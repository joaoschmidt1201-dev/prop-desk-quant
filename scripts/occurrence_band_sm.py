"""
Occurrence Scanner — máquina "BAND-ZONE v2" (spec CZ + refinamentos do João, 2026-07-08).

CONCEITO (CZ): a banda é uma "MA GORDA". Bounce = o preço CHEGA na banda e volta; false/break =
o preço ATRAVESSA a banda (passa a borda de fora).

v2 (correções do João): o bounce é contado por REJEIÇÃO (re-armado), não uma vez por saída-total
da banda — isso conserta os dois bugs que faziam perder bounces na EMA9:
  • MERGE: várias rejeições coladas na banda colapsavam num evento só.
  • POISON: um false "envenenava" o resto da ocupação e nenhum bounce posterior contava.

REGRA:
  side = lado estabelecido (pela borda: acima da banda +1 / abaixo -1).
  BREAK = 2 closes consecutivos além da borda de fora (o lado vira; encadeia).
  FALSE = 1 close além da borda de fora que volta.
  BOUNCE: uma APROXIMAÇÃO abre num toque FRESCO (tocou agora, não tocava na barra anterior). Ela é
    elegível a bounce enquanto NÃO cruzar a borda de fora. Dispara quando o preço REJEITA:
      (a) o close volta pra região de ORIGEM (fora da borda de perto), ou
      (b) o close volta pro lado de origem da LINHA depois de ter ido pro lado oposto dela (dip e volta).
    1 bounce por aproximação. Após disparar por (b), precisa voltar à origem p/ re-armar. Um FALSE/BREAK
    desqualifica a aproximação, mas ao voltar à origem re-arma (é o conserto do POISON).

Validado em scripts/test_occurrence_band.py. Assinatura preservada (classify_band).
"""
from __future__ import annotations

import numpy as np


def classify_band(high, low, close, ma, band, start_idx: int = 0):
    """Retorna (cBounce, cBreak, cFalse, events). events = (idx, kind, side_before)."""
    n = len(close)
    cB = cBk = cF = 0
    events: list[tuple[int, str, int]] = []

    side = 0
    opp_run = 0                # closes consecutivos além da borda de fora (break/false)
    opp_idx = 0
    in_appr = False            # dentro de uma aproximação elegível a bounce
    appr_idx = 0
    appr_crossed_far = False   # cruzou a borda de fora nesta aproximação (mata o bounce)
    appr_below_line = False    # o close foi pro lado oposto da LINHA nesta aproximação
    need_origin = False        # já disparou por rejeição; precisa voltar à origem p/ re-armar
    prev_touched = False

    for i in range(n):
        L = ma[i]
        b = band[i]
        if not (np.isfinite(L) and np.isfinite(b)):
            continue
        upper = L + b
        lower = L - b
        c = close[i]
        touched = (low[i] <= upper) and (high[i] >= lower)

        # ---- estabelece o lado pela BORDA (acima/abaixo da banda) ----
        if side == 0:
            if i >= start_idx:
                if c > upper:
                    side = 1
                elif c < lower:
                    side = -1
            prev_touched = touched
            continue

        far      = (c < lower) if side > 0 else (c > upper)   # passou a borda de fora
        far_line = (c < L) if side > 0 else (c > L)           # close no lado oposto da LINHA
        at_origin = (c > upper) if side > 0 else (c < lower)  # close de volta na região de origem

        # ================= detector de BORDA (break / false) =================
        broke = False
        if far:
            if opp_run == 0:
                opp_idx = i
            opp_run += 1
            if opp_run >= 2:
                cBk += 1
                events.append((i, "break", side))
                broke = True
                side = -side
                opp_run = 0
        else:
            if opp_run == 1:
                cF += 1
                events.append((opp_idx, "false", side))
            opp_run = 0

        if broke:
            in_appr = False
            appr_crossed_far = False
            appr_below_line = False
            need_origin = True
            prev_touched = touched
            continue

        # ================= voltou à origem: fecha a aproximação (bounce se elegível) e re-arma =========
        if at_origin:
            need_origin = False
            if in_appr and not appr_crossed_far:
                cB += 1
                events.append((appr_idx, "bounce", side))
            in_appr = False
            appr_crossed_far = False
            appr_below_line = False

        # ================= abre aproximação num toque FRESCO / atualiza flags =================
        fresh = touched and not prev_touched
        if touched and not need_origin:
            if fresh and not in_appr:
                in_appr = True
                appr_idx = i
                appr_crossed_far = far
                appr_below_line = far_line
            elif in_appr:
                if far:
                    appr_crossed_far = True
                if far_line:
                    appr_below_line = True

        # ================= rejeição (b): voltou p/ o lado de origem da linha após ter cruzado ======
        if in_appr and not appr_crossed_far and appr_below_line and not far_line and not at_origin:
            cB += 1
            events.append((appr_idx, "bounce", side))
            in_appr = False
            appr_below_line = False
            need_origin = True

        prev_touched = touched

    return cB, cBk, cF, events
