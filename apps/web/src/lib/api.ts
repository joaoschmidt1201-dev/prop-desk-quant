/**
 * API client for the ST | Dashboard backend.
 *
 * The base URL is read from NEXT_PUBLIC_API_URL (set in .env.local).
 * In production this points to the Render-hosted FastAPI; in dev it's
 * localhost:8000. See apps/api/SPEC.md for the contract.
 */

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

export type Filter = {
  months: string[];
  env: string | null;
};

export type MonthInfo = {
  sheet: string;
  env: string;
  label: string;
  n_trades: number;
  active: boolean;
};

export type Trade = {
  name: string;
  environment: string;
  environment_raw: string;
  underlying: string;
  is_active: boolean;
  open_date: string | null;
  exp_date: string | null;
  dte_open: number | null;
  dte_remaining: number | null;
  net_credit: number | null;
  max_loss: number | null;
  delta: number | null;
  pnl?: number;
  open_pnl?: number;
  [k: string]: unknown;
};

export type Kpis = {
  filter: Filter;
  pnl: { open: number; rlzd: number; delta: number; max_profit: number };
  risk: { max_loss_exposed: number; net_credit_at_risk: number; est_daily_theta: number };
  performance: {
    win_rate: number | null;
    profit_factor: number | null;
    expectancy: number | null;
  };
  trade_intel: {
    best_trade: number | null;
    worst_trade: number | null;
    n_active: number;
    n_closed: number;
  };
};

export type AnalyticsGroup = {
  key: string;
  label?: string;
  pnl: number;
  n_trades: number;
  wins?: number;
  losses?: number;
  active?: number | boolean;
  win_rate?: number | null;
  avg_pnl?: number | null;
  open_pnl?: number;
  rlzd?: number;
  daily_pnl?: number;
};

export type AnalyticsTrade = {
  name: string;
  sheet: string;
  underlying: string;
  strategy: string;
  dte_bucket: string;
  open_weekday: string;
  close_weekday?: string;
  days_held?: number | null;
  pnl: number;
  is_active: boolean;
};

export type Analytics = {
  filter: Filter;
  summary: {
    total_pnl: number;
    n_trades: number;
    n_active: number;
    win_rate: number | null;
    avg_win: number | null;
    avg_loss: number | null;
    profit_factor: number | null;
    avg_days_held?: number | null;
  };
  by_month: AnalyticsGroup[];
  by_strategy: AnalyticsGroup[];
  by_underlying: AnalyticsGroup[];
  by_dte_bucket: AnalyticsGroup[];
  by_weekday: AnalyticsGroup[];
  by_day?: Array<AnalyticsGroup & { cumulative_pnl?: number }>;
  by_close_weekday?: AnalyticsGroup[];
  top_winners: AnalyticsTrade[];
  top_losers: AnalyticsTrade[];
  insights: { label: string; value: string; detail: number | string }[];
};

export type ChatMessage = {
  role: "user" | "assistant" | "system";
  content: string;
};

export type BacktestSummary = {
  id: string;
  name: string;
  underlying: string;
  strategy: string;
  horizon: string;
  period: string | null;
  kpis: {
    n_trades: number;
    n_open: number;
    total_pnl: number;
    win_rate: number | null;
    profit_factor: number | null;
    max_drawdown: number;
    sharpe: number | null;
  };
};

export type BacktestEquityPoint = {
  trade_date: string;
  exp_date: string;
  pnl_usd: number;
  cumulative_pnl: number;
  drawdown: number;
};

export type BacktestKpis = {
  n_trades: number;
  n_open: number;
  wins: number;
  losses: number;
  total_pnl: number;
  best_trade: number | null;
  worst_trade: number | null;
  win_rate: number | null;
  profit_factor: number | null;
  avg_win: number | null;
  avg_loss: number | null;
  payoff: number | null;
  expectancy: number | null;
  in_range_rate: number | null;
  max_drawdown: number;
  sharpe: number | null;
  max_consecutive_losses: number;
  equity: BacktestEquityPoint[];
};

export type BacktestDetail = {
  meta: {
    id: string;
    name: string;
    underlying: string;
    strategy: string;
    horizon: string;
    description?: string | null;
    kind: "ss42" | "ic7";
    period: string | null;
    multiplier: number;
    rule: string;
    available_rules: string[];
  };
  kpis: BacktestKpis;
  trades: Record<string, unknown>[];
  daily: Record<string, unknown>[];
};

function qs(filter: Partial<Filter>): string {
  const params = new URLSearchParams();
  if (filter.months?.length) params.set("month", filter.months.join(","));
  if (filter.env) params.set("env", filter.env);
  const s = params.toString();
  return s ? `?${s}` : "";
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API ${res.status}: ${path}`);
  return res.json();
}

async function post<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { method: "POST", cache: "no-store" });
  if (!res.ok) throw new Error(`API ${res.status}: ${path}`);
  return res.json();
}

export const api = {
  health: () => get<{ status: string; snapshot_age_seconds: number | null; snapshot_generated_at: string | null }>("/api/health"),
  refreshSnapshot: () => post<{ status: "refresh_started" | "already_running" }>("/api/snapshot/refresh"),
  months: () => get<{ months: MonthInfo[] }>("/api/months"),
  trades: (filter: Partial<Filter> = {}) =>
    get<{ filter: Filter; trades: Trade[] }>(`/api/trades${qs(filter)}`),
  kpis: (filter: Partial<Filter> = {}) => get<Kpis>(`/api/kpis${qs(filter)}`),
  analytics: (filter: Partial<Filter> = {}) => get<Analytics>(`/api/analytics${qs(filter)}`),
  backtests: () => get<{ backtests: BacktestSummary[] }>("/api/backtests"),
  backtest: (id: string, rule?: string) => {
    const q = rule && rule !== "Hold to Expiration" ? `?rule=${encodeURIComponent(rule)}` : "";
    return get<BacktestDetail>(`/api/backtests/${id}${q}`);
  },

  /**
   * Streams chat tokens via SSE. Calls onDelta for each text chunk.
   * Returns a promise that resolves when the stream ends.
   */
  async chat(
    messages: ChatMessage[],
    filter: Filter,
    provider: "anthropic" | "openai",
    onDelta: (text: string) => void,
    signal?: AbortSignal,
  ): Promise<void> {
    const res = await fetch(`${API_BASE}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages, filter, provider }),
      signal,
    });
    if (!res.ok || !res.body) throw new Error(`Chat failed: ${res.status}`);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        const m = line.match(/^data: (.+)$/);
        if (!m) continue;
        try {
          const evt = JSON.parse(m[1]) as { delta?: string; done?: boolean; error?: string };
          if (evt.error) throw new Error(evt.error);
          if (evt.delta) onDelta(evt.delta);
          if (evt.done) return;
        } catch (e) {
          if (e instanceof SyntaxError) continue;
          throw e;
        }
      }
    }
  },
};
