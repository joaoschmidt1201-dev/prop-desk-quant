"use client";

import {
  Bar,
  BarChart,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { GexProfile, GexStrike } from "@/lib/api";

// Focus the chart on the strikes that carry the gamma: the top-N by |Net GEX|,
// drawn back in strike order. Showing every penny-wide strike would be noise.
const TOP_N = 40;

type Row = GexStrike & { netM: number };

function fmtM(v: number): string {
  const s = v > 0 ? "+" : v < 0 ? "−" : "";
  return `${s}$${Math.abs(v / 1e6).toFixed(1)}M`;
}

function nearest(values: number[], target: number | null): number | undefined {
  if (target == null || values.length === 0) return undefined;
  return values.reduce((a, b) => (Math.abs(b - target) < Math.abs(a - target) ? b : a));
}

export function GexProfileChart({ profile }: { profile: GexProfile }) {
  const rows: Row[] = [...profile.strikes]
    .sort((a, b) => Math.abs(b.net_gex) - Math.abs(a.net_gex))
    .slice(0, TOP_N)
    .sort((a, b) => a.strike - b.strike)
    .map((s) => ({ ...s, netM: s.net_gex / 1e6 }));

  if (rows.length === 0) {
    return (
      <div className="flex h-40 items-center justify-center text-xs text-muted-foreground">
        No strikes with open interest.
      </div>
    );
  }

  const strikeVals = rows.map((r) => r.strike);
  const spotStrike = nearest(strikeVals, profile.spot);
  const flipStrike = nearest(strikeVals, profile.gamma_flip);
  const height = Math.max(380, rows.length * 16);

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart layout="vertical" data={rows} margin={{ left: 4, right: 20, top: 8, bottom: 8 }}>
        <XAxis
          type="number"
          tickFormatter={(v) => `${Number(v) > 0 ? "+" : ""}${Math.round(Number(v))}M`}
          tickLine={false}
          axisLine={false}
          fontSize={10}
        />
        <YAxis
          type="category"
          dataKey="strike"
          reversed
          interval={0}
          tickLine={false}
          axisLine={false}
          fontSize={10}
          width={50}
        />
        <Tooltip cursor={{ fill: "var(--border)", opacity: 0.15 }} content={<ProfileTooltip />} />
        <ReferenceLine x={0} stroke="var(--border)" />
        {spotStrike !== undefined && (
          <ReferenceLine
            y={spotStrike}
            stroke="var(--primary)"
            strokeDasharray="5 3"
            label={{ value: `spot ${Math.round(profile.spot)}`, position: "right", fontSize: 10, fill: "var(--primary)" }}
          />
        )}
        {flipStrike !== undefined && profile.gamma_flip != null && (
          <ReferenceLine
            y={flipStrike}
            stroke="var(--accent)"
            strokeDasharray="2 2"
            label={{ value: `flip ${Math.round(profile.gamma_flip)}`, position: "right", fontSize: 10, fill: "var(--accent)" }}
          />
        )}
        <Bar dataKey="netM" radius={[0, 2, 2, 0]} isAnimationActive={false}>
          {rows.map((r, i) => (
            <Cell key={i} fill={r.net_gex >= 0 ? "var(--gain)" : "var(--loss)"} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

type TipProps = { active?: boolean; payload?: Array<{ payload: Row }> };

function ProfileTooltip({ active, payload }: TipProps) {
  if (!active || !payload || payload.length === 0) return null;
  const r = payload[0].payload;
  return (
    <div className="rounded-lg border border-border/60 bg-popover px-3 py-2 text-xs shadow-md">
      <div className="mb-1 font-semibold">Strike {r.strike}</div>
      <div className="text-[var(--gain)]">Call {fmtM(r.call_gex)}</div>
      <div className="text-[var(--loss)]">Put {fmtM(r.put_gex)}</div>
      <div className="mt-1 border-t border-border/40 pt-1">Net {fmtM(r.net_gex)}</div>
    </div>
  );
}
