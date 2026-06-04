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


def test_cache_missing_propagates_oserror(tmp_path, monkeypatch):
    """A missing cache surfaces as OSError (replaces the old HTTP 400 test).

    After the cache migration there is no HTTP path to raise on. The
    equivalent failure mode is a missing or stale cache.
    """
    monkeypatch.setattr("scripts.common.sync_cache.STATE_DIR_DEFAULT", tmp_path / "empty")
    monkeypatch.setattr("scripts.sync.state.STATE_DIR_DEFAULT", tmp_path / "empty")

    with pytest.raises(OSError):
        qv2.query_active_today(today="2026-05-19")
