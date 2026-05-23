# Implementation Plan: Tasker enrichment JSONL state migration (ADR-0002 Phase 7)

**Branch**: `main` | **Date**: 2026-05-23 | **Spec**: [spec.md](spec.md)
**Mission ID**: `01KSB5XVGW5WRDQFR17JSA52M5`
**Parent ADR**: ADR-0002 (Felix JSONL-canonical state model) — Phase 7 / final

## Summary

Mirror the `scripts/escalation/` module to a new `scripts/enrichment/` module with adapted state vocabulary (`proposed/confirmed/skipped/declined`). Update `/data/services/openclaw/tasker-agent/AGENTS.md` to invoke `record_completion.py` instead of writing Vikunja comments directly. Deploy the missing `task-intelligence` SKILL.md. Operator runs cutover (deploy + reconcile backfill + 3-day soak).

## Technical Context

**Language/Version**: Python 3.13
**Primary Dependencies**: stdlib + existing project tooling (no new deps)
**Storage**: new JSONL at `/data/services/openclaw/state/enrichment/enrichment-history.jsonl`; existing Vikunja comments preserved during soak
**Testing**: pytest with mocked subprocess (vikunja-api), tmp_path fixtures
**Target Platform**: office2 (deployed) + Mac (development)
**Project Type**: single project (additive — new scripts/enrichment/ subpackage)
**Performance Goals**: p95 ≤500ms per record_completion call; reconcile backfill ≤60s for the historic window
**Constraints**: mirror escalation module's API surface (C-003); Tier 2 protocol (Restic snapshot); preserve Vikunja-comment write-through (C-002)
**Scale/Scope**: ~10 enrichment events/month natural traffic (sparse, delegation-driven)

## Charter Check

Skipped (charter absent / governance unresolved — pre-existing tool-registry issue).

## Project Structure

### Documentation (this feature)
```
kitty-specs/tasker-jsonl-migration-01KSB5XV/
├── plan.md          # This file
├── spec.md          # Mission spec
├── research.md      # Phase 0 — 4 decisions
├── data-model.md    # E1 EnrichmentCompletion + state vocabulary
├── contracts/cli.md # record_completion + reconcile CLI surfaces
└── checklists/requirements.md
```

### Source Code (repository root)
```
scripts/enrichment/                    # NEW package (mirrors scripts/escalation/)
├── __init__.py                        # NEW
├── schema.py                          # NEW — EnrichmentCompletion dataclass
├── record_completion.py               # NEW — atomic three-write helper + CLI
├── reconcile_completions.py           # NEW — backfill from Vikunja comments
├── derive_state.py                    # NEW — compute current state from JSONL
└── hard_fail.py                       # NEW (optional — mirrors escalation pattern)

scripts/openclaw/agents/felix-admin-tasker/
└── AGENTS.md                          # MODIFIED — cut to ≤14K + record_completion invocation

scripts/openclaw/helpers/
└── cutover_tasker.py                  # NEW — one-shot operator cutover script

tests/enrichment/                      # NEW
├── __init__.py
├── test_schema.py
├── test_record_completion.py
├── test_reconcile_completions.py
└── test_derive_state.py

docs/design/architecture/
├── data/service-inventory.json        # MODIFIED — register new helpers + tasker AGENTS.md note
├── data/data-flows.json               # MODIFIED — enrichment write paths
├── service-inventory.md               # MODIFIED — match JSON
└── data-flows.md                      # MODIFIED — match JSON

docs/runbooks/tasker-ops.md            # NEW (or MODIFIED if exists) — operator runbook for cutover + soak
```

**Structure Decision**: New `scripts/enrichment/` package mirroring `scripts/escalation/`. AGENTS.md edits in place (same authoritative_surface as #371's habits cut).

## Phase 0 — Research (4 decisions)

- **D1 — Module structure**: mirror `scripts/escalation/` 1:1 (schema → record_completion → reconcile → derive_state). Skip `hard_fail.py` unless escalation's variant is load-bearing (review pattern; can add in plan if needed).
- **D2 — Enrichment state vocabulary**: lock to `proposed/confirmed/skipped/declined` per deployed tasker AGENTS.md (verified during #310 spec-readiness). No mapping needed since this is a fresh subsystem.
- **D3 — AGENTS.md cut targets**: mirror #371's D10 approach — remove the entire `enrich_task` step-by-step prose (defers to task-intelligence SKILL.md) and the `comment write procedure` section (defers to `record_completion.py`). Target: 19,391 → ~12,500-13,500 chars (under 14K with margin).
- **D4 — Cutover script scope**: thin script that (a) deploys task-intelligence SKILL.md (cp from repo to office2 path), (b) runs reconcile_completions to backfill the JSONL, (c) writes a marker file. Mirrors `cutover_362.py`/`cleanup_391.py` structure. Idempotent.

See [research.md](research.md).

## Phase 1 — Design

### Entities

**E1 — EnrichmentCompletion** (JSONL row, frozen dataclass). Per spec Key Entities section. Mirrors `EscalationCompletion` from `scripts/escalation/schema.py`.

No other new entities. Reconcile uses Vikunja comment dicts in-memory; not promoted to a dataclass.

### Contracts

[contracts/cli.md](contracts/cli.md) — CLI surfaces for record_completion + reconcile_completions + cutover_tasker (matches escalation patterns).

## Phase 1 Re-check

No new gates; Tier 2 protocol acknowledged.

## Branch Strategy

- Planning base: `main`
- Merge target: `main`
- branch_matches_target: true

## Open Decisions

None — all locked from spec body + pre-spec probe.
