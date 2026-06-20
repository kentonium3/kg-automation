"""Tests for the client-side filter in ``query_active_habits_v2``.

Updated for mission #519 WP02: the helper now reads from the Felix sync
cache (no Vikunja HTTP calls). All GET-path mock_urlopen fixtures have been
replaced with mock_sync_cache_fixture from tests/common/conftest.py.

These tests verify the same semantics as before — the Python-side filter
``done == False AND due_date <= <today>T23:59:59Z`` — but the data now comes
from the cache rather than live Vikunja.

See ``docs/design/research/vikunja-task-model-research.md`` G7 entry for
the original Vikunja v0.24.6 quirk that motivated the client-side approach.
"""
from __future__ import annotations

import pytest

from scripts.habits import query_active_habits_v2 as qv2


# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------

HABITS_PROJECT_ID = 13


def _task_fields(
    title: str = "Habit",
    done: bool = False,
    due_date: str = "2026-05-19T08:00:00Z",
    project_id: int = HABITS_PROJECT_ID,
) -> dict:
    return {
        "title": title,
        "done": done,
        "due_date": due_date,
        "project_id": project_id,
        "repeat_after": 86400,
        "repeat_mode": "default",
        "labels": [],
    }


# ---------------------------------------------------------------------------
# T003 — Five test cases for the client-side filter (research.md D4).
# ---------------------------------------------------------------------------


def test_happy_path_mixed_states(mock_sync_cache_fixture):
    """Mixed task states: only the active-today task survives the filter.

    Three tasks are in the cache:
      - id=1: done=True (excluded)
      - id=2: done=False AND due_date > today (excluded)
      - id=3: done=False AND due_date <= today (kept)
    """
    mock_sync_cache_fixture(
        tasks={
            1: _task_fields(title="Done already", done=True, due_date="2026-05-15T12:00:00Z"),
            2: _task_fields(title="Future", done=False, due_date="2026-05-25T12:00:00Z"),
            3: _task_fields(title="Active today", done=False, due_date="2026-05-19T08:00:00Z"),
        },
    )

    result = qv2.query_active_today(today="2026-05-19")

    assert len(result) == 1
    assert result[0]["id"] == 3


def test_all_done(mock_sync_cache_fixture):
    """All tasks have done=True: filter returns an empty list."""
    mock_sync_cache_fixture(
        tasks={
            1: _task_fields(title="Done A", done=True, due_date="2026-05-19T08:00:00Z"),
            2: _task_fields(title="Done B", done=True, due_date="2026-05-19T09:00:00Z"),
        },
    )

    result = qv2.query_active_today(today="2026-05-19")
    assert result == []


def test_all_future(mock_sync_cache_fixture):
    """All tasks have due_date > today: filter returns an empty list."""
    mock_sync_cache_fixture(
        tasks={
            1: _task_fields(title="Future A", done=False, due_date="2026-05-25T08:00:00Z"),
            2: _task_fields(title="Future B", done=False, due_date="2026-06-01T09:00:00Z"),
        },
    )

    result = qv2.query_active_today(today="2026-05-19")
    assert result == []


def test_boundary_inclusive(mock_sync_cache_fixture):
    """A task whose due_date EXACTLY equals the today-boundary is included.

    The boundary is ``<today>T23:59:59Z`` and the filter is ``<=``, so a
    task with exactly that timestamp survives.
    """
    mock_sync_cache_fixture(
        tasks={
            7: _task_fields(title="Right at the boundary", done=False, due_date="2026-05-19T23:59:59Z"),
        },
    )

    result = qv2.query_active_today(today="2026-05-19")

    assert len(result) == 1
    assert result[0]["id"] == 7


def test_end_of_day_et_due_date_included_on_its_own_day(mock_sync_cache_fixture):
    """Regression for #607: a habit due at end-of-day ET is included today.

    Vikunja stores due_dates in UTC. A habit due Friday 23:59:59 ET is
    stored as ``2026-06-20T03:59:59Z`` (the next UTC calendar day). The old
    lexicographic ``<today>T23:59:59Z`` boundary excluded it on Friday, so
    the Mon/Wed/Fri strength-training habits never appeared on their own
    day. The boundary is now a tz-aware end-of-day in America/New_York, so
    the task is correctly included.
    """
    mock_sync_cache_fixture(
        tasks={
            77: _task_fields(
                title="Strength training — Friday",
                done=False,
                due_date="2026-06-20T03:59:59Z",  # Fri 23:59:59 ET in UTC
            ),
        },
    )

    result = qv2.query_active_today(today="2026-06-19")  # Friday

    assert len(result) == 1
    assert result[0]["id"] == 77


def test_next_utc_day_but_still_today_et_is_included(mock_sync_cache_fixture):
    """A due_date just after UTC midnight but still 'today' in ET is kept.

    ``2026-06-20T02:00:00Z`` is 2026-06-19 22:00 ET — still Kent's Friday.
    The tz-aware boundary includes it; the old UTC-string compare dropped it.
    """
    mock_sync_cache_fixture(
        tasks={
            5: _task_fields(title="Late ET today", done=False, due_date="2026-06-20T02:00:00Z"),
        },
    )

    result = qv2.query_active_today(today="2026-06-19")

    assert len(result) == 1
    assert result[0]["id"] == 5


def test_unset_due_date_sentinel_still_included(mock_sync_cache_fixture):
    """Vikunja's unset-due-date sentinel (0001-01-01) remains INCLUDED.

    Confirms the tz-aware boundary preserves the prior behavior where a
    far-past sentinel passes the ``<= boundary`` filter.
    """
    mock_sync_cache_fixture(
        tasks={
            9: _task_fields(title="No due date", done=False, due_date="0001-01-01T00:00:00Z"),
        },
    )

    result = qv2.query_active_today(today="2026-06-19")

    assert len(result) == 1
    assert result[0]["id"] == 9


def test_genuinely_future_task_still_excluded(mock_sync_cache_fixture):
    """A task due a full day in the future (in ET) is still excluded.

    Guards against the boundary fix over-including: Saturday's task must not
    leak into Friday's list.
    """
    mock_sync_cache_fixture(
        tasks={
            8: _task_fields(title="Tomorrow ET", done=False, due_date="2026-06-21T03:59:59Z"),
        },
    )

    result = qv2.query_active_today(today="2026-06-19")

    assert result == []


def test_cache_missing_propagates_oserror(tmp_path, monkeypatch):
    """A missing cache surfaces as OSError (replaces the old HTTP 400 test).

    After the cache migration there is no HTTP path to raise on. The
    equivalent failure mode is a missing or stale cache.
    """
    monkeypatch.setattr("scripts.common.sync_cache.STATE_DIR_DEFAULT", tmp_path / "empty")
    monkeypatch.setattr("scripts.sync.state.STATE_DIR_DEFAULT", tmp_path / "empty")

    with pytest.raises(OSError):
        qv2.query_active_today(today="2026-05-19")
