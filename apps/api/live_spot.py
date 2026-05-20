"""
live_spot.py — current spot prices per underlying for the dashboard's live
BE→Spot distance feature.

Design (per the approved plan):
  - ONE batched yfinance call per refresh fetches every requested underlying at
    once, so the dashboard's 60s frontend polling does NOT multiply network
    calls — results are served from a process-level cache.
  - Cache TTL defaults to 900s (15 min). Rate-limit math: <=4 fetch cycles/hour,
    ~26 over a 6.5h session, ~96/day even running 24h — far below any yfinance
    limit. Tune via SPOT_CACHE_TTL.
  - yfinance rate-limits on cloud IPs (see context/known_issues.md), so every
    failure path is graceful: a missing/failed symbol simply yields no entry and
    the caller falls back to the trade's open price (source="open").

Public API:
  get_live_spots(underlyings) -> {UNDERLYING: {"price": float, "asof": iso,
                                               "source": "live"}}
Only underlyings successfully priced appear in the result.
"""

from __future__ import annotations

import os
import threading
import time
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
# Min seconds between network attempts. Bounds latency + protects yfinance when
# rate-limited: a failed fetch won't be retried on the next 60s poll, only after
# this backoff. Never longer than the success TTL.
_RETRY_BACKOFF = min(SPOT_CACHE_TTL, int(os.getenv("SPOT_RETRY_BACKOFF", "120")))

# Process-level cache: {underlying: {"price", "asof", "source"}}.
_cache: dict[str, dict] = {}
_cache_fetched_at: float = 0.0  # last SUCCESSFUL fetch
_last_attempt_at: float = 0.0   # last network attempt (success or failure)
_lock = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _extract_last_close(data, yf_symbol: str, single: bool) -> float | None:
    """Pull the most recent close from a yf.download result, tolerating both the
    single-ticker (flat columns) and multi-ticker (MultiIndex columns) shapes."""
    try:
        if data is None or getattr(data, "empty", True):
            return None
        if single:
            series = data["Close"]
        else:
            # MultiIndex columns: level 0 = field, level 1 = ticker.
            if ("Close", yf_symbol) not in data.columns:
                return None
            series = data[("Close", yf_symbol)]
        series = series.dropna()
        if series.empty:
            return None
        value = float(series.iloc[-1])
        return value if value > 0 else None
    except Exception:
        return None


def _fetch_spots(yf_symbols: list[str]) -> dict[str, float]:
    """Single batched yfinance download for all symbols. Returns {yf_symbol: price}.
    Never raises — any failure yields a partial/empty dict."""
    if not yf_symbols:
        return {}
    try:
        import yfinance as yf
    except Exception:
        return {}

    try:
        data = yf.download(
            tickers=yf_symbols,
            period="1d",
            interval="1d",
            progress=False,
            threads=False,
            auto_adjust=True,
        )
    except Exception:
        return {}

    single = len(yf_symbols) == 1
    out: dict[str, float] = {}
    for sym in yf_symbols:
        price = _extract_last_close(data, sym, single)
        if price is not None:
            out[sym] = price
    return out


def get_live_spots(underlyings: set[str]) -> dict[str, dict]:
    """Current spot per underlying, batched + cached.

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
        # Throttle network attempts so a rate-limited yfinance isn't hammered on
        # every 60s poll — serve whatever we already have until the backoff passes.
        if (now - _last_attempt_at) < _RETRY_BACKOFF:
            return {u: _cache[u] for u in wanted if u in _cache}

        # Fetch the full union (cached + newly requested) in one batched call so
        # subsequent requests for any of them are served warm.
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
