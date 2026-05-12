#!/usr/bin/env bash
# deploy.sh — Deploy or migrate Vikunja to the docker-compose pattern (#189).
#
# Replaces the legacy `docker run --rm` deploy. Idempotent: safe to re-run.
# Handles both first-install (no existing unit) and migration (legacy unit
# present — backed up to .deploy-backups/ before replacement).
#
# Run on office2 as the claude user. The script does all the non-sudo
# prep + validation, then prints the exact sudo recipe for Kent to run
# via `ssh office2-kgale`.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/services/vikunja/docker-compose.yml"
SERVICE_FILE_SRC="$REPO_ROOT/scripts/vikunja/vikunja.service"
SERVICE_FILE_DST="/etc/systemd/system/vikunja.service"
BIND_IP="100.92.197.90"
BIND_PORT="3456"
DATA_DIR="/data/services/vikunja/data"
BACKUP_DIR="/data/services/vikunja/.deploy-backups"

echo "=== Vikunja deploy (docker-compose pattern, #189) ==="
echo ""

# ---- Environment checks ----

if ! command -v docker >/dev/null 2>&1; then
    echo "ERROR: Docker not installed." >&2
    exit 1
fi
echo "[OK] Docker: $(docker --version)"

if ! docker compose version >/dev/null 2>&1; then
    echo "ERROR: 'docker compose' subcommand not available. Need Docker 20.10+ with compose plugin." >&2
    exit 1
fi
echo "[OK] Docker Compose: $(docker compose version --short)"

if ! command -v tailscale >/dev/null 2>&1; then
    echo "ERROR: Tailscale not installed." >&2
    exit 1
fi
ACTUAL_IP=$(tailscale ip -4 2>/dev/null || echo "unknown")
if [ "$ACTUAL_IP" != "$BIND_IP" ]; then
    echo "WARNING: Expected Tailscale IP $BIND_IP but found $ACTUAL_IP." >&2
fi
echo "[OK] Tailscale: $ACTUAL_IP"

# ---- File checks ----

for f in "$COMPOSE_FILE" "$SERVICE_FILE_SRC"; do
    if [ ! -f "$f" ]; then
        echo "ERROR: required file missing: $f" >&2
        exit 1
    fi
done
echo "[OK] Compose file: $COMPOSE_FILE"
echo "[OK] Unit source: $SERVICE_FILE_SRC"

# ---- Compose validation ----

echo ""
echo "Validating compose file..."
if ! docker compose -f "$COMPOSE_FILE" config >/dev/null 2>&1; then
    echo "ERROR: docker compose config failed — invalid YAML or unresolved references" >&2
    docker compose -f "$COMPOSE_FILE" config 2>&1 | tail -20 >&2
    exit 1
fi
echo "[OK] Compose file valid"

# ---- Data dir ----

if [ ! -d "$DATA_DIR" ]; then
    echo "Creating data directory: $DATA_DIR"
    mkdir -p "$DATA_DIR"
fi
echo "[OK] Data dir: $DATA_DIR"

# ---- Image pull ----

echo ""
echo "Pulling Vikunja image..."
docker compose -f "$COMPOSE_FILE" pull >/dev/null
echo "[OK] Image pulled"

# ---- Unit file: detect legacy install + back up ----

echo ""
mkdir -p "$BACKUP_DIR"

BACKUP_PATH=""
if [ -f "$SERVICE_FILE_DST" ]; then
    if diff -q "$SERVICE_FILE_DST" "$SERVICE_FILE_SRC" >/dev/null 2>&1; then
        UNIT_STATUS="already_current"
        echo "[OK] Deployed unit already matches in-repo source — no swap needed."
    else
        UNIT_STATUS="needs_update"
        BACKUP_NAME="vikunja.service.pre-189.$(date +%Y%m%d-%H%M%S)"
        BACKUP_PATH="$BACKUP_DIR/$BACKUP_NAME"
        cp "$SERVICE_FILE_DST" "$BACKUP_PATH"
        echo "[OK] Existing unit backed up: $BACKUP_PATH"
    fi
else
    UNIT_STATUS="fresh_install"
    echo "[OK] No existing unit file — fresh install."
fi

# ---- Sudo recipe ----

if [ "$UNIT_STATUS" = "already_current" ]; then
    echo ""
    echo "============================================================"
    echo "Nothing to deploy at the systemd level."
    echo "============================================================"
    echo ""
    echo "If the running container still looks legacy (e.g. you see"
    echo "'docker run --rm --name vikunja' in 'ps -ef'), the unit was"
    echo "updated since the running container was started. To pick up"
    echo "the compose pattern, restart the service:"
    echo ""
    echo "  ssh office2-kgale 'sudo systemctl restart vikunja'"
    echo ""
    exit 0
fi

echo ""
echo "============================================================"
echo "MANUAL SUDO RECIPE — run via ssh office2-kgale"
echo "============================================================"
echo ""
cat <<RECIPE
ssh office2-kgale '
  set -euo pipefail
  echo "=== Vikunja unit swap (#189) ==="

  # 1. Stop the old service (this stops the docker run --rm container too).
  sudo systemctl stop vikunja

  # 2. Replace the unit file.
  sudo cp $SERVICE_FILE_SRC /etc/systemd/system/vikunja.service

  # 3. Reload systemd to pick up the new unit.
  sudo systemctl daemon-reload

  # 4. Start the service. ExecStart runs docker compose up -d, which
  #    re-creates the vikunja container against the same data volume.
  sudo systemctl start vikunja

  # 5. Status check.
  sudo systemctl status vikunja --no-pager | head -10
'
RECIPE
echo ""
echo "After the recipe completes, run the verification block:"
echo ""
cat <<VERIFY
ssh office2-claude '
  set -e
  echo "=== Verification ==="
  systemctl is-active vikunja && echo "[OK] systemd unit active"
  docker ps --filter name=vikunja --format "  {{.Names}} | {{.Image}} | {{.Status}}"
  # Use GET (not HEAD) — Vikunja /api/v1/info returns 401 on HEAD but 200 on GET.
  curl -sf http://${BIND_IP}:${BIND_PORT}/api/v1/info >/dev/null && echo "[OK] API responds on ${BIND_IP}:${BIND_PORT}"
  curl -sf https://office2.tail0f5f56.ts.net/api/v1/info >/dev/null && echo "[OK] HTTPS proxy responds"
'
VERIFY
echo ""
echo "Auto-recovery acceptance test (the actual reason for this change):"
echo "  ssh office2-kgale 'sudo systemctl restart docker.service'"
echo "  # wait ~30s"
echo "  ssh office2-claude 'curl -sf http://${BIND_IP}:${BIND_PORT}/api/v1/info >/dev/null && echo Vikunja-auto-recovered'"
echo ""
echo "=== Deploy script complete ==="
echo ""
echo "Rollback (if something goes wrong):"
if [ "$UNIT_STATUS" = "needs_update" ] && [ -n "$BACKUP_PATH" ]; then
    echo "  ssh office2-kgale 'sudo cp $BACKUP_PATH /etc/systemd/system/vikunja.service && sudo systemctl daemon-reload && sudo systemctl restart vikunja'"
else
    echo "  (No previous unit to roll back to — fresh install.)"
fi
