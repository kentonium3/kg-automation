# Tasks: Constitution & Agent Governance Setup

**Feature**: 012-constitution-agent-governance-setup
**Date**: 2026-04-01
**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

## Subtask Index

| ID | Description | WP | Parallel |
|----|------------|-----|----------|
| T001 | Read existing agent standing orders to understand conventions | WP01 | |
| T002 | Write FELIX-CONSTITUTION.md | WP01 | |
| T003 | Write agent-registry.json | WP01 | |
| T004 | Write AGENT-REGISTRY.md | WP01 | |
| T005 | Define standardized log format and create test fixtures | WP02 | |
| T006 | Write test_summarize.py (test-first) | WP02 | |
| T007 | Write config.py (registry loading, path resolution) | WP02 | [P] |
| T008 | Write summarize.py (core intelligence layer) | WP02 | |
| T009 | Add WhatsApp critical alert path to summarizer | WP02 | |
| T010 | Implement Obsidian digest output (overview + per-agent files) | WP02 | |
| T011 | Study existing Whisper and Vikunja API skills | WP03 | |
| T012 | Write skill-author/SKILL.md (format, conventions, review criteria, examples) | WP03 | |
| T013 | Update felix-admin-capture AGENTS.md with constitution preamble | WP04 | [P] |
| T014 | Update felix-admin-habits AGENTS.md with constitution preamble | WP04 | [P] |
| T015 | Write felix-governance.md runbook | WP04 | |
| T016 | Update service-inventory.json with autonomy_level fields | WP04 | [P] |
| T017 | Update openclaw-ops.md with constitution references | WP04 | [P] |
| T018 | Deploy all governance docs to office2 | WP05 | |
| T019 | Deploy skill-authoring skill and updated agent workspaces to office2 | WP05 | |
| T020 | Set up intelligence layer on office2 (script + cron + directories) | WP05 | |
| T021 | Run dry-run test of intelligence layer on office2 | WP05 | |
| T022 | Verify Obsidian Sync picks up digest files | WP05 | |

## Work Packages

### Phase 1: Foundation

---

#### WP01: Constitution & Agent Registry
**Prompt**: [tasks/WP01-constitution-and-registry.md](tasks/WP01-constitution-and-registry.md)
**Priority**: P0 — blocks all other WPs
**Dependencies**: none
**Subtasks**: T001, T002, T003, T004
**Estimated prompt size**: ~450 lines

**Goal**: Create the Felix constitution document and dual-format agent registry (JSON + Markdown) with both existing agents registered at Assisted (Level 1).

**Included subtasks**:
- [x] T001: Read existing agent standing orders (AGENTS.md, SOUL.md, IDENTITY.md, TOOLS.md for both agents) to understand current conventions before writing constitution
- [x] T002: Write `docs/constitution/FELIX-CONSTITUTION.md` — four directives, autonomy level model, privacy boundary (extensible), ClawHub constraint, activity surfacing per level, amendment process
- [x] T003: Write `docs/constitution/agent-registry.json` — both agents at Assisted, complete transition history entries
- [x] T004: Write `docs/constitution/AGENT-REGISTRY.md` — human-readable narrative view consistent with JSON

**Parallel opportunities**: T003 and T004 can be written in parallel after T002.

**Risks**:
- Constitution contradicting existing agent behavior — T001 mitigates by reading existing files first
- Registry schema incomplete — data-model.md provides the complete schema

---

### Phase 2: Implementation (parallelizable after WP01)

---

#### WP02: Intelligence Layer
**Prompt**: [tasks/WP02-intelligence-layer.md](tasks/WP02-intelligence-layer.md)
**Priority**: P1
**Dependencies**: WP01
**Subtasks**: T005, T006, T007, T008, T009, T010
**Estimated prompt size**: ~500 lines

**Goal**: Build the centralized summarization script that reads agent logs, applies autonomy-level-based filtering, writes Obsidian digests, and sends WhatsApp critical alerts.

**Included subtasks**:
- [x] T005: Define standardized log format specification and create sample log fixtures for testing
- [x] T006: Write `scripts/openclaw/observation/tests/test_summarize.py` (test-first per TEST_FIRST directive)
- [x] T007: Write `scripts/openclaw/observation/config.py` — loads agent-registry.json, resolves log/output paths
- [x] T008: Write `scripts/openclaw/observation/summarize.py` — core: reads logs, filters by category, applies autonomy-level rules, produces consolidated digest
- [x] T009: Add WhatsApp critical alert path (conditional on DM policy being enabled)
- [x] T010: Implement Obsidian digest output — overview.md and per-agent files written to `~/second-brain/notes/00-System/agent-activity/`

**Parallel opportunities**: T007 (config) can be developed in parallel with T005/T006 (fixtures/tests).

**Risks**:
- Log parsing breaks on unexpected format — fixtures and tests mitigate
- WhatsApp DM policy disabled — WhatsApp path implemented but gracefully degrades

---

#### WP03: Skill-Authoring Skill
**Prompt**: [tasks/WP03-skill-authoring-skill.md](tasks/WP03-skill-authoring-skill.md)
**Priority**: P1
**Dependencies**: none (independent — reads existing skills, not new constitution)
**Subtasks**: T011, T012
**Estimated prompt size**: ~400 lines

**Goal**: Create the skill-authoring skill that teaches agents how to write compliant OpenClaw skills conforming to project standards.

**Included subtasks**:
- [x] T011: Study existing Whisper and Vikunja API skills to extract format patterns, conventions, and best practices
- [x] T012: Write `scripts/openclaw/skills/skill-author/SKILL.md` — complete with frontmatter, format specification, project conventions, community skill review criteria, and pattern reference examples

**Parallel opportunities**: Entire WP parallelizable with WP02 and WP04.

**Risks**:
- Skill becomes stale as conventions evolve — version-stamped, constitution mandates updates

---

#### WP04: Agent Standing Orders & Documentation
**Prompt**: [tasks/WP04-agent-updates-and-docs.md](tasks/WP04-agent-updates-and-docs.md)
**Priority**: P1
**Dependencies**: WP01
**Subtasks**: T013, T014, T015, T016, T017
**Estimated prompt size**: ~400 lines

**Goal**: Update both agents' standing orders with constitution preamble, write the governance runbook, and update architecture documentation.

**Included subtasks**:
- [x] T013: Update `scripts/openclaw/agents/felix-admin-capture/AGENTS.md` with constitution preamble (autonomy level, constitution reference, compliance declaration)
- [x] T014: Update `scripts/openclaw/agents/felix-admin-habits/AGENTS.md` with constitution preamble
- [x] T015: Write `docs/handbooks/felix-governance.md` runbook — autonomy level promotion/demotion, new agent registration, activity surfacing, constitution violation handling
- [x] T016: Update `docs/design/architecture/data/service-inventory.json` — add `autonomy_level` field to each agent entry, set `updated_by: "F012"`
- [x] T017: Update `docs/handbooks/openclaw-ops.md` — add references to FELIX-CONSTITUTION.md and AGENT-REGISTRY.md

**Parallel opportunities**: T013/T014 parallel with each other; T016/T017 parallel with each other and with T015.

**Risks**:
- Standing order preamble conflicts with existing content — C-004 requires additive-only changes

---

### Phase 3: Deployment

---

#### WP05: Deployment & Verification
**Prompt**: [tasks/WP05-deployment-and-verification.md](tasks/WP05-deployment-and-verification.md)
**Priority**: P2
**Dependencies**: WP01, WP02, WP03, WP04
**Subtasks**: T018, T019, T020, T021, T022
**Estimated prompt size**: ~350 lines

**Goal**: Deploy all F012 artifacts to office2 and verify the complete system works end-to-end.

**Included subtasks**:
- [ ] T018: Deploy governance docs (constitution, registry, runbook, architecture updates) to office2
- [ ] T019: Deploy skill-authoring skill and updated agent workspace files to office2
- [ ] T020: Set up intelligence layer on office2 — deploy script, configure cron (7 PM ET daily), create `~/second-brain/notes/00-System/agent-activity/` directory
- [ ] T021: Run dry-run test of intelligence layer with existing log files on office2
- [ ] T022: Verify Obsidian Sync picks up digest files on Mac and iPhone

**Parallel opportunities**: T018 and T019 can run in parallel.

**Risks**:
- SSH access issues — verify `ssh office2-claude` works before starting
- Cron timezone — office2 uses UTC; must convert 7 PM ET correctly
- Obsidian Sync path exclusion — verify `notes/00-System/` is in sync scope

---

## Dependency Graph

```
WP01 (Constitution & Registry)
  ├──→ WP02 (Intelligence Layer)
  ├──→ WP04 (Agent Updates & Docs)
  └──→ WP05 (Deployment)

WP03 (Skill-Authoring Skill) ──→ WP05 (Deployment)

WP02 ──→ WP05
WP04 ──→ WP05
```

**Parallelization**: After WP01 completes, WP02, WP03, and WP04 can all run simultaneously. WP05 waits for all.

## MVP Scope

**WP01 alone** delivers the constitution and agent registry — the core governance framework. All other WPs build on it but the governance documents have immediate value even before the intelligence layer or deployment.

<!-- status-model:start -->
## Canonical Status (Generated)
- WP01: approved
- WP02: approved
- WP03: approved
- WP04: approved
<!-- status-model:end -->
