"""
===============================================================================
 TRIPLECAL EXPORT APP — Generate backend-compatible CSVs for Vercel app
===============================================================================
 Reads each config in data/backtest_triplecalendar/raw/, pairs PP+CC,
 enriches with VIX entry (yfinance ^VIX close-of-day as proxy for 15:45 ET),
 and writes trades.csv + daily.csv in the schema expected by apps/api/main.py
 _scan_close_rule().

 OUTPUT: reports/triplecal_backtest_app/{tag}/trades.csv + daily.csv
===============================================================================
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd
import yfinance as yf

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from triplecal_backtest import (  # type: ignore
    RAW_DIR,
    build_combined_settlement,
    load_component,
    pair_trades,
    trade_mtm_series,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("export")

OUT_DIR = REPO_ROOT / "reports" / "triplecal_backtest_app"

CONFIGS = [
    "SPX_7-10_PPC_d16",
    "SPX_7-14_PPC_d16",
    "SPX_14-17_PPC_d16",
    "SPX_14-21_PPC_d16",
    "SPX_21-24_PPC_d16",
    "SPX_21-28_PPC_d16",
    "SPX_7-10_PCC_d16",
    "SPX_7-14_PCC_d16",
    "SPX_14-21_PCC_d16",
    "SPX_21-28_PCC_d16",
]


VIX_CACHE = REPO_ROOT / "data" / "cache" / "vix_daily.parquet"


def fetch_vix(start: str = "2021-05-01", end: str = "2026-05-15") -> pd.DataFrame:
    if VIX_CACHE.exists():
        log.info("VIX cache hit: %s", VIX_CACHE)
        out = pd.read_parquet(VIX_CACHE)
        out["date"] = pd.to_datetime(out["date"]).dt.normalize()
        log.info("VIX (cached): %d daily rows", len(out))
        return out

    # Primary: Cboe official CSV (free, no API key)
    import io
    import urllib.request

    log.info("Fetching VIX from Cboe...")
    url = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode("utf-8")
        v = pd.read_csv(io.StringIO(raw))
        v.columns = [c.lower() for c in v.columns]
        v["date"] = pd.to_datetime(v["date"], format="%m/%d/%Y").dt.normalize()
        v = v[(v["date"] >= pd.Timestamp(start)) & (v["date"] <= pd.Timestamp(end))]
        out = v[["date", "close"]].rename(columns={"close": "vix"})
    except Exception as exc:
        log.warning("Cboe failed: %s — falling back to yfinance", exc)
        v = yf.download("^VIX", start=start, end=end, progress=False, auto_adjust=False)
        if isinstance(v.columns, pd.MultiIndex):
            v.columns = v.columns.droplevel(1)
        v.index = pd.to_datetime(v.index).normalize()
        out = (
            v[["Close"]]
            .rename(columns={"Close": "vix"})
            .reset_index()
            .rename(columns={"Date": "date"})
        )
        out["date"] = pd.to_datetime(out["date"]).dt.normalize()

    out = out.dropna(subset=["vix"]).reset_index(drop=True)
    VIX_CACHE.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(VIX_CACHE, index=False)
    log.info("VIX: %d daily rows (cached to %s)", len(out), VIX_CACHE)
    return out


def vix_at(date: pd.Timestamp, vix_df: pd.DataFrame) -> float | None:
    d = pd.Timestamp(date).normalize()
    exact = vix_df[vix_df["date"] == d]
    if len(exact):
        return float(exact["vix"].iloc[0])
    prior = vix_df[vix_df["date"] <= d].tail(1)
    if len(prior):
        return float(prior["vix"].iloc[0])
    return None


def export_config(tag: str, vix_df: pd.DataFrame) -> None:
    folder = RAW_DIR / tag
    pp = load_component(folder, "pp")
    cc = load_component(folder, "cc")
    pairs = pair_trades(pp, cc)
    combined_cum = build_combined_settlement(pp, cc)

    # Infer short_DTE from folder name e.g. "SPX_21-28_PPC_d16" -> 21
    short_dte = int(tag.split("_")[1].split("-")[0])

    trades_rows: list[dict] = []
    daily_rows: list[dict] = []

    for _, t in pairs.iterrows():
        premium = float(t["combined_premium"])
        pnl = float(t["combined_pnl_final"])
        open_dt = pd.Timestamp(t["Opened"])
        close_dt = pd.Timestamp(t["Closed"])
        vix_e = vix_at(open_dt, vix_df)

        trades_rows.append(
            {
                "trade_date": open_dt.strftime("%Y-%m-%d"),
                "exp_date": close_dt.strftime("%Y-%m-%d"),
                "underlying": "SPX",
                "dte_entry": short_dte,
                "total_credit": round(premium, 2),
                "pnl_usd": round(pnl, 2),
                "vix_entry": round(vix_e, 2) if vix_e is not None else None,
                "result": "WIN" if pnl > 0 else "LOSS",
                "exit_method": "expiration",
                "in_range": bool(pnl > 0),
            }
        )

        mtm = trade_mtm_series(open_dt, close_dt, combined_cum)
        for _, day in mtm.iterrows():
            dsop = (day["Date"] - open_dt).days
            dte_rem = max(short_dte - dsop, 0)
            daily_rows.append(
                {
                    "trade_date": open_dt.strftime("%Y-%m-%d"),
                    "calendar_date": pd.Timestamp(day["Date"]).strftime("%Y-%m-%d"),
                    "dte_remaining": dte_rem,
                    "pnl_usd": round(float(day["combined_mtm"]), 2),
                }
            )

    trades_df = pd.DataFrame(trades_rows)
    daily_df = pd.DataFrame(daily_rows)

    out = OUT_DIR / tag
    out.mkdir(parents=True, exist_ok=True)
    trades_df.to_csv(out / "trades.csv", index=False)
    daily_df.to_csv(out / "daily.csv", index=False)

    n_vix = trades_df["vix_entry"].notna().sum()
    vix_med = trades_df["vix_entry"].median()
    log.info(
        "%s: trades=%d daily=%d | vix_entry: %d/%d not-null, median=%.1f",
        tag,
        len(trades_df),
        len(daily_df),
        n_vix,
        len(trades_df),
        vix_med if pd.notna(vix_med) else 0.0,
    )


def main() -> None:
    vix_df = fetch_vix()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for tag in CONFIGS:
        try:
            export_config(tag, vix_df)
        except Exception as exc:
            log.error("FAILED %s: %s", tag, exc)
    log.info("Export done -> %s", OUT_DIR)


if __name__ == "__main__":
    main()
