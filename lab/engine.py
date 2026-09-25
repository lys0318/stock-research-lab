import hashlib
import inspect
import time
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss
from . import strategies
from .data import load_dataset
from .strategies import resolve, signals as rule_signals

def features(frame):
    c = frame.close
    return pd.DataFrame({
        "return_1": c.pct_change(), "return_5": c.pct_change(5),
        "ma20_gap": c/c.rolling(20).mean()-1,
        "ma60_gap": c/c.rolling(60).mean()-1,
        "volume_change": frame.volume.pct_change(),
        "volatility": c.pct_change().rolling(20).std(),
    }).replace([np.inf, -np.inf], np.nan)

def model_signals(frame, start, end, seed):
    x = features(frame)
    # Signal on t, enter t+1 open, exit t+5 close.
    future = frame.close.shift(-5) / frame.open.shift(-1) - 1
    dates = pd.to_datetime(frame.date)
    test_start = pd.Timestamp(start)
    validation_start = test_start - pd.DateOffset(years=1)
    label_end = dates.shift(-5)
    usable = x.notna().all(axis=1) & future.notna()
    train = usable & (label_end < validation_start)
    validation = usable & (dates >= validation_start) & (label_end < test_start)
    test = usable & (dates >= test_start) & (label_end <= pd.Timestamp(end))
    if train.sum() < 100 or validation.sum() < 30 or test.sum() < 10:
        raise ValueError("모델 학습·검증·평가 데이터가 부족합니다. 평가 시작 전 최소 2년을 확보하세요.")
    y = (future > 0).astype(int)
    if y[train].nunique() < 2:
        raise ValueError("학습 구간에 상승·하락 두 클래스가 필요합니다.")
    model = make_pipeline(StandardScaler(), LogisticRegression(random_state=seed, max_iter=1000))
    model.fit(x[train], y[train])
    pv = model.predict_proba(x[validation])[:, 1]
    thresholds = [.5, .55, .6, .65]
    threshold = max(thresholds, key=lambda t: (accuracy_score(y[validation], pv >= t), -t))
    p = pd.Series(np.nan, index=frame.index)
    valid_x = x.notna().all(axis=1)
    p.loc[valid_x] = model.predict_proba(x[valid_x])[:, 1]
    score = dict(accuracy=float(accuracy_score(y[test], p[test] >= threshold)),
                 brier=float(brier_score_loss(y[test], p[test])), threshold=threshold,
                 train_rows=int(train.sum()), validation_rows=int(validation.sum()),
                 test_rows=int(test.sum()), train_label_end=str(label_end[train].max().date()),
                 validation_label_end=str(label_end[validation].max().date()),
                 validation_start=str(validation_start.date()))
    return (p >= threshold).to_numpy(), score

def simulate(frame, signals, strategy, capital=1000000, fee=.00015, tax=0., slippage=.0005):
    cash, qty, entry_index = float(capital), 0, -1
    trades, curve = [], []
    def trade(i, side, price, phase="open"):
        nonlocal cash, qty, entry_index
        if side == "buy":
            execution = price*(1+slippage)
            shares = int(cash//(execution*(1+fee)))
            if shares == 0: return
            cost = shares*execution*fee
            cash -= shares*execution+cost
            qty = shares
            entry_index = i
        else:
            execution = price*(1-slippage)
            shares = qty
            cost = shares*execution*(fee+tax)
            cash += shares*execution-cost
            qty = 0
        trades.append(dict(date=str(frame.date.iloc[i]), side=side, shares=shares,
                           price=float(execution), costs=float(cost), cash=float(cash), phase=phase))
    for i, row in enumerate(frame.itertuples()):
        # Signals use ONLY the preceding closed bar. No same-close fills.
        if strategy == "hold":
            if i == 0: trade(i, "buy", row.open)
        elif strategy == "model":
            if i > 0 and signals[i-1] and qty == 0 and i+4 < len(frame):
                trade(i, "buy", row.open)
            if qty and i-entry_index == 4: trade(i, "sell", row.close, "close")
        else:  # every chart rule: signals[t] is the hold state decided at t's close
            if i > 0 and signals[i-1] and qty == 0: trade(i, "buy", row.open)
            elif i > 0 and not signals[i-1] and qty: trade(i, "sell", row.open)
        if i == len(frame)-1 and qty: trade(i, "sell", row.close, "close")
        curve.append(dict(date=str(row.date), equity=float(cash+qty*row.close)))
    equity = np.array([capital]+[r["equity"] for r in curve])
    drawdown = equity/np.maximum.accumulate(equity)-1
    for r, dd in zip(curve, drawdown[1:]): r["drawdown"] = float(dd)
    return dict(curve=curve, trades=trades, metrics=dict(
        total_return=float(equity[-1]/capital-1), max_drawdown=float(drawdown.min()),
        trade_count=len(trades), final_equity=float(equity[-1])))

def round_trips(trades):
    """Profit of each buy→sell pair, costs on both legs. Trades always alternate buy, sell."""
    return [s["shares"]*s["price"]-s["costs"]-(b["shares"]*b["price"]+b["costs"]) for b, s in zip(trades[::2], trades[1::2])]

def run(config):
    began = time.perf_counter()
    frame, meta = load_dataset(config["dataset_id"])
    mask = (frame.date >= config["start"]) & (frame.date <= config["end"])
    if config["start"] < meta["start"] or config["end"] > meta["end"] or mask.sum() < 10:
        raise ValueError("선택 기간이 확보 데이터 범위를 벗어나거나 너무 짧습니다.")
    signals, scores, params, marks = np.zeros(len(frame), dtype=bool), None, {}, []
    strategy = config["strategy"]
    if strategy == "model":
        signals, scores = model_signals(frame, config["start"], config["end"], config.get("seed",42))
    elif strategy != "hold":
        params = resolve(strategy, config.get("params") or {}, config.get("ma_window",20))
        signals, marks = rule_signals(frame, strategy, params)
    selected = frame.loc[mask].reset_index(drop=True)
    first, last = selected.date.iloc[0], selected.date.iloc[-1]
    marks = [dict(m, x0=max(m["x0"], first)) if m["kind"] == "line" else m for m in marks
             if first <= (m["x1"] if m["kind"] == "line" else m["date"]) <= last]
    result = simulate(selected, signals[mask], strategy, config.get("capital",1000000),
                      config.get("fee",.00015),config.get("tax",0.),config.get("slippage",.0005))
    result.update(config=config, dataset=meta, prediction=scores, strategy_params=params, marks=marks,
        prices=selected.to_dict(orient="records"),
        code_version=hashlib.sha256((inspect.getsource(inspect.getmodule(run))+inspect.getsource(strategies)).encode()).hexdigest()[:16],
        created_at=datetime.now(timezone.utc).isoformat(), compute_seconds=time.perf_counter()-began,
        environment=dict(python=__import__("platform").python_version(), platform=__import__("platform").platform()),
        assumptions=["단일 종목 현금 매수", "종료일 종가 청산", "세금은 사용자가 입력한 고정 모형", "현재 선정 종목에 한정된 연구"])
    return result
