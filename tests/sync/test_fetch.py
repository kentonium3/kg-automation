"""Tests for scripts/sync/fetch.py (WP02 / T008).

Mocks ``urllib.request.urlopen`` to drive the HTTP wrapper without live
network. Each test asserts the exact call count to catch accidental extra
requests.
"""
from __future__ import annotations

import io
import json
import urllib.error
from unittest.mock import MagicMock

import pytest

from scripts.sync import fetch as f


# ---------------------------------------------------------------------------
# Local mocking helpers (same shape as test_http.py)
# ---------------------------------------------------------------------------


def _resp(payload, *, status: int = 200):
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


# ===========================================================================
# Group 1 — empty delta
# ===========================================================================


class TestEmptyDelta:
    def test_no_changes_returns_empty_delta(self, mock_urlopen):
        # 2 calls: /tasks/all (empty) + /info (version).
        mock_urlopen.side_effect = [
            _resp([]),
            _resp({"version": "0.24.6"}),
        ]
        delta = f.fetch_delta(TOKEN, BASE, "2026-06-01T00:00:00Z", known_project_ids=set())
        assert delta.tasks == ()
        assert delta.projects == {}
        assert delta.vikunja_version == "0.24.6"
        assert mock_urlopen.call_count == 2


# ===========================================================================
# Group 2 — project resolution
# ===========================================================================


class TestProjectResolution:
    def test_known_project_id_skips_extra_fetch(self, mock_urlopen):
        # Two tasks both reference project 13 which is already known.
        # Calls: /tasks/all + /info (no project fetch).
        mock_urlopen.side_effect = [
            _resp(
                [
                    {"id": 14, "project_id": 13, "title": "x", "updated": "2026-06-04T18:32:00Z"},
                    {"id": 15, "project_id": 13, "title": "y", "updated": "2026-06-04T18:32:00Z"},
                ]
            ),
            _resp({"version": "0.24.6"}),
        ]
        delta = f.fetch_delta(TOKEN, BASE, "2026-06-01T00:00:00Z", known_project_ids={13})
        assert mock_urlopen.call_count == 2
        assert delta.projects == {}
        assert len(delta.tasks) == 2

    def test_unknown_project_triggers_just_in_time_fetch(self, mock_urlopen):
        # Calls: /tasks/all + /projects/99 + /info.
        mock_urlopen.side_effect = [
            _resp([{"id": 14, "project_id": 99, "title": "x", "updated": "2026-06-04T18:32:00Z"}]),
            _resp({"id": 99, "title": "New Project", "is_archived": False}),
            _resp({"version": "0.24.6"}),
        ]
        delta = f.fetch_delta(TOKEN, BASE, "2026-06-01T00:00:00Z", known_project_ids=set())
        assert mock_urlopen.call_count == 3
        assert 99 in delta.projects
        assert delta.projects[99]["title"] == "New Project"

    def test_multiple_unknown_projects_each_get_fetched(self, mock_urlopen):
        # Calls: /tasks/all + /projects/99 + /projects/100 + /info.
        mock_urlopen.side_effect = [
            _resp(
                [
                    {"id": 14, "project_id": 99, "title": "x", "updated": "2026-06-04T18:32:00Z"},
                    {"id": 15, "project_id": 100, "title": "y", "updated": "2026-06-04T18:32:00Z"},
                ]
            ),
            _resp({"id": 99, "title": "P99", "is_archived": False}),
            _resp({"id": 100, "title": "P100", "is_archived": False}),
            _resp({"version": "0.24.6"}),
        ]
        delta = f.fetch_delta(TOKEN, BASE, "2026-06-01T00:00:00Z", known_project_ids=set())
        assert mock_urlopen.call_count == 4
        assert set(delta.projects.keys()) == {99, 100}


# ===========================================================================
# Group 3 — graceful degradation
# ===========================================================================


class TestGracefulDegradation:
    def test_per_project_failure_degrades_to_stub(self, mock_urlopen, capsys):
        # /tasks/all + /projects/99 (FAILS with 503) + /info.
        mock_urlopen.side_effect = [
            _resp([{"id": 14, "project_id": 99, "title": "x", "updated": "2026-06-04T18:32:00Z"}]),
            _http_error(503, b'{"message":"project down"}'),
            _resp({"version": "0.24.6"}),
        ]
        delta = f.fetch_delta(TOKEN, BASE, "2026-06-01T00:00:00Z", known_project_ids=set())
        assert mock_urlopen.call_count == 3
        assert delta.projects[99] == {
            "id": 99,
            "title": "<unknown>",
            "is_archived": False,
        }
        # Logged a warning to stderr.
        assert "project 99 fetch failed" in capsys.readouterr().err

    def test_info_failure_silent(self, mock_urlopen):
        # /tasks/all + /info (FAILS).
        mock_urlopen.side_effect = [
            _resp([]),
            _http_error(404, b'{"message":"no info endpoint"}'),
        ]
        delta = f.fetch_delta(TOKEN, BASE, "2026-06-01T00:00:00Z", known_project_ids=set())
        assert mock_urlopen.call_count == 2
        assert delta.vikunja_version is None

    def test_info_non_dict_body_yields_none_version(self, mock_urlopen):
        mock_urlopen.side_effect = [
            _resp([]),
            _resp(["not", "a", "dict"]),
        ]
        delta = f.fetch_delta(TOKEN, BASE, "2026-06-01T00:00:00Z", known_project_ids=set())
        assert delta.vikunja_version is None


# ===========================================================================
# Group 4 — main delta failure propagates
# ===========================================================================


class TestMainDeltaFailure:
    def test_main_delta_failure_raises(self, mock_urlopen):
        mock_urlopen.side_effect = _http_error(503, b'{"message":"vikunja down"}')
        with pytest.raises(OSError, match=r"HTTP 503"):
            f.fetch_delta(TOKEN, BASE, "2026-06-01T00:00:00Z", known_project_ids=set())

    def test_main_delta_non_list_body_treated_as_empty(self, mock_urlopen):
        # Defensive: Vikunja returning unexpected non-list shape on /tasks/all
        # should not crash. Treat as empty.
        mock_urlopen.side_effect = [
            _resp({"unexpected": "shape"}),
            _resp({"version": "0.24.6"}),
        ]
        delta = f.fetch_delta(TOKEN, BASE, "2026-06-01T00:00:00Z", known_project_ids=set())
        assert delta.tasks == ()


# ===========================================================================
# Group 5 — Authorization + URL composition
# ===========================================================================


class TestAuthAndUrl:
    def test_uses_bearer_token(self, mock_urlopen):
        mock_urlopen.side_effect = [_resp([]), _resp({"version": "0.24.6"})]
        f.fetch_delta(TOKEN, BASE, "2026-06-01T00:00:00Z", known_project_ids=set())
        req = mock_urlopen.call_args_list[0][0][0]
        assert req.headers.get("Authorization") == "Bearer test-token"

    def test_delta_url_includes_updated_since(self, mock_urlopen):
        mock_urlopen.side_effect = [_resp([]), _resp({"version": "0.24.6"})]
        f.fetch_delta(TOKEN, BASE, "2026-06-01T12:30:00Z", known_project_ids=set())
        req = mock_urlopen.call_args_list[0][0][0]
        assert "updated_since=2026-06-01T12:30:00Z" in req.full_url
        assert req.full_url.startswith(BASE + "tasks/all?")

    def test_project_url_uses_id(self, mock_urlopen):
        mock_urlopen.side_effect = [
            _resp([{"id": 14, "project_id": 42, "title": "x", "updated": "2026-06-04T18:32:00Z"}]),
            _resp({"id": 42, "title": "X", "is_archived": False}),
            _resp({"version": "0.24.6"}),
        ]
        f.fetch_delta(TOKEN, BASE, "2026-06-01T00:00:00Z", known_project_ids=set())
        project_req = mock_urlopen.call_args_list[1][0][0]
        assert project_req.full_url == BASE + "projects/42"


# ===========================================================================
# Group 6 — vikunja_now_iso
# ===========================================================================


class TestVikunjaNowIso:
    def test_returns_z_suffix(self):
        result = f.vikunja_now_iso()
        assert result.endswith("Z")
        # ISO-8601 prefix shape: YYYY-MM-DDTHH:MM:SS
        assert len(result) == 20

    def test_is_utc(self):
        result = f.vikunja_now_iso()
        # No timezone offset other than Z.
        assert "+" not in result
        assert "-" not in result.split("T")[1]
