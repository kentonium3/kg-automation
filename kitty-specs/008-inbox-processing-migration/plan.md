# Implementation Plan: Inbox Processing Migration

**Branch**: `008-inbox-processing-migration` | **Date**: 2026-03-31 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/kitty-specs/008-inbox-processing-migration/spec.md`

## Summary

Migrate Obsidian inbox processing from Mac-dependent Claude conversation
sessions to an always-on `felix-admin-capture` OpenClaw agent on office2.
The agent runs 3× daily via OpenClaw cron, replicates the existing routing
table and goal handling rules, adds a Vikunja task bridge for action items
and research requests, and supports on-demand WhatsApp triggering via the
main agent.

## Technical Context

**Language/Version**: Markdown workspace files (SOUL.md, AGENTS.md) + OpenClaw CLI
**Primary Dependencies**: OpenClaw 2026.3.24, Vikunja API skill (F007), Obsidian Sync
**Storage**: Obsidian vault at `/home/kgale/second-brain/vault/` (SQLite for Vikunja via F007)
**Testing**: Manual end-to-end with test inbox notes
**Target Platform**: office2 (Ubuntu 24.04 LTS) running OpenClaw
**Project Type**: Agent configuration + workspace files + cron jobs
**Performance Goals**: 10 inbox notes processed in under 5 minutes
**Constraints**: Privacy boundary (02-Growth/_private/), vault-writer standards, kent-voice
**Scale/Scope**: Single user, 5-15 inbox notes per day

## Constitution Check

| Directive | Status | Notes |
| --- | --- | --- |
| Privacy absolute | Pass | 02-Growth/_private/ never touched — encoded in AGENTS.md standing orders |
| Never fail silently | Pass | Processing log captures all errors; task creation failures logged |
| No credentials in code | Pass | Vikunja token via F007 skill credential store pattern |
| Narrow scope | Pass | Agent does one thing: inbox processing |
| Docs adjacent | Pass | Ops runbook and architecture docs updated |

## Project Structure

### Documentation (this feature)

```
kitty-specs/008-inbox-processing-migration/
├── plan.md                  # This file
├── research.md              # Phase 0 — infrastructure verification, architecture decisions
├── data-model.md            # Phase 1 — entity reference
├── contracts/
│   └── openclaw-agent-contract.md  # Agent creation, cron jobs, vault paths
├── quickstart.md            # Deploy and verify guide
└── tasks.md                 # Phase 2 output (/spec-kitty.tasks)
```

### Source Code (repository root)

```
scripts/openclaw/agents/felix-admin-capture/
├── SOUL.md          # Kent-voice authoring identity
├── AGENTS.md        # Standing orders: routing table, task bridge, goals
├── USER.md          # Kent's context
├── IDENTITY.md      # Agent identity
└── TOOLS.md         # Tool notes (vault path, skill references)
```

No executable code. The "source" is workspace configuration files that define
the agent's identity, standing orders, and operational procedures. These are
deployed to `/data/services/openclaw/inbox-agent/` on office2.

**Structure Decision**: Workspace files in a dedicated repo directory matching
the Whisper/Vikunja API skill pattern at `scripts/openclaw/`.

## Key Design Decisions

### 1. Isolated Agent with Own Workspace

felix-admin-capture is a separate OpenClaw agent created via
`openclaw agents add`. It has its own workspace, SOUL.md, and session
isolation. This prevents inbox processing from polluting the main agent's
conversation context.

### 2. Standing Orders, Not a Skill

The inbox processing behavior is encoded as standing orders in AGENTS.md
(auto-injected every session), not as a separate SKILL.md. This is correct
because the agent only does one thing — its entire purpose IS inbox
processing. Standing orders define authorization and process; the vikunja_api
skill (shared) provides the tool capability.

### 3. Kent-Voice in SOUL.md

The kent-voice authoring standards are encoded directly in the agent's
SOUL.md. In the Cowork context, kent-voice was a separate skill. In OpenClaw,
it belongs in SOUL.md because it defines who the agent IS, not what tools
it uses.

### 4. Three Cron Jobs for Scheduling

OpenClaw cron jobs target the agent by ID with isolated sessions. Three jobs
at 7 AM, 12 PM, and 6 PM ET cover morning, midday, and evening processing
windows.

### 5. WhatsApp Trigger via Main Agent Delegation

No intent-based routing exists in OpenClaw. The main agent handles all
WhatsApp messages. An instruction in the main agent's workspace (skill or
standing order addition) teaches it to recognize "process my inbox" intent
and trigger `openclaw cron run inbox-morning` or directly invoke the
felix-admin-capture agent.

### 6. Vault Path Correction

The vault-writer SKILL.md references `~/second-brain/vault/notes/` but the
actual path on office2 is `/home/kgale/second-brain/vault/` — no `Notes/`
subdirectory. Domain folders are directly under `vault/`.

### 7. Research Project as Prerequisite

A "Research" Vikunja project must be created before the task bridge can route
research requests. This is a setup step during deployment.

## Deployment Plan

1. Write workspace files (SOUL.md, AGENTS.md, USER.md, IDENTITY.md, TOOLS.md)
   in `scripts/openclaw/agents/felix-admin-capture/`
2. Create the agent: `openclaw agents add felix-admin-capture --workspace /data/services/openclaw/inbox-agent`
3. Deploy workspace files to office2
4. Create Research project in Vikunja
5. Add 3 cron jobs
6. Test with a manual cron run against real inbox notes
7. Add WhatsApp trigger instruction to main agent
8. Update ops runbook and architecture docs

## Risk Mitigations

| Risk | Mitigation |
| --- | --- |
| Processing quality regression | Processing log provides observable output; Cowork fallback available |
| Vault write conflicts | `status: processed` frontmatter flag is the mutex |
| Task noise from stream-of-consciousness | Use existing `type: task` classification; err on inclusion |
| Obsidian Sync delays | Sync verified running 1+ week; runbook documents troubleshooting |
| WhatsApp trigger mechanics unknown | Main agent delegation approach; fallback to direct agent invocation |
| Vault path differences | Verified correct path; TOOLS.md documents the canonical path |

## Complexity Tracking

No constitution violations. No complexity justifications needed.
