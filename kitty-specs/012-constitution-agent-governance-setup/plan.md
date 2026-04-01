# Implementation Plan: Constitution & Agent Governance Setup

**Branch**: `main` | **Date**: 2026-04-01 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `kitty-specs/012-constitution-agent-governance-setup/spec.md`

## Summary

Formalize the Felix governance framework by creating a constitution document, centralized JSON agent registry with autonomy levels, activity surfacing via Obsidian (with WhatsApp critical alerts), a skill-authoring skill, agent standing order updates, and an operational runbook. All governance documents are authored in the repo and deployed to office2. The centralized intelligence layer runs as a scheduled script on office2 that reads standardized agent logs and produces consolidated digests in the Obsidian vault, with surfacing depth determined by each agent's autonomy level.

## Technical Context

**Language/Version**: Python 3.11+ (intelligence layer script), Markdown (governance documents, skills)
**Primary Dependencies**: OpenClaw (agent orchestration), Obsidian Sync (digest delivery), Baileys/WhatsApp (critical alerts)
**Storage**: File-based — JSON registry, Markdown documents, Markdown activity logs
**Testing**: Manual validation of governance documents; pytest for the intelligence layer script; integration test via agent dry-run on office2
**Target Platform**: office2 (Ubuntu 24.04 LTS), deployed via SSH as claude user
**Project Type**: Single project — mixed documentation + script
**Performance Goals**: Intelligence layer completes in under 60 seconds; agent run time overhead under 60 seconds
**Constraints**: No new credentials; Tailscale-only; claude user only; no sudo
**Scale/Scope**: 2 agents currently; architecture supports growth to 10+ without rearchitecting

## Constitution Check

*GATE: Pre-Phase 0*

| Check | Status | Notes |
|-------|--------|-------|
| Testing standards | PASS | Intelligence layer script will have pytest coverage. Governance docs validated manually. |
| Quality gates | PASS | CI validation (validate_docs.py) runs on push. Self-review before push. |
| Performance benchmarks | PASS | Intelligence layer target: under 60 seconds. Agent overhead: under 60 seconds. |
| Branch strategy | PASS | Push directly to main. Solo maintainer. |
| Deployment constraints | PASS | All services on office2 (Ubuntu 24.04 LTS). Tailscale-only. |
| Risk boundaries | PASS | `02-Growth/_private/` never accessed. No credentials in code. No community skills without review. |
| Documentation sync | PASS | Architecture docs updated as part of this feature (FR-020, FR-021). |
| TEST_FIRST directive | PASS | Intelligence layer developed test-first. Governance docs validated against checklist. |

*No violations. No complexity tracking needed.*

## Project Structure

### Documentation (this feature)

```
kitty-specs/012-constitution-agent-governance-setup/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 research output
├── data-model.md        # Phase 1 data model
├── quickstart.md        # Phase 1 quickstart guide
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks.md             # Phase 2 output (NOT created by /spec-kitty.plan)
```

### Source Code (repository root)

```
docs/constitution/
├── FELIX-CONSTITUTION.md          # Governance document (FR-001 through FR-004)
├── AGENT-REGISTRY.md              # Human-readable agent registry (FR-005)
└── agent-registry.json            # Machine-readable agent registry (FR-005, FR-006)

scripts/openclaw/
├── agents/
│   ├── felix-admin-capture/
│   │   └── AGENTS.md              # Updated with constitution preamble (FR-017)
│   └── felix-admin-habits/
│       └── AGENTS.md              # Updated with constitution preamble (FR-017)
├── skills/
│   └── skill-author/
│       └── SKILL.md               # Skill-authoring skill (FR-015)
└── observation/
    ├── summarize.py               # Centralized intelligence layer (FR-009, FR-010)
    ├── config.py                  # Configuration loading from agent-registry.json
    └── tests/
        ├── test_summarize.py      # Unit tests for intelligence layer
        └── fixtures/              # Sample log files for testing

docs/handbooks/
└── felix-governance.md            # Operations runbook (FR-019)

docs/design/architecture/data/
└── service-inventory.json         # Updated with autonomy_level fields (FR-020)

docs/handbooks/
└── openclaw-ops.md                # Updated with constitution references (FR-021)
```

**Structure Decision**: This feature is primarily documentation (governance docs, skills, standing orders) with one Python script (the intelligence layer). No web frontend, no API backend. The script lives at `scripts/openclaw/observation/` alongside the existing agent and skill directories.

## Design Decisions (from research.md)

### Autonomy Level Model

Three operating modes that determine agent behavior and surfacing depth:

| Level | Name | Agent Behavior | Surfacing Behavior |
|-------|------|---------------|-------------------|
| 1 | **Assisted** | Proposes actions, Kent confirms | All activity in daily digest |
| 2 | **Observed** | Executes autonomously | All activity in daily digest |
| 3 | **Autonomous** | Executes autonomously | Only exceptions in daily digest |

- Critical alerts (errors, security) always surface at every level — no exceptions
- Promotion: 30+ days at current level + Kent's explicit decision
- Demotion: any time, any reason, no minimum time
- Surfacing behavior is determined by autonomy level — not a separate toggle

### Activity Surfacing Delivery

**Primary:** Obsidian notes in `~/second-brain/notes/00-System/agent-activity/`
**Critical alerts:** WhatsApp (when DM policy is re-enabled)
**Fallback:** Obsidian-only (critical alerts marked prominently in digest)

See [research.md](research.md) — Decision 1 for full evaluation.

### Intelligence Layer Architecture

**Centralized summarization script** (`scripts/openclaw/observation/summarize.py`):
- Runs daily at 7:00 PM ET via cron on office2 (after last agent run at 6:00 PM)
- Reads all agent logs from `~/second-brain/agents/logs/` for the current day
- Reads `agent-registry.json` for each agent's autonomy level
- Applies surfacing rules based on autonomy level:
  - Assisted/Observed: routine → counts, flagged/error/security → elevated detail
  - Autonomous: routine → omitted, flagged/error/security → elevated detail
- Writes consolidated digest to `~/second-brain/notes/00-System/agent-activity/overview.md`
- Writes per-agent detail to `~/second-brain/notes/00-System/agent-activity/{agent-name}.md`
- Sends WhatsApp critical alert if errors/security items exist and WhatsApp is enabled

**Cadence:** Daily digest at 7:00 PM ET + immediate critical alerts at run time
**Time window:** Rolling 24 hours, reset at digest time
**Retention:** Digest overwritten each cycle; raw logs retained 90 days

### Agent Registry

**Dual-format:**
- `docs/constitution/agent-registry.json` — machine-readable, authoritative
- `docs/constitution/AGENT-REGISTRY.md` — human-readable narrative view

Autonomy level stored as string enum (`assisted`/`observed`/`autonomous`) in JSON registry.
JSON schema defined in [data-model.md](data-model.md).

### Standardized Log Format

All agents must write logs with these categories for the intelligence layer to process:
- **routine** — normal successful operations (surfaced as counts at Assisted/Observed; omitted at Autonomous)
- **flagged** — items requiring Kent's attention (elevated with detail at all levels)
- **error** — operation failures (always surfaced as critical alert at all levels)
- **security** — security concerns (always surfaced as critical alert at all levels)

The existing felix-admin-capture log format is the base. felix-admin-habits adopts the same format. The intelligence layer parses these categories from the structured markdown.

### Standing Order Updates

Additive only. A governance preamble is prepended to each agent's AGENTS.md:
- Current autonomy level
- Reference to FELIX-CONSTITUTION.md
- Statement that standing orders supplement but do not override the constitution

No existing standing order content is modified.

### Skill-Authoring Skill

Bootstrapped from Whisper and Vikunja API skills. Augmented with:
- External best practices for agent skill design
- Community skill review criteria (security, quality, compatibility, scope)
- Project-specific conventions (credential store, no hardcoded IDs, error handling, identity labels)
- Living document — updated when project conventions change

## Constitution Check (Post-Design)

| Check | Status | Notes |
|-------|--------|-------|
| Testing standards | PASS | `scripts/openclaw/observation/tests/` with pytest. Governance docs validated against checklist. |
| Risk boundaries | PASS | Privacy boundary encoded in constitution. No credentials introduced. Tailscale-only. |
| Documentation sync | PASS | service-inventory.json and openclaw-ops.md updated in same feature. |
| TEST_FIRST directive | PASS | Intelligence layer: tests written before implementation. Sample log fixtures in test directory. |

*No new violations. Design is consistent with pre-Phase 0 check.*

## Implementation Sequence

1. **Read existing agent files** — understand current conventions before writing constitution
2. **Write constitution** — formalize patterns already working, including autonomy level model (FR-001 through FR-004)
3. **Write agent registry** — JSON + Markdown, register both agents at Assisted (FR-005 through FR-007)
4. **Standardize log format** — define categories, update agent log sections if needed (FR-008)
5. **Write intelligence layer** — centralized summarizer script with tests (FR-009, FR-010, FR-011)
6. **Configure activity surfacing** — cron schedule, digest file creation (FR-012, FR-013)
7. **Write skill-authoring skill** — SKILL.md with conventions and review criteria (FR-015)
8. **Update agent standing orders** — additive preamble referencing constitution, stating autonomy level (FR-017)
9. **Write governance runbook** — operational procedures including promotion/demotion (FR-019)
10. **Update architecture docs** — service-inventory.json autonomy_level fields, openclaw-ops.md refs (FR-020, FR-021)
11. **Deploy to office2** — all updated files via SSH as claude user (FR-016, FR-018)

## Risk Mitigations

| Risk | Mitigation |
|------|-----------|
| Constitution contradicts working agent behavior | FR-001 requires reading existing AGENTS.md before writing. Constitution formalizes existing patterns. |
| WhatsApp unavailable for critical alerts | Obsidian digest still contains critical alerts (marked prominently). Graceful degradation. |
| Intelligence layer log parsing breaks on format changes | Standardized log categories defined in constitution. Tests use fixture logs. |
| Skill-authoring skill becomes stale | Constitution mandates update when conventions change. Version-stamped. |
| Agent demoted but standing orders not updated | Registry is authoritative for autonomy level. Standing orders state level at registration; intelligence layer reads current level from registry, not AGENTS.md. |
