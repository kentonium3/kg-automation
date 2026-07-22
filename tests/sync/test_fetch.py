"""Tests for scripts/sync/fetch.py (WP03 / T009).

Full-poll semantics + FR-012 abort cases. All HTTP calls are mocked via
urllib.request.urlopen; no live network. Each test asserts exact call counts
to catch accidental extra (or missing) requests.

Task enumeration is **project-scoped** (the v1 ``GET /tasks/all`` endpoint
returns HTTP 400 code 2004 on Vikunja 2.4.0+, see #853): the fetch calls
``GET /projects`` FIRST, then pages ``GET /projects/{id}/tasks`` per project,
then ``GET /info``.
"""
from __future__ import annotations

import io
import json
import urllib.error
from unittest.mock import MagicMock

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


def _urls(mock_urlopen) -> list[str]:
    """Full URLs of every Request passed to urlopen, in call order."""
    return [c[0][0].full_url for c in mock_urlopen.call_args_list]


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


def _task(tid: int, project_id: int = 10) -> dict:
    return {
        "id": tid,
        "title": f"Task {tid}",
        "project_id": project_id,
        "done": False,
        "updated": "2026-06-04T18:00:00Z",
    }


# ===========================================================================
# Scenario 1 — Happy path: projects → per-project tasks → info
# ===========================================================================


class TestHappyPath:
    def test_returns_fetched_snapshot_with_tasks_and_projects(self, mock_urlopen):
        mock_urlopen.side_effect = [
            _resp(PROJECTS_PAYLOAD),   # 1. projects (fetched FIRST)
            _resp(TASKS_PAYLOAD),      # 2. projects/10/tasks (2 tasks, short → stop)
            _resp([]),                 # 3. projects/11/tasks (empty → stop)
            _resp({"version": "0.24.6"}),  # 4. info
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

    def test_call_sequence_projects_then_per_project_tasks_then_info(self, mock_urlopen):
        """Happy path (2 projects): projects, tasks/10, tasks/11, info = 4 calls."""
        mock_urlopen.side_effect = [
            _resp(PROJECTS_PAYLOAD),
            _resp(TASKS_PAYLOAD),
            _resp([]),
            _resp({"version": "0.24.6"}),
        ]
        f.fetch_full_poll(TOKEN, BASE)
        urls = _urls(mock_urlopen)
        assert mock_urlopen.call_count == 4
        assert urls[0].endswith("projects")
        assert "projects/10/tasks" in urls[1]
        assert "projects/11/tasks" in urls[2]
        assert urls[3].endswith("info")


# ===========================================================================
# Scenario 2 — No updated_since in the (full-poll) task URL
# ===========================================================================


class TestNoUpdatedSince:
    def test_task_url_has_no_updated_since(self, mock_urlopen):
        """Full-poll task URLs are project-scoped with page/per_page only — no
        updated_since incremental marker."""
        mock_urlopen.side_effect = [
            _resp(PROJECTS_PAYLOAD),
            _resp(TASKS_PAYLOAD),
            _resp([]),
            _resp({"version": "0.24.6"}),
        ]
        f.fetch_full_poll(TOKEN, BASE)
        # call[1] is the first per-project task fetch (projects/10/tasks).
        task_url = mock_urlopen.call_args_list[1][0][0].full_url
        assert task_url.startswith(BASE + "projects/10/tasks?")
        assert "updated_since" not in task_url
        assert "page=1" in task_url
        assert "per_page=50" in task_url


# ===========================================================================
# Scenario 2.5 — Per-project pagination across the 50-task Vikunja cap
# ===========================================================================


class TestPagination:
    def test_full_page_triggers_next_page_fetch(self, mock_urlopen):
        """A full 50-task page triggers a page=2 fetch; a partial page stops."""
        full_page = [_task(i) for i in range(1, 51)]      # 50 → full
        partial_page = [_task(i) for i in range(51, 70)]  # 19 → partial, stops
        mock_urlopen.side_effect = [
            _resp([{"id": 10, "title": "Alpha"}]),  # projects (single project 10)
            _resp(full_page),                       # projects/10/tasks page 1
            _resp(partial_page),                    # projects/10/tasks page 2
            _resp({"version": "0.24.6"}),           # info
        ]
        snap = f.fetch_full_poll(TOKEN, BASE)

        assert len(snap.tasks) == 69
        # 4 total: projects + 2 task pages + info.
        assert mock_urlopen.call_count == 4
        urls = _urls(mock_urlopen)
        assert "projects/10/tasks?page=1" in urls[1]
        assert "projects/10/tasks?page=2" in urls[2]

    def test_empty_page_terminates_pagination(self, mock_urlopen):
        """An exactly-full page followed by an empty page stops cleanly."""
        full_page = [_task(i) for i in range(1, 51)]  # exactly 50
        mock_urlopen.side_effect = [
            _resp([{"id": 10, "title": "Alpha"}]),  # projects
            _resp(full_page),                       # page 1 (exactly 50)
            _resp([]),                              # page 2 empty → stop
            _resp({"version": "0.24.6"}),           # info
        ]
        snap = f.fetch_full_poll(TOKEN, BASE)
        assert len(snap.tasks) == 50
        assert mock_urlopen.call_count == 4

    def test_tasks_deduplicated_by_id(self, mock_urlopen):
        """A task id appearing in two per-project pages is kept once."""
        page1 = [_task(i) for i in range(1, 51)]           # 50 → full
        page2 = [_task(1), _task(51)]                       # 1 is a dup of page1
        mock_urlopen.side_effect = [
            _resp([{"id": 10, "title": "Alpha"}]),
            _resp(page1),
            _resp(page2),
            _resp({"version": "0.24.6"}),
        ]
        snap = f.fetch_full_poll(TOKEN, BASE)
        ids = [t["id"] for t in snap.tasks]
        assert len(ids) == len(set(ids))
        assert len(snap.tasks) == 51  # 50 + one new (51); dup id 1 dropped

    def test_multiple_projects_are_each_enumerated(self, mock_urlopen):
        """Each project id from GET /projects gets its own task fetch."""
        mock_urlopen.side_effect = [
            _resp([{"id": 10, "title": "A"}, {"id": 11, "title": "B"}]),
            _resp([_task(1, 10)]),  # projects/10/tasks
            _resp([_task(2, 11)]),  # projects/11/tasks
            _resp({"version": "0.24.6"}),
        ]
        snap = f.fetch_full_poll(TOKEN, BASE)
        assert {t["id"] for t in snap.tasks} == {1, 2}
        urls = _urls(mock_urlopen)
        assert "projects/10/tasks" in urls[1]
        assert "projects/11/tasks" in urls[2]


# ===========================================================================
# Scenario 3 — No fetch for a project id that GET /projects did not return
# ===========================================================================


class TestNoUnknownProjectFetch:
    def test_task_project_id_not_in_projects_triggers_no_extra_fetch(self, mock_urlopen):
        """A task whose project_id is not among the enumerated projects does NOT
        trigger a per-project GET. The enumerated projects are the source of
        truth for which per-project task endpoints are hit."""
        mock_urlopen.side_effect = [
            _resp([{"id": 10, "title": "Alpha"}]),      # only project 10
            _resp([_task(5, project_id=999)]),          # projects/10/tasks
            _resp({"version": "0.24.6"}),               # info
        ]
        snap = f.fetch_full_poll(TOKEN, BASE)

        # Exactly 3 calls: projects, projects/10/tasks, info. No fetch for 999.
        assert mock_urlopen.call_count == 3
        assert 999 not in snap.projects
        assert len(snap.tasks) == 1


# ===========================================================================
# Scenario 4 — FR-012: auth_failure (401 / 403)
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
# Scenario 5 — FR-012: vikunja_5xx (500 / 503)
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
    def test_non_list_projects_body_raises_parse_error(self, mock_urlopen):
        """Non-list response from /projects (the FIRST call) raises parse_error."""
        mock_urlopen.side_effect = [
            _resp({"unexpected": "dict"}),  # not a list
        ]
        with pytest.raises(OSError, match=r"^parse_error:"):
            f.fetch_full_poll(TOKEN, BASE)

    def test_non_list_tasks_body_raises_parse_error(self, mock_urlopen):
        """Non-list response from a per-project task fetch raises parse_error."""
        mock_urlopen.side_effect = [
            _resp([{"id": 10, "title": "Alpha"}]),  # projects OK
            _resp({"unexpected": "dict"}),          # projects/10/tasks not a list
        ]
        with pytest.raises(OSError, match=r"^parse_error:"):
            f.fetch_full_poll(TOKEN, BASE)


# ===========================================================================
# Scenario 7 — FR-012: empty_response_when_cache_nonzero
# ===========================================================================


class TestFR012EmptyResponseWhenCacheNonzero:
    def test_empty_tasks_with_nonempty_cache_raises(self, mock_urlopen):
        """Projects present but every project empty of tasks, while the task
        cache is non-empty → abort (possible data loss)."""
        mock_urlopen.side_effect = [
            _resp([{"id": 10, "title": "Alpha"}]),  # projects
            _resp([]),                              # projects/10/tasks empty
        ]
        with pytest.raises(OSError, match=r"^empty_response_when_cache_nonzero:"):
            f.fetch_full_poll(TOKEN, BASE, task_cache_nonempty=True)

    def test_empty_projects_with_nonempty_cache_raises(self, mock_urlopen):
        mock_urlopen.side_effect = [
            _resp([]),  # empty projects list (fetched first)
        ]
        with pytest.raises(OSError, match=r"^empty_response_when_cache_nonzero:"):
            f.fetch_full_poll(TOKEN, BASE, project_cache_nonempty=True)


# ===========================================================================
# Scenario 8 — Empty response allowed when the cache is empty
# ===========================================================================


class TestEmptyResponseAllowedWhenCacheEmpty:
    def test_empty_tasks_with_empty_cache_succeeds(self, mock_urlopen):
        mock_urlopen.side_effect = [
            _resp([{"id": 10, "title": "Alpha"}]),  # projects
            _resp([]),                              # projects/10/tasks empty
            _resp({"version": "0.24.6"}),           # info
        ]
        snap = f.fetch_full_poll(TOKEN, BASE, task_cache_nonempty=False)
        assert snap.tasks == ()
        assert 10 in snap.projects

    def test_empty_projects_with_empty_cache_succeeds(self, mock_urlopen):
        mock_urlopen.side_effect = [
            _resp([]),                     # empty projects
            _resp({"version": "0.24.6"}),  # info (no per-project task fetches)
        ]
        snap = f.fetch_full_poll(TOKEN, BASE, project_cache_nonempty=False)
        assert snap.projects == {}
        assert snap.tasks == ()
        # projects + info only — no task fetch when there are no projects.
        assert mock_urlopen.call_count == 2


# ===========================================================================
# Scenario 9 — /info failure does NOT abort
# ===========================================================================


class TestInfoFailureDoesNotAbort:
    def test_info_404_yields_none_version(self, mock_urlopen):
        mock_urlopen.side_effect = [
            _resp(PROJECTS_PAYLOAD),
            _resp(TASKS_PAYLOAD),  # projects/10/tasks
            _resp([]),             # projects/11/tasks
            _http_error(404, b'{"message":"no info endpoint"}'),
        ]
        snap = f.fetch_full_poll(TOKEN, BASE)
        assert snap.vikunja_version is None
        assert len(snap.tasks) == 2
        assert len(snap.projects) == 2

    def test_info_network_error_yields_none_version(self, mock_urlopen):
        mock_urlopen.side_effect = [
            _resp(PROJECTS_PAYLOAD),
            _resp(TASKS_PAYLOAD),
            _resp([]),
            urllib.error.URLError("network unreachable"),
        ]
        snap = f.fetch_full_poll(TOKEN, BASE)
        assert snap.vikunja_version is None


# ===========================================================================
# Scenario 10 — Strict call sequence: projects fetched before tasks
# ===========================================================================


class TestStrictCallSequence:
    def test_projects_failure_stops_before_task_fetch(self, mock_urlopen):
        """The projects fetch is first; if it fails no task fetch is attempted."""
        mock_urlopen.side_effect = _http_error(503, b'{"message":"down"}')
        with pytest.raises(OSError, match=r"^vikunja_5xx:"):
            f.fetch_full_poll(TOKEN, BASE)
        # Only 1 call was made (projects), not more.
        assert mock_urlopen.call_count == 1

    def test_projects_url_is_fetched_before_tasks(self, mock_urlopen):
        mock_urlopen.side_effect = [
            _resp([{"id": 10, "title": "Alpha"}]),
            _resp(TASKS_PAYLOAD),
            _resp({"version": "0.24.6"}),
        ]
        f.fetch_full_poll(TOKEN, BASE)
        urls = _urls(mock_urlopen)
        assert urls[0].endswith("projects")
        assert "projects/10/tasks" in urls[1]
