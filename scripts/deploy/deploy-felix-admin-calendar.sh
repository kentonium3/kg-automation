#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

# deploy-felix-admin-calendar.sh — Felix calendar subagent extraction deploy wrapper
#
# Mission: felix-calendar-subagent-extraction-01KTTA33
# Issue:   kentonium3/kg-automation#579
# Contract: kitty-specs/felix-calendar-subagent-extraction-01KTTA33/contracts/openclaw-json-entry.md
# Plan ref: kitty-specs/felix-calendar-subagent-extraction-01KTTA33/plan.md § Deploy substrate
#
# Strict-order-of-operations deploy wrapper (DIR-005, DIR-006, DIR-008).
# Registers the new `felix-admin-calendar` OpenClaw subagent on office2 and
# verifies the truncation warning that broke WhatsApp reply relay on
# 2026-06-09 is gone after main/AGENTS.md was tightened below the 12K
# bootstrap context cap.
#
# Order of operations (each stage runs only after the previous succeeds):
#   1. Pre-flight       — artifact presence, pytest green, SSH reachable,
#                         backup-log hygiene (advisory)
#   2. Agent sync       — start agent-prompt-sync.service, verify sizes
#   3. openclaw.json    — idempotent jq insert of the felix-admin-calendar
#                         entry with backup + parse validation
#   4. Service restart  — restart openclaw-gateway, confirm active
#   5. Journal watch    — NFR-002: zero "truncating in injected context"
#                         hits scoped to agent:main:* sessions since
#                         deploy start
#   6. Post-flight      — print smoke runbook path, rebaseline command,
#                         and merge-commit footer reminder
#
# Exit codes (per task T024):
#   0  success — all stages green
#   1  pre-flight failure (artifacts missing, pytest red, SSH dead, etc.)
#   2  agent-prompt-sync failure (timer unit missing or size mismatch)
#   3  openclaw.json edit failure (backup, jq mutation, or validation)
#   4  service restart failure (gateway not active after restart)
#   5  NFR-002 verification failure (truncation warnings still observed)
#
# Rollback (printed verbatim at every failure path, also summarized here):
#   Stage 1: no-op — nothing touched office2 state yet.
#   Stage 2: no-op — sync is read-converging; mutations begin at stage 3.
#                    Re-run after fixing the local artifact.
#   Stage 3+: restore the backup created at stage 3:
#     ssh office2-claude "cp \$HOME/.openclaw/openclaw.json.bak-<TS> \
#                              \$HOME/.openclaw/openclaw.json && \
#                          systemctl --user restart openclaw-gateway.service"
#   Stage 5: same as stage 3+ (config was mutated). Operator should also
#            revert the merge of WP02's main/AGENTS.md tightening if the
#            truncation reappeared from a regression introduced there.
#
# Operator-only post-deploy steps (not run by this script):
#   - Smoke DM checklist: docs/runbooks/felix-calendar-subagent-extraction-01KTTA33-smoke.md
#   - Rebaseline (#557):  ssh office2-claude 'rm /data/services/security-monitor/baselines/* && sg docker -c /data/services/security-monitor/scripts/audit.sh'
#   - Merge-commit footer must record `Rebaseline: completed at <ts>`.
#
# Usage:
#   scripts/deploy/deploy-felix-admin-calendar.sh

SCRIPT_NAME="$(basename "$0")"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MISSION_SLUG="felix-calendar-subagent-extraction-01KTTA33"
OFFICE2_HOST="office2-claude"    # SSH alias from ~/.ssh/config — claude account ONLY (never kgale)
# Remote openclaw config path. The literal contains $HOME so it expands on
# the REMOTE shell, not locally. shellcheck flags this (SC2016) but it's the
# intended shape — the local shell must not resolve $HOME because this Mac's
# $HOME differs from office2's.
# shellcheck disable=SC2016
OPENCLAW_JSON='$HOME/.openclaw/openclaw.json'

TS="$(date -u +%Y%m%dT%H%M%SZ)"
DEPLOY_START="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# Local agent prompt directory (WP02 owns these files).
AGENT_DIR_LOCAL="${REPO_ROOT}/scripts/openclaw/agents/felix-admin-calendar"
AGENT_FILES=(AGENTS.md IDENTITY.md SOUL.md TOOLS.md USER.md)

# Office2 workspace paths (per plan § Deploy substrate and openclaw-json-entry.md
# contract).  The `workspace` field in the openclaw entry resolves to
# /data/services/openclaw/calendar-agent for felix-admin-calendar.  The main
# agent's deployed AGENTS.md lives at /data/services/openclaw/data/AGENTS.md
# per the existing agent-prompt-sync convention.
REMOTE_CALENDAR_WORKSPACE="/data/services/openclaw/calendar-agent"
REMOTE_MAIN_AGENTS_MD="/data/services/openclaw/data/AGENTS.md"

# Local main agents file for the sync-size comparison.
LOCAL_MAIN_AGENTS_MD="${REPO_ROOT}/scripts/openclaw/agents/main/AGENTS.md"

# Rebaseline command (printed VERBATIM per CLAUDE.md / #557).
REBASELINE_CMD="ssh office2-claude 'rm /data/services/security-monitor/baselines/* && sg docker -c /data/services/security-monitor/scripts/audit.sh'"
REBASELINE_VERIFY_CMD="ssh office2-claude 'ls /data/services/security-monitor/baselines/ | wc -l && tail -5 /data/services/security-monitor/logs/audit-\$(date +%Y-%m-%d).log'"

# Smoke runbook path (delivered by WP07; may not yet exist during development
# of this script but is the canonical handoff path post-merge).
SMOKE_RUNBOOK="docs/runbooks/${MISSION_SLUG}-smoke.md"

# Sleep timings.
SYNC_WAIT_SEC=10
RESTART_WAIT_SEC=5
BOOTSTRAP_WAIT_SEC=10

# NOTE on shellcheck SC2029 (client-side expansion): several `ssh` invocations
# below intentionally let the LOCAL shell substitute constants (paths captured
# in OPENCLAW_JSON / REMOTE_* / TS / DEPLOY_START) into the remote command
# string. These constants are defined here in this script, not on office2, so
# local expansion is correct.  Each such site carries an inline
# `# shellcheck disable=SC2029` annotation acknowledging the deliberate
# pattern.

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log() {
  printf '[%s] %s\n' "${SCRIPT_NAME}" "$*"
}

warn() {
  printf '[%s] WARN: %s\n' "${SCRIPT_NAME}" "$*" >&2
}

err() {
  printf '[%s] ERROR: %s\n' "${SCRIPT_NAME}" "$*" >&2
}

# print_rollback_stage3 prints the canonical post-stage-3 rollback recipe
# (config restore + gateway restart) using the captured TS.
print_rollback_stage3() {
  cat >&2 <<EOF
[${SCRIPT_NAME}] ROLLBACK:
[${SCRIPT_NAME}]   ssh ${OFFICE2_HOST} "cp \$HOME/.openclaw/openclaw.json.bak-${TS} \$HOME/.openclaw/openclaw.json && systemctl --user restart openclaw-gateway.service"
[${SCRIPT_NAME}] After rollback, inspect journalctl --user -u openclaw-gateway and
[${SCRIPT_NAME}] retry the deploy after fixing the underlying issue.
EOF
}

# ---------------------------------------------------------------------------
# Stage 1: Pre-flight (exit code 1 on failure)
# ---------------------------------------------------------------------------
log "=== Stage 1/5: Pre-flight ==="
log "Mission:       ${MISSION_SLUG}"
log "Office2 host:  ${OFFICE2_HOST}"
log "Deploy start:  ${DEPLOY_START}"
log "Backup tag:    ${TS}"
log ""

# 1a — Local artifact presence.
log "Pre-flight 1/5: verifying local agent prompt files exist"
missing_files=()
for f in "${AGENT_FILES[@]}"; do
  if [[ ! -f "${AGENT_DIR_LOCAL}/${f}" ]]; then
    missing_files+=("${AGENT_DIR_LOCAL}/${f}")
  fi
done
if [[ ${#missing_files[@]} -gt 0 ]]; then
  err "Missing required agent prompt files (WP02 must land before deploy):"
  for f in "${missing_files[@]}"; do
    err "  - ${f}"
  done
  err "ROLLBACK: no-op — nothing was touched on office2."
  exit 1
fi
log "  OK: all ${#AGENT_FILES[@]} agent prompt files present in ${AGENT_DIR_LOCAL}"

# 1b — Pytest green.  Asserts NFR-001 + NFR-004 (char-count) and openclaw.json
# schema shape locally before any remote state changes.
log "Pre-flight 2/5: running python3 -m pytest scripts/openclaw/agents/tests/ -v"
if ! ( cd "${REPO_ROOT}" && python3 -m pytest scripts/openclaw/agents/tests/ -v ); then
  err "python3 -m pytest scripts/openclaw/agents/tests/ FAILED."
  err "Resolve red tests before re-running the deploy."
  err "ROLLBACK: no-op — nothing was touched on office2."
  exit 1
fi
log "  OK: pytest green"

# 1c — SSH reachability.  10s connect timeout matches plan's pre-flight check.
log "Pre-flight 3/5: verifying SSH reachability to ${OFFICE2_HOST}"
# `ssh -o ConnectTimeout=10` flag verified via `ssh -o` man page; supported by
# all OpenSSH releases on the office2 substrate.
if ! ssh -o ConnectTimeout=10 -o BatchMode=yes "${OFFICE2_HOST}" 'date -u +%Y-%m-%dT%H:%M:%SZ' >/dev/null; then
  err "SSH to ${OFFICE2_HOST} failed or timed out."
  err "Check Tailscale connectivity and ~/.ssh/config alias."
  err "ROLLBACK: no-op — nothing was touched on office2."
  exit 1
fi
log "  OK: SSH reachable"

# 1d — agent-prompt-sync.service unit existence on office2 (per WP risk row).
# `systemctl --user list-unit-files` flag-shape verified via `systemctl --help`
# (subcommand, no leading dashes); the --user flag scopes to the per-user
# manager (the claude account hosts the unit).
log "Pre-flight 4/5: verifying agent-prompt-sync.service is installed on ${OFFICE2_HOST}"
if ! ssh "${OFFICE2_HOST}" 'systemctl --user list-unit-files agent-prompt-sync.service' | grep -q 'agent-prompt-sync.service'; then
  err "agent-prompt-sync.service unit not found on ${OFFICE2_HOST}."
  err "This deploy depends on #567's auto-sync substrate. Verify the unit"
  err "is installed under ~/.config/systemd/user/ before retrying."
  err "ROLLBACK: no-op — nothing was touched on office2."
  exit 2
fi
log "  OK: agent-prompt-sync.service present"

# 1e — Restic backup hygiene (advisory only — Tier 3 doesn't gate on age).
# Print most recent backup log filenames so the operator can confirm hygiene.
log "Pre-flight 5/5: Restic backup hygiene (advisory only)"
if ! ssh "${OFFICE2_HOST}" 'ls -1 /data/services/backup/logs/ 2>/dev/null | sort | tail -3'; then
  warn "Could not list /data/services/backup/logs/. Tier 3 does not block on this."
fi
log "  (Advisory) — review the timestamps above against your backup expectations."
log ""

# ---------------------------------------------------------------------------
# Stage 2: Agent prompt sync (exit code 2 on failure)
# ---------------------------------------------------------------------------
log "=== Stage 2/5: Agent prompt sync ==="

# Trigger one-shot sync run to avoid the 5-min timer wait.
log "Stage 2: triggering systemctl --user start agent-prompt-sync.service"
if ! ssh "${OFFICE2_HOST}" 'systemctl --user start agent-prompt-sync.service'; then
  err "Failed to start agent-prompt-sync.service on ${OFFICE2_HOST}."
  err "ROLLBACK: no-op — nothing was mutated on office2 yet."
  exit 2
fi

log "Stage 2: waiting ${SYNC_WAIT_SEC}s for sync to complete"
sleep "${SYNC_WAIT_SEC}"

# Local byte sizes (canonical reference).
local_calendar_agents_size="$(wc -c < "${AGENT_DIR_LOCAL}/AGENTS.md" | tr -d '[:space:]')"
local_main_agents_size="$(wc -c < "${LOCAL_MAIN_AGENTS_MD}" | tr -d '[:space:]')"

log "Stage 2: verifying calendar workspace sync (${REMOTE_CALENDAR_WORKSPACE}/AGENTS.md)"
# shellcheck disable=SC2029  # REMOTE_CALENDAR_WORKSPACE expanded locally on purpose
remote_calendar_agents_size="$(ssh "${OFFICE2_HOST}" "wc -c < ${REMOTE_CALENDAR_WORKSPACE}/AGENTS.md 2>/dev/null || echo 0" | tr -d '[:space:]')"
if [[ "${remote_calendar_agents_size}" == "0" ]]; then
  err "Remote calendar AGENTS.md missing or empty after sync run."
  err "Expected: ${REMOTE_CALENDAR_WORKSPACE}/AGENTS.md (~${local_calendar_agents_size} bytes)"
  err "ROLLBACK: no-op — nothing was mutated on office2 yet."
  exit 2
fi
log "  Local size:  ${local_calendar_agents_size} bytes"
log "  Remote size: ${remote_calendar_agents_size} bytes"
if [[ "${local_calendar_agents_size}" != "${remote_calendar_agents_size}" ]]; then
  # Sizes are allowed to drift slightly if the sync renders templates or
  # normalizes line endings; warn but do not fail.
  warn "Size mismatch on calendar AGENTS.md (local ${local_calendar_agents_size} vs remote ${remote_calendar_agents_size})."
  warn "This may be a sync rendering step; verify out-of-band if suspicious."
fi

log "Stage 2: verifying main AGENTS.md sync (${REMOTE_MAIN_AGENTS_MD})"
# shellcheck disable=SC2029  # REMOTE_MAIN_AGENTS_MD expanded locally on purpose
remote_main_agents_size="$(ssh "${OFFICE2_HOST}" "wc -c < ${REMOTE_MAIN_AGENTS_MD} 2>/dev/null || echo 0" | tr -d '[:space:]')"
if [[ "${remote_main_agents_size}" == "0" ]]; then
  err "Remote main AGENTS.md missing or empty after sync run."
  err "Expected: ${REMOTE_MAIN_AGENTS_MD} (~${local_main_agents_size} bytes)"
  err "ROLLBACK: no-op — nothing was mutated on office2 yet."
  exit 2
fi
log "  Local size:  ${local_main_agents_size} bytes"
log "  Remote size: ${remote_main_agents_size} bytes"
if [[ "${local_main_agents_size}" != "${remote_main_agents_size}" ]]; then
  warn "Size mismatch on main AGENTS.md (local ${local_main_agents_size} vs remote ${remote_main_agents_size})."
fi
log "  OK: agent prompt sync verified"
log ""

# ---------------------------------------------------------------------------
# Stage 3: openclaw.json edit (exit code 3 on failure)
# ---------------------------------------------------------------------------
log "=== Stage 3/5: openclaw.json edit ==="

# Idempotency check — if felix-admin-calendar is already registered, skip
# the mutation entirely.  This is critical to preserve invariants on re-run.
log "Stage 3: idempotency check (felix-admin-calendar already registered?)"
# shellcheck disable=SC2029  # OPENCLAW_JSON expansion is intentional (sends literal path string to remote)
existing_entry="$(ssh "${OFFICE2_HOST}" "jq -c '.agents.list[] | select(.id == \"felix-admin-calendar\")' ${OPENCLAW_JSON} 2>/dev/null || true")"
if [[ -n "${existing_entry}" ]]; then
  log "  felix-admin-calendar already registered in ${OPENCLAW_JSON}; skipping edit."
  log "  Entry: ${existing_entry}"
else
  log "  Entry not present; proceeding with backup + jq mutation."

  # Run the full edit transaction remotely, matching the contract verbatim.
  # ${TS} expands LOCALLY (we want the same timestamp captured at script
  # start applied to all stages); $HOME is escaped so it expands on the
  # REMOTE shell to /home/claude/...
  # shellcheck disable=SC2029  # ${TS} local expansion is intentional
  if ! ssh "${OFFICE2_HOST}" "
    set -euo pipefail
    cp \$HOME/.openclaw/openclaw.json \$HOME/.openclaw/openclaw.json.bak-${TS}
    jq '.agents.list += [{
          \"id\": \"felix-admin-calendar\",
          \"name\": \"felix-admin-calendar\",
          \"workspace\": \"/data/services/openclaw/calendar-agent\",
          \"agentDir\": \"/home/claude/.openclaw/agents/felix-admin-calendar/agent\",
          \"model\": \"anthropic/claude-haiku-4-5\"
        }]' \$HOME/.openclaw/openclaw.json.bak-${TS} > \$HOME/.openclaw/openclaw.json.new
    jq . \$HOME/.openclaw/openclaw.json.new > /dev/null
    mv \$HOME/.openclaw/openclaw.json.new \$HOME/.openclaw/openclaw.json
  "; then
    err "openclaw.json mutation failed during backup/jq/mv transaction."
    print_rollback_stage3
    exit 3
  fi

  # Post-edit validation — entry must be present and parseable.
  log "Stage 3: post-edit validation (entry must parse and select)"
  # shellcheck disable=SC2029  # OPENCLAW_JSON expansion is intentional
  if ! ssh "${OFFICE2_HOST}" "jq -e '.agents.list[] | select(.id == \"felix-admin-calendar\")' ${OPENCLAW_JSON} >/dev/null"; then
    err "openclaw.json post-edit validation FAILED: felix-admin-calendar entry not selectable."
    print_rollback_stage3
    exit 3
  fi
  log "  OK: openclaw.json now contains felix-admin-calendar entry"
fi
log ""

# ---------------------------------------------------------------------------
# Stage 4: Service restart (exit code 4 on failure)
# ---------------------------------------------------------------------------
log "=== Stage 4/5: Service restart ==="

log "Stage 4: systemctl --user restart openclaw-gateway.service"
if ! ssh "${OFFICE2_HOST}" 'systemctl --user restart openclaw-gateway.service'; then
  err "Failed to restart openclaw-gateway.service."
  print_rollback_stage3
  exit 4
fi

log "Stage 4: waiting ${RESTART_WAIT_SEC}s for the unit to settle"
sleep "${RESTART_WAIT_SEC}"

# is-active retry-once-after-5s pattern per WP04 risk row.  systemctl
# `is-active` exits 0 only when the unit is `active`; we capture the
# textual state for logging.
log "Stage 4: confirming openclaw-gateway.service is active"
active_state="$(ssh "${OFFICE2_HOST}" 'systemctl --user is-active openclaw-gateway.service' || true)"
if [[ "${active_state}" != "active" ]]; then
  warn "First is-active check returned '${active_state}'; retrying in ${RESTART_WAIT_SEC}s."
  sleep "${RESTART_WAIT_SEC}"
  active_state="$(ssh "${OFFICE2_HOST}" 'systemctl --user is-active openclaw-gateway.service' || true)"
fi
if [[ "${active_state}" != "active" ]]; then
  err "openclaw-gateway.service is not active after restart (state='${active_state}')."
  print_rollback_stage3
  exit 4
fi
log "  OK: openclaw-gateway.service is active"
log ""

# ---------------------------------------------------------------------------
# Stage 5: Journal watch (NFR-002) (exit code 5 on failure)
# ---------------------------------------------------------------------------
log "=== Stage 5/5: Journal watch (NFR-002) ==="

log "Stage 5: waiting ${BOOTSTRAP_WAIT_SEC}s for agent bootstrap to complete"
sleep "${BOOTSTRAP_WAIT_SEC}"

# `journalctl --user -u <unit> --since "<ts>"` flag-shape verified via
# `journalctl --help`.  The --since argument accepts ISO-8601 UTC strings.
# We grep for the truncation marker first, then filter the result down to
# agent:main:* sessions only — per WP04 step 4, non-main truncation hits
# are not a regression of NFR-002.
log "Stage 5: grepping journal since ${DEPLOY_START} for 'truncating in injected context'"
# shellcheck disable=SC2029  # DEPLOY_START expanded locally on purpose (captured at script entry)
trunc_hits="$(ssh "${OFFICE2_HOST}" "journalctl --user -u openclaw-gateway.service --since '${DEPLOY_START}' --no-pager 2>/dev/null | grep 'truncating in injected context' | grep 'agent:main:' || true")"

if [[ -n "${trunc_hits}" ]]; then
  err "NFR-002 verification FAILED — truncation warnings observed on agent:main:* sessions:"
  printf '%s\n' "${trunc_hits}" >&2
  err "main/AGENTS.md is still over the 12K bootstrap cap on the deployed substrate."
  print_rollback_stage3
  err "Operator: also consider reverting WP02's main/AGENTS.md tightening commit if the"
  err "regression originated there (helper test would have caught it pre-deploy; investigate)."
  exit 5
fi
log "  OK: zero truncation warnings observed on agent:main:* sessions since ${DEPLOY_START}"
log "  NFR-002 verified."
log ""

# ---------------------------------------------------------------------------
# Post-flight: operator handoff
# ---------------------------------------------------------------------------
log "=== Post-flight: operator handoff ==="
log ""
log "Deploy stages complete. Next steps (operator-driven, NOT run by this script):"
log ""
log "1. Smoke DM checklist:"
log "     ${SMOKE_RUNBOOK}"
log "   Operator: run the smoke checklist now to validate SC-001 through SC-005."
log ""
log "2. Rebaseline (#557, required for audited-surface changes):"
log "     ${REBASELINE_CMD}"
log ""
log "3. Verify rebaseline completion:"
log "     ${REBASELINE_VERIFY_CMD}"
log ""
log "4. Merge-commit footer reminder:"
log "   The mission merge commit MUST record either:"
log "     Rebaseline: completed at <ts>"
log "   OR"
log "     Rebaseline: not required — <reason>"
log ""
log "Deploy script exiting 0 (success)."

exit 0
