"""
INVERSE BUTTERFLY 1-2-1 — fila QC cloud (clone do burrito_sweep). API-only (lean CLI bloqueado).
  python scripts/inverse_butterfly_sweep.py --smoke      # 1 mês (valida motor)
  python scripts/inverse_butterfly_sweep.py --ref        # 30 DTE w0.15σ full-span (replica o tasty)
  python scripts/inverse_butterfly_sweep.py --axis=dte   # 1/4/7/15/30/45 DTE
  python scripts/inverse_butterfly_sweep.py --axis=width # 0.15/0.25/0.40 σ
Saída: reports/inverse_butterfly/{sweep_ibfly.json, master.csv}
"""
from __future__ import annotations
import json, base64, hashlib, time, os, sys, csv
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOME = Path(os.path.expanduser("~"))
ALGO_SRC = REPO / "backtests" / "quantconnect" / "inverse_butterfly_v1.py"
CLOUD_ID = 27848355
OUT = REPO / "reports" / "inverse_butterfly"; OUT.mkdir(parents=True, exist_ok=True)
SWEEP_JSON = OUT / "sweep_ibfly.json"; MASTER = OUT / "master.csv"
FULL = {"start_date": "2021-01-01", "end_date": "2026-06-08"}

def _cell(tag, **kw): return (tag, kw)

def q_smoke():
    # 4 meses: deixa trades de 30 DTE settlarem (entra jun-set, expira até meados out) + pega ago/2024
    return [_cell("ibfly_smoke", dte="30", width_sigma="0.15", start_date="2024-06-01", end_date="2024-10-15")]
def q_ref():
    return [_cell("ibfly_d30_w0.15", dte="30", width_sigma="0.15", **FULL)]
def q_axis(ax):
    out = []
    if ax == "dte":
        for d in ("1", "4", "7", "15", "30", "45"):
            wd = "all" if d in ("1", "4") else "4"
            out.append(_cell(f"ibfly_dte{d}", dte=d, width_sigma="0.15", entry_weekday=wd, **FULL))
    elif ax == "width":
        for w in ("0.15", "0.25", "0.40"):
            out.append(_cell(f"ibfly_w{w}", dte="30", width_sigma=w, **FULL))
    return out

# ───────── RE-RUN COMPLETO (motor c/ tp_dte+tp_hour) — esquema de tags UNIFORME ibre_d{DTE}_w{W} ─────────
# label DTE do app -> (target_dte do motor, entry_weekday). 14->15, 28->30 (motor mira sexta + |dte-target|).
_IB_DTE = {1: ("1", "all"), 4: ("4", "0"), 7: ("7", "4"), 14: ("15", "4"), 28: ("30", "4"), 45: ("45", "4")}
_IB_W6 = ["0.15", "0.25", "0.40", "0.50", "0.60", "0.75"]
# grid (decisão João): swing 4/7/14/45 + 28 com 6 larguras; 1DTE só 0.15/0.25.
_IB_GRID = {1: ["0.15", "0.25"], 4: _IB_W6, 7: _IB_W6, 14: _IB_W6, 28: _IB_W6, 45: _IB_W6}
_SPLIT2 = "2023-07-01"
_WIN6 = ["2021-01-01", "2021-12-31", "2022-12-31", "2023-12-31", "2024-12-31", "2025-12-31", "2026-06-08"]

def _ibcell(dte_label, w, suffix="", **dates):
    mdte, wd = _IB_DTE[dte_label]
    return _cell(f"ibre_d{dte_label}_w{w}{suffix}", dte=mdte, width_sigma=w, entry_weekday=wd, **dates)

def q_reapp():
    # SINGLE (n<250): 28 e 45 DTE, 6 larguras. Cabem inteiros no log -> 1 run cada.
    out = []
    for d in (28, 45):
        for w in _IB_GRID[d]:
            out.append(_ibcell(d, w, **FULL))
    return out

def q_chunk():
    # CHUNKED em 2 metades (4/7/14 DTE, 6 larguras): n perto/acima de 250 -> metade cabe no log; merge concatena.
    A = {"start_date": "2021-01-01", "end_date": _SPLIT2}
    B = {"start_date": _SPLIT2, "end_date": "2026-06-08"}
    out = []
    for d in (4, 7, 14):
        for w in _IB_GRID[d]:
            out.append(_ibcell(d, w, "_h1", **A))
            out.append(_ibcell(d, w, "_h2", **B))
    return out

def q_chunk1():
    # 1DTE diário (n~1239/largura) -> 6 janelas anuais por largura (0.15 e 0.25).
    out = []
    for w in _IB_GRID[1]:
        for i in range(len(_WIN6) - 1):
            out.append(_ibcell(1, w, f"_c{i+1}", start_date=_WIN6[i], end_date=_WIN6[i+1]))
    return out

def q_minchk():
    # spot-check de spread em MINUTO (aprendizado PL5): near-ATM -> cons horário inflado? Comparar
    # spread de entrada minuto vs horário no dte30 (mesma janela 2025). strikes estreitos p/ velocidade.
    return [_cell("ibfly_d30_minchk", dte="30", width_sigma="0.15", entry_weekday="4",
                  data_res="minute", strike_half="60", start_date="2025-01-01", end_date="2025-12-31")]

def q_best():
    # caca do melhor cenario: width largo (alavanca clara) x DTE semanal. TP sai de graca (record-and-derive).
    out = []
    for w in ("0.50", "0.60", "0.75"):                       # acha o pico de width (em 30 DTE)
        out.append(_cell(f"ibfly_w{w}", dte="30", width_sigma=w, entry_weekday="4", **FULL))
    for d in ("15", "45"):                                    # o melhor width (0.40) em outros DTEs semanais
        out.append(_cell(f"ibfly_d{d}_w0.40", dte=d, width_sigma="0.40", entry_weekday="4", **FULL))
    return out

def q_weekly():
    # CORRECAO (Joao, spec confirmada): 4 DTE = SEGUNDA->SEXTA (entry_weekday="0"=segunda), fechar
    # sexta na ABERTURA (snapshot e_open). 1 DTE fica DIARIO (ja correto). Roda 0.15 e 0.40 sigma.
    return [_cell("ibfly_dte4_mon",     dte="4", width_sigma="0.15", entry_weekday="0", **FULL),
            _cell("ibfly_dte4_mon_w40", dte="4", width_sigma="0.40", entry_weekday="0", **FULL)]

def q_best2():
    # completa a matriz DTE x sweet-spot-width (0.50/0.60s = pico no 30DTE) p/ achar o otimo absoluto.
    out = []
    for d in ("7", "15", "45"):
        for w in ("0.50", "0.60"):
            out.append(_cell(f"ibfly_d{d}_w{w}", dte=d, width_sigma=w, entry_weekday="4", **FULL))
    out.append(_cell("ibfly_dte4_mon_w60", dte="4", width_sigma="0.60", entry_weekday="0", **FULL))
    return out

def build_queue(args):
    if "--reapp" in args:  return q_reapp()
    if "--smoke" in args:  return q_smoke()
    if "--minchk" in args: return q_minchk()
    if "--chunk1" in args: return q_chunk1()
    if "--chunk" in args:  return q_chunk()
    if "--best" in args:   return q_best()
    if "--best2" in args:  return q_best2()
    if "--weekly" in args: return q_weekly()
    if "--ref" in args:    return q_ref()
    ax = next((a.split("=", 1)[1] for a in args if a.startswith("--axis=")), None)
    return q_axis(ax) if ax else q_ref()

_cred = json.load(open(HOME / ".lean" / "credentials"))
_UID = str(_cred.get("user-id") or _cred.get("user_id")); _TOK = _cred.get("api-token") or _cred.get("token")

def api(path, body):
    import urllib.request
    ts = str(int(time.time())); hashed = hashlib.sha256(f"{_TOK}:{ts}".encode()).hexdigest()
    auth = base64.b64encode(f"{_UID}:{hashed}".encode()).decode()
    req = urllib.request.Request("https://www.quantconnect.com/api/v2" + path, data=json.dumps(body).encode(),
        headers={"Authorization": f"Basic {auth}", "Timestamp": ts, "Content-Type": "application/json"}, method="POST")
    return json.load(urllib.request.urlopen(req, timeout=120))

def wait_for(bid, timeout=14000, interval=30):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            bt = api("/backtests/read", {"projectId": CLOUD_ID, "backtestId": bid})["backtest"]
            if bt.get("error") or bt.get("stacktrace"):
                return {"_error": str(bt.get("error") or bt.get("stacktrace"))[:400]}
            if bt.get("completed"):
                return bt.get("runtimeStatistics", {})
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

def wait_node_free(timeout=16000):
    t0 = time.time()
    while node_busy() and (time.time() - t0) < timeout:
        print("  nó ocupado — espera 60s...", flush=True); time.sleep(60)

def push_code():
    r = api("/files/update", {"projectId": CLOUD_ID, "name": "main.py", "content": ALGO_SRC.read_text(encoding="utf-8")})
    if r.get("errors"): raise RuntimeError(f"/files/update: {r.get('errors')}")
    print(f"[push] main.py <- {ALGO_SRC.name}", flush=True)

def compile_project(timeout=360):
    cid = api("/compile/create", {"projectId": CLOUD_ID}).get("compileId")
    if not cid: raise RuntimeError("compile/create falhou")
    t0 = time.time()
    while time.time() - t0 < timeout:
        cr = api("/compile/read", {"projectId": CLOUD_ID, "compileId": cid}); st = cr.get("state")
        if st == "BuildSuccess": print(f"[compile] {cid[:14]}… BuildSuccess", flush=True); return cid
        if st == "BuildError": raise RuntimeError(f"BuildError: {cr.get('errors')}")
        time.sleep(4)
    raise RuntimeError("compile timeout")

def create_backtest(name, params, compile_id):
    bc = api("/backtests/create", {"projectId": CLOUD_ID, "compileId": compile_id, "backtestName": name, "parameters": params})
    return (bc.get("backtest") or {}).get("backtestId")

def load_results(): return json.loads(SWEEP_JSON.read_text(encoding="utf-8")) if SWEEP_JSON.exists() else {}
def save_results(res):
    SWEEP_JSON.write_text(json.dumps(res, indent=2), encoding="utf-8")
    rows = [{"tag": t, "bid": r.get("backtestId", ""), "hold": (r.get("runtime") or {}).get("HOLD mid", ""),
             "exit7": (r.get("runtime") or {}).get("EXIT 7DTE", ""), "tp50": (r.get("runtime") or {}).get("TP 50%", ""),
             "real_vs_impl": (r.get("runtime") or {}).get("real vs impl", ""),
             "err": ((r.get("runtime") or {}).get("_error") or r.get("error", ""))} for t, r in res.items()]
    if rows:
        with open(MASTER, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

def do_scenario(tag, params, res, cid):
    print(f"\n===== {tag} =====\n{params}", flush=True)
    wait_node_free(); bid = None
    for att in range(5):
        try: bid = create_backtest(tag, params, cid)
        except Exception as e: print(f"  create erro: {str(e)[:140]}", flush=True)
        if bid: break
        print(f"  sem bid (tent {att+1}) — espera 60s", flush=True); time.sleep(60)
    if not bid:
        res[tag] = {"params": params, "error": "no-bid"}; save_results(res); return
    rs = wait_for(bid); res[tag] = {"params": params, "backtestId": bid, "runtime": rs}; save_results(res)
    print(f"[ok] {tag} -> HOLD {(rs or {}).get('HOLD mid','?')} | EXIT7 {(rs or {}).get('EXIT 7DTE','?')} | {bid}", flush=True)

def main():
    args = set(sys.argv[1:]); queue = build_queue(args)
    if "--dry" in args:
        print(f"Fila ({len(queue)}):"); [print(f"  {t:20} {o}") for t, o in queue]; return
    force = "--force" in args   # re-roda mesmo tags já OK (ex.: motor mudou -> precisa do tp_dte novo)
    push_code(); cid = compile_project(); res = load_results()
    for tag, ov in queue:
        cur = res.get(tag, {})
        if not force and cur.get("runtime") and not (cur["runtime"] or {}).get("_error"):
            print(f"[skip] {tag}", flush=True); continue
        do_scenario(tag, {**ov, "run_tag": tag}, res, cid)
    print("\n===== SWEEP IBFLY COMPLETO =====", flush=True)

if __name__ == "__main__":
    main()
