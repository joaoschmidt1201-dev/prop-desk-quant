"use client";

import { Crown, Layers, ListOrdered } from "lucide-react";
import { useMemo, useState } from "react";
import type { OccurrenceCategory, OccurrenceTopSetupEntry } from "@/lib/api";

type TopSetupsTableProps = {
  topSetups: Record<string, OccurrenceTopSetupEntry[]>;
  categories: OccurrenceCategory[];
  tickers: string[];
  minSample: number;
};

const ALL = "All";

export function TopSetupsTable({
  topSetups,
  categories,
  tickers,
  minSample,
}: TopSetupsTableProps) {
  const [selectedCategory, setSelectedCategory] = useState<string>(ALL);

  const visibleTickers = useMemo(() => {
    if (selectedCategory === ALL) return tickers;
    const cat = categories.find((c) => c.name === selectedCategory);
    return cat?.tickers ?? [];
  }, [selectedCategory, categories, tickers]);

  return (
    <section className="group relative overflow-hidden rounded-xl border border-border/60 bg-gradient-to-b from-card/65 to-card/30 shadow-xl shadow-black/10 backdrop-blur-sm">
      <div
        className="pointer-events-none absolute -top-12 right-0 h-32 w-32 rounded-full opacity-40 blur-3xl"
        style={{ backgroundColor: "oklch(0.78 0.18 145 / 0.18)" }}
      />
      <div className="relative flex items-start justify-between gap-3 border-b border-border/50 px-5 py-4">
        <div className="flex items-start gap-3">
          <div
            className="flex h-9 w-9 items-center justify-center rounded-lg"
            style={{
              backgroundColor: "oklch(0.78 0.18 145 / 0.18)",
              color: "var(--gain)",
            }}
          >
            <ListOrdered className="h-4 w-4" />
          </div>
          <div>
            <h2 className="text-sm font-semibold tracking-tight">
              Best 3 Setups per Underlying
            </h2>
            <p className="mt-0.5 text-[11px] text-muted-foreground">
              Top 3 (TF × MA) by Bounce% for each ticker
            </p>
          </div>
        </div>
        <span className="rounded-md border border-border/50 bg-background/40 px-2 py-1 text-[10px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
          n ≥ {minSample}
        </span>
      </div>

      <div className="border-b border-border/45 bg-card/20 px-4 py-3">
        <div className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.2em] text-muted-foreground/85">
          <Layers className="h-3 w-3 text-primary/70" />
          Category
        </div>
        <div className="flex flex-wrap gap-1.5">
          <CategoryChip
            label="All"
            active={selectedCategory === ALL}
            onClick={() => setSelectedCategory(ALL)}
          />
          {categories.map((cat) => (
            <CategoryChip
              key={cat.name}
              label={shortCategory(cat.name)}
              active={selectedCategory === cat.name}
              onClick={() => setSelectedCategory(cat.name)}
            />
          ))}
        </div>
      </div>

      <div className="p-4">
        {visibleTickers.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border/45 bg-card/20 p-8 text-center text-xs text-muted-foreground">
            No tickers in this category.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] table-fixed border-separate border-spacing-y-1.5">
              <thead>
                <tr>
                  <th className="w-[88px] px-3 pb-2 text-left text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                    Ticker
                  </th>
                  {[1, 2, 3].map((rank) => (
                    <th
                      key={rank}
                      className="px-2 pb-2 text-left text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground"
                    >
                      <span className="inline-flex items-center gap-1.5">
                        {rank === 1 && (
                          <Crown
                            className="h-3 w-3"
                            style={{ color: "oklch(0.82 0.16 90)" }}
                          />
                        )}
                        #{rank}
                      </span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {visibleTickers.map((ticker) => {
                  const setups = topSetups[ticker] ?? [];
                  return (
                    <tr key={ticker}>
                      <td className="rounded-l-lg border-y border-l border-border/45 bg-background/30 px-3 py-2.5 align-middle">
                        <span className="text-sm font-semibold tracking-tight">
                          {ticker}
                        </span>
                      </td>
                      {[0, 1, 2].map((idx) => {
                        const entry = setups[idx];
                        const isLast = idx === 2;
                        return (
                          <td
                            key={idx}
                            className={
                              "border-y border-border/45 bg-background/30 px-2 py-2 align-middle" +
                              (isLast ? " rounded-r-lg border-r" : "")
                            }
                          >
                            {entry ? (
                              <SetupCell entry={entry} rank={idx + 1} />
                            ) : (
                              <EmptyCell />
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}

function SetupCell({
  entry,
  rank,
}: {
  entry: OccurrenceTopSetupEntry;
  rank: number;
}) {
  const accent = rankColor(rank);
  return (
    <div className="grid grid-cols-[1fr_auto] items-center gap-2">
      <div className="min-w-0">
        <div className="flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5">
          <span className="rounded bg-foreground/8 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            {entry.tf}
          </span>
          <span className="rounded bg-foreground/8 px-1.5 py-0.5 text-[10px] font-semibold text-muted-foreground">
            {entry.ma}
          </span>
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px] text-muted-foreground tabular">
          <span>
            n=
            <span className="font-semibold text-foreground/80">
              {entry.total.toLocaleString("en-US")}
            </span>
          </span>
          <span className="flex items-center gap-0.5">
            <span
              className="h-1.5 w-1.5 rounded-full"
              style={{ backgroundColor: "var(--loss)" }}
            />
            {formatPct(entry.break_pct)}
          </span>
          <span className="flex items-center gap-0.5">
            <span
              className="h-1.5 w-1.5 rounded-full"
              style={{ backgroundColor: "var(--warning)" }}
            />
            {formatPct(entry.false_pct)}
          </span>
        </div>
      </div>
      <div className="text-right">
        <div className="text-xl font-bold tabular leading-none" style={{ color: accent }}>
          {formatPct(entry.bounce_pct)}
        </div>
      </div>
    </div>
  );
}

function EmptyCell() {
  return (
    <div className="flex h-full items-center justify-center text-[12px] text-muted-foreground/40">
      —
    </div>
  );
}

function CategoryChip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={
        active
          ? "h-8 rounded-md border border-primary/65 bg-primary px-3 text-[11px] font-semibold text-primary-foreground shadow-md shadow-primary/25 transition active:scale-95"
          : "h-8 rounded-md border border-border/50 bg-background/35 px-3 text-[11px] font-semibold text-muted-foreground transition hover:border-primary/40 hover:bg-card/70 hover:text-foreground active:scale-95"
      }
    >
      {label}
    </button>
  );
}

function shortCategory(name: string): string {
  const labels: Record<string, string> = {
    "Indices/Futures": "Indices",
    FX: "Forex",
    "QQQ Top 10": "Stocks",
    "Commodities/ETFs": "Commodities",
  };
  return labels[name] ?? name;
}

function rankColor(rank: number): string {
  if (rank === 1) return "var(--gain)";
  if (rank === 2) return "oklch(0.75 0.12 145)";
  return "oklch(0.68 0.08 145)";
}

function formatPct(value: number | null): string {
  return value == null ? "—" : `${value}%`;
}
