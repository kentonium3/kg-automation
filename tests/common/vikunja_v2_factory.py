"""Fixture factory for the real Vikunja v2 task body (mission felix-rrule-adaptation, #1111).

A plain module, not a conftest, so any test package can import it::

    from tests.common.vikunja_v2_factory import make_task, strip_rule

The key set is the one captured live from ``GET /api/v2/tasks/14`` on
vikunja-harness ``d7e202228`` (research.md R-003), satisfying the charter
rule that fixtures mirror real inputs. Callers: WP02-WP10 test suites, which
migrate off the dead ``repeat_after`` / ``repeat_mode`` shape.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from datetime import timedelta, timezone
from typing import Any

from scripts.common.et_datetime import parse_vikunja_instant
from scripts.common.vikunja_rule import parts_to_rrule_text

#: Exact v2 single-task key set (research.md R-003), including ``$schema``.
V2_TASK_KEYS: tuple[str, ...] = (
    "$schema",
    "assignees",
    "attachments",
    "bucket_id",
    "cover_image_attachment_id",
    "created",
    "created_by",
    "description",
    "done",
    "done_at",
    "due_date",
    "end_date",
    "hex_color",
    "id",
    "identifier",
    "index",
    "is_favorite",
    "labels",
    "max_permission",
    "percent_done",
    "position",
    "priority",
    "project_id",
    "reactions",
    "related_tasks",
    "reminders",
    "repeat",
    "repeats_from_current_date",
    "repeats_rrule",
    "start_date",
    "subscription",
    "title",
    "updated",
)

_UNSET_INSTANT = "0001-01-01T00:00:00Z"


def _defaults() -> dict[str, Any]:
    return {
        "$schema": "https://vikunja.example.test/api/v2/schemas/Task.json",
        "assignees": None,
        "attachments": None,
        "bucket_id": 0,
        "cover_image_attachment_id": 0,
        "created": "2026-05-01T12:00:00Z",
        "created_by": {"id": 1, "username": "felix", "name": ""},
        "description": "",
        "done": False,
        "done_at": _UNSET_INSTANT,
        "due_date": "2026-11-20T04:59:59Z",
        "end_date": _UNSET_INSTANT,
        "hex_color": "",
        "id": 14,
        "identifier": "#14",
        "index": 14,
        "is_favorite": False,
        "labels": [],
        "max_permission": 2,
        "percent_done": 0,
        "position": 0,
        "priority": 0,
        "project_id": 2,
        "reactions": None,
        "related_tasks": {},
        "reminders": None,
        "repeat": {"freq": "daily", "interval": 1},
        "repeats_from_current_date": False,
        "repeats_rrule": "FREQ=DAILY;INTERVAL=1",
        "start_date": _UNSET_INSTANT,
        "subscription": None,
        "title": "Wake at 5:00 AM",
        "updated": "2026-11-19T12:00:00Z",
    }


def make_task(**overrides: Any) -> dict[str, Any]:
    """Return a v2 single-task body (``GET /api/v2/tasks/{id}``) with overrides.

    Use ``**{"$schema": ...}`` to override ``$schema``. When ``repeat`` is
    overridden and ``repeats_rrule`` is not, ``repeats_rrule`` is derived from
    it with :func:`parts_to_rrule_text`; overriding ``repeat`` with ``None``
    (no rule) drops ``repeats_rrule``, as :func:`strip_rule` does.
    """
    task = _defaults()
    task.update(copy.deepcopy(overrides))
    if "repeat" in overrides and "repeats_rrule" not in overrides:
        if task["repeat"]:
            task["repeats_rrule"] = parts_to_rrule_text(task["repeat"])
        else:
            task.pop("repeats_rrule", None)
    return task


def make_list_task(**overrides: Any) -> dict[str, Any]:
    """Return a task as v2 list endpoints serialise it: no ``repeats_rrule``."""
    task = make_task(**overrides)
    task.pop("repeats_rrule", None)
    return task


def with_reminder(
    task: Mapping[str, Any],
    relative_to: str = "due_date",
    relative_period: int = -3600,
) -> dict[str, Any]:
    """Return a copy of *task* with one relative reminder appended.

    The ``reminder`` instant is computed the way the server does it: the
    referenced date plus *relative_period* seconds, in UTC ``Z``
    (vikunja-harness d7e202228 ``updateRelativeReminderDates``). It is the
    unset sentinel only when the referenced date is absent. Periods of a day
    or more are applied as elapsed time here; the server applies whole days
    on the saver's calendar, so keep fixture periods under a day across DST.
    """
    out = copy.deepcopy(dict(task))
    reminders = list(out.get("reminders") or [])
    base = parse_vikunja_instant(out.get(relative_to))
    if base is None:
        reminder_at = _UNSET_INSTANT
    else:
        reminder_at = (base + timedelta(seconds=relative_period)).astimezone(
            timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
    reminders.append(
        {
            "reminder": reminder_at,
            "relative_period": relative_period,
            "relative_to": relative_to,
        }
    )
    out["reminders"] = reminders
    return out


def strip_rule(task: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy of *task* as a v1 narrow write leaves it: rule gone.

    ``repeat=None``, ``repeats_rrule`` absent, ``repeats_from_current_date``
    False. This is the positive control for every round-trip test.
    """
    out = copy.deepcopy(dict(task))
    out["repeat"] = None
    out.pop("repeats_rrule", None)
    out["repeats_from_current_date"] = False
    return out
