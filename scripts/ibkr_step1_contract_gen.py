"""
===============================================================================
 IBKR STEP 1 — Contract Universe Generator
 Prop Desk Quant | Backfill Pipeline (SPX / RUT / NDX)
===============================================================================
 Gera o universo completo de contratos (expiration × strike × side) para o
 período de backfill. NÃO faz nenhuma chamada ao IBKR.

 Lógica:
   1. Baixa preços históricos via yfinance (cached em data/)
   2. Gera todas as datas de expiração (weeklies + mensais)
   3. Para cada expiração, gera strikes ATM ± 35% no step correto
   4. Salva universo em data/ibkr_contract_universe.parquet

 Configuração:
   BACKFILL_START / BACKFILL_END  — período alvo
   STRIKE_PCT                     — range em % do ATM (0.35 = ±35%)
   STRIKE_STEPS                   — granularidade por underlying

 Uso:
   python scripts/ibkr_step1_contract_gen.py
   python scripts/ibkr_step1_contract_gen.py --start 2023-01-01 --end 2024-04-01
===============================================================================
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURAÇÃO
# ─────────────────────────────────────────────────────────────────────────────

ROOT       = Path(__file__).parent.parent
DATA_DIR   = ROOT / "data"
OUTPUT     = DATA_DIR / "ibkr_contract_universe.parquet"

# Período default de backfill (1 ano faltante para completar 2 anos)
DEFAULT_START = date(2024, 4, 1)
DEFAULT_END   = date(2025, 4, 4)   # dia anterior ao início dos dados existentes

# Strike range: ATM × (1 ± STRIKE_PCT), alinhado ao step
STRIKE_PCT = 0.35

STRIKE_STEPS: dict[str, int] = {
    "SPX":  5,    # SPX e SPXW usam mesmo step
    "RUT":  5,
    "NDX":  25,
}

# Tickers yfinance para cada underlying
YFINANCE_TICKERS: dict[str, str] = {
    "SPX": "^GSPC",
    "RUT": "^RUT",
    "NDX": "^NDX",
}

# Metadados por símbolo IBKR
SYMBOL_META: dict[str, dict] = {
    "SPX":  {"exchange": "SMART", "multiplier": "100", "currency": "USD", "underlying": "SPX"},
    "SPXW": {"exchange": "SMART", "multiplier": "100", "currency": "USD", "underlying": "SPX"},
    "RUT":  {"exchange": "SMART", "multiplier": "100", "currency": "USD", "underlying": "RUT"},
    "NDX":  {"exchange": "SMART", "multiplier": "100", "currency": "USD", "underlying": "NDX"},
}

# ─────────────────────────────────────────────────────────────────────────────
# SPOT CACHE
# ─────────────────────────────────────────────────────────────────────────────

def fetch_spot_history(underlying: str, start: date, end: date) -> pd.Series:
    """
    Baixa preços de fechamento via yfinance e salva cache CSV.
    Retorna pd.Series indexado por date, valores = close price.
    """
    cache_path = DATA_DIR / f"{underlying}_spot_cache.csv"

    # Tenta carregar cache existente
    if cache_path.exists():
        cached = pd.read_csv(cache_path, index_col=0, parse_dates=True)
        cached.index = pd.to_datetime(cached.index).date
        # Verifica se cobre o período necessário
        if cached.index.min() <= start and cached.index.max() >= end:
            print(f"  [{underlying}] Spot cache OK ({cache_path.name})")
            return cached["Close"]

    ticker = YFINANCE_TICKERS[underlying]
    print(f"  [{underlying}] Baixando preços de {ticker} ({start} → {end})...")

    # Buffer extra de 90 dias para cobrir lookback de expirations
    fetch_start = start - timedelta(days=90)
    fetch_end   = end   + timedelta(days=10)

    df = yf.download(
        ticker,
        start=fetch_start.isoformat(),
        end=fetch_end.isoformat(),
        auto_adjust=True,
        progress=False,
    )

    if df.empty:
        sys.exit(f"[ERRO] yfinance retornou vazio para {ticker}")

    series = df["Close"].copy()
    series.index = pd.to_datetime(series.index).date

    # Remove MultiIndex se yfinance retornar com ticker como nível extra
    if isinstance(series.index, pd.MultiIndex):
        series = series.droplevel(1)

    # Salva cache
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    series.to_frame("Close").to_csv(cache_path)
    print(f"  [{underlying}] Cache salvo: {cache_path.name} ({len(series)} dias)")
    return series


def get_spot_for_date(spot_history: pd.Series, target: date, lookback: int = 10) -> float | None:
    """
    Retorna o spot price do dia mais próximo a target (até lookback dias para trás).
    Usado para estimar ATM de expirations que podem cair em fim de semana/feriado.
    """
    for delta in range(lookback + 1):
        d = target - timedelta(days=delta)
        if d in spot_history.index:
            return float(spot_history[d])
    return None


# ─────────────────────────────────────────────────────────────────────────────
# GERAÇÃO DE EXPIRATIONS
# ─────────────────────────────────────────────────────────────────────────────

def _is_third_friday(d: date) -> bool:
    """True se d é a 3ª sexta-feira do mês (SPX AM settlement mensal)."""
    return d.weekday() == 4 and 15 <= d.day <= 21


def generate_spx_expirations(start: date, end: date) -> list[tuple[str, date]]:
    """
    Gera todas as expirations de SPX/SPXW no período.

    Regras CBOE:
      - SPXW: expira toda Seg, Qua, Sex (PM settlement, European cash)
      - SPX:  expira na 3ª sexta do mês (AM settlement, European cash)
      - A 3ª sexta é AMBOS: gera entrada SPXW + entrada SPX separadas
        (são contratos distintos no IBKR com conIds diferentes)
    """
    result: list[tuple[str, date]] = []
    current = start

    while current <= end:
        wd = current.weekday()

        # Seg (0), Qua (2), Sex (4) → SPXW weekly
        if wd in (0, 2, 4):
            result.append(("SPXW", current))
            # 3ª sexta → também SPX mensal (AM settlement)
            if wd == 4 and _is_third_friday(current):
                result.append(("SPX", current))

        current += timedelta(days=1)

    return result


def generate_friday_expirations(underlying: str, start: date, end: date) -> list[tuple[str, date]]:
    """
    Gera todas as sextas-feiras no período para RUT e NDX (weeklies padrão).
    """
    result: list[tuple[str, date]] = []
    current = start

    # Avança até a primeira sexta
    while current.weekday() != 4:
        current += timedelta(days=1)

    while current <= end:
        result.append((underlying, current))
        current += timedelta(days=7)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# GERAÇÃO DE STRIKES
# ─────────────────────────────────────────────────────────────────────────────

def generate_strikes(
    symbol: str,
    expiration: date,
    spot_history: pd.Series,
    pct: float = STRIKE_PCT,
) -> list[int]:
    """
    Gera lista de strikes candidatos: ATM × (1 ± pct), alinhados ao step.

    Usa o spot do dia mais próximo à expiration como proxy de ATM.
    Strikes retornados como int (SPX não usa frações).
    """
    underlying = SYMBOL_META[symbol]["underlying"]
    step = STRIKE_STEPS[underlying]

    spot = get_spot_for_date(spot_history, expiration)
    if spot is None:
        # Fallback: usa ±30% com ATM estimado de ±60 dias
        spot = get_spot_for_date(spot_history, expiration, lookback=60)
    if spot is None:
        return []

    low  = spot * (1 - pct)
    high = spot * (1 + pct)

    # Alinha ao grid do step
    low_aligned  = int(np.ceil(low  / step) * step)
    high_aligned = int(np.floor(high / step) * step)

    strikes = list(range(low_aligned, high_aligned + step, step))
    return strikes


# ─────────────────────────────────────────────────────────────────────────────
# BUILD UNIVERSE
# ─────────────────────────────────────────────────────────────────────────────

def build_contract_universe(
    all_expirations: list[tuple[str, date]],
    spot_histories: dict[str, pd.Series],
    pct: float = STRIKE_PCT,
) -> pd.DataFrame:
    """
    Monta DataFrame com uma linha por (symbol, expiration, strike, side).
    """
    rows: list[dict] = []
    skipped = 0

    for i, (symbol, exp) in enumerate(all_expirations):
        if i % 100 == 0:
            print(f"  Processando expiration {i+1}/{len(all_expirations)}: {symbol} {exp}")

        underlying = SYMBOL_META[symbol]["underlying"]
        meta       = SYMBOL_META[symbol]
        strikes    = generate_strikes(symbol, exp, spot_histories[underlying], pct)

        if not strikes:
            skipped += 1
            continue

        for strike in strikes:
            for side in ("call", "put"):
                rows.append({
                    "underlying":  underlying,
                    "symbol":      symbol,
                    "expiration":  exp,
                    "strike":      strike,
                    "side":        side,
                    "exchange":    meta["exchange"],
                    "multiplier":  meta["multiplier"],
                    "currency":    meta["currency"],
                })

    if skipped:
        print(f"  [AVISO] {skipped} expirations sem spot histórico — ignoradas")

    df = pd.DataFrame(rows)
    df["expiration"] = pd.to_datetime(df["expiration"])
    df["strike"]     = df["strike"].astype("int64")
    df["side"]       = df["side"].astype("category")
    return df


# ─────────────────────────────────────────────────────────────────────────────
# RELATÓRIO
# ─────────────────────────────────────────────────────────────────────────────

def print_report(df: pd.DataFrame, start: date, end: date) -> None:
    w = 62
    border = "─" * w

    print(f"\n+{border}+")
    print(f"|{'IBKR STEP 1 — CONTRACT UNIVERSE':^{w}}|")
    print(f"+{border}+")
    print(f"|  Período      : {start!s:<{w-17}}|")
    print(f"|  Período fim  : {end!s:<{w-17}}|")
    print(f"|  Total linhas : {len(df):,}{' ' * (w - 17 - len(f'{len(df):,}'))}|")
    print(f"+{border}+")

    for underlying in ["SPX", "RUT", "NDX"]:
        sub = df[df["underlying"] == underlying]
        exps = sub["expiration"].nunique()
        rows = len(sub)
        print(f"|  {underlying:<6}  expirations: {exps:<5}  contratos: {rows:>8,}  |")

    # Distribuição por símbolo
    print(f"+{border}+")
    for sym, grp in df.groupby("symbol", observed=True):
        print(f"|  {sym:<6}  {len(grp):>8,} contratos{' ' * (w - 28)}|")

    print(f"+{border}+")
    print(f"|  Output: {OUTPUT!s:<{w-10}}|")
    print(f"+{border}+\n")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Gera universo de contratos IBKR para backfill")
    p.add_argument("--start", type=date.fromisoformat, default=DEFAULT_START,
                   help=f"Data de início (default: {DEFAULT_START})")
    p.add_argument("--end",   type=date.fromisoformat, default=DEFAULT_END,
                   help=f"Data de fim (default: {DEFAULT_END})")
    p.add_argument("--pct",   type=float, default=STRIKE_PCT,
                   help=f"Range de strikes em %% do ATM (default: {STRIKE_PCT})")
    p.add_argument("--force", action="store_true",
                   help="Regenera mesmo se output já existir")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    print("\n" + "=" * 64)
    print("  IBKR STEP 1 — Contract Universe Generator")
    print(f"  Período: {args.start} → {args.end}  |  Strike range: ±{args.pct*100:.0f}%")
    print("=" * 64 + "\n")

    if OUTPUT.exists() and not args.force:
        existing = pd.read_parquet(OUTPUT)
        print(f"[OK] Universe já existe: {OUTPUT.name} ({len(existing):,} contratos)")
        print("     Use --force para regenerar.\n")
        print_report(existing, args.start, args.end)
        return

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # ── 1. Baixar spots ──────────────────────────────────────────────────────
    print("[1/3] Baixando histórico de preços...")
    spot_histories: dict[str, pd.Series] = {}
    for underlying in ["SPX", "RUT", "NDX"]:
        spot_histories[underlying] = fetch_spot_history(underlying, args.start, args.end)

    # ── 2. Gerar expirations ─────────────────────────────────────────────────
    print("\n[2/3] Gerando expirations...")
    all_exps: list[tuple[str, date]] = []

    spx_exps = generate_spx_expirations(args.start, args.end)
    rut_exps = generate_friday_expirations("RUT", args.start, args.end)
    ndx_exps = generate_friday_expirations("NDX", args.start, args.end)

    all_exps.extend(spx_exps)
    all_exps.extend(rut_exps)
    all_exps.extend(ndx_exps)

    spxw_count = sum(1 for s, _ in spx_exps if s == "SPXW")
    spx_count  = sum(1 for s, _ in spx_exps if s == "SPX")
    print(f"  SPX mensais (AM):  {spx_count}")
    print(f"  SPXW weeklies:     {spxw_count}")
    print(f"  RUT weeklies:      {len(rut_exps)}")
    print(f"  NDX weeklies:      {len(ndx_exps)}")
    print(f"  Total expirations: {len(all_exps)}")

    # ── 3. Build universe ────────────────────────────────────────────────────
    print("\n[3/3] Gerando strikes e montando universo...")
    df = build_contract_universe(all_exps, spot_histories, pct=args.pct)

    if df.empty:
        sys.exit("[ERRO] Universo vazio — verifique datas e dados de spot.")

    # Salva
    df.to_parquet(OUTPUT, index=False, compression="zstd", engine="pyarrow")

    print_report(df, args.start, args.end)
    print(f"[OK] Universo salvo em: {OUTPUT}\n")


if __name__ == "__main__":
    main()
