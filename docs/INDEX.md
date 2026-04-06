---
title: kg-automation Documentation Index
doc_type: reference
status: approved
owners: [kgale]
version: "1.0"
last_validated: 2026-04-05
---

# kg-automation Documentation Index

This is the master map for all active documentation under `docs/`. It is referenced from `CLAUDE.md` as the starting point for agents discovering documentation. Entries are grouped by directory context with Divio-type annotations.

The classification taxonomy (Divio parent types + named sub-types) is defined in [Divio Classification Standard](<./design/standards/divio-classification.md>). Every active document has a `doc_type` frontmatter field drawn from this taxonomy.

## How to use this index

- **AI agents** reading `CLAUDE.md` follow the reference here → navigate to the relevant directory by task type → locate the specific document.
- **Humans** adding a new doc: identify its Divio type, place it in the canonical home for that type, update this INDEX.md as part of the same change (per change-control protocol, WP09).
- **Path reachability**: every active document should be reachable in ≤3 link hops from `CLAUDE.md` (which links here).

**Scope**: `docs/**` excluding `docs/archive/`. The `docs/issues/diagnostics/` directory is exempt from restructuring (actively used at runtime).

---

## Constitution & Governance

### docs/constitution/ — Governance authority

All `reference`. Felix agent governance, autonomy levels, and principles.

- [Felix Constitution](<./constitution/FELIX-CONSTITUTION.md>) — top-level governance, autonomy levels, operational principles
- [Agent Registry (narrative)](<./constitution/AGENT-REGISTRY.md>) — current agent state, deployment status, autonomy transitions
- [Agent Registry (JSON)](<./constitution/agent-registry.json>) — machine-readable authoritative registry

### docs/runbooks/governance/ — Governance operations

Change control governance runbooks (F016):

- [Pre-Flight Change Checklist](<./runbooks/governance/pre-flight-checklist.md>) — `runbook` `both` — mandatory pre-flight assessment for Tier 0/1/2 changes
- [Post-Change Verification Protocol](<./runbooks/governance/post-change-verification.md>) — `runbook` `both` — health-check verification after Tier 0/1/2 changes
- [Incident Postmortem Template](<./runbooks/governance/incident-postmortem-template.md>) — `runbook` `both` — reusable template for blameless incident analysis

---

## System Architecture

### docs/design/architecture/ — Current-state system reference

All `reference`. Describes deployed services, topology, credentials, and data flows.

- [README](<./design/architecture/README.md>) — architecture suite index
- [Service Inventory](<./design/architecture/service-inventory.md>) — running services, ports, systemd units, deployment details
- [Data Flows](<./design/architecture/data-flows.md>) + [Mermaid view](<./design/architecture/data-flows.view.md>)
- [Physical Topology](<./design/architecture/physical-topology.md>) + [Mermaid view](<./design/architecture/physical-topology.view.md>)
- [Credentials & Secrets](<./design/architecture/credentials-and-secrets.md>)
- [Identity Model](<./design/architecture/identity-model.md>)
- [Security Posture](<./design/architecture/security-posture.md>) — policy exceptions recorded here
- [Backup & Recovery](<./design/architecture/backup-and-recovery.md>)
- [Change Control Protocol](<./design/architecture/change-control.md>) — protocol for updating this INDEX and architecture docs
- [Service Dependencies Diagram](<./design/architecture/service-dependencies.view.md>) — `guide` — Mermaid diagram of all office2 service dependencies (F016)
- [Glossary](<./design/architecture/glossary.md>)

### docs/design/architecture/data/ — Canonical machine-readable home

All `reference`. Authoritative operational state (JSON) + schemas. **Exempt from moves (F015 constraint C-001)**. See [architecture README](<./design/architecture/README.md>) for canonical-home policy.

- [Service Inventory (JSON)](<./design/architecture/data/service-inventory.json>)
- [Hardware Inventory (JSON)](<./design/architecture/data/hardware-inventory.json>)
- [Network Topology (JSON)](<./design/architecture/data/network-topology.json>)
- [Credential Manifest (JSON)](<./design/architecture/data/credential-manifest.json>)
- [Data Flows (JSON)](<./design/architecture/data/data-flows.json>)
- [Capabilities Schema (JSON)](<./design/architecture/data/capabilities-schema.json>)
- [Catalog Schema (JSON)](<./design/architecture/data/catalog-schema.json>)
- [Change Risk Taxonomy (JSON)](<./design/architecture/data/change-risk-taxonomy.json>) — five-tier risk taxonomy with guardrail protocols (F016)

---

## Operational Runbooks (docs/runbooks/)

Prescriptive step-by-step procedures. Each runbook declares its `audience`: `agent-executable`, `human-only`, or `both`.

### Agent-executable runbooks

Candidates for future skill conversion. Mechanical queries/mutations using APIs, systemctl, or shell commands.

- [Vikunja Operations](<./runbooks/vikunja-ops.md>) — `runbook` `agent-executable`
- [OpenClaw Operations](<./runbooks/openclaw-ops.md>) — `runbook` `agent-executable`
- [Obsidian Sync Operations](<./runbooks/obsidian-sync-ops.md>) — `runbook` `agent-executable`
- [Transcribe Operations](<./runbooks/transcribe-ops.md>) — `runbook` `agent-executable`
- [Inbox Processing](<./runbooks/inbox-ops.md>) — `runbook` `agent-executable`
- [Goals Operations](<./runbooks/goals-ops.md>) — `runbook` `agent-executable`
- [Habits Operations](<./runbooks/habits-ops.md>) — `runbook` `agent-executable`
- [Task Intelligence Operations](<./runbooks/task-intelligence-ops.md>) — `runbook` `agent-executable`

### Human-only runbooks

Require judgement, credentials beyond agents' access, or policy decisions.

- [Felix Governance](<./runbooks/felix-governance.md>) — `runbook` `human-only`
- [Spec-Kitty Install Guide](<./runbooks/spec-kitty-init-in-existing-repo.md>) — `runbook` `human-only`
- [CI Handbook](<./runbooks/ci-handbook.md>) — `runbook` `human-only`
- [Agent Handbook](<./runbooks/agent-handbook.md>) — `runbook` `human-only`
- [Agent Execution Roles](<./runbooks/agent-execution-roles.md>) — `runbook` `human-only`
- [Claude Code — Execution Agent](<./runbooks/claude-code.md>) — `runbook` `human-only`

### Mixed-audience runbooks

Agent uses API/CLI path; human uses UI path. Variations documented in-doc.

- [Deployment Runbook](<./runbooks/deployment.md>) — `runbook` `both`
- [Observation Intelligence Ops](<./runbooks/observation-ops.md>) — `runbook` `both`
- [Obsidian Setup Guide](<./runbooks/obsidian-setup.md>) — `runbook` `both`
- [Obsidian Vault](<./runbooks/obsidian.md>) — `runbook` `both`
- [Maintenance & Housekeeping](<./runbooks/maintenance.md>) — `runbook` `both`
- [WhatsApp Channel Operations](<./runbooks/whatsapp-ops.md>) — `runbook` `both`

### Non-runbook content in runbooks/

- [Repository Governance — Branch Protection & PR Policy](<./runbooks/repo-governance.md>) — `standard` (git workflow standard)
- [Templater Commands (Canon v2)](<./runbooks/templater-commands.md>) — `reference` (command list)
- [F001 Vikunja Deploy — Acceptance Results](<./runbooks/f001-acceptance-results.md>) — `reference`
- [F002 OpenClaw Install — Acceptance Results](<./runbooks/f002-acceptance-results.md>) — `reference`

---

## Design & Standards

### docs/design/ top-level — Vision and rationale

- [Vision & Architecture](<./design/vision-framework.md>) — `reference` — mission, platform, design principles
- [Personal AI System Spec v1.0](<./design/personal-ai-system-spec-v1.0.md>) — `reference` — current authoritative system spec
- [Personal AI System Spec v0.3](<./design/personal-ai-system-spec-v03.md>) — `reference` `deprecated` — superseded by v1.0
- [Felix Capability Roadmap](<./design/felix-capability-roadmap.md>) — `reference` — living capability status and feature sequence
- [Strategic Acceleration Charter](<./design/strategic-acceleration-charter.md>) — `explanation` — strategic direction rationale
- [Adversarial Analysis](<./design/adversarial-analysis.md>) — `explanation` — security and resilience rationale
- [office2 Backup & Security](<./design/office2-backup-and-security.md>) — `explanation` — backup + security design narrative
- [Vikunja Integration Notes](<./design/Vikunja.md>) — `explanation` — Vikunja design improvements and open questions
- [Risk Register](<./design/risk-register.md>) — `reference` — risk inventory and mitigations
- [Decision Log](<./design/decision-log.md>) — `reference` — append-only decision history
- [Project Charter](<./design/project-charter.md>) — `reference` — template

### docs/design/standards/ — Cross-cutting standards

- [Divio Classification Standard](<./design/standards/divio-classification.md>) — `standard` — authoritative Divio taxonomy (produced by F015 WP01)
- [Documentation Standards](<./design/standards/doc-standards.md>) — `standard` — frontmatter schema, file naming, status lifecycle
- [Visual Documentation Style](<./design/standards/visual-docs-style.md>) — `standard` — Mermaid diagrams, visual conventions
- [Obsidian Linter Alignment](<./design/standards/obsidian-linter-alignment.md>) — `standard` — linter configuration policy
- [Standards README](<./design/standards/standards-readme.md>) — `reference` — standards directory nav
- [Frontmatter Schema (JSON)](<./design/standards/frontmatter.schema.json>) — machine-readable schema
- [Allowed Values (JSON)](<./design/standards/allowed-values.json>) — enum definitions
- [Validator Policy (JSON)](<./design/standards/validator-policy.json>) — validation policy

### docs/design/research/ — F005 architecture research

All from F005 (System Architecture Development feature). Mix of `explanation` (rationale) and `reference` (inventories).

**F005-005-system-architecture-development/**:

- [Agent Team Architecture](<./design/research/005-system-architecture-development/agent-team-architecture.md>) — `explanation`
- [Data Architecture](<./design/research/005-system-architecture-development/data-architecture.md>) — `explanation`
- [Data, Privacy, and Identity Research](<./design/research/005-system-architecture-development/data-privacy-identity.md>) — `explanation` (ambiguity flagged with data-architecture.md)
- [Integration and Tool Research](<./design/research/005-system-architecture-development/integration-needs.md>) — `explanation`
- [OpenClaw Capability Research](<./design/research/005-system-architecture-development/openclaw-capabilities.md>) — `explanation`
- [Integration Map](<./design/research/005-system-architecture-development/integration-map.md>) — `reference`
- [Local Architecture Audit](<./design/research/005-system-architecture-development/local-audit.md>) — `reference`
- [Feature and Capability Roadmap](<./design/research/005-system-architecture-development/roadmap.md>) — `reference`
- [User Story Catalog](<./design/research/005-system-architecture-development/user-story-catalog.md>) — `reference`

---

## Feature Specifications (docs/func-spec/)

All `spec` (except templates/instructions). See [directory listing](func-spec/) for the complete list.

**Active spec-kitty features**:

- F001 — Vikunja Docker Deploy
- F002 — OpenClaw Install
- F003 — Whisper Transcription Skill
- F004 — WhatsApp Channel
- F005 — System Architecture Review
- F006 — Goal and Outcome Structure
- F007 — Vikunja API Skill
- F008 — Inbox Processing Migration
- F009 — Daily Habit Check-in
- F010 — Obsidian Sync on office2
- F011 — Second Brain Vault Cleanup
- F012 — Constitution Update + Agent Setup
- F013 — Vikunja Task Intelligence Agent
- F014 — Felix Core Digest
- F015 — Documentation Architecture Rationalization (this feature)
- F016 — Change Control Governance & Incident Management
- F017 — Vikunja Habit Tracking Architecture Research
- F018 — Habit Today Filter Visibility
- F019 — Escalation Engine
- F020 — Google Calendar OAuth Skill
- FUTURE — Commitment Manager Agent

**Templates & instructions**:

- [Spec-Kitty Feature Specification Template](<./func-spec/_TEMPLATE_spec_kitty_input.md>) — `reference`
- [Spec-Kitty Research Mission Template](<./func-spec/_TEMPLATE_spec_kitty_research_input.md>) — `reference`
- [Claude Pre-Implementation Prompt](<./func-spec/claude-pre-implementation-prompt.md>) — `reference` — standing orchestration directive
- [F015 Augmentation for Alignment](<./func-spec/F015_aug_for_alignment.md>) — `reference` — F015 spec refinement inputs

**Active research missions**:

- [F017 — Vikunja Habit Tracking Architecture Research](<./func-spec/F017_vikunja_habit_tracking_architecture_research.md>) — complete, informs F018

---

## Issues (docs/issues/)

### docs/issues/diagnostics/ — Incident diagnostics

All `diagnostic`. Runtime issue tracking and troubleshooting notes. **Exempt from restructuring (F015 constraint C-002)**.

- [Spec-Kitty Workflow Journal](<./issues/diagnostics/spec-kitty-workflow-journal.md>) — `active` — chronological log of spec-kitty workflow observations
- [F012 Merge Breadcrumbs](<./issues/diagnostics/f012-merge-breadcrumbs.md>) — `resolved` — F012 merge incident notes
- [Spec-Kitty Feedback](issues/diagnostics/spec-kitty-feedback/) — 5 individual upstream bug reports (all `active`)

### docs/issues/postmortems/ — Post-incident analysis

All `postmortem`. Filename format: `YYYY-MM-DD_incident-slug.md`.

- [2026-04-03: Vikunja UFW Outage](<./issues/postmortems/2026-04-03-vikunja-ufw-outage.md>) — `postmortem` — origin incident for F016 change control governance

---

## Archive (docs/archive/)

Frozen historical artifacts. Not maintained to current standards. Excluded from this INDEX's active-document scope.

---

## Adding a New Document

1. Identify the Divio type per [Divio Classification Standard](<./design/standards/divio-classification.md>).
2. Place the file in the canonical home for that type.
3. Add frontmatter (`title`, `doc_type`, `status` minimum; `audience` required for runbooks).
4. **Update this INDEX.md** in the same change — not updating INDEX.md is a change-control protocol violation.
5. If the document should be referenced from `CLAUDE.md` or the Felix constitution, add the reference there.

---

## Maintenance

This INDEX is the chain-of-reference anchor for all active kg-automation documentation. Its accuracy is enforced by:

- **Change-control protocol**: adding, moving, archiving, or deprecating a document requires updating this INDEX.md in the same feature branch (per `docs/design/architecture/change-control.md`, updated by F015 WP09).
- **Feature review gate**: features that touch `docs/**` without updating this INDEX are flagged during review.

Report stale entries or broken links by adding an issue note to `docs/issues/diagnostics/`.

---

**Version**: 1.0 — initial published version authored under F015 (WP07).
