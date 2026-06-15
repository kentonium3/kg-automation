# Phase 0 Research: Trustworthy weekly habit report

## R-01 — openclaw cron primitive: TZ handling for the new Monday 06:00 ET schedule

**Decision**: Express the new cron as `0 6 * * 1` with explicit `TZ=America/New_York` declared in the deploy manifest. The openclaw cron primitive (per `scripts/deploy/lib/`) supports per-job timezone declaration; office2 system time is UTC but Felix scheduling consistently uses America/New_York wall-clock semantics.

**Rationale**: All Kent-facing Felix cadences (morning checkin at 07:05 ET, inbox processor cadence, prior weekly tick at Sunday 22:00 ET) declare ET. Using ET here keeps the model consistent for the operator. UTC-expression (`0 10 * * 1`) would silently drift across DST transitions.

**Alternatives considered**:
- *UTC cron*: rejected — DST drift would silently move the message by an hour twice a year and break operator expectations.
- *System cron*: rejected per kg-automation CLAUDE.md "OpenClaw cron management (OpenClaw only — never system crontab)" rule.

**Verification**: IC-05 deploy manifest must include `tz: America/New_York` (or equivalent — confirm primitive's exact field name during WP scoping). Post-deploy `openclaw cron list` must show the cron at `0 6 * * 1` with the correct TZ.

---

## R-02 — WeeklyHabitReport JSON schema: additive `rendered_text` field vs schema version bump

**Decision**: Add `rendered_text` as a top-level OPTIONAL string field in the WeeklyHabitReport JSON. No schema-version bump. The existing per-habit + overall structure stays intact; consumers that ignore the new field continue to work.

**Rationale**: The existing contract (`kitty-specs/vikunja-client-and-habits-weekly-report-01KTKSFT/contracts/weekly_report_payload.md`) does not declare a strict-schema-with-version field. Adding optional fields is the documented backward-compatible extension path. Schema-version bump would force any downstream consumer (currently only felix-admin-habits agent, but conceivable future tooling) to handle a v1/v2 split for no real benefit.

**Alternatives considered**:
- *Separate render helper invoked after query helper*: rejected — extra subprocess invocation, more failure modes, no real benefit since the same JSON is the input. The agent flow becomes: invoke query → JSON parse → render → invoke render → send. Single-invocation flow is simpler and the rendering is a pure function of the JSON.
- *Schema version bump to v2*: rejected — no breaking change here. Optional additive field doesn't justify version churn.

**Verification**: IC-02 unit tests assert (a) existing fields byte-stable for same fixture state (NFR-001 + NFR-005), (b) `rendered_text` present and matches expected template output for given fixture state (NFR-004).

---

## R-03 — Architectural-test allowlist mechanism: file-level allowlist vs in-code markers

**Decision**: File-level allowlist hard-coded into `tests/architectural/test_habits_history_canonical_read.py` as a Python set of filenames. Any habits script that legitimately needs `VikunjaClient` (current-state queries) must be added to the set in the same change, with a one-line comment naming the reason. The test scans `scripts/habits/*.py` ASTs; any non-allowlisted file that imports `VikunjaClient` fails the test with file:line of the offending import.

**Rationale**: File-level allowlist is the simplest mechanism that surfaces every legitimate exception in code review. Marker-based approaches (e.g., `# arch-ok: vikunja-current-state-only` near imports) work but spread the allowlist across many files, making it harder to audit who's currently importing what. The set-in-test-file pattern matches the existing `tests/architectural/test_guard_capability_call_sites.py` convention used upstream in spec-kitty.

**Alternatives considered**:
- *Inline marker comments at each import site*: rejected — harder to grep "who is allowed to import VikunjaClient" because the answer is spread across many files.
- *Splitting `vikunja_client.py` into `vikunja_current_state.py` + (no completion-history module — those go through `state_log`)*: rejected — bigger refactor; the architectural test enforces the policy without renaming the existing module.

**Verification**: IC-03 test has two components: (1) the actual scan, which fails on offending non-allowlisted imports, and (2) a self-test fixture that intentionally adds VikunjaClient to a sample non-allowlisted file path and asserts the scan reports a violation with file:line.

---

## R-04 — Habits-domain wrapper API surface

**Decision**: Start with three operations in `scripts/habits/history.py`:

```python
def completion_events_in_window(
    start: datetime,  # tz-aware
    end: datetime,    # tz-aware, exclusive
    habit_id: int | None = None,
) -> list[HabitCompletionRecord]: ...

def completion_rate_for_habit(
    habit_id: int,
    window_start: datetime,
    window_end: datetime,
    scheduled_days_count: int,
) -> float: ...  # 0.0 to 1.0

def scheduled_vs_completed_for_habit(
    habit_id: int,
    window_start: datetime,
    window_end: datetime,
    scheduled_days_count: int,
) -> tuple[int, int]: ...  # (scheduled, completed)
```

Add more operations only when an actual caller needs them. Keep `scripts/common/state_log.py` generic; `scripts/habits/history.py` owns habit-shaped semantics.

**Rationale**: The weekly helper (IC-02) needs window-bounded events + per-habit rate. The future trend-analysis epic (#605-future / aligned with #281) will need at minimum these same three operations and possibly per-habit trend over a longer window — but speculating now is YAGNI. Three operations cleanly serves IC-02 with all the math the helper used to do inline.

**Alternatives considered**:
- *Single `query(filter)` operation with a generic filter object*: rejected — too generic, no semantic value over `state_log.read("habits", ...)` directly.
- *Six operations covering trend analysis upfront (current/prior/year-over-year/by-day-of-week/etc.)*: rejected as YAGNI — those land when the trend epic spec-kitty mission specifies them.

**Verification**: IC-01 unit tests cover each operation with golden-week fixtures. SC-005 validates a caller can use the wrapper without parsing raw JSONL.

---

## R-05 — Existing AGENTS.md weekly-tick section: lines to remove vs keep

**Decision**: Keep the agent's role description ("agent invokes helper → posts text"), the contract-failure render path ("Weekly report unavailable: ..."), and the cron-tick metadata reference. Remove any in-prompt template, percentage-formatting rules, or trend-arrow logic. The helper's `rendered_text` is the source of truth; the agent posts it verbatim.

**Rationale**: AGENTS.md should describe what the agent *does* operationally (invoke → post → identity line) and what to do on failure. Implementation details of the rendered message are now in helper code where they're testable.

**Affected lines** (per the grep done during planning): around lines 117-161 of the current AGENTS.md (the "Weekly report (tick workflow)" section). Concrete edit list will land in IC-04's WP prompt.

**Alternatives considered**:
- *Leave the agent prompt unchanged*: rejected — defeats FR-005 and leaves Haiku as a number-rendering hazard.
- *Delete the entire weekly section*: rejected — the agent still has an operational role (invocation, identity, failure path).

**Verification**: Post-IC-04, AGENTS.md weekly section is shorter and contains no template or percentage-format rules. Existing output discipline (no preamble, no between-tool-calls narration) preserved.

---

## R-06 — felix-admin-habits AGENTS.md mentions the prior cron at line 119 (`0 22 * * 0`)

**Decision**: Update both lines that reference the schedule (the bullet "Sunday 22:00 ET cron" near line 76 and the workflow section header near line 119) to `0 6 * * 1 America/New_York` (Monday 06:00 ET). Treat the AGENTS.md text and the deploy manifest as parallel sources that MUST agree.

**Rationale**: AGENTS.md is operator documentation for the agent; a drift between AGENTS.md and the real cron is exactly the silent-incoherence pattern Directive 6 prevents. IC-04 and IC-05 must coordinate.

**Verification**: Post-merge, `grep -E '(22:00|0 22 |06:00|0 6 )' scripts/openclaw/agents/felix-admin-habits/AGENTS.md` shows only references to the new schedule.

---

## R-07 — Vikunja `done_at` field after recurrence: confirmed behavior

**Decision**: Confirmed via the existing helper's code and Vikunja's `repeat_after` model: when a recurring task is marked `done=true`, Vikunja advances `due_date` and (per the post-PATCH state) sets a fresh `done_at` for the completion, then the next-day re-arm resets `done` to false. The `done_at` field thus reflects the MOST RECENT completion only — there is no Vikunja API path that returns the historical completion log for a recurring task.

**Rationale**: This is the root cause of the bug. The `[Felix]` comments on each task ARE the Vikunja-side historical log, but they're free-text strings, not structured. The canonical structured equivalent lives in `habits-history.jsonl`. Reading the JSONL is correct.

**Alternatives considered**:
- *Parse Vikunja comments for history*: rejected — `backfill_jsonl_from_comments.py` already does this for the one-time historical-backfill use case (#308 cutover). Doing it every weekly tick is slower, fragile, and re-derives semantics the JSONL already encodes.
- *Query Vikunja `tasks/<id>/audit` or similar*: confirmed not to exist in the Vikunja API for recurring-task completion history.

**Verification**: IC-02 unit tests use the golden-week JSONL fixture; no Vikunja mocking required for completion-history paths.

---

## Open items deferred to WP authoring

The above resolve every research item that has a confident answer. The following remain as WP-authoring micro-decisions (no Kent-input required):

- Exact name of the openclaw cron primitive's TZ field (will discover at IC-05 WP authoring by reading `scripts/deploy/lib/` cron helpers).
- Exact `WeeklyHabitReport` rendered-text template wording — will preserve the existing message format from the current production output (the format already exists in the agent prompt; the helper inherits it byte-stable, just relocated).
- Whether to expose `rendered_text` as a top-level field OR as a nested `rendering.text` sub-object — leaning top-level for simplicity; decided at WP authoring.
