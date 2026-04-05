# F015 Phase 0 Research: Divio Classification Audit & Gap Analysis

**Feature**: 015-documentation-architecture-rationalization
**Phase**: 0 (Research — gap-filling iteration mode)
**Date**: 2026-04-04
**Method**: File-system audit of `docs/**` (excluding `archive/`, `.obsidian/`, `_templater-scripts/`), frontmatter extraction, Divio classification against internal-audience mapping (C-007), grep-based reference audit.

---

## 1. Document Inventory Table

One row per active document under `docs/`. Divio types per C-007: how-to = `runbook`; reference = architecture/CLAUDE.md/service inventories (narrative); explanation = constitution/ADRs/postmortems/design principles; tutorials absent by design. Sub-types: `spec` (func-spec), `diagnostic`, `postmortem`, `standard`, `readme`.

| Path | Current `doc_type` | Title | Proposed Divio Type | Notes |
|---|---|---|---|---|
| docs/constitution/AGENT-REGISTRY.md | reference | Felix Agent Registry | reference | Registry of agent autonomy levels + transitions. Correct. |
| docs/constitution/FELIX-CONSTITUTION.md | reference | Felix Constitution | reference | Governance + operational rules. Correct. |
| docs/constitution/agent-registry.json | (none) | Agent Registry (JSON) | reference | Machine-readable registry. Exempt from moves (C-001). |
| docs/design/Vikunja.md | note | Vikunja Integration Improvements | explanation | Open-ended design rationale/notes. Misclassified. |
| docs/design/adversarial-analysis.md | strategy | Adversarial Analysis: Personal AI C&A System | explanation | Security/resilience rationale. Misclassified. |
| docs/design/decision-log.md | reference | Decision Log | reference | Append-only log (mostly template). Correct. |
| docs/design/felix-capability-roadmap.md | strategy | Felix — Capability Roadmap & Strategy | reference | Living capability status. Misclassified. |
| docs/design/personal-ai-system-spec-v03.md | strategy | Personal AI C&A System — v0.3 | reference | Superseded by v1.0. Misclassified + duplicate. |
| docs/design/personal-ai-system-spec-v1.0.md | strategy | Felix — Personal AI OS: Architecture v1.0 | reference | Current authoritative spec. Misclassified. |
| docs/design/project-charter.md | reference | Project Charter (Template) | reference | Unfilled template. Correct. |
| docs/design/risk-register.md | reference | Risk Register | reference | Risk inventory. Correct. |
| docs/design/strategic-acceleration-charter.md | charter | Strategic Acceleration Charter | explanation | Strategic direction + rationale. Sub-type of explanation. |
| docs/design/vision-framework.md | reference | KG-Automation — Vision & Architecture | reference | Correct. |
| docs/design/architecture/README.md | index | Architecture Documentation Index | reference | Correct. |
| docs/design/architecture/backup-and-recovery.md | reference | Backup and Recovery | reference | Correct. |
| docs/design/architecture/change-control.md | reference | Change Control | reference | Correct. |
| docs/design/architecture/credentials-and-secrets.md | reference | Credentials and Secrets | reference | Correct. |
| docs/design/architecture/data-flows.md | reference | Data Flows | reference | Correct. |
| docs/design/architecture/data-flows.view.md | guide | Data Flows (Rendered Mermaid) | reference | Visual reference. `guide` acceptable. |
| docs/design/architecture/glossary.md | reference | Glossary | reference | Correct. |
| docs/design/architecture/identity-model.md | reference | Identity Model | reference | Correct. |
| docs/design/architecture/physical-topology.md | reference | Physical Topology | reference | Correct. |
| docs/design/architecture/physical-topology.view.md | guide | Physical Topology (Rendered Mermaid) | reference | Visual reference. `guide` acceptable. |
| docs/design/architecture/security-posture.md | reference | Security Posture | reference | Correct. |
| docs/design/architecture/service-inventory.md | reference | Service Inventory | reference | Correct. |
| docs/design/architecture/data/*.json (7 files) | (none) | schemas + inventories | reference | Machine-readable. Exempt from moves (C-001). |
| docs/design/research/005-*/agent-team-architecture.md | (none) | Agent Team Architecture | explanation | F005 research output. Needs frontmatter. |
| docs/design/research/005-*/data-architecture.md | (none) | Data, Privacy, Identity Research | explanation | F005 research. Needs frontmatter. |
| docs/design/research/005-*/data-privacy-identity.md | (none) | (duplicate-like title) | explanation | Check for true duplicate. Needs frontmatter. |
| docs/design/research/005-*/integration-map.md | (none) | Integration Map | reference | System inventory. Needs frontmatter. |
| docs/design/research/005-*/integration-needs.md | (none) | Integration and Tool Research | explanation | F005 research. Needs frontmatter. |
| docs/design/research/005-*/local-audit.md | (none) | Local Architecture Audit | reference | Audit findings. Needs frontmatter. |
| docs/design/research/005-*/openclaw-capabilities.md | (none) | OpenClaw Capability Research | explanation | F005 research. Needs frontmatter. |
| docs/design/research/005-*/roadmap.md | (none) | Feature and Capability Roadmap | reference | Roadmap inventory. Needs frontmatter. |
| docs/design/research/005-*/user-story-catalog.md | (none) | User Story Catalog | reference | Stories + priority matrix. Needs frontmatter. |
| docs/design/standards/doc-standards.md | policy | kg-automation Documentation Standards (Canon v3) | standard | Authoring standards. Treat `policy` as sub-type of `standard`. |
| docs/design/standards/obsidian-linter-alignment.md | reference | Obsidian Linter Alignment | standard | Cross-cutting linter policy. Misclassified. |
| docs/design/standards/standards-readme.md | readme | Documentation Standards | reference | Nav doc. Correct. |
| docs/design/standards/*.json (3 files) | (none) | allowed-values, frontmatter.schema, validator-policy | reference | Machine-readable. Exempt from moves (C-001). |
| docs/docs-readme.md | readme | Visual Docs Index | reference | Current index (to be replaced by INDEX.md). Correct. |
| docs/func-spec/F001–F016 + FUTURE (18 files) | func-spec | Feature specs | spec | Correct. |
| docs/func-spec/_TEMPLATE_spec_kitty_input.md | reference | TEMPLATE | reference | Correct. |
| docs/func-spec/claude-pre-implementation-prompt.md | reference | Claude Pre-Implementation Prompt | reference | Standing orchestration directive. Correct. |
| docs/issues/diagnostics/f012-merge-breadcrumbs.md | (none) | (no frontmatter) | diagnostic | Needs frontmatter. |
| docs/issues/diagnostics/spec-kitty-feedback/*.md (5 files) | (none) | (no frontmatter) | diagnostic | Needs frontmatter. |
| docs/issues/diagnostics/spec-kitty-workflow-journal.md | diagnostic | Spec-Kitty Workflow Journal | diagnostic | Correct. |
| docs/runbooks/agent-execution-roles.md | handbook | Execution Roles — Runner vs Claude Code | runbook | Misclassified. |
| docs/runbooks/agent-handbook.md | handbook | Agent Handbook — Pre-PR Checklist | runbook | Misclassified. |
| docs/runbooks/ci-handbook.md | handbook | CI Handbook — Docs & Handoffs | runbook | Misclassified. |
| docs/runbooks/claude-code.md | handbook | Claude Code — Execution Agent | runbook | Misclassified. |
| docs/runbooks/deployment.md | handbook | Deployment Runbook | runbook | Misclassified (title already says "Runbook"). |
| docs/runbooks/f001-acceptance-results.md | reference | F001 Vikunja Deploy — Acceptance Results | reference | Correct. |
| docs/runbooks/f002-acceptance-results.md | reference | F002 OpenClaw Install — Acceptance Results | reference | Correct. |
| docs/runbooks/felix-governance.md | handbook | Felix Governance Runbook | runbook | Misclassified. |
| docs/runbooks/goals-ops.md | handbook | Goals Operations Runbook | runbook | Misclassified. |
| docs/runbooks/habits-ops.md | handbook | Habit Check-in Operations Runbook | runbook | Misclassified. |
| docs/runbooks/inbox-ops.md | handbook | Inbox Processing Operations Runbook | runbook | Misclassified. |
| docs/runbooks/maintenance.md | handbook | Maintenance & Housekeeping | runbook | Misclassified. |
| docs/runbooks/observation-ops.md | handbook | Observation Intelligence Layer — Ops Runbook | runbook | Misclassified. |
| docs/runbooks/obsidian-setup.md | handbook | Obsidian Setup Guide | runbook | Misclassified. |
| docs/runbooks/obsidian-sync-ops.md | handbook | Obsidian Sync Operations Runbook | runbook | Misclassified. |
| docs/runbooks/obsidian.md | handbook | Obsidian Vault | runbook | Mixed (setup + config reference); dominant = runbook. |
| docs/runbooks/office2-backup-and-security.md | handbook | office2 — Backup Strategy, Config & Security | explanation | Strategy/rationale, not prescriptive. Misclassified. |
| docs/runbooks/openclaw-ops.md | handbook | OpenClaw Operations Runbook | runbook | Misclassified. |
| docs/runbooks/repo-governance.md | policy | Repository Governance — Branch Protection & PR | standard | Cross-cutting git policy. `policy` as `standard` sub-type. |
| docs/runbooks/spec-kitty-init-in-existing-repo.md | handbook | Spec-Kitty Install Guide | runbook | Misclassified. |
| docs/runbooks/task-intelligence-ops.md | handbook | Task Intelligence Operations | runbook | Misclassified. |
| docs/runbooks/templater-commands.md | handbook | Templater Commands (Canon v2) | reference | Templater command list. Misclassified. |
| docs/runbooks/transcribe-ops.md | handbook | Transcribe API Operations Runbook | runbook | Misclassified. |
| docs/runbooks/vikunja-ops.md | handbook | Vikunja Operations Runbook | runbook | Misclassified. |
| docs/runbooks/visual-docs-style.md | handbook | Visual Documentation Style Guide | standard | Cross-cutting style standard. Misclassified. |
| docs/runbooks/whatsapp-ops.md | handbook | WhatsApp Channel Operations Runbook | runbook | Misclassified. |
| docs/_templates/** | (various) | Obsidian templates + Templater scripts | reference | Auxiliary templates. Correct as reference. |

---

## 2. Misclassifications

26 documents have a `doc_type` that does not match the proposed Divio classification.

| Path | Current | Proposed | Justification |
|---|---|---|---|
| docs/design/Vikunja.md | note | explanation | Design rationale / open questions. |
| docs/design/adversarial-analysis.md | strategy | explanation | Security rationale, not strategic direction. |
| docs/design/felix-capability-roadmap.md | strategy | reference | Describes current capability state. |
| docs/design/personal-ai-system-spec-v03.md | strategy | reference (+ deprecate) | System spec reference; superseded by v1.0. |
| docs/design/personal-ai-system-spec-v1.0.md | strategy | reference | Authoritative system spec. |
| docs/design/strategic-acceleration-charter.md | charter | explanation | Strategic rationale; `charter` as `explanation` sub-type. |
| docs/design/standards/obsidian-linter-alignment.md | reference | standard | Cross-cutting linter policy. |
| docs/runbooks/agent-execution-roles.md | handbook | runbook | Prescriptive how-to. |
| docs/runbooks/agent-handbook.md | handbook | runbook | Prescriptive checklist. |
| docs/runbooks/ci-handbook.md | handbook | runbook | Prescriptive CI procedures. |
| docs/runbooks/claude-code.md | handbook | runbook | Prescriptive Claude Code ops. |
| docs/runbooks/deployment.md | handbook | runbook | Prescriptive deployment (title already says "Runbook"). |
| docs/runbooks/felix-governance.md | handbook | runbook | Prescriptive governance procedures. |
| docs/runbooks/goals-ops.md | handbook | runbook | Prescriptive goal ops. |
| docs/runbooks/habits-ops.md | handbook | runbook | Prescriptive habit ops. |
| docs/runbooks/inbox-ops.md | handbook | runbook | Prescriptive inbox ops. |
| docs/runbooks/maintenance.md | handbook | runbook | Prescriptive maintenance tasks. |
| docs/runbooks/observation-ops.md | handbook | runbook | Prescriptive observation ops. |
| docs/runbooks/obsidian-setup.md | handbook | runbook | Prescriptive setup steps. |
| docs/runbooks/obsidian-sync-ops.md | handbook | runbook | Prescriptive sync ops. |
| docs/runbooks/obsidian.md | handbook | runbook | Dominant type = how-to. |
| docs/runbooks/office2-backup-and-security.md | handbook | explanation | Strategy + rationale, not procedural. |
| docs/runbooks/openclaw-ops.md | handbook | runbook | Prescriptive OpenClaw ops. |
| docs/runbooks/spec-kitty-init-in-existing-repo.md | handbook | runbook | Prescriptive install steps. |
| docs/runbooks/task-intelligence-ops.md | handbook | runbook | Prescriptive task-intel ops. |
| docs/runbooks/templater-commands.md | handbook | reference | Command list, not procedure. |
| docs/runbooks/transcribe-ops.md | handbook | runbook | Prescriptive transcribe ops. |
| docs/runbooks/vikunja-ops.md | handbook | runbook | Prescriptive Vikunja ops. |
| docs/runbooks/visual-docs-style.md | handbook | standard | Cross-cutting style standard. |
| docs/runbooks/whatsapp-ops.md | handbook | runbook | Prescriptive WhatsApp ops. |

**Summary**: 20 × `handbook → runbook`, 4 × strategy/note → explanation/reference, 2 × handbook/reference → standard, 1 × handbook → explanation, 1 × handbook → reference. Plus: `personal-ai-system-spec-v03.md` should also be flagged as deprecated/superseded.

---

## 3. Directory-Level Observations

### `docs/constitution/`
All `reference`; clean. Correctly classified.

### `docs/design/` (top-level)
Mix of `reference`, `explanation`, `strategy` (misused), and one `note`. Strategic/roadmap docs misclassified as `strategy` should be `reference` (living capability state) or `explanation` (rationale).

### `docs/design/architecture/`
Exclusively `reference` (11 markdown + 7 JSON). Clean, consistent, exempt from moves (C-001).

### `docs/design/research/005-*/`
Mix of `explanation` (research rationale) and `reference` (inventories). All 9 files lack `doc_type` frontmatter — needs bulk add.

### `docs/design/standards/`
Cross-cutting standards, but 2 of 3 markdown files mislabeled (`policy`/`reference` should be `standard`).

### `docs/func-spec/`
Clean; all `spec` (func-spec sub-type). Templates correctly labeled `reference`.

### `docs/issues/diagnostics/`
Correctly classified as `diagnostic`. 6 of 7 files lack frontmatter — needs bulk add. **Exempt from restructuring (C-002).**

### `docs/issues/postmortems/`
Empty (`.gitkeep` only). Ready for F016.

### `docs/runbooks/`
Largest concentration of misclassifications: 20 × `handbook` → `runbook`, plus scattered misclassifications. The legacy `handbook` value dominates.

### `docs/_templates/`
Obsidian templates + Templater scripts. All correctly classified as `reference` (auxiliary templates). Most lack frontmatter (acceptable for Templater scripts).

---

## 4. Duplicate Coverage

Only one true duplicate:

| Topic | Files | Resolution |
|---|---|---|
| System specification | `docs/design/personal-ai-system-spec-v03.md`, `docs/design/personal-ai-system-spec-v1.0.md` | v1.0 supersedes v03. Archive v03 or mark `deprecated: true`. |

Other apparent duplicates are **complementary**, not duplicative:
- Narrative `.md` + Mermaid `.view.md` + machine-readable `.json` for data-flows, physical-topology, service-inventory, agent-registry — these serve different audiences and formats.
- `obsidian.md` (config reference) + `obsidian-sync-ops.md` (operational procedures) — complementary.
- `F005_system_architecture_review.md` (spec) + `docs/design/research/005-*/local-audit.md` (research output) — plan vs. deliverable.

---

## 5. Gaps by Divio Type

1. **Explanation (design rationale)** — thin. Most existing rationale docs are misclassified as `strategy` or `handbook`. No consolidated rationale directory.
2. **Postmortem** — `docs/issues/postmortems/` is empty. Populated by F016.
3. **Runbook clarity** — prescriptive docs uniformly labeled `handbook`; Divio distinction not enforced.
4. **Reference (living status)** — no explicit sub-type for living docs like `felix-capability-roadmap.md` or acceptance-results files.
5. **Diagnostic outside issues** — runbooks lack troubleshooting sections; only `docs/issues/diagnostics/` contains diagnostic docs.

---

## 6. Reference Audit Map

Inbound references to `docs/runbooks/*` found across: `CLAUDE.md`, `docs/func-spec/`, `ai-agents/`, `.claude/`, `kitty-specs/`, `scripts/`, and cross-references within `docs/`.

| Source | Target |
|---|---|
| docs/design/architecture/service-inventory.md | docs/runbooks/vikunja-ops.md |
| docs/design/architecture/service-inventory.md | docs/runbooks/goals-ops.md |
| docs/design/architecture/service-inventory.md | docs/runbooks/transcribe-ops.md |
| docs/design/architecture/service-inventory.md | docs/runbooks/openclaw-ops.md |
| docs/design/architecture/service-inventory.md | docs/runbooks/inbox-ops.md |
| docs/design/architecture/service-inventory.md | docs/runbooks/habits-ops.md |
| docs/design/architecture/service-inventory.md | docs/runbooks/observation-ops.md |
| docs/design/architecture/service-inventory.md | docs/runbooks/whatsapp-ops.md |
| docs/design/research/005-*/local-audit.md | docs/runbooks/vikunja-ops.md |
| docs/design/research/005-*/local-audit.md | docs/runbooks/openclaw-ops.md |
| docs/design/research/005-*/local-audit.md | docs/runbooks/transcribe-ops.md |
| docs/design/research/005-*/local-audit.md | docs/runbooks/whatsapp-ops.md |
| docs/design/research/005-*/local-audit.md | docs/runbooks/obsidian-sync-ops.md |
| docs/design/research/005-*/local-audit.md | docs/runbooks/office2-backup-and-security.md |
| docs/runbooks/task-intelligence-ops.md | docs/runbooks/vikunja-ops.md |
| docs/runbooks/deployment.md | docs/design/architecture/change-control.md |
| docs/runbooks/obsidian-sync-ops.md | docs/design/architecture/service-inventory.md |
| docs/runbooks/whatsapp-ops.md | docs/design/architecture/security-posture.md |
| ai-agents/claude-code-instructions.md | docs/design/architecture/change-control.md |
| CLAUDE.md | docs/design/personal-ai-system-spec-v03.md (outdated → should reference v1.0) |
| CLAUDE.md | docs/design/architecture/ (directory) |
| CLAUDE.md | docs/design/architecture/change-control.md |
| CLAUDE.md | docs/func-spec/ (directory) |

**Important finding**: `CLAUDE.md` currently references `personal-ai-system-spec-v03.md` (superseded by v1.0). This reference should be updated as part of F015.

**Finding**: The bulk of inbound runbook references are from `docs/design/architecture/service-inventory.md`. If any runbook files are moved or renamed, service-inventory.md is the primary reference-update target.

---

## 7. Agent-Executable Runbook Candidates

Runbooks whose procedures are mechanical enough to convert to agent skills (FR-005 flagging):

| Runbook | Candidate Steps | Priority |
|---|---|---|
| vikunja-ops.md | health-check, systemctl restart, restic backup verify | Medium |
| openclaw-ops.md | systemctl status/restart, agent list (JSON parse), log tail | Medium |
| obsidian-sync-ops.md | systemctl status/restart, sync-completion timestamp check | Medium |
| transcribe-ops.md | HTTP health check, endpoint test, log tail | Low |
| office2-backup-and-security.md | restic snapshot list, baseline drift diff | Low |
| inbox-ops.md | agent trigger (OpenClaw exec), log tail, vault timestamp check | High |
| goals-ops.md | Vikunja API CRUD on goal tasks | High |
| habits-ops.md | agent trigger, Vikunja API task comment update | High |

**High-priority candidate skills** (informational for future work; NOT scoped into F015):
- `vikunja-service-health`
- `obsidian-sync-health`
- `inbox-process-trigger`
- `goal-ops`
- `habit-check-trigger`

**Keep human-executable** (policy/judgement content): `felix-governance.md`, `spec-kitty-init-in-existing-repo.md`, `ci-handbook.md` sections involving PR review.

---

## 8. Summary Stats

| Metric | Count |
|---|---|
| Total docs inventoried | ~102 |
| Docs with `doc_type` frontmatter | ~72 (71%) |
| Docs without frontmatter | ~30 (research + diagnostics + JSON + templates) |
| Misclassifications (frontmatter fixes needed) | 26 (+1 deprecation flag) |
| True duplicates | 1 (personal-ai-system-spec v03/v1.0) |
| Gaps identified | 5 |
| Files exempt from restructuring (C-001, C-002) | ~30 |
| Agent-executable runbook candidates | 8 |

Proposed-type breakdown (after corrections):

| Divio Type | Count | Examples |
|---|---|---|
| reference | ~45 | architecture/*, data/*.json, templates, acceptance-results, docs-readme |
| runbook | ~25 | runbooks/*-ops.md, runbooks/*-handbook.md (post-rename) |
| spec | ~18 | func-spec/F001–F016, FUTURE |
| explanation | ~8 | adversarial-analysis, office2-backup-and-security, strategic-acceleration-charter, Vikunja.md, research/*research*.md |
| diagnostic | ~7 | issues/diagnostics/**, spec-kitty-workflow-journal |
| standard | ~4 | doc-standards, visual-docs-style, obsidian-linter-alignment, repo-governance |
| readme | ~2 | docs-readme, standards-readme |

---

## 9. Key Findings & Recommendations

### Findings

1. **Core architecture documentation is excellent.** `docs/design/architecture/` is the cleanest area — all `reference`, consistent, well-structured. No changes recommended here.
2. **Primary issue is `handbook` → `runbook` rename.** 20 runbook files use the legacy `handbook` value. Divio distinction not currently enforced.
3. **Design rationale is under-labeled.** Strategy docs and security/backup rationale docs are misclassified as `strategy` or `handbook`.
4. **Research directory needs frontmatter.** 9 files in `docs/design/research/005-*/` lack `doc_type`.
5. **Diagnostic files need frontmatter.** 6 files in `docs/issues/diagnostics/spec-kitty-feedback/` lack frontmatter.
6. **One true duplicate.** `personal-ai-system-spec-v03.md` is superseded by v1.0; CLAUDE.md still references v03.
7. **No content moves are strictly required.** All frontmatter corrections can be made in-place. A few files (`office2-backup-and-security.md` → design rationale area) are candidates for future optional moves.

### Recommendations for F015 Phase 1 / Tasks

1. **Frontmatter corrections in place** — no moves required to complete FR-003, FR-004.
2. **Bulk frontmatter add** — 9 research files + 6 diagnostic files + JSON files if desired.
3. **CLAUDE.md reference update** — change `personal-ai-system-spec-v03.md` → `personal-ai-system-spec-v1.0.md`.
4. **Archive/deprecate** `personal-ai-system-spec-v03.md`.
5. **Move** `office2-backup-and-security.md` out of runbooks to a rationale-appropriate home (optional; scope for task planning).
6. **INDEX.md authoring** covers all ~102 docs with Divio-type groupings.
7. **Do NOT restructure** `docs/design/architecture/data/*` (C-001), `docs/issues/diagnostics/*` (C-002), `docs/func-spec/*` (clean).

### For INDEX.md grouping strategy (see data-model.md)

INDEX.md should group by **directory + Divio type** rather than pure Divio type, to preserve the existing mental model (constitution, design, runbooks, issues, func-spec) while surfacing Divio types inside each group.
