"""
===============================================================================
 PL5 EXPORT APP — CTRADE| (QC log) -> trades.csv + daily.csv (1 pasta por DTE)
===============================================================================
 O PL5 roda em TRACKING SINTÉTICO (sem ordens) -> NÃO tem closedTrades. Logo a
 fonte por-trade é o CTRADE| compacto no log (via /backtests/read/log).

 Cada run (d21/d28/d45/d60) vira uma pasta reports/pl5_backtest_app/<tag>/ com:
   - trades.csv: 1 linha/trade com INFO DE ENTRADA (data, dte, strikes K1/K2/K3,
     spot, crédito/débito, VIX) + colunas de P&L por REGRA DE SAÍDA (mid):
       pnl_usd          = hold-to-expiry (settle)
       pnl_exitD (mid)  = sair com D DTE restantes  (D em 30/21/14/10/7/5/3)
   - daily.csv: 2 linhas/trade (abertura + fechamento) p/ a curva de equity.

 As regras de saída aplicáveis por DTE (D < dte_entry) viram o SELETOR no app
 (registry close_rules em apps/api/main.py).

 Uso:  python scripts/pl5_export_app.py
 Saída: reports/pl5_backtest_app/<tag>/{trades.csv, daily.csv}
===============================================================================
"""
from __future__ import annotations
import json, base64, hashlib, time, os, csv, math
import datetime as dt
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOME = Path(os.path.expanduser("~"))
CLOUD_ID = 27848355
SWEEP = REPO / "reports" / "pl5_bwb" / "sweep_pl5.json"
OUT = REPO / "reports" / "pl5_backtest_app"
OUT.mkdir(parents=True, exist_ok=True)

TAGS = ["pl5_d21_std", "pl5_d28_std", "pl5_d45_std", "pl5_d60_std",
        "pl5_d75_std", "pl5_d100_std", "pl5_d120_std"]   # + DTEs longos (CZ 2026-06-23)
EXIT_GRID = [90, 75, 60, 45, 30, 21, 14, 10, 7, 5, 3]   # DTE restantes (mid) — adaptado p/ longos
TP_LEVELS = [25, 50, 75, 100]                            # % de ref_profit (pico do tent) — colunas tp{L} no log

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

def fetch_log(bid, max_lines=40000):
    out, start = [], 0
    while start < max_lines:
        r = api("/backtests/read/log", {"projectId": CLOUD_ID, "backtestId": bid,
                                        "start": start, "end": start + 200, "query": ""})
        chunk = r.get("logs") or []
        out.extend(chunk)
        if len(chunk) < 200:
            break
        start += 200
    return out

def _bwb_payoff(K1, K2, K3, S):   # +1 K1 / -2 K2 / +2 K3 (puts), em pontos
    return max(0.0, K1 - S) - 2 * max(0.0, K2 - S) + 2 * max(0.0, K3 - S)

def _num(x):
    if x in ("", None):
        return None
    try:
        f = float(x); return int(f) if f.is_integer() else f
    except (ValueError, TypeError):
        return x

def parse_ctrade(bid, tries=6):
    for i in range(tries):
        logs = fetch_log(bid)
        hdr = next((l for l in logs if "CTRADEHDR|" in l), None)
        if hdr:
            cols = hdr.split("CTRADEHDR|", 1)[1].split("|")[0].split(",")
            rows = []
            for l in logs:
                if "CTRADE|" not in l:
                    continue
                vals = l.split("CTRADE|", 1)[1].split(",")
                if len(vals) < len(cols):
                    vals += [""] * (len(cols) - len(vals))
                rows.append({c: _num(v) for c, v in zip(cols, vals)})
            if rows:
                return rows
        wait = min(180, 30 * (i + 1))
        print(f"    CTRADE vazio (rate-limit?) — espera {wait}s", flush=True); time.sleep(wait)
    return []

def export_tag(tag, bid):
    recs = parse_ctrade(bid)
    if not recs:
        print(f"[{tag}] sem CTRADE — pula"); return 0
    dte_entry = int(tag.split("_")[1][1:])   # pl5_d45_std -> 45
    applic = [d for d in EXIT_GRID if d < dte_entry]   # regras de saída válidas p/ esse DTE

    rows, daily = [], []
    for r in recs:
        od = str(r.get("od"))
        try:
            o = dt.date.fromisoformat(od); exp = o + dt.timedelta(days=int(r.get("dte") or dte_entry))
        except Exception:
            continue
        hold = float(r.get("snet") or 0)
        # custo de entrada NO MID (consistente com pnl_usd/pnl_exit, que são todos mid). Prefere a coluna
        # 'cm' (motor novo); senão deriva do payoff no settle: cost_mid = payoff(S_settle) - hold/100.
        K1f, K2f, K3f = float(r.get("K1") or 0), float(r.get("K2") or 0), float(r.get("K3") or 0)
        Ssf = float(r.get("Ss") or 0)
        cm = r.get("cm")
        cost_mid = float(cm) if cm not in ("", None) else (_bwb_payoff(K1f, K2f, K3f, Ssf) - hold / 100.0)
        cost_cons = float(r.get("cost") or 0)
        row = {
            "trade_date": od, "exp_date": exp.isoformat(), "underlying": "SPX",
            "dte_entry": int(r.get("dte") or dte_entry), "structure": "BWB 1-2-2 puts (+1/-2/+2)",
            "spot_entry": r.get("Se"), "spot_exit": r.get("Ss"),
            "put_upper": r.get("K1"), "put_center": r.get("K2"), "put_lower": r.get("K3"),
            "total_credit": round(cost_mid * 100.0, 2),                    # débito pago NO MID (×100); BWB é net débito
            "entry_cons": round(cost_cons * 100.0, 2),                     # entrada spread cheio (referência)
            "entry_spread": round((cost_cons - cost_mid) * 100.0, 2),      # custo de execução por trade (cons-mid)
            "vix_entry": r.get("vix"),
            # IV%/EM%: motor não logou ATM IV por-trade -> VIX como proxy de ATM IV (SPX); EM = IV·√(DTE/365).
            "iv_atm_pct": round(float(r.get("vix") or 0), 2) if (r.get("vix") or 0) else "",
            "em_pct": round(float(r.get("vix") or 0) * math.sqrt((int(r.get("dte") or dte_entry)) / 365.0), 2) if (r.get("vix") or 0) else "",
            "expected_move": round(float(r.get("Se") or 0) * (float(r.get("vix") or 0) / 100.0) * math.sqrt((int(r.get("dte") or dte_entry)) / 365.0), 1) if (r.get("vix") and r.get("Se")) else "",
            "pnl_usd": round(hold, 2),                                     # hold-to-expiry (settle)
            "result": "WIN" if hold > 0 else "LOSS", "exit_method": "expiration",
            "mfe": r.get("mfe"), "mae": r.get("mae"),
        }
        # colunas de saída antecipada (mid). Fallback p/ hold se o trade não atingiu D DTE.
        def exit_val(d):
            v = r.get(f"x{d}m"); return round(float(v), 2) if v not in ("", None) else round(hold, 2)
        for d in applic:
            row[f"pnl_exit{d}"] = exit_val(d)
        # TP isolado (mid): sai no TP se atingido; senão segura até o vencimento (fallback hold).
        dte_real = int(r.get("dte") or dte_entry)
        def tp_val(L):
            v = r.get(f"tp{L}"); return round(float(v), 2) if v not in ("", None) else round(hold, 2)
        for L in TP_LEVELS:
            row[f"pnl_tp{L}"] = tp_val(L)
        # regra COMPOSTA "TP L% senão Exit N DTE" — EXATA via dit do TP:
        # dte_rem no cruzamento do TP = dte_real - tpd{L}; usa o TP só se >= N (bateu ANTES do exit).
        for L in TP_LEVELS:
            tpv = r.get(f"tp{L}"); tpd = r.get(f"tpd{L}")
            for d in applic:
                if tpv not in ("", None) and tpd not in ("", None) and (dte_real - int(float(tpd))) >= d:
                    row[f"pnl_tp{L}_exit{d}"] = round(float(tpv), 2)
                else:
                    row[f"pnl_tp{L}_exit{d}"] = exit_val(d)
        rows.append(row)
        daily.append({"trade_date": od, "calendar_date": od, "dte_remaining": row["dte_entry"], "pnl_usd": 0.0})
        daily.append({"trade_date": od, "calendar_date": exp.isoformat(), "dte_remaining": 0, "pnl_usd": round(hold, 2)})

    d = OUT / tag; d.mkdir(parents=True, exist_ok=True)
    with open(d / "trades.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    with open(d / "daily.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(daily[0].keys())); w.writeheader(); w.writerows(daily)
    net = sum(r["pnl_usd"] for r in rows)
    print(f"[{tag}] {len(rows)} trades | hold net ${net:,.0f} | exits {applic} -> {d}")
    return len(rows)

def main():
    sw = json.loads(SWEEP.read_text(encoding="utf-8")) if SWEEP.exists() else {}
    total = 0
    for tag in TAGS:
        bid = sw.get(tag, {}).get("backtestId")
        if not bid:
            print(f"[{tag}] sem backtestId no sweep_pl5.json — pula"); continue
        try:
            total += export_tag(tag, bid)
        except Exception as e:
            print(f"[{tag}] FALHOU: {e}")
    print(f"\n=== PL5 EXPORT: {total} trades em {len(TAGS)} pastas -> {OUT} ===")

if __name__ == "__main__":
    main()
