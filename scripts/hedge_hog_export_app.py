"""
===============================================================================
 HEDGE HOG — EXPORT PARA O APP / TRADE AUDITOR
===============================================================================
 Le o canal HHOG (posicao continua rolada: 1 linha por EVENTO entrada/roll/reopen).
 Atribuicao FORWARD do P&L (como no Layer B): pnl_usd de cada linha = variacao do
 pnl_total ate o evento seguinte -> soma == headline TRAVADO. Escreve trades.csv +
 daily.csv em reports/hedge_hog/SPX/.

 Uso: python scripts/hedge_hog_export_app.py
===============================================================================
"""
from __future__ import annotations
import csv, sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOME = Path.home()
OUT = REPO / "reports" / "hedge_hog"
QC = HOME / "qc_batman"
RUNS = [("SPX", QC / "hhog_spx_5y.csv")]
MULT = 100.0


def parse_hhog(path: Path):
    cols, rows = None, []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "HHOGHDR|" in raw:
            cols = raw.split("HHOGHDR|", 1)[1].split("|")[0].split(",")
        elif "HHOG|" in raw:
            v = raw.split("HHOG|", 1)[1].split(",")
            if cols and len(v) == len(cols):
                rows.append(dict(zip(cols, v)))
    if cols is None:
        raise SystemExit(f"{path}: sem HHOGHDR")
    return rows


def fnum(r, k, d=0.0):
    v = r.get(k, "")
    try:
        return float(v) if v not in ("", None) else d
    except ValueError:
        return d


def build(tag, path):
    rows = parse_hhog(path)
    if not rows:
        print(f"  {tag}: 0 eventos"); return None
    pnl_tot = [fnum(r, "pnl_total") for r in rows]
    n = len(rows)
    trades = []
    for i, r in enumerate(rows):
        is_open = (i == n - 1)
        # forward: P&L do periodo ate o evento seguinte. Na 1a linha o "antes" e 0 (pre-entrada), o que
        # ABSORVE o custo de entrada (pnl_total[0] != 0, ao contrario do Layer B) -> soma == headline.
        d_pnl = 0.0 if is_open else (pnl_tot[i + 1] - (0.0 if i == 0 else pnl_tot[i]))
        pnl_usd = round(d_pnl * MULT, 2)
        nxt = rows[i + 1] if not is_open else None
        # colunas COMPATIVEIS com o viewer layerb (reusa o kind, zero mudanca de frontend). Mapa:
        # roll_dir=evento, short/long_put=pernas do LPV, delta_short/long=deltas do LPV, total_credit=
        # net_credit, net_roll_usd=P&L do evento. Colunas extras (far_*) so ficam no CSV p/ auditoria.
        trades.append({
            "trade_date": r.get("date"), "exp_date": r.get("lpv_exp"),
            "underlying": tag, "spot_entry": round(fnum(r, "S"), 2), "vix_entry": round(fnum(r, "vix"), 2),
            "roll_dir": r.get("event"), "restruck": "",
            "short_put": r.get("lpv_short"), "long_put": r.get("lpv_long"),
            "delta_short": r.get("d_lpv_sh"), "delta_long": r.get("d_lpv_lg"),
            "lpv_debit": r.get("lpv_debit"),
            "far_short": r.get("far_short"), "far_exp": r.get("far_exp"), "far_credit": r.get("far_credit"),
            "delta_far": r.get("d_far"), "total_credit": r.get("net_credit"),
            "net_roll": round(pnl_usd / MULT, 2), "net_roll_usd": pnl_usd,
            "spot_close": round(fnum(nxt, "S"), 2) if nxt else None,
            "spot_exit": round(fnum(nxt, "S"), 2) if nxt else None,
            "effective_close_date": nxt.get("date") if nxt else None,
            "cash_close": round(fnum(r, "cum_cash"), 2), "mark": round(fnum(r, "mark"), 2),
            "cum_pnl_pts": round(pnl_tot[i + 1], 2) if not is_open else round(pnl_tot[i], 2),
            "pnl_usd": pnl_usd, "pnl_usd_at_exp": pnl_usd,
            "result": "open" if is_open else ("win" if pnl_usd > 0 else ("loss" if pnl_usd < 0 else "flat")),
            "exit_method": "open" if is_open else "roll",
            "in_range": 1 if pnl_usd >= 0 else 0,
        })
    total = round(sum(t["pnl_usd"] for t in trades), 2)
    headline = round(fnum(rows[-1], "pnl_total") * MULT, 2)
    if abs(total - headline) > 1.0:
        raise SystemExit(f"  {tag}: RECONCILIACAO FALHOU soma={total} vs headline={headline}")
    print(f"  {tag}: {len(trades)} eventos | headline ${headline:,.0f} | soma ${total:,.0f} RECONCILIA "
          f"| period {trades[0]['trade_date']}..{trades[-1]['trade_date']}")

    daily = []; cum = 0.0
    for t in trades:
        cum = round(cum + t["pnl_usd"], 2)
        daily.append({"date": t["trade_date"], "trade_date": t["trade_date"],
                      "spot": t["spot_entry"], "pnl_usd": t["pnl_usd"], "cumulative_pnl": cum})
    d = OUT / tag; d.mkdir(parents=True, exist_ok=True)
    with open(d / "trades.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(trades[0].keys())); w.writeheader(); w.writerows(trades)
    with open(d / "daily.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(daily[0].keys())); w.writeheader(); w.writerows(daily)
    print(f"         -> {d.relative_to(REPO)}")
    return {"tag": tag, "n": len(trades), "total": total}


def main():
    print("HEDGE HOG — export p/ o app:")
    got = []
    for tag, path in RUNS:
        if not path.exists():
            print(f"  {tag}: {path.name} nao existe, pulo"); continue
        r = build(tag, path)
        if r:
            got.append(r)
    if not got:
        print("nada exportado"); sys.exit(1)
    print(f"\nOK: {len(got)} run(s).")


if __name__ == "__main__":
    main()
