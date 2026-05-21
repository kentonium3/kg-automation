#!/bin/bash
# felix-doc-auditor scripts-first driver — deploy script
#
# Purpose:
#   Lands the new driver code on office2, installs the systemd unit,
#   retires the old openclaw-agent definition, and removes the legacy
#   workspace files. Implements step 3 of the cutover sequence
#   documented in
#   kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/research.md
#   D10 (5-step fail-forward deploy).
#
# Operator usage:
#   # Dry-run (default — preview only):
#   bash scripts/office2/deploy/felix-doc-auditor-driver.sh
#   # or explicitly:
#   bash scripts/office2/deploy/felix-doc-auditor-driver.sh --dry-run
#
#   # Apply (requires --backup-confirmed):
#   bash scripts/office2/deploy/felix-doc-auditor-driver.sh --apply --backup-confirmed
#
# Pre-requisites:
#   - Run on office2 as the claude user (ssh office2-claude)
#   - Repo at /home/claude/kg-automation up to date with main
#   - openclaw-gateway user service running
#   - Restic backup completed within last 24h (Tier-2 change protocol)
#   - gh CLI authenticated as kg-felix-bot
#   - Anthropic API key readable at /data/services/openclaw/secrets/anthropic
#
# Rollback:
#   None — fail-forward posture per spec C-007.
#   If the deploy fails partway, fix forward and re-run; the script is
#   idempotent for steps 3-7. The old openclaw-agent surface is irrecoverable
#   from this script alone after step 6 (workspace deletion); restore from
#   git (workspace files in scripts/openclaw/agents/felix-doc-auditor/) and
#   re-register via the openclaw CLI if needed.
#
# Idempotency:
#   Re-running the script after a successful deploy is a no-op for steps
#   3-7 (they detect existing state and skip cleanly). Steps 1-2 are always
#   re-run; step 2 is a pull which is itself a no-op if already at the tip.
#
# See also:
#   - kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/research.md (D10 cutover sequence)
#   - kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/contracts/driver-invocation.contract.md
#   - docs/runbooks/doc-auditor-driver-ops.md (operator runbook — written in WP10)

set -euo pipefail

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
REPO_ROOT="/home/claude/kg-automation"
AGENT_NAME="felix-doc-auditor"
DRIVER_REL_PATH="scripts/doc_audit/run.py"
DRIVER_ABS_PATH="${REPO_ROOT}/${DRIVER_REL_PATH}"
SYSTEMD_REPO_DIR="${REPO_ROOT}/scripts/office2"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"
NEW_STATE_DIR="/data/services/openclaw/felix-doc-auditor-driver"
OLD_WORKSPACE_DIR="/data/services/openclaw/felix-doc-auditor"
SECRET_FILE="/data/services/openclaw/secrets/anthropic"
EXPECTED_HOSTNAME="office2"
EXPECTED_GH_USER="kg-felix-bot"

# ---------------------------------------------------------------------------
# Arg parsing
# ---------------------------------------------------------------------------
MODE="dry-run"
BACKUP_CONFIRMED="no"

print_help() {
  cat <<'EOF'
felix-doc-auditor scripts-first driver — deploy script

Purpose:
  Lands the new driver code on office2, installs the systemd unit,
  retires the old openclaw-agent definition, and removes the legacy
  workspace files. Implements step 3 of the cutover sequence
  documented in
  kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/research.md
  D10 (5-step fail-forward deploy).

Operator usage:
  # Dry-run (default — preview only):
  bash scripts/office2/deploy/felix-doc-auditor-driver.sh
  # or explicitly:
  bash scripts/office2/deploy/felix-doc-auditor-driver.sh --dry-run

  # Apply (requires --backup-confirmed):
  bash scripts/office2/deploy/felix-doc-auditor-driver.sh --apply --backup-confirmed

Pre-requisites:
  - Run on office2 as the claude user (ssh office2-claude)
  - Repo at /home/claude/kg-automation up to date with main
  - openclaw-gateway user service running
  - Restic backup completed within last 24h (Tier-2 change protocol)
  - gh CLI authenticated as kg-felix-bot
  - Anthropic API key readable at /data/services/openclaw/secrets/anthropic

Rollback:
  None — fail-forward posture per spec C-007.
  If the deploy fails partway, fix forward and re-run; the script is
  idempotent for steps 3-7. The old openclaw-agent surface is irrecoverable
  from this script alone after step 6 (workspace deletion); restore from
  git (workspace files in scripts/openclaw/agents/felix-doc-auditor/) and
  re-register via the openclaw CLI if needed.

Idempotency:
  Re-running the script after a successful deploy is a no-op for steps
  3-7 (they detect existing state and skip cleanly). Steps 1-2 are always
  re-run; step 2 is a pull which is itself a no-op if already at the tip.

See also:
  - kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/research.md (D10 cutover sequence)
  - kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/contracts/driver-invocation.contract.md
  - docs/runbooks/doc-auditor-driver-ops.md (operator runbook — written in WP10)

Flags:
  --dry-run             Default. Print all intended operations; make no changes.
  --apply               Execute the deploy. Requires --backup-confirmed.
  --backup-confirmed    Operator's signoff that a Restic backup has run within
                        the last 24 hours (per Tier-2 change protocol).
  -h, --help            Print this help and exit.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run) MODE="dry-run" ;;
    --apply) MODE="apply" ;;
    --backup-confirmed) BACKUP_CONFIRMED="yes" ;;
    -h|--help) print_help; exit 0 ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      echo "Run with --help for usage." >&2
      exit 2
      ;;
  esac
  shift
done

if [ "${MODE}" = "apply" ] && [ "${BACKUP_CONFIRMED}" != "yes" ]; then
  cat >&2 <<EOF
ERROR: --apply requires --backup-confirmed.

This deploy is Tier-2 (deletes /data/services/openclaw/felix-doc-auditor/
workspace state). Per the kg-automation Tier-2 change protocol you must
confirm a Restic backup has completed within the last 24h before applying.

Re-run as:
  bash $0 --apply --backup-confirmed
EOF
  exit 2
fi

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
if [ "${MODE}" = "dry-run" ]; then
  PFX="[DRY-RUN]"
else
  PFX="[APPLY]"
fi

CURRENT_STEP="<unset>"

step() {
  CURRENT_STEP="Step $1/8: $2"
  echo
  echo "==> ${CURRENT_STEP}"
}

note() {
  echo "    ${PFX} $*"
}

run_cmd() {
  # Echo what we'd run; only execute in apply mode.
  # In apply mode, if the command fails we MUST emit STEP FAILED before
  # exiting — `set -e` alone would short-circuit the script without the
  # required step-level failure marker. (review-cycle-4 fix.)
  # We capture the command's exit code directly (not via `if !`, whose
  # exit status reflects the negation, not the command).
  echo "    ${PFX} \$ $*"
  if [ "${MODE}" = "apply" ]; then
    local rc=0
    "$@" || rc=$?
    if [ "${rc}" -ne 0 ]; then
      fail "${CURRENT_STEP} — command failed (exit ${rc}): $*"
    fi
  fi
}

fail() {
  echo "STEP FAILED: $1" >&2
  exit 1
}

# ---------------------------------------------------------------------------
# Step 1 — Pre-flight checks
# ---------------------------------------------------------------------------
step 1 "Pre-flight checks"

note "Mode: ${MODE}"

# Hostname check — refuse to run anywhere but office2.
ACTUAL_HOSTNAME="$(hostname)"
if [ "${ACTUAL_HOSTNAME}" != "${EXPECTED_HOSTNAME}" ]; then
  fail "hostname is '${ACTUAL_HOSTNAME}', expected '${EXPECTED_HOSTNAME}'. Refusing to deploy."
fi
note "Hostname OK: ${ACTUAL_HOSTNAME}"

# openclaw-gateway user service must be active.
if systemctl --user is-active --quiet openclaw-gateway.service; then
  note "openclaw-gateway.service: active"
else
  fail "openclaw-gateway.service is not active. Start it before deploying."
fi

# Anthropic secret must be readable.
if [ -r "${SECRET_FILE}" ]; then
  note "Anthropic secret readable at ${SECRET_FILE}"
else
  fail "Anthropic secret not readable at ${SECRET_FILE}"
fi

# gh CLI must be authenticated as kg-felix-bot.
GH_USER="$(gh api user --jq .login 2>/dev/null || echo "")"
if [ "${GH_USER}" = "${EXPECTED_GH_USER}" ]; then
  note "gh authenticated as ${GH_USER}"
else
  fail "gh CLI not authenticated as ${EXPECTED_GH_USER} (got: '${GH_USER:-<none>}')"
fi

# Repo root must exist.
if [ ! -d "${REPO_ROOT}/.git" ]; then
  fail "expected repo at ${REPO_ROOT} not found"
fi
note "Repo present at ${REPO_ROOT}"

# ---------------------------------------------------------------------------
# Step 2 — Pull driver code
# ---------------------------------------------------------------------------
step 2 "Pull driver code (git pull --rebase) at ${REPO_ROOT}"
run_cmd cd "${REPO_ROOT}"
# `cd` above runs in the helper's subshell only when --apply. Make sure the
# subsequent git command lands in the right tree regardless:
if [ "${MODE}" = "apply" ]; then
  cd "${REPO_ROOT}"
fi
run_cmd git -C "${REPO_ROOT}" pull --rebase

# Verify the new driver source landed.
if [ "${MODE}" = "apply" ] && [ ! -f "${DRIVER_ABS_PATH}" ]; then
  fail "driver entry point missing after pull: ${DRIVER_ABS_PATH}"
fi
note "Driver entry point: ${DRIVER_ABS_PATH}"

# ---------------------------------------------------------------------------
# Step 3 — Create driver state directory
# ---------------------------------------------------------------------------
step 3 "Create driver state directory ${NEW_STATE_DIR}"
if [ -d "${NEW_STATE_DIR}" ]; then
  note "already exists — re-asserting ownership and permissions"
else
  run_cmd mkdir -p "${NEW_STATE_DIR}"
fi
run_cmd chmod 755 "${NEW_STATE_DIR}"
run_cmd chown claude:claude "${NEW_STATE_DIR}"

# ---------------------------------------------------------------------------
# Step 4 — Install systemd unit + timer
# ---------------------------------------------------------------------------
step 4 "Install systemd unit + timer to ${SYSTEMD_USER_DIR}"
run_cmd mkdir -p "${SYSTEMD_USER_DIR}"

SRC_SERVICE="${SYSTEMD_REPO_DIR}/${AGENT_NAME}.service"
SRC_TIMER="${SYSTEMD_REPO_DIR}/${AGENT_NAME}.timer"
DST_SERVICE="${SYSTEMD_USER_DIR}/${AGENT_NAME}.service"
DST_TIMER="${SYSTEMD_USER_DIR}/${AGENT_NAME}.timer"

install_if_changed() {
  local src="$1"
  local dst="$2"
  if [ -f "${dst}" ] && cmp -s "${src}" "${dst}"; then
    note "no change needed: ${dst}"
  else
    run_cmd cp "${src}" "${dst}"
  fi
}

install_if_changed "${SRC_SERVICE}" "${DST_SERVICE}"
install_if_changed "${SRC_TIMER}" "${DST_TIMER}"

run_cmd systemctl --user daemon-reload

# ---------------------------------------------------------------------------
# Step 5 — Retire old openclaw agent registration
# ---------------------------------------------------------------------------
# State machine: `openclaw agents list` must succeed before we can decide.
# A non-zero exit from `openclaw agents list` means the registration state is
# UNKNOWN — we must NOT treat that as "already deregistered" because step 6
# below deletes the workspace, which would orphan a still-registered agent.
# Three states:
#   (a) list succeeds AND agent in output     → deregister + verify gone
#   (b) list succeeds AND agent NOT in output → skip (already deregistered)
#   (c) list FAILS (non-zero exit)            → abort the deploy
# State (c) detection requires running the list query in dry-run too — it is
# read-only and surfaces an UNKNOWN posture to the operator before they apply.
step 5 "Retire openclaw agent registration: ${AGENT_NAME}"

# Probe registration state. Capture stdout+stderr so we can surface failure
# detail to the operator. `set -e` is bypassed because the assignment-with-
# command-substitution form lets us inspect the exit code via $?.
openclaw_list_output="$(openclaw agents list 2>&1)" || openclaw_list_rc=$?
openclaw_list_rc="${openclaw_list_rc:-0}"

if [ "${openclaw_list_rc}" -ne 0 ]; then
  # State (c): UNKNOWN. Abort — do NOT proceed to step 6 (workspace delete).
  echo "STEP FAILED: 'openclaw agents list' exited ${openclaw_list_rc} — agent registration state is UNKNOWN." >&2
  echo "  stderr/stdout from openclaw:" >&2
  echo "${openclaw_list_output}" | sed 's/^/    /' >&2
  echo "  Refusing to proceed: step 6 deletes the agent workspace and must not run while registration state is unverified." >&2
  echo "  Operator: investigate openclaw-gateway state manually before re-running this script." >&2
  exit 1
fi

if echo "${openclaw_list_output}" | grep -q "^- ${AGENT_NAME}\b"; then
  # State (a): agent still registered. Deregister and verify.
  note "agent ${AGENT_NAME} present in openclaw — deregistering"
  run_cmd openclaw agents delete "${AGENT_NAME}" --force
  # Post-condition verification (apply mode only — in dry-run nothing was deleted).
  if [ "${MODE}" = "apply" ]; then
    if ! openclaw_verify_output="$(openclaw agents list 2>&1)"; then
      echo "STEP FAILED: post-delete 'openclaw agents list' failed; cannot confirm agent ${AGENT_NAME} was removed." >&2
      echo "  output: ${openclaw_verify_output}" >&2
      exit 1
    fi
    if echo "${openclaw_verify_output}" | grep -q "^- ${AGENT_NAME}\b"; then
      fail "agent ${AGENT_NAME} still present after deregister"
    fi
  fi
else
  # State (b): list succeeded but agent absent — already deregistered.
  note "agent ${AGENT_NAME} already deregistered (not in 'openclaw agents list' output); skipping"
fi

# ---------------------------------------------------------------------------
# Step 6 — Delete legacy workspace files
# ---------------------------------------------------------------------------
step 6 "Delete legacy openclaw workspace at ${OLD_WORKSPACE_DIR}"

# Paranoid path verification — refuse to proceed unless the path matches the
# exact expected shape. (Defends against shell expansion mishaps.)
case "${OLD_WORKSPACE_DIR}" in
  /data/services/openclaw/felix-doc-auditor)
    : ;;
  *)
    fail "OLD_WORKSPACE_DIR does not match expected shape: '${OLD_WORKSPACE_DIR}'"
    ;;
esac

if [ -d "${OLD_WORKSPACE_DIR}" ]; then
  # Tier-2 guard — already enforced at arg parse, re-assert here.
  if [ "${MODE}" = "apply" ] && [ "${BACKUP_CONFIRMED}" != "yes" ]; then
    fail "refusing to delete workspace without --backup-confirmed (Tier-2)"
  fi
  note "workspace exists at ${OLD_WORKSPACE_DIR} — removing"
  # Final path check immediately before destructive op.
  if [ "${OLD_WORKSPACE_DIR}" != "/data/services/openclaw/felix-doc-auditor" ]; then
    fail "path drifted from expected literal — refusing rm -rf"
  fi
  run_cmd rm -rf -- "${OLD_WORKSPACE_DIR}"
else
  note "already deleted, skipping"
fi

# ---------------------------------------------------------------------------
# Step 7 — Verify timer is enabled
# ---------------------------------------------------------------------------
step 7 "Verify ${AGENT_NAME}.timer is enabled"
if systemctl --user is-enabled --quiet "${AGENT_NAME}.timer" 2>/dev/null; then
  note "${AGENT_NAME}.timer already enabled"
else
  run_cmd systemctl --user enable --now "${AGENT_NAME}.timer"
fi

if [ "${MODE}" = "apply" ]; then
  if systemctl --user is-active --quiet "${AGENT_NAME}.timer"; then
    NEXT_FIRE="$(systemctl --user list-timers "${AGENT_NAME}.timer" --no-pager 2>/dev/null | awk 'NR==2 {print $1, $2, $3, $4}')"
    note "${AGENT_NAME}.timer active. Next fire: ${NEXT_FIRE}"
  else
    fail "${AGENT_NAME}.timer is not active after enable"
  fi
fi

# ---------------------------------------------------------------------------
# Step 8 — Done; print follow-up
# ---------------------------------------------------------------------------
step 8 "Done"

if [ "${MODE}" = "dry-run" ]; then
  echo
  echo "Dry-run complete. No changes were made."
  echo "When ready, re-run with: $0 --apply --backup-confirmed"
else
  echo
  echo "Deploy complete. Run a verification tick:"
  echo
  echo "    systemctl --user start --wait ${AGENT_NAME}.service"
  echo
  echo "Then inspect:"
  echo "    cat ${NEW_STATE_DIR}/last-tick.json | jq"
  echo "    journalctl --user -u ${AGENT_NAME} -n 200 --no-pager"
fi
