import { lazy, Suspense, useState } from "react";
import { Download, LocateFixed } from "lucide-react";
import { pct, roundTrips, strategyName, tone, won, type Result } from "./api";

const PriceChart = lazy(() => import("./ResearchCharts").then((m) => ({ default: m.PriceChart })));
const EquityChart = lazy(() => import("./ResearchCharts").then((m) => ({ default: m.EquityChart })));

export default function ResultView({ result }: { result: Result }) {
  const [focus, setFocus] = useState<number | null>(null);
  const m = result.metrics, c = result.config;
  const trips = roundTrips(result.trades);
  const wins = trips.filter((t) => t.pnl > 0).length;
  const prices = result.prices || [];
  const hold = prices.length ? prices[prices.length - 1].close / prices[0].open - 1 : null;
  function download() {
    const csv = "date,equity,drawdown\n" + result.curve.map((r) => [r.date, r.equity, r.drawdown].join(",")).join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = (result.dataset.synthetic ? "SYNTHETIC-" : "") + result.id + ".csv";
    a.click();
    URL.revokeObjectURL(url);
  }
  return <section className="result" aria-label="백테스트 결과">
    <div className="summary">
      <p>{won(c.capital)}원으로 {c.start}에 시작했다면</p>
      <div className="summary-value"><strong>{won(m.final_equity)}원</strong><span className={tone(m.total_return)}>{pct(m.total_return)}</span></div>
      <p>{c.end} 기준 · {strategyName(c, result.strategy_params)}</p>
    </div>
    <div className="metrics">
      {hold !== null && <div><span>그냥 보유했다면</span><strong className={tone(hold)}>{pct(hold)}</strong><small>비용 제외</small></div>}
      <div><span>최대 낙폭</span><strong className="down">{pct(m.max_drawdown)}</strong><small>고점 대비 최대 하락</small></div>
      <div><span>매매 횟수</span><strong>{trips.length}회</strong><small>매수→매도 한 번이 1회</small></div>
      <div><span>승률</span><strong>{trips.length ? Math.round(wins / trips.length * 100) + "%" : "—"}</strong><small>수익으로 끝난 매매 비율</small></div>
    </div>
    {result.dataset.synthetic && <p className="notice">개발용 가상 데이터로 계산한 결과입니다. 실제 주식의 성과가 아닙니다.</p>}
    {Date.now() - Date.parse(result.created_at) > 30 * 86400000 && <p className="notice">30일 전에 만든 결과입니다. 최신 시세를 반영하지 않습니다.</p>}
    <Suspense fallback={<p role="status" className="muted">차트를 불러오는 중…</p>}>
      <PriceChart prices={prices} trades={result.trades} marks={result.marks} focus={focus} label={`${result.dataset.name} 주가와 매수·매도 시점`} />
      <EquityChart result={result} />
    </Suspense>
    {result.prediction && <p className="caption">AI 방향 예측 평가: 정확도 {(result.prediction.accuracy * 100).toFixed(1)}% · Brier 점수 {result.prediction.brier.toFixed(3)} (0.25보다 낮을수록 동전 던지기보다 나음) · 기준 확률 {result.prediction.threshold}</p>}
    <div className="section-row">
      <h3>매매 기록</h3>
      <button className="btn btn-secondary btn-sm" onClick={download}><Download size={15} />자산 곡선 CSV</button>
    </div>
    <div className="table-wrap">
      <table>
        <thead><tr><th>매수</th><th>매도</th><th>보유</th><th>수익률</th><th>손익</th><th><span className="sr-only">차트</span></th></tr></thead>
        <tbody>
          {trips.map((t) => <tr key={t.index}>
            <td><span className="up">▲</span> {t.buy.date}<small>{won(t.buy.price)}원 · {t.buy.shares}주</small></td>
            <td><span className="down">▼</span> {t.sell.date}<small>{won(t.sell.price)}원</small></td>
            <td>{Math.round(t.days)}일</td>
            <td className={tone(t.ret)}>{pct(t.ret)}</td>
            <td className={tone(t.pnl)}>{t.pnl > 0 ? "+" : ""}{won(t.pnl)}원</td>
            <td><button className="btn btn-ghost btn-sm" onClick={() => { setFocus(t.index); document.getElementById("price-chart")?.scrollIntoView({ behavior: "smooth", block: "start" }); }}>
              <LocateFixed size={15} />차트</button></td>
          </tr>)}
        </tbody>
      </table>
      {!trips.length && <p className="empty-row">이 기간에는 매매 신호가 없었습니다.</p>}
    </div>
    <p className="caption">체결가는 수수료·슬리피지를 반영한 모의 가격이며 실제 주문이 아닙니다. {result.dataset.adjustment} · 코드 {result.code_version} · 계산 {result.compute_seconds.toFixed(2)}초</p>
  </section>;
}
