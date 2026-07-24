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
  entry_cons?: number | string | null;
  entry_spread?: number | string | null;
  spot_exit?: number | string | null;
  pnl_usd?: number | string | null;
  pnl_usd_at_exp?: number | string | null;
  effective_close_date?: string | null;
  effective_dit_at_close?: number | string | null;
  max_risk_usd?: number | string | null;
  in_range?: boolean | string | null;
  result?: string | null;
  exit_method?: string | null;
  // Batman (dual OTM butterfly) per-trade fields
  vix_entry?: number | string | null;
  call_lower?: number | string | null;
  call_center?: number | string | null;
  call_upper?: number | string | null;
  call_debit?: number | string | null;
  put_lower?: number | string | null;
  put_center?: number | string | null;
  put_upper?: number | string | null;
  put_debit?: number | string | null;
  call_atm?: number | string | null;
  call_lo?: number | string | null;
  call_up?: number | string | null;
  width_sigma?: number | string | null;
  // Layer B (1x2 square root hedge) per-roll fields
  roll_dir?: string | null;
  restruck?: number | string | null;
  delta_short?: number | string | null;
  delta_long?: number | string | null;
  cash_close?: number | string | null;
  cash_open?: number | string | null;
  net_roll?: number | string | null;
  net_roll_usd?: number | string | null;
  dd_index?: number | string | null;
  k_gap?: number | string | null;
  cum_pnl_pts?: number | string | null;
  iv_short?: number | string | null;
  iv_long?: number | string | null;
  dte_close?: number | string | null;
  spot_close?: number | string | null;
  // Hedge Hog (LPV 30DTE + far short put 90DTE) per-event fields
  lpv_debit?: number | string | null;
  far_short?: number | string | null;
  far_exp?: string | null;
  far_credit?: number | string | null;
  delta_far?: number | string | null;
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
  pnlClose?: number;   // Layer B: valor da posição no fechamento (T+0, ~35 DTE) — a "cova rasa"
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
  // legenda da linha T+0 (varia por família: Layer B "~35 DTE", Duck/HH = data do fechamento)
  closeLabel?: string;
  // 2º marcador: P&L NA EXPIRAÇÃO no spot de settle, quando a regra fechou ANTES (Duck).
  marker2?: { label: string; spot: number; pnl: number } | null;
};

const DASH = "\u2014";

export function BacktestDetail({ id }: { id: string }) {
  const [rule, setRule] = useState<string>("Hold to Expiration");
  const [vixFilter, setVixFilter] = useState<string>("All");
  const [widthRule, setWidthRule] = useState<string | undefined>(undefined);
  const [selectedIdx, setSelectedIdx] = useState<number | null>(0);
  const { data, isLoading, isError, isFetching } = useQuery({
    queryKey: ["backtest", id, rule, vixFilter, widthRule ?? ""],
    queryFn: () => api.backtest(id, rule, vixFilter, widthRule),
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
      width_rule: data.meta.width_rule ?? null,
      available_width_rules: data.meta.available_width_rules ?? [],
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
        widthRule={widthRule ?? safeData.meta.width_rule ?? undefined}
        onWidthRuleChange={setWidthRule}
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
      <VixBreakdownCard detail={safeData} />
      <DowBreakdownCard detail={safeData} />
      {/* Trade auditor ON TOP of the all-trades table (CZ: audit trade-by-trade) */}
      <div className="mt-6 space-y-4">
        <TradeInspector detail={safeData} index={selectedIdx} onChange={setSelectedIdx} />
        <TradesTable detail={safeData} selectedIdx={selectedIdx} onSelect={setSelectedIdx} />
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
  widthRule,
  onWidthRuleChange,
  loading,
}: {
  detail: BacktestDetailType;
  rule: string;
  onRuleChange: (r: string) => void;
  vixFilter: string;
  onVixFilterChange: (v: string) => void;
  widthRule?: string;
  onWidthRuleChange: (v: string) => void;
  loading: boolean;
}) {
  const isOverridden = rule !== "Hold to Expiration";
  const hasRuleOptions = detail.meta.available_rules.length > 1;
  const availableVixFilters = detail.meta.available_vix_filters ?? ["All"];
  const hasVixOptions = availableVixFilters.length > 1;
  const vixApplied = vixFilter !== "All";
  const availableWidthRules = detail.meta.available_width_rules ?? [];
  const hasWidthOptions = availableWidthRules.length > 1;
  const widthValue = widthRule ?? detail.meta.width_rule ?? availableWidthRules[0];
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
          {hasWidthOptions && (
            <div className="flex flex-col items-end gap-1.5">
              <div className="flex items-center gap-2">
                <Settings2 className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
                  {detail.meta.kind === "layerb" ? "Delta variant" : "Width / placement"}
                </span>
              </div>
              <Select value={widthValue} onValueChange={(v) => v && onWidthRuleChange(v)}>
                <SelectTrigger className="h-9 min-w-[170px] border-border/60 bg-card/50 text-sm focus:border-primary/60">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {availableWidthRules.map((w) => (
                    <SelectItem key={w} value={w} className="text-sm">{w}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <span className="text-[11px] text-muted-foreground">
                {detail.meta.kind === "layerb" ? "long-put delta at open (short fixed at Δ25)" : "short strike set by the debit rule"}
              </span>
            </div>
          )}
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

export function VixBreakdownCard({ detail }: { detail: BacktestDetailType }) {
  const rows = detail.kpis.vix_breakdown ?? [];
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
      <ChartCard
        title="VIX regime breakdown"
        icon={<Activity className="h-4 w-4" />}
        sub={`${rows.length} regimes · entry-VIX grouping (CZ/Ernie width table)`}
      >
        <div className="overflow-x-auto">
          <table className="w-full text-sm tabular">
            <thead>
              <tr className="border-b border-border/60 text-[10px] uppercase tracking-wider text-muted-foreground">
                <th className="px-3 py-2 text-left font-medium">VIX regime</th>
                <th className="px-3 py-2 text-right font-medium">Trades</th>
                <th className="px-3 py-2 text-right font-medium">Wins</th>
                <th className="px-3 py-2 text-right font-medium">WR</th>
                <th className="px-3 py-2 text-right font-medium">P&L</th>
                <th className="px-3 py-2 text-right font-medium">P&L %</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.bucket} className="border-b border-border/30 last:border-0">
                  <td className="px-3 py-2 text-left font-medium">{r.bucket}</td>
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

export function DowBreakdownCard({ detail }: { detail: BacktestDetailType }) {
  // Only meaningful for the daily-entry structures (0DTE/1DTE open every weekday).
  const h = detail.meta.horizon ?? "";
  // DoW faz sentido em QUALQUER estratégia que entra todo dia útil (0DTE/1DTE Batman, IC 0DTE, etc.)
  const dailyEntry = h.includes("0DTE") || h.includes("1DTE");
  const rows = detail.kpis.dow_breakdown ?? [];
  if (!dailyEntry || rows.length === 0) return null;
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
      <ChartCard
        title="Open-day breakdown (day of week)"
        icon={<Activity className="h-4 w-4" />}
        sub="Which entry weekday pays — entry-date grouping"
      >
        <div className="overflow-x-auto">
          <table className="w-full text-sm tabular">
            <thead>
              <tr className="border-b border-border/60 text-[10px] uppercase tracking-wider text-muted-foreground">
                <th className="px-3 py-2 text-left font-medium">Open day</th>
                <th className="px-3 py-2 text-right font-medium">Trades</th>
                <th className="px-3 py-2 text-right font-medium">Wins</th>
                <th className="px-3 py-2 text-right font-medium">WR</th>
                <th className="px-3 py-2 text-right font-medium">P&L</th>
                <th className="px-3 py-2 text-right font-medium">P&L %</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.dow} className="border-b border-border/30 last:border-0">
                  <td className="px-3 py-2 text-left font-medium">{r.dow}</td>
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
  const isPl5 = detail.meta.kind === "pl5";
  const isIbfly = detail.meta.kind === "ibfly";
  const isLayerB = detail.meta.kind === "layerb";
  const isHedgehog = detail.meta.kind === "hedgehog";
  const headers = isHedgehog
    ? ["Date", "Bear Put Exp", "Spot", "VIX", "Event", "Bear Put S/L", "Short Put (exp)", "Net credit", "P&L", "Result"]
    : isLayerB
    ? ["Date", "Exp", "Spot", "VIX", "Roll type", "Short / Long×2", "Δ s / l", "Net roll", "P&L wk", "Result"]
    : isSs42
    ? ["Trade", "Exp", "Spot in", "IV%", "Put / Call", "Credit", "Spot out", "P&L", "Result"]
    : isPl5
    ? ["Trade", "Exp", "Spot in", "IV%", "EM%", "Strikes (K1/K2/K3)", "Mid debit", "Spread", "P&L", "Result"]
    : isIbfly
    ? ["Trade", "Exp", "Spot in", "IV%", "EM%", "Strikes (Lo/ATM/Up)", "Credit", "P&L", "Result"]
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
                  <td className="px-4 py-2.5 tabular text-muted-foreground">
                    {isLayerB || isHedgehog
                      ? (t.vix_entry != null ? Number(t.vix_entry).toFixed(1) : "—")
                      : (t.iv_atm_pct != null ? `${Number(t.iv_atm_pct).toFixed(1)}%` : "—")}
                  </td>
                  {isHedgehog ? (
                    <>
                      <td className="px-4 py-2.5 tabular text-muted-foreground">{hedgehogEventLabel(String(t.roll_dir ?? ""))}</td>
                      <td className="px-4 py-2.5 tabular text-muted-foreground">
                        {t.short_put != null ? Number(t.short_put).toFixed(0) : "—"} / {t.long_put != null ? Number(t.long_put).toFixed(0) : "—"}
                      </td>
                      <td className="px-4 py-2.5 tabular text-muted-foreground">
                        {t.far_short != null ? Number(t.far_short).toFixed(0) : "—"}
                        {t.far_exp ? ` (${fmtDate(t.far_exp as string)})` : ""}
                      </td>
                      <td className="px-4 py-2.5 tabular text-muted-foreground">
                        {t.total_credit != null ? `${Number(t.total_credit).toFixed(2)} pts` : "—"}
                      </td>
                    </>
                  ) : isLayerB ? (
                    <>
                      <td className="px-4 py-2.5 tabular text-muted-foreground">
                        {(() => {
                          const dir = String(t.roll_dir ?? "");
                          if (dir === "up") return "Up · re-strike";
                          if (dir === "down") return "Down · keep strikes";
                          if (dir === "entry") return "Entry";
                          return dir || "—";
                        })()}
                      </td>
                      <td className="px-4 py-2.5 tabular text-muted-foreground">
                        {t.short_put != null ? Number(t.short_put).toFixed(0) : "—"} / {t.long_put != null ? Number(t.long_put).toFixed(0) : "—"}
                      </td>
                      <td className="px-4 py-2.5 tabular text-muted-foreground">
                        {t.delta_short != null ? Number(t.delta_short).toFixed(2) : "—"} / {t.delta_long != null ? Number(t.delta_long).toFixed(2) : "—"}
                      </td>
                      <td className="px-4 py-2.5 tabular text-muted-foreground">
                        {t.net_roll_usd != null ? fmtMoney(Number(t.net_roll_usd)) : "—"}
                      </td>
                    </>
                  ) : isSs42 ? (
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
                        {isPl5 ? (
                          `${t.put_upper != null ? Number(t.put_upper).toFixed(0) : "—"}/${t.put_center != null ? Number(t.put_center).toFixed(0) : "—"}/${t.put_lower != null ? Number(t.put_lower).toFixed(0) : "—"}`
                        ) : isIbfly ? (
                          `${t.call_lo != null ? Number(t.call_lo).toFixed(0) : "—"}/${t.call_atm != null ? Number(t.call_atm).toFixed(0) : "—"}/${t.call_up != null ? Number(t.call_up).toFixed(0) : "—"}`
                        ) : (
                          <>
                            {t.long_put != null ? Number(t.long_put).toFixed(0) : "—"}/{t.short_put != null ? Number(t.short_put).toFixed(0) : "—"}
                            {" · "}
                            {t.short_call != null ? Number(t.short_call).toFixed(0) : "—"}/{t.long_call != null ? Number(t.long_call).toFixed(0) : "—"}
                          </>
                        )}
                      </td>
                      <td className="px-4 py-2.5 tabular">{fmtNum(Number(t.total_credit))}</td>
                      {isPl5 && (
                        <td className="px-4 py-2.5 tabular text-muted-foreground">
                          {t.entry_spread != null ? fmtNum(Number(t.entry_spread)) : "—"}
                        </td>
                      )}
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
  const isHedgehog = detail.meta.kind === "hedgehog";
  const dteEntry = asNum(trade.dte_entry)
    ?? (isHedgehog ? daysBetween(trade.trade_date, trade.exp_date) : null)
    ?? inferEntryDte(dailyRows) ?? (detail.meta.kind === "ss42" ? 42 : 7);
  const journey = buildJourneySeries(trade, dailyRows, dteEntry);
  const open = isOpenTrade(trade);
  const markerSpot = getPayoffMarkerSpot(trade, journey, open);
  const payoff = buildPayoffSeries(trade, detail.meta.kind, detail.meta.multiplier, markerSpot, open ? "Current" : "Exit");
  const pnl = asNum(trade.pnl_usd);
  const iv = asNum(trade.iv_atm_pct);
  const credit = asNum(trade.total_credit);
  const spotEntry = asNum(trade.spot_entry);
  const spotExit = asNum(trade.spot_exit);
  const isBatman = detail.meta.kind === "batman";
  const vixEntry = asNum(trade.vix_entry);
  const putCenter = asNum(trade.put_center);
  const callCenter = asNum(trade.call_center);
  // Lower breakeven at entry: short put minus credit (in index points). The downside
  // cushion before the trade starts losing. % is distance below entry spot.
  const shortPut = asNum(trade.short_put);
  const creditPts = credit != null && detail.meta.multiplier ? credit / detail.meta.multiplier : null;
  const lowerBe = shortPut != null && creditPts != null ? shortPut - creditPts : null;
  const lowerBeDistPct =
    lowerBe != null && spotEntry != null && spotEntry > 0 ? ((spotEntry - lowerBe) / spotEntry) * 100 : null;

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
            {/* Layer B nunca segura até a expiração — rola/fecha na semana seguinte. Deixa as datas de
                expiração no título mas avisa aqui que a posição foi fechada antes. */}
            {detail.meta.kind === "layerb" && (
              <p className="mt-0.5 text-[11px] text-[var(--warning)]">
                {open
                  ? "Still open — rolls weekly, not held to expiration"
                  : `Rolled / closed on ${fmtDate((trade.effective_close_date as string) ?? "")} (before expiration)`}
              </p>
            )}
            {isHedgehog && (
              <p className="mt-0.5 text-[11px] text-[var(--warning)]">
                {open
                  ? "Still open — managed by triggers, not held to expiration"
                  : `Rolled / closed on ${fmtDate((trade.effective_close_date as string) ?? "")} — ${hedgehogEventLabel(String(trade.roll_dir ?? ""))}`}
              </p>
            )}
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

      {isBatman ? (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
          <KpiBlock label="VIX Entry" value={fmtNum(vixEntry)} />
          <KpiBlock label="DTE Entry" value={`${fmtNum(dteEntry)} days`} />
          <KpiBlock label="Net Debit" value={credit != null ? fmtMoney(credit) : DASH} sub="paid (max loss)" />
          <KpiBlock label="Put tent" value={fmtNum(putCenter)} sub="body strike" />
          <KpiBlock label="Call tent" value={fmtNum(callCenter)} sub="body strike" />
          <KpiBlock
            label="Settle / P&L"
            value={fmtMoney(pnl)}
            tone={pnl}
            sub={spotExit != null ? `spot ${fmtNum(spotExit)}` : undefined}
          />
        </div>
      ) : isHedgehog ? (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
          <KpiBlock label="VIX Entry" value={fmtNum(vixEntry)} />
          <KpiBlock
            label="Bear Put Spread (debit)"
            value={asNum(trade.lpv_debit) != null ? `${fmtNum(asNum(trade.lpv_debit))} pts` : DASH}
            sub={`${fmtNum(asNum(trade.long_put))} / ${fmtNum(asNum(trade.short_put))} · ${fmtNum(dteEntry)}d`}
          />
          <KpiBlock
            label="Short Put"
            value={asNum(trade.far_credit) != null ? `${fmtNum(asNum(trade.far_credit))} pts cr` : DASH}
            sub={`${fmtNum(asNum(trade.far_short))} · Δ ${fmtNum(asNum(trade.delta_far))}`}
          />
          <KpiBlock
            label="Net credit"
            value={credit != null ? `${fmtNum(credit)} pts` : DASH}
            sub={credit != null ? fmtMoney(credit * detail.meta.multiplier) : undefined}
          />
          <KpiBlock label="Event" value={hedgehogEventLabel(String(trade.roll_dir ?? ""))} small />
          <KpiBlock
            label="P&L (USD)"
            value={open ? "In Progress" : fmtMoney(pnl)}
            tone={open ? null : pnl}
            sub={!open && asNum(trade.spot_close) != null ? `closed @ ${fmtNum(asNum(trade.spot_close))}` : undefined}
            small={open}
          />
        </div>
      ) : (detail.meta.kind === "ic0dte" || detail.meta.kind === "ironfly") ? (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-7">
          <KpiBlock label="VIX Entry" value={fmtNum(vixEntry)} />
          <KpiBlock label="DTE Entry" value={`${fmtNum(dteEntry)} days`} />
          <KpiBlock label="Net Credit" value={credit != null ? fmtMoney(credit) : DASH} sub="received" />
          <KpiBlock
            label="Short Put"
            value={fmtNum(asNum(trade.short_put))}
            sub={detail.meta.kind === "ironfly" ? "ATM body" : undefined}
          />
          <KpiBlock
            label="Short Call"
            value={fmtNum(asNum(trade.short_call))}
            sub={detail.meta.kind === "ironfly" ? "ATM body" : undefined}
          />
          <KpiBlock
            label="Lower BE dist"
            value={lowerBeDistPct != null ? fmtPct(lowerBeDistPct / 100) : DASH}
            sub={lowerBe != null ? `BE ${fmtNum(lowerBe)} · below spot` : undefined}
          />
          <KpiBlock
            label="Settle / P&L"
            value={fmtMoney(pnl)}
            tone={pnl}
            sub={spotExit != null ? `spot ${fmtNum(spotExit)}` : undefined}
          />
        </div>
      ) : (
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
      )}

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
  const hasClose = !!payoff?.points.some((p) => p.pnlClose != null);
  return (
    <ChartCard
      title={hasClose ? "Payoff — at expiration vs at close" : "Expiration payoff"}
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
              <Line type="linear" dataKey="pnl" stroke="var(--primary)" strokeWidth={2.5} dot={false} activeDot={{ r: 4 }} isAnimationActive={false} name="At expiration" />
              {hasClose && (
                <Line type="monotone" dataKey="pnlClose" stroke="var(--warning)" strokeWidth={2} strokeDasharray="5 4" dot={false} activeDot={{ r: 4 }} isAnimationActive={false} name={payoff.closeLabel ?? "At close (~35 DTE)"} />
              )}
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
              {payoff.marker2 && (
                <ReferenceDot
                  x={payoff.marker2.spot}
                  y={payoff.marker2.pnl}
                  r={4}
                  fill="var(--primary)"
                  stroke="var(--foreground)"
                  strokeWidth={1}
                />
              )}
            </AreaChart>
          </ResponsiveContainer>
          <div className="mt-3 flex flex-wrap gap-x-4 gap-y-2 text-[10px] uppercase tracking-wider text-muted-foreground">
            {hasClose && (
              <>
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full" style={{ backgroundColor: "var(--primary)" }} />
                  At expiration
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full" style={{ backgroundColor: "var(--warning)" }} />
                  {payoff.closeLabel ?? "At close (~35 DTE)"}
                </span>
              </>
            )}
            {payoff.references.map((ref) => (
              <span key={ref.key} className="inline-flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full" style={{ backgroundColor: ref.color }} />
                {ref.label} <span className="tabular text-foreground">{fmtNum(ref.value)}</span>
              </span>
            ))}
            {payoff.marker && (
              <span className="inline-flex items-center gap-1.5">
                <span className={`h-2 w-2 rounded-full ${payoff.marker.pnl >= 0 ? "bg-[var(--gain)]" : "bg-[var(--loss)]"}`} />
                {payoff.marker.label} <span className="tabular text-foreground">{fmtNum(payoff.marker.spot)} · {fmtMoney(payoff.marker.pnl)}</span>
              </span>
            )}
            {payoff.marker2 && (
              <span className="inline-flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full" style={{ backgroundColor: "var(--primary)" }} />
                {payoff.marker2.label} <span className="tabular text-foreground">{fmtNum(payoff.marker2.spot)} · {fmtMoney(payoff.marker2.pnl)}</span>
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
    : kind === "batman"
    ? buildBatmanLegRows(trade)
    : kind === "ic0dte"
    ? buildIC0DTELegRows(trade)
    : kind === "ironfly"
    ? buildIronFlyLegRows(trade)
    : kind === "hedgehog"
    ? buildHedgehogLegRows(trade)
    : buildIc7LegRows(trade);

  return (
    <StrikeStructureCard
      rows={rows}
      netCredit={credit}
      multiplier={multiplier}
      rightLabel={kind === "ss42" || kind === "hedgehog" ? "Delta" : "Width"}
    />
  );
}

function buildIC0DTELegRows(trade: BacktestTrade): LegRow[] {
  // IC 0DTE: 4 strikes distintos. Asa = sp-lp (put) e lc-sc (call).
  const lp = asNum(trade.long_put), sp = asNum(trade.short_put);
  const sc = asNum(trade.short_call), lc = asNum(trade.long_call);
  const putWidth = sp != null && lp != null ? `${Math.round(sp - lp)} pt wing` : DASH;
  const callWidth = sc != null && lc != null ? `${Math.round(lc - sc)} pt wing` : DASH;
  return [
    { leg: "Long Put",   side: "Buy",  strike: lp, detail: putWidth, mid: null },
    { leg: "Short Put",  side: "Sell", strike: sp, detail: putWidth, mid: null },
    { leg: "Short Call", side: "Sell", strike: sc, detail: callWidth, mid: null },
    { leg: "Long Call",  side: "Buy",  strike: lc, detail: callWidth, mid: null },
  ];
}

function buildIronFlyLegRows(trade: BacktestTrade): LegRow[] {
  // Iron Fly: shorts no MESMO strike (body ATM); longs ±wing.
  const lp = asNum(trade.long_put), sp = asNum(trade.short_put);
  const sc = asNum(trade.short_call), lc = asNum(trade.long_call);
  const wing = sp != null && lp != null ? `${Math.round(sp - lp)} pt wing (= EM)` : DASH;
  return [
    { leg: "Long Put (low)",   side: "Buy",  strike: lp, detail: wing,     mid: null },
    { leg: "Short Put (ATM)",  side: "Sell", strike: sp, detail: "body",   mid: null },
    { leg: "Short Call (ATM)", side: "Sell", strike: sc, detail: "body",   mid: null },
    { leg: "Long Call (high)", side: "Buy",  strike: lc, detail: wing,     mid: null },
  ];
}

function buildHedgehogLegRows(trade: BacktestTrade): LegRow[] {
  // 3 pernas, 2 expirações: LPV (buy 30Δ / sell 20Δ, ~30 DTE) + far short put (~7Δ, 75-115 DTE).
  const exp = trade.exp_date ? fmtDate(trade.exp_date) : DASH;
  const fexp = trade.far_exp ? fmtDate(trade.far_exp) : DASH;
  return [
    { leg: `Bear Put Spread — Buy (${exp})`, side: "Buy", strike: asNum(trade.long_put), detail: fmtDelta(asNum(trade.delta_long)), mid: null },
    { leg: `Bear Put Spread — Sell (${exp})`, side: "Sell", strike: asNum(trade.short_put), detail: fmtDelta(asNum(trade.delta_short)), mid: null },
    { leg: `Short Put (${fexp})`, side: "Sell", strike: asNum(trade.far_short), detail: fmtDelta(asNum(trade.delta_far)), mid: asNum(trade.far_credit) },
  ];
}

function buildBatmanLegRows(trade: BacktestTrade): LegRow[] {
  const cl = asNum(trade.call_lower), cc = asNum(trade.call_center), cu = asNum(trade.call_upper);
  const pl = asNum(trade.put_lower), pc = asNum(trade.put_center), pu = asNum(trade.put_upper);
  const cWidth = cc != null && cl != null ? `${Math.round(cc - cl)} pt wing` : DASH;
  const pWidth = pc != null && pl != null ? `${Math.round(pc - pl)} pt wing` : DASH;
  // Two long OTM butterflies: each long 1 wing / short 2 body / long 1 wing.
  return [
    { leg: "Call +1 (low)", side: "Buy", strike: cl, detail: cWidth, mid: null },
    { leg: "Call −2 (body)", side: "Sell", strike: cc, detail: cWidth, mid: asNum(trade.call_debit) },
    { leg: "Call +1 (high)", side: "Buy", strike: cu, detail: cWidth, mid: null },
    { leg: "Put +1 (high)", side: "Buy", strike: pu, detail: pWidth, mid: null },
    { leg: "Put −2 (body)", side: "Sell", strike: pc, detail: pWidth, mid: asNum(trade.put_debit) },
    { leg: "Put +1 (low)", side: "Buy", strike: pl, detail: pWidth, mid: null },
  ];
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
  const hasClose = point.pnlClose != null;
  return (
    <div className="rounded-lg border border-border/70 bg-popover/95 px-3 py-2 text-xs shadow-xl">
      <div className="font-medium tabular">Spot {Math.round(point.spot).toLocaleString("en-US")} ({pct})</div>
      {hasClose ? (
        <>
          <div className="mt-1 flex items-center justify-between gap-3 tabular">
            <span className="text-muted-foreground">At expiration</span>
            <span className={pnlClass(point.pnl)}>{fmtMoney(point.pnl)}</span>
          </div>
          <div className="flex items-center justify-between gap-3 tabular">
            <span className="text-muted-foreground">At close (~35 DTE)</span>
            <span className={pnlClass(point.pnlClose as number)}>{fmtMoney(point.pnlClose as number)}</span>
          </div>
        </>
      ) : (
        <div className={`mt-1 tabular ${pnlClass(point.pnl)}`}>theoretical {fmtMoney(point.pnl)}</div>
      )}
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
  const m = String(trade.exit_method ?? "").toLowerCase();
  return m === "fallback_entry" || m === "open";   // "open" = última posição do Layer B, ainda rolando
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
  if (kind === "ic0dte" || kind === "ironfly") {
    const lp = asNum(trade.long_put);
    const sp = asNum(trade.short_put);
    const sc = asNum(trade.short_call);
    const lc = asNum(trade.long_call);
    const credit = asNum(trade.total_credit);
    if (lp == null || sp == null || sc == null || lc == null || credit == null) return null;
    const settle = asNum(trade.spot_exit);
    const entrySpot = asNum(trade.spot_entry);              // SPOT IN (spot no momento da entrada)
    const creditPts = credit / SPX_PT;                       // crédito USD -> pontos pra BEPs
    const lowerBep = sp - creditPts;
    const upperBep = sc + creditPts;
    const anchor = (sp + sc) / 2;                            // meio da zona de lucro (= ATM no IronFly)
    // Iron Duck: a regra pode ter fechado ANTES da expiração — o export grava onde (spot_close) e
    // quando (effective_close_date). Marcador = P&L REALIZADO no fechamento + linha T+0 ancorada;
    // 2º marcador = P&L da expiração no settle. 0DTE antigos não têm as colunas → comportamento velho.
    const spotClose = asNum(trade.spot_close);
    const realized = asNum(trade.pnl_usd);
    const closedEarly = trade.exit_method === "rule_triggered" && spotClose != null && realized != null;
    const refs = [lp, sp, sc, lc, lowerBep, upperBep];
    if (settle != null) refs.push(settle);
    if (entrySpot != null) refs.push(entrySpot);
    if (closedEarly && spotClose != null) refs.push(spotClose);
    let xMin = Math.min(...refs), xMax = Math.max(...refs);
    const pad = Math.max((xMax - xMin) * 0.08, anchor * 0.005);
    xMin = Math.max(0, xMin - pad);
    xMax += pad;
    const theoAtClose = closedEarly && spotClose != null ? ic0dteCloseValue(spotClose, trade) : null;
    const closeOffset = realized != null && theoAtClose != null ? realized - theoAtClose : 0;
    const steps = 240;
    const points = Array.from({ length: steps + 1 }, (_, idx) => {
      const spot = xMin + ((xMax - xMin) * idx) / steps;
      const pnl = payoffAtSpot(spot, trade, kind, multiplier);
      const closeRaw = closedEarly && theoAtClose != null ? ic0dteCloseValue(spot, trade) : null;
      return {
        spot, pnl,
        profit: pnl >= 0 ? pnl : 0, loss: pnl <= 0 ? pnl : 0,
        pctFromEntry: ((spot - anchor) / anchor) * 100,
        ...(closeRaw != null ? { pnlClose: closeRaw + closeOffset } : {}),
      };
    });
    const references: PayoffReference[] = [
      { key: "short-put", label: "Short Put", value: sp, color: "var(--loss)", dash: "3 3" },
      { key: "short-call", label: "Short Call", value: sc, color: "var(--loss)", dash: "3 3" },
      { key: "long-put", label: "Long Put", value: lp, color: "var(--border)", dash: "2 4" },
      { key: "long-call", label: "Long Call", value: lc, color: "var(--border)", dash: "2 4" },
      { key: "bep-lower", label: "Lower BEP", value: lowerBep, color: "var(--warning)", dash: "5 5" },
      { key: "bep-upper", label: "Upper BEP", value: upperBep, color: "var(--warning)", dash: "5 5" },
    ];
    if (entrySpot != null) {
      references.unshift({ key: "entry", label: "SPOT IN", value: entrySpot, color: "var(--primary)", dash: "4 4" });
    }
    if (closedEarly && spotClose != null && realized != null) {
      return {
        points,
        references,
        domain: [xMin, xMax],
        marker: { label: "Closed here", spot: spotClose, pnl: realized },
        marker2: settle == null
          ? null
          : { label: "At expiration", spot: settle, pnl: payoffAtSpot(settle, trade, kind, multiplier) },
        closeLabel: trade.effective_close_date ? `At close (${fmtDate(trade.effective_close_date)})` : "At close",
      };
    }
    return {
      points,
      references,
      domain: [xMin, xMax],
      marker: settle == null || settle < xMin || settle > xMax
        ? null
        : { label: markerLabel, spot: settle, pnl: payoffAtSpot(settle, trade, kind, multiplier) },
    };
  }
  if (kind === "batman") {
    const cl = asNum(trade.call_lower), cc = asNum(trade.call_center), cu = asNum(trade.call_upper);
    const pl = asNum(trade.put_lower), pc = asNum(trade.put_center), pu = asNum(trade.put_upper);
    if (cl == null || cc == null || cu == null || pl == null || pc == null || pu == null) return null;
    const settle = asNum(trade.spot_exit);
    const anchor = (pc + cc) / 2;                       // entre as duas tendas (proxy de "entry")
    const refs = [pl, pu, cl, cu];
    if (settle != null) refs.push(settle);
    let xMin = Math.min(...refs);
    let xMax = Math.max(...refs);
    const pad = Math.max((xMax - xMin) * 0.08, anchor * 0.012);
    xMin = Math.max(0, xMin - pad);
    xMax += pad;
    const steps = 240;
    const points = Array.from({ length: steps + 1 }, (_, idx) => {
      const spot = xMin + ((xMax - xMin) * idx) / steps;
      const pnl = payoffAtSpot(spot, trade, kind, multiplier);
      return { spot, pnl, profit: pnl >= 0 ? pnl : 0, loss: pnl <= 0 ? pnl : 0, pctFromEntry: ((spot - anchor) / anchor) * 100 };
    });
    const references: PayoffReference[] = [
      { key: "put-tent", label: "Put tent", value: pc, color: "var(--gain)", dash: "4 4" },
      { key: "call-tent", label: "Call tent", value: cc, color: "var(--gain)", dash: "4 4" },
      { key: "put-wing", label: "Put wing", value: pl, color: "var(--border)", dash: "2 4" },
      { key: "call-wing", label: "Call wing", value: cu, color: "var(--border)", dash: "2 4" },
    ];
    return {
      points,
      references,
      domain: [xMin, xMax],
      marker: settle == null || settle < xMin || settle > xMax
        ? null
        : { label: markerLabel, spot: settle, pnl: payoffAtSpot(settle, trade, kind, multiplier) },
    };
  }
  if (kind === "pl5") {
    // BWB de puts 1-2-2: K1 (long −30Δ) > K2 (short −18Δ, a tenda) > K3 (long −3Δ, a cauda).
    const k1 = asNum(trade.put_upper), k2 = asNum(trade.put_center), k3 = asNum(trade.put_lower);
    const credit = asNum(trade.total_credit);
    if (k1 == null || k2 == null || k3 == null || credit == null) return null;
    const settle = asNum(trade.spot_exit);
    const entrySpot = asNum(trade.spot_entry);
    const anchor = entrySpot ?? k1;
    const refs = [k1, k2, k3];
    if (settle != null) refs.push(settle);
    if (entrySpot != null) refs.push(entrySpot);
    let xMin = Math.min(...refs), xMax = Math.max(...refs);
    const pad = Math.max((xMax - xMin) * 0.08, anchor * 0.006);
    xMin = Math.max(0, xMin - pad);
    xMax += pad;
    const steps = 240;
    const points = Array.from({ length: steps + 1 }, (_, idx) => {
      const spot = xMin + ((xMax - xMin) * idx) / steps;
      const pnl = payoffAtSpot(spot, trade, kind, multiplier);
      return { spot, pnl, profit: pnl >= 0 ? pnl : 0, loss: pnl <= 0 ? pnl : 0, pctFromEntry: anchor ? ((spot - anchor) / anchor) * 100 : 0 };
    });
    const references: PayoffReference[] = [
      { key: "tent", label: "Tent (−18Δ)", value: k2, color: "var(--gain)", dash: "4 4" },
      { key: "long-top", label: "Long (−30Δ)", value: k1, color: "var(--border)", dash: "2 4" },
      { key: "tail", label: "Tail (−3Δ)", value: k3, color: "var(--border)", dash: "2 4" },
    ];
    if (entrySpot != null) {
      references.unshift({ key: "entry", label: "SPOT IN", value: entrySpot, color: "var(--primary)", dash: "4 4" });
    }
    return {
      points,
      references,
      domain: [xMin, xMax],
      marker: settle == null || settle < xMin || settle > xMax
        ? null
        : { label: markerLabel, spot: settle, pnl: payoffAtSpot(settle, trade, kind, multiplier) },
    };
  }
  if (kind === "ibfly") {
    // short call fly 1-2-1: +2 C (ATM) / -1 Clo (ATM-W) / -1 Cup (ATM+W). Long-vol: VALE no centro, GANHA nas asas.
    const C = asNum(trade.call_atm), Clo = asNum(trade.call_lo), Cup = asNum(trade.call_up);
    const cr = asNum(trade.total_credit);
    if (C == null || Clo == null || Cup == null || cr == null) return null;
    const settle = asNum(trade.spot_exit);
    const entrySpot = asNum(trade.spot_entry);
    const anchor = entrySpot ?? C;
    const refs = [Clo, C, Cup];
    if (settle != null) refs.push(settle);
    if (entrySpot != null) refs.push(entrySpot);
    let xMin = Math.min(...refs), xMax = Math.max(...refs);
    const pad = Math.max((xMax - xMin) * 0.10, anchor * 0.006);
    xMin = Math.max(0, xMin - pad); xMax += pad;
    const steps = 240;
    const points = Array.from({ length: steps + 1 }, (_, idx) => {
      const spot = xMin + ((xMax - xMin) * idx) / steps;
      const pnl = payoffAtSpot(spot, trade, kind, multiplier);
      return { spot, pnl, profit: pnl >= 0 ? pnl : 0, loss: pnl <= 0 ? pnl : 0, pctFromEntry: anchor ? ((spot - anchor) / anchor) * 100 : 0 };
    });
    const references: PayoffReference[] = [
      { key: "body", label: "Body (ATM)", value: C, color: "var(--loss)", dash: "4 4" },
      { key: "wing-lo", label: "Wing (−W)", value: Clo, color: "var(--border)", dash: "2 4" },
      { key: "wing-up", label: "Wing (+W)", value: Cup, color: "var(--border)", dash: "2 4" },
    ];
    if (entrySpot != null) references.unshift({ key: "entry", label: "SPOT IN", value: entrySpot, color: "var(--primary)", dash: "4 4" });
    return {
      points, references, domain: [xMin, xMax],
      marker: settle == null || settle < xMin || settle > xMax ? null
        : { label: markerLabel, spot: settle, pnl: payoffAtSpot(settle, trade, kind, multiplier) },
    };
  }
  if (kind === "layerb") {
    // 1x2 square root hedge: 2 long puts (K_long) + 1 short put (K_short). Desenha a assinatura:
    // crédito no topo, a COVA (pit) entre os strikes, e a cauda convexa que sobe no fundo (o hedge).
    const ks = asNum(trade.short_put), kl = asNum(trade.long_put);
    const entrySpot = asNum(trade.spot_entry);
    if (ks == null || kl == null || entrySpot == null) return null;
    // onde o trade FECHOU = spot no roll seguinte (a posição foi rolada lá). O marcador cai nesse
    // ponto, na linha T+0 (o P&L com que de fato fechou). Sem próximo roll (última linha) → sem marca.
    const spotClose = asNum(trade.spot_close);
    // range: desce o bastante p/ a cauda cruzar zero e sobe acima do spot; inclui o ponto de fecho
    let xMin = Math.max(0, entrySpot * 0.80);
    let xMax = entrySpot * 1.06;
    if (spotClose != null) { xMin = Math.min(xMin, spotClose * 0.995); xMax = Math.max(xMax, spotClose * 1.005); }
    // A linha T+0 é uma reconstrução BS (IV do open reprecificada ~7d depois): a FORMA (cova rasa)
    // é confiável, mas o NÍVEL erra quando a vol muda muito na semana. Ancoramos no ponto realizado:
    // deslocamos a curva por uma constante p/ passar exatamente por (spot_close, pnl_usd realizado).
    // Corrige o viés de nível com a única verdade que temos e mantém a forma. Marcador cai na curva.
    const realized = asNum(trade.pnl_usd);
    const theoAtClose = spotClose != null ? layerbCloseValue(spotClose, trade, multiplier) : null;
    const closeOffset = realized != null && theoAtClose != null ? realized - theoAtClose : 0;
    const steps = 240;
    const points = Array.from({ length: steps + 1 }, (_, idx) => {
      const spot = xMin + ((xMax - xMin) * idx) / steps;
      const pnl = payoffAtSpot(spot, trade, kind, multiplier);
      const closeRaw = layerbCloseValue(spot, trade, multiplier);   // linha T+0 (~35 DTE): a cova rasa
      const close = closeRaw != null ? closeRaw + closeOffset : null;
      return {
        spot, pnl,
        profit: pnl >= 0 ? pnl : 0, loss: pnl <= 0 ? pnl : 0,
        pctFromEntry: ((spot - entrySpot) / entrySpot) * 100,
        ...(close != null ? { pnlClose: close } : {}),
      };
    });
    const references: PayoffReference[] = [
      { key: "short-put", label: "Short Put (Δ25)", value: ks, color: "var(--loss)", dash: "3 3" },
      { key: "long-put", label: "Long Put ×2 (Δ10)", value: kl, color: "var(--gain)", dash: "4 4" },
      { key: "entry", label: "SPOT at open", value: entrySpot, color: "var(--primary)", dash: "4 4" },
    ];
    // marcador = onde o trade FECHOU de fato: spot no roll seguinte, com o P&L REALIZADO (pnl_usd,
    // o mesmo número da tabela). Como a curva de fechamento foi ancorada nesse ponto, o marcador
    // cai EXATAMENTE sobre a linha "At close".
    return {
      points,
      references,
      domain: [xMin, xMax],
      marker: spotClose == null || realized == null || spotClose < xMin || spotClose > xMax
        ? null
        : { label: "Closed here", spot: spotClose, pnl: realized },
    };
  }
  if (kind === "hedgehog") {
    // HH: 3 pernas em 2 expirações. Curva principal = vencimento do LPV (LPV intrínseco + residual
    // BS do far). Linha T+0 = valor na data do roll, ancorada no P&L realizado (padrão Layer B).
    const klg = asNum(trade.long_put), ksh = asNum(trade.short_put), kfar = asNum(trade.far_short);
    const entrySpot = asNum(trade.spot_entry);
    if (klg == null || ksh == null || kfar == null || entrySpot == null) return null;
    const spotClose = asNum(trade.spot_close);
    const realized = asNum(trade.pnl_usd);
    // range: da cauda abaixo do far strike (o risco real) até acima do spot de entrada
    let xMin = Math.max(0, Math.min(kfar * 0.96, entrySpot * 0.82));
    let xMax = entrySpot * 1.05;
    if (spotClose != null) { xMin = Math.min(xMin, spotClose * 0.995); xMax = Math.max(xMax, spotClose * 1.005); }
    const theoAtClose = spotClose != null ? hedgehogCloseValue(spotClose, trade, multiplier) : null;
    const closeOffset = realized != null && theoAtClose != null ? realized - theoAtClose : 0;
    const steps = 240;
    const points = Array.from({ length: steps + 1 }, (_, idx) => {
      const spot = xMin + ((xMax - xMin) * idx) / steps;
      const pnl = payoffAtSpot(spot, trade, kind, multiplier);
      const closeRaw = theoAtClose != null ? hedgehogCloseValue(spot, trade, multiplier) : null;
      return {
        spot, pnl,
        profit: pnl >= 0 ? pnl : 0, loss: pnl <= 0 ? pnl : 0,
        pctFromEntry: ((spot - entrySpot) / entrySpot) * 100,
        ...(closeRaw != null ? { pnlClose: closeRaw + closeOffset } : {}),
      };
    });
    const references: PayoffReference[] = [
      { key: "entry", label: "SPOT at open", value: entrySpot, color: "var(--primary)", dash: "4 4" },
      { key: "lpv-long", label: "Bear Put Spread — Buy (Δ30)", value: klg, color: "var(--gain)", dash: "4 4" },
      { key: "lpv-short", label: "Bear Put Spread — Sell (Δ20)", value: ksh, color: "var(--warning)", dash: "3 3" },
      { key: "far-short", label: "Short Put (Δ7)", value: kfar, color: "var(--loss)", dash: "3 3" },
    ];
    return {
      points,
      references,
      domain: [xMin, xMax],
      marker: spotClose == null || realized == null || spotClose < xMin || spotClose > xMax
        ? null
        : { label: "Closed here", spot: spotClose, pnl: realized },
      closeLabel: trade.effective_close_date ? `At close (${fmtDate(trade.effective_close_date)})` : "At close",
    };
  }
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
    { key: "entry", label: "SPOT IN", value: spotEntry, color: "var(--primary)", dash: "4 4" },
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

// SPX index options settle at $100/point; Batman P&L is in USD already (total_credit in USD).
const SPX_PT = 100;

// Normal CDF (Abramowitz-Stegun 7.1.26) — usada só pela linha T+0 do Layer B (valor no fechamento).
function normCdf(x: number): number {
  const t = 1 / (1 + 0.2316419 * Math.abs(x));
  const d = 0.3989422804014327 * Math.exp(-x * x / 2);
  const p = d * t * (0.31938153 + t * (-0.356563782 + t * (1.781477937 + t * (-1.821255978 + t * 1.330274429))));
  return x >= 0 ? 1 - p : p;
}

// Black-Scholes de uma PUT (r=0, sem dividendos): valor no tempo T (anos) dado sigma.
function bsPut(spot: number, strike: number, T: number, sigma: number): number {
  if (T <= 0 || sigma <= 0) return Math.max(0, strike - spot);   // no vencimento vira intrínseco
  const d1 = (Math.log(spot / strike) + (sigma * sigma / 2) * T) / (sigma * Math.sqrt(T));
  const d2 = d1 - sigma * Math.sqrt(T);
  return strike * normCdf(-d2) - spot * normCdf(-d1);
}

// Black-Scholes de uma CALL via paridade put-call (r=0): C = P + S − K.
function bsCall(spot: number, strike: number, T: number, sigma: number): number {
  if (T <= 0 || sigma <= 0) return Math.max(0, spot - strike);
  return bsPut(spot, strike, T, sigma) + spot - strike;
}

// Inversa da normal padrão (Acklam) — precisa p/ implicar IV a partir do delta gravado no motor.
function invNormCdf(p: number): number {
  if (p <= 0 || p >= 1) return NaN;
  const a = [-3.969683028665376e1, 2.209460984245205e2, -2.759285104469687e2, 1.38357751867269e2, -3.066479806614716e1, 2.506628277459239];
  const b = [-5.447609879822406e1, 1.615858368580409e2, -1.556989798598866e2, 6.680131188771972e1, -1.328068155288572e1];
  const c = [-7.784894002430293e-3, -3.223964580411365e-1, -2.400758277161838, -2.549732539343734, 4.374664141464968, 2.938163982698783];
  const d = [7.784695709041462e-3, 3.224671290700398e-1, 2.445134137142996, 3.754408661907416];
  const pl = 0.02425;
  if (p < pl) {
    const q = Math.sqrt(-2 * Math.log(p));
    return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1);
  }
  if (p > 1 - pl) return -invNormCdf(1 - p);
  const q = p - 0.5, r = q * q;
  return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q /
    (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1);
}

// IV implícita a partir do DELTA gravado na entrada (r=0). Resolve o quadrático em σ de
// d1 = [ln(S/K) + σ²T/2]/(σ√T): σ = (d1 ± √(d1² − 2·ln(S/K)))/√T. Pernas OTM (ln>0) → raiz
// menor (a maior é o ramo absurdo); guarda de sanidade 1%–300%.
function ivFromDelta(S: number, K: number, T: number, delta: number, isPut: boolean): number | null {
  if (S <= 0 || K <= 0 || T <= 0) return null;
  const p = isPut ? 1 + delta : delta;      // N(d1)
  if (!(p > 0 && p < 1)) return null;
  const d1 = invNormCdf(p);
  const L = Math.log(S / K);
  const disc = d1 * d1 - 2 * L;
  if (!Number.isFinite(d1) || disc < 0) return null;
  const s = Math.sqrt(disc), rt = Math.sqrt(T);
  const lo = (d1 - s) / rt, hi = (d1 + s) / rt;
  const sigma = L > 0 ? lo : hi;
  return sigma > 0.01 && sigma < 3 ? sigma : (hi > 0.01 && hi < 3 ? hi : null);
}

// Dias corridos entre duas datas "YYYY-MM-DD" (UTC, evita o gotcha de fuso do JS).
function daysBetween(a?: string | null, b?: string | null): number | null {
  if (!a || !b) return null;
  const ta = Date.parse(`${String(a).slice(0, 10)}T00:00:00Z`);
  const tb = Date.parse(`${String(b).slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(ta) || Number.isNaN(tb)) return null;
  return Math.round((tb - ta) / 86400000);
}

// Valor da estrutura Layer B (2 long puts + 1 short put) a `dteClose` dias, em USD.
// = 2·put(K_long) − 1·put(K_short) − custo de abrir (−cash_open). cash_open é crédito líquido em pts.
function layerbCloseValue(spot: number, trade: BacktestTrade, multiplier: number): number | null {
  const ks = asNum(trade.short_put), kl = asNum(trade.long_put);
  const ivs = asNum(trade.iv_short), ivl = asNum(trade.iv_long);
  const dteClose = asNum(trade.dte_close), cashOpen = asNum(trade.cash_open);
  if (ks == null || kl == null || ivs == null || ivl == null || dteClose == null || cashOpen == null) return null;
  if (ivs <= 0 || ivl <= 0) return null;
  const T = dteClose / 365;
  const structVal = 2 * bsPut(spot, kl, T, ivl) - bsPut(spot, ks, T, ivs);   // pts
  // P&L no fechamento = valor atual da estrutura + o caixa líquido recebido na abertura
  return (structVal + cashOpen) * multiplier;
}

// ── HEDGE HOG (LPV 30DTE + far short put ~90DTE) ─────────────────────────────
// IVs por perna implicadas dos DELTAS gravados na entrada do evento (não temos IV no export).
function hedgehogIvs(trade: BacktestTrade): { lg: number; sh: number; far: number } | null {
  const S = asNum(trade.spot_entry);
  const klg = asNum(trade.long_put), ksh = asNum(trade.short_put), kfar = asNum(trade.far_short);
  const dlg = asNum(trade.delta_long), dsh = asNum(trade.delta_short), dfar = asNum(trade.delta_far);
  const tLpv = daysBetween(trade.trade_date, trade.exp_date);
  const tFar = daysBetween(trade.trade_date, trade.far_exp);
  if (S == null || klg == null || ksh == null || kfar == null) return null;
  if (dlg == null || dsh == null || dfar == null || tLpv == null || tFar == null) return null;
  const lg = ivFromDelta(S, klg, tLpv / 365, dlg, true);
  const sh = ivFromDelta(S, ksh, tLpv / 365, dsh, true);
  const far = ivFromDelta(S, kfar, tFar / 365, dfar, true);
  if (lg == null || sh == null || far == null) return null;
  return { lg, sh, far };
}

// P&L do evento HH no FECHAMENTO (T+0 na data em que rolou): LPV + far reprecificados por BS no
// DTE residual. Nível ancorado no realizado (mesmo truque do Layer B); a FORMA é o que vale.
function hedgehogCloseValue(spot: number, trade: BacktestTrade, multiplier: number): number | null {
  const ivs = hedgehogIvs(trade);
  const klg = asNum(trade.long_put), ksh = asNum(trade.short_put), kfar = asNum(trade.far_short);
  const cash = (asNum(trade.far_credit) ?? 0) - (asNum(trade.lpv_debit) ?? 0);
  const close = trade.effective_close_date;
  const tLpv = daysBetween(close, trade.exp_date), tFar = daysBetween(close, trade.far_exp);
  if (ivs == null || klg == null || ksh == null || kfar == null || tLpv == null || tFar == null) return null;
  const lpv = bsPut(spot, klg, Math.max(0, tLpv) / 365, ivs.lg) - bsPut(spot, ksh, Math.max(0, tLpv) / 365, ivs.sh);
  const farRes = bsPut(spot, kfar, Math.max(0, tFar) / 365, ivs.far);
  return (lpv - farRes + cash) * multiplier;
}

// ── IRON DUCK: valor de fechar o IC na data do first-touch da regra (T+0) ────
// IV das pontas implicada dos deltas dos SHORTS na entrada; longs usam a mesma vol (skew plano —
// aproximação; o nível é ancorado no P&L realizado, então só a forma importa).
function ic0dteCloseValue(spot: number, trade: BacktestTrade): number | null {
  const lp = asNum(trade.long_put), sp = asNum(trade.short_put);
  const sc = asNum(trade.short_call), lc = asNum(trade.long_call);
  const creditUsd = asNum(trade.total_credit);
  const S = asNum(trade.spot_entry), dte = asNum(trade.dte_entry);
  const dp = asNum(trade.delta_put), dc = asNum(trade.delta_call);
  const tClose = daysBetween(trade.effective_close_date, trade.exp_date);
  if (lp == null || sp == null || sc == null || lc == null || creditUsd == null) return null;
  if (S == null || dte == null || dp == null || dc == null || tClose == null) return null;
  const ivP = ivFromDelta(S, sp, dte / 365, dp, true);
  const ivC = ivFromDelta(S, sc, dte / 365, dc, false);
  if (ivP == null || ivC == null) return null;
  const T = Math.max(0, tClose) / 365;
  const buyback = (bsPut(spot, sp, T, ivP) + bsCall(spot, sc, T, ivC))
    - (bsPut(spot, lp, T, ivP) + bsCall(spot, lc, T, ivC));
  return creditUsd - buyback * SPX_PT;
}

function hedgehogEventLabel(dir: string): string {
  const map: Record<string, string> = {
    entry: "Entry",
    T1_far_tp: "T1 · short put >50% TP",
    T1_far_roll: "T1 · short put roll up (bear put ≥14d)",
    T1_reopen: "T1 · short put >50%, reopen all",
    T2_lpv_tp: "T2 · bear put >80% TP",
    T3_lpv_roll: "T3 · bear put <7 DTE roll",
    T3_reopen: "T3 · bear put <7 DTE, reopen all",
    T4_reopen: "T4 · breach, reopen all",
    far_exp: "Short put expiry roll",
  };
  if (map[dir]) return map[dir];
  if (dir.endsWith("_flat")) return `${map[dir.replace(/_flat$/, "")] ?? dir} (flat)`;
  return dir || DASH;
}

function payoffAtSpot(
  spot: number,
  trade: BacktestTrade,
  kind: BacktestDetailType["meta"]["kind"],
  multiplier: number,
): number {
  if (kind === "batman") {
    // Two long OTM butterflies (call fly above, put fly below): +1/-2/+1 each.
    const cl = asNum(trade.call_lower) ?? 0, cc = asNum(trade.call_center) ?? 0, cu = asNum(trade.call_upper) ?? 0;
    const pl = asNum(trade.put_lower) ?? 0, pc = asNum(trade.put_center) ?? 0, pu = asNum(trade.put_upper) ?? 0;
    const callFly = Math.max(0, spot - cl) - 2 * Math.max(0, spot - cc) + Math.max(0, spot - cu);
    const putFly = Math.max(0, pl - spot) - 2 * Math.max(0, pc - spot) + Math.max(0, pu - spot);
    return (callFly + putFly) * SPX_PT - (asNum(trade.total_credit) ?? 0);
  }
  if (kind === "pl5") {
    // BWB de puts 1-2-2: +1 K1 (put_upper) / -2 K2 (put_center) / +2 K3 (put_lower). Tenda em K2,
    // vale em ~K3, e VOLTA a ganhar abaixo de K3 (cauda convexa). total_credit = débito pago (USD).
    const k1 = asNum(trade.put_upper) ?? 0, k2 = asNum(trade.put_center) ?? 0, k3 = asNum(trade.put_lower) ?? 0;
    const bwb = Math.max(0, k1 - spot) - 2 * Math.max(0, k2 - spot) + 2 * Math.max(0, k3 - spot);
    return bwb * SPX_PT - (asNum(trade.total_credit) ?? 0);
  }
  if (kind === "ibfly") {
    // Inverse (short) call fly 1-2-1: +2 C (ATM) / -1 Clo (ATM-W) / -1 Cup (ATM+W). Net credit.
    // Vale no centro (parado = perde), ganha nas asas (movimento). total_credit em USD.
    const C = asNum(trade.call_atm) ?? 0, Clo = asNum(trade.call_lo) ?? 0, Cup = asNum(trade.call_up) ?? 0;
    const terminal = 2 * Math.max(0, spot - C) - Math.max(0, spot - Clo) - Math.max(0, spot - Cup);
    return terminal * SPX_PT + (asNum(trade.total_credit) ?? 0);
  }
  if (kind === "ic0dte" || kind === "ironfly") {
    // Iron Condor / Iron Fly: long put + short put (credit spread) + short call + long call (credit spread).
    // Iron Fly = IC with short_put === short_call (ATM body). Mesma fórmula.
    // Perdas dos spreads capadas na asa; total_credit já em USD (multiplier=1).
    const lp = asNum(trade.long_put) ?? 0;
    const sp = asNum(trade.short_put) ?? 0;
    const sc = asNum(trade.short_call) ?? 0;
    const lc = asNum(trade.long_call) ?? 0;
    const putWing = sp - lp;
    const callWing = lc - sc;
    const putLoss = Math.max(0, Math.min(sp - spot, putWing));
    const callLoss = Math.max(0, Math.min(spot - sc, callWing));
    return (asNum(trade.total_credit) ?? 0) - (putLoss + callLoss) * SPX_PT;
  }
  if (kind === "layerb") {
    // 1x2 square root hedge: +2 long puts (K_long, d10) / -1 short put (K_short, d25).
    // cash_open = crédito líquido de abertura EM PONTOS (sh_mid - 2·lg_mid no motor).
    // Assinatura: crédito no topo, a COVA entre os strikes, cauda convexa (protege no crash).
    const ks = asNum(trade.short_put) ?? 0;
    const kl = asNum(trade.long_put) ?? 0;
    const cashOpen = asNum(trade.cash_open) ?? 0;
    const intrinsic = 2 * Math.max(0, kl - spot) - Math.max(0, ks - spot);
    return (intrinsic + cashOpen) * multiplier;
  }
  if (kind === "hedgehog") {
    // "Expiração" = vencimento do LPV (a perna curta): LPV vira intrínseco; o far short put ainda
    // tem DTE e entra pelo valor residual BS (IV implicada do delta de entrada). + caixa líquido.
    const klg = asNum(trade.long_put) ?? 0, ksh = asNum(trade.short_put) ?? 0, kfar = asNum(trade.far_short) ?? 0;
    const cash = (asNum(trade.far_credit) ?? 0) - (asNum(trade.lpv_debit) ?? 0);
    const lpvIntr = Math.max(0, klg - spot) - Math.max(0, ksh - spot);
    const tRes = Math.max(0, daysBetween(trade.exp_date, trade.far_exp) ?? 0) / 365;
    const ivs = hedgehogIvs(trade);
    const farRes = ivs != null && tRes > 0 ? bsPut(spot, kfar, tRes, ivs.far) : Math.max(0, kfar - spot);
    return (lpvIntr - farRes + cash) * multiplier;
  }
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
