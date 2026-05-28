"""
===============================================================================
 BATMAN SWEEP — roda o grid de cenários no QC cloud SOZINHO (sequencial, B-MICRO)
===============================================================================
 Para cada cenário: escreve params no config.json -> lean cloud push ->
 lean cloud backtest -> ESPERA via API (poll /backtests/read até completed,
 imune a 502 do CLI) -> lê runtimeStatistics -> grava.

 Resiliente: pula cenário já concluído (results.json); segue se um falhar;
 espera o nó liberar (WAIT_FIRST) antes de começar.

 Agregados (net por VIX bucket, por ano, hold-vs-TP, WR, debito/width) vêm das
 RUNTIME STATISTICS que o motor cospe (único canal export-safe no tier não-inst.).

 Uso:  python scripts/batman_sweep.py
 Saída: ~/qc_batman/sweep_results.json  +  ~/qc_batman/sweep_results.md
===============================================================================
"""
from __future__ import annotations
import json, base64, hashlib, time, os, re, subprocess
from pathlib import Path

HOME = Path(os.path.expanduser("~"))
WORKSPACE = HOME / "qc_batman"
PROJECT = "Fat Violet Hippopotamus"
CONFIG = WORKSPACE / PROJECT / "config.json"
CLOUD_ID = 27848355
ORG = "1f97d316a4d53242e929726971860505"
RESULTS_JSON = WORKSPACE / "sweep_results.json"
RESULTS_MD = WORKSPACE / "sweep_results.md"

SPAN = {"start_date": "2022-06-20", "end_date": "2026-05-13"}
BASE = {"symmetry": "sym", "width_mode": "vix_table", **SPAN}

# 5 estruturas (ícones) × 6 variantes de placement/width. Tag = <icon>_<variant>.
# Eixos VIX / close-rule(TP) / dia-de-abertura saem das runtime stats + recon (não viram run).
STRUCTURES = [
    ("0DTE",    "0DTE"),
    ("1DTE",    "1DTE"),
    ("wMonFri", "weekly_mon_fri"),
    ("wFriFri", "weekly_fri_fri"),
    ("w21",     "weekly_fri_fri_21d"),
]
# variante -> overrides (além de structure). ernie = vix_table+debit; wNN = fixed; delta16 = delta 0.16
VARIANTS = [
    ("ernie",   {"placement_mode": "debit", "width_mode": "vix_table"}),
    ("w25",     {"placement_mode": "debit", "width_mode": "fixed", "fixed_width": "25"}),
    ("w30",     {"placement_mode": "debit", "width_mode": "fixed", "fixed_width": "30"}),
    ("w40",     {"placement_mode": "debit", "width_mode": "fixed", "fixed_width": "40"}),
    ("w50",     {"placement_mode": "debit", "width_mode": "fixed", "fixed_width": "50"}),
    ("delta16", {"placement_mode": "delta", "width_mode": "vix_table", "target_delta": "0.16"}),
]

# As 4 ernie das estruturas EXISTENTES já têm dado limpo (tags *_debit) -> NÃO re-roda.
# O grupo da API mapeia o label "Ernie VIX table" -> esses tags *_debit (ver _BATMAN_GROUPS).
EXISTING_ERNIE_TAG = {"0DTE": "0DTE_debit", "1DTE": "1DTE_debit",
                      "wMonFri": "wMonFri_debit", "wFriFri": "wFriFri_debit"}

# TP por-trade (req #4): close-rule %-over-débito EXECUTADA no motor. Cada (variante × nível)
# é um run próprio; o recon pega o fill exato do fechamento. Reaproveita runs antigos já no
# results (1DTE_debit_tp50/100/200). Falta o +150% e todos os outros.
TP_FRACS = [("tp50", "0.5"), ("tp100", "1.0"), ("tp150", "1.5"), ("tp200", "2.0")]

def _canon_tag(icon: str, vname: str) -> str:
    """Tag/pasta canônica da variante base (a que a API mapeia)."""
    if vname == "ernie":
        return EXISTING_ERNIE_TAG.get(icon, f"{icon}_ernie")   # w21 -> w21_ernie
    return f"{icon}_{vname}"

def _build_grid():
    """BASE (26 a rodar) + TP (30 variantes × 4 níveis = 120). Ordem: BASE primeiro
    (21DTE-ernie na frente), depois TP. Idempotente: o main() pula tags já com runtime."""
    first, w21_rest, others, tp = [], [], [], []
    for icon, struct in STRUCTURES:
        for vname, ov in VARIANTS:
            canon = _canon_tag(icon, vname)
            params = {"structure": struct, **ov}
            # ---- BASE (ernie das 4 existentes é pulada; reaproveita *_debit) ----
            if icon == "w21":
                (first if vname == "ernie" else w21_rest).append((canon, params))
            elif vname != "ernie":
                others.append((canon, params))
            # ---- TP: DESATIVADO (decisão João 2026-05-27). O agregado hold-vs-TP já vem das
            #      runtime stats de cada base; TP por-trade só nas vencedoras depois (poucos runs). ----
            for suf, frac in TP_FRACS:
                tp.append((f"{canon}_{suf}", {**params, "tp_close_frac": frac}))
    return first + w21_rest + others          # só os 26 BASE (tp fica fora da fila)

GRID = _build_grid()

# ---------- QC API (HMAC) ----------
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
    import urllib.request as u
    return json.load(u.urlopen(req, timeout=120))

def wait_for(bid, timeout=9000, interval=30):
    """Poll /backtests/read até completed. Imune a 502/transientes. Devolve runtimeStatistics ou None."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            bt = api("/backtests/read", {"projectId": CLOUD_ID, "backtestId": bid})["backtest"]
            if bt.get("completed"):
                return bt.get("runtimeStatistics", {})
            if (bt.get("error") or bt.get("stacktrace")):
                return {"_error": str(bt.get("error"))[:300]}
        except Exception:
            pass
        time.sleep(interval)
    return None

def node_busy():
    """True se há algum backtest 'In Progress' no projeto (tier free = 1 nó)."""
    try:
        r = api("/backtests/list", {"projectId": CLOUD_ID})
        return any("Progress" in (b.get("status") or "") for b in r.get("backtests", []))
    except Exception:
        return False

def wait_node_free(timeout=10800):
    t0 = time.time()
    while node_busy() and (time.time() - t0) < timeout:
        print("  nó ocupado — espera 60s...", flush=True)
        time.sleep(60)

def parse_bid(out):
    m = re.search(r"/project/\d+/([0-9a-fA-F]{16,})", out) or re.search(r"[Bb]acktest id:\s*([0-9a-fA-F]{16,})", out)
    return m.group(1) if m else None

def write_config(params):
    CONFIG.write_text(json.dumps({
        "algorithm-language": "Python", "parameters": params, "description": "",
        "cloud-id": CLOUD_ID, "organization-id": ORG, "python-venv": 1, "encrypted": False,
    }, indent=4), encoding="utf-8")

def run(cmd):
    return subprocess.run(cmd, cwd=str(WORKSPACE), capture_output=True, text=True, timeout=9000)

def load_results():
    return json.loads(RESULTS_JSON.read_text(encoding="utf-8")) if RESULTS_JSON.exists() else {}

def save_results(res):
    RESULTS_JSON.write_text(json.dumps(res, indent=2), encoding="utf-8")
    lines = ["# Batman Sweep — runtime stats por cenário\n"]
    for tag, r in res.items():
        rs = r.get("runtime", {}) or {}
        lines.append(f"## {tag}")
        lines.append(f"- params: `{r.get('params')}`  ·  backtestId: {r.get('backtestId')}")
        lines.append(f"- **Net {rs.get('Net Profit','?')} / Return {rs.get('Return','?')} / DD {rs.get('Drawdown','?')}**")
        order = [k for k in rs if k.startswith("NET ")] + [k for k in rs if k.startswith("M0 VIX")] \
                + [k for k in rs if k.startswith("M0 2")] + [k for k in ("debit_frac med", "width med") if k in rs]
        for k in order:
            lines.append(f"  - {k}: {rs[k]}")
        lines.append("")
    RESULTS_MD.write_text("\n".join(lines), encoding="utf-8")

def do_scenario(tag, params, res):
    print(f"\n===== {tag} =====\n{params}", flush=True)
    write_config(params)
    p = run(["lean", "cloud", "push", "--project", PROJECT])
    if p.returncode != 0:
        res[tag] = {"params": params, "error": "push:" + p.stderr[-300:]}; save_results(res); return
    wait_node_free()                              # tier free = 1 nó; espera run anterior/órfão terminar
    bid, out = None, ""
    for attempt in range(5):                      # retry: "Invalid credentials"/throttle é transitório
        b = run(["lean", "cloud", "backtest", PROJECT, "--name", tag])
        out = (b.stdout or "") + (b.stderr or "")
        bid = parse_bid(out)
        if bid:
            break
        print(f"  [{tag}] sem bid (tentativa {attempt+1}) — espera 90s", flush=True)
        time.sleep(90)
    if not bid:
        res[tag] = {"params": params, "error": "no-bid:" + out[-400:]}; save_results(res); return
    rs = wait_for(bid)
    res[tag] = {"params": params, "backtestId": bid, "runtime": rs}
    save_results(res)
    print(f"[ok] {tag} -> Net {(rs or {}).get('Net Profit','?')} | {bid}", flush=True)

def main():
    res = load_results()
    for tag, ov in GRID:
        cur = res.get(tag, {})
        if cur.get("runtime") and not (cur["runtime"] or {}).get("_error"):
            print(f"[skip] {tag}", flush=True); continue
        if cur.get("backtestId"):                 # run já submetido (interrompido/órfão) -> ADOTA
            print(f"[adopt] {tag} {cur['backtestId']}", flush=True)
            rs = wait_for(cur["backtestId"])
            res[tag] = {**cur, "runtime": rs}; save_results(res)
            print(f"[ok] {tag} -> Net {(rs or {}).get('Net Profit','?')}", flush=True)
            continue
        do_scenario(tag, {**BASE, **ov, "run_tag": tag}, res)
    print("\n===== SWEEP COMPLETO =====", flush=True)

if __name__ == "__main__":
    main()
