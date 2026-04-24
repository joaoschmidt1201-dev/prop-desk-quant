# Dashboard — Guia de Deploy (Link Fixo para CZ)

## Opção A — Streamlit Cloud (RECOMENDADO — gratuito, URL fixa permanente)

### Pré-requisitos
1. GitHub repo público (ou privado com conta Streamlit)
2. Conta em share.streamlit.io

### Passos

1. **Commitar os arquivos necessários** no GitHub:
   ```
   scripts/cz_dashboard_app.py
   scripts/export_control_panel.py
   reports/trades_snapshot_latest.json   ← atualizar diariamente
   reports/trade_history.parquet
   reports/monthly_summary.csv
   requirements.txt
   ```

2. **Criar app no Streamlit Cloud**:
   - Acesse: https://share.streamlit.io
   - Clique em "New app"
   - Repository: seu-usuario/Prop_Desk_Quant
   - Branch: main
   - Main file path: `scripts/cz_dashboard_app.py`

3. **Configurar Secret** (para análise de IA):
   - Em "Advanced settings" → "Secrets"
   - Adicionar:
     ```toml
     ANTHROPIC_API_KEY = "sk-ant-..."
     ```

4. **URL resultante**: `https://propdesk-options.streamlit.app` (você escolhe o nome)

5. **Compartilhar com CZ**: enviar o link. Ele pode salvar como bookmark no celular.

---

## Opção B — Rodar localmente com acesso remoto (ngrok)

Se preferir não colocar no GitHub:

```bash
# Terminal 1 — iniciar dashboard
streamlit run scripts/cz_dashboard_app.py

# Terminal 2 — expor via ngrok (URL pública temporária)
ngrok http 8501
```

Limitação: URL muda a cada restart do ngrok (versão gratuita).

---

## Manter dados atualizados no Streamlit Cloud

Duas opções:

**Opção 1 — GitHub Action automático** (recomendado):
Adicionar ao `.github/workflows/morning_briefing.yml` um passo extra que:
1. Roda `python scripts/export_control_panel.py` depois do briefing
2. Commita os arquivos de `reports/` de volta ao repo

```yaml
- name: Export portfolio snapshot
  run: python scripts/export_control_panel.py
  
- name: Commit reports
  run: |
    git config user.email "bot@propdesk.com"
    git config user.name "Quant Bot"
    git add reports/trades_snapshot_latest.json reports/trade_history.parquet reports/monthly_summary.csv
    git commit -m "chore: update portfolio snapshot $(date +%Y-%m-%d)" || echo "No changes"
    git push
```

**Opção 2 — Manual** (simples):
Baixar o .xlsx do Google Drive, rodar o exportador, commitar os reports.

---

## Workflow diário completo

```
07:30 BRT — Make Scenario 2 atualiza PnL/Delta (2a rodada)
08:00 BRT — GitHub Action roda morning briefing + export_control_panel.py
08:00 BRT — reports/ são commitados ao repo automaticamente
08:05 BRT — Streamlit Cloud detecta novo commit → atualiza o dashboard
08:15 BRT — CZ abre o link e vê o portfolio atualizado do dia
```

---

## URL para CZ (exemplo)

Após o deploy:
```
https://propdesk-options.streamlit.app
```

CZ pode:
- Ver KPIs, trades ativos, alertas
- Expandir cada trade para ver detalhes
- Clicar "Analisar com IA" para uma análise instantânea
- Baixar os dados em CSV/JSON para usar em qualquer IA
- Filtrar por ambiente (CZ Live, Forward, JS)
