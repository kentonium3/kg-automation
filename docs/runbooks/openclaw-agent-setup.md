---
title: OpenClaw Agent Setup
doc_type: runbook
status: approved
audience: agents_and_humans
last_updated: '2026-06-08'
last_validated: '2026-06-08'
updated_by: '#374 + vikunja-client-and-habits-weekly-report-01KTKSFT (#561)'
revision: v1.2
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

NEVER read, process, route to, or reference `04-Growth/_private/`.
```

### Output Discipline (Hard Rules) — standard for user-facing surfaces

Any agent whose AGENTS.md or standing orders surface to user-facing
WhatsApp (announce-channel cron messages, direct replies, escalation
pings) MUST carry the canonical Output Discipline Hard Rules block.
The canonical source is `scripts/openclaw/agents/felix-admin-capture/AGENTS.md`
(currently lines ~33–84). As of mission
`vikunja-client-and-habits-weekly-report-01KTKSFT` (#561 co-shipped
output discipline), the same block is also installed on
`felix-admin-habits` and audited on `felix-admin-escalation` and
`felix-admin-tasker`.

The three Hard Rules forbid:

1. Any preamble before the `Sent by <agent-id>:<model>` identity line in
   a user-facing message.
2. Between-tool-calls narration (the agent talking to itself in the
   announce channel).
3. Any text — internal reasoning, planning, monologue — appearing
   above the identity line in cron-fired announce messages.

When deploying a new agent that emits user-facing WhatsApp, copy the
canonical block from felix-admin-capture's AGENTS.md verbatim and adapt
only the `<agent-id>` placeholder. Agents that do NOT emit user-facing
WhatsApp must carry an explicit "no user-facing WhatsApp" annotation in
their standing orders so the audit trail records the deliberate
non-application of the rules.

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
| `model` | LLM model for this agent (see Model Tier Assignment below) |

### Model Tier Assignment

New agents default to Haiku (`anthropic/claude-haiku-4-5`) — the global
default in `openclaw.json`. Only use Sonnet or higher when the task requires
complex multi-step reasoning, trend analysis, or orchestration.

When registering a new agent:

1. **Set the `model` field** in the `openclaw.json` agent entry
2. **Add `model`, `model_policy`, and `model_rationale`** to the agent's
   entry in `docs/constitution/agent-registry.json`
3. **Update `AGENT-REGISTRY.md`** with the model assignment

Model policy values:
- **pinned**: Must stay on this model. Change requires validation with
  representative production inputs and documented justification.
- **optimizable**: May move to a cheaper model if one passes quality validation.

If Sonnet is needed, document why in `model_rationale`. If unsure, start with
Haiku and validate — it's easier to upgrade than to discover a downgrade broke
something.

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

## Deploy pipeline (post-#567)

As of mission `agent-prompt-deploy-pipeline-01KTMDDD` (#567), the agent
prompt files (`AGENTS.md`, `IDENTITY.md`, `SOUL.md`, `TOOLS.md`, `USER.md`)
under `scripts/openclaw/agents/<slug>/` in the repo are **auto-synced** to
their deployed locations under `/data/services/openclaw/<deploy-dir>/`
within 5 minutes of any merge to `main`.

The pipeline is operator-owned but agent-readable:

- **Helper**: `scripts/openclaw/deploy/deploy_agent_prompts.py` (stdlib-only Python)
- **Systemd timer + service**: `scripts/openclaw/deploy/agent-prompt-sync.{timer,service}` (deployed to `~/.config/systemd/user/` on office2 as the `claude` user)
- **Audit log**: `/data/services/openclaw/deploy/agent-prompt-sync.jsonl` (append-only JSONL)
- **Operator runbook**: [`agent-prompt-sync-ops.md`](<./agent-prompt-sync-ops.md>)

**Implications for new-agent deployment**:

1. Manual `scp` of agent prompt files to the deploy dir is **no longer
   required** post-merge. The sync helper picks up the new files on its next
   tick (≤5 min).
2. Manual file copies remain as the **fallback** path when the helper is
   broken, being bootstrapped, or stopped (e.g., during incident response).
3. Slug → deploy-dir mapping is sourced from `service-inventory.json`
   `services[openclaw].agents.<slug>.workspace`. New agents must be registered
   there with both `source_in_repo` AND `workspace` populated before the sync
   helper will pick them up.
4. `HEARTBEAT.md`, `*.tmpl`, `*.bak*`, and `GOVERNANCE.md` are explicitly
   excluded from sync — they live in the deploy dir but are not repo-sourced
   (or, for `*.tmpl`, are templates not intended for runtime).
5. The sync helper does NOT restart openclaw. Prompt changes take effect at
   the agent's next session-init (next cron tick).

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

## Cutover sequence for main-agent AGENTS.md changes (post-#374)

When changing `/data/services/openclaw/data/AGENTS.md` (the **main**
agent's standing orders — the file that governs verbatim pass-through
routing, etc.), active main-agent sessions keep their cached system
prompt and never see the new content. The new instructions only load on
the **next** session that starts. Use this five-step sequence to force
the new instructions live without restarting the OpenClaw gateway:

1. **Pull repo on office2** (refresh the canonical source):

   ```bash
   ssh office2-claude 'cd ~/kg-automation && git pull origin main'
   ```

2. **Deploy AGENTS.md** (overwrite the live workspace copy):

   ```bash
   ssh office2-claude 'cp ~/kg-automation/scripts/openclaw/agents/main/AGENTS.md /data/services/openclaw/data/AGENTS.md'
   ```

3. **Verify size budget** (effective budget ≤14000 raw source bytes —
   AGENTS.md inflates ~26% in the LLM's view per the rawChars
   measurement; budget exceeded means later instructions may be
   truncated):

   ```bash
   ssh office2-claude 'wc -c /data/services/openclaw/data/AGENTS.md'
   ```

   Output must be ≤14000.

4. **Rotate sessions** (force every active main-agent session to reset
   so the next invocation re-loads the freshly-deployed AGENTS.md):

   ```bash
   ssh office2-claude 'python3 ~/kg-automation/scripts/openclaw/helpers/rotate_main_session.py'
   ```

   Outputs a `SUMMARY:` line + the marker path under
   `~/.config/openclaw/main-rotation-<timestamp>.done`. Re-runs are
   naturally idempotent — each invocation produces a fresh timestamped
   marker and rotates only the sessions that have re-appeared since the
   last run. Add `--dry-run` first if you want to preview the impact.

5. **Smoke test** (send a known WhatsApp message; verify the verbatim
   text appears in the relevant sub-agent's session jsonl — replace
   `felix-admin-habits` with the actual delegated-to sub-agent and
   `<your verbatim phrase>` with a short unique substring of the test
   message):

   ```bash
   ssh office2-claude 'ls -t /home/claude/.openclaw/agents/felix-admin-habits/sessions/*.jsonl | head -1 | xargs grep "<your verbatim phrase>"'
   ```

   A non-empty grep match confirms the new pass-through behavior reached
   the downstream sub-agent.

**Cross-reference**: see
`kitty-specs/main-verbatim-passthrough-01KSATRP/spec.md` for the design
rationale (FR-005..FR-009, NFR-001, NFR-002, NFR-004) and
`kitty-specs/main-verbatim-passthrough-01KSATRP/contracts/rotation-helper.md`
for the rotation helper's CLI/API contract.
