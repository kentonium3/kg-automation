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
        self.kwargs: list[dict] = []

    def __call__(self, status: str, body: str, **kwargs) -> dict:
        self.calls.append((status, body))
        self.kwargs.append(kwargs)
        return dict(self._delivery)


# --- main() end-to-end (send_alert stubbed at the module seam) ------------------


@pytest.fixture(autouse=True)
def _isolated_signal_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the signal file into a tmp dir so tests never touch /data."""
    signal_file = tmp_path / "felix-health-check" / "last-run.json"
    monkeypatch.setattr(run_module, "SIGNAL_FILE", signal_file)
    return signal_file


_REAL_GUARD = run_module._evaluate_coverage_guarded


class _Finding:
    """Stand-in coverage finding (the real ones are tested in test_coverage.py)."""

    def __init__(self, component: str, finding: str = "ok", outcome: str = "healthy",
                 evidence: str = "fixture") -> None:
        self.component, self.finding, self.outcome, self.evidence = component, finding, outcome, evidence

    def to_record(self) -> dict:
        return {"component": self.component, "outcome": self.outcome,
                "finding": self.finding, "evidence": self.evidence}


def _ok_findings() -> list:
    return [_Finding("felix-canary"), _Finding("restic-backup")]


@pytest.fixture(autouse=True)
def _coverage_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default: both coverage checks pass, so these tests exercise the shell
    path exactly as before #1063. Tests that need coverage findings override
    ``_evaluate_coverage_guarded`` themselves."""
    monkeypatch.setattr(run_module, "_evaluate_coverage_guarded", lambda now: _ok_findings())


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


# --- #1063: coverage folded into the verdict, record and alert ---------------


def test_script_lives_in_the_repo_next_to_the_wrapper() -> None:
    assert run_module.HEALTH_CHECK_SCRIPT == Path(run_module.__file__).resolve().with_name("health-check.sh")
    assert run_module.HEALTH_CHECK_SCRIPT.is_file()
    assert "helper-scripts" not in str(run_module.HEALTH_CHECK_SCRIPT)


_SCRIPT_STATUSES = ["ALL_HEALTHY", "FAILURES_DETECTED", "UNKNOWN", "SCRIPT_MISSING"]
_KINDS = ["ok", "failure", "unknown"]


def _expected(script_status: str, kinds: tuple[str, str]) -> str:
    if script_status == "FAILURES_DETECTED" or "failure" in kinds:
        return "FAILURES_DETECTED"
    if script_status == "SCRIPT_MISSING":
        return "SCRIPT_MISSING"
    if script_status == "UNKNOWN" or "unknown" in kinds:
        return "UNKNOWN"
    return "ALL_HEALTHY"


@pytest.mark.parametrize("script_status", _SCRIPT_STATUSES)
@pytest.mark.parametrize("canary", _KINDS)
@pytest.mark.parametrize("backup", _KINDS)
def test_combine_full_grid(script_status: str, canary: str, backup: str) -> None:
    findings = [_Finding("felix-canary", canary), _Finding("restic-backup", backup)]
    assert run_module.combine(script_status, findings) == _expected(script_status, (canary, backup))


def test_combine_spot_checks_independent_of_the_oracle() -> None:
    """The grid's oracle restates the table; pin the cases that matter by hand."""
    ok = _ok_findings()
    stale = [_Finding("felix-canary", "failure", "stale"), _Finding("restic-backup")]
    blind = [_Finding("felix-canary", "unknown"), _Finding("restic-backup")]
    assert run_module.combine("ALL_HEALTHY", ok) == "ALL_HEALTHY"
    assert run_module.combine("ALL_HEALTHY", stale) == "FAILURES_DETECTED"   # #1063 itself
    assert run_module.combine("ALL_HEALTHY", blind) == "UNKNOWN"             # never healthy when blind
    assert run_module.combine("SCRIPT_MISSING", stale) == "FAILURES_DETECTED"
    assert run_module.combine("SCRIPT_MISSING", blind) == "SCRIPT_MISSING"


def test_record_carries_the_contract_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    _exit, payload, _send = _run_main_with_script_result(monkeypatch, returncode=0, stdout="ALL_HEALTHY")
    assert set(payload) == {"status", "ran_at_utc", "exit_code", "delivery",
                            "script_status", "script_path", "coverage_checks"}
    assert payload["script_status"] == "ALL_HEALTHY"
    assert payload["script_path"] == str(run_module.HEALTH_CHECK_SCRIPT)
    assert [c["component"] for c in payload["coverage_checks"]] == ["felix-canary", "restic-backup"]


def test_stale_canary_turns_a_healthy_shell_run_into_an_alert(monkeypatch: pytest.MonkeyPatch) -> None:
    """The incident: shell says ALL_HEALTHY, the canary is dark."""
    monkeypatch.setattr(run_module, "_evaluate_coverage_guarded", lambda now: [
        _Finding("felix-canary", "failure", "stale", "age 54003s vs max_age 2100s"),
        _Finding("restic-backup", "failure", "failed", "restic_exit_code=127 not in good_values [0, 3]"),
    ])
    _exit, payload, send = _run_main_with_script_result(monkeypatch, returncode=0, stdout="ALL_HEALTHY")
    assert payload["status"] == "FAILURES_DETECTED"
    assert payload["script_status"] == "ALL_HEALTHY"
    assert len(send.calls) == 1
    assert [f.component for f in send.kwargs[0]["findings"]] == ["felix-canary", "restic-backup"]


def test_coverage_raising_is_unknown_and_still_writes_the_record(monkeypatch: pytest.MonkeyPatch) -> None:
    """paula-6 / NFR-003: the real guarded seam, with the coverage module broken."""
    from scripts.office2.felix_health_check import coverage

    def boom(now):
        raise RuntimeError("coverage exploded")

    monkeypatch.setattr(coverage, "evaluate_coverage", boom)
    # The autouse fixture stubs the module attribute; _REAL_GUARD is the
    # original, captured at import, so the real guard runs here.
    findings = _REAL_GUARD(None)
    assert [f.finding for f in findings] == ["unknown", "unknown"]
    assert all("coverage exploded" in f.evidence for f in findings)
    assert [f.to_record()["outcome"] for f in findings] == ["unavailable", "unavailable"]


def test_shell_launch_failure_is_unknown_and_coverage_still_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    """Codex-6: any exception from launching or decoding the shell run."""
    monkeypatch.setattr(run_module.Path, "is_file", lambda self: True, raising=True)
    monkeypatch.setattr(run_module.os, "access", lambda path, mode: True, raising=True)

    def explode(script_path=None):
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")

    monkeypatch.setattr(run_module, "run_health_check_script", explode)
    send = _FakeSendAlert(_DELIVERY_SENT)
    monkeypatch.setattr(run_module, "send_alert", send)
    assert run_module.main([]) == 0
    payload = json.loads(Path(run_module.SIGNAL_FILE).read_text(encoding="utf-8"))
    assert payload["status"] == "UNKNOWN"
    assert payload["script_status"] == "UNKNOWN"
    assert payload["exit_code"] is None
    assert len(payload["coverage_checks"]) == 2
    assert "UnicodeDecodeError" in send.kwargs[0]["script_note"]


def test_main_never_raises_when_everything_breaks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run_module, "_evaluate_coverage_guarded", lambda now: [
        _Finding("felix-canary", "unknown", "unavailable", "x"),
        _Finding("restic-backup", "unknown", "unavailable", "x")])
    monkeypatch.setattr(run_module.Path, "is_file", lambda self: True, raising=True)
    monkeypatch.setattr(run_module.os, "access", lambda path, mode: True, raising=True)
    monkeypatch.setattr(run_module, "run_health_check_script",
                        lambda script_path=None: (_ for _ in ()).throw(OSError("exec format error")))
    monkeypatch.setattr(run_module, "send_alert", _FakeSendAlert(_DELIVERY_FAILED))
    assert run_module.main([]) == 0
    payload = json.loads(Path(run_module.SIGNAL_FILE).read_text(encoding="utf-8"))
    assert payload["status"] == "UNKNOWN"


def test_send_alert_raising_still_writes_the_record(monkeypatch: pytest.MonkeyPatch) -> None:
    """Review cycle 1 (MED): the record must survive a raising send_alert."""
    def boom(*_a, **_k):
        raise RuntimeError("bus exploded")

    monkeypatch.setattr(run_module.Path, "is_file", lambda self: True, raising=True)
    monkeypatch.setattr(run_module.os, "access", lambda path, mode: True, raising=True)
    monkeypatch.setattr(run_module, "run_health_check_script",
                        lambda script_path=None: _fake_completed(1, stdout="FAILURES_DETECTED"))
    monkeypatch.setattr(run_module, "send_alert", boom)
    assert run_module.main([]) == 0
    payload = json.loads(Path(run_module.SIGNAL_FILE).read_text(encoding="utf-8"))
    assert payload["status"] == "FAILURES_DETECTED"
    assert payload["delivery"]["sent"] is False
    assert "bus exploded" in payload["delivery"]["detail"]


def test_unserializable_finding_becomes_unknown_in_the_record(monkeypatch: pytest.MonkeyPatch) -> None:
    class Broken(_Finding):
        def to_record(self):
            raise ValueError("cannot serialize")

    monkeypatch.setattr(run_module, "_evaluate_coverage_guarded",
                        lambda now: [Broken("felix-canary"), _Finding("restic-backup")])
    _exit, payload, _send = _run_main_with_script_result(monkeypatch, returncode=0, stdout="ALL_HEALTHY")
    assert payload["coverage_checks"][0]["finding"] == "unknown"
    assert "cannot serialize" in payload["coverage_checks"][0]["evidence"]


def test_component_list_matches_the_coverage_module() -> None:
    """The duplicate in run.py exists for the import-failure case; pin it."""
    from scripts.office2.felix_health_check import coverage

    assert run_module._COVERAGE_COMPONENTS == coverage.COVERAGE_COMPONENTS
