---
work_package_id: WP05
title: Architecture-doc corrections
dependencies: []
requirement_refs:
- FR-006
tracker_refs: []
planning_base_branch: fix/observation-digest-repoint
merge_target_branch: fix/observation-digest-repoint
branch_strategy: Planning artifacts for this mission were generated on fix/observation-digest-repoint. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/observation-digest-repoint unless the human explicitly redirects the landing branch.
subtasks:
- T014
- T015
- T016
agent: claude
history:
- created by /spec-kitty.tasks 2026-07-05
agent_profile: curator-carla
authoritative_surface: docs/design/architecture/data/service-inventory.json
create_intent: []
execution_mode: code_change
owned_files:
- docs/design/architecture/data/service-inventory.json
- docs/design/architecture/data/data-flows.json
- docs/design/architecture/service-inventory.md
- docs/design/architecture/data-flows.md
- docs/design/architecture/data-flows.view.md
- docs/design/architecture/service-dependencies.view.md
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Load your profile: `/ad-hoc-profile-load curator-carla` (role: implementer). Read this WP and the
target JSON entries before editing. JSON is authoritative; markdown views must match.

## Objective

Bring the architecture store into agreement with reality (FR-006, SC-005): the observation-digest
subsystem now writes raw logs to the vault, and the stray tree is decommissioned.

## Context

- `docs/design/architecture/data/service-inventory.json` → entry `felix-core-digest` (~line 1920):
  currently records `input_path` and `output_path` on `/home/claude/second-brain/...`, an
  `exec_start` with a `/home/claude/repos/kg-automation/...` prefix (real unit uses
  `/home/claude/kg-automation/...`, no `repos/`), a `path_retention_note` citing #659, and a
  dependency note "Path retained pending #659".
- `docs/design/architecture/data/data-flows.json` → flow `observation-digest` (~line 135): log
  paths on the stray tree + a `path_retention_note` citing #659.
- Verified reality: raw logs → `/home/kgale/second-brain/agents/logs/`; digest output ALREADY →
  `/home/kgale/second-brain/notes/00-System/agent-activity/Agent-Logs/` (the recorded stray
  `output_path` is STALE, not a live path).

### Subtask T014 — service-inventory.json

- `felix-core-digest`: set `input_path` to the vault log dir; **correct the stale** `output_path`
  to `/home/kgale/second-brain/notes/00-System/agent-activity/Agent-Logs/`; fix `exec_start` to the
  real `/home/claude/kg-automation/...` path (drop the erroneous `repos/`); **remove** the
  `path_retention_note` and the "Path retained pending #659" dependency note; set `updated_by: 659`.
- Keep the schema valid (the architecture-data validator is a blocking Docs-CI gate). Do not touch
  the `/data/services/openclaw/felix-core-digest-signals/` state paths (#490, out of scope).

### Subtask T015 — data-flows.json [P]

- `observation-digest` flow: repoint the `log_action.py` write path and `summarize.py` read path to
  the vault log dir; the digest write path is already the vault (`00-System/agent-activity`) — keep;
  **remove** the `path_retention_note`; set `updated_by: 659`.

### Subtask T016 — Markdown views + validate

- Update `service-inventory.md`, `data-flows.md`, `data-flows.view.md`,
  `service-dependencies.view.md` wherever they render the old stray paths / retention notes, to
  match the JSON.
- Run the architecture-data validator (`python3 tooling/scripts/validate_docs.py` or the
  architecture-data validator invoked in Docs-CI). It MUST pass.

## Branch Strategy

Base/merge target: `fix/observation-digest-repoint`. Independent WP. Worktrees per-lane.

## Test Strategy

Run the architecture-data validator; `grep -c "path_retention_note" data/service-inventory.json
data/data-flows.json` returns 0 for the #659 notes (confirm no OTHER retention notes are wrongly
removed — only the #659 ones).

## Definition of Done

- [ ] JSON: paths corrected (input/output/exec_start), #659 retention notes removed, `updated_by: 659`.
- [ ] Markdown views match JSON.
- [ ] Architecture-data validator passes.
- [ ] No unrelated entries changed (#490 signal paths untouched).

## Risks / Reviewer guidance

- **Risk**: JSON schema break → CI gate fails. Reviewer runs the validator.
- **Risk**: removing a NON-#659 retention note. Reviewer diffs to confirm only the two #659 notes
  are removed.
- **Risk**: markdown views drifting from JSON. Reviewer spot-checks the rendered paths match.
