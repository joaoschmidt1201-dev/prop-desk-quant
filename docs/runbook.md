# Runbook Operacional

Procedures recorrentes do desk. Cada uma foi validada em produção.

## Rotinas Diárias

### Morning Briefing (8:00 BRT)
**Automático.** GitHub Actions roda `scripts/morning_briefing.py` em `cron: 0 11 * * 1-5`.

Publica no Discord: VIX, futures ES/NQ/RTY, SPX + moving averages,
GEX levels da semana, earnings intelligence (Finnhub EPS actuals),
calendário macro (Finnhub high-impact).

**Debug local:**
```bash
python scripts/dry_run_briefing.py   # gera sem publicar
```

**Se falhar em produção:**
1. Check GitHub Actions logs → `.github/workflows/morning_briefing.yml`
2. Verificar secrets: `PERPLEXITY_API_KEY`, `DISCORD_WEBHOOK_URL`, `FINNHUB_API_KEY`
3. State files: `state/gex/gex_history_*.json` precisam ter entries da semana atual

### Control Panel Snapshot (2x/dia — AM e PM)
```bash
python scripts/export_control_panel.py
```
Lê `data/control_panel/OP Control Panel.xlsx` (ou baixa do Drive via `--gdrive-id`),
gera `reports/trades_snapshot_YYYY-MM-DD.json` + `trades_snapshot_latest.json`.

## Rotinas Semanais

### Segunda-feira — GEX Update
Invocar skill `/gex-update` ou manual:

1. Baixar CSV Barchart de cada ticker (SPX, NDX, SPY, QQQ) para `data/raw/gex/`
2. Rodar parser:
   ```bash
   python scripts/gex_csv_parser.py "data/raw/gex/$SPX-gamma-levels-exp-YYYYMMDD-weekly.csv" --week YYYY-MM-DD
   # Repetir p/ NDX ($IUXX), SPY, QQQ
   ```
3. Valida `tradingview/gex_weekly_levels.pine` atualizado
4. Commit: `chore: GEX levels <tickers> week YYYY-MM-DD`
5. Push → Streamlit Cloud auto-deploy

### Sexta/Sábado — Backtest Refresh
Invocar skill `/weekly-backtest` ou manual:
```bash
python scripts/ic7_backtest.py
python scripts/ss42_backtest.py
python scripts/ss42_reinvest_sim.py
```
Commit CSVs em `reports/*/`. Valida no viewer antes de push.

## Rotinas Mensais

### Rebalanceamento do Universo (primeiro dia útil)
1. Revisar lista de tickers em `scripts/morning_briefing.py:_SP500_MAJORS`
2. Conferir com CZ se há ETFs novos a monitorar (ex: XLY adicionado)
3. Ajustar `TICKER_CONFIG` em `scripts/gex_csv_parser.py` se necessário

### Housekeeping
- Arquivar CSVs antigos de `data/raw/gex/` em `data/raw/gex/archive/`
- Limpar `reports/ic7_backtest/backtest.log` e `reports/ss42_backtest/backtest.log`
- `git gc --aggressive` se `.git/` estiver grande

## Incidentes

### "No parquets found for date X" no backtest
1. Verificar `G:/Meu Drive/Quant_Data_MD/{UNDERLYING}_chain_X.parquet`
2. Se ausente, rodar pipeline de backfill:
   ```bash
   python scripts/md_step2_mass_extractor.py          # Market Data App (principal)
   python scripts/ibkr_step2_bulk_downloader.py       # IBKR (fallback)
   python scripts/ibkr_step3_daily_assembler.py       # monta parquets no schema padrão
   ```

### Morning brief sem GEX levels
State file `state/gex/gex_history_{ticker}.json` sem entry da semana atual.
Rodar GEX update manualmente (ver Semanal).

### Streamlit Cloud build falha
1. Cache pip pode ter corrompido — "Reboot app" no dashboard Streamlit
2. Se continuar: check `requirements.txt` vs versão instalada local (`pip freeze`)
3. Python version: `runtime.txt` deve ser `python-3.11` (consistente com pyproject + CI)

### Pre-commit hook bloqueia commit legítimo
```bash
# NÃO use --no-verify. Debug:
pre-commit run --all-files   # roda tudo, mostra quem falha
pre-commit run <hook-id>      # roda hook específico
```

## Contatos e Fontes

| Serviço | Role | Fonte credencial |
|---------|------|------------------|
| Perplexity | briefing generation | `.env` / GH secrets |
| Finnhub | calendars + EPS | `.env` / GH secrets |
| Discord | briefing delivery | webhook URL |
| Barchart | GEX CSVs | manual download |
| MenthorQ | GEX validation | manual screenshot |
| Google Drive | control panel storage | `.credentials/gdrive_*` |
| Anthropic | dashboard AI chat | `.env` |
| OpenAI | dashboard AI chat (alt) | `.env` |

## Referências

- `PROJECT_MAP.md` — fluxos e dependências de alto nível
- `context/workflows.md` — descrição narrativa
- `.claude/skills/project/` — skills Claude Code (weekly-backtest, desk-status)
