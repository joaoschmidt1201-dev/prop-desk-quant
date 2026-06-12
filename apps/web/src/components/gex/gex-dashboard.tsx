"use client";

import { useState } from "react";
import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity, BarChart3, Clock, Layers } from "lucide-react";
import { api, type GexExpirations, type GexMetric, type GexProfile } from "@/lib/api";
import { DASHBOARD_REFETCH_INTERVAL_MS } from "@/lib/refresh";
import { GexProfileChart } from "./gex-profile-chart";
import { NetGexTimeseries } from "./net-gex-timeseries";
import { ChainActivityCard, GammaProfileCard, NetExposureCard, RangeCard } from "./gex-sidebar";
import { fmtLevel, scaleStrike } from "./gex-format";

// Desk universe (indices read via their ETF proxy + the ETFs natively).
const UNDERLYINGS = ["SPX", "NDX", "RUT", "SPY", "QQQ", "IWM"];

const METRICS: { key: GexMetric; label: string }[] = [
  { key: "net_gex", label: "Net GEX" },
  { key: "net_dex", label: "Net DEX" },
  { key: "net_oi", label: "Net OI" },
  { key: "net_vol", label: "Net Vol" },
  { key: "abs_gex", label: "Abs GEX" },
];

const STATE_LABEL: Record<string, string> = {
  positive: "Positive Gamma", negative: "Negative Gamma", transition: "Transition",
  positive_extension: "Positive Extension", negative_extension: "Negative Extension", unknown: "—",
};
const STATE_COLOR: Record<string, string> = {
  positive: "var(--gain)", positive_extension: "var(--gain)",
  negative: "var(--loss)", negative_extension: "var(--loss)",
  transition: "#22d3ee", unknown: "var(--muted-foreground)",
};

type Props = {
  underlying: string;
  initialExpirations: GexExpirations | null;
  initialProfile: GexProfile | null;
};

export function GexDashboard({ underlying: initialUnderlying, initialExpirations, initialProfile }: Props) {
  const [underlying, setUnderlying] = useState(initialUnderlying);
  const [exp, setExp] = useState<string | undefined>(undefined);
  const [cumulative, setCumulative] = useState(false);
  const [metric, setMetric] = useState<GexMetric>("net_gex");

  const isInitial = underlying === initialUnderlying;
  const poll = { refetchInterval: DASHBOARD_REFETCH_INTERVAL_MS, refetchIntervalInBackground: true };

  const expQ = useQuery({
    queryKey: ["gex-exp", underlying],
    queryFn: () => api.gexExpirations(underlying),
    initialData: isInitial ? (initialExpirations ?? undefined) : undefined,
    ...poll,
  });
  const profileQ = useQuery({
    queryKey: ["gex-profile", underlying, exp ?? "nearest", cumulative],
    queryFn: () => api.gexProfile(underlying, exp, cumulative),
    initialData: isInitial && !exp && !cumulative ? (initialProfile ?? undefined) : undefined,
    placeholderData: (prev) => prev,
    ...poll,
  });
  const horizonsQ = useQuery({ queryKey: ["gex-horizons", underlying], queryFn: () => api.gexHorizons(underlying), ...poll });
  const rangeQ = useQuery({ queryKey: ["gex-range", underlying], queryFn: () => api.gexRange(underlying), refetchInterval: 60 * 60 * 1000 });
  const tsQ = useQuery({ queryKey: ["gex-ts", underlying], queryFn: () => api.gexTimeseries(underlying), refetchInterval: DASHBOARD_REFETCH_INTERVAL_MS });

  function switchUnderlying(u: string) {
    setUnderlying(u);
    setExp(undefined);
    setCumulative(false);
  }

  const profile = profileQ.data;
  const expirations = expQ.data?.expirations ?? [];
  const usedExps = profile?.expirations_used ?? [];
  const metricLabel = METRICS.find((m) => m.key === metric)?.label ?? "";

  return (
    <div className="flex flex-col gap-4 p-4 md:p-6">
      <PriceHeader profile={profile} meta={expQ.data} />

      {/* Controls */}
      <div className="glass flex flex-col gap-2.5 rounded-2xl p-3">
        <ChipRow label="Symbol">
          {UNDERLYINGS.map((u) => (
            <Chip key={u} active={u === underlying} onClick={() => switchUnderlying(u)}>{u}</Chip>
          ))}
        </ChipRow>
        <ChipRow label="Expiry">
          {expirations.length === 0 ? (
            <span className="text-xs text-muted-foreground">—</span>
          ) : (
            <div className="flex max-w-full gap-1.5 overflow-x-auto pb-1">
              {expirations.map((e) => (
                <Chip key={e.unix} active={!cumulative && usedExps.includes(e.date)} onClick={() => { setCumulative(false); setExp(e.date); }}>
                  <span className="whitespace-nowrap">{e.date.slice(5)}</span>
                  <span className="ml-1 text-[10px] opacity-70">{e.dte}d</span>
                </Chip>
              ))}
            </div>
          )}
          <Chip active={cumulative} onClick={() => setCumulative((c) => !c)}>
            <Layers className="h-3 w-3" /> Cumulative
          </Chip>
        </ChipRow>
        <ChipRow label="Metric">
          {METRICS.map((m) => (
            <Chip key={m.key} active={m.key === metric} onClick={() => setMetric(m.key)}>{m.label}</Chip>
          ))}
        </ChipRow>
      </div>

      {/* Main grid */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-12">
        <section className="glass min-w-0 rounded-2xl p-4 xl:col-span-8">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-sm font-semibold tracking-tight">
              <BarChart3 className="h-4 w-4 text-primary" />
              {metricLabel} Profile{cumulative ? " · cumulative" : ""}
            </h2>
            <div className="flex items-center gap-3 text-[11px]">
              {profile && (
                <span className="rounded-full px-2 py-0.5 font-medium ring-1"
                  style={{ color: STATE_COLOR[profile.state], borderColor: "transparent", boxShadow: `inset 0 0 0 1px ${STATE_COLOR[profile.state]}40` }}>
                  {STATE_LABEL[profile.state] ?? profile.state}
                </span>
              )}
              <span className="text-muted-foreground">{usedExps.join(" · ")}</span>
            </div>
          </div>
          {profileQ.isError && <ErrorBox msg="Chain unavailable — market closed or source throttled. Retrying…" />}
          {!profile && !profileQ.isError && <Skeleton h={460} />}
          {profile && (
            <div className="max-h-[680px] overflow-y-auto pr-1">
              <GexProfileChart profile={profile} metric={metric} />
            </div>
          )}
        </section>

        <div className="flex min-w-0 flex-col gap-4 xl:col-span-4">
          <RangeCard data={rangeQ.data} />
          <NetExposureCard data={horizonsQ.data} profile={profile} />
          <GammaProfileCard profile={profile} />
          <ChainActivityCard profile={profile} />
        </div>
      </div>

      {/* Forward history — our own series, nobody else has it */}
      <section className="glass rounded-2xl p-4">
        <div className="mb-1 flex items-center gap-2">
          <Activity className="h-4 w-4 text-primary" />
          <h2 className="text-sm font-semibold tracking-tight">Net GEX — forward history</h2>
        </div>
        <p className="mb-3 text-[11px] text-muted-foreground">Built from our own snapshots going forward — fills in as the tool runs.</p>
        <NetGexTimeseries points={tsQ.data?.points ?? []} />
      </section>
    </div>
  );
}

// ─── Price header ────────────────────────────────────────────────────────────────

function PriceHeader({ profile, meta }: { profile?: GexProfile; meta?: GexExpirations }) {
  const proxy = profile?.proxy ?? meta?.proxy;
  const ysym = profile?.yahoo_symbol ?? meta?.yahoo_symbol;
  const idx = profile?.index_symbol ?? meta?.index_symbol;
  const title = profile?.underlying ?? meta?.underlying ?? "GEX";
  const scale = profile?.index_scale ?? null;
  const idxSpot = profile ? scaleStrike(profile.spot, scale) : null;

  return (
    <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
      <div>
        <div className="mb-1 inline-flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-[0.22em] text-primary/80">
          <BarChart3 className="h-3 w-3" /> Gamma Exposure · Live Table
        </div>
        <div className="flex items-baseline gap-3">
          <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
          <span className="tabular text-3xl font-semibold text-foreground">
            {idxSpot != null ? Math.round(idxSpot).toLocaleString("en-US") : "—"}
          </span>
        </div>
        <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
          {proxy && (
            <span className="rounded-full bg-amber-400/10 px-2 py-0.5 text-amber-400 ring-1 ring-amber-400/30">
              ETF proxy{ysym ? ` · ${ysym}` : ""}{idx ? ` → ${idx}` : ""}{scale ? ` ×${scale.toFixed(2)}` : ""}
            </span>
          )}
          <span className="inline-flex items-center gap-1">
            <Clock className="h-3 w-3" />
            {profile?.asof ? new Date(profile.asof).toLocaleTimeString() : "—"} · delayed ~15m · OI daily
          </span>
        </div>
      </div>
      <div className="grid grid-cols-3 gap-1.5">
        <KeyLevel label="C1" value={profile?.levels.call_walls[0] ?? null} scale={scale} tone="up" />
        <KeyLevel label="HVL" value={profile?.levels.hvl ?? null} scale={scale} tone="cyan" />
        <KeyLevel label="P1" value={profile?.levels.put_walls[0] ?? null} scale={scale} tone="down" />
      </div>
    </div>
  );
}

function KeyLevel({ label, value, scale, tone }: { label: string; value: number | null; scale: number | null; tone: "up" | "down" | "cyan" }) {
  const color = tone === "up" ? "var(--gain)" : tone === "down" ? "var(--loss)" : "#22d3ee";
  return (
    <div className="rounded-lg bg-card/40 px-3 py-1.5 ring-1 ring-border/40">
      <div className="text-[10px] font-semibold uppercase tracking-wider" style={{ color }}>{label}</div>
      <div className="tabular text-sm font-semibold text-foreground">{fmtLevel(value, scale)}</div>
    </div>
  );
}

// ─── Bits ────────────────────────────────────────────────────────────────────────

function ChipRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-16 shrink-0 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">{label}</span>
      <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5">{children}</div>
    </div>
  );
}

function Chip({ active, onClick, children }: { active?: boolean; onClick?: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-xs font-medium ring-1 transition ${
        active
          ? "bg-primary/15 text-primary ring-primary/30"
          : "bg-background/30 text-muted-foreground ring-border/40 hover:bg-card/60 hover:text-foreground"
      }`}
    >
      {children}
    </button>
  );
}

function Skeleton({ h }: { h: number }) {
  return <div className="animate-pulse rounded-xl bg-foreground/5" style={{ height: h }} />;
}

function ErrorBox({ msg }: { msg: string }) {
  return (
    <div className="flex items-center gap-2 rounded-xl border border-amber-400/30 bg-amber-400/5 p-4 text-xs text-amber-300">
      {msg}
    </div>
  );
}
