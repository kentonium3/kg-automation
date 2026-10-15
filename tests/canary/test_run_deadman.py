"""felix-canary's off-host dead-man ping (#1077).

The ping is liveness plus channel health, never component health. These tests
drive the real ``run_pass`` through ``main()`` (the existing CLI pattern) and
record what the canary hands to ``deadman``; ``deadman`` itself is covered in
``tests/common/test_deadman.py``.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.canary import run as run_mod
from scripts.canary.health import HealthResult
from scripts.common.alert_bus import Severity

NOW = datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc)

# The persisted TickSignal key set before #1077 -- it must not change.
TICK_SIGNAL_KEYS = {
    "status", "completed_at_utc", "components_evaluated", "emitted",
    "suppressed_dedup", "coverage_gaps", "suppressed_status", "errors",
    "duration_ms",
}


class _Result:
    def __init__(self, ok: bool):
        self.ok = ok
        self.reason = None if ok else "NTFY_MISSING_TOPIC"


def _inventory(*ids: str) -> dict:
    return {"services": [
        {"id": i, "name": i, "type": "systemd-timer", "status": "active",
         "health_check": {"method": "http", "endpoint": "http://x", "timeout_seconds": 1}}
        for i in ids
    ]}


def _evaluate(outcomes: dict[str, str]):
    def fn(target, now, *, http_get, run_cmd, read_state):
        outcome = outcomes.get(target.component_id, "healthy")
        return HealthResult(
            component_id=target.component_id, outcome=outcome, alert_eligible=True,
            should_emit=outcome != "healthy",
            severity=Severity.ERROR if outcome != "healthy" else None,
            evidence=f"{outcome} evidence", evaluated_at=now.isoformat(),
        )
    return fn


@pytest.fixture
def harness(tmp_path, monkeypatch):
    """Route main() to a real run_pass with injected effects; record deadman calls."""
    pings: list[tuple[str, str]] = []
    channel_calls: list[bool] = []
    state = {"channel": (True, "ok"), "outcomes": {}, "emit_ok": True, "raise": False}

    def fake_ping(label, outcome, **kw):
        pings.append((label, outcome))

    def fake_channel_ok(env, delivered_ok, **kw):
        channel_calls.append(delivered_ok)
        ok, why = state["channel"]
        if ok and not delivered_ok:
            return False, "undelivered"
        return ok, why

    monkeypatch.setattr(run_mod.deadman, "ping", fake_ping)
    monkeypatch.setattr(run_mod.deadman, "channel_ok", fake_channel_ok)
    real_run_pass = run_mod.run_pass

    def fake_run_pass(*, now, dry_run):
        if state["raise"]:
            raise RuntimeError("inventory unreadable")
        return real_run_pass(
            now=NOW, dry_run=dry_run, inventory=_inventory("a", "b"),
            evaluate_fn=_evaluate(state["outcomes"]),
            emit_fn=lambda alert: _Result(state["emit_ok"]),
            dedup_path=tmp_path / "dedup.json", tick_path=tmp_path / "last-tick.json",
            ledger_dir=tmp_path / "ledger",
        )

    monkeypatch.setattr(run_mod, "run_pass", fake_run_pass)
    return state, pings, channel_calls, tmp_path


def test_healthy_tick_pings_success(harness):
    state, pings, calls, _ = harness
    assert run_mod.main(["--once"]) == 0
    assert pings == [("canary", "success")]
    assert calls == [True]


def test_unhealthy_components_with_delivered_alerts_still_ping_success(harness):
    """FR-004: liveness, not health."""
    state, pings, calls, _ = harness
    state["outcomes"] = {"a": "failed"}
    assert run_mod.main(["--once"]) == 0
    assert pings == [("canary", "success")]


def test_undelivered_alert_pings_fail(harness):
    state, pings, calls, _ = harness
    state["outcomes"] = {"a": "failed"}
    state["emit_ok"] = False
    assert run_mod.main(["--once"]) == 0
    assert calls == [False]
    assert pings == [("canary", "fail")]


def test_broken_channel_pings_fail_even_with_nothing_to_send(harness):
    state, pings, _, _ = harness
    state["channel"] = (False, "topic_missing")
    assert run_mod.main(["--once"]) == 0
    assert pings == [("canary", "fail")]


def test_runner_failure_pings_fail_and_keeps_exit_1(harness):
    state, pings, _, _ = harness
    state["raise"] = True
    assert run_mod.main(["--once"]) == 1
    assert pings == [("canary", "fail")]


def test_pass_status_error_pings_fail(harness, monkeypatch):
    state, pings, _, tmp = harness
    real = run_mod._write_tick_signal

    def broken(path, signal):
        raise OSError("disk full")

    monkeypatch.setattr(run_mod, "_write_tick_signal", broken)
    assert run_mod.main(["--once"]) == 0
    assert pings == [("canary", "fail")]
    monkeypatch.setattr(run_mod, "_write_tick_signal", real)


def test_dry_run_and_self_check_never_ping(harness, monkeypatch):
    state, pings, _, _ = harness
    assert run_mod.main(["--dry-run"]) == 0
    monkeypatch.setattr(run_mod, "_self_check", lambda *a: (True, ""))
    assert run_mod.main(["--self-check"]) == 0
    assert pings == []


def test_tick_signal_schema_is_unchanged(harness):
    state, _, _, tmp = harness
    state["outcomes"] = {"a": "failed"}
    state["emit_ok"] = False
    run_mod.main(["--once"])
    signal = json.loads((tmp / "last-tick.json").read_text())
    assert set(signal) == TICK_SIGNAL_KEYS
    assert "alerts_undelivered" not in signal


def test_summary_counts_undelivered(tmp_path):
    summary = run_mod.run_pass(
        now=NOW, inventory=_inventory("a", "b", "c"),
        evaluate_fn=_evaluate({"a": "failed", "b": "failed"}),
        emit_fn=lambda alert: _Result(alert.details["component_id"] != "a"),
        dedup_path=tmp_path / "d.json", tick_path=tmp_path / "t.json",
        ledger_dir=tmp_path / "l",
    )
    assert summary["emitted"] == 2
    assert summary["alerts_undelivered"] == 1


def test_a_raising_deadman_never_changes_the_exit_code(harness, monkeypatch):
    state, _, _, _ = harness

    def boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(run_mod.deadman, "ping", boom)
    monkeypatch.setattr(run_mod.deadman, "channel_ok", boom)
    assert run_mod.main(["--once"]) == 0
    state["raise"] = True
    assert run_mod.main(["--once"]) == 1
