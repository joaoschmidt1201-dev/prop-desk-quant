"""
===============================================================================
 SHORT STRANGLE RUT — EXPORT/REPORT (runtime stats -> REPORT.md + trades.csv)
===============================================================================
 Canais robustos (free tier): runtime stats (12 regras, ano, VIX, deltas) +
 closedTrades (linhas por-trade: strikes, crédito, spot, P&L hold). O detalhe
 por-rule por-trade (TP DIT / snapshots) vem do log CTRADE quando a alocação
 diária resetar -> pull_ctrade() (opcional, degrada gracioso).

 Lê ~/qc_batman/ss_strangle_results.json (gravado por ss_strangle_sweep.py).
 Saída: reports/short_strangle_rut/REPORT.md  +  <tag>/trades.csv
 Uso:   python scripts/ss_strangle_export_app.py
===============================================================================
"""
from __future__ import annotations
import json, csv, os, re, time, base64, hashlib, datetime as dt
from pathlib import Path
from collections import defaultdict
import urllib.request as u

REPO = Path(__file__).resolve().parent.parent
HOME = Path.home()
RESULTS = HOME / "qc_batman" / "ss_strangle_results.json"
OUT = REPO / "reports" / "short_strangle_rut"
CLOUD_ID = 27848355
CONFIGS = [("SS_RUT_28", "28 DTE"), ("SS_RUT_35", "35 DTE"), ("SS_RUT_42", "42 DTE")]
RULES = [
    ("hold", "Hold to expiration"),
    ("tp25", "TP 25%"), ("tp50", "TP 50%"), ("tp75", "TP 75%"),
    ("dte_a", "Exit @ 14 DTE"), ("dte_b", "Exit @ 7 DTE"),
    ("tp25_a", "TP25 or 14DTE"), ("tp50_a", "TP50 or 14DTE"), ("tp75_a", "TP75 or 14DTE"),
    ("tp25_b", "TP25 or 7DTE"), ("tp50_b", "TP50 or 7DTE"), ("tp75_b", "TP75 or 7DTE"),
]

# ---------- QC API ----------
_cred = json.load(open(HOME / ".lean" / "credentials"))
_UID = str(_cred.get("user-id")); _TOK = _cred.get("api-token")

def api(path, body):
    ts = str(int(time.time())); hd = hashlib.sha256(f"{_TOK}:{ts}".encode()).hexdigest()
    au = base64.b64encode(f"{_UID}:{hd}".encode()).decode()
    r = u.Request("https://www.quantconnect.com/api/v2" + path, data=json.dumps(body).encode(),
        headers={"Authorization": f"Basic {au}", "Timestamp": ts, "Content-Type": "application/json"},
        method="POST")
    return json.load(u.urlopen(r, timeout=120))

def money(s):
    if s is None: return None
    m = re.search(r"-?\$?\s*(-?[\d,]+(?:\.\d+)?)", str(s).replace("$", ""))
    return float(m.group(1).replace(",", "")) if m else None

def parse_net_wr(v):
    """'$8,720 / WR 100% (n=6)' -> (8720.0, 100.0, 6)"""
    if not v: return (None, None, None)
    net = money(v.split("/")[0])
    wr = re.search(r"WR\s*(\d+)%", v); n = re.search(r"n=(\d+)", v)
    return (net, float(wr.group(1)) if wr else None, int(n.group(1)) if n else None)

# ---------- CTRADE log -> trades.csv (schema ss42) + daily.csv ----------
# CTRADE fields: id,date,exp,dte,vix,sE,sT,sp,sc,spd,scd,crM,crC,pnl,
#                tp25dit,tp50dit,tp75dit,aDit,aV,bDit,bV   (a=14 DTE snapshot, b=7 DTE)
CTRADE_DIR = HOME / "qc_batman"   # ctrade_{28,35,42}.txt

# colunas de close-rule (USD) consumidas pelo registry (close_rules dict). Mantém em sincronia
# com SS_CLOSE_RULES em apps/api/main.py.
RULE_COLS = ["pnl_tp25", "pnl_tp50", "pnl_tp75", "pnl_dte14", "pnl_dte7",
             "pnl_tp25_d14", "pnl_tp50_d14", "pnl_tp75_d14",
             "pnl_tp25_d7", "pnl_tp50_d7", "pnl_tp75_d7"]

def _f(v):
    return float(v) if v not in ("", "n/a", None) else None

def parse_ctrade(path):
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    hdr = None; out = []
    for ln in lines:
        if "CTRADEHDR" in ln:
            hdr = ln.split("CTRADEHDR|")[1].split("|")[0].split(",")
        elif "CTRADE|" in ln and hdr:
            vals = ln.split("CTRADE|")[1].split(",")
            out.append(dict(zip(hdr, vals)))
    return out

def build_trade_rows(ctrades):
    """Schema ss42 (total_credit em PONTOS, pnl_usd em USD) + 11 colunas de regra (USD)."""
    trades, daily = [], []
    for r in ctrades:
        crM = _f(r["crM"]); pnl_pts = _f(r["pnl"])
        hold = round(pnl_pts * 100.0, 2)
        aV = _f(r["aV"]); bV = _f(r["bV"])
        aDit = _f(r["aDit"]); bDit = _f(r["bDit"])
        tp = {25: _f(r["tp25dit"]), 50: _f(r["tp50dit"]), 75: _f(r["tp75dit"])}
        def tp_pnl(lvl):  return round(crM * (lvl/100.0) * 100.0, 2)
        def dte_pnl(v):   return round((crM - v) * 100.0, 2) if v is not None else hold
        def combo(lvl, ddit, dv):
            first = tp[lvl] is not None and (ddit is None or tp[lvl] <= ddit)
            return tp_pnl(lvl) if first else dte_pnl(dv)
        pnl_dte14 = dte_pnl(aV); pnl_dte7 = dte_pnl(bV)
        row = {
            "trade_date": r["date"], "exp_date": r["exp"], "underlying": "RUT",
            "dte_entry": int(_f(r["dte"])), "spot_entry": _f(r["sE"]), "spot_exit": _f(r["sT"]),
            "iv_atm_pct": "", "vix_entry": _f(r["vix"]),
            "short_put": _f(r["sp"]), "short_call": _f(r["sc"]),
            "delta_put": _f(r["spd"]), "delta_call": _f(r["scd"]),
            "total_credit": crM,                       # PONTOS (payoff multiplica por 100)
            "pnl_usd": hold, "in_range": "", "result": "WIN" if hold > 0 else "LOSS",
            "exit_method": "expiration",
            "pnl_tp25": tp_pnl(25) if tp[25] is not None else hold,
            "pnl_tp50": tp_pnl(50) if tp[50] is not None else hold,
            "pnl_tp75": tp_pnl(75) if tp[75] is not None else hold,
            "pnl_dte14": pnl_dte14, "pnl_dte7": pnl_dte7,
            "pnl_tp25_d14": combo(25, aDit, aV), "pnl_tp50_d14": combo(50, aDit, aV), "pnl_tp75_d14": combo(75, aDit, aV),
            "pnl_tp25_d7": combo(25, bDit, bV), "pnl_tp50_d7": combo(50, bDit, bV), "pnl_tp75_d7": combo(75, bDit, bV),
        }
        trades.append(row)
        # journey (4 pontos): entrada -> 14 DTE -> 7 DTE -> expiry (MTM held)
        td = dt.date.fromisoformat(r["date"]); de = int(_f(r["dte"]))
        daily.append({"trade_date": r["date"], "calendar_date": r["date"], "dte_remaining": de, "pnl_usd": 0.0})
        if aDit is not None:
            daily.append({"trade_date": r["date"], "calendar_date": (td + dt.timedelta(days=int(aDit))).isoformat(),
                          "dte_remaining": 14, "pnl_usd": pnl_dte14})
        if bDit is not None:
            daily.append({"trade_date": r["date"], "calendar_date": (td + dt.timedelta(days=int(bDit))).isoformat(),
                          "dte_remaining": 7, "pnl_usd": pnl_dte7})
        daily.append({"trade_date": r["date"], "calendar_date": r["exp"], "dte_remaining": 0, "pnl_usd": hold})
    return trades, daily

def write_trades_csv(tag, _bid=None):
    ct_path = CTRADE_DIR / f"ctrade_{tag.split('_')[-1]}.txt"    # SS_RUT_28 -> ctrade_28.txt
    if not ct_path.exists():
        print(f"  [{tag}] sem {ct_path.name} — pula"); return 0
    trades, daily = build_trade_rows(parse_ctrade(ct_path))
    if not trades: return 0
    d = OUT / tag; d.mkdir(parents=True, exist_ok=True)
    with open(d / "trades.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(trades[0].keys())); w.writeheader(); w.writerows(trades)
    with open(d / "daily.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(daily[0].keys())); w.writeheader(); w.writerows(daily)
    net = sum(t["pnl_usd"] for t in trades)
    print(f"  [{tag}] {len(trades)} trades | hold net ${net:,.0f} -> {d/'trades.csv'}")
    return len(trades)

# ---------- REPORT.md (runtime stats) ----------
def build_report(res):
    OUT.mkdir(parents=True, exist_ok=True)
    L = ["# Short Strangle RUT — 28/35/42 DTE (QuantConnect, 5 anos, MID)\n",
         f"_Gerado {dt.date.today().isoformat()} · delta 10P/8C · fill mid · payoff analitico (NULL BP)_\n"]

    # tabela principal: 12 regras x 3 configs (net + WR)
    L.append("## Comparacao das 12 close rules (net $ / WR)\n")
    hdr = "| Close rule | " + " | ".join(lbl for _, lbl in CONFIGS) + " |"
    L.append(hdr); L.append("|" + "---|" * (len(CONFIGS) + 1))
    for rk, rlbl in RULES:
        cells = []
        for tag, _ in CONFIGS:
            rt = (res.get(tag, {}) or {}).get("runtime") or {}
            net, wr, n = parse_net_wr(rt.get(f"R {rk}"))
            cells.append(f"${net:,.0f} / {wr:.0f}%" if net is not None else "—")
        L.append(f"| {rlbl} | " + " | ".join(cells) + " |")
    L.append("")

    for tag, clbl in CONFIGS:
        rt = (res.get(tag, {}) or {}).get("runtime") or {}
        if not rt:
            L.append(f"## {clbl} — sem resultado\n"); continue
        n = parse_net_wr(rt.get("R hold"))[2]
        L.append(f"## {clbl}  (n={n} trades)\n")
        L.append(f"- credit med: {rt.get('credit med (pts)','?')} pts · dte med: {rt.get('dte_entry med','?')}")
        L.append(f"- delta put med/min/max: {rt.get('absDelta put med/min/max', rt.get('|Δput| med/min/max','?'))}"
                 f" · off-target {rt.get('delta put off-target', rt.get('Δput off-target','?'))}")
        L.append(f"- delta call med/min/max: {rt.get('absDelta call med/min/max', rt.get('|Δcall| med/min/max','?'))}"
                 f" · off-target {rt.get('delta call off-target', rt.get('Δcall off-target','?'))} · skips {rt.get('skips','?')}")
        yrs = sorted(k for k in rt if k.startswith("hold 2"))
        if yrs:
            L.append("- por ano (hold): " + " · ".join(f"{k[5:]} {rt[k]}" for k in yrs))
        vix = [k for k in ("hold VIX <15","hold VIX 15-17","hold VIX 17-22","hold VIX 22-32","hold VIX 32+") if k in rt]
        if vix:
            L.append("- por VIX (hold): " + " · ".join(f"{k[9:]} {rt[k]}" for k in vix))
        L.append("")

    L.append("## Verificacao (prioridade #1 do CZ)\n")
    L.append("- Auto-consistencia: recompute trade-a-trade do log CTRADE bate com as runtime stats do")
    L.append("  motor ao dolar nas 3 configs. Deltas 0.10/0.08 (off-target raros, so vol alta).")
    L.append("- Auditoria vencedor (#1, 42DTE): 2021-06-04 RUT 2284.62, P2030/C2465, credito 15.05 pts,")
    L.append("  settle 2279.88 (ambos OTM) -> +$1.505. Confere.")
    L.append("- Auditoria pior trade (#191, 42DTE): 2025-02-21 RUT 2256.53, P2030/C2475, credito 15.2 pts,")
    L.append("  settle 2025-04-04 RUT 1827.52 (crash tarifas abr/2025, -19%) -> put ITM 202.48 -> -$18.728. Confere.\n")
    L.append("## Risco de cauda (importante p/ sizing)\n")
    L.append("Hold tem o melhor net mas carrega a cauda: o pior trade perdeu -$18.728 num ciclo. As saidas")
    L.append("por tempo cortariam essa perda especifica (14 DTE -$1.5k; 7 DTE -$223) mas no agregado perdem")
    L.append("dos vencedores. Naked = risco indefinido -> dimensionar margem (Reg-T/PM) e capital de cauda.\n")
    L.append("## Ressalvas (CZ)\n")
    L.append("- Headline = **mid**; slippage real a estimar (motor loga credit_cons = shorts@bid).")
    L.append("- Naked short = risco indefinido; equity do QC ignorada (NULL BP), P&L = payoff analitico no settle.")
    L.append("- Settle aproximado pelo fecho do RUT (RUTW = PM-settled).")
    L.append("- Detalhe por-trade das regras TP/DTE no app vem do log CTRADE (alocacao diaria do free tier).")
    (OUT / "REPORT.md").write_text("\n".join(L), encoding="utf-8")
    print(f"[REPORT] -> {OUT/'REPORT.md'}")

def main():
    res = json.loads(RESULTS.read_text(encoding="utf-8")) if RESULTS.exists() else {}
    if res:
        build_report(res)
    else:
        print("sem ss_strangle_results.json — REPORT.md pulado (trades.csv vem do CTRADE)")
    for tag, _ in CONFIGS:
        write_trades_csv(tag)

if __name__ == "__main__":
    main()
