import hashlib
import json
import os
from pathlib import Path
import numpy as np
import pandas as pd

def root():
    p = Path(os.environ.get("LAB_DATA_DIR", "data")).resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p

def validate(frame):
    required = ["date", "open", "high", "low", "close", "volume"]
    if not set(required).issubset(frame.columns):
        raise ValueError("OHLCV 필수 열이 없습니다.")
    f = frame[required].copy()
    f["date"] = pd.to_datetime(f.date).dt.strftime("%Y-%m-%d")
    if f.date.duplicated().any() or not f.date.is_monotonic_increasing:
        raise ValueError("거래일 중복 또는 순서 오류")
    for col in required[1:]:
        f[col] = pd.to_numeric(f[col], errors="raise")
    if not np.isfinite(f[required[1:]].to_numpy()).all():
        raise ValueError("누락 또는 무한대 값")
    if (f[required[1:5]] <= 0).any().any() or (f.volume < 0).any():
        raise ValueError("가격·거래량 범위 오류")
    if ((f.high < f[["open", "close", "low"]].max(axis=1)) | (f.low > f[["open", "close", "high"]].min(axis=1))).any():
        raise ValueError("OHLC 가격 관계 오류")
    if len(f) < 2:
        raise ValueError("데이터가 부족합니다.")
    return f

def save_dataset(frame, symbol, name, source, synthetic, adjustment, rights=False):
    f = validate(frame)
    if not symbol.isdigit() or len(symbol) != 6:
        raise ValueError("종목 코드는 6자리 숫자여야 합니다.")
    fingerprint = f.to_csv(index=False).encode() + json.dumps([symbol, source, synthetic, adjustment]).encode()
    version = hashlib.sha256(fingerprint).hexdigest()[:20]
    folder = root() / "datasets" / version
    folder.mkdir(parents=True, exist_ok=True)
    f.to_parquet(folder / "prices.parquet", index=False)
    meta = dict(id=version, symbol=symbol, name=name, source=source, synthetic=synthetic,
                adjustment=adjustment, publication_allowed=rights, rows=len(f),
                start=f.date.iloc[0], end=f.date.iloc[-1])
    (folder / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta

def datasets():
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((root() / "datasets").glob("*/metadata.json"))]

def load_dataset(version):
    meta = next((x for x in datasets() if x["id"] == version), None)
    if not meta:
        raise ValueError("데이터 버전을 찾을 수 없습니다.")
    return validate(pd.read_parquet(root() / "datasets" / version / "prices.parquet")), meta

def demo():
    rng = np.random.default_rng(42)
    dates = pd.bdate_range("2016-01-01", "2025-12-31")
    close = 50000 * np.exp(np.cumsum(rng.normal(.00015, .015, len(dates))))
    opening = np.r_[close[0], close[:-1]] * np.exp(rng.normal(0, .003, len(dates)))
    frame = pd.DataFrame(dict(date=dates, open=opening, close=close,
        high=np.maximum(opening, close)*1.01, low=np.minimum(opening, close)*.99,
        volume=rng.integers(100000, 2000000, len(dates))))
    return save_dataset(frame, "000000", "개발용 가상 종목", "synthetic-seed-42", True, "synthetic-no-actions")

def import_csv(path, metadata):
    m = json.loads(Path(metadata).read_text(encoding="utf-8"))
    if not m.get("adjustment") or m["adjustment"] == "unknown":
        raise ValueError("분할·배당 및 가격 조정 기준을 metadata에 명시하세요.")
    return save_dataset(pd.read_csv(path), m["symbol"], m["name"], m["source"],
                        False, m["adjustment"], bool(m.get("publication_allowed", False)))
