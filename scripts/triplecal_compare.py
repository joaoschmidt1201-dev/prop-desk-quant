"""
Consolida resultados de todas as configs em data/backtest_triplecalendar/raw/
e gera tabela comparativa em reports/triplecal_backtest/_compare.md + .csv

USO:  python scripts/triplecal_compare.py
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("compare")

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "reports" / "triplecal_backtest"


def main() -> None:
    rows = []
    for cfg_dir in sorted(OUT.iterdir()):
        if not cfg_dir.is_dir() or cfg_dir.name.startswith("_"):
            continue
        metrics_path = cfg_dir / "tp_grid_metrics.csv"
        if not metrics_path.exists():
            continue
        m = pd.read_csv(metrics_path)
        m.insert(0, "config", cfg_dir.name)
        rows.append(m)

    if not rows:
        log.warning("Nenhum tp_grid_metrics.csv encontrado em %s", OUT)
        return

    full = pd.concat(rows, ignore_index=True)
    out_csv = OUT / "_compare_all.csv"
    full.to_csv(out_csv, index=False)
    log.info("Tabela consolidada -> %s (%d linhas)", out_csv, len(full))

    # Best por config (TP=none) — comparativo limpo
    best = full[full["tp"] == "TP=none"].sort_values("sharpe", ascending=False)
    md = ["# Triple Calendar — Comparativo entre configs (TP=none)", ""]
    md.append(best[["config", "trades", "win_rate", "avg_pnl", "total_pnl",
                    "sharpe", "profit_factor", "max_dd_pct", "cagr_pct",
                    "final_equity"]].to_string(index=False))
    md.append("")
    md.append("# Detalhe — grid TP por config")
    md.append("")
    for cfg in full["config"].unique():
        md.append(f"## {cfg}")
        sub = full[full["config"] == cfg].drop(columns=["config"])
        md.append(sub.to_string(index=False))
        md.append("")

    (OUT / "_compare.md").write_text("\n".join(md), encoding="utf-8")
    log.info("Resumo -> %s", OUT / "_compare.md")
    print("\n" + "=" * 90)
    print("RANKING (TP=none) por Sharpe:")
    print("=" * 90)
    print(best[["config", "trades", "win_rate", "avg_pnl", "sharpe",
                "max_dd_pct", "cagr_pct"]].to_string(index=False))


if __name__ == "__main__":
    main()
