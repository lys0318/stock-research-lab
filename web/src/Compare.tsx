import { X } from "lucide-react";
import { pct, tone, type CompareRow } from "./api";

/** Every strategy on the same period, best return first; failed ones (e.g. too little data) last. */
export default function CompareTable({ rows, onDetail, onClose, busy }: {
  rows: CompareRow[]; onDetail: (strategy: string) => void; onClose: () => void; busy: boolean;
}) {
  const ranked = [...rows].sort((a, b) => (b.metrics?.total_return ?? -Infinity) - (a.metrics?.total_return ?? -Infinity));
  return <section className="compare" aria-label="전략 비교">
    <div className="section-row">
      <h3>전략 비교</h3>
      <button className="btn btn-ghost btn-sm" onClick={onClose} aria-label="전략 비교 닫기"><X size={15} />닫기</button>
    </div>
    <div className="table-wrap">
      <table>
        <thead><tr><th>순위</th><th>전략</th><th>수익률</th><th>최대 낙폭</th><th>매매</th><th>승률</th><th><span className="sr-only">동작</span></th></tr></thead>
        <tbody>{ranked.map((r, i) => <tr key={r.strategy} className={r.strategy === "hold" ? "baseline" : ""}>
          <td>{r.metrics ? i + 1 : "—"}</td>
          <td><strong>{r.label}</strong>{r.strategy === "hold" && <span className="badge">기준</span>}<small>{r.group}</small></td>
          {r.metrics ? <>
            <td className={tone(r.metrics.total_return)}>{pct(r.metrics.total_return)}</td>
            <td className="down">{pct(r.metrics.max_drawdown)}</td>
            <td>{r.trips}회</td>
            <td>{r.win_rate === null ? "—" : Math.round(r.win_rate * 100) + "%"}</td>
          </> : <td colSpan={4} className="wrap muted">{r.error}</td>}
          <td>{r.metrics && <button className="btn btn-secondary btn-sm" disabled={busy} onClick={() => onDetail(r.strategy)}>자세히</button>}</td>
        </tr>)}</tbody>
      </table>
    </div>
    <p className="caption">같은 기간·자금·비용에서 각 전략의 기본 설정으로 계산했습니다. '자세히'를 누르면 그 전략으로 백테스트를 실행해 차트와 매매 기록을 보여줍니다.</p>
  </section>;
}
