#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REMOTE="office2-claude"
COMPOSE_DEST="/data/services/transcribe/docker-compose.yml"
SERVICE_STAGING="/tmp/transcribe.service"

echo "=== Transcribe API Deployment ==="

# Stop existing container
echo "[1/4] Stopping existing container..."
ssh "${REMOTE}" "docker-compose -f ${COMPOSE_DEST} down 2>/dev/null || docker stop transcribe-api 2>/dev/null || true"

# Copy updated compose file
echo "[2/4] Copying docker-compose.yml..."
scp "${SCRIPT_DIR}/docker-compose.yml" "${REMOTE}:${COMPOSE_DEST}"

# Stage systemd unit for Kent to install
echo "[3/4] Staging systemd unit..."
scp "${SCRIPT_DIR}/transcribe.service" "${REMOTE}:${SERVICE_STAGING}"

# Start container via compose (without systemd, for immediate testing)
echo "[4/4] Starting container via docker-compose..."
ssh "${REMOTE}" "docker-compose -f ${COMPOSE_DEST} up -d"

echo ""
echo "=== VERIFY ==="
echo "ssh ${REMOTE}"
echo "ss -tlnp | grep 8787"
echo "curl -s http://100.92.197.90:8787/health"
echo ""
echo "=== MANUAL STEPS (Kent runs these via ssh office2-kgale) ==="
echo "sudo cp ${SERVICE_STAGING} /etc/systemd/system/transcribe.service"
echo "sudo systemctl daemon-reload"
echo "sudo systemctl enable transcribe"
echo "sudo systemctl start transcribe"
echo ""
echo "After systemd is installed, verify:"
echo "systemctl status transcribe"
