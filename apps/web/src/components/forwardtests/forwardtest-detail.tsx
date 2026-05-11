"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Activity, ArrowLeft, Radar, Sparkles, TrendingDown, TrendingUp } from "lucide-react";
import {
  api,
  type BacktestDetail as BacktestDetailType,
  type ForwardtestDetail as ForwardtestDetailType,
  type ForwardtestEnv,
  type ForwardtestTrade,
  type LegSpec,
} from "@/lib/api";
import { fmtDate, fmtMoney, fmtNum, fmtPct, pnlClass } from "@/lib/format";
import { DASHBOARD_REFETCH_INTERVAL_MS } from "@/lib/refresh";
import {
  ChartCard,
  DrawdownCard,
  EquityCurveCard,
  EmptyChartState,
  KpiBlock,
  PerformanceCard,
  PnlDistributionCard,
  RiskCard,
  Row,
} from "@/components/backtests/backtest-detail";
import { StrikeStructureCard, type LegRow } from "@/components/shared/strike-structure-card";

type ForwardSelection = { kind: "open" | "closed"; index: number };

type ForwardJourneyPoint = {
  date: string | null;
  dit: number;
  pnl: number;
  delta: number | null;
};

const DASH = "—";

export function ForwardtestDetail({ strategyId, env = "CZ_Forward" }: { strategyId: string; env?: ForwardtestEnv }) {
  const [selected, setSelected] = useState<ForwardSelection | null>(null);
  const { data, isLoading, isError } = useQuery({
    queryKey: ["forwardtest", strategyId, env],
    queryFn: () => api.forwardtest(strategyId, env),
    refetchInterval: DASHBOARD_REFETCH_INTERVAL_MS,
    placeholderData: (prev) => prev,
  });

  if (isLoading && !data) return <Skeleton />;
  if (isError || !data) return <NotFound id={strategyId} />;

  const safe: ForwardtestDetailType = {
    ...data,
    kpis: { ...data.kpis, equity: data.kpis.equity ?? [] },
    open_trades: data.open_trades ?? [],
    closed_trades: data.closed_trades ?? [],
    daily_pnls: data.daily_pnls ?? [],
  };
  const totalOpen = sumPnl(safe.open_trades);
  const total = totalOpen + safe.kpis.total_pnl;
  const selectedTrade = selected
    ? selected.kind === "open"
      ? safe.open_trades[selected.index] ?? null
      : safe.closed_trades[selected.index] ?? null
    : null;

  // Adapter so we can reuse Backtest's chart/perf/risk cards.
  const backtestShaped: BacktestDetailType = {
    meta: {
      id: safe.meta.strategy_id,
      name: safe.meta.name,
      underlying: safe.meta.underlying ?? "",
      strategy: safe.meta.strategy_family ?? "",
      horizon: safe.meta.horizon ?? "",
      description: safe.meta.description,
      kind: "ic7",
      period: safe.meta.period,
      multiplier: 100,
      rule: "Live",
      available_rules: ["Live"],
    },
    kpis: safe.kpis,
    trades: [],
    daily: [],
  };

  return (
    <main className="mx-auto w-full max-w-[1600px] flex-1 px-8 py-8">
      <Header detail={safe} />
      <KpiBand detail={safe} totalOpen={totalOpen} total={total} />

      <section className="mt-8">
        <SectionHeader
          title="Open trades"
          subtitle={`${safe.open_trades.length} live · live mark-to-market refreshed every minute`}
        />
        <OpenTradesTable trades={safe.open_trades} selected={selected} onSelect={setSelected} isDebit={safe.meta.is_debit} />
      </section>

      <section className="mt-10">
        <SectionHeader
          title="Closed trades — analytics"
          subtitle={`${safe.kpis.n_trades} closed · KPIs computed only on closed trades`}
        />
        <div className="mt-4 grid grid-cols-1 gap-6 xl:grid-cols-12">
          <div className="xl:col-span-8 space-y-6">
            <EquityCurveCard detail={backtestShaped} />
            <DrawdownCard detail={backtestShaped} />
            <PnlDistributionCard detail={backtestShaped} />
          </div>
          <div className="xl:col-span-4 space-y-6">
            <PerformanceCard detail={backtestShaped} />
            <RiskCard detail={backtestShaped} />
            <RulesCard meta={safe.meta} />
          </div>
        </div>
        <div className="mt-6">
          <ClosedTradesTable trades={safe.closed_trades} selected={selected} onSelect={setSelected} isDebit={safe.meta.is_debit} />
        </div>
      </section>

      <TradeInspector trade={selectedTrade} isDebit={safe.meta.is_debit} />

      {safe.meta.legs_template.length > 0 && (
        <section className="mt-10">
          <SectionHeader title="Strategy structure" subtitle="Leg template declared in FT Strategies" />
          <div className="mt-4">
            <StrikeStructureCard
              rows={buildTemplateLegRows(safe.meta.legs_template)}
              netCredit={null}
              multiplier={100}
              rightLabel="Spec"
            />
          </div>
        </section>
      )}
    </main>
  );
}

function Header({ detail }: { detail: ForwardtestDetailType }) {
  return (
    <div className="mb-6 flex flex-col gap-3">
      <Link
        href="/forwardtests"
        className="inline-flex items-center gap-1.5 text-xs text-muted-foreground transition hover:text-foreground"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        All forward tests
      </Link>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="mb-2 inline-flex items-center gap-2 rounded-full border border-primary/25 bg-primary/10 px-3 py-1 text-[11px] font-medium uppercase tracking-[0.22em] text-primary">
            <Sparkles className="h-3.5 w-3.5" />
            {detail.meta.strategy_family ?? "Forward test"}
          </div>
          <h1 className="text-3xl font-semibold tracking-tight">
            {detail.meta.underlying ?? DASH}
            {detail.meta.horizon ? ` · ${detail.meta.horizon}` : ""}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {detail.meta.name}
            {detail.meta.tracking_since ? ` · tracking since ${fmtDate(detail.meta.tracking_since)}` : ""}
            {detail.meta.period ? ` · closed ${detail.meta.period}` : ""}
          </p>
          {detail.meta.description && (
            <p className="mt-2 max-w-2xl text-sm text-foreground/85 tabular">
              {detail.meta.description}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="rounded-full border border-primary/25 bg-primary/5 px-3 py-1 text-[10px] font-medium uppercase tracking-[0.22em] text-primary">
            <Radar className="mr-1 inline h-3 w-3" />
            live
          </span>
          {detail.meta.status && detail.meta.status !== "active" && (
            <span className="rounded-full border border-warning/40 bg-warning/10 px-3 py-1 text-[10px] font-medium uppercase tracking-[0.22em] text-[var(--warning)]">
              {detail.meta.status}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

function KpiBand({
  detail,
  totalOpen,
  total,
}: {
  detail: ForwardtestDetailType;
  totalOpen: number;
  total: number;
}) {
  const k = detail.kpis;
  const positive = total >= 0;
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-7">
      <KpiBlock
        label="Total P&L"
        tone={total}
        value={fmtMoney(total)}
        sub="open + closed"
        highlight
        icon={positive ? <TrendingUp className="h-4 w-4" /> : <TrendingDown className="h-4 w-4" />}
      />
      <KpiBlock label="Open P&L" tone={totalOpen} value={fmtMoney(totalOpen)} sub={`${detail.open_trades.length} live`} />
      <KpiBlock label="Closed P&L" tone={k.total_pnl} value={fmtMoney(k.total_pnl)} sub={`${k.n_trades} closed`} />
      <KpiBlock label="Win rate" value={fmtPct(k.win_rate)} sub={`${k.wins}W · ${k.losses}L`} />
      <KpiBlock label="Profit factor" value={fmtNum(k.profit_factor)} />
      <KpiBlock label="Max drawdown" tone={k.max_drawdown} value={fmtMoney(k.max_drawdown)} />
      <KpiBlock label="Sharpe (raw)" value={fmtNum(k.sharpe)} sub={`streak ${k.max_consecutive_losses}L`} />
    </div>
  );
}

function SectionHeader({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div className="flex items-end justify-between">
      <div>
        <h2 className="text-base font-semibold tracking-tight">{title}</h2>
        <p className="text-xs text-muted-foreground">{subtitle}</p>
      </div>
    </div>
  );
}

function OpenTradesTable({
  trades,
  selected,
  onSelect,
  isDebit,
}: {
  trades: ForwardtestTrade[];
  selected: ForwardSelection | null;
  onSelect: (selection: ForwardSelection) => void;
  isDebit: boolean;
}) {
  if (trades.length === 0) {
    return (
      <div className="mt-4 rounded-2xl border border-dashed border-border/60 bg-card/30 p-8 text-center text-sm text-muted-foreground">
        No open trades for this strategy yet.
      </div>
    );
  }
  return (
    <section className="mt-4 overflow-hidden rounded-2xl border border-border/60 bg-card/50">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border/40 text-[11px] uppercase tracking-wider text-muted-foreground">
              <th className="px-4 py-2 text-left font-medium">Trade</th>
              <th className="px-4 py-2 text-left font-medium">Sym</th>
              <th className="px-4 py-2 text-right font-medium">DTE</th>
              <th className="px-4 py-2 text-right font-medium">{isDebit ? "Net debit" : "Net credit"}</th>
              <th className="px-4 py-2 text-right font-medium">Max loss</th>
              <th className="px-4 py-2 text-right font-medium">Delta</th>
              <th className="px-4 py-2 text-right font-medium">P&L</th>
              <th className="px-4 py-2 text-right font-medium">% to LBE</th>
              <th className="px-4 py-2 text-right font-medium">% to UBE</th>
              <th className="px-4 py-2 text-left font-medium">Exp</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((t, index) => {
              const pnl = numOr(t.pnl_current);
              const delta = numOr(t.delta_current);
              const active = selected?.kind === "open" && selected.index === index;
              return (
                <tr
                  key={`${t.name}-${index}`}
                  aria-selected={active}
                  tabIndex={0}
                  onClick={() => onSelect({ kind: "open", index })}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onSelect({ kind: "open", index });
                    }
                  }}
                  className={`cursor-pointer border-b border-border/30 transition last:border-0 ${
                    active ? "bg-primary/10" : "hover:bg-card/40"
                  }`}
                >
                  <td className="px-4 py-2.5 font-medium">{t.name}</td>
                  <td className="px-4 py-2.5 text-muted-foreground">{t.underlying}</td>
                  <td className="px-4 py-2.5 text-right tabular">{fmtNum(t.dte_remaining)}</td>
                  <td className="px-4 py-2.5 text-right tabular">{fmtMoney(t.net_credit)}</td>
                  <td className="px-4 py-2.5 text-right tabular text-muted-foreground">{fmtMoney(t.max_loss)}</td>
                  <td className={`px-4 py-2.5 text-right tabular ${delta == null ? "" : pnlClass(delta)}`}>{fmtNum(delta)}</td>
                  <td className={`px-4 py-2.5 text-right font-semibold tabular ${pnlClass(pnl)}`}>{fmtMoney(pnl)}</td>
                  <td className="px-4 py-2.5 text-right tabular text-muted-foreground">{fmtPctField(t.pct_to_lw_be)}</td>
                  <td className="px-4 py-2.5 text-right tabular text-muted-foreground">{fmtPctField(t.pct_to_up_be)}</td>
                  <td className="px-4 py-2.5 text-muted-foreground tabular">{fmtDate(asString(t.exp_date) ?? asString(t.visual_exp_date))}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ClosedTradesTable({
  trades,
  selected,
  onSelect,
  isDebit,
}: {
  trades: ForwardtestTrade[];
  selected: ForwardSelection | null;
  onSelect: (selection: ForwardSelection) => void;
  isDebit: boolean;
}) {
  if (trades.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-border/60 bg-card/30 p-8 text-center text-sm text-muted-foreground">
        No closed trades for this strategy yet.
      </div>
    );
  }
  return (
    <section className="overflow-hidden rounded-2xl border border-border/60 bg-card/50">
      <div className="flex items-center justify-between border-b border-border/60 px-5 py-3">
        <h3 className="text-sm font-semibold tracking-tight">Closed trades</h3>
        <span className="text-xs text-muted-foreground tabular">{trades.length} rows</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border/40 text-[11px] uppercase tracking-wider text-muted-foreground">
              <th className="px-4 py-2 text-left font-medium">Trade</th>
              <th className="px-4 py-2 text-left font-medium">Open</th>
              <th className="px-4 py-2 text-left font-medium">Close</th>
              <th className="px-4 py-2 text-right font-medium">Days held</th>
              <th className="px-4 py-2 text-right font-medium">{isDebit ? "Net debit" : "Net credit"}</th>
              <th className="px-4 py-2 text-right font-medium">P&L</th>
              <th className="px-4 py-2 text-right font-medium">Result</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((t, index) => {
              const pnl = numOr(t.pnl_current ?? (t.pnl as number | undefined));
              const active = selected?.kind === "closed" && selected.index === index;
              const result = pnl == null ? "—" : pnl >= 0 ? "WIN" : "LOSS";
              return (
                <tr
                  key={`${t.name}-${index}`}
                  aria-selected={active}
                  tabIndex={0}
                  onClick={() => onSelect({ kind: "closed", index })}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onSelect({ kind: "closed", index });
                    }
                  }}
                  className={`cursor-pointer border-b border-border/30 transition last:border-0 ${
                    active ? "bg-primary/10" : "hover:bg-card/40"
                  }`}
                >
                  <td className="px-4 py-2.5 font-medium">{t.name}</td>
                  <td className="px-4 py-2.5 text-muted-foreground tabular">{fmtDate(asString(t.open_date) ?? asString(t.visual_open_date))}</td>
                  <td className="px-4 py-2.5 text-muted-foreground tabular">{fmtDate(asString(t.inferred_close_date))}</td>
                  <td className="px-4 py-2.5 text-right tabular text-muted-foreground">{fmtNum(t.days_held)}</td>
                  <td className="px-4 py-2.5 text-right tabular">{fmtMoney(t.net_credit)}</td>
                  <td className={`px-4 py-2.5 text-right font-semibold tabular ${pnlClass(pnl)}`}>{fmtMoney(pnl)}</td>
                  <td className="px-4 py-2.5 text-right">
                    <span className={`inline-flex rounded-md px-2 py-0.5 text-[11px] font-medium ${
                      result === "WIN"
                        ? "bg-[var(--gain)]/15 text-[var(--gain)]"
                        : result === "LOSS"
                          ? "bg-[var(--loss)]/15 text-[var(--loss)]"
                          : "bg-muted/40 text-muted-foreground"
                    }`}>
                      {result}
                    </span>
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

function TradeInspector({ trade, isDebit }: { trade: ForwardtestTrade | null; isDebit: boolean }) {
  if (!trade) return null;

  const openDate = asString(trade.open_date) ?? asString(trade.visual_open_date);
  const closeDate = asString(trade.inferred_close_date) ?? asString(trade.exp_date) ?? asString(trade.visual_exp_date);
  const journey = buildForwardJourneySeries(trade);
  const pnl = currentTradePnl(trade);
  const milestones = trade.milestones;
  const maxProfit = numOr(milestones?.max_profit_usd);
  const netDebit = numOr(milestones?.net_debit_usd) ?? (isDebit ? numOr(trade.net_credit) : null);
  const pctOfMaxProfit = pnl != null && maxProfit != null && maxProfit > 0 ? pnl / maxProfit : null;
  const delta = numOr(trade.delta_current ?? trade.delta);
  const dteRemaining = numOr(trade.dte_remaining);
  const dteOpenLabel =
    (typeof trade.dte_open_raw === "string" && trade.dte_open_raw.trim()) ||
    (trade.dte_open != null ? String(trade.dte_open) : null);
  const dit = calcTradeDit(trade, journey.at(-1)?.date ?? null);
  const maxDdSeen = numOr(milestones?.max_dd_from_peak);
  const strikeRows = buildTradeStrikeRows(trade);
  const open = Boolean(trade.is_active);

  return (
    <section className="mt-10 space-y-4">
      <div className="rounded-2xl border border-border/60 bg-gradient-to-b from-card/70 to-card/35 p-5 shadow-2xl shadow-black/10">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <div className="mb-2 inline-flex items-center gap-2 text-[10px] font-medium uppercase tracking-[0.22em] text-primary">
              <Activity className="h-3.5 w-3.5" />
              Trade Inspector
            </div>
            <h3 className="text-lg font-semibold tracking-tight">{trade.name}</h3>
            <p className="mt-1 text-xs text-muted-foreground tabular">
              {fmtDate(openDate)} <span className="mx-1">to</span> {open ? "open" : fmtDate(closeDate)}
            </p>
          </div>
          <span
            className={`w-fit rounded-md border px-2.5 py-1 text-[11px] font-medium uppercase tracking-[0.18em] ${
              open
                ? "border-primary/30 bg-primary/10 text-primary"
                : pnl != null && pnl >= 0
                  ? "border-[var(--gain)]/30 bg-[var(--gain)]/10 text-[var(--gain)]"
                  : "border-[var(--loss)]/30 bg-[var(--loss)]/10 text-[var(--loss)]"
            }`}
          >
            {open ? "Open" : "Closed"}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-7">
        <KpiBlock label="Current P&L" tone={pnl} value={fmtMoney(pnl)} />
        {isDebit ? (
          <KpiBlock label="Net debit" value={fmtMoney(netDebit)} sub="paid up-front (max risk)" />
        ) : (
          <KpiBlock label="%MP" value={fmtPct(pctOfMaxProfit)} sub={maxProfit != null ? fmtMoney(maxProfit) : "credit only"} />
        )}
        <KpiBlock label="Delta" tone={delta} value={fmtNum(delta)} />
        <KpiBlock label="DTE @ open" value={dteOpenLabel ?? "—"} sub={isDebit ? "front / back" : undefined} />
        <KpiBlock label="DTE remaining" value={fmtDays(dteRemaining)} />
        <KpiBlock label="DIT" value={fmtDays(dit)} />
        <KpiBlock label="Max DD seen" tone={maxDdSeen} value={fmtMoney(maxDdSeen)} />
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-12">
        <div className="xl:col-span-7">
          <ForwardPnlJourneyChart points={journey} maxProfit={maxProfit} milestones={milestones} />
        </div>
        <div className="xl:col-span-5">
          <ForwardDeltaChart points={journey} />
        </div>
      </div>

      <MilestonesStrip milestones={milestones} isDebit={isDebit} />

      <TradeSetupCard trade={trade} isDebit={isDebit} />

      {strikeRows.length > 0 && (
        <StrikeStructureCard
          rows={strikeRows}
          netCredit={isDebit ? null : numOr(trade.net_credit)}
          multiplier={100}
          rightLabel="Type"
        />
      )}
    </section>
  );
}

function ForwardPnlJourneyChart({
  points,
  maxProfit,
  milestones,
}: {
  points: ForwardJourneyPoint[];
  maxProfit: number | null;
  milestones: ForwardtestTrade["milestones"];
}) {
  const finalPnl = points.at(-1)?.pnl ?? null;
  const color = finalPnl == null ? "var(--primary)" : finalPnl < 0 ? "var(--loss)" : finalPnl > 0 ? "var(--gain)" : "var(--primary)";
  const maxDit = Math.max(1, ...points.map((point) => point.dit));
  const references = maxProfit != null && maxProfit > 0
    ? [
        { label: "10% MP", value: maxProfit * 0.1, dit: milestones?.dit_to_10mp ?? null },
        { label: "25% MP", value: maxProfit * 0.25, dit: milestones?.dit_to_25mp ?? null },
        { label: "50% MP", value: maxProfit * 0.5, dit: milestones?.dit_to_50mp ?? null },
        { label: "75% MP", value: maxProfit * 0.75, dit: milestones?.dit_to_75mp ?? null },
      ]
    : [];

  return (
    <ChartCard title="P&L journey" icon={<TrendingUp className="h-4 w-4" />} sub={finalPnl != null ? fmtMoney(finalPnl) : undefined}>
      {points.length === 0 ? (
        <EmptyChartState label="Daily marks unavailable" />
      ) : (
        <ResponsiveContainer width="100%" height={360}>
          <AreaChart data={points} margin={{ left: 6, right: 14, top: 12, bottom: 0 }}>
            <defs>
              <linearGradient id="ft-pnl-fill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={color} stopOpacity={0.28} />
                <stop offset="100%" stopColor={color} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" opacity={0.45} />
            <XAxis
              dataKey="dit"
              type="number"
              domain={[0, maxDit]}
              tickLine={false}
              axisLine={false}
              fontSize={11}
              allowDecimals={false}
              label={{ value: "DIT", position: "insideBottomRight", offset: -2, fill: "var(--muted-foreground)", fontSize: 10 }}
            />
            <YAxis tickFormatter={fmtAxisMoney} tickLine={false} axisLine={false} fontSize={11} width={58} />
            <Tooltip content={<ForwardPnlTooltip />} />
            <ReferenceLine y={0} stroke="var(--border)" strokeWidth={1.2} />
            {references.map((ref) => (
              <ReferenceLine
                key={ref.label}
                y={ref.value}
                stroke="var(--warning)"
                strokeDasharray="4 4"
                strokeOpacity={0.65}
              />
            ))}
            <Area
              type="monotone"
              dataKey="pnl"
              stroke={color}
              strokeWidth={2.5}
              fill="url(#ft-pnl-fill)"
              dot={{ r: 2.4, fill: color, stroke: "var(--background)", strokeWidth: 1 }}
              activeDot={{ r: 5 }}
              isAnimationActive={false}
            />
            {references.map((ref) => (
              ref.dit != null ? (
                <ReferenceDot
                  key={`${ref.label}-dot`}
                  x={ref.dit}
                  y={ref.value}
                  r={5}
                  fill="var(--warning)"
                  stroke="var(--background)"
                  strokeWidth={2}
                />
              ) : null
            ))}
          </AreaChart>
        </ResponsiveContainer>
      )}
    </ChartCard>
  );
}

function ForwardDeltaChart({ points }: { points: ForwardJourneyPoint[] }) {
  const deltaPoints = points.filter((point) => point.delta != null);
  const latest = deltaPoints.at(-1)?.delta ?? null;
  return (
    <ChartCard title="Delta evolution" icon={<TrendingDown className="h-4 w-4" />} sub={latest != null ? fmtNum(latest) : undefined}>
      {deltaPoints.length === 0 ? (
        <EmptyChartState label="Daily delta unavailable" />
      ) : (
        <ResponsiveContainer width="100%" height={360}>
          <LineChart data={deltaPoints} margin={{ left: 6, right: 14, top: 12, bottom: 0 }}>
            <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" opacity={0.45} />
            <XAxis
              dataKey="dit"
              type="number"
              domain={[0, Math.max(1, ...deltaPoints.map((point) => point.dit))]}
              tickLine={false}
              axisLine={false}
              fontSize={11}
              allowDecimals={false}
              label={{ value: "DIT", position: "insideBottomRight", offset: -2, fill: "var(--muted-foreground)", fontSize: 10 }}
            />
            <YAxis tickFormatter={(value) => fmtNum(Number(value))} tickLine={false} axisLine={false} fontSize={11} width={52} />
            <Tooltip content={<ForwardDeltaTooltip />} />
            <ReferenceLine y={0} stroke="var(--border)" strokeWidth={1.2} />
            <Line
              type="monotone"
              dataKey="delta"
              stroke="var(--primary)"
              strokeWidth={2.5}
              dot={{ r: 2.4, fill: "var(--primary)", stroke: "var(--background)", strokeWidth: 1 }}
              activeDot={{ r: 5 }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </ChartCard>
  );
}

function MilestonesStrip({ milestones, isDebit }: { milestones: ForwardtestTrade["milestones"]; isDebit: boolean }) {
  const items = [
    { label: "10% MP", value: milestones?.dit_to_10mp ?? null },
    { label: "25% MP", value: milestones?.dit_to_25mp ?? null },
    { label: "50% MP", value: milestones?.dit_to_50mp ?? null },
    { label: "75% MP", value: milestones?.dit_to_75mp ?? null },
  ];
  const subtitle = isDebit ? "% of debit recovered" : "% of max profit";
  return (
    <div className="space-y-1">
      <div className="text-[10px] font-medium uppercase tracking-[0.22em] text-muted-foreground">{subtitle}</div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {items.map((item) => (
          <div key={item.label} className="rounded-2xl border border-border/60 bg-card/40 p-4">
            <div className="text-[10px] font-medium uppercase tracking-[0.22em] text-muted-foreground">{item.label}</div>
            <div className="mt-2 text-lg font-semibold tabular">
              {item.value == null ? DASH : `@ DIT ${item.value}`}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function TradeSetupCard({ trade, isDebit }: { trade: ForwardtestTrade; isDebit: boolean }) {
  type SetupRow = { label: string; value: string; tone: number | null };
  const contracts = firstTextValue(trade, [
    "contracts",
    "contract",
    "contract_count",
    "contracts_count",
    "num_contracts",
    "qty",
    "quantity",
    "contratos",
  ]);
  const netCreditValue = numOr(trade.net_credit);
  const maxLossValue = numOr(trade.max_loss);
  const rawRows: Array<SetupRow | null> = [
    contracts ? { label: "Contracts", value: contracts, tone: null } : null,
    netCreditValue != null
      ? {
          label: isDebit ? "Net debit" : "Net credit",
          value: fmtMoney(netCreditValue),
          tone: null,
        }
      : null,
    maxLossValue != null ? { label: "Max loss", value: fmtMoney(maxLossValue), tone: null } : null,
    numOr(trade.lw_be) != null ? { label: "Lower BE", value: fmtNum(numOr(trade.lw_be)), tone: null } : null,
    numOr(trade.up_be) != null ? { label: "Upper BE", value: fmtNum(numOr(trade.up_be)), tone: null } : null,
    numOr(trade.pct_to_lw_be) != null ? { label: "% to LBE", value: fmtPctField(trade.pct_to_lw_be), tone: null } : null,
    numOr(trade.pct_to_up_be) != null ? { label: "% to UBE", value: fmtPctField(trade.pct_to_up_be), tone: null } : null,
  ];
  const rows = rawRows.filter((row): row is SetupRow => row != null);

  if (rows.length === 0) return null;

  return (
    <section className="rounded-2xl border border-border/60 bg-gradient-to-b from-card/70 to-card/35 p-5 shadow-2xl shadow-black/10">
      <h3 className="mb-4 text-sm font-semibold tracking-tight">Trade setup</h3>
      <dl className="space-y-2.5 text-sm">
        {rows.map((row) => (
          <Row key={row.label} label={row.label} value={row.value} tone={row.tone} />
        ))}
      </dl>
    </section>
  );
}

function ForwardPnlTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload as ForwardJourneyPoint | undefined;
  if (!point) return null;
  return (
    <div className="rounded-lg border border-border/70 bg-popover/95 px-3 py-2 text-xs shadow-xl">
      <div className="font-medium">Day {point.dit} {point.date ? `/ ${fmtDate(point.date)}` : ""}</div>
      <div className={`mt-1 tabular ${pnlClass(point.pnl)}`}>P&L {fmtMoney(point.pnl)}</div>
      {point.delta != null && <div className="tabular text-muted-foreground">delta {fmtNum(point.delta)}</div>}
    </div>
  );
}

function ForwardDeltaTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload as ForwardJourneyPoint | undefined;
  if (!point) return null;
  return (
    <div className="rounded-lg border border-border/70 bg-popover/95 px-3 py-2 text-xs shadow-xl">
      <div className="font-medium">Day {point.dit} {point.date ? `/ ${fmtDate(point.date)}` : ""}</div>
      <div className="mt-1 tabular text-primary">delta {fmtNum(point.delta)}</div>
    </div>
  );
}

function RulesCard({ meta }: { meta: ForwardtestDetailType["meta"] }) {
  if (!meta.entry_rule && !meta.exit_rule) return null;
  return (
    <section className="rounded-2xl border border-border/60 bg-gradient-to-b from-card/70 to-card/35 p-5 shadow-2xl shadow-black/10">
      <h3 className="mb-4 text-sm font-semibold tracking-tight">Trade plan</h3>
      <dl className="space-y-2.5 text-sm">
        {meta.entry_rule && <Row label="Entry rule" value={meta.entry_rule} />}
        {meta.exit_rule && <Row label="Exit rule" value={meta.exit_rule} />}
      </dl>
    </section>
  );
}

function buildTemplateLegRows(template: LegSpec[]): LegRow[] {
  return template.map((leg, idx) => {
    const sideLabel: "Buy" | "Sell" = leg.side === "buy" ? "Buy" : "Sell";
    const typeLabel = leg.type === "call" ? "Call" : "Put";
    const qtyLabel = leg.qty && leg.qty !== 1 ? `${leg.qty}× ` : "";
    const expLabel = leg.expiration_offset_days != null ? ` · ${leg.expiration_offset_days}D` : "";
    return {
      leg: `${qtyLabel}${typeLabel}${expLabel || ` #${idx + 1}`}`,
      side: sideLabel,
      strike: null,
      detail: leg.strike_offset ?? typeLabel,
      mid: null,
    };
  });
}

function buildForwardJourneySeries(trade: ForwardtestTrade): ForwardJourneyPoint[] {
  const openDate = asString(trade.open_date) ?? asString(trade.visual_open_date);
  return (trade.daily_history ?? [])
    .map((row, index) => {
      const pnl = numOr(row.pnl);
      if (pnl == null) return null;
      const date = asString(row.date);
      return {
        date,
        dit: daysBetween(openDate, date) ?? index,
        pnl,
        delta: numOr(row.delta),
      };
    })
    .filter((point): point is ForwardJourneyPoint => point != null)
    .sort((a, b) => a.dit - b.dit);
}

function buildTradeStrikeRows(trade: ForwardtestTrade): LegRow[] {
  const raw = asString(trade.strikes);
  if (!raw) return [];
  return raw
    .split(/[\/,\s|]+/)
    .map((part) => part.trim())
    .filter(Boolean)
    .map((part, index) => {
      const match = part.match(/^\$?(\d+(?:\.\d+)?)([CP])$/i);
      const strike = match ? Number(match[1]) : numOr(part);
      const type = match ? (match[2].toUpperCase() === "C" ? "Call" : "Put") : "Strike";
      return {
        leg: `${type} ${index + 1}`,
        side: null,
        strike,
        detail: type,
        mid: null,
      };
    });
}

function currentTradePnl(trade: ForwardtestTrade): number | null {
  return numOr(trade.pnl_current ?? trade.pnl ?? trade.open_pnl);
}

function calcTradeDit(trade: ForwardtestTrade, lastHistoryDate: string | null): number | null {
  const openDate = asString(trade.open_date) ?? asString(trade.visual_open_date);
  const closeDate = asString(trade.inferred_close_date) ?? lastHistoryDate ?? asString(trade.exp_date) ?? asString(trade.visual_exp_date);
  const endDate = trade.is_active ? todayIsoDate() : closeDate;
  return daysBetween(openDate, endDate);
}

function daysBetween(start: string | null | undefined, end: string | null | undefined): number | null {
  const a = parseDay(start);
  const b = parseDay(end);
  if (a == null || b == null) return null;
  return Math.max(0, Math.round((b - a) / 86_400_000));
}

function parseDay(value: string | null | undefined): number | null {
  const s = asString(value)?.slice(0, 10);
  if (!s || !/^\d{4}-\d{2}-\d{2}$/.test(s)) return null;
  const [year, month, day] = s.split("-").map(Number);
  if (!year || !month || !day) return null;
  return Date.UTC(year, month - 1, day);
}

function todayIsoDate(): string {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function fmtDays(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return DASH;
  return `${fmtNum(value)} days`;
}

function fmtPctField(value: unknown): string {
  const n = numOr(value);
  if (n == null) return DASH;
  return fmtPct(Math.abs(n) > 1 ? n / 100 : n);
}

function fmtAxisMoney(value: unknown): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return "";
  if (Math.abs(n) >= 1000) return `$${Math.round(n / 1000)}k`;
  return `$${Math.round(n)}`;
}

function firstTextValue(record: Record<string, unknown>, keys: string[]): string | null {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "number" && Number.isFinite(value)) return fmtNum(value);
    if (typeof value === "string" && value.trim() !== "") return value.trim();
  }
  return null;
}

function sumPnl(trades: ForwardtestTrade[]): number {
  let total = 0;
  for (const t of trades) {
    const v = numOr(t.pnl_current ?? (t.pnl as number | undefined));
    if (v != null) total += v;
  }
  return Math.round(total * 100) / 100;
}

function numOr(value: unknown): number | null {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value === "string" && value.trim() !== "") {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

function asString(value: unknown): string | null {
  if (typeof value === "string" && value.trim() !== "") return value;
  return null;
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
        <h2 className="text-lg font-semibold">Forward test &ldquo;{id}&rdquo; not found</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          Make sure a CZ_Forward trade exists after the tracking cutoff with a recognizable strategy name.
        </p>
        <Link href="/forwardtests" className="mt-4 inline-block rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground transition hover:opacity-90">
          Back to forward tests
        </Link>
      </div>
    </main>
  );
}
