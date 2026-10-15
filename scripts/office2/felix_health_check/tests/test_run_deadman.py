"""felix-health-check's off-host dead-man ping (#1077).

Liveness plus channel health, never the health of what is watched. Runs the
real ``main()`` with the existing seams (script runner, coverage, send_alert)
replaced, and records what is handed to ``deadman``.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts.office2.felix_health_check import run as run_module

SENT = {"attempted": True, "sent": True, "detail": "delivered"}
NOT_SENT_ERROR = {"attempted": True, "sent": False, "detail": "CURL_TIMEOUT"}
# A missing topic: the bus never attempts delivery (Codex post-plan round 1, HIGH).
NOT_SENT_NO_TOPIC = {"attempted": False, "sent": False, "detail": "NTFY_MISSING_TOPIC"}


class _Finding:
    def __init__(self, component, finding="ok", outcome="healthy", evidence="fixture"):
        self.component, self.finding, self.outcome, self.evidence = component, finding, outcome, evidence

    def to_record(self):
        return {"component": self.component, "outcome": self.outcome,
                "finding": self.finding, "evidence": self.evidence}


@pytest.fixture
def harness(tmp_path, monkeypatch):
    signal_file = tmp_path / "last-run.json"
    monkeypatch.setattr(run_module, "SIGNAL_FILE", signal_file)
    pings: list[tuple[str, str]] = []
    channel_calls: list[bool] = []
    state = {
        "script": ("ALL_HEALTHY", 0),  # (stdout, rc) or an exception instance
        "script_exists": True,
        "findings": [_Finding("felix-canary"), _Finding("restic-backup")],
        "delivery": SENT,
        "channel": (True, "ok"),
    }

    monkeypatch.setattr(run_module.Path, "is_file", lambda self: state["script_exists"])
    monkeypatch.setattr(run_module.os, "access", lambda p, m: state["script_exists"])

    def fake_script(script_path=run_module.HEALTH_CHECK_SCRIPT):
        if isinstance(state["script"], BaseException):
            raise state["script"]
        out, rc = state["script"]
        return subprocess.CompletedProcess(["bash"], rc, stdout=out, stderr="")

    monkeypatch.setattr(run_module, "run_health_check_script", fake_script)
    monkeypatch.setattr(run_module, "_evaluate_coverage_guarded", lambda now: state["findings"])
    monkeypatch.setattr(run_module, "send_alert", lambda *a, **k: dict(state["delivery"]))

    def fake_ping(label, outcome, **kw):
        pings.append((label, outcome))

    def fake_channel_ok(env, delivered_ok, **kw):
        channel_calls.append(delivered_ok)
        ok, why = state["channel"]
        return (ok and delivered_ok, why if not ok else ("undelivered" if not delivered_ok else "ok"))

    monkeypatch.setattr(run_module.deadman, "ping", fake_ping)
    monkeypatch.setattr(run_module.deadman, "channel_ok", fake_channel_ok)
    return state, pings, channel_calls, signal_file


def test_all_healthy_pings_success(harness):
    state, pings, calls, _ = harness
    assert run_module.main([]) == 0
    assert pings == [("healthcheck", "success")]
    assert calls == [True]


def test_failures_detected_and_delivered_still_pings_success(harness):
    """FR-004: the watcher ran and could alert."""
    state, pings, _, _ = harness
    state["script"] = ("FAILURES_DETECTED\nDOWN: vikunja-api (HTTP 500)\n", 0)
    assert run_module.main([]) == 0
    assert pings == [("healthcheck", "success")]


@pytest.mark.parametrize("delivery", [NOT_SENT_ERROR, NOT_SENT_NO_TOPIC], ids=["delivery_error", "missing_topic"])
def test_alerting_run_whose_alert_was_not_delivered_pings_fail(harness, delivery):
    state, pings, calls, _ = harness
    state["script"] = ("FAILURES_DETECTED\nDOWN: x (inactive)\n", 0)
    state["delivery"] = delivery
    assert run_module.main([]) == 0
    assert calls == [False]
    assert pings == [("healthcheck", "fail")]


def test_healthy_run_with_broken_channel_pings_fail(harness):
    state, pings, _, _ = harness
    state["channel"] = (False, "topic_missing")
    assert run_module.main([]) == 0
    assert pings == [("healthcheck", "fail")]


def test_script_missing_pings_fail(harness):
    state, pings, _, _ = harness
    state["script_exists"] = False
    assert run_module.main([]) == 0
    assert pings == [("healthcheck", "fail")]


@pytest.mark.parametrize(
    "exc",
    [subprocess.TimeoutExpired(["bash"], 120), OSError("exec format error")],
    ids=["timeout", "launch_failure"],
)
def test_script_that_did_not_run_pings_fail(harness, exc):
    state, pings, _, _ = harness
    state["script"] = exc
    assert run_module.main([]) == 0
    assert pings == [("healthcheck", "fail")]


@pytest.mark.parametrize(
    "evidence",
    ["coverage unavailable: ImportError: boom", "coverage could not start: RuntimeError: x"],
)
def test_coverage_that_could_not_run_pings_fail(harness, evidence):
    state, pings, _, _ = harness
    state["findings"] = [
        _Finding("felix-canary", "unknown", "unavailable", evidence),
        _Finding("restic-backup", "unknown", "unavailable", evidence),
    ]
    assert run_module.main([]) == 0
    assert pings == [("healthcheck", "fail")]


def test_record_write_failure_pings_fail_then_raises(harness, monkeypatch):
    state, pings, _, _ = harness

    def broken(path, payload):
        raise OSError("read-only file system")

    monkeypatch.setattr(run_module, "_atomic_write_json", broken)
    with pytest.raises(OSError):
        run_module.main([])
    assert pings == [("healthcheck", "fail")]


def test_run_record_is_unchanged_by_the_deadman(harness, monkeypatch):
    """C-004: last-run.json carries exactly the pre-#1077 key set."""
    state, _, _, signal_file = harness
    run_module.main([])
    record = json.loads(signal_file.read_text())
    assert set(record) == {
        "status", "ran_at_utc", "exit_code", "delivery", "script_status",
        "script_path", "coverage_checks",
    }


def test_a_raising_deadman_never_changes_the_exit_code(harness, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(run_module.deadman, "ping", boom)
    monkeypatch.setattr(run_module.deadman, "channel_ok", boom)
    assert run_module.main([]) == 0
