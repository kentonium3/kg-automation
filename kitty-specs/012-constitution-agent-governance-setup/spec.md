# Constitution & Agent Governance Setup

**Feature**: 012-constitution-agent-governance-setup
**Mission**: software-dev
**Status**: draft
**Created**: 2026-04-01

## Overview

Two agents are running on office2 (felix-admin-capture, felix-admin-habits) but neither has been formally registered under the Felix governance framework. There is no constitution document, no formal autonomy level assignment, no activity surfacing mechanism, and no skill-authoring skill. As the system grows, each new agent will make up its own conventions unless the governance framework is established now.

This feature formalizes the rules all Felix agents operate under, registers the two existing agents at Assisted (Level 1), implements the autonomy level model with corresponding activity surfacing behavior, creates the skill-authoring skill so future agents can write skills that conform to project standards, and delivers the operational runbook for ongoing governance.

## Actors

- **Kent Gale** — system owner; approves autonomy level transitions, constitution changes, community skill installations; receives activity summaries
- **Felix agents** — agents operating under the constitution; currently felix-admin-capture and felix-admin-habits
- **Future agents** — any agent deployed after F012 that must comply with the constitution from day one

## User Scenarios & Testing

### Scenario 1: New agent onboarding
Kent deploys a new agent. The agent's standing orders reference the constitution. The agent is registered at Assisted (Level 1) in the agent registry. Activity surfacing runs at all levels. The agent operates within the governance framework from its first run.

### Scenario 2: Reviewing agent activity
Kent receives an AI-consolidated activity summary via Obsidian. Routine actions are summarized as counts. Flagged items, errors, and potential-goals are elevated with actionable detail. Kent can drill into the full audit log if needed.

### Scenario 3: Critical alert at any autonomy level
An agent at any autonomy level encounters an error. The error is surfaced to Kent via WhatsApp regardless of the agent's autonomy level — critical alerts are never suppressed.

### Scenario 4: Autonomy level promotion
After 30+ days of reliable Assisted performance, Kent reviews the agent's log history and decides to promote it to Observed (Level 2). The transition is recorded in the agent registry with date and rationale.

### Scenario 5: Autonomy level demotion
An agent at Observed or Autonomous behaves unexpectedly or is modified. Kent demotes it back to Assisted. The demotion is recorded in the registry. The agent resumes confirming actions with Kent before execution.

### Scenario 6: Agent writes a new skill
An agent with skill-writing capability reads the skill-authoring skill and produces a new SKILL.md that conforms to project standards without additional guidance.

### Scenario 7: Community skill installation request
An agent encounters a ClawHub community skill it could use. Per the ClawHub constraint, the agent presents the full SKILL.md to Kent for review rather than self-approving installation, regardless of its autonomy level.

## Functional Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| FR-001 | Create `docs/constitution/FELIX-CONSTITUTION.md` formalizing all four governance directives (narrow scope, earned autonomy with three autonomy levels, central action logging, safety parameters), the privacy boundary, activity surfacing behavior per autonomy level, and the ClawHub constraint | proposed |
| FR-002 | The constitution must be concise enough to be included by reference in agent standing orders without bloating context | proposed |
| FR-003 | The constitution must be version-stamped (v1.0, date) and changeable only through a spec with Kent's approval | proposed |
| FR-004 | The constitution must include an extensible "Privacy & Communication Boundaries" section that encodes the current `_private/` directory boundary and can accommodate future PII and outbound communication rules | proposed |
| FR-005 | Create `docs/constitution/AGENT-REGISTRY.md` as the human-readable record of all deployed Felix agents, their current autonomy level, scope, and transition history. Create `docs/constitution/agent-registry.json` as the machine-readable authoritative operational record | proposed |
| FR-006 | Register felix-admin-capture and felix-admin-habits at Assisted (Level 1) in the agent registry with complete entries (agent name, team, scope, current autonomy level, deploy feature, transition history) | proposed |
| FR-007 | Autonomy level transitions in the registry are append-only — history entries are never edited in place | proposed |
| FR-008 | Both agents must write a structured activity log after every run to `~/second-brain/agents/logs/`, following the existing processing log format with standardized log categories (routine, flagged, error, security) | proposed |
| FR-009 | Implement an AI-consolidated intelligence layer that filters routine actions to counts, elevates flagged items/errors/alerts with actionable detail, and consolidates multi-run agents into a single periodic digest | proposed |
| FR-010 | Implement activity surfacing via Obsidian notes (primary) with WhatsApp for critical alerts. The intelligence layer writes consolidated digests to `~/second-brain/notes/00-System/agent-activity/` | proposed |
| FR-011 | The intelligence layer runs a daily digest at all autonomy levels. Surfacing behavior varies by level: Assisted and Observed surface all activity; Autonomous surfaces only exceptions. Critical alerts (errors, security) always surface at every level | proposed |
| FR-012 | Agent autonomy level persists in `agent-registry.json` and survives agent restarts | proposed |
| FR-013 | Every surfaced summary must include a reference to the full audit log for investigation | proposed |
| FR-014 | Add the ClawHub community skill constraint to the constitution and to the standing orders of any agent with skill management capability | proposed |
| FR-015 | Create `scripts/openclaw/skills/skill-author/SKILL.md` encoding the OpenClaw SKILL.md format, project-specific conventions (credential store, no hardcoded IDs, structured error handling, identity labels, logging), the ClawHub constraint, narrow scope guidance, and pattern references to Whisper and Vikunja API skills | proposed |
| FR-016 | Deploy the skill-authoring skill to office2 alongside other OpenClaw skills | proposed |
| FR-017 | Update both agents' AGENTS.md to reference the constitution, declare compliance, state current autonomy level, and note that standing orders supplement but do not override the constitution | proposed |
| FR-018 | Deploy updated agent workspace files to office2 | proposed |
| FR-019 | Create `docs/handbooks/felix-governance.md` covering: reading the constitution and registry, autonomy level promotion/demotion procedures, new agent registration, activity surfacing behavior per level, and constitution violation handling | proposed |
| FR-020 | Update `docs/design/architecture/data/service-inventory.json` with `updated_by: "F012"` and autonomy_level field on each agent entry | proposed |
| FR-021 | Update `docs/handbooks/openclaw-ops.md` with references to FELIX-CONSTITUTION.md and AGENT-REGISTRY.md | proposed |

## Non-Functional Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| NFR-001 | The constitution document must be readable and actionable by an AI agent without human interpretation — clear, unambiguous language with no implicit assumptions | proposed |
| NFR-002 | The intelligence layer must produce surfaced summaries that answer "what do I need to know?" in under 30 seconds of reading for a typical day's activity | proposed |
| NFR-003 | Activity surfacing must not add more than 60 seconds to an agent's total run time | proposed |
| NFR-004 | The skill-authoring skill must be self-contained — an agent reading only this skill can produce a compliant new skill without additional guidance | proposed |
| NFR-005 | The constitution must formalize patterns already working in existing agents — it must not impose new operational requirements that contradict current successful behavior | proposed |

## Constraints

| ID | Constraint | Status |
|-----|-----------|--------|
| C-001 | The `~/second-brain/notes/02-Growth/_private/` directory is never read, written, referenced, or logged by any agent under any circumstance | proposed |
| C-002 | No new credentials are introduced by this feature | proposed |
| C-003 | Agent actions on office2 must use the `claude` user account, never `kgale` | proposed |
| C-004 | Modifications to existing agent standing orders are additive only (add constitution preamble) — no rewriting of standing orders that are already working | proposed |
| C-005 | ClawHub community skill constraint applies at all autonomy levels including Autonomous (Level 3) and never expires | proposed |
| C-006 | Autonomy level promotion requires Kent's explicit decision and minimum 30 days at the current level — never automatic. Demotion can happen at any time for any reason | proposed |

## Assumptions

- The existing processing log format in felix-admin-capture is a suitable base for the structured activity log format
- The existing SOUL.md / AGENTS.md / IDENTITY.md / TOOLS.md structure is the correct integration point for the constitution reference
- OpenClaw's agent context loading mechanism can include a constitution document by reference without modification to OpenClaw itself
- The four governance directives as written in the F012 input document accurately represent Kent's intent and do not need further refinement
- The skill-authoring skill pattern references (Whisper skill from F003 and Vikunja API skill from F007) are currently deployed and representative of project standards

## Dependencies

- **F008** (felix-admin-capture) — agent must be deployed and operational; standing orders must be readable
- **F009** (felix-admin-habits) — agent must be deployed and operational; standing orders must be readable
- Existing OpenClaw skill structure at `scripts/openclaw/skills/` must be in place
- Agent logs directory at `~/second-brain/agents/logs/` must exist on office2

## Out of Scope

- Security review agent — will be a separate feature after F012 establishes the governance framework
- Promotion to Observed or Autonomous for any agent — neither has the operating history; this is Assisted registration only
- Full daily briefing (F015) — activity surfacing here is a lightweight interim mechanism
- Cross-agent routing (WhatsApp router) — comes with broader agent team configuration
- Modifications to existing agent behavior beyond adding a constitution preamble

## Success Criteria

- The constitution document exists, is complete, version-stamped, and covers all four directives, the autonomy level model, privacy boundary (extensible), ClawHub constraint, and activity surfacing behavior per level
- The agent registry exists (JSON + Markdown) with both agents formally registered at Assisted (Level 1)
- Both agents write structured activity logs after every run with standardized categories
- Surfaced output is an AI-consolidated digest (not raw logs) with routine actions as counts and flagged items elevated
- Critical alerts always surface regardless of autonomy level
- Activity surfacing behavior corresponds to autonomy level (Assisted/Observed: all activity; Autonomous: exceptions only)
- Delivery mechanism, cadence, and time window decisions are documented in the governance runbook with rationale
- The skill-authoring skill exists, is deployed, and is self-contained
- Both agents' standing orders reference the constitution and declare compliance
- Updated workspace files are deployed to office2
- The governance runbook covers autonomy level promotion/demotion, new agent registration, and activity surfacing
- Architecture docs are updated (service-inventory.json autonomy level fields, openclaw-ops.md references)

## Key Entities

- **Constitution** — the authoritative governance document all agents operate under
- **Agent Registry** — the record of all deployed agents, their autonomy levels, and transition history (JSON is authoritative; Markdown is human-readable view)
- **Autonomy Level** — operating mode for an agent: Assisted (Level 1), Observed (Level 2), or Autonomous (Level 3)
- **Activity Log** — structured per-run audit trail written by each agent (mandatory, non-negotiable)
- **Surfaced Summary** — AI-consolidated digest written to Obsidian vault; content varies by autonomy level
- **Skill-Authoring Skill** — SKILL.md that teaches agents how to write compliant OpenClaw skills
- **ClawHub Constraint** — community skills require Kent's explicit approval before installation, at all autonomy levels
