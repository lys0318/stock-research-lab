"""Stock search over saved datasets + the Toss listing, and on-demand daily candle collection."""
from datetime import date, datetime, timedelta, timezone
import json
import os
import threading
import time
import httpx
from .data import datasets, root
from .toss import collect, import_raw, listed_stocks

_guard = threading.Lock()
_locks = {}

def has_key():
    return bool(os.environ.get("TOSS_CLIENT_ID") and os.environ.get("TOSS_CLIENT_SECRET"))

_failed_at = 0.

def universe():
    """Toss KOSPI·KOSDAQ listing cached for a day. Falls back to the stale cache, then to nothing."""
    global _failed_at
    path = root() / "universe.json"
    cached = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    if not has_key() or (cached and time.time()-path.stat().st_mtime < 86400) or time.time()-_failed_at < 600:
        return cached
    try:
        fresh = listed_stocks()
    except (ValueError, httpx.HTTPError):
        _failed_at = time.time()  # e.g. a revoked key: don't hit Toss on every keystroke
        return cached
    path.write_text(json.dumps(fresh, ensure_ascii=False), encoding="utf-8")
    return fresh

def latest():
    """Newest real (non-synthetic) dataset version per symbol."""
    best = {}
    for meta in datasets():
        if meta["synthetic"]: continue
        current = best.get(meta["symbol"])
        if not current or (meta["end"], meta["rows"]) > (current["end"], current["rows"]):
            best[meta["symbol"]] = meta
    return best

def search(q, limit=20):
    q = q.strip().lower()
    items = {s: dict(symbol=s, name=m["name"], market=None, dataset_id=m["id"], end=m["end"]) for s, m in latest().items()}
    listing = universe()
    for stock in listing:
        item = items.setdefault(stock["symbol"], dict(stock, dataset_id=None, end=None))
        item["market"] = stock["market"]
    hits = [i for i in items.values() if not q or q in i["name"].lower() or i["symbol"].startswith(q)]
    hits.sort(key=lambda i: (i["dataset_id"] is None, q not in (i["symbol"], i["name"].lower()),
                             not i["name"].lower().startswith(q), i["name"]))
    # "connected" means the full listing is actually searchable, not merely that a key is set.
    return dict(items=hits[:limit], connected=bool(listing))

def prepare(symbol):
    """Return the symbol's newest dataset, collecting from Toss when missing or older than 5 days."""
    if not symbol.isdigit() or len(symbol) != 6: raise ValueError("6자리 국내 종목 코드가 필요합니다.")
    with _guard: lock = _locks.setdefault(symbol, threading.Lock())
    with lock:
        meta = latest().get(symbol)
        fresh = meta and date.fromisoformat(meta["end"]) >= date.today() - timedelta(days=5)
        if fresh or not has_key():
            if meta: return meta
            raise ValueError("토스 키 없이 실행 중이라 새 종목을 받을 수 없습니다. 서버를 토스 키와 함께 다시 실행하세요.")
        name = next((s["name"] for s in universe() if s["symbol"] == symbol), None) or (meta and meta["name"])
        if not name: raise ValueError("토스 종목 목록에서 찾을 수 없는 코드입니다.")
        folder = root() / "raw" / ("toss-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
        try:
            collect(symbol, str(folder), max_pages=15)
            return import_raw(folder, symbol, name)
        except (ValueError, httpx.HTTPError):
            if meta: return meta  # stale data beats no data; the UI shows the data end date
            raise
