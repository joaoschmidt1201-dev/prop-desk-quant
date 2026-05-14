"use client";

import { MoveUpRight, TrendingDown, TrendingUp } from "lucide-react";
import type { ReactNode } from "react";
import type { OccurrenceLeaderboardEntry } from "@/lib/api";

type LeaderboardsProps = {
  meanReversion: OccurrenceLeaderboardEntry[];
  breakout: OccurrenceLeaderboardEntry[];
  minSample: number;
};

export function Leaderboards({ meanReversion, breakout, minSample }: LeaderboardsProps) {
  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
      <LeaderboardCard
        title="Top 5 Mean-Reversion Setups"
        icon={<TrendingUp className="h-4 w-4 text-[var(--gain)]" />}
        rows={meanReversion}
        primary="bounce_pct"
        primaryLabel="Bounce%"
        minSample={minSample}
      />
      <LeaderboardCard
        title="Top 5 Breakout / Trending Setups"
        icon={<TrendingDown className="h-4 w-4 text-[var(--warning)]" />}
        rows={breakout}
        primary="break_pct"
        primaryLabel="Break%"
        minSample={minSample}
      />
    </div>
  );
}

function LeaderboardCard({
  title,
  icon,
  rows,
  primary,
  primaryLabel,
  minSample,
}: {
  title: string;
  icon: ReactNode;
  rows: OccurrenceLeaderboardEntry[];
  primary: "bounce_pct" | "break_pct";
  primaryLabel: string;
  minSample: number;
}) {
  return (
    <section className="rounded-lg border border-border/60 bg-gradient-to-b from-card/70 to-card/35 p-5 shadow-2xl shadow-black/10">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          {icon}
          <h2 className="text-sm font-semibold tracking-tight">{title}</h2>
        </div>
        <span className="rounded-md border border-border/50 bg-background/35 px-2 py-1 text-[10px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
          n &gt;= {minSample}
        </span>
      </div>
      {rows.length === 0 ? (
        <div className="rounded-md border border-dashed border-border/50 bg-card/20 p-6 text-center text-xs text-muted-foreground">
          No setups meet the sample threshold.
        </div>
      ) : (
        <div className="space-y-2">
          {rows.map((row, index) => (
            <div
              key={`${row.ticker}-${row.tf}-${row.ma}-${index}`}
              className="grid grid-cols-[36px_1fr_auto] items-center gap-3 rounded-md border border-border/45 bg-background/25 px-3 py-2"
            >
              <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary/15 text-[11px] font-semibold text-primary">
                {index + 1}
              </div>
              <div className="min-w-0">
                <div className="flex flex-wrap items-baseline gap-2">
                  <span className="text-sm font-semibold">{row.ticker}</span>
                  <span className="text-xs text-muted-foreground">{row.tf}</span>
                  <span className="text-xs text-muted-foreground">{row.ma}</span>
                </div>
                <div className="mt-0.5 text-[11px] text-muted-foreground">
                  n={row.total} | Bounce {formatPct(row.bounce_pct)} | Break {formatPct(row.break_pct)}
                </div>
              </div>
              <div className="flex items-center gap-1.5 text-right">
                <div>
                  <div className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">{primaryLabel}</div>
                  <div className="text-lg font-semibold tabular text-[#f3c969]">{formatPct(row[primary])}</div>
                </div>
                <MoveUpRight className="h-3.5 w-3.5 text-muted-foreground/70" />
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function formatPct(value: number | null): string {
  return value == null ? "n/a" : `${value}%`;
}
