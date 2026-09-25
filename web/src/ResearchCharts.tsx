import { useEffect, useMemo, useRef, useState } from "react";
import Plotly from "plotly.js-finance-dist-min";
import type { Annotations, Data, Layout, PlotlyHTMLElement, RangeSlider, Shape } from "plotly.js";
import type { Band, Mark, Point, Price, Result, Trade } from "./api";

const up = "#e5383b", down = "#2563eb", ink = "#0d0d0d", grid = "#efefef";
const maColors: Record<number, string> = { 5: "#f59f00", 20: "#12b886", 60: "#7048e8", 120: "#868e96" };
const money = (n: number) => n.toLocaleString("ko-KR", { maximumFractionDigits: 0 });
const base: Partial<Layout> = {
  autosize: true, paper_bgcolor: "transparent", plot_bgcolor: "transparent",
  font: { family: "Pretendard, sans-serif", color: "#5d5d5d", size: 12 },
  margin: { l: 60, r: 12, t: 56, b: 32 },
  legend: { orientation: "h", x: 0, y: 1.1, font: { size: 11 } },
  hovermode: "closest", dragmode: "pan",
  hoverlabel: { bgcolor: "#ffffff", bordercolor: "#e8e8e8", font: { color: ink, family: "Pretendard, sans-serif" } },
  modebar: { bgcolor: "transparent", color: "#8f8f8f", activecolor: ink },
};
type AutoY = (inside: (date: string) => boolean) => [number, number] | null;

function Plot({ traces, layout, label, autoY }: { traces: Data[]; layout: Partial<Layout>; label: string; autoY?: AutoY }) {
  const ref = useRef<HTMLDivElement>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    let active = true, ready = false;
    let graph: PlotlyHTMLElement | undefined;
    setError("");
    Plotly.react(el, traces, { ...base, ...layout }, {
      responsive: true, displayModeBar: true, displaylogo: false, scrollZoom: true,
      modeBarButtonsToRemove: ["select2d", "lasso2d"],
      toImageButtonOptions: { format: "png", filename: "stock-research-chart", scale: 2, width: 1280, height: 650 },
    }).then((rendered) => {
      if (!active) return;
      graph = rendered; ready = true; Plotly.Plots.resize(el);
      if (autoY) rendered.on("plotly_relayout", (event) => {
        // Refit the price axis to whatever dates are visible after a zoom or range button.
        if (!Object.keys(event).some((k) => k.startsWith("xaxis.range") || k === "xaxis.autorange")) return;
        if (Object.keys(event).some((k) => k.startsWith("yaxis.range"))) return;
        const range = rendered.layout.xaxis?.range;
        const from = range ? new Date(range[0]).getTime() : -Infinity, to = range ? new Date(range[1]).getTime() : Infinity;
        const fit = autoY((d) => { const t = new Date(d).getTime(); return t >= from && t <= to; });
        if (fit) void Plotly.relayout(rendered, { "yaxis.range": fit, "yaxis.autorange": false });
      });
    }).catch(() => { if (active) setError("차트를 불러오지 못했습니다. 화면을 새로고침해 주세요."); });
    const observer = new ResizeObserver(() => { if (ready && el.isConnected) Plotly.Plots.resize(el); });
    observer.observe(el);
    return () => { active = false; observer.disconnect(); graph?.removeAllListeners("plotly_relayout"); };
  }, [traces, layout, autoY]);
  useEffect(() => { const el = ref.current; return () => { if (el) Plotly.purge(el); }; }, []);
  return <>{error && <p role="alert" className="notice error">{error}</p>}<div className="plot-canvas" style={{ height: layout.height || 320 }} ref={ref} aria-label={label} role="img" /></>;
}

function movingAverage(values: number[], n: number) {
  let sum = 0;
  return values.map((v, i) => { sum += v - (i >= n ? values[i - n] : 0); return i >= n - 1 ? sum / n : null; });
}
/** Weekdays absent from the (sorted) series — KRX holidays, since the data and forecast path only hold trading days. */
function closedWeekdays(dates: string[]) {
  const have = new Set(dates), out: string[] = [], d = new Date(dates[0]), last = dates[dates.length - 1];
  for (let s = dates[0]; s < last;) {
    d.setUTCDate(d.getUTCDate() + 1);
    s = d.toISOString().slice(0, 10);
    if (d.getUTCDay() % 6 && !have.has(s)) out.push(s);
  }
  return out;
}
const shift = (date: string, days: number) => { const d = new Date(date); d.setUTCDate(d.getUTCDate() + days); return d.toISOString().slice(0, 10); };

type Kind = "candlestick" | "ohlc" | "line" | "area";
const kinds: [Kind, string][] = [["candlestick", "캔들"], ["ohlc", "OHLC 막대"], ["line", "선"], ["area", "영역"]];

export type Scenario = { label: string; path: Point[]; rising: boolean };

export function PriceChart({ prices, trades = [], path, band, scenarios, marks, focus = null, label }: {
  prices: Price[]; trades?: Trade[]; path?: Point[]; band?: Band[]; scenarios?: Scenario[]; marks?: Mark[]; focus?: number | null; label: string;
}) {
  const [kind, setKind] = useState<Kind>("candlestick");
  const [mas, setMas] = useState<number[]>([20, 60]);
  const [showBand, setShowBand] = useState(true);
  const [showScenarios, setShowScenarios] = useState(true);
  const bands = showBand ? band : undefined, lines = showScenarios ? scenarios : undefined;
  const selected = focus === null ? null : trades[focus];
  const { traces, layout, autoY } = useMemo(() => {
    const dates = prices.map((p) => p.date);
    const closes = prices.map((p) => p.close);
    const last = prices[prices.length - 1];
    const end = path?.length ? path[path.length - 1].date : dates[dates.length - 1];
    const traces: Data[] = [];
    const hover = prices.map((p) => `${p.date}<br>시가 ${money(p.open)}원<br>고가 ${money(p.high)}원<br>저가 ${money(p.low)}원<br>종가 ${money(p.close)}원`);
    if (kind === "candlestick" || kind === "ohlc") traces.push({
      type: kind, x: dates, open: prices.map((p) => p.open), high: prices.map((p) => p.high), low: prices.map((p) => p.low), close: closes,
      increasing: { line: { color: up } }, decreasing: { line: { color: down } }, name: "일봉", showlegend: false, text: hover, hoverinfo: "text",
    } as Data);
    else traces.push({
      type: "scatter", mode: "lines", x: dates, y: closes, name: "종가", showlegend: false, line: { color: ink, width: 1.6 },
      fill: kind === "area" ? "tozeroy" : undefined, fillcolor: "rgba(13,13,13,.06)", text: hover, hoverinfo: "text",
    });
    for (const n of mas) traces.push({
      type: "scatter", mode: "lines", x: dates, y: movingAverage(closes, n), name: `${n}일 이동평균`,
      line: { color: maColors[n], width: 1.2 }, hovertemplate: `%{x}<br>${n}일 평균 %{y:,.0f}원<extra></extra>`,
    });
    traces.push({
      type: "bar", x: dates, y: prices.map((p) => p.volume), yaxis: "y2", name: "거래량", showlegend: false,
      marker: { color: prices.map((p) => p.close >= p.open ? "rgba(229,56,59,.35)" : "rgba(37,99,235,.3)") },
      hovertemplate: "%{x}<br>거래량 %{y:,.0f}주<extra></extra>",
    });
    for (const side of ["buy", "sell"]) {
      const list = trades.filter((t) => t.side === side);
      if (!list.length) continue;
      const name = side === "buy" ? "매수" : "매도";
      traces.push({
        type: "scatter", mode: "markers", name, x: list.map((t) => t.date), y: list.map((t) => t.price),
        marker: { symbol: side === "buy" ? "triangle-up" : "triangle-down", size: 12, color: side === "buy" ? up : down, line: { color: "white", width: 1 } },
        text: list.map((t) => `${name} · ${t.date}<br>${t.phase === "close" ? "종가" : "시가"} 기준 모의 체결<br>체결가 ${money(t.price)}원 · ${t.shares}주<br>거래금액 ${money(t.price * t.shares)}원 · 비용 ${money(t.costs)}원`),
        hovertemplate: "%{text}<extra></extra>",
      });
    }
    if (selected) traces.push({ type: "scatter", mode: "markers", x: [selected.date], y: [selected.price], name: "선택한 거래", showlegend: false,
      marker: { symbol: "circle-open", size: 24, color: ink, line: { width: 2 } }, hoverinfo: "skip" });
    const shapes: Partial<Shape>[] = [];
    const annotations: Partial<Annotations>[] = [];
    for (const m of marks || []) {
      if (m.kind === "line") shapes.push({ type: "line", xref: "x", yref: "y", x0: m.x0, y0: m.y0, x1: m.x1, y1: m.y1, line: { color: "#5d5d5d", width: 1.5, dash: "dash" } });
      else annotations.push({ x: m.date, y: m.price, text: m.text, showarrow: true, arrowhead: 0, arrowcolor: "#8f8f8f", ax: 0,
        ay: m.text.startsWith("천장") ? -28 : 28, font: { size: 11, color: ink }, bgcolor: "rgba(255,255,255,.9)", borderpad: 2 });
    }
    if (bands?.length && last) {
      // Each range is an upper edge followed by a lower edge filled back to it ("tonexty"), starting at today's close.
      const x = [last.date, ...bands.map((b) => b.date)];
      const edge = (key: "p10" | "p25" | "p75" | "p90") => [last.close, ...bands.map((b) => b[key])];
      for (const [hi, lo, fill, name] of [["p90", "p10", "rgba(13,13,13,.07)", "80%"], ["p75", "p25", "rgba(13,13,13,.13)", "50%"]] as const) {
        traces.push({ type: "scatter", mode: "lines", x, y: edge(hi), line: { width: 0 }, hoverinfo: "skip", showlegend: false });
        traces.push({ type: "scatter", mode: "lines", x, y: edge(lo), line: { width: 0 }, fill: "tonexty", fillcolor: fill, showlegend: false,
          text: [`현재 ${money(last.close)}원`, ...bands.map((b) => `${name} 범위 ${money(b[lo])} ~ ${money(b[hi])}원`)], hovertemplate: "%{x}<br>%{text}<extra></extra>" });
      }
    }
    for (const s of (last && lines) || []) traces.push({
      type: "scatter", mode: "lines", name: s.label, x: [last.date, ...s.path.map((p) => p.date)], y: [last.close, ...s.path.map((p) => p.price)],
      line: { color: s.rising ? "rgba(229,56,59,.55)" : "rgba(37,99,235,.55)", width: 1.2 },
      hovertemplate: `${s.label}<br>%{x} %{y:,.0f}원<extra></extra>`,
    });
    if (path?.length && last) {
      const target = path[path.length - 1];
      traces.push({
        type: "scatter", mode: "lines", name: "예측 경로", x: [last.date, ...path.map((p) => p.date)], y: [last.close, ...path.map((p) => p.price)],
        line: { color: ink, width: 2, dash: "dot" }, hovertemplate: "%{x}<br>예측 %{y:,.0f}원<extra></extra>",
      });
      shapes.push({ type: "rect", xref: "x", yref: "paper", x0: last.date, x1: target.date, y0: .28, y1: 1, fillcolor: "rgba(13,13,13,.04)", line: { width: 0 }, layer: "below" });
      annotations.push({ x: target.date, y: target.price, text: `예상 ${money(target.price)}원`, showarrow: true, arrowhead: 0, ax: -8, ay: -30, xanchor: "right",
        font: { color: ink, size: 12 }, bgcolor: "#ffffff", bordercolor: "#e8e8e8", borderpad: 4 });
    }
    const autoY: AutoY = (inside) => {
      const values = [...prices.filter((p) => inside(p.date)).flatMap((p) => [p.low, p.high]),
        ...trades.filter((t) => inside(t.date)).map((t) => t.price), ...(path || []).filter((p) => inside(p.date)).map((p) => p.price),
        ...(bands || []).filter((b) => inside(b.date)).flatMap((b) => [b.p10, b.p90]),
        ...(lines || []).flatMap((s) => s.path.filter((p) => inside(p.date)).map((p) => p.price))];
      if (!values.length) return null;
      const low = Math.min(...values), high = Math.max(...values), pad = Math.max((high - low) * .12, high * .005);
      return [low - pad, high + pad];
    };
    const range = selected
      ? [shift(selected.date, -20) < dates[0] ? dates[0] : shift(selected.date, -20), shift(selected.date, 20) > end ? end : shift(selected.date, 20)]
      : [dates[Math.max(0, dates.length - (path?.length ? 80 : 130))], end];  // forecasts: tighter so the future part is readable
    const layout: Partial<Layout> = {
      // The MA toggles double as the legend; an in-chart legend collides with the range buttons on phones.
      height: 520, shapes, annotations, showlegend: false, margin: { l: 60, r: 12, t: 40, b: 32 },
      uirevision: `${label}:${prices.length}:${focus ?? "init"}:${path?.length ?? 0}`,
      xaxis: {
        type: "date", showgrid: false, range, anchor: "y2",
        tickformatstops: [{ dtickrange: [null, "M1"], value: "%m-%d" }, { dtickrange: ["M1", null], value: "%Y-%m" }],
        autorangeoptions: { clipmin: dates[0], clipmax: end },
        rangeslider: { visible: true, range: [dates[0], end], yaxis: { rangemode: "auto" }, thickness: .08, bgcolor: "#f7f7f7", bordercolor: "#e8e8e8", borderwidth: 1 } as Partial<RangeSlider> & { yaxis: { rangemode: "auto" } },
        rangeselector: { buttons: [
          { count: 1, label: "1개월", step: "month", stepmode: "backward" },
          { count: 3, label: "3개월", step: "month", stepmode: "backward" },
          { count: 6, label: "6개월", step: "month", stepmode: "backward" },
          { count: 1, label: "1년", step: "year", stepmode: "backward" },
          { label: "전체", step: "all" },
        ], x: 0, y: 1.02, yanchor: "bottom", bgcolor: "#f0f0f0", activecolor: "#dcdcdc", font: { size: 11 } },
        rangebreaks: [{ bounds: ["sat", "mon"] }, { values: closedWeekdays([...dates, ...(path || []).map((p) => p.date)]) }],
      },
      yaxis: { domain: [.28, 1], range: autoY((d) => d >= range[0] && d <= range[1]) ?? undefined, gridcolor: grid, tickformat: ",.0f", fixedrange: true },
      yaxis2: { domain: [0, .17], gridcolor: grid, tickformat: ".2s", fixedrange: true },
    };
    return { traces, layout, autoY };
  }, [prices, trades, path, bands, lines, marks, selected, focus, kind, mas, label]);
  if (!prices.length) return <p className="notice">이 저장 결과에는 일봉이 포함되어 있지 않습니다. 같은 조건으로 다시 실행하면 주가 차트를 볼 수 있습니다.</p>;
  return <div className="chart" id="price-chart">
    <div className="chart-tools">
      <div className="segmented" role="group" aria-label="차트 종류">
        {kinds.map(([value, text]) => <button key={value} aria-pressed={kind === value} onClick={() => setKind(value)}>{text}</button>)}
      </div>
      <div className="ma-toggles" role="group" aria-label="이동평균선">
        {[5, 20, 60, 120].map((n) => <button key={n} className="ma-toggle" aria-pressed={mas.includes(n)}
          onClick={() => setMas((m) => m.includes(n) ? m.filter((x) => x !== n) : [...m, n].sort((a, b) => a - b))}>
          <i style={{ background: maColors[n] }} />{n}일</button>)}
        {band && <button className="ma-toggle" aria-pressed={showBand} onClick={() => setShowBand(!showBand)}><i className="swatch-band" />범위</button>}
        {scenarios && <button className="ma-toggle" aria-pressed={showScenarios} onClick={() => setShowScenarios(!showScenarios)}><i className="swatch-scenario" />시나리오</button>}
      </div>
    </div>
    {selected && <div className="trade-detail" role="status"><strong>{selected.date} · {selected.side === "buy" ? "▲ 매수" : "▼ 매도"}</strong><span>체결가 {money(selected.price)}원 · {selected.shares}주 · 비용 {money(selected.costs)}원</span></div>}
    <Plot traces={traces} layout={layout} autoY={autoY} label={label} />
    <p className="caption chart-key">
      {trades.length > 0 && <><span className="up">▲ 매수</span> <span className="down">▼ 매도</span> · </>}
      {marks?.length ? "회색 점선은 헤드 앤 숄더 넥라인 · " : ""}
      {path?.length ? "점선은 중앙 예측 · " : ""}{band ? "음영은 50%·80% 예측 범위 · " : ""}{scenarios ? "가는 선은 비슷한 과거 차트 이후 흐름 · " : ""}캔들은 상승 빨강 / 하락 파랑 · 주말·휴장일 제외 · 휠로 확대·축소, 드래그로 이동, 더블 클릭으로 초기화
    </p>
  </div>;
}

export function EquityChart({ result }: { result: Result }) {
  const [mode, setMode] = useState<"equity" | "drawdown">("equity");
  const { traces, layout } = useMemo(() => ({
    traces: [{
      type: "scatter", mode: "lines", x: result.curve.map((p) => p.date),
      y: result.curve.map((p) => mode === "equity" ? p.equity : p.drawdown),
      line: { color: mode === "equity" ? ink : down, width: 1.8 }, fill: mode === "drawdown" ? "tozeroy" : undefined, fillcolor: "rgba(37,99,235,.12)",
      hovertemplate: mode === "equity" ? "%{x}<br>%{y:,.0f}원<extra></extra>" : "%{x}<br>낙폭 %{y:.2%}<extra></extra>",
    }] as Data[],
    layout: { height: 260, showlegend: false, margin: { l: 60, r: 12, t: 12, b: 32 }, xaxis: { showgrid: false, tickformat: "%Y-%m" },
      yaxis: { gridcolor: grid, tickformat: mode === "equity" ? ",.0f" : ".0%", fixedrange: true } } as Partial<Layout>,
  }), [result, mode]);
  return <div className="chart">
    <div className="chart-tools">
      <h3>자산 변화</h3>
      <div className="segmented" role="group" aria-label="성과 차트 종류">
        <button aria-pressed={mode === "equity"} onClick={() => setMode("equity")}>평가 자산</button>
        <button aria-pressed={mode === "drawdown"} onClick={() => setMode("drawdown")}>낙폭</button>
      </div>
    </div>
    <Plot traces={traces} layout={layout} label={mode === "equity" ? "기간별 평가 자산" : "기간별 낙폭"} />
  </div>;
}
