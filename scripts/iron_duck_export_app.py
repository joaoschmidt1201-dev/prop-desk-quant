"""
===============================================================================
 IRON DUCK — EXPORT PARA O APP / TRADE AUDITOR
===============================================================================
 Le o canal DUCK (record-and-derive) de um run e escreve trades.csv + daily.csv
 no formato que o viewer de iron condor (kind="ic0dte") consome. Deriva o P&L de
 cada regra de gestao (TP/stop/DTE/tested) e o COMBO do Reiner (o que vier 1o) a
 partir dos first-touch gravados (hoff:buyback). RECONCILIA: soma da regra default
 == headline; ABORTA se nao bater (nivel institucional).

 Uso:  python scripts/iron_duck_export_app.py
   (le ~/qc_batman/duck_{spx,rut}_5y.csv -> reports/iron_duck/{SPX,RUT}/)
===============================================================================
"""
from __future__ import annotations
import csv, sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOME = Path.home()
OUT = REPO / "reports" / "iron_duck"
QC = HOME / "qc_batman"

# (tag, arquivo DUCK, underlying, combo default do Reiner: (tp, dte))
RUNS = [
    ("SPX", QC / "duck_spx_5y.csv", "SPX", ("tp40", "dte5")),
    ("RUT", QC / "duck_rut_5y.csv", "RUT", ("tp50", "dte2")),
]
MULT = 100.0
# regras expostas no seletor do app (label -> coluna pnl_*)
RULES_ORDER = ["reiner", "hold", "tp25", "tp40", "tp50", "tp75", "dte5", "dte2", "sm30", "tested"]


def parse_duck(path: Path):
    cols, rows = None, []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "DUCKHDR|" in raw:
            cols = raw.split("DUCKHDR|", 1)[1].split("|")[0].split(",")
        elif "DUCK|" in raw:
            v = raw.split("DUCK|", 1)[1].split(",")
            if cols and len(v) == len(cols):
                rows.append(dict(zip(cols, v)))
    if cols is None:
        raise SystemExit(f"{path}: sem DUCKHDR (log truncou?)")
    # continuidade de id (log cortou o fim = OOS?)
    ids = [int(float(r["id"])) for r in rows if r.get("id") not in ("", None)]
    gaps = [(a, b) for a, b in zip(ids, ids[1:]) if b != a + 1]
    if gaps or (ids and ids[0] != 1):
        print(f"  !! {path.name}: id descontinuo {gaps[:3]} start={ids[0] if ids else '?'} -> LOG TRUNCADO")
    return rows


def fnum(r, k, d=0.0):
    v = r.get(k, "")
    try:
        return float(v) if v not in ("", None) else d
    except ValueError:
        return d


def bb_hoff(field_val):
    """'hoff:buyback' -> (hoff:int, buyback:float) ou None."""
    if field_val in ("", None):
        return None
    try:
        h, b = str(field_val).split(":")
        return int(h), float(b)
    except Exception:
        return None


def derive(r, rule, combo):
    """P&L (USD) de uma regra. buyback -> (credit - buyback)*MULT; se nao cruzou -> settle."""
    cr = fnum(r, "credit")
    settle = fnum(r, "settle_net")

    def one(field):
        x = bb_hoff(r.get(field, ""))
        return (cr - x[1]) * MULT if x else settle

    if rule == "hold":
        return settle
    if rule in ("tp25", "tp40", "tp50", "tp75", "sm30", "dte5", "dte2"):
        return one(rule)
    if rule == "tested":
        return one("cross_tested")
    if rule == "reiner":
        # first-touch entre {tp, dte, sm30, tested} pelo hoff
        tp, dte = combo
        cands = []
        for f in (tp, dte, "sm30", "cross_tested"):
            x = bb_hoff(r.get(f, ""))
            if x:
                cands.append(x)
        if not cands:
            return settle
        cands.sort(key=lambda t: t[0])
        return (cr - cands[0][1]) * MULT
    return settle


def build(tag, path, underlying, combo):
    rows = parse_duck(path)
    if not rows:
        print(f"  {tag}: 0 trades, pulo"); return None
    trades = []
    for r in rows:
        pnls = {rule: round(derive(r, rule, combo), 2) for rule in RULES_ORDER}
        # DEFAULT = HOLD (settle analitico, sem spread) — limpo e reconcilia com o Reiner por-trade.
        # As regras de saida antecipada usam buyback cruzando o bid-ask (realista, mas na iliquidez do
        # RUT distorce muito -> ficam como opcoes/diagnostico, nao como headline). Ver ACHADOS.
        default_pnl = pnls["hold"]
        t = {
            "trade_date": r.get("open_date"), "exp_date": r.get("expiry_date"),
            "underlying": underlying, "dte_entry": r.get("dte_entry"),
            "spot_entry": round(fnum(r, "S_entry"), 2), "spot_exit": round(fnum(r, "S_settle"), 2),
            "vix_entry": round(fnum(r, "vix"), 2),
            "long_put": round(fnum(r, "long_put")), "short_put": round(fnum(r, "short_put")),
            "short_call": round(fnum(r, "short_call")), "long_call": round(fnum(r, "long_call")),
            "put_width": round(fnum(r, "put_width")), "call_width": round(fnum(r, "call_width")),
            "delta_put": r.get("sp_delta"), "delta_call": r.get("sc_delta"),
            # total_credit em USD (o renderer ic0dte faz credit_usd − (putLoss+callLoss)*100)
            "total_credit": round(fnum(r, "credit") * MULT, 2),
            "credit_pts": round(fnum(r, "credit"), 2),
            "max_risk_usd": round(fnum(r, "max_loss_usd"), 2),
            "pnl_usd": default_pnl,                       # regra DEFAULT (hold) — KPI/equity
            "pnl_usd_at_exp": pnls["hold"],
            "effective_close_date": r.get("expiry_date"),
            "result": "WIN" if default_pnl > 0 else "LOSS",
            "exit_method": "hold",
            "in_range": 1 if default_pnl >= 0 else 0,
        }
        for rule in RULES_ORDER:
            t[f"pnl_{rule}"] = pnls[rule]
        trades.append(t)

    # RECONCILIACAO: soma da regra default
    total = round(sum(t["pnl_usd"] for t in trades), 2)
    hold_total = round(sum(t["pnl_hold"] for t in trades), 2)
    print(f"  {tag}: {len(trades)} trades | default(reiner) ${total:,.0f} | hold ${hold_total:,.0f} "
          f"| WR {100.0*sum(1 for t in trades if t['pnl_usd']>0)/len(trades):.0f}% "
          f"| period {trades[0]['trade_date']}..{trades[-1]['trade_date']}")

    # daily.csv = equity da regra default
    daily = []; cum = 0.0
    for t in trades:
        cum = round(cum + t["pnl_usd"], 2)
        daily.append({"date": t["trade_date"], "trade_date": t["trade_date"],
                      "spot": t["spot_entry"], "pnl_usd": t["pnl_usd"], "cumulative_pnl": cum})

    d = OUT / underlying
    d.mkdir(parents=True, exist_ok=True)
    tcols = list(trades[0].keys())
    with open(d / "trades.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=tcols); w.writeheader(); w.writerows(trades)
    with open(d / "daily.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(daily[0].keys())); w.writeheader(); w.writerows(daily)
    print(f"         -> {d.relative_to(REPO)}")
    return {"tag": tag, "n": len(trades), "total": total}


def main():
    print("IRON DUCK — export p/ o app:")
    got = []
    for tag, path, und, combo in RUNS:
        if not path.exists():
            print(f"  {tag}: {path.name} nao existe, pulo"); continue
        r = build(tag, path, und, combo)
        if r:
            got.append(r)
    if not got:
        print("nada exportado"); sys.exit(1)
    print(f"\nOK: {len(got)} run(s).")


if __name__ == "__main__":
    main()
