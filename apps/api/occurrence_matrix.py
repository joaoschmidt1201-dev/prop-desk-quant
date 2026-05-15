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
    count_block,
    load_snapshot as load_report_snapshot,
    universe_tickers,
)

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


def _normalize_tolerances(raw: Any) -> list[float | None]:
    if not isinstance(raw, list):
        return [None] * len(MA_NAMES)

    values: list[float | None] = []
    for item in raw[: len(MA_NAMES)]:
        if item is None:
            values.append(None)
        elif isinstance(item, (int, float)):
            values.append(float(item))
        else:
            text = str(item).strip().lower()
            if text in {"", "na", "n/a", "skip", "none", "null"}:
                values.append(None)
            else:
                try:
                    values.append(float(text))
                except ValueError:
                    values.append(None)

    while len(values) < len(MA_NAMES):
        values.append(None)
    return values


def _metric(values: list[int], ma_index: int, tolerance_pct: float | None) -> dict[str, Any]:
    total, bounce, break_count, false_count = count_block(values, ma_index)
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


def build_matrix(snapshots: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Build ticker x tf x ma metrics from raw TradingView snapshots."""
    tickers = universe_tickers()
    categories = [{"name": name, "tickers": list(category_tickers)} for name, category_tickers in CATEGORIES]
    tfs = [tf for tf in TF_ORDER if tf in snapshots]

    data: dict[str, dict[str, dict[str, dict[str, Any]]]] = {ticker: {} for ticker in tickers}
    tolerances: dict[str, list[float | None]] = {}
    dates: dict[str, str] = {}
    snapshot_meta: dict[str, dict[str, Any]] = {}
    setups: list[dict[str, Any]] = []

    for tf in tfs:
        snapshot = snapshots[tf]
        snapshot_data = snapshot["data"]
        tf_tolerances = _normalize_tolerances(snapshot.get("tolerances"))
        tolerances[tf] = tf_tolerances
        dates[tf] = str(snapshot["d"])
        age_seconds = _snapshot_age_seconds(str(snapshot["d"]))
        snapshot_meta[tf] = {
            "date": str(snapshot["d"]),
            "file": str(snapshot["_file"]),
            "raw_tf": str(snapshot["_raw_tf"]),
            "age_seconds": age_seconds,
            "has_tolerances": isinstance(snapshot.get("tolerances"), list),
        }

        for ticker in tickers:
            values = snapshot_data[ticker]
            data[ticker][tf] = {}
            for ma_index, ma_name in enumerate(MA_NAMES):
                metric = _metric(values, ma_index, tf_tolerances[ma_index])
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
