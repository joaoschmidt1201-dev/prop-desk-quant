"""
gex.py — the desk's own Gamma Exposure (GEX) engine.

Forward-looking by design: it pulls the *live* option chain from Yahoo's public
options endpoint (open interest + implied vol per expiration), computes gamma
ourselves via Black-Scholes (greeks.py) and aggregates dealer GEX per strike —
no Barchart, no historical parquet backfill. Accumulated snapshots build our own
Net GEX time-series going forward.

Data source & honesty (see context/known_issues.md, mirrors live_spot.py):
  - Yahoo serves *ETF* option chains reliably (SPY/QQQ/IWM), NOT index chains
    (^GSPC etc). So SPX/NDX/RUT are read through their ETF proxy and the response
    is flagged `proxy=True`. A live index/ETF spot ratio is offered so the UI can
    relabel strikes as index-equivalent.
  - Quotes are delayed ~15 min on the free endpoint.
  - Open interest is an OCC settlement figure that updates ONCE PER DAY. The
    profile "breathes" intraday only because we re-price gamma against the latest
    spot — the OI structure is constant within a day.
  - We use urllib (stdlib) with a UA + cache + backoff. We never use yfinance
    (absent from the API runtime + rate-limited on cloud IPs).

GEX convention (matches Barchart / common retail tools, so levels are comparable):
    GEX_strike_side = gamma * OI * 100 * spot^2 * 0.01   (dollar gamma per 1% move)
    sign: calls (+), puts (-);  NetGEX(K) = call_gex(K) + put_gex(K)
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
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

try:  # robust to both `uvicorn main:app` (from apps/api) and package import
    from .greeks import gamma as bs_gamma, implied_vol
except ImportError:  # pragma: no cover
    from greeks import gamma as bs_gamma, implied_vol

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

# Index → ETF whose Yahoo chain we actually read (Yahoo lacks index option chains).
PROXY_ETF: dict[str, str] = {"SPX": "SPY", "NDX": "QQQ", "RUT": "IWM"}
# ETF → the index it proxies, for relabeling strikes to index-equivalent in the UI.
ETF_INDEX: dict[str, str] = {"SPY": "SPX", "QQQ": "NDX", "IWM": "RUT"}

GEX_CACHE_TTL = int(os.getenv("GEX_CACHE_TTL", "600"))        # 10 min — OI is daily anyway
_RETRY_BACKOFF = min(GEX_CACHE_TTL, int(os.getenv("GEX_RETRY_BACKOFF", "120")))
_HTTP_TIMEOUT = float(os.getenv("GEX_HTTP_TIMEOUT", "10"))
RISK_FREE = float(os.getenv("GEX_RISK_FREE", "0.04"))
# Cap how many expirations we sweep for "all"/cumulative/0DTE-split requests.
# Gamma far out in time is negligible; this bounds the number of HTTP calls.
MAX_EXPIRATIONS = int(os.getenv("GEX_MAX_EXPIRATIONS", "12"))
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

# Per-key chain cache: key = (yahoo_symbol, expiration_unix|0). value = {"data", "at"}.
_cache: dict[tuple[str, int], dict] = {}
_last_attempt: dict[tuple[str, int], float] = {}
_lock = threading.Lock()


class GexError(Exception):
    """Raised when the chain cannot be fetched/parsed (caller maps to HTTP 503)."""


# ─── Symbol resolution ──────────────────────────────────────────────────────────

def resolve_symbol(underlying: str) -> tuple[str, bool]:
    """(yahoo_symbol, is_proxy). 'SPX'->('SPY', True); 'SPY'->('SPY', False)."""
    u = (underlying or "").strip().upper()
    if u in PROXY_ETF:
        return PROXY_ETF[u], True
    return u, False


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _today_et():
    return datetime.now(ET).date()


def _exp_date(unix: int):
    return datetime.fromtimestamp(unix, tz=timezone.utc).date()


def _years_to_exp(exp_unix: int) -> float:
    dte = (_exp_date(exp_unix) - _today_et()).days
    return max(dte, 0) / 365.0


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
    """GET the Yahoo options chain with cookie+crumb; refresh the crumb once on 401."""
    global _crumb
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

def _option_metrics(opt: dict, spot: float, sign: float):
    """Per-option (strike, signed GEX at spot, leg) or None for junk.

    `leg` = (sign, oi, strike, T, iv) feeds the zero-gamma spot sweep. Yahoo's own
    `impliedVolatility` is unreliable (often 0 / 1e-5), so we invert IV from the
    option price — mid when quotes are live, last trade after hours — and only
    fall back to a *plausible* Yahoo IV if inversion fails.
    """
    try:
        strike = float(opt["strike"])
    except (KeyError, TypeError, ValueError):
        return None
    oi = opt.get("openInterest") or 0
    if oi <= 0 or strike <= 0:
        return None

    T = _years_to_exp(int(opt.get("expiration") or 0))
    is_call = sign > 0
    bid = opt.get("bid") or 0.0
    ask = opt.get("ask") or 0.0
    price = (bid + ask) / 2.0 if bid > 0 and ask > 0 else (opt.get("lastPrice") or 0.0)

    iv = implied_vol(price, spot, strike, T, RISK_FREE, is_call=is_call)
    if iv is None:
        y_iv = opt.get("impliedVolatility") or 0.0
        iv = y_iv if 0.01 < y_iv < 3.0 else None
    if iv is None:
        return None

    oi = float(oi)
    gex = sign * bs_gamma(spot, strike, T, iv, RISK_FREE) * oi * 100.0 * spot * spot * 0.01
    return strike, gex, (sign, oi, strike, T, iv)


def _aggregate(calls: list[dict], puts: list[dict], spot: float):
    """(rows, legs): per-strike call/put/net GEX at spot (sorted asc), plus the
    raw legs (sign, oi, K, T, iv) used by the zero-gamma sweep."""
    by_strike: dict[float, dict[str, float]] = {}
    legs: list[tuple] = []
    for opt_list, sign in ((calls, 1.0), (puts, -1.0)):
        key = "call" if sign > 0 else "put"
        for opt in opt_list:
            m = _option_metrics(opt, spot, sign)
            if m is None:
                continue
            strike, gex, leg = m
            by_strike.setdefault(strike, {"call": 0.0, "put": 0.0})[key] += gex
            legs.append(leg)
    rows = [
        {"strike": k, "call_gex": v["call"], "put_gex": v["put"], "net_gex": v["call"] + v["put"]}
        for k, v in by_strike.items()
    ]
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


# ─── Public API ─────────────────────────────────────────────────────────────────

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
    spot = base["spot"]
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
    call_wall, put_wall = _walls(rows)
    net_total = sum(r["net_gex"] for r in rows)

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
        "call_wall": call_wall,
        "put_wall": put_wall,
        "net_gex_total": net_total,
        "asof": base["asof"],
    }
    _maybe_record_history(underlying.upper(), yahoo_symbol, spot, flip, call_wall, put_wall)
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

    net_all = sum(r["net_gex"] for r in _aggregate(all_calls, all_puts, spot)[0])
    net_0dte = sum(r["net_gex"] for r in _aggregate(zero_calls, zero_puts, spot)[0])
    return {
        "underlying": underlying.upper(),
        "spot": spot,
        "net_gex_all": net_all,
        "net_gex_0dte": net_0dte,
        "has_0dte": bool(zero_calls or zero_puts),
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
