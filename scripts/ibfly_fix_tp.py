"""
IBFLY FIX TP — corrige anomalia dos TP (MTM fantasma de quote horário).
O motor gravava no TP o MTM no cruzamento (lido de quote horário stale em opções near-expiry),
gerando 'ganhos' acima do crédito (ganho máx terminal da IB = crédito) = não-executáveis.
CORREÇÃO: uma ordem-limite de TP a l% do crédito executa NO ALVO -> pnl_tp{l} = l% × crédito
se o TP foi atingido (valor != hold); senão mantém o hold. Patcheia os trades.csv in-place.
Uso: python scripts/ibfly_fix_tp.py
"""
from __future__ import annotations
import csv, sys
from pathlib import Path
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
OUT = Path(__file__).resolve().parent.parent / "reports" / "ibfly_backtest_app"

def f(x):
    try: return float(x)
    except Exception: return None

def fix_file(d):
    fp = d / "trades.csv"
    rows = list(csv.DictReader(open(fp, encoding="utf-8")))
    if not rows: return None
    tp_cols = [c for c in rows[0] if c.startswith("pnl_tp") and "exit" not in c and "noon" not in c]
    comp_cols = [c for c in rows[0] if (("_exit" in c or "_noon" in c) and c.startswith("pnl_tp"))]
    before = {c: sum(f(r[c]) or 0 for r in rows) for c in tp_cols}
    anom = 0
    for r in rows:
        hold = f(r["pnl_usd"]) or 0.0; cred = f(r["total_credit"]) or 0.0
        for c in tp_cols:
            lvl = int(c.replace("pnl_tp", ""))          # 25/50/75
            v = f(r[c])
            if v is not None and abs(v - hold) > 0.01:    # TP foi atingido (gravou MTM != hold)
                tgt = round(lvl / 100.0 * cred, 2)        # alvo da ordem-limite (l% do crédito)
                if v > tgt + 0.01: anom += 1              # era pico fantasma acima do alvo
                r[c] = tgt
        # regra composta (TP+exit/noon): se o ramo do TP foi usado e excede o alvo, capa no alvo
        for c in comp_cols:
            lvl = int(c.split("_")[1].replace("tp", ""))
            v = f(r[c])
            if v is not None and v > lvl / 100.0 * cred + 0.01 and abs(v - hold) > 0.01:
                # só capa se o valor corresponde a um TP fantasma (acima do alvo). senão (saída) mantém.
                # heurística conservadora: capa no alvo do TP.
                r[c] = round(lvl / 100.0 * cred, 2)
    with open(fp, "w", newline="", encoding="utf-8") as fpw:
        w = csv.DictWriter(fpw, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    after = {c: sum(f(r[c]) or 0 for r in rows) for c in tp_cols}
    return tp_cols, before, after, anom, len(rows)

def main():
    folders = sorted([p for p in OUT.iterdir() if p.is_dir() and (p / "trades.csv").exists()])
    print(f"corrigindo TP fantasma em {len(folders)} configs IB...\n")
    tot_anom = 0
    for d in folders:
        res = fix_file(d)
        if not res: continue
        tp_cols, before, after, anom, n = res; tot_anom += anom
        chg = " | ".join(f"{c.replace('pnl_','')}: ${before[c]:,.0f}->${after[c]:,.0f}" for c in tp_cols)
        print(f"[{d.name:<12}] n={n} fantasmas={anom:>3} | {chg}")
    print(f"\n=== {tot_anom} TP fantasmas corrigidos (MTM stale -> alvo da ordem-limite) ===")

if __name__ == "__main__":
    main()
