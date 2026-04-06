---
name: escalation
description: Detect overdue and at-risk tasks in Vikunja and deliver level-appropriate escalation alerts via WhatsApp. Tracks escalation state via structured task comments. Handles Kent's responses (done, snooze, dismiss, reschedule, acknowledge).
version: 1.0.0
---

# Escalation Skill

This skill defines the complete escalation model for the felix-admin-escalation
agent. It is self-contained — apply the full escalation workflow by reading
this skill alone.

**API Base URL**: `https://office2.tail0f5f56.ts.net/api/v1`
**API Token**: `cat /data/services/openclaw/secrets/vikunja-api`

---

## 1. Escalation Criteria

### What qualifies for escalation

A task qualifies if ALL of the following are true:
- `done = false`
- `priority >= 2` (medium=2, high=3, urgent=4)
- `project_id` is NOT 11 (Goals) and NOT 13 (Habits)
- The task is overdue (`due_date < today`) OR due today with `priority >= 3`
- The task is not currently snoozed (snooze window not expired)
- The task is not dismissed (unless `due_date` was updated after the dismiss)

### What does NOT qualify

- Done tasks (`done = true`) — never escalated
- Low priority tasks (`priority = 1`) or unset priority (`priority = 0`)
- Tasks in the Habits project (ID 13) — managed by felix-admin-habits
- Tasks in the Goals project (ID 11) — goals are anchors, not tasks
- Tasks with no `due_date` (null sentinel `0001-01-01T00:00:00Z`)

### Priority values

| Value | Meaning | Escalated? |
|-------|---------|-----------|
| 0 | Unset | No |
| 1 | Low | No |
| 2 | Medium | Yes |
| 3 | High | Yes |
| 4 | Urgent | Yes |

---

## 2. Escalation Level Model

| Level | Name | Trigger |
|-------|------|---------|
| 1 | Nudge | Task overdue 1–3 days with no prior escalation, OR due today with priority >= 3 |
| 2 | Insistence | Task overdue >3 days, OR Level 1 sent 2+ days ago with no response |

### Level determination algorithm

For each qualifying task, read its `[Felix-Escalation]` comments (most recent
first) and apply these rules in order:

1. **No escalation comment exists**:
   - Overdue 1–3 days → Level 1
   - Overdue >3 days → Level 2
   - Due today (priority >= 3) → Level 1

2. **Most recent comment is `level-1 | sent`**:
   - Sent 2+ days ago AND no subsequent `acknowledged` comment → Level 2
   - Sent <2 days ago → skip (Level 1 already active, not yet stale)

3. **Most recent comment is `level-2 | sent`**:
   - Sent today → skip (daily deduplication — max one Level 2 per day)
   - Sent before today → Level 2 (repeat the insistence)

4. **Most recent comment is `snoozed:Nd | acknowledged`**:
   - Parse the snooze: comment date + N days = expiry date
   - If expiry date <= today → snooze expired, re-enter at Level 1
   - If expiry date > today → skip (snooze active)

5. **Most recent comment is `dismissed | acknowledged`**:
   - Check if task's `due_date` is later than the comment date
   - If yes → due date was updated (rescheduled), reset: treat as Level 1
   - If no → permanently suppressed, skip

6. **Most recent comment is `done | acknowledged`**:
   - Skip (task was marked done via escalation)

7. **Most recent comment is `rescheduled:YYYY-MM-DD | acknowledged`**:
   - Escalation history reset — if the new due date has passed, treat as
     newly overdue (no prior escalation)

---

## 3. Escalation Comment Format

**Prefix**: `[Felix-Escalation]`
**Delimiter**: ` | ` (space-pipe-space)
**Fields**: `date | state | disposition`

### Escalation sent (written after alert delivery)

```
[Felix-Escalation] 2026-04-06 | level-1 | sent
[Felix-Escalation] 2026-04-06 | level-2 | sent
```

### Response recorded (written after Kent responds)

```
[Felix-Escalation] 2026-04-06 | snoozed:3d | acknowledged
[Felix-Escalation] 2026-04-06 | dismissed | acknowledged
[Felix-Escalation] 2026-04-06 | done | acknowledged
[Felix-Escalation] 2026-04-06 | rescheduled:2026-04-10 | acknowledged
```

### Parsing rules

- Split on ` | ` to get `[date, state, disposition]`
- Date is always `YYYY-MM-DD`
- State tokens: `level-1`, `level-2`, `snoozed:Nd`, `dismissed`, `done`,
  `rescheduled:YYYY-MM-DD`
- Disposition: `sent` (agent initiated) or `acknowledged` (Kent responded)
- `snoozed:Nd` — N is an integer, d is literal (e.g., `snoozed:3d`)
- `rescheduled:YYYY-MM-DD` — the new due date

### Rules

- Comments are **append-only** — never modify or delete existing comments
- Only the **most recent** `[Felix-Escalation]` comment determines state
- Use `GET /api/v1/tasks/{id}/comments` to read; scan for prefix `[Felix-Escalation]`
- Use `PUT /api/v1/tasks/{id}/comments` with `{"comment": "..."}` to write

---

## 4. WhatsApp Message Format

### Combined message structure

```
🔴 Tasks slipping:

1. [Project] Task name — N days overdue

⚠️ Tasks needing attention:

2. [Project] Task name — N days overdue
3. [Project] Task name — due today (high priority)

Reply: "1 done", "2 snooze 3d", "3 dismiss",
"2 move to friday", or "all snooze 2d"
```

### Rules

- Level 2 tasks listed FIRST with `🔴 Tasks slipping:` header
- Level 1 tasks listed AFTER with `⚠️ Tasks needing attention:` header
- If only one level exists, use only that header
- Each task line: `N. [Project Name] Task title — N days overdue`
  (or `due today (high priority)` for today-due tasks)
- Numbers are sequential across both levels (1, 2, 3... continuous)
- Cap at **7 tasks total**. If more exist, add: `(+N more in Vikunja Overdue filter)`
- Include response prompt at the end
- If no tasks qualify, send **nothing** — silent run

### Resolving project names

Use `GET /api/v1/projects/{project_id}` to get the project title for
each task. Cache project names within a single run to avoid redundant calls.

---

## 5. Response Parsing

When Kent replies to an escalation message, parse the response:

| Pattern | Action |
|---------|--------|
| `N done` | Mark task #N complete: `POST /api/v1/tasks/{id}` with `{"done": true}`. Write `done \| acknowledged` comment. |
| `N snooze` | Snooze task #N for 1 day (default). Write `snoozed:1d \| acknowledged` comment. |
| `N snooze Nd` | Snooze task #N for N days. Write `snoozed:Nd \| acknowledged` comment. |
| `N dismiss` | Write `dismissed \| acknowledged` comment. Leave task open. |
| `move N to <date>` or `N move to <date>` | Parse the date. Confirm with Kent. Update `due_date` via `POST /api/v1/tasks/{id}`. Write `rescheduled:YYYY-MM-DD \| acknowledged` comment. |
| `N and M done` | Mark multiple tasks complete. Process each independently. |
| `all snooze Nd` | Apply snooze to every task in the message. |
| `got it` or vague acknowledgment | Write acknowledgment: no specific comment per task. If a Level 2 task exists, it stays at Level 2 but won't re-alert today (deduplication). |
| Ambiguous or unrecognized | Ask ONE clarifying question. Do not guess. |

### Date parsing for reschedule

- `friday` → next Friday from today
- `next monday` → next Monday from today
- `april 10` → 2026-04-10
- Always confirm the parsed date before executing the update

### Task number resolution

Numbers map to positions in the message **as sent**. The agent must
remember the task-to-number mapping from the most recent escalation
message in this session.

---

## 6. Error Handling

### Vikunja unavailable

- Log the error. Do NOT send "nothing overdue" to WhatsApp — silence is
  better than a false negative.
- Do NOT write escalation comments if the alert was never delivered.
- Report the error in the cron run output.

### Comment write failure

- Log which task failed. Continue processing remaining tasks.
- Report the failure in the run output.

### WhatsApp delivery failure

- Do NOT write escalation comments to tasks — state should reflect what
  Kent actually received.
- Log the failure.

### Task completed between detection and alert

- Re-check `done` status before sending. If `done = true`, skip silently.

---

## 7. Daily Deduplication

Before sending a Level 2 alert for a task, check if a `level-2 | sent`
comment already exists with today's date. If so, skip that task — max
one Level 2 alert per task per calendar day.

Level 1 alerts follow the same rule — if `level-1 | sent` exists with
today's date, skip.

---

**END OF SKILL**
