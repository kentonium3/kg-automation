---
title: kg-automation Documentation Index
doc_type: reference
status: approved
owners: [kgale]
version: "2.0"
last_validated: 2026-05-26
tags: [152, 126, 119, 103, 114, 115, 116, 490, 518/, 507, 572]
---

# kg-automation Documentation Index

Master map for all active documentation under `docs/`. Referenced from
`CLAUDE.md` as the starting point for agents discovering documentation.

**Scope**: `docs/**` excluding `docs/archive/`
(both exempt from restructuring).

---

## Onboarding & Navigation

- [Developer Portal](<./DEVELOPER_PORTAL.md>) — guided onboarding sitemap (start here for new agents and contributors)
- [Doc Maintenance](<./runbooks/doc-maintenance.md>) — link conventions, runbook frontmatter, portal filter, and validator behavior

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
- [LLM Spend Baseline](<./design/architecture/llm-spend-baseline.md>) — monthly cost snapshot per service, trend commentary (narrative companion to `data/llm-spend-baseline.json`) *(pre-2026-05-26 doc-audit suspension; expect substantial June 2026 drop)*
- [LLM Cost Source Ledger](<./design/architecture/llm-cost.md>) — Kent's raw invoice/dashboard sweep (Anthropic, Gemini, etc.); source data feeding the spend baseline

### docs/design/architecture/adr/ — Architecture Decision Records

Immutable, dated records of *why* particular options were chosen over alternatives. See the README for when to write one.

- [ADR Index](<./design/architecture/adr/README.md>)
- [ADR-0001 — Google Workspace integration via `gog`](<./design/architecture/adr/0001-google-workspace-via-gog.md>) (approved 2026-05-13)
- [ADR-0002 — Felix ↔ Vikunja task model](<./design/architecture/adr/0002-felix-vikunja-task-model.md>) (approved 2026-05-17)
- [ADR-0004 — Enable Tailscale SSH on office2 with `accept` ACL](<./design/architecture/adr/0004-tailscale-ssh-with-accept-acl.md>) (approved 2026-06-09)
- [ADR-0005 — Vikunja client standardization (base URL, token, timeout, error policy)](<./design/architecture/adr/0005-vikunja-client-standards.md>) (approved 2026-06-10)

### docs/design/architecture/data/ — Machine-readable state (JSON)

Authoritative operational state. **Exempt from moves (F015 constraint C-001)**.

- [Agent State Log Schema](<./design/architecture/data/agent-state-log-schema.md>) (reference) — canonical JSONL schema for the shared agent state log
- [Service Inventory](<./design/architecture/data/service-inventory.json>)
- [Hardware Inventory](<./design/architecture/data/hardware-inventory.json>)
- [Network Topology](<./design/architecture/data/network-topology.json>)
- [Credential Manifest](<./design/architecture/data/credential-manifest.json>)
- [Data Flows](<./design/architecture/data/data-flows.json>)
- [Capabilities Schema](<./design/architecture/data/capabilities-schema.json>)
- [Catalog Schema](<./design/architecture/data/catalog-schema.json>)
- [Mutation Surfaces](<./design/architecture/data/mutation-surfaces.json>) — Layer 1.5 governance: enumeration of all mutation surfaces (file edits, GitHub API, git push, shell exec, etc.) available to Felix agents, with per-surface risk tier and approval requirements
- [Change Risk Taxonomy](<./design/architecture/data/change-risk-taxonomy.json>)
- [Doc Domain Map](<./design/architecture/data/doc-domain-map.json>)
- [LLM Spend Baseline](<./design/architecture/data/llm-spend-baseline.json>) — monthly LLM cost across all services (authoritative; see narrative companion in parent dir)
- [Audited Surfaces](<./design/architecture/data/audited-surfaces.json>) — repo paths whose changes affect office2 security-monitor baselines; consumed by `.github/workflows/audited-surface-reminder.yml` and the spec-kitty charter rebaseline obligation (#557)

### docs/design/architecture/baselines/ — Pre/post-change measurement baselines

Numerators/denominators captured before and after material architectural changes; referenced by spec-level NFR acceptance gates.

- [Baselines Index & Methodology](<./design/architecture/baselines/README.md>) — how baselines are captured, retained, and compared (includes the felix-doc-auditor pre-rework snapshot)

---

## Operational Runbooks (docs/runbooks/)

### Configuration Integrity Sweeps (topical view)

Two periodic sweeps verify that office2's configuration is in the state we expect; together they cover system-level drift and credential-level drift, and any new sweep should be added to this group. Both runbooks are also listed under *Agent-executable* below.

- [Security Baseline Operations](<./runbooks/security-baseline-ops.md>) — daily 3 AM audit comparing the live system (pip / brew packages, Docker images, listening ports, systemd units, SSH keys, crontabs, OpenClaw cron + config) against `/data/services/security-monitor/baselines/`. Drift fires the alert log + `drift-events.jsonl`. Audited surface list at [`audited-surfaces.json`](<./design/architecture/data/audited-surfaces.json>) drives the rebaseline obligation (#557).
- [Credential Liveness Probe Operations](<./runbooks/credential-liveness-probe-ops.md>) — 6-hourly OAuth liveness probe (00, 06, 12, 18 UTC). Live API call per credential, classified as `dead-routine-7day` (re-auth cycle), `dead-unexpected` (mid-week token death — investigate before re-authing), or `probe-error`. Auto-files a GitHub issue with the recovery command in the body (#572, #616).

### Agent-executable runbooks

- [Doc Auditor Driver Operations](<./runbooks/doc-auditor-driver-ops.md>) — felix-doc-auditor **scripts-first driver** operations (post-#343): hourly systemd tick, `last-tick.json` health signal, prompt artifacts, backlog/lock recovery, pending-approval workflow, troubleshooting, baselines *(⏸ currently suspended; see runbook banner)*
- [Signal-Driven Monitoring Operations](<./runbooks/signal-driven-monitoring-ops.md>) — `felix-core-digest` signal extraction + `felix-heartbeat-gate` (Haiku-tier routing) operations: pre-cutover checklist (Restic Tier 2 precondition + identity/credential checks), 12-step cutover procedure, post-cutover verification, troubleshooting, rollback, post-rollout tuning. Mission #490.
- [Felix-Vikunja Sync Driver Operations](<./runbooks/sync-driver-ops.md>) — install, bootstrap, observe, and recover the Felix-Vikunja reconciliation driver per ADR-0003: 5-min systemd timer, 7-phase full-poll pipeline, project-layer audit (`layer_summary`), deletion cleanup (Phase 5b), URL config prerequisite (`vikunja-base-url.txt`), `conflict-events.jsonl` audit trail, three delivery guards (G-1/G-2/G-3), known soft edge for Vikunja server-side auto-advance, full SC-001..SC-009 verification commands. Missions #518/#519/#520 (Epic #507 complete).
- [Doc Auditor Operations (pre-#343 — historical)](<./runbooks/doc-auditor-ops.md>) — original openclaw-agent runbook; retained for reference until the pre-#343 implementation is fully retired
- [Security Baseline Operations](<./runbooks/security-baseline-ops.md>) — canonical baseline-reset procedure for the daily 3 AM audit; linked from service runbooks for the "how"
- [Credential Liveness Probe Operations](<./runbooks/credential-liveness-probe-ops.md>) — 6-hourly OAuth liveness probe (sister sweep to the daily security audit); cadence, classification logic, manifest config, operator response when an issue is filed (#572, #616)
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
- [OpenClaw Agent Setup](<./runbooks/openclaw-agent-setup.md>) — agent deployment + verification; now includes DM-reply lifecycle troubleshooting (#588)
- [Google Workspace Operations](<./runbooks/google-workspace-ops.md>) — `gog` CLI setup, OAuth flow, pitfalls, common commands, second-account expansion, credential liveness probe auto-detection (#100, ADR-0001, #572)
- [Phone Termius Setup & Recovery](<./runbooks/phone-termius-setup.md>) — iPhone Termius SSH setup (kgale + claude hosts), new-phone enrollment, post-key-rotation recovery, Tailscale SSH ACL gotchas (#575, ADR-0004)
- [Local Test Gate (pre-push hook)](<./runbooks/local-test-gate.md>) — `.githooks/pre-push` runs `make test` before `git push`; one-time `git config core.hooksPath .githooks` setup; bypass policy (#571)
- [Smoke checklist — felix-admin-calendar extraction (#579)](<./runbooks/felix-calendar-subagent-extraction-01KTTA33-smoke.md>) — operator-driven post-deploy verification for the felix-calendar-subagent-extraction mission: DM round-trips per subagent, doc-auditor `last-tick.json` freshness, 24h observation window for scheduled outbound flows, decision criteria

### Human and mixed-audience runbooks

- [Agent Workspace Reconciliation](<./runbooks/agent-workspace-reconciliation.md>) — drift enforcement, factory-default lifecycle, last-author-wins strategy
- [Deploy Discipline (canonical)](<./runbooks/deploy/discipline.md>) — manifest-driven deploys to office2 via the felix-deployer applier; entrypoint shape, tier policy, verification commands, failure handling, rebaseline obligation
- [Deployment Runbook](<./runbooks/deployment.md>) — historical stub; redirects to the discipline runbook above. Preserved as a stable URL for older docs / ADRs / issues that link here
- [Felix Governance](<./runbooks/felix-governance.md>) — agent registration, promotion, demotion, violation handling
- [felix-bot Vikunja Provisioning](<./runbooks/felix-bot-vikunja-provisioning.md>) — operator runbook for provisioning, rotating, and revoking the kg-felix-bot Vikunja API credential
- [Credential Rotation Operations](<./runbooks/credential-rotation-ops.md>) — operator runbook for manually rotating each credential in the manifest with a manual rotation path (8 procedures + pre-flight + manifest-update obligations)
- [Vault Path Registry Migration](<./runbooks/vault-path-registry-migration.md>) — reusable playbook for migrating vault folder names through the registry (how-to guide; first executed by mission 026 / #152)
- [Repository Governance](<./runbooks/repo-governance.md>) — git workflow, labels, milestones, issue management
- [GitHub Issues Workflow](<./runbooks/github-issues-workflow.md>) — issue lifecycle, templates, triage, project board
- [Observation Intelligence Ops](<./runbooks/observation-ops.md>)
- [Obsidian Setup Guide](<./runbooks/obsidian-setup.md>)
- [Obsidian Vault](<./runbooks/obsidian.md>)
- [WhatsApp Channel Operations](<./runbooks/whatsapp-ops.md>)

### Deprecated runbooks (retained in place)

- [Spec-Kitty Bug Reporting](<./runbooks/spec-kitty-bug-reporting.md>) — dual-track workflow for filing tooling bugs: internal kg-automation issue tracks status, slim external paste doc goes upstream
- [Spec-Kitty Install Guide](<./runbooks/spec-kitty-init-in-existing-repo.md>) — historical, setup already complete

### Non-runbook content in runbooks/

- [Templater Commands (Canon v2)](<./runbooks/templater-commands.md>) — command reference

---

## Design & Standards

### docs/design/ — Vision and rationale

- [Felix System Overview](<./design/README.md>) — **start here for new contributors.** Day-1 orientation: what Felix is, what it does for Kent, how he interacts with it, key flows, components, and architectural principles. 5 high-level mermaid diagrams.
- [Felix Capability Roadmap](<./design/felix-capability-roadmap.md>) — living capability status, feature sequence, and design principles
- [OpenClaw Workspace Authoring Standard](<./design/openclaw-workspace-authoring-standard.md>) — file-ownership contract (SOUL/USER/TOOLS/IDENTITY/AGENTS) + shared-invariant rules every agent workspace is authored against; validated by `scripts/openclaw/agents/validate_workspace.py` (#587)
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

## Feature Specifications (docs/archive/func-spec/)

Historical archive. Features F001-F020 are documented here as the
historical record. New features are tracked as GitHub Issues — see
[GitHub Issues Workflow](<./runbooks/github-issues-workflow.md>).

Templates:

- [Feature Specification Template](<./archive/func-spec/_TEMPLATE_spec_kitty_input.md>)
- [Research Mission Template](<./archive/func-spec/_TEMPLATE_spec_kitty_research_input.md>)
- [Docs Debt Issue Template](<../.github/ISSUE_TEMPLATE/docs-debt.md>)
- [Research Issue Template](<../.github/ISSUE_TEMPLATE/research.md>)

---

## Diagnostics (docs/diagnostics/)

Active troubleshooting and upstream bug reporting.

- [Spec-Kitty Workflow Journal](<./diagnostics/spec-kitty-workflow-journal.md>) — running observations log; promote stabilized entries to internal kg-automation issues per the bug-reporting runbook
- [Spec-Kitty External Bug Report Template](<./diagnostics/spec-kitty-bug-report-external-template.md>) — slim template for upstream submission; source for transient paste docs at `{slug}-external.md`
- [Spec-Kitty Bug Report Template (deprecated)](<./diagnostics/spec-kitty-bug-report-template.md>) — original combined internal+external template; superseded 2026-05-28 by the dual-track workflow (internal issue template at `.github/ISSUE_TEMPLATE/spec-kitty-bug.md` + external template above); retained as reference during the migration window

---

## Archive (docs/archive/)

Frozen historical artifacts. Not maintained. Excluded from this index.

---

## Adding a New Document

1. Identify the Divio type per [Divio Classification Standard](<./design/standards/divio-classification.md>).
2. Place the file in the canonical home for that type.
3. Add frontmatter (`title`, `doc_type`, `status` minimum; `audience` required for runbooks).
4. **Update this INDEX.md** in the same change.
