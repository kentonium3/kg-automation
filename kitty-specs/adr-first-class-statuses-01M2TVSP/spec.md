# Mission Specification: ADRs as first-class docs — lifecycle-mapped statuses and a generated status taxonomy

**Mission Branch**: `feat/adr-first-class-statuses`
**Created**: 2026-09-18
**Status**: Draft
**Input**: kentonium3/kg-automation#987, plus the discovery interview recorded in `decisions/` (DM-01M2TVTS, DM-01M2TX8V, DM-01M2TY0N).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A reader learns an ADR's standing without being misled (Priority: P1)

An agent session or Kent opens an ADR to inherit a constraint rather than re-derive it. The ADR tells
them two things in the document itself: its **current standing** (is this safe to act on?) and **how it
got there** (what has been corrected, amended, or superseded since approval). They never have to open a
second document to find out that part of what they just read is known-wrong.

**Why this priority**: this is the defect, observed. On 2026-09-18 an agent session read ADR-0008, hit
the `RunSSH: false` reasoning, and reported it to Kent as a fresh finding. It had been recorded as an
erratum on 2026-08-29 — in **ADR-0004's** log. The correction existed and did not reach the reader.
ADRs are now persistent decision memory and a coordination artifact between sessions, so a record that
misstates its own standing is a correctness problem, not a tidiness one.

**Independent Test**: take the nine live ADRs; for each, confirm standing and full amendment history
are derivable from that file alone. ADR-0008 must surface its own erratum; ADR-0002 must surface that
Q6 was superseded by ADR-0007.

### User Story 2 - An author records a change in standing without editing a frozen decision (Priority: P2)

Something changes about an approved ADR — a cited fact goes stale, a sub-decision is superseded by a
newer ADR, a stated reason turns out to be wrong. The author appends one row to that ADR's decision log
and changes its frontmatter status if the standing actually moved. They do not edit the frozen text,
and they do not need a whole new ADR for a correction that leaves the decision intact.

**Why this priority**: it is what makes User Story 1 sustainable. Without an append path, corrections
either go to the wrong document (the observed failure) or force a successor ADR for changes that decide
nothing, churning the ADR map.

**Independent Test**: append an erratum row to an approved ADR; validation passes, the frozen body is
unchanged, and the entry is visible to a reader of that ADR.

### User Story 3 - A maintainer adds a status value and nothing drifts (Priority: P3)

A maintainer adds or renames a status in the one enforced source. The schema and the narrative
documentation update from it; a stale copy fails the build rather than sitting wrong indefinitely.

**Why this priority**: it is the root-cause fix for how this mission started. Valuable, but the reader
is not harmed while it is pending — the corpus migration is.

**Independent Test**: desynchronise the generated copies deliberately; CI fails and names the drift.

### Edge Cases

- **A log entry that would change what the ADR decides.** Impossible by construction — the log carries
  no decision authority. Decisions are made only in ADRs. Nothing needs to detect this, but the ADR
  README must state it so authors do not try.
- **An ADR-only status applied to a runbook**, or `active` applied to an ADR. Must be rejected with a
  message naming the `doc_type` and its permitted set.
- **An ADR with no log entries yet** — the common case. An empty log section is valid, not a finding.
- **`--no-verify` bypasses the pre-commit hook.** CI must catch what the hook would have.
- **spec-kitty's own generated artifacts.** `kitty-specs/` and `.kittify/` carry frontmatter written by
  spec-kitty, on its own contract. Our validator must never walk them.
- **Two files disagree after a hand edit** to a generated copy. The generated copies must be treated as
  build output, not editable source.

## Requirements *(mandatory)*

### Functional Requirements

| ID | Title | User Story | Priority | Status |
|----|-------|------------|----------|--------|
| FR-001 | ADR decision log section | As a reader of an ADR, I want an append-only log at the bottom of that ADR so that I see every correction and change of standing without opening another document. | High | Open |
| FR-002 | Log entry belongs to the ADR it is about | As a reader, I want an entry about ADR-X to live in ADR-X so that a correction reaches whoever reads the thing it corrects. | High | Open |
| FR-003 | Fixed log columns | As a maintainer, I want the log table to have defined columns so that it stays parseable instead of drifting into free prose. | High | Open |
| FR-004 | doc_type-scoped status sets | As a maintainer, I want permitted statuses to depend on `doc_type` so that ADR statuses cannot leak onto runbooks and `active` cannot be applied to an ADR. | High | Open |
| FR-005 | Single enforced source, generated copies | As a maintainer, I want the schema and narrative status lists generated from `allowed-values.json` so that hand-maintained copies cannot drift. | High | Open |
| FR-006 | Enforcement in CI, not only pre-commit | As a maintainer, I want drift and status violations caught in CI so that `--no-verify` does not bypass the contract. | High | Open |
| FR-007 | Frontmatter is authoritative for standing | As a reader, I want one authoritative status field so that body text and metadata cannot disagree; new ADRs carry no body `Status:` line. | High | Open |
| FR-008 | Migrate ADRs 0001-0009 | As a reader, I want existing ADRs moved onto the new contract, with state currently held as prose in `README.md`/`INDEX.md` seeded into each ADR's own log. | High | Open |
| FR-009 | Reconcile the ADR README | As an author, I want the ADR README's documented status set and immutability rule to match reality, including that the log is append-only and carries no decision authority. | Medium | Open |
| FR-010 | Seed the two known log entries | As a reader of ADR-0002 and ADR-0008, I want their existing amendments recorded in their own logs (Q6 superseded by ADR-0007; the erratum recorded in ADR-0004's ACL log). | Medium | Open |

### Non-Functional Requirements

| ID | Title | Requirement | Category | Priority | Status |
|----|-------|-------------|----------|----------|--------|
| NFR-001 | Generator determinism | Running the generator twice on unchanged input produces byte-identical output; a second run stages no diff. | Reliability | High | Open |
| NFR-002 | No validation regression | After migration, a full-repo `validate_docs.py` run reports 0 findings across every non-skipped doc. | Reliability | High | Open |
| NFR-003 | Validator runtime | Full-repo scan wall time stays within 1.5x the pre-change baseline, measured on office4. | Performance | Medium | Open |
| NFR-004 | Actionable failure messages | Every new validation failure names the file, the offending value, the `doc_type`, and the permitted set for that `doc_type`. | Usability | High | Open |

### Constraints

| ID | Title | Constraint | Category | Priority | Status |
|----|-------|------------|----------|----------|--------|
| C-001 | Never validate spec-kitty-owned trees | Frontmatter validation must not walk `kitty-specs/`, `.kittify/`, `.agents/`, `.claude/`, `.codex/` or `dist/`. Imposing our taxonomy on spec-kitty's generated artifacts is out of bounds. | Technical | High | Open |
| C-002 | ADR decisions stay frozen | Everything above the decision log in an approved ADR is immutable. The log is append-only and may not alter or contradict the frozen text. | Technical | High | Open |
| C-003 | The log carries no decision authority | Decisions are made and reversed only by ADRs. The log records history; `status` carries standing. | Technical | High | Open |
| C-004 | No partial-supersession state | `partially_superseded` must not exist. An ADR is wholly binding or its standing has moved; partial changes are log entries. | Technical | High | Open |
| C-005 | `approved`, not `accepted` | Retain `approved` — it carries a stated authority, which can matter. | Business | Medium | Open |
| C-006 | Repo-local, no deploy | Documentation and repo tooling only. No `deploys/queued/` manifest, no office2 change. | Technical | High | Open |
| C-007 | Generated files are build output | The generated schema and narrative status lists must not be hand-edited; the generator is the only writer. | Technical | Medium | Open |

### Key Entities

- **Doc status**: the authoritative standing of a document, in frontmatter, drawn from a set permitted
  for its `doc_type`. The single machine-readable answer to "is this safe to act on?"
- **Decision log entry**: one append-only row in the ADR it concerns, recording a change of standing or
  a correction. Carries no authority; records that authority was exercised elsewhere.
- **ADR**: a decision record whose body is frozen at approval, carrying its own decision log.
- **Status taxonomy source**: `docs/design/standards/allowed-values.json` — the one enforced
  definition, from which every other representation is generated.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For all 9 live ADRs, current standing and complete amendment history are derivable from
  that ADR alone — 0 of 9 require opening a second file. Verified against the two known cases
  (ADR-0002 Q6, ADR-0008 erratum).
- **SC-002**: Deliberately desynchronising a generated copy from `allowed-values.json` fails CI on
  100% of attempts, with a message naming the drifted file.
- **SC-003**: Applying an ADR-only status to a non-ADR doc, or `active` to an ADR, is rejected 100% of
  the time with a message naming the `doc_type` and its permitted set.
- **SC-004**: A full-repo validation run after migration reports 0 findings.
- **SC-005**: 0 files under `kitty-specs/`, `.kittify/`, `.agents/`, `.claude/`, `.codex/` or `dist/`
  are frontmatter-validated, asserted by a test rather than by inspection.
- **SC-006**: Running the generator twice produces no staged diff on the second run.
