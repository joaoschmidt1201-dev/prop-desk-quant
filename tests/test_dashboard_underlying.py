from __future__ import annotations

import export_control_panel as export
from apps.api import main as api


def test_export_infers_js_forward_underlyings() -> None:
    assert export._infer_underlying("T01 XLE IC8") == "XLE"
    assert export._infer_underlying("T02 XSP IC42") == "XSP"


def test_api_backfills_unknown_underlyings_in_cached_snapshot() -> None:
    snap = {
        "trades": [
            {"name": "T01 XLE IC8", "underlying": "?"},
            {"name": "T02 XSP IC42", "underlying": "Unknown"},
            {"name": "T50 NDX BWIC7", "underlying": "NDX"},
        ]
    }

    api._normalize_snapshot_underlyings(snap)

    assert [trade["underlying"] for trade in snap["trades"]] == ["XLE", "XSP", "NDX"]
