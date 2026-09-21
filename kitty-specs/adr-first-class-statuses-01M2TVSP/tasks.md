# Tasks: ADRs as first-class docs — lifecycle-mapped statuses and a generated status taxonomy

**Mission**: adr-first-class-statuses-01M2TVSP · **Branch**: `feat/adr-first-class-statuses` · **Issue**: #987

Subtask completion is **event-sourced** — record with
`spec-kitty agent tasks mark-status T0xx --status done`. The rows below are reference rows, not checkboxes.

## Ordering is a safety property, not a preference

`docs/design/standards/allowed-values.json` gates **every commit in this repo** through
`.githooks/pre-commit`. WP06 (enable the gates) is deliberately last: turning on a freshness check
before the generated outputs exist would block every subsequent commit, including this mission's own.
Do not reorder.

**WP01 → WP02 → WP03 → (WP04 ∥ WP05) → WP06**

## Subtask Index

| ID | Description | WP | Parallel |
|----|-------------|----|----------|
| T001 | Add `status_by_doc_type` with the `decision` status set to allowed-values.json | WP01 | |
| T002 | New `doc_taxonomy.py` — shared loader for the status taxonomy | WP01 | |
| T003 | Make the loader fail-closed: no silent fallback on missing/malformed input | WP01 | |
| T004 | Tests: valid load, plus a negative test per malformed shape | WP01 | [P] |
| T005 | Confirm repo-wide validation still passes (no behaviour change yet) | WP01 | |
| T006 | `generate_doc_standards.py` skeleton with default and `--check` modes | WP02 | |
| T007 | Emit **conditional** JSON Schema (doc_type-dependent status enum) | WP02 | |
| T008 | Sentinel bootstrap mode plus strict pair validation | WP02 | |
| T009 | Region-scoped write into doc-standards.md | WP02 | |
| T010 | Tests: idempotency, determinism, sentinel edge cases, prose preservation | WP02 | [P] |
| T011 | Bootstrap the sentinels and generate fresh outputs | WP02 | |
| T012 | doc_type-scoped status enforcement via the shared loader | WP03 | |
| T013 | Failure messages naming file, value, doc_type and permitted set | WP03 | |
| T014 | Decision-log validation: presence, shape, Type vocabulary, ISO date, superseded pairing | WP03 | |
| T015 | Assert frontmatter validation never reaches spec-kitty trees, secret scanning intact | WP03 | |
| T016 | Negative test per promised check | WP03 | [P] |
| T017 | Full-repo validation run green | WP03 | |
| T018 | Fix `docs/_templates/decision.md` to emit the new contract | WP04 | |
| T019 | Regression test over rendered template output | WP04 | [P] |
| T020 | Migrate nine ADR frontmatters per the migration matrix | WP05 | |
| T021 | Append decision logs; seed ADR-0002, ADR-0003, ADR-0008 entries | WP05 | |
| T022 | ADR-0004 special case: preserve legacy log, append canonical, relocate the erratum | WP05 | |
| T023 | Update the three external pointers to the canonical log | WP05 | |
| T024 | RFC #681 decision log section | WP05 | |
| T025 | Reconcile ADR README doctrine and both index tables | WP05 | |
| T026 | Add generator `--check` to the pre-commit hook | WP06 | |
| T027 | Add generator `--check` step to docs-ci.yml | WP06 | |
| T028 | Verify the full gate green and the suite floor held | WP06 | |

## Work Packages

### WP01 — Taxonomy data and fail-closed loader
**Prompt**: `tasks/WP01-taxonomy-loader.md` · **Priority**: P1 · **Depends on**: none
**Goal**: make `allowed-values.json` express doc_type-scoped status sets, and give every consumer one
loader that refuses to guess.
**Independent test**: the loader accepts the new shape and rejects each malformed shape; repo-wide
validation still passes unchanged.
Subtasks: T001 T002 T003 T004 T005
**Risk**: this file gates every commit. A parse regression blocks all work — keep the default `status`
key readable by the current code until WP03 switches consumers over.

### WP02 — Generator with conditional schema and sentinel bootstrap
**Prompt**: `tasks/WP02-generator.md` · **Priority**: P1 · **Depends on**: WP01
**Goal**: derive both unenforced copies from the enforced source so they cannot drift.
**Independent test**: run twice, second run stages no diff; `--check` fails on a hand-mutated copy.
Subtasks: T006 T007 T008 T009 T010 T011
**Risk**: the flat `status.enum` cannot express scoped sets (review #2) — conditional schema is
mandatory, not optional. Bootstrap is circular unless T008 lands first (review #6).

### WP03 — Scoped validation and decision-log checks
**Prompt**: `tasks/WP03-validator.md` · **Priority**: P1 · **Depends on**: WP01, WP02
**Goal**: enforce the contract with messages an author can act on, without widening what gets walked.
**Independent test**: an ADR-only status on a runbook is rejected naming both sets; a full-repo run is green.
Subtasks: T012 T013 T014 T015 T016 T017
**Risk**: "never walk" is the wrong rule — the secret scanner deliberately scans `kitty-specs/`.
T015 asserts *never frontmatter-validate* and must prove secret scanning survives (review #10).

### WP04 — ADR authoring template
**Prompt**: `tasks/WP04-template.md` · **Priority**: P2 · **Depends on**: WP01
**Goal**: new ADRs conform at creation instead of being migrated later.
**Independent test**: rendering the template yields `doc_type: decision`, a valid status, and an empty log.
Subtasks: T018 T019
**Risk**: the template was missed entirely in the first decomposition (review #9); it currently emits
`doc_type: reference` and no log.

### WP05 — Corpus migration
**Prompt**: `tasks/WP05-corpus-migration.md` · **Priority**: P1 · **Depends on**: WP01, WP04
**Goal**: every decision document states its own standing and history. This is SC-001.
**Independent test**: for all eleven rows, standing and history derive from that document alone.
Subtasks: T020 T021 T022 T023 T024 T025
**Risk**: ADR-0004 already has a competing log and three live files still point at it. Appending a
second log without closing the old route recreates the exact defect this mission fixes (review #3).

### WP06 — Enable the gates
**Prompt**: `tasks/WP06-enable-gates.md` · **Priority**: P1 · **Depends on**: WP02, WP03, WP04, WP05
**Goal**: the contract survives `--no-verify`.
**Independent test**: a stale generated file fails CI; the suite floor is held.
Subtasks: T026 T027 T028
**Risk**: **must be last.** Enabling before outputs exist blocks every commit. Also edits
`.github/workflows/` — flagged for the operator, see the WP prompt.
