#!/usr/bin/env bash
# deploy.sh — Deploy Vikunja Docker container on office2
# Run as claude user. Sudo commands are printed for Kent to execute manually.
set -euo pipefail

VIKUNJA_IMAGE="vikunja/vikunja:0.24.6"
BIND_IP="100.92.197.90"
BIND_PORT="3456"
DATA_DIR="/data/services/vikunja/data"
SERVICE_FILE="$(cd "$(dirname "$0")" && pwd)/vikunja.service"

echo "=== Vikunja Deploy ==="
echo ""

# Check Docker
if ! command -v docker &>/dev/null; then
    echo "ERROR: Docker is not installed on this system." >&2
    exit 1
fi
echo "[OK] Docker installed: $(docker --version)"

# Check Tailscale
if ! command -v tailscale &>/dev/null; then
    echo "ERROR: Tailscale is not installed on this system." >&2
    exit 1
fi

ACTUAL_IP=$(tailscale ip -4 2>/dev/null || echo "unknown")
if [ "$ACTUAL_IP" != "$BIND_IP" ]; then
    echo "WARNING: Expected Tailscale IP $BIND_IP but found $ACTUAL_IP" >&2
    echo "Update BIND_IP in this script if the IP has changed." >&2
fi
echo "[OK] Tailscale active: $ACTUAL_IP"

# Check port
if ss -tlnp | grep -q ":${BIND_PORT}" 2>/dev/null; then
    EXISTING=$(ss -tlnp | grep ":${BIND_PORT}")
    echo "WARNING: Port $BIND_PORT is already in use:" >&2
    echo "  $EXISTING" >&2
    echo "If this is an existing Vikunja container, stop it first." >&2
    read -p "Continue anyway? (y/N) " -r
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi
echo "[OK] Port $BIND_PORT is available"

# Check data directory
if [ ! -d "$DATA_DIR" ]; then
    echo "Creating data directory: $DATA_DIR"
    mkdir -p "$DATA_DIR"
fi
echo "[OK] Data directory: $DATA_DIR"

# Pull image
echo ""
echo "Pulling Docker image: $VIKUNJA_IMAGE"
docker pull "$VIKUNJA_IMAGE"
echo "[OK] Image pulled"

# Test run (quick start/stop to verify image works)
echo ""
echo "Testing container startup..."
docker run --rm -d --name vikunja-test \
    -p "${BIND_IP}:${BIND_PORT}:3456" \
    -v "${DATA_DIR}:/app/vikunja/files" \
    -e VIKUNJA_SERVICE_PUBLICURL="http://office2:${BIND_PORT}" \
    -e VIKUNJA_SERVICE_INTERFACE=":3456" \
    -e VIKUNJA_DATABASE_TYPE=sqlite \
    -e VIKUNJA_DATABASE_PATH=/app/vikunja/files/vikunja.db \
    "$VIKUNJA_IMAGE" >/dev/null 2>&1

sleep 3

if docker ps | grep -q vikunja-test; then
    echo "[OK] Container starts successfully"
    docker stop vikunja-test >/dev/null 2>&1 || true
else
    echo "ERROR: Container failed to start. Check: docker logs vikunja-test" >&2
    docker rm -f vikunja-test >/dev/null 2>&1 || true
    exit 1
fi

# Verify port binding
echo ""
echo "Verifying port binding..."
docker run --rm -d --name vikunja-verify \
    -p "${BIND_IP}:${BIND_PORT}:3456" \
    -v "${DATA_DIR}:/app/vikunja/files" \
    -e VIKUNJA_SERVICE_PUBLICURL="http://office2:${BIND_PORT}" \
    -e VIKUNJA_SERVICE_INTERFACE=":3456" \
    -e VIKUNJA_DATABASE_TYPE=sqlite \
    -e VIKUNJA_DATABASE_PATH=/app/vikunja/files/vikunja.db \
    "$VIKUNJA_IMAGE" >/dev/null 2>&1

sleep 2
# Check the local address column (field 4 in ss output) for the bind IP
LOCAL_ADDR=$(ss -tlnp | grep ":${BIND_PORT}" | awk '{print $4}' || true)
if [ -z "$LOCAL_ADDR" ]; then
    echo "ERROR: Port $BIND_PORT not found in ss output" >&2
    docker stop vikunja-verify >/dev/null 2>&1 || true
    exit 1
fi
if echo "$LOCAL_ADDR" | grep -q "0.0.0.0:${BIND_PORT}"; then
    echo "SECURITY ERROR: Port bound to 0.0.0.0 — aborting!" >&2
    docker stop vikunja-verify >/dev/null 2>&1 || true
    exit 1
fi
if ! echo "$LOCAL_ADDR" | grep -q "${BIND_IP}:${BIND_PORT}"; then
    echo "WARNING: Port bound to $LOCAL_ADDR (expected ${BIND_IP}:${BIND_PORT})" >&2
fi
echo "[OK] Port binding: $LOCAL_ADDR"
docker stop vikunja-verify >/dev/null 2>&1 || true

# Print sudo commands for Kent
echo ""
echo "============================================================"
echo "MANUAL STEP: Kent must run the following sudo commands:"
echo "============================================================"
echo ""
echo "  sudo cp $SERVICE_FILE /etc/systemd/system/vikunja.service"
echo "  sudo systemctl daemon-reload"
echo "  sudo systemctl enable vikunja"
echo "  sudo systemctl start vikunja"
echo ""
echo "After running, verify with:"
echo "  systemctl status vikunja"
echo "  ss -tlnp | grep $BIND_PORT"
echo "  curl -s http://${BIND_IP}:${BIND_PORT}"
echo ""
echo "=== Deploy script complete ==="
