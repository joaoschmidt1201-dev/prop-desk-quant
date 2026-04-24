# Chat Handoff

## Estado Atual

- Streamlit hospedado continua no `Streamlit Community Cloud`.
- Decisão tomada: manter assim por enquanto, sem migrar para hospedagem paga/always-on.
- Quando o app dorme, o procedimento aceito é clicar para reativar.

## IC7 NDX

- O backtest `IC7 7DTE NDX` foi corrigido para deixar as close rules consistentes no viewer.
- Regras atualmente disponíveis no Streamlit para IC7:
  - `Hold to Expiration`
  - `50% Max Profit`
  - `4 DTE`
  - `Loss = Max Profit`
- O `trade auditor` do IC7 já marca corretamente o ponto de saída dessas regras.
- O MTM diário do IC7 não usa mais `entry IV`.
- Fontes aceitas no diário do IC7:
  - `market`
  - `hybrid_day_iv`
  - `bs_day_iv`
  - `intrinsic`
- `bs_entry_iv` foi removido do fluxo.

## Data Lake

- O data lake foi atualizado para `NDX`, `SPX` e `RUT` até onde o provider permitiu.
- Cobertura efetiva atual:
  - `NDX`: até `2026-04-21`
  - `SPX`: até `2026-04-21`
  - `RUT`: até `2026-04-21`
- Datas ainda faltantes nos três tickers:
  - `2026-04-03`
  - `2026-04-10`
  - `2026-04-22`
- Leitura operacional:
  - `2026-04-03` provavelmente ausente por feriado (`Good Friday`)
  - `2026-04-10` a API listou expirações, mas todas as chains retornaram `404`
  - `2026-04-22` o endpoint de expirations retornou `400` no dia

## SS42 SPX/RUT

- Os backtests `SS42 SPX` e `SS42 RUT` foram rerodados após o refresh do data lake.
- Também foram regenerados os CSVs pré-computados de reinvestimento usados pelo Streamlit Cloud para:
  - `25% Profit Target`
  - `50% Profit Target`
  - `75% Profit Target`
  - `50% Profit or 24 DIT`
  - `24 DIT`
- O Streamlit hospedado já foi atualizado com esses CSVs.

## Morning Briefing

- O `morning_briefing.py` foi atualizado para incluir no bloco técnico do SPX:
  - `D EMA9`
  - `D EMA20`
  - `W EMA9`
- Já existiam:
  - `W EMA20`
  - `D SMA50`
  - `D SMA200`
- A instrução do prompt foi ajustada para usar esses níveis quando forem relevantes, sem forçar menção diária de todos.
- O briefing foi testado via GitHub workflow e o resultado foi aprovado pelo usuário.

## GEX Indicator

- O workflow do indicador de GEX foi expandido para suportar `SPY` com níveis manuais do `TradingLit`.
- `SPX`, `NDX` e `QQQ` continuam no fluxo normal já existente.
- O histórico manual do `SPY` foi salvo em [gex_history_spy.json](/C:/Users/joao%20smith/OneDrive/Documentos/Prop_Desk_Quant_Codex/gex_history_spy.json).
- O `SPY` agora tem `20` semanas históricas cadastradas, de `2025-12-08` até `2026-04-20`.
- Em cada semana do `SPY`, o JSON preserva:
  - `raw_text` com o texto bruto do TradingLit
  - `manual_levels` com os níveis estruturados para o Pine
- O gerador [scripts/gex_csv_parser.py](/C:/Users/joao%20smith/OneDrive/Documentos/Prop_Desk_Quant_Codex/scripts/gex_csv_parser.py) foi alterado para:
  - suportar níveis manuais livres por label para `SPY`
  - manter `SPX/NDX/QQQ` no modelo original
  - desenhar labels em todas as semanas, não só na semana atual
  - desenhar a semana de segunda abertura até sexta fechamento com `W = D * 5 - 1`
  - desenhar separadores verticais de segunda a sexta
  - desenhar separadores apenas quando o ticker tiver dados naquela semana
- A convenção visual atual do `SPY` no Pine ficou:
  - `p` / `coi` em verde
  - `ag` em roxo
  - `g flip` em cinza
  - `n` / `poi` em vermelho
- O Pine final do dia está em [tradingview/gex_weekly_levels.pine](/C:/Users/joao%20smith/OneDrive/Documentos/Prop_Desk_Quant_Codex/tradingview/gex_weekly_levels.pine).
- Esse é o arquivo que deve ser copiado integralmente para o TradingView em chats futuros.
- Durante a sessão houve vários ajustes por limites e parsing do Pine:
  - limite de tokens
  - escopo de `_lines/_labels`
  - labels históricos
  - span semanal
  - separadores por ticker
  - linha vertical de sexta
- Estado final esperado do indicador:
  - labels em todas as semanas
  - `SPY` usando histórico manual do TradingLit
  - `SPX/NDX/QQQ` sem semanas fantasma com separadores
  - linhas horizontais indo até o fechamento de sexta
  - separadores verticais de segunda a sexta

## Commits Relevantes

- `88d542d` — `Fix IC7 close rules and daily MTM realism`
- `e08f107` — `Add hold to expiration option for IC7 viewer`
- `be813d5` — `Update SS42 backtests after data refresh`
- `a566ecd` — `Add EMA levels to SPX morning briefing`

## Pendências Conhecidas

- `THETADATA_API_KEY` segue vazia no `.env`; atualização via ThetaData continua bloqueada.
- O provider atual ainda não entregou os três dias faltantes citados acima.
- O Streamlit Cloud só reflete o que estiver commitado e enviado para `main`.
- O indicador de GEX do TradingView foi trabalhado localmente; se quiser persistir no GitHub, ainda é preciso `commit/push`.

## Como Usar Este Arquivo

- Em um novo chat, pedir para ler `CHAT_HANDOFF.md` primeiro.
- Tratar este arquivo como referência do estado operacional mais recente.
