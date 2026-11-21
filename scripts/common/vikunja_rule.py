"""Pure helpers for Vikunja RRULE recurrence rules (mission felix-rrule-adaptation, #1111).

Vikunja (vikunja-harness ``d7e202228``) models recurrence as a structured
``repeat`` object plus ``repeats_rrule`` RFC 5545 text. Raw ``repeat`` dicts
differ between reads in list order, casing, the response-only ``read_only``
flag and zero-valued parts, so callers must never compare them directly.
This module is the single definition of "the same rule", the text <-> parts
conversion, and the completion-outcome classifier (FR-014).

It is **pure**: stdlib only, no network, no import of ``vikunja_client``.
Exceptions raised by an injected ``preview`` callable are caught generically.

Server facts this module relies on:

- ``repeat`` responses are lowercase (``daily``, ``mo``, ``2tu``);
  ``repeats_rrule`` is RFC 5545 uppercase.
- ``read_only`` is response-only.
- ``count`` is the number of occurrences *remaining*; each completion
  decrements it.
- COUNT exhaustion clears the rule and leaves the task Done; UNTIL having
  passed leaves it Done with the rule kept.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta, tzinfo
from typing import Any, Literal

from scripts.common.et_datetime import ET_ZONE, parse_vikunja_instant

__all__ = [
    "completion_outcome",
    "exhaustion_expected",
    "has_rule",
    "moved_absolute_reminder",
    "normalise",
    "parts_to_rrule_text",
    "recurrence_drift",
    "rrule_text_to_parts",
    "rule_equal_except_count",
    "same_rule",
]

Exhaustion = Literal["yes", "no", "unknown"]
Outcome = Literal["advanced", "series_ended", "unexpected"]

#: RFC 5545 key -> Vikunja ``repeat`` part, in the deterministic text order
#: used by :func:`parts_to_rrule_text` (FREQ, INTERVAL, BY* in RFC order,
#: COUNT, UNTIL, WKST).
_TEXT_TO_PART: dict[str, str] = {
    "FREQ": "freq",
    "INTERVAL": "interval",
    "BYSECOND": "by_second",
    "BYMINUTE": "by_minute",
    "BYHOUR": "by_hour",
    "BYDAY": "by_day",
    "BYMONTHDAY": "by_month_day",
    "BYYEARDAY": "by_year_day",
    "BYWEEKNO": "by_week_no",
    "BYMONTH": "by_month",
    "BYSETPOS": "by_set_pos",
    "COUNT": "count",
    "UNTIL": "until",
    "WKST": "wkst",
}
_PART_TO_TEXT: dict[str, str] = {v: k for k, v in _TEXT_TO_PART.items()}

_STRING_PARTS = frozenset({"freq", "wkst"})
_STRING_LIST_PARTS = frozenset({"by_day"})

#: One BYDAY entry: optional sign, optional ordinal, two-letter weekday.
_WEEKDAY_ENTRY = re.compile(r"^([+-]?)(\d{1,2})?([a-z]{2})$")


def _canonical_weekday(value: Any) -> str:
    """Canonical BYDAY entry, as the server's structured ``repeat`` writes it.

    The server renders ``by_day`` with ``fmt.Sprintf("%d%s", wd.N(), day)``
    (vikunja-harness d7e202228 pkg/models/task_repeat.go:556-562): lowercase,
    no ``+`` sign, no leading zero, ``-`` kept, and a bare weekday for N=0.
    ``repeats_rrule`` text keeps whatever spelling was stored (``+1MO``), so
    both spellings must normalise to ``1mo``. An entry that is not a weekday
    is kept lowercased verbatim, so it never compares equal to a real one.
    """
    text = str(value).strip().lower()
    match = _WEEKDAY_ENTRY.match(text)
    if match is None:
        return text
    sign, ordinal, day = match.groups()
    n = int(ordinal) if ordinal else 0
    if n == 0:
        return day
    return f"{'-' if sign == '-' else ''}{n}{day}"
_INT_LIST_PARTS = frozenset(
    {
        "by_second",
        "by_minute",
        "by_hour",
        "by_month_day",
        "by_year_day",
        "by_week_no",
        "by_month",
        "by_set_pos",
    }
)
_EMPTY_VALUES: tuple[Any, ...] = (0, "", None)

_DEFAULT_WKST = "mo"

_EXPLICIT_END_REASONS = frozenset({"until_passed", "count_exhausted"})


def _normalise_until(value: Any) -> str | None:
    """Return *value* as an RFC3339 UTC ``Z`` string, or None if unusable."""
    instant = parse_vikunja_instant(value)
    if instant is None:
        return None
    return instant.strftime("%Y-%m-%dT%H:%M:%SZ")


def normalise(repeat: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Return the normal form of a Vikunja ``repeat`` object, or None for no rule.

    ``None``, ``{}`` and a mapping without ``freq`` all mean "no rule". The
    normal form drops ``read_only`` and the default ``wkst`` (``mo``),
    lowercases string parts, canonicalises BYDAY ordinals
    (``+1MO`` -> ``1mo``, :func:`_canonical_weekday`), sorts every
    ``by_*`` list, drops zero/empty values, defaults ``interval`` to 1 (the
    server treats 0 as 1), and renders ``until`` as UTC ``Z`` RFC3339.

    Callers: WP03, WP04, WP05, WP06, WP07, WP10 (via :func:`same_rule` /
    :func:`has_rule`), and the round-trip tests here.
    """
    if not repeat:
        return None
    freq = repeat.get("freq")
    if not freq:
        return None
    out: dict[str, Any] = {}
    for key, value in repeat.items():
        if key == "read_only" or key == "interval":
            continue
        if isinstance(value, list):
            if not value:
                continue
            if key in _STRING_LIST_PARTS:
                out[key] = sorted(_canonical_weekday(v) for v in value)
            else:
                out[key] = sorted(value)
            continue
        if value in _EMPTY_VALUES:
            continue
        if key in _STRING_PARTS:
            lowered = str(value).lower()
            if key == "wkst" and lowered == _DEFAULT_WKST:
                # Monday is the default week start: the server omits it in
                # responses and compares "" equal to "mo" (vikunja-harness
                # d7e202228 pkg/models/task_repeat.go:60, 444-446, 524-526).
                continue
            out[key] = lowered
        elif key == "until":
            # An unparseable UNTIL is kept verbatim rather than dropped, so
            # it can never make two different rules compare equal.
            until = _normalise_until(value)
            out[key] = until if until is not None else str(value)
        else:
            out[key] = value
    interval = repeat.get("interval")
    out["interval"] = interval if isinstance(interval, int) and interval > 0 else 1
    return out


def same_rule(a: Mapping[str, Any] | None, b: Mapping[str, Any] | None) -> bool:
    """True when two ``repeat`` objects denote the same rule (normal forms equal).

    Callers: WP03, WP04, WP05, WP06, WP07, WP10.
    """
    return normalise(a) == normalise(b)


def has_rule(task: Mapping[str, Any]) -> bool:
    """True when *task* carries a recurrence rule.

    Callers: WP03, WP04, WP05, WP06, WP07, WP10; also
    :func:`completion_outcome`.
    """
    return normalise(task.get("repeat")) is not None


def rule_equal_except_count(
    before: Mapping[str, Any] | None, after: Mapping[str, Any] | None
) -> bool:
    """True when *after* is *before* with COUNT decremented by exactly one.

    Both are ``repeat`` objects. The rules must be equal once ``count`` is
    removed, and ``after.count == before.count - 1``. This is the
    "advanced on a COUNT rule" shape.

    Callers: WP03, WP04 (completion "advanced"); :func:`completion_outcome`.
    """
    nb = normalise(before)
    na = normalise(after)
    if nb is None or na is None:
        return False
    count_before = nb.pop("count", None)
    count_after = na.pop("count", None)
    if not isinstance(count_before, int) or not isinstance(count_after, int):
        return False
    return nb == na and count_after == count_before - 1


def rrule_text_to_parts(text: str) -> dict[str, Any]:
    """Parse RFC 5545 RRULE text into Vikunja ``repeat`` parts.

    Tolerates an optional ``RRULE:`` prefix. Numeric BY* lists become ints,
    strings are lowercased, ``UNTIL=20261231T235959Z`` becomes
    ``"2026-12-31T23:59:59Z"``. Raises ``ValueError`` on an unknown key, a
    malformed component, a missing FREQ, or an UNTIL that is not UTC
    ``YYYYMMDDTHHMMSSZ`` (date-only and floating forms are refused). RRULE semantics are not validated
    here; the server does that (preview 2002).

    Callers: WP07 (schedule YAML), WP08 (``create_task --rrule``), WP10
    (inventory snapshot rule text).
    """
    body = text.strip()
    if body.upper().startswith("RRULE:"):
        body = body[len("RRULE:"):]
    parts: dict[str, Any] = {}
    for component in body.split(";"):
        component = component.strip()
        if not component:
            continue
        if "=" not in component:
            raise ValueError(f"malformed RRULE component: {component!r}")
        raw_key, raw_value = component.split("=", 1)
        key = raw_key.strip().upper()
        value = raw_value.strip()
        part = _TEXT_TO_PART.get(key)
        if part is None:
            raise ValueError(f"unknown RRULE key: {raw_key!r}")
        try:
            if part in ("interval", "count"):
                parts[part] = int(value)
            elif part in _INT_LIST_PARTS:
                parts[part] = [int(v) for v in value.split(",") if v.strip()]
            elif part in _STRING_LIST_PARTS:
                parts[part] = [v.strip().lower() for v in value.split(",") if v.strip()]
            elif part == "until":
                parts[part] = _until_text_to_rfc3339(value)
            else:
                parts[part] = value.lower()
        except ValueError as exc:
            raise ValueError(f"bad RRULE value for {key}: {value!r}") from exc
    if not parts.get("freq"):
        raise ValueError(f"RRULE has no FREQ: {text!r}")
    return parts


def _until_text_to_rfc3339(value: str) -> str:
    """Convert an RFC 5545 UTC UNTIL (``YYYYMMDDTHHMMSSZ``) to RFC3339 UTC.

    Date-only (``YYYYMMDD``) and floating (``YYYYMMDDTHHMMSS``) forms are
    refused with ``ValueError``: they name no instant, and Felix must not
    invent a zone for them.
    """
    raw = value.upper()
    if len(raw) != len("20261231T235959Z") or not raw.endswith("Z"):
        raise ValueError(f"UNTIL must be YYYYMMDDTHHMMSSZ (UTC), got {value!r}")
    parsed = datetime.strptime(raw, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    return parsed.strftime("%Y-%m-%dT%H:%M:%SZ")


def _rfc3339_to_until_text(value: Any) -> str:
    instant = parse_vikunja_instant(value)
    if instant is None:
        raise ValueError(f"unusable UNTIL value: {value!r}")
    return instant.strftime("%Y%m%dT%H%M%SZ")


def parts_to_rrule_text(parts: Mapping[str, Any]) -> str:
    """Render Vikunja ``repeat`` parts as uppercase RFC 5545 RRULE text.

    Key order is deterministic (FREQ, INTERVAL, BY* in RFC order, COUNT,
    UNTIL, WKST). The input is normalised first, so zero/empty parts and
    ``read_only`` are omitted and INTERVAL is always present. Raises
    ``ValueError`` when *parts* is not a rule.

    Callers: WP07, WP08, WP10; ``tests/common/vikunja_v2_factory.py``.
    """
    norm = normalise(parts)
    if norm is None:
        raise ValueError("parts do not describe a rule (no freq)")
    unknown = set(norm) - set(_PART_TO_TEXT)
    if unknown:
        raise ValueError(f"unknown rule parts: {sorted(unknown)}")
    rendered: list[str] = []
    for key, part in _TEXT_TO_PART.items():
        if part not in norm:
            continue
        value = norm[part]
        if isinstance(value, list):
            text = ",".join(str(v) for v in value)
        elif part == "until":
            text = _rfc3339_to_until_text(value)
        else:
            text = str(value)
        rendered.append(f"{key}={text.upper()}")
    return ";".join(rendered)


def exhaustion_expected(
    before: Mapping[str, Any],
    *,
    preview: Callable[..., Mapping[str, Any]] | None,
) -> Exhaustion:
    """Decide, **before** a completion write, whether it should end the series.

    - No rule -> ``"no"`` (not completing a series).
    - ``count == 1`` -> ``"yes"`` (checked locally).
    - ``until`` set, ``repeats_from_current_date is False`` and *preview*
      given -> ask the server via ``preview(repeat=..., due_date=...,
      repeats_from_current_date=False, count=1)``: an explicit
      ``until_passed`` / ``count_exhausted`` reason -> ``"yes"``; a non-empty
      occurrence list with no reason -> ``"no"``; anything else -> ``"unknown"``.
    - ``until`` set but the from-current flag is not ``False``, no *preview*,
      or *preview* raising -> ``"unknown"``.
    - No COUNT and no UNTIL -> ``"no"``.

    *preview* is injected (the client's ``preview_occurrences``); any
    ``Exception`` it raises yields ``"unknown"``.

    Callers: WP03 (habit completion), WP04 (escalation done).
    """
    rule = normalise(before.get("repeat"))
    if rule is None:
        return "no"
    if rule.get("count") == 1:
        return "yes"
    if "until" not in rule:
        return "no"
    if before.get("repeats_from_current_date") is not False or preview is None:
        return "unknown"
    try:
        result = preview(
            repeat=rule,
            due_date=before.get("due_date"),
            repeats_from_current_date=False,
            count=1,
        )
    except Exception:  # noqa: BLE001 - any client failure means "cannot tell"
        return "unknown"
    if not isinstance(result, Mapping):
        return "unknown"
    reason = result.get("reason")
    occurrences = result.get("occurrences")
    if reason in _EXPLICIT_END_REASONS:
        return "yes"
    if not reason and isinstance(occurrences, list) and occurrences:
        return "no"
    return "unknown"


def completion_outcome(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    *,
    exhaustion: str,
) -> Outcome:
    """Classify a completion write on a repeating task (FR-014, data-model.md).

    - ``advanced``: *before* had a rule; *after* is ``done=False`` with a later
      ``due_date``; and the rule is unchanged or differs only by COUNT one
      lower.
    - ``series_ended``: *after* is ``done=True`` **and** *exhaustion* is
      ``"yes"`` (computed by :func:`exhaustion_expected` before the write).
      When the end came from COUNT (``count == 1`` before), the rule must also
      be absent after. For UNTIL the server keeps the rule, so the rule after
      must equal the rule before (:func:`same_rule`).
    - ``unexpected``: everything else, including ``done=True`` with
      exhaustion ``"no"`` or ``"unknown"``. A bare ``done=True`` is never a
      normal end.

    Callers: WP03 (habit completion), WP04 (escalation done).
    """
    if has_rule(before) and after.get("done") is False:
        due_before = parse_vikunja_instant(before.get("due_date"))
        due_after = parse_vikunja_instant(after.get("due_date"))
        if (
            due_before is not None
            and due_after is not None
            and due_after > due_before
            and (
                same_rule(before.get("repeat"), after.get("repeat"))
                or rule_equal_except_count(before.get("repeat"), after.get("repeat"))
            )
        ):
            return "advanced"
        return "unexpected"
    if after.get("done") is True and exhaustion == "yes":
        rule_before = normalise(before.get("repeat"))
        if rule_before is None:
            return "unexpected"
        if rule_before.get("count") == 1:
            # COUNT exhaustion: the server clears the rule.
            return "unexpected" if has_rule(after) else "series_ended"
        # UNTIL passed: the server keeps the rule unchanged. A stripped or
        # replaced rule is damage, not a normal end.
        if same_rule(before.get("repeat"), after.get("repeat")):
            return "series_ended"
        return "unexpected"
    return "unexpected"


# ---------------------------------------------------------------------------
# Rule-state drift across a write (data-model.md Invariant 2, FR-020)
# ---------------------------------------------------------------------------

#: Relative-reminder anchors whose trigger the server derives from a task date
#: (vikunja-harness d7e202228 pkg/models/tasks.go:2575-2590,
#: ``updateRelativeReminderDates``). The anchor name is also the task field.
_RELATIVE_ANCHORS = frozenset({"due_date", "start_date", "end_date"})

#: Rule frequencies the server steps by elapsed time (``familyElapsed``,
#: vikunja-harness d7e202228 pkg/models/task_next_occurrence_engine.go:58-68).
_ELAPSED_FREQS = frozenset({"secondly", "minutely", "hourly"})

#: Sort key for an absolute reminder: unusable values (``(0, repr)``) before
#: instants (``(1, iso)``). The read path sorts reminders by instant
#: (pkg/models/tasks.go:2670), so position is not identity; a sorted list is.
_AbsKey = tuple[int, str]


def _floating(instant: datetime, zone: tzinfo) -> datetime:
    """Wall clock of *instant* in *zone*, naive (the engine's ``float``)."""
    return instant.astimezone(zone).replace(tzinfo=None)


def _localise(wall: datetime, zone: tzinfo) -> datetime:
    """The instant whose wall clock in *zone* is *wall* (the engine's ``localise``).

    ``fold=0`` gives the server's choices (task_next_occurrence.go:240-268):
    an overlap takes the earlier instant, and a gap takes the pre-transition
    offset, which reads as the wall clock moved forward by the gap.
    """
    return wall.replace(tzinfo=zone, fold=0).astimezone(UTC)


def moved_absolute_reminder(
    reminder: datetime,
    old_due: datetime,
    new_due: datetime,
    rule: Mapping[str, Any],
    *,
    zone: tzinfo = ET_ZONE,
) -> datetime:
    """Predict where the server moves an absolute reminder when a completion advances.

    The single predictor of the server's companion move. It mirrors
    vikunja-harness d7e202228:

    - ``setTaskDatesRRule`` hands only absolute reminders to the engine
      (pkg/models/tasks.go:2318-2327) and ``applyNextOccurrence`` writes the
      moved instants back (tasks.go:2402-2413);
    - ``withDueDate`` moves each as a companion of the due date, in both
      repeat modes, and moves nothing when the next occurrence is the stored
      due date (task_next_occurrence_engine.go:429-456);
    - ``moveCompanion`` (engine.go:576-592): SECONDLY/MINUTELY/HOURLY shift
      by the elapsed due-date delta; other rules without BYHOUR/BYMINUTE/
      BYSECOND keep their wall-clock time and move by the calendar days the
      due date moved; rules naming a time shift the wall clock by the wall
      due delta, clamped to the new due date when that crosses it.

    *rule* is a ``repeat`` object (normalised here). *zone* is the
    completion's zone; Felix completes as Kent, so America/New_York.
    ``tests/common/fixtures/reminder_move_parity.json`` holds outputs of the
    server engine itself for DST gap/overlap, clamping and reordering cases.
    """
    if old_due == new_due:
        return reminder
    norm = normalise(rule) or {}
    if norm.get("freq") in _ELAPSED_FREQS:
        return reminder + (new_due - old_due)
    wall = _floating(reminder, zone)
    old_wall, new_wall = _floating(old_due, zone), _floating(new_due, zone)
    if not (norm.get("by_hour") or norm.get("by_minute") or norm.get("by_second")):
        days = (new_wall.date() - old_wall.date()).days
        return _localise(wall + timedelta(days=days), zone)
    moved = _localise(wall + (new_wall - old_wall), zone)
    if (wall < old_wall and moved > new_due) or (wall > old_wall and moved < new_due):
        moved = new_due
    return moved


def _reminder_signature(reminders: Any) -> list[tuple[Any, ...]]:
    """Reminders as an order-free list of kinds.

    A relative reminder is identified by ``(relative_to, relative_period)``:
    the server recomputes its instant on every save, in the saver's zone
    (tasks.go:1813 ``updateReminders`` -> ``updateRelativeReminderDates``),
    so the instant legitimately moves. An absolute one is ``("absolute",)``;
    its instant is compared by :func:`_absolute_reminders_damaged`.
    """
    signature: list[tuple[Any, ...]] = []
    for reminder in reminders or []:
        if not isinstance(reminder, Mapping):
            signature.append(("malformed", repr(reminder)))
            continue
        relative_to = str(reminder.get("relative_to") or "")
        if relative_to:
            period = reminder.get("relative_period") or 0
            signature.append(("relative", relative_to, repr(period)))
        else:
            signature.append(("absolute",))
    return sorted(signature)


def _absolute_values(reminders: Any) -> list[datetime | str]:
    """Absolute reminder triggers: the instant, or the raw value when unusable."""
    values: list[datetime | str] = []
    for reminder in reminders or []:
        if not isinstance(reminder, Mapping) or reminder.get("relative_to"):
            continue
        raw = reminder.get("reminder")
        instant = parse_vikunja_instant(raw)
        values.append(instant if instant is not None else repr(raw))
    return values


def _abs_key(value: datetime | str) -> _AbsKey:
    if isinstance(value, datetime):
        return (1, value.astimezone(UTC).isoformat())
    return (0, value)


def _absolute_reminders_damaged(
    before: Mapping[str, Any], after: Mapping[str, Any], *, advanced: bool
) -> bool:
    """True when absolute triggers changed other than as the server moves them.

    Without an advance the server moves no date (tasks.go:2342-2352), so the
    instants must be identical. On an advance each must land exactly where
    :func:`moved_absolute_reminder` puts it. An unset or unusable trigger never
    moves (``moveCompanion`` keeps an unset date unset) and never matches a set
    one.
    """
    old = _absolute_values(before.get("reminders"))
    new = sorted(_abs_key(v) for v in _absolute_values(after.get("reminders")))
    if len(old) != len(new):
        return True
    expected: list[datetime | str] = old
    if advanced:
        old_due = parse_vikunja_instant(before.get("due_date"))
        new_due = parse_vikunja_instant(after.get("due_date"))
        rule = normalise(before.get("repeat"))
        if old_due is not None and new_due is not None and rule is not None:
            expected = [
                moved_absolute_reminder(v, old_due, new_due, rule)
                if isinstance(v, datetime)
                else v
                for v in old
            ]
        else:
            # "advanced" requires both due dates and a rule
            # (completion_outcome); defensively keep set-ness at least.
            return [isinstance(v, datetime) for v in sorted(old, key=_abs_key)] != [
                k[0] == 1 for k in new
            ]
    return sorted(_abs_key(v) for v in expected) != new


def _relative_trigger_missing(task: Mapping[str, Any]) -> bool:
    """True when a relative reminder with a set base date has no trigger instant.

    The server derives the trigger from anchor + period on every save
    (vikunja-harness d7e202228 pkg/models/tasks.go:2575-2590): it zeroes it,
    then sets it whenever the base date is set. A read showing the zero
    sentinel (or nothing usable) beside a set base date is not a state the
    server produces, so it reads as damage.
    """
    for reminder in task.get("reminders") or []:
        if not isinstance(reminder, Mapping):
            continue
        anchor = str(reminder.get("relative_to") or "")
        if anchor not in _RELATIVE_ANCHORS:
            continue
        if parse_vikunja_instant(task.get(anchor)) is None:
            continue
        if parse_vikunja_instant(reminder.get("reminder")) is None:
            return True
    return False


def recurrence_drift(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    *,
    compare_rule: bool = True,
    advanced: bool = False,
) -> list[str]:
    """Rule-bearing state a write lost or changed (data-model.md Invariant 2).

    The one definition of "the write kept the rule, the flag and the
    reminders". Returns the drifted field names, in this order, or ``[]``:

    - ``"repeat"``: the rule differs (:func:`same_rule`). Only when
      *compare_rule*; a completion's rule change is judged by
      :func:`completion_outcome` instead, so completion callers pass False.
    - ``"repeats_from_current_date"``: the flag differs (truthiness).
    - ``"reminders"``: the reminder set differs. Relative reminders compare by
      ``(relative_to, relative_period)``; absolute ones by instant, which must
      be unchanged unless *advanced* (a completion that moved the task to its
      next occurrence), when each must sit where
      :func:`moved_absolute_reminder` predicts. Also reported when *after*
      holds a relative reminder whose base date is set but whose trigger is
      the zero sentinel (:func:`_relative_trigger_missing`).

    Callers: ``habits.set_due_dates`` (and ``habits.sweeper`` through it),
    ``habits.record_completion``, ``vikunja.migrate_tasks.rule_state_drift``
    (and its callers ``intake.apply_reply``,
    ``vikunja.migrate_date_only_due_dates``), ``escalation.record_completion``.
    """
    drift: list[str] = []
    if compare_rule and not same_rule(before.get("repeat"), after.get("repeat")):
        drift.append("repeat")
    if bool(before.get("repeats_from_current_date")) != bool(
        after.get("repeats_from_current_date")
    ):
        drift.append("repeats_from_current_date")
    if (
        _reminder_signature(before.get("reminders"))
        != _reminder_signature(after.get("reminders"))
        or _absolute_reminders_damaged(before, after, advanced=advanced)
        or _relative_trigger_missing(after)
    ):
        drift.append("reminders")
    return drift
