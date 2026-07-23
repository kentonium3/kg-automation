"""Unit tests for scripts/deploy/felix-deployer/expected_drift.py (#862).

The helper answers "which baselines have fresh, expected in-flight drift?" for the
security-monitor audit's push filter. It must be fail-safe (empty set on any error /
absent / stale token) and honor the dedicated short suppression window — NOT
felix-deployer's 24 h stale threshold.
"""
from __future__ import annotations

import datetime as _dt
import importlib.util
import json
import pathlib
import subprocess
import sys

import pytest

# ---------------------------------------------------------------------------
# Module loader — same importlib pattern as test_rebaseline.py
# ---------------------------------------------------------------------------

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
FELIX_DEPLOYER_DIR = REPO_ROOT / "scripts" / "deploy" / "felix-deployer"
HELPER_PATH = FELIX_DEPLOYER_DIR / "expected_drift.py"


def _load_expected_drift():
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    if str(FELIX_DEPLOYER_DIR) not in sys.path:
        sys.path.insert(0, str(FELIX_DEPLOYER_DIR))
    spec = importlib.util.spec_from_file_location(
        "felix_deployer_expected_drift_under_test", HELPER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["felix_deployer_expected_drift_under_test"] = module
    spec.loader.exec_module(module)
    return module


ed = _load_expected_drift()

_NOW = _dt.datetime(2026, 7, 23, 12, 0, 0, tzinfo=_dt.timezone.utc)


def _iso(dt: _dt.datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_token(tmp_path: pathlib.Path, monkeypatch, payload) -> pathlib.Path:
    token = tmp_path / "rebaseline-pending.json"
    if payload is not None:
        token.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("EXPECTED_DRIFT_TOKEN_PATH", str(token))
    return token


def _fresh_payload(**over):
    payload = {
        "schema_version": 1,
        "pending_since_utc": _iso(_NOW - _dt.timedelta(seconds=60)),
        "expected_baselines": ["systemd-user-unit-contents.txt", "openclaw-cron.txt"],
    }
    payload.update(over)
    return payload


def test_fresh_member_baselines_returned(tmp_path, monkeypatch):
    _write_token(tmp_path, monkeypatch, _fresh_payload())
    assert ed.fresh_expected_baselines(now=_NOW) == {
        "systemd-user-unit-contents.txt",
        "openclaw-cron.txt",
    }


def test_stale_token_returns_empty(tmp_path, monkeypatch):
    # 20 min old > 900 s window -> stale -> empty (still detected/paged by audit).
    payload = _fresh_payload(pending_since_utc=_iso(_NOW - _dt.timedelta(minutes=20)))
    _write_token(tmp_path, monkeypatch, payload)
    assert ed.fresh_expected_baselines(now=_NOW) == set()


def test_future_dated_token_returns_empty(tmp_path, monkeypatch):
    payload = _fresh_payload(pending_since_utc=_iso(_NOW + _dt.timedelta(minutes=1)))
    _write_token(tmp_path, monkeypatch, payload)
    assert ed.fresh_expected_baselines(now=_NOW) == set()


def test_absent_token_returns_empty(tmp_path, monkeypatch):
    _write_token(tmp_path, monkeypatch, None)  # no file written
    assert ed.fresh_expected_baselines(now=_NOW) == set()


def test_malformed_token_returns_empty(tmp_path, monkeypatch):
    token = tmp_path / "rebaseline-pending.json"
    token.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setenv("EXPECTED_DRIFT_TOKEN_PATH", str(token))
    assert ed.fresh_expected_baselines(now=_NOW) == set()


def test_unparseable_timestamp_returns_empty(tmp_path, monkeypatch):
    payload = _fresh_payload(pending_since_utc="not-a-date")
    _write_token(tmp_path, monkeypatch, payload)
    assert ed.fresh_expected_baselines(now=_NOW) == set()


def test_empty_expected_list_returns_empty(tmp_path, monkeypatch):
    payload = _fresh_payload(expected_baselines=[])
    _write_token(tmp_path, monkeypatch, payload)
    assert ed.fresh_expected_baselines(now=_NOW) == set()


def test_missing_pending_since_returns_empty(tmp_path, monkeypatch):
    payload = _fresh_payload()
    del payload["pending_since_utc"]
    _write_token(tmp_path, monkeypatch, payload)
    assert ed.fresh_expected_baselines(now=_NOW) == set()


def test_at_window_boundary_is_fresh(tmp_path, monkeypatch):
    # Exactly at the window edge (age == 900) is still honored (<=).
    payload = _fresh_payload(
        pending_since_utc=_iso(_NOW - _dt.timedelta(seconds=ed.AUDIT_SUPPRESS_WINDOW_SECONDS))
    )
    _write_token(tmp_path, monkeypatch, payload)
    assert ed.fresh_expected_baselines(now=_NOW) == {
        "systemd-user-unit-contents.txt",
        "openclaw-cron.txt",
    }


# ---------------------------------------------------------------------------
# Record-aware push filter (Codex F: multi-line diff bodies must be dropped whole)
# ---------------------------------------------------------------------------

# A realistic expected-drift record: header + multi-line diff body.
_EXPECTED_RECORD = [
    "[ALERT] systemd-user-unit-contents.txt changed since baseline: 5c5",
    "< ExecStart=/old/path",
    "---",
    "> ExecStart=/new/path",
]
_UNEXPECTED_RECORD = [
    "[ALERT] openclaw-cron.txt changed since baseline: 1c1",
    "< jobs-before",
    "> jobs-after",
]
_IOC_RECORD = ["[ALERT] IOC: /tmp/pglog exists (litellm indicator)"]


def test_filter_drops_expected_record_including_diff_body():
    lines = _EXPECTED_RECORD + _UNEXPECTED_RECORD + _IOC_RECORD
    kept = ed.filter_alert_lines(lines, {"systemd-user-unit-contents.txt"})
    # The expected record's header AND its 3 diff-body lines are gone.
    assert kept == _UNEXPECTED_RECORD + _IOC_RECORD
    # No orphaned diff-body line leaked through.
    assert "< ExecStart=/old/path" not in kept
    assert "> ExecStart=/new/path" not in kept


def test_filter_keeps_ioc_and_unexpected_records():
    lines = _EXPECTED_RECORD + _IOC_RECORD + _UNEXPECTED_RECORD
    kept = ed.filter_alert_lines(lines, {"systemd-user-unit-contents.txt"})
    assert kept == _IOC_RECORD + _UNEXPECTED_RECORD


def test_filter_all_expected_returns_empty():
    kept = ed.filter_alert_lines(_EXPECTED_RECORD, {"systemd-user-unit-contents.txt"})
    assert kept == []


def test_filter_empty_expected_keeps_everything():
    lines = _EXPECTED_RECORD + _UNEXPECTED_RECORD + _IOC_RECORD
    assert ed.filter_alert_lines(lines, set()) == lines


def test_filter_exact_match_not_prefix_sibling():
    # A token naming the shorter sibling must NOT suppress the longer baseline.
    lines = _EXPECTED_RECORD  # systemd-user-unit-contents.txt
    kept = ed.filter_alert_lines(lines, {"systemd-user-units.txt"})
    assert kept == _EXPECTED_RECORD  # nothing suppressed


def test_filter_alerts_cli_roundtrip(tmp_path):
    """--filter-alerts reads stdin, drops the expected record, exits 0.

    The subprocess computes freshness against REAL wall-clock now (it can't see the
    test's injected _NOW), so the token's pending_since_utc must be real-now-relative.
    """
    real_now = _dt.datetime.now(tz=_dt.timezone.utc)
    token = tmp_path / "rebaseline-pending.json"
    token.write_text(
        json.dumps(
            {
                "pending_since_utc": _iso(real_now - _dt.timedelta(seconds=30)),
                "expected_baselines": ["systemd-user-unit-contents.txt"],
            }
        ),
        encoding="utf-8",
    )
    stdin = "\n".join(_EXPECTED_RECORD + _IOC_RECORD) + "\n"
    env = {**__import__("os").environ, "EXPECTED_DRIFT_TOKEN_PATH": str(token)}
    proc = subprocess.run(
        [sys.executable, str(HELPER_PATH), "--filter-alerts"],
        input=stdin, capture_output=True, text=True, env=env, check=False,
    )
    assert proc.returncode == 0
    # systemd-user-unit-contents.txt is expected+fresh → its record dropped; IOC kept.
    assert "systemd-user-unit-contents.txt" not in proc.stdout
    assert "IOC: /tmp/pglog" in proc.stdout


@pytest.mark.parametrize("payload", [None, _fresh_payload(), {"bad": 1}])
def test_cli_list_always_exits_zero(tmp_path, payload):
    """--list must never fail the caller (exit 0) regardless of token state."""
    token = tmp_path / "rebaseline-pending.json"
    if payload is not None:
        token.write_text(json.dumps(payload), encoding="utf-8")
    env = {"EXPECTED_DRIFT_TOKEN_PATH": str(token), "PATH": "/usr/bin:/bin"}
    # Preserve the interpreter's environment essentials for import resolution.
    import os as _os

    full_env = {**_os.environ, **env}
    proc = subprocess.run(
        [sys.executable, str(HELPER_PATH), "--list"],
        capture_output=True,
        text=True,
        env=full_env,
        check=False,
    )
    assert proc.returncode == 0
