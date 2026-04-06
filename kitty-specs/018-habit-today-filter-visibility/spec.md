# Habit Today Filter Visibility

**Feature**: 018-habit-today-filter-visibility
**Mission**: software-dev
**Status**: draft
**Priority**: HIGH
**Depends on**: F017 (Vikunja Habit Tracking Architecture — research findings)

---

## Summary

Daily habit tasks deployed by F009 never appear in the Vikunja Today filter
because they have no `due_date` set. F017 research determined the correct
fix: the felix-admin-habits agent should set `due_date = today` on each
scheduled habit during the morning check-in, before delivering the WhatsApp
message. This makes habits visible in Today with minimal change to the
existing system.

---

## Actors

- **felix-admin-habits agent**: Sets due_date and delivers check-in
- **Kent (system owner)**: Views habits in Vikunja Today filter and checks
  them off via Vikunja UI or WhatsApp
- **Vikunja Today filter**: Displays tasks where due_date falls within today

---

## User Scenarios and Testing

### Scenario 1: Habits appear in Today after morning check-in

**Actor**: Kent
**Precondition**: Morning check-in cron runs at 7:05 AM ET
**Flow**:
1. Agent determines today's scheduled habits (e.g., 7 on weekdays, 5 on Sunday)
2. Agent sets `due_date = today` on each scheduled habit
3. Agent delivers WhatsApp check-in message
4. Kent opens Vikunja Today view
5. All scheduled habits appear in the Today filter

**Acceptance**: Habits are visible in Today immediately after check-in runs.
Habits not scheduled today (e.g., strength training on Tuesday) do not appear.

### Scenario 2: due_date failure does not block check-in

**Actor**: felix-admin-habits agent
**Precondition**: Vikunja API is partially degraded
**Flow**:
1. Agent attempts to set due_date on 7 habits
2. API call fails for 1 habit (e.g., timeout)
3. Agent continues setting due_date on remaining 6 habits
4. Agent delivers WhatsApp check-in listing all 7 habits
5. Agent reports the failed due_date update in its output

**Acceptance**: WhatsApp delivery succeeds despite partial API failure.
6 of 7 habits appear in Today. The failure is logged, not silent.

### Scenario 3: Kent marks habit complete via Vikunja UI

**Actor**: Kent
**Precondition**: Habits are visible in Today filter
**Flow**:
1. Kent sees "Meditate 45 min" in Today filter
2. Kent marks it complete in Vikunja UI (checks it off)
3. Vikunja sets `done = true` on the task

**Acceptance**: This scenario reveals a design consideration — marking
done in Vikunja sets the task done flag, but the agent's completion model
uses comments. The agent's next check-in should still detect the comment
absence and list the habit. Kent's primary completion path remains
WhatsApp; Vikunja Today is a visibility aid, not a completion interface.

---

## Requirements

### Functional Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| FR-001 | During the morning check-in, the agent must set due_date to today on each habit scheduled for that day, before delivering the WhatsApp message | draft |
| FR-002 | Habits not scheduled for today must not have their due_date changed to today | draft |
| FR-003 | If the due_date API call fails for one habit, the agent must continue processing remaining habits and still deliver the WhatsApp check-in | draft |
| FR-004 | Paused habits (description contains "(PAUSED)") and archived habits (done = true) must not have their due_date modified | draft |
| FR-005 | The agent's standing orders (AGENTS.md) must be updated with the new due_date step, positioned after habit querying and before check-in formatting | draft |
| FR-006 | The deployed AGENTS.md on office2 must be updated to match the repo copy after changes | draft |
| FR-007 | The habits operations runbook must be updated to document the due_date mechanism and add a troubleshooting entry for Today filter visibility | draft |

### Non-Functional Requirements

| ID | Requirement | Threshold | Status |
|----|-------------|-----------|--------|
| NFR-001 | The due_date update step must complete within the existing 120-second cron timeout alongside all other check-in operations | <= 120s total | draft |
| NFR-002 | The due_date step must not increase the agent's API token count by more than 20% over the current morning check-in | <= 20% token increase | draft |

### Constraints

| ID | Constraint | Status |
|----|------------|--------|
| C-001 | The comment-based completion model must remain unchanged — due_date is a visibility mechanism only | active |
| C-002 | No new services, external data stores, or Vikunja schema changes | active |
| C-003 | The agent must use the existing vikunja_api skill for task updates | active |
| C-004 | Vikunja API token location and base URL are unchanged from F009 | active |

---

## Scope

### In scope

- Adding due_date = today to the morning check-in workflow
- Updating AGENTS.md (repo copy and deployed copy on office2)
- Updating habits-ops.md runbook with due_date behavior and troubleshooting

### Out of scope

- Changes to completion recording (comment model unchanged)
- Changes to weekly reporting (already queries comments by date)
- Changes to cron configuration (same schedule, same delivery)
- Changes to WhatsApp interaction (message format and reply handling unchanged)
- Creating a Vikunja saved filter (Kent can do this in the UI)
- Native Vikunja recurring task features (eliminated by F017)
- Handling Vikunja UI completion (marking done in Vikunja UI is outside
  the agent's completion model — WhatsApp remains the primary interface)

---

## Success Criteria

### Today filter visibility
- Scheduled habits appear in the Vikunja Today filter after the morning
  check-in runs each day
- Habits not scheduled for today do not appear in the Today filter
- The Today filter shows the correct set of habits for every day of the
  week (weekday vs. weekend schedule differences are reflected)

### Agent reliability
- A single API failure does not prevent WhatsApp check-in delivery
- The agent completes the full morning check-in (including due_date
  updates) within the existing 120-second timeout
- Failed due_date updates are reported, not silently dropped

### Documentation completeness
- AGENTS.md accurately describes the due_date step in the correct
  workflow position
- The deployed AGENTS.md on office2 matches the repo copy
- The habits-ops runbook documents the due_date mechanism and
  includes troubleshooting for Today filter issues
- All documentation passes CI validation

---

## Key Entities

| Entity | Role | Changes in this feature |
|--------|------|------------------------|
| Habit task (Vikunja tasks 14-20) | Static tasks in Habits project | due_date field set daily by agent |
| AGENTS.md | Agent standing orders | New step added to morning check-in |
| habits-ops.md | Operations runbook | Updated with due_date documentation |
| Vikunja Today filter | Date-based task view | No change — habits become visible by having due_date set |

---

## Assumptions

- The Vikunja task update endpoint accepts partial updates (confirmed by
  F017 research — only due_date needs to be sent)
- The 7 habit tasks (IDs 14-20) in project 13 are the complete active set
- The vikunja_api skill available to the agent already supports task updates
- Setting due_date does not trigger any Vikunja side effects (e.g.,
  notifications, recurrence changes) — confirmed by F017: no recurrence
  is configured on these tasks

---

## Dependencies

- **F017 findings** (`kitty-specs/017-vikunja-habit-tracking-architecture/findings.md`):
  Architecture recommendation, API capability confirmation, comparison table
- **F009 deployment**: The existing agent, cron jobs, and task structure
  that this feature extends

---

**END OF SPECIFICATION**
