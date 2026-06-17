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

## Automatic rebaseline (felix-deployer)

As of mission #618, felix-deployer automatically rebaselines the
security-monitor baselines when it applies a change that touches an
audited surface. **No operator action is needed on the happy path.**

### How it works (deferred-confirm flow)

1. On each `git pull`, felix-deployer intersects the pulled commit range
   against the audited-surface registry
   (`docs/design/architecture/data/audited-surfaces.json`). If any
   audited path changed, it writes a **rebaseline-pending token** at
   `/data/services/felix-deployer/state/rebaseline-pending.json`
   recording the matched surface IDs, expected affected baselines, and
   `pending_since` timestamp.

2. On each subsequent tick while a pending token exists, the deployer
   runs a **read-only** audit (baselines present — compare mode, no
   reset) to check whether expected drift has appeared yet:

   - **Drift confined to the expected baselines** — the surface has
     deployed and its fingerprint has changed. The deployer rebaselines
     (`rm baselines/* && sg docker -c audit.sh`), verifies that the
     baseline count equals `expected_baseline_count` from the registry
     and that the audit reports clear, stamps the deploy record
     `rebaseline: completed`, and clears the token.

   - **Audit clean (no drift)** — the committed change did not alter
     the hashed content of any monitored surface (e.g. a comment-only
     edit to an audited path, or the surface already matched the
     baseline). Token is cleared with `rebaseline: not_required`.

   - **Drift extends beyond the expected baselines** — potential
     security event. The deployer does NOT auto-rebaseline; it emits an
     ntfy alert (`rebaseline_unexpected_drift`) and leaves the baselines
     intact for human review.

3. If the pending token ages past the configured max age and no drift is
   ever confirmed, the deployer emits an ntfy alert
   (`rebaseline_stale`) so a human can investigate why the surface never
   appeared to deploy.

### Observability outcomes

The outcome is recorded on the tick log
(`/data/services/felix-deployer/logs/<date>.jsonl`) and, when a deploy
record is available, on the `deploys/applied/` entry:

| Outcome | Meaning |
|---|---|
| `not_required` | No audited surface in the pulled commit range. |
| `pending_set` | Audited surface observed; pending token written; awaiting drift confirmation. |
| `completed` | Expected drift confirmed; baselines regenerated and verified healthy. |
| `cleared_clean` | Pending token cleared because the audit was clean (no drift to confirm). |
| `unexpected_drift` | Drift beyond the expected set; operator alert emitted; baselines left intact. |
| `failed` | Rebaseline attempted but verification failed (count mismatch or audit not clear); operator alert emitted; applied code left in place. |
| `stale` | Pending token exceeded max age without drift confirmation; operator alert emitted. |

### ntfy alerts

felix-deployer emits exactly one ntfy alert per event:

| Topic suffix | Trigger |
|---|---|
| `rebaseline_failed` | Regeneration failed or baseline-count mismatch after a rebaseline attempt. |
| `rebaseline_unexpected_drift` | Observed drift extends beyond the expected baseline set. |
| `rebaseline_stale` | Pending token aged out without drift confirmation. |

### When a human is still involved

- **Out-of-band changes** — a change made directly on office2, bypassing
  felix-deployer, is invisible to the automatic flow. The daily security
  audit surfaces it as drift. Investigate, then reset manually (see the
  manual procedure below).

- **Unexpected drift** — if the `unexpected_drift` alert fires, do not
  auto-reset. Inspect the alert and the audit log to determine whether
  the drift is a security event or a misconfiguration before deciding
  whether to reset.

- **Rebaseline failed** — if the `rebaseline_failed` alert fires, the
  applied code is in place and working, but the baseline reset failed.
  Investigate and reset manually once the root cause is clear.

## Manual reset procedure (fallback)

Use this for out-of-band changes, after a `rebaseline_failed` alert,
or whenever the automatic flow cannot run. Run as the `claude` user on
office2 via `ssh office2-claude`. The `sg docker -c` wrapper supplies
the docker group needed for the image diff.

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

The audit is the authority on "the system changed unexpectedly." On the
happy path (changes via felix-deployer), the reset is automatic. For
out-of-band changes or post-alert recovery, reset manually after any
**intentional** change to one of the audited surfaces. Service runbooks
list specific triggers:

- Vikunja deploy / image upgrade → [vikunja-ops.md](vikunja-ops.md#security-baseline-trigger)
- OpenClaw deploy / config change → [openclaw-ops.md](openclaw-ops.md#security-baseline-trigger)
- New service added per [deployment.md](deployment.md)
- Bulk repo changes that touch `openclaw-config.txt` content (e.g.,
  agent-config sweeps)

If you see drift alerts and aren't sure whether the change is
intentional, inspect `logs/alerts-YYYY-MM-DD.log` for the diff before
resetting.

## Integration verification (post-merge canary)

This section documents the explicit integration verification for mission
#618. A pre-merge live smoke is impossible because the auto-rebaseline
code goes live on office2 only on the felix-deployer tick *after* the
mission merges. The verification is an **operator-run post-merge canary**
against the real office2 service state. Its outcome is the mission's
**merge acceptance criterion**: the merge commit (or its closing-issue
comment) must record the canary result alongside the Rebaseline note.

### SC-001 / SC-003 — happy path and not-required path

**After the next real audited-surface deploy via felix-deployer:**

1. Inspect the tick log for the deploy that landed the audited-surface
   change:
   ```bash
   ssh office2-claude 'tail -50 /data/services/felix-deployer/logs/$(date +%Y-%m-%d).jsonl'
   ```
2. Confirm the tick sequence shows `pending_set` followed (on a later
   tick) by `completed`.
3. Confirm baselines are healthy:
   ```bash
   ssh office2-claude 'ls /data/services/security-monitor/baselines/ | wc -l'
   ```
   Expect the count to equal `expected_baseline_count` from
   `docs/design/architecture/data/audited-surfaces.json` (currently 14).
4. Confirm no operator action was needed (no manual reset command was
   run).

**For a deploy that touches no audited surface:**

1. Check the tick log entry for the manifest.
2. Confirm outcome is `not_required` (no pending token written, no reset
   attempted).

### SC-002 — next scheduled audit clean

After the auto-rebaseline completed (SC-001), wait for the next 3 AM
daily security audit and confirm:

```bash
ssh office2-claude 'tail -10 /data/services/security-monitor/logs/audit-$(date +%Y-%m-%d).log'
```

Expect `AUDIT COMPLETE: All clear` with no drift attributed to the
intentional change. Zero false-positive drift alerts.

### SC-004 — simulated failure path

To exercise the failure path without a real failure, the operator can:

1. Temporarily set an incorrect `expected_baseline_count` in a test
   copy of `audited-surfaces.json`, or arrange for the audit to return
   non-zero after a rebaseline (e.g. temporarily corrupt one baseline
   file).
2. Trigger a rebaseline by landing an audited-surface change.
3. Observe the tick log for `failed` outcome.
4. Confirm exactly one ntfy alert with topic `rebaseline_failed` was
   emitted.
5. Confirm the deploy record carries a `failed` annotation.
6. Confirm the applied code is still in place (no rollback).
7. Restore the correct `expected_baseline_count` and reset manually.

Alternatively, inspect the unit tests in `tests/deploy/test_rebaseline.py`
which cover all failure branches with mocked audit and notification
dispatch — the SC-004 live canary is the confirmation that the mocked
behavior matches real office2.

## Interaction with doc-audit (drift-events.jsonl)

The audit writes to the same `drift-events.jsonl` that the doc-audit
driver reads. A baseline reset itself does **not** emit drift events
(the audit sees no prior baseline to diff against). New drift events
only fire on subsequent real changes.

## Related documents

- [office2 Backup and Security Model](../design/office2-backup-and-security.md) — overall security posture and audit context
- [Security Posture (architecture)](../design/architecture/security-posture.md) — change-control tiers + audit surface table
- [Deployment Runbook](deployment.md) — when a feature deploy should trigger a reset
