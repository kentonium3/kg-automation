---
work_package_id: WP01
title: Domain Map & Issue Template
dependencies: []
requirement_refs:
- FR-001
- FR-002
planning_base_branch: main
merge_target_branch: main
branch_strategy: 'Current branch at workflow start: main. Planning/base branch: main. Merge target: main.'
subtasks: [T001, T002, T003]
history:
- date: '2026-04-08T19:40:49Z'
  action: created
  by: tasks-prompt
authoritative_surface: docs/design/architecture/data/
execution_mode: code_change
owned_files:
- docs/design/architecture/data/doc-domain-map.json
- .github/ISSUE_TEMPLATE/docs-debt.md
---

# WP01: Domain Map & Issue Template

## Objective

Create two foundational artifacts for the doc audit infrastructure:

1. **doc-domain-map.json** — a machine-readable mapping from each of the 8 area
   labels to the documentation files that must be verified when that domain changes.
2. **docs-debt.md** — a GitHub issue template for filing documentation gaps.

These are the static data files that the post-merge GitHub Action (WP02) will
consume, and that the future felix-doc-auditor agent (#105) will build on.

## Context

- **Area labels** (8 total): `area/infrastructure`, `area/security`,
  `area/felix-core`, `area/ea`, `area/task-intel`, `area/content`,
  `area/docs`, `area/biz-ops`
- **Architecture data home**: `docs/design/architecture/data/` — JSON files
  are the authoritative record; this directory is exempt from moves
- **Existing issue templates**: 4 templates at `.github/ISSUE_TEMPLATE/`
  (bug.md, feature.md, infra.md, rfc.md) plus config.yml
- **Spec references**: FR-001 (domain map), FR-002 (issue template)

## Branch Strategy

- **Planning base branch**: `main`
- **Merge target branch**: `main`
- **Implementation command**: `spec-kitty implement WP01`

---

## Subtask T001: Create doc-domain-map.json

**Purpose**: Create the machine-readable scope contract mapping area labels to
affected documentation. This is the single source of truth that both GitHub
Actions and the future doc-auditor agent will consume.

**File**: `docs/design/architecture/data/doc-domain-map.json`

**Schema design**:
```json
{
  "schema_version": "1.0",
  "last_updated": "2026-04-08",
  "updated_by": "#104",
  "description": "Maps area labels to documentation files requiring verification when that domain changes.",
  "domains": {
    "area/infrastructure": [...],
    "area/security": [...],
    ...
  }
}
```

Each domain key is the exact area label name. Each value is an array of relative
file paths (from repo root) of documents that must be checked when that domain
changes.

**Steps**:

1. Create the JSON file at `docs/design/architecture/data/doc-domain-map.json`
2. Include metadata fields: `schema_version` ("1.0"), `last_updated`, `updated_by` ("#104"),
   `description`
3. Populate the `domains` object with all 8 area labels as keys
4. For each area label, list the documentation files that are affected. Use the
   current docs/INDEX.md as the authoritative list of active docs.

**Domain-to-docs mapping guidance**:

- **area/infrastructure**: physical-topology.md, service-inventory.md,
  hardware-inventory.json, network-topology.json, service-inventory.json,
  backup-and-recovery.md, service-dependencies.view.md, change-control.md,
  deployment.md, pre-flight-checklist.md, post-change-verification.md
- **area/security**: security-posture.md, credentials-and-secrets.md,
  credential-manifest.json, identity-model.md, change-risk-taxonomy.json
- **area/felix-core**: FELIX-CONSTITUTION.md, AGENT-REGISTRY.md,
  agent-registry.json, felix-governance.md, felix-capability-roadmap.md
- **area/ea**: escalation-ops.md, observation-ops.md
- **area/task-intel**: task-intelligence-ops.md, vikunja-ops.md
- **area/content**: obsidian-sync-ops.md, obsidian-setup.md, obsidian.md,
  transcribe-ops.md, inbox-ops.md
- **area/docs**: INDEX.md, doc-standards.md, divio-classification.md,
  visual-docs-style.md, glossary.md
- **area/biz-ops**: goals-ops.md, habits-ops.md, vision-framework.md,
  strategic-acceleration-charter.md

Note: A document CAN appear under multiple domains (constraint C-005). Use
your judgment — if a doc would need checking when that area changes, include it.
Use relative paths from repo root (e.g., `docs/design/architecture/service-inventory.md`).

**Validation**:
- [ ] JSON is valid (parseable)
- [ ] All 8 area labels are present as keys
- [ ] All paths listed actually exist in the repo
- [ ] schema_version, last_updated, updated_by fields present
- [ ] A single new doc can be added with a one-line edit (NFR-002)

---

## Subtask T002: Create docs-debt Issue Template

**Purpose**: Provide a structured issue template for filing documentation gaps,
so audit issues have consistent structure for Claude Code to act on.

**File**: `.github/ISSUE_TEMPLATE/docs-debt.md`

**Steps**:

1. Create the template file following the existing template pattern (see
   `.github/ISSUE_TEMPLATE/bug.md` for frontmatter and structure conventions)
2. Use this frontmatter:
   ```yaml
   ---
   name: Docs Debt
   about: Documentation gap or outdated content that needs attention
   title: "Docs: "
   labels: P2-debt
   assignees: ''
   ---
   ```
3. Include these sections in the body:

   - **Artifact** — path to the document that is missing or outdated
   - **Gap description** — what is missing, outdated, or incorrect
   - **Area** — which area label(s) this relates to (checklist of 8 areas)
   - **Cross-references** — related docs, issues, or PRs that provide context
   - **Draft outline** — suggested structure or content for the fix
   - **Success criteria** — how to verify the gap is resolved

4. Use HTML comments for guidance text (matching existing template style)
5. Keep the template concise but structured enough for automated consumption

**Validation**:
- [ ] File exists at `.github/ISSUE_TEMPLATE/docs-debt.md`
- [ ] Frontmatter is valid YAML with name, about, title, labels
- [ ] All required sections present: artifact, gap, area, cross-refs, outline, criteria
- [ ] Template follows same formatting conventions as bug.md
- [ ] config.yml does not need updating (it uses `blank_issues_enabled: true` or
      similar — check and update only if it explicitly restricts template list)

---

## Subtask T003: Validate Domain Map Completeness

**Purpose**: Ensure the domain map covers all active documentation files listed
in docs/INDEX.md. Every active doc should appear in at least one domain.

**Steps**:

1. After creating doc-domain-map.json (T001), compare its entries against
   docs/INDEX.md
2. Extract all doc paths from INDEX.md (excluding archive/ and issues/diagnostics/)
3. Check that every active doc path appears in at least one domain in the map
4. If any docs are missing, add them to the appropriate domain(s)
5. Check that all paths in the domain map actually exist as files

**Validation**:
- [ ] Every active doc in INDEX.md appears in at least one domain
- [ ] No paths in the domain map point to non-existent files
- [ ] Coverage is reasonable — docs appear under domains where changes would
      actually require re-verification of that doc

---

## Definition of Done

- [ ] doc-domain-map.json exists at `docs/design/architecture/data/` with all 8 domains
- [ ] docs-debt.md template exists at `.github/ISSUE_TEMPLATE/` with all required fields
- [ ] Domain map is complete (all active docs covered, all paths valid)
- [ ] JSON is valid and parseable
- [ ] Template renders correctly in GitHub issue creation UI

## Risks

| Risk | Mitigation |
|------|-----------|
| Domain map misses a doc | T003 cross-validates against INDEX.md |
| Template doesn't render in GitHub UI | Follow existing template pattern exactly |
| Domain assignments are debatable | Use best judgment; map is easy to update later |

## Reviewer Guidance

1. Verify all 8 area labels are present in the domain map
2. Spot-check 3-4 domain entries — are the listed docs actually relevant?
3. Check that the issue template has all 6 required sections
4. Verify JSON validity
5. Check that the template frontmatter labels field uses `P2-debt` (not a new label)
