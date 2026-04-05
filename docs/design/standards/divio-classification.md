---
title: Divio Classification Standard
doc_type: standard
status: approved
owners: [kgale]
version: "1.0"
last_validated: 2026-04-05
---

# Divio Classification Standard

## Overview

The [Divio documentation framework](https://docs.divio.com/documentation-system/) organizes technical documentation into four distinct types — **tutorials**, **how-to guides**, **reference**, and **explanation** — each serving a different user need. kg-automation adopts an adapted version of this framework tuned for a solo-operator, AI-agent-consumed documentation corpus.

**Why kg-automation uses Divio**: Documentation is consumed by both human operators and AI agents (Claude Code, OpenClaw). Divio provides an unambiguous classification that tells a reader what to DO with a document — execute its steps (how-to/runbook), absorb as context (reference), understand why something is (explanation), or skip (tutorials, which are absent by design). Agents that misclassify docs waste tokens reading operational procedures as conceptual material, or vice versa.

**Internal-audience mapping**:

- **Tutorials** — ABSENT by design. Solo-operator system; there is no onboarding audience needing guided learning.
- **How-to guides** → `runbook`. Prescriptive, step-by-step procedures executable by humans or agents.
- **Reference** → architecture docs, CLAUDE.md-style system context, service inventories, schemas.
- **Explanation** → governance (constitution), design rationale, post-incident analysis.

This standard is the authoritative taxonomy for the repo's `doc_type` frontmatter field. Treat `docs/design/standards/doc-standards.md` as the operational authoring companion (frontmatter schema, file naming, status lifecycle); treat this document as the classification taxonomy.

---

## Canonical doc_type Values

Seven canonical `doc_type` values cover every active document. Three are Divio parents; four are named sub-types that extend the parents for specific artifact categories.

| `doc_type` | Divio Parent | Purpose | Example Paths |
|---|---|---|---|
| `runbook` | how-to | Prescriptive step-by-step procedure; executable by human or agent | `docs/runbooks/vikunja-ops.md`, `docs/runbooks/deployment.md`, `docs/runbooks/felix-governance.md` |
| `reference` | reference | Describes system machinery — architecture, services, schemas, inventories, context | `docs/design/architecture/service-inventory.md`, `docs/constitution/AGENT-REGISTRY.md`, `CLAUDE.md` |
| `spec` | reference (sub) | Feature specification produced via spec-kitty | `docs/func-spec/F013_vikunja_task_intelligence_agent.md`, `docs/func-spec/F015_documentation_architecture_rationalization.md` |
| `explanation` | explanation | Rationale — WHY decisions were made, design principles, context behind the architecture | `docs/design/adversarial-analysis.md`, `docs/design/office2-backup-and-security.md` |
| `standard` | explanation (sub) | Cross-cutting authoring or operational standards with rationale | `docs/design/standards/doc-standards.md`, `docs/design/standards/divio-classification.md` (this file), `docs/runbooks/repo-governance.md` |
| `postmortem` | explanation (sub) | Post-incident analysis — what happened, why, what changes | `docs/issues/postmortems/YYYY-MM-DD_*.md` |
| `diagnostic` | how-to (sub) | Incident diagnostics, troubleshooting notes, runtime-used issue logs | `docs/issues/diagnostics/spec-kitty-workflow-journal.md`, `docs/issues/diagnostics/f012-merge-breadcrumbs.md` |

**Dominant-type rule**: If a document mixes types, pick the dominant type and note the secondary type in a `divio_ambiguity` frontmatter field.

---

## Canonical Home Per Type

Each `doc_type` lives in a single canonical directory. This enforces discoverability and prevents duplicate coverage.

| `doc_type` | Canonical Home | Notes |
|---|---|---|
| `runbook` | `docs/runbooks/` | Governance runbooks live in `docs/runbooks/governance/` |
| `reference` | Contextual | Architecture in `docs/design/architecture/`, governance registries in `docs/constitution/`, system-wide specs/vision in `docs/design/` top-level |
| `spec` | `docs/func-spec/` | Always |
| `explanation` | `docs/design/` top-level | Design rationale. Service-specific rationale may live alongside its runbook with `doc_type: explanation` flagged |
| `standard` | `docs/design/standards/` | Cross-cutting standards consolidated here |
| `postmortem` | `docs/issues/postmortems/` | Filename format: `YYYY-MM-DD_incident-slug.md` |
| `diagnostic` | `docs/issues/diagnostics/` | Exempt from restructuring per F015 constraint C-002 |

**Machine-readable artifacts (JSON files)**:

| Artifact type | Canonical Home |
|---|---|
| Operational state (service inventory, topology, hardware, network, credentials, data-flows) | `docs/design/architecture/data/` |
| Schemas for operational state | `docs/design/architecture/data/` (co-located with data) |
| Doc standards schemas (frontmatter, validator policy, allowed values) | `docs/design/standards/` |
| Agent registry | `docs/constitution/` |

**Protocol boundary**: Adding a new document without updating `docs/INDEX.md` is a protocol violation (see `docs/design/architecture/change-control.md`).

---

## Legacy Value Migration Table

kg-automation's documentation corpus pre-dates this standard. Older docs used ad-hoc `doc_type` values that must be migrated to canonical values. Use the **dominant-type rule** (C-007): classify by the document's primary purpose, note secondary types in `divio_ambiguity`.

| Legacy value | Migrate to | How to decide |
|---|---|---|
| `handbook` | `runbook` (if prescriptive) OR `explanation` (if rationale) OR `standard` (if cross-cutting policy) OR `reference` (if command list) | Classify each file individually by dominant content type |
| `strategy` | `reference` (if describing current state / living capability status) OR `explanation` (if articulating strategic rationale) | Prefer `reference` for "what is"; `explanation` for "why" |
| `charter` | `explanation` | Sub-type of strategic rationale |
| `policy` | `standard` | Sub-type of cross-cutting rule with rationale |
| `note` | `explanation` OR `reference` depending on content | Too generic; force Divio classification |
| `index` | `reference` | An index IS a reference doc |
| `readme` | `reference` (recommended) | A readme IS a reference doc; legacy `readme` value retained for compatibility but prefer `reference` for new docs |
| `guide` | `reference` (if rendered view / diagram) OR `runbook` (if how-to) | Depends on whether guide is descriptive or prescriptive |
| `func-spec` | `spec` | Direct rename |

**Migration procedure**:

1. Read the document; identify primary purpose.
2. Choose canonical `doc_type` from the Canonical Values table.
3. If document mixes types, use dominant-type rule and add `divio_ambiguity` note.
4. Update frontmatter; do NOT modify body content during migration.
5. If the doc also belongs in a different canonical home, use `git mv` to move it in the same change.

---

## Audience Declaration (for runbooks)

For `doc_type: runbook`, the `audience` frontmatter field is **required**. It declares who can execute the runbook's steps:

| Value | Meaning | Implications |
|---|---|---|
| `human-only` | Steps require judgement, credentials not accessible to agents, or policy decisions | Never delegated to agents; runbook lives in repo for human reference |
| `agent-executable` | Steps are mechanical queries/mutations using APIs, systemctl, or shell commands already available to agents | Candidate for future skill conversion; kept up-to-date as source of truth |
| `both` | Steps can be performed by either; in-doc notes describe variations | Agent uses API variant; human uses UI variant. Most operational runbooks land here |

**Examples**:

- `docs/runbooks/felix-governance.md` → `audience: human-only` (autonomy transitions require judgement)
- `docs/runbooks/vikunja-ops.md` → `audience: agent-executable` (health checks, restarts are mechanical)
- `docs/runbooks/deployment.md` → `audience: both` (procedural but some judgement calls)

**Rule for new runbooks**: Default to `both` if uncertain. Escalate to `human-only` if steps involve autonomy, identity, credentials-beyond-secrets-dir, or irreversible destructive operations.

For non-runbook `doc_type` values, `audience` is optional (defaults to `both`).

---

## Supersession

When a document is replaced by a newer version (e.g., v0.3 system spec → v1.0), use the supersession pattern:

**On the deprecated doc**:

```yaml
---
title: <original title>
doc_type: reference
status: deprecated
superseded_by: docs/design/personal-ai-system-spec-v1.0.md
---
```

**On the replacement doc** (optional but recommended):

```yaml
---
title: <new title>
doc_type: reference
status: approved
supersedes: docs/design/personal-ai-system-spec-v03.md
---
```

**Lifecycle states** (per `status` field):

| From → To | Trigger |
|---|---|
| (new) → `draft` | Initial authoring |
| `draft` → `approved` | Content validated; `last_validated` set |
| `approved` → `approved` | Re-validation; update `last_validated` |
| `approved` → `deprecated` | Superseded (set `superseded_by`) or no longer relevant |
| `deprecated` → `archived` | Moved to `docs/archive/` (retained for history) |

**Archived docs** (under `docs/archive/`) are exempt from this standard — they are frozen historical artifacts and their stale frontmatter is acceptable.

---

## Compliance

A document is **compliant** with this standard if:

1. Its `doc_type` is one of the 7 canonical values (no legacy values).
2. It lives in the canonical home for its `doc_type`.
3. If `doc_type: runbook`, it declares an `audience`.
4. If it mixes Divio types, it declares `divio_ambiguity`.
5. It is listed in `docs/INDEX.md`.

Docs that fail (1)–(4) are flagged during feature reviews or `/spec-kitty.analyze` passes. Docs that fail (5) are orphaned and invisible to agents — they get flagged on the next feature that touches the surrounding directory.

No automated validator enforces this standard (per F015 constraint C-006). Correctness is verified manually by authors and reviewers.

---

## Related Standards

- `docs/design/standards/doc-standards.md` — operational authoring companion (frontmatter schema, filename conventions, status lifecycle mechanics)
- `docs/design/standards/frontmatter.schema.json` — JSON schema for frontmatter fields (not actively enforced; for future automation)
- `docs/design/standards/allowed-values.json` — enum definitions (not actively enforced)
- `docs/design/architecture/change-control.md` — protocol for updating `docs/INDEX.md` when adding/moving/archiving docs

---

## Revision History

| Version | Date | Changes |
|---|---|---|
| 1.0 | 2026-04-05 | Initial published version — authored under F015 (WP01) |
