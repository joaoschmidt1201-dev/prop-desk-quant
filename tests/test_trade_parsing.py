"""Parsing dos nomes de trade do CZ.

O CZ nomeia os trades a mao e mudou o padrao em jul/2026 (`260607-3 SPY 1-1-1 45/85`: id vira
YYMMDD-seq e a estrutura pode ter razao de pernas + par de vencimentos). O parser deriva ticker,
familia da estrategia e DTE direto do nome, entao qualquer nome novo precisa de cobertura aqui.
"""

from __future__ import annotations

import pandas as pd
import pytest

import export_control_panel as export
from apps.api import main as api


def test_underlyings_tuple_stays_in_sync() -> None:
    """As duas copias precisam casar: o exporter resolve o ticker no export e a API re-resolve
    ao servir. Ja divergiram uma vez (ARM entrou so num lado)."""
    assert export.TRADE_UNDERLYINGS == api.TRADE_UNDERLYINGS
    assert export.UNDERLYING_ALIASES == api.UNDERLYING_ALIASES


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("260607-2 BE EDGE SP24", "BE"),          # BE = Bloom Energy, ticker novo
        ("260607-3 SPY 1-1-1 45/85", "SPY"),
        ("T89 ARM SS25", "ARM"),
        ("T99 SPX BE 5250", "SPX"),               # 'BE' aqui e breakeven — SPX manda
        ("T58 SMH BPS3", "SMH"),
        ("PL5 SPY 30D", "SPY"),
    ],
)
def test_infer_underlying_from_name(name: str, expected: str) -> None:
    assert api._infer_underlying_from_name(name) == expected
    assert export._infer_underlying(name) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        # Acao NOVA (fora da tupla fixa): resolve pelo 1o token do nome, sem manter a lista a mao.
        ("260724-1 AMD SC7", "AMD"),
        ("T90 COIN PS7", "COIN"),
        ("JS NFLX SS8", "NFLX"),        # prefixo de env "JS " antes do ticker
        ("260724-2 GOOGL IC7", "GOOGL"),  # 5 letras
        ("260724-9 PLTR BPS8", "PLTR"),
    ],
)
def test_infer_underlying_fallback_new_tickers(name: str, expected: str) -> None:
    # os dois modulos precisam concordar (paridade) tambem no fallback.
    assert api._infer_underlying_from_name(name) == expected
    assert export._infer_underlying(name) == expected


@pytest.mark.parametrize(
    "name",
    [
        "260724-1 SC7 sem ticker",   # codigo de estrategia solto nao vira ticker
        "260724-1 CALL FLY teste",   # descritor generico nao vira ticker
    ],
)
def test_infer_underlying_fallback_ignores_non_tickers(name: str) -> None:
    assert api._infer_underlying_from_name(name) is None
    assert export._infer_underlying(name) == "?"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        # iniciais que o CZ padronizou em 2026-07-09
        ("260607-2 BE EDGE SP24", "Short Put"),
        ("260710-3 GLD SC9", "Short Call"),
        ("260713-2 RUT SS25", "Short Strangle"),
        ("260712-1 SPX PCS7", "Bull Put Spread"),
        ("260710-1 QQQ CCS7", "Bear Call Spread"),   # CCS = call credit spread (era "Other")
        ("260711-4 IWM IC10", "Iron Condor"),
        # CS = call spread = bear call = call credit spread; PS = put spread = bull put spread
        # (confirmado pelo CZ em 2026-07-09). Ambos eram "Other".
        ("T70 SLV CS8", "Bear Call Spread"),
        ("T71 SPCX CS7", "Bear Call Spread"),
        ("T73 EWY PS7", "Bull Put Spread"),
        ("T12 SMH PS6", "Bull Put Spread"),
        # estrutura nova
        ("260607-3 SPY 1-1-1 45/85", "1-1-1"),
        # nao-regressao das familias existentes
        ("T42 RUT CALL BEAR + SP 28", "Jade Lizard"),
        ("T29 BAT42", "Batman"),
        ("T37 SPX CALL-HALF BAT42", "Call Fly"),
        ("T38 NDX BULL CALL SP7", "Bull Call"),
        ("T54 GLD TC22/29", "Triple Calendar"),
        ("T45 RUT RJL42", "RJL"),
        ("PL5 SPY 30D", "PL5"),
        ("T72 RUT PFly7", "Put Fly"),             # abreviacao da JUN26 ("PutFly" nos outros)
        ("T67 RUT PutFly6", "Put Fly"),
    ],
)
def test_strategy_family(name: str, expected: str) -> None:
    assert api.strategy_family(name) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        # `\bCS\d*\b` e `\bPS\d*\b` sao curtos: nao podem engolir as siglas vizinhas.
        ("T59 USO BearCS7", "Bear Call Spread"),   # BearCS != CS solto (mesma familia, outra regra)
        ("T58 SMH BPS3", "Bull Put Spread"),       # BPS != PS solto
        ("T78 RUT SP7 (short put) w/ hedge LP5", "Short Put"),   # SP != PS
        ("T75 USO SC4", "Short Call"),             # SC != CS
        ("T77 RUT SS4", "Short Strangle"),
    ],
)
def test_short_initials_do_not_collide(name: str, expected: str) -> None:
    assert api.strategy_family(name) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        # "45/85" sao os VENCIMENTOS; a perna da frente manda. Antes retornava 1 (do "1-1-1").
        ("260607-3 SPY 1-1-1 45/85", 45),
        # sem o strip do id "260607-2 ", o fallback lia o DTE de dentro da data (dava 26).
        ("260607-2 BE EDGE SP24", 24),
        ("260710-1 QQQ CCS7", 7),
        ("T15 IWM 4DTE BAT", 4),
        ("T89 ARM SS25", 25),
        ("PL5 SPY 30D", 30),
        ("T58 SMH BPS3", 3),
        ("T78 RUT SP7 (short put) w/ hedge LP5", 7),
        ("FOR TC 01 RUT 7/10; 8/11", 7),
        ("T22 42 IC, 40 width", 42),
        ("T04 SLV Triple Calendar 11/18DTE", 11),
    ],
)
def test_dte_from_name(name: str, expected: int) -> None:
    assert api.dte_from_name(name) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("260607-3 SPY 1-1-1 45/85", "45/85"),
        ("FOR TC 01 RUT 7/10; 8/11", "7/10"),
        ("T04 SLV Triple Calendar 11/18DTE", "11/18"),
        ("260711-4 IWM IC10", "10"),
    ],
)
def test_parse_strategy_structure(name: str, expected: str) -> None:
    assert api.parse_strategy_structure(name) == expected


@pytest.mark.parametrize(
    ("dte", "expected"),
    [
        (1, "1DTE"), (2, "1DTE"),
        (6, "4DTE"), (13, "7-13DTE"), (21, "14-21DTE"),
        (28, "21/28DTE"), (35, "28/35DTE"),
        (36, "35-40DTE"), (40, "35-40DTE"),
        (41, "40+DTE"), (42, "40+DTE"), (45, "40+DTE"), (85, "40+DTE"),
        (None, "Unknown"),
    ],
)
def test_dte_bucket_from_int(dte: int | None, expected: str) -> None:
    assert api.dte_bucket_from_int(dte) == expected


def test_dte_bucket_order_covers_every_bucket() -> None:
    """DTE_BUCKET_ORDER ordena o grafico; um bucket fora da lista vai parar no fim silenciosamente."""
    produced = {api.dte_bucket_from_int(d) for d in list(range(0, 130)) + [None]}
    assert produced <= set(api.DTE_BUCKET_ORDER)


def test_trade_max_profit_falls_back_to_legacy_net_credit() -> None:
    """Snapshot antigo (pre 2026-07-09) so tem `net_credit`, e ele guarda o max profit."""
    assert api.trade_max_profit({"max_profit": 3186.0, "net_credit": -40.0}) == 3186.0
    assert api.trade_max_profit({"net_credit": 59858.0}) == 59858.0
    assert api.trade_max_profit({"max_profit": 0.0, "net_credit": 999.0}) == 0.0  # 0.0 nao e "vazio"
    assert api.trade_max_profit({}) is None


def test_legacy_snapshot_never_shows_max_profit_as_net_credit() -> None:
    """O Render serve o snapshot commitado ate o 1o tick do scheduler. Num snapshot antigo o
    campo `net_credit` guarda o MAX PROFIT — se vazar cru pro /api/trades, a coluna NC do app
    mostra $59.858 de novo (a reclamacao original do CZ)."""
    snap = {"trades": [{"name": "PL5 SPY 30D", "net_credit": 59858.0, "max_loss": 5142.0}]}

    api._migrate_legacy_trade_fields(snap)

    t = snap["trades"][0]
    assert t["max_profit"] == 59858.0
    assert t["net_credit"] is None      # NC real e desconhecido no snapshot antigo -> "—" no app
    assert t["contracts"] is None


def test_migration_preserves_a_real_net_credit() -> None:
    """Snapshot novo: `max_profit` existe (mesmo que None) -> nao mexer no NC anotado pelo CZ."""
    snap = {"trades": [
        {"name": "PL5 SPY 30D", "max_profit": 59858.0, "net_credit": -40.0, "contracts": 2},
        {"name": "T86 RUT SP29", "max_profit": 1600.0, "net_credit": None, "contracts": None},
        {"name": "orfao visual", "max_profit": None, "net_credit": None},
    ]}

    api._migrate_legacy_trade_fields(snap)

    assert [t["net_credit"] for t in snap["trades"]] == [-40.0, None, None]
    assert [t["max_profit"] for t in snap["trades"]] == [59858.0, 1600.0, None]
    assert snap["trades"][0]["contracts"] == 2


def _snapshot_one(dte_open: int, open_offset_days: int, closed_from_sheets: set[str] | None = None) -> dict:
    """Monta um snapshot de 1 trade RUT p/ testar o is_active. Marca db_robots HOJE (ativo pela data) e abre
    `open_offset_days` atrás com `dte_open` DTE → controla se venceu hoje, ontem ou no futuro. `closed_from_sheets`
    simula o marcador manual 'Closed' que o CZ escreve na célula acima do nome/url no Control Panel."""
    today = pd.Timestamp.today().normalize()
    open_date = today - pd.Timedelta(days=open_offset_days)
    robots = pd.DataFrame([{
        "date": today, "strategy": "260724-1 RUT SS7", "environment": "CZ Trades",
        "env_norm": "CZ_Live", "pnl": 100.0, "delta": 0.1, "was_closed_flag": False,
    }])
    cria = pd.DataFrame([{
        "trade_name": "260724-1 RUT SS7", "max_profit": 500.0, "max_loss": -5000.0,
        "dte_open": dte_open, "dte_open_raw": str(dte_open), "open_date": open_date,
        "underlying_price": 2400.0, "ist_lw_be": 2350.0, "ist_up_be": 2450.0,
        "soll_lw_be": None, "soll_up_be": None, "strikes": "2350P / 2450C", "sd": 0.1,
    }])
    snap = export.build_trade_snapshot(robots, cria, closed_from_sheets)
    assert snap, "snapshot vazio"
    return snap[0]


def test_snapshot_expiry_day_is_still_active() -> None:
    """Vence HOJE (raw_days == 0, '0 DTE') NÃO é fechado — segue aberto até o settlement. Era o bug
    que jogava todo trade de expiry-day pra Closed (e, por tabela, sumia o BE dist)."""
    t = _snapshot_one(dte_open=7, open_offset_days=7)
    assert t["is_active"] is True
    assert t["dte_remaining"] == 0


def test_snapshot_after_expiry_is_closed() -> None:
    """Venceu ONTEM (raw_days == -1) → Closed."""
    t = _snapshot_one(dte_open=7, open_offset_days=8)
    assert t["is_active"] is False


def test_snapshot_future_expiry_is_active() -> None:
    """Vence daqui a dias, SEM marcador manual → Open (dentro do prazo). Regra do João: enquanto não tiver
    'Closed' e estiver antes da expiração, aparece open."""
    t = _snapshot_one(dte_open=7, open_offset_days=2)
    assert t["is_active"] is True
    assert t["dte_remaining"] == 5


def test_snapshot_manual_close_within_dte_is_closed() -> None:
    """Regra do João: o CZ fecha o trade ANTES do vencimento e escreve 'Closed' na célula acima do nome/url.
    O marcador manual vence o DTE → Closed no app JÁ, mesmo com DTE restante > 0."""
    t = _snapshot_one(dte_open=7, open_offset_days=2, closed_from_sheets={"260724-1 RUT SS7"})
    assert t["is_active"] is False
    assert t["dte_remaining"] == 5   # o DTE segue calculado; só o STATUS mudou pelo marcador manual
