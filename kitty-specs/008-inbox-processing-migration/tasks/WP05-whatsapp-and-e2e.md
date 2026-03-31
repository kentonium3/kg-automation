---
work_package_id: WP05
title: WhatsApp Trigger and End-to-End Test
lane: "doing"
dependencies: [WP04]
requirement_refs:
- C-007
- FR-022
- FR-023
- FR-025
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: 008-inbox-processing-migration-WP04
base_commit: aa93b5727523d7098b41cae718db38ab3f9fdc6c
created_at: '2026-03-31T03:35:07.379677+00:00'
subtasks: [T023, T024, T025]
agent: "claude-code"
shell_pid: "78580"
history:
- date: '2026-03-31T02:04:57Z'
  event: created
  actor: claude
---

# WP05: WhatsApp Trigger and End-to-End Test

## Implementation Command

```bash
spec-kitty implement WP05 --base WP04
```

## Objective

Add an inbox-trigger instruction to the main agent so it can delegate
"process my inbox" requests from WhatsApp to felix-admin-capture. Then run
a comprehensive end-to-end test covering all content types.

**Note**: The WhatsApp trigger depends on OpenClaw's ability to invoke
another agent or cron job from within an agent turn. If this doesn't work,
document the limitation and defer FR-022/FR-023.

## Context

- **Main agent workspace**: `/data/services/openclaw/data/` on office2
- **Main agent AGENTS.md**: `~/.openclaw/workspace/AGENTS.md` (default)
- **Cron job name**: `inbox-morning` (or any of the 3 jobs)
- **Alternative approach**: `openclaw agent --agent felix-admin-capture --message "..."`

## Subtask Guidance

### T023: Add Inbox-Trigger Instruction to Main Agent

**Purpose**: Teach the main agent to recognize inbox processing requests
and delegate to felix-admin-capture.

**Steps**:
1. Read the main agent's current AGENTS.md:
   ```bash
   ssh office2-claude "cat ~/.openclaw/workspace/AGENTS.md"
   ```
2. Add an instruction block (append, don't overwrite):
   ```markdown
   ## Inbox Processing Delegation

   When Kent asks to "process my inbox", "check my inbox", "run inbox
   processing", or any natural variation of processing Obsidian inbox
   captures:

   1. Trigger the inbox processing agent by running:
      ```bash
      openclaw cron run inbox-morning
      ```
   2. Wait for the result
   3. Read the latest processing log:
      ```bash
      ls -t /home/kgale/second-brain/agents/logs/inbox-processing-*.md | head -1
      ```
   4. Summarize the results back to Kent: files processed, tasks created,
      items flagged for review

   Do NOT process the inbox yourself. The felix-admin-capture agent handles
   this with specific standing orders and kent-voice encoding.
   ```
3. Deploy the updated AGENTS.md:
   ```bash
   ssh office2-claude "cat > ~/.openclaw/workspace/AGENTS.md" < <updated-file>
   ```

**Validation**:
- [ ] Main agent AGENTS.md has inbox delegation instruction
- [ ] Trigger command uses `openclaw cron run`
- [ ] Agent instructed to summarize results, not process inbox itself

**Fallback**: If `openclaw cron run` doesn't work from within an agent turn,
try:
```bash
openclaw agent --agent felix-admin-capture --message "Process the inbox now." --json
```
If neither works, document the limitation and note that WhatsApp triggering
requires a future OpenClaw feature.

### T024: Test WhatsApp Trigger

**Purpose**: Verify the WhatsApp-to-inbox-processing chain works.

**Steps**:
1. Ensure there are unprocessed inbox notes (create a test note if needed)
2. Send "process my inbox" via WhatsApp to the OpenClaw number
3. Verify:
   - Main agent recognizes the intent
   - felix-admin-capture runs
   - Processing log is written
   - Main agent responds with a summary
4. Test natural variations: "check my inbox", "run inbox processing"

**If WhatsApp trigger fails**:
- Document which step failed (intent recognition, cron run, result relay)
- Note the error in the processing log or agent response
- File as a known limitation for future resolution

**Validation**:
- [ ] WhatsApp trigger works OR limitation documented
- [ ] If working: responds with processing summary

### T025: Comprehensive End-to-End Test

**Purpose**: Verify the full processing cycle with all content types.

**Steps**:
1. Create test inbox notes covering multiple content types:
   - A note with a values statement and a task item
   - A note with a research request
   - A note with a valid Felix goal declaration
   - A note with an aspirational (not valid) goal
   - A note with journal-style reflection
   - An empty note (frontmatter only)
2. Run the agent:
   ```bash
   ssh office2-claude "openclaw cron run inbox-morning"
   ```
3. Verify each content type was handled correctly:
   - [ ] Values → integrated into 01-Constitution/Values.md
   - [ ] Task → Vikunja task in Inbox project with label
   - [ ] Research → Vikunja task in Research project
   - [ ] Valid goal → Goals-MOC.md + Vikunja Goals project
   - [ ] Aspirational → flagged as potential-goal in log
   - [ ] Journal → new entry in 06-Journal/
   - [ ] Empty → marked processed, noted in log
4. Verify processing log completeness
5. Verify no content routed to 02-Growth/_private/
6. **Clean up test data**: remove test inbox notes and any test Vikunja tasks

**Validation**:
- [ ] All content types classified and routed correctly
- [ ] Processing log is complete and accurate
- [ ] Privacy boundary not violated
- [ ] Test data cleaned up

## Definition of Done

- [ ] Main agent has inbox delegation instruction
- [ ] WhatsApp trigger tested (working or limitation documented)
- [ ] End-to-end test covers all content types
- [ ] All routing correct, privacy boundary enforced
- [ ] Test data cleaned up

## Risks

- **openclaw cron run may not work from agent turn**: The mechanics of
  invoking a cron job from within an agent's exec tool are untested. Have
  the fallback approach ready.
- **Test inbox notes may sync**: Creating test notes on office2 may sync
  to Mac/iPhone via Obsidian Sync. Clean up promptly to avoid confusion.

## Activity Log

- 2026-03-31T03:35:07Z – claude-code – shell_pid=74032 – lane=doing – Assigned agent via workflow command
- 2026-03-31T03:59:18Z – claude-code – shell_pid=74032 – lane=for_review – Ready for review: Main agent patched with inbox delegation (openclaw agent --agent fallback since cron run by name unsupported). WhatsApp delegation verified — main agent recognizes intent and invokes felix-admin-capture. E2E test: goal declaration routed to Goals-MOC.md + Vikunja, gap audit filled 5 missing tasks. Test data cleaned up.
- 2026-03-31T04:00:17Z – claude-code – shell_pid=78580 – lane=doing – Started review via workflow command
