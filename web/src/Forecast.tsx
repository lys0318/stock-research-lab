import { lazy, Suspense, useEffect, useState } from "react";
import { api, pct, tone, won, type Dataset, type Forecast } from "./api";

const PriceChart = lazy(() => import("./ResearchCharts").then((m) => ({ default: m.PriceChart })));
const horizons = [5, 20, 60];
const percent = (v: number) => (v * 100).toFixed(1) + "%";

function verdict(e: Forecast["evaluation"]) {
  const price = e.mape < e.naive_mape
    ? "검증 기간에 '가격이 그대로'라는 단순 가정보다 가격 오차가 작았습니다."
    : "검증 기간에 '가격이 그대로'라는 단순 가정보다 가격 오차가 작지 않았습니다.";
  const direction = e.hit_rate > Math.max(e.up_rate, 1 - e.up_rate)
    ? "방향은 '항상 같은 방향' 가정보다 잘 맞혔습니다."
    : "방향은 '항상 같은 방향' 가정보다 잘 맞히지 못했습니다. 참고용으로만 보세요.";
  return price + " " + direction;
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
  const change = data && target ? target.price / data.last_close - 1 : 0;
  return <section className="forecast" aria-label="미래 가격 예측">
    <div className="forecast-head">
      <div className="segmented" role="group" aria-label="예측 기간">
        {horizons.map((h) => <button key={h} aria-pressed={horizon === h} onClick={() => setHorizon(h)}>{h}거래일</button>)}
      </div>
      {loading && <span className="muted" role="status"><span className="spinner" /> 예측 계산 중…</span>}
    </div>
    {error && <p className="notice error" role="alert">{error}</p>}
    {data && target && <>
      <div className="summary">
        <p>{data.horizon}거래일 뒤 ({target.date}) 예상 가격</p>
        <div className="summary-value"><strong>{won(target.price)}원</strong><span className={tone(change)}>{pct(change)}</span></div>
        <p>{data.last_date} 종가 {won(data.last_close)}원 기준</p>
      </div>
      <div className="metrics">
        <div><span>방향 적중률</span><strong>{percent(data.evaluation.hit_rate)}</strong><small>실제로 오른 비율 {percent(data.evaluation.up_rate)}</small></div>
        <div><span>평균 가격 오차</span><strong>±{percent(data.evaluation.mape)}</strong><small>가격 유지 가정 ±{percent(data.evaluation.naive_mape)}</small></div>
        <div><span>검증 기간</span><strong>{data.evaluation.test_rows}일</strong><small>{data.evaluation.test_start}부터 · 학습에서 제외</small></div>
      </div>
      <p className="notice">{verdict(data.evaluation)} {data.notice}</p>
      <Suspense fallback={<p role="status" className="muted">차트를 불러오는 중…</p>}>
        <PriceChart prices={data.prices} path={data.path} label={`${dataset.name} 최근 주가와 ${data.horizon}거래일 예측 경로`} />
      </Suspense>
      <p className="caption">
        방법: 최근 수익률, 20·60일 이동평균과의 차이, 거래량 변화, 변동성으로 1~{data.horizon}거래일 뒤 가격 변화를 한 번에 학습한 Ridge 회귀입니다.
        {" "}검증은 {data.evaluation.test_start} 이후를 학습에서 빼고 평가했으며, 점선은 전체 데이터로 다시 학습해 {data.last_date} 이후를 예측한 값입니다.
      </p>
    </>}
  </section>;
}
