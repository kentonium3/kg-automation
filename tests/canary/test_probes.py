"""Unit tests for scripts.canary.probes.

Every effect is injected — no network, no subprocess, no real filesystem. The
``health_check`` shapes and freshness-pointer payloads below are copied from
real ``service-inventory.json`` entries and their real pointer files (restic
``last-backup.json``, the canary runner's ``last-tick.json``, trust-scan's
``seen-findings.json`` map, agent-prompt-sync's JSONL log surfaced as a list).

``now`` is always injected, never ``datetime.now()``.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

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


@pytest.mark.parametrize("ts_key", ["started_at_utc", "ran_at_utc", "timestamp_utc"])
def test_freshness_real_office2_timestamp_keys_resolve(ts_key):
    # Real office2 freshness pointers anchor on these fields (audited 2026-07-11):
    # felix-core-digest / felix-heartbeat-gate -> started_at_utc; felix-health-check
    # -> ran_at_utc; felix-doc-auditor -> timestamp_utc. Each MUST resolve so those
    # (core) components are actually freshness-watched, not persistent-unknown.
    assert ts_key in TIMESTAMP_KEYS
    pointer = {ts_key: "2026-07-11T11:50:00Z"}  # 10 min old
    hc = {"method": "tick-signal-file", "state_path": "/x/p.json",
          "max_age_seconds": 2100}
    result = run_probe(hc, NOW, http_get=_boom, run_cmd=_boom,
                       read_state=make_state(pointer))
    assert result.evaluable and result.ok and not result.stale
    assert ts_key in result.evidence


def test_freshness_started_at_utc_is_fallback_after_completion_keys():
    # A pointer with BOTH a completion anchor and started_at_utc must prefer the
    # completion field (started_at_utc is only the fallback).
    assert TIMESTAMP_KEYS.index("completed_at_utc") < TIMESTAMP_KEYS.index(
        "started_at_utc"
    )
    pointer = {"started_at_utc": "2020-01-01T00:00:00Z",
               "completed_at_utc": "2026-07-11T11:59:00Z"}  # 1 min old
    hc = {"method": "tick-signal-file", "state_path": "/x/p.json",
          "max_age_seconds": 2100}
    result = run_probe(hc, NOW, http_get=_boom, run_cmd=_boom,
                       read_state=make_state(pointer))
    assert not result.stale and "completed_at_utc" in result.evidence


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


# --- F2: generalized explicit-error field conventions ------------------------ #
# The real freshness pointers signal failure via exit_status / status / exit_code
# (not just restic_exit_code). A FRESH pointer carrying such a signal must read
# `failed`, and the healthy counterparts must stay `healthy` when fresh.
def test_freshness_exit_status_failed_is_failed():
    # felix-core-digest / felix-habit-sweeper tick-signals: exit_status enum
    # {"success","partial","failure"}. A fresh but failed tick must NOT read
    # healthy (the F2 regression: pointer was fresh with errors=[] → false ok).
    pointer = {"exit_status": "failed", "completed_at_utc": "2026-07-11T11:59:00Z",
               "errors": []}
    hc = {"method": "tick-signal-file", "endpoint": "/x/last-tick.json",
          "max_age_seconds": 2100}
    result = run_probe(hc, NOW, http_get=_boom, run_cmd=_boom,
                       read_state=make_state(pointer))
    assert result.evaluable and not result.ok
    assert "exit_status" in result.evidence


def test_freshness_exit_status_partial_is_failed():
    # `partial` is a non-success exit_status → operator attention → failed.
    pointer = {"exit_status": "partial", "completed_at_utc": "2026-07-11T11:59:00Z"}
    hc = {"method": "tick-signal-file", "endpoint": "/x/last-tick.json",
          "max_age_seconds": 2100}
    result = run_probe(hc, NOW, http_get=_boom, run_cmd=_boom,
                       read_state=make_state(pointer))
    assert result.evaluable and not result.ok
    assert "partial" in result.evidence


def test_freshness_exit_status_success_stays_healthy():
    pointer = {"exit_status": "success", "completed_at_utc": "2026-07-11T11:59:00Z"}
    hc = {"method": "tick-signal-file", "endpoint": "/x/last-tick.json",
          "max_age_seconds": 2100}
    result = run_probe(hc, NOW, http_get=_boom, run_cmd=_boom,
                       read_state=make_state(pointer))
    assert result.ok and result.evaluable and not result.stale


def test_freshness_status_error_is_failed():
    # canary's own / agent-prompt-sync tick-signal: status {"success","error"}.
    pointer = {"status": "error", "completed_at_utc": "2026-07-11T11:59:00Z"}
    hc = {"method": "tick-signal-file", "endpoint": "/x/last-tick.json",
          "max_age_seconds": 2100}
    result = run_probe(hc, NOW, http_get=_boom, run_cmd=_boom,
                       read_state=make_state(pointer))
    assert result.evaluable and not result.ok
    assert "status" in result.evidence


def test_freshness_status_success_stays_healthy():
    pointer = {"status": "success", "completed_at_utc": "2026-07-11T11:59:00Z"}
    hc = {"method": "tick-signal-file", "endpoint": "/x/last-tick.json",
          "max_age_seconds": 2100}
    result = run_probe(hc, NOW, http_get=_boom, run_cmd=_boom,
                       read_state=make_state(pointer))
    assert result.ok and result.evaluable and not result.stale


def test_freshness_open_status_vocabulary_not_false_failed():
    # felix-health-check uses status={ALL_HEALTHY, FAILURES_DETECTED, ...} where
    # a non-"success" status is NOT a runner failure. The OPEN `status`
    # vocabulary must be matched on explicit failure VALUES only — neither of
    # these may flip to failed just because they are not "success".
    for value in ("ALL_HEALTHY", "FAILURES_DETECTED"):
        pointer = {"status": value, "completed_at_utc": "2026-07-11T11:59:00Z"}
        hc = {"method": "signal-file", "endpoint": "/x/last-run.json",
              "max_age_seconds": 100800}
        result = run_probe(hc, NOW, http_get=_boom, run_cmd=_boom,
                           read_state=make_state(pointer))
        assert result.ok and result.evaluable, f"{value} wrongly failed"


def test_freshness_exit_code_nonzero_is_failed():
    # agent-prompt-sync / felix-doc-auditor / felix-deployer: exit_code=0 good.
    pointer = {"exit_code": 1, "completed_at_utc": "2026-07-11T11:59:00Z"}
    hc = {"method": "tick-signal-file", "endpoint": "/x/last-tick.json",
          "max_age_seconds": 2100}
    result = run_probe(hc, NOW, http_get=_boom, run_cmd=_boom,
                       read_state=make_state(pointer))
    assert result.evaluable and not result.ok
    assert "exit_code=1" in result.evidence


def test_freshness_exit_code_zero_stays_healthy():
    pointer = {"exit_code": 0, "status": "success",
               "completed_at_utc": "2026-07-11T11:59:00Z"}
    hc = {"method": "tick-signal-file", "endpoint": "/x/last-tick.json",
          "max_age_seconds": 2100}
    result = run_probe(hc, NOW, http_get=_boom, run_cmd=_boom,
                       read_state=make_state(pointer))
    assert result.ok and result.evaluable and not result.stale


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
    # Post-F1: the endpoint's own grep does the marker filtering, so "marker
    # absent" means the command ran clean but returned NO matching lines (empty
    # stdout). The prose `expected` is never used as a literal substring.
    hc = {"method": "log-tail", "endpoint": "tail x | grep OK", "expected": "OK"}
    result = run_probe(hc, NOW, http_get=_boom,
                       run_cmd=make_cmd((0, "", "")),
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


# --- F1: healthy is driven by the COMMAND result, never by an expected-prose
# substring. These use real-shaped credential-liveness-probe inventory data:
# the endpoint's own grep filters the markers, and `expected` is human prose.
def test_log_scan_prose_expected_with_marker_output_is_healthy():
    # credential-liveness-probe (real entry): endpoint greps the markers; the
    # command returns a real marker line; `expected` is PROSE that is NOT a
    # substring of stdout. Pre-F1 this false-failed on the prose-substring test.
    hc = {
        "method": "log-tail",
        "endpoint": ("journalctl --user -u credential-liveness-probe.service "
                     "--since '7 hours ago' | grep -E "
                     "'credential_alive|credential_dead|credential_probe_error'"),
        "expected": ("At least one credential_alive or credential_dead event in "
                     "the last 7-hour window; absence means the timer did not fire"),
        "timeout_seconds": 5,
    }
    result = run_probe(
        hc, NOW, http_get=_boom,
        run_cmd=make_cmd((0, "Jul 11 11:59:00 host probe[1]: credential_alive "
                             "account=personal", "")),
        read_state=_boom,
    )
    assert result.ok and result.evaluable and not result.stale


def test_log_scan_clean_run_no_matching_lines_is_failed():
    # The grep matched nothing (timer did not fire) → exit 0, empty stdout →
    # marker absent → failed (not a false healthy, not unknown).
    hc = {
        "method": "log-tail",
        "endpoint": ("journalctl --user -u credential-liveness-probe.service "
                     "--since '7 hours ago' | grep -E 'credential_alive'"),
        "expected": "At least one credential_alive event in the window",
    }
    result = run_probe(hc, NOW, http_get=_boom,
                       run_cmd=make_cmd((0, "", "")), read_state=_boom)
    assert result.evaluable and not result.ok and not result.stale
    assert "no matching lines" in result.evidence


def test_log_scan_command_error_is_unknown():
    # A command spawn/execution error (raised) → unknown, per the wrapper.
    hc = {"method": "journal", "endpoint": "journalctl --user -u x | grep OK",
          "expected": "prose about OK events"}
    result = run_probe(hc, NOW, http_get=_boom,
                       run_cmd=make_cmd(raises=OSError("journalctl vanished")),
                       read_state=_boom)
    assert not result.evaluable
    assert "OSError" in result.evidence


def test_log_scan_staleness_boundary_with_prose_expected():
    # Timestamped marker line older than max_age → stale, even though the prose
    # `expected` never appears in stdout (F1: prose is not a matcher).
    hc = {"method": "journal", "endpoint": "journalctl -u x | grep cycle_end",
          "expected": "cycle_end event present from the most recent tick",
          "max_age_seconds": 3600}
    result = run_probe(
        hc, NOW, http_get=_boom,
        run_cmd=make_cmd((0, "2026-07-10T00:00:00Z cycle_end ok", "")),  # >1h old
        read_state=_boom,
    )
    assert result.ok and result.stale and result.evaluable


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


# --------------------------------------------------------------------------- #
# openclaw-cron-state (#722) — schedule-aware cron health via
# `openclaw cron list --json`. Every case drives the probe through the public
# run_probe() with a fake run_cmd returning a canned cron-list JSON payload.
# Timestamps are built relative to NOW so the schedule-aware freshness (now vs
# nextRunAtMs + grace) is exercised deterministically.
# --------------------------------------------------------------------------- #
import json as _json

NOW_MS = NOW.timestamp() * 1000.0
_GRACE_MS = 900_000.0  # default grace_seconds=900


def _cron_job(name, *, enabled=True, status="ok", last_run_ms=None,
              next_run_ms=None, last_error=None):
    """One entry shaped like a real `openclaw cron list --json` job."""
    state = {}
    if status is not None:
        state["lastRunStatus"] = status
    if last_run_ms is not None:
        state["lastRunAtMs"] = last_run_ms
    if next_run_ms is not None:
        state["nextRunAtMs"] = next_run_ms
    if last_error is not None:
        state["lastError"] = last_error
    return {"name": name, "enabled": enabled, "state": state}


def _cron_list(*jobs):
    """A run_cmd result tuple (exit 0) carrying the jobs as `{"jobs": [...]}`."""
    return (0, _json.dumps({"jobs": list(jobs)}), "")


def _cron_hc(crons, **overrides):
    hc = {
        "method": "openclaw-cron-state",
        "endpoint": "/home/claude/.local/bin/openclaw cron list --json",
        "crons": crons,
        "timeout_seconds": 30,
        "grace_seconds": 900,
    }
    hc.update(overrides)
    return hc


def test_openclaw_cron_all_healthy():
    # Two crons of different cadence, both ok + next fire in the future → healthy.
    payload = _cron_list(
        _cron_job("habits-morning-checkin", next_run_ms=NOW_MS + 3_600_000),
        _cron_job("habits-weekly-report", next_run_ms=NOW_MS + 5 * 86_400_000),
    )
    result = run_probe(
        _cron_hc(["habits-morning-checkin", "habits-weekly-report"]),
        NOW, http_get=_boom, run_cmd=make_cmd(payload), read_state=_boom,
    )
    assert result.ok and not result.stale and result.evaluable
    assert "on schedule" in result.evidence


def test_openclaw_cron_errored_run_is_failed():
    payload = _cron_list(
        _cron_job("escalation-daily", status="error", next_run_ms=NOW_MS + 3_600_000,
                  last_error="fetch projects/-4 -> python3 inline script failed"),
    )
    result = run_probe(
        _cron_hc(["escalation-daily"]),
        NOW, http_get=_boom, run_cmd=make_cmd(payload), read_state=_boom,
    )
    assert not result.ok and not result.stale and result.evaluable
    assert "escalation-daily" in result.evidence
    assert "lastRunStatus=error" in result.evidence
    assert "python3 inline script failed" in result.evidence


def test_openclaw_cron_errored_run_sets_run_identity_signal():
    # #871: an all-run-error failure carries a run-identity signal (fingerprinted
    # by nextRunAtMs) so dedup re-alerts on a NEW run, not the same frozen one.
    payload = _cron_list(
        _cron_job("inbox-5pm", status="error", next_run_ms=NOW_MS + 3_600_000,
                  last_error="boom"),
    )
    result = run_probe(
        _cron_hc(["inbox-5pm"]),
        NOW, http_get=_boom, run_cmd=make_cmd(payload), read_state=_boom,
    )
    assert not result.ok and result.evaluable
    assert result.signal is not None and "inbox-5pm@" in result.signal

    # The cron ran again (next-run anchor advanced) → a DIFFERENT signal, so a
    # genuine new failure is not mistaken for the frozen one.
    payload2 = _cron_list(
        _cron_job("inbox-5pm", status="error", next_run_ms=NOW_MS + 90_000_000,
                  last_error="boom again"),
    )
    result2 = run_probe(
        _cron_hc(["inbox-5pm"]),
        NOW, http_get=_boom, run_cmd=make_cmd(payload2), read_state=_boom,
    )
    assert result2.signal is not None and result2.signal != result.signal


def test_openclaw_cron_config_drift_failure_has_no_signal():
    # A live config-drift failure (a mapped cron missing from the list) present →
    # NO run-identity signal, so the condition re-nags on the normal window.
    payload = _cron_list(
        _cron_job("inbox-5pm", status="error", next_run_ms=NOW_MS + 3_600_000,
                  last_error="boom"),
    )  # inbox-noon is absent → live drift alongside the run-error
    result = run_probe(
        _cron_hc(["inbox-5pm", "inbox-noon"]),
        NOW, http_get=_boom, run_cmd=make_cmd(payload), read_state=_boom,
    )
    assert not result.ok and result.evaluable
    assert result.signal is None


def test_openclaw_cron_healthy_has_no_signal():
    payload = _cron_list(
        _cron_job("inbox-7am", status="ok", next_run_ms=NOW_MS + 3_600_000),
    )
    result = run_probe(
        _cron_hc(["inbox-7am"]),
        NOW, http_get=_boom, run_cmd=make_cmd(payload), read_state=_boom,
    )
    assert result.ok and result.signal is None


def test_openclaw_cron_overdue_is_stale():
    # Scheduler stopped firing it: nextRunAtMs is in the past by > grace.
    payload = _cron_list(
        _cron_job("inbox-7am", status="ok", next_run_ms=NOW_MS - _GRACE_MS - 60_000),
    )
    result = run_probe(
        _cron_hc(["inbox-7am"]),
        NOW, http_get=_boom, run_cmd=make_cmd(payload), read_state=_boom,
    )
    assert result.ok and result.stale and result.evaluable
    assert "inbox-7am" in result.evidence and "overdue" in result.evidence


def test_openclaw_cron_within_grace_is_not_stale():
    # Just past nextRunAtMs but inside the grace window (mid-run) → healthy.
    payload = _cron_list(
        _cron_job("inbox-7am", status="ok", next_run_ms=NOW_MS - (_GRACE_MS / 2)),
    )
    result = run_probe(
        _cron_hc(["inbox-7am"]),
        NOW, http_get=_boom, run_cmd=make_cmd(payload), read_state=_boom,
    )
    assert result.ok and not result.stale


def test_openclaw_cron_missing_from_list_is_failed():
    payload = _cron_list(_cron_job("inbox-7am", next_run_ms=NOW_MS + 3_600_000))
    result = run_probe(
        _cron_hc(["inbox-7am", "inbox-noon"]),
        NOW, http_get=_boom, run_cmd=make_cmd(payload), read_state=_boom,
    )
    assert not result.ok and result.evaluable
    assert "inbox-noon" in result.evidence and "not present" in result.evidence


def test_openclaw_cron_disabled_is_failed():
    payload = _cron_list(
        _cron_job("inbox-7am", enabled=False, next_run_ms=NOW_MS + 3_600_000),
    )
    result = run_probe(
        _cron_hc(["inbox-7am"]),
        NOW, http_get=_boom, run_cmd=make_cmd(payload), read_state=_boom,
    )
    assert not result.ok and result.evaluable
    assert "not enabled" in result.evidence


def test_openclaw_cron_string_enabled_does_not_false_heal():
    # A drifted non-boolean `enabled` must fail loud, never silently heal.
    payload = _cron_list(
        _cron_job("inbox-7am", status="ok", next_run_ms=NOW_MS + 3_600_000),
    )
    # Overwrite enabled to a drifted non-boolean string ("disabled" is truthy).
    doc = _json.loads(payload[1])
    doc["jobs"][0]["enabled"] = "disabled"
    result = run_probe(
        _cron_hc(["inbox-7am"]),
        NOW, http_get=_boom, run_cmd=make_cmd((0, _json.dumps(doc), "")),
        read_state=_boom,
    )
    assert not result.ok and result.evaluable
    assert "not enabled" in result.evidence


def test_openclaw_cron_missing_next_run_is_unevaluable():
    # Enabled + ok but no freshness anchor → indeterminate, NOT false-healthy.
    payload = _cron_list(_cron_job("inbox-7am", status="ok", next_run_ms=None))
    result = run_probe(
        _cron_hc(["inbox-7am"]),
        NOW, http_get=_boom, run_cmd=make_cmd(payload), read_state=_boom,
    )
    assert not result.evaluable
    assert "inbox-7am" in result.evidence and "nextRunAtMs" in result.evidence


def test_openclaw_cron_non_numeric_next_run_is_unevaluable():
    payload = _cron_list(
        _cron_job("inbox-7am", status="ok", next_run_ms=None),
    )
    doc = _json.loads(payload[1])
    doc["jobs"][0]["state"]["nextRunAtMs"] = "soon"
    result = run_probe(
        _cron_hc(["inbox-7am"]),
        NOW, http_get=_boom, run_cmd=make_cmd((0, _json.dumps(doc), "")),
        read_state=_boom,
    )
    assert not result.evaluable and "nextRunAtMs" in result.evidence


def test_openclaw_cron_failure_outranks_indeterminate():
    # A concrete failure surfaces even when another cron is indeterminate.
    payload = _cron_list(
        _cron_job("a", status="error", next_run_ms=NOW_MS + 3_600_000, last_error="boom"),
        _cron_job("b", status="ok", next_run_ms=None),
    )
    result = run_probe(
        _cron_hc(["a", "b"]),
        NOW, http_get=_boom, run_cmd=make_cmd(payload), read_state=_boom,
    )
    assert not result.ok and result.evaluable  # failed, not unknown
    assert "lastRunStatus=error" in result.evidence


def test_openclaw_cron_never_run_but_not_due_is_healthy():
    # No lastRunStatus yet, next fire in the future → nothing is wrong.
    payload = _cron_list(_cron_job("inbox-7am", status=None, next_run_ms=NOW_MS + 3_600_000))
    result = run_probe(
        _cron_hc(["inbox-7am"]),
        NOW, http_get=_boom, run_cmd=make_cmd(payload), read_state=_boom,
    )
    assert result.ok and not result.stale and result.evaluable


def test_openclaw_cron_gateway_down_is_unevaluable():
    # Non-zero exit (gateway unreachable) → fail-open unknown, never false-failed.
    result = run_probe(
        _cron_hc(["inbox-7am"]),
        NOW, http_get=_boom,
        run_cmd=make_cmd((1, "", "connect ECONNREFUSED 127.0.0.1")),
        read_state=_boom,
    )
    assert not result.evaluable
    assert "exit 1" in result.evidence


def test_openclaw_cron_non_json_is_unevaluable():
    result = run_probe(
        _cron_hc(["inbox-7am"]),
        NOW, http_get=_boom, run_cmd=make_cmd((0, "not json at all", "")),
        read_state=_boom,
    )
    assert not result.evaluable


def test_openclaw_cron_no_jobs_key_is_unevaluable():
    result = run_probe(
        _cron_hc(["inbox-7am"]),
        NOW, http_get=_boom, run_cmd=make_cmd((0, _json.dumps({"foo": 1}), "")),
        read_state=_boom,
    )
    assert not result.evaluable and "jobs" in result.evidence


def test_openclaw_cron_no_crons_configured_is_unevaluable():
    hc = {"method": "openclaw-cron-state",
          "endpoint": "/home/claude/.local/bin/openclaw cron list --json"}
    result = run_probe(hc, NOW, http_get=_boom, run_cmd=_boom, read_state=_boom)
    assert not result.evaluable and "no crons" in result.evidence


def test_openclaw_cron_failed_precedence_over_stale():
    # One errored + one overdue → failed wins (worst outcome).
    payload = _cron_list(
        _cron_job("a", status="error", next_run_ms=NOW_MS + 3_600_000, last_error="boom"),
        _cron_job("b", status="ok", next_run_ms=NOW_MS - _GRACE_MS - 60_000),
    )
    result = run_probe(
        _cron_hc(["a", "b"]),
        NOW, http_get=_boom, run_cmd=make_cmd(payload), read_state=_boom,
    )
    assert not result.ok and not result.stale


def test_dispatch_covers_every_handled_method():
    # Guard against registry/probes drift: every method the registry says is
    # handled must have a probe dispatcher, and vice versa.
    from scripts.canary.probes import _DISPATCH
    from scripts.canary.registry import HANDLED_METHODS
    assert set(_DISPATCH) == set(HANDLED_METHODS)


# --------------------------------------------------------------------------- #
# #891 — health verdicts must be affirmative, not default-positive.
#
# Health check shapes below are copied verbatim from real service-inventory.json
# entries, per this module's house style.
# --------------------------------------------------------------------------- #

_HC_HEALTH_CHECK_RUNNER = {
    "method": "signal-file",
    "max_age_seconds": 46800,
    "endpoint": "/data/services/openclaw/felix-health-check/last-run.json",
    "success_status_values": ["ALL_HEALTHY", "FAILURES_DETECTED"],
}

_HC_SECURITY_MONITOR = {
    "method": "state-file",
    "state_path": "/data/services/security-monitor/state/last-tick.json",
    "max_age_seconds": 108000,
}

_HC_SYNC_DRIVER = {
    "method": "tick-signal-file",
    "endpoint": "/data/services/openclaw/state/sync/last-tick.json",
    "max_age_seconds": 600,
}


def _fresh(**extra):
    payload = {"completed_at_utc": NOW.isoformat()}
    payload.update(extra)
    return payload


class TestDeclaredSuccessStatusValues:
    """`success_status_values` inverts `status` from a deny-list to an allow-list."""

    def test_declared_healthy_value_passes(self):
        r = run_probe(
            _HC_HEALTH_CHECK_RUNNER, NOW,
            http_get=_boom, run_cmd=_boom,
            read_state=make_state({"ran_at_utc": NOW.isoformat(), "status": "ALL_HEALTHY"}),
        )
        assert r.ok and not r.stale

    def test_failures_detected_stays_healthy(self):
        """Monitored-system failures are data, not a runner fault — the
        monitored services have their own canary entries."""
        r = run_probe(
            _HC_HEALTH_CHECK_RUNNER, NOW,
            http_get=_boom, run_cmd=_boom,
            read_state=make_state({"ran_at_utc": NOW.isoformat(), "status": "FAILURES_DETECTED"}),
        )
        assert r.ok

    @pytest.mark.parametrize("status", ["SCRIPT_MISSING", "UNKNOWN"])
    def test_runner_faults_fail(self, status):
        """Both mean the check did not conclusively execute. Before #891 both
        read healthy, because `status` was matched against a deny-list."""
        r = run_probe(
            _HC_HEALTH_CHECK_RUNNER, NOW,
            http_get=_boom, run_cmd=_boom,
            read_state=make_state({"ran_at_utc": NOW.isoformat(), "status": status}),
        )
        assert not r.ok
        assert status in r.evidence

    def test_a_newly_invented_status_word_fails_closed(self):
        """The property that retires the class: nobody has to remember to add
        the new word to a failure list."""
        r = run_probe(
            _HC_HEALTH_CHECK_RUNNER, NOW,
            http_get=_boom, run_cmd=_boom,
            read_state=make_state({"ran_at_utc": NOW.isoformat(), "status": "PARTIALLY_WEDGED"}),
        )
        assert not r.ok

    def test_without_a_declaration_legacy_denylist_still_applies(self):
        """Backward compatibility for the components not yet migrated."""
        hc = {k: v for k, v in _HC_HEALTH_CHECK_RUNNER.items() if k != "success_status_values"}
        assert run_probe(
            hc, NOW, http_get=_boom, run_cmd=_boom,
            read_state=make_state({"ran_at_utc": NOW.isoformat(), "status": "UNKNOWN"}),
        ).ok
        assert not run_probe(
            hc, NOW, http_get=_boom, run_cmd=_boom,
            read_state=make_state({"ran_at_utc": NOW.isoformat(), "status": "error"}),
        ).ok


class TestSecurityMonitorCompletionPointer:
    def test_clean_run_is_healthy(self):
        r = run_probe(
            _HC_SECURITY_MONITOR, NOW, http_get=_boom, run_cmd=_boom,
            read_state=make_state(_fresh(exit_status="success", alert_count=0, pushed_count=0)),
        )
        assert r.ok and not r.stale

    def test_drift_does_not_flip_health(self):
        """audit.sh pushes its own alert for drift; the canary must not page
        again for the same event — nor for a #862 suppressed rebaseline."""
        r = run_probe(
            _HC_SECURITY_MONITOR, NOW, http_get=_boom, run_cmd=_boom,
            read_state=make_state(_fresh(exit_status="success", alert_count=3, pushed_count=2)),
        )
        assert r.ok

    def test_abnormal_termination_fails(self):
        r = run_probe(
            _HC_SECURITY_MONITOR, NOW, http_get=_boom, run_cmd=_boom,
            read_state=make_state(_fresh(exit_status="failure", alert_count=0, pushed_count=0)),
        )
        assert not r.ok

    def test_stale_pointer_is_stale(self):
        old = (NOW - timedelta(seconds=108001)).isoformat()
        r = run_probe(
            _HC_SECURITY_MONITOR, NOW, http_get=_boom, run_cmd=_boom,
            read_state=make_state({"completed_at_utc": old, "exit_status": "success"}),
        )
        assert r.stale

    def test_missing_pointer_is_unknown_never_healthy(self):
        """The pre-#891 probe reported healthy on nothing at all."""
        r = run_probe(
            _HC_SECURITY_MONITOR, NOW, http_get=_boom, run_cmd=_boom,
            read_state=make_state(None),
        )
        assert not r.evaluable


class TestCycleErrorVocabulary:
    def test_clean_cycle_is_healthy(self):
        r = run_probe(
            _HC_SYNC_DRIVER, NOW, http_get=_boom, run_cmd=_boom,
            read_state=make_state(_fresh(cycle_error=None)),
        )
        assert r.ok

    def test_non_null_cycle_error_fails(self):
        """Pre-#891 this read healthy: the probe piped through jq and inspected
        the LAST line, which was the literal string `null`."""
        r = run_probe(
            _HC_SYNC_DRIVER, NOW, http_get=_boom, run_cmd=_boom,
            read_state=make_state(_fresh(cycle_error="vikunja 500")),
        )
        assert not r.ok
        assert "cycle_error" in r.evidence

    def test_stale_pointer_is_stale(self):
        """Also previously invisible — `_parse_iso('null')` returned None, so
        the staleness branch never ran."""
        old = (NOW - timedelta(seconds=601)).isoformat()
        r = run_probe(
            _HC_SYNC_DRIVER, NOW, http_get=_boom, run_cmd=_boom,
            read_state=make_state({"completed_at_utc": old, "cycle_error": None}),
        )
        assert r.stale
