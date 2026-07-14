---
name: escalation
description: Detect overdue and at-risk tasks in Vikunja and deliver level-appropriate escalation alerts via WhatsApp. Tracks escalation state via per-project JSONL state-log files. Handles Kent's responses (done, snooze, dismiss, reschedule, acknowledge).
version: 2.0.0
---

# Escalation Skill

This skill defines the complete escalation model for the felix-admin-escalation
agent. It is self-contained — apply the full escalation workflow by reading
this skill alone.

**API Base URL**: `https://office2.tail0f5f56.ts.net/api/v1`
**API Token**: `cat /data/services/openclaw/secrets/vikunja-api`

---

## 0. State Source

The canonical state for escalation is per-project JSONL state-log files.
The agent reads state via `scripts/escalation/derive_state.py` and writes
events via `scripts/escalation/record_completion.py`. JSONL is the sole
substrate.

---

## 1. Escalation Criteria

### Mechanism (how these criteria are applied)

The date/priority/project slice of this section — everything under "What
qualifies for escalation" except the snooze/dismiss lines — is enumerated
deterministically by `scripts/escalation/enumerate_candidates.py`
(invoked by the agent as `python3 -m scripts.escalation.enumerate_candidates`;
see AGENTS.md "Tick workflow" Step 2). Its output is a set of
**pre-candidates**: tasks that clear the date/priority/project bar, before
lifecycle state is considered. The snooze/dismiss/level eligibility lines
below are NOT evaluated by that helper — they are applied per-candidate by
`derive_state` (§2), which the agent calls for each pre-candidate and
which alone determines whether an alert is actually sent
(`next_eligible_level != null`). This section's wording remains the
authoritative source of truth for the criteria themselves; the helper is
the mechanism, not a separate rule set.

### What qualifies for escalation

A task qualifies if ALL of the following are true:
- `done = false`
- `priority >= 2` (medium=2, high=3, urgent=4)
- `project_id` is NOT 13 (Habits)
- The task is overdue (`due_date < today`) OR due today with `priority >= 3`
- The task is not currently snoozed (snooze window not expired)
- The task is not dismissed (unless `due_date` was updated after the dismiss)

### What does NOT qualify

- Done tasks (`done = true`) — never escalated
- Low priority tasks (`priority = 1`) or unset priority (`priority = 0`)
- Tasks in the Habits project (ID 13) — managed by felix-admin-habits
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

## 2. Level Determination via JSONL State

For each candidate task, invoke the `derive_state` CLI helper to get
current state:

    python3 -m scripts.escalation.derive_state \
      --task-id <id> --project-id <pid>

Parse stdout JSON. The `next_eligible_level` field tells you which level (if
any) to send this tick.

### Policy rules (encoded in derive_state)

| `current_state` | `next_eligible_level` | Agent action |
|-----------------|----------------------|--------------|
| `new` | 1 or 2 (per §1) | Send the indicated level if task qualifies |
| `level_1_sent` | `null` | Skip — Level 1 active, not yet stale |
| `level_1_sent` | `2` | Send Level 2 (Level 1 was sent 2+ days ago, no response) |
| `level_2_sent` | `2` | Send Level 2 again (daily dedup at §7 applies) |
| `snoozed` | `null` | Skip — snooze window active |
| `snoozed_expired` | `1` | Re-enter at Level 1 |
| `rescheduled` | per §1 | Re-evaluate via §1 against the new due_date |
| `done` | `null` | Skip — terminal |
| `dismissed` | `null` | Skip — terminal (unless due_date updated after dismiss) |

### Level model (mapped to current_state transitions)

| Level | Name | Trigger |
|-------|------|---------|
| 1 | Nudge | Task overdue 1–3 days with no prior escalation, OR due today with priority >= 3 |
| 2 | Insistence | Task overdue >3 days, OR Level 1 sent 2+ days ago with no response |

### Error handling

On `EscalationStateError` (exit code 3): `derive_state` has filed a P2-bug
automatically. Skip this task; continue with others. Do NOT attempt to retry.

---

## 3. Escalation State Format

**Canonical state**: per-project JSONL at
`/data/services/openclaw/state/escalation/project-<id>-escalation-history.jsonl`.

See `kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/data-model.md`
for the record schema.

### Writes — invoke `record_completion`

All escalation events (level sent, snooze, dismiss, done, reschedule) flow
through the `record_completion` CLI. For `done` and `rescheduled` events
it performs the Vikunja task PATCH FIRST and the JSONL append SECOND, per
research D6. For `level_sent`, `snoozed`, and `dismissed` events the
JSONL append is the sole side-effect.

    python3 -m scripts.escalation.record_completion \
      --task-id <id> --project-id <pid> --title "<task title>" \
      --date <YYYY-MM-DD> --state <event_type> --source <agent|kent_reply> \
      [--level N | --snooze-days N | --reschedule-to YYYY-MM-DD] \
      [--reason "..."] [--note "..."] [--idempotent]

### Valid `--state` values

`level_sent`, `snoozed`, `dismissed`, `done`, `rescheduled`.

### Valid `--source` values

`agent` (agent-initiated, e.g. level_sent), `kent_reply` (response handling
in §5), `reconcile` (synthetic from reconcile_completions — agents do not
emit this directly), `backfill` and `operator_repair` (operator use).

### Per-state flag pairing

| `--state` | Required additional flag |
|-----------|--------------------------|
| `level_sent` | `--level N` (1 or 2) |
| `snoozed` | `--snooze-days N` |
| `rescheduled` | `--reschedule-to YYYY-MM-DD` |
| `dismissed` | (optional `--reason "..."`) |
| `done` | (optional `--reason "..."`) |

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success (Vikunja + JSONL write OK) |
| 1 | Validation error (bad flags / state transition rejected) |
| 2 | Vikunja side-effect failed (no JSONL write performed) |
| 3 | Hard-fail; P2-bug filed; agent should skip this task |

### Idempotency

Pass `--idempotent` whenever a retry could re-deliver the same
(task_id, date, state) triple — the helper pre-checks for a duplicate
JSONL record and no-ops on hit.

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

When Kent replies to an escalation message, parse his WhatsApp reply text
and route each task event through `record_completion`. The skill still
parses Kent's reply (his patterns are unchanged); it no longer writes
state into Vikunja comments directly.

| Pattern | Action |
|---------|--------|
| `N done` | Mark task #N complete: `POST /api/v1/tasks/{id}` with `{"done": true}`. Then `record_completion --state done --source kent_reply`. |
| `N snooze` | `record_completion --state snoozed --snooze-days 1 --source kent_reply` (default N=1). |
| `N snooze Nd` | `record_completion --state snoozed --snooze-days N --source kent_reply`. |
| `N dismiss` | `record_completion --state dismissed --source kent_reply`. Leave task open. |
| `move N to <date>` or `N move to <date>` | Parse the date. Confirm with Kent. Then `record_completion --state rescheduled --reschedule-to YYYY-MM-DD --source kent_reply` — the helper performs the Vikunja `due_date` PATCH (end-of-day ET) itself; do NOT write `due_date` separately. |
| `N and M done` | Mark multiple tasks complete. Process each independently — one `record_completion` invocation per task. |
| `all snooze Nd` | Apply snooze to every task in the message — one `record_completion` invocation per task. |
| `got it` or vague acknowledgment | No task mutation. No per-task `record_completion`. If a Level 2 task exists, it stays at Level 2 but won't re-alert today (daily dedup per §7). |
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

### Idempotency on retries

When a `record_completion` invocation could be retried (e.g. transient
Vikunja error), pass `--idempotent` so the helper skips duplicate
(task_id, date, state) writes.

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
