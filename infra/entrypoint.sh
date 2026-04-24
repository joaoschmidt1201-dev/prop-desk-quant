#!/bin/bash
# =============================================================================
# IBKR Backfill Pipeline — Entrypoint
# Orquestra Step 1 → Step 2 → Step 3 → rclone sync
# =============================================================================
set -e  # Para imediatamente em qualquer erro

echo ""
echo "============================================================"
echo "  IBKR Backfill Pipeline"
echo "  $(date '+%Y-%m-%d %H:%M:%S UTC')"
echo "============================================================"
echo ""

# Aguarda IB Gateway estar pronto (já garantido pelo healthcheck do compose,
# mas adiciona 5s de buffer para o login do IBKR completar)
echo "[0/3] Aguardando IB Gateway estabilizar..."
sleep 5

# Diretórios de dados
mkdir -p /app/data/ibkr_raw
mkdir -p /app/data/ibkr_assembled

# ── Step 1: Geração do universo de contratos ─────────────────────────────────
echo ""
echo "[1/3] Gerando universo de contratos..."
python ibkr_step1_contract_gen.py
echo "[1/3] Concluído."

# ── Step 2: Download bulk via IBKR ───────────────────────────────────────────
echo ""
echo "[2/3] Iniciando download bulk (estimado: 6-8h)..."
python ibkr_step2_bulk_downloader.py \
    --host "${IBKR_HOST:-ib-gateway}" \
    --port "${IBKR_PORT:-4002}"
echo "[2/3] Download concluído."

# ── Step 3: Montar parquets diários ──────────────────────────────────────────
echo ""
echo "[3/3] Montando parquets diários..."
python ibkr_step3_daily_assembler.py \
    --output-dir /app/data/ibkr_assembled \
    --validate
echo "[3/3] Assembly concluído."

# ── rclone sync para Google Drive ────────────────────────────────────────────
if [ -f "/rclone/rclone.conf" ]; then
    echo ""
    echo "[UPLOAD] Sincronizando para Google Drive..."
    rclone copy /app/data/ibkr_assembled gdrive:Quant_Data_MD \
        --config /rclone/rclone.conf \
        --progress \
        --transfers 4
    echo "[UPLOAD] Sync concluído."
else
    echo ""
    echo "[AVISO] rclone.conf não encontrado — pulando upload."
    echo "         Monte infra/rclone.conf em /rclone/rclone.conf para habilitar."
fi

# ── Sinaliza conclusão ────────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "  PIPELINE COMPLETO — $(date '+%Y-%m-%d %H:%M:%S UTC')"
echo "============================================================"
touch /app/data/pipeline_complete
echo ""
