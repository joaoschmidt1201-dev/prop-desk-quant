"""
Occurrence Scanner — máquina de estados "LINE-CROSS" (spec do João, 2026-07-08).

MODELO (derivado dos gabaritos S01-S14, C01-C06 do João):
  A LINHA da MA é o que separa os lados. As BORDAS da banda NÃO importam para
  break/false — a banda só serve para detectar o TOQUE do bounce. Só o CLOSE
  cruza a linha (a mecha nunca conta para cruzamento).

  Estado: `side` = lado estabelecido (+1 acima da linha / -1 abaixo).

  BREAK  = 2 closes CONSECUTIVOS do lado OPOSTO ao `side` (captura no 2º).
           O `side` vira para o novo lado. Breaks encadeiam (down->up->down...).
  FALSE  = exatamente 1 close do lado oposto que VOLTA antes do 2º (captura na volta).
           `side` não muda.
  BOUNCE = a barra TOCA a banda (mecha ou close) e o episódio termina (sai da banda)
           SEM nenhum close ter cruzado a linha. Um bounce por toque contínuo.

  NÃO há lookahead/winSize: tudo é event-driven (o 2º close confirma o break;
  a volta confirma o false; sair da banda confirma o bounce).

Isto NÃO é a lógica antiga do occurrence_matrix.pine (aquela é far-edge + timer).
É a nova spec, a validar contra a suíte antes de portar para o Pine de produção.
"""
from __future__ import annotations

import numpy as np


def classify(high, low, close, ma, band, start_idx: int = 1):
    """Retorna (cBounce, cBreak, cFalse, events).
    events = lista de (idx, kind, side_before) — idx = barra em que o evento fecha."""
    n = len(close)
    cB = cBk = cF = 0
    events: list[tuple[int, str, int]] = []

    side: int | None = None      # +1 acima / -1 abaixo (lado estabelecido)
    opp_run = 0                   # closes consecutivos do lado oposto
    in_touch = False             # dentro de um episódio de toque na banda
    touch_crossed = False        # nesse episódio, algum close cruzou a linha?

    for i in range(n):
        L = ma[i]
        b = band[i]
        if not (np.isfinite(L) and np.isfinite(b)):
            continue
        c = close[i]
        upper = L + b
        lower = L - b
        touched = (low[i] <= upper) and (high[i] >= lower)
        pos = 1 if c > L else (-1 if c < L else 0)   # lado do CLOSE vs a linha

        # ---- estabelece o lado inicial na 1ª barra classificável ----
        if side is None:
            if i >= start_idx and pos != 0:
                side = pos
            continue

        is_opp = (pos == -side)
        is_est = (pos == side)     # pos == 0 (em cima da linha) NÃO é oposto → tratado como estabelecido

        # ================= detector de LINHA (break / false) =================
        if is_opp:
            opp_run += 1
            touch_crossed = True                     # cruzou → mata candidatura a bounce
            if opp_run >= 2:                         # BREAK
                cBk += 1
                events.append((i, "break", side))
                side = -side                         # vira o lado
                opp_run = 0
                in_touch = False                     # episódio consumido pelo break
                touch_crossed = False
        else:
            if opp_run == 1:                         # voltou após 1 close oposto → FALSE
                cF += 1
                events.append((i, "false", side))
            opp_run = 0

        # ================= detector de TOQUE (bounce) =================
        if touched:
            if not in_touch:
                in_touch = True
                touch_crossed = is_opp               # se já entrou cruzando, não é bounce
        else:
            if in_touch:                             # episódio de toque terminou (saiu da banda)
                if not touch_crossed:                # tocou e saiu sem cruzar a linha → BOUNCE
                    cB += 1
                    events.append((i, "bounce", side))
                in_touch = False
                touch_crossed = False

    # episódio de toque aberto no fim dos dados (E03): descartado (incompleto)
    return cB, cBk, cF, events
