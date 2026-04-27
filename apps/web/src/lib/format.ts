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

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  } catch {
    return iso;
  }
}

export function fmtRelativeAge(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "no snapshot";
  if (seconds < 60) return `${Math.round(seconds)}s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h ago`;
  return `${Math.round(seconds / 86400)}d ago`;
}
