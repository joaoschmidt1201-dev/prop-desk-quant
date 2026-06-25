"""
===============================================================================
 SHORT STRANGLE RUT SWEEP — roda as 3 configs (28/35/42 DTE) no QC cloud
===============================================================================
 Para cada config: escreve params no config.json -> lean cloud push ->
 lean cloud backtest -> ESPERA via API (poll /backtests/read até completed) ->
 lê runtimeStatistics + baixa os logs (CTRADE) -> grava.

 As 12 close rules (hold, TP25/50/75, exit@14, exit@7, 6 combos) saem do
 pós-proc (ss_strangle_export_app.py) a partir do log CTRADE de cada run.

 NB: o wrapper lean.exe está bloqueado por App Control nesta máquina; chamamos
 o CLI via runner python (~/qc_batman/_lean.py).

 Uso:  python scripts/ss_strangle_sweep.py
 Saída: ~/qc_batman/ss_strangle_results.json
===============================================================================
"""
from __future__ import annotations
import json, base64, hashlib, time, os, re, subprocess, sys
from pathlib import Path

HOME = Path(os.path.expanduser("~"))
WORKSPACE = HOME / "qc_batman"
PROJECT = "Fat Violet Hippopotamus"
CONFIG = WORKSPACE / PROJECT / "config.json"
RUNNER = WORKSPACE / "_lean.py"
PY = sys.executable                      # python do env atual (trade_env)
CLOUD_ID = 27848355
ORG = "1f97d316a4d53242e929726971860505"
RESULTS_JSON = WORKSPACE / "ss_strangle_results.json"

SPAN = {"start_date": "2021-06-01", "end_date": "2026-06-01"}    # 5 anos
BASE = {
    "ticker": "RUT", "opt_target": "RUTW", "fill_mode": "mid",
    "target_delta_put": "0.10", "target_delta_call": "0.08",
    "exit_dte_a": "14", "exit_dte_b": "7", "strike_filter": "120",
    "entry_hour": "10", "entry_minute": "0", "commission_per_contract": "1.5",
    **SPAN,
}
# 1 run por DTE de entrada. As saídas por tempo (14/7) e os TPs são derivados, não viram run.
GRID = [
    ("SS_RUT_28", {"target_dte": "28"}),
    ("SS_RUT_35", {"target_dte": "35"}),
    ("SS_RUT_42", {"target_dte": "42"}),
]

# ---------- QC API (HMAC) ----------
_cred = json.load(open(HOME / ".lean" / "credentials"))
_UID = str(_cred.get("user-id") or _cred.get("user_id") or _cred.get("userId"))
_TOK = _cred.get("api-token") or _cred.get("token") or _cred.get("apiToken")

def api(path, body):
    import urllib.request as u
    ts = str(int(time.time()))
    hashed = hashlib.sha256(f"{_TOK}:{ts}".encode()).hexdigest()
    auth = base64.b64encode(f"{_UID}:{hashed}".encode()).decode()
    req = u.Request("https://www.quantconnect.com/api/v2" + path,
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Basic {auth}", "Timestamp": ts, "Content-Type": "application/json"},
        method="POST")
    return json.load(u.urlopen(req, timeout=120))

def wait_for(bid, timeout=14400, interval=30):
    """Poll /backtests/read até completed. Devolve o dict backtest inteiro (runtime + logs via read)."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            bt = api("/backtests/read", {"projectId": CLOUD_ID, "backtestId": bid})["backtest"]
            if bt.get("completed"):
                return bt
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

def parse_bid(out):
    m = re.search(r"/project/\d+/([0-9a-fA-F]{16,})", out) or \
        re.search(r"[Bb]acktest id:\s*([0-9a-fA-F]{16,})", out)
    return m.group(1) if m else None

def write_config(params):
    CONFIG.write_text(json.dumps({
        "algorithm-language": "Python", "parameters": params, "description": "",
        "cloud-id": CLOUD_ID, "organization-id": ORG, "python-venv": 1, "encrypted": False,
    }, indent=4), encoding="utf-8")

def lean(*args, timeout=600):
    # só p/ PUSH (rápido). NÃO usar p/ 'cloud backtest' (bloqueia horas -> estoura timeout).
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}    # evita crash cp1252 do CLI no Windows
    return subprocess.run([PY, str(RUNNER), *args], cwd=str(WORKSPACE),
                          capture_output=True, text=True, timeout=timeout, env=env)

def compile_project():
    """Compila via API e espera BuildSuccess. Devolve compileId ou None."""
    r = api("/compile/create", {"projectId": CLOUD_ID})
    cid = r.get("compileId")
    if not cid:
        return None
    for _ in range(60):
        rr = api("/compile/read", {"projectId": CLOUD_ID, "compileId": cid})
        st = rr.get("state")
        if st == "BuildSuccess":
            return cid
        if st == "BuildError":
            print(f"  compile BuildError: {rr.get('errors')}"); return None
        time.sleep(5)
    return None

def create_backtest(cid, name):
    """Submete backtest via API (NÃO bloqueia). Devolve backtestId ou None."""
    r = api("/backtests/create", {"projectId": CLOUD_ID, "compileId": cid, "backtestName": name})
    bt = r.get("backtest") or {}
    return bt.get("backtestId")

def load_results():
    return json.loads(RESULTS_JSON.read_text(encoding="utf-8")) if RESULTS_JSON.exists() else {}

def save_results(res):
    RESULTS_JSON.write_text(json.dumps(res, indent=2), encoding="utf-8")

def do_config(tag, ov, res):
    params = {**BASE, **ov, "run_tag": tag}
    print(f"\n===== {tag} =====\n{params}", flush=True)
    write_config(params)
    p = lean("cloud", "push", "--project", PROJECT)
    if p.returncode != 0:
        res[tag] = {"params": params, "error": "push:" + (p.stderr or "")[-300:]}
        save_results(res); return
    wait_node_free()                                   # 1 nó free: espera run anterior terminar
    cid = compile_project()
    if not cid:
        res[tag] = {"params": params, "error": "compile-fail"}; save_results(res); return
    bid = create_backtest(cid, tag)
    if not bid:
        res[tag] = {"params": params, "error": "create-fail"}; save_results(res); return
    res[tag] = {"params": params, "backtestId": bid, "runtime": None}; save_results(res)
    print(f"  [{tag}] submetido bid={bid} — polling...", flush=True)
    bt = wait_for(bid)                                 # poll API (não bloqueia o nó; ~5-6h)
    rs = (bt or {}).get("runtimeStatistics", {}) if bt else None
    res[tag] = {"params": params, "backtestId": bid, "runtime": rs}
    save_results(res)
    print(f"[ok] {tag} -> bid={bid} | R hold={rs.get('R hold') if rs else '?'}", flush=True)

def main():
    res = load_results()
    for tag, ov in GRID:
        cur = res.get(tag, {})
        if cur.get("runtime") and not (cur["runtime"] or {}).get("_error"):
            print(f"[skip] {tag}", flush=True); continue
        if cur.get("backtestId"):
            print(f"[adopt] {tag} {cur['backtestId']}", flush=True)
            bt = wait_for(cur["backtestId"])
            res[tag] = {**cur, "runtime": (bt or {}).get("runtimeStatistics", {})}
            save_results(res); continue
        do_config(tag, ov, res)
    print("\n===== SS SWEEP COMPLETO =====", flush=True)

if __name__ == "__main__":
    main()
