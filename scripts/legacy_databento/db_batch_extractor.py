"""
===============================================================================
 DB BATCH EXTRACTOR — Databento OPRA Institutional Data Pipeline
 Prop Desk Quant | Senior Data Engineer
===============================================================================
 Submete um Batch Job ao Databento para extrair dados CBBO-1m de opcoes
 NDX/NDXP do dataset OPRA (2021-01 ate hoje).

 NOTA: A API do Databento NAO suporta filtro intraday recorrente
 (limit_time_of_day). O roadmap lista como "Considering" sem ETA.
 Estrategia: baixar dia completo -> filtrar localmente pos-download.
===============================================================================
"""

import os
import sys
from datetime import date, datetime

from dotenv import load_dotenv
import databento as db


# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACAO
# ─────────────────────────────────────────────────────────────────────────────

ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
load_dotenv(ENV_PATH)

API_KEY = os.getenv("DATABENTO_API_KEY")
if not API_KEY:
    sys.exit("[ERRO FATAL] DATABENTO_API_KEY nao encontrada no .env")


# ─────────────────────────────────────────────────────────────────────────────
# PARAMETROS DO BATCH JOB
# ─────────────────────────────────────────────────────────────────────────────

DATASET = "OPRA.PILLAR"
SYMBOLS = ["NDX.OPT", "NDXP.OPT"]
SCHEMA = "cbbo-1m"
START = "2021-01-01T00:00:00"
END = date.today().isoformat() + "T00:00:00"
ENCODING = "csv"
STYPE_IN = "parent"
SPLIT_DURATION = "day"

# Janelas intraday para filtragem LOCAL pos-download (ET)
# A API nao suporta este filtro nativamente.
TIME_WINDOWS = ["09:50-10:10", "15:45-16:00"]


# ─────────────────────────────────────────────────────────────────────────────
# SUBMISSAO DO JOB
# ─────────────────────────────────────────────────────────────────────────────

def submit_batch_job():
    """Submete o batch job e retorna o dict de resposta."""
    client = db.Historical(API_KEY)

    job = client.batch.submit_job(
        dataset=DATASET,
        symbols=SYMBOLS,
        schema=SCHEMA,
        start=START,
        end=END,
        encoding=ENCODING,
        stype_in=STYPE_IN,
        split_duration=SPLIT_DURATION,
        pretty_px=True,
        pretty_ts=True,
        map_symbols=True,
    )

    return job


# ─────────────────────────────────────────────────────────────────────────────
# RELATORIO TERMINAL
# ─────────────────────────────────────────────────────────────────────────────

def print_report(job):
    """Imprime recibo da submissao no terminal."""
    w = 64
    border = "=" * w

    # Extrair campos — submit_job retorna dict
    if isinstance(job, dict):
        job_id = job.get("id", job.get("job_id", "N/A"))
        status = job.get("state", job.get("status", "N/A"))
        cost = job.get("cost_usd", job.get("cost", None))
        records = job.get("record_count", None)
        bill_ct = job.get("billable_size", None)
        dataset_r = job.get("dataset", DATASET)
        schema_r = job.get("schema", SCHEMA)
    else:
        job_id = getattr(job, "id", getattr(job, "job_id", "N/A"))
        status = getattr(job, "state", getattr(job, "status", "N/A"))
        cost = getattr(job, "cost_usd", getattr(job, "cost", None))
        records = getattr(job, "record_count", None)
        bill_ct = getattr(job, "billable_size", None)
        dataset_r = DATASET
        schema_r = SCHEMA

    cost_str = f"US$ {cost:.4f}" if cost is not None else "Pendente (calculado apos processamento)"
    records_str = f"{records:,}" if records is not None else "Pendente"
    bill_str = f"{bill_ct:,} bytes" if bill_ct is not None else "Pendente"

    print()
    print(f"+{border}+")
    print(f"|{'DB BATCH EXTRACTOR — PROP DESK QUANT':^{w}}|")
    print(f"|{'Databento OPRA Institutional Pipeline':^{w}}|")
    print(f"+{border}+")
    print(f"|  Timestamp:       {datetime.now().strftime('%Y-%m-%d %H:%M:%S'):<{w - 20}}|")
    print(f"+{border}+")
    print(f"|{'PARAMETROS DA REQUISICAO':^{w}}|")
    print(f"+{border}+")
    print(f"|  Dataset:         {dataset_r:<{w - 20}}|")
    print(f"|  Symbols:         {', '.join(SYMBOLS):<{w - 20}}|")
    print(f"|  Schema:          {schema_r:<{w - 20}}|")
    print(f"|  Periodo:         {START[:10]}  ->  {END[:10]:<{w - 43}}|")
    print(f"|  Encoding:        {ENCODING:<{w - 20}}|")
    print(f"|  Split:           {SPLIT_DURATION:<{w - 20}}|")
    print(f"|  SType In:        {STYPE_IN:<{w - 20}}|")
    print(f"+{border}+")
    print(f"|{'RECIBO DA SUBMISSAO':^{w}}|")
    print(f"+{border}+")
    print(f"|  Job ID:          {str(job_id):<{w - 20}}|")
    print(f"|  Status:          {str(status):<{w - 20}}|")
    print(f"|  Custo Estimado:  {cost_str:<{w - 20}}|")
    print(f"|  Records:         {records_str:<{w - 20}}|")
    print(f"|  Billable Size:   {bill_str:<{w - 20}}|")
    print(f"+{border}+")
    print(f"|{'FILTRO LOCAL POS-DOWNLOAD (nao suportado pela API)':^{w}}|")
    print(f"+{border}+")
    print(f"|  Janelas ET:      {' | '.join(TIME_WINDOWS):<{w - 20}}|")
    print(f"+{border}+")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# EXECUCAO PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("\n[...] Conectando ao Databento e submetendo Batch Job...\n")
    try:
        job = submit_batch_job()
        print_report(job)
    except Exception as e:
        print(f"\n[ERRO] Falha na submissao: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
