/**
 * Formatting utilities for dashboard numbers.
 * All numbers in the API are in USD; we render them with adaptive precision.
 */

const usd = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

const usdPrecise = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 2,
});

const pct = new Intl.NumberFormat("en-US", {
  style: "percent",
  maximumFractionDigits: 1,
});

const num = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 2,
});

export function fmtMoney(v: number | null | undefined, precise = false): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return precise ? usdPrecise.format(v) : usd.format(v);
}

/** Signed money, for values where the sign carries meaning (net credit + / net debit −). */
export function fmtSignedMoney(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return v > 0 ? `+${usd.format(v)}` : usd.format(v);
}

export function fmtPct(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return pct.format(v);
}

export function fmtNum(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return num.format(v);
}

export function pnlClass(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v) || v === 0) return "text-muted-foreground";
  return v > 0 ? "text-[var(--gain)]" : "text-[var(--loss)]";
}

/** Format an already-percentage value (e.g. -1.8 → "-1.8%"), with a +/- sign. */
export function fmtSignedPct(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return `${v > 0 ? "+" : ""}${v.toFixed(1)}%`;
}

/** Color BE→Spot distance by proximity: breached/within 2% = loss, within 5% = amber. */
export function beDistClass(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "text-muted-foreground";
  const a = Math.abs(v);
  if (v <= 0 || a < 2) return "text-[var(--loss)]";
  if (a < 5) return "text-amber-400";
  return "text-muted-foreground";
}

const DATE_ONLY_RE = /^(\d{4})-(\d{2})-(\d{2})$/;

/**
 * Parse an API date string into a Date.
 *
 * `new Date("2026-07-31")` is UTC midnight per the ECMAScript spec, so rendering it in a
 * negative-offset timezone (BRT is UTC-3) shows the *previous* day. Trade dates from the
 * sheet are calendar dates with no time, so build them from local components instead.
 * Full timestamps (spot_asof, with an offset) keep the normal timezone conversion.
 */
export function parseApiDate(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  const m = DATE_ONLY_RE.exec(iso.trim());
  const d = m ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = parseApiDate(iso);
  if (!d) return iso;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export function fmtRelativeAge(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "no snapshot";
  if (seconds < 60) return `${Math.round(seconds)}s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h ago`;
  return `${Math.round(seconds / 86400)}d ago`;
}
