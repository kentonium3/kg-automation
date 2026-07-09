"""Test matrix for ``scripts.office2.felix_health_check.run`` (WP03 T015).

Covers the contract's required matrix (health-check-runner.contract.md):
stdout-only ALL_HEALTHY; stdout-only FAILURES_DETECTED; both tokens present
(failure wins); token in stderr only; non-zero exit + ALL_HEALTHY (->
UNKNOWN); missing script (-> SCRIPT_MISSING + alert); oversized output
(truncation); ntfy send failure (non-fatal, logged + recorded).

No real subprocess, script, or network call is made — ``subprocess.run`` is
monkeypatched at the module level for both the health-check invocation and
the ntfy curl POST.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from scripts.office2.felix_health_check import run as run_module


# --- classify() unit tests ---------------------------------------------------


def test_classify_stdout_only_all_healthy() -> None:
    assert run_module.classify("ALL_HEALTHY", "", 0) == run_module.STATUS_ALL_HEALTHY


def test_classify_stdout_only_failures_detected() -> None:
    assert (
        run_module.classify("FAILURES_DETECTED", "", 1)
        == run_module.STATUS_FAILURES_DETECTED
    )


def test_classify_both_tokens_failure_wins() -> None:
    """Codex #9: FAILURES_DETECTED wins even when ALL_HEALTHY also appears."""
    stdout = "ALL_HEALTHY\nFAILURES_DETECTED"
    assert run_module.classify(stdout, "", 0) == run_module.STATUS_FAILURES_DETECTED


def test_classify_token_in_stderr_only() -> None:
    assert (
        run_module.classify("", "FAILURES_DETECTED", 1)
        == run_module.STATUS_FAILURES_DETECTED
    )


def test_classify_all_healthy_token_in_stderr_only() -> None:
    assert run_module.classify("", "ALL_HEALTHY", 0) == run_module.STATUS_ALL_HEALTHY


def test_classify_nonzero_exit_with_all_healthy_token_is_unknown() -> None:
    """A non-zero exit code invalidates an otherwise-healthy token."""
    assert run_module.classify("ALL_HEALTHY", "", 1) == run_module.STATUS_UNKNOWN


def test_classify_neither_token_is_unknown() -> None:
    assert run_module.classify("some noise", "", 0) == run_module.STATUS_UNKNOWN


# --- truncation ---------------------------------------------------------------


def test_truncate_under_limit_is_unchanged() -> None:
    text = "short output"
    assert run_module._truncate(text) == text


def test_truncate_oversized_output_adds_marker_and_bounds_size() -> None:
    text = "A" * (run_module.OUTPUT_TRUNCATE_BYTES * 2)
    truncated = run_module._truncate(text)
    assert truncated.endswith(run_module.TRUNCATION_MARKER)
    assert len(truncated.encode("utf-8")) <= (
        run_module.OUTPUT_TRUNCATE_BYTES + len(run_module.TRUNCATION_MARKER)
    )


# --- ntfy delivery --------------------------------------------------------------


def _fake_completed(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["curl"], returncode=returncode, stdout=stdout, stderr=stderr)


def test_send_ntfy_alert_skips_when_topic_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(run_module.NTFY_TOPIC_ENV, raising=False)
    called = False

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        nonlocal called
        called = True
        return _fake_completed(0)

    monkeypatch.setattr(run_module.subprocess, "run", fake_run)
    delivery = run_module.send_ntfy_alert(run_module.STATUS_FAILURES_DETECTED, "body")
    assert delivery == {
        "attempted": False,
        "sent": False,
        "detail": f"ntfy skipped: {run_module.NTFY_TOPIC_ENV} not configured",
    }
    assert called is False


def test_send_ntfy_alert_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(run_module.NTFY_TOPIC_ENV, "test-topic-1234")
    monkeypatch.setattr(run_module.subprocess, "run", lambda *a, **k: _fake_completed(0))
    delivery = run_module.send_ntfy_alert(run_module.STATUS_FAILURES_DETECTED, "body")
    assert delivery["attempted"] is True
    assert delivery["sent"] is True


def test_send_ntfy_alert_failure_is_non_fatal_and_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(run_module.NTFY_TOPIC_ENV, "test-topic-1234")
    monkeypatch.setattr(run_module.subprocess, "run", lambda *a, **k: _fake_completed(22))
    delivery = run_module.send_ntfy_alert(run_module.STATUS_FAILURES_DETECTED, "body")
    assert delivery["attempted"] is True
    assert delivery["sent"] is False
    assert "curl rc=22" in delivery["detail"]


def test_send_ntfy_alert_spawn_failure_is_non_fatal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(run_module.NTFY_TOPIC_ENV, "test-topic-1234")

    def raise_oserror(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise OSError("curl not found")

    monkeypatch.setattr(run_module.subprocess, "run", raise_oserror)
    delivery = run_module.send_ntfy_alert(run_module.STATUS_FAILURES_DETECTED, "body")
    assert delivery["attempted"] is True
    assert delivery["sent"] is False
    assert "non-fatal" in delivery["detail"]


# --- main() end-to-end (subprocess.run stubbed at module import site) -----------


@pytest.fixture(autouse=True)
def _isolated_signal_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the signal file into a tmp dir so tests never touch /data."""
    signal_file = tmp_path / "felix-health-check" / "last-run.json"
    monkeypatch.setattr(run_module, "SIGNAL_FILE", signal_file)
    return signal_file


def _run_main_with_script_result(
    monkeypatch: pytest.MonkeyPatch,
    *,
    returncode: int,
    stdout: str = "",
    stderr: str = "",
    script_exists: bool = True,
    ntfy_returncode: int = 0,
) -> tuple[int, dict]:
    monkeypatch.setattr(
        run_module.Path, "is_file", lambda self: script_exists, raising=True
    )
    monkeypatch.setattr(
        run_module.os, "access", lambda path, mode: script_exists, raising=True
    )

    def fake_run_health_check_script(
        script_path: Path = run_module.HEALTH_CHECK_SCRIPT,
    ) -> subprocess.CompletedProcess[str]:
        return _fake_completed(returncode, stdout=stdout, stderr=stderr)

    monkeypatch.setattr(run_module, "run_health_check_script", fake_run_health_check_script)

    monkeypatch.setenv(run_module.NTFY_TOPIC_ENV, "test-topic-1234")
    monkeypatch.setattr(
        run_module.subprocess, "run", lambda *a, **k: _fake_completed(ntfy_returncode)
    )

    exit_code = run_module.main([])
    signal_file: Path = run_module.SIGNAL_FILE
    payload = json.loads(signal_file.read_text(encoding="utf-8"))
    return exit_code, payload


def test_main_all_healthy_stamps_signal_and_no_alert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exit_code, payload = _run_main_with_script_result(
        monkeypatch, returncode=0, stdout="ALL_HEALTHY"
    )
    assert exit_code == 0
    assert payload["status"] == run_module.STATUS_ALL_HEALTHY
    assert payload["exit_code"] == 0
    assert payload["delivery"]["attempted"] is False


def test_main_failures_detected_alerts(monkeypatch: pytest.MonkeyPatch) -> None:
    exit_code, payload = _run_main_with_script_result(
        monkeypatch, returncode=1, stdout="FAILURES_DETECTED"
    )
    assert exit_code == 0
    assert payload["status"] == run_module.STATUS_FAILURES_DETECTED
    assert payload["delivery"]["attempted"] is True
    assert payload["delivery"]["sent"] is True


def test_main_missing_script_alerts_and_exits_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exit_code, payload = _run_main_with_script_result(
        monkeypatch, returncode=0, stdout="ALL_HEALTHY", script_exists=False
    )
    assert exit_code == 0
    assert payload["status"] == run_module.STATUS_SCRIPT_MISSING
    assert payload["exit_code"] is None
    assert payload["delivery"]["attempted"] is True
    assert payload["delivery"]["sent"] is True


def test_main_ntfy_failure_is_non_fatal_and_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exit_code, payload = _run_main_with_script_result(
        monkeypatch,
        returncode=1,
        stdout="FAILURES_DETECTED",
        ntfy_returncode=22,
    )
    assert exit_code == 0
    assert payload["status"] == run_module.STATUS_FAILURES_DETECTED
    assert payload["delivery"]["attempted"] is True
    assert payload["delivery"]["sent"] is False
    assert "curl rc=22" in payload["delivery"]["detail"]


def test_main_oversized_output_is_truncated_before_alert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    huge_stdout = "FAILURES_DETECTED\n" + ("x" * (run_module.OUTPUT_TRUNCATE_BYTES * 2))
    captured_bodies: list[str] = []

    def fake_run_health_check_script(
        script_path: Path = run_module.HEALTH_CHECK_SCRIPT,
    ) -> subprocess.CompletedProcess[str]:
        return _fake_completed(1, stdout=huge_stdout)

    monkeypatch.setattr(run_module.Path, "is_file", lambda self: True, raising=True)
    monkeypatch.setattr(run_module.os, "access", lambda path, mode: True, raising=True)
    monkeypatch.setattr(run_module, "run_health_check_script", fake_run_health_check_script)
    monkeypatch.setenv(run_module.NTFY_TOPIC_ENV, "test-topic-1234")

    def fake_curl(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured_bodies.append(kwargs.get("input", ""))
        return _fake_completed(0)

    monkeypatch.setattr(run_module.subprocess, "run", fake_curl)

    exit_code = run_module.main([])
    assert exit_code == 0
    assert len(captured_bodies) == 1
    body = captured_bodies[0]
    assert body.endswith(run_module.TRUNCATION_MARKER)
    assert len(body.encode("utf-8")) <= (
        run_module.OUTPUT_TRUNCATE_BYTES + len(run_module.TRUNCATION_MARKER)
    )


def test_main_subprocess_timeout_is_unknown_and_alerts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(run_module.Path, "is_file", lambda self: True, raising=True)
    monkeypatch.setattr(run_module.os, "access", lambda path, mode: True, raising=True)

    def fake_run_health_check_script(
        script_path: Path = run_module.HEALTH_CHECK_SCRIPT,
    ) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd="health-check.sh", timeout=300)

    monkeypatch.setattr(run_module, "run_health_check_script", fake_run_health_check_script)
    monkeypatch.setenv(run_module.NTFY_TOPIC_ENV, "test-topic-1234")
    monkeypatch.setattr(run_module.subprocess, "run", lambda *a, **k: _fake_completed(0))

    exit_code = run_module.main([])
    signal_file: Path = run_module.SIGNAL_FILE
    payload = json.loads(signal_file.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["status"] == run_module.STATUS_UNKNOWN
    assert payload["delivery"]["attempted"] is True


def test_run_health_check_script_uses_subprocess_run_not_exec() -> None:
    """Guard against a future regression reintroducing os.exec* (Codex #1).

    Checks the compiled bytecode's global names rather than source text,
    so this assertion can't be fooled (or broken) by prose mentioning
    "exec" in a docstring or comment.
    """
    code = run_module.run_health_check_script.__code__
    names = code.co_names
    assert "run" in names  # subprocess.run is called
    assert not any(name.startswith("exec") for name in names)
