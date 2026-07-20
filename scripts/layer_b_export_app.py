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
    """Acha o sigma tal que o delta BS bate o delta logado, p/ a linha T+0.

    CUIDADO (bug achado pelo Joao 2026-07-19): p/ uma put OTM, |delta| como funcao de sigma SOBE
    de 0, atinge um PICO, e volta a CAIR -> ha DUAS raizes de IV p/ o mesmo delta. A raiz de sigma
    BAIXO e a financeiramente correta; a de sigma ALTO (~250-290%) e espuria e explodia o valor BS
    do put -> curva T+0 de $380k. Solucao: varrer de baixo p/ cima e pegar a PRIMEIRA raiz (menor
    sigma). P/ put ITM (|delta| decresce monotonico de ~1) a primeira raiz tambem e a unica/correta.
    Cap em 150%: acima disso e degenerado -> 0.0 (o viewer pula a linha T+0 dessa roll)."""
    if T <= 0 or S <= 0 or K <= 0 or target_delta == 0:
        return 0.0
    tgt = abs(target_delta)
    SIG_MAX = 1.5                                          # 150% de vol; acima e espurio
    steps = 300
    prev_sig = 0.01
    prev_d = abs(bs_delta(S, K, T, prev_sig, is_call=is_call))
    for i in range(1, steps + 1):
        sig = 0.01 + (SIG_MAX - 0.01) * i / steps
        d = abs(bs_delta(S, K, T, sig, is_call=is_call))
        if (prev_d - tgt) * (d - tgt) <= 0:               # o alvo esta entre prev_sig e sig (1a raiz)
            lo, hi = prev_sig, sig
            for _ in range(60):                           # bisseccao no bracket da PRIMEIRA raiz
                m = (lo + hi) / 2
                dm = abs(bs_delta(S, K, T, m, is_call=is_call))
                d_lo = abs(bs_delta(S, K, T, lo, is_call=is_call))
                if (d_lo - tgt) * (dm - tgt) <= 0:
                    hi = m
                else:
                    lo = m
            root = (lo + hi) / 2
            if abs(abs(bs_delta(S, K, T, root, is_call=is_call)) - tgt) < 0.01:
                return round(root, 4)
        prev_sig, prev_d = sig, d
    return 0.0                                             # sem raiz <=150% -> degenerado
OUT = REPO / "reports" / "layer_b"
MULT = 100.0   # $/pt (opcao de indice, SPX e RUT)

# Uma PASTA por variante de delta; a API agrupa por underlying (1 card SPX + 1 card RUT) e o
# seletor troca a variante. Tag = "<UND>_<variante>". So exporta as que tem CROLL no disco
# (as do sweep aparecem conforme terminam). (tag, arquivo CROLL, underlying)
QC = HOME / "qc_batman"
# Só a estrutura da fonte (Δ10/Δ25). As variantes de delta d12.5/d15 foram testadas e PIORARAM
# (ver §8 do ACHADOS) → removidas do app por decisão do João. (Os CROLLs delas seguem em
# ~/qc_batman se um dia quisermos re-analisar; basta re-adicionar as linhas aqui.)
RUNS = [
    ("SPX_d10", QC / "croll_spx_5y.csv", "SPX"),
    ("RUT_d10", QC / "croll_rut_5y.csv", "RUT"),
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

    # ATRIBUICAO FORWARD (corrige o desalinhamento que o Joao achou 2026-07-19): cada linha =
    # a posicao ABERTA naquele roll, mantida ate o roll SEGUINTE (quando e fechada/rolada). Logo
    # o P&L da linha = variacao de MTM da ABERTURA (roll i) ao FECHAMENTO (roll i+1) = pnl_total[i+1]
    # - pnl_total[i]. Antes eu usava pnl_total[i]-pnl_total[i-1] (o P&L da posicao ANTERIOR), o que
    # nao batia com o payoff/strikes desta linha. A ultima posicao fica ABERTA (P&L nao realizado).
    pnl_tot = [fnum(r, "pnl_total") for r in rows]
    n = len(rows)
    trades = []
    for i, r in enumerate(rows):
        is_open = (i == n - 1)                            # ultima posicao ainda nao foi fechada
        d_pnl = 0.0 if is_open else (pnl_tot[i + 1] - pnl_tot[i])   # realizado no periodo que ela viveu
        pnl_usd = round(d_pnl * MULT, 2)
        nxt = rows[i + 1] if not is_open else None
        spot_close = round(fnum(nxt, "S"), 2) if nxt else None
        close_date = nxt.get("date") if nxt else None
        cum_at_close = pnl_tot[i + 1] if not is_open else pnl_tot[i]
        net_roll = fnum(r, "net_roll")
        # IV por perna (invertida do delta logado) p/ a linha T+0. dte do CROLL = DTE da posicao na
        # abertura (~42); a linha "no fechamento" reprecifica ~7d depois (quando ela e rolada).
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
            "total_credit": round(fnum(r, "cash_open"), 2),  # CREDITO liquido de abertura (pts) = o "credit"
            "cash_close": round(fnum(r, "cash_close"), 2),   # custo de desmontar (no fechamento)
            "cash_open": round(fnum(r, "cash_open"), 2),
            "net_roll": round(net_roll, 2),
            "net_roll_usd": round(net_roll * MULT, 2),
            "spot_close": spot_close,                        # exit spot (spot no roll seguinte)
            "spot_exit": spot_close,                         # alias p/ o inspector generico
            "effective_close_date": close_date,              # data em que a posicao foi fechada
            "dd_index": round(fnum(r, "dd") * 100, 2),
            "k_gap": round(fnum(r, "k_gap"), 2),
            "mark": round(fnum(r, "mark"), 2) if r.get("mark") not in ("", None) else None,
            "cum_pnl_pts": round(cum_at_close, 2),
            "pnl_usd": pnl_usd,                              # realizado no periodo em que a posicao viveu
            "pnl_usd_at_exp": pnl_usd,
            "result": "open" if is_open else ("win" if pnl_usd > 0 else ("loss" if pnl_usd < 0 else "flat")),
            "exit_method": "open" if is_open else "roll",
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
