---
work_package_id: WP01
title: Shared Vikunja scope config (foundation)
dependencies: []
requirement_refs:
- FR-008
tracker_refs: []
planning_base_branch: fix/deterministic-cron-hardening
merge_target_branch: fix/deterministic-cron-hardening
branch_strategy: Planning artifacts for this mission were generated on fix/deterministic-cron-hardening. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/deterministic-cron-hardening unless the human explicitly redirects the landing branch.
subtasks:
- T001
- T002
- T003
- T004
agent: claude
history:
- '2026-07-12: authored by /spec-kitty.tasks'
agent_profile: python-pedro
authoritative_surface: scripts/common/vikunja_scope.py
create_intent:
- scripts/common/vikunja_scope.py
- tests/common/test_vikunja_scope.py
execution_mode: code_change
owned_files:
- scripts/common/vikunja_scope.py
- scripts/habits/query_active_habits_weekly.py
- tests/common/test_vikunja_scope.py
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned profile:
`/ad-hoc-profile-load python-pedro` (role: implementer). Adopt its identity, boundaries, and initialization declaration, then proceed.

## Objective

Create a single importable module, `scripts/common/vikunja_scope.py`, that externalizes the Vikunja selectors the escalation and habit code depend on, and rewire the weekly habit helper to read the habit project id from it (it currently hardcodes `HABITS_PROJECT_ID = 13`). This is the foundation that decouples the mission from the #714 Vikunja reorganization (FR-008, NFR-004): a taxonomy change becomes a value edit in this one module.

**Scope guardrail**: this WP ships the config seam + the **`project_id`** habit-fetch form only. The **label** fetch strategy is explicitly OUT OF SCOPE (deferred to #716 — see `contracts/post-plan-review-resolutions.md` H5/H6). Shape the selector so a future label value is representable, but do NOT build the label fetch path here.

## Context

- Authoritative contract: `kitty-specs/deterministic-cron-hardening-01KXA4PX/contracts/vikunja_scope.md`.
- Data model: `data-model.md` → VikunjaScopeConfig.
- The weekly helper `scripts/habits/query_active_habits_weekly.py` hardcodes `HABITS_PROJECT_ID = 13` (line ~71) and uses it at `/projects/{HABITS_PROJECT_ID}/tasks` (lines ~290, ~389, ~912).
- `scripts/common/` already holds shared modules (`vikunja_client.py`, `vikunja_config.py`); follow their style.

### Subtask T001 — Create `scripts/common/vikunja_scope.py`

**Purpose**: the single source for Vikunja selectors.

**Provide**:
- Module constants (today's values):
  - `ESCALATION_EXCLUDED_PROJECT_IDS = [11, 13]`  (Goals, Habits)
  - `HABIT_SELECTOR = {"kind": "project_id", "value": 13}`
- Accessors (the public API — consumers MUST use these, never the constants directly):
  - `get_escalation_excluded_project_ids() -> list[int]`
  - `get_habit_selector() -> dict`  (returns a copy: `{"kind": "project_id"|"label", "value": int|str}`)
  - `habit_project_id() -> int | None`  (the int value when `kind == "project_id"`, else `None`)
- A tiny validation on import or in the accessor: `kind` ∈ {`project_id`, `label`}; raise `ValueError` on an unknown kind.
- Module docstring: explains the #714 decoupling and that the label fetch strategy is #716's work.

**Do NOT**: read files, hit the network, or import heavy deps. Pure Python constants + functions.

### Subtask T002 — Rewire the weekly helper to the scope module

**Purpose**: remove the hardcoded habit project id (FR-008).

**Steps**:
- In `scripts/habits/query_active_habits_weekly.py`, replace the module-level `HABITS_PROJECT_ID = 13` with a value sourced from `scripts.common.vikunja_scope.habit_project_id()`.
- Keep the existing `f"/projects/{...}/tasks"` fetch shape (project_id form). If `habit_project_id()` returns `None` (a label selector — not possible today), raise a clear `NotImplementedError("label habit selector not supported yet — see #716")` rather than silently misbehaving. This makes the #716 boundary explicit and honest.
- Do not change any other behavior of the helper (rendering, counts, exit codes) — this is a pure id-sourcing refactor.

### Subtask T003 — Tests `tests/common/test_vikunja_scope.py`

**Purpose**: lock the accessors + prove the #714 swap is config-only for the value.

**Cases**:
- `get_escalation_excluded_project_ids()` returns `[11, 13]`.
- `get_habit_selector()` returns the project_id form; the returned dict is a copy (mutating it does not affect the module).
- `habit_project_id()` returns `13` for the project_id form and `None` for a label form (construct a label-form selector and verify — e.g. via monkeypatching the constant or a helper that accepts a selector).
- An unknown `kind` raises `ValueError`.

### Subtask T004 — Regression + pagination fixture

**Purpose**: prove the weekly helper still works with the config-sourced id, and guard the >50-task pagination path (post-plan review M10).

**Steps**:
- Add/extend a test that runs the weekly helper's project-fetch path against a **fake `VikunjaClient`** returning a >50-task multi-page fixture, asserting it paginates (stops on empty page, not on `len < 100`) and aggregates correctly with the config-sourced id.
- If the existing weekly-helper tests already cover pagination, extend them minimally rather than duplicating; keep the new test in `tests/common/` or the existing `tests/habits/` suite as fits — but do NOT create a second owned file outside this WP's `owned_files`. (If you must touch an existing `tests/habits/` file, record a one-line out-of-map rationale.)

## Branch Strategy

Planning base + merge target: **`fix/deterministic-cron-hardening`**. Execution runs in this WP's computed lane worktree (from `lanes.json` after finalize). Merge back to the mission branch; the mission later merges feat→main.

## Test strategy

Deterministic pytest only — fake `VikunjaClient`, no network, no LLM. Run `pytest tests/common/test_vikunja_scope.py -q` and the weekly-helper suite.

## Definition of Done

- [ ] `scripts/common/vikunja_scope.py` exists with the 3 accessors + validation.
- [ ] `query_active_habits_weekly.py` sources the habit project id from the scope module; no hardcoded `13` remains for habit identity.
- [ ] `tests/common/test_vikunja_scope.py` green; weekly-helper suite green (incl. >50 pagination).
- [ ] `label` form raises a clear NotImplementedError in the helper (honest #716 boundary), not silent misbehavior.
- [ ] No behavior change to the weekly helper beyond id sourcing.

## Risks / reviewer guidance

- **Do not** build the label fetch strategy — reviewer rejects any label-scoped Vikunja fetch here (#716 scope).
- Verify the accessor returns a copy (no shared-mutable-state leak).
- Verify no other consumer of `HABITS_PROJECT_ID` was missed (grep the helper for all uses).
- Keep the module dependency-free (importable from both escalation and habits code without cycles).
