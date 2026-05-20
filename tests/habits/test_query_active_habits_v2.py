"""Tests for scripts/habits/query_active_habits_v2.py.

Originally written for WP04 / T015 against a server-side filter
implementation. Updated for G7 (#336): the helper now drops the
server-side ``?filter=`` query param (Vikunja v0.24.6 rejects the
compound expression — see G7 in
``docs/design/research/vikunja-task-model-research.md``) and applies the
equivalent ``done == False AND due_date <= <today>T23:59:59Z`` filter
in Python.

Covers the ``query_active_today()`` Python API and the ``__main__`` CLI
surface. All Vikunja HTTP traffic is mocked via ``urllib.request.urlopen``
(the ``mock_urlopen`` fixture from ``conftest.py``).

Enumeration is project-scoped to the Habits project — same pattern as
``reconcile_completions.py``. Each call makes **two** HTTP requests in
order:

  1. ``GET /projects`` -- resolve the Habits project id by title
  2. ``GET /projects/<id>/tasks`` -- enumerate the Habits project (no
     server-side filter; the helper filters client-side)

Tests use ``_responses(tasks=...)`` to script both responses in order via
``mock_urlopen.side_effect``.

Test groups:

1. Happy path — three active tasks returned in order.
2. Empty result.
3. ``today`` override / default UTC today.
4. URL shape — project-scoped, no server-side ``?filter=`` query param.
5. HTTPError -> CLI exit 1.
6. CLI stdout format -- JSONL, one task per line, each parses.
7. Project scoping (regression for the WP03 lesson).
8. Misc.

See also ``test_query_active_habits_v2_filter.py`` for the G7 (#336)
client-side filter test cases.
"""
from __future__ import annotations

import io
import json
import urllib.error
from unittest.mock import MagicMock

import pytest

from scripts.habits import query_active_habits_v2 as qv2


# ---------------------------------------------------------------------------
# Local mocking helpers
# ---------------------------------------------------------------------------


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


#: Habits project id used across tests.
HABITS_PROJECT_ID = 42


def _projects_payload(project_id: int = HABITS_PROJECT_ID):
    """Return a Vikunja-shaped ``GET /projects`` payload with a Habits project."""
    return [
        {"id": 1, "title": "Inbox"},
        {"id": project_id, "title": "Habits"},
        {"id": 99, "title": "Goals"},
    ]


def _responses(tasks, *, projects=None):
    """Build urlopen responses scripting (projects -> tasks).

    Use via ``mock_urlopen.side_effect = _responses(tasks=[...])``.
    """
    if projects is None:
        projects = _projects_payload()
    return [_resp(projects), _resp(tasks)]


def _http_error(code: int = 500, body: bytes = b'{"message":"boom"}'):
    return urllib.error.HTTPError(
        url="http://test/",
        code=code,
        msg="Server Error",
        hdrs=None,
        fp=io.BytesIO(body),
    )


def _task(
    task_id: int,
    title: str = "Habit",
    due_date: str = "2026-05-20T08:00:00Z",
    done: bool = False,
    repeat_after: int = 86400,
    project_id: int = HABITS_PROJECT_ID,
    labels: list | None = None,
) -> dict:
    return {
        "id": task_id,
        "title": title,
        "due_date": due_date,
        "done": done,
        "repeat_after": repeat_after,
        "project_id": project_id,
        "labels": labels or [],
    }


# ===========================================================================
# Group 1 — Happy path
# ===========================================================================


class TestHappyPath:
    def test_returns_three_active_tasks_in_order(self, mock_urlopen):
        """A canned list of 3 tasks is returned by query_active_today in order."""
        canned = [
            _task(14, title="Wake at 5:00 AM"),
            _task(15, title="Drink water"),
            _task(16, title="Meditate"),
        ]
        mock_urlopen.side_effect = _responses(tasks=canned)
        result = qv2.query_active_today(
            api_base_url="http://test/api/v1/",
            token="t",
            today="2026-05-20",
        )
        assert len(result) == 3
        assert [t["id"] for t in result] == [14, 15, 16]
        assert result[0]["title"] == "Wake at 5:00 AM"

    def test_returns_full_task_dicts_passthrough(self, mock_urlopen):
        """Task dicts are passed through unmodified."""
        canned = [_task(14, title="Wake", repeat_after=86400)]
        mock_urlopen.side_effect = _responses(tasks=canned)
        result = qv2.query_active_today(
            api_base_url="http://test/api/v1/",
            token="t",
            today="2026-05-20",
        )
        assert result[0] == canned[0]


# ===========================================================================
# Group 2 — Empty result
# ===========================================================================


class TestEmptyResult:
    def test_empty_list_returned(self, mock_urlopen):
        mock_urlopen.side_effect = _responses(tasks=[])
        result = qv2.query_active_today(
            api_base_url="http://test/api/v1/",
            token="t",
            today="2026-05-20",
        )
        assert result == []

    def test_empty_body_treated_as_no_tasks(self, mock_urlopen):
        """A Vikunja response with an empty body becomes an empty list."""
        mock_urlopen.side_effect = [
            _resp(_projects_payload()),
            _resp(None),  # empty body
        ]
        result = qv2.query_active_today(
            api_base_url="http://test/api/v1/",
            token="t",
            today="2026-05-20",
        )
        assert result == []


# ===========================================================================
# Group 3 — `today` override flows into the URL
# ===========================================================================


class TestTodayOverride:
    def test_today_kwarg_drives_client_side_boundary(self, mock_urlopen):
        """The explicit today override is applied as the client-side filter boundary.

        Post-G7 (#336): the URL no longer carries a ``filter=`` query
        param. The boundary lives in Python. We verify it by feeding a
        boundary-spanning task list and asserting the filter behavior.
        """
        # boundary = 2026-05-15T23:59:59Z
        payload = [
            {"id": 1, "title": "Before", "done": False, "due_date": "2026-05-15T08:00:00Z"},
            {"id": 2, "title": "After", "done": False, "due_date": "2026-05-16T00:00:00Z"},
        ]
        mock_urlopen.side_effect = _responses(tasks=payload)
        result = qv2.query_active_today(
            api_base_url="http://test/api/v1/",
            token="t",
            today="2026-05-15",
        )
        assert [t["id"] for t in result] == [1]

    def test_today_default_uses_utc_today(self, mock_urlopen):
        """When `today` is None, the helper uses the system UTC date.

        We don't assert the exact value (test would race the calendar);
        instead we confirm two HTTP calls happen and the second call hits
        the project-scoped tasks endpoint.
        """
        mock_urlopen.side_effect = _responses(tasks=[])
        qv2.query_active_today(
            api_base_url="http://test/api/v1/",
            token="t",
        )
        assert len(mock_urlopen.call_args_list) == 2
        tasks_req = mock_urlopen.call_args_list[1][0][0]
        url = tasks_req.full_url
        assert f"/projects/{HABITS_PROJECT_ID}/tasks" in url

    def test_today_bad_format_raises_value_error(self, mock_urlopen):
        mock_urlopen.side_effect = AssertionError("must not be called")
        with pytest.raises(ValueError, match="YYYY-MM-DD"):
            qv2.query_active_today(
                api_base_url="http://test/api/v1/",
                token="t",
                today="5/15/2026",
            )


# ===========================================================================
# Group 4 — URL shape (post-G7 #336): no server-side ?filter= query param
# ===========================================================================


class TestUrlShape:
    """Verify the helper no longer sends a server-side ``?filter=`` query.

    Post-G7 (#336), Vikunja v0.24.6's compound filter expression
    ``due_date <= <iso> AND done = false`` is rejected with HTTP 400.
    The helper now drops the filter and applies the equivalent logic in
    Python. These tests pin the new URL shape.
    """

    def test_tasks_url_has_no_filter_query_param(self, mock_urlopen):
        """The tasks GET request must not include any ``?filter=`` query."""
        mock_urlopen.side_effect = _responses(tasks=[])
        qv2.query_active_today(
            api_base_url="http://test/api/v1/",
            token="t",
            today="2026-05-20",
        )
        tasks_req = mock_urlopen.call_args_list[1][0][0]
        assert "filter=" not in tasks_req.full_url
        # And no query string at all on the tasks endpoint.
        assert "?" not in tasks_req.full_url

    def test_tasks_url_is_project_scoped_bare_endpoint(self, mock_urlopen):
        """The tasks GET must hit ``/projects/<id>/tasks`` with no extras."""
        mock_urlopen.side_effect = _responses(tasks=[])
        qv2.query_active_today(
            api_base_url="http://test/api/v1/",
            token="t",
            today="2026-05-20",
        )
        tasks_req = mock_urlopen.call_args_list[1][0][0]
        assert tasks_req.full_url.endswith(f"/projects/{HABITS_PROJECT_ID}/tasks")

    def test_client_side_filter_applies_done_false_semantics(self, mock_urlopen):
        """Tasks with ``done=True`` are excluded by the client-side filter."""
        payload = [
            _task(14, title="Active", done=False, due_date="2026-05-20T08:00:00Z"),
            _task(15, title="Done", done=True, due_date="2026-05-20T08:00:00Z"),
        ]
        mock_urlopen.side_effect = _responses(tasks=payload)
        result = qv2.query_active_today(
            api_base_url="http://test/api/v1/",
            token="t",
            today="2026-05-20",
        )
        assert [t["id"] for t in result] == [14]

    def test_client_side_filter_applies_due_date_predicate(self, mock_urlopen):
        """Tasks with ``due_date > <today>T23:59:59Z`` are excluded."""
        payload = [
            _task(14, title="Today", done=False, due_date="2026-05-20T08:00:00Z"),
            _task(15, title="Tomorrow", done=False, due_date="2026-05-21T00:00:00Z"),
        ]
        mock_urlopen.side_effect = _responses(tasks=payload)
        result = qv2.query_active_today(
            api_base_url="http://test/api/v1/",
            token="t",
            today="2026-05-20",
        )
        assert [t["id"] for t in result] == [14]


# ===========================================================================
# Group 5 — HTTPError -> CLI exit 1
# ===========================================================================


class TestCliFailures:
    def test_http_error_via_cli_exits_one(
        self, mock_urlopen, tmp_token_file, capsys
    ):
        """A Vikunja HTTPError surfaces as CLI exit 1 with a helpful stderr."""
        mock_urlopen.side_effect = _http_error(503, b'{"message":"down"}')
        exit_code = qv2.main([
            "--token-file", str(tmp_token_file),
            "--base-url", "http://test/api/v1/",
            "--today", "2026-05-20",
        ])
        assert exit_code == 1
        err = capsys.readouterr().err
        assert "query failed" in err or "ERROR" in err

    def test_url_error_via_cli_exits_one(
        self, mock_urlopen, tmp_token_file, capsys
    ):
        mock_urlopen.side_effect = urllib.error.URLError("connection refused")
        exit_code = qv2.main([
            "--token-file", str(tmp_token_file),
            "--base-url", "http://test/api/v1/",
            "--today", "2026-05-20",
        ])
        assert exit_code == 1
        err = capsys.readouterr().err
        assert "ERROR" in err

    def test_missing_token_file_exits_one(
        self, mock_urlopen, tmp_path, capsys
    ):
        mock_urlopen.side_effect = AssertionError("must not be called")
        missing = tmp_path / "nope" / "token"
        exit_code = qv2.main([
            "--token-file", str(missing),
            "--base-url", "http://test/api/v1/",
        ])
        assert exit_code == 1
        err = capsys.readouterr().err
        assert "Token file not found" in err

    def test_cli_bad_today_exits_two(
        self, mock_urlopen, tmp_token_file, capsys
    ):
        mock_urlopen.side_effect = AssertionError("must not be called")
        exit_code = qv2.main([
            "--token-file", str(tmp_token_file),
            "--base-url", "http://test/api/v1/",
            "--today", "5/15/2026",
        ])
        assert exit_code == 2
        err = capsys.readouterr().err
        assert "YYYY-MM-DD" in err


# ===========================================================================
# Group 6 — CLI stdout format (JSONL, one task per line)
# ===========================================================================


class TestCliStdoutFormat:
    def test_three_tasks_emitted_as_jsonl(
        self, mock_urlopen, tmp_token_file, capsys
    ):
        canned = [
            _task(14, title="Wake at 5:00 AM"),
            _task(15, title="Drink water"),
            _task(16, title="Meditate"),
        ]
        mock_urlopen.side_effect = _responses(tasks=canned)
        exit_code = qv2.main([
            "--token-file", str(tmp_token_file),
            "--base-url", "http://test/api/v1/",
            "--today", "2026-05-20",
        ])
        assert exit_code == 0
        out = capsys.readouterr().out
        lines = [ln for ln in out.splitlines() if ln.strip()]
        assert len(lines) == 3
        for line in lines:
            obj = json.loads(line)
            assert "id" in obj
            assert "title" in obj
        ids = [json.loads(ln)["id"] for ln in lines]
        assert ids == [14, 15, 16]

    def test_empty_result_emits_no_stdout(
        self, mock_urlopen, tmp_token_file, capsys
    ):
        mock_urlopen.side_effect = _responses(tasks=[])
        exit_code = qv2.main([
            "--token-file", str(tmp_token_file),
            "--base-url", "http://test/api/v1/",
            "--today", "2026-05-20",
        ])
        assert exit_code == 0
        out = capsys.readouterr().out
        assert out == ""


# ===========================================================================
# Group 7 — Project scoping (regression for the WP03 lesson)
# ===========================================================================


class TestProjectScoping:
    """Ensure the query is project-scoped to Habits.

    Without scoping, ``GET /tasks/all?filter=...`` would let non-habit
    tasks (Inbox, Goals) match the filter and leak into the Phase 5
    check-in flow. The helper must mirror the v1 sibling's pattern of
    resolving the Habits project by title first.
    """

    def test_two_requests_projects_then_tasks(self, mock_urlopen):
        mock_urlopen.side_effect = _responses(tasks=[])
        qv2.query_active_today(
            api_base_url="http://test/api/v1/",
            token="t",
            today="2026-05-20",
        )
        assert len(mock_urlopen.call_args_list) == 2

    def test_first_request_is_projects_lookup(self, mock_urlopen):
        mock_urlopen.side_effect = _responses(tasks=[])
        qv2.query_active_today(
            api_base_url="http://test/api/v1/",
            token="t",
            today="2026-05-20",
        )
        first_req = mock_urlopen.call_args_list[0][0][0]
        assert first_req.get_method() == "GET"
        assert first_req.full_url.endswith("/projects")

    def test_second_request_is_project_scoped_tasks(self, mock_urlopen):
        mock_urlopen.side_effect = _responses(tasks=[])
        qv2.query_active_today(
            api_base_url="http://test/api/v1/",
            token="t",
            today="2026-05-20",
        )
        tasks_req = mock_urlopen.call_args_list[1][0][0]
        assert tasks_req.get_method() == "GET"
        assert f"/projects/{HABITS_PROJECT_ID}/tasks" in tasks_req.full_url

    def test_no_habits_project_raises_os_error(self, mock_urlopen):
        """If the Habits project cannot be resolved, raise OSError."""
        projects_without_habits = [
            {"id": 1, "title": "Inbox"},
            {"id": 99, "title": "Goals"},
        ]
        mock_urlopen.side_effect = [_resp(projects_without_habits)]
        with pytest.raises(OSError, match="No project titled"):
            qv2.query_active_today(
                api_base_url="http://test/api/v1/",
                token="t",
                today="2026-05-20",
            )

    def test_non_list_projects_payload_raises_os_error(self, mock_urlopen):
        mock_urlopen.side_effect = [_resp({"not": "a list"})]
        with pytest.raises(OSError, match="non-list payload"):
            qv2.query_active_today(
                api_base_url="http://test/api/v1/",
                token="t",
                today="2026-05-20",
            )

    def test_non_list_tasks_payload_raises_os_error(self, mock_urlopen):
        mock_urlopen.side_effect = [
            _resp(_projects_payload()),
            _resp({"not": "a list"}),
        ]
        with pytest.raises(OSError, match="non-list payload"):
            qv2.query_active_today(
                api_base_url="http://test/api/v1/",
                token="t",
                today="2026-05-20",
            )


# ===========================================================================
# Group 8 — Misc
# ===========================================================================


class TestMisc:
    def test_help_exits_zero(self):
        with pytest.raises(SystemExit) as exc:
            qv2.main(["--help"])
        assert exc.value.code == 0

    def test_authorization_header_present(self, mock_urlopen):
        """Both Vikunja calls must carry a Bearer token header."""
        mock_urlopen.side_effect = _responses(tasks=[])
        qv2.query_active_today(
            api_base_url="http://test/api/v1/",
            token="abc123",
            today="2026-05-20",
        )
        for call in mock_urlopen.call_args_list:
            req = call[0][0]
            assert req.headers.get("Authorization") == "Bearer abc123"

    def test_base_url_normalized_without_trailing_slash(self, mock_urlopen):
        """A base URL without trailing slash still produces valid request URLs."""
        mock_urlopen.side_effect = _responses(tasks=[])
        qv2.query_active_today(
            api_base_url="http://test/api/v1",
            token="t",
            today="2026-05-20",
        )
        first_req = mock_urlopen.call_args_list[0][0][0]
        assert first_req.full_url == "http://test/api/v1/projects"

    def test_non_dict_task_entries_skipped(self, mock_urlopen):
        """Defensive: stray non-dict entries are skipped silently."""
        mock_urlopen.side_effect = _responses(
            tasks=[_task(14), "garbage", 42, _task(15)]
        )
        result = qv2.query_active_today(
            api_base_url="http://test/api/v1/",
            token="t",
            today="2026-05-20",
        )
        ids = [t["id"] for t in result]
        assert ids == [14, 15]
