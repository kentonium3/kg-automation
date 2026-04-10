---
work_package_id: WP01
title: Add Identity Header to All Agents
dependencies: []
requirement_refs:
- FR-001
- FR-002
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T001
- T002
- T003
- T004
- T005
- T006
- T007
history:
- date: '2026-04-10T02:37:26Z'
  action: created
  by: spec-kitty.tasks
authoritative_surface: scripts/openclaw/agents/
execution_mode: code_change
owned_files:
- scripts/openclaw/agents/felix-admin-capture/AGENTS.md
- scripts/openclaw/agents/felix-admin-habits/AGENTS.md
- scripts/openclaw/agents/felix-admin-escalation/AGENTS.md
- scripts/openclaw/agents/felix-admin-tasker/AGENTS.md
tags: []
---

# WP01: Add Identity Header to All Agents

## Objective

Add a `Sent by <agent-id>:<model-short-name>` identity header as the first line of every WhatsApp message from all Felix agents. This is a standing-orders edit — find the output/summary format section in each agent's AGENTS.md and add the header instruction.

## Context

- All agent workspaces are on office2 under `/data/services/openclaw/`
- Access via `ssh office2-claude`
- Repo-side copies at `scripts/openclaw/agents/*/AGENTS.md`
- Tier 3 change (agent prompts) — no backup required
- The header uses hardcoded agent ID and model short name

**Agent-to-model mapping:**

| Agent ID | Model | Short Name | Workspace |
|---|---|---|---|
| felix-admin-capture | claude-haiku-4-5 | haiku | /data/services/openclaw/inbox-agent/ |
| felix-admin-habits | claude-sonnet-4-6 | sonnet | /data/services/openclaw/habits-agent/ |
| felix-admin-escalation | claude-sonnet-4-6 | sonnet | /data/services/openclaw/escalation-agent/ |
| felix-admin-tasker | claude-sonnet-4-6 | sonnet | /data/services/openclaw/tasker-agent/ |
| main | claude-sonnet-4-6 | sonnet | /data/services/openclaw/data/ |

## Branch Strategy

- Planning base: `main`
- Merge target: `main`
- Implementation command: `spec-kitty agent action implement WP01 --agent claude`

---

## Subtask T001: Add Header to felix-admin-capture

**Purpose**: The inbox agent sends processing summaries via WhatsApp. Add the identity header.

**Steps**:
1. SSH to office2, read `/data/services/openclaw/inbox-agent/AGENTS.md`
2. Find the processing summary format section (the section that defines what the WhatsApp message looks like)
3. Add this instruction at the start of the summary format:

   ```
   Begin every WhatsApp message with this identity line, followed by a blank line:

   Sent by felix-admin-capture:haiku
   ```

4. Place this instruction BEFORE the existing summary format content, so the agent knows the header comes first

**Example output after change:**
```
Sent by felix-admin-capture:haiku

Inbox processing complete — 2026-04-10
Files scanned: 28 | Unprocessed: 1
...
```

**Validation**:
- [ ] Header instruction added to AGENTS.md
- [ ] Instruction is clear: header is first line, blank line separates from body

---

## Subtask T002: Add Header to felix-admin-habits

**Purpose**: The habits agent sends check-in messages and weekly reports via WhatsApp.

**Steps**:
1. Read `/data/services/openclaw/habits-agent/AGENTS.md`
2. Find the output format section for WhatsApp messages (check-in delivery, weekly report)
3. Add the same header instruction pattern:

   ```
   Begin every WhatsApp message with this identity line, followed by a blank line:

   Sent by felix-admin-habits:sonnet
   ```

4. This applies to both daily check-in messages AND weekly report messages

**Example output:**
```
Sent by felix-admin-habits:sonnet

Morning check-in — Thursday, April 10:
1. Get steps in today
...
```

**Validation**:
- [ ] Header instruction added
- [ ] Applies to both daily and weekly message formats

---

## Subtask T003: Add Header to felix-admin-escalation

**Purpose**: The escalation agent sends alerts for overdue tasks via WhatsApp.

**Steps**:
1. Read `/data/services/openclaw/escalation-agent/AGENTS.md`
2. Find the alert message format section
3. Add the header instruction:

   ```
   Begin every WhatsApp message with this identity line, followed by a blank line:

   Sent by felix-admin-escalation:sonnet
   ```

**Example output:**
```
Sent by felix-admin-escalation:sonnet

⚠️ Tasks needing attention:
1. [Inbox] Check red van tire pressure...
...
```

**Validation**:
- [ ] Header instruction added to escalation alert format

---

## Subtask T004: Add Header to felix-admin-tasker

**Purpose**: The tasker agent sends task proposals to Kent for confirmation via WhatsApp.

**Steps**:
1. Read `/data/services/openclaw/tasker-agent/AGENTS.md`
2. Find the section where the agent formats messages to Kent (task proposals, confirmations)
3. Add the header instruction:

   ```
   Begin every WhatsApp message with this identity line, followed by a blank line:

   Sent by felix-admin-tasker:sonnet
   ```

**Validation**:
- [ ] Header instruction added to tasker message format

---

## Subtask T005: Investigate and Add Header to Main Agent

**Purpose**: The main agent runs health checks and delivers results via WhatsApp. Its configuration may differ from the named agents.

**Steps**:
1. Check if the main agent has an AGENTS.md or equivalent in its workspace:
   - `/data/services/openclaw/data/AGENTS.md`
   - Or check if health check output format is defined in the health check skill
2. Find where the health check WhatsApp output format is controlled
3. If found, add the header instruction:

   ```
   Sent by main:sonnet
   ```

4. If the main agent uses a built-in skill that doesn't have an editable output format, document this limitation and skip

**Validation**:
- [ ] Main agent output format location identified
- [ ] Header added if editable, limitation documented if not

---

## Subtask T006: Sync to Repo

**Purpose**: Keep repo-side copies in sync with office2.

**Steps**:
1. Copy updated AGENTS.md files from office2 to repo:
   - `/data/services/openclaw/inbox-agent/AGENTS.md` → `scripts/openclaw/agents/felix-admin-capture/AGENTS.md`
   - `/data/services/openclaw/habits-agent/AGENTS.md` → `scripts/openclaw/agents/felix-admin-habits/AGENTS.md`
   - `/data/services/openclaw/escalation-agent/AGENTS.md` → `scripts/openclaw/agents/felix-admin-escalation/AGENTS.md`
   - `/data/services/openclaw/tasker-agent/AGENTS.md` → `scripts/openclaw/agents/felix-admin-tasker/AGENTS.md`
2. Only copy files that were actually modified (skip main if T005 wasn't applicable)

**Validation**:
- [ ] Repo copies match office2 versions
- [ ] Diff shows only the header instruction additions

---

## Subtask T007: Verify with Live Test

**Purpose**: Confirm the header appears in actual WhatsApp output.

**Steps**:
1. Trigger one inbox processing run: `openclaw cron run <inbox-7am-id>`
2. Wait for completion
3. Check the latest session for the assistant's final output — verify it starts with `Sent by felix-admin-capture:haiku`
4. If Kent receives the WhatsApp message, confirm the header is visible

**Validation**:
- [ ] Triggered agent run completed
- [ ] Output starts with identity header
- [ ] Header format matches spec: `Sent by <agent-id>:<model>`

---

## Definition of Done

- [ ] All 4 named agents (capture, habits, escalation, tasker) have the header instruction
- [ ] Main agent investigated — header added or limitation documented
- [ ] Repo copies synced
- [ ] At least one agent verified with live test
- [ ] Header format: `Sent by <agent-id>:<model-short-name>` as first line

## Risks

- **Main agent may not have an editable output format**: Document and skip if so
- **Haiku may not follow the header instruction**: The inbox agent runs on Haiku. If it ignores the header, the instruction may need to be more prominent or repeated

## Reviewer Guidance

- Verify the header instruction is placed where the agent will see it when composing WhatsApp output
- Check that the model short name matches the agent's configured model from mission 021
- Confirm repo copies match office2 exactly
