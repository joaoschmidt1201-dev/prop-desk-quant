"""
===============================================================================
 TRIPLE CALENDAR BACKTEST — Synthetic Combine + TP/SL Grid
 Prop Desk Quant | Senior Quant Developer
===============================================================================
 Combina dois backtests tastytrade (2 Put Calendars + 1 Call Calendar) num
 Triple Calendar sintetico (PPC, 6-leg). Simula grid de TP/SL post-hoc sobre
 o premium combinado real.

 PRE-REQS (tastytrade backtester, ambos):
   - Entry: Friday, max 1 active, close-oldest-and-enter-new, $100k cap
   - Exit: "days in trade" = short_DTE - 1, SEM TP/SL, SEM VIX filter

 INPUTS (em data/backtest_triplecalendar/raw/{tag}/):
   pp_Trades.csv, pp_Orders.csv, pp_Transactions.csv, pp_Daily_Settlement.csv
   cc_Trades.csv, cc_Orders.csv, cc_Transactions.csv, cc_Daily_Settlement.csv

 USO:
   python scripts/triplecal_backtest.py SPX_7-14_d16

 OUTPUTS (em reports/triplecal_backtest/{tag}/):
   combined_trades.csv      Pareamento PP+CC com mtm diario
   tp_grid_metrics.csv      Metricas por TP level
   equity_curves.png        Curvas por TP level
   summary.md               Sumario textual
===============================================================================
"""

from __future__ import annotations

import argparse
import logging
import math
import sys
from datetime import date, datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("triplecal")


REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / "data" / "backtest_triplecalendar" / "raw"
OUT_DIR = REPO_ROOT / "reports" / "triplecal_backtest"

TP_GRID = [None, 0.10, 0.20, 0.25, 0.50]
SL_PCT = 1.00


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def _parse_dt(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, format="%d/%m/%Y", errors="coerce")


def load_component(folder: Path, prefix: str) -> dict:
    """Carrega os 4 CSVs de um componente (pp_ ou cc_). Transactions é opcional."""
    trades = pd.read_csv(folder / f"{prefix}_Trades.csv")
    orders = pd.read_csv(folder / f"{prefix}_Orders.csv")
    settle = pd.read_csv(folder / f"{prefix}_Daily_Settlement.csv")

    txns_path = folder / f"{prefix}_Transactions.csv"
    if txns_path.exists():
        txns = pd.read_csv(txns_path)
        txns["Date"] = _parse_dt(txns["Date"])
    else:
        log.warning("[%s] Transactions.csv ausente (nao usado no fluxo principal)", prefix)
        txns = None

    trades["Opened"] = _parse_dt(trades["Opened"])
    trades["Closed"] = _parse_dt(trades["Closed"])
    settle["Date"] = _parse_dt(settle["Date"])
    orders["Date"] = _parse_dt(orders["Date"])

    # Premium signed: tastytrade exporta negativo para debit; usamos abs
    trades["Premium_abs"] = trades["Premium"].abs()

    # Detecta tipo pelo primeiro Orders entry de abertura
    first_open = orders[orders["Effect"] == "debit"].iloc[0]["Legs"]
    puts = first_open.lower().count(" put ")
    calls = first_open.lower().count(" call ")
    component_type = "PP" if puts > calls else "CC"

    log.info(
        "[%s] %d trades | premium media $%.0f | legs detectadas puts=%d calls=%d -> %s",
        prefix,
        len(trades),
        trades["Premium_abs"].mean(),
        puts,
        calls,
        component_type,
    )

    return {
        "trades": trades,
        "orders": orders,
        "txns": txns,
        "settle": settle,
        "type": component_type,
    }


# ---------------------------------------------------------------------------
# Pairing
# ---------------------------------------------------------------------------

def pair_trades(pp: dict, cc: dict) -> pd.DataFrame:
    """Pareia PP e CC pela data de abertura. Valida fechamento sincronizado."""
    pp_t = pp["trades"][["Opened", "Closed", "Premium_abs", "Profit/loss", "Fees"]].copy()
    pp_t.columns = ["Opened", "pp_Closed", "pp_Premium", "pp_PnL", "pp_Fees"]

    cc_t = cc["trades"][["Opened", "Closed", "Premium_abs", "Profit/loss", "Fees"]].copy()
    cc_t.columns = ["Opened", "cc_Closed", "cc_Premium", "cc_PnL", "cc_Fees"]

    merged = pp_t.merge(cc_t, on="Opened", how="inner")
    dropped_pp = len(pp_t) - len(merged)
    dropped_cc = len(cc_t) - len(merged)
    if dropped_pp or dropped_cc:
        log.warning(
            "Trades nao pareados: PP=%d, CC=%d (mantidos %d)",
            dropped_pp,
            dropped_cc,
            len(merged),
        )

    mismatch = merged[merged["pp_Closed"] != merged["cc_Closed"]]
    if len(mismatch):
        log.warning(
            "%d trades com Closed dates divergentes (esperado 0 com DIT correto)",
            len(mismatch),
        )
        log.warning("Exemplo:\n%s", mismatch.head(3).to_string())

    merged["combined_premium"] = merged["pp_Premium"] + merged["cc_Premium"]
    merged["combined_pnl_final"] = merged["pp_PnL"] + merged["cc_PnL"]
    merged["combined_fees"] = merged["pp_Fees"] + merged["cc_Fees"]
    # Close date: usa o pp_Closed (deve igualar cc_Closed)
    merged["Closed"] = merged["pp_Closed"]
    merged["trade_id"] = range(1, len(merged) + 1)

    log.info(
        "Trades pareados: %d | premium combinado medio $%.0f | pnl final medio $%.2f",
        len(merged),
        merged["combined_premium"].mean(),
        merged["combined_pnl_final"].mean(),
    )
    return merged


# ---------------------------------------------------------------------------
# Daily mark-to-market per trade
# ---------------------------------------------------------------------------

def build_combined_settlement(pp: dict, cc: dict) -> pd.DataFrame:
    """Soma cumulativa PP+CC alinhada por data."""
    p = pp["settle"][["Date", "Total profit/loss"]].rename(columns={"Total profit/loss": "pp_cum"})
    c = cc["settle"][["Date", "Total profit/loss"]].rename(columns={"Total profit/loss": "cc_cum"})
    df = p.merge(c, on="Date", how="outer").sort_values("Date").reset_index(drop=True)
    df["pp_cum"] = df["pp_cum"].ffill().fillna(0.0)
    df["cc_cum"] = df["cc_cum"].ffill().fillna(0.0)
    df["combined_cum"] = df["pp_cum"] + df["cc_cum"]
    return df


def trade_mtm_series(
    trade_open: pd.Timestamp,
    trade_close: pd.Timestamp,
    combined_cum: pd.DataFrame,
) -> pd.DataFrame:
    """Retorna mark-to-market diario de UM trade combinando settlements."""
    # Baseline = cumulativo no dia anterior ao open
    prior = combined_cum[combined_cum["Date"] < trade_open]
    base_pp = float(prior["pp_cum"].iloc[-1]) if len(prior) else 0.0
    base_cc = float(prior["cc_cum"].iloc[-1]) if len(prior) else 0.0

    window = combined_cum[
        (combined_cum["Date"] >= trade_open) & (combined_cum["Date"] <= trade_close)
    ].copy()
    window["pp_mtm"] = window["pp_cum"] - base_pp
    window["cc_mtm"] = window["cc_cum"] - base_cc
    window["combined_mtm"] = window["pp_mtm"] + window["cc_mtm"]
    return window[["Date", "pp_mtm", "cc_mtm", "combined_mtm"]]


# ---------------------------------------------------------------------------
# TP/SL simulation
# ---------------------------------------------------------------------------

def simulate_tp_sl(
    pairs: pd.DataFrame,
    combined_cum: pd.DataFrame,
    tp_pct: float | None,
    sl_pct: float = SL_PCT,
) -> pd.DataFrame:
    """
    Para cada trade pareado, varre dias e aplica TP/SL sobre o premium combinado.
    Retorna DataFrame com pnl final simulado por trade.
    """
    rows = []
    for _, t in pairs.iterrows():
        premium = t["combined_premium"]
        tp_thr = tp_pct * premium if tp_pct is not None else None
        sl_thr = -sl_pct * premium

        mtm = trade_mtm_series(t["Opened"], t["Closed"], combined_cum)
        if mtm.empty:
            rows.append(
                {
                    "trade_id": t["trade_id"],
                    "Opened": t["Opened"],
                    "Closed": t["Closed"],
                    "exit_reason": "no_data",
                    "pnl": t["combined_pnl_final"],
                    "premium": premium,
                }
            )
            continue

        exit_reason = "expiration"
        final_pnl = t["combined_pnl_final"]
        exit_date = t["Closed"]

        for _, day in mtm.iterrows():
            val = day["combined_mtm"]
            if tp_thr is not None and val >= tp_thr:
                exit_reason = "take_profit"
                final_pnl = tp_thr
                exit_date = day["Date"]
                break
            if val <= sl_thr:
                exit_reason = "stop_loss"
                final_pnl = sl_thr
                exit_date = day["Date"]
                break

        rows.append(
            {
                "trade_id": t["trade_id"],
                "Opened": t["Opened"],
                "Closed": exit_date,
                "exit_reason": exit_reason,
                "pnl": final_pnl,
                "premium": premium,
            }
        )

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def _drawdown(equity: pd.Series) -> pd.Series:
    return equity - equity.cummax()


def _sharpe(pnl: pd.Series, freq: float = 52.0) -> float:
    if len(pnl) < 2 or pnl.std() == 0:
        return float("nan")
    return float((pnl.mean() / pnl.std()) * math.sqrt(freq))


def _profit_factor(pnl: pd.Series) -> float:
    wins = pnl[pnl > 0].sum()
    losses = abs(pnl[pnl < 0].sum())
    return float(wins / losses) if losses > 0 else float("inf")


def compute_metrics(sim: pd.DataFrame, starting_capital: float = 100_000.0) -> dict:
    pnl = sim["pnl"].astype(float)
    n = len(pnl)
    wins = (pnl > 0).sum()
    win_rate = wins / n if n else 0.0
    total = pnl.sum()
    avg = pnl.mean()
    sharpe = _sharpe(pnl)
    pf = _profit_factor(pnl)

    sim_sorted = sim.sort_values("Closed").reset_index(drop=True)
    equity = starting_capital + sim_sorted["pnl"].cumsum()
    dd = _drawdown(equity)
    max_dd = float(dd.min())
    max_dd_pct = max_dd / starting_capital * 100.0

    if n:
        days = (sim_sorted["Closed"].iloc[-1] - sim_sorted["Closed"].iloc[0]).days
        years = max(days / 365.25, 1e-9)
        end_eq = float(equity.iloc[-1])
        cagr = (end_eq / starting_capital) ** (1 / years) - 1 if end_eq > 0 else -1.0
    else:
        cagr = float("nan")

    return {
        "trades": n,
        "win_rate": round(win_rate * 100, 2),
        "avg_pnl": round(float(avg), 2),
        "total_pnl": round(float(total), 2),
        "sharpe": round(sharpe, 3),
        "profit_factor": round(pf, 3),
        "max_dd_usd": round(max_dd, 2),
        "max_dd_pct": round(max_dd_pct, 2),
        "cagr_pct": round(cagr * 100, 2),
        "final_equity": round(float(equity.iloc[-1]) if n else starting_capital, 2),
        "exits_tp": int((sim["exit_reason"] == "take_profit").sum()),
        "exits_sl": int((sim["exit_reason"] == "stop_loss").sum()),
        "exits_exp": int((sim["exit_reason"] == "expiration").sum()),
    }


# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------

def plot_equity_curves(curves: dict[str, pd.DataFrame], outpath: Path, tag: str):
    fig, ax = plt.subplots(figsize=(12, 6))
    for label, df in curves.items():
        ax.plot(df["Closed"], df["equity"], label=label, linewidth=1.5)
    ax.set_title(f"Triple Calendar PPC — {tag} — Equity Curves por TP")
    ax.set_xlabel("Data")
    ax.set_ylabel("Equity (USD)")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(outpath, dpi=110)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(tag: str, starting_capital: float = 100_000.0) -> None:
    folder = RAW_DIR / tag
    if not folder.exists():
        log.error("Pasta nao encontrada: %s", folder)
        sys.exit(1)

    out = OUT_DIR / tag
    out.mkdir(parents=True, exist_ok=True)

    log.info("=" * 70)
    log.info("Triple Calendar Backtest — %s", tag)
    log.info("=" * 70)

    pp = load_component(folder, "pp")
    cc = load_component(folder, "cc")
    if pp["type"] != "PP":
        log.warning("pp_* nao identificado como PP (detectado %s)", pp["type"])
    if cc["type"] != "CC":
        log.warning("cc_* nao identificado como CC (detectado %s)", cc["type"])

    pairs = pair_trades(pp, cc)
    pairs.to_csv(out / "combined_trades.csv", index=False)
    log.info("combined_trades.csv -> %s", out / "combined_trades.csv")

    combined_cum = build_combined_settlement(pp, cc)

    metrics_rows = []
    equity_curves = {}
    for tp in TP_GRID:
        tp_label = f"TP={int(tp*100)}%" if tp is not None else "TP=none"
        sim = simulate_tp_sl(pairs, combined_cum, tp_pct=tp, sl_pct=SL_PCT)
        m = compute_metrics(sim, starting_capital)
        m["tp"] = tp_label
        metrics_rows.append(m)

        sim_sorted = sim.sort_values("Closed").reset_index(drop=True)
        sim_sorted["equity"] = starting_capital + sim_sorted["pnl"].cumsum()
        equity_curves[tp_label] = sim_sorted[["Closed", "equity"]]
        sim.to_csv(out / f"trades_{tp_label.replace('%', 'pct').replace('=', '_')}.csv", index=False)

    metrics = pd.DataFrame(metrics_rows)
    cols = ["tp"] + [c for c in metrics.columns if c != "tp"]
    metrics = metrics[cols]
    metrics.to_csv(out / "tp_grid_metrics.csv", index=False)
    log.info("tp_grid_metrics.csv:\n%s", metrics.to_string(index=False))

    plot_equity_curves(equity_curves, out / "equity_curves.png", tag)
    log.info("equity_curves.png -> %s", out / "equity_curves.png")

    # Summary markdown
    summary = [
        f"# Triple Calendar PPC — {tag}",
        "",
        f"**Janela:** {pairs['Opened'].min().date()} -> {pairs['Closed'].max().date()}",
        f"**Trades pareados:** {len(pairs)}",
        f"**Premium combinado medio:** ${pairs['combined_premium'].mean():.0f}",
        "",
        "## Grid TP",
        "",
        metrics.to_string(index=False),
    ]
    (out / "summary.md").write_text("\n".join(summary), encoding="utf-8")
    log.info("summary.md -> %s", out / "summary.md")
    log.info("DONE.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Triple Calendar combine + TP grid sim")
    parser.add_argument("tag", help="Pasta dentro de data/backtest_triplecalendar/raw/")
    parser.add_argument("--capital", type=float, default=100_000.0)
    args = parser.parse_args()
    run(args.tag, args.capital)


if __name__ == "__main__":
    main()
