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
