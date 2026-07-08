"""
Suíte da máquina BAND-ZONE (spec do CZ, áudio 2026-07-08) — scripts/occurrence_band_sm.py.

Gabaritos DERIVADOS do conceito do CZ ("banda = MA gorda; bounce = chegar na banda;
false/break = atravessar a banda"). Marquei com ⚑CHANGED os cenários cujo rótulo MUDA vs o
modelo LINE-CROSS anterior (é a mudança que o CZ pediu — dip que só entra na banda = bounce).

RODAR: python -X utf8 scripts/test_occurrence_band.py [-v]
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field

import numpy as np

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from occurrence_band_sm import classify_band  # noqa: E402

MA = 100.0
BAND = 1.0    # upper=101, lower=99

_TOK = {
    "A":  (101.5, 102.5, 102.0),   # acima da banda, não toca
    "At": (100.5, 102.5, 102.0),   # acima da banda, mecha toca
    "u":  (99.8, 101.2, 100.5),    # dentro da banda, acima da linha
    "d":  (98.8, 100.2, 99.5),     # dentro da banda, abaixo da linha (NÃO passa a borda de fora)
    "B":  (97.5, 99.5, 98.0),      # abaixo da borda de fora (atravessa)
    "uW": (98.5, 101.0, 100.5),    # close em u, mecha fura o lower
    "D":  (96.5, 98.5, 97.5),      # abaixo da banda, não toca (estabelece lado abaixo)
}


@dataclass
class Scenario:
    name: str
    tokens: list[str]
    expected: dict[str, int]
    note: str = ""
    events: list = field(default_factory=list, repr=False)


def _run(sc):
    lows = np.array([_TOK[t][0] for t in sc.tokens])
    highs = np.array([_TOK[t][1] for t in sc.tokens])
    closes = np.array([_TOK[t][2] for t in sc.tokens])
    ma = np.full(len(sc.tokens), MA)
    band = np.full(len(sc.tokens), BAND)
    cB, cBk, cF, events = classify_band(highs, lows, closes, ma, band, start_idx=0)
    sc.events = events
    return cB, cBk, cF


SCENARIOS = [
    # --- bounces: tocar a banda e voltar (a linha da MA por dentro não importa) ---
    Scenario("S01_bounce_mecha", ["A", "A", "At", "A", "A"], {"bounce": 1, "break": 0, "false": 0}),
    Scenario("S02_bounce", ["A", "u", "A"], {"bounce": 1, "break": 0, "false": 0}),
    Scenario("S03_bounce_consol", ["A", "u", "u", "u", "u", "A"], {"bounce": 1, "break": 0, "false": 0}),
    Scenario("S04_dip_na_banda_BOUNCE", ["A", "u", "d", "u", "A"], {"bounce": 1, "break": 0, "false": 0},
             "⚑CHANGED (era false): cruzou a linha por dentro mas não passou a banda → bounce (print1/2)"),
    Scenario("S05_2closes_na_banda_BOUNCE", ["A", "d", "d", "u", "A"], {"bounce": 1, "break": 0, "false": 0},
             "⚑CHANGED (era break×2): 2 closes abaixo da linha mas dentro da banda → bounce"),
    Scenario("S06_ride_na_banda_BOUNCE", ["A", "d", "d", "d", "d", "A", "A"], {"bounce": 1, "break": 0, "false": 0},
             "⚑CHANGED: anda dentro da banda e volta → bounce"),
    Scenario("S07_whipsaw_BOUNCE", ["A", "u", "d", "u", "d", "u", "A"], {"bounce": 1, "break": 0, "false": 0},
             "⚑CHANGED (era 2 false): serrou dentro da banda → bounce"),
    Scenario("S10_bounce_mecha_furaB", ["A", "uW", "A"], {"bounce": 1, "break": 0, "false": 0}),
    # --- false: passa a borda de fora 1x e volta ---
    Scenario("S08_poke_e_volta_FALSE", ["A", "d", "B", "u", "A"], {"bounce": 0, "break": 0, "false": 1},
             "⚑CHANGED (era break×2): passou a borda (B) 1x e voltou → false"),
    Scenario("S09_false_B", ["A", "B", "A"], {"bounce": 0, "break": 0, "false": 1}),
    Scenario("S12_poke_volta_banda_FALSE", ["A", "B", "d"], {"bounce": 0, "break": 0, "false": 1},
             "⚑CHANGED (era break): furou a borda 1x, voltou pra dentro → false"),
    # --- break: atravessa a banda (2 closes além da borda de fora) ---
    Scenario("S11_break", ["A", "B", "B"], {"bounce": 0, "break": 1, "false": 0}),
    Scenario("S14_break_tendencia", ["A", "B", "B", "B", "B"], {"bounce": 0, "break": 1, "false": 0}),
    Scenario("C06_serra_3breaks", ["A", "B", "B", "A", "A", "B", "B"], {"bounce": 0, "break": 3, "false": 0},
             "atravessa a banda inteira 3x (B abaixo, A acima) → 3 breaks"),
    Scenario("C03_2bounces", ["A", "u", "A", "At", "u", "A"], {"bounce": 2, "break": 0, "false": 0},
             "2 toques separados → 2 bounces"),
    # --- lado inicial abaixo da banda (#3) ---
    Scenario("E_inicial_abaixo_bounce", ["D", "d", "D"], {"bounce": 1, "break": 0, "false": 0},
             "começa abaixo da banda; toca de baixo e volta → bounce"),
    # --- incompleto no fim é ignorado (#4) ---
    Scenario("E_incompleto_fim", ["A", "d"], {"bounce": 0, "break": 0, "false": 0}),
    Scenario("S13_incompleto", ["A", "d", "B"], {"bounce": 0, "break": 0, "false": 0},
             "⚑CHANGED (era break): só 1 close além da borda, fim dos dados → incompleto, ignora"),
    # --- v2: rejeição / re-arme (conserta MERGE + POISON) — gabaritos do João 2026-07-08 ---
    Scenario("V2_AuA", ["A", "u", "A"], {"bounce": 1, "break": 0, "false": 0},
             "A u A → sempre bounce"),
    Scenario("V2_AuuA", ["A", "u", "u", "A"], {"bounce": 1, "break": 0, "false": 0},
             "A u u A → 1 bounce"),
    Scenario("V2_AdA", ["A", "d", "A"], {"bounce": 1, "break": 0, "false": 0},
             "A d A → bounce (dip na banda e volta)"),
    Scenario("V2_AduA", ["A", "d", "u", "A"], {"bounce": 1, "break": 0, "false": 0},
             "A d u → bounce por rejeição (volta acima da linha)"),
    Scenario("V2_false_depois_bounce", ["A", "u", "B", "d", "A", "d", "A"],
             {"bounce": 1, "break": 0, "false": 1},
             "POISON conserto: false, e um bounce POSTERIOR conta"),
    Scenario("V2_dois_bounces_separados", ["A", "u", "A", "A", "d", "A"],
             {"bounce": 2, "break": 0, "false": 0},
             "MERGE conserto: 2 aproximações separadas → 2 bounces"),
    Scenario("V2_whipsaw_1", ["A", "u", "d", "u", "d", "u", "A"], {"bounce": 1, "break": 0, "false": 0},
             "serra dentro da banda numa aproximação → 1 bounce"),
    Scenario("V2_tap_ride", ["A", "At", "At", "At", "A"], {"bounce": 1, "break": 0, "false": 0},
             "toque contínuo de mecha (ride) → 1 bounce, não um por candle"),
]


def main(verbose):
    print(f"{'CASO':<32} {'GABARITO':<14} {'OBTIDO':<10} STATUS")
    print("-" * 82)
    fails = 0
    for sc in SCENARIOS:
        got = _run(sc)
        exp = (sc.expected["bounce"], sc.expected["break"], sc.expected["false"])
        ok = got == exp
        if not ok:
            fails += 1
        print(f"{sc.name:<32} {str(exp):<14} {str(got):<10} {'PASS' if ok else '*** FAIL ***'}")
        if verbose and sc.note:
            print(f"    {sc.note}")
    print("-" * 82)
    print("TODOS PASSARAM ✔" if not fails else f"{fails} FALHA(S)")
    print(f"({len(SCENARIOS)} cenários — modelo BAND-ZONE do CZ)")
    return 1 if fails else 0


def test_all():
    for sc in SCENARIOS:
        got = _run(sc)
        exp = (sc.expected["bounce"], sc.expected["break"], sc.expected["false"])
        assert got == exp, f"{sc.name}: esperado {exp}, obtido {got}"


if __name__ == "__main__":
    sys.exit(main(verbose="-v" in sys.argv))
