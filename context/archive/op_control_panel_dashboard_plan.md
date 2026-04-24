# OP Control Panel — Dashboard Plan
*Gerado em: 2026-04-23*

---

## Aba `CZ Dashboard` (dentro do Google Sheets)

Proposta de uma aba nova, limpa, pensada para Cristiano ver rapidamente sem rolar.

### Layout (colunas A–M, rows 1–30)

```
Row 1:  [TÍTULO] OPTIONS DESK — APR 2026         Last Update: {db_robots última data}
Row 2:  [vazio]

Row 3:  [CARTEIRA ATUAL]
Row 4:  Open PnL Total | Max Loss Exposto | Delta Total | # Trades Ativos

Row 6:  [RESULTADO DO MÊS]
Row 7:  RLZD Abr26 | RLZD Mar26 | Acumulado 2026

Row 9:  [TRADES ATIVOS] — tabela compacta
Row 10: Nome | DTE | Estrutura | Underlying | PnL Atual | % MaxP | Delta | Status
Row 11: T45 RUT RJL42 | 29 | RJL42 | RUT 2645 | -$16,965 | -143% | -173 | ⚠️ OUT
...

Row 20: [TRADES FECHADOS NO MÊS]
Row 21: Nome | Abertura | Fechamento | DIT | Max Profit | RLZD | % Realizado

Row 28: [PRÓXIMOS VENCIMENTOS]
Row 29: Ordenado por DTE crescente (todos com DTE < 14)
```

### Fórmulas necessárias

Tudo já existe nas abas APR26/MAR26 — o CZ Dashboard seria só uma view consolidada via referências (`=APR26!F13`, `=APR26!H13`, etc.). Zero fórmulas novas, zero Make novo.

### Como compartilhar com CZ

Opção A (simples): Proteger a aba CZ Dashboard com permissão de só-leitura para CZ.
Opção B (melhor): Python script gera um PDF ou HTML de 1 página diariamente e João envia por WhatsApp.

---

## Script Python de Dashboard HTML (gerado externamente)

**Arquivo**: `scripts/generate_cz_dashboard.py`

**Input**: `reports/daily_snapshot_YYYYMMDD.json` (gerado pelo exportador)

**Output**: `reports/cz_dashboard_YYYYMMDD.html` — 1 página, mobile-friendly

### Seções do HTML

1. **Header**: Data + "Atualizado às 10:15 BRT"
2. **KPIs**: 4 tiles — Open PnL | RLZD do mês | Delta total | # trades ativos
3. **Tabela de trades ativos**: ordenada por DTE, com semáforo de status
4. **Gráfico de equity do mês**: linha simples com PnL acumulado dia a dia
5. **Footer**: "Dados: OptionStrat via Make | Análise: Desk Quant"

### Por que HTML e não PDF
- Funciona em qualquer device (WhatsApp, email, browser)
- Gráfico é interativo (hover nos pontos)
- Zero dependência de instalação para CZ
- Pode ser hospedado em GitHub Pages ou Google Drive (read-only link)

---

## Integração com Morning Briefing Existente

O `dry_run_briefing.py` já existe. Adicionar uma seção:

```python
# No briefing de 11:00 UTC (8h BRT)
def get_portfolio_status():
    # Lê daily_snapshot mais recente
    # Retorna string formatada com trades ativos, alertas, KPIs
    pass

briefing_sections = [
    get_gex_section(),
    get_market_section(),
    get_portfolio_status(),  # ← NOVO
    ...
]
```

Isso coloca o status da carteira do CZ no contexto do briefing diário — antes de qualquer análise de mercado, João já sabe se tem algum trade fora da tent ou com DTE crítico.
