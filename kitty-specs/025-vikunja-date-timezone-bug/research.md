# Phase 0 Research — Vikunja Date Timezone Bug

**Feature**: 025-vikunja-date-timezone-bug
**Source**: GitHub issue #112
**Research date**: 2026-04-10

This document captures the investigation findings that informed `plan.md`. All evidence gathered from live system inspection.

---

## Investigation Layers Checked

### Layer 1: office2 system timezone

**Command run:** `timedatectl` on office2

**Output:**
```
Local time: Fri 2026-04-10 17:09:49 UTC
Universal time: Fri 2026-04-10 17:09:49 UTC
Time zone: Etc/UTC (UTC, +0000)
```

**Also checked:**
- `/etc/timezone` → `Etc/UTC`
- `echo $TZ` as claude user → (empty)
- `date` → returns UTC time

**Finding:** System timezone is UTC. The `claude` user has no `TZ` env variable, so `date` in agent scripts returns UTC.

### Layer 2: Agent USER.md timezone guidance

**File:** `/data/services/openclaw/tasker-agent/USER.md`
**File:** `/data/services/openclaw/habits-agent/USER.md`

**Both files contain:**
```
When setting due_date via the Vikunja API, use the ET offset:
- EDT (March–November): 2026-04-09T00:00:00-04:00
- EST (November–March): 2026-01-15T00:00:00-05:00

Never use the Z (UTC) suffix for due dates — it causes off-by-one errors
for evening task creation.
```

**Finding:** USER.md clearly instructs agents to use ET offset and explicitly forbids the `Z` suffix. Both tasker and habits have this guidance.

### Layer 3: Habits agent AGENTS.md date logic

**File:** `/data/services/openclaw/habits-agent/AGENTS.md` lines 49-95

**Relevant snippets:**
```
today's date in YYYY-MM-DD format. **Use Eastern time, not UTC:**
TZ=America/New_York date +%F    # YYYY-MM-DD

office2 runs in UTC. Without the `TZ` prefix, dates after 8 PM ET will
return the next calendar day.
```

And for due_date:
```
{"due_date": "<YYYY-MM-DD>T00:00:00<ET_OFFSET>"}
```

**Finding:** AGENTS.md has detailed, correct step-by-step instructions. The template uses `<YYYY-MM-DD>T00:00:00<ET_OFFSET>` — note the `00:00:00` (midnight).

### Layer 4: vikunja_api skill documentation

**File:** `~/.openclaw/skills/vikunja-api/SKILL.md` lines 155-165

**Content:**
```bash
curl -s -X PUT \
  -H "Authorization: Bearer $(cat /data/services/openclaw/secrets/vikunja-api)" \
  -H "Content-Type: application/json" \
  -d '{"title": "TASK_TITLE", "description": "DESCRIPTION", "due_date": "2026-04-15T00:00:00Z", "priority": 1}' \
  https://office2.tail0f5f56.ts.net/api/v1/projects/PROJECT_ID/tasks
```
- `due_date` must be ISO 8601 format (e.g., `2026-04-15T00:00:00Z`)

**Finding:** **The skill's canonical example uses the `Z` (UTC) suffix** — directly contradicting USER.md's "never use Z" instruction. The description says "ISO 8601" which technically includes both `Z` and offset formats, but the example shows `Z`. An agent reading the skill for API syntax gets the UTC example.

### Layer 5: Actual session traces — what agents sent

**Habits session today** (`96352590-a3c1-4ce1-b4b0-e80385e02d32.jsonl`, 2026-04-10 morning run):

Grepping for due_date values in the session shows:
```
due_date\": \"2026-04-10T00:00:00-04:00\"
```

**Finding:** Today's habits run actually sent the **correct** ET offset format. The instructions are being followed... at least for this run.

**Tasker session** (`c02399cf-ba24-4be9-8a84-3f88196c1d6a.jsonl`):
```
due_date\": \"2026-04-15T00:00:00Z\"
```

**Finding:** Tasker sent the **UTC Z format** — the vikunja_api skill's example verbatim. This is the inconsistency: tasker followed the skill, habits followed USER.md.

### Layer 6: How Vikunja stores and displays the value

**API query** for habit task #16 (Morning shoulder PT):
```
"title": "Morning shoulder PT",
"done": true,
"done_at": "2026-04-10T15:03:43Z",
"due_date": "2026-04-10T04:00:00Z"
```

**Finding:** The agent sent `2026-04-10T00:00:00-04:00`. Vikunja stored it as `2026-04-10T04:00:00Z` — that's the **same moment in time**, just expressed in UTC. The conversion is correct.

**BUT** the stored moment is midnight at the START of April 10 EDT. A user opening Vikunja at 7:05 AM EDT (when the cron fires the check-in) sees a task that was "due" 7+ hours ago.

### Layer 7: Git history of previous fix attempts

**Search:** `git log --oneline --all | grep -iE "timezone|tz|date|#112"` (candidate)

Not yet executed during research phase — will confirm in implementation.

---

## Root Cause Analysis

There are **two distinct bugs** that together produce the observed symptoms:

### Bug A — Midnight anchor convention (habits symptom)

**Location:** `/data/services/openclaw/habits-agent/AGENTS.md` line 85

The template is:
```
{"due_date": "<YYYY-MM-DD>T00:00:00<ET_OFFSET>"}
```

This anchors the task to **midnight at the START of the day** in ET. When the morning cron fires at 7:05 AM ET, the task has been "due" for 7 hours. Vikunja's Today view and any overdue filter will correctly flag it as overdue.

**The user-visible symptom:** "habit tasks show as due a day ago" (issue #112 wording) or "some seemingly random number of hours overdue" (Kent's updated description).

**The actual behavior:** The task is set to midnight ET. Any time after that on the same day is "past the due moment."

**Why it looks random:** Because the overdue hours grow as the day progresses — 7 hours at 7 AM, 14 hours at 2 PM, etc. Kent perceives this as random.

### Bug B — vikunja_api skill/USER.md conflict (tasker symptom)

**Location:** `~/.openclaw/skills/vikunja-api/SKILL.md` line 159

The skill's concrete example uses `"2026-04-15T00:00:00Z"` — the UTC `Z` suffix. USER.md tells agents to never use Z. Agents reading the skill for API syntax copy the example and produce UTC-anchored dates.

**Effect for tasker:** If the agent computes "tomorrow" correctly in ET (e.g., "2026-04-11") but then formats it as `"2026-04-11T00:00:00Z"` (UTC midnight), that's actually `2026-04-10T20:00:00-04:00` — **8 PM today in ET**. If Kent said "tomorrow" at 10 PM ET, he expected a deadline the next day, and he got one that's already 2 hours past.

This matches the #112 symptom description: "due tomorrow in an evening ET message" creates a task with the WRONG date.

### Why previous fixes didn't resolve the issue

The investigation strongly suggests that previous fix attempts updated the USER.md or AGENTS.md text while leaving the vikunja_api skill's canonical example unchanged. Agents that read the skill's example (as they should, to get correct API syntax) would continue to produce UTC-anchored dates, making the fix appear to work intermittently depending on which source the agent weighted.

Additionally, Bug A (midnight anchor) may not have been recognized as a separate bug. If the fix focused only on the timezone format, the midnight anchor would still produce the "overdue" appearance.

---

## Design Implications for the Plan

**Fix A (midnight anchor):** Change the habits agent's due_date convention from midnight (00:00:00) to end-of-day (23:59:59) in ET. This means the task is "due by the end of the day" rather than "due at the start of the day", matching natural user expectation for daily tasks.

**Fix B (skill/USER.md conflict):** Update the vikunja_api skill's example to use the ET offset format. Ideally, the skill should show BOTH a naive date example AND an explicit-offset example, with a note about when to use each. This makes the skill self-consistent with USER.md.

**Fix C (tasker end-to-end trace):** Before declaring Bug B fixed, run an end-to-end trace of tasker with an evening "tomorrow" scenario and verify the resulting Vikunja task has the correct due date. We have NOT yet verified this during research — it must be done during implementation.

**Optional consideration:** Should the skill also include a `TZ=America/New_York` prefix in date-calculating commands? The habits agent already does this, but the tasker doesn't appear to. This is a potential third fix point to consider during implementation.

---

## Open Questions (resolved during implementation)

1. Does the tasker actually compute "tomorrow" correctly in ET before formatting? → Check during FR-001 end-to-end trace
2. Does the fix for Bug A (end-of-day) have any unintended side effects for Vikunja's Today filter or reminder notifications? → Check Vikunja docs or test empirically
3. Are there other agents using the vikunja_api skill that also need updates? → Check which agents read the skill during FR-003

---

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Research tool | Direct SSH + grep + API query | Cheapest possible verification; no reliance on agent-side reasoning |
| Root cause confirmation threshold | Two confirmed bugs with evidence; third suspected bug trace TBD | Enough to proceed with confidence; trace verification baked into FR-001 |
| Fix layering | Both the skill (canonical) and the habits AGENTS.md (convention) | Skill fix prevents recurrence; AGENTS.md fix addresses the midnight anchor |
| Alternatives considered | System timezone change (Tier 0, needs sudo, rejected) | Agents already have ET-aware tooling; system-level change is unnecessary and higher-risk |

---

**END OF RESEARCH**
