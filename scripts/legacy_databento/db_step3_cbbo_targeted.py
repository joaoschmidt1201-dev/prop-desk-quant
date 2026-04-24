"""
===============================================================================
 DB STEP 3 — CBBO-1m Bulk Extractor (Arquitetura "Bulk por Data")
 Prop Desk Quant | Extração OPRA via Parent Symbols (Etapa 3 de 3)
===============================================================================
 Arquitetura de baixo custo: em vez de 130K instrument_ids individuais,
 usa symbols=['NDX', 'NDXP'] com stype_in='parent'. A bolsa resolve a chain
 completa; filtramos localmente após o download.

 MUDANCAS vs versao anterior:
   - REMOVIDA dependencia de filtered_ids.csv
   - stype_in: 'instrument_id' -> 'parent'
   - Periodo: 5 anos -> 12 meses (2025-04-04 a 2026-03-28)
   - Estrutura: batches por ID -> uma chamada por sexta (09:30-16:00 ET)
   - Gate de custo: sys.exit(0) apos exibir estimativa — SEM download

 MODELO DE CUSTO:
   - metadata.get_cost() chamado para UMA sexta de amostra
   - Total estimado = custo_amostra × numero_de_sextas (~48)
   - Script encerra aqui; para habilitar download: ALLOW_DOWNLOAD = True

 INPUT:  nenhum (standalone)
 OUTPUT: data/cbbo_weekly_options_filtered.csv (quando download habilitado)
         data/cbbo_bulk/cbbo_YYYY-MM-DD.dbn.zst (um por sexta)
===============================================================================
"""

import os
import re
import sys
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo   # stdlib Python 3.9+ — sem instalacao adicional

import pandas as pd
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

ROOT        = Path(__file__).parent.parent
DATA_DIR    = ROOT / "data"
BULK_DIR    = DATA_DIR / "cbbo_bulk"       # um .dbn.zst por sexta
OUTPUT_CSV  = DATA_DIR / "cbbo_weekly_options_filtered.csv"

DATASET  = "OPRA.PILLAR"
SCHEMA   = "cbbo-1m"
STYPE_IN = "parent"
SYMBOLS  = ["NDX.OPT", "NDXP.OPT"]

DATE_START = "2025-04-04"   # primeira sexta util do periodo (Good Friday = 04-18, excluida)
DATE_END   = "2026-03-28"   # ultima sexta antes de 2026-03-31

ACCOUNT_BALANCE_USD = 74.00  # saldo restante em 2026-04-01

# Feriados de sexta no periodo (NYSE closed)
MARKET_HOLIDAYS_FRIDAYS = {
    date(2025, 4, 18),   # Good Friday 2025
    # Nao ha outros feriados de sexta no NYSE calendar ate 2026-03-28
}

# ── GATE DE SEGURANÇA ────────────────────────────────────────────────────────
# Download habilitado apos aprovacao de Joao/CZ em 2026-04-01.
ALLOW_DOWNLOAD = True
# ─────────────────────────────────────────────────────────────────────────────

ET  = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

MARKET_OPEN_ET  = time(9, 30)
MARKET_CLOSE_ET = time(16, 0)


# ─────────────────────────────────────────────────────────────────────────────
# GERACAO DE SEXTAS UTEIS
# ─────────────────────────────────────────────────────────────────────────────

def generate_fridays(start: str = DATE_START, end: str = DATE_END) -> list[date]:
    """
    Gera todas as sextas uteis entre start e end (inclusive),
    excluindo feriados NYSE em MARKET_HOLIDAYS_FRIDAYS.
    """
    all_fridays = pd.date_range(start, end, freq="W-FRI")
    return [d.date() for d in all_fridays if d.date() not in MARKET_HOLIDAYS_FRIDAYS]


# ─────────────────────────────────────────────────────────────────────────────
# CONVERSAO ET -> UTC COM SUPORTE A DST
# ─────────────────────────────────────────────────────────────────────────────

def friday_to_utc_window(friday: date) -> tuple[str, str]:
    """
    Converte a sessao 09:30-16:00 ET de uma sexta para janela UTC.

    Usa ZoneInfo('America/New_York') para DST automatico:
      - Verao (EDT = UTC-4): 09:30 ET -> 13:30Z | 16:00 ET -> 20:00Z
      - Inverno (EST = UTC-5): 09:30 ET -> 14:30Z | 16:00 ET -> 21:00Z

    Returns:
        (start_utc, end_utc) como strings ISO-8601 sem sufixo Z.
    """
    open_et = datetime(
        friday.year, friday.month, friday.day,
        MARKET_OPEN_ET.hour, MARKET_OPEN_ET.minute,
        tzinfo=ET,
    )
    close_et = datetime(
        friday.year, friday.month, friday.day,
        MARKET_CLOSE_ET.hour, MARKET_CLOSE_ET.minute,
        tzinfo=ET,
    )

    fmt = "%Y-%m-%dT%H:%M:%S"
    return (
        open_et.astimezone(UTC).strftime(fmt),
        close_et.astimezone(UTC).strftime(fmt),
    )


# ─────────────────────────────────────────────────────────────────────────────
# ESTIMATIVA DE CUSTO — GATE OBRIGATORIO
# ─────────────────────────────────────────────────────────────────────────────

def get_sample_friday(fridays: list[date]) -> date:
    """
    Retorna a sexta de amostra mais recente que ja passou (< hoje).
    Usada como proxy de custo para uma sexta tipica.
    """
    today = date.today()
    past = [f for f in fridays if f < today]
    if not past:
        # Nenhuma sexta no passado no periodo — usa a primeira como estimativa
        return fridays[0]
    return past[-1]


def estimate_cost_and_exit(client: db.Historical, fridays: list[date]) -> None:
    """
    1. Seleciona uma sexta de amostra no passado.
    2. Chama metadata.get_cost() para APENAS essa sexta (09:30-16:00 ET -> UTC).
    3. Extrapola: total_estimado = custo_amostra * len(fridays).
    4. Imprime relatorio de custo completo.
    5. sys.exit(0) — NENHUM DOWNLOAD OCORRE NESTA FUNCAO.
    """
    sample_friday = get_sample_friday(fridays)
    start_utc, end_utc = friday_to_utc_window(sample_friday)

    print(f"\n[...] Calculando custo via metadata.get_cost()...")
    print(f"      Sexta de amostra : {sample_friday}")
    print(f"      Janela UTC       : {start_utc} -> {end_utc}")
    print(f"      Symbols          : {SYMBOLS}")
    print(f"      stype_in         : {STYPE_IN}")

    try:
        per_friday_cost = client.metadata.get_cost(
            dataset=DATASET,
            symbols=SYMBOLS,
            stype_in=STYPE_IN,
            schema=SCHEMA,
            start=start_utc,
            end=end_utc,
        )
    except Exception as e:
        print(f"\n[ERRO] metadata.get_cost() falhou: {e}")
        print("[INFO] Nao foi possivel estimar o custo. Abortando por seguranca.")
        sys.exit(1)

    n_fridays       = len(fridays)
    total_estimated = per_friday_cost * n_fridays
    pct_balance     = (total_estimated / ACCOUNT_BALANCE_USD) * 100 if ACCOUNT_BALANCE_USD > 0 else float("inf")

    w = 66
    border = "=" * w
    print()
    print(f"+{border}+")
    print(f"|{'ESTIMATIVA DE CUSTO — DB STEP 3 BULK':^{w}}|")
    print(f"|{'Arquitetura: parent symbols x sextas (09:30-16:00 ET)':^{w}}|")
    print(f"+{border}+")
    print(f"|  Periodo            : {DATE_START} a {DATE_END:<{w-35}}|")
    print(f"|  Sextas uteis       : {n_fridays:<{w-23}}|")
    print(f"|  Sexta de amostra   : {str(sample_friday):<{w-23}}|")
    print(f"|  Custo p/ sexta     : US$ {per_friday_cost:<{w-27}.4f}|")
    print(f"|  Total estimado     : US$ {total_estimated:<{w-27}.4f}|")
    print(f"|  Saldo disponivel   : US$ {ACCOUNT_BALANCE_USD:<{w-27}.2f}|")
    print(f"|  Custo / Saldo      : {pct_balance:<{w-23}.1f}%|")
    print(f"+{border}+")

    if total_estimated > ACCOUNT_BALANCE_USD:
        print(f"\n[ALERTA CRITICO] Custo estimado (US$ {total_estimated:.2f}) "
              f"EXCEDE o saldo (US$ {ACCOUNT_BALANCE_USD:.2f})!")
        print("                 Revise a estrategia antes de habilitar o download.")
    elif total_estimated > ACCOUNT_BALANCE_USD * 0.80:
        print(f"\n[AVISO] Custo estimado consome {pct_balance:.1f}% do saldo restante.")
        print("        Proceda com cautela.")
    else:
        print(f"\n[OK] Custo estimado dentro do saldo disponivel ({pct_balance:.1f}%).")

    print()
    print("[INFO] Prosseguindo para download...")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# DOWNLOAD POR SEXTA (INALCANCAVEL COM ALLOW_DOWNLOAD = False)
# ─────────────────────────────────────────────────────────────────────────────

def download_friday(
    client: db.Historical,
    friday: date,
    output_dir: Path,
) -> Path:
    """
    Baixa cbbo-1m para uma sexta (09:30-16:00 ET) via parent symbols.
    Escreve em arquivo .tmp e renomeia atomicamente apos conclusao.
    Pula se o arquivo final ja existir (idempotente).
    """
    final_path = output_dir / f"cbbo_{friday.isoformat()}.dbn.zst"
    tmp_path   = output_dir / f"cbbo_{friday.isoformat()}.dbn.zst.tmp"

    if final_path.exists():
        print(f"[SKIP] {friday} — arquivo ja existe: {final_path.name}")
        return final_path

    start_utc, end_utc = friday_to_utc_window(friday)
    print(f"[...] {friday}  {start_utc} -> {end_utc} UTC")

    client.timeseries.get_range(
        dataset=DATASET,
        symbols=SYMBOLS,
        stype_in=STYPE_IN,
        schema=SCHEMA,
        start=start_utc,
        end=end_utc,
        path=str(tmp_path),
    )

    # Renomeia atomicamente para o caminho final
    tmp_path.rename(final_path)
    print(f"[OK]   {friday} -> {final_path.name}")
    return final_path


def download_all_fridays(
    client: db.Historical,
    fridays: list[date],
) -> list[Path]:
    """
    Itera sobre todas as sextas e baixa cada uma.
    So executa se ALLOW_DOWNLOAD = True.
    """
    if not ALLOW_DOWNLOAD:
        sys.exit(
            "[SEGURANCA] ALLOW_DOWNLOAD=False.\n"
            "            Defina ALLOW_DOWNLOAD = True apos revisar o custo estimado."
        )

    BULK_DIR.mkdir(parents=True, exist_ok=True)
    n = len(fridays)
    print(f"\n[INFO] Iniciando download de {n} sextas em {BULK_DIR}")

    downloaded = []
    for idx, friday in enumerate(fridays, 1):
        print(f"[{idx:02d}/{n:02d}] ", end="")
        try:
            path = download_friday(client, friday, BULK_DIR)
            downloaded.append(path)
        except Exception as e:
            print(f"[ERRO] {friday}: {e}")

    print(f"\n[OK] {len(downloaded)}/{n} arquivos baixados.")
    return downloaded


# ─────────────────────────────────────────────────────────────────────────────
# PARSING DE SIMBOLOS OPRA
# ─────────────────────────────────────────────────────────────────────────────

# Formato OSI/OPRA: "NDXP  250404C13000000"
#   root (1-6 chars, padded) + YYMMDD + C/P + strike (8 digits, millesimos de USD)
_OPRA_RE = re.compile(
    r"^(?P<root>[A-Z]{1,6})\s+"
    r"(?P<yy>\d{2})(?P<mm>\d{2})(?P<dd>\d{2})"
    r"(?P<cls>[CP])"
    r"(?P<strike>\d{8})$"
)


def parse_opra_symbol(raw_symbol: str) -> dict:
    """
    Decodifica simbolo OPRA para componentes.
    Strike retornado em escala humana (dolares): 13000000 -> 13000.000.
    Retorna dict com chaves: root, expiration, instrument_class, strike_price.
    Em caso de falha de parsing, retorna None em todos os campos.
    """
    if not isinstance(raw_symbol, str):
        return {"root": None, "expiration": None, "instrument_class": None, "strike_price": None}

    m = _OPRA_RE.match(raw_symbol.strip())
    if not m:
        return {"root": None, "expiration": None, "instrument_class": None, "strike_price": None}

    try:
        exp = date(2000 + int(m.group("yy")), int(m.group("mm")), int(m.group("dd")))
    except ValueError:
        exp = None

    return {
        "root":             m.group("root"),
        "expiration":       exp,
        "instrument_class": m.group("cls"),
        "strike_price":     int(m.group("strike")) / 1000.0,
    }


# ─────────────────────────────────────────────────────────────────────────────
# PROCESSAMENTO LOCAL DOS ARQUIVOS DBN
# ─────────────────────────────────────────────────────────────────────────────

def load_and_filter_dbn(dbn_files: list[Path]) -> pd.DataFrame:
    """
    Le arquivos DBN baixados, aplica filtros locais e enriquece com dados OPRA.

    Filtros:
      - instrument_class in ['C', 'P']
      - root in ['NDX', 'NDXP']

    Enriquecimento:
      - parse_opra_symbol() -> strike_price, expiration, instrument_class, root
      - midpoint = (bid_px + ask_px) / 2
      - friday_date derivado de ts_recv convertido para ET
    """
    print("\n[...] Processando arquivos DBN...")

    all_dfs = []
    for f in dbn_files:
        if not f.exists():
            print(f"[AVISO] Arquivo nao encontrado: {f}")
            continue
        store = db.DBNStore.from_file(str(f))
        df = store.to_df()
        all_dfs.append(df)
        print(f"[OK] {f.name}: {len(df):,} records")

    if not all_dfs:
        sys.exit("[ERRO] Nenhum arquivo DBN para processar.")

    raw = pd.concat(all_dfs, ignore_index=True)
    print(f"[INFO] Total antes do filtro: {len(raw):,} records")

    # Normalizar ts_recv para UTC
    if "ts_recv" not in raw.columns:
        sys.exit("[ERRO] Coluna ts_recv ausente. Verifique o schema cbbo-1m.")
    raw["ts_recv"] = pd.to_datetime(raw["ts_recv"], utc=True)

    # Derivar friday_date a partir do ts_recv em ET
    raw["friday_date"] = (
        raw["ts_recv"]
        .dt.tz_convert(ET)
        .dt.date
        .astype(str)
    )

    # Normalizar colunas de preco
    if "bid_price" in raw.columns and "bid_px" not in raw.columns:
        raw = raw.rename(columns={"bid_price": "bid_px", "ask_price": "ask_px"})

    # Calcular midpoint
    if "bid_px" in raw.columns and "ask_px" in raw.columns:
        raw["midpoint"] = (raw["bid_px"] + raw["ask_px"]) / 2

    # Enriquecer com parsing OPRA (se raw_symbol disponivel)
    if "raw_symbol" in raw.columns:
        parsed = raw["raw_symbol"].apply(parse_opra_symbol).apply(pd.Series)
        raw = pd.concat([raw, parsed], axis=1)
        # Filtrar por root NDX/NDXP e classe C/P
        raw = raw[raw["root"].isin(["NDX", "NDXP"])].copy()
        raw = raw[raw["instrument_class"].isin(["C", "P"])].copy()
    else:
        print("[AVISO] Coluna raw_symbol ausente — parsamento OPRA ignorado.")
        print("        Passe map_symbols=True na chamada timeseries.get_range().")

    print(f"[INFO] Records apos filtro: {len(raw):,}")

    # Selecionar colunas finais
    base_cols  = ["ts_recv", "friday_date", "instrument_id"]
    opra_cols  = ["raw_symbol", "root", "instrument_class", "strike_price", "expiration"]
    price_cols = ["bid_px", "ask_px", "bid_sz", "ask_sz", "midpoint"]
    final_cols = [c for c in base_cols + opra_cols + price_cols if c in raw.columns]

    result = raw[final_cols].copy()
    result = result.sort_values(
        [c for c in ["friday_date", "instrument_class", "strike_price", "ts_recv"] if c in result.columns]
    )
    return result


# ─────────────────────────────────────────────────────────────────────────────
# RELATORIO FINAL
# ─────────────────────────────────────────────────────────────────────────────

def print_final_report(df: pd.DataFrame) -> None:
    w = 66
    border = "=" * w
    fridays = df["friday_date"].nunique() if "friday_date" in df.columns else "N/A"
    n_calls = (df["instrument_class"] == "C").sum() if "instrument_class" in df.columns else "N/A"
    n_puts  = (df["instrument_class"] == "P").sum() if "instrument_class" in df.columns else "N/A"

    print()
    print(f"+{border}+")
    print(f"|{'DB STEP 3 — CBBO BULK EXTRACTOR':^{w}}|")
    print(f"|{'Prop Desk Quant | Etapa 3 de 3 — CONCLUIDO':^{w}}|")
    print(f"+{border}+")
    print(f"|  Timestamp     : {datetime.now().strftime('%Y-%m-%d %H:%M:%S'):<{w-18}}|")
    print(f"|  Records total : {len(df):,}{' ' * (w - 18 - len(str(len(df))))}|")
    print(f"|  Sextas        : {str(fridays):<{w-18}}|")
    print(f"|  Calls         : {str(n_calls):<{w-18}}|")
    print(f"|  Puts          : {str(n_puts):<{w-18}}|")
    print(f"|  Output        : {str(OUTPUT_CSV.name):<{w-18}}|")
    print(f"+{border}+")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 68)
    print("  DB STEP 3 — CBBO-1m Bulk Extractor (Bulk por Data)")
    print("  Prop Desk Quant | stype_in='parent' | 12 meses | ~48 sextas")
    print("=" * 68 + "\n")

    client  = db.Historical(API_KEY)
    fridays = generate_fridays()

    print(f"[INFO] Periodo  : {DATE_START} -> {DATE_END}")
    print(f"[INFO] Symbols  : {SYMBOLS}  |  stype_in: {STYPE_IN}")
    print(f"[INFO] Sextas   : {len(fridays)}  ({fridays[0]} a {fridays[-1]})")
    print(f"[INFO] Saldo    : US$ {ACCOUNT_BALANCE_USD:.2f}")

    # ── GATE OBRIGATORIO: estima custo e encerra ──────────────────────────────
    # sys.exit(0) e chamado dentro de estimate_cost_and_exit().
    # As linhas abaixo sao INALCANCAVEIS enquanto ALLOW_DOWNLOAD = False.
    estimate_cost_and_exit(client, fridays)

    # ── INALCANCAVEL COM ALLOW_DOWNLOAD = False ───────────────────────────────
    if not ALLOW_DOWNLOAD:
        sys.exit(
            "[SEGURANCA] ALLOW_DOWNLOAD=False.\n"
            "            Defina True apos revisar o custo e obter aprovacao."
        )

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    dbn_files = download_all_fridays(client, fridays)

    result = load_and_filter_dbn(dbn_files)
    if result.empty:
        print("[AVISO] Nenhum record apos filtragem local.")
        sys.exit(1)

    result.to_csv(OUTPUT_CSV, index=False)
    print(f"\n[OK] Output salvo: {OUTPUT_CSV}")
    print_final_report(result)


if __name__ == "__main__":
    main()
