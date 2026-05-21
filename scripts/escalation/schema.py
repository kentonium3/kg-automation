"""Per-event_type parameter schema for the escalation domain.

This module is the structured-parameter half of the escalation JSONL schema.
The Phase 2 ``state_log.validate_record`` already enforces the seven shared
required fields (``domain``, ``task_id``, ``title``, ``date``, ``state``,
``source``, ``timestamp``) plus the optional ``note`` field. Escalation
records also carry a flat-enum ``state`` (see ``DOMAIN_STATES["escalation"]``
in ``scripts/common/state_log_schema.py``) plus per-event_type structured
parameters captured below.

Reviewer surface (NFR-005): every event_type's required parameters are
enumerated in ``EVENT_TYPE_PARAMETERS`` and validated in
``validate_event_params``. A reviewer reading this file alone can answer
"what fields must a ``state=<x>`` record carry?" without running tests.

Required parameters per event_type
----------------------------------

- ``level_sent``: ``level`` (int in {1, 2}).
- ``snoozed``: ``snooze_days`` (int > 0) + ``snooze_until`` (YYYY-MM-DD).
- ``dismissed``: no required params; optional ``reason`` (str).
- ``done``: no required params; optional ``reason`` (str).
- ``rescheduled``: ``reschedule_to`` (YYYY-MM-DD).

Shared across all event_types: ``project_id`` (int > 0). See data-model
Entity 1 for the on-disk record shape, and ``contracts/api.md`` for the
public surface.
"""
from __future__ import annotations

import datetime
import re


# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

#: Map of escalation event_type (``state`` field) to the frozenset of
#: required structured parameter fields beyond the Phase 2 shared schema and
#: the shared ``project_id`` field. Empty frozenset means "no extra required
#: params" (optional ``reason`` may still be supplied for ``dismissed`` and
#: ``done``). Locked in lockstep with ``DOMAIN_STATES["escalation"]``.
EVENT_TYPE_PARAMETERS: dict[str, frozenset[str]] = {
    "level_sent":   frozenset({"level"}),
    "snoozed":      frozenset({"snooze_days", "snooze_until"}),
    "dismissed":    frozenset(),  # no required params; optional ``reason``
    "done":         frozenset(),  # no required params; optional ``reason``
    "rescheduled":  frozenset({"reschedule_to"}),
}


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class EscalationSchemaError(Exception):
    """Raised when an escalation record fails per-event_type validation."""


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

#: Matches Phase 2 ``state_log_schema._DATE_RE`` so JSONL ``date`` and the
#: per-event_type date params share one canonical pattern.
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _check_date_param(record: dict, field: str) -> None:
    """Validate that ``record[field]`` is a YYYY-MM-DD ISO-8601 calendar date.

    Raises ``EscalationSchemaError`` short-circuit on the first failure with
    a field-named, value-quoted message.
    """
    value = record[field]
    if not isinstance(value, str) or not _DATE_RE.match(value):
        raise EscalationSchemaError(
            f"{field} '{value!r}' must match YYYY-MM-DD"
        )
    try:
        datetime.date.fromisoformat(value)
    except ValueError as exc:
        raise EscalationSchemaError(
            f"{field} '{value}' is not a valid ISO-8601 date: {exc}"
        ) from None


# ---------------------------------------------------------------------------
# Public validator
# ---------------------------------------------------------------------------


def validate_event_params(record: dict) -> None:
    """Validate the per-event_type structured parameters on an escalation record.

    This is the structured-parameter validator that complements the Phase 2
    ``state_log.validate_record`` (which handles the seven shared required
    fields + optional ``note``). Call this AFTER the Phase 2 validator has
    already accepted the record, OR call it standalone to short-circuit on
    parameter-shape errors before the shared validator runs.

    Validation steps (short-circuit on first failure):

    a. ``record["state"]`` must be present and a known event_type
       (``in EVENT_TYPE_PARAMETERS``).
    b. Every field in ``EVENT_TYPE_PARAMETERS[state]`` must be present in
       ``record``.
    c. Per-parameter type/value checks:
       - ``level``: int in {1, 2} (no ``bool`` accepted).
       - ``snooze_days``: int > 0 (no ``bool`` accepted).
       - ``snooze_until``: str matching YYYY-MM-DD and parsing via
         ``datetime.date.fromisoformat``.
       - ``reschedule_to``: same shape rules as ``snooze_until``.
       - ``reason`` (optional on ``dismissed`` / ``done``): str when present.
    d. ``project_id`` (shared across all event_types per data-model Entity 1):
       required, int > 0 (no ``bool`` accepted).

    Raises:
        EscalationSchemaError: On the first violation. Message names the
            offending field and quotes the rejected value.

    Returns:
        None on success.
    """
    # (a) state is present and known
    state = record.get("state")
    if state is None:
        raise EscalationSchemaError(
            "required field 'state' missing from record"
        )
    if state not in EVENT_TYPE_PARAMETERS:
        known = ", ".join(sorted(EVENT_TYPE_PARAMETERS.keys()))
        raise EscalationSchemaError(
            f"state '{state}' not in escalation event_types {{{known}}}"
        )

    # (b) all required structured params for this event_type are present
    for field in sorted(EVENT_TYPE_PARAMETERS[state]):
        if field not in record:
            raise EscalationSchemaError(
                f"required field '{field}' missing for state '{state}'"
            )

    # (c) per-parameter type/value checks (only for fields present)
    if "level" in record:
        level = record["level"]
        if isinstance(level, bool) or not isinstance(level, int):
            raise EscalationSchemaError(
                f"level '{level!r}' must be int (got {type(level).__name__})"
            )
        if level not in (1, 2):
            raise EscalationSchemaError(
                f"level '{level}' must be 1 or 2"
            )

    if "snooze_days" in record:
        snooze_days = record["snooze_days"]
        if isinstance(snooze_days, bool) or not isinstance(snooze_days, int):
            raise EscalationSchemaError(
                f"snooze_days '{snooze_days!r}' must be int "
                f"(got {type(snooze_days).__name__})"
            )
        if snooze_days <= 0:
            raise EscalationSchemaError(
                f"snooze_days '{snooze_days}' must be a positive integer"
            )

    if "snooze_until" in record:
        _check_date_param(record, "snooze_until")

    if "reschedule_to" in record:
        _check_date_param(record, "reschedule_to")

    if "reason" in record:
        reason = record["reason"]
        if not isinstance(reason, str):
            raise EscalationSchemaError(
                f"reason '{reason!r}' must be str "
                f"(got {type(reason).__name__})"
            )

    # (d) project_id is required across all event_types
    if "project_id" not in record:
        raise EscalationSchemaError(
            "required field 'project_id' missing from record"
        )
    project_id = record["project_id"]
    if isinstance(project_id, bool) or not isinstance(project_id, int):
        raise EscalationSchemaError(
            f"project_id '{project_id!r}' must be int "
            f"(got {type(project_id).__name__})"
        )
    if project_id <= 0:
        raise EscalationSchemaError(
            f"project_id '{project_id}' must be a positive integer"
        )
