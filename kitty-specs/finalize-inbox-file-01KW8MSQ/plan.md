# Implementation Plan: Atomic in-place inbox finalize (mark_processed hardening)

**Branch**: `feat/finalize-inbox-file-v2` | **Date**: 2026-06-28 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `kitty-specs/finalize-inbox-file-01KW8MSQ/spec.md`

## Summary

Close the silent-finalize-failure class by hardening the **existing**
`scripts/inbox/mark_processed.py` (already wired into `felix-admin-capture`
Step 5c) so a failed atomic write is **surfaced**, not silent: add a filesystem-
error exit path (**exit 2** + `OSError` on stderr), a single-line JSON success
signal on **stdout**, and inbox-root validation. Add explicit exit-code handling
to the agent's Step 5c standing orders. Finalize stays **in place** — the note
keeps `status: processed` in `01-Inbox/`; `prescan.py` owns the 7-day archive.

## Technical Context

**Language/Version**: Python 3.12 (office2 runtime; 3.10+ compatible — the helper
uses `from __future__ import annotations` + PEP 604 unions)
**Primary Dependencies**: Python standard library only (`argparse`, `os`, `re`,
`stat`, `tempfile`, `json`, `datetime`, `pathlib`). **No new dependencies** (NFR-001).
**Storage**: Filesystem — Obsidian vault `01-Inbox/` markdown notes; inbox root
resolved from `scripts/vault/paths.json` (shared registry with `prescan.py`).
**Testing**: pytest; reuse the inbox/prescan test fixtures and the
`PRESCAN_REGISTRY_PATH` hermetic-override pattern; perm-denied test via `os.chmod`
on a tmp note (skip-guarded where the runner is root).
**Target Platform**: Linux (office2 Ubuntu 24.04 LTS) + macOS dev parity.
**Project Type**: single (helper library under `scripts/inbox/`).
**Performance Goals**: N/A — one note per agent tick (handful/day); sub-second.
**Constraints**: stdlib-only; atomic mode-preserving write; idempotent; **in place,
no move**; `04-Growth/_private/` never touched; invoked via `-m` module form.
**Scale/Scope**: one file changed (`mark_processed.py`) + its tests + the Step 5c
standing-orders edit + the `agent-prompt-changed` doc set. Surgical.

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **DIRECTIVE_001 (Architectural Integrity)** — PASS. The helper remains a single
  focused finalize primitive; no new component or boundary is introduced.
- **DIRECTIVE_003 (Decision Documentation)** — PASS. The two resolved forks and the
  fidelity deviations are recorded (spec A1–A4; design tracer).
- **DIRECTIVE_010 (Specification Fidelity)** — PASS. Deviations from the issue's
  literal "new `finalize_inbox_file.py`" title and its stale "inline `Edit`" framing
  are explicitly documented (spec A1/A2).
- **DIRECTIVE_024 (Locality of Change)** — PASS. Blast radius confined to
  `mark_processed.py`, its tests, Step 5c, and the doc-map targets.
- **DIRECTIVE_031/033/034 + project DIR-001..005** — no conflicts; Tier-3 logic
  change, additive exit code, no infra/credential/topology impact.
- **Engineering-principles Directive 6 (deterministic vs stochastic)** — the
  finalize is deterministic → lives in a helper the agent invokes (already true;
  this mission hardens it). PASS.

No charter violations → Complexity Tracking is empty.

## Project Structure

### Documentation (this mission)

```
kitty-specs/finalize-inbox-file-01KW8MSQ/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (CLI contract)
└── traces/              # #2095 tracers (seeded at specify)
```

### Source Code (repository root)

```
scripts/inbox/
├── mark_processed.py        # MODIFIED — exit-2 fs-error path, JSON stdout, inbox-root validation
└── prescan.py               # READ ONLY — reuse resolve_registry()/paths.json + JSON convention

scripts/vault/
└── paths.json               # READ ONLY — inbox-root source of truth

scripts/openclaw/agents/felix-admin-capture/
└── AGENTS.md                # MODIFIED — Step 5c exit-code handling (deploys via pull-based sync → inbox-agent)

tests/inbox/                 # MODIFIED/ADDED — contract coverage (happy/idempotent/validation/fs-fail/private)

docs/design/architecture/data/service-inventory.json   # MODIFIED — felix-admin-capture finalize note
docs/design/architecture/service-inventory.md          # MODIFIED — narrative counterpart
docs/design/architecture/data/audited-surfaces.json    # REVIEW — agent-prompt surface mapping current?
docs/runbooks/openclaw-agent-setup.md                  # REVIEW — per-agent deploy expectations
docs/runbooks/agent-prompt-sync-ops.md                 # REVIEW — auto-sync pipeline
```

**Structure Decision**: Single-project helper-library layout. The change is an
in-place hardening of one existing module plus its tests, one agent-prompt edit,
and the doc-map-required architecture/runbook updates.

## Complexity Tracking

*(none — Charter Check passed with no violations)*

## Implementation Concern Map

> Concerns are NOT work packages. `/spec-kitty.tasks` translates these into WPs.

### IC-01 — Helper error-surface hardening

- **Purpose**: Make a failed finalize non-silent and machine-confirmable by adding
  the exit-2 filesystem-error path, the single-line JSON stdout success signal, and
  inbox-root validation to `mark_processed.py`, without weakening its existing
  atomicity/idempotency/round-trip guarantees.
- **Relevant requirements**: FR-001, FR-002, FR-003, FR-004; NFR-001..004; C-002, C-003.
- **Affected surfaces**: `scripts/inbox/mark_processed.py` (reuses
  `prescan.resolve_registry()` + `paths.json`).
- **Sequencing/depends-on**: none (foundational).
- **Risks**: exit-code reconciliation must stay additive (2 added, 3 retained);
  the inbox-root check must not reject the legitimate `01-Inbox/` path; the
  perm-denied path must catch `OSError` from `_atomic_write` (including the
  fsync/replace window) and leave the original uncorrupted.

### IC-02 — Contract test coverage

- **Purpose**: Prove all five outcomes (happy, idempotent, validation-fail,
  fs-fail, private-refusal) against the 0/1/2/3 contract and the stdout/stderr
  split, including the NFR-003 "original uncorrupted after exit 2" assertion.
- **Relevant requirements**: SC-001..004; FR-001..004; NFR-003, NFR-004.
- **Affected surfaces**: `tests/inbox/` (reuse `PRESCAN_REGISTRY_PATH` hermetic
  fixtures; perm-denied test skip-guarded under root).
- **Sequencing/depends-on**: IC-01 (tests the hardened helper).
- **Risks**: perm-denied test portability (root runner can write through 0o444 —
  guard with a skip); ensuring the JSON-stdout assertion is exact (single line).

### IC-03 — Standing-orders cutover + required doc updates

- **Purpose**: Give Step 5c explicit exit-code handling so a non-zero finalize is
  surfaced/escalated (not silently continued), retaining the "do NOT move; preserve
  in `01-Inbox/`" invariant; and land the `agent-prompt-changed` doc-map updates.
- **Relevant requirements**: FR-005, FR-006; C-001, C-004.
- **Affected surfaces**: `scripts/openclaw/agents/felix-admin-capture/AGENTS.md`
  (Step 5c); `service-inventory.json`/`.md`; `audited-surfaces.json`;
  `openclaw-agent-setup.md`; `agent-prompt-sync-ops.md`.
- **Sequencing/depends-on**: IC-01 (the exit-code semantics the orders reference
  must exist first); doc updates can proceed in parallel once the contract is fixed.
- **Risks**: deploy-path accuracy (pull-based sync, slug→`inbox-agent`, NOT a
  felix-deployer manifest); rebaseline note must read "not required" per gap #621;
  must not re-introduce a `02-Inbox-Processed/` per-file log (C-001).
