"""Testes de estrutura do state GEX — schema e parsing das fixtures."""

from __future__ import annotations

import json


def test_gex_history_schema(sample_gex_history_spy):
    """Schema minimo de uma entrada de gex_history_*.json."""
    entry = sample_gex_history_spy[0]
    required = {"week", "ticker", "expiry", "gflip", "pos", "neg", "conf"}
    assert required.issubset(entry.keys())

    # gflip e inteiro, pos/neg sao listas com 3 elementos
    assert isinstance(entry["gflip"], int)
    assert isinstance(entry["pos"], list) and len(entry["pos"]) == 3
    assert isinstance(entry["neg"], list) and len(entry["neg"]) == 3


def test_gex_history_file_persistable(sample_gex_history_file):
    """Fixture deve gravar JSON valido que carrega de volta identico."""
    loaded = json.loads(sample_gex_history_file.read_text(encoding="utf-8"))
    assert isinstance(loaded, list)
    assert loaded[0]["ticker"] == "SPY"
    assert loaded[0]["week"] == "2026-04-20"


def test_real_state_gex_files_parse(project_root):
    """Arquivos reais em state/gex/ devem ser JSON valido."""
    gex_dir = project_root / "state" / "gex"
    if not gex_dir.exists():
        # Em CI fresh clone pode nao existir — nao e regressao
        return

    for f in gex_dir.glob("gex_history_*.json"):
        data = json.loads(f.read_text(encoding="utf-8"))
        assert isinstance(data, list), f"{f.name} deve ser lista"
        for entry in data:
            assert "ticker" in entry, f"entry sem ticker em {f.name}"
            assert "week" in entry, f"entry sem week em {f.name}"
