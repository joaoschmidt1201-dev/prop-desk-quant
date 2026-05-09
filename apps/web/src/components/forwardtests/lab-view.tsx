"use client";

import { useQuery } from "@tanstack/react-query";
import { Activity, DollarSign, Flame, Radar, Sparkles, Zap } from "lucide-react";
import { api } from "@/lib/api";
import { fmtMoney, fmtNum, fmtPct, pnlClass } from "@/lib/format";
import { DASHBOARD_REFETCH_INTERVAL_MS } from "@/lib/refresh";
import { PerformanceMatrix } from "./performance-matrix";
import { StructureComparison } from "./structure-comparison";
import { TopSetups } from "./top-setups";
import { RecentActivity } from "./recent-activity";

export function LabView() {
  const { data, isLoading } = useQuery({
    queryKey: ["forwardtests", "lab"],
    queryFn: () => api.forwardtestsLab(),
    refetchInterval: DASHBOARD_REFETCH_INTERVAL_MS,
  });

  return (
    <main className="mx-auto w-full max-w-[1600px] flex-1 px-8 py-8">
      <Header />

      {isLoading || !data ? (
        <SkeletonLayout />
      ) : (
        <div className="space-y-6">
          <Hero
            nStrategies={data.hero.n_strategies}
            nOpen={data.hero.n_trades_open}
            nClosed={data.hero.n_trades_closed}
            totalPnl={data.hero.total_pnl}
            globalWinRate={data.hero.global_win_rate}
            medianDit={data.hero.median_dit_to_50mp}
          />

          <PerformanceMatrix cells={data.matrix} />

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
            <div className="xl:col-span-2">
              <StructureComparison groups={data.structure_comparison} />
            </div>
            <RecentActivity entries={data.recent_activity} />
          </div>

          <TopSetups
            topWinrate={data.leaderboards.top_winrate}
            topPnl={data.leaderboards.top_pnl}
            topSpeed={data.leaderboards.top_speed}
          />
        </div>
      )}
    </main>
  );
}

function Header() {
  return (
    <div className="mb-8 flex items-end justify-between">
      <div>
        <div className="mb-2 inline-flex items-center gap-2 rounded-full border border-primary/25 bg-primary/10 px-3 py-1 text-[11px] font-medium uppercase tracking-[0.22em] text-primary">
          <Radar className="h-3.5 w-3.5" />
          Forward Lab
        </div>
        <h1 className="text-2xl font-semibold tracking-tight">Forward tests</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
          Cross-strategy view over every OptionStrat-fed forward trade. Hunt for the (family · structure × ticker) combos worth scaling into live with CZ.
        </p>
      </div>
      <div className="hidden items-center gap-2 text-xs text-muted-foreground sm:flex">
        <span className="h-1.5 w-1.5 rounded-full bg-[var(--gain)]" />
        <span>auto-grouped from <code className="rounded bg-card/60 px-1.5 py-0.5 text-[10px]">db_cria</code> + <code className="rounded bg-card/60 px-1.5 py-0.5 text-[10px]">db_robots</code></span>
      </div>
    </div>
  );
}

type HeroProps = {
  nStrategies: number;
  nOpen: number;
  nClosed: number;
  totalPnl: number;
  globalWinRate: number | null;
  medianDit: number | null;
};

function Hero({ nStrategies, nOpen, nClosed, totalPnl, globalWinRate, medianDit }: HeroProps) {
  return (
    <section className="grid grid-cols-2 gap-3 lg:grid-cols-5">
      <HeroBlock
        icon={<Sparkles className="h-3.5 w-3.5" />}
        label="Strategies tracked"
        value={String(nStrategies)}
        sub={`${nOpen} open · ${nClosed} closed`}
      />
      <HeroBlock
        icon={<DollarSign className="h-3.5 w-3.5" />}
        label="Total P&L"
        value={fmtMoney(totalPnl)}
        valueClass={pnlClass(totalPnl)}
        sub="open + closed across the lab"
      />
      <HeroBlock
        icon={<Flame className="h-3.5 w-3.5" />}
        label="Global win rate"
        value={globalWinRate != null ? fmtPct(globalWinRate) : "—"}
        sub={nClosed > 0 ? `from ${nClosed} closed` : "needs closed trades"}
      />
      <HeroBlock
        icon={<Zap className="h-3.5 w-3.5" />}
        label="Median DIT → 50% MP"
        value={medianDit != null ? `${fmtNum(medianDit)}d` : "—"}
        sub="how fast credits decay"
      />
      <HeroBlock
        icon={<Activity className="h-3.5 w-3.5" />}
        label="Status"
        value={nStrategies === 0 ? "Awaiting" : "Live"}
        sub="real OptionStrat marks"
      />
    </section>
  );
}

type HeroBlockProps = {
  icon: React.ReactNode;
  label: string;
  value: string;
  sub: string;
  valueClass?: string;
};

function HeroBlock({ icon, label, value, sub, valueClass }: HeroBlockProps) {
  return (
    <div className="rounded-2xl border border-border/60 bg-gradient-to-b from-card/70 to-card/35 p-4 shadow-2xl shadow-black/10">
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
        <span className="text-foreground/70">{icon}</span>
        {label}
      </div>
      <div className={`mt-2 text-2xl font-semibold tabular ${valueClass ?? ""}`}>{value}</div>
      <div className="mt-1 text-[11px] text-muted-foreground">{sub}</div>
    </div>
  );
}

function SkeletonLayout() {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        {[0, 1, 2, 3, 4].map((i) => (
          <div key={i} className="h-[110px] animate-pulse rounded-2xl border border-border/60 bg-card/30" />
        ))}
      </div>
      <div className="h-[280px] animate-pulse rounded-2xl border border-border/60 bg-card/30" />
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <div className="h-[260px] animate-pulse rounded-2xl border border-border/60 bg-card/30 xl:col-span-2" />
        <div className="h-[260px] animate-pulse rounded-2xl border border-border/60 bg-card/30" />
      </div>
      <div className="h-[260px] animate-pulse rounded-2xl border border-border/60 bg-card/30" />
    </div>
  );
}
