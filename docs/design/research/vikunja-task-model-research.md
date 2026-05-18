---
id: research-vikunja-task-model
doc_type: research
title: Vikunja task model — capabilities, current usage, and completion-record audit
status: draft
level: 1
owners: [kent]
last_validated: 2026-05-18
version: 0.2
---

# Vikunja task model research

**Purpose.** Surface the data Kent and Claude need to redesign how Felix
interacts with Vikunja. The recent habits subsystem investigation
(2026-05-16) exposed a fragile pattern (custom "completion = dated
comment" semantics on tasks with `repeat_after=0`) that likely exists
elsewhere. Before redesigning, we need a clear picture of (1) what
Vikunja can do natively, (2) how each of Felix's four Vikunja-touching
agents uses it today, and (3) the shape of the completion records we
already depend on.

This document does **not** propose a design. It enumerates the facts and
the open questions that the design discussion must answer.

---

## Executive summary

1. **Vikunja has native repeating tasks; we don't use them.**
   `repeat_mode` takes three integer values (0 default/interval,
   1 monthly, 2 from-current-date). On `done=true` Vikunja advances
   `due_date`, `start_date`, `end_date`, and reminders in place, then
   flips `done` back to `false` — task ID, comments, labels are
   preserved. All eight production habit tasks (IDs 14-20, 65) have
   `repeat_after=0, repeat_mode=0`.
2. **Native recurrence is interval-only.** Vikunja cannot express
   "every Mon" or "first Tue of month". Closest fits: daily
   (`repeat_after=86400`) or monthly-on-same-date (`repeat_mode=1`).
   Day-of-week schedules (`Mon-Sat`, `Mon/Wed/Fri`) live entirely in
   our description-parser.
3. **No native completion-history surface.** `/api/v1/activity`,
   `/api/v1/events`, `/api/v1/tasks/{id}/activity` all return 404.
   `done_at` is scalar (last completion only). Our `[Felix]` comments
   ARE the history substrate.
4. **Webhooks exist but are unconfigured.** `webhooks_enabled: true`;
   `GET /projects/13/webhooks` returns `[]`. We could subscribe to
   `task.updated` / comment events instead of cron polling.
5. **The filter language is more expressive than our usage.** Date
   math (`now/d`, `now-7d`), comparisons on `done_at`/`updated`, and
   boolean combinations all work live. Saved views per project also
   carry filters (e.g., the Habits "List" view filters `done = false`).
6. **Three structured-comment conventions coexist.** habits
   (`[Felix] YYYY-MM-DD | state`), escalation (`[Felix-Escalation] ...`),
   and tasker (`[Felix] enrichment | ...`). Only the habits parser is
   extracted to a deterministic helper; the others are LLM-parsed in
   prompt. None have an external mirror.
7. **The vulnerability that hit habits likely applies to escalation.**
   Both key off comment-based state. The escalation skill partially
   mitigates Kent-rescheduled-in-UI (rule 5: "due_date later than last
   comment → reset to Level 1") but has no comparable mitigation for
   Kent-marks-done-in-UI.

---

## Section 1 — Vikunja native capabilities

Live instance: `v0.24.6` (verified `GET /api/v1/info`).
Base URL: `https://office2.tail0f5f56.ts.net/api/v1/`.
All probes below executed read-only with the API token at
`/data/services/openclaw/secrets/vikunja-api`.

### 1.1 Recurrence model

Source: Vikunja source `pkg/models/task_repeat.go` (verified via
`kolaente.dev` mirror).

| Constant | Integer | Behavior on `done=true` |
| --- | --- | --- |
| `TaskRepeatModeDefault` | `0` | Advance `due_date`, `start_date`, `end_date`, and reminders by `repeat_after` seconds. Then set `done=false`. |
| `TaskRepeatModeMonth` | `1` | Shift the same dates forward by one calendar month (ignores `repeat_after`). Then set `done=false`. |
| `TaskRepeatModeFromCurrentDate` | `2` | Anchor the next instance to the time the task was marked done (not the previous `due_date`). Uses `repeat_after`. |

Key facts:

- **In place, not new task.** The task ID, comments, attachments,
  labels, and `done_at` are preserved across cycles. Only the date
  fields and `done` flag change.
- **`repeat_after` is seconds.** "Daily" = `86400`, "weekly" =
  `604800`, "biweekly" = `1209600`.
- **No RRULE, no iCal recurrence rules.** Concrete recurrences Vikunja
  can express natively:
  - Every N days/weeks/hours (`repeat_after=N seconds, repeat_mode=0`)
  - Monthly on the same date (`repeat_mode=1`)
  - "N seconds after I last finished" (`repeat_mode=2`) — useful for
    habits like "PT every 2 days after the previous session"
- **Cannot express natively:**
  - "Every Mon" or any weekday subset (`Mon/Wed/Fri`)
  - "First Tuesday of the month"
  - "Every weekday"
  - End-of-month dates with weekend skipping
- **CalDAV is enabled** (`caldav_enabled: true` in `/api/v1/info`). If
  CalDAV's recurrence handling differs from the JSON API, that is
  unverified.

### 1.2 Completion behavior

| Aspect | Behavior |
| --- | --- |
| Non-repeating task | `done=true` → `done_at` populated, task stays done. |
| Repeating task | `done=true` → `done_at` populated, dates advance, `done` returns to `false` (one round-trip). |
| Multiple completions in one cycle | The most recent `done_at` overwrites the previous one. Vikunja stores **one** `done_at` per task, not a list. |
| Done-then-undone | Setting `done=false` clears `done_at` to the zero sentinel `0001-01-01T00:00:00Z`. |

Implication: **on a non-repeating task, `done_at` records only the most
recent completion.** If Kent marks the same task done twice (because he
re-opened it), the first completion timestamp is lost.

### 1.3 Activity log / history

| Endpoint | Status | Result |
| --- | --- | --- |
| `GET /api/v1/activity` | 404 | Not implemented |
| `GET /api/v1/tasks/14/activity` | 404 | Not implemented |
| `GET /api/v1/events` | 404 | Not implemented |
| `GET /api/v1/notifications` | 200 → `null` | Empty (per-user notifications, not events) |

There is no native API surface for "task X was marked done at time T by
user U." The only persistent traces are:

- `task.done_at` (most recent completion only, scalar)
- `task.updated` (touched by any update, no detail of what changed)
- `task.created` (set-once)
- Task comments (free-text, any user, any content)

**This is the core finding for Section 3:** our `[Felix]` comment
discipline is the *only* completion history Felix has. Vikunja does not
preserve it independently.

### 1.4 Filter / query language

Probed against the live instance. Confirmed-working syntax:

| Pattern | Example | Verified |
| --- | --- | --- |
| Boolean field | `done = false` | Yes |
| Numeric comparison | `priority >= 2` | Yes |
| Date math (anchor) | `due_date < now` | Yes |
| Date math (rounding) | `due_date < now/d` | Yes |
| Date math (offset) | `done_at >= now-7d` | Yes |
| Date math (explicit) | `due_date < 2026-05-16` | Yes |
| Combined AND | `done = false && priority >= 2 && due_date < now/d` | Yes (returned task ID 63) |
| Label membership | `labels in 1` | Yes (numeric IDs only) |
| URL encoding | spaces → `%20` or `+`, `&&` → `%26%26` | Both forms accepted |

Time units in date math: `s m h d w M y`. Anchors: `now` or fixed
date with `||` separator (`2024-03-11||+1w`). Source:
[Vikunja docs — filters](https://vikunja.io/docs/filters/).

**Not supported in filters:** label names (must resolve to IDs first);
project names (must resolve to IDs); the `s=` search parameter cannot be
combined with `filter=`; `repeat_mode` and `repeat_after` are not
listed as documented filter fields.

**Views (saved filters per project) exist as a first-class entity.**
`GET /projects/{id}/views` returns objects with a `filter` field —
each project has default List / Gantt / Table / Kanban views, and the
"List" view on the Habits project has `filter: "done = false"`
(verified id 61). New views can be created per project; they are
project-scoped, not global.

### 1.5 Webhooks / events

| Aspect | Value |
| --- | --- |
| Enabled flag (`/api/v1/info`) | `"webhooks_enabled": true` |
| Configured webhooks on Habits project | `[]` (none) |
| Configuration | Per-project endpoint: `GET/PUT/POST/DELETE /api/v1/projects/{id}/webhooks`. User-account webhooks exist separately. |
| Payload shape | `{event_name, time, data: {task, doer}}` per [docs/webhooks](https://vikunja.io/docs/webhooks) |
| Verified events | `task.created` documented by example; other events ("task, project, comment, attachment, and relation events") referenced but not enumerated in the doc page we fetched. |
| Signature | Optional HMAC-SHA256 via `X-Vikunja-Signature` |
| Delivery | At-most-once. No retry on failure. 30s default timeout. |

We can react to UI writes in (near) real time if we run an HTTP
receiver on office2. We do not today.

### 1.6 Auth model

The API token at `/data/services/openclaw/secrets/vikunja-api` is
owned by the `kent` user (user ID 1, username `kent`). Verified by
the `created_by` and `author` fields on every probed task/comment.

There is no separate `felix-bot` account in Vikunja. **Agent writes are
indistinguishable from Kent's writes at the API layer.** The `[Felix]`
prefix on comments is the only thing that flags an entry as
agent-generated. Comment authors are always `kent`. Kent's UI session
and the agent's API session see the same data and have the same
mutation permissions.

---

## Section 2 — Current code survey

Four agents touch Vikunja. Workspace files on office2 at
`/data/services/openclaw/<agent>-agent/AGENTS.md`. The shared
`vikunja-api` skill is at `~/.openclaw/skills/vikunja-api/SKILL.md`.

### 2.1 felix-admin-habits

| Aspect | Detail |
| --- | --- |
| Endpoints read | `GET /projects`, `GET /projects/{id}/tasks?per_page=200`, `GET /tasks/{id}/comments` |
| Endpoints written | `POST /tasks/{id}` (due_date update), `PUT /tasks/{id}/comments` |
| Helper scripts | `scripts/habits/compute_today.py`, `query_active_habits.py`, `set_due_dates.py`, `exclude_completed.py` |
| Completion model | `[Felix] YYYY-MM-DD \| {complete\|rescheduled\|will-not-do} \| optional note` comment. Vikunja's native `done` flag is NOT used to mark a completion. |
| "Today's work" model | Frequency lexicon parsed from `description` field: empty → daily, `Daily`, `Mon-Sat`, `Mon/Wed/Fri`. Filter is local in `query_active_habits.py:69-76`. |
| State-tracking workaround | The "dated comment" pattern is required because `repeat_mode=0, repeat_after=0` means the task never auto-rolls over. Daily due_date is force-set every morning by `set_due_dates.py` to end-of-day-ET (issue #112 fix). |
| Parallel-write reconciliation | None. If Kent marks the task `done=true` in the UI, `query_active_habits.py:152-154` permanently excludes it (the 2026-05-16 incident). |

References:
- `/Users/kentgale/repos/kg-automation/scripts/habits/query_active_habits.py:150-154` — `done=True` exclusion
- `/Users/kentgale/repos/kg-automation/scripts/habits/exclude_completed.py:79-83` — `[Felix]` comment regex
- `/Users/kentgale/repos/kg-automation/scripts/habits/set_due_dates.py:56-78` — UTC-`Z` rejection (issue #112 regression-prevention)
- `/data/services/openclaw/habits-agent/AGENTS.md` Steps 1-6 — full workflow

### 2.2 felix-admin-escalation

| Aspect | Detail |
| --- | --- |
| Endpoints read | `GET /projects/{id}` (name lookup), `GET /api/v1/tasks/all?filter=...` (candidates), `GET /tasks/{id}/comments` |
| Endpoints written | `POST /tasks/{id}` (mark done, update due_date on reschedule), `PUT /tasks/{id}/comments` |
| Helper scripts | None — escalation is currently in-prompt logic following `~/.openclaw/skills/escalation/SKILL.md` |
| Completion model | The agent reads `done` via the Vikunja-native flag for filtering candidates, and writes `done=true` only on explicit "N done" responses from Kent. State is tracked in `[Felix-Escalation]` comments separate from completion. |
| "Today's work" model | Native filter: `done = false && priority >= 2 && due_date < today && project_id NOT IN (11, 13)`. Verified live (task #63 matched on 2026-05-16). |
| State-tracking workaround | Comment-based escalation level state: `[Felix-Escalation] DATE \| level-N \| sent`, snooze/dismiss/done/rescheduled disposition tokens. Most-recent comment determines next-step level. |
| Parallel-write reconciliation | Partial. Skill section 2 rule 5: `dismissed` + later `due_date` → reset to Level 1. No reconciliation for "done in UI" (the task drops out of the candidate query naturally), but also no detection that Kent silently dismissed the alert outside the response patterns. |

**The same vulnerability class as habits exists here**: if Kent reschedules a
task in the UI (changing `due_date`), the escalation skill rule 5 partially
handles it. But if he resolves an escalation by marking done in the UI
without using the response patterns, the `[Felix-Escalation] level-N | sent`
comment remains the latest, and the algorithm in skill section 2 rule 3 would
re-escalate at Level 2 if the cron fires again (task is no longer overdue, so
it drops out — saved by the candidate filter, not by the comment-state logic).

References:
- `/data/services/openclaw/escalation-agent/AGENTS.md` Steps 1-7 (full workflow)
- `~/.openclaw/skills/escalation/SKILL.md` sections 1-5 on office2
- Live verification: task #63 has comment id 33 `[Felix-Escalation] 2026-05-16 | level-1 | sent`

### 2.3 felix-admin-capture (inbox)

| Aspect | Detail |
| --- | --- |
| Endpoints read | `GET /projects` (resolve Goals/Inbox by name) |
| Endpoints written | Delegates task creation to felix-admin-tasker. Directly creates a task only when the inbox content is a valid Felix goal declaration; that goes into the Goals project (ID 11) via `PUT /projects/{goals_id}/tasks`. |
| Helper scripts | `scripts/inbox/prescan.py`, `append_routing_entry.py`, `handle_marker_cleanup.py`, `handle_parse_failures.py`, etc. — none touch Vikunja directly. |
| Completion model | N/A — the agent does not record completions. |
| "Today's work" model | Routing log at `~/second-brain/agents/state/inbox-routing.jsonl` (filesystem, not Vikunja) — dedups by filename. |
| State-tracking workaround | All state lives in the routing log + Obsidian frontmatter (`status: processed`, `processed_at: ISO timestamp`). Vikunja is a write-only sink for tasks/goals routed out of the inbox. |
| Parallel-write reconciliation | Not applicable — the inbox state is Obsidian-side. |

References:
- `/data/services/openclaw/inbox-agent/AGENTS.md` Steps 1-7

### 2.4 felix-admin-tasker

| Aspect | Detail |
| --- | --- |
| Endpoints read | `GET /projects`, `GET /labels`, `GET /tasks/all?filter=...` (active goals, flat tasks in Inbox), `GET /tasks/{id}/comments` (enrichment state check) |
| Endpoints written | `PUT /projects/{id}/tasks` (create), `PUT /tasks/{id}/labels` (identity), `PUT /tasks/{id}/relations` (goal link), `PUT /tasks/{id}/comments` (enrichment state), `POST /tasks/{id}` (updates) |
| Helper scripts | None — tasker is in-prompt logic against the `vikunja-api` and `task-intelligence` skills |
| Completion model | The agent does not track task completion. It tracks **enrichment** state via `[Felix] enrichment \| {proposed\|confirmed\|skipped\|declined} \| ISO timestamp`. |
| "Today's work" model | `GET /tasks/all?filter=done = false && project_id = <inbox>` for flat-task detection; one-shot per `enrich_task` for delegated handoffs. |
| State-tracking workaround | Comment-based enrichment state (single-offer policy: a skipped/declined task is never re-proposed). The agent supports the optional task fields `repeat_after`, `repeat_mode`, `start_date` — verified in AGENTS.md Step 6 — but in practice none of the production tasks I sampled use them. |
| Parallel-write reconciliation | Implicit — the `[Felix] enrichment | proposed` lookup will see a Kent-added enrichment comment if he ever wrote one, but no other UI signal is reconciled. |

References:
- `/data/services/openclaw/tasker-agent/AGENTS.md` Action: enrich_task Step 6
- `~/.openclaw/skills/task-intelligence/SKILL.md` (not read in full but referenced)
- Live verified: task #8 has `[Felix] enrichment | proposed | 2026-04-11T16:12:28Z` (comment id 7); task #9 has same pattern (comment id 8).

### 2.5 Cross-agent comparison

| Concern | habits | escalation | inbox | tasker |
| --- | --- | --- | --- | --- |
| Uses Vikunja `done=true` to mark completion? | **No** | Only in response to "N done" | N/A | N/A (creates only) |
| Uses Vikunja `repeat_mode`/`repeat_after`? | No (`0, 0` for all 8 habits) | No | No | Optional, unused in practice |
| Uses `[Felix]`-prefixed structured comments? | Yes (state) | Yes (`[Felix-Escalation]`) | No (uses Obsidian frontmatter) | Yes (`[Felix] enrichment`) |
| Has helper-script-extracted parsers? | Yes (#282) | No (in-prompt skill) | N/A | No (in-prompt skill) |
| Has external state mirror? | No | No | Yes (routing log + frontmatter) | No |
| Reconciles Kent-in-UI parallel writes? | **No (regressed 2026-05-16)** | Partial (reschedule only) | N/A | None |

---

## Section 3 — Completion-record data model

### 3.1 Three structured-comment conventions in production

Three distinct `[Felix]…`-prefixed comment formats coexist:

| Convention | Prefix | Owner | Shape |
| --- | --- | --- | --- |
| Habit completion | `[Felix]` | habits-agent | `[Felix] YYYY-MM-DD \| {complete\|rescheduled\|will-not-do} \| optional note` |
| Escalation state | `[Felix-Escalation]` | escalation-agent | `[Felix-Escalation] YYYY-MM-DD \| {level-N\|snoozed:Nd\|dismissed\|done\|rescheduled:DATE} \| {sent\|acknowledged}` |
| Enrichment state | `[Felix]` | tasker-agent | `[Felix] enrichment \| {proposed\|confirmed\|skipped\|declined} \| ISO timestamp \| optional note` |

Note that habit comments and enrichment comments **share the same
`[Felix]` prefix** but use a different second-field shape (`YYYY-MM-DD`
vs the literal word `enrichment`). The habits parser
(`exclude_completed.py:79-83`) and the tasker single-offer check use
different regexes; neither is shared.

### 3.2 Live samples

All samples pulled from office2 on 2026-05-16.

Habit task 14 ("Wake at 5:00 AM"):
- id 2 (2026-04-01): `[Felix] 2026-03-31 | complete | test entry`
- id 11 (2026-04-16): `<p></p>` — HTML empty, author kent, source unknown
- id 17: `[Felix] 2026-05-12 | complete`
- id 19: `[Felix] 2026-05-13 | will-not-do | late work session until 4am`
- id 30: `[Felix] 2026-05-15 | complete`

Habit task 17 ("Functional strength training 45 min"):
- id 4: `[Felix] 2026-04-01 | will-not-do`
- id 14, 22, 28: `[Felix] {date} | complete` (2026-05-11, -13, -15)

Habit task 65 ("Morning hip PT") — shorter history, illustrating that
not all habits have a long trail:
- id 20: `[Felix] 2026-05-13 | complete`
- id 29: `[Felix] 2026-05-15 | complete`

Escalation task 63 ("Prepare Intentional materials..."):
- id 33 (2026-05-16): `[Felix-Escalation] 2026-05-16 | level-1 | sent`

Tasker enrichment tasks 8 and 9 (both):
- `[Felix] enrichment | proposed | 2026-04-11T16:12:28Z`

### 3.3 Format codification

| Format | Codified where | Authoritative parser |
| --- | --- | --- |
| Habit completion | `habits-agent/AGENTS.md` "Comment format specification" section | `scripts/habits/exclude_completed.py:79-83` (regex `FELIX_COMMENT_PATTERN`) |
| Escalation | `~/.openclaw/skills/escalation/SKILL.md` section 3 | None (in-prompt parsing per skill section 2 rules) |
| Enrichment | `tasker-agent/AGENTS.md` "Enrichment State Tracking" section + `~/.openclaw/skills/task-intelligence/SKILL.md` (referenced) | None (in-prompt per skill) |

The habits parser is the **only** deterministic, tested implementation.
Escalation and enrichment formats are interpreted by the agent prompt at
runtime — stochastic, not deterministic, even though the format is
mechanical.

### 3.4 Storage and durability

- **Comments are the only authoritative store** for all three
  conventions. There is no external mirror.
- Comment deletion permanently destroys the record. Vikunja v0.24.6
  exposes `DELETE /api/v1/tasks/{id}/comments/{cid}` (untested but
  documented). Kent can delete any comment in the UI.
- `done_at` is the only Vikunja-native timestamp of a completion-like
  event, and it is **scalar**: one timestamp per task. For a
  non-repeating habit task that has been marked done many times,
  `done_at` only reflects the most recent. (Verified live: tasks
  14, 15, 16, 17, 20, 65 all have `done_at` set to 2026-05-16, and
  the field has been overwritten on prior days that are no longer
  recoverable from the API.)

### 3.5 Queryability

| Consumer | Method | Determinism |
| --- | --- | --- |
| habits-agent weekly report (AGENTS.md "Weekly pattern report") | LLM-parsed in prompt at report time | Stochastic |
| habits-agent morning check-in (`exclude_completed.py`) | Regex-parsed by helper script | Deterministic |
| escalation-agent level determination | LLM-parsed in prompt per skill section 2 | Stochastic |
| tasker-agent single-offer check (enrichment) | LLM-parsed in prompt per AGENTS.md Step 1 | Stochastic |

Only the morning check-in path has been split into deterministic
helpers (mission #282). The weekly report and the other two agents'
state parsing remain in-prompt — a known fragility per
Constitution Directive 6.

### 3.6 Failure modes

| Mode | Current behavior |
| --- | --- |
| Comment with non-Felix prefix (e.g., `<p></p>`) | Habits: skipped silently (`exclude_completed.py:133`). Escalation/tasker: skipped if scan finds no recognized prefix (in-prompt). |
| Felix prefix with malformed body | Habits: WARN to stderr, treated as not-addressed (`exclude_completed.py:138-142`). Escalation/tasker: stochastic — depends on LLM interpretation. |
| Felix prefix with unknown state token | Habits: WARN, treated as not-addressed (`exclude_completed.py:149`). Others: stochastic. |
| Date wrong (mismatched with today) | Skipped (not addressed today). |
| Missing comment entirely | Habits: counts as "no-response" (AGENTS.md "No-response tracking"). |
| Kent edits a comment in UI | Vikunja updates `comment.updated` timestamp; no audit trail of the prior value. Habits' "most recent wins" rule (`exclude_completed.py:155-161`) uses comment id, not text-edit recency. |
| Kent deletes a comment in UI | Record is gone. No recovery path. |
| Kent marks `done=true` in UI on a habit | **Critical:** `query_active_habits.py:152-154` excludes the habit from future check-ins forever. The 2026-05-16 incident. |

---

## Open design questions

These are the choices the data forces. They are not answered here.

1. **Native recurrence vs custom day-of-week logic.** Do we adopt
   Vikunja's `repeat_mode=0, repeat_after=86400` (daily) for the daily
   habits and keep `query_active_habits.py` only for the `Mon-Sat` and
   `Mon/Wed/Fri` cases? Or do we keep the description-parser uniform
   for all habits so the agent has one mental model?
2. **`done=true` vs comment-as-completion.** Is "habit done today"
   meant to be the native `done` flag (which on a repeating task
   auto-rolls), or the dated comment (which we control)? If we adopt
   `done=true`, do we still need any structured comment beyond a free-
   text optional note?
3. **History preservation.** If `done` auto-flips back to `false` on
   each cycle, `done_at` is overwritten. Where does "the last 30
   days of completions" live? Options: (a) keep writing dated comments
   alongside native `done`, (b) write a JSONL mirror to disk on each
   completion, (c) subscribe to a webhook that pushes
   completions to an event log.
4. **Webhooks vs cron polling.** Should Felix subscribe to Vikunja
   webhooks (`task.updated`, comment events) so UI writes can be
   reconciled in real time? Or keep cron-based reconciliation, with
   each agent doing its own delta detection?
5. **One comment-format parser or N.** Three structured-comment
   conventions exist (`[Felix] DATE | state`, `[Felix-Escalation] ...`,
   `[Felix] enrichment | ...`). Do we codify a single canonical shape
   and one parser library all agents import, or keep them
   independent?
6. **Identity attribution.** All Vikunja writes appear to come from
   `kent`. Do we provision a separate `felix-bot` Vikunja user so the
   audit trail at the API layer reflects who wrote what (with
   implications for sharing/ownership)? Or rely solely on the
   `[Felix]` prefix convention?
7. **Parallel-write reconciliation policy.** When Kent acts in the UI,
   each agent should decide what to do with stale agent-side state.
   Concretely: if Kent marks a habit `done=true` in the UI, should the
   agent (a) treat that as equivalent to a `[Felix] complete` comment
   and skip the morning check-in, (b) ignore it and check in anyway,
   (c) detect it and prompt Kent for confirmation. Same question for
   escalation, where it's "Kent marks the escalated task done in UI."
8. **Frequency lexicon expansion.** Today the lexicon is `Daily`,
   `Mon-Sat`, `Mon/Wed/Fri`, empty (= daily). Do we extend it
   (`Sun`, `Tue/Thu`, "first Mon of month") via the description
   parser, or migrate the genuinely-monthly cases to
   `repeat_mode=1`?
9. **Filter scope.** The escalation candidate query is currently
   built in-prompt and could be a single saved view on the relevant
   projects (`GET /projects/{id}/views`). Should agents own saved
   filters/views, or keep filters local to the agent code?
10. **Failure-mode hardening.** Today, a malformed `[Felix]` comment
    on a habit causes the habit to be re-asked. Is that the right
    failure direction for all three conventions, or should some lean
    the other way (e.g., a malformed `[Felix-Escalation]` comment
    should NOT silently downgrade to Level 1)?

---

## Appendix: Verified API gotchas (Vikunja v0.24.6)

Five defects in the felix-bot provisioning helpers slipped past 89
passing pytest tests and three rounds of Codex review and were caught
only during the live Phase 1 run of mission
`felix-bot-vikunja-provisioning-01KRT3N4` on 2026-05-17 (filed as
issue [#317](https://github.com/kentonium3/kg-automation/issues/317)).
Four are genuine Vikunja API contract quirks; the fifth is a
helper-defaults defect surfaced by the same live run and recorded here
because it shares an origin and a lesson.

Future ADR-0002 work (issues
[#305](https://github.com/kentonium3/kg-automation/issues/305) and
[#311](https://github.com/kentonium3/kg-automation/issues/311)) — any
new helper that calls Vikunja v0.24.6 — should treat these as known
shape until confirmed otherwise on a newer Vikunja release.

### G1 — Share payload `user_id` field expects a username string

`PUT /api/v1/projects/{id}/users` accepts a body of shape
`{"user_id": "<username>", "right": 1}`. The field is named `user_id`
but its value is the target user's USERNAME (string), not the numeric
user id (not as int, not as the int cast to string).

- Passing `int` returns HTTP 400 `Unmarshal type error: expected=string,
  got=number, field=user_id`.
- Passing the numeric id as a string (`"2"`) returns API error `1005`
  (`user does not exist`).
- Passing the username string (`"felix-bot"`) succeeds; the
  create-response echoes the value back under `user_id`.

Fixed in `01fabcf` (int → str cast) and `eb9cc80` (str id → username
string). See `scripts/vikunja/provision_felix_bot.py:share_project_with_user`.

### G2 — Share-list response uses `username`, not `user_id`

`GET /api/v1/projects/{id}/users` returns a list of user objects with
shape `{id, name, username, right, ...}`. There is **no `user_id`
field**. Helpers that verify "is felix-bot shared on this project?"
must match on the `username` field.

Fixed in `eb9cc80` (`verify_shares_applied` now matches on
`username`). See `scripts/vikunja/provision_felix_bot.py:verify_shares_applied`.

### G3 — Comment attribution lives on `author`, not `created_by`

Comment objects on `/api/v1/tasks/{id}/comments` (both PUT-create
response and GET-readback) carry attribution under
`author.username`. Vikunja v0.24.6 **does not populate `created_by`
on comment objects at all** — so any helper enforcing a strict
`created_by.username == X` invariant on a comment object will fail
unconditionally, regardless of who actually wrote the comment.

Note the asymmetry with TASK objects, which DO use
`created_by.username` for the creator (validator's task-creation
checkpoint relies on this and is correct).

Fixed in `baa96ee` (validator + swap-secrets probe switched to
`author.username`, no fallback). See
`scripts/vikunja/validate_felix_bot.py` and
`scripts/vikunja/swap_vikunja_secrets.py`.

### G4 — Comment-create is `PUT`, not `POST`

`PUT /api/v1/tasks/{id}/comments` creates a comment. The same path
with `POST` returns HTTP 404. Helpers that probe the comment-write
path post-secret-swap (or anywhere else) must use PUT.

Fixed in `e31ae54` (swap-secrets verify-probe switched from POST to
PUT, matching the working PUT in `validate_felix_bot.py`).

Severity note: this defect first surfaced as a misleading
"DEEPLY DEGRADED" warning during auto-rollback — the rollback itself
succeeded, but the verify probe could never get HTTP 2xx on either
the forward or reverse path. False alarm, real production scare.

### G5 — Production secret-file paths are under `/data/`, not `/etc/`

The default values for `--secrets-path` and `--bak-path` in
`validate_felix_bot.py` initially pointed at `/etc/openclaw/secrets/...`
with an obsolete `vikunja-api.kent` filename. The canonical production
paths are `/data/services/openclaw/secrets/vikunja-api` and
`/data/services/openclaw/secrets/vikunja-api.kent-pre-felix-bot.bak`
(matches `swap_vikunja_secrets.py:DEFAULT_SECRETS_PATH +
DEFAULT_BAK_SUFFIX`).

Not a Vikunja API quirk — a helper-defaults defect. Listed here
because it shares the same root cause (mock-only tests never exercised
the path defaults end-to-end) and the same lesson (defaults that
encode environment assumptions need at least one live invocation).

Fixed in `6753184` (closes
[#316](https://github.com/kentonium3/kg-automation/issues/316)).

### Why these slipped past pytest

All five defects are invisible to the pytest-mock-only pattern used in
`tests/vikunja/`: mocks accept whatever HTTP method, field names, and
payload types the helper sends, so the tests validate the helper
against itself rather than against the Vikunja server. The pattern is
right for helper logic (idempotency, atomicity, exit codes) but
provides no signal on API contract correctness.

Per [#317](https://github.com/kentonium3/kg-automation/issues/317),
this gap is acknowledged and accepted: future Vikunja helpers should
treat live integration as the contract test of record, and this
appendix should be checked first whenever a v0.24.6 helper is touched.

---

## Glossary

- **`done_at`** — Vikunja Task field. ISO 8601 timestamp of the most
  recent transition from `done=false` to `done=true`. Scalar
  (overwritten each completion). Zero sentinel: `0001-01-01T00:00:00Z`.
- **`repeat_after`** — Vikunja Task field. Integer seconds. Interval
  for `repeat_mode=0` and `repeat_mode=2`.
- **`repeat_mode`** — Vikunja Task field. Integer 0/1/2 = default
  (interval) / month / from-current-date.
- **Pseudo-project** — Vikunja project with a negative ID exposing a
  built-in filter. `-2` = Today, `-3` = Upcoming, `-4` = Overdue,
  `-1` = Favorites, `-5` = Goals.
- **View** — Per-project saved configuration. Each project has
  default `List`, `Gantt`, `Table`, `Kanban` views; each holds a
  `filter` expression and rendering preferences.
- **Identity label** — One of three Vikunja labels (`personal`,
  `intentional`, `metalcasework`) that every agent-created task must
  carry. Required-business-rule per `vikunja-api` skill.
- **Felix comment prefix** — `[Felix]` for habits/enrichment and
  `[Felix-Escalation]` for escalation. Marker that the comment was
  written by an agent rather than by Kent in the UI.
