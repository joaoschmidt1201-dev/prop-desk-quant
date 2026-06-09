"""
Unit tests for the GEX engine (apps/api/greeks.py + apps/api/gex.py).

Pure math only — no network. Validates the Black-Scholes gamma, IV inversion,
the dealer sign convention (calls +, puts -), the zero-gamma (flip) spot sweep
and the walls.
"""

import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

import greeks  # noqa: E402
import gex  # noqa: E402


# ─── greeks ─────────────────────────────────────────────────────────────────────

def test_gamma_atm_greater_than_otm():
    S, T, sigma = 100.0, 30 / 365, 0.20
    atm = greeks.gamma(S, 100, T, sigma)
    otm = greeks.gamma(S, 130, T, sigma)
    assert atm > 0
    assert atm > otm


def test_gamma_degenerate_inputs_return_zero():
    assert greeks.gamma(0, 100, 0.1, 0.2) == 0.0
    assert greeks.gamma(100, 0, 0.1, 0.2) == 0.0
    assert greeks.gamma(100, 100, 0.1, 0.0) == 0.0


def test_gamma_zero_dte_is_finite():
    g = greeks.gamma(100, 100, 0.0, 0.20)  # T floored, no explosion / div0
    assert g > 0 and math.isfinite(g)


def test_implied_vol_roundtrips():
    # Price an option at a known vol, then invert it back.
    S, K, T, r, sigma = 100.0, 100.0, 30 / 365, 0.04, 0.25
    price = greeks.bs_price(S, K, T, sigma, r, is_call=True)
    iv = greeks.implied_vol(price, S, K, T, r, is_call=True)
    assert iv is not None
    assert abs(iv - sigma) < 1e-3


def test_implied_vol_rejects_out_of_range_price():
    S, K, T = 100.0, 100.0, 30 / 365
    assert greeks.implied_vol(0.0, S, K, T) is None      # non-positive
    assert greeks.implied_vol(S + 1, S, K, T) is None    # above no-arb ceiling


# ─── gex aggregation ────────────────────────────────────────────────────────────

def _opt(strike, oi, iv, exp_unix):
    # No bid/ask/last -> engine falls back to a plausible Yahoo IV for the test.
    return {"strike": strike, "openInterest": oi, "impliedVolatility": iv, "expiration": exp_unix}


def test_aggregate_sign_convention_and_net():
    exp = int(time.time()) + 20 * 86400
    rows, legs = gex._aggregate([_opt(100, 1000, 0.2, exp)], [_opt(100, 1000, 0.2, exp)], 100.0)
    row = next(r for r in rows if r["strike"] == 100)
    assert row["call_gex"] > 0          # calls add positive gamma
    assert row["put_gex"] < 0           # puts subtract
    assert abs(row["net_gex"]) < 1e-6   # equal legs cancel
    assert len(legs) == 2


def test_aggregate_skips_zero_oi():
    exp = int(time.time()) + 20 * 86400
    rows, legs = gex._aggregate([_opt(100, 0, 0.2, exp)], [], 100.0)
    assert rows == []                   # zero-OI option contributes nothing
    assert legs == []


def test_zero_gamma_brackets_spot():
    # Put gamma concentrated below, call gamma above -> flip sits between them.
    legs = [
        (1.0, 1000.0, 110.0, 0.05, 0.20),   # call above
        (-1.0, 1000.0, 90.0, 0.05, 0.20),   # put below
    ]
    flip = gex._zero_gamma(legs, 100.0)
    assert flip is not None and 90.0 < flip < 110.0


def test_walls_pick_extreme_strikes():
    rows = [
        {"strike": 90, "net_gex": -50.0},
        {"strike": 100, "net_gex": 10.0},
        {"strike": 110, "net_gex": 80.0},
    ]
    call_wall, put_wall = gex._walls(rows)
    assert call_wall == 110
    assert put_wall == 90


def test_resolve_symbol_proxy_mapping():
    assert gex.resolve_symbol("SPX") == ("SPY", True)
    assert gex.resolve_symbol("spy") == ("SPY", False)
    assert gex.resolve_symbol("RUT") == ("IWM", True)
