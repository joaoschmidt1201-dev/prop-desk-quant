"""
PL5 — matriz REGRA DE FECHAMENTO x DTE, no MID e no CONS (bid/ask).
Explica por que o ranking de DTE muda entre os dois pricings. Lê o CTRADE de cada run
(d21/d28/d45/d60) via QC API. Saída: 2 matrizes (mid, cons) + CSV em reports/pl5_bwb/.
Uso: python scripts/pl5_exit_matrix.py
"""
from __future__ import annotations
import json, base64, hashlib, time, os, sys, csv
from pathlib import Path
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

REPO = Path(__file__).resolve().parent.parent
HOME = Path(os.path.expanduser("~"))
CLOUD_ID = 27848355
SWEEP = REPO / "reports" / "pl5_bwb" / "sweep_pl5.json"
TAGS = [("pl5_d21_std", 21), ("pl5_d28_std", 28), ("pl5_d45_std", 45), ("pl5_d60_std", 60)]
EXITS = [30, 21, 14, 10, 7, 5, 3]

_cred = json.load(open(HOME / ".lean" / "credentials"))
_UID = str(_cred.get("user-id") or _cred.get("user_id")); _TOK = _cred.get("api-token") or _cred.get("token")

def api(path, body):
    import urllib.request
    ts = str(int(time.time())); hashed = hashlib.sha256(f"{_TOK}:{ts}".encode()).hexdigest()
    auth = base64.b64encode(f"{_UID}:{hashed}".encode()).decode()
    req = urllib.request.Request("https://www.quantconnect.com/api/v2" + path, data=json.dumps(body).encode(),
        headers={"Authorization": f"Basic {auth}", "Timestamp": ts, "Content-Type": "application/json"}, method="POST")
    return json.load(urllib.request.urlopen(req, timeout=120))

def parse_ctrade(bid, tries=6):
    for i in range(tries):
        logs, start = [], 0
        while start < 40000:
            r = api("/backtests/read/log", {"projectId": CLOUD_ID, "backtestId": bid, "start": start, "end": start+200, "query": ""})
            ch = r.get("logs") or []; logs += ch
            if len(ch) < 200: break
            start += 200
        hdr = next((l for l in logs if "CTRADEHDR|" in l), None)
        if hdr:
            cols = hdr.split("CTRADEHDR|", 1)[1].split("|")[0].split(",")
            rows = []
            for l in logs:
                if "CTRADE|" not in l: continue
                vals = l.split("CTRADE|", 1)[1].split(",")
                if len(vals) < len(cols): vals += [""]*(len(cols)-len(vals))
                rows.append(dict(zip(cols, vals)))
            if rows: return rows
        time.sleep(min(150, 30*(i+1)))
    return []

def f(x):
    try: return float(x)
    except Exception: return None

def payoff(k1, k2, k3, s): return max(0,k1-s) - 2*max(0,k2-s) + 2*max(0,k3-s)

def build():
    sw = json.loads(SWEEP.read_text(encoding="utf-8")) if SWEEP.exists() else {}
    mid_tbl, cons_tbl = {}, {}   # rule -> {dte: net}
    nmap = {}
    for tag, dte in TAGS:
        bid = sw.get(tag, {}).get("backtestId")
        if not bid: print(f"[{tag}] sem bid"); continue
        recs = parse_ctrade(bid)
        if not recs: print(f"[{tag}] sem CTRADE"); continue
        nmap[dte] = len(recs)
        hold_mid = hold_cons = 0.0
        for r in recs:
            snet = f(r.get("snet")) or 0; hold_mid += snet
            k1,k2,k3,ss,cc = f(r.get("K1")),f(r.get("K2")),f(r.get("K3")),f(r.get("Ss")),f(r.get("cost"))
            if None not in (k1,k2,k3,ss,cc): hold_cons += (payoff(k1,k2,k3,ss)-cc)*100
        mid_tbl.setdefault("Hold", {})[dte] = hold_mid
        cons_tbl.setdefault("Hold", {})[dte] = hold_cons
        for d in EXITS:
            if d >= dte: continue
            sm = sc = 0.0
            for r in recs:
                vm = f(r.get(f"x{d}m")); vc = f(r.get(f"x{d}c")); snet = f(r.get("snet")) or 0
                sm += vm if vm is not None else snet
                # cons fallback: hold_cons do trade
                if vc is not None: sc += vc
                else:
                    k1,k2,k3,ss,cc = f(r.get("K1")),f(r.get("K2")),f(r.get("K3")),f(r.get("Ss")),f(r.get("cost"))
                    sc += (payoff(k1,k2,k3,ss)-cc)*100 if None not in (k1,k2,k3,ss,cc) else 0
            mid_tbl.setdefault(f"Exit {d} DTE", {})[dte] = sm
            cons_tbl.setdefault(f"Exit {d} DTE", {})[dte] = sc

    order = ["Hold"] + [f"Exit {d} DTE" for d in EXITS]
    dtes = [d for _, d in TAGS if d in nmap]
    def show(title, tbl):
        print(f"\n=== {title}  (n: " + " ".join(f"{d}={nmap.get(d,'?')}" for d in dtes) + ") ===")
        print(f"{'Regra':<14}" + "".join(f"{f'{d} DTE':>12}" for d in dtes))
        for rule in order:
            if rule not in tbl: continue
            cells = "".join((f"{tbl[rule][d]:>12,.0f}" if d in tbl[rule] else f"{'—':>12}") for d in dtes)
            print(f"{rule:<14}{cells}")
        # melhor DTE por regra
        print("  melhor DTE por regra: " + ", ".join(
            f"{rule.split()[-2] if 'Exit' in rule else rule}:{max(tbl[rule], key=tbl[rule].get)}" for rule in order if rule in tbl))
    show("MID (atual)", mid_tbl)
    show("CONS / bid-ask (1o backtest p/ CZ)", cons_tbl)

    # CSV (mid) p/ o PDF
    out = REPO / "reports" / "pl5_bwb" / "exit_matrix_mid.csv"
    with open(out, "w", newline="", encoding="utf-8") as fp:
        w = csv.writer(fp); w.writerow(["rule"] + [f"d{d}" for d in dtes])
        for rule in order:
            if rule in mid_tbl: w.writerow([rule] + [round(mid_tbl[rule].get(d, "")) if d in mid_tbl[rule] else "" for d in dtes])
    print(f"\nCSV (mid) -> {out}")

if __name__ == "__main__":
    build()
