---
work_package_id: WP01
title: Agent Workspace Foundation
lane: "doing"
dependencies: []
requirement_refs:
- C-003
- C-005
- FR-001
- FR-002
- FR-003
- NFR-004
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: main
base_commit: f663bad0dbc28b762c1024badb9ed88b35192736
created_at: '2026-03-31T02:56:29.193865+00:00'
subtasks: [T001, T002, T003, T004, T005]
shell_pid: "66038"
agent: "claude-code"
history:
- date: '2026-03-31T02:04:57Z'
  event: created
  actor: claude
---

# WP01: Agent Workspace Foundation

## Implementation Command

```bash
spec-kitty implement WP01
```

## Objective

Create the felix-admin-capture agent's workspace files, register the agent
with OpenClaw on office2, deploy the workspace, and verify the agent is
operational.

## Context

- **Repo location for workspace files**: `scripts/openclaw/agents/felix-admin-capture/`
- **Deploy target on office2**: `/data/services/openclaw/inbox-agent/`
- **Existing skill pattern**: `scripts/openclaw/skills/whisper/SKILL.md`
- **Existing workspace reference**: SSH to office2 and read `~/.openclaw/workspace/SOUL.md` for the default agent's structure
- **kent-voice source**: `~/second-brain/.claude/skills/kent-voice/SKILL.md` (read locally)
- **Agent contract**: `kitty-specs/008-inbox-processing-migration/contracts/openclaw-agent-contract.md`

## Subtask Guidance

### T001: Write SOUL.md with Kent-Voice Identity

**Purpose**: Define the agent's authoring identity so all vault content
sounds like Kent, not generic AI.

**Steps**:
1. Read the kent-voice SKILL.md at `~/second-brain/.claude/skills/kent-voice/SKILL.md`
2. Create `scripts/openclaw/agents/felix-admin-capture/SOUL.md`
3. Encode the following from kent-voice into SOUL.md:
   - First person always ("I", "my")
   - Direct and action-oriented, no hedging
   - Confident but honest
   - Context before detail (systems thinking)
   - Structured and chunked (ADD-friendly)
   - No exclamation marks in professional content
   - Active voice, present/future tense
   - Em dashes for emphasis
   - Sentence case for headers
   - Words to avoid list (from kent-voice SKILL.md)
   - Words that are Kent (from kent-voice SKILL.md)
4. Add the agent's core purpose: "You are felix-admin-capture. Your sole
   purpose is processing Kent's Obsidian inbox. You read unprocessed notes,
   classify content, route it to the correct vault locations, create Vikunja
   tasks for action items, and write a processing log."
5. Add the privacy boundary: "NEVER read, process, route to, or reference
   `02-Growth/_private/`. This is absolute."

**Files**: `scripts/openclaw/agents/felix-admin-capture/SOUL.md` (new)

**Validation**:
- [ ] Kent-voice principles encoded (first person, direct, structured, no filler)
- [ ] Agent purpose stated
- [ ] Privacy boundary stated
- [ ] Reads naturally as an identity document, not a skill manual

### T002: Write USER.md, IDENTITY.md, TOOLS.md

**Purpose**: Complete the workspace with Kent's context, agent identity, and
tool notes.

**Steps**:
1. Create `scripts/openclaw/agents/felix-admin-capture/USER.md`:
   ```markdown
   # USER.md - About Your Human

   - **Name:** Kent Gale
   - **What to call them:** Kent
   - **Timezone:** America/New_York (Eastern)
   - **Notes:** 63, entrepreneur/consultant/technologist. ADD (managed).
     Building an AI-powered second brain and accountability system.

   ## Context

   Kent captures notes via Wispr Flow (voice) and typed quick notes into
   the Obsidian 00-Inbox/ folder. Your job is to process these captures
   and route them to the correct locations in his vault.
   ```

2. Create `scripts/openclaw/agents/felix-admin-capture/IDENTITY.md`:
   ```markdown
   # IDENTITY.md

   - **Name:** Felix (Admin Capture)
   - **Creature:** Inbox processing agent
   - **Vibe:** Methodical, thorough, quiet worker
   - **Emoji:** 📥
   ```

3. Create `scripts/openclaw/agents/felix-admin-capture/TOOLS.md`:
   ```markdown
   # TOOLS.md

   ## Vault
   - **Path on office2**: `/home/kgale/second-brain/vault/`
   - **Inbox**: `/home/kgale/second-brain/vault/00-Inbox/`
   - **Processing logs**: `/home/kgale/second-brain/agents/logs/`
   - **Access**: claude user via secondbrain group

   ## Vikunja API
   - Use the vikunja_api skill for task creation
   - Run `openclaw skills info vikunja_api` for details

   ## Privacy
   - NEVER access: `/home/kgale/second-brain/vault/02-Growth/_private/`
   ```

**Files**: USER.md, IDENTITY.md, TOOLS.md (all new in `scripts/openclaw/agents/felix-admin-capture/`)

### T003: Create felix-admin-capture Agent on office2

**Purpose**: Register the agent with OpenClaw.

**Steps**:
1. SSH to office2:
   ```bash
   ssh office2-claude "openclaw agents add felix-admin-capture \
     --workspace /data/services/openclaw/inbox-agent \
     --model anthropic/claude-sonnet-4-6 \
     --non-interactive"
   ```
2. Verify: `ssh office2-claude "openclaw agents list"`
3. Expected: felix-admin-capture appears with workspace `/data/services/openclaw/inbox-agent`

**Validation**:
- [ ] Agent created without errors
- [ ] Workspace directory created at `/data/services/openclaw/inbox-agent/`

### T004: Deploy Workspace Files to office2

**Purpose**: Copy workspace files from the repo to the agent's workspace.

**Steps**:
1. Copy all workspace files:
   ```bash
   for f in SOUL.md USER.md IDENTITY.md TOOLS.md; do
     ssh office2-claude "cat > /data/services/openclaw/inbox-agent/$f" \
       < scripts/openclaw/agents/felix-admin-capture/$f
   done
   ```
2. Verify files exist:
   ```bash
   ssh office2-claude "ls -la /data/services/openclaw/inbox-agent/"
   ```

**Note**: AGENTS.md is written in WP02 — do not create a placeholder here.

### T005: Verify Agent is Operational

**Purpose**: Confirm the agent can start a session.

**Steps**:
1. Test with a simple message:
   ```bash
   ssh office2-claude "openclaw agent --agent felix-admin-capture \
     --message 'Who are you? What is your purpose?' --json --timeout 30"
   ```
2. Verify the response references inbox processing and Kent's voice
3. If the agent fails, check logs: `ssh office2-claude "journalctl --user -u openclaw-gateway --since '5 min ago'"`

**Validation**:
- [ ] Agent responds to a message
- [ ] Response reflects SOUL.md identity (mentions inbox processing)

## Definition of Done

- [ ] All 5 workspace files exist in `scripts/openclaw/agents/felix-admin-capture/`
- [ ] Agent created on office2 and appears in `openclaw agents list`
- [ ] Workspace files deployed to `/data/services/openclaw/inbox-agent/`
- [ ] Agent responds to test message with correct identity

## Risks

- **Agent creation may require gateway restart**: If `openclaw agents add` doesn't
  take effect immediately, restart: `systemctl --user restart openclaw-gateway`
- **Model availability**: If `anthropic/claude-sonnet-4-6` is unavailable, check
  OpenClaw's model configuration

## Activity Log

- 2026-03-31T02:56:29Z – claude-code – shell_pid=66038 – lane=doing – Assigned agent via workflow command
