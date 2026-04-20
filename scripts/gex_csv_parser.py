#!/usr/bin/env python3
"""
gex_csv_parser.py
─────────────────
Reads a Barchart GEX CSV (SPX or NDX/IUXX) and:
  1. Calculates all GEX levels (Gamma Flip, p1/p2/p3, n1/n2/n3, coi, poi, agg, zones, confluences)
  2. Saves to gex_history_spx.json or gex_history_ndx.json
  3. Regenerates tradingview/gex_weekly_levels.pine (single indicator — auto-switches SPX ↔ NDX)
  4. Prints terminal summary with distances to spot

Usage:
  python scripts/gex_csv_parser.py "data/$SPX-gamma-levels-exp-20260421-weekly.csv" --week 2026-04-14
  python scripts/gex_csv_parser.py "data/$IUXX-gamma-levels-exp-20260421-monthly.csv" --week 2026-04-14
"""

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta
from io import StringIO
from pathlib import Path

import pandas as pd

try:
    import yfinance as yf
    HAS_YF = True
except ImportError:
    HAS_YF = False

try:
    import pytz
    ET = pytz.timezone("America/New_York")
    HAS_PYTZ = True
except ImportError:
    HAS_PYTZ = False

ROOT      = Path(__file__).parent.parent
PINE_FILE = ROOT / "tradingview" / "gex_weekly_levels.pine"

# ─── TICKER CONFIGURATION ─────────────────────────────────────────────────────

TICKER_CONFIG = {
    "SPX": {
        "filename_prefix": "$SPX-",
        "yf_symbol":       "^GSPC",
        "strike_min":      4000,
        "strike_max":      10000,
        "history_file":    ROOT / "gex_history_spx.json",
        "conf_tol":        5,
    },
    "NDX": {
        "filename_prefix": "$IUXX-",
        "yf_symbol":       "^NDX",
        "strike_min":      15000,
        "strike_max":      30000,
        "history_file":    ROOT / "gex_history_ndx.json",
        "conf_tol":        25,
    },
}

# ─── PINE TEMPLATE ────────────────────────────────────────────────────────────

PINE_TEMPLATE = """\
//@version=5
// =======================================================================
// GEX Weekly Levels [TradingLitt Style] — SPX + NDX — AUTO-GENERATED
// DO NOT EDIT MANUALLY. Regenerate via:
//   python scripts/gex_csv_parser.py <csv_path> --week YYYY-MM-DD
// Last updated : {generated_date}
// Weeks stored : {total_weeks}
// =======================================================================
indicator("GEX Weekly Levels [TradingLitt]", overlay=true, max_lines_count=500, max_labels_count=500, shorttitle="GEX Levels")

// --- TICKER DETECTION -----------------------------------------------
_is_spx = syminfo.ticker == "SPX" or str.contains(syminfo.ticker, "ES1")
_is_ndx = syminfo.ticker == "NDX" or str.contains(syminfo.ticker, "NQ1")
_valid  = _is_spx or _is_ndx

// --- INPUTS (Colors) ------------------------------------------------
var string _GC = "Colors"
C_GFLIP = input.color(color.rgb(128, 0, 200),   "Gamma Flip",    group=_GC, display=display.none)
C_POS   = input.color(color.rgb(0, 200, 83),    "Positive GEX",  group=_GC, display=display.none)
C_NEG   = input.color(color.rgb(255, 23, 68),   "Negative GEX",  group=_GC, display=display.none)
C_AGG   = input.color(color.rgb(170, 0, 255),   "Aggregate",     group=_GC, display=display.none)
C_SEP_W = input.color(color.new(color.gray, 40), "Sep. Monday",  group=_GC, display=display.none)
C_SEP_D = input.color(color.new(color.gray, 72), "Sep. Tue-Thu", group=_GC, display=display.none)

// --- INPUTS (Styles) ------------------------------------------------
var string _GS = "Styles"
STY_GFLIP = input.string("Dashed",  "Gamma Flip",    options=["Solid", "Dashed", "Dotted"], group=_GS, display=display.none)
STY_P1    = input.string("Solid",   "Pos GEX p1",    options=["Solid", "Dashed", "Dotted"], group=_GS, display=display.none)
STY_P2    = input.string("Dashed",  "Pos GEX p2",    options=["Solid", "Dashed", "Dotted"], group=_GS, display=display.none)
STY_P3    = input.string("Dotted",  "Pos GEX p3",    options=["Solid", "Dashed", "Dotted"], group=_GS, display=display.none)
STY_N1    = input.string("Solid",   "Neg GEX n1",    options=["Solid", "Dashed", "Dotted"], group=_GS, display=display.none)
STY_N2    = input.string("Dashed",  "Neg GEX n2",    options=["Solid", "Dashed", "Dotted"], group=_GS, display=display.none)
STY_N3    = input.string("Dotted",  "Neg GEX n3",    options=["Solid", "Dashed", "Dotted"], group=_GS, display=display.none)
STY_AGG   = input.string("Dotted",  "Aggregate",     options=["Solid", "Dashed", "Dotted"], group=_GS, display=display.none)
STY_SEP_W = input.string("Dashed",  "Sep. Monday",   options=["Solid", "Dashed", "Dotted"], group=_GS, display=display.none)
STY_SEP_D = input.string("Dashed",  "Sep. Tue-Thu",  options=["Solid", "Dashed", "Dotted"], group=_GS, display=display.none)

// --- INPUTS (Widths) ------------------------------------------------
var string _GW = "Widths"
LW_GFLIP  = input.int(2, "Gamma Flip",   minval=1, maxval=4, group=_GW, display=display.none)
LW_P1     = input.int(2, "Pos GEX p1",   minval=1, maxval=4, group=_GW, display=display.none)
LW_P2     = input.int(1, "Pos GEX p2",   minval=1, maxval=4, group=_GW, display=display.none)
LW_P3     = input.int(1, "Pos GEX p3",   minval=1, maxval=4, group=_GW, display=display.none)
LW_N1     = input.int(2, "Neg GEX n1",   minval=1, maxval=4, group=_GW, display=display.none)
LW_N2     = input.int(1, "Neg GEX n2",   minval=1, maxval=4, group=_GW, display=display.none)
LW_N3     = input.int(1, "Neg GEX n3",   minval=1, maxval=4, group=_GW, display=display.none)
LW_AGG    = input.int(1, "Aggregate",    minval=1, maxval=4, group=_GW, display=display.none)
LW_SEP_W  = input.int(2, "Sep. Monday",  minval=1, maxval=4, group=_GW, display=display.none)
LW_SEP_D  = input.int(2, "Sep. Tue-Thu", minval=1, maxval=4, group=_GW, display=display.none)

f_style(s) =>
    s == "Solid" ? line.style_solid : s == "Dotted" ? line.style_dotted : line.style_dashed

// True on the first 15m bar of a given Monday (by timestamp)
is_week_start(ts) => time >= ts and (na(time[1]) or time[1] < ts)

// 15m chart: 26 bars/day, 130 bars/week
W = 130
D = 26

// --- MONDAY BAR INDEX DETECTION (auto-generated) --------------------
{bi_vars}

{bi_detections}

// --- GLOBAL LINE / LABEL STORAGE ------------------------------------
var line[]  _lines  = array.new_line()
var label[] _labels = array.new_label()

// --- REDRAW ON LAST BAR (delete all → redraw with current inputs) ---
if barstate.islast and _valid
    for l in _lines
        line.delete(l)
    array.clear(_lines)
    for lb in _labels
        label.delete(lb)
    array.clear(_labels)
{draw_weeks_block}
"""

# ─── CSV LOADING ──────────────────────────────────────────────────────────────

def detect_ticker(csv_path: Path, override: str | None = None) -> str:
    if override:
        if override not in TICKER_CONFIG:
            raise ValueError(f"Invalid ticker: {override}. Choose SPX or NDX.")
        return override
    name = csv_path.name
    for ticker, cfg in TICKER_CONFIG.items():
        if name.startswith(cfg["filename_prefix"]):
            return ticker
    raise ValueError(
        f"Cannot detect ticker from filename '{name}'.\n"
        f"Expected prefix: {[c['filename_prefix'] for c in TICKER_CONFIG.values()]}\n"
        f"Use --ticker SPX|NDX to override."
    )


def load_csv(csv_path: Path, ticker: str) -> pd.DataFrame:
    raw   = csv_path.read_text(encoding="utf-8", errors="replace")
    lines = [l for l in raw.splitlines() if not l.startswith("Downloaded from")]
    df    = pd.read_csv(StringIO("\n".join(lines)))

    # Drop non-numeric strike rows (extra footer lines)
    df = df[pd.to_numeric(df["Strike"], errors="coerce").notna()].copy()

    float_cols = [
        "Strike", "Call Gamma Exposure", "Put Gamma Exposure",
        "Net Gamma Exposure", "Absolute Gamma Exposure",
        "Call Open Interest", "Put Open Interest", "Gamma Exposure Profile",
    ]
    for col in float_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    cfg = TICKER_CONFIG[ticker]
    df  = df[(df["Strike"] >= cfg["strike_min"]) & (df["Strike"] <= cfg["strike_max"])].copy()
    df  = df.dropna(subset=["Strike", "Gamma Exposure Profile"])
    df  = df.sort_values("Strike").reset_index(drop=True)

    if df.empty:
        raise ValueError(
            f"No valid strikes for {ticker} ({cfg['strike_min']}–{cfg['strike_max']})"
        )
    return df

# ─── LEVEL CALCULATIONS ───────────────────────────────────────────────────────

def calc_gamma_flip(df: pd.DataFrame) -> int:
    profile = df["Gamma Exposure Profile"].values
    strikes = df["Strike"].values
    for i in range(len(profile) - 1):
        a, b = profile[i], profile[i + 1]
        if (a <= 0 < b) or (b <= 0 < a):
            s1, s2 = strikes[i], strikes[i + 1]
            t = -a / (b - a) if (b - a) != 0 else 0.5
            return round(s1 + t * (s2 - s1))
    # Fallback: strike closest to zero in the profile
    return int(df.loc[df["Gamma Exposure Profile"].abs().idxmin(), "Strike"])


def top_strikes(series: pd.Series, strikes: pd.Series, n: int) -> list[int]:
    """Top-N strikes by absolute magnitude of series, sorted by descending magnitude."""
    df_tmp = pd.DataFrame({"val": series.abs(), "strike": strikes})
    top    = df_tmp.nlargest(n, "val")
    # Return in descending magnitude order
    return [int(s) for s in top.sort_values("val", ascending=False)["strike"].tolist()]


def detect_confluences(levels: dict, tol: int) -> list[int]:
    """Strikes where ≥2 distinct categories land within ±tol points."""
    cat_strikes: dict[str, list[int]] = {}
    for cat in ("gflip", "pos", "neg", "coi", "poi", "agg", "pos_zone", "neg_zone"):
        val = levels.get(cat)
        if val is None:
            continue
        cat_strikes[cat] = val if isinstance(val, list) else [val]

    # Build flat list of (cat, strike) pairs
    pairs = [(cat, s) for cat, strikes in cat_strikes.items() for s in strikes if s]

    conf_set = set()
    for i, (cat1, s1) in enumerate(pairs):
        for cat2, s2 in pairs[i + 1:]:
            if cat1 != cat2 and abs(s1 - s2) <= tol:
                conf_set.add(s1)
                conf_set.add(s2)

    return sorted(conf_set)


def calculate_levels(df: pd.DataFrame, ticker: str) -> dict:
    cfg   = TICKER_CONFIG[ticker]
    gflip = calc_gamma_flip(df)

    # Positive GEX levels: top-3 strikes with highest positive Net GEX (Call Walls)
    pos_rows = df[df["Net Gamma Exposure"] > 0].nlargest(3, "Net Gamma Exposure")
    pos = [int(s) for s in pos_rows.sort_values("Net Gamma Exposure", ascending=False)["Strike"].tolist()]

    # Negative GEX levels: top-3 strikes with most negative Net GEX (Put Walls)
    neg_rows = df[df["Net Gamma Exposure"] < 0].nsmallest(3, "Net Gamma Exposure")
    neg = [int(s) for s in neg_rows.sort_values("Net Gamma Exposure")["Strike"].tolist()]

    coi      = top_strikes(df["Call Open Interest"],  df["Strike"], 2)
    poi      = top_strikes(df["Put Open Interest"],   df["Strike"], 2)
    agg_idx  = df["Absolute Gamma Exposure"].idxmax()
    agg      = int(df.loc[agg_idx, "Strike"])

    above    = df[df["Strike"] > gflip]
    pos_zone_rows = above[above["Gamma Exposure Profile"] > 0]
    pos_zone = int(pos_zone_rows["Strike"].iloc[0]) if not pos_zone_rows.empty else None

    below    = df[df["Strike"] < gflip]
    neg_zone_rows = below[below["Gamma Exposure Profile"] < 0]
    neg_zone = int(neg_zone_rows["Strike"].iloc[-1]) if not neg_zone_rows.empty else None

    levels = {
        "gflip":    gflip,
        "pos":      pos,
        "neg":      neg,
        "coi":      coi,
        "poi":      poi,
        "agg":      agg,
        "pos_zone": pos_zone,
        "neg_zone": neg_zone,
    }
    levels["conf"] = detect_confluences(levels, cfg["conf_tol"])
    return levels

# ─── SPOT PRICE ───────────────────────────────────────────────────────────────

def get_spot(ticker: str) -> float | None:
    if not HAS_YF:
        return None
    try:
        sym  = TICKER_CONFIG[ticker]["yf_symbol"]
        hist = yf.Ticker(sym).history(period="2d", auto_adjust=True)
        return round(float(hist["Close"].iloc[-1]), 2) if not hist.empty else None
    except Exception:
        return None

# ─── TERMINAL SUMMARY ────────────────────────────────────────────────────────

def print_summary(levels: dict, ticker: str, week_date: str, spot: float | None):
    sep = "=" * 68
    print(f"\n{sep}")
    print(f"  GEX LEVELS -- {ticker} -- week of {week_date}")
    if spot:
        print(f"  Spot {ticker}: {spot:,.2f}")
    print(sep)

    def dist(price: int) -> str:
        if spot and price:
            d = round(price - spot)
            return f"({d:+,} pts)"
        return ""

    def fmt(vals: list[int] | int | None) -> str:
        if vals is None:
            return "(none)"
        lst = vals if isinstance(vals, list) else [vals]
        return "  |  ".join(f"{v:,} {dist(v)}" for v in lst if v)

    rows = [
        ("Gamma Flip",  levels.get("gflip")),
        ("p1",          [levels["pos"][0]] if levels.get("pos") else None),
        ("p2",          [levels["pos"][1]] if len(levels.get("pos", [])) > 1 else None),
        ("p3",          [levels["pos"][2]] if len(levels.get("pos", [])) > 2 else None),
        ("n1",          [levels["neg"][0]] if levels.get("neg") else None),
        ("n2",          [levels["neg"][1]] if len(levels.get("neg", [])) > 1 else None),
        ("n3",          [levels["neg"][2]] if len(levels.get("neg", [])) > 2 else None),
        ("Call OI",     levels.get("coi")),
        ("Put OI",      levels.get("poi")),
        ("Aggregate",   levels.get("agg")),
        ("Pos Zone",    levels.get("pos_zone")),
        ("Neg Zone",    levels.get("neg_zone")),
        ("Confluences", levels.get("conf")),
    ]
    for label, vals in rows:
        if vals is not None:
            print(f"  {label:<14} ->  {fmt(vals)}")
    print(sep)
    print()

# ─── HISTORY ─────────────────────────────────────────────────────────────────

def load_history(ticker: str) -> list:
    path = TICKER_CONFIG[ticker]["history_file"]
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return []


def save_history(
    ticker: str,
    week_date: str,
    expiry: str,
    levels: dict,
    source_file: str,
) -> list:
    history = load_history(ticker)
    entry   = {
        "week":        week_date,
        "ticker":      ticker,
        "expiry":      expiry,
        "gflip":       levels["gflip"],
        "pos":         levels["pos"],
        "neg":         levels["neg"],
        "coi":         levels["coi"],
        "poi":         levels["poi"],
        "agg":         levels["agg"],
        "pos_zone":    levels["pos_zone"],
        "neg_zone":    levels["neg_zone"],
        "conf":        levels["conf"],
        "source_file": source_file,
    }
    updated = sorted(
        [e for e in history if e["week"] != week_date] + [entry],
        key=lambda e: e["week"],
    )
    path = TICKER_CONFIG[ticker]["history_file"]
    path.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  [{ticker}] History saved: {len(updated)} week(s) -> {path.name}")
    return updated

# ─── PINE GENERATION ─────────────────────────────────────────────────────────

def monday_ts_ms(date_str: str) -> int:
    if HAS_PYTZ:
        naive = datetime.strptime(date_str, "%Y-%m-%d").replace(hour=9, minute=30)
        return int(ET.localize(naive).timestamp() * 1000)
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(hour=14, minute=30)
    return int(dt.timestamp() * 1000)


def _pf(val) -> str:
    """Format a price value as Pine float literal, or 'float(na)' if missing."""
    return f"{float(val):.1f}" if val is not None else "float(na)"


def _is_conf(price: int | None, conf_list: list[int], tol: int) -> bool:
    if price is None:
        return False
    return any(abs(price - c) <= tol for c in conf_list)


# Each entry: (json_key, list_rank_or_None, label_prefix, color_var, style_var, width_var)
LEVEL_SPEC = [
    ("gflip",    None, "g-flip",   "C_GFLIP", "STY_GFLIP", "LW_GFLIP"),
    ("pos",      0,    "p1",       "C_POS",   "STY_P1",    "LW_P1"),
    ("pos",      1,    "p2",       "C_POS",   "STY_P2",    "LW_P2"),
    ("pos",      2,    "p3",       "C_POS",   "STY_P3",    "LW_P3"),
    ("neg",      0,    "n1",       "C_NEG",   "STY_N1",    "LW_N1"),
    ("neg",      1,    "n2",       "C_NEG",   "STY_N2",    "LW_N2"),
    ("neg",      2,    "n3",       "C_NEG",   "STY_N3",    "LW_N3"),
    ("agg",      None, "agg",      "C_AGG",   "STY_AGG",   "LW_AGG"),
]


def _get_price(entry: dict | None, key: str, rank: int | None) -> int | None:
    if entry is None:
        return None
    val = entry.get(key)
    if val is None:
        return None
    if isinstance(val, list):
        return val[rank] if rank is not None and rank < len(val) else None
    return val


def generate_pine_combined(hist_spx: list, hist_ndx: list) -> str:
    all_weeks   = sorted(set([e["week"] for e in hist_spx] + [e["week"] for e in hist_ndx]))
    spx_by_week = {e["week"]: e for e in hist_spx}
    ndx_by_week = {e["week"]: e for e in hist_ndx}

    bi_vars_lines       = []
    bi_detections_lines = []
    draw_blocks         = []

    for i, week_date in enumerate(all_weeks):
        mon_ts     = monday_ts_ms(week_date)
        is_current = (i == len(all_weeks) - 1)
        spx_e  = spx_by_week.get(week_date)
        ndx_e  = ndx_by_week.get(week_date)

        spx_conf = spx_e.get("conf", []) if spx_e else []
        ndx_conf = ndx_e.get("conf", []) if ndx_e else []

        bi_vars_lines.append(f"var int _bi{i} = na")
        bi_detections_lines.append(
            f"if is_week_start({mon_ts}) and _valid\n    _bi{i} := bar_index"
        )

        block = [
            f"    // --- Week {i}: {week_date} ---",
            f"    if not na(_bi{i})",
        ]

        # Vertical separators (identical for both tickers — same calendar)
        for offset, clr, sty, lw in [
            (f"_bi{i}",         "C_SEP_W", "STY_SEP_W", "LW_SEP_W"),
            (f"_bi{i} + D",     "C_SEP_D", "STY_SEP_D", "LW_SEP_D"),
            (f"_bi{i} + D * 2", "C_SEP_D", "STY_SEP_D", "LW_SEP_D"),
            (f"_bi{i} + D * 3", "C_SEP_D", "STY_SEP_D", "LW_SEP_D"),
        ]:
            block.append(
                f"        array.push(_lines, line.new({offset}, close, {offset}, close + 1, "
                f"color={clr}, style=f_style({sty}), width={lw}, extend=extend.both))"
            )

        # GEX level lines — merge overlapping strikes into combined labels
        # Step 1: collect all (spx_p, ndx_p, lbl, clr, sty, lw) entries
        raw_levels = []
        for key, rank, lbl, clr, sty, lw in LEVEL_SPEC:
            spx_p = _get_price(spx_e, key, rank)
            ndx_p = _get_price(ndx_e, key, rank)
            if spx_p is None and ndx_p is None:
                continue
            raw_levels.append((spx_p, ndx_p, lbl, clr, sty, lw))

        # Step 2: merge entries that share the same (spx_price, ndx_price) pair
        # First entry in LEVEL_SPEC order wins for color/style/width; labels are concatenated
        seen_pairs: dict[tuple, int] = {}
        merged_levels: list[list] = []  # [spx_p, ndx_p, combined_lbl, clr, sty, lw]
        for spx_p, ndx_p, lbl, clr, sty, lw in raw_levels:
            pair = (spx_p, ndx_p)
            if pair not in seen_pairs:
                seen_pairs[pair] = len(merged_levels)
                merged_levels.append([spx_p, ndx_p, lbl, clr, sty, lw])
            else:
                merged_levels[seen_pairs[pair]][2] += f" + {lbl}"

        # Step 3: generate Pine variables for each merged entry
        for spec_i, (spx_p, ndx_p, combined_lbl, clr, sty, lw) in enumerate(merged_levels):
            var     = f"_p{i}_{spec_i}"
            spx_val = _pf(spx_p)
            ndx_val = _pf(ndx_p)

            # Confluence star suffix per ticker
            spx_star = '" ★"' if _is_conf(spx_p, spx_conf, TICKER_CONFIG["SPX"]["conf_tol"]) else '""'
            ndx_star = '" ★"' if _is_conf(ndx_p, ndx_conf, TICKER_CONFIG["NDX"]["conf_tol"]) else '""'

            lbl_expr = (
                f'"{combined_lbl} " + str.tostring(math.round({var})) + '
                f'(_is_spx ? {spx_star} : {ndx_star})'
            )

            block += [
                f"        float {var} = _is_spx ? {spx_val} : {ndx_val}",
                f"        if not na({var})",
                f"            array.push(_lines, line.new(_bi{i}, {var}, _bi{i} + W, {var}, "
                f"color={clr}, style=f_style({sty}), width={lw}))",
            ]
            if is_current:
                block.append(
                    f"            array.push(_labels, label.new(_bi{i} + W, {var}, "
                    f"{lbl_expr}, color=color.new(color.black, 100), textcolor={clr}, "
                    f"style=label.style_none, size=size.small))"
                )

        draw_blocks.append("\n".join(block))

    return PINE_TEMPLATE.format(
        generated_date   = date.today().strftime("%Y-%m-%d"),
        total_weeks      = len(all_weeks),
        bi_vars          = "\n".join(bi_vars_lines),
        bi_detections    = "\n".join(bi_detections_lines),
        draw_weeks_block = "\n\n".join(draw_blocks),
    )

# ─── UTILS ───────────────────────────────────────────────────────────────────

def detect_expiry(csv_path: Path) -> str:
    m = re.search(r"exp-(\d{8})", csv_path.name)
    if m:
        return datetime.strptime(m.group(1), "%Y%m%d").strftime("%Y-%m-%d")
    return ""


def resolve_week(arg_week: str | None) -> str:
    if arg_week:
        dt = datetime.strptime(arg_week, "%Y-%m-%d")
        if dt.weekday() != 0:
            dt -= timedelta(days=dt.weekday())
            print(f"  [INFO] Adjusted to Monday: {dt.strftime('%Y-%m-%d')}")
        return dt.strftime("%Y-%m-%d")
    today = date.today()
    return (today - timedelta(days=today.weekday())).strftime("%Y-%m-%d")

# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Parse Barchart GEX CSV -> update history + Pine indicator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            '  python scripts/gex_csv_parser.py "data/$SPX-gamma-levels-exp-20260421-weekly.csv" --week 2026-04-14\n'
            '  python scripts/gex_csv_parser.py "data/$IUXX-gamma-levels-exp-20260421-monthly.csv" --week 2026-04-14'
        ),
    )
    parser.add_argument("csv",     help="Path to the Barchart CSV file")
    parser.add_argument("--week",  default=None, help="Monday date YYYY-MM-DD (default: this week)")
    parser.add_argument("--ticker", default=None, choices=["SPX", "NDX"],
                        help="Override ticker detection (default: auto from filename)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show calculated levels without saving")
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"[ERROR] File not found: {csv_path}")
        sys.exit(1)

    try:
        ticker = detect_ticker(csv_path, args.ticker)
    except ValueError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    week_date  = resolve_week(args.week)
    expiry     = detect_expiry(csv_path)

    print(f"\n  Ticker  : {ticker}")
    print(f"  Week    : {week_date}")
    print(f"  Expiry  : {expiry or '(not detected from filename)'}")
    print(f"  File    : {csv_path.name}")

    print("\n  Loading CSV...")
    try:
        df = load_csv(csv_path, ticker)
    except Exception as e:
        print(f"[ERROR] {e}")
        sys.exit(1)
    print(f"  Strikes : {len(df)} rows  ({int(df['Strike'].min()):,} – {int(df['Strike'].max()):,})")

    print("  Calculating GEX levels...")
    levels = calculate_levels(df, ticker)

    spot = get_spot(ticker)
    print_summary(levels, ticker, week_date, spot)

    if args.dry_run:
        print("  [DRY-RUN] Nothing saved.\n")
        return

    # Save history
    save_history(ticker, week_date, expiry, levels, csv_path.name)

    # Regenerate Pine (reads both histories — one may be empty)
    hist_spx  = load_history("SPX")
    hist_ndx  = load_history("NDX")
    pine_code = generate_pine_combined(hist_spx, hist_ndx)

    PINE_FILE.parent.mkdir(parents=True, exist_ok=True)
    PINE_FILE.write_text(pine_code, encoding="utf-8")
    print(f"  Pine Script regenerated -> {PINE_FILE.name}")

    ticker_lower = ticker.lower()
    print(f"\n  Next steps:")
    print(f"    1. git add gex_history_{ticker_lower}.json tradingview/gex_weekly_levels.pine")
    print(f"    2. git commit -m 'chore: GEX levels {ticker} week {week_date}'")
    print(f"    3. git push")
    print(f"    4. In TradingView -> Pine Editor -> paste gex_weekly_levels.pine -> Save\n")


if __name__ == "__main__":
    main()
