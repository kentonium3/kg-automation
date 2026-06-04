"""Felix sync cache: canonical cache-read helper for touchpoints (mission #519).

This is the sole entry point for every migrated touchpoint to read task state
from the Felix-Vikunja sync driver cache.  No touchpoint imports
``scripts.sync.state`` or any state-log code directly (spec C-004).

Data model
----------
- ``task-cache.json``  — the driver's local view of all tracked Vikunja tasks.
- ``freshness.json``   — per-layer UTC pointer; age compared against SLA.
- ``{domain}-history.jsonl`` — per-domain state log used to derive
  completion timestamps (``done_at`` equivalent) for reconciler touchpoints.

All public functions raise ``OSError`` with a structured message on failure.
None of them make HTTP calls, write state, or touch the production path at
import time.

Public surface
--------------
Constants: SLA_HOT, SLA_NORMAL, SLA_BATCH, SLA_LOOSE
Dataclasses: SLATier, TaskCacheView, CompletionTimestamps
Functions: read_cached_tasks, read_cached_task_by_id, read_freshness_pointer,
           read_completion_timestamps, is_cache_healthy
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.sync.state import (
    STATE_DIR_DEFAULT,
    read_freshness,
    read_task_cache,
)

__all__ = [
    # SLA tier constants
    "SLA_HOT",
    "SLA_NORMAL",
    "SLA_BATCH",
    "SLA_LOOSE",
    # Dataclasses
    "SLATier",
    "TaskCacheView",
    "CompletionTimestamps",
    # Functions
    "read_cached_tasks",
    "read_cached_task_by_id",
    "read_freshness_pointer",
    "read_completion_timestamps",
    "is_cache_healthy",
]


# ---------------------------------------------------------------------------
# SLA tier definitions — see kitty-specs/.../research.md Unknown 1
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SLATier:
    """Named freshness-SLA tier.  Callers compare pointer age against seconds."""

    name: str
    seconds: int


SLA_HOT = SLATier("HOT", 60)
SLA_NORMAL = SLATier("NORMAL", 900)
SLA_BATCH = SLATier("BATCH", 3600)
SLA_LOOSE = SLATier("LOOSE", 86400)


# ---------------------------------------------------------------------------
# Public data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TaskCacheView:
    """Read-only view of a single Vikunja task from the sync cache.

    ``fields`` contains the 7 TRACKED_TASK_FIELDS when ``is_private`` is False;
    ``fields`` is an empty dict when ``is_private`` is True (the privacy
    boundary — never log or surface field content for private tasks).
    """

    task_id: int
    fields: dict[str, Any]
    vikunja_updated_at: str
    is_private: bool


@dataclass(frozen=True)
class CompletionTimestamps:
    """Most-recent ``state == "complete"`` timestamps for a task from a JSONL log.

    Both fields are ``None`` when the task has no completion history — that is
    NOT an error condition; fresh tasks legitimately have no history.
    """

    most_recent_complete_at_utc: str | None
    most_recent_complete_date_et: str | None


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _format_error(
    touchpoint_name: str | None,
    summary: str,
    recovery: str,
) -> str:
    """Build the canonical structured error message.

    Format: ``[<touchpoint_name>] <summary>. Recovery: <recovery>.``
    When ``touchpoint_name`` is None, the bracket prefix is omitted so the
    message remains readable for operator one-liners.
    """
    prefix = f"[{touchpoint_name}] " if touchpoint_name else ""
    return f"{prefix}{summary}. Recovery: {recovery}."


def _parse_utc(ts: str) -> datetime:
    """Parse an ISO-8601 UTC string into a timezone-aware datetime.

    Accepts both the ``Z`` suffix (from the driver) and the ``+00:00``
    offset form (from ``datetime.isoformat()``).
    """
    normalized = ts.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized).replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


def read_cached_tasks(
    sla: SLATier,
    state_dir: Path | None = None,
    *,
    touchpoint_name: str | None = None,
) -> dict[int, TaskCacheView]:
    """Read every task in the sync cache, enforcing the caller's freshness SLA.

    Args:
        sla: The touchpoint's freshness SLA.  Raises ``OSError`` if the
            pointer age (now_utc - last_polled_utc) exceeds ``sla.seconds``.
        state_dir: Cache directory.  ``None`` (default) uses
            ``STATE_DIR_DEFAULT`` resolved at call time so monkeypatching in
            tests works correctly.
        touchpoint_name: For error messages.  Optional but RECOMMENDED so
            operators can identify which touchpoint raised the error.

    Returns:
        A dict mapping ``task_id`` (int) to :class:`TaskCacheView`.
        Private-project tasks are included with empty ``fields`` and
        ``is_private=True``; the caller decides whether to skip or raise.

    Raises:
        OSError: On cache file missing, freshness file missing,
            stale-beyond-SLA, malformed JSON, or schema-version mismatch.
            Message format: ``[<tp>] <summary>. Recovery: <hint>.``
    """
    if state_dir is None:
        state_dir = STATE_DIR_DEFAULT  # resolved at call time from module globals

    # Step 1 — read freshness pointer
    try:
        pointer = read_freshness(state_dir)
    except OSError:
        freshness_path = state_dir / "freshness.json"
        raise OSError(
            _format_error(
                touchpoint_name,
                f"sync cache freshness pointer missing at {freshness_path}",
                "cd ~/kg-automation && python3 -m scripts.sync.driver --bootstrap",
            )
        )

    # Step 2 — compute pointer age and compare against SLA
    # The pointer layer name used by the driver is "status_and_task".
    layer = pointer.layers.get("status_and_task")
    if layer is None:
        # Fallback: use last_updated_utc from the pointer itself
        last_polled_utc_str = pointer.last_updated_utc
    else:
        last_polled_utc_str = layer.last_polled_utc

    last_polled_utc = _parse_utc(last_polled_utc_str)
    now_utc = datetime.now(timezone.utc)
    age_seconds = (now_utc - last_polled_utc).total_seconds()

    if age_seconds > sla.seconds:
        raise OSError(
            _format_error(
                touchpoint_name,
                (
                    f"sync cache stale beyond SLA_{sla.name} (max {sla.seconds}s); "
                    f"pointer age {age_seconds:.0f}s"
                ),
                "systemctl --user status felix-vikunja-sync.timer",
            )
        )

    # Step 3 — read task cache (propagates OSError on malformed/schema-mismatch)
    task_cache = read_task_cache(state_dir)

    # Step 4 — translate TaskCacheRecord → dict[int, TaskCacheView]
    result: dict[int, TaskCacheView] = {}
    for task_id_str, entry in task_cache.tasks.items():
        task_id = int(task_id_str)
        is_private = entry.fields == {}
        result[task_id] = TaskCacheView(
            task_id=task_id,
            fields=entry.fields,
            vikunja_updated_at=entry.vikunja_updated_at,
            is_private=is_private,
        )

    return result


def read_cached_task_by_id(
    task_id: int,
    sla: SLATier,
    state_dir: Path | None = None,
    *,
    touchpoint_name: str | None = None,
) -> TaskCacheView:
    """Read one task by its integer ``task_id`` from the sync cache.

    Args:
        task_id: The Vikunja integer task id.
        sla: As for :func:`read_cached_tasks`.
        state_dir: As for :func:`read_cached_tasks`.
        touchpoint_name: As for :func:`read_cached_tasks`.

    Returns:
        :class:`TaskCacheView` for the requested task.

    Raises:
        OSError: All cases from :func:`read_cached_tasks` plus task-not-found
            (message includes ``task_id`` and ``last_polled_utc``) and
            private-task (message includes ``task_id`` but NO field content).
    """
    if state_dir is None:
        state_dir = STATE_DIR_DEFAULT  # resolved at call time from module globals

    # Step 1 — read full cache (re-raises its errors)
    tasks = read_cached_tasks(sla, state_dir, touchpoint_name=touchpoint_name)

    # Also read the pointer so we can include last_polled_utc in the
    # task-not-found message (the pointer was already validated above, so
    # this second read is cheap).
    try:
        pointer = read_freshness(state_dir)
        layer = pointer.layers.get("status_and_task")
        if layer is not None:
            last_polled_utc_str = layer.last_polled_utc
        else:
            last_polled_utc_str = pointer.last_updated_utc
    except OSError:
        last_polled_utc_str = "unknown"

    # Step 2 — look up task_id
    if task_id not in tasks:
        raise OSError(
            _format_error(
                touchpoint_name,
                (
                    f"task {task_id} not in sync cache; "
                    f"cache last_polled_utc={last_polled_utc_str}"
                ),
                (
                    "Vikunja may have added the task after the last driver tick; "
                    "next tick will catch it"
                ),
            )
        )

    view = tasks[task_id]

    # Step 3 — private-task boundary: raise without field content
    if view.is_private:
        raise OSError(
            _format_error(
                touchpoint_name,
                f"task {task_id} is private-project (data unavailable in cache)",
                "Contact the operator if this task should be in a non-private project",
            )
        )

    return view


def read_freshness_pointer(
    state_dir: Path | None = None,
    *,
    touchpoint_name: str | None = None,
) -> datetime:
    """Return the cache's freshness pointer as a timezone-aware UTC datetime.

    Used by tests and ad-hoc operator queries:

        python3 -c "from scripts.common import sync_cache; print(sync_cache.read_freshness_pointer())"

    Args:
        state_dir: Cache directory.  ``None`` (default) uses
            ``STATE_DIR_DEFAULT`` resolved at call time.
        touchpoint_name: For error messages.

    Returns:
        ``datetime`` with ``tzinfo=timezone.utc``.

    Raises:
        OSError: On freshness file missing or malformed.
    """
    if state_dir is None:
        state_dir = STATE_DIR_DEFAULT  # resolved at call time from module globals

    try:
        pointer = read_freshness(state_dir)
    except OSError as exc:
        prefix = f"[{touchpoint_name}] " if touchpoint_name else ""
        raise OSError(f"{prefix}{exc}") from exc

    layer = pointer.layers.get("status_and_task")
    if layer is not None:
        ts = layer.last_polled_utc
    else:
        ts = pointer.last_updated_utc

    return _parse_utc(ts)


def read_completion_timestamps(
    domain: str,
    task_id: int,
    state_log_dir: Path,
) -> CompletionTimestamps:
    """Return the most recent ``state == "complete"`` timestamps for ``task_id``.

    Scans ``{state_log_dir}/{domain}-history.jsonl`` and returns the row with
    the latest ``timestamp`` where ``state == "complete"`` and ``task_id``
    matches.  Malformed JSONL lines are skipped defensively.

    Args:
        domain: One of ``"habits"``, ``"escalation"``, ``"enrichment"``.
            Used to derive the JSONL filename: ``f"{domain}-history.jsonl"``.
        task_id: The Vikunja integer task id.
        state_log_dir: Directory containing the state log JSONL.
            (Typically ``/data/services/openclaw/state/``.)

    Returns:
        :class:`CompletionTimestamps`.  Both fields are ``None`` when the
        task has no completion history — this is NOT an error.

    Raises:
        OSError: On state log file missing.
    """
    log_path = state_log_dir / f"{domain}-history.jsonl"
    if not log_path.exists():
        raise OSError(
            _format_error(
                None,
                f"state log {domain}-history.jsonl not found at {log_path}",
                f"cd ~/kg-automation && python3 -m scripts.common.state_log read --domain {domain}",
            )
        )

    best_timestamp: str | None = None
    best_date_et: str | None = None

    with open(log_path, "r", encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except (ValueError, TypeError):
                # Defensive: skip malformed lines
                continue
            if not isinstance(row, dict):
                continue
            if row.get("state") != "complete":
                continue
            if row.get("task_id") != task_id:
                continue
            row_ts = row.get("timestamp")
            if not isinstance(row_ts, str):
                continue
            # Track the row with the latest ISO-8601 timestamp.
            # Simple string comparison works for ISO-8601 UTC timestamps
            # when the format is consistent (which the JSONL schema guarantees).
            if best_timestamp is None or row_ts > best_timestamp:
                best_timestamp = row_ts
                best_date_et = row.get("date")

    return CompletionTimestamps(
        most_recent_complete_at_utc=best_timestamp,
        most_recent_complete_date_et=best_date_et,
    )


def is_cache_healthy(
    sla: SLATier,
    state_dir: Path | None = None,
) -> bool:
    """Non-raising health check for the sync cache.

    Used by ``quickstart.md`` verification commands and operator-side smoke
    tests.  Production touchpoints use the raising APIs above.

    Args:
        sla: The SLA tier to test freshness against.
        state_dir: Cache directory.  ``None`` (default) uses
            ``STATE_DIR_DEFAULT`` resolved at call time.

    Returns:
        ``True`` if :func:`read_cached_tasks` would succeed with ``sla``.
        ``False`` on any :exc:`OSError`.
    """
    if state_dir is None:
        state_dir = STATE_DIR_DEFAULT  # resolved at call time from module globals
    try:
        read_cached_tasks(sla, state_dir)
        return True
    except OSError:
        return False
