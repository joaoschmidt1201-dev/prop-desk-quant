# PROJETO — Backtest das Estratégias de Butterfly do Ernie (QuantConnect)
*Charter vivo · multi-dia · será refinado ao longo do processo · criado 2026-05-20*

## ▶ RETOMAR AQUI (ponto de parada — 2026-05-20)
**Onde paramos:** Fase 0 ✅ (dados SPXW grátis no QC validados) e Fase 1 ✅ (algo escrito e validado em janela curta 2024-11: 4 trades, 1 W zone2, net +$185, aritmética conferida trade a trade).

**Próxima ação (começar por aqui amanhã):** rodar o **primeiro estudo de ano inteiro** no QC.
1. Abrir o algo (`backtests/quantconnect/fase1_classic_otm_fly.py`) e trocar as 2 datas no topo do `initialize`:
   `self.set_start_date(2024, 1, 1)` / `self.set_end_date(2024, 12, 31)`.
2. Rodar; pegar o resumo + o bloco `>>>CSV_START … >>>CSV_END` do log (download do ObjectStore é gated → usar o log).
3. Repetir em blocos: 2022(jun→dez), 2023, 2025, 2026 — o Claude costura os CSVs.
4. Comparar a distribuição (win rate, múltiplo do winner, PF, Sharpe) com o subset SPX do log do Ernie.
*(Manter o baseline: `placement_mode="debit"`, asa 30, EMA9, 10:00. Varreduras de asa/horário/EMA-vs-Hull vêm depois.)*

**Pendências anotadas:** IV às vezes vem 0 na cadeia (ok no modo debit; resolver no modo sigma da F3); reconciliar 1× o net analítico vs equity oficial do QC (fills+fees). **Git: ainda NÃO commitado** (arquivos salvos em disco/OneDrive).

## Context
Pedido do CZ (sessão 2026-05-20): entender a estratégia 0DTE que ele opera (framework do
Coach Ernie / Fly On The Wall) e pensar em estendê-la para DTE mais alto (desk opera ≥7DTE).
Material neste diretório (`context/0DTE strategies/`): primer, curso "Fat Tail Campaigns",
7 cheat-sheets de estratégia e o log real de 738 trades do Ernie.

**Decisões já tomadas com o João:**
- Ferramenta = **QuantConnect** (grátis na nuvem; traz dados de index options SPX 1-min desde 2012; faz intraday → cobre 0DTE de verdade). Tasty foi descartada por ser daily/EOD.
- **Escopo fatiado**, sem abraçar tudo num backtest só. **Começar pelo 0DTE padrão**, depois expandir DTE e cenários.
- Não temos dados de opções do IBKR → por isso QC (dados inclusos).
- Projeto de vários dias; João conduz, eu (Claude) ajudo em cada etapa.

---

## O que DÁ e o que NÃO DÁ para testar (a separação honesta)
**DÁ (QuantConnect, 1-min):**
- Expectativa da *estrutura* (fly OTM) em qualquer DTE.
- Seleção de **lado por tendência** (MA no diário) → call vs put fly.
- Entrada intraday em **horário fixo** (e varredura de horários).
- Gestão intraday: profit targets, trailing stop (proxy do trail dinâmico), saída por horário.
- Buckets de VIX e largura por regime de VIX.
- Cadência **seg/ter/qua**; filtros de dia macro.
- **Batman** (dual-fly) e expansão de DTE 0 → 7+.

**NÃO DÁ (limites assumidos):**
- O **Tradable Event discricionário** (nível de volume-profile + continuação) → não é codificável. Usamos horário fixo + viés de tendência como proxy. *(O João confirmou: pullback não simula.)*
- O **trail dinâmico exato** casado a theta/gamma → aproximado por trailing stop parametrizado.
- A **colocação discricionária "centrar no próximo HVN"** do volume-profile → usamos a regra σ (codificável, ver Fase 1).
- O julgamento discricionário de "pular o dia" → só validável em forward-test.

> Leitura científica: cada fase adiciona UMA camada de edge. Comparar a base (estrutura pura)
> com o log real do Ernie isola quanto vem da estrutura vs. da seleção de entrada.

---

## Fases (testes separados)
| Fase | Objetivo | Adiciona |
|---|---|---|
| **0** | Setup: criar este doc, conta QC, validar dataset SPX index options no tier grátis | — |
| **1** | **0DTE padrão** — Classic OTM Fly, baseline estrutura + viés de tendência | horário fixo + lado por MA |
| **2** | Realismo de gestão | trail proxy, profit targets, largura por VIX |
| **3** | Expansão de DTE → horizonte do desk | 1,2,3,5,7 DTE + Sigma Drift 7–10 |
| **4** | Cenários e dual-fly | Batman, dias macro (CPI/FOMC), regimes de VIX |

---

## FASE 1 — especificação (a refinar juntos)
**Engine:** QuantConnect (Lean), Python.
**Ativo:** **SPX → contratos SPXW** (weekly/daily, europeu, PM cash-settled — sem assignment; bate
com o Ernie e a Lei 1 do desk). Dataset AlgoSeek US Index Options (QC Cloud, **grátis**), 1-min com
bid/ask, desde 2012; 0DTE diário (SPXW) desde ~2022.
**Período:** 2022-06 → presente (casa com o início do log do Ernie e com SPX 0DTE diário).
**Dias:** **seg/ter/qua** (cadência confirmada do Ernie). *Variante:* todos os dias úteis (testar se qui/sex diferem).
**Entrada:** horário fixo por sessão — **default 10:00 ET** (dentro da janela 9:30–12:30 onde ocorrem 80% dos eventos). *Varredura de robustez:* 9:45 / 10:00 / 10:30 / 11:00.
**Lado (qual arriscar) — filtro de tendência no diário:**
- **Default = EMA9 diária do SPX** (o desk/CZ já acompanham). Preço acima + EMA9 subindo → **Call fly acima**; abaixo + descendo → **Put fly abaixo**; lateral → **pula**.
- **Variante = Hull MA diária** (default do Ernie) para comparar a qualidade da seleção.
**Estrutura:** long OTM symmetric butterfly, expiração 0DTE.
- Pernas: **buy 1 lower · sell 2 center · buy 1 upper**. Naming do Ernie: **"30-wide" = 30 pts por ASA** (longs em center ∓ 30) → 60 pts de span total. O "width" do primer = a asa.
- Asa inicial **25–30 pts SPX** (o "most days" do Ernie). *Varredura:* 20/25/30/35. (Largura por VIX só na Fase 2.)
- **Colocação do short strike (center) — CODIFICÁVEL.** No **0DTE (Fase 1) a regra é o DEBIT:** center OTM no strike onde **debit ≈ 10% da asa** (R:R ~1:9). ⚠️ A colocação por **σ (1.75–2.5σ "Sweet Spot")** é do curso para **DTE alto** (Convexity/Sigma Drift) — a 2σ num 0DTE a fly fica longe demais e quase sem valor (**validado: 2σ → debit $0.05, expira zerada**). σ vai para a Fase 3. *(Centrar no próximo HVN do volume-profile NÃO é codificável → forward-test.)*
**Sizing:** 1 contrato por sinal (MAD/sizing entra depois — isola a distribuição por-trade).
**Gestão (simples, p/ isolar a estrutura):**
- Variante A: **hold-to-expiry** (losers expiram; winner = intrínseco no settle) → expectativa estrutural pura.
- Variante B: **profit target fixo** (50% / 75% / 100% do máx) → mede captura de lucro. (Trail dinâmico = Fase 2.)
- Sem stop (risco definido = debit).
**Métricas:** distribuição de retorno por-trade, win rate, múltiplo médio/mediano do winner, profit
factor, Sharpe, max DD, % em Zone 0/1/2/3.
**Benchmark:** subset **SPX-only** do log do Ernie (738 trades, Sharpe 4.02 / PF 1.80) — remover
TSLA e outros (fora da Lei 1) e separar por asa.

**O que a Fase 1 isola:** convexidade da estrutura + valor da seleção de lado por tendência, em
horário fixo. **Não inclui:** timing de pullback, trail dinâmico, largura por VIX, sizing/MAD.

### Referência — colocação do short strike (do material do Ernie)
- **Quantitativa (codificável):** curso "Fat Tail Campaigns", Tier 3 → *"Strike centered at 1.75σ–2.5σ (Sweet Spot) or 2.5σ–3.0σ (Sniper)"*. σ = expected move implícito. Perto demais = caro ("Convexity Kink"); longe demais = quase nunca acerta.
- **Estrutural (discricionária, não codificável):** cheat-sheet Classic OTM Fly + Volume Profile Map → center OTM relativo ao nível estrutural de entrada; *"center butterfly on the next HVN as the strike target"* (mira o próximo high-volume node). Construído ao vivo com o "Convexity Heatmap".
- **Trail por horário** (Classic OTM Fly, p/ Fase 2): manhã 50–75% → tarde 25–50% → fechamento 15–25%.
- **Distribuição esperada do Ernie:** ~50% perda total · ~38% win pequeno (sai de manhã) · ~8% médio · ~4% pin/max. (Ele conta o win pequeno como win → "win rate ~50%", vs ~30% no primer — calibrar no benchmark.)

---

## Decisões em aberto (para resolver durante o processo)
1. EMA9 vs Hull MA como default do filtro de tendência (vamos testar as duas — qual vira default?).
2. Regra exata de "lateral/chop" que faz pular o dia (slope mínimo? distância da MA?).
3. **RESOLVIDO (corrigido na validação):** 0DTE usa **placement por debit-10%** (center OTM onde debit ≈ 10% da asa), NÃO σ — a 2σ num 0DTE a fly custa centavos (debit $0.05 no teste). O **σ (1.75–2.5σ, IV da cadeia do Option Universe)** fica para DTE alto (Fase 3). Varrer asa 20–35 pts.
4. **RESOLVIDO:** usar **SPXW** (weekly/daily, PM cash-settled, europeu) — é o que tem 0DTE todo dia desde ~2022. Hold-to-expiry = intrínseco no fechamento 16:00 ET; QC liquida cash automaticamente.
5. Modelo de custos: comissão + slippage realista para SPX no QC (definir na Fase 1).

---

## Como vamos trabalhar
- Este doc é o **charter vivo** — atualizo a cada fase com parâmetros travados, resultados e próximos passos.
- Cada fase = um backtest QC isolado + um resumo de resultados versionado no desk.
- Eu escrevo/depuro o algoritmo Lean; o João roda/valida na conta QC e traz o read do CZ.

## Próximos passos
- [x] Salvar este charter no desk.
- [x] **Fase 0 — PASSOU (2026-05-20):** SPX/SPXW index options são **grátis no QC Cloud** (research/backtest/live); minute com bid/ask; Greeks+IV via Option Universe; 0DTE (SPXW) diário desde ~2022. *Caveat:* tier grátis tem limite de compute → manter backtests enxutos (períodos/filtros de strike).
- [x] Fase 1 — algoritmo escrito: `backtests/quantconnect/fase1_classic_otm_fly.py` (v1, janela curta de validação 2024-11-04→15). Emite `fase1_trades.csv` no ObjectStore.
- [x] Fase 1 — **validação PASSOU (2024-11, 4 trades, 1 W zone2, net +$185):** debit ~$2.55–2.95 (≈9% da asa) ✓, placement por debit ✓, debit-cap pulou 2 dias >$3 ✓, CSV via log ✓, shape de convexidade aparece (1 winner paga 3 losers). Achados: `implied_volatility` às vezes vem 0 na cadeia (ok p/ modo debit; resolver p/ modo sigma na F3); strike filter reduzido p/ ±60 strikes (compute); falta reconciliar net analítico vs equity do QC (fills/fees).
- [ ] Fase 1 — **estudo completo:** trocar datas p/ 2022-06→presente e rodar; varrer asa (20–35) / horário / EMA9-vs-Hull; comparar ao subset SPX do log do Ernie.
- [ ] Export: adaptador `scripts/qc_to_auditor.py` (CSV do QC → formato do CZ Dashboard / Trade Auditor) — passo posterior; logging já nasce pronto.
  - ⚠️ **Tier free não baixa o ObjectStore** ("derivative data", só institucional). **Canal de saída = os LOGS** (botão *Download Logs* / copiar). O algo despeja o CSV entre `>>>CSV_START`/`>>>CSV_END`. Para o estudo grande (centenas de trades), os logs aguentam (~120 chars/linha); se estourar a cota, ler o ObjectStore de graça no **Research notebook** ou chunkar.

## Sources
- Material interno: `context/0DTE strategies/` (primer, curso "Fat Tail Campaigns", cheat-sheets, log de 738 trades)
- [QuantConnect — US Index Options (SPX/VIX/NDX, 1-min desde 2012)](https://www.quantconnect.com/data/algoseek-us-index-options)
- [QuantConnect — plataforma grátis de backtest](https://www.quantconnect.com/)
