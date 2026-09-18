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

Post-plan Codex review run 2026-09-18 (read-only sandbox, no profile) against `spec.md` + `plan.md` +
`research.md` + `data-model.md` + `contracts/`. 13 findings: 4 blocking, 7 material, 2 minor. **Every
checkable factual claim was independently verified before disposition** — all verified true, including
two that contradicted this document. Nothing dropped.

| # | Severity | Finding | Disposition |
|---|---|---|---|
| 1 | blocking | R-01's premise "`decision` is used by nothing" is false | **changed** — see R-01 correction below |
| 2 | blocking | A flat `status.enum` cannot express `doc_type`-scoped sets | **accepted** — generator must emit conditional schema |
| 3 | blocking | ADR-0004's existing `## ACL changes log` is undispositioned | **accepted** — explicit migration design required |
| 4 | blocking | No per-ADR migration matrix; corpus self-disagrees | **accepted** — 9-row matrix required |
| 5 | material | No component owns decision-log validation | **accepted** — assigned to `validate_docs.py` |
| 6 | material | Sentinel bootstrap is circular / impossible as specified | **accepted** — bootstrap mode + strict pair rules |
| 7 | material | Taxonomy loader falls back silently on malformed input | **accepted** — must be fail-closed |
| 8 | material | "Type is the only machine-read column" contradicts validating date/shape/pairing | **accepted** — split semantic enum from structural parse |
| 9 | material | `docs/_templates/decision.md` omitted from affected surfaces | **accepted** — added |
| 10 | material | "never walk" could disable secret scanning | **accepted** — reworded to "never frontmatter-validate" |
| 11 | material | No commit-safe migration ordering | **accepted** — ordering prescribed in plan |
| 12 | minor | The R-07 CI-trigger defect does not exist | **changed** — see R-07 correction below |
| 13 | minor | NFR-004 over-broad | **accepted** — scoped to status-membership failures |

---

## R-01 CORRECTION (post-plan review finding #1)

**What R-01 got wrong.** It asserted `doc_type: decision` "is used by nothing". **False, verified**:
`docs/design/research/felix-workspace-api-vs-gog-681.md` carries `doc_type: decision`. It is RFC #681.

**Why it matters.** R-01's resolution assumed `decision` was free to claim for ADRs exclusively.

**Corrected resolution (Kent, 2026-09-18).** `decision` is **not** ADR-exclusive and does not need to
be. An RFC is a decision document — arguably a *more* correct use of `decision` than the ADRs' current
`reference`. Reclassifying it would make the taxonomy less accurate. ADRs and RFCs are siblings with
near-identical lifecycles (`draft → proposed → approved → superseded / deprecated`), so the scoped
status set serves both unchanged, and **no discriminator is needed at all**.

**Consequence**: the decision-log requirement applies to every `doc_type: decision` document, ADRs and
RFCs alike — an RFC benefits from append-only history for the same reason an ADR does. RFC #681 becomes
a migration target alongside the nine ADRs (status `draft` is already valid; it needs the log section).

**Also surfaced, deliberately out of scope**: `divio-classification.md` documents 11 doc types and
omits `decision`, `design`, `project`, `research` and `standard`; 17 distinct values are in live use; a
Templater expression leaks as a literal value. Same "enforced source + drifting copies" disease one
field over. Filed as **#988**, to be done *after* this mission so it reuses this generator rather than
building a second mechanism.

## R-07 CORRECTION (post-plan review finding #12)

**What R-07 got wrong.** It recommended adding a `push`-to-`main` trigger so mission merges would not
bypass the gate. **Verified**: `.github/workflows/docs-ci.yml` already triggers on `push: [main]`,
`pull_request: [main]` and `workflow_dispatch`. There is no trigger defect.

**Corrected**: the reasoning about spec-kitty merges not firing `pull_request` remains true and worth
recording, but it is already handled. IC-06 becomes "add a generator `--check` step to the existing
job", not "fix the triggers".
