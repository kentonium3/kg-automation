---
title: Post-Change Verification Protocol
doc_type: runbook
status: approved
audience: both
owners: [kgale]
last_validated: 2026-04-05
---

# Post-Change Verification Protocol

Mandatory verification after Tier 0, 1, and 2 changes. Uses health-check endpoints from the [enriched service inventory](../../design/architecture/data/service-inventory.json).

---

## Tier 0/1 Verification (Host/Foundational + Connectivity/Fabric)

1. **Wait 30 seconds** after the change completes to allow services to stabilize.

2. **For EACH dependent service** identified during the [pre-flight checklist](pre-flight-checklist.md) step 2:
   - Run its health-check endpoint (from `service-inventory.json`)
   - Compare result against `health_check.expected` value
   - Record: service name, endpoint, expected, actual, pass/fail

3. **Tier 1 connectivity confirmation**: run `tailscale status` and verify all expected devices show as connected. Check that Tailscale Serve endpoints respond.

4. **If ANY health check fails**: trigger rollback immediately (see Rollback Trigger below).

5. **If ALL health checks pass**: change is verified. Document the result.

---

## Tier 2 Verification (Application/State)

1. **Run the affected service's health-check endpoint** (from `service-inventory.json`).
2. **Verify** the response matches `health_check.expected`.
3. **If health check fails within 5 minutes**: restore from the backup confirmed during pre-flight, or restart the service.

---

## Rollback Trigger Condition

> **If any dependent service's health check fails within 5 minutes of the change, execute the pre-defined rollback procedure immediately.**

Do NOT wait for the service to recover on its own. Execute the rollback procedure documented during the pre-flight checklist. After rollback, re-run all verification steps to confirm services are healthy.

**After rollback**:
- Confirm all dependent services pass their health checks
- Document what failed and why in an [incident postmortem](incident-postmortem-template.md) if the outage lasted more than 15 minutes or affected users

---

## Health Check Methods

Per the enriched service inventory, services declare their health-check method:

| Method | How to verify | Example |
|---|---|---|
| `http` | `curl -s -o /dev/null -w '%{http_code}' <endpoint>` | Vikunja: `http://100.92.197.90:3456/api/v1/info` → 200 |
| `tcp` | `nc -z <host> <port>` | Port connectivity check |
| `systemd-status` | `systemctl --user status <unit>` or `systemctl status <unit>` | OpenClaw: `systemctl --user status openclaw-gateway` → active |
| `shell` | Run the specified command | Restic: `restic snapshots --latest 1` |
| `none` | Manual verification required | Cron agents: check logs for recent execution |

---

## Tier 3/4 — No Verification Required

Tier 3 (Logic/Workflow) and Tier 4 (Schema/Metadata) changes do not require post-change verification. Standard dry-run/sandbox testing (Tier 3) or direct commit (Tier 4) per the taxonomy.
