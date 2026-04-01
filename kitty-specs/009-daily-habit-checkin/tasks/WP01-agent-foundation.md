---
work_package_id: WP01
title: Agent Workspace Foundation
lane: "doing"
dependencies: []
requirement_refs:
- C-001
- C-004
- C-005
- C-008
- FR-001
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: main
base_commit: a627f3e6cc4b3da947a336e243792f4388792cec
created_at: '2026-04-01T03:09:01.064952+00:00'
subtasks: [T001, T002, T003, T004, T005]
shell_pid: "90925"
agent: "claude-code"
history:
- date: '2026-04-01T01:46:04Z'
  event: created
  actor: claude
---

# WP01: Agent Workspace Foundation

## Implementation command

```bash
spec-kitty implement WP01
```

## Objective

Create the felix-admin-habits agent's workspace files, register the agent
with OpenClaw on office2, deploy the workspace, and verify the agent is
operational.

## Context

- **Repo location for workspace files**: `scripts/openclaw/agents/felix-admin-habits/`
- **Deploy target on office2**: `/data/services/openclaw/habits-agent/`
- **Existing agent pattern**: `scripts/openclaw/agents/felix-admin-capture/` — reuse SOUL.md and USER.md structure
- **kent-voice source**: `~/second-brain/.claude/skills/kent-voice/SKILL.md` (read locally)
- **Agent contract**: `kitty-specs/009-daily-habit-checkin/contracts/openclaw-habits-agent-contract.md`

## Subtask guidance

### T001: Write SOUL.md with kent-voice identity

**Purpose**: Define the agent's authoring identity so all WhatsApp content
sounds like Kent, not generic AI.

**Steps**:
1. Read `scripts/openclaw/agents/felix-admin-capture/SOUL.md` — this is the
   pattern to follow
2. Create `scripts/openclaw/agents/felix-admin-habits/SOUL.md`
3. Copy the kent-voice principles from felix-admin-capture's SOUL.md
4. Change the agent purpose to: "You are felix-admin-habits. Your sole
   purpose is managing Kent's daily habit check-ins. You deliver morning
   check-ins via WhatsApp, record completion state in Vikunja, generate
   weekly pattern reports, and manage habit additions and removals."
5. Keep the privacy boundary: "NEVER read, process, route to, or reference
   `02-Growth/_private/`. This is absolute."

**Files**: `scripts/openclaw/agents/felix-admin-habits/SOUL.md` (new)

**Validation**:
- [ ] Kent-voice principles encoded (first person, direct, structured)
- [ ] Agent purpose states habit check-in scope
- [ ] Privacy boundary stated

### T002: Write USER.md, IDENTITY.md, TOOLS.md

**Purpose**: Complete the workspace with Kent's context, agent identity, and
tool references.

**Steps**:
1. Create `scripts/openclaw/agents/felix-admin-habits/USER.md`:
   - Copy from felix-admin-capture's USER.md
   - Update context: "Kent tracks recurring commitments (habits) to build
     accountability. Your job is to deliver daily check-ins, record completions,
     and report on patterns over time."

2. Create `scripts/openclaw/agents/felix-admin-habits/IDENTITY.md`:
   ```markdown
   # IDENTITY.md

   - **Name:** Felix (Habits)
   - **Creature:** Habit accountability agent
   - **Vibe:** Encouraging, consistent, concise
   - **Emoji:** ✅
   ```

3. Create `scripts/openclaw/agents/felix-admin-habits/TOOLS.md`:
   ```markdown
   # TOOLS.md

   ## Vikunja API
   - Use the vikunja_api skill for all Vikunja operations
   - Run `openclaw skills info vikunja_api` for details
   - **Habits project**: resolve by name "Habits" at runtime

   ## Habit completion storage
   - Each habit = one task in the Habits project
   - Daily completion = comment on the habit task
   - Comment format: `[Felix] YYYY-MM-DD | {complete|rescheduled|will-not-do} | optional note`

   ## Privacy
   - NEVER access: `/home/kgale/second-brain/vault/02-Growth/_private/`
   ```

**Files**: USER.md, IDENTITY.md, TOOLS.md (all new in
`scripts/openclaw/agents/felix-admin-habits/`)

### T003: Create felix-admin-habits agent on office2

**Purpose**: Register the agent with OpenClaw.

**Steps**:
1. SSH to office2:
   ```bash
   ssh office2-claude "openclaw agents add felix-admin-habits \
     --workspace /data/services/openclaw/habits-agent \
     --model anthropic/claude-sonnet-4-6 \
     --non-interactive"
   ```
2. Verify: `ssh office2-claude "openclaw agents list"`
3. Expected: felix-admin-habits appears with workspace
   `/data/services/openclaw/habits-agent`

**Validation**:
- [ ] Agent created without errors
- [ ] Workspace directory created

### T004: Deploy workspace files to office2

**Purpose**: Copy workspace files from the repo to the agent's workspace.

**Steps**:
1. Copy all workspace files:
   ```bash
   for f in SOUL.md USER.md IDENTITY.md TOOLS.md; do
     ssh office2-claude "cat > /data/services/openclaw/habits-agent/$f" \
       < scripts/openclaw/agents/felix-admin-habits/$f
   done
   ```
2. Verify files exist:
   ```bash
   ssh office2-claude "ls -la /data/services/openclaw/habits-agent/"
   ```

**Note**: AGENTS.md is written in WP03 — do not create a placeholder here.

### T005: Verify agent is operational

**Purpose**: Confirm the agent can start a session.

**Steps**:
1. Test with a simple message:
   ```bash
   ssh office2-claude "openclaw agent --agent felix-admin-habits \
     --message 'Who are you? What is your purpose?' --json --timeout 30"
   ```
2. Verify the response references habit check-ins and Kent's voice
3. If the agent fails, check logs:
   ```bash
   ssh office2-claude "journalctl --user -u openclaw-gateway --since '5 min ago'"
   ```

**Validation**:
- [ ] Agent responds to a message
- [ ] Response reflects SOUL.md identity (mentions habit check-ins)

## Definition of done

- [ ] All 4 workspace files exist in `scripts/openclaw/agents/felix-admin-habits/`
- [ ] Agent created on office2 and appears in `openclaw agents list`
- [ ] Workspace files deployed to `/data/services/openclaw/habits-agent/`
- [ ] Agent responds to test message with correct identity

## Risks

- **Agent creation may require gateway restart**: If `openclaw agents add`
  doesn't take effect, restart: `systemctl --user restart openclaw-gateway`

## Activity Log

- 2026-04-01T03:09:01Z – claude-code – shell_pid=90925 – lane=doing – Assigned agent via workflow command
