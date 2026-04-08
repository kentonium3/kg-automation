---
title: kg-automation Documentation Index
doc_type: reference
status: approved
owners: [kgale]
version: "2.0"
last_validated: 2026-04-08
---

# kg-automation Documentation Index

Master map for all active documentation under `docs/`. Referenced from
`CLAUDE.md` as the starting point for agents discovering documentation.

**Scope**: `docs/**` excluding `docs/archive/` and `docs/issues/diagnostics/`
(both exempt from restructuring).

---

## Constitution & Governance

### docs/constitution/ — Governance authority

- [Felix Constitution](<./constitution/FELIX-CONSTITUTION.md>) — top-level governance, autonomy levels, principles
- [Agent Registry (narrative)](<./constitution/AGENT-REGISTRY.md>) — current agent state, deployment status, autonomy transitions
- [Agent Registry (JSON)](<./constitution/agent-registry.json>) — machine-readable authoritative registry

### docs/runbooks/governance/ — Change control governance

- [Pre-Flight Change Checklist](<./runbooks/governance/pre-flight-checklist.md>) — mandatory assessment for Tier 0/1/2 changes
- [Post-Change Verification Protocol](<./runbooks/governance/post-change-verification.md>) — health-check verification after changes
- [Incident Postmortem Template](<./runbooks/governance/incident-postmortem-template.md>) — reusable template for incident analysis

---

## System Architecture

### docs/design/architecture/ — Current-state system reference

- [README](<./design/architecture/README.md>) — architecture suite index
- [Service Inventory](<./design/architecture/service-inventory.md>) — running services, ports, systemd units
- [Data Flows](<./design/architecture/data-flows.md>) + [Mermaid view](<./design/architecture/data-flows.view.md>)
- [Physical Topology](<./design/architecture/physical-topology.md>) + [Mermaid view](<./design/architecture/physical-topology.view.md>)
- [Credentials & Secrets](<./design/architecture/credentials-and-secrets.md>)
- [Identity Model](<./design/architecture/identity-model.md>)
- [Security Posture](<./design/architecture/security-posture.md>)
- [Backup & Recovery](<./design/architecture/backup-and-recovery.md>)
- [Change Control Protocol](<./design/architecture/change-control.md>)
- [Service Dependencies Diagram](<./design/architecture/service-dependencies.view.md>)
- [Glossary](<./design/architecture/glossary.md>)

### docs/design/architecture/data/ — Machine-readable state (JSON)

Authoritative operational state. **Exempt from moves (F015 constraint C-001)**.

- [Service Inventory](<./design/architecture/data/service-inventory.json>)
- [Hardware Inventory](<./design/architecture/data/hardware-inventory.json>)
- [Network Topology](<./design/architecture/data/network-topology.json>)
- [Credential Manifest](<./design/architecture/data/credential-manifest.json>)
- [Data Flows](<./design/architecture/data/data-flows.json>)
- [Capabilities Schema](<./design/architecture/data/capabilities-schema.json>)
- [Catalog Schema](<./design/architecture/data/catalog-schema.json>)
- [Change Risk Taxonomy](<./design/architecture/data/change-risk-taxonomy.json>)
- [Doc Domain Map](<./design/architecture/data/doc-domain-map.json>)

---

## Operational Runbooks (docs/runbooks/)

### Agent-executable runbooks

- [Vikunja Operations](<./runbooks/vikunja-ops.md>)
- [OpenClaw Operations](<./runbooks/openclaw-ops.md>)
- [Obsidian Sync Operations](<./runbooks/obsidian-sync-ops.md>)
- [Transcribe Operations](<./runbooks/transcribe-ops.md>)
- [Inbox Processing](<./runbooks/inbox-ops.md>)
- [Goals Operations](<./runbooks/goals-ops.md>)
- [Habits Operations](<./runbooks/habits-ops.md>)
- [Task Intelligence Operations](<./runbooks/task-intelligence-ops.md>)
- [Escalation Engine Operations](<./runbooks/escalation-ops.md>)

### Human and mixed-audience runbooks

- [Felix Governance](<./runbooks/felix-governance.md>) — agent registration, promotion, demotion, violation handling
- [Deployment Runbook](<./runbooks/deployment.md>) — how features are deployed to office2
- [Repository Governance](<./runbooks/repo-governance.md>) — git workflow, labels, milestones, issue management
- [GitHub Issues Workflow](<./runbooks/github-issues-workflow.md>) — issue lifecycle, templates, triage, project board
- [Observation Intelligence Ops](<./runbooks/observation-ops.md>)
- [Obsidian Setup Guide](<./runbooks/obsidian-setup.md>)
- [Obsidian Vault](<./runbooks/obsidian.md>)
- [WhatsApp Channel Operations](<./runbooks/whatsapp-ops.md>)

### Deprecated runbooks (retained in place)

- [Spec-Kitty Install Guide](<./runbooks/spec-kitty-init-in-existing-repo.md>) — historical, setup already complete

### Non-runbook content in runbooks/

- [Templater Commands (Canon v2)](<./runbooks/templater-commands.md>) — command reference

---

## Design & Standards

### docs/design/ — Vision and rationale

- [Vision & Architecture](<./design/vision-framework.md>)
- [Personal AI System Spec v1.0](<./design/personal-ai-system-spec-v1.0.md>) — current authoritative system spec
- [Felix Capability Roadmap](<./design/felix-capability-roadmap.md>) — living capability status and feature sequence
- [Strategic Acceleration Charter](<./design/strategic-acceleration-charter.md>)
- [Adversarial Analysis](<./design/adversarial-analysis.md>)
- [office2 Backup & Security](<./design/office2-backup-and-security.md>)
- [Vikunja Integration Notes](<./design/Vikunja.md>)
- [Risk Register](<./design/risk-register.md>)
- [Decision Log](<./design/decision-log.md>)

### docs/design/standards/ — Cross-cutting standards

- [Divio Classification Standard](<./design/standards/divio-classification.md>)
- [Documentation Standards](<./design/standards/doc-standards.md>)
- [Visual Documentation Style](<./design/standards/visual-docs-style.md>)
- [Obsidian Linter Alignment](<./design/standards/obsidian-linter-alignment.md>)
- [Allowed Values (JSON)](<./design/standards/allowed-values.json>)
- [Validator Policy (JSON)](<./design/standards/validator-policy.json>)

### docs/design/research/ — Architecture research

- [Agent Team Architecture](<./design/research/005-system-architecture-development/agent-team-architecture.md>)
- [Data Architecture](<./design/research/005-system-architecture-development/data-architecture.md>)
- [OpenClaw Capability Research](<./design/research/005-system-architecture-development/openclaw-capabilities.md>)
- [OpenClaw Runtime State Audit](<./design/research/005-system-architecture-development/openclaw-runtime-state-audit.md>)
- [Integration Map](<./design/research/005-system-architecture-development/integration-map.md>)
- [User Story Catalog](<./design/research/005-system-architecture-development/user-story-catalog.md>)

---

## Feature Specifications (docs/func-spec/)

**Historical archive.** Features F001-F020 are documented here as the
historical record. New features are tracked as GitHub Issues — see
[GitHub Issues Workflow](<./runbooks/github-issues-workflow.md>).

**Templates**:

- [Feature Specification Template](<./func-spec/_TEMPLATE_spec_kitty_input.md>)
- [Research Mission Template](<./func-spec/_TEMPLATE_spec_kitty_research_input.md>)
- [Docs Debt Issue Template](<../.github/ISSUE_TEMPLATE/docs-debt.md>)
- [Research Issue Template](<../.github/ISSUE_TEMPLATE/research.md>)

---

## Issues (docs/issues/)

### docs/issues/diagnostics/ — Incident diagnostics

Exempt from restructuring. Runtime issue tracking and troubleshooting.

- [Spec-Kitty Workflow Journal](<./issues/diagnostics/spec-kitty-workflow-journal.md>)
- [Spec-Kitty Feedback](issues/diagnostics/spec-kitty-feedback/) — upstream bug reports
- [Obsolete Workflow References Audit](<./issues/diagnostics/obsolete-workflow-references-audit.md>)

### docs/issues/postmortems/

- [2026-04-03: Vikunja UFW Outage](<./issues/postmortems/2026-04-03-vikunja-ufw-outage.md>)

---

## Archive (docs/archive/)

Frozen historical artifacts. Not maintained. Excluded from this index.

---

## Adding a New Document

1. Identify the Divio type per [Divio Classification Standard](<./design/standards/divio-classification.md>).
2. Place the file in the canonical home for that type.
3. Add frontmatter (`title`, `doc_type`, `status` minimum; `audience` required for runbooks).
4. **Update this INDEX.md** in the same change.
