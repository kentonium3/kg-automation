---
title: Crontab Recovery
doc_type: runbook
audience: agents_and_humans
status: approved
created: 2026-08-28
last_validated: 2026-08-28
last_updated: '2026-08-28'
version: v1.0
owners: [kgale]
---

# Crontab Recovery

How to restore the `claude` crontab on office2 after it is lost.

This exists because it happened. On 2026-08-27 the crontab was destroyed along
with `/home/claude`, and the only surviving copy was
`/data/services/security-monitor/baselines/crontabs.txt` — a file the security
audit writes for *drift detection*, not as a backup, and one the documented
rebaseline procedure deletes as its first action. Recovery depended on a file
that exists for an unrelated reason (#895).

## Scope

**The `claude` crontab only.** `crontab -u kgale -l` and `crontab -u root -l`
both return permission denied to an unprivileged reader, so those crontabs are
not captured by anything and are not recoverable by this procedure.

## Recover from the live artifact (normal case)

An hourly timer captures the crontab to
`/data/services/host-state/crontabs/claude.crontab`. That path is on a different
tree from `/home/claude`, so it survives the failure that motivated this runbook.

Check what you are about to install:

```bash
ssh office2-claude 'cd /home/claude/kg-automation && python3 scripts/office2/crontab_capture.py --emit-body'
```

Then install it:

```bash
ssh office2-claude 'cd /home/claude/kg-automation && python3 scripts/office2/crontab_capture.py --emit-body | crontab -'
```

Confirm:

```bash
ssh office2-claude 'crontab -l'
```

`--emit-body` strips the provenance header using the same parser that wrote it,
so there is nothing to hand-type and nothing that can drift out of step with the
header format.

## ⚠️ Do not hand-strip the header

Older material — including the `#895` mission quickstart — documents this form:

```
grep -v "^# captured-\|^# source-\|^# NOTE:\|^#       " …
```

**It is wrong and must not be used.** It predates the sentinel-delimited header
and leaves two lines behind. Two consequences, both landing during an incident:

- Used to *verify*, it reports a difference and makes a working capture look
  broken.
- Used to *recover*, it installs a crontab carrying two stray comment lines,
  which the next hourly capture absorbs as body — so the header grows on every
  recovery cycle.

This is #906. Use `--emit-body`.

## Recover from a snapshot (when `/data` is also gone)

The artifact rides the nightly Restic backup because it lives under
`/data/services/`, an existing source path.

Restoring needs sudo: `/etc/restic/password` is root-only, so the `claude`
account cannot open the repository at all.

```bash
sudo restic -r /mnt/backups/restic-repo \
  --password-file /etc/restic/password \
  restore latest --target /tmp/crontab-recovery \
  --include /data/services/host-state
```

Then emit and install from the restored copy:

```bash
python3 /home/claude/kg-automation/scripts/office2/crontab_capture.py \
  --emit-body --artifact-path /tmp/crontab-recovery/data/services/host-state/crontabs/claude.crontab | crontab -
```

## If `--emit-body` refuses

It fails closed on purpose. A refusal means the artifact is missing, empty, or
does not carry a recognisable header — and emitting an unverified body would
install wrong content silently, which is worse than stopping. Read the stderr
message; then fall back to the snapshot path above, or transcribe by hand from
the artifact after inspecting it.

## Related

- [Security Baseline Operations](<./security-baseline-ops.md>) — the rebaseline
  procedure, whose destructive step is why the baseline is not a backup.
- [Restic Backup Operations](<./restic-backup-ops.md>) — the backup this
  artifact rides on.
