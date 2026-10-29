---
work_package_id: WP05
title: Architecture docs and runbooks
dependencies:
- WP04
requirement_refs:
- FR-010
- NFR-001
- C-005
planning_base_branch: fix/canary-deadman-backup-coverage
merge_target_branch: fix/canary-deadman-backup-coverage
branch_strategy: Planning artifacts for this mission were generated on fix/canary-deadman-backup-coverage. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/canary-deadman-backup-coverage unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-canary-deadman-backup-coverage-01M4XVY3
base_commit: 0f7009f6a384fbaeded6c183df657abb84b2e1aa
created_at: '2026-10-14T19:53:50.618252+00:00'
subtasks:
- T020
- T021
- T022
- T023
phase: Phase 4 - Documentation
history:
- at: '2026-10-14T19:40:00Z'
  actor: tasks
  action: Prompt generated via /spec-kitty.tasks (plan IC-04; paula-1(a), debbie-3, Codex-7)
agent_profile: python-pedro
authoritative_surface: docs/
create_intent: []
execution_mode: code_change
lane: planned
model: claude-opus-5-5
owned_files:
- docs/design/architecture/observability-and-alerting.md
- docs/design/architecture/service-inventory.md
- docs/runbooks/restic-backup-ops.md
- docs/runbooks/canary-registry-ops.md
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP05 – Architecture docs and runbooks

## ⚡ Do This First: Load Agent Profile

Use the `/spk-charter-profile-load` skill to load the agent profile specified in the frontmatter (or any user-defined profile), and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `python-pedro`
- **Role**: `implementer`
- **Agent/tool**: `claude`

---

## ⚠️ IMPORTANT: Review Feedback

Check `review_ref` via `spec-kitty agent tasks status`; address every item; record progress with `spec-kitty agent tasks add-history WP05 --note "..."`.

---

## Objectives & Success Criteria

The narrative docs match what WP01–WP04 built (FR-010; the standing architecture-doc directive):
- the mutual watch, and the shared-fate limit with its follow-up (#1069);
- where a backup failure is reported, and how fast (NFR-001);
- the retired path is gone from every active doc.

Done when `validate_docs.py`, `validate_architecture_data.py` and the full pytest suite (which includes the broken-link gate) pass, and the T023 sweep is clean.

## Context & Constraints

- Inventory JSON prose was already updated in WP01 T004; the JSON wins where it and the narrative differ. Consult `docs/design/architecture/data/signal-to-doc-map.json` (`change_class` `service-added-or-modified`, `runbook-modified`) for any other doc target it names. If it names one outside `owned_files`, edit it with a one-line out-of-map rationale.
- Match each doc's existing voice, frontmatter and section style. Doc frontmatter is validated.

## Branch Strategy

- **Planning base branch**: `fix/canary-deadman-backup-coverage` · **Merge target branch**: `fix/canary-deadman-backup-coverage`.

## Subtasks & Detailed Guidance

### Subtask T020 – `observability-and-alerting.md`

Add a "Who watches the watcher" subsection:
- felix-health-check (calendar, 11:00/23:00 UTC) evaluates `felix-canary` and `restic-backup` through the canary's own evaluator and inventory declarations.
- The canary probes the health check's `last-run.json` (#891).
- The canary's tick ledger (#1063) makes "alive" affirmative.
- **Shared-fate limit**: same host, user manager, checkout and alert channel. A regression in the shared evaluator is guarded by CI sentinels. Host or channel loss is uncovered, tracked in kentonium3/kg-automation#1069.
- Detection latency (NFR-001): a dark canary is reported ≤ 12 h + 35 min; a missed backup ≤ 12 h after the snapshot passes its 28 h bound.
- Post-downtime catch-up runs may report the canary stale once, by design (R9).

### Subtask T021 – `service-inventory.md`

Update the felix-health-check and felix-canary narrative rows/sections to match the JSON (script location, coverage, ledger).

### Subtask T022 – `restic-backup-ops.md`

A short section, "What tells you backups stopped":
- the canary (`restic-backup` ledger, per its dedup windows);
- felix-health-check (independent, twice daily, `coverage:restic-backup` alert detail);
- the not-mounted path does not alert directly yet, follow-up kentonium3/kg-automation#1067.

Link the existing "Backup drive missing" section (#1064).

### Subtask T023 – Reference sweep + validators

- Run `grep -rn "helper-scripts/health-check" --exclude-dir=.git --exclude-dir=kitty-specs --exclude-dir=.kittify .`. The only allowed hits are `deploys/applied/` (immutable records), the new manifest/entrypoint (which name the path in order to retire it) and test fixtures. Fix anything else in `owned_files`. For a hit outside `owned_files`, record it in `add-history` and fix it with a rationale.
- `docs/runbooks/canary-registry-ops.md`: if it describes tick health, mention the ledger in one line.
- Run `python3 tooling/scripts/validate_docs.py`, `python3 tooling/scripts/validate_architecture_data.py` and `python3 -m pytest -q`.

## Test Strategy

Docs only. The gate is the validators plus the full pytest suite (the link checker lives there; memory: "Docs CI green ≠ CI green").

## Risks & Mitigations

- **Broken links from moved anchors**: run the full suite.

## Review Guidance

- Is the shared-fate limit stated plainly, not buried?
- Do the latencies quoted match the inventory bounds?

## Progress & Status

`spec-kitty agent tasks add-history WP05 --note "…"` · implement: `spec-kitty agent action implement WP05 --agent claude --mission canary-deadman-backup-coverage-01M4XVY3`
