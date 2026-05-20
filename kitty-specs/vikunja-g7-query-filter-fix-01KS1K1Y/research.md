# Research: Tactical decisions for G7 query filter fix

**Mission**: `vikunja-g7-query-filter-fix-01KS1K1Y`
**Phase**: 0 (research — content + reconcile audit outcome)

This mission is small (one helper bug fix). Research focuses on three tactical questions and the reconcile_completions.py audit outcome.

---

## D1 — Where to perform the client-side filter

**Decision**: Apply the client-side filter inside `query_active_today()`, immediately after the HTTP response is parsed and before the function returns. The function continues to return only active-today habits (its existing contract).

**Rationale**:
- Mirrors the pattern in `reconcile_completions.py` (lines 188-193) where client-side filtering is colocated with the HTTP call.
- Callers of `query_active_today` (currently only `main()` in the same file) shouldn't have to know that filtering is now client-side.
- Keeps the test surface clean: the test mocks the HTTP response, calls `query_active_today()`, and asserts the returned list contains only the expected tasks.

**Rejected alternative**:
- **Filter in `main()` after `query_active_today` returns the full list**: leaks the filter responsibility to callers. Future callers might assume the function returns the full project list (because the HTTP call now does). Tighter to keep the function contract narrow.

---

## D2 — Disposition of `_build_filter_expression()`

**Decision**: REMOVE the `_build_filter_expression(today)` function entirely. Also remove the import of `urllib.parse` if no other code in the file uses it.

**Rationale**:
- The function is only called by `query_active_today()`, which no longer needs it.
- Leaving it as dead code invites future callers to use the rejected filter pattern.
- The docstring's filter expression `due_date <= now/d AND done = false` will live ONLY in the G7 entry of `vikunja-task-model-research.md` — as a NEGATIVE example (don't do this).

**Rejected alternatives**:
- **Keep the function for tests**: no existing test imports `_build_filter_expression`. Verified by `grep -r "_build_filter_expression" tests/`. No need to keep it.
- **Keep the function but mark as deprecated**: introduces deprecation tracking overhead for zero benefit.

---

## D3 — Reconcile audit outcome

**Decision**: NO code change to `scripts/habits/reconcile_completions.py`. Audit confirms it already uses the client-side filter pattern.

**Evidence**:
- Grep on `reconcile_completions.py` for `filter\|due_date\|done = \|/projects/`: only relevant match is line 191 documenting "Vikunja v0.24.6's filter syntax does not accept `is_archived` as a filterable field — server-side filtering returns HTTP 400. Client-side filter is the workaround."
- The HTTP call uses `GET /projects/<id>/tasks` (no `?filter=`).
- The smoke-test session log from Phase 5 cutover (`fb54e5d2-6179-4507-8350-99bc32867ff2.jsonl`) shows reconcile completed successfully (`tasks_examined: 13, backfilled: 1, drift: 0, errors: 0`).

**Audit conclusion**: pass. No change needed.

---

## D4 — Test strategy

**Decision**: Add one new test file `tests/habits/test_query_active_habits_v2_filter.py` with the following cases:

1. **Happy path — active today**: mock HTTP returns 3 tasks, one with `done=true` (should be excluded), one with `due_date > today` (should be excluded), one with `due_date <= today AND done=false` (should be kept). Assert the function returns exactly the one expected task.

2. **All tasks done**: mock HTTP returns 2 tasks, both with `done=true`. Assert the function returns an empty list (exit 0).

3. **All tasks future**: mock HTTP returns 2 tasks, both with `done=false AND due_date > today`. Assert empty list.

4. **Date comparison edge case — equal**: a task with `due_date == today + 23:59:59Z` is included (`<=` boundary).

5. **HTTP 400 on the new URL**: mock raises 400 (e.g., if Vikunja returns 400 for a project that doesn't exist). Assert the function raises OSError (existing behavior preserved).

**Mocking approach**: use `unittest.mock.patch` on the `_http_get` private function (or whichever HTTP helper is the call site).

**Test count**: 5 new tests. Brings total habits tests from 314 to 319.

**Rationale**: the contract being tested is "filter logic is now in Python". The mock approach lets us assert exactly which tasks survive the filter. We don't need to test the HTTP transport layer (already covered by Phase 3 tests).

---

## D5 — `vikunja-task-model-research.md` G7 entry

**Decision**: Append a G7 section to the Verified API Gotchas appendix following the same format as G1-G6.

**Required content**:

```markdown
### G7 — Compound server-side filter `due_date <= <iso> AND done = false` rejected

**Status**: Verified 2026-05-20

**Symptom**: `GET /projects/<id>/tasks?filter=due_date <= <iso> AND done = false` returns HTTP 400 with `{"code":...}` body.

**Example failing URL** (URL-decoded):
GET /api/v1/projects/13/tasks?filter=due_date <= 2026-05-19T23:59:59Z AND done = false

**Surfacing context**:
- Surfaced during Phase 5 cutover smoke-test (#308).
- Session log: `/home/claude/.openclaw/agents/felix-admin-habits/sessions/fb54e5d2-6179-4507-8350-99bc32867ff2.jsonl` on office2.
- Cron run: `openclaw cron runs --id 3082343c-bc7f-47ee-916b-ee070b1e50dc`, ts 1779242530389.

**Workaround**: drop the `filter` query parameter, enumerate `/projects/<id>/tasks`, and apply the filter in Python. Same pattern as G6 (#333).

**Affected helpers**: `scripts/habits/query_active_habits_v2.py` (fixed in #336).

**Related**: G6 (`is_archived` field rejection — same class of bug).
```

**Rationale**: future helpers and reviewers will consult this entry before constructing server-side filters. Each gotcha entry documents the verification date, the exact failing expression, and the workaround. Keeps the gotchas appendix as the authoritative single source for Vikunja v0.24.6 quirks.

---

## Summary

Three tactical decisions + one audit outcome + one test strategy. The mission is small and well-defined; no `[NEEDS CLARIFICATION]` markers required. Ready for Phase 1 design artifacts.
