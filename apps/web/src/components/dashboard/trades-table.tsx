"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type Filter, type Trade } from "@/lib/api";
import { fmtDate, fmtMoney, pnlClass } from "@/lib/format";
import { DASHBOARD_REFETCH_INTERVAL_MS } from "@/lib/refresh";

type Props = { filter: Filter };

const SORT_OPTIONS = [
  { value: "status_dte", label: "Status + DTE" },
  { value: "name_az", label: "Alphabetical A-Z" },
  { value: "open_newest", label: "Opening date newest" },
  { value: "open_oldest", label: "Opening date oldest" },
  { value: "ticker_az", label: "Ticker A-Z" },
  { value: "pnl_best", label: "P&L best first" },
  { value: "pnl_worst", label: "P&L worst first" },
  { value: "expiration", label: "Expiration soonest" },
] as const;

type SortMode = (typeof SORT_OPTIONS)[number]["value"];

function textValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function numericValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function dateValue(value: unknown): number | null {
  if (!value) return null;
  const parsed = Date.parse(String(value));
  return Number.isFinite(parsed) ? parsed : null;
}

function compareText(a: unknown, b: unknown): number {
  return textValue(a).localeCompare(textValue(b), undefined, { numeric: true, sensitivity: "base" });
}

function compareNullableNumber(a: number | null, b: number | null, direction: "asc" | "desc" = "asc"): number {
  if (a == null && b == null) return 0;
  if (a == null) return 1;
  if (b == null) return -1;
  return direction === "asc" ? a - b : b - a;
}

function tradePnl(t: Trade): number | null {
  return numericValue(t.pnl ?? t.open_pnl);
}

function compareTrades(sortMode: SortMode, a: Trade, b: Trade): number {
  switch (sortMode) {
    case "name_az":
      return compareText(a.name, b.name);
    case "open_newest":
      return compareNullableNumber(dateValue(a.open_date), dateValue(b.open_date), "desc") || compareText(a.name, b.name);
    case "open_oldest":
      return compareNullableNumber(dateValue(a.open_date), dateValue(b.open_date), "asc") || compareText(a.name, b.name);
    case "ticker_az":
      return compareText(a.underlying, b.underlying) || compareText(a.name, b.name);
    case "pnl_best":
      return compareNullableNumber(tradePnl(a), tradePnl(b), "desc") || compareText(a.name, b.name);
    case "pnl_worst":
      return compareNullableNumber(tradePnl(a), tradePnl(b), "asc") || compareText(a.name, b.name);
    case "expiration":
      return compareNullableNumber(dateValue(a.exp_date), dateValue(b.exp_date), "asc") || compareText(a.name, b.name);
    case "status_dte":
    default:
      return (
        Number(b.is_active) - Number(a.is_active) ||
        compareNullableNumber(numericValue(a.dte_remaining), numericValue(b.dte_remaining), "asc")
      );
  }
}

export function TradesTable({ filter }: Props) {
  const [sortMode, setSortMode] = useState<SortMode>("status_dte");
  const { data, isLoading } = useQuery({
    queryKey: ["trades", filter.months, filter.env],
    queryFn: () => api.trades(filter),
    placeholderData: (previousData) => previousData,
    refetchInterval: DASHBOARD_REFETCH_INTERVAL_MS,
    refetchIntervalInBackground: true,
  });

  const sortLabel = SORT_OPTIONS.find((option) => option.value === sortMode)?.label ?? "Status + DTE";
  const trades = useMemo(() => {
    if (!data?.trades) return [];
    return [...data.trades].sort(
      (a, b) => compareTrades(sortMode, a, b) || compareText(a.name, b.name),
    );
  }, [data?.trades, sortMode]);

  if (isLoading || !data) {
    return <div className="h-72 animate-pulse rounded-2xl bg-card/20" />;
  }

  const active = trades.filter((t) => t.is_active);
  const closed = trades.filter((t) => !t.is_active);

  return (
    <section className="rounded-2xl border border-border/40 bg-card/30">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/30 px-6 py-4">
        <div>
          <h3 className="text-sm font-semibold tracking-tight">Positions</h3>
          <p className="mt-0.5 text-[11px] text-muted-foreground">
            {active.length} active / {closed.length} closed / sorted: {sortLabel}
          </p>
        </div>
        <label className="flex items-center gap-2">
          <span className="text-[10px] uppercase tracking-[0.22em] text-muted-foreground/70">Sort</span>
          <select
            value={sortMode}
            onChange={(event) => setSortMode(event.target.value as SortMode)}
            className="h-8 rounded-md border border-border/50 bg-background/80 px-3 text-[11px] font-medium text-foreground outline-none transition hover:bg-card/60 focus:ring-1 focus:ring-primary/50"
          >
            {SORT_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[10px] uppercase tracking-[0.16em] text-muted-foreground/70">
              <th className="px-6 py-3 text-left font-medium">Trade</th>
              <th className="px-3 py-3 text-left font-medium">Sym</th>
              <th className="px-3 py-3 text-left font-medium">Status</th>
              <th className="px-3 py-3 text-right font-medium">DTE</th>
              <th className="px-3 py-3 text-right font-medium">NC</th>
              <th className="px-3 py-3 text-right font-medium">Max Loss</th>
              <th className="px-3 py-3 text-right font-medium">Delta</th>
              <th className="px-3 py-3 text-right font-medium">P&L</th>
              <th className="px-6 py-3 text-right font-medium">Exp</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((t: Trade) => {
              const pnl = tradePnl(t);
              return (
                <tr key={t.name} className="border-t border-border/20 transition hover:bg-card/40">
                  <td className="px-6 py-3 font-medium tracking-tight">{t.name}</td>
                  <td className="px-3 py-3 text-muted-foreground tabular">{t.underlying}</td>
                  <td className="px-3 py-3">
                    <span
                      className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[10px] font-medium ${
                        t.is_active ? "bg-[var(--gain)]/10 text-[var(--gain)]" : "bg-muted/30 text-muted-foreground"
                      }`}
                    >
                      <span className={`h-1 w-1 rounded-full ${t.is_active ? "bg-[var(--gain)]" : "bg-muted-foreground/60"}`} />
                      {t.is_active ? "Active" : "Closed"}
                    </span>
                  </td>
                  <td className="px-3 py-3 text-right tabular text-muted-foreground">{t.dte_remaining ?? "--"}</td>
                  <td className="px-3 py-3 text-right tabular text-muted-foreground">{fmtMoney(t.net_credit)}</td>
                  <td className="px-3 py-3 text-right tabular text-muted-foreground">{fmtMoney(t.max_loss)}</td>
                  <td className="px-3 py-3 text-right tabular text-muted-foreground">
                    {t.delta != null ? Number(t.delta).toFixed(1) : "--"}
                  </td>
                  <td className={`px-3 py-3 text-right tabular font-semibold ${pnlClass(pnl)}`}>{fmtMoney(pnl)}</td>
                  <td className="px-6 py-3 text-right tabular text-[11px] text-muted-foreground">{fmtDate(t.exp_date)}</td>
                </tr>
              );
            })}
            {trades.length === 0 && (
              <tr>
                <td colSpan={9} className="px-6 py-12 text-center text-sm text-muted-foreground">
                  No trades match the current filter.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
