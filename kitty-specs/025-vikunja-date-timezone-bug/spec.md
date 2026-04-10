# Vikunja Date Timezone Bug Fix

**Feature**: 025-vikunja-date-timezone-bug
**Mission**: software-dev
**Source**: GitHub issue #112 (reopened 2026-04-10)
**Target Branch**: main

---

## Executive Summary

Tasks created in Vikunja by Felix agents (felix-admin-tasker and felix-admin-habits) have incorrect due dates. Daily habit tasks appear already overdue when they first show up each day, and tasker-created tasks described as "due tomorrow" in an evening note land with today's date instead. Both symptoms suggest a UTC/ET timezone mismatch, but multiple previous fix attempts have not resolved the issue.

This mission treats diagnosis as a first-class deliverable: produce a written root-cause analysis with evidence before proposing or applying any fix. The goal is to stop the cycle of plausible-but-incomplete fixes and ground the next attempt in a confirmed understanding of what is actually happening.

Current gaps:

- ❌ Daily habit tasks appear in Vikunja already overdue when they first show
- ❌ Evening-captured "tomorrow" tasks land with today's date
- ❌ Root cause unknown despite multiple previous fix attempts
- ❌ No documented understanding of the date calculation path for future reference

---

## Problem Statement

**Current State:**
```
Date handling in the task creation pipeline
├─ office2 system timezone     → unknown (investigate)
├─ Agent date calculation      → unknown (investigate)
├─ Vikunja API call shape      → unknown (investigate)
├─ USER.md timezone handling   → unknown (investigate)
└─ Cron schedule interpretation → unknown (investigate)
     └─ Symptom: tasks overdue by ~random hours on creation
```

**Target State:**
```
Date handling correctly honors Kent's timezone (America/New_York)
├─ Root cause documented with evidence   ✅
├─ Fix applied at the confirmed layer    ✅
├─ Both symptoms verified resolved       ✅
│  ├─ "Tomorrow" in evening ET → next ET calendar date
│  └─ Daily habit tasks due today (not yesterday)
└─ Documentation prevents regression     ✅
```

---

## Study These Files First

1. **Agent standing orders and tools**
   - Find: `/data/services/openclaw/tasker-agent/AGENTS.md` and `TOOLS.md` on office2
   - Find: `/data/services/openclaw/habits-agent/AGENTS.md` and `TOOLS.md` on office2
   - Study: how these agents calculate dates, what they send to Vikunja, whether USER.md timezone is referenced
   - Repo copies: `scripts/openclaw/agents/felix-admin-tasker/` and `felix-admin-habits/`

2. **Vikunja API skill**
   - Find: the vikunja_api skill used by agents for task creation (`openclaw skills info vikunja_api` on office2)
   - Study: the skill's handling of due dates — does it format them with timezone offset, as naive date strings, as UTC epoch?
   - Note: where the skill lives on office2 and whether its source is in the repo

3. **USER.md and agent identity files**
   - Find: USER.md in each agent workspace on office2
   - Study: whether it specifies Kent's timezone and whether agents are instructed to use it

4. **Cron configurations for habit agents**
   - Find: `habits-morning-checkin` and `habits-weekly-report` cron entries (via `openclaw cron list`)
   - Study: the schedule timezone, when they fire, and what the scheduled run prompt contains

5. **office2 system timezone**
   - Check: `timedatectl` and `/etc/timezone` on office2
   - Check: the `claude` user's environment — is `TZ` set? What does `date` return?

6. **Recent session logs for task creation**
   - Find: recent tasker and habits session JSONL files
   - Study: what date values were sent to Vikunja, what the responses contained
   - Note: look for the actual string values of due dates in the requests

7. **Previous fix attempts**
   - Find: git history referencing #112, timezone, date, or TZ
   - Study: what was tried, why it was believed to fix the issue, what may have been missed

---

## Assumptions

- Kent's timezone is America/New_York (UTC-4 during EDT, UTC-5 during EST)
- office2 is running Ubuntu 24.04 LTS and its system timezone may or may not be set to America/New_York
- Vikunja stores due dates in some canonical form (likely UTC or ISO-8601 with offset); the mismatch is almost certainly in how the agent formats the due date before sending, not in how Vikunja stores it
- Both affected agents (tasker and habits) may have independent date-calculation bugs, OR they may share a common helper/skill that has the bug in one place — the investigation determines which
- Previous fix attempts likely addressed one layer while missing another; the investigation must cover all candidate layers before declaring a fix
- The fix may live in multiple places (agent standing orders + vikunja_api skill + system config); scope is not limited to a single file

---

## Functional Requirements

### FR-001: Diagnose Root Cause with Evidence

| Field | Value |
|---|---|
| **ID** | FR-001 |
| **Status** | Proposed |
| **Priority** | High |

**What it must do:**
- Perform a methodical investigation covering all candidate layers listed in "Study These Files First"
- Capture concrete evidence at each layer: actual command outputs, actual session log content, actual file contents — not assumptions
- Trace a specific task creation from end to end: what date value the agent believed was "today" or "tomorrow" → what value it passed to the vikunja_api skill → what the skill sent to Vikunja → what Vikunja stored → what Kent sees in the UI
- Identify the exact layer where the wrong date gets introduced
- Document the root cause in a diagnosis artifact with quoted evidence

**Business rules:**
- Do NOT propose or apply a fix until the root cause is confirmed with evidence
- Do NOT accept "probably the timezone" as a root cause — specify WHICH calculation in WHICH file gives WHICH wrong value
- If the investigation finds multiple bugs at multiple layers, document all of them

**Success criteria:**
- [ ] Diagnosis artifact exists with: the bug location (file + line + function), the wrong value observed, the correct value expected, and why the error happens
- [ ] At least one real end-to-end trace included as evidence (real task, real values, real logs)
- [ ] All 5 candidate layers from the investigation path checked and results documented
- [ ] If previous fix attempts are identified in git history, explained why they did not fully resolve the issue

---

### FR-002: Design a Fix That Addresses the Root Cause

| Field | Value |
|---|---|
| **ID** | FR-002 |
| **Status** | Proposed |
| **Priority** | High |

**What it must do:**
- Based on the diagnosis from FR-001, design a fix at the correct layer
- The fix must address the confirmed root cause, not adjacent symptoms
- If multiple bugs were found, design fixes for each
- The design considers whether the fix should live in the agent standing orders, the shared vikunja_api skill, environment configuration, or multiple places
- The design accounts for EDT/EST transitions (the fix must work correctly across DST changes)

**Business rules:**
- Prefer fixes at the layer closest to the root cause (e.g., if the bug is in the shared skill, fix the skill — not individual agent prompts)
- Avoid fragile "magic number" offsets; use proper timezone libraries or ISO-8601 with offset where possible
- If the fix involves hardcoding a timezone, document why and where it gets updated if Kent ever moves

**Success criteria:**
- [ ] Fix design is documented with rationale
- [ ] Fix targets the root cause identified in FR-001
- [ ] Design addresses DST transitions
- [ ] Design states where the fix will be applied (agent files, skill, config, etc.)

---

### FR-003: Apply the Fix

| Field | Value |
|---|---|
| **ID** | FR-003 |
| **Status** | Proposed |
| **Priority** | High |

**What it must do:**
- Implement the fix at the layer(s) identified in FR-002
- Keep the change minimal and focused — do not refactor adjacent code
- Update agent files on office2 AND repo copies (keep them in sync)
- If the fix is in the vikunja_api skill, update the skill on office2 and commit the source in the repo if it lives there

**Business rules:**
- Make the fix testable by hand (i.e., triggering an agent run should produce the correct behavior)
- Do not apply the fix to files that aren't part of the root cause
- Commit changes with a clear message referencing #112

**Success criteria:**
- [ ] Fix applied to the confirmed root cause location(s)
- [ ] Office2 and repo copies in sync
- [ ] Changes committed with clear references

---

### FR-004: Verify Both Symptoms Resolved

| Field | Value |
|---|---|
| **ID** | FR-004 |
| **Status** | Proposed |
| **Priority** | High |

**What it must do:**
- Verify the tasker symptom: create an inbox note with a "due tomorrow" instruction in the evening (ET), process via felix-admin-capture → felix-admin-tasker, confirm the resulting Vikunja task has tomorrow's ET date
- Verify the habits symptom: trigger the habits morning check-in cron, confirm the tasks created/updated have today's ET date (not yesterday's)
- Verify the fix holds across timezone edge cases: late-evening creation (e.g., 11:30 PM ET), midnight boundary, early-morning (e.g., 1 AM ET)
- Record the verification evidence (task IDs, observed dates) in the diagnosis/fix artifact

**Business rules:**
- Verification must use real agent runs, not simulated or stubbed calls
- The verification step is a gate: the mission is not complete until BOTH symptoms are confirmed resolved
- If one symptom is fixed but the other persists, that's a partial fix — document and continue investigating

**Success criteria:**
- [ ] Tasker symptom verified fixed with real task creation evidence
- [ ] Habits symptom verified fixed with real task creation evidence
- [ ] At least one late-evening edge case tested
- [ ] Verification results recorded in the artifact

---

### FR-005: Document the Root Cause and Fix for the Record

| Field | Value |
|---|---|
| **ID** | FR-005 |
| **Status** | Proposed |
| **Priority** | Medium |

**What it must do:**
- Create or update a durable document (not just a commit message) explaining:
  - What the bug was
  - Why previous fix attempts didn't work
  - What the actual root cause is
  - How the fix addresses it
  - How to verify it still works in the future
- The document should live where future contributors will find it when working on date handling, task creation, or timezone issues

**Business rules:**
- The document is authoritative — future date-handling work should reference it
- Include the EDT/EST transition behavior explicitly so it's not a surprise later

**Success criteria:**
- [ ] Root cause document exists and is discoverable
- [ ] Future regression prevention is explicit (what to check for, what to avoid)
- [ ] Referenced from relevant code/config files (via comment or README link)

---

## Non-Functional Requirements

### NFR-001: No Regression for Explicit Dates

| Field | Value |
|---|---|
| **ID** | NFR-001 |
| **Status** | Proposed |
| **Priority** | High |

The fix must not break task creation for explicit date references (e.g., "due April 15" or "due 2026-04-15"). These already work correctly and the fix must not change their behavior.

---

### NFR-002: DST Transition Correctness

| Field | Value |
|---|---|
| **ID** | NFR-002 |
| **Status** | Proposed |
| **Priority** | High |

The fix must work correctly across EDT/EST transitions. A naive UTC-4 offset will break in November; using an IANA timezone name (America/New_York) handles DST automatically.

---

## Constraints

### C-001: Production System

| Field | Value |
|---|---|
| **ID** | C-001 |
| **Status** | Active |
| **Priority** | High |

Office2 is a live production system. Any changes to agent files, skills, or system configuration must follow change control protocols. Agent config is Tier 3 (standard); system timezone change would be Tier 0 or 1 (requires care). Prefer fixes that don't require system-level changes if possible.

### C-002: No New Dependencies

| Field | Value |
|---|---|
| **ID** | C-002 |
| **Status** | Active |
| **Priority** | Medium |

The fix should use timezone support available in the existing runtime (Python stdlib `zoneinfo`, JS `Intl.DateTimeFormat` with timeZone option, or similar). No new library installs unless absolutely necessary.

### C-003: Sudo Not Available

| Field | Value |
|---|---|
| **ID** | C-003 |
| **Status** | Active |
| **Priority** | High |

The `claude` user on office2 does not have sudo. If the fix requires sudo (e.g., changing system timezone), the investigation must stop and report this to Kent for manual execution. The fix should prefer user-space changes.

---

## Out of Scope

- ❌ Refactoring unrelated date or time handling in the codebase
- ❌ Adding timezone support to agents that don't currently create dated content
- ❌ Building a general-purpose "time library" — this is a targeted bug fix
- ❌ Changing Kent's timezone or adding multi-timezone support
- ❌ Fixing Vikunja itself (the fix is in how we USE Vikunja, not in Vikunja)

---

## User Scenarios & Testing

### Scenario 1: Evening "Tomorrow" Via Tasker

**Actor:** Kent captures a voice note at 10 PM ET: "I need to return the rental car tomorrow"
**Flow:** felix-admin-capture processes the inbox note → delegates to felix-admin-tasker → tasker proposes a Vikunja task with due date → Kent sees the task in Vikunja
**Expected outcome:** The task's due date is the next ET calendar date (not tonight's UTC date)
**Acceptance:** The Vikunja task's due date matches what Kent said — "tomorrow" from 10 PM ET means the next day in ET

### Scenario 2: Daily Habit Morning Check-in

**Actor:** habits-morning-checkin cron fires at 7:05 AM ET
**Flow:** felix-admin-habits updates/creates daily habit tasks in Vikunja → sends check-in message to Kent → Kent opens Vikunja Today view
**Expected outcome:** Habit tasks are due TODAY (not yesterday); they appear in the Today view, not the Overdue view
**Acceptance:** Kent opens Vikunja and sees today's habit tasks as due today

### Scenario 3: Midnight Boundary

**Actor:** Tasker creates a task at 12:15 AM ET (4:15 AM UTC)
**Flow:** The task is described as "due tomorrow" → agent calculates and creates the Vikunja task
**Expected outcome:** "Tomorrow" is calculated relative to ET, so the due date is the next ET calendar date (not 2 days out from UTC)
**Acceptance:** The resulting task is due the correct ET date

### Scenario 4: DST Transition

**Actor:** Hypothetical — EDT ends in early November
**Flow:** The day before DST ends and the day after, the agent creates habit tasks
**Expected outcome:** Both days' tasks are due the correct ET calendar date, regardless of DST state
**Acceptance:** IANA timezone (America/New_York) is used, not a fixed UTC-4 offset

### Scenario 5: Explicit Date Still Works

**Actor:** Kent captures "schedule dentist appointment for April 15"
**Flow:** Tasker parses the explicit date and creates a Vikunja task due April 15
**Expected outcome:** Task is due April 15 (not April 14 or 16) regardless of current time of day
**Acceptance:** NFR-001 holds — explicit dates are unaffected by the fix

---

## Key Entities

| Entity | Description |
|---|---|
| Due Date | The date a Vikunja task is marked as due |
| Agent Date Calculation | The code or prompt logic that determines "today" or "tomorrow" for task creation |
| vikunja_api Skill | The OpenClaw skill that formats and sends API calls to Vikunja |
| Timezone Context | The timezone in which date calculations should be done — Kent's: America/New_York |
| Root Cause | The specific location and logic that produces the wrong date |

---

## Success Criteria

- Root cause is documented with evidence (not assumed)
- Fix is applied at the confirmed root cause layer
- Both symptoms (tasker evening "tomorrow" and habits morning overdue) verified resolved
- No regression for explicit date references
- Fix handles EDT/EST transitions correctly
- Durable documentation prevents future regression
- Future contributors can find the root cause explanation without re-investigating

---

## Risk Considerations

**Risk: Investigation finds only the symptom's timezone shape, not the true root cause**
- Previous fix attempts may have patched one symptom without finding the underlying bug
- Mitigation: require an end-to-end trace with actual values at each layer, not inferred behavior

**Risk: Fix works in testing but regresses at DST transition**
- A fix that uses a hardcoded UTC offset will silently break in November
- Mitigation: NFR-002 explicitly requires IANA timezone handling; verification should include at least one DST-aware test (can be synthetic if real DST is not imminent)

**Risk: Fix requires sudo or system-level changes we can't apply**
- If the root cause is "system timezone is wrong", changing it needs sudo which the claude user lacks
- Mitigation: C-003 forces us to stop and escalate; prefer fixes that don't require sudo

**Risk: The fix lands correctly but one of the agents still produces bad dates due to prompt-level date reasoning**
- Even with correct system timezone, an agent that computes "today" via LLM reasoning over a UTC clock can still get it wrong
- Mitigation: FR-004 verification uses real end-to-end agent runs, not just code paths

---

## Notes for Implementation

**Investigation should start with the cheapest checks first:**
- `timedatectl` on office2 (system timezone)
- Read session logs for a recent task creation (what value was sent)
- Compare with USER.md and AGENTS.md to see what the agents THINK the date should be

**Avoid jumping to fixes until the diagnosis is solid.** The issue reopening note is a clear signal that earlier confident fixes missed the mark. A slower, more evidence-driven investigation is the goal.

**Document as you investigate.** The diagnosis artifact should be written during the investigation, not reconstructed afterward. This makes the root cause visible even if the fix is later revised.

---

**END OF SPECIFICATION**
