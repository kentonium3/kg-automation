"""Unit tests for scripts.canary.health.evaluate.

All effects are injected. The headline test proves **gate-before-probe**: a
non-alert-eligible target returns ``suppressed`` and NONE of the injected
callables are invoked. ``now`` is always injected, never ``datetime.now()``.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from scripts.canary.health import HealthResult, evaluate
from scripts.canary.registry import CanaryTarget
from scripts.common.alert_bus import Severity

NOW = datetime(2026, 7, 11, 12, 0, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# Recording effect fakes.
# --------------------------------------------------------------------------- #
def make_http(return_value=None, raises=None):
    calls = []

    def http_get(endpoint, timeout=None):
        calls.append((endpoint, timeout))
        if raises is not None:
            raise raises
        return return_value

    http_get.calls = calls
    return http_get


def make_cmd(result=(0, "", ""), raises=None):
    calls = []

    def run_cmd(endpoint, timeout=None):
        calls.append((endpoint, timeout))
        if raises is not None:
            raise raises
        return result

    run_cmd.calls = calls
    return run_cmd


def make_state(payload=None, raises=None):
    calls = []

    def read_state(path):
        calls.append(path)
        if raises is not None:
            raise raises
        return payload

    read_state.calls = calls
    return read_state


def _boom(*_a, **_k):
    raise AssertionError("effect should not have been called")


def target(*, alert_eligible=True, status="active", method="http",
           health_check=None, component_id="comp-x"):
    hc = health_check
    if hc is None and method is not None:
        hc = {"method": method, "endpoint": "x", "expected": 200}
    return CanaryTarget(
        component_id=component_id,
        type="docker",
        status=status,
        alert_eligible=alert_eligible,
        health_check=hc,
        pointer_path=None,
    )


# --------------------------------------------------------------------------- #
# GATE-BEFORE-PROBE (the load-bearing test for F6 / INV-A).
# --------------------------------------------------------------------------- #
def test_suppressed_target_returns_suppressed_without_probing():
    http = make_http(200)
    cmd = make_cmd((0, "", ""))
    state = make_state({"completed_at_utc": "2026-07-11T11:59:00Z"})
    tgt = target(alert_eligible=False, status="suspended")

    result = evaluate(tgt, NOW, http_get=http, run_cmd=cmd, read_state=state)

    assert result.outcome == "suppressed"
    assert result.should_emit is False
    assert result.severity is None
    assert result.alert_eligible is False
    # The proof: no injected effect was ever called → the gate ran before any probe.
    assert http.calls == []
    assert cmd.calls == []
    assert state.calls == []


def test_suppressed_uses_boom_effects_to_prove_no_probe():
    # Even effects that would raise if touched are safe on the suppressed path.
    tgt = target(alert_eligible=False, status="deprecated")
    result = evaluate(tgt, NOW, http_get=_boom, run_cmd=_boom, read_state=_boom)
    assert result.outcome == "suppressed"


# --------------------------------------------------------------------------- #
# Outcome → severity / should_emit mapping (alert-eligible).
# --------------------------------------------------------------------------- #
def test_healthy_maps_to_none_severity_no_emit():
    tgt = target(method="http")
    result = evaluate(tgt, NOW, http_get=make_http(200),
                      run_cmd=_boom, read_state=_boom)
    assert result.outcome == "healthy"
    assert result.severity is None
    assert result.should_emit is False
    assert result.alert_eligible is True


def test_failed_maps_to_error_and_emits():
    tgt = target(method="http")
    result = evaluate(tgt, NOW, http_get=make_http(503),
                      run_cmd=_boom, read_state=_boom)
    assert result.outcome == "failed"
    assert result.severity is Severity.ERROR
    assert result.should_emit is True


def test_stale_maps_to_error_and_emits():
    tgt = target(method="state-file",
                 health_check={"method": "state-file", "endpoint": "/x/p.json",
                               "max_age_seconds": 3600})
    old = make_state({"completed_at_utc": "2026-07-10T00:00:00Z"})  # >1h
    result = evaluate(tgt, NOW, http_get=_boom, run_cmd=_boom, read_state=old)
    assert result.outcome == "stale"
    assert result.severity is Severity.ERROR
    assert result.should_emit is True


def test_unknown_maps_to_warn_but_does_not_emit_here():
    # WP04's persistence layer flips should_emit once unknown persists.
    tgt = target(method="http")
    result = evaluate(tgt, NOW,
                      http_get=make_http(raises=ConnectionError("refused")),
                      run_cmd=_boom, read_state=_boom)
    assert result.outcome == "unknown"
    assert result.severity is Severity.WARN
    assert result.should_emit is False


def test_uninterpretable_pointer_is_unknown_not_healthy():
    tgt = target(method="state-file",
                 health_check={"method": "state-file",
                               "endpoint": "/x/seen-findings.json",
                               "max_age_seconds": 2100})
    bare_map = make_state({"fp_a": {}, "fp_b": {}})
    result = evaluate(tgt, NOW, http_get=_boom, run_cmd=_boom, read_state=bare_map)
    assert result.outcome == "unknown"
    assert result.severity is Severity.WARN


# --------------------------------------------------------------------------- #
# Fail-safe: a probe that raises → unknown, never escapes evaluate (INV-D).
# --------------------------------------------------------------------------- #
def test_probe_exception_becomes_unknown_no_raise():
    tgt = target(method="shell",
                 health_check={"method": "shell", "endpoint": "/x"})
    # run_cmd raises → probes.run_probe catches → unknown; evaluate never raises.
    result = evaluate(tgt, NOW, http_get=_boom,
                      run_cmd=make_cmd(raises=OSError("spawn failed")),
                      read_state=_boom)
    assert isinstance(result, HealthResult)
    assert result.outcome == "unknown"
    assert result.severity is Severity.WARN
    assert result.should_emit is False


# --------------------------------------------------------------------------- #
# HealthResult shape / evaluated_at from injected now.
# --------------------------------------------------------------------------- #
def test_evaluated_at_is_isoformat_of_injected_now():
    tgt = target(method="http")
    result = evaluate(tgt, NOW, http_get=make_http(200),
                      run_cmd=_boom, read_state=_boom)
    assert result.evaluated_at == NOW.isoformat()
    assert result.component_id == "comp-x"


def test_should_emit_implies_alert_eligible_invariant():
    # INV-A: should_emit ⟹ alert_eligible, across a representative set.
    cases = [
        evaluate(target(alert_eligible=False, status="planned"), NOW,
                 http_get=_boom, run_cmd=_boom, read_state=_boom),
        evaluate(target(method="http"), NOW, http_get=make_http(200),
                 run_cmd=_boom, read_state=_boom),
        evaluate(target(method="http"), NOW, http_get=make_http(503),
                 run_cmd=_boom, read_state=_boom),
    ]
    for result in cases:
        if result.should_emit:
            assert result.alert_eligible is True
