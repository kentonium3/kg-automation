---
work_package_id: WP01
title: enrichment schema + record_completion
dependencies: []
requirement_refs:
- C-003
- FR-001
- FR-002
- FR-003
- FR-004
- FR-005
- FR-013
- FR-015
- NFR-001
- NFR-006
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this mission were generated on main.
created_at: '2026-05-23T19:50:00+00:00'
subtasks:
- T001
- T002
- T003
history: []
authoritative_surface: scripts/enrichment/
execution_mode: code_change
mission_id: 01KSB5XVGW5WRDQFR17JSA52M5
mission_slug: tasker-jsonl-migration-01KSB5XV
owned_files:
- scripts/enrichment/__init__.py
- scripts/enrichment/schema.py
- scripts/enrichment/record_completion.py
- tests/enrichment/__init__.py
- tests/enrichment/test_schema.py
- tests/enrichment/test_record_completion.py
tags: []
---

# WP01 — enrichment schema + record_completion

## Objective

Create the foundation of `scripts/enrichment/` module: the `EnrichmentCompletion` dataclass + the `record_completion` helper that implements the atomic three-write contract (Vikunja comment FIRST → JSONL append SECOND → ack log).

## Context

- **Pattern source**: `scripts/escalation/schema.py` (198 lines) and `scripts/escalation/record_completion.py` (1000 lines). MIRROR these 1:1 with adapted state vocabulary.
- **Spec**: FR-001..FR-005, FR-013, FR-015, NFR-001, NFR-006
- **Data model**: [data-model.md](../data-model.md) E1 EnrichmentCompletion
- **CLI contract**: [contracts/cli.md](../contracts/cli.md) record_completion section

## Subtasks

### T001 — schema.py + __init__.py

Steps:
1. Create `scripts/enrichment/__init__.py` (empty).
2. Create `scripts/enrichment/schema.py` mirroring `scripts/escalation/schema.py`. Adapt:
   - Class name: `EnrichmentCompletion` (was `EscalationCompletion`)
   - VALID_STATES: `frozenset({"proposed", "confirmed", "skipped", "declined"})`
   - VALID_SOURCES: `frozenset({"agent", "reconcile", "backfill", "operator_repair"})`
   - DEFAULT_LEDGER_PATH: `Path("/data/services/openclaw/state/enrichment/enrichment-history.jsonl")`
   - SCHEMA_VERSION = 1
3. Field order in dataclass MUST match data-model.md E1 (used for deterministic JSONL serialization).

Validation:
- [ ] `python3 -c "from scripts.enrichment.schema import EnrichmentCompletion, VALID_STATES, VALID_SOURCES; print('ok')"` prints `ok`
- [ ] `EnrichmentCompletion` is `frozen=True`

### T002 — record_completion.py + CLI

Steps:
1. Read `scripts/escalation/record_completion.py` end-to-end to understand the atomic three-write contract + CLI surface.
2. Create `scripts/enrichment/record_completion.py` mirroring escalation's structure. Adapt:
   - State enum to enrichment vocabulary
   - Comment format: `[Felix] enrichment | <state> | <ISO timestamp>` (per deployed AGENTS.md)
   - Vikunja API call: same pattern (PUT /tasks/<id>/comments)
   - JSONL append: same atomic write semantics
   - Activity log path/format: match escalation if possible (operator-readable)
3. CLI flags per contracts/cli.md: `--task-id`, `--state`, `--source`, `--note`, `--idempotent`, `--no-vikunja`, `--base-url`, `--token-path`.
4. Use `_StructuredArgumentParser` pattern (mirrors cutover_362.py) so argparse errors → exit 3.
5. Soft-fail per FR-013: if JSONL append fails AFTER Vikunja side-effect lands, log warning + exit 0.

Validation:
- [ ] CLI `--help` exits 0
- [ ] Importable: `from scripts.enrichment.record_completion import record, main`

### T003 — Tests

Steps:
1. Create `tests/enrichment/__init__.py` (empty).
2. Create `tests/enrichment/test_schema.py` — basic dataclass tests; VALID_STATES/VALID_SOURCES coverage.
3. Create `tests/enrichment/test_record_completion.py` mirroring `tests/escalation/test_record_completion.py` (if exists) OR new pytest with comprehensive scenarios:
   - All 4 states × all 4 sources happy paths
   - `--idempotent` flag duplicate hit → no-op exit 0
   - `--no-vikunja` flag → JSONL written, no Vikunja subprocess call
   - Vikunja API failure → exit 1 (hard fail; nothing written)
   - JSONL append failure after Vikunja success → exit 0 with logged warning (Q10 soft-fail)
   - Atomic ordering: Vikunja call happens BEFORE JSONL append (mock and verify call_args timing)
   - CLI exit codes: 0/1/2/3 covered
4. Coverage target ≥85%.

Validation:
- [ ] `PYTHONPATH=scripts python3 -m pytest tests/enrichment/test_schema.py tests/enrichment/test_record_completion.py -v --cov=enrichment.schema --cov=enrichment.record_completion` ≥85%

## Definition of Done

- [ ] All 3 subtasks complete
- [ ] `pytest tests/enrichment/` passes ≥85% on covered modules
- [ ] No regression on existing escalation/habits/doc_audit suites
- [ ] CLI smoke: `python3 -m scripts.enrichment.record_completion --help` exits 0

## Implementation Command

```bash
spec-kitty agent action implement WP01 --mission tasker-jsonl-migration-01KSB5XV --agent claude:opus:python-implementer:implementer
```
