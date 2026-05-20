# Tasks: Vikunja G7 query filter fix

**Mission**: `vikunja-g7-query-filter-fix-01KS1K1Y`
**Mission ID**: `01KS1K1YE6H1CTY29A6MRWW836`
**Branch**: main (planning + merge target)
**Date**: 2026-05-19 (UTC 2026-05-20)
**Spec**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md)

---

## Summary

Bug fix #336 / Vikunja G7 — single helper change. Drop server-side filter from `query_active_habits_v2.py`; apply equivalent filter client-side. Add test, append G7 to research doc, audit reconcile.

**Sizing**: 1 WP, 6 subtasks. Tightly coupled (one Python file + its test + a docs append + an audit). Splitting would create undersized fragments.

---

## Subtask Index

| ID | Description | WP | Parallel |
|----|-------------|----|----------|
| T001 | Refactor `query_active_today()` — drop server-side filter, fetch full project list, apply client-side filter (`done == false AND due_date <= today`) | WP01 | | [D] |
| T002 | Remove `_build_filter_expression()` function + audit `urllib.parse` import for removability | WP01 | | [D] |
| T003 | Add new test file `tests/habits/test_query_active_habits_v2_filter.py` with 5 test cases per research D4 | WP01 | | [D] |
| T004 | Audit `reconcile_completions.py` for similar filter usage; document outcome in research.md (expected: pass, no change) | WP01 | | [D] |
| T005 | Append G7 entry to `docs/design/research/vikunja-task-model-research.md` Verified API Gotchas appendix | WP01 | | [D] |
| T006 | Validation — run `pytest tests/habits/` (expect 319 passing); commit | WP01 | | [D] |

---

## WP01 — Fix G7 query filter + add test + docs

- **Prompt**: [WP01-fix-g7-query-filter.md](tasks/WP01-fix-g7-query-filter.md)
- **Goal**: Drop the server-side filter from `query_active_habits_v2.py`. Apply equivalent filter logic in Python. Add a test exercising the client-side filter. Append G7 to the Verified API Gotchas appendix. Audit reconcile.
- **Priority**: P1 (the only WP; mission-blocking)
- **Estimated prompt size**: ~400 lines
- **Independent test**: After merge + operator deploy: `python3 -m scripts.habits.query_active_habits_v2 --today $(date -u +%Y-%m-%d)` on office2 exits 0 and emits JSONL. No HTTP 400.
- **Includes**:
  - [x] T001 Refactor `query_active_today()` (WP01)
  - [x] T002 Remove `_build_filter_expression()` + audit import (WP01)
  - [x] T003 Add client-side filter tests (WP01)
  - [x] T004 Audit reconcile + document outcome (WP01)
  - [x] T005 G7 entry in Verified API Gotchas (WP01)
  - [x] T006 Validation — run pytest + commit (WP01)
- **Dependencies**: None.
- **Owned files**:
  - `scripts/habits/query_active_habits_v2.py`
  - `tests/habits/test_query_active_habits_v2_filter.py` (new file)
  - `docs/design/research/vikunja-task-model-research.md`
  - `kitty-specs/vikunja-g7-query-filter-fix-01KS1K1Y/research.md` (audit outcome append only)
- **Risks**:
  - Subtle date-boundary semantics: the `<=` boundary at `YYYY-MM-DDT23:59:59Z` MUST match what server-side `due_date <= now/d` produced. Includes tasks with `due_date == "0001-01-01T00:00:00Z"` (Vikunja "unset" sentinel) since they lex-compare less than today's boundary. Test #1 covers this.
  - `_http_get` is a private function (underscore prefix); test mocking must use the actual import path. Verify before merge.

---

## Parallelization

No parallelization — single WP, single Python file.

---

## MVP Scope Recommendation

WP01 IS the MVP. Smaller scope (e.g., skip the test, skip the docs append) would leave gaps: future agents/reviewers wouldn't have evidence of the regression, and the next time someone constructs a Vikunja filter they'd repeat the same mistake.

---

## Requirement Coverage

WP01 covers all functional requirements:

- **FR-001** (no `filter=` query param) → T001
- **FR-002** (Python-side filter logic) → T001
- **FR-003** (preserve existing filtering — no PAUSED handling added; out of scope) → T001 (by inaction)
- **FR-004** (stdout JSONL format unchanged) → T001
- **FR-005** (exit codes unchanged) → T001
- **FR-006** (reconcile audit) → T004
- **FR-007** (G7 docs append) → T005
- **FR-008** (client-side filter test) → T003

Non-functional:

- **NFR-001** (<2s runtime) → enforced by code review; not measured in tests
- **NFR-002** (314+ tests passing) → T006 validation
- **NFR-003** (≥85% coverage) → enforced by code review

---

## Next Steps

After tasks finalize, drive WP01 through the implement-review loop (Claude implementer + Codex reviewer).
