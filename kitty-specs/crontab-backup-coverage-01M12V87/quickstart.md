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

A health check that cannot fail is worse than none (#891). Prove this one fails,
using the real probe rather than a hand-rolled mimic. This never touches the live
pointer — it builds a fixture in a temp dir and points a copy of the health-check
config at it.

```bash
ssh office2-claude 'cd /home/claude/kg-automation && python3 - <<PY
import json, tempfile, pathlib
from datetime import datetime, timedelta, timezone
from scripts.canary.probes import run_probe

now = datetime.now(timezone.utc)
tmp = pathlib.Path(tempfile.mkdtemp())
ptr = tmp / "last-tick.json"

def check(p):
    return {"method": "state-file", "state_path": str(p), "max_age_seconds": 7200}

def read_state(path):
    return json.loads(pathlib.Path(path).read_text())

for label, age_h in (("fresh", 0.5), ("stale", 9)):
    ptr.write_text(json.dumps({
        "status": "success", "exit_code": 0,
        "completed_at_utc": (now - timedelta(hours=age_h)).isoformat(),
    }))
    r = run_probe(check(ptr), now, http_get=None, run_cmd=None, read_state=read_state)
    print(f"{label:6} -> ok={r.ok} stale={r.stale} evaluable={r.evaluable}")

# explicit-error path: a runner failure must be unhealthy regardless of freshness
ptr.write_text(json.dumps({
    "status": "error", "exit_code": 2,
    "completed_at_utc": now.isoformat(),
}))
r = run_probe(check(ptr), now, http_get=None, run_cmd=None, read_state=read_state)
print(f"errored -> ok={r.ok} evidence={r.evidence}")
PY'
```

Expected: `fresh` reports not-stale, `stale` reports `stale=True`, and the
errored pointer is not ok. If `stale` comes back false, the check cannot fail and
the registration is worthless.

### Verify drift-found is not mistaken for unhealthy

The inverse of the above, and the specific trap this mission avoids: the drift
check exits `1` when it *finds* drift, which is a successful run. Confirm the
pointer records that as healthy.

```bash
ssh office2-claude 'cd /home/claude/kg-automation && python3 - <<PY
import json, pathlib
from datetime import datetime, timezone
from scripts.canary.probes import run_probe
now = datetime.now(timezone.utc)
p = pathlib.Path("/data/services/openclaw/state/enforcement/last-tick.json")
d = json.loads(p.read_text())
print("pointer:", {k: d.get(k) for k in ("status", "exit_code", "has_drift")})
r = run_probe(
    {"method": "state-file", "state_path": str(p), "max_age_seconds": 108000},
    now, http_get=None, run_cmd=None,
    read_state=lambda path: json.loads(pathlib.Path(path).read_text()),
)
print("verdict:", r.ok, r.evidence)
PY'
```

`has_drift: true` with `exit_code: 0` must still read healthy.

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
