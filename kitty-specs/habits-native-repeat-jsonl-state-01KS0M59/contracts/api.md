# Contract — Python API

**Mission**: `habits-native-repeat-jsonl-state-01KS0M59`
**Module group**: `scripts.habits.*`

Each helper exposes both a Python API (for in-process callers, mostly test code) and a `__main__` CLI surface (for shell + LLM-agent invocation per C-006). This document covers the Python signatures; see `contracts/cli.md` for the CLI surface.

---

## `scripts.habits.identify_workout_task`

Lookup-only helper. Reads from Vikunja, prints to stdout. Does not write anything.

### `find_workout_task(api_base_url: str, token: str, candidate_ids: list[int]) -> dict | None`

```python
def find_workout_task(
    api_base_url: str,
    token: str,
    candidate_ids: list[int] | None = None,
) -> dict | None:
    """Find the current 'workout' habit task among known candidate IDs.

    Args:
        api_base_url: Vikunja API base (e.g., "https://office2.tail0f5f56.ts.net/api/v1/")
        token: Vikunja API token (felix-bot or kent — read-only operation)
        candidate_ids: List of task IDs to search among. Default: [14, 15, 16, 17, 18, 19, 20, 65]
            (the 8 known production habit tasks).

    Returns:
        Dict with keys {task_id, title, project_id, labels, repeat_after, due_date} for the
        first task whose title matches r"workout" (case-insensitive). None if no match.

    Raises:
        OSError: On network or HTTP error.
    """
```

---

## `scripts.habits.migrate_schedule`

The migration helper. Applies the `habits-schedule.yaml` config.

### `load_schedule(path: pathlib.Path) -> dict`

```python
def load_schedule(path: pathlib.Path) -> dict:
    """Load and validate habits-schedule.yaml.

    Returns:
        Parsed dict matching the schema in contracts/config.md.

    Raises:
        ValueError: On schema violation. Error message names the operation
            index + offending field.
        OSError: On file-read error.
    """
```

### `capture_snapshot(api_base_url: str, token: str, schedule: dict) -> dict`

```python
def capture_snapshot(api_base_url: str, token: str, schedule: dict) -> dict:
    """Capture BEFORE state of every task touched by the schedule.

    Returns:
        Snapshot dict per data-model.md Entity 3. Contains before_states for
        all PATCH/retire target IDs. created_tasks and applied_changes are
        initialized to empty lists.

    Raises:
        OSError: On network/HTTP error.
    """
```

### `apply_schedule(api_base_url: str, token: str, schedule: dict, snapshot_path: pathlib.Path, dry_run: bool = False) -> dict`

```python
def apply_schedule(
    api_base_url: str,
    token: str,
    schedule: dict,
    snapshot_path: pathlib.Path,
    dry_run: bool = False,
) -> dict:
    """Apply the schedule's operations to Vikunja, persisting the snapshot
    incrementally as changes succeed.

    Args:
        api_base_url, token: Vikunja API access.
        schedule: Validated schedule dict from load_schedule().
        snapshot_path: Path to write the rollback substrate (created if absent;
            updated incrementally during the run).
        dry_run: If True, prints planned changes to stdout but issues no
            PATCH/POST/DELETE calls. Snapshot is still written with
            before_states (no applied_changes).

    Returns:
        The final snapshot dict (also written to snapshot_path).

    Raises:
        OSError: On unrecoverable network/HTTP error mid-batch. The snapshot
            on disk reflects the partial state for rollback.
        ValueError: On schedule validation failure (should be caught by
            load_schedule first).
    """
```

### `rollback(api_base_url: str, token: str, snapshot_path: pathlib.Path) -> dict`

```python
def rollback(api_base_url: str, token: str, snapshot_path: pathlib.Path) -> dict:
    """Reverse every change recorded in the snapshot's applied_changes.

    Iterates applied_changes in reverse order. For each entry:
        - "patch" op: PATCH the task back to before_states[<id>].before values.
        - "retire" op: PATCH the task with done=false (or back to the captured
          done value if it was true pre-Phase-3).
        - "create" op: DELETE the created task (id from created_tasks).

    After successful rollback, the helper appends an "applied_changes" entry
    with op="rollback" and the original op as a sub-field, so the snapshot
    file records both the original change and the reversal.

    Returns:
        Updated snapshot dict (with rollback annotations appended).

    Raises:
        OSError: On network/HTTP error during rollback. Operator triages.
        ValueError: If snapshot_path is missing or malformed.
    """
```

---

## `scripts.habits.record_completion`

The three-write atomic completion helper.

### `record(task_id: int, title: str, date: str, state: str, source: str, note: str | None = None, *, api_base_url: str, token: str) -> None`

```python
def record(
    task_id: int,
    title: str,
    date: str,
    state: str,
    source: str,
    note: str | None = None,
    *,
    api_base_url: str,
    token: str,
) -> None:
    """Three-write atomic completion record per ADR Q3-D.

    1. Check state_log.read("habits", task_id, date, state). If a matching
       record exists, return immediately (idempotent no-op).
    2. POST /tasks/<id> with done=true (Vikunja). Raises OSError on failure.
    3. PUT /tasks/<id>/comments with body "[Felix] <date> | <state>"
       (or with " | <note>" appended if note is provided). Raises OSError
       on failure; the Vikunja task is now marked done but the JSONL is
       not yet written — caller surfaces this to the operator.
    4. state_log.append("habits", record). The record is built from the
       arguments + timestamp = now UTC.

    Args:
        task_id: Vikunja task ID.
        title: Denormalized task title (for the JSONL record).
        date: ISO-8601 date (YYYY-MM-DD) — the day the completion is FOR.
        state: Must be a member of state_log_schema.DOMAIN_STATES["habits"].
        source: Identifier of the writer (e.g., "whatsapp").
        note: Optional freeform string.
        api_base_url, token: Vikunja API access.

    Raises:
        ValueError: On invalid state or invalid arguments (caught by
            state_log.validate_record before any I/O).
        OSError: On Vikunja API failure. The exception message names which
            of the three writes failed.
    """
```

---

## `scripts.habits.reconcile_completions`

The backfill + drift detection helper.

### `reconcile(api_base_url: str, token: str, today: str | None = None) -> dict`

```python
def reconcile(
    api_base_url: str,
    token: str,
    today: str | None = None,
) -> dict:
    """Enumerate habit tasks, detect missing JSONL entries (backfill from
    Vikunja UI completions), and report drift.

    Args:
        api_base_url, token: Vikunja API access.
        today: ISO-8601 date for the drift-detection comparison. Defaults
            to current UTC date.

    Returns:
        Summary dict:
        {
            "tasks_examined": int,
            "backfilled": [{task_id, date, ...}, ...],
            "drift": [{task_id, jsonl_state, vikunja_done, note}, ...],
            "errors": [...]  # non-fatal errors per task
        }

    Raises:
        OSError: On unrecoverable Vikunja API failure (the helper would not
            be able to enumerate tasks at all).
    """
```

The helper does NOT raise on drift — drift is reported via the returned dict.

---

## `scripts.habits.query_active_habits_v2`

Parallel new variant. The CLI surface is also exposed but the Python API is the canonical contract.

### `query_active_today(api_base_url: str, token: str, today: str | None = None) -> list[dict]`

```python
def query_active_today(
    api_base_url: str,
    token: str,
    today: str | None = None,
) -> list[dict]:
    """Return habit tasks that are active for today using Vikunja's native filter.

    Args:
        api_base_url, token: Vikunja API access.
        today: ISO-8601 date for the filter comparison. Defaults to UTC today.

    Returns:
        List of task dicts (one per active habit) with at least these fields:
        id, title, due_date, done, repeat_after, project_id, labels.

    Raises:
        OSError: On Vikunja API failure.
    """
```

---

## `scripts.habits.exclude_completed_v2`

Parallel new variant. Reads state_log instead of LLM-parsing comments.

### `exclude_completed_for_today(active_tasks: list[dict], today: str | None = None) -> list[dict]`

```python
def exclude_completed_for_today(
    active_tasks: list[dict],
    today: str | None = None,
) -> list[dict]:
    """Filter the input list to tasks WITHOUT a 'complete' JSONL entry for today.

    Args:
        active_tasks: Output of query_active_today (or compatible list of task
            dicts; only the "id" field is consulted).
        today: ISO-8601 date for the JSONL filter. Defaults to UTC today.

    Returns:
        Subset of active_tasks where state_log.read("habits", task_id=X,
        date=today, state="complete") is empty.

    Raises:
        OSError: If state_log read fails (rare; the log file is local).
    """
```

---

## Exceptions used

| Exception | When |
|---|---|
| `ValueError` | Schema violation (schedule.yaml), invalid state arg, malformed snapshot |
| `OSError` (+ subclasses `PermissionError`, `FileNotFoundError`, `urllib.error.URLError`, `urllib.error.HTTPError`) | Network / file I/O failure |

No custom exception classes are introduced. Same convention as Phase 2.

---

## Thread / process safety

- All helpers are designed for synchronous, single-caller invocation per process.
- `state_log` writes (used by `record_completion` and `reconcile_completions`) are fcntl-locked per Phase 2 contract — safe for concurrent processes.
- Vikunja API calls are not concurrent in any helper here; future Phase 5+ callers may parallelize, but each helper invocation is sequential.
