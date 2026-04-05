# F015 Phase 1 — Quickstart: How to Add a Doc

**Feature**: 015-documentation-architecture-rationalization
**Phase**: 1 (Design — authoring flow)
**Audience**: Kent + AI agents authoring docs in kg-automation

This quickstart describes the authoring flow that future docs must follow after F015 is accepted. Read this before adding a new doc to `docs/**`.

---

## Decision Tree — Which Divio Type Is My Doc?

Answer these questions in order. Stop at the first "yes".

1. **Is my doc a prescriptive step-by-step procedure someone (human or agent) will execute?**
   → `doc_type: runbook`
   → Canonical home: `docs/runbooks/` (governance ones go in `docs/runbooks/governance/`)
   → Declare `audience` in frontmatter: `human-only` | `agent-executable` | `both`.

2. **Is my doc a spec-kitty feature specification?**
   → `doc_type: spec`
   → Canonical home: `docs/func-spec/`
   → Filename: `F###_feature_slug.md`

3. **Is my doc describing the CURRENT state of the system — architecture, services, schemas, inventories, CLAUDE.md-style context?**
   → `doc_type: reference`
   → Canonical home depends on subject:
     - System architecture → `docs/design/architecture/`
     - Governance registries → `docs/constitution/`
     - Cross-cutting system specs / vision → `docs/design/` (top-level)

4. **Is my doc a cross-cutting authoring or operational standard (docs style, git policy, linter config)?**
   → `doc_type: standard`
   → Canonical home: `docs/design/standards/`

5. **Is my doc a post-incident analysis?**
   → `doc_type: postmortem`
   → Canonical home: `docs/postmortems/`
   → Filename: `YYYY-MM-DD_incident-slug.md`

6. **Is my doc an incident diagnostic / troubleshooting note used at runtime?**
   → `doc_type: diagnostic`
   → Canonical home: `docs/issues/diagnostics/`

7. **Is my doc explaining WHY a decision was made — rationale, design principles, strategic direction, security analysis?**
   → `doc_type: explanation`
   → Canonical home: `docs/design/` (or alongside the service/system it explains)

If none of the above applies, stop and ask: is this really a kg-automation doc, or does it belong in `~/second-brain/` or elsewhere?

---

## Authoring Flow

### Step 1 — Choose the doc_type

Use the decision tree above. If the content mixes types, pick the **dominant** type and note the secondary in `divio_ambiguity` frontmatter per C-007.

### Step 2 — Place the file in the canonical home

Single canonical home per type (see `data-model.md` § 2). Do NOT create new subdirectories without updating INDEX.md in the same change.

### Step 3 — Write the frontmatter block

Minimum required fields:

```yaml
---
title: <human-readable title matching H1>
doc_type: <one of: runbook|reference|spec|explanation|standard|postmortem|diagnostic>
status: draft
---
```

If `doc_type: runbook`, add `audience: <human-only|agent-executable|both>`.

See `data-model.md` § 7 for example blocks per type.

### Step 4 — Write the content

Follow the doc-type conventions:

- **Runbook**: Numbered or checklist-based prescriptive steps. Each step is executable (shell command, API call, UI action). Include expected output / success criteria per step. Troubleshooting section at end.
- **Reference**: Describe what IS. Tables, diagrams, inventories. No "how to"; no "why" — those belong in runbooks and explanations.
- **Spec**: Use `docs/func-spec/_TEMPLATE_spec_kitty_input.md` as starting point.
- **Explanation**: Narrative prose. State the decision, then justify. Link to the reference doc(s) the decision affects.
- **Standard**: State the rule, then rationale. Enumerate applicability.
- **Postmortem**: Incident summary → timeline → root cause → impact → remediation → lessons learned.
- **Diagnostic**: Context → symptom → investigation steps → findings → resolution (if known) → follow-ups.

### Step 5 — Update `docs/INDEX.md`

Add the new doc to the appropriate section of `docs/INDEX.md`. Per the change-control protocol (FR-011), this is NOT optional — adding a doc without updating INDEX.md is a protocol violation.

### Step 6 — Update inbound references (if applicable)

If your new doc should be referenced from:
- `CLAUDE.md` — add a reference there
- The Felix constitution — add a reference there
- Related runbooks / architecture docs — add cross-references

### Step 7 — Commit

Conventional commit message:

```text
docs: add <doc_type> for <subject>

<short description>
```

Example: `docs: add runbook for new felix-admin-scheduler service`.

---

## Example — Adding a New Service Runbook

You're adding a runbook for a new service called `felix-admin-journal`.

1. **Decide type**: Prescriptive ops procedure → `runbook`.
2. **Place file**: `docs/runbooks/journal-ops.md`.
3. **Frontmatter**:

   ```yaml
   ---
   title: Journal Operations Runbook
   doc_type: runbook
   status: draft
   audience: agent-executable
   owners: [kgale]
   last_validated: 2026-04-04
   ---
   ```

4. **Content**: Service management (start/stop/restart), credentials, health check, logs, troubleshooting.
5. **Update `docs/INDEX.md`**: add entry under "Operational Runbooks" section.
6. **Inbound references**:
   - Add service entry to `docs/design/architecture/service-inventory.md` → link to this runbook.
   - Update `docs/design/architecture/data/service-inventory.json` with new service record.
7. **Commit**: `docs: add runbook for felix-admin-journal service`.

---

## Example — Adding Design Rationale

You're documenting why you chose Vikunja over alternatives.

1. **Decide type**: Rationale for a past decision → `explanation`.
2. **Place file**: `docs/design/vikunja-selection-rationale.md` (or consolidate into an existing explanation doc if one fits).
3. **Frontmatter**:

   ```yaml
   ---
   title: Vikunja Selection Rationale
   doc_type: explanation
   status: approved
   owners: [kgale]
   ---
   ```

4. **Content**: Alternatives considered → selection criteria → why Vikunja won → trade-offs accepted.
5. **Update `docs/INDEX.md`**: add entry under "Design Rationale" section.
6. **Inbound references**: Link from `docs/design/architecture/service-inventory.md` (Vikunja section) and from any relevant func-spec.
7. **Commit**: `docs: add explanation for Vikunja selection rationale`.

---

## Anti-Patterns — Do NOT Do These

1. **Don't mix Divio types in one doc.** A doc that is "mostly a runbook but also explains why we chose this architecture" should be split: runbook in `docs/runbooks/`, explanation in `docs/design/`, with cross-references between them.
2. **Don't leave `doc_type` blank.** Every active doc must declare its type.
3. **Don't use legacy values** (`handbook`, `strategy`, `policy`, `note`, `charter`, `index`, `guide`, `func-spec`). Map to canonical values per `data-model.md` § 1.
4. **Don't add a doc without updating INDEX.md.** Protocol violation per FR-011.
5. **Don't write runbooks without an audience declaration.** Mandatory field for `doc_type: runbook`.
6. **Don't create new directories** under `docs/` without writing down the purpose in INDEX.md and establishing the canonical home rule.

---

## Quick Reference Card

| Need to add… | `doc_type` | Home |
|---|---|---|
| Service operations procedure | runbook | `docs/runbooks/` |
| Governance procedure | runbook | `docs/runbooks/governance/` |
| Architecture description | reference | `docs/design/architecture/` |
| Service JSON/schema | (reference, no frontmatter needed for pure JSON) | `docs/design/architecture/data/` |
| Governance registry | reference | `docs/constitution/` |
| Feature spec | spec | `docs/func-spec/` |
| Design decision rationale | explanation | `docs/design/` |
| Documentation/git standard | standard | `docs/design/standards/` |
| Post-incident report | postmortem | `docs/postmortems/` |
| Troubleshooting / issue diagnostic | diagnostic | `docs/issues/diagnostics/` |

---

## Where This Standard Lives

- **Authoritative definition**: `docs/design/standards/divio-classification.md` (created as part of F015 implementation).
- **This quickstart**: Planning artifact, retained in `kitty-specs/015-*/` for historical context. The permanent standard lives in the standards directory.
