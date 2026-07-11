"""Unit tests for scripts.canary.probes.

Every effect is injected — no network, no subprocess, no real filesystem. The
``health_check`` shapes and freshness-pointer payloads below are copied from
real ``service-inventory.json`` entries and their real pointer files (restic
``last-backup.json``, the canary runner's ``last-tick.json``, trust-scan's
``seen-findings.json`` map, agent-prompt-sync's JSONL log surfaced as a list).

``now`` is always injected, never ``datetime.now()``.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from scripts.canary.probes import (
    TIMESTAMP_KEYS,
    ProbeResult,
    run_probe,
)

NOW = datetime(2026, 7, 11, 12, 0, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# Injectable effect fakes. Each records its calls so tests can assert the probe
# used the right effect (and only that one).
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


# --------------------------------------------------------------------------- #
# http
# --------------------------------------------------------------------------- #
def test_http_healthy_status_matches_expected():
    hc = {"method": "http", "endpoint": "http://x/health",
          "expected": 200, "timeout_seconds": 5}
    result = run_probe(hc, NOW, http_get=make_http(200),
                       run_cmd=_boom, read_state=_boom)
    assert result == ProbeResult(ok=True, stale=False, evaluable=True,
                                 evidence=result.evidence)
    assert result.ok and result.evaluable


def test_http_failed_status_mismatch():
    hc = {"method": "http", "endpoint": "http://x/health", "expected": 200}
    result = run_probe(hc, NOW, http_get=make_http(503),
                       run_cmd=_boom, read_state=_boom)
    assert result.evaluable and not result.ok
    assert "503" in result.evidence


def test_http_connection_error_is_unknown():
    hc = {"method": "http", "endpoint": "http://x/health", "expected": 200}
    result = run_probe(hc, NOW, http_get=make_http(raises=ConnectionError("refused")),
                       run_cmd=_boom, read_state=_boom)
    assert not result.evaluable
    assert "ConnectionError" in result.evidence


def test_http_passes_timeout_through():
    http = make_http(200)
    hc = {"method": "http", "endpoint": "http://x", "expected": 200,
          "timeout_seconds": 7}
    run_probe(hc, NOW, http_get=http, run_cmd=_boom, read_state=_boom)
    assert http.calls == [("http://x", 7)]


# --------------------------------------------------------------------------- #
# shell / self-check-command / self-test (liveness by exit code)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("method", ["shell", "self-check-command", "self-test"])
def test_command_healthy_on_exit_zero(method):
    hc = {"method": method, "endpoint": "/usr/bin/true"}
    result = run_probe(hc, NOW, http_get=_boom,
                       run_cmd=make_cmd((0, "ok", "")), read_state=_boom)
    assert result.ok and result.evaluable and not result.stale


@pytest.mark.parametrize("method", ["shell", "self-check-command", "self-test"])
def test_command_failed_on_nonzero_exit(method):
    hc = {"method": method, "endpoint": "/usr/bin/false"}
    result = run_probe(hc, NOW, http_get=_boom,
                       run_cmd=make_cmd((1, "", "boom")), read_state=_boom)
    assert result.evaluable and not result.ok
    assert "exit 1" in result.evidence


def test_command_spawn_error_is_unknown():
    hc = {"method": "shell", "endpoint": "/nope"}
    result = run_probe(hc, NOW, http_get=_boom,
                       run_cmd=make_cmd(raises=FileNotFoundError("no such file")),
                       read_state=_boom)
    assert not result.evaluable
    assert "FileNotFoundError" in result.evidence


# --------------------------------------------------------------------------- #
# systemd-status
# --------------------------------------------------------------------------- #
def test_systemd_active_is_healthy():
    hc = {"method": "systemd-status", "endpoint": "systemctl --user status x"}
    result = run_probe(
        hc, NOW, http_get=_boom,
        run_cmd=make_cmd((0, "Active: active (running) since ...", "")),
        read_state=_boom,
    )
    assert result.ok and result.evaluable


def test_systemd_inactive_is_failed():
    hc = {"method": "systemd-status", "endpoint": "systemctl --user status x"}
    result = run_probe(
        hc, NOW, http_get=_boom,
        run_cmd=make_cmd((3, "Active: inactive (dead)", "")),
        read_state=_boom,
    )
    assert result.evaluable and not result.ok


def test_systemd_spawn_error_is_unknown():
    hc = {"method": "systemd-status", "endpoint": "systemctl --user status x"}
    result = run_probe(hc, NOW, http_get=_boom,
                       run_cmd=make_cmd(raises=OSError("systemctl missing")),
                       read_state=_boom)
    assert not result.evaluable


# --------------------------------------------------------------------------- #
# Freshness pointer — candidate-key resolution + staleness boundary
# --------------------------------------------------------------------------- #
def test_freshness_fresh_within_max_age_completed_at_utc():
    # canary runner's own last-tick.json uses completed_at_utc.
    pointer = {"status": "success",
               "completed_at_utc": "2026-07-11T11:45:00Z"}  # 15 min old
    hc = {"method": "tick-signal-file", "state_path": "/x/last-tick.json",
          "max_age_seconds": 2100}
    result = run_probe(hc, NOW, http_get=_boom, run_cmd=_boom,
                       read_state=make_state(pointer))
    assert result.ok and result.evaluable and not result.stale


def test_freshness_stale_past_max_age_snapshot_timestamp_utc():
    # restic last-backup.json uses snapshot_timestamp_utc (WP05 state-file).
    pointer = {"restic_exit_code": 0,
               "snapshot_timestamp_utc": "2026-07-10T11:00:00Z"}  # ~25h old
    hc = {"method": "state-file", "endpoint": "/x/last-backup.json",
          "max_age_seconds": 100800}  # 28h — still fresh at 25h? no: 25h < 28h
    # Make it stale: shrink max_age below the age.
    hc["max_age_seconds"] = 3600  # 1h; age ~25h → stale
    result = run_probe(hc, NOW, http_get=_boom, run_cmd=_boom,
                       read_state=make_state(pointer))
    assert result.ok and result.evaluable and result.stale


def test_freshness_boundary_exactly_at_max_age_is_not_stale():
    # age == max_age → not stale (strict > boundary).
    pointer = {"completed_at_utc": "2026-07-11T11:00:00Z"}  # exactly 3600s old
    hc = {"method": "signal-file", "endpoint": "/x/p.json", "max_age_seconds": 3600}
    result = run_probe(hc, NOW, http_get=_boom, run_cmd=_boom,
                       read_state=make_state(pointer))
    assert not result.stale and result.ok


def test_freshness_just_past_boundary_is_stale():
    pointer = {"completed_at_utc": "2026-07-11T10:59:59Z"}  # 3601s old
    hc = {"method": "signal-file", "endpoint": "/x/p.json", "max_age_seconds": 3600}
    result = run_probe(hc, NOW, http_get=_boom, run_cmd=_boom,
                       read_state=make_state(pointer))
    assert result.stale


def test_freshness_candidate_key_order_prefers_first_present():
    # completed_at_utc precedes snapshot_timestamp_utc in TIMESTAMP_KEYS.
    assert TIMESTAMP_KEYS.index("completed_at_utc") < TIMESTAMP_KEYS.index(
        "snapshot_timestamp_utc"
    )
    pointer = {"snapshot_timestamp_utc": "2020-01-01T00:00:00Z",
               "completed_at_utc": "2026-07-11T11:59:00Z"}  # 1 min old
    hc = {"method": "state-file", "endpoint": "/x/p.json", "max_age_seconds": 2100}
    result = run_probe(hc, NOW, http_get=_boom, run_cmd=_boom,
                       read_state=make_state(pointer))
    # If it had used snapshot_timestamp_utc (2020) it would be stale; it isn't.
    assert not result.stale
    assert "completed_at_utc" in result.evidence


def test_freshness_no_max_age_is_liveness_only():
    pointer = {"completed_at_utc": "2000-01-01T00:00:00Z"}  # ancient, but…
    hc = {"method": "tick-signal-file", "endpoint": "/x/p.json"}  # no max_age
    result = run_probe(hc, NOW, http_get=_boom, run_cmd=_boom,
                       read_state=make_state(pointer))
    assert result.ok and not result.stale and result.evaluable
    assert "liveness only" in result.evidence


# --- explicit-error detection ------------------------------------------------ #
def test_freshness_restic_exit_code_nonzero_is_failed():
    pointer = {"restic_exit_code": 1,
               "snapshot_timestamp_utc": "2026-07-11T11:59:00Z"}
    hc = {"method": "state-file", "endpoint": "/x/last-backup.json",
          "max_age_seconds": 100800}
    result = run_probe(hc, NOW, http_get=_boom, run_cmd=_boom,
                       read_state=make_state(pointer))
    assert result.evaluable and not result.ok
    assert "restic_exit_code=1" in result.evidence


def test_freshness_restic_exit_code_3_is_ok():
    # 3 = "some source files unreadable" — snapshot still completed.
    pointer = {"restic_exit_code": 3,
               "snapshot_timestamp_utc": "2026-07-11T11:59:00Z"}
    hc = {"method": "state-file", "endpoint": "/x/last-backup.json",
          "max_age_seconds": 100800}
    result = run_probe(hc, NOW, http_get=_boom, run_cmd=_boom,
                       read_state=make_state(pointer))
    assert result.ok


def test_freshness_truthy_errors_field_is_failed():
    pointer = {"completed_at_utc": "2026-07-11T11:59:00Z",
               "errors": ["disk full"]}
    hc = {"method": "state-file", "endpoint": "/x/p.json", "max_age_seconds": 2100}
    result = run_probe(hc, NOW, http_get=_boom, run_cmd=_boom,
                       read_state=make_state(pointer))
    assert result.evaluable and not result.ok
    assert "errors" in result.evidence


# --- uninterpretable pointer shapes → unknown -------------------------------- #
def test_freshness_bare_map_no_timestamp_is_unknown():
    # felix-trust-scan seen-findings.json: a fingerprint→record map with no
    # top-level timestamp key. Must be unknown, never a false healthy.
    pointer = {"fp_abc123": {"first_seen": "..."},
               "fp_def456": {"first_seen": "..."}}
    hc = {"method": "state-file", "endpoint": "/x/seen-findings.json",
          "max_age_seconds": 2100}
    result = run_probe(hc, NOW, http_get=_boom, run_cmd=_boom,
                       read_state=make_state(pointer))
    assert not result.evaluable
    assert "no interpretable timestamp key" in result.evidence


def test_freshness_non_dict_payload_is_unknown():
    # agent-prompt-sync JSONL surfaced as a list → not a flat pointer.
    hc = {"method": "tick-signal-file", "endpoint": "/x/audit.jsonl",
          "max_age_seconds": 2100}
    result = run_probe(hc, NOW, http_get=_boom, run_cmd=_boom,
                       read_state=make_state([{"tick_summary": {}}]))
    assert not result.evaluable
    assert "not a JSON object" in result.evidence


def test_freshness_read_error_is_unknown():
    hc = {"method": "state-file", "endpoint": "/x/missing.json",
          "max_age_seconds": 2100}
    result = run_probe(hc, NOW, http_get=_boom, run_cmd=_boom,
                       read_state=make_state(raises=FileNotFoundError("gone")))
    assert not result.evaluable
    assert "FileNotFoundError" in result.evidence


# --------------------------------------------------------------------------- #
# log-scan (log-tail / journal)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("method", ["log-tail", "journal"])
def test_log_scan_marker_present_is_healthy(method):
    hc = {"method": method, "endpoint": "journalctl -u x | grep OK",
          "expected": "OK"}
    result = run_probe(hc, NOW, http_get=_boom,
                       run_cmd=make_cmd((0, "2026-07-11T11:59:00Z OK done", "")),
                       read_state=_boom)
    assert result.ok and result.evaluable and not result.stale


def test_log_scan_marker_absent_is_failed():
    hc = {"method": "log-tail", "endpoint": "tail x | grep OK", "expected": "OK"}
    result = run_probe(hc, NOW, http_get=_boom,
                       run_cmd=make_cmd((0, "nothing here", "")),
                       read_state=_boom)
    assert result.evaluable and not result.ok


def test_log_scan_stale_when_marker_line_older_than_max_age():
    hc = {"method": "journal", "endpoint": "journalctl -u x | grep OK",
          "expected": "OK", "max_age_seconds": 3600}
    result = run_probe(
        hc, NOW, http_get=_boom,
        run_cmd=make_cmd((0, "2026-07-10T00:00:00Z OK ran", "")),  # >1h old
        read_state=_boom,
    )
    assert result.ok and result.stale


def test_log_scan_command_error_with_output_is_failed():
    hc = {"method": "log-tail", "endpoint": "journalctl -u x", "expected": "OK"}
    result = run_probe(hc, NOW, http_get=_boom,
                       run_cmd=make_cmd((1, "", "permission denied")),
                       read_state=_boom)
    assert result.evaluable and not result.ok


def test_log_scan_spawn_error_is_unknown():
    hc = {"method": "journal", "endpoint": "journalctl -u x"}
    result = run_probe(hc, NOW, http_get=_boom,
                       run_cmd=make_cmd(raises=OSError("no journalctl")),
                       read_state=_boom)
    assert not result.evaluable


# --------------------------------------------------------------------------- #
# Defensive: unhandled / none method → unevaluable, no crash.
# --------------------------------------------------------------------------- #
def test_none_method_is_unevaluable():
    result = run_probe({"method": "none"}, NOW, http_get=_boom,
                       run_cmd=_boom, read_state=_boom)
    assert not result.evaluable


def test_unhandled_method_is_unevaluable():
    result = run_probe({"method": "smoke-signals"}, NOW, http_get=_boom,
                       run_cmd=_boom, read_state=_boom)
    assert not result.evaluable
    assert "smoke-signals" in result.evidence


def test_missing_method_is_unevaluable():
    result = run_probe({}, NOW, http_get=_boom, run_cmd=_boom, read_state=_boom)
    assert not result.evaluable


def test_run_probe_never_raises_on_effect_exception():
    # A handler is selected but the effect raises → caught, unevaluable.
    hc = {"method": "http", "endpoint": "x", "expected": 200}
    result = run_probe(hc, NOW, http_get=make_http(raises=RuntimeError("kaboom")),
                       run_cmd=_boom, read_state=_boom)
    assert isinstance(result, ProbeResult)
    assert not result.evaluable and "RuntimeError" in result.evidence
