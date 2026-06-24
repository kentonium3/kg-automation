# Implementation Plan: Atomic inbox-file finalize helper

**Branch**: `feat/finalize-inbox-file` | **Date**: 2026-06-24 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `kitty-specs/finalize-inbox-file-01KVXNDC/spec.md`

## Summary

Add `scripts/inbox/finalize_inbox_file.py`: a single deterministic helper the
`felix-admin-capture` agent invokes once per file to perform post-routing
cleanup — set frontmatter `status: processed`, move the file to
`02-Inbox-Processed/`, and append a UTC-dated daily-log line — as one
atomic-per-step, idempotent operation with explicit exit codes and JSON stdout.
It replaces the agent's fragile inline `Edit` + `Bash mv` + log-append sequence.
The helper composes the existing `scripts/inbox/` primitives (`mark_processed.py`,
`append_routing_entry.py`/`routing_log.py`) and the prescan path/atomic-write
patterns rather than duplicating them. This is a Directive-6 deterministic-work
extraction: the entire operation is mechanical and belongs in a helper, not in
LLM-issued tool calls.

## Technical Context

**Language/Version**: Python 3.12 (office2 / Ubuntu 24.04 LTS runtime); 3.10+ compatible for CI
**Primary Dependencies**: Python standard library (`os`, `sys`, `json`, `argparse`, `tempfile`, `pathlib`, `datetime`) + PyYAML (`yaml.safe_load` only, matching `prescan.py`)
**Storage**: Filesystem only — Obsidian vault under `~/second-brain/notes/` (`01-Inbox/`, `02-Inbox-Processed/`); no database
**Testing**: pytest under `tests/inbox/`, reusing `conftest.py` fixtures and the atomic-write/permission pattern established in `tests/inbox/test_atomic_write_perms.py`; vault paths injected via the registry env override so tests run hermetically in a tmp vault
**Target Platform**: Linux (office2); macOS dev parity
**Project Type**: single (Python CLI helper in an existing scripts/ tree)
**Performance Goals**: Not performance-sensitive — one invocation per inbox file at human cadence; correctness/atomicity dominate
**Constraints**: Atomic per step (temp-write+fsync+rename for content; `os.rename` for move); idempotent (exactly one daily-log line per file); zero silent failures (non-zero exit + stderr on any failure); no hardcoded vault paths (resolve from `scripts/vault/paths.json`)
**Scale/Scope**: One new ~150–250 LOC helper + one test module (8 scenarios) + one agent standing-orders edit + one deploy manifest

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Active directives from `charter context --action plan` (compact): DIRECTIVE_001,
003, 010, 024, 031, 033, 034. Assessment:

- **DIRECTIVE_001 (Architectural Integrity)** — PASS. Helper has a single
  responsibility (finalize). It reuses existing inbox primitives and the prescan
  path/atomic-write patterns instead of forking new ones; reconciliation with
  `mark_processed.py`/`routing_log.py` is a Phase-0 research item.
- **DIRECTIVE_003 (Decision Documentation)** — PASS. Material decisions
  (reuse-vs-supersede of existing helpers, log line format, cross-FS rejection)
  captured in `research.md`.
- **DIRECTIVE_010 (Specification Fidelity)** — PASS. Plan maps directly to
  FR-001…FR-010 / NFR-001…004 / C-001…005 with no scope drift.
- **DIRECTIVE_024 / 031 / 033 / 034** — PASS / N/A at plan scope; testing-
  standard and quality-gate directives are satisfied by the pytest suite and CI;
  re-checked post-design.
- **Change-Risk Taxonomy** — Tier 3 (logic/workflow); additive helper, dry-run
  validatable; no Tier-0/1/2 surfaces touched.
- **Rebaseline Obligation (#557)** — the only audited-surface touch is the
  felix-admin-capture `AGENTS.md` standing-orders edit; per the known
  directives-rebaseline gap nothing hashes agent `AGENTS.md` files, so **no
  rebaseline is required** — record that reasoning at merge.

No charter violations → Complexity Tracking left empty.

## Project Structure

### Documentation (this mission)

```
kitty-specs/finalize-inbox-file-01KVXNDC/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (CLI contract)
└── tasks/               # Phase 2 output (/spec-kitty.tasks — NOT created here)
```

### Source Code (repository root)

```
scripts/
├── inbox/
│   ├── finalize_inbox_file.py     # NEW — the finalize helper (this mission)
│   ├── mark_processed.py          # existing — frontmatter status primitive (reuse/reconcile)
│   ├── append_routing_entry.py    # existing — log primitives (reuse/reconcile)
│   ├── routing_log.py             # existing — log primitives (reuse/reconcile)
│   └── prescan.py                 # existing — path-resolution + atomic-write reference pattern
└── vault/
    └── paths.json                 # existing — inbox-root / processed-dir registry (read-only here)

tests/
└── inbox/
    ├── conftest.py                # existing — reuse fixtures
    ├── test_atomic_write_perms.py # existing — atomic-write/perm test pattern to follow
    └── test_finalize_inbox_file.py # NEW — 8-scenario coverage (this mission)

deploys/
└── queued/
    └── finalize-inbox-file.yaml   # NEW — office2 deploy manifest (helper presence + standing-orders cutover)
```

**Structure Decision**: Single-project layout. The helper joins the existing
`scripts/inbox/` family and follows its conventions (registry path resolution,
PyYAML `safe_load`, atomic temp-write+rename, single-line JSON stdout). Tests
join `tests/inbox/`. The office2 cutover (helper availability + standing-orders
edit) flows through a `deploys/queued/` manifest per the deploy discipline.

## Complexity Tracking

*No charter violations — section intentionally empty.*

## Implementation Concern Map

> Concerns are NOT work packages. `/spec-kitty.tasks` translates these into WPs.

### IC-01 — Finalize helper core

- **Purpose**: The deterministic, atomic, idempotent finalize operation (validate → set status → move → log) with exit-code + JSON contract.
- **Relevant requirements**: FR-001…FR-009, NFR-001, NFR-002, NFR-003, C-001, C-003, C-004, C-005
- **Affected surfaces**: `scripts/inbox/finalize_inbox_file.py`; reads `scripts/vault/paths.json`; reuses `mark_processed.py` / `routing_log.py` / prescan path+atomic-write helpers
- **Sequencing/depends-on**: none (foundational)
- **Risks**: reconciling with existing `mark_processed.py`/`routing_log.py` to avoid behavior divergence; correct cross-filesystem (`EXDEV`) rejection; per-step idempotence checks must be race-tolerant

### IC-02 — Test coverage

- **Purpose**: Prove all eight enumerated scenarios incl. atomicity, idempotency, and error surfacing in a hermetic tmp vault.
- **Relevant requirements**: NFR-004 + acceptance scenarios 1–8; verifies FR/NFR/C behavior
- **Affected surfaces**: `tests/inbox/test_finalize_inbox_file.py`; reuse `tests/inbox/conftest.py` + `test_atomic_write_perms.py` patterns
- **Sequencing/depends-on**: IC-01 (test-first acceptable per testing standards)
- **Risks**: simulating permission-denied and cross-FS rename portably (macOS dev vs Linux CI); asserting no-duplicate-log-line on re-invocation

### IC-03 — Agent cutover + office2 deploy

- **Purpose**: Switch felix-admin-capture to call the helper as the single finalize step (with exit-code handling) and deliver the helper + standing-orders change to office2.
- **Relevant requirements**: FR-010, C-002
- **Affected surfaces**: `/home/claude/.openclaw/agents/felix-admin-capture/AGENTS.md` (standing orders); `deploys/queued/finalize-inbox-file.yaml`
- **Sequencing/depends-on**: IC-01 (helper must exist and be on office2 before the standing-orders cutover references it)
- **Risks**: standing-orders wording must define exit-1 vs exit-2 handling unambiguously; AGENTS.md is an audited surface but unhashed → no rebaseline (record at merge); manifest must make the helper present on office2 before cutover
