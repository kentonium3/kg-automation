---
work_package_id: WP04
title: Architecture data, docs and runbook for the dead-man pings
dependencies:
- WP01
requirement_refs:
- FR-008
- FR-009
- C-001
- C-002
- C-003
- SC-002
planning_base_branch: feat/offhost-deadman-pings
merge_target_branch: feat/offhost-deadman-pings
branch_strategy: Planning artifacts for this mission were generated on feat/offhost-deadman-pings. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/offhost-deadman-pings unless the human explicitly redirects the landing branch.
subtasks:
- T011
- T012
- T013
history:
- at: '2026-10-15T18:00:00Z'
  actor: tasks
  action: Prompt generated via /spec-kitty.tasks
agent_profile: python-pedro
authoritative_surface: docs/
create_intent:
- tests/docs/test_deadman_docs.py
execution_mode: code_change
model: claude-opus-5-5
owned_files:
- docs/design/architecture/data/credential-manifest.json
- docs/design/architecture/data/data-flows.json
- docs/design/architecture/data/service-inventory.json
- docs/design/architecture/observability-and-alerting.md
- docs/runbooks/canary-registry-ops.md
- tests/docs/test_deadman_docs.py
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP04 – Architecture data, docs and runbook

## ⚡ Do This First: Load Agent Profile

Use the `/spk-charter-profile-load` skill to load the agent profile specified in the frontmatter, and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `python-pedro`
- **Role**: `implementer`
- **Agent/tool**: `claude`

---

## ⚠️ IMPORTANT: Review Feedback

Check `review_ref` via `spec-kitty agent tasks status`; address every item; record progress with `spec-kitty agent tasks add-history <WP> --note "..."`.

---

## Branch Strategy

- **Planning base branch**: `feat/offhost-deadman-pings` · **Merge target branch**: `feat/offhost-deadman-pings`. Worktrees come from `lanes.json`.

## Context

- **Inputs:** `plan.md` (rounds 3 and 4), `data-model.md` and `quickstart.md`.
- **Variable names** (from WP01): `FELIX_DEADMAN_CANARY_URL`, `FELIX_DEADMAN_HEALTHCHECK_URL`. Env file: `/home/claude/.config/felix/deadman/env`.
- **Entries to mirror:**
  - credential: `felix-alert-ntfy-topic` in `credential-manifest.json`;
  - flow: `felix-deployer-ntfy-egress` in `data-flows.json`.
- **Validator:** `tooling/scripts/validate_architecture_data.py`. Date sanity requires bumping each touched file's `last_updated` to 2026-10-15.
- **Placeholders only:** never write a real URL. Use `https://hc-ping.com/<uuid>`.

## Subtasks

### T011 – Architecture data

- **`credential-manifest.json`:**
  - New `felix-deadman-ping-urls`, type `env-file`.
  - `storage` names the path; `used_by` is `[felix-canary, felix-health-check]`; owner `claude:claude`, mode `0600`.
  - `notes`: these are capability URLs. Knowing one lets someone spoof "up", so a leak means rotation. They are read only by `scripts/common/deadman.py` and never put in the environment. They are provisioned by Kent with `read -rsp` through `ssh -t office2-claude`.
  - `expiry_notes`: rotate by regenerating the ping URL in healthchecks.io and re-running the provisioning one-liner.
  - Separately: add `felix-canary` to `felix-alert-ntfy-topic.used_by`, which is a pre-existing omission. The canary's unit loads that file.
- **`data-flows.json`:**
  - New flow `deadman-ping-egress`. Source: felix-canary and felix-health-check on office2. Destination `hc-ping.com` (healthchecks.io), HTTPS GET.
  - Frequency: every canary tick (15 min) and every health-check run (11:00 and 23:00 UTC).
  - Payload: none (the path only).
  - Also a flow, or a note on it, for the read-only `ntfy.sh/v1/health` probe.
  - Purpose: off-host dead-man (#1069). healthchecks.io emails Kent, never through ntfy.
- **`service-inventory.json`:** append one sentence to the felix-canary and felix-health-check notes saying each pings its dead-man check, and prepend `offhost-deadman-pings-01M50990 (#1077 — …)` to `updated_by`.
- Bump `last_updated` in each touched file.

### T012 – Docs

- **`observability-and-alerting.md` §5a "Who watches the watcher":** add a short subsection on the off-host dead-man. Cover:
  - the shared-fate gap it closes;
  - healthchecks.io emails, never ntfy;
  - success versus fail semantics (liveness plus channel health: topic configured, ntfy healthy, this run's deliveries);
  - the accepted residuals: a revoked or mistyped topic on a healthy server surfaces at the next real alert; a lost double ping gives one false email.
  - Link #1069 and #1077. Update the line that calls the off-host watchdog deferred.
- **`canary-registry-ops.md`:** new section "Off-host dead-man pings (#1077)", covering:
  - the two checks and their schedules: canary simple 15 min / 45 min grace; health-check Cron `0 11,23 * * *` UTC / 1 h grace;
  - provisioning: the exact `ssh -t office2-claude 'umask 077; …'` one-liner from `quickstart.md`;
  - verification: journal `grep deadman`, and the dashboard shows the ping;
  - the fail-email test: `cd ~/kg-automation && python3 -m scripts.common.deadman --label canary --outcome fail`;
  - pausing: pause the check in healthchecks.io during planned office2 downtime;
  - rotation;
  - reading a `fail` email: check `journalctl --user -u felix-canary.service | grep deadman` for the reason (`topic_missing`, `ntfy_unhealthy`, `undelivered`, or a runner error).

### T013 – Docs test (`tests/docs/test_deadman_docs.py`)

- The runbook names both variables, the env path, `--outcome fail`, and `0 11,23 * * *`.
- `credential-manifest.json` has `felix-deadman-ping-urls`, with `used_by` covering both watchers.
- `data-flows.json` has a flow whose destination mentions `hc-ping.com`.
- No file in `docs/` contains `hc-ping.com/` followed by a UUID-shaped string; this guards against a leaked real URL.

## Definition of Done

- The validator reports 0 findings. `validate_docs` and `check_doc_links` are OK.
- `TMPDIR=/dev/shm .venv/bin/python3 -m pytest tests/docs -q` passes.
