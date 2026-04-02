---
work_package_id: WP04
title: Inbox Processor Handoff Update
dependencies: [WP03]
requirement_refs:
- FR-017
- FR-018
- FR-019
- FR-020
planning_base_branch: main
merge_target_branch: main
branch_strategy: 'Planning branch: main. Merge target: main. Depends on WP03 — use: spec-kitty implement WP04 --base WP03'
subtasks: [T018, T019, T020, T021, T022]
history:
- date: '2026-04-02T12:53:14Z'
  action: created
  by: spec-kitty.tasks
authoritative_surface: scripts/openclaw/agents/felix-admin-capture/
execution_mode: code_change
owned_files: [scripts/openclaw/agents/felix-admin-capture/AGENTS.md]
---

# WP04: Inbox Processor Handoff Update

## Objective

Update felix-admin-capture's AGENTS.md to delegate raw task descriptions to felix-admin-tasker instead of creating flat tasks directly in Vikunja. The update must preserve all existing behavior while adding the delegation path, implement a fallback to flat task creation when the tasker is unavailable, and ensure no tasks are lost during the transition.

## Context

- **Feature**: 013-vikunja-task-intelligence-agent (FR-017, FR-018, FR-019, FR-020)
- **Current capture agent**: `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` — read this thoroughly before modifying
- **Delegation contract**: `kitty-specs/013-vikunja-task-intelligence-agent/contracts/agent-delegation-contract.md`
- **Key principle**: The inbox processor's role ends at classification ("this is a task"). Structuring begins with felix-admin-tasker.

### Implementation command

```bash
spec-kitty implement WP04 --base WP03
```

## Branch Strategy

- **Planning base branch**: `main`
- **Merge target**: `main`
- **Dependencies**: WP03 (agent standing orders must exist for handoff to make sense)
- **Actual base branch**: WP03's branch (stacked) — follow `spec-kitty implement` output

---

## Subtask T018: Add Delegation Section to felix-admin-capture AGENTS.md

**Purpose**: Add a new section to the capture agent's standing orders that delegates task creation to felix-admin-tasker.

**Steps**:
1. Read `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` thoroughly — understand the current task bridge section
2. Locate the **Task Bridge — Vikunja Task Creation** section (this is what currently creates flat tasks)
3. Add a new section **before** the existing task bridge, titled **Task Delegation to felix-admin-tasker**:
   ```markdown
   ### Task Delegation to felix-admin-tasker

   When content is classified as an action item or research request, delegate
   to felix-admin-tasker instead of creating a flat Vikunja task directly.

   **Delegation command**:
   ```bash
   openclaw agent --agent felix-admin-tasker \
     --message '<JSON payload>' \
     --json --timeout 120
   ```

   **Payload**: Build JSON with:
   - action: "enrich_task"
   - raw_text: the task description extracted from the inbox note
   - source_reference: path to the originating inbox file
   - inferred_identity: identity label you inferred (personal/intentional/metalcasework)
   - date_signals: any date/time references you found in the text
   - context_signals: keywords suggesting project, priority, or goal
   ```
4. Mark the existing flat task creation as the **fallback path** (see T020)

**Validation**:
- [ ] Delegation section added to AGENTS.md
- [ ] Payload format matches agent-delegation-contract.md
- [ ] Existing task bridge section preserved as fallback
- [ ] No existing behavior broken

---

## Subtask T019: Define Delegation Message Payload Format

**Purpose**: Document the exact JSON payload format within the capture agent's standing orders so the agent constructs it correctly.

**Steps**:
1. In the delegation section, add a detailed payload construction guide:
   ```markdown
   **Building the delegation payload**:

   From the inbox note content you have already extracted:
   1. raw_text — the task description (you already have this from classification)
   2. source_reference — the inbox file path (e.g., "00-Inbox/2026-04-02-voice-note.md")
   3. inferred_identity — apply your existing identity inference rules:
      - intentional: business, consulting, client, revenue, marketing
      - metalcasework: metal casework, fabrication, ecommerce
      - personal: everything else (default)
   4. date_signals — extract any date/time phrases from the raw text:
      - Look for: "next week", "by Friday", "April 15", "tomorrow", "end of month"
      - Pass as array of strings, preserving original phrasing
   5. context_signals — extract project/priority/goal hints:
      - Look for: project names, priority words ("urgent", "important"), goal references
      - Pass as array of strings

   **Example**:
   ```json
   {
     "action": "enrich_task",
     "raw_text": "Schedule appointment with PT for knee follow-up",
     "source_reference": "00-Inbox/2026-04-02-voice-dump.md",
     "inferred_identity": "personal",
     "date_signals": [],
     "context_signals": ["PT", "knee", "health"]
   }
   ```
   ```

2. Ensure the payload construction uses information the capture agent already has — no additional API calls or file reads required

**Validation**:
- [ ] Payload construction guide is clear and actionable
- [ ] All fields from agent-delegation-contract.md are covered
- [ ] Example provided
- [ ] No new information gathering required (uses existing classification output)

---

## Subtask T020: Implement Fallback to Flat Task Creation

**Purpose**: If delegation to felix-admin-tasker fails, the capture agent falls back to creating a flat task in Vikunja Inbox (preserving the existing behavior so no tasks are lost).

**Steps**:
1. Add fallback logic to the delegation section:
   ```markdown
   **Fallback**: If delegation fails (timeout, error, or agent unavailable):
   1. Log the failure: "felix-admin-tasker delegation failed: {reason}. Falling back to flat task creation."
   2. Create the task using the existing Task Bridge procedure below (flat task in Inbox)
   3. Add a comment to the flat task: "[Felix] enrichment | pending | {timestamp} | delegation fallback — tasker unavailable"
   4. Continue processing remaining inbox files — do not halt

   **Delegation is considered failed if**:
   - Command returns non-zero exit code
   - Response JSON has "status": "error" with "fallback_required": true
   - Command times out (120 seconds)
   ```

2. Update the existing task bridge section header to indicate it's the fallback path:
   ```markdown
   ### Task Bridge — Vikunja Task Creation (Fallback)

   **This section is the fallback path** when felix-admin-tasker delegation
   fails. The primary path is delegation (section above).

   [... existing content unchanged ...]
   ```

**Validation**:
- [ ] Fallback logic clearly defined
- [ ] All failure modes covered (timeout, error, unavailable)
- [ ] Flat task gets enrichment comment for later pickup by tasker's polling
- [ ] Existing task bridge behavior preserved unchanged
- [ ] Processing continues after fallback (no halt)

---

## Subtask T021: Update Task Bridge Documentation

**Purpose**: Update inline documentation and comments to reflect the new delegation-first, fallback-second architecture.

**Steps**:
1. Update the routing table entry for "Action items" and "Research requests" to indicate delegation:
   - Change from: "→ Create Vikunja task in Inbox/Research project"
   - Change to: "→ Delegate to felix-admin-tasker (fallback: create flat Vikunja task)"

2. Add a note at the top of the task-related sections:
   ```markdown
   **Note (F013)**: Task creation now delegates to felix-admin-tasker for
   intelligent structuring. The flat task bridge is preserved as fallback
   only. See "Task Delegation" section above.
   ```

3. Ensure no other sections reference the old direct-creation path as the primary path

**Validation**:
- [ ] Routing table updated
- [ ] F013 note added
- [ ] No references to flat task creation as the primary path

---

## Subtask T022: Define No-Gap Deployment Procedure

**Purpose**: Document how to transition from flat task creation to delegation without losing any tasks.

**Steps**:
1. Add a deployment note section (can be a comment block or a separate section at the end):
   ```markdown
   <!-- F013 Deployment Note:
   To transition to delegation without losing tasks:
   1. Deploy felix-admin-tasker workspace and skill to office2 FIRST
   2. Verify tasker responds to manual test delegation
   3. THEN update this AGENTS.md on office2 with the delegation section
   4. The fallback path ensures any in-flight tasks during the transition
      land as flat tasks in Inbox if tasker is not yet ready
   5. felix-admin-tasker's detect_incomplete polling will catch any flat
      tasks created during the transition window
   -->
   ```

2. The key insight: deploy the tasker first, then update the capture agent. The fallback path and polling detection create a safety net.

**Validation**:
- [ ] Deployment order is clear: tasker first, capture update second
- [ ] Safety net explained (fallback + polling)
- [ ] No-gap guarantee documented

---

## Definition of Done

- [ ] felix-admin-capture AGENTS.md updated with delegation section
- [ ] Delegation payload format documented with example
- [ ] Fallback to flat task creation implemented
- [ ] Existing task bridge behavior preserved unchanged
- [ ] Routing table and documentation updated
- [ ] No-gap deployment procedure documented
- [ ] No tasks can be lost during transition

## Risks

- **Modifying a production agent**: felix-admin-capture is actively running on office2. Changes must preserve all existing behavior.
- **Delegation timeout**: If felix-admin-tasker is slow to respond, 120-second timeout may not be enough. The fallback handles this gracefully.

## Reviewer Guidance

- Read the current AGENTS.md carefully before reviewing changes
- Verify ALL existing behavior is preserved — the delegation is additive, not a replacement
- Check that the delegation payload matches `contracts/agent-delegation-contract.md` exactly
- Verify fallback covers all failure modes
- Confirm the flat task gets an enrichment comment for later pickup
- Check deployment order: tasker first, capture update second
