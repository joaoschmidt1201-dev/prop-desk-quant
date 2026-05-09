# ForwardTest Handoff - 2026-05-08

Contexto: camada ForwardTest do dashboard Prop Desk Quant. O objetivo era fechar milestones no backend e TradeInspector no frontend, reaproveitando a base já implementada de auto-deteccao por nome, cutoff date e daily_history no snapshot.

## Estado atual

Implementado e validado:

- Backend em `apps/api/main.py`
  - `_ft_milestones(trade)` calcula:
    - `max_profit_usd`
    - `max_pnl_seen`
    - `min_pnl_seen`
    - `max_dd_from_peak`
    - `dit_to_25mp`
    - `dit_to_50mp`
    - `dit_to_75mp`
  - `_enrich_ft_trade(t)` adiciona `milestones`.
  - `GET /api/forwardtests/{strategy_id}` agora retorna `open_trades` e `closed_trades` enriquecidos.
  - Milestones de %MP só aparecem quando `net_credit > 0`; debit trades continuam com daily PnL chart sem linhas de milestone.

- Frontend types em `apps/web/src/lib/api.ts`
  - `ForwardtestDailyPoint`
  - `ForwardtestMilestones`
  - `ForwardtestTrade.daily_history?`
  - `ForwardtestTrade.milestones?`

- Frontend detalhe em `apps/web/src/components/forwardtests/forwardtest-detail.tsx`
  - Estado de selecao de trade open/closed.
  - Linha clicavel e acessivel por teclado nas tabelas.
  - `TradeInspector` inline com:
    - header do trade
    - badge open/closed
    - KPIs: Current P&L, %MP, Delta, DTE remaining, DIT, Max DD seen
    - P&L Journey chart via `daily_history`
    - Delta Evolution chart via `daily_history`
    - milestone strip 25/50/75% MP
    - Trade setup card lendo breakevens e contratos quando existirem no trade
    - StrikeStructureCard a partir de `trade.strikes`
  - Parser de strikes aceita separadores `/`, `,`, whitespace e `|`.
  - `% to LBE/UBE` agora formata corretamente quando o snapshot vier como `-6.88` em vez de `-0.0688`.

- Shared card em `apps/web/src/components/shared/strike-structure-card.tsx`
  - `LegRow.side` aceita `null` para estruturas vindas de string de strikes sem side buy/sell.

## Validacoes realizadas

- Smoke test Python dos milestones:
  - Fixture `T54 IWM Triple Calendar 21/28DTE`
  - `net_credit=1200`
  - daily_history com PnL 0, 320, 650, 700
  - Resultado esperado confirmado:
    - `max_profit_usd=1200`
    - `max_pnl_seen=700`
    - `dit_to_25mp=3`
    - `dit_to_50mp=6`
    - `dit_to_75mp=None`

- Typecheck frontend:
  - `cd apps/web && npx tsc --noEmit`
  - Passou sem erros.

- Next dev server:
  - `http://127.0.0.1:3000/forwardtests`
  - Respondeu `HTTP/1.1 200 OK`.
  - Processo observado: PID `7104` escutando na porta `3000`.

## Observacao importante sobre backend local

O frontend usa:

```env
NEXT_PUBLIC_API_URL=http://localhost:8001
```

Arquivo: `apps/web/.env.local`

O FastAPI sobe corretamente em foreground com:

```powershell
cd apps/api
python -m uvicorn main:app --host 127.0.0.1 --port 8001
```

Mas, durante este handoff, tentativas de manter o FastAPI em background via `Start-Process` encerraram imediatamente. Para testar a tela com dados reais localmente, rode o comando acima em um terminal separado.

## Arquivos tocados nesta etapa

- `apps/api/main.py`
- `apps/web/src/lib/api.ts`
- `apps/web/src/components/forwardtests/forwardtest-detail.tsx`
- `apps/web/src/components/shared/strike-structure-card.tsx`

Tambem ja existiam alteracoes anteriores do ForwardTest em:

- `scripts/export_control_panel.py`
- `apps/web/src/components/backtests/backtest-detail.tsx`
- `apps/web/src/components/layout/app-shell.tsx`
- `apps/web/src/app/forwardtests/`
- `apps/web/src/components/forwardtests/`
- `apps/web/src/components/shared/`

## Estado de git observado

Havia varios arquivos modificados/untracked antes desta etapa. Nao reverter nada sem revisar, pois fazem parte do trabalho em andamento ou alteracoes do usuario.

Arquivos relevantes apareciam como modificados/untracked:

- `apps/api/main.py`
- `apps/web/src/components/backtests/backtest-detail.tsx`
- `apps/web/src/components/layout/app-shell.tsx`
- `apps/web/src/lib/api.ts`
- `scripts/export_control_panel.py`
- `reports/monthly_summary.csv`
- `reports/trades_snapshot_2026-04-28.json`
- `reports/trades_snapshot_latest.json`
- `apps/web/src/app/forwardtests/`
- `apps/web/src/components/forwardtests/`
- `apps/web/src/components/shared/`
- `reports/trades_snapshot_2026-05-06.json`
- `reports/trades_snapshot_2026-05-08.json`
- `tradingview/mtf_moving_averages_bb_levels_table.pine`
- `tradingview/occurrence_mtf.pine`

## Proximo passo recomendado

1. Rodar backend local em foreground:

```powershell
cd apps/api
python -m uvicorn main:app --host 127.0.0.1 --port 8001
```

2. Abrir:

```text
http://127.0.0.1:3000/forwardtests
```

3. Clicar em uma strategy e depois em uma linha de trade.

4. Conferir visualmente:
   - `TradeInspector` aparece abaixo das tabelas.
   - P&L Journey usa `daily_history`.
   - Delta Evolution usa `daily_history.delta`.
   - Breakevens e contratos aparecem no `Trade setup` quando o snapshot trouxer esses campos.
   - Strikes com `|` renderizam corretamente.

5. Antes de commit:

```powershell
python scripts/export_control_panel.py --xlsx "data/control_panel/OP Control Panel.xlsx" --snapshot-only
cd apps/web
npx tsc --noEmit
```

6. Commitar em bloco coerente depois de revisar o diff.

## Decisoes que nao devem ser desfeitas

- Forward trades vivem em `db_robots` com `environment == "CZ_Forward"`.
- Strategy e detectada pelo nome via `strategy_family()` + `underlying`.
- `strategy_id = slugify(family)_underlying.lower()`.
- Aba `FT Strategies` e metadata opcional, nao dependencia operacional.
- Cutoff default: `2026-05-08`, via env `FORWARD_TEST_START_DATE`.
- Milestones de %MP so fazem sentido para credit strategies (`net_credit > 0`).
- A aba `db`/`db_robots` tera breakevens, contratos e outras informacoes por trade; o frontend deve preferir ler esses campos diretamente do trade quando existirem.

