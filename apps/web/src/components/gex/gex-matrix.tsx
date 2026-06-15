"use client";

import { useQuery } from "@tanstack/react-query";
import { api, type GexMatrixCell } from "@/lib/api";
import { fmtUsd, fmtLevel, LEVEL_COLORS } from "./gex-format";

const sgn = (v: number | null | undefined) =>
  v == null ? "var(--muted-foreground)" : v > 0 ? "var(--gain)" : v < 0 ? "var(--loss)" : "var(--muted-foreground)";

function Num({ v }: { v: number | null | undefined }) {
  return <span className="tabular" style={{ color: sgn(v) }}>{fmtUsd(v ?? null)}</span>;
}

function Cells({ cell, scale, oi }: { cell: GexMatrixCell; scale: number | null; oi: boolean }) {
  return (
    <>
      <td className="border-l border-border/40 px-2 py-1 text-right"><Num v={cell.net_gex} /></td>
      <td className="px-2 py-1 text-right"><Num v={cell.net_dex} /></td>
      {oi && <td className="px-2 py-1 text-right tabular text-muted-foreground">{cell.oi_pct != null ? `${cell.oi_pct.toFixed(0)}%` : "—"}</td>}
      <td className="px-2 py-1 text-right tabular" style={{ color: LEVEL_COLORS.call }}>{fmtLevel(cell.c1, scale)}</td>
      <td className="px-2 py-1 text-right tabular" style={{ color: LEVEL_COLORS.hvl }}>{fmtLevel(cell.hvl, scale)}</td>
      <td className="px-2 py-1 text-right tabular" style={{ color: LEVEL_COLORS.put }}>{fmtLevel(cell.p1, scale)}</td>
    </>
  );
}

export function GexMatrix({ underlying }: { underlying: string }) {
  const q = useQuery({
    queryKey: ["gex-matrix", underlying],
    queryFn: () => api.gexMatrix(underlying),
    refetchInterval: 5 * 60 * 1000,
  });
  const data = q.data;
  const scale = data?.index_scale ?? null;

  return (
    <section className="glass min-w-0 rounded-2xl p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold tracking-tight">GEX Matrix — per expiration</h2>
        <span className="text-[11px] text-muted-foreground">Standalone (⊙) vs Cumulative (⅀)</span>
      </div>

      {q.isError && (
        <div className="rounded-xl border border-amber-400/30 bg-amber-400/5 p-4 text-xs text-amber-300">
          Chain unavailable — market closed or source throttled. Retrying…
        </div>
      )}
      {!data && !q.isError && <div className="h-64 animate-pulse rounded-xl bg-foreground/5" />}

      {data && (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-[11px]">
            <thead>
              <tr className="text-[9px] uppercase tracking-wider text-muted-foreground/70">
                <th className="px-2 py-1 text-left" colSpan={2}>Expiry</th>
                <th className="border-l border-border/40 px-2 py-1 text-center" colSpan={6}>⊙ Standalone</th>
                <th className="border-l border-border/40 px-2 py-1 text-center" colSpan={5}>⅀ Cumulative</th>
              </tr>
              <tr className="border-b border-border/40 text-[9px] uppercase tracking-wider text-muted-foreground">
                <th className="px-2 py-1 text-left">Date</th>
                <th className="px-2 py-1 text-right">DTE</th>
                <th className="border-l border-border/40 px-2 py-1 text-right">NetGEX</th>
                <th className="px-2 py-1 text-right">DEX</th>
                <th className="px-2 py-1 text-right">OI%</th>
                <th className="px-2 py-1 text-right">C1</th>
                <th className="px-2 py-1 text-right">HVL</th>
                <th className="px-2 py-1 text-right">P1</th>
                <th className="border-l border-border/40 px-2 py-1 text-right">NetGEX</th>
                <th className="px-2 py-1 text-right">DEX</th>
                <th className="px-2 py-1 text-right">C1</th>
                <th className="px-2 py-1 text-right">HVL</th>
                <th className="px-2 py-1 text-right">P1</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((r) => (
                <tr key={r.date} className="border-b border-border/20 hover:bg-card/40">
                  <td className="px-2 py-1 text-left font-medium tabular">{r.date.slice(5)}</td>
                  <td className="px-2 py-1 text-right tabular text-muted-foreground">{r.dte}d</td>
                  <Cells cell={r.standalone} scale={scale} oi />
                  <Cells cell={r.cumulative} scale={scale} oi={false} />
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-3 text-[10px] text-muted-foreground">
            NetGEX/DEX in index-$ space. Levels (C1/HVL/P1) are robust (relative OI); HVL & magnitudes
            are approximate on free (retail) OI — see data-feed note.
          </p>
        </div>
      )}
    </section>
  );
}
