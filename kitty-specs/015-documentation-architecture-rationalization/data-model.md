# F015 Phase 1 — Data Model: Divio Schema + Frontmatter

**Feature**: 015-documentation-architecture-rationalization
**Phase**: 1 (Design)

This document defines the canonical `doc_type` schema, Divio-to-directory mapping, and frontmatter field contracts that F015 establishes. All documents added to `docs/**` after F015 acceptance must conform to this schema.

---

## 1. Canonical `doc_type` Values

The `doc_type` frontmatter field names the Divio classification for a document. Seven canonical values, organized by Divio type:

| `doc_type` | Divio Parent | Purpose | Example Paths |
|---|---|---|---|
| `runbook` | how-to | Prescriptive step-by-step procedure; executable by human or agent | `docs/runbooks/*-ops.md`, `docs/runbooks/deployment.md` |
| `reference` | reference | Describes system machinery — architecture, services, schemas, inventories | `docs/design/architecture/*.md`, `docs/constitution/AGENT-REGISTRY.md`, `CLAUDE.md` |
| `spec` | reference (sub) | Feature specification produced via spec-kitty | `docs/func-spec/F###_*.md` |
| `explanation` | explanation | Rationale — WHY decisions were made, design principles, context | `docs/design/adversarial-analysis.md`, design-rationale docs |
| `standard` | explanation (sub) | Cross-cutting authoring or operational standards with rationale | `docs/design/standards/doc-standards.md`, `docs/runbooks/repo-governance.md` |
| `postmortem` | explanation (sub) | Post-incident analysis | `docs/postmortems/YYYY-MM-DD_*.md` |
| `diagnostic` | how-to (sub) | Incident diagnostics, troubleshooting notes, runtime-used issue logs | `docs/issues/diagnostics/**` |

**Retired values** (existing docs to be migrated):

| Legacy value | Migrate to | Rationale |
|---|---|---|
| `handbook` | `runbook` (prescriptive) OR `explanation` (rationale) OR `standard` (cross-cutting policy) OR `reference` (command list) | Dominant-type rule per C-007; classify each file individually |
| `strategy` | `reference` (living capability state) OR `explanation` (strategic rationale) | Ambiguous; prefer `reference` if describing current state, `explanation` if articulating why |
| `charter` | `explanation` | Sub-type of explanation (strategic rationale) |
| `policy` | `standard` | Sub-type of standard (cross-cutting rule with rationale) |
| `note` | `explanation` OR `reference` depending on content | Note is too generic; force Divio classification |
| `index` | `reference` | An index IS a reference doc |
| `readme` | `reference` | A readme IS a reference doc (kept as-is for existing 2 files) |
| `guide` | `reference` OR `runbook` depending on content | Rendered views (e.g., `.view.md`) are `reference`; how-to guides are `runbook` |
| `func-spec` | `spec` | Direct rename |

---

## 2. Divio-to-Directory Mapping

Single canonical home per artifact type (from spec Architecture Principles):

| `doc_type` | Canonical Home | Notes |
|---|---|---|
| `runbook` | `docs/runbooks/` | Governance runbooks land in `docs/runbooks/governance/` (created for F016) |
| `reference` | Contextual — `docs/design/architecture/`, `docs/constitution/`, `docs/design/` top-level | Single canonical home per specific artifact (architecture in architecture/, constitution in constitution/, system-wide specs in design/) |
| `spec` | `docs/func-spec/` | Always |
| `explanation` | `docs/design/` (design rationale) OR the doc's contextual home | Design rationale in `docs/design/`; service-specific rationale may live alongside the service's runbook (flagged in frontmatter) |
| `standard` | `docs/design/standards/` | Cross-cutting standards consolidated here |
| `postmortem` | `docs/postmortems/` | Always; filename format `YYYY-MM-DD_incident-slug.md` |
| `diagnostic` | `docs/issues/diagnostics/` | Always; exempt from restructuring per C-002 |

**Machine-readable artifacts** (JSON files):

| Artifact type | Canonical Home |
|---|---|
| Operational state (service inventory, topology, hardware, network, credentials, data-flows) | `docs/design/architecture/data/` |
| Schemas for operational state | `docs/design/architecture/data/` (co-located with data they describe) |
| Doc standards schemas (frontmatter.schema, allowed-values, validator-policy) | `docs/design/standards/` |
| Agent registry | `docs/constitution/` |
| Other machine-readable artifacts | Determined per-feature; INDEX.md must reference |

---

## 3. Required Frontmatter Fields

Every document in `docs/**` (excluding `docs/archive/**`, `docs/_templates/**`) must have these fields:

| Field | Type | Required | Values | Purpose |
|---|---|---|---|---|
| `title` | string | ✅ | free-form | Human-readable title (matches H1) |
| `doc_type` | enum | ✅ | one of canonical values above | Divio classification |
| `status` | enum | ✅ | `draft` \| `approved` \| `deprecated` \| `archived` | Document lifecycle state |

---

## 4. Optional Frontmatter Fields

| Field | Type | Applicable To | Values | Purpose |
|---|---|---|---|---|
| `audience` | enum | `runbook` (required); others optional | `human-only` \| `agent-executable` \| `both` | Operator vs. agent execution pathway (F015 FR-005) |
| `owners` | array | all | GitHub handles or names | Maintainers / points of contact |
| `last_validated` | string (date) | `runbook`, `reference`, `standard` | ISO 8601 date | Last time content was verified against reality |
| `version` | string | `reference`, `spec`, `standard` | semver-ish or free-form | Version of the referenced artifact |
| `supersedes` | string (path) | `reference`, `spec` | path to prior doc | Explicit supersession link (e.g., v1.0 spec supersedes v0.3) |
| `superseded_by` | string (path) | deprecated docs | path to new doc | Reverse pointer (v0.3 points to v1.0) |
| `divio_ambiguity` | string | any | free-form note | If doc mixes Divio types, note the secondary type here per C-007 |

---

## 5. Audience Declaration Rules (FR-005)

For `doc_type: runbook`, `audience` is **required**:

- **`human-only`**: Steps require judgement, credentials not accessible to agents, or policy decisions. Example: `felix-governance.md`, `spec-kitty-init-in-existing-repo.md`.
- **`agent-executable`**: Steps are mechanical queries/mutations using APIs, systemctl, or shell commands already available to agents. Candidate for future skill conversion. Example: health checks, service restarts.
- **`both`**: Steps can be performed by either; variations noted in-doc (e.g., agent uses API, human uses UI).

For other `doc_type` values, `audience` is optional (defaults to `both`).

---

## 6. `status` Lifecycle Rules

| From → To | Trigger |
|---|---|
| (new) → `draft` | Initial authoring |
| `draft` → `approved` | Content validated; `last_validated` set |
| `approved` → `approved` (re-validation) | Content re-verified; `last_validated` updated |
| `approved` → `deprecated` | Superseded by another doc (set `superseded_by`) or no longer relevant |
| `deprecated` → `archived` | Moved to `docs/archive/` (retained for history) |

**Archived docs exempt from this schema.**

---

## 7. Example Frontmatter Blocks

### Runbook (agent-executable)

```yaml
---
title: Vikunja Operations Runbook
doc_type: runbook
status: approved
audience: agent-executable
owners: [kgale]
last_validated: 2026-04-04
version: "1.2"
---
```

### Runbook (human-only)

```yaml
---
title: Felix Governance Runbook
doc_type: runbook
status: approved
audience: human-only
owners: [kgale]
last_validated: 2026-04-04
---
```

### Reference doc (architecture)

```yaml
---
title: Service Inventory
doc_type: reference
status: approved
owners: [kgale]
last_validated: 2026-04-04
version: "1.0"
---
```

### Explanation (design rationale)

```yaml
---
title: Adversarial Analysis — Personal AI Command & Accountability System
doc_type: explanation
status: approved
owners: [kgale]
---
```

### Standard

```yaml
---
title: kg-automation Documentation Standards (Canon v3)
doc_type: standard
status: approved
version: "3.0"
owners: [kgale]
---
```

### Spec (func-spec)

```yaml
---
title: "F015: Documentation Architecture Rationalization"
doc_type: spec
status: draft
version: "1.1"
---
```

### Deprecated doc

```yaml
---
title: "Personal AI Command & Accountability System — v0.3"
doc_type: reference
status: deprecated
superseded_by: docs/design/personal-ai-system-spec-v1.0.md
---
```

### Diagnostic

```yaml
---
title: Spec-Kitty Workflow Journal
doc_type: diagnostic
status: active
---
```

### Postmortem

```yaml
---
title: "2026-MM-DD: Vikunja Service Outage"
doc_type: postmortem
status: approved
owners: [kgale]
---
```

---

## 8. INDEX.md Grouping Strategy

`docs/INDEX.md` groups documents by **directory context** (preserving existing mental model) with Divio-type annotations:

```markdown
## CLAUDE.md → Governance & Operating Rules

- [Felix Constitution](docs/constitution/FELIX-CONSTITUTION.md) — `reference` (governance)
- [Agent Registry](docs/constitution/AGENT-REGISTRY.md) — `reference` (registry)

## System Architecture (docs/design/architecture/)

All `reference`. Describes current deployed state.
- [README](docs/design/architecture/README.md) — architecture suite index
- [Service Inventory](docs/design/architecture/service-inventory.md) + [JSON](docs/design/architecture/data/service-inventory.json)
...

## Operational Runbooks (docs/runbooks/)

All `runbook`. Prescriptive step-by-step procedures.
- [Vikunja Operations](docs/runbooks/vikunja-ops.md) — `agent-executable`
...

## Design Rationale & Standards (docs/design/, docs/design/standards/)

Mix of `explanation` and `standard`. Why decisions were made + cross-cutting rules.
...

## Feature Specifications (docs/func-spec/)

All `spec`. Historical and planned features.
...

## Diagnostics & Postmortems (docs/issues/, docs/postmortems/)

All `diagnostic` and `postmortem`. Runtime and post-incident.
...

## Machine-Readable Artifacts

Canonical home: `docs/design/architecture/data/` for operational state.
...
```

This grouping provides both navigability (by directory/purpose) and Divio discoverability (type annotations).

---

## 9. State Transitions — Not Applicable

This is a documentation schema, not an executable entity. No state-machine transitions beyond `status` lifecycle (section 6).

---

## 10. Validation — Manual

Per C-006, no automated validator is introduced. Correctness of a document's frontmatter is verified by:

1. Author checks their doc against this schema when adding/editing.
2. INDEX.md listing serves as a registry; docs not in INDEX.md are orphaned and get flagged on next feature.
3. Spot-checks during feature implementation (reference-audit passes catch broken links, which implicitly verify frontmatter presence).

Future feature may introduce a JSON-schema-backed validator at `docs/design/standards/frontmatter.schema.json` (file already exists but not enforced). Out of F015 scope.
