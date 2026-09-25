# 미래 예측 발전 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 기존 Ridge 경로 예측에 변동성 기반 예측 범위·확률, 지표별 근거 분해, 비슷한 과거 차트 시나리오와 그 검증 지표를 더한다.

**Architecture:** `lab/forecast.py`의 `forecast()` 응답에 필드를 추가한다(엔드포인트 변경 없음). 비슷한 차트 검색은 `rebased_windows()`와 `similar()` 순수 함수로 분리해 오늘 예측과 검증이 같은 코드를 쓴다. 화면은 `Forecast.tsx`에 요약·근거·유사 차트 카드를 추가하고, `ResearchCharts.PriceChart`에 `band`·`scenarios` 선택 입력과 토글을 더한다.

**Tech Stack:** Python 3.12, numpy(sliding_window_view), scikit-learn Ridge / React 19, TypeScript, Plotly.

Spec: `docs/superpowers/specs/2026-09-25-forecast-range-analogs-design.md`

## Global Constraints
- 창 W=60, 시나리오 5개, 시나리오 간 최소 간격 20거래일, 후보는 j + H < 기준 인덱스.
- 범위 σ = 최근 60거래일 일별 로그수익률 표준편차, k일 σ√k, z80=1.2816, z50=0.6745.
- 시나리오 검증은 평가 구간에서 5거래일 간격 표본.
- 커밋 메시지는 한국어.

---

### Task 1: 범위·확률·근거·시나리오 계산 (`lab/forecast.py`)

**Files:** Modify `lab/forecast.py`; Test `tests/test_forecast.py`

**Interfaces:**
- Produces: `LABELS: dict[str, str]`, `rebased_windows(log_close: np.ndarray) -> np.ndarray` (행 r = 인덱스 r+60에서 끝나는 61점 경로, 끝 기준 0), `similar(shapes, end: int, horizon: int, k=5) -> list[tuple[int, float]]` (창 끝 인덱스, 거리), `forecast()` 응답 필드 `band, probabilities, drivers, trend, analogs, current_shape, window` 및 `evaluation.band80_cover, band50_cover, analog_hit_rate`.

- [ ] **Step 1: 실패하는 테스트**

```python
from lab.forecast import LABELS, forecast, rebased_windows, similar

def test_band_orders_and_widens():
    f, _ = load_dataset(demo()["id"])
    r = forecast(f, 20)
    for b, p in zip(r["band"], r["path"]):
        assert b["p10"] < b["p25"] < p["price"] < b["p75"] < b["p90"]
    widths = [b["p90"] / b["p10"] for b in r["band"]]
    assert widths == sorted(widths)
    pr = r["probabilities"]
    assert 0 <= pr["up10"] <= pr["up"] <= 1 and 0 <= pr["down10"] <= 1

def test_drivers_sum_to_center():
    f, _ = load_dataset(demo()["id"])
    r = forecast(f, 20)
    total = sum(d["contribution"] for d in r["drivers"]) + r["trend"]
    assert total == pytest.approx(np.log(r["path"][-1]["price"] / r["last_close"]))
    assert {d["key"] for d in r["drivers"]} == set(LABELS)

def test_similar_charts_use_only_known_outcomes():
    f, _ = load_dataset(demo()["id"])
    picks = similar(rebased_windows(np.log(f.close.to_numpy())), 1500, 20)
    ends = [j for j, _ in picks]
    assert len(ends) == 5 and all(j + 20 < 1500 for j in ends)
    assert all(abs(a - b) >= 20 for a in ends for b in ends if a != b)
    r = forecast(f, 20)
    assert len(r["analogs"]) == 5
    assert all(len(a["path"]) == 20 and len(a["shape"]) == 81 for a in r["analogs"])
    assert len(r["current_shape"]) == 61
    e = r["evaluation"]
    assert all(0 <= e[k] <= 1 for k in ("band80_cover", "band50_cover", "analog_hit_rate"))
```

- [ ] **Step 2:** `.venv/Scripts/python.exe -m pytest tests/test_forecast.py -q` → ImportError(LABELS) 실패 확인
- [ ] **Step 3: 구현** — 스펙의 계산 절을 그대로 구현. `similar()`는 거리 오름차순 탐욕 선택으로 간격 조건 충족. 근거는 `ridge.coef_[H-1] * (x_last - scaler.mean_) / scaler.scale_`, `trend = ridge.intercept_[H-1]`. 확률은 `math.erf` 정규 누적분포.
- [ ] **Step 4:** 같은 명령 PASS, 전체 `pytest -q` PASS
- [ ] **Step 5:** 커밋 `미래 예측에 범위·근거·비슷한 과거 차트 계산 추가`

### Task 2: 차트에 범위·시나리오 표시 (`web/src/ResearchCharts.tsx`, `web/src/api.ts`)

- `Forecast` 타입에 새 필드 추가.
- `PriceChart` 선택 입력 `band?: Band[]`, `scenarios?: { label: string; path: {date; price}[] }[]`. 제공될 때만 '범위'·'시나리오' 토글 표시(기본 켜짐). 80% 범위(p90→p10, `fill: "tonexty"`, 옅게), 50% 범위(p75→p25, 진하게)를 마지막 실제 종가에서 시작. 시나리오는 회색 가는 선. y축 자동 맞춤에 범위·시나리오 포함.
- 검증: `npx tsc --noEmit`

### Task 3: 예측 화면 (`web/src/Forecast.tsx`, `web/src/style.css`)

- 요약: 중앙 예상 가격, 80%·50% 범위 문장, 확률 칩 3개.
- 예측 근거: 지표 설명 문장(예: "20일선보다 3.5% 아래")과 기여도 막대(상승 빨강·하락 파랑), 평균 추세, 합계.
- 비슷한 과거 차트: "지금" 카드(현재 60일 미니 차트) + 5개 카드(과거 60일 회색 + 이후 H일 색, 기간, 이후 변화, 평균 차이), 요약 문장.
- 검증 4칸: 방향 적중률, 평균 가격 오차, 80% 범위 적중률(목표 80%), 시나리오 방향 적중률. 80% 범위 적중률 < 0.7이면 경고.
- 검증: `npx tsc --noEmit`, 브라우저에서 카카오 5·20·60일 확인, 모바일 가로 넘침 없음, 콘솔 오류 0.
- 커밋 `미래 예측 화면에 범위·근거·비슷한 과거 차트 표시`
