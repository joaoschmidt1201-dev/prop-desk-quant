"""
Suíte de testes da máquina de estados LINE-CROSS do Occurrence Scanner.

GABARITO = respostas do João (2026-07-08) para o catálogo
context/occurrence_sm_cenarios_gabarito.md. Cada cenário é uma sequência de
candles sobre MA plana=100 e banda=1 (upper=101, lower=99); testa a lógica de
scripts/occurrence_line_sm.py (o modelo "2 closes cruzando a LINHA").

RODAR:
  python -X utf8 scripts/test_occurrence_sm.py        # tabela PASS/FAIL
  python -X utf8 scripts/test_occurrence_sm.py -v      # + trilha de eventos
  pytest scripts/test_occurrence_sm.py

Notação de tokens (close vs linha, com controle de mecha):
  A  = close acima da borda de cima, SEM tocar a banda
  At = close acima da borda, mas a MECHA toca a banda
  u  = close dentro da banda, ACIMA da linha (toca)
  d  = close dentro da banda, ABAIXO da linha (toca)
  B  = close abaixo da borda de baixo (toca)
  uW = close em u, mas a MECHA fura a borda de baixo (caso S10)
  L  = close EXATO na linha da MA (toca) — regra: conta como bounce
  Bg = close abaixo da banda por GAP, mecha NÃO toca a banda (regra: conta cruzamento)
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field

import numpy as np

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from occurrence_line_sm import classify  # noqa: E402

MA = 100.0
BAND = 1.0          # upper=101, lower=99

# token -> (low, high, close)
_TOK = {
    "A":  (101.5, 102.5, 102.0),   # acima, não toca (low>upper)
    "At": (100.5, 102.5, 102.0),   # acima, mecha toca (low<=upper), close acima
    "u":  (99.8, 101.2, 100.5),    # dentro da banda, acima da linha
    "d":  (98.8, 100.2, 99.5),     # dentro da banda, abaixo da linha
    "B":  (97.5, 99.5, 98.0),      # abaixo do lower (high>=lower ainda toca)
    "uW": (98.5, 101.0, 100.5),    # close em u, mecha fura o lower
    "L":  (99.5, 100.5, 100.0),    # close EXATO na linha (toca a banda)
    "Bg": (94.0, 96.0, 95.0),      # abaixo da banda por gap, NÃO toca (high<lower)
    "D":  (96.5, 98.5, 97.5),      # abaixo da banda, NÃO toca (mirror de A) — estabelece lado abaixo
}


@dataclass
class Scenario:
    name: str
    tokens: list[str]
    expected: dict[str, int]        # {"bounce":_, "break":_, "false":_}
    note: str = ""
    flag: str = ""                  # observação (ex.: aguardando confirmação)
    events: list = field(default_factory=list, repr=False)


def _run(sc: Scenario):
    lows = np.array([_TOK[t][0] for t in sc.tokens])
    highs = np.array([_TOK[t][1] for t in sc.tokens])
    closes = np.array([_TOK[t][2] for t in sc.tokens])
    ma = np.full(len(sc.tokens), MA)
    band = np.full(len(sc.tokens), BAND)
    cB, cBk, cF, events = classify(highs, lows, closes, ma, band, start_idx=0)
    sc.events = events
    return cB, cBk, cF


# ============================ ÁTOMOS (S01–S14) ============================
ATOMS = [
    Scenario("S01_bounce_so_mecha", ["A", "A", "At", "A", "A"],
             {"bounce": 1, "break": 0, "false": 0}, "só a mecha toca → bounce"),
    Scenario("S02_bounce_close_na_banda", ["A", "u", "A"],
             {"bounce": 1, "break": 0, "false": 0}, "1 close na banda acima da linha → bounce"),
    Scenario("S03_bounce_consolidacao", ["A", "u", "u", "u", "u", "A"],
             {"bounce": 1, "break": 0, "false": 0}, "consolida acima da linha → 1 bounce (print1)"),
    Scenario("S04_false_1_cruza", ["A", "u", "d", "u", "A"],
             {"bounce": 0, "break": 0, "false": 1}, "1 close cruza a linha e volta → false"),
    Scenario("S05_break_down_up", ["A", "d", "d", "u", "A"],
             {"bounce": 0, "break": 2, "false": 0}, "2 closes abaixo (break down) + 2 acima (break up)"),
    Scenario("S06_break_down_up_longo", ["A", "d", "d", "d", "d", "A", "A"],
             {"bounce": 0, "break": 2, "false": 0},
             "break down no 2º d; segue abaixo; break up nos 2 A finais",
             flag="ajustei p/ 2 closes acima no fim (o original tinha só 1 A)"),
    Scenario("S07_whipsaw_falses", ["A", "u", "d", "u", "d", "u", "A"],
             {"bounce": 0, "break": 0, "false": 2}, "2 pokes de 1 close cada → 2 falses",
             flag="você escreveu 'False' (singular) — CONFIRMAR se é 1 ou 2"),
    Scenario("S08_break_down_up_viaB", ["A", "d", "B", "u", "A"],
             {"bounce": 0, "break": 2, "false": 0}, "d+B = 2 abaixo (break down) + u+A = 2 acima (break up)"),
    Scenario("S09_false_1B", ["A", "B", "A"],
             {"bounce": 0, "break": 0, "false": 1}, "1 close em B e volta → false"),
    Scenario("S10_bounce_mecha_furaB", ["A", "uW", "A"],
             {"bounce": 1, "break": 0, "false": 0}, "mecha fura B mas close fica em u → bounce"),
    Scenario("S11_break_BB", ["A", "B", "B"],
             {"bounce": 0, "break": 1, "false": 0}, "2 closes em B → break"),
    Scenario("S12_break_Bd", ["A", "B", "d"],
             {"bounce": 0, "break": 1, "false": 0}, "B+d = 2 closes abaixo da linha → break"),
    Scenario("S13_break_dB", ["A", "d", "B"],
             {"bounce": 0, "break": 1, "false": 0}, "d+B = 2 closes abaixo da linha → break"),
    Scenario("S14_break_tendencia", ["A", "B", "B", "B", "B"],
             {"bounce": 0, "break": 1, "false": 0}, "break no 2º B; resto é continuação → 1 break"),
]

# ============================ CADEIAS (C01–C06) ============================
CHAINS = [
    Scenario("C01_break_down_up", ["A", "B", "B", "u", "u"],
             {"bounce": 0, "break": 2, "false": 0}, "break down no 2º B + break up no 2º u"),
    Scenario("C02_V_no_nivel", ["A", "d", "B", "B", "u", "A"],
             {"bounce": 0, "break": 2, "false": 0}, "break down no 1º B + break up no A"),
    Scenario("C03_bounce_rebounce", ["A", "u", "A", "At", "u", "A"],
             {"bounce": 2, "break": 0, "false": 0}, "2 toques separados → 2 bounces"),
    Scenario("C04_false_depois_break", ["A", "B", "u", "A", "A", "d", "B", "B"],
             {"bounce": 0, "break": 1, "false": 1}, "false no 1º B + break no 2º abaixo depois"),
    Scenario("C05_break_down_up_seguido", ["A", "B", "B", "d", "u", "A", "A"],
             {"bounce": 0, "break": 2, "false": 0}, "break down no 2º B + break up no 2º acima (1º A)"),
    Scenario("C06_serra_3breaks", ["A", "B", "B", "A", "A", "B", "B"],
             {"bounce": 0, "break": 3, "false": 0}, "break down + break up + break down"),
]

# ============================ BORDAS confirmadas (João 2026-07-08) ============================
EDGES = [
    Scenario("E_close_na_linha_bounce", ["A", "L", "A"],
             {"bounce": 1, "break": 0, "false": 0}, "close exato na linha, tocou e voltou → bounce (#2)"),
    Scenario("E_gap_break", ["A", "Bg", "Bg"],
             {"bounce": 0, "break": 1, "false": 0}, "2 closes abaixo por gap, sem tocar → break (#5)"),
    Scenario("E_gap_false", ["A", "Bg", "A"],
             {"bounce": 0, "break": 0, "false": 1}, "1 close abaixo por gap e volta → false (#5)"),
    # #3 — lado inicial vem do 1º close (aqui começa ABAIXO da linha)
    Scenario("E_lado_inicial_break_up", ["B", "u", "A"],
             {"bounce": 0, "break": 1, "false": 0}, "começa abaixo; 2 closes acima → break up (#3)"),
    Scenario("E_lado_inicial_bounce_baixo", ["D", "d", "D"],
             {"bounce": 1, "break": 0, "false": 0}, "começa abaixo; toca a linha de baixo e volta → bounce (#3)"),
    # #4 — episódio incompleto na última barra é ignorado
    Scenario("E_incompleto_toque_fim", ["A", "u"],
             {"bounce": 0, "break": 0, "false": 0}, "toca na última barra e o gráfico acaba → ignora (#4)"),
    Scenario("E_incompleto_cruza_fim", ["A", "d"],
             {"bounce": 0, "break": 0, "false": 0}, "1 close cruza na última barra, não resolve → ignora (#4)"),
]

SCENARIOS = ATOMS + CHAINS + EDGES


def check(sc: Scenario):
    got = _run(sc)
    exp = (sc.expected["bounce"], sc.expected["break"], sc.expected["false"])
    return got == exp, got, exp


def main(verbose: bool) -> int:
    print(f"{'CASO':<30} {'GABARITO B/Bk/F':<17} {'OBTIDO':<10} STATUS")
    print("-" * 78)
    fails = 0
    for sc in SCENARIOS:
        ok, got, exp = check(sc)
        status = "PASS" if ok else "*** FAIL ***"
        if not ok:
            fails += 1
        flag = f"  ⚑ {sc.flag}" if sc.flag else ""
        print(f"{sc.name:<30} {str(exp):<17} {str(got):<10} {status}{flag}")
        if verbose:
            print(f"    tokens: {' '.join(sc.tokens)}  | {sc.note}")
            for idx, kind, side in sc.events:
                print(f"      → {kind:<7} @barra{idx} (lado antes: {'acima' if side > 0 else 'abaixo'})")
    print("-" * 78)
    print(f"{'TODOS PASSARAM ✔' if not fails else f'{fails} FALHA(S)'}  "
          f"({len(SCENARIOS)} cenários)")
    return 1 if fails else 0


def test_all_scenarios():
    for sc in SCENARIOS:
        ok, got, exp = check(sc)
        assert ok, f"{sc.name}: esperado {exp}, obtido {got}  (tokens: {' '.join(sc.tokens)})"


if __name__ == "__main__":
    sys.exit(main(verbose="-v" in sys.argv))
