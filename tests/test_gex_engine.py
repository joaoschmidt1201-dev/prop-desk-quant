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


def test_resolve_symbol_native_index_default():
    # Default: indices read from Yahoo's native cash-index caret chains, no proxy.
    assert gex.resolve_symbol("SPX") == ("^SPX", False)
    assert gex.resolve_symbol("ndx") == ("^NDX", False)
    assert gex.resolve_symbol("RUT") == ("^RUT", False)
    assert gex.resolve_symbol("spy") == ("SPY", False)


def test_resolve_symbol_proxy_fallback(monkeypatch):
    # GEX_NATIVE_INDEX=0 falls back to the ETF proxy (SPY/QQQ/IWM-space).
    monkeypatch.setattr(gex, "USE_NATIVE_INDEX", False)
    assert gex.resolve_symbol("SPX") == ("SPY", True)
    assert gex.resolve_symbol("RUT") == ("IWM", True)
    assert gex.resolve_symbol("spy") == ("SPY", False)


# ─── greeks: delta ──────────────────────────────────────────────────────────────

def test_delta_call_put_signs_and_atm():
    S, T, sigma = 100.0, 30 / 365, 0.20
    c = greeks.delta(S, 100, T, sigma, is_call=True)
    p = greeks.delta(S, 100, T, sigma, is_call=False)
    assert 0.0 < c < 1.0 and -1.0 < p < 0.0     # calls 0..1, puts -1..0
    assert abs(c - 0.5) < 0.1                    # ATM call delta ~0.5
    assert abs((c - p) - 1.0) < 1e-9            # call - put = e^{-qT} = 1 (q=0)


def test_delta_degenerate_returns_zero():
    assert greeks.delta(0, 100, 0.1, 0.2) == 0.0
    assert greeks.delta(100, 100, 0.1, 0.0) == 0.0


# ─── gex: DEX / OI / Volume / abs aggregation ─────────────────────────────────────

def _opt_full(strike, oi, iv, exp_unix, vol=0.0):
    return {"strike": strike, "openInterest": oi, "impliedVolatility": iv,
            "expiration": exp_unix, "volume": vol}


def test_dex_sign_calls_positive_puts_negative():
    exp = int(time.time()) + 20 * 86400
    rows, _ = gex._aggregate([_opt_full(100, 1000, 0.2, exp)],
                             [_opt_full(100, 1000, 0.2, exp)], 100.0)
    row = next(r for r in rows if r["strike"] == 100)
    assert row["call_dex"] > 0          # call delta positive
    assert row["put_dex"] < 0           # put delta negative
    # ATM call(+0.5) and put(−0.5) deltas roughly cancel → |net| small vs a leg
    assert abs(row["net_dex"]) < abs(row["call_dex"])


def test_aggregate_rich_fields_oi_vol_abs():
    exp = int(time.time()) + 20 * 86400
    rows, _ = gex._aggregate([_opt_full(100, 800, 0.2, exp, vol=500)],
                             [_opt_full(100, 300, 0.2, exp, vol=100)], 100.0)
    row = next(r for r in rows if r["strike"] == 100)
    assert row["call_oi"] == 800 and row["put_oi"] == 300
    assert row["net_oi"] == 500                 # 800 - 300
    assert row["call_vol"] == 500 and row["put_vol"] == 100
    assert row["net_vol"] == 400
    assert row["abs_gex"] >= abs(row["net_gex"]) # |call|+|put| >= |net|


def test_rank_walls_orders_by_net_gex():
    rows = [
        {"strike": 90, "net_gex": -50.0}, {"strike": 95, "net_gex": -120.0},
        {"strike": 100, "net_gex": 10.0}, {"strike": 110, "net_gex": 80.0},
        {"strike": 115, "net_gex": 200.0},
    ]
    assert gex._rank(rows, "net_gex", positive=True, n=6) == [115, 110, 100]
    assert gex._rank(rows, "net_gex", positive=False, n=6) == [95, 90]


def test_chain_activity_lean_shift_and_ratios():
    rows = [{"strike": 100, "call_oi": 100.0, "put_oi": 300.0,
             "call_vol": 700.0, "put_vol": 300.0}]
    act = gex._chain_activity(rows)
    assert act["vol_cp"] == 700.0 / 300.0
    assert act["oi_cp"] == 100.0 / 300.0
    # lean = 0.7*(700/1000) + 0.3*(100/400) = 0.49 + 0.075 = 0.565 -> calls
    assert abs(act["lean"] - 0.565) < 1e-9
    assert act["lean_label"] == "calls"
    assert act["shift"] is True                 # volume call-leaning, OI put-leaning


def test_gex_state_classification():
    # below put wall -> negative extension; above call wall -> positive extension
    assert gex._gex_state(90, 100, 120, 95, 98, 102) == "negative_extension"
    assert gex._gex_state(130, 100, 120, 95, 98, 102) == "positive_extension"
    # inside transition band -> transition; else by side of the flip
    assert gex._gex_state(100, 100, 120, 95, 98, 102) == "transition"
    assert gex._gex_state(110, 100, 120, 95, 98, 102) == "positive"
    assert gex._gex_state(97, 100, 120, 95, 98, 99) == "negative"


def test_classify_full_payload_shape():
    exp = int(time.time()) + 20 * 86400
    calls = [_opt_full(105, 2000, 0.2, exp, vol=400), _opt_full(110, 500, 0.2, exp)]
    puts = [_opt_full(95, 1800, 0.2, exp, vol=200), _opt_full(90, 600, 0.2, exp)]
    rows, legs = gex._aggregate(calls, puts, 100.0)
    cls = gex._classify(rows, 100.0, gex._zero_gamma(legs, 100.0))
    assert set(cls["levels"]) >= {"call_walls", "put_walls", "hvl", "c_trans",
                                  "p_trans", "abs_gex", "dex_pos", "dex_neg",
                                  "oi_call", "oi_put"}
    assert cls["state"] in {"positive", "negative", "transition",
                            "positive_extension", "negative_extension", "unknown"}
    assert cls["regime"] in {"positive", "negative", "transition", "neutral"}
    assert "lean" in cls["activity"]


def test_pick_optimal_prefers_35_70_dte_band():
    from datetime import datetime as _DT, timezone as _TZ, timedelta as _TD
    today = gex._today_et()

    def u(days):  # expiry unix at 12:00 UTC `days` out (noon avoids date rollover)
        d = today + _TD(days=days)
        return int(_DT(d.year, d.month, d.day, 12, 0, tzinfo=_TZ.utc).timestamp())

    # 1, 7, 45, 120 DTE -> OPTIMAL = 45 (in 35-70 band, nearest 50)
    assert gex._exp_date(gex._pick_optimal([u(1), u(7), u(45), u(120)], today)) == today + _TD(days=45)
    # none in band -> fall back to closest to 50 DTE (= 10)
    assert gex._exp_date(gex._pick_optimal([u(1), u(7), u(10)], today)) == today + _TD(days=10)
    assert gex._pick_optimal([], today) is None


def test_change_1d_null_without_history(tmp_path, monkeypatch):
    # No history yet -> never fabricate a change.
    monkeypatch.setattr(gex, "HISTORY_DIR", tmp_path)
    out = gex._change_1d("ZZZ", 1.0e9, 2.0e9)
    assert out == {"gex": None, "dex": None, "ref_ts": None}
