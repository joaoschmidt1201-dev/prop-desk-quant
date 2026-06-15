"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type GexProfile, GEX_TIMEFRAMES, type GexTimeframe } from "@/lib/api";
import { LEVEL_COLORS, scaleStrike } from "./gex-format";

// Custom SVG candlestick + GEX level overlay. Recharts has no native candlestick,
// and we want precise control of wicks/bodies + labeled horizontal level lines that
// match Tanuki's GEX Live Chart — so we measure the wrapper and draw the SVG directly.
function useWidth() {
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

const GAIN = "var(--gain)";
const LOSS = "var(--loss)";
const CYAN = LEVEL_COLORS.hvl;

type Level = { value: number; label: string; color: string; strong: boolean; dashed: boolean };

function buildLevels(profile: GexProfile): Level[] {
  const scale = profile.index_scale;
  const s = (v: number | null | undefined) => scaleStrike(v ?? null, scale);
  const lv = profile.levels;
  const out: Level[] = [];
  lv.call_walls.forEach((v, i) =>
    out.push({ value: s(v)!, label: `C${i + 1}`, color: GAIN, strong: i === 0, dashed: i > 0 }));
  lv.put_walls.forEach((v, i) =>
    out.push({ value: s(v)!, label: `P${i + 1}`, color: LOSS, strong: i === 0, dashed: i > 0 }));
  if (lv.hvl != null) out.push({ value: s(lv.hvl)!, label: "HVL", color: CYAN, strong: true, dashed: false });
  if (lv.c_trans != null) out.push({ value: s(lv.c_trans)!, label: "cTrans", color: CYAN, strong: false, dashed: true });
  if (lv.p_trans != null) out.push({ value: s(lv.p_trans)!, label: "pTrans", color: CYAN, strong: false, dashed: true });
  return out.filter((l) => Number.isFinite(l.value));
}

export function GexLiveChart({ underlying, profile }: { underlying: string; profile?: GexProfile }) {
  const [tf, setTf] = useState<GexTimeframe>("5d");
  const candlesQ = useQuery({
    queryKey: ["gex-candles", underlying, tf],
    queryFn: () => api.gexCandles(underlying, tf),
    refetchInterval: 120_000,
  });
  const [wrapRef, width] = useWidth();
  const height = 480;
  const pad = { top: 14, right: 70, bottom: 22, left: 8 };

  const bars = candlesQ.data?.bars ?? [];
  const levels = useMemo(() => (profile ? buildLevels(profile) : []), [profile]);
  const spotScaled = profile ? scaleStrike(profile.spot, profile.index_scale) : null;

  const plotW = Math.max(0, width - pad.left - pad.right);
  const plotH = height - pad.top - pad.bottom;

  // Y-domain: candle range, expanded to include nearby levels (±4% of price), padded.
  const { lo, hi } = useMemo(() => {
    if (bars.length === 0) return { lo: 0, hi: 1 };
    let mn = Math.min(...bars.map((b) => b.l));
    let mx = Math.max(...bars.map((b) => b.h));
    const band = (mx - mn) || mx * 0.01;
    const near = levels.map((l) => l.value).filter((v) => v >= mn - band * 1.2 && v <= mx + band * 1.2);
    if (spotScaled != null) near.push(spotScaled);
    for (const v of near) { mn = Math.min(mn, v); mx = Math.max(mx, v); }
    const p = (mx - mn) * 0.06 || mx * 0.01;
    return { lo: mn - p, hi: mx + p };
  }, [bars, levels, spotScaled]);

  const yOf = (price: number) => pad.top + (1 - (price - lo) / (hi - lo)) * plotH;
  const n = bars.length;
  const step = n > 0 ? plotW / n : 0;
  const bodyW = Math.max(1, Math.min(10, step * 0.62));
  const xOf = (i: number) => pad.left + i * step + step / 2;

  // Y gridline ticks (5 evenly spaced, rounded).
  const ticks = useMemo(() => {
    if (hi <= lo) return [];
    const out: number[] = [];
    for (let i = 0; i <= 4; i++) out.push(lo + ((hi - lo) * i) / 4);
    return out;
  }, [lo, hi]);

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <div className="flex flex-wrap items-center gap-1">
          {GEX_TIMEFRAMES.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTf(t)}
              className={`rounded-md px-2 py-0.5 text-[11px] font-medium ring-1 transition ${
                t === tf ? "bg-primary/15 text-primary ring-primary/30"
                         : "bg-background/30 text-muted-foreground ring-border/40 hover:text-foreground"
              }`}
            >
              {t}
            </button>
          ))}
        </div>
        {candlesQ.data && (
          <span className="text-[10px] text-muted-foreground">
            {candlesQ.data.yahoo_symbol} · {candlesQ.data.interval} bars
          </span>
        )}
      </div>

      <div ref={wrapRef} className="w-full">
        {candlesQ.isError && (
          <div className="flex h-72 items-center justify-center text-xs text-amber-300">
            Candles unavailable — source throttled or market closed.
          </div>
        )}
        {!candlesQ.isError && n === 0 && (
          <div className="h-72 animate-pulse rounded-xl bg-foreground/5" />
        )}
        {width > 0 && n > 0 && (
          <svg width={width} height={height} className="overflow-visible">
            {/* y gridlines + labels */}
            {ticks.map((tk, i) => (
              <g key={i}>
                <line x1={pad.left} x2={pad.left + plotW} y1={yOf(tk)} y2={yOf(tk)}
                      stroke="var(--border)" strokeOpacity={0.25} strokeWidth={1} />
                <text x={pad.left + plotW + 4} y={yOf(tk) + 3} fontSize={9}
                      className="tabular" fill="var(--muted-foreground)">
                  {Math.round(tk).toLocaleString("en-US")}
                </text>
              </g>
            ))}

            {/* candles */}
            {bars.map((b, i) => {
              const up = b.c >= b.o;
              const color = up ? GAIN : LOSS;
              const x = xOf(i);
              const yO = yOf(b.o), yC = yOf(b.c);
              const top = Math.min(yO, yC);
              const h = Math.max(1, Math.abs(yC - yO));
              return (
                <g key={i}>
                  <line x1={x} x2={x} y1={yOf(b.h)} y2={yOf(b.l)} stroke={color} strokeWidth={1} strokeOpacity={0.85} />
                  <rect x={x - bodyW / 2} y={top} width={bodyW} height={h} fill={color} fillOpacity={up ? 0.55 : 0.8} />
                </g>
              );
            })}

            {/* spot line */}
            {spotScaled != null && spotScaled >= lo && spotScaled <= hi && (
              <g>
                <line x1={pad.left} x2={pad.left + plotW} y1={yOf(spotScaled)} y2={yOf(spotScaled)}
                      stroke="var(--foreground)" strokeWidth={1} strokeDasharray="1 3" strokeOpacity={0.7} />
                <rect x={pad.left + plotW + 1} y={yOf(spotScaled) - 7} width={pad.right - 2} height={14} fill="var(--foreground)" fillOpacity={0.14} />
                <text x={pad.left + plotW + 5} y={yOf(spotScaled) + 3} fontSize={9} fontWeight={700}
                      className="tabular" fill="var(--foreground)">
                  {Math.round(spotScaled).toLocaleString("en-US")}
                </text>
              </g>
            )}

            {/* level lines (clamped to edge if out of view, with ▲/▼ marker) */}
            {levels.map((l, i) => {
              const inView = l.value >= lo && l.value <= hi;
              const y = inView ? yOf(l.value) : (l.value > hi ? pad.top + 1 : pad.top + plotH - 1);
              const marker = inView ? "" : l.value > hi ? " ▲" : " ▼";
              return (
                <g key={i} opacity={inView ? 1 : 0.5}>
                  <line x1={pad.left} x2={pad.left + plotW} y1={y} y2={y}
                        stroke={l.color} strokeWidth={l.strong ? 1.4 : 1}
                        strokeDasharray={l.dashed ? "4 4" : undefined} strokeOpacity={l.strong ? 0.9 : 0.55} />
                  <text x={pad.left + plotW + 5} y={y - 2} fontSize={9} fontWeight={l.strong ? 700 : 500}
                        className="tabular" fill={l.color}>
                    {l.label}{marker}
                  </text>
                  <text x={pad.left + plotW + 5} y={y + 8} fontSize={8}
                        className="tabular" fill={l.color} fillOpacity={0.7}>
                    {Math.round(l.value).toLocaleString("en-US")}
                  </text>
                </g>
              );
            })}
          </svg>
        )}
      </div>
    </div>
  );
}
