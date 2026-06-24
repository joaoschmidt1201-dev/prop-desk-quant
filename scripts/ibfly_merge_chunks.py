"""
INVERSE BUTTERFLY — MERGE de chunks -> trades.csv final (configs que truncavam no log).
Cada config truncado foi re-rodado em metades de data (h1+h2) ou janelas (1DTE: c1..c6).
Este script baixa os CTRADE de cada chunk, CONCATENA, reconcilia (Σ runtimes dos chunks) e
escreve reports/ibfly_backtest_app/d{dte}_w{width}/{trades,daily}.csv — idêntico ao export normal.
Uso: python scripts/ibfly_merge_chunks.py
"""
from __future__ import annotations
import json, base64, hashlib, time, os, csv, sys, re, math
from pathlib import Path

# ── valor teórico BS p/ validar o MTM do TP (anti quote-stale) — espelha ibfly_export_app ──
TP_VOL_MULT = 3.0
def _N(x): return 0.5 * (1 + math.erf(x / math.sqrt(2)))
def _bs_call(S, K, T, sig, r=0.04):
    if S <= 0 or K <= 0: return 0.0
    if T <= 0 or sig <= 0: return max(0.0, S - K)
    d1 = (math.log(S / K) + (r + sig * sig / 2) * T) / (sig * math.sqrt(T)); d2 = d1 - sig * math.sqrt(T)
    return S * _N(d1) - K * math.exp(-r * T) * _N(d2)
def _ifly_cap_pnl(spot, dte_rem, vol, C, Clo, Cup, credit):
    if spot is None or C is None: return None
    T = (dte_rem or 0) / 365.0; sig = (vol or 0.15) * TP_VOL_MULT
    val = 2 * _bs_call(spot, C, T, sig) - _bs_call(spot, Clo, T, sig) - _bs_call(spot, Cup, T, sig)
    return val * 100.0 + (credit or 0.0)
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

REPO = Path(__file__).resolve().parent.parent
HOME = Path(os.path.expanduser("~")); CLOUD_ID = 27848355
SWEEP = REPO / "reports" / "inverse_butterfly" / "sweep_ibfly.json"
OUT = REPO / "reports" / "ibfly_backtest_app"

# (dte_label, width, [tags dos chunks]) — esquema UNIFORME ibre_d{DTE}_w{W}_{h1/h2 | c1..c6}.
# 4/7/14 DTE = 2 metades (h1+h2); 1 DTE = 6 janelas (c1..c6). Concatena na ordem temporal.
_W6 = ["0.15", "0.25", "0.40", "0.50", "0.60", "0.75"]
MERGES = (
    [(d, w, [f"ibre_d{d}_w{w}_h1", f"ibre_d{d}_w{w}_h2"]) for d in (4, 7, 14) for w in _W6]
    + [(1, w, [f"ibre_d1_w{w}_c{i}" for i in range(1, 7)]) for w in ("0.15", "0.25")]
)

_cred = json.load(open(HOME / ".lean" / "credentials"))
_UID = str(_cred.get("user-id") or _cred.get("user_id")); _TOK = _cred.get("api-token") or _cred.get("token")

def api(path, body):
    import urllib.request
    ts = str(int(time.time())); h = hashlib.sha256(f"{_TOK}:{ts}".encode()).hexdigest()
    auth = base64.b64encode(f"{_UID}:{h}".encode()).decode()
    req = urllib.request.Request("https://www.quantconnect.com/api/v2" + path, data=json.dumps(body).encode(),
        headers={"Authorization": f"Basic {auth}", "Timestamp": ts, "Content-Type": "application/json"}, method="POST")
    return json.load(urllib.request.urlopen(req, timeout=120))

def parse_ctrade(bid, tries=4):
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

def rn(sw, tag):
    m = re.search(r"n=(\d+)", (sw.get(tag, {}).get("runtime") or {}).get("n / dte / W", "")); return int(m.group(1)) if m else None

def merge(dte, width, tags, sw):
    # checa que todos os chunks existem no sweep
    missing = [t for t in tags if not sw.get(t, {}).get("backtestId")]
    if missing:
        print(f"[d{dte}_w{width}] chunks faltando: {missing} — pula"); return None
    recs = []
    exp_total = 0
    for t in tags:
        rc = parse_ctrade(sw[t]["backtestId"])
        n_rt = rn(sw, t)
        if not rc:
            print(f"[d{dte}_w{width}] {t} SEM CTRADE — pula merge"); return None
        if n_rt and len(rc) < n_rt:
            print(f"[d{dte}_w{width}] {t} ainda TRUNCADO ({len(rc)}/{n_rt}) — chunk grande demais; pula"); return None
        recs += rc; exp_total += (n_rt or len(rc))
    recs.sort(key=lambda r: (r["open_date"], r["open_time"]))
    exit_ds = sorted({int(c[1:].split("_")[0]) for c in recs[0] if c.startswith("x") and c.endswith("_m")}, reverse=True)
    rows, daily = [], []
    for i, r in enumerate(recs, 1):
        od = r["open_date"]; hold = f(r["hold_net_mid"]) or 0.0
        cred = f(r.get("credit_mid")) or 0.0
        C, Clo, Cup, aiv = f(r.get("C")), f(r.get("Clo")), f(r.get("Cup")), f(r.get("atm_iv"))
        def eff(col):
            v = f(r.get(col)); return round(v, 2) if v is not None else round(hold, 2)
        def tp_hit(tp): return f(r.get(f"tp{tp}_m")) is not None
        def tp_value(tp):  # MTM real do cruzamento, validado por teto BS (mantém real, capa anomalia)
            mtm = f(r.get(f"tp{tp}_m"))
            if mtm is None: return None
            cap = _ifly_cap_pnl(f(r.get(f"tp{tp}_s")), f(r.get(f"tp{tp}_d")), aiv, C, Clo, Cup, cred)
            return round(min(mtm, cap), 2) if cap is not None else round(mtm, 2)
        def composite(tp, exit_n):
            tpd = f(r.get(f"tp{tp}_d")); v = tp_value(tp)
            if v is not None and tpd is not None and tpd >= exit_n:
                return v
            return eff(f"x{exit_n}_m")
        def composite_noon(tp):
            tpd = f(r.get(f"tp{tp}_d")); tph = f(r.get(f"tp{tp}_h")); v = tp_value(tp)
            if v is not None and tpd is not None and (tpd > 0 or (tpd == 0 and tph is not None and tph < 12)):
                return v
            return eff("e12_m")
        row = {
            "trade_date": od, "exp_date": r["expiry_date"], "underlying": "SPX",
            "dte_entry": int(f(r["dte_real"]) or dte), "width_sigma": width, "structure": "Inverse Butterfly 1-2-1 (calls)",
            "spot_entry": f(r["S_entry"]), "spot_exit": f(r["S_settle"]),
            "call_atm": f(r["C"]), "call_lo": f(r["Clo"]), "call_up": f(r["Cup"]),
            "total_credit": round(f(r["credit_mid"]) or 0, 2), "vix_entry": f(r["vix"]),
            "iv_atm_pct": round((f(r["atm_iv"]) or 0)*100, 2), "expected_move": round(f(r["sigma"]) or 0, 1),
            "pnl_usd": round(hold, 2),
            "pnl_tp25": tp_value(25) if tp_hit(25) else round(hold, 2),
            "pnl_tp50": tp_value(50) if tp_hit(50) else round(hold, 2),
            "pnl_tp75": tp_value(75) if tp_hit(75) else round(hold, 2),
            "result": "WIN" if hold > 0 else "LOSS", "exit_method": "expiration",
            "mfe": f(r.get("mfe")), "mae": f(r.get("mae")),
        }
        for d in exit_ds:
            row[f"pnl_exit{d}"] = eff(f"x{d}_m")
        for tp in (25, 50, 75):
            for d in exit_ds:
                row[f"pnl_tp{tp}_exit{d}"] = composite(tp, d)
        if not exit_ds and f(r.get("e12_m")) is not None:
            for tp in (25, 50, 75):
                row[f"pnl_tp{tp}_noon"] = composite_noon(tp)
        rows.append(row)
        daily.append({"trade_date": od, "calendar_date": od, "dte_remaining": row["dte_entry"], "pnl_usd": 0.0})
        daily.append({"trade_date": od, "calendar_date": r["expiry_date"], "dte_remaining": 0, "pnl_usd": round(hold, 2)})
    d = OUT / f"d{dte}_w{width}"; d.mkdir(parents=True, exist_ok=True)
    with open(d / "trades.csv", "w", newline="", encoding="utf-8") as fp:
        w = csv.DictWriter(fp, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    with open(d / "daily.csv", "w", newline="", encoding="utf-8") as fp:
        w = csv.DictWriter(fp, fieldnames=list(daily[0].keys())); w.writeheader(); w.writerows(daily)
    net = sum(r["pnl_usd"] for r in rows)
    print(f"[d{dte}_w{width}] MERGED {len(rows)} trades (esperado ~{exp_total}) | HOLD net ${net:,.0f} -> {d.name}")
    return len(rows)

def main():
    sw = json.loads(SWEEP.read_text(encoding="utf-8"))
    total = 0
    for dte, width, tags in MERGES:
        # idempotente: se todos os chunks dessa célula estão no sweep, re-mergeia (sobrescreve com dados novos);
        # se faltam chunks (ainda rodando), o merge() detecta e pula sem apagar o que existe.
        try:
            n = merge(dte, width, tags, sw)
            if n: total += n
            time.sleep(15)
        except Exception as e:
            print(f"[d{dte}_w{width}] FALHOU: {str(e)[:120]}")
    print(f"\n=== MERGE: {total} trades em configs concatenados -> {OUT} ===")

if __name__ == "__main__":
    main()
