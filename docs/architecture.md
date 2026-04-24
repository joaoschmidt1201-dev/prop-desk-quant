# Arquitetura

## Princípios

1. **Dados imutáveis fora do repo.** Parquets históricos vivem em `G:/Meu Drive/Quant_Data_MD/`, não no git. Repositório guarda código + CSVs leves gerados.
2. **State separado de input.** `state/` = artefatos gerados/persistidos pelos scripts (tracked). `data/` = inputs brutos e caches (gitignored, estrutura preservada com `.gitkeep`).
3. **Entry points finos, engines reutilizáveis.** `scripts/*.py` são CLIs. A lógica de negócio vive dentro de cada engine (ainda não extraída em pacote — planejado para fase 2).
4. **Zero dependência de execução ao vivo.** Backtests operam offline (parquets). Morning briefing só lê dados de terceiros read-only (yfinance, finnhub, perplexity).

## Fluxo de Dados

```
EXTERNOS                  LOCAL                        OUTPUT
─────────                 ─────                        ──────

Market Data App  ─┐
IBKR (TWS)       ─┤→ G:/Meu Drive/Quant_Data_MD/     (parquets)
ThetaData        ─┘   {UNDERLYING}_chain_YYYY-MM-DD.parquet
                                     │
                                     ▼
                      scripts/{ic7,ss42}_backtest.py
                                     │
                                     ▼
                      reports/{ic7,ss42}_backtest/*.csv  → Streamlit Cloud (ic7_viewer)


Barchart website (manual) → data/raw/gex/*.csv
                                     │
                                     ▼
                      scripts/gex_csv_parser.py
                                     │
                          ┌──────────┴──────────┐
                          ▼                     ▼
                state/gex/*.json    tradingview/gex_weekly_levels.pine
                          │                     │
                          ▼                     ▼
            scripts/morning_briefing.py       TradingView
                          │
                          ▼
                  Discord webhook (daily 8h BRT)


OP Control Panel.xlsx (Google Sheets)
           │
           ▼ (baixa via Drive API ou local path)
scripts/export_control_panel.py
           │
           ├→ reports/trades_snapshot_YYYY-MM-DD.json
           ├→ reports/trades_snapshot_latest.json
           ├→ reports/trade_history.parquet
           └→ reports/monthly_summary.csv
                          │
                          ▼
              scripts/cz_dashboard_app.py  (Streamlit)
                          │
                          ▼
                  Dashboard CZ (trades + AI chat)
```

## Camadas

### 1. Ingestion
Scripts que chegam em dados externos e os materializam localmente:
- `md_step1/2/3_*.py` — Market Data App (fonte principal histórica)
- `ibkr_step1/2/3_*.py` — Interactive Brokers (fallback + backfill)
- `thetadata_step1/2.py` — ThetaData (fonte alternativa)
- `mq_scraper.py` — MenthorQ historical GEX
- `gex_csv_parser.py` — Barchart CSV → state + Pine
- `gex_ocr_helper.py`, `gex_input.py` — captura visual MenthorQ/TradingLit

### 2. Engine
Lógica de backtest e cálculo de P&L:
- `ic7_backtest.py` — Iron Condor 7DTE NDX (estratégia principal)
- `ss42_backtest.py` — Short Strangle 42DTE SPX/RUT (secundária)
- `ss42_reinvest_sim.py` — simulação de cenários de reinvestimento

### 3. Presentation
Interfaces para operador:
- `ic7_viewer.py` — Streamlit Cloud, auditoria trade-a-trade, equity curve
- `cz_dashboard_app.py` — Streamlit local, Options Control Panel + AI chat
- `morning_briefing.py` — Discord (pré-mercado)
- `tradingview/*.pine` — overlays no TradingView

### 4. Tooling
Scripts de suporte não-críticos:
- `export_control_panel.py` — extrai xlsx → JSON/Parquet normalizado
- `clean_db_robots.py` — limpeza da base de robots da planilha
- `whisper_transcriber.py` — transcrição de áudios CZ
- `gex_compare.py` — cross-check Barchart vs TradingLit vs MenthorQ
- `add_dashboard_ai_pack.py`, `build_control_panel_template.py` — geração de planilhas

## State vs Data

| Pasta | Propósito | Git |
|-------|-----------|-----|
| `state/gex/` | Histórico GEX calculado + input semanal | tracked |
| `data/raw/gex/` | CSVs Barchart baixados | ignored |
| `data/control_panel/` | OP Control Panel xlsx | ignored |
| `data/cache/` | Caches de terceiros (yfinance, etc) | ignored |
| `data/scraped/` | Outputs de scrapers | ignored |
| `data/market_data/` | Parquets locais (cache do G:/) | ignored |
| `reports/*/*.csv` | Backtest outputs | tracked (alimenta viewer) |
| `reports/*/*.log` | Logs de execução | ignored |
| `reports/trades_snapshot_*.json` | Snapshots do control panel | tracked |

## Dependências Críticas

**Sem estes, o sistema para:**
- Google Drive for Desktop montado em `G:/` (Windows) — data lake principal
- Python 3.11 (não 3.12 — `runtime.txt`, `pyproject.toml` e workflow travam nisso)
- `PERPLEXITY_API_KEY` + `DISCORD_WEBHOOK_URL` em GH secrets — morning briefing

**Desejáveis mas não bloqueantes:**
- `FINNHUB_API_KEY` — sem ele, briefing perde earnings + macro calendar
- `ANTHROPIC_API_KEY` ou `OPENAI_API_KEY` — AI chat do dashboard vira read-only
- `.credentials/gdrive_*.json` — sem isso, `export_control_panel.py` exige xlsx local

## Decisões Recentes

- **2026-04-24**: consolidação Prop_Desk_Quant_Codex → Prop_Desk_Quant em single tree. Foi feito merge dos 4 commits Codex + sync de trabalho local. (commit `2616c7d`)
- **2026-04-24**: Fase 1 de reorg — `state/` separado de `data/`, `data/` particionado em `raw/control_panel/cache/scraped/market_data`. Bugs de case (`Data` vs `data`) corrigidos. (commit `4cebcdd`)
- **2026-04-24**: Fase 3 tooling — pyproject.toml, ruff, pre-commit, requirements pinados, python 3.11 unificado. (commit em HEAD)
- **2026-04-24**: Fase 5 CI — lint + tests workflows, skills `/weekly-backtest` e `/desk-status` tracked.

## Planejado (não feito)

- **Fase 2 (bloqueada)**: reorganizar `scripts/` em pacote `src/prop_desk/` por domínio (data_providers, gex, strategies, viewers, briefing). Requer testar Streamlit deploy + CI workflow paths.
- **Tests de regressão**: scaffolding existe (`tests/`), cobertura real ainda parcial.
- **Automação GEX via API**: substituir download manual Barchart por endpoint (se disponível).
