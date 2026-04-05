---
work_package_id: WP07
title: Create docs/INDEX.md Master Map
dependencies:
- WP01
- WP02
- WP03
- WP04
- WP05
- WP06
requirement_refs:
- FR-008
- NFR-001
- NFR-004
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
base_branch: 015-documentation-architecture-rationalization-WP07-merge-base
base_commit: 74a9f66ec428ce926ed3767b6b4f348b31855e18
created_at: '2026-04-05T04:21:39.591219+00:00'
subtasks:
- T025
- T026
- T027
- T028
- T029
- T030
- T031
phase: Phase 2 - Master Index
assignee: ''
agent: "claude"
shell_pid: "5374"
history:
- at: '2026-04-05T01:28:56Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: docs/INDEX.md
execution_mode: code_change
owned_files:
- docs/INDEX.md
---

# Work Package Prompt: WP07 — Create docs/INDEX.md Master Map

## Branch Strategy

- **Planning/base branch at prompt creation**: `main`
- **Final merge target for completed work**: `main`
- **Actual worktree base may differ later**: base = main or stacked on WP01-WP06.
- **If human instructions contradict these fields**: stop and resolve the intended landing branch before coding.

---

## Objectives & Success Criteria

Author `docs/INDEX.md` as the master documentation map covering every active directory, its purpose, the Divio types it contains, and its key documents. This file replaces `docs/docs-readme.md` as the canonical index.

**Success criteria**:

- [ ] `docs/INDEX.md` exists with correct frontmatter (`doc_type: reference`, `status: approved`).
- [ ] Lists every active directory under `docs/` (constitution, design, design/architecture, design/architecture/data, design/standards, design/research, docs/runbooks, docs/runbooks/governance, docs/postmortems, docs/issues/diagnostics, docs/issues/postmortems, docs/func-spec).
- [ ] Names at least one key document per directory.
- [ ] Each document entry shows its `doc_type` and (if runbook) `audience`.
- [ ] Every active document is reachable in ≤3 link hops from CLAUDE.md via INDEX.md.
- [ ] INDEX.md acknowledges `CLAUDE.md` as the parent entry point.

## Context & Constraints

This WP is the **primary deliverable** of F015. Quality of INDEX.md determines whether chain-of-reference is solved.

**Grouping strategy per data-model.md §8**: group by directory context (preserving mental model) with Divio-type annotations. NOT pure Divio grouping.

**Constraints**:

- Manual authoring only; no automated generator (per C-006).
- Must link to files, not directories-only — every directory section lists key files.
- Must include machine-readable artifacts (JSON files in `docs/design/architecture/data/` and `docs/design/standards/`).
- ~200 active markdown + ~20 JSON files to cover.

**Reference documents**:

- `kitty-specs/015-documentation-architecture-rationalization/research.md` §1 (full inventory)
- `kitty-specs/015-documentation-architecture-rationalization/data-model.md` §8 (grouping strategy)
- `docs/design/architecture/README.md` (pattern to follow for architecture section)

## Subtasks & Detailed Guidance

### Subtask T025 — Create INDEX.md with frontmatter and overview

- **Purpose**: File skeleton with purpose statement and usage guidance.
- **Steps**:
  1. Create `docs/INDEX.md` with frontmatter:

     ```yaml
     ---
     title: kg-automation Documentation Index
     doc_type: reference
     status: approved
     owners: [kgale]
     last_validated: 2026-04-05
     version: "1.0"
     ---
     ```

  2. Add H1 "kg-automation Documentation Index".
  3. Add intro paragraph explaining:
     - This is the master map for all active documentation.
     - Referenced from `CLAUDE.md` as the starting point.
     - Grouped by directory context with Divio type annotations.
     - Uses the classification defined in `docs/design/standards/divio-classification.md`.
  4. Add a "How to use" subsection: agents read CLAUDE.md → follow link here → navigate to needed doc.
- **Files**: `docs/INDEX.md` (new, ~30 lines for this subtask).
- **Parallel?**: No — blocks T026-T030.
- **Notes**: Keep overview concise (under 200 words).

### Subtask T026 — Constitution + Governance section

- **Purpose**: Link Felix constitution, agent registry, and governance runbooks.
- **Steps**: Add section "## Constitution & Governance" with entries for:

  ```markdown
  ### docs/constitution/ — Governance authority

  - [Felix Constitution](constitution/FELIX-CONSTITUTION.md) — `reference` — top-level governance, autonomy levels, principles
  - [Agent Registry (narrative)](constitution/AGENT-REGISTRY.md) — `reference` — current agent state, autonomy
  - [Agent Registry (JSON)](constitution/agent-registry.json) — `reference` (machine-readable)

  ### docs/runbooks/governance/ — Governance operations

  - (Empty — populated by F016)
  ```

- **Files**: `docs/INDEX.md` (append ~20 lines).
- **Parallel?**: Yes — after T025.

### Subtask T027 — System Architecture section

- **Purpose**: Link architecture docs + data/ machine-readable artifacts.
- **Steps**: Add section "## System Architecture" covering:

  ```markdown
  ### docs/design/architecture/ — Current-state system reference

  All `reference`. Describes deployed services, topology, credentials, data flows.

  - [README](design/architecture/README.md) — architecture suite index
  - [Service Inventory](design/architecture/service-inventory.md) — running services, ports, systemd
  - [Data Flows](design/architecture/data-flows.md) + [Mermaid view](design/architecture/data-flows.view.md)
  - [Physical Topology](design/architecture/physical-topology.md) + [Mermaid view](design/architecture/physical-topology.view.md)
  - [Credentials & Secrets](design/architecture/credentials-and-secrets.md)
  - [Identity Model](design/architecture/identity-model.md)
  - [Security Posture](design/architecture/security-posture.md)
  - [Backup & Recovery](design/architecture/backup-and-recovery.md)
  - [Change Control Protocol](design/architecture/change-control.md)
  - [Glossary](design/architecture/glossary.md)

  ### docs/design/architecture/data/ — Canonical machine-readable home

  All `reference`. Authoritative operational state (JSON) + schemas. **Exempt from moves (C-001)**.

  - [Service Inventory (JSON)](design/architecture/data/service-inventory.json)
  - [Hardware Inventory (JSON)](design/architecture/data/hardware-inventory.json)
  - [Network Topology (JSON)](design/architecture/data/network-topology.json)
  - [Credential Manifest (JSON)](design/architecture/data/credential-manifest.json)
  - [Data Flows (JSON)](design/architecture/data/data-flows.json)
  - [Capabilities Schema (JSON)](design/architecture/data/capabilities-schema.json)
  - [Catalog Schema (JSON)](design/architecture/data/catalog-schema.json)
  ```

- **Files**: `docs/INDEX.md` (append ~40 lines).
- **Parallel?**: Yes — after T025.

### Subtask T028 — Operational Runbooks section

- **Purpose**: Link all runbooks, grouped by audience.
- **Steps**: Add section "## Operational Runbooks" with subsections:

  ```markdown
  ### docs/runbooks/ — How-to procedures

  All `runbook`. Prescriptive step-by-step operations.

  **Agent-executable (candidates for skill conversion)**:

  - [Vikunja Operations](runbooks/vikunja-ops.md) — `runbook` `agent-executable`
  - [OpenClaw Operations](runbooks/openclaw-ops.md) — `runbook` `agent-executable`
  - [Obsidian Sync Operations](runbooks/obsidian-sync-ops.md) — `runbook` `agent-executable`
  - [Transcribe Operations](runbooks/transcribe-ops.md) — `runbook` `agent-executable`
  - [Inbox Processing](runbooks/inbox-ops.md) — `runbook` `agent-executable`
  - [Goals Operations](runbooks/goals-ops.md) — `runbook` `agent-executable`
  - [Habits Operations](runbooks/habits-ops.md) — `runbook` `agent-executable`
  - [Task Intelligence](runbooks/task-intelligence-ops.md) — `runbook` `agent-executable`

  **Human-executable (judgement-required)**:

  - [Felix Governance](runbooks/felix-governance.md) — `runbook` `human-only`
  - [Spec-Kitty Init](runbooks/spec-kitty-init-in-existing-repo.md) — `runbook` `human-only`
  - [CI Handbook](runbooks/ci-handbook.md) — `runbook` `human-only`
  - [Agent Handbook](runbooks/agent-handbook.md) — `runbook` `human-only`
  - [Agent Execution Roles](runbooks/agent-execution-roles.md) — `runbook` `human-only`
  - [Claude Code](runbooks/claude-code.md) — `runbook` `human-only`
  - [Repo Governance](runbooks/repo-governance.md) — `standard`

  **Mixed (both)**:

  - [Deployment](runbooks/deployment.md) — `runbook` `both`
  - [Observation Operations](runbooks/observation-ops.md) — `runbook` `both`
  - [Obsidian Setup](runbooks/obsidian-setup.md) — `runbook` `both`
  - [Obsidian Vault](runbooks/obsidian.md) — `runbook` `both`
  - [Maintenance](runbooks/maintenance.md) — `runbook` `both`
  - [WhatsApp Operations](runbooks/whatsapp-ops.md) — `runbook` `both`

  **Other**:

  - [Templater Commands](runbooks/templater-commands.md) — `reference`
  - [F001 Acceptance Results](runbooks/f001-acceptance-results.md) — `reference`
  - [F002 Acceptance Results](runbooks/f002-acceptance-results.md) — `reference`
  ```

- **Files**: `docs/INDEX.md` (append ~60 lines).
- **Parallel?**: Yes — after T025.
- **Notes**: Audience assignments from WP03.

### Subtask T029 — Design, Standards, Research section

- **Purpose**: Link design rationale, standards, and research outputs.
- **Steps**: Add sections for `docs/design/` top-level + `docs/design/standards/` + `docs/design/research/`:

  ```markdown
  ### docs/design/ — System vision and rationale

  - [Vision & Architecture](design/vision-framework.md) — `reference`
  - [System Spec v1.0](design/personal-ai-system-spec-v1.0.md) — `reference` (current)
  - [System Spec v0.3](design/personal-ai-system-spec-v03.md) — `reference` `status: deprecated`, superseded by v1.0
  - [Felix Capability Roadmap](design/felix-capability-roadmap.md) — `reference` (living)
  - [Strategic Acceleration Charter](design/strategic-acceleration-charter.md) — `explanation`
  - [Adversarial Analysis](design/adversarial-analysis.md) — `explanation`
  - [office2 Backup & Security](design/office2-backup-and-security.md) — `explanation`
  - [Vikunja Integration Notes](design/Vikunja.md) — `explanation`
  - [Risk Register](design/risk-register.md) — `reference`
  - [Decision Log](design/decision-log.md) — `reference`
  - [Project Charter](design/project-charter.md) — `reference` (template)

  ### docs/design/standards/ — Cross-cutting standards

  - [Documentation Standards](design/standards/doc-standards.md) — `standard`
  - [Divio Classification Standard](design/standards/divio-classification.md) — `standard` (F015)
  - [Visual Documentation Style](design/standards/visual-docs-style.md) — `standard`
  - [Obsidian Linter Alignment](design/standards/obsidian-linter-alignment.md) — `standard`
  - [Standards README](design/standards/standards-readme.md) — `reference`
  - [Frontmatter Schema (JSON)](design/standards/frontmatter.schema.json)
  - [Allowed Values (JSON)](design/standards/allowed-values.json)
  - [Validator Policy (JSON)](design/standards/validator-policy.json)

  ### docs/design/research/005-system-architecture-development/ — F005 research outputs

  9 files, mix of `explanation` (rationale) and `reference` (inventories). See [research directory](design/research/005-system-architecture-development/) for full list.
  ```

- **Files**: `docs/INDEX.md` (append ~45 lines).
- **Parallel?**: Yes — after T025.

### Subtask T030 — Func-specs, Diagnostics, Postmortems sections

- **Purpose**: Link feature specs, diagnostics, postmortems.
- **Steps**: Add sections:

  ```markdown
  ### docs/func-spec/ — Feature specifications

  All `spec`. See [directory](func-spec/) for full list (F001 through F016, FUTURE features, templates).

  ### docs/issues/diagnostics/ — Incident diagnostics

  All `diagnostic`. Active runtime issue tracking. **Exempt from restructuring (C-002)**.

  - [Spec-Kitty Workflow Journal](issues/diagnostics/spec-kitty-workflow-journal.md) — active log
  - [Spec-Kitty Feedback](issues/diagnostics/spec-kitty-feedback/) — upstream bug reports

  ### docs/issues/postmortems/ — Post-incident analysis

  All `postmortem`. Populated by F016 onwards.
  ```

- **Files**: `docs/INDEX.md` (append ~20 lines).
- **Parallel?**: Yes — after T025.

### Subtask T031 — Verify reachability in ≤3 hops

- **Purpose**: Confirm NFR-001 (every active doc reachable in ≤3 hops from CLAUDE.md).
- **Steps**:
  1. Open CLAUDE.md.
  2. Verify it references `docs/INDEX.md` (will be added in WP08).
  3. For 5 randomly selected files (one per major section), trace: CLAUDE.md → INDEX.md → section → file. Count hops ≤ 3.
  4. If any file requires more than 3 hops (e.g., through a nested section header), flag in review.
  5. Confirm ~102 active docs referenced across all sections.
- **Files**: None modified. Verification only.
- **Parallel?**: No — runs after T026-T030.
- **Notes**: This verification relies on WP08 adding the CLAUDE.md → INDEX.md link. Since WP08 depends on this WP, flag any gaps for WP08 to handle.

## Test Strategy

N/A — documentation feature, no automated tests.

**Manual validation**:

- All active directories listed.
- Every entry links to a real file (spot-check 10 random links).
- Divio type annotations present on every entry.

## Risks & Mitigations

- **Risk**: Missing a directory or key file. **Mitigation**: Use research.md §3 directory list as checklist.
- **Risk**: INDEX.md becomes too long and unreadable. **Mitigation**: Hierarchical sections; don't enumerate every file (link to directory when listing is exhaustive).
- **Risk**: Stale links if files get renamed later. **Mitigation**: WP09 makes INDEX.md maintenance mandatory in change-control protocol.

## Integration Verification

- [ ] `docs/INDEX.md` exists with valid frontmatter.
- [ ] All 13 directory sections present.
- [ ] At least one key document linked per directory.
- [ ] Each entry has `doc_type` annotation; runbooks have `audience`.
- [ ] Spot-check 10 links — all resolve to real files.
- [ ] Every active doc reachable in ≤3 hops from CLAUDE.md (verified after WP08).

## Review Guidance

- **Key checkpoints**: Coverage of all active directories. Annotations per Divio type. Links work. Not too verbose.
- **Before approving**: Click 5 random links in the rendered view; all should resolve.

## Definition of Done

- `docs/INDEX.md` committed to main with complete directory coverage.
- All ~102 active documents reachable via INDEX.md.

## Activity Log

- 2026-04-05T04:21:40Z – claude – shell_pid=4187 – Started implementation via workflow command
- 2026-04-05T04:24:16Z – claude – shell_pid=4187 – Ready for review: docs/INDEX.md created (241 lines). Covers all 12 active directories. All 7 subtasks complete. All spot-checked links resolve. NFR-001 (≤3 hop reachability from CLAUDE.md) verification partial — completes after WP08 adds CLAUDE.md→INDEX.md link.
- 2026-04-05T04:24:42Z – claude – shell_pid=5374 – Started review via workflow command
