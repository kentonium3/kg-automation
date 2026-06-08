"""Unit tests for ``scripts.common.vikunja_client`` (mission WP01).

Per DIRECTIVE_034 the test surface was authored alongside the
implementation. Coverage targets are enforced by invoking
``pytest --cov=scripts.common.vikunja_client --cov-branch
--cov-fail-under=90`` (see ``tests/common/README.md`` for the canonical
invocation).

Test groups
-----------
- Construction (defaults, overrides, validation rejections).
- Request execution (URL composition, headers, body encoding, method
  wiring across GET/POST/PUT/DELETE).
- Param encoding (single, multi, special chars).
- Error mapping (each HTTP status class, timeouts, URLErrors, non-JSON
  bodies, 204 empty body).
- Redaction (``str(exc)`` short; ``verbose_message`` longer; no body
  content leaks).
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

from scripts.common import vikunja_client as vc
from scripts.common.vikunja_client import (
    VikunjaAuthError,
    VikunjaBadRequestError,
    VikunjaClient,
    VikunjaError,
    VikunjaHttpError,
    VikunjaNotFoundError,
    VikunjaServerError,
    VikunjaTimeoutError,
)


# Test-time base URL — never touches a real server because the global
# ``_block_live_http`` guard in ``tests/conftest.py`` raises on any
# unmocked ``urlopen`` call.
TEST_BASE_URL = "https://vikunja.test/api/v1"
TEST_TOKEN = "test-token-xxx"


def _client(**overrides) -> VikunjaClient:
    """Construct a client with safe defaults; override per-test as needed."""
    kwargs = {"base_url": TEST_BASE_URL, "token": TEST_TOKEN}
    kwargs.update(overrides)
    return VikunjaClient(**kwargs)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_construct_with_explicit_args_succeeds() -> None:
    client = _client()
    assert client.base_url == TEST_BASE_URL
    assert client.token == TEST_TOKEN
    assert client.timeout == vc.DEFAULT_TIMEOUT


def test_construct_strips_trailing_slash_from_base_url() -> None:
    client = _client(base_url="https://vikunja.test/api/v1/")
    assert client.base_url == "https://vikunja.test/api/v1"


def test_construct_strips_token_whitespace() -> None:
    client = _client(token="  token-with-padding  \n")
    assert client.token == "token-with-padding"


def test_construct_rejects_invalid_base_url() -> None:
    with pytest.raises(ValueError, match="base_url"):
        _client(base_url="not-a-url")


def test_construct_rejects_base_url_missing_api_v1() -> None:
    with pytest.raises(ValueError, match="base_url"):
        _client(base_url="https://vikunja.test")


def test_construct_rejects_empty_token() -> None:
    with pytest.raises(ValueError, match="token"):
        _client(token="   ")


def test_construct_rejects_non_positive_timeout() -> None:
    with pytest.raises(ValueError, match="timeout"):
        _client(timeout=0)
    with pytest.raises(ValueError, match="timeout"):
        _client(timeout=-1.5)


def test_construct_rejects_non_numeric_timeout() -> None:
    with pytest.raises(ValueError, match="timeout"):
        _client(timeout="forever")  # type: ignore[arg-type]


def test_construct_resolves_base_url_from_config_when_omitted(monkeypatch) -> None:
    monkeypatch.setattr(
        "scripts.common.vikunja_config.get_vikunja_base_url",
        lambda: "https://configured.test/api/v1/",
    )
    client = VikunjaClient(token=TEST_TOKEN)
    assert client.base_url == "https://configured.test/api/v1"


def test_construct_resolves_token_from_default_path(monkeypatch, tmp_path) -> None:
    token_file = tmp_path / "vikunja-token"
    token_file.write_text("file-token\n", encoding="utf-8")
    monkeypatch.setattr(vc, "DEFAULT_TOKEN_PATH", token_file)
    client = VikunjaClient(base_url=TEST_BASE_URL)
    assert client.token == "file-token"


def test_construct_raises_when_token_file_missing(monkeypatch, tmp_path) -> None:
    missing = tmp_path / "does-not-exist"
    monkeypatch.setattr(vc, "DEFAULT_TOKEN_PATH", missing)
    with pytest.raises(ValueError, match="token file"):
        VikunjaClient(base_url=TEST_BASE_URL)


# ---------------------------------------------------------------------------
# Request execution + URL composition
# ---------------------------------------------------------------------------


def test_get_returns_parsed_json_list(mock_vikunja_urlopen) -> None:
    calls = mock_vikunja_urlopen("mock_response_200_json")
    result = _client().get("/projects/13/tasks")
    assert result == [{"id": 1, "title": "Sample habit", "done": False}]
    assert len(calls) == 1
    assert calls[0].full_url == f"{TEST_BASE_URL}/projects/13/tasks"
    assert calls[0].get_method() == "GET"


def test_get_returns_parsed_json_object(mock_vikunja_urlopen) -> None:
    mock_vikunja_urlopen("mock_response_200_object")
    result = _client().get("/tasks/7")
    assert result == {"id": 7, "title": "One task", "done": True}


def test_get_returns_empty_dict_on_empty_body(mock_vikunja_urlopen) -> None:
    # Per contract (data-model.md: DELETE returns "parsed JSON, often empty
    # dict") empty successful bodies parse to ``{}`` so callers get a uniform
    # mapping type. Regression for cycle-1 review issue #3.
    mock_vikunja_urlopen("mock_response_204_no_content")
    assert _client().get("/tasks/1") == {}


def test_request_attaches_authorization_header(mock_vikunja_urlopen) -> None:
    calls = mock_vikunja_urlopen("mock_response_200_object")
    _client().get("/tasks/7")
    assert calls[0].get_header("Authorization") == f"Bearer {TEST_TOKEN}"


def test_get_does_not_set_content_type_header(mock_vikunja_urlopen) -> None:
    calls = mock_vikunja_urlopen("mock_response_200_object")
    _client().get("/tasks/7")
    assert calls[0].get_header("Content-type") is None


def test_post_serializes_json_body_and_sets_content_type(mock_vikunja_urlopen) -> None:
    calls = mock_vikunja_urlopen("mock_response_200_object")
    body = {"title": "New", "project_id": 13}
    _client().post("/tasks", json=body)
    req = calls[0]
    assert req.get_method() == "POST"
    assert req.get_header("Content-type") == "application/json"
    assert json.loads(req.data.decode("utf-8")) == body


def test_put_serializes_json_body(mock_vikunja_urlopen) -> None:
    calls = mock_vikunja_urlopen("mock_response_200_object")
    _client().put("/tasks/7", json={"done": True})
    req = calls[0]
    assert req.get_method() == "PUT"
    assert req.get_header("Content-type") == "application/json"
    assert json.loads(req.data.decode("utf-8")) == {"done": True}


def test_delete_makes_delete_request(mock_vikunja_urlopen) -> None:
    calls = mock_vikunja_urlopen("mock_response_204_no_content")
    result = _client().delete("/tasks/7")
    # DELETE returns parsed JSON; empty body -> {} per contract (issue #3).
    assert result == {}
    assert calls[0].get_method() == "DELETE"
    assert calls[0].data is None


def test_delete_empty_body_returns_empty_dict(mock_vikunja_urlopen) -> None:
    # Regression for cycle-1 review issue #3: DELETE on a resource with an
    # empty body must yield {} (uniform mapping), not None.
    mock_vikunja_urlopen("mock_response_204_no_content")
    assert _client().delete("/tasks/9") == {}


def test_post_without_body_sets_content_type(mock_vikunja_urlopen) -> None:
    # Regression for cycle-1 review issue #4: Content-Type: application/json
    # is method-driven (POST/PUT) per contract, not body-driven.
    calls = mock_vikunja_urlopen("mock_response_200_object")
    _client().post("/tasks/7/bulk")
    assert calls[0].get_header("Content-type") == "application/json"
    assert calls[0].data is None


def test_put_without_body_sets_content_type(mock_vikunja_urlopen) -> None:
    # Regression for cycle-1 review issue #4: PUT mirrors POST — bodyless
    # PUTs still advertise application/json.
    calls = mock_vikunja_urlopen("mock_response_200_object")
    _client().put("/tasks/7/bulk")
    assert calls[0].get_header("Content-type") == "application/json"
    assert calls[0].data is None


# ---------------------------------------------------------------------------
# Param encoding
# ---------------------------------------------------------------------------


def test_single_param_appended_to_url(mock_vikunja_urlopen) -> None:
    calls = mock_vikunja_urlopen("mock_response_200_json")
    _client().get("/tasks", params={"page": "2"})
    assert calls[0].full_url == f"{TEST_BASE_URL}/tasks?page=2"


def test_multiple_params_appended_in_order(mock_vikunja_urlopen) -> None:
    calls = mock_vikunja_urlopen("mock_response_200_json")
    _client().get("/tasks", params={"filter": "done=true", "per_page": "200"})
    parsed = urllib.parse.urlparse(calls[0].full_url)
    qs = urllib.parse.parse_qs(parsed.query)
    assert qs == {"filter": ["done=true"], "per_page": ["200"]}


def test_special_chars_are_url_encoded(mock_vikunja_urlopen) -> None:
    calls = mock_vikunja_urlopen("mock_response_200_json")
    _client().get("/tasks", params={"filter": "title=Strength training"})
    parsed = urllib.parse.urlparse(calls[0].full_url)
    qs = urllib.parse.parse_qs(parsed.query)
    assert qs["filter"] == ["title=Strength training"]
    assert "%20" in parsed.query or "+" in parsed.query


def test_get_merges_params_with_path_query_string(mock_vikunja_urlopen) -> None:
    # Regression for cycle-1 review issue #2: when ``path`` already contains
    # a ``?`` query string (e.g. ``/projects/13/tasks?filter=done=true``),
    # adding params must produce a single, well-formed query string —
    # ``?filter=done=true&per_page=200`` — not ``?filter=done=true?per_page=200``.
    # Assert structurally via ``parse_qs`` to avoid ordering brittleness.
    calls = mock_vikunja_urlopen("mock_response_200_json")
    _client().get("/projects/13/tasks?filter=done=true", params={"per_page": "200"})
    parsed = urllib.parse.urlparse(calls[0].full_url)
    qs = urllib.parse.parse_qs(parsed.query)
    assert qs == {"filter": ["done=true"], "per_page": ["200"]}
    assert parsed.path == "/api/v1/projects/13/tasks"
    # Exactly one '?' separator in the URL — no stray ``?`` from naive append.
    assert calls[0].full_url.count("?") == 1


def test_get_params_override_embedded_query_string(mock_vikunja_urlopen) -> None:
    # When ``params`` and ``path`` share a key, the explicit ``params`` arg
    # wins — keeps the API single-source-of-truth for caller intent.
    calls = mock_vikunja_urlopen("mock_response_200_json")
    _client().get("/tasks?page=1", params={"page": "3"})
    parsed = urllib.parse.urlparse(calls[0].full_url)
    qs = urllib.parse.parse_qs(parsed.query)
    assert qs == {"page": ["3"]}


def test_get_preserves_embedded_query_when_no_params(mock_vikunja_urlopen) -> None:
    # Branch-coverage companion: ``params`` is None/empty, embedded query
    # string passes through unchanged.
    calls = mock_vikunja_urlopen("mock_response_200_json")
    _client().get("/tasks?filter=done=true")
    parsed = urllib.parse.urlparse(calls[0].full_url)
    qs = urllib.parse.parse_qs(parsed.query)
    assert qs == {"filter": ["done=true"]}


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "scenario,exc_class",
    [
        ("mock_response_401", VikunjaAuthError),
        ("mock_response_404", VikunjaNotFoundError),
        ("mock_response_400", VikunjaBadRequestError),
        ("mock_response_500", VikunjaServerError),
        ("mock_response_502", VikunjaServerError),
    ],
)
def test_http_error_status_maps_to_typed_exception(
    mock_vikunja_urlopen, scenario, exc_class
) -> None:
    mock_vikunja_urlopen(scenario)
    with pytest.raises(exc_class) as info:
        _client().get("/tasks")
    assert info.value.path == "/tasks"
    assert info.value.status is not None


def test_unhandled_http_status_maps_to_base_http_error(mock_vikunja_urlopen) -> None:
    mock_vikunja_urlopen("mock_response_418")
    with pytest.raises(VikunjaHttpError) as info:
        _client().get("/tea")
    assert type(info.value) is VikunjaHttpError
    assert info.value.status == 418


def test_socket_timeout_maps_to_timeout_error(mock_vikunja_urlopen) -> None:
    mock_vikunja_urlopen("mock_response_timeout")
    with pytest.raises(VikunjaTimeoutError) as info:
        _client().get("/tasks")
    assert info.value.path == "/tasks"
    assert info.value.status is None


def test_url_error_timeout_maps_to_timeout_error(mock_vikunja_urlopen) -> None:
    mock_vikunja_urlopen("mock_response_url_error_timeout")
    with pytest.raises(VikunjaTimeoutError):
        _client().get("/tasks")


def test_url_error_non_timeout_maps_to_server_error(mock_vikunja_urlopen) -> None:
    mock_vikunja_urlopen("mock_response_url_error_other")
    with pytest.raises(VikunjaServerError) as info:
        _client().get("/tasks")
    assert info.value.status is None


def test_non_json_body_maps_to_server_error(mock_vikunja_urlopen) -> None:
    mock_vikunja_urlopen("mock_response_non_json")
    with pytest.raises(VikunjaServerError) as info:
        _client().get("/tasks")
    assert info.value.status == 200


# ---------------------------------------------------------------------------
# Redaction policy (FR-012)
# ---------------------------------------------------------------------------


def test_str_exc_redacts_response_body(mock_vikunja_urlopen) -> None:
    mock_vikunja_urlopen("mock_response_401")
    with pytest.raises(VikunjaAuthError) as info:
        _client().get("/projects/13/tasks")
    rendered = str(info.value)
    assert "Invalid token" not in rendered
    assert "401" not in rendered
    assert rendered == "VikunjaAuthError: /projects/13/tasks"


def test_str_exc_does_not_include_status_for_timeout(mock_vikunja_urlopen) -> None:
    mock_vikunja_urlopen("mock_response_timeout")
    with pytest.raises(VikunjaTimeoutError) as info:
        _client().get("/tasks")
    rendered = str(info.value)
    assert rendered == "VikunjaTimeoutError: /tasks"


def test_verbose_message_includes_status_and_path(mock_vikunja_urlopen) -> None:
    mock_vikunja_urlopen("mock_response_404")
    with pytest.raises(VikunjaNotFoundError) as info:
        _client().get("/missing")
    verbose = info.value.verbose_message()
    assert "VikunjaNotFoundError" in verbose
    assert "/missing" in verbose
    assert "404" in verbose


def test_verbose_message_for_non_status_exception() -> None:
    exc = VikunjaTimeoutError(path="/tasks", status=None)
    verbose = exc.verbose_message()
    assert "VikunjaTimeoutError" in verbose
    assert "/tasks" in verbose
    assert "None" in verbose


def test_base_exception_can_be_caught_for_any_subclass(mock_vikunja_urlopen) -> None:
    mock_vikunja_urlopen("mock_response_500")
    with pytest.raises(VikunjaError):
        _client().get("/tasks")


# ---------------------------------------------------------------------------
# Per-call timeout override
# ---------------------------------------------------------------------------


def test_per_call_timeout_overrides_default(mock_vikunja_urlopen, monkeypatch) -> None:
    seen_timeouts: list[float] = []
    mock_vikunja_urlopen("mock_response_200_object")
    fake_urlopen = urllib.request.urlopen  # captured after fixture install

    def capturing(req, timeout=None):
        seen_timeouts.append(timeout)
        return fake_urlopen(req, timeout=timeout)

    monkeypatch.setattr("urllib.request.urlopen", capturing)
    _client(timeout=10.0).get("/tasks/7", timeout=2.5)
    assert seen_timeouts == [2.5]


def test_default_timeout_used_when_no_override(mock_vikunja_urlopen, monkeypatch) -> None:
    seen_timeouts: list[float] = []
    mock_vikunja_urlopen("mock_response_200_object")
    fake_urlopen = urllib.request.urlopen

    def capturing(req, timeout=None):
        seen_timeouts.append(timeout)
        return fake_urlopen(req, timeout=timeout)

    monkeypatch.setattr("urllib.request.urlopen", capturing)
    _client(timeout=7.5).get("/tasks/7")
    assert seen_timeouts == [7.5]
