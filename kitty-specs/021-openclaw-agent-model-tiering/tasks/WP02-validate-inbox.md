---
work_package_id: WP02
title: Validate Inbox Agent on Haiku
dependencies: [WP01]
requirement_refs:
- FR-001
- FR-003
planning_base_branch: main
merge_target_branch: main
branch_strategy: Branch from WP01 if stacked, or from main
subtasks: [T004, T005]
history:
- date: '2026-04-09T17:18:21Z'
  action: created
  by: spec-kitty.tasks
authoritative_surface: ''
execution_mode: code_change
owned_files: []
---

# WP02: Validate Inbox Agent on Haiku

## Objective

Test whether `felix-admin-capture` (inbox classification and routing agent) produces acceptable results when running on the cheaper Haiku model. This is the simplest agent, highest-volume (8 runs/day), and biggest cost savings target — making it the ideal first validation candidate.

## Context

- Agent: `felix-admin-capture`
- Workspace: `/data/services/openclaw/inbox-agent/`
- Agent dir: `/home/claude/.openclaw/agents/felix-admin-capture/agent/`
- Task: Scans Obsidian inbox (`/home/kgale/second-brain/notes/00-Inbox/`), classifies notes by content type, routes to appropriate vault destinations, creates Vikunja tasks
- Current model: `anthropic/claude-sonnet-4-6`
- Candidate model: `anthropic/claude-haiku-4-5`
- Runs 8×/day — highest-volume agent, most cost savings potential
- Access via `ssh office2-claude`

## Branch Strategy

- Planning base: `main`
- Merge target: `main`
- Implementation command: `spec-kitty implement WP02 --base WP01`

---

## Subtask T004: Collect Recent Production Inputs

**Purpose**: Gather representative inbox items that the agent has recently processed, to use as validation test inputs.

**Steps**:
1. SSH to office2: `ssh office2-claude`
2. Find recent agent session logs:
   - Check `/home/claude/.openclaw/agents/felix-admin-capture/sessions/sessions.json`
   - Look for recent session entries with prompts and responses
3. Identify 3-5 recent inbox processing runs where we can see:
   - What inbox files were present (input)
   - How the agent classified and routed them (output)
   - Whether any Vikunja tasks were created
4. If session logs don't have clear input/output pairs, check:
   - Recently processed files in the Obsidian vault (look for `status: processed` frontmatter)
   - The agent's workspace for any processing logs
5. Extract representative samples covering:
   - A straightforward note (single topic, clear classification)
   - A multi-topic note (WisprFlow voice transcription with multiple content types)
   - A typed quick note (different format from voice transcription)
6. Document each sample: input content, Sonnet's classification/routing decision, any Vikunja tasks created

**Important**: Do NOT modify any inbox files or agent state. This is read-only collection.

**Validation**:
- [ ] At least 3 representative input samples collected
- [ ] Each sample has the corresponding Sonnet output/decision documented
- [ ] Samples cover different content types (voice transcription, typed note, multi-topic)

---

## Subtask T005: Run Inbox Agent on Haiku and Compare

**Purpose**: Temporarily switch the inbox agent to Haiku, run it against the collected inputs, and compare output quality to the Sonnet baseline.

**Steps**:
1. SSH to office2: `ssh office2-claude`
2. **Prepare test conditions**:
   - Ensure there are unprocessed inbox files available for the agent to process
   - If needed, create test inbox files that mirror the collected samples (with `status: unprocessed`)
   - Put test files in a location the agent will scan
3. **Temporarily change the model**:
   - Edit `/home/claude/.openclaw/openclaw.json`
   - Change `felix-admin-capture`'s `model` field from `anthropic/claude-sonnet-4-6` to `anthropic/claude-haiku-4-5`
4. **Trigger a run**:
   - Determine how to manually trigger the inbox agent (cron-like invocation or OpenClaw command)
   - Run the agent and capture its output
5. **Compare results**:
   - For each test input, compare Haiku's classification/routing to Sonnet's baseline:
     - Did it identify the same content types?
     - Did it route to the same destinations?
     - Did it create equivalent Vikunja tasks?
     - Is the output quality (prose, structure) acceptable?
6. **Record pass/fail**:
   - PASS: Haiku produces functionally equivalent routing and classification
   - FAIL: Haiku misroutes content, misses content types, or produces significantly degraded output
7. **Revert model** after testing:
   - Change the `model` field back to `anthropic/claude-sonnet-4-6`
   - This prevents production impact if the next scheduled run fires before WP04 deploys

**Quality comparison criteria**:
- Content type classification: Must match Sonnet's decisions
- Routing destination: Must match Sonnet's decisions
- Vikunja task creation: Must create equivalent tasks (title, project, labels)
- Prose quality: Acceptable if functionally correct even if less polished

**Validation**:
- [ ] Haiku run completed successfully (no errors)
- [ ] At least 3 input samples compared to Sonnet baseline
- [ ] Classification accuracy matches Sonnet
- [ ] Routing decisions match Sonnet
- [ ] Pass/fail documented with specific observations
- [ ] Model reverted to Sonnet after testing

---

## Definition of Done

- [ ] 3+ representative inputs collected with Sonnet baseline
- [ ] Haiku validation run completed
- [ ] Quality comparison documented (pass/fail per criterion)
- [ ] Model reverted to Sonnet after testing
- [ ] Clear recommendation: Haiku is acceptable / not acceptable for this agent

## Risks

- **No unprocessed inbox files available**: Create synthetic test files mirroring real samples
- **Agent trigger mechanism unclear**: Check OpenClaw docs or session logs for how cron runs are invoked
- **Haiku run triggers side effects**: Test files may be routed to real vault locations — use clearly-marked test content that can be cleaned up

## Reviewer Guidance

- Focus on routing accuracy — did Haiku route the same content to the same places?
- Multi-topic notes are the hardest case — verify Haiku extracts all topics, not just the first
- Check that the model was reverted after testing
