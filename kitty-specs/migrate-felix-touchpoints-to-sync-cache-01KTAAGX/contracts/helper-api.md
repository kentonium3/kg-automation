# Contract: `scripts/common/sync_cache.py` API

**Mission**: `migrate-felix-touchpoints-to-sync-cache-01KTAAGX`
**Phase**: Plan / Phase 1 / contracts
**Date**: 2026-06-04

Canonical API contract for the new shared helper. Every migrated touchpoint reads through these functions; no touchpoint imports `scripts.sync.state` or any state-log code directly (spec C-004).

---

## Module imports + module-level constants

```python
"""Felix sync cache: canonical cache-read helper for touchpoints (mission #519)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.sync.state import (
    STATE_DIR_DEFAULT,
    TaskCacheRecord,
    read_freshness,
    read_task_cache,
)
```

```python
# SLA tier definitions — see kitty-specs/.../research.md Unknown 1
@dataclass(frozen=True)
class SLATier:
    name: str
    seconds: int

SLA_HOT = SLATier("HOT", 60)
SLA_NORMAL = SLATier("NORMAL", 900)
SLA_BATCH = SLATier("BATCH", 3600)
SLA_LOOSE = SLATier("LOOSE", 86400)
```

```python
@dataclass(frozen=True)
class TaskCacheView:
    task_id: int
    fields: dict[str, Any]
    vikunja_updated_at: str
    is_private: bool

@dataclass(frozen=True)
class CompletionTimestamps:
    most_recent_complete_at_utc: str | None
    most_recent_complete_date_et: str | None
```

---

## Function 1 — `read_cached_tasks`

```python
def read_cached_tasks(
    sla: SLATier,
    state_dir: Path = STATE_DIR_DEFAULT,
    *,
    touchpoint_name: str | None = None,
) -> dict[int, TaskCacheView]:
    """Read every task in the cache.

    Args:
        sla: The touchpoint's freshness SLA. Raises OSError if the pointer
            age exceeds the SLA's seconds value.
        state_dir: Cache directory. Default is the production location.
        touchpoint_name: For error messages. Optional but RECOMMENDED so
            operators can identify which touchpoint failed.

    Returns:
        A dict mapping task_id (int) to TaskCacheView. Includes private-project
        tasks (those have empty fields + is_private=True); the touchpoint
        decides whether to skip them or surface them as errors via
        read_cached_task_by_id.

    Raises:
        OSError: On cache file missing, freshness file missing,
            stale-beyond-SLA, malformed JSON, or schema-version mismatch.
            Message includes touchpoint_name, failure class, recovery hint.
    """
```

**Behavior contract**:

1. Read `freshness.json` first. If missing → `OSError("[<tp_name>] sync cache freshness pointer missing at {path}. Recovery: cd ~/kg-automation && python3 -m scripts.sync.driver --bootstrap")`.
2. Compute pointer age (`now_utc - pointer.last_polled_utc`). If `age_seconds > sla.seconds` → `OSError("[<tp_name>] sync cache stale beyond {sla.name} (max {sla.seconds}s); pointer age {age:.0f}s. Recovery: systemctl --user status felix-vikunja-sync.timer")`.
3. Read `task-cache.json` via `state.read_task_cache(state_dir)`. Propagates `OSError` on malformed/schema-mismatch with the original `state.py` error message.
4. Translate `TaskCacheRecord.tasks` → `dict[int, TaskCacheView]`:
   - `int(task_id_str)` for the dict key
   - `is_private = (entry.fields == {})` for the view's flag
5. Return.

**Forbidden behaviors**:
- Silent default on cache-missing
- Silent default on stale
- Empty-dict return on any failure
- Logging the cache contents to stderr or any log file

---

## Function 2 — `read_cached_task_by_id`

```python
def read_cached_task_by_id(
    task_id: int,
    sla: SLATier,
    state_dir: Path = STATE_DIR_DEFAULT,
    *,
    touchpoint_name: str | None = None,
) -> TaskCacheView:
    """Read one task by its integer task_id.

    Args:
        task_id: The Vikunja integer task id.
        sla: As above.
        state_dir: As above.
        touchpoint_name: As above.

    Returns:
        TaskCacheView for the requested task.

    Raises:
        OSError: All cases from read_cached_tasks plus:
            - Task not in cache (with the message including the task_id
              and the cache's last_polled_utc)
            - Task is private-project (empty fields) — caller is treated
              as "task data unavailable"
    """
```

**Behavior contract**:

1. Call `read_cached_tasks(sla, state_dir, touchpoint_name=touchpoint_name)`. Re-raises its errors.
2. Look up `task_id` in the returned dict. If missing → `OSError("[<tp_name>] task {task_id} not in sync cache; cache last_polled_utc={pointer}. Vikunja may have added the task after the last driver tick; next tick will catch it.")`.
3. If `view.is_private` → `OSError("[<tp_name>] task {task_id} is private-project (data unavailable in cache).")`. NO field content in the message.
4. Return the view.

---

## Function 3 — `read_freshness_pointer`

```python
def read_freshness_pointer(
    state_dir: Path = STATE_DIR_DEFAULT,
    *,
    touchpoint_name: str | None = None,
) -> datetime:
    """Return the cache's freshness pointer as a UTC datetime.

    Args:
        state_dir: As above.
        touchpoint_name: As above.

    Returns:
        datetime with tzinfo=timezone.utc.

    Raises:
        OSError: On freshness file missing or malformed.
    """
```

**Behavior contract**:

1. `state.read_freshness(state_dir)` — propagates errors with touchpoint_name prefix.
2. Parse `pointer.layers["status_and_task"].last_polled_utc` ISO-8601 → `datetime`.
3. Return.

**Used by**: helper-internal SLA computation, plus tests + ad-hoc operator queries (`python3 -c "from scripts.common import sync_cache; print(sync_cache.read_freshness_pointer())"`).

---

## Function 4 — `read_completion_timestamps`

```python
def read_completion_timestamps(
    domain: str,
    task_id: int,
    state_log_dir: Path,
) -> CompletionTimestamps:
    """Return the most recent 'complete'-state timestamp for task_id in domain's JSONL log.

    Args:
        domain: One of "habits", "escalation", "enrichment". Used to derive
            the JSONL filename: f"{domain}-history.jsonl".
        task_id: The Vikunja integer task id.
        state_log_dir: The directory containing the state log JSONL.
            (Typically /data/services/openclaw/state/.)

    Returns:
        CompletionTimestamps. If task_id has no completion in the log,
        both fields are None (this is NOT an error condition — fresh tasks
        legitimately have no completion history).

    Raises:
        OSError: On state log file missing or malformed JSONL.
    """
```

**Behavior contract**:

1. Compute path: `state_log_dir / f"{domain}-history.jsonl"`. Missing → `OSError`.
2. Stream-read the JSONL. For each parseable row:
   - Skip rows where `state != "complete"` or `task_id != target_task_id`.
   - Track the row with the latest `timestamp` (ISO-8601 UTC).
3. Return `CompletionTimestamps(most_recent_complete_at_utc, most_recent_complete_date_et)`. `date_et` comes from the row's `date` field (already in ET YYYY-MM-DD format per the JSONL schema).
4. If no matching row found, return `CompletionTimestamps(None, None)`.

**Why this function is in `sync_cache.py` and not a separate state-log helper**: per spec C-004, touchpoints must route every state read through one entry point. Adding state-log reading here keeps the surface small (one import for the touchpoint) and respects the constraint. Future missions that introduce more state-log consumers may extract a separate module.

---

## Function 5 — `is_cache_healthy` (utility)

```python
def is_cache_healthy(
    sla: SLATier,
    state_dir: Path = STATE_DIR_DEFAULT,
) -> bool:
    """Non-raising health check.

    Used by quickstart.md verification commands and operator-side smoke
    tests; NOT used in production touchpoint code paths (those use the
    raising APIs above).

    Returns:
        True if read_cached_tasks would succeed with the given SLA.
        False on any OSError.
    """
```

---

## Error message format (normative)

Every `OSError` raised by this module follows the format:

```
[<touchpoint_name>] <one-line summary>. Recovery: <one-line recovery command or hint>.
```

Examples (all touchpoint_name is the value the caller passed):

```
[habits.morning_checkin_list] sync cache stale beyond SLA_NORMAL (max 900s); pointer age 2042s. Recovery: systemctl --user status felix-vikunja-sync.timer
[habits.reconcile_completions] task 14 not in sync cache; cache last_polled_utc=2026-06-04T21:48:31Z. Vikunja may have added the task after the last driver tick; next tick will catch it.
[escalation.reconcile_completions] task 27 is private-project (data unavailable in cache).
[habits.set_due_dates] sync cache freshness pointer missing at /data/services/openclaw/state/sync/freshness.json. Recovery: cd ~/kg-automation && python3 -m scripts.sync.driver --bootstrap
[enrichment.reconcile_completions] state log enrichment-history.jsonl not found at /data/services/openclaw/state/enrichment-history.jsonl.
```

**Verification**: helper unit tests assert the exact message format. Per FR-006 + NFR-005.

---

## Testing contract

`tests/common/test_sync_cache.py` covers (at minimum):

- `read_cached_tasks` happy path: synthetic 3-task cache, fresh pointer, returns 3 views
- `read_cached_tasks` cache missing: raises with message containing "freshness pointer missing"
- `read_cached_tasks` stale: raises with message containing "stale beyond SLA_<NAME>" and age in seconds
- `read_cached_tasks` malformed JSON: raises with the underlying state.py message
- `read_cached_tasks` schema version mismatch: raises with the underlying state.py message
- `read_cached_task_by_id` happy path
- `read_cached_task_by_id` task missing: raises with message containing the task_id
- `read_cached_task_by_id` private: raises with message; no field content in the message
- `read_freshness_pointer` returns a `datetime` with `tzinfo=utc`
- `read_completion_timestamps` returns latest `complete` event
- `read_completion_timestamps` returns `(None, None)` when no completion exists for task_id
- `read_completion_timestamps` raises on missing state log file
- SLA tier constants have the expected (`name`, `seconds`) values
- `is_cache_healthy` returns True on a fresh cache and False on a stale one

Tests use `tmp_path` for state directory; `monkeypatch` to override `datetime.now(timezone.utc)` for deterministic stale tests; no live filesystem or network.
