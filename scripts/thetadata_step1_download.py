"""
===============================================================================
 THETADATA STEP 1 — Bulk EOD Options Downloader
 Prop Desk Quant | ThetaData Standard Pipeline
===============================================================================
 Downloads all historical EOD options chain data from ThetaData Standard API.
 One parquet per expiration: data/thetadata_raw/{ROOT}/{YYYYMMDD}.parquet

 Prerequisites:
   pip install requests pandas pyarrow python-dotenv
   THETADATA_API_KEY=... in .env

 Usage:
   python scripts/thetadata_step1_download.py
   python scripts/thetadata_step1_download.py --root SPX
   python scripts/thetadata_step1_download.py --start 20240101 --end 20250101
   python scripts/thetadata_step1_download.py --force   # re-download all
===============================================================================
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURAÇÃO
# ─────────────────────────────────────────────────────────────────────────────

ROOT_DIR = Path(__file__).parent.parent

DOWNLOAD_START = "20170101"   # 8 anos de histórico
DOWNLOAD_END   = "20250404"   # dia anterior aos dados MarketData existentes

# Mapeamento underlying → root ThetaData
# SPX usa 'SPXW' para capturar todos os contratos weekly e mensais
ROOTS = {
    "SPX": "SPXW",
    "RUT": "RUT",
    "NDX": "NDX",
}

RAW_DIR     = ROOT_DIR / "data" / "thetadata_raw"
BASE_URL    = "https://api.thetadata.us"
MAX_WORKERS = 4
RETRY_MAX   = 3


# ─────────────────────────────────────────────────────────────────────────────
# API
# ─────────────────────────────────────────────────────────────────────────────

def get_api_key() -> str:
    load_dotenv(ROOT_DIR / ".env")
    key = os.getenv("THETADATA_API_KEY", "").strip()
    if not key:
        sys.exit(
            "[ERRO] THETADATA_API_KEY não encontrado no .env\n"
            "       Adicione: THETADATA_API_KEY=sua_chave_aqui"
        )
    return key


def _api_get(
    session: requests.Session,
    endpoint: str,
    params: dict,
    api_key: str,
    retry: int = 0,
) -> dict | None:
    """GET com retry exponencial em caso de rate limit ou erro de rede."""
    url     = f"{BASE_URL}{endpoint}"
    headers = {"X-ThetaAPI-Key": api_key}
    try:
        resp = session.get(url, params=params, headers=headers, timeout=90)

        if resp.status_code == 204:
            return None  # sem dados para este request

        if resp.status_code == 429:
            if retry < RETRY_MAX:
                wait = (2 ** retry) * 10
                print(f"    [429] Rate limit — aguardando {wait}s...")
                time.sleep(wait)
                return _api_get(session, endpoint, params, api_key, retry + 1)
            return None

        resp.raise_for_status()
        return resp.json()

    except requests.RequestException as e:
        if retry < RETRY_MAX:
            time.sleep(2 ** retry * 2)
            return _api_get(session, endpoint, params, api_key, retry + 1)
        print(f"    [ERRO] {endpoint} {params}: {e}")
        return None


def list_expirations(root: str, api_key: str, start: str, end: str) -> list[str]:
    """
    Retorna lista de expirations disponíveis para um root no período [start, end].
    Formato de entrada/saída: YYYYMMDD.
    """
    with requests.Session() as session:
        data = _api_get(session, "/v2/list/expirations", {"root": root}, api_key)

    if not data:
        return []

    rows     = data.get("response", [])
    start_dt = datetime.strptime(start, "%Y%m%d")
    end_dt   = datetime.strptime(end,   "%Y%m%d")

    expirations: list[str] = []
    for row in rows:
        raw = row[0] if isinstance(row, list) else row
        exp_str = str(int(raw))
        try:
            exp_dt = datetime.strptime(exp_str, "%Y%m%d")
            if start_dt <= exp_dt <= end_dt:
                expirations.append(exp_str)
        except ValueError:
            continue

    return sorted(expirations)


def download_expiration(
    root: str, exp: str, start: str, end: str, api_key: str
) -> pd.DataFrame | None:
    """
    Baixa toda a chain EOD de uma expiration específica via bulk_hist/option/eod.
    Uma chamada → todos os strikes × todos os dias ativos no período.
    Retorna DataFrame bruto (colunas ThetaData + '_expiration') ou None.
    """
    params = {
        "root":       root,
        "exp":        exp,
        "start_date": start,
        "end_date":   end,
    }
    with requests.Session() as session:
        data = _api_get(session, "/v2/bulk_hist/option/eod", params, api_key)

    if not data:
        return None

    fmt  = data.get("header", {}).get("format", [])
    rows = data.get("response", [])

    if not fmt or not rows:
        return None

    df = pd.DataFrame(rows, columns=fmt)
    df["_expiration"] = exp   # metadado: expiration desta chain
    return df


# ─────────────────────────────────────────────────────────────────────────────
# ARMAZENAMENTO
# ─────────────────────────────────────────────────────────────────────────────

def save_raw(df: pd.DataFrame, root: str, exp: str) -> Path:
    """Salva parquet bruto em data/thetadata_raw/{ROOT}/{EXP}.parquet (escrita atômica)."""
    out_dir = RAW_DIR / root
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{exp}.parquet"
    tmp = out_dir / f"{exp}.tmp"
    df.to_parquet(tmp, index=False, compression="zstd", engine="pyarrow")
    tmp.replace(out)
    return out


def load_checkpoint(root: str) -> set[str]:
    """Carrega lista de expirations já baixadas para um root."""
    cp = RAW_DIR / root / "completed.json"
    if cp.exists():
        with open(cp) as f:
            return set(json.load(f))
    return set()


def save_checkpoint(root: str, completed: set[str]) -> None:
    """Persiste checkpoint de expirations concluídas."""
    cp = RAW_DIR / root / "completed.json"
    cp.parent.mkdir(parents=True, exist_ok=True)
    with open(cp, "w") as f:
        json.dump(sorted(completed), f, indent=2)


# ─────────────────────────────────────────────────────────────────────────────
# WORKER
# ─────────────────────────────────────────────────────────────────────────────

def _worker(root: str, exp: str, start: str, end: str, api_key: str) -> tuple[str, int]:
    """
    Thread worker: baixa + salva 1 expiration.
    Sleep de cortesia para respeitar rate limits da API.
    Retorna (exp, n_rows). n_rows = 0 se sem dados.
    """
    time.sleep(0.1)  # ~40 req/s com 4 workers — seguro para ThetaData Standard
    df = download_expiration(root, exp, start, end, api_key)
    if df is not None and not df.empty:
        save_raw(df, root, exp)
        return exp, len(df)
    return exp, 0


# ─────────────────────────────────────────────────────────────────────────────
# RUNNER POR ROOT
# ─────────────────────────────────────────────────────────────────────────────

def run_root(
    root: str,
    underlying: str,
    api_key: str,
    start: str,
    end: str,
    force: bool = False,
    exp_end: str | None = None,
) -> None:
    """
    Download completo de um root. Idempotente via checkpoint:
    re-execuções saltam expirations já baixadas.
    exp_end: limite superior para listar expirations (default: end).
    """
    _exp_end = exp_end or end
    print(f"\n[{underlying} -> {root}] Listando expirations {start}-{_exp_end}...")
    expirations = list_expirations(root, api_key, start, _exp_end)
    print(f"  {len(expirations)} expirations encontradas")

    completed = load_checkpoint(root) if not force else set()
    pending   = [e for e in expirations if e not in completed]

    if not pending:
        print(f"  Já concluído (checkpoint). Use --force para re-baixar.")
        return

    skipped = len(expirations) - len(pending)
    if skipped:
        print(f"  {len(pending)} a baixar | {skipped} já existentes (checkpoint)")

    rows_total = 0
    done       = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {
            pool.submit(_worker, root, exp, start, end, api_key): exp
            for exp in pending
        }

        for fut in as_completed(futures):
            exp, nrows = fut.result()
            rows_total += nrows
            completed.add(exp)
            done += 1

            if done % 50 == 0:
                save_checkpoint(root, completed)
                pct = done / len(pending) * 100
                print(
                    f"  [{underlying}] {done}/{len(pending)} ({pct:.0f}%) "
                    f"| {rows_total:,} linhas acumuladas"
                )

    save_checkpoint(root, completed)
    print(
        f"[{underlying}] Concluído: {rows_total:,} linhas | "
        f"{len(pending)} expirations -> {RAW_DIR / root}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="ThetaData Step 1 — Bulk EOD Options Downloader"
    )
    p.add_argument(
        "--root", choices=list(ROOTS.keys()),
        help="Baixar apenas 1 underlying (default: todos: SPX, RUT, NDX)",
    )
    p.add_argument(
        "--start", default=DOWNLOAD_START, metavar="YYYYMMDD",
        help=f"Data início (default: {DOWNLOAD_START})",
    )
    p.add_argument(
        "--end", default=DOWNLOAD_END, metavar="YYYYMMDD",
        help=f"Data fim dos dados de trading (default: {DOWNLOAD_END})",
    )
    p.add_argument(
        "--exp-end", default=None, metavar="YYYYMMDD",
        help="Limite superior para listar expirations (default: igual a --end). "
             "Útil quando expirations relevantes expiram após o fim dos dados necessários.",
    )
    p.add_argument(
        "--force", action="store_true",
        help="Re-baixar mesmo que expiration já esteja no checkpoint",
    )
    return p.parse_args()


def main() -> None:
    args    = parse_args()
    api_key = get_api_key()
    exp_end = args.exp_end or args.end

    w = 64
    print("\n" + "=" * w)
    print("  THETADATA STEP 1 — Bulk EOD Options Downloader")
    print(f"  Dados    : {args.start} -> {args.end}")
    if exp_end != args.end:
        print(f"  Exp-end  : {exp_end}  (expirations listadas até esta data)")
    print(f"  Destino  : {RAW_DIR}")
    print(f"  Workers  : {MAX_WORKERS}")
    print("=" * w)

    pairs = {args.root: ROOTS[args.root]} if args.root else ROOTS

    for underlying, root in pairs.items():
        run_root(root, underlying, api_key, args.start, args.end, args.force, exp_end)

    print(f"\n{'=' * w}")
    print("  Download ThetaData concluído.")
    print("  Próximo: python scripts/thetadata_step2_assemble.py")
    print(f"{'=' * w}\n")


if __name__ == "__main__":
    main()
