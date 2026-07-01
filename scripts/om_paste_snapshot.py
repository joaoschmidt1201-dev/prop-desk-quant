#!/usr/bin/env python3
"""
om_paste_snapshot.py
────────────────────
Assemble an Occurrence Matrix v13 snapshot from a Pine Logs paste.

Pine v5 caps strings at 4096 chars, so the v13 indicator emits the JSON
payload as a sequence of ~30 log.info() lines (head + 29 ticker rows +
footer), delimited by BEGIN/END markers. This helper:

  1. Reads pasted Pine Logs from stdin (or `--file PATH`).
  2. Strips TradingView's timestamp prefix from each line.
  3. Locates BEGIN/END markers and concatenates the lines between them.
  4. Validates the result as JSON.
  5. Writes to `state/occurrence_matrix_snapshots/<DATE>_<TF>.json`.

Usage:
  # From clipboard (Windows PowerShell):
  Get-Clipboard | python scripts/om_paste_snapshot.py 2026-05-19 D

  # From a file:
  python scripts/om_paste_snapshot.py 2026-05-19 D --file pine_paste.txt

  # Dry run (don't write, just validate and print):
  python scripts/om_paste_snapshot.py 2026-05-19 D --dry-run < pine_paste.txt

  # Merge 2-3 partial slice snapshots (when running with Memory Saver A/B/C):
  python scripts/om_paste_snapshot.py 2026-05-19 D --merge slice_A.json slice_B.json slice_C.json
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_DIR = ROOT / "state" / "occurrence_matrix_snapshots"

BEGIN_MARKER = "--- OM SNAPSHOT BEGIN ---"
END_MARKER = "--- OM SNAPSHOT END ---"

# TradingView's Pine Logs panel prefixes each line with a timestamp like:
#   [2026-05-19T11:07:23.000-03:00]: {...}
# Various copy-paste flows may also include a trailing source tag or other
# bracketed metadata; we strip everything from the start of the line up to
# the last "]:" or "] " on that line.
TIMESTAMP_PREFIX_RE = re.compile(r"^\s*\[[^\]]+\]\s*:?\s*")

TF_ALIASES = {
    "D": "D", "d": "D", "1d": "D", "1D": "D",
    "W": "W", "w": "W", "1w": "W", "1W": "W",
    "1h": "1h", "1H": "1h", "60": "1h",
    "15m": "15m", "15": "15m",
    "5m": "5m", "5": "5m",
    "2m": "2m", "2": "2m",
}


def strip_timestamp(line: str) -> str:
    return TIMESTAMP_PREFIX_RE.sub("", line).rstrip()


def maybe_extract_csv(raw_text: str) -> str:
    """If the input is a TradingView Pine Logs CSV export (header `Date,Message`),
    return just the Message column, one entry per line, so assemble() can find the
    BEGIN/END block. Otherwise return the text unchanged (plain paste)."""
    stripped = raw_text.lstrip()
    first_line = stripped.splitlines()[0] if stripped else ""
    if first_line.strip().lower().lstrip("﻿") not in ("date,message", "message,date"):
        return raw_text
    reader = csv.reader(io.StringIO(raw_text))
    rows = list(reader)
    if not rows:
        return raw_text
    header = [h.strip().lower().lstrip("﻿") for h in rows[0]]
    msg_idx = header.index("message") if "message" in header else 1
    messages = [row[msg_idx] for row in rows[1:] if len(row) > msg_idx]
    return "\n".join(messages)


def assemble(raw_text: str) -> str:
    lines = [strip_timestamp(line) for line in raw_text.splitlines()]
    # Find BEGIN ... END markers. We take the LAST occurrence so multiple
    # runs in the same Pine Logs session still resolve correctly.
    begin_idx = None
    end_idx = None
    for i, line in enumerate(lines):
        if line == BEGIN_MARKER:
            begin_idx = i
        elif line == END_MARKER and begin_idx is not None:
            end_idx = i
    if begin_idx is None or end_idx is None or end_idx <= begin_idx:
        raise ValueError(
            f"Could not find a {BEGIN_MARKER!r} ... {END_MARKER!r} block in the input. "
            "Make sure you copied the full snapshot from Pine Logs, including both markers."
        )
    body_lines = [line for line in lines[begin_idx + 1 : end_idx] if line]
    if not body_lines:
        raise ValueError("Snapshot block is empty.")
    return "".join(body_lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Assemble an Occurrence Matrix v13 snapshot from pasted Pine Logs."
    )
    parser.add_argument("date", help="Snapshot date YYYY-MM-DD")
    parser.add_argument(
        "tf",
        help="Timeframe (W, D, 1h, 15m, 5m, 2m — aliases like '60' for 1h accepted)",
    )
    parser.add_argument("--file", dest="input_file", help="Read paste from FILE instead of stdin")
    parser.add_argument(
        "--out",
        dest="out_path",
        help="Override output path (default: state/occurrence_matrix_snapshots/<date>_<tf>.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print summary but do not write the snapshot file.",
    )
    parser.add_argument(
        "--merge",
        dest="merge_inputs",
        nargs="+",
        help=(
            "Merge 2-3 partial slice snapshots (JSON files emitted with Memory Saver "
            "A/B/C). Each file's `tol_idx_slots` lists which tol indices it covers; "
            "the union must equal [0,1,2,3,4] with no overlaps."
        ),
    )
    parser.add_argument(
        "--merge-tickers",
        dest="merge_ticker_inputs",
        nargs="+",
        help=(
            "Merge disjoint TICKER-GROUP snapshots (v14 g1/g2 baseline files). Unions "
            "their ticker sets and collapses to the 28-int baseline block (grid_size 1)."
        ),
    )
    return parser.parse_args()


# Ints per tolerance level = (number of levels) × 4 metrics (T,B,Bk,F).
# Derived from MA_NAMES so it tracks v14 (7 levels → 28) automatically.
try:
    from occurrence_matrix_report import MA_NAMES as _MA_NAMES  # same scripts/ dir
    STRIDE = len(_MA_NAMES) * 4
except Exception:  # pragma: no cover - fallback if run oddly
    STRIDE = 28


def merge_slices(paths: list[str]) -> dict:
    """Combine slice snapshots into a single v13 snapshot covering all 5 tol indices."""
    slices: list[dict] = []
    for p in paths:
        snap = json.loads(Path(p).read_text(encoding="utf-8"))
        slots = snap.get("tol_idx_slots")
        if not isinstance(slots, list) or not all(isinstance(s, int) for s in slots):
            raise ValueError(
                f"{p}: missing or invalid `tol_idx_slots` field — was this snapshot "
                "produced by Pine v13.2 or later?"
            )
        slices.append({"path": p, "slots": slots, "snap": snap})

    # Validate slot coverage: union == {0,1,2,3,4}, no overlap.
    seen: dict[int, str] = {}
    for s in slices:
        for idx in s["slots"]:
            if idx in seen:
                raise ValueError(
                    f"tol_idx={idx} appears in both {seen[idx]} and {s['path']}."
                )
            seen[idx] = s["path"]
    missing = sorted(set(range(5)) - set(seen.keys()))
    if missing:
        raise ValueError(f"Missing tol indices in slice union: {missing}")

    # Pick the first slice as the template; verify date/tf/ma agree.
    base = slices[0]["snap"]
    for s in slices[1:]:
        for k in ("d", "tf", "ma"):
            if s["snap"].get(k) != base.get(k):
                raise ValueError(
                    f"{s['path']}: {k}={s['snap'].get(k)!r} disagrees with "
                    f"{slices[0]['path']}: {k}={base.get(k)!r}."
                )

    # Merge per ticker. Each ticker has 100 ints; copy the 20-int block at
    # tol_idx * STRIDE from the slice that owns that tol_idx.
    merged_data: dict[str, list[int]] = {}
    base_data = base.get("data", {})
    tickers = list(base_data.keys())
    for ticker in tickers:
        merged = [0] * (5 * STRIDE)
        for s in slices:
            arr = s["snap"]["data"].get(ticker, [])
            if len(arr) != 5 * STRIDE:
                raise ValueError(
                    f"{s['path']}: ticker {ticker} has {len(arr)} ints, expected {5 * STRIDE}."
                )
            for idx in s["slots"]:
                start = idx * STRIDE
                merged[start : start + STRIDE] = arr[start : start + STRIDE]
        merged_data[ticker] = merged

    out = {**base, "data": merged_data, "tol_idx_slots": [0, 1, 2, 3, 4]}
    return out


BASELINE_IDX = 2  # tol index that reproduces the CZ baseline table


def merge_ticker_groups(paths: list[str]) -> dict:
    """Combine disjoint TICKER-GROUP snapshots (v14 g1/g2) into ONE baseline
    snapshot. Each group ran only the baseline tolerance; we union their ticker
    sets and collapse every ticker to the 28-int baseline block (grid_size 1)."""
    groups = [json.loads(Path(p).read_text(encoding="utf-8")) for p in paths]
    base = groups[0]

    # Header agreement (date/tf/ma).
    for g, p in zip(groups[1:], paths[1:]):
        for k in ("d", "tf", "ma"):
            if g.get(k) != base.get(k):
                raise ValueError(f"{p}: {k}={g.get(k)!r} disagrees with {paths[0]}: {k}={base.get(k)!r}.")

    # Union tickers, rejecting overlaps.
    owner: dict[str, str] = {}
    merged_full: dict[str, list[int]] = {}
    for g, p in zip(groups, paths):
        for ticker, arr in g.get("data", {}).items():
            if ticker in owner:
                raise ValueError(f"ticker {ticker} appears in both {owner[ticker]} and {p}.")
            owner[ticker] = p
            merged_full[ticker] = arr

    # Collapse each ticker to the baseline block (28 ints).
    lo = BASELINE_IDX * STRIDE
    hi = lo + STRIDE
    collapsed: dict[str, list[int]] = {}
    for ticker, arr in merged_full.items():
        if len(arr) < hi:
            raise ValueError(f"ticker {ticker} has {len(arr)} ints; expected ≥ {hi} to read the baseline block.")
        collapsed[ticker] = arr[lo:hi]

    # Collapse tol_grid to a single baseline value per level.
    tol_grid = base.get("tol_grid")
    if isinstance(tol_grid, dict):
        tol_grid = {
            k: ([v[BASELINE_IDX]] if isinstance(v, list) and len(v) > BASELINE_IDX else v)
            for k, v in tol_grid.items()
        }

    out = {**base, "data": collapsed}
    if isinstance(tol_grid, dict):
        out["tol_grid"] = tol_grid
    out.pop("tol_idx_slots", None)  # single-tol snapshot → no slot metadata
    return out


def main() -> int:
    args = parse_args()

    try:
        date.fromisoformat(args.date)
    except ValueError as exc:
        print(f"ERROR: invalid date {args.date!r}: {exc}", file=sys.stderr)
        return 2

    tf = TF_ALIASES.get(args.tf)
    if tf is None:
        print(
            f"ERROR: invalid timeframe {args.tf!r}. Expected one of W, D, 1h, 15m, 5m, 2m.",
            file=sys.stderr,
        )
        return 2

    if args.merge_ticker_inputs:
        try:
            payload = merge_ticker_groups(args.merge_ticker_inputs)
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            print(f"ERROR: ticker merge failed: {exc}", file=sys.stderr)
            return 1
    elif args.merge_inputs:
        try:
            payload = merge_slices(args.merge_inputs)
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            print(f"ERROR: merge failed: {exc}", file=sys.stderr)
            return 1
    else:
        if args.input_file:
            raw_text = Path(args.input_file).read_text(encoding="utf-8")
        else:
            raw_text = sys.stdin.read()
        if not raw_text.strip():
            print("ERROR: input is empty (pipe a paste in via stdin or use --file)", file=sys.stderr)
            return 2

        raw_text = maybe_extract_csv(raw_text)
        try:
            payload_str = assemble(raw_text)
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

        try:
            payload = json.loads(payload_str)
        except json.JSONDecodeError as exc:
            print(f"ERROR: assembled payload is not valid JSON: {exc}", file=sys.stderr)
            print(f"First 400 chars:\n{payload_str[:400]}", file=sys.stderr)
            return 1

    snap_tf = payload.get("tf")
    if snap_tf is not None and TF_ALIASES.get(str(snap_tf), str(snap_tf)) != tf:
        print(
            f"WARNING: snapshot tf={snap_tf!r} but you asked to save as {tf!r}. "
            "Saving with the requested TF in the filename anyway.",
            file=sys.stderr,
        )

    data = payload.get("data", {})
    n_tickers = len(data) if isinstance(data, dict) else 0
    sample = next(iter(data.values()), []) if isinstance(data, dict) else []
    n_values = len(sample) if isinstance(sample, list) else 0
    schema = payload.get("schema", "(none)")
    grid = "full-grid" if n_values == 5 * STRIDE else "single-tol" if n_values == STRIDE else "???"
    print(
        f"Parsed OK · schema={schema} · tf={snap_tf!r} · d={payload.get('d')!r} · "
        f"tickers={n_tickers} · ints/ticker={n_values} "
        f"(stride={STRIDE}, {grid})"
    )

    if args.dry_run:
        return 0

    out_path = Path(args.out_path) if args.out_path else SNAPSHOT_DIR / f"{args.date}_{tf}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Wrote {out_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
