#!/usr/bin/env bash
# deploy-felix-deployer-bootstrap.sh
# ============================================================================
# Bootstrap deploy for the felix-deployer applier.
#
# Mission:   felix-deployer-ntfy-failure-notifications-01KTZ76F (v2 substrate swap)
#            pull-based-deploy-pipeline-01KTYQQS (WP05, original v1 bootstrap)
# Issue:     kentonium3/kg-automation#595 (v2 substrate swap; supersedes #136)
# Contract:  kitty-specs/felix-deployer-ntfy-failure-notifications-01KTZ76F/contracts/ntfy-notification-v1.md
# Reference: scripts/deploy/deploy-149.sh (canonical one-shot shape)
#
# This is a one-shot wrapper that mirrors the deploy-149.sh canonical shape:
#   - set -euo pipefail
#   - --dry-run / --apply / --rollback modes
#   - Pre-flight checks for every mode
#   - Strict order-of-operations
#   - Halt on any failure (no silent fallbacks)
#   - NEVER touches the system cron table (closed issue #162). Failure
#     notifications now route via direct ntfy.sh POST (curl subprocess in
#     notify.py); no openclaw cron registration in this bootstrap path.
#
# After this script runs successfully on office2 once, every subsequent
# deploy goes through the manifest discipline (deploys/queued/ -> applier
# -> deploys/applied/). This deploy ITSELF is recorded as an applied entry:
# deploys/applied/0002-bootstrap-felix-deployer-v2.yaml, with
# `apply_mode: bootstrap`. That entry supersedes the original
# 0001-bootstrap-felix-deployer.yaml (which is preserved as the historical
# record of the original — partially-applied — bootstrap event).
#
# ----------------------------------------------------------------------------
# Modes
# ----------------------------------------------------------------------------
#   --dry-run   Read-only preview: pre-flight + print intended actions.
#   --apply     Execute the bootstrap end-to-end against office2-claude.
#   --rollback  Disable + remove the felix-deployer timer/service from office2.
#               (Manual operator action; idempotent.)
#
# ----------------------------------------------------------------------------
# Manual rollback recipe (kept in sync with --rollback mode below)
# ----------------------------------------------------------------------------
# If you need to undo this bootstrap without invoking --rollback, run:
#
#   ssh office2-claude 'systemctl --user disable --now felix-deployer.timer felix-deployer.service || true'
#   ssh office2-claude 'rm -f /home/claude/.config/systemd/user/felix-deployer.service /home/claude/.config/systemd/user/felix-deployer.timer'
#   ssh office2-claude 'systemctl --user daemon-reload'
#
# This matches exactly what --rollback does (see the rollback() function below).
# Both must stay in sync.
# ============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SCRIPT_NAME="$(basename "$0")"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

SSH_HOST="office2-claude"
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=10)

REMOTE_REPO="/home/claude/kg-automation"
REMOTE_SYSTEMD_USER_DIR="/home/claude/.config/systemd/user"

FELIX_DEPLOYER_SRC_DIR="${REPO_ROOT}/scripts/deploy/felix-deployer"
DEPLOY_LIB_SRC_DIR="${REPO_ROOT}/scripts/deploy/lib"
SYSTEMD_SERVICE_SRC="${FELIX_DEPLOYER_SRC_DIR}/felix-deployer.service"
SYSTEMD_TIMER_SRC="${FELIX_DEPLOYER_SRC_DIR}/felix-deployer.timer"

ISSUE_REF="kentonium3/kg-automation#595"
APPLIED_NAME="0002-bootstrap-felix-deployer-v2"

# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------
log() { printf '[%s] %s\n' "${SCRIPT_NAME}" "$*"; }
warn() { printf '[%s] WARN: %s\n' "${SCRIPT_NAME}" "$*" >&2; }
err() { printf '[%s] ERROR: %s\n' "${SCRIPT_NAME}" "$*" >&2; }

usage() {
  cat <<EOF
${SCRIPT_NAME} — bootstrap deploy for felix-deployer applier

Usage:
  ${SCRIPT_NAME} --dry-run    Show planned actions only; read-only preview.
  ${SCRIPT_NAME} --apply      Execute the bootstrap against ${SSH_HOST}.
  ${SCRIPT_NAME} --rollback   Disable+remove felix-deployer units from ${SSH_HOST}.
  ${SCRIPT_NAME} -h|--help    Print this message.

Invariants:
  - Never touches the system cron table (closed issue #162). Failure
    notifications route via direct ntfy.sh POST in notify.py — no
    openclaw cron registration in this bootstrap path.
  - --apply records itself as deploys/applied/${APPLIED_NAME}.yaml
    with apply_mode: bootstrap (supersedes the original
    0001-bootstrap-felix-deployer.yaml — preserved as historical record).
  - --rollback exactly matches the rollback recipe in the script header.

Reference shape: scripts/deploy/deploy-149.sh
EOF
}

# ---------------------------------------------------------------------------
# Argument parsing — mutually exclusive modes; default is usage + exit 1
# ---------------------------------------------------------------------------
MODE=""
if [[ $# -eq 0 ]]; then
  usage
  exit 1
fi

case "${1:-}" in
  -h|--help)
    usage
    exit 0
    ;;
  --dry-run|--apply|--rollback)
    MODE="$1"
    ;;
  *)
    err "Unknown argument: ${1:-}"
    usage >&2
    exit 2
    ;;
esac

# ---------------------------------------------------------------------------
# Summary header
# ---------------------------------------------------------------------------
log "Mission:        felix-deployer-ntfy-failure-notifications-01KTZ76F (v2)"
log "Mode:           ${MODE}"
log "Repo root:      ${REPO_ROOT}"
log "SSH host:       ${SSH_HOST}"
log "Remote repo:    ${REMOTE_REPO}"
log "Applied entry:  deploys/applied/${APPLIED_NAME}.yaml"

# ===========================================================================
# Pre-flight (run for every mode — read-only)
# ===========================================================================
log ""
log "===== PRE-FLIGHT ====="

# 1. Local source files present
log "Pre-flight: verifying source files present locally..."
python3 -m scripts.deploy.lib.verify verify_file_present "${FELIX_DEPLOYER_SRC_DIR}/deployer.py"
python3 -m scripts.deploy.lib.verify verify_file_present "${SYSTEMD_SERVICE_SRC}"
python3 -m scripts.deploy.lib.verify verify_file_present "${SYSTEMD_TIMER_SRC}"
python3 -m scripts.deploy.lib.verify verify_file_present "${DEPLOY_LIB_SRC_DIR}/__init__.py"
log "[OK]   All source files present."

# 2. openclaw cron healthy on office2 (lists without error)
log "Pre-flight: confirming openclaw cron is healthy on ${SSH_HOST}..."
if ! ssh "${SSH_OPTS[@]}" "$SSH_HOST" 'openclaw cron list --json' >/dev/null 2>&1; then
  err "[FAIL] 'openclaw cron list --json' returned non-zero on ${SSH_HOST}."
  err "       Confirm openclaw is installed and the user service is running."
  exit 1
fi
log "[OK]   openclaw cron healthy on ${SSH_HOST}."

log "Pre-flight complete."

# ===========================================================================
# Rollback mode (matches the script header recipe exactly)
# ===========================================================================
if [[ "$MODE" == "--rollback" ]]; then
  log ""
  log "===== ROLLBACK ====="
  log "Disabling and removing felix-deployer units from ${SSH_HOST}..."

  # Step 1: stop + disable the timer and service (|| true — idempotent).
  ssh "${SSH_OPTS[@]}" "$SSH_HOST" 'systemctl --user disable --now felix-deployer.timer felix-deployer.service || true'
  log "[OK]   systemctl --user disable --now (timer + service)."

  # Step 2: remove the unit files.
  ssh "${SSH_OPTS[@]}" "$SSH_HOST" "rm -f ${REMOTE_SYSTEMD_USER_DIR}/felix-deployer.service ${REMOTE_SYSTEMD_USER_DIR}/felix-deployer.timer"
  log "[OK]   Removed unit files from ${REMOTE_SYSTEMD_USER_DIR}."

  # Step 3: daemon-reload.
  ssh "${SSH_OPTS[@]}" "$SSH_HOST" 'systemctl --user daemon-reload'
  log "[OK]   systemctl --user daemon-reload."

  log ""
  log "===== ROLLBACK COMPLETE ====="
  log "felix-deployer units removed. Re-run --apply to redeploy."
  exit 0
fi

# ===========================================================================
# Dry-run mode
# ===========================================================================
if [[ "$MODE" == "--dry-run" ]]; then
  log ""
  log "===== DRY RUN ====="
  log "DRY RUN — would do (6 steps):"
  log "  1. rsync scripts/deploy/felix-deployer/ -> ${SSH_HOST}:${REMOTE_REPO}/scripts/deploy/felix-deployer/"
  log "     rsync scripts/deploy/lib/             -> ${SSH_HOST}:${REMOTE_REPO}/scripts/deploy/lib/"
  log "  2. mkdir -p ${REMOTE_SYSTEMD_USER_DIR}"
  log "     scp felix-deployer.service            -> ${SSH_HOST}:${REMOTE_SYSTEMD_USER_DIR}/"
  log "     scp felix-deployer.timer              -> ${SSH_HOST}:${REMOTE_SYSTEMD_USER_DIR}/"
  log "  3. ssh ${SSH_HOST} 'systemctl --user daemon-reload'"
  log "  4. ssh ${SSH_HOST} 'systemctl --user enable --now felix-deployer.timer'"
  log "  5. ssh ${SSH_HOST} 'systemctl --user status felix-deployer.timer' (verify active)"
  log "  6. ssh ${SSH_HOST} 'python3 -m scripts.deploy.lib.applied write_applied --manifest <temp> --apply-mode bootstrap'"
  log "     (writes deploys/applied/${APPLIED_NAME}.yaml; commit + push from office2)"
  log ""
  log "Note: notification topic provisioning (FELIX_DEPLOYER_NTFY_TOPIC in"
  log "      ~/.config/felix-deployer/env on office2) is operator-driven, NOT"
  log "      part of this bootstrap. See scripts/deploy/felix-deployer/env.sample."
  log ""
  log "===== DRY RUN COMPLETE ====="
  log "No mutations performed."
  exit 0
fi

# ===========================================================================
# Apply mode — strict order-of-operations; halt on any failure
# ===========================================================================
log ""
log "===== APPLY ====="

# Step 1: Rsync source artifacts (felix-deployer + deploy lib)
log "Step 1/6: rsync felix-deployer/ and lib/ to ${SSH_HOST}..."
ssh "${SSH_OPTS[@]}" "$SSH_HOST" "mkdir -p ${REMOTE_REPO}/scripts/deploy/felix-deployer ${REMOTE_REPO}/scripts/deploy/lib"
rsync -avz --delete --exclude='__pycache__' --exclude='*.pyc' \
  "${FELIX_DEPLOYER_SRC_DIR}/" "${SSH_HOST}:${REMOTE_REPO}/scripts/deploy/felix-deployer/"
rsync -avz --delete --exclude='__pycache__' --exclude='*.pyc' \
  "${DEPLOY_LIB_SRC_DIR}/" "${SSH_HOST}:${REMOTE_REPO}/scripts/deploy/lib/"
log "[OK]   Source artifacts rsynced."

# Step 2: Install systemd user units
log "Step 2/6: installing systemd user units..."
ssh "${SSH_OPTS[@]}" "$SSH_HOST" "mkdir -p ${REMOTE_SYSTEMD_USER_DIR}"
scp "${SSH_OPTS[@]}" "${SYSTEMD_SERVICE_SRC}" "${SSH_HOST}:${REMOTE_SYSTEMD_USER_DIR}/"
scp "${SSH_OPTS[@]}" "${SYSTEMD_TIMER_SRC}" "${SSH_HOST}:${REMOTE_SYSTEMD_USER_DIR}/"
log "[OK]   Unit files installed."

# Step 3: Reload systemd user daemon
log "Step 3/6: systemctl --user daemon-reload..."
ssh "${SSH_OPTS[@]}" "$SSH_HOST" 'systemctl --user daemon-reload'
log "[OK]   Daemon reloaded."

# Step 4: Enable + start the timer
log "Step 4/6: systemctl --user enable --now felix-deployer.timer..."
ssh "${SSH_OPTS[@]}" "$SSH_HOST" 'systemctl --user enable --now felix-deployer.timer'
log "[OK]   Timer enabled and started."

# Step 5: Post-flight — confirm the timer is actually active
log "Step 5/6: post-flight — confirm felix-deployer.timer is active..."
if ! ssh "${SSH_OPTS[@]}" "$SSH_HOST" 'systemctl --user status felix-deployer.timer' | grep -Eq 'active \((waiting|running)\)'; then
  err "[FAIL] felix-deployer.timer is not active on ${SSH_HOST}."
  err "       Investigate: ssh ${SSH_HOST} 'systemctl --user status felix-deployer.timer'"
  exit 1
fi
log "[OK]   felix-deployer.timer is active."

# Step 6: Write the retroactive applied entry
# Constructs a Tier 1 manifest inline (verification block required by schema),
# writes it via the canonical lib.applied CLI, then commits + pushes from office2.
log "Step 6/6: writing retroactive applied entry deploys/applied/${APPLIED_NAME}.yaml..."

CREATED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# The manifest is written to a temp file on office2 (the lib.applied CLI
# requires --manifest <path>), then load + augment + write under
# deploys/applied/. Tier 1 schema requires a verification block.
ssh "${SSH_OPTS[@]}" "$SSH_HOST" "cat > /tmp/bootstrap-felix-deployer-v2-manifest.yaml" <<EOF
schema_version: v1
name: bootstrap-felix-deployer-v2
issue: ${ISSUE_REF}
tier: 1
entrypoint: scripts/deploy/deploy-felix-deployer-bootstrap.sh
audited_surface: true
verification:
  pre:
    - test -f scripts/deploy/felix-deployer/deployer.py
  post:
    - systemctl --user is-active felix-deployer.timer
    - test -f ${REMOTE_SYSTEMD_USER_DIR}/felix-deployer.service
notes: |
  Bootstrap re-apply of felix-deployer with the ntfy.sh substrate fix
  (kentonium3/kg-automation#595). Supersedes
  deploys/applied/0001-bootstrap-felix-deployer.yaml, which records the
  original partial-applied state when step 5 (openclaw cron registration
  with non-existent flags) failed. The original 0001 entry is preserved
  verbatim as the historical record of the broken-bootstrap event.

  This v2 bootstrap is the first successful clean apply of felix-deployer
  with the ntfy.sh failure-notification substrate. ntfy topic provisioning
  (FELIX_DEPLOYER_NTFY_TOPIC env var via /home/claude/.config/felix-deployer/env)
  is operator-driven, NOT part of this bootstrap.
created_at: "${CREATED_AT}"
created_by: operator-bootstrap
EOF

ssh "${SSH_OPTS[@]}" "$SSH_HOST" "cd ${REMOTE_REPO} && python3 -m scripts.deploy.lib.applied write_applied --manifest /tmp/bootstrap-felix-deployer-v2-manifest.yaml --apply-mode bootstrap"
log "[OK]   Applied entry written."

# Commit + push the new applied entry from office2 (uses claude user's git config).
ssh "${SSH_OPTS[@]}" "$SSH_HOST" "cd ${REMOTE_REPO} && git add deploys/applied/${APPLIED_NAME}.yaml && git commit -m 'chore(deploy): record bootstrap applied entry ${APPLIED_NAME}' && git push origin main"
log "[OK]   Applied entry committed and pushed."

# Cleanup the temp manifest.
ssh "${SSH_OPTS[@]}" "$SSH_HOST" 'rm -f /tmp/bootstrap-felix-deployer-v2-manifest.yaml'

log ""
log "===== APPLY COMPLETE ====="
log "felix-deployer is live on ${SSH_HOST}. Every 5min the timer fires the applier."
log "Applied entry recorded: deploys/applied/${APPLIED_NAME}.yaml"
log ""
log "Next steps:"
log "  - Drop deploys/queued/<name>.yaml manifests to trigger pull-based deploys."
log "  - Check applier logs: ssh ${SSH_HOST} 'journalctl --user -u felix-deployer.service -n 50'"
exit 0
