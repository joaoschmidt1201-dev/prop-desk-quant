"use client";

import { Crown, Medal, Target, TrendingUp, Zap } from "lucide-react";
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
        subtitle="Highest bounce% per (ticker × MA)"
        icon={<Target className="h-4 w-4" />}
        tone="gain"
        rows={meanReversion}
        primary="bounce_pct"
        primaryLabel="Bounce%"
        minSample={minSample}
      />
      <LeaderboardCard
        title="Top 5 Breakout / Trending Setups"
        subtitle="Highest break% per (ticker × MA)"
        icon={<Zap className="h-4 w-4" />}
        tone="loss"
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
  subtitle,
  icon,
  tone,
  rows,
  primary,
  primaryLabel,
  minSample,
}: {
  title: string;
  subtitle: string;
  icon: ReactNode;
  tone: "gain" | "loss";
  rows: OccurrenceLeaderboardEntry[];
  primary: "bounce_pct" | "break_pct";
  primaryLabel: string;
  minSample: number;
}) {
  const accent =
    tone === "gain"
      ? { color: "var(--gain)", glow: "oklch(0.78 0.18 145 / 0.18)" }
      : { color: "var(--loss)", glow: "oklch(0.70 0.22 25 / 0.18)" };

  return (
    <section className="group relative overflow-hidden rounded-xl border border-border/60 bg-gradient-to-b from-card/65 to-card/30 shadow-xl shadow-black/10 backdrop-blur-sm">
      <div
        className="pointer-events-none absolute -top-12 right-0 h-32 w-32 rounded-full opacity-40 blur-3xl"
        style={{ backgroundColor: accent.glow }}
      />
      <div className="relative flex items-start justify-between gap-3 border-b border-border/50 px-5 py-4">
        <div className="flex items-start gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg" style={{ backgroundColor: accent.glow, color: accent.color }}>
            {icon}
          </div>
          <div>
            <h2 className="text-sm font-semibold tracking-tight">{title}</h2>
            <p className="mt-0.5 text-[11px] text-muted-foreground">{subtitle}</p>
          </div>
        </div>
        <span className="rounded-md border border-border/50 bg-background/40 px-2 py-1 text-[10px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
          n ≥ {minSample}
        </span>
      </div>
      <div className="p-4">
        {rows.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border/45 bg-card/20 p-8 text-center text-xs text-muted-foreground">
            <TrendingUp className="mx-auto mb-2 h-5 w-5 opacity-50" />
            No setups meet the sample threshold for the current filters.
          </div>
        ) : (
          <ol className="space-y-2">
            {rows.map((row, index) => (
              <LeaderRow
                key={`${row.ticker}-${row.tf}-${row.ma}-${index}`}
                rank={index + 1}
                row={row}
                primary={primary}
                primaryLabel={primaryLabel}
                accentColor={accent.color}
              />
            ))}
          </ol>
        )}
      </div>
    </section>
  );
}

function LeaderRow({
  rank,
  row,
  primary,
  primaryLabel,
  accentColor,
}: {
  rank: number;
  row: OccurrenceLeaderboardEntry;
  primary: "bounce_pct" | "break_pct";
  primaryLabel: string;
  accentColor: string;
}) {
  const rankInfo = rankAccent(rank);

  return (
    <li
      className="group/row relative grid grid-cols-[44px_1fr_auto] items-center gap-3 overflow-hidden rounded-lg border border-border/45 bg-background/30 px-3 py-2.5 transition hover:border-border/70 hover:bg-background/55"
    >
      {rank === 1 && (
        <div
          className="pointer-events-none absolute inset-y-0 left-0 w-1"
          style={{ backgroundColor: rankInfo.color }}
        />
      )}
      <div className="flex items-center justify-center">
        <div
          className="relative flex h-9 w-9 items-center justify-center rounded-lg text-[12px] font-bold tabular"
          style={{
            backgroundColor: rankInfo.bg,
            color: rankInfo.color,
            boxShadow: rank <= 3 ? `0 0 0 1px ${rankInfo.color}40` : undefined,
          }}
        >
          {rank <= 3 ? (
            rank === 1 ? (
              <Crown className="h-4 w-4" />
            ) : (
              <Medal className="h-4 w-4" />
            )
          ) : (
            rank
          )}
        </div>
      </div>
      <div className="min-w-0">
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
          <span className="text-sm font-semibold tracking-tight">{row.ticker}</span>
          <span className="rounded bg-foreground/8 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            {row.tf}
          </span>
          <span className="rounded bg-foreground/8 px-1.5 py-0.5 text-[10px] font-semibold text-muted-foreground">
            {row.ma}
          </span>
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] text-muted-foreground tabular">
          <span>
            n=<span className="font-semibold text-foreground/80">{row.total.toLocaleString("en-US")}</span>
          </span>
          <Dot />
          <span className="flex items-center gap-1">
            <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: "var(--gain)" }} />
            B {formatPct(row.bounce_pct)}
          </span>
          <Dot />
          <span className="flex items-center gap-1">
            <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: "var(--loss)" }} />
            Bk {formatPct(row.break_pct)}
          </span>
          <Dot />
          <span className="flex items-center gap-1">
            <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: "var(--warning)" }} />
            F {formatPct(row.false_pct)}
          </span>
        </div>
      </div>
      <div className="text-right">
        <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
          {primaryLabel}
        </div>
        <div className="text-2xl font-bold tabular leading-none" style={{ color: accentColor }}>
          {formatPct(row[primary])}
        </div>
      </div>
    </li>
  );
}

function Dot() {
  return <span className="text-border/60">·</span>;
}

function rankAccent(rank: number): { bg: string; color: string } {
  if (rank === 1)
    return { bg: "oklch(0.82 0.16 90 / 0.18)", color: "oklch(0.82 0.16 90)" };
  if (rank === 2)
    return { bg: "oklch(0.78 0.02 250 / 0.18)", color: "oklch(0.78 0.02 250)" };
  if (rank === 3)
    return { bg: "oklch(0.66 0.12 50 / 0.18)", color: "oklch(0.66 0.12 50)" };
  return { bg: "oklch(0.30 0.02 250 / 0.5)", color: "oklch(0.78 0.02 250)" };
}

function formatPct(value: number | null): string {
  return value == null ? "—" : `${value}%`;
}
