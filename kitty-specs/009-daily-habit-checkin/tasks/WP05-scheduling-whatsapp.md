---
work_package_id: WP05
title: Scheduling and WhatsApp Integration
lane: "doing"
dependencies: [WP04]
requirement_refs:
- FR-003
- FR-005
- FR-008
- FR-009
- NFR-001
- NFR-002
- NFR-003
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: 009-daily-habit-checkin-WP04
base_commit: bfaff56d4e61ead85480b258bc288b7a3fabafe0
created_at: '2026-04-01T03:40:38.251027+00:00'
subtasks: [T019, T020, T021, T022, T023, T024, T025]
shell_pid: "97929"
agent: "claude-code"
history:
- date: '2026-04-01T01:46:04Z'
  event: created
  actor: claude
---

# WP05: Scheduling and WhatsApp Integration

## Implementation command

```bash
spec-kitty implement WP05 --base WP04
```

## Objective

Add cron jobs for the morning check-in and weekly report, patch the main
agent with habits delegation, and test the full WhatsApp interaction loop
end-to-end.

## Context

- **Agent contract**: `kitty-specs/009-daily-habit-checkin/contracts/openclaw-habits-agent-contract.md` — cron specs and delegation patch
- **F008 pattern**: inbox-morning cron uses `--no-deliver`. F009 crons OMIT `--no-deliver` so output reaches WhatsApp.
- **Main agent AGENTS.md on office2**: `/data/services/openclaw/data/AGENTS.md`
- **F008 delegation patch**: `scripts/openclaw/agents/main-patches/inbox-delegation.md` — follow same pattern
- **Open question**: Whether omitting `--no-deliver` is sufficient or if `--announce` is needed. Test during T022.

## Subtask guidance

### T019: Add morning check-in cron job

**Purpose**: Schedule the daily check-in delivery.

**Steps**:
1. Add the cron job (note: NO `--no-deliver` flag):
   ```bash
   ssh office2-claude "openclaw cron add \
     --name habits-morning-checkin \
     --cron '5 11 * * *' \
     --agent felix-admin-habits \
     --session isolated \
     --message 'Generate today'\''s habit check-in. Query Vikunja for active habits scheduled for today, exclude any already marked complete, and deliver the check-in message.' \
     --timeout-seconds 120"
   ```
2. Verify: `ssh office2-claude "openclaw cron list"`

**Validation**:
- [ ] Cron job created at 11:05 UTC (7:05 AM ET during EDT)
- [ ] Targets felix-admin-habits agent
- [ ] Uses isolated session
- [ ] Does NOT use `--no-deliver`

### T020: Add weekly report cron job

**Purpose**: Schedule the Sunday evening pattern report.

**Steps**:
1. Add the cron job:
   ```bash
   ssh office2-claude "openclaw cron add \
     --name habits-weekly-report \
     --cron '0 22 * * 0' \
     --agent felix-admin-habits \
     --session isolated \
     --message 'Generate the weekly habit pattern report. Compare this week vs. last week for each habit and overall.' \
     --timeout-seconds 120"
   ```
2. Verify: `ssh office2-claude "openclaw cron list"`

**Validation**:
- [ ] Cron job created at 22:00 UTC Sunday (6 PM ET during EDT)
- [ ] Does NOT use `--no-deliver`

### T021: Patch main agent with habits delegation

**Purpose**: Teach the main agent to delegate habit messages to felix-admin-habits.

**Steps**:
1. Read the current main agent AGENTS.md:
   ```bash
   ssh office2-claude "cat /data/services/openclaw/data/AGENTS.md"
   ```
2. Append the habits delegation section (see agent contract for exact text):
   ```markdown
   ## Habit tracking delegation

   When Kent sends a message about habits — completing a habit ("meditation
   done", "did my steps", "skipped training"), asking about habit status
   ("how am I doing on habits?", "show my track record"), or managing habits
   ("add daily journaling", "pause steps habit"):

   1. Delegate to felix-admin-habits:
      ```bash
      openclaw agent --agent felix-admin-habits \
        --message "<Kent's exact message>" --json --timeout 120
      ```
   2. Relay the result back to Kent via WhatsApp.

   Do NOT handle habit tracking yourself. felix-admin-habits has the standing
   orders, Vikunja project access, and completion state logic.
   ```
3. Save a copy in the repo at `scripts/openclaw/agents/main-patches/habits-delegation.md`
4. Restart the gateway to pick up the change:
   ```bash
   ssh office2-claude "systemctl --user restart openclaw-gateway"
   ```

**Validation**:
- [ ] Main agent AGENTS.md updated on office2
- [ ] Repo copy saved at main-patches/habits-delegation.md
- [ ] Gateway restarted

### T022: Test proactive check-in delivery via WhatsApp

**Purpose**: Verify that the cron job delivers the check-in to Kent's WhatsApp.

**Steps**:
1. Trigger the morning check-in cron manually:
   ```bash
   ssh office2-claude "openclaw cron run <habits-morning-checkin-uuid>"
   ```
2. Check if the message was delivered to Kent's WhatsApp
3. If `--no-deliver` omission doesn't work, try adding `--announce` flag
   to the cron job and re-test
4. If neither works, document the limitation and use the main agent delegation
   as a workaround (trigger via `openclaw agent --agent felix-admin-habits`)

**Validation**:
- [ ] Check-in message reaches Kent's WhatsApp
- [ ] Message lists today's scheduled habits
- [ ] Format is concise (<=10 lines)
- [ ] OR: limitation documented with workaround

### T023: Test completion marking via WhatsApp reply

**Purpose**: Verify Kent can mark habits complete via WhatsApp.

**Steps**:
1. Send a test message through the main agent simulating Kent's reply:
   ```bash
   ssh office2-claude "openclaw agent --agent main \
     --message 'meditation done, skipped training' --json --timeout 120"
   ```
2. Verify the main agent delegates to felix-admin-habits
3. Verify completion comments are created in Vikunja
4. Verify confirmation message is sent back
5. Test idempotency: send the same message again, verify update not duplicate

**Validation**:
- [ ] Main agent delegates correctly
- [ ] Vikunja comments created with correct format
- [ ] Confirmation sent back
- [ ] Idempotent on repeat

### T024: Test weekly report delivery

**Purpose**: Verify the weekly report reaches WhatsApp.

**Steps**:
1. Ensure there are some completion records (from T022/T023 testing)
2. Trigger the weekly report cron manually:
   ```bash
   ssh office2-claude "openclaw cron run <habits-weekly-report-uuid>"
   ```
3. Verify the report is delivered via WhatsApp
4. If delivery doesn't work, test via direct agent invocation

**Validation**:
- [ ] Report reaches WhatsApp OR limitation documented
- [ ] Report shows per-habit rates
- [ ] Format is concise (<=20 lines)

### T025: Verify full interaction loop

**Purpose**: End-to-end verification of the complete flow.

**Steps**:
1. Trigger morning check-in → verify delivery
2. Reply with completions → verify recording and confirmation
3. Ask "how am I doing on habits?" → verify track record response
4. Trigger weekly report → verify delivery
5. Clean up any test data if needed

**Validation**:
- [ ] Full loop works: cron → check-in → reply → recorded → confirmed
- [ ] Track record query returns data
- [ ] Weekly report generates from recorded data

## Definition of done

- [ ] 2 cron jobs configured and visible in `openclaw cron list`
- [ ] Main agent has habits delegation instruction
- [ ] Check-in delivery tested via WhatsApp (working or limitation documented)
- [ ] Completion marking tested via WhatsApp
- [ ] Weekly report tested
- [ ] Full loop verified end-to-end

## Risks

- **Cron delivery to WhatsApp may not work without --no-deliver**: The exact
  mechanism for delivering cron output to WhatsApp needs testing. If it doesn't
  work, the workaround is to have the agent explicitly use a delivery tool.
- **Main agent may not classify habit messages correctly**: Test with varied
  natural language. Iterate on the delegation prompt if needed.
- **Session lock conflicts**: If the habits agent session is locked from a
  previous run, clear locks before testing.

## Activity Log

- 2026-04-01T03:40:38Z – claude-code – shell_pid=97929 – lane=doing – Assigned agent via workflow command
