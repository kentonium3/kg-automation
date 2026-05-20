"""Tests for the client-side filter in ``query_active_habits_v2``.

These tests exercise the G7 (#336) fix — the helper now enumerates
``GET /projects/<id>/tasks`` (no server-side ``?filter=`` param) and
applies the equivalent ``done == False AND due_date <= <today>T23:59:59Z``
filter in Python.

See ``docs/design/research/vikunja-task-model-research.md`` G7 entry for
the underlying Vikunja v0.24.6 quirk, and
``kitty-specs/vikunja-g7-query-filter-fix-01KS1K1Y/research.md`` D4 for
the test strategy.

The mock approach mirrors ``test_query_active_habits_v2.py``: the
``mock_urlopen`` conftest fixture monkey-patches
``urllib.request.urlopen``; each test scripts the two-call sequence
(``GET /projects`` then ``GET /projects/<id>/tasks``) via
``side_effect``.
"""
from __future__ import annotations

import json
import urllib.error
from unittest.mock import MagicMock

import pytest

from scripts.habits import query_active_habits_v2 as qv2


# ---------------------------------------------------------------------------
# Local mocking helpers (copied from test_query_active_habits_v2.py for
# clarity — keeping this file self-contained so a reader doesn't need to
# cross-reference the broader test suite to understand the fixtures).
# ---------------------------------------------------------------------------


HABITS_PROJECT_ID = 13


def _resp(payload, *, status: int = 200):
    """Return a context-manager-compatible mock urlopen response."""
    body = json.dumps(payload).encode("utf-8") if payload is not None else b""
    resp = MagicMock(name="response")
    resp.status = status
    resp.read = MagicMock(return_value=body)
    cm = MagicMock(name="cm")
    cm.__enter__ = MagicMock(return_value=resp)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


def _projects_payload(project_id: int = HABITS_PROJECT_ID):
    return [
        {"id": 1, "title": "Inbox"},
        {"id": project_id, "title": "Habits"},
        {"id": 99, "title": "Goals"},
    ]


def _responses(tasks, *, projects=None):
    """Build urlopen responses scripting (projects -> tasks)."""
    if projects is None:
        projects = _projects_payload()
    return [_resp(projects), _resp(tasks)]


# ---------------------------------------------------------------------------
# T003 — Five test cases for the client-side filter (research.md D4).
# ---------------------------------------------------------------------------


def test_happy_path_mixed_states(mock_urlopen):
    """Mixed task states: only the active-today task survives the filter.

    Three tasks are returned by Vikunja:
      - id=1: done=True (excluded)
      - id=2: done=False AND due_date > today (excluded)
      - id=3: done=False AND due_date <= today (kept)
    """
    payload = [
        {
            "id": 1,
            "title": "Done already",
            "done": True,
            "due_date": "2026-05-15T12:00:00Z",
        },
        {
            "id": 2,
            "title": "Future",
            "done": False,
            "due_date": "2026-05-25T12:00:00Z",
        },
        {
            "id": 3,
            "title": "Active today",
            "done": False,
            "due_date": "2026-05-19T08:00:00Z",
        },
    ]
    mock_urlopen.side_effect = _responses(tasks=payload)

    result = qv2.query_active_today(
        api_base_url="http://test/api/v1/",
        token="t",
        today="2026-05-19",
    )

    assert len(result) == 1
    assert result[0]["id"] == 3


def test_all_done(mock_urlopen):
    """All tasks have done=True: filter returns an empty list."""
    payload = [
        {"id": 1, "title": "Done A", "done": True, "due_date": "2026-05-19T08:00:00Z"},
        {"id": 2, "title": "Done B", "done": True, "due_date": "2026-05-19T09:00:00Z"},
    ]
    mock_urlopen.side_effect = _responses(tasks=payload)

    result = qv2.query_active_today(
        api_base_url="http://test/api/v1/",
        token="t",
        today="2026-05-19",
    )

    assert result == []


def test_all_future(mock_urlopen):
    """All tasks have due_date > today: filter returns an empty list."""
    payload = [
        {"id": 1, "title": "Future A", "done": False, "due_date": "2026-05-25T08:00:00Z"},
        {"id": 2, "title": "Future B", "done": False, "due_date": "2026-06-01T09:00:00Z"},
    ]
    mock_urlopen.side_effect = _responses(tasks=payload)

    result = qv2.query_active_today(
        api_base_url="http://test/api/v1/",
        token="t",
        today="2026-05-19",
    )

    assert result == []


def test_boundary_inclusive(mock_urlopen):
    """A task whose due_date EXACTLY equals the today-boundary is included.

    The boundary is ``<today>T23:59:59Z`` and the filter is ``<=``, so a
    task with exactly that timestamp survives.
    """
    payload = [
        {
            "id": 7,
            "title": "Right at the boundary",
            "done": False,
            "due_date": "2026-05-19T23:59:59Z",
        },
    ]
    mock_urlopen.side_effect = _responses(tasks=payload)

    result = qv2.query_active_today(
        api_base_url="http://test/api/v1/",
        token="t",
        today="2026-05-19",
    )

    assert len(result) == 1
    assert result[0]["id"] == 7


def test_http_400_propagates(mock_urlopen):
    """An HTTP 400 from the new (no-filter) URL surfaces as OSError.

    Existing behavior is preserved: ``_http_get`` raises ``OSError`` on
    any non-2xx HTTP response, and ``query_active_today`` propagates it
    unchanged. The CLI converts this to exit code 1.
    """
    err = urllib.error.HTTPError(
        url="http://test/api/v1/projects/13/tasks",
        code=400,
        msg="Bad Request",
        hdrs=None,
        fp=None,
    )
    # First call (GET /projects) succeeds; second call (GET /projects/<id>/tasks)
    # raises 400.
    mock_urlopen.side_effect = [
        _resp(_projects_payload()),
        err,
    ]

    with pytest.raises(OSError):
        qv2.query_active_today(
            api_base_url="http://test/api/v1/",
            token="t",
            today="2026-05-19",
        )
