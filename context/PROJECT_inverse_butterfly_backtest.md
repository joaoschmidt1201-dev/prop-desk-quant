# PROJETO — Inverse Butterfly 1-2-1 (short call fly, SPX) · Backtest QC
*Charter vivo · criado 2026-06-17 · estratégia do vídeo alemão (Castle Trader)*

## A estratégia
**+2 CALL ATM / −1 CALL (ATM−W) / −1 CALL (ATM+W)** (1-2-1, net CRÉDITO). "Tenda pra baixo":
GANHA se o preço se mexe (qualquer lado), PERDE se fica parado. Long vega/gamma. Width W em múltiplos
de σ. Só SPX. **Ainda em validação — NÃO colocar no app** (decisão do João).

## Estado (2026-06-17)
- **Eixo DTE rodado** (1/4/7/15/30/45, w0.15σ): HOLD mid todos +$6k a +$14k / WR ~88-92%.
  TP50 melhora muito (+$25k a +$74k). `real vs impl` 0,73-0,85 (vol implícita > realizada → cara).
  **dte7 ERROU (runtime vazio) → RE-RODANDO agora.**
- **Eixo WIDTH rodando** (0.15/0.25/0.40σ em dte30). (w0.15 = dte30, redundante — usar o que vier.)
- Background task: `inverse_butterfly_sweep.py --axis=dte` (retry dte7) + `--axis=width`.
- Motor: `backtests/quantconnect/inverse_butterfly_v1.py` (tracking sintético). Gerador de PDF:
  `scripts/build_ibfly_pdf.py` (lê runtimeStatistics do sweep).

## ★ APRENDIZADOS DO PL5 — APLICAR NA ANÁLISE DO IB (ler antes de montar o PDF)
1. **Consistência de pricing.** No PL5 a 1ª versão misturou **hold no CONS** com **saídas no MID** →
   exagerou a vantagem da saída. AQUI: apresentar **hold mid vs saídas mid** (o motor grava os dois);
   nunca cruzar pricings diferentes na mesma tabela.
2. **NÃO apresentar o cons cru como "o resultado".** O cons = soma do spread cheio de cada perna
   (= 3 ordens a mercado) = PIOR caso irreal. O IB cons horário está absurdo (−$172k a −$331k vs mid
   +$10k) — quase certamente **inflado**. Apresentar **mid + sensibilidade ao fill (25/50%)**, não o cons.
3. **VERIFICAR, não assumir (lição dura do PL5).** No PL5 EU ASSUMI que o spread era artefato horário —
   e o minuto PROVOU que era REAL. Aqui as pernas são **near-ATM (líquidas)**, então o cons provavelmente
   É inflado — mas **rodar um spot-check em MINUTO** (igual `pl5_d60_minchk`) pra PROVAR antes de afirmar.
   Se minuto << horário → cons inflado, edge real perto do mid; se ≈ → o custo é real.
4. **Combo vs leg-by-leg.** Butterfly se trada como UM combo no limite; o net spread do combo é muito
   menor que a soma das pernas. Mid = net mid do combo (o preço que se mira).
5. **Semântica de "sair com D DTE".** É distância do VENCIMENTO, não da entrada → dias-segurado muda por
   DTE. Cuidado ao comparar saídas entre DTEs (no PL5 isso explicou o ranking).

## ✅ CONCLUÍDO (2026-06-17) — verificação + PDF
- **Eixo DTE (6) + width (3) rodados.** dte7 computado do CTRADE (HOLD mid ~flat −$500, TP50 +$21k).
- **VERIFICAÇÃO EM MINUTO (aprendizado #3 aplicado):** o cons horário (−$175k) é **ARTEFATO de quote
  stale** — spread minuto ~$150/trade consistente vs horário errático $95-5.580 (mediana ~7×, picos 37×).
  **Oposto do PL5** (lá a cauda −3Δ tinha spread REAL). `scripts/ibfly_minute_xcheck.py`.
- **PDF:** `reports/inverse_butterfly/InverseButterfly_report.pdf` (5 pág, EN).
- **VEREDITO honesto:** execução é LIMPA, mas o **hold não sobrevive ao slippage** (dte1/4 diário acumula
  em 1.200+ trades); TP50 é **bruto da saída** → líquido **marginal-a-positivo**, melhor no width largo;
  **implied > realized (0,73-0,85)** = edge fino. **Borderline; só viável como TP + wide wings.** Forward-
  test sugerido: 0,40σ + TP. **NÃO no app** (João valida).

## Próximos (se o João quiser aprofundar)
- Eixo de TP/exit refinado + OOS (treino/val) nas variantes wide; medir o fill REAL de combo.
