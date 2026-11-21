---
work_package_id: WP05
title: Intake and bulk tools
dependencies:
- WP01
- WP02
requirement_refs:
- FR-007
- FR-008
- FR-009
- FR-010
- FR-020
- NFR-002
- SC-005
planning_base_branch: fix/felix-rrule-adaptation
merge_target_branch: fix/felix-rrule-adaptation
branch_strategy: Planning artifacts for this mission were generated on fix/felix-rrule-adaptation. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/felix-rrule-adaptation unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-felix-rrule-adaptation-01M7TKNX
base_commit: a668375f9670d501c278ee1f6bc8a46f4e63d432
created_at: '2026-11-19T23:19:37.176058+00:00'
subtasks:
- T022
- T023
- T024
- T025
phase: Phase 2 - Remaining write paths
history:
- at: '2026-11-19T22:30:00Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
agent_profile: python-pedro
authoritative_surface: scripts/intake/
create_intent:
- tests/intake/test_apply_reply_rule_roundtrip.py
execution_mode: code_change
model: claude-opus-5-5
owned_files:
- scripts/intake/apply_reply.py
- scripts/vikunja/migrate_tasks.py
- scripts/vikunja/migrate_date_only_due_dates.py
- tests/intake/test_apply_reply.py
- tests/vikunja/test_migrate_tasks.py
- tests/vikunja/test_migrate_date_only_due_dates.py
- tests/intake/test_apply_reply_rule_roundtrip.py
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP05 – Intake and bulk tools

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

Fix audit rows 7–11 (#1111).

**Two** writable-field allowlists exist (research.md R-007):
- `scripts/intake/apply_reply.py:164-181`, which only "mirrors" the other;
- `scripts/vikunja/migrate_tasks.py:143-156`, which `migrate_date_only_due_dates.py:37-41` imports.

Both lack `repeat`, `repeats_from_current_date` and `reminders`, so every write strips them. The readbacks only check allowlisted fields, so they can't see the damage.

After this WP:
1. **Both allowlists and both `_writable_payload` copies are gone.** Each site sends only its changed fields through `patch_task`.
2. **Every site's readback** asserts `same_rule(before, readback)`, the `repeats_from_current_date` flag and the reminder set, as well as its own changes, and fails loudly with the existing error type.
3. **Intake eliminate** (L588-591) on a recurring task uses `end_series`, so the task ends Done and stays Done (FR-008). A non-recurring eliminate stays `{"done": true}`.
4. `_is_recurring` (L419-422) reads `has_rule(task)` (FR-009).

## Context & Constraints

- Spec: FR-007, FR-008, FR-009, FR-010, FR-020, NFR-002. Plan IC-04. data-model.md Invariant 2 (non-completion writes) and the end-series contract. Client contract: `patch_task`, `end_series`, `SeriesEndIncomplete`.
- **The callers use a `client` object.** Grep where it's constructed (the kent token, `KENT_TOKEN`). If it is not a `VikunjaClient`, adapt by constructing one with the same token. Keep the token-loading seam unchanged, and never print the token.
- **Readback reads:** `migrate_tasks` and `migrate_date_only` use `client.get('/tasks/{id}')` on v1. v1 GET carries `repeat` but not `repeats_rrule`, which is fine for `same_rule`. You may switch them to `get_task_v2` for consistency.
- **Label behaviour.** The move readback's label-survival check (`migrate_tasks.py` around L850+) must keep working. Labels are not in the PATCH body.
- **Due-date compare.** Keep the instant comparison via `et_datetime.parse_vikunja_instant` (#757).
- **Project move via PATCH `project_id`** is writable in the fork (`tasks.go:1518-1533`). Pin it with a test against the fake server's expected request shape. Note in the history that live verification happens in the post-merge canary.

## Branch Strategy

- **Strategy**: {{branch_strategy}}
- **Planning base branch**: {{planning_base_branch}}
- **Merge target branch**: {{merge_target_branch}}

```bash
spec-kitty agent action implement WP05 --agent claude --mission felix-rrule-adaptation-01M7TKNX
```

## Subtasks & Detailed Guidance

### Subtask T022 – `apply_reply` writes

- **Steps**:
  1. Delete `_WRITABLE_FIELDS` and `_writable_payload` from `apply_reply.py`.
  2. Rewrite `_post_task_fields(client, task, changes)` so that it:
     - (a) does `client.patch_task(task["id"], changes)`;
     - (b) reads back with `get_task_v2`;
     - (c) checks each change as today (due-date instant compare; equality for the rest);
     - (d) **additionally** requires `same_rule(task.get("repeat"), readback.get("repeat"))` and `bool(task.get("repeats_from_current_date")) == bool(readback.get("repeats_from_current_date"))`, and that the reminder lists are equal when compared as a sorted list of `(reminder, relative_period, relative_to)`. Relative reminders may move with the due date, so when `due_date` is in `changes`, compare only the `relative_*` keys for those reminders (data-model.md Invariant 2).

     On mismatch, raise `ApplyError` with a message that names the field and both values.
  3. Remove `done_at` handling. It is read-only server-side and was only in the allowlist.
  4. Rename the function to `_patch_task_fields` and update its callers.
- **Files**: `scripts/intake/apply_reply.py`

### Subtask T023 – Eliminate and `_is_recurring`

- **Steps**:
  1. In the planning code (L588-591), when `line.quadrant == ELIMINATE_QUADRANT` and the task is not done:
     - if `has_rule(task)`, set a plan flag `plan.end_series = True` and record a note: "eliminated — recurring series ended (rule cleared, done)";
     - otherwise keep `field_changes["done"] = True`.
  2. In the apply step, run `end_series` **instead of** the field patch for `done`. Other field changes in the same plan, such as labels, still apply. Ordering:
     - (a) labels;
     - (b) other field changes excluding `done`;
     - (c) `end_series`.

     Catch `SeriesEndIncomplete` and map it to a per-line `failed` with the state in the message (`rule_cleared_not_done` and so on). Never report success on a partial end.
  3. `_is_recurring(task)` returns `has_rule(task)`, and its docstring is updated.
- **Notes**: The existing intake reply semantics (FR-008 of the earlier intake mission) are "eliminate → done". This keeps them, and makes them true for recurring tasks too.

### Subtask T024 – Bulk tools

- **Steps**:
  1. `migrate_tasks.py`:
     - Delete `_WRITABLE_FIELDS` (L143-156) and `_writable_payload` (L778-785).
     - `move_task` does `patch_task(task_id, {"project_id": to_pid})`, then reads back and checks `project_id`, the label survival (unchanged), `same_rule`, the from-current flag and reminders.
     - Raise `ReconcileError` on mismatch.
  2. `migrate_date_only_due_dates.py`:
     - Stop importing the allowlist.
     - `apply_change` does `patch_task(task_id, {"due_date": new_due})`, then reads back and checks the instant and `same_rule`, flag and reminders (relative reminders may move).
     - Raise `MigrationError` on mismatch.
  3. Grep for any other importer of `migrate_tasks._WRITABLE_FIELDS` or `_writable_payload` and fix it in place. Record any out-of-map edit with a one-line rationale in the history.

### Subtask T025 – Tests

- New `tests/intake/test_apply_reply_rule_roundtrip.py`, using the WP01 factory and `mock_vikunja_urlopen`:
  - a project move of a recurring task: the PATCH body is exactly `{"project_id": N}`, and the readback rule check passes;
  - a due change: the PATCH body is exactly `{"due_date": ...}`;
  - **positive control**: the fake readback returns `strip_rule(task)`, which must raise `ApplyError`;
  - eliminate on a recurring task: the request sequence is GET, PATCH `{"repeat": null}`, GET, PATCH `{"done": true}`, GET, with no single body containing both keys;
  - eliminate on a one-off: PATCH `{"done": true}`;
  - eliminate where step 2 returns 500: the line is `failed` with `rule_cleared_not_done`;
  - `_is_recurring` is true or false on the new shape, and the habit note fires.
- Convert `tests/intake/test_apply_reply.py` (4 old-shape hits) and `tests/vikunja/test_migrate_tasks.py` (7). Add move and date-migration positive controls (a stripped rule must fail) to `tests/vikunja/test_migrate_tasks.py` and `tests/vikunja/test_migrate_date_only_due_dates.py`.
- Red-then-green: run the new intake file plus the bulk positive controls on a `cc4f2154` scratch checkout, and record the failures with `add-history`.

```bash
python3 -m pytest -q tests/intake tests/vikunja
```

```bash
make test
```

## Risks & Mitigations

- **Relative reminders.** They move with the due date by design (research.md R-001 hazard 6). The check must allow that and still catch removal.
- **Hidden importers** of the deleted allowlist: grep the whole repo.

## Review Guidance

- Both allowlists are gone (grep `_WRITABLE_FIELDS`).
- The eliminate sequence and the partial-failure mapping are tested.
- Every readback checks the rule, not only the changed fields.

## Progress & Status

Use `spec-kitty agent tasks add-history WP05 --note "..."` and `spec-kitty agent tasks mark-status T0xx --status done`.
