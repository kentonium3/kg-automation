---
work_package_id: WP06
title: Living documentation
dependencies:
- WP04
requirement_refs:
- FR-014
- C-006
- C-007
- NFR-004
- NFR-005
planning_base_branch: fix/crash-loop-unit-alerting
merge_target_branch: fix/crash-loop-unit-alerting
branch_strategy: Planning artifacts for this mission were generated on fix/crash-loop-unit-alerting. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/crash-loop-unit-alerting unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-crash-loop-unit-alerting-01M858E8
base_commit: 48d7a59eb2d1596c8a30c42679120eca8508cf04
created_at: '2026-11-24T00:10:47.207420+00:00'
subtasks:
- T023
- T024
- T025
- T026
history:
- at: '2026-11-23T23:40:00Z'
  actor: tasks
  action: Prompt generated via /spec-kitty.tasks
agent_profile: curator-carla
authoritative_surface: docs/
create_intent: []
execution_mode: code_change
model: claude-opus-5-5
owned_files:
- docs/design/architecture/data/service-inventory.json
- docs/design/architecture/service-inventory.md
- docs/design/architecture/data/data-flows.json
- docs/design/architecture/data-flows.md
- docs/design/architecture/service-dependencies.view.md
- docs/design/architecture/observability-and-alerting.md
- docs/design/felix-capability-roadmap.md
- docs/runbooks/canary-registry-ops.md
- docs/INDEX.md
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP06 – Living documentation

## ⚡ Do This First: Load Agent Profile

Use the `/spk-charter-profile-load` skill to load the agent profile specified in the frontmatter, and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `curator-carla`
- **Role**: `implementer`
- **Agent/tool**: `claude`

---

## ⚠️ IMPORTANT: Review Feedback

Check `review_ref` via `spec-kitty agent tasks status`; address every item; record progress with `spec-kitty agent tasks add-history <WP> --note "..."`.

---

## Objective

Meet FR-014 and C-007: the repo's standing architecture-docs requirement and `signal-to-doc-map.json` classes `service-added-or-modified`, `data-flow-added-or-modified` and `runbook-modified`. The architecture data, the narrative views, the canary runbook and the docs index must describe crash-loop detection **as built in WP01–WP04**.

The JSON files are authoritative. Update them first, then the markdown views (CLAUDE.md "Documentation Standards").

Describe the shipped behaviour, not the plan. Read the merged code in the lane (WP04 depends on WP01–WP03, so all of it is present) and cross-check every number you write: threshold 3, window 900 s, K 2, cap 3, read budget 6 s, retention 24 h / 64.

## Context to read first

- `research.md`: R-05 (the proven-crossing rule; state its two accepted limits plainly), R-06, R-07, R-08, R-11, R-14 (the 7-day procedure) and R-15.
- `plan.md`: "Surfaced judgment calls". The runbook must state limits 1 to 3 honestly.
- `contracts/crash-loop-alert.md` (alert shapes, ledger outcomes `crash-loop`, `crash-loop-reremind`, `crash-loop-cleared`, `crash-loop-unverified`).
- `docs/design/architecture/change-control.md` (update protocol) and `docs/design/architecture/data/signal-to-doc-map.json`.
- The existing felix-canary entries in each target file, to keep their style and keys.

## Branch Strategy

Planning happened on `kitty/mission-crash-loop-unit-alerting-01M858E8`. The merge target is `fix/crash-loop-unit-alerting`. Get the worktree with `spec-kitty agent action implement WP06 --agent claude --mission crash-loop-unit-alerting-01M858E8`.

## Subtasks

### T023 — Architecture data (JSON first)

- **`service-inventory.json`, felix-canary entry.**
  - Extend `purpose` with one sentence on crash-loop detection (persistent `NRestarts` / `RestartCount`, three scopes, proven-crossing rule, episode lifecycle) and its config file `scripts/canary/crash_loop_config.json`.
  - Add the new state paths (`/data/services/felix-canary/state/crash-loop.json`, `crash-loop.lock`) wherever the entry lists state or config files. Follow the entry's existing keys and do not invent new top-level keys.
  - Set `updated_by` in the entry's existing format, citing `crash-loop-unit-alerting-01M858E8 (kentonium3/kg-automation#1133)`.
  - **Do not change `health_check`.** The tick-signal key ledger is unchanged (research R-09). If the file has top-level `last_updated` or `updated_by`, update them.
- **`data-flows.json`.**
  - Add a flow (or extend the felix-canary flow) that reads systemd (system and `claude` user managers) and the docker daemon, without privilege, into the felix-canary crash-loop stage, then writes `crash-loop.json` and canary ledger lines, then emits through the alert bus.
  - Note the docker isolation (empty `DOCKER_CONFIG`, pinned `DOCKER_HOST`; the CLI retrieves the full inspect object, and the process receives five formatted fields).
  - Update the top-level `updated_by` in its existing style.
- Run `.venv/bin/python tooling/scripts/validate_architecture_data.py` (read `--help`) and fix anything it reports.

### T024 — Narrative views

- **`service-inventory.md`**: the felix-canary section gets a short "Crash-loop detection" paragraph that mirrors the JSON.
- **`data-flows.md`**: the matching narrative for the new flow, including the state file row in the storage table (see the existing "Canary per-component ledger" row near line 1035).
- **`service-dependencies.view.md`**: add felix-canary's read dependencies on the systemd managers and the docker daemon, in the file's Mermaid style.
- **`observability-and-alerting.md`**: in the felix-canary exemplar section, describe:
  - the crash-loop stage: the counter signal, the proof rule, episodes, the per-tick cap and aggregate;
  - that could-not-check scopes route through the canary's `unknown` path;
  - the accepted sampling limits.
- **`felix-capability-roadmap.md`**: review the canary capability row. Add a crash-loop line or row: "✅ Shipped (pending deploy)", with the mission and issue. **Do not claim "deployed"**: deploy waits for Kent's merge approval.

### T025 — Runbook and index

`docs/runbooks/canary-registry-ops.md`: add a `## Crash-loop detection` section covering:

- **What it watches** (FR-001, C-008): every loaded system service and `claude` user service with a `Restart=` value other than `no`, plus docker containers with a restart policy other than `no`, minus the ignore list.
- **What pages**: alert, re-remind (6 h), cleared after K quiet ticks, and the aggregate when more than 3 events occur in one tick.
- **The proven-crossing rule in one paragraph**, with a worked example: 39 restarts over 16 min gives m = 2, bound 5, page. 3 restarts over 16 min is an unverified ledger line with no page.
- **Accepted limits**, stated plainly:
  - slow loops of 3 or 4 restarts per tick interval do not page;
  - a short burst split across a tick boundary can be missed;
  - a failed delivery is not retried; the dead-man reports it;
  - delivery time during an alert storm is the bus's.
- **Tuning**: config fields, with their validation, and how to change them (commit to the repo; it reaches office2 through the normal pipeline).
- **Ignore list**: an entry needs a reason, and matching is exact.
- **Reset**: `rm` the state file, after which every unit is first-seen and nothing alerts.
- **Reading crash-loop ledger lines**: `jq` examples filtering `component_id | startswith("crash-loop")`.
- **Could-not-check**: what each `unknown` reason means and what to check.
- **The 7-day acceptance procedure** (research R-14) as numbered, copy-pasteable `ssh office2-claude` read-only commands for checks 1 and 2, with how to record the result on kentonium3/kg-automation#1133.
- **C-006 cross-reference** (unit-file drift is out of scope): "Follow-up: kentonium3/kg-automation#1138".

Update the runbook's frontmatter (`updated_by`, `last_updated`, `last_validated` if present) to the doc standard.

`docs/INDEX.md`: update the canary-registry-ops entry (line ~129) to mention crash-loop detection (the `runbook-modified` class). Review the observability-and-alerting entry (line ~51), and update it if its summary is now incomplete.

### T026 — Validation

- `.venv/bin/python tooling/scripts/validate_docs.py` (frontmatter and secret scan; mandatory in CI).
- `.venv/bin/python tooling/scripts/validate_architecture_data.py`.
- `.venv/bin/python -m pytest tests/docs tests/tooling -q`.
- The full suite at the end; record the counts in the WP history.

## Definition of Done

- [ ] All nine files are reviewed, and each is updated or has a recorded reason it needs no change.
- [ ] The validators and tests pass.
- [ ] Every number in the docs matches the shipped code and config.
- [ ] No doc claims the feature is deployed.
- [ ] Commits use conventional messages with `docs:` and these trailers:
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01AFaUqc3Puxhf5oxUb9LLP6`.

## Reviewer guidance

- JSON first, and the markdown agrees with it.
- The limits are stated honestly, not buried.
- The 7-day procedure is executable as written and read-only.
- There are no `@` mentions anywhere.
