#!/usr/bin/env python3
"""Deterministic validator for ExtractedCalendarBlock → CalendarEventPayload.

Reads an ``ExtractedCalendarBlock`` JSON object from stdin, validates that
every field needed to create a Google Calendar event is present and
parseable, and emits one of:

- a ``CalendarEventPayload`` ready for delegation to Felix main + ``gog
  calendar create`` (``complete: true``); or
- a structured ``missing_fields`` report (``complete: false``) so capture
  can persist a ``PendingClarificationRecord`` and prompt Kent.

Implements Felix Constitution Directive 6 (scripts vs LLM split): the
capture LLM extracts natural-language fields; this helper performs
deterministic validation, datetime parsing, RRULE conversion, and payload
assembly. Pure: no filesystem reads/writes beyond stdin/stdout, no
network, no environment variables, no wall-clock reads (uses
caller-supplied ``tick_iso``).

Contract: ``kitty-specs/inbox-calendar-and-aspiration-routing-01KTHHXS/
contracts/validate_calendar_event.md`` is authoritative for input
schema, output schema, recurrence pattern table, and exit codes.

Exit codes:
    0 — normal return (``complete: true`` or ``complete: false``)
    2 — malformed input JSON
    3 — missing a required input field
    4 — internal error (should not happen)
"""
from __future__ import annotations

import json
import os
import re
import sys
import traceback
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

DEFAULT_TIMEZONE = "America/New_York"
DEFAULT_CALENDAR_ID = "primary"
DEFAULT_ACCOUNT = "kent@intentional.biz"

REQUIRED_INPUT_FIELDS = (
    "title",
    "start_natural",
    "source_inbox_path",
    "source_block_index",
    "tick_iso",
)

_WEEKDAY_TOKENS = {
    "monday": ("MO", 0),
    "tuesday": ("TU", 1),
    "wednesday": ("WE", 2),
    "thursday": ("TH", 3),
    "friday": ("FR", 4),
    "saturday": ("SA", 5),
    "sunday": ("SU", 6),
}

_ORDINAL_TOKENS = {
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "last": -1,
}

_MONTH_TOKENS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5,
    "june": 6, "july": 7, "august": 8, "september": 9, "october": 10,
    "november": 11, "december": 12,
}


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def _missing_required(block: dict) -> Optional[str]:
    """Return the name of the first required field that is missing or None."""
    for field in REQUIRED_INPUT_FIELDS:
        if field not in block:
            return field
        value = block[field]
        if field == "source_block_index":
            if not isinstance(value, int):
                return field
        else:
            if value is None:
                return field
            if isinstance(value, str) and not value.strip():
                return field
    return None


# ---------------------------------------------------------------------------
# Time-of-day parsing
# ---------------------------------------------------------------------------


_TIME_24H = re.compile(r"\b(\d{1,2}):(\d{2})\b(?!\s*(?:am|pm|AM|PM))")
_TIME_12H = re.compile(
    r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|AM|PM|a\.m\.|p\.m\.)",
    re.IGNORECASE,
)
_TIME_WORD_NOON = re.compile(r"\bnoon\b", re.IGNORECASE)
_TIME_WORD_MIDNIGHT = re.compile(r"\bmidnight\b", re.IGNORECASE)


def _parse_time_component(text: str) -> Optional[tuple[int, int]]:
    """Extract (hour, minute) from a free-text fragment.

    Recognized: "noon", "midnight", "2pm", "2:30 PM", "14:00".
    Returns None when no time token is present.
    """
    if _TIME_WORD_NOON.search(text):
        return 12, 0
    if _TIME_WORD_MIDNIGHT.search(text):
        return 0, 0

    m = _TIME_12H.search(text)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2)) if m.group(2) else 0
        meridiem = m.group(3).lower().replace(".", "")
        if meridiem == "pm" and hour != 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute
        return None

    m = _TIME_24H.search(text)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute
    return None


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------


_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_AMERICAN_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
_AMERICAN_DATE_SHORT = re.compile(r"\b(\d{1,2})/(\d{1,2})\b")
_MONTH_NAME_DATE = re.compile(
    r"\b(january|february|march|april|may|june|july|august|september|"
    r"october|november|december)\s+(\d{1,2})(?:,?\s+(\d{4}))?",
    re.IGNORECASE,
)

_RELATIVE_TODAY = re.compile(r"\btoday\b", re.IGNORECASE)
_RELATIVE_TOMORROW = re.compile(r"\btomorrow\b", re.IGNORECASE)
_RELATIVE_NEXT_WEEKDAY = re.compile(
    r"\bnext\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    re.IGNORECASE,
)
_RELATIVE_THIS_WEEKDAY = re.compile(
    r"\bthis\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    re.IGNORECASE,
)
_BARE_WEEKDAY = re.compile(
    r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    re.IGNORECASE,
)


def _resolve_next_weekday(anchor: datetime, weekday_idx: int) -> datetime:
    """Return the first date strictly AFTER the anchor with the given weekday."""
    delta = (weekday_idx - anchor.weekday()) % 7
    if delta == 0:
        delta = 7
    return anchor + timedelta(days=delta)


def _resolve_this_weekday(anchor: datetime, weekday_idx: int) -> datetime:
    """Return the upcoming weekday (today if today matches, else the next)."""
    delta = (weekday_idx - anchor.weekday()) % 7
    return anchor + timedelta(days=delta)


def _parse_date_component(
    text: str, anchor: datetime
) -> Optional[tuple[int, int, int]]:
    """Extract (year, month, day) from a free-text fragment.

    Tries (in order): ISO YYYY-MM-DD, MM/DD/YYYY, Month-name forms,
    "today", "tomorrow", "next <weekday>", "this <weekday>", bare
    weekday name. Anchor is the caller-supplied ``tick`` datetime.
    """
    m = _ISO_DATE.search(text)
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))

    m = _AMERICAN_DATE.search(text)
    if m:
        month = int(m.group(1))
        day = int(m.group(2))
        year = int(m.group(3))
        if 1 <= month <= 12 and 1 <= day <= 31:
            return year, month, day

    m = _MONTH_NAME_DATE.search(text)
    if m:
        month = _MONTH_TOKENS[m.group(1).lower()]
        day = int(m.group(2))
        year = int(m.group(3)) if m.group(3) else anchor.year
        if 1 <= day <= 31:
            return year, month, day

    if _RELATIVE_TODAY.search(text):
        return anchor.year, anchor.month, anchor.day

    if _RELATIVE_TOMORROW.search(text):
        nxt = anchor + timedelta(days=1)
        return nxt.year, nxt.month, nxt.day

    m = _RELATIVE_NEXT_WEEKDAY.search(text)
    if m:
        _, idx = _WEEKDAY_TOKENS[m.group(1).lower()]
        target = _resolve_next_weekday(anchor, idx)
        return target.year, target.month, target.day

    m = _RELATIVE_THIS_WEEKDAY.search(text)
    if m:
        _, idx = _WEEKDAY_TOKENS[m.group(1).lower()]
        target = _resolve_this_weekday(anchor, idx)
        return target.year, target.month, target.day

    m = _AMERICAN_DATE_SHORT.search(text)
    if m:
        month = int(m.group(1))
        day = int(m.group(2))
        if 1 <= month <= 12 and 1 <= day <= 31:
            return anchor.year, month, day

    m = _BARE_WEEKDAY.search(text)
    if m:
        _, idx = _WEEKDAY_TOKENS[m.group(1).lower()]
        target = _resolve_this_weekday(anchor, idx)
        return target.year, target.month, target.day

    return None


def parse_datetime(natural: str, tick_iso: str) -> Optional[datetime]:
    """Parse a natural-language datetime against the tick-time reference.

    Returns a timezone-aware datetime in America/New_York, or None when
    the fragment doesn't yield a parseable date.
    """
    if not isinstance(natural, str) or not natural.strip():
        return None
    try:
        anchor = datetime.fromisoformat(tick_iso)
    except (TypeError, ValueError):
        return None
    tz = ZoneInfo(DEFAULT_TIMEZONE)
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=tz)
    else:
        anchor = anchor.astimezone(tz)

    ymd = _parse_date_component(natural, anchor)
    if ymd is None:
        return None
    year, month, day = ymd

    time_component = _parse_time_component(natural)
    hour, minute = time_component if time_component else (0, 0)

    try:
        return datetime(year, month, day, hour, minute, 0, tzinfo=tz)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Duration parsing
# ---------------------------------------------------------------------------


_DURATION_HOUR = re.compile(r"(\d+)\s*(?:hours?|hrs?|h)\b", re.IGNORECASE)
_DURATION_MIN = re.compile(r"(\d+)\s*(?:minutes?|mins?|m)\b", re.IGNORECASE)
_DURATION_DAY = re.compile(r"(\d+)\s*(?:days?|d)\b", re.IGNORECASE)


def parse_duration(natural: Optional[str]) -> Optional[timedelta]:
    """Parse "30 minutes", "1 hour", "2 hours 15 minutes", "1 day"."""
    if not isinstance(natural, str) or not natural.strip():
        return None
    total = timedelta()
    matched = False
    for pat, unit in (
        (_DURATION_DAY, "day"),
        (_DURATION_HOUR, "hour"),
        (_DURATION_MIN, "minute"),
    ):
        m = pat.search(natural)
        if m:
            n = int(m.group(1))
            if unit == "day":
                total += timedelta(days=n)
            elif unit == "hour":
                total += timedelta(hours=n)
            else:
                total += timedelta(minutes=n)
            matched = True
    if not matched:
        return None
    if total <= timedelta(0):
        return None
    return total


# ---------------------------------------------------------------------------
# Recurrence parsing
# ---------------------------------------------------------------------------


_BIWEEKLY = re.compile(
    r"\b(?:biweekly|every\s+other\s+week|fortnightly|every\s+two\s+weeks)\b",
    re.IGNORECASE,
)
_WEEKLY_KEYWORD = re.compile(
    r"\b(?:weekly|every\s+week|every)\b",
    re.IGNORECASE,
)
_MONTHLY_DAYOFMONTH = re.compile(
    r"\bmonthly\s+on\s+the\s+(\d{1,2})\w*\b"
    r"|\bevery\s+month\s+on\s+the\s+(\d{1,2})\w*\b"
    r"|\bon\s+the\s+(\d{1,2})\w*\s+of\s+(?:each|every)\s+month\b",
    re.IGNORECASE,
)


# Tokens / connectors allowed to appear alongside a recognized recurrence
# phrase without disqualifying it. Anything else in the phrase is treated
# as "we don't understand this" → unsupported.
_FILLER_TOKENS = re.compile(
    r"\b(?:on|the|of|month|each|every|and)\b|[,\s\-]+|"
    r"(?:1st|2nd|3rd|\d+th)",
    re.IGNORECASE,
)
_FILLER_PUNCT = re.compile(r"[.,;:!?]+")


def _phrase_is_fully_explained(text: str, consumed_spans: list[tuple[int, int]]) -> bool:
    """Return True when every non-filler character in ``text`` is consumed."""
    mask = [False] * len(text)
    for start, end in consumed_spans:
        for i in range(start, end):  # pragma: no branch
            # spans come from re.Match.span() which is always in-bounds of
            # the source text; the guard below is defensive belt-and-braces.
            if 0 <= i < len(text):  # pragma: no branch
                mask[i] = True
    leftover_chars: list[str] = []
    for i, ch in enumerate(text):
        if not mask[i]:
            leftover_chars.append(ch)
    leftover = "".join(leftover_chars)
    # Remove filler tokens; if anything substantive remains we don't understand
    # the phrase.
    leftover = _FILLER_PUNCT.sub(" ", leftover)
    leftover = _FILLER_TOKENS.sub(" ", leftover).strip()
    return leftover == ""


def parse_recurrence(natural: Optional[str]) -> Optional[str]:
    """Convert a natural-language recurrence phrase to an RFC 5545 RRULE.

    Returns the RRULE string, or None when the phrase does not match any
    supported pattern (capture must then surface a missing_fields entry).

    Strictness: the entire phrase must be reducible to (a) one of the
    supported patterns + (b) connective filler ("on", "the", "of",
    "month", weekday names, ordinal suffixes, punctuation). Any other
    substantive token disqualifies the phrase — keeps the contract honest
    that "anything outside the supported set → missing_fields".
    """
    if not isinstance(natural, str) or not natural.strip():
        return None
    text = natural.strip()

    # 1. By-weekday-of-month (ordinal + weekday) → MONTHLY;BYDAY.
    ordinal_pattern = re.compile(
        r"\b(first|second|third|fourth|fifth|last)\s+"
        r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        re.IGNORECASE,
    )
    matches = list(ordinal_pattern.finditer(text))
    if matches:
        tokens: list[str] = []
        spans: list[tuple[int, int]] = []
        for m in matches:
            ord_num = _ORDINAL_TOKENS[m.group(1).lower()]
            day_token, _ = _WEEKDAY_TOKENS[m.group(2).lower()]
            tokens.append(f"{ord_num}{day_token}")
            spans.append(m.span())
        if _phrase_is_fully_explained(text, spans):
            return f"RRULE:FREQ=MONTHLY;BYDAY={','.join(tokens)}"
        return None

    # 2. Monthly on numeric day.
    m = _MONTHLY_DAYOFMONTH.search(text)
    if m:
        day = next((g for g in m.groups() if g), None)
        if day is not None and _phrase_is_fully_explained(text, [m.span()]):
            return f"RRULE:FREQ=MONTHLY;BYMONTHDAY={int(day)}"
        return None

    # 3. Biweekly (optionally with a weekday).
    biweekly_match = _BIWEEKLY.search(text)
    if biweekly_match:
        spans = [biweekly_match.span()]
        weekday_tokens: list[str] = []
        for m in re.finditer(
            r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)s?\b",
            text,
            flags=re.IGNORECASE,
        ):
            token, _ = _WEEKDAY_TOKENS[m.group(1).lower()]
            if token not in weekday_tokens:
                weekday_tokens.append(token)
            spans.append(m.span())
        if not _phrase_is_fully_explained(text, spans):
            return None
        if weekday_tokens:
            return f"RRULE:FREQ=WEEKLY;INTERVAL=2;BYDAY={','.join(weekday_tokens)}"
        return "RRULE:FREQ=WEEKLY;INTERVAL=2"

    # 4. Weekly with one or more weekdays.
    weekly_kw = _WEEKLY_KEYWORD.search(text)
    weekday_iter = list(re.finditer(
        r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)s?\b",
        text,
        flags=re.IGNORECASE,
    ))
    if weekday_iter and (weekly_kw or any(m.group(0).lower().endswith("s") for m in weekday_iter)):
        spans = [m.span() for m in weekday_iter]
        if weekly_kw:
            spans.append(weekly_kw.span())
        weekday_tokens = []
        for m in weekday_iter:
            token, _ = _WEEKDAY_TOKENS[m.group(1).lower()]
            if token not in weekday_tokens:
                weekday_tokens.append(token)
        if _phrase_is_fully_explained(text, spans):
            return f"RRULE:FREQ=WEEKLY;BYDAY={','.join(weekday_tokens)}"
        return None

    return None


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def _coerce_title(value: object) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _fields_so_far(block: dict) -> dict:
    """Echo the parseable input shape used to surface partial captures."""
    keys = (
        "title",
        "start_natural",
        "end_natural",
        "duration_natural",
        "location",
        "recurrence_natural",
        "attendees",
        "source_inbox_path",
        "source_block_index",
    )
    return {k: block.get(k) for k in keys}


def _rfc3339(dt: datetime) -> str:
    """Render a timezone-aware datetime as RFC 3339 with explicit offset."""
    return dt.strftime("%Y-%m-%dT%H:%M:%S%z")[:-2] + ":" + dt.strftime("%z")[-2:]


def validate(block: dict) -> dict:
    """Validate an ExtractedCalendarBlock; return the contract-shaped output."""
    missing: list[str] = []

    title = _coerce_title(block.get("title"))
    if title is None:
        missing.append("title")

    tick_iso = block.get("tick_iso")
    start_natural = block.get("start_natural")
    start_dt = parse_datetime(start_natural, tick_iso) if isinstance(tick_iso, str) else None
    if start_dt is None:
        missing.append("start_datetime")

    # end_or_duration is satisfied when EITHER an end datetime parses OR a
    # duration parses; both are checked independently of start so the
    # missing_fields report stays a faithful diagnosis of each individual
    # field (per contract — "absent or unparseable").
    end_natural = block.get("end_natural")
    end_dt_candidate: Optional[datetime] = None
    if isinstance(end_natural, str) and end_natural.strip() and isinstance(tick_iso, str):
        end_dt_candidate = parse_datetime(end_natural, tick_iso)
    duration = parse_duration(block.get("duration_natural"))
    has_end_or_duration = end_dt_candidate is not None or duration is not None
    if not has_end_or_duration:
        missing.append("end_or_duration")

    # Resolve the actual end_dt only when start_dt is known.
    end_dt: Optional[datetime] = None
    if start_dt is not None:
        if end_dt_candidate is not None:
            end_dt = end_dt_candidate
        elif duration is not None:
            end_dt = start_dt + duration

    recurrence_natural = block.get("recurrence_natural")
    rrule: Optional[str] = None
    if isinstance(recurrence_natural, str) and recurrence_natural.strip():
        rrule = parse_recurrence(recurrence_natural)
        if rrule is None:
            missing.append("recurrence_pattern")

    if missing:
        return {
            "complete": False,
            "missing_fields": missing,
            "fields_so_far": _fields_so_far(block),
        }

    # All required parts present — assemble the payload.
    assert title is not None
    assert start_dt is not None
    assert end_dt is not None
    source_inbox_path = block["source_inbox_path"]
    description = f"Source: {os.path.basename(source_inbox_path)}"

    payload = {
        "action": "create_calendar_event",
        "calendar_id": DEFAULT_CALENDAR_ID,
        "account": DEFAULT_ACCOUNT,
        "summary": title,
        "start_rfc3339": _rfc3339(start_dt),
        "end_rfc3339": _rfc3339(end_dt),
        "start_timezone": DEFAULT_TIMEZONE,
        "location": block.get("location"),
        "description": description,
        "rrule": rrule,
        "attendees": block.get("attendees"),
        "source_inbox_path": source_inbox_path,
    }
    return {
        "complete": True,
        "missing_fields": [],
        "calendar_event_payload": payload,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        print("INVALID_INPUT_JSON: empty stdin", file=sys.stderr)
        return 2
    try:
        block = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"INVALID_INPUT_JSON: {exc}", file=sys.stderr)
        return 2
    if not isinstance(block, dict):
        print("INVALID_INPUT_JSON: top-level value is not a JSON object", file=sys.stderr)
        return 2

    missing_field = _missing_required(block)
    if missing_field is not None:
        print(f"MISSING_INPUT_FIELD: {missing_field}", file=sys.stderr)
        return 3

    try:
        result = validate(block)
    except Exception:  # pragma: no cover — defensive; tests cover via monkeypatch
        print(f"INTERNAL_ERROR: {traceback.format_exc()}", file=sys.stderr)
        return 4

    sys.stdout.write(json.dumps(result) + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
