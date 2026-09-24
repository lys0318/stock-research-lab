export type Dataset = {
  id: string;
  name: string;
  symbol: string;
  start: string;
  end: string;
  rows: number;
  source: string;
  synthetic: boolean;
  adjustment: string;
};
export type Config = {
  dataset_id: string;
  start: string;
  end: string;
  strategy: string;
  capital: number;
  fee: number;
  tax: number;
  slippage: number;
  ma_window: number;
  seed: number;
};
export type Metrics = { total_return: number; max_drawdown: number; trade_count: number; final_equity: number };
export type Job = { id: string; status: string; config: Config; created_at: string; error?: string; metrics?: Metrics | null };
export type Price = { date: string; open: number; high: number; low: number; close: number; volume: number };
export type Trade = { date: string; side: string; shares: number; price: number; costs: number; phase?: "open" | "close" };
export type Result = {
  id: string;
  dataset: Dataset;
  config: Config;
  metrics: Metrics;
  curve: { date: string; equity: number; drawdown: number }[];
  prices?: Price[];
  trades: Trade[];
  prediction: null | { accuracy: number; brier: number; threshold: number };
  created_at: string;
  compute_seconds: number;
  code_version: string;
  assumptions: string[];
};
export type Benchmark = {
  id: string;
  environment: string;
  created_at: string;
  cost_note: string;
  runs: {
    workers: number;
    total_seconds: number;
    throughput: number;
    observed_concurrency: number;
    equal_results: boolean | null;
    estimated_compute_cost: number | null;
  }[];
};
export type StockHit = { symbol: string; name: string; market: string | null; dataset_id: string | null; end: string | null };
export type Forecast = {
  horizon: number;
  last_date: string;
  last_close: number;
  path: { date: string; price: number }[];
  prices: Price[];
  evaluation: {
    hit_rate: number;
    up_rate: number;
    mape: number;
    naive_mape: number;
    train_rows: number;
    test_rows: number;
    train_label_end: string;
    test_start: string;
  };
  notice: string;
  dataset: Dataset;
};

export const publicMode = import.meta.env.VITE_PUBLIC_MODE === "true";
/** Names picked in search, so a stock page can title itself while its data is still being collected. */
export const nameHints = new Map<string, string>();
export const labels: Record<string, string> = { hold: "매수 후 보유", ma: "이동평균 전략", model: "AI 방향 예측" };
export const states: Record<string, string> = {
  queued: "대기 중",
  running: "계산 중",
  completed: "완료",
  failed: "실패",
  cancelled: "취소됨",
};
export const won = (v: number) => new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 0 }).format(v);
export const pct = (v: number) => (v > 0 ? "+" : "") + (v * 100).toFixed(2) + "%";
export const tone = (v: number) => (v > 0 ? "up" : v < 0 ? "down" : "");

export async function api<T = any>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch("/api" + path, {
    ...options,
    headers: { "Content-Type": "application/json", "X-Research-Local": "1", ...options?.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: "서버 응답을 읽을 수 없습니다." }));
    throw new Error(typeof body.detail === "string" ? body.detail : "입력 조건을 확인해 주세요.");
  }
  return response.json();
}

export type RoundTrip = { buy: Trade; sell: Trade; index: number; days: number; ret: number; pnl: number };
/** Pairs each buy with the following sell. Costs are included on both legs. */
export function roundTrips(trades: Trade[]): RoundTrip[] {
  const trips: RoundTrip[] = [];
  trades.forEach((sell, i) => {
    const buy = trades[i - 1];
    if (sell.side !== "sell" || buy?.side !== "buy") return;
    const paid = buy.shares * buy.price + buy.costs;
    const pnl = sell.shares * sell.price - sell.costs - paid;
    trips.push({ buy, sell, index: i - 1, days: (Date.parse(sell.date) - Date.parse(buy.date)) / 86400000, ret: pnl / paid, pnl });
  });
  return trips;
}
