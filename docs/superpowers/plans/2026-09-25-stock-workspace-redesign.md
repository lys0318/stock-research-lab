# 종목 작업 공간 개편 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 종목 검색 → 백테스트 → 미래 가격 경로 예측을 한 작업 공간에서 제공하고 UI를 OpenAI Platform 스타일로 바꾼다.

**Architecture:** 백엔드에 `lab/forecast.py`(Ridge 다중 출력 경로 예측)와 `lab/stocks.py`(토스 종목 목록 캐시·검색·자동 수집)를 추가하고 `lab/api.py`에 엔드포인트 3개를 연결한다. 프론트엔드는 864줄 `main.tsx`를 앱 셸·API·홈·작업 공간·보조 페이지로 나누고, `ResearchCharts.tsx`를 차트 종류 4개·이동평균·예측 경로를 지원하는 공용 가격 차트로 확장한다.

**Tech Stack:** Python 3.12, FastAPI, pandas, scikit-learn(Ridge), httpx / React 19, TypeScript, Vite, plotly.js-finance-dist-min.

Spec: `docs/superpowers/specs/2026-09-25-stock-workspace-redesign-design.md`

## Global Constraints
- 예측 기간은 5·20·60거래일만 허용.
- 토스 키는 환경 변수 `TOSS_CLIENT_ID` / `TOSS_CLIENT_SECRET`로만 전달, 파일에 저장하지 않음.
- 자동 수집 최대 15페이지, 저장본 끝 날짜가 오늘보다 5일 넘게 이전일 때만 재수집.
- POST는 기존 `X-Research-Local: 1` 보호를 그대로 받음.
- 색 강조는 상승 #e5383b / 하락 #2563eb 뿐. 주 버튼 검정(#0d0d0d) 알약.
- 공개 모드(`VITE_PUBLIC_MODE=true`)에는 검색·실행·예측이 없음.
- 저장소가 git이 아니므로 커밋 단계는 생략한다.

---

### Task 1: 미래 가격 경로 예측 (`lab/forecast.py`)

**Files:**
- Create: `lab/forecast.py`
- Test: `tests/test_forecast.py`

**Interfaces:**
- Consumes: `lab.engine.features(frame) -> DataFrame`, `lab.data.load_dataset(id) -> (frame, meta)`
- Produces: `forecast(frame, horizon:int) -> dict(horizon, last_date, last_close, path=[{date, price}], evaluation={hit_rate, mape, naive_mape, train_rows, test_rows, train_label_end, test_start}, notice)`; `run_forecast(dataset_id, horizon) -> forecast dict + dataset meta`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
import numpy as np
import pandas as pd
import pytest
from lab.data import demo, load_dataset
from lab.forecast import forecast

@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("LAB_DATA_DIR", str(tmp_path))

def test_path_shape_and_dates():
    f, _ = load_dataset(demo()["id"])
    r = forecast(f, 20)
    assert len(r["path"]) == 20
    dates = pd.to_datetime([p["date"] for p in r["path"]])
    assert dates[0] > pd.Timestamp(r["last_date"]) and (dates.dayofweek < 5).all()
    assert all(np.isfinite(p["price"]) and p["price"] > 0 for p in r["path"])
    assert r["last_close"] == f.close.iloc[-1]

def test_evaluation_has_no_leakage():
    f, _ = load_dataset(demo()["id"])
    e = forecast(f, 60)["evaluation"]
    assert e["train_label_end"] < e["test_start"]
    assert 0 <= e["hit_rate"] <= 1 and e["mape"] >= 0 and e["naive_mape"] >= 0

def test_rejects_bad_horizon_and_short_data():
    f, _ = load_dataset(demo()["id"])
    with pytest.raises(ValueError):
        forecast(f, 7)
    with pytest.raises(ValueError, match="부족"):
        forecast(f.tail(150).reset_index(drop=True), 5)
```

- [ ] **Step 2:** `.venv/Scripts/python.exe -m pytest tests/test_forecast.py -q` → FAIL (ModuleNotFoundError)
- [ ] **Step 3: 구현** — `features()` 재사용, 목표 `log(close[t+k]/close[t])` k=1..H, 평가 시작 = 마지막 날짜 − 2년(학습 행 100 미만이면 정답 확정 행의 80% 지점), 학습 행은 `label_end < test_start`, `StandardScaler → Ridge(alpha=1.0)`. 평가 후 정답 확정 전체 행으로 재학습, 마지막 행 특징으로 경로 산출, 날짜는 `pd.bdate_range`.
- [ ] **Step 4:** 같은 명령 → PASS

### Task 2: 종목 검색·자동 수집 (`lab/stocks.py`, `lab/toss.py`)

**Files:**
- Modify: `lab/toss.py` (토큰 발급을 `client()` 컨텍스트로 분리, `listed_stocks()` 추가)
- Create: `lab/stocks.py`
- Test: `tests/test_stocks.py`

**Interfaces:**
- Produces: `toss.client()` (인증 헤더가 설정된 `httpx.Client`), `toss.listed_stocks() -> [{symbol, name, market}]`, `stocks.has_key() -> bool`, `stocks.search(q:str, limit=20) -> {items:[{symbol,name,market,dataset_id,end}], connected:bool}`, `stocks.prepare(symbol:str) -> dataset meta`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
import pandas as pd
import pytest
from lab import stocks
from lab.data import save_dataset, demo

@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("LAB_DATA_DIR", str(tmp_path))
    for name in ("TOSS_CLIENT_ID", "TOSS_CLIENT_SECRET"):
        monkeypatch.delenv(name, raising=False)

def prices(end="2026-09-24", n=30):
    d = pd.bdate_range(end=end, periods=n)
    return pd.DataFrame(dict(date=d, open=100., high=101., low=99., close=100., volume=10))

def saved(symbol="005930", name="삼성전자", end="2026-09-24"):
    return save_dataset(prices(end), symbol, name, "test", False, "test")

def test_search_without_key_uses_saved_only():
    demo(); meta = saved()
    r = stocks.search("삼성")
    assert r["connected"] is False
    assert [i["symbol"] for i in r["items"]] == ["005930"]
    assert r["items"][0]["dataset_id"] == meta["id"]
    assert stocks.search("0059")["items"][0]["name"] == "삼성전자"
    assert all(i["symbol"] != "000000" for i in stocks.search("")["items"])

def test_prepare_without_key(monkeypatch):
    meta = saved(end="2020-01-03")
    assert stocks.prepare("005930")["id"] == meta["id"]
    with pytest.raises(ValueError, match="토스 키"):
        stocks.prepare("000660")

def test_prepare_collects_new_symbol(monkeypatch):
    monkeypatch.setenv("TOSS_CLIENT_ID", "x"); monkeypatch.setenv("TOSS_CLIENT_SECRET", "y")
    monkeypatch.setattr(stocks, "listed_stocks", lambda: [dict(symbol="000660", name="SK하이닉스", market="KOSPI")])
    calls = []
    monkeypatch.setattr(stocks, "collect", lambda symbol, output, max_pages: calls.append((symbol, max_pages)))
    monkeypatch.setattr(stocks, "import_raw", lambda folder, symbol, name: saved(symbol, name))
    assert stocks.search("하이닉스")["items"][0]["market"] == "KOSPI"
    meta = stocks.prepare("000660")
    assert meta["name"] == "SK하이닉스" and calls == [("000660", 15)]
    assert stocks.prepare("000660")["id"] == meta["id"] and len(calls) == 1
```

- [ ] **Step 2:** `.venv/Scripts/python.exe -m pytest tests/test_stocks.py -q` → FAIL
- [ ] **Step 3: 구현** — `universe()`는 `data/universe.json`을 24시간 캐시, 키 없거나 실패 시 기존 캐시 또는 빈 목록. `latest()`는 실제 데이터 종목별 끝 날짜가 가장 늦은 버전. 검색 정렬: 저장됨 → 코드·이름 정확 일치 → 이름 시작 일치 → 이름순. `prepare()`는 종목별 잠금, 5일 기준 재수집, 실패 시 저장본이 있으면 그대로 반환.
- [ ] **Step 4:** 같은 명령 + `tests/test_connect.py tests/test_real_data.py` → PASS

### Task 3: API 연결과 `serve` 키 입력

**Files:**
- Modify: `lab/api.py` (엔드포인트 3개), `lab/cli.py` (`serve` 시 키 선택 입력)
- Test: `tests/test_stocks.py`에 API 테스트 추가

- [ ] **Step 1: 실패하는 테스트 추가**

```python
from fastapi.testclient import TestClient
from lab.api import app

def test_api_routes():
    meta = demo(); saved()
    with TestClient(app) as c:
        assert c.get("/api/stocks", params={"q": "삼성"}).json()["items"][0]["symbol"] == "005930"
        assert c.post("/api/stocks/005930/prepare").status_code == 403
        assert c.post("/api/stocks/000660/prepare", headers={"X-Research-Local": "1"}).status_code == 422
        r = c.get("/api/forecast", params={"dataset_id": meta["id"], "horizon": 5})
        assert r.status_code == 200 and len(r.json()["path"]) == 5
        assert c.get("/api/forecast", params={"dataset_id": meta["id"], "horizon": 7}).status_code == 422
```

- [ ] **Step 2:** FAIL(404) 확인 → **Step 3:** 엔드포인트 구현(ValueError → 422) → **Step 4:** 전체 `pytest -q` PASS

### Task 4: 디자인 토큰과 앱 셸

**Files:**
- Modify: `web/src/tokens.css`, `web/src/style.css`(전면 교체), `web/index.html`(theme-color·아이콘)
- Create: `web/src/api.ts` (타입 `Dataset, Config, Job, Result, Benchmark, StockHit, Forecast`; `api()`, `won`, `pct`, `labels`, `states`, `publicMode`)
- Modify: `web/src/main.tsx` → 앱 셸만: 사이드바(새 분석·실험 기록·클라우드 실험·데이터 안내), 상단 바, 흰 메인 패널, 화면 상태 `{view:"home"} | {view:"stock", symbol} | {view:"history"|"cloud"|"data"}`, 3초 폴링(datasets·runs·benchmarks)

- [ ] 검증: `cd web && npm run build` 성공

### Task 5: 홈과 기록·보조 페이지

**Files:**
- Create: `web/src/Home.tsx` — 검색 입력(250ms 디바운스로 `/api/stocks?q=`), 결과 목록(저장됨/토스 수집 배지), 저장된 종목 칩, 최근 실험 카드 6개. 선택 시 `onOpenStock(symbol, name)`.
- Create: `web/src/Pages.tsx` — `History`(실험 카드 목록·취소·열기), `Cloud`, `DataInfo` (기존 내용 이관)
- [ ] 검증: `npm run build` 성공

### Task 6: 종목 작업 공간과 결과

**Files:**
- Create: `web/src/Workspace.tsx` — 진입 시 `POST /api/stocks/{symbol}/prepare`(수집 중 안내), 머리글, 탭(과거 백테스트 / 미래 예측). 백테스트: 기간 프리셋(1년·2년·5년·직접, 끝 = 데이터 끝), 전략 카드, 이동평균 기간, 시작 자금, 접힌 고급 설정, 실행 → 1초 폴링 → 결과 자동 로드. 결과: 요약 문장, 보유 대비, 최대 낙폭, 거래 횟수, 승률, 차트, 왕복 거래 표(`roundTrips(trades)`), CSV. 예측: 5/20/60 선택 → `/api/forecast` → 차트 + 예상 가격·변화율 + 검증 수치 + 안내.
- 기록에서 결과를 열면 `initialResult`로 같은 작업 공간에 표시.
- [ ] 검증: `npm run build` 성공

### Task 7: 공용 가격 차트

**Files:**
- Modify: `web/src/ResearchCharts.tsx` — `PriceChart({prices, trades?, forecast?, focus?})`: 종류 캔들·OHLC·선·영역 전환, 이동평균 5·20·60·120 토글, 거래량, ▲/▼, 예측 점선 + 마지막 가격 주석. `EquityChart(result)` 유지. 색 상승 #e5383b / 하락 #2563eb.
- [ ] 검증: `npm run build` 성공

### Task 8: 문서와 브라우저 검증

**Files:**
- Modify: `DESIGN.md`, `PRODUCT.md`(Visual commitment), `README.md`(새 흐름·`serve` 키 입력)
- [ ] 백엔드 `serve` + `npm run dev` 실행, 브라우저로 홈 검색 → 삼성전자 → 2년·이동평균 실행 → 결과 자동 표시 → 차트 종류 4개·이동평균 토글 → 예측 20일 → 모바일 390px 확인, 콘솔 오류 0
- [ ] `pytest -q` 전체 PASS, `npm run build` 및 `npm run build:public` 성공
