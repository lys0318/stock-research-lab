import { useEffect, useRef, useState } from "react";
import { ArrowLeft, ChevronDown, LineChart, ListOrdered, Play, Sparkles } from "lucide-react";
import { api, nameHints, publicMode, states, type CompareRow, type Config, type Dataset, type Job, type Result, type StrategyInfo } from "./api";
import CompareTable from "./Compare";
import ResultView from "./Result";
import ForecastView from "./Forecast";

type Preset = "1y" | "2y" | "5y" | "all" | "custom";
const presets: [Preset, string][] = [["1y", "1년"], ["2y", "2년"], ["5y", "5년"], ["all", "전체"], ["custom", "직접"]];
const groups = ["기본", "추세", "반전", "모멘텀"];
const defaults: Config = { dataset_id: "", start: "", end: "", strategy: "ma", capital: 1000000, fee: .00015, tax: 0, slippage: .0005, ma_window: 20, seed: 42 };

function period(d: Dataset, preset: Preset, c: Config) {
  if (preset === "custom") return { start: !c.start || c.start < d.start ? d.start : c.start, end: !c.end || c.end > d.end ? d.end : c.end };
  if (preset === "all") return { start: d.start, end: d.end };
  const from = new Date(d.end);
  from.setUTCFullYear(from.getUTCFullYear() - { "1y": 1, "2y": 2, "5y": 5 }[preset]);
  const start = from.toISOString().slice(0, 10);
  return { start: start < d.start ? d.start : start, end: d.end };
}
const percentInput = (v: number) => +(v * 100).toFixed(4);

export default function Workspace({ symbol, initial, onChanged, onBack }: {
  symbol: string; initial?: Result; onChanged: () => void; onBack: () => void;
}) {
  const skipPrepare = publicMode || !!initial?.dataset.synthetic;
  const [dataset, setDataset] = useState<Dataset | null>(skipPrepare ? initial?.dataset ?? null : null);
  const [preparing, setPreparing] = useState(!skipPrepare);
  const [prepareError, setPrepareError] = useState("");
  const [error, setError] = useState("");
  const [tab, setTab] = useState<"backtest" | "forecast">("backtest");
  const [preset, setPreset] = useState<Preset>(initial ? "custom" : "2y");
  const [config, setConfig] = useState<Config>(initial?.config ?? defaults);
  const [advanced, setAdvanced] = useState(false);
  const [job, setJob] = useState<Job | null>(null);
  const [result, setResult] = useState<Result | null>(initial ?? null);
  const [catalog, setCatalog] = useState<StrategyInfo[]>([]);
  const [compare, setCompare] = useState<CompareRow[] | null>(null);
  const [comparing, setComparing] = useState(false);
  const errorRef = useRef<HTMLDivElement>(null);
  const running = !!job && ["queued", "running"].includes(job.status);

  useEffect(() => {
    if (skipPrepare) return;
    let alive = true;
    api<Dataset>(`/stocks/${symbol}/prepare`, { method: "POST" })
      .then((d) => {
        if (!alive) return;
        setDataset(d);
        setConfig((c) => ({ ...c, dataset_id: d.id, ...period(d, initial ? "custom" : "2y", c) }));
        onChanged();
      })
      .catch((e) => {
        if (!alive) return;
        setPrepareError((e as Error).message);
        if (initial) setDataset(initial.dataset);
      })
      .finally(() => alive && setPreparing(false));
    return () => { alive = false; };
  }, []);

  useEffect(() => {
    if (!job || !running) return;
    const timer = setTimeout(async () => {
      try {
        const next = await api<Job>(`/runs/${job.id}`);
        if (next.status === "completed") { setResult(await api<Result>(`/runs/${job.id}/results`)); onChanged(); }
        if (next.status === "failed") { setError(next.error || "실행하지 못했습니다."); onChanged(); }
        setJob(next);
      } catch (e) { setError((e as Error).message); setJob(null); }
    }, 1000);
    return () => clearTimeout(timer);
  }, [job]);

  useEffect(() => { if (error) errorRef.current?.focus(); }, [error]);
  useEffect(() => { if (!publicMode) api<StrategyInfo[]>("/strategies").then(setCatalog).catch((e) => setError((e as Error).message)); }, []);

  function choose(p: Preset) {
    setPreset(p);
    if (dataset) setConfig((c) => ({ ...c, ...period(dataset, p, c) }));
  }
  async function start(cfg: Config) {
    setError("");
    try {
      setJob(await api<Job>("/runs", { method: "POST", body: JSON.stringify(cfg) }));
      onChanged();
    } catch (err) { setError((err as Error).message); }
  }
  async function compareAll() {
    setError("");
    setComparing(true);
    try {
      const { dataset_id, start: from, end, capital, fee, tax, slippage } = config;
      setCompare(await api<CompareRow[]>("/compare", { method: "POST", body: JSON.stringify({ dataset_id, start: from, end, capital, fee, tax, slippage }) }));
    } catch (err) { setError((err as Error).message); }
    finally { setComparing(false); }
  }
  function detail(strategy: string) {
    const cfg = { ...config, strategy, params: {} };
    setConfig(cfg);
    void start(cfg);
  }
  async function cancel() {
    if (!job) return;
    try { setJob(await api<Job>(`/runs/${job.id}/cancel`, { method: "POST" })); onChanged(); }
    catch (err) { setError((err as Error).message); }
  }
  const selected = catalog.find((s) => s.key === config.strategy);
  const name = dataset?.name ?? initial?.dataset.name ?? nameHints.get(symbol) ?? symbol;
  const field = (key: "fee" | "tax" | "slippage", label: string, hint: string) => <label>
    {label}
    <span className="input-unit"><input type="number" min={0} max={5} step={0.001} required value={percentInput(config[key])}
      onChange={(e) => setConfig({ ...config, [key]: Number(e.target.value) / 100 })} /><span>%</span></span>
    <small>{hint}</small>
  </label>;

  return <>
    {!publicMode && <button className="btn btn-ghost btn-sm back" onClick={onBack}><ArrowLeft size={16} />종목 검색</button>}
    <header className="stock-head">
      <div>
        <h1>{name}</h1>
        <p className="muted">
          {symbol}
          {dataset && <> · {dataset.start} ~ {dataset.end} · {dataset.rows.toLocaleString()}거래일{dataset.synthetic ? " · 개발용 가상 데이터" : ""}</>}
        </p>
      </div>
    </header>
    {preparing && <div className="notice" role="status"><span className="spinner" /> 일봉 데이터를 준비하고 있습니다. 처음 여는 종목은 토스에서 받느라 5초 정도 걸립니다.</div>}
    {prepareError && <div className="notice error" role="alert">{prepareError}</div>}
    {publicMode && result && <ResultView result={result} />}
    {!publicMode && dataset && <>
      <div className="tabs" role="tablist" aria-label="분석 종류">
        <button role="tab" aria-selected={tab === "backtest"} onClick={() => setTab("backtest")}><LineChart size={16} />과거 백테스트</button>
        <button role="tab" aria-selected={tab === "forecast"} onClick={() => setTab("forecast")}><Sparkles size={16} />미래 예측</button>
      </div>
      {tab === "forecast" ? <ForecastView dataset={dataset} /> : <div className="workspace">
        <form className="settings" onSubmit={(e) => { e.preventDefault(); void start(config); }}>
          <fieldset>
            <legend>기간</legend>
            <div className="chips">{presets.map(([p, text]) => <button type="button" key={p} className="chip" aria-pressed={preset === p} onClick={() => choose(p)}>{text}</button>)}</div>
            <div className="date-pair">
              <label><span className="sr-only">시작일</span><input type="date" required min={dataset.start} max={config.end} value={config.start}
                onChange={(e) => { setPreset("custom"); setConfig({ ...config, start: e.target.value }); }} /></label>
              <span aria-hidden="true">~</span>
              <label><span className="sr-only">종료일</span><input type="date" required min={config.start} max={dataset.end} value={config.end}
                onChange={(e) => { setPreset("custom"); setConfig({ ...config, end: e.target.value }); }} /></label>
            </div>
          </fieldset>
          <fieldset>
            <legend>전략</legend>
            <label><span className="sr-only">전략 선택</span>
              <select value={config.strategy} onChange={(e) => setConfig({ ...config, strategy: e.target.value, params: {} })}>
                {groups.map((g) => <optgroup key={g} label={g}>
                  {catalog.filter((s) => s.group === g).map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
                </optgroup>)}
              </select>
            </label>
            {selected && <p className="strategy-note">{selected.description}</p>}
            {selected?.params.map((p) => <label key={p.key}>{p.label}
              <input type="number" min={p.min} max={p.max} step={p.step} required
                value={config.params?.[p.key] ?? (config.strategy === "ma" && p.key === "window" ? config.ma_window : p.default)}
                onChange={(e) => setConfig({ ...config, params: { ...config.params, [p.key]: Number(e.target.value) } })} />
            </label>)}
          </fieldset>
          <label>시작 자금
            <span className="input-unit"><input type="number" min={1000} max={1e10} step={1000} required value={config.capital}
              onChange={(e) => setConfig({ ...config, capital: Number(e.target.value) })} /><span>원</span></span>
          </label>
          <button type="button" className="disclosure" aria-expanded={advanced} onClick={() => setAdvanced(!advanced)}>
            고급 설정 <ChevronDown size={16} />
          </button>
          {advanced && <div className="advanced">
            {field("fee", "거래 수수료", "매수·매도 때마다 체결 금액에 부과")}
            {field("tax", "매도 세금 가정", "실제 세율이 아닌 실험 입력값")}
            {field("slippage", "슬리피지", "매수는 비싸게, 매도는 싸게 체결된다고 가정")}
          </div>}
          {running
            ? <div className="run-row"><button type="button" className="btn btn-primary" disabled><span className="spinner light" />{states[job!.status]}…</button>
              <button type="button" className="btn btn-secondary" onClick={cancel}>취소</button></div>
            : <button type="submit" className="btn btn-primary"><Play size={16} />백테스트 실행</button>}
          <button type="button" className="btn btn-secondary" onClick={compareAll} disabled={comparing || running}>
            {comparing ? <><span className="spinner" />모든 전략 계산 중…</> : <><ListOrdered size={16} />모든 전략 비교</>}
          </button>
          <p className="caption">실제 주문 없이 과거 일봉으로 모의 매매합니다. 신호는 다음 거래일 시가에 체결합니다.</p>
        </form>
        <div className="output">
          {error && <div ref={errorRef} tabIndex={-1} className="notice error" role="alert">{error}</div>}
          {compare && <CompareTable rows={compare} busy={running} onDetail={detail} onClose={() => setCompare(null)} />}
          {running && <div className="notice" role="status"><span className="spinner" /> 계산 중입니다. 끝나면 결과가 여기에 바로 나타납니다.</div>}
          {result ? <ResultView key={result.id} result={result} /> : !running && <div className="empty">
            <LineChart size={28} />
            <h3>전략을 골라 실행해 보세요</h3>
            <p>얼마를 벌었는지, 언제 사고팔았는지 차트와 매매 기록으로 보여줍니다.</p>
          </div>}
        </div>
      </div>}
    </>}
  </>;
}
