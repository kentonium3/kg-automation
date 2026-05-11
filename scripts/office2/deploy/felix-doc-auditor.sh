#!/usr/bin/env bash
# felix-doc-auditor.sh — Deploy or refresh felix-doc-auditor agent on office2
# Idempotent: safe to re-run after any in-repo source changes.
#
# Run from office2 (as claude or kgale; sudo required for some steps).
# Usage: bash /home/claude/kg-automation/scripts/office2/deploy/felix-doc-auditor.sh

set -euo pipefail

REPO_ROOT="/home/claude/kg-automation"
AGENT_NAME="felix-doc-auditor"
SKILL_NAME="doc-audit"
AGENT_REPO_PATH="${REPO_ROOT}/scripts/openclaw/agents/${AGENT_NAME}"
AGENT_DEPLOY_PATH="/data/services/openclaw/${AGENT_NAME}"
SKILL_REPO_PATH="${REPO_ROOT}/scripts/openclaw/skills/${SKILL_NAME}"
SKILL_DEPLOY_PATH="${HOME}/.openclaw/skills/${SKILL_NAME}"

echo ">>> Pulling latest repo state"
git -C "${REPO_ROOT}" pull origin main

echo ">>> Verifying source paths exist"
for p in "${AGENT_REPO_PATH}" "${SKILL_REPO_PATH}"; do
  if [ ! -d "${p}" ]; then
    echo "ERROR: source directory missing: ${p}" >&2
    exit 1
  fi
done

echo ">>> Deploying agent workspace -> ${AGENT_DEPLOY_PATH}"
mkdir -p "${AGENT_DEPLOY_PATH}"
rsync -av --delete "${AGENT_REPO_PATH}/" "${AGENT_DEPLOY_PATH}/"

echo ">>> Deploying skill -> ${SKILL_DEPLOY_PATH}"
mkdir -p "${SKILL_DEPLOY_PATH}"
rsync -av --delete "${SKILL_REPO_PATH}/" "${SKILL_DEPLOY_PATH}/"

echo ">>> Verifying OpenClaw recognizes the agent"
if openclaw agents 2>/dev/null | grep -q "${AGENT_NAME}"; then
  echo "    OK: ${AGENT_NAME} is registered with OpenClaw"
else
  echo "    WARNING: ${AGENT_NAME} not in 'openclaw agents' output"
  echo "    Manual step required: edit /home/claude/.openclaw/openclaw.json"
  echo "    See WP05 / T019 for the JSON snippet to add"
fi

echo ">>> Verifying skill is discoverable"
if [ -f "${SKILL_DEPLOY_PATH}/SKILL.md" ]; then
  echo "    OK: ${SKILL_DEPLOY_PATH}/SKILL.md present"
else
  echo "    ERROR: skill SKILL.md missing after deploy" >&2
  exit 1
fi

echo ">>> Installing systemd user timer + service"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"
SYSTEMD_REPO_DIR="${REPO_ROOT}/scripts/office2"
mkdir -p "${SYSTEMD_USER_DIR}"
cp "${SYSTEMD_REPO_DIR}/${AGENT_NAME}.timer" "${SYSTEMD_USER_DIR}/${AGENT_NAME}.timer"
cp "${SYSTEMD_REPO_DIR}/${AGENT_NAME}.service" "${SYSTEMD_USER_DIR}/${AGENT_NAME}.service"
systemctl --user daemon-reload
systemctl --user enable --now "${AGENT_NAME}.timer"

echo ">>> Verifying timer is active"
if systemctl --user is-active --quiet "${AGENT_NAME}.timer"; then
  NEXT_FIRE=$(systemctl --user list-timers "${AGENT_NAME}.timer" --no-pager 2>/dev/null | awk 'NR==2 {print $1, $2, $3, $4}')
  echo "    OK: ${AGENT_NAME}.timer active. Next fire: ${NEXT_FIRE}"
else
  echo "    ERROR: ${AGENT_NAME}.timer is not active after enable" >&2
  exit 1
fi

echo ">>> Done."
echo "    Manual on first deploy: create the GitHub label (see WP05 / T020)."
echo "    Tail logs:    journalctl --user -u ${AGENT_NAME} -f"
echo "    Force a tick: systemctl --user start ${AGENT_NAME}.service"
