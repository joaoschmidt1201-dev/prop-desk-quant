/**
 * API client for the CZ Dashboard backend.
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

export type ChatMessage = {
  role: "user" | "assistant" | "system";
  content: string;
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

export const api = {
  health: () => get<{ status: string; snapshot_age_seconds: number | null; snapshot_generated_at: string | null }>("/api/health"),
  months: () => get<{ months: MonthInfo[] }>("/api/months"),
  trades: (filter: Partial<Filter> = {}) =>
    get<{ filter: Filter; trades: Trade[] }>(`/api/trades${qs(filter)}`),
  kpis: (filter: Partial<Filter> = {}) => get<Kpis>(`/api/kpis${qs(filter)}`),

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
