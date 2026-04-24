# OP Control Panel — AI Reporting Plan
*Gerado em: 2026-04-23*

---

## Objetivo

Criar uma camada Python que:
1. Exporta os dados do Google Sheets (via openpyxl no .xlsx local, ou Google Sheets API)
2. Gera artefatos estruturados (JSON, CSV, parquet)
3. Alimenta o morning briefing e relatórios de qualidade de trade

Nenhuma mudança no Google Sheets. Nenhuma mudança no Make.

---

## Arquivo: `scripts/export_control_panel.py`

### Função 1: `export_active_trades()`

Lê `db_robots` e `db_cria` → gera `reports/trades_snapshot_YYYYMMDD.json`

```json
{
  "generated_at": "2026-04-23T08:15:00",
  "month": "APR26",
  "portfolio": {
    "open_pnl_total": -16965,
    "delta_total": -173,
    "max_loss_exposed": 3150,
    "n_active_trades": 1,
    "rlzd_month": -19149.51
  },
  "trades": [
    {
      "name": "T45 RUT RJL42",
      "env": "Live",
      "underlying": "RUT",
      "open_price": 2645,
      "open_date": "2026-04-13",
      "exp_date": "2026-05-22",
      "dte_remaining": 29,
      "dit": 10,
      "net_credit": 11850,
      "max_loss": 3150,
      "pnl_latest": -16965,
      "pnl_pct_max": -1.432,
      "delta_latest": -173,
      "lw_be": 2410.5,
      "up_be": 2789.5,
      "current_price": 2645,
      "pct_to_lw_be": -0.0887,
      "pct_to_up_be": 0.0546,
      "status": "active",
      "tent_status": "inside",
      "url": "https://optionstrat.com/7Ubm..."
    }
  ]
}
```

### Função 2: `export_trade_history()`

Lê toda a série temporal do db_robots → gera `reports/trade_history.parquet`

```
Columns: date | trade_name | env | pnl | delta | dit | dte_remaining
```

Permite backtest de management rules, análise de P&L por DTE, curva de equity.

### Função 3: `export_monthly_summary()`

Consolida todos os trades fechados (RLZD != 0) → gera `reports/monthly_summary.csv`

```
month | trade_name | structure | underlying | dte_open | dit_close | max_profit | rlzd | pct_realized | won
APR26 | T41 RUT... | CALL SP7  | RUT        | 7        | 3         | 3150       | -15149| -480%        | 0
MAR26 | T26 BATMAN14 | BAT14   | SPX        | 14       | 14        | 965        | +965  | +100%        | 1
```

---

## Relatório de Qualidade de Trade

Gerado pelo morning briefing (`dry_run_briefing.py`) a partir do snapshot JSON.

### Seção de Portfólio no Briefing

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 PORTFÓLIO ATUAL — APR26 (atualizado 2026-04-22)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Open PnL:  -$16,965  |  RLZD mês:  -$19,149  |  Delta total: -173

TRADES ATIVOS (1):

⚠️ T45 RUT RJL42
   Underlying: RUT @ 2645 | DTE: 29 | DIT: 10
   PnL: -$16,965 (-143% do Max Profit de $11,850)
   Delta: -173 (bearish bias)
   BEs: Lw 2410.5 (-8.9% do spot) | Up 2789.5 (+5.5% do spot)
   Status: FORA DA TENT (PnL abaixo de -100%)
   ⚠️ ALERTA: Trade acima do stop loss referência (1x Max Profit)

TRADES FECHADOS NO MÊS (5):
   T41 RUT CALL BEAR: -$15,149 (-481%) ❌
   T43 SPX BW IC 7:   resultado pendente
   T44 RUT IC 7:      resultado pendente
   T42 RUT CALL BEAR 28: -$4,000 ❌
   T46 RUT RJL7:      resultado pendente
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### Análise de Leaks (gerada trimestralmente)

Com `trade_history.parquet` e `monthly_summary.csv`, a IA pode responder:

```
Análise de Leaks — Jan-Apr 2026:

1. ESTRUTURA COM MAIOR PERDA: 7DTE trades (RLZD médio: -X%)
   Padrão: Abertura em momentum de alta → mercado reverte → sem tempo para ajuste

2. DRIFT DE DELTA: T45 abriu com Delta -X, subiu para -173 em 10 dias
   Padrão: RJL42 em tendência direcional forte acumula delta

3. TIMING DE FECHAMENTO: 3 de 5 trades fechados com DIT < 50% do DTE original
   Pergunta: fechamento antecipado foi ótimo ou subótimo vs hold até 50% profit?

4. WIN RATE POR ESTRUTURA:
   BAT42: X/X = XX%
   IC7:   X/X = XX%
   RJL42: X/X = XX%
```

---

## Plano de Implementação

### Fase 1 — Exportador (1-2 dias)
- `scripts/export_control_panel.py` com as 3 funções
- Integração no morning briefing (seção de portfólio)
- Teste com dados reais do APR26

### Fase 2 — Relatório de Qualidade (1 semana)
- Prompt de análise de trade para Claude API
- Output: análise de leaks + strengths por mês
- Arquivo salvo em `reports/quality_YYYYMMDD.md`

### Fase 3 — Dashboard para CZ (1-2 dias)
- `scripts/generate_cz_dashboard.py`
- HTML estático de 1 página
- Integrado no briefing diário

### Fase 4 — Histórico acumulado (1 mês de dados)
- Com 2+ meses de parquet, análise estatística fica possível
- Win rate por estrutura, Sharpe aproximado, drawdown máximo
- Input para decisões de tamanho de posição futuras
