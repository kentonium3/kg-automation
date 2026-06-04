"""Tests for scripts/sync/http.py (WP01 / T005).

Covers the happy path and every error path of the HTTP wrapper using
``unittest.mock`` patches of ``urllib.request.urlopen``. No live network.
"""
from __future__ import annotations

import io
import json
import urllib.error
from unittest.mock import MagicMock

import pytest

from scripts.sync import http as h


# ---------------------------------------------------------------------------
# Local mocking helpers (mirrors tests/habits/test_record_completion.py)
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


def _resp_raw(raw_body: bytes, *, status: int = 200):
    """Mock response returning raw (non-JSON) bytes."""
    resp = MagicMock(name="response")
    resp.status = status
    resp.read = MagicMock(return_value=raw_body)
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


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_urlopen(monkeypatch):
    """Patch ``urllib.request.urlopen`` used inside scripts.sync.http."""
    mock = MagicMock()
    monkeypatch.setattr("scripts.sync.http.urllib.request.urlopen", mock)
    return mock


# ===========================================================================
# Group 1 — get_json happy path
# ===========================================================================


class TestGetJsonHappyPath:
    def test_returns_parsed_dict(self, mock_urlopen):
        mock_urlopen.side_effect = [_resp({"id": 14, "title": "Wake"})]
        result = h.get_json("http://test/api/v1/tasks/14", "tok")
        assert result == {"id": 14, "title": "Wake"}

    def test_authorization_header_set(self, mock_urlopen):
        mock_urlopen.side_effect = [_resp({"ok": True})]
        h.get_json("http://test/", "test-token")
        req = mock_urlopen.call_args_list[0][0][0]
        assert req.headers.get("Authorization") == "Bearer test-token"

    def test_method_is_get(self, mock_urlopen):
        mock_urlopen.side_effect = [_resp({"ok": True})]
        h.get_json("http://test/", "tok")
        req = mock_urlopen.call_args_list[0][0][0]
        assert req.get_method() == "GET"
        # GET requests carry no body.
        assert req.data is None

    def test_default_timeout_used(self, mock_urlopen):
        mock_urlopen.side_effect = [_resp({"ok": True})]
        h.get_json("http://test/", "tok")
        # Called with timeout kwarg matching HTTP_TIMEOUT_SECONDS.
        kwargs = mock_urlopen.call_args_list[0][1]
        assert kwargs.get("timeout") == h.HTTP_TIMEOUT_SECONDS

    def test_custom_timeout_passed_through(self, mock_urlopen):
        mock_urlopen.side_effect = [_resp({"ok": True})]
        h.get_json("http://test/", "tok", timeout=30)
        kwargs = mock_urlopen.call_args_list[0][1]
        assert kwargs.get("timeout") == 30


# ===========================================================================
# Group 2 — get_json error paths
# ===========================================================================


class TestGetJsonErrors:
    def test_http_500_raises_oserror_with_status(self, mock_urlopen):
        mock_urlopen.side_effect = _http_error(500, b'{"message":"server down"}')
        with pytest.raises(OSError, match=r"HTTP 500"):
            h.get_json("http://test/", "tok")

    def test_http_500_includes_body_in_message(self, mock_urlopen):
        mock_urlopen.side_effect = _http_error(500, b'{"message":"server down"}')
        with pytest.raises(OSError, match="server down"):
            h.get_json("http://test/", "tok")

    def test_http_404_raises_oserror(self, mock_urlopen):
        mock_urlopen.side_effect = _http_error(404, b'{"message":"not found"}')
        with pytest.raises(OSError, match=r"HTTP 404"):
            h.get_json("http://test/api/v1/tasks/9999", "tok")

    def test_network_failure_raises_oserror_with_failure_marker(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError("connection refused")
        with pytest.raises(OSError, match=r"network failure"):
            h.get_json("http://test/", "tok")

    def test_timeout_raises_oserror(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError("timed out")
        with pytest.raises(OSError, match=r"network failure"):
            h.get_json("http://test/", "tok")

    def test_url_included_in_error_message(self, mock_urlopen):
        mock_urlopen.side_effect = _http_error(500, b"x")
        with pytest.raises(OSError, match="http://test/specific-path"):
            h.get_json("http://test/specific-path", "tok")


# ===========================================================================
# Group 3 — Non-JSON body handling
# ===========================================================================


class TestNonJsonBody:
    def test_non_json_body_returns_none(self, mock_urlopen):
        mock_urlopen.side_effect = [_resp_raw(b"<html>oops</html>", status=200)]
        # 200 with non-JSON: get_json returns None (does NOT raise).
        result = h.get_json("http://test/", "tok")
        assert result is None

    def test_empty_body_returns_none(self, mock_urlopen):
        mock_urlopen.side_effect = [_resp_raw(b"", status=200)]
        result = h.get_json("http://test/", "tok")
        assert result is None


# ===========================================================================
# Group 4 — post_json
# ===========================================================================


class TestPostJson:
    def test_post_includes_content_type_header(self, mock_urlopen):
        mock_urlopen.side_effect = [_resp({"ok": True})]
        h.post_json("http://test/", "tok", body={"x": 1})
        req = mock_urlopen.call_args_list[0][0][0]
        assert req.headers.get("Content-type") == "application/json"

    def test_post_serializes_body_as_json(self, mock_urlopen):
        mock_urlopen.side_effect = [_resp({"ok": True})]
        h.post_json("http://test/", "tok", body={"x": 1, "y": [2, 3]})
        req = mock_urlopen.call_args_list[0][0][0]
        body = json.loads(req.data.decode("utf-8"))
        assert body == {"x": 1, "y": [2, 3]}

    def test_post_method_is_post(self, mock_urlopen):
        mock_urlopen.side_effect = [_resp({"ok": True})]
        h.post_json("http://test/", "tok", body={"x": 1})
        req = mock_urlopen.call_args_list[0][0][0]
        assert req.get_method() == "POST"


# ===========================================================================
# Group 5 — Module sanity
# ===========================================================================


class TestModuleConstants:
    def test_default_timeout_is_10_seconds(self):
        assert h.HTTP_TIMEOUT_SECONDS == 10
