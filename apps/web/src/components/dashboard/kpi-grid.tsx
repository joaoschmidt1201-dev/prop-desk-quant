"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import { api, type Filter } from "@/lib/api";
import { fmtMoney, fmtNum, fmtPct, pnlClass } from "@/lib/format";
import { DASHBOARD_REFETCH_INTERVAL_MS } from "@/lib/refresh";

type Props = { filter: Filter };

export function KpiGrid({ filter }: Props) {
  const { data, isLoading } = useQuery({
    queryKey: ["kpis", filter.months, filter.env],
    queryFn: () => api.kpis(filter),
    placeholderData: (previousData) => previousData,
    refetchInterval: DASHBOARD_REFETCH_INTERVAL_MS,
    refetchIntervalInBackground: true,
  });

  if (isLoading || !data) {
    return (
      <div className="space-y-6">
        <div className="h-[180px] animate-pulse rounded-2xl bg-card/30" />
        <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="h-[88px] animate-pulse rounded-xl bg-card/20" />
          ))}
        </div>
      </div>
    );
  }

  const { pnl, risk, performance, trade_intel } = data;
  const totalPnl = (pnl.open ?? 0) + (pnl.rlzd ?? 0);

  return (
    <div className="space-y-5">
      <HeroPnl
        total={totalPnl}
        open={pnl.open}
        rlzd={pnl.rlzd}
        delta={pnl.delta}
        nActive={trade_intel.n_active}
        nClosed={trade_intel.n_closed}
      />

      <SectionLabel>Risk</SectionLabel>
      <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
        <Stat label="Max Loss Exposed" value={fmtMoney(risk.max_loss_exposed)} tone={risk.max_loss_exposed} />
        <Stat label="Net Credit @ Risk" value={fmtMoney(risk.net_credit_at_risk)} />
        <Stat label="Max Profit (sheet)" value={fmtMoney(pnl.max_profit)} />
        <Stat label="Daily Theta" value={fmtMoney(risk.est_daily_theta)} hint="estimated" />
      </div>

      <SectionLabel>Performance</SectionLabel>
      <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
        <Stat label="Win Rate" value={fmtPct(performance.win_rate)} hint={`${trade_intel.n_closed} closed`} />
        <Stat label="Profit Factor" value={fmtNum(performance.profit_factor)} />
        <Stat label="Expectancy" value={fmtMoney(performance.expectancy)} tone={performance.expectancy ?? null} />
        <Stat label="Best / Worst" value={`${fmtMoney(trade_intel.best_trade)} · ${fmtMoney(trade_intel.worst_trade)}`} small />
      </div>
    </div>
  );
}

function HeroPnl({ total, open, rlzd, delta, nActive, nClosed }: {
  total: number;
  open: number;
  rlzd: number;
  delta: number;
  nActive: number;
  nClosed: number;
}) {
  const tone = total >= 0 ? "gain" : "loss";
  const Arrow = total > 0 ? ArrowUpRight : total < 0 ? ArrowDownRight : Minus;
  return (
    <div className="rounded-2xl border border-border/50 bg-gradient-to-br from-card/60 via-card/40 to-card/20 p-7">
      <div className="flex items-start justify-between gap-6">
        <div className="min-w-0">
          <div className="text-[10px] font-medium uppercase tracking-[0.22em] text-muted-foreground">Total Portfolio P&L</div>
          <div className="mt-2 flex items-baseline gap-3">
            <span className={`text-5xl font-semibold tabular tracking-tight ${pnlClass(total)}`}>
              {fmtMoney(total)}
            </span>
            <span className={`flex h-7 w-7 items-center justify-center rounded-full ${tone === "gain" ? "bg-[var(--gain)]/15" : "bg-[var(--loss)]/15"}`}>
              <Arrow className={`h-4 w-4 ${tone === "gain" ? "text-[var(--gain)]" : "text-[var(--loss)]"}`} />
            </span>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1.5 text-[12px]">
            <Inline label="Open" value={fmtMoney(open)} tone={open} />
            <Divider />
            <Inline label="Realized" value={fmtMoney(rlzd)} tone={rlzd} />
            <Divider />
            <Inline label="Δ" value={fmtNum(delta)} />
            <Divider />
            <Inline label="Active" value={String(nActive)} />
            <Divider />
            <Inline label="Closed" value={String(nClosed)} />
          </div>
        </div>
      </div>
    </div>
  );
}

function Inline({ label, value, tone }: { label: string; value: string; tone?: number }) {
  return (
    <span className="inline-flex items-baseline gap-1.5">
      <span className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</span>
      <span className={`tabular font-medium ${tone == null ? "text-foreground" : pnlClass(tone)}`}>{value}</span>
    </span>
  );
}

function Divider() {
  return <span className="h-3 w-px bg-border/50" aria-hidden />;
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return <div className="px-1 text-[10px] font-medium uppercase tracking-[0.22em] text-muted-foreground/70">{children}</div>;
}

function Stat({ label, value, hint, tone, small }: { label: string; value: string; hint?: string; tone?: number | null; small?: boolean }) {
  return (
    <div className="rounded-xl border border-border/40 bg-card/35 px-4 py-3 transition hover:border-border/70 hover:bg-card/55">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className={`mt-1 ${small ? "text-sm" : "text-lg"} font-semibold tabular tracking-tight ${tone == null ? "text-foreground" : pnlClass(tone)}`}>
        {value}
      </div>
      {hint && <div className="mt-0.5 text-[10px] text-muted-foreground/70">{hint}</div>}
    </div>
  );
}
