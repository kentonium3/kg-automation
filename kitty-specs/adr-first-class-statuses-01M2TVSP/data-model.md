# Data Model: ADRs as first-class docs

**Mission**: adr-first-class-statuses-01M2TVSP · **Phase**: 1 · **Date**: 2026-09-18

No database. The "data" here is document metadata and one taxonomy file, but the entities and their
invariants are what the validator enforces, so they are modelled explicitly.

---

## Entity: DocStatus

The authoritative standing of a document. **The single machine-readable answer to "is this safe to act
on?"** Lives in frontmatter.

| Attribute | Value |
|---|---|
| Location | `status:` in document frontmatter (required field) |
| Domain | drawn from the set permitted for that document's `doc_type` |
| Authority | **authoritative**. Where body text and frontmatter disagree, frontmatter wins. |

**Permitted sets**

| `doc_type` | Permitted statuses |
|---|---|
| `decision` (ADRs) | `draft`, `proposed`, `approved`, `superseded`, `deprecated` |
| all others | `draft`, `proposed`, `in_review`, `approved`, `deprecated`, `archived`, `active` |

**State meanings for `decision`**

- `draft` — being written; not yet put forward.
- `proposed` — complete and coherent, but the concept is not settled; needs debate or design.
- `approved` — decided, by a stated authority, and safe to act on.
- `superseded` — a newer ADR replaces this decision. A log row of type `superseded-by` names it.
- `deprecated` — the topic is no longer relevant. No successor.

**Invariants**
- `partially_superseded` does not exist and must never be added (C-004).
- `active` is invalid for `doc_type: decision`.
- A status transition is caused by an ADR or by topic irrelevance — never by a log entry (C-003).

---

## Entity: DecisionLogEntry

One append-only row recording how an ADR's standing was reached. **Carries no authority** — it records
that authority was exercised elsewhere.

| Column | Type | Machine-read? | Content |
|---|---|---|---|
| `Date` | ISO `YYYY-MM-DD` | ordering only | when the fact was recorded |
| `Type` | enum | **yes — the only parsed column** | `erratum` · `amendment` · `superseded-by` · `context` |
| `By` | free text | no | who recorded it |
| `Summary` | free text, one line | no | the human-readable fact |
| `Refs` | free text | no | ADR / issue / commit where authority was exercised |

**Invariants**
- **Belongs to the ADR it is about** (FR-002). An entry concerning ADR-0008 lives in ADR-0008 — not in
  the ADR it cross-references. This is the observed defect: the ADR-0008 erratum was filed in ADR-0004.
- **Append-only.** Rows are added; existing rows are never edited or removed.
- **May not contradict the frozen body** (C-002). It annotates; it cannot decide.
- A `superseded-by` row pairs with `status: superseded`. Neither is meaningful alone.

---

## Entity: ADR

| Part | Mutability |
|---|---|
| Frontmatter | **mutable** — `status` changes as standing changes; this is metadata about the decision, not the decision |
| Body (everything above the log) | **frozen at approval** |
| Decision log section | **append-only**; required in every ADR, empty when unused (`*No entries.*`) |

**Invariants**
- Exactly one decision log section, last in the document.
- New ADRs carry no body `Status:` line — frontmatter is authoritative (FR-007). Existing bodies that
  carry one are historical and are not edited; the frozen text stands.

---

## Entity: StatusTaxonomySource

`docs/design/standards/allowed-values.json` — the one enforced definition.

```
{
  "status": [ ...default set... ],
  "status_by_doc_type": { "decision": [ ...ADR set... ] },
  ...
}
```

**Derived artifacts (build output, never hand-edited — C-007)**
- `docs/design/standards/frontmatter.schema.json` — status enum
- `docs/design/standards/doc-standards.md` — status list, inside `GENERATED:status-list` sentinels

**Invariants**
- Exactly one writer: the generator.
- Regenerating twice produces no diff (NFR-001).
- A derived artifact out of sync with the source fails CI (SC-002).

---

## Scope boundary (C-001)

Frontmatter validation must never walk `kitty-specs/`, `.kittify/`, `.agents/`, `.claude/`, `.codex/`
or `dist/`. Those carry frontmatter written by **spec-kitty**, on spec-kitty's own contract. This model
governs kg-automation-authored documents only, and the boundary is asserted by test (SC-005) rather
than left as a comment in `SKIP_DIRS`.
