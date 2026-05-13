"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Activity, ArrowLeft, BarChart3, ChevronLeft, ChevronRight, Crosshair, Settings2, ShieldAlert, Sparkles, TrendingDown, TrendingUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api, type BacktestDetail as BacktestDetailType } from "@/lib/api";
import { fmtDate, fmtMoney, fmtNum, fmtPct, pnlClass } from "@/lib/format";
import { StrikeStructureCard, type LegRow } from "@/components/shared/strike-structure-card";

type BacktestTrade = {
  trade_date?: string | null;
  exp_date?: string | null;
  underlying?: string | null;
  dte_entry?: number | string | null;
  spot_entry?: number | string | null;
  iv_atm_pct?: number | string | null;
  expected_move?: number | string | null;
  em_pct?: number | string | null;
  short_put?: number | string | null;
  long_put?: number | string | null;
  short_call?: number | string | null;
  long_call?: number | string | null;
  delta_put?: number | string | null;
  delta_call?: number | string | null;
  mid_put_entry?: number | string | null;
  mid_call_entry?: number | string | null;
  mid_sp?: number | string | null;
  mid_lp?: number | string | null;
  mid_sc?: number | string | null;
  mid_lc?: number | string | null;
  total_credit?: number | string | null;
  spot_exit?: number | string | null;
  pnl_usd?: number | string | null;
  pnl_usd_at_exp?: number | string | null;
  effective_close_date?: string | null;
  effective_dit_at_close?: number | string | null;
  max_risk_usd?: number | string | null;
  in_range?: boolean | string | null;
  result?: string | null;
  exit_method?: string | null;
};

type BacktestDailyRow = {
  trade_date?: string | null;
  calendar_date?: string | null;
  dte_remaining?: number | string | null;
  spot?: number | string | null;
  put_mid?: number | string | null;
  call_mid?: number | string | null;
  debit_points?: number | string | null;
  pnl_usd?: number | string | null;
};

type PayoffPoint = {
  spot: number;
  pnl: number;
  profit: number;
  loss: number;
  pctFromEntry: number;
};

type JourneyPoint = {
  dit: number;
  dte: number;
  pnl: number;
  spot: number | null;
  date: string | null;
};

type PayoffReference = {
  key: string;
  label: string;
  value: number;
  color: string;
  dash?: string;
};

type PayoffSeries = {
  points: PayoffPoint[];
  references: PayoffReference[];
  domain: [number, number];
  marker: { label: string; spot: number; pnl: number } | null;
};

const DASH = "\u2014";

export function BacktestDetail({ id }: { id: string }) {
  const [rule, setRule] = useState<string>("Hold to Expiration");
  const [vixFilter, setVixFilter] = useState<string>("All");
  const [selectedIdx, setSelectedIdx] = useState<number | null>(0);
  const { data, isLoading, isError, isFetching } = useQuery({
    queryKey: ["backtest", id, rule, vixFilter],
    queryFn: () => api.backtest(id, rule, vixFilter),
    placeholderData: (prev) => prev,
  });

  if (isLoading && !data) return <Skeleton />;
  if (isError || !data) return <NotFound id={id} />;

  // Defensive: a stale API server may omit rule / available_rules / equity.
  // Normalize once so downstream renderers can't blow up on .map of undefined.
  const safeData: BacktestDetailType = {
    ...data,
    meta: {
      ...data.meta,
      rule: data.meta.rule ?? "Hold to Expiration",
      available_rules: data.meta.available_rules ?? ["Hold to Expiration"],
      vix_filter: data.meta.vix_filter ?? "All",
      available_vix_filters: data.meta.available_vix_filters ?? ["All"],
    },
    kpis: { ...data.kpis, equity: data.kpis.equity ?? [] },
    trades: data.trades ?? [],
    daily: data.daily ?? [],
  };

  return (
    <main className="mx-auto w-full max-w-[1600px] flex-1 px-8 py-8">
      <Header
        detail={safeData}
        rule={rule}
        onRuleChange={setRule}
        vixFilter={vixFilter}
        onVixFilterChange={setVixFilter}
        loading={isFetching}
      />
      <KpiBand detail={safeData} />
      <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-12">
        <div className="xl:col-span-8 space-y-6">
          <EquityCurveCard detail={safeData} />
          <DrawdownCard detail={safeData} />
          <PnlDistributionCard detail={safeData} />
        </div>
        <div className="xl:col-span-4 space-y-6">
          <PerformanceCard detail={safeData} />
          <RiskCard detail={safeData} />
        </div>
      </div>
      <YearlyBreakdownCard detail={safeData} />
      <div className="mt-6">
        <TradesTable detail={safeData} selectedIdx={selectedIdx} onSelect={setSelectedIdx} />
        <TradeInspector detail={safeData} index={selectedIdx} onChange={setSelectedIdx} />
      </div>
    </main>
  );
}

function Header({
  detail,
  rule,
  onRuleChange,
  vixFilter,
  onVixFilterChange,
  loading,
}: {
  detail: BacktestDetailType;
  rule: string;
  onRuleChange: (r: string) => void;
  vixFilter: string;
  onVixFilterChange: (v: string) => void;
  loading: boolean;
}) {
  const isOverridden = rule !== "Hold to Expiration";
  const hasRuleOptions = detail.meta.available_rules.length > 1;
  const availableVixFilters = detail.meta.available_vix_filters ?? ["All"];
  const hasVixOptions = availableVixFilters.length > 1;
  const vixApplied = vixFilter !== "All";
  return (
    <div className="mb-6 flex flex-col gap-3">
      <Link
        href="/backtests"
        className="inline-flex items-center gap-1.5 text-xs text-muted-foreground transition hover:text-foreground"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        All backtests
      </Link>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="mb-2 inline-flex items-center gap-2 rounded-full border border-primary/25 bg-primary/10 px-3 py-1 text-[11px] font-medium uppercase tracking-[0.22em] text-primary">
            <Sparkles className="h-3.5 w-3.5" />
            {detail.meta.strategy}
          </div>
          <h1 className="text-3xl font-semibold tracking-tight">
            {detail.meta.underlying} · {detail.meta.horizon}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {detail.meta.period ?? "no period"} · multiplier ${detail.meta.multiplier}/pt · mid-price fills
          </p>
          {detail.meta.description && (
            <p className="mt-2 max-w-2xl text-sm text-foreground/85 tabular">
              {detail.meta.description}
            </p>
          )}
        </div>
        <div className="flex flex-wrap items-end gap-4">
          {hasVixOptions && (
            <div className="flex flex-col items-end gap-1.5">
              <div className="flex items-center gap-2">
                <Activity className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="text-[10px] uppercase tracking-[0.22em] text-muted-foreground">VIX entry filter</span>
              </div>
              <Select value={vixFilter} onValueChange={(v) => v && onVixFilterChange(v)}>
                <SelectTrigger className="h-9 min-w-[160px] border-border/60 bg-card/50 text-sm focus:border-primary/60">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {availableVixFilters.map((v) => (
                    <SelectItem key={v} value={v} className="text-sm">
                      {v}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <div className="flex items-center gap-2 text-[11px]">
                {vixApplied ? (
                  <span className="rounded-full border border-primary/40 bg-primary/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-primary">
                    regime filter
                  </span>
                ) : (
                  <span className="text-muted-foreground">all regimes</span>
                )}
              </div>
            </div>
          )}
          {hasRuleOptions && (
            <div className="flex flex-col items-end gap-1.5">
              <div className="flex items-center gap-2">
                <Settings2 className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="text-[10px] uppercase tracking-[0.22em] text-muted-foreground">Close rule</span>
              </div>
              <Select value={rule} onValueChange={(v) => v && onRuleChange(v)}>
                <SelectTrigger className="h-9 min-w-[220px] border-border/60 bg-card/50 text-sm focus:border-primary/60">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {detail.meta.available_rules.map((r) => (
                    <SelectItem key={r} value={r} className="text-sm">
                      {r}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <div className="flex items-center gap-2 text-[11px]">
                {loading && <span className="text-muted-foreground">Re-simulating…</span>}
                {!loading && isOverridden && (
                  <span className="rounded-full border border-warning/40 bg-warning/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-[var(--warning)]">
                    rule applied
                  </span>
                )}
                {!loading && !isOverridden && (
                  <span className="text-muted-foreground">expiration P&L (raw)</span>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function KpiBand({ detail }: { detail: BacktestDetailType }) {
  const k = detail.kpis;
  const positive = k.total_pnl >= 0;
  const hasCapital = k.peak_capital_deployed != null && k.peak_capital_deployed > 0;
  const gridCols = hasCapital ? "xl:grid-cols-9" : "xl:grid-cols-7";
  return (
    <div className={`grid grid-cols-2 gap-3 sm:grid-cols-4 ${gridCols}`}>
      <KpiBlock
        label="Total P&L"
        tone={k.total_pnl}
        value={fmtMoney(k.total_pnl)}
        sub={
          k.total_pnl_pct != null && k.starting_capital
            ? `${fmtPct(k.total_pnl_pct)} on ${fmtMoney(k.starting_capital)}`
            : k.total_pnl_pct != null
            ? `${fmtPct(k.total_pnl_pct)} return`
            : undefined
        }
        highlight
        icon={positive ? <TrendingUp className="h-4 w-4" /> : <TrendingDown className="h-4 w-4" />}
      />
      <KpiBlock label="Win rate" value={fmtPct(k.win_rate)} sub={`${k.wins}W · ${k.losses}L`} />
      <KpiBlock label="Profit factor" value={fmtNum(k.profit_factor)} />
      <KpiBlock label="Expectancy / trade" tone={k.expectancy} value={fmtMoney(k.expectancy)} />
      <KpiBlock
        label="Max drawdown"
        tone={k.max_drawdown}
        value={fmtMoney(k.max_drawdown)}
        sub={k.max_drawdown_pct != null ? `${fmtPct(k.max_drawdown_pct)} of base` : undefined}
      />
      <KpiBlock label="Best / Worst" value={`${fmtMoney(k.best_trade)} / ${fmtMoney(k.worst_trade)}`} sub="USD per trade" small />
      <KpiBlock label="Sharpe (raw)" value={fmtNum(k.sharpe)} sub={`streak ${k.max_consecutive_losses}L`} />
      {hasCapital && (
        <>
          <KpiBlock
            label="Capital deployed (peak)"
            value={fmtMoney(k.peak_capital_deployed)}
            sub={
              k.capital_utilization_pct != null
                ? `${fmtPct(k.capital_utilization_pct)} of ${fmtMoney(k.starting_capital ?? 100000)} base`
                : undefined
            }
          />
          <KpiBlock
            label="Return on capital"
            tone={k.return_on_peak_capital_pct}
            value={fmtPct(k.return_on_peak_capital_pct)}
            sub={k.total_pnl_pct != null ? `vs ${fmtPct(k.total_pnl_pct)} on full base` : undefined}
            highlight
          />
        </>
      )}
    </div>
  );
}

export function KpiBlock({ label, value, sub, tone, highlight, small, icon }: {
  label: string;
  value: string;
  sub?: string;
  tone?: number | null;
  highlight?: boolean;
  small?: boolean;
  icon?: React.ReactNode;
}) {
  return (
    <div className={`rounded-xl border border-border/60 ${highlight ? "bg-gradient-to-b from-primary/15 to-card/40" : "bg-card/40"} px-4 py-3`}>
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className={`mt-1 flex items-baseline gap-1.5 ${small ? "text-sm" : "text-lg"} font-semibold tabular ${tone == null ? "" : pnlClass(tone)}`}>
        {value}
        {icon && <span className={tone != null ? pnlClass(tone) : "text-muted-foreground"}>{icon}</span>}
      </div>
      {sub && <div className="mt-0.5 text-[10px] text-muted-foreground">{sub}</div>}
    </div>
  );
}

export function ChartCard({ title, icon, children, sub }: { title: string; icon: React.ReactNode; children: React.ReactNode; sub?: string }) {
  return (
    <section className="rounded-2xl border border-border/60 bg-gradient-to-b from-card/70 to-card/35 p-5 shadow-2xl shadow-black/10">
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-primary">{icon}</span>
          <h3 className="text-sm font-semibold tracking-tight">{title}</h3>
        </div>
        {sub && <span className="text-[11px] text-muted-foreground">{sub}</span>}
      </div>
      {children}
    </section>
  );
}

export function YearlyBreakdownCard({ detail }: { detail: BacktestDetailType }) {
  const rows = detail.kpis.yearly_breakdown ?? [];
  if (rows.length === 0) return null;
  const totals = rows.reduce(
    (acc, r) => {
      acc.n_trades += r.n_trades;
      acc.wins += r.wins;
      acc.total_pnl += r.total_pnl;
      acc.total_pnl_pct += r.total_pnl_pct;
      return acc;
    },
    { n_trades: 0, wins: 0, total_pnl: 0, total_pnl_pct: 0 },
  );
  const totalWr = totals.n_trades ? totals.wins / totals.n_trades : null;
  return (
    <div className="mt-6">
      <ChartCard title="Yearly breakdown" icon={<BarChart3 className="h-4 w-4" />} sub={`${rows.length} years · entry-year grouping`}>
        <div className="overflow-x-auto">
          <table className="w-full text-sm tabular">
            <thead>
              <tr className="border-b border-border/60 text-[10px] uppercase tracking-wider text-muted-foreground">
                <th className="px-3 py-2 text-left font-medium">Year</th>
                <th className="px-3 py-2 text-right font-medium">Trades</th>
                <th className="px-3 py-2 text-right font-medium">Wins</th>
                <th className="px-3 py-2 text-right font-medium">WR</th>
                <th className="px-3 py-2 text-right font-medium">P&L</th>
                <th className="px-3 py-2 text-right font-medium">P&L %</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.year} className="border-b border-border/30 last:border-0">
                  <td className="px-3 py-2 text-left font-medium">{r.year}</td>
                  <td className="px-3 py-2 text-right">{r.n_trades}</td>
                  <td className="px-3 py-2 text-right text-muted-foreground">{r.wins}</td>
                  <td className="px-3 py-2 text-right">{fmtPct(r.win_rate)}</td>
                  <td className={`px-3 py-2 text-right font-medium ${pnlClass(r.total_pnl)}`}>{fmtMoney(r.total_pnl)}</td>
                  <td className={`px-3 py-2 text-right ${pnlClass(r.total_pnl_pct)}`}>{fmtPct(r.total_pnl_pct)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t-2 border-border/80 text-[11px] uppercase tracking-wider text-muted-foreground">
                <td className="px-3 py-2 text-left font-semibold">Total</td>
                <td className="px-3 py-2 text-right font-semibold">{totals.n_trades}</td>
                <td className="px-3 py-2 text-right font-semibold">{totals.wins}</td>
                <td className="px-3 py-2 text-right font-semibold">{fmtPct(totalWr)}</td>
                <td className={`px-3 py-2 text-right font-semibold ${pnlClass(totals.total_pnl)}`}>{fmtMoney(totals.total_pnl)}</td>
                <td className={`px-3 py-2 text-right font-semibold ${pnlClass(totals.total_pnl_pct)}`}>{fmtPct(totals.total_pnl_pct)}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      </ChartCard>
    </div>
  );
}

export function EquityCurveCard({ detail }: { detail: BacktestDetailType }) {
  const data = detail.kpis.equity.map((p) => ({ date: p.trade_date, cum: p.cumulative_pnl, pnl: p.pnl_usd }));
  const final = data.length ? data[data.length - 1].cum : 0;
  return (
    <ChartCard title="Equity curve" icon={<TrendingUp className="h-4 w-4" />} sub={`final ${fmtMoney(final)}`}>
      <ResponsiveContainer width="100%" height={300}>
        <AreaChart data={data} margin={{ left: 6, right: 12, top: 12, bottom: 0 }}>
          <defs>
            <linearGradient id="eq-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--primary)" stopOpacity={0.45} />
              <stop offset="100%" stopColor="var(--primary)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" opacity={0.45} />
          <XAxis dataKey="date" tickLine={false} axisLine={false} fontSize={11} minTickGap={32} />
          <YAxis tickFormatter={(v) => `$${Math.round(Number(v) / 1000)}k`} tickLine={false} axisLine={false} fontSize={11} width={56} />
          <Tooltip content={<EquityTooltip />} />
          <ReferenceLine y={0} stroke="var(--border)" strokeWidth={1} />
          <Area type="monotone" dataKey="cum" stroke="var(--primary)" strokeWidth={2.5} fill="url(#eq-fill)" />
        </AreaChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

export function DrawdownCard({ detail }: { detail: BacktestDetailType }) {
  const data = detail.kpis.equity.map((p) => ({ date: p.trade_date, dd: p.drawdown }));
  const max = Math.min(...data.map((d) => d.dd), 0);
  return (
    <ChartCard title="Underwater (drawdown)" icon={<ShieldAlert className="h-4 w-4" />} sub={`max ${fmtMoney(max)}`}>
      <ResponsiveContainer width="100%" height={200}>
        <AreaChart data={data} margin={{ left: 6, right: 12, top: 8, bottom: 0 }}>
          <defs>
            <linearGradient id="dd-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--loss)" stopOpacity={0.45} />
              <stop offset="100%" stopColor="var(--loss)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" opacity={0.45} />
          <XAxis dataKey="date" tickLine={false} axisLine={false} fontSize={11} minTickGap={32} />
          <YAxis tickFormatter={(v) => `$${Math.round(Number(v) / 1000)}k`} tickLine={false} axisLine={false} fontSize={11} width={56} />
          <Tooltip content={<DrawdownTooltip />} />
          <Area type="monotone" dataKey="dd" stroke="var(--loss)" strokeWidth={2} fill="url(#dd-fill)" />
        </AreaChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

export function PnlDistributionCard({ detail }: { detail: BacktestDetailType }) {
  const buckets = useMemo(() => buildHistogram(detail.kpis.equity.map((e) => e.pnl_usd), 10), [detail]);
  return (
    <ChartCard title="P&L distribution per trade" icon={<BarChart3 className="h-4 w-4" />} sub="bucket size adapts to range">
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={buckets} margin={{ left: 6, right: 12, top: 12, bottom: 0 }}>
          <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" opacity={0.45} />
          <XAxis dataKey="label" tickLine={false} axisLine={false} fontSize={10} interval={0} angle={-15} dy={8} height={48} />
          <YAxis tickLine={false} axisLine={false} fontSize={11} width={28} />
          <Tooltip content={<HistTooltip />} />
          <ReferenceLine x={buckets.find((b) => b.crossesZero)?.label} stroke="var(--border)" />
          <Bar dataKey="count" radius={[6, 6, 0, 0]}>
            {buckets.map((b, idx) => <Cell key={idx} fill={b.midpoint >= 0 ? "var(--gain)" : "var(--loss)"} opacity={0.85} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

export function PerformanceCard({ detail }: { detail: BacktestDetailType }) {
  const k = detail.kpis;
  return (
    <section className="rounded-2xl border border-border/60 bg-gradient-to-b from-card/70 to-card/35 p-5 shadow-2xl shadow-black/10">
      <h3 className="mb-4 text-sm font-semibold tracking-tight">Payoff profile</h3>
      <dl className="space-y-2.5 text-sm">
        <Row label="Avg win" value={fmtMoney(k.avg_win)} tone={k.avg_win} />
        <Row label="Avg loss" value={fmtMoney(k.avg_loss)} tone={k.avg_loss} />
        <Row label="Payoff ratio" value={k.payoff != null ? `${k.payoff.toFixed(2)}x` : "—"} />
        <Row label="In-range rate" value={fmtPct(k.in_range_rate)} />
        <Row label="Closed trades" value={fmtNum(k.n_trades)} />
        <Row label="Open trades" value={fmtNum(k.n_open)} sub="not in stats" />
      </dl>
    </section>
  );
}

export function RiskCard({ detail }: { detail: BacktestDetailType }) {
  const k = detail.kpis;
  return (
    <section className="rounded-2xl border border-border/60 bg-gradient-to-b from-card/70 to-card/35 p-5 shadow-2xl shadow-black/10">
      <h3 className="mb-4 text-sm font-semibold tracking-tight">Risk metrics</h3>
      <dl className="space-y-2.5 text-sm">
        <Row label="Max drawdown" value={fmtMoney(k.max_drawdown)} tone={k.max_drawdown} />
        <Row label="Worst trade" value={fmtMoney(k.worst_trade)} tone={k.worst_trade} />
        <Row label="Best trade" value={fmtMoney(k.best_trade)} tone={k.best_trade} />
        <Row label="Max consecutive losses" value={fmtNum(k.max_consecutive_losses)} />
        <Row label="Sharpe (raw, ann.)" value={fmtNum(k.sharpe)} sub="per-trade std" />
      </dl>
    </section>
  );
}

export function Row({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: number | null }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-border/30 pb-2 last:border-0">
      <div>
        <dt className="text-[11px] uppercase tracking-wider text-muted-foreground">{label}</dt>
        {sub && <div className="text-[10px] text-muted-foreground/70">{sub}</div>}
      </div>
      <dd className={`tabular text-sm font-semibold ${tone == null ? "" : pnlClass(tone)}`}>{value}</dd>
    </div>
  );
}

function TradesTable({
  detail,
  selectedIdx,
  onSelect,
}: {
  detail: BacktestDetailType;
  selectedIdx: number | null;
  onSelect: (idx: number) => void;
}) {
  const isSs42 = detail.meta.kind === "ss42";
  const headers = isSs42
    ? ["Trade", "Exp", "Spot in", "IV%", "Put / Call", "Credit", "Spot out", "P&L", "Result"]
    : ["Trade", "Exp", "Spot in", "IV%", "EM%", "Strikes (P/C)", "Credit", "P&L", "Result"];
  const rows = detail.trades;
  return (
    <section className="overflow-hidden rounded-2xl border border-border/60 bg-card/50">
      <div className="flex items-center justify-between border-b border-border/60 px-5 py-3">
        <h3 className="text-sm font-semibold tracking-tight">All trades</h3>
        <span className="text-xs text-muted-foreground tabular">{rows.length} rows</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border/40 text-[11px] uppercase tracking-wider text-muted-foreground">
              {headers.map((h) => <th key={h} className={`px-4 py-2 ${h === "P&L" || h === "Result" ? "text-right" : "text-left"} font-medium`}>{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.map((t, idx) => {
              const pnl = Number(t.pnl_usd ?? 0);
              const result = String(t.result ?? "");
              return (
                <tr
                  key={idx}
                  role="button"
                  tabIndex={0}
                  aria-selected={selectedIdx === idx}
                  onClick={() => onSelect(idx)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onSelect(idx);
                    }
                  }}
                  className={`cursor-pointer border-b border-border/30 transition last:border-0 hover:bg-card/40 focus-visible:bg-card/50 focus-visible:outline-none ${selectedIdx === idx ? "bg-primary/10 hover:bg-primary/15" : ""}`}
                >
                  <td className="px-4 py-2.5 font-medium tabular">{fmtDate(t.trade_date as string)}</td>
                  <td className="px-4 py-2.5 text-muted-foreground tabular">{fmtDate(t.exp_date as string)}</td>
                  <td className="px-4 py-2.5 tabular text-muted-foreground">{fmtNum(Number(t.spot_entry))}</td>
                  <td className="px-4 py-2.5 tabular text-muted-foreground">{t.iv_atm_pct != null ? `${Number(t.iv_atm_pct).toFixed(1)}%` : "—"}</td>
                  {isSs42 ? (
                    <>
                      <td className="px-4 py-2.5 tabular text-muted-foreground">
                        {t.short_put != null ? Number(t.short_put).toFixed(0) : "—"} / {t.short_call != null ? Number(t.short_call).toFixed(0) : "—"}
                      </td>
                      <td className="px-4 py-2.5 tabular">{fmtNum(Number(t.total_credit))}</td>
                      <td className="px-4 py-2.5 tabular text-muted-foreground">{t.spot_exit != null ? Number(t.spot_exit).toFixed(2) : "—"}</td>
                    </>
                  ) : (
                    <>
                      <td className="px-4 py-2.5 tabular text-muted-foreground">{t.em_pct != null ? `${Number(t.em_pct).toFixed(2)}%` : "—"}</td>
                      <td className="px-4 py-2.5 tabular text-muted-foreground">
                        {t.long_put != null ? Number(t.long_put).toFixed(0) : "—"}/{t.short_put != null ? Number(t.short_put).toFixed(0) : "—"}
                        {" · "}
                        {t.short_call != null ? Number(t.short_call).toFixed(0) : "—"}/{t.long_call != null ? Number(t.long_call).toFixed(0) : "—"}
                      </td>
                      <td className="px-4 py-2.5 tabular">{fmtNum(Number(t.total_credit))}</td>
                    </>
                  )}
                  <td className={`px-4 py-2.5 text-right font-semibold tabular ${pnlClass(pnl)}`}>{fmtMoney(pnl)}</td>
                  <td className="px-4 py-2.5 text-right">
                    <ResultBadge result={result} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ResultBadge({ result }: { result: string }) {
  const lower = result.toLowerCase();
  const map: Record<string, { bg: string; text: string }> = {
    win: { bg: "bg-[var(--gain)]/15", text: "text-[var(--gain)]" },
    loss: { bg: "bg-[var(--loss)]/15", text: "text-[var(--loss)]" },
    max_loss: { bg: "bg-[var(--loss)]/25", text: "text-[var(--loss)]" },
    open: { bg: "bg-warning/15", text: "text-[var(--warning)]" },
  };
  const style = map[lower] ?? { bg: "bg-muted/40", text: "text-muted-foreground" };
  return (
    <span className={`inline-flex rounded-md px-2 py-0.5 text-[11px] font-medium ${style.bg} ${style.text}`}>
      {result || "—"}
    </span>
  );
}

function TradeInspector({
  detail,
  index,
  onChange,
}: {
  detail: BacktestDetailType;
  index: number | null;
  onChange: (idx: number) => void;
}) {
  if (index == null || index < 0 || index >= detail.trades.length) return null;

  const trade = detail.trades[index] as BacktestTrade;
  const dailyRows = getTradeDailyRows(trade, detail.daily as BacktestDailyRow[]);
  const dteEntry = asNum(trade.dte_entry) ?? inferEntryDte(dailyRows) ?? (detail.meta.kind === "ss42" ? 42 : 7);
  const journey = buildJourneySeries(trade, dailyRows, dteEntry);
  const open = isOpenTrade(trade);
  const markerSpot = getPayoffMarkerSpot(trade, journey, open);
  const payoff = buildPayoffSeries(trade, detail.meta.kind, detail.meta.multiplier, markerSpot, open ? "Current" : "Exit");
  const pnl = asNum(trade.pnl_usd);
  const iv = asNum(trade.iv_atm_pct);
  const credit = asNum(trade.total_credit);
  const spotEntry = asNum(trade.spot_entry);
  const spotExit = asNum(trade.spot_exit);

  return (
    <div className="mt-4 space-y-4">
      <section className="rounded-2xl border border-border/60 bg-gradient-to-b from-card/70 to-card/35 p-5 shadow-2xl shadow-black/10">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <div className="mb-2 inline-flex items-center gap-2 text-[10px] font-medium uppercase tracking-[0.22em] text-primary">
              <Activity className="h-3.5 w-3.5" />
              Trade Inspector
            </div>
            <h3 className="text-lg font-semibold tracking-tight">
              {fmtDate(trade.trade_date)} <span className="text-muted-foreground">to</span> {fmtDate(trade.exp_date)}
            </h3>
            <p className="mt-1 text-xs text-muted-foreground">
              {detail.meta.strategy} {detail.meta.underlying} / {detail.meta.rule}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <ResultBadge result={open ? "OPEN" : String(trade.result ?? "")} />
            <span className="rounded-md border border-border/50 bg-card/40 px-2 py-1 text-[11px] text-muted-foreground tabular">
              {index + 1} / {detail.trades.length}
            </span>
            <Button
              type="button"
              variant="outline"
              size="icon-sm"
              disabled={index <= 0}
              aria-label="Previous trade"
              onClick={() => onChange(Math.max(0, index - 1))}
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <Button
              type="button"
              variant="outline"
              size="icon-sm"
              disabled={index >= detail.trades.length - 1}
              aria-label="Next trade"
              onClick={() => onChange(Math.min(detail.trades.length - 1, index + 1))}
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </section>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <KpiBlock label="Entry Spot" value={fmtNum(spotEntry)} />
        <KpiBlock label="IV ATM" value={iv != null ? fmtPct(iv / 100) : DASH} />
        <KpiBlock label="DTE Entry" value={`${fmtNum(dteEntry)} days`} />
        <KpiBlock
          label="Credit"
          value={credit != null ? `${fmtNum(credit)} pts` : DASH}
          sub={credit != null ? fmtMoney(credit * detail.meta.multiplier) : undefined}
        />
        <KpiBlock
          label="Exit Spot"
          value={open ? DASH : fmtNum(spotExit)}
          sub={!open && spotEntry != null && spotExit != null ? `${fmtSigned(spotExit - spotEntry, 0)} pts` : undefined}
          tone={!open && spotEntry != null && spotExit != null ? spotExit - spotEntry : null}
        />
        <KpiBlock
          label="P&L (USD)"
          value={open ? "In Progress" : fmtMoney(pnl)}
          tone={open ? null : pnl}
          sub={open ? "Open trade" : undefined}
          small={open}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-12">
        <div className="xl:col-span-7">
          <PayoffDiagram payoff={payoff} multiplier={detail.meta.multiplier} credit={credit} />
        </div>
        <div className="xl:col-span-5">
          <JourneyChart points={journey} dteEntry={dteEntry} open={open} tradePnl={pnl} />
        </div>
      </div>

      <BacktestStrikeStructure trade={trade} dailyRows={dailyRows} kind={detail.meta.kind} multiplier={detail.meta.multiplier} />
    </div>
  );
}

function PayoffDiagram({
  payoff,
  multiplier,
  credit,
}: {
  payoff: PayoffSeries | null;
  multiplier: number;
  credit: number | null;
}) {
  return (
    <ChartCard
      title="Expiration payoff"
      icon={<Crosshair className="h-4 w-4" />}
      sub={credit != null ? `${fmtNum(credit)} pts / ${fmtMoney(credit * multiplier)}` : undefined}
    >
      {!payoff ? (
        <EmptyChartState label="Payoff inputs unavailable" />
      ) : (
        <>
          <ResponsiveContainer width="100%" height={360}>
            <AreaChart data={payoff.points} margin={{ left: 6, right: 14, top: 12, bottom: 0 }}>
              <defs>
                <linearGradient id="payoff-gain-fill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--gain)" stopOpacity={0.34} />
                  <stop offset="100%" stopColor="var(--gain)" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="payoff-loss-fill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--loss)" stopOpacity={0.34} />
                  <stop offset="100%" stopColor="var(--loss)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" opacity={0.45} />
              <XAxis
                dataKey="spot"
                type="number"
                domain={payoff.domain}
                tickFormatter={(v) => Number(v).toFixed(0)}
                tickLine={false}
                axisLine={false}
                fontSize={11}
                minTickGap={28}
              />
              <YAxis tickFormatter={fmtAxisMoney} tickLine={false} axisLine={false} fontSize={11} width={58} />
              <Tooltip content={<PayoffTooltip />} />
              <ReferenceLine y={0} stroke="var(--border)" strokeWidth={1.2} />
              {payoff.references.map((ref) => (
                <ReferenceLine
                  key={ref.key}
                  x={ref.value}
                  stroke={ref.color}
                  strokeWidth={ref.key.startsWith("entry") ? 2 : 1.35}
                  strokeDasharray={ref.dash}
                />
              ))}
              <Area type="linear" dataKey="profit" stroke="none" fill="url(#payoff-gain-fill)" isAnimationActive={false} />
              <Area type="linear" dataKey="loss" stroke="none" fill="url(#payoff-loss-fill)" isAnimationActive={false} />
              <Line type="linear" dataKey="pnl" stroke="var(--primary)" strokeWidth={2.5} dot={false} activeDot={{ r: 4 }} isAnimationActive={false} />
              {payoff.marker && (
                <ReferenceDot
                  x={payoff.marker.spot}
                  y={payoff.marker.pnl}
                  r={5}
                  fill={payoff.marker.pnl >= 0 ? "var(--gain)" : "var(--loss)"}
                  stroke="var(--foreground)"
                  strokeWidth={1.5}
                />
              )}
            </AreaChart>
          </ResponsiveContainer>
          <div className="mt-3 flex flex-wrap gap-x-4 gap-y-2 text-[10px] uppercase tracking-wider text-muted-foreground">
            {payoff.references.map((ref) => (
              <span key={ref.key} className="inline-flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full" style={{ backgroundColor: ref.color }} />
                {ref.label} <span className="tabular text-foreground">{fmtNum(ref.value)}</span>
              </span>
            ))}
            {payoff.marker && (
              <span className="inline-flex items-center gap-1.5">
                <span className={`h-2 w-2 rounded-full ${payoff.marker.pnl >= 0 ? "bg-[var(--gain)]" : "bg-[var(--loss)]"}`} />
                {payoff.marker.label} <span className="tabular text-foreground">{fmtNum(payoff.marker.spot)}</span>
              </span>
            )}
          </div>
        </>
      )}
    </ChartCard>
  );
}

function JourneyChart({
  points,
  dteEntry,
  open,
  tradePnl,
}: {
  points: JourneyPoint[];
  dteEntry: number;
  open: boolean;
  tradePnl: number | null;
}) {
  const finalPnl = open ? points.at(-1)?.pnl ?? null : tradePnl ?? points.at(-1)?.pnl ?? null;
  const color = finalPnl == null ? "var(--primary)" : finalPnl < 0 ? "var(--loss)" : finalPnl > 0 ? "var(--gain)" : "var(--primary)";
  const checkpoint = findCheckpoint21Dte(points, dteEntry);
  return (
    <ChartCard title="P&L journey" icon={<TrendingUp className="h-4 w-4" />} sub={finalPnl != null ? fmtMoney(finalPnl) : undefined}>
      {points.length === 0 ? (
        <EmptyChartState label="Daily marks unavailable" />
      ) : (
        <ResponsiveContainer width="100%" height={360}>
          <AreaChart data={points} margin={{ left: 6, right: 14, top: 12, bottom: 0 }}>
            <defs>
              <linearGradient id="journey-fill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={color} stopOpacity={0.28} />
                <stop offset="100%" stopColor={color} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" opacity={0.45} />
            <XAxis
              dataKey="dit"
              type="number"
              domain={[0, Math.max(1, Math.ceil(dteEntry))]}
              tickLine={false}
              axisLine={false}
              fontSize={11}
              allowDecimals={false}
              label={{ value: "DIT", position: "insideBottomRight", offset: -2, fill: "var(--muted-foreground)", fontSize: 10 }}
            />
            <YAxis tickFormatter={fmtAxisMoney} tickLine={false} axisLine={false} fontSize={11} width={58} />
            <Tooltip content={<JourneyTooltip />} />
            <ReferenceLine y={0} stroke="var(--border)" strokeWidth={1.2} />
            <Area
              type="monotone"
              dataKey="pnl"
              stroke={color}
              strokeWidth={2.5}
              fill="url(#journey-fill)"
              dot={{ r: 2.4, fill: color, stroke: "var(--background)", strokeWidth: 1 }}
              activeDot={{ r: 5 }}
              isAnimationActive={false}
            />
            {checkpoint && (
              <ReferenceDot
                x={checkpoint.dit}
                y={checkpoint.pnl}
                r={5}
                fill="var(--warning)"
                stroke="var(--background)"
                strokeWidth={2}
              />
            )}
          </AreaChart>
        </ResponsiveContainer>
      )}
    </ChartCard>
  );
}

function BacktestStrikeStructure({
  trade,
  dailyRows,
  kind,
  multiplier,
}: {
  trade: BacktestTrade;
  dailyRows: BacktestDailyRow[];
  kind: BacktestDetailType["meta"]["kind"];
  multiplier: number;
}) {
  const entryDaily = dailyRows[0];
  const credit = asNum(trade.total_credit);
  const rows = kind === "ss42"
    ? buildSs42LegRows(trade, entryDaily)
    : buildIc7LegRows(trade);

  return (
    <StrikeStructureCard
      rows={rows}
      netCredit={credit}
      multiplier={multiplier}
      rightLabel={kind === "ss42" ? "Delta" : "Width"}
    />
  );
}

export function EmptyChartState({ label }: { label: string }) {
  return (
    <div className="flex h-[360px] items-center justify-center rounded-xl border border-border/40 bg-card/20 text-sm text-muted-foreground">
      {label}
    </div>
  );
}

function EquityTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  const cum = payload[0].payload.cum as number;
  const pnl = payload[0].payload.pnl as number;
  return (
    <div className="rounded-lg border border-border/70 bg-popover/95 px-3 py-2 text-xs shadow-xl">
      <div className="font-medium">{label}</div>
      <div className={`mt-1 tabular ${pnlClass(cum)}`}>cumulative {fmtMoney(cum)}</div>
      <div className={`tabular ${pnlClass(pnl)}`}>trade {fmtMoney(pnl)}</div>
    </div>
  );
}

function DrawdownTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  const v = payload[0].payload.dd as number;
  return (
    <div className="rounded-lg border border-border/70 bg-popover/95 px-3 py-2 text-xs shadow-xl">
      <div className="font-medium">{label}</div>
      <div className={`mt-1 tabular ${pnlClass(v)}`}>{fmtMoney(v)}</div>
    </div>
  );
}

function HistTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  const count = payload[0].value as number;
  return (
    <div className="rounded-lg border border-border/70 bg-popover/95 px-3 py-2 text-xs shadow-xl">
      <div className="font-medium">{label}</div>
      <div className="mt-1 tabular text-foreground">{count} trade{count === 1 ? "" : "s"}</div>
    </div>
  );
}

function PayoffTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload as PayoffPoint | undefined;
  if (!point) return null;
  const pct = `${point.pctFromEntry >= 0 ? "+" : ""}${point.pctFromEntry.toFixed(1)}%`;
  return (
    <div className="rounded-lg border border-border/70 bg-popover/95 px-3 py-2 text-xs shadow-xl">
      <div className="font-medium tabular">Spot {Math.round(point.spot).toLocaleString("en-US")} ({pct})</div>
      <div className={`mt-1 tabular ${pnlClass(point.pnl)}`}>theoretical {fmtMoney(point.pnl)}</div>
    </div>
  );
}

function JourneyTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload as JourneyPoint | undefined;
  if (!point) return null;
  return (
    <div className="rounded-lg border border-border/70 bg-popover/95 px-3 py-2 text-xs shadow-xl">
      <div className="font-medium">Day {point.dit} {point.date ? `/ ${fmtDate(point.date)}` : ""}</div>
      <div className="mt-1 tabular text-muted-foreground">DTE {point.dte}{point.spot != null ? ` / spot ${fmtNum(point.spot)}` : ""}</div>
      <div className={`tabular ${pnlClass(point.pnl)}`}>P&L {fmtMoney(point.pnl)}</div>
    </div>
  );
}

function asNum(value: unknown): number | null {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value === "string" && value.trim() !== "") {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

function fmtSigned(value: number | null | undefined, digits = 2): string {
  if (value == null || Number.isNaN(value)) return DASH;
  const abs = Math.abs(value).toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
  return `${value >= 0 ? "+" : "-"}${abs}`;
}

function fmtAxisMoney(value: unknown): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return "";
  if (Math.abs(n) >= 1000) return `$${Math.round(n / 1000)}k`;
  return `$${Math.round(n)}`;
}

function isOpenTrade(trade: BacktestTrade): boolean {
  return String(trade.exit_method ?? "").toLowerCase() === "fallback_entry";
}

function getTradeDailyRows(trade: BacktestTrade, daily: BacktestDailyRow[]): BacktestDailyRow[] {
  const tradeDate = String(trade.trade_date ?? "");
  if (!tradeDate) return [];
  return daily
    .filter((row) => String(row.trade_date ?? "") === tradeDate)
    .sort((a, b) => (asNum(b.dte_remaining) ?? -Infinity) - (asNum(a.dte_remaining) ?? -Infinity));
}

function inferEntryDte(rows: BacktestDailyRow[]): number | null {
  const dtes = rows.map((row) => asNum(row.dte_remaining)).filter((v): v is number => v != null);
  return dtes.length ? Math.max(...dtes) : null;
}

function buildJourneySeries(trade: BacktestTrade, dailyRows: BacktestDailyRow[], dteEntry: number): JourneyPoint[] {
  const points = dailyRows
    .map((row) => {
      const dte = asNum(row.dte_remaining);
      const pnl = asNum(row.pnl_usd);
      if (dte == null || pnl == null) return null;
      return {
        dit: Math.max(0, Math.round(dteEntry - dte)),
        dte: Math.round(dte),
        pnl,
        spot: asNum(row.spot),
        date: row.calendar_date ?? null,
      };
    })
    .filter((point): point is JourneyPoint => point != null)
    .sort((a, b) => a.dit - b.dit);

  if (points.length > 0) return points;

  const entrySpot = asNum(trade.spot_entry);
  if (isOpenTrade(trade)) {
    return [{ dit: 0, dte: Math.round(dteEntry), pnl: 0, spot: entrySpot, date: trade.trade_date ?? null }];
  }

  const finalPnl = asNum(trade.pnl_usd);
  const exitSpot = asNum(trade.spot_exit);
  if (finalPnl == null) return [];
  return [
    { dit: 0, dte: Math.round(dteEntry), pnl: 0, spot: entrySpot, date: trade.trade_date ?? null },
    { dit: Math.round(dteEntry), dte: 0, pnl: finalPnl, spot: exitSpot, date: trade.exp_date ?? null },
  ];
}

function findCheckpoint21Dte(points: JourneyPoint[], dteEntry: number): JourneyPoint | null {
  const checkpointDit = Math.round(dteEntry - 21);
  if (checkpointDit < 0) return null;
  return points.find((point) => point.dte === 21 || point.dit === checkpointDit) ?? null;
}

function getPayoffMarkerSpot(trade: BacktestTrade, journey: JourneyPoint[], open: boolean): number | null {
  if (open) return journey.at(-1)?.spot ?? asNum(trade.spot_exit) ?? null;
  return asNum(trade.spot_exit) ?? journey.at(-1)?.spot ?? null;
}

function buildPayoffSeries(
  trade: BacktestTrade,
  kind: BacktestDetailType["meta"]["kind"],
  multiplier: number,
  markerSpot: number | null,
  markerLabel: string,
): PayoffSeries | null {
  const spotEntry = asNum(trade.spot_entry);
  const credit = asNum(trade.total_credit);
  const shortPut = asNum(trade.short_put);
  const shortCall = asNum(trade.short_call);
  const longPut = asNum(trade.long_put);
  const longCall = asNum(trade.long_call);
  if (spotEntry == null || credit == null || shortPut == null || shortCall == null) return null;
  if (kind === "ic7" && (longPut == null || longCall == null)) return null;

  const lowerBep = shortPut - credit;
  const upperBep = shortCall + credit;
  const referenceValues: number[] = [spotEntry, lowerBep, upperBep, shortPut, shortCall];
  if (kind === "ic7" && longPut != null && longCall != null) referenceValues.push(longPut, longCall);

  let xMin = Math.min(...referenceValues);
  let xMax = Math.max(...referenceValues);
  for (const value of referenceValues) {
    if (value == null) continue;
    xMin = Math.min(xMin, value);
    xMax = Math.max(xMax, value);
  }
  const pad = Math.max((xMax - xMin) * 0.06, spotEntry * 0.01);
  xMin = Math.max(0, xMin - pad);
  xMax += pad;

  const steps = 200;
  const points = Array.from({ length: steps + 1 }, (_, idx) => {
    const spot = xMin + ((xMax - xMin) * idx) / steps;
    const pnl = payoffAtSpot(spot, trade, kind, multiplier);
    return {
      spot,
      pnl,
      profit: pnl >= 0 ? pnl : 0,
      loss: pnl <= 0 ? pnl : 0,
      pctFromEntry: ((spot - spotEntry) / spotEntry) * 100,
    };
  });

  const references: PayoffReference[] = [
    { key: "entry", label: "Entry", value: spotEntry, color: "var(--primary)", dash: "4 4" },
    { key: "bep-lower", label: "Lower B/E", value: lowerBep, color: "var(--warning)", dash: "5 5" },
    { key: "bep-upper", label: "Upper B/E", value: upperBep, color: "var(--warning)", dash: "5 5" },
    { key: "short-put", label: "Short Put", value: shortPut, color: "var(--loss)", dash: "3 3" },
    { key: "short-call", label: "Short Call", value: shortCall, color: "var(--loss)", dash: "3 3" },
  ];

  if (kind === "ic7" && longPut != null && longCall != null) {
    references.push(
      { key: "long-put", label: "Long Put", value: longPut, color: "var(--border)", dash: "2 4" },
      { key: "long-call", label: "Long Call", value: longCall, color: "var(--border)", dash: "2 4" },
    );
  }

  return {
    points,
    references,
    domain: [xMin, xMax],
    marker: markerSpot == null || markerSpot < xMin || markerSpot > xMax
      ? null
      : { label: markerLabel, spot: markerSpot, pnl: payoffAtSpot(markerSpot, trade, kind, multiplier) },
  };
}

function payoffAtSpot(
  spot: number,
  trade: BacktestTrade,
  kind: BacktestDetailType["meta"]["kind"],
  multiplier: number,
): number {
  const credit = asNum(trade.total_credit) ?? 0;
  const shortPut = asNum(trade.short_put) ?? 0;
  const shortCall = asNum(trade.short_call) ?? 0;
  if (kind === "ss42") {
    return (credit - Math.max(0, shortPut - spot) - Math.max(0, spot - shortCall)) * multiplier;
  }
  const longPut = asNum(trade.long_put) ?? 0;
  const longCall = asNum(trade.long_call) ?? 0;
  return (
    credit -
    Math.max(0, shortPut - spot) +
    Math.max(0, longPut - spot) -
    Math.max(0, spot - shortCall) +
    Math.max(0, spot - longCall)
  ) * multiplier;
}

function buildSs42LegRows(trade: BacktestTrade, entryDaily?: BacktestDailyRow): LegRow[] {
  return [
    {
      leg: "Short Put",
      side: "Sell",
      strike: asNum(trade.short_put),
      detail: fmtDelta(asNum(trade.delta_put)),
      mid: asNum(trade.mid_put_entry) ?? asNum(entryDaily?.put_mid),
    },
    {
      leg: "Short Call",
      side: "Sell",
      strike: asNum(trade.short_call),
      detail: fmtDelta(asNum(trade.delta_call)),
      mid: asNum(trade.mid_call_entry) ?? asNum(entryDaily?.call_mid),
    },
  ];
}

function buildIc7LegRows(trade: BacktestTrade): LegRow[] {
  const putWidth = widthBetween(trade.long_put, trade.short_put);
  const callWidth = widthBetween(trade.short_call, trade.long_call);
  return [
    { leg: "Long Put", side: "Buy", strike: asNum(trade.long_put), detail: putWidth, mid: asNum(trade.mid_lp) },
    { leg: "Short Put", side: "Sell", strike: asNum(trade.short_put), detail: putWidth, mid: asNum(trade.mid_sp) },
    { leg: "Short Call", side: "Sell", strike: asNum(trade.short_call), detail: callWidth, mid: asNum(trade.mid_sc) },
    { leg: "Long Call", side: "Buy", strike: asNum(trade.long_call), detail: callWidth, mid: asNum(trade.mid_lc) },
  ];
}

function widthBetween(a: unknown, b: unknown): string {
  const left = asNum(a);
  const right = asNum(b);
  if (left == null || right == null) return DASH;
  return `${fmtNum(Math.abs(right - left))} pts`;
}

function fmtDelta(value: number | null): string {
  if (value == null) return DASH;
  return fmtSigned(value, 2);
}

function buildHistogram(values: number[], binCount = 10) {
  if (!values.length) return [];
  const min = Math.min(...values);
  const max = Math.max(...values);
  if (min === max) return [{ label: fmtMoney(min), count: values.length, midpoint: min, crossesZero: min === 0 }];
  const span = max - min;
  const width = span / binCount;
  const bins = Array.from({ length: binCount }, (_, i) => ({
    lo: min + i * width,
    hi: min + (i + 1) * width,
    count: 0,
  }));
  for (const v of values) {
    const idx = Math.min(binCount - 1, Math.max(0, Math.floor((v - min) / width)));
    bins[idx].count += 1;
  }
  return bins.map((b) => ({
    label: `${fmtMoney(b.lo)}…${fmtMoney(b.hi)}`,
    count: b.count,
    midpoint: (b.lo + b.hi) / 2,
    crossesZero: b.lo <= 0 && b.hi >= 0,
  }));
}

function Skeleton() {
  return (
    <main className="mx-auto w-full max-w-[1600px] flex-1 px-8 py-8">
      <div className="h-8 w-48 animate-pulse rounded bg-card/40" />
      <div className="mt-2 h-10 w-96 animate-pulse rounded bg-card/40" />
      <div className="mt-6 grid grid-cols-7 gap-3">
        {Array.from({ length: 7 }).map((_, i) => (
          <div key={i} className="h-20 animate-pulse rounded-xl bg-card/30" />
        ))}
      </div>
      <div className="mt-6 h-[600px] animate-pulse rounded-2xl bg-card/20" />
    </main>
  );
}

function NotFound({ id }: { id: string }) {
  return (
    <main className="mx-auto w-full max-w-[1600px] flex-1 px-8 py-12">
      <div className="rounded-2xl border border-border/60 bg-card/40 p-8 text-center">
        <h2 className="text-lg font-semibold">Backtest "{id}" not found</h2>
        <p className="mt-2 text-sm text-muted-foreground">Check the URL or pick from the overview.</p>
        <Link href="/backtests" className="mt-4 inline-block rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground transition hover:opacity-90">
          Back to backtests
        </Link>
      </div>
    </main>
  );
}
