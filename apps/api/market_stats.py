"""market_stats.py — 52-week range + moving averages, index-native.

Yahoo's v8 chart endpoint (the one live_spot.py already uses) is NOT crumb-gated and
serves *indices* (^GSPC / ^NDX / ^RUT) directly — so, unlike the option chain, we read
SPX/NDX/RUT natively here. That gives the 52-week range and 50/200-day moving averages
on the *real index scale* (matches Tanuki's "% of 52w range" and MA levels) instead of
the SPY proxy. ETFs (SPY/QQQ/IWM) use their own symbol. Stdlib only, daily-ish cache.

This is the reliable, free-data context layer for the GEX Live "52w Range" card — no
fabricated numbers: if the fetch fails we return None and the UI simply hides the card.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.parse
import urllib.request
from statistics import fmean

# Index-native where Yahoo serves it; ETFs use themselves.
_YAHOO_SYM: dict[str, str] = {
    "SPX": "^GSPC", "NDX": "^NDX", "RUT": "^RUT",
    "SPY": "SPY", "QQQ": "QQQ", "IWM": "IWM",
}

_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_TTL = int(os.getenv("GEX_RANGE_TTL", "3600"))       # daily figures; 1h cache is plenty
_TIMEOUT = float(os.getenv("GEX_HTTP_TIMEOUT", "10"))

_cache: dict[str, dict] = {}
_lock = threading.Lock()


def _fetch_daily_closes(yahoo_symbol: str) -> list[float]:
    """1 year of daily closes (oldest → newest). Empty list on any failure."""
    url = (_CHART_URL.format(sym=urllib.parse.quote(yahoo_symbol))
           + "?range=1y&interval=1d")
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        raw = json.load(resp)
    result = ((raw.get("chart") or {}).get("result") or [])
    if not result:
        return []
    quote = ((result[0].get("indicators") or {}).get("quote") or [{}])[0]
    return [float(c) for c in (quote.get("close") or []) if c is not None]


_CANDLE_TTL = int(os.getenv("GEX_CANDLE_TTL", "120"))   # intraday bars; short cache
# Allowed (range, interval) pairs Yahoo serves well, mapped from a simple timeframe key.
_TIMEFRAMES: dict[str, tuple[str, str]] = {
    "1d":  ("1d",  "5m"),
    "5d":  ("5d",  "15m"),
    "1mo": ("1mo", "1h"),
    "3mo": ("3mo", "1d"),
    "6mo": ("6mo", "1d"),
    "1y":  ("1y",  "1d"),
}
_candle_cache: dict[tuple[str, str], dict] = {}


def candles(underlying: str, timeframe: str = "5d") -> dict | None:
    """OHLC candles (index-native where Yahoo serves it) for the GEX Live Chart.

    Yahoo's v8 chart endpoint is reliable and not crumb-gated, so candles come free
    and stable even when the option chain throttles. Returns None on failure (UI hides
    the chart rather than show a guess). `timeframe` is one of _TIMEFRAMES keys.
    """
    u = (underlying or "").strip().upper()
    sym = _YAHOO_SYM.get(u, u)
    tf = timeframe if timeframe in _TIMEFRAMES else "5d"
    rng, interval = _TIMEFRAMES[tf]
    key = (u, tf)
    now = time.time()
    with _lock:
        cached = _candle_cache.get(key)
        if cached and now - cached["at"] < _CANDLE_TTL:
            return cached["data"]
    try:
        url = (_CHART_URL.format(sym=urllib.parse.quote(sym))
               + f"?range={rng}&interval={interval}&includePrePost=false")
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            raw = json.load(resp)
        result = ((raw.get("chart") or {}).get("result") or [])
        if not result:
            return None
        r0 = result[0]
        ts = r0.get("timestamp") or []
        q = ((r0.get("indicators") or {}).get("quote") or [{}])[0]
        o, h, l, c = (q.get("open") or [], q.get("high") or [],
                      q.get("low") or [], q.get("close") or [])
        bars = []
        for i, t in enumerate(ts):
            oo, hh, ll, cc = (o[i] if i < len(o) else None, h[i] if i < len(h) else None,
                              l[i] if i < len(l) else None, c[i] if i < len(c) else None)
            if None in (oo, hh, ll, cc):
                continue
            bars.append({"t": int(t), "o": round(float(oo), 2), "h": round(float(hh), 2),
                         "l": round(float(ll), 2), "c": round(float(cc), 2)})
        if not bars:
            return None
        data = {
            "underlying": u,
            "yahoo_symbol": sym,
            "index_native": sym.startswith("^"),
            "timeframe": tf,
            "interval": interval,
            "bars": bars,
            "asof": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now)),
        }
        with _lock:
            _candle_cache[key] = {"data": data, "at": now}
        return data
    except Exception:
        return None


def range_stats(underlying: str) -> dict | None:
    """52-week high/low, % of range, and 50/200-day MAs (index-native where possible).

    Returns None when the data isn't available — the caller hides the card rather
    than show a guessed number (desk rule: zero hallucination).
    """
    u = (underlying or "").strip().upper()
    sym = _YAHOO_SYM.get(u, u)
    now = time.time()
    with _lock:
        cached = _cache.get(u)
        if cached and now - cached["at"] < _TTL:
            return cached["data"]
    try:
        closes = _fetch_daily_closes(sym)
    except Exception:
        closes = []
    if len(closes) < 2:
        return None
    hi, lo, cur = max(closes), min(closes), closes[-1]
    data = {
        "underlying": u,
        "yahoo_symbol": sym,
        "index_native": sym.startswith("^"),
        "spot": cur,
        "high_52w": hi,
        "low_52w": lo,
        "pct_of_range": ((cur - lo) / (hi - lo) * 100.0) if hi > lo else None,
        "ma50": fmean(closes[-50:]) if len(closes) >= 50 else None,
        "ma200": fmean(closes[-200:]) if len(closes) >= 200 else None,
        "samples": len(closes),
        "asof": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now)),
    }
    with _lock:
        _cache[u] = {"data": data, "at": now}
    return data
