#!/usr/bin/env python3
"""Central loader for the habit runtime schedule (mission #408 / WP-01).

Reads the ``habits:`` top-level section of
``scripts/habits/migrations/phase3-schedule.yaml`` and returns typed
``ScheduleEntry`` instances. This is the **single** parse surface for the
runtime schedule — ``morning_checkin_list.py``, ``query_active_habits_v2``,
``set_due_dates.py --reconcile-schedule``, and the future
``sweeper.py`` all consume the loader so the YAML is parsed in exactly
one place.

The existing ``operations:`` section of the YAML is the frozen mission #282
migration record and is consumed by ``migrate_schedule.py``. This loader
ignores ``operations:`` entirely and only reads ``habits:``.

Public API:

  ``load_schedule(path) -> list[ScheduleEntry]``
      Parse and validate the YAML; raise ``ScheduleConfigError`` on any
      load-time validation failure (unknown weekday name, malformed entry,
      duplicate task_id, etc.).

  ``is_day_specific(entry) -> bool``
      ``True`` iff the entry has at least one designated weekday.

  ``is_active_today(entry, today_weekday) -> bool``
      ``True`` if the entry is daily (no designated weekdays) OR
      ``today_weekday`` is in the entry's designated set.

  ``ScheduleConfigError``
      Raised for every load-time validation failure.

  ``WEEKDAY_NAMES``
      Canonical 3-letter ISO weekday tuple ``("Mon", ..., "Sun")``.

Contract: ``kitty-specs/habit-day-specific-scheduling-01KT48Y6/contracts/schedule-config.contract.md``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


#: Canonical 3-letter ISO weekday names in Mon=0..Sun=6 order.
WEEKDAY_NAMES: tuple[str, ...] = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

#: Frozen set form for O(1) membership checks.
_WEEKDAY_SET: frozenset[str] = frozenset(WEEKDAY_NAMES)


class ScheduleConfigError(Exception):
    """Raised for any load-time validation failure of the habits schedule.

    The message names the offending entry index + field + violation so the
    operator can fix the YAML without grepping.
    """


@dataclass(frozen=True, slots=True)
class ScheduleEntry:
    """One habit's runtime scheduling metadata.

    Attributes:
        task_id: Vikunja task identifier (the immutable per-task integer id —
            NOT the Vikunja UI ``identifier`` like ``"#10"``).
        title: Display title, mirroring Vikunja's title for human-readability.
        designated_weekdays: Tuple of 3-letter ISO weekday abbreviations. Empty
            tuple = daily habit (appears every day). Non-empty = day-specific
            habit (appears only on listed weekdays).
        repeat_after_seconds: Vikunja-native repeat interval in seconds.
    """

    task_id: int
    title: str
    designated_weekdays: tuple[str, ...] = field(default_factory=tuple)
    repeat_after_seconds: int = 0


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _normalize_designated_weekdays(
    raw: Any,
    *,
    entry_index: int,
) -> tuple[str, ...]:
    """Validate + dedupe a raw ``designated_weekdays`` value into a tuple.

    Preserves the input ordering of first occurrence; downstream consumers do
    not depend on ordering, but stable ordering aids reproducible test output.
    """
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ScheduleConfigError(
            f"habits[{entry_index}].designated_weekdays must be a list "
            f"(got {type(raw).__name__})"
        )
    seen: set[str] = set()
    ordered: list[str] = []
    for j, item in enumerate(raw):
        if not isinstance(item, str):
            raise ScheduleConfigError(
                f"habits[{entry_index}].designated_weekdays[{j}] must be a "
                f"string (got {type(item).__name__})"
            )
        if item not in _WEEKDAY_SET:
            raise ScheduleConfigError(
                f"habits[{entry_index}].designated_weekdays[{j}] {item!r} is "
                f"not a valid 3-letter ISO weekday — expected one of "
                f"{list(WEEKDAY_NAMES)}"
            )
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return tuple(ordered)


def _validate_entry(raw: Any, *, entry_index: int) -> ScheduleEntry:
    """Validate one raw dict entry and return a ``ScheduleEntry``."""
    if not isinstance(raw, dict):
        raise ScheduleConfigError(
            f"habits[{entry_index}] must be a YAML mapping "
            f"(got {type(raw).__name__})"
        )

    task_id = raw.get("task_id")
    if not isinstance(task_id, int) or isinstance(task_id, bool) or task_id <= 0:
        raise ScheduleConfigError(
            f"habits[{entry_index}].task_id must be a positive integer "
            f"(got {task_id!r})"
        )

    title = raw.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ScheduleConfigError(
            f"habits[{entry_index}].title must be a non-empty string "
            f"(got {title!r})"
        )

    repeat_after = raw.get("repeat_after_seconds", 0)
    if (
        not isinstance(repeat_after, int)
        or isinstance(repeat_after, bool)
        or repeat_after < 0
    ):
        raise ScheduleConfigError(
            f"habits[{entry_index}].repeat_after_seconds must be a "
            f"non-negative integer (got {repeat_after!r})"
        )

    weekdays = _normalize_designated_weekdays(
        raw.get("designated_weekdays"), entry_index=entry_index
    )

    return ScheduleEntry(
        task_id=task_id,
        title=title,
        designated_weekdays=weekdays,
        repeat_after_seconds=repeat_after,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_schedule(path: Path | str) -> list[ScheduleEntry]:
    """Load and validate the ``habits:`` section of the schedule YAML.

    Args:
        path: Filesystem path to the schedule YAML file.

    Returns:
        A list of validated ``ScheduleEntry`` instances. Empty if the YAML
        has no ``habits:`` section (a valid but degenerate configuration).

    Raises:
        ScheduleConfigError: On any validation failure (unknown weekday,
            malformed entry shape, duplicate task_id, etc.). Also wraps
            YAML parse errors and missing files so callers handle one
            exception type.
    """
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ScheduleConfigError(
            f"schedule file not found: {path}"
        ) from exc
    except OSError as exc:  # pragma: no cover -- FileNotFoundError handled above
        raise ScheduleConfigError(
            f"failed reading schedule file {path}: {exc}"
        ) from exc

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ScheduleConfigError(
            f"YAML parse error in {path}: {exc}"
        ) from exc

    if data is None:
        return []
    if not isinstance(data, dict):
        raise ScheduleConfigError(
            f"schedule file {path} top-level must be a YAML mapping "
            f"(got {type(data).__name__})"
        )

    raw_habits = data.get("habits")
    if raw_habits is None:
        return []
    if not isinstance(raw_habits, list):
        raise ScheduleConfigError(
            f"schedule file {path} 'habits' must be a list "
            f"(got {type(raw_habits).__name__})"
        )

    entries: list[ScheduleEntry] = []
    seen_task_ids: set[int] = set()
    for i, raw in enumerate(raw_habits):
        entry = _validate_entry(raw, entry_index=i)
        if entry.task_id in seen_task_ids:
            raise ScheduleConfigError(
                f"habits[{i}].task_id {entry.task_id} duplicates an earlier "
                f"entry — each habit must appear at most once"
            )
        seen_task_ids.add(entry.task_id)
        entries.append(entry)
    return entries


def is_day_specific(entry: ScheduleEntry) -> bool:
    """``True`` iff the entry has at least one designated weekday set."""
    return len(entry.designated_weekdays) > 0


def is_active_today(entry: ScheduleEntry, today_weekday: str) -> bool:
    """``True`` if the entry should appear in today's check-in.

    Daily habits (no designated weekdays) are always active. Day-specific
    habits are active only on a listed weekday.

    Args:
        entry: A ``ScheduleEntry`` from ``load_schedule``.
        today_weekday: A 3-letter ISO weekday name (``"Mon"`` .. ``"Sun"``).
            Typically produced by ``compute_today.compute_today()``'s ``day``
            field.

    Returns:
        ``True`` if the entry is active today, else ``False``.

    Raises:
        ValueError: ``today_weekday`` is not in ``WEEKDAY_NAMES``.
    """
    if today_weekday not in _WEEKDAY_SET:
        raise ValueError(
            f"today_weekday {today_weekday!r} must be one of "
            f"{list(WEEKDAY_NAMES)}"
        )
    if not entry.designated_weekdays:
        return True
    return today_weekday in entry.designated_weekdays
