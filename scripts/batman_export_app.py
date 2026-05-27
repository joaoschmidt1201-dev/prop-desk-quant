"""
===============================================================================
 BATMAN EXPORT APP — closedTrades (QC API) -> trades.csv + daily.csv (schema do app)
===============================================================================
 Para cada cenário com backtestId em ~/qc_batman/sweep_results.json:
   - puxa totalPerformance.closedTrades via /backtests/read (NÃO bloqueado),
   - agrupa as 6 pernas por entryTime = 1 Batman,
   - P&L por Batman = payoff de settlement (closedTrades.profitLoss ignora o cash-settle ITM),
   - CALIBRAÇÃO ADITIVA: o gap recon-vs-QC é ~constante por trade (fees/slippage que o
     payoff ignora), então distribui (qc_net - recon)/n por trade. Bate o total do QC
     EXATO sem distorcer as fatias (VIX/ano). [multiplicativo explodia em net pequeno.]

 PROFIT TARGETS: NÃO viram backtests separados. Os runs tp50/tp100/tp200 são lidos e
 mesclados no 1DTE_debit como COLUNAS (pnl_tp50/100/200), pra o app oferecer
 "Close at +50%/+100%/+200% of net debit" no seletor de close-rule (igual o filtro de VIX).

 Uso:  python scripts/batman_export_app.py            # exporta tudo do sweep_results.json
       python scripts/batman_export_app.py <bid> <tag>
===============================================================================
"""
from __future__ import annotations
import json, base64, hashlib, time, os, sys, csv, datetime as dt
from collections import defaultdict
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
HOME = Path(os.path.expanduser("~"))
PID = 27848355
OUT = REPO / "reports" / "batman_backtest_app"
SWEEP = HOME / "qc_batman" / "sweep_results.json"
VIX_CACHE = REPO / "data" / "cache" / "vix_daily.parquet"
SPX_CACHE = REPO / "data" / "cache" / "spx_daily.parquet"

# Profit targets são COLUNAS no host, não backtests autônomos.
# host tag -> {coluna: tag do run de TP}
TP_MERGE = {
    "1DTE_debit": {
        "pnl_tp50": "1DTE_debit_tp50",
        "pnl_tp100": "1DTE_debit_tp100",
        "pnl_tp200": "1DTE_debit_tp200",
    },
}
# tags de TP NÃO são exportadas como backtests separados (viram colunas acima).
SKIP_STANDALONE = {"1DTE_debit_tp50", "1DTE_debit_tp100", "1DTE_debit_tp200"}

_cred = json.load(open(HOME / ".lean" / "credentials"))
_UID = str(_cred.get("user-id") or _cred.get("user_id") or _cred.get("userId"))
_TOK = _cred.get("api-token") or _cred.get("token") or _cred.get("apiToken")

SWEEP_RES: dict = {}


def api(path, body):
    import urllib.request
    ts = str(int(time.time()))
    hashed = hashlib.sha256(f"{_TOK}:{ts}".encode()).hexdigest()
    auth = base64.b64encode(f"{_UID}:{hashed}".encode()).decode()
    req = urllib.request.Request("https://www.quantconnect.com/api/v2" + path,
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Basic {auth}", "Timestamp": ts, "Content-Type": "application/json"},
        method="POST")
    return json.load(urllib.request.urlopen(req, timeout=180))


def load_vix():
    if VIX_CACHE.exists():
        v = pd.read_parquet(VIX_CACHE)
        v["date"] = pd.to_datetime(v["date"]).dt.normalize()
        return v.sort_values("date")
    import io, urllib.request
    url = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    raw = urllib.request.urlopen(req, timeout=30).read().decode()
    v = pd.read_csv(io.StringIO(raw)); v.columns = [c.lower() for c in v.columns]
    v["date"] = pd.to_datetime(v["date"]).dt.normalize()
    return v[["date", "close"]].rename(columns={"close": "vix"}).sort_values("date")


def vix_at(d, vdf):
    d = pd.Timestamp(d).normalize()
    p = vdf[vdf["date"] <= d].tail(1)
    return round(float(p["vix"].iloc[0]), 2) if len(p) else None


def load_spx():
    """SPX close diário (settlement ref do SPXW PM). Cache; Yahoo chart endpoint (stdlib)."""
    if SPX_CACHE.exists():
        s = pd.read_parquet(SPX_CACHE)
        s["date"] = pd.to_datetime(s["date"]).dt.normalize()
        return s.sort_values("date")
    import urllib.request
    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
    url = "https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC?range=5y&interval=1d"
    last = None
    for _ in range(4):
        try:
            data = json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30))
            res = data["chart"]["result"][0]
            ts = res["timestamp"]
            closes = res["indicators"]["quote"][0]["close"]
            rows = [(pd.Timestamp(t, unit="s").normalize(), c) for t, c in zip(ts, closes) if c is not None]
            s = pd.DataFrame(rows, columns=["date", "spx"]).sort_values("date")
            if len(s) > 100:
                SPX_CACHE.parent.mkdir(parents=True, exist_ok=True)
                s.to_parquet(SPX_CACHE, index=False)
                return s
        except Exception as e:
            last = e; time.sleep(5)
    raise RuntimeError(f"nao consegui baixar SPX diario (Yahoo chart): {last}")


def spx_at(d, sdf):
    d = pd.Timestamp(d).normalize()
    ex = sdf[sdf["date"] == d]
    if len(ex):
        return float(ex["spx"].iloc[0])
    p = sdf[sdf["date"] <= d].tail(1)
    return float(p["spx"].iloc[0]) if len(p) else None


def parse_symbol(v):
    body = v.replace("SPXW", "").strip()            # "220622C03835000"
    exp = dt.datetime.strptime(body[:6], "%y%m%d").date()
    return exp, body[6], int(body[7:]) / 1000.0


def _money(s):
    try:
        return float(str(s).replace("$", "").replace(",", "").strip())
    except Exception:
        return None


def recon(bid, qc_net):
    """Per-trade reconstructed P&L (1 Batman por entryTime), com calibração ADITIVA
    pro total bater no QC sem distorcer as fatias. Devolve lista de dicts."""
    bt = api("/backtests/read", {"projectId": PID, "backtestId": bid})["backtest"]
    ct = (bt.get("totalPerformance") or {}).get("closedTrades") or []
    if not ct:
        return []
    vdf = load_vix(); sdf = load_spx()
    groups = defaultdict(list)
    for t in ct:
        groups[t["entryTime"]].append(t)
    trades = []
    for et, legs in sorted(groups.items()):
        entry = dt.datetime.fromisoformat(et.replace("Z", "+00:00"))
        tdate = entry.date()
        exp = max(parse_symbol(l["symbols"][0]["value"])[0] for l in legs)
        S_exp = spx_at(exp, sdf)
        if S_exp is None:
            continue
        debit = 0.0; pnl = 0.0
        for l in legs:
            _, right, K = parse_symbol(l["symbols"][0]["value"])
            n = (1 if l["direction"] == 0 else -1) * abs(l["quantity"]) * 100
            debit += n * l["entryPrice"]
            if (l.get("exitPrice") or 0) > 0:           # fechada cedo (TP real) -> round-trip exato
                pnl += l.get("profitLoss") or 0
            else:                                        # held-to-expiry -> payoff de settlement
                intr = max(0.0, S_exp - K) if right == "C" else max(0.0, K - S_exp)
                pnl += n * (intr - l["entryPrice"])
        trades.append({"trade_date": tdate, "exp_date": exp, "dte": max((exp - tdate).days, 1),
                       "debit": round(debit, 2), "pnl": pnl, "vix": vix_at(tdate, vdf)})
    rec = sum(t["pnl"] for t in trades)
    if qc_net is not None and trades:
        adj = (qc_net - rec) / len(trades)              # gap ~constante por trade -> aditivo
        for t in trades:
            t["pnl"] = round(t["pnl"] + adj, 2)
    return trades


def export(tag, bid, qc_net, underlying="SPX"):
    trades = recon(bid, qc_net)
    if not trades:
        print(f"[{tag}] sem closedTrades"); return 0
    # mescla profit-targets como colunas (só nos host tags)
    tp_maps = {}
    for col, tp_tag in TP_MERGE.get(tag, {}).items():
        tr = SWEEP_RES.get(tp_tag, {})
        tbid = tr.get("backtestId"); tqc = _money((tr.get("runtime") or {}).get("Net Profit"))
        if tbid:
            tp_maps[col] = {t["trade_date"]: t["pnl"] for t in recon(tbid, tqc)}

    rows = []
    for t in trades:
        row = {
            "trade_date": t["trade_date"].isoformat(), "exp_date": t["exp_date"].isoformat(),
            "underlying": underlying, "dte_entry": t["dte"], "total_credit": t["debit"],
            "pnl_usd": t["pnl"], "vix_entry": t["vix"],
            "result": "WIN" if t["pnl"] > 0 else "LOSS", "exit_method": "expiration",
            "in_range": t["pnl"] > 0,
        }
        for col, m in tp_maps.items():
            row[col] = m.get(t["trade_date"], t["pnl"])   # dia sem par no run de TP -> hold
        rows.append(row)

    daily = []
    for t in trades:
        daily.append({"trade_date": t["trade_date"].isoformat(), "calendar_date": t["trade_date"].isoformat(),
                      "dte_remaining": t["dte"], "pnl_usd": 0.0})
        daily.append({"trade_date": t["trade_date"].isoformat(), "calendar_date": t["exp_date"].isoformat(),
                      "dte_remaining": 0, "pnl_usd": t["pnl"]})

    d = OUT / tag; d.mkdir(parents=True, exist_ok=True)
    with open(d / "trades.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    with open(d / "daily.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(daily[0].keys())); w.writeheader(); w.writerows(daily)
    net = sum(r["pnl_usd"] for r in rows)
    wr = 100.0 * sum(1 for r in rows if r["pnl_usd"] > 0) / len(rows)
    extra = (" | TP cols: " + ",".join(tp_maps)) if tp_maps else ""
    print(f"[{tag}] {len(rows)} batmans | net ${net:,.0f} | WR {wr:.0f}%{extra} -> {d}")
    return len(rows)


def main():
    global SWEEP_RES
    OUT.mkdir(parents=True, exist_ok=True)
    SWEEP_RES = json.loads(SWEEP.read_text(encoding="utf-8")) if SWEEP.exists() else {}
    if len(sys.argv) >= 3:
        bid, tag = sys.argv[1], sys.argv[2]
        export(tag, bid, _money((SWEEP_RES.get(tag, {}).get("runtime") or {}).get("Net Profit")))
        return
    for tag, r in SWEEP_RES.items():
        if tag in SKIP_STANDALONE:
            continue
        bid = r.get("backtestId")
        if not bid:
            continue
        try:
            export(tag, bid, _money((r.get("runtime") or {}).get("Net Profit")))
        except Exception as e:
            print(f"[{tag}] FALHOU: {e}")


if __name__ == "__main__":
    main()
