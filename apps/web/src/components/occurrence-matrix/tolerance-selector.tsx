"use client";

import { Gauge } from "lucide-react";

const TF_ORDER = ["2m", "5m", "15m", "1h", "D", "W"] as const;
const MA_DISPLAY_ORDER = ["EMA 9", "EMA 20", "SMA 50", "SMA 200", "VWAP"] as const;

type ToleranceSelectorProps = {
  tfs: string[];
  tolGrids?: Record<string, Record<string, Array<number | null>>>;
  gridSizes?: Record<string, number>;
  selectedTolIdx: Record<string, number>;
  onChange: (tf: string, idx: number) => void;
};

export function ToleranceSelector({
  tfs,
  tolGrids,
  gridSizes,
  selectedTolIdx,
  onChange,
}: ToleranceSelectorProps) {
  if (!tolGrids || !gridSizes) return null;

  const rows = TF_ORDER.filter((tf) => {
    if (!tfs.includes(tf)) return false;
    const size = gridSizes[tf] ?? 1;
    return size > 1;
  });

  if (rows.length === 0) return null;

  return (
    <section className="overflow-hidden rounded-xl border border-border/60 bg-card/35 shadow-lg shadow-black/5 backdrop-blur-sm">
      <div className="flex items-center gap-2 border-b border-border/45 bg-card/25 px-4 py-2.5">
        <Gauge className="h-3.5 w-3.5 text-primary/80" />
        <span className="text-[10px] font-semibold uppercase tracking-[0.22em] text-muted-foreground">
          Tolerance grid
        </span>
        <span className="ml-auto text-[10px] uppercase tracking-[0.18em] text-muted-foreground/70">
          Baseline highlighted · click to flip
        </span>
      </div>
      <div className="flex flex-col gap-2 p-4">
        {rows.map((tf) => {
          const grid = tolGrids[tf] ?? {};
          const size = gridSizes[tf] ?? 1;
          const baselineIdx = Math.floor(size / 2);
          const currentIdx = selectedTolIdx[tf] ?? baselineIdx;

          return (
            <div key={tf} className="flex items-center gap-3">
              <span className="w-10 shrink-0 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                {tf}
              </span>
              <div className="flex flex-wrap gap-1.5">
                {Array.from({ length: size }).map((_, idx) => {
                  const label = formatChipLabel(grid, idx);
                  const isActive = idx === currentIdx;
                  const isBaseline = idx === baselineIdx;
                  return (
                    <button
                      key={idx}
                      type="button"
                      aria-pressed={isActive}
                      onClick={() => onChange(tf, idx)}
                      className={chipClass(isActive, isBaseline)}
                      title={tooltipFor(grid, idx)}
                    >
                      {label}
                      {isBaseline && (
                        <span className="ml-1 text-[9px] uppercase tracking-[0.12em] opacity-70">
                          base
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function uniqueValuesAtIdx(grid: Record<string, Array<number | null>>, idx: number): number[] {
  const seen = new Set<number>();
  for (const ma of MA_DISPLAY_ORDER) {
    const series = grid[ma];
    if (!series) continue;
    const v = series[idx];
    if (typeof v === "number" && v > 0) seen.add(v);
  }
  return Array.from(seen).sort((a, b) => a - b);
}

function formatChipLabel(grid: Record<string, Array<number | null>>, idx: number): string {
  const vals = uniqueValuesAtIdx(grid, idx);
  if (vals.length === 0) return "—";
  if (vals.length === 1) return `±${formatPct(vals[0])}%`;
  return `±${formatPct(vals[0])}–${formatPct(vals[vals.length - 1])}%`;
}

function tooltipFor(grid: Record<string, Array<number | null>>, idx: number): string {
  const parts: string[] = [];
  for (const ma of MA_DISPLAY_ORDER) {
    const series = grid[ma];
    if (!series) continue;
    const v = series[idx];
    if (v === null || v === undefined || v <= 0) {
      parts.push(`${ma}: skip`);
    } else {
      parts.push(`${ma}: ±${formatPct(v)}%`);
    }
  }
  return parts.join(" · ");
}

function formatPct(value: number): string {
  if (Number.isInteger(value * 100)) return value.toFixed(2);
  return value.toString();
}

function chipClass(active: boolean, baseline: boolean): string {
  if (active) {
    return "inline-flex h-8 items-center rounded-md border border-primary/65 bg-primary px-3 text-[11px] font-semibold text-primary-foreground shadow-md shadow-primary/25 transition active:scale-95";
  }
  const baseStyles =
    "inline-flex h-8 items-center rounded-md border px-3 text-[11px] font-semibold transition hover:border-primary/40 hover:bg-card/70 hover:text-foreground active:scale-95";
  if (baseline) {
    return `${baseStyles} border-primary/35 bg-primary/10 text-foreground`;
  }
  return `${baseStyles} border-border/50 bg-background/35 text-muted-foreground`;
}
