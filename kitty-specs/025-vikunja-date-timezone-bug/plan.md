# Implementation Plan: Vikunja Date Timezone Bug Fix

**Branch**: `main` | **Date**: 2026-04-10 | **Spec**: [spec.md](spec.md)
**Input**: [spec.md](spec.md), [research.md](research.md)
**Source Issue**: #112

## Summary

Two distinct bugs produce the #112 symptoms. Both are confirmed with evidence (see `research.md`):

**Bug A — Midnight anchor:** Habits agent sets `due_date` to midnight ET at the START of the day, so tasks appear overdue from 7:05 AM onward.

**Bug B — Skill/USER.md conflict:** The `vikunja_api` skill's example uses `"2026-04-15T00:00:00Z"` (UTC suffix) while USER.md says "never use Z." Agents that read the skill for API syntax copy the UTC format, producing off-by-one dates for evening task creation.

The fix has three parts: update the skill's example to use ET offset (prevents recurrence across all agents), change the habits agent's `due_date` convention from midnight to end-of-day (fixes the overdue-all-day symptom), and add a trace verification for the tasker symptom (confirms Bug B root cause for the tasker path specifically).

## Technical Context

**Platform**: office2 (Ubuntu 24.04 LTS) via `ssh office2-claude`
**Languages**: Markdown (AGENTS.md, USER.md, SKILL.md) and shell (curl examples) — no code changes
**Tools**: Standard shell, `curl`, `jq`, Vikunja REST API
**Change control tier**: Tier 3 (agent prompts / skill docs) — no backup required, no system-level changes
**Testing**: Empirical — real agent runs, real Vikunja API calls, verified via API query and UI

## Research Findings

See `research.md` for the full evidence trail. Key facts:

| Question | Answer | Source |
|---|---|---|
| office2 system timezone | `Etc/UTC` | `timedatectl` |
| claude user `$TZ` | (unset) | SSH inspection |
| USER.md timezone guidance | Correct — says use ET offset | Both agent workspaces |
| habits AGENTS.md date step | Correct — uses `TZ=America/New_York date` | Line 49-95 |
| vikunja_api skill example | **Wrong** — uses `"2026-04-15T00:00:00Z"` | Line 159 |
| habits today's actual send | `"2026-04-10T00:00:00-04:00"` — correct format | Session 96352590 |
| habits task stored in Vikunja | `"2026-04-10T04:00:00Z"` = midnight EDT | API query |
| Why "overdue by random hours" | **Midnight anchor** — task "due" at start of day | Derivation from stored value |

## Charter Check

Charter references `test-first` paradigm which is not available in this project's doctrine. For this bug fix mission, testing is empirical (real agent runs + API queries) rather than unit-test-first. This is acceptable because:
- The fix is content changes to markdown instruction files
- There's no code to unit test
- The verification surface is behavioral (agent produces correct output), not functional (function returns correct value)
- FR-004 mandates real end-to-end verification before the mission is considered complete

## Implementation Approach

The mission has a linear fix sequence: update skill → update habits AGENTS.md → verify tasker symptom → verify habits symptom → document.

### Phase 1: Fix the vikunja_api skill (addresses Bug B for all agents)

**File:** `~/.openclaw/skills/vikunja-api/SKILL.md` on office2

**Changes:**

1. Update the task creation example (around line 159) to show the ET offset format:
   ```bash
   -d '{"title": "TASK_TITLE", "description": "DESCRIPTION", "due_date": "2026-04-15T00:00:00-04:00", "priority": 1}' \
   ```

2. Update line 165 to be explicit about timezone:
   ```
   - `due_date` must be ISO 8601 format with explicit timezone offset
     (e.g., `2026-04-15T00:00:00-04:00` for EDT, `-05:00` for EST).
     Never use the `Z` (UTC) suffix — it causes off-by-one errors for
     tasks created in the evening ET.
   ```

3. Add a note about when to use which offset (dynamic resolution):
   ```
   Use `TZ=America/New_York date +%:z` to get the current ET offset
   (`-04:00` during EDT, `-05:00` during EST).
   ```

**Effect:** The canonical skill is self-consistent with USER.md. Any agent reading the skill for API syntax now gets ET-aware guidance.

### Phase 2: Fix the habits end-of-day convention (addresses Bug A)

**File:** `/data/services/openclaw/habits-agent/AGENTS.md` on office2

**Changes:**

Update the due_date template around line 85 from:
```
{"due_date": "<YYYY-MM-DD>T00:00:00<ET_OFFSET>"}
```

to:
```
{"due_date": "<YYYY-MM-DD>T23:59:59<ET_OFFSET>"}
```

Add explanation:
```
Use 23:59:59 (end of day ET), NOT 00:00:00 (start of day). A midnight
anchor causes the task to appear overdue from the moment it's created
(7:05 AM cron fire), because the deadline is already in the past.
End-of-day anchoring means the task stays "on time" throughout the day
and only flips to overdue after midnight ET.
```

**Effect:** Habit tasks no longer appear as "overdue by N hours" when they first show. They remain on time until end-of-day ET.

### Phase 3: Verify tasker symptom with end-to-end trace

**No file changes** — this is a verification step to confirm Bug B's tasker branch.

**Steps:**
1. Create a test inbox note with a "due tomorrow" instruction timestamped in the evening ET (e.g., after 8 PM ET)
2. Trigger felix-admin-capture to process the note
3. Observe what the delegation to tasker produces
4. Look at the Vikunja task the tasker creates
5. Verify the due_date matches the next ET calendar date (not today, not day-after-tomorrow)

**If the trace shows the tasker still produces wrong dates:** there may be a third bug in the tasker agent's date reasoning. In that case, add a corrective instruction to the tasker AGENTS.md or extend the fix. Do not conclude the mission until the trace passes.

### Phase 4: Sync office2 changes to repo

Both the skill and the habits AGENTS.md need to be synced to the repo-side copies:
- `scripts/openclaw/agents/felix-admin-habits/AGENTS.md` (for the habits fix)
- There is no repo-side copy of the vikunja_api skill currently — it lives only in `~/.openclaw/skills/vikunja-api/` on office2. Decision point during implementation: add a repo copy or leave as-is. For MVP, committing the fix as an office2-only change is acceptable, with a note in the fix commit referencing that the skill isn't repo-versioned.

### Phase 5: Verify habits symptom with real run

**Steps:**
1. Wait for or trigger the habits-morning-checkin cron
2. After the run, query one of the habit tasks via the Vikunja API
3. Verify the due_date's stored UTC value corresponds to 23:59:59 EDT (i.e., 03:59:59 UTC the next day), NOT midnight EDT
4. Open Vikunja UI (manual check) and confirm the task appears in Today view, not Overdue view

### Phase 6: Document the root cause and fix

Create `docs/runbooks/vikunja-date-handling.md` (or extend an existing runbook) documenting:
- The two bugs that caused #112
- The midnight anchor rule (why 23:59:59 not 00:00:00)
- The skill/USER.md consistency rule (all canonical examples use offset, never Z)
- How to verify correct behavior if someone suspects a regression
- The DST transition behavior

This prevents future developers from re-introducing either bug.

## Files Modified

### On office2

```
~/.openclaw/skills/vikunja-api/SKILL.md
/data/services/openclaw/habits-agent/AGENTS.md
```

### In kg-automation repo

```
scripts/openclaw/agents/felix-admin-habits/AGENTS.md  (synced from office2)
docs/runbooks/vikunja-date-handling.md                (new — root cause + fix doc)
```

### Possibly modified (TBD during implementation)

```
/data/services/openclaw/tasker-agent/AGENTS.md        (only if Phase 3 trace reveals a tasker-specific bug)
scripts/openclaw/agents/felix-admin-tasker/AGENTS.md  (if above)
```

## Risk Mitigation

| Risk | Mitigation | Phase |
|---|---|---|
| Skill update breaks other agents that reference UTC format | The `Z` format is technically still valid ISO 8601, so existing code that parses the example won't break. Only agents that COPY the example are affected, and they should be updated. | Phase 1 |
| End-of-day convention causes Vikunja's "Today" filter to miss the task | Vikunja typically shows tasks with due_date on the current date regardless of time. Verify empirically in Phase 5. | Phase 5 |
| Tasker trace reveals a third bug not in the current plan | Phase 3 is explicitly a diagnostic step with the authority to extend the fix scope. | Phase 3 |
| DST transition in November breaks the fix | Using `TZ=America/New_York date +%:z` dynamically resolves the correct offset. Hardcoded `-04:00` would break. | Phase 1/2 |
| Vikunja skill has no repo-side copy | For MVP, commit office2 changes only and note this in the commit. Future work can add versioning if needed. | Phase 4 |

## Success Gates

**The mission is not complete until:**
- Both bugs (A and B) have evidence-based root cause documentation in `research.md` (already complete)
- Fixes for both bugs are deployed to office2
- Tasker end-to-end trace (Phase 3) produces a correct due_date
- Habits morning run (Phase 5) produces a task that is NOT immediately overdue
- Durable documentation exists so future contributors can avoid regression
- Mission 023's identity header and mission 022's GitHub routing remain intact (no drift from this mission's changes)

## Branch Contract

- Current branch: `main`
- Planning/base branch: `main`
- Merge target: `main`
- Branch matches target: **true**

---

**PLAN COMPLETE** — Ready for `/spec-kitty.tasks --mission 025-vikunja-date-timezone-bug`

This command ends here per the mandatory stop point. Per auto-drive rule, proceeding to tasks as the next workflow step.
