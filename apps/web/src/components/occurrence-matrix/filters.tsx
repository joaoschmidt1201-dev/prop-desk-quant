"use client";

import { SlidersHorizontal } from "lucide-react";
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
    <section className="rounded-lg border border-border/60 bg-card/35 p-4">
      <div className="mb-3 flex items-center gap-2 text-[10px] font-medium uppercase tracking-[0.22em] text-muted-foreground">
        <SlidersHorizontal className="h-3.5 w-3.5" />
        Filters
      </div>
      <div className="grid gap-4 xl:grid-cols-[1fr_1fr_1.5fr_1.3fr]">
        <ChipGroup label="Timeframe">
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

        <ChipGroup label="Heat color">
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

        <ChipGroup label="Category">
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
              {category.name}
            </button>
          ))}
        </ChipGroup>

        <ChipGroup label="Moving average">
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

function ChipGroup({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.2em] text-muted-foreground/75">
        {label}
      </div>
      <div className="flex flex-wrap gap-2">{children}</div>
    </div>
  );
}

function chipClass(active: boolean, disabled = false): string {
  if (disabled) {
    return "h-8 cursor-not-allowed rounded-md border border-border/30 bg-background/20 px-3 text-[11px] font-semibold text-muted-foreground/35";
  }
  return [
    "h-8 rounded-md border px-3 text-[11px] font-semibold transition",
    active
      ? "border-primary/60 bg-primary text-primary-foreground"
      : "border-border/50 bg-background/35 text-muted-foreground hover:border-primary/35 hover:bg-card/70 hover:text-foreground",
  ].join(" ");
}
