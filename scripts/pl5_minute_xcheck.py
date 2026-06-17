"""
PL5 — CROSS-CHECK de SPREAD: minuto vs horário (resposta ao CZ).
Lê o run pl5_d60_minchk (MINUTO, com cm/h1/h2/h3 no CTRADE) e compara o spread de entrada
(cons - mid) e os half-spreads por perna contra o run HORÁRIO d60 (reports/pl5_backtest_app/
pl5_d60_std/trades.csv) nas MESMAS datas. Prova se os spreads de 30-58pt do horário são
artefato de quote stale (minuto deve ser muito menor) ou custo real.
Uso: python scripts/pl5_minute_xcheck.py
"""
from __future__ import annotations
import json, base64, hashlib, time, os, csv, sys
from pathlib import Path
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

REPO = Path(__file__).resolve().parent.parent
HOME = Path(os.path.expanduser("~"))
CLOUD_ID = 27848355
SWEEP = REPO / "reports" / "pl5_bwb" / "sweep_pl5.json"
HOURLY_CSV = REPO / "reports" / "pl5_backtest_app" / "pl5_d60_std" / "trades.csv"

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

def fetch_log(bid, max_lines=20000):
    out, start = [], 0
    while start < max_lines:
        r = api("/backtests/read/log", {"projectId": CLOUD_ID, "backtestId": bid,
                                        "start": start, "end": start + 200, "query": ""})
        chunk = r.get("logs") or []
        out.extend(chunk)
        if len(chunk) < 200: break
        start += 200
    return out

def parse_ctrade(bid):
    logs = fetch_log(bid)
    hdr = next((l for l in logs if "CTRADEHDR|" in l), None)
    if not hdr: return []
    cols = hdr.split("CTRADEHDR|", 1)[1].split("|")[0].split(",")
    rows = []
    for l in logs:
        if "CTRADE|" not in l: continue
        vals = l.split("CTRADE|", 1)[1].split(",")
        if len(vals) < len(cols): vals += [""] * (len(cols) - len(vals))
        rows.append(dict(zip(cols, vals)))
    return rows

def fnum(x):
    try: return float(x)
    except Exception: return None

def main():
    sw = json.loads(SWEEP.read_text(encoding="utf-8")) if SWEEP.exists() else {}
    bid = sw.get("pl5_d60_minchk", {}).get("backtestId")
    if not bid:
        print("pl5_d60_minchk ainda sem backtestId no sweep_pl5.json — rode o --minchk antes."); return
    recs = parse_ctrade(bid)
    if not recs:
        print(f"sem CTRADE no run {bid} (ainda rodando / rate-limit?)."); return
    # horário: data -> entry_spread (pts)
    hourly = {}
    if HOURLY_CSV.exists():
        for r in csv.DictReader(open(HOURLY_CSV, encoding="utf-8")):
            sp = fnum(r.get("entry_spread"))
            if sp is not None: hourly[r["trade_date"]] = sp / 100.0   # $ -> pts

    print(f"=== PL5 d60 — SPREAD minuto vs horário (run {bid[:12]}…, n={len(recs)}) ===")
    print(f"{'data':<12}{'vix':>6}{'sp_hora':>9}{'sp_min':>8}{'h1(-30d)':>10}{'h2(-18d)':>10}{'h3(-3d)':>9}")
    mins, hrs = [], []
    for r in recs:
        od = r.get("od"); cons = fnum(r.get("cost")); cm = fnum(r.get("cm"))
        h1, h2, h3 = fnum(r.get("h1")), fnum(r.get("h2")), fnum(r.get("h3"))
        if cons is None or cm is None: continue
        sp_min = cons - cm; vix = fnum(r.get("vix")) or 0
        sp_hr = hourly.get(od)
        mins.append(sp_min)
        if sp_hr is not None: hrs.append((sp_hr, sp_min))
        print(f"{od:<12}{vix:>6.1f}{(sp_hr if sp_hr is not None else float('nan')):>9.1f}{sp_min:>8.1f}"
              f"{(h1 or 0):>10.2f}{(h2 or 0):>10.2f}{(h3 or 0):>9.2f}")
    import statistics as st
    if mins:
        print(f"\nSPREAD entrada MINUTO: mediana {st.median(mins):.2f} pts | média {st.mean(mins):.2f} | max {max(mins):.2f}")
    if hrs:
        mh = st.median([h for h, _ in hrs]); mm = st.median([m for _, m in hrs])
        print(f"Mesmas datas: mediana HORÁRIO {mh:.2f} pts vs MINUTO {mm:.2f} pts -> "
              f"horário {'INFLA' if mh > mm*1.5 else '≈'} {mh/mm:.1f}× o minuto" if mm else "")
        print("\nVEREDITO: se minuto << horário -> os 30-58pt do horário são ARTEFATO de quote stale;")
        print("o custo de execução REAL é o do minuto (perna -3Δ = h3 domina).")

if __name__ == "__main__":
    main()
