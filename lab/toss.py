"""Read-only official REST collector. Raw response is evidence, not approved data."""
import json
from contextlib import contextmanager
import os
import time
from pathlib import Path
import httpx

BASE = "https://openapi.tossinvest.com"
@contextmanager
def client():
    """httpx.Client carrying a fresh bearer token. Credentials come from the environment only."""
    key, secret = os.environ.get("TOSS_CLIENT_ID"), os.environ.get("TOSS_CLIENT_SECRET")
    if not key or not secret:
        raise ValueError("TOSS_CLIENT_ID, TOSS_CLIENT_SECRET 환경 변수를 로컬에서 설정하세요.")
    with httpx.Client(base_url=BASE,timeout=30) as session:
        response = session.post("/oauth2/token",data=dict(grant_type="client_credentials",client_id=key,client_secret=secret))
        if response.status_code != 200: raise ValueError(f"토스 인증 실패 HTTP {response.status_code}; 키와 허용 IP를 확인하세요.")
        token = response.json().get("access_token")
        if not token: raise ValueError("공식 토큰 응답 형식이 변경되었습니다. 응답을 공개하지 말고 문서를 확인하세요.")
        session.headers["Authorization"] = f"Bearer {token}"
        yield session

def get(session, path, params):
    """GET that waits out 429s (stocks/all allows 1 request per second)."""
    for attempt in range(4):
        r = session.get(path,params=params)
        if r.status_code != 429: break
        time.sleep(min(30,max(1,float(r.headers.get("Retry-After","2")))))
    return r

def listed_stocks():
    """KOSPI·KOSDAQ listed common/preferred stocks (daily batch data on Toss's side)."""
    stocks = []
    with client() as session:
        for market in ("KOSPI", "KOSDAQ"):
            r = get(session,"/api/v1/stocks/all",dict(market=market,securityType="STOCK"))
            if r.status_code != 200: raise ValueError(f"종목 목록 조회 실패 HTTP {r.status_code}")
            stocks += [dict(symbol=s["symbol"],name=s["name"],market=market) for s in r.json().get("result",[])]
    return stocks

def collect(symbol, output, max_pages=1):
    if not symbol.isdigit() or len(symbol)!=6: raise ValueError("6자리 국내 종목 코드 필요")
    folder = Path(output)
    with client() as session:
        folder.mkdir(parents=True,exist_ok=True)
        before = None
        seen = set()
        for page in range(max_pages):
            params = dict(symbol=symbol,interval="1d",count=200,adjusted="true")
            if before: params["before"]=before
            r = get(session,"/api/v1/candles",params)
            if r.status_code != 200: raise ValueError(f"주가 조회 실패 HTTP {r.status_code}")
            payload = r.json()
            (folder/f"{symbol}-{page:04}.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
            body = payload.get("result",{})
            if not isinstance(body,dict) or "candles" not in body:
                raise ValueError("원본 저장 완료. 응답 스키마를 공식 문서와 대조한 뒤 변환기를 확정하세요.")
            next_before = body.get("nextBefore")
            if not next_before: break
            if next_before in seen: raise ValueError("페이지 커서 반복 감지")
            seen.add(next_before)
            before = next_before
            time.sleep(.25)
    return dict(output=str(folder),notice="원본만 수집했습니다. OHLCV 매핑·조정 기준·권한 검증 후 CSV로 등록하세요.")


def import_raw(folder, symbol, name):
    """Register adjusted daily snapshots for local exploration, not publication.

    Inclusive cursor boundaries may repeat identical candles. Conflicting
    duplicates are rejected; never silently choose one set of prices.
    """
    import pandas as pd
    from .data import save_dataset
    if not symbol.isdigit() or len(symbol) != 6:
        raise ValueError("6자리 국내 종목 코드 필요")
    records = []
    for path in sorted(Path(folder).glob(f"{symbol}-[0-9][0-9][0-9][0-9].json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        candles = payload.get("result", {}).get("candles")
        if not isinstance(candles, list):
            raise ValueError("토스 일봉 응답 형식 오류")
        for candle in candles:
            if candle.get("currency") != "KRW":
                raise ValueError("국내 주식 KRW 데이터만 지원합니다.")
            stamp = pd.Timestamp(candle["timestamp"])
            if stamp.tzinfo is None:
                raise ValueError("타임존 없는 일봉 날짜")
            records.append(dict(date=stamp.tz_convert("Asia/Seoul").strftime("%Y-%m-%d"),
                **{key: float(candle[source]) for key, source in {
                    "open": "openPrice", "high": "highPrice", "low": "lowPrice",
                    "close": "closePrice", "volume": "volume"}.items()}))
    if not records:
        raise ValueError("등록할 토스 일봉이 없습니다.")
    frame = pd.DataFrame(records).drop_duplicates()
    if frame.date.duplicated().any():
        raise ValueError("같은 거래일의 가격이 서로 다릅니다. 원본을 확인하세요.")
    frame = frame.sort_values("date").reset_index(drop=True)
    adjustment = "토스 수정주가(adjusted=true). 분할·배당 세부 기준 미확인, 배당 현금흐름 미포함. 로컬 탐색용."
    return save_dataset(frame, symbol, name, "토스증권 Open API · 일봉 스냅샷", False, adjustment, rights=False)
