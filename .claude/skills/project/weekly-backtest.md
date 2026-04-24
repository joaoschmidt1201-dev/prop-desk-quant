---
name: weekly-backtest
description: Rerun dos backtests IC7 (NDX) e SS42 (SPX + RUT) apos refresh de parquets — regenera CSVs que alimentam o ic7_viewer e documenta mudancas em reports/. Use ao atualizar o data lake ou antes de revisao de estrategia.
---

# Weekly Backtest Refresh

## Contexto
Os viewers (`ic7_viewer.py`) consomem CSVs em `reports/{ic7,ss42}_backtest/`.
Esses CSVs sao commitados (alimentam o Streamlit Cloud). Toda vez que o
data lake em `G:/Meu Drive/Quant_Data_MD/` e atualizado, os backtests
precisam rodar de novo para incorporar as novas barras.

## Checklist

1. **Verificar data lake atualizado**
   - `ls -la "G:/Meu Drive/Quant_Data_MD/NDX_chain_*.parquet" | tail -5`
   - Ultima data deve ser Friday ou posterior a ultima linha do CSV atual

2. **IC7 (NDX) — estrategia principal**
   ```bash
   python scripts/ic7_backtest.py
   ```
   Gera em `reports/ic7_backtest/`:
   - `IC7_7DTE_NDX_YYYY-MM-DD_YYYY-MM-DD.csv` (trade log)
   - `IC7_7DTE_NDX_daily_*.csv` (daily MTM)
   - `performance_report.txt`, graficos PNG

3. **SS42 (SPX + RUT) — estrategia secundaria**
   ```bash
   python scripts/ss42_backtest.py
   python scripts/ss42_reinvest_sim.py
   ```
   Gera em `reports/ss42_backtest/` os CSVs de cada cenario de reinvestimento
   (24dit, 25pct, 50pct, 50pct_24dit, 75pct).

4. **Validar no viewer**
   - `streamlit run scripts/ic7_viewer.py`
   - Confirmar que equity curve extende ate a data nova
   - Checar se ha trades com PnL absurdo (>3x max_profit) = bug

5. **Commit separando engine de data**
   - Se codigo mudou: commit `feat(strategy): <mudanca>` com CSVs atualizados
   - Se so dados: commit `chore(data): refresh backtest CSVs YYYY-MM-DD`

## Gotchas

- `ic7_backtest.py` faz fallback Black-Scholes para dias sem dados — se
  muitos dias caem no fallback, verificar se extractor pulou datas.
- `ss42_reinvest_sim.py` ja nao soma PnL isoladamente — o viewer aplica
  close rules em runtime. Nao comparar numeros antigos cegamente.
- Se aparecer `ValueError: No parquets found for date X`, rodar
  `md_step2_mass_extractor.py` ou `ibkr_step2/3` para preencher gap.

## Referencias

- `scripts/ic7_backtest.py` — engine IC7
- `scripts/ss42_backtest.py` — engine SS42
- `scripts/ss42_reinvest_sim.py` — simulacao de cenarios
- `PROJECT_MAP.md` secao 2.4/2.6 — fluxos detalhados
