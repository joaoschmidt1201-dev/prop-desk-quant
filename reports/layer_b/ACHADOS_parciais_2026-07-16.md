# Layer B (1x2 Square Root Hedge) — Achados Parciais

> **Status:** smoke validado. Baselines de 5 anos (SPX e RUT) rodando em corrente autônoma.
> Documento escrito **antes** do resultado de 5 anos, de propósito — a previsão da §4 está
> registrada para poder ser refutada, não racionalizada depois do fato.
>
> Data: 2026-07-16 · Motor: `backtests/quantconnect/layer_b_hedge_v1.py` · Projeto QC: **34195392**

> ## ⚠️ ATUALIZAÇÃO 2026-07-17 — LEIA A §7 ANTES DA §4
> A previsão registrada na §4 **foi REFUTADA pelo dado** (§7). O 1º run de 5 anos morreu de RAM aos
> 85%, mas a curva de equity foi salva e ela responde a pergunta central: **2022 não paga a conta —
> foi o pior ano da série.** A §4 fica no documento *exatamente como foi escrita*, sem edição, porque
> o valor dela é ter sido registrada antes. Um run limpo (filtro enxuto, mid, `k_gap`) está rodando
> para fechar o veredito no mid.

---

## 1. O que foi rodado

| Run | Span | Status | backtestId |
|---|---|---|---|
| `LB_SPX_smoke` | 2021-06-01 → 2021-09-01 | ✅ Completo, 13 rolls, **0 skips** | `b94304a7723e199cd153e8e9042da508` |
| `LB_SPX_5y` | 2021-06-01 → 2026-06-01 | ⏳ rodando (~6h) | `e2c45464f19b67d8822ee7a5f0ac235d` |
| `LB_RUT_5y` | 2021-06-01 → 2026-06-01 | ⏳ encadeado após o SPX | — |

Config: 1 unidade · vende 1× put d25 · compra 2× put d10 · alvo 42 DTE · roll sexta ·
`roll_ref=wow` · `roll_band=0` · fill **mid** (headline) · comissão $1.5/perna.

> B-MICRO tem **1 nó e não aceita fila** (*"no spare nodes available"*), por isso as runs são
> **encadeadas** por `~/qc_batman/_chain_layerb.py`, não enfileiradas.

---

## 2. Verificação do motor — passou

Antes de qualquer conclusão, o motor foi auditado linha a linha contra o log `CROLL`.

| Gate | Resultado |
|---|---|
| **Topologia** (K_long < K_short; senão não é backspread) | **0 violações / 13** ✅ |
| **Delta short** (alvo 0.25) | mediana **0.251** (min 0.245) ✅ |
| **Delta long** (alvo 0.10) | mediana **0.100** (min 0.098) ✅ |
| **Escada de DTE** (janela 40–45) | **13/13 = 100%** ✅ (SPXW é denso) |
| **Contabilidade** `cum_cash + mark = pnl_total` | bate exato (5.05 − 8.10 = −3.05) ✅ |
| **Invariante de entrada** (P&L = 0 ao abrir) | `cash_open +5.90`, `mark −5.90`, `pnl 0.00` ✅ |
| **Roll assimétrico** | rolls "down" (id 3, 12) **mantêm** o strike (4100→4100, 4300→4300) e o delta deriva p/ 0.35/0.15; o "up" seguinte re-strikeia p/ 0.25 ✅ |
| Skips | **0** ✅ |

**A regra assimétrica da fonte está implementada corretamente e verificada no dado.**

### 2.1 A divergência mid × blotter — explicada, não é bug

| Contabilidade | P&L (3 meses, 1 unidade) |
|---|---|
| **mid** (headline — regra do João) | **−$305** |
| **QC blotter** (`Net Profit`, ordem a mercado) | **−$2.377** |
| **cons** (pior caso: 3 pernas, entrada e saída) | **−$3.120** |

O QC preenche ordem a mercado **cruzando o spread**; por isso o blotter cai **entre** mid e cons,
e muito mais perto do cons. Não é erro de contabilidade — é o mesmo fenômeno visto de dois ângulos.
O `custo iliquidez mid-cons` medido pelo motor foi **$2.815** em 3 meses, coerente com o gap.

> **O QC, por conta própria, está dizendo que o custo real é ~7,8× o que o mid mostra.**
> Isso não contradiz a regra "sempre mid": mid segue sendo o headline. Mas o headline sozinho,
> nesta estrutura, esconde quase 8× do custo.

---

## 3. O achado central — o crédito não é renda

A fonte diz *"I.d.R. ergibt sich ein Credit"*. **Isso é verdade — e é irrelevante.**

- **13/13 entradas abriram a crédito** (+2.95 a +8.20 pts, mediana +6.00)
- **12/12 fechamentos custaram dinheiro** (−3.45 a −9.60 pts, mediana −5.83)
- **Net do roll: mediana +0.05 pts (+$5).** Uma moeda ao ar em torno de zero.
- Em crédito: **58% dos rolls no mid** · **25% cruzando o spread**

**Mecanismo:** na entrada, `cash_open = +5.90` e `mark = −5.90` → `P&L = 0`. O crédito é **caixa
recebido contra um passivo de valor idêntico**. Fechar a posição devolve esse passivo; abrir a nova
recebe outro. O roll é um lava-e-enxuga.

> **É aqui que nasce o erro da SPEC §4.6** ("crédito de entrada +$11.814 → o CZ é pago para
> carregar"). Esse crédito é recebido **uma vez** e é compensado por um passivo igual. Não é renda.
> A estrutura **não paga carrego** — ela é, no mid, **carrego-neutra**; e negativa assim que o
> spread entra.

**Consequência direta para a restrição #1 do João** (*"receber um crédito semanalmente"*):
o dado de 3 meses diz **não**. O crédito semanal não existe; o que existe é um crédito de entrada
que se repete e se cancela.

---

## 4. O padrão — e a previsão (registrada antes do resultado)

Decomposição dos 12 rolls do smoke por direção da semana:

| Semana | n | Soma | Média/semana |
|---|---|---|---|
| **UP** (re-strikeia) | 10 | +4.75 pts | **+0.47** |
| **DOWN** (horizontal) | 2 | −5.60 pts | **−2.80** |

**Ganha devagar na alta, perde 5,9× mais rápido na baixa.** As duas semanas de queda foram rasas
(−1.56% e −1.77% de DD) — ou seja, **a dor começa muito antes dos −12% que a fonte admite**.

Isso é exatamente o mecanismo que a própria fonte descreve:
> *"Ihr leidet aufgrund Gamma und einem Anstieg der Vola, die aber zu langsam ist."*

O short d25 ganha valor rápido na queda; os 2 long d10 estão OTM demais para responder; e a vol
sobe devagar demais para salvar. É **a cova**, e ela morde a partir de −0.5%, não de −12%.

Confirmado também pelas faixas de drawdown do smoke:

| Faixa de DD | Net | n | por roll |
|---|---|---|---|
| DD ~topo (> −0.5%) | **+7.00 pts** | 8 | +0.88 |
| DD −4% .. −0.5% | **−7.85 pts** | 4 | **−1.96** |

### 4.1 A CAUSA: a estrutura é COMPRADA em delta (+0.05)

A perda nas quedas rasas **não é gamma nem "a cova"** — é **delta puro**. Medido nos 13 rolls:

```
delta_pos = −1×(d_sh) + 2×(d_lg) = −(−0.25) + 2×(−0.10) = +0.25 − 0.20 = +0.05
```

| | valor |
|---|---|
| delta_pos mediano | **+0.0497** |
| min / max | +0.0408 / +0.0562 |

Teste da hipótese (SPX ~4300):

| Queda | Perda esperada só por delta | Observado |
|---|---|---|
| 1.5% (64 pts) | **−3.21 pts** | **−2.80 pts** (as 2 semanas down: dd −1.56% e −1.77%) |

Bate. A diferença é theta compensando parte.

> **O 1x2 @ d25/d10 nasce LONG ~5 delta.** Ele é uma posição levemente altista. Só vira hedge
> quando o mercado cai o bastante para o gamma das 2 compradas superar a vendida (o "flip de
> delta") — e é isso, mecanicamente, que a fonte chama de *"ab einem Drawdown von ca. 12%"*.
>
> Evidência do flip em ação: no roll id 3, o mercado caiu 1.56% e o delta_pos foi de **+0.0497 →
> +0.0411**. Anda na direção certa, mas ainda comprado.

**A consequência que importa para o desk:** o book do CZ **já é comprado em delta** (SPEC §3.2:
short put 2900 / long put 2820 → **+0.31**). O Layer B **também** é comprado (+0.05). Então, na
faixa de 0 a ~−12%, **o "hedge" ADICIONA delta comprado a um book que já está comprado** — ele
piora o risco exatamente na região onde o book já sangra. Ele só passa a proteger no tail.

### 4.2 ▶ CANDIDATO A CONSERTO (para a fase de sweep, se o baseline confirmar)

Se o problema é delta de nascença, ele tem conserto **sem tocar na convexidade da cauda**: escolher
os deltas para a estrutura nascer neutra ou levemente vendida.

| Variante | delta_pos no nascimento |
|---|---|
| **2× d10 / 1× d25** (a fonte) | **+0.05** ← altista |
| 2× d12.5 / 1× d25 | **0.00** ← neutra |
| 2× d15 / 1× d25 | **−0.05** ← levemente vendida |

Custo: subir o delta das compradas aproxima os strikes, **encarece as pernas long** e reduz a
alavancagem convexa no tail. É um trade-off real, não almoço grátis — mas é mensurável e ataca
o medo do João (grind lento) na origem.

### ▶ PREVISÃO (a ser confirmada ou refutada pelos 5 anos)

Com mistura real de semanas (~55% up / 45% down), o carrego esperado no **mid** é:

```
0.55 × (+0.47)  +  0.45 × (−2.80)  =  −1.00 pt/semana
                                   ≈  −52 pts/ano  ≈  −$5.200/ano por unidade
```

**Previsão:** o baseline de 5 anos do SPX deve mostrar **carrego negativo no mid**, dirigido pelas
semanas de queda, e a única chance de o resultado total ser positivo é o **bear de 2022** (DD ~−25%,
fundo o bastante para cruzar os −12% onde a fonte diz que a estrutura funciona) pagar mais do que
5 anos de sangria.

**A pergunta que os 5 anos respondem:** 2022 paga a conta de 5 anos, ou não?

> ⚠️ A extrapolação linear **quebra na cauda** de propósito: no crash a estrutura vira convexa e
> a média semanal deixa de valer. A previsão vale para o regime normal (0 a −12%), que é onde
> a estrutura passa 95% do tempo.

---

## 5. O que este trabalho NÃO responde — declarar, não esconder

1. **Margem sob portfolio margin** — decisão explícita do João de deixar fora do v1.
   `BuyingPowerModel.NULL` faz o QC parar de policiar margem. A restrição #3 segue **sem resposta**.
   Destrava só com o CZ montando 1 unidade no IBKR e informando o número real.
2. **Degradação do basis RUT×SPX no crash** — rodar os dois mede condição normal. O research note
   avisa que beta é menos confiável **exatamente** quando as correlações convergem p/ 1.
3. **Risco de execução do roll** — o backtest assume que a sexta sempre acontece. A fonte diz
   *"Ihr habt Null Risk, solange Ihr Euren Hedge pflegt"*: **isso é falso**. A cova é risco real e
   o roll é dependência operacional. A 9 unidades, a cova é ~$105k se o roll falhar uma vez.
4. **n=12 é ruído.** Tudo nas §3 e §4 vem de 3 meses de bull. Nada aqui é conclusão — é hipótese
   com mecanismo. Os 5 anos decidem.

---

## 6. Ferramentas criadas nesta sessão

| Arquivo | Função |
|---|---|
| `backtests/quantconnect/layer_b_hedge_v1.py` | motor (contabilidade de fluxo de caixa; `CROLL\|` como canal) |
| `scripts/layer_b_analyze.py` | analisa o `CROLL` → as 3 restrições + diagnósticos; **grita se o log truncar** |
| `~/qc_batman/_run.py` | lança backtest via REST (o `lean cloud backtest` do CLI é gated) |
| `~/qc_batman/_pull.py` | puxa canal de log genérico (o `_logpull.py` tinha projeto e `CTRADE` hardcoded) |
| `~/qc_batman/_chain_layerb.py` | corrente autônoma SPX → RUT (B-MICRO não aceita fila) |

**Gotcha novo descoberto:** `/projects/update` devolve **HTTP 500** com `parameters` como dict
(2026-07-16). O caminho que funciona: editar `<proj>/config.json` local → `_lean.py cloud push`.
Os params ficam **congelados no `parameterSet`** do backtest na criação — por isso dá pra empurrar
o config do RUT sem contaminar o SPX que já está rodando.

---

## 7. A previsão da §4 foi REFUTADA — 2022 não paga a conta (2026-07-17)

### 7.1 Como este dado apareceu

O `LB_SPX_5y` **morreu de RAM aos 85%** (out/2025). O filtro `.expiration(0, 52)` assina todo
vencimento de 0 a 52 DTE; como o SPX passou a ter vencimento **diário** a partir de 2023, a coleção
de contratos cresce monotonicamente até estourar os **7,8GB** do nó B-MICRO.

> **Assinatura de OOM no QC** (vale para os próximos backtests): `status: In Progress`, **sem erro e
> sem stacktrace**, nó `busy=True`, e progresso **+ runtime stats congelados até o centavo** entre
> duas leituras. Não é lentidão — é morte silenciosa.

O log do QC **só materializa quando o run completa** → o CROLL dos 85% se perdeu. Mas os **charts
saem durante a execução** (`/backtests/chart/read`), e foi de lá que veio a curva de equity abaixo.

### 7.2 O resultado

Curva de equity, 2021-06 → 2025-10 (88 pontos, base $1M, 1 unidade), **fecho por ano civil**:

| Ano | Equity | Resultado do ano |
|---|---|---|
| 2021 (7 meses) | 982.255 | −17.745 |
| **2022** (bear, DD ~−25%) | 906.818 | **−75.437** ← o pior ano |
| 2023 | 846.718 | −60.100 |
| 2024 | 795.093 | −51.625 |
| 2025 (até out) | 732.087 | −63.006 |

**Total: −27,2%.** Os dois piores períodos da série inteira são **ago/2022** (−32.777) e **abr/2025**
(−32.638) — os dois crashes. Uma ladeira monótona, **sem convexidade em lugar nenhum**.

### 7.3 O que isso mata

A §4 registrou, antes do resultado: *"a única chance de o resultado total ser positivo é o bear de
2022 pagar mais do que 5 anos de sangria"*. **2022 foi o pior ano de todos.**

E mata também a alegação central da fonte alemã. O SPX fez ~−25% de drawdown em 2022 — o dobro dos
**−12%** onde o autor garante *"seine volle Wirkung entfalten"*. A estrutura atravessou com folga o
limiar onde ela deveria funcionar, **e perdeu mais do que em qualquer ano de bull**.

### 7.4 O que este número ainda NÃO é

- É **blotter** (ordem a mercado cruzando o spread), **não mid** — que é a regra de headline do desk.
  No mid tudo encolhe ~7,8× (§2.1), mas a **ordem dos anos não muda**: a fricção é ~52 rolls/ano em
  todo ano, então 2022 continua o pior. O run limpo fecha isso no mid.
- **Falta decompor:** dá ~−$1.038/roll aqui contra −$198/roll no smoke — **6× pior**. Pode ser real
  (vol e spread de 2022+, índice 4300→6000) ou **artefato**: no roll horizontal o strike fica parado
  enquanto o spot cai, deriva para ITM, e se sair da janela `strike_filter` o `_pick_by_strike` pega
  "o mais próximo" e **re-strikeia em silêncio, justo onde a regra proíbe**. → instrumentado como
  `k_gap` (§7.6).

### 7.5 A pergunta certa sobre o roll (reframe do João, 2026-07-17)

> *"A ideia dessa estratégia é justamente não deixar a cova se formar."*

Isso é **mecanicamente verdadeiro**: a 42 DTE a cova é rasa (o valor no tempo a suaviza); ela só
aprofunda perto do vencimento. Rolando toda sexta e nunca chegando perto do expiry, a cova **nunca
se materializa** — é exatamente por isso que a fonte exige 40-45 DTE.

Só que os dados dizem que a sangria existe assim mesmo, e a §4.1 mostrou que a perda das semanas de
queda bate com **delta puro** (−3,21 pts previstos por delta vs −2,80 observados). Logo a hipótese a
testar não é "a estratégia dá lucro?", e sim:

> **O roll cumpre o que promete, a cova nunca se forma, e o dinheiro vai embora por outro cano** —
> delta comprado de nascença (+0,05) mais pedágio de spread 52×/ano.

Se confirmar, o veredito para o CZ é bem mais forte que "não deu certo": **a estratégia é
bem-sucedida no seu objetivo declarado e perde dinheiro assim mesmo.** O motor já loga o que decide
isso: `mark_max_wk` e `dd_wk` (extremos **intra-semana** da posição desmontada) medem se a cova
chegou perto, em vez de a gente argumentar.

### 7.6 O que mudou no motor (e o que foi provado, não assumido)

| Mudança | Efeito | Como foi verificada |
|---|---|---|
| `puts_only=1` + `exp_lo=25` | filtro enxuto; run **termina** e roda ~20× mais rápido (smoke 3m47s; 5y ~1h) | **A/B**: `_ab_check.py` rodou o mesmo span do smoke validado → **13/13 rolls idênticos em 18 colunas de medição** |
| `base_cash=100000` (pedido do João) | só a leitura de equity/Return% | mesmo A/B: neutro (o P&L do CROLL é analítico, em pts, no mid) |
| `k_gap` (novo) | mede o re-strike **silencioso** no roll horizontal | `_gate_roll_rule` no analyzer grita se algum roll `down` tem `k_gap>0`; runs antigos não têm a coluna e o gate **diz isso** em vez de fingir que passou |
| detector de trava na corrente v2 | progresso congelado 60min → aborta | nasceu deste OOM |

> `strike_filter` **não** foi mexido de propósito: cortar a janela positiva quebraria justamente 2022,
> que é onde o strike deriva para ITM.

### 7.7 Para onde ir (e o que NÃO fazer)

**Não** varrer 18 variantes de roll atrás de um resultado positivo: com espaço de busca desse tamanho
**a gente acha**, e é curve-fit (a cicatriz que obrigou o edge mining a virar k-fold + bootstrap +
permutation). O eixo honesto é o que a §4.2 já registrou **antes** de qualquer resultado, porque ataca
a causa medida:

| Variante | delta no nascimento |
|---|---|
| 2× d10 / 1× d25 (a fonte) | **+0,05** ← altista |
| 2× d12,5 / 1× d25 | **0,00** ← neutra |
| 2× d15 / 1× d25 | **−0,05** ← levemente vendida |

Custo real: subir o delta das compradas encarece as pernas long e reduz a alavancagem convexa no tail.
É trade-off mensurável, não almoço grátis.

---

## 8. Sweep de delta — o "conserto" da §4.2 tem efeito CONTRÁRIO (2026-07-18)

A §4.2 propôs que a perda vinha do delta comprado de nascença (+0,05) e que nascer neutro/vendido
consertaria. **Testado nos 5 anos do SPX (short fixo Δ25, long variando), a hipótese foi refutada:**

| Variante | Delta de nascença | P&L 5 anos (mid) |
|---|---|---|
| Δ10 / Δ25 (a fonte) | **+0,05** (long) | **−$65.020** |
| Δ12,5 / Δ25 | 0,00 (neutro) | −$82.760 |
| Δ15 / Δ25 | **−0,05** (short) | **−$96.475** |

**Nascer mais neutro/vendido PIORA, monotonicamente.** O mecanismo é simples em retrospecto: o SPX
subiu ~40% no período (bull secular), então o pequeno delta **comprado** de nascença do Δ10 era um
**vento a favor**, não a causa da sangria. Removê-lo (subindo o delta das pernas compradas) só tirou
o tailwind.

**Conclusão para o desk:** a perda do Layer B é **estrutural** — fricção do roll (52×/ano), a cova, e
o decay do short put nas semanas de queda — e **não** se conserta mexendo no delta de nascença. O
"conserto óbvio" que a intuição sugere (achatar o delta) piora o resultado. Isso *fortalece* o veredito
de que a estrutura, como está, não é o hedge: nem o parâmetro mais natural a otimizar a salva.

> Nota metodológica: NÃO varremos as 18 combinações de roll atrás de um resultado positivo (seria
> curve-fit). Testamos **um** eixo, escolhido por mecanismo (o delta de nascença), e ele refutou a
> própria hipótese. Um resultado que refuta é mais confiável que um que confirma após busca ampla.

*(Braço RUT das variantes rodando; será somado quando fechar. k_gap nos runs d125/d15 = grid-snapping
benigno de ~5–25 pts, comum a todas as variantes, imaterial ao headline.)*
