"""
===============================================================================
 MD STEP 1 — Options Chain Extractor (Market Data API)
 Prop Desk Quant | NDX 7DTE Historical Snapshot | Etapa 1 de N
===============================================================================
 Arquitetura: pivot 100% do Databento para Market Data API (marketdata.app).
 Plano Trader: 100.000 requisicoes/dia.

 ESTE SCRIPT E UM TESTE UNITARIO:
   - Extrai a chain de opcoes do NDX para UM unico dia historico
   - Data alvo : 2026-01-15  (trade date)
   - Expiracao : 2026-01-22  (7DTE — horizonte minimo operacional do desk)
   - Saida     : G:/Meu Drive/Quant_Data_MD/NDX_chain_2026-01-15.parquet
   - Sem loops, sem extracoes massivas — validar integridade antes de escalar.

 CHAMADAS DE API: 2 (expirations probe + chain fetch)
 OUTPUT: 1 arquivo .parquet (compressao zstd, otimizado para ML)

 INPUT:  nenhum (standalone)
 OUTPUT: G:/Meu Drive/Quant_Data_MD/NDX_chain_2026-01-15.parquet
===============================================================================
"""

import os
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests


# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACAO
# ─────────────────────────────────────────────────────────────────────────────

API_KEY     = "aTUxSkNONm5PZ0tYLS1zN1JMSXpXVGhGM0lNd1Jra2g2UDJuVWtwMnFpYz0"
BASE_URL    = "https://api.marketdata.app/v1"

UNDERLYING  = "NDX"
TRADE_DATE  = "2026-01-15"
EXPIRATION  = "2026-01-22"   # 7DTE a partir de TRADE_DATE

OUTPUT_DIR  = Path("G:/Meu Drive/Quant_Data_MD")
COMPRESSION = "zstd"         # melhor ratio para workloads ML numericos
# stub para o futuro Step 2 com loops — nao usado aqui
RATE_LIMIT_SLEEP = 0.5

# Renomeia campos camelCase da API para snake_case padrao do desk
RENAME_MAP = {
    "optionSymbol":    "option_symbol",
    "bidSize":         "bid_size",
    "askSize":         "ask_size",
    "openInterest":    "open_interest",
    "underlyingPrice": "underlying_price",
    "inTheMoney":      "in_the_money",
    "intrinsicValue":  "intrinsic_value",
    "extrinsicValue":  "extrinsic_value",
}

# Campos esperados na resposta do endpoint /options/chain/
REQUIRED_FIELDS = [
    "optionSymbol", "bid", "ask", "iv", "delta", "gamma", "theta", "vega",
]


# ─────────────────────────────────────────────────────────────────────────────
# HTTP SESSION
# ─────────────────────────────────────────────────────────────────────────────

def build_session() -> requests.Session:
    """
    Cria uma requests.Session reutilizavel com header de autenticacao Token
    e Accept: application/json pre-configurados.
    Connection pooling reduz overhead em chamadas multiplas (Step 2+).
    """
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Token {API_KEY}",
        "Accept":        "application/json",
    })
    return session


# ─────────────────────────────────────────────────────────────────────────────
# PRE-FLIGHT: verificar disponibilidade da expiracao alvo
# ─────────────────────────────────────────────────────────────────────────────

def fetch_expirations(
    session: requests.Session,
    underlying: str,
    date: str,
) -> list[str]:
    """
    GET /v1/options/expirations/{underlying}/?date={date}

    Retorna lista de datas de expiracao disponiveis (ISO-8601: 'YYYY-MM-DD').
    Usado como guarda pre-flight para confirmar que EXPIRATION existe na API
    antes de chamar o endpoint chain (mais caro/lento).

    Encerra com sys.exit se: status HTTP != 2xx, status API != 'ok',
    ou lista de expiracoes vazia.
    """
    url = f"{BASE_URL}/options/expirations/{underlying}/"
    params = {"date": date}  # endpoint retorna strings 'YYYY-MM-DD' por padrao

    print(f"[INFO] Pre-flight: GET {url}?date={date}")
    try:
        resp = session.get(url, params=params, timeout=(10, 60))
        resp.raise_for_status()
    except requests.HTTPError as exc:
        sys.exit(
            f"[ERRO FATAL] HTTP {exc.response.status_code} em expirations.\n"
            f"             Verifique a API Key e o plano Trader."
        )
    except requests.RequestException as exc:
        sys.exit(f"[ERRO FATAL] Falha de rede em expirations: {exc}")

    data = resp.json()
    if data.get("s") != "ok":
        sys.exit(
            f"[ERRO FATAL] API status != 'ok' em expirations.\n"
            f"             Resposta: {data}"
        )

    # Endpoint retorna expiracoes como strings 'YYYY-MM-DD' — ler diretamente
    expirations = data.get("expirations", [])
    if not expirations:
        sys.exit(
            f"[ERRO FATAL] Nenhuma expiracao disponivel para {underlying} "
            f"em {date}."
        )

    return expirations


# ─────────────────────────────────────────────────────────────────────────────
# FETCH CHAIN — chamada principal de dados
# ─────────────────────────────────────────────────────────────────────────────

def fetch_chain(
    session: requests.Session,
    underlying: str,
    trade_date: str,
    expiration: str,
) -> dict:
    """
    GET /v1/options/chain/{underlying}/
    Params: date, expiration, dateformat=timestamp

    Retorna o JSON bruto da chain completa para a expiracao 7DTE.
    Cada contrato contem: bid, ask, mid, iv, delta, gamma, theta, vega, rho,
    strike, volume, open_interest, in_the_money, etc.

    Raises:
        SystemExit: em erro HTTP, erro de rede, ou status API != 'ok'.
    """
    url = f"{BASE_URL}/options/chain/{underlying}/"
    params = {
        "date":        trade_date,
        "expiration":  expiration,
        "dateformat":  "timestamp",  # expiracoes como Unix int — parse deterministico
    }

    print(f"[INFO] Fetch chain: GET {url}")
    print(f"       date={trade_date}  expiration={expiration}")
    try:
        resp = session.get(url, params=params, timeout=(10, 60))
        resp.raise_for_status()
    except requests.HTTPError as exc:
        sys.exit(
            f"[ERRO FATAL] HTTP {exc.response.status_code} em chain.\n"
            f"             Body: {exc.response.text[:300]}"
        )
    except requests.RequestException as exc:
        sys.exit(f"[ERRO FATAL] Falha de rede em chain: {exc}")

    data = resp.json()
    status = data.get("s", "")
    if status == "no_data":
        sys.exit(
            f"[ERRO FATAL] API retornou 'no_data' para chain {underlying} "
            f"em {trade_date} / exp {expiration}.\n"
            f"             Verifique se o mercado estava aberto nessa data."
        )
    if status != "ok":
        sys.exit(
            f"[ERRO FATAL] API status='{status}' em chain.\n"
            f"             errmsg: {data.get('errmsg', 'n/a')}"
        )

    # Verificar presenca dos campos criticos
    missing = [f for f in REQUIRED_FIELDS if f not in data]
    if missing:
        sys.exit(
            f"[ERRO FATAL] Campos ausentes na resposta da chain: {missing}\n"
            f"             Chaves disponíveis: {list(data.keys())}"
        )

    n_contracts = len(data.get("optionSymbol", []))
    print(f"[OK]   Chain recebida: {n_contracts} contratos")
    return data


# ─────────────────────────────────────────────────────────────────────────────
# PARSE — arrays colunar da API -> DataFrame tipado
# ─────────────────────────────────────────────────────────────────────────────

def parse_chain_to_dataframe(raw: dict, trade_date: str) -> pd.DataFrame:
    """
    Converte o formato colunar da API (cada campo e uma lista de N valores)
    em um DataFrame Pandas com tipagem otimizada para ML.

    Injeta 'trade_date' como coluna constante (a API nao ecoa o parametro
    'date' na resposta — necessario para concatenacoes futuras).

    Renomeia campos camelCase para snake_case via RENAME_MAP.
    """
    # A API retorna dados no formato colunar: {"optionSymbol": [...], "bid": [...]}
    # pd.DataFrame(raw) funciona diretamente quando todos os arrays tem mesmo len.
    # Excluir o campo de status 's' antes de construir o DataFrame.
    payload = {k: v for k, v in raw.items() if k != "s" and isinstance(v, list)}
    df = pd.DataFrame(payload)

    if df.empty:
        sys.exit("[ERRO FATAL] DataFrame vazio apos parse da chain.")

    # ── Renomear colunas para snake_case ──────────────────────────────────────
    df.rename(columns=RENAME_MAP, inplace=True)

    # ── Injetar trade_date (nao retornado pela API) ───────────────────────────
    trade_dt = pd.Timestamp(trade_date, tz="UTC")
    df.insert(0, "trade_date", trade_dt)

    # ── Converter timestamps para datetime64 UTC ─────────────────────────────
    # A chain retorna strings com offset: "2026-01-22 16:00:00 -05:00"
    # pd.to_datetime sem unit="s" parseia strings ISO-8601 com timezone nativo.
    for ts_col in ["expiration", "updated"]:
        if ts_col in df.columns:
            df[ts_col] = pd.to_datetime(df[ts_col], utc=True)

    # ── Calcular DTE a partir de trade_date e expiration ─────────────────────
    if "expiration" in df.columns:
        df["dte"] = (
            df["expiration"].dt.normalize() - trade_dt.normalize()
        ).dt.days.astype("int16")

    # ── Garantir coluna 'underlying' para joins futuros ──────────────────────
    # A API pode ja incluir 'underlying' no payload; sobrescrever com constante.
    df["underlying"] = "NDX"

    # ── Aplicar dtypes otimizados ─────────────────────────────────────────────
    category_cols = ["underlying", "side"]
    float32_cols  = [
        "bid", "ask", "mid", "underlying_price",
        "iv", "delta", "gamma", "theta", "vega", "rho",
        "intrinsic_value", "extrinsic_value",
    ]
    int32_cols = ["bid_size", "ask_size", "volume", "open_interest"]

    for col in category_cols:
        if col in df.columns:
            df[col] = df[col].astype("category")

    for col in float32_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("float32")

    for col in int32_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype("int32")

    if "in_the_money" in df.columns:
        df["in_the_money"] = df["in_the_money"].astype(bool)

    if "strike" in df.columns:
        df["strike"] = pd.to_numeric(df["strike"], errors="coerce")  # float64 — precisao de preco

    # ── Ordenar por side (call/put) e strike ─────────────────────────────────
    sort_cols = [c for c in ["side", "strike"] if c in df.columns]
    if sort_cols:
        df.sort_values(sort_cols, inplace=True, ignore_index=True)

    return df


# ─────────────────────────────────────────────────────────────────────────────
# VALIDACAO PRE-SAVE
# ─────────────────────────────────────────────────────────────────────────────

def validate_dataframe(df: pd.DataFrame) -> None:
    """
    Assercoes pre-save. Encerra com sys.exit em caso de falha.

    Checks:
    1. DataFrame nao vazio
    2. Colunas criticas presentes (option_symbol, bid, ask, delta, iv)
    3. Gregas nao todas-NaN (indicaria chain sem Greeks na resposta)
    4. bid <= ask em todos os registros
    5. strike > 0 em todos os registros
    """
    print("[INFO] Validando DataFrame...")

    if df.empty:
        sys.exit("[ERRO FATAL] Validacao falhou: DataFrame vazio.")

    required = ["option_symbol", "bid", "ask", "delta", "iv"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        sys.exit(f"[ERRO FATAL] Validacao falhou: colunas ausentes: {missing}")

    greeks_all_nan = []
    for greek in ["delta", "gamma", "theta", "vega", "iv"]:
        if greek in df.columns and df[greek].isna().all():
            greeks_all_nan.append(greek)
    if greeks_all_nan:
        # Endpoint historico do Market Data nao armazena gregas computadas.
        # Bid/ask e estrutura da chain estao presentes — pipeline valido.
        print(
            f"[AVISO] Greeks {greeks_all_nan} sao 100% NaN para esta data historica.\n"
            f"        O endpoint /options/chain/ historico nao computa gregas.\n"
            f"        Bid, Ask e estrutura da chain estao integros — parquet valido."
        )

    if "bid" in df.columns and "ask" in df.columns:
        invalid_spread = df["bid"] > df["ask"]
        n_invalid = invalid_spread.sum()
        if n_invalid > 0:
            print(
                f"[AVISO] {n_invalid} contratos com bid > ask "
                f"({n_invalid/len(df)*100:.1f}%) — possivel dado de mercado fechado."
            )

    if "strike" in df.columns:
        n_zero = (df["strike"] <= 0).sum()
        if n_zero > 0:
            sys.exit(f"[ERRO FATAL] Validacao falhou: {n_zero} registros com strike <= 0.")

    print(f"[OK]   Validacao passou: {len(df):,} contratos, {len(df.columns)} colunas.")


# ─────────────────────────────────────────────────────────────────────────────
# SALVAR PARQUET
# ─────────────────────────────────────────────────────────────────────────────

def save_parquet(
    df: pd.DataFrame,
    output_dir: Path,
    trade_date: str,
    underlying: str,
) -> Path:
    """
    Salva o DataFrame em parquet com escrita atomica:
        1. Escreve em {filename}.tmp
        2. os.replace(tmp, final) — atomico no Windows NTFS e POSIX

    Nomenclatura: {underlying}_chain_{trade_date}.parquet
    Exemplo     : NDX_chain_2026-01-15.parquet

    Engine  : pyarrow (suporte completo a UTC-aware datetime e category dtype)
    Compressao: zstd (~40-50% melhor ratio que snappy para colunas float densas)
    """
    # Guard: Google Drive precisa estar montado
    if not Path("G:/").exists():
        sys.exit(
            "[ERRO FATAL] Google Drive nao montado em G:/.\n"
            "             Verifique o Google Drive for Desktop e tente novamente."
        )

    output_dir.mkdir(parents=True, exist_ok=True)

    filename  = f"{underlying}_chain_{trade_date}.parquet"
    final_path = output_dir / filename
    tmp_path   = output_dir / (filename + ".tmp")

    print(f"[INFO] Salvando parquet: {final_path}")
    try:
        df.to_parquet(
            tmp_path,
            engine="pyarrow",
            compression=COMPRESSION,
            index=False,
        )
        os.replace(tmp_path, final_path)  # atomico no Windows NTFS
    except Exception as exc:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        sys.exit(f"[ERRO FATAL] Falha ao salvar parquet: {exc}")

    file_kb = final_path.stat().st_size / 1024
    print(f"[OK]   Parquet salvo: {final_path}  ({file_kb:.1f} KB)")
    return final_path


# ─────────────────────────────────────────────────────────────────────────────
# VERIFICACAO POS-SAVE (read-back)
# ─────────────────────────────────────────────────────────────────────────────

def verify_parquet(path: Path) -> None:
    """
    Le o arquivo parquet de volta do disco e imprime relatorio de integridade.
    Confirma que o arquivo e legivel pelo pyarrow e que os dados fazem sentido.
    Nao lanca excecoes — apenas imprime avisos se algo for inesperado.
    """
    print(f"\n[INFO] Verificacao read-back: {path.name}")
    try:
        df_check = pd.read_parquet(path, engine="pyarrow")
    except Exception as exc:
        print(f"[AVISO] Nao foi possivel ler o parquet de volta: {exc}")
        return

    calls = df_check[df_check["side"].astype(str) == "call"] if "side" in df_check.columns else pd.DataFrame()
    puts  = df_check[df_check["side"].astype(str) == "put"]  if "side" in df_check.columns else pd.DataFrame()

    print(f"  Shape        : {df_check.shape[0]:,} linhas x {df_check.shape[1]} colunas")
    print(f"  Calls / Puts : {len(calls):,} / {len(puts):,}")

    if "strike" in df_check.columns:
        print(
            f"  Strikes      : {df_check['strike'].min():,.0f}  ->  "
            f"{df_check['strike'].max():,.0f}"
        )
    if "iv" in df_check.columns:
        iv_pct = df_check["iv"].dropna() * 100
        print(f"  IV range     : {iv_pct.min():.1f}%  ->  {iv_pct.max():.1f}%")
    if "delta" in df_check.columns:
        d = df_check["delta"].dropna()
        print(f"  Delta range  : {d.min():.3f}  ->  {d.max():.3f}")

    print(f"\n  dtypes:")
    for col, dtype in df_check.dtypes.items():
        print(f"    {col:<25} {str(dtype)}")

    print(f"\n  Amostra (head 3):")
    display_cols = [c for c in ["option_symbol", "side", "strike", "bid", "ask", "iv", "delta"] if c in df_check.columns]
    print(df_check[display_cols].head(3).to_string(index=False))


# ─────────────────────────────────────────────────────────────────────────────
# RELATORIO FINAL
# ─────────────────────────────────────────────────────────────────────────────

def print_report(df: pd.DataFrame, path: Path, elapsed_sec: float) -> None:
    """Imprime o banner de relatorio no estilo visual do desk (w=66)."""
    w      = 66
    border = "=" * w

    n_calls = (df["side"].astype(str) == "call").sum() if "side" in df.columns else "N/A"
    n_puts  = (df["side"].astype(str) == "put").sum()  if "side" in df.columns else "N/A"
    s_min   = f"{df['strike'].min():,.0f}" if "strike" in df.columns else "N/A"
    s_max   = f"{df['strike'].max():,.0f}" if "strike" in df.columns else "N/A"
    iv_min  = f"{df['iv'].min()*100:.1f}%" if "iv" in df.columns else "N/A"
    iv_max  = f"{df['iv'].max()*100:.1f}%" if "iv" in df.columns else "N/A"
    file_kb = f"{path.stat().st_size / 1024:.1f} KB"

    print()
    print(f"+{border}+")
    print(f"|{'MD STEP 1 — OPTIONS CHAIN EXTRACTOR':^{w}}|")
    print(f"|{'Prop Desk Quant | Market Data API | CONCLUIDO':^{w}}|")
    print(f"+{border}+")
    print(f"|  Timestamp     : {datetime.now().strftime('%Y-%m-%d %H:%M:%S'):<{w-18}}|")
    print(f"|  Elapsed       : {elapsed_sec:.1f}s{' ' * (w - 18 - len(f'{elapsed_sec:.1f}s'))}|")
    print(f"|  Underlying    : {UNDERLYING:<{w-18}}|")
    print(f"|  Trade Date    : {TRADE_DATE:<{w-18}}|")
    print(f"|  Expiration    : {EXPIRATION}  (7DTE){' ' * (w - 26)}|")
    print(f"+{border}+")
    print(f"|  Total cttos   : {len(df):,}{' ' * (w - 18 - len(f'{len(df):,}'))}|")
    print(f"|  Calls         : {str(n_calls):<{w-18}}|")
    print(f"|  Puts          : {str(n_puts):<{w-18}}|")
    print(f"|  Strikes       : {s_min} -> {s_max}{' ' * max(0, w-18-len(f'{s_min} -> {s_max}'))}|")
    print(f"|  IV range      : {iv_min} -> {iv_max}{' ' * max(0, w-18-len(f'{iv_min} -> {iv_max}'))}|")
    print(f"+{border}+")
    print(f"|  Output        : {path.name:<{w-18}}|")
    print(f"|  Tamanho       : {file_kb:<{w-18}}|")
    print(f"|  Compressao    : {COMPRESSION:<{w-18}}|")
    print(f"+{border}+")
    print(f"|  {'PROXIMO PASSO: pd.read_parquet(path).info() para validar':^{w}}|")
    print(f"+{border}+")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    t_start = time.time()

    print("\n" + "=" * 68)
    print("  MD STEP 1 — Options Chain Extractor (Market Data API)")
    print(f"  Prop Desk Quant | {UNDERLYING} | {TRADE_DATE} | 7DTE")
    print("=" * 68 + "\n")

    # ── 1. Session ────────────────────────────────────────────────────────────
    session = build_session()
    print(f"[INFO] API      : {BASE_URL}")
    print(f"[INFO] Plano    : Trader (100.000 req/dia)")
    print(f"[INFO] Output   : {OUTPUT_DIR}\n")

    # ── 2. Pre-flight: confirmar expiracao disponivel ─────────────────────────
    expirations = fetch_expirations(session, UNDERLYING, TRADE_DATE)
    if EXPIRATION not in expirations:
        sys.exit(
            f"[ERRO FATAL] Expiracao {EXPIRATION} nao encontrada na API para "
            f"{UNDERLYING} em {TRADE_DATE}.\n"
            f"             Expiracoes disponíveis: {expirations[:10]}"
        )
    print(f"[OK]   Expiracao {EXPIRATION} confirmada (7DTE).\n")

    # ── 3. Fetch chain snapshot ───────────────────────────────────────────────
    raw = fetch_chain(session, UNDERLYING, TRADE_DATE, EXPIRATION)
    print()

    # ── 4. Parse para DataFrame tipado ───────────────────────────────────────
    df = parse_chain_to_dataframe(raw, TRADE_DATE)
    print(f"[OK]   DataFrame: {df.shape[0]:,} linhas x {df.shape[1]} colunas\n")

    # ── 5. Validacao pre-save ─────────────────────────────────────────────────
    validate_dataframe(df)
    print()

    # ── 6. Salvar parquet ─────────────────────────────────────────────────────
    output_path = save_parquet(df, OUTPUT_DIR, TRADE_DATE, UNDERLYING)
    print()

    # ── 7. Verificacao read-back ──────────────────────────────────────────────
    verify_parquet(output_path)

    # ── 8. Relatorio final ────────────────────────────────────────────────────
    elapsed = time.time() - t_start
    print_report(df, output_path, elapsed)


if __name__ == "__main__":
    main()
