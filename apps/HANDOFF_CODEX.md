# Handoff pro Codex — Continuar correções do CZ Dashboard

## ✅ O que JÁ foi feito (NÃO refazer)

1. **TAREFA 2 (select Claude/GPT ilegível)** — corrigido em `apps/web/src/components/dashboard/chat-panel.tsx`. Agora usa shadcn `<Select>`.
2. **TAREFA 1A (exporter)** — `scripts/export_control_panel.py` já foi modificado para:
   - Detectar automaticamente abas que casam regex `^(JS )?[A-Z]{3}\d{2}$` (APR26, MAR26, JS APR26, futuras MAY26 etc.)
   - `read_individual_trade_pnls()` agora retorna tupla `(individual_pnls, sheet_to_trades)`
   - Cada trade no snapshot recebe campo novo `sheet` (ex: "APR26", "JS APR26", ou null)

## ⏭️ O que FALTA (passe para o Codex nesta ordem)

### PASSO 1 — Regenerar snapshot

Você roda no terminal (não precisa Codex):

```bash
python scripts/export_control_panel.py --gdrive-id 1RIXpDUIq1692_6UwoPFYyrKtukYB2UArCTWvI6Y5Xbk
```

Isso atualiza `reports/trades_snapshot_latest.json` com o campo novo `sheet` em cada trade. Procure no log a linha `[trade-sheets detected] [...]` — deve listar `MAR26`, `APR26`, `JS APR26` (e qualquer outra MMMyy que exista hoje na planilha).

**Verificação:**
```bash
python -c "import json; d=json.load(open('reports/trades_snapshot_latest.json')); from collections import Counter; print(Counter(t.get('sheet') for t in d['trades']))"
```
Saída esperada: contagem por sheet, ex.: `Counter({'APR26': 6, 'MAR26': 8, 'JS APR26': 5, None: 24})`. Os `None` são trades de db_robots que não estão em nenhuma aba MMMyy — OK.

### PASSO 2 — Backend: filtrar por `sheet` (Codex)

Cole no Codex:

```
codex exec --sandbox workspace-write "
Edit apps/api/main.py to switch the filtering from 'environment_raw' to the new 'sheet' field on each trade.

Context: scripts/export_control_panel.py was just updated to inject a 'sheet' field into every trade in the snapshot. Valid values match regex ^(JS )?[A-Z]{3}\d{2}$ (e.g. APR26, MAR26, JS APR26). Trades not in any month sheet have sheet=null and must be excluded from /api/months and from filtered queries.

Make these changes in apps/api/main.py:

1. Add at the top after imports:
   import re
   MONTH_SHEET_REGEX = re.compile(r'^(JS )?[A-Z]{3}\d{2}\$')

2. In parse_months(): keep input as-is (no .lower()), strip only.

3. In trade_in_filter(): replace the 'environment_raw' comparison with:
   sheet = (trade.get('sheet') or '').strip()
   if not sheet or not MONTH_SHEET_REGEX.match(sheet):
       return False if months else True  # exclude orphan trades when filtering, allow when no filter
   if months and sheet not in months:
       return False
   if env and trade.get('environment') != env:
       return False
   return True

4. In get_months(): iterate trades by trade.get('sheet'), skip None and any not matching MONTH_SHEET_REGEX. Group by sheet, count active. Sort: active first, then by year DESC, then by month DESC. Use this MONTH_NUM mapping for sort:
   MONTH_NUM = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
   For sort key, parse sheet 'APR26' or 'JS APR26' -> (year=26, month=4). Sort key = (-active, -year, -month).

5. In _pretty_month_label(): keep current behavior; it already produces 'Apr 2026' for 'APR26' and 'JS Apr 2026' for 'JS APR26'.

Verify by:
- Restart the API: cd apps/api && python -m uvicorn main:app --reload --port 8000
- curl 'http://127.0.0.1:8000/api/months' should ONLY list MMMyy sheets (no Live, FOR JS, etc.)
- curl 'http://127.0.0.1:8000/api/kpis?month=APR26' should return ~6 trades with the same numbers as before
- curl 'http://127.0.0.1:8000/api/trades?month=JS%20APR26' should work too (URL-encoded space)

Reply with EXACTLY: 'DONE — months listed: <comma-separated months>' on success, or 'FAIL: <reason>' on error.
" 2>&1 | tail -20
```

### PASSO 3 — Endpoint Refresh + botão funcional (Codex)

Cole no Codex:

```
codex exec --sandbox workspace-write "
Add a snapshot refresh feature to the CZ Dashboard.

Backend (apps/api/main.py):
1. Add at the top: import subprocess, sys, threading
2. Add a module-level lock variable: _refresh_lock = threading.Lock(); _refresh_running = {'state': False}
3. Add a constant: GDRIVE_ID = '1RIXpDUIq1692_6UwoPFYyrKtukYB2UArCTWvI6Y5Xbk'
4. Add new endpoint after /api/snapshot:

   @app.post('/api/snapshot/refresh')
   def refresh_snapshot():
       if _refresh_running['state']:
           return JSONResponse({'status': 'already_running'}, status_code=409)
       def run():
           with _refresh_lock:
               _refresh_running['state'] = True
               try:
                   subprocess.run(
                       [sys.executable, str(REPO_ROOT / 'scripts' / 'export_control_panel.py'),
                        '--gdrive-id', GDRIVE_ID],
                       cwd=str(REPO_ROOT), check=False, capture_output=True, timeout=300,
                   )
               finally:
                   _refresh_running['state'] = False
                   _snapshot_cache['data'] = None  # invalidate cache
       threading.Thread(target=run, daemon=True).start()
       return JSONResponse({'status': 'refresh_started'}, status_code=202)

Frontend (apps/web/src/components/dashboard/header.tsx):
1. Import the api client and add a new function call. Replace the existing onClick of the refresh button so it does:
   - POST /api/snapshot/refresh (use fetch directly, no streaming needed)
   - After 8 seconds, refetch the health query AND invalidate the React Query cache for ['kpis'], ['trades'], ['months']
   - During the 8s, keep the button spinning (already has isFetching state — extend with local 'isRefreshing' useState)
2. Use useQueryClient from @tanstack/react-query to invalidate.

Don't break the existing health refetchInterval. Don't add toast libs (sonner is installed but skip it).

Verify:
- Restart API: cd apps/api && python -m uvicorn main:app --reload --port 8000
- curl -X POST 'http://127.0.0.1:8000/api/snapshot/refresh' should return 202 with {status: refresh_started}
- A second curl within 1s should return 409
- Open http://localhost:3000, click the refresh button — server log should show export_control_panel.py running

Reply EXACTLY: 'DONE' or 'FAIL: <reason>'.
" 2>&1 | tail -20
```

### PASSO 4 — Smoke test (você no terminal)

Com API e frontend rodando:

```bash
# 1. API endpoints
curl 'http://127.0.0.1:8000/api/months' | python -m json.tool
curl 'http://127.0.0.1:8000/api/kpis?month=APR26' | python -m json.tool

# 2. Frontend
# Abrir http://localhost:3000 — confirmar:
#   - Filtros mostram só MAR26, APR26, JS APR26 (e o que mais houver MMMyy)
#   - Selecionar APR26 → 6 trades
#   - Select Claude/GPT abre legível
#   - Botão refresh dispara o exporter
#   - Chat AI responde (se você colou as keys novas em apps/api/.env)
```

### PASSO 5 — Commit (você ou Codex)

```bash
git add scripts/export_control_panel.py apps/api/main.py \
        apps/web/src/components/dashboard/chat-panel.tsx \
        apps/web/src/components/dashboard/header.tsx \
        apps/HANDOFF_CODEX.md
git commit -m "fix(dashboard): filtrar por aba MMMyy + select shadcn + botão refresh

- Exporter detecta abas MMMyy/JS MMMyy automaticamente (APR26, MAR26,
  JS APR26, futuras MAY26 etc.) e injeta campo 'sheet' em cada trade
- Backend filtra por 'sheet' em vez de 'environment_raw'; /api/months
  lista somente abas válidas, ordenadas por mês/ano DESC
- Chat panel: select Claude/GPT trocado por shadcn Select (legível)
- Endpoint POST /api/snapshot/refresh dispara exporter assíncrono;
  botão refresh do header invalida cache do React Query"
git push
```

---

## Como passar pro Codex (resumo operacional)

- Cada bloco `codex exec --sandbox workspace-write "..."` acima é um prompt completo. **Copie tudo entre aspas e cole no terminal.**
- Codex roda autônomo, retorna `DONE` ou `FAIL: ...`. Se falhar, leia o erro, ajuste o prompt e rode de novo.
- O `--sandbox workspace-write` permite Codex editar arquivos do projeto, sem precisar de aprovação por comando.
- Se quiser revisar o diff antes de commitar: `git diff` mostra o que ele mudou.

## Para o que você pode usar Codex sem mim

- **Bugs visuais simples** (z-index, contraste, padding)
- **Adicionar componentes shadcn novos** ("instale shadcn dialog e use no botão X")
- **Refatorações mecânicas** (renomear variável, mover funções)
- **Conectar endpoint API → componente React** (com SPEC do backend já existente)
- **Rodar testes/build e reportar erros**
- **Pequenas features autônomas** (ex.: "adicione coluna 'Underlying' na trades-table")

## Quando voltar pra mim (Claude)

- **Decisões arquiteturais** (que stack, monorepo vs separado, Vercel vs Render)
- **Bugs sutis** (erro intermitente, race condition, query do Sheets dando dados errados)
- **Migrações** (adicionar nova fonte de dados, refatorar grandes módulos)
- **Deploy** (configurar Vercel + Render do zero, env vars, custom domain) — vale a pena pelo orquestrar de várias coisas

## Status final do dashboard hoje

- Local funciona: API :8000, Frontend :3000, AI chat com keys
- Falta deploy (Render Hobby grátis + Vercel grátis) → próxima sessão comigo
- Equity chart com Recharts → próxima sessão comigo (ou Codex se você quiser tentar)
