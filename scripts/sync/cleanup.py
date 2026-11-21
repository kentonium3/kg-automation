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

``prune_schedule_yaml`` edits the file **as text** when the ``habits:``
key is a top-level block sequence (the production shape): it deletes only
the lines of the matching ``- task_id: N`` item and leaves every other byte
alone. That keeps the header comments, every habit's ``rrule`` value and
the frozen ``operations:`` block (C-005, mission felix-rrule-adaptation,
#1111) byte-identical. A full re-serialisation cannot promise that — PyYAML
drops comments, and even ruamel's round-trip re-indents sequences — and
neither library is guaranteed to be installed (office2 has only PyYAML).
After the text edit the result is parsed back and must equal the original
data minus the pruned entry, or the function raises ``ValueError`` and
writes nothing.

The key may be bare or quoted (``habits:``, ``"habits":``, ``'habits':``).
Pruning the last habit writes ``habits: []``. Only when the file has no
top-level block ``habits:`` key (for example a flow-style mapping) **and
no** ``operations`` key does the function fall back to a library
round-trip: ``ruamel.yaml`` (round-trip mode) when available, else PyYAML
(``yaml.safe_load`` / ``yaml.safe_dump``), which drops comments. A file
with ``operations`` in an unsupported layout is refused (``ValueError``,
nothing written) rather than re-serialised (C-005).

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
   (list of str), and ``rrule`` (RFC 5545 text, #1111; it replaced
   ``repeat_after_seconds``). Pruning carries every surviving entry's
   keys through untouched.

``prune_schedule_yaml`` removes entries from the ``habits`` list by
matching on ``entry["task_id"]``. It preserves the rest of the
mapping (``mission_id``, ``operations``) untouched.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml as _safe_yaml

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

#: A top-level ``habits:`` key opening a block (nothing but a comment after it).
_HABITS_KEY_RE = re.compile(r"""^(?P<key>habits|"habits"|'habits'):[ \t]*(?P<comment>#.*)?$""")


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

    Deletes only the matching item's lines from the text (see "YAML library
    trade-off" in the module docstring), so comments, the surviving entries'
    ``rrule`` values and the frozen ``operations:`` block stay byte-identical
    (C-005). Falls back to a ruamel/PyYAML round-trip only when ``habits:``
    is not a top-level block key.

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
            is not a list of dicts — or if the text edit would not yield
            exactly the original schedule minus the entry (nothing written).
    """
    if not path.exists():
        return False

    text = path.read_text(encoding="utf-8")
    data = _safe_yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError(
            f"Expected schedule YAML at {path} to be a top-level mapping; "
            f"got {type(data).__name__}"
        )

    habits = data.get("habits")
    if habits is None:
        # No habits section — nothing to prune.
        return False

    if not isinstance(habits, list) or not all(isinstance(e, dict) for e in habits):
        raise ValueError(
            f"Expected 'habits' in {path} to be a list of dicts; "
            f"got {type(habits).__name__}"
        )

    new_habits = [entry for entry in habits if entry.get("task_id") != task_id]
    if len(new_habits) == len(habits):
        return False

    pruned_text = _prune_habits_text(text, task_id)
    if pruned_text is not None:
        expected = dict(data)
        expected["habits"] = new_habits
        try:
            reparsed = _safe_yaml.safe_load(pruned_text)
        except _safe_yaml.YAMLError:
            reparsed = None
        if reparsed != expected:
            raise ValueError(
                f"Refusing to prune task_id={task_id} from {path}: the text "
                f"edit did not yield the expected schedule (file left unchanged)"
            )
        path.write_text(pruned_text, encoding="utf-8")
        return True

    if "operations" in data:
        # C-005: a library round-trip re-serialises the frozen operations
        # record (comments dropped, sequences re-indented). Refuse instead.
        raise ValueError(
            f"Refusing to prune task_id={task_id} from {path}: its 'habits' key "
            f"is not a top-level block sequence, and rewriting the file through "
            f"a YAML library would change the frozen 'operations' record "
            f"(C-005). File left unchanged."
        )
    _rewrite_with_library(path, task_id)
    return True


def _prune_habits_text(text: str, task_id: int) -> str | None:
    """Delete the ``habits:`` block-sequence item(s) for ``task_id`` from *text*.

    Returns the edited text, or ``None`` when *text* has no top-level block
    ``habits:`` key (the caller then falls back to a library round-trip).
    An item is its ``-`` line plus the following non-blank lines indented
    deeper than the dash; blank lines and comments at or left of the dash
    column (group headings such as ``# ── Day-specific habits``) are kept.
    """
    lines = text.splitlines(keepends=True)
    try:
        header, match = next(
            (i, m)
            for i, ln in enumerate(lines)
            if (m := _HABITS_KEY_RE.match(ln.rstrip("\r\n")))
        )
    except StopIteration:
        return None
    kept_items = 0

    dash_indent: int | None = None
    keep: list[str] = lines[: header + 1]
    i = header + 1
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        indent = len(line) - len(line.lstrip(" "))
        if stripped and indent == 0 and not stripped.startswith(("#", "-")):
            break  # next top-level key: the habits section is over
        is_item = stripped.startswith("- ") or stripped == "-"
        if is_item and (dash_indent is None or indent == dash_indent):
            dash_indent = indent
            end = i + 1
            while end < len(lines):
                nxt = lines[end]
                nxt_indent = len(nxt) - len(nxt.lstrip(" "))
                if not nxt.strip() or nxt_indent <= dash_indent:
                    break
                end += 1
            item = lines[i:end]
            if not _item_has_task_id(item, dash_indent, task_id):
                keep.extend(item)
                kept_items += 1
            i = end
            continue
        keep.append(line)
        i += 1
    keep.extend(lines[i:])
    if kept_items == 0 and dash_indent is not None:
        # The last habit was pruned: a bare ``habits:`` would parse as null,
        # so write an explicit empty sequence on the key line.
        old = lines[header]
        newline = old[len(old.rstrip("\r\n")):]
        comment = match.group("comment")
        keep[header] = f"{match.group('key')}: []" + (f"  {comment}" if comment else "") + newline
    return "".join(keep)


def _item_has_task_id(item: list[str], dash_indent: int, task_id: int) -> bool:
    """True when the block-sequence *item* text is a mapping with ``task_id``."""
    body = "".join(ln[dash_indent:] if len(ln) > dash_indent else ln.lstrip(" ") for ln in item)
    try:
        parsed = _safe_yaml.safe_load(body)
    except _safe_yaml.YAMLError:
        return False
    return (
        isinstance(parsed, list)
        and len(parsed) == 1
        and isinstance(parsed[0], dict)
        and parsed[0].get("task_id") == task_id
    )


def _rewrite_with_library(path: Path, task_id: int) -> None:
    """Fallback for a non-block ``habits:`` key: library round-trip (may lose comments)."""
    if _USING_RUAMEL:
        yaml = _make_yaml()
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.load(f)
    else:
        with open(path, "r", encoding="utf-8") as f:
            data = _pyyaml.safe_load(f)  # type: ignore[union-attr]
    data["habits"] = [e for e in data["habits"] if e.get("task_id") != task_id]
    if _USING_RUAMEL:
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)
    else:
        with open(path, "w", encoding="utf-8") as f:
            _pyyaml.safe_dump(data, f, default_flow_style=False)  # type: ignore[union-attr]
