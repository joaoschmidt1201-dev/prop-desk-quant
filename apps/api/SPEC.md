# CZ Dashboard API — Contrato

FastAPI backend que expõe os dados do snapshot processado por `scripts/export_control_panel.py` e um endpoint de chat AI com contexto filtrado.

## Convenções

- Base URL local: `http://localhost:8000`
- Base URL prod: TBD (Render)
- Todas as respostas são JSON exceto `/api/chat` (streaming SSE)
- CORS liberado para `http://localhost:3000` (dev) e domínio de produção
- Erros: `{"error": "...", "code": "<machine_readable>"}` com HTTP status apropriado
- Datas: ISO 8601 (`YYYY-MM-DD`)
- Valores monetários: number (float), em USD, sem formatação

## Endpoints

### `GET /api/health`
Healthcheck. Resposta: `{"status": "ok", "snapshot_age_seconds": 142}`

### `GET /api/snapshot`
Snapshot completo (último processado). Forma idêntica ao `reports/trades_snapshot_latest.json`.
Headers: `X-Snapshot-Generated-At: <iso>`, `Cache-Control: max-age=300`

### `POST /api/snapshot/refresh`
Força re-download do Drive + reprocessamento. Async; retorna 202 com `{"job_id": "..."}`.
Polling: `GET /api/snapshot/refresh/{job_id}` retorna `{"status": "running|done|failed", "snapshot": ... | null}`.

### `GET /api/months`
Lista de meses/ambientes disponíveis no snapshot atual.
```json
{
  "months": [
    {"sheet": "APR26", "env": "CZ_Live", "label": "Apr 2026", "n_trades": 6, "active": true},
    {"sheet": "MAR26", "env": "CZ_Live", "label": "Mar 2026", "n_trades": 8, "active": false}
  ]
}
```

### `GET /api/trades?month=APR26&env=CZ_Live`
Trades do filtro. `month` aceita CSV (`APR26,MAR26`) para filtros multi-mês.
```json
{
  "filter": {"months": ["APR26"], "env": "CZ_Live"},
  "trades": [
    {
      "name": "T45 RUT RJL42",
      "month": "APR26",
      "ticker": "RUT",
      "structure": "RJL",
      "open_date": "2026-03-12",
      "exp_date": "2026-04-24",
      "dte_initial": 42,
      "dte_remaining": -3,
      "status": "active",
      "pnl": -14805.0,
      "max_loss": -25000.0,
      "net_credit": 12000.0,
      "delta": -8.4
    }
  ]
}
```

### `GET /api/kpis?month=APR26&env=CZ_Live`
KPIs computados sobre o filtro ativo. Mesma lógica do dashboard atual mas restrita ao período.
```json
{
  "filter": {"months": ["APR26"], "env": "CZ_Live"},
  "pnl": {"open": -33954.51, "rlzd": 0, "delta": -8.4, "max_profit": 18000},
  "risk": {"max_loss_exposed": -75000, "net_credit_at_risk": 60000, "est_daily_theta": 230},
  "performance": {"win_rate": 0.42, "profit_factor": 1.18, "expectancy": 145},
  "trade_intel": {"best_trade": 4500, "worst_trade": -14805, "avg_dte": 35, "n_active": 6, "n_closed": 12}
}
```

### `GET /api/equity?month=APR26&env=CZ_Live`
Series de equity curve (sheet-anchored). Restrito ao filtro.
```json
{
  "filter": {"months": ["APR26"], "env": "CZ_Live"},
  "series": [
    {"date": "2026-03-12", "cumulative_pnl": 0},
    {"date": "2026-03-13", "cumulative_pnl": 1200},
    ...
  ]
}
```

### `POST /api/chat`
AI chat streaming. Server-Sent Events.
```json
// Request body
{
  "messages": [
    {"role": "user", "content": "Por que o T45 está perdendo tanto?"}
  ],
  "filter": {"months": ["APR26"], "env": "CZ_Live"},
  "provider": "anthropic"  // ou "openai"
}
```
Response: SSE stream de eventos `data: {"delta": "...", "done": false}\n\n` até `data: {"done": true}\n\n`.

System prompt inclui:
- Identidade (CZ Dashboard AI, contexto do desk)
- Trades do filtro ativo (JSON serializado, compacto)
- KPIs do filtro ativo
- Diretivas: nunca recomendar execução, focar em análise quantitativa, identificar leaks/correlações

## Caching

- `/api/snapshot`, `/api/trades`, `/api/kpis`, `/api/equity`, `/api/months` → cache em memória 5 min, invalidado por `/api/snapshot/refresh`
- `/api/chat` → sem cache

## Auth (Fase 4 — deploy)

- Localhost: sem auth
- Prod: API key via header `X-Api-Key` (single key, env var). Frontend lê de `NEXT_PUBLIC_API_KEY` que é proxy via Next API route (key real fica server-side).

## Stack

- FastAPI + uvicorn
- pydantic v2
- pandas + openpyxl (reusa lógica de `scripts/export_control_panel.py`)
- anthropic + openai SDKs (streaming)
- python-dotenv
