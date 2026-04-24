#!/usr/bin/env python3
"""
gex_csv_parser.py
─────────────────
Reads a Barchart GEX CSV (SPX, NDX, SPY, or QQQ) and:
  1. Calculates all GEX levels (Gamma Flip, p1/p2/p3, n1/n2/n3, coi, poi, agg, zones, confluences)
  2. Saves to the ticker's history JSON
  3. Regenerates tradingview/gex_weekly_levels.pine (single indicator — auto-switches ticker)
  4. Prints terminal summary with distances to spot

Usage:
  python scripts/gex_csv_parser.py "data/raw/gex/$SPX-gamma-levels-exp-20260421-weekly.csv" --week 2026-04-14
  python scripts/gex_csv_parser.py "data/raw/gex/$IUXX-gamma-levels-exp-20260421-weekly.csv" --week 2026-04-14
  python scripts/gex_csv_parser.py "data/raw/gex/SPY-gamma-levels-exp-20260421-weekly.csv"   --week 2026-04-14
  python scripts/gex_csv_parser.py "data/raw/gex/QQQ-gamma-levels-exp-20260421-weekly.csv"   --week 2026-04-14
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
# pine_aliases  : exact syminfo.ticker values to match in Pine
# pine_contains : substrings to match via str.contains (for futures like ES1!, NQ1!)

TICKER_CONFIG = {
    "SPX": {
        "filename_prefix": ["$SPX-"],
        "yf_symbol":       "^GSPC",
        "strike_min":      4000,
        "strike_max":      10000,
        "history_file":    ROOT / "state" / "gex" / "gex_history_spx.json",
        "conf_tol":        5,
        "pine_aliases":    ["SPX"],
        "pine_contains":   ["ES1"],
    },
    "NDX": {
        "filename_prefix": ["$IUXX-"],
        "yf_symbol":       "^NDX",
        "strike_min":      15000,
        "strike_max":      30000,
        "history_file":    ROOT / "state" / "gex" / "gex_history_ndx.json",
        "conf_tol":        25,
        "pine_aliases":    ["NDX"],
        "pine_contains":   ["NQ1"],
    },
    "SPY": {
        "filename_prefix": ["SPY-", "$SPY-"],
        "yf_symbol":       "SPY",
        "strike_min":      200,
        "strike_max":      800,
        "history_file":    ROOT / "state" / "gex" / "gex_history_spy.json",
        "conf_tol":        2,
        "pine_aliases":    ["SPY"],
        "pine_contains":   [],
    },
    "QQQ": {
        "filename_prefix": ["QQQ-", "$QQQ-"],
        "yf_symbol":       "QQQ",
        "strike_min":      150,
        "strike_max":      700,
        "history_file":    ROOT / "state" / "gex" / "gex_history_qqq.json",
        "conf_tol":        2,
        "pine_aliases":    ["QQQ"],
        "pine_contains":   [],
    },
}

# ─── PINE TEMPLATE ────────────────────────────────────────────────────────────

PINE_TEMPLATE = """\
//@version=5
// =======================================================================
// GEX Weekly Levels [TradingLitt Style] — SPX + NDX + SPY + QQQ — AUTO-GENERATED
// DO NOT EDIT MANUALLY. Regenerate via:
//   python scripts/gex_csv_parser.py <csv_path> --week YYYY-MM-DD
// Last updated : {generated_date}
// Weeks stored : {total_weeks}
// =======================================================================
indicator("GEX Weekly Levels [TradingLitt]", overlay=true, max_lines_count=500, max_labels_count=500, shorttitle="GEX Levels")

// --- TICKER DETECTION -----------------------------------------------
{ticker_detection}

// --- INPUTS (Indicator Inputs) --------------------------------------
var string _GI = "Indicator Inputs"
SHOW_TS    = input.bool(false,     "Show Timestamp",    group=_GI)
SHORT_NAME = input.bool(false,     "Short Name",        group=_GI)
LBL_POS    = input.string("Right", "Labels Position",   group=_GI, options=["Right", "Left", "Center"])
LBL_OFFSET = input.int(0,          "Labels Offset",     group=_GI, minval=-200, maxval=200)
LBL_SIZE   = input.string("Small", "Labels Text Size",  group=_GI, options=["Tiny", "Small", "Normal", "Large"])

// --- INPUTS (Level Settings) — cor + estilo + largura por linha -----
var string _GLS = "Level Settings"
C_GFLIP   = input.color( color.rgb(158, 158, 158),   "Gamma Flip  ", group=_GLS, inline="gflip",  display=display.none)
STY_GFLIP = input.string("Dashed", "",                group=_GLS, inline="gflip",  options=["Solid","Dashed","Dotted"], display=display.none)
LW_GFLIP  = input.int(2,  "",      minval=1, maxval=4, group=_GLS, inline="gflip",  display=display.none)

C_P1    = input.color( color.rgb(0, 200, 83),        "Pos GEX p1  ", group=_GLS, inline="p1",    display=display.none)
STY_P1  = input.string("Solid",  "",                 group=_GLS, inline="p1",    options=["Solid","Dashed","Dotted"], display=display.none)
LW_P1   = input.int(2,  "",      minval=1, maxval=4,  group=_GLS, inline="p1",    display=display.none)

C_P2    = input.color( color.rgb(0, 200, 83),        "Pos GEX p2  ", group=_GLS, inline="p2",    display=display.none)
STY_P2  = input.string("Dashed", "",                 group=_GLS, inline="p2",    options=["Solid","Dashed","Dotted"], display=display.none)
LW_P2   = input.int(1,  "",      minval=1, maxval=4,  group=_GLS, inline="p2",    display=display.none)

C_P3    = input.color( color.rgb(0, 200, 83),        "Pos GEX p3  ", group=_GLS, inline="p3",    display=display.none)
STY_P3  = input.string("Dotted", "",                 group=_GLS, inline="p3",    options=["Solid","Dashed","Dotted"], display=display.none)
LW_P3   = input.int(1,  "",      minval=1, maxval=4,  group=_GLS, inline="p3",    display=display.none)

C_N1    = input.color( color.rgb(255, 23, 68),       "Neg GEX n1  ", group=_GLS, inline="n1",    display=display.none)
STY_N1  = input.string("Solid",  "",                 group=_GLS, inline="n1",    options=["Solid","Dashed","Dotted"], display=display.none)
LW_N1   = input.int(2,  "",      minval=1, maxval=4,  group=_GLS, inline="n1",    display=display.none)

C_N2    = input.color( color.rgb(255, 23, 68),       "Neg GEX n2  ", group=_GLS, inline="n2",    display=display.none)
STY_N2  = input.string("Dashed", "",                 group=_GLS, inline="n2",    options=["Solid","Dashed","Dotted"], display=display.none)
LW_N2   = input.int(1,  "",      minval=1, maxval=4,  group=_GLS, inline="n2",    display=display.none)

C_N3    = input.color( color.rgb(255, 23, 68),       "Neg GEX n3  ", group=_GLS, inline="n3",    display=display.none)
STY_N3  = input.string("Dotted", "",                 group=_GLS, inline="n3",    options=["Solid","Dashed","Dotted"], display=display.none)
LW_N3   = input.int(1,  "",      minval=1, maxval=4,  group=_GLS, inline="n3",    display=display.none)

C_AGG   = input.color( color.rgb(170, 0, 255),       "Aggregate   ", group=_GLS, inline="agg",   display=display.none)
STY_AGG = input.string("Dotted", "",                 group=_GLS, inline="agg",   options=["Solid","Dashed","Dotted"], display=display.none)
LW_AGG  = input.int(1,  "",      minval=1, maxval=4,  group=_GLS, inline="agg",   display=display.none)

C_SEP_W   = input.color( color.new(color.gray, 40),  "Sep. Monday ", group=_GLS, inline="sep_w", display=display.none)
STY_SEP_W = input.string("Dashed", "",                group=_GLS, inline="sep_w", options=["Solid","Dashed","Dotted"], display=display.none)
LW_SEP_W  = input.int(2,  "",      minval=1, maxval=4, group=_GLS, inline="sep_w", display=display.none)

C_SEP_D   = input.color( color.new(color.gray, 72),  "Sep. Tue-Thu", group=_GLS, inline="sep_d", display=display.none)
STY_SEP_D = input.string("Dashed", "",                group=_GLS, inline="sep_d", options=["Solid","Dashed","Dotted"], display=display.none)
LW_SEP_D  = input.int(2,  "",      minval=1, maxval=4, group=_GLS, inline="sep_d", display=display.none)

// --- INPUTS (Single Levels) — toggle por level ----------------------
var string _GSL = "Single Levels"
SH_GFLIP = input.bool(true, "Gamma Flip", group=_GSL)
SH_P1    = input.bool(true, "Pos GEX p1", group=_GSL)
SH_P2    = input.bool(true, "Pos GEX p2", group=_GSL)
SH_P3    = input.bool(true, "Pos GEX p3", group=_GSL)
SH_N1    = input.bool(true, "Neg GEX n1", group=_GSL)
SH_N2    = input.bool(true, "Neg GEX n2", group=_GSL)
SH_N3    = input.bool(true, "Neg GEX n3", group=_GSL)
SH_AGG   = input.bool(true, "Aggregate",  group=_GSL)

// --- CONSTANTS ------------------------------------------------------
// D = bars per trading day; W = Monday open -> Friday close span — auto-adapted to any timeframe
// US equity session: 9:30-16:00 = 390 minutes
int D = timeframe.isintraday ? math.max(1, math.round(390.0 / (timeframe.in_seconds() / 60.0))) : 1
int W = D * 5 - 1
string _update_date = "{generated_date}"

f_week_x2(int bi, int next_bi) =>
    na(bi) ? na : na(next_bi) ? bi + W : math.max(bi, next_bi - 1)

// --- HELPERS --------------------------------------------------------
f_style(s) =>
    s == "Solid" ? line.style_solid : s == "Dotted" ? line.style_dotted : line.style_dashed

f_lbl_x(x1, x2, lpos, loff) =>
    lpos == "Left" ? x1 + loff : lpos == "Center" ? x1 + math.floor((x2 - x1) / 2) + loff : x2 + loff

f_lbl_size(s) =>
    s == "Tiny" ? size.tiny : s == "Large" ? size.large : s == "Normal" ? size.normal : size.small

// True on the first bar of a given Monday (by timestamp)
is_week_start(ts) => time >= ts and (na(time[1]) or time[1] < ts)

// --- MONDAY BAR INDEX DETECTION (auto-generated) --------------------
{bi_vars}

{bi_detections}

// --- GLOBAL LINE / LABEL STORAGE ------------------------------------
var line[]  _lines  = array.new_line()
var label[] _labels = array.new_label()

f_draw_sep(x, clr, sty, lw) =>
    array.push(_lines, line.new(x, 0.0, x, 1.0, xloc=xloc.bar_index, color=clr, style=f_style(sty), width=lw, extend=extend.both))

f_draw_sep_clamped(x, x2, clr, sty, lw) =>
    if not na(x2) and x <= x2
        f_draw_sep(x, clr, sty, lw)

f_draw_level(x1, x2, price, clr, sty, lw, show, lbl) =>
    if show and not na(price) and not na(x2) and x2 >= x1
        array.push(_lines, line.new(x1, price, x2, price, color=clr, style=f_style(sty), width=lw))
        array.push(_labels, label.new(f_lbl_x(x1, x2, LBL_POS, LBL_OFFSET), price, lbl, color=color.new(color.black, 100), textcolor=clr, style=label.style_none, size=f_lbl_size(LBL_SIZE)))

// --- REDRAW ON LAST BAR (delete all → redraw with current inputs) ---
f_redraw_all() =>
    for l in _lines
        line.delete(l)
    array.clear(_lines)
    for lb in _labels
        label.delete(lb)
    array.clear(_labels)
{draw_week_functions}

if barstate.islast and _valid
    f_redraw_all()
{draw_week_calls}
"""

# ─── CSV LOADING ──────────────────────────────────────────────────────────────

def detect_ticker(csv_path: Path, override: str | None = None) -> str:
    if override:
        if override not in TICKER_CONFIG:
            raise ValueError(f"Invalid ticker: {override}. Choose {'/'.join(TICKER_CONFIG)}.")
        return override
    name = csv_path.name
    for ticker, cfg in TICKER_CONFIG.items():
        prefixes = cfg["filename_prefix"] if isinstance(cfg["filename_prefix"], list) else [cfg["filename_prefix"]]
        if any(name.startswith(p) for p in prefixes):
            return ticker
    raise ValueError(
        f"Cannot detect ticker from filename '{name}'.\n"
        f"Use --ticker {'/'.join(TICKER_CONFIG)} to override."
    )


def load_csv(csv_path: Path, ticker: str) -> pd.DataFrame:
    raw   = csv_path.read_text(encoding="utf-8", errors="replace")
    lines = [l for l in raw.splitlines() if not l.startswith("Downloaded from")]
    df    = pd.read_csv(StringIO("\n".join(lines)))

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
    return int(df.loc[df["Gamma Exposure Profile"].abs().idxmin(), "Strike"])


def top_strikes(series: pd.Series, strikes: pd.Series, n: int) -> list[int]:
    df_tmp = pd.DataFrame({"val": series.abs(), "strike": strikes})
    top    = df_tmp.nlargest(n, "val")
    return [int(s) for s in top.sort_values("val", ascending=False)["strike"].tolist()]


def detect_confluences(levels: dict, tol: int) -> list[int]:
    cat_strikes: dict[str, list[int]] = {}
    for cat in ("gflip", "pos", "neg", "coi", "poi", "agg", "pos_zone", "neg_zone"):
        val = levels.get(cat)
        if val is None:
            continue
        cat_strikes[cat] = val if isinstance(val, list) else [val]

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

    pos_rows = df[df["Net Gamma Exposure"] > 0].nlargest(3, "Net Gamma Exposure")
    pos = [int(s) for s in pos_rows.sort_values("Net Gamma Exposure", ascending=False)["Strike"].tolist()]

    neg_rows = df[df["Net Gamma Exposure"] < 0].nsmallest(3, "Net Gamma Exposure")
    neg = [int(s) for s in neg_rows.sort_values("Net Gamma Exposure")["Strike"].tolist()]

    coi     = top_strikes(df["Call Open Interest"], df["Strike"], 2)
    poi     = top_strikes(df["Put Open Interest"],  df["Strike"], 2)
    agg_idx = df["Absolute Gamma Exposure"].idxmax()
    agg     = int(df.loc[agg_idx, "Strike"])

    above         = df[df["Strike"] > gflip]
    pos_zone_rows = above[above["Gamma Exposure Profile"] > 0]
    pos_zone      = int(pos_zone_rows["Strike"].iloc[0]) if not pos_zone_rows.empty else None

    below         = df[df["Strike"] < gflip]
    neg_zone_rows = below[below["Gamma Exposure Profile"] < 0]
    neg_zone      = int(neg_zone_rows["Strike"].iloc[-1]) if not neg_zone_rows.empty else None

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


def save_history(ticker: str, week_date: str, expiry: str, levels: dict, source_file: str) -> list:
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


def _pine_str(val: str) -> str:
    return val.replace("\\", "\\\\").replace('"', '\\"')


def _indent_block(text: str, spaces: int = 4) -> str:
    prefix = " " * spaces
    return "\n".join(f"{prefix}{line}" if line else "" for line in text.splitlines())


def _is_conf(price: int | None, conf_list: list[int], tol: int) -> bool:
    if price is None:
        return False
    return any(abs(price - c) <= tol for c in conf_list)


def _build_ticker_detection() -> str:
    """Generate Pine ticker detection block from TICKER_CONFIG."""
    lines  = []
    is_vars = []
    for ticker, cfg in TICKER_CONFIG.items():
        t     = ticker.lower()
        conds = [f'syminfo.ticker == "{a}"' for a in cfg.get("pine_aliases", [ticker])]
        conds += [f'str.contains(syminfo.ticker, "{c}")' for c in cfg.get("pine_contains", [])]
        lines.append(f"_is_{t} = {' or '.join(conds)}")
        is_vars.append(f"_is_{t}")
    lines.append(f"_valid  = {' or '.join(is_vars)}")
    return "\n".join(lines)


# (json_key, rank, short_name, full_name, clr_var, sty_var, lw_var, show_var)
LEVEL_SPEC = [
    ("gflip", None, "g-flip", "Gamma Flip", "C_GFLIP", "STY_GFLIP", "LW_GFLIP", "SH_GFLIP"),
    ("pos",   0,    "p1",     "Pos p1",     "C_P1",    "STY_P1",    "LW_P1",    "SH_P1"),
    ("pos",   1,    "p2",     "Pos p2",     "C_P2",    "STY_P2",    "LW_P2",    "SH_P2"),
    ("pos",   2,    "p3",     "Pos p3",     "C_P3",    "STY_P3",    "LW_P3",    "SH_P3"),
    ("neg",   0,    "n1",     "Neg n1",     "C_N1",    "STY_N1",    "LW_N1",    "SH_N1"),
    ("neg",   1,    "n2",     "Neg n2",     "C_N2",    "STY_N2",    "LW_N2",    "SH_N2"),
    ("neg",   2,    "n3",     "Neg n3",     "C_N3",    "STY_N3",    "LW_N3",    "SH_N3"),
    ("agg",   None, "agg",    "Aggregate",  "C_AGG",   "STY_AGG",   "LW_AGG",   "SH_AGG"),
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


def _manual_level_draw_spec(level: dict) -> tuple[str, str, str, str]:
    bucket = (level.get("bucket") or "").lower()
    if bucket == "green":
        return "C_P1", "STY_P1", "LW_P1", "(SH_P1 or SH_P2 or SH_P3)"
    if bucket == "red":
        return "C_N1", "STY_N1", "LW_N1", "(SH_N1 or SH_N2 or SH_N3)"
    if bucket == "purple":
        return "C_AGG", "STY_AGG", "LW_AGG", "SH_AGG"
    return "C_GFLIP", "STY_GFLIP", "LW_GFLIP", "SH_GFLIP"


def generate_pine_combined(histories: dict[str, list]) -> str:
    """
    histories: {ticker: [week_entries, ...]}
    Merge is done per-ticker: if two levels land on the same price for a given ticker,
    they become one line with a combined label (e.g. "p1 + agg").
    Each ticker gets its own if _is_{t} block in the Pine draw section.
    """
    tickers   = list(TICKER_CONFIG.keys())
    all_weeks = sorted(set(e["week"] for entries in histories.values() for e in entries))
    by_week   = {t: {e["week"]: e for e in histories.get(t, [])} for t in tickers}

    bi_vars_lines       = []
    bi_detections_lines = []
    draw_functions      = []
    draw_calls          = []

    for i, week_date in enumerate(all_weeks):
        mon_ts     = monday_ts_ms(week_date)
        entries    = {t: by_week[t].get(week_date) for t in tickers}
        confs      = {t: (entries[t].get("conf", []) if entries[t] else []) for t in tickers}

        bi_vars_lines.append(f"var int _bi{i} = na")
        bi_detections_lines.append(
            f"if is_week_start({mon_ts}) and _valid\n    _bi{i} := bar_index"
        )

        next_bi = f"_bi{i + 1}" if i + 1 < len(all_weeks) else "int(na)"
        x2_expr = f"f_week_x2(_bi{i}, {next_bi})"

        block = [
            f"    // --- Week {i}: {week_date} ---",
            f"    if not na(_bi{i})",
            f"        int _x2 = {x2_expr}",
        ]

        # Per-ticker GEX levels — merged independently per ticker
        for t in tickers:
            tl    = t.lower()
            entry = entries[t]
            conf  = confs[t]

            manual_levels = entry.get("manual_levels", []) if entry else []
            if manual_levels:
                block.append(f"        if _is_{tl}")
                for offset, clr, sty, lw in [
                    (f"_bi{i}",         "C_SEP_W", "STY_SEP_W", "LW_SEP_W"),
                    (f"_bi{i} + D",     "C_SEP_D", "STY_SEP_D", "LW_SEP_D"),
                    (f"_bi{i} + D * 2", "C_SEP_D", "STY_SEP_D", "LW_SEP_D"),
                    (f"_bi{i} + D * 3", "C_SEP_D", "STY_SEP_D", "LW_SEP_D"),
                    (f"_bi{i} + D * 4", "C_SEP_D", "STY_SEP_D", "LW_SEP_D"),
                ]:
                    block.append(f"            f_draw_sep_clamped({offset}, _x2, {clr}, {sty}, {lw})")

                for j, level in enumerate(manual_levels):
                    price = level.get("price")
                    label = level.get("label", "")
                    if price is None or not label:
                        continue

                    clr, sty, lw, show_expr = _manual_level_draw_spec(level)
                    pval = _pf(price)
                    label_text = _pine_str(label)
                    lbl_expr = (
                        f'"{label_text} ($" + str.tostring(math.round({pval})) + ")" + '
                        f'(SHOW_TS ? " [" + _update_date + "]" : "")'
                    )

                    block.append(
                        f"            f_draw_level(_bi{i}, _x2, {pval}, {clr}, {sty}, {lw}, {show_expr}, {lbl_expr})"
                    )
                continue

            # Collect all LEVEL_SPEC entries that have a price for this ticker
            raw: list[tuple] = []
            for key, rank, short_lbl, full_lbl, clr, sty, lw, show_var in LEVEL_SPEC:
                price = _get_price(entry, key, rank)
                if price is None:
                    continue
                raw.append((price, short_lbl, full_lbl, clr, sty, lw, show_var))

            if not raw:
                continue

            # Merge levels that share the same price FOR THIS TICKER
            # First entry in LEVEL_SPEC order wins for color/style/width
            seen: dict[int, int] = {}
            merged: list[list] = []  # [price, short_lbl, full_lbl, clr, sty, lw, [show_vars]]

            for price, short_lbl, full_lbl, clr, sty, lw, show_var in raw:
                if price not in seen:
                    seen[price] = len(merged)
                    merged.append([price, short_lbl, full_lbl, clr, sty, lw, [show_var]])
                else:
                    idx = seen[price]
                    merged[idx][1] += f" + {short_lbl}"
                    merged[idx][2] += f" + {full_lbl}"
                    merged[idx][6].append(show_var)

            block.append(f"        if _is_{tl}")
            for offset, clr, sty, lw in [
                (f"_bi{i}",         "C_SEP_W", "STY_SEP_W", "LW_SEP_W"),
                (f"_bi{i} + D",     "C_SEP_D", "STY_SEP_D", "LW_SEP_D"),
                (f"_bi{i} + D * 2", "C_SEP_D", "STY_SEP_D", "LW_SEP_D"),
                (f"_bi{i} + D * 3", "C_SEP_D", "STY_SEP_D", "LW_SEP_D"),
                (f"_bi{i} + D * 4", "C_SEP_D", "STY_SEP_D", "LW_SEP_D"),
            ]:
                block.append(f"            f_draw_sep_clamped({offset}, _x2, {clr}, {sty}, {lw})")

            for j, (price, short_lbl, full_lbl, clr, sty, lw, show_vars) in enumerate(merged):
                pval      = _pf(price)
                star      = '" ★"' if _is_conf(price, conf, TICKER_CONFIG[t]["conf_tol"]) else '""'
                show_expr = " or ".join(show_vars)

                lbl_expr = (
                    f'(SHORT_NAME ? "{short_lbl}" : "{full_lbl}") + " " + '
                    f'str.tostring(math.round({pval})) + {star} + '
                    f'(SHOW_TS ? " [" + _update_date + "]" : "")'
                )

                block.append(
                    f"            f_draw_level(_bi{i}, _x2, {pval}, {clr}, {sty}, {lw}, ({show_expr}), {lbl_expr})"
                )

        draw_functions.append(f"f_draw_week_{i}() =>\n" + "\n".join(block))
        draw_calls.append(f"    f_draw_week_{i}()")

    return PINE_TEMPLATE.format(
        generated_date   = date.today().strftime("%Y-%m-%d"),
        total_weeks      = len(all_weeks),
        ticker_detection = _build_ticker_detection(),
        bi_vars          = "\n".join(bi_vars_lines),
        bi_detections    = "\n".join(bi_detections_lines),
        draw_week_functions = "\n\n".join(draw_functions),
        draw_week_calls     = "\n".join(draw_calls),
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
            '  python scripts/gex_csv_parser.py "data/raw/gex/$SPX-gamma-levels-exp-20260421-weekly.csv" --week 2026-04-14\n'
            '  python scripts/gex_csv_parser.py "data/raw/gex/SPY-gamma-levels-exp-20260421-weekly.csv"  --week 2026-04-14\n'
            '  python scripts/gex_csv_parser.py "data/raw/gex/QQQ-gamma-levels-exp-20260421-weekly.csv"  --week 2026-04-14'
        ),
    )
    parser.add_argument("csv",      help="Path to the Barchart CSV file")
    parser.add_argument("--week",   default=None, help="Monday date YYYY-MM-DD (default: this week)")
    parser.add_argument("--ticker", default=None, choices=list(TICKER_CONFIG.keys()),
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

    week_date = resolve_week(args.week)
    expiry    = detect_expiry(csv_path)

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

    save_history(ticker, week_date, expiry, levels, csv_path.name)

    # Regenerate Pine from all histories
    histories = {t: load_history(t) for t in TICKER_CONFIG}
    pine_code = generate_pine_combined(histories)

    PINE_FILE.parent.mkdir(parents=True, exist_ok=True)
    PINE_FILE.write_text(pine_code, encoding="utf-8")
    print(f"  Pine Script regenerated -> {PINE_FILE.name}")

    ticker_lower = ticker.lower()
    print("\n  Next steps:")
    print(f"    1. git add gex_history_{ticker_lower}.json tradingview/gex_weekly_levels.pine")
    print(f"    2. git commit -m 'chore: GEX levels {ticker} week {week_date}'")
    print("    3. git push")
    print("    4. In TradingView -> Pine Editor -> paste gex_weekly_levels.pine -> Save\n")


if __name__ == "__main__":
    main()
