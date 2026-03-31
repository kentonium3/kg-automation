# Research: Inbox Processing Migration

## Decision 1: Agent Architecture — Isolated Agent with Own Workspace

**Decision**: Create a dedicated `felix-admin-capture` agent via
`openclaw agents add` with its own workspace directory containing a custom
SOUL.md that encodes kent-voice authoring standards.

**Rationale**: OpenClaw supports multiple isolated agents, each with their
own workspace (SOUL.md, AGENTS.md, USER.md, skills/). An isolated agent
provides clean separation from the main agent's conversation context. The
kent-voice authoring identity belongs in the agent's SOUL.md — not as a
separate skill invocation — because SOUL.md is auto-injected every session
and defines who the agent is.

**Alternatives considered**:
- Running inbox processing as the main agent — would pollute the main
  agent's session context and make it harder to isolate processing behavior
- A standalone script outside OpenClaw — would lose access to the skill
  system and API token credential store

**Verified**: `openclaw agents add` CLI exists and supports `--workspace`
flag. Current setup has only a `main` agent.

## Decision 2: Vault Path on office2

**Decision**: Vault root is `/home/kgale/second-brain/vault/` (not
`vault/Notes/`).

**Rationale**: Verified via SSH. The vault-writer SKILL.md references
`~/second-brain/vault/notes/` but the actual path on office2 has no `Notes/`
subdirectory — domain folders (00-Inbox, 01-Constitution, etc.) are directly
under `vault/`.

**Verified**:
- Vault exists at `/home/kgale/second-brain/vault/`
- claude user has write access via secondbrain group membership
- 00-Inbox/ contains inbox files (e.g., `Inbox 2026-03-22 1355.md`)
- Obsidian Sync service running for 1+ week continuously
- Processing logs directory exists at `/home/kgale/second-brain/agents/logs/`

## Decision 3: Scheduling — OpenClaw Cron Jobs

**Decision**: Use `openclaw cron add` with `--agent felix-admin-capture`
and `--session isolated` to schedule 3× daily processing runs.

**Rationale**: OpenClaw's built-in cron system supports targeting specific
agents via `--agent` flag, isolated sessions via `--session isolated`, and
cron expressions for scheduling. This is the native mechanism — no external
crontab entries needed.

**Schedule**:
- Morning: `0 7 * * *` (7 AM ET)
- Midday: `0 12 * * *` (12 PM ET)
- Evening: `0 18 * * *` (6 PM ET)

**Example command**:
```bash
openclaw cron add \
  --name "inbox-morning" \
  --cron "0 11 * * *" \
  --tz "America/New_York" \
  --agent felix-admin-capture \
  --session isolated \
  --message "Process the inbox now. Read all unprocessed files in 00-Inbox/, classify and route content per your standing orders, create Vikunja tasks for action items and research requests, and write the processing log." \
  --no-deliver
```

Note: Times in cron are UTC unless `--tz` is specified (7 AM ET = 11 AM UTC
during EDT).

**Alternatives considered**:
- System crontab (`crontab -e`) calling `openclaw agent --message` — works
  but loses session isolation and OpenClaw's built-in job management
- Heartbeat-based scheduling — less precise timing, shared with main agent

## Decision 4: WhatsApp Trigger — Main Agent Delegates to Cron Job

**Decision**: The WhatsApp trigger works through the main agent recognizing
the "process my inbox" intent and invoking `openclaw cron run <job-name>`
to trigger an immediate inbox processing run.

**Rationale**: OpenClaw has no intent-based routing — all WhatsApp messages
go to the main agent. The main agent can be taught (via a skill or standing
order) to recognize inbox-processing requests and trigger the cron job
manually. `openclaw cron run` executes a named job immediately.

**Implementation path**:
1. Add an inbox-trigger instruction to the main agent's AGENTS.md or a skill
2. When Kent says "process my inbox" via WhatsApp, main agent runs
   `openclaw cron run inbox-morning` (or a dedicated on-demand job)
3. The cron job runs felix-admin-capture in an isolated session
4. Response delivery: the cron job can `--announce` back to WhatsApp, or
   the main agent can relay the result

**Risk**: This is the least-verified part of the plan. The exact mechanics
of `openclaw cron run` from within an agent turn need testing during
implementation. If it doesn't work, the fallback is to have the main agent
use `openclaw agent --agent felix-admin-capture --message "..."` directly.

**Alternatives considered**:
- Peer-based routing (bind Kent's WhatsApp to felix-admin-capture) — would
  route ALL of Kent's messages to the inbox agent, losing the main agent
- Separate WhatsApp account — unnecessary complexity for one trigger phrase

## Decision 5: Skill Structure — Standing Orders + Shared Skills

**Decision**: The felix-admin-capture agent uses:
- **SOUL.md**: Kent-voice authoring identity
- **AGENTS.md**: Standing orders defining inbox processing authorization,
  routing table, goal handling rules, and Vikunja task bridge behavior
- **Shared vikunja_api skill**: Already deployed at `~/.openclaw/skills/`
- **No new skills needed in agent workspace**: The processing behavior is
  encoded as standing orders in AGENTS.md, not as a separate SKILL.md

**Rationale**: Per OpenClaw docs, standing orders in AGENTS.md define "what"
the agent is authorized to do. The routing table, goal handling rules, and
Vikunja task bridge are authorization and process definitions — they belong
in standing orders. The vikunja_api skill (F007) provides the "how" for
task creation. AGENTS.md is auto-injected every session.

**Alternatives considered**:
- Port inbox-processor SKILL.md to a workspace skill — would work but adds
  a layer of indirection. Standing orders are more direct since the agent
  only does one thing (inbox processing).
- Encode everything in SOUL.md — SOUL.md is for identity/personality, not
  operational procedures. AGENTS.md is the correct location for standing
  orders.

## Decision 6: Research Project in Vikunja

**Decision**: Create a "Research" project in Vikunja as a prerequisite for
F008 deployment. Research request tasks go here instead of the Inbox project.

**Rationale**: Research requests are a different category from action items.
A dedicated project keeps the Inbox project focused on actionable tasks.

**Verified**: Current Vikunja projects do not include a Research project.
It needs to be created during F008 implementation (similar to how F006
created the Goals project).

## Decision 7: Task Quality Threshold

**Decision**: Use the existing `type: task` classification from the
inbox-processor routing table as the threshold for Vikunja task creation.
Err on the side of inclusion.

**Rationale**: Per the func-spec: "it is better to create a task that turns
out not to be needed than to miss an actionable item." The Inbox project is
the triage point — Kent reviews and promotes or deletes tasks from there.
The threshold can be tightened in a future iteration after observing real
usage patterns.

## Infrastructure Verification Summary

| Check | Status | Details |
| --- | --- | --- |
| Vault path | Verified | `/home/kgale/second-brain/vault/` |
| Vault write access | Verified | claude user, secondbrain group |
| 00-Inbox exists | Verified | Contains inbox files |
| Obsidian Sync | Running | Active 1+ week, `ob sync --continuous` |
| Processing logs dir | Verified | `/home/kgale/second-brain/agents/logs/` |
| OpenClaw cron | Available | `openclaw cron add` with `--agent` support |
| OpenClaw agents | Available | `openclaw agents add` with `--workspace` |
| vikunja_api skill | Deployed | Shared at `~/.openclaw/skills/vikunja-api/` |
| Vikunja API token | Working | Verified in F007 |
| Research project | Missing | Needs creation during F008 |
