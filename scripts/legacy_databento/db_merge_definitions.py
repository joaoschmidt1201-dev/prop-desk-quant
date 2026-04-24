"""
db_merge_definitions.py
Lê todos os arquivos .csv.zst de data/raw_definitions um por vez,
fazendo append direto no CSV de saída (sem acumular na RAM).
"""

import glob
import os
import sys

import pandas as pd

BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_DIR  = os.path.join(BASE_DIR, "data", "raw_definitions")
OUTPUT_CSV = os.path.join(BASE_DIR, "data", "ndx_definitions_raw.csv")

CHUNKSIZE = 50_000   # linhas por chunk — controla uso de RAM

pattern = os.path.join(INPUT_DIR, "*.csv.zst")
files   = sorted(glob.glob(pattern))

if not files:
    print(f"ERRO: nenhum arquivo .csv.zst encontrado em {INPUT_DIR}")
    sys.exit(1)

print(f"Arquivos encontrados: {len(files)}")
print(f"Saída: {OUTPUT_CSV}\n")

total_rows = 0
write_header = True   # primeiro arquivo escreve o header; demais não

for i, fp in enumerate(files, 1):
    fname = os.path.basename(fp)
    file_rows = 0

    try:
        for chunk in pd.read_csv(fp, compression="zstd", low_memory=False,
                                 chunksize=CHUNKSIZE):
            chunk.to_csv(OUTPUT_CSV, mode="a", index=False, header=write_header)
            write_header = False   # header só na primeira vez
            file_rows += len(chunk)

        total_rows += file_rows
        print(f"  [{i:02d}/{len(files)}] {fname} — {file_rows:,} linhas | acumulado: {total_rows:,}")

    except Exception as e:
        print(f"  [{i:02d}/{len(files)}] ERRO em {fname}: {e}")
        sys.exit(1)

print(f"\n>>> RESULTADO FINAL: {total_rows:,} linhas | arquivo salvo em data/ndx_definitions_raw.csv")
