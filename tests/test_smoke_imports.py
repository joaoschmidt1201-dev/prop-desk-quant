"""Smoke tests — garantem que os scripts criticos importam sem erro.

Se estes quebram, algo fundamental no repo foi movido de lugar sem atualizacao
dos paths. Sao a primeira linha de defesa contra regressoes de reorg.
"""

from __future__ import annotations

import importlib
import sys

import pytest

# Scripts que devem sempre ser importaveis sem side effects pesados
CRITICAL_MODULES = [
    "gex_csv_parser",
    "gex_input",
    "gex_compare",
    "morning_briefing",
]


@pytest.mark.parametrize("module_name", CRITICAL_MODULES)
def test_critical_modules_import(module_name: str):
    """Importar modulo nao pode levantar. `pythonpath=scripts` cuida do resolve."""
    if module_name in sys.modules:
        del sys.modules[module_name]
    importlib.import_module(module_name)


def test_morning_briefing_paths_resolve(project_root):
    """morning_briefing deve apontar para state/gex/ (nao raiz legacy)."""
    import morning_briefing as mb

    assert str(mb.HISTORY_FILE).endswith("state\\gex\\gex_history.json") or \
           str(mb.HISTORY_FILE).endswith("state/gex/gex_history.json")
    assert "state" in str(mb.HISTORY_SPX)
    assert "state" in str(mb.HISTORY_NDX)


def test_gex_csv_parser_ticker_config(project_root):
    """TICKER_CONFIG do parser deve usar state/gex/ para history files."""
    import gex_csv_parser as gcp

    for ticker, cfg in gcp.TICKER_CONFIG.items():
        history = str(cfg["history_file"])
        assert "state" in history and "gex" in history, \
            f"{ticker} history aponta fora de state/gex: {history}"
