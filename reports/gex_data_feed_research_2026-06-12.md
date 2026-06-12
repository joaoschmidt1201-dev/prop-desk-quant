# Pesquisa — Feed de Dados Confiável p/ o GEX (2026-06-12)

**Pergunta do João:** "qual a melhor forma de termos dados confiáveis, e se realmente vai
mudar algo se assinarmos uma plataforma de dados."

## TL;DR — Sim, muda, e muda exatamente o que falta

A causa-raiz dos números que **não batem com o Tanuki** (HVL/flip e Net Gamma/Delta) é
**dado, não motor**: o Yahoo grátis entrega **OI incompleto/inconsistente** na chain de
índice (`^SPX`). Comprovado na calibração de 3 dias (26/06: nós ~milhares de OI por strike
vs Tanuki 3,0M call / 4,6M put). As **walls** batem porque dependem da concentração relativa
(robusta); o **flip e as magnitudes** dependem da distribuição **completa** de gamma → exigem
OI completo.

**Um feed pago resolve isso** porque os provedores sérios puxam de **OPRA** (o feed
consolidado oficial de opções dos EUA) + **OCC** (open interest de liquidação). Isso é o OI
**completo de todos os strikes** do SPX/NDX/RUT — precisamente o que o Yahoo não dá.

> Conclusão direta: **assinar muda sim.** Sobe a ferramenta do nível "mapa de walls retail"
> para "GEX institucional grade Tanuki/MenthorQ" — incluindo o HVL/regime e as magnitudes,
> que é a veracidade #1 do CZ.

## Comparativo das opções (preços jun/2026)

| Provedor | Preço/mês | Fonte | OI completo índice? | Greeks | Notas |
|---|---|---|---|---|---|
| **Tradier** | **US$10** (ou grátis c/ conta brokerage funded) | ORATS | Sim (chain c/ `open_interest` por contrato; suporta `$SPX/SPXW`) | sim (ORATS) | **mais barato/live**; dado real-time p/ titular de conta |
| **ThetaData Value** | US$40 | OPRA direto | Sim ("daily OI across all strikes") | 1ª–3ª ordem | 4 anos de histórico, 3 request types |
| **ThetaData Standard** | **US$80** | OPRA direto | Sim | 1ª–3ª ordem | **8 anos histórico + tick** — melhor p/ quant/backtest |
| **ThetaData Pro** | US$160 | OPRA direto | Sim | sim | streaming de cada trade — overkill agora |
| **Polygon.io (Options)** | US$79 | OPRA | Sim | sim | bom, mas sem o histórico tick da Theta |
| **ORATS** | US$99 | OPRA | Sim | sim (98 indicadores) | **EOD** (não intraday) — não serve p/ live |
| **Intrinio** | ~US$1.000+ | OPRA | Sim | sim | caro demais p/ nosso caso |

## Recomendação (em ordem)

### 1ª opção — **Tradier (US$10/mês ou grátis c/ brokerage)** — começar por aqui
- **Por quê:** resolve o problema (OI completo de índice + chain live) pelo menor custo/atrito.
  Greeks vêm do ORATS, mas **a gente nem usa** — o motor já computa gamma/delta da nossa IV
  invertida. Só precisamos de **OI + preço + strikes completos**, e o Tradier entrega.
- **Risco:** precisa de conta Tradier (o desk provavelmente já tem corretora; checar se dá pra
  abrir/usar só pelo market data US$10). Cobertura de `$SPX/SPXW` confirmada na doc.

### 2ª opção (recomendada p/ o desk a médio prazo) — **ThetaData Standard (US$80/mês)**
- **Por quê:** OPRA direto, OI diário completo, **+ 8 anos de histórico tick**. O histórico é
  um **bônus enorme** que vai além do GEX:
  - destrava o **GEX Replay/History (DVR)** que adiamos (Fase 6) — reconstruir níveis do passado;
  - pode **alimentar os backtests do QC** com dado de opções real (hoje o desk depende de
    parquets que o João **não confia** — ver [[project_pipeline_status]] / desconfiança dos parquets);
  - índice nativo SPX/NDX/RUT sem proxy.
- **Slot já existe:** `THETADATA_API_KEY` já está reservado no `.env`.

### NÃO recomendado agora
- **ORATS** (EOD, não dá intraday "respirando"), **Polygon** (ok mas Theta é melhor p/ o
  histórico que o desk vai querer), **Intrinio** (caro demais).

## Esforço de integração (baixo — o motor já abstrai a fonte)

O motor de classificação (walls/HVL/DEX/states) **não muda**. Só trocamos a **camada de fetch**:
- Hoje: `apps/api/gex.py::_fetch_options_json` (Yahoo v7 + crumb).
- Mudança: um **adapter de provedor** (`_provider_chain(symbol, exp)`) que retorna o mesmo
  formato (strikes com OI/IV/bid/ask/vol). Yahoo vira fallback; Tradier/Theta vira primário
  via env (mesmo padrão do `GEX_NATIVE_INDEX` que já fizemos).
- **Bônus colateral:** com OI completo, some também a necessidade do **gate/rate-limit** que
  montamos pro Yahoo (provedor pago tem rate-limit generoso e dado estável) → mais simples e rápido.

## Próximo passo (decisão do João)
1. Confirmar se o desk já tem conta Tradier (ou abrir) → testo o adapter Tradier com US$10/mês,
   valido OI vs Tanuki num dia, e se bater, viramos a chave.
2. OU ir direto no ThetaData Standard (US$80) se você já quer o histórico p/ backtest/DVR também.

Eu recomendo **testar o Tradier primeiro** (custo mínimo p/ provar que o OI completo fecha a
paridade com o Tanuki) e, se o desk for usar GEX histórico/backtest a sério, subir pro ThetaData.

---
*Fontes: thetadata.net/pricing, docs.tradier.com, flashalpha.com (comparativo 2026), polygon.io, orats.com.*
