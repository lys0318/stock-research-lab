import { useEffect, useState } from "react";
import { ArrowUpRight, LineChart, Search } from "lucide-react";
import { api, labels, nameHints, pct, publicMode, states, tone, type Dataset, type Job, type StockHit } from "./api";

export function JobCard({ job, datasets, onOpen }: { job: Job; datasets: Dataset[]; onOpen: (job: Job) => void }) {
  const d = datasets.find((x) => x.id === job.config.dataset_id);
  const done = job.status === "completed";
  return <button className="card" onClick={() => onOpen(job)} disabled={!done} aria-label={`${d?.name ?? "종목"} ${labels[job.config.strategy]} 결과 ${done ? "열기" : states[job.status]}`}>
    <span className="card-icon"><LineChart size={18} /></span>
    <strong>{d?.name ?? "종목"} · {labels[job.config.strategy]}</strong>
    <span className="card-value">
      {done && job.metrics ? <span className={tone(job.metrics.total_return)}>{pct(job.metrics.total_return)}</span> : <span className={"badge " + job.status}>{states[job.status]}</span>}
    </span>
    <span className="card-meta"><span>{job.config.start} ~ {job.config.end}</span>{d?.synthetic && <span>가상 데이터</span>}</span>
  </button>;
}

export default function Home({ datasets, jobs, onOpenStock, onOpenJob }: {
  datasets: Dataset[]; jobs: Job[]; onOpenStock: (symbol: string) => void; onOpenJob: (job: Job) => void;
}) {
  const [q, setQ] = useState("");
  // Results are tagged with their query so a slow response never shows under a newer query.
  const [hits, setHits] = useState<{ q: string; items: StockHit[] }>({ q: "", items: [] });
  const [connected, setConnected] = useState<boolean | null>(null);
  const [active, setActive] = useState(0);
  useEffect(() => {
    if (publicMode) return;
    let alive = true;
    const timer = setTimeout(() => api<{ items: StockHit[]; connected: boolean }>("/stocks?q=" + encodeURIComponent(q))
      .then((r) => { if (alive) { setHits({ q, items: r.items }); setConnected(r.connected); setActive(0); } })
      .catch(() => alive && setHits({ q, items: [] })), q ? 200 : 0);
    return () => { alive = false; clearTimeout(timer); };
  }, [q]);
  const open = (hit: StockHit) => { nameHints.set(hit.symbol, hit.name); onOpenStock(hit.symbol); };
  const saved = Array.from(new Map(datasets.filter((d) => !d.synthetic).map((d) => [d.symbol, d])).values());
  const answered = q.trim() !== "" && hits.q === q;
  const listed = answered ? hits.items : [];
  function key(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, listed.length - 1)); }
    if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
    if (e.key === "Enter" && listed[active]) { e.preventDefault(); open(listed[active]); }
    if (e.key === "Escape") setQ("");
  }
  return <>
    {!publicMode && <section className="hero">
      <h1>어떤 종목을 분석할까요?</h1>
      <div className="search">
        <Search size={18} aria-hidden="true" />
        <input autoFocus role="combobox" aria-expanded={listed.length > 0} aria-controls="stock-results" aria-autocomplete="list"
          aria-activedescendant={listed[active] ? "hit-" + listed[active].symbol : undefined} aria-label="종목 검색"
          placeholder="종목명 또는 코드 (삼성전자, 005930)" value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={key} />
        {listed.length > 0 && <ul id="stock-results" role="listbox" className="results">
          {listed.map((h, i) => <li key={h.symbol} id={"hit-" + h.symbol} role="option" aria-selected={i === active}
            onMouseEnter={() => setActive(i)} onMouseDown={(e) => { e.preventDefault(); open(h); }}>
            <strong>{h.name}</strong><span className="muted">{h.symbol}{h.market ? " · " + h.market : ""}</span>
            <span className={"tag" + (h.dataset_id ? " saved" : "")}>{h.dataset_id ? "저장됨" : "처음 열면 수집"}</span>
          </li>)}
        </ul>}
        {answered && !listed.length && <p className="results empty-row" role="status">검색 결과가 없습니다.</p>}
      </div>
      <div className="chips center">
        {saved.map((d) => <button key={d.symbol} className="chip" onClick={() => { nameHints.set(d.symbol, d.name); onOpenStock(d.symbol); }}>{d.name}</button>)}
      </div>
      {connected !== null && <p className="caption center">{connected
        ? "토스증권 연결됨 · 코스피·코스닥 전체 종목을 검색합니다."
        : "저장된 종목만 검색합니다. 코스피·코스닥 전체 검색과 새 종목 수집에는 유효한 토스 키가 필요합니다."}</p>}
    </section>}
    {publicMode && <section className="page-title"><h1>공개된 연구 결과</h1><p className="muted">표시 권한을 확인한 실제 데이터의 완료 결과만 게시합니다.</p></section>}
    <section>
      <div className="section-row"><h2>최근 실험</h2>{jobs.length > 6 && <a href="#/history" className="link">전체 보기 <ArrowUpRight size={14} /></a>}</div>
      {jobs.length ? <div className="cards">{jobs.slice(0, 6).map((j) => <JobCard key={j.id} job={j} datasets={datasets} onOpen={onOpenJob} />)}</div>
        : <div className="empty"><LineChart size={28} /><h3>{publicMode ? "아직 공개된 결과가 없습니다" : "첫 백테스트를 실행해 보세요"}</h3>
          <p>{publicMode ? "검증된 결과가 게시되면 이곳에 나타납니다." : "위에서 종목을 검색하면 기간과 전략을 고를 수 있습니다."}</p></div>}
    </section>
  </>;
}
