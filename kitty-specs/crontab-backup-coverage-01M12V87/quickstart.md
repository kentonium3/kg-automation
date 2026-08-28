# Quickstart: Crontab Backup Coverage

How to verify this mission's outcome on office2, and how to actually use it in
the incident it exists for.

## Verify the capture is alive

```bash
ssh office2-claude 'systemctl --user list-timers crontab-capture.timer --no-pager'
```

```bash
ssh office2-claude 'cat /data/services/host-state/last-tick.json'
```

Expect `"status": "success"`, `"exit_code": 0`, and a `completed_at_utc` within
the last two hours.

## Verify the artifact is real and restorable (SC-001, SC-002)

```bash
ssh office2-claude 'cat /data/services/host-state/crontabs/claude.crontab'
```

Confirm the body below the provenance header matches the live crontab:

```bash
ssh office2-claude 'diff <(crontab -l) <(grep -v "^# captured-\|^# source-\|^# NOTE:\|^#       " /data/services/host-state/crontabs/claude.crontab)'
```

Empty output means byte-identical.

## Verify it is genuinely in the backup, not just on disk

This is the criterion the mission exists for — the artifact must be recoverable
from a snapshot, with no security-monitor baseline involved.

```bash
ssh office2-kgale 'sudo restic -r /mnt/backups/restic-repo --password-file /etc/restic/password snapshots --latest 1'
```

```bash
ssh office2-kgale 'sudo restic -r /mnt/backups/restic-repo --password-file /etc/restic/password restore latest --target /tmp/restore-check --include /data/services/host-state'
```

```bash
ssh office2-kgale 'cat /tmp/restore-check/data/services/host-state/crontabs/claude.crontab'
```

Both commands need sudo because `/etc/restic/password` is root-only — this is an
operator step, not an agent step.

## Verify snapshot grouping did not change (SC-003, NFR-001)

The failure this guards against is silent and permanent, so check it explicitly.

```bash
ssh office2-kgale 'sudo restic -r /mnt/backups/restic-repo --password-file /etc/restic/password snapshots --json' | python3 -c "
import json,sys
snaps = json.load(sys.stdin)
groups = {tuple(sorted(s['paths'])) for s in snaps}
print(f'{len(snaps)} snapshots, {len(groups)} distinct path group(s)')
for g in groups: print(' ', list(g))
assert len(groups) == 1, 'PATH GROUP SPLIT — forget/prune will strand a series'
print('OK: single path group')
"
```

One group is required. More than one means a source path was added despite
C-002, and the older series will never be pruned again.

## Verify the drift check is registered and reporting (SC-005)

```bash
ssh office2-claude 'cat /data/services/openclaw/state/enforcement/last-tick.json'
```

```bash
ssh office2-claude 'cd /home/claude/kg-automation && python3 -m scripts.canary.run --once --dry-run' | grep -i "drift\|crontab-capture"
```

Both components should appear with a definite verdict — not `unknown`.

## Verify staleness is actually detected (SC-004)

A health check that cannot fail is worse than none (#891). Prove this one fails:

```bash
ssh office2-claude 'python3 - <<PY
import json, pathlib, datetime
p = pathlib.Path("/data/services/host-state/last-tick.json")
d = json.loads(p.read_text())
d["completed_at_utc"] = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=9)).isoformat()
pathlib.Path("/tmp/stale-tick.json").write_text(json.dumps(d))
print("wrote /tmp/stale-tick.json")
PY'
```

Point a dry-run probe at the stale copy and confirm it reports `stale`, then
discard it. Do **not** overwrite the real pointer.

## Using it in the incident

If the crontab is destroyed:

```bash
ssh office2-claude 'grep -v "^# captured-\|^# source-\|^# NOTE:\|^#       " /data/services/host-state/crontabs/claude.crontab > /tmp/restore.crontab && crontab /tmp/restore.crontab && crontab -l'
```

If `/data` is gone too, restore the artifact from a snapshot first (above), then
reinstall from the restored copy.

**Do not** reach for `/data/services/security-monitor/baselines/crontabs.txt`.
That file exists for drift detection, is deleted by the rebaseline procedure,
and depending on it is the gap this mission closed.

## Rollback

```bash
ssh office2-claude 'systemctl --user disable --now crontab-capture.timer && systemctl --user daemon-reload'
```

The captured artifact is inert data and can be left in place; nothing reads it
except a human during recovery. Removing the timer restores the prior state
exactly — no backup configuration was ever modified.
