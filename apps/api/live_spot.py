"""
live_spot.py — current spot prices per underlying for the dashboard's live
BE→Spot distance feature.

Design:
  - Quotes come from Yahoo's public chart endpoint
    (query1.finance.yahoo.com/v8/finance/chart/<symbol>) using the stdlib
    urllib — NO third-party dependency. This deliberately avoids `yfinance`,
    which (a) isn't installed in the API runtime and (b) hits a bulk-download
    rate limit on cloud IPs (see context/known_issues.md). The chart endpoint
    returns the live `regularMarketPrice` and is not crumb/auth-gated.
  - One small GET per distinct underlying per refresh, served thereafter from a
    process-level cache, so the dashboard's 60s frontend polling does NOT
    multiply network calls.
  - Cache TTL defaults to 900s (15 min). Rate math: <=4 refresh cycles/hour,
    ~26 over a 6.5h session — a handful of GETs each. Tune via SPOT_CACHE_TTL.
  - Every failure path is graceful: a failed symbol simply yields no entry and
    the caller falls back to the trade's open price (source="open").

Public API:
  get_live_spots(underlyings) -> {UNDERLYING: {"price": float, "asof": iso,
                                               "source": "live"}}
Only underlyings successfully priced appear in the result.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

# Desk underlying → Yahoo Finance symbol. Indices need the ^ prefix; ETFs and
# crypto use their plain/Yahoo ticker. Aliases (SPXW→SPX, NDXP→NDX, BITCOIN→BTC)
# are already normalized upstream in main.py before reaching here.
YF_SYMBOLS: dict[str, str] = {
    "SPX": "^GSPC",
    "NDX": "^NDX",
    "RUT": "^RUT",
    "XSP": "^XSP",
    "SPY": "SPY",
    "QQQ": "QQQ",
    "IWM": "IWM",
    "DIA": "DIA",
    "GLD": "GLD",
    "SLV": "SLV",
    "XLB": "XLB",
    "XLC": "XLC",
    "XLE": "XLE",
    "XLF": "XLF",
    "XLI": "XLI",
    "XLK": "XLK",
    "XLP": "XLP",
    "XLRE": "XLRE",
    "XLU": "XLU",
    "XLV": "XLV",
    "XLY": "XLY",
    "BTC": "BTC-USD",
}

SPOT_CACHE_TTL = int(os.getenv("SPOT_CACHE_TTL", "900"))
# Min seconds between network attempts. Bounds latency + protects the source if
# it ever throttles: a failed fetch won't be retried on the next 60s poll, only
# after this backoff. Never longer than the success TTL.
_RETRY_BACKOFF = min(SPOT_CACHE_TTL, int(os.getenv("SPOT_RETRY_BACKOFF", "120")))
_HTTP_TIMEOUT = float(os.getenv("SPOT_HTTP_TIMEOUT", "8"))

_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=1d&interval=1d"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Process-level cache: {underlying: {"price", "asof", "source"}}.
_cache: dict[str, dict] = {}
_cache_fetched_at: float = 0.0  # last SUCCESSFUL fetch
_last_attempt_at: float = 0.0   # last network attempt (success or failure)
_lock = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _fetch_one(yf_symbol: str) -> float | None:
    """Live price for one Yahoo symbol via the chart endpoint. Never raises."""
    url = _CHART_URL.format(sym=urllib.parse.quote(yf_symbol))
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
            data = json.load(resp)
        result = data["chart"]["result"][0]
        meta = result.get("meta") or {}
        price = meta.get("regularMarketPrice")
        if price is None:
            # Pre/post-market or odd payload: use the last non-null close.
            closes = (result.get("indicators", {}).get("quote", [{}])[0].get("close")) or []
            for c in reversed(closes):
                if c is not None:
                    price = c
                    break
        if price is None:
            return None
        price = float(price)
        return price if price > 0 else None
    except Exception:
        return None


def _fetch_spots(yf_symbols: list[str]) -> dict[str, float]:
    """Fetch each symbol's live price. Returns {yf_symbol: price}; failures omitted."""
    out: dict[str, float] = {}
    for sym in yf_symbols:
        price = _fetch_one(sym)
        if price is not None:
            out[sym] = price
    return out


def get_live_spots(underlyings: set[str]) -> dict[str, dict]:
    """Current spot per underlying, fetched once per cycle and cached.

    Returns only underlyings that were priced this cycle, e.g.
        {"SPX": {"price": 5821.3, "asof": "2026-05-20T18:02:11+00:00", "source": "live"}}
    Unknown symbols (not in YF_SYMBOLS) and failed fetches are simply omitted —
    the caller falls back to the trade's open price.
    """
    global _cache_fetched_at, _last_attempt_at

    wanted = {u for u in underlyings if u in YF_SYMBOLS}
    if not wanted:
        return {}

    with _lock:
        now = time.time()

        # Serve from cache when the last success is still fresh and covers all wanted.
        fresh = (now - _cache_fetched_at) < SPOT_CACHE_TTL
        if fresh and wanted.issubset(_cache.keys()):
            return {u: _cache[u] for u in wanted}

        # A fetch is needed (stale, or a newly-requested underlying isn't cached).
        # Throttle network attempts so a throttled source isn't hit on every 60s
        # poll — serve whatever we already have until the backoff passes.
        if (now - _last_attempt_at) < _RETRY_BACKOFF:
            return {u: _cache[u] for u in wanted if u in _cache}

        # Fetch the full union (cached + newly requested) so subsequent requests
        # for any of them are served warm.
        _last_attempt_at = now
        union = set(_cache.keys()) | wanted
        yf_for = {YF_SYMBOLS[u]: u for u in union}
        prices = _fetch_spots(list(yf_for.keys()))

        asof = _now_iso()
        refreshed: dict[str, dict] = {}
        for yf_sym, price in prices.items():
            underlying = yf_for[yf_sym]
            refreshed[underlying] = {"price": price, "asof": asof, "source": "live"}

        if refreshed:
            _cache.update(refreshed)
            _cache_fetched_at = time.time()

        return {u: _cache[u] for u in wanted if u in _cache}
