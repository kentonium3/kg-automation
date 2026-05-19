---
affected_files: []
cycle_number: 1
mission_slug: habits-native-repeat-jsonl-state-01KS0M59
reproduction_command:
reviewed_at: '2026-05-19T19:35:04Z'
reviewer_agent: unknown
verdict: rejected
wp_id: WP03
---

# WP03 Review Feedback — Cycle 1/3

**Reviewer**: codex:gpt-5:python-reviewer:reviewer (verdict relayed by orchestrator — codex sandbox blocked the move-task write).

**Verdict**: Changes requested.

## Blocking finding

`reconcile_completions.py` enumerates ALL unarchived Vikunja tasks and could write non-habit completions to the habits JSONL log.

Current implementation: `_enumerate_active_habits()` calls `GET /tasks/all?filter=is_archived = false`, returning every unarchived task. Backfill path at `reconcile_completions.py:268`: any task with `done=true` + valid `done_at` that has no matching JSONL entry is appended to the habits log with `source="vikunja-ui"`.

Consequence: a completed Inbox / Goals / Recurring-event task would be backfilled into the habits domain log, violating FR-008 ("active habit tasks" scope) and the Phase 2 state_log contract (one domain per log; cross-domain entries corrupt canonical history).

The drift path is incidentally protected (only emits warnings when an existing habits JSONL row exists; non-habit tasks never have such rows). The bug only surfaces on backfill.

## Required fix

Narrow `_enumerate_active_habits()` to return only real habit tasks BEFORE the backfill decision. Approaches:

1. **Project-scoped enumeration (recommended)**: resolve the Habits project ID (like `scripts/habits/query_active_habits.py` already does) and use `GET /projects/<id>/tasks?filter=is_archived = false`.
2. **Label-based filter**: filter by a habit-discriminating label.
3. **Known-ID set**: cross-check against known habit task IDs from `phase3-schedule.yaml` (least ideal — couples reconcile to the migration config).

Option 1 matches the existing project pattern in the same scripts dir.

## Required regression test

Add a test to `tests/habits/test_reconcile_completions.py` that:
- Mocks enumerate response to include BOTH a completed habit task AND a completed non-habit task.
- Asserts habits JSONL is appended only for the habit task.
- Asserts the non-habit task does NOT appear in JSONL after reconcile.

## Non-blocking spot-checks (passed)

- G4 PUT verification at record_completion.py:276 — correct, dedicated test in place.
- Coverage: record_completion 91%, reconcile_completions 86% — both above NFR-005 ≥85% target.
- All 57 WP03 tests pass.

## Cycle tracking

Cycle 1/3. Re-implementer should apply Option 1 unless a strong reason to choose otherwise, and add the regression test.
