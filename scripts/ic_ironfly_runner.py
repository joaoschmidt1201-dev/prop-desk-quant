"""
===============================================================================
 IC 0DTE + IRON FLY 0DTE RUNNER — troca a engine cloud entre cenários
===============================================================================
 Reusa os helpers do batman_sweep (API, wait_for, do_scenario style). Pra cada
 cenário: copia a engine certa pra cloud project, push, run, espera, grava bid.
 Idempotente: pula tags já com runtime; adota runs com bid sem runtime.

 Cenários (ordem):
   IC0DTE        — hold (sem stop)
   IC0DTE_stop   — stop ao tocar 2x crédito (perda max = 1x crédito)
   IF0DTE        — Iron Fly hold
   IF0DTE_tp10   — TP a 10% do crédito + stop centro±EM
   IF0DTE_tp20   — TP a 20% do crédito + stop centro±EM
   IF0DTE_tp30   — TP a 30% do crédito + stop centro±EM
===============================================================================
"""
from __future__ import annotations
import sys, shutil
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import batman_sweep as bs   # reusa: api, wait_for, wait_node_free, run, parse_bid, write_config, load_results, save_results

IC_ENGINE = REPO / "backtests/quantconnect/iron_condor_0dte.py"
IF_ENGINE = REPO / "backtests/quantconnect/iron_fly_0dte.py"
CLOUD_MAIN = bs.WORKSPACE / bs.PROJECT / "main.py"

SPAN = {"start_date": "2022-06-20", "end_date": "2026-05-13"}

# (tag, engine_path, full_params)
SCENARIOS = [
    ("IC0DTE",       IC_ENGINE, {**SPAN, "stop_close": "none"}),
    ("IC0DTE_stop",  IC_ENGINE, {**SPAN, "stop_close": "on"}),
    ("IF0DTE",       IF_ENGINE, {**SPAN}),                                                      # hold
    ("IF0DTE_stop",  IF_ENGINE, {**SPAN, "stop_close": "on"}),                                  # só stop @ centro±EM
    ("IF0DTE_tp10",  IF_ENGINE, {**SPAN, "tp_close_frac": "0.10", "stop_close": "on"}),         # Doc rule: TP 10% + stop
    ("IF0DTE_tp20",  IF_ENGINE, {**SPAN, "tp_close_frac": "0.20", "stop_close": "on"}),
    ("IF0DTE_tp30",  IF_ENGINE, {**SPAN, "tp_close_frac": "0.30", "stop_close": "on"}),
]

current_engine = {"path": None}

def ensure_engine(engine_path):
    if current_engine["path"] != engine_path:
        shutil.copy(str(engine_path), str(CLOUD_MAIN))
        current_engine["path"] = engine_path
        print(f"[engine] {engine_path.name} -> cloud project", flush=True)

def do_one(tag, params):
    print(f"\n===== {tag} =====\n{params}", flush=True)
    bs.write_config(params)
    p = bs.run(["lean", "cloud", "push", "--project", bs.PROJECT])
    if p.returncode != 0:
        return {"params": params, "error": "push:" + (p.stderr or "")[-300:]}
    bs.wait_node_free()
    bid, out = None, ""
    for attempt in range(5):
        b = bs.run(["lean", "cloud", "backtest", bs.PROJECT, "--name", tag])
        out = (b.stdout or "") + (b.stderr or "")
        bid = bs.parse_bid(out)
        if bid: break
        print(f"  [{tag}] sem bid (tent {attempt+1}) — espera 90s", flush=True)
        import time; time.sleep(90)
    if not bid:
        return {"params": params, "error": "no-bid:" + out[-400:]}
    rs = bs.wait_for(bid)
    print(f"[ok] {tag} -> Net {(rs or {}).get('Net Profit','?')} | {bid}", flush=True)
    return {"params": params, "backtestId": bid, "runtime": rs}

def main():
    res = bs.load_results()
    for tag, engine, params in SCENARIOS:
        cur = res.get(tag, {})
        if cur.get("runtime") and not (cur.get("runtime") or {}).get("_error"):
            print(f"[skip] {tag}", flush=True); continue
        ensure_engine(engine)
        if cur.get("backtestId"):
            print(f"[adopt] {tag} {cur['backtestId']}", flush=True)
            rs = bs.wait_for(cur["backtestId"])
            res[tag] = {**cur, "runtime": rs}; bs.save_results(res)
            print(f"[ok] {tag} -> Net {(rs or {}).get('Net Profit','?')}", flush=True)
            continue
        res[tag] = {**params, **do_one(tag, {**params, "run_tag": tag})}
        bs.save_results(res)
    print("\n===== IC + IRON FLY COMPLETO =====", flush=True)

if __name__ == "__main__":
    main()
