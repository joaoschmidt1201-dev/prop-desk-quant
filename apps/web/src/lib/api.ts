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
  live?: boolean;
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
  dte_open_raw: string | null;
  dte_remaining: number | null;
  net_credit: number | null;
  max_loss: number | null;
  delta: number | null;
  pnl?: number;
  open_pnl?: number;
  // Live BE→Spot distance (attached by /api/trades for active trades).
  lw_be?: number | null;
  up_be?: number | null;
  spot?: number | null;
  spot_source?: "live" | "open" | null;
  spot_asof?: string | null;
  dist_to_lw_be_pct?: number | null;
  dist_to_up_be_pct?: number | null;
  dist_to_be_pct?: number | null;
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
  family?: string;
  horizon: string;
  period: string | null;
  kpis: {
    n_trades: number;
    n_open: number;
    total_pnl: number;
    total_pnl_pct?: number | null;
    starting_capital?: number | null;
    win_rate: number | null;
    profit_factor: number | null;
    max_drawdown: number;
    max_drawdown_pct?: number | null;
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

export type BacktestYearRow = {
  year: number;
  n_trades: number;
  wins: number;
  win_rate: number | null;
  total_pnl: number;
  total_pnl_pct: number;
};

export type BacktestVixRow = {
  bucket: string;
  n_trades: number;
  wins: number;
  win_rate: number | null;
  total_pnl: number;
  total_pnl_pct: number;
};

export type BacktestDowRow = {
  dow: string;
  n_trades: number;
  wins: number;
  win_rate: number | null;
  total_pnl: number;
  total_pnl_pct: number;
};

export type BacktestKpis = {
  n_trades: number;
  n_open: number;
  wins: number;
  losses: number;
  total_pnl: number;
  total_pnl_pct?: number | null;
  starting_capital?: number | null;
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
  max_drawdown_pct?: number | null;
  sharpe: number | null;
  max_consecutive_losses: number;
  equity: BacktestEquityPoint[];
  peak_capital_deployed?: number | null;
  avg_capital_deployed?: number | null;
  return_on_peak_capital_pct?: number | null;
  capital_utilization_pct?: number | null;
  yearly_breakdown?: BacktestYearRow[];
  vix_breakdown?: BacktestVixRow[];
  dow_breakdown?: BacktestDowRow[];
};

export type BacktestDetail = {
  meta: {
    id: string;
    name: string;
    underlying: string;
    strategy: string;
    family?: string;
    horizon: string;
    description?: string | null;
    kind: "ss42" | "ic7" | "triplecal" | "batman" | "ic0dte" | "ironfly" | "pl5";
    period: string | null;
    multiplier: number;
    rule: string;
    available_rules: string[];
    vix_filter?: string;
    available_vix_filters?: string[];
    width_rule?: string | null;
    available_width_rules?: string[];
  };
  kpis: BacktestKpis;
  trades: Record<string, unknown>[];
  daily: Record<string, unknown>[];
};

export type LegSpec = {
  side: "buy" | "sell";
  type: "call" | "put";
  qty: number;
  strike_offset?: string | null;
  expiration_offset_days?: number | null;
};

export type ForwardtestEnv = "CZ_Forward" | "JS_Forward";

export type ForwardtestStrategySummary = {
  strategy_id: string;
  name: string;
  underlying: string | null;
  structure: string | null;
  horizon: string | null;
  strategy_family: string | null;
  is_debit: boolean;
  description: string | null;
  status: string;
  n_open: number;
  n_closed: number;
  open_pnl: number;
  closed_pnl: number;
  win_rate: number | null;
  profit_factor: number | null;
  max_drawdown: number;
  sharpe: number | null;
};

export type ForwardtestDailyPoint = {
  date: string | null;
  pnl: number | null;
  delta: number | null;
};

export type ForwardtestMilestones = {
  is_debit: boolean;
  max_profit_usd: number | null;
  net_debit_usd: number | null;
  max_pnl_seen: number | null;
  min_pnl_seen: number | null;
  max_dd_from_peak: number | null;
  dit_to_10mp: number | null;
  dit_to_25mp: number | null;
  dit_to_50mp: number | null;
  dit_to_75mp: number | null;
};

export type ForwardtestTrade = Trade & {
  strategy_id?: string | null;
  pnl_current?: number | null;
  delta_current?: number | null;
  pct_to_lw_be?: number | null;
  pct_to_up_be?: number | null;
  lw_be?: number | null;
  up_be?: number | null;
  strikes?: string | null;
  visual_open_date?: string | null;
  visual_exp_date?: string | null;
  inferred_close_date?: string | null;
  days_held?: number | null;
  daily_history?: ForwardtestDailyPoint[];
  milestones?: ForwardtestMilestones;
};

export type ForwardtestDailyPnl = {
  date: string;
  pnl?: number;
  open_pnl?: number;
  rlzd?: number;
  daily_pnl?: number;
  n_trades?: number;
};

export type ForwardtestLabHero = {
  n_strategies: number;
  n_trades_open: number;
  n_trades_closed: number;
  total_pnl: number;
  global_win_rate: number | null;
  median_dit_to_50mp: number | null;
};

export type ForwardtestMatrixCell = {
  strategy_id: string;
  name: string;
  strategy_family: string | null;
  structure: string | null;
  underlying: string | null;
  is_debit: boolean;
  status: string;
  n_open: number;
  n_closed: number;
  open_pnl: number;
  closed_pnl: number;
  total_pnl: number;
  win_rate: number | null;
  profit_factor: number | null;
  median_dit_to_50mp: number | null;
};

export type ForwardtestStructureRow = {
  structure: string | null;
  n_open: number;
  n_closed: number;
  total_pnl: number;
  win_rate: number | null;
  median_dit_to_50mp: number | null;
  underlyings: string[];
};

export type ForwardtestStructureGroup = {
  family: string;
  structures: ForwardtestStructureRow[];
};

export type ForwardtestRecentEntry = {
  kind: "open" | "closed";
  trade_name: string;
  strategy_id: string;
  strategy_name: string;
  underlying: string | null;
  structure: string | null;
  event_date: string | null;
  pnl: number;
};

export type ForwardtestLabPayload = {
  env: ForwardtestEnv;
  hero: ForwardtestLabHero;
  matrix: ForwardtestMatrixCell[];
  structure_comparison: ForwardtestStructureGroup[];
  leaderboards: {
    top_winrate: ForwardtestMatrixCell[];
    top_pnl: ForwardtestMatrixCell[];
    top_speed: ForwardtestMatrixCell[];
  };
  recent_activity: ForwardtestRecentEntry[];
};

export type ForwardtestAggDim = "family" | "ticker" | "structure";

export type ForwardtestAggregationRow = {
  key: string;
  n_trades_open: number;
  n_trades_closed: number;
  n_trades_total: number;
  open_pnl: number;
  closed_pnl: number;
  total_pnl: number;
  win_rate: number | null;
  profit_factor: number | null;
  avg_dit_to_10mp: number | null;
  avg_dit_to_25mp: number | null;
  avg_dit_to_50mp: number | null;
  avg_dit_to_75mp: number | null;
};

export type ForwardtestAggregationsPayload = {
  env: ForwardtestEnv;
  dim: ForwardtestAggDim;
  rows: ForwardtestAggregationRow[];
};

export type ForwardtestDetail = {
  env: ForwardtestEnv;
  meta: {
    strategy_id: string;
    name: string;
    underlying: string | null;
    structure: string | null;
    horizon: string | null;
    strategy_family: string | null;
    is_debit: boolean;
    description: string | null;
    entry_rule: string | null;
    exit_rule: string | null;
    legs_template: LegSpec[];
    status: string;
    sheet: string | null;
    tracking_since: string | null;
    period: string | null;
  };
  kpis: BacktestKpis;
  open_trades: ForwardtestTrade[];
  closed_trades: ForwardtestTrade[];
  daily_pnls: ForwardtestDailyPnl[];
};

export type OccurrenceMetric = {
  T: number;
  B: number;
  Bk: number;
  F: number;
  bounce_pct: number | null;
  break_pct: number | null;
  false_pct: number | null;
  low_sample: boolean;
  tolerance_pct: number | null;
};

export type OccurrenceCategory = {
  name: string;
  tickers: string[];
};

export type OccurrenceSnapshotMeta = {
  date: string;
  file: string;
  raw_tf: string;
  age_seconds: number | null;
  has_tolerances: boolean;
  grid_size?: number;
  selected_tol_idx?: number;
};

export type OccurrenceLeaderboardEntry = {
  ticker: string;
  tf: string;
  ma: string;
  total: number;
  bounce_pct: number | null;
  break_pct: number | null;
  false_pct: number | null;
};

export type OccurrenceTopSetupEntry = {
  tf: string;
  ma: string;
  total: number;
  bounce_pct: number | null;
  break_pct: number | null;
  false_pct: number | null;
};

export type OccurrenceMatrixPayload = {
  date: string | null;
  latest_snapshot_date: string | null;
  oldest_snapshot_date: string | null;
  oldest_snapshot_age_seconds: number | null;
  generated_at: string;
  expected_tfs: string[];
  tfs: string[];
  mas: string[];
  min_sample: number;
  categories: OccurrenceCategory[];
  tickers: string[];
  dates: Record<string, string>;
  snapshots: Record<string, OccurrenceSnapshotMeta>;
  tolerances: Record<string, Array<number | null>>;
  tol_grids?: Record<string, Record<string, Array<number | null>>>;
  grid_sizes?: Record<string, number>;
  selected_tol_idx?: Record<string, number>;
  data: Record<string, Record<string, Record<string, OccurrenceMetric>>>;
  leaderboards: {
    mean_reversion: OccurrenceLeaderboardEntry[];
    breakout: OccurrenceLeaderboardEntry[];
  };
  top_setups: Record<string, OccurrenceTopSetupEntry[]>;
};

// ─── GEX (our own gamma-exposure engine) ───────────────────────────────────────

export type GexExpiration = { date: string; unix: number; dte: number };

export type GexExpirations = {
  underlying: string;
  yahoo_symbol: string;
  proxy: boolean;
  index_symbol: string | null;
  spot: number | null;
  expirations: GexExpiration[];
  asof: string;
};

export type GexStrike = {
  strike: number;
  call_gex: number; put_gex: number; net_gex: number; abs_gex: number;
  call_dex: number; put_dex: number; net_dex: number;
  call_oi: number; put_oi: number; net_oi: number;
  call_vol: number; put_vol: number; net_vol: number;
};

// The metric a profile column / level family can render (Tanuki's 8 + abs gex).
export type GexMetric =
  | "net_gex" | "abs_gex" | "net_dex" | "net_oi" | "net_vol";

export type GexLevels = {
  call_walls: number[];   // C1..C6
  put_walls: number[];    // P1..P6
  hvl: number | null;
  c_trans: number | null;
  p_trans: number | null;
  abs_gex: number[];      // Ab1..Ab3
  dex_pos: number | null; // D+
  dex_neg: number | null; // D-
  oi_call: number | null; // COI
  oi_put: number | null;  // POI
};

export type GexActivity = {
  call_vol: number; put_vol: number; call_oi: number; put_oi: number;
  vol_cp: number | null; oi_cp: number | null;
  lean: number | null;                  // 0..1 toward calls
  lean_label: "calls" | "puts" | null;
  shift: boolean;
  activity: number | null;              // volume intensity vs OI
};

export type GexState =
  | "positive" | "negative" | "transition"
  | "positive_extension" | "negative_extension" | "unknown";
export type GexRegime = "positive" | "negative" | "transition" | "neutral";

export type GexProfile = {
  underlying: string;
  yahoo_symbol: string;
  proxy: boolean;
  index_symbol: string | null;
  index_scale: number | null;
  spot: number;
  expirations_used: string[];
  cumulative: boolean;
  strikes: GexStrike[];
  gamma_flip: number | null;
  call_wall: number | null;
  put_wall: number | null;
  net_gex_total: number;
  net_dex_total: number;
  levels: GexLevels;
  state: GexState;
  regime: GexRegime;
  activity: GexActivity;
  asof: string;
};

export type Gex0dte = {
  underlying: string;
  spot: number;
  net_gex_all: number;
  net_gex_0dte: number;
  has_0dte: boolean;
  asof: string;
};

export type GexHistoryPoint = {
  ts: string;
  underlying: string;
  spot: number;
  net_gex_total: number;
  net_gex_0dte: number;
  gamma_flip: number | null;
  call_wall: number | null;
  put_wall: number | null;
};

export type GexTimeseries = { underlying: string; points: GexHistoryPoint[] };

export type GexHorizon = {
  exp: string | null;
  dte: number | null;
  net_gex: number | null;
  net_dex: number | null;
};

export type GexHorizons = {
  underlying: string;
  yahoo_symbol: string;
  proxy: boolean;
  index_symbol: string | null;
  index_scale: number | null;
  spot: number;
  first: GexHorizon;     // nearest live expiration
  optimal: GexHorizon;   // ~monthly, 35-70 DTE
  every: {
    net_gex: number | null;
    net_dex: number | null;
    n_exp: number;
    change_1d: { gex: number | null; dex: number | null; ref_ts: string | null };
  };
  asof: string;
};

export type GexRange = {
  underlying: string;
  yahoo_symbol: string;
  index_native: boolean;
  spot: number;
  high_52w: number;
  low_52w: number;
  pct_of_range: number | null;
  ma50: number | null;
  ma200: number | null;
  samples: number;
  asof: string;
};

export type GexMatrixCell = {
  net_gex: number;
  net_dex: number;
  oi: number;
  oi_pct?: number;
  c1: number | null;
  p1: number | null;
  hvl: number | null;
};

export type GexMatrixRow = {
  date: string;
  dte: number;
  standalone: GexMatrixCell;
  cumulative: GexMatrixCell;
};

export type GexMatrix = {
  underlying: string;
  yahoo_symbol: string;
  proxy: boolean;
  index_symbol: string | null;
  index_scale: number | null;
  spot: number;
  rows: GexMatrixRow[];
  asof: string;
};

export type GexCandle = { t: number; o: number; h: number; l: number; c: number };

export type GexCandles = {
  underlying: string;
  yahoo_symbol: string;
  index_native: boolean;
  timeframe: string;
  interval: string;
  bars: GexCandle[];
  asof: string;
};

export const GEX_TIMEFRAMES = ["1d", "5d", "1mo", "3mo", "6mo", "1y"] as const;
export type GexTimeframe = (typeof GEX_TIMEFRAMES)[number];

function qs(filter: Partial<Filter>): string {
  const params = new URLSearchParams();
  if (filter.live) {
    // Live ignores month selection on the backend; keep the URL clean.
    params.set("live", "1");
  } else if (filter.months?.length) {
    params.set("month", filter.months.join(","));
  }
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
  occurrenceMatrix: (tolIdxByTf: Record<string, number> = {}) => {
    const params = new URLSearchParams();
    for (const [tf, idx] of Object.entries(tolIdxByTf)) {
      params.set(`tol_idx_${tf}`, String(idx));
    }
    const q = params.toString();
    return get<OccurrenceMatrixPayload>(`/api/occurrence-matrix${q ? `?${q}` : ""}`);
  },
  gexExpirations: (underlying = "SPY") =>
    get<GexExpirations>(`/api/gex/expirations?underlying=${encodeURIComponent(underlying)}`),
  gexProfile: (underlying = "SPY", exp?: string, cumulative = false) => {
    const params = new URLSearchParams({ underlying });
    if (exp) params.set("exp", exp);
    if (cumulative) params.set("cumulative", "true");
    return get<GexProfile>(`/api/gex/profile?${params.toString()}`);
  },
  gex0dte: (underlying = "SPY") =>
    get<Gex0dte>(`/api/gex/0dte?underlying=${encodeURIComponent(underlying)}`),
  gexTimeseries: (underlying = "SPY") =>
    get<GexTimeseries>(`/api/gex/timeseries?underlying=${encodeURIComponent(underlying)}`),
  gexHorizons: (underlying = "SPY") =>
    get<GexHorizons>(`/api/gex/horizons?underlying=${encodeURIComponent(underlying)}`),
  gexRange: (underlying = "SPY") =>
    get<GexRange>(`/api/gex/range?underlying=${encodeURIComponent(underlying)}`),
  gexCandles: (underlying = "SPY", timeframe = "5d") =>
    get<GexCandles>(`/api/gex/candles?underlying=${encodeURIComponent(underlying)}&timeframe=${encodeURIComponent(timeframe)}`),
  gexMatrix: (underlying = "SPY") =>
    get<GexMatrix>(`/api/gex/matrix?underlying=${encodeURIComponent(underlying)}`),
  backtest: (id: string, rule?: string, vixFilter?: string, widthRule?: string) => {
    const params: string[] = [];
    if (rule && rule !== "Hold to Expiration") params.push(`rule=${encodeURIComponent(rule)}`);
    if (vixFilter && vixFilter !== "All") params.push(`vix_filter=${encodeURIComponent(vixFilter)}`);
    if (widthRule) params.push(`width_rule=${encodeURIComponent(widthRule)}`);
    const q = params.length ? `?${params.join("&")}` : "";
    return get<BacktestDetail>(`/api/backtests/${id}${q}`);
  },
  forwardtests: (env: ForwardtestEnv = "CZ_Forward") =>
    get<{ forwardtests: ForwardtestStrategySummary[] }>(`/api/forwardtests?env=${env}`),
  forwardtestsLab: (env: ForwardtestEnv = "CZ_Forward") =>
    get<ForwardtestLabPayload>(`/api/forwardtests/lab?env=${env}`),
  forwardtestsAggregations: (env: ForwardtestEnv = "CZ_Forward", dim: ForwardtestAggDim = "family") =>
    get<ForwardtestAggregationsPayload>(`/api/forwardtests/aggregations?env=${env}&dim=${dim}`),
  forwardtest: (strategyId: string, env: ForwardtestEnv = "CZ_Forward") =>
    get<ForwardtestDetail>(`/api/forwardtests/${encodeURIComponent(strategyId)}?env=${env}`),

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
