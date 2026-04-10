---
title: Vikunja Date Handling
doc_type: runbook
status: approved
audience: agents_and_humans
last_updated: '2026-04-10'
revision: v1.0
---

# Vikunja date handling

How Felix agents handle dates when creating tasks in Vikunja, and why
this is non-trivial. office2 runs in UTC, the user lives in Eastern
time, and Vikunja stores everything in UTC. Getting these layers wrong
produces "task is overdue at 7 AM" and "tomorrow becomes today" bugs.

This runbook is the durable record of the two bugs that produced GitHub
issue #112 and the conventions we adopted to prevent recurrence. For
the full investigation, see
[`kitty-specs/025-vikunja-date-timezone-bug/research.md`](../../kitty-specs/025-vikunja-date-timezone-bug/research.md).

## The two bugs that caused #112

Issue #112 reported two seemingly unrelated symptoms:

1. Daily habit tasks consistently appeared "some seemingly random
   number of hours overdue" the moment the morning cron created them.
2. A "tomorrow" task captured in the evening sometimes landed on the
   wrong day.

Mission 025 traced these to two distinct root causes.

### Bug A — Midnight anchor (habits symptom)

**Location**: `/data/services/openclaw/habits-agent/AGENTS.md`

The habits agent template anchored every daily task to midnight at the
**start** of the day in ET:

```
{"due_date": "<YYYY-MM-DD>T00:00:00<ET_OFFSET>"}
```

When the morning cron fired at 7:05 AM ET and created the task, the
"due moment" had already passed seven hours earlier. Vikunja's overdue
filter and Today view correctly flagged the task as past due. The
"random hours" the user perceived was simply how far into the day each
view was loaded.

### Bug B — Skill / USER.md conflict (tasker symptom)

**Location**: `~/.openclaw/skills/vikunja-api/SKILL.md`

`USER.md` for both tasker and habits told agents:

> Never use the `Z` (UTC) suffix for due dates — it causes off-by-one
> errors for evening task creation.

But the canonical curl example in the `vikunja_api` skill showed:

```json
{"due_date": "2026-04-15T00:00:00Z"}
```

Agents that read the skill for API syntax (which is exactly what they
should do) copied the `Z` example. Result: an evening "tomorrow" date
computed correctly in ET (e.g., `2026-04-11`) was then formatted as
`2026-04-11T00:00:00Z`, which is `2026-04-10T20:00:00-04:00` — 8 PM
*today* in ET. The date silently shifted backwards by one day for any
late-evening capture.

## The fix

### For daily / recurring tasks (habits)

Use `T23:59:59<ET_OFFSET>` — **end of day in ET**. The task is "due by
the end of the day" rather than "due at the start of the day", which
matches natural user expectation for daily habits. It only flips to
overdue after midnight ET, when the day is genuinely over.

### For one-off tasks with explicit dates (tasker, capture)

Use the explicit date parsed from the inbox note (e.g., "April 15"
→ `2026-04-15T...`). The midnight-vs-end-of-day convention for one-off
tasks is left to the agent's judgement based on the task type — what
matters is that the **date** is right and the format uses an ET offset.

### For relative dates ("tomorrow", "next week")

Resolve the relative date in ET, never in UTC:

```bash
TZ=America/New_York date +%F                    # today in ET
TZ=America/New_York date -d 'tomorrow' +%F      # tomorrow in ET
```

office2 runs in UTC. Without the `TZ` prefix, `date` after 8 PM ET will
return the next calendar day, which is exactly the bug we just fixed.

### Timezone format rule

**Always use an explicit ET offset** for task creation:

- EDT (March–November): `-04:00`
- EST (November–March): `-05:00`

**Never** use the `Z` (UTC) suffix when creating Vikunja tasks. Vikunja
will store the task in UTC internally regardless — that's fine and
correct — but the agent must write the offset so that "midnight in ET"
actually means midnight in ET and not midnight in UTC (which is 8 PM
ET the previous day).

To get the current offset dynamically and survive DST transitions:

```bash
TZ=America/New_York date +%:z                   # → -04:00 or -05:00
```

## DST transition behavior

The dynamic offset lookup above handles DST automatically. **Do not
hardcode** `-04:00` or `-05:00` anywhere in agent prompts, skill
examples, or scripts. On transition Sundays the wrong literal will
silently produce a one-hour skew until someone notices.

The day-of-the-week behavior is unchanged across DST: "tomorrow in ET"
is always the next ET calendar day, regardless of whether ET is
currently EDT or EST. The offset only affects how the timestamp is
serialized.

## How to verify correct behavior

Use this recipe to verify any agent run that creates a task with a
due date.

1. **Trigger the run** that creates the task. Example for the inbox
   capture cron:

   ```bash
   ssh office2-claude "openclaw cron run cc9977fa-e451-47e7-9a18-eb6d85775f26"
   ```

2. **Find the task** by name or recency in Vikunja:

   ```bash
   ssh office2-claude 'curl -s \
     -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
     "https://office2.tail0f5f56.ts.net/api/v1/tasks/all?filter=done%20%3D%20false&per_page=20" \
     | python3 -c "import json,sys; tasks=json.load(sys.stdin); print(json.dumps([{k:t.get(k) for k in [\"id\",\"title\",\"due_date\"]} for t in tasks][:5], indent=2))"'
   ```

3. **Pull the specific task by id** to confirm the stored value:

   ```bash
   ssh office2-claude 'curl -s \
     -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
     "https://office2.tail0f5f56.ts.net/api/v1/tasks/<TASK_ID>" \
     | python3 -m json.tool | grep -E "title|due_date|created"'
   ```

4. **Convert UTC back to ET** to verify the date matches what the user
   expected. The stored value will look like `2026-04-11T04:00:00Z` —
   subtract the current ET offset (`-04:00` in EDT) to confirm it
   represents `2026-04-11T00:00:00-04:00` (midnight April 11 EDT) or
   `2026-04-11T03:59:59Z` for the end-of-day convention.

5. **Inspect the agent session** to see what the agent literally sent:

   ```bash
   ssh office2-claude 'ls -t /home/claude/.openclaw/agents/<AGENT>/sessions/*.jsonl \
     | head -1 | xargs grep -o "due_date[^,}]*" | head -5'
   ```

   The string the agent sent must contain an offset (`-04:00` or
   `-05:00`), not `Z`.

## Source files affected by these fixes

| Layer | File | Fix |
|---|---|---|
| Skill (canonical example) | `~/.openclaw/skills/vikunja-api/SKILL.md` | Replaced `Z` example with ET offset example, added warning |
| Habits agent template | `/data/services/openclaw/habits-agent/AGENTS.md` | Changed `T00:00:00<ET_OFFSET>` → `T23:59:59<ET_OFFSET>` |
| Repo copy of habits | `scripts/openclaw/agents/felix-admin-habits/AGENTS.md` | Same change, kept in sync |
| User instructions | `*/USER.md` (tasker, habits) | Already correct — left unchanged |

The skill is the canonical source of API syntax for every agent that
touches Vikunja. Future Vikunja API changes should be made there first.

## History

- **2026-04-10** — Mission 025 (`kitty-specs/025-vikunja-date-timezone-bug/`)
  identified both bugs and shipped both fixes. Closes
  [#112](https://github.com/kentonium3/kg-automation/issues/112).
  - WP01: Fixed `vikunja_api` skill canonical example to use the ET
    offset instead of `Z`.
  - WP02: Changed habits agent due_date template from `00:00:00` to
    `23:59:59` (end of day in ET).
  - WP03: Verified end-to-end with a live evening "tomorrow" capture.
    Test note `Inbox 2026-04-09 2115-test025.md` → Vikunja task #43
    with `due_date: 2026-04-11T00:00:00-04:00`. ET offset present, date
    correct, no `Z` format. See
    [`kitty-specs/025-vikunja-date-timezone-bug/research.md`](../../kitty-specs/025-vikunja-date-timezone-bug/research.md)
    for the full evidence trail.
