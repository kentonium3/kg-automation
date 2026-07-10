"""Tests for the scripts.common.alert_bus CLI (__main__)."""

from __future__ import annotations

import io

import pytest

from scripts.common.alert_bus.__main__ import main
from scripts.common.alert_bus.model import AlertResult


@pytest.fixture
def capture_emit(monkeypatch):
    """Capture the Alert passed to emit and control the AlertResult returned."""
    captured: dict = {}

    def _make(result: AlertResult):
        def _emit(alert):
            captured["alert"] = alert
            return result

        # Patch the name the CLI uses (imported into __main__ namespace).
        monkeypatch.setattr("scripts.common.alert_bus.__main__.emit", _emit)
        return captured

    return _make


def test_emit_best_effort_exits_0_on_failure(capture_emit):
    capture_emit(AlertResult(ok=False, reason="CURL_TIMEOUT"))
    rc = main(
        [
            "emit",
            "--source", "s",
            "--severity", "error",
            "--title", "t",
            "--description", "d",
        ]
    )
    assert rc == 0


def test_emit_best_effort_exits_0_on_success(capture_emit):
    capture_emit(AlertResult(ok=True))
    rc = main(
        [
            "emit",
            "--source", "s",
            "--severity", "info",
            "--title", "t",
            "--description", "d",
        ]
    )
    assert rc == 0


def test_emit_strict_exits_nonzero_on_failure(capture_emit):
    capture_emit(AlertResult(ok=False, reason="NTFY_MISSING_TOPIC"))
    rc = main(
        [
            "emit",
            "--source", "s",
            "--severity", "error",
            "--title", "t",
            "--description", "d",
            "--strict",
        ]
    )
    assert rc == 1


def test_emit_strict_exits_0_on_success(capture_emit):
    capture_emit(AlertResult(ok=True))
    rc = main(
        [
            "emit",
            "--source", "s",
            "--severity", "error",
            "--title", "t",
            "--description", "d",
            "--strict",
        ]
    )
    assert rc == 0


def test_emit_builds_details_from_repeated_flags(capture_emit):
    captured = capture_emit(AlertResult(ok=True))
    main(
        [
            "emit",
            "--source", "s",
            "--severity", "warn",
            "--title", "t",
            "--description", "d",
            "--action", "do the thing",
            "--detail", "phase=dry_run",
            "--detail", "exit_code=126",
        ]
    )
    alert = captured["alert"]
    assert alert.action == "do the thing"
    assert alert.details == {"phase": "dry_run", "exit_code": "126"}


def test_detail_value_may_contain_equals(capture_emit):
    captured = capture_emit(AlertResult(ok=True))
    main(
        [
            "emit",
            "--source", "s",
            "--severity", "warn",
            "--title", "t",
            "--description", "d",
            "--detail", "url=https://x/y?a=b",
        ]
    )
    assert captured["alert"].details["url"] == "https://x/y?a=b"


def test_detail_stdin_folds_into_details(capture_emit, monkeypatch):
    captured = capture_emit(AlertResult(ok=True))
    monkeypatch.setattr("sys.stdin", io.StringIO("captured stderr blob"))
    main(
        [
            "emit",
            "--source", "s",
            "--severity", "error",
            "--title", "t",
            "--description", "d",
            "--detail-stdin",
        ]
    )
    assert captured["alert"].details["stdin"] == "captured stderr blob"


def test_bad_detail_format_errors(capture_emit):
    capture_emit(AlertResult(ok=True))
    with pytest.raises(SystemExit):
        main(
            [
                "emit",
                "--source", "s",
                "--severity", "error",
                "--title", "t",
                "--description", "d",
                "--detail", "no-equals-here",
            ]
        )


def test_bad_detail_empty_key_errors(capture_emit):
    capture_emit(AlertResult(ok=True))
    with pytest.raises(SystemExit):
        main(
            [
                "emit",
                "--source", "s",
                "--severity", "error",
                "--title", "t",
                "--description", "d",
                "--detail", "=value",
            ]
        )


def test_invalid_severity_choice_errors(capture_emit):
    capture_emit(AlertResult(ok=True))
    with pytest.raises(SystemExit):
        main(
            [
                "emit",
                "--source", "s",
                "--severity", "fatal",
                "--title", "t",
                "--description", "d",
            ]
        )


def test_no_subcommand_errors():
    with pytest.raises(SystemExit):
        main([])


def test_self_test_exit_0_when_delivered(capture_emit):
    captured = capture_emit(AlertResult(ok=True))
    rc = main(["self-test"])
    assert rc == 0
    assert captured["alert"].severity.value == "info"
    assert captured["alert"].source == "alert-bus/self-test"


def test_self_test_exit_nonzero_when_not_delivered(capture_emit):
    capture_emit(AlertResult(ok=False, reason="NTFY_MISSING_TOPIC"))
    rc = main(["self-test"])
    assert rc == 1
