"use client";

import { Clock, FolderTree, Palette, SlidersHorizontal, TrendingUp } from "lucide-react";
import type { ReactNode } from "react";
import type { OccurrenceCategory } from "@/lib/api";

export type OccurrenceMetricKey = "bounce_pct" | "break_pct" | "false_pct" | "T";

const METRIC_OPTIONS: Array<{ key: OccurrenceMetricKey; label: string }> = [
  { key: "bounce_pct", label: "Bounce%" },
  { key: "break_pct", label: "Break%" },
  { key: "false_pct", label: "False%" },
  { key: "T", label: "Events" },
];

type FiltersProps = {
  tfs: string[];
  expectedTfs: string[];
  selectedTf: string;
  onTfChange: (tf: string) => void;
  selectedMetric: OccurrenceMetricKey;
  onMetricChange: (metric: OccurrenceMetricKey) => void;
  categories: OccurrenceCategory[];
  selectedCategory: string;
  onCategoryChange: (category: string) => void;
  mas: string[];
  selectedMas: string[];
  onMaToggle: (ma: string) => void;
  onAllMas: () => void;
};

export function OccurrenceFilters({
  tfs,
  expectedTfs,
  selectedTf,
  onTfChange,
  selectedMetric,
  onMetricChange,
  categories,
  selectedCategory,
  onCategoryChange,
  mas,
  selectedMas,
  onMaToggle,
  onAllMas,
}: FiltersProps) {
  return (
    <section className="overflow-hidden rounded-xl border border-border/60 bg-card/35 shadow-lg shadow-black/5 backdrop-blur-sm">
      <div className="flex items-center gap-2 border-b border-border/45 bg-card/25 px-4 py-2.5">
        <SlidersHorizontal className="h-3.5 w-3.5 text-primary/80" />
        <span className="text-[10px] font-semibold uppercase tracking-[0.22em] text-muted-foreground">
          Filters
        </span>
      </div>
      <div className="grid gap-4 p-4 xl:grid-cols-[0.8fr_1fr_1.5fr_1.4fr]">
        <ChipGroup icon={<Clock className="h-3 w-3" />} label="Timeframe">
          {expectedTfs.map((tf) => {
            const loaded = tfs.includes(tf);
            return (
              <button
                key={tf}
                type="button"
                disabled={!loaded}
                aria-pressed={selectedTf === tf}
                onClick={() => onTfChange(tf)}
                className={chipClass(selectedTf === tf, !loaded)}
                title={loaded ? `${tf} loaded` : `${tf} snapshot not loaded`}
              >
                {tf}
              </button>
            );
          })}
        </ChipGroup>

        <ChipGroup icon={<Palette className="h-3 w-3" />} label="Heat color">
          {METRIC_OPTIONS.map((option) => (
            <button
              key={option.key}
              type="button"
              aria-pressed={selectedMetric === option.key}
              onClick={() => onMetricChange(option.key)}
              className={chipClass(selectedMetric === option.key)}
            >
              {option.label}
            </button>
          ))}
        </ChipGroup>

        <ChipGroup icon={<FolderTree className="h-3 w-3" />} label="Category">
          <button
            type="button"
            aria-pressed={selectedCategory === "All"}
            onClick={() => onCategoryChange("All")}
            className={chipClass(selectedCategory === "All")}
          >
            All
          </button>
          {categories.map((category) => (
            <button
              key={category.name}
              type="button"
              aria-pressed={selectedCategory === category.name}
              onClick={() => onCategoryChange(category.name)}
              className={chipClass(selectedCategory === category.name)}
            >
              {displayCategoryShort(category.name)}
            </button>
          ))}
        </ChipGroup>

        <ChipGroup icon={<TrendingUp className="h-3 w-3" />} label="Moving average">
          <button
            type="button"
            aria-pressed={selectedMas.length === mas.length}
            onClick={onAllMas}
            className={chipClass(selectedMas.length === mas.length)}
          >
            All MAs
          </button>
          {mas.map((ma) => (
            <button
              key={ma}
              type="button"
              aria-pressed={selectedMas.includes(ma)}
              onClick={() => onMaToggle(ma)}
              className={chipClass(selectedMas.includes(ma))}
            >
              {ma}
            </button>
          ))}
        </ChipGroup>
      </div>
    </section>
  );
}

function ChipGroup({
  icon,
  label,
  children,
}: {
  icon: ReactNode;
  label: string;
  children: ReactNode;
}) {
  return (
    <div>
      <div className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.2em] text-muted-foreground/85">
        <span className="text-primary/70">{icon}</span>
        {label}
      </div>
      <div className="flex flex-wrap gap-1.5">{children}</div>
    </div>
  );
}

function displayCategoryShort(name: string): string {
  const labels: Record<string, string> = {
    "Indices/Futures": "Indices",
    FX: "Forex",
    "QQQ Top 10": "Stocks",
    "Commodities/ETFs": "Commodities",
  };
  return labels[name] ?? name;
}

function chipClass(active: boolean, disabled = false): string {
  if (disabled) {
    return "h-8 cursor-not-allowed rounded-md border border-border/25 bg-background/15 px-3 text-[11px] font-semibold text-muted-foreground/35 line-through decoration-1";
  }
  if (active) {
    return "h-8 rounded-md border border-primary/65 bg-primary px-3 text-[11px] font-semibold text-primary-foreground shadow-md shadow-primary/25 transition active:scale-95";
  }
  return "h-8 rounded-md border border-border/50 bg-background/35 px-3 text-[11px] font-semibold text-muted-foreground transition hover:border-primary/40 hover:bg-card/70 hover:text-foreground active:scale-95";
}
