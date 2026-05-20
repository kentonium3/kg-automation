# Fix Vikunja G7 query filter for habits v2 — Specification

**Mission**: `vikunja-g7-query-filter-fix-01KS1K1Y`
**Mission ID**: `01KS1K1YE6H1CTY29A6MRWW836`
**Mission type**: software-dev (fix-focused)
**Source**: GitHub issue [#336](https://github.com/kentonium3/issues/336)
**Risk tier**: 3 (Standard — Python helper script change; no schema/state changes)
**Created**: 2026-05-19 (UTC 2026-05-20)

---

## Overview

`scripts/habits/query_active_habits_v2.py` sends a Vikunja-native filter expression `due_date <= {today}T23:59:59Z AND done = false` to `GET /projects/13/tasks?filter=<expr>`. Vikunja v0.24.6 rejects this with HTTP 400 — the compound expression with a date comparison and a boolean equality is not accepted by the server's filter syntax.

This is the **same class of bug as G6** (#333 — `is_archived` server-side filter rejection). The fix is the same pattern: drop the server-side filter expression, enumerate the project's tasks, and filter client-side in Python.

Surfaced during Phase 5 cutover smoke-test (#308) on 2026-05-20 02:00 UTC. Without this fix, the habits agent's morning check-in v2 path fails at Step 2; the agent falls back to ad-hoc behavior (reading the v1 helper) or hits Step 4.5 (helper failure handling).

---

## User Scenarios & Testing

### Primary actor

**felix-admin-habits agent** (claude-haiku-4-5 on office2) — invokes `query_active_habits_v2` at Step 2 of the morning check-in workflow. The agent expects newline-delimited JSON on stdout describing today's active habit tasks.

### Scenario 1 — Morning cron Step 2 succeeds with client-side filter

At the next morning cron tick post-fix-deploy:

1. The agent runs `cd /home/claude/kg-automation && python3 -m scripts.habits.query_active_habits_v2 --today 2026-05-21`.
2. The helper makes a single `GET /api/v1/projects/13/tasks` HTTP call (no `filter` query parameter).
3. Vikunja returns 200 with the full Habits project task list (all tasks, no server-side filtering).
4. The helper filters in Python: keep tasks where `done == false` AND `due_date <= 2026-05-21T23:59:59` (UTC normalized).
5. The helper preserves the existing PAUSED-label exclusion (label-based filter; happens in Python today and continues to happen in Python).
6. Exit code 0; stdout emits one JSON object per active task (JSONL).

### Scenario 2 — `reconcile_completions.py` audit (no change needed)

The reconcile helper already uses the client-side filter pattern for `is_archived` (G6 fix from #333). Audit confirms no server-side `due_date` or `done` filter usage. No code change to reconcile_completions.py.

### Scenario 3 — Vikunja API still down or returns 5xx

The helper continues to exit 1 on Vikunja API failures (existing behavior). No behavior change for failure paths.

### Scenario 4 — G7 documented in research doc

A reader of `docs/design/research/vikunja-task-model-research.md` sees G7 in the Verified API Gotchas appendix, with the verification date, the exact failing expression, the HTTP status, and the workaround pattern. Future helpers and reviewers consult this entry before constructing server-side filters.

---

## Functional Requirements

| ID | Requirement | Status |
|---|---|---|
| FR-001 | `scripts/habits/query_active_habits_v2.py` no longer sends a `filter=...` query parameter to `GET /projects/<id>/tasks`. The HTTP URL is `GET /api/v1/projects/13/tasks` (with default pagination params if applicable). | Active |
| FR-002 | The helper applies the equivalent filter logic in Python: tasks are kept iff `task["done"] == False` AND `task["due_date"] <= <today>T23:59:59Z` (ISO-8601 lex compare against the UTC normalized today). | Active |
| FR-003 | The helper preserves the existing PAUSED-label exclusion. Any task with the `paused` label (case-insensitive) is excluded. | Active |
| FR-004 | The helper's stdout format is unchanged: newline-delimited JSON, one object per surviving task, fields: `id`, `title`, `description`, `due_date`, `done`, `repeat_after`, `project_id`, `labels` (whichever subset is currently emitted). | Active |
| FR-005 | Exit codes are unchanged: 0 success (empty result OK), 1 Vikunja API failure, 2 usage error. | Active |
| FR-006 | `scripts/habits/reconcile_completions.py` is audited for similar filter-expression usage. If similar bugs are found, they are fixed in the same mission. Audit outcome documented in the mission's research.md. (Expectation: no change needed; reconcile already uses client-side filtering.) | Active |
| FR-007 | `docs/design/research/vikunja-task-model-research.md` Verified API Gotchas appendix gains a G7 entry documenting the failure expression, HTTP status, workaround pattern, verification date (2026-05-20), and the surfacing session ID. | Active |
| FR-008 | At least one new test in `tests/habits/` exercises the client-side filter logic. The test mocks the Vikunja `/projects/13/tasks` HTTP response and asserts the helper's filter logic correctly excludes `done == true` tasks, includes `due_date <= today` tasks, and respects the PAUSED-label exclusion. | Active |

## Non-Functional Requirements

| ID | Requirement | Threshold | Status |
|---|---|---|---|
| NFR-001 | Helper wall-clock runtime stays under the existing budget (Phase 3 baseline was sub-second for a project with ~15 tasks). | < 2s | Active |
| NFR-002 | All existing habits tests pass post-fix (Phase 4 baseline was 314 tests; expect 314+ post-this-mission with the new test added). | All passing | Active |
| NFR-003 | Code coverage for `query_active_habits_v2.py` remains at or above the Phase 3 baseline (85%+). | ≥ 85% coverage | Active |

## Constraints

| ID | Constraint | Status |
|---|---|---|
| C-001 | This mission ONLY fixes the G7 filter bug. No other behavior changes. No refactors. No CLI surface changes. No new flags. | Active |
| C-002 | The helper's exit code semantics are preserved. Tests that assert specific exit codes must continue to pass. | Active |
| C-003 | The reconcile_completions.py audit is documented; if no change is needed, the audit outcome is recorded in research.md and no code in that file changes. | Active |
| C-004 | felix-bot identity authentication continues to be the only Vikunja write attribution path. No identity changes. | Active |
| C-005 | After merge, the operator (Kent) syncs the updated `query_active_habits_v2.py` to office2. This may use a simple scp / rsync command or rely on a future git-pull deploy mechanism. The deploy command is documented in the mission's quickstart.md. | Active |

---

## Key Entities

### `scripts/habits/query_active_habits_v2.py` (the deliverable)

Current state: builds a Vikunja-native filter expression in `_build_filter_expression(today)`, then sends it as a `filter` query param. Vikunja v0.24.6 rejects with HTTP 400.

Post-mission state: no filter expression in the HTTP request; full project task list fetched; filter applied in Python. PAUSED-label exclusion preserved (already client-side today).

### `scripts/habits/reconcile_completions.py` (audited, expected unchanged)

Already uses `GET /projects/<id>/tasks` (no server-side `filter` param) and filters client-side. The G6 (`is_archived`) workaround pattern is documented in its docstring (lines 188-193 of the pre-mission file).

### `docs/design/research/vikunja-task-model-research.md` (docs update)

Gains a G7 entry in the Verified API Gotchas appendix. Existing G1-G6 entries are preserved.

### `tests/habits/` (new test file or extended existing)

Gains a test that mocks the Vikunja HTTP response and exercises the client-side filter logic. Existing 314 tests continue to pass.

### Cron jobs (consumers, not modified)

- `habits-morning-checkin` — daily 11:00 UTC. Step 2 of its workflow calls `query_active_habits_v2`. Post-fix, Step 2 succeeds; the agent proceeds to Step 4 (exclude_completed_v2 pipe).

---

## Success Criteria

| ID | Criterion |
|---|---|
| SC-001 | After fix-deploy: a manual invocation of `python3 -m scripts.habits.query_active_habits_v2 --today $(date -u +%Y-%m-%d)` on office2 exits 0 and emits at least 1 line of JSONL (assuming active habits exist). |
| SC-002 | The next `habits-morning-checkin` cron tick post-deploy completes Step 2 without HTTP 400; the agent's session log shows `query_active_habits_v2` returned active habits and the agent proceeded to Step 4. |
| SC-003 | All existing 314 habits tests continue to pass. The new client-side-filter test passes. |
| SC-004 | `docs/design/research/vikunja-task-model-research.md` Verified API Gotchas appendix has a G7 entry. |
| SC-005 | `reconcile_completions.py` audit outcome is documented in mission's `research.md` (whether or not code changed). |

---

## Assumptions

1. The Vikunja Habits project ID is 13 (consistent with Phase 3 hardcode; not parameterized in this mission).
2. The total number of tasks in the Habits project is small enough (~15-30) that enumerating all of them and filtering client-side has negligible performance impact.
3. The PAUSED-label exclusion logic already in `query_active_habits_v2.py` continues to work; it's label-based (Python-side) and unaffected by this fix.
4. Helper deploy mechanism: Kent runs an scp/rsync after merge to push the updated `.py` file to office2's `/home/claude/kg-automation/scripts/habits/`. Alternatively, future deploy automation lands separately (out of scope for this mission).
5. The `--today YYYY-MM-DD` flag and its default-to-UTC-today behavior are preserved; only the HTTP-call shape changes.

---

## Out of scope

- AGENTS.md changes (already hotfixed in commit `4e7177c`).
- Changes to `query_active_habits_v2`'s CLI surface (no new flags, no renames).
- Changes to other v2 helpers (`exclude_completed_v2`, `record_completion`) unless audit reveals similar bugs (expected: none).
- Deploy automation. The scope is the code fix + docs + tests, not the deploy pipeline.
- Phase 6 (#309) escalation migration.
- Phase 7 (#310) tasker/enrichment migration.
