---
work_package_id: WP01
title: Seam label taxonomy declaration
dependencies: []
requirement_refs:
- FR-002
- FR-006
tracker_refs: []
planning_base_branch: feat/task-intake-validation-loop
merge_target_branch: feat/task-intake-validation-loop
branch_strategy: Planning artifacts for this mission were generated on feat/task-intake-validation-loop. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/task-intake-validation-loop unless the human explicitly redirects the landing branch.
subtasks:
- T001
- T002
- T003
- T004
phase: Phase 1 - Foundation
agent: "claude:opus:reviewer-renata:reviewer"
shell_pid: "57404"
shell_pid_created_at: "1784327736.623405"
history:
- at: '2026-07-17T21:55:00Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: python-pedro
authoritative_surface: scripts/common/vikunja_refs
create_intent:
- tests/common/test_vikunja_refs_labels.py
execution_mode: code_change
model: claude-sonnet-5
owned_files:
- scripts/common/vikunja_refs.json
- scripts/common/vikunja_refs_validate.py
- tests/common/test_vikunja_refs_labels.py
role: implementer
tags: []
---

# Work Package Prompt: WP01 — Seam label taxonomy declaration

## ⚡ Do This First: Load Agent Profile

Use the `/ad-hoc-profile-load` skill to load the profile in the frontmatter and behave per its guidance before reading further.

- **Profile**: `python-pedro`
- **Role**: `implementer`
- **Agent/tool**: `claude`

---

## Branch Strategy

Planning branch: `feat/task-intake-validation-loop`. Merge target: `feat/task-intake-validation-loop`. Your execution worktree is allocated per the computed lane in `lanes.json`.

## Objective

Extend the #748 Vikunja reference seam so the intake loop can resolve **every**
Tier-1/Tier-2 label id through the fail-loud accessor — no hardcoded ids. Today
`scripts/common/vikunja_refs.json` declares only `q:schedule` (id 23). Declare the
full friction / Eisenhower / type / LOE taxonomy, and extend the drift validator to
cover the additions.

Read first: `scripts/common/vikunja_refs.py` (accessor — note `label_id(name, owner_token)`,
`declared_labels()`, `_require_positive_int_id`), `scripts/common/vikunja_refs_validate.py`
(the drift/AST gate), the spec's data-model "Seam registry additions", and
`docs/design/vikunja-configuration-design.md` (label taxonomy + colors, source of truth).

## Subtasks

### T001 — Reconcile live label ids (owner_token = kent)
Determine the **exact live ids** for each label below from the #715 label set
(kent-owned). Do NOT invent or approximate ids (no "~18–29"): reconcile against the
live Vikunja labels. If a helper/fixture with the live ids exists, use it; otherwise
document the reconciliation source in the test. Labels:
`f:1-flow`, `f:2-growth`, `f:3-edge`, `f:4-overload`, `q:do`, `q:schedule` (present,
id 23), `q:delegate`, `q:eliminate`, `t:habit`, `loe:s`, `loe:m`, `loe:l`.

### T002 — Declare labels in `vikunja_refs.json`
Add each label to the `labels` array with its `name`, `title`, `owner: "kent"`, and a
`selector` `{kind: "label_id", value: <int>}` (match the existing `q:schedule` shape).
Keep `schema_version`/`source_of_truth` intact; bump `last_verified_utc`.

### T003 — Extend the drift/AST validator
Ensure `vikunja_refs_validate.py` validates the new declarations (id is a positive int,
owner present, no duplicate names/ids) and stays green. If the validator enumerates an
expected label set, extend it to include the new labels. Preserve the SC-001-style AST
gate behavior.

### T004 — Unit tests
`tests/common/test_vikunja_refs_labels.py`: assert `label_id(name, "kent")` returns the
declared id for every new label; assert an undeclared/unprovisioned label raises the
seam's fail-loud error; assert `vikunja_refs_validate` passes on the updated registry.
Use `set_registry_for_test` for isolation where helpful.

## Definition of Done
- All 12 labels resolvable via `label_id(name, "kent")`; no hardcoded ids anywhere else.
- Drift validator green; `python3 -m scripts.common.vikunja_refs_validate` exits 0.
- Tests pass: `pytest tests/common/test_vikunja_refs_labels.py -q`.
- No approximate id ranges remain in any artifact (Codex post-plan #11).

## Risks / reviewer guidance
- **Reviewer:** verify ids were reconciled against the live set (not fabricated), owner is `kent` on every label, and the validator actually exercises the new entries. Confirm `q:schedule` id 23 is unchanged.

## Implementation command
`spec-kitty agent action implement WP01 --agent claude`

## Activity Log

- 2026-07-17T22:21:07Z – claude:sonnet:python-pedro:implementer – shell_pid=52864 – Assigned agent via action command
- 2026-07-17T22:35:17Z – claude:sonnet:python-pedro:implementer – shell_pid=52864 – WP01 seam label taxonomy: 12 labels declared (ids 18-29 reconciled live), validator+tests green
- 2026-07-17T22:35:47Z – claude:opus:reviewer-renata:reviewer – shell_pid=57404 – Started review via action command
- 2026-07-17T22:39:49Z – user – shell_pid=57404 – reviewer-renata APPROVE: 12 kent-owned labels ids 18-29 on seam; validator+354 tests green
