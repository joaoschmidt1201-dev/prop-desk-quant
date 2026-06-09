"use client";

import { useState } from "react";
import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Clock,
  Gauge,
  Layers,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import { api, type Gex0dte, type GexExpirations, type GexProfile } from "@/lib/api";
import { DASHBOARD_REFETCH_INTERVAL_MS } from "@/lib/refresh";
import { GexProfileChart } from "./gex-profile-chart";
import { NetGexTimeseries } from "./net-gex-timeseries";

// Desk universe (indices read via their ETF proxy + the ETFs natively).
const UNDERLYINGS = ["SPX", "NDX", "RUT", "SPY", "QQQ", "IWM"];

type Props = {
  underlying: string;
  initialExpirations: GexExpirations | null;
  initialProfile: GexProfile | null;
};

function fmtGex(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const sign = v > 0 ? "+" : v < 0 ? "−" : "";
  const a = Math.abs(v);
  if (a >= 1e9) return `${sign}$${(a / 1e9).toFixed(2)}Bn`;
  if (a >= 1e6) return `${sign}$${(a / 1e6).toFixed(0)}M`;
  if (a >= 1e3) return `${sign}$${(a / 1e3).toFixed(0)}K`;
  return `${sign}$${a.toFixed(0)}`;
}

export function GexDashboard({ underlying: initialUnderlying, initialExpirations, initialProfile }: Props) {
  const [underlying, setUnderlying] = useState(initialUnderlying);
  const [exp, setExp] = useState<string | undefined>(undefined);
  const [cumulative, setCumulative] = useState(false);

  const isInitial = underlying === initialUnderlying;

  const expQ = useQuery({
    queryKey: ["gex-exp", underlying],
    queryFn: () => api.gexExpirations(underlying),
    initialData: isInitial ? (initialExpirations ?? undefined) : undefined,
    refetchInterval: DASHBOARD_REFETCH_INTERVAL_MS,
    refetchIntervalInBackground: true,
  });

  const profileQ = useQuery({
    queryKey: ["gex-profile", underlying, exp ?? "nearest", cumulative],
    queryFn: () => api.gexProfile(underlying, exp, cumulative),
    initialData: isInitial && !exp && !cumulative ? (initialProfile ?? undefined) : undefined,
    placeholderData: (prev) => prev,
    refetchInterval: DASHBOARD_REFETCH_INTERVAL_MS,
    refetchIntervalInBackground: true,
  });

  const zeroQ = useQuery({
    queryKey: ["gex-0dte", underlying],
    queryFn: () => api.gex0dte(underlying),
    refetchInterval: DASHBOARD_REFETCH_INTERVAL_MS,
    refetchIntervalInBackground: true,
  });

  const tsQ = useQuery({
    queryKey: ["gex-ts", underlying],
    queryFn: () => api.gexTimeseries(underlying),
    refetchInterval: DASHBOARD_REFETCH_INTERVAL_MS,
  });

  function switchUnderlying(u: string) {
    setUnderlying(u);
    setExp(undefined);
    setCumulative(false);
  }

  const profile = profileQ.data;
  const expirations = expQ.data?.expirations ?? [];
  // Highlight the chip(s) the backend actually aggregated — truth-based, so it
  // stays correct whether we sent an explicit exp or fell back to the default.
  const usedExps = profile?.expirations_used ?? [];

  return (
    <div className="flex flex-col gap-5 p-6">
      <Header profile={profile} meta={expQ.data} />

      <div className="flex flex-col gap-3 rounded-2xl border border-border/40 bg-card/30 p-4">
        <ChipRow label="Underlying">
          {UNDERLYINGS.map((u) => (
            <Chip key={u} active={u === underlying} onClick={() => switchUnderlying(u)}>
              {u}
            </Chip>
          ))}
        </ChipRow>
        <ChipRow label="Expiration">
          {expirations.length === 0 ? (
            <span className="text-xs text-muted-foreground">—</span>
          ) : (
            <div className="flex max-w-full gap-1.5 overflow-x-auto pb-1">
              {expirations.map((e) => (
                <Chip key={e.unix} active={!cumulative && usedExps.includes(e.date)} onClick={() => { setCumulative(false); setExp(e.date); }}>
                  <span className="whitespace-nowrap">{e.date}</span>
                  <span className="ml-1 text-[10px] opacity-70">{e.dte}d</span>
                </Chip>
              ))}
            </div>
          )}
          <Chip active={cumulative} onClick={() => setCumulative((c) => !c)}>
            <Layers className="h-3 w-3" /> Cumulative
          </Chip>
        </ChipRow>
      </div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-12">
        <section className="rounded-2xl border border-border/40 bg-card/30 p-5 xl:col-span-8">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold tracking-tight">
              GEX Profile{cumulative ? " · cumulative" : ""}
            </h2>
            <span className="text-[11px] text-muted-foreground">
              {profile?.expirations_used?.join(" · ")}
            </span>
          </div>
          {profileQ.isError && <ErrorBox msg="Chain unavailable — market closed or source throttled. Retrying…" />}
          {!profile && !profileQ.isError && <Skeleton h={420} />}
          {profile && <GexProfileChart profile={profile} />}
        </section>

        <div className="flex flex-col gap-5 xl:col-span-4">
          <ZeroDteCard data={zeroQ.data} />
          <LevelsCard profile={profile} />
        </div>
      </div>

      <section className="rounded-2xl border border-border/40 bg-card/30 p-5">
        <div className="mb-1 flex items-center gap-2">
          <Activity className="h-4 w-4 text-primary" />
          <h2 className="text-sm font-semibold tracking-tight">Net GEX — forward history</h2>
        </div>
        <p className="mb-3 text-[11px] text-muted-foreground">
          Built from our own snapshots going forward — fills in as the tool runs.
        </p>
        <NetGexTimeseries points={tsQ.data?.points ?? []} />
      </section>
    </div>
  );
}

function Header({ profile, meta }: { profile?: GexProfile; meta?: GexExpirations }) {
  const proxy = profile?.proxy ?? meta?.proxy;
  const ysym = profile?.yahoo_symbol ?? meta?.yahoo_symbol;
  const idx = profile?.index_symbol ?? meta?.index_symbol;
  const title = profile?.underlying ?? meta?.underlying ?? "GEX";
  return (
    <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
      <div>
        <div className="mb-1 inline-flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-[0.22em] text-primary/80">
          <BarChart3 className="h-3 w-3" /> Gamma Exposure
        </div>
        <h1 className="text-2xl font-semibold tracking-tight">
          {title} <span className="text-muted-foreground">Net GEX</span>
        </h1>
        <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
          {proxy && (
            <span className="rounded-full bg-amber-400/10 px-2 py-0.5 text-amber-400 ring-1 ring-amber-400/30">
              ETF proxy{ysym ? ` · ${ysym}` : ""}{idx ? ` → ${idx}` : ""}
            </span>
          )}
          <span className="inline-flex items-center gap-1">
            <Clock className="h-3 w-3" />
            {profile?.asof ? new Date(profile.asof).toLocaleTimeString() : "—"} · delayed ~15m · OI updates daily
          </span>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
        <Stat label="Spot" value={profile?.spot != null ? profile.spot.toFixed(2) : "—"} icon={<Gauge className="h-3.5 w-3.5" />} />
        <Stat label="Gamma flip" value={profile?.gamma_flip != null ? String(Math.round(profile.gamma_flip)) : "—"} />
        <Stat label="Call wall" value={profile?.call_wall != null ? String(Math.round(profile.call_wall)) : "—"} tone="up" />
        <Stat label="Put wall" value={profile?.put_wall != null ? String(Math.round(profile.put_wall)) : "—"} tone="down" />
      </div>
    </div>
  );
}

function Stat({ label, value, icon, tone }: { label: string; value: string; icon?: ReactNode; tone?: "up" | "down" }) {
  const color = tone === "up" ? "text-[var(--gain)]" : tone === "down" ? "text-[var(--loss)]" : "text-foreground";
  return (
    <div className="rounded-lg border border-border/30 bg-background/20 px-3 py-1.5">
      <div className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-muted-foreground">
        {icon}
        {label}
      </div>
      <div className={`tabular text-sm font-semibold ${color}`}>{value}</div>
    </div>
  );
}

function ChipRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-20 shrink-0 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
        {label}
      </span>
      <div className="flex flex-1 flex-wrap items-center gap-1.5">{children}</div>
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

function ZeroDteCard({ data }: { data?: Gex0dte }) {
  return (
    <div className="rounded-2xl border border-border/40 bg-card/30 p-5">
      <h3 className="mb-3 text-sm font-semibold tracking-tight">0DTE vs all expirations</h3>
      {!data ? (
        <Skeleton h={72} />
      ) : !data.has_0dte ? (
        <p className="text-xs text-muted-foreground">No 0DTE expiration today for this underlying.</p>
      ) : (
        <div className="grid grid-cols-2 gap-3">
          <Stat label="0DTE Net GEX" value={fmtGex(data.net_gex_0dte)} tone={data.net_gex_0dte >= 0 ? "up" : "down"} />
          <Stat label="All Net GEX" value={fmtGex(data.net_gex_all)} tone={data.net_gex_all >= 0 ? "up" : "down"} />
        </div>
      )}
    </div>
  );
}

function LevelsCard({ profile }: { profile?: GexProfile }) {
  return (
    <div className="rounded-2xl border border-border/40 bg-card/30 p-5">
      <h3 className="mb-3 text-sm font-semibold tracking-tight">Key levels</h3>
      {!profile ? (
        <Skeleton h={120} />
      ) : (
        <ul className="space-y-2 text-sm">
          <LevelRow icon={<TrendingUp className="h-3.5 w-3.5 text-[var(--gain)]" />} label="Call wall" value={profile.call_wall} spot={profile.spot} />
          <LevelRow icon={<Gauge className="h-3.5 w-3.5 text-[var(--accent)]" />} label="Gamma flip" value={profile.gamma_flip} spot={profile.spot} />
          <LevelRow icon={<TrendingDown className="h-3.5 w-3.5 text-[var(--loss)]" />} label="Put wall" value={profile.put_wall} spot={profile.spot} />
          <li className="flex items-center justify-between border-t border-border/40 pt-2 text-xs text-muted-foreground">
            <span>Net GEX total</span>
            <span className="tabular font-semibold text-foreground">{fmtGex(profile.net_gex_total)}</span>
          </li>
        </ul>
      )}
    </div>
  );
}

function LevelRow({ icon, label, value, spot }: { icon: ReactNode; label: string; value: number | null; spot: number }) {
  const dist = value != null ? value - spot : null;
  return (
    <li className="flex items-center justify-between">
      <span className="inline-flex items-center gap-1.5 text-muted-foreground">
        {icon}
        {label}
      </span>
      <span className="tabular">
        {value != null ? Math.round(value) : "—"}
        {dist != null && (
          <span className="ml-2 text-[11px] text-muted-foreground">
            ({dist > 0 ? "+" : ""}
            {Math.round(dist)})
          </span>
        )}
      </span>
    </li>
  );
}

function Skeleton({ h }: { h: number }) {
  return <div className="animate-pulse rounded-xl border border-border/40 bg-card/20" style={{ height: h }} />;
}

function ErrorBox({ msg }: { msg: string }) {
  return (
    <div className="flex items-center gap-2 rounded-xl border border-amber-400/30 bg-amber-400/5 p-4 text-xs text-amber-300">
      <AlertTriangle className="h-4 w-4" />
      {msg}
    </div>
  );
}
