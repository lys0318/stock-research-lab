import { lazy, Suspense, useEffect, useState } from "react";
import { api, pct, tone, won, type Dataset, type Forecast } from "./api";

const PriceChart = lazy(() => import("./ResearchCharts").then((m) => ({ default: m.PriceChart })));
const horizons = [5, 20, 60];
const percent = (v: number) => (v * 100).toFixed(1) + "%";
const round = (v: number) => Math.round(v * 100) + "%";
const change = (logValue: number) => pct(Math.exp(logValue) - 1);

/** Plain-language reading of today's value for each indicator. */
function describe(key: string, v: number) {
  const size = Math.abs(v * 100).toFixed(1) + "%";
  if (key === "ma20_gap" || key === "ma60_gap") return `${key === "ma20_gap" ? 20 : 60}일선보다 ${size} ${v < 0 ? "아래" : "위"}`;
  if (key === "return_1") return `어제 ${pct(v)}`;
  if (key === "return_5") return `5일간 ${pct(v)}`;
  if (key === "volume_change") return `거래량 전일 대비 ${pct(v)}`;
  return `하루 평균 ${size} 움직임`;
}

function verdict(e: Forecast["evaluation"]) {
  const price = e.mape < e.naive_mape
    ? "중앙 예측은 검증 기간에 '가격이 그대로'라는 단순 가정보다 오차가 작았습니다."
    : "중앙 예측은 검증 기간에 '가격이 그대로'라는 단순 가정보다 오차가 작지 않았습니다. 방향보다 범위를 보세요.";
  const band = e.band80_cover >= .7
    ? `80% 범위에는 실제 가격이 ${round(e.band80_cover)} 들어왔습니다.`
    : `80% 범위에 실제 가격이 ${round(e.band80_cover)}만 들어왔습니다. 추세가 강할 때는 범위를 자주 벗어나니 주의하세요.`;
  return price + " " + band;
}

/** Tiny chart: the matched window in gray, what followed in market color, a tick where "today" was. */
function Spark({ shape, split, rising, points = shape.length }: { shape: number[]; split: number; rising?: boolean; points?: number }) {
  // `points` fixes the x scale so "now" (window only) lines up with past cards (window + horizon).
  const w = 168, h = 52, lo = Math.min(...shape), hi = Math.max(...shape), span = hi - lo || 1;
  const pt = (v: number, i: number) => `${(i / (points - 1)) * w},${h - 4 - ((v - lo) / span) * (h - 8)}`;
  const past = shape.slice(0, split + 1).map(pt).join(" ");
  const next = shape.slice(split).map((v, i) => pt(v, i + split)).join(" ");
  const x = (split / (points - 1)) * w;
  return <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="spark" aria-hidden="true">
    <line x1={x} x2={x} y1={0} y2={h} className="spark-now" />
    <polyline points={past} className="spark-past" />
    {split < shape.length - 1 && <polyline points={next} className={rising ? "spark-up" : "spark-down"} />}
  </svg>;
}

export default function ForecastView({ dataset }: { dataset: Dataset }) {
  const [horizon, setHorizon] = useState(20);
  const [data, setData] = useState<Forecast | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError("");
    api<Forecast>(`/forecast?dataset_id=${dataset.id}&horizon=${horizon}`)
      .then((f) => alive && setData(f))
      .catch((e) => alive && setError((e as Error).message))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [dataset.id, horizon]);
  const target = data?.path[data.path.length - 1];
  const edge = data?.band[data.band.length - 1];
  const e = data?.evaluation;
  const total = data ? data.drivers.reduce((s, d) => s + d.contribution, data.trend) : 0;
  const widest = data ? Math.max(...data.drivers.map((d) => Math.abs(d.contribution)), Math.abs(data.trend), 1e-9) : 1;
  const rising = data ? data.analogs.filter((a) => a.change > 0).length : 0;
  const median = data?.analogs.length ? [...data.analogs].sort((a, b) => a.change - b.change)[Math.floor(data.analogs.length / 2)].change : 0;
  return <section className="forecast" aria-label="미래 가격 예측">
    <div className="forecast-head">
      <div className="segmented" role="group" aria-label="예측 기간">
        {horizons.map((h) => <button key={h} aria-pressed={horizon === h} onClick={() => setHorizon(h)}>{h}거래일</button>)}
      </div>
      {loading && <span className="muted" role="status"><span className="spinner" /> 예측 계산 중…</span>}
    </div>
    {error && <p className="notice error" role="alert">{error}</p>}
    {data && target && edge && e && <>
      <div className="summary">
        <p>{data.horizon}거래일 뒤 ({target.date}) 예상 가격 · {data.last_date} 종가 {won(data.last_close)}원 기준</p>
        <div className="summary-value"><strong>{won(target.price)}원</strong><span className={tone(target.price / data.last_close - 1)}>{pct(target.price / data.last_close - 1)}</span></div>
        <p><strong className="ink">80% 범위 {won(edge.p10)} ~ {won(edge.p90)}원</strong> · 50% 범위 {won(edge.p25)} ~ {won(edge.p75)}원</p>
      </div>
      <div className="chips">
        <span className="chip static">오를 확률 <b>{round(data.probabilities.up)}</b></span>
        <span className="chip static">10% 이상 상승 <b className="up">{round(data.probabilities.up10)}</b></span>
        <span className="chip static">10% 이상 하락 <b className="down">{round(data.probabilities.down10)}</b></span>
      </div>
      <Suspense fallback={<p role="status" className="muted">차트를 불러오는 중…</p>}>
        <PriceChart prices={data.prices} path={data.path} band={data.band}
          scenarios={data.analogs.map((a) => ({ label: `${a.start} ~ ${a.end} 이후 흐름 ${pct(a.change)}`, path: a.path, rising: a.change > 0 }))}
          label={`${dataset.name} 최근 주가, ${data.horizon}거래일 예측 범위와 비슷한 과거 차트 시나리오`} />
      </Suspense>

      <div className="panel-section">
        <div className="section-row"><h3>예측 근거</h3><span className="caption">오늘 지표가 {data.horizon}거래일 뒤 가격을 어느 쪽으로 미는지</span></div>
        <ul className="drivers">
          {data.drivers.map((d) => <li key={d.key}>
            <span><strong>{d.label}</strong><small>{describe(d.key, d.value)}</small></span>
            <span className="bar-track" aria-hidden="true"><i className={d.contribution >= 0 ? "bar up-bar" : "bar down-bar"}
              style={{ width: `${(Math.abs(d.contribution) / widest) * 50}%`, [d.contribution >= 0 ? "left" : "right"]: "50%" }} /></span>
            <span className={"driver-value " + tone(d.contribution)}>{change(d.contribution)}</span>
          </li>)}
          <li className="drivers-trend">
            <span><strong>과거 평균 추세</strong><small>지표와 무관한 평균 흐름</small></span>
            <span className="bar-track" aria-hidden="true"><i className={data.trend >= 0 ? "bar up-bar" : "bar down-bar"}
              style={{ width: `${(Math.abs(data.trend) / widest) * 50}%`, [data.trend >= 0 ? "left" : "right"]: "50%" }} /></span>
            <span className={"driver-value " + tone(data.trend)}>{change(data.trend)}</span>
          </li>
          <li className="drivers-total"><span><strong>합계 = 중앙 예측</strong></span><span /><span className={"driver-value " + tone(total)}>{change(total)}</span></li>
        </ul>
        <p className="caption">빨강은 오르는 쪽, 파랑은 내리는 쪽으로 민 지표입니다. 신호끼리 부딪치면 합계가 0에 가까워져 점선이 평평해집니다.</p>
      </div>

      {data.analogs.length > 0 && <div className="panel-section">
        <div className="section-row">
          <h3>비슷한 과거 차트</h3>
          <span className="caption">최근 {data.window}거래일 흐름과 가장 비슷했던 구간 · {data.analogs.length}번 중 {rising}번 상승, 중앙값 {pct(median)}</span>
        </div>
        <div className="analogs">
          <div className="analog now">
            <Spark shape={data.current_shape} split={data.window} points={data.window + data.horizon + 1} />
            <strong>지금</strong><small>{data.last_date}까지 {data.window}거래일</small>
          </div>
          {data.analogs.map((a) => <div className="analog" key={a.end}>
            <Spark shape={a.shape} split={data.window} rising={a.change > 0} />
            <strong className={tone(a.change)}>이후 {data.horizon}거래일 {pct(a.change)}</strong>
            <small>{a.start} ~ {a.end} · 평균 차이 {percent(a.gap)}</small>
          </div>)}
        </div>
        <p className="caption">회색은 비교한 {data.window}거래일, 색 선은 그 뒤 실제 흐름입니다. 결과가 오늘 전에 확정된 구간만 쓰며, 같은 시기가 겹치지 않도록 20거래일 이상 떨어진 구간을 골랐습니다.</p>
      </div>}

      <div className="panel-section">
        <div className="section-row"><h3>검증 결과</h3><span className="caption">{e.test_start} 이후 {e.test_rows}일을 학습에서 빼고 채점</span></div>
        <div className="metrics">
          <div><span>중앙 예측 방향 적중률</span><strong>{percent(e.hit_rate)}</strong><small>실제로 오른 비율 {percent(e.up_rate)}</small></div>
          <div><span>중앙 예측 평균 오차</span><strong>±{percent(e.mape)}</strong><small>가격 유지 가정 ±{percent(e.naive_mape)}</small></div>
          <div><span>80% 범위 적중률</span><strong className={e.band80_cover < .7 ? "down" : ""}>{percent(e.band80_cover)}</strong><small>목표 80% · 50% 범위 {percent(e.band50_cover)}</small></div>
          <div><span>시나리오 방향 적중률</span><strong>{e.analog_hit_rate === null ? "—" : percent(e.analog_hit_rate)}</strong><small>비슷한 차트 중앙값의 방향 · 5일 간격 표본</small></div>
        </div>
        <p className={"notice" + (e.band80_cover < .7 ? " error" : "")}>{verdict(e)} {data.notice}</p>
        <p className="caption">
          방법: 중앙 예측은 최근 수익률, 20·60일 이동평균과의 거리, 거래량 변화, 변동성으로 1~{data.horizon}거래일 뒤 변화를 학습한 Ridge 회귀입니다.
          {" "}범위는 최근 {data.window}거래일 변동성을 기간의 제곱근만큼 넓힌 정규분포 가정이라 급락·급등은 과소평가합니다.
          {" "}비슷한 과거 차트는 같은 종목에서 로그 가격 흐름의 차이가 가장 작은 구간입니다.
        </p>
      </div>
    </>}
  </section>;
}
