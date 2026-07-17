"""
===============================================================================
 LAYER B (1x2 Square Root Hedge) — EXPORT PARA O APP / TRADE AUDITOR
===============================================================================
 Le o CROLL de um run do Layer B e escreve trades.csv + daily.csv no formato que
 o viewer de backtest consome, para o Joao AUDITAR trade-a-trade (prioridade do CZ).

 Modelo de "trade" para uma posicao ROLADA continua (nao ha entradas independentes):
   - 1 roll = 1 linha da tabela.
   - pnl_usd por linha = VARIACAO do P&L total naquela semana (delta pnl_total * mult).
     Isso faz a SOMA da tabela == headline (-$65k SPX / -$31k RUT) EXATO, e a equity
     curve do app vira a curva de MTM real. E o numero mais honesto p/ um hedge carregado
     continuamente: "quanto a posicao mexeu esta semana".
   - net_roll / cash_close / cash_open / k_sh / k_lg / deltas / dd / vix ficam como
     colunas de exibicao p/ auditar a MECANICA do roll (crE o roll a peca critica).

 RECONCILIACAO (impressa e travada): sum(pnl_usd) tem que bater o pnl_total final do
 CROLL ao centavo, senao o script ABORTA (nao sobe numero que nao reconcilia).

 Uso: python scripts/layer_b_export_app.py
 Saida: reports/layer_b/<TAG>/trades.csv + daily.csv
===============================================================================
"""
from __future__ import annotations
import csv
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOME = Path.home()
sys.path.insert(0, str(REPO / "apps" / "api"))
from greeks import delta as bs_delta   # noqa: E402  (invert IV a partir do delta logado)


def iv_from_delta(target_delta: float, S: float, K: float, T: float, is_call: bool = False) -> float:
    """Acha o sigma tal que o delta BS bate o delta logado. Usa a vol REAL que o motor negociou
    (fiel a superficie) p/ a linha T+0. Robusto a monotonicidade: |delta| de put OTM CRESCE com
    sigma, mas de put ITM (roll horizontal com spot caido) DECRESCE -> busca em GRADE + refino,
    nao bisseccao direcional. Devolve 0.0 se nao casar (o viewer pula a linha T+0 dessa roll)."""
    if T <= 0 or S <= 0 or K <= 0 or target_delta == 0:
        return 0.0
    tgt = abs(target_delta)
    # grade grossa em log-sigma -> pega o sigma cujo |delta| mais se aproxima do alvo (qualquer direcao)
    best_sig, best_err = 0.0, 1e9
    steps = 240
    for i in range(steps + 1):
        sig = 0.02 * (3.0 / 0.02) ** (i / steps)          # 2%..300% geometrico
        err = abs(abs(bs_delta(S, K, T, sig, is_call=is_call)) - tgt)
        if err < best_err:
            best_err, best_sig = err, sig
    # refino local em torno do melhor ponto da grade
    span = best_sig * 0.1
    lo, hi = max(0.001, best_sig - span), best_sig + span
    for _ in range(40):
        m1 = lo + (hi - lo) / 3
        m2 = hi - (hi - lo) / 3
        e1 = abs(abs(bs_delta(S, K, T, m1, is_call=is_call)) - tgt)
        e2 = abs(abs(bs_delta(S, K, T, m2, is_call=is_call)) - tgt)
        if e1 < e2:
            hi = m2
        else:
            lo = m1
    sig = (lo + hi) / 2
    if abs(abs(bs_delta(S, K, T, sig, is_call=is_call)) - tgt) > 0.01:
        return 0.0        # nao casou (degenerado) -> invalido
    return round(sig, 4)
OUT = REPO / "reports" / "layer_b"
MULT = 100.0   # $/pt (opcao de indice, SPX e RUT)

# (tag no app, arquivo CROLL, underlying)
RUNS = [
    ("LB_SPX", HOME / "qc_batman" / "croll_spx_5y.csv", "SPX"),
    ("LB_RUT", HOME / "qc_batman" / "croll_rut_5y.csv", "RUT"),
]


def parse_croll(path: Path):
    cols, rows, meta = None, [], {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "CROLLHDR|" in raw:
            body = raw.split("CROLLHDR|", 1)[1]
            parts = body.split("|")
            cols = parts[0].split(",")
            for p in parts[1:]:
                if "=" in p:
                    k, v = p.split("=", 1)
                    meta[k] = v
        elif "CROLL|" in raw:
            v = raw.split("CROLL|", 1)[1].split(",")
            rows.append(v)
    if cols is None:
        raise SystemExit(f"{path}: sem CROLLHDR")
    out = [dict(zip(cols, v)) for v in rows if len(v) == len(cols)]
    # continuidade do id (o log do QC pode cortar o fim = OOS): aborta se houver buraco
    ids = [int(float(r["id"])) for r in out if r.get("id") not in ("", None)]
    gaps = [(a, b) for a, b in zip(ids, ids[1:]) if b != a + 1]
    if gaps or (ids and ids[0] != 1):
        raise SystemExit(f"{path}: id descontinuo {gaps[:3]} start={ids[0] if ids else '?'} "
                         f"-> LOG TRUNCADO, nao exporto parcial")
    return out, meta


def fnum(r, k, default=0.0):
    v = r.get(k, "")
    if v in ("", None):
        return default
    try:
        return float(v)
    except ValueError:
        return default


def build(tag: str, croll: Path, underlying: str):
    rows, meta = parse_croll(croll)
    if not rows:
        print(f"  {tag}: 0 rolls, pulo")
        return None

    trades = []
    prev_pnl_total = 0.0
    for r in rows:
        pnl_total = fnum(r, "pnl_total")
        d_pnl = pnl_total - prev_pnl_total          # variacao MTM da semana (pts)
        prev_pnl_total = pnl_total
        is_entry = r.get("dir") == "entry"
        pnl_usd = round(d_pnl * MULT, 2)
        net_roll = fnum(r, "net_roll")
        # IV por perna (invertida do delta logado) p/ a linha T+0 no viewer. dte do CROLL = DTE
        # da posicao NOVA na abertura (~42); a linha "no fechamento" reprecifica ~7d depois.
        S = fnum(r, "S"); k_sh = fnum(r, "k_sh"); k_lg = fnum(r, "k_lg")
        dte_open = fnum(r, "dte", 42.0)
        iv_sh = iv_from_delta(fnum(r, "d_sh"), S, k_sh, dte_open / 365.0) if k_sh else 0.0
        iv_lg = iv_from_delta(fnum(r, "d_lg"), S, k_lg, dte_open / 365.0) if k_lg else 0.0
        trades.append({
            "trade_date": r.get("date"),
            "exp_date": r.get("exp"),
            "underlying": underlying,
            "dte_entry": r.get("dte"),
            "spot_entry": round(fnum(r, "S"), 2),
            "vix_entry": round(fnum(r, "vix"), 2),
            "roll_dir": r.get("dir"),                  # entry | up (re-strike) | down (horizontal)
            "restruck": r.get("restruck"),
            "short_put": round(fnum(r, "k_sh"), 0),    # perna vendida (d25)
            "long_put": round(fnum(r, "k_lg"), 0),     # pernas compradas 2x (d10)
            "delta_short": round(fnum(r, "d_sh"), 3),
            "delta_long": round(fnum(r, "d_lg"), 3),
            "iv_short": iv_sh,                          # IV invertida do delta (linha T+0)
            "iv_long": iv_lg,
            "dte_close": max(round(dte_open - 7), 1),   # ~35 DTE: onde a posicao sera rolada
            "cash_close": round(fnum(r, "cash_close"), 2),   # desmontar a posicao velha
            "cash_open": round(fnum(r, "cash_open"), 2),     # abrir a nova
            "net_roll": round(net_roll, 2),                  # caixa realizado da semana (pts)
            "net_roll_usd": round(net_roll * MULT, 2),
            "dd_index": round(fnum(r, "dd") * 100, 2),       # drawdown do indice (%)
            "k_gap": round(fnum(r, "k_gap"), 2),             # >0 num 'down' = re-strike proibido
            "mark": round(fnum(r, "mark"), 2) if r.get("mark") not in ("", None) else None,
            "cum_pnl_pts": round(pnl_total, 2),
            "pnl_usd": pnl_usd,                              # <- KPI/equity: soma == headline
            "pnl_usd_at_exp": pnl_usd,
            "result": "win" if pnl_usd > 0 else ("loss" if pnl_usd < 0 else "flat"),
            "exit_method": "roll" if not is_entry else "entry",
            "in_range": 1 if pnl_usd >= 0 else 0,
        })

    # ---- RECONCILIACAO (trava) ----
    total_usd = round(sum(t["pnl_usd"] for t in trades), 2)
    headline_usd = round(fnum(rows[-1], "pnl_total") * MULT, 2)
    if abs(total_usd - headline_usd) > 1.0:
        raise SystemExit(f"  {tag}: RECONCILIACAO FALHOU soma={total_usd} vs headline={headline_usd}")

    # daily.csv = curva de equity MTM (uma linha por roll; o app tb tem a equity dos KPIs)
    daily = []
    cum = 0.0
    for t in trades:
        cum = round(cum + t["pnl_usd"], 2)
        daily.append({
            "date": t["trade_date"], "trade_date": t["trade_date"],
            "spot": t["spot_entry"], "pnl_usd": t["pnl_usd"],
            "cumulative_pnl": cum, "mtm_pnl": t["cum_pnl_pts"] * MULT,
        })

    d = OUT / tag
    d.mkdir(parents=True, exist_ok=True)
    tcols = list(trades[0].keys())
    with open(d / "trades.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=tcols)
        w.writeheader(); w.writerows(trades)
    dcols = list(daily[0].keys())
    with open(d / "daily.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=dcols)
        w.writeheader(); w.writerows(daily)

    downs = [t for t in trades if t["roll_dir"] == "down"]
    dirty = [t for t in downs if t["k_gap"] > 0]
    print(f"  {tag}: {len(trades)} rolls | headline ${headline_usd:,.0f} | "
          f"soma ${total_usd:,.0f} RECONCILIA | period {trades[0]['trade_date']}..{trades[-1]['trade_date']}")
    print(f"         rolls down={len(downs)}, k_gap>0={len(dirty)} | -> {d.relative_to(REPO)}")
    return {"tag": tag, "underlying": underlying, "n": len(trades),
            "total_usd": total_usd, "period": f"{trades[0]['trade_date']}..{trades[-1]['trade_date']}"}


def main():
    print("LAYER B — export p/ o app (Trade Auditor):")
    got = []
    for tag, croll, und in RUNS:
        if not croll.exists():
            print(f"  {tag}: {croll} nao existe, pulo")
            continue
        r = build(tag, croll, und)
        if r:
            got.append(r)
    if not got:
        print("nada exportado")
        sys.exit(1)
    print(f"\nOK: {len(got)} run(s) exportados p/ reports/layer_b/<tag>/")


if __name__ == "__main__":
    main()
