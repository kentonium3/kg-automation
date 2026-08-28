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
| Password file | `/etc/restic/password` (root-owned 0600; moved out of `/home/claude/.config/restic/` by #888 because the key lived inside the tree it protects) |
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
    elif (has("prune_exit_code") and .prune_exit_code != 0) then "FAIL: prune exit \(.prune_exit_code)"
    else "OK (\($age_sec / 3600 | floor) hours since snapshot)"
    end
  end'"'"' /data/services/backup/state/last-backup.json'
```

Returns one line on stdout and exit 0 (`OK …`) or exit 1 (`FAIL: …`).

The `prune_exit_code` clause is guarded with `has(...)` so a pointer written
before #902 — which carries no such field — still evaluates. Note the good-set
is `0` alone, deliberately narrower than the backup's `{0, 3}`: a `restic backup`
exiting 3 completed with warnings but still produced a snapshot, whereas
`restic forget` exiting 3 means snapshots could not be removed, which is not a
successful retention pass. `127` is the script's "never attempted" sentinel.

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
| `restic_exit_code` | the `restic backup` step's `$?` | NOT the script's overall exit. `127` = "never reached the backup step" (pre-check failed). Good set `{0, 3}`. |
| `prune_exit_code` | the `restic forget --prune` step's `$?` (#902) | Good set `{0}` ONLY. `127` = "never reached the prune step". Before #902 this was logged as a WARNING and discarded, so a stale lock blocked retention for ten hours while every health surface correctly reported the *backup* healthy. |
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
  RESTIC_PASSWORD_FILE=/etc/restic/password \
  restic snapshots --latest 5'
```

### Restore from a snapshot

The standard restic workflow. Identify the snapshot id from the listing
above, then:

```bash
ssh office2-kgale 'sudo RESTIC_REPOSITORY=/mnt/backups/restic-repo \
  RESTIC_PASSWORD_FILE=/etc/restic/password \
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

## Deploying this script — manual, by decision

`scripts/office2/restic-backup.sh` is the repo source of truth. The deployed copy
is `/data/services/backup/scripts/backup.sh`, owned `root:root` in a `root:root`
directory.

**It is installed by hand, on purpose, and that will not change.** The deploy
pipeline runs as `claude`, so automating this install would mean making
`/data/services/backup/scripts/` claude-writable. That directory holds the
`NOPASSWD` sudo target `backup.sh`, and a writable directory on a NOPASSWD path
makes the grant equivalent to `NOPASSWD: ALL` — which is #899, a real privilege
escalation fixed on 2026-08-27. Automating the deploy would reopen it to save one
command. So the pipeline is not used here; instead `backup-script-drift` (#903)
reports when the two copies diverge.

### Installing an updated script

**Install from GitHub, not from the office2 checkout.** `/home/claude/kg-automation`
is writable by the unprivileged `claude` account; installing from there as root
would let that account influence root-executed content. Fetching the reviewed
commit from GitHub removes it from the trust path entirely.

Two earlier versions of this procedure were wrong and are worth recording so they
are not reintroduced:

- Sourcing the install from `/home/claude/kg-automation/...` — protects the
  destination while leaving the source unverified.
- Verifying with `git -C /home/claude/kg-automation diff --quiet …` — `/home/claude`
  is mode `0750`, so `kgale` cannot traverse it. The command exits non-zero for
  *permission denied* and, wrapped in `&& … || …`, reports that as "working tree
  differs". A check that cannot distinguish "verified false" from "could not
  check" is the defect class this whole runbook exists to fix.

```bash
ssh office2-kgale
```

Fetch the exact reviewed commit into your own home (not `/tmp`, which is
world-writable and invites a swap between fetch and install):

```bash
curl -fsSL -o ~/restic-backup.sh https://raw.githubusercontent.com/kentonium3/kg-automation/<commit-sha>/scripts/office2/restic-backup.sh
```

Confirm the content hash matches the commit you reviewed:

```bash
md5sum ~/restic-backup.sh
```

Only then install, from the file you just verified:

```bash
sudo install -o root -g root -m 755 ~/restic-backup.sh /data/services/backup/scripts/backup.sh
```

Confirm what actually landed:

```bash
sudo md5sum /data/services/backup/scripts/backup.sh
```

It must equal the hash from the fetch. `backup-script-drift` then performs that
comparison daily without being asked, and will flip from `drift` to `match`.

### Reading the drift signal

```bash
ssh office2-claude 'cat /data/services/backup/drift/script-drift-last-tick.json'
```

| `verdict` | meaning |
|---|---|
| `match` | the deployed script is the repo script |
| `drift` | they differ — reinstall, or find out who changed the host copy |
| `inconclusive` | the comparator could not read one side: missing, unreadable, a symlink, or not a regular file. **Never treated as agreement.** A symlinked deployed copy is especially significant: it would mean the NOPASSWD sudo target points somewhere else. |

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
- **Pre-flight checklist**: [`docs/runbooks/governance/pre-flight-checklist.md`](<./governance/pre-flight-checklist.md>) Tier 2 § "Confirm recent backup exists".
- **Backup architecture overview**: [`docs/design/architecture/backup-and-recovery.md`](<../design/architecture/backup-and-recovery.md>).
- **Issue**: [#511](https://github.com/kentonium3/kg-automation/issues/511).
