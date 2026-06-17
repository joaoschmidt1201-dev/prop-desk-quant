"""
INVERSE BUTTERFLY EXPORT APP — CTRADE (QC log) -> trades.csv + daily.csv por (DTE × width).
Só os configs VERIFICADOS 100% completos no log (7/28/45 DTE; 1/14 ficam p/ chunked).
Cada (DTE,width) vira reports/ibfly_backtest_app/d{dte}_w{width}/ com:
  - trades.csv: 1 linha/trade, info de entrada + P&L por close-rule (mid):
      pnl_usd = HOLD; pnl_tp25/50/75; pnl_exit{d} (DTE-restante)
  - daily.csv: 2 linhas/trade (abertura + settle) p/ a curva.
Uso: python scripts/ibfly_export_app.py
"""
from __future__ import annotations
import json, base64, hashlib, time, os, csv, sys
import datetime as dt
from pathlib import Path
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

REPO = Path(__file__).resolve().parent.parent
HOME = Path(os.path.expanduser("~")); CLOUD_ID = 27848355
SWEEP = REPO / "reports" / "inverse_butterfly" / "sweep_ibfly.json"
OUT = REPO / "reports" / "ibfly_backtest_app"; OUT.mkdir(parents=True, exist_ok=True)

# (dte_label, width_label, sweep_tag) — só os COMPLETOS (verificado: log == runtime n)
CONFIGS = [
    (7,  "0.15", "ibfly_dte7"),  (7,  "0.50", "ibfly_d7_w0.50"), (7,  "0.60", "ibfly_d7_w0.60"),
    (28, "0.15", "ibfly_dte30"), (28, "0.25", "ibfly_w0.25"),    (28, "0.40", "ibfly_w0.40"),
    (28, "0.50", "ibfly_w0.50"), (28, "0.60", "ibfly_w0.60"),    (28, "0.75", "ibfly_w0.75"),
    (45, "0.15", "ibfly_dte45"), (45, "0.40", "ibfly_d45_w0.40"),
    (45, "0.50", "ibfly_d45_w0.50"), (45, "0.60", "ibfly_d45_w0.60"),
]

_cred = json.load(open(HOME / ".lean" / "credentials"))
_UID = str(_cred.get("user-id") or _cred.get("user_id")); _TOK = _cred.get("api-token") or _cred.get("token")

def api(path, body):
    import urllib.request
    ts = str(int(time.time())); h = hashlib.sha256(f"{_TOK}:{ts}".encode()).hexdigest()
    auth = base64.b64encode(f"{_UID}:{h}".encode()).decode()
    req = urllib.request.Request("https://www.quantconnect.com/api/v2" + path, data=json.dumps(body).encode(),
        headers={"Authorization": f"Basic {auth}", "Timestamp": ts, "Content-Type": "application/json"}, method="POST")
    return json.load(urllib.request.urlopen(req, timeout=120))

def parse_ctrade(bid, tries=5):
    for i in range(tries):
        logs, start = [], 0
        while start < 60000:
            r = api("/backtests/read/log", {"projectId": CLOUD_ID, "backtestId": bid, "start": start, "end": start+200, "query": ""})
            ch = r.get("logs") or []; logs += ch
            if len(ch) < 200: break
            start += 200
        hdr = next((l for l in logs if "CTRADEHDR|" in l), None)
        if hdr:
            cols = hdr.split("CTRADEHDR|", 1)[1].split("|")[0].split(",")
            rows = [dict(zip(cols, l.split("CTRADE|", 1)[1].split(","))) for l in logs if "CTRADE|" in l and "HDR" not in l]
            if rows: return rows
        time.sleep(min(120, 30*(i+1)))
    return []

def f(x):
    try: return float(x)
    except Exception: return None

def runtime_n(sw, tag):
    import re
    m = re.search(r"n=(\d+)", (sw.get(tag, {}).get("runtime") or {}).get("n / dte / W", ""))
    return int(m.group(1)) if m else None

def export(dte, width, tag, bid, sw):
    recs = parse_ctrade(bid)
    if not recs:
        print(f"[d{dte}_w{width}] SEM CTRADE — pula"); return None
    rn = runtime_n(sw, tag)
    if rn and len(recs) < rn:
        print(f"[d{dte}_w{width}] ⚠️ TRUNCADO ({len(recs)}/{rn}) — PULA (não subir incompleto)"); return None
    exit_ds = sorted({int(c[1:].split("_")[0]) for c in recs[0] if c.startswith("x") and c.endswith("_m")}, reverse=True)
    rows, daily = [], []
    for r in recs:
        od = r["open_date"]; hold = f(r["hold_net_mid"]) or 0.0
        def eff(col):
            v = f(r.get(col)); return round(v, 2) if v is not None else round(hold, 2)
        row = {
            "trade_date": od, "exp_date": r["expiry_date"], "underlying": "SPX",
            "dte_entry": int(f(r["dte_real"]) or dte), "width_sigma": width, "structure": "Inverse Butterfly 1-2-1 (calls)",
            "spot_entry": f(r["S_entry"]), "spot_exit": f(r["S_settle"]),
            "call_atm": f(r["C"]), "call_lo": f(r["Clo"]), "call_up": f(r["Cup"]),
            "total_credit": round(f(r["credit_mid"]) or 0, 2),
            "vix_entry": f(r["vix"]),
            "iv_atm_pct": round((f(r["atm_iv"]) or 0)*100, 2),
            "expected_move": round(f(r["sigma"]) or 0, 1),
            "pnl_usd": round(hold, 2),
            "pnl_tp25": eff("tp25_m"), "pnl_tp50": eff("tp50_m"), "pnl_tp75": eff("tp75_m"),
            "result": "WIN" if hold > 0 else "LOSS", "exit_method": "expiration",
            "mfe": f(r.get("mfe")), "mae": f(r.get("mae")),
        }
        for d in exit_ds:
            row[f"pnl_exit{d}"] = eff(f"x{d}_m")
        rows.append(row)
        daily.append({"trade_date": od, "calendar_date": od, "dte_remaining": row["dte_entry"], "pnl_usd": 0.0})
        daily.append({"trade_date": od, "calendar_date": r["expiry_date"], "dte_remaining": 0, "pnl_usd": round(hold, 2)})
    d = OUT / f"d{dte}_w{width}"; d.mkdir(parents=True, exist_ok=True)
    with open(d / "trades.csv", "w", newline="", encoding="utf-8") as fp:
        w = csv.DictWriter(fp, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    with open(d / "daily.csv", "w", newline="", encoding="utf-8") as fp:
        w = csv.DictWriter(fp, fieldnames=list(daily[0].keys())); w.writeheader(); w.writerows(daily)
    net = sum(r["pnl_usd"] for r in rows)
    print(f"[d{dte}_w{width}] {len(rows)} trades | HOLD net ${net:,.0f} | exits {exit_ds} -> {d.name}")
    return len(rows)

def main():
    sw = json.loads(SWEEP.read_text(encoding="utf-8"))
    total = 0
    for dte, width, tag in CONFIGS:
        dest = OUT / f"d{dte}_w{width}" / "trades.csv"
        if dest.exists():   # idempotente: não re-baixa o que já saiu (evita re-disparar o rate-limit)
            print(f"[d{dte}_w{width}] já existe — skip"); continue
        bid = sw.get(tag, {}).get("backtestId")
        if not bid:
            print(f"[{tag}] sem backtestId — pula"); continue
        n = export(dte, width, tag, bid, sw)
        if n: total += n
        time.sleep(20)      # pausa entre configs p/ respeitar o rate-limit do QC
    print(f"\n=== IBFLY EXPORT: {total} trades novos -> {OUT} ===")

if __name__ == "__main__":
    main()
