"""Test matrix for ``scripts.office2.felix_health_check.run`` (WP03 T015;
alert-bus migration #701).

Covers the contract's required matrix (health-check-runner.contract.md):
stdout-only ALL_HEALTHY; stdout-only FAILURES_DETECTED; both tokens present
(failure wins); token in stderr only; non-zero exit + ALL_HEALTHY (->
UNKNOWN); missing script (-> SCRIPT_MISSING + alert); oversized output
(truncation); delivery failure (non-fatal, recorded).

Since the alert-bus migration (#701), ``send_alert``/``_delivery_record`` and
their ``emit()`` wiring are covered by ``tests/office2/felix_health_check/
test_run.py``. This co-located file focuses on ``classify``, ``_truncate``,
``run_health_check_script``, and ``main()`` orchestration; the ``main()`` tests
mock ``run_module.send_alert`` directly so no real subprocess, script, network,
or bus call is made.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

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


# --- helpers -------------------------------------------------------------------


def _fake_completed(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["bash"], returncode=returncode, stdout=stdout, stderr=stderr)


# A fake delivery record matching send_alert's return shape (via _delivery_record).
_DELIVERY_SENT = {"attempted": True, "sent": True, "detail": "delivered"}
_DELIVERY_FAILED = {"attempted": True, "sent": False, "detail": "ntfy POST failed: rc=22"}


class _FakeSendAlert:
    """Records ``send_alert`` calls and returns a canned delivery record.

    The ``main()`` tests mock ``run_module.send_alert`` with this so the
    orchestration path is exercised without touching the alert bus (whose
    own coverage lives in ``tests/office2/felix_health_check/test_run.py``).
    """

    def __init__(self, delivery: dict) -> None:
        self._delivery = delivery
        self.calls: list[tuple[str, str]] = []

    def __call__(self, status: str, body: str) -> dict:
        self.calls.append((status, body))
        return dict(self._delivery)


# --- main() end-to-end (send_alert stubbed at the module seam) ------------------


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
    delivery: dict = _DELIVERY_SENT,
) -> tuple[int, dict, _FakeSendAlert]:
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

    fake_send = _FakeSendAlert(delivery)
    monkeypatch.setattr(run_module, "send_alert", fake_send)

    exit_code = run_module.main([])
    signal_file: Path = run_module.SIGNAL_FILE
    payload = json.loads(signal_file.read_text(encoding="utf-8"))
    return exit_code, payload, fake_send


def test_main_all_healthy_stamps_signal_and_no_alert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exit_code, payload, fake_send = _run_main_with_script_result(
        monkeypatch, returncode=0, stdout="ALL_HEALTHY"
    )
    assert exit_code == 0
    assert payload["status"] == run_module.STATUS_ALL_HEALTHY
    assert payload["exit_code"] == 0
    # Healthy run stamps a "no alert" delivery and never calls send_alert.
    assert fake_send.calls == []
    assert payload["delivery"]["attempted"] is False


def test_main_failures_detected_alerts(monkeypatch: pytest.MonkeyPatch) -> None:
    exit_code, payload, fake_send = _run_main_with_script_result(
        monkeypatch, returncode=1, stdout="FAILURES_DETECTED"
    )
    assert exit_code == 0
    assert payload["status"] == run_module.STATUS_FAILURES_DETECTED
    assert len(fake_send.calls) == 1
    assert fake_send.calls[0][0] == run_module.STATUS_FAILURES_DETECTED
    assert payload["delivery"]["attempted"] is True
    assert payload["delivery"]["sent"] is True


def test_main_missing_script_alerts_and_exits_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exit_code, payload, fake_send = _run_main_with_script_result(
        monkeypatch, returncode=0, stdout="ALL_HEALTHY", script_exists=False
    )
    assert exit_code == 0
    assert payload["status"] == run_module.STATUS_SCRIPT_MISSING
    assert payload["exit_code"] is None
    assert len(fake_send.calls) == 1
    assert fake_send.calls[0][0] == run_module.STATUS_SCRIPT_MISSING
    assert payload["delivery"]["attempted"] is True
    assert payload["delivery"]["sent"] is True


def test_main_ntfy_failure_is_non_fatal_and_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exit_code, payload, fake_send = _run_main_with_script_result(
        monkeypatch,
        returncode=1,
        stdout="FAILURES_DETECTED",
        delivery=_DELIVERY_FAILED,
    )
    # A failed delivery must not fail the run — main() stays non-fatal (exit 0)
    # and records the failure outcome in the signal file.
    assert exit_code == 0
    assert payload["status"] == run_module.STATUS_FAILURES_DETECTED
    assert len(fake_send.calls) == 1
    assert payload["delivery"]["attempted"] is True
    assert payload["delivery"]["sent"] is False
    assert payload["delivery"]["detail"] == _DELIVERY_FAILED["detail"]


def test_main_oversized_output_is_truncated_before_alert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    huge_stdout = "FAILURES_DETECTED\n" + ("x" * (run_module.OUTPUT_TRUNCATE_BYTES * 2))

    exit_code, _payload, fake_send = _run_main_with_script_result(
        monkeypatch, returncode=1, stdout=huge_stdout
    )
    assert exit_code == 0
    # The body handed to send_alert must already be truncated by main().
    assert len(fake_send.calls) == 1
    _status, body = fake_send.calls[0]
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

    fake_send = _FakeSendAlert(_DELIVERY_SENT)
    monkeypatch.setattr(run_module, "send_alert", fake_send)

    exit_code = run_module.main([])
    signal_file: Path = run_module.SIGNAL_FILE
    payload = json.loads(signal_file.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["status"] == run_module.STATUS_UNKNOWN
    assert len(fake_send.calls) == 1
    assert fake_send.calls[0][0] == run_module.STATUS_UNKNOWN
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
