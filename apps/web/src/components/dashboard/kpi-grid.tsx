"use client";

import { useQuery } from "@tanstack/react-query";
import { api, type Filter } from "@/lib/api";
import { KpiCard } from "./kpi-card";

type Props = { filter: Filter };

export function KpiGrid({ filter }: Props) {
  const { data, isLoading } = useQuery({
    queryKey: ["kpis", filter.months, filter.env],
    queryFn: () => api.kpis(filter),
  });

  if (isLoading || !data) {
    return (
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="h-[112px] animate-pulse rounded-xl border border-border/60 bg-card/30" />
        ))}
      </div>
    );
  }

  const { pnl, risk, performance, trade_intel } = data;

  return (
    <div className="space-y-4">
      <section>
        <h2 className="mb-2 text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">P&L</h2>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <KpiCard label="Open P&L" value={pnl.open} format="money" size="lg" />
          <KpiCard label="Realized" value={pnl.rlzd} format="money" size="lg" />
          <KpiCard label="Δ Total" value={pnl.delta} format="num" hint="portfolio delta" />
          <KpiCard label="Net Credit @ Risk" value={risk.net_credit_at_risk} format="money" />
        </div>
      </section>

      <section>
        <h2 className="mb-2 text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">Risk · Performance</h2>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <KpiCard label="Max Loss Exposed" value={risk.max_loss_exposed} format="money" />
          <KpiCard label="Daily Theta" value={risk.est_daily_theta} format="money" hint="estimated" />
          <KpiCard label="Win Rate" value={performance.win_rate} format="pct" hint={`${trade_intel.n_closed ?? 0} closed`} />
          <KpiCard label="Profit Factor" value={performance.profit_factor} format="num" hint={performance.expectancy != null ? `Exp ${performance.expectancy.toFixed(0)}` : undefined} />
        </div>
      </section>

      <section>
        <h2 className="mb-2 text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">Trade Intelligence</h2>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <KpiCard label="Best Trade" value={trade_intel.best_trade ?? null} format="money" />
          <KpiCard label="Worst Trade" value={trade_intel.worst_trade ?? null} format="money" />
          <KpiCard label="Active" value={trade_intel.n_active} format="num" hint="open positions" />
          <KpiCard label="Closed" value={trade_intel.n_closed} format="num" hint="historical" />
        </div>
      </section>
    </div>
  );
}
