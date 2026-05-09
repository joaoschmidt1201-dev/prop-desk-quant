"use client";

import { Layers3 } from "lucide-react";
import { fmtMoney, fmtNum } from "@/lib/format";

const DASH = "—";

export type LegRow = {
  leg: string;
  side: "Buy" | "Sell" | null;
  strike: number | null;
  detail: string;
  mid: number | null;
};

function fmtPoints(value: number | null): string {
  if (value == null || Number.isNaN(value)) return DASH;
  return `${fmtNum(value)} pts`;
}

export function StrikeStructureCard({
  rows,
  netCredit,
  multiplier,
  rightLabel,
}: {
  rows: LegRow[];
  netCredit: number | null;
  multiplier: number;
  rightLabel: string;
}) {
  return (
    <section className="rounded-2xl border border-border/60 bg-gradient-to-b from-card/70 to-card/35 p-5 shadow-2xl shadow-black/10">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="text-primary"><Layers3 className="h-4 w-4" /></span>
          <h3 className="text-sm font-semibold tracking-tight">Strike structure</h3>
        </div>
        <span className="text-[11px] text-muted-foreground">
          {netCredit != null
            ? `net credit ${fmtNum(netCredit)} pts / ${fmtMoney(netCredit * multiplier)}`
            : `net credit ${DASH}`}
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border/40 text-[11px] uppercase tracking-wider text-muted-foreground">
              <th className="px-3 py-2 text-left font-medium">Leg</th>
              <th className="px-3 py-2 text-left font-medium">Side</th>
              <th className="px-3 py-2 text-right font-medium">Strike</th>
              <th className="px-3 py-2 text-right font-medium">{rightLabel}</th>
              <th className="px-3 py-2 text-right font-medium">Entry mid</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, idx) => (
              <tr key={`${row.leg}-${idx}`} className="border-b border-border/30 last:border-0">
                <td className="px-3 py-2.5 font-medium">{row.leg}</td>
                <td className={`px-3 py-2.5 text-xs font-semibold uppercase tracking-wider ${
                  row.side === "Sell"
                    ? "text-[var(--warning)]"
                    : row.side === "Buy"
                      ? "text-primary"
                      : "text-muted-foreground"
                }`}>
                  {row.side ?? DASH}
                </td>
                <td className="px-3 py-2.5 text-right tabular">{fmtNum(row.strike)}</td>
                <td className="px-3 py-2.5 text-right tabular text-muted-foreground">{row.detail || DASH}</td>
                <td className="px-3 py-2.5 text-right tabular text-muted-foreground">{fmtPoints(row.mid)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
