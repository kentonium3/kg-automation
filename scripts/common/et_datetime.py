"""Canonical Eastern-time date/time utilities (#761).

Single source of truth for the ET/UTC boundary. Vikunja and office2 both
default to UTC; surfaces that cross that boundary previously re-derived the
same conversions inline, which is why the *same* ET-vs-UTC bug shape recurred
on five independent code paths (#733/#736/#739/#757/#759). Consolidating the
conversions here breaks that whack-a-mole cycle.

Adopted so far (#761): escalation write (``record_completion``) + read
(``enumerate_candidates``), intake ``apply_reply`` + ``scan_inbox``, and the
alert-bus renderer. Not yet folded in (each still carries an inline copy, to be
migrated incrementally): the ``scripts/habits/*`` date logic,
``scripts/security/credential_health_check/vikunja_writer.py`` (its own
end-of-day ET write), ``scripts/sync/guards.py``, and the calendar validator
``scripts/calendar_routing/validate_calendar_event.py`` — the last is invoked by
script path and deliberately avoids a ``scripts.common`` import (the #668 ``-m``
trap), so it keeps a local zone constant.

Hard rule: never use a bare no-argument ``dt.astimezone()``. On office2 the
host TZ is ``Etc/UTC``, so a bare call silently yields UTC, not Eastern (the
#759 shape). Always convert with an explicit zone — this module does, and the
pytest AST guard ``tests/common/test_no_bare_astimezone.py`` enforces the rule
repo-wide.
"""

from __future__ import annotations

from datetime import date, datetime, timezone, tzinfo
from zoneinfo import ZoneInfo

#: Kent's operating timezone. DST-aware (``-04:00`` EDT / ``-05:00`` EST).
ET_ZONE = ZoneInfo("America/New_York")

__all__ = [
    "ET_ZONE",
    "to_et",
    "today_et",
    "parse_vikunja_instant",
    "et_calendar_date",
    "et_end_of_day",
]


def to_et(value: datetime, *, assume: tzinfo = timezone.utc) -> datetime:
    """Return *value* as an aware datetime in :data:`ET_ZONE`.

    A naive *value* is interpreted as being in *assume* (default UTC — the
    alert-bus and Vikunja convention). Callers whose naive values are
    wall-clock Eastern (calendar routing) pass ``assume=ET_ZONE``.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=assume)
    return value.astimezone(ET_ZONE)


def today_et(*, now: datetime | None = None) -> date:
    """Return today's calendar date in :data:`ET_ZONE`.

    *now* (aware, or naive-assumed-UTC) is injectable for tests; it defaults to
    the current instant. Using the Eastern calendar date — not the UTC one —
    is what keeps "today"/"tomorrow" correct for Kent between ~19:00–23:59 ET,
    when the UTC date has already rolled over (the #733 class).
    """
    if now is None:
        now = datetime.now(timezone.utc)
    return to_et(now).date()


def parse_vikunja_instant(value: object) -> datetime | None:
    """Parse a Vikunja ``due_date`` string into an aware **UTC** instant.

    Vikunja serializes every ``due_date`` to UTC ``Z`` (#733/#736), but a value
    written as an ET offset (``…-04:00``) denotes the same instant. This returns
    that instant in UTC so callers can compare instants (#757) or take an
    Eastern calendar date (:func:`et_calendar_date`).

    Returns ``None`` — the "no usable due date" signal — for: a non-str /
    empty / whitespace-only value; any **year <= 1** datetime (this covers the
    ``0001-01-01`` "unset" sentinel in every offset spelling, and defensively
    excludes any other year-1 value too — checked *before* conversion, since a
    year-1 ``.astimezone()`` can ``OverflowError``); a **naive** datetime
    (Vikunja values are always aware, so a naive one is malformed and is
    excluded rather than assumed UTC — matching the escalation read-side's
    deliberate "don't guess a timezone" safety choice); and any value that fails
    ISO-8601 parsing.

    Note the ``year <= 1`` and naive exclusions are slightly *broader* than the
    prior inline ``apply_reply._due_instant`` (which only pre-checked the literal
    ``0001-01-01`` prefix and assumed naive→UTC). That is safe for the existing
    callers — the readback-compare only ever sees modern aware strings on both
    sides — but a future reuse on a surface that can produce naive or non-Jan-1
    year-1 strings will exclude values the old inline copy would have accepted.
    """
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped:
        return None
    normalized = (
        stripped.replace("Z", "+00:00") if stripped.endswith("Z") else stripped
    )
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    if parsed.year <= 1:
        return None
    try:
        return parsed.astimezone(timezone.utc)
    except (OverflowError, ValueError, OSError):
        return None


def et_calendar_date(value: object, *, zone: tzinfo = ET_ZONE) -> date | None:
    """Return the Eastern calendar date of a Vikunja ``due_date`` string.

    Parses via :func:`parse_vikunja_instant`, converts to *zone* (default
    :data:`ET_ZONE`; overridable for tests), and takes the calendar date — so a
    ``23:00 UTC`` due date reads as the *prior* Eastern day, which is what makes
    day-boundary classification consistent. Returns ``None`` when the value is
    excluded (see :func:`parse_vikunja_instant`).
    """
    instant = parse_vikunja_instant(value)
    if instant is None:
        return None
    try:
        return instant.astimezone(zone).date()
    except (OverflowError, ValueError, OSError):
        return None


def et_end_of_day(target: date | str) -> str:
    """Render a date as an end-of-day Eastern instant string.

    Returns ``YYYY-MM-DDT23:59:59±HH:MM`` anchored to ``23:59:59`` in
    :data:`ET_ZONE` with the DST-correct offset (``-04:00`` EDT / ``-05:00``
    EST) — never UTC ``Z``. Writing UTC midnight (``…T00:00:00Z``) lands in the
    *prior* Eastern evening, so a task due "June 15" reads back as June 14 and
    is mis-classified as overdue a day early (#733). End-of-day ET is the single
    correct ``due_date`` write for every Vikunja surface.

    *target* is a :class:`datetime.date` or a ``YYYY-MM-DD`` string.

    Raises:
        ValueError: If *target* is a non-``YYYY-MM-DD`` string, or a
            pre-standardization date whose Eastern offset carries sub-minute
            seconds (e.g. a year-1 Local-Mean-Time ``-04:56:02``) — never a real
            due date and a violation of the ``±HH:MM`` contract.
    """
    if isinstance(target, str):
        target = date.fromisoformat(target)
    anchor = datetime(
        target.year, target.month, target.day, 23, 59, 59, tzinfo=ET_ZONE
    )
    raw_offset = anchor.strftime("%z")
    if len(raw_offset) != 5:
        # Modern Eastern Time is always a whole-hour offset (``-0400`` /
        # ``-0500`` → 5 chars). A longer value carries a pre-1883 Local Mean
        # Time offset with seconds (e.g. ``-045602``), which is never a real
        # due date and would break the ``YYYY-MM-DDT23:59:59±HH:MM`` contract.
        raise ValueError(
            f"date {target.isoformat()!r} resolves to a non-standard UTC "
            f"offset {raw_offset!r}; expected a modern Eastern date"
        )
    offset = f"{raw_offset[:3]}:{raw_offset[3:]}"
    return f"{target.isoformat()}T23:59:59{offset}"
