"""
===============================================================================
 JADE LIZARD -> APP EXPORT (schema ic7, close-rules como colunas)
===============================================================================
 Posta as células JL (exceto 7DTE) no app, no MESMO padrão de IC 0DTE / Iron Fly
 0DTE: trades.csv + daily.csv por célula, lidos pelo registry de apps/api/main.py.

 P&L AUTORITATIVO (bate com o runtime do engine; o recon de closedTrades distorce o
 P&L do JL — short call quase-ATM expira ITM → split-settle, WR sai 51% vs 84% real):
   - Preferência: jl_closure_pertrade.csv (LOCAL, já reconstruído, sem hit de API) p/ as
     células que ele tem (w20n5/w30n5 0DTE + w20n5 1DTE).
   - Fallback: CTRADE| (log compacto, com retry p/ o rate-limit do free tier) p/ as demais.
 STRIKES reais lp/sp/sc/lc + spot_exit: closedTrades (/backtests/read — endpoint OK).

 Colunas de close-rule (GROSS, sem comissão, apples-to-apples c/ IC/IF no app):
   pnl_tp10/25/50/75 = captura lvl% do crédito se o TP foi tocado; senão = hold.
 A sensibilidade a custo (0.65 vs 1.50/perna) está no fechamento (jl_closure_report.md).

 Uso:  python scripts/jl_export_app.py
 Saída: reports/jadelizard_backtest/<TAG>/{trades.csv, daily.csv}
===============================================================================
"""
from __future__ import annotations
import json, csv, sys, time, os
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import ic_ironfly_export as IE        # recon_trades (closedTrades -> strikes reais + spot_exit)
import tasty_validation_analyze as T  # parse_trades, tp_hit (fallback CTRADE)

SWEEP_JL = REPO / "reports" / "zerodte_backtest" / "jl_research" / "sweep_jl.json"
PERTRADE = REPO / "reports" / "zerodte_backtest" / "jl_research" / "jl_closure_pertrade.csv"
OUT = REPO / "reports" / "jadelizard_backtest"
TP_LEVELS = [10, 25, 50, 75]
CELLS = ["jl_w20_n5_0dte", "jl_w20_n10_0dte", "jl_w30_n5_0dte", "jl_w30_n10_0dte", "jl_w20_n5_1dte"]


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def load_local():
    """jl_closure_pertrade.csv -> {cell: {date: rec normalizado}}."""
    if not PERTRADE.exists():
        return {}
    out = {}
    with open(PERTRADE, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            cr = _f(r["credit_mid_pts"])
            rec = {"credit_pts": cr, "hold_usd": round((_f(r["hold_pnl_pts"]) or 0) * 100.0, 2),
                   "s": _f(r["S_entry"]), "em": _f(r["em_pts"]), "vix": _f(r["vix"]),
                   "ret_dist": _f(r["retained_dist"]), "dte": int(_f(r["dte"]) or 0),
                   "tp": {lvl: r.get(f"tp{lvl}_hit") == "1" for lvl in TP_LEVELS}}
            out.setdefault(r["cell"], {})[r["date"]] = rec
    return out


def parse_ctrade_retry(bids, tries=None):
    """Endpoint de log do free tier dá rate-limit ('SEM HDR'). Retry com backoff.
       JL_TRIES no env aumenta o orçamento p/ esperar o cooldown (cap de espera = 300s)."""
    tries = tries or int(os.environ.get("JL_TRIES", "6"))
    rows, diag = [], []
    for i in range(tries):
        rows, diag = T.parse_trades(bids)
        if rows:
            return rows
        wait = min(300, 30 * (i + 1))
        print(f"    [retry {i+1}/{tries}] CTRADE vazio ({[d[2] for d in diag]}) — espera {wait}s", flush=True)
        time.sleep(wait)
    return rows


def ctrade_records(bids):
    recs = {}
    for r in parse_ctrade_retry(bids):
        recs[r.get("date")] = {"credit_pts": r.get("credit"),
                               "hold_usd": round((r.get("spnl") or 0) * 100.0, 2),
                               "s": r.get("s"), "em": r.get("em"), "vix": r.get("vix"),
                               "ret_dist": r.get("ret_dist"), "dte": int(r.get("dte") or 0),
                               "tp": {lvl: T.tp_hit(r, lvl) for lvl in TP_LEVELS}}
    return recs


def export_cell(tag, sw, local):
    bids = [sw[tag + s]["backtestId"] for s in ("__a", "__b")
            if sw.get(tag + s, {}).get("backtestId")]
    if not bids:
        print(f"[{tag}] sem bids — pula"); return 0

    # strikes reais (closedTrades) por data
    strikes = {}
    for bid in bids:
        for t in IE.recon_trades(bid):
            strikes.setdefault(t["trade_date"].isoformat(), t)

    # P&L autoritativo: local se houver, senão CTRADE
    src = "local" if tag in local else "ctrade"
    recs = local[tag] if src == "local" else ctrade_records(bids)
    if not recs:
        print(f"[{tag}] sem P&L (local ausente e CTRADE rate-limited) — pula"); return 0

    rows, miss_strikes = [], 0
    for tdate in sorted(recs):
        rec = recs[tdate]
        st = strikes.get(tdate)
        if not st:
            miss_strikes += 1
        cr_pts = rec["credit_pts"]
        credit_usd = round((cr_pts or 0) * 100.0, 2)
        gross_hold = rec["hold_usd"]
        sp, lp = (st["short_put"], st["long_put"]) if st else (None, None)
        sc, lc = (st["short_call"], st["long_call"]) if st else (None, None)
        put_w = (sp - lp) if (sp and lp) else None
        call_w = (lc - sc) if (lc and sc) else None
        wide_w = max([w for w in (put_w, call_w) if w], default=None)
        max_risk = round(wide_w * 100.0 - credit_usd, 2) if wide_w else None
        exp_iso = st["exp_date"].isoformat() if st else tdate
        row = {
            "trade_date": tdate, "exp_date": exp_iso, "underlying": "SPX",
            "dte_entry": rec["dte"], "structure": "JL",
            "spot_entry": rec["s"], "expected_move": rec["em"],
            "short_put": sp, "long_put": lp, "short_call": sc, "long_call": lc,
            "put_width": put_w, "call_width": call_w, "retained_dist": rec["ret_dist"],
            "total_credit": credit_usd, "spot_exit": (st["spot_exit"] if st else None),
            "vix_entry": rec["vix"], "pnl_usd": gross_hold, "pnl_usd_at_exp": gross_hold,
            "result": "WIN" if gross_hold > 0 else "LOSS", "exit_method": "expiration",
            "effective_close_date": exp_iso, "effective_dit_at_close": rec["dte"],
            "in_range": None, "max_risk_usd": max_risk,
        }
        for lvl in TP_LEVELS:
            row[f"pnl_tp{lvl}"] = round(cr_pts * lvl, 2) if (rec["tp"][lvl] and cr_pts) else gross_hold
        rows.append(row)

    daily = []
    for r in rows:
        daily.append({"trade_date": r["trade_date"], "calendar_date": r["trade_date"],
                      "dte_remaining": r["dte_entry"], "pnl_usd": 0.0})
        daily.append({"trade_date": r["trade_date"], "calendar_date": r["effective_close_date"],
                      "dte_remaining": 0, "pnl_usd": r["pnl_usd"]})

    d = OUT / tag
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "trades.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    with open(d / "daily.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(daily[0].keys())); w.writeheader(); w.writerows(daily)
    net = sum(r["pnl_usd"] for r in rows)
    wr = 100.0 * sum(1 for r in rows if r["pnl_usd"] > 0) / len(rows)
    print(f"[{tag}] {len(rows)} trades ({src}) | net hold GROSS ${net:,.0f} | WR {wr:.0f}% | "
          f"sem-strike {miss_strikes} -> {d}")
    return len(rows)


def main():
    sw = json.loads(SWEEP_JL.read_text(encoding="utf-8"))
    local = load_local()
    print(f"local pertrade: {{ {', '.join(f'{k}:{len(v)}' for k, v in local.items())} }}")
    OUT.mkdir(parents=True, exist_ok=True)
    cells = os.environ.get("JL_CELLS", "").split(",") if os.environ.get("JL_CELLS") else CELLS
    total = 0
    for tag in cells:
        try:
            total += export_cell(tag, sw, local)
        except Exception as e:
            print(f"[{tag}] FALHOU: {e}")
    print(f"\n=== JL EXPORT: {total} trades em {len(CELLS)} células ===")


if __name__ == "__main__":
    main()
