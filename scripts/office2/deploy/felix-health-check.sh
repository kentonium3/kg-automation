#!/usr/bin/env bash
# felix-health-check.sh — Deploy or refresh the felix-health-check
# systemd user timer + service on office2.
# Idempotent: safe to re-run after any in-repo source changes.
#
# Run from office2 as the claude user. No sudo required.
# Usage: bash /home/claude/kg-automation/scripts/office2/deploy/felix-health-check.sh
#
# NOTE (WP03 scope, #676): this script installs and enables the new
# felix-health-check timer. It does NOT remove the openclaw
# health-check-morning / health-check-evening crons — that cutover is
# WP04's manifest/quickstart step, run in strict order after this deploy
# is verified (contract: health-check-runner.contract.md).

set -euo pipefail

REPO_ROOT="/home/claude/kg-automation"
SERVICE_NAME="felix-health-check"
WRAPPER_PACKAGE_PATH="${REPO_ROOT}/scripts/office2/felix_health_check"
HEALTH_CHECK_SCRIPT="/home/claude/helper-scripts/health-check.sh"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"
SYSTEMD_REPO_DIR="${REPO_ROOT}/scripts/office2"

echo ">>> Sanity check"
if [[ "$(whoami)" != "claude" ]]; then
  echo "ERROR: must run as the claude user (currently: $(whoami))" >&2
  exit 1
fi
if [[ ! -f "${WRAPPER_PACKAGE_PATH}/run.py" ]]; then
  echo "ERROR: felix_health_check wrapper not found at ${WRAPPER_PACKAGE_PATH}" >&2
  echo "       Did 'git pull origin main' run successfully?" >&2
  exit 1
fi

echo ">>> Pulling latest repo state"
git -C "${REPO_ROOT}" pull origin main

echo ">>> Preflighting health-check.sh presence + executability"
if [[ ! -f "${HEALTH_CHECK_SCRIPT}" ]]; then
  echo "ERROR: ${HEALTH_CHECK_SCRIPT} not found — the wrapper has nothing to run." >&2
  echo "       This is the same script the removed openclaw crons invoked;" >&2
  echo "       confirm it hasn't moved or been deleted before enabling the timer." >&2
  exit 1
fi
if [[ ! -x "${HEALTH_CHECK_SCRIPT}" ]]; then
  echo "ERROR: ${HEALTH_CHECK_SCRIPT} exists but is not executable." >&2
  echo "       Run: chmod +x ${HEALTH_CHECK_SCRIPT}" >&2
  exit 1
fi
echo "    OK: ${HEALTH_CHECK_SCRIPT} present and executable."

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

echo ">>> Checking ntfy delivery config"
NTFY_ENV_FILE="/data/services/openclaw/felix-health-check/ntfy.env"
if [[ -f "${NTFY_ENV_FILE}" ]]; then
  echo "    OK: ${NTFY_ENV_FILE} present — ntfy alerts enabled."
else
  echo "    WARNING: ${NTFY_ENV_FILE} not found — the wrapper will run but"
  echo "             failure alerts will be skipped (logged as non-fatal)."
  echo "             Provision NTFY_TOPIC=<topic> in that file to enable alerts."
fi

echo ">>> Provisioning unified felix-alert bus env-file skeleton"
# Create the alert-bus topic env-file DIRECTORY + a 0600 skeleton file if absent
# (mirrors the ntfy.env pattern). The topic VALUE is a secret provisioned
# out-of-band by the operator (credential felix-alert-ntfy-topic; template
# scripts/common/alert_bus.env.sample) — this script NEVER writes a real topic,
# only the empty FELIX_ALERT_NTFY_TOPIC= placeholder so the file exists with the
# right ownership/mode and the systemd EnvironmentFile= directives resolve.
ALERT_BUS_ENV_DIR="/home/claude/.config/felix/alert-bus"
ALERT_BUS_ENV_FILE="${ALERT_BUS_ENV_DIR}/env"
if [[ -f "${ALERT_BUS_ENV_FILE}" ]]; then
  echo "    OK: ${ALERT_BUS_ENV_FILE} present — alert-bus topic env-file exists (not overwritten)."
else
  mkdir -p "${ALERT_BUS_ENV_DIR}"
  # Skeleton only: empty placeholder, never a real topic value.
  printf 'FELIX_ALERT_NTFY_TOPIC=\n' > "${ALERT_BUS_ENV_FILE}"
  chmod 600 "${ALERT_BUS_ENV_FILE}"
  echo "    CREATED: ${ALERT_BUS_ENV_FILE} (0600 skeleton, empty placeholder)."
  echo "             Fill FELIX_ALERT_NTFY_TOPIC=<topic> out-of-band to enable the felix-alert bus."
fi

echo ">>> Smoke-test (one-shot run via the installed service)"
systemctl --user start "${SERVICE_NAME}.service"
sleep 1
journalctl --user -u "${SERVICE_NAME}" -n 20 --no-pager || true

echo ">>> Done."
echo "    Tail logs:       journalctl --user -u ${SERVICE_NAME} -f"
echo "    Force a tick:    systemctl --user start ${SERVICE_NAME}.service"
echo "    Signal file:     cat /data/services/openclaw/felix-health-check/last-run.json"
echo "    Soft kill:       systemctl --user stop ${SERVICE_NAME}.timer && systemctl --user disable ${SERVICE_NAME}.timer"
echo "    NOTE: openclaw health-check-morning/evening crons are NOT removed by this"
echo "          script (WP04 scope) — both paths run in parallel until that cutover."
