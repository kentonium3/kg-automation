# Implementation Plan: Fix Vikunja G7 query filter for habits v2

**Mission**: `vikunja-g7-query-filter-fix-01KS1K1Y`
**Mission ID**: `01KS1K1YE6H1CTY29A6MRWW836`
**Branch**: main (planning + merge target; matches current)
**Date**: 2026-05-19 (UTC 2026-05-20)
**Spec**: [spec.md](spec.md) · **Source issue**: [#336](https://github.com/kentonium3/kg-automation/issues/336) · **Related**: [#333 G6 fix](https://github.com/kentonium3/kg-automation/issues/333)

## Summary

Single helper bug fix. `scripts/habits/query_active_habits_v2.py` sends a server-side filter expression to Vikunja that v0.24.6 rejects with HTTP 400. The fix: drop the `?filter=` query param, fetch the full project task list, apply the equivalent `done == false AND due_date <= today` filter in Python. Mirror the pattern already used in `reconcile_completions.py` (the G6 #333 fix).

Also: append a G7 entry to `docs/design/research/vikunja-task-model-research.md` and add a test exercising the client-side filter logic.

## Technical Context

**Language/Version**: Python 3 (stdlib only — `urllib` for HTTP, no new dependencies).
**Primary Dependencies**: None new. Same dependencies as Phase 3 baseline.
**Storage**: N/A (this helper is read-only against Vikunja; no JSONL writes).
**Testing**: pytest-based; existing 314 habits tests must continue to pass. One new test added under `tests/habits/`.
**Target Platform**: office2 (Ubuntu 24.04 LTS) — same deploy target as Phase 3. The helper is exercised by the morning-checkin cron via the felix-admin-habits agent.
**Project Type**: Single-file Python helper change + docs + tests.
**Performance Goals**: < 2s wall clock (NFR-001). Vikunja Habits project has ~15-30 tasks; client-side filter cost is negligible.
**Constraints**: C-001 (G7 fix only, no scope creep); C-002 (exit codes preserved); C-003 (reconcile audit documented); C-005 (operator deploys via scp/rsync).
**Scale/Scope**: One `.py` file edit (~30-50 lines diff), one docs append (~10 lines), one test file (~50 lines).

## Charter Check

Charter context: compact mode, no enforced directives or tactics. **No gate violations.**

## Project Structure

### Documentation (this feature)

```
kitty-specs/vikunja-g7-query-filter-fix-01KS1K1Y/
├── plan.md              # This file
├── spec.md              # Mission specification
├── research.md          # Phase 0 — tactical decisions + reconcile audit outcome
├── data-model.md        # Phase 1 — code surface map (before/after)
├── quickstart.md        # Phase 1 — operator deploy walkthrough
└── tasks/               # Phase 2 — work packages (NOT created here)
```

### Source Code (repository root)

```
scripts/habits/
└── query_active_habits_v2.py           # MODIFIED — primary deliverable

scripts/habits/reconcile_completions.py # AUDITED — no change expected (already client-side)

docs/design/research/
└── vikunja-task-model-research.md      # MODIFIED — append G7 to Verified API Gotchas

tests/habits/
└── test_query_active_habits_v2_filter.py  # NEW — exercises client-side filter logic
```

**Structure Decision**: One Python file change (~30 lines), one docs append, one new test file. No new directories, no new modules.

## Complexity Tracking

No charter check violations. No scope-expansion temptations (PAUSED handling explicitly out of scope per C-001 — see Spec FR-003 note).

---

## Plan

Both phases (research + design) execute in this single pass. Mission is small enough that the design artifacts can be lean.

### Phase 0 — Research artifacts

See [research.md](research.md). Three tactical decisions documented:

1. **D1 — Where to perform the client-side filter**: in `query_active_today()` immediately after the HTTP response is parsed, before the function returns. Mirrors the pattern from `reconcile_completions.py`. Alternative (filtering in `main()` after `query_active_today` returns) rejected — keeps the public function's contract narrow ("returns active-today habits") rather than leaking the filter responsibility to callers.

2. **D2 — Disposition of `_build_filter_expression()`**: REMOVE the function entirely. It's only used by `query_active_today()` and is no longer needed. Removing it avoids dead-code that would tempt future callers to use the rejected filter pattern. (Alternative — keep for tests — rejected because no callers + no tests depend on it; verified by grep.)

3. **D3 — Reconcile audit outcome**: `reconcile_completions.py` lines 188-193 explicitly document the `is_archived` client-side filter workaround. The smoke-test session log confirms reconcile worked correctly during Phase 5 cutover. **No code change to reconcile_completions.py.** Audit outcome: pass.

### Phase 1 — Design artifacts

- [data-model.md](data-model.md) — BEFORE/AFTER map for `query_active_today()` and `_build_filter_expression()`. No data model changes (no schema, no JSONL).
- [quickstart.md](quickstart.md) — operator walkthrough: pull main, deploy `.py` via scp, verify with manual invocation.

### Charter re-check (post-design)

Same outcome — no constraints. Pass.

---

## Branch contract (restated)

- **Current branch at plan start**: `main`
- **Planning/base branch**: `main`
- **Final merge target**: `main`
- **branch_matches_target**: `true`

Completed changes from this mission merge into `main`. The operator then deploys the updated `.py` to office2 via scp/rsync.

---

## Stop

Planning artifacts complete. Next: `/spec-kitty.tasks` to break the plan into work packages.
