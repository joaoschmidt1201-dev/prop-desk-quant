"""
===============================================================================
 PL5 EXPORT APP — CTRADE| (QC log) -> trades.csv + daily.csv (1 pasta por DTE)
===============================================================================
 O PL5 roda em TRACKING SINTÉTICO (sem ordens) -> NÃO tem closedTrades. Logo a
 fonte por-trade é o CTRADE| compacto no log (via /backtests/read/log).

 Cada run (d21/d28/d45/d60) vira uma pasta reports/pl5_backtest_app/<tag>/ com:
   - trades.csv: 1 linha/trade com INFO DE ENTRADA (data, dte, strikes K1/K2/K3,
     spot, crédito/débito, VIX) + colunas de P&L por REGRA DE SAÍDA (mid):
       pnl_usd          = hold-to-expiry (settle)
       pnl_exitD (mid)  = sair com D DTE restantes  (D em 30/21/14/10/7/5/3)
   - daily.csv: 2 linhas/trade (abertura + fechamento) p/ a curva de equity.

 As regras de saída aplicáveis por DTE (D < dte_entry) viram o SELETOR no app
 (registry close_rules em apps/api/main.py).

 Uso:  python scripts/pl5_export_app.py
 Saída: reports/pl5_backtest_app/<tag>/{trades.csv, daily.csv}
===============================================================================
"""
from __future__ import annotations
import json, base64, hashlib, time, os, csv, math
import datetime as dt
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOME = Path(os.path.expanduser("~"))
CLOUD_ID = 27848355
SWEEP = REPO / "reports" / "pl5_bwb" / "sweep_pl5.json"
OUT = REPO / "reports" / "pl5_backtest_app"
OUT.mkdir(parents=True, exist_ok=True)

TAGS = ["pl5_d21_std", "pl5_d28_std", "pl5_d45_std", "pl5_d60_std"]
EXIT_GRID = [30, 21, 14, 10, 7, 5, 3]   # DTE restantes (mid) — colunas pnl_exitD

_cred = json.load(open(HOME / ".lean" / "credentials"))
_UID = str(_cred.get("user-id") or _cred.get("user_id"))
_TOK = _cred.get("api-token") or _cred.get("token")

def api(path, body):
    import urllib.request
    ts = str(int(time.time()))
    hashed = hashlib.sha256(f"{_TOK}:{ts}".encode()).hexdigest()
    auth = base64.b64encode(f"{_UID}:{hashed}".encode()).decode()
    req = urllib.request.Request("https://www.quantconnect.com/api/v2" + path,
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Basic {auth}", "Timestamp": ts, "Content-Type": "application/json"},
        method="POST")
    return json.load(urllib.request.urlopen(req, timeout=120))

def fetch_log(bid, max_lines=40000):
    out, start = [], 0
    while start < max_lines:
        r = api("/backtests/read/log", {"projectId": CLOUD_ID, "backtestId": bid,
                                        "start": start, "end": start + 200, "query": ""})
        chunk = r.get("logs") or []
        out.extend(chunk)
        if len(chunk) < 200:
            break
        start += 200
    return out

def _num(x):
    if x in ("", None):
        return None
    try:
        f = float(x); return int(f) if f.is_integer() else f
    except (ValueError, TypeError):
        return x

def parse_ctrade(bid, tries=6):
    for i in range(tries):
        logs = fetch_log(bid)
        hdr = next((l for l in logs if "CTRADEHDR|" in l), None)
        if hdr:
            cols = hdr.split("CTRADEHDR|", 1)[1].split("|")[0].split(",")
            rows = []
            for l in logs:
                if "CTRADE|" not in l:
                    continue
                vals = l.split("CTRADE|", 1)[1].split(",")
                if len(vals) < len(cols):
                    vals += [""] * (len(cols) - len(vals))
                rows.append({c: _num(v) for c, v in zip(cols, vals)})
            if rows:
                return rows
        wait = min(180, 30 * (i + 1))
        print(f"    CTRADE vazio (rate-limit?) — espera {wait}s", flush=True); time.sleep(wait)
    return []

def export_tag(tag, bid):
    recs = parse_ctrade(bid)
    if not recs:
        print(f"[{tag}] sem CTRADE — pula"); return 0
    dte_entry = int(tag.split("_")[1][1:])   # pl5_d45_std -> 45
    applic = [d for d in EXIT_GRID if d < dte_entry]   # regras de saída válidas p/ esse DTE

    rows, daily = [], []
    for r in recs:
        od = str(r.get("od"))
        try:
            o = dt.date.fromisoformat(od); exp = o + dt.timedelta(days=int(r.get("dte") or dte_entry))
        except Exception:
            continue
        hold = float(r.get("snet") or 0)
        row = {
            "trade_date": od, "exp_date": exp.isoformat(), "underlying": "SPX",
            "dte_entry": int(r.get("dte") or dte_entry), "structure": "BWB 1-2-2 puts (+1/-2/+2)",
            "spot_entry": r.get("Se"), "spot_exit": r.get("Ss"),
            "put_upper": r.get("K1"), "put_center": r.get("K2"), "put_lower": r.get("K3"),
            "total_credit": round(float(r.get("cost") or 0) * 100.0, 2),   # débito pago (×100); BWB é net débito
            "vix_entry": r.get("vix"),
            # IV%/EM%: motor não logou ATM IV por-trade -> VIX como proxy de ATM IV (SPX); EM = IV·√(DTE/365).
            "iv_atm_pct": round(float(r.get("vix") or 0), 2) if (r.get("vix") or 0) else "",
            "em_pct": round(float(r.get("vix") or 0) * math.sqrt((int(r.get("dte") or dte_entry)) / 365.0), 2) if (r.get("vix") or 0) else "",
            "expected_move": round(float(r.get("Se") or 0) * (float(r.get("vix") or 0) / 100.0) * math.sqrt((int(r.get("dte") or dte_entry)) / 365.0), 1) if (r.get("vix") and r.get("Se")) else "",
            "pnl_usd": round(hold, 2),                                     # hold-to-expiry (settle)
            "result": "WIN" if hold > 0 else "LOSS", "exit_method": "expiration",
            "mfe": r.get("mfe"), "mae": r.get("mae"),
        }
        # colunas de saída antecipada (mid). Fallback p/ hold se o trade não atingiu D DTE.
        for d in applic:
            v = r.get(f"x{d}m")
            row[f"pnl_exit{d}"] = round(float(v), 2) if v not in ("", None) else round(hold, 2)
        rows.append(row)
        daily.append({"trade_date": od, "calendar_date": od, "dte_remaining": row["dte_entry"], "pnl_usd": 0.0})
        daily.append({"trade_date": od, "calendar_date": exp.isoformat(), "dte_remaining": 0, "pnl_usd": round(hold, 2)})

    d = OUT / tag; d.mkdir(parents=True, exist_ok=True)
    with open(d / "trades.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    with open(d / "daily.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(daily[0].keys())); w.writeheader(); w.writerows(daily)
    net = sum(r["pnl_usd"] for r in rows)
    print(f"[{tag}] {len(rows)} trades | hold net ${net:,.0f} | exits {applic} -> {d}")
    return len(rows)

def main():
    sw = json.loads(SWEEP.read_text(encoding="utf-8")) if SWEEP.exists() else {}
    total = 0
    for tag in TAGS:
        bid = sw.get(tag, {}).get("backtestId")
        if not bid:
            print(f"[{tag}] sem backtestId no sweep_pl5.json — pula"); continue
        try:
            total += export_tag(tag, bid)
        except Exception as e:
            print(f"[{tag}] FALHOU: {e}")
    print(f"\n=== PL5 EXPORT: {total} trades em {len(TAGS)} pastas -> {OUT} ===")

if __name__ == "__main__":
    main()
