#!/usr/bin/env bash
set -euo pipefail

# F026: Vault path registry full rollout + folder renumber deploy wrapper
#
# Mission: 026-vault-path-registry-and-folder-renumber
# Issue:   kentonium3/kg-automation#152
# Contract: kitty-specs/026-vault-path-registry-and-folder-renumber/contracts/deploy-wrapper-contract.md
#
# Thin wrapper around scripts/vault/deploy.py that adds mission-specific
# orchestration: cron pause/resume, verification greps, and smoke tests
# around the two critical OpenClaw agents (felix-admin-capture,
# felix-admin-tasker).
#
# Invariants (per contract):
#   1. Idempotent — re-runs with the same registry state produce the same result
#   2. No partial success — either everything succeeds or we exit non-zero
#   3. Never silent — every decision and action emits output
#   4. Exit code fidelity — 0 means every step passed, non-zero means at least
#      one failed
#   5. Verification is mandatory — --skip-smoke and --skip-cron exist only for
#      debugging and must print loud warnings
#
# Lifecycle:
#   - Created:     WP01
#   - First used:  WP04 (--apply --mode pre-rename)
#   - Risky use:   WP05 (--apply --mode post-rename)

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT_NAME="$(basename "$0")"

# ---------------------------------------------------------------------------
# Default argument state
# ---------------------------------------------------------------------------
MODE=""             # "pre-rename" | "post-rename" | "" (none)
APPLY=0             # 0 = dry-run, 1 = apply
SKIP_SMOKE=0
SKIP_CRON=0
BACKUP_CONFIRMED=0  # post-rename Tier 2 pre-flight acknowledgement

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
usage() {
  cat <<EOF
${SCRIPT_NAME} — Mission 026 vault path registry deploy wrapper

Usage:
  ${SCRIPT_NAME} [--dry-run]                              # default: dry-run
  ${SCRIPT_NAME} --apply --mode pre-rename                # WP04 pre-rename deploy
  ${SCRIPT_NAME} --apply --mode post-rename               # WP05 post-rename deploy
  ${SCRIPT_NAME} --help

Flags:
  --dry-run             Show planned actions only; no side effects (default
                        when no --apply flag provided).
  --apply               Actually execute. Requires --mode.
  --mode <m>            One of: pre-rename | post-rename
  --backup-confirmed    (post-rename only) Operator has confirmed a Tier 2
                        Restic backup is <=24h old out-of-band. Skips the
                        inline backup verification prompt.
  --skip-smoke          (debug) Skip smoke tests. Prints a loud warning.
  --skip-cron           (debug) Skip cron pause/resume. Prints a loud warning.
  -h, --help            Print this message and exit 0.

Modes:
  pre-rename   For WP04 — deploy resolved files against the current (pre-rename)
               registry. Cron is NOT touched. Smoke-tests felix-admin-capture
               and felix-admin-tasker and captures output for WP04's
               refactor-fidelity diff.

  post-rename  For WP05 — the risky deploy. Pauses felix-admin-capture cron,
               runs deploy.py, verifies zero stale literals and zero
               unreplaced {{VAULT_*}} markers, runs full smoke tests, spot-
               checks Obsidian wikilinks, re-enables cron, and verifies the
               next tick fires cleanly. Any failure halts the sequence,
               prints a ===== FAILURE ===== banner, and does NOT auto-resume
               cron (operator must acknowledge).

See the contract for the full invariants list:
  kitty-specs/026-vault-path-registry-and-folder-renumber/contracts/deploy-wrapper-contract.md
EOF
}

log() {
  # Step-level narration on stdout
  printf '[%s] %s\n' "${SCRIPT_NAME}" "$*"
}

warn() {
  printf '[%s] WARN: %s\n' "${SCRIPT_NAME}" "$*" >&2
}

err() {
  printf '[%s] ERROR: %s\n' "${SCRIPT_NAME}" "$*" >&2
}

fail_post_rename() {
  # Loud failure banner for post-rename mode. Does NOT resume cron.
  local reason="$1"
  local cron_state="${2:-unknown}"
  printf '\n' >&2
  printf '===== FAILURE =====\n' >&2
  printf '===== FAILURE =====\n' >&2
  printf '===== FAILURE =====\n' >&2
  printf '\n' >&2
  printf 'deploy-f026.sh post-rename mode halted with an error.\n' >&2
  printf '\n' >&2
  printf 'Reason: %s\n' "$reason" >&2
  printf 'Cron state (felix-admin-capture on office2): %s\n' "$cron_state" >&2
  printf '\n' >&2
  printf 'This script will NOT auto-resume the cron on a failure path.\n' >&2
  printf 'Operator action required:\n' >&2
  printf '  1. Review the failure reason above\n' >&2
  printf '  2. Consult the WP05 rollback section:\n' >&2
  printf '     kitty-specs/026-vault-path-registry-and-folder-renumber/tasks/WP05-*.md\n' >&2
  printf '  3. Decide whether to roll back or advance manually\n' >&2
  printf '  4. Re-enable the cron via ssh office2-claude after remediation\n' >&2
  printf '\n' >&2
  printf '===== FAILURE =====\n' >&2
  printf '===== FAILURE =====\n' >&2
  printf '===== FAILURE =====\n' >&2
  exit 1
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --dry-run)
      APPLY=0
      shift
      ;;
    --apply)
      APPLY=1
      shift
      ;;
    --mode)
      if [[ $# -lt 2 ]]; then
        err "--mode requires an argument (pre-rename | post-rename)"
        exit 2
      fi
      MODE="$2"
      shift 2
      ;;
    --mode=*)
      MODE="${1#--mode=}"
      shift
      ;;
    --backup-confirmed)
      BACKUP_CONFIRMED=1
      shift
      ;;
    --skip-smoke)
      SKIP_SMOKE=1
      shift
      ;;
    --skip-cron)
      SKIP_CRON=1
      shift
      ;;
    *)
      err "Unknown argument: $1"
      err "Run '${SCRIPT_NAME} --help' for usage."
      exit 2
      ;;
  esac
done

# ---------------------------------------------------------------------------
# Argument validation
# ---------------------------------------------------------------------------
if [[ "$APPLY" -eq 1 ]]; then
  if [[ -z "$MODE" ]]; then
    err "--apply requires --mode <pre-rename|post-rename>"
    err "Run '${SCRIPT_NAME} --help' for usage."
    exit 2
  fi
fi

if [[ -n "$MODE" && "$MODE" != "pre-rename" && "$MODE" != "post-rename" ]]; then
  err "Invalid --mode value: '${MODE}'. Must be 'pre-rename' or 'post-rename'."
  exit 2
fi

if [[ "$SKIP_SMOKE" -eq 1 ]]; then
  warn "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
  warn "!! --skip-smoke is set. SMOKE TESTS WILL BE SKIPPED.          !!"
  warn "!! This flag exists only for debugging. Never use in normal   !!"
  warn "!! operation. Verification is a mandatory contract invariant. !!"
  warn "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
fi

if [[ "$SKIP_CRON" -eq 1 ]]; then
  warn "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
  warn "!! --skip-cron is set. CRON PAUSE/RESUME WILL BE SKIPPED.     !!"
  warn "!! This flag exists only for debugging. Never use in normal   !!"
  warn "!! operation. Cron safety is a mandatory contract invariant.  !!"
  warn "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
fi

# ---------------------------------------------------------------------------
# Configuration (paths used below)
# ---------------------------------------------------------------------------
DEPLOY_PY="${REPO_ROOT}/scripts/vault/deploy.py"
PATHS_JSON="${REPO_ROOT}/scripts/vault/paths.json"
TARGETS_JSON="${REPO_ROOT}/scripts/vault/targets.json"

# Stale literals to grep for in hygiene check (post-rename)
STALE_LITERALS='00-Inbox\|01-Constitution\|02-Growth\|03-Health\|04-Business\|05-Finance\|06-Journal\|07-Resources\|00-System'

# Directories to search in the repo-wide stale-literal check
STALE_SEARCH_ROOTS=(
  "${REPO_ROOT}/scripts"
  "${REPO_ROOT}/ai-agents"
  "${REPO_ROOT}/CLAUDE.md"
)

# Office2 paths for the unreplaced-marker sweep
OFFICE2_DEPLOY_ROOT="/data/services/openclaw"

# ---------------------------------------------------------------------------
# Common dispatch
# ---------------------------------------------------------------------------
log "Repo root:     ${REPO_ROOT}"
log "Deploy helper: ${DEPLOY_PY}"
log "Apply flag:    $( [[ $APPLY -eq 1 ]] && echo YES || echo NO )"
log "Mode:          ${MODE:-<none>}"
log "Skip smoke:    $( [[ $SKIP_SMOKE -eq 1 ]] && echo YES || echo NO )"
log "Skip cron:     $( [[ $SKIP_CRON -eq 1 ]] && echo YES || echo NO )"
log ""

# Default (no --apply): dry-run preview
if [[ "$APPLY" -ne 1 ]]; then
  log "=== DRY RUN ==="
  log "No changes will be made."
  log ""
  log "Planned action: invoke scripts/vault/deploy.py in dry-run mode."
  log ""
  if [[ -z "$MODE" ]]; then
    log "No --mode specified — would default to showing deploy.py's dry-run output."
  else
    log "Mode '${MODE}' — would run the ${MODE} sequence on --apply."
  fi
  log ""
  log "Invoking: python3 ${DEPLOY_PY}"
  if [[ ! -f "$DEPLOY_PY" ]]; then
    err "deploy.py not found at ${DEPLOY_PY}"
    exit 1
  fi
  # deploy.py dry-run may exit non-zero if .tmpl sources are missing (WP02
  # hasn't run yet). In the WP01 state this is expected — we tolerate the
  # non-zero exit by displaying the output but returning 0 ourselves so the
  # wrapper's own dry-run path stays safe per contract acceptance check.
  set +e
  python3 "$DEPLOY_PY"
  dry_rc=$?
  set -e
  if [[ $dry_rc -ne 0 ]]; then
    warn "deploy.py dry-run returned non-zero (${dry_rc}). This is expected"
    warn "at the WP01/WP02 boundary if .tmpl sources do not yet exist."
  fi
  log ""
  log "Dry run complete. No side effects."
  exit 0
fi

# ---------------------------------------------------------------------------
# Pre-rename mode (WP04)
# ---------------------------------------------------------------------------
run_deploy_apply() {
  log "Running: python3 ${DEPLOY_PY} --apply"
  if ! python3 "$DEPLOY_PY" --apply; then
    return 1
  fi
  return 0
}

smoke_test_capture() {
  log "Smoke test: felix-admin-capture"
  if [[ "$SKIP_SMOKE" -eq 1 ]]; then
    warn "Skipping felix-admin-capture smoke test (--skip-smoke)"
    return 0
  fi
  ssh office2-claude 'openclaw agent --agent felix-admin-capture \
    --message '"'"'{"action": "smoke_test", "dry_run": true}'"'"' \
    --json --timeout 120'
}

smoke_test_tasker() {
  log "Smoke test: felix-admin-tasker"
  if [[ "$SKIP_SMOKE" -eq 1 ]]; then
    warn "Skipping felix-admin-tasker smoke test (--skip-smoke)"
    return 0
  fi
  ssh office2-claude 'openclaw agent --agent felix-admin-tasker \
    --message '"'"'{"action": "smoke_test", "dry_run": true}'"'"' \
    --json --timeout 120'
}

if [[ "$MODE" == "pre-rename" ]]; then
  log "=== PRE-RENAME DEPLOY (WP04) ==="
  log ""
  log "This mode deploys resolved files against the CURRENT registry."
  log "Cron is NOT touched — this is a pure refactor deploy."
  log ""

  log "Step 1/3: Apply deploy.py"
  if ! run_deploy_apply; then
    err "deploy.py --apply failed. Aborting."
    exit 1
  fi

  log ""
  log "Step 2/3: Smoke-test felix-admin-capture"
  if ! smoke_test_capture; then
    err "felix-admin-capture smoke test failed."
    exit 1
  fi

  log ""
  log "Step 3/3: Smoke-test felix-admin-tasker"
  if ! smoke_test_tasker; then
    err "felix-admin-tasker smoke test failed."
    exit 1
  fi

  log ""
  log "Pre-rename deploy complete. Capture the smoke-test output above and"
  log "diff it against the pre-deploy baseline per WP04's fidelity check."
  exit 0
fi

# ---------------------------------------------------------------------------
# Post-rename mode (WP05) — the risky window
# ---------------------------------------------------------------------------
cron_paused=0
cron_state_text="unknown"

pause_capture_cron() {
  log "Step: Pausing felix-admin-capture cron on office2"
  if [[ "$SKIP_CRON" -eq 1 ]]; then
    warn "Skipping cron pause (--skip-cron)"
    cron_state_text="UNKNOWN (--skip-cron set)"
    return 0
  fi
  # Comment out the felix-admin-capture cron entry. The exact mechanism may
  # vary depending on openclaw's cron interface — use a disable verb if
  # available, otherwise edit crontab in place.
  if ! ssh office2-claude 'openclaw cron disable --name inbox-processing' 2>/dev/null; then
    # Fallback: edit crontab directly
    log "  openclaw cron disable unavailable, falling back to crontab edit"
    ssh office2-claude 'crontab -l | sed "s|^\([^#].*felix-admin-capture\)|#F026-PAUSED \1|" | crontab -'
  fi
  log "  Verifying pause state..."
  if ssh office2-claude 'crontab -l' | grep -E '^[^#].*felix-admin-capture' >/dev/null 2>&1; then
    err "  Failed to verify cron pause — active felix-admin-capture entry still present"
    cron_state_text="FAILED TO PAUSE — still active"
    return 1
  fi
  cron_paused=1
  cron_state_text="PAUSED"
  log "  Cron paused."
  return 0
}

resume_capture_cron() {
  log "Step: Resuming felix-admin-capture cron on office2"
  if [[ "$SKIP_CRON" -eq 1 ]]; then
    warn "Skipping cron resume (--skip-cron)"
    return 0
  fi
  if ! ssh office2-claude 'openclaw cron enable --name inbox-processing' 2>/dev/null; then
    log "  openclaw cron enable unavailable, falling back to crontab edit"
    ssh office2-claude 'crontab -l | sed "s|^#F026-PAUSED ||" | crontab -'
  fi
  log "  Verifying resume state..."
  if ssh office2-claude 'crontab -l' | grep -E '^[^#].*felix-admin-capture' >/dev/null 2>&1; then
    cron_paused=0
    cron_state_text="RESUMED"
    log "  Cron resumed."
    return 0
  fi
  cron_state_text="FAILED TO RESUME — no active entry found"
  return 1
}

verify_stale_literals() {
  log "Step: Scanning repo for stale vault folder literals"
  # Exclusions:
  #   - .tmpl sources (the template layer; literals there are intentional)
  #   - _private/ boundary references (hardcoded per constitution)
  #   - scripts/vault/paths.json (the registry data file itself)
  #   - scripts/vault/README.md (docs that quote example literals)
  #   - scripts/deploy/deploy-f026.sh (this wrapper's own STALE_LITERALS pattern
  #     variable is a self-reference; exclude to avoid false positive)
  local hits
  hits=$(grep -rn "$STALE_LITERALS" \
    --include="*.md" --include="*.json" --include="*.py" --include="*.sh" \
    "${STALE_SEARCH_ROOTS[@]}" 2>/dev/null \
    | grep -v '\.tmpl:' \
    | grep -v '_private/' \
    | grep -v 'scripts/vault/paths.json:' \
    | grep -v 'scripts/vault/README.md:' \
    | grep -v 'scripts/deploy/deploy-f026.sh:' \
    || true)
  if [[ -n "$hits" ]]; then
    err "  Stale literal hits found:"
    printf '%s\n' "$hits" >&2
    return 1
  fi
  log "  No stale literals detected."
  return 0
}

verify_unreplaced_markers_repo() {
  log "Step: Scanning repo for unreplaced {{VAULT_*}} markers in deployed files"
  local hits
  hits=$(grep -rn '{{VAULT_' \
    --include="*.md" --include="*.json" --include="*.py" --include="*.sh" \
    "${STALE_SEARCH_ROOTS[@]}" 2>/dev/null \
    | grep -v '\.tmpl:' \
    || true)
  if [[ -n "$hits" ]]; then
    err "  Unreplaced marker hits found in repo:"
    printf '%s\n' "$hits" >&2
    return 1
  fi
  log "  No unreplaced markers in repo deployed files."
  return 0
}

verify_unreplaced_markers_office2() {
  log "Step: Scanning office2 ${OFFICE2_DEPLOY_ROOT} for unreplaced {{VAULT_*}} markers"
  local hits
  hits=$(ssh office2-claude "grep -rn '{{VAULT_' ${OFFICE2_DEPLOY_ROOT} 2>/dev/null" || true)
  if [[ -n "$hits" ]]; then
    err "  Unreplaced marker hits found on office2:"
    printf '%s\n' "$hits" >&2
    return 1
  fi
  log "  No unreplaced markers on office2."
  return 0
}

verify_wikilinks() {
  log "Step: Obsidian wikilink integrity check"
  # No programmatic Obsidian API is available from this environment; the
  # intended mechanism is a spot-check by the operator against Obsidian's
  # "Unresolved links" report. We emit a checkpoint line the operator must
  # acknowledge in their runbook; this does not fail the script
  # automatically because there is no reliable programmatic signal.
  log "  MANUAL CONFIRM REQUIRED:"
  log "    1. Open Obsidian on the Mac"
  log "    2. Check the 'Unresolved links' pane"
  log "    3. Confirm zero NEW entries attributable to this mission"
  log "    4. Spot-check 3-5 known notes' wikilinks resolve"
  log "  If any check fails, abort the cron resume and roll back."
  log "  (This step is advisory in the script; the operator is the gate.)"
  return 0
}

verify_cron_fires() {
  log "Step: Verifying felix-admin-capture cron fires cleanly post-resume"
  if [[ "$SKIP_CRON" -eq 1 ]]; then
    warn "Skipping cron fire verification (--skip-cron)"
    return 0
  fi
  # Trigger a one-shot run rather than waiting for the natural tick.
  if ! ssh office2-claude 'openclaw agent --agent felix-admin-capture \
    --message '"'"'{"action": "process_inbox", "dry_run": false}'"'"' \
    --json --timeout 300'; then
    err "  One-shot cron fire invocation failed."
    return 1
  fi
  log "  One-shot cron fire completed cleanly."
  return 0
}

if [[ "$MODE" == "post-rename" ]]; then
  log "=== POST-RENAME DEPLOY (WP05) ==="
  log ""
  log "This is the risky window. On any failure the script halts with a"
  log "loud banner and does NOT auto-resume cron."
  log ""

  # Step 1: Tier 2 backup pre-flight
  log "Step 1/10: Tier 2 backup verification"
  if [[ "$BACKUP_CONFIRMED" -ne 1 ]]; then
    err "  --backup-confirmed not provided."
    err "  Per the pre-flight checklist, confirm a Restic backup is <=24h"
    err "  old via docs/runbooks/governance/pre-flight-checklist.md, then"
    err "  re-run with --backup-confirmed."
    exit 1
  fi
  log "  Backup acknowledged by operator (--backup-confirmed)."

  # Step 2: pause cron
  log ""
  log "Step 2/10: Pause felix-admin-capture cron"
  if ! pause_capture_cron; then
    fail_post_rename "Failed to pause felix-admin-capture cron." "$cron_state_text"
  fi

  # Step 3: deploy
  log ""
  log "Step 3/10: Run deploy.py --apply"
  if ! run_deploy_apply; then
    fail_post_rename "deploy.py --apply failed." "$cron_state_text"
  fi

  # Step 4: stale-literal grep
  log ""
  log "Step 4/10: Repo-wide stale literal sweep"
  if ! verify_stale_literals; then
    fail_post_rename "Stale vault folder literals found in repo." "$cron_state_text"
  fi

  # Step 5: unreplaced-marker grep
  log ""
  log "Step 5/10: Unreplaced {{VAULT_*}} marker sweep"
  if ! verify_unreplaced_markers_repo; then
    fail_post_rename "Unreplaced {{VAULT_*}} markers found in repo deployed files." "$cron_state_text"
  fi
  if ! verify_unreplaced_markers_office2; then
    fail_post_rename "Unreplaced {{VAULT_*}} markers found on office2." "$cron_state_text"
  fi

  # Step 6: smoke-test felix-admin-capture
  log ""
  log "Step 6/10: Smoke-test felix-admin-capture"
  if ! smoke_test_capture; then
    fail_post_rename "felix-admin-capture smoke test failed." "$cron_state_text"
  fi

  # Step 7: smoke-test felix-admin-tasker
  log ""
  log "Step 7/10: Smoke-test felix-admin-tasker"
  if ! smoke_test_tasker; then
    fail_post_rename "felix-admin-tasker smoke test failed." "$cron_state_text"
  fi

  # Step 8: wikilink integrity
  log ""
  log "Step 8/10: Obsidian wikilink integrity (manual-confirm)"
  if ! verify_wikilinks; then
    fail_post_rename "Wikilink integrity check failed." "$cron_state_text"
  fi

  # Step 9: re-enable cron
  log ""
  log "Step 9/10: Resume felix-admin-capture cron"
  if ! resume_capture_cron; then
    fail_post_rename "Failed to resume felix-admin-capture cron." "$cron_state_text"
  fi

  # Step 10: verify cron fires
  log ""
  log "Step 10/10: Verify cron fires cleanly"
  if ! verify_cron_fires; then
    fail_post_rename "Post-resume cron fire verification failed." "$cron_state_text"
  fi

  log ""
  log "=== POST-RENAME DEPLOY COMPLETE ==="
  log "All 10 steps passed. Cron state: ${cron_state_text}."
  log "Operator: review WP05 exit criteria in"
  log "  kitty-specs/026-vault-path-registry-and-folder-renumber/contracts/verification-contract.md"
  exit 0
fi

# ---------------------------------------------------------------------------
# Should not reach here
# ---------------------------------------------------------------------------
err "Unreachable: mode dispatch fell through. This is a bug."
exit 1
