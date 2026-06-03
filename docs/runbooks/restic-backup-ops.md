---
id: restic-backup-ops
doc_type: runbook
title: Restic Backup Operations
status: approved
level: 2
owners: [kent]
audience: agents_and_humans
last_validated: '2026-06-02'
updated_by: '#511'
---

# Restic Backup Operations

The nightly backup for office2. Runs as a plain cron job under the `claude`
user with `NOPASSWD sudo` for one specific script — there is no systemd
unit or timer, so `systemctl status` will not find it.

## Where things live

| Resource | Path / Value |
|---|---|
| Script (canonical source) | [`scripts/office2/restic-backup.sh`](../../scripts/office2/restic-backup.sh) |
| Script (deployed) | `/data/services/backup/scripts/backup.sh` on office2 |
| Restic repo | `/mnt/backups/restic-repo` on office2 (2.7 TB drive at `/mnt/backups`) |
| Password file | `/home/claude/.config/restic/password` |
| Daily logs | `/data/services/backup/logs/backup-YYYY-MM-DD.log` |
| Health pointer | `/data/services/backup/state/last-backup.json` |
| Cron entry | `claude`'s crontab on office2, `0 4 * * *` (04:00 UTC daily) via `sudo /data/services/backup/scripts/backup.sh` |
| Sudoers grant | `claude ALL=(root) NOPASSWD: /data/services/backup/scripts/backup.sh` |

## Verifying backup currency (the load-bearing check)

The pre-flight check that Tier 2 changes depend on. Fast (sub-second),
no restic creds needed at check time, no read load on the repo:

```bash
ssh office2-claude 'jq -er '"'"'
  if .snapshot_timestamp_utc == null then "FAIL: no snapshot recorded" else
    (now - (.snapshot_timestamp_utc | fromdateiso8601)) as $age_sec |
    if ($age_sec > 100800) then "FAIL: stale (\($age_sec / 3600 | floor) hours old)"
    elif (.restic_exit_code != 0 and .restic_exit_code != 3) then "FAIL: restic exit \(.restic_exit_code)"
    else "OK (\($age_sec / 3600 | floor) hours since snapshot)"
    end
  end'"'"' /data/services/backup/state/last-backup.json'
```

Returns one line on stdout and exit 0 (`OK …`) or exit 1 (`FAIL: …`).

Freshness budget: 28 hours = 24 h cadence + 4 h slack for a slow run.
Restic exit codes 0 (success) and 3 (success with permission-denied
warnings) both pass.

## Health-pointer schema (#511)

The pointer at `/data/services/backup/state/last-backup.json` is written
atomically (`.tmp` + `mv`) by `backup.sh` on every exit — success OR
failure — so a stale pointer always means the cron has not fired.

| Field | Source | Notes |
|---|---|---|
| `schema_version` | constant `1` | Bump on breaking schema change. |
| `snapshot_timestamp_utc` | `restic snapshots --latest 1 --json` after the run | Authoritative. `null` when the snapshot query failed (repo broken). |
| `snapshot_id` | same query | `null` on failure. |
| `restic_exit_code` | the `restic backup` step's `$?` | NOT the script's overall exit. `127` = "never reached the backup step" (pre-check failed). |
| `script_finished_at_utc` | `date -u` at script-end | Separate witness so "did the cron fire" stays distinct from "did restic succeed". |
| `repo_size_bytes` | `du -sb /mnt/backups/restic-repo` | Trend with the daily logs. |
| `snapshot_count` | `restic snapshots --json` length | After prune. |
| `integrity_check_run` | bool — true on Sundays | `restic check` runs weekly. |
| `integrity_check_passed` | bool or `null` | `null` on non-Sunday runs. |

## Operational tasks

### Trigger a backup manually

```bash
ssh office2-claude 'sudo /data/services/backup/scripts/backup.sh'
```

The NOPASSWD sudoers entry allows this without a password prompt. The
run writes to today's log file at `/data/services/backup/logs/` and
refreshes the pointer.

### Inspect the most recent run

```bash
ssh office2-claude 'cat /data/services/backup/state/last-backup.json | jq .'
ssh office2-claude 'tail -20 /data/services/backup/logs/backup-$(date -u +%Y-%m-%d).log'
```

### List snapshots (requires sudo via kgale)

The repo files are `root:root` mode 400, so `claude` cannot run
`restic snapshots` directly. From your laptop:

```bash
ssh office2-kgale 'sudo RESTIC_REPOSITORY=/mnt/backups/restic-repo \
  RESTIC_PASSWORD_FILE=/home/claude/.config/restic/password \
  restic snapshots --latest 5'
```

### Restore from a snapshot

The standard restic workflow. Identify the snapshot id from the listing
above, then:

```bash
ssh office2-kgale 'sudo RESTIC_REPOSITORY=/mnt/backups/restic-repo \
  RESTIC_PASSWORD_FILE=/home/claude/.config/restic/password \
  restic restore <snapshot-id> --target /tmp/restore-<date>'
```

Inspect `/tmp/restore-<date>/`; copy paths back into place as needed.

### Verify a stale pointer fails the freshness check

Used to confirm the pre-flight check is actually load-bearing:

```bash
# Save the current pointer
ssh office2-claude 'cp /data/services/backup/state/last-backup.json /tmp/last-backup.json.bak'

# Inject a stale timestamp
ssh office2-claude 'jq ".snapshot_timestamp_utc = \"2026-05-25T04:00:00Z\"" \
  /tmp/last-backup.json.bak > /tmp/last-backup.json.stale'

# Run the freshness check against the stale copy — must FAIL
ssh office2-claude 'jq -er '"'"'<the check from above>'"'"' /tmp/last-backup.json.stale'
echo $?  # should be 1
```

The real pointer file is owned `root:root`, so this manual test is
sandboxed in `/tmp` and does not perturb production state.

## Retention policy

GFS, applied at the end of each run via `restic forget --prune`:

- 7 daily
- 4 weekly
- 6 monthly
- 1 yearly

A weekly `restic check` runs on Sundays. Result is captured into
`integrity_check_passed` in the pointer.

## What is NOT yet automated

Per the optional follow-ups in #511 (deliberately deferred to keep
this maintenance action small):

- No signal-extraction-style alarm on `restic-backup-stale-or-failed`.
  Tier 2 changes are the only place the pointer is consumed today.
- The cron has not been migrated to a systemd timer. Discoverability is
  via this runbook plus `service-inventory.json`; `systemctl` queries
  will return nothing for the backup itself.

## Cross-references

- **Service entry**: `docs/design/architecture/data/service-inventory.json` → `restic-backup` (updated_by `#511 + #159 + #208`).
- **Pre-flight checklist**: [`docs/runbooks/governance/pre-flight-checklist.md`](governance/pre-flight-checklist.md) Tier 2 § "Confirm recent backup exists".
- **Backup architecture overview**: [`docs/design/architecture/backup-and-recovery.md`](../design/architecture/backup-and-recovery.md).
- **Issue**: [#511](https://github.com/kentonium3/kg-automation/issues/511).
