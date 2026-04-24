# Prop Desk Quant

Infraestrutura quantitativa da mesa proprietária de opções — pipelines de dados,
backtests, GEX, morning briefing e viewers. O sistema é **motor de decisão**, não
executa ordens (regra inegociável do desk).

> Hierarquia: João (Architect) reporta a Cristiano (Head Trader).
> Universo: ETFs macro + commodities (SPX, NDX, RUT, SPY, QQQ, XLV, GLD, SLV, BTC).
> Zero stocks individuais. Mínimo 7DTE.

## Quick Start

```bash
# Clone e setup
git clone https://github.com/joaoschmidt1201-dev/prop-desk-quant.git
cd prop-desk-quant

# Dependências runtime (Streamlit + morning briefing)
pip install -r requirements.txt

# Dev (ruff, mypy, pytest, pre-commit)
pip install -r requirements-dev.txt
pre-commit install

# Heavy deps — backtests, IBKR, scraping
pip install -r requirements-research.txt
```

## Estrutura

```
.
├── scripts/               # entry points CLI (backtest, briefing, parsers)
├── tests/                 # pytest suite (smoke tests dos engines)
├── data/                  # inputs (gitignored)
│   ├── raw/gex/           #   CSVs Barchart por ticker/semana
│   ├── control_panel/     #   OP Control Panel.xlsx
│   ├── cache/             #   caches locais (ndx_closes, etc)
│   ├── scraped/           #   outputs de scrapers (menthorq, etc)
│   └── market_data/       #   parquets locais
├── state/                 # estado persistente (tracked)
│   └── gex/               #   histórico GEX por ticker + levels input
├── reports/               # outputs dos backtests (CSVs tracked, logs ignored)
│   ├── ic7_backtest/      #   Iron Condor 7DTE NDX
│   └── ss42_backtest/     #   Short Strangle 42DTE SPX/RUT
├── tradingview/           # Pine Scripts gerados (GEX Weekly Levels)
├── context/               # docs operacionais, intel CZ, meetings
├── infra/                 # docker, GCP VM (IBKR downloader)
├── .github/workflows/     # CI (morning brief, lint, tests)
└── .claude/skills/project/ # skills Claude Code do projeto
```

## Fluxos Principais

Ver [`PROJECT_MAP.md`](PROJECT_MAP.md) para detalhes de cada fluxo.

| Fluxo | Script | Output | Cadência |
|-------|--------|--------|----------|
| Morning Briefing | `morning_briefing.py` | Discord webhook | Diário 8h BRT (Actions) |
| GEX Weekly Update | `gex_csv_parser.py` | `state/gex/*.json` + Pine | Semanal (Seg) |
| IC7 Backtest | `ic7_backtest.py` | `reports/ic7_backtest/*.csv` | Após data refresh |
| SS42 Backtest | `ss42_backtest.py` | `reports/ss42_backtest/*.csv` | Após data refresh |
| CZ Dashboard | `cz_dashboard_app.py` | Streamlit local | On-demand |
| IC7 Viewer | `ic7_viewer.py` | Streamlit Cloud | Auto-deploy |
| Control Panel Export | `export_control_panel.py` | `reports/trades_snapshot_*.json` | Diário 2x (AM/PM) |

## Desenvolvimento

```bash
# Lint
ruff check scripts/
ruff format scripts/

# Tests
pytest
pytest -m "not slow and not network"  # local rápido
pytest -m slow                         # backtest completo

# Type check
mypy scripts/
```

## Documentação

| Doc | Propósito |
|-----|-----------|
| [`CLAUDE.md`](CLAUDE.md) | Identidade do sistema, metodologia do desk, regras inegociáveis |
| [`PROJECT_MAP.md`](PROJECT_MAP.md) | Mapa completo de workflows, scripts críticos, dependências |
| [`AGENTS.md`](AGENTS.md) | Instruções específicas para agentes de IA (Codex, Claude) |
| [`docs/runbook.md`](docs/runbook.md) | Procedimentos operacionais recorrentes |
| [`docs/architecture.md`](docs/architecture.md) | Decisões arquiteturais, fluxo de dados |
| `context/workflows.md` | Descrição narrativa dos fluxos |
| `context/data_map.md` | Onde vive cada tipo de dado |

## Variáveis de Ambiente

```bash
# Morning briefing (GitHub Actions secrets)
PERPLEXITY_API_KEY=pplx-...
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
FINNHUB_API_KEY=...

# CZ Dashboard (local)
ANTHROPIC_API_KEY=sk-ant-...   # chat AI via Claude
OPENAI_API_KEY=sk-...          # chat AI via ChatGPT (opcional)

# IBKR pipeline (local .env)
IBKR_HOST=localhost
IBKR_PORT=4002
IBKR_TRADING_MODE=paper
```

## Regras Inegociáveis

1. **Nenhum script toca broker.** Execução é 100% manual via Cristiano.
2. **Sem ações individuais** no universo de trading automatizado (risco idiossincrático).
3. **Mínimo 7DTE** — zero intraday / 0DTE.
4. **Zero mock de dados de opções** — backtest lê parquet real ou Black-Scholes local.

## Licença

Proprietary — uso interno do Prop Desk.
