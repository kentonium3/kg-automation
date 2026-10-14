"""The run-record and alert contract (#1063;
kitty-specs/canary-deadman-backup-coverage-01M4XVY3/contracts/health-check-run-record.md).

felix-canary watches this component by probing ``last-run.json`` through its
legacy ``signal-file`` path (#891). That path keys on bare top-level names:
``_explicit_error``'s vocabulary, and ``TIMESTAMP_KEYS``, where the first
parseable key wins. Adding a key to the record can therefore silently change
how the canary judges the health check. The canary's own completion
timestamp, hoisted here, would make it judge this runner's freshness by the
canary's clock. These tests drive the canary's real probe over records the
real ``main()`` wrote.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.canary import probes, registry
from scripts.common.alert_bus import Alert, Severity
from scripts.common.alert_bus.render import DETAIL_VALUE_MAX, render_body
from scripts.office2.felix_health_check import coverage
from scripts.office2.felix_health_check import run as run_module

_LEGACY_ERROR_KEYS = {"restic_exit_code", "prune_exit_code", "exit_status", "errors", "error", "cycle_error"}
# Derived from the canary at runtime, never copied (paula-2): every timestamp
# key that would outrank ran_at_utc as this record's freshness anchor.
_OUTRANKING_TS_KEYS = probes.TIMESTAMP_KEYS[: probes.TIMESTAMP_KEYS.index("ran_at_utc")]


class _F:
    def __init__(self, component, finding="ok", outcome="healthy", evidence="fixture"):
        self.component, self.finding, self.outcome, self.evidence = component, finding, outcome, evidence

    def to_record(self):
        return {"component": self.component, "outcome": self.outcome,
                "finding": self.finding, "evidence": self.evidence}


OK = [_F("felix-canary"), _F("restic-backup")]
FAILING = [_F("felix-canary", "failure", "stale", "ts completed_at_utc=2026-09-27T15:52:00+00:00, age 54003s"),
           _F("restic-backup", "failure", "failed", "restic_exit_code=127 not in good_values [0, 3]")]
BLIND = [_F("felix-canary", "unknown", "unavailable", "coverage unavailable"),
         _F("restic-backup", "unknown", "unavailable", "coverage unavailable")]


def _write_record(tmp_path, monkeypatch, *, findings, returncode=0, stdout="ALL_HEALTHY",
                  script_exists=True, raise_exc=None) -> dict:
    signal = tmp_path / "last-run.json"
    monkeypatch.setattr(run_module, "SIGNAL_FILE", signal)
    monkeypatch.setattr(run_module, "_evaluate_coverage_guarded", lambda now: findings)
    monkeypatch.setattr(run_module.Path, "is_file", lambda self: script_exists, raising=True)
    monkeypatch.setattr(run_module.os, "access", lambda p, m: script_exists, raising=True)

    def fake_run(script_path=None):
        if raise_exc is not None:
            raise raise_exc
        return subprocess.CompletedProcess(args=["bash"], returncode=returncode, stdout=stdout, stderr="")

    monkeypatch.setattr(run_module, "run_health_check_script", fake_run)
    monkeypatch.setattr(run_module, "send_alert",
                        lambda *a, **k: {"attempted": True, "sent": True, "detail": "delivered"})
    assert run_module.main([]) == 0
    return json.loads(signal.read_text(encoding="utf-8"))


def _health_check_declaration() -> dict:
    targets, _gaps = registry.load_targets(registry.load_inventory(coverage.INVENTORY_PATH))
    return next(t for t in targets if t.component_id == "felix-health-check").health_check


def _canary_probe(record: dict, now: datetime | None = None) -> probes.ProbeResult:
    ran = datetime.fromisoformat(record["ran_at_utc"].replace("Z", "+00:00"))
    return probes.run_probe(_health_check_declaration(), now or ran + timedelta(minutes=1),
                            http_get=None, run_cmd=None, read_state=lambda _p: record)


# --- Invariant 3: the canary's verdict on the health check -------------------

@pytest.mark.parametrize("case, kwargs, healthy", [
    ("(a) all healthy", dict(findings=OK), True),
    ("(b) coverage failure, shell exit 0", dict(findings=FAILING), True),
    ("(c) coverage unknown", dict(findings=BLIND), False),
    ("(d) coverage failure, shell exit 1",
     dict(findings=FAILING, returncode=1, stdout="FAILURES_DETECTED\nDOWN: vikunja.service"), False),
])
def test_canary_judges_records_written_by_main(tmp_path, monkeypatch, case, kwargs, healthy):
    record = _write_record(tmp_path, monkeypatch, **kwargs)
    result = _canary_probe(record)
    assert (result.ok and not result.stale and result.evaluable) is healthy, f"{case}: {result.evidence}"
    if healthy:
        assert "ran_at_utc" in result.evidence, f"{case}: anchored elsewhere: {result.evidence}"


def test_canary_still_sees_a_stale_runner(tmp_path, monkeypatch):
    record = _write_record(tmp_path, monkeypatch, findings=OK)
    ran = datetime.fromisoformat(record["ran_at_utc"].replace("Z", "+00:00"))
    assert _canary_probe(record, now=ran + timedelta(hours=14)).stale


# --- Invariants 1-2: no new key can hijack the probe -------------------------

@pytest.mark.parametrize("findings", [OK, FAILING, BLIND], ids=["ok", "failing", "blind"])
def test_record_avoids_the_canary_vocabulary(tmp_path, monkeypatch, findings):
    record = _write_record(tmp_path, monkeypatch, findings=findings)
    assert not set(record) & _LEGACY_ERROR_KEYS
    assert not set(record) & set(_OUTRANKING_TS_KEYS)
    for entry in record["coverage_checks"]:
        assert set(entry) == {"component", "outcome", "finding", "evidence"}


@pytest.mark.parametrize("key", _OUTRANKING_TS_KEYS)
def test_an_outranking_timestamp_would_hijack_the_anchor(tmp_path, monkeypatch, key):
    """Non-vacuity control: the guard above matters, because each of these keys
    really would replace ran_at_utc as the probe's anchor."""
    record = _write_record(tmp_path, monkeypatch, findings=OK)
    assert "ran_at_utc" in _canary_probe(record).evidence
    record[key] = "2020-01-01T00:00:00Z"
    hijacked = _canary_probe(record)
    assert "ran_at_utc" not in hijacked.evidence and key in hijacked.evidence


@pytest.mark.parametrize("key", sorted(_LEGACY_ERROR_KEYS))
def test_a_legacy_error_key_would_fail_the_runner(tmp_path, monkeypatch, key):
    record = _write_record(tmp_path, monkeypatch, findings=OK)
    record[key] = 127 if key.endswith("exit_code") else "boom"
    if key == "exit_status":
        record[key] = "failure"
    assert not _canary_probe(record).ok


def test_outranking_keys_are_derived_not_empty():
    assert "completed_at_utc" in _OUTRANKING_TS_KEYS


# --- Invariant 4: coverage_checks on every record ----------------------------

@pytest.mark.parametrize("kwargs", [
    dict(findings=OK, script_exists=False),
    dict(findings=OK, raise_exc=subprocess.TimeoutExpired(cmd="bash", timeout=300)),
    dict(findings=OK, raise_exc=OSError("exec format error")),
    dict(findings=BLIND),
], ids=["script-missing", "timeout", "launch-failure", "coverage-unavailable"])
def test_coverage_checks_on_every_record(tmp_path, monkeypatch, kwargs):
    record = _write_record(tmp_path, monkeypatch, **kwargs)
    assert [c["component"] for c in record["coverage_checks"]] == ["felix-canary", "restic-backup"]


# --- Alert details survive the bus renderer (Codex-3, paula-5) ---------------

def _render(details: dict) -> str:
    return render_body(Alert(source=run_module.ALERT_SOURCE, severity=Severity.ERROR,
                             title=run_module.ALERT_TITLE, description="d", details=details))


def test_findings_survive_long_shell_output():
    output = "FAILURES_DETECTED\n" + "DOWN: filler\n" * 600  # > 6 KB
    details = run_module.alert_details("FAILURES_DETECTED", run_module._truncate(output), FAILING,
                                       script_note="Health-check script not found or not executable: x")
    body = _render(details)
    assert "restic_exit_code=127" in body
    assert "age 54003s" in body
    assert "script=Health-check script not found" in body
    assert list(details)[:3] == ["script", "coverage:felix-canary", "coverage:restic-backup"]


def test_appending_findings_to_the_output_would_lose_them():
    """Non-vacuity control: the shape the plan replaced really does drop them."""
    output = "FAILURES_DETECTED\n" + "DOWN: filler\n" * 600
    folded = output + "\n" + "\n".join(f.evidence for f in FAILING)
    body = _render({"status": "FAILURES_DETECTED", "output": folded})
    assert "restic_exit_code=127" not in body
    assert len(folded) > DETAIL_VALUE_MAX


def test_ok_findings_add_no_details():
    details = run_module.alert_details("UNKNOWN", "out", OK)
    assert list(details) == ["status", "output"]
