# PL5 — BWB 1-2-2 de Puts (SPX) · Relatório de Backtest
*Gerado 2026-06-16 (execução autônoma) · charter: `context/PROJECT_pl5_bwb_backtest.md`*

## Resumo executivo
Backtest mecânico (v1 ESTÁTICA, sem o "tent"-tracking discricionário) da estrutura "PL5" vista
em vídeo: broken-wing put butterfly ratio **1/2/2** ancorada em delta (−30/−18/−3), SPX/SPXW,
entrada semanal (sexta), hold-to-expiry. **Achado central: a estrutura estática PERDE — e os fills
realistas pioram muito.** A tese do vídeo (curva consistente, ganho no crash) **não se replica** sem
a gestão discricionária.

## Validação do método (janela curta 2024-07, pré-crash Ago/2024) ✓
- Deltas saíram exatos (−0.298 / −0.180 / −0.030 vs alvos −0.30/−0.18/−0.03).
- Estrutura broken-wing correta (K1>K2>K3, tent + cauda); o trade pré-crash ganhou **+$2.302**
  (convexidade de crash funcionando ao vivo).
- Marcação viva (MFE/MAE, cruzamentos TP/SL gravados).
- **Fix de margem** (combo único `combo_market_order` + `_OptBpInit` BP-null): resolveu o crash
  `OptionStrategyPositionGroupBuyingPowerModel` que estourava com pernas/combos sobrepostos.

## Resultado — d21 (21 DTE, span 2021-06 → 2026-06, 178 trades)
| Métrica | Valor |
|---|---|
| **NET hold (analítico, Σ settle)** | **−$39.867** · WR 16% |
| **Equity QC (fills reais)** | **−$98.051 (−100%)** |
| Gap analítico→QC | ~−$58k (≈ **−$330/trade de slippage** na entrada de 6 pernas deep-OTM) |
| entry_cost mediano | 4,5 pts · MFE med $175 · MAE med −$1.365 |

**Leitura do gap:** a perna K3 (−3Δ) fica deep-OTM com bid/ask largo; o `combo_market_order`
cruza o spread na entrada. O drag (~$330/trade) é consistente com o ~$180/trade visto na validação
curta, escalado p/ o span. ∴ o **−$98k do QC é realista** (não artefato como na Fase 1 — aqui NÃO há
market-order no expiry; o settle é cash nativo). A estrutura é cara de executar.

### Por regime de VIX (M0 hold, analítico)
| VIX | net | n |
|---|---|---|
| <15 | −$23.583 | 45 |
| 15-17 | +$1.089 | 33 |
| **17-22** | **+$15.647** | 50 |
| 22-32 | −$30.550 | 48 |
| 32+ | −$2.470 | 2 |

Só **VIX 17-22** é claramente positivo. <15 (vol baixa, sem movimento p/ a estrutura long-gamma da
cauda) e 22-32 (bear trending 2022-24 atravessa o vale) sangram. Eco do achado Batman: existe uma
janela de VIX, não um edge geral.

### Por ano (M0 hold)
2021 −$11.049 · 2022 +$4.913 · 2023 −$15.364 · 2024 −$18.367 (2025/26 no resto do span).
Negativo na maioria dos anos.

### Hold vs gestão derivada (record-and-derive)
| Regra | net | WR |
|---|---|---|
| hold | −$39.867 | 16% |
| **TP25** | **−$18.512** | 25% |
| TP50 | −$19.001 | 18% |
| TP75 | −$43.574 | 16% |
| SL50 | −$44.964 | 16% |
| SL100/150/200 | −$39.867 | 16% |

**Nuance vs Batman:** aqui **cortar cedo (TP25/50) REDUZ a perda** (não decapita o edge — porque não
há edge a decapitar; o hold só acumula o drag). Stops não ajudam (SL50 piora; SL≥100 raramente toca).

## d30 / d45 (30 e 45 DTE) — NÃO CONCLUÍDOS (limitação técnica do free tier)
Não foi possível obter d30/d45 full-span. Dois modos de falha intermitentes do LEAN no free tier
com MUITAS posições multi-perna sobrepostas:
1. **Stall** a ~95% (compute) na 1ª tentativa (marcação 30-min × 5 anos × cadeia larga).
2. **Runtime Error** `OptionStrategyPositionGroupBuyingPowerModel.cs:498` ("Sequence contains no
   matching element") na tentativa otimizada — crash **intermitente** do modelo de buying-power do
   grupo de posições quando combos sobrepostos colidem em strikes. O `combo_market_order`+`_OptBpInit`
   (BP-null por-security) **reduziu mas não eliminou** (o BP do GRUPO é resolvido à parte). O d21
   (178 trades) passou; d30 crashou — depende da sequência de colisões.

**Decisão:** abandonados nesta rodada. O **d21 já responde a pergunta do desk** (a estrutura estática
não replica o vídeo; é perdedora). d30/d45 exigiriam um fix mais profundo (ex.: conta CASH, ordens
individuais com BP-null, ou cap de concorrência) — fazer só se o desk quiser explorar DTEs maiores.
*(Hipótese: DTE maior dá mais tempo p/ o "tent" pegar o preço; mas sem a gestão discricionária,
improvável virar o jogo dado o drag de fill de ~$330/trade.)*

## Conclusão (preliminar, d21)
1. **PL5 estático 21 DTE é um perdedor claro** (−$40k analítico, −$98k com fills) em 5 anos. A tese
   do vídeo NÃO se replica na versão mecânica sem ajuste.
2. O **edge alegado mora na gestão discricionária do "tent"** (rolar p/ acompanhar o spot) — que é
   **não-testável** aqui (forward test). Ou a estratégia não tem o edge anunciado.
3. **Custo de execução é proibitivo** (~$330/trade) p/ uma estrutura de 6 pernas com cauda deep-OTM.
4. Se houver algo, é só na **janela VIX 17-22** + **saída cedo (TP25)** — a investigar se d30/d45
   mudam o quadro (mais tempo p/ o tent pegar o preço).
