---
work_package_id: WP01
title: Habits-domain query wrapper
dependencies: []
requirement_refs:
- FR-002
- FR-003
- FR-007
- FR-008
- NFR-001
- NFR-005
tracker_refs: []
planning_base_branch: main
merge_target_branch: main
branch_strategy: lane-from-coord
subtasks:
- T001
- T002
- T003
- T004
- T005
agent: claude
history:
- at: '2026-06-15T02:33:00Z'
  actor: spec-kitty agent mission tasks
  event: WP created from /spec-kitty.tasks
agent_profile: implementer-ivan
authoritative_surface: scripts/habits/history.py
create_intent: []
execution_mode: code_change
owned_files:
- scripts/habits/history.py
- tests/habits/test_history.py
- tests/habits/fixtures/golden_week_jsonl.py
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Before reading anything else in this prompt, load your assigned agent profile via `/ad-hoc-profile-load implementer-ivan` (or the equivalent profile loader in your harness). The profile carries the identity, governance scope, and boundaries you operate under during this WP. Treat the profile as authoritative for tone, escalation rules, and Op lifecycle.

## Objective

Create `scripts/habits/history.py` — the canonical habits-domain read API that exposes window-bounded completion-event queries on top of generic `scripts/common/state_log.py`. This module becomes the single read path for any caller that consumes habit completion history: the weekly helper (WP02), future trend-analysis tooling (post-#605 epic), and any ad-hoc analysis. Nobody else parses raw `habits-history.jsonl` after this lands.

## Context

The bug captured in [issue #605](https://github.com/kentonium3/kg-automation/issues/605) is that `scripts/habits/query_active_habits_weekly.py` reads Vikunja's `done_at` field — a single per-task timestamp that gets reset on each daily-recurrence cycle — instead of the canonical append-only `habits-history.jsonl` on office2. The Felix Constitution Directive 6 fix is to push the read path into a helper. This WP creates that helper.

Read these before starting:

- `kitty-specs/trustworthy-weekly-habit-report-01KV4GZ7/spec.md`
- `kitty-specs/trustworthy-weekly-habit-report-01KV4GZ7/plan.md` (IC-01)
- `kitty-specs/trustworthy-weekly-habit-report-01KV4GZ7/contracts/habits_history_wrapper.md` (the public contract you implement)
- `kitty-specs/trustworthy-weekly-habit-report-01KV4GZ7/data-model.md` (the entity shapes)
- `scripts/common/state_log.py` (the primitive you build on)

## Subtasks

### T001 — Create `scripts/habits/history.py`

Implement the three operations per `contracts/habits_history_wrapper.md`:

```python
def completion_events_in_window(
    start: datetime,
    end: datetime,
    habit_id: int | None = None,
) -> list[dict]: ...

def completion_rate_for_habit(
    habit_id: int,
    window_start: datetime,
    window_end: datetime,
    scheduled_days_count: int,
) -> float: ...

def scheduled_vs_completed_for_habit(
    habit_id: int,
    window_start: datetime,
    window_end: datetime,
    scheduled_days_count: int,
) -> tuple[int, int]: ...
```

**Allowed imports**: stdlib (`datetime`, `zoneinfo`, `typing`), `scripts.common.state_log`.
**Forbidden imports**: `scripts.common.vikunja_client` (any symbol from it). The architectural test in WP03 enforces this — your module will be one of the few habits scripts that is NOT on the allowlist.

**Module docstring** (mandatory): explain that this module is the canonical read API for habits completion history, why Vikunja `done_at` must not be read here (the volatility/repeat_after issue), and reference the mission slug `trustworthy-weekly-habit-report-01KV4GZ7`.

**No `datetime.now()` calls** inside the module. Callers pass tz-aware datetimes explicitly. This is for determinism (NFR-001) and DST-safe testing.

**Validation**:
- `start.tzinfo is None` or `end.tzinfo is None` → raise `ValueError("start/end must be tz-aware")`.
- `end <= start` → raise `ValueError("end must be > start")`.
- `scheduled_days_count <= 0` → raise `ValueError(...)`.

**File**: `scripts/habits/history.py` (NEW, ~120–150 lines).

### T002 — [P] Unit tests for `completion_events_in_window`

File: `tests/habits/test_history.py` (NEW).

Cases (use the golden-week fixture from T005):
1. Empty JSONL → returns `[]`.
2. `habit_id=None` returns all events in window.
3. `habit_id=123` filters to that task's events only.
4. Events outside window are excluded (boundary: `start` inclusive, `end` exclusive).
5. Stable ordering: `(date, timestamp)` ascending. Construct out-of-order JSONL fixture and assert output is sorted.
6. `start.tzinfo is None` → `ValueError`.
7. `end.tzinfo is None` → `ValueError`.
8. `end == start` → `ValueError` (must be strictly greater).
9. `end < start` → `ValueError`.

**Determinism check** (NFR-001): same fixture content + same args → byte-identical result across runs. Assert via `assert result == result_from_second_call`.

### T003 — [P] Unit tests for `completion_rate_for_habit`

Same file as T002.

Cases:
1. Daily habit completed 7/7 → rate `1.0`.
2. Daily habit completed 3/7 → rate `≈0.4286` (assert with `pytest.approx`).
3. Day-specific habit (e.g. Monday only) scheduled 1 day, completed 1 → rate `1.0`.
4. Day-specific habit scheduled 1 day, completed 0 → rate `0.0`.
5. Same date appearing twice in JSONL (operator dedup edge) → counted as 1 completion.
6. `scheduled_days_count=0` → `ValueError`.
7. `scheduled_days_count=-1` → `ValueError`.
8. Argument validation inherited from `completion_events_in_window` (naive datetime → `ValueError`).

### T004 — [P] Unit tests for `scheduled_vs_completed_for_habit`

Same file as T002.

Cases (mirror T003 but assert `(scheduled, completed)` tuples):
1. Daily perfect week → `(7, 7)`.
2. Daily 3-of-7 → `(7, 3)`.
3. Day-specific completed → `(1, 1)`.
4. Day-specific missed → `(1, 0)`.
5. Validation inherited.

### T005 — Golden-week fixture

File: `tests/habits/fixtures/golden_week_jsonl.py` (NEW).

Provide:

```python
def write_golden_week_jsonl(path: Path, *, week_anchor_iso: str = "2026-06-08") -> None:
    """Write a JSONL fixture representing a known week for testing.

    Covers all three scheduling patterns:
      - habit_id=100 "Daily walk" — daily, completed 4 days (Mon, Tue, Thu, Sat)
      - habit_id=200 "Strength Mon" — day-specific, completed 1 (Monday)
      - habit_id=300 "Weekly review" — week-bounded, completed 1 (Sunday)

    The week_anchor_iso defaults to a fixed date so the fixture is deterministic
    independent of wall clock.
    """
```

Plus a constant `GOLDEN_WEEK_ANCHOR = datetime(2026, 6, 8, ...)` for tests to import as the canonical reference window.

Records use the schema from `scripts/common/state_log.py` `validate_record` (i.e. the existing habits domain schema — do NOT invent fields).

## Branch strategy

- Planning base branch: `main`
- Merge target branch: `main`
- This WP lands on its computed lane worktree (lane assignment performed by `finalize-tasks` and recorded in `lanes.json`).
- `spec-kitty merge` at end-of-mission folds the lane into the mission branch and ultimately into `main`. You do NOT do any branch surgery from this WP; commit to your lane and let spec-kitty orchestrate the rest.

## Test strategy

Tests are mandatory per the spec's FR-008 + SC-004. Use `pytest tests/habits/test_history.py -v`. The golden-week fixture is the single source of fixture data; do not invent state inside individual tests beyond what the fixture provides (extend the fixture if you need a new scenario).

## Definition of Done

- [ ] `scripts/habits/history.py` exists and implements the three operations per contract.
- [ ] Module imports only stdlib + `scripts.common.state_log`. No `VikunjaClient` import.
- [ ] `tests/habits/test_history.py` covers all cases enumerated above (T002–T004).
- [ ] `tests/habits/fixtures/golden_week_jsonl.py` exists with `write_golden_week_jsonl` helper.
- [ ] `pytest tests/habits/test_history.py -v` is green on first run.
- [ ] Module docstring explains the canonical-read intent and references the mission slug.
- [ ] No `datetime.now()` / `Date.now()` / `os.getenv()` inside the module.
- [ ] `mypy scripts/habits/history.py` (if mypy is in CI) returns no new errors.

## Risks

- **Schema drift with `state_log.validate_record`**: if the habits domain JSONL schema evolves during WP01, the wrapper must match. Read `scripts/common/state_log_schema.py` `DOMAIN_STATES` for current habits states; record/exclude states accurately.
- **API surface bloat**: resist adding more operations than the three spec'd. Per `research.md` R-04, the trend-analysis epic can add operations later; YAGNI here.
- **Test isolation**: ensure tests use `tmp_path` for fixture file paths so they don't accidentally read the production `habits-history.jsonl` via `state_log.STATE_DIR`. The existing `tests/habits/conftest.py` may provide a `mock_state_log_dir` fixture — use it if present.

## Reviewer guidance

Reviewers verify:

1. The three public operations match `contracts/habits_history_wrapper.md` exactly (signature, raises, determinism).
2. No forbidden imports (grep for `VikunjaClient` in the module).
3. Tests cover the boundary cases (naive datetime, inverted window, empty JSONL, dedup-by-date).
4. The golden-week fixture is self-contained (no external file dependencies).
5. Module docstring explains the intent.

If reviewers find the API surface drifting (e.g. an extra operation tacked on), redirect to a follow-up issue rather than expanding scope here.

## Implementation command

```bash
spec-kitty agent action implement WP01 --agent claude
```
