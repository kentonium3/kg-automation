# Implementation Plan: ADRs as first-class docs — lifecycle-mapped statuses and a generated status taxonomy

**Branch**: `feat/adr-first-class-statuses` | **Date**: 2026-09-18 | **Spec**: `kitty-specs/adr-first-class-statuses-01M2TVSP/spec.md`
**Input**: `kitty-specs/adr-first-class-statuses-01M2TVSP/spec.md` · issue kentonium3/kg-automation#987

**Note**: This template is filled in by the `/spec-kitty.plan` command. See `packs/built-in/missions/mission-steps/software-dev/plan/prompt.md` for the execution workflow.

The planner will not begin until all planning questions have been answered—capture those answers in this document before progressing to later phases.

## Summary

ADRs became persistent decision memory and a cross-session coordination artifact, but their metadata
cannot express their lifecycle: a reader sees `status: approved` and cannot tell that part of the ADR
is dead or that a stated reason is known-wrong. The corrections exist — they are just filed somewhere
the reader never looks. Separately, three files define the doc-status taxonomy and only one is
enforced, so the other two drift silently.

Approach, in three separated roles decided during discovery: **a new ADR** is the only place decisions
are made or reversed; **frontmatter `status`** is the authoritative, machine-readable standing; an
**append-only decision log** at the bottom of each ADR records how that standing was reached and
carries no authority of its own. Enforcement moves to a single generated source so the taxonomy cannot
drift, and status sets become `doc_type`-scoped so ADR states cannot leak onto runbooks.

## Technical Context

<!--
  ACTION REQUIRED: Replace the content in this section with the technical details
  for the project. The structure here is presented in advisory capacity to guide
  the iteration process.

  If multiple developers/agents will work on this mission, add an "Implementation
  Concern Map" section below to decompose architectural intent into IC-## concerns
  before generating tasks.
-->

**Language/Version**: Python 3.12.3 (stdlib only — `json`, `pathlib`, `re`)
**Primary Dependencies**: none added. Existing: `tooling/scripts/validate_docs.py`, `.githooks/pre-commit`, `.github/workflows/docs-ci.yml`
**Storage**: flat files — `docs/design/standards/allowed-values.json` is the single enforced source; schema + narrative are generated artifacts
**Testing**: pytest, under `tests/` (existing layout, e.g. `tests/doc_audit/`). Each FR gets a test; drift and scope violations must be provably detected, not inspected
**Target Platform**: repo-local — developer checkout (office4) + GitHub Actions. No office2 deploy, no runtime service
**Project Type**: single project (repo tooling + documentation)
**Performance Goals**: full-repo `validate_docs.py` scan stays within 1.5x its pre-change baseline (NFR-003)
**Constraints**: ADR bodies above the log are frozen (C-002); the log carries no decision authority (C-003); frontmatter validation must never walk `kitty-specs/`, `.kittify/`, `.agents/`, `.claude/`, `.codex/`, `dist/` (C-001); generated files are build output and never hand-edited (C-007)
**Scale/Scope**: 9 ADRs, ~3 standards files, 1 validator, 1 CI workflow, ~200 validated markdown docs repo-wide

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Charter loaded via `spec-kitty charter context --action plan` (mode: compact; template set
`software-dev-default`; languages: python).

| Gate | Verdict | Note |
|---|---|---|
| DIRECTIVE_006 — deterministic vs stochastic split | **PASS** | Generation, cross-file consistency, and `doc_type` scoping are fully mechanical → helper script + tests. The only judgment work (the taxonomy itself) was settled in discovery, not deferred to runtime. |
| Testing standards | **PASS** | Every FR gets a test. Drift (SC-002), scope leakage (SC-003), and skip-dir coverage (SC-005) are asserted by tests, not inspection. |
| Change-risk taxonomy | **PASS** | Tier 3 (repo logic/tooling) + Tier 4 (docs/metadata). No Tier 0/1/2 surface: no host, network, or application state touched. |
| Deployment constraints | **PASS (N/A)** | Repo-local. No `deploys/queued/` manifest; nothing reaches office2. |
| Rebaseline obligation (#557) | **PASS (N/A)** | No audited surface touched — `tooling/` and `docs/` are not in `audited-surfaces.json`. Merge records "Rebaseline: not required — no audited surface touched". |
| Supply-chain install safety (051) | **PASS (N/A)** | Zero new dependencies; Python stdlib only. |

No violations — Complexity Tracking stays empty.

## Project Structure

### Documentation (this mission)

```
kitty-specs/adr-first-class-statuses-01M2TVSP/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # Phase 2 output (/spec-kitty.tasks — NOT created here)
```

### Source Code (repository root)

```
docs/design/standards/
├── allowed-values.json          # SINGLE ENFORCED SOURCE — doc_type-scoped status sets (IC-01)
├── frontmatter.schema.json      # GENERATED from allowed-values.json (IC-02)
└── doc-standards.md             # status list GENERATED; prose hand-written (IC-02)

docs/design/architecture/adr/
├── README.md                    # status set + immutability/log rules reconciled (IC-04, IC-05)
└── 0001..0009-*.md              # frontmatter migrated + decision logs seeded (IC-05)

docs/INDEX.md                    # per-ADR status text reconciled (IC-05)

tooling/scripts/
├── validate_docs.py             # doc_type-scoped status enforcement (IC-03)
└── generate_doc_standards.py    # NEW — the generator (IC-02)

tests/docs_standards/            # NEW — one test per FR (IC-02, IC-03, IC-04)

.github/workflows/docs-ci.yml    # generator freshness + validation in CI (IC-06)
```

## Complexity Tracking

*Fill ONLY if Charter Check has violations that must be justified*

No Charter Check violations. Section intentionally empty.

## Implementation Concern Map

> **Note**: Implementation concerns are NOT work packages and are NOT executable units.
> `/spec-kitty.tasks` translates these into executable WPs.

### IC-01 — Status taxonomy as doc_type-scoped data

- **Purpose**: Restructure `allowed-values.json` so permitted statuses depend on `doc_type`, and define the ADR lifecycle set (`draft`, `proposed`, `approved`, `superseded`, `deprecated`) with `approved` retained over `accepted` for its stated authority.
- **Relevant requirements**: FR-004, C-004, C-005
- **Affected surfaces**: `docs/design/standards/allowed-values.json`
- **Sequencing/depends-on**: none — this is the root; everything else consumes its shape
- **Risks**: the file is consumed by a live pre-commit hook on every commit repo-wide; a shape change that the validator mis-parses blocks all commits. The loader must be **fail-closed** — today it catches malformed JSON, warns, and continues on built-in fallbacks, which is unsafe once this is the single enforced source (review #7).
- **Post-review correction (#1)**: `doc_type: decision` is **not** ADR-exclusive — RFC #681 (`docs/design/research/felix-workspace-api-vs-gog-681.md`) already uses it, and correctly. `decision` covers ADRs **and** RFCs; their lifecycles are near-identical so one status set serves both, and no discriminator is needed. RFC #681 joins the migration set.

### IC-02 — Generation: one source, derived copies

- **Purpose**: Generate the status list in `frontmatter.schema.json` and `doc-standards.md` from `allowed-values.json`, so the two unenforced copies cannot drift.
- **Relevant requirements**: FR-005, NFR-001, C-007
- **Affected surfaces**: `tooling/scripts/generate_doc_standards.py` (new), `docs/design/standards/frontmatter.schema.json`, `docs/design/standards/doc-standards.md`
- **Sequencing/depends-on**: IC-01
- **Risks**: `doc-standards.md` is part generated, part hand-written prose — the generator must replace only a delimited region and be idempotent (NFR-001).
- **Post-review correction (#2, BLOCKING)**: a flat `status.enum` in `frontmatter.schema.json` **cannot** express `doc_type`-scoped sets — a union would permit `active` on a decision doc; the default would reject `superseded`. The generator must emit **conditional schema** (`if doc_type == decision / then / else`), with tests asserting both the accept and reject paths, and unrelated schema content preserved.
- **Post-review correction (#6)**: the sentinel bootstrap is circular as specified — `doc-standards.md` has no sentinels, the generator must fail when they are absent, and generated files may have no other writer. Needs an explicit one-time bootstrap mode, then strict rules: exactly one ordered start/end pair; reject duplicate, reversed, nested or partial pairs **without writing**.

### IC-03 — Validator: scoped enforcement and honest messages

- **Purpose**: Enforce `doc_type`-scoped status sets with failure messages that name the file, offending value, `doc_type`, and permitted set; and assert that spec-kitty-owned trees are never walked.
- **Relevant requirements**: FR-004, FR-006, NFR-003, NFR-004, C-001
- **Affected surfaces**: `tooling/scripts/validate_docs.py`, `tests/docs_standards/`
- **Sequencing/depends-on**: IC-01
- **Risks**: `SKIP_DIRS` currently protects `kitty-specs/`/`.kittify/` by convention; a widening refactor would silently impose our taxonomy on spec-kitty's generated artifacts. This must become an asserted test (SC-005), not a comment. The validator gates every commit, so a regression is repo-wide.
- **Post-review correction (#10)**: "never walk" is the wrong wording and is **dangerous** — the secret scanner deliberately *does* scan `kitty-specs/` and other committed content, and a process-wide "never walk" test could silently disable that coverage. The rule is **"never frontmatter-validate"**: assert `front_matter()` is never invoked for those paths, while secret scanning continues unchanged.
- **Post-review correction (#5)**: decision-log validation has no owner in the original decomposition. It belongs here — section presence, table shape, `Type` vocabulary, ISO date, and `superseded-by` ⇔ `status: superseded` consistency — with ADR/RFC selection defined and a negative test per check.

### IC-04 — ADR decision-log contract

- **Purpose**: Define the append-only decision log: its fixed columns, that an entry lives in the ADR it is about, that everything above it is frozen, and that it carries no decision authority.
- **Relevant requirements**: FR-001, FR-002, FR-003, FR-009, C-002, C-003
- **Affected surfaces**: `docs/design/architecture/adr/README.md`, ADR template if one exists, `tests/docs_standards/`
- **Sequencing/depends-on**: none (parallel with IC-01)
- **Risks**: this is the concern most likely to be under-specified into prose. The column set must be fixed enough to parse later and loose enough to record a genuine erratum.
- **Post-review correction (#8)**: "Type is the only machine-read column" contradicts validating the date, the table shape, and the status pairing. Split the two ideas: `Type` is the **semantic enum**; `Date`, shape and pairing are **structurally parsed**. Define *both* grammars — the empty form (`*No entries.*`, no table) and the populated form — and state that the empty placeholder may be atomically replaced by header + first row, after which rows are immutable.
- **Post-review correction (#9)**: `docs/_templates/decision.md` is the actual ADR authoring template and was omitted. It emits `doc_type: reference` and has no decision log, so new ADRs would violate the contract on creation. It is an affected surface and needs a regression test over rendered output.

### IC-05 — Corpus migration

- **Purpose**: Move ADRs 0001–0009 onto the contract — frontmatter status under the new set, decision logs seeded from state currently held as prose in `README.md`/`INDEX.md`, and the body `Status:` line dropped going forward (frontmatter rules).
- **Relevant requirements**: FR-007, FR-008, FR-010, SC-001
- **Affected surfaces**: `docs/design/architecture/adr/0001..0009-*.md`, `docs/design/architecture/adr/README.md`, `docs/INDEX.md`
- **Sequencing/depends-on**: IC-01, IC-04
- **Risks**: ADR bodies are frozen, so migration touches frontmatter and appends a log section only. Existing bodies carrying `**Status**: Accepted` will disagree with frontmatter `approved` — resolved by declaring frontmatter authoritative rather than editing frozen text.
- **Post-review correction (#4, BLOCKING)**: a **nine-row migration matrix** is required — target `doc_type`, target status, seeded log rows and their `Type`, and the reconciliation source for each. Implementers must not have to infer standing. The corpus already self-disagrees: **ADR-0003** frontmatter says `draft` while both indexes say "approved 2026-06-09" — resolve explicitly, do not guess. **ADR-0002** stays `approved` (it is not superseded as a whole), so its Q6 row is an **`amendment`**, not `superseded-by`. RFC #681 is a tenth row.
- **Post-review correction (#3, BLOCKING)**: ADR-0004's existing `## ACL changes log` is undispositioned. It holds genuine ADR-0004 history, the **misplaced ADR-0008 erratum**, and standing instructions telling future authors to write there — and `security-posture.md`, `signal-to-doc-map.json` and ADR-0009 all still point at it. Appending a second log would leave two competing logs with traffic flowing to the obsolete one. Required design: preserve the frozen legacy section, append the canonical Decision log, map its history across, **seed the erratum into ADR-0008 where it belongs**, mark the legacy route closed without rewriting it, and update every external pointer.

### IC-06 — CI enforcement

- **Purpose**: Ensure the contract holds when the pre-commit hook is bypassed with `--no-verify`.
- **Relevant requirements**: FR-006, SC-002
- **Affected surfaces**: `.github/workflows/docs-ci.yml`
- **Sequencing/depends-on**: IC-02, IC-03
- **Post-review correction (#12)**: verified — `docs-ci.yml` **already** triggers on `push: [main]`, `pull_request: [main]` and `workflow_dispatch`. There is no trigger defect. IC-06 is therefore "add a generator `--check` step to the existing job, ordered relative to `validate_docs.py`", not a trigger change.
- **Risks**: enabling the freshness gate before sentinels and generated outputs exist would block every subsequent commit — see the migration ordering below.


## Migration ordering (post-review finding #11 — commit-safe sequence)

`allowed-values.json` gates **every commit in this repo** through `.githooks/pre-commit`. Landing these
concerns in the wrong order blocks all work, including the mission's own commits. Required order:

1. **Land the fail-closed taxonomy loader and generator, plus their tests** — behind no gate yet.
   Nothing enforces, nothing can block.
2. **Bootstrap the sentinels and write fresh generated outputs**, using the one-time bootstrap mode.
3. **Enable `doc_type`-scoped status validation** — only now can the validator reject anything new.
4. **Migrate the corpus** (nine ADRs + RFC #681 + `docs/_templates/decision.md`) per the matrix.
5. **Enable the freshness gate** in the hook and the CI `--check` step — last, once every generated
   artifact is already fresh and every document already conforms.

Run the hook-equivalent checks after **every** step, not only at the end. A full-repo
`validate_docs.py` run is the gate between steps.
