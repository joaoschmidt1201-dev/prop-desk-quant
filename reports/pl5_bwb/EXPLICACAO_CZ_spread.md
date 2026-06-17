# PL5 — Por que o resultado muda tanto entre "mid" e "bid/ask"? (resposta pro CZ)

*João — roteiro pra apresentar. Tudo abaixo está VERIFICADO nos dados, inclusive em resolução de minuto.*

## A pergunta
"Como o HOLD do PL5 passa de **−$195k** (preço bid/ask) pra **+$131k** (preço mid)? Isso é estranho."
Está certo desconfiar. A resposta é precisa, **não é bug**, e — importante — **não é artefato de dado**.
É **custo de execução REAL** na perna ilíquida.

## 1. Por que SÓ a entrada importa no hold
No HOLD até o vencimento **não existe spread de saída**: o SPX faz cash-settlement no preço oficial
(sem ordem de saída, sem bid/ask na saída). Logo a ÚNICA diferença entre "mid" e "bid/ask" é o
**preço de ENTRADA** das 5 pernas. Matematicamente:

> hold(mid) − hold(bid/ask) = spread de entrada total (e mais nada)

Confere exato: d60 → diferença $196.465 = soma dos spreads de entrada ($196.465). ✓ (não é bug)

## 2. A estrutura é barata no mid, mas o spread é grande relativo ao edge fino
| DTE | custo entrada MID (mediana) | custo entrada BID/ASK (mediana) | spread (mediana) |
|---|---|---|---|
| 21 | 2,55 pts | 4,90 pts | 1,55 pts |
| 28 | 2,70 pts | 5,65 pts | 1,88 pts |
| 45 | 3,10 pts | 6,30 pts | 3,18 pts |
| 60 | 3,20 pts | 7,50 pts | 3,65 pts |

A estrutura (5 pernas: +1/−2/+2 puts) custa **~3 pts no mid**. O edge terminal é fino (~$330/trade),
então o spread de entrada **decide o sinal** do resultado.

## 3. O −$195k é dominado por OUTLIERS na cauda −3Δ
A média do spread é MUITO maior que a mediana → poucos trades carregam o custo:
- d60: spread **mediana 3,65 pts** mas **média 8,22 pts**, **máximo 58,50 pts** ($5.850 num trade).
- Os **10% piores trades carregam 37%** de todo o custo de spread.
- A perna **−3Δ deep-OTM (×2)** é a culpada: opção de cauda, OI baixo, **mercado naturalmente largo**
  (o market maker não aperta o spread de uma put a 1000+ pts OTM, mesmo com VIX calmo).

## 4. ⚠️ VERIFIQUEI EM MINUTO — e o spread é REAL (minha 1ª hipótese estava errada)
Desconfiei que os spreads de 30-58pt fossem **quote horário stale** e re-rodei o d60 em **resolução de
minuto** (cotação mais confiável) na janela dos outliers. Resultado da comparação nas mesmas datas,
**mesma estrutura (K3 idêntico)**:

| spread HORÁRIO | spread MINUTO |
|---|---|
| 1,2 pts | 1,2 pts |
| 6,3 pts | 6,3 pts |
| 1,6 pts | 1,6 pts |
| **mediana 1,6** | **mediana 1,6 (1,000×)** |

E nos outliers (58,5 / 50,0 / 39,3 pt): minuto deu 58,6 / 51,8 / 39,7 — **idêntico**. **Conclusão: o spread
NÃO some com mais resolução. É o mercado real da cauda −3Δ, não um defeito do dado horário.** Sou obrigado
a reportar isso — o −$195k é custo de execução genuíno, não um artefato que dá pra descartar.

## 5. O risco REAL da estrutura (separado do spread)
Além do spread, há perdas grandes **legítimas** quando o spot pousa no **vale (K3)**. Ex.: **07/02/2025,
crash de tarifas: −$53.541 NO MID** (spread de só $3k). É a perda máxima definida — o mid já captura.

## 6. O que dizer pro CZ (resumo honesto de 30 segundos)
1. O hold no vencimento só depende da **entrada**; mid vs bid/ask = só o spread de entrada (não é bug).
2. **O spread é REAL** (verifiquei em minuto: idêntico ao horário). O edge do PL5 mora na cauda −3Δ de
   convexidade de crash — que é **justamente a perna mais ilíquida** (spread 30-58pt em ~20% dos dias).
   Essa é a tensão central da estratégia.
3. Portanto **mid (+$131k) só é alcançável com ordem-limite paciente** preenchendo a cauda perto do meio.
   **A mercado (cruzando o spread cheio) você perde** (−$195k). Não é estratégia de ordem a mercado.
4. **Veredito:** PL5 é **execution-bound na cauda**. Com disciplina de limite, 21-45 DTE fica
   modestamente positivo (ver tabela de fill: mid / 25% / 50% / cheio). 60 DTE é marginal. O risco real
   é o vale (perda máx definida) **+** a qualidade do fill na −3Δ. **Não vender como dinheiro fácil.**

*Tabela de sensibilidade ao fill (mid / 25% / 50% / cheio) e curvas no `PL5_report.pdf`. O spread usado
ali está agora VERIFICADO como real (não inflado), então o lado "cheio" é um cenário legítimo de pior caso.*
