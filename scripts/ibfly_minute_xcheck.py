"""
INVERSE BUTTERFLY — cross-check de SPREAD minuto vs horário (aprendizado PL5: VERIFICAR, não assumir).
Compara o spread de entrada (credit_mid - credit_cons) do run de MINUTO (ibfly_d30_minchk) contra o
HORÁRIO (ibfly_dte30) nas mesmas datas/estrutura. Pernas near-ATM -> hipótese: cons horário inflado.
Uso: python scripts/ibfly_minute_xcheck.py
"""
from __future__ import annotations
import json, base64, hashlib, time, os, sys, csv as csvmod, statistics as st
from pathlib import Path
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

REPO = Path(__file__).resolve().parent.parent
HOME = Path(os.path.expanduser("~")); CLOUD_ID = 27848355
SWEEP = REPO / "reports" / "inverse_butterfly" / "sweep_ibfly.json"
_cred = json.load(open(HOME / ".lean" / "credentials"))
_UID = str(_cred.get("user-id") or _cred.get("user_id")); _TOK = _cred.get("api-token") or _cred.get("token")

def api(path, body):
    import urllib.request
    ts = str(int(time.time())); h = hashlib.sha256(f"{_TOK}:{ts}".encode()).hexdigest()
    auth = base64.b64encode(f"{_UID}:{h}".encode()).decode()
    req = urllib.request.Request("https://www.quantconnect.com/api/v2" + path, data=json.dumps(body).encode(),
        headers={"Authorization": f"Basic {auth}", "Timestamp": ts, "Content-Type": "application/json"}, method="POST")
    return json.load(urllib.request.urlopen(req, timeout=120))

def fetch_logs(bid, maxl=12000):
    out, start = [], 0
    while start < maxl:
        r = api("/backtests/read/log", {"projectId": CLOUD_ID, "backtestId": bid, "start": start, "end": start+200, "query": ""})
        ch = r.get("logs") or []; out += ch
        if len(ch) < 200: break
        start += 200
    return out

def parse_trades(bid):
    """Lida com CTRADE| (compacto) E com >>>CSV_START (full, p/ <=70 trades)."""
    logs = fetch_logs(bid)
    # tenta CTRADE
    hdr = next((l for l in logs if "CTRADEHDR|" in l), None)
    if hdr:
        cols = hdr.split("CTRADEHDR|", 1)[1].split("|")[0].split(",")
        rows = [dict(zip(cols, l.split("CTRADE|", 1)[1].split(","))) for l in logs if "CTRADE|" in l]
        if rows: return rows
    # senão, bloco CSV
    def strip_ts(l):
        p = l.split(" ", 2); return p[2] if len(p) == 3 and p[0][:2] == "20" else l
    cl, cap = [], False
    for l in logs:
        s = strip_ts(l)
        if ">>>CSV_START" in l: cap = True; continue
        if cap and "," in s and ">>>" not in s: cl.append(s)
    return list(csvmod.DictReader(cl)) if cl else []

def f(x):
    try: return float(x)
    except Exception: return None

def main():
    sw = json.loads(SWEEP.read_text(encoding="utf-8")) if SWEEP.exists() else {}
    mb = sw.get("ibfly_d30_minchk", {}).get("backtestId")
    hb = sw.get("ibfly_dte30", {}).get("backtestId")
    if not mb: print("ibfly_d30_minchk sem backtestId — rode o --minchk antes."); return
    mins = parse_trades(mb)
    if not mins: print(f"minuto {mb}: sem trades (rodando/rate-limit?)."); return
    hrs = parse_trades(hb) if hb else []
    # hourly: open_date -> spread (credit_mid - credit_cons)
    H = {}
    for r in hrs:
        cm, cc = f(r.get("credit_mid")), f(r.get("credit_cons"))
        if cm is not None and cc is not None: H[r["open_date"]] = (cm - cc, f(r.get("C")))
    print(f"=== IB d30 — spread de entrada (credit_mid - credit_cons) minuto vs horário (minuto n={len(mins)}) ===")
    print(f"{'data':<12}{'C(min)':>8}{'sp_HORA':>9}{'sp_MIN':>9}{'match':>7}")
    pair = []
    for r in mins:
        od = r["open_date"]; cm, cc = f(r.get("credit_mid")), f(r.get("credit_cons"))
        if cm is None or cc is None: continue
        spm = cm - cc; h = H.get(od)
        same = "—"
        if h:
            sph, Ch = h; same = "✓" if (Ch and f(r.get("C")) and abs(Ch-f(r.get("C"))) < 1) else "✗"
            if same == "✓": pair.append((sph, spm))
            print(f"{od:<12}{f(r.get('C')) or 0:>8.0f}{sph:>9.0f}{spm:>9.0f}{same:>7}")
    if pair:
        mh, mm = st.median([a for a,_ in pair]), st.median([b for _,b in pair])
        print(f"\nMesma estrutura (n={len(pair)}): spread HORÁRIO mediana ${mh:.0f} vs MINUTO ${mm:.0f}"
              f"  ->  horário = {mh/mm:.1f}x o minuto" if mm else "")
        print("VEREDITO: minuto << horário => cons horário INFLADO (near-ATM) -> edge real perto do mid.")
        print("          minuto ≈ horário => spread real -> usar fill sensitivity 25-50%.")
    else:
        print("\n(sem datas de estrutura idêntica p/ comparar — ver tabela acima)")

if __name__ == "__main__":
    main()
