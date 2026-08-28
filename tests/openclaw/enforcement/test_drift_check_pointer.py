"""The drift check's freshness pointer must separate liveness from result (#895).

`drift_check.main()` exits 1 when it FINDS drift — a successful run. The canary
treats any non-zero `exit_code` in a pointer as an explicit failure. So writing
the process exit code into the pointer would make every drift-finding run page as
broken. These tests assert the separation holds, judged by the REAL canary probe
rather than a hand-rolled restatement of it.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.canary.probes import run_probe
from scripts.openclaw.enforcement import drift_check


def read_state(path):
    return json.loads(Path(path).read_text())


def probe(pointer_path, max_age_seconds=108000, now=None):
    """Judge a pointer with the real canary freshness probe."""
    return run_probe(
        {
            "method": "state-file",
            "state_path": str(pointer_path),
            "max_age_seconds": max_age_seconds,
        },
        now or datetime.now(timezone.utc),
        http_get=None,
        run_cmd=None,
        read_state=read_state,
    )


def test_drift_found_is_recorded_as_healthy(tmp_path):
    """The whole point: exit 1 means 'ran and found drift', not 'broken'."""
    ptr = tmp_path / "last-tick.json"
    drift_check.write_last_tick(str(ptr), status="success", exit_code=0, has_drift=True)

    payload = read_state(ptr)
    assert payload["has_drift"] is True
    assert payload["exit_code"] == 0
    assert payload["status"] == "success"

    result = probe(ptr)
    assert result.ok, f"drift-found must be healthy, got: {result.evidence}"
    assert not result.stale


def test_clean_run_is_healthy(tmp_path):
    ptr = tmp_path / "last-tick.json"
    drift_check.write_last_tick(str(ptr), status="success", exit_code=0, has_drift=False)
    result = probe(ptr)
    assert result.ok
    assert not result.stale


def test_runner_error_is_unhealthy(tmp_path):
    """Exit 2 is a genuine runner failure and must be visible."""
    ptr = tmp_path / "last-tick.json"
    drift_check.write_last_tick(str(ptr), status="error", exit_code=2, has_drift=None)
    result = probe(ptr)
    assert not result.ok, "a runner error must not read as healthy"


def test_stale_pointer_is_reported_stale(tmp_path):
    """A health check that cannot fail is worse than none (#891)."""
    ptr = tmp_path / "last-tick.json"
    drift_check.write_last_tick(str(ptr), status="success", exit_code=0, has_drift=False)

    payload = read_state(ptr)
    old = datetime.now(timezone.utc) - timedelta(hours=40)
    payload["completed_at_utc"] = old.strftime("%Y-%m-%dT%H:%M:%SZ")
    ptr.write_text(json.dumps(payload))

    result = probe(ptr)
    assert result.stale, "a 40h-old pointer must be stale against a 30h bound"


def test_has_drift_does_not_trip_the_explicit_error_scan(tmp_path):
    """`has_drift` must not collide with error/errors/cycle_error/exit_status."""
    ptr = tmp_path / "last-tick.json"
    drift_check.write_last_tick(str(ptr), status="success", exit_code=0, has_drift=True)
    payload = read_state(ptr)
    for forbidden in ("error", "errors", "cycle_error", "exit_status"):
        assert forbidden not in payload, f"{forbidden} would be read as an explicit failure"


def test_pointer_is_written_atomically_and_leaves_no_temp(tmp_path):
    ptr = tmp_path / "nested" / "last-tick.json"
    drift_check.write_last_tick(str(ptr), status="success", exit_code=0, has_drift=False)
    assert ptr.exists(), "parent directory should be created"
    assert not list(ptr.parent.glob("*.tmp")), "temp files left behind"


def test_pointer_write_failure_is_never_fatal(tmp_path, monkeypatch):
    """Losing the freshness signal must not crash drift enforcement."""
    ptr = tmp_path / "last-tick.json"

    def boom(*a, **kw):
        raise OSError("simulated failure")

    monkeypatch.setattr(drift_check.os, "makedirs", boom)
    # Must not raise.
    drift_check.write_last_tick(str(ptr), status="success", exit_code=0, has_drift=False)
    assert not ptr.exists()


def test_pointer_path_is_not_under_tmp():
    """#894 pins the set of components probing /tmp; this must not join it."""
    assert not drift_check.LAST_TICK_PATH.startswith("/tmp/")
    assert drift_check.LAST_TICK_PATH.startswith("/data/services/")


# --------------------------------------------------------------------------- #
# main() end-to-end (post-review). The tests above verify the pointer SHAPE and
# the canary's interpretation of it, but would not catch a regression where
# main() writes the process exit code into the pointer on the drift path — which
# is the exact defect this work package exists to prevent.
# --------------------------------------------------------------------------- #

def test_main_records_drift_run_as_healthy(tmp_path, monkeypatch):
    """report + drift -> process exit 1, but pointer says success / 0 / has_drift.

    This is the regression guard for the central defect: copying the process exit
    code into the pointer would make a healthy drift-finding run page as broken.
    """
    ptr = tmp_path / "last-tick.json"

    class _Result:
        agent_id = "a"
        filename = "AGENTS.md"
        state = drift_check.DriftState.REPO_CHANGED
        is_factory_default = False
        current_repo_hash = "x"
        current_office2_hash = "y"

    monkeypatch.setattr(drift_check, "load_json", lambda path: {})
    monkeypatch.setattr(drift_check, "get_repo_root", lambda: str(tmp_path))
    monkeypatch.setattr(drift_check, "compute_all_hashes", lambda *a, **k: {})
    monkeypatch.setattr(drift_check, "detect_all_drift", lambda *a, **k: [_Result()])
    monkeypatch.setattr(drift_check, "format_results", lambda r: "")
    monkeypatch.setattr(sys, "argv", [
        "drift_check.py", "report", "--last-tick-path", str(ptr),
    ])

    with pytest.raises(SystemExit) as exc:
        drift_check.main()

    assert exc.value.code == 1, "report mode must still exit 1 when drift is found"

    assert ptr.exists(), "main() must always leave a pointer"
    payload = read_state(ptr)
    assert payload["exit_code"] == 0, (
        f"pointer recorded process exit {payload['exit_code']}; the process exit "
        "code must never be copied into the pointer"
    )
    assert payload["status"] == "success"
    assert payload["has_drift"] is True
    assert probe(ptr).ok, "a drift-finding run is healthy, not broken"


def test_main_writes_error_pointer_when_config_is_missing(tmp_path, monkeypatch):
    """An early failure must still leave an explicit error, not silence.

    Before this hardening, load_json's sys.exit(1) aborted before any pointer was
    written, so the canary would only notice hours later via staleness.
    """
    ptr = tmp_path / "last-tick.json"
    monkeypatch.setattr(drift_check, "LAST_TICK_PATH", str(ptr))
    monkeypatch.setattr(sys, "argv", [
        "drift_check.py", "check", "--config", str(tmp_path / "nope.json"),
    ])

    with pytest.raises(SystemExit):
        drift_check.main()

    assert ptr.exists(), "an early abort must still record an error pointer"
    payload = read_state(ptr)
    assert payload["status"] == "error"
    assert payload["exit_code"] == 2
    assert not probe(ptr).ok, "a runner failure must not read as healthy"
