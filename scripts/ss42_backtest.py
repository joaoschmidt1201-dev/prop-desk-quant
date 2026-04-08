"""
===============================================================================
 SS42 BACKTEST — Short Strangle 42 DTE
 Prop Desk Quant | SPX / RUT
===============================================================================
 Estratégia : Short Strangle (Venda de Put OTM + Venda de Call OTM)
 Entrada    : Primeira sexta-feira do mês (~42 DTE)
              Se sexta for feriado → usa quinta-feira
 Expiração  : Sexta-feira mais próxima de 42 DTE no chain
              Se sexta for feriado → usa quinta-feira
 Strikes    : Mais próximo de 16-delta (calculado via Black-Scholes)
 Pricing    : MID price
 Checkpoint : Mark-to-market em ~21 DTE (padrão TastyTrade)
 Saída      : Na expiração (exercício europeu, cash-settled)
 Multiplier : $100/ponto (SPX e RUT)

 USO:
     python scripts/ss42_backtest.py SPX
     python scripts/ss42_backtest.py RUT

 OUTPUT:
     reports/ss42_backtest/SS42_{UNDERLYING}_{start}_{end}.csv
===============================================================================
"""

from __future__ import annotations

import calendar
import gc
import logging
import math
import sys
import warnings
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.stats import norm

warnings.filterwarnings("ignore")


# ─────────────────────────────────────────────────────────────────────────────
# PARÂMETROS
# ─────────────────────────────────────────────────────────────────────────────

UNDERLYING    = sys.argv[1].upper() if len(sys.argv) > 1 else "SPX"
MULTIPLIER    = 100          # $100/ponto (SPX e RUT)
TARGET_DTE    = 42           # DTE alvo na entrada
CHECKPOINT_DTE = 21          # DTE do checkpoint (padrão TastyTrade)
TARGET_DELTA  = 0.16         # Delta alvo dos strikes
RISK_FREE_RATE = 0.045       # Taxa livre de risco (anualizada)
MIN_BID       = 0.05         # Bid mínimo para considerar opção líquida
IV_LOWER      = 1e-6
IV_UPPER      = 20.0

DATA_DIR      = Path("G:/Meu Drive/Quant_Data_MD")
OUTPUT_DIR    = Path(__file__).resolve().parent.parent / "reports" / "ss42_backtest"

CHAIN_COLS    = ["side", "strike", "dte", "dte_actual",
                 "bid", "mid", "ask", "open_interest", "underlying_price"]


# ─────────────────────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────────────────────

log = logging.getLogger("ss42_backtest")
log.setLevel(logging.INFO)
_fmt = logging.Formatter("%(asctime)s [%(levelname)-7s] %(message)s",
                         datefmt="%Y-%m-%d %H:%M:%S")
_sh = logging.StreamHandler()
_sh.setFormatter(_fmt)
log.addHandler(_sh)


def _attach_file_handler():
    fh = logging.FileHandler(OUTPUT_DIR / "backtest.log", mode="w", encoding="utf-8")
    fh.setFormatter(_fmt)
    log.addHandler(fh)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION A — DATA LAYER
# ─────────────────────────────────────────────────────────────────────────────

def get_available_dates() -> set[date]:
    """Retorna conjunto de datas com parquet disponível para o underlying."""
    dates: set[date] = set()
    for f in DATA_DIR.glob(f"{UNDERLYING}_chain_*.parquet"):
        ds = f.stem.replace(f"{UNDERLYING}_chain_", "")
        try:
            dates.add(date.fromisoformat(ds))
        except ValueError:
            pass
    return dates


def load_chain(trade_date: date) -> pd.DataFrame | None:
    """Carrega o parquet de um dia específico. Retorna None se ausente."""
    path = DATA_DIR / f"{UNDERLYING}_chain_{trade_date.isoformat()}.parquet"
    if not path.exists():
        return None
    try:
        cols = [c for c in CHAIN_COLS if c != "dte_actual"]
        try:
            df = pd.read_parquet(path, columns=CHAIN_COLS)
        except Exception:
            df = pd.read_parquet(path, columns=cols)
            df["dte_actual"] = df["dte"]

        df["strike"]           = df["strike"].astype("float64")
        df["underlying_price"] = df["underlying_price"].astype("float64")
        df["mid"]              = df["mid"].astype("float64")
        df["bid"]              = df["bid"].astype("float64")
        df["ask"]              = df["ask"].astype("float64")
        return df
    except Exception as exc:
        log.warning(f"Erro ao carregar {path.name}: {exc}")
        return None


def first_friday_of_month(year: int, month: int) -> date:
    """Retorna a primeira sexta-feira do mês."""
    cal = calendar.monthcalendar(year, month)
    for week in cal:
        if week[calendar.FRIDAY] != 0:
            return date(year, month, week[calendar.FRIDAY])
    raise ValueError(f"Sem sexta em {year}-{month}")


def discover_entry_dates(available: set[date]) -> list[date]:
    """
    Para cada mês no range disponível, encontra a data de entrada:
      1. Primeira sexta do mês (se tiver parquet)
      2. Quinta anterior (se sexta for feriado)
    """
    months = sorted({(d.year, d.month) for d in available})
    entries: list[date] = []
    for year, month in months:
        friday = first_friday_of_month(year, month)
        if friday in available:
            entries.append(friday)
        elif (friday - timedelta(days=1)) in available:
            entries.append(friday - timedelta(days=1))
        # Se nenhum → skip (semana inteira sem dados)
    return entries


def find_target_expiration(chain: pd.DataFrame, entry_date: date) -> tuple[date | None, int]:
    """
    Encontra a expiração mais próxima de TARGET_DTE no chain.
    Retorna (exp_date, dte_real). exp_date é derivada de entry_date + dte.
    """
    available_dtes = sorted(chain["dte"].dropna().unique())
    # Janela primária: 35–52 DTE
    candidates = [d for d in available_dtes if 35 <= d <= 52]
    if not candidates:
        candidates = [d for d in available_dtes if 25 <= d <= 60]
    if not candidates:
        return None, 0

    best_dte = int(min(candidates, key=lambda x: abs(x - TARGET_DTE)))
    exp_date = entry_date + timedelta(days=best_dte)

    # Se a expiração cair num sábado, recua para sexta
    if exp_date.weekday() == 5:
        exp_date -= timedelta(days=1)

    return exp_date, best_dte


def find_checkpoint_date(exp_date: date, available: set[date]) -> date | None:
    """
    Encontra a data de trading mais próxima de (exp_date - CHECKPOINT_DTE dias).
    Tenta ±3 dias úteis.
    """
    target = exp_date - timedelta(days=CHECKPOINT_DTE)
    for offset in range(0, 4):
        for delta in [0, -1, 1, -2, 2, -3, 3]:
            candidate = target + timedelta(days=delta + offset)
            if candidate in available and candidate < exp_date:
                return candidate
    return None


# ─────────────────────────────────────────────────────────────────────────────
# SECTION B — BLACK-SCHOLES IV + DELTA
# ─────────────────────────────────────────────────────────────────────────────

def _bs_price(S: float, K: float, T: float, r: float,
              sigma: float, opt_type: str) -> float:
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return float("nan")
    sq = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / sq
    d2 = d1 - sq
    if opt_type == "call":
        return S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
    return K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def _bs_iv(market_price: float, S: float, K: float, T: float,
           r: float, opt_type: str) -> float | None:
    if T <= 0 or S <= 0 or K <= 0 or market_price <= 0:
        return None
    intrinsic = max(0.0, (S - K) if opt_type == "call" else (K - S))
    if market_price < intrinsic - 1e-3:
        return None
    obj = lambda sig: _bs_price(S, K, T, r, sig, opt_type) - market_price
    try:
        f_lo, f_hi = obj(IV_LOWER), obj(IV_UPPER)
        if f_lo * f_hi > 0:
            return None
        iv = brentq(obj, IV_LOWER, IV_UPPER, xtol=1e-8, maxiter=200)
        return float(iv) if 0 < iv < IV_UPPER else None
    except Exception:
        return None


def _bs_delta(S: float, K: float, T: float, r: float,
              sigma: float, opt_type: str) -> float:
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return float("nan")
    sq = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / sq
    if opt_type == "call":
        return float(norm.cdf(d1))
    return float(norm.cdf(d1) - 1)  # delta da put (negativo)


def calc_iv_atm(chain: pd.DataFrame, spot: float, dte: int) -> float | None:
    """Calcula IV ATM como média entre call e put ATM no DTE alvo."""
    T = dte / 365.0
    opts = chain[chain["dte"] == dte].copy()
    if opts.empty:
        return None

    all_strikes = opts["strike"].unique()
    atm_k = float(min(all_strikes, key=lambda k: abs(k - spot)))

    ivs = []
    for side in ("call", "put"):
        row = opts[(opts["side"] == side) & (opts["strike"] == atm_k)]
        if row.empty:
            continue
        mid = float(row["mid"].iloc[0])
        if mid <= 0:
            continue
        iv = _bs_iv(mid, spot, atm_k, T, RISK_FREE_RATE, side)
        if iv is not None:
            ivs.append(iv)

    return float(np.mean(ivs)) if ivs else None


# ─────────────────────────────────────────────────────────────────────────────
# SECTION C — SELEÇÃO DE STRIKES (16-DELTA)
# ─────────────────────────────────────────────────────────────────────────────

def select_16delta_strikes(
    chain: pd.DataFrame,
    spot: float,
    target_dte: int,
) -> dict | None:
    """
    Filtra o chain para o DTE alvo e seleciona o strike de put e call
    mais próximo de TARGET_DELTA (16-delta).

    Para cada candidato OTM:
      1. Inverter BS para obter IV implícita via mid price
      2. Calcular delta com essa IV
      3. Selecionar o que minimiza |delta| - TARGET_DELTA

    Retorna dict com strikes, deltas, mids e crédito total.
    Retorna None se não conseguir selecionar ambos os lados.
    """
    T = target_dte / 365.0

    opts = chain[chain["dte"] == target_dte].copy()

    # Fallback: aceita ±2 DTE se o alvo exato não tiver dados suficientes
    if opts.empty or len(opts) < 5:
        nearby = chain[chain["dte"].between(target_dte - 2, target_dte + 2)].copy()
        if not nearby.empty:
            best_dte = int(nearby["dte"].value_counts().index[0])
            opts = nearby[nearby["dte"] == best_dte].copy()
            T = best_dte / 365.0

    if opts.empty:
        return None

    # ── PUTS ────────────────────────────────────────────────────────────────
    puts = opts[(opts["side"] == "put") & (opts["strike"] < spot) &
                (opts["bid"] >= MIN_BID)].copy()
    puts = (puts.sort_values("open_interest", ascending=False)
                .drop_duplicates("strike")
                .sort_values("strike"))

    best_put_strike = None
    best_put_delta  = None
    best_put_mid    = None
    best_put_dist   = float("inf")

    for _, row in puts.iterrows():
        K   = float(row["strike"])
        mid = float(row["mid"])
        if mid <= 0:
            continue
        iv = _bs_iv(mid, spot, K, T, RISK_FREE_RATE, "put")
        if iv is None:
            continue
        delta = _bs_delta(spot, K, T, RISK_FREE_RATE, iv, "put")
        abs_delta = abs(delta)
        dist = abs(abs_delta - TARGET_DELTA)
        if dist < best_put_dist:
            best_put_strike = K
            best_put_delta  = delta
            best_put_mid    = mid
            best_put_dist   = dist

    # ── CALLS ───────────────────────────────────────────────────────────────
    calls = opts[(opts["side"] == "call") & (opts["strike"] > spot) &
                 (opts["bid"] >= MIN_BID)].copy()
    calls = (calls.sort_values("open_interest", ascending=False)
                  .drop_duplicates("strike")
                  .sort_values("strike"))

    best_call_strike = None
    best_call_delta  = None
    best_call_mid    = None
    best_call_dist   = float("inf")

    for _, row in calls.iterrows():
        K   = float(row["strike"])
        mid = float(row["mid"])
        if mid <= 0:
            continue
        iv = _bs_iv(mid, spot, K, T, RISK_FREE_RATE, "call")
        if iv is None:
            continue
        delta = _bs_delta(spot, K, T, RISK_FREE_RATE, iv, "call")
        dist = abs(delta - TARGET_DELTA)
        if dist < best_call_dist:
            best_call_strike = K
            best_call_delta  = delta
            best_call_mid    = mid
            best_call_dist   = dist

    if best_put_strike is None or best_call_strike is None:
        return None

    total_credit = best_put_mid + best_call_mid

    return dict(
        short_put       = best_put_strike,
        short_call      = best_call_strike,
        delta_put       = round(best_put_delta,  4),
        delta_call      = round(best_call_delta, 4),
        mid_put_entry   = round(best_put_mid,    4),
        mid_call_entry  = round(best_call_mid,   4),
        total_credit    = round(total_credit,    4),
    )


# ─────────────────────────────────────────────────────────────────────────────
# SECTION D — P&L ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def get_checkpoint_mark(
    chain_ckpt: pd.DataFrame,
    short_put: float,
    short_call: float,
    total_credit: float,
    exp_date: date,
    ckpt_date: date,
) -> dict:
    """
    Busca os mid prices das pernas abertas no checkpoint (~21 DTE).
    Retorna dict com PnL mark-to-market. Retorna NaN nos campos se não achar.
    """
    ckpt_dte_exact = (exp_date - ckpt_date).days

    # Filtrar pelo DTE da nossa expiração (±3 dias de tolerância)
    mask_dte = chain_ckpt["dte"].between(ckpt_dte_exact - 3, ckpt_dte_exact + 3)

    def get_mid(side: str, strike: float) -> float | None:
        rows = chain_ckpt[mask_dte & (chain_ckpt["side"] == side) &
                          (chain_ckpt["strike"] == strike)]
        if rows.empty:
            return None
        v = float(rows["mid"].iloc[0])
        return v if v > 0 else None

    mid_put  = get_mid("put",  short_put)
    mid_call = get_mid("call", short_call)

    if mid_put is None or mid_call is None:
        return dict(
            mid_put_21dte  = float("nan"),
            mid_call_21dte = float("nan"),
            pnl_pts_21dte  = float("nan"),
            pnl_usd_21dte  = float("nan"),
        )

    close_cost   = mid_put + mid_call
    pnl_pts      = total_credit - close_cost
    pnl_usd      = pnl_pts * MULTIPLIER
    spot_ckpt    = float(chain_ckpt["underlying_price"].median())

    return dict(
        spot_21dte     = round(spot_ckpt, 2),
        mid_put_21dte  = round(mid_put,   4),
        mid_call_21dte = round(mid_call,  4),
        pnl_pts_21dte  = round(pnl_pts,   4),
        pnl_usd_21dte  = round(pnl_usd,   2),
    )


def calc_pnl_expiration(
    short_put: float,
    short_call: float,
    total_credit: float,
    spot_exit: float,
) -> dict:
    """
    P&L na expiração via exercício europeu (valor intrínseco).
    put_cost  = max(0, K_put  - spot)
    call_cost = max(0, spot   - K_call)
    pnl       = credit - put_cost - call_cost
    """
    put_cost  = max(0.0, short_put  - spot_exit)
    call_cost = max(0.0, spot_exit  - short_call)
    pnl_pts   = total_credit - put_cost - call_cost
    pnl_usd   = pnl_pts * MULTIPLIER
    in_range  = (short_put <= spot_exit <= short_call)
    result    = "WIN" if pnl_pts > 0 else "LOSS"

    return dict(
        spot_exit    = round(spot_exit, 2),
        put_cost_exp = round(put_cost,  4),
        call_cost_exp= round(call_cost, 4),
        pnl_points   = round(pnl_pts,   4),
        pnl_usd      = round(pnl_usd,   2),
        in_range     = in_range,
        result       = result,
    )


def compute_daily_mtm(
    entry_date:   date,
    exp_date:     date,
    short_put:    float,
    short_call:   float,
    entry_credit: float,
    available:    set[date],
) -> list[dict]:
    """
    Computes mark-to-market P&L for every available trading day of a strangle.
    Uses actual mid prices from parquets (±1 DTE tolerance).
    On expiration day, uses European intrinsic value.
    """
    records: list[dict] = []
    sp_int = int(short_put)
    sc_int = int(short_call)

    current = entry_date
    while current <= exp_date:
        if current not in available:
            current += timedelta(days=1)
            continue

        chain = load_chain(current)
        if chain is None:
            current += timedelta(days=1)
            continue

        dte_rem = (exp_date - current).days
        spot    = float(chain["underlying_price"].median())

        if dte_rem == 0:
            # Expiration: intrinsic value (European exercise)
            put_mid  = max(0.0, short_put  - spot)
            call_mid = max(0.0, spot       - short_call)
        else:
            mask_dte = chain["dte"].between(dte_rem - 1, dte_rem + 1)

            def _get_mid(side: str, strike: int) -> float | None:
                rows = chain[mask_dte & (chain["side"] == side) & (chain["strike"] == strike)]
                if rows.empty:
                    return None
                v = float(rows["mid"].iloc[0])
                return v if v >= 0 else None

            put_mid  = _get_mid("put",  sp_int)
            call_mid = _get_mid("call", sc_int)

            if put_mid is None or call_mid is None:
                current += timedelta(days=1)
                continue

        close_cost = put_mid + call_mid
        pnl_usd    = round((entry_credit - close_cost) * MULTIPLIER, 2)

        records.append(dict(
            trade_date    = entry_date,
            calendar_date = current,
            dte_remaining = dte_rem,
            spot          = round(spot,      2),
            put_mid       = round(float(put_mid),  4),
            call_mid      = round(float(call_mid), 4),
            pnl_usd       = pnl_usd,
        ))

        del chain
        gc.collect()
        current += timedelta(days=1)

    return records


# ─────────────────────────────────────────────────────────────────────────────
# SECTION E — LOOP PRINCIPAL DO BACKTEST
# ─────────────────────────────────────────────────────────────────────────────

def run_backtest() -> tuple[pd.DataFrame, pd.DataFrame]:
    available = get_available_dates()
    if not available:
        log.error(f"Nenhum parquet encontrado para {UNDERLYING} em {DATA_DIR}")
        return pd.DataFrame(), pd.DataFrame()

    entry_dates = discover_entry_dates(available)
    log.info(f"Datas de entrada encontradas: {len(entry_dates)}")

    records:       list[dict] = []
    daily_records: list[dict] = []
    skipped = 0

    for entry_date in entry_dates:
        chain_entry = None
        chain_ckpt  = None
        chain_exp   = None

        try:
            # ── ENTRADA ──────────────────────────────────────────────────────
            chain_entry = load_chain(entry_date)
            if chain_entry is None:
                log.warning(f"[SKIP] Sem parquet para entrada: {entry_date}")
                skipped += 1
                continue

            spot = float(chain_entry["underlying_price"].median())
            if spot <= 0:
                log.warning(f"[SKIP] Spot inválido ({spot}) em {entry_date}")
                skipped += 1
                continue

            # ── EXPIRAÇÃO ALVO ────────────────────────────────────────────────
            exp_date, dte_entry = find_target_expiration(chain_entry, entry_date)
            if exp_date is None:
                log.warning(f"[SKIP] Sem expiração ~42 DTE em {entry_date}")
                skipped += 1
                continue

            # ── SELEÇÃO DE STRIKES 16-DELTA ──────────────────────────────────
            strikes = select_16delta_strikes(chain_entry, spot, dte_entry)
            if strikes is None:
                log.warning(f"[SKIP] Não foi possível selecionar strikes em {entry_date}")
                skipped += 1
                continue

            iv_atm = calc_iv_atm(chain_entry, spot, dte_entry)

            # ── CHECKPOINT (~21 DTE) ──────────────────────────────────────────
            ckpt_date = find_checkpoint_date(exp_date, available)
            ckpt_data: dict = {}

            if ckpt_date is not None:
                chain_ckpt = load_chain(ckpt_date)
                if chain_ckpt is not None:
                    spot_ckpt = float(chain_ckpt["underlying_price"].median())
                    ckpt_data = get_checkpoint_mark(
                        chain_ckpt,
                        strikes["short_put"],
                        strikes["short_call"],
                        strikes["total_credit"],
                        exp_date,
                        ckpt_date,
                    )

            ckpt_data.setdefault("checkpoint_date", ckpt_date)
            ckpt_data.setdefault("spot_21dte",     float("nan"))
            ckpt_data.setdefault("mid_put_21dte",  float("nan"))
            ckpt_data.setdefault("mid_call_21dte", float("nan"))
            ckpt_data.setdefault("pnl_pts_21dte",  float("nan"))
            ckpt_data.setdefault("pnl_usd_21dte",  float("nan"))
            ckpt_data["checkpoint_date"] = ckpt_date

            # ── SAÍDA (EXPIRAÇÃO) ─────────────────────────────────────────────
            # Tenta carregar o parquet da expiração (ou ±1 dia para feriados)
            spot_exit   = float("nan")
            exit_method = "missing"
            for offset in [0, -1, 1]:
                exp_try = exp_date + timedelta(days=offset)
                chain_exp = load_chain(exp_try)
                if chain_exp is not None:
                    spot_exit   = float(chain_exp["underlying_price"].median())
                    exit_method = "market" if offset == 0 else f"fallback+{offset:+d}d"
                    break

            if math.isnan(spot_exit) or spot_exit <= 0:
                # Último recurso: usar spot de entrada (trade sem dados de saída)
                log.warning(f"[WARN] Sem parquet de expiração {exp_date}. Usando spot_entry.")
                spot_exit   = spot
                exit_method = "fallback_entry"

            pnl_rec = calc_pnl_expiration(
                strikes["short_put"],
                strikes["short_call"],
                strikes["total_credit"],
                spot_exit,
            )

            record = dict(
                trade_date   = entry_date,
                exp_date     = exp_date,
                underlying   = UNDERLYING,
                dte_entry    = dte_entry,
                spot_entry   = round(spot, 2),
                iv_atm_entry = round(iv_atm, 6) if iv_atm else float("nan"),
                iv_atm_pct   = round(iv_atm * 100, 2) if iv_atm else float("nan"),
                exit_method  = exit_method,
                **strikes,
                **ckpt_data,
                **pnl_rec,
            )
            records.append(record)

            # ── DAILY MTM ────────────────────────────────────────────────────
            daily_records.extend(compute_daily_mtm(
                entry_date,
                exp_date,
                strikes["short_put"],
                strikes["short_call"],
                strikes["total_credit"],
                available,
            ))

            log.info(
                f"{entry_date} -> {exp_date} ({dte_entry}DTE) | "
                f"Spot:{spot:>7.0f} | "
                f"Put:{strikes['short_put']:>6.0f}(d={strikes['delta_put']:+.2f}) "
                f"Call:{strikes['short_call']:>6.0f}(d={strikes['delta_call']:+.2f}) | "
                f"Cred:{strikes['total_credit']:>6.2f}pts | "
                f"Ckpt21:{ckpt_data.get('pnl_usd_21dte', float('nan')):>+8.0f}$ | "
                f"Exit:{spot_exit:>7.0f} | "
                f"PnL:{pnl_rec['pnl_points']:>+7.2f}pts "
                f"(${pnl_rec['pnl_usd']:>+7.0f}) | "
                f"{pnl_rec['result']}"
            )

        except Exception as exc:
            log.error(f"[ERROR] Trade {entry_date}: {exc}", exc_info=True)
            skipped += 1

        finally:
            del chain_entry, chain_ckpt, chain_exp
            gc.collect()

    log.info(f"\n{'─'*60}")
    log.info(f"Trades executados: {len(records)} | Pulados: {skipped}")
    log.info(f"Daily MTM records: {len(daily_records)}")
    return pd.DataFrame(records), pd.DataFrame(daily_records)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION F — SALVAR RESULTADO
# ─────────────────────────────────────────────────────────────────────────────

def save_results(df: pd.DataFrame) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if df.empty:
        log.error("DataFrame vazio — nenhum CSV gerado.")
        return OUTPUT_DIR

    start = df["trade_date"].min()
    end   = df["trade_date"].max()
    fname = f"SS42_{UNDERLYING}_{start}_{end}.csv"
    path  = OUTPUT_DIR / fname
    df.to_csv(path, index=False)
    log.info(f"CSV salvo: {path}")
    log.info(f"Shape: {df.shape}")

    wins     = (df["result"] == "WIN").sum()
    wr       = wins / len(df) * 100
    total    = df["pnl_usd"].sum()
    avg_cred = df["total_credit"].mean()
    log.info(f"\n{'='*55}")
    log.info(f"  SS42 {UNDERLYING} — RESUMO DO BACKTEST")
    log.info(f"{'='*55}")
    log.info(f"  Trades       : {len(df)}")
    log.info(f"  Win Rate     : {wr:.1f}%")
    log.info(f"  P&L Total    : ${total:,.0f}")
    log.info(f"  Avg Credit   : {avg_cred:.2f} pts")
    log.info(f"  P&L Médio    : ${df['pnl_usd'].mean():,.0f}/trade")
    log.info(f"  Melhor trade : ${df['pnl_usd'].max():,.0f}")
    log.info(f"  Pior trade   : ${df['pnl_usd'].min():,.0f}")
    log.info(f"{'='*55}\n")

    return path


def save_daily_mtm(df_daily: pd.DataFrame) -> Path:
    if df_daily.empty:
        log.warning("Daily MTM vazio — nenhum CSV daily gerado.")
        return OUTPUT_DIR

    start = df_daily["trade_date"].min()
    end   = df_daily["trade_date"].max()
    fname = f"SS42_{UNDERLYING}_daily_{start}_{end}.csv"
    path  = OUTPUT_DIR / fname
    df_daily.to_csv(path, index=False)
    log.info(f"Daily MTM CSV salvo: {path} ({len(df_daily)} rows)")
    return path


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _attach_file_handler()

    log.info("=" * 60)
    log.info(f"  SS42 BACKTEST | {UNDERLYING}")
    log.info(f"  Target DTE={TARGET_DTE} | Checkpoint={CHECKPOINT_DTE}DTE")
    log.info(f"  Delta alvo={TARGET_DELTA} | Multiplier=${MULTIPLIER}")
    log.info(f"  Risk-free={RISK_FREE_RATE*100:.1f}%")
    log.info(f"  Data dir: {DATA_DIR}")
    log.info("=" * 60)

    if not Path("G:/").exists():
        sys.exit("[ERRO FATAL] Google Drive nao montado em G:/")

    df, df_daily = run_backtest()
    save_results(df)
    save_daily_mtm(df_daily)


if __name__ == "__main__":
    main()
