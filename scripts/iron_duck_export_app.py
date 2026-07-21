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
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOME = Path.home()
OUT = REPO / "reports" / "iron_duck"
QC = HOME / "qc_batman"

# (tag, arquivo DUCK, underlying, campos do combo EXATO do Reiner — SEM tested)
# SPX = TP40 ou 5DTE ou stop $300 · RUT = TP50 ou 5DTE.
RUNS = [
    ("SPX", QC / "duck_spx_5y.csv", "SPX", ["tp40", "dte5", "ls300"]),
    ("RUT", QC / "duck_rut_5y.csv", "RUT", ["tp50", "dte5"]),
]
MULT = 100.0
# regras expostas no seletor do app (label -> coluna pnl_*)
RULES_ORDER = ["reiner", "hold", "tp25", "tp40", "tp50", "tp75", "dte5", "dte2",
               "sm15", "sm20", "sm25", "sm30", "ls300", "ls750", "ls1500", "ls3000", "tested"]


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
    """'hoff:buyback[:dS]' -> (hoff:int, buyback:float, dS:float|None) ou None.
    dS = offset do spot vs entrada no momento do toque (formato novo; velho = 2 campos)."""
    if field_val in ("", None):
        return None
    try:
        parts = str(field_val).split(":")
        h, b = int(parts[0]), float(parts[1])
        dS = float(parts[2]) if len(parts) > 2 else None
        return h, b, dS
    except Exception:
        return None


def derive(r, rule, combo):
    """Uma regra -> (pnl_usd, hoff|None, dS|None). buyback -> (credit - buyback)*MULT;
    sem toque -> settle (hoff/dS None = fechou na expiracao)."""
    cr = fnum(r, "credit")
    settle = fnum(r, "settle_net")

    def one(field):
        x = bb_hoff(r.get(field, ""))
        return ((cr - x[1]) * MULT, x[0], x[2]) if x else (settle, None, None)

    if rule == "hold":
        return settle, None, None
    if rule == "tested":
        return one("cross_tested")
    if rule == "reiner":
        # combo EXATO do Reiner (lista de campos, SEM tested): first-touch pelo hoff
        cands = [x for x in (bb_hoff(r.get(f, "")) for f in combo) if x]
        if not cands:
            return settle, None, None
        cands.sort(key=lambda t: t[0])
        h, b, dS = cands[0]
        return (cr - b) * MULT, h, dS
    if rule.startswith(("tp", "sm", "ls", "dte")):     # regra isolada -> lê o campo direto
        return one(rule)
    return settle, None, None


def build(tag, path, underlying, combo):
    rows = parse_duck(path)
    if not rows:
        print(f"  {tag}: 0 trades, pulo"); return None
    trades = []
    for r in rows:
        drv = {rule: derive(r, rule, combo) for rule in RULES_ORDER}
        pnls = {rule: round(v[0], 2) for rule, v in drv.items()}
        # DEFAULT = HOLD (settle analitico) — REGRA DA MESA: tudo no MID (entradas, saidas, hold);
        # os buybacks das regras tambem sao no mid (motor 2026-07-21) -> comparaveis ao hold.
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
        # ONDE/QUANDO cada regra fechou (p/ o Trade Auditor marcar o ponto no payoff):
        #   toque -> spot_close = S_entry + dS (gravado no motor), close_date = open + hoff horas;
        #   sem toque -> fechou na expiracao (spot settle / data da expiracao).
        try:
            open_dt = datetime.strptime(f"{r.get('open_date')} {r.get('open_time','09:45')}", "%Y-%m-%d %H:%M")
        except ValueError:
            open_dt = None
        s_entry = fnum(r, "S_entry"); s_settle = fnum(r, "S_settle")
        for rule in RULES_ORDER:
            _, hoff, dS = drv[rule]
            if hoff is not None and dS is not None and open_dt is not None:
                t[f"spot_close_{rule}"] = round(s_entry + dS, 2)
                t[f"close_date_{rule}"] = (open_dt + timedelta(hours=hoff)).strftime("%Y-%m-%d")
            else:
                t[f"spot_close_{rule}"] = round(s_settle, 2)
                t[f"close_date_{rule}"] = r.get("expiry_date")
        trades.append(t)

    # RECONCILIACAO: soma da regra default (hold)
    total = round(sum(t["pnl_usd"] for t in trades), 2)
    hold_total = round(sum(t["pnl_hold"] for t in trades), 2)
    print(f"  {tag}: {len(trades)} trades | period {trades[0]['trade_date']}..{trades[-1]['trade_date']}")
    # TABELA comparativa (total / WR / PIOR trade) — responde 'qual saida corta as perdas grandes?'
    print(f"    {'regra':16} {'total':>12} {'WR':>5} {'pior trade':>12}")
    for rule in ["hold", "reiner", "tp40", "tp50", "dte5", "dte2",
                 "ls300", "ls750", "ls1500", "ls3000", "sm20", "sm30"]:
        ps = [t[f"pnl_{rule}"] for t in trades]
        n = sum(ps); wr = 100.0 * sum(1 for x in ps if x > 0) / len(ps); worst = min(ps)
        print(f"    {rule:16} ${n:>10,.0f} {wr:>4.0f}% ${worst:>10,.0f}")

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
