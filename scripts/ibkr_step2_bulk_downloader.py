"""
===============================================================================
 IBKR STEP 2 — Bulk Historical Options Downloader
 Prop Desk Quant | Backfill Pipeline (SPX / RUT / NDX)
===============================================================================
 Conecta ao IB Gateway via ib_insync (asyncio) e baixa 1 barra diária de
 BID_ASK para cada contrato do universo gerado pelo Step 1.

 Arquitetura:
   - asyncio.Semaphore(5) → max 5 requests simultâneos (respeita pacing IBKR)
   - Checkpoint JSON   → idempotente, pode ser interrompido e retomado
   - Raw output        → data/ibkr_raw/{UNDERLYING}/{exp}_{strike}_{side}.parquet
   - 1 linha por dia útil em que o contrato esteve ativo

 Pacing IBKR:
   - Max 60 historical requests / 10 segundos
   - Max 6 simultâneos por clientId
   - Semaphore(5) + asyncio mantém bem abaixo do limite

 Parsing BID_ASK (comportamento TWS documentado):
   - bar.close   = bid EOD (close do bid)
   - bar.average = ask EOD (TWS empacota ask no campo average)

 Uso:
   # Requer IB Gateway rodando (porta 4002 paper / 4001 live)
   python scripts/ibkr_step2_bulk_downloader.py
   python scripts/ibkr_step2_bulk_downloader.py --underlying SPX
   python scripts/ibkr_step2_bulk_downloader.py --resume      # pula contratos já baixados
===============================================================================
"""

from __future__ import annotations

import argparse
import asyncio
import gc
import json
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

# ib_insync importado aqui para facilitar mocks em teste
try:
    from ib_insync import IB, Option
    from ib_insync import util as ib_util
except ImportError:
    sys.exit(
        "[ERRO] ib_insync não instalado.\n"
        "       pip install ib_insync==0.9.86"
    )

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURAÇÃO
# ─────────────────────────────────────────────────────────────────────────────

ROOT       = Path(__file__).parent.parent
DATA_DIR   = ROOT / "data"
UNIVERSE   = DATA_DIR / "ibkr_contract_universe.parquet"
RAW_DIR    = DATA_DIR / "ibkr_raw"
CHECKPOINT = DATA_DIR / "ibkr_checkpoint.json"

load_dotenv(ROOT / ".env")

IBKR_HOST          = os.getenv("IBKR_HOST", "localhost")
IBKR_PORT          = int(os.getenv("IBKR_PORT", "4002"))
IBKR_CLIENT_ID     = int(os.getenv("IBKR_CLIENT_ID", "10"))
IBKR_TRADING_MODE  = os.getenv("IBKR_TRADING_MODE", "paper")

# Período do backfill (filtro aplicado às barras retornadas)
BACKFILL_START = date(2024, 4, 1)
BACKFILL_END   = date(2025, 4, 4)

MAX_PARALLEL        = 5      # Semaphore — max requests simultâneos
CHECKPOINT_INTERVAL = 500    # Salva checkpoint a cada N contratos completos
PROGRESS_INTERVAL   = 100    # Printa progresso a cada N contratos
CONNECT_RETRIES     = 10     # Tentativas de conexão ao gateway
CONNECT_WAIT_SEC    = 15     # Espera entre tentativas

# ─────────────────────────────────────────────────────────────────────────────
# CHECKPOINT
# ─────────────────────────────────────────────────────────────────────────────

def load_checkpoint() -> dict:
    """Carrega checkpoint existente ou retorna estrutura vazia."""
    if CHECKPOINT.exists():
        try:
            with open(CHECKPOINT) as f:
                data = json.load(f)
            data["completed"] = set(data.get("completed", []))
            data["no_data"]   = set(data.get("no_data", []))
            data["errors"]    = data.get("errors", {})
            return data
        except Exception:
            pass
    return {"completed": set(), "no_data": set(), "errors": {}}


def save_checkpoint(cp: dict) -> None:
    """Atomic write do checkpoint JSON."""
    tmp = CHECKPOINT.with_suffix(".tmp")
    payload = {
        "completed":       list(cp["completed"]),
        "no_data":         list(cp["no_data"]),
        "errors":          cp["errors"],
        "total_completed": len(cp["completed"]),
        "total_no_data":   len(cp["no_data"]),
        "last_saved":      pd.Timestamp.utcnow().isoformat(),
    }
    tmp.write_text(json.dumps(payload, indent=2))
    tmp.replace(CHECKPOINT)


def task_key(symbol: str, expiration, strike: int, side: str) -> str:
    exp_str = pd.Timestamp(expiration).strftime("%Y%m%d")
    return f"{symbol}/{exp_str}_{strike}_{side}"


def raw_path(underlying: str, symbol: str, expiration, strike: int, side: str) -> Path:
    exp_str = pd.Timestamp(expiration).strftime("%Y%m%d")
    return RAW_DIR / underlying / f"{symbol}_{exp_str}_{strike}_{side}.parquet"


# ─────────────────────────────────────────────────────────────────────────────
# IBKR CONNECTION
# ─────────────────────────────────────────────────────────────────────────────

async def connect_gateway(host: str, port: int, client_id: int) -> IB:
    """
    Conecta ao IB Gateway com retry. O docker-compose healthcheck garante
    que o gateway está pronto, mas a conexão pode falhar brevemente.
    """
    ib = IB()
    for attempt in range(1, CONNECT_RETRIES + 1):
        try:
            await ib.connectAsync(host, port, clientId=client_id, timeout=30)
            print(f"[OK] Conectado ao IB Gateway em {host}:{port} (clientId={client_id})")
            return ib
        except Exception as e:
            print(f"  [tentativa {attempt}/{CONNECT_RETRIES}] Falha: {e} — aguardando {CONNECT_WAIT_SEC}s...")
            await asyncio.sleep(CONNECT_WAIT_SEC)

    sys.exit(f"[ERRO FATAL] Não foi possível conectar ao IB Gateway após {CONNECT_RETRIES} tentativas.")


# ─────────────────────────────────────────────────────────────────────────────
# CONTRACT CREATION
# ─────────────────────────────────────────────────────────────────────────────

def make_option_contract(symbol: str, expiration, strike: int, side: str) -> Option:
    """
    Cria contrato ib_insync Option.

    Usa exchange='SMART' (roteamento automático IBKR → CBOE) para evitar
    erros 200 em alguns SPXW weeklies que falham com exchange='CBOE' direto.
    """
    right   = "C" if side == "call" else "P"
    exp_str = pd.Timestamp(expiration).strftime("%Y%m%d")
    return Option(
        symbol=symbol,
        lastTradeDateOrContractMonth=exp_str,
        strike=float(strike),
        right=right,
        exchange="SMART",
        multiplier="100",
        currency="USD",
    )


# ─────────────────────────────────────────────────────────────────────────────
# BAR PARSING
# ─────────────────────────────────────────────────────────────────────────────

def bars_to_dataframe(
    bars,
    underlying: str,
    expiration,
    strike: int,
    side: str,
) -> pd.DataFrame | None:
    """
    Converte BarDataList de BID_ASK para DataFrame.

    Comportamento TWS para whatToShow='BID_ASK':
      bar.close   → EOD bid (close do bid bar)
      bar.average → EOD ask (TWS empacota ask no campo average)
    """
    records = []
    exp_ts  = pd.Timestamp(expiration, tz="UTC")

    start_ts = pd.Timestamp(BACKFILL_START, tz="UTC")
    end_ts   = pd.Timestamp(BACKFILL_END + timedelta(days=1), tz="UTC")

    for bar in bars:
        try:
            # formatDate=1 → bar.date é string 'YYYYMMDD'
            trade_date = pd.Timestamp(str(bar.date), tz="UTC")
        except Exception:
            continue

        # Filtra ao período de backfill
        if trade_date < start_ts or trade_date >= end_ts:
            continue

        bid_eod = float(bar.close)
        ask_eod = float(bar.average)

        # Descarta barras com cotação inválida
        if bid_eod <= 0 or ask_eod <= 0 or ask_eod < bid_eod:
            continue

        records.append({
            "trade_date": trade_date,
            "expiration": exp_ts,
            "strike":     strike,
            "side":       side,
            "underlying": underlying,
            "bid":        np.float32(bid_eod),
            "ask":        np.float32(ask_eod),
            "volume":     max(0, int(bar.volume)) if bar.volume and bar.volume != -1 else 0,
        })

    if not records:
        return None

    df = pd.DataFrame(records)
    df["side"]       = df["side"].astype("category")
    df["underlying"] = df["underlying"].astype("category")
    return df


# ─────────────────────────────────────────────────────────────────────────────
# DOWNLOAD DE UM CONTRATO
# ─────────────────────────────────────────────────────────────────────────────

async def download_contract(
    ib: IB,
    semaphore: asyncio.Semaphore,
    row: pd.Series,
    cp: dict,
) -> str:
    """
    Baixa histórico de 1 contrato e salva raw parquet.
    Retorna o task_key ao terminar (usado para atualizar checkpoint).
    """
    symbol     = row["symbol"]
    underlying = row["underlying"]
    exp        = row["expiration"]
    strike     = int(row["strike"])
    side       = row["side"]

    key   = task_key(symbol, exp, strike, side)
    fpath = raw_path(underlying, symbol, exp, strike, side)

    # Idempotência: arquivo já existe → skip
    if fpath.exists():
        cp["completed"].add(key)
        return key

    contract = make_option_contract(symbol, exp, strike, side)

    # endDateTime: expiration + 2 dias (captura último dia de trading)
    exp_date = pd.Timestamp(exp).date()
    end_dt   = (exp_date + timedelta(days=2)).strftime("%Y%m%d") + " 23:59:59"

    async with semaphore:
        try:
            bars = await ib.reqHistoricalDataAsync(
                contract=contract,
                endDateTime=end_dt,
                durationStr="90 D",
                barSizeSetting="1 day",
                whatToShow="BID_ASK",
                useRTH=True,
                formatDate=1,
                keepUpToDate=False,
                timeout=30,
            )
        except TimeoutError:
            cp["errors"][key] = "timeout"
            return key
        except Exception as e:
            err_str = str(e)
            if "162" in err_str:
                # Pacing violation — aguarda e retenta
                await asyncio.sleep(70)
                try:
                    bars = await ib.reqHistoricalDataAsync(
                        contract=contract,
                        endDateTime=end_dt,
                        durationStr="90 D",
                        barSizeSetting="1 day",
                        whatToShow="BID_ASK",
                        useRTH=True,
                        formatDate=1,
                        keepUpToDate=False,
                        timeout=30,
                    )
                except Exception as e2:
                    cp["errors"][key] = f"pacing_retry_fail:{e2}"
                    return key
            elif "200" in err_str or "No security" in err_str:
                # Contrato não existe — normal para strikes muito OTM
                cp["no_data"].add(key)
                return key
            elif "354" in err_str:
                # Sem subscription de dados — fatal
                sys.exit(
                    "\n[ERRO FATAL] Erro 354: sem assinatura de dados OPRA.\n"
                    "  Verifique em Client Portal → Market Data → OPRA.\n"
                )
            else:
                cp["errors"][key] = err_str[:120]
                return key

    if not bars:
        cp["no_data"].add(key)
        return key

    df = bars_to_dataframe(bars, underlying, exp, strike, side)
    if df is None:
        cp["no_data"].add(key)
        return key

    # Salva raw parquet
    fpath.parent.mkdir(parents=True, exist_ok=True)
    tmp = fpath.with_suffix(".tmp")
    df.to_parquet(tmp, index=False, compression="zstd", engine="pyarrow")
    tmp.replace(fpath)

    cp["completed"].add(key)
    return key


# ─────────────────────────────────────────────────────────────────────────────
# RUNNER POR UNDERLYING
# ─────────────────────────────────────────────────────────────────────────────

async def run_underlying(
    ib: IB,
    df_underlying: pd.DataFrame,
    cp: dict,
    underlying: str,
) -> None:
    """
    Processa todos os contratos de um underlying com paralelismo controlado.
    """
    semaphore = asyncio.Semaphore(MAX_PARALLEL)
    total     = len(df_underlying)
    completed = 0
    t0        = time.monotonic()

    print(f"\n  [{underlying}] {total:,} contratos a processar...")

    # Filtra contratos já feitos
    pending_rows = [
        row for _, row in df_underlying.iterrows()
        if task_key(row["symbol"], row["expiration"], int(row["strike"]), row["side"])
           not in cp["completed"]
        and task_key(row["symbol"], row["expiration"], int(row["strike"]), row["side"])
           not in cp["no_data"]
        and not raw_path(row["underlying"], row["symbol"],
                         row["expiration"], int(row["strike"]), row["side"]).exists()
    ]

    skipped = total - len(pending_rows)
    if skipped:
        print(f"  [{underlying}] {skipped:,} já baixados — pulando")

    # Processa em batches para limitar tarefas simultâneas no event loop
    BATCH = 1000
    for batch_start in range(0, len(pending_rows), BATCH):
        batch = pending_rows[batch_start : batch_start + BATCH]
        tasks = [
            asyncio.create_task(download_contract(ib, semaphore, row, cp))
            for row in batch
        ]

        for future in asyncio.as_completed(tasks):
            await future
            completed += 1

            if completed % PROGRESS_INTERVAL == 0:
                elapsed  = time.monotonic() - t0
                rate     = completed / elapsed if elapsed > 0 else 0
                remaining = len(pending_rows) - completed
                eta_sec   = remaining / rate if rate > 0 else 0
                eta_h     = eta_sec / 3600
                print(
                    f"  [{underlying}] {completed:>6,}/{len(pending_rows):,} "
                    f"| {rate:.1f} req/s | ETA: {eta_h:.1f}h"
                )

            if completed % CHECKPOINT_INTERVAL == 0:
                save_checkpoint(cp)
                print(f"  [{underlying}] Checkpoint salvo ({len(cp['completed']):,} completos)")

    # Checkpoint final deste underlying
    save_checkpoint(cp)
    elapsed = time.monotonic() - t0
    print(
        f"\n  [{underlying}] Concluído: {len(cp['completed']):,} completos | "
        f"{len(cp['no_data']):,} sem dados | {len(cp['errors']):,} erros | "
        f"{elapsed/3600:.1f}h"
    )


# ─────────────────────────────────────────────────────────────────────────────
# RELATÓRIO FINAL
# ─────────────────────────────────────────────────────────────────────────────

def print_final_report(cp: dict, t_total: float) -> None:
    w = 62
    border = "─" * w
    n_completed = len(cp["completed"])
    n_no_data   = len(cp["no_data"])
    n_errors    = len(cp["errors"])
    n_total     = n_completed + n_no_data + n_errors

    print(f"\n+{border}+")
    print(f"|{'IBKR STEP 2 — DOWNLOAD COMPLETO':^{w}}|")
    print(f"+{border}+")
    print(f"|  Contratos OK       : {n_completed:>10,}  ({n_completed/max(n_total,1)*100:.1f}%)  |")
    print(f"|  Sem dados (normal) : {n_no_data:>10,}  ({n_no_data/max(n_total,1)*100:.1f}%)  |")
    print(f"|  Erros              : {n_errors:>10,}  ({n_errors/max(n_total,1)*100:.1f}%)  |")
    print(f"|  Total processado   : {n_total:>10,}{' ' * (w - 27)}|")
    print(f"|  Tempo total        : {t_total/3600:>7.1f}h{' ' * (w - 22)}|")
    print(f"+{border}+")

    if n_errors > 0:
        print("\n  Primeiros 5 erros:")
        for k, v in list(cp["errors"].items())[:5]:
            print(f"    {k}: {v}")

    print(f"\n  Raw output: {RAW_DIR}")
    print("  Próximo passo: python scripts/ibkr_step3_daily_assembler.py\n")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Download bulk histórico IBKR para backfill")
    p.add_argument("--underlying", choices=["SPX", "RUT", "NDX"],
                   help="Processa apenas 1 underlying (default: todos)")
    p.add_argument("--resume", action="store_true",
                   help="Retoma de onde parou (usa checkpoint existente)")
    p.add_argument("--host",  default=IBKR_HOST, help="IB Gateway host")
    p.add_argument("--port",  type=int, default=IBKR_PORT, help="IB Gateway port")
    return p.parse_args()


async def async_main(args: argparse.Namespace) -> None:
    print("\n" + "=" * 64)
    print("  IBKR STEP 2 — Bulk Historical Options Downloader")
    print(f"  Gateway: {args.host}:{args.port}  |  Modo: {IBKR_TRADING_MODE}")
    print(f"  Período: {BACKFILL_START} → {BACKFILL_END}")
    print("=" * 64 + "\n")

    if not UNIVERSE.exists():
        sys.exit(
            f"[ERRO] Universe não encontrado: {UNIVERSE}\n"
            f"       Execute primeiro: python scripts/ibkr_step1_contract_gen.py"
        )

    # Carrega universo
    df_all = pd.read_parquet(UNIVERSE)
    print(f"[INFO] Universo carregado: {len(df_all):,} contratos")

    if args.underlying:
        df_all = df_all[df_all["underlying"] == args.underlying].reset_index(drop=True)
        print(f"[INFO] Filtrado para {args.underlying}: {len(df_all):,} contratos")

    # Checkpoint
    cp = load_checkpoint()
    if cp["completed"] or cp["no_data"]:
        print(
            f"[INFO] Checkpoint: {len(cp['completed']):,} completos, "
            f"{len(cp['no_data']):,} sem dados, {len(cp['errors']):,} erros"
        )
    else:
        print("[INFO] Sem checkpoint — iniciando do zero")

    # Conecta ao IB Gateway
    ib = await connect_gateway(args.host, args.port, IBKR_CLIENT_ID)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()

    underlyings = [args.underlying] if args.underlying else ["SPX", "RUT", "NDX"]

    for und in underlyings:
        df_und = df_all[df_all["underlying"] == und].reset_index(drop=True)
        if df_und.empty:
            continue
        await run_underlying(ib, df_und, cp, und)
        gc.collect()

    ib.disconnect()
    t_total = time.monotonic() - t0
    print_final_report(cp, t_total)


def main() -> None:
    args = parse_args()
    # ib_insync requer que o event loop esteja rodando — startLoop() configura isso
    ib_util.startLoop()
    try:
        asyncio.run(async_main(args))
    except KeyboardInterrupt:
        print("\n[INTERROMPIDO] Checkpoint salvo — use --resume para continuar.")


if __name__ == "__main__":
    main()
