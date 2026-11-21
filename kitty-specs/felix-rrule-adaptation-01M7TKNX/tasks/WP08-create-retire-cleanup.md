---
work_package_id: WP08
title: Create path, retirement, final client cleanup
dependencies:
- WP03
- WP04
- WP05
- WP06
- WP07
requirement_refs:
- FR-011
- FR-018
- NFR-001
- NFR-003
- C-003
- C-007
- NFR-002
planning_base_branch: fix/felix-rrule-adaptation
merge_target_branch: fix/felix-rrule-adaptation
branch_strategy: Planning artifacts for this mission were generated on fix/felix-rrule-adaptation. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/felix-rrule-adaptation unless the human explicitly redirects the landing branch.
subtasks:
- T036
- T037
- T038
- T039
- T040
phase: Phase 3 - Cleanup
history:
- at: '2026-11-19T22:30:00Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: python-pedro
authoritative_surface: scripts/vikunja/create_task.py
create_intent:
- tests/architectural/test_no_retired_repeat_fields.py
execution_mode: code_change
model: claude-opus-5-5
owned_files:
- scripts/vikunja/create_task.py
- tests/vikunja/test_create_task.py
- scripts/habits/migrate_schedule.py
- tests/habits/test_migrate_schedule.py
- tests/architectural/test_habits_history_canonical_read.py
- tests/architectural/test_no_retired_repeat_fields.py
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP08 – Create path, retirement, final client cleanup

## ⚡ Do This First: Load Agent Profile

Use the `/spk-charter-profile-load` skill to load the agent profile specified in the frontmatter, and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `python-pedro`
- **Role**: `implementer`
- **Agent/tool**: `claude`

---

## ⚠️ IMPORTANT: Review Feedback

Check `spec-kitty agent tasks status` for a `review_ref`, and address every item before going back to review.

---

## Objectives & Success Criteria

1. **`create_task --rrule`** (audit row 23, FR-011, O3). The CLI creates real recurring tasks through `create_task_v2`, reads them back, and fails if the rule is missing. `--repeat-after` and `--repeat-mode` are removed.
2. **Retire `migrate_schedule`** (audit rows 12–16, FR-018, Kent's decision `01M7TN0X`). Delete the script and its tests, and update every code or test reference.
3. **Remove `replace_task_fields`** from the client (plan IC-01). By now WP03 has moved its last callers. Fix the client docstrings that cite `migrate_schedule`.
4. **NFR-001 ratchet.** A test fails if `repeat_after` or `repeat_mode` appears in active Felix code or agent docs.
5. **NFR-003.** The full suite is green, and `validate_architecture_data.py --strict` passes.

## Context & Constraints

- Spec: FR-011, FR-018, NFR-001, NFR-003, C-003. Plan IC-07. research.md R-012 lists every `migrate_schedule` reference.
- **Planned out-of-map edits.** Record each one with `spec-kitty agent tasks add-history WP08 --note "out-of-map: <file> — <reason>"`.
  - `scripts/common/vikunja_client.py` (owned by WP02): delete `replace_task_fields` (L415-432), and reword the docstrings at L425-426 and L470-471 that cite `migrate_schedule`. The edit is planned here because it can only happen once every caller has moved.
  - `docs/design/architecture/data/service-inventory.json:1110-1117` and `credential-manifest.json:411` are **not** edited here. WP11 owns them. Leave a history note for WP11.
- Do **not** edit WP07's files (schedule_loader, the YAML, sync/cleanup). WP07 already reworded their `migrate_schedule` mentions.
- `tests/habits/conftest.py:191` was already cleaned up in WP03.
- Out of scope for the NFR-001 ratchet:
  - `scripts/deploy/vikunja_release/**`, `scripts/vikunja/rollback_release.py` and their tests, which are release tooling reading DB columns;
  - the frozen `operations:` block in `scripts/habits/migrations/phase3-schedule.yaml`;
  - `docs/archive/**` and `docs/research/**`, which are history.

## Branch Strategy

- **Strategy**: {{branch_strategy}}
- **Planning base branch**: {{planning_base_branch}}
- **Merge target branch**: {{merge_target_branch}}

```bash
spec-kitty agent action implement WP08 --agent claude --mission felix-rrule-adaptation-01M7TKNX
```

## Subtasks & Detailed Guidance

### Subtask T036 – `create_task --rrule`

- **Steps**:
  1. `build_payload` (L49-86): drop `repeat_after`/`repeat_mode`, and replace their docstring with the rule model.
  2. Rule options:
     - Add `rrule: str | None` and `from_completion: bool`. Validate `rrule` locally with `vikunja_rule.rrule_text_to_parts`, which gives a clear early error.
     - A due date is required when `rrule` is set, **unless** `--initial-due-time HH:MM` is given; the v2 create then generates the first due date (`initial_due_time`).
     - `from_completion` maps to `repeats_from_current_date: true`.
  3. `create_task` (L118-123): use `client.create_task_v2(project_id, fields, rrule=..., initial_due_time=...)`. The client is a `VikunjaClient`; check `_build_client`.
  4. **Readback.** `get_task_v2(created["id"])`. If an rrule was requested, require `same_rule(rrule_text_to_parts(rrule), readback["repeat"])`. Otherwise exit 1 with "created task <id> but its rule is missing/different — fix or delete it". Never report success on a one-off.
  5. CLI flags: `--rrule "FREQ=WEEKLY;INTERVAL=2;COUNT=6"`, `--from-completion`, `--initial-due-time HH:MM`. Remove `--repeat-after` and `--repeat-mode`; argparse rejects them anyway. Help text gives examples for daily, fortnightly, monthly, "N times" (COUNT) and "until" (UNTIL).
- **Tests** (`tests/vikunja/test_create_task.py`, 7 old hits):
  - convert them;
  - add: the create body carries `repeats_rrule`;
  - a readback missing the rule gives exit 1, as the **positive control**;
  - `--from-completion` maps to the flag;
  - `--initial-due-time` with no due date is allowed;
  - an invalid rrule is rejected before any HTTP call.
- **Red-then-green (NFR-002, analysis finding C1).** Run the readback positive-control test on a `cc4f2154` scratch checkout, port the test only, and expect it to fail. Record the failing test names with `spec-kitty agent tasks add-history WP08 --note "red on cc4f2154: ..."`, then show it green on the WP branch.

### Subtask T037 – Retire `migrate_schedule`

- **Steps**:
  1. `git rm scripts/habits/migrate_schedule.py tests/habits/test_migrate_schedule.py`.
  2. Remove the `migrate_schedule` entry from `VIKUNJA_CURRENT_STATE_ALLOWLIST` in `tests/architectural/test_habits_history_canonical_read.py:63`. This is **mandatory**: `test_allowlist_contains_no_stale_entries` (L171-185) fails on a missing file.
  3. Grep once more: `git grep -n migrate_schedule -- scripts tests ':!kitty-specs'`. The only remaining hits should be WP07-owned history comments, if any, and research or archive docs.

### Subtask T038 – Remove `replace_task_fields`

- **Steps**:
  1. Confirm there are no callers: `git grep -n replace_task_fields -- scripts tests`. Only the definition and its own tests should remain.
  2. Delete the method and its tests in `tests/common/test_vikunja_client.py`. That file is owned by WP02; record the out-of-map edit.
  3. Reword the `create_task_in_project` docstring (L470-471) and any `update_task_fields` text that names `replace_task_fields`.

### Subtask T039 – NFR-001 ratchet test

- New `tests/architectural/test_no_retired_repeat_fields.py`:
  - Walk `scripts/**/*.py` and `scripts/openclaw/**/*.md`, excluding the scope list above.
  - Assert there is no `\brepeat_after\b|\brepeat_mode\b|repeat_after_seconds`.
  - For `phase3-schedule.yaml`, check only the `habits:` block: parse the YAML and assert no habit has `repeat_after_seconds`.
- Make the failure message list `file:line`.
- **Prove it can fail.** Point it at a temporary file with one hit (tmp_path) and assert it reports it.

### Subtask T040 – Full suite and architecture validation

```bash
make test
```

```bash
python3 tooling/scripts/validate_architecture_data.py --strict
```

```bash
git grep -nE "repeat_after|repeat_mode" -- scripts ':!scripts/deploy/vikunja_release' ':!scripts/vikunja/rollback_release.py'
```

The grep should show only the frozen `operations:` block. Record the counts with `add-history`: tests passed or failed, and grep hits. Run nothing in GitHub Actions (C-003).

## Risks & Mitigations

- **A WP still using `replace_task_fields`** because of lane ordering. T038 step 1's grep is the gate. If it finds a caller, stop and report; do not migrate it here.
- **Ratchet false positives** in release tooling. Keep the exclusion list explicit and give each entry a reason.

## Review Guidance

- Is `replace_task_fields` gone, and does `update_task_fields` still work (WP02 tests)?
- Does the ratchet test fail on a planted hit?
- Is `create_task` unable to report success for a recurring create that produced a one-off?

## Progress & Status

Use `spec-kitty agent tasks add-history WP08 --note "..."` and `spec-kitty agent tasks mark-status T0xx --status done`.
