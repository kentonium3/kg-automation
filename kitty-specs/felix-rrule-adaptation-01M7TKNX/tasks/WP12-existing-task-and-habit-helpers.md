---
work_package_id: WP12
title: Existing-task and habit-management helpers
dependencies:
- WP09
requirement_refs:
- FR-025
- FR-026
planning_base_branch: fix/felix-rrule-adaptation
merge_target_branch: fix/felix-rrule-adaptation
branch_strategy: Planning artifacts for this mission were generated on fix/felix-rrule-adaptation. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/felix-rrule-adaptation unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-felix-rrule-adaptation-01M7TKNX
base_commit: 5a2005304d147d6e1e5642dca98243d282771067
created_at: '2026-11-20T20:03:05.130826+00:00'
subtasks:
- T056
- T057
- T058
- T059
- T060
phase: Phase 3 - Guidance
history:
- at: '2026-11-20T23:30:00Z'
  actor: claude
  action: Prompt added in-mission (Kent's ruling A on #1111, 2026-11-20; pause semantics A, scope confirmed)
agent_profile: python-pedro
authoritative_surface: scripts/vikunja/update_task.py
create_intent:
- scripts/vikunja/update_task.py
- tests/vikunja/test_update_task.py
- scripts/habits/manage_habit.py
- tests/habits/test_manage_habit.py
- tests/habits/test_paused_habits_excluded.py
execution_mode: code_change
model: claude-opus-5-5
owned_files:
- scripts/vikunja/update_task.py
- tests/vikunja/test_update_task.py
- scripts/habits/manage_habit.py
- tests/habits/test_manage_habit.py
- tests/habits/test_paused_habits_excluded.py
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP12 – Existing-task and habit-management helpers

## ⚡ Do This First: Load Agent Profile

Use the `/spk-charter-profile-load` skill to load the agent profile specified in the frontmatter, and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `python-pedro`
- **Role**: `implementer`
- **Agent/tool**: `claude`

---

## ⚠️ IMPORTANT: Review Feedback

Check `spec-kitty agent tasks status` for a `review_ref`, and address every item before going back to review.

---

## Why this WP exists

This WP was added in-mission on 2026-11-20 (Kent's ruling A on #1111).

During WP09, two agent write paths turned out to have no safe Felix helper. They had run on raw curl writes, which can strip a rule. WP09 switched them off; this WP brings them back on safe seams:

- **tasker** `retroactive_enrichment` / `detect_incomplete` changing an existing task's fields. WP09 left these as "propose, don't write".
- **habits** Pause / Resume / Remove. WP09 left these as "decline; change it in Vikunja".

The pause behaviour is also new. No code on `main` or on this branch skips a `(PAUSED)` habit, although the old habits AGENTS.md claimed that "the morning-list helper excludes paused tasks automatically". Kent chose pause semantics A: keep the description prefix, and make the readers honour it.

## Objectives & Success Criteria

1. **`scripts/vikunja/update_task.py`** (FR-025): `python3 -m scripts.vikunja.update_task --task-id N [--title T] [--description D] [--due ISO] [--priority P] [--project-id ID]`.
   - It writes through `VikunjaClient.patch_task`, sending only the named fields and never a null.
   - It reads the task back with `get_task_v2` and runs the shared `vikunja_rule.recurrence_drift` helper (WP08) against the pre-write read. If the rule, `repeats_from_current_date` or the reminder set changed, it exits 1 with an `unexpected` outcome. A due-date change on a recurring task is refused before any write (exit 2).
   - It refuses rule edits: it has no `--rrule` flag. Unknown flags exit 2.
   - It verifies that every requested field reads back as sent. A 304 counts as success with no change.
   - Its last line is a JSON summary, following `docs/design/helper-script-conventions.md`.
2. **`scripts/habits/manage_habit.py`** (FR-026): `pause|resume|remove --task-id N`.
   - `pause` adds the `(PAUSED) ` description prefix, and `resume` strips it. Both go through `update_task`'s core function, not a subprocess, so the same readback guards apply. Both are idempotent: pausing an already-paused habit is a no-op with exit 0.
   - `remove` calls `VikunjaClient.end_series` (rule cleared, then done, verified) and never deletes the task. On an `end_series` failure, it surfaces the client's recovery outcome rather than retrying blindly.
3. **Paused habits are skipped** by the morning check-in list (`scripts/habits/morning_checkin_list.py` / `query_active_habits_v2.py`) and by the sweeper (`scripts/habits/sweeper.py`).
   - Find where each one gets the task description. The sync cache may not carry it; if not, add it through the sync layer with the smallest change, and say so.
   - A paused habit must never be auto-skipped, swept or listed.
   - Put the predicate in one place, e.g. `is_paused(task)` in `manage_habit.py` or a small shared module, and import it everywhere it's needed.
4. **Docs re-enabled**. These are out-of-map edits of WP09's files: record a one-line rationale for each, and keep both AGENTS.md files under 14,000 bytes.
   - tasker AGENTS.md § "Existing tasks": field changes Kent confirmed go through `update_task`. Rule and recurring-due changes still say "change it in Vikunja". `confirmed` is recorded only after every confirmed change is applied.
   - habits AGENTS.md: Pause / Resume / Remove use `manage_habit`, after the existing name-resolution and confirmation step.
   - vikunja-api SKILL § Updating Tasks: list `update_task` and `manage_habit` among the helpers.
   - `tests/architectural/test_agent_docs_no_direct_task_writes.py` and `test_no_retired_repeat_fields.py` must still pass with no new allowances.

## Subtasks

T056 `update_task` helper + tests (WP12)
T057 `manage_habit` pause/resume/remove + tests (WP12)
T058 Paused habits skipped by the morning list and the sweeper + tests (WP12)
T059 Re-enable the tasker and habits doc paths and the vikunja-api helper list (WP12)
T060 Full validation (WP12)

## Test strategy

- Round-trip tests with the shared v2 factory (`tests/common/vikunja_v2_factory.py`), on a task with `repeats_from_current_date=true`, a rule, and relative plus absolute reminders. After update, pause, resume and remove, everything that should survive does.
- Corruption controls, each of which must exit non-zero:
  - the server drops the reminders;
  - the server flips the flag;
  - the server drops the rule on a field update;
  - a requested field does not read back as sent.
- Refusals with zero HTTP writes (assert on the mock): a due change on a recurring task, an unknown flag, an empty change set.
- Remove: assert the two PATCHes `end_series` makes, and that no DELETE is ever sent.
- Paused exclusion:
  - a paused habit is absent from the morning list and untouched by a sweeper tick;
  - resuming brings it back;
  - a non-paused habit whose title merely contains "PAUSED" is not excluded, because the predicate tests the description prefix.
- Prove the tests can fail: they must fail with the readback guard or the predicate disabled.

## Constraints

- No live Vikunja or office2. Never read token files. Never send an explicit JSON null except through `end_series`.
- Run the full suite with `TMPDIR=/dev/shm` and the repo venv; it must be green.
- Commit with `spec-kitty safe-commit <explicit paths>`, with a Co-Authored-By trailer.
- Never use bare `git stash`.

## Review Guidance

Reviewers should check:
- the readback guard is live, i.e. called on every write path;
- the paused predicate has one definition and every reader uses it;
- no doc path tells an agent to write a task by curl or the raw API;
- the AGENTS.md sizes are under 14,000 bytes.
