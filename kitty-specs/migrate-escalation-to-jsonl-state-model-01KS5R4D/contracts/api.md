# API Contracts: Python function signatures

**Mission**: `migrate-escalation-to-jsonl-state-model-01KS5R4D`
**Date**: 2026-05-21

Authoritative Python function signatures for the four new helpers. Implementation may add private functions and helpers; the signatures here are the public surface.

---

## `scripts/escalation/record_completion.py`

### `record_event(record: dict, *, base_url: str = DEFAULT_BASE_URL, token_path: Path = DEFAULT_TOKEN_PATH) -> dict`

Atomic three-write helper. Performs the Vikunja side-effect first, then writes the JSONL record.

**Behavior** (per research D6):

1. Validate `record` against shared `state_log` schema + `EVENT_TYPE_PARAMETERS` (see `schema.py`).
2. For event_types that require a Vikunja side-effect (`level_sent`, `snoozed`, `dismissed`, `done`, `rescheduled` when initiated by Kent's reply): perform the side-effect (e.g., write `[Felix-Escalation]` comment per the v1 vocabulary; for `done` also PATCH the task with `done=true`).
3. Call `state_log.append("escalation", record)` for the JSONL write. Note: the file routing is via `state_log` consumer file selection by project slug; see `_jsonl_path_for_record()`.
4. Return a dict: `{"ok": True, "jsonl_path": "<path>", "vikunja_actions": ["<list>"], "deduped": bool}`.

**Raises**:
- `EscalationSchemaError` on validation failure (no writes attempted).
- `VikunjaError` on Vikunja step failure (no JSONL write).
- `StateLogError` on JSONL write failure (Vikunja step already committed — operator-triageable; the helper logs a structured stderr message naming the failed step).

### `idempotent_record_event(record: dict, ...) -> dict`

Wraps `record_event` with a pre-check: if a record matching `record` already exists in the JSONL file (by `state_log.read("escalation", task_id, date, state)`), return immediately with `deduped=True` and no Vikunja calls.

### Module constants

```python
DEFAULT_BASE_URL = "http://100.92.197.90:3456/api/v1/"
DEFAULT_TOKEN_PATH = Path("/data/services/openclaw/secrets/vikunja-api")
HTTP_TIMEOUT_SECONDS = 30
JSONL_STATE_DIR = Path("/data/services/openclaw/state/escalation")
```

---

## `scripts/escalation/reconcile_completions.py`

### `reconcile_project(project_id: int, *, base_url: str = ..., token_path: Path = ...) -> ReconcileReport`

Sweep one Vikunja project for drift. Per research D3 + spec FR-005.

**Behavior**:
1. Enumerate escalation-subscribed tasks in the project (tasks with at least one prior `level_sent` JSONL record AND no terminal record since).
2. For each task: GET current Vikunja state; load JSONL records; call `derive_state(records)`.
3. Detect drift cases:
   - `vikunja.done=true` AND JSONL has no `done` record → emit synthetic `{state: "done", source: "reconcile"}`
   - `vikunja.due_date != last_rescheduled_to (or original)` AND no terminal record → emit synthetic `{state: "rescheduled", source: "reconcile", reschedule_to: <new>}`
4. Returns a `ReconcileReport` summarizing tasks scanned, synthetic records emitted, hard-fail events fired.

### `ReconcileReport` dataclass

```python
@dataclass(frozen=True, slots=True)
class ReconcileReport:
    project_id: int
    project_slug: str
    tasks_scanned: int
    synthetic_done_emitted: int
    synthetic_rescheduled_emitted: int
    hard_fails: list[HardFailEvent]
    duration_seconds: float
```

### `HardFailEvent` dataclass

```python
@dataclass(frozen=True, slots=True)
class HardFailEvent:
    task_id: int
    task_title: str
    project_id: int
    reason: Literal["malformed_jsonl_record", "phantom_subscription", "derive_state_inconsistency"]
    detail: str
    detected_at: datetime  # UTC, tz-aware
    deduped: bool  # True if an open bug already exists; no new bug filed
    bug_url: Optional[str]
```

---

## `scripts/escalation/backfill_jsonl_from_comments.py`

### `backfill_project(project_id: int, *, base_url: str = ..., token_path: Path = ..., dry_run: bool = False) -> BackfillReport`

One-time replay of `[Felix-Escalation]` comments to JSONL records. Per research D5.

**Behavior**:
1. Enumerate every task in the project with at least one `[Felix-Escalation]` comment.
2. Read all comments per task; parse with the locked vocabulary mapping (data-model Entity 3).
3. Write the pre-backfill snapshot (data-model Entity 4) BEFORE any JSONL writes.
4. For each parseable comment: emit a JSONL record via `state_log.append`. Skip malformed comments.
5. Return a `BackfillReport`.

`dry_run=True`: do everything except the snapshot write and the JSONL writes. Useful for previewing.

### `BackfillReport` dataclass

```python
@dataclass(frozen=True, slots=True)
class BackfillReport:
    project_id: int
    project_slug: str
    tasks_scanned: int
    comments_parsed: int
    comments_replayed: int
    comments_malformed: int
    malformed_details: list[MalformedComment]  # task_id + snippet + reason
    snapshot_path: Path
    jsonl_path: Path
    dry_run: bool
```

---

## `scripts/escalation/derive_state.py`

### `derive_state(records: list[StateLogRecord]) -> EscalationState`

Pure function. Per research D7 + spec FR-001.

**Behavior**:
1. Sort records newest-first by `timestamp`.
2. Apply the policy walk (in order: terminal? → snoozed-active? → rescheduled-future? → most-recent level? → derive next eligible level).
3. Return an `EscalationState` dataclass.
4. Raise `EscalationStateError` if records are mutually inconsistent (e.g., `level_sent` with no `level` parameter).

### `EscalationState` dataclass

```python
@dataclass(frozen=True, slots=True)
class EscalationState:
    current_state: Literal[
        "new",            # no records yet (caller probably shouldn't pass this)
        "level_1_sent",   # last record was level_sent with level=1
        "level_2_sent",   # last record was level_sent with level=2
        "snoozed",        # active snooze; snooze_active_until > today
        "snoozed_expired",# most recent was snoozed, but now > snooze_until
        "dismissed",      # terminal
        "done",           # terminal
        "rescheduled",    # future due_date in JSONL
    ]
    last_event: Optional[StateLogRecord]
    snooze_active_until: Optional[date]
    next_eligible_level: Optional[int]  # 1, 2, or None (terminal)
    last_event_recorded_at: Optional[datetime]
```

### `EscalationStateError`

```python
class EscalationStateError(Exception):
    """Raised when the records list is internally inconsistent.

    Attributes:
        task_id: which task's records were being processed
        records: the records that caused the inconsistency
        reason: short string per data-model Entity 5 reason taxonomy
    """
```

---

## `scripts/escalation/schema.py`

### `EVENT_TYPE_PARAMETERS: dict[str, frozenset[str]]`

Per data-model Entity 1 schema validator surface.

### `validate_event_params(record: dict) -> None`

Validates that `record["state"]` is in `EVENT_TYPE_PARAMETERS`, and that all required parameters for that event_type are present and well-typed. Raises `EscalationSchemaError` on the first violation (short-circuit, with field-named, value-quoted message).

### `EscalationSchemaError(Exception)`

Mirrors the Phase 2 library's `ValueError` pattern but uses a domain-specific exception class for easier upstream try/except routing.

---

## Cross-references

- Phase 2 library: `scripts/common/state_log.py` (`append`, `read` — consumed as-is).
- Phase 3 reference impl: `scripts/habits/record_completion.py` (HTTP wrapper, error handling pattern).
- Research D6 (three-write ordering), D7 (derive_state shape), D8 (Q10 trigger), D9 (dedup query).
