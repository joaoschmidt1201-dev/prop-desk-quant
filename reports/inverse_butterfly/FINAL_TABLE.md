# Inverse Butterfly 1-2-1 — TABELA FINAL (mid, 5,5 anos, SPX)
*Cada DTE na cadência/saída correta. mid ≈ alcançável (near-ATM líquido, verificado em minuto).
best2 (0,50/0,60σ em 7/15/45) entra como bônus depois.*

## 1. Sweet spot de WIDTH (@ 30 DTE, sexta) — a alavanca estrutural

| Width | W (pts) | HOLD | WR | **TP 50%** |
|---|---|---|---|---|
| 0,15σ | 30 | +$5,7k | 90% | +$25,3k |
| 0,25σ | 50 | +$20,2k | 86% | +$41,2k |
| 0,40σ | 80 | +$38,1k | 79% | +$43,4k |
| 0,50σ | 95 | +$46,3k | 74% | **+$58,6k** |
| 0,60σ | 115 | **+$60,7k** | 70% | +$56,6k |
| 0,75σ | 145 | +$45,2k | 63% | +$5,1k ⚠️ quebra |

→ **Sweet spot = 0,50-0,60σ.** Acima disso (0,75) a estrutura vira quase straddle e o TP raramente bate.

## 2. Matriz DTE × width (HOLD / TP 50%, mid)

| DTE | Entrada | Saída | HOLD @0,15 | TP50 @0,15 | HOLD @0,40 | TP50 @0,40 |
|---|---|---|---|---|---|---|
| 1 | diário | 12:00 exp | +$9,9k | +$46,8k | — | — |
| 4 | seg→sex | sexta abert. | −$0,6k | +$15,3k | +$11,3k | +$21,3k |
| 7 | sexta | DTE-rest/TP | −$0,5k | +$21,0k | — | — |
| **15** | sexta | DTE-rest/TP | +$14,1k | +$32,7k | **+$54,0k** | **+$62,0k** |
| 30 | sexta | DTE-rest/TP | +$5,7k | +$25,3k | +$38,1k | +$43,4k |
| **45** | sexta | DTE-rest/TP | +$8,7k | +$39,0k | +$31,1k | **+$62,0k** |

*(best2 vai preencher 0,50/0,60σ em 7/15/45.)*

## 3. Achados que importam

1. **TP 50% é a melhor saída em TODOS os DTEs.** Long-vol → tira o lucro quando o movimento acontece.
2. **Width largo amplifica** (0,40σ no 15 DTE leva o TP50 de $33k → $62k). Sweet spot 0,50-0,60σ.
3. **Saída "sexta na abertura" do 4 DTE é fraca** (−$885) — a estrutura devolve na manhã da expiração;
   no 4 DTE use TP (+$15-21k).
4. **1 DTE diário:** TP50 +$46,8k, mas são ~1.240 trades (entrada diária) = muito mais exposição a custo
   acumulado. O exit 12:00 puro dá só +$10k.

## 4. Melhores cenários (mid)

| # | Config | Saída | Net 5,5a (mid) |
|---|---|---|---|
| 🥇 | **15 DTE @ 0,40σ** | TP 50% | **+$62,0k** |
| 🥇 | **45 DTE @ 0,40σ** | TP 50% | **+$62,0k** |
| 🥈 | 30 DTE @ 0,50σ | TP 50% | +$58,6k |
| 🥉 | 30 DTE @ 0,60σ | HOLD | +$60,7k |
| — | 1 DTE diário | TP 50% | +$46,8k (muitos trades) |

## 5. Caveats honestos (pro CZ)
- **mid ≈ real** aqui (pernas near-ATM líquidas; spread real ~$150/trade verificado em minuto). TP é
  bruto da saída, mas o haircut é pequeno (combo no limite). Líquido fica perto do mid.
- **Lumpy por ano** (long-vol): paga em anos de movimento (2022/2025), sangra em ano calmo (2021).
  **Não há filtro de VIX confiável** (o "VIX 15-20 ruim" era 2021 disfarçado — artefato temporal).
- Headwind estrutural: **implied > realized (0,77-0,79)** — você paga um pouco caro pelo movimento.

## Veredito
**Forma viável = WIDTH largo (0,40-0,60σ) + semanal (15-45 DTE) + TP 50%.** Não é income constante;
é um **long-vol que paga +$58-62k/5,5a no mid** quando o mercado se move, com anos calmos negativos.
Candidato a forward-test: **15 DTE @ 0,40σ + TP 50%.**
