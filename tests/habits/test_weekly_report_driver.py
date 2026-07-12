"""Unit tests for ``scripts.habits.weekly_report_driver`` (mission WP03, #723).

Fully offline: the report helper, the ``openclaw message send`` effect,
the clock, and the tick-state path are all injected as fakes — no
subprocess, no network, no LLM turn.

Coverage groups (per ``contracts/weekly_report_driver.md`` +
``contracts/post-plan-review-resolutions.md`` C1/C2/H4):

- Happy path: helper body delivered verbatim after attribution;
  ``status=success``, ``delivery_confirmed=true``.
- Helper failure: no send attempted; ``status=failure``; non-zero exit.
- Send result without ``messageId``: not confirmed; ``status=failure``;
  non-zero exit (FR-006 — never claim delivery that did not happen).
- Malformed JSON from send: not confirmed; failure tick.
- ``dryRun=true`` on an otherwise "successful" send: not confirmed.
- ``--self-test``: writes a fresh tick to the SEPARATE self-test tick path
  (never the production ``last-tick.json``), calls send with the dry-run
  flag, never invokes a real send.
- ``--dry-run``: no state written, no send at all.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.habits import weekly_report_driver as driver


FIXED_NOW = datetime(2026, 7, 13, 6, 0, 0, tzinfo=timezone.utc)


def _now() -> datetime:
    return FIXED_NOW


def _ok_helper(body: str = "Weekly Habit Report\n\nAll good.") -> driver.RunHelper:
    def _helper() -> driver.HelperResult:
        return driver.HelperResult(ok=True, report_body=body)

    return _helper


def _failing_helper(error: str = "VikunjaError: /projects/1/tasks") -> driver.RunHelper:
    def _helper() -> driver.HelperResult:
        return driver.HelperResult(ok=False, error=error)

    return _helper


def _confirmed_send_result() -> driver.SendResult:
    payload = {
        "messageId": "msg-123",
        "dryRun": False,
        "payload": {"result": {"messageId": "msg-123", "runId": "run-1", "dryRun": False}},
    }
    return driver.SendResult(exit_code=0, stdout=json.dumps(payload), stderr="")


def _read_tick(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Happy path.
# --------------------------------------------------------------------------- #
def test_happy_path_delivers_and_confirms(tmp_path: Path) -> None:
    body = "Weekly Habit Report\n\nMorning Run: 6/7\nStretch: 7/7\n"
    calls: list[tuple[str, bool]] = []

    def _send(message: str, dry_run: bool) -> driver.SendResult:
        calls.append((message, dry_run))
        return _confirmed_send_result()

    tick_path = tmp_path / "last-tick.json"
    exit_code = driver.run(
        mode="run",
        run_helper=_ok_helper(body),
        send=_send,
        now=_now,
        tick_path=tick_path,
    )

    assert exit_code == 0
    assert len(calls) == 1
    sent_message, dry_run_flag = calls[0]
    assert dry_run_flag is False
    # Report portion is byte-identical after the attribution + blank line (FR-005).
    assert sent_message == f"{driver.ATTRIBUTION_LINE}\n\n{body}"

    tick = _read_tick(tick_path)
    assert tick["status"] == "success"
    assert tick["exit_code"] == 0
    assert tick["delivery_confirmed"] is True
    assert tick["failure_reason"] is None
    assert tick["completed_at_utc"] == "2026-07-13T06:00:00Z"


def test_compose_message_preserves_report_body_verbatim() -> None:
    body = "line one\nline two\n"
    composed = driver.compose_message(body)
    assert composed == f"{driver.ATTRIBUTION_LINE}\n\n{body}"
    # The report portion (everything after the attribution + blank line)
    # must be byte-identical to the helper's output.
    assert composed.split("\n\n", 1)[1] == body


# --------------------------------------------------------------------------- #
# Helper failure.
# --------------------------------------------------------------------------- #
def test_helper_failure_writes_failure_tick_and_no_send(tmp_path: Path) -> None:
    calls: list[tuple[str, bool]] = []

    def _send(message: str, dry_run: bool) -> driver.SendResult:
        calls.append((message, dry_run))
        return _confirmed_send_result()

    tick_path = tmp_path / "last-tick.json"
    exit_code = driver.run(
        mode="run",
        run_helper=_failing_helper("VikunjaError: /projects/1/tasks"),
        send=_send,
        now=_now,
        tick_path=tick_path,
    )

    assert exit_code != 0
    assert calls == []  # no send attempted — never deliver a partial/fabricated report

    tick = _read_tick(tick_path)
    assert tick["status"] == "failure"
    assert tick["exit_code"] != 0
    assert tick["delivery_confirmed"] is False
    assert "VikunjaError" in tick["failure_reason"]


# --------------------------------------------------------------------------- #
# Send confirmation predicate (C1 / FR-006).
# --------------------------------------------------------------------------- #
def test_send_result_without_message_id_is_not_confirmed(tmp_path: Path) -> None:
    def _send(message: str, dry_run: bool) -> driver.SendResult:
        payload = {"dryRun": False, "queued": True}
        return driver.SendResult(exit_code=0, stdout=json.dumps(payload), stderr="")

    tick_path = tmp_path / "last-tick.json"
    exit_code = driver.run(
        mode="run",
        run_helper=_ok_helper(),
        send=_send,
        now=_now,
        tick_path=tick_path,
    )

    assert exit_code != 0
    tick = _read_tick(tick_path)
    assert tick["status"] == "failure"
    assert tick["delivery_confirmed"] is False
    assert "messageId" in tick["failure_reason"]


def test_malformed_json_from_send_is_not_confirmed(tmp_path: Path) -> None:
    def _send(message: str, dry_run: bool) -> driver.SendResult:
        return driver.SendResult(exit_code=0, stdout="not json{{{", stderr="")

    tick_path = tmp_path / "last-tick.json"
    exit_code = driver.run(
        mode="run",
        run_helper=_ok_helper(),
        send=_send,
        now=_now,
        tick_path=tick_path,
    )

    assert exit_code != 0
    tick = _read_tick(tick_path)
    assert tick["status"] == "failure"
    assert tick["delivery_confirmed"] is False
    assert "not JSON" in tick["failure_reason"]


def test_dry_run_true_in_send_response_is_not_confirmed(tmp_path: Path) -> None:
    def _send(message: str, dry_run: bool) -> driver.SendResult:
        payload = {"messageId": "msg-999", "dryRun": True}
        return driver.SendResult(exit_code=0, stdout=json.dumps(payload), stderr="")

    tick_path = tmp_path / "last-tick.json"
    exit_code = driver.run(
        mode="run",
        run_helper=_ok_helper(),
        send=_send,
        now=_now,
        tick_path=tick_path,
    )

    assert exit_code != 0
    tick = _read_tick(tick_path)
    assert tick["status"] == "failure"
    assert tick["delivery_confirmed"] is False
    assert "dryRun" in tick["failure_reason"]


def test_nonzero_send_exit_is_not_confirmed(tmp_path: Path) -> None:
    def _send(message: str, dry_run: bool) -> driver.SendResult:
        return driver.SendResult(exit_code=1, stdout="", stderr="gateway unreachable")

    tick_path = tmp_path / "last-tick.json"
    exit_code = driver.run(
        mode="run",
        run_helper=_ok_helper(),
        send=_send,
        now=_now,
        tick_path=tick_path,
    )

    assert exit_code != 0
    tick = _read_tick(tick_path)
    assert tick["status"] == "failure"
    assert tick["delivery_confirmed"] is False
    assert "gateway unreachable" in tick["failure_reason"]


def test_confirm_delivery_non_object_json_is_not_confirmed() -> None:
    send_result = driver.SendResult(exit_code=0, stdout=json.dumps([1, 2, 3]), stderr="")
    confirmed, reason = driver.confirm_delivery(send_result)
    assert confirmed is False
    assert "not an object" in reason


def test_confirm_delivery_predicate_matches_c1_nested_payload() -> None:
    payload = {
        "payload": {"result": {"messageId": "msg-abc", "runId": "run-1", "dryRun": False}}
    }
    send_result = driver.SendResult(exit_code=0, stdout=json.dumps(payload), stderr="")
    confirmed, reason = driver.confirm_delivery(send_result)
    assert confirmed is True
    assert reason == ""


# --------------------------------------------------------------------------- #
# --self-test mode (C2).
# --------------------------------------------------------------------------- #
def test_self_test_writes_tick_calls_dry_run_send_no_real_send(tmp_path: Path) -> None:
    calls: list[tuple[str, bool]] = []

    def _send(message: str, dry_run: bool) -> driver.SendResult:
        calls.append((message, dry_run))
        # Self-test's own send effect must be invoked with dry_run=True;
        # simulate the realistic openclaw --dry-run response shape.
        payload = {"dryRun": True, "queued": False}
        return driver.SendResult(exit_code=0, stdout=json.dumps(payload), stderr="")

    tick_path = tmp_path / "self-test-last-tick.json"
    exit_code = driver.run(
        mode="self-test",
        run_helper=_ok_helper(),
        send=_send,
        now=_now,
        tick_path=tick_path,
    )

    assert exit_code == 0
    assert len(calls) == 1
    _message, dry_run_flag = calls[0]
    assert dry_run_flag is True  # NO real send

    tick = _read_tick(tick_path)
    assert tick["status"] == "success"
    # Self-test never claims real delivery confirmation (a dry-run send can
    # never satisfy the C1 predicate by construction).
    assert tick["delivery_confirmed"] is False


def test_self_test_default_tick_path_is_self_test_scoped_not_production(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """--self-test with no explicit tick_path must write ONLY the self-test
    path and must NOT touch DEFAULT_TICK_PATH (production).

    Regression guard (post-merge Codex review, #723): a self-test dry-run
    must never be able to make the production freshness canary report the
    weekly producer "healthy" when no real delivery occurred.
    """
    production_tick_path = tmp_path / "last-tick.json"
    self_test_tick_path = tmp_path / "self-test-last-tick.json"
    monkeypatch.setattr(driver, "DEFAULT_TICK_PATH", production_tick_path)
    monkeypatch.setattr(driver, "SELF_TEST_TICK_PATH", self_test_tick_path)

    def _send(message: str, dry_run: bool) -> driver.SendResult:
        payload = {"dryRun": True, "queued": False}
        return driver.SendResult(exit_code=0, stdout=json.dumps(payload), stderr="")

    exit_code = driver.run(
        mode="self-test",
        run_helper=_ok_helper(),
        send=_send,
        now=_now,
        # tick_path intentionally omitted — exercise the mode-aware default.
    )

    assert exit_code == 0
    assert self_test_tick_path.exists()
    assert not production_tick_path.exists()


def test_run_mode_default_tick_path_is_production_last_tick(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A real ``mode="run"`` pass with no explicit tick_path still writes
    the production DEFAULT_TICK_PATH (unaffected by the self-test isolation
    change)."""
    production_tick_path = tmp_path / "last-tick.json"
    self_test_tick_path = tmp_path / "self-test-last-tick.json"
    monkeypatch.setattr(driver, "DEFAULT_TICK_PATH", production_tick_path)
    monkeypatch.setattr(driver, "SELF_TEST_TICK_PATH", self_test_tick_path)

    def _send(message: str, dry_run: bool) -> driver.SendResult:
        return _confirmed_send_result()

    exit_code = driver.run(
        mode="run",
        run_helper=_ok_helper(),
        send=_send,
        now=_now,
        # tick_path intentionally omitted — exercise the mode-aware default.
    )

    assert exit_code == 0
    assert production_tick_path.exists()
    assert not self_test_tick_path.exists()


def test_self_test_send_path_failure_writes_failure_tick(tmp_path: Path) -> None:
    def _send(message: str, dry_run: bool) -> driver.SendResult:
        return driver.SendResult(exit_code=1, stdout="", stderr="boom")

    tick_path = tmp_path / "self-test-last-tick.json"
    exit_code = driver.run(
        mode="self-test",
        run_helper=_ok_helper(),
        send=_send,
        now=_now,
        tick_path=tick_path,
    )

    assert exit_code != 0
    tick = _read_tick(tick_path)
    assert tick["status"] == "failure"
    assert tick["delivery_confirmed"] is False


def test_self_test_helper_failure_writes_failure_tick_no_send(tmp_path: Path) -> None:
    calls: list[tuple[str, bool]] = []

    def _send(message: str, dry_run: bool) -> driver.SendResult:
        calls.append((message, dry_run))
        return _confirmed_send_result()

    tick_path = tmp_path / "self-test-last-tick.json"
    exit_code = driver.run(
        mode="self-test",
        run_helper=_failing_helper(),
        send=_send,
        now=_now,
        tick_path=tick_path,
    )

    assert exit_code != 0
    assert calls == []
    tick = _read_tick(tick_path)
    assert tick["status"] == "failure"


# --------------------------------------------------------------------------- #
# --dry-run mode (local preview).
# --------------------------------------------------------------------------- #
def test_dry_run_no_state_written_no_send(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    calls: list[tuple[str, bool]] = []

    def _send(message: str, dry_run: bool) -> driver.SendResult:
        calls.append((message, dry_run))
        return _confirmed_send_result()

    tick_path = tmp_path / "last-tick.json"
    body = "Weekly Habit Report\n\nSomething.\n"
    exit_code = driver.run(
        mode="dry-run",
        run_helper=_ok_helper(body),
        send=_send,
        now=_now,
        tick_path=tick_path,
    )

    assert exit_code == 0
    assert calls == []  # no send at all
    assert not tick_path.exists()  # no state written

    captured = capsys.readouterr()
    assert driver.ATTRIBUTION_LINE in captured.out
    assert body in captured.out


def test_dry_run_helper_failure_no_state_written(tmp_path: Path) -> None:
    tick_path = tmp_path / "last-tick.json"
    exit_code = driver.run(
        mode="dry-run",
        run_helper=_failing_helper(),
        send=lambda message, dry_run: _confirmed_send_result(),
        now=_now,
        tick_path=tick_path,
    )

    assert exit_code != 0
    assert not tick_path.exists()


# --------------------------------------------------------------------------- #
# CLI wiring.
# --------------------------------------------------------------------------- #
def test_parse_args_defaults_to_run_mode() -> None:
    args = driver._parse_args([])
    assert args.self_test is False
    assert args.dry_run is False


def test_parse_args_self_test_flag() -> None:
    args = driver._parse_args(["--self-test"])
    assert args.self_test is True


def test_parse_args_dry_run_flag() -> None:
    args = driver._parse_args(["--dry-run"])
    assert args.dry_run is True


def test_parse_args_mutually_exclusive_flags_rejected() -> None:
    with pytest.raises(SystemExit):
        driver._parse_args(["--self-test", "--dry-run"])


def test_main_dry_run_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tick_path = tmp_path / "last-tick.json"
    monkeypatch.setattr(driver, "run_report_helper", _ok_helper("Body.\n"))
    exit_code = driver.main(["--dry-run", "--tick-path", str(tick_path)])
    assert exit_code == 0
    assert not tick_path.exists()


def test_main_self_test_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tick_path = tmp_path / "self-test-last-tick.json"
    monkeypatch.setattr(driver, "run_report_helper", _ok_helper("Body.\n"))

    def _fake_send(message: str, dry_run: bool, **kwargs) -> driver.SendResult:
        assert dry_run is True
        payload = {"dryRun": True}
        return driver.SendResult(exit_code=0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(driver, "send_message", _fake_send)
    exit_code = driver.main(["--self-test", "--tick-path", str(tick_path)])
    assert exit_code == 0
    assert tick_path.exists()
    tick = _read_tick(tick_path)
    assert tick["status"] == "success"


def test_main_self_test_no_tick_path_flag_uses_self_test_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``main(["--self-test"])`` with no --tick-path override must resolve
    to SELF_TEST_TICK_PATH, not DEFAULT_TICK_PATH (production)."""
    production_tick_path = tmp_path / "last-tick.json"
    self_test_tick_path = tmp_path / "self-test-last-tick.json"
    monkeypatch.setattr(driver, "DEFAULT_TICK_PATH", production_tick_path)
    monkeypatch.setattr(driver, "SELF_TEST_TICK_PATH", self_test_tick_path)
    monkeypatch.setattr(driver, "run_report_helper", _ok_helper("Body.\n"))

    def _fake_send(message: str, dry_run: bool, **kwargs) -> driver.SendResult:
        assert dry_run is True
        payload = {"dryRun": True}
        return driver.SendResult(exit_code=0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(driver, "send_message", _fake_send)
    exit_code = driver.main(["--self-test"])
    assert exit_code == 0
    assert self_test_tick_path.exists()
    assert not production_tick_path.exists()


# --------------------------------------------------------------------------- #
# write_tick atomicity smoke test.
# --------------------------------------------------------------------------- #
def test_write_tick_creates_parent_dir_and_is_readable(tmp_path: Path) -> None:
    tick_path = tmp_path / "nested" / "state" / "last-tick.json"
    driver.write_tick(
        tick_path,
        now=FIXED_NOW,
        exit_code=0,
        status="success",
        delivery_confirmed=True,
        failure_reason=None,
    )
    assert tick_path.exists()
    tick = _read_tick(tick_path)
    assert tick["status"] == "success"
    assert tick["delivery_confirmed"] is True


# --------------------------------------------------------------------------- #
# run() input validation.
# --------------------------------------------------------------------------- #
def test_write_tick_cleans_up_tempfile_on_rename_failure(tmp_path: Path) -> None:
    tick_path = tmp_path / "last-tick.json"
    with patch(
        "scripts.habits.weekly_report_driver.os.replace",
        side_effect=OSError("disk full"),
    ):
        with pytest.raises(OSError, match="disk full"):
            driver.write_tick(
                tick_path,
                now=FIXED_NOW,
                exit_code=0,
                status="success",
                delivery_confirmed=True,
                failure_reason=None,
            )
    # No stray tempfiles left behind and no tick written.
    assert not tick_path.exists()
    leftovers = list(tmp_path.glob(".last-tick.json.*.tmp"))
    assert leftovers == []


def test_run_rejects_unknown_mode(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown mode"):
        driver.run(
            mode="bogus",
            run_helper=_ok_helper(),
            send=lambda message, dry_run: _confirmed_send_result(),
            now=_now,
            tick_path=tmp_path / "last-tick.json",
        )


# --------------------------------------------------------------------------- #
# send_message production effect (subprocess boundary mocked — still offline:
# no real process is spawned, no network call is made).
# --------------------------------------------------------------------------- #
def test_send_message_invokes_absolute_openclaw_with_expected_argv() -> None:
    fake_completed = MagicMock(
        returncode=0,
        stdout=json.dumps({"messageId": "msg-1", "dryRun": False}),
        stderr="",
    )
    with patch(
        "scripts.habits.weekly_report_driver.subprocess.run",
        return_value=fake_completed,
    ) as mock_run:
        result = driver.send_message("hello world", False)

    assert result.exit_code == 0
    args, kwargs = mock_run.call_args
    cmd = args[0]
    assert cmd[0] == driver.OPENCLAW_BIN
    assert cmd[:5] == [
        driver.OPENCLAW_BIN,
        "message",
        "send",
        "--channel",
        "whatsapp",
    ]
    assert "--target" in cmd
    assert driver.DEFAULT_TARGET in cmd
    assert "--message" in cmd
    assert "hello world" in cmd
    assert "--json" in cmd
    assert "--dry-run" not in cmd
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True


def test_send_message_dry_run_appends_flag() -> None:
    fake_completed = MagicMock(
        returncode=0, stdout=json.dumps({"dryRun": True}), stderr=""
    )
    with patch(
        "scripts.habits.weekly_report_driver.subprocess.run",
        return_value=fake_completed,
    ) as mock_run:
        driver.send_message("hello", True)

    cmd = mock_run.call_args[0][0]
    assert "--dry-run" in cmd


def test_send_message_timeout_expired_maps_to_exit_124() -> None:
    exc = subprocess.TimeoutExpired(cmd=["openclaw"], timeout=60, output="partial", stderr="stalled")
    with patch(
        "scripts.habits.weekly_report_driver.subprocess.run", side_effect=exc
    ):
        result = driver.send_message("hello", False, timeout=60)

    assert result.exit_code == 124
    assert "timed out after 60s" in result.stderr


def test_send_message_os_error_maps_to_exit_127() -> None:
    with patch(
        "scripts.habits.weekly_report_driver.subprocess.run",
        side_effect=OSError("no such file"),
    ):
        result = driver.send_message("hello", False)

    assert result.exit_code == 127
    assert "no such file" in result.stderr


# --------------------------------------------------------------------------- #
# run_report_helper production effect (Vikunja client + helper internals
# mocked at the module boundary — still offline).
# --------------------------------------------------------------------------- #
def test_run_report_helper_success_path_delegates_to_weekly_helper() -> None:
    fake_report = {"rendered_text": "Weekly Habit Report\n\nMorning Run: 5/7\n"}
    with patch("scripts.common.vikunja_client.VikunjaClient") as MockClient, patch.object(
        driver.weekly_helper, "query_completion_events", return_value=[]
    ), patch.object(
        driver.weekly_helper, "build_report", return_value=fake_report
    ):
        MockClient.return_value = MagicMock()
        result = driver.run_report_helper()

    assert result.ok is True
    assert result.report_body == fake_report["rendered_text"]


def test_run_report_helper_vikunja_error_is_reported_not_raised() -> None:
    from scripts.common.vikunja_client import VikunjaError

    def _raise_vikunja_error(*args, **kwargs):
        raise VikunjaError(path="/projects/1/tasks")

    with patch(
        "scripts.common.vikunja_client.VikunjaClient",
        side_effect=_raise_vikunja_error,
    ):
        result = driver.run_report_helper()

    assert result.ok is False
    assert "VikunjaError" in result.error


def test_run_report_helper_unexpected_exception_is_reported_not_raised() -> None:
    with patch(
        "scripts.common.vikunja_client.VikunjaClient",
        side_effect=RuntimeError("boom"),
    ):
        result = driver.run_report_helper()

    assert result.ok is False
    assert "internal error" in result.error
    assert "boom" in result.error
