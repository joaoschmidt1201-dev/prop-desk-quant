#!/usr/bin/env python3
"""
layer_b_analyze.py
------------------
Analisa o canal CROLL do backtest do Layer B (1x2 Square Root Hedge) e responde as
TRES restricoes do Joao, reportadas lado a lado SEM veredito unico (o CZ escolhe qual
falha ele sobrevive -- e a conclusao do proprio research note).

  R1  "receber credito semanalmente"  -> net cash por roll; % das semanas em credito
  R2  "lucrar num crash"              -> P&L nos episodios de DD >= 12%
  R3  "nao morrer no grind lento"     -> P&L na faixa 0 a -12% (a travessia da cova)

Diagnosticos (nao sao headline):
  - mid vs cons  -> quanto a iliquidez custa (RUT fino vs SPX liquido)
  - escada de DTE -> % dos rolls dentro de 40-45. Confunde a comparacao SPX x RUT:
    ela mistura basis + iliquidez + qualidade da escada. Por isso os 3 saem separados.

Uso:
  python scripts/layer_b_analyze.py <croll_file.csv> [mais.csv ...]

O arquivo vem do `~/qc_batman/_pull.py <projectId> <bid> CROLL <out>`; cada linha e
"<timestamp> CROLL|v1,v2,...". O header vem como "CROLLHDR|col1,col2,...|ref=..|band=..".
"""

import sys
from pathlib import Path
from statistics import median

MULT = 100.0          # $/pt tanto p/ SPX quanto p/ RUT (opcao de indice)
DD_TAIL = -0.12       # a fonte: "ab einem Drawdown von ca. 12% volle Wirkung"


def parse(path: Path):
    """Le o dump do CROLL. Retorna (rows, meta). Tolera o timestamp do log na frente."""
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
            vals = raw.split("CROLL|", 1)[1].split(",")
            rows.append(vals)
    if cols is None:
        raise SystemExit(f"{path}: sem CROLLHDR - o log truncou? (cap do free tier)")
    out, dropped = [], []
    for v in rows:
        if len(v) != len(cols):
            dropped.append(v)             # linha partida pelo cap de log
            continue
        out.append(dict(zip(cols, v)))
    # NUNCA descartar em silencio: o cap de log do QC (~707 linhas) corta o fim da serie,
    # que e justamente o OOS. Uma analise "limpa" sobre metade dos rolls e pior que um erro.
    if dropped:
        print(f"\n  !! ATENCAO {path.name}: {len(dropped)} linha(s) mal-formada(s) descartada(s) "
              f"de {len(rows)} - LOG TRUNCADO? A analise abaixo esta INCOMPLETA.")
        for v in dropped[:3]:
            print(f"     ex ({len(v)} campos, esperado {len(cols)}): {','.join(v)[:100]}")
    _check_continuity(path, out)
    return out, meta


def _check_continuity(path: Path, rows):
    """O cap de log do QC nao corta so no meio da linha: ele come LINHAS INTEIRAS do fim da
    serie -- que e justamente o OOS. Uma linha bem-formada a menos nao dispara o check de
    campos acima, entao a serie some em silencio. O `id` e sequencial (1..N) na emissao, logo
    qualquer buraco ou fim precoce e prova de truncamento."""
    ids = []
    for r in rows:
        try:
            ids.append(int(float(r.get("id", ""))))
        except (ValueError, TypeError):
            return                      # sem id utilizavel -> nada a afirmar
    if not ids:
        return
    gaps = [(a, b) for a, b in zip(ids, ids[1:]) if b != a + 1]
    if gaps:
        print(f"\n  !! ATENCAO {path.name}: BURACO na sequencia de id -> LOG TRUNCADO. "
              f"A analise abaixo esta INCOMPLETA.")
        for a, b in gaps[:5]:
            print(f"     id {a} -> {b} (faltam {b - a - 1})")
    if ids[0] != 1:
        print(f"\n  !! ATENCAO {path.name}: a serie comeca em id={ids[0]}, nao 1 - "
              f"inicio truncado.")
    print(f"  continuidade: id {ids[0]}..{ids[-1]}, {len(ids)} rolls"
          f"{' (OK, sem buracos)' if not gaps and ids[0] == 1 else ''}")


def f(row, key, default=None):
    v = row.get(key, "")
    if v in ("", None):
        return default
    try:
        return float(v)
    except ValueError:
        return default


def report(path: Path):
    rows, meta = parse(path)
    if not rows:
        print(f"\n{path.name}: 0 rolls\n")
        return
    rolls = [r for r in rows if r.get("dir") != "entry"]
    n = len(rolls)
    print("=" * 78)
    print(f"{path.name}   rolls={n}  ref={meta.get('ref','?')} band={meta.get('band','?')}")
    print(f"  periodo: {rows[0]['date']} -> {rows[-1]['date']}")
    print("=" * 78)

    # ---------- R1: credito semanal ----------
    nets = [f(r, "net_roll", 0.0) for r in rolls]
    netc = [f(r, "net_roll_cons", 0.0) for r in rolls]
    if n:
        pos = sum(1 for x in nets if x > 0)
        posc = sum(1 for x in netc if x > 0)
        print("\n[R1] CREDITO SEMANAL  (a hipotese: o credito de entrada e cobrado 1x, o roll 52x)")
        print(f"  rolls em credito (mid) : {pos}/{n} = {100.0*pos/n:.0f}%")
        print(f"  rolls em credito (cons): {posc}/{n} = {100.0*posc/n:.0f}%")
        print(f"  net/roll  mediana: {median(nets):+.2f} pts (${median(nets)*MULT:+,.0f})")
        print(f"  net/roll  media  : {sum(nets)/n:+.2f} pts")
        print(f"  soma dos rolls   : {sum(nets):+.2f} pts (${sum(nets)*MULT:+,.0f})")

    # ---------- P&L / carrego ----------
    last = rows[-1]
    pnl = f(last, "pnl_total", 0.0)
    cash = f(last, "cum_cash", 0.0)
    cashc = f(last, "cum_cash_cons", 0.0)
    comm = f(last, "comm", 0.0)
    yrs = max(1e-9, (int(last["date"][:4]) - int(rows[0]["date"][:4])) or 1)
    print("\n[CARREGO]")
    print(f"  P&L total          : {pnl:+.2f} pts = ${pnl*MULT:+,.0f}  (1 unidade)")
    print(f"  custo/ano por unid.: ${pnl*MULT/yrs:+,.0f}")
    print(f"  comissoes          : ${comm:,.0f}")
    gap = cash - cashc
    print(f"  ILIQUIDEZ mid-cons : ${gap*MULT:,.0f}  <- o que o mid esconde")

    # ---------- R2 / R3: P&L por faixa de drawdown ----------
    print("\n[R2/R3] NET DOS ROLLS POR FAIXA DE DRAWDOWN DO INDICE")
    bands = [(-1.00, DD_TAIL, "DD <= -12%  (tail: onde a fonte diz que funciona)"),
             (DD_TAIL, -0.04, "DD -12..-4% (A COVA - o grind lento)"),
             (-0.04, -0.005, "DD -4..-0.5%"),
             (-0.005, 1.00, "DD ~topo")]
    for lo, hi, label in bands:
        rs = [r for r in rolls if lo <= f(r, "dd", 0.0) < hi]
        if not rs:
            print(f"  {label:46s}  (nenhum roll)")
            continue
        s = sum(f(r, "net_roll", 0.0) for r in rs)
        print(f"  {label:46s}  net {s:+8.2f} pts (${s*MULT:+9,.0f})  n={len(rs)}")

    # pico de payoff intra-semana no tail (o futuro nao pega o gap; o Layer B deveria)
    tail = [r for r in rolls if f(r, "dd_wk", 0.0) is not None
            and f(r, "dd_wk", 0.0) <= DD_TAIL]
    if tail:
        mk = [f(r, "mark_max_wk") for r in tail if f(r, "mark_max_wk") is not None]
        if mk:
            print(f"\n  pico de mark intra-semana com DD<=-12%: max {max(mk):+.2f} pts "
                  f"(${max(mk)*MULT:+,.0f}) em n={len(mk)} semanas")

    # ---------- diagnostico: escada de DTE ----------
    inb = sum(1 for r in rows if r.get("in_band") == "1")
    dtes = [f(r, "dte", 0) for r in rows]
    print("\n[DIAG] ESCADA DE VENCIMENTOS  (confunde a comparacao SPX x RUT se ignorada)")
    print(f"  DTE dentro de 40-45: {inb}/{len(rows)} = {100.0*inb/len(rows):.0f}%")
    print(f"  DTE mediano: {median(dtes):.0f}")

    # ---------- diagnostico: veracidade dos deltas ----------
    dsh = [abs(f(r, "d_sh", 0.0)) for r in rows if f(r, "d_sh") is not None]
    dlg = [abs(f(r, "d_lg", 0.0)) for r in rows if f(r, "d_lg") is not None]
    if dsh and dlg:
        print("\n[DIAG] DELTAS  (alvo short 0.25 / long 0.10; se desviar, a selecao esta errada)")
        print(f"  short: med {median(dsh):.3f}  min {min(dsh):.3f}  max {max(dsh):.3f}")
        print(f"  long : med {median(dlg):.3f}  min {min(dlg):.3f}  max {max(dlg):.3f}")

    # ---------- GATE DE TOPOLOGIA ----------
    bad = [r for r in rows if f(r, "k_lg", 0) >= f(r, "k_sh", 1e9)]
    print("\n[GATE] TOPOLOGIA  (K_long < K_short senao nao e um 1x2 backspread)")
    print(f"  violacoes: {len(bad)}/{len(rows)}" + ("  <-- FALHOU" if bad else "  OK"))

    ups = sum(1 for r in rolls if r.get("dir") == "up")
    print(f"\n[DIAG] rolls up (re-strikeia) / down (horizontal): {ups}/{n-ups}")

    _gate_roll_rule(rolls)


def _gate_roll_rule(rolls):
    """GATE DA REGRA DO ROLL -- o roll e a peca mais critica da estrutura, entao ele tem gate
    proprio, nao so diagnostico.

    A fonte manda: BAIXA -> rola horizontal e NAO re-strikeia. Mas num bear o strike fica
    parado enquanto o spot cai, ou seja, ele deriva p/ ITM; se sair da janela `strike_filter`
    o motor pega "o mais proximo" e re-strikeia EM SILENCIO -- exatamente onde a regra proibe,
    e exatamente no ano (2022) que decide a tese. `k_gap` mede esse desvio em pontos.

    k_gap > 0 num roll "down" = aquele roll desobedeceu a regra -> o P&L dele esta contaminado."""
    have = [r for r in rolls if r.get("k_gap") not in (None, "")]
    if not have:
        print("\n[GATE] REGRA DO ROLL: coluna k_gap ausente (run anterior a instrumentacao)"
              "\n  -> NAO da p/ afirmar que os rolls 'down' mantiveram o strike. Re-rodar p/ saber.")
        return
    downs = [r for r in have if r.get("dir") == "down"]
    dirty = [r for r in downs if f(r, "k_gap", 0.0) > 0]
    print("\n[GATE] REGRA DO ROLL  (baixa => horizontal, SEM re-strike)")
    if not downs:
        print("  nenhum roll 'down' no periodo")
        return
    if not dirty:
        print(f"  {len(downs)} rolls 'down', todos com k_gap=0 -> a regra foi obedecida  OK")
        return
    worst = max(dirty, key=lambda r: f(r, "k_gap", 0.0))
    pnl_dirty = sum(f(r, "net_roll", 0.0) for r in dirty)
    print(f"  !! {len(dirty)}/{len(downs)} rolls 'down' RE-STRIKEARAM sem autorizacao (k_gap>0)")
    print(f"     pior desvio: {f(worst,'k_gap')} pts em {worst.get('date')} (S={worst.get('S')})")
    print(f"     net desses rolls: {pnl_dirty:+.2f} pts (${pnl_dirty*MULT:+,.0f}) <- CONTAMINADO")
    print(f"     causa provavel: strike derivou p/ fora de strike_filter -> alargar a janela")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    for a in sys.argv[1:]:
        report(Path(a))
    print("\nNAO respondido por este backtest (declarar, nao esconder):")
    print("  - margem sob portfolio margin: fora do v1 por decisao (BuyingPowerModel.NULL)")
    print("  - degradacao do basis RUT x SPX no crash: as correlacoes convergem p/ 1")
    print("    exatamente quando o hedge importa; rodar os dois mede condicao normal")
    print("  - risco de execucao do roll: o backtest assume que a sexta sempre acontece")


if __name__ == "__main__":
    main()
