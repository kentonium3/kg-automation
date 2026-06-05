# ARCHIVED 2026-06-05 — v1 script and tests superseded by v2 (mission #520 / issue #526).
"""Tests for scripts/habits/query_active_habits.py (FR-002).

Verifies the contract in
kitty-specs/habits-checkin-d6-extract-01KRNV46/contracts/query_active_habits.md.

Mocks urllib.request.urlopen so no real Vikunja calls happen during tests.
"""
from __future__ import annotations

import io
import json
from unittest.mock import MagicMock, patch

import pytest

# scripts/habits/ is on sys.path via conftest.py
import query_active_habits as qah  # type: ignore  # noqa: E402


def _mock_response(payload):
    """Return a context-manager-compatible mock that produces the given JSON payload."""
    mock = MagicMock()
    mock.__enter__ = MagicMock(return_value=MagicMock(read=MagicMock(
        return_value=json.dumps(payload).encode("utf-8")
    )))
    mock.__exit__ = MagicMock(return_value=False)
    return mock


def _patch_urlopen(responses_by_path):
    """Patch urllib.request.urlopen to return scripted responses by URL path.

    `responses_by_path` is {path_substring: payload}. The mock matches by checking
    if a substring of the URL contains the key.
    """
    def side_effect(req, timeout=15):  # noqa: ARG001
        url = req.full_url if hasattr(req, "full_url") else str(req)
        for path_substr, payload in responses_by_path.items():
            if path_substr in url:
                return _mock_response(payload)
        raise AssertionError(f"Unexpected URL: {url}")
    return patch.object(qah.urllib.request, "urlopen", side_effect=side_effect)


def _fake_token_file(tmp_path):
    """Write a fake Vikunja token to a tempfile; return the path."""
    p = tmp_path / "vikunja-token"
    p.write_text("fake-token-for-tests\n")
    return p


# ---------- Helpers (parse_frequency unit tests) ----------


def test_parse_frequency_empty_description_is_daily():
    """Production convention: empty/whitespace-only description means daily.

    All current habits (id 14-20, 65 as of 2026-05-15) have empty descriptions
    and were always treated as daily by the prior Sonnet agent. The helper
    encodes this implicitly so empty-description habits show up every day.
    """
    days, paused = qah.parse_frequency("")
    assert days == qah.ALL_DAYS
    assert paused is False
    # Whitespace-only also counts as empty
    days, _ = qah.parse_frequency("   ")
    assert days == qah.ALL_DAYS


def test_parse_frequency_daily():
    days, paused = qah.parse_frequency("Daily")
    assert days == qah.ALL_DAYS
    assert paused is False


def test_parse_frequency_daily_evening():
    days, paused = qah.parse_frequency("Daily (evening)")
    assert days == qah.ALL_DAYS
    assert paused is False


def test_parse_frequency_mon_sat_ascii():
    days, paused = qah.parse_frequency("Mon-Sat")
    assert "Sun" not in days
    assert "Mon" in days and "Sat" in days
    assert paused is False


def test_parse_frequency_mon_sat_en_dash():
    days, paused = qah.parse_frequency("Mon–Sat")  # en-dash
    assert "Sun" not in days
    assert "Mon" in days and "Sat" in days


def test_parse_frequency_paused_detected():
    days, paused = qah.parse_frequency("(PAUSED) Daily")
    assert paused is True
    # We still report the frequency; main flow excludes paused regardless
    assert days == qah.ALL_DAYS


def test_parse_frequency_unrecognized_returns_none():
    days, paused = qah.parse_frequency("Twice weekly")
    assert days is None
    assert paused is False


# ---------- End-to-end tests (main()) ----------


def test_daily_all_seven_days(tmp_path, capsys):
    token = _fake_token_file(tmp_path)
    projects = [{"id": 5, "title": "Habits"}]
    tasks = [{"id": 100, "title": "Meditate", "description": "Daily", "done": False, "due_date": None}]
    with _patch_urlopen({"/projects/5/tasks": tasks, "/projects": projects}):
        for day in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]:
            rc = qah.main([
                "--day", day,
                "--vikunja-token-path", str(token),
                "--vikunja-base-url", "http://test",
            ])
            assert rc == 0
    out = capsys.readouterr().out
    # Last call's output should still show the daily habit (Sun is the last iteration)
    assert "Meditate" in out


def test_mon_sat_excludes_sunday(tmp_path, capsys):
    token = _fake_token_file(tmp_path)
    projects = [{"id": 5, "title": "Habits"}]
    tasks = [{"id": 101, "title": "Lift", "description": "Mon-Sat", "done": False}]
    with _patch_urlopen({"/projects/5/tasks": tasks, "/projects": projects}):
        rc_sat = qah.main(["--day", "Sat", "--vikunja-token-path", str(token), "--vikunja-base-url", "http://test"])
        capsys.readouterr()
        rc_sun = qah.main(["--day", "Sun", "--vikunja-token-path", str(token), "--vikunja-base-url", "http://test"])
        sun_out = capsys.readouterr().out
    assert rc_sat == 0
    assert rc_sun == 0
    payload = json.loads(sun_out.splitlines()[0])
    assert payload["scheduled_today"] == 0
    assert payload["habits"] == []


def test_mon_wed_fri_only_three_days(tmp_path, capsys):
    token = _fake_token_file(tmp_path)
    projects = [{"id": 5, "title": "Habits"}]
    tasks = [{"id": 102, "title": "Cardio", "description": "Mon/Wed/Fri", "done": False}]
    with _patch_urlopen({"/projects/5/tasks": tasks, "/projects": projects}):
        for day, expected in [("Mon", 1), ("Tue", 0), ("Wed", 1), ("Thu", 0), ("Fri", 1), ("Sat", 0), ("Sun", 0)]:
            rc = qah.main(["--day", day, "--vikunja-token-path", str(token), "--vikunja-base-url", "http://test"])
            out = capsys.readouterr().out
            assert rc == 0
            payload = json.loads(out.splitlines()[0])
            assert payload["scheduled_today"] == expected, f"day={day}"


def test_paused_excluded(tmp_path, capsys):
    token = _fake_token_file(tmp_path)
    projects = [{"id": 5, "title": "Habits"}]
    tasks = [
        {"id": 110, "title": "Active", "description": "Daily", "done": False},
        {"id": 111, "title": "Paused habit", "description": "(PAUSED) Daily", "done": False},
    ]
    with _patch_urlopen({"/projects/5/tasks": tasks, "/projects": projects}):
        rc = qah.main(["--day", "Mon", "--vikunja-token-path", str(token), "--vikunja-base-url", "http://test"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out.splitlines()[0])
    assert payload["scheduled_today"] == 1
    assert payload["habits"][0]["id"] == 110


def test_done_excluded(tmp_path, capsys):
    token = _fake_token_file(tmp_path)
    projects = [{"id": 5, "title": "Habits"}]
    tasks = [
        {"id": 120, "title": "Active", "description": "Daily", "done": False},
        {"id": 121, "title": "Completed habit", "description": "Daily", "done": True},
    ]
    with _patch_urlopen({"/projects/5/tasks": tasks, "/projects": projects}):
        rc = qah.main(["--day", "Mon", "--vikunja-token-path", str(token), "--vikunja-base-url", "http://test"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out.splitlines()[0])
    assert payload["scheduled_today"] == 1


def test_unrecognized_freq_skipped_with_warning(tmp_path, capsys):
    token = _fake_token_file(tmp_path)
    projects = [{"id": 5, "title": "Habits"}]
    tasks = [{"id": 130, "title": "Odd one", "description": "Twice weekly", "done": False}]
    with _patch_urlopen({"/projects/5/tasks": tasks, "/projects": projects}):
        rc = qah.main(["--day", "Mon", "--vikunja-token-path", str(token), "--vikunja-base-url", "http://test"])
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out.splitlines()[0])
    assert payload["scheduled_today"] == 0
    assert "WARN" in captured.err
    assert "unrecognized frequency" in captured.err


def test_empty_project(tmp_path, capsys):
    token = _fake_token_file(tmp_path)
    projects = [{"id": 5, "title": "Habits"}]
    tasks: list[dict] = []
    with _patch_urlopen({"/projects/5/tasks": tasks, "/projects": projects}):
        rc = qah.main(["--day", "Mon", "--vikunja-token-path", str(token), "--vikunja-base-url", "http://test"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out.splitlines()[0])
    assert payload["habits"] == []
    assert payload["total_in_project"] == 0
    assert payload["scheduled_today"] == 0


def test_vikunja_unreachable(tmp_path, capsys):
    token = _fake_token_file(tmp_path)
    import urllib.error
    with patch.object(qah.urllib.request, "urlopen", side_effect=urllib.error.URLError("connection refused")):
        rc = qah.main(["--day", "Mon", "--vikunja-token-path", str(token), "--vikunja-base-url", "http://test"])
    captured = capsys.readouterr()
    assert rc == 1
    assert "ERROR" in captured.err
    assert "unreachable" in captured.err.lower() or "URLError" in captured.err or "Vikunja" in captured.err


def test_invalid_day_arg(tmp_path, capsys):
    token = _fake_token_file(tmp_path)
    rc = qah.main(["--day", "Funday", "--vikunja-token-path", str(token), "--vikunja-base-url", "http://test"])
    captured = capsys.readouterr()
    assert rc == 2
    assert "ERROR" in captured.err
