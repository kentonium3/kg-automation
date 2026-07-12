# Implementation Plan: Vikunja Label Taxonomy

**Branch**: `feat/vikunja-label-taxonomy` | **Date**: 2026-07-12 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `kitty-specs/vikunja-label-taxonomy-01KXB8JM/spec.md`

## Summary

Create the canonical 12-label taxonomy (`f:`/`q:`/`t:`/`loe:`) in Vikunja and
delete the three legacy labels, using a single deterministic, idempotent,
tested helper built on the existing stdlib `VikunjaClient`
(`scripts/common/vikunja_client.py`). The taxonomy (names + colors) and the
legacy set are declared as explicit constants matching
`docs/design/vikunja-configuration-design.md`. The helper reconciles the live
label set toward the taxonomy: it paginates the existing labels, creates any
missing taxonomy label with its assigned color, optionally (behind an explicit
flag) deletes the legacy labels, reports a per-label outcome, and emits the
resulting title→id map. Unit tests cover create / skip / delete / idempotent
re-run / failure modes against a mocked client. The destructive live run
(create pass, then a backup-gated delete pass) is a post-merge operational
step, keeping the mission's work packages pure code + tests.

## Technical Context

**Language/Version**: Python 3.12 (office2 runtime; repo targets 3.10+ for tests)
**Primary Dependencies**: standard library only (`urllib`) via `scripts/common/vikunja_client.VikunjaClient` and `scripts/common/vikunja_config`; `pytest` for tests. No new third-party dependency.
**Storage**: none local. State lives in the remote Vikunja instance (labels via its REST API).
**Testing**: `pytest` with a mocked `VikunjaClient` — unit tests make no live API calls. The live label set is verified separately as an operational step (SC-001..003) after merge.
**Target Platform**: Linux (office2) for the live run; tests are platform-agnostic.
**Project Type**: single (one helper module under `scripts/vikunja/` + tests under `tests/`).
**Performance Goals**: a full helper run completes in ≤ 30s under normal Vikunja latency (NFR-003).
**Constraints**: idempotent (re-run = 0 changes, NFR-002); deletions require an explicit opt-in flag (FR-006) and a confirmed Restic backup before running (C-002, Tier-2); label titles + colors are locked to the design doc (C-001); label reads paginate at `per_page` ≤ 50 and mutations reference labels by `id` (FR-009); `area:` labels are not created (C-003).
**Scale/Scope**: 12 labels created, 3 deleted, one Vikunja instance. Blast radius is one helper module + its tests plus a one-shot config run.

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Charter present (`software-dev-default`; directives DIRECTIVE_001/003/010/024/031/033/034; Felix Constitution Directive 6 governs deterministic work).

- **Directive 6 / deterministic work (Felix)** — PASS. Label create/delete is mechanical with no judgment; it lives entirely in a tested helper the operator invokes. No LLM turn.
- **DIRECTIVE_010 Specification Fidelity** — PASS. Label titles and colors are explicit constants asserted against the design doc; a fidelity test guards drift (C-001).
- **DIRECTIVE_024 Locality of Change** — PASS. One new helper + one test module; no change to existing consumers. `vikunja_scope.py` is *not* edited here — moving habit identity onto `t:habit` is #716's config edit.
- **DIRECTIVE_001 Architectural Integrity** — PASS. The helper depends only on the existing `VikunjaClient` boundary; it does not introduce a parallel HTTP path (the older `requests`-based `setup_*.py` scripts are not extended).
- **Change-Risk Taxonomy** — the code is Tier-3 (a script). The **live run's deletion pass is Tier-2** (application state): a recent Restic backup must be confirmed/triggered first. `scripts/vikunja/` is **not** in `audited-surfaces.json`, so **no security-baseline rebaseline** is required.

No violations. Complexity Tracking not needed.

## Project Structure

### Documentation (this mission)

```
kitty-specs/vikunja-label-taxonomy-01KXB8JM/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output — the operational run procedure
├── contracts/           # Phase 1 output — helper CLI contract
└── tasks.md             # Phase 2 output (/spec-kitty.tasks)
```

### Source Code (repository root)

```
scripts/
├── vikunja/
│   └── create_taxonomy_labels.py   # NEW: taxonomy constants + reconcile helper + CLI
└── common/
    └── vikunja_client.py           # REUSED (unchanged): stdlib HTTP client

tests/
└── vikunja/
    └── test_create_taxonomy_labels.py   # NEW: unit tests (mocked client)
```

**Structure Decision**: Single-project layout. The one new production module is
`scripts/vikunja/create_taxonomy_labels.py`; its tests live at
`tests/vikunja/test_create_taxonomy_labels.py`. No existing module is modified —
`VikunjaClient`/`vikunja_config` are consumed as-is. The exact filename is a
planning proposal; `/spec-kitty.tasks` may refine it.

## Implementation Concern Map

> Concerns are not work packages. `/spec-kitty.tasks` translates these into WPs.

### IC-01 — Taxonomy declaration + reconcile helper

- **Purpose**: Declare the 12 taxonomy labels (title + color) and the 3 legacy labels as explicit constants matching the design doc, and implement the idempotent reconcile logic (list existing → create missing with color → optionally delete legacy → emit outcomes + title→id map) on `VikunjaClient`, exposed via a CLI.
- **Relevant requirements**: FR-001, FR-002, FR-003, FR-004, FR-005, FR-006, FR-007, FR-008, FR-009; C-001, C-005.
- **Affected surfaces**: `scripts/vikunja/create_taxonomy_labels.py` (new); consumes `scripts/common/vikunja_client.py`, `scripts/common/vikunja_config.py`.
- **Sequencing/depends-on**: none.
- **Risks**: the id-vs-title gotcha (mutate by id); `per_page` ≤ 50 pagination; deletion is destructive and must be gated behind an explicit flag (default create-only); Vikunja `hex_color` is stored without a leading `#`.

### IC-02 — Automated test suite

- **Purpose**: Prove every reconcile path against a mocked client with zero live calls: create-all-from-empty, skip-existing (partial pre-existing state), delete-legacy, idempotent re-run (0 changes), and failure modes (store unreachable, delete without the flag is a no-op), plus a fidelity assertion that the constants exactly match the design-doc taxonomy.
- **Relevant requirements**: NFR-001, NFR-002; guards FR-001/FR-004/FR-005/FR-006; C-001.
- **Affected surfaces**: `tests/vikunja/test_create_taxonomy_labels.py` (new).
- **Sequencing/depends-on**: IC-01 (imports the helper).
- **Risks**: mocks must mirror the real `VikunjaClient` method surface (`get`/`post`/`delete`, leading-slash paths, empty-body → `{}`), or tests pass while live behavior diverges (the mock-fidelity lesson from prior missions).

### IC-03 — Operational run procedure + verification

- **Purpose**: Document the post-merge live run in `quickstart.md` — confirm/trigger a Restic backup, run the create pass, verify all 12 labels + colors, run the backup-gated delete pass, verify the legacy labels are gone and the taxonomy is the entire label set, run an idempotent re-run (0 changes), and record the title→id map on issue #715.
- **Relevant requirements**: FR-006, FR-008; C-002; SC-001, SC-002, SC-003, SC-004, SC-005.
- **Affected surfaces**: `kitty-specs/.../quickstart.md` (mission doc); the run itself executes on office2 via `ssh office2-claude`. No architecture-data JSON changes (no service/credential/port/data-flow added).
- **Sequencing/depends-on**: IC-01, IC-02.
- **Risks**: running from where `VikunjaClient` defaults resolve (office2 token + base-URL config); Tier-2 backup gate must be honored before any deletion.
