"""Tests for the v2 seam of ``scripts.common.vikunja_client`` (WP02, #1111).

Contract: ``kitty-specs/felix-rrule-adaptation-01M7TKNX/contracts/vikunja-client-v2.md``
and the End-series recovery contract in ``data-model.md``.

Single-response cases use the shared ``mock_vikunja_urlopen`` fixture
(``tests/common/conftest.py``). Multi-step flows (``end_series``) need a
scripted server, so this module adds ``scripted_urlopen``: it patches
``urllib.request.urlopen`` with a queue of canned answers and records every
request. Task bodies come from the WP01 v2 factory.
"""
from __future__ import annotations

import http.client
import io
import json
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any, Self

import pytest

from scripts.common.vikunja_client import (
    WRITABLE_TASK_FIELDS,
    SeriesEndIncomplete,
    VikunjaAuthError,
    VikunjaBadRequestError,
    VikunjaClient,
    VikunjaError,
    VikunjaNotFoundError,
    VikunjaServerError,
    VikunjaTimeoutError,
)
from tests.common.vikunja_v2_factory import make_task, strip_rule, with_reminder

TEST_BASE_URL = "https://vikunja.test/api/v1"
V2 = "https://vikunja.test/api/v2"
TEST_TOKEN = "secret-token-v2-do-not-leak"
MERGE_PATCH = "application/merge-patch+json"


def _client() -> VikunjaClient:
    return VikunjaClient(base_url=TEST_BASE_URL, token=TEST_TOKEN)


# ---------------------------------------------------------------------------
# Scripted fake server
# ---------------------------------------------------------------------------


class _Resp:
    def __init__(
        self,
        body: bytes,
        *,
        truncate: bool = False,
        read_error: BaseException | None = None,
    ) -> None:
        self._buf = io.BytesIO(body)
        self._truncate = truncate
        self._read_error = read_error

    def read(self) -> bytes:
        if self._truncate:
            # The server committed and began answering; the body was cut off.
            raise http.client.IncompleteRead(b'{"id": 5, "do', 400)
        if self._read_error is not None:
            raise self._read_error
        return self._buf.read()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self._buf.close()


def _encode(body: Any) -> bytes:
    if body is None:
        return b""
    if isinstance(body, bytes):
        return body
    if isinstance(body, str):
        return body.encode("utf-8")
    return json.dumps(body).encode("utf-8")


TIMEOUT = object()  # queue marker: raise socket.timeout for this request
TRUNCATED = object()  # queue marker: 200 whose body read raises IncompleteRead
RESET = object()  # queue marker: connection reset after the request was sent
CLOSED_READ = object()  # queue marker: 200 whose read raises ValueError (closed file)

#: Bodies json.loads cannot decode (review cycle 2): invalid UTF-8, a UTF-16
#: BOM with an odd tail, and nesting deep enough for RecursionError.
INVALID_UTF8 = b'{"id": 5, "done": true, "title": "\xc3\x28"}'
BAD_UTF16 = b"\xff\xfe{"
DEEP_NESTING = b"[" * 100_000


@pytest.fixture
def scripted_urlopen(monkeypatch) -> Callable[..., list[urllib.request.Request]]:
    """Install a fake ``urlopen`` answering from a queue of ``(status, body)``.

    An entry may be ``TIMEOUT`` to raise ``socket.timeout``, ``TRUNCATED``
    for a 200 whose body read raises ``http.client.IncompleteRead``, or
    ``RESET`` to raise ``ConnectionResetError``. Status >= 300
    raises ``HTTPError`` the way urllib does (urllib raises for 304 too).
    Running out of answers fails the test loudly.
    """

    def install(*answers: Any) -> list[urllib.request.Request]:
        queue = list(answers)
        calls: list[urllib.request.Request] = []

        def fake(req, timeout=None):
            calls.append(req)
            if not queue:
                # pytest.fail raises a BaseException, so the client's broad
                # v2 handler cannot swallow it as a "transport error".
                pytest.fail(f"unexpected request {req.get_method()} {req.full_url}")
            answer = queue.pop(0)
            if answer is TIMEOUT:
                raise TimeoutError("simulated timeout")
            if answer is TRUNCATED:
                return _Resp(b"", truncate=True)
            if answer is RESET:
                raise ConnectionResetError("simulated reset")
            if answer is CLOSED_READ:
                return _Resp(b"", read_error=ValueError("I/O operation on closed file"))
            status, body = answer
            if status >= 300:
                raise urllib.error.HTTPError(
                    url=req.full_url,
                    code=status,
                    msg="error",
                    hdrs=None,  # type: ignore[arg-type]
                    fp=io.BytesIO(_encode(body)),
                )
            return _Resp(_encode(body))

        monkeypatch.setattr("urllib.request.urlopen", fake)
        return calls

    return install


def _body(req: urllib.request.Request) -> Any:
    return json.loads(req.data.decode("utf-8")) if req.data else None


def _assert_no_combined_end_body(calls: list[urllib.request.Request]) -> None:
    """R-001 hazard 3: no single request may carry both ``repeat`` and ``done``."""
    for req in calls:
        body = _body(req)
        if isinstance(body, dict):
            assert not ({"repeat", "done"} <= body.keys()), body


# ---------------------------------------------------------------------------
# T006 — v2 root and plumbing
# ---------------------------------------------------------------------------


def test_v2_base_url_is_derived_from_v1_base() -> None:
    assert _client().v2_base_url == V2
    trailing = VikunjaClient(base_url=TEST_BASE_URL + "/", token=TEST_TOKEN)
    assert trailing.v2_base_url == V2
    assert trailing.base_url == TEST_BASE_URL


def test_v1_requests_still_use_v1_root(mock_vikunja_urlopen) -> None:
    calls = mock_vikunja_urlopen("mock_response_200_object")
    _client().get_task(7)
    assert calls[0].full_url == f"{TEST_BASE_URL}/tasks/7"
    assert calls[0].get_header("Content-type") is None


def test_writable_task_fields_matches_contract() -> None:
    assert WRITABLE_TASK_FIELDS == frozenset(
        {
            "title", "description", "done", "due_date", "repeat", "repeats_rrule",
            "repeats_from_current_date", "priority", "start_date", "end_date",
            "hex_color", "percent_done", "project_id", "reminders", "is_favorite",
        }
    )


# ---------------------------------------------------------------------------
# T007 — patch_task
# ---------------------------------------------------------------------------


def test_patch_task_sends_exact_body_as_merge_patch_to_v2(scripted_urlopen) -> None:
    returned = make_task(id=5, due_date="2026-11-21T04:59:59Z")
    calls = scripted_urlopen((200, returned))
    changes = {"due_date": "2026-11-21T04:59:59Z"}
    result = _client().patch_task(5, changes)
    assert result == returned
    req = calls[0]
    assert req.get_method() == "PATCH"
    assert req.full_url == f"{V2}/tasks/5"
    assert req.get_header("Content-type") == MERGE_PATCH
    assert req.get_header("Authorization") == f"Bearer {TEST_TOKEN}"
    assert _body(req) == changes


def test_patch_task_304_returns_none(scripted_urlopen) -> None:
    scripted_urlopen((304, None))
    assert _client().patch_task(5, {"title": "same"}) is None


@pytest.mark.parametrize(
    "changes",
    [
        {"repeat": None},
        {"due_date": None},
        {"title": "x", "reminders": None},
        {"repeat": {"freq": "daily", "count": None}},
        {"reminders": [None]},
    ],
)
def test_patch_task_refuses_null_without_http(scripted_urlopen, changes) -> None:
    calls = scripted_urlopen()
    with pytest.raises(ValueError, match="null"):
        _client().patch_task(5, changes)
    assert calls == []


@pytest.mark.parametrize(
    "changes", [{}, {"bucket_id": 3}, {"repeat_after": 86400}, {"done": True, "id": 9}]
)
def test_patch_task_refuses_empty_or_unknown_keys(scripted_urlopen, changes) -> None:
    calls = scripted_urlopen()
    with pytest.raises(ValueError):
        _client().patch_task(5, changes)
    assert calls == []


def test_patch_task_private_allow_null_admits_only_named_key(scripted_urlopen) -> None:
    calls = scripted_urlopen((200, strip_rule(make_task(id=5))))
    _client().patch_task(5, {"repeat": None}, _allow_null=frozenset({"repeat"}))
    assert _body(calls[0]) == {"repeat": None}
    with pytest.raises(ValueError):
        _client().patch_task(
            5, {"due_date": None}, _allow_null=frozenset({"repeat"})
        )


def test_patch_task_refuses_clearing_rule_and_done_in_one_body(scripted_urlopen) -> None:
    calls = scripted_urlopen()
    with pytest.raises(ValueError, match="one body"):
        _client().patch_task(
            5, {"repeat": None, "done": True}, _allow_null=frozenset({"repeat"})
        )
    assert calls == []


def test_patch_task_404_maps_to_not_found(scripted_urlopen) -> None:
    scripted_urlopen((404, {"code": 3, "title": "Not Found"}))
    with pytest.raises(VikunjaNotFoundError):
        _client().patch_task(5, {"done": True})


def test_patch_task_401_maps_to_auth_error_without_token(scripted_urlopen) -> None:
    scripted_urlopen((401, {"code": 11, "message": f"bad {TEST_TOKEN}"}))
    with pytest.raises(VikunjaAuthError) as info:
        _client().patch_task(5, {"done": True})
    exc = info.value
    assert "tasks.update" in str(exc)
    assert TEST_TOKEN not in str(exc)
    assert TEST_TOKEN not in exc.verbose_message()
    assert exc.code == 11


def test_patch_task_non_dict_200_is_server_error(scripted_urlopen) -> None:
    scripted_urlopen((200, [1, 2]))
    with pytest.raises(VikunjaServerError):
        _client().patch_task(5, {"done": True})


# ---------------------------------------------------------------------------
# T009 — reads, create, occurrences, preview
# ---------------------------------------------------------------------------


def test_get_task_v2_reads_from_v2(scripted_urlopen) -> None:
    task = make_task(id=14)
    calls = scripted_urlopen((200, task))
    result = _client().get_task_v2(14)
    assert result["repeats_rrule"] == "FREQ=DAILY;INTERVAL=1"
    assert calls[0].get_method() == "GET"
    assert calls[0].full_url == f"{V2}/tasks/14"


def test_get_task_v2_401_names_read_permission(scripted_urlopen) -> None:
    scripted_urlopen((401, {"code": 11}))
    with pytest.raises(VikunjaAuthError, match="tasks.read_one"):
        _client().get_task_v2(14)


def test_create_task_v2_posts_with_rule_and_initial_time(scripted_urlopen) -> None:
    created = make_task(id=99, repeat={"freq": "weekly", "by_day": ["mo"]})
    calls = scripted_urlopen((200, created))
    result = _client().create_task_v2(
        2,
        {"title": "Gym", "repeats_from_current_date": False},
        rrule="FREQ=WEEKLY;BYDAY=MO",
        initial_due_time="07:30",
    )
    assert result == created
    req = calls[0]
    assert req.get_method() == "POST"
    assert req.full_url == f"{V2}/projects/2/tasks"
    assert req.get_header("Content-type") == "application/json"
    assert _body(req) == {
        "title": "Gym",
        "repeats_from_current_date": False,
        "repeats_rrule": "FREQ=WEEKLY;BYDAY=MO",
        "initial_due_time": "07:30",
    }


def test_create_task_v2_omits_unset_options(scripted_urlopen) -> None:
    calls = scripted_urlopen((200, make_task(id=99, repeat=None)))
    _client().create_task_v2(2, {"title": "One-off"})
    assert _body(calls[0]) == {"title": "One-off"}


def test_create_task_v2_refuses_none_and_conflicts(scripted_urlopen) -> None:
    calls = scripted_urlopen()
    with pytest.raises(ValueError):
        _client().create_task_v2(2, {"title": "x", "due_date": None})
    with pytest.raises(ValueError):
        _client().create_task_v2(2, {"title": "x", "repeats_rrule": "FREQ=DAILY"}, rrule="FREQ=DAILY")
    assert calls == []


def test_occurrences_gets_with_count(scripted_urlopen) -> None:
    answer = {"occurrences": ["2026-11-21T12:30:00Z"]}
    calls = scripted_urlopen((200, answer))
    assert _client().occurrences(14, count=1) == answer
    assert calls[0].get_method() == "GET"
    assert calls[0].full_url == f"{V2}/tasks/14/occurrences?count=1"


def test_occurrences_passes_reason_through(scripted_urlopen) -> None:
    answer = {"occurrences": [], "reason": "count_exhausted"}
    scripted_urlopen((200, answer))
    assert _client().occurrences(14, count=3)["reason"] == "count_exhausted"


@pytest.mark.parametrize("count", [0, 101, -1, True, 1.5])
def test_occurrences_validates_count_locally(scripted_urlopen, count) -> None:
    calls = scripted_urlopen()
    with pytest.raises(ValueError):
        _client().occurrences(14, count=count)
    assert calls == []


def test_occurrences_401_names_missing_permission(scripted_urlopen) -> None:
    scripted_urlopen((401, {"code": 11, "message": "missing permission"}))
    with pytest.raises(VikunjaAuthError) as info:
        _client().occurrences(14)
    assert "tasks.occurrences" in str(info.value)
    assert "tasks.occurrences_preview" not in str(info.value)
    assert TEST_TOKEN not in str(info.value)


def test_preview_occurrences_posts_body(scripted_urlopen) -> None:
    answer = {"occurrences": [], "timezone": "America/New_York", "evaluated_at": "x"}
    calls = scripted_urlopen((200, answer))
    result = _client().preview_occurrences(
        rrule="FREQ=DAILY", initial_due_time="07:30", count=1
    )
    assert result == answer
    req = calls[0]
    assert req.get_method() == "POST"
    assert req.full_url == f"{V2}/tasks/occurrences/preview"
    assert _body(req) == {
        "repeats_rrule": "FREQ=DAILY",
        "initial_due_time": "07:30",
        "timezone": "America/New_York",
        "repeats_from_current_date": False,
        "count": 1,
    }


def test_preview_occurrences_accepts_structured_repeat_and_due_date(scripted_urlopen) -> None:
    calls = scripted_urlopen((200, {"occurrences": []}))
    _client().preview_occurrences(
        repeat={"freq": "weekly", "by_day": ["mo"]},
        due_date="2026-11-23T12:00:00Z",
        repeats_from_current_date=True,
    )
    body = _body(calls[0])
    assert body["repeat"] == {"freq": "weekly", "by_day": ["mo"]}
    assert body["due_date"] == "2026-11-23T12:00:00Z"
    assert "repeats_rrule" not in body and "initial_due_time" not in body
    assert body["repeats_from_current_date"] is True
    assert body["count"] == 3


@pytest.mark.parametrize(
    "kwargs",
    [
        {"initial_due_time": "07:30"},
        {"rrule": "FREQ=DAILY", "repeat": {"freq": "daily"}, "initial_due_time": "07:30"},
        {"rrule": "FREQ=DAILY"},
        {"rrule": "FREQ=DAILY", "due_date": "2026-11-23T12:00:00Z", "initial_due_time": "07:30"},
        {"rrule": "FREQ=DAILY", "initial_due_time": "07:30", "count": 0},
    ],
)
def test_preview_occurrences_shape_errors_before_call(scripted_urlopen, kwargs) -> None:
    calls = scripted_urlopen()
    with pytest.raises(ValueError):
        _client().preview_occurrences(**kwargs)
    assert calls == []


@pytest.mark.parametrize("code", [2002, 2003])
def test_preview_occurrences_400_exposes_server_code(scripted_urlopen, code) -> None:
    scripted_urlopen((400, {"code": code, "title": "Bad Request", "detail": "bad"}))
    with pytest.raises(VikunjaBadRequestError) as info:
        _client().preview_occurrences(rrule="FREQ=NOPE", initial_due_time="07:30")
    assert info.value.code == code


def test_preview_occurrences_400_without_json_body_has_no_code(scripted_urlopen) -> None:
    scripted_urlopen((400, "not json"))
    with pytest.raises(VikunjaBadRequestError) as info:
        _client().preview_occurrences(rrule="FREQ=DAILY", initial_due_time="07:30")
    assert info.value.code is None


def test_preview_occurrences_401_names_preview_permission(scripted_urlopen) -> None:
    scripted_urlopen((401, {"code": 11}))
    with pytest.raises(VikunjaAuthError, match="tasks.occurrences_preview"):
        _client().preview_occurrences(rrule="FREQ=DAILY", initial_due_time="07:30")


def test_v2_timeout_maps_to_timeout_error(scripted_urlopen) -> None:
    scripted_urlopen(TIMEOUT)
    with pytest.raises(VikunjaTimeoutError):
        _client().get_task_v2(14)


def test_v2_304_on_get_is_not_swallowed(scripted_urlopen) -> None:
    # Only PATCH treats 304 as "unchanged"; anywhere else it stays an error.
    scripted_urlopen((304, None))
    with pytest.raises(VikunjaError):
        _client().get_task_v2(14)


# ---------------------------------------------------------------------------
# T008 — end_series (End-series recovery contract)
# ---------------------------------------------------------------------------

OPEN_RULE = make_task(id=5, done=False)
OPEN_NO_RULE = strip_rule(make_task(id=5, done=False))
DONE_RULE = make_task(id=5, done=True)
DONE_NO_RULE = strip_rule(make_task(id=5, done=True))


def _methods(calls: list[urllib.request.Request]) -> list[tuple[str, Any]]:
    return [(c.get_method(), _body(c)) for c in calls]


def test_end_series_open_with_rule_clears_then_completes(scripted_urlopen) -> None:
    calls = scripted_urlopen(
        (200, OPEN_RULE),
        (200, OPEN_NO_RULE),
        (200, OPEN_NO_RULE),
        (200, DONE_NO_RULE),
        (200, DONE_NO_RULE),
    )
    assert _client().end_series(5) == DONE_NO_RULE
    assert _methods(calls) == [
        ("GET", None),
        ("PATCH", {"repeat": None}),
        ("GET", None),
        ("PATCH", {"done": True}),
        ("GET", None),
    ]
    assert all(c.full_url == f"{V2}/tasks/5" for c in calls)
    _assert_no_combined_end_body(calls)


def test_end_series_open_without_rule_only_completes(scripted_urlopen) -> None:
    calls = scripted_urlopen((200, OPEN_NO_RULE), (200, DONE_NO_RULE), (200, DONE_NO_RULE))
    assert _client().end_series(5) == DONE_NO_RULE
    assert _methods(calls) == [("GET", None), ("PATCH", {"done": True}), ("GET", None)]


def test_end_series_done_without_rule_is_noop(scripted_urlopen) -> None:
    calls = scripted_urlopen((200, DONE_NO_RULE))
    assert _client().end_series(5) == DONE_NO_RULE
    assert _methods(calls) == [("GET", None)]


def test_end_series_done_with_rule_clears_rule_without_touching_done(scripted_urlopen) -> None:
    calls = scripted_urlopen((200, DONE_RULE), (200, DONE_NO_RULE), (200, DONE_NO_RULE))
    assert _client().end_series(5) == DONE_NO_RULE
    assert _methods(calls) == [("GET", None), ("PATCH", {"repeat": None}), ("GET", None)]
    _assert_no_combined_end_body(calls)


def test_end_series_304_on_each_step_still_verifies(scripted_urlopen) -> None:
    calls = scripted_urlopen(
        (200, OPEN_RULE),
        (304, None),
        (200, OPEN_NO_RULE),
        (304, None),
        (200, DONE_NO_RULE),
    )
    assert _client().end_series(5) == DONE_NO_RULE
    assert len(calls) == 5
    _assert_no_combined_end_body(calls)


def test_end_series_304_on_clear_with_rule_still_present_is_rule_reappeared(
    scripted_urlopen,
) -> None:
    scripted_urlopen((200, OPEN_RULE), (304, None), (200, OPEN_RULE))
    with pytest.raises(SeriesEndIncomplete) as info:
        _client().end_series(5)
    assert info.value.state == "rule_reappeared"


def test_end_series_rule_reappears_before_step_two(scripted_urlopen) -> None:
    calls = scripted_urlopen((200, OPEN_RULE), (200, OPEN_NO_RULE), (200, OPEN_RULE))
    with pytest.raises(SeriesEndIncomplete) as info:
        _client().end_series(5)
    assert info.value.task_id == 5
    assert info.value.state == "rule_reappeared"
    # Never sent done=true onto a task that has a rule again.
    assert all(_body(c) != {"done": True} for c in calls)


def test_end_series_error_after_step_one_is_rule_cleared_not_done(scripted_urlopen) -> None:
    # A 5xx at step 2 is uncertain: re-read, and the task is still open.
    calls = scripted_urlopen(
        (200, OPEN_RULE),
        (200, OPEN_NO_RULE),
        (200, OPEN_NO_RULE),
        (500, "boom"),
        (200, OPEN_NO_RULE),
    )
    with pytest.raises(SeriesEndIncomplete) as info:
        _client().end_series(5)
    assert info.value.state == "rule_cleared_not_done"
    assert isinstance(info.value.__cause__, VikunjaServerError)
    assert len(calls) == 5


def test_end_series_refusal_after_step_one_is_rule_cleared_not_done(scripted_urlopen) -> None:
    # A 4xx at step 2 is a definite refusal: no re-read needed.
    calls = scripted_urlopen(
        (200, OPEN_RULE),
        (200, OPEN_NO_RULE),
        (200, OPEN_NO_RULE),
        (403, {"code": 4}),
    )
    with pytest.raises(SeriesEndIncomplete) as info:
        _client().end_series(5)
    assert info.value.state == "rule_cleared_not_done"
    assert len(calls) == 4


def test_end_series_readback_failure_after_step_one(scripted_urlopen) -> None:
    scripted_urlopen((200, OPEN_RULE), (200, OPEN_NO_RULE), (404, None))
    with pytest.raises(SeriesEndIncomplete) as info:
        _client().end_series(5)
    assert info.value.state == "rule_cleared_not_done"
    assert isinstance(info.value.__cause__, VikunjaNotFoundError)


def test_end_series_refusal_at_step_one_propagates_unwrapped(scripted_urlopen) -> None:
    # A 4xx refusal means nothing was written: no re-read, no partial progress.
    calls = scripted_urlopen((200, OPEN_RULE), (403, {"code": 4}))
    with pytest.raises(VikunjaError) as info:
        _client().end_series(5)
    assert not isinstance(info.value, SeriesEndIncomplete)
    assert info.value.status == 403
    assert len(calls) == 2


def test_end_series_5xx_at_step_one_reread_unchanged_reraises(scripted_urlopen) -> None:
    # Uncertain write; the re-read shows the rule kept, so nothing changed.
    calls = scripted_urlopen((200, OPEN_RULE), (500, "boom"), (200, OPEN_RULE))
    with pytest.raises(VikunjaServerError) as info:
        _client().end_series(5)
    assert not isinstance(info.value, SeriesEndIncomplete)
    assert len(calls) == 3


# --- Commit-then-fail: the write lands, its response does not (review cycle 1)

_BROKEN_RESPONSES = [
    pytest.param((200, "<html>proxy page</html>"), id="non-json-200"),
    pytest.param((200, [1, 2]), id="non-object-200"),
    pytest.param(TRUNCATED, id="incomplete-read"),
    pytest.param(RESET, id="connection-reset"),
    pytest.param((502, "Bad Gateway"), id="502-after-commit"),
    pytest.param((200, INVALID_UTF8), id="invalid-utf8"),
    pytest.param((200, BAD_UTF16), id="bad-utf16"),
    pytest.param((200, DEEP_NESTING), id="deep-nesting"),
    pytest.param(CLOSED_READ, id="closed-file-read"),
]
# A malformed task in a *write* response is not listed: end_series never uses
# that body (it verifies with its own read), so it lives in _BROKEN_READS.

#: Recovery/readback answers that must end as SeriesEndIncomplete, never escape.
_BROKEN_READS = [
    pytest.param(TRUNCATED, id="incomplete-read"),
    pytest.param((200, INVALID_UTF8), id="invalid-utf8"),
    pytest.param((200, BAD_UTF16), id="bad-utf16"),
    pytest.param((200, DEEP_NESTING), id="deep-nesting"),
    pytest.param(CLOSED_READ, id="closed-file-read"),
    pytest.param((200, "<html/>"), id="non-json"),
    pytest.param((200, {**OPEN_NO_RULE, "repeat": "daily"}), id="malformed-repeat-str"),
    pytest.param((200, {**OPEN_NO_RULE, "repeat": ["x"]}), id="malformed-repeat-list"),
    # WP02 arbiter (fixed in WP08): a falsy non-mapping ``repeat`` beside a
    # live rule text must not read as "no rule" (that would let end_series
    # call a live series ended). One entry per falsy shape.
    *[
        pytest.param(
            (200, {**OPEN_NO_RULE, "repeat": falsy, "repeats_rrule": "FREQ=DAILY;INTERVAL=1"}),
            id=f"falsy-repeat-{name}-with-rrule",
        )
        for name, falsy in (("empty-list", []), ("false", False), ("zero", 0), ("empty-str", ""))
    ],
    pytest.param(
        (200, {**OPEN_NO_RULE, "repeat": None, "repeats_rrule": "FREQ=DAILY;INTERVAL=1"}),
        id="null-repeat-with-rrule",
    ),
    pytest.param(
        (200, {**{k: v for k, v in OPEN_NO_RULE.items() if k != "repeat"},
               "repeats_rrule": "FREQ=DAILY;INTERVAL=1"}),
        id="absent-repeat-with-rrule",
    ),
    pytest.param(
        (200, {**OPEN_RULE, "repeats_rrule": "FREQ=WEEKLY;INTERVAL=3"}),
        id="repeat-and-rrule-disagree",
    ),
    pytest.param((200, {**OPEN_RULE, "repeats_rrule": ""}), id="rule-with-empty-rrule"),
    pytest.param(
        (200, {k: v for k, v in OPEN_RULE.items() if k != "repeats_rrule"}),
        id="rule-without-rrule",
    ),
    pytest.param((200, {**OPEN_NO_RULE, "repeats_rrule": 5}), id="rrule-not-a-string"),
]


@pytest.mark.parametrize("broken", _BROKEN_RESPONSES)
def test_end_series_step_one_commits_then_response_fails_resumes(
    scripted_urlopen, broken
) -> None:
    calls = scripted_urlopen(
        (200, OPEN_RULE),
        broken,  # rule clear committed server-side
        (200, OPEN_NO_RULE),  # re-read shows it
        (200, DONE_NO_RULE),
        (200, DONE_NO_RULE),
    )
    assert _client().end_series(5) == DONE_NO_RULE
    assert _methods(calls) == [
        ("GET", None),
        ("PATCH", {"repeat": None}),
        ("GET", None),
        ("PATCH", {"done": True}),
        ("GET", None),
    ]
    _assert_no_combined_end_body(calls)


@pytest.mark.parametrize("broken", _BROKEN_RESPONSES)
def test_end_series_step_one_commits_then_response_fails_reread_fails(
    scripted_urlopen, broken
) -> None:
    scripted_urlopen((200, OPEN_RULE), broken, TRUNCATED)
    with pytest.raises(SeriesEndIncomplete) as info:
        _client().end_series(5)
    assert info.value.state == "unknown"


@pytest.mark.parametrize("broken", _BROKEN_RESPONSES)
def test_end_series_step_two_commits_then_response_fails_verifies_end(
    scripted_urlopen, broken
) -> None:
    calls = scripted_urlopen(
        (200, OPEN_RULE),
        (200, OPEN_NO_RULE),
        (200, OPEN_NO_RULE),
        broken,  # done=true committed server-side
        (200, DONE_NO_RULE),  # re-read shows the series ended
    )
    assert _client().end_series(5) == DONE_NO_RULE
    assert len(calls) == 5


@pytest.mark.parametrize("broken", _BROKEN_RESPONSES)
def test_end_series_step_two_response_fails_task_still_open(
    scripted_urlopen, broken
) -> None:
    scripted_urlopen(
        (200, OPEN_RULE), (200, OPEN_NO_RULE), (200, OPEN_NO_RULE), broken, (200, OPEN_NO_RULE)
    )
    with pytest.raises(SeriesEndIncomplete) as info:
        _client().end_series(5)
    assert info.value.state == "rule_cleared_not_done"


@pytest.mark.parametrize("broken", _BROKEN_RESPONSES)
def test_end_series_step_two_response_fails_reread_fails(scripted_urlopen, broken) -> None:
    scripted_urlopen(
        (200, OPEN_RULE), (200, OPEN_NO_RULE), (200, OPEN_NO_RULE), broken, RESET
    )
    with pytest.raises(SeriesEndIncomplete) as info:
        _client().end_series(5)
    assert info.value.state == "unknown"


@pytest.mark.parametrize("broken", _BROKEN_RESPONSES)
def test_end_series_open_no_rule_done_commits_then_response_fails(
    scripted_urlopen, broken
) -> None:
    scripted_urlopen((200, OPEN_NO_RULE), broken, (200, DONE_NO_RULE))
    assert _client().end_series(5) == DONE_NO_RULE


@pytest.mark.parametrize("broken", _BROKEN_RESPONSES)
def test_end_series_done_rule_clear_commits_then_response_fails(
    scripted_urlopen, broken
) -> None:
    scripted_urlopen((200, DONE_RULE), broken, (200, DONE_NO_RULE))
    assert _client().end_series(5) == DONE_NO_RULE


@pytest.mark.parametrize("bad_read", _BROKEN_READS)
def test_end_series_step_one_recovery_read_broken_is_unknown(scripted_urlopen, bad_read) -> None:
    # Rule clear times out, and the recovery read itself is undecodable.
    scripted_urlopen((200, OPEN_RULE), TIMEOUT, bad_read)
    with pytest.raises(SeriesEndIncomplete) as info:
        _client().end_series(5)
    assert info.value.state == "unknown"


@pytest.mark.parametrize("bad_read", _BROKEN_READS)
def test_end_series_step_two_recovery_read_broken_is_unknown(scripted_urlopen, bad_read) -> None:
    scripted_urlopen(
        (200, OPEN_RULE), (200, OPEN_NO_RULE), (200, OPEN_NO_RULE), TIMEOUT, bad_read
    )
    with pytest.raises(SeriesEndIncomplete) as info:
        _client().end_series(5)
    assert info.value.state == "unknown"


@pytest.mark.parametrize("bad_read", _BROKEN_READS)
def test_end_series_readback_after_rule_clear_broken(scripted_urlopen, bad_read) -> None:
    # Clear PATCH returned 200; its verifying readback is undecodable.
    scripted_urlopen((200, OPEN_RULE), (200, OPEN_NO_RULE), bad_read)
    with pytest.raises(SeriesEndIncomplete) as info:
        _client().end_series(5)
    assert info.value.state == "rule_cleared_not_done"


@pytest.mark.parametrize("bad_read", _BROKEN_READS)
def test_end_series_final_readback_broken_is_unknown(scripted_urlopen, bad_read) -> None:
    scripted_urlopen(
        (200, OPEN_RULE), (200, OPEN_NO_RULE), (200, OPEN_NO_RULE), (200, DONE_NO_RULE), bad_read
    )
    with pytest.raises(SeriesEndIncomplete) as info:
        _client().end_series(5)
    assert info.value.state == "unknown"


def test_recurrence_shape_accepts_consistent_reads() -> None:
    """Control for the strict check: real server shapes pass."""
    from scripts.common.vikunja_client import _recurrence_shape_error

    assert OPEN_RULE["repeats_rrule"]  # factory derives the text from repeat
    for task in (OPEN_RULE, OPEN_NO_RULE, DONE_RULE, DONE_NO_RULE, OPEN_ORDINAL,
                 OPEN_READ_ONLY, {**OPEN_NO_RULE, "repeats_rrule": ""}):
        assert _recurrence_shape_error(task) is None


# --- Server-shaped rules the strict check must accept (review cycle 1) -------

#: Ordinal weekdays as d7e202228 serves them: structured ``by_day`` via
#: ``fmt.Sprintf("%d%s")`` (task_repeat.go:556-562, so ``1mo`` / ``-1fr``), and
#: the stored rule text with its own spelling (``+1MO``).
_ORDINAL_REPEAT = {"freq": "monthly", "interval": 1, "by_day": ["1mo", "-1fr"]}
OPEN_ORDINAL = make_task(
    id=5, done=False, repeat=_ORDINAL_REPEAT,
    repeats_rrule="FREQ=MONTHLY;INTERVAL=1;BYDAY=+1MO,-1FR",
)
#: A rule the structured form cannot hold: the server marks the projection
#: read_only (task_repeat.go:63, projectionLoses at :449) and supports clearing
#: it with repeat: null. The text holds BYEASTER, unknown to the local parser.
_EASTER_REPEAT = {"freq": "yearly", "interval": 1, "read_only": True}
OPEN_READ_ONLY = make_task(
    id=5, done=False, repeat=_EASTER_REPEAT, repeats_rrule="FREQ=YEARLY;BYEASTER=0"
)


@pytest.mark.parametrize(
    "task", [OPEN_ORDINAL, OPEN_READ_ONLY], ids=["ordinal-by-day", "read-only-byeaster"]
)
def test_end_series_clears_server_shaped_rules(scripted_urlopen, task) -> None:
    calls = scripted_urlopen(
        (200, task),
        (200, OPEN_NO_RULE),
        (200, OPEN_NO_RULE),
        (200, DONE_NO_RULE),
        (200, DONE_NO_RULE),
    )
    assert _client().end_series(5) == DONE_NO_RULE
    assert _methods(calls) == [
        ("GET", None),
        ("PATCH", {"repeat": None}),
        ("GET", None),
        ("PATCH", {"done": True}),
        ("GET", None),
    ]


@pytest.mark.parametrize(
    "task",
    [
        pytest.param({**OPEN_READ_ONLY, "repeats_rrule": ""}, id="read-only-empty-text"),
        pytest.param(
            {k: v for k, v in OPEN_READ_ONLY.items() if k != "repeats_rrule"},
            id="read-only-no-text",
        ),
        pytest.param(
            {**OPEN_READ_ONLY, "repeat": {"read_only": True}}, id="read-only-no-freq"
        ),
        pytest.param({**OPEN_READ_ONLY, "repeats_rrule": 7}, id="read-only-text-not-str"),
        pytest.param(
            {**OPEN_ORDINAL, "repeats_rrule": "FREQ=MONTHLY;INTERVAL=1;BYDAY=+2MO,-1FR"},
            id="ordinal-disagrees",
        ),
        pytest.param(
            {**OPEN_ORDINAL, "repeats_rrule": "FREQ=MONTHLY;INTERVAL=1;BYDAY=+1MO,+1FR"},
            id="ordinal-sign-disagrees",
        ),
    ],
)
def test_end_series_still_refuses_malformed_server_shaped_reads(
    scripted_urlopen, task
) -> None:
    calls = scripted_urlopen((200, task))
    with pytest.raises(VikunjaServerError) as info:
        _client().end_series(5)
    assert not isinstance(info.value, SeriesEndIncomplete)
    assert len(calls) == 1  # refused before any write


@pytest.mark.parametrize("bad_read", _BROKEN_READS)
def test_end_series_initial_read_broken_is_server_error(scripted_urlopen, bad_read) -> None:
    # Nothing written yet: a plain VikunjaServerError, not partial progress.
    calls = scripted_urlopen(bad_read)
    with pytest.raises(VikunjaServerError) as info:
        _client().end_series(5)
    assert not isinstance(info.value, SeriesEndIncomplete)
    assert len(calls) == 1


@pytest.mark.parametrize("body", [INVALID_UTF8, BAD_UTF16, DEEP_NESTING])
def test_v2_undecodable_body_maps_to_server_error_status_none(scripted_urlopen, body) -> None:
    scripted_urlopen((200, body))
    with pytest.raises(VikunjaServerError) as info:
        _client().patch_task(5, {"done": True})
    assert info.value.status is None
    assert TEST_TOKEN not in str(info.value)


def test_v2_error_body_too_deep_still_maps_http_error(scripted_urlopen) -> None:
    scripted_urlopen((400, DEEP_NESTING))
    with pytest.raises(VikunjaBadRequestError) as info:
        _client().preview_occurrences(rrule="FREQ=DAILY", initial_due_time="07:30")
    assert info.value.code is None


def test_v1_invalid_utf8_behaviour_unchanged(scripted_urlopen) -> None:
    # v1 still maps only JSONDecodeError; UnicodeDecodeError escapes raw.
    scripted_urlopen((200, INVALID_UTF8))
    with pytest.raises(UnicodeDecodeError):
        _client().get_task(14)


@pytest.mark.parametrize("broken", [TRUNCATED, RESET, CLOSED_READ])
def test_v2_transport_failure_maps_to_server_error(scripted_urlopen, broken) -> None:
    scripted_urlopen(broken)
    with pytest.raises(VikunjaServerError) as info:
        _client().get_task_v2(14)
    assert info.value.status is None
    assert TEST_TOKEN not in str(info.value)


@pytest.mark.parametrize(
    ("broken", "raw"),
    [(TRUNCATED, http.client.IncompleteRead), (RESET, ConnectionResetError)],
)
def test_v1_transport_failure_behaviour_unchanged(scripted_urlopen, broken, raw) -> None:
    scripted_urlopen(broken)
    with pytest.raises(raw):
        _client().get_task(14)


def test_end_series_initial_read_failure_propagates(scripted_urlopen) -> None:
    scripted_urlopen((404, None))
    with pytest.raises(VikunjaNotFoundError):
        _client().end_series(5)


def test_end_series_timeout_at_step_one_reread_shows_rule_cleared(scripted_urlopen) -> None:
    calls = scripted_urlopen(
        (200, OPEN_RULE),
        TIMEOUT,
        (200, OPEN_NO_RULE),
        (200, DONE_NO_RULE),
        (200, DONE_NO_RULE),
    )
    assert _client().end_series(5) == DONE_NO_RULE
    assert _methods(calls) == [
        ("GET", None),
        ("PATCH", {"repeat": None}),
        ("GET", None),
        ("PATCH", {"done": True}),
        ("GET", None),
    ]
    _assert_no_combined_end_body(calls)


def test_end_series_timeout_at_step_one_reread_shows_rule_kept(scripted_urlopen) -> None:
    # The write did not land: nothing changed, so the timeout surfaces as-is.
    scripted_urlopen((200, OPEN_RULE), TIMEOUT, (200, OPEN_RULE))
    with pytest.raises(VikunjaTimeoutError):
        _client().end_series(5)


def test_end_series_timeout_and_failed_reread_is_unknown(scripted_urlopen) -> None:
    scripted_urlopen((200, OPEN_RULE), TIMEOUT, TIMEOUT)
    with pytest.raises(SeriesEndIncomplete) as info:
        _client().end_series(5)
    assert info.value.state == "unknown"
    assert isinstance(info.value.__cause__, VikunjaTimeoutError)


def test_end_series_timeout_at_step_two_reread_shows_ended(scripted_urlopen) -> None:
    calls = scripted_urlopen(
        (200, OPEN_RULE),
        (200, OPEN_NO_RULE),
        (200, OPEN_NO_RULE),
        TIMEOUT,
        (200, DONE_NO_RULE),
    )
    assert _client().end_series(5) == DONE_NO_RULE
    assert len(calls) == 5


def test_end_series_timeout_at_step_two_reread_shows_not_done(scripted_urlopen) -> None:
    scripted_urlopen(
        (200, OPEN_RULE),
        (200, OPEN_NO_RULE),
        (200, OPEN_NO_RULE),
        TIMEOUT,
        (200, OPEN_NO_RULE),
    )
    with pytest.raises(SeriesEndIncomplete) as info:
        _client().end_series(5)
    assert info.value.state == "rule_cleared_not_done"


def test_end_series_timeout_at_step_two_failed_reread_is_unknown(scripted_urlopen) -> None:
    scripted_urlopen(
        (200, OPEN_RULE), (200, OPEN_NO_RULE), (200, OPEN_NO_RULE), TIMEOUT, (500, "x")
    )
    with pytest.raises(SeriesEndIncomplete) as info:
        _client().end_series(5)
    assert info.value.state == "unknown"


def test_end_series_timeout_on_open_no_rule_task_reread_unchanged(scripted_urlopen) -> None:
    scripted_urlopen((200, OPEN_NO_RULE), TIMEOUT, (200, OPEN_NO_RULE))
    with pytest.raises(VikunjaTimeoutError):
        _client().end_series(5)


def test_end_series_final_check_fails_when_server_reopens(scripted_urlopen) -> None:
    # done=true came back as open (server advanced a rule we could not see).
    scripted_urlopen((200, OPEN_NO_RULE), (200, OPEN_NO_RULE), (200, OPEN_NO_RULE))
    with pytest.raises(SeriesEndIncomplete) as info:
        _client().end_series(5)
    assert info.value.state == "not_ended"


def test_end_series_done_with_rule_that_will_not_clear(scripted_urlopen) -> None:
    scripted_urlopen((200, DONE_RULE), (200, DONE_RULE), (200, DONE_RULE))
    with pytest.raises(SeriesEndIncomplete) as info:
        _client().end_series(5)
    assert info.value.state == "rule_reappeared"


def test_series_end_incomplete_is_redacted_vikunja_error() -> None:
    exc = SeriesEndIncomplete(5, "rule_cleared_not_done")
    assert isinstance(exc, VikunjaError)
    assert exc.task_id == 5
    assert exc.state == "rule_cleared_not_done"
    assert "rule_cleared_not_done" in str(exc)
    with pytest.raises(ValueError):
        SeriesEndIncomplete(5, "bogus")


# ---------------------------------------------------------------------------
# T010 — guarded update_task_fields (v1 full-echo fallback)
# ---------------------------------------------------------------------------


def _fake_v1(client: VikunjaClient, current: dict) -> list[tuple[str, dict]]:
    posts: list[tuple[str, dict]] = []

    def fake_get(path, *, params=None, timeout=None):
        return json.loads(json.dumps(current))

    def fake_post(path, *, json=None, params=None, timeout=None):
        posts.append((path, json))
        return json

    client.get = fake_get  # type: ignore[assignment]
    client.post = fake_post  # type: ignore[assignment]
    return posts


NEW_SHAPE = with_reminder(
    make_task(id=42, repeat={"freq": "weekly", "by_day": ["mo", "we"]},
              repeats_from_current_date=True)
)


def test_update_task_fields_full_echo_keeps_new_shape_rule() -> None:
    client = _client()
    posts = _fake_v1(client, NEW_SHAPE)
    client.update_task_fields(42, {"title": "Renamed"})
    path, body = posts[0]
    assert path == "/tasks/42"
    assert body["title"] == "Renamed"
    assert body["repeat"] == NEW_SHAPE["repeat"]
    assert body["repeats_from_current_date"] is True
    assert body["reminders"] == NEW_SHAPE["reminders"]


@pytest.mark.parametrize(
    "changes",
    [
        {"repeat": None},
        {"repeat": {"freq": "daily", "interval": 1}},
        {"repeats_rrule": "FREQ=DAILY"},
        {"repeats_from_current_date": False},
        {"reminders": []},
        {"reminders": None},
    ],
)
def test_update_task_fields_refuses_destructive_change(changes) -> None:
    client = _client()
    posts = _fake_v1(client, NEW_SHAPE)
    with pytest.raises(ValueError, match="allow_rule_change"):
        client.update_task_fields(42, changes)
    assert posts == []


def test_update_task_fields_override_allows_rule_change() -> None:
    client = _client()
    posts = _fake_v1(client, NEW_SHAPE)
    client.update_task_fields(42, {"repeat": None}, allow_rule_change=True)
    assert posts[0][1]["repeat"] is None


def test_update_task_fields_allows_equivalent_rule_spelling() -> None:
    client = _client()
    posts = _fake_v1(client, NEW_SHAPE)
    client.update_task_fields(
        42, {"repeat": {"freq": "WEEKLY", "by_day": ["MO", "WE"], "interval": 1}}
    )
    assert len(posts) == 1


def test_update_task_fields_unguarded_on_plain_task() -> None:
    client = _client()
    plain = strip_rule(make_task(id=42))
    posts = _fake_v1(client, plain)
    client.update_task_fields(42, {"repeat": {"freq": "daily"}})
    assert posts[0][1]["repeat"] == {"freq": "daily"}
