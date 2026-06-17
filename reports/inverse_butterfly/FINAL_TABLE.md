# Inverse Butterfly 1-2-1 — TABELA FINAL (mid, 5,5 anos, SPX)
*Matriz DTE × width completa (best2 incluído). mid ≈ alcançável (near-ATM, verificado em minuto).
Net/WR = runtime (amostra completa). Sharpe/maxDD = amostra parcial (log truncado) → re-run limpo pendente.*

## 1. Matriz completa — HOLD / TP50 / TP75 (net $k, mid)

| DTE | 0,15σ | 0,25σ | 0,40σ | 0,50σ | 0,60σ | 0,75σ |
|---|---|---|---|---|---|---|
| 7 | −1/20/0 | — | — | 33/34/39 | 52/43/60 | — |
| **15** | 14/32/39 | — | 54/62/59 | 80/61/72 | **101/90/97** | — |
| 30 | 5/25/27 | 20/41/28 | 38/43/33 | 46/58/23 | 60/56/35 | 45/5/20 ⚠️ |
| **45** | 8/38/46 | — | 31/62/74 | 65/**105**/66 | 65/**118**/92 | — |

→ **Sweet spot subiu p/ 0,50-0,60σ nos prazos longos (15/45 DTE).** No 30 DTE quebra no 0,75; nos
longos o 0,60σ ainda escala forte.

## 2. Melhores cenários (net, mid)

| # | Config | Saída | Net 5,5a |
|---|---|---|---|
| 🥇 | **45 DTE @ 0,60σ** | TP 50% | **+$118k** |
| 🥈 | 45 DTE @ 0,50σ | TP 50% | +$105k |
| 🥉 | **15 DTE @ 0,60σ** | HOLD | +$101k (TP75 +$97k) |
| 4 | 45 DTE @ 0,60σ | TP 75% | +$92k |
| 5 | 15 DTE @ 0,50σ | HOLD | +$80k |

## 3. Achados
1. **TP é a melhor saída**, e o ótimo varia: TP25 → WR 92-94% (consistência); TP50 → net robusto;
   TP75 → melhor net em 45 DTE.
2. **Width largo (0,50-0,60σ) nos prazos longos é a maior alavanca** — 15 DTE vai de TP50 $32k (0,15σ)
   a HOLD $101k (0,60σ). 30 DTE quebra no 0,75; 15/45 ainda escalam no 0,60.
3. **4 DTE "sexta abertura" fraca** (−$885) — usar TP.

## 4. Métricas de risco (15 DTE @ 0,40σ; amostra parcial 2021-mai/25 → otimista)
| | net (full, confiável) | Sharpe (aprox) | maxDD (aprox) |
|---|---|---|---|
| HOLD | +$54k/78% | ~1,5 | −$13k |
| TP25 | +$48k/94% | ~3,0 | −$6k |
| TP50 | +$62k/88% | ~2,6 | −$8k |
→ TP melhora Sharpe (2-3) e corta maxDD à metade. **Re-run limpo (chunk/ano) pendente p/ Sharpe full.**

## 5. Caveats
- **mid ≈ real** (near-ATM líquido). Sharpe/maxDD acima são de amostra TRUNCADA pelo log free-tier
  (perdeu ~o último ano, que foi fraco) → **otimistas**; precisa re-run limpo.
- **Width 0,60σ = mais net MAS vale mais fundo (mais tail risk por trade) e WR menor** → o líder em net
  pode NÃO ser o líder em Sharpe. Decidir finalista por **risco-ajustado**, não só net.
- **Lumpy por ano** (long-vol); **sem filtro de VIX** (era artefato de 2021).
- Headwind: **implied > realized (0,77-0,79)**.

## 6. Valor de PORTFÓLIO (o argumento mais forte)
A IB é **long-vol** → negativamente correlacionada com o book short-vol do desk (Bull Put, IC, Batman).
**Paga quando os outros sangram** (mercado se move/crash). É o hedge que também é positive-EV.

## Veredito / próximos passos
**Finalistas (net):** 45 DTE @ 0,50-0,60σ + TP50 (+$105-118k) e 15 DTE @ 0,50-0,60σ (+$80-101k).
**Antes do forward-test:** (a) re-run limpo p/ Sharpe/maxDD full-sample (escolher finalista por risco-
ajustado, não net), (b) testar em 2-3 underlyings (diversificar a lumpiness). Forward-test como
diversificador long-vol do portfólio.
