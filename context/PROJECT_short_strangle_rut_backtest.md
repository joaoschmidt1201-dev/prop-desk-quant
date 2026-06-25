# PROJECT — Short Strangle RUT (28/35/42 DTE) no QuantConnect

> Charter vivo. Pedido do CZ em 2026-06-24. Liga: memória `project_qc_lean_pipeline`,
> `project_ss42_backtest` (engine local antigo), `feedback_anomaly_check_before_app`.

## Pedido do CZ (2026-06-24)
Short Strangle em **RUT**, abrindo **toda sexta-feira**, strikes por delta
(**SHORT PUT 10Δ / SHORT CALL 8Δ**), três horizontes de entrada **28 / 35 / 42 DTE**,
**5 anos**, **tudo no mid price**, dados verídicos (verificar a cada passo).

## Decisões (com o João, nesta sessão)
- **Regra de DTE = duas saídas por tempo: 14 DTE e 7 DTE** (substitui a leitura ambígua "2/3/4 semanas").
- **RUT sem precedente no QC neste repo** → smoke-test primeiro; se cadeia vazia, PARAR e reportar.
  → **RESOLVIDO: RUT/RUTW TEM dados no QC** (smoke operou de verdade).
- **Escopo: pipeline completo** incluindo integração no app.

## Estratégia (spec final)
- Ativo RUT, opção RUTW (weeklies), europeu cash-settled, $100/pt.
- Entrada toda sexta 10:00 ET; vários trades concorrentes; expiry mais próximo do DTE-alvo.
- Strikes: put |Δ|≈0.10, call |Δ|≈0.08. Delta = greeks da cadeia → IV da cadeia → **IV invertida do mid (BS)**.
- Fill MID (headline); loga conservador (shorts@bid) p/ slippage.
- Naked → **BuyingPowerModel.NULL** (não bloqueia entrada / não liquida); P&L vem do **payoff analítico**.

### 12 close rules (record-and-derive, 1 run por config)
`hold` · `tp25/50/75` · `dte_a`(14 DTE) · `dte_b`(7 DTE) ·
combos "TP ou DTE o que vier 1º": `tp25_a tp50_a tp75_a` (vs 14) · `tp25_b tp50_b tp75_b` (vs 7).
Tudo derivado em `_rule_pnl()` no motor → emitido como runtime stats `R <rule>` (net/$ + WR).

## Arquivos
- Motor: `backtests/quantconnect/short_strangle_rut.py`  (cópia em `~/qc_batman/Fat Violet Hippopotamus/main.py`).
- Sweep: `scripts/ss_strangle_sweep.py` (3 configs, lean cloud, poll API). Saída `~/qc_batman/ss_strangle_results.json`.
- Export/report: `scripts/ss_strangle_export_app.py` (a fazer).
- Helpers no workspace: `~/qc_batman/_lean.py` (runner do CLI), `_status.py`, `_rt.py`, `_ctrades.py`.

## Infra / gotchas desta máquina
- **`lean.exe` bloqueado por App Control** → chamar o CLI via `python ~/qc_batman/_lean.py <args>`.
- **CLI quebra ao renderizar unicode** (cp1252 no console Windows): runtime-stat keys/valores **só ASCII**;
  subprocess com `PYTHONIOENCODING=utf-8`.
- **Log API rate-limited (alocação diária)**: `/backtests/read/log` precisa `{projectId,backtestId,start,end,query}`,
  páginas ≤200 linhas. Esgotou hoje (testes). Reseta no dia seguinte. Canais robustos = **runtime stats + closedTrades**.
- ObjectStore download bloqueado (free tier) — igual aos outros projetos.
- Projeto cloud "Fat Violet Hippopotamus" (cloud-id 27848355), org 1f97d316a4d53242e929726971860505.

## Validação do smoke (2024-07-01 → 2024-09-15, target_dte=42)
- **RUTW operou** (Lowest Capacity Asset = RUTW…|RUT). 6 trades liquidados na janela, skips 0.
- **Deltas verídicos**: |Δput| med 0.101 (0.099–0.103), |Δcall| med 0.079 (0.070–0.080), **0/6 off-target**.
  (alarme inicial de "call longe demais" era falso — RUT subiu de ~2030→2260 no rally de small-caps de jul/24,
   então C2500 era mesmo ~8Δ.)
- credit med 15.7 pts; as 12 regras saem distintas (ex.: hold +$8.7k WR100% · tp75 +$6.5k · dte_a(14) −$3.4k · dte_b(7) +$4.0k).
- Equity do QC (−1.14%) é IRRELEVANTE (naked + NULL BP) — vale o payoff analítico.

## Estado atual (2026-06-25) — COMPLETO
- ✅ 3 configs concluídas (28/35/42, 5y, mid). bids: 28=949a03d4, 35=b64602ee, 42=ce13b748.
- ✅ Export: `reports/short_strangle_rut/REPORT.md` + `SS_RUT_{28,35,42}/trades.csv`+`daily.csv` (do CTRADE).
- ✅ Verificação: recompute CTRADE = runtime stats ao $; vencedor + pior trade (#191 crash abr/2025) auditados.
- ✅ App integrado: 3 cards `ss-strangle-rut-d{28,35,42}` em `apps/api/main.py`, reusa kind="ss42",
  close_rules dict (12 regras), mult 100. Validado via get_backtest (12 regras + filtro VIX, nets batem).
- **PENDENTE:** commit/push p/ deploy (Vercel front + Render API) — aguardar João pedir.

## Veredito final
**Hold domina; 42 > 35 > 28** (hold $285k/$237k/$213k, WR ~92%). Toda gestão (TP/DTE/combos) reduz o net.
Lucrativo todo ano (incl. bear 2022 e crash abr/2025). **Risco de cauda:** hold maximiza net mas leva a
cauda (pior trade −$18.7k no crash abr/2025); naked = risco indefinido → dimensionar margem/capital de cauda.

## Ressalvas conhecidas (p/ o relatório ao CZ)
- Mid vs bid: headline é mid; slippage real a estimar (loga credit_cons).
- Settle: aproximado pelo fecho do RUT; weeklies RUTW são PM-settled (ok), monthly seria AM/SET (não usado).
- Naked = risco indefinido; margem real (Reg-T/PM) a dimensionar fora do QC.
