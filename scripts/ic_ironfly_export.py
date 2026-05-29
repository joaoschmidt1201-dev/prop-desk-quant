"""
===============================================================================
 IC 0DTE + IRON FLY 0DTE EXPORT — closedTrades -> trades.csv (schema ic7 do app)
===============================================================================
 Recon LIMPO (mesma filosofia do Batman: payoff num único preço de settle, imune
 ao artefato split-settle do QC). Identifica pernas SP/LP/SC/LC pelo direction
 (0=long, 1=short). Crédito = -debit (pra IC/IronFly o "debit" calculado é negativo
 porque a posição é de CRÉDITO).

 Saída:
   reports/ic0dte_backtest/<tag>/trades.csv  +  daily.csv
   reports/ironfly_backtest/<tag>/trades.csv +  daily.csv

 Usa o kind="ic7" do app (já existe viewer, com payoff/strikes/breakdowns).
===============================================================================
"""
from __future__ import annotations
import json, csv, sys, os, datetime as dt
from pathlib import Path
from collections import defaultdict

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import batman_export_app as bx   # api, load_vix, load_spx, parse_symbol, vix_at, spx_at, _money

HOME = Path.home()
SWEEP = HOME / "qc_batman" / "sweep_results.json"
PID = bx.PID
OUT_IC = REPO / "reports" / "ic0dte_backtest"
OUT_IF = REPO / "reports" / "ironfly_backtest"

# Grupos: base tag (a pasta) + variantes que viram COLUNAS (igual TP do Batman).
GROUPS = {
    "IC0DTE":  {"out": "ic0dte_backtest",  "merge": {"pnl_stop_2x": "IC0DTE_stop"}},
    "IF0DTE":  {"out": "ironfly_backtest", "merge": {"pnl_tp10": "IF0DTE_tp10",
                                                       "pnl_tp20": "IF0DTE_tp20",
                                                       "pnl_tp30": "IF0DTE_tp30"}},
}

def extract_legs(legs):
    """SP/LP/SC/LC pelo direction (0=long, 1=short)."""
    sp = lp = sc = lc = None
    for l in legs:
        _, right, K = bx.parse_symbol(l["symbols"][0]["value"])
        d = l["direction"]
        if   right == "P" and d == 1: sp = K
        elif right == "P" and d == 0: lp = K
        elif right == "C" and d == 1: sc = K
        elif right == "C" and d == 0: lc = K
    return lp, sp, sc, lc

def recon_trades(bid):
    bt = bx.api("/backtests/read", {"projectId": PID, "backtestId": bid})["backtest"]
    ct = (bt.get("totalPerformance") or {}).get("closedTrades") or []
    if not ct: return []
    vdf = bx.load_vix(); sdf = bx.load_spx()
    groups = defaultdict(list)
    for t in ct: groups[t["entryTime"]].append(t)
    trades = []
    for et, legs in sorted(groups.items()):
        entry = dt.datetime.fromisoformat(et.replace("Z", "+00:00"))
        tdate = entry.date()
        exp = max(bx.parse_symbol(l["symbols"][0]["value"])[0] for l in legs)
        S_exp = bx.spx_at(exp, sdf)
        if S_exp is None: continue
        debit_usd = 0.0; pnl_usd = 0.0
        for l in legs:
            _, right, K = bx.parse_symbol(l["symbols"][0]["value"])
            n = (1 if l["direction"] == 0 else -1) * abs(l["quantity"]) * 100
            debit_usd += n * l["entryPrice"]
            if (l.get("exitPrice") or 0) > 0:
                pnl_usd += l.get("profitLoss") or 0     # round-trip exato (early close)
            else:
                intr = max(0.0, S_exp - K) if right == "C" else max(0.0, K - S_exp)
                pnl_usd += n * (intr - l["entryPrice"])
        lp, sp, sc, lc = extract_legs(legs)
        credit_usd = -debit_usd                          # IC/IronFly: posição CRÉDITO
        trades.append({
            "trade_date": tdate, "exp_date": exp, "dte": max((exp-tdate).days, 0),
            "credit": round(credit_usd, 2), "pnl": round(pnl_usd, 2),
            "vix": bx.vix_at(tdate, vdf), "spot_exit": round(S_exp, 2),
            "long_put": lp, "short_put": sp, "short_call": sc, "long_call": lc,
        })
    return trades

def export_group(base_tag, group, sw_res):
    base_bid = sw_res.get(base_tag, {}).get("backtestId")
    if not base_bid:
        print(f"[{base_tag}] sem bid base — pula"); return 0
    trades = recon_trades(base_bid)
    if not trades:
        print(f"[{base_tag}] sem closedTrades"); return 0
    # variantes (close-rule) viram colunas, casadas por trade_date
    merge_cols = {}
    for col, vtag in group["merge"].items():
        vbid = sw_res.get(vtag, {}).get("backtestId")
        if not vbid:
            print(f"  [{base_tag}] variante {vtag} sem bid ainda — coluna {col} vazia"); continue
        try:
            vtrades = recon_trades(vbid)
            merge_cols[col] = {t["trade_date"]: t["pnl"] for t in vtrades}
        except Exception as e:
            print(f"  [{base_tag}] recon {vtag} falhou: {e}")

    rows = []
    for t in trades:
        row = {
            "trade_date": t["trade_date"].isoformat(), "exp_date": t["exp_date"].isoformat(),
            "underlying": "SPX", "dte_entry": t["dte"], "total_credit": t["credit"],
            "pnl_usd": t["pnl"], "pnl_usd_at_exp": t["pnl"],
            "vix_entry": t["vix"], "spot_exit": t["spot_exit"],
            "long_put": t["long_put"], "short_put": t["short_put"],
            "short_call": t["short_call"], "long_call": t["long_call"],
            "result": "WIN" if t["pnl"] > 0 else "LOSS",
            "exit_method": "expiration", "effective_close_date": t["exp_date"].isoformat(),
            "effective_dit_at_close": t["dte"], "in_range": t["pnl"] > 0,
            "max_risk_usd": None,
        }
        for col, mp in merge_cols.items():
            row[col] = round(mp.get(t["trade_date"], t["pnl"]), 2)   # sem fechamento -> hold
        rows.append(row)

    daily = []
    for t in trades:
        daily.append({"trade_date": t["trade_date"].isoformat(), "calendar_date": t["trade_date"].isoformat(),
                      "dte_remaining": t["dte"], "pnl_usd": 0.0})
        daily.append({"trade_date": t["trade_date"].isoformat(), "calendar_date": t["exp_date"].isoformat(),
                      "dte_remaining": 0, "pnl_usd": t["pnl"]})

    d = REPO / "reports" / group["out"] / base_tag
    d.mkdir(parents=True, exist_ok=True)
    with open(d/"trades.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    with open(d/"daily.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(daily[0].keys())); w.writeheader(); w.writerows(daily)
    net = sum(r["pnl_usd"] for r in rows)
    wr = 100.0 * sum(1 for r in rows if r["pnl_usd"] > 0) / len(rows)
    rt = sw_res.get(base_tag, {}).get("runtime") or {}
    m0_raw = rt.get("NET hold") or rt.get("NET M0 hold")
    m0 = bx._money((m0_raw or "").split("/")[0]) if m0_raw else None
    chk = f" | M0 motor ${m0:,.0f} | dif ${net-m0:+,.0f}" if m0 is not None else ""
    extra = (" | cols TP: " + ",".join(merge_cols)) if merge_cols else ""
    print(f"[{base_tag}] {len(rows)} trades | net LIMPO ${net:,.0f} | WR {wr:.0f}%{chk}{extra} -> {d}")
    return len(rows)

def main():
    sw_res = json.loads(SWEEP.read_text(encoding="utf-8"))
    for base_tag, group in GROUPS.items():
        try: export_group(base_tag, group, sw_res)
        except Exception as e: print(f"[{base_tag}] FALHOU: {e}")

if __name__ == "__main__":
    main()
