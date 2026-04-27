"use client";

import { ArrowDown, ArrowUp } from "lucide-react";
import { fmtMoney, fmtNum, fmtPct, pnlClass } from "@/lib/format";

type Format = "money" | "pct" | "num" | "delta";

type Props = {
  label: string;
  value: number | null | undefined;
  format?: Format;
  hint?: string;
  size?: "sm" | "md" | "lg";
};

export function KpiCard({ label, value, format = "num", hint, size = "md" }: Props) {
  const formatted =
    value === null || value === undefined
      ? "—"
      : format === "money"
      ? fmtMoney(value)
      : format === "pct"
      ? fmtPct(value)
      : fmtNum(value);

  const colorClass =
    format === "money" || format === "delta" ? pnlClass(value) : "text-foreground";

  const valueSize = size === "lg" ? "text-3xl md:text-4xl" : size === "sm" ? "text-xl" : "text-2xl md:text-3xl";

  const showArrow = (format === "money" || format === "delta") && value !== null && value !== undefined && value !== 0;

  return (
    <div className="group relative overflow-hidden rounded-xl border border-border/60 bg-card/50 p-5 transition hover:border-border hover:bg-card/70">
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-primary/30 to-transparent opacity-0 transition group-hover:opacity-100" />
      <div className="flex items-start justify-between gap-2">
        <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">{label}</span>
        {showArrow && (
          <span className={`flex h-5 w-5 items-center justify-center rounded-full ${value! > 0 ? "bg-[var(--gain)]/15" : "bg-[var(--loss)]/15"}`}>
            {value! > 0 ? <ArrowUp className="h-3 w-3 text-[var(--gain)]" /> : <ArrowDown className="h-3 w-3 text-[var(--loss)]" />}
          </span>
        )}
      </div>
      <div className={`mt-2 font-semibold tabular tracking-tight ${valueSize} ${colorClass}`}>{formatted}</div>
      {hint && <div className="mt-1 text-xs text-muted-foreground">{hint}</div>}
    </div>
  );
}
