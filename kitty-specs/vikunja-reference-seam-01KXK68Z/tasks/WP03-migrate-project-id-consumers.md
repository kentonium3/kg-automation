---
work_package_id: WP03
title: Migrate project-id resolution consumers (scope + habits + security)
dependencies:
- WP01
requirement_refs:
- FR-002
- FR-005
- FR-008
tracker_refs: []
planning_base_branch: feat/vikunja-reference-seam
merge_target_branch: feat/vikunja-reference-seam
branch_strategy: Planning artifacts for this mission were generated on feat/vikunja-reference-seam. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/vikunja-reference-seam unless the human explicitly redirects the landing branch.
subtasks:
- T009
- T010
- T011
- T012
- T013
- T014
phase: Phase 2 - Migration
assignee: ''
agent: ''
history:
- at: '2026-07-15T17:18:48Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: scripts/habits/
create_intent: []
execution_mode: code_change
owned_files:
- scripts/common/vikunja_scope.py
- scripts/habits/query_active_habits_v2.py
- scripts/habits/reconcile_completions.py
- scripts/habits/backfill_jsonl_from_comments.py
- scripts/habits/query_active_habits_weekly.py
- scripts/security/credential_health_check/vikunja_writer.py
- tests/common/test_vikunja_scope.py
- tests/habits/test_query_active_habits_v2.py
- tests/habits/test_query_active_habits_v2_day_of_week.py
- tests/habits/test_query_active_habits_v2_filter.py
- tests/habits/test_reconcile_completions.py
- tests/habits/test_backfill_jsonl_from_comments.py
- tests/habits/test_query_active_habits_weekly.py
- tests/security/test_vikunja_writer.py
tags: []
---

# Work Package Prompt: WP03 – Migrate project-id resolution consumers

## ⚡ Do This First: Load Agent Profile

Use the `/ad-hoc-profile-load` skill to load the agent profile specified in the frontmatter, and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `python-pedro`
- **Role**: `implementer`
- **Agent/tool**: `claude`

---

## Branch Strategy

- **Planning/base branch at prompt creation**: `feat/vikunja-reference-seam`
- **Final merge target for completed work**: `feat/vikunja-reference-seam`
- **Actual execution workspace is resolved later**: trust the path printed by `spec-kitty agent workflow implement`; do not manually create a different worktree.
- **If human instructions contradict these fields**: stop and resolve the intended landing branch before coding.

---

## Markdown Formatting

Wrap HTML/XML tags in backticks. Use language identifiers in code blocks.

---

## Objectives & Success Criteria

Move every runtime **project-id** resolution consumer onto the WP01 accessor and
**delete** the old by-title / hardcoded-id lookups (no vestiges). Keep `vikunja_scope`
as the selector layer, but have it read its identity **through** the registry.

**Done when:**
- `vikunja_scope.HABIT_SELECTOR` is derived from `vikunja_refs.selector("habits")`
  and `ESCALATION_EXCLUDED_PROJECT_IDS` **derives** from
  `vikunja_refs.project_id("habits")` — the literal `13` / `[13]` no longer appear
  as resolution sources in that module.
- The four habits scripts and `vikunja_writer` resolve their project ids via the
  accessor; `HABITS_PROJECT_ID = 13` / `= 2`, `title == "Habits"`,
  `lookup_inbox_project_id` by-title, and the `query_active_habits_weekly`
  module-level mirror are **removed**.
- Behavior is unchanged (habits still scope to project 13; escalation still excludes
  13; the credential-health writer still targets Inbox id 1). All existing tests for
  these modules pass, updated where they asserted the old constants.

## Context & Constraints

Read first: `plan.md` (§ vikunja_scope ownership, § runtime call-site migration),
`spec.md` FR-005 inventory + FR-008, `data-model.md` § vikunja_scope ownership, and
WP01's accessor contract.

**Preserve the `{kind, value}` selector shape (FR-008):** `vikunja_scope` already
exposes `HABIT_SELECTOR = {"kind": ..., "value": ...}` because #717 will migrate
Habits identity from project-id 13 → the `t:habit` label. Do **not** flatten this to
a bare int. The label-fetch *strategy* stays #716/#717's work — this WP only moves
the identity **source** into the registry.

Constraints: C-001 (Felix-side only); no behavior change (same effective ids today);
stdlib + existing modules. Import convention: `from scripts.common import vikunja_refs`
(grep siblings to confirm; `[[feedback_wp_prompts_grep_codebase]]`).

**Note on this branch:** `reconcile_completions.py` currently reads
`HABITS_PROJECT_ID = 2` here (main fixed it to 13 in `5e24ac4e`). Migrating it to
`project_id("habits")` supersedes that raw-int fix — do not merely change 2→13,
route it through the accessor.

## Subtasks & Detailed Guidance

### Subtask T009 – `vikunja_scope` read-through + derive escalation exclusion
- **Purpose**: Make the selector layer read identity from the one registry.
- **Steps**:
  1. In `scripts/common/vikunja_scope.py`, source `HABIT_SELECTOR` from
     `vikunja_refs.selector("habits")` (keep the `{kind, value}` contract and the
     existing `_validate_selector` guard).
  2. Derive `ESCALATION_EXCLUDED_PROJECT_IDS` from
     `vikunja_refs.project_id("habits")` (e.g. `[project_id("habits")]`) instead of
     the literal `[13]`. Keep the accessor functions (`get_escalation_excluded_project_ids`,
     `get_habit_selector`, `habit_project_id`) and their copy-return semantics.
  3. Update the module docstring's "value edit in this module only" note to "value
     lives in the registry (`vikunja_refs.json`); this module reads it through the
     accessor" — keep the #716/#717 label-migration note.
- **Files**: `scripts/common/vikunja_scope.py`, `tests/common/test_vikunja_scope.py`.
- **Notes**: `habit_project_id()` still returns `None` for a `label` selector — that
  contract is unchanged. Update tests that asserted the literal `[13]` /
  `{"kind":"project_id","value":13}` to assert the registry-derived value (or patch
  the accessor to a known value and assert the derivation).

### Subtask T010 – Migrate `query_active_habits_v2`
- **Purpose**: Resolve the Habits project via the seam.
- **Steps**: Replace `HABITS_PROJECT_ID = 13` (and the `HABITS_PROJECT_TITLE`
  fallback const) with a resolution through `vikunja_scope.habit_project_id()` /
  `vikunja_refs.project_id("habits")`. The `:237` filter (`project_id != <id>`)
  reads the resolved id. Remove the now-dead title fallback if it only existed for
  the `None` case (keep fail-loud behavior — a label selector must raise, not
  silently skip; mirror `query_active_habits_weekly`'s `_resolve_habits_project_id`).
- **Files**: `scripts/habits/query_active_habits_v2.py`,
  `tests/habits/test_query_active_habits_v2.py`,
  `tests/habits/test_query_active_habits_v2_day_of_week.py`,
  `tests/habits/test_query_active_habits_v2_filter.py`.
- **Parallel?**: [P] with T011–T014.

### Subtask T011 – Migrate `reconcile_completions`
- **Purpose**: Same, for the reconcile path.
- **Steps**: Replace `HABITS_PROJECT_ID = 2` (line ~71) with
  `vikunja_refs.project_id("habits")` (via `vikunja_scope` if that reads cleaner);
  the `:155` filter uses the resolved id. Delete the module-level literal.
- **Files**: `scripts/habits/reconcile_completions.py`,
  `tests/habits/test_reconcile_completions.py`.
- **Parallel?**: [P].

### Subtask T012 – Migrate `backfill_jsonl_from_comments`
- **Purpose**: Replace the by-title Habits resolver.
- **Steps**: Remove the `title == "Habits"` resolution (`:63`, `:172`, the
  `resolve` helper ~`:149`) and resolve via `vikunja_refs.project_id("habits")`.
  Preserve the "uniquely resolvable / else fail loud" behavior — now the accessor
  is the fail-loud surface. Update the reporting line (`:583`) accordingly.
- **Files**: `scripts/habits/backfill_jsonl_from_comments.py`,
  `tests/habits/test_backfill_jsonl_from_comments.py`.
- **Parallel?**: [P].

### Subtask T013 – Collapse `query_active_habits_weekly` mirror
- **Purpose**: One source, not a mirror.
- **Steps**: This module already sources the id from `vikunja_scope.habit_project_id()`
  at import (`_resolve_habits_project_id`), which now reads the registry — good.
  Remove the module-level `HABITS_PROJECT_ID` **mirror** const (`:63`) if it merely
  re-exports; have consumers reference the resolved value directly. Keep the
  fail-loud raise when the selector is a label.
- **Files**: `scripts/habits/query_active_habits_weekly.py`,
  `tests/habits/test_query_active_habits_weekly.py`.
- **Parallel?**: [P].

### Subtask T014 – Migrate `vikunja_writer` inbox lookup
- **Purpose**: Resolve Inbox via the seam in the credential-health writer.
- **Steps**: Replace `lookup_inbox_project_id` (by-title) with
  `vikunja_refs.project_id("inbox")`. Delete the by-title helper. Keep the writer's
  downstream behavior identical (targets Inbox id 1).
- **Files**: `scripts/security/credential_health_check/vikunja_writer.py`,
  `tests/security/test_vikunja_writer.py`.
- **Parallel?**: [P].
- **Notes**: If `vikunja_writer` runs where the network is unavailable, resolution
  is still network-free (committed id) — good; verify no test mocked the old
  `/projects` list in a way that now needs updating to the accessor.

## Test Strategy

- `python3 -m pytest tests/common/test_vikunja_scope.py tests/habits/ tests/security/test_vikunja_writer.py -q`.
- Also run the escalation consumer to catch ripple:
  `python3 -m pytest tests/escalation/test_enumerate_candidates.py -q` (should stay
  green — exclusion is still `[13]`, now derived; if it needs a one-line touch,
  record the out-of-map rationale in the Activity Log).
- **SC-002 regression**: add/confirm a test that a habits resolution against a
  *deleted/renamed* reference **fails loud** (accessor raises) rather than returning
  an empty task set.

## Risks & Mitigations

- **Behavior drift** (accidentally changing the effective id). Mitigation: the
  registry seeds Habits=13; existing tests assert the same scoping.
- **Flattening the selector** (breaking FR-008 / #717). Mitigation: keep
  `HABIT_SELECTOR` as `{kind,value}`; T009 review checkpoint.
- **Escalation ripple** via `ESCALATION_EXCLUDED_PROJECT_IDS`. Mitigation: run the
  escalation test; value is unchanged.

## Integration Verification (mandatory before for_review)

- [ ] No `HABITS_PROJECT_ID = <int>`, `title == "Habits"`, or `lookup_inbox_project_id`
      by-title remains in the owned files (grep clean).
- [ ] `HABIT_SELECTOR` keeps the `{kind, value}` shape (FR-008).
- [ ] Habits queries + escalation exclusion + credential-writer target are behaviorally identical.
- [ ] Tests verify the contract (fail-loud on deleted ref), not just the swap.

## Review Guidance

- Confirm the literals are **deleted**, not shadowed.
- Confirm `vikunja_scope` derives (not restates) the escalation exclusion.
- Confirm the selector shape survives for #717.

## Activity Log

> Append new entries at the END, chronological order, UTC `YYYY-MM-DDTHH:MM:SSZ`.

- 2026-07-15T17:18:48Z – system – Prompt created.
