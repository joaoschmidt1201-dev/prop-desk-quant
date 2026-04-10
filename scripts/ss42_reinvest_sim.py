"""
===============================================================================
 SS42 RE-INVESTMENT SIMULATOR
 Prop Desk Quant
===============================================================================
 Pre-computes trade logs + daily MTM for all SS42 close rule scenarios
 with recursive re-entry simulation.  Run locally (requires G:/ parquets)
 and commit the output CSVs so Streamlit Cloud can load them directly.

 USO:
     python scripts/ss42_reinvest_sim.py SPX
     python scripts/ss42_reinvest_sim.py RUT

 OUTPUT (por close rule):
     reports/ss42_backtest/SS42_{UND}_reinvest_{key}_trades.csv
     reports/ss42_backtest/SS42_{UND}_reinvest_{key}_daily.csv
===============================================================================
"""
from __future__ import annotations

import gc
import logging
import math
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

# ── Import backtest engine ─────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ss42_backtest import (
    load_chain,
    find_target_expiration,
    select_16delta_strikes,
    calc_iv_atm,
    get_available_dates,
    compute_daily_mtm,
    calc_pnl_expiration,
    DATA_DIR,
    OUTPUT_DIR,
)

# ─────────────────────────────────────────────────────────────────────────────
# PARÂMETROS
# ─────────────────────────────────────────────────────────────────────────────

_arg_u     = sys.argv[1].upper() if len(sys.argv) > 1 else "SPX"
UNDERLYING = _arg_u if _arg_u in ("SPX", "RUT") else "SPX"
MULTIPLIER = 100

CLOSE_RULES: dict[str, str] = {
    "25pct":       "25% Profit Target",
    "50pct":       "50% Profit Target",
    "75pct":       "75% Profit Target",
    "50pct_24dit": "50% Profit or 24 DIT",
    "24dit":       "24 DIT",
}

log = logging.getLogger("reinvest_sim")
log.setLevel(logging.INFO)
_sh = logging.StreamHandler()
_sh.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)-7s] %(message)s", datefmt="%H:%M:%S"
))
log.addHandler(_sh)


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS — CLOSE DATE E PRÓXIMA SEXTA
# ─────────────────────────────────────────────────────────────────────────────

def get_close_date(
    trade: pd.Series,
    rule: str,
    daily_df: pd.DataFrame,
) -> date:
    """Retorna a data em que a close rule dispara para o trade (ou exp_date)."""
    trade_date_str = str(trade["trade_date"])
    exp_date = pd.to_datetime(trade["exp_date"]).date()
    max_p    = float(trade["total_credit"]) * MULTIPLIER

    rows = daily_df[daily_df["trade_date"] == trade_date_str].copy()
    if rows.empty:
        return exp_date

    rows = rows.sort_values("dte_remaining", ascending=False)
    dte_max = int(rows["dte_remaining"].iloc[0])
    rows_scan = rows[rows["dte_remaining"] < dte_max]

    if rule in ("24 DIT", "50% Profit or 24 DIT"):
        tp_thr = 0.50 * max_p if "50%" in rule else None
        for _, row in rows_scan.iterrows():
            dit = dte_max - int(row["dte_remaining"])
            pnl = float(row["pnl_usd"])
            if tp_thr is not None and pnl >= tp_thr:
                return pd.to_datetime(row["calendar_date"]).date()
            if dit >= 24:
                return pd.to_datetime(row["calendar_date"]).date()
    else:
        pct_map = {
            "25% Profit Target": 0.25,
            "50% Profit Target": 0.50,
            "75% Profit Target": 0.75,
        }
        tp_pct = pct_map.get(rule)
        if tp_pct is not None:
            tp_thr = tp_pct * max_p
            for _, row in rows_scan.iterrows():
                if float(row["pnl_usd"]) >= tp_thr:
                    return pd.to_datetime(row["calendar_date"]).date()

    return exp_date


def next_friday_after(d: date) -> date:
    """Retorna a próxima sexta-feira estritamente após d."""
    days_ahead = 4 - d.weekday()   # 4 = sexta
    if days_ahead <= 0:
        days_ahead += 7
    return d + timedelta(days=days_ahead)


# ─────────────────────────────────────────────────────────────────────────────
# SIMULAÇÃO DE UM ÚNICO TRADE (re-entrada)
# ─────────────────────────────────────────────────────────────────────────────

def simulate_single_trade(entry_date: date) -> tuple[dict | None, list[dict]]:
    """
    Simula um SS42 strangle completo a partir de entry_date.
    Retorna (trade_dict, daily_records) ou (None, []) se dados indisponíveis.
    """
    chain_entry = load_chain(entry_date, UNDERLYING)
    if chain_entry is None:
        log.warning(f"  [skip] Sem parquet para re-entrada {entry_date}")
        return None, []

    spot = float(chain_entry["underlying_price"].median())
    if spot <= 0:
        return None, []

    exp_date, dte_entry = find_target_expiration(chain_entry, entry_date)
    if exp_date is None:
        log.warning(f"  [skip] Sem expiração ~42 DTE em {entry_date}")
        return None, []

    strikes = select_16delta_strikes(chain_entry, spot, dte_entry)
    if strikes is None:
        log.warning(f"  [skip] Não encontrou strikes 16-delta em {entry_date}")
        return None, []

    iv_atm    = calc_iv_atm(chain_entry, spot, dte_entry)
    available = get_available_dates(UNDERLYING)
    del chain_entry
    gc.collect()

    # Exit na expiração (±1 dia para feriados)
    spot_exit   = float("nan")
    exit_method = "missing"
    for offset in [0, -1, 1]:
        chain_exp = load_chain(exp_date + timedelta(days=offset), UNDERLYING)
        if chain_exp is not None:
            spot_exit   = float(chain_exp["underlying_price"].median())
            exit_method = "market" if offset == 0 else f"fallback+{offset:+d}d"
            del chain_exp
            gc.collect()
            break

    if math.isnan(spot_exit) or spot_exit <= 0:
        spot_exit   = spot
        exit_method = "reinvest_fallback"

    pnl_rec = calc_pnl_expiration(
        strikes["short_put"], strikes["short_call"],
        strikes["total_credit"], spot_exit,
    )

    trade_dict: dict = dict(
        trade_date      = entry_date,
        exp_date        = exp_date,
        underlying      = UNDERLYING,
        dte_entry       = dte_entry,
        spot_entry      = round(spot, 2),
        iv_atm_entry    = round(iv_atm, 6) if iv_atm else float("nan"),
        iv_atm_pct      = round(iv_atm * 100, 2) if iv_atm else float("nan"),
        vix_entry       = float("nan"),
        exit_method     = "reinvestment",
        **strikes,
        checkpoint_date  = None,
        spot_21dte       = float("nan"),
        mid_put_21dte    = float("nan"),
        mid_call_21dte   = float("nan"),
        pnl_pts_21dte    = float("nan"),
        pnl_usd_21dte    = float("nan"),
        **pnl_rec,
    )

    daily_records = compute_daily_mtm(
        entry_date, exp_date,
        strikes["short_put"], strikes["short_call"],
        strikes["total_credit"], available, UNDERLYING,
    )

    log.info(
        f"  Re-entrada {entry_date} → {exp_date} ({dte_entry}DTE) | "
        f"Spot:{spot:>7.0f} | "
        f"Put:{strikes['short_put']:>6.0f} Call:{strikes['short_call']:>6.0f} | "
        f"Cred:{strikes['total_credit']:>6.2f}pts | "
        f"P&L:{pnl_rec['pnl_usd']:>+7.0f}$  {pnl_rec['result']}"
    )
    return trade_dict, daily_records


# ─────────────────────────────────────────────────────────────────────────────
# LOOP PRINCIPAL DE SIMULAÇÃO (recursivo)
# ─────────────────────────────────────────────────────────────────────────────

def run_reinvest_sim(
    df_orig: pd.DataFrame,
    daily_df: pd.DataFrame,
    rule: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Monthly-anchor simulation.

    The 12 monthly trades are the base.  When a close rule fires on any trade:
      - A re-entry opens the next Friday (~42 DTE).
      - The NEXT scheduled monthly slot is skipped (one-for-one swap).
      - The re-entry itself may also fire the rule → another re-entry + skip,
        recursively, until a trade expires without triggering the rule.
      - After any expiration the monthly schedule resumes.

    Trade count is always EXACTLY equal to Hold to Expiration (12).
    Worst case (rule never fires) = identical to Hold.
    """
    df_sorted = df_orig.copy()
    df_sorted["_td"] = pd.to_datetime(df_sorted["trade_date"]).dt.date
    df_sorted["_ed"] = pd.to_datetime(df_sorted["exp_date"]).dt.date
    df_sorted = df_sorted.sort_values("_td").reset_index(drop=True)
    n = len(df_sorted)

    result_trades: list[dict] = []
    result_daily:  list[dict] = list(daily_df.to_dict("records"))

    i = 0
    while i < n:
        row       = df_sorted.iloc[i]
        t_exp     = row["_ed"]
        trade_str = str(row["trade_date"])
        trade_d   = row.drop(["_td", "_ed"]).to_dict()

        result_trades.append(trade_d)
        i += 1  # advance past this monthly slot

        close_d = get_close_date(
            pd.Series(trade_d | {"trade_date": trade_str, "exp_date": t_exp}),
            rule, daily_df,
        )

        if close_d >= t_exp:
            continue  # rule never fired → advance to next monthly normally

        # ── Close rule fired: start re-entry chain ────────────────────────
        # Monthly slot is only skipped AFTER the re-entry successfully opens.
        # If the parquet is missing the monthly slot is preserved (not wasted).
        re_entry = next_friday_after(close_d)

        while True:
            t_re, daily_re = simulate_single_trade(re_entry)
            if t_re is None:
                log.warning(f"  [re-entrada] Sem parquet para {re_entry} — cadeia encerrada")
                break  # can't open re-entry → don't skip monthly

            # Re-entry opened successfully → NOW skip the next monthly slot
            if i < n:
                log.debug(f"  {str(t_re['trade_date'])} abriu → pula mensal {df_sorted.at[i, '_td']}")
                i += 1

            result_trades.append(t_re)
            result_daily.extend(daily_re)

            t_exp_re = pd.to_datetime(t_re["exp_date"]).date()

            if daily_re:
                s = pd.Series(t_re | {"trade_date": str(t_re["trade_date"])})
                dre = pd.DataFrame(daily_re)
                dre["trade_date"] = dre["trade_date"].astype(str)
                close_re = get_close_date(s, rule, dre)

                if close_re < t_exp_re:
                    # Re-entry also fired: set next re-entry (skip happens on next iteration)
                    re_entry = next_friday_after(close_re)
                    continue

            break  # re-entry expired → return to monthly schedule

    # ── Build output DataFrames ───────────────────────────────────────────
    if not result_trades:
        return df_orig, daily_df

    df_new = pd.DataFrame(result_trades)
    df_new["trade_date"] = pd.to_datetime(df_new["trade_date"]).dt.date
    df_new["exp_date"]   = pd.to_datetime(df_new["exp_date"]).dt.date
    df_new = df_new.sort_values("trade_date").reset_index(drop=True)

    daily_new = pd.DataFrame(result_daily)
    if not daily_new.empty:
        daily_new["trade_date"]    = daily_new["trade_date"].astype(str)
        # Normalise to plain YYYY-MM-DD — avoids mixed Timestamp/date format
        # issue with newer pandas on Streamlit Cloud
        daily_new["calendar_date"] = pd.to_datetime(
            daily_new["calendar_date"]
        ).dt.strftime("%Y-%m-%d")

    return df_new, daily_new


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def find_latest_csv(pattern: str) -> Path | None:
    matches = sorted(
        OUTPUT_DIR.glob(pattern),
        key=lambda p: p.stat().st_mtime, reverse=True,
    )
    return matches[0] if matches else None


def main() -> None:
    if not DATA_DIR.exists():
        sys.exit(f"[ERRO] G:/ não montado — {DATA_DIR} não encontrado")

    log.info("=" * 65)
    log.info(f"  SS42 RE-INVESTMENT SIMULATOR | {UNDERLYING}")
    log.info(f"  Close rules: {', '.join(CLOSE_RULES.keys())}")
    log.info("=" * 65)

    # Detectar CSVs base (sem _daily_ no nome)
    trade_csv = find_latest_csv(f"SS42_{UNDERLYING}_2*.csv")
    daily_csv = find_latest_csv(f"SS42_{UNDERLYING}_daily_*.csv")

    if trade_csv is None:
        sys.exit(f"[ERRO] Nenhum trade log encontrado para {UNDERLYING} em {OUTPUT_DIR}")
    if daily_csv is None:
        sys.exit(f"[ERRO] Nenhum daily MTM encontrado para {UNDERLYING} em {OUTPUT_DIR}")

    log.info(f"  Trade log: {trade_csv.name}")
    log.info(f"  Daily MTM: {daily_csv.name}")

    # Carregar CSVs base
    df_orig = pd.read_csv(trade_csv)
    df_orig["trade_date"] = pd.to_datetime(df_orig["trade_date"]).dt.date
    df_orig["exp_date"]   = pd.to_datetime(df_orig["exp_date"]).dt.date

    daily_orig = pd.read_csv(daily_csv)
    daily_orig["trade_date"]    = daily_orig["trade_date"].astype(str)
    daily_orig["calendar_date"] = pd.to_datetime(daily_orig["calendar_date"])

    log.info(f"  Trades originais: {len(df_orig)} | Daily rows: {len(daily_orig)}\n")

    # Rodar simulação para cada close rule
    for rule_key, rule_name in CLOSE_RULES.items():
        log.info(f"{'─' * 55}")
        log.info(f"  RULE: {rule_name}  [{rule_key}]")

        df_sim, daily_sim = run_reinvest_sim(df_orig, daily_orig, rule_name)

        n_orig    = len(df_orig)
        n_sim     = len(df_sim)
        n_reentry = n_sim - n_orig
        pnl_orig  = df_orig["pnl_usd"].sum()
        pnl_sim   = df_sim["pnl_usd"].sum()

        log.info(f"  Trades: {n_orig} → {n_sim}  ({n_reentry:+d} re-entradas)")
        log.info(f"  P&L base (hold to exp): ${pnl_orig:>10,.0f}")
        log.info(f"  P&L com re-entradas:    ${pnl_sim:>10,.0f}")

        # Salvar CSVs
        out_trades = OUTPUT_DIR / f"SS42_{UNDERLYING}_reinvest_{rule_key}_trades.csv"
        out_daily  = OUTPUT_DIR / f"SS42_{UNDERLYING}_reinvest_{rule_key}_daily.csv"

        df_sim.to_csv(out_trades, index=False)
        daily_sim.to_csv(out_daily, index=False)

        log.info(f"  Salvo → {out_trades.name}")
        log.info(f"  Salvo → {out_daily.name}\n")

    log.info("=" * 65)
    log.info("  CONCLUÍDO. Commite os CSVs gerados para o GitHub.")
    log.info("=" * 65)


if __name__ == "__main__":
    main()
