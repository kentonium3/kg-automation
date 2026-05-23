---
work_package_id: WP02
title: reconcile + derive_state
dependencies:
- WP01
requirement_refs:
- FR-006
- FR-007
- FR-008
- FR-009
- FR-014
- NFR-001
- NFR-003
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this feature were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
created_at: '2026-05-23T19:50:00+00:00'
subtasks:
- T004
- T005
- T006
history: []
authoritative_surface: scripts/enrichment/
execution_mode: code_change
mission_id: 01KSB5XVGW5WRDQFR17JSA52M5
mission_slug: tasker-jsonl-migration-01KSB5XV
owned_files:
- scripts/enrichment/reconcile_completions.py
- scripts/enrichment/derive_state.py
- tests/enrichment/test_reconcile_completions.py
- tests/enrichment/test_derive_state.py
tags: []
agent: "codex:gpt-5:spec-kitty-review:reviewer"
shell_pid: "14969"
---

# WP02 — reconcile + derive_state

## Objective

Build the consumer/backfill surfaces: `reconcile_completions.py` (backfill from Vikunja comments) and `derive_state.py` (compute current state from JSONL).

## Context

- **Pattern source**: `scripts/escalation/reconcile_completions.py` (1535 lines) + `scripts/escalation/derive_state.py` (686 lines). MIRROR with adapted state vocabulary.
- **Spec**: FR-006..FR-009, FR-014, NFR-001, NFR-003
- **CLI contract**: [contracts/cli.md](../contracts/cli.md) reconcile_completions section

## Subtasks

### T004 — reconcile_completions.py

Steps:
1. Read `scripts/escalation/reconcile_completions.py` end-to-end.
2. Create `scripts/enrichment/reconcile_completions.py` mirroring escalation. Adapt:
   - Comment parsing regex: match `[Felix] enrichment | <state> | <ISO timestamp>` (per deployed AGENTS.md vocabulary)
   - Disambiguation per FR-007: second pipe-delimited field MUST be literal `enrichment`; habit comments (second field is `YYYY-MM-DD`) are skipped silently
   - Default window: 2026-04-11 onward (FR-008)
   - Idempotency: key on (task_id, state, comment_timestamp); duplicate hit → skip silently (FR-009)
   - For each parsed comment: invoke `record_completion.record(...)` with `source=backfill` + `--no-vikunja` (don't re-write the comment)
3. CLI flags per contracts/cli.md: `--since`, `--dry-run`, `--ledger-path`, `--base-url`, `--token-path`.
4. Use `_StructuredArgumentParser` for exit code 3 on bad flags.

Validation:
- [ ] CLI `--help` exits 0
- [ ] Importable

### T005 — derive_state.py

Steps:
1. Read `scripts/escalation/derive_state.py` end-to-end.
2. Create `scripts/enrichment/derive_state.py` mirroring escalation. Adapt:
   - State vocabulary to enrichment
   - Single-offer policy: terminal states (`skipped`, `declined`) are sticky — once reached, the task is in that state until manual override
   - `confirmed` is terminal (task got structured, cycle complete)
   - `proposed` is non-terminal — can transition to any of the 3 terminal states
3. Public function `derive_state(task_id: int, ledger_path: Path = DEFAULT_LEDGER_PATH) -> Optional[str]` — returns latest state for the task, or None if no rows.
4. CLI optional (mirror escalation if it has one).

Validation:
- [ ] `python3 -c "from scripts.enrichment.derive_state import derive_state; print('ok')"` prints `ok`

### T006 — Tests for reconcile + derive_state

Steps:
1. Create `tests/enrichment/test_reconcile_completions.py`:
   - Happy path: 5 enrichment comments → 5 JSONL rows
   - Disambiguation: mixed comment list (3 enrichment + 2 habit) → only 3 JSONL rows; habit comments skipped
   - Idempotency: re-run on the same comment set → 0 new rows (duplicates skipped)
   - Window filter: comments before --since cutoff are skipped
   - `--dry-run`: no writes; print intent only
   - CLI exit codes
2. Create `tests/enrichment/test_derive_state.py`:
   - Empty ledger → returns None
   - Single proposed row → returns "proposed"
   - Multiple rows: returns latest state by timestamp
   - Terminal state (skipped/declined/confirmed) sticky
   - Multiple terminal states across tasks (per-task isolation)
3. Coverage target ≥85%.

Validation:
- [ ] `pytest tests/enrichment/test_reconcile_completions.py tests/enrichment/test_derive_state.py -v --cov=enrichment.reconcile_completions --cov=enrichment.derive_state` ≥85%
- [ ] Full `tests/enrichment/` suite passes

## Definition of Done

- [ ] All 3 subtasks complete; coverage ≥85% per file
- [ ] No regression on existing escalation/habits/doc_audit suites
- [ ] Disambiguation rule (FR-007) explicitly tested

## Implementation Command

```bash
spec-kitty agent action implement WP02 --mission tasker-jsonl-migration-01KSB5XV --agent claude:opus:python-implementer:implementer
```

## Activity Log

- 2026-05-23T20:32:12Z – claude:opus:python-implementer:implementer – shell_pid=11725 – Started implementation via action command
- 2026-05-23T20:50:05Z – claude:opus:python-implementer:implementer – shell_pid=11725 – Ready for review: reconcile + derive_state; 72 tests / 100% (derive) + 90% (reconcile) coverage
- 2026-05-23T20:51:20Z – codex:gpt-5:spec-kitty-review:reviewer – shell_pid=14969 – Started review via action command
