---
work_package_id: WP01
title: Escalation Skill
dependencies: []
requirement_refs:
- FR-013
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks: [T001]
history:
- date: '2026-04-06'
  action: created
  by: spec-kitty.tasks
authoritative_surface: scripts/openclaw/skills/escalation/
execution_mode: code_change
owned_files:
- scripts/openclaw/skills/escalation/SKILL.md
---

# WP01: Escalation Skill

## Objective

Create the self-contained escalation skill at
`scripts/openclaw/skills/escalation/SKILL.md` that encodes the full
escalation model. This skill is what `felix-admin-escalation` reads to
apply consistent behavior. It must be complete enough that the agent
can implement the full escalation workflow by reading this skill alone.

## Context

**Why a skill**: OpenClaw skills are reusable instruction sets that agents
load on demand. The escalation skill encodes the model in one place so
that (a) the agent's AGENTS.md can reference it without duplicating logic,
and (b) future agents (Commitment Manager, escalation heartbeat) can read
the same skill to understand escalation state.

**Pattern reference**: Study the existing vikunja-api skill at
`scripts/openclaw/skills/vikunja-api/SKILL.md` for format conventions.
Also study `scripts/openclaw/agents/felix-admin-habits/AGENTS.md` for
the comment-as-state pattern that this skill formalizes for escalation.

**Key research findings** (from `kitty-specs/019-escalation-engine/research.md`):
- Priority filter: `priority >= 2` (medium, high, urgent)
- Excluded projects: Goals (ID 11), Habits (ID 13)
- Cron: 8:00 AM ET (12:00 UTC)
- Vikunja priority values: 0=unset, 1=low, 2=medium, 3=high, 4=urgent

## Branch Strategy

- Planning/base branch: `main`
- Merge target: `main`
- Implementation command: `spec-kitty implement WP01`

---

## Subtask T001: Create Escalation Skill (SKILL.md)

**Purpose**: Define the complete escalation model in a self-contained skill.

**File**: `scripts/openclaw/skills/escalation/SKILL.md`

**The skill must encode all of the following sections:**

### 1. Escalation Criteria

- **Overdue detection**: Tasks where `due_date < today` AND `done = false`
- **Priority filter**: Only tasks with `priority >= 2` (medium, high, urgent)
  - Priority values: 0=unset, 1=low, 2=medium, 3=high, 4=urgent
- **Project filter**: Exclude project IDs 11 (Goals) and 13 (Habits)
- **Pre-emptive alert**: Tasks due today (`due_date = today`) qualify for
  Level 1 only if `priority >= 3` (high or urgent)
- **Done tasks**: Never escalated — always check `done = false`

### 2. Escalation Level Model

| Level | Name | Trigger conditions |
|-------|------|--------------------|
| 1 | Nudge | Task overdue 1-3 days with no prior escalation comment, OR due today with priority >= 3 |
| 2 | Insistence | Task overdue >3 days, OR Level 1 sent 2+ days ago with no response comment |

**Level determination algorithm**:
1. Read the most recent `[Felix-Escalation]` comment on the task
2. If no escalation comment exists AND overdue 1-3 days → Level 1
3. If no escalation comment exists AND overdue >3 days → Level 2
4. If most recent comment is `level-1 | sent` AND sent 2+ days ago
   with no subsequent `acknowledged` comment → Level 2
5. If most recent comment is `snoozed:Nd` → check if snooze expired
   (snooze date + N days <= today); if expired, re-enter at Level 1
6. If most recent comment is `dismissed` → skip UNLESS the task's
   due_date is later than the dismiss comment date (indicates
   rescheduling reset)
7. If most recent comment is any `acknowledged` → skip (already addressed)

### 3. Escalation Comment Format

**Prefix**: `[Felix-Escalation]`

**Escalation sent** (written by agent after alert delivery):
```
[Felix-Escalation] YYYY-MM-DD | level-1 | sent
[Felix-Escalation] YYYY-MM-DD | level-2 | sent
```

**Response recorded** (written by agent after Kent responds):
```
[Felix-Escalation] YYYY-MM-DD | snoozed:Nd | acknowledged
[Felix-Escalation] YYYY-MM-DD | dismissed | acknowledged
[Felix-Escalation] YYYY-MM-DD | done | acknowledged
[Felix-Escalation] YYYY-MM-DD | rescheduled:YYYY-MM-DD | acknowledged
```

**Parsing rules**:
- Split on ` | ` (space-pipe-space) to get [date, state, disposition]
- Date is always YYYY-MM-DD
- State tokens are lowercase, hyphenated
- `snoozed:Nd` — N is an integer, d is literal "d" (days)
- `rescheduled:YYYY-MM-DD` — the new due date
- Comments are append-only — never modify or delete existing comments
- The most recent `[Felix-Escalation]` comment determines current state

### 4. WhatsApp Message Format

**Combined message structure** (Level 2 first, then Level 1):
```
🔴 Tasks slipping:

1. [Project] Task name — N days overdue

⚠️ Tasks needing attention:

2. [Project] Task name — N days overdue
3. [Project] Task name — due today (high priority)

Reply: "1 done", "2 snooze 3d", "3 dismiss",
"2 move to friday", or "all snooze 2d"
```

**Rules**:
- Level 2 tasks listed first with 🔴 header
- Level 1 tasks listed after with ⚠️ header
- If only one level exists, use only that header
- Each task: numbered, project in brackets, task name, overdue duration
- Cap at 7 tasks total; if more, note "(+N more in Vikunja Overdue filter)"
- Include response prompt at the end
- Numbers are sequential across both levels (1, 2, 3... not restarting)

### 5. Response Parsing

| Response pattern | Action |
|------------------|--------|
| `N done` | Mark task #N complete in Vikunja (`done: true`) |
| `N snooze` or `N snooze Nd` | Write snooze comment (default 1d) |
| `N dismiss` | Write dismiss comment |
| `move N to <date>` or `N move to <date>` | Update due_date, write reschedule comment |
| `N and M done` | Mark multiple tasks complete |
| `all snooze Nd` | Apply snooze to every listed task |
| `got it` or vague acknowledgment | Write acknowledgment comment, no task action |
| Ambiguous or unrecognized | Ask ONE clarifying question |

**Date parsing for reschedule**: "friday" = next Friday, "next monday" =
next Monday, "april 10" = 2026-04-10. Always confirm the parsed date
before executing.

### 6. Error Handling

- **Vikunja unavailable**: Log the error. Do NOT send a WhatsApp message
  claiming no tasks are overdue — silence is better than a false negative.
  Report the error in the run output.
- **Comment write fails**: Log which task failed. Continue processing
  remaining tasks. Report the failure.
- **WhatsApp delivery fails**: Log the failure. Escalation comments should
  NOT be written if the alert was never delivered — the state should
  reflect what Kent actually received.
- **Task marked done between detection and alert**: Re-check `done`
  status before sending. If done, skip silently.

### 7. Daily Deduplication

The agent must not send duplicate Level 2 alerts for the same task on
the same calendar day. Before sending, check if a `level-2 | sent`
comment exists with today's date. If so, skip that task.

---

## Definition of Done

- [ ] SKILL.md exists at `scripts/openclaw/skills/escalation/SKILL.md`
- [ ] All 7 sections present and complete
- [ ] Escalation level algorithm is unambiguous — no edge cases left undefined
- [ ] Comment format documented with exact syntax and parsing rules
- [ ] Response parsing covers all specified patterns
- [ ] Error handling addresses Vikunja unavailability, comment write failure, and delivery failure
- [ ] The skill is self-contained — an agent can apply the full model from this file alone

## Risks

| Risk | Mitigation |
|------|------------|
| Level determination logic has ambiguous edge cases | Algorithm specified step-by-step with numbered priority |
| Comment format too rigid for future extension | Lowercase hyphenated tokens; new states addable without breaking parsers |

## Reviewer Guidance

1. Walk through the level determination algorithm with test cases:
   - New overdue task (2 days) → should be Level 1
   - Task at Level 1 for 3 days, no response → should be Level 2
   - Snoozed task, snooze expired → should re-enter at Level 1
   - Dismissed task, due_date updated → should re-enter at Level 1
2. Verify comment format examples are syntactically consistent
3. Confirm error handling: no false negatives (don't report "nothing overdue"
   when Vikunja is down)
4. Check that the 7-task cap and deduplication rules are explicit

---

**END OF WORK PACKAGE**
