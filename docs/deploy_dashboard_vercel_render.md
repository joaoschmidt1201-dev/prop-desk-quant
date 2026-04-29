# Deploy Dashboard: Vercel + Render/Railway

Objetivo: publicar o dashboard para Cristiano com frontend em Vercel e API em Render,
sem dominio proprio e com custo inicial zero. Railway fica preparado como plano B barato.

## Arquitetura recomendada

- Frontend: Vercel, root directory `apps/web`
- Backend: Render Web Service, blueprint `render.yaml`
- API publica gratuita: `https://prop-desk-dashboard-api.onrender.com`
- Dashboard gratuito: `https://<nome-do-projeto>.vercel.app`
- Dados: snapshot inicial versionado em `reports/`; scheduler da API atualiza via Google Drive.

## Modo economico recomendado

- Vercel Hobby: gratuito para projeto pessoal/pequeno.
- Render Free Web Service: gratuito, mas dorme apos 15 minutos sem trafego.
- UptimeRobot Free: ping HTTPS em `/api/health` a cada 5 minutos para manter a API ativa.
- Dominio proprio: nao usar agora. Compartilhar a URL `.vercel.app` com Cristiano.
- Railway: usar apenas se o Render Free falhar; Hobby custa pouco, mas nao e necessario de inicio.

Tradeoff importante: o UptimeRobot normalmente evita o sleep porque gera trafego antes dos
15 minutos de idle do Render Free, mas isso nao e SLA. Se o Render reiniciar, redeployar,
esgotar horas free ou suspender o servico, ainda pode haver atraso no primeiro acesso.

## O que Joao precisa fornecer

- Conta Vercel conectada ao GitHub.
- Conta Render conectada ao GitHub ou, se Render falhar, conta Railway.
- Nao precisa de dominio agora.
- Usuario e senha para Basic Auth do Cristiano.
- Permissao para transformar `.credentials/gdrive_credentials.json` e `.credentials/gdrive_token.json` em secrets de producao.
- `ANTHROPIC_API_KEY` e/ou `OPENAI_API_KEY` se o chat do dashboard precisar funcionar em producao.

## Pre-flight local

1. Commitar as mudancas do dashboard/backtests/API.
2. Confirmar que o branch de deploy esta no GitHub.
3. Rodar:

```powershell
python -m py_compile apps/api/main.py scripts/export_control_panel.py scripts/print_gdrive_env_vars.py
cd apps/web
npm run build
npx tsc --noEmit --incremental false
```

## Render API

1. No Render, criar servico via Blueprint usando o `render.yaml` da raiz.
2. Se o Render perguntar o plano do workspace, escolher `Hobby` (`$0/mo + compute`).
3. No servico da API, usar instância/compute gratuito. O `render.yaml` ja esta com `plan: free`.
4. Configurar secrets:

```text
CORS_ORIGINS=https://<nome-do-projeto>.vercel.app
ANTHROPIC_API_KEY=<opcional para Claude chat>
OPENAI_API_KEY=<opcional para OpenAI chat>
GDRIVE_CREDENTIALS_JSON=<json compacto>
GDRIVE_TOKEN_JSON=<json compacto>
```

5. Gerar os JSON compactos localmente:

```powershell
python scripts\print_gdrive_env_vars.py
```

6. Depois do deploy, testar:

```text
https://prop-desk-dashboard-api.onrender.com/api/health
https://prop-desk-dashboard-api.onrender.com/api/months
```

7. Sem dominio proprio: usar a URL `.onrender.com` gerada pelo Render.

## UptimeRobot keep-alive

1. Criar conta gratuita em UptimeRobot.
2. Criar monitor:

```text
Monitor Type: HTTP(s)
Friendly Name: Prop Desk API
URL: https://prop-desk-dashboard-api.onrender.com/api/health
Monitoring Interval: 5 minutes
```

3. Quando o deploy da Vercel mudar o nome/URL da API, ajustar a URL do monitor.
4. Para a apresentacao, abrir o dashboard 5-10 minutos antes e clicar no refresh manual se o snapshot estiver antigo.

## Railway API, plano B

O arquivo `railway.json` ja define build, start command, healthcheck e restart policy.

1. Criar um projeto no Railway conectado ao GitHub.
2. Selecionar este repo.
3. Usar a raiz do repo como deploy path.
4. Configurar as mesmas variaveis de ambiente usadas no Render.
5. Gerar dominio publico no Railway se usar esse fallback.
6. Testar `/api/health` e `/api/months`.

## Vercel Frontend

1. Importar o repo no Vercel.
2. Configurar:

```text
Framework Preset: Next.js
Root Directory: apps/web
Build Command: npm run build
Install Command: npm ci
Output Directory: .next
```

3. Configurar env vars de producao:

```text
NEXT_PUBLIC_API_URL=https://prop-desk-dashboard-api.onrender.com
DASHBOARD_BASIC_AUTH_USER=<usuario>
DASHBOARD_BASIC_AUTH_PASSWORD=<senha forte>
DASHBOARD_BASIC_AUTH_EXTRA_USERS=cristiano:<senha forte>
```

`DASHBOARD_BASIC_AUTH_EXTRA_USERS` aceita mais de um acesso separado por virgula, por exemplo:
`cristiano:<senha>,joao-backup:<senha>`. O usuario/senha principal continua funcionando.

4. Deployar.
5. Sem dominio proprio: compartilhar a URL `.vercel.app` gerada pela Vercel.

## Smoke test

1. Abrir `https://<nome-do-projeto>.vercel.app`.
2. Validar Basic Auth.
3. Validar filtros: `APR26`, `MAR26`, depois `JS`.
4. Validar KPIs, tabela, analytics e chat.
5. Abrir `/backtests`.
6. Abrir `ss42-spx`, `ss42-rut`, `ic7-ndx`.
7. No backend, verificar logs:

```text
[scheduler] started
[snapshot refresh:scheduler] finished rc=0
```

## Rollback

- Vercel: redeploy do deployment anterior.
- Render/Railway: redeploy do commit anterior ou desligar `SCHEDULER_ENABLED`.
- Emergencia: remover custom domain temporariamente ou trocar senha Basic Auth.

## Seguranca

- Nao commitar `.env`, `.env.local`, `.credentials/` nem saida do `print_gdrive_env_vars.py`.
- Basic Auth protege o frontend.
- A API deve ficar com `CORS_ORIGINS` restrito a URL `.vercel.app` do dashboard.
- Para protecao mais forte no futuro, usar dominio proprio + Cloudflare Access.
