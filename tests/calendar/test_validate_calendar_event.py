"""Tests for `scripts/calendar_routing/validate_calendar_event.py`.

Fixture-driven validator tests + explicit edge-case coverage. Tests use
direct module imports for speed; one subprocess-mode smoke test confirms
the CLI surface still wires stdin/stdout/exit codes correctly.

Per DIRECTIVE_034 these tests were authored before the helper's
implementation reached green.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.calendar_routing import validate_calendar_event as vce  # noqa: E402


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _fixture_pairs() -> list[tuple[str, Path, Path]]:
    pairs: list[tuple[str, Path, Path]] = []
    for input_path in sorted(FIXTURES_DIR.glob("*.input.json")):
        name = input_path.name.removesuffix(".input.json")
        expected_path = FIXTURES_DIR / f"{name}.expected.json"
        assert expected_path.exists(), f"Missing expected file for {name}"
        pairs.append((name, input_path, expected_path))
    return pairs


@pytest.mark.parametrize(
    "name,input_path,expected_path", _fixture_pairs(), ids=lambda x: x if isinstance(x, str) else ""
)
def test_fixture_roundtrip(name: str, input_path: Path, expected_path: Path) -> None:
    """For every fixture pair, validate() should produce the expected output."""
    block = json.loads(input_path.read_text())
    expected = json.loads(expected_path.read_text())
    actual = vce.validate(block)
    assert actual == expected, f"Fixture {name} mismatch.\nExpected: {json.dumps(expected, indent=2)}\nActual:   {json.dumps(actual, indent=2)}"


# ---------------------------------------------------------------------------
# Explicit branch / edge-case coverage
# ---------------------------------------------------------------------------


def test_missing_title_reports_missing_field() -> None:
    block = {
        "title": None,
        "start_natural": "June 10, 2026 at 2pm",
        "end_natural": "June 10, 2026 at 3pm",
        "source_inbox_path": "/tmp/Inbox 2026-06-07 1000.md",
        "source_block_index": 0,
        "tick_iso": "2026-06-07T10:00:00-04:00",
    }
    result = vce.validate(block)
    assert result["complete"] is False
    assert "title" in result["missing_fields"]


def test_missing_title_empty_string_reports_missing_field() -> None:
    block = {
        "title": "   ",
        "start_natural": "June 10, 2026 at 2pm",
        "end_natural": "June 10, 2026 at 3pm",
        "source_inbox_path": "/tmp/Inbox 2026-06-07 1000.md",
        "source_block_index": 0,
        "tick_iso": "2026-06-07T10:00:00-04:00",
    }
    result = vce.validate(block)
    assert result["complete"] is False
    assert "title" in result["missing_fields"]


def test_recurrence_multiple_weekdays() -> None:
    block = {
        "title": "Yoga",
        "start_natural": "June 9, 2026 at 7am",
        "duration_natural": "1 hour",
        "recurrence_natural": "every Tuesday and Thursday",
        "source_inbox_path": "/tmp/Inbox 2026-06-07 1000.md",
        "source_block_index": 0,
        "tick_iso": "2026-06-07T10:00:00-04:00",
    }
    result = vce.validate(block)
    assert result["complete"] is True
    assert result["calendar_event_payload"]["rrule"] == "RRULE:FREQ=WEEKLY;BYDAY=TU,TH"


def test_recurrence_last_friday() -> None:
    block = {
        "title": "Monthly review",
        "start_natural": "June 26, 2026 at 4pm",
        "duration_natural": "30 minutes",
        "recurrence_natural": "last Friday of the month",
        "source_inbox_path": "/tmp/Inbox 2026-06-07 1000.md",
        "source_block_index": 0,
        "tick_iso": "2026-06-07T10:00:00-04:00",
    }
    result = vce.validate(block)
    assert result["complete"] is True
    assert result["calendar_event_payload"]["rrule"] == "RRULE:FREQ=MONTHLY;BYDAY=-1FR"


def test_recurrence_every_other_week_no_weekday() -> None:
    """'every other week' without a weekday → biweekly interval only."""
    block = {
        "title": "Sprint planning",
        "start_natural": "June 9, 2026 at 10am",
        "duration_natural": "1 hour",
        "recurrence_natural": "every other week",
        "source_inbox_path": "/tmp/Inbox 2026-06-07 1000.md",
        "source_block_index": 0,
        "tick_iso": "2026-06-07T10:00:00-04:00",
    }
    result = vce.validate(block)
    assert result["complete"] is True
    assert result["calendar_event_payload"]["rrule"] == "RRULE:FREQ=WEEKLY;INTERVAL=2"


def test_recurrence_second_tuesday_fourth_thursday() -> None:
    block = {
        "title": "Council meeting",
        "start_natural": "June 9, 2026 at 7pm",
        "duration_natural": "2 hours",
        "recurrence_natural": "second Tuesday and fourth Thursday of the month",
        "source_inbox_path": "/tmp/Inbox 2026-06-07 1000.md",
        "source_block_index": 0,
        "tick_iso": "2026-06-07T10:00:00-04:00",
    }
    result = vce.validate(block)
    assert result["complete"] is True
    assert result["calendar_event_payload"]["rrule"] == "RRULE:FREQ=MONTHLY;BYDAY=2TU,4TH"


def test_time_form_midnight() -> None:
    block = {
        "title": "Midnight reflection",
        "start_natural": "June 10, 2026 at midnight",
        "duration_natural": "30 minutes",
        "source_inbox_path": "/tmp/Inbox 2026-06-07 1000.md",
        "source_block_index": 0,
        "tick_iso": "2026-06-07T10:00:00-04:00",
    }
    result = vce.validate(block)
    assert result["complete"] is True
    assert result["calendar_event_payload"]["start_rfc3339"].startswith("2026-06-10T00:00:00")


def test_time_form_24h() -> None:
    block = {
        "title": "Standup",
        "start_natural": "June 10, 2026 at 14:00",
        "duration_natural": "30 minutes",
        "source_inbox_path": "/tmp/Inbox 2026-06-07 1000.md",
        "source_block_index": 0,
        "tick_iso": "2026-06-07T10:00:00-04:00",
    }
    result = vce.validate(block)
    assert result["complete"] is True
    assert result["calendar_event_payload"]["start_rfc3339"].startswith("2026-06-10T14:00:00")


def test_time_form_with_minutes_lowercase_am() -> None:
    block = {
        "title": "Workout",
        "start_natural": "June 10, 2026 at 6:30 am",
        "duration_natural": "45 minutes",
        "source_inbox_path": "/tmp/Inbox 2026-06-07 1000.md",
        "source_block_index": 0,
        "tick_iso": "2026-06-07T10:00:00-04:00",
    }
    result = vce.validate(block)
    assert result["complete"] is True
    assert result["calendar_event_payload"]["start_rfc3339"].startswith("2026-06-10T06:30:00")


def test_anchor_next_weekday_when_today_is_same_weekday_skips_a_week() -> None:
    """'next Tuesday' when tick IS Tuesday → 7 days out, not today."""
    block = {
        "title": "Recurring sync",
        "start_natural": "next Tuesday at 10am",
        "duration_natural": "30 minutes",
        "source_inbox_path": "/tmp/Inbox 2026-06-09 1000.md",
        "source_block_index": 0,
        "tick_iso": "2026-06-09T10:00:00-04:00",
    }
    result = vce.validate(block)
    assert result["complete"] is True
    assert result["calendar_event_payload"]["start_rfc3339"].startswith("2026-06-16T")


def test_anchor_this_weekday() -> None:
    """'this Friday' from Sunday should land on the upcoming Friday."""
    block = {
        "title": "Pickup laundry",
        "start_natural": "this Friday at 3pm",
        "duration_natural": "15 minutes",
        "source_inbox_path": "/tmp/Inbox 2026-06-07 1000.md",
        "source_block_index": 0,
        "tick_iso": "2026-06-07T10:00:00-04:00",
    }
    result = vce.validate(block)
    assert result["complete"] is True
    assert result["calendar_event_payload"]["start_rfc3339"].startswith("2026-06-12T")


def test_anchor_today() -> None:
    block = {
        "title": "Quick errand",
        "start_natural": "today at 3pm",
        "duration_natural": "30 minutes",
        "source_inbox_path": "/tmp/Inbox 2026-06-07 1000.md",
        "source_block_index": 0,
        "tick_iso": "2026-06-07T10:00:00-04:00",
    }
    result = vce.validate(block)
    assert result["complete"] is True
    assert result["calendar_event_payload"]["start_rfc3339"].startswith("2026-06-07T15:00:00")


def test_iso_date_explicit() -> None:
    block = {
        "title": "Doctor",
        "start_natural": "2026-07-15 at 9am",
        "duration_natural": "30 minutes",
        "source_inbox_path": "/tmp/Inbox 2026-06-07 1000.md",
        "source_block_index": 0,
        "tick_iso": "2026-06-07T10:00:00-04:00",
    }
    result = vce.validate(block)
    assert result["complete"] is True
    assert result["calendar_event_payload"]["start_rfc3339"].startswith("2026-07-15T09:00:00")


def test_american_slash_date() -> None:
    block = {
        "title": "Pickup",
        "start_natural": "6/15/2026 at 2pm",
        "duration_natural": "30 minutes",
        "source_inbox_path": "/tmp/Inbox 2026-06-07 1000.md",
        "source_block_index": 0,
        "tick_iso": "2026-06-07T10:00:00-04:00",
    }
    result = vce.validate(block)
    assert result["complete"] is True
    assert result["calendar_event_payload"]["start_rfc3339"].startswith("2026-06-15T14:00:00")


def test_duration_complex_hours_and_minutes() -> None:
    block = {
        "title": "Workshop",
        "start_natural": "June 10, 2026 at 9am",
        "duration_natural": "2 hours 15 minutes",
        "source_inbox_path": "/tmp/Inbox 2026-06-07 1000.md",
        "source_block_index": 0,
        "tick_iso": "2026-06-07T10:00:00-04:00",
    }
    result = vce.validate(block)
    assert result["complete"] is True
    assert result["calendar_event_payload"]["end_rfc3339"].startswith("2026-06-10T11:15:00")


def test_end_takes_precedence_over_duration_when_both_present() -> None:
    block = {
        "title": "Long meeting",
        "start_natural": "June 10, 2026 at 9am",
        "end_natural": "June 10, 2026 at 5pm",
        "duration_natural": "30 minutes",
        "source_inbox_path": "/tmp/Inbox 2026-06-07 1000.md",
        "source_block_index": 0,
        "tick_iso": "2026-06-07T10:00:00-04:00",
    }
    result = vce.validate(block)
    assert result["complete"] is True
    # end_natural wins.
    assert result["calendar_event_payload"]["end_rfc3339"].startswith("2026-06-10T17:00:00")


def test_all_day_event_date_only() -> None:
    """start_natural is a date-only string → defaults to 00:00; end uses 1-day default."""
    block = {
        "title": "Anniversary",
        "start_natural": "June 14, 2026",
        "duration_natural": "1 day",
        "source_inbox_path": "/tmp/Inbox 2026-06-07 1000.md",
        "source_block_index": 0,
        "tick_iso": "2026-06-07T10:00:00-04:00",
    }
    result = vce.validate(block)
    assert result["complete"] is True
    assert result["calendar_event_payload"]["start_rfc3339"].startswith("2026-06-14T00:00:00")


def test_multiple_missing_fields_reported() -> None:
    block = {
        "title": "Mystery event",
        "start_natural": "vibes only",
        "duration_natural": "uhhh",
        "recurrence_natural": "perhaps quarterly when the moon",
        "source_inbox_path": "/tmp/Inbox 2026-06-07 1000.md",
        "source_block_index": 0,
        "tick_iso": "2026-06-07T10:00:00-04:00",
    }
    result = vce.validate(block)
    assert result["complete"] is False
    assert "start_datetime" in result["missing_fields"]
    assert "end_or_duration" in result["missing_fields"]
    assert "recurrence_pattern" in result["missing_fields"]


def test_unrecognized_recurrence_phrase() -> None:
    block = {
        "title": "Quarterly thing",
        "start_natural": "June 10, 2026 at 2pm",
        "duration_natural": "1 hour",
        "recurrence_natural": "every third Wednesday of every other quarter",
        "source_inbox_path": "/tmp/Inbox 2026-06-07 1000.md",
        "source_block_index": 0,
        "tick_iso": "2026-06-07T10:00:00-04:00",
    }
    result = vce.validate(block)
    assert result["complete"] is False
    assert "recurrence_pattern" in result["missing_fields"]


# ---------------------------------------------------------------------------
# CLI surface — subprocess smoke tests
# ---------------------------------------------------------------------------


HELPER = REPO_ROOT / "scripts" / "calendar_routing" / "validate_calendar_event.py"


def test_cli_complete_event_emits_json_exit_zero() -> None:
    block = json.loads((FIXTURES_DIR / "complete_oneoff.input.json").read_text())
    proc = subprocess.run(
        [sys.executable, str(HELPER)],
        input=json.dumps(block),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"stderr={proc.stderr}"
    out = json.loads(proc.stdout)
    assert out["complete"] is True
    assert out["calendar_event_payload"]["summary"] == "Dentist cleaning"


def test_cli_malformed_json_exits_2() -> None:
    proc = subprocess.run(
        [sys.executable, str(HELPER)],
        input="this is not JSON {{{",
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 2
    assert "INVALID_INPUT_JSON" in proc.stderr


def test_cli_empty_stdin_exits_2() -> None:
    proc = subprocess.run(
        [sys.executable, str(HELPER)],
        input="",
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 2
    assert "INVALID_INPUT_JSON" in proc.stderr


def test_cli_missing_required_field_exits_3() -> None:
    proc = subprocess.run(
        [sys.executable, str(HELPER)],
        input=json.dumps({}),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 3
    assert "MISSING_INPUT_FIELD" in proc.stderr


def test_cli_missing_tick_iso_exits_3() -> None:
    """tick_iso is required because the helper is pure (no wall clock)."""
    proc = subprocess.run(
        [sys.executable, str(HELPER)],
        input=json.dumps({
            "title": "X",
            "start_natural": "June 10, 2026 at 2pm",
            "source_inbox_path": "/tmp/Inbox.md",
            "source_block_index": 0,
        }),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 3
    assert "MISSING_INPUT_FIELD: tick_iso" in proc.stderr


def test_cli_incomplete_event_still_exits_zero() -> None:
    block = json.loads((FIXTURES_DIR / "incomplete_no_start.input.json").read_text())
    proc = subprocess.run(
        [sys.executable, str(HELPER)],
        input=json.dumps(block),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["complete"] is False


# ---------------------------------------------------------------------------
# Internal-error / contract details
# ---------------------------------------------------------------------------


def test_validate_purity_no_side_effects() -> None:
    """Calling validate() repeatedly with the same input yields the same output."""
    block = json.loads((FIXTURES_DIR / "complete_weekly.input.json").read_text())
    r1 = vce.validate(block)
    r2 = vce.validate(block)
    assert r1 == r2


def test_description_uses_basename_not_full_path() -> None:
    block = json.loads((FIXTURES_DIR / "complete_oneoff.input.json").read_text())
    result = vce.validate(block)
    desc = result["calendar_event_payload"]["description"]
    assert desc == "Source: Inbox 2026-06-07 1000.md"
    assert "/home/" not in desc


# ---------------------------------------------------------------------------
# In-process main() tests — exercise the CLI surface for coverage
# ---------------------------------------------------------------------------


def _run_main(monkeypatch, stdin_text: str) -> tuple[int, str, str]:
    import io
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin_text))
    monkeypatch.setattr(sys, "stdout", stdout_buf)
    monkeypatch.setattr(sys, "stderr", stderr_buf)
    rc = vce.main()
    return rc, stdout_buf.getvalue(), stderr_buf.getvalue()


def test_main_empty_stdin(monkeypatch) -> None:
    rc, out, err = _run_main(monkeypatch, "")
    assert rc == 2
    assert out == ""
    assert "INVALID_INPUT_JSON" in err


def test_main_malformed_json(monkeypatch) -> None:
    rc, out, err = _run_main(monkeypatch, "not json")
    assert rc == 2
    assert "INVALID_INPUT_JSON" in err


def test_main_top_level_not_object(monkeypatch) -> None:
    rc, out, err = _run_main(monkeypatch, "[1, 2, 3]")
    assert rc == 2
    assert "INVALID_INPUT_JSON" in err
    assert "top-level" in err


def test_main_missing_required_field(monkeypatch) -> None:
    rc, out, err = _run_main(monkeypatch, "{}")
    assert rc == 3
    assert "MISSING_INPUT_FIELD" in err


def test_main_missing_field_non_string_index(monkeypatch) -> None:
    """source_block_index must be an int."""
    block = {
        "title": "X",
        "start_natural": "today at 3pm",
        "source_inbox_path": "/tmp/x.md",
        "source_block_index": "0",  # wrong type
        "tick_iso": "2026-06-07T10:00:00-04:00",
    }
    rc, out, err = _run_main(monkeypatch, json.dumps(block))
    assert rc == 3
    assert "source_block_index" in err


def test_main_complete_event(monkeypatch) -> None:
    block = json.loads((FIXTURES_DIR / "complete_oneoff.input.json").read_text())
    rc, out, err = _run_main(monkeypatch, json.dumps(block))
    assert rc == 0
    parsed = json.loads(out)
    assert parsed["complete"] is True


def test_main_incomplete_event(monkeypatch) -> None:
    block = json.loads((FIXTURES_DIR / "incomplete_no_start.input.json").read_text())
    rc, out, err = _run_main(monkeypatch, json.dumps(block))
    assert rc == 0
    parsed = json.loads(out)
    assert parsed["complete"] is False


def test_main_internal_error_exit_4(monkeypatch) -> None:
    """When validate() raises unexpectedly, main() returns 4."""
    def boom(_block):
        raise RuntimeError("synthetic")

    monkeypatch.setattr(vce, "validate", boom)
    block = json.loads((FIXTURES_DIR / "complete_oneoff.input.json").read_text())
    rc, out, err = _run_main(monkeypatch, json.dumps(block))
    assert rc == 4
    assert "INTERNAL_ERROR" in err


# ---------------------------------------------------------------------------
# Unit tests for internal parser components
# ---------------------------------------------------------------------------


def test_parse_time_24h_only() -> None:
    assert vce._parse_time_component("at 23:45 sharp") == (23, 45)


def test_parse_time_invalid_returns_none() -> None:
    assert vce._parse_time_component("at 99:99") is None
    assert vce._parse_time_component("when convenient") is None


def test_parse_time_25_oclock_12h_returns_none() -> None:
    """13pm is not a real time; the parser must reject it."""
    # 13 PM would normalize to 25 — out of range; parser returns None.
    assert vce._parse_time_component("at 25pm") is None


def test_parse_duration_no_match() -> None:
    assert vce.parse_duration("soon") is None
    assert vce.parse_duration("") is None
    assert vce.parse_duration(None) is None


def test_parse_duration_zero_returns_none() -> None:
    assert vce.parse_duration("0 minutes") is None


def test_parse_datetime_invalid_tick_iso() -> None:
    """Unparseable tick_iso → parse_datetime returns None gracefully."""
    assert vce.parse_datetime("June 10, 2026 at 2pm", "not an iso string") is None


def test_parse_datetime_empty_natural() -> None:
    assert vce.parse_datetime("", "2026-06-07T10:00:00-04:00") is None
    assert vce.parse_datetime(None, "2026-06-07T10:00:00-04:00") is None


def test_parse_datetime_invalid_calendar_date() -> None:
    """February 30 should not parse to a real date."""
    assert vce.parse_datetime("February 30, 2026 at 2pm", "2026-06-07T10:00:00-04:00") is None


def test_parse_recurrence_empty_and_none() -> None:
    assert vce.parse_recurrence(None) is None
    assert vce.parse_recurrence("") is None
    assert vce.parse_recurrence("   ") is None


def test_parse_recurrence_bare_weekday_no_keyword_is_unrecognized() -> None:
    """Just "Tuesday" with no 'every' / 'weekly' / plural 's' is ambiguous."""
    assert vce.parse_recurrence("Tuesday") is None


def test_parse_recurrence_plural_weekdays_only() -> None:
    """'Tuesdays' alone is enough to mean weekly."""
    assert vce.parse_recurrence("Tuesdays") == "RRULE:FREQ=WEEKLY;BYDAY=TU"


def test_parse_recurrence_anchored_naive_tick(monkeypatch) -> None:
    """tick_iso without offset triggers the timezone-fill branch."""
    # naive ISO → parse_datetime should still resolve via DEFAULT_TIMEZONE.
    result = vce.parse_datetime("today at 3pm", "2026-06-07T10:00:00")
    assert result is not None
    assert result.strftime("%Y-%m-%d") == "2026-06-07"


def test_anchor_in_non_local_timezone_normalizes_to_ny() -> None:
    """tick_iso with a non-NY offset should still anchor against NY local."""
    # 2026-06-07T14:00:00 UTC = 10:00 EDT.
    result = vce.parse_datetime("today at 3pm", "2026-06-07T14:00:00+00:00")
    assert result is not None
    assert result.strftime("%Y-%m-%d") == "2026-06-07"


def test_missing_required_detects_missing_key() -> None:
    assert vce._missing_required({}) == "title"


def test_missing_required_passes_when_complete() -> None:
    block = {
        "title": "x",
        "start_natural": "today at 3pm",
        "source_inbox_path": "/tmp/x.md",
        "source_block_index": 0,
        "tick_iso": "2026-06-07T10:00:00-04:00",
    }
    assert vce._missing_required(block) is None


def test_missing_required_blank_string_fails() -> None:
    block = {
        "title": "x",
        "start_natural": "today at 3pm",
        "source_inbox_path": "   ",
        "source_block_index": 0,
        "tick_iso": "2026-06-07T10:00:00-04:00",
    }
    assert vce._missing_required(block) == "source_inbox_path"


def test_time_form_12_am_is_midnight() -> None:
    block = {
        "title": "Late night",
        "start_natural": "June 10, 2026 at 12 AM",
        "duration_natural": "30 minutes",
        "source_inbox_path": "/tmp/Inbox 2026-06-07 1000.md",
        "source_block_index": 0,
        "tick_iso": "2026-06-07T10:00:00-04:00",
    }
    result = vce.validate(block)
    assert result["complete"] is True
    assert result["calendar_event_payload"]["start_rfc3339"].startswith("2026-06-10T00:00:00")


def test_american_short_date_no_year_uses_anchor_year() -> None:
    """'6/15' (no year) anchors to the tick's year."""
    block = {
        "title": "Short-form",
        "start_natural": "6/15 at 9am",
        "duration_natural": "30 minutes",
        "source_inbox_path": "/tmp/Inbox 2026-06-07 1000.md",
        "source_block_index": 0,
        "tick_iso": "2026-06-07T10:00:00-04:00",
    }
    result = vce.validate(block)
    assert result["complete"] is True
    assert result["calendar_event_payload"]["start_rfc3339"].startswith("2026-06-15T09:00:00")


def test_bare_weekday_no_qualifier_resolves_to_upcoming() -> None:
    """'Friday' on its own (no 'this'/'next') still parses to upcoming Friday."""
    block = {
        "title": "Casual mention",
        "start_natural": "Friday at 5pm",
        "duration_natural": "1 hour",
        "source_inbox_path": "/tmp/Inbox 2026-06-07 1000.md",
        "source_block_index": 0,
        "tick_iso": "2026-06-07T10:00:00-04:00",
    }
    result = vce.validate(block)
    assert result["complete"] is True
    # 2026-06-07 is Sunday; Friday is 2026-06-12.
    assert result["calendar_event_payload"]["start_rfc3339"].startswith("2026-06-12T")


def test_recurrence_monthly_with_extra_substantive_token_rejected() -> None:
    assert vce.parse_recurrence("monthly on the 15th unless holiday") is None


def test_recurrence_weekly_with_extra_substantive_token_rejected() -> None:
    assert vce.parse_recurrence("every Tuesday until further notice") is None


def test_recurrence_biweekly_with_extra_substantive_token_rejected() -> None:
    assert vce.parse_recurrence("biweekly when the moon is full") is None


def test_american_date_with_invalid_month_falls_through() -> None:
    """13/40/2026 fails the bounds check; parser doesn't return early."""
    block = {
        "title": "Bogus date",
        "start_natural": "13/40/2026 at 2pm",
        "duration_natural": "30 minutes",
        "source_inbox_path": "/tmp/Inbox 2026-06-07 1000.md",
        "source_block_index": 0,
        "tick_iso": "2026-06-07T10:00:00-04:00",
    }
    # The phrase yields no other date hint and lands on today via fall-through?
    # In our implementation, when no date pattern matches we return None — so
    # start_datetime is missing. (The bad MM/DD/YYYY match should not produce
    # a fake date.)
    result = vce.validate(block)
    assert result["complete"] is False
    assert "start_datetime" in result["missing_fields"]


def test_month_name_with_invalid_day_falls_through() -> None:
    """'June 99, 2026' fails the bounds check."""
    block = {
        "title": "Bogus day",
        "start_natural": "June 99, 2026 at 2pm",
        "duration_natural": "30 minutes",
        "source_inbox_path": "/tmp/Inbox 2026-06-07 1000.md",
        "source_block_index": 0,
        "tick_iso": "2026-06-07T10:00:00-04:00",
    }
    result = vce.validate(block)
    assert result["complete"] is False
    assert "start_datetime" in result["missing_fields"]


def test_coerce_title_non_string_returns_none() -> None:
    """A non-string non-None title shouldn't crash; it should be unset."""
    block = {
        "title": 42,  # int, not str
        "start_natural": "today at 3pm",
        "duration_natural": "30 minutes",
        "source_inbox_path": "/tmp/Inbox 2026-06-07 1000.md",
        "source_block_index": 0,
        "tick_iso": "2026-06-07T10:00:00-04:00",
    }
    result = vce.validate(block)
    assert result["complete"] is False
    assert "title" in result["missing_fields"]


def test_missing_required_none_value_fails() -> None:
    block = {
        "title": None,
        "start_natural": "today at 3pm",
        "source_inbox_path": "/tmp/x.md",
        "source_block_index": 0,
        "tick_iso": "2026-06-07T10:00:00-04:00",
    }
    assert vce._missing_required(block) == "title"


# Keep the legacy subprocess-driven internal-error test for end-to-end parity.
def test_internal_error_path_exit_4(monkeypatch) -> None:
    """Force an unexpected exception inside validate() → exit 4."""

    def boom(_block: dict) -> dict:
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(vce, "validate", boom)
    proc = subprocess.run(
        [sys.executable, "-c",
         "import sys, json; "
         "sys.path.insert(0, %r); "
         "from scripts.calendar_routing import validate_calendar_event as v; "
         "v.validate = lambda b: (_ for _ in ()).throw(RuntimeError('boom')); "
         "sys.exit(v.main())" % str(REPO_ROOT)],
        input=json.dumps({"title": "x", "start_natural": "today at 3pm",
                          "source_inbox_path": "/tmp/x.md",
                          "source_block_index": 0,
                          "tick_iso": "2026-06-07T10:00:00-04:00"}),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 4
    assert "INTERNAL_ERROR" in proc.stderr
