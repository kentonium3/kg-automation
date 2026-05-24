---
title: "F018: Habit Today Filter Visibility"
doc_type: func-spec
status: draft
feature: F018
---

# F018: Habit Today Filter Visibility

**Version**: 1.0
**Priority**: HIGH
**Type**: Agent Behavior Change
**Depends on**: F017 (Vikunja Habit Tracking Architecture — research findings)

---

## Executive Summary

F009 deployed daily habit tracking with static Vikunja tasks and comment-based
completion recording. The check-in delivery, WhatsApp interaction, and weekly
reporting all work. However, habit tasks never appear in the Vikunja Today
filter because they have no `due_date` set — an architecture gap identified
in F017 research.

Current gaps:
- ❌ Habit tasks have no `due_date`, so they are invisible in Vikunja's Today view
- ❌ Kent cannot check off habits directly in Vikunja — only via WhatsApp
- ❌ The Vikunja UI provides no at-a-glance view of today's habits

This spec adds a single step to the morning check-in workflow: the agent sets
`due_date = today` on each scheduled habit before delivering the WhatsApp
message. Everything else remains unchanged.

---

## Problem Statement

**Current State:**
```
felix-admin-habits agent (morning check-in)
├── ✅ Queries habit tasks from Vikunja project 13
├── ✅ Checks completion comments for today
├── ✅ Delivers check-in via WhatsApp
├── ✅ Records completions as comments
├── ❌ Does NOT set due_date on any task
└── ❌ Habits never appear in Vikunja Today filter

Vikunja Today filter
├── ✅ Queries tasks where dueDate >= now/d && dueDate < now/d+1d
└── ❌ All 7 habit tasks have due_date = null (0001-01-01T00:00:00Z)
```

**Target State:**
```
felix-admin-habits agent (morning check-in)
├── ✅ Queries habit tasks from Vikunja project 13
├── ✅ Checks completion comments for today
├── ✅ Sets due_date = today on each scheduled habit
├── ✅ Delivers check-in via WhatsApp
└── ✅ Records completions as comments

Vikunja Today filter
├── ✅ Queries tasks where dueDate >= now/d && dueDate < now/d+1d
└── ✅ Today's scheduled habits appear with due_date = today
```

---

## CRITICAL: Study These Files First

Before implementation, the planning phase MUST read and understand:

1. **F017 research findings — the architecture decision**
   - `kitty-specs/017-vikunja-habit-tracking-architecture/findings.md`
   - Contains the evaluated options, the recommended approach (Option C),
     and the specific API calls needed
   - The architecture recommendation is authoritative — do not re-evaluate

2. **Current agent standing orders**
   - `/data/services/openclaw/habits-agent/AGENTS.md` on office2
   - Study the morning check-in workflow (Steps 1-4)
   - The new due_date step inserts between Step 2 (query habits) and
     Step 4 (format check-in)
   - Also read the repo copy: `scripts/openclaw/agents/felix-admin-habits/AGENTS.md`

3. **Vikunja API behavior for task updates**
   - F017 findings confirm `PUT /api/v1/tasks/{id}` with `{"due_date": "..."}` works
   - The agent's existing vikunja_api skill already has task update capability
   - Study how the agent currently queries tasks to understand the existing
     API interaction pattern

4. **Habits operations runbook**
   - `docs/runbooks/habits-ops.md` — current operational documentation
   - Must be updated to reflect the new due_date behavior

---

## Requirements Reference

This specification implements the architecture recommendation from F017:
- **Option C**: Static tasks + agent-managed due_date + comment history
- Resolves the deferred architecture decision from F009's "Habits Are Not
  Tasks" principle

---

## Functional Requirements

### FR-1: Set due_date on Scheduled Habits During Morning Check-in

**What it must do:**
- During the morning check-in workflow, after determining which habits are
  scheduled for today, set `due_date` to today's date on each scheduled habit
- The due_date must be set BEFORE delivering the WhatsApp check-in message,
  so habits are visible in Today by the time Kent opens Vikunja
- Only habits scheduled for today receive today's due_date — habits not
  scheduled today retain their previous due_date

**Business rules:**
- The due_date is a visibility mechanism, not a completion record — the
  comment model remains the authoritative source for completion state
- If the API call to set due_date fails for one habit, continue with the
  remaining habits and deliver the check-in — do not block the entire
  workflow on a single API failure
- The agent must not set due_date on paused habits (description contains
  "(PAUSED)") or archived habits (done = true)

**Pattern reference:** Study the agent's existing task query workflow in
AGENTS.md Step 2 — the due_date update follows the same API interaction
pattern with an additional write call per task

**Success criteria:**
- [ ] Scheduled habits appear in Vikunja Today filter after morning check-in runs
- [ ] Habits not scheduled today do not appear in Today filter
- [ ] WhatsApp check-in delivery is not blocked by due_date API failures
- [ ] Paused and archived habits are not modified

---

### FR-2: Update Agent Standing Orders (AGENTS.md)

**What it must do:**
- Add a new step to the morning check-in workflow in AGENTS.md that sets
  due_date on scheduled habits
- The new step must be positioned after habit querying and filtering, but
  before check-in message formatting and delivery
- Update both the repo copy and the deployed copy on office2

**Business rules:**
- The repo copy at `scripts/openclaw/agents/felix-admin-habits/AGENTS.md`
  is the version-controlled source of truth
- The deployed copy at `/data/services/openclaw/habits-agent/AGENTS.md` on
  office2 must match the repo copy after deployment
- No other sections of AGENTS.md should change — completion recording,
  weekly reporting, habit management, and error handling remain unchanged

**Pattern reference:** Study the existing AGENTS.md step structure — each
step has a title, description, and specific instructions

**Success criteria:**
- [ ] AGENTS.md contains a new step for setting due_date
- [ ] New step is positioned correctly in the workflow sequence
- [ ] Repo copy and deployed copy are in sync
- [ ] No unrelated changes to AGENTS.md

---

### FR-3: Update Habits Operations Runbook

**What it must do:**
- Update `docs/runbooks/habits-ops.md` to document the due_date behavior
- Explain that habits appear in the Today filter after the morning check-in
- Add troubleshooting entry for "habits not appearing in Today"

**Success criteria:**
- [ ] Runbook documents the due_date mechanism
- [ ] Troubleshooting table includes Today filter visibility
- [ ] Runbook passes doc validation (frontmatter compliant)

---

## Out of Scope

- ❌ Changes to the completion recording model — comment-based tracking is
  unchanged (validated by F017 research)
- ❌ Changes to weekly reporting — the agent already queries comments by date
- ❌ Changes to cron configuration — same schedule, same delivery
- ❌ Changes to WhatsApp interaction — message format and reply handling unchanged
- ❌ Vikunja saved filter creation — Kent can create a Today filter in the UI;
  the agent's job is to set the due_date so tasks appear in it
- ❌ New services or external data stores — F017 confirmed none are needed
- ❌ Native Vikunja recurring task features — F017 eliminated this approach

---

## Success Criteria

**Complete when:**

### Today Filter Visibility
- [ ] After morning check-in runs, today's scheduled habits appear in Vikunja
  Today filter
- [ ] Habits not scheduled today do not appear in Today filter
- [ ] Marking a habit complete via WhatsApp does not remove it from Today
  (the comment is the state record, not done status)

### Agent Behavior
- [ ] AGENTS.md updated with due_date step in correct position
- [ ] Agent sets due_date on all scheduled habits before delivering check-in
- [ ] A single API failure does not block the entire check-in workflow
- [ ] Deployed AGENTS.md on office2 matches repo copy

### Documentation
- [ ] `docs/runbooks/habits-ops.md` updated with due_date behavior
- [ ] Runbook troubleshooting covers Today filter issues
- [ ] All documentation passes CI validation

---

## Architecture Principles

### due_date Is a View Mechanism, Not a State Record

The `due_date` field serves one purpose: making habits visible in the
Vikunja Today filter. It is not a completion record, not a scheduling
constraint, and not an input to reporting. The comment model
(`[Felix] YYYY-MM-DD | state | note`) remains the sole authority for
completion state. If the due_date is wrong or missing, the only impact
is Today filter visibility — all other functionality (WhatsApp check-in,
completion recording, reporting) is unaffected.

### Minimal Change, Maximum Leverage

F017 research confirmed the current system is 90% correct. This feature
adds one API call per habit to the existing workflow. No new data stores,
no new services, no new agent capabilities. The smallest possible change
to close the gap.

---

## Constitutional Compliance

✅ **Privacy is absolute**: No change to privacy handling. Habits from
private context appear as habit names only — unchanged from F009.

✅ **Narrow scope**: felix-admin-habits gains one new behavior (set due_date)
within its existing scope of habit check-in management.

✅ **Never fail silently**: If due_date API calls fail, the agent reports
the failure and continues with check-in delivery.

✅ **No credentials in code**: Vikunja API token from credential store —
same mechanism as existing task queries.

---

## Risk Considerations

**Risk: Morning cron fails, due_date not set**
- Habits won't appear in Today filter until next successful run
- Impact is cosmetic — WhatsApp check-in still works, completions still
  recorded. Today filter is a convenience, not the primary workflow.

**Risk: Vikunja API rejects due_date update**
- Possible if task schema validation changes in a future Vikunja version
- Mitigation: agent reports error and continues; F017 confirmed the API
  call works on Vikunja 0.24.6

**Risk: Tasks not scheduled today retain stale due_date**
- A habit scheduled Mon/Wed/Fri will show Tuesday's due_date on Wednesday
  morning until the check-in runs
- Impact: minor — the habit briefly appears under yesterday's date in
  date-based views, then gets updated to today

---

## Notes for Implementation

**Pattern Discovery (Planning Phase):**
- Study the existing morning check-in workflow in AGENTS.md Steps 1-4
- Study how the agent currently uses the vikunja_api skill for task queries
- Study the F017 findings for the exact API call specification

**Key Patterns to Copy:**
- The agent's existing task query pattern → extend with a task update call
- The existing AGENTS.md step structure → copy format for the new step
- The habits-ops.md troubleshooting table → add new entry following same format

**Focus Areas:**
- The new step must execute BEFORE the check-in message is formatted,
  so habits are visible in Today by the time Kent receives the WhatsApp message
- Error handling must be non-blocking — a failed due_date update should
  not prevent check-in delivery

---

**END OF SPECIFICATION**
