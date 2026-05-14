"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Grid3X3, RefreshCw, ShieldAlert, Sparkles } from "lucide-react";
import type { CSSProperties } from "react";
import { api, type OccurrenceLeaderboardEntry, type OccurrenceMatrixPayload, type OccurrenceMetric } from "@/lib/api";
import { fmtRelativeAge } from "@/lib/format";
import { OccurrenceFilters } from "./filters";
import { Leaderboards } from "./leaderboards";

type DashboardProps = {
  initialData?: OccurrenceMatrixPayload | null;
};

type Summary = {
  avgBounce: number | null;
  events: number;
  lowSampleCells: number;
  best: OccurrenceLeaderboardEntry | null;
};

export function OccurrenceMatrixDashboard({ initialData }: DashboardProps) {
  const [selectedTf, setSelectedTf] = useState(initialData?.tfs[0] ?? "D");
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
    <main className="mx-auto w-full max-w-[1600px] flex-1 px-8 py-8">
      <Header data={data} isFetching={isFetching} onRefresh={() => refetch()} />
      {missingTfs.length > 0 && <SnapshotNotice loaded={data.tfs} missing={missingTfs} />}
      <KpiBand summary={summary} selectedTf={selectedTf} oldestSnapshotAge={data.oldest_snapshot_age_seconds} />
      <div className="mt-5">
        <OccurrenceFilters
          tfs={data.tfs}
          expectedTfs={data.expected_tfs}
          selectedTf={selectedTf}
          onTfChange={setSelectedTf}
          categories={data.categories}
          selectedCategory={selectedCategory}
          onCategoryChange={setSelectedCategory}
          mas={data.mas}
          selectedMas={visibleMas}
          onMaToggle={toggleMa}
          onAllMas={() => setSelectedMas(data.mas)}
        />
      </div>
      <div className="mt-5">
        <Heatmap data={data} selectedTf={selectedTf} tickers={categoryTickers} mas={visibleMas} />
      </div>
      <div className="mt-5">
        <Leaderboards meanReversion={meanReversion} breakout={breakout} minSample={data.min_sample} />
      </div>
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
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
      <div>
        <div className="mb-2 inline-flex items-center gap-2 rounded-md border border-primary/25 bg-primary/10 px-3 py-1 text-[11px] font-medium uppercase tracking-[0.22em] text-primary">
          <Grid3X3 className="h-3.5 w-3.5" />
          Occurrence Matrix
        </div>
        <h1 className="text-2xl font-semibold tracking-tight">MMA Occurrence Matrix</h1>
        <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
          Bounce, break and false-touch statistics by ticker, timeframe and moving average.
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <div className="rounded-md border border-border/55 bg-card/35 px-3 py-2 text-right">
          <div className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">Snapshot</div>
          <div className="mt-0.5 text-sm font-semibold tabular">{data.latest_snapshot_date ?? "n/a"}</div>
        </div>
        <button
          type="button"
          onClick={onRefresh}
          className="inline-flex h-10 items-center gap-2 rounded-md border border-border/55 bg-card/45 px-3 text-xs font-semibold text-muted-foreground transition hover:border-primary/40 hover:bg-card/70 hover:text-foreground"
        >
          <RefreshCw className={`h-4 w-4 ${isFetching ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>
    </div>
  );
}

function SnapshotNotice({ loaded, missing }: { loaded: string[]; missing: string[] }) {
  return (
    <div className="mb-5 flex flex-wrap items-center gap-3 rounded-lg border border-warning/35 bg-warning/10 px-4 py-3 text-sm">
      <ShieldAlert className="h-4 w-4 text-[var(--warning)]" />
      <span className="text-foreground/85">
        Loaded TFs: <strong>{loaded.join(", ") || "none"}</strong>. Missing snapshots:{" "}
        <strong>{missing.join(", ")}</strong>.
      </span>
    </div>
  );
}

function KpiBand({
  summary,
  selectedTf,
  oldestSnapshotAge,
}: {
  summary: Summary;
  selectedTf: string;
  oldestSnapshotAge: number | null;
}) {
  return (
    <section className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
      <KpiBlock label={`Avg Bounce% ${selectedTf}`} value={formatPct(summary.avgBounce)} sub="Sample-filtered cells" />
      <KpiBlock label="Events analyzed" value={summary.events.toLocaleString("en-US")} sub="Visible heatmap scope" />
      <KpiBlock
        label="Best setup"
        value={summary.best ? `${summary.best.ticker} ${summary.best.ma}` : "n/a"}
        sub={summary.best ? `${summary.best.tf} | ${formatPct(summary.best.bounce_pct)} | n=${summary.best.total}` : "No setup above threshold"}
      />
      <KpiBlock
        label="Oldest snapshot"
        value={fmtRelativeAge(oldestSnapshotAge)}
        sub={`${summary.lowSampleCells} low-sample cells`}
      />
    </section>
  );
}

function KpiBlock({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="rounded-lg border border-border/60 bg-gradient-to-br from-[#0d1f3c] to-[#1c3461] p-4 text-white shadow-xl shadow-black/10">
      <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[#c9d4ec]">{label}</div>
      <div className="mt-2 truncate text-2xl font-semibold tabular text-[#f3c969]">{value}</div>
      <div className="mt-1 truncate text-[11px] text-[#c9d4ec]">{sub}</div>
    </div>
  );
}

function Heatmap({
  data,
  selectedTf,
  tickers,
  mas,
}: {
  data: OccurrenceMatrixPayload;
  selectedTf: string;
  tickers: string[];
  mas: string[];
}) {
  return (
    <section className="overflow-hidden rounded-lg border border-border/60 bg-card/35">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/50 px-5 py-4">
        <div>
          <h2 className="text-sm font-semibold tracking-tight">Heatmap</h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Cell color follows Bounce%; low-confidence cells keep the value at reduced opacity.
          </p>
        </div>
        <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
          <Sparkles className="h-3.5 w-3.5 text-[#f3c969]" />
          {selectedTf} | {mas.length} MAs | {tickers.length} tickers
        </div>
      </div>
      <div className="overflow-auto">
        <table className="w-full min-w-[760px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-border/50 bg-background/35">
              <th className="sticky left-0 z-10 w-[120px] bg-background/95 px-3 py-3 text-left text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                Ticker
              </th>
              {mas.map((ma) => (
                <th
                  key={ma}
                  className="min-w-[118px] px-3 py-3 text-center text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground"
                >
                  {ma}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {tickers.map((ticker) => (
              <tr key={ticker} className="border-b border-border/35 last:border-b-0">
                <td className="sticky left-0 z-10 bg-background/95 px-3 py-2.5 text-sm font-semibold text-foreground">
                  {ticker}
                </td>
                {mas.map((ma) => (
                  <HeatCell key={`${ticker}-${ma}`} metric={data.data[ticker]?.[selectedTf]?.[ma] ?? null} />
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function HeatCell({ metric }: { metric: OccurrenceMetric | null }) {
  const style = heatStyle(metric);
  if (!metric || metric.T === 0) {
    return (
      <td className="h-[58px] min-w-[118px] border-l border-border/30 px-2 py-2 text-center" style={style}>
        <span className="text-[11px] font-semibold">No data</span>
      </td>
    );
  }

  const tooltip = [
    `T=${metric.T}`,
    `B=${metric.B}`,
    `Bk=${metric.Bk}`,
    `F=${metric.F}`,
    `Bounce=${formatPct(metric.bounce_pct)}`,
    `Break=${formatPct(metric.break_pct)}`,
    `False=${formatPct(metric.false_pct)}`,
    `Tolerance=${metric.tolerance_pct == null ? "n/a" : `+/-${metric.tolerance_pct}%`}`,
  ].join(" | ");

  return (
    <td
      className="h-[58px] min-w-[118px] border-l border-border/30 px-2 py-2 text-center transition hover:brightness-105"
      style={style}
      title={tooltip}
    >
      <div className="text-base font-bold tabular">{formatPct(metric.bounce_pct)}</div>
      <div className="mt-0.5 text-[10px] font-semibold opacity-80">n={metric.T}</div>
    </td>
  );
}

function getCategoryTickers(data: OccurrenceMatrixPayload, selectedCategory: string): string[] {
  if (selectedCategory === "All") return data.tickers;
  return data.categories.find((category) => category.name === selectedCategory)?.tickers ?? data.tickers;
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
    }
  }

  return {
    avgBounce: bounceValues.length ? Math.round(bounceValues.reduce((sum, value) => sum + value, 0) / bounceValues.length) : null,
    events,
    lowSampleCells,
    best: meanReversion[0] ?? null,
  };
}

function heatStyle(metric: OccurrenceMetric | null): CSSProperties {
  if (!metric || metric.T === 0 || metric.bounce_pct == null) {
    return { backgroundColor: "#f0f0f0", color: "#9aa0a6" };
  }

  const bands =
    metric.bounce_pct < 25
      ? ["#fde2e2", "#7a1f1f"]
      : metric.bounce_pct < 35
        ? ["#fdedd2", "#6e4d18"]
        : metric.bounce_pct < 45
          ? ["#fff8d6", "#5d5418"]
          : metric.bounce_pct < 55
            ? ["#e1f1d6", "#345417"]
            : metric.bounce_pct < 65
              ? ["#bfe5b0", "#1f4012"]
              : ["#94d27a", "#143008"];

  return {
    backgroundColor: bands[0],
    color: bands[1],
    opacity: metric.low_sample ? 0.55 : 1,
  };
}

function formatPct(value: number | null): string {
  return value == null ? "n/a" : `${value}%`;
}

function OccurrenceSkeleton() {
  return (
    <main className="mx-auto w-full max-w-[1600px] flex-1 px-8 py-8">
      <div className="h-24 animate-pulse rounded-lg bg-card/30" />
      <div className="mt-5 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
        {[0, 1, 2, 3].map((item) => (
          <div key={item} className="h-24 animate-pulse rounded-lg bg-card/30" />
        ))}
      </div>
      <div className="mt-5 h-[560px] animate-pulse rounded-lg bg-card/25" />
    </main>
  );
}

function OccurrenceError() {
  return (
    <main className="mx-auto w-full max-w-[1600px] flex-1 px-8 py-8">
      <div className="rounded-lg border border-destructive/40 bg-destructive/10 p-8">
        <div className="text-lg font-semibold">Occurrence Matrix unavailable</div>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
          The API could not load the TradingView snapshots. Check the snapshot directory and retry the page.
        </p>
      </div>
    </main>
  );
}
