"""Tests for scripts/sync/fetch.py (WP03 / T009).

Full-poll semantics + FR-012 abort cases. All HTTP calls are mocked via
urllib.request.urlopen; no live network. Each test asserts exact call counts
to catch accidental extra (or missing) requests.

10 scenarios per WP03 T009 spec.
"""
from __future__ import annotations

import io
import json
import urllib.error
from unittest.mock import MagicMock, call, patch

import pytest

from scripts.sync import fetch as f
from scripts.sync.fetch import FetchedSnapshot


# ---------------------------------------------------------------------------
# Mocking helpers
# ---------------------------------------------------------------------------


def _resp(payload, *, status: int = 200):
    """Build a mock urlopen context-manager response."""
    body = json.dumps(payload).encode("utf-8") if payload is not None else b""
    resp = MagicMock(name="response")
    resp.status = status
    resp.read = MagicMock(return_value=body)
    cm = MagicMock(name="cm")
    cm.__enter__ = MagicMock(return_value=resp)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


def _http_error(code: int = 500, body: bytes = b'{"message":"boom"}'):
    return urllib.error.HTTPError(
        url="http://test/",
        code=code,
        msg="Server Error",
        hdrs=None,
        fp=io.BytesIO(body),
    )


@pytest.fixture
def mock_urlopen(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr("scripts.sync.http.urllib.request.urlopen", mock)
    return mock


BASE = "http://test/api/v1/"
TOKEN = "test-token"

TASKS_PAYLOAD = [
    {"id": 1, "title": "Task A", "project_id": 10, "done": False, "updated": "2026-06-04T18:00:00Z"},
    {"id": 2, "title": "Task B", "project_id": 10, "done": True, "updated": "2026-06-04T19:00:00Z"},
]
PROJECTS_PAYLOAD = [
    {"id": 10, "title": "Project Alpha", "is_archived": False},
    {"id": 11, "title": "Project Beta", "is_archived": True},
]


# ===========================================================================
# Scenario 1 — Happy path: two HTTP calls, populated FetchedSnapshot
# ===========================================================================


class TestHappyPath:
    def test_returns_fetched_snapshot_with_tasks_and_projects(self, mock_urlopen):
        mock_urlopen.side_effect = [
            _resp(TASKS_PAYLOAD),
            _resp(PROJECTS_PAYLOAD),
            _resp({"version": "0.24.6"}),
        ]
        snap = f.fetch_full_poll(TOKEN, BASE)

        assert isinstance(snap, FetchedSnapshot)
        assert len(snap.tasks) == 2
        assert snap.tasks[0]["id"] == 1
        assert snap.tasks[1]["id"] == 2
        assert 10 in snap.projects
        assert 11 in snap.projects
        assert snap.projects[10]["title"] == "Project Alpha"
        assert snap.vikunja_version == "0.24.6"
        assert snap.fetched_at_utc.endswith("Z")

    def test_exactly_three_calls_tasks_projects_info(self, mock_urlopen):
        """Happy path makes exactly 3 calls: tasks, projects, info."""
        mock_urlopen.side_effect = [
            _resp(TASKS_PAYLOAD),
            _resp(PROJECTS_PAYLOAD),
            _resp({"version": "0.24.6"}),
        ]
        f.fetch_full_poll(TOKEN, BASE)
        assert mock_urlopen.call_count == 3


# ===========================================================================
# Scenario 2 — No updated_since in task URL
# ===========================================================================


class TestNoUpdatedSince:
    def test_tasks_url_has_no_query_string(self, mock_urlopen):
        mock_urlopen.side_effect = [
            _resp(TASKS_PAYLOAD),
            _resp(PROJECTS_PAYLOAD),
            _resp({"version": "0.24.6"}),
        ]
        f.fetch_full_poll(TOKEN, BASE)
        tasks_req = mock_urlopen.call_args_list[0][0][0]
        assert tasks_req.full_url == BASE + "tasks/all"
        assert "updated_since" not in tasks_req.full_url
        assert "?" not in tasks_req.full_url


# ===========================================================================
# Scenario 3 — No just-in-time per-project fetch
# ===========================================================================


class TestNoJitProjectFetch:
    def test_unknown_project_id_in_task_does_not_trigger_extra_fetch(self, mock_urlopen):
        """Even if a task references a project not in the projects response,
        no per-project GET is made. The snapshot's projects dict is the source
        of truth.
        """
        tasks_with_unknown_project = [
            {"id": 5, "title": "Task", "project_id": 999, "done": False, "updated": "2026-06-04T18:00:00Z"},
        ]
        mock_urlopen.side_effect = [
            _resp(tasks_with_unknown_project),
            _resp(PROJECTS_PAYLOAD),  # project 999 is NOT in this list
            _resp({"version": "0.24.6"}),
        ]
        snap = f.fetch_full_poll(TOKEN, BASE)

        # Exactly 3 calls: tasks, projects, info. No extra GET for project 999.
        assert mock_urlopen.call_count == 3
        # Project 999 is not in the snapshot (not in GET /projects response).
        assert 999 not in snap.projects
        assert len(snap.tasks) == 1


# ===========================================================================
# Scenario 4 — FR-012: auth_failure (401)
# ===========================================================================


class TestFR012AuthFailure:
    def test_401_raises_auth_failure_oserror(self, mock_urlopen):
        mock_urlopen.side_effect = _http_error(401, b'{"message":"unauthorized"}')
        with pytest.raises(OSError, match=r"^auth_failure:"):
            f.fetch_full_poll(TOKEN, BASE)

    def test_403_raises_auth_failure_oserror(self, mock_urlopen):
        mock_urlopen.side_effect = _http_error(403, b'{"message":"forbidden"}')
        with pytest.raises(OSError, match=r"^auth_failure:"):
            f.fetch_full_poll(TOKEN, BASE)


# ===========================================================================
# Scenario 5 — FR-012: vikunja_5xx (503)
# ===========================================================================


class TestFR012Vikunja5xx:
    def test_503_raises_vikunja_5xx_oserror(self, mock_urlopen):
        mock_urlopen.side_effect = _http_error(503, b'{"message":"service unavailable"}')
        with pytest.raises(OSError, match=r"^vikunja_5xx:"):
            f.fetch_full_poll(TOKEN, BASE)

    def test_500_raises_vikunja_5xx_oserror(self, mock_urlopen):
        mock_urlopen.side_effect = _http_error(500, b'{"message":"internal error"}')
        with pytest.raises(OSError, match=r"^vikunja_5xx:"):
            f.fetch_full_poll(TOKEN, BASE)


# ===========================================================================
# Scenario 6 — FR-012: parse_error (non-list body)
# ===========================================================================


class TestFR012ParseError:
    def test_non_json_tasks_body_raises_parse_error(self, mock_urlopen):
        """Non-list response from /tasks/all raises parse_error."""
        mock_urlopen.side_effect = [
            _resp({"unexpected": "dict"}),  # not a list
        ]
        with pytest.raises(OSError, match=r"^parse_error:"):
            f.fetch_full_poll(TOKEN, BASE)

    def test_non_list_projects_body_raises_parse_error(self, mock_urlopen):
        """Non-list response from /projects raises parse_error."""
        mock_urlopen.side_effect = [
            _resp(TASKS_PAYLOAD),
            _resp({"unexpected": "dict"}),  # not a list
        ]
        with pytest.raises(OSError, match=r"^parse_error:"):
            f.fetch_full_poll(TOKEN, BASE)


# ===========================================================================
# Scenario 7 — FR-012: empty_response_when_cache_nonzero (tasks)
# ===========================================================================


class TestFR012EmptyResponseWhenCacheNonzero:
    def test_empty_tasks_with_nonempty_cache_raises(self, mock_urlopen):
        mock_urlopen.side_effect = [
            _resp([]),  # empty task list
        ]
        with pytest.raises(OSError, match=r"^empty_response_when_cache_nonzero:"):
            f.fetch_full_poll(TOKEN, BASE, task_cache_nonempty=True)

    def test_empty_projects_with_nonempty_cache_raises(self, mock_urlopen):
        mock_urlopen.side_effect = [
            _resp(TASKS_PAYLOAD),
            _resp([]),  # empty projects list
        ]
        with pytest.raises(OSError, match=r"^empty_response_when_cache_nonzero:"):
            f.fetch_full_poll(TOKEN, BASE, project_cache_nonempty=True)


# ===========================================================================
# Scenario 8 — Empty response allowed when cache is empty
# ===========================================================================


class TestEmptyResponseAllowedWhenCacheEmpty:
    def test_empty_tasks_with_empty_cache_succeeds(self, mock_urlopen):
        mock_urlopen.side_effect = [
            _resp([]),
            _resp([]),
            _resp({"version": "0.24.6"}),
        ]
        snap = f.fetch_full_poll(TOKEN, BASE, task_cache_nonempty=False)
        assert snap.tasks == ()
        assert snap.projects == {}

    def test_empty_projects_with_empty_cache_succeeds(self, mock_urlopen):
        mock_urlopen.side_effect = [
            _resp(TASKS_PAYLOAD),
            _resp([]),
            _resp({"version": "0.24.6"}),
        ]
        snap = f.fetch_full_poll(TOKEN, BASE, project_cache_nonempty=False)
        assert snap.projects == {}
        assert len(snap.tasks) == 2


# ===========================================================================
# Scenario 9 — /info failure does NOT abort
# ===========================================================================


class TestInfoFailureDoesNotAbort:
    def test_info_404_yields_none_version(self, mock_urlopen):
        mock_urlopen.side_effect = [
            _resp(TASKS_PAYLOAD),
            _resp(PROJECTS_PAYLOAD),
            _http_error(404, b'{"message":"no info endpoint"}'),
        ]
        snap = f.fetch_full_poll(TOKEN, BASE)
        assert snap.vikunja_version is None
        # tasks and projects still populated
        assert len(snap.tasks) == 2
        assert len(snap.projects) == 2

    def test_info_network_error_yields_none_version(self, mock_urlopen):
        mock_urlopen.side_effect = [
            _resp(TASKS_PAYLOAD),
            _resp(PROJECTS_PAYLOAD),
            urllib.error.URLError("network unreachable"),
        ]
        snap = f.fetch_full_poll(TOKEN, BASE)
        assert snap.vikunja_version is None


# ===========================================================================
# Scenario 10 — Strict call sequence: tasks failure stops projects call
# ===========================================================================


class TestStrictCallSequence:
    def test_tasks_failure_does_not_attempt_projects_fetch(self, mock_urlopen):
        mock_urlopen.side_effect = _http_error(503, b'{"message":"down"}')
        with pytest.raises(OSError, match=r"^vikunja_5xx:"):
            f.fetch_full_poll(TOKEN, BASE)
        # Only 1 call was made (tasks), not 2.
        assert mock_urlopen.call_count == 1

    def test_projects_url_is_fetched_after_tasks(self, mock_urlopen):
        mock_urlopen.side_effect = [
            _resp(TASKS_PAYLOAD),
            _resp(PROJECTS_PAYLOAD),
            _resp({"version": "0.24.6"}),
        ]
        f.fetch_full_poll(TOKEN, BASE)
        tasks_req = mock_urlopen.call_args_list[0][0][0]
        projects_req = mock_urlopen.call_args_list[1][0][0]
        assert "tasks/all" in tasks_req.full_url
        assert "projects" in projects_req.full_url
