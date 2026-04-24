"""
===============================================================================
 DB STEP 2 — Definition Filter & Instrument ID Mapper
 Prop Desk Quant | Extração Cirúrgica OPRA (Etapa 2 de 3)
===============================================================================
 Le o CSV de definicoes baixado no Step 1 e filtra apenas os instrument_ids
 dos contratos relevantes para o Iron Condor 7DTE:
   - Expiry = proxima sexta-feira de cada semana do historico
   - Strike = dentro da faixa ±1 SD (calculado com o fechamento de quinta)
   - instrument_class = C (call) ou P (put)

 Reusa calc_annualized_hv() e calc_expected_move() do ic7_simulator.py.

 INPUT:  data/ndx_definitions_raw.csv
 OUTPUT: data/filtered_ids.csv

 PROXIMO PASSO: db_step3_cbbo_targeted.py
===============================================================================
"""

import bisect
import os
import sys
import warnings
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore", category=FutureWarning)

# Importar funcoes do motor quantitativo existente
sys.path.insert(0, os.path.dirname(__file__))
from ic7_simulator import calc_annualized_hv, calc_expected_move


# ─────────────────────────────────────────────────────────────────────────────
# CAMINHOS
# ─────────────────────────────────────────────────────────────────────────────

ROOT        = Path(__file__).parent.parent
DATA_DIR    = ROOT / "data"
DEF_CSV     = DATA_DIR / "ndx_definitions_raw.csv"
OUTPUT_CSV  = DATA_DIR / "filtered_ids.csv"


# ─────────────────────────────────────────────────────────────────────────────
# PARAMETROS
# ─────────────────────────────────────────────────────────────────────────────

TICKER            = "^NDX"
HV_WINDOW         = 30
TRADING_DAYS_YEAR = 252
DTE_CALENDAR_DAYS = 7
CALENDAR_DAYS_YEAR = 365
SD_MULTIPLIER     = 1.0
STRIKE_WINDOW     = 15     # strikes acima e abaixo de cada breakeven (upper/lower)
START_DATE        = date(2021, 1, 1)


# ─────────────────────────────────────────────────────────────────────────────
# UTILIDADES DE DATA
# ─────────────────────────────────────────────────────────────────────────────

def get_all_fridays(start: date, end: date) -> list[date]:
    """Retorna todas as sextas-feiras entre start e end."""
    fridays = []
    d = start
    while d <= end:
        if d.weekday() == 4:  # Friday = 4
            fridays.append(d)
        d += timedelta(days=1)
    return fridays


def get_thursday(friday: date) -> date:
    """Retorna a quinta-feira imediatamente anterior a uma sexta."""
    return friday - timedelta(days=1)


# ─────────────────────────────────────────────────────────────────────────────
# DADOS DE PRECO HISTORICO NDX
# ─────────────────────────────────────────────────────────────────────────────

NDX_CACHE = DATA_DIR / "ndx_closes_cache.csv"

def load_ndx_history() -> pd.Series:
    """
    Baixa historico completo do NDX desde 2020 (margem para HV window de 30d).
    Usa cache local (data/ndx_closes_cache.csv) para evitar rate limit do yfinance.
    Retorna Series com index=date, values=Close.
    """
    if NDX_CACHE.exists():
        print(f"[...] Carregando historico NDX do cache local ({NDX_CACHE.name}) ...")
        cached = pd.read_csv(NDX_CACHE, index_col=0, parse_dates=True)
        closes = cached.squeeze()
        closes.index = pd.to_datetime(closes.index).date
        print(f"[OK] {len(closes)} pregoes carregados do cache ({closes.index[0]} -> {closes.index[-1]})")
        return closes

    print("[...] Baixando historico NDX via yfinance (desde 2020-01-01)...")
    raw = yf.download(TICKER, start="2020-01-01", auto_adjust=True, progress=False)
    if raw.empty:
        sys.exit("[ERRO FATAL] yfinance nao retornou dados para ^NDX.")
    closes = raw["Close"].squeeze()
    closes.index = pd.to_datetime(closes.index).date
    closes.to_csv(NDX_CACHE, header=["Close"])
    print(f"[OK] {len(closes)} pregoes carregados e cache salvo em {NDX_CACHE.name}.")
    return closes


def get_thursday_close(closes: pd.Series, thursday: date) -> float | None:
    """
    Retorna o fechamento de uma data especifica.
    Se a data for feriado/fim-de-semana, usa o pregao anterior mais recente.
    """
    # Procurar o fechamento na data ou no pregao mais recente anterior
    available = [d for d in closes.index if d <= thursday]
    if not available:
        return None
    closest = max(available)
    return float(closes[closest])


# ─────────────────────────────────────────────────────────────────────────────
# CARREGAMENTO E PARSE DO CSV DE DEFINICOES
# ─────────────────────────────────────────────────────────────────────────────

def load_definitions() -> pd.DataFrame:
    """
    Carrega o CSV de definicoes do Databento em chunks para evitar OOM.
    Aplica filtros de asset (NDX/NDXP) e instrument_class (C/P) por chunk.
    Normaliza expiration e strike_price inline.
    """
    if not DEF_CSV.exists():
        sys.exit(
            f"[ERRO FATAL] Arquivo nao encontrado: {DEF_CSV}\n"
            f"Execute db_step1_definition.py e baixe o CSV para data/"
        )

    # Detectar nano-units via amostra pequena (evita carregar o DF completo)
    sample = pd.read_csv(DEF_CSV, nrows=1_000, low_memory=False)
    is_nano = pd.to_numeric(sample["strike_price"], errors="coerce").median() > 1e6
    if is_nano:
        print("[INFO] strike_price detectado em nano-units — sera convertido (* 1e-9) por chunk.")

    print(f"[...] Carregando definicoes: {DEF_CSV.name} (chunked, 100k linhas/chunk) ...")

    # Ler apenas as colunas necessarias — reduz ~90% da RAM por chunk (6 de 65 colunas)
    USECOLS = ["asset", "instrument_class", "expiration", "strike_price",
               "instrument_id", "raw_symbol"]

    chunks_filtered = []
    total_read = 0

    for chunk in pd.read_csv(DEF_CSV, usecols=USECOLS, low_memory=False, chunksize=100_000):
        total_read += len(chunk)

        # Filtro 1: apenas ativos NDX / NDXP
        if "asset" in chunk.columns:
            chunk = chunk[chunk["asset"].isin(["NDX", "NDXP"])]

        # Filtro 2: apenas calls e puts
        chunk = chunk[chunk["instrument_class"].isin(["C", "P", "CALL", "PUT"])]

        if chunk.empty:
            continue

        # Normalizar expiration
        chunk["expiration"] = pd.to_datetime(chunk["expiration"], errors="coerce").dt.date

        # Normalizar strike_price — cast incondicional para eliminar linhas com
        # texto (ex: headers duplicados embutidos no CSV)
        chunk["strike_price"] = pd.to_numeric(chunk["strike_price"], errors="coerce")
        if is_nano:
            chunk["strike_price"] = chunk["strike_price"] * 1e-9

        # Descartar linhas invalidas geradas por headers duplicados ou dados corrompidos
        chunk = chunk.dropna(subset=["strike_price", "expiration"])

        if chunk.empty:
            continue

        chunks_filtered.append(chunk)

    if not chunks_filtered:
        sys.exit("[ERRO FATAL] Nenhum registro NDX/NDXP encontrado no CSV de definicoes.")

    df = pd.concat(chunks_filtered, ignore_index=True)
    total_kept = len(df)
    print(f"[OK] {total_read:,} registros lidos. {total_kept:,} mantidos (NDX/NDXP + C/P).")

    return df


# ─────────────────────────────────────────────────────────────────────────────
# FILTRO CIRURGICO POR SEMANA
# ─────────────────────────────────────────────────────────────────────────────

def filter_week(
    defs: pd.DataFrame,
    friday: date,
    thursday_close: float,
    hv_annual: float,
) -> pd.DataFrame:
    """
    Para uma sexta-feira especifica:
    - Calcula upper_be (+1 SD) e lower_be (-1 SD) como mira aproximada
    - Calls: mantém STRIKE_WINDOW strikes abaixo e acima do upper_be
    - Puts:  mantém STRIKE_WINDOW strikes abaixo e acima do lower_be
    - Tudo fora dessa 'rede de pesca' é descartado
    """
    move = calc_expected_move(
        thursday_close, hv_annual, DTE_CALENDAR_DAYS, CALENDAR_DAYS_YEAR, SD_MULTIPLIER
    )
    upper_be = thursday_close + move
    lower_be = thursday_close - move

    # Contratos com expiry = sexta desta semana
    friday_df = defs[defs["expiration"] == friday]
    if friday_df.empty:
        return pd.DataFrame()

    # ── CALLS: janela de ±STRIKE_WINDOW strikes em torno do upper_be ──────────
    calls = friday_df[friday_df["instrument_class"].isin(["C", "CALL"])]
    call_strikes = sorted(calls["strike_price"].dropna().unique())
    idx_c = bisect.bisect_left(call_strikes, upper_be)
    lo_c  = max(0, idx_c - STRIKE_WINDOW)
    hi_c  = min(len(call_strikes), idx_c + STRIKE_WINDOW)
    valid_call_strikes = set(call_strikes[lo_c:hi_c])
    calls_filtered = calls[calls["strike_price"].isin(valid_call_strikes)]

    # ── PUTS: janela de ±STRIKE_WINDOW strikes em torno do lower_be ──────────
    puts = friday_df[friday_df["instrument_class"].isin(["P", "PUT"])]
    put_strikes = sorted(puts["strike_price"].dropna().unique())
    idx_p = bisect.bisect_left(put_strikes, lower_be)
    lo_p  = max(0, idx_p - STRIKE_WINDOW)
    hi_p  = min(len(put_strikes), idx_p + STRIKE_WINDOW)
    valid_put_strikes = set(put_strikes[lo_p:hi_p])
    puts_filtered = puts[puts["strike_price"].isin(valid_put_strikes)]

    subset = pd.concat([calls_filtered, puts_filtered], ignore_index=True)
    if not subset.empty:
        subset["friday_date"]    = friday
        subset["thursday_close"] = round(thursday_close, 2)
        subset["hv_annual_pct"]  = round(hv_annual * 100, 2)
        subset["sd_move_pts"]    = round(move, 2)
        subset["upper_be"]       = round(upper_be, 2)
        subset["lower_be"]       = round(lower_be, 2)

    return subset


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 66)
    print("  DB STEP 2 — Definition Filter & Instrument ID Mapper")
    print("  Prop Desk Quant | Etapa 2 de 3")
    print("=" * 66 + "\n")

    # 1. Carregar historico de precos primeiro (fail-fast em caso de rate limit)
    closes = load_ndx_history()

    # 2. Carregar definicoes (operacao lenta — leitura chunked de 47M linhas)
    defs = load_definitions()

    # 2. Calcular HV anualizada rolante (uma vez, sobre toda a serie)
    # Usaremos HV calculada a partir dos 30 pregoes ANTERIORES a cada quinta
    today = date.today()
    fridays = get_all_fridays(START_DATE, today)
    print(f"\n[INFO] Processando {len(fridays)} sextas-feiras ({fridays[0]} -> {fridays[-1]})")

    all_rows = []
    skipped = 0

    for friday in fridays:
        thursday = get_thursday(friday)

        # Fechamento de quinta
        spot = get_thursday_close(closes, thursday)
        if spot is None:
            skipped += 1
            continue

        # HV com os 30 pregoes anteriores a quinta
        avail_closes = closes[closes.index <= thursday]
        if len(avail_closes) < HV_WINDOW + 5:
            skipped += 1
            continue

        try:
            hv = calc_annualized_hv(avail_closes, HV_WINDOW, TRADING_DAYS_YEAR)
        except ValueError:
            skipped += 1
            continue

        # Filtrar contratos para essa sexta
        week_rows = filter_week(defs, friday, spot, hv)
        if not week_rows.empty:
            all_rows.append(week_rows)

    if not all_rows:
        sys.exit(
            "\n[ERRO] Nenhum contrato encontrado. Verifique se o CSV de definicoes "
            "cobre o periodo 2021-2026 e se os strikes/expiries estao corretos."
        )

    # 3. Consolidar e exportar
    result = pd.concat(all_rows, ignore_index=True)

    # Selecionar colunas finais relevantes
    keep_cols = [
        "friday_date", "instrument_id", "raw_symbol",
        "strike_price", "instrument_class", "expiration",
        "thursday_close", "hv_annual_pct", "sd_move_pts",
        "upper_be", "lower_be",
    ]
    keep_cols = [c for c in keep_cols if c in result.columns]
    result = result[keep_cols].drop_duplicates(subset=["friday_date", "instrument_id"])
    result = result.sort_values(["friday_date", "instrument_class", "strike_price"])

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUTPUT_CSV, index=False)

    # 4. Relatorio final
    n_fridays_found = result["friday_date"].nunique()
    n_ids = result["instrument_id"].nunique()
    n_calls = (result["instrument_class"].isin(["C", "CALL"])).sum()
    n_puts  = (result["instrument_class"].isin(["P", "PUT"])).sum()

    print(f"\n{'=' * 66}")
    print(f"  RELATORIO — DB STEP 2")
    print(f"{'=' * 66}")
    print(f"  Sextas processadas:     {len(fridays)}")
    print(f"  Sextas com dados:       {n_fridays_found}")
    print(f"  Sextas sem preco/HV:    {skipped}")
    print(f"  Instrument IDs unicos:  {n_ids:,}")
    print(f"  Calls selecionados:     {n_calls:,}")
    print(f"  Puts selecionados:      {n_puts:,}")
    print(f"  Output:                 {OUTPUT_CSV}")
    print(f"{'=' * 66}")
    print(f"\n  PROXIMO PASSO: python scripts/db_step3_cbbo_targeted.py\n")


if __name__ == "__main__":
    main()
