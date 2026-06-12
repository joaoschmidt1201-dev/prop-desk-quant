"""
gex.py — the desk's own Gamma Exposure (GEX) engine.

Forward-looking by design: it pulls the *live* option chain from Yahoo's public
options endpoint (open interest + implied vol per expiration), computes gamma
ourselves via Black-Scholes (greeks.py) and aggregates dealer GEX per strike —
no Barchart, no historical parquet backfill. Accumulated snapshots build our own
Net GEX time-series going forward.

Data source & honesty (see context/known_issues.md, mirrors live_spot.py):
  - Yahoo serves the *native* cash-index option chains under their caret tickers
    (^SPX/^NDX/^RUT) — dense, real institutional OI, sane IV — so SPX/NDX/RUT are
    read directly, no ETF proxy, `proxy=False`. (Verified 2026-06-12: ^SPX returns
    50 expirations, ~250 strikes/expiry, OI in the thousands.) The ETF proxy map is
    kept only as a fallback (GEX_NATIVE_INDEX=0) for SPY/QQQ/IWM-space if a native
    caret chain ever goes dark. When proxied, a live index/ETF spot ratio is
    offered so the UI can relabel strikes as index-equivalent.
  - Quotes are delayed ~15 min on the free endpoint.
  - Open interest is an OCC settlement figure that updates ONCE PER DAY. The
    profile "breathes" intraday only because we re-price gamma against the latest
    spot — the OI structure is constant within a day.
  - We use urllib (stdlib) with a UA + cache + backoff. We never use yfinance
    (absent from the API runtime + rate-limited on cloud IPs).

GEX convention (matches Barchart / common retail tools, so levels are comparable):
    GEX_strike_side = gamma * OI * 100 * spot^2 * 0.01   (dollar gamma per 1% move)
    sign: calls (+), puts (-);  NetGEX(K) = call_gex(K) + put_gex(K)
DEX (delta exposure) convention:
    DEX_strike_side = delta * OI * 100 * spot   (delta already signed: calls 0..1, puts -1..0)
    NetDEX(K) = call_dex(K) + put_dex(K)        (validate magnitude/sign vs Tanuki "Net Delta")
Per-strike also carries: Net OI = call_oi - put_oi, Net Vol = call_vol - put_vol,
AbsGEX = |call_gex| + |put_gex|. The classification engine ranks these into levels
(C1..C6 / P1..P6 walls, Ab1..Ab3, DEX +/-, OI/Vol) — see _classify_* below.
"""

from __future__ import annotations

import http.cookiejar
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, time as dtime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

try:  # robust to both `uvicorn main:app` (from apps/api) and package import
    from .greeks import gamma as bs_gamma, delta as bs_delta, implied_vol
except ImportError:  # pragma: no cover
    from greeks import gamma as bs_gamma, delta as bs_delta, implied_vol

try:  # spot for the index/ETF proxy ratio; never fatal
    from .live_spot import get_live_spots
except ImportError:  # pragma: no cover - `uvicorn main:app` from apps/api
    try:
        from live_spot import get_live_spots
    except Exception:  # pragma: no cover
        get_live_spots = None  # type: ignore[assignment]

# ─── Config ───────────────────────────────────────────────────────────────────

try:
    ET = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover - tzdata missing; fall back to UTC dates
    ET = timezone.utc
REPO_ROOT = Path(__file__).resolve().parents[2]
HISTORY_DIR = REPO_ROOT / "state" / "gex"

# Index → Yahoo's native cash-index caret ticker (real institutional chain).
NATIVE_INDEX: dict[str, str] = {"SPX": "^SPX", "NDX": "^NDX", "RUT": "^RUT"}
# Default to the native index chain; set GEX_NATIVE_INDEX=0 to fall back to the
# ETF proxy below (SPY/QQQ/IWM-space) if a caret chain ever stops serving.
USE_NATIVE_INDEX = os.getenv("GEX_NATIVE_INDEX", "1").strip().lower() not in ("0", "false", "no")
# Index → ETF proxy (fallback only). Read when native is disabled/unavailable.
PROXY_ETF: dict[str, str] = {"SPX": "SPY", "NDX": "QQQ", "RUT": "IWM"}
# ETF → the index it proxies, for relabeling strikes to index-equivalent in the UI.
ETF_INDEX: dict[str, str] = {"SPY": "SPX", "QQQ": "NDX", "IWM": "RUT"}

GEX_CACHE_TTL = int(os.getenv("GEX_CACHE_TTL", "1800"))       # 30 min — OI is daily; spot is refreshed separately
_RETRY_BACKOFF = min(GEX_CACHE_TTL, int(os.getenv("GEX_RETRY_BACKOFF", "120")))
_HTTP_TIMEOUT = float(os.getenv("GEX_HTTP_TIMEOUT", "6"))  # fail fast so a slow fetch holds the gate briefly
# Serialize options fetches and keep a floor between them. Yahoo's v7 options
# endpoint throttles request *bursts* from a shared datacenter IP (Render): one
# GEX page fans out to ~15 chain fetches (per-expiration horizons + cumulative),
# which trips the limit instantly. We make at most ONE options request at a time,
# spaced by GEX_FETCH_MIN_INTERVAL s — a burst becomes a trickle Yahoo tolerates.
# Combined with the long cache + startup warm-up, most requests never hit Yahoo.
GEX_FETCH_MIN_INTERVAL = float(os.getenv("GEX_FETCH_MIN_INTERVAL", "0.4"))
# Symbols to gently pre-warm on startup (nearest chain each) so the first real
# page load reads warm cache instead of bursting the source.
WARM_SYMBOLS = [s.strip().upper() for s in
                os.getenv("GEX_WARM_SYMBOLS", "SPX,SPY,QQQ,IWM,NDX,RUT").split(",") if s.strip()]
RISK_FREE = float(os.getenv("GEX_RISK_FREE", "0.04"))
# Cap how many expirations we sweep for "all"/cumulative/0DTE-split requests.
# Gamma far out in time is negligible; this bounds the number of HTTP calls per
# page (each expiration past the nearest is its own fetch behind the gate), so a
# smaller cap = snappier page + less head-of-line blocking on the serial gate.
MAX_EXPIRATIONS = int(os.getenv("GEX_MAX_EXPIRATIONS", "8"))
# Don't append a history point more often than this (seconds).
HISTORY_MIN_INTERVAL = int(os.getenv("GEX_HISTORY_MIN_INTERVAL", "900"))

_OPTIONS_URL = "https://query1.finance.yahoo.com/v7/finance/options/{sym}"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Yahoo's v7 options endpoint is cookie + crumb gated (the v8 chart endpoint that
# live_spot.py uses is not — that's why spot worked but the chain 401'd). We grab
# a session cookie from fc.yahoo.com, fetch a crumb, cache both, and refresh on a
# 401. Stdlib cookiejar keeps the API's no-extra-deps discipline.
_CRUMB_URL = "https://query2.finance.yahoo.com/v1/test/getcrumb"
_COOKIE_URL = "https://fc.yahoo.com"
_cookie_jar = http.cookiejar.CookieJar()
_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_cookie_jar))
_crumb: str | None = None
_crumb_lock = threading.Lock()

# Global gate: only one options fetch in flight at a time, spaced by the min
# interval. Turns the per-page burst into a serialized trickle the source allows.
_fetch_gate = threading.Lock()
_last_fetch_at = 0.0

# Per-key chain cache: key = (yahoo_symbol, expiration_unix|0). value = {"data", "at"}.
_cache: dict[tuple[str, int], dict] = {}
_last_attempt: dict[tuple[str, int], float] = {}
_lock = threading.Lock()


class GexError(Exception):
    """Raised when the chain cannot be fetched/parsed (caller maps to HTTP 503)."""


# ─── Symbol resolution ──────────────────────────────────────────────────────────

def resolve_symbol(underlying: str) -> tuple[str, bool]:
    """(yahoo_symbol, is_proxy). Native: 'SPX'->('^SPX', False). Proxy fallback
    (GEX_NATIVE_INDEX=0): 'SPX'->('SPY', True). 'SPY'->('SPY', False)."""
    u = (underlying or "").strip().upper()
    if USE_NATIVE_INDEX and u in NATIVE_INDEX:
        return NATIVE_INDEX[u], False
    if u in PROXY_ETF:
        return PROXY_ETF[u], True
    return u, False


def _fresh_spot(underlying: str, fallback: float | None) -> float | None:
    """Live spot from the throttle-safe v8 chart endpoint (live_spot), so the
    profile keeps breathing intraday even when the (daily) option chain is served
    from a long cache. Falls back to the chain's own quote spot on any miss."""
    if get_live_spots is None:
        return fallback
    try:
        u = underlying.upper()
        px = get_live_spots({u}).get(u, {}).get("price")
        return float(px) if px else fallback
    except Exception:
        return fallback


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _today_et():
    return datetime.now(ET).date()


def _exp_date(unix: int):
    return datetime.fromtimestamp(unix, tz=timezone.utc).date()


_SECONDS_PER_YEAR = 365.0 * 24 * 3600.0


def _years_to_exp(exp_unix: int) -> float:
    """Intraday-aware year fraction to the 16:00 ET expiration moment.

    Whole-day resolution made 0DTE gamma explode — T floored to MIN_T all day and
    even after the close, so a dead same-day 0DTE dominated the all-expiry GEX with
    spurious gamma. Counting real time to 4pm ET on the expiry date keeps 0DTE
    realistic during the session and lets expired contracts fall to T=0 so
    _option_metrics drops them.
    """
    expiry = datetime.combine(_exp_date(exp_unix), dtime(16, 0), tzinfo=ET)
    secs = (expiry - datetime.now(ET)).total_seconds()
    return max(secs, 0.0) / _SECONDS_PER_YEAR


# ─── HTTP + cache ───────────────────────────────────────────────────────────────

def _refresh_crumb() -> str | None:
    """Establish a Yahoo session cookie + crumb (cached). Returns None on failure."""
    global _crumb
    try:
        try:
            _opener.open(
                urllib.request.Request(_COOKIE_URL, headers={"User-Agent": _UA}),
                timeout=_HTTP_TIMEOUT,
            )
        except urllib.error.HTTPError:
            pass  # fc.yahoo.com 404s but still drops the session cookie
        req = urllib.request.Request(_CRUMB_URL, headers={"User-Agent": _UA})
        with _opener.open(req, timeout=_HTTP_TIMEOUT) as resp:
            crumb = resp.read().decode("utf-8").strip()
        _crumb = crumb if crumb and "<" not in crumb else None
    except Exception:
        _crumb = None
    return _crumb


def _fetch_options_json(symbol: str, expiration_unix: int | None) -> dict | None:
    """GET the Yahoo options chain with cookie+crumb; refresh the crumb once on 401.

    Serialized behind `_fetch_gate` with a min interval between network hits so a
    page's fan-out of chain fetches can't burst the source from a datacenter IP.
    """
    global _crumb, _last_fetch_at
    with _fetch_gate:
        wait = GEX_FETCH_MIN_INTERVAL - (time.time() - _last_fetch_at)
        if wait > 0:
            time.sleep(wait)
        try:
            for attempt in range(2):
                with _crumb_lock:
                    crumb = _crumb or _refresh_crumb()
                if not crumb:
                    return None
                params = {"crumb": crumb}
                if expiration_unix:
                    params["date"] = str(int(expiration_unix))
                url = _OPTIONS_URL.format(sym=urllib.parse.quote(symbol)) + "?" + urllib.parse.urlencode(params)
                try:
                    with _opener.open(
                        urllib.request.Request(url, headers={"User-Agent": _UA}),
                        timeout=_HTTP_TIMEOUT,
                    ) as resp:
                        return json.load(resp)
                except urllib.error.HTTPError as exc:
                    if exc.code in (401, 403) and attempt == 0:
                        with _crumb_lock:
                            _crumb = None  # stale crumb — refresh and retry once
                        continue
                    return None
                except Exception:
                    return None
            return None
        finally:
            _last_fetch_at = time.time()


def _get_chain(yahoo_symbol: str, expiration_unix: int | None = None) -> dict:
    """Raw chain for a symbol (and optional expiration), cached with backoff.

    Returns {"spot", "expirations" (unix list), "exp_unix", "calls", "puts",
    "asof"}. Raises GexError when nothing usable is available (no cache + fetch
    failed). `calls`/`puts` are the raw Yahoo option dicts for `exp_unix`.
    """
    key = (yahoo_symbol, expiration_unix or 0)
    now = time.time()

    with _lock:
        cached = _cache.get(key)
        if cached and (now - cached["at"]) < GEX_CACHE_TTL:
            return cached["data"]
        # Throttle re-fetch after a failure so we don't hammer a throttled source.
        if (now - _last_attempt.get(key, 0.0)) < _RETRY_BACKOFF and cached:
            return cached["data"]
        _last_attempt[key] = now

    raw = _fetch_options_json(yahoo_symbol, expiration_unix)

    result = None
    if raw:
        try:
            results = raw["optionChain"]["result"]
            result = results[0] if results else None
        except (KeyError, IndexError, TypeError):
            result = None

    if not result:
        with _lock:
            stale = _cache.get(key)
        if stale:
            return stale["data"]
        raise GexError(f"Yahoo options chain unavailable for {yahoo_symbol}")

    quote = result.get("quote") or {}
    spot = quote.get("regularMarketPrice")
    options0 = (result.get("options") or [{}])[0]
    data = {
        "spot": float(spot) if spot else None,
        "expirations": list(result.get("expirationDates") or []),
        "exp_unix": int(options0.get("expirationDate") or (expiration_unix or 0)),
        "calls": options0.get("calls") or [],
        "puts": options0.get("puts") or [],
        "asof": _now_iso(),
    }
    with _lock:
        _cache[key] = {"data": data, "at": time.time()}
    return data


# ─── Aggregation ────────────────────────────────────────────────────────────────

def _invert_iv(opt: dict, spot: float, T: float, is_call: bool) -> float | None:
    """IV inverted from the option's own price (mid when quotes are live, else last
    trade). None when the price is junk / sub-intrinsic and inversion fails."""
    try:
        strike = float(opt["strike"])
    except (KeyError, TypeError, ValueError):
        return None
    bid = opt.get("bid") or 0.0
    ask = opt.get("ask") or 0.0
    price = (bid + ask) / 2.0 if bid > 0 and ask > 0 else (opt.get("lastPrice") or 0.0)
    return implied_vol(price, spot, strike, T, RISK_FREE, is_call=is_call)


def _strike_iv(call: dict | None, put: dict | None, strike: float, spot: float, T: float) -> float | None:
    """One IV for a (strike, expiration), taken from the *OTM* side (put below spot,
    call above). Gamma is a strike property, so call and put MUST share it; using
    the OTM side dodges the deep-ITM trap where a quote prints below intrinsic
    (delayed spot) → inversion fails → Yahoo's 1.0 placeholder IV is pulled in and
    fabricates enormous gamma at high-OI strikes (the 7000 monthly bug). Yahoo's own
    IV is a last resort and only when plausible (never the 1.0 placeholder)."""
    otm, itm = ((put, False), (call, True)) if strike < spot else ((call, True), (put, False))
    for opt, is_call in (otm, itm):
        if opt is not None:
            iv = _invert_iv(opt, spot, T, is_call)
            if iv is not None:
                return iv
    for opt, _is_call in (otm, itm):  # last resort: a *plausible* Yahoo IV
        if opt is not None:
            y = opt.get("impliedVolatility") or 0.0
            if 0.03 < y < 1.5 and abs(y - 1.0) > 1e-6:
                return y
    return None


_ZERO_STRIKE = {
    "call_gex": 0.0, "put_gex": 0.0, "call_dex": 0.0, "put_dex": 0.0,
    "call_oi": 0.0, "put_oi": 0.0, "call_vol": 0.0, "put_vol": 0.0,
}


def _aggregate(calls: list[dict], puts: list[dict], spot: float):
    """(rows, legs): per-strike GEX/DEX/OI/Volume at spot (sorted asc), plus the
    raw legs (sign, oi, K, T, iv) used by the zero-gamma sweep.

    Call and put at a (strike, expiration) are paired and share ONE IV/gamma from
    the OTM side, so a deep-ITM mispricing can't fabricate gamma. Strikes accumulate
    across expirations (cumulative view) into one row. Each row carries call/put +
    net for every family, plus abs_gex, so the classification engine reads one table.
    """
    pairs: dict[tuple[float, int], dict] = {}
    for opt_list, side in ((calls, "call"), (puts, "put")):
        for opt in opt_list:
            try:
                strike = float(opt["strike"])
            except (KeyError, TypeError, ValueError):
                continue
            if strike <= 0:
                continue
            exp_unix = int(opt.get("expiration") or 0)
            pairs.setdefault((strike, exp_unix), {})[side] = opt

    by_strike: dict[float, dict[str, float]] = {}
    legs: list[tuple] = []
    for (strike, exp_unix), cp in pairs.items():
        T = _years_to_exp(exp_unix)
        if T <= 0.0:
            continue  # expired (past 16:00 ET) — no live gamma/delta
        call, put = cp.get("call"), cp.get("put")
        iv = _strike_iv(call, put, strike, spot, T)
        if iv is None:
            continue
        g = bs_gamma(spot, strike, T, iv, RISK_FREE)
        for opt, side, sign, is_call in (
            (call, "call", 1.0, True), (put, "put", -1.0, False),
        ):
            if opt is None:
                continue
            oi = float(opt.get("openInterest") or 0.0)
            if oi <= 0:
                continue
            row = by_strike.setdefault(strike, dict(_ZERO_STRIKE))
            row[f"{side}_gex"] += sign * g * oi * 100.0 * spot * spot * 0.01
            row[f"{side}_dex"] += bs_delta(spot, strike, T, iv, RISK_FREE, is_call=is_call) * oi * 100.0 * spot
            row[f"{side}_oi"] += oi
            row[f"{side}_vol"] += float(opt.get("volume") or 0.0)
            legs.append((sign, oi, strike, T, iv))
    rows = []
    for k, v in by_strike.items():
        rows.append({
            "strike": k,
            "call_gex": v["call_gex"], "put_gex": v["put_gex"],
            "net_gex": v["call_gex"] + v["put_gex"],
            "abs_gex": abs(v["call_gex"]) + abs(v["put_gex"]),
            "call_dex": v["call_dex"], "put_dex": v["put_dex"],
            "net_dex": v["call_dex"] + v["put_dex"],
            "call_oi": v["call_oi"], "put_oi": v["put_oi"],
            "net_oi": v["call_oi"] - v["put_oi"],
            "call_vol": v["call_vol"], "put_vol": v["put_vol"],
            "net_vol": v["call_vol"] - v["put_vol"],
        })
    rows.sort(key=lambda r: r["strike"])
    return rows, legs


def _zero_gamma(legs: list[tuple], spot: float) -> float | None:
    """Zero-gamma ('gamma flip') level: the spot S* where total dealer gamma
    exposure changes sign. Computed the proper way — repricing every option's
    gamma across candidate spot levels — not a cross-strike cumulative (which put
    the flip nowhere near spot). Returns the crossing nearest the current spot.
    """
    if not legs or spot <= 0:
        return None
    lo, hi, steps = spot * 0.80, spot * 1.15, 90

    def total_at(s: float) -> float:
        return sum(
            sign * bs_gamma(s, k, t, iv) * oi * 100.0 * s * s * 0.01
            for sign, oi, k, t, iv in legs
        )

    crossings: list[float] = []
    prev_s = lo
    prev_v = total_at(lo)
    for i in range(1, steps + 1):
        s = lo + (hi - lo) * i / steps
        v = total_at(s)
        if (prev_v < 0 <= v) or (prev_v > 0 >= v):
            span = v - prev_v
            frac = (-prev_v / span) if span else 0.5
            crossings.append(prev_s + frac * (s - prev_s))
        prev_s, prev_v = s, v
    if not crossings:
        return None
    return round(min(crossings, key=lambda c: abs(c - spot)), 2)


def _walls(rows: list[dict]) -> tuple[float | None, float | None]:
    """(call_wall, put_wall) = strikes of max positive / most negative Net GEX."""
    if not rows:
        return None, None
    call_wall = max(rows, key=lambda r: r["net_gex"])
    put_wall = min(rows, key=lambda r: r["net_gex"])
    cw = call_wall["strike"] if call_wall["net_gex"] > 0 else None
    pw = put_wall["strike"] if put_wall["net_gex"] < 0 else None
    return cw, pw


# ─── Classification engine (Tanuki "Gamma Classification Engine" parity) ──────────

def _rank(rows: list[dict], key: str, *, positive: bool = True, n: int = 6, strict: bool = True) -> list[float]:
    """Top-n strikes by `key`. positive=True → most positive first (C-walls);
    positive=False → most negative first (P-walls). strict drops the wrong sign /
    zeros so a flat side yields fewer than n (or none)."""
    if positive:
        pool = [r for r in rows if (not strict or r[key] > 0)]
        pool.sort(key=lambda r: -r[key])
    else:
        pool = [r for r in rows if (not strict or r[key] < 0)]
        pool.sort(key=lambda r: r[key])
    return [r["strike"] for r in pool[:n]]


def _argmax_strike(rows: list[dict], key: str, *, positive: bool = True) -> float | None:
    """Strike of the max (positive=True) or min (False) `key`, or None if degenerate."""
    if not rows:
        return None
    r = (max if positive else min)(rows, key=lambda r: r[key])
    if positive and r[key] <= 0:
        return None
    if not positive and r[key] >= 0:
        return None
    return r["strike"]


def _transitions(rows: list[dict], flip: float | None) -> tuple[float | None, float | None]:
    """(pTrans, cTrans) — strikes bracketing the zero-gamma flip on the grid.

    The flip (HVL) itself is exact (zero-gamma sweep). The transition band is our
    best-effort interpretation pending cross-validation vs Tanuki: the nearest
    listed strikes just below / above the flip.
    """
    if flip is None or not rows:
        return None, None
    strikes = [r["strike"] for r in rows]
    below = [s for s in strikes if s <= flip]
    above = [s for s in strikes if s >= flip]
    return (max(below) if below else None), (min(above) if above else None)


def _gex_state(spot, flip, c1, p1, ptrans, ctrans) -> str:
    """Price regime vs gamma structure (Tanuki GEX States)."""
    if spot is None or flip is None:
        return "unknown"
    if c1 is not None and spot > c1:
        return "positive_extension"
    if p1 is not None and spot < p1:
        return "negative_extension"
    if ptrans is not None and ctrans is not None and ptrans <= spot <= ctrans:
        return "transition"
    return "positive" if spot >= flip else "negative"


def _regime(spot, flip, ptrans, ctrans) -> str:
    """3-state HVL badge: positive (green) / transition (blue) / negative (red)."""
    if spot is None or flip is None:
        return "neutral"
    if ptrans is not None and ctrans is not None and ptrans <= spot <= ctrans:
        return "transition"
    return "positive" if spot >= flip else "negative"


def _chain_activity(rows: list[dict]) -> dict:
    """Lean / Shift / Activity from volume vs OI. NOT a directional signal —
    describes the current state (Tanuki convention: Lean = 70/30 volume/OI blend)."""
    cv = sum(r["call_vol"] for r in rows)
    pv = sum(r["put_vol"] for r in rows)
    co = sum(r["call_oi"] for r in rows)
    po = sum(r["put_oi"] for r in rows)
    vol_tot, oi_tot = cv + pv, co + po
    vol_share = cv / vol_tot if vol_tot > 0 else None   # 1.0 = all calls
    oi_share = co / oi_tot if oi_tot > 0 else None
    parts = [(0.70, vol_share), (0.30, oi_share)]
    avail = [(w, s) for w, s in parts if s is not None]
    lean = (sum(w * s for w, s in avail) / sum(w for w, _ in avail)) if avail else None
    shift = (vol_share is not None and oi_share is not None
             and (vol_share > 0.5) != (oi_share > 0.5))
    return {
        "call_vol": cv, "put_vol": pv, "call_oi": co, "put_oi": po,
        "vol_cp": (cv / pv) if pv > 0 else None,
        "oi_cp": (co / po) if po > 0 else None,
        "lean": lean,                                   # 0..1 toward calls
        "lean_label": (None if lean is None else ("calls" if lean > 0.5 else "puts")),
        "shift": bool(shift),
        "activity": (vol_tot / oi_tot) if oi_tot > 0 else None,
    }


def _classify(rows: list[dict], spot: float, flip: float | None) -> dict:
    """Build the full level / state set from the per-strike table (the engine)."""
    call_walls = _rank(rows, "net_gex", positive=True, n=6)     # C1..C6
    put_walls = _rank(rows, "net_gex", positive=False, n=6)     # P1..P6
    ptrans, ctrans = _transitions(rows, flip)
    c1 = call_walls[0] if call_walls else None
    p1 = put_walls[0] if put_walls else None
    return {
        "levels": {
            "call_walls": call_walls,
            "put_walls": put_walls,
            "hvl": flip,
            "c_trans": ctrans,
            "p_trans": ptrans,
            "abs_gex": _rank(rows, "abs_gex", positive=True, n=3, strict=False),   # Ab1..Ab3
            "dex_pos": _argmax_strike(rows, "net_dex", positive=True),             # D+
            "dex_neg": _argmax_strike(rows, "net_dex", positive=False),            # D-
            "oi_call": _argmax_strike(rows, "call_oi", positive=True),             # COI
            "oi_put": _argmax_strike(rows, "put_oi", positive=True),               # POI
        },
        "state": _gex_state(spot, flip, c1, p1, ptrans, ctrans),
        "regime": _regime(spot, flip, ptrans, ctrans),
        "activity": _chain_activity(rows),
        "call_wall": c1,
        "put_wall": p1,
    }


# ─── Public API ─────────────────────────────────────────────────────────────────

def warm_cache() -> int:
    """Gently pre-populate the chain cache for the desk symbols (serialized via the
    fetch gate) so the first real page load reads warm cache instead of bursting
    Yahoo. Warms the *default profile path* (nearest live expiration) — the exact
    chain the page opens on — not just the bare first/0DTE chain. Best-effort;
    never raises. Returns the count of symbols warmed."""
    warmed = 0
    for u in WARM_SYMBOLS:
        try:
            compute_profile(u)
            warmed += 1
        except Exception:
            continue
    return warmed


def list_expirations(underlying: str) -> dict:
    """Available expirations (+ spot + proxy info) for the picker."""
    yahoo_symbol, is_proxy = resolve_symbol(underlying)
    base = _get_chain(yahoo_symbol)
    today = _today_et()
    exps = []
    for unix in base["expirations"]:
        d = _exp_date(int(unix))
        exps.append({"date": d.isoformat(), "unix": int(unix), "dte": (d - today).days})
    exps.sort(key=lambda e: e["unix"])
    return {
        "underlying": underlying.upper(),
        "yahoo_symbol": yahoo_symbol,
        "proxy": is_proxy,
        "index_symbol": ETF_INDEX.get(yahoo_symbol),
        "spot": base["spot"],
        "expirations": exps,
        "asof": base["asof"],
    }


def _index_scale(yahoo_symbol: str, etf_spot: float | None) -> float | None:
    """Live index/ETF spot ratio so the UI can show index-equivalent strikes."""
    index = ETF_INDEX.get(yahoo_symbol)
    if not index or not etf_spot or get_live_spots is None:
        return None
    try:
        spots = get_live_spots({index})
        idx_spot = spots.get(index, {}).get("price")
        return round(idx_spot / etf_spot, 4) if idx_spot else None
    except Exception:
        return None


def _resolve_exp_unix(base: dict, expiration: str | None) -> int | None:
    """Map a 'YYYY-MM-DD' (or None) to the matching expiration unix from the chain."""
    if not expiration:
        return None
    try:
        want = datetime.strptime(expiration, "%Y-%m-%d").date()
    except ValueError:
        return None
    best = min(base["expirations"], key=lambda u: abs((_exp_date(int(u)) - want).days), default=None)
    return int(best) if best is not None else None


def compute_profile(underlying: str, expiration: str | None = None, cumulative: bool = False) -> dict:
    """GEX profile (per-strike call/put/net + flip + walls) for the chosen expiration.

    expiration=None      -> nearest expiration.
    cumulative=True       -> sum every expiration up to and including `expiration`.
    """
    yahoo_symbol, is_proxy = resolve_symbol(underlying)
    base = _get_chain(yahoo_symbol)
    # Chain (OI/IV) is cached long since it's daily; refresh spot live so the
    # profile re-prices against the latest price and keeps breathing intraday.
    spot = _fresh_spot(underlying, base["spot"])
    if not spot:
        raise GexError(f"No spot for {yahoo_symbol}")

    target_unix = _resolve_exp_unix(base, expiration)
    all_exp = sorted(int(u) for u in base["expirations"])
    if cumulative:
        ceiling = target_unix or (all_exp[0] if all_exp else None)
        targets = [u for u in all_exp if ceiling is None or u <= ceiling][:MAX_EXPIRATIONS]
    elif target_unix:
        targets = [target_unix]
    else:
        # Default view: nearest expiration with real life left. The same-day 0DTE
        # is degenerate once it expires (OI/quotes gone), so prefer dte>=1 and let
        # the user click the 0DTE chip explicitly during the session.
        today = _today_et()
        future = [u for u in all_exp if (_exp_date(u) - today).days >= 1]
        targets = future[:1] or all_exp[:1]

    calls: list[dict] = []
    puts: list[dict] = []
    used: list[str] = []
    for unix in targets:
        chain = base if unix == base["exp_unix"] else _get_chain(yahoo_symbol, unix)
        calls += chain["calls"]
        puts += chain["puts"]
        used.append(_exp_date(unix).isoformat())

    rows, legs = _aggregate(calls, puts, spot)
    flip = _zero_gamma(legs, spot)
    cls = _classify(rows, spot, flip)
    net_gex_total = sum(r["net_gex"] for r in rows)
    net_dex_total = sum(r["net_dex"] for r in rows)

    out = {
        "underlying": underlying.upper(),
        "yahoo_symbol": yahoo_symbol,
        "proxy": is_proxy,
        "index_symbol": ETF_INDEX.get(yahoo_symbol),
        "index_scale": _index_scale(yahoo_symbol, spot) if is_proxy else None,
        "spot": spot,
        "expirations_used": used,
        "cumulative": cumulative,
        "strikes": rows,
        "gamma_flip": flip,
        "call_wall": cls["call_wall"],
        "put_wall": cls["put_wall"],
        "net_gex_total": net_gex_total,
        "net_dex_total": net_dex_total,
        "levels": cls["levels"],
        "state": cls["state"],
        "regime": cls["regime"],
        "activity": cls["activity"],
        "asof": base["asof"],
    }
    _maybe_record_history(underlying.upper(), yahoo_symbol, spot, flip,
                          cls["call_wall"], cls["put_wall"])
    return out


def zero_dte_split(underlying: str) -> dict:
    """Net GEX of today's expiration (0DTE) vs all expirations — the MenthorQ gripe."""
    yahoo_symbol, _ = resolve_symbol(underlying)
    base = _get_chain(yahoo_symbol)
    spot = base["spot"]
    if not spot:
        raise GexError(f"No spot for {yahoo_symbol}")
    today = _today_et()

    all_calls: list[dict] = []
    all_puts: list[dict] = []
    zero_calls: list[dict] = []
    zero_puts: list[dict] = []
    for unix in sorted(int(u) for u in base["expirations"])[:MAX_EXPIRATIONS]:
        chain = base if unix == base["exp_unix"] else _get_chain(yahoo_symbol, unix)
        all_calls += chain["calls"]
        all_puts += chain["puts"]
        if _exp_date(unix) == today:
            zero_calls += chain["calls"]
            zero_puts += chain["puts"]

    all_rows = _aggregate(all_calls, all_puts, spot)[0]
    zero_rows = _aggregate(zero_calls, zero_puts, spot)[0]
    return {
        "underlying": underlying.upper(),
        "spot": spot,
        "net_gex_all": sum(r["net_gex"] for r in all_rows),
        "net_gex_0dte": sum(r["net_gex"] for r in zero_rows),
        "net_dex_all": sum(r["net_dex"] for r in all_rows),
        "net_dex_0dte": sum(r["net_dex"] for r in zero_rows),
        "has_0dte": bool(zero_calls or zero_puts),
        "asof": base["asof"],
    }


def _pick_optimal(all_exp_unix: list[int], today) -> int | None:
    """Expiration nearest ~50 DTE inside the 35-70 DTE band (Tanuki 'OPTIMAL');
    fallback to whichever is closest to 50 DTE."""
    if not all_exp_unix:
        return None
    def dte(u):
        return (_exp_date(u) - today).days
    band = [u for u in all_exp_unix if 35 <= dte(u) <= 70]
    pool = band or all_exp_unix
    return min(pool, key=lambda u: abs(dte(u) - 50))


def gex_horizons(underlying: str) -> dict:
    """FIRST (nearest) / OPTIMAL (~monthly 35-70 DTE) / EVERY (all) Net GEX & DEX.

    Tanuki's honest horizon framing (their screener's FIRST/OPTIMAL/EVERY): the
    EVERY total is LEAPS-sensitive and least comparable across tools, so we show it
    *alongside* FIRST and OPTIMAL — the near-term reads the desk actually trades —
    instead of a single noisy 'all expiries' number. Δ1d on EVERY comes from our
    forward history (null until two sessions accumulate — never fabricated).
    """
    yahoo_symbol, is_proxy = resolve_symbol(underlying)
    base = _get_chain(yahoo_symbol)
    spot = base["spot"]
    if not spot:
        raise GexError(f"No spot for {yahoo_symbol}")
    today = _today_et()
    all_exp = sorted(int(u) for u in base["expirations"])[:MAX_EXPIRATIONS]
    # Only LIVE expirations (drop a same-day 0DTE already past 16:00 ET) so FIRST
    # rolls to the next real expiry after the close instead of reading 0.
    live_exp = [u for u in all_exp if _years_to_exp(u) > 0.0] or all_exp
    first_u = live_exp[0] if live_exp else None
    optimal_u = _pick_optimal(live_exp, today)

    def _totals(exp_list: list[int]) -> tuple[float, float]:
        calls: list[dict] = []
        puts: list[dict] = []
        for u in exp_list:
            ch = base if u == base["exp_unix"] else _get_chain(yahoo_symbol, u)
            calls += ch["calls"]
            puts += ch["puts"]
        rows = _aggregate(calls, puts, spot)[0]
        return sum(r["net_gex"] for r in rows), sum(r["net_dex"] for r in rows)

    def _horizon(u: int | None) -> dict:
        if u is None:
            return {"exp": None, "dte": None, "net_gex": None, "net_dex": None}
        g, d = _totals([u])
        return {"exp": _exp_date(u).isoformat(), "dte": (_exp_date(u) - today).days,
                "net_gex": g, "net_dex": d}

    every_g, every_d = _totals(live_exp)
    return {
        "underlying": underlying.upper(),
        "yahoo_symbol": yahoo_symbol,
        "proxy": is_proxy,
        "index_symbol": ETF_INDEX.get(yahoo_symbol),
        "index_scale": _index_scale(yahoo_symbol, spot) if is_proxy else None,
        "spot": spot,
        "first": _horizon(first_u),
        "optimal": _horizon(optimal_u),
        "every": {
            "net_gex": every_g, "net_dex": every_d, "n_exp": len(live_exp),
            "change_1d": _change_1d(underlying.upper(), every_g, every_d),
        },
        "asof": base["asof"],
    }


# ─── Forward-built history (the time-series we trust) ────────────────────────────

def _history_path(underlying: str) -> Path:
    return HISTORY_DIR / f"netgex_history_{underlying.lower()}.json"


def load_history(underlying: str) -> list[dict]:
    path = _history_path(underlying.upper())
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
    return []


def _change_1d(underlying: str, cur_gex: float | None, cur_dex: float | None) -> dict:
    """Δ vs ~24h ago from our forward history. Returns None until a prior session's
    snapshot actually exists — we never fabricate a change we can't source."""
    out = {"gex": None, "dex": None, "ref_ts": None}
    hist = load_history(underlying)
    if not hist:
        return out
    now = time.time()
    target = now - 24 * 3600.0
    prior, best = None, None
    for h in hist:
        try:
            ts = datetime.fromisoformat(h["ts"]).timestamp()
        except (KeyError, ValueError):
            continue
        if now - ts < 12 * 3600.0:        # too recent to count as a prior session
            continue
        gap = abs(ts - target)
        if best is None or gap < best:
            best, prior = gap, h
    if prior is None:
        return out
    if cur_gex is not None and prior.get("net_gex_total") is not None:
        out["gex"] = cur_gex - prior["net_gex_total"]
    if cur_dex is not None and prior.get("net_dex_total") is not None:
        out["dex"] = cur_dex - prior["net_dex_total"]
    out["ref_ts"] = prior.get("ts")
    return out


def _maybe_record_history(
    underlying: str,
    yahoo_symbol: str,
    spot: float,
    flip: float | None,
    call_wall: float | None,
    put_wall: float | None,
) -> None:
    """Append a Net GEX point, throttled, so the time-series grows forward."""
    history = load_history(underlying)
    now = time.time()
    if history:
        try:
            last = datetime.fromisoformat(history[-1]["ts"]).timestamp()
            if now - last < HISTORY_MIN_INTERVAL:
                return
        except (KeyError, ValueError):
            pass
    try:
        split = zero_dte_split(underlying)
    except GexError:
        return
    history.append({
        "ts": _now_iso(),
        "underlying": underlying,
        "spot": spot,
        "net_gex_total": split["net_gex_all"],
        "net_gex_0dte": split["net_gex_0dte"],
        "net_dex_total": split.get("net_dex_all"),
        "net_dex_0dte": split.get("net_dex_0dte"),
        "gamma_flip": flip,
        "call_wall": call_wall,
        "put_wall": put_wall,
    })
    try:
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        _history_path(underlying).write_text(
            json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError:
        pass
