import type { ReactNode } from "react";
import { Activity, BarChart3, Gauge, TrendingUp } from "lucide-react";
import type { GexHorizons, GexProfile, GexRange } from "@/lib/api";
import { clamp01, distPct, fmtLevel, fmtUsd } from "./gex-format";

const CYAN = "#22d3ee";

// ─── Card shell ───────────────────────────────────────────────────────────────

function Card({
  title, icon, note, children,
}: { title: string; icon?: ReactNode; note?: string; children: ReactNode }) {
  return (
    <section className="glass rounded-2xl p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          {icon}
          {title}
        </h3>
        {note && (
          <span className="rounded-full bg-background/40 px-2 py-0.5 text-[9px] uppercase tracking-wider text-muted-foreground ring-1 ring-border/40">
            {note}
          </span>
        )}
      </div>
      {children}
    </section>
  );
}

function Skeleton({ h }: { h: number }) {
  return <div className="animate-pulse rounded-xl bg-foreground/5" style={{ height: h }} />;
}

const tone = (v: number | null | undefined) =>
  v == null ? "text-foreground" : v > 0 ? "text-[var(--gain)]" : v < 0 ? "text-[var(--loss)]" : "text-muted-foreground";

// ─── 52-week Range ──────────────────────────────────────────────────────────────

function RangeMarker({ pct, label, color }: { pct: number; label: string; color: string }) {
  return (
    <div className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2" style={{ left: `${pct}%` }}>
      <div className="mx-auto h-3 w-px" style={{ background: color }} />
      <div className="mt-0.5 text-[8px] font-semibold tabular" style={{ color }}>{label}</div>
    </div>
  );
}

export function RangeCard({ data }: { data?: GexRange }) {
  return (
    <Card title="52-Week Range" icon={<TrendingUp className="h-3.5 w-3.5" />}
      note={data?.index_native ? "index" : undefined}>
      {!data ? (
        <Skeleton h={92} />
      ) : (
        (() => {
          const lo = data.low_52w, hi = data.high_52w, span = hi - lo || 1;
          const pos = (x: number | null) => (x == null ? null : clamp01((x - lo) / span) * 100);
          const pSpot = pos(data.spot), p50 = pos(data.ma50), p200 = pos(data.ma200);
          return (
            <div>
              <div className="mb-3 text-sm">
                <span className="tabular text-base font-semibold text-foreground">
                  {data.pct_of_range == null ? "—" : `${data.pct_of_range.toFixed(0)}%`}
                </span>
                <span className="ml-1.5 text-xs text-muted-foreground">of 52-week range</span>
              </div>
              <div className="relative mx-1 h-10">
                <div className="absolute inset-x-0 top-1/2 h-1.5 -translate-y-1/2 rounded-full"
                  style={{ background: "linear-gradient(90deg, var(--loss), var(--muted-foreground), var(--gain))", opacity: 0.35 }} />
                {p200 != null && <RangeMarker pct={p200} label="200" color="var(--muted-foreground)" />}
                {p50 != null && <RangeMarker pct={p50} label="50" color="var(--primary)" />}
                {pSpot != null && (
                  <div className="absolute top-1/2 z-10 -translate-x-1/2 -translate-y-1/2" style={{ left: `${pSpot}%` }}>
                    <div className="h-3.5 w-3.5 rounded-full border-2 border-background bg-foreground shadow" />
                  </div>
                )}
              </div>
              <div className="mt-1 flex justify-between text-[10px] tabular text-muted-foreground">
                <span>{Math.round(lo).toLocaleString("en-US")}</span>
                <span className="text-foreground/80">{Math.round(data.spot).toLocaleString("en-US")}</span>
                <span>{Math.round(hi).toLocaleString("en-US")}</span>
              </div>
            </div>
          );
        })()
      )}
    </Card>
  );
}

// ─── Net Exposure (GEX + DEX, all expiries, with Δ1d + FIRST/OPTIMAL/EVERY) ───────

function ExposureTile({ label, value, delta }: { label: string; value: number | null; delta: number | null }) {
  return (
    <div className="rounded-xl bg-background/30 p-2.5 ring-1 ring-border/40">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className={`tabular text-lg font-semibold ${tone(value)}`}>{fmtUsd(value)}</div>
      <div className="text-[10px] tabular text-muted-foreground">
        {delta == null ? <span className="opacity-50">Δ1d —</span> : <span className={tone(delta)}>{fmtUsd(delta)} <span className="opacity-60">1d</span></span>}
      </div>
    </div>
  );
}

function HorizonRow({ label, sub, v }: { label: string; sub: string; v: number | null }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-muted-foreground">{label} <span className="opacity-50">{sub}</span></span>
      <span className={`tabular ${tone(v)}`}>{fmtUsd(v)}</span>
    </div>
  );
}

export function NetExposureCard({ data, profile }: { data?: GexHorizons; profile?: GexProfile }) {
  const dte = (h?: { dte: number | null }) => (h?.dte == null ? "" : `${h.dte}d`);
  // Headline = the SELECTED expiration's exposure (matches Tanuki's per-expiry view).
  // Δ1d is left blank here: our forward history snapshots the all-expiry aggregate,
  // so a per-expiration Δ1d would be apples-to-oranges. The horizon rows below keep
  // the broader First/Optimal/Every context.
  const expLabel = !profile
    ? "—"
    : profile.cumulative
      ? `≤ ${profile.expirations_used.at(-1)?.slice(5) ?? ""}`
      : profile.expirations_used[0]?.slice(5) ?? "selected";
  return (
    <Card title="Net Exposure" icon={<Activity className="h-3.5 w-3.5" />} note={expLabel}>
      {!profile ? (
        <Skeleton h={150} />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-2">
            <ExposureTile label="Net Gamma" value={profile.net_gex_total} delta={null} />
            <ExposureTile label="Net Delta" value={profile.net_dex_total} delta={null} />
          </div>
          {data && (
            <div className="mt-3 space-y-1.5 border-t border-border/40 pt-2.5 text-[11px]">
              <div className="mb-1 text-[9px] uppercase tracking-wider text-muted-foreground/70">Net GEX by horizon</div>
              <HorizonRow label="First" sub={dte(data.first)} v={data.first.net_gex} />
              <HorizonRow label="Optimal" sub={dte(data.optimal)} v={data.optimal.net_gex} />
              <HorizonRow label="Every" sub={`${data.every.n_exp} exp`} v={data.every.net_gex} />
            </div>
          )}
        </>
      )}
    </Card>
  );
}

// ─── Gamma Profile (regime + ranked key levels) ──────────────────────────────────

const REGIME = {
  positive: { color: "var(--gain)", label: "Positive Gamma", desc: "dealers sell rallies / buy dips — stabilizing" },
  negative: { color: "var(--loss)", label: "Negative Gamma", desc: "dealers buy rallies / sell dips — destabilizing" },
  transition: { color: CYAN, label: "Transition", desc: "price inside the gamma flip band" },
  neutral: { color: "var(--muted-foreground)", label: "Gamma Profile", desc: "select an expiry" },
} as const;

type LevelRow = { name: string; value: number; color: string; key: boolean; spot?: boolean };

export function GammaProfileCard({ profile }: { profile?: GexProfile }) {
  return (
    <Card title="Gamma Profile" icon={<BarChart3 className="h-3.5 w-3.5" />}>
      {!profile ? (
        <Skeleton h={170} />
      ) : (
        (() => {
          const reg = REGIME[profile.regime] ?? REGIME.neutral;
          const lv = profile.levels;
          const scale = profile.index_scale;
          const rows: LevelRow[] = [];
          lv.call_walls.slice(0, 3).forEach((s, i) => rows.push({ name: `C${i + 1}`, value: s, color: "var(--gain)", key: i === 0 }));
          if (lv.c_trans != null) rows.push({ name: "cTrans", value: lv.c_trans, color: CYAN, key: false });
          if (lv.hvl != null) rows.push({ name: "HVL", value: lv.hvl, color: CYAN, key: true });
          if (lv.p_trans != null && lv.p_trans !== lv.hvl) rows.push({ name: "pTrans", value: lv.p_trans, color: CYAN, key: false });
          lv.put_walls.slice(0, 3).forEach((s, i) => rows.push({ name: `P${i + 1}`, value: s, color: "var(--loss)", key: i === 0 }));
          rows.push({ name: profile.underlying, value: profile.spot, color: "var(--foreground)", key: true, spot: true });
          rows.sort((a, b) => b.value - a.value);
          return (
            <div>
              <div className="mb-3 flex items-center gap-2">
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: reg.color, boxShadow: `0 0 8px ${reg.color}` }} />
                <div>
                  <div className="text-xs font-semibold" style={{ color: reg.color }}>{reg.label}</div>
                  <div className="text-[10px] text-muted-foreground">{reg.desc}</div>
                </div>
              </div>
              <ul className="space-y-0.5">
                {rows.map((r, i) => {
                  const d = distPct(r.value, profile.spot);
                  return (
                    <li key={i} className={`flex items-center justify-between rounded px-1.5 py-1 text-xs ${r.spot ? "bg-foreground/5" : ""}`}>
                      <span className="flex items-center gap-2">
                        <span className="h-2 w-2 rounded-full" style={{ background: r.color, opacity: r.key ? 1 : 0.5 }} />
                        <span className={`font-medium ${r.spot ? "text-foreground" : ""}`} style={{ color: r.spot ? undefined : r.color }}>{r.name}</span>
                      </span>
                      <span className="flex items-center gap-2">
                        <span className="tabular text-foreground">{fmtLevel(r.value, scale)}</span>
                        <span className="w-12 text-right text-[10px] tabular text-muted-foreground">
                          {d == null || r.spot ? "" : `${d > 0 ? "+" : ""}${d.toFixed(2)}%`}
                        </span>
                      </span>
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        })()
      )}
    </Card>
  );
}

// ─── Chain Activity (Lean / Shift + VOL/OI ratios) ───────────────────────────────

function RatioTile({ label, ratio, call, put }: { label: string; ratio: number | null; call: number; put: number }) {
  const total = call + put;
  const callShare = total > 0 ? (call / total) * 100 : 50;
  const fmtK = (v: number) => (v >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : v >= 1e3 ? `${(v / 1e3).toFixed(0)}K` : `${v.toFixed(0)}`);
  return (
    <div className="rounded-xl bg-background/30 p-2.5 ring-1 ring-border/40">
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{label}</span>
        <span className="tabular text-[11px] text-foreground">C/P {ratio == null ? "—" : ratio.toFixed(2)}</span>
      </div>
      <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-[var(--loss)]/30">
        <div className="h-full rounded-full bg-[var(--gain)]" style={{ width: `${callShare}%` }} />
      </div>
      <div className="mt-1 flex justify-between text-[10px] tabular">
        <span className="text-[var(--gain)]">{fmtK(call)}</span>
        <span className="text-[var(--loss)]">{fmtK(put)}</span>
      </div>
    </div>
  );
}

export function ChainActivityCard({ profile }: { profile?: GexProfile }) {
  const a = profile?.activity;
  const leanPct = a?.lean == null ? 50 : clamp01(a.lean) * 100;
  return (
    <Card title="Chain Activity" icon={<Gauge className="h-3.5 w-3.5" />} note="not directional">
      {!a ? (
        <Skeleton h={140} />
      ) : (
        <>
          <div className="mb-2 flex items-center gap-2">
            <span className={`rounded-md px-2 py-0.5 text-xs font-semibold ${a.lean_label === "calls" ? "bg-[var(--gain)]/15 text-[var(--gain)]" : a.lean_label === "puts" ? "bg-[var(--loss)]/15 text-[var(--loss)]" : "bg-foreground/10 text-muted-foreground"}`}>
              Lean: {a.lean_label ? a.lean_label.toUpperCase() : "—"}
            </span>
            <span className={`rounded-md px-2 py-0.5 text-[10px] font-medium ring-1 ${a.shift ? "text-[var(--warning)] ring-[var(--warning)]/40" : "text-muted-foreground ring-border/40"}`}>
              {a.shift ? "⚡ Shift" : "Aligned"}
            </span>
          </div>
          <div className="relative my-3 h-1.5 rounded-full" style={{ background: "linear-gradient(90deg, var(--loss), var(--muted-foreground), var(--gain))", opacity: 0.5 }}>
            <div className="absolute top-1/2 h-3.5 w-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-foreground shadow" style={{ left: `${leanPct}%` }} />
          </div>
          <div className="mb-2 flex justify-between text-[9px] uppercase tracking-wider text-muted-foreground">
            <span>Puts</span><span>Balanced</span><span>Calls</span>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <RatioTile label="Vol" ratio={a.vol_cp} call={a.call_vol} put={a.put_vol} />
            <RatioTile label="OI" ratio={a.oi_cp} call={a.call_oi} put={a.put_oi} />
          </div>
        </>
      )}
    </Card>
  );
}
