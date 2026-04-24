#!/usr/bin/env python3
"""
gex_compare.py
--------------
Compara níveis de GEX/OI entre três fontes:
  1. TradingLit  — ThinkScript com OI (Open Interest) por strike
  2. Barchart    — pipeline local (gex_history_spx.json / gex_history_ndx.json)
  3. MenthorQ    — entrada manual (preencher MENTHORQ_DATA abaixo)

Uso:
  1. Copie o ThinkScript do TradingLit e salve em tradinglit_script.txt
     (ou cole diretamente na variável TRADINGLIT_SCRIPT abaixo)
  2. Preencha MENTHORQ_DATA com os níveis que você ver no MenthorQ
  3. python scripts/gex_compare.py

NOTA METODOLÓGICA:
  TradingLit  → Open Interest puro (nº de contratos por strike)
  Barchart    → GEX = OI × gamma × spot × 100 (sensibilidade ao delta-hedging)
  MenthorQ    → Net GEX (metodologia proprietária, similar ao Barchart)
  OI ≠ GEX, mas os strikes mais relevantes tendem a convergir.
  Divergências grandes entre OI e GEX indicam que o flow está em strikes
  com gamma baixo (far OTM / LEAPS) — menos relevante para o desk.
"""

import re
import json
import sys
from pathlib import Path
from datetime import date

# ─── CONFIGURAÇÃO MANUAL — MenthorQ ──────────────────────────────────────────
# Preencha com os níveis que você vê no MenthorQ para esta semana.
# Formato: lista de inteiros (SPX) ou None se não disponível.
MENTHORQ_DATA = {
    "SPX": {
        "gamma_flip":  None,   # ex: 6650
        "call_walls":  [],     # ex: [7000, 6900, 7050]
        "put_walls":   [],     # ex: [6700, 6500, 6300]
    },
    "NDX": {
        "gamma_flip":  None,
        "call_walls":  [],
        "put_walls":   [],
    },
}

# ─── TRADINGLIT — fonte do script ─────────────────────────────────────────────
# Opção A: arquivo externo
_SCRIPT_FILE = Path(__file__).parent.parent / "tradinglit_script.txt"

# Opção B: cole diretamente aqui (string vazia = usa arquivo)
TRADINGLIT_SCRIPT = ""

# ─── CAMINHOS DOS JSON LOCAIS ─────────────────────────────────────────────────
ROOT        = Path(__file__).parent.parent
HISTORY_SPX = ROOT / "state" / "gex" / "gex_history_spx.json"
HISTORY_NDX = ROOT / "state" / "gex" / "gex_history_ndx.json"


# ─── PARSER TRADINGLIT ────────────────────────────────────────────────────────

def parse_tradinglit(script: str) -> dict[str, dict]:
    """
    Extrai call/put OI levels e premiums por ticker do ThinkScript do TradingLit.
    Retorna: {TICKER: {calls:[float], puts:[float], call_premium:float, put_premium:float}}
    """
    result = {}
    # Cada bloco: GetSymbol() == "TICKER") {... dados ...}
    pattern = re.compile(
        r'GetSymbol\(\)\s*==\s*"(\w+)"\)\s*\{([^}]+)\}',
        re.DOTALL,
    )
    for m in pattern.finditer(script):
        ticker = m.group(1)
        block  = m.group(2)

        cp = re.search(r'total_call_premium\s*=\s*([\d.]+)', block)
        pp = re.search(r'total_put_premium\s*=\s*([\d.]+)',  block)
        calls = [float(v) for v in re.findall(r'oi_call_\d\s*=\s*([\d.]+)', block)]
        puts  = [float(v) for v in re.findall(r'oi_put_\d\s*=\s*([\d.]+)',  block)]

        result[ticker] = {
            "calls":         sorted(set(calls), reverse=True),
            "puts":          sorted(set(puts),  reverse=True),
            "call_premium":  float(cp.group(1)) if cp else 0.0,
            "put_premium":   float(pp.group(1)) if pp else 0.0,
        }
    return result


# ─── LEITURA GEX LOCAL (Barchart) ────────────────────────────────────────────

def load_barchart(json_file: Path) -> dict | None:
    if not json_file.exists():
        return None
    try:
        history = json.loads(json_file.read_text(encoding="utf-8"))
        return history[-1] if history else None
    except Exception:
        return None


# ─── FORMATADORES ────────────────────────────────────────────────────────────

def fmt_levels(levels: list, n: int = 5) -> str:
    if not levels:
        return "—"
    return "  ".join(f"${int(v):,}" for v in levels[:n])

def fmt_prem(v: float) -> str:
    if v >= 1_000_000:
        return f"${v/1_000_000:.1f}M"
    if v >= 1_000:
        return f"${v/1_000:.0f}K"
    return f"${v:.0f}"

def pct_diff(a: float, b: float) -> str:
    if a and b:
        return f"{abs(a-b)/b*100:.1f}%"
    return "—"


# ─── BLOCO DE COMPARAÇÃO POR TICKER ──────────────────────────────────────────

def compare_ticker(
    ticker: str,
    tl_data: dict | None,
    bc_data: dict | None,
    mq_data: dict | None,
    spy_to_spx: float | None = None,
    qqq_to_ndx: float | None = None,
):
    W = 70
    print(f"\n{'='*W}")
    print(f"  {ticker}  -- Comparacao de Niveis  --  {date.today():%d/%m/%Y}")
    print(f"{'='*W}")

    # ── TradingLit ──────────────────────────────────────────────────────────
    print("\n  [1] TRADINGLIT  (Open Interest — contratos)")
    if tl_data:
        # Conversão SPY→SPX ou QQQ→NDX se necessário
        factor_label = ""
        calls = tl_data["calls"]
        puts  = tl_data["puts"]

        if ticker == "SPX" and spy_to_spx:
            spy = tl_data  # já é SPX direto ou convertido
            # Também mostrar SPY convertido como referência
            print(f"    SPX direto:")
        elif ticker == "NDX" and qqq_to_ndx:
            calls = [round(v * qqq_to_ndx) for v in calls]
            puts  = [round(v * qqq_to_ndx) for v in puts]
            factor_label = f"  (QQQ × {qqq_to_ndx:.1f})"
        print(f"    Call OI{factor_label}:   {fmt_levels(calls)}")
        print(f"    Put  OI{factor_label}:   {fmt_levels(puts)}")
        print(f"    Call Premium: {fmt_prem(tl_data['call_premium'])}   "
              f"Put Premium: {fmt_prem(tl_data['put_premium'])}   "
              f"Ratio C/P: {tl_data['call_premium']/(tl_data['put_premium'] or 1):.1f}×")
    else:
        print("    Dados não disponíveis no script fornecido.")

    # ── Barchart (GEX local) ───────────────────────────────────────────────
    print(f"\n  [2] BARCHART  (GEX — delta-hedging exposure)")
    if bc_data:
        flip = bc_data.get("gflip")
        pos  = bc_data.get("pos", [])
        neg  = bc_data.get("neg", [])
        conf = bc_data.get("conf", [])
        expiry = bc_data.get("expiry", "?")
        print(f"    Expiry:       {expiry}")
        print(f"    Gamma Flip:   ${flip:,}  ← dealer behavior switches here")
        print(f"    Call Walls:   {fmt_levels(pos)}  (positive GEX — resistance)")
        print(f"    Put Walls:    {fmt_levels(neg)}  (negative GEX — support)")
        if conf:
            print(f"    Confluences:  {fmt_levels(sorted(conf))}")
    else:
        print("    JSON local não encontrado.")

    # ── MenthorQ (manual) ──────────────────────────────────────────────────
    print(f"\n  [3] MENTHORQ  (entrada manual)")
    if mq_data:
        flip = mq_data.get("gamma_flip")
        cw   = mq_data.get("call_walls", [])
        pw   = mq_data.get("put_walls",  [])
        if flip or cw or pw:
            if flip: print(f"    Gamma Flip:   ${flip:,}")
            if cw:   print(f"    Call Walls:   {fmt_levels(cw)}")
            if pw:   print(f"    Put Walls:    {fmt_levels(pw)}")
        else:
            print("    (não preenchido — edite MENTHORQ_DATA no topo do script)")
    else:
        print("    (não preenchido — edite MENTHORQ_DATA no topo do script)")

    # ── Análise de Convergência ────────────────────────────────────────────
    print(f"\n  [CONVERGÊNCIA]")
    if tl_data and bc_data:
        tl_calls = set()
        if ticker == "SPX":
            tl_calls = {int(v) for v in tl_data["calls"]}
        elif ticker == "NDX" and qqq_to_ndx:
            tl_calls = {round(v * qqq_to_ndx / 25) * 25 for v in tl_data["calls"]}

        bc_calls  = set(bc_data.get("pos", []))
        bc_puts   = set(bc_data.get("neg", []))
        bc_flip   = bc_data.get("gflip")

        # Verificar se os top OI calls convergem com GEX call walls (±100 pts SPX)
        tol = 100 if ticker == "SPX" else 300
        convergentes = []
        for tl_lvl in tl_calls:
            for bc_lvl in bc_calls:
                if abs(tl_lvl - bc_lvl) <= tol:
                    convergentes.append((tl_lvl, bc_lvl))

        if convergentes:
            for tl_lvl, bc_lvl in convergentes:
                diff = abs(tl_lvl - bc_lvl)
                print(f"    OK TradingLit OI ${tl_lvl:,} ~ Barchart GEX ${bc_lvl:,}  (delta: {diff} pts)")
        else:
            print(f"    ! Nenhum call OI do TradingLit converge com GEX calls (tolerância ±{tol})")

        # Nota sobre divergência no lado de puts
        tl_puts_raw = tl_data["puts"] if ticker == "SPX" else [round(v * (qqq_to_ndx or 1)) for v in tl_data["puts"]]
        if tl_puts_raw and bc_puts:
            tl_put_max = max(tl_puts_raw)
            bc_put_min = min(bc_puts)
            if tl_put_max < bc_put_min - tol:
                print(f"    ~ Put OI (TL max=${int(tl_put_max):,}) bem abaixo dos Put Walls GEX (min=${bc_put_min:,})")
                print(f"      → OI concentrado em puts OTM/LEAPS (hedges distantes); GEX support é near-money")

        # Gamma flip como contexto
        if bc_flip:
            tl_puts_near = [v for v in tl_puts_raw if isinstance(v, (int, float)) and abs(v - bc_flip) <= 200]
            if tl_puts_near:
                print(f"    OK Put OI perto do Gamma Flip (${bc_flip:,}): {[f'${int(v):,}' for v in tl_puts_near]}")
    else:
        print("    Dados insuficientes para análise de convergência.")


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    # Carregar ThinkScript
    script = TRADINGLIT_SCRIPT.strip()
    if not script:
        if _SCRIPT_FILE.exists():
            script = _SCRIPT_FILE.read_text(encoding="utf-8")
        else:
            print("[ERRO] Cole o ThinkScript em TRADINGLIT_SCRIPT no topo do script,")
            print(f"       ou salve em: {_SCRIPT_FILE}")
            sys.exit(1)

    print("Parseando TradingLit ThinkScript...")
    tl = parse_tradinglit(script)
    print(f"  Tickers encontrados: {', '.join(sorted(tl.keys()))}")

    # Carregar GEX locais
    bc_spx = load_barchart(HISTORY_SPX)
    bc_ndx = load_barchart(HISTORY_NDX)

    # Fatores de conversão ETF → índice
    # SPY × ~10 ~ SPX  |  QQQ × ~41 ~ NDX  (valores aproximados, ajuste se necessário)
    spy_to_spx = 10.0
    qqq_to_ndx = 41.0

    # ── Comparação SPX ────────────────────────────────────────────────────
    tl_spx = tl.get("SPX")
    if not tl_spx and "SPY" in tl:
        # Converter SPY → SPX
        spy = tl["SPY"]
        tl_spx = {
            "calls":        [round(v * spy_to_spx) for v in spy["calls"]],
            "puts":         [round(v * spy_to_spx) for v in spy["puts"]],
            "call_premium": spy["call_premium"],
            "put_premium":  spy["put_premium"],
        }
        print(f"\n  SPX não encontrado diretamente → usando SPY × {spy_to_spx:.0f}")

    compare_ticker("SPX", tl_spx, bc_spx, MENTHORQ_DATA.get("SPX"), spy_to_spx=spy_to_spx)

    # ── Comparação NDX ────────────────────────────────────────────────────
    tl_ndx = tl.get("NDX")
    tl_qqq = tl.get("QQQ")
    if not tl_ndx and tl_qqq:
        tl_ndx_conv = {
            "calls":        [round(v * qqq_to_ndx) for v in tl_qqq["calls"]],
            "puts":         [round(v * qqq_to_ndx) for v in tl_qqq["puts"]],
            "call_premium": tl_qqq["call_premium"],
            "put_premium":  tl_qqq["put_premium"],
        }
        print(f"\n  NDX não encontrado diretamente → usando QQQ × {qqq_to_ndx:.0f}")
    else:
        tl_ndx_conv = tl_ndx

    compare_ticker("NDX", tl_ndx_conv, bc_ndx, MENTHORQ_DATA.get("NDX"), qqq_to_ndx=qqq_to_ndx)

    # ── IWM (só TradingLit, sem GEX local) ───────────────────────────────
    if "IWM" in tl:
        print(f"\n{'='*70}")
        print(f"  IWM  —  TradingLit OI  (referência, sem GEX local)")
        print(f"{'='*70}")
        iwm = tl["IWM"]
        print(f"  Call OI:   {fmt_levels(iwm['calls'])}")
        print(f"  Put  OI:   {fmt_levels(iwm['puts'])}")
        print(f"  Ratio C/P: {iwm['call_premium']/(iwm['put_premium'] or 1):.1f}×")

    print(f"\n{'='*70}")
    print("  Para completar a comparação com MenthorQ:")
    print("  Edite MENTHORQ_DATA no topo deste script e rode novamente.")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
