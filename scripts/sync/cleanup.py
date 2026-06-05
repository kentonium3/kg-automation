"""Deletion-cleanup helpers for the Felix-Vikunja sync driver Phase 5b.

Mission #520 (felix-vikunja-sync-project-layer-and-url-config-01KTCDZ7), FR-003.
See ``kitty-specs/felix-vikunja-sync-project-layer-and-url-config-01KTCDZ7/
contracts/cycle-pipeline.md`` § Phase 5b for the orchestration contract.

This module provides two pure side-effect helpers. No orchestration logic,
no cycle integration — WP04 imports both and wires them into the cycle.

------------------------------------------------------------------------
Atomicity guarantees
------------------------------------------------------------------------

``append_task_deleted_event``:
    Opens the target JSONL file in append mode (``"a"``). POSIX guarantees
    that ``write`` calls smaller than PIPE_BUF (~4 KB on Linux) are atomic.
    A single event line is well under 200 bytes, so concurrent writes from
    a single process are safe. The function is NOT atomic in the
    database-transaction sense (no rollback), but a partial write is
    practically impossible at these sizes.

``prune_schedule_yaml``:
    Uses a read-modify-write pattern, which is NOT atomic end-to-end.
    A crash between the read and the write leaves the file in its
    original state (no partial state). Because ``prune_schedule_yaml``
    is idempotent (see below), a retry on the next cycle recovers cleanly.

------------------------------------------------------------------------
Idempotency guarantees
------------------------------------------------------------------------

``append_task_deleted_event`` is **NOT** idempotent:
    Re-running for the same ``task_id`` appends a duplicate event.
    This is acceptable — the audit log is append-only and the duplicate
    shows that cleanup was attempted twice, which is a useful signal.

``prune_schedule_yaml`` IS idempotent:
    If the entry for ``task_id`` is already absent, the function returns
    ``False`` and writes nothing. Repeat calls are safe.

------------------------------------------------------------------------
Event schema (mirrored from data-model.md § TaskDeletedEvent)
------------------------------------------------------------------------

Each event appended by ``append_task_deleted_event`` has this shape:

.. code-block:: json

    {
      "event_type": "task_deleted",
      "task_id": 42,
      "title": "Wake at 5:00 AM",
      "detected_at_utc": "2026-06-05T20:00:00Z",
      "schema_version": 1
    }

Field notes:
- ``event_type`` — literal ``"task_deleted"``; matches existing
  habits-history.jsonl event-type conventions.
- ``task_id`` — positive integer; the Vikunja task.id.
- ``title`` — last-known task title from the task cache before deletion.
- ``detected_at_utc`` — ISO-8601 UTC timestamp (``"YYYY-MM-DDTHH:MM:SSZ"``).
- ``schema_version`` — always ``1`` in this implementation.

------------------------------------------------------------------------
YAML library trade-off
------------------------------------------------------------------------

``prune_schedule_yaml`` uses ``ruamel.yaml`` (round-trip mode) when
available, which preserves YAML comments, block-style ordering, and
inline whitespace. This is the production path — the schedule YAML
contains multi-line header comments that must survive the round-trip.

When ``ruamel.yaml`` is not installed (test environments without it),
the function falls back to PyYAML (``yaml.safe_load`` / ``yaml.safe_dump``).
The fallback drops all comments and may reorder keys. Tests that assert
comment preservation are skipped via ``pytest.mark.skipif`` when ruamel
is unavailable.

The ``try/except ImportError`` check runs at module import time so the
``_USING_RUAMEL`` flag is set once, not on every function call.

------------------------------------------------------------------------
Verified structure of phase3-schedule.yaml
------------------------------------------------------------------------

Inspected ``scripts/habits/migrations/phase3-schedule.yaml`` directly
(2026-06-05). Key findings:

1. The top-level YAML value is a **dict** (mapping), NOT a list.
   Top-level keys: ``mission_id``, ``operations``, ``habits``.

2. ``operations`` — list of dicts; frozen one-shot migration record
   consumed by ``migrate_schedule.py``. Each dict has a ``task_id``
   key (plus ``op``, ``target``, etc.). This section is NOT touched
   by ``prune_schedule_yaml``.

3. ``habits`` — list of dicts; the runtime schedule consumed by
   ``scripts/habits/schedule_loader.py``. Each dict has ``task_id``
   (positive int), ``title`` (str), optional ``designated_weekdays``
   (list of str), and ``repeat_after_seconds`` (int).

``prune_schedule_yaml`` removes entries from the ``habits`` list by
matching on ``entry["task_id"]``. It preserves the rest of the
mapping (``mission_id``, ``operations``) untouched.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from ruamel.yaml import YAML as _RuamelYAML

    def _make_yaml() -> Any:
        return _RuamelYAML(typ="rt")

    _USING_RUAMEL = True
except ImportError:
    import yaml as _pyyaml  # type: ignore[import-not-found]

    def _make_yaml() -> Any:  # type: ignore[misc]
        return _pyyaml

    _USING_RUAMEL = False


_SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# append_task_deleted_event
# ---------------------------------------------------------------------------


def append_task_deleted_event(
    task_id: int,
    title: str,
    detected_at_utc: str,
    path: Path,
) -> None:
    """Append a task_deleted event to a JSONL audit log.

    Atomic at small write sizes via stdlib's append-mode open. NOT idempotent
    — re-running produces a duplicate event (acceptable; the audit trail is
    append-only).

    Args:
        task_id: Positive integer task identifier (Vikunja task.id).
        title: Last-known task title before deletion (from cache).
        detected_at_utc: ISO-8601 UTC timestamp (``"YYYY-MM-DDTHH:MM:SSZ"``).
        path: Target JSONL file (e.g.,
            ``scripts/habits/state/habits-history.jsonl``).

    Raises:
        ValueError: If ``task_id`` is not a positive integer.
        OSError: On filesystem failure. Caller decides whether to abort
            the cycle or skip this task_id and continue.
    """
    if not isinstance(task_id, int) or isinstance(task_id, bool) or task_id <= 0:
        raise ValueError(f"task_id must be a positive integer; got {task_id!r}")
    event = {
        "event_type": "task_deleted",
        "task_id": task_id,
        "title": title,
        "detected_at_utc": detected_at_utc,
        "schema_version": _SCHEMA_VERSION,
    }
    line = json.dumps(event, separators=(",", ":")) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)


# ---------------------------------------------------------------------------
# prune_schedule_yaml
# ---------------------------------------------------------------------------


def prune_schedule_yaml(task_id: int, path: Path) -> bool:
    """Remove the entry for ``task_id`` from the ``habits:`` list in a schedule YAML.

    Round-trips the YAML preserving comments + ordering when ruamel.yaml is
    available; falls back to PyYAML (comments lost) for environments without
    ruamel.

    The schedule YAML is a top-level mapping with (at minimum) a ``habits:``
    key whose value is a list of dicts. Each dict has a ``task_id`` key.
    This function targets **only** the ``habits:`` list; the ``operations:``
    section and other top-level keys are preserved untouched.

    Idempotent — if the entry is already absent, returns ``False`` and
    writes nothing.

    Args:
        task_id: Positive integer; the ``habits`` entry with this ``task_id``
            is removed.
        path: Path to the schedule YAML file
            (e.g., ``scripts/habits/migrations/phase3-schedule.yaml``).

    Returns:
        ``True`` if an entry was removed; ``False`` if no matching entry was
        found (idempotent — repeat calls return ``False``).

    Raises:
        OSError: On filesystem failure.
        ValueError: If the YAML body is malformed — specifically if the
            top-level value is not a dict, or if ``habits`` is present but
            is not a list of dicts.
    """
    if not path.exists():
        return False

    if _USING_RUAMEL:
        yaml = _make_yaml()
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.load(f)
    else:
        with open(path, "r", encoding="utf-8") as f:
            data = _pyyaml.safe_load(f)  # type: ignore[union-attr]

    if not isinstance(data, dict):
        raise ValueError(
            f"Expected schedule YAML at {path} to be a top-level mapping; "
            f"got {type(data).__name__}"
        )

    habits = data.get("habits")
    if habits is None:
        # No habits section — nothing to prune.
        return False

    if not isinstance(habits, list):
        raise ValueError(
            f"Expected 'habits' in {path} to be a list of dicts; "
            f"got {type(habits).__name__}"
        )

    original_len = len(habits)
    new_habits = [entry for entry in habits if entry.get("task_id") != task_id]

    if len(new_habits) == original_len:
        return False

    # Update the habits list in-place for ruamel (preserves other top-level keys).
    data["habits"] = new_habits

    if _USING_RUAMEL:
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)
    else:
        with open(path, "w", encoding="utf-8") as f:
            _pyyaml.safe_dump(data, f, default_flow_style=False)  # type: ignore[union-attr]

    return True
