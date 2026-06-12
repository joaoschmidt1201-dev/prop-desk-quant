"use client";

import { useEffect, useRef, useState } from "react";
import {
  Bar,
  BarChart,
  ReferenceLine,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { GexMetric, GexProfile, GexStrike } from "@/lib/api";
import { fmtLevel, scaleStrike } from "./gex-format";

// Size the chart from a measured wrapper width (ResizeObserver) instead of Recharts'
// ResponsiveContainer — predictable for this fixed-height vertical histogram and immune
// to any first-paint zero-width race.
function useChartWidth() {
  const ref = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const update = () => setW(el.clientWidth);
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w] as const;
}

// Focus on the strikes that carry the metric: top-N by |value|, drawn in strike order.
const TOP_N = 45;
const CYAN = "#22d3ee";

const SIDE: Record<GexMetric, [keyof GexStrike, keyof GexStrike]> = {
  net_gex: ["call_gex", "put_gex"],
  abs_gex: ["call_gex", "put_gex"],
  net_dex: ["call_dex", "put_dex"],
  net_oi: ["call_oi", "put_oi"],
  net_vol: ["call_vol", "put_vol"],
};

const METRIC_KEY: Record<GexMetric, keyof GexStrike> = {
  net_gex: "net_gex", abs_gex: "abs_gex", net_dex: "net_dex", net_oi: "net_oi", net_vol: "net_vol",
};

function unitOf(metric: GexMetric): { div: number; suf: string; dollar: boolean } {
  if (metric === "net_oi" || metric === "net_vol") return { div: 1, suf: "", dollar: false };
  return { div: 1e6, suf: "M", dollar: true };
}

function fmtVal(v: number, metric: GexMetric): string {
  const { dollar } = unitOf(metric);
  const sign = v > 0 ? "+" : v < 0 ? "−" : "";
  const a = Math.abs(v);
  const pre = dollar ? "$" : "";
  if (a >= 1e9) return `${sign}${pre}${(a / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `${sign}${pre}${(a / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `${sign}${pre}${(a / 1e3).toFixed(0)}K`;
  return `${sign}${pre}${a.toFixed(0)}`;
}

function nearest(values: number[], target: number | null | undefined): number | undefined {
  if (target == null || values.length === 0) return undefined;
  return values.reduce((a, b) => (Math.abs(b - target) < Math.abs(a - target) ? b : a));
}

type Row = { strike: number; callV: number; putV: number; raw: GexStrike };

export function GexProfileChart({ profile, metric }: { profile: GexProfile; metric: GexMetric }) {
  const [wrapRef, width] = useChartWidth();
  const key = METRIC_KEY[metric];
  const { div } = unitOf(metric);
  const [ck, pk] = SIDE[metric];
  const isAbs = metric === "abs_gex";

  // Select the most impactful strikes by |net|, then split into call (green, right)
  // and put (red, left) bars diverging from zero — the iconic GEX-profile look.
  const rows: Row[] = [...profile.strikes]
    .filter((s) => Number(s[key]) !== 0)
    .sort((a, b) => Math.abs(Number(b[key])) - Math.abs(Number(a[key])))
    .slice(0, TOP_N)
    .sort((a, b) => a.strike - b.strike)
    .map((s) => {
      const callV = (isAbs ? Number(s.abs_gex) : Number(s[ck])) / div;
      let putRaw = isAbs ? 0 : Number(s[pk]);
      if (metric === "net_oi" || metric === "net_vol") putRaw = -Math.abs(putRaw); // force left
      return { strike: s.strike, callV, putV: putRaw / div, raw: s };
    });

  if (rows.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center text-xs text-muted-foreground">
        No strikes with open interest for this metric.
      </div>
    );
  }

  const strikeVals = rows.map((r) => r.strike);
  const scale = profile.index_scale;
  const lv = profile.levels;

  // Level lines snapped to the nearest displayed strike (the flip is interpolated).
  type Line = { y: number; color: string; label?: string; dash: string };
  const lines: Line[] = [];
  const push = (val: number | null | undefined, color: string, label?: string, dash = "3 3") => {
    const y = nearest(strikeVals, val);
    if (y !== undefined) lines.push({ y, color, label, dash });
  };
  lv.call_walls.slice(0, 3).forEach((s, i) => push(s, "var(--gain)", i === 0 ? `C1 ${fmtLevel(s, scale)}` : undefined, i === 0 ? "4 2" : "1 4"));
  lv.put_walls.slice(0, 3).forEach((s, i) => push(s, "var(--loss)", i === 0 ? `P1 ${fmtLevel(s, scale)}` : undefined, i === 0 ? "4 2" : "1 4"));
  push(lv.c_trans, CYAN, undefined, "1 4");
  push(lv.p_trans, CYAN, undefined, "1 4");
  push(lv.hvl, CYAN, `HVL ${fmtLevel(lv.hvl, scale)}`, "5 3");

  const spotStrike = nearest(strikeVals, profile.spot);
  const height = Math.max(440, rows.length * 15);

  return (
    <div ref={wrapRef} className="w-full">
      {width > 0 && (
      <BarChart width={width} height={height} layout="vertical" data={rows} margin={{ left: 8, right: 64, top: 8, bottom: 8 }}>
        <XAxis
          type="number"
          tickFormatter={(v) => fmtVal(Number(v) * div, metric)}
          tickLine={false}
          axisLine={false}
          fontSize={10}
          stroke="var(--muted-foreground)"
        />
        <YAxis
          type="category"
          dataKey="strike"
          reversed
          interval={0}
          tickFormatter={(v) => String(Math.round(scaleStrike(Number(v), scale) ?? Number(v)))}
          tickLine={false}
          axisLine={false}
          fontSize={9}
          width={52}
          stroke="var(--muted-foreground)"
        />
        <Tooltip cursor={{ fill: "var(--foreground)", opacity: 0.06 }} content={<ProfileTooltip metric={metric} scale={scale} />} />
        <ReferenceLine x={0} stroke="var(--border)" />
        {lines.map((l, i) => (
          <ReferenceLine
            key={i}
            y={l.y}
            stroke={l.color}
            strokeDasharray={l.dash}
            strokeOpacity={l.label ? 0.9 : 0.4}
            label={l.label ? { value: l.label, position: "right", fontSize: 9, fill: l.color } : undefined}
          />
        ))}
        {spotStrike !== undefined && (
          <ReferenceLine
            y={spotStrike}
            stroke="var(--foreground)"
            strokeDasharray="2 2"
            label={{ value: `● ${Math.round(scaleStrike(profile.spot, scale) ?? profile.spot)}`, position: "right", fontSize: 9, fill: "var(--foreground)" }}
          />
        )}
        <Bar dataKey="callV" stackId="g" radius={[0, 2, 2, 0]} isAnimationActive={false} barSize={9}
          fill={isAbs ? "var(--warning)" : "var(--gain)"} />
        {!isAbs && (
          <Bar dataKey="putV" stackId="g" radius={[2, 0, 0, 2]} isAnimationActive={false} barSize={9} fill="var(--loss)" />
        )}
      </BarChart>
      )}
    </div>
  );
}

type TipProps = {
  active?: boolean;
  payload?: Array<{ payload: Row }>;
  metric: GexMetric;
  scale: number | null;
};

function ProfileTooltip({ active, payload, metric, scale }: TipProps) {
  if (!active || !payload || payload.length === 0) return null;
  const r = payload[0].payload;
  const [ck, pk] = SIDE[metric];
  return (
    <div className="rounded-lg border border-border/60 bg-popover px-3 py-2 text-xs shadow-md">
      <div className="mb-1 font-semibold tabular">Strike {Math.round(scaleStrike(r.strike, scale) ?? r.strike).toLocaleString("en-US")}</div>
      <div className="text-[var(--gain)]">Call {fmtVal(Number(r.raw[ck]), metric)}</div>
      <div className="text-[var(--loss)]">Put {fmtVal(Number(r.raw[pk]), metric)}</div>
      <div className="mt-1 border-t border-border/40 pt-1">Net {fmtVal(Number(r.raw[METRIC_KEY[metric]]), metric)}</div>
    </div>
  );
}
