"""
===============================================================================
 PL5 / BWB 1-2-2 de PUTS — FILA (QC cloud, sequencial, free-tier 1 nó)
===============================================================================
 Espelho do jadelizard_sweep.py. Empurra pl5_bwb_v1.py p/ o projeto cloud (API,
 pois o lean CLI está bloqueado pelo Controle de Aplicativo do Windows), compila
 e roda a fila. Cada run = 1 backtest full-span HOLD; gestão (TP/SL/DIT) sai do
 per-trade compacto (CTRADE|) em pós-proc.

 Fila default (3 runs): target_dte = 21, 30, 45 — span 2021-06 → 2026-06.

 Uso:
   python scripts/pl5_sweep.py --validate     # 1 run curto (d30, jul/2024 c/ crash ago) p/ sanidade
   python scripts/pl5_sweep.py --dry          # lista a fila
   python scripts/pl5_sweep.py [--only=TAG]   # roda a fila full-span
 Saída: reports/pl5_bwb/{sweep_pl5.json, master_runs_pl5.csv}
===============================================================================
"""
from __future__ import annotations
import json, base64, hashlib, time, os, sys, csv
from pathlib import Path

REPO      = Path(__file__).resolve().parent.parent
HOME      = Path(os.path.expanduser("~"))
WORKSPACE = HOME / "qc_batman"
PROJECT   = "Fat Violet Hippopotamus"
ALGO_SRC  = REPO / "backtests" / "quantconnect" / "pl5_bwb_v1.py"
CLOUD_ID  = 27848355
ORG       = "1f97d316a4d53242e929726971860505"

OUT        = REPO / "reports" / "pl5_bwb"
OUT.mkdir(parents=True, exist_ok=True)
SWEEP_JSON = OUT / "sweep_pl5.json"
MASTER_CSV = OUT / "master_runs_pl5.csv"

FULL = {"start_date": "2021-06-01", "end_date": "2026-06-01"}

def _cell(tag, **kw):
    return (tag, kw)

def _full_queue():
    # CZ redirect 2026-06-16: saída ANTECIPADA (não hold), DTEs 21/28/45/60, delta 30/18/3 (só std —
    # João descartou a variante 29/17/3). Resolução HORÁRIA (swing; ~3-5× mais rápido que minuto).
    q = []
    for dte in (21, 28, 45, 60):
        q.append(_cell(f"pl5_d{dte}_std", target_dte=str(dte), **FULL))
    return q

def _long_queue():
    # CZ pediu (2026-06-23, p/ reunião amanhã): DTEs LONGOS 75/100/120. Mesma estrutura/deltas (30/18/3).
    # strike_lo ampliado: a perna -3Δ fica MUITO OTM em prazo longo (ex. 120 DTE alta-vol ~1600+pts) ->
    # -500 strikes cobre c/ folga. dte_exit_grid do motor já adapta (saídas em 90/75/60/45 restantes).
    q = []
    for dte in (75, 100, 120):
        q.append(_cell(f"pl5_d{dte}_std", target_dte=str(dte), strike_lo="-500", **FULL))
    return q

# janela curta de validação: jul/2024 (entra) -> expira meados de ago (pega o crash 05/08/2024)
VALIDATE = [_cell("pl5_validate_d30", target_dte="30",
                  start_date="2024-07-01", end_date="2024-08-23")]

# SPOT-CHECK de SPREAD (resp. ao CZ): roda d60 em MINUTO na janela dos outliers de spread horário
# (entradas nov/2025-fev/2026 c/ spreads 58/50/39pt em VIX calmo = suspeita de quote stale). Compara
# o spread de entrada (cons-mid) minuto vs horário nas mesmas datas -> prova se o -195k é artefato.
MINCHK = [_cell("pl5_d60_minchk", target_dte="60", data_res="minute", strike_lo="-200",
                start_date="2025-11-01", end_date="2026-04-30")]

QUEUE = _full_queue()

def params_for(tag, ov):
    return {**ov, "run_tag": tag}

# ---------- QC API (HMAC) — igual jadelizard_sweep ----------
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
    return json.load(urllib.request.urlopen(req, timeout=120))

def wait_for(bid, timeout=12000, interval=30):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            bt = api("/backtests/read", {"projectId": CLOUD_ID, "backtestId": bid})["backtest"]
            if bt.get("completed"):
                return bt.get("runtimeStatistics", {})
            if bt.get("error") or bt.get("stacktrace"):
                return {"_error": str(bt.get("error") or bt.get("stacktrace"))[:400]}
        except Exception:
            pass
        time.sleep(interval)
    return None

def node_busy():
    try:
        r = api("/backtests/list", {"projectId": CLOUD_ID})
        return any("Progress" in (b.get("status") or "") for b in r.get("backtests", []))
    except Exception:
        return False

def wait_node_free(timeout=14400):
    t0 = time.time()
    while node_busy() and (time.time() - t0) < timeout:
        print("  nó ocupado — espera 60s...", flush=True); time.sleep(60)

def push_code():
    content = ALGO_SRC.read_text(encoding="utf-8")
    r = api("/files/update", {"projectId": CLOUD_ID, "name": "main.py", "content": content})
    if r.get("errors"):
        raise RuntimeError(f"/files/update erro: {r.get('errors')}")
    print(f"[push] main.py <- {ALGO_SRC.name} (API)", flush=True)

def compile_project(timeout=360):
    cc = api("/compile/create", {"projectId": CLOUD_ID})
    cid = cc.get("compileId")
    if not cid:
        raise RuntimeError(f"compile/create falhou: {cc}")
    t0 = time.time()
    while time.time() - t0 < timeout:
        cr = api("/compile/read", {"projectId": CLOUD_ID, "compileId": cid})
        st = cr.get("state")
        if st == "BuildSuccess":
            print(f"[compile] {cid[:16]}… BuildSuccess", flush=True); return cid
        if st == "BuildError":
            raise RuntimeError(f"BuildError: {cr.get('errors')}")
        time.sleep(4)
    raise RuntimeError("compile timeout")

def create_backtest(name, params, compile_id):
    bc = api("/backtests/create", {"projectId": CLOUD_ID, "compileId": compile_id,
                                   "backtestName": name, "parameters": params})
    return (bc.get("backtest") or {}).get("backtestId")

def load_results():
    return json.loads(SWEEP_JSON.read_text(encoding="utf-8")) if SWEEP_JSON.exists() else {}

def save_results(res):
    SWEEP_JSON.write_text(json.dumps(res, indent=2), encoding="utf-8")
    rows = []
    for tag, r in res.items():
        rs = r.get("runtime") or {}
        rows.append({"tag": tag, "backtestId": r.get("backtestId", ""),
                     "net_hold": rs.get("NET M0 hold", ""),
                     "dte_med": rs.get("dte_real med", ""),
                     "cost_med": rs.get("entry_cost med", ""),
                     "error": (rs.get("_error") if isinstance(rs, dict) else "") or r.get("error", ""),
                     "params": json.dumps(r.get("params", {}))})
    if rows:
        with open(MASTER_CSV, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

def do_scenario(tag, params, res, compile_id):
    print(f"\n===== {tag} =====\n{params}", flush=True)
    wait_node_free()
    bid = None
    for attempt in range(5):
        try:
            bid = create_backtest(tag, params, compile_id)
        except Exception as e:
            print(f"  [{tag}] create erro: {str(e)[:150]}", flush=True)
        if bid:
            break
        print(f"  [{tag}] sem bid (tentativa {attempt+1}) — espera 60s", flush=True); time.sleep(60)
    if not bid:
        res[tag] = {"params": params, "error": "no-bid (create)"}; save_results(res); return
    rs = wait_for(bid)
    res[tag] = {"params": params, "backtestId": bid, "runtime": rs}
    save_results(res)
    print(f"[ok] {tag} -> hold {(rs or {}).get('NET M0 hold','?')} | {bid}", flush=True)

def main():
    args = set(sys.argv[1:])
    if "--validate" in args:   queue = VALIDATE
    elif "--minchk" in args:   queue = MINCHK
    elif "--long" in args:     queue = _long_queue()   # CZ: DTEs 75/100/120 (prioridade)
    else:                      queue = QUEUE
    if "--dry" in args:
        print(f"Fila ({len(queue)} runs):")
        for tag, ov in queue:
            print(f"  {tag:22} {ov}")
        return
    only = next((a.split("=", 1)[1] for a in args if a.startswith("--only=")), None)
    queue = [(t, o) for (t, o) in queue if (only is None or t == only)]
    push_code()
    compile_id = compile_project()
    res = load_results()
    for tag, ov in queue:
        cur = res.get(tag, {})
        if cur.get("runtime") and not (cur["runtime"] or {}).get("_error"):
            print(f"[skip] {tag}", flush=True); continue
        if cur.get("backtestId") and not cur.get("runtime"):
            print(f"[adopt] {tag} {cur['backtestId']}", flush=True)
            res[tag] = {**cur, "runtime": wait_for(cur["backtestId"])}; save_results(res); continue
        do_scenario(tag, params_for(tag, ov), res, compile_id)
    print("\n===== SWEEP PL5 COMPLETO =====", flush=True)

if __name__ == "__main__":
    main()
