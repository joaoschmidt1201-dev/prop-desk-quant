"""
INVERSE BUTTERFLY EXPORT APP — CTRADE (QC log) -> trades.csv + daily.csv por (DTE × width).
Só os configs VERIFICADOS 100% completos no log (7/28/45 DTE; 1/14 ficam p/ chunked).
Cada (DTE,width) vira reports/ibfly_backtest_app/d{dte}_w{width}/ com:
  - trades.csv: 1 linha/trade, info de entrada + P&L por close-rule (mid):
      pnl_usd = HOLD; pnl_tp25/50/75; pnl_exit{d} (DTE-restante)
  - daily.csv: 2 linhas/trade (abertura + settle) p/ a curva.
Uso: python scripts/ibfly_export_app.py
"""
from __future__ import annotations
import json, base64, hashlib, time, os, csv, sys
import datetime as dt
from pathlib import Path
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

REPO = Path(__file__).resolve().parent.parent
HOME = Path(os.path.expanduser("~")); CLOUD_ID = 27848355
SWEEP = REPO / "reports" / "inverse_butterfly" / "sweep_ibfly.json"
OUT = REPO / "reports" / "ibfly_backtest_app"; OUT.mkdir(parents=True, exist_ok=True)

# SINGLE (n<250): esquema de tags UNIFORME ibre_d{DTE}_w{W} (re-run com tp_dte+tp_hour).
# 28 e 45 DTE × 6 larguras. Os chunked (1/4/7/14 DTE) saem pelo ibfly_merge_chunks.py.
_W6 = ["0.15", "0.25", "0.40", "0.50", "0.60", "0.75"]
CONFIGS = [(d, w, f"ibre_d{d}_w{w}") for d in (28, 45) for w in _W6]

_cred = json.load(open(HOME / ".lean" / "credentials"))
_UID = str(_cred.get("user-id") or _cred.get("user_id")); _TOK = _cred.get("api-token") or _cred.get("token")

def api(path, body):
    import urllib.request
    ts = str(int(time.time())); h = hashlib.sha256(f"{_TOK}:{ts}".encode()).hexdigest()
    auth = base64.b64encode(f"{_UID}:{h}".encode()).decode()
    req = urllib.request.Request("https://www.quantconnect.com/api/v2" + path, data=json.dumps(body).encode(),
        headers={"Authorization": f"Basic {auth}", "Timestamp": ts, "Content-Type": "application/json"}, method="POST")
    return json.load(urllib.request.urlopen(req, timeout=120))

def parse_ctrade(bid, tries=5):
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

def runtime_n(sw, tag):
    import re
    m = re.search(r"n=(\d+)", (sw.get(tag, {}).get("runtime") or {}).get("n / dte / W", ""))
    return int(m.group(1)) if m else None

def export(dte, width, tag, bid, sw):
    recs = parse_ctrade(bid)
    if not recs:
        print(f"[d{dte}_w{width}] SEM CTRADE — pula"); return None
    rn = runtime_n(sw, tag)
    if rn and len(recs) < rn:
        print(f"[d{dte}_w{width}] ⚠️ TRUNCADO ({len(recs)}/{rn}) — PULA (não subir incompleto)"); return None
    exit_ds = sorted({int(c[1:].split("_")[0]) for c in recs[0] if c.startswith("x") and c.endswith("_m")}, reverse=True)
    rows, daily = [], []
    for r in recs:
        od = r["open_date"]; hold = f(r["hold_net_mid"]) or 0.0
        cred = f(r.get("credit_mid")) or 0.0
        def eff(col):
            v = f(r.get(col)); return round(v, 2) if v is not None else round(hold, 2)
        def tp_target(tp):
            # ANTI-FANTASMA: uma ordem-limite de TP a tp% do crédito EXECUTA NO ALVO (tp%*crédito),
            # NÃO no pico do MTM (que vinha de quote horário stale -> ganho > crédito = impossível).
            return round(tp / 100.0 * cred, 2)
        def tp_hit(tp):
            return f(r.get(f"tp{tp}_m")) is not None   # MTM gravado = TP foi atingido em algum momento
        def composite(tp, exit_n):
            # "TP tp% senão Exit exit_n DTE" — EXATA via tp_dte. TP fecha NO ALVO (tp_target), não no MTM.
            tpd = f(r.get(f"tp{tp}_d"))
            if tp_hit(tp) and tpd is not None and tpd >= exit_n:
                return tp_target(tp)
            return eff(f"x{exit_n}_m")
        def composite_noon(tp):
            # "TP tp% senão Exit 12:00 ET (noon)" — p/ 1DTE. TP fecha NO ALVO.
            tpd = f(r.get(f"tp{tp}_d")); tph = f(r.get(f"tp{tp}_h"))
            if tp_hit(tp) and tpd is not None and (tpd > 0 or (tpd == 0 and tph is not None and tph < 12)):
                return tp_target(tp)
            return eff("e12_m")
        row = {
            "trade_date": od, "exp_date": r["expiry_date"], "underlying": "SPX",
            "dte_entry": int(f(r["dte_real"]) or dte), "width_sigma": width, "structure": "Inverse Butterfly 1-2-1 (calls)",
            "spot_entry": f(r["S_entry"]), "spot_exit": f(r["S_settle"]),
            "call_atm": f(r["C"]), "call_lo": f(r["Clo"]), "call_up": f(r["Cup"]),
            "total_credit": round(f(r["credit_mid"]) or 0, 2),
            "vix_entry": f(r["vix"]),
            "iv_atm_pct": round((f(r["atm_iv"]) or 0)*100, 2),
            "expected_move": round(f(r["sigma"]) or 0, 1),
            "pnl_usd": round(hold, 2),
            # TP isolado: sai NO ALVO (tp%*crédito) se atingido; senão segura até o vencimento (hold).
            "pnl_tp25": tp_target(25) if tp_hit(25) else round(hold, 2),
            "pnl_tp50": tp_target(50) if tp_hit(50) else round(hold, 2),
            "pnl_tp75": tp_target(75) if tp_hit(75) else round(hold, 2),
            "result": "WIN" if hold > 0 else "LOSS", "exit_method": "expiration",
            "mfe": f(r.get("mfe")), "mae": f(r.get("mae")),
        }
        for d in exit_ds:
            row[f"pnl_exit{d}"] = eff(f"x{d}_m")
        # regra composta "TP X% senão Exit N DTE" (EXATA via tp_dte) — uma coluna por (TP, exit)
        for tp in (25, 50, 75):
            for d in exit_ds:
                row[f"pnl_tp{tp}_exit{d}"] = composite(tp, d)
        # 1DTE (sem exits por DTE): regra composta "TP X% senão Exit 12:00 ET (noon)"
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
    print(f"[d{dte}_w{width}] {len(rows)} trades | HOLD net ${net:,.0f} | exits {exit_ds} -> {d.name}")
    return len(rows)

def _throttled(sw):
    """1 chamada-teste gentil: throttle ativo se vier vazio/erro."""
    try:
        bid = sw.get("ibfly_dte7", {}).get("backtestId")
        r = api("/backtests/read/log", {"projectId": CLOUD_ID, "backtestId": bid, "start": 0, "end": 5, "query": ""})
        return not (r.get("logs"))
    except Exception:
        return True

def main():
    sw = json.loads(SWEEP.read_text(encoding="utf-8"))
    import re
    def rn(tag):
        m = re.search(r"n=(\d+)", (sw.get(tag, {}).get("runtime") or {}).get("n / dte / W", "")); return int(m.group(1)) if m else 0
    # ALVO = só os baixáveis (n<=249; acima trunca no log do free tier -> ficam p/ chunked re-run)
    target = [(dte, w, tag) for (dte, w, tag) in CONFIGS if rn(tag) <= 249]
    def have(dte, w): return (OUT / f"d{dte}_w{w}" / "trades.csv").exists()
    def done(): return all(have(dte, w) for dte, w, _ in target)
    # LOOP: cada janela de throttle libera ~4 configs; repete até completar os baixáveis (ou ~12 ciclos).
    for outer in range(12):
        if done():
            break
        cleared = False
        for a in range(16):
            if not _throttled(sw):
                cleared = True; break
            print(f"[poll {outer+1}.{a+1}] rate-limit do QC ativo — espera 40min", flush=True); time.sleep(2400)
        if not cleared:
            print("[poller] rate-limit persistiu >10h — parando este ciclo."); break
        print(f"[ciclo {outer+1}] rate-limit LIVRE — baixando o que der nesta janela...", flush=True)
        for dte, width, tag in CONFIGS:
            if have(dte, width):
                continue
            bid = sw.get(tag, {}).get("backtestId")
            if not bid:
                continue
            export(dte, width, tag, bid, sw)
            time.sleep(20)
        n = sum(1 for dte, w, _ in target if have(dte, w))
        print(f"[ciclo {outer+1}] baixáveis prontos: {n}/{len(target)}", flush=True)
    n = sum(1 for dte, w, _ in target if have(dte, w))
    trunc = [(dte, w) for dte, w, tag in CONFIGS if rn(tag) > 249]
    print(f"\n=== FIM: baixáveis {n}/{len(target)} prontos | truncados (chunking): {trunc} ===")

if __name__ == "__main__":
    main()
