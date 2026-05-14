"use client";

import type { ReactNode } from "react";
import type { OccurrenceCategory } from "@/lib/api";

export type OccurrenceMetricKey = "bounce_pct" | "break_pct" | "false_pct" | "T";

const METRIC_OPTIONS: Array<{ key: OccurrenceMetricKey; label: string }> = [
  { key: "bounce_pct", label: "Bounce %" },
  { key: "break_pct", label: "Break %" },
  { key: "false_pct", label: "False %" },
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
    <section className="flex flex-col gap-5 xl:flex-row xl:flex-wrap xl:items-start xl:gap-10">
      <Field label="Timeframe">
        {expectedTfs.map((tf) => {
          const loaded = tfs.includes(tf);
          return (
            <Pill
              key={tf}
              active={selectedTf === tf}
              disabled={!loaded}
              onClick={() => onTfChange(tf)}
              title={loaded ? `${tf} loaded` : `${tf} snapshot not loaded`}
            >
              {tf}
            </Pill>
          );
        })}
      </Field>

      <Field label="Metric">
        {METRIC_OPTIONS.map((option) => (
          <Pill
            key={option.key}
            active={selectedMetric === option.key}
            onClick={() => onMetricChange(option.key)}
          >
            {option.label}
          </Pill>
        ))}
      </Field>

      <Field label="Category">
        <Pill active={selectedCategory === "All"} onClick={() => onCategoryChange("All")}>
          All
        </Pill>
        {categories.map((category) => (
          <Pill
            key={category.name}
            active={selectedCategory === category.name}
            onClick={() => onCategoryChange(category.name)}
          >
            {displayCategoryShort(category.name)}
          </Pill>
        ))}
      </Field>

      <Field label="Moving average">
        <Pill active={selectedMas.length === mas.length} onClick={onAllMas}>
          All
        </Pill>
        {mas.map((ma) => (
          <Pill
            key={ma}
            active={selectedMas.includes(ma)}
            onClick={() => onMaToggle(ma)}
          >
            {ma}
          </Pill>
        ))}
      </Field>
    </section>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <div className="mb-2.5 text-[10px] font-medium uppercase tracking-[0.22em] text-muted-foreground/85">
        {label}
      </div>
      <div className="flex flex-wrap gap-1.5">{children}</div>
    </div>
  );
}

function Pill({
  active,
  disabled = false,
  onClick,
  children,
  title,
}: {
  active: boolean;
  disabled?: boolean;
  onClick: () => void;
  children: ReactNode;
  title?: string;
}) {
  if (disabled) {
    return (
      <button
        type="button"
        disabled
        title={title}
        className="h-8 cursor-not-allowed rounded-md border border-border/20 bg-transparent px-3 text-[11.5px] font-medium text-muted-foreground/30"
      >
        {children}
      </button>
    );
  }
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      aria-pressed={active}
      className={[
        "h-8 rounded-md border px-3 text-[11.5px] font-medium transition active:scale-[0.97]",
        active
          ? "border-foreground/85 bg-foreground text-background"
          : "border-border/40 bg-transparent text-muted-foreground hover:border-foreground/40 hover:text-foreground",
      ].join(" ")}
    >
      {children}
    </button>
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
