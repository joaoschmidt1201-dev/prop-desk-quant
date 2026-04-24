# PROJECT MAP

## 1. Resumo Executivo Do Sistema

Este projeto é a infraestrutura quantitativa de uma mesa proprietária de opções focada em índices macro e commodities, com ênfase operacional atual em NDX, SPX e RUT. O sistema não executa ordens; ele funciona como motor de dados, validação, backtest, visualização e briefing operacional para apoiar a tomada de decisão do desk.

A lógica central combina duas camadas:

- metodologia de venda de premium no estilo TastyTrade, com foco em probabilidade, IV e estruturas como Iron Condor e Short Strangle
- validação estrutural via análise técnica e leitura de gamma/GEX

Os principais resultados entregues pelo sistema são:

- briefing diário pré-mercado no Discord
- níveis semanais de GEX para leitura operacional e TradingView
- backtests históricos da estratégia principal IC7 e da estratégia secundária SS42
- dashboard Streamlit para auditoria visual trade a trade
- pipeline de dados históricos de opções em parquet

Restrições estruturais do desk:

- universo restrito a índices macro e ativos sistêmicos
- horizonte mínimo de 7 DTE
- zero uso de ações individuais como foco da operação principal
- nenhuma automação de execução via broker

## 2. Workflows Principais

### 2.1 Morning Briefing Diário

Objetivo: produzir o briefing pré-mercado automatizado da mesa.

Fluxo:

1. GitHub Actions executa `scripts/morning_briefing.py`
2. o script busca dados de mercado via `yfinance`
3. lê os últimos níveis de GEX nos arquivos `gex_history*.json`
4. consulta Finnhub para calendário macro e earnings
5. consulta Perplexity para pesquisa contextual e geração textual
6. publica o briefing no Discord via webhook

Saída operacional:

- briefing diário no canal do desk

### 2.2 Atualização Semanal De GEX

Objetivo: manter os níveis de gamma estruturais atualizados para briefing e TradingView.

Fluxo:

1. download manual dos CSVs do Barchart para `data/`
2. execução de `scripts/gex_csv_parser.py`
3. cálculo de gamma flip, paredes, confluências e zonas
4. atualização dos históricos `gex_history*.json`
5. regeneração de `tradingview/gex_weekly_levels.pine`
6. commit e push para disponibilizar os dados ao briefing e ao repositório

Saída operacional:

- históricos semanais de GEX
- indicador Pine atualizado

### 2.3 Atualização Do Data Lake De Options Chains

Objetivo: manter a base histórica de chains usada pelos backtests.

Fluxo principal:

1. atualização manual do cache de closes quando necessário
2. execução de `scripts/md_step2_mass_extractor.py` para o pipeline principal
3. execução de `scripts/md_step3_strangle_extractor.py` quando for necessário cobrir SS42
4. gravação de parquets em `G:/Meu Drive/Quant_Data_MD/`

Saída operacional:

- arquivos `{UNDERLYING}_chain_YYYY-MM-DD.parquet`

### 2.4 Re-Run Do Backtest IC7

Objetivo: recalcular a estratégia principal com dados atualizados.

Fluxo:

1. `scripts/ic7_backtest.py` lê os parquets de NDX
2. seleciona strikes, calcula IV ATM, expected move, P&L e daily MTM
3. grava CSVs e relatório em `reports/ic7_backtest/`
4. os CSVs são commitados para alimentar o viewer em produção

Saída operacional:

- trade log do IC7
- daily MTM do IC7
- relatório de performance

### 2.5 Visualização E Auditoria Operacional

Objetivo: permitir inspeção visual do comportamento das estratégias.

Fluxo:

1. `scripts/ic7_viewer.py` lê os CSVs em `reports/`
2. apresenta payoff, strikes, close rules, equity curve, drawdown e distribuição de P&L
3. o deploy no Streamlit Cloud é atualizado após push no repositório

Saída operacional:

- dashboard para leitura do João e do Cristiano

### 2.6 Re-Run Do Backtest SS42

Objetivo: validar a estratégia secundária de short strangle em SPX e RUT.

Fluxo:

1. `scripts/ss42_backtest.py` lê parquets de SPX ou RUT
2. encontra a expiração alvo próxima de 42 DTE
3. seleciona strikes próximos de 16-delta
4. calcula checkpoint em ~21 DTE e P&L na expiração
5. grava CSVs em `reports/ss42_backtest/`

Saída operacional:

- trade log da SS42
- daily MTM da SS42

### 2.7 Backfill IBKR Sob Demanda

Objetivo: preencher lacunas históricas não cobertas pelo pipeline principal.

Fluxo:

1. `scripts/ibkr_step1_contract_gen.py` gera o universo de contratos
2. `scripts/ibkr_step2_bulk_downloader.py` baixa os dados via IB Gateway/TWS
3. `scripts/ibkr_step3_daily_assembler.py` monta parquets diários compatíveis com o schema principal

Saída operacional:

- raw files de contratos individuais
- parquets diários compatíveis com o restante do sistema

## 3. Scripts Críticos

### `scripts/morning_briefing.py`

- função: briefing diário automatizado
- criticidade: alta
- impacto operacional: comunicação diária do desk

### `scripts/gex_csv_parser.py`

- função: parser de GEX semanal e gerador do Pine Script
- criticidade: alta
- impacto operacional: leitura estrutural de gamma no briefing e no TradingView

### `scripts/md_step2_mass_extractor.py`

- função: pipeline principal de extração histórica do Market Data App
- criticidade: alta
- impacto operacional: abastece o data lake central

### `scripts/md_step3_strangle_extractor.py`

- função: extractor especializado para SS42
- criticidade: alta
- impacto operacional: garante cobertura suficiente para seleção 16-delta

### `scripts/ic7_backtest.py`

- função: motor principal do backtest IC7
- criticidade: alta
- impacto operacional: valida a estratégia principal do desk

### `scripts/ic7_viewer.py`

- função: dashboard de auditoria visual
- criticidade: média-alta
- impacto operacional: interpretação e leitura de resultados pelo desk

### `scripts/ss42_backtest.py`

- função: motor do backtest SS42
- criticidade: alta
- impacto operacional: valida a estratégia secundária

### `scripts/ibkr_step1_contract_gen.py`

- função: geração do universo de contratos do backfill
- criticidade: média-alta
- impacto operacional: define a base do backfill IBKR

### `scripts/ibkr_step2_bulk_downloader.py`

- função: download bruto dos contratos via IBKR
- criticidade: alta
- impacto operacional: captura os dados de contingência

### `scripts/ibkr_step3_daily_assembler.py`

- função: montagem dos parquets diários compatíveis com os backtests
- criticidade: alta
- impacto operacional: integra o backfill ao restante do sistema

## 4. Arquivos De Alto Risco

### Arquivos de dados e configuração operacional

- `.env`
  - contém segredos locais e chaves de API
- `.github/workflows/morning_briefing.yml`
  - controla a automação diária do briefing
- `gex_history.json`, `gex_history_spx.json`, `gex_history_ndx.json`, `gex_history_spy.json`, `gex_history_qqq.json`
  - alimentam briefing e contexto operacional de GEX
- `tradingview/gex_weekly_levels.pine`
  - artefato direto para leitura visual no TradingView
- `data/ndx_closes_cache.csv`
  - insumo crítico do extractor principal

### Arquivos de saída que alimentam outros componentes

- `reports/ic7_backtest/*.csv`
  - alimentam o viewer e o processo de auditoria
- `reports/ss42_backtest/*.csv`
  - base dos estudos da estratégia secundária

### Scripts com risco operacional alto

- `scripts/md_step2_mass_extractor.py`
  - risco de contaminar o data lake
- `scripts/ic7_backtest.py`
  - risco de distorcer a estratégia principal
- `scripts/gex_csv_parser.py`
  - risco de alterar níveis estruturais usados pelo desk
- `scripts/morning_briefing.py`
  - risco de quebrar a rotina diária de inteligência
- `scripts/ibkr_step2_bulk_downloader.py`
  - risco de falha ou inconsistência no backfill
- `scripts/ibkr_step3_daily_assembler.py`
  - risco de incompatibilidade de schema com os backtests

## 5. Dependências Externas Principais

### Fontes de dados

- Market Data App API
  - fonte principal de chains históricas
- Interactive Brokers TWS / IB Gateway
  - fonte secundária para backfill
- Barchart
  - origem manual dos CSVs de GEX
- MenthorQ
  - validação complementar de gamma
- Yahoo Finance / `yfinance`
  - preços spot, VIX e outros dados auxiliares
- Finnhub
  - calendário econômico, earnings e EPS atual
- Perplexity API
  - pesquisa contextual e geração textual do briefing

### Infraestrutura externa

- Google Drive for Desktop em `G:/Meu Drive/Quant_Data_MD`
  - data lake principal dos parquets
- GitHub Actions
  - automação do morning briefing
- Streamlit Cloud
  - hospedagem do viewer
- Discord Webhook
  - entrega do briefing
- TradingView
  - consumo do Pine Script semanal de GEX

### Dependências locais relevantes

- ambiente Python local, historicamente assumido como `trade_env`
- bibliotecas centrais: `pandas`, `numpy`, `pyarrow`, `fastparquet`, `requests`, `yfinance`, `scipy`, `matplotlib`, `plotly`, `streamlit`, `python-dotenv`, `playwright`, `ib_insync`

## Observações Operacionais

- o sistema depende fortemente de ambiente Windows com Google Drive montado em `G:/`
- parte relevante da operação ainda depende de passos manuais e conhecimento tácito do operador
- o repositório contém código legado e scripts auxiliares que não representam o núcleo operacional atual
- o desk usa este projeto como motor de decisão e validação, não como executor automático de ordens
