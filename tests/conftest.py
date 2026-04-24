"""Pytest configuration e fixtures globais do desk.

pythonpath=scripts ja esta em pyproject.toml, entao `import morning_briefing`
funciona direto dos tests.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def project_root() -> Path:
    """Absolute path para a raiz do projeto."""
    return ROOT


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    """Pasta de fixtures dos tests (CSVs pequenos, JSONs esperados, etc)."""
    return FIXTURES


@pytest.fixture
def sample_gex_history_spy() -> list[dict]:
    """Snapshot real de uma semana SPY — usado para smoke tests de GEX."""
    return [
        {
            "week": "2026-04-20",
            "ticker": "SPY",
            "expiry": "2026-04-24",
            "gflip": 699,
            "pos": [710, 715, 720],
            "neg": [700, 702, 695],
            "coi": [710, 705],
            "poi": [700, 702],
            "agg": 700,
            "pos_zone": 700,
            "neg_zone": 698,
            "conf": [698, 699, 700, 702, 710],
            "source_file": "SPY-gamma-levels-exp-20260424-weekly.csv",
        }
    ]


@pytest.fixture
def tmp_state_gex(tmp_path: Path) -> Path:
    """Diretorio isolado simulando state/gex/ para testes que escrevem state."""
    state_gex = tmp_path / "state" / "gex"
    state_gex.mkdir(parents=True)
    return state_gex


@pytest.fixture
def sample_gex_history_file(tmp_state_gex: Path, sample_gex_history_spy: list[dict]) -> Path:
    """gex_history_spy.json pronto num tmp dir, para passar a funcoes que leem state."""
    f = tmp_state_gex / "gex_history_spy.json"
    f.write_text(json.dumps(sample_gex_history_spy), encoding="utf-8")
    return f
