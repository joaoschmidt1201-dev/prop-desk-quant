"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  AlertCircle,
  ArrowUpRight,
  Database,
  Flame,
  Grid3X3,
  Layers,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  Target,
  Zap,
} from "lucide-react";
import type { CSSProperties, ReactNode } from "react";
import {
  api,
  type OccurrenceCategory,
  type OccurrenceLeaderboardEntry,
  type OccurrenceMatrixPayload,
  type OccurrenceMetric,
} from "@/lib/api";
import { OccurrenceFilters, type OccurrenceMetricKey } from "./filters";
import { Leaderboards } from "./leaderboards";
import { TopSetupsTable } from "./top-setups-table";

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
  const [selectedCategories, setSelectedCategories] = useState<string[]>(
    initialData?.categories.map((c) => c.name) ?? [],
  );
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

  useEffect(() => {
    if (!data) return;
    if (selectedCategories.length === 0) {
      setSelectedCategories(data.categories.map((c) => c.name));
    }
  }, [data, selectedCategories.length]);

  if (isLoading && !data) return <OccurrenceSkeleton />;
  if (isError || !data) return <OccurrenceError />;

  const visibleMas = selectedMas.filter((ma) => data.mas.includes(ma));
  const categoryTickers = getCategoryTickers(data, selectedCategories);
  const visibleCategories = getVisibleCategories(data, selectedCategories);
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

  function toggleCategory(name: string) {
    setSelectedCategories((current) => {
      if (current.includes(name)) {
        return current.length <= 1 ? current : current.filter((item) => item !== name);
      }
      const order = data?.categories.map((c) => c.name) ?? [];
      return order.filter((item) => current.includes(item) || item === name);
    });
  }

  return (
    <main className="mx-auto w-full max-w-[1600px] flex-1 px-6 py-8 lg:px-8">
      <Header data={data} isFetching={isFetching} onRefresh={() => refetch()} />
      {missingTfs.length > 0 && <SnapshotNotice loaded={data.tfs} missing={missingTfs} />}
      <KpiBand summary={summary} selectedTf={selectedTf} />
      <div className="mt-6 fade-in">
        <OccurrenceFilters
          tfs={data.tfs}
          expectedTfs={data.expected_tfs}
          selectedTf={selectedTf}
          onTfChange={setSelectedTf}
          selectedMetric={selectedMetric}
          onMetricChange={setSelectedMetric}
          categories={data.categories}
          selectedCategories={selectedCategories}
          onCategoryToggle={toggleCategory}
          onAllCategories={() => setSelectedCategories(data.categories.map((c) => c.name))}
          mas={data.mas}
          selectedMas={visibleMas}
          onMaToggle={toggleMa}
          onAllMas={() => setSelectedMas(data.mas)}
        />
      </div>
      <div className="mt-6 fade-in">
        <Heatmap
          data={data}
          selectedTf={selectedTf}
          categories={visibleCategories}
          mas={visibleMas}
          selectedMetric={selectedMetric}
        />
      </div>
      <div className="mt-6 fade-in">
        <TopSetupsTable
          matrix={data.data}
          categories={data.categories}
          tickers={data.tickers}
          tfs={data.tfs}
          mas={data.mas}
          minSample={data.min_sample}
        />
      </div>
      <div className="mt-6 fade-in">
        <Leaderboards meanReversion={meanReversion} breakout={breakout} minSample={data.min_sample} />
      </div>
      <Legend selectedMetric={selectedMetric} />
    </main>
  );
}

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
  const isFresh = oldestAge < 60 * 60 * 24; // < 24h
  const isStale = oldestAge > 60 * 60 * 24 * 7; // > 7d

  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-primary/30 bg-primary/10 px-3 py-1 text-[11px] font-medium uppercase tracking-[0.22em] text-primary backdrop-blur-sm">
          <Grid3X3 className="h-3.5 w-3.5" />
          Occurrence Matrix
        </div>
        <h1 className="text-3xl font-semibold tracking-tight">
          MMA{" "}
          <span className="bg-gradient-to-r from-primary via-chart-2 to-accent bg-clip-text text-transparent">
            Occurrence Matrix
          </span>
        </h1>
        <p className="mt-1.5 max-w-3xl text-sm text-muted-foreground">
          Bounce, break and false-touch statistics by ticker, timeframe and moving average — calibrated tolerances per (TF, MA).
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-3 rounded-xl border border-border/60 bg-card/45 px-4 py-2.5 shadow-lg shadow-black/5 backdrop-blur-sm">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/15 text-primary">
            <Database className="h-4 w-4" />
          </div>
          <div className="text-right">
            <div className="flex items-center justify-end gap-1.5 text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
              Snapshot
              {isFresh && <StatusDot tone="gain" label="Fresh" />}
              {isStale && <StatusDot tone="warning" label="Stale" />}
            </div>
            <div className="mt-0.5 text-sm font-semibold tabular">{data.latest_snapshot_date ?? "n/a"}</div>
          </div>
        </div>
        <button
          type="button"
          onClick={onRefresh}
          disabled={isFetching}
          className="inline-flex h-11 items-center gap-2 rounded-xl border border-border/55 bg-card/45 px-4 text-xs font-semibold text-muted-foreground transition hover:border-primary/40 hover:bg-primary/10 hover:text-foreground active:scale-95 disabled:cursor-wait disabled:opacity-60"
        >
          <RefreshCw className={`h-4 w-4 ${isFetching ? "animate-spin" : ""}`} />
          {isFetching ? "Refreshing…" : "Refresh"}
        </button>
      </div>
    </div>
  );
}

function StatusDot({ tone, label }: { tone: "gain" | "warning"; label: string }) {
  const color = tone === "gain" ? "var(--gain)" : "var(--warning)";
  return (
    <span className="inline-flex items-center gap-1 normal-case tracking-normal">
      <span className="relative flex h-1.5 w-1.5">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full opacity-60" style={{ backgroundColor: color }} />
        <span className="relative inline-flex h-1.5 w-1.5 rounded-full" style={{ backgroundColor: color }} />
      </span>
      <span className="text-[9px] font-semibold" style={{ color }}>
        {label}
      </span>
    </span>
  );
}

function SnapshotNotice({ loaded, missing }: { loaded: string[]; missing: string[] }) {
  return (
    <div className="mb-5 flex flex-wrap items-center gap-3 rounded-xl border border-warning/30 bg-warning/8 px-4 py-3 text-sm">
      <ShieldAlert className="h-4 w-4 shrink-0 text-[var(--warning)]" />
      <span className="text-foreground/85">
        Loaded TFs: <strong className="font-semibold">{loaded.join(", ") || "none"}</strong>. Missing snapshots:{" "}
        <strong className="font-semibold text-[var(--warning)]">{missing.join(", ")}</strong>.
      </span>
    </div>
  );
}

type KpiTone = "gain" | "loss" | "warning" | "neutral";

function KpiBand({
  summary,
  selectedTf,
}: {
  summary: Summary;
  selectedTf: string;
}) {
  return (
    <section className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
      <KpiBlock
        icon={<Target className="h-4 w-4" />}
        label={`Avg Bounce% · ${selectedTf}`}
        value={formatPct(summary.avgBounce)}
        sub="Mean-reversion strength"
        tone="gain"
      />
      <KpiBlock
        icon={<Zap className="h-4 w-4" />}
        label={`Avg Break% · ${selectedTf}`}
        value={formatPct(summary.avgBreak)}
        sub="Trend continuation"
        tone="loss"
      />
      <KpiBlock
        icon={<AlertCircle className="h-4 w-4" />}
        label={`Avg False% · ${selectedTf}`}
        value={formatPct(summary.avgFalse)}
        sub="Whipsaw rate"
        tone="warning"
      />
      <KpiBlock
        icon={<Activity className="h-4 w-4" />}
        label="Events Analyzed"
        value={summary.events.toLocaleString("en-US")}
        sub={`${summary.lowSampleCells} low-sample cells`}
        tone="neutral"
      />
    </section>
  );
}

function KpiBlock({
  icon,
  label,
  value,
  sub,
  tone,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  sub: string;
  tone: KpiTone;
}) {
  const accent =
    tone === "gain"
      ? { from: "oklch(0.32 0.12 145 / 0.55)", to: "oklch(0.22 0.04 250 / 0.45)", icon: "var(--gain)", text: "var(--gain)" }
      : tone === "loss"
        ? { from: "oklch(0.32 0.14 25 / 0.55)", to: "oklch(0.22 0.04 250 / 0.45)", icon: "var(--loss)", text: "var(--loss)" }
        : tone === "warning"
          ? { from: "oklch(0.32 0.12 90 / 0.55)", to: "oklch(0.22 0.04 250 / 0.45)", icon: "var(--warning)", text: "var(--warning)" }
          : { from: "oklch(0.28 0.06 250 / 0.65)", to: "oklch(0.20 0.02 250 / 0.45)", icon: "var(--primary)", text: "oklch(0.96 0.01 250)" };

  return (
    <div
      className="group relative overflow-hidden rounded-xl border border-border/55 p-4 shadow-lg shadow-black/10 transition hover:border-border/80 hover:shadow-xl hover:shadow-black/20"
      style={{
        background: `linear-gradient(135deg, ${accent.from} 0%, ${accent.to} 100%)`,
      }}
    >
      <div className="absolute -right-6 -top-6 h-24 w-24 rounded-full opacity-20 blur-2xl transition group-hover:opacity-30" style={{ backgroundColor: accent.icon }} />
      <div className="relative flex items-start justify-between gap-2">
        <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-foreground/70">{label}</div>
        <div className="rounded-md bg-background/30 p-1.5 backdrop-blur-sm" style={{ color: accent.icon }}>
          {icon}
        </div>
      </div>
      <div className="relative mt-3 text-3xl font-bold tabular tracking-tight" style={{ color: accent.text }}>
        {value}
      </div>
      <div className="relative mt-1 text-[11px] text-foreground/65">{sub}</div>
    </div>
  );
}

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
  const tickerCount = categories.reduce((sum, category) => sum + category.tickers.length, 0);

  return (
    <section className="overflow-hidden rounded-xl border border-border/60 bg-card/35 shadow-xl shadow-black/10 backdrop-blur-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/50 bg-gradient-to-r from-card/60 to-card/30 px-5 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/15 text-primary">
            <Flame className="h-4 w-4" />
          </div>
          <div>
            <h2 className="text-sm font-semibold tracking-tight">Heatmap</h2>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Each cell shows the selected metric, with B/Bk/F sub-bars. Column headers display the (TF, MA) tolerance.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 rounded-md border border-border/40 bg-background/30 px-3 py-1.5 text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
          <Sparkles className="h-3.5 w-3.5 text-[var(--warning)]" />
          <span className="font-semibold text-foreground/85">{selectedTf}</span>
          <Separator />
          <span>{metricLabel(selectedMetric)}</span>
          <Separator />
          <span>{mas.length} MAs</span>
          <Separator />
          <span>{tickerCount} tickers</span>
        </div>
      </div>
      <div className="space-y-5 p-4">
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

function Separator() {
  return <span className="text-border/60">·</span>;
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
    <div className="overflow-hidden rounded-lg border border-border/40 bg-background/15">
      <div className="flex items-center justify-between gap-3 border-b border-border/35 bg-card/20 px-4 py-2.5">
        <div className="flex items-center gap-2">
          <Layers className="h-3.5 w-3.5 text-muted-foreground/75" />
          <h3 className="text-sm font-semibold">{displayCategoryName(category.name)}</h3>
        </div>
        <span className="rounded-md border border-border/40 bg-background/25 px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
          {category.tickers.length} tickers
        </span>
      </div>
      <div className="overflow-auto">
        <table className="w-full min-w-[920px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-border/40 bg-background/35">
              <th className="sticky left-0 z-10 w-[110px] bg-background/95 px-3 py-3 text-left text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground backdrop-blur-sm">
                Ticker
              </th>
              {mas.map((ma) => (
                <th key={ma} className="min-w-[152px] px-2 py-3 text-center">
                  <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-foreground/85">{ma}</div>
                  <div className="mt-1 inline-block rounded-full bg-background/35 px-2 py-0.5 text-[9.5px] font-medium normal-case tracking-normal text-[var(--warning)]">
                    {toleranceLabel(data, selectedTf, ma)}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {category.tickers.map((ticker, rowIdx) => (
              <tr
                key={ticker}
                className="group/row border-b border-border/30 last:border-b-0 transition hover:bg-primary/[0.04]"
              >
                <td className="sticky left-0 z-10 bg-background/95 px-3 py-2 text-sm font-semibold text-foreground backdrop-blur-sm transition group-hover/row:text-primary">
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-normal text-muted-foreground/60 tabular">{String(rowIdx + 1).padStart(2, "0")}</span>
                    <span>{ticker}</span>
                  </div>
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
        className="h-[92px] min-w-[152px] border-l border-border/20 px-2 py-2 text-center"
        style={{ backgroundColor: "oklch(0.22 0.018 250 / 0.45)" }}
      >
        <span className="text-[11px] font-medium text-muted-foreground/55">—</span>
      </td>
    );
  }

  const style = heatStyle(metric, selectedMetric);

  const tooltip = [
    `Total events: ${metric.T}`,
    `Bounce: ${metric.B} (${formatPct(metric.bounce_pct)})`,
    `Break:  ${metric.Bk} (${formatPct(metric.break_pct)})`,
    `False:  ${metric.F} (${formatPct(metric.false_pct)})`,
    `Tolerance: ${metric.tolerance_pct == null ? "n/a" : `±${metric.tolerance_pct}%`}`,
    metric.low_sample ? "[low sample]" : "",
  ]
    .filter(Boolean)
    .join("\n");

  const cellStyle: CSSProperties = metric.low_sample
    ? { ...style, boxShadow: "inset 0 0 0 1px oklch(1 0 0 / 0.25)" }
    : style;

  return (
    <td
      className="group/cell relative h-[92px] min-w-[152px] cursor-help border-l border-border/20 px-2 py-2 text-center text-white transition-all duration-150 hover:z-10 hover:scale-[1.03] hover:shadow-xl hover:shadow-black/40"
      style={cellStyle}
      title={tooltip}
    >
      <div className="text-[9.5px] font-semibold uppercase tracking-[0.18em] text-white/80">
        {metricLabel(selectedMetric)}
      </div>
      <div className="mt-0.5 text-[20px] font-bold leading-tight tabular text-white">
        {formatMetric(metric, selectedMetric)}
      </div>
      <SubMetrics metric={metric} selectedMetric={selectedMetric} />
    </td>
  );
}

function SubMetrics({ metric, selectedMetric }: { metric: OccurrenceMetric; selectedMetric: OccurrenceMetricKey }) {
  return (
    <div className="mt-2 grid grid-cols-4 gap-[3px] text-[9.5px] font-semibold tabular">
      <SubMetric label="B" value={metric.bounce_pct} suffix="%" active={selectedMetric === "bounce_pct"} tone="gain" />
      <SubMetric label="Bk" value={metric.break_pct} suffix="%" active={selectedMetric === "break_pct"} tone="loss" />
      <SubMetric label="F" value={metric.false_pct} suffix="%" active={selectedMetric === "false_pct"} tone="warning" />
      <SubMetric label="n" value={metric.T} suffix="" active={selectedMetric === "T"} tone="neutral" />
    </div>
  );
}

function SubMetric({
  label,
  value,
  suffix,
  active,
  tone,
}: {
  label: string;
  value: number | null;
  suffix: string;
  active: boolean;
  tone: "gain" | "loss" | "warning" | "neutral";
}) {
  const dot =
    tone === "gain"
      ? "oklch(0.78 0.18 145)"
      : tone === "loss"
        ? "oklch(0.72 0.22 25)"
        : tone === "warning"
          ? "oklch(0.85 0.16 90)"
          : "oklch(0.75 0.02 250)";

  return (
    <span
      className={`flex items-center justify-center gap-0.5 rounded-[3px] px-1 py-[3px] ${active ? "bg-white/25 ring-1 ring-white/40" : "bg-black/35"}`}
    >
      <span className="h-1 w-1 rounded-full" style={{ backgroundColor: dot }} />
      <span className="text-white/90">{label}</span>
      <span className="font-bold text-white">
        {value == null ? "—" : `${value}${suffix}`}
      </span>
    </span>
  );
}

function getCategoryTickers(data: OccurrenceMatrixPayload, selectedCategories: string[]): string[] {
  if (selectedCategories.length === 0 || selectedCategories.length === data.categories.length) {
    return data.tickers;
  }
  const set = new Set(selectedCategories);
  const tickers: string[] = [];
  for (const category of data.categories) {
    if (set.has(category.name)) tickers.push(...category.tickers);
  }
  return tickers;
}

function getVisibleCategories(data: OccurrenceMatrixPayload, selectedCategories: string[]): OccurrenceCategory[] {
  if (selectedCategories.length === 0 || selectedCategories.length === data.categories.length) {
    return data.categories;
  }
  const set = new Set(selectedCategories);
  return data.categories.filter((category) => set.has(category.name));
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
      if (metric.T >= data.min_sample && metric.bounce_pct != null) {
        bounceValues.push(metric.bounce_pct);
      }
      if (metric.T >= data.min_sample && metric.break_pct != null) {
        breakValues.push(metric.break_pct);
      }
      if (metric.T >= data.min_sample && metric.false_pct != null) {
        falseValues.push(metric.false_pct);
      }
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

function heatStyle(metric: OccurrenceMetric | null, selectedMetric: OccurrenceMetricKey): CSSProperties {
  const value = metric ? metricValue(metric, selectedMetric) : null;
  if (!metric || metric.T === 0 || value == null) {
    return { backgroundColor: "oklch(0.22 0.018 250 / 0.45)" };
  }

  const bg = heatBands(value, selectedMetric);

  // Keep cells fully opaque so the text stays sharp. Low-sample cells are
  // flagged via a dashed ring in HeatCell instead of reducing opacity.
  return { backgroundColor: bg };
}

// Minimal 3-tone palette: red (< 30%), neutral gray (30-54%), green (>= 55%).
// Same thresholds applied across bounce/break (high = good) and false%
// (inverted: high = bad). Events use a separate neutral→blue scale since
// it's magnitude, not polarity.
const COLOR_RED = "oklch(0.45 0.18 25)";
const COLOR_NEUTRAL = "oklch(0.32 0.025 250)";
const COLOR_GREEN = "oklch(0.52 0.20 148)";

const COLOR_BLUE_SOFT = "oklch(0.36 0.10 250)";
const COLOR_BLUE = "oklch(0.46 0.18 250)";
const COLOR_BLUE_STRONG = "oklch(0.54 0.22 250)";

function heatBands(value: number, selectedMetric: OccurrenceMetricKey): string {
  if (selectedMetric === "T") {
    if (value < 50) return COLOR_NEUTRAL;
    if (value < 200) return COLOR_BLUE_SOFT;
    if (value < 1000) return COLOR_BLUE;
    return COLOR_BLUE_STRONG;
  }

  if (selectedMetric === "false_pct") {
    // inverted: low false% = good (green), high = bad (red)
    if (value < 30) return COLOR_GREEN;
    if (value < 50) return COLOR_NEUTRAL;
    return COLOR_RED;
  }

  // bounce_pct / break_pct: high = good
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

function metricLabel(selectedMetric: OccurrenceMetricKey): string {
  if (selectedMetric === "bounce_pct") return "Bounce%";
  if (selectedMetric === "break_pct") return "Break%";
  if (selectedMetric === "false_pct") return "False%";
  return "Events";
}

function formatPct(value: number | null): string {
  return value == null ? "—" : `${value}%`;
}

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
    <div className="mt-6 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border/50 bg-card/30 px-4 py-3 text-xs text-muted-foreground fade-in">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-[10px] font-semibold uppercase tracking-[0.18em] text-foreground/80">
          Legend · {metricLabel(selectedMetric)}
        </span>
        <div className="flex items-center gap-1">
          {stops.map((stop) => (
            <div key={stop.label} className="flex items-center gap-1.5">
              <div className="h-3.5 w-7 rounded shadow-inner shadow-black/30" style={{ backgroundColor: stop.color }} />
              <span className="text-[10px] text-foreground/75">{stop.label}</span>
            </div>
          ))}
        </div>
      </div>
      <div className="flex items-center gap-4 text-[10px]">
        <span className="flex items-center gap-1.5">
          <span
            className="inline-block h-3.5 w-3.5 rounded"
            style={{ backgroundColor: COLOR_NEUTRAL, boxShadow: "inset 0 0 0 1px oklch(1 0 0 / 0.25)" }}
          />
          Low sample (n &lt; min)
        </span>
      </div>
    </div>
  );
}

function OccurrenceSkeleton() {
  return (
    <main className="mx-auto w-full max-w-[1600px] flex-1 px-6 py-8 lg:px-8">
      <div className="mb-6 h-24 animate-pulse rounded-xl bg-card/30" />
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
        {[0, 1, 2, 3].map((item) => (
          <div key={item} className="h-28 animate-pulse rounded-xl bg-card/30" />
        ))}
      </div>
      <div className="mt-6 h-[640px] animate-pulse rounded-xl bg-card/25" />
    </main>
  );
}

function OccurrenceError() {
  return (
    <main className="mx-auto w-full max-w-[1600px] flex-1 px-6 py-8 lg:px-8">
      <div className="rounded-xl border border-destructive/40 bg-destructive/10 p-8 backdrop-blur-sm">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-destructive/20 text-destructive">
            <AlertCircle className="h-5 w-5" />
          </div>
          <div>
            <div className="text-lg font-semibold">Occurrence Matrix unavailable</div>
            <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
              The API could not load the TradingView snapshots. Verify the snapshot directory and retry the page.
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="mt-4 inline-flex items-center gap-2 rounded-md border border-border/60 bg-card/45 px-3 py-1.5 text-xs font-semibold transition hover:bg-card/65"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Reload page
          <ArrowUpRight className="h-3.5 w-3.5" />
        </button>
      </div>
    </main>
  );
}
