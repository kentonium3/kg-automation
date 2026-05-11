---
work_package_id: WP08
title: Architecture documentation
dependencies:
- WP07
requirement_refs:
- C-007
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T033
- T034
- T035
history:
- event: created
  at: '2026-05-11T21:43:38Z'
  by: 'spec-kitty.tasks (auto-drive via #115)'
authoritative_surface: docs/design/architecture/
execution_mode: code_change
owned_files:
- docs/design/architecture/data/service-inventory.json
- docs/design/architecture/service-inventory.md
- docs/design/architecture/credentials-and-secrets.md
tags: []
---

# WP08 — Architecture documentation

## Objective

Update the live architecture documents to reflect the deployed credential-health-check service per C-007. JSON is authoritative; the markdown narratives match.

## Context

- **Spec** anchors: C-007 (same-change-set arch-doc update); SC-005 (Kent can operate from the runbook only — the quickstart.md is in scope but the runbook proper is the doc inventory the auditor cross-references).
- **Plan** anchor: project structure §"Source Code (repository root)" lists the three doc files.
- **Prior art**: my earlier this-session commit `dbdfafc` added `obsidian-sync-heartbeat` to the same JSON; matches the new-cron-entry pattern exactly.

## Branch Strategy

- **Planning/base branch**: `main`
- **Merge target branch**: `main`
- This WP runs in a lane-allocated worktree; merges to `main`.

## Subtasks

### T033 — Add `credential-health-check` entry to `service-inventory.json`

**Purpose**: Authoritative JSON record for the new service.

**Steps**:

1. Open `docs/design/architecture/data/service-inventory.json`.
2. Add a new `services[]` entry, modeled on the existing `felix-doc-auditor` entry, placed adjacent to it for related-services grouping:
   ```json
   {
     "name": "credential-health-check",
     "type": "systemd-timer",
     "host": "office2",
     "user": "claude",
     "systemd_unit": "credential-health-check.timer (user unit) + credential-health-check.service (user oneshot)",
     "systemd_user": "claude",
     "schedule": "daily 13:00 UTC (OnCalendar=*-*-* 13:00:00, Persistent=true)",
     "exec_start": "/usr/bin/python3 -m credential_health_check --manifest /home/claude/kg-automation/docs/design/architecture/data/credential-manifest.json",
     "timeout_seconds": 600,
     "timeout_seconds_note": "TimeoutStartSec=10min systemd outer failsafe; expected cycle <10 seconds (NFR-001).",
     "deployed_by": "#115",
     "deployed_on": "<DATE_OF_WP07_DEPLOY>",
     "updated_by": "#115",
     "status": "active",
     "purpose": "Daily credential expiry health check. Reads credential-manifest.json; for fixed-cadence credentials, alerts when last_reviewed + cadence is within 30 days. For monitor-activity credentials, alerts when activity signal drifts. Files paired GitHub issue + Vikunja task (due_date = boundary - 7 days). Closes R-003.",
     "risk_tier": 3,
     "dependencies": [
       {"target": "credential-manifest.json", "type": "requires", "description": "Source of truth for tracked credentials"},
       {"target": "gh-cli", "type": "requires", "description": "GitHub issue filing as kg-felix-bot"},
       {"target": "vikunja-api", "type": "requires", "description": "Vikunja task filing via API token"},
       {"target": "tailscale", "type": "requires", "description": "tailscale status --json for tailscale-auth signal"},
       {"target": "openclaw-gateway:18789", "type": "requires", "description": "openclaw channels status for whatsapp-session signal"}
     ],
     "health_check": {
       "method": "journal",
       "endpoint": "journalctl --user -u credential-health-check --since today",
       "expected": "cycle_end event present from the most recent 13:00 UTC tick",
       "timeout_seconds": 5
     },
     "config_files": [
       {"path": "~/.config/systemd/user/credential-health-check.timer", "format": "systemd-unit", "source_in_repo": "scripts/office2/credential-health-check.timer"},
       {"path": "~/.config/systemd/user/credential-health-check.service", "format": "systemd-unit", "source_in_repo": "scripts/office2/credential-health-check.service"},
       {"path": "/home/claude/kg-automation/scripts/security/credential_health_check/", "format": "python-package", "source_in_repo": "scripts/security/credential_health_check/"}
     ]
   }
   ```
3. Bump top-level `last_updated` to today's date.
4. Extend top-level `updated_by` to include `+ #115-credential-health-check`.

**Files**: `docs/design/architecture/data/service-inventory.json` (modify).

**Validation**:

- `python -c "import json; json.load(open('docs/design/architecture/data/service-inventory.json'))"` succeeds.
- `python tooling/scripts/validate_docs.py` passes.

---

### T034 — Update `service-inventory.md` narrative

**Purpose**: Match the JSON in the human-readable view.

**Steps**:

1. Add a row to the §Scheduled Jobs table:
   ```
   | Credential Health Check | Daily 13:00 UTC | `credential-health-check.timer` (systemd) → python3 -m credential_health_check | claude | Daily credential expiry + activity-signal audit; R-003 |
   ```
2. Add a detail section, modeled on §"Felix Doc Auditor (#105, 2026-05-10)":
   ```markdown
   ### Credential Health Check (#115)
   - **Deployed by**: #115
   - **Type**: systemd user timer + oneshot service (no LLM — pure deterministic script)
   - **Schedule**: daily 13:00 UTC via `credential-health-check.timer` (`OnCalendar=*-*-* 13:00:00`, `Persistent=true`)
   - **Per-tick invocation**: `credential-health-check.service` runs `/usr/bin/python3 -m credential_health_check --manifest /home/claude/kg-automation/docs/design/architecture/data/credential-manifest.json`
   - **Source in repo**: `scripts/security/credential_health_check/` (package: `__init__.py`, `manifest.py`, `cadence.py`, `signals.py`, `github_writer.py`, `vikunja_writer.py`, `orchestrator.py`, `__main__.py`)
   - **Purpose**: closes R-003 — automated credential expiry/cadence tracking. For fixed-cadence credentials, alerts 30 days before review boundary. For `monitor-activity` credentials, alerts on activity-signal drift.
   - **Alert path**: paired GitHub issue + Vikunja task. Issue is the audit trail; task `due_date = boundary - 7 days` drives the existing escalation engine's WhatsApp pressure window. Activity-staleness alerts are GitHub-only (no task — drift is "look at it now," not "rotate by date").
   - **Quickstart / runbook**: `kitty-specs/credential-expiry-health-check-01KRCF92/quickstart.md` (mission-local; should be promoted to `docs/runbooks/credential-health-check-ops.md` in a follow-up if operational learnings accumulate).
   ```

**Files**: `docs/design/architecture/service-inventory.md` (modify).

---

### T035 — Update `credentials-and-secrets.md` Security Posture cross-reference

**Purpose**: Make the live narrative aware that credentials are now automatically tracked.

**Steps**:

1. Open `docs/design/architecture/credentials-and-secrets.md`.
2. In §Security Posture, append a paragraph (or insert before "**Known risk**"):
   ```markdown
   **Credential expiry health check (R-003 closure)**: As of #115, an automated daily check (`credential-health-check.service` on office2) reads this manifest, evaluates each credential's `review_cadence` and `last_reviewed`, and files a paired GitHub issue + Vikunja task when a credential is within 30 days of its cadence boundary. `monitor-activity` credentials (`tailscale-auth`, `whatsapp-session`) are evaluated against live activity signals and alerted on drift. See `kitty-specs/credential-expiry-health-check-01KRCF92/` for the design and `scripts/security/credential_health_check/` for the implementation.
   ```
3. Bump frontmatter `last_updated` to today, append `+ #115` to `updated_by`.

**Files**: `docs/design/architecture/credentials-and-secrets.md` (modify).

---

## Definition of Done

- All three subtasks complete.
- JSON validates: `python -c "import json; json.load(open('docs/design/architecture/data/service-inventory.json'))"` exits 0.
- Markdown validates: `python tooling/scripts/validate_docs.py` exits 0.
- Service inventory has a new `credential-health-check` entry.
- Service inventory narrative has a row + detail section.
- Credentials-and-secrets has a Security Posture paragraph cross-referencing the auditor.
- Commit prefix: `docs(security):` or `docs(WP08):` referencing #115.

## Risks

- **Stale `deployed_on`**: T033 sets `deployed_on` to "the day WP07 was actually executed." If WP08 lands before WP07 (out-of-dependency-order — shouldn't happen given the dependency graph), use the date the implementing agent expects WP07 to land (or the WP08 commit date as a fallback). Spec-kitty's lane ordering should prevent this.
- **R-003 status sync**: marking R-003 as closed lives in `docs/archive/risk-register.md` (archived). The Security Posture paragraph here is the active reference; don't touch the archived file.

## Reviewer guidance

- Verify: the JSON entry's `health_check.endpoint` is `journalctl --user -u credential-health-check --since today` — matches R-002.
- Verify: top-level `last_updated` is bumped on both `service-inventory.json` and `credentials-and-secrets.md`.
- Verify: the Scheduled Jobs row in `service-inventory.md` uses the systemd-timer-friendly description ("`credential-health-check.timer` (systemd) → python3 -m …"), not the old "OpenClaw cron" pattern.
- Verify: no implementation detail leaks into the `purpose` field — keep it user-facing.

## Suggested implement command

```bash
spec-kitty agent action implement WP08 --agent <name>
```
