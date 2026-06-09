#!/usr/bin/env bash
# credential-liveness-probe.sh — Deploy or refresh the credential-liveness-probe
# systemd user timer + service on office2. Idempotent.
#
# Run from office2 as the claude user. No sudo required.
# Usage: bash /home/claude/kg-automation/scripts/office2/deploy/credential-liveness-probe.sh

set -euo pipefail

REPO_ROOT="/home/claude/kg-automation"
SERVICE_NAME="credential-liveness-probe"
PACKAGE_REPO_PATH="${REPO_ROOT}/scripts/security/credential_health_check"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"
SYSTEMD_REPO_DIR="${REPO_ROOT}/scripts/office2"

echo ">>> Sanity check"
if [[ "$(whoami)" != "claude" ]]; then
  echo "ERROR: must run as the claude user (currently: $(whoami))" >&2
  exit 1
fi
if [[ ! -f "${PACKAGE_REPO_PATH}/liveness.py" ]]; then
  echo "ERROR: liveness.py not found at ${PACKAGE_REPO_PATH}/liveness.py" >&2
  echo "       Did 'git pull origin main' run successfully?" >&2
  exit 1
fi
if [[ ! -x "/home/linuxbrew/.linuxbrew/bin/gog" ]]; then
  echo "ERROR: gog binary not found at /home/linuxbrew/.linuxbrew/bin/gog" >&2
  echo "       See docs/runbooks/google-workspace-ops.md for setup." >&2
  exit 1
fi
if [[ ! -f "/data/services/openclaw/secrets/openclaw-gateway.env" ]]; then
  echo "ERROR: openclaw-gateway env file missing at /data/services/openclaw/secrets/openclaw-gateway.env" >&2
  exit 1
fi

echo ">>> Pulling latest repo state"
git -C "${REPO_ROOT}" pull origin main

echo ">>> Installing systemd user timer + service"
mkdir -p "${SYSTEMD_USER_DIR}"
cp "${SYSTEMD_REPO_DIR}/${SERVICE_NAME}.timer" "${SYSTEMD_USER_DIR}/${SERVICE_NAME}.timer"
cp "${SYSTEMD_REPO_DIR}/${SERVICE_NAME}.service" "${SYSTEMD_USER_DIR}/${SERVICE_NAME}.service"
systemctl --user daemon-reload
systemctl --user enable --now "${SERVICE_NAME}.timer"

echo ">>> Verifying timer is active"
if systemctl --user is-active --quiet "${SERVICE_NAME}.timer"; then
  NEXT_FIRE=$(systemctl --user list-timers "${SERVICE_NAME}.timer" --no-pager 2>/dev/null | awk 'NR==2 {print $1, $2, $3, $4}')
  echo "    OK: ${SERVICE_NAME}.timer active. Next fire: ${NEXT_FIRE}"
else
  echo "    ERROR: ${SERVICE_NAME}.timer is not active after enable" >&2
  exit 1
fi

echo ">>> Smoke-test (dry-run, real probe call)"
PYTHONPATH="${REPO_ROOT}/scripts/security" python3 -m credential_health_check \
  --manifest "${REPO_ROOT}/docs/design/architecture/data/credential-manifest.json" \
  --dry-run --liveness-only

echo ">>> Deploy complete."
echo "    Verify: systemctl --user status ${SERVICE_NAME}.timer"
echo "    Force a probe: systemctl --user start ${SERVICE_NAME}.service"
echo "    View logs: journalctl --user -u ${SERVICE_NAME}.service --since '1 hour ago'"
