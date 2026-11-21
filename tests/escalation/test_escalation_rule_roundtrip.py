"""Round-trip regression tests: escalation writes keep the recurrence rule (FR-006/014/020).

Mission felix-rrule-adaptation-01M7TKNX, WP04. A stateful fake Vikunja
(``urllib.request.urlopen`` replaced) serves the real v2 task body from
``tests.common.vikunja_v2_factory``. Any ``/api/v1`` request gets **405**,
which is what the live server answers to the pre-fix v1 task PATCH
(research.md R-005), so these tests fail on the pre-fix helper.
"""
from __future__ import annotations

import copy
import io
import json
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any, Self

import pytest

from scripts.common.et_datetime import parse_vikunja_instant
from scripts.escalation import record_completion as rc
from tests.common.vikunja_v2_factory import make_task, strip_rule, with_reminder

TASK_ID = 14
PROJECT_ID = 2
BASE_URL = "https://vikunja.test/api/v1"
V2_TASK_URL = f"https://vikunja.test/api/v2/tasks/{TASK_ID}"

Transition = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


class _Response:
    def __init__(self, body: bytes, status: int = 200) -> None:
        self._body = body
        self.status = status

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def _http_error(url: str, code: int, body: bytes = b"") -> urllib.error.HTTPError:
    return urllib.error.HTTPError(url, code, "fake", None, io.BytesIO(body))  # type: ignore[arg-type]


class FakeVikunja:
    """Minimal stateful stand-in for the vikunja-harness ``d7e202228`` task API."""

    def __init__(
        self,
        task: dict[str, Any],
        on_patch: Transition,
        *,
        patch_returns_304: bool = False,
        preview: dict[str, Any] | None = None,
    ) -> None:
        self.task = copy.deepcopy(task)
        self.on_patch = on_patch
        self.patch_returns_304 = patch_returns_304
        self.preview = preview
        self.requests: list[tuple[str, str, Any]] = []

    def __call__(self, req: urllib.request.Request, timeout: float | None = None) -> _Response:
        method = req.get_method()
        url = req.full_url
        body = json.loads(req.data.decode("utf-8")) if req.data else None
        self.requests.append((method, url, body))
        if "/api/v1/" in url:
            raise _http_error(url, 405, b'{"message":"Method Not Allowed"}')
        if url == V2_TASK_URL and method == "GET":
            return _Response(json.dumps(self.task).encode())
        if url == V2_TASK_URL and method == "PATCH":
            self.task = self.on_patch(copy.deepcopy(self.task), body)
            if self.patch_returns_304:
                raise _http_error(url, 304)
            return _Response(json.dumps(self.task).encode())
        if url.endswith("/api/v2/tasks/occurrences/preview") and method == "POST":
            if self.preview is None:
                raise _http_error(url, 401, b'{"code":11,"message":"forbidden"}')
            return _Response(json.dumps(self.preview).encode())
        raise AssertionError(f"unexpected request {method} {url}")

    @property
    def patches(self) -> list[tuple[str, Any]]:
        return [(url, body) for method, url, body in self.requests if method == "PATCH"]


# ---------------------------------------------------------------------------
# Server transitions (pkg/models/tasks.go semantics)
# ---------------------------------------------------------------------------


def advance_one_day(task: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    """A normal completion of a repeating task: stays open, due date advances."""
    assert body == {"done": True}
    task["done"] = False
    task["due_date"] = "2026-11-21T04:59:59Z"
    return task


def count_exhausted(task: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    """COUNT=1: the task stays Done and the rule is cleared."""
    assert body == {"done": True}
    task["done"] = True
    task["repeat"] = None
    task.pop("repeats_rrule", None)
    return task


def done_rule_kept(task: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    """Done with the rule still present and no exhaustion expected: unexpected."""
    assert body == {"done": True}
    task["done"] = True
    return task


def apply_patch(task: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    task.update(body)
    return task


def reschedule_strips_rule(task: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    task.update(body)
    return strip_rule(task)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def jsonl_sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    sandbox = tmp_path / "escalation_state"
    sandbox.mkdir()
    monkeypatch.setattr(rc, "JSONL_STATE_DIR", sandbox)
    return sandbox


@pytest.fixture
def install(monkeypatch: pytest.MonkeyPatch) -> Callable[..., FakeVikunja]:
    def _install(task: dict[str, Any], on_patch: Transition, **kwargs: Any) -> FakeVikunja:
        fake = FakeVikunja(task, on_patch, **kwargs)
        monkeypatch.setattr(urllib.request, "urlopen", fake)
        return fake

    return _install


def _record(state: str, **params: Any) -> dict[str, Any]:
    record = {
        "domain": "escalation",
        "task_id": TASK_ID,
        "project_id": PROJECT_ID,
        "title": "Wake at 5:00 AM",
        "date": "2026-11-19",
        "state": state,
        "source": "kent_reply",
        "timestamp": "2026-11-19T12:00:00+00:00",
        "note": None,
    }
    record.update(params)
    return record


def _jsonl(sandbox: Path) -> list[dict[str, Any]]:
    path = sandbox / f"project-{PROJECT_ID}-escalation-history.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _assert_v2_only(fake: FakeVikunja) -> None:
    assert fake.requests, "no request was made"
    for method, url, _ in fake.requests:
        assert "/api/v1/" not in url, f"v1 request issued: {method} {url}"


# ---------------------------------------------------------------------------
# done
# ---------------------------------------------------------------------------


def test_done_on_recurring_patches_v2_and_records_advanced(
    install, jsonl_sandbox, tmp_token_file
) -> None:
    fake = install(make_task(id=TASK_ID, project_id=PROJECT_ID), advance_one_day)

    result = rc.record_event(_record("done"), base_url=BASE_URL, token_path=tmp_token_file)

    assert fake.patches == [(V2_TASK_URL, {"done": True})]
    assert result["vikunja_actions"] == ["task_PATCH_done", "outcome:advanced"]
    assert result["outcome"] == "advanced"
    assert "anomaly" not in result
    assert fake.task["repeat"] == {"freq": "daily", "interval": 1}
    [written] = _jsonl(jsonl_sandbox)
    assert written["state"] == "done"
    assert written["note"] is None
    _assert_v2_only(fake)


def test_done_on_count_one_records_series_ended(install, jsonl_sandbox, tmp_token_file) -> None:
    task = make_task(
        id=TASK_ID, project_id=PROJECT_ID, repeat={"freq": "daily", "interval": 1, "count": 1}
    )
    fake = install(task, count_exhausted)

    result = rc.record_event(_record("done"), base_url=BASE_URL, token_path=tmp_token_file)

    assert result["outcome"] == "series_ended"
    assert result["vikunja_actions"][-1] == "outcome:series_ended"
    assert len(_jsonl(jsonl_sandbox)) == 1
    _assert_v2_only(fake)


def test_done_304_rereads_before_classifying(install, jsonl_sandbox, tmp_token_file) -> None:
    fake = install(
        make_task(id=TASK_ID, project_id=PROJECT_ID), advance_one_day, patch_returns_304=True
    )

    result = rc.record_event(_record("done"), base_url=BASE_URL, token_path=tmp_token_file)

    assert result["outcome"] == "advanced"
    methods = [m for m, _, _ in fake.requests]
    assert methods == ["GET", "PATCH", "GET"]


def test_done_unexpected_writes_jsonl_with_note_then_exits_nonzero(
    install, jsonl_sandbox, tmp_token_file, monkeypatch, capsys
) -> None:
    fake = install(make_task(id=TASK_ID, project_id=PROJECT_ID), done_rule_kept)
    monkeypatch.setattr(rc, "_read_stdin_record", lambda: None)

    code = rc.main(
        [
            "--task-id", str(TASK_ID), "--project-id", str(PROJECT_ID),
            "--title", "Wake at 5:00 AM", "--date", "2026-11-19",
            "--state", "done", "--source", "kent_reply",
            "--base-url", BASE_URL, "--token-path", str(tmp_token_file),
        ]
    )

    assert code == rc.EXIT_OUTCOME_UNEXPECTED
    assert code != 0
    [written] = _jsonl(jsonl_sandbox)
    assert written["state"] == "done"
    assert written["note"].startswith("vikunja outcome unexpected: ")
    err = capsys.readouterr().err
    assert "vikunja_outcome" in err and "unexpected" in err
    _assert_v2_only(fake)


def test_done_on_one_off_records_done_one_off(install, jsonl_sandbox, tmp_token_file) -> None:
    task = make_task(id=TASK_ID, project_id=PROJECT_ID, repeat=None)
    fake = install(task, done_rule_kept)

    result = rc.record_event(_record("done"), base_url=BASE_URL, token_path=tmp_token_file)

    assert fake.patches == [(V2_TASK_URL, {"done": True})]
    assert result["outcome"] == "done_one_off"
    assert "anomaly" not in result
    assert len(_jsonl(jsonl_sandbox)) == 1


# ---------------------------------------------------------------------------
# rescheduled
# ---------------------------------------------------------------------------


def test_reschedule_patches_only_due_date_and_keeps_rule(
    install, jsonl_sandbox, tmp_token_file
) -> None:
    fake = install(make_task(id=TASK_ID, project_id=PROJECT_ID), apply_patch)

    result = rc.record_event(
        _record("rescheduled", reschedule_to="2026-11-24"),
        base_url=BASE_URL,
        token_path=tmp_token_file,
    )

    assert fake.patches == [(V2_TASK_URL, {"due_date": "2026-11-24T23:59:59-05:00"})]
    assert result["vikunja_actions"] == ["task_PATCH_due_date"]
    assert fake.task["repeat"] == {"freq": "daily", "interval": 1}
    assert len(_jsonl(jsonl_sandbox)) == 1
    _assert_v2_only(fake)


def test_positive_control_reschedule_that_strips_rule_raises_and_writes_nothing(
    install, jsonl_sandbox, tmp_token_file
) -> None:
    fake = install(make_task(id=TASK_ID, project_id=PROJECT_ID), reschedule_strips_rule)

    with pytest.raises(rc.VikunjaError, match="rule changed by reschedule"):
        rc.record_event(
            _record("rescheduled", reschedule_to="2026-11-24"),
            base_url=BASE_URL,
            token_path=tmp_token_file,
        )

    assert _jsonl(jsonl_sandbox) == []
    _assert_v2_only(fake)


@pytest.mark.parametrize(
    ("state", "params", "transition"),
    [
        ("done", {}, advance_one_day),
        ("rescheduled", {"reschedule_to": "2026-11-24"}, apply_patch),
    ],
)
def test_no_v1_task_patch_is_ever_issued(
    install, jsonl_sandbox, tmp_token_file, state, params, transition
) -> None:
    """The v1 PATCH answered 405 on the live server (R-005); it must be gone."""
    fake = install(make_task(id=TASK_ID, project_id=PROJECT_ID), transition)

    rc.record_event(_record(state, **params), base_url=BASE_URL, token_path=tmp_token_file)

    assert not [r for r in fake.requests if r[0] == "PATCH" and "/api/v1/" in r[1]]
    _assert_v2_only(fake)


# ---------------------------------------------------------------------------
# Companion fields (FR-020): repeat-from-completion flag and reminders survive
# (review cycle 1, finding 3). Positive cases and corruption controls.
# ---------------------------------------------------------------------------


def _recompute_relative(task: dict[str, Any]) -> dict[str, Any]:
    """Move relative reminders with their anchor, as the server does."""
    for reminder in task.get("reminders") or []:
        anchor = parse_vikunja_instant(task.get(reminder.get("relative_to") or ""))
        if anchor is not None:
            reminder["reminder"] = (
                anchor + timedelta(seconds=reminder["relative_period"])
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
    return task


def _companion_task(**overrides: Any) -> dict[str, Any]:
    base = make_task(id=TASK_ID, project_id=PROJECT_ID, repeats_from_current_date=True, **overrides)
    return with_reminder(base, relative_to="due_date", relative_period=-3600)


def advance_moving_reminders(task: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    return _recompute_relative(advance_one_day(task, body))


def reschedule_moving_reminders(task: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    return _recompute_relative(apply_patch(task, body))


def drop_reminders(transition: Transition) -> Transition:
    def _t(task: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
        out = transition(task, body)
        out["reminders"] = None
        return out

    return _t


def reset_from_current(transition: Transition) -> Transition:
    def _t(task: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
        out = transition(task, body)
        out["repeats_from_current_date"] = False
        return out

    return _t


def test_done_keeps_flag_and_moved_reminder(install, jsonl_sandbox, tmp_token_file) -> None:
    task = _companion_task()
    before_reminder = task["reminders"][0]["reminder"]
    fake = install(task, advance_moving_reminders)

    result = rc.record_event(_record("done"), base_url=BASE_URL, token_path=tmp_token_file)

    assert result["outcome"] == "advanced"
    assert "anomaly" not in result
    assert fake.task["repeats_from_current_date"] is True
    [reminder] = fake.task["reminders"]
    assert reminder["reminder"] != before_reminder  # legitimately moved
    assert (reminder["relative_to"], reminder["relative_period"]) == ("due_date", -3600)


@pytest.mark.parametrize(
    ("corrupt", "lost"),
    [(drop_reminders, "reminders"), (reset_from_current, "repeats_from_current_date")],
)
def test_done_control_lost_companion_field_is_unexpected(
    install, jsonl_sandbox, tmp_token_file, corrupt, lost
) -> None:
    install(_companion_task(), corrupt(advance_moving_reminders))

    result = rc.record_event(_record("done"), base_url=BASE_URL, token_path=tmp_token_file)

    assert result["outcome"] == "unexpected"
    assert f"companion fields changed: {lost}" in result["anomaly"]
    [written] = _jsonl(jsonl_sandbox)  # Kent said done: the record is kept
    assert lost in written["note"]


def test_reschedule_keeps_flag_and_moved_reminder(install, jsonl_sandbox, tmp_token_file) -> None:
    fake = install(_companion_task(), reschedule_moving_reminders)

    rc.record_event(
        _record("rescheduled", reschedule_to="2026-11-24"),
        base_url=BASE_URL,
        token_path=tmp_token_file,
    )

    assert fake.task["repeats_from_current_date"] is True
    assert len(fake.task["reminders"]) == 1
    assert len(_jsonl(jsonl_sandbox)) == 1


@pytest.mark.parametrize(
    ("corrupt", "lost"),
    [(drop_reminders, "reminders"), (reset_from_current, "repeats_from_current_date")],
)
def test_reschedule_control_lost_companion_field_raises_without_jsonl(
    install, jsonl_sandbox, tmp_token_file, corrupt, lost
) -> None:
    install(_companion_task(), corrupt(reschedule_moving_reminders))

    with pytest.raises(rc.VikunjaError, match=f"companion fields changed by reschedule.*{lost}"):
        rc.record_event(
            _record("rescheduled", reschedule_to="2026-11-24"),
            base_url=BASE_URL,
            token_path=tmp_token_file,
        )

    assert _jsonl(jsonl_sandbox) == []


# ---------------------------------------------------------------------------
# Finite series (contracts/vikunja-client-v2.md test obligations)
# ---------------------------------------------------------------------------


def advance_decrementing_count(task: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    task = advance_one_day(task, body)
    task["repeat"] = {**task["repeat"], "count": task["repeat"]["count"] - 1}
    task["repeats_rrule"] = "FREQ=DAILY;INTERVAL=1;COUNT=1"
    return task


def test_done_count_two_to_one_is_advanced(install, jsonl_sandbox, tmp_token_file) -> None:
    task = make_task(
        id=TASK_ID, project_id=PROJECT_ID, repeat={"freq": "daily", "interval": 1, "count": 2}
    )
    fake = install(task, advance_decrementing_count)

    result = rc.record_event(_record("done"), base_url=BASE_URL, token_path=tmp_token_file)

    assert result["outcome"] == "advanced"
    assert fake.task["repeat"]["count"] == 1
    assert len(_jsonl(jsonl_sandbox)) == 1


def test_done_until_passed_is_series_ended(install, jsonl_sandbox, tmp_token_file) -> None:
    rule = {"freq": "daily", "interval": 1, "until": "2026-11-20T04:59:59Z"}
    task = make_task(id=TASK_ID, project_id=PROJECT_ID, repeat=rule)
    fake = install(
        task, done_rule_kept, preview={"occurrences": [], "reason": "until_passed"}
    )

    result = rc.record_event(_record("done"), base_url=BASE_URL, token_path=tmp_token_file)

    assert result["outcome"] == "series_ended"
    assert fake.task["done"] is True and fake.task["repeat"] == rule
    previews = [b for m, u, b in fake.requests if u.endswith("/occurrences/preview")]
    assert len(previews) == 1 and previews[0]["repeats_from_current_date"] is False
    assert len(_jsonl(jsonl_sandbox)) == 1


def test_done_until_without_preview_evidence_is_unexpected(
    install, jsonl_sandbox, tmp_token_file
) -> None:
    """Control: Done with an UNTIL rule but preview refused (401) is not a normal end."""
    rule = {"freq": "daily", "interval": 1, "until": "2026-11-20T04:59:59Z"}
    install(make_task(id=TASK_ID, project_id=PROJECT_ID, repeat=rule), done_rule_kept)

    result = rc.record_event(_record("done"), base_url=BASE_URL, token_path=tmp_token_file)

    assert result["outcome"] == "unexpected"
    assert "exhaustion_expected=unknown" in result["anomaly"]


# ---------------------------------------------------------------------------
# Absolute reminders (review cycle 2, finding 1). The server moves an absolute
# reminder on completion as a companion of the due date
# (task_next_occurrence_engine.go:429-456, 576-592) and never on a reschedule.
# Expected instants below are written out literally, not computed by the code
# under test.
# ---------------------------------------------------------------------------

UNSET = "0001-01-01T00:00:00Z"


def _absolute(at: str) -> dict[str, Any]:
    return {"reminder": at, "relative_period": 0, "relative_to": ""}


def _with_absolute(at: str, **overrides: Any) -> dict[str, Any]:
    return make_task(id=TASK_ID, project_id=PROJECT_ID, reminders=[_absolute(at)], **overrides)


def complete_to(due: str, reminder: str) -> Transition:
    def _t(task: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
        assert body == {"done": True}
        task["done"] = False
        task["due_date"] = due
        task["reminders"] = [_absolute(reminder)]
        return task

    return _t


def reschedule_with_reminder(reminder: str) -> Transition:
    def _t(task: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
        task.update(body)
        task["reminders"] = [_absolute(reminder)]
        return task

    return _t


@pytest.mark.parametrize(
    ("overrides", "reminder", "new_due", "moved"),
    [
        # DAILY: wall-clock kept, one calendar day (EST, no DST change).
        ({}, "2026-11-19T14:00:00Z", "2026-11-21T04:59:59Z", "2026-11-20T14:00:00Z"),
        # DAILY across the 2026-11-01 DST end: 09:00 EDT -> 09:00 EST.
        (
            {"due_date": "2026-11-01T03:59:59Z"},
            "2026-10-31T13:00:00Z",
            "2026-11-02T04:59:59Z",
            "2026-11-01T14:00:00Z",
        ),
        # HOURLY: elapsed shift by the due-date delta.
        (
            {"due_date": "2026-11-19T15:00:00Z", "repeat": {"freq": "hourly", "interval": 1}},
            "2026-11-19T14:30:00Z",
            "2026-11-19T16:00:00Z",
            "2026-11-19T15:30:00Z",
        ),
    ],
)
def test_done_absolute_reminder_moved_as_server_moves_it(
    install, jsonl_sandbox, tmp_token_file, overrides, reminder, new_due, moved
) -> None:
    install(_with_absolute(reminder, **overrides), complete_to(new_due, moved))

    result = rc.record_event(_record("done"), base_url=BASE_URL, token_path=tmp_token_file)

    assert result["outcome"] == "advanced", result.get("anomaly")


@pytest.mark.parametrize(
    "corrupted",
    [
        UNSET,  # timestamp replaced by the unset sentinel
        "2026-11-19T14:00:00Z",  # not moved with the due date
        "2026-11-21T14:00:00Z",  # moved, but by the wrong amount
    ],
)
def test_done_control_absolute_reminder_damage_is_unexpected(
    install, jsonl_sandbox, tmp_token_file, corrupted
) -> None:
    install(
        _with_absolute("2026-11-19T14:00:00Z"),
        complete_to("2026-11-21T04:59:59Z", corrupted),
    )

    result = rc.record_event(_record("done"), base_url=BASE_URL, token_path=tmp_token_file)

    assert result["outcome"] == "unexpected"
    assert "companion fields changed: reminders" in result["anomaly"]
    assert len(_jsonl(jsonl_sandbox)) == 1


def test_reschedule_keeps_absolute_reminder_instant(install, jsonl_sandbox, tmp_token_file) -> None:
    install(_with_absolute("2026-11-19T14:00:00Z"), apply_patch)

    rc.record_event(
        _record("rescheduled", reschedule_to="2026-11-24"),
        base_url=BASE_URL,
        token_path=tmp_token_file,
    )

    assert len(_jsonl(jsonl_sandbox)) == 1


@pytest.mark.parametrize("corrupted", [UNSET, "2026-11-19T15:00:00Z"])
def test_reschedule_control_absolute_reminder_changed_raises_without_jsonl(
    install, jsonl_sandbox, tmp_token_file, corrupted
) -> None:
    install(_with_absolute("2026-11-19T14:00:00Z"), reschedule_with_reminder(corrupted))

    with pytest.raises(rc.VikunjaError, match="companion fields changed by reschedule.*reminders"):
        rc.record_event(
            _record("rescheduled", reschedule_to="2026-11-24"),
            base_url=BASE_URL,
            token_path=tmp_token_file,
        )

    assert _jsonl(jsonl_sandbox) == []
