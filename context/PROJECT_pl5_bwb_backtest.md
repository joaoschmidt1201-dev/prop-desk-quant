# PROJETO — Backtest "PL5" / BWB 1-2-2 de Puts (QuantConnect)
*Charter vivo · criado 2026-06-15 · será refinado ao longo do processo*

## ★★ ESTADO FINAL (2026-06-17) — LER PRIMEIRO
**PL5 é EXECUTION-DOMINATED. Spread VERIFICADO em minuto = REAL (não artefato).**
Hipótese noturna (spread = quote horário stale) foi REFUTADA: re-rodei d60 em MINUTO (run
`pl5_d60_minchk` fdcadd55…), comparei spread de entrada minuto vs horário em datas de K3 idêntico →
**1,000× (idêntico, dif 0,00pt)**; até nos outliers (58,5 vs 58,6 / 50 vs 51,8). Logo o spread de
30-58pt da cauda −3Δ é **mercado real** (far-OTM, OI baixo), não defeito do dado. O −$195k cons é
custo de execução genuíno (ordem a mercado); +$131k mid só com ordem-limite paciente na cauda.
**Integridade conferida:** hold E saídas já eram mid (via entry_cost_mid); só o `total_credit` exibido
estava em cons → corrigido (reconcilia exato). Colunas novas: entry_cons, entry_spread. Motor ganhou
params data_res/strike_lo + cm/h1/h2/h3 no log. Explicação p/ CZ: `reports/pl5_bwb/EXPLICACAO_CZ_spread.md`.
O custo de entrada das 5 pernas (cauda −3Δ ilíquida) domina. HOLD × fill de entrada:
| DTE | mid | 25% | 50% | spread cheio |
|---|---|---|---|---|
| 21 | +$97k | +$67k | +$36k | −$24k |
| 28 | +$131k | +$99k | +$68k | +$4k |
| 45 | +$88k | +$49k | +$11k | −$66k |
| 60 | +$2k | −$47k | −$96k | −$195k |
→ Fill realista (25-50%): **21-45 DTE hold modestamente POSITIVO; 60 DTE negativo.** O −$190k de antes
era spread cheio (pessimista); +$131k é mid (otimista). **App atualizado (MID + flag); PDF:
`reports/pl5_bwb/PL5_report.pdf`.** Settle=intrínseco verificado (não é bug). commits b72ae7f/75b084e/1582f54.

## ▶ RETOMAR AQUI (ponto de parada — 2026-06-15)
**Onde paramos:** estratégia vista num vídeo ("PL5", *modified broken-wing butterfly* de puts com
convexidade de crash embutida). Motor **v1 construído e validado em sintaxe**:
`backtests/quantconnect/pl5_bwb_v1.py`. Plano aprovado em
`~/.claude/plans/claude-tem-uma-nova-cozy-tome.md`.

**▶▶ AO VOLTAR:**
1. Rodar **janela curta** (~2024-07) no QC p/ validar: deltas certos, entrada como 3 combos sem
   rejeição de margem, settle = intrínseco analítico, reconciliar net derivado ≈ End Equity.
2. Rodar **span completo (2021-06→2026-06)** nos **3 DTE (21/30/45)** = 3 backtests.
3. Puxar CSV via Research notebook → relatório em `reports/pl5_bwb/`.
4. Sanidade da tese de crash: trades abertos ~2 sem antes de 05/08/2024 → P&L positivo no settle?

---

## A estratégia (do vídeo)
"PL5" — apresentada como estrutura que bate o S&P com drawdown baixo e **lucra no crash**
(convexidade embutida; ganhou ~8% no portfólio no crash de Ago/2024 segundo o autor). Gestão por
4 variáveis (dias-no-trade, "tent", P&L, delta da posição); ~30 dias de hold; **sem stop**; profit
target ~$3k. Trade exemplo: aberto 27/jan, fechado 27/fev, +$7k sem nenhum ajuste.

### Estrutura travada com o João (1 "pacote" = unidade de sizing)
Tudo em **puts**, ratio **1/2/2**, ancorado em delta:
- **+1 put @ −30Δ** (K1 = maior strike) — long de cima
- **−2 puts @ −18Δ** (K2) — corpo short
- **+2 puts @ −3Δ** (K3 = menor strike) — cauda long de baixo

Net **long 1 put**. Payoff: 0 acima de K1; pico (tent) em K2; vale de perda máxima ~K3; **volta a
ganhar abaixo de K3** (a cauda = convexidade de crash, a tese central). Risco DEFINIDO (= o vale).

---

## Design travado (v1)
- **Ativo:** SPX → contratos **SPXW** (europeu, PM cash-settle; sem assignment). *(Lei 1 do desk.)*
- **DTE:** 3 runs — **~21, ~30, ~45 DTE** (`target_dte`). *(Lei 2: ≥7DTE — respeitada.)*
- **Período:** 2021-06 → 2026-06 (5 anos: bear 2022, grind 2023-24, **crash Ago/2024**).
- **Entrada:** toda **SEXTA-FEIRA 10:00 ET**; expiry numa **sexta** minimizando |dte_real−target|
  (entrada sexta ⇒ expiry sexta facilita achar 21/30/45 em múltiplos de semana limpos).
- **Sizing:** 1 pacote por sinal; `set_cash(100_000)`. Posições sobrepostas (semanal).
- **Montagem (margem netada):** `bear_put_spread(K1,K2) + bull_put_spread(K2,K3) + 1 long put K3`
  = +1K1/−2K2/+2K3. Combos reconhecidos evitam o bug de naked-short margin (lição do Batman).
- **Gestão:** **record-and-derive** — o motor NÃO executa TP/SL; grava o 1º cruzamento (hora+DIT+valor)
  de TP [25/50/75/100% de ref_profit] e SL [0.5/1/1.5/2× de ref_loss], + MFE/MAE + MTM em 7/14/21
  DIT. Hold-to-expiry (cash-settle nativo) = baseline M0 = equity do QC. Variantes de close + cortes
  por VIX saem do dataset **no app** — sem re-rodar o QC.

---

## O que DÁ e o que NÃO DÁ testar (a separação honesta)
**DÁ (QuantConnect, 1-min):**
- Expectativa da *estrutura* BWB 1/2/2 ancorada em delta, em 21/30/45 DTE.
- A **convexidade de crash** (cauda K3) — se a estrutura ganha no stress (Ago/2024).
- Gestão derivada: profit targets, stops, saída por tempo (DIT), buckets de VIX, por ano.
- Curva de equity hold-to-expiry + maxDD (a tese central do vídeo).

**NÃO DÁ (limites assumidos):**
- O **"tent"-tracking discricionário** (rolar/ajustar a estrutura p/ manter o tent perto do spot) →
  **v1 é ESTÁTICA, sem ajuste**, igual ao trade do vídeo ("without making a single adjustment").
  Ajuste fica p/ o forward-test.
- O julgamento das 4 variáveis em tempo real (decisão de quando mexer) → não codificável.

---

## Métricas / relatório
Net, CAGR, Sharpe, Sortino, maxDD, PF, WR; distribuição por-trade; por VIX bucket e por ano; hold vs
grid de TP/SL; sanidade do crash de Ago/2024. Relatório em `reports/pl5_bwb/`.

## Como rodar (free tier)
- 3 backtests (`target_dte` = 21/30/45), via `lean cloud push` + `lean cloud backtest`
  (workspace existente; ver `~/.claude/.../memory/project_qc_lean_pipeline`).
- Params: `target_dte`, `start_date=2021-06-01`, `end_date=2026-06-01`, `run_tag=pl5_bwb_d{N}`.
- Free tier: ObjectStore não baixa (Research notebook), log cap ~707 linhas (CTRADE| compacto),
  1 nó por vez. Fallback se apertar: `Resolution.HOUR` na chain ou chunkar por ano.

## Riscos / pontos de atenção
- **Margem dos combos sobrepostos** (3 combos compartilham K2) — validar na janela curta que netam
  como perda máx definida. Maior risco técnico.
- **IV/greeks 0 na cadeia** — `_delta` tem fallback Black-Scholes (herda resolvido do Batman).
- **Expiry no DTE-alvo** — SPXW tem weeklies; picker por |dte−target| acomoda; gravar `dte_real`.
- **Compute** com posições semanais sobrepostas × 5 anos × marcação 30min — monitorar.

## Sources
- Transcrição do vídeo (no histórico desta sessão).
- Motor template: `backtests/quantconnect/batman_1dte_v1.py`; delta-pick: `iron_condor_0dte.py`.
- [QuantConnect — US Index Options (SPX/VIX, 1-min desde 2012)](https://www.quantconnect.com/data/algoseek-us-index-options)
