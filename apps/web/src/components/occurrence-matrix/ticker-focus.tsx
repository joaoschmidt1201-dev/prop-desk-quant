"use client";

import { Crown, ListOrdered, Medal, Target, Grid3X3 } from "lucide-react";
import type { CSSProperties } from "react";
import { useMemo, useState } from "react";
import type {
  OccurrenceMatrixPayload,
  OccurrenceMetric,
} from "@/lib/api";
import type { OccurrenceMetricKey } from "./filters";

type TickerFocusProps = {
  data: OccurrenceMatrixPayload;
};

type RankedLevel = {
  tf: string;
  ma: string;
  metric: OccurrenceMetric;
};

const METRIC_OPTIONS: Array<{ key: OccurrenceMetricKey; label: string }> = [
  { key: "bounce_pct", label: "Bounce%" },
  { key: "break_pct", label: "Break%" },
  { key: "false_pct", label: "False%" },
  { key: "T", label: "Events" },
];

export function TickerFocus({ data }: TickerFocusProps) {
  const [selectedTicker, setSelectedTicker] = useState<string>(
    () => data.tickers[0] ?? "",
  );
  const [selectedMetric, setSelectedMetric] =
    useState<OccurrenceMetricKey>("bounce_pct");

  // Guard: if the ticker vanished from a refetch, fall back to the first one.
  const ticker = data.tickers.includes(selectedTicker)
    ? selectedTicker
    : (data.tickers[0] ?? "");

  const ranked = useMemo<RankedLevel[]>(() => {
    const tickerData = data.data[ticker];
    if (!tickerData) return [];
    const rows: RankedLevel[] = [];
    for (const tf of data.tfs) {
      const tfData = tickerData[tf];
      if (!tfData) continue;
      for (const ma of data.mas) {
        const metric = tfData[ma];
        if (!metric || metric.T < data.min_sample) continue;
        rows.push({ tf, ma, metric });
      }
    }
    rows.sort((a, b) => {
      const av = a.metric.bounce_pct ?? -1;
      const bv = b.metric.bounce_pct ?? -1;
      if (bv !== av) return bv - av;
      if (b.metric.T !== a.metric.T) return b.metric.T - a.metric.T;
      if (a.tf !== b.tf) return a.tf < b.tf ? -1 : 1;
      return a.ma < b.ma ? -1 : 1;
    });
    return rows;
  }, [data, ticker]);

  return (
    <section className="overflow-hidden rounded-xl border border-border/60 bg-card/35 shadow-xl shadow-black/10 backdrop-blur-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/50 bg-gradient-to-r from-card/60 to-card/30 px-5 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/15 text-primary">
            <Target className="h-4 w-4" />
          </div>
          <div>
            <h2 className="text-sm font-semibold tracking-tight">Single Ticker Focus</h2>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Pick a ticker to see its best-behaving levels across every timeframe.
            </p>
          </div>
        </div>
        <TickerPicker
          data={data}
          value={ticker}
          onChange={setSelectedTicker}
        />
      </div>

      <div className="grid gap-5 p-4 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <RankingCard ranked={ranked} minSample={data.min_sample} ticker={ticker} />
        <MatrixCard
          data={data}
          ticker={ticker}
          selectedMetric={selectedMetric}
          onMetricChange={setSelectedMetric}
        />
      </div>
    </section>
  );
}

function TickerPicker({
  data,
  value,
  onChange,
}: {
  data: OccurrenceMatrixPayload;
  value: string;
  onChange: (ticker: string) => void;
}) {
  return (
    <label className="flex items-center gap-2 rounded-md border border-border/50 bg-background/40 px-3 py-1.5">
      <span className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
        Ticker
      </span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="min-w-[120px] cursor-pointer bg-transparent text-sm font-semibold text-foreground outline-none"
      >
        {data.categories.map((category) => (
          <optgroup key={category.name} label={category.name} className="bg-background text-foreground">
            {category.tickers.map((ticker) => (
              <option key={ticker} value={ticker} className="bg-background text-foreground">
                {ticker}
              </option>
            ))}
          </optgroup>
        ))}
      </select>
    </label>
  );
}

function RankingCard({
  ranked,
  minSample,
  ticker,
}: {
  ranked: RankedLevel[];
  minSample: number;
  ticker: string;
}) {
  return (
    <div className="overflow-hidden rounded-lg border border-border/40 bg-background/15">
      <div className="flex items-center justify-between gap-3 border-b border-border/35 bg-card/20 px-4 py-2.5">
        <div className="flex items-center gap-2">
          <ListOrdered className="h-3.5 w-3.5 text-muted-foreground/75" />
          <h3 className="text-sm font-semibold">
            Best Levels — {ticker || "—"}
          </h3>
        </div>
        <span className="rounded-md border border-border/40 bg-background/25 px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
          by Bounce% · n ≥ {minSample}
        </span>
      </div>
      {ranked.length === 0 ? (
        <div className="p-8 text-center text-xs text-muted-foreground">
          No level reaches the minimum sample (n ≥ {minSample}) for this ticker yet.
        </div>
      ) : (
        <ol className="divide-y divide-border/30">
          {ranked.map((row, idx) => (
            <RankingRow key={`${row.tf}-${row.ma}`} row={row} rank={idx + 1} />
          ))}
        </ol>
      )}
    </div>
  );
}

function RankingRow({ row, rank }: { row: RankedLevel; rank: number }) {
  const { tf, ma, metric } = row;
  const accent = rankColor(rank);
  return (
    <li className="flex items-center gap-3 px-4 py-2.5 transition hover:bg-primary/[0.04]">
      <span
        className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-[11px] font-bold tabular"
        style={{ backgroundColor: "oklch(0.28 0.03 250)", color: accent }}
      >
        {rank <= 3 ? <RankIcon rank={rank} /> : rank}
      </span>
      <div className="flex min-w-0 flex-1 items-center gap-1.5">
        <span className="rounded bg-foreground/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          {tf}
        </span>
        <span className="rounded bg-foreground/10 px-1.5 py-0.5 text-[10px] font-semibold text-muted-foreground">
          {ma}
        </span>
        {metric.low_sample && (
          <span className="text-[9px] font-medium uppercase tracking-wide text-[var(--warning)]/80">
            low n
          </span>
        )}
      </div>
      <div className="flex items-center gap-3 text-[10px] text-muted-foreground tabular">
        <span>
          n=<span className="font-semibold text-foreground/80">{metric.T.toLocaleString("en-US")}</span>
        </span>
        <span className="flex items-center gap-0.5">
          <Dot color="var(--loss)" />
          {formatPct(metric.break_pct)}
        </span>
        <span className="flex items-center gap-0.5">
          <Dot color="var(--warning)" />
          {formatPct(metric.false_pct)}
        </span>
      </div>
      <div className="w-14 text-right text-xl font-bold tabular leading-none" style={{ color: accent }}>
        {formatPct(metric.bounce_pct)}
      </div>
    </li>
  );
}

function MatrixCard({
  data,
  ticker,
  selectedMetric,
  onMetricChange,
}: {
  data: OccurrenceMatrixPayload;
  ticker: string;
  selectedMetric: OccurrenceMetricKey;
  onMetricChange: (metric: OccurrenceMetricKey) => void;
}) {
  const tickerData = data.data[ticker];
  return (
    <div className="overflow-hidden rounded-lg border border-border/40 bg-background/15">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/35 bg-card/20 px-4 py-2.5">
        <div className="flex items-center gap-2">
          <Grid3X3 className="h-3.5 w-3.5 text-muted-foreground/75" />
          <h3 className="text-sm font-semibold">Timeframe × Level</h3>
        </div>
        <div className="flex flex-wrap gap-1">
          {METRIC_OPTIONS.map((option) => (
            <button
              key={option.key}
              type="button"
              aria-pressed={selectedMetric === option.key}
              onClick={() => onMetricChange(option.key)}
              className={
                selectedMetric === option.key
                  ? "h-7 rounded-md border border-primary/65 bg-primary px-2.5 text-[10px] font-semibold text-primary-foreground transition active:scale-95"
                  : "h-7 rounded-md border border-border/50 bg-background/35 px-2.5 text-[10px] font-semibold text-muted-foreground transition hover:border-primary/40 hover:text-foreground active:scale-95"
              }
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>
      <div className="overflow-auto">
        <table className="w-full min-w-[520px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-border/40 bg-background/35">
              <th className="sticky left-0 z-10 w-[64px] bg-background/95 px-3 py-2.5 text-left text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground backdrop-blur-sm">
                TF
              </th>
              {data.mas.map((ma) => (
                <th
                  key={ma}
                  className="min-w-[92px] px-2 py-2.5 text-center text-[10px] font-semibold uppercase tracking-[0.14em] text-foreground/85"
                >
                  {ma}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.tfs.map((tf) => (
              <tr key={tf} className="border-b border-border/30 last:border-b-0">
                <td className="sticky left-0 z-10 bg-background/95 px-3 py-2 text-xs font-semibold text-foreground backdrop-blur-sm">
                  {tf}
                </td>
                {data.mas.map((ma) => (
                  <MatrixCell
                    key={`${tf}-${ma}`}
                    metric={tickerData?.[tf]?.[ma] ?? null}
                    selectedMetric={selectedMetric}
                  />
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function MatrixCell({
  metric,
  selectedMetric,
}: {
  metric: OccurrenceMetric | null;
  selectedMetric: OccurrenceMetricKey;
}) {
  if (!metric || metric.T === 0) {
    return (
      <td
        className="h-[52px] min-w-[92px] border-l border-border/20 px-1.5 text-center"
        style={{ backgroundColor: "oklch(0.22 0.018 250 / 0.45)" }}
      >
        <span className="text-[11px] font-medium text-muted-foreground/55">—</span>
      </td>
    );
  }

  const bg = heatBands(metricValue(metric, selectedMetric), selectedMetric);
  const style: CSSProperties = metric.low_sample
    ? { backgroundColor: bg, boxShadow: "inset 0 0 0 1px oklch(1 0 0 / 0.25)" }
    : { backgroundColor: bg };
  const tooltip = [
    `Total events: ${metric.T}`,
    `Bounce: ${metric.B} (${formatPct(metric.bounce_pct)})`,
    `Break:  ${metric.Bk} (${formatPct(metric.break_pct)})`,
    `False:  ${metric.F} (${formatPct(metric.false_pct)})`,
    metric.low_sample ? "[low sample]" : "",
  ]
    .filter(Boolean)
    .join("\n");

  return (
    <td
      className="h-[52px] min-w-[92px] cursor-help border-l border-border/20 px-1.5 text-center text-white"
      style={style}
      title={tooltip}
    >
      <div className="text-[15px] font-bold leading-none tabular">
        {formatMetric(metric, selectedMetric)}
      </div>
      <div className="mt-0.5 text-[9px] font-medium text-white/70 tabular">
        n={metric.T.toLocaleString("en-US")}
      </div>
    </td>
  );
}

function Dot({ color }: { color: string }) {
  return <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: color }} />;
}

function RankIcon({ rank }: { rank: number }) {
  if (rank === 1) return <Crown className="h-3.5 w-3.5" />;
  if (rank === 2) return <Medal className="h-3.5 w-3.5" />;
  return <Medal className="h-3 w-3" />;
}

function rankColor(rank: number): string {
  if (rank === 1) return "oklch(0.82 0.16 90)";
  if (rank === 2) return "var(--gain)";
  if (rank === 3) return "oklch(0.75 0.12 145)";
  return "var(--foreground)";
}

// ─── palette (mirrors the global Heatmap thresholds in matrix-heatmap.tsx) ───
const COLOR_RED = "oklch(0.45 0.18 25)";
const COLOR_NEUTRAL = "oklch(0.32 0.025 250)";
const COLOR_GREEN = "oklch(0.52 0.20 148)";
const COLOR_BLUE_SOFT = "oklch(0.36 0.10 250)";
const COLOR_BLUE = "oklch(0.46 0.18 250)";
const COLOR_BLUE_STRONG = "oklch(0.54 0.22 250)";

function heatBands(value: number | null, selectedMetric: OccurrenceMetricKey): string {
  if (value == null) return COLOR_NEUTRAL;
  if (selectedMetric === "T") {
    if (value < 50) return COLOR_NEUTRAL;
    if (value < 200) return COLOR_BLUE_SOFT;
    if (value < 1000) return COLOR_BLUE;
    return COLOR_BLUE_STRONG;
  }
  if (selectedMetric === "false_pct") {
    if (value < 30) return COLOR_GREEN;
    if (value < 50) return COLOR_NEUTRAL;
    return COLOR_RED;
  }
  if (value < 30) return COLOR_RED;
  if (value < 50) return COLOR_NEUTRAL;
  return COLOR_GREEN;
}

function metricValue(metric: OccurrenceMetric, selectedMetric: OccurrenceMetricKey): number | null {
  if (selectedMetric === "T") return metric.T;
  return metric[selectedMetric];
}

function formatMetric(metric: OccurrenceMetric, selectedMetric: OccurrenceMetricKey): string {
  const value = metricValue(metric, selectedMetric);
  if (value == null) return "—";
  return selectedMetric === "T" ? value.toLocaleString("en-US") : `${value}%`;
}

function formatPct(value: number | null): string {
  return value == null ? "—" : `${value}%`;
}
