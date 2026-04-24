---
name: desk-status
description: Imprime um snapshot completo do estado da mesa — trades ativos, posicao por ambiente, ultima atualizacao de GEX, proximas expirations, saude dos backtests e pipelines. Use para handoff, inicio de semana, ou quando o Cristiano pedir "situa".
---

# Desk Status Snapshot

Comando para gerar visao executiva rapida do desk em 1 tela.

## Output esperado

```
═══════════════════════════════════════════════════════════════
  PROP DESK STATUS — YYYY-MM-DD HH:MM BRT
═══════════════════════════════════════════════════════════════

[ POSICAO ]
  CZ Live (APR26)        Open PnL: $X,XXX   RLZD: $X,XXX   Delta: XX
  CZ Live (MAR26)        Open PnL: $X,XXX   RLZD: $X,XXX
  JS Forward (APR26)     Open PnL: $X,XXX   Delta: XX
  FOR Trades             Open PnL: $X,XXX

[ TRADES ATIVOS ]
  <trade_name>           DTE: XX   PnL: $XXX    URL: optionstrat.com/...
  <...>                  <...>     <...>        <...>

[ GEX LEVELS (semana atual) ]
  SPX (expiry YYYY-MM-DD): flip XXXX, pos XXXX/XXXX, neg XXXX/XXXX
  NDX (expiry YYYY-MM-DD): flip XXXXX, ...
  SPY / QQQ: ...
  Fonte: Barchart  |  Ultima atualizacao: YYYY-MM-DD

[ BACKTESTS ]
  IC7  NDX 7DTE   Ultima trade: YYYY-MM-DD   Total PnL: $X,XXX
  SS42 SPX 42DTE  Ultima trade: YYYY-MM-DD   Total PnL: $X,XXX
  SS42 RUT 42DTE  Ultima trade: YYYY-MM-DD   Total PnL: $X,XXX

[ PIPELINE HEALTH ]
  Data lake G:/ : ultimo parquet YYYY-MM-DD  (X dias atras)
  Morning brief : ultima execucao YYYY-MM-DD
  Dashboard     : ultimo snapshot YYYY-MM-DD
```

## Como montar

1. **Posicao** — ler `reports/trades_snapshot_latest.json`
2. **Trades ativos** — mesmo arquivo, filtrar `status != "CLOSED"`
3. **GEX levels** — ler ultima entrada de cada `state/gex/gex_history_*.json`
4. **Backtests** — ultima linha dos CSVs em `reports/ic7_backtest/` e `reports/ss42_backtest/`
5. **Data lake health** — `ls -la "G:/Meu Drive/Quant_Data_MD/"` ordenado por data
6. **Morning brief health** — checar ultimo run em GitHub Actions ou `reports/morning_briefing_*.log`

## Formato

- Usar box Unicode (═ ─ │) para secoes
- Valores monetarios: `$X,XXX` (sem centavos para >$100)
- Delta sempre com sinal (+/-)
- Emoji SOMENTE se o Cristiano pedir explicitamente
- Output em portugues, secoes em ingles (consistente com CLAUDE.md)

## Quando usar

- Inicio de semana (segunda 9h BRT)
- Antes de call com Cristiano
- Apos long weekend / feriado
- Handoff entre operadores
- Cristiano pergunta "como estamos?"
