"use client";

import type { OccurrenceLeaderboardEntry } from "@/lib/api";

type LeaderboardsProps = {
  meanReversion: OccurrenceLeaderboardEntry[];
  breakout: OccurrenceLeaderboardEntry[];
  minSample: number;
};

const GAIN = "oklch(0.55 0.20 148)";
const LOSS = "oklch(0.46 0.18 250)";

export function Leaderboards({ meanReversion, breakout, minSample }: LeaderboardsProps) {
  return (
    <section className="grid grid-cols-1 gap-px overflow-hidden rounded-2xl border border-border/40 bg-border/40 xl:grid-cols-2">
      <LeaderboardCard
        title="Mean-reversion"
        subtitle="Highest bounce rate per ticker × MA"
        rows={meanReversion}
        primary="bounce_pct"
        accent={GAIN}
        minSample={minSample}
      />
      <LeaderboardCard
        title="Breakout"
        subtitle="Highest break rate per ticker × MA"
        rows={breakout}
        primary="break_pct"
        accent={LOSS}
        minSample={minSample}
      />
    </section>
  );
}

function LeaderboardCard({
  title,
  subtitle,
  rows,
  primary,
  accent,
  minSample,
}: {
  title: string;
  subtitle: string;
  rows: OccurrenceLeaderboardEntry[];
  primary: "bounce_pct" | "break_pct";
  accent: string;
  minSample: number;
}) {
  return (
    <div className="relative bg-card/55 px-6 py-5">
      <span
        className="absolute inset-x-6 top-0 h-px"
        style={{ background: `linear-gradient(90deg, transparent, ${accent}, transparent)` }}
      />
      <div className="mb-4 flex items-baseline justify-between gap-3">
        <div>
          <h2 className="text-[13px] font-semibold tracking-tight">{title}</h2>
          <p className="mt-0.5 text-[11px] text-muted-foreground">{subtitle}</p>
        </div>
        <span className="text-[10px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
          n ≥ {minSample}
        </span>
      </div>

      {rows.length === 0 ? (
        <div className="rounded-md border border-dashed border-border/40 bg-card/20 py-8 text-center text-[12px] text-muted-foreground">
          No setups meet the sample threshold.
        </div>
      ) : (
        <ol className="divide-y divide-border/35">
          {rows.map((row, index) => (
            <li
              key={`${row.ticker}-${row.tf}-${row.ma}-${index}`}
              className="grid grid-cols-[28px_1fr_auto] items-center gap-3 py-2.5 transition first:pt-0 last:pb-0"
            >
              <span className="text-[12px] font-medium tabular text-muted-foreground/65">
                {String(index + 1).padStart(2, "0")}
              </span>
              <div className="min-w-0">
                <div className="flex flex-wrap items-baseline gap-x-2">
                  <span className="text-[13px] font-semibold tracking-tight">{row.ticker}</span>
                  <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                    {row.tf}
                  </span>
                  <span className="text-[11px] font-medium text-muted-foreground">{row.ma}</span>
                </div>
                <div className="mt-0.5 text-[11px] text-muted-foreground/85 tabular">
                  n = {row.total.toLocaleString("en-US")} · B {formatPct(row.bounce_pct)} · Bk{" "}
                  {formatPct(row.break_pct)} · F {formatPct(row.false_pct)}
                </div>
              </div>
              <div className="text-right">
                <div className="text-[20px] font-semibold leading-none tabular tracking-tight" style={{ color: accent }}>
                  {formatPct(row[primary])}
                </div>
              </div>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

function formatPct(value: number | null): string {
  return value == null ? "—" : `${value}%`;
}
