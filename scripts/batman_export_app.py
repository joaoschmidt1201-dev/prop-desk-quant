"""
===============================================================================
 BATMAN EXPORT APP — orders/closedTrades (QC API) -> trades.csv + daily.csv
===============================================================================
 FONTE DE VERDADE = payoff de BORBOLETA LIMPO (intrínseco num ÚNICO preço de
 settle), reconstruído dos fills reais de entrada. NÃO calibra pra equity do QC.

 POR QUÊ (achado 2026-05-27): a equity/Net Profit do QC INFLA borboletas que
 expiram deep-ITM-atravessadas (ex.: crash abr/2025). O QC liquida as pernas
 curtas e longas em timestamps/preços DIFERENTES (orders type 6) e fabrica P&L
 fantasma. Uma borboleta simétrica atravessada vale $0 EXATO (pernas se
 cancelam). Logo a equity do QC está ERRADA nesses casos; o payoff limpo é o
 número CORRETO — e é imune ao artefato por construção (um único preço de settle).

 Cada Batman = 6 pernas (call fly +1/-2/+1 acima, put fly +1/-2/+1 abaixo),
 agrupadas por entryTime. P&L = Σ_legs n*(intrínseco(S_exp) - entryPrice), onde
 entryPrice = fill REAL do QC (exato) e S_exp = close do SPX no expiry.

 VALIDAÇÃO: Σ pnl_usd reconcilia com o `NET M0 hold` do motor (runtime stat,
 também limpo). Diferença esperada = só o spread de entrada (o motor estima asas
 no ask / corpo no bid; aqui usamos o fill real, mais barato) → poucos $/trade.

 Uso:  python scripts/batman_export_app.py            # exporta tudo do sweep
       python scripts/batman_export_app.py <bid> <tag>
===============================================================================
"""
from __future__ import annotations
import json, base64, hashlib, time, os, sys, csv, datetime as dt
from collections import defaultdict
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
HOME = Path(os.path.expanduser("~"))
PID = 27848355
OUT = REPO / "reports" / "batman_backtest_app"
SWEEP = HOME / "qc_batman" / "sweep_results.json"
VIX_CACHE = REPO / "data" / "cache" / "vix_daily.parquet"
SPX_CACHE = REPO / "data" / "cache" / "spx_daily.parquet"

_cred = json.load(open(HOME / ".lean" / "credentials"))
_UID = str(_cred.get("user-id") or _cred.get("user_id") or _cred.get("userId"))
_TOK = _cred.get("api-token") or _cred.get("token") or _cred.get("apiToken")

SWEEP_RES: dict = {}


def api(path, body):
    import urllib.request
    ts = str(int(time.time()))
    hashed = hashlib.sha256(f"{_TOK}:{ts}".encode()).hexdigest()
    auth = base64.b64encode(f"{_UID}:{hashed}".encode()).decode()
    req = urllib.request.Request("https://www.quantconnect.com/api/v2" + path,
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Basic {auth}", "Timestamp": ts, "Content-Type": "application/json"},
        method="POST")
    return json.load(urllib.request.urlopen(req, timeout=180))


def load_vix():
    if VIX_CACHE.exists():
        v = pd.read_parquet(VIX_CACHE)
        v["date"] = pd.to_datetime(v["date"]).dt.normalize()
        return v.sort_values("date")
    import io, urllib.request
    url = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    raw = urllib.request.urlopen(req, timeout=30).read().decode()
    v = pd.read_csv(io.StringIO(raw)); v.columns = [c.lower() for c in v.columns]
    v["date"] = pd.to_datetime(v["date"]).dt.normalize()
    return v[["date", "close"]].rename(columns={"close": "vix"}).sort_values("date")


def vix_at(d, vdf):
    d = pd.Timestamp(d).normalize()
    p = vdf[vdf["date"] <= d].tail(1)
    return round(float(p["vix"].iloc[0]), 2) if len(p) else None


def load_spx():
    """SPX close diário (settlement ref do SPXW PM). Cache; Yahoo chart endpoint (stdlib)."""
    if SPX_CACHE.exists():
        s = pd.read_parquet(SPX_CACHE)
        s["date"] = pd.to_datetime(s["date"]).dt.normalize()
        return s.sort_values("date")
    import urllib.request
    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
    url = "https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC?range=5y&interval=1d"
    last = None
    for _ in range(4):
        try:
            data = json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30))
            res = data["chart"]["result"][0]
            ts = res["timestamp"]
            closes = res["indicators"]["quote"][0]["close"]
            rows = [(pd.Timestamp(t, unit="s").normalize(), c) for t, c in zip(ts, closes) if c is not None]
            s = pd.DataFrame(rows, columns=["date", "spx"]).sort_values("date")
            if len(s) > 100:
                SPX_CACHE.parent.mkdir(parents=True, exist_ok=True)
                s.to_parquet(SPX_CACHE, index=False)
                return s
        except Exception as e:
            last = e; time.sleep(5)
    raise RuntimeError(f"nao consegui baixar SPX diario (Yahoo chart): {last}")


def spx_at(d, sdf):
    d = pd.Timestamp(d).normalize()
    ex = sdf[sdf["date"] == d]
    if len(ex):
        return float(ex["spx"].iloc[0])
    p = sdf[sdf["date"] <= d].tail(1)
    return float(p["spx"].iloc[0]) if len(p) else None


def parse_symbol(v):
    body = v.replace("SPXW", "").strip()            # "220622C03835000"
    exp = dt.datetime.strptime(body[:6], "%y%m%d").date()
    return exp, body[6], int(body[7:]) / 1000.0


def _money(s):
    try:
        return float(str(s).replace("$", "").replace(",", "").strip())
    except Exception:
        return None


def _m0_hold(tag):
    """NET M0 hold do motor (runtime stat) — referência LIMPA p/ validar. '$X / WR Y%'."""
    rt = (SWEEP_RES.get(tag, {}).get("runtime") or {})
    return _money((rt.get("NET M0 hold") or "").split("/")[0])


def _fly_strikes(legs, right):
    """(lower, center, upper, side_debit) de um lado. center = short (qty 2)."""
    side = [l for l in legs if parse_symbol(l["symbols"][0]["value"])[1] == right]
    ks = {}
    for l in side:
        _, _, K = parse_symbol(l["symbols"][0]["value"])
        ks[K] = l
    if not ks:                                  # lado ausente (ex.: run de TP fechou só um lado)
        return None, None, None, 0.0
    lo, up = min(ks), max(ks)
    center = [K for K in ks if K not in (lo, up)]
    center = center[0] if center else round((lo + up) / 2, 0)
    debit = 0.0
    for K, l in ks.items():
        n = (1 if l["direction"] == 0 else -1) * abs(l["quantity"])
        debit += n * l["entryPrice"]
    return lo, center, up, round(debit, 2)


def recon(bid):
    """Per-trade LIMPO (1 Batman por entryTime). Payoff de borboleta num único preço
    de settle, dos fills reais. SEM calibração. Devolve lista de dicts (com detalhe p/ auditoria)."""
    bt = api("/backtests/read", {"projectId": PID, "backtestId": bid})["backtest"]
    ct = (bt.get("totalPerformance") or {}).get("closedTrades") or []
    if not ct:
        return []
    vdf = load_vix(); sdf = load_spx()
    groups = defaultdict(list)
    for t in ct:
        groups[t["entryTime"]].append(t)
    trades = []
    for et, legs in sorted(groups.items()):
        entry = dt.datetime.fromisoformat(et.replace("Z", "+00:00"))
        tdate = entry.date()
        exp = max(parse_symbol(l["symbols"][0]["value"])[0] for l in legs)
        S_exp = spx_at(exp, sdf)
        if S_exp is None:
            continue
        debit = 0.0; pnl = 0.0
        for l in legs:
            _, right, K = parse_symbol(l["symbols"][0]["value"])
            n = (1 if l["direction"] == 0 else -1) * abs(l["quantity"]) * 100
            debit += n * l["entryPrice"]
            if (l.get("exitPrice") or 0) > 0:           # fechada CEDO (TP executado) -> round-trip
                pnl += l.get("profitLoss") or 0          # exato (sem artefato: 2 lados fecham juntos no mid)
            else:                                        # held-to-expiry -> PAYOFF LIMPO num único preço
                intr = max(0.0, S_exp - K) if right == "C" else max(0.0, K - S_exp)
                pnl += n * (intr - l["entryPrice"])
        clo, ccen, cup, cdeb = _fly_strikes(legs, "C")
        plo, pcen, pup, pdeb = _fly_strikes(legs, "P")
        trades.append({
            "trade_date": tdate, "exp_date": exp, "dte": max((exp - tdate).days, 1),
            "debit": round(debit, 2), "pnl": round(pnl, 2), "vix": vix_at(tdate, vdf),
            "spot_settle": round(S_exp, 2),
            "call_lower": clo, "call_center": ccen, "call_upper": cup, "call_debit": cdeb,
            "put_lower": plo, "put_center": pcen, "put_upper": pup, "put_debit": pdeb,
        })
    return trades


TP_LEVELS = [50, 100, 150, 200]   # % sobre o débito (close-rule); colunas pnl_tpNN


def export(tag, bid, tp_bids=None, underlying="SPX"):
    """Exporta a variante base. tp_bids = {nivel(int): backtestId} dos runs tp_close;
    o recon de cada um vira a coluna pnl_tpNN (P&L por-trade SOB aquela regra de TP)."""
    trades = recon(bid)
    if not trades:
        print(f"[{tag}] sem closedTrades"); return 0

    # colunas de TP: recon de cada run tp_close, casado por trade_date (mesmo dia de abertura).
    tp_maps = {}
    for lvl, tbid in (tp_bids or {}).items():
        try:
            tp_maps[lvl] = {t["trade_date"]: t["pnl"] for t in recon(tbid)}
        except Exception as e:
            print(f"  [{tag}] tp{lvl} recon falhou: {e}")

    rows = []
    for t in trades:
        row = {
            "trade_date": t["trade_date"].isoformat(), "exp_date": t["exp_date"].isoformat(),
            "underlying": underlying, "dte_entry": t["dte"], "total_credit": t["debit"],
            "pnl_usd": t["pnl"], "vix_entry": t["vix"], "spot_exit": t["spot_settle"],
            "result": "WIN" if t["pnl"] > 0 else "LOSS", "exit_method": "expiration",
            "in_range": t["pnl"] > 0,
            "call_lower": t["call_lower"], "call_center": t["call_center"], "call_upper": t["call_upper"],
            "call_debit": t["call_debit"],
            "put_lower": t["put_lower"], "put_center": t["put_center"], "put_upper": t["put_upper"],
            "put_debit": t["put_debit"],
        }
        for lvl in TP_LEVELS:
            if lvl in tp_maps:                       # sem fechamento naquele dia -> segura (hold)
                row[f"pnl_tp{lvl}"] = round(tp_maps[lvl].get(t["trade_date"], t["pnl"]), 2)
        rows.append(row)

    daily = []
    for t in trades:
        daily.append({"trade_date": t["trade_date"].isoformat(), "calendar_date": t["trade_date"].isoformat(),
                      "dte_remaining": t["dte"], "pnl_usd": 0.0})
        daily.append({"trade_date": t["trade_date"].isoformat(), "calendar_date": t["exp_date"].isoformat(),
                      "dte_remaining": 0, "pnl_usd": t["pnl"]})

    d = OUT / tag; d.mkdir(parents=True, exist_ok=True)
    with open(d / "trades.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    with open(d / "daily.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(daily[0].keys())); w.writeheader(); w.writerows(daily)

    net = sum(r["pnl_usd"] for r in rows)
    wr = 100.0 * sum(1 for r in rows if r["pnl_usd"] > 0) / len(rows)
    # VALIDAÇÃO: reconcilia com o M0 limpo do motor (diferença = spread de entrada)
    m0 = _m0_hold(tag)
    chk = ""
    if m0 is not None:
        chk = f" | M0 motor ${m0:,.0f} | dif ${net - m0:+,.0f} ({(net-m0)/len(rows):+.1f}/trade)"
    print(f"[{tag}] {len(rows)} batmans | net LIMPO ${net:,.0f} | WR {wr:.0f}%{chk} -> {d}")
    return len(rows)


import re as _re
_TP_RE = _re.compile(r"^(.*)_tp(\d+)$")


def main():
    global SWEEP_RES
    OUT.mkdir(parents=True, exist_ok=True)
    SWEEP_RES = json.loads(SWEEP.read_text(encoding="utf-8")) if SWEEP.exists() else {}
    if len(sys.argv) >= 3:
        export(sys.argv[2], sys.argv[1])
        return
    # Mapeia tags tp_close -> base: {base_tag: {nivel: bid}}. As tags _tpNN NÃO viram pasta;
    # entram como colunas pnl_tpNN na pasta da variante base.
    tp_by_base: dict[str, dict[int, str]] = {}
    base_tags: list[str] = []
    for tag, r in SWEEP_RES.items():
        bid = r.get("backtestId")
        if not bid:
            continue
        m = _TP_RE.match(tag)
        if m:
            tp_by_base.setdefault(m.group(1), {})[int(m.group(2))] = bid
        else:
            base_tags.append(tag)
    for tag in base_tags:
        bid = SWEEP_RES[tag]["backtestId"]
        try:
            export(tag, bid, tp_bids=tp_by_base.get(tag))
        except Exception as e:
            print(f"[{tag}] FALHOU: {e}")


if __name__ == "__main__":
    main()
