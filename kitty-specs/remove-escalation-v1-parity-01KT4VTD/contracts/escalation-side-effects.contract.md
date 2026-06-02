# Contract: escalation side-effect dispatch (post-parity cleanup)

**Mission**: `remove-escalation-v1-parity-01KT4VTD`
**Parent contract**: [`kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/contracts/api.md`](../../migrate-escalation-to-jsonl-state-model-01KS5R4D/contracts/api.md) (mission #309)

This contract specifies the per-state side-effect behavior of `record_event` after the v1 comment-write parity is removed and the phantom-subscription detector is deleted from `reconcile_completions.py`.

## `record_event` side-effect dispatch

For each escalation event flowing through `record_event(record, …)`:

1. **Validate the record** (Step 0). On failure raise `EscalationSchemaError`; no side-effects.
2. **Vikunja side-effects** (Step 1, only for two states):
   - `state == "done"`: `PATCH /tasks/{task_id}` with body `{"done": true}`.
   - `state == "rescheduled"`: `PATCH /tasks/{task_id}` with body `{"due_date": "YYYY-MM-DDT00:00:00Z"}` where `YYYY-MM-DD` is `record["reschedule_to"]`.
   - For `state in {"level_sent", "snoozed", "dismissed"}`: NO Vikunja side-effect.
   - On any HTTP/network failure in this step: raise `VikunjaError`. Step 2 does NOT run.
3. **JSONL append** (Step 2, every state): append the record to `/data/services/openclaw/state/escalation/project-{project_id}-escalation-history.jsonl` using the fcntl-locked append pattern. On I/O failure raise `StateLogError`.

## Invariants

- **I-1 (no comment write)**: `record_event` MUST NOT issue any `PUT /tasks/{id}/comments` call. The path is removed entirely.
- **I-2 (cycle of `done`/`rescheduled` task PATCH unchanged)**: the existing task PATCH semantics are preserved — these are Vikunja state mutations, not v1-comment artifacts.
- **I-3 (ordering)**: Vikunja PATCH (when present) MUST precede the JSONL append. A failed PATCH means no JSONL append.
- **I-4 (purity of validation)**: the schema validator MUST NOT have side-effects.
- **I-5 (idempotence)**: `idempotent_record_event(record)` MUST still skip writing if the same record is already present in JSONL.

## `reconcile_project` sweep contract

The reconcile module runs ONE pass per project per tick:

- **Subscribed sweep**: enumerate JSONL records for `project_id` → derive state per task via `derive_state` → compare against Vikunja state via task GET → file Q10 hard-fail for any drift.

The phantom-subscription sweep (which previously enumerated Vikunja project tasks via `GET /projects/{id}/tasks` and looked for `[Felix-Escalation]` comments on tasks not in the JSONL subscribed set) is removed entirely.

## Invariants on reconcile

- **I-6 (no v1 reader)**: reconcile MUST NOT call any helper that reads `[Felix-Escalation]` comment markers from Vikunja. `_COMMENT_MARKER` and `_count_escalation_comments` are deleted.
- **I-7 (subscribed-sweep preservation)**: every test currently asserting subscribed-sweep behavior MUST pass without modification.
- **I-8 (reason-code surface shrinks)**: the `phantom_subscription` reason code is removed from `hard_fail.py`. Remaining reason codes (`state_drift`, `malformed_jsonl_record`, `derive_state_error`) are preserved.

## Test obligations

| Case | Inputs | Expected |
|---|---|---|
| `level_sent_no_comment`     | `state="level_sent"` record | one JSONL append; zero Vikunja calls |
| `snoozed_no_comment`        | `state="snoozed"` record    | one JSONL append; zero Vikunja calls |
| `dismissed_no_comment`      | `state="dismissed"` record  | one JSONL append; zero Vikunja calls |
| `done_patch_then_jsonl`     | `state="done"` record       | one Vikunja PATCH (body `{"done": true}`), then one JSONL append; no comment PUT |
| `rescheduled_patch_then_jsonl` | `state="rescheduled"` record, `reschedule_to="2026-06-15"` | one Vikunja PATCH (body `{"due_date": "2026-06-15T00:00:00Z"}`), then one JSONL append; no comment PUT |
| `patch_failure_blocks_jsonl` | `state="done"`, Vikunja returns 5xx on PATCH | `VikunjaError` raised; JSONL file unchanged |
| `reconcile_no_phantom_path` | project with both subscribed and unsubscribed Vikunja tasks | only subscribed-sweep runs; no `GET /projects/{id}/tasks` enumeration for phantom detection; no `phantom_subscription` hard-fail filed |

## Out of scope for this contract

- Schema definitions (lives in `scripts/escalation/schema.py`)
- HTTP error mapping details (lives in `scripts/escalation/record_completion.py` HTTP wrapper)
- Pre-cutover comments on Vikunja tasks (preserved as historical record; not touched by any code path)
- Habits/enrichment domain side-effects (different module, separate cleanup)
