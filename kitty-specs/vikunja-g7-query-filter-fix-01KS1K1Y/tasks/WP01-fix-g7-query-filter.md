---
work_package_id: WP01
title: Fix G7 query filter + add test + docs
dependencies: []
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-004
- FR-005
- FR-006
- FR-007
- FR-008
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-vikunja-g7-query-filter-fix-01KS1K1Y
base_commit: 82932f7d11365fcbef8a51a69b833c77924ceb37
created_at: '2026-05-20T02:30:37.289490+00:00'
subtasks:
- T001
- T002
- T003
- T004
- T005
- T006
shell_pid: "25272"
agent: "codex:gpt-5:spec-kitty-review:reviewer"
history:
- date: '2026-05-20T02:30:00Z'
  event: created
  note: G7 filter fix — single WP for the helper change, test, docs append, and reconcile audit.
authoritative_surface: scripts/habits/
execution_mode: code_change
mission_id: 01KS1K1YE6H1CTY29A6MRWW836
mission_slug: vikunja-g7-query-filter-fix-01KS1K1Y
owned_files:
- scripts/habits/query_active_habits_v2.py
- tests/habits/test_query_active_habits_v2_filter.py
- docs/design/research/vikunja-task-model-research.md
- kitty-specs/vikunja-g7-query-filter-fix-01KS1K1Y/research.md
priority: P1
tags: []
---

# WP01 — Fix G7 query filter + add test + docs

## Objective

Drop the server-side filter from `scripts/habits/query_active_habits_v2.py`. Apply the equivalent `done == false AND due_date <= today` filter in Python. Mirror the pattern already used in `reconcile_completions.py` (the G6 #333 fix).

Also: add a test exercising the new client-side filter, append a G7 entry to the Verified API Gotchas appendix in `docs/design/research/vikunja-task-model-research.md`, and audit `reconcile_completions.py` for similar issues (expected: no change needed).

After this WP merges and the operator deploys, the morning check-in cron's Step 2 will succeed end-to-end without falling back to v1.

---

## Context (read these before editing)

1. **Spec**: [`spec.md`](../spec.md) — FR/NFR/C requirements, scenarios.
2. **Research / tactical decisions**: [`research.md`](../research.md) — D1 (filter location), D2 (remove `_build_filter_expression`), D3 (reconcile audit pass), D4 (test strategy), D5 (G7 entry format).
3. **Code surface map**: [`data-model.md`](../data-model.md) — BEFORE/AFTER pseudocode for `query_active_today()`.
4. **Operator deploy**: [`quickstart.md`](../quickstart.md) — what happens after merge.
5. **GitHub issue**: [#336](https://github.com/kentonium3/kg-automation/issues/336).
6. **Reference pattern**: `scripts/habits/reconcile_completions.py` lines 188-193 (the G6 #333 fix; mirror this pattern).

---

## Subtasks

### Subtask T001 — Refactor `query_active_today()` to client-side filter

**Purpose**: Replace the server-side `?filter=` query with a full project enumeration + Python-side filter.

**Steps**:

1. Open `scripts/habits/query_active_habits_v2.py`. Locate `query_active_today(api_base_url, token, today=None)` (around line 199 in the pre-mission file).
2. Modify the HTTP URL construction:
   - **Before**: `url = _join_url(api_base_url, f"projects/{project_id}/tasks?{query}")` where `query` is the URL-encoded filter expression.
   - **After**: `url = _join_url(api_base_url, f"projects/{project_id}/tasks")` (no query string).
3. After parsing the HTTP response into `payload`, add the client-side filter loop:
   ```python
   boundary = f"{today_date}T23:59:59Z"
   out: list[dict] = []
   for item in payload:
       if not isinstance(item, dict):
           continue
       if item.get("done", False):
           continue
       due = item.get("due_date") or ""
       if not due or due > boundary:
           continue
       out.append(item)
   return out
   ```
4. **Boundary semantics**: The Vikunja-unset sentinel `"0001-01-01T00:00:00Z"` lex-compares less than today's boundary, so unset-due-date tasks ARE included by the `<=` filter (matches server-side semantics). Empty-string `due_date` (truly absent field) is excluded.
5. Update the docstring of `query_active_today` to reflect the new behavior: "Fetches all habit tasks in the Habits project (no server-side filter) and filters client-side for `done == false AND due_date <= today`. The native server-side filter pattern is rejected by Vikunja v0.24.6 — see G7 in vikunja-task-model-research.md."

**Files modified**:

- `scripts/habits/query_active_habits_v2.py`

**Validation**:

- [ ] The HTTP URL is `projects/<id>/tasks` (no `?filter=`).
- [ ] The function still returns a list of dicts with the expected fields.
- [ ] Exit codes unchanged (0 success, 1 Vikunja failure, 2 usage error).

---

### Subtask T002 — Remove `_build_filter_expression()` + audit `urllib.parse` import

**Purpose**: Remove dead code that would tempt future callers to use the rejected filter pattern.

**Steps**:

1. Delete the `_build_filter_expression(today)` function entirely (around lines 172-191).
2. Audit the file's imports: if `urllib.parse` is now unused (only `urlencode` was called for the filter expression), remove the import. Keep `urllib.request` (used by `_http_get`).
3. Verify no other code in the file references `_build_filter_expression`:
   ```bash
   grep -n "_build_filter_expression" scripts/habits/query_active_habits_v2.py
   # Expected: no matches
   ```
4. Verify no test imports the function:
   ```bash
   grep -rn "_build_filter_expression" tests/
   # Expected: no matches
   ```

**Files modified**:

- `scripts/habits/query_active_habits_v2.py`

**Validation**:

- [ ] `grep -n "_build_filter_expression" scripts/habits/query_active_habits_v2.py` returns no matches.
- [ ] If `urllib.parse` import was removed, the file's import block is consistent.

---

### Subtask T003 — Add client-side filter test

**Purpose**: Verify the new filter logic behaves correctly per the research.md D4 cases.

**Steps**:

1. Create `tests/habits/test_query_active_habits_v2_filter.py`.
2. Add 5 test cases (each ~10 lines):
   - **test_happy_path_mixed_states**: mock `_http_get` to return 3 tasks — one done=true, one due_date > today, one done=false AND due_date <= today. Assert the function returns only the one expected task.
   - **test_all_done**: mock returns 2 tasks both with done=true. Assert empty list.
   - **test_all_future**: mock returns 2 tasks both with done=false AND due_date > today. Assert empty list.
   - **test_boundary_inclusive**: a task with due_date EXACTLY `<today>T23:59:59Z`. Assert included.
   - **test_http_400_propagates**: mock `_http_get` to raise OSError (simulating HTTP 400 on the new URL). Assert the function raises OSError.
3. Mocking approach (find the actual import path during impl):
   ```python
   from unittest.mock import patch
   import scripts.habits.query_active_habits_v2 as qa

   def test_happy_path_mixed_states():
       payload = [
           {"id": 1, "title": "Done", "done": True, "due_date": "2026-05-15T12:00:00Z"},
           {"id": 2, "title": "Future", "done": False, "due_date": "2026-05-25T12:00:00Z"},
           {"id": 3, "title": "Active", "done": False, "due_date": "2026-05-19T08:00:00Z"},
       ]
       with patch.object(qa, "_http_get", return_value=(200, payload)), \
            patch.object(qa, "_resolve_habits_project_id", return_value=13):
           result = qa.query_active_today("http://test", "token", today="2026-05-19")
       assert len(result) == 1
       assert result[0]["id"] == 3
   ```
   Adapt patch paths to whatever the actual private helpers are named.

**Files modified**:

- `tests/habits/test_query_active_habits_v2_filter.py` (NEW)

**Validation**:

- [ ] File exists with 5 test functions.
- [ ] `pytest tests/habits/test_query_active_habits_v2_filter.py` exits 0 with 5 tests passing.

---

### Subtask T004 — Audit `reconcile_completions.py` + document outcome

**Purpose**: Confirm the reconcile helper doesn't have a similar server-side filter bug. Document the audit outcome.

**Steps**:

1. Re-verify by grep:
   ```bash
   grep -n "filter=\|filter+\?filter" scripts/habits/reconcile_completions.py
   ```
   Expected: no `?filter=` URL query construction. The only filter-related strings should be docstring mentions of the G6 workaround.
2. Confirm the reconcile HTTP call is `GET /projects/<id>/tasks` (no filter).
3. Append the audit outcome to `kitty-specs/vikunja-g7-query-filter-fix-01KS1K1Y/research.md` D3 section. The current text already documents the expected outcome; if the audit confirms no issues, just verify the existing D3 text is accurate. If the audit reveals issues, update D3 AND add the necessary fix to `reconcile_completions.py` (this would expand WP scope — STOP and consult Kent first).

**Files modified**:

- `kitty-specs/vikunja-g7-query-filter-fix-01KS1K1Y/research.md` (if D3 needs updating; otherwise no change)

**Validation**:

- [ ] `reconcile_completions.py` has no `?filter=` URL construction.
- [ ] research.md D3 reflects the audit outcome.

---

### Subtask T005 — Append G7 entry to Verified API Gotchas

**Purpose**: Document G7 in the canonical Vikunja-quirks appendix so future helpers and reviewers consult it before constructing server-side filters.

**Steps**:

1. Open `docs/design/research/vikunja-task-model-research.md`.
2. Locate the Verified API Gotchas appendix (search for "G1" or "G6").
3. Append a G7 entry using the format specified in `kitty-specs/vikunja-g7-query-filter-fix-01KS1K1Y/research.md` D5:
   - Section heading: `### G7 — Compound server-side filter due_date <= <iso> AND done = false rejected`
   - **Status**: Verified 2026-05-20
   - **Symptom**: HTTP 400 + body excerpt
   - **Failing URL**: URL-decoded GET /api/v1/projects/13/tasks?filter=…
   - **Surfacing context**: Phase 5 cutover smoke-test (#308), session log path, cron run ID + timestamp
   - **Workaround**: drop the filter, enumerate + client-side filter (mirror G6 #333 pattern)
   - **Affected helpers**: `scripts/habits/query_active_habits_v2.py` (fixed in #336)
   - **Related**: G6 (`is_archived` field rejection — same class of bug)
4. Match the visual format of the existing G1-G6 entries (heading depth, bullet structure, code block syntax).

**Files modified**:

- `docs/design/research/vikunja-task-model-research.md`

**Validation**:

- [ ] `grep -F "G7 — Compound server-side filter" docs/design/research/vikunja-task-model-research.md` returns 1 line.
- [ ] G7 entry references #336 and G6/#333.
- [ ] Date `2026-05-20` is present.

---

### Subtask T006 — Validation: run pytest + commit

**Purpose**: Confirm the full habits test suite passes and commit.

**Steps**:

1. Run the full habits test suite:
   ```bash
   pytest tests/habits/ -v --tb=short
   ```
   Expected: 319 tests passing (314 baseline + 5 new from T003). If any existing test breaks, investigate before committing.
2. Optionally run coverage:
   ```bash
   pytest tests/habits/test_query_active_habits_v2*.py --cov=scripts.habits.query_active_habits_v2
   ```
   Expected: ≥ 85% coverage for `query_active_habits_v2.py` (NFR-003).
3. Stage and commit:
   ```bash
   git add scripts/habits/query_active_habits_v2.py \
           tests/habits/test_query_active_habits_v2_filter.py \
           docs/design/research/vikunja-task-model-research.md \
           kitty-specs/vikunja-g7-query-filter-fix-01KS1K1Y/research.md
   git commit -m "fix(WP01): drop server-side filter in query_active_habits_v2; client-side equivalent + G7 docs + test"
   ```
4. Mark subtasks done:
   ```bash
   spec-kitty agent tasks mark-status T001 T002 T003 T004 T005 T006 --status done --mission vikunja-g7-query-filter-fix-01KS1K1Y
   ```
5. Move WP01 to for_review:
   ```bash
   spec-kitty agent tasks move-task WP01 --to for_review --mission vikunja-g7-query-filter-fix-01KS1K1Y --note "G7 fix ready: server-side filter dropped; client-side filter mirrors reconcile pattern; 5 new tests passing; G7 documented in Verified API Gotchas; reconcile audit clean."
   ```

**Files modified**:

- None (validation + commit subtask).

**Validation**:

- [ ] `pytest tests/habits/` exits 0 with 319+ tests passing.
- [ ] Commit landed; WP01 moved to for_review.

---

## Branch Strategy

- **Planning branch**: main
- **Final merge target**: main
- **Execution worktree**: allocated by `finalize_tasks` per `lanes.json`. The implementing agent enters the worktree printed by `spec-kitty agent action implement WP01 --agent <name>`.

---

## Definition of Done

- All 6 subtasks completed and committed.
- `pytest tests/habits/` exits 0 with at least 319 tests passing.
- `scripts/habits/query_active_habits_v2.py` HTTP URL has no `?filter=` query param.
- `_build_filter_expression` function removed.
- G7 entry present in Verified API Gotchas.
- Reconcile audit outcome reflected in research.md D3 (or D3 unchanged if it already documents the outcome correctly).
- WP01 moved to for_review.

---

## Risks

- **Risk**: The `_http_get` private function may have a different signature than expected. Mocking it may require a different patch path (e.g., the urllib.request URL opener rather than a wrapper).
  **Mitigation**: read the actual imports and helper names in the file before writing tests.

- **Risk**: Vikunja v0.24.6 may have additional pagination semantics for `/projects/13/tasks` without a filter — e.g., the response might be paginated and the full list might require multiple HTTP calls.
  **Mitigation**: check existing call sites in `reconcile_completions.py` — that helper already enumerates the same endpoint and presumably handles pagination correctly. Mirror its approach.

- **Risk**: Removing `_build_filter_expression` and the `urllib.parse` import might break something unexpected (e.g., if the file imports `urllib.parse` for other reasons that aren't obvious).
  **Mitigation**: run the full habits test suite after the removal; if anything breaks, revert the import removal and document why.

---

## Reviewer Guidance

A reviewer should verify:

1. **HTTP URL has no `?filter=` parameter** in `query_active_habits_v2.py`.
2. **Client-side filter logic is correct**:
   - Excludes `done=true` tasks.
   - Includes `due_date <= today + 23:59:59Z` (lex string compare).
   - Excludes empty-string `due_date` (no due date).
   - Includes `"0001-01-01T00:00:00Z"` (Vikunja unset-sentinel; lex-compares less than today).
3. **`_build_filter_expression` is removed entirely**, not just commented out.
4. **5 new tests pass and exercise the new code path** (not just import the module).
5. **G7 entry in vikunja-task-model-research.md** matches the format of G1-G6.
6. **Reconcile audit documented** in research.md (whether or not reconcile changed).
7. **No scope creep**: only the four owned files are modified. PAUSED-label handling is NOT added (out of scope per spec C-001).
8. **`git diff --stat` clean**: only the owned files appear.

## Activity Log

- 2026-05-20T02:30:40Z – claude:sonnet:implementer:implementer – shell_pid=23869 – Assigned agent via action command
- 2026-05-20T02:36:57Z – claude:sonnet:implementer:implementer – shell_pid=23869 – G7 fix ready: server-side filter dropped; client-side filter mirrors reconcile G6 pattern; 5 new tests in test_query_active_habits_v2_filter.py + 5 existing URL-shape assertions updated in test_query_active_habits_v2.py (scope expansion outside owned_files — flagged for reviewer); 320 tests passing (314 baseline + 5 new + 1 net); G7 documented in Verified API Gotchas appendix; reconcile_completions.py audit clean (already uses GET /projects/<id>/tasks with client-side filter); 90% coverage on modified module.
- 2026-05-20T02:37:30Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=25272 – Started review via action command
