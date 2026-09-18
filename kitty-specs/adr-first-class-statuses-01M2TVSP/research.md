# Research: ADRs as first-class docs

**Mission**: adr-first-class-statuses-01M2TVSP · **Phase**: 0 · **Date**: 2026-09-18

Resolves the clarifications outstanding after discovery. Discovery settled the *model* (three separated
roles: ADRs decide, `status` carries standing, the log records history). What follows is the mechanical
detail that model implies.

---

## R-01 — ADRs are not distinguishable by `doc_type` today — **BLOCKING, resolved**

**Finding (measured, not assumed).** All nine ADRs carry `doc_type: reference`, identical to ordinary
reference documents:

```
0001..0009  →  doc_type: reference   (9 of 9)
```

Meanwhile `decision` is **already a permitted `doc_type`** in `allowed-values.json` and is used by
nothing.

**Why it blocks.** FR-004 requires status sets scoped by `doc_type`. With every ADR typed `reference`,
"ADR-only statuses" and "`active` is invalid for an ADR" are both unexpressible — the validator cannot
tell an ADR from any other reference doc.

**Resolution.** Migrate ADRs to `doc_type: decision` as part of IC-05. It is already allowed, it is
semantically correct (an ADR *is* a decision record — the ADR README calls them "focused notes that
explain *why* a particular architectural option was chosen"), and it needs no enum change.

**Consequence for the plan.** IC-05 grows a step, and IC-01/IC-03 depend on it: the scoped status sets
key off `decision`. Without this, FR-004, SC-003 and half of SC-001 cannot be satisfied.

**Alternatives rejected.** Path-based scoping (`docs/design/architecture/adr/`) — couples the validator
to a directory layout and silently fails if an ADR moves. A new frontmatter field (`is_adr`) —
redundant with `doc_type`, and a second thing to keep true.

---

## R-02 — Shape of `doc_type`-scoped status in `allowed-values.json`

**Question.** `status` is currently a flat array consumed by `validate_docs.py`. Scoping needs a map.

**Recommendation.** Keep a `status` default array (unchanged meaning for every doc_type that does not
opt in) and add `status_by_doc_type: { "decision": [...] }` consulted first. Backward-compatible: an
unmodified validator reading only `status` still works, and the diff stays reviewable.

**Rejected.** Replacing `status` with a map — breaks any consumer reading the flat list, and this file
gates *every commit in the repo* through the pre-commit hook. A parse regression blocks all work.

**Open for the reviewer**: whether non-ADR doc types should eventually get their own sets, or whether
the shared default is the long-term shape.

---

## R-03 — Which statuses survive

**Decided in discovery**: `partially_superseded` must never exist (C-004); `approved` is retained over
`accepted` (C-005).

**Recommendation.**
- `decision` (ADRs): `draft`, `proposed`, `approved`, `superseded`, `deprecated`.
- All other doc types: current set unchanged — `draft`, `proposed`, `in_review`, `approved`,
  `deprecated`, `archived`, `active`.

`rejected` — **do not add**. No live case exists, and a proposed ADR Kent declines can carry
`deprecated` with a log entry stating why. Additive later if a real case appears.
`active` — **excluded from `decision`**. It has no meaning for a decision record and its presence is
exactly the leakage FR-004 exists to prevent. It stays valid for other doc types (it is in use).
`in_review` — **excluded from `decision`**: `proposed` covers the pre-approval state for an ADR, and
two near-synonyms invite drift.

---

## R-04 — Decision log columns

**Requirement**: fixed enough to parse later, loose enough to record a real erratum (C-003, FR-003).

**Recommendation** — five columns:

| Column | Content | Why |
|---|---|---|
| `Date` | ISO `YYYY-MM-DD` | orders the history; sortable |
| `Type` | controlled vocabulary (below) | the parseable axis |
| `By` | who recorded it | provenance; ADR-0004's log already does this informally |
| `Summary` | one line, prose | the human-readable fact |
| `Refs` | ADR / issue / commit | where authority was actually exercised |

**`Type` vocabulary**: `erratum` (a stated reason is wrong, conclusion stands) · `amendment` (a detail
changed, decision stands) · `superseded-by` (this decision replaced — pairs with `status: superseded`)
· `context` (a referenced fact changed). Deliberately small; extending it is additive.

**Note**: `Type` is the only column that should ever be machine-read. Everything else is for humans.

---

## R-05 — Is the log section mandatory?

**Recommendation**: the section is **required in every ADR**, empty when unused ("*No entries.*").

Reason: an optional section is one an author forgets, and a reader who sees no log cannot distinguish
"nothing has changed" from "this ADR predates the contract". A required-but-empty section makes absence
of change an assertion rather than an ambiguity. It also makes migration verifiable — 9 of 9 must have
it — which is what SC-001 measures.

---

## R-06 — Generated-region marking in `doc-standards.md`

**Problem**: the file is part generated (the status list) and part hand-written prose. The generator
must replace only its own region and be idempotent (NFR-001).

**Recommendation**: HTML-comment sentinels — `<!-- GENERATED:status-list START -->` /
`<!-- GENERATED:status-list END -->`. Invisible in rendered Markdown, unambiguous to a script, and the
generator fails loudly if the sentinels are missing rather than guessing where to write.

---

## R-07 — CI trigger, given spec-kitty merges

**Finding**: kg-automation's CLAUDE.md records that spec-kitty merges create merge commits **directly
to `main`** and do not fire `pull_request` triggers.

**Consequence**: a docs-CI gate triggered only on `pull_request` would silently never run on mission
merges — the exact bypass FR-006 exists to close.

**Recommendation**: trigger the generator-freshness and validation job on `push` to `main` **as well
as** `pull_request`. Confirm against the existing `docs-ci.yml` triggers during implementation rather
than assuming.

---

## Adversarial evidence

No security-impacting dependency decision is made by this mission: zero new dependencies, Python
stdlib only, no network, no credentials, no supply-chain surface (Charter Check, directive 051 — N/A).
The adversarial pass that *does* apply is the mandatory post-plan Codex review, run against
`spec.md` + `plan.md` + `research.md` + `data-model.md` before `/spec-kitty.tasks`. Findings and their
dispositions (`accepted` / `changed` / `deferred_with_rationale`) are appended below.

### Dispositions

*(populated by the post-plan review)*
