"""
===============================================================================
 THETADATA STEP 2 — Daily Chain Assembler
 Prop Desk Quant | ThetaData Standard Pipeline
===============================================================================
 Lê parquets brutos por expiration (gerados pelo Step 1),
 agrupa por trade_date e monta arquivos diários de chain com schema
 IDÊNTICO aos parquets existentes do MarketData.app.

 Schema de saída (compatível com ss42_backtest.py e ic7_backtest.py):
   side             category  ("call" / "put")
   strike           int64     (ex: 5000)
   dte              int64     (expiration - trade_date).days
   dte_actual       int16     (igual ao dte)
   bid              float32
   mid              float32   ((bid + ask) / 2)
   ask              float32
   open_interest    int32
   underlying_price float32   (de yfinance cache)
   trade_date       datetime64[ns, UTC]
   expiration       datetime64[ns, UTC]
   volume           int32

 Compressão: zstd
 Nomeação:   {UNDERLYING}_chain_{YYYY-MM-DD}.parquet

 Uso:
   python scripts/thetadata_step2_assemble.py
   python scripts/thetadata_step2_assemble.py --underlying SPX
   python scripts/thetadata_step2_assemble.py --output-dir data/thetadata_assembled
   python scripts/thetadata_step2_assemble.py --upload        # rclone sync ao final
   python scripts/thetadata_step2_assemble.py --validate      # verifica schema
===============================================================================
"""

from __future__ import annotations

import argparse
import gc
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURAÇÃO
# ─────────────────────────────────────────────────────────────────────────────

ROOT_DIR    = Path(__file__).parent.parent
RAW_DIR     = ROOT_DIR / "data" / "thetadata_raw"
DEFAULT_OUT = ROOT_DIR / "data" / "thetadata_assembled"

GDRIVE_REMOTE = "gdrive:Quant_Data_MD"
RCLONE_CONF   = ROOT_DIR / "infra" / "rclone.conf"

# Mapeamento underlying → root ThetaData (mesmo do Step 1)
ROOTS = {
    "SPX": "SPXW",
    "RUT": "RUT",
    "NDX": "NDX",
}

# Colunas finais na ordem exata dos parquets existentes
FINAL_COLS = [
    "side", "strike", "dte", "dte_actual", "bid", "mid", "ask",
    "open_interest", "underlying_price", "trade_date", "expiration", "volume",
]

MAX_DTE = 55   # alinhado com parquets existentes MarketData

# Tickers yfinance por underlying
_YF_TICKERS = {"SPX": "^GSPC", "RUT": "^RUT", "NDX": "^NDX"}


# ─────────────────────────────────────────────────────────────────────────────
# PARSING THETADATA → FORMATO INTERNO
# ─────────────────────────────────────────────────────────────────────────────

def parse_thetadata_raw(df: pd.DataFrame) -> pd.DataFrame:
    """
    Converte DataFrame bruto ThetaData para formato interno comum.

    Transformações principais:
      - strike:      ThetaData usa milésimos (5000000 = strike 5000) → divide por 1000
      - right:       'C' → 'call', 'P' → 'put'
      - date:        int YYYYMMDD → datetime UTC (trade_date)
      - _expiration: str YYYYMMDD → datetime UTC (expiration)
    """
    df = df.copy()

    # trade_date: coluna 'date' é int YYYYMMDD no ThetaData
    df["trade_date"] = pd.to_datetime(
        df["date"].astype(str).str.zfill(8), format="%Y%m%d", utc=True
    )

    # expiration: coluna '_expiration' adicionada pelo Step 1
    df["expiration"] = pd.to_datetime(
        df["_expiration"].astype(str).str.zfill(8), format="%Y%m%d", utc=True
    )

    # strike: milésimos → unidade inteira
    df["strike"] = (df["strike"].astype("float64") / 1000.0).round(0).astype("int64")

    # side
    df["side"] = df["right"].map({"C": "call", "P": "put"})

    # Remove linhas sem side reconhecido (dados corrompidos)
    df = df[df["side"].notna()].copy()

    # Bid / ask
    df["bid"] = df["bid"].astype("float32")
    df["ask"] = df["ask"].astype("float32")

    # Volume (opcional — pode não estar presente em alguns endpoints)
    if "volume" in df.columns:
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype("int32")
    else:
        df["volume"] = np.int32(0)

    # Open interest
    if "open_interest" in df.columns:
        df["open_interest"] = pd.to_numeric(df["open_interest"], errors="coerce").fillna(0).astype("int32")
    else:
        df["open_interest"] = np.int32(0)

    return df[[
        "trade_date", "expiration", "strike", "side",
        "bid", "ask", "volume", "open_interest",
    ]]


# ─────────────────────────────────────────────────────────────────────────────
# SPOT CACHE (yfinance)
# ─────────────────────────────────────────────────────────────────────────────

def load_spot_cache(underlying: str) -> dict:
    """
    Carrega (ou cria via yfinance) cache de preços de fechamento do underlying.
    Cobre 2016–2026 para acomodar 8 anos de dados ThetaData.
    Retorna dict {date: float}.
    """
    cache_path = ROOT_DIR / "data" / f"{underlying}_spot_cache.csv"

    if not cache_path.exists():
        try:
            import yfinance as yf

            ticker = _YF_TICKERS[underlying]
            print(f"  [{underlying}] Baixando spot cache via yfinance ({ticker})...")
            df = yf.download(
                ticker,
                start="2016-01-01",
                end="2026-01-01",
                auto_adjust=True,
                progress=False,
            )
            if df.empty:
                sys.exit(f"[ERRO] yfinance não retornou dados para {ticker}")

            (ROOT_DIR / "data").mkdir(parents=True, exist_ok=True)
            df[["Close"]].to_csv(cache_path)
            print(f"  [{underlying}] Spot cache salvo: {cache_path}")
        except ImportError:
            sys.exit(
                "[ERRO] yfinance não instalado. Execute: pip install yfinance"
            )
        except Exception as e:
            sys.exit(f"[ERRO] Não foi possível criar spot cache para {underlying}: {e}")

    df = pd.read_csv(cache_path, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index).date
    # yfinance pode retornar MultiIndex de colunas — achata se necessário
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df["Close"].to_dict()


def get_spot(cache: dict, trade_date, lookback: int = 5) -> float | None:
    """Retorna spot do dia ou do último dia útil anterior (até lookback dias)."""
    d = pd.Timestamp(trade_date).date()
    for i in range(lookback + 1):
        candidate = d - pd.Timedelta(days=i)
        if candidate in cache:
            return float(cache[candidate])
    return None


# ─────────────────────────────────────────────────────────────────────────────
# MONTAGEM DE ARQUIVO DIÁRIO
# ─────────────────────────────────────────────────────────────────────────────

def apply_final_schema(df: pd.DataFrame, spot: float) -> pd.DataFrame:
    """
    Aplica tipos e colunas calculadas para corresponder ao schema dos
    parquets existentes do MarketData.app.
    """
    df = df.copy()

    df["trade_date"] = pd.to_datetime(df["trade_date"], utc=True)
    df["expiration"] = pd.to_datetime(df["expiration"], utc=True)

    df["dte"] = (
        df["expiration"].dt.normalize() - df["trade_date"].dt.normalize()
    ).dt.days.astype("int64")

    df["dte_actual"]       = df["dte"].astype("int16")
    df["mid"]              = ((df["bid"] + df["ask"]) / 2.0).astype("float32")
    df["open_interest"]    = df["open_interest"].astype("int32")
    df["underlying_price"] = np.float32(spot)

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
    Retorna True se arquivo foi salvo, False caso contrário.
    """
    spot = get_spot(spot_cache, trade_date)
    if spot is None:
        print(f"    [AVISO] Sem spot para {underlying} em {trade_date} — pulando")
        return False

    df = df_day.copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"], utc=True)
    df["expiration"] = pd.to_datetime(df["expiration"], utc=True)

    # Filtra DTE: mantém 0 < DTE <= MAX_DTE
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

    # Ordena por (expiration, side, strike) — mesmo padrão dos parquets existentes
    df = df.sort_values(["expiration", "side", "strike"]).reset_index(drop=True)

    # Escrita atômica: .tmp → .parquet
    date_str = pd.Timestamp(trade_date).strftime("%Y-%m-%d")
    out_path = output_dir / f"{underlying}_chain_{date_str}.parquet"
    tmp_path = out_path.with_suffix(".tmp")

    df.to_parquet(tmp_path, index=False, compression="zstd", engine="pyarrow")
    tmp_path.replace(out_path)
    return True


# ─────────────────────────────────────────────────────────────────────────────
# CARREGAMENTO DE RAW THETADATA
# ─────────────────────────────────────────────────────────────────────────────

def load_raw_for_underlying(underlying: str) -> pd.DataFrame:
    """
    Lê todos os parquets brutos de data/thetadata_raw/{ROOT}/.
    Cada arquivo = 1 expiration × todos os dias que estava ativo.
    Aplica parse_thetadata_raw e retorna DataFrame concatenado.
    """
    root    = ROOTS[underlying]
    raw_dir = RAW_DIR / root

    if not raw_dir.exists():
        print(f"  [{underlying}] Diretório raw não encontrado: {raw_dir}")
        print(f"  Execute primeiro: python scripts/thetadata_step1_download.py --root {underlying}")
        return pd.DataFrame()

    # Apenas arquivos com nome YYYYMMDD.parquet (exclui completed.json, .tmp, etc.)
    files = sorted(f for f in raw_dir.glob("*.parquet") if f.stem.isdigit())
    if not files:
        print(f"  [{underlying}] Nenhum parquet raw encontrado em {raw_dir}")
        return pd.DataFrame()

    print(f"  [{underlying}] Carregando {len(files):,} parquets raw ({root})...")

    chunks = []
    for i, f in enumerate(files):
        try:
            df     = pd.read_parquet(f)
            parsed = parse_thetadata_raw(df)
            if not parsed.empty:
                chunks.append(parsed)
        except Exception as e:
            print(f"    [AVISO] Erro ao processar {f.name}: {e} — pulando")

        if (i + 1) % 200 == 0:
            print(f"    [{underlying}] {i+1:,}/{len(files):,} parquets lidos...")

    if not chunks:
        return pd.DataFrame()

    result = pd.concat(chunks, ignore_index=True)
    print(f"  [{underlying}] {len(result):,} linhas carregadas")
    return result


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

    df_raw["trade_date"] = pd.to_datetime(df_raw["trade_date"], utc=True)
    df_raw["_date_key"]  = df_raw["trade_date"].dt.date

    trade_dates = sorted(df_raw["_date_key"].unique())
    print(f"[{underlying}] {len(trade_dates)} dias únicos a montar...")

    files_written = 0
    for i, td in enumerate(trade_dates):
        date_str = td.strftime("%Y-%m-%d")
        out_path = output_dir / f"{underlying}_chain_{date_str}.parquet"

        if out_path.exists() and not force:
            files_written += 1
            continue

        df_day = df_raw[df_raw["_date_key"] == td].drop(columns=["_date_key"])
        ok     = assemble_day(df_day, td, underlying, spot_cache, output_dir)
        if ok:
            files_written += 1

        if (i + 1) % 100 == 0:
            print(f"  [{underlying}] {i+1}/{len(trade_dates)} dias | {files_written} arquivos escritos")

    del df_raw
    gc.collect()

    print(f"[{underlying}] Concluído: {files_written} parquets → {output_dir}")
    return files_written


# ─────────────────────────────────────────────────────────────────────────────
# RCLONE UPLOAD
# ─────────────────────────────────────────────────────────────────────────────

def upload_to_gdrive(assembled_dir: Path) -> None:
    if not RCLONE_CONF.exists():
        print(f"\n[AVISO] rclone.conf não encontrado: {RCLONE_CONF}")
        print("         Copie infra/rclone.conf e re-execute com --upload")
        return

    cmd = [
        "rclone", "copy",
        str(assembled_dir),
        GDRIVE_REMOTE,
        "--config", str(RCLONE_CONF),
        "--progress",
        "--transfers", "4",
    ]
    print(f"\n[UPLOAD] {assembled_dir} → {GDRIVE_REMOTE}")
    result = subprocess.run(cmd)
    if result.returncode == 0:
        print("[OK] Upload para Google Drive concluído.")
    else:
        print(f"[AVISO] rclone terminou com código {result.returncode}. Verifique o output acima.")


# ─────────────────────────────────────────────────────────────────────────────
# SCHEMA VALIDATION
# ─────────────────────────────────────────────────────────────────────────────

def validate_sample(output_dir: Path) -> None:
    """
    Verifica schema e sanidade de um parquet de amostra.
    Se Google Drive estiver montado, compara dtypes com MarketData existente.
    """
    sample = next(output_dir.glob("SPX_chain_*.parquet"), None)
    if sample is None:
        print("[VALIDAÇÃO] Nenhum parquet SPX encontrado para validar.")
        return

    print(f"\n[VALIDAÇÃO] Verificando: {sample.name}")
    df = pd.read_parquet(sample)

    # Colunas
    missing = set(FINAL_COLS) - set(df.columns)
    if missing:
        print(f"  [FALHA] Colunas faltando: {missing}")
    else:
        print("  [OK] Todas as colunas presentes")

    # Dtypes
    expected = {
        "side": "category", "strike": "int64", "dte": "int64",
        "dte_actual": "int16", "bid": "float32", "mid": "float32",
        "ask": "float32", "open_interest": "int32", "underlying_price": "float32",
        "volume": "int32",
    }
    for col, exp_dtype in expected.items():
        if col in df.columns:
            actual = str(df[col].dtype)
            status = "OK  " if exp_dtype in actual else "DIFF"
            print(f"  [{status}] {col:<22} esperado={exp_dtype:<12} atual={actual}")

    # Sanidade dos valores
    print(f"\n  Linhas:  {len(df):,}")
    print(f"  Strikes: {df['strike'].min()} – {df['strike'].max()}")
    print(f"  DTE:     {df['dte'].min()} – {df['dte'].max()}")
    print(f"  Bid:     {df['bid'].min():.2f} – {df['bid'].max():.2f}")
    print(f"  Ask:     {df['ask'].min():.2f} – {df['ask'].max():.2f}")
    print(f"  Spot:    {df['underlying_price'].iloc[0]:.1f}")

    # Comparação com parquet MarketData (se disponível no GDrive)
    gdrive = Path("G:/Meu Drive/Quant_Data_MD")
    if gdrive.exists():
        md_files = list(gdrive.glob("SPX_chain_2025-04-*.parquet"))
        if md_files:
            df_md = pd.read_parquet(md_files[0])
            print(f"\n  Comparação dtype vs MarketData ({md_files[0].name}):")
            for col in FINAL_COLS:
                if col in df.columns and col in df_md.columns:
                    t1    = str(df[col].dtype)
                    t2    = str(df_md[col].dtype)
                    match = "✓" if t1 == t2 else "✗"
                    print(f"    {match} {col:<22} ThetaData={t1:<25} MD={t2}")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="ThetaData Step 2 — Daily Chain Assembler"
    )
    p.add_argument(
        "--underlying", choices=list(ROOTS.keys()),
        help="Processa apenas 1 underlying (default: todos: SPX, RUT, NDX)",
    )
    p.add_argument(
        "--output-dir", type=Path, default=DEFAULT_OUT,
        help=f"Diretório de saída (default: {DEFAULT_OUT})",
    )
    p.add_argument(
        "--force", action="store_true",
        help="Re-monta mesmo que o parquet diário já exista",
    )
    p.add_argument(
        "--upload", action="store_true",
        help="Faz rclone sync para Google Drive ao final",
    )
    p.add_argument(
        "--validate", action="store_true",
        help="Valida schema de um arquivo de amostra após assembly",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    w = 64
    print("\n" + "=" * w)
    print("  THETADATA STEP 2 — Daily Chain Assembler")
    print(f"  Output: {args.output_dir}")
    print("=" * w)

    if not RAW_DIR.exists():
        sys.exit(
            f"[ERRO] Diretório raw não encontrado: {RAW_DIR}\n"
            f"       Execute primeiro: python scripts/thetadata_step1_download.py"
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)

    underlyings = [args.underlying] if args.underlying else list(ROOTS.keys())
    total_files = 0

    for und in underlyings:
        total_files += process_underlying(und, args.output_dir, force=args.force)

    # ── Sumário ──────────────────────────────────────────────────────────────
    border = "─" * w
    print(f"\n+{border}+")
    print(f"|{'THETADATA STEP 2 — CONCLUÍDO':^{w}}|")
    print(f"+{border}+")
    print(f"|  Total parquets escritos : {total_files:>6}{' ' * (w - 33)}|")
    print(f"|  Output dir : {args.output_dir!s:<{w - 15}}|")
    print(f"+{border}+\n")

    # ── Validação ────────────────────────────────────────────────────────────
    if args.validate:
        validate_sample(args.output_dir)

    # ── Upload ───────────────────────────────────────────────────────────────
    if args.upload:
        upload_to_gdrive(args.output_dir)
    else:
        print("  Para fazer upload ao Google Drive:")
        print("  python scripts/thetadata_step2_assemble.py --upload\n")


if __name__ == "__main__":
    main()
