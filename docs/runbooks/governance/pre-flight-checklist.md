---
title: Pre-Flight Change Checklist
doc_type: runbook
status: approved
audience: agents_and_humans
owners: [kgale]
last_validated: 2026-04-13
---

# Pre-Flight Change Checklist

Mandatory assessment before Tier 0, 1, and 2 changes per the [change-risk taxonomy](<../../design/architecture/data/change-risk-taxonomy.json>). Referenced from [CLAUDE.md](../../../CLAUDE.md) guardrail rules and [change-control.md](<../../design/architecture/change-control.md>).

---

## Tier 0/1 Checklist (Full — Mandatory for Host/Foundational and Connectivity/Fabric changes)

Complete ALL steps before executing the change:

- [ ] **1. Identify affected ports/interfaces** — list every port, network interface, or service endpoint this change touches. For UFW/iptables changes, enumerate ALL ports affected (including implicitly blocked ports).

- [ ] **2. Query service inventory for dependent services** — for each affected port/interface, look up `docs/design/architecture/data/service-inventory.json`. Search the `dependencies` array of each service for entries whose `target` matches the affected port/interface. List every service that `requires` the affected resource.

- [ ] **3. Note health-check endpoints** — for each dependent service identified in step 2, record its `health_check.endpoint` and `health_check.expected` values from the inventory. These will be used for post-change verification.

- [ ] **4. Document rollback procedure** — write the exact commands to undo this change. For UFW: the previous rule set. For Tailscale: the previous serve configuration. For Docker: the previous compose/env state. The rollback must be executable without further investigation.

- [ ] **5. Confirm operator availability** — Kent must be present and able to respond to issues before the change is applied. This is NOT a maintenance window — it is an availability check appropriate for a solo operator. If Kent is unavailable, defer the change.

- [ ] **6. Define post-change verification plan** — list which health checks to run (from step 3), in what order, and what constitutes success. Reference the [post-change verification protocol](<./post-change-verification.md>).

---

## Tier 2 Checklist (Lighter — Mandatory for Application/State changes)

- [ ] **1. Confirm recent backup exists** — single command, freshness-checked against the health pointer at `/data/services/backup/state/last-backup.json` (introduced in #511). Pass = exit 0 with an `OK …` line:

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

  Freshness budget is 28 hours (24 h cadence + 4 h slack). A pointer that exists but is stale or carries a failed exit code MUST fail. If the check fails, do NOT use `--backup-confirmed` to attest around it — investigate per [`docs/runbooks/restic-backup-ops.md`](<../restic-backup-ops.md>).

  Deploy scripts continue to accept `--backup-confirmed` as an operator attestation flag, but the attestation should be made on the basis of the check above, not log-scraping.

- [ ] **2. Note affected service's health-check endpoint** — from `service-inventory.json`, record the service's `health_check.endpoint` and `health_check.expected`.

- [ ] **3. Have rollback plan** — restart the service (`systemctl restart <unit>`), or restore from the Restic backup verified in step 1.

---

## Tier 3/4 — No Checklist Required

Tier 3 (Logic/Workflow) and Tier 4 (Schema/Metadata) changes do not require a pre-flight checklist. Apply the standard or auto-commit guardrail protocol per the taxonomy.

---

## Example: UFW Rule Change (Tier 0)

**Scenario**: Agent asked to add a UFW rule allowing port 8080.

1. **Affected ports**: port 8080 on all interfaces (or specific interface)
2. **Dependent services**: query inventory → any service with `dependencies[].target` matching port 8080? If none, proceed. If found, note the dependency.
3. **Health checks**: for each dependent service, record endpoint
4. **Rollback**: `ufw delete allow 8080/tcp` (or restore previous rule set)
5. **Operator availability**: Kent present? Yes → proceed. No → defer.
6. **Verification plan**: after applying, run health checks for all dependent services

**Tier 0 reminder**: Claude Code generates the UFW script but does NOT execute it. Present to Kent for manual execution via `ssh office2-kgale`.
