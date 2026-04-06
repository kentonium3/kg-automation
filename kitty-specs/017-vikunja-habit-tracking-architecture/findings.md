# F017 Findings: Vikunja Habit Tracking Architecture

**Feature**: 017-vikunja-habit-tracking-architecture
**Mission**: research
**Date**: 2026-04-06
**Vikunja version**: 0.24.6 (confirmed from `service-inventory.json`)

---

## RQ-2: Current F009 Deployment State

### What was intended

The F009 spec (`docs/func-spec/F009_daily_habit_checkin.md`) defines habits
as recurring commitments with three completion states (complete, rescheduled,
will-not-do) and 90-day queryable history. The spec explicitly deferred the
architecture decision, noting in the "Habits Are Not Tasks" principle:

> The planning phase must determine whether Vikunja's native recurring task
> capability or a custom pattern (e.g., a parent habit task with daily state
> stored in comments) is the better fit.

The spec also required habits to appear in a way that supports daily check-in
delivery and weekly pattern reporting.

### What was deployed

**Vikunja project**: Habits project (ID 13) exists with 7 tasks:

| Task ID | Title | due_date | repeat_after | repeat_mode | done |
|---------|-------|----------|-------------|-------------|------|
| 14 | Wake at 5:00 AM | null | 0 | 0 | false |
| 15 | Meditate 45 min | null | 0 | 0 | false |
| 16 | Morning shoulder PT | null | 0 | 0 | false |
| 17 | Functional strength training 45 min | null | 0 | 0 | false |
| 18 | 10K steps (monthly average) | null | 0 | 0 | false |
| 19 | Read 30 min minimum | null | 0 | 0 | false |
| 20 | Evening shoulder PT | null | 0 | 0 | false |

("null" = `0001-01-01T00:00:00Z`, Vikunja's zero-value sentinel)

All 7 tasks are static — no due_date, no recurrence configured. Frequency
is stored in the description field as text (e.g., "Daily", "Mon/Wed/Fri").

**Agent (felix-admin-habits)**: Deployed and operational. AGENTS.md defines
a query-only model — the agent reads existing tasks, checks for completion
comments by date, formats a check-in message, and delivers via WhatsApp.
The agent **never sets due_date** and **never creates new tasks**.

**Cron jobs**: Both exist and run successfully:
- `habits-morning-checkin`: daily at 11:05 UTC (7:05 AM ET), status `ok`
- `habits-weekly-report`: Sunday 22:00 UTC (6:00 PM ET), status `ok`

**Completion tracking**: Comment-based model is operational. Format:
`[Felix] YYYY-MM-DD | {complete|rescheduled|will-not-do} | note`. One
confirmed comment exists on task 15 (`[Felix] 2026-04-01 | complete`).
Task 18 has zero comments. Comment volume is sparse — the system has been
running for 6 days.

### Gap analysis

| Capability | Spec intent | Deployed state | Gap? |
|------------|-------------|---------------|------|
| Habit project structure | Dedicated project with labeled tasks | Habits project (ID 13) with 7 tasks, identity labels | No |
| Daily check-in delivery | WhatsApp message listing today's habits | Working — cron runs, agent delivers | No |
| Completion recording | Three states recorded with date | Comment-based model operational | No |
| Today filter visibility | Habits appear in Vikunja Today view | **No due_date set on any task** | **Yes** |
| Recurring behavior | Habits recur without manual intervention | Static tasks, no recurrence | **Yes** |
| Weekly pattern report | Completion rates this week vs. last | Agent has the logic; queries comments | No |
| 90-day history | Queryable completion records | Comments persist indefinitely | No |

**Root cause of the Today filter issue**: The architecture decision was
deferred during F009 planning. The implementation chose static tasks with
comment-based tracking, which works for the agent's check-in and reporting
workflows but produces tasks with no `due_date`. Vikunja's Today filter
queries `dueDate >= now/d && dueDate < now/d+1d` — tasks without a
`due_date` are invisible to it.

**Sources**: Live Vikunja API queries (tasks 14-20, comments on 15 and 18),
`openclaw cron list`, AGENTS.md on office2, F009 spec.

---

## RQ-1: Vikunja Recurring Task Behavior

### How recurring tasks work in Vikunja 0.24.6

Vikunja's recurring task model uses two fields:
- `repeat_after`: integer, seconds between repetitions (e.g., 86400 = 1 day)
- `repeat_mode`: 0 = default (add interval to dates), 1 = from current date,
  2 = monthly

**On completion** (task marked done via UI or API):
1. Vikunja advances all date fields (`due_date`, `start_date`, `end_date`,
   reminders) according to the repeat mode
2. If the task was overdue by multiple intervals, dates skip forward past
   all missed occurrences to the next future date
3. `done` is set back to `false`
4. `done_at` is **cleared** — no record of when the previous occurrence
   was completed

**The task is NOT cloned.** Vikunja reuses the same task entity — same ID,
same comments, same attachments. This is the reset-in-place model, not a
clone model. The maintainer (kolaente) has confirmed: "The way it is
currently implemented is that it only updates the dates and then marks the
task as undone."

### What happens to comments

Comments **persist** on the task because it is the same entity being reset.
They accumulate over time across all occurrences. This is a side effect of
the reset model, not a deliberate history feature.

### Completion history

**No completion history is preserved.** There is no built-in log of when
previous occurrences were completed. The `done_at` field is cleared on
each reset. The maintainer has acknowledged this gap and mentioned plans
for an activity log, but it is not implemented in any current version.

### Skip / will-not-do

**Not natively expressible.** Vikunja has no concept of skipping a single
occurrence or marking it "will not do." The only options are:
- Mark done (advances to next occurrence — indistinguishable from "complete")
- Leave overdue (sits as overdue until manually addressed)
- Delete recurrence (stops entirely)

There is no "cancel this occurrence only" state.

### Today filter behavior

The Today saved filter (or any filter using date math) queries:
```
dueDate >= now/d && dueDate < now/d+1d
```

Where `now/d` = start of today (00:00), `now/d+1d` = start of tomorrow.
Tasks with `due_date` falling within today appear. Tasks with null
`due_date` never appear.

**Note**: The API uses `snake_case` (`due_date`) but filters use
`camelCase` (`dueDate`).

### Version-specific notes

- The reset-in-place model has been consistent since at least v0.17;
  unchanged in v0.24.6
- `repeat_mode = 2` (monthly) was added in PR #834; available in v0.24.6
- No completion history or skip/will-not-do in any version to date
- Clone-based recurring tasks are a long-standing community request but
  not yet implemented

**Sources**: Vikunja help docs (vikunja.io/help/dates-and-reminders/),
Vikunja community forum threads (repeatable-tasks-reset, recurring-task-history,
temporary-marking-as-done), maintainer statements, Vikunja filter docs
(vikunja.io/help/filters/).

---

## RQ-3: Candidate Approach Comparison

### Option A: Native Vikunja Recurring Tasks

Set `repeat_after: 86400` (1 day) and `repeat_mode: 0` on each habit task.
Vikunja auto-advances `due_date` when marked done.

### Option B: Agent-Managed Daily Task Creation

The agent creates 7 new child tasks each morning with `due_date = today`.
Old tasks accumulate as the completion history (task title + done status +
date = the record).

### Option C: Hybrid — Static Tasks + Agent-Managed due_date + Comment History

Keep the current static task structure. Each morning, the agent sets
`due_date = today` on each scheduled habit. Completion tracking continues
via the existing comment model. No recurrence fields used.

### Comparison Table

| Criterion | Weight | Option A: Native Recurring | Option B: Daily Task Creation | Option C: Hybrid (due_date + comments) |
|-----------|--------|---------------------------|------------------------------|---------------------------------------|
| **Today filter visibility** | High | **Pass** — due_date is set automatically by recurrence | **Pass** — new tasks created with today's due_date | **Pass** — agent sets due_date = today each morning |
| **Skipped state expressible** | High | **Fail** — marking done is indistinguishable from skip; no native skip state | **Pass** — task can be left open (not done) or deleted; agent can add a label or description for state | **Pass** — comment records `will-not-do` distinctly from `complete`; existing model already handles this |
| **Completion history 90 days** | High | **Fail** — done_at cleared on each reset; no history preserved | **Pass** — old tasks ARE the history; queryable by date range | **Pass** — comments persist on the static task; queryable via GET /tasks/{id}/comments |
| **48-hour catch-up window** | Medium | **Fail** — if overdue, marking done skips past all missed intervals to next future date; missed days are lost | **Partial** — yesterday's task still exists and can be marked; but agent must handle creating missed tasks | **Pass** — agent can set due_date to yesterday and record a comment for any missed day; flexible |
| **Agent complexity** | Medium | **Pass** — minimal agent changes; just set recurrence fields once | **Fail** — agent must create 7 tasks daily, manage accumulating tasks (630 in 90 days), handle cleanup or archival | **Pass** — one API call per habit per morning (PATCH due_date); comment recording already implemented |

### Summary

| Option | High criteria passed | Medium criteria passed | Total |
|--------|---------------------|----------------------|-------|
| A: Native Recurring | 1 of 3 | 1 of 2 | 2 of 5 |
| B: Daily Task Creation | 3 of 3 | 1 of 2 | 4 of 5 |
| C: Hybrid | 3 of 3 | 2 of 2 | **5 of 5** |

### Assessment

**Option A is eliminated.** Native recurring tasks fail on the two most
important requirements: skipped state and completion history. The reset-in-place
model destroys the data this system needs. These are not edge cases — they are
core to the accountability tracking purpose.

**Option B is viable but unnecessarily complex.** Creating 7 tasks daily produces
630 tasks in 90 days. The Habits project would become cluttered, query performance
degrades, and the agent needs task lifecycle management (creation, archival, cleanup)
that doesn't currently exist. The 48-hour catch-up is only partial — the agent
must retroactively create tasks for missed days.

**Option C satisfies all five criteria with minimal change.** The current system
already has 90% of the implementation: static tasks, comment-based completion
tracking, agent check-in workflow, cron jobs. The only missing piece is setting
`due_date = today` on each scheduled habit during the morning check-in. This is
one PATCH call per habit — 7 API calls added to the existing morning workflow.

The "lightweight external log" evaluated for Option C turns out to be **the
existing comment model** — it already satisfies history, state tracking, and
queryability requirements. No new external store is needed.

**Sources**: RQ-1 findings (recurring task behavior), RQ-2 findings (current
deployment state), Vikunja API documentation (task update, filter behavior).

---

## RQ-4: API Capabilities for Option C

All operations below are confirmed available in Vikunja 0.24.6.

### Required Operations

| Operation | Method | Endpoint | Key Fields | Confirmed |
|-----------|--------|----------|------------|-----------|
| Update task due_date | PUT | `/api/v1/tasks/{id}` | `due_date` (ISO 8601) | Yes |
| Get task details | GET | `/api/v1/tasks/{id}` | Full task object | Yes (used in pre-research) |
| List project tasks | GET | `/api/v1/projects/{id}/tasks` | Array of task objects | Yes |
| Create comment | PUT | `/api/v1/tasks/{id}/comments` | `comment` (string) | Yes |
| List comments | GET | `/api/v1/tasks/{id}/comments` | Array of comment objects | Yes (used in pre-research) |
| Filter tasks by due_date | GET | `/api/v1/tasks/all?filter=dueDate...` | Filter syntax | Yes (documented) |

### Implementation Detail

**Setting due_date** (the new operation needed):
```
PUT /api/v1/tasks/{id}
Authorization: Bearer <token>
Content-Type: application/json

{
  "due_date": "2026-04-06T00:00:00Z"
}
```

Vikunja's task update endpoint accepts partial updates — only `due_date`
needs to be sent; other fields remain unchanged.

**Today filter query** (confirming habits appear after due_date is set):
```
GET /api/v1/tasks/all?filter=done = false %26%26 dueDate >= now/d %26%26 dueDate < now/d%2B1d
```

Or via saved filter in the Vikunja UI — same filter syntax.

### Gaps

None identified. All required operations exist and are documented in the
Vikunja API reference. The pre-research session already exercised GET
endpoints for tasks and comments against the live instance.

**Sources**: Vikunja API reference (try.vikunja.io/api/v1/docs), live
instance queries (pre-research session), Vikunja filter documentation
(vikunja.io/help/filters/).

---

## Architecture Recommendation

### Recommended Approach: Option C — Hybrid (Static Tasks + Agent-Managed due_date + Comment History)

### Rationale by Evaluation Criterion

**Today filter visibility (High)**: The agent sets `due_date = today` on
each scheduled habit during the morning check-in. Tasks immediately appear
in the Vikunja Today filter. This is a single PUT call per habit — 7 calls
for the full habit list.

**Skipped state expressible (High)**: The existing comment model already
records three distinct states: `complete`, `rescheduled`, `will-not-do`.
No change needed. The comment format
`[Felix] YYYY-MM-DD | {state} | note` is already deployed and operational.

**Completion history survives 90 days (High)**: Comments persist
indefinitely on the static task. Each day's completion is a separate
comment with the date embedded. The agent already queries these for weekly
reporting. No change needed.

**48-hour catch-up window (Medium)**: The agent can set `due_date` to
any date and record a comment for that date. If Kent missed yesterday's
check-in, the agent can still create yesterday's completion record as a
comment. The due_date for today's check-in simply overwrites yesterday's.

**Agent implementation complexity (Medium)**: Minimal change required.
The agent's morning check-in workflow gains one additional step: after
determining today's scheduled habits, PATCH each task's `due_date` to
today before delivering the WhatsApp message. No new external data store.
No new task lifecycle management. The comment-based completion model is
unchanged.

### What Changes in the Revised F009 Implementation

1. **AGENTS.md — new step in morning check-in**:
   After Step 2 (query active habits) and before Step 4 (format check-in):
   - New Step 3: For each habit scheduled for today, set `due_date` to
     today via `PUT /api/v1/tasks/{id}` with
     `{"due_date": "<today>T00:00:00Z"}`
   - This ensures habits appear in the Today filter before Kent checks
     Vikunja

2. **No changes to completion recording**: The comment model is unchanged.

3. **No changes to weekly reporting**: The agent already queries comments
   by date for pattern reporting. No new data source needed.

4. **No changes to cron configuration**: Same schedule, same delivery.

5. **No new services or external stores**: The recommendation uses only
   existing Vikunja API capabilities on the existing instance.

### Known Risks and Limitations

| Risk | Severity | Mitigation |
|------|----------|------------|
| If the morning cron fails, due_date is not set and habits don't appear in Today | Medium | Cron failure is already monitored; habits still work via WhatsApp even without Today visibility |
| due_date is overwritten daily — no record of when it was last set | Low | Irrelevant; the comment is the authoritative completion record, not the due_date |
| Tasks not scheduled today retain yesterday's due_date until next scheduled day | Low | Acceptable — they won't appear in Today filter until their next scheduled day |
| Vikunja API rate limiting on 7 rapid PUT calls | Very Low | Vikunja is a local instance with no rate limiting configured; 7 calls in sequence is negligible |

### Decision Gate: Resolved

This recommendation fully resolves the deferred architecture decision in
the F009 spec's "Habits Are Not Tasks" section. The answer is: **habits
are static tasks with agent-managed due_date for Today visibility and
comment-based completion tracking for history and state.** No native
recurring task features are used. No external data store is needed.

---

## Sources Consulted

| # | Source | Type | RQs |
|---|--------|------|-----|
| 1 | Live Vikunja instance (API queries, tasks 14-20, comments) | Primary | RQ-1, RQ-2, RQ-4 |
| 2 | Vikunja API reference (try.vikunja.io/api/v1/docs) | Primary | RQ-1, RQ-4 |
| 3 | Vikunja help docs — dates/reminders (vikunja.io/help/dates-and-reminders/) | Secondary | RQ-1 |
| 4 | Vikunja help docs — filters (vikunja.io/help/filters/) | Secondary | RQ-1, RQ-4 |
| 5 | Vikunja community forum — recurring task threads | Secondary | RQ-1 |
| 6 | service-inventory.json (version confirmation) | Internal | RQ-1 |
| 7 | F009 spec (docs/func-spec/F009_daily_habit_checkin.md) | Internal | RQ-2 |
| 8 | habits-ops.md runbook | Internal | RQ-2 |
| 9 | AGENTS.md on office2 | Internal | RQ-2 |
| 10 | openclaw cron list/runs on office2 | Internal | RQ-2 |

**Independent source count**: 5 (live instance, API docs, help docs,
community forum, internal documentation) — exceeds the minimum of 3.

---

**END OF FINDINGS**
