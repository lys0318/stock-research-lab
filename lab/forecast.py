"""Future price path: one multi-output Ridge over horizons 1..H, validated on a held-out tail."""
import holidays
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from .data import load_dataset
from .engine import features

HORIZONS = (5, 20, 60)

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
    evaluation = dict(
        hit_rate=float(np.mean((predicted > 0) == (actual > 0))),
        up_rate=float(np.mean(actual > 0)),  # "always up" baseline for hit_rate
        mape=float(np.mean(np.abs(np.exp(predicted-actual)-1))),
        naive_mape=float(np.mean(np.abs(np.exp(-actual)-1))),
        train_rows=int(train.sum()), test_rows=int(test.sum()),
        train_label_end=str(label_end[train].max().date()), test_start=str(test_start.date()))
    if not x.iloc[-1].notna().all():
        raise ValueError("최근 거래일의 지표를 계산할 수 없습니다.")
    model.fit(x[labeled], y[labeled])
    last_close = float(frame.close.iloc[-1])
    path = last_close*np.exp(model.predict(x.iloc[[-1]])[0])
    # ponytail: library KRX calendar matched all 189 weekday gaps in 2014-2026 Samsung data;
    # a holiday declared after the installed `holidays` release is missed until it's upgraded.
    first = dates.iloc[-1] + pd.Timedelta(days=1)
    closed = holidays.financial_holidays("XKRX", years=range(first.year, first.year + 2))
    future = pd.bdate_range(first, periods=horizon, freq="C", holidays=list(closed))
    return dict(horizon=horizon, last_date=str(dates.iloc[-1].date()), last_close=last_close,
        path=[dict(date=str(d.date()), price=float(p)) for d, p in zip(future, path)],
        prices=frame.tail(500).to_dict(orient="records"),
        evaluation=evaluation,
        notice="과거 패턴의 통계적 추정이며 투자 조언이 아닙니다. 날짜는 한국거래소 휴장일을 제외한 거래일입니다.")

def run_forecast(dataset_id, horizon):
    frame, meta = load_dataset(dataset_id)
    return dict(forecast(frame, horizon), dataset=meta)
