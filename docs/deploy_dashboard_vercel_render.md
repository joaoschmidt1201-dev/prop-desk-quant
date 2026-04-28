# Deploy Dashboard: Vercel + Render/Railway

Objetivo: publicar o dashboard para Cristiano com frontend em Vercel e API em Render.
Railway fica preparado como plano B para a API.

## Arquitetura recomendada

- Frontend: Vercel, root directory `apps/web`
- Backend: Render Web Service, blueprint `render.yaml`
- API publica: `https://api.<dominio>`
- Dashboard: `https://dashboard.<dominio>`
- Dados: snapshot inicial versionado em `reports/`; scheduler da API atualiza via Google Drive.

## Custos esperados

Conferir valores oficiais antes de pagar, porque planos mudam.

- Vercel: Hobby pode servir para teste; Pro e o caminho profissional.
- Render: usar Web Service pago `Starter` para evitar sleep e manter scheduler vivo.
- Railway: alternativa ao Render; usar Hobby/Pro conforme billing e limites.
- Dominio: comprar ou usar um dominio existente. Normalmente fica fora de Vercel/Render/Railway.

## O que Joao precisa fornecer

- Conta Vercel conectada ao GitHub.
- Conta Render conectada ao GitHub ou, se Render falhar, conta Railway.
- Dominio desejado e acesso DNS.
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
2. Selecionar plano pago `Starter` para evitar sleep. O scheduler precisa do processo vivo.
3. Configurar secrets:

```text
CORS_ORIGINS=https://dashboard.<dominio>
ANTHROPIC_API_KEY=<opcional para Claude chat>
OPENAI_API_KEY=<opcional para OpenAI chat>
GDRIVE_CREDENTIALS_JSON=<json compacto>
GDRIVE_TOKEN_JSON=<json compacto>
```

4. Gerar os JSON compactos localmente:

```powershell
python scripts\print_gdrive_env_vars.py
```

5. Depois do deploy, testar:

```text
https://api.<dominio>/api/health
https://api.<dominio>/api/months
```

6. Em custom domain do Render, apontar `api.<dominio>` para o target indicado pelo Render.

## Railway API, plano B

O arquivo `railway.json` ja define build, start command, healthcheck e restart policy.

1. Criar um projeto no Railway conectado ao GitHub.
2. Selecionar este repo.
3. Usar a raiz do repo como deploy path.
4. Configurar as mesmas variaveis de ambiente usadas no Render.
5. Gerar dominio publico no Railway ou configurar `api.<dominio>`.
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
NEXT_PUBLIC_API_URL=https://api.<dominio>
DASHBOARD_BASIC_AUTH_USER=<usuario>
DASHBOARD_BASIC_AUTH_PASSWORD=<senha forte>
```

4. Deployar.
5. Em custom domain do Vercel, apontar `dashboard.<dominio>` para o target indicado pela Vercel.

## Smoke test

1. Abrir `https://dashboard.<dominio>`.
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
- A API deve ficar com `CORS_ORIGINS` restrito ao dominio do dashboard.
- Para protecao mais forte tambem da API, usar Cloudflare Access na frente de `dashboard.<dominio>` e `api.<dominio>`.
