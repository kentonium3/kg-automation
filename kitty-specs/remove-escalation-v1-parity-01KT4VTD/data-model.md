# Data Model: Remove escalation v1 comment-write parity

**Mission**: `remove-escalation-v1-parity-01KT4VTD`

This mission introduces no new data entities and no schema changes. The "data model" below is the before/after invariants table for the two affected modules (`record_completion.py` and `reconcile_completions.py`).

## Per-state side-effect contract — `record_event(record, …)`

### Before (current production state on 2026-06-02)

| record.state | Vikunja PATCH | Vikunja PUT (comment) | JSONL append |
|---|---|---|---|
| `level_sent`     | — | `[Felix-Escalation] YYYY-MM-DD \| level-N \| sent` | yes |
| `snoozed`        | — | `[Felix-Escalation] YYYY-MM-DD \| snoozed:Nd \| acknowledged` | yes |
| `dismissed`      | — | `[Felix-Escalation] YYYY-MM-DD \| dismissed \| acknowledged` | yes |
| `done`           | `{done: true}` | `[Felix-Escalation] YYYY-MM-DD \| done \| acknowledged` | yes |
| `rescheduled`    | `{due_date: YYYY-MM-DD}` | `[Felix-Escalation] YYYY-MM-DD \| rescheduled:YYYY-MM-DD \| acknowledged` | yes |

Three-write contract: validate → Vikunja side-effects (PATCH then PUT-comment) → JSONL append.

### After (this mission)

| record.state | Vikunja PATCH | Vikunja PUT (comment) | JSONL append |
|---|---|---|---|
| `level_sent`     | — | **— (removed)** | yes |
| `snoozed`        | — | **— (removed)** | yes |
| `dismissed`      | — | **— (removed)** | yes |
| `done`           | `{done: true}` | **— (removed)** | yes |
| `rescheduled`    | `{due_date: YYYY-MM-DD}` | **— (removed)** | yes |

Contract becomes: validate → Vikunja PATCH (only for `done`/`rescheduled`) → JSONL append. For `level_sent`/`snoozed`/`dismissed` events, JSONL append is the sole side-effect.

### Invariants preserved

- **Ordering**: Vikunja PATCH (when present) precedes JSONL append. If PATCH fails, no JSONL write.
- **Atomicity**: JSONL append remains the fcntl-locked append-then-flush-then-fsync pattern.
- **CLI exit codes**: 0 success, 1 Vikunja step failure, 2 JSONL step failure, 3 validation error — unchanged.
- **Idempotence**: `idempotent_record_event` semantics unchanged.

## Reconcile sweep paths — `reconcile_project(project_id, …)`

### Before (current production state)

The reconcile module runs two passes per project per tick:

1. **Subscribed sweep**: enumerate JSONL records for `project_id`, derive state for each task, compare against Vikunja state, file Q10 hard-fail for any discrepancy. Substrate: JSONL + Vikunja task PATCHes.
2. **Phantom-subscription sweep**: enumerate Vikunja project tasks via `GET /projects/{id}/tasks`; for each task NOT in the subscribed set, count `[Felix-Escalation]` comments via `_count_escalation_comments`; if `comment_count > 0`, file Q10 hard-fail with `phantom_subscription` reason. Substrate: Vikunja comments (frozen, historical).

### After (this mission)

Only the subscribed sweep remains:

1. **Subscribed sweep** (unchanged): operates on JSONL + Vikunja PATCH state.

Phantom-subscription detection is removed entirely. The general cross-system drift detector for tasks-Felix-doesn't-know-about is deferred to #507 (Felix↔Vikunja bi-directional sync foundation).

### Invariants preserved

- **Reconcile CLI surface**: `--dry-run`, `--quiet`, `--all`, per-project invocation patterns unchanged.
- **Subscribed-sweep semantics**: all subscribed-sweep tests pass without modification.
- **Q10 hard-fail filing**: dedup against open GitHub issues per FR-009 of #309 unchanged for the remaining reason codes.

## Hard-fail reason codes — `hard_fail.py`

### Before

Reason codes (non-exhaustive): `state_drift`, `malformed_jsonl_record`, `derive_state_error`, `phantom_subscription`.

### After

Reason codes: `state_drift`, `malformed_jsonl_record`, `derive_state_error`. `phantom_subscription` removed along with its producer in reconcile. The bug-body templating that referenced `[Felix-Escalation]` comment count is removed.

## Files deleted entirely (no per-file invariants required)

- `scripts/escalation/backfill_jsonl_from_comments.py` — one-time migration tool.
- `tests/escalation/test_backfill.py` — tests for the migration tool.

## State files untouched

- `/data/services/openclaw/state/escalation/project-*-escalation-history.jsonl` — JSONL records preserved exactly.
- `/data/services/openclaw/state/escalation/pre-phase6-snapshot.json` — pre-migration snapshot preserved as historical record.
- Pre-cutover `[Felix-Escalation]` comments on Vikunja tasks — preserved exactly (C-001).

## Cross-references

- Authoritative pipeline contract: [`contracts/escalation-side-effects.contract.md`](contracts/escalation-side-effects.contract.md)
- Production cron schedule that exercises the new contract: `escalation-daily` at 12:00 UTC daily on office2
