from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.occurrence_matrix_report import (  # noqa: E402
    CATEGORIES,
    MA_NAMES,
    MIN_SAMPLE,
    baseline_tol_idx,
    count_block,
    load_snapshot as load_report_snapshot,
    snapshot_grid_size,
    universe_tickers,
)

# Per-ticker stride: 5 MAs × 4 metrics = 20 ints per tolerance level.
TICKER_STRIDE = len(MA_NAMES) * 4

TF_ORDER = ("W", "D", "1h", "15m", "5m", "2m")
TF_ALIASES = {
    "d": "D",
    "1d": "D",
    "w": "W",
    "1w": "W",
    "60": "1h",
    "1h": "1h",
    "2": "2m",
    "2m": "2m",
    "5": "5m",
    "5m": "5m",
    "15": "15m",
    "15m": "15m",
}


def canonicalize_tf(value: Any) -> str | None:
    if value is None:
        return None
    return TF_ALIASES.get(str(value).strip().lower())


def snapshot_mtimes(snapshots_dir: Path) -> dict[str, float]:
    if not snapshots_dir.exists():
        return {}
    return {path.name: path.stat().st_mtime for path in sorted(snapshots_dir.glob("*.json"))}


def _file_tf(path: Path) -> str | None:
    if "_" not in path.stem:
        return None
    return canonicalize_tf(path.stem.rsplit("_", 1)[-1])


def _load_snapshot_for_file(path: Path) -> tuple[str, dict[str, Any]]:
    file_tf = _file_tf(path)
    if file_tf is None:
        raise ValueError(f"Snapshot filename must end with a supported TF suffix: {path.name}")

    raw = json.loads(path.read_text(encoding="utf-8"))
    raw_tf = raw.get("tf")
    raw_canonical_tf = canonicalize_tf(raw_tf)
    if raw_canonical_tf != file_tf:
        raise ValueError(
            f"Snapshot {path.name} has tf={raw_tf!r}, which does not match filename TF {file_tf!r}."
        )

    snapshot = load_report_snapshot(path, str(raw_tf))
    snapshot["tf"] = file_tf
    snapshot["_raw_tf"] = raw_tf
    snapshot["_file"] = path.name
    snapshot["_mtime"] = path.stat().st_mtime
    return file_tf, snapshot


def load_latest_snapshots(snapshots_dir: Path) -> dict[str, dict[str, Any]]:
    """Load the newest valid snapshot for each canonical timeframe."""
    if not snapshots_dir.exists():
        return {}

    latest: dict[str, dict[str, Any]] = {}
    for path in sorted(snapshots_dir.glob("*.json")):
        tf, snapshot = _load_snapshot_for_file(path)
        current = latest.get(tf)
        next_key = (str(snapshot["d"]), float(snapshot["_mtime"]))
        current_key = (str(current["d"]), float(current["_mtime"])) if current else ("", 0.0)
        if current is None or next_key > current_key:
            latest[tf] = snapshot

    return {tf: latest[tf] for tf in TF_ORDER if tf in latest}


def _pct(part: int, total: int) -> int | None:
    if total <= 0:
        return None
    return round(part / total * 100)


def _snapshot_age_seconds(snapshot_date: str) -> float | None:
    try:
        dt = datetime.fromisoformat(snapshot_date).replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds())


def _coerce_float(item: Any) -> float | None:
    if item is None:
        return None
    if isinstance(item, (int, float)):
        return float(item)
    text = str(item).strip().lower()
    if text in {"", "na", "n/a", "skip", "none", "null"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _normalize_tol_grid(snapshot: dict[str, Any], grid_size: int) -> dict[str, list[float | None]]:
    """Build a per-MA tolerance grid from either the v13 `tol_grid` dict
    or the legacy v12.x `tolerances` list (single tolerance per MA).

    Returns {MA_NAME: [v0, v1, ..., v_{grid_size-1}]}. Values may be None
    when a level is intentionally skipped (e.g. VWAP on D/W) or missing.
    """
    raw_grid = snapshot.get("tol_grid")
    grid: dict[str, list[float | None]] = {}

    if isinstance(raw_grid, dict):
        # v13 schema: {"EMA9": [..5..], "EMA20": [..5..], ...}
        # Pine emits keys without spaces; report MA names are "EMA 9", "EMA 20", etc.
        ma_key_aliases = {
            "EMA 9": ("EMA 9", "EMA9"),
            "EMA 20": ("EMA 20", "EMA20"),
            "SMA 50": ("SMA 50", "SMA50"),
            "SMA 200": ("SMA 200", "SMA200"),
            "VWAP": ("VWAP",),
            "BB Upper": ("BB Upper", "BBu", "BB_U", "BBU"),
            "BB Lower": ("BB Lower", "BBl", "BB_L", "BBL"),
        }
        for ma_name in MA_NAMES:
            row: list[float | None] = []
            source: Any = None
            for alias in ma_key_aliases.get(ma_name, (ma_name,)):
                if alias in raw_grid:
                    source = raw_grid[alias]
                    break
            if isinstance(source, list):
                for item in source[:grid_size]:
                    val = _coerce_float(item)
                    row.append(val if (val is None or val > 0) else None)
            while len(row) < grid_size:
                row.append(None)
            grid[ma_name] = row
        return grid

    # Legacy v12.x: snapshot has `tolerances: [v_ma0, v_ma1, v_ma2, v_ma3, v_ma4]`.
    legacy = snapshot.get("tolerances")
    if isinstance(legacy, list):
        for ma_index, ma_name in enumerate(MA_NAMES):
            val = _coerce_float(legacy[ma_index]) if ma_index < len(legacy) else None
            normalized = val if (val is None or val > 0) else None
            grid[ma_name] = [normalized] * grid_size
        return grid

    # No tolerance metadata at all.
    for ma_name in MA_NAMES:
        grid[ma_name] = [None] * grid_size
    return grid


def _metric(
    values: list[int],
    ma_index: int,
    tol_idx: int,
    tolerance_pct: float | None,
) -> dict[str, Any]:
    total, bounce, break_count, false_count = count_block(values, ma_index, tol_idx)
    return {
        "T": total,
        "B": bounce,
        "Bk": break_count,
        "F": false_count,
        "bounce_pct": _pct(bounce, total),
        "break_pct": _pct(break_count, total),
        "false_pct": _pct(false_count, total),
        "low_sample": total < MIN_SAMPLE,
        "tolerance_pct": tolerance_pct,
    }


def _leaderboard_rows(setups: list[dict[str, Any]], primary: str) -> list[dict[str, Any]]:
    rows = sorted(
        setups,
        key=lambda item: (
            -(item[primary] if item[primary] is not None else -1),
            -item["total"],
            item["ticker"],
            item["tf"],
            item["ma"],
        ),
    )[:5]
    return rows


def _top_setups_per_ticker(
    setups: list[dict[str, Any]],
    n: int = 3,
    primary: str = "bounce_pct",
) -> dict[str, list[dict[str, Any]]]:
    """Group qualified setups by ticker, sort by primary metric desc, take top N each."""
    by_ticker: dict[str, list[dict[str, Any]]] = {}
    for setup in setups:
        by_ticker.setdefault(setup["ticker"], []).append(setup)

    result: dict[str, list[dict[str, Any]]] = {}
    for ticker, entries in by_ticker.items():
        ranked = sorted(
            entries,
            key=lambda item: (
                -(item[primary] if item[primary] is not None else -1),
                -item["total"],
                item["tf"],
                item["ma"],
            ),
        )[:n]
        result[ticker] = [
            {
                "tf": entry["tf"],
                "ma": entry["ma"],
                "total": entry["total"],
                "bounce_pct": entry["bounce_pct"],
                "break_pct": entry["break_pct"],
                "false_pct": entry["false_pct"],
            }
            for entry in ranked
        ]
    return result


def _clamp_tol_idx(requested: int | None, grid_size: int) -> int:
    """Clamp a requested tol_idx to [0, grid_size-1], defaulting to baseline."""
    if grid_size <= 1:
        return 0
    if requested is None:
        return baseline_tol_idx(grid_size)
    return max(0, min(int(requested), grid_size - 1))


def build_matrix(
    snapshots: dict[str, dict[str, Any]],
    tol_idx_by_tf: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Build ticker x tf x ma metrics from raw TradingView snapshots.

    `tol_idx_by_tf` lets the caller pick which tolerance level to read for
    each TF. Out-of-range values are clamped; missing TFs fall back to the
    baseline (idx 2 for v13, idx 0 for v12.x).
    """
    tickers = universe_tickers()
    categories = [{"name": name, "tickers": list(category_tickers)} for name, category_tickers in CATEGORIES]
    tfs = [tf for tf in TF_ORDER if tf in snapshots]
    tol_idx_by_tf = tol_idx_by_tf or {}

    data: dict[str, dict[str, dict[str, dict[str, Any]]]] = {ticker: {} for ticker in tickers}
    tolerances: dict[str, list[float | None]] = {}
    tol_grids: dict[str, dict[str, list[float | None]]] = {}
    grid_sizes: dict[str, int] = {}
    selected_tol_idx: dict[str, int] = {}
    dates: dict[str, str] = {}
    snapshot_meta: dict[str, dict[str, Any]] = {}
    setups: list[dict[str, Any]] = []

    for tf in tfs:
        snapshot = snapshots[tf]
        snapshot_data = snapshot["data"]

        # Infer grid size from the first ticker (validated to be consistent).
        first_ticker_values = next(iter(snapshot_data.values()), [])
        try:
            grid_size = snapshot_grid_size(len(first_ticker_values)) if first_ticker_values else 1
        except ValueError:
            grid_size = 1
        grid_sizes[tf] = grid_size

        tf_tol_grid = _normalize_tol_grid(snapshot, grid_size)
        tol_grids[tf] = tf_tol_grid

        idx = _clamp_tol_idx(tol_idx_by_tf.get(tf), grid_size)
        selected_tol_idx[tf] = idx

        # Project the per-MA tolerance vector AT the selected idx — keeps
        # the legacy `tolerances` field stable for current frontend consumers.
        tf_tolerances = [tf_tol_grid[ma_name][idx] if idx < len(tf_tol_grid[ma_name]) else None for ma_name in MA_NAMES]
        tolerances[tf] = tf_tolerances

        dates[tf] = str(snapshot["d"])
        age_seconds = _snapshot_age_seconds(str(snapshot["d"]))
        snapshot_meta[tf] = {
            "date": str(snapshot["d"]),
            "file": str(snapshot["_file"]),
            "raw_tf": str(snapshot["_raw_tf"]),
            "age_seconds": age_seconds,
            "has_tolerances": isinstance(snapshot.get("tolerances"), list)
                or isinstance(snapshot.get("tol_grid"), dict),
            "grid_size": grid_size,
            "selected_tol_idx": idx,
        }

        for ticker in tickers:
            values = snapshot_data[ticker]
            data[ticker][tf] = {}
            for ma_index, ma_name in enumerate(MA_NAMES):
                metric = _metric(values, ma_index, idx, tf_tolerances[ma_index])
                data[ticker][tf][ma_name] = metric
                if metric["T"] >= MIN_SAMPLE:
                    setups.append(
                        {
                            "ticker": ticker,
                            "tf": tf,
                            "ma": ma_name,
                            "total": metric["T"],
                            "bounce_pct": metric["bounce_pct"],
                            "break_pct": metric["break_pct"],
                            "false_pct": metric["false_pct"],
                        }
                    )

    latest_date = max(dates.values()) if dates else None
    oldest_date = min(dates.values()) if dates else None
    ages = [
        meta["age_seconds"]
        for meta in snapshot_meta.values()
        if isinstance(meta.get("age_seconds"), (int, float))
    ]

    return {
        "date": latest_date,
        "latest_snapshot_date": latest_date,
        "oldest_snapshot_date": oldest_date,
        "oldest_snapshot_age_seconds": max(ages) if ages else None,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "expected_tfs": list(TF_ORDER),
        "tfs": tfs,
        "mas": list(MA_NAMES),
        "min_sample": MIN_SAMPLE,
        "categories": categories,
        "tickers": tickers,
        "dates": dates,
        "snapshots": snapshot_meta,
        "tolerances": tolerances,
        "tol_grids": tol_grids,
        "grid_sizes": grid_sizes,
        "selected_tol_idx": selected_tol_idx,
        "data": data,
        "leaderboards": {
            "mean_reversion": _leaderboard_rows(setups, "bounce_pct"),
            "breakout": _leaderboard_rows(setups, "break_pct"),
        },
        "top_setups": _top_setups_per_ticker(setups, n=3, primary="bounce_pct"),
    }


def matrix_health(snapshots_dir: Path) -> dict[str, Any]:
    snapshots = load_latest_snapshots(snapshots_dir)
    if not snapshots:
        return {
            "occurrence_matrix_oldest_snapshot_age_seconds": None,
            "occurrence_matrix_snapshot_tfs": [],
        }
    matrix = build_matrix(snapshots)
    return {
        "occurrence_matrix_oldest_snapshot_age_seconds": matrix["oldest_snapshot_age_seconds"],
        "occurrence_matrix_snapshot_tfs": matrix["tfs"],
    }
