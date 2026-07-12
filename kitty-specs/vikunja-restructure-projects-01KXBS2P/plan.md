# Implementation Plan: Vikunja Project Restructure

**Branch**: `feat/vikunja-restructure-projects` | **Date**: 2026-07-12 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `kitty-specs/vikunja-restructure-projects-01KXBS2P/spec.md`

## Summary

Add an idempotent Vikunja reconciliation helper (`scripts/vikunja/`) that
establishes the canonical topic-project structure and removes the legacy saved
filters, run with the kent-owned API token. Additive-only: it creates missing
projects, verifies `Inbox`, and deletes the five legacy saved filters; it never
deletes a task-bearing project (that is #717). Built on the canonical stdlib
`VikunjaClient`, mirroring the #715 taxonomy-reconcile helper. Destructive
filter deletion is gated behind an explicit backup-confirmation flag (Tier-2).

## Technical Context

**Language/Version**: Python 3.12 (office2 runtime; Mac dev). Standard-library only in the helper.
**Primary Dependencies**: `scripts/common/vikunja_client.py` (stdlib `urllib` HTTP client), `scripts/common/vikunja_config.py` (base-URL resolution); `pytest` for tests. No third-party runtime deps.
**Storage**: None local. Mutates live Vikunja state (projects, saved filters) via the REST API.
**Testing**: `pytest` with the `VikunjaClient` HTTP layer mocked (repo convention; no live-probe test modes — quirks are documented in `research.md`, not exercised as integration tests). Coverage gate ≥ 90% for the helper module.
**Target Platform**: Vikunja v0.24.6 on office2 (Ubuntu 24.04 LTS), reached over Tailscale HTTPS; helper invoked by a Felix operator as `python3 -m scripts.vikunja.<module>`.
**Project Type**: single (one helper module + one test module + one design-doc edit).
**Performance Goals**: N/A — one-shot admin reconciliation, completes in a few seconds against ~13 projects / ~5 filters.
**Constraints**: idempotent (zero mutating calls on a converged second run); fail-loud on any API error; kent-owned token only; no project deletions; destructive filter delete gated on `--backup-confirmed` (Tier-2 Restic precondition).
**Scale/Scope**: ~13 existing projects, 5 legacy filters, 5 new projects to create. Single module.

## Charter Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

Charter present (`.kittify/doctrine`). Relevant governance:

- **DIRECTIVE_024 (Locality of Change)** — PASS. One new helper + one test module + one design-doc update. No changes to unrelated surfaces.
- **DIRECTIVE_001 (Architectural Integrity)** — PASS. Reuses the canonical `VikunjaClient`; no parallel HTTP path, no new client. Config seam (`vikunja_config`) reused.
- **DIRECTIVE_010 (Spec Fidelity)** — the helper implements FR-001..012 exactly; out-of-scope items (project deletes, migration, filter creation) are explicitly excluded.
- **DIRECTIVE_003 (Decision Documentation)** — the two-token model, the additive-only boundary, and the filter-id derivation are recorded here + in `research.md`.
- **Helper/library/skill decision (Engineering Principles / Directive 6)** — this is a **helper script**: deterministic, operator-invoked, single responsibility. No LLM/judgment involved → scripts-first is correct.
- **Change-Risk Taxonomy** — **Tier 2 (Application/State)**: mutates Vikunja projects/filters. Confirm a recent Restic backup before the destructive (filter-delete) pass; gated by `--backup-confirmed`. Project creation is additive/low-risk.
- **Rebaseline Obligation** — no audited surface touched (`scripts/vikunja/**` and `docs/**` are not in `audited-surfaces.json`; the `vikunja-api-kent` credential was already registered in #715). Expected: `Rebaseline: not required`.
- **Architecture docs** — update `docs/design/vikunja-configuration-design.md` (design narrative). No `service-inventory.json` / `credential-manifest.json` change (no new service or credential).

No violations → Complexity Tracking not required.

## Project Structure

### Documentation (this mission)

```
kitty-specs/vikunja-restructure-projects-01KXBS2P/
├── plan.md              # This file
├── research.md          # Phase 0 output — filter-id derivation, client patterns, v0.24.6 quirks
├── data-model.md        # Phase 1 output — Project / SavedFilter entities + reconcile model
├── quickstart.md        # Phase 1 output — how to run + verify
├── contracts/           # Phase 1 output — Vikunja API surface used
└── tasks.md             # Phase 2 (/spec-kitty.tasks) — NOT created here
```

### Source Code (repository root)

```
scripts/
├── common/
│   ├── vikunja_client.py     # (existing) canonical stdlib client — reused, not modified
│   └── vikunja_config.py     # (existing) base-URL resolution — reused
└── vikunja/
    └── reconcile_projects.py # (new) idempotent project + legacy-filter reconciliation helper

tests/
└── vikunja/
    └── test_reconcile_projects.py  # (new) unit tests, VikunjaClient HTTP mocked

docs/design/
└── vikunja-configuration-design.md # (edit) Project Structure section reconciled to final state
```

**Structure Decision**: Single-project layout. The helper is one module under
`scripts/vikunja/` (peer of `create_taxonomy_labels.py` from #715), tested by a
peer module under `tests/vikunja/`, plus one narrative doc edit. No new
package, service, or credential.

## Implementation Concern Map

> Concerns, not work packages. `/spec-kitty.tasks` decides WP decomposition.

### IC-01 — Project reconciliation

- **Purpose**: Idempotently create the missing topic projects (with the `Clients` parent/child hierarchy) and verify `Inbox`, all as kent.
- **Relevant requirements**: FR-001, FR-002, FR-003, FR-004, FR-005, FR-006, FR-008, FR-009, FR-012.
- **Affected surfaces**: `scripts/vikunja/reconcile_projects.py`, `tests/vikunja/test_reconcile_projects.py`.
- **Sequencing/depends-on**: none.
- **Risks**: parent/child ordering (create `Clients` before its sub-projects; resolve parent id at runtime); match projects by `title` to avoid duplicates; handle JSON `null` for empty collections (#715 quirk).

### IC-02 — Legacy saved-filter removal

- **Purpose**: Delete the five legacy saved filters, gated on backup confirmation, leaving the native `Favorites` view intact.
- **Relevant requirements**: FR-007, FR-010 (do-no-harm), NFR-002, NFR-004, C-005, C-006.
- **Affected surfaces**: same helper + tests.
- **Sequencing/depends-on**: independent of IC-01 (can run in either order); shares the CLI entrypoint.
- **Risks**: no `/filters` list endpoint on v0.24.6 → derive filter ids from negative-id pseudo-projects (`filter_id = -pseudo_id - 1`); never touch `Favorites` (`-1`, no backing filter id); refuse the pass without `--backup-confirmed`.

### IC-03 — Documentation reconciliation

- **Purpose**: Update the authoritative design doc so its Project Structure section matches the final agreed structure and corrects the pseudo-view vs native-filter description.
- **Relevant requirements**: FR-011, SC-006.
- **Affected surfaces**: `docs/design/vikunja-configuration-design.md`.
- **Sequencing/depends-on**: none (documentation).
- **Risks**: keep consistent with the live structure the helper produces (retained projects: Metal Casework, CT-90day, Habits; created: Felix / kg-automation, Clients+2, Personal).
