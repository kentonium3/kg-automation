"""Unit tests for the canonical Eastern-time utilities (#761).

These pin the behavior the migrated surfaces depend on: the DST-correct
end-of-day write (#733), the Vikunja-instant parse that tolerates UTC-``Z``
normalization while rejecting the year-1 sentinel (#736/#757), the Eastern
calendar-date read, and the render-in-ET conversion (#759).
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from scripts.common import et_datetime as et

UTC = timezone.utc


# ---------------------------------------------------------------------------
# et_end_of_day (#733)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "target, expected",
    [
        ("2026-06-15", "2026-06-15T23:59:59-04:00"),  # EDT
        ("2026-01-15", "2026-01-15T23:59:59-05:00"),  # EST
        ("2026-03-09", "2026-03-09T23:59:59-04:00"),  # day after spring-forward
        ("2026-03-07", "2026-03-07T23:59:59-05:00"),  # day before spring-forward
    ],
)
def test_et_end_of_day_dst_offsets(target, expected):
    assert et.et_end_of_day(target) == expected


def test_et_end_of_day_accepts_date_object():
    assert et.et_end_of_day(date(2026, 6, 15)) == "2026-06-15T23:59:59-04:00"


@pytest.mark.parametrize("bad", ["2026-13-99", "not-a-date", "2026/06/15"])
def test_et_end_of_day_rejects_malformed_string(bad):
    with pytest.raises(ValueError):
        et.et_end_of_day(bad)


@pytest.mark.parametrize("pre_standard", ["0001-01-01", "1800-06-15"])
def test_et_end_of_day_rejects_pre_standard_offset(pre_standard):
    # Pre-1883 Local Mean Time offsets carry sub-minute seconds → not a modern
    # Eastern date; must raise rather than emit a malformed instant.
    with pytest.raises(ValueError, match="non-standard UTC offset"):
        et.et_end_of_day(pre_standard)


def test_et_end_of_day_round_trips_to_the_same_date_in_et():
    written = et.et_end_of_day("2026-07-20")
    # Vikunja would store this as UTC-Z; the Eastern calendar date must survive.
    assert et.et_calendar_date(written) == date(2026, 7, 20)


# ---------------------------------------------------------------------------
# parse_vikunja_instant (#736/#757)
# ---------------------------------------------------------------------------


def test_parse_vikunja_instant_utc_z():
    got = et.parse_vikunja_instant("2026-07-21T03:59:59Z")
    assert got == datetime(2026, 7, 21, 3, 59, 59, tzinfo=UTC)


def test_parse_vikunja_instant_et_offset_normalizes_to_utc():
    # An ET-offset write and its UTC-Z readback are the SAME instant (#757).
    et_write = et.parse_vikunja_instant("2026-07-20T23:59:59-04:00")
    utc_readback = et.parse_vikunja_instant("2026-07-21T03:59:59Z")
    assert et_write == utc_readback


@pytest.mark.parametrize(
    "sentinel",
    [
        "0001-01-01T00:00:00Z",
        "0001-01-01T00:00:00+00:00",
        "0001-01-01",
    ],
)
def test_parse_vikunja_instant_rejects_year1_sentinel(sentinel):
    assert et.parse_vikunja_instant(sentinel) is None


@pytest.mark.parametrize(
    "bad", [None, 42, "", "   ", "not-a-date", "2026-07-20T23:59:59"]
)
def test_parse_vikunja_instant_rejects_bad_values(bad):
    # The last case is a NAIVE datetime — excluded (not assumed UTC), matching
    # the escalation read-side's "don't guess a timezone" safety choice.
    assert et.parse_vikunja_instant(bad) is None


# ---------------------------------------------------------------------------
# et_calendar_date (#736)
# ---------------------------------------------------------------------------


def test_et_calendar_date_utc_evening_is_prior_eastern_day():
    # 2026-07-21T02:00:00Z == 2026-07-20 22:00 EDT → Eastern date is the 20th.
    assert et.et_calendar_date("2026-07-21T02:00:00Z") == date(2026, 7, 20)


def test_et_calendar_date_excludes_sentinel_and_naive():
    assert et.et_calendar_date("0001-01-01T00:00:00Z") is None
    assert et.et_calendar_date("2026-07-20T00:00:00") is None  # naive


def test_et_calendar_date_zone_override():
    # In UTC the calendar date is the 21st; in ET it is the 20th.
    value = "2026-07-21T02:00:00Z"
    assert et.et_calendar_date(value, zone=UTC) == date(2026, 7, 21)
    assert et.et_calendar_date(value) == date(2026, 7, 20)


# ---------------------------------------------------------------------------
# to_et / today_et (#759 render, #733 today)
# ---------------------------------------------------------------------------


def test_to_et_converts_aware_utc():
    got = et.to_et(datetime(2026, 7, 21, 3, 0, 0, tzinfo=UTC))
    assert got.utcoffset().total_seconds() == -4 * 3600
    assert (got.year, got.month, got.day, got.hour) == (2026, 7, 20, 23)


def test_to_et_naive_assumed_utc_by_default():
    got = et.to_et(datetime(2026, 7, 21, 3, 0, 0))
    assert got == datetime(2026, 7, 21, 3, 0, 0, tzinfo=UTC).astimezone(et.ET_ZONE)


def test_to_et_naive_assume_et_for_wallclock_callers():
    # Calendar routing treats a naive anchor as wall-clock Eastern.
    got = et.to_et(datetime(2026, 7, 20, 9, 0, 0), assume=et.ET_ZONE)
    assert (got.year, got.month, got.day, got.hour) == (2026, 7, 20, 9)
    assert got.tzinfo is et.ET_ZONE or str(got.tzinfo) == "America/New_York"


def test_today_et_uses_eastern_calendar_date():
    # 00:30 UTC on the 21st is still 20:30 ET on the 20th.
    now = datetime(2026, 7, 21, 0, 30, 0, tzinfo=UTC)
    assert et.today_et(now=now) == date(2026, 7, 20)


def test_today_et_defaults_to_now():
    assert isinstance(et.today_et(), date)
