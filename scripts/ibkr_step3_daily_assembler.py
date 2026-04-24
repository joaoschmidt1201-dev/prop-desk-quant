"""
===============================================================================
 IBKR STEP 3 — Daily Chain Assembler
 Prop Desk Quant | Backfill Pipeline (SPX / RUT / NDX)
===============================================================================
 Lê todos os parquets brutos gerados pelo Step 2 (1 arquivo por contrato),
 agrupa por (underlying, trade_date) e monta os arquivos diários de chain
 com schema IDÊNTICO aos parquets existentes do MarketData.app.

 Schema de saída (compatível com ss42_backtest.py e ic7_backtest.py):
   side             category  ("call" / "put")
   strike           int64     (ex: 5000)
   dte              int64     (expiration - trade_date).days
   dte_actual       int16     (igual ao dte)
   bid              float32
   mid              float32   ((bid + ask) / 2)
   ask              float32
   open_interest    int32     (0 — IBKR histórico não confiável)
   underlying_price float32   (de yfinance cache)
   trade_date       datetime64[ns, UTC]
   expiration       datetime64[ns, UTC]
   volume           int32

 Compressão: zstd
 Nomeação:   {UNDERLYING}_chain_{YYYY-MM-DD}.parquet

 Uso:
   python scripts/ibkr_step3_daily_assembler.py
   python scripts/ibkr_step3_daily_assembler.py --underlying SPX
   python scripts/ibkr_step3_daily_assembler.py --output-dir data/ibkr_assembled
   python scripts/ibkr_step3_daily_assembler.py --upload        # rclone sync ao final
===============================================================================
"""

from __future__ import annotations

import argparse
import gc
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURAÇÃO
# ─────────────────────────────────────────────────────────────────────────────

ROOT         = Path(__file__).parent.parent
DATA_DIR     = ROOT / "data"
RAW_DIR      = DATA_DIR / "ibkr_raw"
DEFAULT_OUT  = DATA_DIR / "ibkr_assembled"

# Destino Google Drive (para rclone)
GDRIVE_REMOTE = "gdrive:Quant_Data_MD"
RCLONE_CONF   = ROOT / "infra" / "rclone.conf"

# Colunas finais na ordem exata dos parquets existentes
FINAL_COLS = [
    "side", "strike", "dte", "dte_actual", "bid", "mid", "ask",
    "open_interest", "underlying_price", "trade_date", "expiration", "volume",
]

# DTE máximo a incluir (alinhado com Step 2 md_step3: MAX_DTE = 55)
MAX_DTE = 55


# ─────────────────────────────────────────────────────────────────────────────
# SPOT CACHE
# ─────────────────────────────────────────────────────────────────────────────

def load_spot_cache(underlying: str) -> dict:
    """
    Carrega cache de preços do underlying gerado pelo Step 1.
    Retorna dict {date: float}.
    """
    cache_path = DATA_DIR / f"{underlying}_spot_cache.csv"
    if not cache_path.exists():
        # Tenta fallback com tickers yfinance
        try:
            import yfinance as yf
            TICKERS = {"SPX": "^GSPC", "RUT": "^RUT", "NDX": "^NDX"}
            ticker  = TICKERS[underlying]
            df = yf.download(ticker, start="2024-01-01", end="2025-06-01",
                             auto_adjust=True, progress=False)
            series = df["Close"]
            series.index = pd.to_datetime(series.index).date
            series.to_frame("Close").to_csv(cache_path)
            print(f"  [{underlying}] Spot cache criado via yfinance")
        except Exception as e:
            sys.exit(
                f"[ERRO] Spot cache não encontrado para {underlying}: {cache_path}\n"
                f"       Execute primeiro: python scripts/ibkr_step1_contract_gen.py\n"
                f"       Detalhe: {e}"
            )

    df = pd.read_csv(cache_path, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index).date
    return df["Close"].to_dict()


def get_spot(cache: dict, trade_date, lookback: int = 5) -> float | None:
    """Retorna spot do dia ou do último dia útil anterior (até lookback dias)."""
    from datetime import timedelta
    d = pd.Timestamp(trade_date).date()
    for i in range(lookback + 1):
        candidate = d - pd.Timedelta(days=i)
        if candidate in cache:
            return float(cache[candidate])
    return None


# ─────────────────────────────────────────────────────────────────────────────
# CARREGAMENTO DE RAW PARQUETS
# ─────────────────────────────────────────────────────────────────────────────

def load_raw_for_underlying(underlying: str) -> pd.DataFrame:
    """
    Lê todos os parquets brutos de data/ibkr_raw/{underlying}/.
    Retorna DataFrame concatenado.
    """
    raw_und = RAW_DIR / underlying
    if not raw_und.exists():
        print(f"  [{underlying}] Diretório raw não encontrado: {raw_und}")
        return pd.DataFrame()

    files = sorted(raw_und.glob("*.parquet"))
    if not files:
        print(f"  [{underlying}] Nenhum parquet raw encontrado em {raw_und}")
        return pd.DataFrame()

    print(f"  [{underlying}] Carregando {len(files):,} parquets raw...")

    chunks = []
    for i, f in enumerate(files):
        try:
            chunks.append(pd.read_parquet(f))
        except Exception as e:
            print(f"    [AVISO] Erro ao ler {f.name}: {e} — pulando")

        if (i + 1) % 5000 == 0:
            print(f"    Lidos {i+1:,}/{len(files):,}...")

    if not chunks:
        return pd.DataFrame()

    df = pd.concat(chunks, ignore_index=True)
    print(f"  [{underlying}] {len(df):,} linhas brutas carregadas")
    return df


# ─────────────────────────────────────────────────────────────────────────────
# MONTAGEM DE ARQUIVO DIÁRIO
# ─────────────────────────────────────────────────────────────────────────────

def apply_final_schema(df: pd.DataFrame, spot: float) -> pd.DataFrame:
    """
    Aplica tipos e colunas calculadas para corresponder ao schema dos
    parquets existentes do MarketData.app.
    """
    df = df.copy()

    # Garante que trade_date e expiration são Timestamps UTC
    df["trade_date"] = pd.to_datetime(df["trade_date"], utc=True)
    df["expiration"] = pd.to_datetime(df["expiration"], utc=True)

    # Métricas calculadas
    df["dte"] = (
        df["expiration"].dt.normalize() - df["trade_date"].dt.normalize()
    ).dt.days.astype("int64")

    df["dte_actual"]       = df["dte"].astype("int16")
    df["mid"]              = ((df["bid"] + df["ask"]) / 2.0).astype("float32")
    df["open_interest"]    = np.int32(0)
    df["underlying_price"] = np.float32(spot)

    # Tipos exatos
    df["side"]   = df["side"].astype("category")
    df["strike"] = df["strike"].astype("int64")
    df["bid"]    = df["bid"].astype("float32")
    df["ask"]    = df["ask"].astype("float32")
    df["volume"] = df["volume"].fillna(0).astype("int32")

    return df[FINAL_COLS]


def assemble_day(
    df_day: pd.DataFrame,
    trade_date,
    underlying: str,
    spot_cache: dict,
    output_dir: Path,
) -> bool:
    """
    Monta e salva o parquet diário para um (underlying, trade_date).
    Retorna True se arquivo salvo, False caso contrário.
    """
    spot = get_spot(spot_cache, trade_date)
    if spot is None:
        print(f"    [AVISO] Sem spot para {underlying} em {trade_date} — pulando")
        return False

    df = df_day.copy()

    # Remove expirations que já expiraram (dte <= 0) ou muito longe (dte > MAX_DTE)
    df["trade_date"] = pd.to_datetime(df["trade_date"], utc=True)
    df["expiration"] = pd.to_datetime(df["expiration"], utc=True)
    dte_raw = (
        df["expiration"].dt.normalize() - df["trade_date"].dt.normalize()
    ).dt.days
    df = df[(dte_raw > 0) & (dte_raw <= MAX_DTE)]

    if df.empty:
        return False

    # Remove duplicatas (keep last — dado mais recente do mesmo contrato)
    df = df.drop_duplicates(subset=["expiration", "strike", "side"], keep="last")

    # Aplica schema
    df = apply_final_schema(df, spot)

    # Sort por (expiration, side, strike) — mesmo padrão dos existentes
    df = df.sort_values(["expiration", "side", "strike"]).reset_index(drop=True)

    # Nome do arquivo
    date_str  = pd.Timestamp(trade_date).strftime("%Y-%m-%d")
    out_path  = output_dir / f"{underlying}_chain_{date_str}.parquet"
    tmp_path  = out_path.with_suffix(".tmp")

    df.to_parquet(tmp_path, index=False, compression="zstd", engine="pyarrow")
    tmp_path.replace(out_path)
    return True


# ─────────────────────────────────────────────────────────────────────────────
# RUNNER POR UNDERLYING
# ─────────────────────────────────────────────────────────────────────────────

def process_underlying(underlying: str, output_dir: Path, force: bool = False) -> int:
    """
    Processa todos os dias de 1 underlying.
    Retorna número de arquivos escritos.
    """
    print(f"\n[{underlying}] Carregando raw parquets...")
    df_raw = load_raw_for_underlying(underlying)
    if df_raw.empty:
        print(f"[{underlying}] Nada a processar.")
        return 0

    spot_cache = load_spot_cache(underlying)

    # Normaliza trade_date para date (para groupby)
    df_raw["trade_date"] = pd.to_datetime(df_raw["trade_date"], utc=True)
    df_raw["_date_key"]  = df_raw["trade_date"].dt.date

    trade_dates = sorted(df_raw["_date_key"].unique())
    print(f"[{underlying}] {len(trade_dates)} dias únicos a montar...")

    files_written = 0
    for i, td in enumerate(trade_dates):
        date_str  = td.strftime("%Y-%m-%d")
        out_path  = output_dir / f"{underlying}_chain_{date_str}.parquet"

        if out_path.exists() and not force:
            files_written += 1
            continue

        df_day = df_raw[df_raw["_date_key"] == td].drop(columns=["_date_key"])
        ok     = assemble_day(df_day, td, underlying, spot_cache, output_dir)
        if ok:
            files_written += 1

        if (i + 1) % 50 == 0:
            print(f"  [{underlying}] {i+1}/{len(trade_dates)} dias | {files_written} arquivos")

    del df_raw
    gc.collect()

    print(f"[{underlying}] Concluído: {files_written} parquets escritos → {output_dir}")
    return files_written


# ─────────────────────────────────────────────────────────────────────────────
# RCLONE UPLOAD
# ─────────────────────────────────────────────────────────────────────────────

def upload_to_gdrive(assembled_dir: Path) -> None:
    """
    Sincroniza assembled_dir para Google Drive via rclone.
    """
    if not RCLONE_CONF.exists():
        print(f"\n[AVISO] rclone.conf não encontrado: {RCLONE_CONF}")
        print("         Copie infra/rclone.conf manualmente e re-execute com --upload")
        return

    cmd = [
        "rclone", "copy",
        str(assembled_dir),
        GDRIVE_REMOTE,
        "--config", str(RCLONE_CONF),
        "--progress",
        "--transfers", "4",
    ]

    print(f"\n[UPLOAD] Sincronizando para Google Drive...")
    print(f"  Origem:  {assembled_dir}")
    print(f"  Destino: {GDRIVE_REMOTE}\n")

    result = subprocess.run(cmd)
    if result.returncode == 0:
        print("\n[OK] Sync para Google Drive concluído.")
    else:
        print(f"\n[AVISO] rclone terminou com código {result.returncode}. Verifique o output acima.")


# ─────────────────────────────────────────────────────────────────────────────
# SCHEMA VALIDATION
# ─────────────────────────────────────────────────────────────────────────────

def validate_sample(output_dir: Path, gdrive_dir: Path | None = None) -> None:
    """
    Compara um parquet IBKR assembado com um parquet MarketData existente.
    Verifica dtypes e sanidade dos valores.
    """
    sample_ibkr = next(output_dir.glob("SPX_chain_*.parquet"), None)
    if sample_ibkr is None:
        print("[VALIDAÇÃO] Nenhum parquet IBKR encontrado para validar.")
        return

    print(f"\n[VALIDAÇÃO] Verificando schema: {sample_ibkr.name}")
    df_ibkr = pd.read_parquet(sample_ibkr)

    # Verifica colunas
    missing = set(FINAL_COLS) - set(df_ibkr.columns)
    if missing:
        print(f"  [FALHA] Colunas faltando: {missing}")
    else:
        print("  [OK] Todas as colunas presentes")

    # Verifica dtypes
    expected_dtypes = {
        "side": "category", "strike": "int64", "dte": "int64",
        "dte_actual": "int16", "bid": "float32", "mid": "float32",
        "ask": "float32", "open_interest": "int32", "underlying_price": "float32",
        "volume": "int32",
    }
    for col, expected in expected_dtypes.items():
        if col in df_ibkr.columns:
            actual = str(df_ibkr[col].dtype)
            status = "OK" if expected in actual else f"DIFERENTE ({actual})"
            print(f"  [{status}] {col}: esperado={expected}, atual={actual}")

    # Sanidade dos valores
    print(f"\n  Linhas: {len(df_ibkr):,}")
    print(f"  Strikes: {df_ibkr['strike'].min()} – {df_ibkr['strike'].max()}")
    print(f"  DTE: {df_ibkr['dte'].min()} – {df_ibkr['dte'].max()}")
    print(f"  Bid: {df_ibkr['bid'].min():.2f} – {df_ibkr['bid'].max():.2f}")
    print(f"  Ask: {df_ibkr['ask'].min():.2f} – {df_ibkr['ask'].max():.2f}")
    print(f"  Spot: {df_ibkr['underlying_price'].iloc[0]:.1f}")

    # Compara com parquet MarketData se disponível
    if gdrive_dir and gdrive_dir.exists():
        md_candidates = list(gdrive_dir.glob("SPX_chain_2025-04-*.parquet"))
        if md_candidates:
            df_md = pd.read_parquet(md_candidates[0])
            print(f"\n  Comparação de dtypes com MarketData ({md_candidates[0].name}):")
            for col in FINAL_COLS:
                if col in df_ibkr.columns and col in df_md.columns:
                    t_ibkr = str(df_ibkr[col].dtype)
                    t_md   = str(df_md[col].dtype)
                    match  = "✓" if t_ibkr == t_md else "✗ DIFERENTE"
                    print(f"    {match}  {col:<22} IBKR={t_ibkr:<25} MD={t_md}")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Monta parquets diários a partir dos raw IBKR")
    p.add_argument("--underlying", choices=["SPX", "RUT", "NDX"],
                   help="Processa apenas 1 underlying (default: todos)")
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUT,
                   help=f"Diretório de saída (default: {DEFAULT_OUT})")
    p.add_argument("--force", action="store_true",
                   help="Re-escreve parquets existentes")
    p.add_argument("--upload", action="store_true",
                   help="Faz rclone sync para Google Drive ao final")
    p.add_argument("--validate", action="store_true",
                   help="Valida schema de um arquivo de amostra")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    print("\n" + "=" * 64)
    print("  IBKR STEP 3 — Daily Chain Assembler")
    print(f"  Output: {args.output_dir}")
    print("=" * 64 + "\n")

    if not RAW_DIR.exists():
        sys.exit(
            f"[ERRO] Diretório raw não encontrado: {RAW_DIR}\n"
            f"       Execute primeiro: python scripts/ibkr_step2_bulk_downloader.py"
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)

    underlyings = [args.underlying] if args.underlying else ["SPX", "RUT", "NDX"]
    total_files = 0

    for und in underlyings:
        total_files += process_underlying(und, args.output_dir, force=args.force)

    # ── Sumário ──────────────────────────────────────────────────────────────
    w = 62
    border = "─" * w
    print(f"\n+{border}+")
    print(f"|{'IBKR STEP 3 — CONCLUÍDO':^{w}}|")
    print(f"+{border}+")
    print(f"|  Total parquets escritos: {total_files:>6}{' ' * (w - 32)}|")
    print(f"|  Output dir: {str(args.output_dir):<{w - 14}}|")
    print(f"+{border}+\n")

    # ── Validação ────────────────────────────────────────────────────────────
    if args.validate:
        gdrive = Path("G:/Meu Drive/Quant_Data_MD")
        validate_sample(args.output_dir, gdrive_dir=gdrive if gdrive.exists() else None)

    # ── Upload ───────────────────────────────────────────────────────────────
    if args.upload:
        upload_to_gdrive(args.output_dir)
    else:
        print("  Para fazer upload ao Google Drive:")
        print(f"  python scripts/ibkr_step3_daily_assembler.py --upload\n")


if __name__ == "__main__":
    main()
