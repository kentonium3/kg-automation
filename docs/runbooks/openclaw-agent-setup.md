---
title: OpenClaw Agent Setup
doc_type: runbook
status: approved
audience: agents_and_humans
last_updated: '2026-04-09'
revision: v1.0
---

# OpenClaw agent setup

How to register and deploy an OpenClaw agent on office2. Every Felix agent
(felix-admin-capture, felix-admin-habits, felix-admin-tasker, etc.) follows
this pattern.

## Two registrations, not one

An agent must be registered in **both** of these systems:

1. **Governance registry** (`docs/constitution/agent-registry.json`) — who
   the agent is, its autonomy level, and its team. This is the kg-automation
   record.
2. **OpenClaw config** (`~/.openclaw/openclaw.json` on office2) — how
   OpenClaw discovers and runs the agent. Without this, delegation fails
   with "Unknown agent id."

Neither is sufficient alone. The governance registry without OpenClaw
registration means the agent exists on paper but can't run. OpenClaw
registration without governance means the agent runs but isn't tracked
under Felix's governance framework.

## Per-agent workspace files

Each agent has a workspace directory at `/data/services/openclaw/<agent-name>/`.
These files define the agent's identity and behavior:

### Required files

| File | Purpose |
|------|---------|
| **AGENTS.md** | Standing orders — the agent's complete operational instructions. Scope, workflow, constraints, and delegation rules. This is the longest and most important file. |
| **SOUL.md** | Purpose, voice, and personality. Defines how the agent writes and communicates. Includes privacy boundaries. |
| **IDENTITY.md** | Short identity card — name, emoji, creature type, vibe. OpenClaw reads this to display agent identity in `openclaw agents` output. |

### Optional files

| File | Purpose | When to include |
|------|---------|-----------------|
| **TOOLS.md** | Agent-specific tool references — vault paths, API endpoints, access notes. | When the agent interacts with specific resources. |
| **USER.md** | Information about the human the agent serves — name, timezone, preferences. | When the agent communicates with the user directly. |
| **HEARTBEAT.md** | Periodic check tasks the agent runs on heartbeat intervals. | When the agent has scheduled proactive work. Empty file or omit if agent only runs via delegation. |
| **BOOTSTRAP.md** | First-run instructions. Agent reads it on first session, then deletes it. | Only during initial agent creation. |

### Example: IDENTITY.md

```markdown
# IDENTITY.md

- **Name:** Felix (Admin Tasker)
- **Creature:** Task intelligence agent
- **Vibe:** Precise, structured, deliberate — every task gets the right shape
- **Emoji:** 🎯
```

### Example: SOUL.md

```markdown
# SOUL.md — felix-admin-tasker

## Purpose

You are felix-admin-tasker. Your purpose is structuring and enriching
Kent's tasks in Vikunja. [...]

## Voice — write as Kent

Follow the same voice principles as other Felix agents. First person,
direct, no filler.

## Privacy boundary

NEVER read, process, route to, or reference `02-Growth/_private/`.
```

## OpenClaw configuration

### openclaw.json agent entry

Add the agent to the `agents.list` array in `~/.openclaw/openclaw.json`:

```json
{
  "id": "felix-admin-tasker",
  "name": "felix-admin-tasker",
  "workspace": "/data/services/openclaw/tasker-agent",
  "agentDir": "/home/claude/.openclaw/agents/felix-admin-tasker/agent",
  "model": "anthropic/claude-sonnet-4-6"
}
```

| Field | Value |
|-------|-------|
| `id` | Agent identifier — must match what other agents use for delegation |
| `name` | Display name (typically same as id) |
| `workspace` | Path to the agent's workspace directory containing AGENTS.md, SOUL.md, etc. |
| `agentDir` | Path to the agent's runtime directory under `~/.openclaw/agents/` |
| `model` | LLM model for this agent |

### Agent runtime directory

Create `~/.openclaw/agents/<agent-id>/agent/` and add `auth-profiles.json`.
Copy from an existing agent:

```bash
mkdir -p ~/.openclaw/agents/felix-admin-tasker/agent
cp ~/.openclaw/agents/felix-admin-capture/agent/auth-profiles.json \
   ~/.openclaw/agents/felix-admin-tasker/agent/
```

## Restart and verification

OpenClaw reads `openclaw.json` at startup. After adding or modifying an
agent entry, restart the gateway:

```bash
systemctl --user restart openclaw-gateway.service
```

Verify the agent is visible:

```bash
openclaw agents
```

The output should show the new agent with its identity (from IDENTITY.md),
workspace path, and model.

## Current agent layout

```
/data/services/openclaw/
├── inbox-agent/          ← felix-admin-capture
│   ├── AGENTS.md
│   ├── BOOTSTRAP.md
│   ├── HEARTBEAT.md
│   ├── IDENTITY.md
│   ├── SOUL.md
│   ├── TOOLS.md
│   └── USER.md
├── habits-agent/         ← felix-admin-habits
│   ├── AGENTS.md
│   ├── BOOTSTRAP.md
│   ├── HEARTBEAT.md
│   ├── IDENTITY.md
│   ├── SOUL.md
│   ├── TOOLS.md
│   └── USER.md
├── escalation-agent/     ← felix-admin-escalation
│   ├── AGENTS.md
│   ├── HEARTBEAT.md
│   ├── IDENTITY.md
│   ├── SOUL.md
│   ├── TOOLS.md
│   └── USER.md
├── tasker-agent/         ← felix-admin-tasker
│   ├── AGENTS.md
│   ├── IDENTITY.md
│   └── SOUL.md
└── data/                 ← main agent workspace

~/.openclaw/
├── openclaw.json         ← agent list lives here
├── agents/
│   ├── main/agent/
│   ├── felix-admin-capture/agent/
│   ├── felix-admin-habits/agent/
│   ├── felix-admin-escalation/agent/
│   └── felix-admin-tasker/agent/
├── skills/               ← shared skills (vikunja-api, whisper, etc.)
└── workspace/            ← global defaults (AGENTS.md, SOUL.md, etc.)
```

## Checklist for new agent deployment

- [ ] Governance: add entry to `docs/constitution/agent-registry.json`
- [ ] Workspace: create `/data/services/openclaw/<agent-name>/`
- [ ] Workspace: create AGENTS.md with standing orders
- [ ] Workspace: create SOUL.md with purpose, voice, privacy boundary
- [ ] Workspace: create IDENTITY.md with name, emoji, vibe
- [ ] Workspace: create TOOLS.md if agent uses specific resources
- [ ] Workspace: create USER.md if agent communicates with the user
- [ ] Config: add agent entry to `~/.openclaw/openclaw.json`
- [ ] Config: create `~/.openclaw/agents/<agent-id>/agent/` with auth-profiles.json
- [ ] Restart: `systemctl --user restart openclaw-gateway.service`
- [ ] Verify: `openclaw agents` shows the new agent with identity
- [ ] Architecture: update `docs/design/architecture/data/service-inventory.json` if needed
