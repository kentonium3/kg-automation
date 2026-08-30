#!/bin/bash
# Restic backup with GFS rotation for office2
# Backs up /data (services, transcripts, configs) and /home
# Runs daily via cron
# #511: writes /data/services/backup/state/last-backup.json so a Tier 2
# pre-flight check can verify backup currency with a single `jq` query
# instead of scraping logs. The trap below guarantees the pointer is
# written on every script exit (success or failure).
#
# #902: the pointer also records `prune_exit_code`, the outcome of
# `restic forget --prune`. Before this, a prune failure was logged as a
# WARNING and then discarded, so a stale lock blocked retention for ten
# hours while every health surface correctly reported the BACKUP healthy.
#   0    retention applied
#   127  never attempted -- the run exited before reaching the prune step
#   else the prune ran and failed
# Only 0 is success. This differs from `restic_exit_code`, where {0,3} is
# accepted because a backup exiting 3 still produced a snapshot; `forget`
# exiting 3 carries no such guarantee.
#
# pointer-key-ledger-01M189P6/WP01: four keys added, schema bumped to 2, so
# the pointer can express four previously-invisible total-loss conditions.
# Every addition fails soft -- computed into a shell variable, guarded, and
# defaulted to the JSON literal `null` on any failure -- because this
# instrumentation must never be the reason the backup itself aborts.
#   last_integrity_check_utc  UTC instant of the last *passing* weekly
#                              `restic check`, carried forward from the
#                              previous state document when today's run
#                              doesn't reach (or doesn't pass) the Sunday
#                              check. Every failure path exits before that
#                              block, so without carry-forward a run of bad
#                              Sundays would silently reset this to null
#                              every week rather than accumulating the gap --
#                              which is exactly the condition this key exists
#                              to surface. Set only on a passing check, never
#                              on "we ran it" -- see integrity_check_run for
#                              that.
#   files_processed           `.total_file_count` from `restic stats`, so a
#                              backup that exits 0 and produces a fresh
#                              snapshot but captured nothing (source-path
#                              typo, over-broad exclude) is distinguishable
#                              from a real capture.
#   source_roots_present      whether every path in SOURCE_ROOTS appears in
#                              the latest snapshot's `paths`, so a partial
#                              capture -- one root silently missing -- isn't
#                              mistaken for a complete one.
#   repo_fs_free_bytes        free space on the filesystem backing
#                              RESTIC_REPOSITORY, so the approach to a full
#                              volume is visible before the backup starts
#                              failing outright.

export RESTIC_REPOSITORY="${RESTIC_REPOSITORY:-/mnt/backups/restic-repo}"
export RESTIC_PASSWORD_FILE="${RESTIC_PASSWORD_FILE:-/etc/restic/password}"

# Source roots backed up nightly. Defined once (T004) and used both for the
# `restic backup` invocation below and for the source_roots_present check in
# write_state_pointer -- a second, hand-copied list would be exactly the kind
# of unenforced coupling this mission exists to retire.
SOURCE_ROOTS=(
    /data/services
    /data/transcripts
    /home/claude
    /home/kgale
)

# Overridable for testing only. Added with #902 so the pointer-emission paths --
# especially the early exits that skip the prune -- can be EXECUTED by a test
# rather than verified by reading, which is how the sibling #906 defect survived
# review.
#
# Hardened per post-implementation review: when running privileged, the overrides
# are ignored outright and the real paths are used. This script is a NOPASSWD
# sudo target, so it normally runs as root. Today `sudo` is configured with
# env_reset + secure_path (verified on office2), which already strips these --
# but that makes the safety property depend on sudoers staying that way. If the
# rule ever gained SETENV or a matching env_keep, an attacker could redirect
# RESTIC_REPOSITORY and RESTIC_PASSWORD_FILE, bypass the mount check with
# BACKUP_MOUNT=/, and have root write into paths they control.
#
# Making the guard intrinsic removes that dependency: privileged runs cannot be
# redirected regardless of how sudo is configured.
if [ "$(id -u)" -eq 0 ]; then
    LOG_DIR="/data/services/backup/logs"
    STATE_DIR="/data/services/backup/state"
    BACKUP_MOUNT="/mnt/backups"
    RESTIC_REPOSITORY="/mnt/backups/restic-repo"
    RESTIC_PASSWORD_FILE="/etc/restic/password"
else
    LOG_DIR="${LOG_DIR:-/data/services/backup/logs}"
    STATE_DIR="${STATE_DIR:-/data/services/backup/state}"
    BACKUP_MOUNT="${BACKUP_MOUNT:-/mnt/backups}"
fi
mkdir -p "$LOG_DIR" "$STATE_DIR"
DATE=$(date +%Y-%m-%d)
LOGFILE="$LOG_DIR/backup-$DATE.log"
STATE_FILE="$STATE_DIR/last-backup.json"

# Health-pointer state (#511). Defaults reflect "we have not yet reached
# the backup step"; subsequent code overwrites them. The trap on EXIT
# writes the pointer atomically so the freshness check always sees the
# latest outcome — including failed runs where restic never executed.
BACKUP_RC=127      # "not run" sentinel; overwritten by `restic backup`
PRUNE_RC=127       # "not run" sentinel; overwritten by `restic forget --prune`.
                   # Deliberately an integer, never null: the canary's
                   # explicit-error scan guards with isinstance(code, int), so a
                   # non-integer is SKIPPED and a run killed between a successful
                   # backup and the prune would read healthy (#902).
INTEGRITY_RUN=false
INTEGRITY_PASSED=null
LAST_INTEGRITY_CHECK_UTC=null   # carried forward below, then possibly set by
                                 # the Sunday integrity block (T002)

# Carry the last-known-good integrity-check timestamp forward from the prior
# state document, before this run's document is written. Every backup
# failure path exits before the weekly check block, so without this a run of
# bad Sundays would silently reset the field to null every week instead of
# accumulating the gap (see the header comment). Must fail soft: a missing
# or corrupt prior document must leave the null default and must not abort
# the run.
if [ -f "$STATE_FILE" ]; then
    # jq both validates and encodes: the retained value is accepted only if
    # it is a JSON string matching the timestamp shape this script itself
    # emits (script_finished_at_utc et al.), and $v is then let through as
    # jq's own encoding -- never hand-built with shell quotes, so a value
    # containing a literal `"` cannot produce an unparseable document. A
    # parse error on the prior document itself (corrupt file) makes jq emit
    # nothing, so PRIOR_INTEGRITY_CHECK_UTC_JSON stays empty and the `null`
    # default above is left untouched.
    if PRIOR_INTEGRITY_CHECK_UTC_JSON=$(jq -c '
            (.last_integrity_check_utc // null) as $v
            | if ($v | type) == "string"
                and ($v | test("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"))
              then $v
              else null
              end
        ' "$STATE_FILE" 2>/dev/null) \
        && [ -n "$PRIOR_INTEGRITY_CHECK_UTC_JSON" ]; then
        LAST_INTEGRITY_CHECK_UTC="$PRIOR_INTEGRITY_CHECK_UTC_JSON"
    fi
    unset PRIOR_INTEGRITY_CHECK_UTC_JSON
fi

log() { echo "[$(date '+%H:%M:%S')] $1" | tee -a "$LOGFILE"; }

write_state_pointer() {
    # Authoritative snapshot timestamp comes from `restic snapshots
    # --latest 1 --json` (what landed in the repo), not from `date` at
    # script-end. Per #511 design: the pointer is a fast local read for
    # Tier 2 pre-flight; the *value* it carries is repo-side fact.
    local snapshot_ts_json="null" snapshot_id_json="null" snapshot_count_json="null"
    local source_roots_present_json="null"
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

        # T004: every configured source root must appear in the latest
        # snapshot's paths, or a partial capture reads as complete. Reuses
        # the snapshot already fetched above rather than a second query.
        #
        # `jq -e` exits non-zero both when the filter is false AND when jq
        # itself fails (malformed JSON, `paths` not an array) -- collapsing
        # those would report "false" (a root proven absent) when nothing was
        # actually measured. So the filter never uses -e: it emits the
        # literal string "true"/"false" only when the comparison could be
        # performed at all, and empty output otherwise, and the shell case
        # below is what tells "false" apart from "could not evaluate".
        #
        # No `// []` default on `.paths`: a default supplied BEFORE the type
        # check turns an absent/null `paths` into `[]`, which IS an array,
        # so the guard would pass and the comparison would emit "false" --
        # exactly the false-proven-absent bug this filter exists to avoid.
        # Absent/null must fall through to `empty` undefaulted.
        #
        # Non-string entries inside an otherwise-array `paths` are left to
        # `index()`, not treated as malformed: jq's `index()` structurally
        # compares each element regardless of type, so a stray number/null/
        # object just fails to match $r rather than erroring the filter --
        # the comparison against the well-typed entries still genuinely
        # completed, so reporting `null` ("could not evaluate") for that
        # case would be a false negative in the other direction.
        local root all_roots_present=1 root_eval_failed=0 present
        for root in "${SOURCE_ROOTS[@]}"; do
            present=$(echo "$snapshot_json" \
                | jq -r --arg r "$root" '
                    (.[0].paths) as $p
                    | if ($p | type) == "array" then ($p | index($r) != null) else empty end
                ' 2>/dev/null)
            case "$present" in
                true)  ;;
                false) all_roots_present=0 ;;
                *)     root_eval_failed=1; break ;;
            esac
        done
        if [ "$root_eval_failed" -eq 1 ]; then
            source_roots_present_json="null"
        elif [ "$all_roots_present" -eq 1 ]; then
            source_roots_present_json="true"
        else
            source_roots_present_json="false"
        fi

        local all
        if all=$(restic snapshots --json 2>/dev/null) && [ -n "$all" ]; then
            snapshot_count_json=$(echo "$all" | jq 'length' 2>/dev/null)
            # T006: guard against an unguarded empty result producing
            # invalid JSON ("snapshot_count": ,) -- the defect
            # repo_size_bytes below was already guarded against.
            if [ -z "$snapshot_count_json" ] || ! [[ "$snapshot_count_json" =~ ^[0-9]+$ ]]; then
                snapshot_count_json="null"
            fi
        fi
    fi

    local repo_size_bytes
    repo_size_bytes=$(du -sb "$RESTIC_REPOSITORY" 2>/dev/null | awk '{print $1}')
    [ -z "$repo_size_bytes" ] && repo_size_bytes="null"

    # T003: distinguish a real capture from an empty one. `restic stats`
    # rather than `restic backup --json`, to leave the human-readable
    # --verbose backup log the runbook depends on untouched.
    local files_processed_json="null"
    local stats_json
    if stats_json=$(restic stats --mode files-by-contents latest --json 2>/dev/null) \
        && [ -n "$stats_json" ]; then
        local files_processed
        files_processed=$(echo "$stats_json" | jq -r '.total_file_count' 2>/dev/null)
        if [ -n "$files_processed" ] && [[ "$files_processed" =~ ^[0-9]+$ ]]; then
            files_processed_json="$files_processed"
        fi
    fi

    # T005: free space on the filesystem backing the repository -- distinct
    # from repo_size_bytes, which measures the repository itself.
    local repo_fs_free_bytes
    repo_fs_free_bytes=$(df -B1 --output=avail "$RESTIC_REPOSITORY" 2>/dev/null | tail -n +2 | tr -d '[:space:]')
    if [ -z "$repo_fs_free_bytes" ] || ! [[ "$repo_fs_free_bytes" =~ ^[0-9]+$ ]]; then
        repo_fs_free_bytes="null"
    fi

    local script_finished_at_utc
    script_finished_at_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)

    local tmp="${STATE_FILE}.tmp"
    cat > "$tmp" <<EOF
{
  "schema_version": 2,
  "snapshot_timestamp_utc": $snapshot_ts_json,
  "snapshot_id": $snapshot_id_json,
  "restic_exit_code": $BACKUP_RC,
  "prune_exit_code": $PRUNE_RC,
  "script_finished_at_utc": "$script_finished_at_utc",
  "repo_size_bytes": $repo_size_bytes,
  "snapshot_count": $snapshot_count_json,
  "integrity_check_run": $INTEGRITY_RUN,
  "integrity_check_passed": $INTEGRITY_PASSED,
  "last_integrity_check_utc": $LAST_INTEGRITY_CHECK_UTC,
  "files_processed": $files_processed_json,
  "source_roots_present": $source_roots_present_json,
  "repo_fs_free_bytes": $repo_fs_free_bytes
}
EOF
    mv -f "$tmp" "$STATE_FILE"
    chmod 644 "$STATE_FILE"
    log "State pointer written: ts=$snapshot_ts_json rc=$BACKUP_RC"
}

trap write_state_pointer EXIT

echo "=== Backup: $DATE ===" > "$LOGFILE"

# Check if backup drive is mounted
if ! mountpoint -q "$BACKUP_MOUNT"; then
    log "ERROR: $BACKUP_MOUNT not mounted. Backup drive missing?"
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
    "${SOURCE_ROOTS[@]}" \
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
        LAST_INTEGRITY_CHECK_UTC="\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\""
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
