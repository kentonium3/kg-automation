---
title: Security Baseline Operations
doc_type: runbook
audience: agents_and_humans
status: approved
created: 2026-05-27
last_validated: 2026-05-27
last_updated: '2026-05-27'
version: v1.0
owners: [kgale]
---

# Security Baseline Operations

The daily security audit at 3 AM on office2 compares the live system
against a set of baselines and emits an alert when anything drifts.
After any intentional change to the audited surface — a new service,
an updated container image, a new cron entry, a config edit picked up
by one of the checks — the baselines must be regenerated so subsequent
runs don't alert on the now-expected state.

This runbook is the canonical procedure. Service-specific runbooks
(vikunja-ops, openclaw-ops, etc.) link here and only document
**when** their service needs a reset, not how.

## Locations

- **Audit script**: `/data/services/security-monitor/scripts/audit.sh`
- **Baselines**: `/data/services/security-monitor/baselines/`
- **Logs**: `/data/services/security-monitor/logs/audit-YYYY-MM-DD.log`
- **Alerts**: `/data/services/security-monitor/logs/alerts-YYYY-MM-DD.log`
- **Drift events** (consumed by doc-audit): `/data/services/security-monitor/logs/drift-events.jsonl`

## What the audit checks

| Check | Baseline file |
|---|---|
| Python `.pth` startup-hijack files | `pth-files.txt` |
| System pip package list | `pip-packages.txt` |
| Homebrew packages + taps | `brew-packages.txt`, `brew-taps.txt` |
| Docker images | `docker-images.txt` |
| Listening ports | `listening-ports.txt` |
| Enabled systemd services (system + user) | `enabled-services.txt`, `systemd-user-units.txt`, `systemd-user-dropins.txt` |
| SSH `authorized_keys` | `ssh-keys.txt` |
| `/etc/hosts` (hash) | `hosts-hash.txt` |
| Crontabs | `crontabs.txt` |
| OpenClaw cron + config | `openclaw-cron.txt`, `openclaw-config.txt` |

## Reset procedure

Run as the `claude` user on office2 via `ssh office2-claude`. The
`sg docker -c` wrapper supplies the docker group needed for the image diff.

```bash
ssh office2-claude 'rm /data/services/security-monitor/baselines/* && sg docker -c /data/services/security-monitor/scripts/audit.sh'
```

Expected output on success: `Security audit YYYY-MM-DD: All clear` and
14 baseline files freshly written in `baselines/`.

## Verifying the reset

```bash
ssh office2-claude 'ls /data/services/security-monitor/baselines/ | wc -l'
ssh office2-claude 'tail -5 /data/services/security-monitor/logs/audit-$(date +%Y-%m-%d).log'
```

Expect 14 files and an `AUDIT COMPLETE: All clear` line stamped near
the time of the reset.

## When to reset

The audit is the authority on "the system changed unexpectedly." Reset
the baselines after any **intentional** change to one of the audited
surfaces. Service runbooks list specific triggers:

- Vikunja deploy / image upgrade → [vikunja-ops.md](vikunja-ops.md#security-baseline-trigger)
- OpenClaw deploy / config change → [openclaw-ops.md](openclaw-ops.md#security-baseline-trigger)
- New service added per [deployment.md](deployment.md)
- Bulk repo changes that touch `openclaw-config.txt` content (e.g.,
  agent-config sweeps)

If you see drift alerts and aren't sure whether the change is
intentional, inspect `logs/alerts-YYYY-MM-DD.log` for the diff before
resetting.

## Interaction with doc-audit (drift-events.jsonl)

The audit writes to the same `drift-events.jsonl` that the doc-audit
driver reads. A baseline reset itself does **not** emit drift events
(the audit sees no prior baseline to diff against). New drift events
only fire on subsequent real changes.

## Related documents

- [office2 Backup and Security Model](../design/office2-backup-and-security.md) — overall security posture and audit context
- [Security Posture (architecture)](../design/architecture/security-posture.md) — change-control tiers + audit surface table
- [Deployment Runbook](deployment.md) — when a feature deploy should trigger a reset
