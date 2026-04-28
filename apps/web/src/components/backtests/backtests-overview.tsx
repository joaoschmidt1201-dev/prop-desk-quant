"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight, FlaskConical, TrendingDown, TrendingUp } from "lucide-react";
import { api, type BacktestSummary } from "@/lib/api";
import { fmtMoney, fmtPct, fmtNum, pnlClass } from "@/lib/format";

export function BacktestsOverview() {
  const { data, isLoading } = useQuery({ queryKey: ["backtests"], queryFn: () => api.backtests() });
  const items = data?.backtests ?? [];

  return (
    <main className="mx-auto w-full max-w-[1600px] flex-1 px-8 py-8">
      <div className="mb-8 flex items-end justify-between">
        <div>
          <div className="mb-2 inline-flex items-center gap-2 rounded-full border border-primary/25 bg-primary/10 px-3 py-1 text-[11px] font-medium uppercase tracking-[0.22em] text-primary">
            <FlaskConical className="h-3.5 w-3.5" />
            Research Lab
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">Backtests</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            Historical edge studies on the desk's core strategies. Mid-price fills, calendar DTE, no live execution. Sharpe is informational (per-trade, not return-normalized).
          </p>
        </div>
        <div className="hidden items-center gap-2 text-xs text-muted-foreground sm:flex">
          <span className="h-1.5 w-1.5 rounded-full bg-[var(--gain)]" />
          <span>Sourced from <code className="rounded bg-card/60 px-1.5 py-0.5 text-[10px]">reports/*_backtest/</code></span>
        </div>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-72 animate-pulse rounded-2xl border border-border/60 bg-card/30" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
          {items.map((bt) => <BacktestCard key={bt.id} bt={bt} />)}
        </div>
      )}
    </main>
  );
}

function BacktestCard({ bt }: { bt: BacktestSummary }) {
  const positive = bt.kpis.total_pnl >= 0;
  return (
    <Link
      href={`/backtests/${bt.id}`}
      className="group relative flex flex-col overflow-hidden rounded-2xl border border-border/60 bg-gradient-to-b from-card/70 to-card/35 p-6 shadow-2xl shadow-black/10 transition hover:border-primary/40"
    >
      <div className="mb-4 flex items-start justify-between">
        <div>
          <div className="text-[10px] uppercase tracking-[0.22em] text-muted-foreground">{bt.strategy}</div>
          <div className="mt-1 flex items-baseline gap-2">
            <h3 className="text-xl font-semibold tracking-tight">{bt.underlying}</h3>
            <span className="rounded-md border border-border/60 bg-background/40 px-2 py-0.5 text-[10px] text-muted-foreground">{bt.horizon}</span>
          </div>
        </div>
        <ArrowUpRight className="h-5 w-5 text-muted-foreground/60 transition group-hover:translate-x-0.5 group-hover:-translate-y-0.5 group-hover:text-primary" />
      </div>

      <div className="mb-5 rounded-xl border border-border/40 bg-background/25 p-4">
        <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Total P&L</div>
        <div className="mt-1 flex items-baseline gap-2">
          <span className={`text-3xl font-semibold tabular ${pnlClass(bt.kpis.total_pnl)}`}>{fmtMoney(bt.kpis.total_pnl)}</span>
          {positive ? (
            <TrendingUp className="h-4 w-4 text-[var(--gain)]" />
          ) : (
            <TrendingDown className="h-4 w-4 text-[var(--loss)]" />
          )}
        </div>
        <div className="mt-1 text-[11px] text-muted-foreground">
          {bt.kpis.n_trades} closed · {bt.kpis.n_open} open · {bt.period ?? "no period"}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Stat label="Win rate" value={fmtPct(bt.kpis.win_rate)} />
        <Stat label="Profit factor" value={fmtNum(bt.kpis.profit_factor)} />
        <Stat label="Max DD" value={fmtMoney(bt.kpis.max_drawdown)} tone={bt.kpis.max_drawdown} />
        <Stat label="Sharpe (raw)" value={fmtNum(bt.kpis.sharpe)} />
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
