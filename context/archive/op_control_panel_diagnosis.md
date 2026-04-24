# OP Control Panel — Diagnóstico de Arquitetura
*Gerado em: 2026-04-23 | Baseado em inspeção direta do arquivo `Data/OP Control Panel.xlsx`*

---

## PARTE 1 — MAPEAMENTO DA ARQUITETURA ATUAL

### Inventário de Abas

| Aba | Tipo | Estado | Dimensões | Papel |
|-----|------|--------|-----------|-------|
| `Playbook` | Documentação | Visível | A1:Z947 | Regras e diretrizes da estratégia do desk |
| `APR26` | Visual — principal | Visível | A1:DK928 (col 115) | Painel de controle dos trades do CZ — Abril 2026 |
| `MAR26` | Visual — histórico | Visível | A1:DW937 (col 127) | Painel de controle dos trades do CZ — Março 2026 |
| `JS APR26` | Visual — João | Visível | A1:CQ927 (col 95) | Painel de controle dos trades do JS — Abril 2026 |
| `JS-FOR MAR26` | Visual — João/Forward | Visível | A1:CN928 (col 92) | Painel JS + Forward para Março 2026 |
| `FOR Trades` | Visual — Forward | Visível | A1:BX930 (col 76) | Forward trades (FOR01/02/03) Março 2026 |
| `FOR Guidelines` | Documentação | Visível | B2:B268 | Notas e diretrizes dos forward trades (inclui feedback de IA) |
| `db_robots` | Base de dados — PnL/Delta | Oculta | A1:Z52427 | Log diário de PnL e Delta de todos os trades ativos |
| `db_cria` | Base de dados — abertura | Oculta | A1:N1034 | Dados de abertura dos trades (scraper do OptionStrat) |

---

### Estrutura Interna de APR26 e MAR26 (template compartilhado)

Cada aba mensal de CZ tem duas zonas horizontais bem definidas:

#### Zona Esquerda — Painel de Resumo e Price Tracker (cols A–U)

```
Rows 7–13:  Dashboard de sumário por DTE
            B: Categoria (35/42 DTE | 28 DTE | 21 DTE | 7 DTE | TOTAL)
            D: # trades ativos
            E: Max Profit agregado (abertos)
            F: Open PnL atual (via SUMIFS → blocos individuais)
            G: Mx% = F/E (% do max profit realizado)
            H: RLZD = PnL realizado dos trades já fechados
            I: Delta agregado (direcional)

Rows 15–17: Headers do price tracker (SPX, NDX, RUT + VIX)
Rows 18–N:  Uma linha por dia de mercado desde T0 (abertura do mês)
            Col B: Data | C: DIT (Days in Trade)
            Col D: SPX Price | E: % daily | F: % since T0 | G: VIX
            Col H: NDX Price | I: % daily | J: % since T0 | K: VXN
            Col L: RUT Price | M: % daily | N: % since T0 | O: RVX
            Col Q: Technical Elements (ATH, W ATR, D ATR — manual)
```

**Como entra o preço**: via `GOOGLEFINANCE()` para preços diários de fechamento (98–126 chamadas por aba).

#### Zona Direita — Blocos Individuais por Trade (cols V–DK)

Cada trade ocupa um bloco de **~13 colunas**. Layout do bloco (exemplificado com Trade 1, cols V–AH):

```
Row 2:  Estado (vazio = ativo | "Closed")
Row 4:  Nome do trade (ex: "T45 RUT RJL42") — via ArrayFormula/db_cria
Row 5:  URL do OptionStrat (curto, ex: optionstrat.com/7Ubm...)
Row 6:  Preço abertura | Data open | Data exp | DTE restante
Row 7:  Strikes das pernas (LP | SP | SC | LC)
Row 8:  Max Profit | Max Loss
Row 9:  SD | (col +3) Mx Profit por leg
Row 10: SD% | Delta atual ← CHOOSEROWS(FILTER(db_robots!$E:$E, ...))
Row 11: DIT | DTE | PnL atual ← CHOOSEROWS(FILTER(db_robots!$D:$D, ...))
Row 12: Technical elements (MA50, BB, ATH — manual)
Row 13: SOLL Lw BE | % distância
Row 14: SOLL Up BE | % distância
Row 15: IST Lw BE | valor | % | distância relativa ao SOLL
Row 16: IST Up BE | valor | % | distância relativa ao SOLL
Row 17: Headers da série temporal (PnL | % Mx | SOLL $/d | Delta)
Row 18+: Uma linha por dia de mercado desde T0
         Col V: PnL ← CHOOSEROWS(FILTER(db_robots!$D, nome=V4, data=B_row))
         Col W: % Mx
         Col X: SOLL $/d = Max Profit / DTE restante (meta diária)
         Col Y: Delta ← CHOOSEROWS(FILTER(db_robots!$E, ...))
```

**Fórmula central de lookup** (reconstruída do DUMMYFUNCTION):
```
IFERROR(
  CHOOSEROWS(
    FILTER(db_robots!$D:$D,
      TRIM(SUBSTITUTE(db_robots!$C:$C, " - CLOSED", "")) = TRIM(SUBSTITUTE(V$4, " - CLOSED", "")),
      INT(db_robots!$A:$A) = $B{row}
    ), -1
  ), ""
)
```
Ou seja: filtra `db_robots` por nome do trade (coluna C) e data (coluna A), retorna PnL (col D) ou Delta (col E).

---

### Estrutura de `db_robots`

Colunas ativas:
```
A: Data (datetime)
B: Environment  → "Live" | "Live-apr" | "FOR Trades" | "FOR JS" | "Forward JS" | "URL Não Cadastrada"
C: Strategy     → nome do trade (ex: "T45 RUT RJL42")
D: PnL          → valor numérico (positivo = lucro)
E: Delta        → valor numérico
F: URL          → URL longa do OptionStrat (opcional)
N: aba          → label da aba destino (ex: "Live")
O: trades       → nome longo do trade
P: url          → URL ativa do trade
Q: url ativos   → URL para todos os ativos
R: url novos    → URL para novos trades
```

**Escala real de dados**:
- 27 datas únicas (2026-03-17 a 2026-04-22)
- ~972 registros com dados reais
- **51,454 linhas de placeholder** (vazias, pré-alocadas para o bot escrever sequencialmente)
- Environments por data (últimas semanas): `Live`, `Live-apr`, `FOR Trades`, `FOR JS`

---

### Estrutura de `db_cria`

Colunas:
```
A: Data da entrada
B: URL (longa do OptionStrat — scraper vai aqui)
C: DTE
D: SD (desvio padrão — implied move)
E: Open (data de abertura ou timestamp)
F: Underlying price no momento da abertura
G: SOLL Lw BE
H: SOLL Up BE
I: Net Credit
J: Max Loss
K: Contratos / Strikes (texto)
L: IST Lw BE
M: IST Up BE
N: Trade Name
```

- 27 registros com dados reais
- Preenchido pelo **Make Scenario 1** (scraper de OptionStrat quando detecta "New" + URL)
- Alimenta os campos de abertura nos blocos de cada trade nas abas visuais

---

### Como os dados entram, circulam e saem

```
ENTRADA DE UM NOVO TRADE:
  João digita "New" + URL na aba visual (ex: APR26)
    → Make Scenario 1 detecta → scraper OptionStrat
    → Escreve em db_cria (DTE, SD, strikes, BEs, Net Credit, Max Loss)
    → Fórmulas ArrayFormula nas abas visuais puxam db_cria → populam bloco

ATUALIZAÇÃO DIÁRIA (2x/dia):
  Make Scenario 2 → busca PnL e Delta de todos os trades ativos
    → Escreve em db_robots (Data, Env, Strategy, PnL, Delta)
    → CHOOSEROWS/FILTER nas abas visuais puxam o valor mais recente

CONSUMO DOS DADOS:
  Dashboard (cols A-U): SUMIFS/COUNTIFS sobre colunas dos blocos de trades
  Price tracker: GOOGLEFINANCE (automático, nativo do Google Sheets)
  Série temporal do trade: linha por linha, lookup em db_robots por (nome, data)
  Cristiano vê: APR26, MAR26 (visão direta dos trades dele)
  João vê: JS APR26, JS-FOR MAR26 (seus próprios trades)
```

---

## PARTE 2 — DIAGNÓSTICO TÉCNICO

### Pontos Fortes

1. **Separação de responsabilidades bem definida**: db_robots (log diário) e db_cria (dados de abertura) são layers de dados distintos e ocultos — ninguém edita acidentalmente.

2. **Template de bloco individual por trade é rico**: Cada trade tem seu próprio mini-dashboard com série temporal de PnL, Delta, SOLL $/d, breakevens, e elementos técnicos. Isso é nível profissional.

3. **Dashboard de sumário por DTE (rows 7-13) é excelente**: A visão por categoria (35/42, 28, 21, 7 DTE) com #, MxProfit, OpenPnL, %, RLZD e Delta é exatamente o que um portfolio manager precisa ver.

4. **Price tracker multi-índice integrado**: SPX + NDX + RUT com VIX/VXN/RVX, % diária e % desde T0, tudo em uma linha por dia. Estrutura limpa.

5. **CHOOSEROWS/FILTER é a escolha certa**: Muito mais elegante que VLOOKUP/INDEX-MATCH aninhados. O match por nome + data é robusto.

6. **Make Scenarios bem divididos por responsabilidade**: Scenario 1 (scraper de abertura) e Scenario 2 (updater de PnL/Delta) têm funções independentes e não se interferem.

7. **Nomenclatura consistente de trades**: T##, FOR##, codificação por tipo (BAT, IC, RJL, BW) facilita filtros.

---

### Gargalos e Fragilidades

#### CRÍTICO — Performance

- **51,454 linhas de placeholder em db_robots**: O Make escreve sequencialmente, então a planilha tem ~51k linhas vazias pré-alocadas. As fórmulas FILTER varrem `db_robots!$D:$D` (coluna inteira, 52k linhas) em cada célula de cada bloco de trade. Com 688 referências a db_robots em APR26 e 756 em MAR26, isso é potencialmente ~1.4 milhão de células varridas em cada recalculo.

- **GOOGLEFINANCE acumulado**: 98–163 chamadas por aba × 5 abas visuais = até 550+ chamadas de API por recalculo. Causa lentidão crescente à medida que mais linhas de preço são adicionadas.

#### ALTO — Fragilidade Estrutural

- **Expansão horizontal ilimitada**: Cada trade novo adiciona 13 colunas à direita. APR26 já vai até coluna DK (115). Depois de ~20 trades por mês, a planilha fica ilegível horizontalmente. Não há limite ou arquivamento automático.

- **Nomes de trades com espaços extras**: `db_robots` contém `"T07 Put Broken Wing                        "` (trailing spaces). As fórmulas usam `TRIM(SUBSTITUTE(...))` como mitigação, mas isso é uma falha na entrada de dados do Make que pode se repetir.

- **Inconsistência de environments**: `"Live"` e `"Live-apr"` coexistem como environments distintos. Se o Make mudar o label, lookups falham silenciosamente (retornam vazio, não erro).

- **`#DIV/0!` em campos de BE para trades vazios**: Trades fechados ou blocos sem dados geram `#DIV/0!` nas colunas de `% SOLL Lw BE` e `% SOLL Up BE`. Isso polui a visualização e pode confundir análises.

#### MÉDIO — Governança e Manutenção

- **db_cria sem estrutura de chave única**: Dois registros para o mesmo trade com datas diferentes existem (T35 RUT HALF-CALL BAT7 aparece em 23/03 e depois em outra data). Sem constraint de unicidade, duplicatas silenciosas são possíveis.

- **db_robots sem índice de lookup**: O FILTER varre a coluna C inteira para encontrar nome do trade. Um índice ou tabela de referência reduziria drasticamente o custo computacional.

- **Abas JS desatualizadas**: `JS APR26` última atualização 30/03, `JS-FOR MAR26` última atualização 23/03. Se o Make não as alimenta mais, estão desconectadas do fluxo real.

- **FOR Guidelines é texto livre em uma única coluna**: Valioso como documentação, mas invisível para automação e difícil de compartilhar com Cristiano.

- **"URL Não Cadastrada"**: 3 registros no db_robots com este label indicam trades que o Make não conseguiu mapear — falha silenciosa sem alerta.

---

### Manual vs Automático

| Campo | Manual | Automático |
|-------|--------|------------|
| URL do trade | João digita na aba | — |
| "New" para trigger do scraper | João digita | — |
| Strikes / Max Profit / BEs | — | Make Scenario 1 (db_cria) |
| PnL diário | — | Make Scenario 2 (db_robots) |
| Delta diário | — | Make Scenario 2 (db_robots) |
| Technical elements (ATH, MA50, BB) | João preenche | — |
| SOLL BEs | João preenche (ou fórmula?) | — |
| Preços SPX/NDX/RUT | — | GOOGLEFINANCE |
| Status "Closed" | João muda manualmente | — |
| Abertura de nova aba mensal | João copia template | — |

---

### O Que Está Escalando Mal

1. **Volume de db_robots**: Cada dia adiciona ~36 registros. Em 6 meses = ~5k registros reais + 51k placeholders = planilha de 56k linhas. As fórmulas FILTER ficam progressivamente mais lentas.

2. **Largura das abas visuais**: Cada mês novo com 10+ trades vai até coluna 115+. Sem padronização de quantas colunas reservar, quebra o layout.

3. **Duplicação entre abas**: MAR26, APR26, JS APR26, JS-FOR MAR26 e FOR Trades têm estrutura idêntica (mesmo template copiado). Uma mudança na lógica central requer atualização em 5 places.

4. **Sem histórico consolidado**: Cada mês é uma aba separada. Não existe uma visão agregada de performance Jan-Apr2026 nem uma curva de crescimento da conta.

---
