#!/usr/bin/env bash
set -euo pipefail

# deploy-149.sh — Mission 027 inbox pre-scan helper deploy wrapper
#
# Mission: 027-inbox-pre-scan-helper
# Issue:   kentonium3/kg-automation#149
# Contract: kitty-specs/027-inbox-pre-scan-helper/plan.md "Deploy Wrapper Contract"
#
# One-shot deploy that pushes three things to office2 in a single safe
# sequence:
#   (1) the inbox pre-scan helper (scripts/inbox/prescan.py)
#   (2) the updated felix-admin-capture agent workspace files
#   (3) the 4 inbox-* openclaw cron payload messages
#
# Modes:
#   --dry-run  read-only preview (pre-flight + probe + print intent)
#   --apply    execute the deploy
#
# Invariants:
#   - Halt on any step failure. No silent fallbacks.
#   - NEVER touches the system crontab. All cron edits go through
#     `openclaw cron edit`, `openclaw cron list`, `openclaw cron run`,
#     `openclaw cron runs`. (See closed issue #162.)
#   - Cron UUIDs are resolved at runtime from `openclaw cron list --json`;
#     none are hardcoded in this script.
#   - On failure the wrapper prints manual rollback instructions. It does
#     NOT auto-rollback — operator judgement is the rollback mechanism.
#   - This mission does NOT disable/recreate any cron jobs — it only edits
#     payload.message. Therefore no pause/resume logic is needed.

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SCRIPT_NAME="$(basename "$0")"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

SSH_HOST="office2-claude"
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=10)

# Helper (WP01) — repo source and remote destination
HELPER_SRC_DIR="${REPO_ROOT}/scripts/inbox/"
HELPER_SRC_FILE="${REPO_ROOT}/scripts/inbox/prescan.py"
REMOTE_HELPER_DIR="/home/claude/kg-automation/scripts/inbox/"
REMOTE_HELPER_PATH="/home/claude/kg-automation/scripts/inbox/prescan.py"

# Vault registry sibling directory — MUST also be rsynced because the helper's
# _default_registry_path() resolves to ${REMOTE_HELPER_DIR}../vault/paths.json
# (see scripts/inbox/prescan.py). Without this, Step 3 --self-check fails.
VAULT_SRC_DIR="${REPO_ROOT}/scripts/vault/"
REMOTE_VAULT_DIR="/home/claude/kg-automation/scripts/vault/"

# Agent workspace (WP02) — repo source (rendered) and remote destination
#
# The destination is the openclaw agent's `workspace` path per
# /home/claude/.openclaw/openclaw.json. Do NOT confuse this with
# /home/claude/.openclaw/agents/felix-admin-capture/ (which is openclaw's
# own agent state directory). openclaw reads the agent's standing-orders
# files (AGENTS.md, SOUL.md, etc.) from the `workspace` path.
AGENT_SRC_DIR="${REPO_ROOT}/scripts/openclaw/agents/felix-admin-capture/"
REMOTE_AGENT_WORKSPACE="/data/services/openclaw/inbox-agent/"
AGENT_DEPLOY_FILES=(AGENTS.md USER.md TOOLS.md IDENTITY.md SOUL.md)

# Vault registry (used by deploy.py to render .tmpl -> .md)
DEPLOY_PY="${REPO_ROOT}/scripts/vault/deploy.py"
PATHS_JSON="${REPO_ROOT}/scripts/vault/paths.json"

# 4 inbox cron names — UUIDs are resolved at runtime, never hardcoded
INBOX_CRON_NAMES=(inbox-7am inbox-noon inbox-5pm inbox-10pm)
SMOKE_CRON_NAME="inbox-noon"

# New cron payload message (single source of truth)
NEW_CRON_MESSAGE="Process the inbox now. Begin with your Step 1 pre-scan per your standing orders. If the helper reports no unprocessed files, reply with IDLE only. If the helper returns unprocessed paths, process each file per your routing rules. If the helper exits non-zero, report its error and stop."

# Smoke test polling
SMOKE_TIMEOUT_SEC=60
SMOKE_POLL_INTERVAL_SEC=5

TOTAL_STEPS=8

# ---------------------------------------------------------------------------
# Mode flags (parsed below)
# ---------------------------------------------------------------------------
APPLY=0
DRY_RUN=0
BACKUP_CONFIRMED=0  # operator ack; skips inline Restic query (see Step 1f)

# ---------------------------------------------------------------------------
# State tracking (used by ROLLBACK_INSTRUCTIONS on ERR)
# ---------------------------------------------------------------------------
LAST_STEP="init"
LAST_STEP_NUM=0
HELPER_COPIED=0
WORKSPACE_COPIED=0
CRONS_EDITED=()  # uuid:old_message pairs for crons that were successfully edited

# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------
log() { printf '[%s] %s\n' "${SCRIPT_NAME}" "$*"; }
warn() { printf '[%s] WARN: %s\n' "${SCRIPT_NAME}" "$*" >&2; }
err() { printf '[%s] ERROR: %s\n' "${SCRIPT_NAME}" "$*" >&2; }

STEP() {
  local num="$1"
  local desc="$2"
  LAST_STEP_NUM="$num"
  LAST_STEP="$desc"
  printf '\n' >&2
  printf '[%s] ====================================================================\n' "${SCRIPT_NAME}" >&2
  printf '[%s] Step %d/%d: %s\n' "${SCRIPT_NAME}" "$num" "$TOTAL_STEPS" "$desc" >&2
  printf '[%s] ====================================================================\n' "${SCRIPT_NAME}" >&2
}

HALT() {
  err "$*"
  err "Halting at Step ${LAST_STEP_NUM}/${TOTAL_STEPS}: ${LAST_STEP}"
  exit 1
}

usage() {
  cat <<EOF
${SCRIPT_NAME} — Mission 027 inbox pre-scan helper deploy wrapper

Usage:
  ${SCRIPT_NAME} --dry-run              Show planned actions only; safe read-only preview.
  ${SCRIPT_NAME} --apply                Execute the deploy against ${SSH_HOST}.
  ${SCRIPT_NAME} --apply --backup-confirmed
                                        Skip the inline Restic query; operator
                                        attests a <=24h snapshot exists (see
                                        docs/runbooks/governance/pre-flight-checklist.md).
  ${SCRIPT_NAME} -h|--help              Print this message.

Description:
  Pushes scripts/inbox/prescan.py and the rendered felix-admin-capture agent
  workspace to office2, then rewrites the 4 inbox-* openclaw cron payload
  messages via 'openclaw cron edit'. Halts on any step failure. Prints
  manual rollback instructions on error; does NOT auto-rollback.

Invariants:
  - Never touches the system crontab (closed issue #162).
  - Cron UUIDs resolved at runtime via 'openclaw cron list --json'.
  - 8 ordered steps; each must succeed before the next.
EOF
}

# ---------------------------------------------------------------------------
# Argument parsing (mutually exclusive --dry-run / --apply; default = usage)
# ---------------------------------------------------------------------------
if [[ $# -eq 0 ]]; then
  usage
  exit 1
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --apply)
      APPLY=1
      shift
      ;;
    --backup-confirmed)
      BACKUP_CONFIRMED=1
      shift
      ;;
    *)
      err "Unknown argument: $1"
      usage >&2
      exit 2
      ;;
  esac
done

if [[ "$DRY_RUN" -eq 1 && "$APPLY" -eq 1 ]]; then
  err "--dry-run and --apply are mutually exclusive."
  exit 2
fi
if [[ "$DRY_RUN" -eq 0 && "$APPLY" -eq 0 ]]; then
  usage
  exit 1
fi

MODE_LABEL="DRY-RUN"
[[ "$APPLY" -eq 1 ]] && MODE_LABEL="APPLY"

# ---------------------------------------------------------------------------
# Rollback instructions (printed on any ERR via trap below)
# ---------------------------------------------------------------------------
ROLLBACK_INSTRUCTIONS() {
  local rc=$?
  # Avoid re-entry on errors inside this function itself
  trap - ERR EXIT
  printf '\n' >&2
  printf '===== DEPLOY-149 FAILED =====\n' >&2
  printf 'Failed at Step %d/%d: %s\n' "$LAST_STEP_NUM" "$TOTAL_STEPS" "$LAST_STEP" >&2
  printf 'Exit code: %d\n' "$rc" >&2
  printf '\n' >&2
  printf 'Rollback is NOT automatic. Manual recovery recipe below.\n' >&2
  printf '\n' >&2

  if [[ "$HELPER_COPIED" -eq 1 ]]; then
    printf '- Step 2 (helper rsync) completed. To revert:\n' >&2
    printf '    ssh %s '"'"'rm -f %s'"'"'\n' "$SSH_HOST" "$REMOTE_HELPER_PATH" >&2
    printf '    (or restore the previous version via git on office2)\n' >&2
    printf '\n' >&2
  fi

  if [[ "$WORKSPACE_COPIED" -eq 1 ]]; then
    printf '- Step 4 (agent workspace rsync) completed. To revert:\n' >&2
    printf '    Restore the prior files at %s\n' "$REMOTE_AGENT_WORKSPACE" >&2
    printf '    Last-known-good copies live in git history; to recover:\n' >&2
    printf '      ssh %s '"'"'git -C /home/claude/kg-automation checkout HEAD -- scripts/openclaw/agents/felix-admin-capture/'"'"'\n' "$SSH_HOST" >&2
    printf '      then re-run the render+rsync manually.\n' >&2
    printf '\n' >&2
  fi

  if [[ "${#CRONS_EDITED[@]}" -gt 0 ]]; then
    printf '- Step 6 (cron edits) partially completed. Crons already re-written:\n' >&2
    local pair uuid old_msg
    for pair in "${CRONS_EDITED[@]}"; do
      uuid="${pair%%::*}"
      old_msg="${pair#*::}"
      printf '    ssh %s "openclaw cron edit %s --message %s"\n' "$SSH_HOST" "$uuid" "$(printf '%q' "$old_msg")" >&2
    done
    printf '  (Each cron above was edited by this run; re-apply the old message to revert.)\n' >&2
    printf '\n' >&2
  fi

  printf 'Rollback is NOT automatic. Review the commands above and apply them manually if needed.\n' >&2
  printf '===== END DEPLOY-149 FAILURE REPORT =====\n' >&2
  exit "$rc"
}

trap ROLLBACK_INSTRUCTIONS ERR

# ---------------------------------------------------------------------------
# Summary header
# ---------------------------------------------------------------------------
log "Mission:        027-inbox-pre-scan-helper"
log "Mode:           ${MODE_LABEL}"
log "Repo root:      ${REPO_ROOT}"
log "SSH host:       ${SSH_HOST}"
log "Helper target:  ${REMOTE_HELPER_PATH}"
log "Workspace tgt:  ${REMOTE_AGENT_WORKSPACE}"
log "Cron names:     ${INBOX_CRON_NAMES[*]}"
log "Backup ack:     $( [[ "$BACKUP_CONFIRMED" -eq 1 ]] && echo YES || echo NO )"

# ===========================================================================
# Step 1 — Pre-flight checks (all read-only; run in BOTH dry-run and apply)
# ===========================================================================
STEP 1 "Pre-flight checks"

# 1a. Helper source exists in repo
if [[ ! -f "$HELPER_SRC_FILE" ]]; then
  HALT "[FAIL] Helper source missing: ${HELPER_SRC_FILE}"
fi
log "[OK]   Helper source present: ${HELPER_SRC_FILE}"

# 1b. Agent workspace template sources exist in repo
for f in AGENTS.md.tmpl USER.md.tmpl TOOLS.md.tmpl IDENTITY.md SOUL.md; do
  if [[ ! -f "${AGENT_SRC_DIR}${f}" ]]; then
    HALT "[FAIL] Agent workspace source missing: ${AGENT_SRC_DIR}${f}"
  fi
  log "[OK]   Agent workspace source present: ${f}"
done

# 1c. Vault registry resolvable (JSON parse)
if ! python3 -c "import json,sys; json.load(open('${PATHS_JSON}'))" 2>/dev/null; then
  HALT "[FAIL] Vault registry not resolvable: ${PATHS_JSON}"
fi
log "[OK]   Vault registry resolvable: ${PATHS_JSON}"

# 1d. deploy.py exists (used for rendering .tmpl -> .md)
if [[ ! -f "$DEPLOY_PY" ]]; then
  HALT "[FAIL] Render helper missing: ${DEPLOY_PY}"
fi
log "[OK]   Render helper present: ${DEPLOY_PY}"

# 1e. office2 reachable via SSH (BatchMode avoids interactive passphrase prompt)
if ! ssh "${SSH_OPTS[@]}" "$SSH_HOST" true 2>/dev/null; then
  HALT "[FAIL] Cannot reach ${SSH_HOST} via SSH. Check Tailscale / SSH key / agent."
fi
log "[OK]   ${SSH_HOST} reachable via SSH"

# 1f. Restic backup age <=24h (Tier 2 pre-flight)
#
# Note: the 'claude' user on office2 does not have RESTIC_REPOSITORY set in
# its environment (the Restic backup cron runs under the kgale user). If the
# inline query fails with "Please specify repository", we fall back to
# requiring the operator to re-run with --backup-confirmed after manually
# verifying a <=24h snapshot per the pre-flight checklist. This keeps Tier 2
# enforcement honest without silently swallowing the check.
if [[ "$BACKUP_CONFIRMED" -eq 1 ]]; then
  warn "[SKIP] Restic inline query skipped (--backup-confirmed). Operator attests a <=24h snapshot exists."
  log "[OK]   Tier 2 pre-flight acknowledged by operator."
  restic_check_pass=1
else
  restic_check_pass=0
fi

if [[ "$restic_check_pass" -ne 1 ]]; then
log "[..]   Querying latest Restic snapshot on ${SSH_HOST}..."
restic_combined="$(ssh "${SSH_OPTS[@]}" "$SSH_HOST" 'restic snapshots --latest 1 --json' 2>&1; echo "RC=$?")"
restic_rc="${restic_combined##*RC=}"
restic_json="${restic_combined%RC=*}"
if [[ $restic_rc -ne 0 ]]; then
  err "[FAIL] Restic query failed (rc=${restic_rc}): ${restic_json}"
  err "       The 'claude' user likely does not have RESTIC_REPOSITORY configured."
  err "       Verify a <=24h snapshot manually per"
  err "       docs/runbooks/governance/pre-flight-checklist.md, then re-run with --backup-confirmed."
  HALT "Tier 2 pre-flight failed: Restic backup age could not be verified."
fi
restic_check="$(
  REPLY_JSON="$restic_json" python3 - <<'PY'
import json, os, sys, datetime
raw = os.environ.get("REPLY_JSON", "")
try:
    snaps = json.loads(raw)
except Exception as e:
    print(f"parse-error: {e}", flush=True)
    sys.exit(2)
if not isinstance(snaps, list) or not snaps:
    print("no-snapshots", flush=True)
    sys.exit(3)
ts = snaps[-1].get("time")
if not ts:
    print("no-timestamp", flush=True)
    sys.exit(4)
# Restic timestamps look like: 2026-04-11T12:34:56.789012345Z or +00:00
ts_clean = ts.replace("Z", "+00:00")
# Trim sub-microsecond fractional seconds if present
if "." in ts_clean and "+" in ts_clean:
    head, tz = ts_clean.split("+", 1)
    if "." in head:
        base, frac = head.split(".", 1)
        frac = frac[:6]
        head = f"{base}.{frac}"
    ts_clean = f"{head}+{tz}"
try:
    snap_dt = datetime.datetime.fromisoformat(ts_clean)
except Exception as e:
    print(f"parse-ts-error: {e}", flush=True)
    sys.exit(5)
now = datetime.datetime.now(datetime.timezone.utc)
age_sec = (now - snap_dt).total_seconds()
age_h = age_sec / 3600.0
if age_sec > 86400:
    print(f"too-old: {age_h:.1f}h", flush=True)
    sys.exit(10)
print(f"ok: {age_h:.1f}h", flush=True)
PY
)" || {
  HALT "[FAIL] Tier 2 pre-flight failed (Restic age check): ${restic_check}. Run 'restic backup' before retrying."
}
log "[OK]   Restic snapshot age ${restic_check}"
fi  # restic_check_pass

log "Pre-flight complete."

# ===========================================================================
# Step 2 — Copy helper to office2
# ===========================================================================
STEP 2 "Copy helper (scripts/inbox/) and vault registry (scripts/vault/) to office2"

rsync_opts=(-avz --delete --exclude='__pycache__' --exclude='*.pyc')
if [[ "$APPLY" -eq 1 ]]; then
  log "Running: rsync ${rsync_opts[*]} ${HELPER_SRC_DIR} ${SSH_HOST}:${REMOTE_HELPER_DIR}"
  rsync "${rsync_opts[@]}" "${HELPER_SRC_DIR}" "${SSH_HOST}:${REMOTE_HELPER_DIR}"
  HELPER_COPIED=1
  log "[OK]   Helper rsynced."
  log "Running: rsync ${rsync_opts[*]} ${VAULT_SRC_DIR} ${SSH_HOST}:${REMOTE_VAULT_DIR}"
  rsync "${rsync_opts[@]}" "${VAULT_SRC_DIR}" "${SSH_HOST}:${REMOTE_VAULT_DIR}"
  log "[OK]   Vault registry rsynced."
else
  log "DRY-RUN: would run: rsync ${rsync_opts[*]} ${HELPER_SRC_DIR} ${SSH_HOST}:${REMOTE_HELPER_DIR}"
  log "DRY-RUN: probing rsync --dry-run for helper diff preview..."
  rsync "${rsync_opts[@]}" --dry-run "${HELPER_SRC_DIR}" "${SSH_HOST}:${REMOTE_HELPER_DIR}" || \
    warn "rsync dry-run probe returned non-zero; this is informational only"
  log "DRY-RUN: would run: rsync ${rsync_opts[*]} ${VAULT_SRC_DIR} ${SSH_HOST}:${REMOTE_VAULT_DIR}"
  log "DRY-RUN: probing rsync --dry-run for vault registry diff preview..."
  rsync "${rsync_opts[@]}" --dry-run "${VAULT_SRC_DIR}" "${SSH_HOST}:${REMOTE_VAULT_DIR}" || \
    warn "rsync dry-run probe returned non-zero; this is informational only"
fi

# ===========================================================================
# Step 3 — Verify helper via --self-check
# ===========================================================================
STEP 3 "Verify helper on office2 via --self-check"

# Safe to run in both modes: --self-check is read-only. Capture rc via a
# trailing echo inside the command substitution so the ERR trap doesn't fire
# on expected non-zero (e.g., helper not yet deployed in dry-run).
self_check_combined="$(ssh "${SSH_OPTS[@]}" "$SSH_HOST" "python3 ${REMOTE_HELPER_PATH} --self-check" 2>&1; echo "RC=$?")"
self_check_rc="${self_check_combined##*RC=}"
self_check_out="${self_check_combined%RC=*}"
if [[ "$APPLY" -eq 1 ]]; then
  if [[ $self_check_rc -ne 0 ]]; then
    HALT "[FAIL] Helper self-check failed (rc=${self_check_rc}): ${self_check_out}"
  fi
  if ! printf '%s' "$self_check_out" | python3 -c 'import json,sys; d=json.loads(sys.stdin.read().splitlines()[-1]); sys.exit(0 if d.get("self_check")=="ok" else 1)' 2>/dev/null; then
    HALT "[FAIL] Helper self-check output did not contain {\"self_check\":\"ok\"}: ${self_check_out}"
  fi
  log "[OK]   Helper self-check ok."
else
  if [[ $self_check_rc -eq 0 ]]; then
    log "DRY-RUN: remote helper self-check currently returns ok (informational)."
  else
    log "DRY-RUN: remote helper self-check currently returns rc=${self_check_rc} (expected if not yet deployed)."
  fi
fi

# ===========================================================================
# Step 4 — Render + copy agent workspace to office2
# ===========================================================================
STEP 4 "Render agent workspace templates and rsync to ${REMOTE_AGENT_WORKSPACE}"

# Render via scripts/vault/deploy.py. We pass --no-office2 so deploy.py
# only writes locally; this wrapper owns the rsync to the mission-149
# destination path (which differs from targets.json's mission-026 paths).
if [[ "$APPLY" -eq 1 ]]; then
  log "Rendering templates via: python3 ${DEPLOY_PY} --apply --no-office2"
  python3 "$DEPLOY_PY" --apply --no-office2
else
  log "DRY-RUN: would render via: python3 ${DEPLOY_PY} --apply --no-office2"
  log "DRY-RUN: running deploy.py in dry-run to surface any marker errors..."
  # deploy.py's own dry-run is safe (reads only)
  set +e
  python3 "$DEPLOY_PY" || warn "deploy.py dry-run returned non-zero (informational)"
  set -e
fi

# Verify all expected rendered files exist in repo before we try to rsync
for f in "${AGENT_DEPLOY_FILES[@]}"; do
  if [[ ! -f "${AGENT_SRC_DIR}${f}" ]]; then
    if [[ "$APPLY" -eq 1 ]]; then
      HALT "[FAIL] Rendered file missing after deploy.py: ${AGENT_SRC_DIR}${f}"
    else
      warn "DRY-RUN: rendered file not yet present: ${AGENT_SRC_DIR}${f} (informational)"
    fi
  fi
done

# rsync only the deploy files — exclude .tmpl sources and any stray artifacts.
ws_rsync_opts=(-avz --include='AGENTS.md' --include='USER.md' --include='TOOLS.md' --include='IDENTITY.md' --include='SOUL.md' --exclude='*')
if [[ "$APPLY" -eq 1 ]]; then
  log "Running: rsync ${ws_rsync_opts[*]} ${AGENT_SRC_DIR} ${SSH_HOST}:${REMOTE_AGENT_WORKSPACE}"
  rsync "${ws_rsync_opts[@]}" "${AGENT_SRC_DIR}" "${SSH_HOST}:${REMOTE_AGENT_WORKSPACE}"
  WORKSPACE_COPIED=1
  log "[OK]   Agent workspace rsynced."
else
  log "DRY-RUN: would run: rsync ${ws_rsync_opts[*]} ${AGENT_SRC_DIR} ${SSH_HOST}:${REMOTE_AGENT_WORKSPACE}"
  log "DRY-RUN: probing rsync --dry-run for diff preview..."
  rsync "${ws_rsync_opts[@]}" --dry-run "${AGENT_SRC_DIR}" "${SSH_HOST}:${REMOTE_AGENT_WORKSPACE}" 2>&1 || \
    warn "rsync dry-run probe returned non-zero; this is informational only"
fi

# ===========================================================================
# Step 5 — Verify agent workspace via md5sum match
# ===========================================================================
STEP 5 "Verify agent workspace via md5sum"

if [[ "$APPLY" -eq 1 ]]; then
  # Compute local md5s
  local_md5s=""
  for f in "${AGENT_DEPLOY_FILES[@]}"; do
    if [[ -f "${AGENT_SRC_DIR}${f}" ]]; then
      sum=$(md5sum "${AGENT_SRC_DIR}${f}" | awk '{print $1}')
      local_md5s="${local_md5s}${sum}  ${f}"$'\n'
    fi
  done
  # Compute remote md5s
  remote_md5s=$(ssh "${SSH_OPTS[@]}" "$SSH_HOST" "cd ${REMOTE_AGENT_WORKSPACE} && md5sum ${AGENT_DEPLOY_FILES[*]} 2>/dev/null | awk '{print \$1\"  \"\$2}'")
  # Compare set-wise (sorted)
  local_sorted=$(printf '%s' "$local_md5s" | sort)
  remote_sorted=$(printf '%s\n' "$remote_md5s" | sort)
  if [[ "$local_sorted" != "$remote_sorted" ]]; then
    err "[FAIL] md5 mismatch between local rendered files and remote deployed files."
    err "Local:"
    printf '%s\n' "$local_sorted" >&2
    err "Remote:"
    printf '%s\n' "$remote_sorted" >&2
    HALT "Agent workspace verification failed."
  fi
  log "[OK]   md5 match for ${#AGENT_DEPLOY_FILES[@]} workspace files."
else
  log "DRY-RUN: would md5sum local and remote copies of: ${AGENT_DEPLOY_FILES[*]}"
fi

# ===========================================================================
# Step 6 — Edit the 4 inbox-* cron payload messages
# ===========================================================================
STEP 6 "Edit inbox-* cron payloads via 'openclaw cron edit'"

# Resolve UUIDs at runtime via `openclaw cron list --json`. Never hardcoded.
log "Resolving cron UUIDs via 'openclaw cron list --json'..."
cron_list_combined="$(ssh "${SSH_OPTS[@]}" "$SSH_HOST" 'openclaw cron list --json' 2>&1; echo "RC=$?")"
cron_list_rc="${cron_list_combined##*RC=}"
cron_list_json="${cron_list_combined%RC=*}"
if [[ $cron_list_rc -ne 0 ]]; then
  HALT "[FAIL] 'openclaw cron list --json' failed (rc=${cron_list_rc}): ${cron_list_json}"
fi

# Parse out { name -> {uuid, message} } for the 4 names we care about.
resolved="$(
  CRON_JSON="$cron_list_json" CRON_NAMES="${INBOX_CRON_NAMES[*]}" python3 - <<'PY'
import json, os, sys
raw = os.environ.get("CRON_JSON", "")
names = os.environ.get("CRON_NAMES", "").split()
try:
    data = json.loads(raw)
except Exception as e:
    print(f"ERR parse: {e}", file=sys.stderr)
    sys.exit(2)

# openclaw cron list --json schema: either {"jobs":[...]} or a plain list
if isinstance(data, dict):
    jobs = data.get("jobs") or data.get("crons") or data.get("items") or []
elif isinstance(data, list):
    jobs = data
else:
    print("ERR: unexpected JSON shape", file=sys.stderr)
    sys.exit(3)

by_name = {}
for job in jobs:
    n = job.get("name") or job.get("id") or job.get("cron_name")
    if n:
        by_name[n] = job

missing = [n for n in names if n not in by_name]
if missing:
    print(f"ERR missing: {','.join(missing)}", file=sys.stderr)
    sys.exit(4)

# Emit "<name>\t<uuid>\t<current_message>" per line
for n in names:
    job = by_name[n]
    uuid = job.get("uuid") or job.get("id") or job.get("cron_id") or ""
    # message may live at payload.message, payload, or message
    msg = ""
    pl = job.get("payload")
    if isinstance(pl, dict):
        msg = pl.get("message", "") or ""
    elif isinstance(pl, str):
        msg = pl
    if not msg:
        msg = job.get("message", "") or ""
    # Flatten tabs/newlines for safe line-oriented emission
    msg_safe = msg.replace("\t", " ").replace("\n", " ")
    print(f"{n}\t{uuid}\t{msg_safe}")
PY
)" || HALT "[FAIL] Could not resolve cron UUIDs from openclaw cron list output."

if [[ -z "$resolved" ]]; then
  HALT "[FAIL] Empty UUID resolution output."
fi

log "Resolved cron UUIDs:"
while IFS=$'\t' read -r name uuid old_msg; do
  log "  ${name}: uuid=${uuid}"
done <<< "$resolved"

# Edit each cron
while IFS=$'\t' read -r name uuid old_msg; do
  if [[ -z "$uuid" ]]; then
    HALT "[FAIL] Resolved empty uuid for cron '${name}'."
  fi
  if [[ "$APPLY" -eq 1 ]]; then
    log "Editing cron ${name} (${uuid})..."
    # Pass the message as a single argv slot via ssh. Use printf %q to quote.
    remote_cmd=$(printf 'openclaw cron edit %q --message %q' "$uuid" "$NEW_CRON_MESSAGE")
    # ssh -n disables reading from stdin to prevent the while-read loop from
    # having its input consumed by ssh (which closes stdin for the remote cmd).
    if ! ssh -n "${SSH_OPTS[@]}" "$SSH_HOST" "$remote_cmd"; then
      HALT "[FAIL] openclaw cron edit failed for ${name} (${uuid}). Aborting with no fallback (system crontab is NOT used — see #162)."
    fi
    CRONS_EDITED+=("${uuid}::${old_msg}")
    log "[OK]   ${name} payload updated."
  else
    log "DRY-RUN: would edit ${name} (${uuid})"
    log "  current message: ${old_msg}"
    log "  new message:     ${NEW_CRON_MESSAGE}"
  fi
done <<< "$resolved"

# ===========================================================================
# Step 7 — Verify cron state (all 4 show the new message)
# ===========================================================================
STEP 7 "Verify all 4 inbox-* crons show the new payload message"

if [[ "$APPLY" -eq 1 ]]; then
  verify_combined="$(ssh "${SSH_OPTS[@]}" "$SSH_HOST" 'openclaw cron list --json' 2>&1; echo "RC=$?")"
  verify_rc="${verify_combined##*RC=}"
  verify_json="${verify_combined%RC=*}"
  if [[ $verify_rc -ne 0 ]]; then
    HALT "[FAIL] 'openclaw cron list --json' (verify) failed: ${verify_json}"
  fi

  verify_result="$(
    CRON_JSON="$verify_json" CRON_NAMES="${INBOX_CRON_NAMES[*]}" EXPECTED="$NEW_CRON_MESSAGE" python3 - <<'PY'
import json, os, sys
raw = os.environ.get("CRON_JSON", "")
names = os.environ.get("CRON_NAMES", "").split()
expected = os.environ.get("EXPECTED", "")
try:
    data = json.loads(raw)
except Exception as e:
    print(f"ERR parse: {e}")
    sys.exit(2)
if isinstance(data, dict):
    jobs = data.get("jobs") or data.get("crons") or data.get("items") or []
else:
    jobs = data if isinstance(data, list) else []
by_name = {}
for job in jobs:
    n = job.get("name") or job.get("id") or job.get("cron_name")
    if n:
        by_name[n] = job
mismatches = []
for n in names:
    if n not in by_name:
        mismatches.append(f"{n}: missing")
        continue
    job = by_name[n]
    pl = job.get("payload")
    msg = ""
    if isinstance(pl, dict):
        msg = pl.get("message", "") or ""
    elif isinstance(pl, str):
        msg = pl
    if not msg:
        msg = job.get("message", "") or ""
    if msg.strip() != expected.strip():
        mismatches.append(f"{n}: message does not match expected")
if mismatches:
    for m in mismatches:
        print(m)
    sys.exit(10)
print("all-match")
PY
  )" || HALT "[FAIL] Cron verification mismatch:\n${verify_result}"
  log "[OK]   All 4 inbox-* crons show the new payload message."
else
  log "DRY-RUN: would re-read 'openclaw cron list --json' and confirm all 4 crons show new message."
fi

# ===========================================================================
# Step 8 — Post-flight smoke test (trigger one cron, verify run + helper log)
# ===========================================================================
STEP 8 "Post-flight smoke test via 'openclaw cron run'"

if [[ "$APPLY" -ne 1 ]]; then
  log "DRY-RUN: skipping smoke test (it actually triggers an agent turn)."
  log ""
  log "===== DRY-RUN COMPLETE ====="
  log "No mutations were performed."
  # Clear the ERR trap for clean exit
  trap - ERR
  exit 0
fi

# Find the smoke cron UUID from the resolved map
smoke_uuid=""
while IFS=$'\t' read -r name uuid _rest; do
  if [[ "$name" == "$SMOKE_CRON_NAME" ]]; then
    smoke_uuid="$uuid"
  fi
done <<< "$resolved"
if [[ -z "$smoke_uuid" ]]; then
  HALT "[FAIL] Smoke cron '${SMOKE_CRON_NAME}' UUID not found in resolved map."
fi

log "Triggering: openclaw cron run ${smoke_uuid} (${SMOKE_CRON_NAME})"
run_combined="$(ssh "${SSH_OPTS[@]}" "$SSH_HOST" "openclaw cron run ${smoke_uuid}" 2>&1; echo "RC=$?")"
run_rc="${run_combined##*RC=}"
run_out="${run_combined%RC=*}"
if [[ $run_rc -ne 0 ]]; then
  HALT "[FAIL] 'openclaw cron run ${smoke_uuid}' failed (rc=${run_rc}): ${run_out}"
fi
log "[OK]   Cron run invoked. Polling for completion..."

# Poll openclaw cron runs <uuid> until we see status ok/error or timeout.
elapsed=0
final_status=""
while [[ $elapsed -lt $SMOKE_TIMEOUT_SEC ]]; do
  runs_combined="$(ssh -n "${SSH_OPTS[@]}" "$SSH_HOST" "openclaw cron runs --id ${smoke_uuid} --limit 5 2>&1 | head -30" 2>&1; echo "RC=$?")"
  runs_rc="${runs_combined##*RC=}"
  runs_out="${runs_combined%RC=*}"
  if [[ $runs_rc -eq 0 ]]; then
    if printf '%s' "$runs_out" | grep -Eqi 'status[^[:alnum:]]*(ok|success|done)'; then
      final_status="ok"
      break
    fi
    if printf '%s' "$runs_out" | grep -Eqi 'status[^[:alnum:]]*(error|failed|fail)'; then
      final_status="error"
      break
    fi
  fi
  sleep "$SMOKE_POLL_INTERVAL_SEC"
  elapsed=$((elapsed + SMOKE_POLL_INTERVAL_SEC))
done

if [[ -z "$final_status" ]]; then
  HALT "[FAIL] Smoke test timed out after ${SMOKE_TIMEOUT_SEC}s waiting for cron run completion. Last output:\n${runs_out:-<none>}"
fi
if [[ "$final_status" == "error" ]]; then
  HALT "[FAIL] Smoke test cron run reported error status. Last output:\n${runs_out}"
fi
log "[OK]   openclaw cron runs reports status=ok for the smoke run."

# Confirm the helper log file was written today.
log "Checking helper log file under /home/claude/second-brain/agents/logs/ ..."
log_combined="$(ssh "${SSH_OPTS[@]}" "$SSH_HOST" 'ls -t /home/claude/second-brain/agents/logs/inbox-prescan-*.md 2>/dev/null | head -1 | xargs -r tail -20' 2>&1; echo "RC=$?")"
log_rc="${log_combined##*RC=}"
log_tail="${log_combined%RC=*}"
if [[ $log_rc -ne 0 || -z "$log_tail" ]]; then
  HALT "[FAIL] Could not locate or read helper log file. rc=${log_rc} out=${log_tail}"
fi
log "[OK]   Helper log present (last 20 lines shown below):"
printf '%s\n' "$log_tail"

# ---------------------------------------------------------------------------
# Success
# ---------------------------------------------------------------------------
trap - ERR
printf '\n' >&2
log "===== DEPLOY-149 COMPLETE ====="
log "All 8 steps passed. Mission 027 deployed to ${SSH_HOST}."
exit 0
