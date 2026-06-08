# Auditoria de Integridade — Jade Lizard / Reverse Jade Lizard

Filtro: strikes ausentes **OU** credit > 1.8x mediana da celula **OU** retained_dist > 400 pts (normal ~31, p95 79).

| Célula | Trades | Removidos | Net ANTES | Net DEPOIS | Δ (lucro fake removido) |
|---|---|---|---|---|---|
| jl_w20_n10_0dte | 975 | 4 | $4,631 | $2,351 | $2,280 |
| jl_w20_n5_0dte | 975 | 5 | $17,161 | $12,066 | $5,095 |
| jl_w20_n5_1dte | 954 | 2 | $40,362 | $39,857 | $505 |
| jl_w30_n10_0dte | 975 | 4 | $12,056 | $10,098 | $1,958 |
| jl_w30_n5_0dte | 975 | 4 | $34,296 | $29,446 | $4,850 |
| rjl_w20_n10_0dte | 975 | 4 | $-32,280 | $-33,909 | $1,629 |
| rjl_w20_n5_0dte | 975 | 5 | $-24,627 | $-25,726 | $1,099 |
| rjl_w20_n5_1dte | 960 | 3 | $-20,195 | $-20,297 | $102 |
| rjl_w30_n10_0dte | 975 | 4 | $-44,899 | $-45,406 | $507 |
| rjl_w30_n5_0dte | 975 | 5 | $-17,170 | $-18,123 | $953 |

## Sessões removidas (detalhe)

### jl_w20_n10_0dte
- `2022-12-16` — pnl $1,280, credit $1,280 — sem-strikes
- `2024-06-28` — pnl $-915, credit $1,085 — sem-strikes
- `2025-11-28` — pnl $1,820, credit $2,820 — sem-strikes, credit-outlier(2820>1.8x1020), retained_dist(1054)
- `2026-05-13` — pnl $95, credit $1,095 — sem-strikes

### jl_w20_n5_0dte
- `2022-12-16` — pnl $760, credit $760 — sem-strikes
- `2023-12-15` — pnl $1,042, credit $1,045 — sem-strikes, credit-outlier(1045>1.8x525), retained_dist(970)
- `2024-06-28` — pnl $-62, credit $523 — sem-strikes
- `2025-11-28` — pnl $3,340, credit $3,840 — sem-strikes, credit-outlier(3840>1.8x525), retained_dist(1054)
- `2026-05-13` — pnl $15, credit $515 — sem-strikes

### jl_w20_n5_1dte
- `2024-06-27` — pnl $505, credit $505 — sem-strikes
- `2026-05-12` — pnl $0, credit $500 — sem-strikes

### jl_w30_n10_0dte
- `2022-12-16` — pnl $1,060, credit $1,060 — sem-strikes
- `2024-06-28` — pnl $-967, credit $1,118 — sem-strikes
- `2025-11-28` — pnl $1,820, credit $2,820 — sem-strikes, credit-outlier(2820>1.8x1040), retained_dist(1044)
- `2026-05-13` — pnl $45, credit $1,045 — sem-strikes

### jl_w30_n5_0dte
- `2023-12-15` — pnl $1,042, credit $1,045 — sem-strikes, credit-outlier(1045>1.8x527), retained_dist(960)
- `2024-06-28` — pnl $423, credit $508 — sem-strikes
- `2025-11-28` — pnl $3,340, credit $3,840 — sem-strikes, credit-outlier(3840>1.8x527), retained_dist(1044)
- `2026-05-13` — pnl $45, credit $545 — sem-strikes

### rjl_w20_n10_0dte
- `2023-12-15` — pnl $1,042, credit $1,045 — sem-strikes
- `2024-06-28` — pnl $22, credit $1,022 — sem-strikes
- `2025-11-28` — pnl $1,475, credit $1,475 — sem-strikes, retained_dist(586)
- `2026-05-13` — pnl $-910, credit $1,090 — sem-strikes

### rjl_w20_n5_0dte
- `2023-12-15` — pnl $467, credit $470 — sem-strikes
- `2024-06-28` — pnl $30, credit $530 — sem-strikes
- `2024-08-05` — pnl $610, credit $610 — sem-strikes
- `2025-11-28` — pnl $1,475, credit $1,475 — sem-strikes, credit-outlier(1475>1.8x538), retained_dist(586)
- `2026-05-13` — pnl $-1,483, credit $505 — sem-strikes

### rjl_w20_n5_1dte
- `2022-07-29` — pnl $505, credit $1,005 — credit-outlier(1005>1.8x530)
- `2024-06-27` — pnl $50, credit $550 — sem-strikes
- `2026-05-12` — pnl $-453, credit $535 — sem-strikes

### rjl_w30_n10_0dte
- `2023-12-15` — pnl $897, credit $900 — sem-strikes
- `2024-06-28` — pnl $25, credit $1,025 — sem-strikes
- `2025-11-28` — pnl $1,475, credit $1,475 — sem-strikes, retained_dist(566)
- `2026-05-13` — pnl $-1,890, credit $1,110 — sem-strikes

### rjl_w30_n5_0dte
- `2023-12-15` — pnl $322, credit $325 — sem-strikes
- `2024-06-28` — pnl $72, credit $572 — sem-strikes
- `2024-08-05` — pnl $500, credit $500 — sem-strikes
- `2025-11-28` — pnl $1,475, credit $1,475 — sem-strikes, credit-outlier(1475>1.8x543), retained_dist(566)
- `2026-05-13` — pnl $-1,416, credit $573 — sem-strikes
