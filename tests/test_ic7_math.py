"""Testes de matematica pura do IC7 — expected move e Black-Scholes.

Fundacoes que NAO podem regredir. Se quebra aqui, o P&L dos trades muda
silenciosamente e o desk toma decisao com EV errado.
"""

from __future__ import annotations

import math

import pytest


def test_expected_move_formula():
    """EM = Spot * IV * sqrt(DTE/365) — mesma formula do OptionsStrat."""
    import ic7_backtest as ic7

    # 1SD semanal classico: SPX 5000, IV 20%, 7 DTE
    em = ic7.calc_expected_move(spot=5000.0, iv_atm=0.20, dte_calendar=7)
    expected = 5000.0 * 0.20 * math.sqrt(7 / 365.0)
    assert em == pytest.approx(expected, rel=1e-9)


def test_expected_move_zero_iv():
    """IV zero -> EM zero."""
    import ic7_backtest as ic7

    assert ic7.calc_expected_move(spot=5000.0, iv_atm=0.0, dte_calendar=7) == 0.0


def test_bs_price_call_atm():
    """Black-Scholes ATM call com valores canonicos."""
    import ic7_backtest as ic7

    # S=100, K=100, T=1yr, r=0%, sigma=20% -> preco ~7.97 (referencia conhecida)
    price = ic7._bs_price(S=100.0, K=100.0, T=1.0, r=0.0, sigma=0.20, opt_type="call")
    assert price == pytest.approx(7.9656, abs=0.01)


def test_bs_price_invalid_returns_nan():
    """T=0 ou sigma=0 ou S<=0 retorna NaN."""
    import ic7_backtest as ic7

    assert math.isnan(ic7._bs_price(100, 100, 0.0, 0.0, 0.20, "call"))
    assert math.isnan(ic7._bs_price(100, 100, 1.0, 0.0, 0.0, "call"))
    assert math.isnan(ic7._bs_price(0, 100, 1.0, 0.0, 0.20, "call"))


def test_bs_put_call_parity():
    """C - P = S - K*e^(-rT)  — invariante matematico."""
    import ic7_backtest as ic7

    S, K, T, r, sigma = 5000.0, 5050.0, 7 / 365, 0.04, 0.18
    c = ic7._bs_price(S, K, T, r, sigma, "call")
    p = ic7._bs_price(S, K, T, r, sigma, "put")
    rhs = S - K * math.exp(-r * T)
    assert (c - p) == pytest.approx(rhs, abs=1e-4)
