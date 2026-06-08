"""
===============================================================================
 JADE LIZARD / RJL -> LIMPEZA DE ANOMALIAS DE DADO (pente fino p/ o CZ)
===============================================================================
 Motivo: o trade 28/11/2025 (meio-pregao pos-Thanksgiving) apareceu com
 credit ~$3.840 (7x o normal) e lucro fake $3.340, sem strikes e sem payoff.
 Causa-raiz: cadeia de opcoes 0DTE rala/stale em meio-pregoes e OPEX de baixa
 liquidez -> o motor montou estrutura impossivel (retained_dist ~1000 pts vs
 normal ~31; p95=79). NAO e bug do motor, e dado podre da sessao.

 Filtro de integridade (objetivo, por LINHA, reproduzivel) -- dropa a sessao se:
   (a) strikes ausentes (recon do closedTrades nao casou)  -> payoff nao renderiza
   (b) credit > 1.8x a mediana da celula                   -> credito inflado
   (c) retained_dist > 400 pts (normal ~31, p95 79)         -> estrutura impossivel

 Acao: reescreve trades.csv/daily.csv de cada celula SEM as sessoes ruins,
 grava reports/jadelizard_backtest/_anomalies_audit.md (trilha p/ o CZ) e
 imprime net antes/depois. <1% das sessoes; nao muda as conclusoes (RJL segue
 negativo, JL n5 segue positivo) e remove o lucro fake.

 Uso:  python scripts/jl_clean_anomalies.py          (aplica)
       python scripts/jl_clean_anomalies.py --dry    (so audita, nao escreve)
===============================================================================
"""
from __future__ import annotations
import csv, os, sys, statistics as st
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BASE = REPO / "reports" / "jadelizard_backtest"
AUDIT = BASE / "_anomalies_audit.md"
CREDIT_MULT = 1.8
RETAINED_MAX = 400.0


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def bad_reasons(r, med_credit):
    """Retorna lista de motivos pelos quais a sessao e' invalida (vazia = ok)."""
    out = []
    if not r["short_put"] or not r["short_call"]:
        out.append("sem-strikes")
    cr = fnum(r["total_credit"])
    if cr is not None and med_credit and cr > med_credit * CREDIT_MULT:
        out.append(f"credit-outlier({cr:.0f}>1.8x{med_credit:.0f})")
    rd = fnum(r["retained_dist"])
    if rd is not None and rd > RETAINED_MAX:
        out.append(f"retained_dist({rd:.0f})")
    return out


def main():
    dry = "--dry" in sys.argv
    cells = sorted(d.name for d in BASE.iterdir() if d.is_dir() and not d.name.startswith("_"))
    audit = ["# Auditoria de Integridade — Jade Lizard / Reverse Jade Lizard",
             "",
             f"Filtro: strikes ausentes **OU** credit > {CREDIT_MULT}x mediana da celula "
             f"**OU** retained_dist > {RETAINED_MAX:.0f} pts (normal ~31, p95 79).",
             "",
             "| Célula | Trades | Removidos | Net ANTES | Net DEPOIS | Δ (lucro fake removido) |",
             "|---|---|---|---|---|---|"]
    detail = ["", "## Sessões removidas (detalhe)", ""]
    for c in cells:
        d = BASE / c
        rows = list(csv.DictReader(open(d / "trades.csv")))
        creds = [fnum(r["total_credit"]) for r in rows if fnum(r["total_credit"])]
        med = st.median(creds) if creds else 0.0
        keep, drop = [], []
        for r in rows:
            reasons = bad_reasons(r, med)
            (drop if reasons else keep).append((r, reasons))
        net_before = sum(fnum(r["pnl_usd"]) or 0 for r, _ in [(x, None) for x in rows])
        net_after = sum(fnum(r["pnl_usd"]) or 0 for r, _ in keep)
        delta = net_before - net_after
        audit.append(f"| {c} | {len(rows)} | {len(drop)} | "
                     f"${net_before:,.0f} | ${net_after:,.0f} | ${delta:,.0f} |")
        if drop:
            detail.append(f"### {c}")
            for r, reasons in drop:
                detail.append(f"- `{r['trade_date']}` — pnl ${fnum(r['pnl_usd']):,.0f}, "
                              f"credit ${fnum(r['total_credit']):,.0f} — {', '.join(reasons)}")
            detail.append("")
        # reescreve sem as sessoes ruins
        drop_dates = {r["trade_date"] for r, _ in drop}
        if not dry and drop:
            kept_rows = [r for r, _ in keep]
            with open(d / "trades.csv", "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader(); w.writerows(kept_rows)
            daily = list(csv.DictReader(open(d / "daily.csv")))
            daily = [dr for dr in daily if dr["trade_date"] not in drop_dates]
            with open(d / "daily.csv", "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(daily[0].keys()))
                w.writeheader(); w.writerows(daily)
        print(f"[{c}] {len(rows)}->{len(keep)} trades | drop {len(drop)} | "
              f"net ${net_before:,.0f}->${net_after:,.0f} (d {delta:+,.0f})"
              + (" [DRY]" if dry else ""))
    if not dry:
        AUDIT.write_text("\n".join(audit + detail), encoding="utf-8")
        print(f"\nAudit -> {AUDIT}")


if __name__ == "__main__":
    main()
