---
work_package_id: WP01
title: Remove the stale-path lint validator + all wiring
dependencies: []
requirement_refs:
- FR-001
tracker_refs: []
planning_base_branch: feat/retire-private-folder-guards
merge_target_branch: feat/retire-private-folder-guards
branch_strategy: Planning artifacts for this mission were generated on feat/retire-private-folder-guards. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/retire-private-folder-guards unless the human explicitly redirects the landing branch.
subtasks:
- T001
- T002
- T003
- T004
- T005
agent: "claude:sonnet:implementer:implementer"
history: []
agent_profile: implementer-ivan
authoritative_surface: tooling/scripts/
create_intent: []
execution_mode: code_change
owned_files:
- tooling/scripts/validate_privacy_boundary.py
- .githooks/pre-commit
- .github/workflows/docs-ci.yml
- Makefile
- .agents/autopilot/adapters/kg-automation.md
- docs/runbooks/local-test-gate.md
role: implementer
tags: []
shell_pid: "22263"
shell_pid_created_at: "1784651109.595756"
---

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your agent profile via `/ad-hoc-profile-load implementer-ivan`
so you adopt the implementer identity, governance scope, and boundaries.

## Objective

Delete the folder-specific stale-path lint validator and remove every caller so nothing invokes a
removed script (which would red-fail pre-commit/CI). Authoritative detail: `data-model.md` IC-01 row
table; requirement FR-001; the CI-check flag is issue #848's Codex/Stijn context.

## Context

`tooling/scripts/validate_privacy_boundary.py` lints active surfaces for the pre-#152 path
`02-Growth/_private`. With the `_private` boundary physically excluded and being purged, there is no
"current boundary path" to keep un-stale — the tool guards nothing. Remove it and all wiring in one
change so gates stay self-consistent.

## Subtasks

- **T001** — Delete `tooling/scripts/validate_privacy_boundary.py` entirely.
- **T002** — `.githooks/pre-commit`: remove the `validate_privacy_boundary` invocation only; leave
  `validate_docs`, the whole-tree privacy/arch-data steps, and the rest intact. Keep the hook valid.
- **T003** — `.github/workflows/docs-ci.yml`: remove the `- name: Validate privacy boundary lint …`
  step (the run line + the preceding `#560` explanatory comment block that avoids the literal token).
- **T004** — `Makefile`: remove the validator target/recipe and any reference to it in aggregate
  targets (e.g. a `validate`/`check` target that calls it). Keep other targets working.
- **T005** — Remove the validator reference from `.agents/autopilot/adapters/kg-automation.md`
  (its gate list) and from `docs/runbooks/local-test-gate.md` (drop it from the documented local gate).

## Branch Strategy

Planning/base and merge target are both `feat/retire-private-folder-guards` (single_branch). An
execution worktree is allocated for this lane per `lanes.json`; work there and let the workflow
merge the lane.

## Definition of Done

- `tooling/scripts/validate_privacy_boundary.py` no longer exists.
- `grep -rn "validate_privacy_boundary" .githooks/ .github/ Makefile .agents/ docs/runbooks/local-test-gate.md`
  returns zero hits.
- A clean local commit succeeds (pre-commit no longer calls the deleted script).
- No other pre-commit/CI step is broken by the edits.

## Risks & reviewer guidance

- A dangling call to the deleted script red-fails the gate — verify T002/T003/T004 remove ALL
  callers, not just the script.
- Reviewer: confirm the docs-ci comment block (the #560 meta-reference trap) is removed with the
  step, and that no aggregate Makefile target still references the removed recipe.

## Activity Log

- 2026-07-21T16:25:22Z – claude:sonnet:implementer:implementer – shell_pid=22263 – Assigned agent via action command
