"use client";

import { useQuery } from "@tanstack/react-query";
import { api, type Filter, type Trade } from "@/lib/api";
import { fmtDate, fmtMoney, pnlClass } from "@/lib/format";

type Props = { filter: Filter };

export function TradesTable({ filter }: Props) {
  const { data, isLoading } = useQuery({
    queryKey: ["trades", filter.months, filter.env],
    queryFn: () => api.trades(filter),
  });

  if (isLoading || !data) {
    return <div className="h-64 animate-pulse rounded-xl border border-border/60 bg-card/30" />;
  }

  const trades = [...data.trades].sort((a, b) => Number(b.is_active) - Number(a.is_active) || (a.dte_remaining ?? 0) - (b.dte_remaining ?? 0));

  return (
    <div className="rounded-xl border border-border/60 bg-card/50 overflow-hidden">
      <div className="flex items-center justify-between border-b border-border/60 px-5 py-3">
        <h3 className="text-sm font-semibold tracking-tight">Trades</h3>
        <span className="text-xs text-muted-foreground tabular">{trades.length} positions</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border/40 text-[11px] uppercase tracking-wider text-muted-foreground">
              <th className="px-5 py-2 text-left font-medium">Trade</th>
              <th className="px-3 py-2 text-left font-medium">Sym</th>
              <th className="px-3 py-2 text-left font-medium">Status</th>
              <th className="px-3 py-2 text-right font-medium">DTE</th>
              <th className="px-3 py-2 text-right font-medium">NC</th>
              <th className="px-3 py-2 text-right font-medium">Max Loss</th>
              <th className="px-3 py-2 text-right font-medium">Δ</th>
              <th className="px-5 py-2 text-right font-medium">P&L</th>
              <th className="px-5 py-2 text-right font-medium">Exp</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((t: Trade) => {
              const pnl = (t.pnl ?? t.open_pnl ?? null) as number | null;
              return (
                <tr key={t.name} className="border-b border-border/30 transition last:border-0 hover:bg-card/40">
                  <td className="px-5 py-3 font-medium">{t.name}</td>
                  <td className="px-3 py-3 text-muted-foreground">{t.underlying}</td>
                  <td className="px-3 py-3">
                    <span className={`inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-[11px] font-medium ${
                      t.is_active ? "bg-[var(--gain)]/15 text-[var(--gain)]" : "bg-muted text-muted-foreground"
                    }`}>
                      <span className={`h-1.5 w-1.5 rounded-full ${t.is_active ? "bg-[var(--gain)]" : "bg-muted-foreground"}`} />
                      {t.is_active ? "Active" : "Closed"}
                    </span>
                  </td>
                  <td className="px-3 py-3 text-right tabular">{t.dte_remaining ?? "—"}</td>
                  <td className="px-3 py-3 text-right tabular text-muted-foreground">{fmtMoney(t.net_credit)}</td>
                  <td className="px-3 py-3 text-right tabular text-muted-foreground">{fmtMoney(t.max_loss)}</td>
                  <td className="px-3 py-3 text-right tabular text-muted-foreground">{t.delta != null ? Number(t.delta).toFixed(1) : "—"}</td>
                  <td className={`px-5 py-3 text-right tabular font-semibold ${pnlClass(pnl)}`}>{fmtMoney(pnl)}</td>
                  <td className="px-5 py-3 text-right tabular text-muted-foreground">{fmtDate(t.exp_date)}</td>
                </tr>
              );
            })}
            {trades.length === 0 && (
              <tr>
                <td colSpan={9} className="px-5 py-12 text-center text-sm text-muted-foreground">
                  No trades match the current filter.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
