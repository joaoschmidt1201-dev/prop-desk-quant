"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight, Radar, TrendingDown, TrendingUp } from "lucide-react";
import { api, type ForwardtestStrategySummary } from "@/lib/api";
import { fmtMoney, fmtPct, fmtNum, pnlClass } from "@/lib/format";
import { DASHBOARD_REFETCH_INTERVAL_MS } from "@/lib/refresh";

export function ForwardtestsOverview() {
  const { data, isLoading } = useQuery({
    queryKey: ["forwardtests"],
    queryFn: () => api.forwardtests(),
    refetchInterval: DASHBOARD_REFETCH_INTERVAL_MS,
  });
  const items = data?.forwardtests ?? [];

  return (
    <main className="mx-auto w-full max-w-[1600px] flex-1 px-8 py-8">
      <div className="mb-8 flex items-end justify-between">
        <div>
          <div className="mb-2 inline-flex items-center gap-2 rounded-full border border-primary/25 bg-primary/10 px-3 py-1 text-[11px] font-medium uppercase tracking-[0.22em] text-primary">
            <Radar className="h-3.5 w-3.5" />
            Forward Lab
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">Forward tests</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            Live OptionStrat-fed strategies. Open trades show live mark-to-market; closed trades feed a desk-running KPI band so we can validate edge before going live.
          </p>
        </div>
        <div className="hidden items-center gap-2 text-xs text-muted-foreground sm:flex">
          <span className="h-1.5 w-1.5 rounded-full bg-[var(--gain)]" />
          <span>Auto-grouped from <code className="rounded bg-card/60 px-1.5 py-0.5 text-[10px]">FOR Trades</code></span>
        </div>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-72 animate-pulse rounded-2xl border border-border/60 bg-card/30" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
          {items.map((s) => <StrategyCard key={s.strategy_id} s={s} />)}
        </div>
      )}
    </main>
  );
}

function EmptyState() {
  return (
    <div className="rounded-2xl border border-dashed border-border/60 bg-card/30 p-10 text-center">
      <div className="mx-auto inline-flex h-12 w-12 items-center justify-center rounded-full border border-border/60 bg-card/40">
        <Radar className="h-5 w-5 text-muted-foreground" />
      </div>
      <h3 className="mt-4 text-base font-semibold">No forward-test strategies detected yet</h3>
      <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
        Open a forward trade in the <code className="rounded bg-card/60 px-1.5 py-0.5 text-[11px]">FOR Trades</code> tab and refresh the snapshot — strategies are auto-grouped from each trade's name (e.g., &ldquo;T54 IWM Triple Calendar&rdquo; → Triple Calendar / IWM). Add an optional <code className="rounded bg-card/60 px-1.5 py-0.5 text-[11px]">FT Strategies</code> row to enrich the card with description, leg template, and rules.
      </p>
    </div>
  );
}

function StrategyCard({ s }: { s: ForwardtestStrategySummary }) {
  const total = s.open_pnl + s.closed_pnl;
  const positive = total >= 0;
  return (
    <Link
      href={`/forwardtests/${encodeURIComponent(s.strategy_id)}`}
      className="group relative flex flex-col overflow-hidden rounded-2xl border border-border/60 bg-gradient-to-b from-card/70 to-card/35 p-6 shadow-2xl shadow-black/10 transition hover:border-primary/40"
    >
      <div className="mb-4 flex items-start justify-between">
        <div>
          <div className="text-[10px] uppercase tracking-[0.22em] text-muted-foreground">{s.strategy_family ?? "Strategy"}</div>
          <div className="mt-1 flex items-baseline gap-2">
            <h3 className="text-xl font-semibold tracking-tight">{s.underlying ?? "—"}</h3>
            {s.horizon && (
              <span className="rounded-md border border-border/60 bg-background/40 px-2 py-0.5 text-[10px] text-muted-foreground">{s.horizon}</span>
            )}
          </div>
          <div className="mt-1 text-[11px] text-muted-foreground">{s.name}</div>
        </div>
        <ArrowUpRight className="h-5 w-5 text-muted-foreground/60 transition group-hover:translate-x-0.5 group-hover:-translate-y-0.5 group-hover:text-primary" />
      </div>

      <div className="mb-5 rounded-xl border border-border/40 bg-background/25 p-4">
        <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Total P&L (open + closed)</div>
        <div className="mt-1 flex items-baseline gap-2">
          <span className={`text-3xl font-semibold tabular ${pnlClass(total)}`}>{fmtMoney(total)}</span>
          {positive ? (
            <TrendingUp className="h-4 w-4 text-[var(--gain)]" />
          ) : (
            <TrendingDown className="h-4 w-4 text-[var(--loss)]" />
          )}
        </div>
        <div className="mt-1 text-[11px] text-muted-foreground">
          {s.n_open} open · {s.n_closed} closed
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Stat label="Open P&L" value={fmtMoney(s.open_pnl)} tone={s.open_pnl} />
        <Stat label="Closed P&L" value={fmtMoney(s.closed_pnl)} tone={s.closed_pnl} />
        <Stat label="Win rate" value={fmtPct(s.win_rate)} />
        <Stat label="Profit factor" value={fmtNum(s.profit_factor)} />
      </div>
    </Link>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: number }) {
  return (
    <div className="rounded-lg border border-border/40 bg-background/20 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className={`mt-0.5 text-sm font-semibold tabular ${tone == null ? "" : pnlClass(tone)}`}>{value}</div>
    </div>
  );
}
