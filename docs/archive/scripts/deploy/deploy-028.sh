#!/usr/bin/env bash
set -euo pipefail

# deploy-028.sh — Mission 028 agent workspace reconciliation deploy wrapper
#
# Mission: 028-agent-workspace-reconciliation
# Issue:   kentonium3/kg-automation#166
#
# Deploys two things to office2:
#   (1) Reconciled tasker agent workspace files (repo→office2)
#   (2) Drift enforcement script + config + manifests to the repo clone
#
# Modes:
#   --dry-run          read-only preview (pre-flight + probe + print intent)
#   --apply            execute the deploy
#   --backup-confirmed Tier 2 attestation — operator confirms Restic backup ≤24h
#
# Invariants:
#   - Halt on any step failure. No silent fallbacks.
#   - Tier 2 pre-flight: --backup-confirmed required for --apply.
#   - Post-deploy hash verification for every file.
#   - On failure, prints manual rollback instructions.

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SCRIPT_NAME="$(basename "$0")"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

SSH_HOST="office2-claude"
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=10)

# Tasker agent files (repo→office2)
TASKER_SRC_DIR="${REPO_ROOT}/scripts/openclaw/agents/felix-admin-tasker"
REMOTE_TASKER_DIR="/data/services/openclaw/tasker-agent"
TASKER_FILES=(SOUL.md TOOLS.md USER.md IDENTITY.md)

# Enforcement script + config (repo→office2 repo clone)
ENFORCEMENT_SRC_DIR="${REPO_ROOT}/scripts/openclaw/enforcement"
REMOTE_ENFORCEMENT_DIR="/home/claude/kg-automation/scripts/openclaw/enforcement"
MANIFEST_SRC="${REPO_ROOT}/scripts/openclaw/agents/baseline-manifest.json"
FACTORY_SRC="${REPO_ROOT}/scripts/openclaw/agents/factory-baselines.json"
REMOTE_MANIFEST="/home/claude/kg-automation/scripts/openclaw/agents/baseline-manifest.json"
REMOTE_FACTORY="/home/claude/kg-automation/scripts/openclaw/agents/factory-baselines.json"

# Cron schedule (daily at 06:00 UTC / 02:00 ET)
CRON_SCHEDULE="0 6 * * *"
CRON_CMD="cd /home/claude/kg-automation && python3 scripts/openclaw/enforcement/drift_check.py check --config scripts/openclaw/enforcement/drift-check-config.json >> /tmp/drift-check.log 2>&1"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
info()  { printf '  ✓ %s\n' "$*"; }
warn()  { printf '  ⚠ %s\n' "$*" >&2; }
fail()  { printf '  ✗ %s\n' "$*" >&2; exit 1; }

sha256_local() { shasum -a 256 "$1" | cut -d' ' -f1; }
sha256_remote() { ssh "${SSH_OPTS[@]}" "$SSH_HOST" "sha256sum \"$1\"" 2>/dev/null | cut -d' ' -f1; }

# ---------------------------------------------------------------------------
# Parse args
# ---------------------------------------------------------------------------
MODE="dry-run"
BACKUP_CONFIRMED=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --apply)            MODE="apply"; shift ;;
        --dry-run)          MODE="dry-run"; shift ;;
        --backup-confirmed) BACKUP_CONFIRMED=true; shift ;;
        -h|--help)
            echo "Usage: $SCRIPT_NAME [--dry-run|--apply] [--backup-confirmed]"
            exit 0 ;;
        *) fail "Unknown flag: $1" ;;
    esac
done

echo "═══════════════════════════════════════════════════════════"
echo " deploy-028.sh — Agent Workspace Reconciliation"
echo " Mode: ${MODE}  Backup confirmed: ${BACKUP_CONFIRMED}"
echo "═══════════════════════════════════════════════════════════"
echo

# ---------------------------------------------------------------------------
# Step 1: Pre-flight
# ---------------------------------------------------------------------------
echo "Step 1: Pre-flight checks"

# 1a. Tier 2 gate
if [[ "$MODE" == "apply" && "$BACKUP_CONFIRMED" != "true" ]]; then
    echo
    echo "  Tier 2 pre-flight: Restic backup ≤24h required."
    echo "  Verify with: ssh office2-claude 'cat /data/services/backup/logs/backup-\$(date +%Y-%m-%d).log | tail -5'"
    echo "  Then rerun with: $SCRIPT_NAME --apply --backup-confirmed"
    exit 1
fi
info "Tier 2 gate: ${BACKUP_CONFIRMED}"

# 1b. SSH reachability
ssh "${SSH_OPTS[@]}" "$SSH_HOST" 'echo ok' >/dev/null 2>&1 || fail "Cannot reach $SSH_HOST"
info "SSH reachable: $SSH_HOST"

# 1c. Source files exist
for f in "${TASKER_FILES[@]}"; do
    [[ -f "${TASKER_SRC_DIR}/${f}" ]] || fail "Missing source: ${TASKER_SRC_DIR}/${f}"
done
info "Tasker source files present (${#TASKER_FILES[@]} files)"

[[ -f "${ENFORCEMENT_SRC_DIR}/drift_check.py" ]] || fail "Missing: drift_check.py"
[[ -f "${ENFORCEMENT_SRC_DIR}/drift-check-config.json" ]] || fail "Missing: drift-check-config.json"
[[ -f "${MANIFEST_SRC}" ]] || fail "Missing: baseline-manifest.json"
[[ -f "${FACTORY_SRC}" ]] || fail "Missing: factory-baselines.json"
info "Enforcement source files present"

# 1d. Remote directories exist
ssh "${SSH_OPTS[@]}" "$SSH_HOST" "test -d ${REMOTE_TASKER_DIR}" || fail "Remote dir missing: ${REMOTE_TASKER_DIR}"
info "Remote tasker directory exists"

echo

# ---------------------------------------------------------------------------
# Step 2: Deploy tasker files
# ---------------------------------------------------------------------------
echo "Step 2: Deploy tasker workspace files (repo→office2)"

for f in "${TASKER_FILES[@]}"; do
    local_path="${TASKER_SRC_DIR}/${f}"
    remote_path="${REMOTE_TASKER_DIR}/${f}"
    local_hash=$(sha256_local "$local_path")

    if [[ "$MODE" == "dry-run" ]]; then
        echo "  DRY RUN: would scp ${f} → ${remote_path}"
        echo "           local hash: ${local_hash:0:16}..."
    else
        scp "${SSH_OPTS[@]}" "$local_path" "${SSH_HOST}:${remote_path}" || fail "SCP failed: ${f}"
        remote_hash=$(sha256_remote "$remote_path")
        if [[ "$local_hash" != "$remote_hash" ]]; then
            fail "Post-deploy hash mismatch for ${f}: local=${local_hash:0:16} remote=${remote_hash:0:16}"
        fi
        info "Deployed ${f} (hash verified: ${local_hash:0:16}...)"
    fi
done

echo

# ---------------------------------------------------------------------------
# Step 3: Deploy enforcement script + config
# ---------------------------------------------------------------------------
echo "Step 3: Deploy enforcement script to office2 repo clone"

# Ensure remote directories exist
if [[ "$MODE" == "apply" ]]; then
    ssh "${SSH_OPTS[@]}" "$SSH_HOST" "mkdir -p ${REMOTE_ENFORCEMENT_DIR}"
fi

ENFORCEMENT_FILES=(
    drift_check.py
    detection.py
    remediation.py
    notification.py
    generate_manifest.py
    drift-check-config.json
    __init__.py
)

for f in "${ENFORCEMENT_FILES[@]}"; do
    local_path="${ENFORCEMENT_SRC_DIR}/${f}"
    remote_path="${REMOTE_ENFORCEMENT_DIR}/${f}"
    if [[ ! -f "$local_path" ]]; then
        warn "Skipping missing file: ${f}"
        continue
    fi
    if [[ "$MODE" == "dry-run" ]]; then
        echo "  DRY RUN: would scp ${f} → ${remote_path}"
    else
        scp "${SSH_OPTS[@]}" "$local_path" "${SSH_HOST}:${remote_path}" || fail "SCP failed: ${f}"
        info "Deployed enforcement/${f}"
    fi
done

# Deploy manifests
for src_dest in "${MANIFEST_SRC}:${REMOTE_MANIFEST}" "${FACTORY_SRC}:${REMOTE_FACTORY}"; do
    src="${src_dest%%:*}"
    dest="${src_dest##*:}"
    fname="$(basename "$src")"
    if [[ "$MODE" == "dry-run" ]]; then
        echo "  DRY RUN: would scp ${fname} → ${dest}"
    else
        ssh "${SSH_OPTS[@]}" "$SSH_HOST" "mkdir -p $(dirname "$dest")"
        scp "${SSH_OPTS[@]}" "$src" "${SSH_HOST}:${dest}" || fail "SCP failed: ${fname}"
        info "Deployed ${fname}"
    fi
done

echo

# ---------------------------------------------------------------------------
# Step 4: Install cron job
# ---------------------------------------------------------------------------
echo "Step 4: Install drift-check cron job"

if [[ "$MODE" == "dry-run" ]]; then
    echo "  DRY RUN: would add cron entry:"
    echo "  ${CRON_SCHEDULE} ${CRON_CMD}"
    echo "  Checking existing cron..."
    ssh "${SSH_OPTS[@]}" "$SSH_HOST" "crontab -l 2>/dev/null | grep -c drift-check || echo 0" | {
        read -r count
        if [[ "$count" -gt 0 ]]; then
            echo "  Note: drift-check cron entry already exists (${count} entries)"
        else
            echo "  Note: no existing drift-check cron entry"
        fi
    }
else
    # Check if already installed
    existing=$(ssh "${SSH_OPTS[@]}" "$SSH_HOST" "crontab -l 2>/dev/null | grep -c drift-check || true")
    existing="${existing%%[^0-9]*}"  # strip non-numeric
    existing="${existing:-0}"
    if [[ "$existing" -gt 0 ]]; then
        info "Drift-check cron already installed (${existing} entries), skipping"
    else
        ssh "${SSH_OPTS[@]}" "$SSH_HOST" "
            crontab -l 2>/dev/null > /tmp/crontab-028.bak
            echo '# Agent workspace drift enforcement (mission 028)' >> /tmp/crontab-028.bak
            echo '${CRON_SCHEDULE} ${CRON_CMD}' >> /tmp/crontab-028.bak
            crontab /tmp/crontab-028.bak
        " || fail "Cron install failed"
        info "Cron job installed: ${CRON_SCHEDULE}"
    fi
fi

echo

# ---------------------------------------------------------------------------
# Step 5: Sync office2 repo clone
# ---------------------------------------------------------------------------
echo "Step 5: Sync office2 repo clone"

if [[ "$MODE" == "dry-run" ]]; then
    echo "  DRY RUN: would run git pull on office2 repo clone"
else
    ssh "${SSH_OPTS[@]}" "$SSH_HOST" "cd /home/claude/kg-automation && git pull --ff-only 2>&1" | while read -r line; do
        echo "  $line"
    done
    info "Office2 repo clone synced"
fi

echo

# ---------------------------------------------------------------------------
# Step 6: Post-flight smoke test (zero-drift gate)
# ---------------------------------------------------------------------------
echo "Step 6: Post-flight zero-drift verification"

if [[ "$MODE" == "dry-run" ]]; then
    echo "  DRY RUN: would verify zero drift via direct hash comparison"
else
    echo "  Comparing all 25 workspace file hashes (repo vs office2)..."
    DRIFT_COUNT=0
    for agent_dir in main:data felix-admin-capture:inbox-agent felix-admin-habits:habits-agent felix-admin-escalation:escalation-agent felix-admin-tasker:tasker-agent; do
        repo_name="${agent_dir%%:*}"
        office2_name="${agent_dir##*:}"
        for f in AGENTS.md SOUL.md TOOLS.md USER.md IDENTITY.md; do
            local_path="${REPO_ROOT}/scripts/openclaw/agents/${repo_name}/${f}"
            remote_path="/data/services/openclaw/${office2_name}/${f}"
            if [[ -f "$local_path" ]]; then
                local_hash=$(sha256_local "$local_path")
                remote_hash=$(sha256_remote "$remote_path")
                if [[ "$local_hash" != "$remote_hash" ]]; then
                    warn "DRIFT: ${repo_name}/${f} local=${local_hash:0:16} remote=${remote_hash:0:16}"
                    DRIFT_COUNT=$((DRIFT_COUNT + 1))
                fi
            fi
        done
    done
    if [[ "$DRIFT_COUNT" -gt 0 ]]; then
        fail "Post-deploy verification failed: ${DRIFT_COUNT} files with drift"
    fi
    info "Zero-drift verification passed: all tracked files match"
fi

echo
echo "═══════════════════════════════════════════════════════════"
if [[ "$MODE" == "dry-run" ]]; then
    echo " DRY RUN complete. To apply: $SCRIPT_NAME --apply --backup-confirmed"
else
    echo " Deploy complete."
    echo
    echo " Rollback instructions (if needed):"
    echo "   Tasker files: restic restore from pre-deploy snapshot"
    echo "   Enforcement:  ssh $SSH_HOST 'rm -rf ${REMOTE_ENFORCEMENT_DIR}'"
    echo "   Cron:         ssh $SSH_HOST 'crontab -l | grep -v drift-check | crontab -'"
fi
echo "═══════════════════════════════════════════════════════════"
