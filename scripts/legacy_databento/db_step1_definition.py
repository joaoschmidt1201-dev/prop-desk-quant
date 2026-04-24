"""
===============================================================================
 DB STEP 1 — Definition Schema Extractor
 Prop Desk Quant | Extração Cirúrgica OPRA (Etapa 1 de 3)
===============================================================================
 Submete um Batch Job BARATO ao Databento para baixar apenas o schema
 'definition' (metadata dos contratos) do NDX e NDXP.
 Custo estimado: ~$0.50–$2.00 (coberto pelo crédito gratuito de $125).

 Output: data/ndx_definitions_raw.csv (via download manual no portal
         Databento após o job processar)

 PROXIMO PASSO: db_step2_filter_ids.py
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
# PARAMETROS DO JOB
# ─────────────────────────────────────────────────────────────────────────────

DATASET        = "OPRA.PILLAR"
SYMBOLS        = ["NDX.OPT", "NDXP.OPT"]
SCHEMA         = "definition"
START          = "2021-01-01T00:00:00"
END            = date.today().isoformat() + "T00:00:00"
ENCODING       = "csv"
STYPE_IN       = "parent"
SPLIT_DURATION = "month"


# ─────────────────────────────────────────────────────────────────────────────
# PRE-CHECAGEM DE CUSTO
# ─────────────────────────────────────────────────────────────────────────────

def check_cost(client: db.Historical) -> float | None:
    """Consulta o custo estimado antes de submeter o job."""
    try:
        cost = client.metadata.get_cost(
            dataset=DATASET,
            symbols=SYMBOLS,
            schema=SCHEMA,
            start=START,
            end=END,
            stype_in=STYPE_IN,
        )
        return cost
    except Exception as e:
        print(f"[AVISO] metadata.get_cost() indisponivel: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# SUBMISSAO DO JOB
# ─────────────────────────────────────────────────────────────────────────────

def submit_job(client: db.Historical) -> dict:
    """Submete o batch job de definition e retorna o dict de resposta."""
    return client.batch.submit_job(
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


# ─────────────────────────────────────────────────────────────────────────────
# RELATORIO
# ─────────────────────────────────────────────────────────────────────────────

def print_report(job: dict, cost: float | None) -> None:
    w = 64
    border = "=" * w

    job_id  = job.get("id", "N/A")
    status  = job.get("state", "N/A")
    cost_str = f"US$ {cost:.4f}" if cost is not None else "Consulte o portal Databento"

    print()
    print(f"+{border}+")
    print(f"|{'DB STEP 1 — DEFINITION EXTRACTOR':^{w}}|")
    print(f"|{'Prop Desk Quant | Etapa 1 de 3':^{w}}|")
    print(f"+{border}+")
    print(f"|  Timestamp:       {datetime.now().strftime('%Y-%m-%d %H:%M:%S'):<{w-20}}|")
    print(f"+{border}+")
    print(f"|  Dataset:         {DATASET:<{w-20}}|")
    print(f"|  Symbols:         {', '.join(SYMBOLS):<{w-20}}|")
    print(f"|  Schema:          {SCHEMA:<{w-20}}|")
    print(f"|  Periodo:         {START[:10]}  ->  {END[:10]:<{w-43}}|")
    print(f"|  Encoding:        {ENCODING:<{w-20}}|")
    print(f"|  Split:           {SPLIT_DURATION:<{w-20}}|")
    print(f"+{border}+")
    print(f"|  Job ID:          {str(job_id):<{w-20}}|")
    print(f"|  Status:          {str(status):<{w-20}}|")
    print(f"|  Custo Estimado:  {cost_str:<{w-20}}|")
    print(f"+{border}+")
    print(f"|{'PROXIMOS PASSOS':^{w}}|")
    print(f"+{border}+")
    print(f"|  1. Aguarde o job processar (portal: databento.com/portal)  |")
    print(f"|  2. Baixe o CSV para: data/ndx_definitions_raw.csv          |")
    print(f"|  3. Execute: python scripts/db_step2_filter_ids.py          |")
    print(f"+{border}+")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("\n[...] Conectando ao Databento — Step 1: Definition Schema...\n")
    client = db.Historical(API_KEY)

    cost = check_cost(client)
    if cost is not None:
        print(f"[INFO] Custo estimado: US$ {cost:.4f}")
        confirm = input("[?] Confirmar submissao do job? (s/N): ").strip().lower()
        if confirm != "s":
            print("[ABORTADO] Job nao submetido.")
            sys.exit(0)

    try:
        job = submit_job(client)
        print_report(job, cost)
    except Exception as e:
        print(f"\n[ERRO] Falha na submissao: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
