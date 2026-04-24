#!/usr/bin/env python3
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

"""
gex_input.py
------------
Reads gex_levels.txt, saves to permanent history and generates the Pine Script.

MONDAY WORKFLOW:
  1. Watch TradingLitt Weekly Outlook on YouTube
  2. Edit gex_levels.txt with this week's levels (2 min)
  3. Run: python scripts/gex_input.py --week 2026-04-14
  4. Paste tradingview/gex_weekly_levels.pine into TradingView Pine Editor -> Save

Usage:
  python scripts/gex_input.py --week 2026-04-14
  python scripts/gex_input.py --week 2026-04-14 --dry-run
"""

import argparse
import json
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

try:
    import pytz
    ET = pytz.timezone("America/New_York")
    HAS_PYTZ = True
except ImportError:
    HAS_PYTZ = False
    print("[WARNING] pytz not installed. Run: pip install pytz")

# --- PATHS -------------------------------------------------------------------
ROOT         = Path(__file__).parent.parent
LEVELS_FILE       = ROOT / "state" / "gex" / "levels_input.txt"
HISTORY_FILE      = ROOT / "state" / "gex" / "gex_history.json"
PINE_FILE         = ROOT / "tradingview" / "gex_weekly_levels.pine"
PINE_CURRENT_FILE = ROOT / "tradingview" / "gex_current_levels.pine"

# Category → (color_var, style_var) used in generated Pine code
CAT_CONFIG = {
    "gflip":    ("C_GFLIP", "STY_GFLIP"),
    "pos":      ("C_POS",   "STY_POS"),
    "neg":      ("C_NEG",   "STY_NEG"),
    "agg":      ("C_AGG",   "STY_AGG"),
    "pos_zone": ("C_PZ",    "STY_PZ"),
    "neg_zone": ("C_NZ",    "STY_NZ"),
}

# --- PINE SCRIPT TEMPLATE (weekly 15m) ---------------------------------------
# Architecture: lines drawn exclusively on barstate.islast via var arrays.
# Prevents the duplication bug that occurs when Settings inputs trigger
# a re-execution — on every last bar we delete all old lines first, then
# redraw everything with the current input values.
PINE_TEMPLATE = """\
//@version=5
// =======================================================================
// GEX Weekly Levels [TradingLitt Style] - AUTO-GENERATED
// DO NOT EDIT MANUALLY. Regenerate every Monday via:
//   python scripts/gex_input.py --week YYYY-MM-DD
// Last updated : {generated_date}
// Weeks stored : {total_weeks}
// =======================================================================
indicator("GEX Weekly Levels [TradingLitt]", overlay=true, max_lines_count=500, max_labels_count=500, shorttitle="GEX Levels")

// --- INPUTS (Colors) ------------------------------------------------
var string _GC = "Colors"
C_GFLIP = input.color(color.white,                           "Gamma Flip",   group=_GC, display=display.none)
C_POS   = input.color(color.rgb(0, 200, 83),                 "Positive GEX", group=_GC, display=display.none)
C_NEG   = input.color(color.rgb(255, 23, 68),                "Negative GEX", group=_GC, display=display.none)
C_AGG   = input.color(color.rgb(170, 0, 255),                "Aggregate",    group=_GC, display=display.none)
C_PZ    = input.color(color.new(color.rgb(0, 200, 83),  45), "Pos Zone",     group=_GC, display=display.none)
C_NZ    = input.color(color.new(color.rgb(255, 23, 68), 45), "Neg Zone",     group=_GC, display=display.none)
C_SEP_W = color.new(color.gray, 40)
C_SEP_D = color.new(color.gray, 72)

// --- INPUTS (Styles) ------------------------------------------------
var string _GS = "Styles"
STY_GFLIP = input.string("Dashed", "Gamma Flip",   options=["Solid", "Dashed", "Dotted"], group=_GS, display=display.none)
STY_POS   = input.string("Solid",  "Positive GEX", options=["Solid", "Dashed", "Dotted"], group=_GS, display=display.none)
STY_NEG   = input.string("Solid",  "Negative GEX", options=["Solid", "Dashed", "Dotted"], group=_GS, display=display.none)
STY_AGG   = input.string("Dotted", "Aggregate",    options=["Solid", "Dashed", "Dotted"], group=_GS, display=display.none)
STY_PZ    = input.string("Dashed", "Pos Zone",     options=["Solid", "Dashed", "Dotted"], group=_GS, display=display.none)
STY_NZ    = input.string("Dashed", "Neg Zone",     options=["Solid", "Dashed", "Dotted"], group=_GS, display=display.none)

// Resolves the style string to a line style constant
f_style(s) =>
    s == "Solid" ? line.style_solid : s == "Dotted" ? line.style_dotted : line.style_dashed

// --- SCALE GUARD (SPY range; excludes SPX > 2000) -------------------
_valid_scale = close < 2000

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
if barstate.islast and _valid_scale
    for l in _lines
        line.delete(l)
    array.clear(_lines)
    for lb in _labels
        label.delete(lb)
    array.clear(_labels)
{draw_weeks_block}
"""

# --- PINE SCRIPT TEMPLATE: CURRENT LEVELS (daily / hourly) -------------------
PINE_CURRENT_TEMPLATE = """\
//@version=5
// =======================================================================
// GEX Current Levels - AUTO-GENERATED
// For use on DAILY or HOURLY charts.
// DO NOT EDIT MANUALLY. Regenerate every Monday via:
//   python scripts/gex_input.py --week YYYY-MM-DD
// Last updated : {generated_date}
// Week         : {week_date}
// =======================================================================
indicator("GEX Current Levels", overlay=true, max_labels_count=50, shorttitle="GEX Now")

// --- FILTERS --------------------------------------------------------
var string G = "Filter"
show_gflip = input.bool(true,  "Gamma Flip",                 group=G)
show_pos   = input.bool(true,  "Call Walls (Positive GEX)",  group=G)
show_neg   = input.bool(true,  "Put Support (Negative GEX)", group=G)
show_agg   = input.bool(false, "Aggregate / Confluence",      group=G)

// --- INPUTS (Colors) ------------------------------------------------
var string _GC = "Colors"
C_GFLIP = input.color(color.white,                           "Gamma Flip",   group=_GC, display=display.none)
C_POS   = input.color(color.rgb(0, 200, 83),                 "Positive GEX", group=_GC, display=display.none)
C_NEG   = input.color(color.rgb(255, 23, 68),                "Negative GEX", group=_GC, display=display.none)
C_AGG   = input.color(color.rgb(170, 0, 255),                "Aggregate",    group=_GC, display=display.none)
C_PZ    = input.color(color.new(color.rgb(0, 200, 83),  45), "Pos Zone",     group=_GC, display=display.none)
C_NZ    = input.color(color.new(color.rgb(255, 23, 68), 45), "Neg Zone",     group=_GC, display=display.none)

// Only draw on SPY-scale charts (excludes SPX > 2000)
_valid = close < 2000

// Levels visible from this week's Monday onwards
_in_week = time >= {mon_ts} and _valid

// --- PRICE LEVELS via plot() ----------------------------------------
// plot() is stable on zoom/scroll/symbol change; color inputs work correctly.
{plot_calls}

// --- LABELS via label.new() -----------------------------------------
_label_off = timeframe.in_seconds(timeframe.period) * 10000
var label[] _B = array.new_label()
if barstate.islast and _valid
    for lb in _B
        label.delete(lb)
    array.clear(_B)
    _lbl = timenow + _label_off
{label_calls}
"""

# --- TIMESTAMP ---------------------------------------------------------------

def monday_ts_ms(date_str: str) -> int:
    if HAS_PYTZ:
        naive = datetime.strptime(date_str, "%Y-%m-%d").replace(hour=9, minute=30)
        return int(ET.localize(naive).timestamp() * 1000)
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(hour=14, minute=30)
    return int(dt.timestamp() * 1000)

def next_monday_str(date_str: str) -> str:
    return (datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=7)).strftime("%Y-%m-%d")

def most_recent_monday() -> str:
    today = date.today()
    return (today - timedelta(days=today.weekday())).strftime("%Y-%m-%d")

# --- CATEGORIZATION ----------------------------------------------------------

def categorize(label: str) -> str:
    t = label.lower().strip()
    if "g-flip" in t or "gflip" in t:        return "gflip"
    if "pos_zone" in t or "pos gex" in t:    return "pos_zone"
    if "neg_zone" in t or "neg gex" in t:    return "neg_zone"
    if re.match(r"^p[\d+\s]|^p$", t):        return "pos"
    if re.match(r"^n[\d+\s\-]|^n$|^r[\d]?", t) or "low gex" in t: return "neg"
    if re.match(r"^ag[\d\s]|^agg", t):       return "agg"
    return "unknown"

# --- PARSE gex_levels.txt ----------------------------------------------------

def normalize_label(lbl: str) -> str:
    return re.sub(r"\s*\+\s*", "+", lbl.strip())

def parse_levels_file(path: Path) -> list[tuple[str, float]]:
    levels, errors = [], []
    for i, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            errors.append(f"  line {i}: missing ':'"); continue
        colon = line.index(":")
        lbl = line[:colon].strip()
        try:
            price = float(line[colon+1:].strip())
        except ValueError:
            errors.append(f"  line {i}: invalid price"); continue
        if not (300 <= price <= 1000):
            errors.append(f"  line {i}: price out of SPY range -> {price}"); continue
        levels.append((lbl, price))
    if errors:
        print("[WARNING]"); [print(e) for e in errors]; print()
    return levels

def group_levels(levels):
    grouped = defaultdict(list)
    for lbl, price in levels:
        grouped[categorize(lbl)].append((lbl, round(price)))
    return grouped

def grouped_to_strings(grouped: dict) -> dict:
    def fmt(items):
        seen, parts = set(), []
        for lbl, price in sorted(items, key=lambda x: -x[1]):
            if price not in seen:
                seen.add(price)
                parts.append(f"{normalize_label(lbl)}:{price}")
        return ", ".join(parts)
    return {k: fmt(grouped.get(k, [])) for k in ("gflip","pos","neg","agg","pos_zone","neg_zone")}

# --- PARSE LEVEL STRINGS (for Pine generation) -------------------------------

def parse_level_string(raw: str) -> list[tuple[str, float]]:
    """Parse 'lbl:price, lbl:price' string back to list of (label, price)."""
    levels = []
    if not raw:
        return levels
    for part in raw.split(","):
        part = part.strip()
        if ":" not in part:
            continue
        lbl, price_str = part.rsplit(":", 1)
        try:
            levels.append((lbl.strip(), float(price_str.strip())))
        except ValueError:
            pass
    return levels

def sanitize_label(lbl: str) -> str:
    """Escape double-quotes for safe embedding in Pine string literals."""
    return lbl.replace('"', "'")

# --- HISTORY -----------------------------------------------------------------

def load_history() -> list:
    if HISTORY_FILE.exists():
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    return []

def save_history(history: list, week_date: str, strings: dict) -> list:
    entry = {"week": week_date, "factor": 1.0, **strings}
    updated = sorted([e for e in history if e["week"] != week_date] + [entry],
                     key=lambda e: e["week"])
    HISTORY_FILE.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  History saved: {len(updated)} week(s) in {HISTORY_FILE.name}")
    return updated

# --- PINE SCRIPT GENERATION --------------------------------------------------

def generate_pine(history: list) -> str:
    MAX_WEEKS = 28
    if len(history) > MAX_WEEKS:
        history = history[-MAX_WEEKS:]

    bi_vars_lines       = []
    bi_detections_lines = []
    draw_blocks         = []

    for i, entry in enumerate(history):
        week_date = entry["week"]
        mon_ts    = monday_ts_ms(week_date)

        bi_vars_lines.append(f"var int _bi{i} = na")
        bi_detections_lines.append(
            f"if is_week_start({mon_ts}) and _valid_scale\n    _bi{i} := bar_index"
        )

        block_lines = [f"    // --- Week {i}: {week_date} ---", f"    if not na(_bi{i})"]

        # Vertical separators (Mon=week-color, Tue/Wed/Thu=day-color)
        sep_offsets = [
            (f"_bi{i}",             "C_SEP_W"),
            (f"_bi{i} + D",         "C_SEP_D"),
            (f"_bi{i} + D * 2",     "C_SEP_D"),
            (f"_bi{i} + D * 3",     "C_SEP_D"),
        ]
        for x, clr in sep_offsets:
            block_lines.append(
                f"        array.push(_lines, line.new({x}, close, {x}, close + 1, "
                f"color={clr}, style=line.style_dashed, width=1, extend=extend.both))"
            )

        # Level lines and labels (prices are SPY values — no factor conversion)
        for cat, (clr_var, sty_var) in CAT_CONFIG.items():
            for lbl, price in parse_level_string(entry.get(cat, "")):
                safe_lbl  = sanitize_label(lbl)
                label_txt = f"{safe_lbl} (${int(round(price))})"
                block_lines.append(
                    f"        array.push(_lines, line.new(_bi{i}, {price:.1f}, _bi{i} + W, {price:.1f}, "
                    f"color={clr_var}, style=f_style({sty_var}), width=2))"
                )
                block_lines.append(
                    f'        array.push(_labels, label.new(_bi{i} + W, {price:.1f}, '
                    f'"{label_txt}", color=color.new(color.black, 100), textcolor={clr_var}, '
                    f"style=label.style_none, size=size.small))"
                )

        draw_blocks.append("\n".join(block_lines))

    return PINE_TEMPLATE.format(
        generated_date   = date.today().strftime("%Y-%m-%d"),
        total_weeks      = len(history),
        bi_vars          = "\n".join(bi_vars_lines),
        bi_detections    = "\n".join(bi_detections_lines),
        draw_weeks_block = "\n\n".join(draw_blocks),
    )


def generate_pine_current(entry: dict) -> str:
    """Generates the current-levels indicator (daily/hourly) from the most recent week.

    Price levels use plot() — stable on zoom/scroll/symbol change.
    Color inputs work with plot(). Style inputs are not available for plot().
    Labels use label.new() at barstate.islast.
    """
    week_date = entry["week"]
    mon_ts    = monday_ts_ms(week_date)

    SHOW_VAR = {
        "gflip":    "show_gflip",
        "pos":      "show_pos",
        "neg":      "show_neg",
        "agg":      "show_agg",
        "pos_zone": "show_neg",
        "neg_zone": "show_neg",
    }

    plot_lines  = []
    label_lines = []

    for cat, (clr_var, _) in CAT_CONFIG.items():
        show = SHOW_VAR[cat]
        for lbl, price in parse_level_string(entry.get(cat, "")):
            safe_lbl  = sanitize_label(lbl)
            label_txt = f"{safe_lbl} (${int(round(price))})"
            plot_lines.append(
                f'plot({show} and _in_week ? {price:.1f} : na, "{label_txt}", '
                f"color={clr_var}, style=plot.style_linebr, linewidth=2)"
            )
            label_lines.append(f"    if {show}")
            label_lines.append(
                f'        array.push(_B, label.new(_lbl, {price:.1f}, "{label_txt}", '
                f"xloc=xloc.bar_time, color=color.new(color.black, 100), textcolor={clr_var}, "
                f"style=label.style_none, size=size.small))"
            )

    return PINE_CURRENT_TEMPLATE.format(
        generated_date = date.today().strftime("%Y-%m-%d"),
        week_date      = week_date,
        mon_ts         = mon_ts,
        plot_calls     = "\n".join(plot_lines)  if plot_lines  else "// no levels",
        label_calls    = "\n".join(label_lines) if label_lines else "    na",
    )

# --- FORMATTED OUTPUT --------------------------------------------------------

def print_output(strings: dict, week_date: str):
    sep = "=" * 64
    print(sep)
    print(f"  GEX WEEKLY LEVELS -- {week_date}   (SPY prices)")
    print(sep)
    fields = [
        ("gflip",    "Gamma Flip    "),
        ("pos",      "Positive GEX  "),
        ("neg",      "Negative GEX  "),
        ("agg",      "Aggregate     "),
        ("pos_zone", "Pos Zone Start"),
        ("neg_zone", "Neg Zone Start"),
    ]
    for key, label in fields:
        val = strings.get(key, "")
        if val:
            print(f"  {label} ->  {val}")
        else:
            print(f"  {label} ->  (empty)")
    print(sep)

# --- MAIN --------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Saves GEX levels and generates the weekly Pine Script",
        epilog="Example: python scripts/gex_input.py --week 2026-04-14"
    )
    parser.add_argument("--week",    type=str,  default=None, help="Monday date YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true",     help="Show output without saving")
    args = parser.parse_args()

    week_date = args.week or most_recent_monday()
    dt = datetime.strptime(week_date, "%Y-%m-%d")
    if dt.weekday() != 0:
        correct = (dt - timedelta(days=dt.weekday())).strftime("%Y-%m-%d")
        print(f"[WARNING] {week_date} is not a Monday! Use --week {correct}")

    if not LEVELS_FILE.exists():
        print(f"[ERROR] File not found: {LEVELS_FILE}"); raise SystemExit(1)

    levels = parse_levels_file(LEVELS_FILE)
    if not levels:
        print("[ERROR] No valid levels in gex_levels.txt."); raise SystemExit(1)

    grouped = group_levels(levels)
    strings = grouped_to_strings(grouped)
    total   = sum(len(v) for v in grouped.values())

    print(f"\nLevels loaded: {total}  |  Week: {week_date}\n")
    print_output(strings, week_date)

    if args.dry_run:
        print("\n[dry-run] Nothing saved."); return

    print()
    history = save_history(load_history(), week_date, strings)

    # --- Weekly indicator (15m chart, Monday-to-Monday segments) ---
    pine = generate_pine(history)
    PINE_FILE.write_text(pine, encoding="utf-8")
    print(f"  Generated (weekly 15m) : {PINE_FILE.name}")

    # --- Current levels indicator (daily/hourly, extends right) ---
    most_recent = history[-1]
    pine_current = generate_pine_current(most_recent)
    PINE_CURRENT_FILE.write_text(pine_current, encoding="utf-8")
    print(f"  Generated (current D/H): {PINE_CURRENT_FILE.name}")

    print()
    print("-" * 64)
    print("  NEXT STEPS:")
    print("  Weekly (15m)  : paste gex_weekly_levels.pine  -> TradingView")
    print("  Current (D/H) : paste gex_current_levels.pine -> TradingView")
    print("-" * 64)
    print()

if __name__ == "__main__":
    main()
