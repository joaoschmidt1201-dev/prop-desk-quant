# OP Control Panel — Melhorias Pragmáticas
*Gerado em: 2026-04-23 | Preserva a arquitetura atual e os Make Scenarios existentes*

---

## PARTE 3 — MELHORIAS SEM QUEBRAR O SISTEMA

### Quick Wins (implementar em horas, sem tocar no Make)

#### QW-1: Limpar os 51,454 placeholders de db_robots
**Problema**: db_robots tem 51,454 linhas vazias pré-alocadas. As fórmulas FILTER varrem todas elas.  
**Solução**: Deletar as linhas vazias. O Make escreve na próxima linha disponível, não precisa de pré-alocação.
- Antes de deletar: verificar no Make como o módulo de escrita localiza a próxima linha (se usa `getValues()` + loop ou se usa uma célula de referência).
- Se o Make usa uma célula de referência (ex: conta total de linhas), apenas deletar as vazias resolve.
- Impacto estimado: redução de 98% do volume varrido pelas fórmulas FILTER → ganho de velocidade significativo.

#### QW-2: Padronizar Environment labels no Make
**Problema**: "Live" e "Live-apr" coexistem. Se o bot mudar o label, lookups falham silenciosamente.  
**Solução**: Padronizar para 4 labels fixos e imutáveis:
```
Live_CZ    → trades do Cristiano (atual: "Live" + "Live-apr")
Live_JS    → trades do João (atual: "Forward JS")  
Forward    → forward trades (atual: "FOR Trades")
Forward_JS → forward JS (atual: "FOR JS")
```
Atualizar as fórmulas das abas visuais para usar os novos labels.

#### QW-3: Adicionar IFERROR nos #DIV/0!
**Problema**: Trades fechados ou vazios geram #DIV/0! nas colunas de % BE.  
**Solução**: Envolver os cálculos de % em `IFERROR(..., "")` — as fórmulas já usam IFERROR em outros lugares, é só padronizar.

#### QW-4: TRIM nos nomes de estratégias no Make
**Problema**: "T07 Put Broken Wing                        " (trailing spaces) causa mismatch em lookups.  
**Solução**: Adicionar um módulo de `trim()` no Make Scenario 2 antes de escrever o nome em db_robots.C.

---

### Melhorias de UX

#### UX-1: Pinning das colunas de sumário (A-U)
O painel de resumo (rows 7-13) some quando João/CZ rola horizontalmente para ver os blocos de trades.  
**Solução**: `View → Freeze columns → Freeze up to column U` no Google Sheets.  
Nenhuma fórmula muda, só configuração de visualização.

#### UX-2: Separador visual entre trades ativos e fechados
Atualmente, trades fechados ficam na mesma linha horizontal que os abertos.  
**Solução**: Usar background color diferente (cinza claro) nas colunas de status "Closed". Já existe o campo na linha 2 — criar uma conditional formatting rule baseada nele.

#### UX-3: Indicador de alerta visual por DTE
Nos blocos individuais de trade, adicionar um semáforo (verde/amarelo/vermelho) baseado no DTE restante:
- Verde: DTE > 14
- Amarelo: DTE 7–14  
- Vermelho: DTE < 7
Usa conditional formatting no campo de DTE (linha 11 do bloco), sem nova fórmula.

#### UX-4: Aba de navegação rápida
Criar uma aba "INDEX" simples com links/resumo de cada aba mensal. Sem fórmulas complexas — só hiperlinks e os números-chave (RLZD do mês, # trades fechados, maior ganho, maior perda).

---

### Melhorias de Automação (Make)

#### AUTO-1: Validação de entrada no Scenario 1
Atualmente o scraper roda quando encontra "New" + URL. Adicionar uma check pós-scraping:
- Se o scrape retornar campos vazios (DTE nulo, Net Credit nulo), escrever "SCRAPE_FAIL" em uma célula designada
- Make envia notificação via email/WhatsApp para João

#### AUTO-2: Alertas automáticos de DTE crítico
O Make Scenario 2 já tem acesso a todos os trades ativos. Adicionar lógica:
- Se DTE ≤ 7 e trade ainda aberto → enviar alerta para João/CZ
- Se PnL ≥ 50% do Max Profit → enviar alerta "50% target atingido"
- Se PnL ≤ -100% do Max Profit → enviar alerta "Stop loss atingido"

#### AUTO-3: Auto-marcação de fechamento
Quando um trade tem DTE = 0 ou PnL cessa de atualizar por 2 dias consecutivos:
- Make tenta detectar → escreve "Closed_Auto" na célula de status
- João confirma ou reverte manualmente

#### AUTO-4: Webhook de confirmação de escrita
Após cada ciclo do Scenario 2, Make registra em uma célula de controle:
```
db_robots!A1 = "Último update: " & now() & " | Trades atualizados: " & count
```
Isso cria um heartbeat visível na planilha — João vê imediatamente se o bot parou de rodar.

---

### Melhorias de Governança dos Dados

#### GOV-1: Chave única em db_cria
Adicionar validação no Make: antes de escrever em db_cria, verificar se já existe um registro com a mesma URL. Se sim, atualizar em vez de duplicar.

#### GOV-2: Log de versão em db_robots
Adicionar coluna F em db_robots: `timestamp_write` (quando o Make escreveu aquela linha). Permite auditoria de latência e detecção de falhas silenciosas.

#### GOV-3: Aba `db_status` (nova, oculta)
Uma aba de controle operacional com 5 campos apenas:
```
A1: Último run Scenario 1 (scraper)
A2: Último run Scenario 2 (PnL updater)
A3: Total trades ativos monitorados
A4: Total registros em db_robots
A5: Alertas pendentes
```
O Make atualiza ao final de cada cenário. João vê se os bots estão vivos sem precisar checar o Make.

---

### Melhorias de Dashboard

#### DASH-1: Curva de capital mensal (nova aba `Equity`)
Uma aba simples com:
- Linha por mês (Jan26, Feb26, Mar26, Apr26...)
- Colunas: RLZD do mês | Acumulado | % do mês | # trades fechados | Win Rate | Avg Winner | Avg Loser
- Alimentada manualmente (copia os valores da aba de RLZD de cada mês)
- Gráfico de linha: curva de equity da conta

#### DASH-2: Heatmap de performance por estratégia
Na aba Equity ou Playbook: tabela de performance por tipo de estrutura (BAT42, IC7, RJL, BW IC...) com win rate, avg P&L, max winner, max loser. Alimentada pelo RLZD dos trades fechados.

#### DASH-3: Gauge de risco atual
No topo de APR26: uma barra visual com:
- Delta total da carteira (atual: calculado na row 13, col I)
- % do capital em risco (Max Loss agregado dos trades abertos / capital total)
- DTE médio ponderado dos trades abertos
Já temos os dados — é questão de agregar e formatar visualmente.

---

### Melhorias de Integração com IA

#### AI-1: Exportador CSV diário (Python script)
Script `scripts/export_control_panel.py`:
- Lê db_robots via openpyxl
- Lê db_cria via openpyxl
- Gera `reports/daily_snapshot_YYYYMMDD.csv` com todos os trades ativos, PnL atual, Delta, DTE restante, % do max profit
- Roda diariamente (pode ser integrado ao morning briefing existente)
- Produz o contexto que a IA precisa para análise sem precisar abrir o .xlsx

#### AI-2: Prompt de análise de qualidade de trade
Com o CSV do AI-1, o morning briefing pode incluir uma seção:
```
Para cada trade aberto:
- Nome | DTE | PnL% | Delta | Status (dentro/fora do tent)
- Alerta se DTE < 7 ou PnL < -50%
- Resumo de 1 linha por trade
```
Zero alucinação — tudo baseado em dados concretos do db_robots.

---

## PARTE 4 — PROPOSTA DE EVOLUÇÃO

### Versão Conservadora: Melhorar Bastante Sem Mudar a Arquitetura

**O que muda**: Limpeza, padronização, quick wins. Zero risco operacional.

**Sequência**:
1. **Semana 1**: QW-1 (deletar 51k placeholders) + QW-2 (padronizar env labels) + QW-4 (TRIM no Make)
2. **Semana 2**: GOV-3 (aba db_status) + AUTO-4 (heartbeat) + UX-1 (freeze cols) + UX-3 (semáforo DTE)
3. **Semana 3**: AUTO-2 (alertas 50% e DTE crítico no Make) + QW-3 (IFERROR nos #DIV/0!)
4. **Semana 4**: DASH-1 (aba Equity simplificada) + AI-1 (script exportador CSV)

**Resultado**: A mesma planilha, mais rápida, com alertas proativos, sem erros visuais, e com uma camada de exportação para IA.

---

### Versão Ambiciosa: Elevar o Nível Profissional da Operação

**O que muda**: Adiciona uma camada Python entre o Google Sheets e a IA. O Sheets continua como interface operacional (João e CZ continuam usando da mesma forma), mas os dados passam a circular por um pipeline Python.

```
Google Sheets (Make escreve) 
    → Python script exporta CSV diariamente (via Google Sheets API ou openpyxl)
        → DataFrame de trades históricos (parquet)
            → Morning briefing com análise de qualidade
            → Dashboard Streamlit/HTML estático para CZ
            → Backtests de ajuste de estrutura
```

**Nenhuma mudança no Sheets**: João e CZ continuam usando a planilha exatamente como hoje. A camada Python é aditiva.

---

### Ordem de Prioridade Recomendada

**Primeiro** (impacto imediato, baixo risco):
1. Deletar os 51k placeholders do db_robots (QW-1) — isso sozinho resolve o gargalo de performance
2. Padronizar env labels (QW-2) — previne falhas silenciosas futuras
3. Heartbeat de status no Make (AUTO-4) — João sabe se o bot está vivo sem checar o Make

**Segundo** (semana seguinte, adiciona valor real):
4. Alertas de 50% profit / DTE crítico no Make (AUTO-2) — substitui a atenção manual
5. Script exportador Python (AI-1) — desbloqueia análise de IA sem abrir o .xlsx

**Terceiro** (mês seguinte, nível profissional):
6. Aba Equity com curva de capital (DASH-1) — contexto histórico para decisões de Cristiano
7. Dashboard compartilhável para CZ (HTML estático gerado pelo Python)

---

### Como Compartilhar Melhor com Cristiano

**Hoje**: CZ acessa a planilha diretamente (view-only). Problema: muito dado técnico, muito scroll horizontal.

**Proposta**:
- Criar uma aba `CZ Dashboard` que é a única aba que CZ realmente precisa ver
- Layout: apenas os dados essenciais — Delta total, Open PnL, trades ativos por DTE, alertas
- Pode ser uma aba protegida (read-only para CZ, edit só para João)
- Alternativamente: Python gera um HTML estático diário com os trades dele, João envia via WhatsApp ou email

---

### Camada de Exportação para IA e Relatórios de Qualidade

**Estrutura proposta** (`scripts/export_control_panel.py`):

```python
# Lê db_robots e db_cria → gera 3 artefatos:

# 1. trades_snapshot.json — estado atual de todos os trades abertos
{
  "date": "2026-04-23",
  "trades": [
    {
      "name": "T45 RUT RJL42",
      "env": "Live_CZ",
      "dte": 29,
      "open_date": "2026-04-13",
      "exp_date": "2026-05-22",
      "underlying_open": 2645,
      "net_credit": 11850,
      "max_loss": 3150,
      "pnl_current": -16965,
      "pnl_pct_max": -143.2,
      "delta": -173,
      "lw_be": 2410.5,
      "up_be": 2789.5,
      "status": "active"
    }
  ]
}

# 2. trades_history.parquet — série temporal completa de PnL/Delta por trade
# 3. monthly_summary.csv — resumo mensal consolidado (RLZD, win rate, stats)
```

**Relatório de qualidade de trade** (gerado pelo morning briefing com os artefatos acima):
- Leaks identificados: "T45 está com Delta -173, fora do range esperado para RJL"
- Strengths: "Todos os trades 35/42DTE fechados no mês com 47% avg win rate"
- Consistência: "3 meses consecutivos com RLZD positivo"
- Alertas: "T45 está a -143% do Max Profit — fora da tent"

---

## O QUE DECIDI MANTER DA ARQUITETURA ATUAL

| Elemento | Decisão | Motivo |
|----------|---------|--------|
| Make Scenario 1 (scraper) | MANTER sem mudança | Funciona. Único ponto de entrada de dados de abertura. Qualquer mudança no workflow de criação de trade quebraria o hábito operacional. |
| Make Scenario 2 (PnL updater) | MANTER com adições pequenas (TRIM + heartbeat) | O fluxo de escrita em db_robots é correto. Adições são aditivas, não destrutivas. |
| db_robots como log append-only | MANTER | Append-only é a arquitetura certa para log de séries temporais. |
| db_cria como registro de abertura | MANTER | Serve o propósito bem. Só precisa de validação de duplicatas. |
| Estrutura de blocos por trade nas abas visuais | MANTER | Rico, funcional, e é o coração do painel. Mudá-lo seria reconstrução total. |
| CHOOSEROWS/FILTER como lookup | MANTER | É a escolha certa. O problema é a escala (51k linhas), não a técnica. |
| Template mensal (nova aba por mês) | MANTER | Isolamento temporal correto. O que mudar é criar uma consolidação sobre eles, não eliminar a separação. |
| Google Sheets como frontend | MANTER | João e CZ já usam. A automação Make já está integrada. Migrar para outra ferramenta seria meses de retrabalho sem ganho operacional imediato. |
