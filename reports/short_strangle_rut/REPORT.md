# Short Strangle RUT — 28/35/42 DTE (QuantConnect, 5 anos, MID)

_Gerado 2026-06-25 · delta 10P/8C · fill mid · payoff analitico (NULL BP)_

## Comparacao das 12 close rules (net $ / WR)

| Close rule | 28 DTE | 35 DTE | 42 DTE |
|---|---|---|---|
| Hold to expiration | $212,766 / 92% | $236,888 / 92% | $285,458 / 93% |
| TP 25% | $64,176 / 99% | $72,360 / 99% | $93,867 / 100% |
| TP 50% | $120,266 / 98% | $151,896 / 98% | $163,184 / 98% |
| TP 75% | $162,727 / 95% | $195,791 / 94% | $221,009 / 95% |
| Exit @ 14 DTE | $83,286 / 81% | $100,738 / 81% | $131,066 / 81% |
| Exit @ 7 DTE | $116,130 / 82% | $159,024 / 82% | $203,953 / 86% |
| TP25 or 14DTE | $46,140 / 94% | $46,246 / 96% | $62,091 / 96% |
| TP50 or 14DTE | $74,243 / 85% | $96,146 / 91% | $115,923 / 89% |
| TP75 or 14DTE | $87,819 / 82% | $108,564 / 82% | $124,968 / 81% |
| TP25 or 7DTE | $44,448 / 97% | $68,213 / 98% | $79,023 / 98% |
| TP50 or 7DTE | $88,486 / 92% | $126,184 / 95% | $152,388 / 96% |
| TP75 or 7DTE | $115,758 / 85% | $158,233 / 87% | $186,371 / 89% |

## 28 DTE  (n=250 trades)

- credit med: 12.60 pts · dte med: 28
- delta put med/min/max: 0.100 / 0.083 / 0.131 · off-target 0/250
- delta call med/min/max: 0.080 / 0.064 / 0.133 · off-target 0/250 · skips 0
- por ano (hold): 2021 $23,574 (n=30) · 2022 $42,501 (n=51) · 2023 $25,382 (n=51) · 2024 $61,892 (n=51) · 2025 $44,406 (n=50) · 2026 $15,011 (n=17)
- por VIX (hold): <15 $28,556 (n=56) · 15-17 $56,332 (n=58) · 17-22 $72,104 (n=72) · 22-32 $47,561 (n=60) · 32+ $8,212 (n=4)

## 35 DTE  (n=249 trades)

- credit med: 14.15 pts · dte med: 35
- delta put med/min/max: 0.100 / 0.086 / 0.144 · off-target 0/249
- delta call med/min/max: 0.080 / 0.061 / 0.266 · off-target 2/249 · skips 0
- por ano (hold): 2021 $42,673 (n=30) · 2022 $39,763 (n=51) · 2023 $31,606 (n=51) · 2024 $61,064 (n=51) · 2025 $41,724 (n=50) · 2026 $20,058 (n=16)
- por VIX (hold): <15 $21,282 (n=56) · 15-17 $67,486 (n=57) · 17-22 $87,162 (n=72) · 22-32 $53,997 (n=60) · 32+ $6,961 (n=4)

## 42 DTE  (n=248 trades)

- credit med: 15.55 pts · dte med: 42
- delta put med/min/max: 0.100 / 0.087 / 0.220 · off-target 1/248
- delta call med/min/max: 0.081 / 0.062 / 0.196 · off-target 4/248 · skips 0
- por ano (hold): 2021 $51,380 (n=30) · 2022 $55,821 (n=51) · 2023 $41,700 (n=51) · 2024 $76,232 (n=51) · 2025 $41,308 (n=50) · 2026 $19,017 (n=15)
- por VIX (hold): <15 $38,610 (n=56) · 15-17 $66,439 (n=57) · 17-22 $92,228 (n=71) · 22-32 $79,355 (n=60) · 32+ $8,825 (n=4)

## Verificacao (prioridade #1 do CZ)

- Auto-consistencia: recompute trade-a-trade do log CTRADE bate com as runtime stats do
  motor ao dolar nas 3 configs. Deltas 0.10/0.08 (off-target raros, so vol alta).
- Auditoria vencedor (#1, 42DTE): 2021-06-04 RUT 2284.62, P2030/C2465, credito 15.05 pts,
  settle 2279.88 (ambos OTM) -> +$1.505. Confere.
- Auditoria pior trade (#191, 42DTE): 2025-02-21 RUT 2256.53, P2030/C2475, credito 15.2 pts,
  settle 2025-04-04 RUT 1827.52 (crash tarifas abr/2025, -19%) -> put ITM 202.48 -> -$18.728. Confere.

## Risco de cauda (importante p/ sizing)

Hold tem o melhor net mas carrega a cauda: o pior trade perdeu -$18.728 num ciclo. As saidas
por tempo cortariam essa perda especifica (14 DTE -$1.5k; 7 DTE -$223) mas no agregado perdem
dos vencedores. Naked = risco indefinido -> dimensionar margem (Reg-T/PM) e capital de cauda.

## Ressalvas (CZ)

- Headline = **mid**; slippage real a estimar (motor loga credit_cons = shorts@bid).
- Naked short = risco indefinido; equity do QC ignorada (NULL BP), P&L = payoff analitico no settle.
- Settle aproximado pelo fecho do RUT (RUTW = PM-settled).
- Detalhe por-trade das regras TP/DTE no app vem do log CTRADE (alocacao diaria do free tier).