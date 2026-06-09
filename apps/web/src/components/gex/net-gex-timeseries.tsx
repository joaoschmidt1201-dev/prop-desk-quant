"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { GexHistoryPoint } from "@/lib/api";

type Row = { t: string; total: number; zero: number };

function fmtBn(v: number): string {
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}Bn`;
}

export function NetGexTimeseries({ points }: { points: GexHistoryPoint[] }) {
  if (!points || points.length === 0) {
    return (
      <div className="flex h-40 items-center justify-center rounded-xl border border-dashed border-border/50 px-4 text-center text-xs text-muted-foreground">
        No history yet — this series builds forward as snapshots accumulate.
      </div>
    );
  }

  const rows: Row[] = points.map((p) => ({
    t: new Date(p.ts).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit" }),
    total: p.net_gex_total / 1e9,
    zero: p.net_gex_0dte / 1e9,
  }));

  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={rows} margin={{ left: 6, right: 12, top: 8, bottom: 0 }}>
        <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" opacity={0.5} />
        <XAxis dataKey="t" tickLine={false} axisLine={false} fontSize={10} minTickGap={28} />
        <YAxis tickFormatter={(v) => `${Number(v).toFixed(1)}B`} tickLine={false} axisLine={false} fontSize={10} width={44} />
        <Tooltip
          contentStyle={{ background: "var(--popover)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }}
          formatter={(value) => fmtBn(Number(value))}
        />
        <ReferenceLine y={0} stroke="var(--border)" />
        <Line type="monotone" dataKey="total" name="All exp" stroke="var(--primary)" strokeWidth={2} dot={false} />
        <Line type="monotone" dataKey="zero" name="0DTE" stroke="var(--accent)" strokeWidth={1.5} strokeDasharray="4 3" dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}
