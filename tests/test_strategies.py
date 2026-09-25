import numpy as np
import pandas as pd
import pytest
from lab import strategies as S
from lab.data import demo, load_dataset
from lab.engine import run

@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("LAB_DATA_DIR", str(tmp_path))

def series(close, volume=None):
    close = np.asarray(close, dtype=float)
    return pd.DataFrame(dict(date=[str(d.date()) for d in pd.bdate_range("2020-01-01", periods=len(close))],
        open=close, high=close, low=close, close=close,
        volume=np.full(len(close), 1000.) if volume is None else np.asarray(volume, dtype=float)))

RULES = [key for key, s in S.STRATEGIES.items() if s["rule"]]

@pytest.mark.parametrize("key", RULES)
def test_signals_never_use_future_prices(key):
    f, _ = load_dataset(demo()["id"])
    base, _ = S.signals(f, key, {})
    changed = f.copy()
    late = changed.index >= 1500
    for col in ["open", "high", "low", "close"]: changed.loc[late, col] *= 3
    changed["volume"] = changed.volume.astype(float)
    changed.loc[late, "volume"] *= .1
    after, _ = S.signals(changed, key, {})
    assert np.array_equal(base[:1500], after[:1500])

def test_golden_cross_holds_while_short_above_long():
    close = np.r_[np.linspace(100, 60, 80), np.linspace(60, 120, 80)]
    state, _ = S.signals(series(close), "golden", {"short": 5, "long": 20})
    c = pd.Series(close)
    assert np.array_equal(state, (c.rolling(5).mean() > c.rolling(20).mean()).to_numpy())
    assert state[-1] and not state[70]

def test_rsi_enters_oversold_and_holds_until_overbought():
    close = np.r_[np.linspace(100, 130, 30), np.linspace(130, 80, 30), np.linspace(80, 140, 40)]
    state, _ = S.signals(series(close), "rsi", {})
    r = S.rsi(pd.Series(close), 14).to_numpy()
    first = int(np.argmax(state))
    assert r[first] < 30 and not state[:first].any()
    exit_ = first + int(np.argmin(state[first:]))
    assert r[exit_] > 70 and state[first:exit_].all()

def test_pump_holds_for_n_days_and_stops_out():
    close = np.r_[np.full(30, 100.), [106.], np.full(10, 106.)]
    volume = np.r_[np.full(30, 1000.), [5000.], np.full(10, 1000.)]
    state, _ = S.signals(series(close, volume), "pump", {"hold": 5})
    assert list(np.flatnonzero(state)) == list(range(30, 36))
    dropped = close.copy()
    dropped[33:] = 99.
    state, _ = S.signals(series(dropped, volume), "pump", {"hold": 5})
    assert list(np.flatnonzero(state)) == [30, 31, 32]

def test_inverse_head_and_shoulders_breakout_and_target():
    knots = [(0, 100), (10, 80), (20, 90), (30, 70), (40, 90), (50, 80), (65, 100), (90, 115)]
    close = np.interp(np.arange(91), *zip(*knots))
    state, marks = S.signals(series(close), "hns", {"pivot": 3})
    first = int(np.argmax(state))
    # Neckline is 90; the right shoulder (day 50) is only known on day 53.
    assert first >= 53 and close[first] > 90 >= close[first - 1]
    target = int(np.argmax(close >= 110))  # neckline 90 + head depth 20
    assert state[first:target].all() and not state[target:].any()
    assert {m["text"] for m in marks if m["kind"] == "point"} >= {"왼쪽 어깨", "머리", "오른쪽 어깨"}

def test_params_are_validated():
    for strategy, params in [("golden", {"short": 60, "long": 20}), ("golden", {"nope": 1}),
                             ("rsi", {"low": 1}), ("macd", {"fast": 30, "slow": 20}), ("unknown", {})]:
        with pytest.raises(ValueError):
            S.resolve(strategy, params)
    assert S.resolve("ma", {}, ma_window=33) == {"window": 33}
    assert S.resolve("golden", {"short": 10}) == {"short": 10, "long": 60}

def test_run_with_chart_strategy():
    meta = demo()
    r = run(dict(dataset_id=meta["id"], start="2024-01-01", end="2025-12-31", strategy="golden", params={"short": 10, "long": 30}))
    assert r["strategy_params"] == {"short": 10, "long": 30}
    assert r["metrics"]["trade_count"] > 0 and "marks" in r
