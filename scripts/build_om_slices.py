#!/usr/bin/env python3
"""
build_om_slices.py
──────────────────
Generates 3 sliced Pine files from `tradingview/occurrence_matrix.pine`:

  - occurrence_matrix_slice_a.pine — tol indices 0,1 only
  - occurrence_matrix_slice_b.pine — tol indices 2,3 only
  - occurrence_matrix_slice_c.pine — tol index 4 only

Why this is necessary:
  Pine v5 allocates `var` slots at COMPILE time, not runtime. Wrapping
  state-machine calls in `if active` doesn't actually shrink runtime
  memory — Pine still pre-reserves every call-site's history buffers.
  To truly cut memory, we must remove call sites from the SOURCE.

Each slice file:
  - Keeps only the run_sm_gated() lines for its tol indices; the rest
    become explicit `int mXT_Y = 0` declarations so the CSV concat
    code is unchanged.
  - Removes the chart-direct `d_str = run_full()` and the 29 DIRECT
    overrides (saves one full context — ~3-4% memory).
  - Hardcodes `tol_idx_slots` in the emitted JSON header so the merger
    knows which slots are authoritative.

Re-run after editing the main file:
  python scripts/build_om_slices.py
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN_PINE = ROOT / "tradingview" / "occurrence_matrix.pine"

SLICES = {
    "a": {"indices": [0, 1], "title_suffix": "Slice A 0,1", "ver_suffix": "a"},
    "b": {"indices": [2, 3], "title_suffix": "Slice B 2,3", "ver_suffix": "b"},
    "c": {"indices": [4],    "title_suffix": "Slice C 4",   "ver_suffix": "c"},
}


def transform_state_machine_calls(text: str, active_indices: set[int]) -> str:
    """Replace inactive run_sm_gated() lines with zero-init declarations.

    Matches lines of the form:
      [mXT_Y, mXB_Y, mXK_Y, mXF_Y] = run_sm_gated(...)
    For inactive Y, replace with:
      int mXT_Y = 0
      int mXB_Y = 0
      int mXK_Y = 0
      int mXF_Y = 0
    For active Y, replace `sliceActiveY` with `true` (no runtime gate needed).
    """
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
            # Active slot — strip the gating var (always true), call run_sm directly.
            return (
                f"{indent}[m{ma_idx}T_{tol_idx}, m{ma_idx}B_{tol_idx}, "
                f"m{ma_idx}K_{tol_idx}, m{ma_idx}F_{tol_idx}] = run_sm({rest_args})"
            )
        # Inactive slot — replace with zero-init, no run_sm call site.
        return (
            f"{indent}int m{ma_idx}T_{tol_idx} = 0\n"
            f"{indent}int m{ma_idx}B_{tol_idx} = 0\n"
            f"{indent}int m{ma_idx}K_{tol_idx} = 0\n"
            f"{indent}int m{ma_idx}F_{tol_idx} = 0"
        )

    return pattern.sub(replace, text)


def remove_chart_direct_fallback(text: str) -> str:
    """Remove the chart-direct `d_str = run_full()` and the 29 DIRECT overrides.

    Replaces the entire section 5b with simple `aa01 := a01` aliases — the
    chart-ticker parity feature is dropped for slice files (the dashboard
    consumes request.security results regardless, and parity bugs only
    matter for in-Pine auditing).
    """
    # Replace the d_str assignment + var declarations + 29 conditional reassignments
    # with a minimal aa01..aa29 := a01..a29 alias block.
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

    aliases = "\n".join(f"aa{i:02d} = a{i:02d}" for i in range(1, 30))
    replacement = (
        "// ==========================================\n"
        "// 5b. NO DIRECT FALLBACK (slice file — chart-ticker parity disabled to save memory)\n"
        "// ==========================================\n"
        + aliases
        + "\n\n"
    )

    return text[:start_idx] + replacement + text[end_match.end():]


def transform_slice_metadata(text: str, indices: list[int], title_suffix: str, ver_suffix: str) -> str:
    """Pin slice flags, update indicator title, version, and emitted tol_idx_slots."""
    out = text

    # 1. Indicator title (only the title; keep max_bars_back and overlay).
    out = out.replace(
        'indicator("Occurrence Matrix [ST]", shorttitle="OM [ST]"',
        f'indicator("Occurrence Matrix [ST] — {title_suffix}", shorttitle="OM {title_suffix}"',
        1,
    )

    # 2. Version string.
    out = re.sub(
        r'string ver_num\s*=\s*"v13\.\d+"',
        f'string ver_num  = "v13.3-{ver_suffix}"',
        out,
        count=1,
    )

    # 3. Hardcode sliceActive flags (so the unused tolSlice input never wires to anything live).
    for i in range(5):
        on = i in indices
        out = re.sub(
            rf'sliceActive{i}\s*=\s*tolSlice\s*==.*$',
            f'sliceActive{i} = {str(on).lower()}',
            out,
            count=1,
            flags=re.MULTILINE,
        )

    # 4. Hardcode tol_idx_slots in the emitted JSON header.
    slots_str = "[" + ",".join(str(i) for i in indices) + "]"
    out = re.sub(
        r'string slice_json = .*?$',
        f'string slice_json = "{slots_str}"',
        out,
        count=1,
        flags=re.MULTILINE,
    )
    out = re.sub(
        r'string slice_json_a = .*?$',
        f'string slice_json_a = "{slots_str}"',
        out,
        count=1,
        flags=re.MULTILINE,
    )

    return out


def add_generated_banner(text: str, slice_name: str) -> str:
    banner = (
        "// === AUTO-GENERATED FROM tradingview/occurrence_matrix.pine ===\n"
        f"// Slice: {slice_name.upper()}\n"
        "// DO NOT EDIT MANUALLY. Re-generate with:\n"
        "//   python scripts/build_om_slices.py\n"
        "// ================================================================\n"
    )
    # Insert after the //@version=5 line.
    return re.sub(r"^(//@version=5\s*\n)", r"\1" + banner, text, count=1, flags=re.MULTILINE)


def build_one(slice_name: str, indices: list[int], title_suffix: str, ver_suffix: str) -> None:
    src = MAIN_PINE.read_text(encoding="utf-8")
    out = transform_state_machine_calls(src, set(indices))
    out = remove_chart_direct_fallback(out)
    out = transform_slice_metadata(out, indices, title_suffix, ver_suffix)
    out = add_generated_banner(out, slice_name)
    dst = ROOT / "tradingview" / f"occurrence_matrix_slice_{slice_name}.pine"
    dst.write_text(out, encoding="utf-8")
    n_calls_kept = len(indices) * 5  # 5 MAs × N active tol indices
    print(f"Wrote {dst.relative_to(ROOT)} · {len(indices)} tol idx active · {n_calls_kept} state-machine call sites")


def main() -> None:
    if not MAIN_PINE.exists():
        raise SystemExit(f"Missing source: {MAIN_PINE}")
    for name, cfg in SLICES.items():
        build_one(name, cfg["indices"], cfg["title_suffix"], cfg["ver_suffix"])


if __name__ == "__main__":
    main()
