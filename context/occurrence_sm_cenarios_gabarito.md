# Occurrence Scanner — Catálogo COMPLETO de cenários (para gabarito do João)

Objetivo: enumerar **todos** os cenários possíveis de interação preço × MA × banda, para
o João rotular cada um como **Bounce / Break / False** (ou "não é evento"). O resultado
vira a spec fechada → cada cenário vira um teste sintético em `scripts/test_occurrence_sm.py`
→ a lógica é ajustada até passar em TODOS antes de tocar no Pine.

Como responder: pode escrever a classificação na frente de cada `[ ____ ]`, ou só me mandar
"S01=bounce, S04=false, ..." e as decisões dos FORKS. O que estiver ambíguo, me diga sua regra.

---

## 0. Legenda — regiões de um FECHAMENTO (close)

Tudo descrito do ponto de vista de **teste de SUPORTE** (preço vem de CIMA testando a MA como
suporte). O teste de **resistência** é o espelho exato (basta inverter cima/baixo) — ver §6.

```
   A   ────────────────────  ← acima da BORDA de cima (fora da banda, lado de origem)
        região u (dentro da banda, ACIMA da linha)
   L   ════════════════════  ← a LINHA da MA
        região d (dentro da banda, ABAIXO da linha)
   B   ────────────────────  ← abaixo da BORDA de baixo (fora da banda = "furou pra fora")
```

- **A** = close acima da borda de cima (fora da banda, lado de origem)
- **u** = close dentro da banda, **acima** da linha (metade do lado de origem)
- **d** = close dentro da banda, **abaixo** da linha (metade do lado oposto)
- **B** = close abaixo da borda de baixo (fora da banda, lado oposto = rompeu pra fora)
- `(t)` = a **mecha** (wick) tocou a banda mas o **close** ficou em A (só encostou)

Um cenário é uma **sequência de closes**, barra a barra. Ex.: `A A u u A` = 5 barras.
"Tocar/abrir evento" é pela mecha; "classificar" é pelos closes. Assumo que a mecha toca
sempre que um close está dentro/além da banda (natural).

**Duas definições que HOJE estão em disputa** (decididas nos FORKS da §2):
- O que conta como "romper": furar a **borda de fora** (chegar em B) ou só **cruzar a linha**
  (2 closes em d)?
- 1 close que cruza a linha e volta = **bounce** ou **false**?

---

## 1. ÁTOMOS — uma única aproximação (preço encosta uma vez e resolve)

### 1.1 Candidatos a BOUNCE (nunca cruza a linha pra baixo)

- **S01** `A A (t) A A` — só a **mecha** toca a banda; todo close fica acima da borda. `[ ____ ]`
- **S02** `A u A` — 1 close dentro da banda, ainda acima da linha; volta pra cima. `[ ____ ]`
- **S03** `A u u u u A` — **consolida** dentro da banda acima da linha (N barras) e volta pra cima. `[ ____ ]`
  *(= print1 na versão que nem chega a cruzar a linha)*

### 1.2 O MEIO AMBÍGUO (close cruza a LINHA mas fica DENTRO da banda — nunca fura B)

- **S04** `A u d u A` — **1** close abaixo da linha (ainda na banda) e volta. `[ ____ ]` ← **FORK R2**
- **S05** `A d d u A` — **2 closes consecutivos** abaixo da linha (na banda), depois volta pra cima. `[ ____ ]` ← **FORK R1**
- **S06** `A d d d d A` — cruza a linha e **anda abaixo dela DENTRO da banda** por muitas barras, sem furar B, e no fim volta. `[ ____ ]`
- **S07** `A u d u d u A` — fica **serrando em cima da linha** dentro da banda (whipsaw), sem furar nenhuma borda. `[ ____ ]` (quantos eventos? qual tipo?)

### 1.3 Candidatos a FALSE (fura a borda de fora B e volta)

- **S08** `A d B u A` — fura a borda inferior (1 close em B) e volta pra dentro/acima. `[ ____ ]`
- **S09** `A B A` — 1 close direto em B e já volta pra cima (sem passar por d). `[ ____ ]`
- **S10** `A (mecha fura B) u A` — a **mecha** fura a borda inferior mas o **close** nunca sai da banda. `[ ____ ]` (bounce ou false?)

### 1.4 Candidatos a BREAK (sustenta do outro lado)

- **S11** `A B B` — **2 closes consecutivos** em B. `[ ____ ]` (o caso mais limpo)
- **S12** `A B d` — 1 close em B, depois 1 close em d (voltou pra dentro da banda mas ainda abaixo da linha). 2 closes consecutivos além da linha, mas só 1 furou B. `[ ____ ]` ← **FORK R1**
- **S13** `A d B` — 1 close em d, depois 1 em B (2 consecutivos além da linha, o 2º furando B). `[ ____ ]`
- **S14** `A B B B B` — rompe e **continua** indo (tendência). `[ ____ ]` (trivial, mas confirma)

---

## 2. FORKS DE REGRA (cada um vira vários átomos de uma vez — decisão do João)

### FORK R1 — o que conta como "rompeu"?
- **(a) Cruzar a LINHA:** 2 closes consecutivos **além da linha** (regiões d ou B) já é BREAK.
  → S05 = break, S12 = break.
- **(b) Furar a BORDA de fora:** só é BREAK se o preço **furar B** (a lógica ORIGINAL do scanner);
  ficar em d dentro da banda **não** rompe.
  → S05 = bounce/false (nunca furou), S12 = false (só 1 furou B).

**Sua escolha R1: [ (a) linha / (b) borda ]**  — e nesse caso, quando é (b), 2 closes em d
sem furar B é **bounce** ou **false**? `[ ____ ]`

### FORK R2 — 1 close cruzando a linha e voltando (S04) é...?
- **(a) bounce** (a banda "conteve", cruzar a linha 1x dentro da tolerância não é fakeout).
- **(b) false** (cruzou a linha = tentativa de romper que falhou).

**Sua escolha R2: [ (a) bounce / (b) false ]**

*(Estes dois forks resolvem toda a §1.2 e boa parte da §1.3/1.4 de uma vez.)*

---

## 3. CADEIAS — eventos em sequência (a dimensão nova)

Aqui é a parte que você levantou: eventos que acontecem **logo em seguida** não podem ser
engolidos. Preciso do seu gabarito de **quantos** eventos e **de que tipo** cada cadeia gera.

- **C01 (seu exemplo)** `A B B | u u` — rompe pra BAIXO (2 closes em B = break de suporte),
  e **em seguida** faz 2 closes pra CIMA (volta acima da linha).
  → break pra baixo **+** o quê na volta? `[ break(baixo) + ____ ]`
  *(Você disse "contabilizado os dois bounces" — me confirme: o 2º evento é um **bounce** (o preço
  bounceou do lado de baixo e voltou), ou um **break de resistência** pra cima? Preciso desse rótulo.)*

- **C02 (V no exato nível)** `A d B | B u A` — fura pra baixo (break), reverte em V e volta acima da
  linha no mesmo impulso. `[ ____ + ____ ]`

- **C03 (bounce e re-bounce)** `A u A (t) A u A` — bounce, **sai** da banda, **re-entra** logo e
  bounce de novo. `[ 2 bounces? / 1 bounce? ]`

- **C04 (false → break)** `A B u A | A d B B` — primeiro um poke que volta (false), depois um
  rompimento genuíno. `[ false + break? ]`

- **C05 (rompe baixo e depois rompe alto)** `A B B ... d u A A` — rompe pra baixo (break de suporte)
  e **segue** subindo até romper pra CIMA através da borda de cima, sem uma re-entrada limpa.
  `[ break(baixo) + break(alto)? ]`

- **C06 (serra grande / whipsaw amplo)** `A B B | A A | B B | A A` — oscila cruzando os DOIS lados
  repetidamente. Quantos eventos e quais? `[ ____ ]`

**A pergunta-mãe das cadeias (RE-ARMAMENTO) está na §4** — as respostas de C01–C06 definem ela.

---

## 4. RE-ARMAMENTO — quando um NOVO evento pode começar?

Depois que um evento resolve, quando a máquina pode **abrir o próximo**? Esta é a manopla que
causou todo o whack-a-mole (print1 vs print2). Escolha uma política (ou descreva a sua):

- **(a) Sair-e-reentrar** (fresh-entry atual): novo evento só quando o preço **sai da banda** e
  **re-entra**. → mata break espúrio na consolidação (print1 ✓) mas **perde** break no meio do
  ride (print2 ✗ = under-count).
- **(b) Cruzar-a-linha**: um novo evento pode abrir quando o preço **cruza a linha** de novo,
  mesmo sem sair da banda. → pega o break do meio do ride (print2 ✓) mas **arrisca** re-disparo
  na consolidação (print1 — a menos que a direção discrimine).
- **(c) Híbrida (minha hipótese)**: **1 evento por ocupação da banda**, mas o evento **não fecha
  como bounce** enquanto o preço ainda ocupa a banda **e ainda pode romper a linha do lado OPOSTO
  ao lado de origem travado**. Assim: consolidação/rally no MESMO lado (print1) = 1 bounce; cruzar
  pro lado oposto e sustentar (print2) = vira break. A **direção relativa à linha** é o
  discriminador, não "saiu/entrou da banda".

**Sua escolha de re-armamento: [ (a) / (b) / (c) / outra ]** — e ela precisa ser consistente com
os rótulos que você deu em C01–C06.

---

## 5. CASOS DEGENERADOS / BORDA (dados reais têm todos)

- **E01 (gap por cima da banda)** barra pula a banda inteira: close anterior em A, próxima barra
  já fecha em B com a **mecha sem tocar** a banda (gap). `[ break? / ignora? ]`
- **E02 (barra gigante engloba a banda)** uma única barra com low < borda inferior e high > borda
  superior (mecha atravessa tudo). Conta toque de qual lado? O **close** decide? `[ ____ ]`
- **E03 (evento aberto no fim dos dados)** o preço entrou na banda e a série acaba antes de
  resolver. `[ descarta / conta bounce / ignora ]`
- **E04 (já dentro da banda na 1ª barra)** sem lado de origem definido (não há close anterior
  claro em A ou B). `[ ignora até sair / assume lado pelo close? ]`
- **E05 (encosta exatamente na borda)** low == borda superior (toque de tangência, sem penetrar).
  `[ conta toque? ]`
- **E06 (fecha exatamente NA linha)** close == MA (nem u nem d). `[ conta de que lado? ]`

---

## 6. SIMETRIA — teste de RESISTÊNCIA (espelho)

Tudo acima é **teste de suporte** (preço vem de cima). O teste de **resistência** (preço vem de
baixo, testando a MA como teto) é o **espelho exato**: trocar A↔B, u↔d, "acima"↔"abaixo". A regra
tem que ser simétrica — não precisa rotular tudo de novo, só confirmar: **"vale o espelho pra
todos?"** `[ sim / exceções: ____ ]`

---

## 7. TABELA-RESUMO (preencher)

| ID  | Cenário (closes)        | Classificação |
|-----|-------------------------|---------------|
| S01 | `A A (t) A A`           |               |
| S02 | `A u A`                 |               |
| S03 | `A u u u u A`           |               |
| S04 | `A u d u A`             |               |
| S05 | `A d d u A`             |               |
| S06 | `A d d d d A`           |               |
| S07 | `A u d u d u A`         |               |
| S08 | `A d B u A`             |               |
| S09 | `A B A`                 |               |
| S10 | `A (mecha fura B) u A`  |               |
| S11 | `A B B`                 |               |
| S12 | `A B d`                 |               |
| S13 | `A d B`                 |               |
| S14 | `A B B B B`             |               |
| C01 | `A B B \| u u`          |               |
| C02 | `A d B \| B u A`        |               |
| C03 | `A u A (t) A u A`       |               |
| C04 | `A B u A \| A d B B`    |               |
| C05 | `A B B ... d u A A`     |               |
| C06 | `A B B \| A A \| B B`   |               |
| E01 | gap por cima da banda   |               |
| E02 | barra gigante           |               |
| E03 | evento aberto no fim    |               |
| E04 | já dentro na 1ª barra   |               |
| E05 | encosta na borda        |               |
| E06 | fecha na linha          |               |

**Forks:** R1 = `[ (a) linha / (b) borda ]`  ·  R2 = `[ (a) bounce / (b) false ]`  ·
Re-armamento = `[ (a) / (b) / (c) ]`  ·  Simetria vale? `[ sim / não: ____ ]`
