#!/bin/bash
# =============================================================================
# GCP VM Startup Script
# Executado automaticamente como root na inicialização da VM.
# Instala Docker, clona o repo e inicia o pipeline.
# =============================================================================
set -e

LOG="/var/log/ibkr_pipeline.log"
exec >> "$LOG" 2>&1

echo "=== VM Startup: $(date) ==="

# ── Instala dependências ──────────────────────────────────────────────────────
apt-get update -qq
apt-get install -y docker.io docker-compose git curl

# Habilita e inicia Docker
systemctl enable docker
systemctl start docker

# ── Recupera variáveis de ambiente do GCP Metadata ───────────────────────────
# As variáveis são passadas pelo gcp_deploy.sh via --metadata-from-file
META_URL="http://metadata.google.internal/computeMetadata/v1/instance/attributes"
HEADERS=(-H "Metadata-Flavor: Google")

IBKR_USERNAME=$(curl -sf "${META_URL}/IBKR_USERNAME" "${HEADERS[@]}")
IBKR_PASSWORD=$(curl -sf "${META_URL}/IBKR_PASSWORD" "${HEADERS[@]}")
IBKR_TRADING_MODE=$(curl -sf "${META_URL}/IBKR_TRADING_MODE" "${HEADERS[@]}" || echo "paper")
REPO_URL=$(curl -sf "${META_URL}/REPO_URL" "${HEADERS[@]}")

# ── Clona o repositório ───────────────────────────────────────────────────────
cd /opt
if [ -d "prop_desk" ]; then
    cd prop_desk && git pull
else
    git clone "$REPO_URL" prop_desk
    cd prop_desk
fi

# Cria .env na raiz do projeto
cat > .env << EOF
IBKR_USERNAME=${IBKR_USERNAME}
IBKR_PASSWORD=${IBKR_PASSWORD}
IBKR_TRADING_MODE=${IBKR_TRADING_MODE}
IBKR_HOST=ib-gateway
IBKR_PORT=4002
EOF

# Cria diretórios de dados
mkdir -p data/ibkr_raw data/ibkr_assembled

# ── Copia rclone.conf do GCS (se disponível) ─────────────────────────────────
# O arquivo é enviado para um bucket antes do deploy para manter seguro
RCLONE_GCS=$(curl -sf "${META_URL}/RCLONE_GCS_PATH" "${HEADERS[@]}" || echo "")
if [ -n "$RCLONE_GCS" ]; then
    gsutil cp "$RCLONE_GCS" infra/rclone.conf
    echo "rclone.conf baixado de $RCLONE_GCS"
else
    echo "AVISO: RCLONE_GCS_PATH não definido — upload para GDrive desabilitado"
    # Cria arquivo vazio para evitar erro no volume mount
    touch infra/rclone.conf
fi

# ── Inicia o pipeline ─────────────────────────────────────────────────────────
echo "=== Iniciando docker-compose: $(date) ==="
docker-compose -f infra/docker-compose.yml up --abort-on-container-exit

# ── Aguarda conclusão e desliga a VM ─────────────────────────────────────────
echo "=== Pipeline concluído: $(date) ==="
echo "=== Desligando VM em 60 segundos (tempo para logs flushar) ==="
sleep 60
poweroff
