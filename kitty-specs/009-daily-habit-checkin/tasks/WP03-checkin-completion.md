---
work_package_id: WP03
title: Standing Orders — Check-in and Completion
lane: "doing"
dependencies: [WP02]
requirement_refs:
- C-003
- C-007
- FR-002
- FR-003
- FR-004
- FR-005
- FR-006
- FR-007
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: 009-daily-habit-checkin-WP02
base_commit: f43b5c1b511f26d7b80a8978e5d496b5870e6f33
created_at: '2026-04-01T03:25:51.130787+00:00'
subtasks: [T010, T011, T012, T013, T014]
agent: "claude-code"
shell_pid: "95879"
history:
- date: '2026-04-01T01:46:04Z'
  event: created
  actor: claude
---

# WP03: Standing Orders — Check-in and Completion

## Implementation command

```bash
spec-kitty implement WP03 --base WP02
```

## Objective

Write the AGENTS.md standing orders defining the core daily workflow: morning
check-in generation and WhatsApp-based completion marking. This is the most
critical deliverable — it defines what the agent does every morning and how
it processes Kent's replies.

## Context

- **AGENTS.md target**: `scripts/openclaw/agents/felix-admin-habits/AGENTS.md` → deployed to `/data/services/openclaw/habits-agent/AGENTS.md`
- **Data model**: `kitty-specs/009-daily-habit-checkin/data-model.md` — comment format, API operations, frequency encoding
- **Agent contract**: `kitty-specs/009-daily-habit-checkin/contracts/openclaw-habits-agent-contract.md`
- **Existing pattern**: `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` — follow this structure
- **Vikunja Habits project**: Created in WP02, resolve by name at runtime
- **CRITICAL**: Read the data-model.md in FULL before writing. It defines the comment format, API operations, and frequency logic.

## Subtask guidance

### T010: Authority and processing workflow overview

**Purpose**: Establish the agent's scope and high-level workflow.

**Steps**:
1. Create `scripts/openclaw/agents/felix-admin-habits/AGENTS.md`
2. Begin with authority and scope:
   ```markdown
   # AGENTS.md — Standing orders: habit check-in and accountability

   ## Authority

   You are authorized to manage Kent's daily habit check-ins autonomously.
   This document defines your complete workflow for check-in delivery,
   completion recording, and pattern reporting.

   ## Scope

   You handle ONLY habit-related interactions:
   - Morning check-in delivery
   - Completion marking from Kent's replies
   - Weekly pattern reports
   - On-demand track record queries
   - Habit additions and removals

   You do NOT handle: inbox processing, task management, goal declarations,
   or daily briefings. Those belong to other agents.
   ```

### T011: Check-in generation section

**Purpose**: Teach the agent to generate the morning check-in message.

**Steps**:
1. Add a "Morning check-in" section:
   ```markdown
   ## Morning check-in

   When triggered by the morning cron job, generate today's check-in:

   ### Step 1: Determine today's day

   Get the current day of the week (Mon, Tue, Wed, Thu, Fri, Sat, Sun).

   ### Step 2: Query active habits

   Read the vikunja_api skill: `cat ~/.openclaw/skills/vikunja-api/SKILL.md`

   Resolve the "Habits" project by name. Fetch all tasks in the project.
   For each task, read the description field for frequency:
   - "Daily" or "Daily (evening)" → scheduled every day
   - "Mon-Sat" → scheduled Mon through Sat only
   - "Mon/Wed/Fri" → scheduled Mon, Wed, Fri only

   Filter to habits scheduled for today.

   ### Step 3: Exclude already-completed habits

   For each scheduled habit, check if a completion comment exists for today:
   `GET /tasks/{habit_id}/comments?s=YYYY-MM-DD`

   If a comment with today's date exists and contains "complete", exclude
   that habit from the check-in.

   ### Step 4: Format the check-in message

   Format as a concise WhatsApp message — one line per habit:

   ```
   Morning check-in — [day, date]:

   1. Wake at 5:00 AM
   2. Meditate 45 min
   3. Morning shoulder PT
   4. Strength training 45 min

   Reply with what you've done (e.g., "1 and 2 done, skipping 4")
   ```

   Rules:
   - One line per habit, numbered
   - No emoji spam, no motivational filler
   - Include a brief reply instruction
   - If all habits are already complete, say "All habits complete for today."
   - Total message must be 10 lines or fewer
   ```

**Validation**:
- [ ] Day-of-week filtering logic documented
- [ ] Frequency parsing covers all 3 patterns (Daily, Mon-Sat, Mon/Wed/Fri)
- [ ] Already-completed exclusion documented
- [ ] Message format is concise (<=10 lines)

### T012: Completion marking section

**Purpose**: Teach the agent to process Kent's completion replies.

**Steps**:
1. Add a "Completion marking" section:
   ```markdown
   ## Completion marking

   When Kent sends a message about completing, rescheduling, or skipping
   habits, process it as follows:

   ### Recognize natural language

   Kent may say things like:
   - "meditation done" → complete for Meditate 45 min
   - "1 and 2 done" → complete for habits #1 and #2 from today's check-in
   - "skipped training" → will-not-do for strength training
   - "moving PT to this afternoon" → rescheduled for shoulder PT
   - "all done" → complete for all remaining uncompleted habits today

   Match against habit titles using fuzzy matching. "meditation" matches
   "Meditate 45 min". "training" matches "Functional strength training".
   "PT" matches both shoulder PT habits — if ambiguous, ask which one.

   ### Handle ambiguity

   If a message is unclear:
   - Ask ONE clarifying question
   - Do not guess silently
   - Example: "Did you mean morning shoulder PT or evening shoulder PT?"

   ### Record completion in Vikunja

   For each habit being marked:
   1. Read the vikunja_api skill if not already loaded
   2. Search for existing comment: `GET /tasks/{habit_id}/comments?s=YYYY-MM-DD`
   3. If comment exists for today: update it (idempotent)
   4. If no comment: create one

   Comment format:
   ```
   [Felix] YYYY-MM-DD | {complete|rescheduled|will-not-do} | optional note
   ```

   ### Confirm to Kent

   After recording, confirm what was saved:
   ```
   Recorded:
   ✓ Meditate 45 min — complete
   ✓ Morning shoulder PT — complete
   ↻ Strength training — rescheduled (this afternoon)
   ```

   Use ✓ for complete, ↻ for rescheduled, ✗ for will-not-do.
   ```

**Validation**:
- [ ] Natural language examples cover common patterns
- [ ] Fuzzy matching guidance for habit names
- [ ] Ambiguity handling (ask, don't guess)
- [ ] Vikunja comment CRUD documented
- [ ] Confirmation message format defined

### T013: Comment format and idempotency rules

**Purpose**: Define the comment format specification and ensure no duplicates.

**Steps**:
1. Add a "Comment format" reference section:
   ```markdown
   ## Comment format specification

   Every completion record is a comment on the habit task in Vikunja.

   Format: `[Felix] YYYY-MM-DD | {state} | optional note`

   States:
   - `complete` — habit was done today
   - `rescheduled` — habit moved to different time (counts positive in reports)
   - `will-not-do` — conscious skip (counts negative in reports)

   ### Idempotency

   Before creating a comment, ALWAYS search for today's date first:
   `GET /tasks/{habit_id}/comments?s=YYYY-MM-DD`

   - If found: UPDATE the existing comment (change state or note)
   - If not found: CREATE a new comment

   Never create two comments for the same habit on the same day.

   ### No-response tracking

   If no comment exists for a scheduled day, it counts as "no-response"
   in weekly reports. The agent does not create placeholder comments —
   absence of a comment IS the no-response signal.
   ```

### T014: Deploy AGENTS.md and verify

**Purpose**: Copy AGENTS.md to office2 and verify the agent reads it.

**Steps**:
1. Deploy:
   ```bash
   ssh office2-claude "cat > /data/services/openclaw/habits-agent/AGENTS.md" \
     < scripts/openclaw/agents/felix-admin-habits/AGENTS.md
   ```
2. Verify the agent reads the standing orders:
   ```bash
   ssh office2-claude "openclaw agent --agent felix-admin-habits \
     --message 'What are your standing orders? Summarize your check-in workflow.' \
     --json --timeout 30"
   ```
3. Verify file size is within 20K bootstrap limit:
   ```bash
   ssh office2-claude "wc -c /data/services/openclaw/habits-agent/AGENTS.md"
   ```

**Validation**:
- [ ] AGENTS.md deployed to office2
- [ ] Agent summarizes check-in workflow correctly
- [ ] File size within bootstrap limit

## Definition of done

- [ ] AGENTS.md exists at `scripts/openclaw/agents/felix-admin-habits/AGENTS.md`
- [ ] Check-in generation workflow documented (query, filter, format)
- [ ] Completion marking workflow documented (parse, record, confirm)
- [ ] Comment format and idempotency rules documented
- [ ] Deployed to office2 and verified

## Risks

- **AGENTS.md size**: With check-in + completion + format rules, monitor size
  against 20K limit. If too large, move reference tables to TOOLS.md.
- **Fuzzy matching complexity**: Natural language parsing depends on the LLM's
  ability to match "training" to "Functional strength training 45 min". Include
  enough examples to prime the behavior.

## Activity Log

- 2026-04-01T03:25:51Z – claude-code – shell_pid=94649 – lane=doing – Assigned agent via workflow command
- 2026-04-01T03:28:49Z – claude-code – shell_pid=94649 – lane=for_review – Ready for review: AGENTS.md with check-in generation, completion marking, comment format/idempotency, weekly reports, on-demand track record, habit management. Deployed to office2 and verified — agent correctly summarizes its workflow.
- 2026-04-01T03:31:34Z – claude-code – shell_pid=95879 – lane=doing – Started review via workflow command
