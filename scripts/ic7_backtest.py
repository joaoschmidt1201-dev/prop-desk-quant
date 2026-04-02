"""
===============================================================================
 IC7 BACKTEST — Iron Condor 7DTE Historical Backtest Engine
 Prop Desk Quant | Senior Quant Developer
===============================================================================
 Validates the 7DTE Iron Condor strategy on NDX against historical data.

 Data Source    : NDX_chain_YYYY-MM-DD.parquet (G:/Meu Drive/Quant_Data_MD)
 Entry          : Every Friday (daily snapshot)
 Exit           : Following Friday — expiration (European exercise)
 Expected Move  : Spot × IV_ATM × sqrt(7/365)  ← identical to OptionsStrat
 Strikes        : Optimized to minimize BEP ↔ 1SD target distance
 Structure      : Put Spread 50pts + Call Spread 100pts
===============================================================================
"""

from __future__ import annotations

import gc
import logging
import math
import warnings
from datetime import date, timedelta
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.colors as mcolors
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.stats import norm

warnings.filterwarnings("ignore")


# ─────────────────────────────────────────────────────────────────────────────
# PARÂMETROS CONFIGURÁVEIS
# ─────────────────────────────────────────────────────────────────────────────

DATA_DIR       = Path("G:/Meu Drive/Quant_Data_MD")
DATA_PATTERN   = "NDX_chain_{date}.parquet"
OUTPUT_DIR     = Path(__file__).resolve().parent.parent / "reports" / "ic7_backtest"

# Strategy tag — change this when running a different backtest variant.
# The output CSV will be named: {STRATEGY_TAG}_{start}_{end}.csv
# Example variants: "IC7_14DTE_NDX", "IC7_7DTE_SPX", "IC7_7DTE_NDX"
STRATEGY_TAG   = "IC7_7DTE_NDX"

NDX_MULTIPLIER = 100      # USD per index point
PUT_WIDTH      = 50       # Put spread width  (points)
CALL_WIDTH     = 100      # Call spread width (points)
ENTRY_DTE      = 7        # Calendar days to expiration

RISK_FREE_RATE = 0.045    # Risk-free rate (~Fed Funds 2025, annualized)
MIN_BID        = 0.05     # Minimum bid for liquid option filter (primary tier)
MIN_BID_TIERS  = [0.05, 0.03, 0.01]  # Progressive relaxation — only if primary yields no feasible IC
IV_LOWER       = 1e-6     # brentq search lower bound
IV_UPPER       = 20.0     # brentq search upper bound (2000%)
EM_SEARCH_MULT = 2.0      # Strike search window = ±EM × this factor

# Required parquet columns (avoids loading unnecessary data)
CHAIN_COLS = [
    "side", "strike", "dte",
    "bid", "mid", "ask",
    "open_interest", "underlying_price",
]


# ─────────────────────────────────────────────────────────────────────────────
# LOGGING  (arquivo criado em OUTPUT_DIR após main() criar o diretório)
# ─────────────────────────────────────────────────────────────────────────────

log = logging.getLogger("ic7_backtest")
log.setLevel(logging.INFO)
_fmt = logging.Formatter("%(asctime)s [%(levelname)-7s] %(message)s",
                          datefmt="%Y-%m-%d %H:%M:%S")
_sh = logging.StreamHandler()
_sh.setFormatter(_fmt)
log.addHandler(_sh)


def _attach_file_handler():
    """Adiciona handler de arquivo após OUTPUT_DIR ser criado."""
    fh = logging.FileHandler(OUTPUT_DIR / "backtest.log", mode="w", encoding="utf-8")
    fh.setFormatter(_fmt)
    log.addHandler(fh)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION A — DATA LAYER
# ─────────────────────────────────────────────────────────────────────────────

def discover_friday_pairs(data_dir: Path) -> list[tuple[date, date]]:
    """
    Escaneia data_dir por arquivos NDX_chain_*.parquet, filtra sextas-feiras
    e monta pares (entry_friday, exit_friday) onde AMBOS os arquivos existem.
    """
    available: set[date] = set()
    for f in data_dir.glob("NDX_chain_*.parquet"):
        date_str = f.stem.replace("NDX_chain_", "")
        try:
            available.add(date.fromisoformat(date_str))
        except ValueError:
            continue

    pairs: list[tuple[date, date]] = []
    for d in sorted(available):
        if d.weekday() != 4:          # 4 = Friday
            continue
        exit_d = d + timedelta(days=7)
        if exit_d in available:
            pairs.append((d, exit_d))

    log.info(f"Valid Friday pairs found: {len(pairs)}")
    return pairs


def load_chain(trade_date: date) -> pd.DataFrame | None:
    """
    Carrega o parquet de um dia específico.
    Retorna None se o arquivo não existir ou estiver corrompido.
    Carrega apenas as colunas necessárias para manter RAM mínima.
    """
    path = DATA_DIR / DATA_PATTERN.format(date=trade_date.isoformat())
    if not path.exists():
        return None
    try:
        try:
            df = pd.read_parquet(path, columns=CHAIN_COLS)
        except Exception as exc:
            # PyArrow >=14 added strict repetition-level histogram validation that
            # rejects files written by older writers (e.g. vendor cloud pipelines).
            # fastparquet skips that check and reads the same data correctly.
            if "histogram" in str(exc).lower() or "repetition" in str(exc).lower():
                df = pd.read_parquet(path, columns=CHAIN_COLS, engine="fastparquet")
            else:
                raise
        # Garantir tipos numéricos precisos
        df["strike"]           = df["strike"].astype("float64")
        df["underlying_price"] = df["underlying_price"].astype("float64")
        df["mid"]              = df["mid"].astype("float64")
        df["bid"]              = df["bid"].astype("float64")
        df["ask"]              = df["ask"].astype("float64")
        return df
    except Exception as exc:
        log.warning(f"Error loading {path.name}: {exc}")
        return None


def filter_chain_by_dte(
    chain: pd.DataFrame,
    side: str,
    target_dte: int = ENTRY_DTE,
    min_bid: float = MIN_BID,
) -> pd.DataFrame:
    """
    Filtra o chain para o lado (call/put) e DTE alvo.
    Nota: coluna 'expiration' pode estar corrompida nos parquets; usa 'dte'.
    Fallback: aceita dte ∈ [target-2, target+2] e escolhe o mais frequente.
    """
    mask = (chain["side"] == side) & (chain["bid"] >= min_bid)

    # Tentativa exata
    exact = chain.loc[mask & (chain["dte"] == target_dte)].copy()

    # Fallback por proximidade
    if exact.empty:
        nearby = chain.loc[mask & chain["dte"].between(target_dte - 2, target_dte + 2)].copy()
        if nearby.empty:
            return pd.DataFrame()
        best_dte = int(nearby["dte"].value_counts().index[0])
        exact = nearby[nearby["dte"] == best_dte].copy()

    if exact.empty:
        return pd.DataFrame()

    # Dedup por strike → mantém maior open_interest
    exact = (
        exact
        .sort_values("open_interest", ascending=False)
        .drop_duplicates(subset="strike")
        .sort_values("strike")
        .reset_index(drop=True)
    )
    return exact


# ─────────────────────────────────────────────────────────────────────────────
# SECTION B — IV ENGINE (BLACK-SCHOLES EUROPEU, SEM DIVIDENDOS)
# ─────────────────────────────────────────────────────────────────────────────

def _bs_price(S: float, K: float, T: float, r: float,
              sigma: float, opt_type: str) -> float:
    """Preço Black-Scholes para opção europeia (q=0)."""
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
    """
    Inverte _bs_price via brentq para encontrar IV implícita.
    Retorna None se não convergir ou se preço < valor intrínseco.
    """
    if T <= 0 or S <= 0 or K <= 0 or market_price <= 0:
        return None
    intrinsic = max(0.0, (S - K) if opt_type == "call" else (K - S))
    if market_price < intrinsic - 1e-3:
        return None
    obj = lambda sig: _bs_price(S, K, T, r, sig, opt_type) - market_price
    try:
        f_lo, f_hi = obj(IV_LOWER), obj(IV_UPPER)
        if f_lo * f_hi > 0:
            return None          # sem mudança de sinal
        iv = brentq(obj, IV_LOWER, IV_UPPER, xtol=1e-8, maxiter=200)
        return float(iv) if 0 < iv < IV_UPPER else None
    except Exception:
        return None


def calc_iv_atm(
    puts: pd.DataFrame,
    calls: pd.DataFrame,
    spot: float,
    r: float = RISK_FREE_RATE,
) -> tuple[float | None, float]:
    """
    Calcula IV ATM como média entre call ATM e put ATM.
    Strike ATM = strike mais próximo do spot no universo combinado.
    Retorna (iv_atm, atm_strike).  iv_atm é None se ambos os lados falharem.
    """
    T = ENTRY_DTE / 365.0

    # Strike ATM no universo combinado
    all_strikes = pd.concat([
        puts[["strike"]], calls[["strike"]]
    ]).drop_duplicates()["strike"]
    atm_strike = float(all_strikes.iloc[(all_strikes - spot).abs().argsort().iloc[0]])

    iv_call, iv_put = None, None

    c_row = calls[calls["strike"] == atm_strike]
    if not c_row.empty:
        mid_c = float(c_row["mid"].iloc[0])
        if mid_c > 0:
            iv_call = _bs_iv(mid_c, spot, atm_strike, T, r, "call")

    p_row = puts[puts["strike"] == atm_strike]
    if not p_row.empty:
        mid_p = float(p_row["mid"].iloc[0])
        if mid_p > 0:
            iv_put = _bs_iv(mid_p, spot, atm_strike, T, r, "put")

    if iv_call is not None and iv_put is not None:
        iv_atm = (iv_call + iv_put) / 2.0
    elif iv_call is not None:
        iv_atm = iv_call
    elif iv_put is not None:
        iv_atm = iv_put
    else:
        iv_atm = None

    return iv_atm, atm_strike


def calc_expected_move(spot: float, iv_atm: float,
                       dte_calendar: int = ENTRY_DTE) -> float:
    """
    EM = Spot × IV_ATM × sqrt(DTE / 365)
    Fórmula idêntica ao OptionsStrat (volatilidade implícita, dias corridos).
    """
    return spot * iv_atm * math.sqrt(dte_calendar / 365.0)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION C — OTIMIZADOR DE STRIKES (MINIMIZA DISTÂNCIA BEP ↔ ALVO 1 DP)
# ─────────────────────────────────────────────────────────────────────────────

def _mid_for_strike(df: pd.DataFrame, strike: float) -> float | None:
    """Retorna o mid-price para um strike específico; None se não encontrado."""
    row = df.loc[df["strike"] == strike, "mid"]
    if row.empty:
        return None
    v = float(row.iloc[0])
    return v if v > 0 else None


def select_optimal_strikes(
    puts: pd.DataFrame,
    calls: pd.DataFrame,
    spot: float,
    upper_target: float,
    lower_target: float,
    em: float,
) -> dict | None:
    """
    Enumerates all (short_put, short_call) combinations and selects the optimal
    with a BEP HARD CONSTRAINT.

    Hard constraint (absolute priority):
        bep_lower <= lower_target   (lower BEP at or outside -1SD)
        bep_upper >= upper_target   (upper BEP at or outside +1SD)

    Wing selection — FLEXIBLE MINIMUM WIDTH:
        long_put  = largest  put  strike available with strike <= short_put  - PUT_WIDTH
        long_call = smallest call strike available with strike >= short_call + CALL_WIDTH

    This avoids discarding deep-OTM short strikes due to strike spacing changes
    (e.g. 25pt near ATM → 100pt deep OTM). The real wing widths are recorded.

    Selection:
        • Among feasible candidates (constraint satisfied) → minimum combined BEP distance
        • If none feasible → returns None (caller retries with relaxed MIN_BID tier)

    Returns dict with all strikes, mids, credit, BEPs, real wing widths,
    and constraint_satisfied flag (always True when returned).
    """
    window = em * EM_SEARCH_MULT

    put_cands = puts.loc[
        (puts["strike"] < spot) &
        puts["strike"].between(lower_target - window, lower_target + window)
    ]
    call_cands = calls.loc[
        (calls["strike"] > spot) &
        calls["strike"].between(upper_target - window, upper_target + window)
    ]

    # Fallback: no candidates in window → use all OTM strikes
    if put_cands.empty:
        put_cands = puts[puts["strike"] < spot]
    if call_cands.empty:
        call_cands = calls[calls["strike"] > spot]
    if put_cands.empty or call_cands.empty:
        return None

    # Sorted arrays for flexible wing lookup (ascending)
    puts_arr  = np.sort(puts["strike"].values)
    calls_arr = np.sort(calls["strike"].values)

    # Only feasible candidates (BEPs covering ±1SD) are collected
    feasible: list[tuple[float, dict]] = []  # (dist, candidate)

    for sp in put_cands["strike"].values:
        # Flexible long_put: largest put strike available that is <= sp - PUT_WIDTH
        lp_pool = puts_arr[puts_arr <= sp - PUT_WIDTH]
        if len(lp_pool) == 0:
            continue
        lp = float(lp_pool[-1])

        mid_sp = _mid_for_strike(puts, sp)
        mid_lp = _mid_for_strike(puts, lp)
        if mid_sp is None or mid_lp is None:
            continue

        for sc in call_cands["strike"].values:
            # Flexible long_call: smallest call strike available that is >= sc + CALL_WIDTH
            lc_pool = calls_arr[calls_arr >= sc + CALL_WIDTH]
            if len(lc_pool) == 0:
                continue
            lc = float(lc_pool[0])

            mid_sc = _mid_for_strike(calls, sc)
            mid_lc = _mid_for_strike(calls, lc)
            if mid_sc is None or mid_lc is None:
                continue

            credit = (mid_sp - mid_lp) + (mid_sc - mid_lc)
            if credit <= 0:
                continue

            # ── Hard Risk Constraints: wing width caps and proportion rule ──
            put_width_real  = sp - lp
            call_width_real = lc - sc
            if put_width_real > 100 or call_width_real > 100:
                continue
            if put_width_real > call_width_real:  # put wing must never exceed call wing
                continue

            bep_upper = sc + credit
            bep_lower = sp - credit

            # Violation: how far BEPs are INSIDE the forbidden zone (0 = compliant)
            violation = (
                max(0.0, bep_lower - lower_target) +   # lower BEP above -1SD
                max(0.0, upper_target - bep_upper)     # upper BEP below +1SD
            )
            dist = (bep_upper - upper_target) ** 2 + (bep_lower - lower_target) ** 2

            candidate = dict(
                short_put=sp,           long_put=lp,
                short_call=sc,          long_call=lc,
                put_width_real=round(put_width_real, 1),
                call_width_real=round(call_width_real, 1),
                mid_sp=mid_sp,          mid_lp=mid_lp,
                mid_sc=mid_sc,          mid_lc=mid_lc,
                total_credit=round(credit, 4),
                bep_upper=round(bep_upper, 2),
                bep_lower=round(bep_lower, 2),
                bep_score=round(dist, 4),
                constraint_satisfied=(violation == 0.0),
            )

            if violation == 0.0:
                feasible.append((dist, candidate))

    if feasible:
        feasible.sort(key=lambda x: x[0])
        return feasible[0][1]

    return None


# ─────────────────────────────────────────────────────────────────────────────
# SECTION D — P&L ENGINE (EXERCÍCIO EUROPEU NA EXPIRAÇÃO)
# ─────────────────────────────────────────────────────────────────────────────

def calc_trade_pnl(entry: dict, spot_exit: float) -> dict:
    """
    Calcula P&L na expiração assumindo exercício europeu (valor intrínseco).

    exit_cost = [max(0, sp − spot) − max(0, lp − spot)]   ← asa de puts
              + [max(0, spot − sc) − max(0, spot − lc)]   ← asa de calls

    pnl_points = credit_recebido − exit_cost
    pnl_usd    = pnl_points × NDX_MULTIPLIER ($100/pt)
    """
    sp = entry["short_put"]
    lp = entry["long_put"]
    sc = entry["short_call"]
    lc = entry["long_call"]
    credit = entry["total_credit"]

    put_cost  = max(0.0, sp - spot_exit) - max(0.0, lp - spot_exit)
    call_cost = max(0.0, spot_exit - sc) - max(0.0, spot_exit - lc)
    exit_cost = put_cost + call_cost

    pnl_pts = credit - exit_cost
    pnl_usd = pnl_pts * NDX_MULTIPLIER
    in_range = (sp <= spot_exit <= sc)
    max_loss = max(PUT_WIDTH, CALL_WIDTH) - credit   # pior caso teórico

    if pnl_pts > 0:
        result = "WIN"
    elif exit_cost >= max(PUT_WIDTH, CALL_WIDTH):
        result = "MAX_LOSS"
    else:
        result = "LOSS"

    return dict(
        spot_exit=round(spot_exit, 2),
        put_cost=round(put_cost, 4),
        call_cost=round(call_cost, 4),
        exit_cost=round(exit_cost, 4),
        pnl_points=round(pnl_pts, 4),
        pnl_usd=round(pnl_usd, 2),
        max_risk_usd=round(max_loss * NDX_MULTIPLIER, 2),
        in_range=in_range,
        result=result,
    )


# ─────────────────────────────────────────────────────────────────────────────
# SECTION E — LOOP PRINCIPAL DO BACKTEST
# ─────────────────────────────────────────────────────────────────────────────

def run_backtest() -> pd.DataFrame:
    """
    Itera todos os pares de sextas-feiras válidos e simula o Iron Condor 7DTE.
    Processa um arquivo por vez para RAM mínima (safe em 16 GB).
    """
    pairs = discover_friday_pairs(DATA_DIR)
    if not pairs:
        log.error("No valid pairs found — check DATA_DIR.")
        return pd.DataFrame()

    records: list[dict] = []
    skipped = 0

    for entry_date, exit_date in pairs:

        chain_entry = None
        chain_exit  = None
        puts        = None
        calls       = None

        try:
            # ── ENTRADA ──────────────────────────────────────────────────
            chain_entry = load_chain(entry_date)
            if chain_entry is None:
                log.warning(f"[SKIP] Missing file: {entry_date}")
                skipped += 1
                continue

            spot = float(chain_entry["underlying_price"].median())
            if spot <= 0:
                log.warning(f"[SKIP] Invalid spot ({spot}) on {entry_date}")
                skipped += 1
                continue

            puts  = filter_chain_by_dte(chain_entry, "put")
            calls = filter_chain_by_dte(chain_entry, "call")

            if puts.empty or calls.empty:
                log.warning(f"[SKIP] No DTE={ENTRY_DTE} options on {entry_date}")
                skipped += 1
                continue

            # ── IV E EXPECTED MOVE ────────────────────────────────────────
            # ATM options are always liquid — primary filter (MIN_BID=0.05) is sufficient
            iv_atm, atm_strike = calc_iv_atm(puts, calls, spot)
            if iv_atm is None:
                log.warning(f"[SKIP] IV did not converge on {entry_date}")
                skipped += 1
                continue

            em           = calc_expected_move(spot, iv_atm)
            upper_target = spot + em
            lower_target = spot - em

            # ── SELEÇÃO ÓTIMA DE STRIKES (progressive MIN_BID) ───────────
            # Tier 1 (0.05): reuse already-filtered puts/calls.
            # Tiers 2–3 (0.03, 0.01): re-filter to unlock thinly-bid strikes
            # that can push BEPs past ±1SD. Skips the week only if all tiers fail.
            optimal      = None
            min_bid_used = None
            for tier in MIN_BID_TIERS:
                puts_t  = puts  if tier == MIN_BID else filter_chain_by_dte(chain_entry, "put",  min_bid=tier)
                calls_t = calls if tier == MIN_BID else filter_chain_by_dte(chain_entry, "call", min_bid=tier)
                if puts_t.empty or calls_t.empty:
                    continue
                candidate = select_optimal_strikes(puts_t, calls_t, spot, upper_target, lower_target, em)
                if candidate is not None:
                    optimal      = candidate
                    min_bid_used = tier
                    break

            if optimal is None:
                log.warning(f"[SKIP] No feasible IC on {entry_date} (all MIN_BID tiers exhausted)")
                skipped += 1
                continue

            # ── SAÍDA (EXPIRAÇÃO DA SEXTA SEGUINTE) ───────────────────────
            chain_exit = load_chain(exit_date)
            if chain_exit is not None:
                spot_exit   = float(chain_exit["underlying_price"].median())
                exit_method = "market"
            else:
                log.warning(f"[WARN] Exit file missing: {exit_date}. Falling back to entry spot.")
                spot_exit   = spot
                exit_method = "fallback"

            # ── P&L ───────────────────────────────────────────────────────
            entry_rec = dict(
                trade_date   = entry_date,
                exp_date     = exit_date,
                spot_entry   = round(spot, 2),
                atm_strike   = atm_strike,
                iv_atm       = round(iv_atm, 6),
                iv_atm_pct   = round(iv_atm * 100, 2),
                expected_move= round(em, 2),
                em_pct       = round(em / spot * 100, 2),
                upper_target = round(upper_target, 2),
                lower_target = round(lower_target, 2),
                min_bid_used = min_bid_used,
                exit_method  = exit_method,
                **optimal,
            )
            pnl_rec = calc_trade_pnl(entry_rec, spot_exit)
            records.append({**entry_rec, **pnl_rec})

            tier_tag = f" [bid≥{min_bid_used}]" if min_bid_used != MIN_BID else ""
            log.info(
                f"{entry_date} → {exit_date} | "
                f"Spot:{spot:>8.0f} | EM:±{em:>5.0f} ({em/spot*100:.1f}%) | "
                f"IV:{iv_atm*100:>5.1f}% | "
                f"P/{optimal['short_put']:.0f}-{optimal['long_put']:.0f} "
                f"C/{optimal['short_call']:.0f}-{optimal['long_call']:.0f} | "
                f"Cred:{optimal['total_credit']:>6.2f}pts | "
                f"Exit:{spot_exit:>8.0f} | "
                f"PnL:{pnl_rec['pnl_points']:>+7.2f}pts "
                f"(${pnl_rec['pnl_usd']:>+7.0f}) | "
                f"{pnl_rec['result']}{tier_tag}"
            )

        except Exception as exc:
            log.error(f"[ERROR] Trade {entry_date}: {exc}", exc_info=False)
            skipped += 1

        finally:
            # Liberar memória explicitamente — um arquivo por vez
            del chain_entry, chain_exit, puts, calls
            gc.collect()

    log.info(f"\n{'─'*60}")
    log.info(f"Trades executed: {len(records)} | Skipped: {skipped}")
    return pd.DataFrame(records)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION F — ANALYTICS DE PERFORMANCE
# ─────────────────────────────────────────────────────────────────────────────

def _equity_curve(tl: pd.DataFrame) -> pd.Series:
    return tl.set_index("exp_date")["pnl_usd"].cumsum()


def _drawdown(equity: pd.Series) -> pd.Series:
    return equity - equity.cummax()


def _sharpe(pnl: pd.Series, freq: float = 52.0) -> float:
    """Sharpe anualizado para estratégia semanal (freq=52)."""
    if len(pnl) < 2 or pnl.std() == 0:
        return float("nan")
    return (pnl.mean() / pnl.std()) * math.sqrt(freq)


def _profit_factor(pnl: pd.Series) -> float:
    wins   = pnl[pnl > 0].sum()
    losses = abs(pnl[pnl < 0].sum())
    return float(wins / losses) if losses > 0 else float("inf")


def _max_consec_losses(results: pd.Series) -> int:
    best = cur = 0
    for r in results:
        cur = cur + 1 if r != "WIN" else 0
        best = max(best, cur)
    return best


def build_performance_report(tl: pd.DataFrame) -> dict:
    pnl    = tl["pnl_usd"]
    equity = _equity_curve(tl)
    dd     = _drawdown(equity)
    total  = len(tl)
    wins   = int((tl["result"] == "WIN").sum())
    losses = int((tl["result"] == "LOSS").sum())
    maxl   = int((tl["result"] == "MAX_LOSS").sum())

    # Sortino: penaliza apenas downside
    downside = pnl[pnl < 0]
    downside_std = downside.std() if len(downside) > 1 else float("nan")
    sortino = (pnl.mean() / downside_std * math.sqrt(52)) if not math.isnan(downside_std) and downside_std > 0 else float("nan")

    # Recovery factor
    total_pnl = pnl.sum()
    max_dd = dd.min()
    recovery = abs(total_pnl / max_dd) if max_dd != 0 else float("inf")

    return dict(
        total_trades          = total,
        wins                  = wins,
        partial_losses        = losses,
        max_losses            = maxl,
        win_rate_pct          = round(wins / total * 100, 1),
        in_range_rate_pct     = round(tl["in_range"].mean() * 100, 1),
        total_pnl_usd         = round(total_pnl, 2),
        avg_pnl_usd           = round(pnl.mean(), 2),
        median_pnl_usd        = round(pnl.median(), 2),
        best_trade_usd        = round(pnl.max(), 2),
        worst_trade_usd       = round(pnl.min(), 2),
        std_pnl_usd           = round(pnl.std(), 2),
        max_drawdown_usd      = round(max_dd, 2),
        sharpe_ratio          = round(_sharpe(pnl), 3),
        sortino_ratio         = round(sortino, 3),
        profit_factor         = round(_profit_factor(pnl), 3),
        recovery_factor       = round(recovery, 3),
        max_consec_losses     = _max_consec_losses(tl["result"]),
        avg_credit_pts        = round(tl["total_credit"].mean(), 2),
        avg_credit_usd        = round(tl["total_credit"].mean() * NDX_MULTIPLIER, 2),
        avg_em_pct            = round(tl["em_pct"].mean(), 2),
        avg_iv_atm_pct        = round(tl["iv_atm_pct"].mean(), 2),
    )


# ─────────────────────────────────────────────────────────────────────────────
# SECTION G — CHARTS & REPORT
# ─────────────────────────────────────────────────────────────────────────────

# Estilo visual consistente
_STYLE = {
    "bg_fig"  : "#0d1117",
    "bg_ax"   : "#161b22",
    "green"   : "#00c896",
    "red"     : "#ff4d4d",
    "yellow"  : "#f0e040",
    "white"   : "#e6edf3",
    "gridc"   : "#30363d",
}

def _style_ax(fig, *axes):
    fig.patch.set_facecolor(_STYLE["bg_fig"])
    for ax in axes:
        ax.set_facecolor(_STYLE["bg_ax"])
        ax.tick_params(colors=_STYLE["white"], labelsize=9)
        ax.xaxis.label.set_color(_STYLE["white"])
        ax.yaxis.label.set_color(_STYLE["white"])
        ax.title.set_color(_STYLE["white"])
        ax.grid(color=_STYLE["gridc"], linewidth=0.6)
        for spine in ax.spines.values():
            spine.set_edgecolor(_STYLE["gridc"])


def _save_fig(fig, outdir: Path, fname: str):
    fig.tight_layout()
    fig.savefig(outdir / fname, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    log.info(f"  ✓ {outdir / fname}")


# ── Chart 1: Equity Curve ─────────────────────────────────────────────────

def plot_equity_curve(equity: pd.Series, dd: pd.Series, outdir: Path):
    fig, ax = plt.subplots(figsize=(13, 5))

    color = _STYLE["green"] if equity.iloc[-1] >= 0 else _STYLE["red"]
    ax.plot(equity.index, equity.values, color=color, linewidth=2, zorder=3)
    ax.fill_between(equity.index, equity.values, 0,
                    where=equity.values >= 0, alpha=0.18, color=_STYLE["green"])
    ax.fill_between(equity.index, equity.values, 0,
                    where=equity.values < 0, alpha=0.25, color=_STYLE["red"])
    ax.axhline(0, color=_STYLE["white"], linewidth=0.8, linestyle="--", alpha=0.4)

    # Anotar pior drawdown
    dd_idx = dd.idxmin()
    dd_val = dd.min()
    ax.annotate(
        f"Max DD\n${dd_val:,.0f}",
        xy=(dd_idx, equity[dd_idx]),
        xytext=(15, -45), textcoords="offset points",
        color=_STYLE["red"], fontsize=8, fontweight="bold",
        arrowprops=dict(arrowstyle="->", color=_STYLE["red"], lw=1.2),
    )

    # Anotar P&L final
    final = equity.iloc[-1]
    ax.annotate(
        f"Final P&L\n${final:,.0f}",
        xy=(equity.index[-1], final),
        xytext=(-90, 12), textcoords="offset points",
        color=color, fontsize=9, fontweight="bold",
    )

    ax.set_title("IC7 NDX — Equity Curve | Cumulative P&L (USD)", fontsize=13, fontweight="bold", pad=10)
    ax.set_xlabel("Expiration Date")
    ax.set_ylabel("Cumulative P&L (USD)")
    _style_ax(fig, ax)
    _save_fig(fig, outdir, "equity_curve.png")


# ── Chart 2: Drawdown ─────────────────────────────────────────────────────

def plot_drawdown(dd: pd.Series, outdir: Path):
    fig, ax = plt.subplots(figsize=(13, 4))

    ax.fill_between(dd.index, dd.values, 0,
                    where=dd.values <= 0, color=_STYLE["red"], alpha=0.55, label="Drawdown")
    ax.plot(dd.index, dd.values, color=_STYLE["red"], linewidth=1.2)
    ax.axhline(0, color=_STYLE["white"], linewidth=0.8, linestyle="--", alpha=0.4)

    worst_idx = dd.idxmin()
    ax.axvline(worst_idx, color=_STYLE["yellow"], linewidth=1.2,
               linestyle=":", label=f"Worst DD: ${dd.min():,.0f}")

    ax.set_title("IC7 NDX — Drawdown Curve", fontsize=13, fontweight="bold", pad=10)
    ax.set_xlabel("Date")
    ax.set_ylabel("Drawdown (USD)")
    ax.legend(facecolor=_STYLE["bg_ax"], labelcolor=_STYLE["white"], fontsize=9)
    _style_ax(fig, ax)
    _save_fig(fig, outdir, "drawdown.png")


# ── Chart 3: P&L Distribution ────────────────────────────────────────────

def plot_pnl_distribution(tl: pd.DataFrame, outdir: Path):
    pnl      = tl["pnl_usd"]
    win_rate = (tl["result"] == "WIN").mean() * 100

    fig, ax = plt.subplots(figsize=(10, 5))
    n, bins, patches = ax.hist(pnl, bins=25, edgecolor="#0d1117", linewidth=0.4)
    for patch, left in zip(patches, bins[:-1]):
        patch.set_facecolor(_STYLE["green"] if left >= 0 else _STYLE["red"])
        patch.set_alpha(0.85)

    ax.axvline(0,          color=_STYLE["white"],  linewidth=1.4, linestyle="--",
               label="Zero")
    ax.axvline(pnl.mean(), color=_STYLE["yellow"], linewidth=1.4, linestyle="-.",
               label=f"Mean: ${pnl.mean():,.0f}")

    ax.set_title(
        f"IC7 NDX — P&L Distribution per Trade  |  "
        f"Win Rate: {win_rate:.1f}%  |  N={len(tl)}",
        fontsize=12, fontweight="bold", pad=10,
    )
    ax.set_xlabel("P&L per Trade (USD)")
    ax.set_ylabel("Frequency")
    ax.legend(facecolor=_STYLE["bg_ax"], labelcolor=_STYLE["white"], fontsize=9)
    _style_ax(fig, ax)
    _save_fig(fig, outdir, "pnl_distribution.png")


# ── Chart 4: Monthly P&L Heatmap ─────────────────────────────────────────

def plot_monthly_heatmap(tl: pd.DataFrame, outdir: Path):
    _MONTH = {1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"May",6:"Jun",
              7:"Jul",8:"Aug",9:"Sep",10:"Oct",11:"Nov",12:"Dec"}

    df = tl.copy()
    df["year"]  = pd.to_datetime(df["exp_date"]).dt.year
    df["month"] = pd.to_datetime(df["exp_date"]).dt.month

    pivot = df.pivot_table(values="pnl_usd", index="year",
                           columns="month", aggfunc="sum")
    pivot.columns = [_MONTH[m] for m in pivot.columns]

    vals    = pivot.values[~np.isnan(pivot.values)]
    abs_max = max(abs(vals).max(), 1.0)
    norm    = mcolors.TwoSlopeNorm(vmin=-abs_max, vcenter=0, vmax=abs_max)

    fig_h = max(2.5, len(pivot) * 1.5)
    fig, ax = plt.subplots(figsize=(14, fig_h))
    im = ax.imshow(pivot.values, cmap="RdYlGn", norm=norm, aspect="auto")

    cbar = plt.colorbar(im, ax=ax, shrink=0.85)
    cbar.set_label("P&L (USD)", color=_STYLE["white"], fontsize=9)
    cbar.ax.yaxis.set_tick_params(color=_STYLE["white"])
    plt.setp(cbar.ax.yaxis.get_ticklabels(), color=_STYLE["white"])

    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels(pivot.columns, fontsize=9)
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels([str(y) for y in pivot.index], fontsize=9)

    for i in range(len(pivot.index)):
        for j in range(len(pivot.columns)):
            v = pivot.values[i, j]
            if not np.isnan(v):
                txt_color = "black" if abs(v) < abs_max * 0.6 else "white"
                ax.text(j, i, f"${v:,.0f}", ha="center", va="center",
                        fontsize=8, color=txt_color, fontweight="bold")

    ax.set_title("IC7 NDX — Monthly Consolidated P&L (USD)",
                 fontsize=13, fontweight="bold", pad=10)
    _style_ax(fig, ax)
    _save_fig(fig, outdir, "monthly_heatmap.png")


# ── Export: CSV + TXT Report ──────────────────────────────────────────────

def export_results(tl: pd.DataFrame, rpt: dict, outdir: Path):
    # ── CSV  (filename encodes strategy + actual date range of the backtest)
    start    = str(tl["trade_date"].min())
    end      = str(tl["exp_date"].max())
    csv_name = f"{STRATEGY_TAG}_{start}_{end}.csv"
    csv_path = outdir / csv_name
    tl.to_csv(csv_path, index=False, float_format="%.4f")
    log.info(f"  ✓ {csv_path}")

    # ── TXT
    sep  = "═" * 68
    sep2 = "─" * 68
    lines = [
        sep,
        "  IC7 IRON CONDOR 7DTE — NDX  |  BACKTEST REPORT",
        f"  Period   : {tl['trade_date'].min()} → {tl['exp_date'].max()}",
        f"  Generated: {date.today().isoformat()}",
        sep,
        "",
        "  ┌─ EXECUTIVE SUMMARY ─────────────────────────────────────┐",
        f"  │  Total Trades               :  {rpt['total_trades']:>6}                    │",
        f"  │  Wins                       :  {rpt['wins']:>6}  ({rpt['win_rate_pct']:>5.1f}%)          │",
        f"  │  Partial Losses             :  {rpt['partial_losses']:>6}                    │",
        f"  │  Max Losses (spread 100%)   :  {rpt['max_losses']:>6}                    │",
        f"  │  In-Range Rate              :  {rpt['in_range_rate_pct']:>5.1f}%                   │",
        "  └────────────────────────────────────────────────────────┘",
        "",
        "  P&L",
        sep2,
        f"  Total P&L                    :  ${rpt['total_pnl_usd']:>12,.2f}",
        f"  Avg P&L per Trade            :  ${rpt['avg_pnl_usd']:>12,.2f}",
        f"  Median P&L                   :  ${rpt['median_pnl_usd']:>12,.2f}",
        f"  Std Dev (P&L)                :  ${rpt['std_pnl_usd']:>12,.2f}",
        f"  Best Trade                   :  ${rpt['best_trade_usd']:>12,.2f}",
        f"  Worst Trade                  :  ${rpt['worst_trade_usd']:>12,.2f}",
        "",
        "  RISK",
        sep2,
        f"  Max Drawdown                 :  ${rpt['max_drawdown_usd']:>12,.2f}",
        f"  Sharpe Ratio (ann. 52x)      :  {rpt['sharpe_ratio']:>13.3f}",
        f"  Sortino Ratio                :  {rpt['sortino_ratio']:>13.3f}",
        f"  Profit Factor                :  {rpt['profit_factor']:>13.3f}",
        f"  Recovery Factor              :  {rpt['recovery_factor']:>13.3f}",
        f"  Max Consecutive Losses       :  {rpt['max_consec_losses']:>13}",
        "",
        "  TRADE STRUCTURE",
        sep2,
        f"  Put Spread Width             :  {PUT_WIDTH} pts",
        f"  Call Spread Width            :  {CALL_WIDTH} pts",
        f"  Average Credit               :  {rpt['avg_credit_pts']:>6.2f} pts  "
        f"(${rpt['avg_credit_usd']:,.2f} USD)",
        f"  Average Expected Move        :  {rpt['avg_em_pct']:>5.2f}%",
        f"  Average IV ATM               :  {rpt['avg_iv_atm_pct']:>5.2f}%",
        "",
        sep,
        "  Prop Desk Quant  |  Senior Quant Developer",
        "  For internal use only — Cristiano (CZ)",
        sep,
    ]
    txt_path = outdir / "performance_report.txt"
    txt_path.write_text("\n".join(lines), encoding="utf-8")
    log.info(f"  ✓ {txt_path}")

    # Imprimir no terminal (safe para consoles Windows cp1252)
    output = "\n" + "\n".join(lines)
    try:
        print(output)
    except UnicodeEncodeError:
        import sys
        sys.stdout.buffer.write(output.encode("utf-8"))
        sys.stdout.buffer.write(b"\n")


# ── Orchestrator ─────────────────────────────────────────────────────────

def generate_all_outputs(tl: pd.DataFrame, outdir: Path = OUTPUT_DIR):
    if tl.empty:
        log.error("Trade log is empty — nothing to report.")
        return

    outdir.mkdir(parents=True, exist_ok=True)
    log.info(f"\nGenerating report at: {outdir}\n")

    equity = _equity_curve(tl)
    dd     = _drawdown(equity)
    rpt    = build_performance_report(tl)

    plot_equity_curve(equity, dd, outdir)
    plot_drawdown(dd, outdir)
    plot_pnl_distribution(tl, outdir)
    plot_monthly_heatmap(tl, outdir)
    export_results(tl, rpt, outdir)


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _attach_file_handler()

    log.info("═" * 60)
    log.info("  IC7 BACKTEST  —  Iron Condor 7DTE | NDX")
    log.info(f"  Data DIR  : {DATA_DIR}")
    log.info(f"  Output DIR: {OUTPUT_DIR}")
    log.info(f"  Put Width : {PUT_WIDTH}pts  |  Call Width: {CALL_WIDTH}pts")
    log.info(f"  Risk-Free : {RISK_FREE_RATE*100:.1f}%  |  Min Bid: {MIN_BID}")
    log.info("═" * 60 + "\n")

    if not DATA_DIR.exists():
        log.error(f"DATA_DIR not found: {DATA_DIR}")
        return

    trade_log = run_backtest()

    if trade_log.empty:
        log.error("Backtest produced no trades. Check data and parameters.")
        return

    generate_all_outputs(trade_log)


if __name__ == "__main__":
    main()
