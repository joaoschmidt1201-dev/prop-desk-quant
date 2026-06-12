// Shared formatting for the GEX views. SPX/NDX/RUT are read from Yahoo's native
// cash-index chains (^SPX/^NDX/^RUT) — strikes and dollar magnitudes are already
// in index space, so `index_scale` is null and nothing is relabeled. The ×scale
// path only fires in the legacy ETF-proxy fallback (GEX_NATIVE_INDEX=0), where a
// strike/level is relabeled to index-equivalent (see context/tanuki/CROSS_VALIDATION.md).

export const LEVEL_COLORS = {
  call: "var(--gain)",
  put: "var(--loss)",
  hvl: "#22d3ee", // cyan — HVL / transitions (matches Tanuki)
  trans: "#22d3ee",
  abs: "var(--warning)",
  dex: "var(--accent)",
  spot: "var(--muted-foreground)",
} as const;

/** Compact signed USD: +$1.23B / −$45.6M / +$700K. */
export function fmtUsd(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "—";
  const sign = v > 0 ? "+" : v < 0 ? "−" : "";
  const a = Math.abs(v);
  if (a >= 1e9) return `${sign}$${(a / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `${sign}$${(a / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `${sign}$${(a / 1e3).toFixed(0)}K`;
  return `${sign}$${a.toFixed(0)}`;
}

/** Strike/level in index-equivalent terms (×scale) or raw when not a proxy. */
export function scaleStrike(v: number | null | undefined, scale: number | null): number | null {
  if (v == null) return null;
  return scale ? v * scale : v;
}

/** Level label, index-equivalent, thousands-separated. */
export function fmtLevel(v: number | null | undefined, scale: number | null): string {
  const s = scaleStrike(v, scale);
  return s == null ? "—" : Math.round(s).toLocaleString("en-US");
}

/** Distance from spot in % (scale-invariant — both sides ×scale cancel). */
export function distPct(v: number | null | undefined, spot: number | null | undefined): number | null {
  if (v == null || !spot) return null;
  return ((v - spot) / spot) * 100;
}

export const clamp01 = (x: number) => Math.max(0, Math.min(1, x));

export function fmtSignedPct(v: number | null | undefined, digits = 2): string {
  if (v == null || Number.isNaN(v)) return "—";
  return `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(digits)}%`;
}
