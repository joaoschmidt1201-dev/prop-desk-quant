#!/bin/bash
# =============================================================================
# GCP Deploy — Cria VM e inicia o pipeline IBKR de backfill
#
# Pré-requisitos:
#   1. gcloud CLI instalado e autenticado (gcloud auth login)
#   2. Projeto GCP configurado (gcloud config set project SEU_PROJETO)
#   3. .env preenchido com IBKR_USERNAME e IBKR_PASSWORD
#   4. (Opcional) rclone.conf no GCS para upload automático ao GDrive
#
# Uso:
#   chmod +x infra/gcp_deploy.sh
#   ./infra/gcp_deploy.sh
#   ./infra/gcp_deploy.sh meu-projeto-gcp us-east1-b
#
# Monitorar logs da VM:
#   gcloud compute ssh ibkr-backfill-YYYYMMDD --zone=ZONE -- 'tail -f /var/log/ibkr_pipeline.log'
#
# Ver progresso do docker:
#   gcloud compute ssh ibkr-backfill-YYYYMMDD --zone=ZONE -- 'docker logs -f $(docker ps -q)'
# =============================================================================

set -e

# ── Configuração ─────────────────────────────────────────────────────────────
GCP_PROJECT="${1:-$(gcloud config get-value project 2>/dev/null)}"
ZONE="${2:-us-central1-a}"
INSTANCE_NAME="ibkr-backfill-$(date +%Y%m%d)"
MACHINE_TYPE="e2-standard-2"   # 2 vCPU, 8GB RAM — ~$0.067/h
DISK_SIZE="50GB"
REPO_URL=$(git remote get-url origin 2>/dev/null || echo "")

# ── Validações ────────────────────────────────────────────────────────────────
if [ -z "$GCP_PROJECT" ]; then
    echo "[ERRO] Projeto GCP não definido."
    echo "       Execute: gcloud config set project SEU_PROJETO_ID"
    exit 1
fi

if [ ! -f ".env" ]; then
    echo "[ERRO] .env não encontrado na raiz do projeto."
    echo "       Crie o .env com IBKR_USERNAME e IBKR_PASSWORD."
    exit 1
fi

# Carrega .env para ler credenciais
source <(grep -v '^#' .env | grep -v '^$' | sed 's/^/export /')

if [ -z "$IBKR_USERNAME" ] || [ -z "$IBKR_PASSWORD" ]; then
    echo "[ERRO] IBKR_USERNAME ou IBKR_PASSWORD não definidos no .env"
    exit 1
fi

if [ -z "$REPO_URL" ]; then
    echo "[ERRO] Repositório Git remoto não encontrado."
    echo "       O startup script clona o repo na VM — configure um remote."
    exit 1
fi

TRADING_MODE="${IBKR_TRADING_MODE:-paper}"

# ── Resumo antes de criar ─────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "  GCP Deploy — IBKR Backfill Pipeline"
echo "============================================================"
echo "  Projeto      : $GCP_PROJECT"
echo "  Zona         : $ZONE"
echo "  VM           : $INSTANCE_NAME"
echo "  Tipo         : $MACHINE_TYPE (~\$0.067/h)"
echo "  Disco        : $DISK_SIZE"
echo "  IBKR user    : $IBKR_USERNAME"
echo "  Modo         : $TRADING_MODE"
echo "  Repo         : $REPO_URL"
echo "  Custo estim. : ~\$0.60-0.80 (7-10h total)"
echo "============================================================"
echo ""
read -p "Confirma criação da VM? (s/N) " confirm
if [[ "$confirm" != "s" && "$confirm" != "S" ]]; then
    echo "Cancelado."
    exit 0
fi

# ── (Opcional) Sobe rclone.conf para GCS ─────────────────────────────────────
RCLONE_GCS_PATH=""
if [ -f "infra/rclone.conf" ] && [ -s "infra/rclone.conf" ]; then
    BUCKET="gs://${GCP_PROJECT}-ibkr-config"
    echo "[INFO] Enviando rclone.conf para $BUCKET..."
    gsutil mb -p "$GCP_PROJECT" "$BUCKET" 2>/dev/null || true
    gsutil cp infra/rclone.conf "${BUCKET}/rclone.conf"
    RCLONE_GCS_PATH="${BUCKET}/rclone.conf"
    echo "[OK] rclone.conf em $RCLONE_GCS_PATH"
fi

# ── Cria a VM ─────────────────────────────────────────────────────────────────
echo ""
echo "[INFO] Criando VM $INSTANCE_NAME..."

gcloud compute instances create "$INSTANCE_NAME" \
    --project="$GCP_PROJECT" \
    --zone="$ZONE" \
    --machine-type="$MACHINE_TYPE" \
    --image-family="ubuntu-2204-lts" \
    --image-project="ubuntu-os-cloud" \
    --boot-disk-size="$DISK_SIZE" \
    --boot-disk-type="pd-standard" \
    --scopes="cloud-platform" \
    --no-restart-on-failure \
    --metadata="startup-script=$(cat infra/vm_startup.sh)" \
    --metadata="IBKR_USERNAME=${IBKR_USERNAME}" \
    --metadata="IBKR_PASSWORD=${IBKR_PASSWORD}" \
    --metadata="IBKR_TRADING_MODE=${TRADING_MODE}" \
    --metadata="REPO_URL=${REPO_URL}" \
    --metadata="RCLONE_GCS_PATH=${RCLONE_GCS_PATH}"

echo ""
echo "============================================================"
echo "  VM criada com sucesso!"
echo "============================================================"
echo ""
echo "  Monitorar logs de startup:"
echo "  gcloud compute ssh $INSTANCE_NAME --zone=$ZONE -- 'tail -f /var/log/ibkr_pipeline.log'"
echo ""
echo "  Ver progresso do download:"
echo "  gcloud compute ssh $INSTANCE_NAME --zone=$ZONE -- 'docker logs -f \$(docker ps -q --filter name=downloader)'"
echo ""
echo "  A VM se desliga automaticamente ao terminar (~7-9h)."
echo "  Custo final: ~\$0.50-0.80"
echo ""
