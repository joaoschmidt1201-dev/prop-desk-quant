"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ReactNode } from "react";
import { Activity, Brain, CalendarDays, Crosshair, Layers3, Trophy } from "lucide-react";
import { api, type AnalyticsGroup, type Filter } from "@/lib/api";
import { fmtMoney, fmtNum, fmtPct, pnlClass } from "@/lib/format";
import { DASHBOARD_REFETCH_INTERVAL_MS } from "@/lib/refresh";

type Props = { filter: Filter };

const WEEKDAY_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Unknown"];

export function AnalyticsPanel({ filter }: Props) {
  const { data, isLoading } = useQuery({
    queryKey: ["analytics", filter.months, filter.env],
    queryFn: () => api.analytics(filter),
    refetchInterval: DASHBOARD_REFETCH_INTERVAL_MS,
    refetchIntervalInBackground: true,
  });

  if (isLoading || !data) {
    return <div className="h-[620px] animate-pulse rounded-2xl border border-border/60 bg-card/30" />;
  }

  const weekdayRows = [...data.by_weekday].sort(
    (a, b) => WEEKDAY_ORDER.indexOf(a.key) - WEEKDAY_ORDER.indexOf(b.key),
  );
  const monthRows = data.by_month.map((m) => ({ ...m, key: m.label ?? m.key }));

  return (
    <section className="space-y-5 rounded-2xl border border-border/40 bg-card/30 p-6">
      <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
        <div>
          <div className="mb-2 inline-flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-[0.22em] text-primary/80">
            <Brain className="h-3 w-3" />
            Edge Lab
          </div>
          <h2 className="text-xl font-semibold tracking-tight">Performance attribution</h2>
          <p className="mt-1 max-w-2xl text-[12px] text-muted-foreground">
            Breaks results by structure, underlying, DTE and opening weekday to locate where the edge shows up.
          </p>
        </div>
        <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
          <MiniStat label="Sample" value={fmtMoney(data.summary.total_pnl)} tone={data.summary.total_pnl} />
          <MiniStat label="Trades" value={fmtNum(data.summary.n_trades)} />
          <MiniStat label="Win rate" value={fmtPct(data.summary.win_rate)} />
          <MiniStat label="Profit factor" value={fmtNum(data.summary.profit_factor)} />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-12">
        <ChartCard className="xl:col-span-7" title="Monthly P&L path" icon={<CalendarDays className="h-4 w-4" />}>
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={monthRows} margin={{ left: 6, right: 12, top: 16, bottom: 0 }}>
              <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" opacity={0.55} />
              <XAxis dataKey="key" tickLine={false} axisLine={false} fontSize={11} />
              <YAxis tickFormatter={(v) => `$${Math.round(Number(v) / 1000)}k`} tickLine={false} axisLine={false} fontSize={11} width={46} />
              <Tooltip content={<MoneyTooltip />} />
              <Line type="monotone" dataKey="pnl" stroke="var(--primary)" strokeWidth={3} dot={{ r: 5 }} activeDot={{ r: 7 }} />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>

        <div className="grid grid-cols-1 gap-4 xl:col-span-5">
          <InsightStrip insights={data.insights} />
          <WinLossCard avgWin={data.summary.avg_win} avgLoss={data.summary.avg_loss} />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <ChartCard title="Strategy family attribution" icon={<Layers3 className="h-4 w-4" />}>
          <HorizontalBars rows={data.by_strategy.slice(0, 8)} />
        </ChartCard>
        <ChartCard title="Underlying attribution" icon={<Crosshair className="h-4 w-4" />}>
          <HorizontalBars rows={data.by_underlying.slice(0, 8)} />
        </ChartCard>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-12">
        <ChartCard className="xl:col-span-7" title="DTE bucket edge" icon={<Activity className="h-4 w-4" />}>
          <VerticalBars rows={data.by_dte_bucket} />
        </ChartCard>
        <ChartCard className="xl:col-span-5" title="Open weekday edge" icon={<CalendarDays className="h-4 w-4" />}>
          <VerticalBars rows={weekdayRows} />
        </ChartCard>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <TradeRank title="Top winners" rows={data.top_winners} positive />
        <TradeRank title="Top losers" rows={data.top_losers} />
      </div>
    </section>
  );
}

function MiniStat({ label, value, tone }: { label: string; value: string; tone?: number }) {
  return (
    <div className="rounded-lg border border-border/30 bg-background/20 px-3 py-1.5">
      <div className="text-[9px] uppercase tracking-wider text-muted-foreground/70">{label}</div>
      <div className={`mt-0.5 text-sm font-semibold tabular ${tone == null ? "" : pnlClass(tone)}`}>{value}</div>
    </div>
  );
}

function ChartCard({ title, icon, children, className = "" }: { title: string; icon: ReactNode; children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl border border-border/30 bg-background/15 p-4 ${className}`}>
      <div className="mb-3 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/80">
        <span className="text-primary/80">{icon}</span>
        {title}
      </div>
      {children}
    </div>
  );
}

function HorizontalBars({ rows }: { rows: AnalyticsGroup[] }) {
  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={rows} layout="vertical" margin={{ left: 6, right: 16, top: 8, bottom: 0 }}>
        <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" opacity={0.45} horizontal={false} />
        <XAxis type="number" tickFormatter={(v) => `$${Math.round(Number(v) / 1000)}k`} tickLine={false} axisLine={false} fontSize={11} />
        <YAxis type="category" dataKey="key" tickLine={false} axisLine={false} fontSize={11} width={112} />
        <Tooltip content={<MoneyTooltip />} />
        <Bar dataKey="pnl" radius={[0, 8, 8, 0]}>
          {rows.map((r) => <Cell key={r.key} fill={r.pnl >= 0 ? "var(--gain)" : "var(--loss)"} opacity={0.86} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

function VerticalBars({ rows }: { rows: AnalyticsGroup[] }) {
  return (
    <ResponsiveContainer width="100%" height={250}>
      <BarChart data={rows} margin={{ left: 6, right: 12, top: 16, bottom: 0 }}>
        <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" opacity={0.45} />
        <XAxis dataKey="key" tickLine={false} axisLine={false} fontSize={11} interval={0} />
        <YAxis tickFormatter={(v) => `$${Math.round(Number(v) / 1000)}k`} tickLine={false} axisLine={false} fontSize={11} width={46} />
        <Tooltip content={<MoneyTooltip />} />
        <Bar dataKey="pnl" radius={[8, 8, 0, 0]}>
          {rows.map((r) => <Cell key={r.key} fill={r.pnl >= 0 ? "var(--gain)" : "var(--loss)"} opacity={0.86} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

function MoneyTooltip({ active, payload, label }: { active?: boolean; payload?: Array<{ value: number; payload: AnalyticsGroup }>; label?: string }) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  return (
    <div className="rounded-lg border border-border/70 bg-popover/95 px-3 py-2 text-xs shadow-xl">
      <div className="font-medium">{label ?? row.key}</div>
      <div className={`mt-1 tabular ${pnlClass(Number(payload[0].value))}`}>{fmtMoney(Number(payload[0].value))}</div>
      {row.n_trades != null && <div className="mt-1 text-muted-foreground">{row.n_trades} trades</div>}
      {row.win_rate != null && <div className="text-muted-foreground">WR {fmtPct(row.win_rate)}</div>}
    </div>
  );
}

function InsightStrip({ insights }: { insights: { label: string; value: string; detail: number | string }[] }) {
  return (
    <div className="grid grid-cols-1 gap-2">
      {insights.slice(0, 4).map((i) => (
        <div key={i.label} className="rounded-xl border border-border/60 bg-background/20 px-4 py-3">
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{i.label}</div>
          <div className="mt-1 flex items-baseline justify-between gap-3">
            <span className="text-sm font-semibold">{i.value}</span>
            <span className={`tabular text-sm ${typeof i.detail === "number" ? pnlClass(i.detail) : "text-muted-foreground"}`}>
              {typeof i.detail === "number" ? fmtMoney(i.detail) : i.detail}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}

function WinLossCard({ avgWin, avgLoss }: { avgWin: number | null; avgLoss: number | null }) {
  const ratio = avgWin && avgLoss ? Math.abs(avgWin / avgLoss) : null;
  return (
    <div className="rounded-xl border border-border/60 bg-background/20 p-4">
      <div className="mb-3 flex items-center gap-2 text-sm font-semibold">
        <Trophy className="h-4 w-4 text-primary" />
        Payoff profile
      </div>
      <div className="grid grid-cols-3 gap-2">
        <MiniStat label="Avg win" value={fmtMoney(avgWin)} tone={avgWin ?? undefined} />
        <MiniStat label="Avg loss" value={fmtMoney(avgLoss)} tone={avgLoss ?? undefined} />
        <MiniStat label="Payoff" value={ratio == null ? "—" : `${ratio.toFixed(2)}x`} />
      </div>
    </div>
  );
}

function TradeRank({ title, rows, positive = false }: { title: string; rows: { name: string; pnl: number; underlying: string; strategy: string; dte_bucket: string }[]; positive?: boolean }) {
  return (
    <div className="rounded-xl border border-border/60 bg-background/20 p-4">
      <div className="mb-3 text-sm font-semibold">{title}</div>
      <div className="space-y-2">
        {rows.map((t, idx) => (
          <div key={`${t.name}-${idx}`} className="flex items-center justify-between gap-3 rounded-lg border border-border/40 bg-card/30 px-3 py-2">
            <div className="min-w-0">
              <div className="truncate text-sm font-medium">{t.name}</div>
              <div className="mt-0.5 text-[11px] text-muted-foreground">{t.underlying} · {t.strategy} · {t.dte_bucket}</div>
            </div>
            <div className={`shrink-0 text-sm font-semibold tabular ${positive ? "text-[var(--gain)]" : pnlClass(t.pnl)}`}>
              {fmtMoney(t.pnl)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
