---
work_package_id: WP02
title: Weekly helper rewrite (canonical-read + rendering)
dependencies:
- WP01
requirement_refs:
- FR-002
- FR-005
- FR-006
- FR-007
- FR-008
- FR-009
- FR-010
- NFR-001
- NFR-004
- NFR-005
tracker_refs: []
planning_base_branch: main
merge_target_branch: main
branch_strategy: lane-from-coord
subtasks:
- T006
- T007
- T008
- T009
- T010
- T011
agent: claude
history:
- at: '2026-06-15T02:33:00Z'
  actor: spec-kitty agent mission tasks
  event: WP created from /spec-kitty.tasks
agent_profile: implementer-ivan
authoritative_surface: scripts/habits/query_active_habits_weekly.py
create_intent: []
execution_mode: code_change
owned_files:
- scripts/habits/query_active_habits_weekly.py
- tests/habits/test_query_active_habits_weekly.py
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Before reading anything else in this prompt, load your assigned agent profile via `/ad-hoc-profile-load implementer-ivan` (or the equivalent profile loader in your harness). The profile carries the identity, governance scope, and boundaries you operate under during this WP.

## Objective

Rewrite `scripts/habits/query_active_habits_weekly.py` so it reads completion history from the canonical `habits-history.jsonl` (via the WP01 wrapper) instead of Vikunja `done_at`, moves WhatsApp message rendering into the helper (no LLM in the data path), and fixes the 7-day window label. The helper's stdout becomes the single source of truth for the weekly report: same JSONL state + same Vikunja current-state response + same `--as-of` argument → byte-identical JSON output AND byte-identical `rendered_text`.

## Context

This is the bug-fix payload for [issue #605](https://github.com/kentonium3/kg-automation/issues/605). Symptom: daily habits report 0% completion in the WhatsApp weekly summary even when completed multiple times during the week. Root cause: the current helper reads Vikunja's `done_at` field — a single timestamp per task that gets reset on each `repeat_after` recurrence cycle — so daily habits' completion history is effectively unreadable from Vikunja.

The Vikunja side still has data the helper needs: habit titles and `repeat_after` classification (current-state). The helper retains exactly that one call to `VikunjaClient.get_tasks(...)` and discards everything related to historical completion reading.

Read before starting:

- `kitty-specs/trustworthy-weekly-habit-report-01KV4GZ7/spec.md`
- `kitty-specs/trustworthy-weekly-habit-report-01KV4GZ7/plan.md` (IC-02)
- `kitty-specs/trustworthy-weekly-habit-report-01KV4GZ7/contracts/weekly_helper_cli.md` (the CLI + JSON contract you implement)
- `kitty-specs/trustworthy-weekly-habit-report-01KV4GZ7/research.md` (especially R-02 rendered_text schema decision and R-05 / R-06 AGENTS.md cross-references)
- `scripts/habits/history.py` (the WP01 wrapper you call into)
- `scripts/habits/query_active_habits_weekly.py` (the current implementation — read end-to-end before editing)
- The existing WeeklyHabitReport contract at `kitty-specs/vikunja-client-and-habits-weekly-report-01KTKSFT/contracts/weekly_report_payload.md`

## Subtasks

### T006 — Remove the `done_at` completion-history path

Delete these from `query_active_habits_weekly.py`:

- `_parse_done_at` (only used by the broken path)
- The `task.get("done_at")` reads inside `query_completion_events`
- Any window-membership check based on a single `done_at` timestamp per task
- The warning emitted when `done_at` is None ("skipping done task without parseable done_at")

Keep the surrounding scaffolding (argparse, `parse_weekday_in_title`, `classify_habit`, `scheduled_days_for_window`, `build_report`, `main`) — those are the parts that survive.

### T007 — Switch to the canonical store via the WP01 wrapper

Replace the body of `query_completion_events` (the function the helper calls to get per-habit completion counts for the current and prior windows) with calls to `scripts.habits.history`:

```python
from scripts.habits import history

# For each task in the habits list:
current_scheduled, current_completed = history.scheduled_vs_completed_for_habit(
    habit_id=task["id"],
    window_start=window_start,
    window_end=window_end,
    scheduled_days_count=current_scheduled_days,
)
prior_scheduled, prior_completed = history.scheduled_vs_completed_for_habit(
    habit_id=task["id"],
    window_start=prior_window_start,
    window_end=prior_window_end,
    scheduled_days_count=prior_scheduled_days,
)
```

Use the `scheduled_vs_completed_for_habit` form (not `completion_rate_for_habit`) so the JSON output can include both raw counts AND percentage if a future renderer wants to display "4 of 7" instead of "57%".

**Imports to retain**:
```python
from scripts.common.vikunja_client import VikunjaClient, VikunjaError
```
This stays for the current-state habit-list call (`VikunjaClient.get_tasks(project_id=HABITS_PROJECT_ID, ...)`) — titles + `repeat_after`. The architectural test (WP03) will allowlist `query_active_habits_weekly.py` for this reason.

**New import**:
```python
from scripts.habits import history
```

### T008 — Add `--as-of` CLI flag

Add to the argparse setup:

```python
parser.add_argument(
    "--as-of",
    type=_parse_iso_datetime,  # tz-aware
    default=None,
    help=(
        "Reference datetime (ISO 8601, tz-aware) for the report window. "
        "Defaults to current wall clock in America/New_York. Used by tests "
        "for deterministic golden-week fixtures."
    ),
)
```

Helper `_parse_iso_datetime` converts the string into a tz-aware `datetime`. If user passes a naive datetime, raise `argparse.ArgumentTypeError`.

Use `args.as_of or _now_in_et()` at the top of the report-building flow. `_now_in_et()` is a thin wrapper that returns `datetime.now(ZoneInfo("America/New_York"))` — keep this function tiny so it's easy to monkeypatch in tests if needed.

### T009 — Implement `rendered_text` generation

Add a pure function:

```python
def _render_whatsapp_text(report: dict) -> str:
    """Render the WeeklyHabitReport JSON to the canonical WhatsApp message.

    Same input → byte-identical output (NFR-004).
    Template per kitty-specs/trustworthy-weekly-habit-report-01KV4GZ7/contracts/weekly_helper_cli.md.
    """
```

Template structure (preserves the existing production message format Kent sees):

```
*This week* ({short_window}):

{habit_title} — {pct}% (was {prior_pct}%) {arrow}
...

*Overall: {overall_pct}%* (was {prior_overall_pct}%) {overall_arrow}
```

Implementation rules:
- `{short_window}` per T010's `_format_window_label`.
- `{pct}` is `round(current_pct * 100)` with no decimals.
- `{arrow}` is `↑` if `current_pct > prior_pct + 0.005`, `↓` if `current_pct < prior_pct - 0.005`, empty string (no arrow) otherwise. The `0.005` epsilon prevents arrow flicker on essentially-equal rates.
- Habits are listed in the same order the existing helper produces (alphabetical by title or by classification — verify by reading existing code; preserve the order to keep diffs reviewable).
- Include the `rendered_text` as a top-level field in `build_report`'s output dict:

```python
def build_report(...) -> dict:
    report = {
        "report_date": ...,
        "window_start": ...,
        "window_end": ...,
        "per_habit": ...,
        "overall": ...,
    }
    report["rendered_text"] = _render_whatsapp_text(report)
    return report
```

### T010 — Fix the 7-day window label

Implement `_format_window_label(window_start: datetime, window_end: datetime) -> str` returning a clean 7-day label.

Examples (window_end is INCLUSIVE for label purposes; the math windows are start-inclusive / end-exclusive elsewhere):

- `_format_window_label(Mon Jun 8, Sun Jun 14)` → `"Jun 8–14"` (same month, range)
- `_format_window_label(Mon Jul 28, Sun Aug 3)` → `"Jul 28 – Aug 3"` (cross-month, en-dash with spaces)

Implementation:

```python
def _format_window_label(window_start: datetime, window_end: datetime) -> str:
    """Format a 7-day inclusive window label for the report."""
    if window_start.month == window_end.month:
        return f"{window_start.strftime('%b')} {window_start.day}–{window_end.day}"
    return f"{window_start.strftime('%b %-d')} – {window_end.strftime('%b %-d')}"
```

The existing helper was generating "Jun 7–14" — an 8-day span (Sun-to-Sun inclusive). Make sure the new function and the new windowing convention together produce a 7-day inclusive span (Mon-to-Sun) per the spec's Primary scenario.

### T011 — Update tests + add golden-week behavior tests

File: `tests/habits/test_query_active_habits_weekly.py` (UPDATE existing).

Read the existing tests first — much of the existing test infrastructure (stubbing `VikunjaClient.get_tasks`, etc.) should be reusable.

Add or update:

1. **Byte-stable JSON output**: With the golden-week fixture from WP01 + a stubbed Vikunja response, assert `--output json` produces byte-identical stdout across two runs.

2. **Byte-stable `rendered_text`**: Same fixture, assert `--output text` produces byte-identical stdout. Use a known-string assertion against the expected template output.

3. **Per-habit rates correct for daily pattern**: Daily habit `habit_id=100` completed 4 of 7 days in golden-week fixture → reports `current_pct=4/7` (assert with `pytest.approx`).

4. **Per-habit rates correct for day-specific pattern**: Habit `habit_id=200` (Strength Mon) completed Monday → reports `current_pct=1.0`. Same habit completed Monday → reports `current_pct=1.0`.

5. **Sunday late completion captured**: With `--as-of "2026-06-15T06:00:00-04:00"` (Monday 06:00 ET) and golden-week fixture, a Sunday completion appears in the current window's count.

6. **`done_at` is NOT read**: Construct a stubbed Vikunja response where `done_at` is intentionally garbage (e.g., a year-old timestamp); assert the report still shows correct completion counts from the JSONL fixture. This is the regression test that prevents reverting to the broken path.

7. **Window label correct**: Assert `_format_window_label(monday, sunday)` produces `"Jun 8–14"` (NOT `"Jun 8 – Jun 14"` for same-month, NOT `"Jun 7–14"`).

8. **Window label cross-month**: Assert `_format_window_label(Jul 28, Aug 3)` produces `"Jul 28 – Aug 3"`.

## Branch strategy

- Planning base branch: `main`
- Merge target branch: `main`
- This WP lands on its computed lane worktree (allocated by `finalize-tasks`).
- Depends on WP01 — your lane's base will include WP01's commits.

## Test strategy

Tests are mandatory per the spec's FR-008 + NFR-001 + NFR-004 + SC-004. Use `pytest tests/habits/test_query_active_habits_weekly.py -v`.

Stub `VikunjaClient.get_tasks(...)` for current-state info — use the existing test pattern (likely a `conftest.py` fixture or a `monkeypatch` setter). DO NOT make real Vikunja calls.

The JSONL state comes from `tests/habits/fixtures/golden_week_jsonl.py` (WP01).

## Definition of Done

- [ ] `scripts/habits/query_active_habits_weekly.py` no longer reads `task.get("done_at")` anywhere.
- [ ] `scripts/habits/query_active_habits_weekly.py` imports `scripts.habits.history` and uses `scheduled_vs_completed_for_habit`.
- [ ] CLI accepts `--as-of` flag with tz-aware datetime parsing.
- [ ] Helper output JSON includes the top-level `rendered_text` field.
- [ ] `rendered_text` matches the canonical template, byte-stable for same inputs.
- [ ] `_format_window_label` produces 7-day inclusive labels (`"Jun 8–14"` for same-month).
- [ ] All tests in `tests/habits/test_query_active_habits_weekly.py` pass on first run, including the new golden-week tests.
- [ ] Module docstring updated to reflect the canonical-read pivot (reference `habits-history.jsonl` and mission slug).
- [ ] `_parse_done_at` and other dead code removed.
- [ ] No `datetime.now()` calls inside `build_report` or its callees — all time references trace to `args.as_of` or `_now_in_et()`.
- [ ] The architectural test in WP03 keeps this file on the allowlist (current-state Vikunja access is allowed; completion history is not).

## Risks

- **Backward-compat regression**: NFR-005 requires the JSON schema to stay backward-compatible. Adding `rendered_text` is additive, but verify that the existing per_habit array structure is preserved byte-for-byte (use a snapshot test if available).
- **DST boundary in `_now_in_et`**: spring/fall DST shifts can produce 23- or 25-hour days. The golden-week fixture should be inside a no-DST week to avoid having to assert against DST math; production behavior is correct because `zoneinfo` handles DST natively.
- **Habit list filtering**: the existing helper filters for habits with `repeat_after > 0` (recurring) vs others. Preserve that filter; the wrapper change is purely about WHERE completion history comes from, not WHICH habits get reported on.
- **Tests touching production JSONL**: ensure pytest fixtures route `state_log.STATE_DIR` to a temp dir so tests can't read or mutate the real office2 file. Use the existing `mock_state_log_dir` fixture if it exists (it does, per the test inventory).
- **Identity line preservation**: FR-010 — the helper produces the message body but the agent prepends the `Sent by felix-admin-habits:<model>` identity line. Don't render the identity inside `rendered_text`; that's the agent's responsibility.

## Reviewer guidance

Reviewers verify:

1. The helper no longer calls anything `done_at`-shaped. Grep for `done_at` should return zero hits in the file.
2. The helper still calls `VikunjaClient.get_tasks(...)` for current-state info. This is intentional and required.
3. `rendered_text` is generated deterministically and matches the template.
4. The 7-day window label is correct (one-letter "Jun" abbreviation, en-dash for same-month, en-dash-with-spaces for cross-month).
5. Tests cover the regression case (garbage `done_at` doesn't affect output).
6. The architectural test (WP03) doesn't flag this file when run.

If the reviewer finds the JSON schema accidentally widened beyond the additive `rendered_text` field, request a revision.

## Implementation command

```bash
spec-kitty agent action implement WP02 --agent claude
```
