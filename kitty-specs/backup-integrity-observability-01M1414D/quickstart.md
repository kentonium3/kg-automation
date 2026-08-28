# Quickstart: Backup Integrity Observability

How to verify this mission on office2, and the one privileged step it needs.

## ⚠ The operator step: install the updated backup script

`restic-backup.sh` is `root:root` in a `root:root` directory, deliberately —
that directory holds a `NOPASSWD` sudo target, and making it claude-writable
would recreate the #899 privilege escalation. So the install is manual, by
design, not by omission.

```
ssh office2-kgale
```

**Verify the source before installing it.** The file lives in
`/home/claude/kg-automation`, which the unprivileged `claude` account can write.
Installing straight from there would let that account influence root-executed
content — not the #899 escalation, but the same boundary weakened one step
upstream. Check it against the commit you reviewed first:

```
cd /home/claude/kg-automation && git log --oneline -1 -- scripts/office2/restic-backup.sh
```

```
git -C /home/claude/kg-automation diff --quiet HEAD -- scripts/office2/restic-backup.sh && echo "matches committed content" || echo "WORKING TREE DIFFERS — do not install"
```

Only if both agree with what you reviewed:

```
sudo install -o root -g root -m 755 \
  /home/claude/kg-automation/scripts/office2/restic-backup.sh \
  /data/services/backup/scripts/backup.sh
```

Then confirm what actually landed:

```
sudo md5sum /data/services/backup/scripts/backup.sh /home/claude/kg-automation/scripts/office2/restic-backup.sh
```

Both hashes must match. The drift comparator gives you this check
independently on every run from then on.

Until this runs, the comparator will correctly report `drift` — the repo leads
the host. That is the tool working, not a fault.

## Verify the prune signal (SC-001, SC-002)

Trigger a backup through the sanctioned path and read the pointer:

```
ssh office2-claude 'sudo -n /data/services/backup/scripts/backup.sh 2>&1 | tail -3'
```

```
ssh office2-claude 'cat /data/services/backup/state/last-backup.json'
```

Expect `"prune_exit_code": 0` alongside `"restic_exit_code": 0`.

Now prove the check can actually fail — the whole point. Build the three
pointer shapes and judge them with the **real** probe:

```
ssh office2-claude 'cd /home/claude/kg-automation && python3 - <<PY
import json, pathlib, tempfile
from datetime import datetime, timezone
from scripts.canary.probes import run_probe

now = datetime.now(timezone.utc)
tmp = pathlib.Path(tempfile.mkdtemp()) / "p.json"
hc = {"method": "state-file", "state_path": str(tmp), "max_age_seconds": 100800}
read = lambda p: json.loads(pathlib.Path(p).read_text())

base = {"snapshot_timestamp_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "restic_exit_code": 0}
for label, prune in (("clean", 0), ("prune failed", 1), ("prune not attempted", 127)):
    tmp.write_text(json.dumps({**base, "prune_exit_code": prune}))
    r = run_probe(hc, now, http_get=None, run_cmd=None, read_state=read)
    print(f"{label:22} prune_exit_code={prune:3} -> ok={r.ok}")

# a pre-change pointer, with no prune field at all, must stay healthy
tmp.write_text(json.dumps(base))
r = run_probe(hc, now, http_get=None, run_cmd=None, read_state=read)
print(f"{'legacy (no field)':22} {'':16} -> ok={r.ok}")
PY'
```

Required: `clean` ok, **`prune failed` NOT ok**, **`prune not attempted` NOT
ok**, and `legacy` still ok (NFR-002 — old pointers stay interpretable).

## Verify the drift comparator (SC-003)

```
ssh office2-claude 'systemctl --user list-timers backup-script-drift.timer --no-pager | head -3'
```

```
ssh office2-claude 'cat /data/services/backup/state/script-drift-last-tick.json'
```

Then prove each verdict is reachable, without touching the real deployed file:

```
ssh office2-claude 'cd /home/claude/kg-automation && python3 -c "
import scripts.office2.backup_script_drift as d
print(\"altered copy ->\", d.compare(\"scripts/office2/restic-backup.sh\", \"/etc/hostname\"))
print(\"missing copy ->\", d.compare(\"scripts/office2/restic-backup.sh\", \"/nonexistent\"))
print(\"identical    ->\", d.compare(\"scripts/office2/restic-backup.sh\", \"scripts/office2/restic-backup.sh\"))
"'
```

Required: `drift`, `inconclusive`, `match`. An unreadable copy reporting `match`
is the failure mode this component exists to prevent.

## Verify crontab recovery (SC-004, SC-005)

```
ssh office2-claude 'cd /home/claude/kg-automation && diff <(crontab -l) <(python3 scripts/office2/crontab_capture.py --emit-body)'
```

Empty output means byte-identical — recovery needs no hand-written pattern.

The real recovery, during an incident:

```
ssh office2-claude 'cd /home/claude/kg-automation && python3 scripts/office2/crontab_capture.py --emit-body | crontab -'
```

```
ssh office2-claude 'crontab -l'
```

**Do not** use the `grep -v "^# captured-..."` form from the #895 quickstart. It
predates the sentinel-delimited header, leaves two stray lines behind, and is the
defect #906 fixed.

## Verify no privilege boundary moved

```
ssh office2-claude 'ls -ld /data/services/backup/scripts; touch /data/services/backup/scripts/.t 2>&1 | head -1'
```

Required: `root root`, and permission denied. If `claude` can write there, the
#899 escalation is back regardless of anything else in this mission.

## Rollback

```
ssh office2-claude 'systemctl --user disable --now backup-script-drift.timer'
```

The pointer field is additive and inert to old consumers; the probe change only
fires when the key is present. To revert the backup script, reinstall the prior
copy from a snapshot the same way it was installed.
