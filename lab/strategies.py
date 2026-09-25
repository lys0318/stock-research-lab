"""Chart-technique strategies as hold-state series.

A rule sees data up to the close of day t and answers "hold after day t?". The simulator fills any
change at the next day's open, so no rule can act on information it wouldn't have had.
"""
import numpy as np
import pandas as pd

def P(default, low, high, label, step=1):
    return dict(default=default, min=low, max=high, label=label, step=step)

def sma(c, n): return c.rolling(n).mean()

def ema(c, n): return c.ewm(span=n, adjust=False).mean()

def rsi(c, n):
    """Wilder's RSI."""
    delta = c.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    with np.errstate(divide="ignore", invalid="ignore"):
        return 100 - 100/(1 + gain/loss)

def latch(enter, leave):
    """Hold from an `enter` day until the next `leave` day."""
    state, holding = np.zeros(len(enter), dtype=bool), False
    for i, (e, l) in enumerate(zip(np.asarray(enter, dtype=bool), np.asarray(leave, dtype=bool))):
        holding = (not l) if holding else bool(e)
        state[i] = holding
    return state

def ma(f, window): return (f.close > sma(f.close, window)).to_numpy()

def golden(f, short, long):
    return (sma(f.close, short) > sma(f.close, long)).to_numpy()

def aligned(f):
    m = [sma(f.close, n) for n in (5, 20, 60, 120)]
    return ((m[0] > m[1]) & (m[1] > m[2]) & (m[2] > m[3])).to_numpy()

def macd(f, fast, slow, signal):
    line = ema(f.close, fast) - ema(f.close, slow)
    return (line > ema(line, signal)).to_numpy()

def breakout(f, entry, exit):
    return latch(f.close > f.high.rolling(entry).max().shift(1), f.close < f.low.rolling(exit).min().shift(1))

def rsi_rule(f, period, low, high):
    r = rsi(f.close, period)
    return latch(r < low, r > high)

def bollinger(f, window, width):
    mid, sd = sma(f.close, window), f.close.rolling(window).std()
    return latch(f.close < mid - width*sd, f.close > mid)

def pump(f, volume, surge, hold, stop):
    c = f.close.to_numpy()
    event = ((f.volume >= volume*f.volume.rolling(20).mean().shift(1)) & (f.close.pct_change() >= surge/100)).to_numpy()
    state, start = np.zeros(len(c), dtype=bool), None
    for t in range(len(c)):
        if start is not None and (t - start > hold or c[t] <= c[start]*(1 - stop/100)):
            start = None
        if start is None and event[t]:
            start = t  # reference = signal-day close; the real fill is the next open
        state[t] = start is not None
    return state

def pivots(values, k, highest):
    """(confirmed_on, index, value) of strict extrema over ±k days. Known only k days later."""
    out = []
    for i in range(k, len(values) - k):
        window = values[i-k:i+k+1]
        target = window.max() if highest else window.min()
        if values[i] == target and np.count_nonzero(window == target) == 1:
            out.append((i + k, i, float(values[i])))
    return out

def formations(extremes, others, tolerance, bottom):
    """Head-and-shoulders built from three consecutive extremes, neckline from the swings between them."""
    found = []
    for a, b, c in zip(extremes, extremes[1:], extremes[2:]):
        head = b[2] < min(a[2], c[2]) if bottom else b[2] > max(a[2], c[2])
        if not head or abs(a[2] - c[2])/max(a[2], c[2]) > tolerance: continue
        left = [p for p in others if a[1] < p[1] < b[1]]
        right = [p for p in others if b[1] < p[1] < c[1]]
        if not left or not right: continue
        pick = max if bottom else min
        n1, n2 = pick(left, key=lambda p: p[2]), pick(right, key=lambda p: p[2])
        found.append(dict(at=max(c[0], n1[0], n2[0]), shoulders=(a, c), head=b, neck=(n1, n2)))
    return sorted(found, key=lambda p: p["at"])

def neck(p, t):
    (_, i1, v1), (_, i2, v2) = p["neck"]
    return v1 + (v2 - v1)*(t - i1)/(i2 - i1)

def hns(f, pivot, tolerance, max_hold):
    c, dates = f.close.to_numpy(), f.date.astype(str).to_numpy()
    troughs, peaks = pivots(f.low.to_numpy(), pivot, False), pivots(f.high.to_numpy(), pivot, True)
    bottoms = formations(troughs, peaks, tolerance/100, True)
    tops = formations(peaks, troughs, tolerance/100, False)
    state, marks = np.zeros(len(c), dtype=bool), []
    armed, warnings, position = [], [], None
    def draw(p, t, names):
        (_, i1, v1), _ = p["neck"]
        for (_, i, v), text in zip([p["shoulders"][0], p["head"], p["shoulders"][1]], names):
            marks.append(dict(kind="point", date=dates[i], price=v, text=text))
        marks.append(dict(kind="line", x0=dates[i1], y0=v1, x1=dates[t], y1=neck(p, t), text="넥라인"))
    for t in range(len(c)):
        armed += [p for p in bottoms if p["at"] == t]
        warnings += [p for p in tops if p["at"] == t]
        # A bottom is void once price breaks the right shoulder's low; a top once it clears the right shoulder's high.
        armed = [p for p in armed if c[t] >= p["shoulders"][1][2] and t - p["at"] <= max_hold]
        warnings = [p for p in warnings if c[t] <= p["shoulders"][1][2] and t - p["at"] <= max_hold]
        if position:
            broken = [p for p in warnings if c[t] < neck(p, t)]
            if c[t] >= position["target"] or c[t] < position["stop"] or t - position["t"] >= max_hold or broken:
                for p in broken: draw(p, t, ["천장 왼쪽 어깨", "천장 머리", "천장 오른쪽 어깨"])
                warnings = [p for p in warnings if p not in broken]
                position = None
        else:
            crossed = [p for p in armed if c[t] > neck(p, t)]
            if crossed:
                p = crossed[-1]
                depth = neck(p, p["head"][1]) - p["head"][2]
                position = dict(t=t, target=neck(p, t) + depth, stop=p["shoulders"][1][2])
                draw(p, t, ["왼쪽 어깨", "머리", "오른쪽 어깨"])
                armed = []
        state[t] = position is not None
    return state, marks

STRATEGIES = {
    "hold": dict(label="매수 후 보유", group="기본", rule=None, params={},
                 description="첫날 시가에 사서 마지막 날 종가에 팝니다. 다른 전략의 비교 기준입니다."),
    "ma": dict(label="이동평균 전략", group="기본", rule=ma, params=dict(window=P(20, 2, 250, "이동평균 기간(일)")),
               description="종가가 이동평균선 위면 보유, 아래로 내려가면 다음 날 시가에 팝니다."),
    "model": dict(label="AI 방향 예측", group="기본", rule=None, params={},
                  description="5일 뒤 오를 확률이 높을 때만 사서 5일 보유합니다. 시작일 전 2년 데이터가 필요합니다."),
    "golden": dict(label="골든크로스", group="추세", rule=golden,
                   params=dict(short=P(20, 2, 120, "단기선(일)"), long=P(60, 5, 250, "장기선(일)")),
                   description="단기선이 장기선을 뚫고 올라가면(골든크로스) 사고, 다시 내려가면(데드크로스) 팝니다."),
    "aligned": dict(label="이동평균 정배열", group="추세", rule=aligned, params={},
                    description="5 > 20 > 60 > 120일선 정배열일 때만 보유하고, 배열이 깨지면 팝니다. 역배열 구간은 피합니다."),
    "macd": dict(label="MACD", group="추세", rule=macd,
                 params=dict(fast=P(12, 2, 50, "빠른 선(일)"), slow=P(26, 5, 100, "느린 선(일)"), signal=P(9, 2, 50, "시그널(일)")),
                 description="MACD선이 시그널선 위에 있으면 보유, 아래로 내려가면 팝니다."),
    "breakout": dict(label="신고가 돌파", group="추세", rule=breakout,
                     params=dict(entry=P(20, 5, 250, "돌파 기준(일)"), exit=P(10, 2, 120, "이탈 기준(일)")),
                     description="종가가 최근 N일 최고가를 넘으면 사고, 최근 M일 최저가 아래로 내려가면 팝니다."),
    "rsi": dict(label="RSI 과매도·과매수", group="반전", rule=rsi_rule,
                params=dict(period=P(14, 2, 50, "RSI 기간(일)"), low=P(30, 5, 50, "과매도 기준"), high=P(70, 50, 95, "과매수 기준")),
                description="RSI가 과매도 기준 아래로 내려가면 사고, 과매수 기준을 넘으면 팝니다."),
    "bollinger": dict(label="볼린저 밴드", group="반전", rule=bollinger,
                      params=dict(window=P(20, 5, 120, "기간(일)"), width=P(2, 1, 4, "밴드 폭(표준편차)", .5)),
                      description="종가가 하단 밴드 아래로 내려가면 사고, 중심선을 회복하면 팝니다."),
    "hns": dict(label="헤드 앤 숄더", group="반전", rule=hns,
                params=dict(pivot=P(5, 2, 20, "꼭짓점 확인(일)"), tolerance=P(10, 2, 30, "양 어깨 높이 차이(%)"),
                            max_hold=P(60, 5, 250, "최대 보유(일)")),
                description="역헤드앤숄더(바닥 반전)의 넥라인을 돌파하면 사고, 목표가·오른쪽 어깨 이탈·천장 헤드앤숄더 넥라인 붕괴·최대 보유일 중 먼저 오면 팝니다."),
    "pump": dict(label="펌핑 시그널", group="모멘텀", rule=pump,
                 params=dict(volume=P(3, 1.5, 20, "거래량 배수(직전 20일 평균 대비)", .5), surge=P(5, 1, 30, "하루 상승률(%)"),
                             hold=P(5, 1, 60, "보유(거래일)"), stop=P(5, 1, 50, "손절(%)")),
                 description="거래량이 급증하면서 급등한 날 다음 날 사서 정해진 기간 보유하고, 손절선 아래로 내려가면 팝니다."),
}
ORDER = dict(golden=("short", "long"), macd=("fast", "slow"), rsi=("low", "high"))

def resolve(strategy, params, ma_window=20):
    """Defaults filled in, unknown keys and out-of-range values rejected."""
    if strategy not in STRATEGIES: raise ValueError(f"알 수 없는 전략입니다: {strategy}")
    spec = STRATEGIES[strategy]["params"]
    unknown = set(params) - set(spec)
    if unknown: raise ValueError(f"{STRATEGIES[strategy]['label']}에 없는 설정입니다: {', '.join(sorted(unknown))}")
    out = {k: p["default"] for k, p in spec.items()}
    if strategy == "ma": out["window"] = ma_window  # results saved before params existed
    out.update(params)
    for k, v in out.items():
        if not spec[k]["min"] <= v <= spec[k]["max"]:
            raise ValueError(f"{spec[k]['label']}은 {spec[k]['min']}~{spec[k]['max']} 사이여야 합니다.")
        if spec[k]["step"] == 1: out[k] = int(v)
    if strategy in ORDER and out[ORDER[strategy][0]] >= out[ORDER[strategy][1]]:
        a, b = ORDER[strategy]
        raise ValueError(f"{spec[a]['label']}은 {spec[b]['label']}보다 작아야 합니다.")
    return out

def signals(frame, strategy, params, ma_window=20):
    """(hold state per day, chart marks) for a rule-based strategy."""
    result = STRATEGIES[strategy]["rule"](frame, **resolve(strategy, params, ma_window))
    return result if isinstance(result, tuple) else (result, [])

def catalog():
    return [dict(key=k, label=s["label"], group=s["group"], description=s["description"],
                 params=[dict(key=pk, **p) for pk, p in s["params"].items()]) for k, s in STRATEGIES.items()]
