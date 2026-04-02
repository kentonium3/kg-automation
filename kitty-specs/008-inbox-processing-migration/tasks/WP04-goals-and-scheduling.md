---
work_package_id: WP04
title: Goal Routing and Scheduling
dependencies: [WP03]
requirement_refs:
- FR-015
- FR-016
- FR-017
- FR-018
- FR-019
- FR-020
- FR-021
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: 008-inbox-processing-migration-WP03
base_commit: a13b1e4b164a8019b47660f1a81f56de63ee6a89
created_at: '2026-03-31T03:13:04.809808+00:00'
subtasks: [T017, T018, T019, T020, T021, T022]
history:
- date: '2026-03-31T02:04:57Z'
  event: created
  actor: claude
authoritative_surface: kitty-specs/008-inbox-processing-migration/
execution_mode: planning_artifact
mission_id: 01KN5QX3WJGAVA67AVPSBGXX96
owned_files:
- kitty-specs/008-inbox-processing-migration/**
wp_code: WP04
---

# WP04: Goal Routing and Scheduling

## Implementation Command

```bash
spec-kitty implement WP04 --base WP03
```

## Objective

Add goal declaration routing to AGENTS.md (Felix validation, Goals-MOC.md +
Vikunja routing, potential-goal flagging), then add 3 cron jobs for scheduled
execution and test the full processing cycle.

## Context

- **AGENTS.md**: Built in WP02 (routing) and WP03 (task bridge). This WP adds goal handling.
- **Goal handling source**: `~/second-brain/.claude/skills/inbox-processor/SKILL.md` — "Goal handling rules" section
- **Goals-MOC.md**: `~/second-brain/vault/01-Constitution/Goals-MOC.md` (read locally to understand current structure)
- **Felix declaration format**: "On [date], I have [outcome] as evidenced by [proof]"
- **Cron contract**: `kitty-specs/008-inbox-processing-migration/contracts/openclaw-agent-contract.md`

## Subtask Guidance

### T017: Felix Declaration Validation Rules

**Purpose**: Teach the agent to validate goal declarations strictly.

**Steps**:
1. Read the "Goal handling rules" section of inbox-processor SKILL.md
2. Add a "Goal Declaration Handling" section to AGENTS.md:
   ```markdown
   ## Goal Declaration Handling

   ### Validation rules

   A valid Felix goal declaration MUST contain ALL THREE elements:
   1. **Specific date** — "On June 30th, 2026" (not "someday" or "soon")
   2. **Present-tense outcome** — "I have established $5K/month income"
      (not "I will" or "I want to")
   3. **Observable evidence** — "as evidenced by deposits totaling $5,000"
      (not vague or unmeasurable)

   If ANY element is missing, the content is NOT a valid declaration.

   **NEVER invent dates or evidence criteria.** If the inbox note says
   "I want to run a 5K" without a date or evidence, that is aspirational
   — not a declaration. Flag it, don't promote it.
   ```

**Validation**:
- [ ] All three elements documented (date, outcome, evidence)
- [ ] "Never invent" rule stated
- [ ] Matches inbox-processor SKILL.md goal handling exactly

### T018: Valid Declaration Routing

**Purpose**: Route valid declarations to Goals-MOC.md AND Vikunja.

**Steps**:
1. Add routing instructions:
   ```markdown
   ### When content contains a valid declaration

   1. Read `/home/kgale/second-brain/vault/01-Constitution/Goals-MOC.md`
   2. Check if this goal already exists (update in place if so)
   3. If new: add to the Active Declarations section using the Felix format
   4. Include the identity label: personal, intentional, or metalcasework
   5. Create a Vikunja task in the Goals project:
      - Title: the outcome statement
      - Due date: the target date from the declaration
      - Identity label: same as above
      - Description: "Source: Inbox YYYY-MM-DD HHmm.md — Felix goal declaration"
   6. Log in processing log under "Goals routed"
   ```

**Validation**:
- [ ] Dual routing: Goals-MOC.md AND Vikunja Goals project
- [ ] Due date set from declaration's target date
- [ ] Duplicate check (update existing, don't create second)

### T019: Potential-Goal Flagging

**Purpose**: Flag partial/aspirational goals without promoting them.

**Steps**:
1. Add flagging rules:
   ```markdown
   ### When content is goal-adjacent but NOT a valid declaration

   Aspirations, undated intentions, or partial goals missing evidence:
   - Do NOT add to Goals-MOC.md
   - Do NOT create a Vikunja task in Goals project
   - Flag in processing log as `type: potential-goal`
   - Note specifically what is missing (date, evidence, or both)

   Examples of content that is NOT a valid declaration:
   - "I want to run a 5K" → missing date and evidence
   - "By next year I'll have more income" → vague date, no evidence
   - "On June 30, I'll be healthier" → missing specific evidence

   Never add checkbox-style items or vague aspirations to Goals-MOC.md.
   Never modify Goals-MOC-pre-Felix-backup-2026-03-29.md.
   ```

**Validation**:
- [ ] Clear distinction between valid and invalid declarations
- [ ] Specific examples of what NOT to promote
- [ ] Backup file protection stated

### T020: Add 3 Cron Jobs

**Purpose**: Schedule 3× daily processing.

**Steps**:
1. Add cron jobs on office2 (times in UTC, America/New_York):
   ```bash
   ssh office2-claude "openclaw cron add \
     --name inbox-morning \
     --cron '0 11 * * *' \
     --agent felix-admin-capture \
     --session isolated \
     --message 'Process the inbox now. Read all unprocessed files in 00-Inbox/, classify and route content per your standing orders, create Vikunja tasks for action items and research requests, route valid goal declarations, and write the processing log.' \
     --no-deliver \
     --timeout-seconds 300"

   ssh office2-claude "openclaw cron add \
     --name inbox-midday \
     --cron '0 16 * * *' \
     --agent felix-admin-capture \
     --session isolated \
     --message 'Process the inbox now.' \
     --no-deliver \
     --timeout-seconds 300"

   ssh office2-claude "openclaw cron add \
     --name inbox-evening \
     --cron '0 22 * * *' \
     --agent felix-admin-capture \
     --session isolated \
     --message 'Process the inbox now.' \
     --no-deliver \
     --timeout-seconds 300"
   ```
2. Verify: `ssh office2-claude "openclaw cron list"`
3. Note: 7 AM ET = 11:00 UTC (during EDT). Adjust for EST in winter.

**Validation**:
- [ ] 3 cron jobs created
- [ ] All target felix-admin-capture agent
- [ ] All use isolated sessions
- [ ] Timeout set to 5 minutes (300s)

### T021: Test Manual Cron Run

**Purpose**: Verify the full processing cycle works.

**Steps**:
1. Ensure there are unprocessed inbox notes on office2:
   ```bash
   ssh office2-claude "ls /home/kgale/second-brain/vault/00-Inbox/"
   ```
2. Run the morning job manually:
   ```bash
   ssh office2-claude "openclaw cron run inbox-morning"
   ```
3. Check results:
   - Processing log written: `ls /home/kgale/second-brain/agents/logs/`
   - Inbox files marked processed: check frontmatter status
   - Content routed to correct destinations
   - Vikunja tasks created (if any task items found)
4. If no unprocessed notes exist, create a test note first

**Validation**:
- [ ] Manual cron run completes without errors
- [ ] Processing log written
- [ ] At least one inbox note processed correctly

### T022: Verify Idempotency

**Purpose**: Confirm running twice produces the same result.

**Steps**:
1. After T021, run the job again:
   ```bash
   ssh office2-claude "openclaw cron run inbox-morning"
   ```
2. Verify: already-processed files are skipped (no new actions in the log)
3. Verify: no duplicate Vikunja tasks created

**Validation**:
- [ ] Second run skips already-processed files
- [ ] No duplicate tasks or content

## Definition of Done

- [ ] Goal declaration handling in AGENTS.md (validation, routing, flagging)
- [ ] 3 cron jobs configured and visible in `openclaw cron list`
- [ ] Manual cron run processes inbox notes correctly
- [ ] Idempotency verified
- [ ] Updated AGENTS.md deployed to office2

## Risks

- **Cron timezone**: UTC times must be correct for Eastern timezone.
  During EDT (Mar-Nov): ET = UTC-4. During EST (Nov-Mar): ET = UTC-5.
  If `--tz` flag works, use `America/New_York` instead of manual UTC calculation.
- **Agent timeout**: If processing 10+ notes takes >5 minutes, increase
  `--timeout-seconds`. Monitor first few runs.
- **Goals-MOC.md structure**: Read the current file to understand section
  structure before writing instructions to modify it.

## Activity Log

- 2026-03-31T03:13:05Z – claude-code – shell_pid=69931 – lane=doing – Assigned agent via workflow command
- 2026-03-31T03:22:28Z – claude-code – shell_pid=69931 – lane=for_review – Ready for review: Goal declaration handling with 3-element validation, dual routing (Goals-MOC.md + Vikunja), potential-goal flagging. 3 cron jobs configured. Manual test: processed 3 notes, 2 Vikunja tasks created, processing log written. Idempotency verified.
- 2026-03-31T03:28:59Z – claude-code – shell_pid=72973 – lane=doing – Started review via workflow command
- 2026-03-31T03:31:12Z – claude-code – shell_pid=72973 – lane=approved – Review passed: Goal declaration handling with 3-element validation, dual routing to Goals-MOC.md + Vikunja, potential-goal flagging with examples. 3 cron jobs verified on office2. Manual test: 3 notes processed, 2 Vikunja tasks, structured log. Idempotency confirmed.
