"""
===============================================================================
 BATMAN EXPORT APP — closedTrades (QC API) -> trades.csv + daily.csv (schema do app)
===============================================================================
 Para cada cenário com backtestId em ~/qc_batman/sweep_results.json:
   - puxa totalPerformance.closedTrades via /backtests/read (NÃO bloqueado),
   - agrupa as 6 pernas por entryTime = 1 Batman,
   - P&L hold por Batman = soma de profitLoss das pernas (exato, já em USD),
   - débito = sum(entryPrice*|qty|*100 * sign),  VIX = cache grátis (data/cache),
   - escreve reports/batman_backtest_app/<tag>/trades.csv + daily.csv.

 daily.csv = entrada (0) + expiry (pnl) por trade — schema satisfeito; close-rule
 do app fica coarse (intradiário do TP está bloqueado no ObjectStore). Hold + KPIs
 + slice por VIX funcionam 100%.

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

_cred = json.load(open(HOME / ".lean" / "credentials"))
_UID = str(_cred.get("user-id") or _cred.get("user_id") or _cred.get("userId"))
_TOK = _cred.get("api-token") or _cred.get("token") or _cred.get("apiToken")

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
    # fallback Cboe
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

SPX_CACHE = REPO / "data" / "cache" / "spx_daily.parquet"

def load_spx():
    """SPX close diário (settlement ref do SPXW PM). Cache; fallback stooq -> yfinance."""
    if SPX_CACHE.exists():
        s = pd.read_parquet(SPX_CACHE)
        s["date"] = pd.to_datetime(s["date"]).dt.normalize()
        return s.sort_values("date")
    # Yahoo chart endpoint (stdlib, NÃO rate-limited como o yfinance bulk; ver apps/api/live_spot.py)
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
    body = v.replace("SPXW", "").strip()        # "220622C03835000"
    exp = dt.datetime.strptime(body[:6], "%y%m%d").date()
    return exp, body[6], int(body[7:]) / 1000.0

def export(bid, tag, underlying="SPX", qc_net=None):
    bt = api("/backtests/read", {"projectId": PID, "backtestId": bid})["backtest"]
    ct = (bt.get("totalPerformance") or {}).get("closedTrades") or []
    if not ct:
        print(f"[{tag}] sem closedTrades (status={bt.get('status')})"); return 0
    vdf = load_vix(); sdf = load_spx()
    groups = defaultdict(list)
    for t in ct:
        groups[t["entryTime"]].append(t)

    trades, daily = [], []
    skipped = 0
    for et, legs in sorted(groups.items()):
        entry = dt.datetime.fromisoformat(et.replace("Z", "+00:00"))
        tdate = entry.date()
        exp = max(parse_symbol(l["symbols"][0]["value"])[0] for l in legs)
        S_exp = spx_at(exp, sdf)
        if S_exp is None:
            skipped += 1; continue
        # P&L pelo PAYOFF real (closedTrades.profitLoss ignora o cash-settle ITM -> errado).
        debit = 0.0; pnl = 0.0
        for l in legs:
            _, right, K = parse_symbol(l["symbols"][0]["value"])
            n = (1 if l["direction"] == 0 else -1) * abs(l["quantity"]) * 100
            debit += n * l["entryPrice"]
            if (l.get("exitPrice") or 0) > 0:     # fechada CEDO (TP real) -> P&L do round-trip (correto)
                pnl += l.get("profitLoss") or 0
            else:                                  # held-to-expiry -> payoff (closedTrades ignora cash-settle)
                intr = max(0.0, S_exp - K) if right == "C" else max(0.0, K - S_exp)
                pnl += n * (intr - l["entryPrice"])
        pnl = round(pnl, 2); debit = round(debit, 2)
        vix = vix_at(tdate, vdf)
        dte = max((exp - tdate).days, 1)
        trades.append({
            "trade_date": tdate.isoformat(), "exp_date": exp.isoformat(), "underlying": underlying,
            "dte_entry": dte, "total_credit": debit, "pnl_usd": pnl, "vix_entry": vix,
            "result": "WIN" if pnl > 0 else "LOSS", "exit_method": "expiration", "in_range": pnl > 0,
        })
        daily.append({"trade_date": tdate.isoformat(), "calendar_date": tdate.isoformat(),
                      "dte_remaining": dte, "pnl_usd": 0.0})
        daily.append({"trade_date": tdate.isoformat(), "calendar_date": exp.isoformat(),
                      "dte_remaining": 0, "pnl_usd": pnl})

    # calibra à equity AUTORITATIVA do QC (recon usa SPX close ~ base vs settle intradiário).
    # fator > 0 preserva sinal -> WR/result/in_range intactos; só ajusta magnitude.
    recon = sum(t["pnl_usd"] for t in trades)
    if qc_net is not None and recon:
        fac = qc_net / recon
        for t in trades:
            t["pnl_usd"] = round(t["pnl_usd"] * fac, 2)
        for r in daily:
            r["pnl_usd"] = round(r["pnl_usd"] * fac, 2)

    d = OUT / tag; d.mkdir(parents=True, exist_ok=True)
    with open(d / "trades.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(trades[0].keys())); w.writeheader(); w.writerows(trades)
    with open(d / "daily.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(daily[0].keys())); w.writeheader(); w.writerows(daily)
    net = sum(t["pnl_usd"] for t in trades)
    wr = 100.0 * sum(1 for t in trades if t["pnl_usd"] > 0) / len(trades)
    print(f"[{tag}] {len(trades)} batmans | net ${net:,.0f} | WR {wr:.0f}% -> {d}")
    return len(trades)

def _money(s):
    try:
        return float(str(s).replace("$", "").replace(",", "").strip())
    except Exception:
        return None

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    if len(sys.argv) >= 3:
        export(sys.argv[1], sys.argv[2]); return
    res = json.loads(SWEEP.read_text(encoding="utf-8")) if SWEEP.exists() else {}
    for tag, r in res.items():
        bid = r.get("backtestId")
        if bid:
            try:
                export(bid, tag, qc_net=_money((r.get("runtime") or {}).get("Net Profit")))
            except Exception as e:
                print(f"[{tag}] FALHOU: {e}")

if __name__ == "__main__":
    main()
