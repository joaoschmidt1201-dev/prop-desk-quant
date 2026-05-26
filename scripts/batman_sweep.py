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

# Run de diagnóstico já em curso (debit_search) — esperar terminar e usar como data-point.
WAIT_FIRST_BID = "1a10e12b12f3aef5d89d738338d85415"
WAIT_FIRST_TAG = "1DTE_debit_search"
WAIT_FIRST_PARAMS = {"structure": "1DTE", "placement_mode": "debit", "width_mode": "debit_search",
                     "symmetry": "sym", "start_date": "2022-06-20", "end_date": "2026-05-13",
                     "run_tag": "1DTE_debit_sym"}

SPAN = {"start_date": "2022-06-20", "end_date": "2026-05-13"}
BASE = {"symmetry": "sym", "width_mode": "vix_table", **SPAN}

# (tag, overrides) — só eixos ESTRUTURAIS. VIX/close-rule/TP saem das runtime stats de cada run.
GRID = [
    ("1DTE_debit",    {"structure": "1DTE",           "placement_mode": "debit"}),
    ("1DTE_delta",    {"structure": "1DTE",           "placement_mode": "delta"}),
    ("0DTE_debit",    {"structure": "0DTE",           "placement_mode": "debit"}),
    ("0DTE_delta",    {"structure": "0DTE",           "placement_mode": "delta"}),
    ("wMonFri_debit", {"structure": "weekly_mon_fri", "placement_mode": "debit"}),
    ("wFriFri_debit", {"structure": "weekly_fri_fri", "placement_mode": "debit"}),
    ("1DTE_debit_search", {"structure": "1DTE", "placement_mode": "debit", "width_mode": "debit_search"}),
]

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
    b = run(["lean", "cloud", "backtest", PROJECT, "--name", tag])
    bid = parse_bid((b.stdout or "") + (b.stderr or ""))
    if not bid:
        res[tag] = {"params": params, "error": "no-bid:" + ((b.stdout or "") + (b.stderr or ""))[-400:]}; save_results(res); return
    rs = wait_for(bid)
    res[tag] = {"params": params, "backtestId": bid, "runtime": rs}
    save_results(res)
    print(f"[ok] {tag} -> Net {(rs or {}).get('Net Profit','?')} | {bid}", flush=True)

def main():
    res = load_results()
    # 1) aproveita o run de diagnóstico já em curso como o data-point debit_search
    if WAIT_FIRST_TAG not in res or not res[WAIT_FIRST_TAG].get("runtime"):
        print(f"esperando diag {WAIT_FIRST_BID} terminar...", flush=True)
        rs = wait_for(WAIT_FIRST_BID)
        res[WAIT_FIRST_TAG] = {"params": WAIT_FIRST_PARAMS, "backtestId": WAIT_FIRST_BID, "runtime": rs}
        save_results(res)
        print(f"[ok] {WAIT_FIRST_TAG} -> Net {(rs or {}).get('Net Profit','?')}", flush=True)
    # 2) grid faithful (nó já livre)
    for tag, ov in GRID:
        if tag in res and res[tag].get("runtime"):
            print(f"[skip] {tag}", flush=True); continue
        do_scenario(tag, {**BASE, **ov, "run_tag": tag}, res)
    print("\n===== SWEEP COMPLETO =====", flush=True)

if __name__ == "__main__":
    main()
