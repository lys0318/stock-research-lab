import { X } from "lucide-react";
import { pct, tone, type Metrics } from "./api";

export type RankRow = {
  id: string; name: string; sub?: string; baseline?: boolean;
  metrics: Metrics | null; trips: number; win_rate: number | null; error: string | null;
};

/** Ranked backtests (strategy comparison or parameter grid), best return first; failed runs last. */
export default function RankTable({ title, rows, caption, onDetail, onClose, busy }: {
  title: string; rows: RankRow[]; caption: string; onDetail: (id: string) => void; onClose: () => void; busy: boolean;
}) {
  const ranked = [...rows].sort((a, b) => (b.metrics?.total_return ?? -Infinity) - (a.metrics?.total_return ?? -Infinity));
  return <section className="compare" aria-label={title}>
    <div className="section-row">
      <h3>{title}</h3>
      <button className="btn btn-ghost btn-sm" onClick={onClose} aria-label={`${title} 닫기`}><X size={15} />닫기</button>
    </div>
    <div className="table-wrap">
      <table>
        <thead><tr><th>순위</th><th>전략·설정</th><th>수익률</th><th>연평균</th><th>최대 낙폭</th><th>샤프</th><th>매매</th><th>승률</th><th><span className="sr-only">동작</span></th></tr></thead>
        <tbody>{ranked.map((r, i) => <tr key={r.id} className={r.baseline ? "baseline" : ""}>
          <td>{r.metrics ? i + 1 : "—"}</td>
          <td><strong>{r.name}</strong>{r.baseline && <span className="badge">기준</span>}{r.sub && <small>{r.sub}</small>}</td>
          {r.metrics ? <>
            <td className={tone(r.metrics.total_return)}>{pct(r.metrics.total_return)}</td>
            <td className={tone(r.metrics.cagr ?? 0)}>{r.metrics.cagr === undefined ? "—" : pct(r.metrics.cagr)}</td>
            <td className="down">{pct(r.metrics.max_drawdown)}</td>
            <td>{r.metrics.sharpe === undefined ? "—" : r.metrics.sharpe.toFixed(2)}</td>
            <td>{r.trips}회</td>
            <td>{r.win_rate === null ? "—" : Math.round(r.win_rate * 100) + "%"}</td>
          </> : <td colSpan={6} className="wrap muted">{r.error}</td>}
          <td>{r.metrics && <button className="btn btn-secondary btn-sm" disabled={busy} onClick={() => onDetail(r.id)}>자세히</button>}</td>
        </tr>)}</tbody>
      </table>
    </div>
    <p className="caption">{caption}</p>
  </section>;
}
