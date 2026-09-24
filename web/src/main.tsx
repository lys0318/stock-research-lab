import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { Cloud as CloudIcon, Database, History as HistoryIcon, Search, TrendingUp } from "lucide-react";
import "@fontsource/pretendard/400.css";
import "@fontsource/pretendard/500.css";
import "@fontsource/pretendard/600.css";
import "./style.css";
import { api, publicMode, type Benchmark, type Dataset, type Job, type Result } from "./api";
import Home from "./Home";
import Workspace from "./Workspace";
import { Cloud, DataInfo, History } from "./Pages";

type Route = { page: "home" | "history" | "cloud" | "data" } | { page: "stock"; symbol: string } | { page: "run"; id: string };
function parse(hash: string): Route {
  const [page, arg] = hash.replace(/^#\/?/, "").split("/");
  if (page === "stock" && arg) return { page, symbol: arg };
  if (page === "run" && arg) return { page, id: arg };
  if (page === "history" || page === "cloud" || page === "data") return { page };
  return { page: "home" };
}
const go = (hash: string) => { location.hash = hash; };
const nav = [
  { group: "분석", items: [["home", "새 분석", Search], ["history", "실험 기록", HistoryIcon]] },
  { group: "연구", items: [["cloud", "클라우드 실험", CloudIcon], ["data", "데이터 안내", Database]] },
] as const;

function RunPage({ id, published, onChanged }: { id: string; published: Result[] | null; onChanged: () => void }) {
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (publicMode) {
      if (published) published.find((r) => r.id === id) ? setResult(published.find((r) => r.id === id)!) : setError("공개된 결과를 찾을 수 없습니다.");
      return;
    }
    api<Result>(`/runs/${id}/results`).then(setResult).catch((e) => setError((e as Error).message));
  }, [id, published]);
  if (error) return <div className="notice error" role="alert">{error}</div>;
  if (!result) return <p role="status" className="muted"><span className="spinner" /> 결과를 불러오는 중…</p>;
  return <Workspace symbol={result.dataset.symbol} initial={result} onChanged={onChanged} onBack={() => go("#/")} />;
}

function App() {
  const [route, setRoute] = useState(() => parse(location.hash));
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [reports, setReports] = useState<Benchmark[]>([]);
  const [published, setPublished] = useState<Result[] | null>(null);
  const [error, setError] = useState("");
  async function refresh() {
    try {
      if (publicMode) {
        const response = await fetch("/results/index.json");
        if (!response.ok) throw Error("공개 결과를 불러오지 못했습니다.");
        const results: Result[] = await response.json();
        setPublished(results);
        setJobs(results.map((r) => ({ id: r.id, status: "completed", config: r.config, created_at: r.created_at, metrics: r.metrics })));
        setDatasets(Array.from(new Map(results.map((r) => [r.dataset.id, r.dataset])).values()));
        const benchmarks = await fetch("/results/benchmarks.json");
        if (benchmarks.ok) setReports(await benchmarks.json());
      } else {
        const [d, j, b] = await Promise.all([api<Dataset[]>("/datasets"), api<Job[]>("/runs"), api<Benchmark[]>("/benchmarks")]);
        setDatasets(d); setJobs(j); setReports(b);
      }
      setError("");
    } catch (e) {
      setError(publicMode ? (e as Error).message : "연구 서버에 연결할 수 없습니다. 터미널에서 research-lab serve를 실행했는지 확인하세요.");
    }
  }
  useEffect(() => {
    const onHash = () => { setRoute(parse(location.hash)); window.scrollTo(0, 0); };
    addEventListener("hashchange", onHash);
    refresh();
    const timer = publicMode ? undefined : setInterval(refresh, 3000);
    return () => { removeEventListener("hashchange", onHash); clearInterval(timer); };
  }, []);
  const openJob = (job: Job) => go("#/run/" + job.id);
  const current = route.page === "stock" || route.page === "run" ? "home" : route.page;
  return <div className="app">
    <header className="topbar">
      <a href="#/" className="brand"><span className="brand-mark"><TrendingUp size={16} /></span>주식 전략 연구실</a>
      <span className="crumb" aria-hidden="true">/</span>
      <span className="crumb">{publicMode ? "공개 결과" : "로컬 연구 환경"}</span>
      <span className="topbar-note">연구용 · 실제 주문 없음</span>
    </header>
    <nav className="sidebar" aria-label="주요 메뉴">
      {nav.map(({ group, items }) => <div key={group} className="nav-group">
        <span className="nav-label">{group}</span>
        {items.map(([page, text, Icon]) => <a key={page} href={"#/" + (page === "home" ? "" : page)} className="nav-item" aria-current={current === page ? "page" : undefined}>
          <Icon size={18} />{publicMode && page === "home" ? "공개 결과" : text}</a>)}
      </div>)}
    </nav>
    <main className="panel">
      {error && <div className="notice error" role="alert">{error}</div>}
      {route.page === "home" && <Home datasets={datasets} jobs={jobs} onOpenStock={(s) => go("#/stock/" + s)} onOpenJob={openJob} />}
      {route.page === "stock" && !publicMode && <Workspace key={route.symbol} symbol={route.symbol} onChanged={refresh} onBack={() => go("#/")} />}
      {route.page === "run" && <RunPage key={route.id} id={route.id} published={published} onChanged={refresh} />}
      {route.page === "history" && <History jobs={jobs} datasets={datasets} onOpen={openJob} onChanged={refresh} onError={setError} />}
      {route.page === "cloud" && <Cloud reports={reports} />}
      {route.page === "data" && <DataInfo datasets={datasets} />}
    </main>
  </div>;
}
createRoot(document.getElementById("root")!).render(<App />);
