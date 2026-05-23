# Tasks: Tasker enrichment JSONL state migration

**Mission**: `tasker-jsonl-migration-01KSB5XV`
**Branch**: `main`
**Generated**: 2026-05-23

3 work packages, sequential in lane-a.

## Subtask Index

| ID | Description | WP |
|---|---|---|
| T001 | schema.py — EnrichmentCompletion dataclass + constants (mirror escalation/schema.py) | WP01 |
| T002 | record_completion.py — atomic three-write contract + CLI (mirror escalation/record_completion.py) | WP01 |
| T003 | Tests for schema + record_completion (≥85% coverage; mock subprocess for Vikunja, tmp_path for JSONL) | WP01 |
| T004 | reconcile_completions.py — backfill from Vikunja comments with disambiguation (mirror escalation/reconcile_completions.py) | WP02 |
| T005 | derive_state.py — compute current state from JSONL (mirror escalation/derive_state.py) | WP02 |
| T006 | Tests for reconcile + derive_state (≥85%; including disambiguation edge cases) | WP02 |
| T007 | tasker AGENTS.md cut: 19,391 → ≤14,000 chars per research D3; replace direct comment writes with record_completion invocation | WP03 |
| T008 | cutover_tasker.py — one-shot deploy script (mirror cutover_362.py); deploy SKILL.md + AGENTS.md, run reconcile, write marker | WP03 |
| T009 | Tests for cutover_tasker (≥85%; mock subprocess + filesystem) | WP03 |
| T010 | Architecture docs + runbook: service-inventory.json, data-flows.json, markdown views, docs/runbooks/tasker-ops.md (create or update) | WP03 |

## Dependency Graph

```
WP01 (schema + record_completion) → WP02 (reconcile + derive_state) → WP03 (AGENTS.md + cutover + docs)
```

All sequential in lane-a.

## Phase 1 — Foundation

### WP01 — schema + record_completion

**Goal**: Build the core enrichment helper module — atomic three-write contract.
**Dependencies**: none
**Independent test**: `pytest tests/enrichment/test_record_completion.py -v` ≥85% coverage
**Prompt**: [WP01-schema-and-record.md](tasks/WP01-schema-and-record.md)

Included: T001 schema, T002 record_completion, T003 tests

## Phase 2 — Consumers

### WP02 — reconcile + derive_state

**Goal**: Build the backfill + state-computation surfaces.
**Dependencies**: WP01
**Independent test**: `pytest tests/enrichment/test_reconcile_completions.py tests/enrichment/test_derive_state.py -v` ≥85%
**Prompt**: [WP02-reconcile-and-derive.md](tasks/WP02-reconcile-and-derive.md)

Included: T004 reconcile, T005 derive_state, T006 tests

## Phase 3 — Integration + Cutover

### WP03 — AGENTS.md cut + cutover script + docs

**Goal**: Wire tasker to invoke record_completion; cutover script; arch docs + runbook.
**Dependencies**: WP02
**Independent test**: `wc -c scripts/openclaw/agents/felix-admin-tasker/AGENTS.md` ≤14000; `pytest tests/openclaw/helpers/test_cutover_tasker.py -v` ≥85%; JSON files parse
**Prompt**: [WP03-cutover-and-docs.md](tasks/WP03-cutover-and-docs.md)

Included: T007 AGENTS.md cut, T008 cutover_tasker, T009 tests, T010 arch docs + runbook

## Estimated size

| WP | Subtasks | Est. lines |
|---|---|---|
| WP01 | 3 | ~1500 |
| WP02 | 3 | ~1500 |
| WP03 | 4 | ~700 |
| **Total** | **10** | **~3700** |

## Next step

`spec-kitty agent mission finalize-tasks --mission tasker-jsonl-migration-01KSB5XV --json`
