"""Future price: Ridge center path, volatility range, per-indicator drivers, and similar past charts.

Every piece is validated on the held-out tail (last 2 years) with the same code used for today's forecast.
"""
import math
import holidays
import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from .data import load_dataset
from .engine import features

HORIZONS = (5, 20, 60)
WINDOW, ANALOGS, SPACING = 60, 5, 20
Z80, Z50 = 1.2816, 0.6745
LABELS = dict(return_1="어제 대비 수익률", return_5="최근 5일 수익률", ma20_gap="20일 이동평균과의 거리",
              ma60_gap="60일 이동평균과의 거리", volume_change="거래량 변화", volatility="20일 변동성")

def normal_cdf(v): return .5*(1+math.erf(v/math.sqrt(2)))

def rebased_windows(log_close):
    """Row r: the WINDOW+1 log prices ending at index r+WINDOW, shifted so the last point is 0."""
    shapes = sliding_window_view(log_close, WINDOW+1)
    return shapes - shapes[:, -1:]

def similar(shapes, end, horizon, k=ANALOGS):
    """(window end, distance) of the k past charts closest to the one ending at `end`.

    Only windows whose horizon-day outcome was known before `end` qualify (j + horizon < end),
    and picks sit >= SPACING days apart so one episode isn't counted twice.
    """
    last = end - horizon - 1
    if last < WINDOW: return []
    dist = np.linalg.norm(shapes[:last-WINDOW+1] - shapes[end-WINDOW], axis=1)
    picks = []
    for r in np.argsort(dist):
        j = int(r) + WINDOW
        if all(abs(j - p) >= SPACING for p, _ in picks): picks.append((j, float(dist[r])))
        if len(picks) == k: break
    return picks

def forecast(frame, horizon):
    if horizon not in HORIZONS: raise ValueError("예측 기간은 5, 20, 60거래일 중 하나입니다.")
    x = features(frame)
    log_close = np.log(frame.close)
    # Target k: log(close[t+k] / close[t]) for every step of the path.
    y = pd.DataFrame({k: log_close.shift(-k) - log_close for k in range(1, horizon+1)})
    dates = pd.to_datetime(frame.date)
    label_end = dates.shift(-horizon)
    labeled = x.notna().all(axis=1) & y.notna().all(axis=1)
    test_start = dates.iloc[-1] - pd.DateOffset(years=2)
    if (labeled & (label_end < test_start)).sum() < 100 and labeled.sum():
        test_start = dates[labeled].iloc[int(labeled.sum()*.8)]
    train = labeled & (label_end < test_start)
    test = labeled & (dates >= test_start)
    if train.sum() < 100 or test.sum() < 30:
        raise ValueError("예측 학습·검증 데이터가 부족합니다. 최소 1년 이상의 일봉이 필요합니다.")
    model = make_pipeline(StandardScaler(), Ridge(alpha=1.0))
    model.fit(x[train], y[train])
    predicted = model.predict(x[test])[:, -1]
    actual = y[test].iloc[:, -1].to_numpy()
    # ponytail: normal approximation of log returns; fat tails (crashes, limit-ups) are under-covered.
    sigma = log_close.diff().rolling(WINDOW).std()
    spread = sigma[test].to_numpy()*math.sqrt(horizon)
    known = ~np.isnan(spread)
    miss = np.abs(actual - predicted)[known]
    lc = log_close.to_numpy()
    shapes = rebased_windows(lc)
    hits = []
    for i in np.flatnonzero(test.to_numpy())[::5]:  # ponytail: every 5th day keeps the request ~1s
        picks = similar(shapes, i, horizon)
        if picks: hits.append((np.median([lc[j+horizon]-lc[j] for j, _ in picks]) > 0) == (lc[i+horizon]-lc[i] > 0))
    evaluation = dict(
        hit_rate=float(np.mean((predicted > 0) == (actual > 0))),
        up_rate=float(np.mean(actual > 0)),  # "always up" baseline for hit_rate
        mape=float(np.mean(np.abs(np.exp(predicted-actual)-1))),
        naive_mape=float(np.mean(np.abs(np.exp(-actual)-1))),
        band80_cover=float(np.mean(miss <= Z80*spread[known])),
        band50_cover=float(np.mean(miss <= Z50*spread[known])),
        analog_hit_rate=float(np.mean(hits)) if hits else None,
        train_rows=int(train.sum()), test_rows=int(test.sum()),
        train_label_end=str(label_end[train].max().date()), test_start=str(test_start.date()))
    if not x.iloc[-1].notna().all():
        raise ValueError("최근 거래일의 지표를 계산할 수 없습니다.")
    model.fit(x[labeled], y[labeled])
    center = model.predict(x.iloc[[-1]])[0]
    last_close = float(frame.close.iloc[-1])
    # ponytail: library KRX calendar matched all 189 weekday gaps in 2014-2026 Samsung data;
    # a holiday declared after the installed `holidays` release is missed until it's upgraded.
    first = dates.iloc[-1] + pd.Timedelta(days=1)
    closed = holidays.financial_holidays("XKRX", years=range(first.year, first.year + 2))
    future = [str(d.date()) for d in pd.bdate_range(first, periods=horizon, freq="C", holidays=list(closed))]
    now = float(sigma.iloc[-1])
    band = [dict(date=d, **{name: last_close*math.exp(c + z*now*math.sqrt(k)) for name, z in
                 (("p10", -Z80), ("p25", -Z50), ("p75", Z50), ("p90", Z80))})
            for k, (d, c) in enumerate(zip(future, center), start=1)]
    end_c, end_s = center[-1], now*math.sqrt(horizon)
    probabilities = dict(up=1-normal_cdf(-end_c/end_s), up10=1-normal_cdf((math.log(1.1)-end_c)/end_s),
                         down10=normal_cdf((math.log(.9)-end_c)/end_s))
    # Linear model: prediction = intercept + sum(coef * standardized feature), split exactly per indicator.
    scaler, ridge = model.named_steps["standardscaler"], model.named_steps["ridge"]
    z = (x.iloc[-1].to_numpy() - scaler.mean_)/scaler.scale_
    drivers = sorted((dict(key=key, label=LABELS[key], value=float(x.iloc[-1][key]), contribution=float(c))
                      for key, c in zip(x.columns, ridge.coef_[horizon-1]*z)), key=lambda d: -abs(d["contribution"]))
    today = len(lc) - 1
    analogs = [dict(start=str(dates.iloc[j-WINDOW].date()), end=str(dates.iloc[j].date()),
                    change=float(math.exp(lc[j+horizon]-lc[j])-1), gap=dist/math.sqrt(WINDOW+1),
                    path=[dict(date=d, price=last_close*math.exp(lc[j+k]-lc[j])) for k, d in enumerate(future, start=1)],
                    shape=(lc[j-WINDOW:j+horizon+1]-lc[j]).tolist())
               for j, dist in similar(shapes, today, horizon)]
    return dict(horizon=horizon, last_date=str(dates.iloc[-1].date()), last_close=last_close, window=WINDOW,
        path=[dict(date=d, price=last_close*math.exp(c)) for d, c in zip(future, center)],
        band=band, probabilities=probabilities, drivers=drivers, trend=float(ridge.intercept_[horizon-1]),
        analogs=analogs, current_shape=shapes[today-WINDOW].tolist(),
        prices=frame.tail(500).to_dict(orient="records"),
        evaluation=evaluation,
        notice="과거 패턴의 통계적 추정이며 투자 조언이 아닙니다. 날짜는 한국거래소 휴장일을 제외한 거래일입니다.")

def run_forecast(dataset_id, horizon):
    frame, meta = load_dataset(dataset_id)
    return dict(forecast(frame, horizon), dataset=meta)
