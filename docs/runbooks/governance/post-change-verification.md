---
title: Post-Change Verification Protocol
doc_type: runbook
status: approved
audience: agents_and_humans
owners: [kgale]
last_validated: 2026-04-05
---

# Post-Change Verification Protocol

Mandatory verification after Tier 0, 1, and 2 changes. Uses health-check endpoints from the [enriched service inventory](<../../design/architecture/data/service-inventory.json>).

---

## Tier 0/1 Verification (Host/Foundational + Connectivity/Fabric)

1. **Wait 30 seconds** after the change completes to allow services to stabilize.

2. **For EACH dependent service** identified during the [pre-flight checklist](<./pre-flight-checklist.md>) step 2:
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
- Document what failed and why in an [incident postmortem](<./incident-postmortem-template.md>) if the outage lasted more than 15 minutes or affected users

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

## Tier 3/4 — No Verification Required (service health)

Tier 3 (Logic/Workflow) and Tier 4 (Schema/Metadata) changes do not require post-change *service health* verification. Standard dry-run/sandbox testing (Tier 3) or direct commit (Tier 4) per the taxonomy.

**Note**: Tier 3/4 changes may still trigger the **rebaseline obligation** below if the change touches an audited surface. The two obligations are independent — a Tier 3 prompt edit doesn't need service-health verification, but if it's an OpenClaw agent prompt (`scripts/openclaw/agents/*/AGENTS.md`) then it touches the `openclaw-config.txt` audit baseline and the rebaseline is required.

---

## Post-Change Rebaseline (audited surfaces, #557)

Separate from the service-health verification above, ANY change that touches an **audited surface** (per `docs/design/architecture/data/audited-surfaces.json`) requires resetting the security-monitor baselines on office2 after the change deploys. Otherwise the daily 3 AM audit alerts as drift on the now-expected state, producing alert fatigue and burying real drift.

**Trigger classes** (any of these → rebaseline required):

- OpenClaw agent prompts (`AGENTS.md`, `SOUL.md`, `IDENTITY.md`, `USER.md`, `GOVERNANCE.md` under `scripts/openclaw/agents/`)
- OpenClaw runtime config (`scripts/openclaw/openclaw*.json`)
- Systemd user units + deploy scripts (`scripts/office2/*.{service,timer,target,path}` + `scripts/office2/deploy/*.sh`)
- Python dependency manifests (`requirements*.txt`, `pyproject.toml`)
- Docker compose / Dockerfile changes
- Committed SSH key material

The full enumeration with affected baselines per surface is in `docs/design/architecture/data/audited-surfaces.json`.

**Reset procedure** (canonical):

```bash
ssh office2-claude 'rm /data/services/security-monitor/baselines/* && sg docker -c /data/services/security-monitor/scripts/audit.sh'
```

**Verification**:

```bash
ssh office2-claude 'ls /data/services/security-monitor/baselines/ | wc -l'
# Expected: 14
ssh office2-claude 'tail -5 /data/services/security-monitor/logs/audit-$(date +%Y-%m-%d).log'
# Expected: AUDIT COMPLETE: All clear
```

Full runbook: [`security-baseline-ops.md`](<../security-baseline-ops.md>).

**Reminder surfaces** (the operator is responsible for running the actual command on office2 — neither CI nor the charter can perform the reset itself):

- `.github/workflows/audited-surface-reminder.yml` — CI soft-reminder annotates PRs/pushes that touch audited-surface paths
- `.kittify/charter/charter.md` § Rebaseline obligation — spec-kitty mission-end gate
- `.github/ISSUE_TEMPLATE/feature.md` § Architecture Impact / Rebaseline — issue-template prompt
- `.github/ISSUE_TEMPLATE/infra.md` § Architecture Impact / Rebaseline — issue-template prompt
