"""Shared Vikunja scope config: the single source for Vikunja selectors.

Decouples escalation and habit logic from the concrete Vikunja project/label
taxonomy (mission ``deterministic-cron-hardening-01KXA4PX``, issue
kentonium3/kg-automation#723, FR-008/NFR-004). The #714 Vikunja
reorganization may move habit identity from a project id to a label; when
that happens, the swap is a **value edit in this module only** — consumers
never hardcode ids.

Authoritative contract:
``kitty-specs/deterministic-cron-hardening-01KXA4PX/contracts/vikunja_scope.md``.
Data model: ``data-model.md`` → ``VikunjaScopeConfig``.

Scope boundary (post-plan review H5/H6, authoritative)
-------------------------------------------------------
This module ships the config **seam** plus the ``project_id`` selector form
only. ``habit_selector`` is shaped so a future ``{"kind": "label", ...}``
value is representable, but the **label fetch strategy** (a
``list_habit_tasks(client, selector)`` that dispatches on ``kind``) is
explicitly OUT OF SCOPE here — it is issue #716's work. Until #716 lands,
:func:`habit_project_id` returns ``None`` for a label selector, and callers
MUST raise rather than silently misbehave (see
``scripts/habits/query_active_habits_weekly.py``). Likewise, escalation
exclusion (:func:`get_escalation_excluded_project_ids`) remains
project-ID-only; re-deriving exclusion from ``habit_selector`` when it is a
label is also #716's work.

Per Felix Constitution Directive 6 this is the deterministic config layer:
no I/O, no network, no heavy dependencies. Pure constants + accessor
functions.

Public surface
--------------
Constants: ``ESCALATION_EXCLUDED_PROJECT_IDS``, ``HABIT_SELECTOR``
Functions: ``get_escalation_excluded_project_ids``, ``get_habit_selector``,
    ``habit_project_id``
"""
from __future__ import annotations

__all__ = [
    "ESCALATION_EXCLUDED_PROJECT_IDS",
    "HABIT_SELECTOR",
    "get_escalation_excluded_project_ids",
    "get_habit_selector",
    "habit_project_id",
]

#: Project ids that escalation excludes from candidate enumeration.
#: Today: Habits (13) only. Goals (11) was deleted by #717 (its tasks moved
#: to Intentional LLC and are now normal escalation candidates), so it is no
#: longer excluded. Project-ID-only (see H6 above) — re-deriving this from
#: ``habit_selector`` when it becomes a label is #716's work.
ESCALATION_EXCLUDED_PROJECT_IDS: list[int] = [13]

#: Habit identity selector. ``kind`` is ``"project_id"`` or ``"label"``;
#: today's value uses ``project_id``. A future #714/#716 label move sets
#: this to e.g. ``{"kind": "label", "value": "t:habit"}`` — a config edit,
#: not a logic change, once #716 ships the label fetch strategy.
HABIT_SELECTOR: dict[str, object] = {"kind": "project_id", "value": 13}

_VALID_SELECTOR_KINDS = frozenset({"project_id", "label"})


def _validate_selector(selector: dict) -> None:
    kind = selector.get("kind")
    if kind not in _VALID_SELECTOR_KINDS:
        raise ValueError(
            f"Unknown habit selector kind {kind!r}: expected one of "
            f"{sorted(_VALID_SELECTOR_KINDS)}"
        )


def get_escalation_excluded_project_ids() -> list[int]:
    """Return the project ids escalation excludes from enumeration.

    Returns a copy — callers may not mutate module state via the result.
    """
    return list(ESCALATION_EXCLUDED_PROJECT_IDS)


def get_habit_selector() -> dict:
    """Return the habit identity selector: ``{"kind": ..., "value": ...}``.

    Returns a copy — callers may not mutate module state via the result.
    Validates ``kind`` against the known selector kinds, raising
    :class:`ValueError` on an unknown kind.
    """
    selector = dict(HABIT_SELECTOR)
    _validate_selector(selector)
    return selector


def habit_project_id() -> int | None:
    """Return the habit project id, or ``None`` if the selector is a label.

    Convenience accessor for the ``project_id`` selector form (the only form
    this mission's fetch path supports — see module docstring). Returns the
    int value when ``get_habit_selector()["kind"] == "project_id"``,
    otherwise ``None`` (label form — not fetchable until #716 ships the
    label fetch strategy).
    """
    selector = get_habit_selector()
    if selector["kind"] == "project_id":
        value = selector["value"]
        return int(value) if isinstance(value, int) else None
    return None
