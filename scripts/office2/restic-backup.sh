#!/bin/bash
# Restic backup with GFS rotation for office2
# Backs up /data (services, transcripts, configs) and /home
# Runs daily via cron
# #511: writes /data/services/backup/state/last-backup.json so a Tier 2
# pre-flight check can verify backup currency with a single `jq` query
# instead of scraping logs. The trap below guarantees the pointer is
# written on every script exit (success or failure).

export RESTIC_REPOSITORY="/mnt/backups/restic-repo"
export RESTIC_PASSWORD_FILE="/home/claude/.config/restic/password"

LOG_DIR="/data/services/backup/logs"
STATE_DIR="/data/services/backup/state"
mkdir -p "$LOG_DIR" "$STATE_DIR"
DATE=$(date +%Y-%m-%d)
LOGFILE="$LOG_DIR/backup-$DATE.log"
STATE_FILE="$STATE_DIR/last-backup.json"

# Health-pointer state (#511). Defaults reflect "we have not yet reached
# the backup step"; subsequent code overwrites them. The trap on EXIT
# writes the pointer atomically so the freshness check always sees the
# latest outcome — including failed runs where restic never executed.
BACKUP_RC=127      # "not run" sentinel; overwritten by `restic backup`
INTEGRITY_RUN=false
INTEGRITY_PASSED=null

log() { echo "[$(date '+%H:%M:%S')] $1" | tee -a "$LOGFILE"; }

write_state_pointer() {
    # Authoritative snapshot timestamp comes from `restic snapshots
    # --latest 1 --json` (what landed in the repo), not from `date` at
    # script-end. Per #511 design: the pointer is a fast local read for
    # Tier 2 pre-flight; the *value* it carries is repo-side fact.
    local snapshot_ts_json="null" snapshot_id_json="null" snapshot_count_json="null"
    local snapshot_json
    if snapshot_json=$(restic snapshots --latest 1 --json 2>/dev/null) \
        && [ -n "$snapshot_json" ] && [ "$snapshot_json" != "null" ] && [ "$snapshot_json" != "[]" ]; then
        local ts sid
        ts=$(echo "$snapshot_json" | jq -r '.[0].time
            | sub("\\.[0-9]+"; "")
            | sub("\\+00:00$"; "Z")
            | if test("Z$") then . else . + "Z" end')
        sid=$(echo "$snapshot_json" | jq -r '.[0].id')
        snapshot_ts_json="\"$ts\""
        snapshot_id_json="\"$sid\""
        local all
        if all=$(restic snapshots --json 2>/dev/null) && [ -n "$all" ]; then
            snapshot_count_json=$(echo "$all" | jq 'length')
        fi
    fi

    local repo_size_bytes
    repo_size_bytes=$(du -sb /mnt/backups/restic-repo 2>/dev/null | awk '{print $1}')
    [ -z "$repo_size_bytes" ] && repo_size_bytes="null"

    local script_finished_at_utc
    script_finished_at_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)

    local tmp="${STATE_FILE}.tmp"
    cat > "$tmp" <<EOF
{
  "schema_version": 1,
  "snapshot_timestamp_utc": $snapshot_ts_json,
  "snapshot_id": $snapshot_id_json,
  "restic_exit_code": $BACKUP_RC,
  "script_finished_at_utc": "$script_finished_at_utc",
  "repo_size_bytes": $repo_size_bytes,
  "snapshot_count": $snapshot_count_json,
  "integrity_check_run": $INTEGRITY_RUN,
  "integrity_check_passed": $INTEGRITY_PASSED
}
EOF
    mv -f "$tmp" "$STATE_FILE"
    chmod 644 "$STATE_FILE"
    log "State pointer written: ts=$snapshot_ts_json rc=$BACKUP_RC"
}

trap write_state_pointer EXIT

echo "=== Backup: $DATE ===" > "$LOGFILE"

# Check if backup drive is mounted
if ! mountpoint -q /mnt/backups; then
    log "ERROR: /mnt/backups not mounted. Backup drive missing?"
    exit 1
fi

# Check restic repo is accessible
if ! restic snapshots --latest 1 &>/dev/null; then
    log "ERROR: Cannot access restic repo"
    exit 1
fi

# --- Run backup ---
log "Starting backup of /data and /home..."
restic backup \
    /data/services \
    /data/transcripts \
    /home/claude \
    /home/kgale \
    --exclude="/data/services/transcribe/models" \
    --exclude="*.tmp" \
    --exclude="__pycache__" \
    --exclude=".cache" \
    --tag "daily" \
    --verbose >> "$LOGFILE" 2>&1

BACKUP_RC=$?
# Exit code 3 = completed with warnings (e.g. permission denied on some files)
if [ $BACKUP_RC -ne 0 ] && [ $BACKUP_RC -ne 3 ]; then
    log "ERROR: Backup failed with exit code $BACKUP_RC"
    exit 1
fi
log "Backup completed successfully"

# --- GFS Retention Policy ---
# Keep: 7 daily, 4 weekly, 6 monthly, 1 yearly
log "Applying retention policy..."
restic forget \
    --keep-daily 7 \
    --keep-weekly 4 \
    --keep-monthly 6 \
    --keep-yearly 1 \
    --prune \
    --verbose >> "$LOGFILE" 2>&1

PRUNE_RC=$?
if [ $PRUNE_RC -ne 0 ]; then
    log "WARNING: Prune failed with exit code $PRUNE_RC"
else
    log "Retention policy applied"
fi

# --- Integrity check (weekly on Sundays) ---
DOW=$(date +%u)
if [ "$DOW" -eq 7 ]; then
    log "Running weekly integrity check..."
    restic check >> "$LOGFILE" 2>&1
    INTEGRITY_RC=$?
    INTEGRITY_RUN=true
    if [ $INTEGRITY_RC -eq 0 ]; then
        log "Integrity check passed"
        INTEGRITY_PASSED=true
    else
        log "WARNING: Integrity check found issues"
        INTEGRITY_PASSED=false
    fi
fi

# --- Report ---
log "Snapshot summary:"
restic snapshots --latest 3 >> "$LOGFILE" 2>&1

REPO_SIZE=$(du -sh /mnt/backups/restic-repo 2>/dev/null | awk '{print $1}')
DRIVE_FREE=$(df -h /mnt/backups | tail -1 | awk '{print $4}')
log "Repo size: $REPO_SIZE | Drive free: $DRIVE_FREE"
log "=== Backup complete ==="

# write_state_pointer fires via the EXIT trap
