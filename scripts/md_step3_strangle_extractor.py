"""
===============================================================================
 MD STEP 3 — Strangle Extractor (Market Data API)
 Prop Desk Quant | SPX / RUT | 42-DTE Short Strangle Backtest Data
===============================================================================
 Objetivo: Extrair chain de opções com cobertura suficiente para selecionar
 strikes de 16-delta em estruturas ~42 DTE (Short Strangle).

 Diferenças em relação ao Step 2:
   - STRIKE_RADIUS = 100 posições (era 30) — captura puts 16-delta a 42 DTE
   - MAX_DTE       = 55              (era 45) — buffer para encontrar ~42 DTE
   - Spot source   : yfinance (spot correto por ativo — corrige bug do Step 2)
   - FORCE_OVERWRITE = True — sobrescreve arquivos existentes (re-extração SPX)

 Configuração:
   UNDERLYING = "RUT"   → extrai RUT (novo)
   UNDERLYING = "SPX"   → re-extrai SPX com strike radius correto

 Custo estimado de API:
   ~252 dias × ~9 req/dia = ~2.268 req  (cabe em 1 sessão — plano 100k/dia)

 INPUT:  nenhum (spot via yfinance, trading days derivados do próprio yfinance)
 OUTPUT: G:/Meu Drive/Quant_Data_MD/{UNDERLYING}_chain_YYYY-MM-DD.parquet
===============================================================================
"""

from __future__ import annotations

import os
import sys
import time
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import requests

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURAÇÃO — EDITAR AQUI
# ─────────────────────────────────────────────────────────────────────────────

UNDERLYING       = sys.argv[1].upper() if len(sys.argv) > 1 else "RUT"  # passa como argumento: python script.py RUT  ou  python script.py SPX
# --resume: pula dias que já têm parquet (retomada após interrupção)
_RESUME_MODE     = "--resume" in sys.argv
# --start-date YYYY-MM-DD: sobrescreve DATE_START via linha de comando
_start_date_arg  = next((sys.argv[i+1] for i, a in enumerate(sys.argv) if a == "--start-date" and i+1 < len(sys.argv)), None)
DATE_START       = _start_date_arg if _start_date_arg else "2025-04-05"   # início da janela histórica
DATE_END         = "2026-04-10"   # fim da janela (data de hoje)

MAX_DTE          = 55             # captura todas as expirações com DTE ≤ 55
STRIKE_RADIUS    = 100            # ±100 posições de strike em relação ao ATM
FORCE_OVERWRITE  = not _RESUME_MODE  # --resume → False (pula dias existentes)

API_KEY          = "aTUxSkNONm5PZ0tYLS1zN1JMSXpXVGhGM0lNd1Jra2g2UDJuVWtwMnFpYz0"
BASE_URL         = "https://api.marketdata.app/v1"

OUTPUT_DIR       = Path("G:/Meu Drive/Quant_Data_MD")
COMPRESSION      = "zstd"

API_LIMIT        = 95_000         # watchdog: para a 5% antes do limite
RATE_SLEEP       = 0.12           # ~8 req/s — margem de segurança

# Ticker yfinance por underlying (fallback)
YFINANCE_TICKER  = {
    "SPX": "^GSPC",
    "RUT": "^RUT",
    "NDX": "^NDX",
}

# Ticker Stooq por underlying (fonte primária — gratuita, sem rate limit)
STOOQ_TICKER     = {
    "SPX": "^spx",
    "RUT": "^rut",
    "NDX": "^ndx",
}


# ─────────────────────────────────────────────────────────────────────────────
# WATCHDOG — CONTADOR GLOBAL
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
    APICounter.increment()
    resp = session.get(url, **kwargs)
    time.sleep(RATE_SLEEP)
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# SPOT CACHE — VIA YFINANCE (fallback quando API não retorna underlyingPrice)
# ─────────────────────────────────────────────────────────────────────────────

def build_spot_cache() -> dict[str, float]:
    """
    Baixa o histórico de closes via yfinance para o ativo configurado.
    Usado como fallback quando a chain API não retorna underlyingPrice.
    Retorna dict {YYYY-MM-DD: close_price} ou {} em caso de falha.
    """
    ticker_sym = YFINANCE_TICKER.get(UNDERLYING)
    if not ticker_sym:
        print(f"[SPOT CACHE] Nenhum ticker yfinance definido para {UNDERLYING}. Fallback desativado.")
        return {}
    try:
        import yfinance as yf
        tk = yf.Ticker(ticker_sym)
        hist = tk.history(start=DATE_START, end=DATE_END, auto_adjust=True)
        if hist.empty:
            print(f"[SPOT CACHE] yfinance retornou vazio para {ticker_sym}.")
            return {}
        hist.index = hist.index.normalize().tz_localize(None)
        cache = {dt.strftime("%Y-%m-%d"): float(row["Close"]) for dt, row in hist.iterrows()}
        print(f"[SPOT CACHE] yfinance OK — {len(cache)} closes para {ticker_sym}")
        return cache
    except Exception as exc:
        print(f"[SPOT CACHE] yfinance falhou ({exc}). Fallback desativado.")
        return {}


def build_trading_days() -> list[str]:
    """
    Gera lista de dias úteis via pd.bdate_range (sem API externa).
    Feriados americanos incluídos são automaticamente descartados pelo loop
    principal (API retorna expirations vazia → skip).
    """
    dates = pd.bdate_range(start=DATE_START, end=DATE_END, freq="B")
    result = [d.strftime("%Y-%m-%d") for d in dates]
    print(f"[INFO] Dias úteis no range  : {len(result)} (bdate_range)")
    return result


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
# EXPIRATIONS
# ─────────────────────────────────────────────────────────────────────────────

def wait_for_connectivity(check_url: str = "https://api.marketdata.app", interval: int = 30) -> None:
    """Bloqueia até a conexão com a API ser restabelecida."""
    print(f"\n[NETWORK] Conexão perdida. Aguardando reconexão (verificando a cada {interval}s)...")
    attempt = 0
    while True:
        attempt += 1
        try:
            requests.get(check_url, timeout=5)
            print(f"[NETWORK] Conexão restabelecida após {attempt * interval}s. Retomando...\n")
            return
        except Exception:
            print(f"[NETWORK] Sem conexão... ({attempt * interval}s aguardados)")
            time.sleep(interval)


def _is_network_error(exc: Exception) -> bool:
    msg = str(exc)
    return "NameResolutionError" in msg or "getaddrinfo failed" in msg or "Failed to resolve" in msg


def fetch_expirations(session: requests.Session, trade_date: str) -> list[str]:
    url = f"{BASE_URL}/options/expirations/{UNDERLYING}/"
    while True:
        try:
            resp = tracked_get(session, url, params={"date": trade_date}, timeout=(10, 30))
            resp.raise_for_status()
            data = resp.json()
            break
        except Exception as exc:
            if _is_network_error(exc):
                wait_for_connectivity()
                continue  # retry após reconexão sem contar como falha
            print(f"  [WARN] expirations falhou em {trade_date}: {exc}")
            return []
    if data.get("s") != "ok":
        return []
    return data.get("expirations", [])


def get_valid_expirations(
    expirations: list[str],
    trade_date: str,
    max_dte: int,
) -> list[tuple[str, int]]:
    trade_dt = date.fromisoformat(trade_date)
    result = []
    for e in expirations:
        dte = (date.fromisoformat(e) - trade_dt).days
        if 0 < dte <= max_dte:
            result.append((e, dte))
    return sorted(result, key=lambda x: x[1])


# ─────────────────────────────────────────────────────────────────────────────
# CHAIN FETCH + PARSE
# ─────────────────────────────────────────────────────────────────────────────

def fetch_chain_raw(
    session: requests.Session,
    trade_date: str,
    expiration: str,
) -> dict | None:
    url = f"{BASE_URL}/options/chain/{UNDERLYING}/"
    while True:
        try:
            resp = tracked_get(
                session, url,
                params={"date": trade_date, "expiration": expiration},
                timeout=(10, 60),
            )
            resp.raise_for_status()
            data = resp.json()
            break
        except Exception as exc:
            if _is_network_error(exc):
                wait_for_connectivity()
                continue  # retry após reconexão
            print(f"  [WARN] chain falhou ({trade_date}/{expiration}): {exc}")
            return None
    if data.get("s") not in ("ok",):
        return None
    return data


def parse_chain(raw: dict, trade_date: str) -> pd.DataFrame:
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
        "underlyingPrice": "underlying_price_api",  # guardamos separado para debug
        "intrinsicValue":  "intrinsic_value",
        "extrinsicValue":  "extrinsic_value",
    }, inplace=True)

    # Timestamps
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

    # Descartar colunas de baixo valor analítico
    drop_cols = [
        "firstTraded", "bid_size", "ask_size",
        "intrinsic_value", "extrinsic_value", "underlying_price_api",
        "rho", "iv", "delta", "gamma", "theta", "vega",
    ]
    df.drop(columns=[c for c in drop_cols if c in df.columns], inplace=True)

    return df


# ─────────────────────────────────────────────────────────────────────────────
# FILTRO DE STRIKES — ±STRIKE_RADIUS posições em relação ao ATM
# ─────────────────────────────────────────────────────────────────────────────

def filter_atm_strikes(df: pd.DataFrame, spot: float, radius: int) -> pd.DataFrame:
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
# TIPAGEM FINAL + INJEÇÃO DE SPOT CORRETO
# ─────────────────────────────────────────────────────────────────────────────

def float32_safe(val: float) -> np.float32:
    return np.float32(val) if val is not None else np.float32("nan")


def apply_dtypes(df: pd.DataFrame, spot: float) -> pd.DataFrame:
    # Injeta underlying_price do yfinance (spot correto por ativo)
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
# SALVAR PARQUET (escrita atômica via pyarrow)
# ─────────────────────────────────────────────────────────────────────────────

def save_parquet(df: pd.DataFrame, trade_date: str) -> Path | None:
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
    print(f"|{'MD STEP 3 — STRANGLE EXTRACTOR':^{w}}|")
    print(f"|{f'Prop Desk Quant | {UNDERLYING} | MAX_DTE={MAX_DTE} | RADIUS={STRIKE_RADIUS}':^{w}}|")
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
    print(f"  MD STEP 3 — Strangle Extractor | {UNDERLYING}")
    print(f"  MAX_DTE={MAX_DTE} | STRIKE_RADIUS=±{STRIKE_RADIUS} | FORCE_OVERWRITE={FORCE_OVERWRITE}")
    print(f"  Range: {DATE_START} → {DATE_END}")
    print("=" * 68 + "\n")

    if not Path("G:/").exists():
        sys.exit("[ERRO FATAL] Google Drive não montado em G:/.\n"
                 "             Verifique Google Drive for Desktop.")

    trading_days = build_trading_days()
    spot_cache   = build_spot_cache()
    session      = build_session()
    print(f"[INFO] MAX_DTE              : {MAX_DTE} dias")
    print(f"[INFO] Strike radius        : ±{STRIKE_RADIUS} posições")
    print(f"[INFO] Force overwrite      : {FORCE_OVERWRITE}")
    print(f"[INFO] API limit (watchdog) : {API_LIMIT:,} chamadas")
    print(f"[INFO] Output               : {OUTPUT_DIR}\n")

    days_done    = 0
    days_skipped = 0

    for trade_date in trading_days:

        if not APICounter.is_safe():
            print(
                f"\n[WATCHDOG] Limite de {API_LIMIT:,} chamadas atingido.\n"
                f"           Execute novamente para continuar.\n"
                f"           ({APICounter.status_line()})"
            )
            break

        # Idempotência (respeitada apenas se FORCE_OVERWRITE=False)
        if not FORCE_OVERWRITE and parquet_exists(trade_date):
            days_skipped += 1
            continue

        spot: float | None = spot_cache.get(trade_date)  # pré-carregado via yfinance

        print(f"\n{'─' * 60}")
        print(f"[DIA] {trade_date}  |  {APICounter.status_line()}")

        expirations = fetch_expirations(session, trade_date)
        if not expirations:
            print("  [SKIP] Sem expirações disponíveis.")
            continue

        valid_exps = get_valid_expirations(expirations, trade_date, MAX_DTE)
        if not valid_exps:
            print(f"  [SKIP] Nenhuma expiração no range 0–{MAX_DTE} DTE.")
            continue

        src = "yfinance" if trade_date in spot_cache else "API"
        print(f"  [SPOT] {spot:,.2f} ({src})" if spot else "  [SPOT] desconhecido")
        print(f"  Expirações válidas (0–{MAX_DTE} DTE): {len(valid_exps)}")

        day_frames: list[pd.DataFrame] = []

        for expiration, dte_actual in valid_exps:

            if not APICounter.is_safe():
                print(f"  [WATCHDOG] Cota atingida durante chains ({trade_date}).")
                break

            raw = fetch_chain_raw(session, trade_date, expiration)
            if raw is None:
                continue

            # Refina spot com underlyingPrice da API, se disponível e válido
            prices = raw.get("underlyingPrice") or []
            if prices:
                try:
                    api_spot = float(prices[0])
                    if api_spot > 0:
                        spot = api_spot
                except (TypeError, ValueError):
                    pass

            df_chain    = parse_chain(raw, trade_date)
            df_filtered = filter_atm_strikes(df_chain, spot or 0.0, STRIKE_RADIUS)

            n_raw  = len(df_chain)
            n_filt = len(df_filtered)
            print(f"  DTE={dte_actual:>3}  {expiration}  →  {n_raw} → {n_filt} contratos")

            if not df_filtered.empty:
                day_frames.append(df_filtered)

        if not day_frames:
            print(f"  [SKIP] Nenhum dado coletado para {trade_date}.")
            continue

        df_day = pd.concat(day_frames, ignore_index=True)
        df_day = apply_dtypes(df_day, spot or 0.0)

        saved = save_parquet(df_day, trade_date)
        if saved:
            days_done += 1

    print_session_report(days_done, days_skipped, len(trading_days), t_start)


if __name__ == "__main__":
    main()
