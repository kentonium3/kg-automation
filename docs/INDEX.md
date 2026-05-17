---
title: kg-automation Documentation Index
doc_type: reference
status: approved
owners: [kgale]
version: "2.0"
last_validated: 2026-05-13
---

# kg-automation Documentation Index

Master map for all active documentation under `docs/`. Referenced from
`CLAUDE.md` as the starting point for agents discovering documentation.

**Scope**: `docs/**` excluding `docs/archive/`
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
- [LLM Spend Baseline](<./design/architecture/llm-spend-baseline.md>) — monthly cost snapshot per service, trend commentary (narrative companion to `data/llm-spend-baseline.json`)

### docs/design/architecture/adr/ — Architecture Decision Records

Immutable, dated records of *why* particular options were chosen over alternatives. See the README for when to write one.

- [ADR Index](<./design/architecture/adr/README.md>)
- [ADR-0001 — Google Workspace integration via `gog`](<./design/architecture/adr/0001-google-workspace-via-gog.md>) (approved 2026-05-13)
- [ADR-0002 — Felix ↔ Vikunja task model](<./design/architecture/adr/0002-felix-vikunja-task-model.md>) (approved 2026-05-17)

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
- [LLM Spend Baseline](<./design/architecture/data/llm-spend-baseline.json>) — monthly LLM cost across all services (authoritative; see narrative companion in parent dir)

---

## Operational Runbooks (docs/runbooks/)

### Agent-executable runbooks

- [Doc Auditor Operations](<./runbooks/doc-auditor-ops.md>) — felix-doc-auditor agent operations: how it runs, manual triggers, scope management, stale-lock recovery, kill switch
- [Vikunja Operations](<./runbooks/vikunja-ops.md>)
- [OpenClaw Operations](<./runbooks/openclaw-ops.md>)
- [Obsidian Sync Operations](<./runbooks/obsidian-sync-ops.md>)
- [Transcribe Operations](<./runbooks/transcribe-ops.md>)
- [Ollama Operations](<./runbooks/ollama-ops.md>) — local LLM inference runtime (GPU-accelerated)
- [Inbox Processing](<./runbooks/inbox-ops.md>)
- [Goals Operations](<./runbooks/goals-ops.md>)
- [Habits Operations](<./runbooks/habits-ops.md>)
- [Task Intelligence Operations](<./runbooks/task-intelligence-ops.md>)
- [Escalation Engine Operations](<./runbooks/escalation-ops.md>)
- [OpenClaw Agent Setup](<./runbooks/openclaw-agent-setup.md>)
- [Google Workspace Operations](<./runbooks/google-workspace-ops.md>) — `gog` CLI setup, OAuth flow, pitfalls, common commands, second-account expansion (#100, ADR-0001)

### Human and mixed-audience runbooks

- [Agent Workspace Reconciliation](<./runbooks/agent-workspace-reconciliation.md>) — drift enforcement, factory-default lifecycle, last-author-wins strategy
- [Deployment Runbook](<./runbooks/deployment.md>) — how features are deployed to office2
- [Felix Governance](<./runbooks/felix-governance.md>) — agent registration, promotion, demotion, violation handling
- [Vault Path Registry Migration](<./runbooks/vault-path-registry-migration.md>) — reusable playbook for migrating vault folder names through the registry (how-to guide; first executed by mission 026 / #152)
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

- [Felix Capability Roadmap](<./design/felix-capability-roadmap.md>) — living capability status, feature sequence, and design principles
- [Vision & Architecture](<./archive/vision-framework.md>) *(archived — superseded by capability roadmap)*
- [Personal AI System Spec v1.0](<./archive/personal-ai-system-spec-v1.0.md>) *(archived — design intent consolidated into roadmap; work items in GitHub issues)*
- [Strategic Acceleration Charter](<./archive/strategic-acceleration-charter.md>) *(archived — pre-Felix era, superseded by capability roadmap)*
- [Adversarial Analysis](<./archive/adversarial-analysis.md>) *(archived — items extracted to #126, #119)*
- [office2 Backup & Security](<./design/office2-backup-and-security.md>)
- [Vikunja Integration Notes](<./archive/Vikunja.md>) *(archived — items covered by #103)*
- [Risk Register](<./archive/risk-register.md>) *(archived — items transcribed to GitHub issues #114, #115, #116)*
- [Decision Log](<./archive/decision-log.md>) *(archived — decisions tracked as GitHub issues with RFC labels)*

### docs/design/standards/ — Cross-cutting standards

- [Divio Classification Standard](<./design/standards/divio-classification.md>)
- [Documentation Standards](<./design/standards/doc-standards.md>)
- [Visual Documentation Style](<./design/standards/visual-docs-style.md>)
- [Obsidian Linter Alignment](<./design/standards/obsidian-linter-alignment.md>)
- [Allowed Values (JSON)](<./design/standards/allowed-values.json>)
- [Validator Policy (JSON)](<./design/standards/validator-policy.json>)

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

## Diagnostics (docs/diagnostics/)

Active troubleshooting and upstream bug reporting.

- [Spec-Kitty Workflow Journal](<./diagnostics/spec-kitty-workflow-journal.md>)
- [Spec-Kitty Bug Report Template](<./diagnostics/spec-kitty-bug-report-template.md>)

---

## Archive (docs/archive/)

Frozen historical artifacts. Not maintained. Excluded from this index.

---

## Adding a New Document

1. Identify the Divio type per [Divio Classification Standard](<./design/standards/divio-classification.md>).
2. Place the file in the canonical home for that type.
3. Add frontmatter (`title`, `doc_type`, `status` minimum; `audience` required for runbooks).
4. **Update this INDEX.md** in the same change.
