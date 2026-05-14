"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  AlertCircle,
  ArrowUpRight,
  RefreshCw,
  ShieldAlert,
} from "lucide-react";
import type { CSSProperties } from "react";
import {
  api,
  type OccurrenceCategory,
  type OccurrenceLeaderboardEntry,
  type OccurrenceMatrixPayload,
  type OccurrenceMetric,
} from "@/lib/api";
import { OccurrenceFilters, type OccurrenceMetricKey } from "./filters";
import { Leaderboards } from "./leaderboards";

// ============================================================
// Color palette — calm, modern, dark-theme native
// ============================================================
const COLOR_RED = "oklch(0.46 0.16 25)";
const COLOR_NEUTRAL = "oklch(0.30 0.025 250)";
const COLOR_GREEN = "oklch(0.55 0.20 148)";

const COLOR_BLUE_SOFT = "oklch(0.36 0.10 250)";
const COLOR_BLUE = "oklch(0.46 0.18 250)";
const COLOR_BLUE_STRONG = "oklch(0.54 0.22 250)";

type DashboardProps = {
  initialData?: OccurrenceMatrixPayload | null;
};

type Summary = {
  avgBounce: number | null;
  avgBreak: number | null;
  avgFalse: number | null;
  events: number;
  lowSampleCells: number;
  best: OccurrenceLeaderboardEntry | null;
};

export function OccurrenceMatrixDashboard({ initialData }: DashboardProps) {
  const [selectedTf, setSelectedTf] = useState(initialData?.tfs[0] ?? "W");
  const [selectedMetric, setSelectedMetric] = useState<OccurrenceMetricKey>("bounce_pct");
  const [selectedCategory, setSelectedCategory] = useState("All");
  const [selectedMas, setSelectedMas] = useState<string[]>(initialData?.mas ?? []);

  const { data, isLoading, isError, isFetching, refetch } = useQuery({
    queryKey: ["occurrence-matrix"],
    queryFn: () => api.occurrenceMatrix(),
    initialData: initialData ?? undefined,
    refetchInterval: 300_000,
  });

  useEffect(() => {
    if (!data) return;
    if (!data.tfs.includes(selectedTf) && data.tfs.length > 0) {
      setSelectedTf(data.tfs[0]);
    }
  }, [data, selectedTf]);

  useEffect(() => {
    if (!data) return;
    if (selectedMas.length === 0) {
      setSelectedMas(data.mas);
    }
  }, [data, selectedMas.length]);

  if (isLoading && !data) return <OccurrenceSkeleton />;
  if (isError || !data) return <OccurrenceError />;

  const visibleMas = selectedMas.filter((ma) => data.mas.includes(ma));
  const categoryTickers = getCategoryTickers(data, selectedCategory);
  const visibleCategories = getVisibleCategories(data, selectedCategory);
  const missingTfs = data.expected_tfs.filter((tf) => !data.tfs.includes(tf));
  const meanReversion = collectSetups(data, selectedTf, categoryTickers, visibleMas, "bounce_pct");
  const breakout = collectSetups(data, selectedTf, categoryTickers, visibleMas, "break_pct");
  const summary = summarize(data, selectedTf, categoryTickers, visibleMas, meanReversion);

  function toggleMa(ma: string) {
    setSelectedMas((current) => {
      if (current.includes(ma)) {
        return current.length <= 1 ? current : current.filter((item) => item !== ma);
      }
      return (data?.mas ?? []).filter((item) => current.includes(item) || item === ma);
    });
  }

  return (
    <main className="mx-auto w-full max-w-[1500px] flex-1 px-6 py-10 lg:px-10">
      <Header data={data} isFetching={isFetching} onRefresh={() => refetch()} />
      {missingTfs.length > 0 && <SnapshotNotice loaded={data.tfs} missing={missingTfs} />}

      <div className="mt-10 fade-in">
        <KpiBand summary={summary} selectedTf={selectedTf} />
      </div>

      <div className="mt-8 fade-in">
        <OccurrenceFilters
          tfs={data.tfs}
          expectedTfs={data.expected_tfs}
          selectedTf={selectedTf}
          onTfChange={setSelectedTf}
          selectedMetric={selectedMetric}
          onMetricChange={setSelectedMetric}
          categories={data.categories}
          selectedCategory={selectedCategory}
          onCategoryChange={setSelectedCategory}
          mas={data.mas}
          selectedMas={visibleMas}
          onMaToggle={toggleMa}
          onAllMas={() => setSelectedMas(data.mas)}
        />
      </div>

      <div className="mt-8 fade-in">
        <Heatmap
          data={data}
          selectedTf={selectedTf}
          categories={visibleCategories}
          mas={visibleMas}
          selectedMetric={selectedMetric}
        />
      </div>

      <div className="mt-8 fade-in">
        <Leaderboards meanReversion={meanReversion} breakout={breakout} minSample={data.min_sample} />
      </div>

      <Legend selectedMetric={selectedMetric} />
    </main>
  );
}

// ============================================================
// Header
// ============================================================
function Header({
  data,
  isFetching,
  onRefresh,
}: {
  data: OccurrenceMatrixPayload;
  isFetching: boolean;
  onRefresh: () => void;
}) {
  const oldestAge = data.oldest_snapshot_age_seconds ?? 0;
  const freshLabel = formatAge(oldestAge);

  return (
    <div className="flex flex-col items-start justify-between gap-6 sm:flex-row sm:items-end">
      <div>
        <div className="mb-3 inline-flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.24em] text-muted-foreground">
          <span className="inline-block h-1 w-6 rounded-full bg-primary/70" />
          Occurrence Matrix
        </div>
        <h1 className="text-4xl font-semibold tracking-tight">MMA Occurrence Matrix</h1>
        <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-muted-foreground">
          Bounce, break and false-touch statistics across {data.tickers.length} tickers, {data.tfs.length} timeframes and {data.mas.length} moving averages.
        </p>
      </div>
      <div className="flex items-center gap-4">
        <div className="text-right">
          <div className="text-[10px] font-medium uppercase tracking-[0.2em] text-muted-foreground">
            Snapshot
          </div>
          <div className="mt-1 text-sm font-semibold tabular">
            {data.latest_snapshot_date ?? "n/a"}
          </div>
          <div className="text-[10px] text-muted-foreground">{freshLabel}</div>
        </div>
        <button
          type="button"
          onClick={onRefresh}
          disabled={isFetching}
          className="group inline-flex h-10 items-center gap-2 rounded-lg border border-border/40 bg-card/30 px-3.5 text-[12px] font-medium text-muted-foreground transition hover:border-border/80 hover:bg-card/60 hover:text-foreground disabled:cursor-wait disabled:opacity-60"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? "animate-spin" : "group-hover:rotate-90 transition-transform"}`} />
          {isFetching ? "Refreshing" : "Refresh"}
        </button>
      </div>
    </div>
  );
}

function formatAge(seconds: number): string {
  if (seconds < 60) return "moments ago";
  if (seconds < 3600) return `${Math.round(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)} h ago`;
  const days = Math.round(seconds / 86400);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

function SnapshotNotice({ loaded, missing }: { loaded: string[]; missing: string[] }) {
  return (
    <div className="mt-6 flex flex-wrap items-center gap-2 rounded-lg border border-warning/25 bg-warning/[0.06] px-4 py-2.5 text-[13px] text-foreground/80">
      <ShieldAlert className="h-3.5 w-3.5 text-[var(--warning)]" />
      Loaded: <span className="font-medium">{loaded.join(", ") || "none"}</span> · Missing:{" "}
      <span className="font-medium text-[var(--warning)]">{missing.join(", ")}</span>
    </div>
  );
}

// ============================================================
// KPI Band — minimal, big numbers
// ============================================================
function KpiBand({
  summary,
  selectedTf,
}: {
  summary: Summary;
  selectedTf: string;
}) {
  return (
    <section className="grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-border/40 bg-border/40 xl:grid-cols-4">
      <KpiBlock label="Bounce" value={formatPct(summary.avgBounce)} sub={`avg · ${selectedTf}`} accent={COLOR_GREEN} />
      <KpiBlock label="Break" value={formatPct(summary.avgBreak)} sub={`avg · ${selectedTf}`} accent={COLOR_BLUE} />
      <KpiBlock label="False" value={formatPct(summary.avgFalse)} sub={`avg · ${selectedTf}`} accent={COLOR_RED} />
      <KpiBlock
        label="Events"
        value={summary.events.toLocaleString("en-US")}
        sub={`${summary.lowSampleCells} low-sample`}
      />
    </section>
  );
}

function KpiBlock({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string;
  sub: string;
  accent?: string;
}) {
  return (
    <div className="group relative bg-card/60 px-6 py-5 transition hover:bg-card/80">
      {accent && (
        <span
          className="absolute inset-x-6 top-0 h-px"
          style={{ background: `linear-gradient(90deg, transparent, ${accent}, transparent)` }}
        />
      )}
      <div className="text-[11px] font-medium uppercase tracking-[0.22em] text-muted-foreground">
        {label}
      </div>
      <div className="mt-3 text-4xl font-semibold tabular leading-none tracking-tight text-foreground">
        {value}
      </div>
      <div className="mt-2 text-[11px] text-muted-foreground/85">{sub}</div>
    </div>
  );
}

// ============================================================
// Heatmap — clean cells, big numbers, hover reveals detail
// ============================================================
function Heatmap({
  data,
  selectedTf,
  categories,
  mas,
  selectedMetric,
}: {
  data: OccurrenceMatrixPayload;
  selectedTf: string;
  categories: OccurrenceCategory[];
  mas: string[];
  selectedMetric: OccurrenceMetricKey;
}) {
  return (
    <section>
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">Matrix</h2>
          <p className="mt-1 text-[12px] text-muted-foreground">
            Each cell shows{" "}
            <span className="font-medium text-foreground/85">{metricLabel(selectedMetric)}</span> · hover for details.
          </p>
        </div>
        <div className="text-[11px] font-medium uppercase tracking-[0.2em] text-muted-foreground">
          {selectedTf} · {mas.length} MAs · {categories.reduce((sum, c) => sum + c.tickers.length, 0)} tickers
        </div>
      </div>
      <div className="space-y-8">
        {categories.map((category) => (
          <CategoryHeatmap
            key={category.name}
            data={data}
            selectedTf={selectedTf}
            category={category}
            mas={mas}
            selectedMetric={selectedMetric}
          />
        ))}
      </div>
    </section>
  );
}

function CategoryHeatmap({
  data,
  selectedTf,
  category,
  mas,
  selectedMetric,
}: {
  data: OccurrenceMatrixPayload;
  selectedTf: string;
  category: OccurrenceCategory;
  mas: string[];
  selectedMetric: OccurrenceMetricKey;
}) {
  return (
    <div>
      <div className="mb-3 flex items-baseline justify-between gap-3 px-1">
        <h3 className="text-[13px] font-semibold tracking-tight text-foreground/85">
          {displayCategoryName(category.name)}
        </h3>
        <span className="text-[10px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
          {category.tickers.length} tickers
        </span>
      </div>
      <div className="overflow-hidden rounded-xl border border-border/35 bg-card/20">
        <div className="overflow-auto">
          <table className="w-full min-w-[840px] border-collapse">
            <thead>
              <tr>
                <th className="sticky left-0 z-10 w-[100px] bg-card/85 px-4 py-3 text-left text-[10px] font-semibold uppercase tracking-[0.2em] text-muted-foreground backdrop-blur-sm">
                  Ticker
                </th>
                {mas.map((ma) => (
                  <th key={ma} className="min-w-[140px] px-2 py-3 text-center">
                    <div className="text-[11px] font-semibold tracking-tight text-foreground/90">{ma}</div>
                    <div className="mt-0.5 text-[10px] font-normal text-muted-foreground/75">
                      {toleranceLabel(data, selectedTf, ma)}
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {category.tickers.map((ticker) => (
                <tr key={ticker} className="group/row border-t border-border/25 transition hover:bg-primary/[0.025]">
                  <td className="sticky left-0 z-10 bg-card/85 px-4 py-2 text-[13px] font-semibold text-foreground backdrop-blur-sm transition group-hover/row:text-primary">
                    {ticker}
                  </td>
                  {mas.map((ma) => (
                    <HeatCell
                      key={`${ticker}-${ma}`}
                      metric={data.data[ticker]?.[selectedTf]?.[ma] ?? null}
                      selectedMetric={selectedMetric}
                    />
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function HeatCell({
  metric,
  selectedMetric,
}: {
  metric: OccurrenceMetric | null;
  selectedMetric: OccurrenceMetricKey;
}) {
  if (!metric || metric.T === 0) {
    return (
      <td
        className="h-[68px] min-w-[140px] border-l border-border/15 px-2 py-2 text-center"
        style={{ backgroundColor: "oklch(0.18 0.012 250)" }}
      >
        <span className="text-[12px] text-muted-foreground/40">—</span>
      </td>
    );
  }

  const style = heatStyle(metric, selectedMetric);
  const tooltip = [
    `T=${metric.T}`,
    `Bounce ${metric.B} · ${formatPct(metric.bounce_pct)}`,
    `Break  ${metric.Bk} · ${formatPct(metric.break_pct)}`,
    `False  ${metric.F} · ${formatPct(metric.false_pct)}`,
    `Tol ±${metric.tolerance_pct ?? "n/a"}%`,
    metric.low_sample ? "low sample" : "",
  ]
    .filter(Boolean)
    .join("\n");

  const cellStyle: CSSProperties = metric.low_sample
    ? { ...style, boxShadow: "inset 0 0 0 1px oklch(1 0 0 / 0.18)" }
    : style;

  return (
    <td
      className="group/cell relative h-[68px] min-w-[140px] cursor-help border-l border-border/15 px-2 py-2 text-center text-white transition-all duration-150 hover:z-10 hover:scale-[1.04]"
      style={cellStyle}
      title={tooltip}
    >
      <div className="text-[22px] font-semibold leading-none tabular tracking-tight">
        {formatMetric(metric, selectedMetric)}
      </div>
      <div className="mt-1.5 text-[10px] font-medium tabular text-white/65">
        n = {metric.T.toLocaleString("en-US")}
      </div>
    </td>
  );
}

// ============================================================
// Color logic — 3-tone palette (red / neutral / green)
// ============================================================
function heatStyle(metric: OccurrenceMetric | null, selectedMetric: OccurrenceMetricKey): CSSProperties {
  const value = metric ? metricValue(metric, selectedMetric) : null;
  if (!metric || metric.T === 0 || value == null) {
    return { backgroundColor: "oklch(0.20 0.015 250)" };
  }
  return { backgroundColor: heatBands(value, selectedMetric) };
}

function heatBands(value: number, selectedMetric: OccurrenceMetricKey): string {
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

// ============================================================
// Helpers
// ============================================================
function getCategoryTickers(data: OccurrenceMatrixPayload, selectedCategory: string): string[] {
  if (selectedCategory === "All") return data.tickers;
  return data.categories.find((category) => category.name === selectedCategory)?.tickers ?? data.tickers;
}

function getVisibleCategories(data: OccurrenceMatrixPayload, selectedCategory: string): OccurrenceCategory[] {
  if (selectedCategory === "All") return data.categories;
  const category = data.categories.find((item) => item.name === selectedCategory);
  return category ? [category] : data.categories;
}

function displayCategoryName(name: string): string {
  const labels: Record<string, string> = {
    "Indices/Futures": "Major Indices / Futures",
    FX: "Forex",
    "QQQ Top 10": "Stocks",
    "Commodities/ETFs": "Commodities / ETFs",
  };
  return labels[name] ?? name;
}

function toleranceLabel(data: OccurrenceMatrixPayload, tf: string, ma: string): string {
  const maIndex = data.mas.indexOf(ma);
  const tolerance = maIndex >= 0 ? data.tolerances[tf]?.[maIndex] : null;
  if (tolerance == null) return "tol n/a";
  if (tolerance === 0) return "skip";
  return `±${tolerance}%`;
}

function collectSetups(
  data: OccurrenceMatrixPayload,
  tf: string,
  tickers: string[],
  mas: string[],
  primary: "bounce_pct" | "break_pct",
): OccurrenceLeaderboardEntry[] {
  const rows: OccurrenceLeaderboardEntry[] = [];
  for (const ticker of tickers) {
    for (const ma of mas) {
      const metric = data.data[ticker]?.[tf]?.[ma];
      if (!metric || metric.T < data.min_sample) continue;
      rows.push({
        ticker,
        tf,
        ma,
        total: metric.T,
        bounce_pct: metric.bounce_pct,
        break_pct: metric.break_pct,
        false_pct: metric.false_pct,
      });
    }
  }
  return rows
    .sort((a, b) => {
      const av = a[primary] ?? -1;
      const bv = b[primary] ?? -1;
      if (bv !== av) return bv - av;
      return b.total - a.total;
    })
    .slice(0, 5);
}

function summarize(
  data: OccurrenceMatrixPayload,
  tf: string,
  tickers: string[],
  mas: string[],
  meanReversion: OccurrenceLeaderboardEntry[],
): Summary {
  const bounceValues: number[] = [];
  const breakValues: number[] = [];
  const falseValues: number[] = [];
  let events = 0;
  let lowSampleCells = 0;

  for (const ticker of tickers) {
    for (const ma of mas) {
      const metric = data.data[ticker]?.[tf]?.[ma];
      if (!metric) continue;
      events += metric.T;
      if (metric.T > 0 && metric.T < data.min_sample) lowSampleCells += 1;
      if (metric.T >= data.min_sample && metric.bounce_pct != null) bounceValues.push(metric.bounce_pct);
      if (metric.T >= data.min_sample && metric.break_pct != null) breakValues.push(metric.break_pct);
      if (metric.T >= data.min_sample && metric.false_pct != null) falseValues.push(metric.false_pct);
    }
  }

  return {
    avgBounce: averagePct(bounceValues),
    avgBreak: averagePct(breakValues),
    avgFalse: averagePct(falseValues),
    events,
    lowSampleCells,
    best: meanReversion[0] ?? null,
  };
}

function averagePct(values: number[]): number | null {
  return values.length ? Math.round(values.reduce((sum, value) => sum + value, 0) / values.length) : null;
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

function metricLabel(selectedMetric: OccurrenceMetricKey): string {
  if (selectedMetric === "bounce_pct") return "Bounce %";
  if (selectedMetric === "break_pct") return "Break %";
  if (selectedMetric === "false_pct") return "False %";
  return "Events";
}

function formatPct(value: number | null): string {
  return value == null ? "—" : `${value}%`;
}

// ============================================================
// Legend
// ============================================================
function Legend({ selectedMetric }: { selectedMetric: OccurrenceMetricKey }) {
  const stops =
    selectedMetric === "T"
      ? [
          { color: COLOR_NEUTRAL, label: "< 50" },
          { color: COLOR_BLUE_SOFT, label: "50-199" },
          { color: COLOR_BLUE, label: "200-999" },
          { color: COLOR_BLUE_STRONG, label: "≥ 1000" },
        ]
      : selectedMetric === "false_pct"
        ? [
            { color: COLOR_GREEN, label: "< 30%" },
            { color: COLOR_NEUTRAL, label: "30-49%" },
            { color: COLOR_RED, label: "≥ 50%" },
          ]
        : [
            { color: COLOR_RED, label: "< 30%" },
            { color: COLOR_NEUTRAL, label: "30-49%" },
            { color: COLOR_GREEN, label: "≥ 50%" },
          ];

  return (
    <div className="mt-10 flex flex-wrap items-center justify-between gap-4 border-t border-border/35 px-1 pt-5 text-[11px] text-muted-foreground fade-in">
      <div className="flex flex-wrap items-center gap-4">
        <span className="font-medium uppercase tracking-[0.2em] text-foreground/70">
          {metricLabel(selectedMetric)}
        </span>
        <div className="flex items-center gap-3">
          {stops.map((stop) => (
            <div key={stop.label} className="flex items-center gap-1.5">
              <span className="block h-3 w-6 rounded" style={{ backgroundColor: stop.color }} />
              <span className="tabular">{stop.label}</span>
            </div>
          ))}
        </div>
      </div>
      <div className="flex items-center gap-3">
        <span className="flex items-center gap-1.5">
          <span className="block h-3 w-3 rounded" style={{ backgroundColor: COLOR_NEUTRAL, boxShadow: "inset 0 0 0 1px oklch(1 0 0 / 0.2)" }} />
          low sample
        </span>
      </div>
    </div>
  );
}

// ============================================================
// Skeleton + Error
// ============================================================
function OccurrenceSkeleton() {
  return (
    <main className="mx-auto w-full max-w-[1500px] flex-1 px-6 py-10 lg:px-10">
      <div className="h-16 max-w-xl animate-pulse rounded-lg bg-card/30" />
      <div className="mt-10 grid grid-cols-2 gap-px overflow-hidden rounded-2xl xl:grid-cols-4">
        {[0, 1, 2, 3].map((item) => (
          <div key={item} className="h-28 animate-pulse bg-card/30" />
        ))}
      </div>
      <div className="mt-8 h-[520px] animate-pulse rounded-2xl bg-card/25" />
    </main>
  );
}

function OccurrenceError() {
  return (
    <main className="mx-auto w-full max-w-[1500px] flex-1 px-6 py-10 lg:px-10">
      <div className="rounded-2xl border border-destructive/30 bg-destructive/[0.06] p-10">
        <div className="flex items-center gap-4">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-destructive/15 text-destructive">
            <AlertCircle className="h-5 w-5" />
          </div>
          <div>
            <div className="text-lg font-semibold tracking-tight">Occurrence Matrix unavailable</div>
            <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
              The API could not load the TradingView snapshots. Verify the snapshot directory and retry.
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="mt-5 inline-flex items-center gap-2 rounded-lg border border-border/50 bg-card/45 px-4 py-2 text-[12px] font-medium transition hover:bg-card/70"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Reload page
          <ArrowUpRight className="h-3.5 w-3.5" />
        </button>
      </div>
    </main>
  );
}
