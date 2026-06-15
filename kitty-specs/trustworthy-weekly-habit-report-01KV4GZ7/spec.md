# Trustworthy Weekly Habit Report

**Mission**: `trustworthy-weekly-habit-report-01KV4GZ7`
**Mission Type**: software-dev
**Target Branch**: `main`
**Status**: spec
**Source**: GitHub issue [#605](https://github.com/kentonium3/kg-automation/issues/605)

## Purpose

**TLDR**: Fix the Sunday weekly habit report so its percentages match the canonical completion history and it arrives after the week actually ends.

**Context**: Felix's weekly habit accountability report is currently unusable. It shows 0% for habits Kent completed multiple times during the week because the helper reads Vikunja's volatile `done_at` field — a single per-task timestamp that gets reset on each daily-recurrence cycle — instead of the canonical `habits-history.jsonl` append-only log on office2. The cron also fires Sunday 22:00 ET, roughly three hours before the reporting window closes, so any Sunday-evening completions are lost.

This mission routes the weekly query through the canonical store via a new habits-domain wrapper, adds an architectural test that fails the build if any habits script reads completion history through Vikunja, moves the WhatsApp message rendering into the helper so the LLM cannot drift the numbers, and reschedules the cron to Monday 06:00 ET. Trust in this report is a prerequisite for the planned analysis-and-course-correction epic, so the investment goes into a tight ratchet now rather than patching the symptom.

---

## User Scenarios & Testing

### Primary scenario — accurate Monday-morning weekly summary

**Actor**: Kent (recipient) / felix-admin-habits agent (sender).

**Trigger**: Monday 06:00 America/New_York openclaw cron tick.

**Flow**:
1. Cron fires. felix-admin-habits invokes `scripts/habits/query_active_habits_weekly.py` (or its successor entry point).
2. Helper queries the canonical `habits-history.jsonl` for the prior 7-day window via the new habits-domain wrapper on top of `scripts/common/state_log.py`. It does NOT touch Vikunja `done_at`.
3. Helper computes per-habit completion percentages for the current 7-day window and the prior 7-day baseline window.
4. Helper renders the final WhatsApp message text from the WeeklyHabitReport JSON.
5. Agent posts the helper's rendered text verbatim to WhatsApp, preserving the `Sent by felix-admin-habits:<model>` identity line.

**Success outcome**: Kent receives a WhatsApp message Monday morning whose percentages match the completion record he kept during the week.

### Exception — helper failure

**Trigger**: The helper exits non-zero (Vikunja unavailable for the active-habits list, state_log unreadable, contract violation).

**Flow**: Agent emits the existing contract-failure message — `Weekly report unavailable: <one-line error class + stripped path>` — and stops. No retries inside the tick. No preamble. The next Monday's cron is the retry surface.

### Edge — truly empty week

**Trigger**: Kent completed nothing during the reporting window.

**Flow**: Every habit reports 0% and overall reports 0%. The report is *correct* — 0% is a true 0%, not a data-loss artifact. The architectural test and the golden-week regression test must distinguish "real 0%" from "wrong query path."

### Edge — habit added mid-window

**Trigger**: A habit is added to Vikunja project 13 part-way through the reporting window.

**Flow**: Percentage scales to the days the habit was actually scheduled within the window. (Behavior preservation from the existing helper; not changed by this mission.)

### Edge — Sunday late completion

**Trigger**: Kent completes a habit Sunday 22:30 ET.

**Flow** (post-fix): Monday 06:00 ET cron captures the Sunday 22:30 record because the cron now fires AFTER end of Sunday, not before.

---

## Functional Requirements

| ID | Description | Status |
| --- | --- | --- |
| FR-001 | The weekly habit report cron MUST fire after the reporting window has fully closed. Specifically: Monday 06:00 America/New_York, summarizing the prior 7-day window (Monday 00:00 ET through Sunday 23:59 ET). | Pending |
| FR-002 | The weekly-report helper MUST query completion history from `habits-history.jsonl` via `scripts/common/state_log.py` (directly or through the new domain wrapper). It MUST NOT query Vikunja `done_at` for completion-history purposes. | Pending |
| FR-003 | A new habits-domain wrapper module MUST exist that exposes query-level operations on top of `state_log.read("habits", ...)`. At minimum it MUST provide a window-bounded "completion events in this window" operation usable by any caller (current weekly helper, future trend-analysis helper, ad-hoc analysis). | Pending |
| FR-004 | An architectural test MUST exist that fails the build if any script under `scripts/habits/*.py` imports `VikunjaClient` for completion-history queries. Current-state queries (e.g. "what habits are due today") MUST remain permitted through an explicit allowlist or interface boundary. | Pending |
| FR-005 | The final WhatsApp message text for the weekly tick MUST be rendered inside the helper. The agent's role for the weekly tick collapses to: invoke helper, post helper-rendered text verbatim to WhatsApp. | Pending |
| FR-006 | The reporting-window date label in the message MUST match the actual 7-day window (exclusive of duplicate boundary days). The current "Jun 7–14" label, which spans 8 calendar days, MUST be corrected. | Pending |
| FR-007 | The helper's output JSON MUST conform to the existing WeeklyHabitReport contract (`kitty-specs/vikunja-client-and-habits-weekly-report-01KTKSFT/contracts/weekly_report_payload.md`) so any downstream consumer continues to work. The data source changes; the shape does not. | Pending |
| FR-008 | A golden-week regression fixture MUST exist that covers at least one completed habit per scheduling pattern: a daily-recurring habit, a day-specific habit (e.g. Strength training Monday), and a week-bounded habit. The test MUST fail if the weekly query returns 0% for any of them. | Pending |
| FR-009 | Per-habit and overall percentages in the report MUST reflect the completion-record count divided by the count of scheduled occurrences within the reporting window. For example, a daily habit completed four times in the prior week reports `≈57%` (4 of 7). | Pending |
| FR-010 | The `Sent by felix-admin-habits:<model>` identity line MUST be preserved in the rendered message. Identity attribution belongs to the agent, not the helper, regardless of where rendering happens. | Pending |
| FR-011 | The architecture documentation (`docs/design/architecture/data/service-inventory.json` and its narrative counterpart, plus any `data-flows.json` entry that currently claims the weekly tick reads Vikunja `done_at` history) MUST be updated to reflect the new canonical-read path. | Pending |

## Non-Functional Requirements

| ID | Description | Status |
| --- | --- | --- |
| NFR-001 | **Byte-stable helper output**: same `habits-history.jsonl` state + same CLI arguments + same wall-clock window → byte-identical helper JSON output. Preserves the determinism contract from the prior weekly-report mission (NFR-004 there). | Pending |
| NFR-002 | **Architectural-test runtime**: the canonical-read architectural test MUST complete in under 5 seconds when run standalone, and MUST run on every push to `main` via the existing CI pytest workflow. | Pending |
| NFR-003 | **Architectural-test diagnostics**: when the test fails, the failure message MUST name the specific `scripts/habits/<file>.py` and the offending import line, so the contributor can fix it without diff-archeology. | Pending |
| NFR-004 | **Renderer determinism**: same WeeklyHabitReport JSON → byte-identical rendered WhatsApp message text. No LLM-driven variation in the message. | Pending |
| NFR-005 | **Backward-compatible JSON schema**: the WeeklyHabitReport JSON schema version stays the same. Existing downstream consumers must not need any change. | Pending |

## Constraints

| ID | Description | Status |
| --- | --- | --- |
| C-001 | MUST use the existing `scripts/common/state_log.py` library as the underlying JSONL read primitive. No alternative parser or duplicate read path. | Active |
| C-002 | MUST NOT modify the `habits-history.jsonl` schema. This mission is a read-only consumer; the canonical write path (record_completion.py, sweeper.py, backfill_jsonl_from_comments.py) is out of scope. | Active |
| C-003 | The morning-tick rendering refactor is **out of scope** for this mission. If the same in-prompt-rendering pattern exists there, it will be addressed in a follow-on. | Active |
| C-004 | The broader analysis-and-course-correction epic (trend commentary, pattern detection, prompts toward course-correction) is **out of scope**. This mission ships the *primitive* those future functions build on. | Active |
| C-005 | Per Felix Constitution Directive 6: deterministic work (percentage math, window math, rendering) lives in helpers; the agent prompt only orchestrates and surfaces errors. No LLM judgment in the data path. | Active |
| C-006 | Per kg-automation deploy discipline: any change to the openclaw cron schedule or the felix-admin-habits agent prompt MUST flow through a `deploys/queued/<name>.yaml` manifest entry. | Active |
| C-007 | The architectural-test rule MUST allow a documented escape hatch for legitimate Vikunja current-state queries (e.g. "what habits are due today" via `query_active_habits_v2.py`). The rule applies to completion-history reads only. | Active |

---

## Domain Language

| Term | Definition |
| --- | --- |
| canonical primary store / canonical history | `/data/services/openclaw/state/habits-history.jsonl` on office2. Append-only JSONL written by the canonical completion writers. Authoritative for "did this habit happen on this date." |
| volatile parity write | Vikunja `done_at` field. Single timestamp per task; reset on each `repeat_after` recurrence. Useful for "is this currently done" but NEVER authoritative for historical completion counts. |
| audit-trail parity write | Vikunja `[Felix] YYYY-MM-DD \| state \| note` comments. Full historical record but as free-text strings; the JSONL log is the structured equivalent. |
| reporting window | The 7-day span of completion records being summarized in the current report. Monday 00:00 ET through Sunday 23:59 ET for the Monday 06:00 ET tick. |
| baseline window | The prior 7-day window used for change-vs-prior-week comparisons in the report. |
| habits-domain wrapper | The new module (e.g. `scripts/habits/history.py`) that exposes habit-shaped query operations on top of generic `state_log`. Owns "habits"-domain semantics; callers do not parse raw JSONL. |

---

## Key Entities

| Entity | Description |
| --- | --- |
| HabitCompletionRecord | A single completion event in `habits-history.jsonl`. Fields include `task_id`, `date`, `state` (e.g. `complete`, `auto_skipped`), `note`, `source`, `timestamp`. Schema is fixed by the existing `state_log` validate path. |
| WeeklyHabitReport | The helper's JSON output document. Per-habit rows include title, classification (daily / day-specific / week-bounded), current-window completion percentage, prior-window completion percentage, and the trend arrow. Schema defined in `kitty-specs/vikunja-client-and-habits-weekly-report-01KTKSFT/contracts/weekly_report_payload.md`. |
| HabitsHistoryWrapper | New module exposing habit-shaped queries (window-bounded completion events, per-habit completion rate, scheduled-vs-completed counts) on top of `state_log`. Becomes the single read API for any consumer of habits completion history. |

---

## Success Criteria

| ID | Description |
| --- | --- |
| SC-001 | The Monday-morning weekly report Kent receives matches an out-of-band reconstruction of his completion record for the prior week (manual spot-check against `habits-history.jsonl` ground truth on the Monday after merge + deploy). |
| SC-002 | The report arrives Monday morning, not Sunday evening. The reporting window in the message label matches the actual 7-day span. |
| SC-003 | A deliberately-bad commit (a habits script that reads Vikunja `done_at` for historical purposes) is rejected by the architectural test in CI. Test failure message names the file and line of the violation. |
| SC-004 | The golden-week regression fixture passes with non-zero percentages for at least one habit per scheduling pattern (daily, day-specific, week-bounded). |
| SC-005 | A future caller can ask the new habits-domain wrapper for "completion events in window X" without parsing raw JSONL. (Validated by the weekly helper actually using it, OR by a stub caller in the test suite.) |
| SC-006 | The architecture documentation (`docs/design/architecture/data/service-inventory.json` and its narrative counterpart, and any `data-flows.json` entry that misrepresents the weekly tick path) accurately describes the canonical-read path post-merge. |

---

## Assumptions

- `habits-history.jsonl` on office2 contains a complete record for the prior reporting week. If it doesn't, that's a separate data-integrity bug to surface — not in scope here.
- The felix-admin-habits openclaw cron schedule is operator-modifiable via OpenClaw cron configuration (no system crontab dependency). If it isn't, the cron-rescheduling step expands to a deploy-pipeline change.
- Vikunja project 13 (Habits) schema is stable for the duration of this mission. No upstream Vikunja API changes affect `done` / `done_at` / comments semantics during the mission window.
- `scripts/common/state_log.py` `read("habits", ...)` semantics are stable. The 8-domain JSONL state library is shared infrastructure and is treated as a stable dependency.
- The existing morning-checkin tick continues to work unchanged. The wrapper extraction must not regress its `exclude_completed_v2.py` consumer.
- Kent reviews and accepts the per-WP work during implement-review.

---

## Out of Scope (explicit)

- Morning-tick rendering refactor (deferred to a follow-on mission).
- Broader analysis-and-course-correction epic — trend commentary, pattern detection, course-correction prompts (deferred to a separate epic referenced by #605 / aligned with #281).
- Changes to the `habits-history.jsonl` schema or write path.
- Migration off Haiku for the felix-admin-habits agent. (Model choice stays; rendering moves to helper so model choice no longer affects number accuracy.)
- Vikunja API changes. The mission is a read-side fix on our side.

---

## Cross-References

- GitHub issue [#605](https://github.com/kentonium3/kg-automation/issues/605) — bug report with evidence + confirmed root cause.
- GitHub issue [#281](https://github.com/kentonium3/kg-automation/issues/281) — Epic: Felix-wide Directive 6 audit. felix-admin-habits is the explicit highest-contrast case.
- `kitty-specs/vikunja-client-and-habits-weekly-report-01KTKSFT/` — prior mission that introduced `query_active_habits_weekly.py` and the WeeklyHabitReport contract.
- `scripts/common/state_log.py` — domain-scoped JSONL primitive used by `record_completion.py`, `exclude_completed_v2.py`, `backfill_jsonl_from_comments.py`, `sweeper.py`.
- `docs/design/architecture/data/service-inventory.json` + `data-flows.json` — architecture data that needs updating post-merge.
- Memory `reference_vikunja_recurrence_model.md` — `repeat_after` semantics that make `done_at` volatile for daily habits.
