# Implementation Plan: Vikunja Task Intelligence Agent

**Branch**: `main` | **Date**: 2026-04-02 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `kitty-specs/013-vikunja-task-intelligence-agent/spec.md`

## Summary

Introduce felix-admin-tasker, a specialist OpenClaw agent that transforms raw task descriptions into fully structured Vikunja entries. The agent uses a confidence threshold model to reason through task attributes, clarifies uncertain attributes via WhatsApp (primary interaction channel), and creates tasks only after Kent's explicit confirmation (Assisted mode). Implementation follows the established OpenClaw agent delegation pattern, with a self-contained task-intelligence skill encoding the structuring logic, and updates to felix-admin-capture's handoff behavior.

## Technical Context

**Language/Version**: Python 3.11+ (constitution), Markdown (skill/agent documents)
**Primary Dependencies**: OpenClaw agent framework, Vikunja REST API v0.24.6, WhatsApp (Baileys)
**Storage**: Vikunja SQLite (via REST API) — no additional storage infrastructure
**Testing**: pytest for Python modules, manual validation of agent behavior, validate_docs.py for document compliance
**Target Platform**: office2 (Ubuntu 24.04 LTS), Tailscale-only access
**Project Type**: OpenClaw agent + skill documents with supporting Python scripts
**Performance Goals**: Task proposal within 60 seconds of handoff, WhatsApp response within 10 seconds (constitution)
**Constraints**: Tailscale-only, no credentials in code, central action logging, Assisted mode at launch
**Scale/Scope**: Single user (Kent), ~5-20 tasks per day, retroactive enrichment of ~50-100 existing flat tasks

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Directive | Status | Notes |
|---|---|---|
| TEST_FIRST | Pass | Acceptance tests defined per scenario; pytest for Python modules; manual agent behavior validation |
| Privacy boundary (02-Growth/_private/) | Pass | Agent has no reason to access private vault paths; not referenced in any skill or agent document |
| No credentials in code | Pass | Vikunja API token read from `/data/services/openclaw/secrets/vikunja-api` at runtime |
| Tailscale-only | Pass | All Vikunja API access via `https://office2.tail0f5f56.ts.net` |
| Central action logging | Pass | Agent logs to `~/second-brain/agents/logs/` per Felix Constitution Directive 3 |
| Narrow scope (Directive 1) | Pass | Agent structures tasks only — does not process inbox, manage habits, or send briefings |
| Earned autonomy (Directive 2) | Pass | Starts at Assisted (Level 1); progression via standard 30-day observation |
| Never fail silently (Directive 4) | Pass | All error paths log and alert Kent |
| Exception policy | N/A | No policy exceptions required |

**Post-Phase 1 re-check**: Constitution compliance maintained. No new violations introduced by design decisions.

## Project Structure

### Documentation (this feature)

```
kitty-specs/013-vikunja-task-intelligence-agent/
├── spec.md
├── plan.md                          # This file
├── research.md                      # Phase 0 output
├── data-model.md                    # Phase 1 output
├── quickstart.md                    # Phase 1 output
├── contracts/
│   ├── agent-delegation-contract.md # Agent handoff protocol
│   └── vikunja-task-enrichment-contract.md  # Vikunja API usage
├── checklists/
│   └── requirements.md
└── tasks/
    └── README.md
```

### Source Code (repository root)

```
scripts/openclaw/agents/felix-admin-tasker/
├── AGENTS.md                        # Agent standing orders (new)
├── SOUL.md                          # Agent identity (new)
├── USER.md                          # User context (new)
├── IDENTITY.md                      # Agent identity card (new)
└── TOOLS.md                         # Available tools (new)

scripts/openclaw/skills/task-intelligence/
└── SKILL.md                         # Task structuring skill (new)

scripts/openclaw/agents/felix-admin-capture/
└── AGENTS.md                        # Updated: handoff to tasker + fallback

docs/handbooks/
└── task-intelligence-ops.md         # Operations runbook (new)

docs/constitution/
└── AGENT-REGISTRY.md                # Updated: add felix-admin-tasker

docs/design/architecture/
├── service-inventory.md             # Updated: add agent + cron
└── data/
    └── service-inventory.json       # Updated: add agent + cron
```

**Structure Decision**: Follows the established OpenClaw agent pattern — each agent gets a workspace directory under `scripts/openclaw/agents/` with standard files (AGENTS.md, SOUL.md, USER.md, IDENTITY.md, TOOLS.md). Skills live under `scripts/openclaw/skills/`. No traditional `src/` directory needed; the "source code" is the agent/skill documents that OpenClaw interprets.

## Key Design Decisions

### 1. Delegation + Polling Hybrid

felix-admin-capture delegates to felix-admin-tasker for new tasks (real-time enrichment). felix-admin-tasker also runs a scheduled poll for incomplete tasks (catches directly-created tasks and fallback flat tasks). This satisfies both FR-017 (handoff) and FR-015 (detection) with a single agent.

### 2. Enrichment State in Vikunja Comments

Rather than maintaining external state (database, files), enrichment tracking uses Vikunja task comments with the `[Felix] enrichment | <status>` format. This keeps the Vikunja API as the single source of truth and avoids state synchronization issues.

### 3. Confidence Model in Skill Document

The confidence threshold and inference rules live in the task-intelligence skill (SKILL.md), not in code. This allows tuning the model by editing the skill document without deploying code changes — matching the OpenClaw pattern where agent behavior is defined by documents.

### 4. Primary Interaction Channel Abstraction

The agent's conversation logic references a "primary interaction channel" abstraction. The AGENTS.md document specifies WhatsApp as the initial channel. Switching channels later requires only updating the AGENTS.md channel configuration, not the task-intelligence skill logic.

### 5. Two-Step Task Creation with Runtime Resolution

Following the established pattern from felix-admin-capture: create task first, then add identity label in a second API call. All project IDs and label IDs are resolved by name at runtime — never hardcoded.

## Cron Schedule

| Job | Schedule | Agent | Action |
|---|---|---|---|
| Incomplete task detection | Every 4 hours (0 */4 * * *) | felix-admin-tasker | Poll Inbox for flat tasks, offer enrichment |
| Retroactive enrichment | Manual trigger initially; scheduled after backlog cleared | felix-admin-tasker | Process next batch of flat tasks |

## Deployment Sequence

1. Deploy task-intelligence skill to office2
2. Deploy felix-admin-tasker agent workspace to office2
3. Register agent in AGENT-REGISTRY.md at Assisted (Level 1)
4. Test agent manually with sample tasks (Assisted mode — Kent confirms each)
5. Update felix-admin-capture AGENTS.md with delegation handoff
6. Redeploy felix-admin-capture with updated standing orders
7. Add incomplete task detection cron job
8. Run retroactive enrichment manually for first batch
9. Update architecture documentation

## Complexity Tracking

No constitution violations requiring justification.
