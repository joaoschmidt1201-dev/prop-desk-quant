"""
===============================================================================
 MD STEP 2 — Mass Options Extractor (Market Data API)
 Prop Desk Quant | NDX | Janela Contínua 0–45 DTE | Extração Histórica em Lote
===============================================================================
 Arquitetura: extração bruta de chain completa, sem Greeks via API.
 Greeks serão calculadas localmente (Black-Scholes / Heston) a partir
 dos preços brutos Bid / Ask / Spot nas etapas seguintes do pipeline.

 FLUXO POR TRADE_DATE:
   1. Busca expirations disponíveis na API              → 1 req
   2. Filtra expirations com 0 < DTE ≤ MAX_DTE=45      → 0 req (local)
   3. Para cada expiração válida (~7–9 por dia):
      a. GET /chain/ → snapshot completo                → 1 req por expiração
      b. Filtro ATM ±STRIKE_RADIUS=30 posições (local)  → 0 req
   4. Concat de todas as cadeias do dia
   5. Salva NDX_chain_YYYY-MM-DD.parquet (zstd)

 CÃO DE GUARDA (watchdog):
   - APICounter global: para graciosamente em 95.000 chamadas
   - Idempotência: dias com parquet já existente são pulados
   - Orçamento real: ~252 dias × ~8 req = ~2.016 req — cabe em UMA sessão

 RANGE:  2025-04-05 → 2026-04-01  (limite Trial: máx 1 ano de profundidade)
 INPUT:  data/ndx_closes_cache.csv  (spot NDX local — 0 chamadas de API)
 OUTPUT: G:/Meu Drive/Quant_Data_MD/NDX_chain_YYYY-MM-DD.parquet
===============================================================================
"""

import os
import sys
import time
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import requests

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURAÇÃO
# ─────────────────────────────────────────────────────────────────────────────

API_KEY        = "aTUxSkNONm5PZ0tYLS1zN1JMSXpXVGhGM0lNd1Jra2g2UDJuVWtwMnFpYz0"
BASE_URL       = "https://api.marketdata.app/v1"
UNDERLYING     = "SPX"

DATE_START     = "2025-04-05"   # limite Trial: máx 1 ano de profundidade histórica
DATE_END       = "2026-04-01"   # data atual

MAX_DTE        = 45             # janela contínua: todas as expirações com DTE ≤ 45
STRIKE_RADIUS  = 30             # ±30 posições de strike em relação ao ATM

OUTPUT_DIR     = Path("G:/Meu Drive/Quant_Data_MD")
COMPRESSION    = "zstd"

API_LIMIT      = 95_000         # hard stop do watchdog (5% de margem antes do 429)
RATE_SLEEP     = 0.10           # ~10 req/s — cortesia com o endpoint

CLOSES_CACHE   = Path(__file__).parent.parent / "data" / "cache" / "ndx_closes_cache.csv"


# ─────────────────────────────────────────────────────────────────────────────
# CÃO DE GUARDA — CONTADOR GLOBAL DE REQUISIÇÕES
# ─────────────────────────────────────────────────────────────────────────────

class APICounter:
    _count: int = 0

    @classmethod
    def increment(cls) -> None:
        cls._count += 1

    @classmethod
    def count(cls) -> int:
        return cls._count

    @classmethod
    def is_safe(cls) -> bool:
        return cls._count < API_LIMIT

    @classmethod
    def status_line(cls) -> str:
        pct = cls._count / API_LIMIT * 100
        return f"API calls: {cls._count:,} / {API_LIMIT:,}  ({pct:.1f}%)"


def tracked_get(session: requests.Session, url: str, **kwargs) -> requests.Response:
    """Wrapper sobre session.get() que contabiliza cada chamada e aplica rate sleep."""
    APICounter.increment()
    resp = session.get(url, **kwargs)
    time.sleep(RATE_SLEEP)
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# SPOT PRICE — CACHE LOCAL (0 CHAMADAS DE API)
# ─────────────────────────────────────────────────────────────────────────────

def load_spot_cache() -> dict[str, float]:
    """
    Carrega closes cache em dict {date_str: close_price}.
    Fonte autoritativa para NDX spot histórico. Custo: 0 chamadas de API.
    """
    if not CLOSES_CACHE.exists():
        sys.exit(
            f"[ERRO FATAL] Closes cache não encontrado: {CLOSES_CACHE}\n"
            f"             Execute ic7_simulator.py para regenerar."
        )
    df = pd.read_csv(CLOSES_CACHE, parse_dates=False)
    return dict(zip(df["date"].astype(str), df["Close"].astype(float)))


def get_trading_days(spot_cache: dict[str, float]) -> list[str]:
    """Retorna dias úteis no range [DATE_START, DATE_END] a partir do closes cache."""
    return sorted(d for d in spot_cache if DATE_START <= d <= DATE_END)


# ─────────────────────────────────────────────────────────────────────────────
# HTTP SESSION
# ─────────────────────────────────────────────────────────────────────────────

def build_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "Authorization": f"Token {API_KEY}",
        "Accept":        "application/json",
    })
    return s


# ─────────────────────────────────────────────────────────────────────────────
# EXPIRATIONS — JANELA CONTÍNUA
# ─────────────────────────────────────────────────────────────────────────────

def fetch_expirations(session: requests.Session, trade_date: str) -> list[str]:
    """
    GET /v1/options/expirations/{UNDERLYING}/?date={trade_date}
    Retorna lista de strings 'YYYY-MM-DD'. Retorna [] em erro.
    """
    url = f"{BASE_URL}/options/expirations/{UNDERLYING}/"
    try:
        resp = tracked_get(session, url, params={"date": trade_date}, timeout=(10, 30))
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        print(f"  [WARN] expirations falhou em {trade_date}: {exc}")
        return []

    if data.get("s") != "ok":
        print(f"  [WARN] expirations status={data.get('s')} em {trade_date}")
        return []

    return data.get("expirations", [])


def get_valid_expirations(
    expirations: list[str],
    trade_date: str,
    max_dte: int,
) -> list[tuple[str, int]]:
    """
    Filtra expirations para a janela contínua 0 < DTE ≤ max_dte.
    Retorna lista de (expiration_str, dte_actual) ordenada por DTE crescente.
    Não deduplica — todas as expirações válidas são extraídas.
    """
    trade_dt = date.fromisoformat(trade_date)
    result = []
    for e in expirations:
        dte = (date.fromisoformat(e) - trade_dt).days
        if 0 < dte <= max_dte:
            result.append((e, dte))
    return sorted(result, key=lambda x: x[1])


# ─────────────────────────────────────────────────────────────────────────────
# CHAIN FETCH
# ─────────────────────────────────────────────────────────────────────────────

def fetch_chain_raw(
    session: requests.Session,
    trade_date: str,
    expiration: str,
) -> dict | None:
    """
    GET /v1/options/chain/{UNDERLYING}/?date={trade_date}&expiration={expiration}
    Retorna dict bruto ou None em erro / no_data.
    """
    url = f"{BASE_URL}/options/chain/{UNDERLYING}/"
    try:
        resp = tracked_get(
            session, url,
            params={"date": trade_date, "expiration": expiration},
            timeout=(10, 60),
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        print(f"  [WARN] chain falhou ({trade_date}/{expiration}): {exc}")
        return None

    if data.get("s") not in ("ok",):
        return None

    return data


def parse_chain(raw: dict, trade_date: str) -> pd.DataFrame:
    """
    Converte payload colunar da chain em DataFrame.
    Injeta trade_date (constante). Calcula dte_actual.
    Descarta colunas de baixo valor analítico.
    """
    payload = {k: v for k, v in raw.items() if k != "s" and isinstance(v, list)}
    df = pd.DataFrame(payload)
    if df.empty:
        return df

    df.rename(columns={
        "optionSymbol":    "option_symbol",
        "openInterest":    "open_interest",
        "bidSize":         "bid_size",
        "askSize":         "ask_size",
        "inTheMoney":      "in_the_money",
        "underlyingPrice": "underlying_price",
        "intrinsicValue":  "intrinsic_value",
        "extrinsicValue":  "extrinsic_value",
    }, inplace=True)

    # Timestamps: chain retorna strings com offset "2026-01-22 16:00:00 -05:00"
    for ts_col in ["expiration", "updated", "firstTraded"]:
        if ts_col in df.columns:
            df[ts_col] = pd.to_datetime(df[ts_col], utc=True)

    trade_dt = pd.Timestamp(trade_date, tz="UTC")
    df["trade_date"] = trade_dt

    if "expiration" in df.columns:
        df["dte_actual"] = (
            df["expiration"].dt.normalize() - trade_dt.normalize()
        ).dt.days.astype("int16")

    df["underlying"] = UNDERLYING

    # Descartar colunas auxiliares sem valor para o pipeline de ML
    drop_cols = [
        "firstTraded", "bid_size", "ask_size",
        "intrinsic_value", "extrinsic_value", "underlying_price",
        "rho", "iv", "delta", "gamma", "theta", "vega",
    ]
    df.drop(columns=[c for c in drop_cols if c in df.columns], inplace=True)

    return df


# ─────────────────────────────────────────────────────────────────────────────
# FILTRO ATM ±STRIKE_RADIUS
# ─────────────────────────────────────────────────────────────────────────────

def filter_atm_strikes(df: pd.DataFrame, spot: float, radius: int) -> pd.DataFrame:
    """
    Mantém ±radius posições de strike em relação ao ATM (medido por índice
    no array de strikes únicos ordenados — não por valor monetário).
    """
    if df.empty or spot <= 0:
        return df

    unique_strikes = sorted(df["strike"].unique())
    if not unique_strikes:
        return df

    atm_idx = min(range(len(unique_strikes)), key=lambda i: abs(unique_strikes[i] - spot))
    lo = max(0, atm_idx - radius)
    hi = min(len(unique_strikes), atm_idx + radius + 1)
    valid_strikes = set(unique_strikes[lo:hi])

    return df[df["strike"].isin(valid_strikes)].copy()


# ─────────────────────────────────────────────────────────────────────────────
# TIPAGEM FINAL
# ─────────────────────────────────────────────────────────────────────────────

def float32_safe(val: float) -> np.float32:
    return np.float32(val) if val is not None else np.float32("nan")


def apply_dtypes(df: pd.DataFrame, spot: float) -> pd.DataFrame:
    """
    Tipagem otimizada para ML. Injeta underlying_price do closes cache local.
    """
    df["underlying_price"] = float32_safe(spot)

    for col in ["underlying", "side"]:
        if col in df.columns:
            df[col] = df[col].astype("category")

    for col in ["bid", "ask", "mid", "last", "underlying_price"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("float32")

    for col in ["volume", "open_interest"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype("int32")

    if "dte_actual" in df.columns:
        df["dte_actual"] = df["dte_actual"].astype("int16")

    if "in_the_money" in df.columns:
        df["in_the_money"] = df["in_the_money"].astype(bool)

    if "strike" in df.columns:
        df["strike"] = pd.to_numeric(df["strike"], errors="coerce")

    sort_cols = [c for c in ["dte_actual", "side", "strike"] if c in df.columns]
    if sort_cols:
        df.sort_values(sort_cols, inplace=True, ignore_index=True)

    return df


# ─────────────────────────────────────────────────────────────────────────────
# SALVAR PARQUET (escrita atômica)
# ─────────────────────────────────────────────────────────────────────────────

def save_parquet(df: pd.DataFrame, trade_date: str) -> Path | None:
    """Escrita atômica .tmp → os.replace(). Nomenclatura: NDX_chain_YYYY-MM-DD.parquet"""
    if not Path("G:/").exists():
        sys.exit(
            "[ERRO FATAL] Google Drive não montado em G:/.\n"
            "             Verifique Google Drive for Desktop."
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    filename   = f"{UNDERLYING}_chain_{trade_date}.parquet"
    final_path = OUTPUT_DIR / filename
    tmp_path   = OUTPUT_DIR / (filename + ".tmp")

    try:
        df.to_parquet(tmp_path, engine="pyarrow", compression=COMPRESSION, index=False)
        os.replace(tmp_path, final_path)
    except Exception as exc:
        tmp_path.unlink(missing_ok=True)
        print(f"  [ERRO] Falha ao salvar parquet {trade_date}: {exc}")
        return None

    kb = final_path.stat().st_size / 1024
    print(f"  [OK] {final_path.name}  ({kb:.1f} KB)")
    return final_path


def parquet_exists(trade_date: str) -> bool:
    path = OUTPUT_DIR / f"{UNDERLYING}_chain_{trade_date}.parquet"
    return path.exists() and path.stat().st_size > 0


# ─────────────────────────────────────────────────────────────────────────────
# RELATÓRIO DE SESSÃO
# ─────────────────────────────────────────────────────────────────────────────

def print_session_report(days_done: int, days_skipped: int, days_total: int, t_start: float) -> None:
    w = 66
    elapsed = time.time() - t_start
    mins, secs = divmod(int(elapsed), 60)
    print()
    print(f"+{'=' * w}+")
    print(f"|{'MD STEP 2 — MASS EXTRACTOR':^{w}}|")
    print(f"|{'Prop Desk Quant | Janela 0–45 DTE | SESSÃO ENCERRADA':^{w}}|")
    print(f"+{'=' * w}+")
    print(f"|  Timestamp      : {datetime.now().strftime('%Y-%m-%d %H:%M:%S'):<{w-19}}|")
    print(f"|  Elapsed        : {mins}m {secs}s{' ' * (w - 19 - len(f'{mins}m {secs}s'))}|")
    print(f"|  Dias extraídos : {days_done:<{w-19}}|")
    print(f"|  Dias pulados   : {days_skipped} (já existiam){' ' * max(0, w-19-len(f'{days_skipped} (já existiam)'))}|")
    print(f"|  Dias restantes : {max(0, days_total - days_done - days_skipped):<{w-19}}|")
    print(f"|  {APICounter.status_line():<{w-2}}|")
    print(f"|  Output dir     : {OUTPUT_DIR!s:<{w-19}}|")
    print(f"+{'=' * w}+")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    t_start = time.time()

    print("\n" + "=" * 68)
    print("  MD STEP 2 — Mass Options Extractor (Janela Contínua 0–45 DTE)")
    print(f"  Prop Desk Quant | {UNDERLYING} | MAX_DTE={MAX_DTE} | ±{STRIKE_RADIUS} strikes ATM")
    print(f"  Range: {DATE_START} → {DATE_END}")
    print("=" * 68 + "\n")

    if not Path("G:/").exists():
        sys.exit("[ERRO FATAL] Google Drive não montado em G:/.")

    spot_cache   = load_spot_cache()
    trading_days = get_trading_days(spot_cache)
    session      = build_session()

    print(f"[INFO] Dias úteis no range  : {len(trading_days)}")
    print(f"[INFO] MAX_DTE              : {MAX_DTE} dias")
    print(f"[INFO] Strike radius (ATM)  : ±{STRIKE_RADIUS} posições")
    print(f"[INFO] API limit (watchdog) : {API_LIMIT:,} chamadas")
    print(f"[INFO] Output               : {OUTPUT_DIR}\n")

    days_done    = 0
    days_skipped = 0

    for trade_date in trading_days:

        # ── Watchdog: verificar cota antes de iniciar o dia ───────────────────
        if not APICounter.is_safe():
            print(
                f"\n[WATCHDOG] Limite de {API_LIMIT:,} chamadas atingido.\n"
                f"           Execute novamente amanhã para continuar.\n"
                f"           ({APICounter.status_line()})"
            )
            break

        # ── Idempotência ──────────────────────────────────────────────────────
        if parquet_exists(trade_date):
            days_skipped += 1
            continue

        spot = spot_cache.get(trade_date)
        if not spot or spot <= 0:
            print(f"[SKIP] {trade_date} — spot ausente no cache local.")
            continue

        print(f"\n{'─' * 60}")
        print(f"[DIA] {trade_date}  |  Spot: {spot:,.2f}  |  {APICounter.status_line()}")

        # ── Buscar e filtrar expirações ───────────────────────────────────────
        expirations = fetch_expirations(session, trade_date)   # +1 req
        if not expirations:
            print("  [SKIP] Sem expirações disponíveis.")
            continue

        valid_exps = get_valid_expirations(expirations, trade_date, MAX_DTE)
        if not valid_exps:
            print(f"  [SKIP] Nenhuma expiração no range 0–{MAX_DTE} DTE.")
            continue

        print(f"  Expirações válidas (0–{MAX_DTE} DTE): {len(valid_exps)}")

        # ── Chain por expiração + filtro ATM ─────────────────────────────────
        day_frames: list[pd.DataFrame] = []

        for expiration, dte_actual in valid_exps:

            if not APICounter.is_safe():
                print(f"  [WATCHDOG] Cota atingida durante loop de chains ({trade_date}).")
                break

            raw = fetch_chain_raw(session, trade_date, expiration)   # +1 req
            if raw is None:
                continue

            df_chain    = parse_chain(raw, trade_date)
            df_filtered = filter_atm_strikes(df_chain, spot, STRIKE_RADIUS)

            n_raw  = len(df_chain)
            n_filt = len(df_filtered)
            print(f"  DTE={dte_actual:>3}  {expiration}  →  {n_raw} → {n_filt} contratos")

            if not df_filtered.empty:
                day_frames.append(df_filtered)

        # ── Consolidar e salvar ───────────────────────────────────────────────
        if not day_frames:
            print(f"  [SKIP] Nenhum dado coletado para {trade_date}.")
            continue

        df_day = pd.concat(day_frames, ignore_index=True)
        df_day = apply_dtypes(df_day, spot)

        path = save_parquet(df_day, trade_date)
        if path:
            days_done += 1
            print(
                f"  [RESUMO] {len(df_day):,} registros  |  "
                f"{df_day['dte_actual'].nunique()} vencimentos  |  "
                f"{APICounter.status_line()}"
            )

    print_session_report(days_done, days_skipped, len(trading_days), t_start)


if __name__ == "__main__":
    main()
