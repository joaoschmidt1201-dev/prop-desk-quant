"use client";

import { useQuery } from "@tanstack/react-query";
import { api, type Filter, type Trade } from "@/lib/api";
import { fmtDate, fmtMoney, pnlClass } from "@/lib/format";
import { DASHBOARD_REFETCH_INTERVAL_MS } from "@/lib/refresh";

type Props = { filter: Filter };

export function TradesTable({ filter }: Props) {
  const { data, isLoading } = useQuery({
    queryKey: ["trades", filter.months, filter.env],
    queryFn: () => api.trades(filter),
    refetchInterval: DASHBOARD_REFETCH_INTERVAL_MS,
    refetchIntervalInBackground: true,
  });

  if (isLoading || !data) {
    return <div className="h-72 animate-pulse rounded-2xl bg-card/20" />;
  }

  const trades = [...data.trades].sort(
    (a, b) => Number(b.is_active) - Number(a.is_active) || (a.dte_remaining ?? 0) - (b.dte_remaining ?? 0),
  );
  const active = trades.filter((t) => t.is_active);
  const closed = trades.filter((t) => !t.is_active);

  return (
    <section className="rounded-2xl border border-border/40 bg-card/30">
      <div className="flex items-center justify-between border-b border-border/30 px-6 py-4">
        <div>
          <h3 className="text-sm font-semibold tracking-tight">Positions</h3>
          <p className="mt-0.5 text-[11px] text-muted-foreground">
            {active.length} active · {closed.length} closed · sorted by status, then DTE
          </p>
        </div>
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
              <th className="px-3 py-3 text-right font-medium">Δ</th>
              <th className="px-3 py-3 text-right font-medium">P&L</th>
              <th className="px-6 py-3 text-right font-medium">Exp</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((t: Trade) => {
              const pnl = (t.pnl ?? t.open_pnl ?? null) as number | null;
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
                  <td className="px-3 py-3 text-right tabular text-muted-foreground">{t.dte_remaining ?? "—"}</td>
                  <td className="px-3 py-3 text-right tabular text-muted-foreground">{fmtMoney(t.net_credit)}</td>
                  <td className="px-3 py-3 text-right tabular text-muted-foreground">{fmtMoney(t.max_loss)}</td>
                  <td className="px-3 py-3 text-right tabular text-muted-foreground">{t.delta != null ? Number(t.delta).toFixed(1) : "—"}</td>
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
