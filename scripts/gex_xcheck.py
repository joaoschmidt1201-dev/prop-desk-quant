"""
gex_xcheck.py - cross-validate our GEX engine against Tanuki Trade, per expiration.

Pulls our own engine's output for a symbol + a *specific expiration date* and
prints it in Tanuki's own layout (HVL, C1-C6, P1-P6, cTrans/pTrans, Net Gamma,
Net Delta, Gamma regime). Open Tanuki's GEX-Live for the same symbol/expiration
and eyeball the blocks side by side. The *strike* levels (HVL, walls, transitions)
must match Tanuki nearly exactly - they're just ranked high-gamma/OI strikes, so
they're independent of any dollar-magnitude scaling.

Usage:
  python scripts/gex_xcheck.py SPX
  python scripts/gex_xcheck.py SPX --exp 2026-06-15
  python scripts/gex_xcheck.py SPX --exp 2026-06-15 --cumulative
  python scripts/gex_xcheck.py SPX --base https://prop-desk-dashboard-api.onrender.com
  # paste Tanuki's numbers to get the signed diff:
  python scripts/gex_xcheck.py SPX --exp 2026-06-15 --t-hvl 7410 --t-c1 7400 --t-p1 7360

Notes:
  - Default --base is the local dev API (127.0.0.1:8000). Point it at Render to
    validate production.
  - --exp accepts YYYY-MM-DD; omit for the nearest live expiration.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request


def _get(base: str, path: str, params: dict) -> dict:
    url = f"{base.rstrip('/')}{path}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.load(resp)


def _fmt(v, nd=2):
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:,.{nd}f}"
    return f"{v:,}" if isinstance(v, int) else str(v)


def _usd(v):
    if v is None:
        return "-"
    s = "+" if v > 0 else "-" if v < 0 else ""
    a = abs(v)
    if a >= 1e9:
        return f"{s}${a/1e9:.2f}B"
    if a >= 1e6:
        return f"{s}${a/1e6:.1f}M"
    if a >= 1e3:
        return f"{s}${a/1e3:.0f}K"
    return f"{s}${a:.0f}"


def _dist(level, spot):
    if level is None or not spot:
        return ""
    return f"({(level - spot) / spot * 100:+.2f}%)"


def _row(label, ours, spot, tanuki=None):
    base = f"  {label:<10} {_fmt(ours):>12} {_dist(ours, spot):>10}"
    if tanuki is not None:
        diff = "" if (ours is None) else f"d {ours - tanuki:+.2f}"
        base += f"   | Tanuki {_fmt(tanuki):>10}  {diff}"
    return base


def main() -> int:
    ap = argparse.ArgumentParser(description="Cross-check our GEX vs Tanuki for one expiration.")
    ap.add_argument("symbol", help="SPX / NDX / RUT / SPY / QQQ / IWM")
    ap.add_argument("--exp", help="expiration YYYY-MM-DD (default: nearest live)")
    ap.add_argument("--cumulative", action="store_true", help="sum all expirations up to --exp")
    ap.add_argument("--base", default="http://127.0.0.1:8000", help="API base URL")
    # optional Tanuki values to diff against
    ap.add_argument("--t-hvl", type=float)
    ap.add_argument("--t-c1", type=float)
    ap.add_argument("--t-p1", type=float)
    ap.add_argument("--t-flip", type=float)
    args = ap.parse_args()

    sym = args.symbol.upper()
    params = {"underlying": sym}
    if args.exp:
        params["exp"] = args.exp
    if args.cumulative:
        params["cumulative"] = "true"

    try:
        prof = _get(args.base, "/api/gex/profile", params)
    except Exception as exc:  # noqa: BLE001 - CLI, surface the cause plainly
        print(f"ERROR fetching profile from {args.base}: {exc}", file=sys.stderr)
        return 1

    spot = prof.get("spot")
    lv = prof.get("levels") or {}
    cw = lv.get("call_walls") or []
    pw = lv.get("put_walls") or []
    native = not prof.get("proxy")

    print("=" * 64)
    print(f"  GEX CROSS-CHECK - {sym}   ({prof.get('yahoo_symbol')}, "
          f"{'NATIVE' if native else 'PROXY ' + str(prof.get('index_scale'))})")
    print(f"  expiration(s): {', '.join(prof.get('expirations_used') or [])}"
          f"{'  [cumulative]' if prof.get('cumulative') else ''}")
    print(f"  as of: {prof.get('asof')}")
    print("=" * 64)
    print(_row("Spot", spot, spot))
    print(_row("HVL", lv.get("hvl"), spot, args.t_hvl))
    print(_row("Gamma flip", prof.get("gamma_flip"), spot, args.t_flip))
    print(_row("cTrans", lv.get("c_trans"), spot))
    print(_row("pTrans", lv.get("p_trans"), spot))
    print(f"  Regime: {prof.get('regime')}   GEX state: {prof.get('state')}")
    print("-" * 64)
    print("  CALL WALLS (ranked C1..C6)")
    for i, k in enumerate(cw, 1):
        t = args.t_c1 if i == 1 else None
        print(_row(f"C{i}", k, spot, t))
    print("  PUT WALLS (ranked P1..P6)")
    for i, k in enumerate(pw, 1):
        t = args.t_p1 if i == 1 else None
        print(_row(f"P{i}", k, spot, t))
    print("-" * 64)
    print(f"  Net Gamma (GEX):  {_usd(prof.get('net_gex_total'))}")
    print(f"  Net Delta (DEX):  {_usd(prof.get('net_dex_total'))}")
    print(f"  Abs GEX peaks:    {', '.join(_fmt(x) for x in (lv.get('abs_gex') or []))}")
    print(f"  DEX +/- pivots:   {_fmt(lv.get('dex_pos'))} / {_fmt(lv.get('dex_neg'))}")
    print(f"  OI call/put:      {_fmt(lv.get('oi_call'))} / {_fmt(lv.get('oi_put'))}")
    print("=" * 64)
    if native:
        print("  OK native index chain - strikes & $ magnitudes are real SPX space.")
    print("  Open Tanuki GEX-Live for the same symbol/expiration and compare the")
    print("  strike levels (HVL/walls/transitions) - those must match nearly exactly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
