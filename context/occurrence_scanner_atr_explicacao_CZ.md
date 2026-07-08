# Occurrence Scanner ATR — explicação para apresentar ao CZ

## 1. O que a ferramenta faz (o objetivo)
A occurrence matrix conta, ao longo de toda a história, quantas vezes o preço — **ao chegar numa
média móvel (MA)** — faz:
- **Bounce**: a MA **segurou** (o preço voltou / respeitou o nível).
- **Break**: o preço **rompeu** a MA de forma decisiva.
- **False**: o preço **fingiu que rompeu** (furou e voltou).

Isso serve pra responder, por ticker: *"essa MA é um bom suporte/resistência? o ativo é mais
mean-reversion (bounca nas MAs) ou momentum (rompe)?"* — e escolher o tipo de operação.

## 2. O problema que a gente resolveu: a "tolerância no olho"
Pra decidir *"o preço chegou perto o suficiente da MA pra contar como um toque?"*, precisa de uma
**tolerância** — uma **banda** (faixa) em volta da linha. Antes, essa banda era um **% fixo no olho**
(ex.: 0,2%).

**Por que isso estava quebrado:** 0,2% significa coisas **completamente diferentes** dependendo do
ativo e do timeframe. 0,2% no EURCHF (que anda em 4 casas decimais, super calmo) é uma banda **enorme**;
0,2% no Bitcoin (volátil) é **minúscula**. Ou seja, a mesma "régua" **não era comparável entre ativos**
— a matriz ficava enviesada e a comparação perdia sentido.

**A ideia:** parar de usar um % e passar a medir a banda em **unidades da própria volatilidade do ativo**.
Assim a banda se ajusta sozinha — larga onde o ativo é volátil, estreita onde é calmo — e **um número só
serve pra todos os ativos**, significando a mesma coisa em todo lugar.

Existem duas formas de medir "volatilidade típica": **σ (desvio-padrão)** ou **ATR**. A ferramenta tem os
dois modos; a gente escolheu o ATR, e vale explicar a diferença.

## 3. O modelo σ (Standard Deviation)
- **σ = desvio-padrão da distância entre o preço e a MA** (`close − MA`), numa janela de N barras.
  Mede o "tamanho típico do balanço" do preço **em torno daquela MA específica**.
- Banda = **k · σ**.
- **✅ Vantagem:** comparável **entre tickers** — auto-escala pela volatilidade de cada ativo.
- **❌ O problema que descobrimos:** o σ é medido **em relação a cada MA**. Numa MA **lenta** (ex.: SMA200),
  o preço fica **muito longe** dela durante tendências → o σ dela é **grande** → a banda fica **larga**.
  Numa MA **rápida** (EMA9), o preço fica colado → σ pequeno → banda estreita.
  **Resultado:** a SMA200 ganha uma banda "gorda" de graça → parece ter **mais bounces** → a comparação
  **entre MAs fica enviesada** (a ferramenta favorece as MAs lentas). No SPX, a banda da SMA200 ficava
  **2,4× mais larga** que a da EMA9 no mesmo k — puro artefato. **O σ captura distância de TENDÊNCIA,
  não a proximidade do toque.**

## 4. O modelo ATR (o escolhido)
- **ATR (Average True Range) = a amplitude típica de UMA barra** — o quanto o preço se move por candle.
  É uma medida de volatilidade do **ativo**, **independente da MA**.
- Banda = **k · ATR**.
- **✅ Vantagem 1:** comparável **entre tickers** (ATR é por ativo, auto-escala) — igual ao σ.
- **✅ Vantagem 2 (o pulo do gato):** como o ATR **não depende da MA**, a banda fica com a **mesma largura
  pra TODAS as MAs** do ativo. Então a comparação **entre MAs** (qual MA segura melhor) fica **justa** — a
  SMA200 não ganha mais banda gorda de graça (no SPX passou de 2,4× pra **1,0×**).

**Por isso o ATR é o escolhido:** é o único que dá comparação **justa nos TRÊS eixos ao mesmo tempo** —
entre **levels (MAs)**, entre **timeframes** e entre **tickers**. Que é exatamente o que o CZ pediu:
comparar tudo na mesma régua, "cristalino".

## 5. O k = 0,2 (a régua única)
- **k é adimensional**: *"quantos ATRs de distância da MA contam como um toque"*. **k = 0,2** = o preço
  chegou a dentro de **0,2 ATR** da MA.
- Escolhido no olho, testado em **vários tickers e timeframes**, comportou-se bem. É a **mesma régua pra
  tudo** — 1 número no lugar dos ~1300 percentuais no olho de antes.
- **Ponte com o mundo do CZ:** ele já pensa em **"3 ATRs OTM"** pros credit spreads — é a **mesma lógica**
  de medir distância em ATRs. Aqui é uma fração de ATR pra definir "encostou na MA".

## 6. O que aparece no gráfico (o scanner)
- A **banda ATR** plotada (zona sombreada) em volta da MA — o CZ vê a tolerância e que ela é **igual pra
  qualquer MA**.
- **Marcadores**: ▲ verde = Bounce, ▼ vermelho = Break, ✕ laranja = False, no candle do evento.
- **Tabela (HUD)** no canto: contagem e **%** de Bounce / Break / False + Total. É o resumo que orienta a
  decisão (ex.: *"EMA9 no EURCHF = 53% bounce"* → nível respeitado → mean-reversion).

## 7. "E os erros? Por que é uma boa versão mesmo assim?"
Isto é importante deixar claro (com honestidade):
- A classificação **candle-a-candle** é **intrinsecamente ambígua** em consolidações (preço colado na MA
  por muitas barras). **Nenhuma regra** acerta 100% dos casos visuais — e a gente aceita isso, porque é
  da natureza do problema (é o mesmo tipo de subjetividade de "onde exatamente está o suporte").
- **MAS a ferramenta é ESTATÍSTICA:** ela conta **centenas/milhares de eventos** por ticker. Um samba
  mal-contado aqui, um evento a mais ali, **diluem no agregado**. O que importa — e é o que o CZ usa — é
  o **percentual sobre muitos eventos** ("EMA9 = 53% bounce"), que é **robusto** a esses detalhes.
- E o **ganho estrutural** (banda ATR justa + normalizada) é **real e resolve o problema central**: antes
  a matriz comparava maçã com laranja (0,2% ≠ 0,2%); agora compara tudo na mesma régua, entre MAs,
  timeframes e tickers.

## Frase de elevador (pro CZ, em 20 segundos)
> "Trocamos a tolerância de *'um % chutado no olho por ativo'* por *'uma fração do ATR do próprio ativo'* —
> um número só (0,2 ATR) que se ajusta sozinho e significa a mesma coisa no EURCHF, no SPX e no Bitcoin.
> Usamos ATR (não desvio-padrão) porque o ATR dá a **mesma banda pra todas as MAs**, então dá pra comparar
> qual MA é melhor suporte de forma justa — entre levels, timeframes e tickers ao mesmo tempo. A leitura
> candle-a-candle não é perfeita em consolidações, mas como é estatística (centenas de eventos), o
> percentual agregado é sólido — e é nele que a gente decide."
