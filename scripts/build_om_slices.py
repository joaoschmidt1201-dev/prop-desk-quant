#!/usr/bin/env python3
"""
build_om_slices.py
──────────────────
Generates 2 TICKER-GROUP Pine files from `tradingview/occurrence_matrix.pine`,
each running only the BASELINE tolerance (idx 2):

  - occurrence_matrix_g1.pine — tickers 01..16, baseline tol only
  - occurrence_matrix_g2.pine — tickers 17..32, baseline tol only

Why ticker groups (v14):
  Memory on TradingView is dominated by the number of `request.security`
  contexts (each ~9 heavy series over 210 bars), NOT by the tolerance count.
  With 32 tickers × 7 levels even a single tolerance (~224 state machines,
  32 securities) blew Pine's "Memory limits exceeded". Splitting the tickers
  into 2 groups of 16 (16 securities, 112 machines) loads comfortably — that
  is well under the ~29 securities that ran before.

Why baseline only:
  CZ wants just the baseline tolerance table (per-TF/per-MA), so we drop the
  5-level tolerance grid. Each group emits idx 2 only; `om_paste_snapshot.py
  --merge-tickers` unions the two groups AND collapses each ticker to the
  28-int baseline block (grid_size 1).

Run all groups per TF, then merge:
  # G1 (add occurrence_matrix_g1.pine, copy Pine Logs):
  Get-Clipboard | python scripts/om_paste_snapshot.py 2026-07-01 D --out G1.json
  # G2:
  Get-Clipboard | python scripts/om_paste_snapshot.py 2026-07-01 D --out G2.json
  # merge:
  python scripts/om_paste_snapshot.py 2026-07-01 D --merge-tickers G1.json G2.json

Re-run after editing the main file:
  python scripts/build_om_slices.py
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN_PINE = ROOT / "tradingview" / "occurrence_matrix.pine"

# Baseline tolerance index (matches v12.8 / the CZ baseline table).
BASELINE_IDX = 2

# Each group runs a disjoint set of tickers (1-indexed, inclusive) at baseline tol.
# 4 groups of 8 (56 machines/pass) so INTRADAY (2m/5m load far more bars per
# security) also fits memory. Daily/Weekly fit with fewer groups but this scheme
# works for every TF. Merge unions all groups regardless of count.
GROUPS = {
    "g1": {"keep": range(1, 9),   "title_suffix": "G1 t1-8",   "ver_suffix": "g1"},
    "g2": {"keep": range(9, 17),  "title_suffix": "G2 t9-16",  "ver_suffix": "g2"},
    "g3": {"keep": range(17, 25), "title_suffix": "G3 t17-24", "ver_suffix": "g3"},
    "g4": {"keep": range(25, 33), "title_suffix": "G4 t25-32", "ver_suffix": "g4"},
}


def transform_state_machine_calls(text: str, active_indices: set[int]) -> str:
    """Keep run_sm_gated() lines for active tol indices (as direct run_sm calls);
    replace inactive ones with zero-init declarations so the CSV concat is unchanged."""
    pattern = re.compile(
        r"^(\s*)\[m(\d)T_(\d), m\2B_\3, m\2K_\3, m\2F_\3\] = run_sm_gated\((\w+), (.+)\)$",
        re.MULTILINE,
    )

    def replace(match: re.Match) -> str:
        indent = match.group(1)
        ma_idx = match.group(2)
        tol_idx = int(match.group(3))
        rest_args = match.group(5)
        if tol_idx in active_indices:
            return (
                f"{indent}[m{ma_idx}T_{tol_idx}, m{ma_idx}B_{tol_idx}, "
                f"m{ma_idx}K_{tol_idx}, m{ma_idx}F_{tol_idx}] = run_sm({rest_args})"
            )
        return (
            f"{indent}int m{ma_idx}T_{tol_idx} = 0\n"
            f"{indent}int m{ma_idx}B_{tol_idx} = 0\n"
            f"{indent}int m{ma_idx}K_{tol_idx} = 0\n"
            f"{indent}int m{ma_idx}F_{tol_idx} = 0"
        )

    return pattern.sub(replace, text)


def remove_chart_direct_fallback(text: str) -> str:
    """Drop the chart-direct `d_str = run_full()` and the 32 DIRECT overrides,
    replacing section 5b with simple aa01..aa32 := a01..a32 aliases (saves one
    full run_full context)."""
    start_marker = "// ==========================================\n// 5b. DIRECT FALLBACK FOR CHART TICKER"
    end_marker_pattern = re.compile(
        r"if barstate\.islast and dbgEnable\n    log\.info\(\"CHART-ID = \'\" \+ chartId.*?\n",
        re.DOTALL,
    )
    start_idx = text.find(start_marker)
    if start_idx == -1:
        return text
    end_match = end_marker_pattern.search(text, start_idx)
    if not end_match:
        return text
    aliases = "\n".join(f"aa{i:02d} = a{i:02d}" for i in range(1, 33))
    replacement = (
        "// ==========================================\n"
        "// 5b. NO DIRECT FALLBACK (slice file — chart-ticker parity disabled to save memory)\n"
        "// ==========================================\n"
        + aliases
        + "\n\n"
    )
    return text[:start_idx] + replacement + text[end_match.end():]


def restrict_tickers(text: str, keep: set[int]) -> str:
    """Keep only the `keep` tickers' request.security + export + table rows.

    Out-of-group tickers:
      - `aNN = request.security(...)` → `string aNN = na` (no security context = memory saved)
      - their `log.info(fmt_row(...))`, `alert(fmt_row(...))` and
        `render_row_from_csv(...)` lines are dropped from the output.
    The first kept ticker in each of the log/alert blocks gets `false` for the
    leading-comma flag (JSON `data:{` opener); the rest get `true`.
    """
    out: list[str] = []
    log_seen = False
    alert_seen = False
    re_req = re.compile(r"^a(\d\d) = request\.security\(")
    re_log = re.compile(r"^    log\.info\(fmt_row\(n(\d\d), aa\d\d, (?:true|false)\)\)$")
    re_alert = re.compile(
        r"^    alert\(fmt_row\(n(\d\d), aa\d\d, (?:true|false)\),  alert\.freq_once_per_bar_close\)$"
    )
    re_row = re.compile(r"^    render_row_from_csv\(\s*\d+, n(\d\d),")

    for line in text.split("\n"):
        m = re_req.match(line)
        if m:
            nn = int(m.group(1))
            out.append(line if nn in keep else f"string a{m.group(1)} = na")
            continue
        m = re_log.match(line)
        if m:
            nn = int(m.group(1))
            if nn not in keep:
                continue
            lead = "false" if not log_seen else "true"
            log_seen = True
            out.append(f"    log.info(fmt_row(n{m.group(1)}, aa{m.group(1)}, {lead}))")
            continue
        m = re_alert.match(line)
        if m:
            nn = int(m.group(1))
            if nn not in keep:
                continue
            lead = "false" if not alert_seen else "true"
            alert_seen = True
            out.append(
                f"    alert(fmt_row(n{m.group(1)}, aa{m.group(1)}, {lead}),  alert.freq_once_per_bar_close)"
            )
            continue
        m = re_row.match(line)
        if m:
            nn = int(m.group(1))
            if nn not in keep:
                continue
            out.append(line)
            continue
        out.append(line)
    return "\n".join(out)


def transform_metadata(text: str, title_suffix: str, ver_suffix: str) -> str:
    """Pin baseline-only slice flags, update indicator title/version, and the
    emitted tol_idx_slots ([2] = baseline)."""
    out = text
    out = out.replace(
        'indicator("Occurrence Matrix [ST]", shorttitle="OM [ST]"',
        f'indicator("Occurrence Matrix [ST] — {title_suffix}", shorttitle="OM {title_suffix}"',
        1,
    )
    out = re.sub(
        r'string ver_num\s*=\s*"v\d[\w.\-]+"',
        f'string ver_num  = "v15.0-BAND-{ver_suffix}"',
        out,
        count=1,
    )
    for i in range(5):
        on = i == BASELINE_IDX
        out = re.sub(
            rf'sliceActive{i}\s*=\s*.*$',
            f'sliceActive{i} = {str(on).lower()}',
            out,
            count=1,
            flags=re.MULTILINE,
        )
    slots_str = f"[{BASELINE_IDX}]"
    out = re.sub(r'string slice_json = .*?$', f'string slice_json = "{slots_str}"', out, count=1, flags=re.MULTILINE)
    out = re.sub(r'string slice_json_a = .*?$', f'string slice_json_a = "{slots_str}"', out, count=1, flags=re.MULTILINE)
    return out


def add_generated_banner(text: str, slice_name: str) -> str:
    banner = (
        "// === AUTO-GENERATED FROM tradingview/occurrence_matrix.pine ===\n"
        f"// Ticker group: {slice_name.upper()} · baseline tol only\n"
        "// DO NOT EDIT MANUALLY. Re-generate with:\n"
        "//   python scripts/build_om_slices.py\n"
        "// ================================================================\n"
    )
    return re.sub(r"^(//@version=5\s*\n)", r"\1" + banner, text, count=1, flags=re.MULTILINE)


def build_one(name: str, keep: range, title_suffix: str, ver_suffix: str) -> None:
    src = MAIN_PINE.read_text(encoding="utf-8")
    out = transform_state_machine_calls(src, {BASELINE_IDX})
    out = remove_chart_direct_fallback(out)
    out = restrict_tickers(out, set(keep))
    out = transform_metadata(out, title_suffix, ver_suffix)
    out = add_generated_banner(out, name)
    dst = ROOT / "tradingview" / f"occurrence_matrix_{name}.pine"
    dst.write_text(out, encoding="utf-8")
    n_tickers = len(keep)
    print(f"Wrote {dst.relative_to(ROOT)} · {n_tickers} tickers · baseline tol · {n_tickers * 7} state-machine call sites")


def main() -> None:
    if not MAIN_PINE.exists():
        raise SystemExit(f"Missing source: {MAIN_PINE}")
    for name, cfg in GROUPS.items():
        build_one(name, cfg["keep"], cfg["title_suffix"], cfg["ver_suffix"])


if __name__ == "__main__":
    main()
