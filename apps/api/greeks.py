"""
greeks.py — minimal Black-Scholes greeks for the GEX engine.

Only what GEX needs: option *gamma* from a known implied vol. Implemented with
the stdlib ``math`` alone (gamma needs nothing but the normal PDF), so the API
runtime takes on no new dependency — the same discipline live_spot.py follows.
The desk's other Black-Scholes code (scripts/ic7_backtest.py) leans on
scipy.stats.norm, which is deliberately NOT imported here to keep apps/api light.
"""

from __future__ import annotations

import math

_INV_SQRT_2PI = 1.0 / math.sqrt(2.0 * math.pi)

# Floor for time-to-expiry, in years. As an option approaches expiry T -> 0,
# which makes BS gamma diverge / divide-by-zero. Clamp to ~10 minutes of a
# trading year so ATM 0DTE gamma stays large-but-finite instead of exploding.
#   10 min / (252 trading days * 6.5h * 60min) ~= 1.7e-4 years
MIN_T = 1.7e-4


def norm_pdf(x: float) -> float:
    """Standard normal probability density function."""
    return _INV_SQRT_2PI * math.exp(-0.5 * x * x)


def d1(S: float, K: float, T: float, sigma: float, r: float = 0.0, q: float = 0.0) -> float:
    return (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))


def gamma(S: float, K: float, T: float, sigma: float, r: float = 0.0, q: float = 0.0) -> float:
    """Black-Scholes gamma.

    Gamma is identical for calls and puts. Returns 0.0 for degenerate inputs
    (non-positive price/strike/vol) instead of raising, so a single junk strike
    in a chain never breaks the whole profile.
    """
    if S <= 0.0 or K <= 0.0 or sigma <= 0.0:
        return 0.0
    T = max(T, MIN_T)
    try:
        sqrt_t = math.sqrt(T)
        _d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * sqrt_t)
        return norm_pdf(_d1) / (S * sigma * sqrt_t)
    except (ValueError, ZeroDivisionError):
        return 0.0


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_price(S: float, K: float, T: float, sigma: float, r: float = 0.0, *, is_call: bool = True) -> float:
    """Black-Scholes price. Returns intrinsic value for degenerate T/sigma."""
    if S <= 0.0 or K <= 0.0:
        return 0.0
    if T <= 0.0 or sigma <= 0.0:
        return max(0.0, (S - K) if is_call else (K - S))
    sqrt_t = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t
    if is_call:
        return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
    return K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)


def implied_vol(
    price: float | None, S: float, K: float, T: float, r: float = 0.0,
    *, is_call: bool = True, lo: float = 1e-3, hi: float = 5.0,
) -> float | None:
    """Implied vol by bisection. Yahoo's own IV field is unreliable (often 0 or
    1e-5), so the GEX engine inverts IV from the option price instead. Returns
    None when the price is outside the no-arbitrage range — we'd rather drop a
    strike than feed garbage gamma into the aggregation.
    """
    if price is None or price <= 0.0 or S <= 0.0 or K <= 0.0 or T <= 0.0:
        return None
    if price <= bs_price(S, K, T, lo, r, is_call=is_call):
        return None
    if price >= bs_price(S, K, T, hi, r, is_call=is_call):
        return None
    for _ in range(64):
        mid = 0.5 * (lo + hi)
        if bs_price(S, K, T, mid, r, is_call=is_call) > price:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)
