"""Tests for the felix-deployer DM-notify surface.

Covers the payload shape contract (`contracts/dm-payload-v1.md`),
secret redaction in `error_summary`, temp-file cleanup, and
non-propagation of subprocess failures.

The notify module lives under ``scripts/deploy/felix-deployer/`` —
that directory name contains a hyphen so it is not importable via
``import scripts.deploy.felix_deployer.notify``. We load it through
``importlib`` from its on-disk path; the same trick the systemd
service uses (path-based ``ExecStart``).
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess
import sys
from typing import Any

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
FELIX_DEPLOYER_DIR = REPO_ROOT / "scripts" / "deploy" / "felix-deployer"


def _load_notify():
    """Import notify.py from the hyphenated felix-deployer/ dir."""
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    if str(FELIX_DEPLOYER_DIR) not in sys.path:
        sys.path.insert(0, str(FELIX_DEPLOYER_DIR))
    spec = importlib.util.spec_from_file_location(
        "felix_deployer_notify_under_test",
        FELIX_DEPLOYER_DIR / "notify.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


notify = _load_notify()


# ---------------------------------------------------------------------------
# build_payload — shape contract
# ---------------------------------------------------------------------------


def _minimal_manifest() -> dict[str, Any]:
    return {
        "name": "rotate-secret-example",
        "tier": 3,
        "schema_version": "v1",
        "entrypoint": "scripts/deploy/example.sh",
        "audited_surface": False,
    }


def test_build_payload_has_all_v1_required_fields():
    p = notify.build_payload(
        manifest=_minimal_manifest(),
        phase="entrypoint",
        error_summary="something broke",
        head_sha="abc1234567",
        failed_at="2026-06-12T20:00:00Z",
    )
    assert p["payload_version"] == "v1"
    assert p["manifest_name"] == "rotate-secret-example"
    assert p["tier"] == 3
    assert p["phase"] == "entrypoint"
    assert p["error_summary"] == "something broke"
    assert p["head_sha"] == "abc1234567"
    assert p["failed_at"] == "2026-06-12T20:00:00Z"


def test_build_payload_uses_dm_v1_phase_enum():
    for phase in notify.DM_PHASES:
        p = notify.build_payload(
            manifest=_minimal_manifest(),
            phase=phase,
            error_summary="x",
            head_sha="abc",
        )
        assert p["phase"] == phase


def test_build_payload_truncates_error_summary_to_500():
    # Use short tokens separated by whitespace so redact_secrets's
    # 32+ char token-shape regex does NOT collapse the whole string
    # to "[REDACTED]" before truncation. Each segment is 5 chars + a
    # space — well under the token threshold.
    long_summary = ("hello " * 200).rstrip()  # 1199 chars
    assert len(long_summary) > 500
    p = notify.build_payload(
        manifest=_minimal_manifest(),
        phase="entrypoint",
        error_summary=long_summary,
        head_sha="abc",
    )
    assert len(p["error_summary"]) == notify.ERROR_SUMMARY_MAX
    assert len(p["error_summary"]) == 500


def test_build_payload_redacts_secrets_in_error_summary():
    # 40-character token-shaped string triggers verify._TOKEN_RE.
    secret = "A" * 40
    p = notify.build_payload(
        manifest=_minimal_manifest(),
        phase="entrypoint",
        error_summary=f"failed with token={secret}",
        head_sha="abc",
    )
    assert secret not in p["error_summary"]
    assert "REDACTED" in p["error_summary"]


def test_build_payload_redacts_bearer_token():
    p = notify.build_payload(
        manifest=_minimal_manifest(),
        phase="entrypoint",
        error_summary="auth failed: Bearer abc123secrettoken",
        head_sha="abc",
    )
    assert "abc123secrettoken" not in p["error_summary"]


def test_build_payload_defaults_failed_at_to_now():
    p = notify.build_payload(
        manifest=_minimal_manifest(),
        phase="entrypoint",
        error_summary="x",
        head_sha="abc",
    )
    assert p["failed_at"].endswith("Z")


# ---------------------------------------------------------------------------
# dispatch_failure_dm — subprocess interaction
# ---------------------------------------------------------------------------


class _FakeProc:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_dispatch_invokes_openclaw_with_correct_args(monkeypatch, tmp_path):
    seen: dict[str, Any] = {}

    def _fake_run(argv, capture_output, text, check):
        seen["argv"] = list(argv)
        # Read the payload file the caller created and capture its contents.
        i = argv.index("--payload-file")
        payload_path = argv[i + 1]
        seen["payload_file_existed"] = pathlib.Path(payload_path).exists()
        seen["payload"] = json.loads(pathlib.Path(payload_path).read_text())
        return _FakeProc(returncode=0, stdout='{"ok": true}')

    monkeypatch.setattr(subprocess, "run", _fake_run)
    monkeypatch.setattr(notify.subprocess, "run", _fake_run)

    result = notify.dispatch_failure_dm(
        manifest=_minimal_manifest(),
        phase="entrypoint",
        error_summary="exit code 7",
        head_sha="abc1234",
    )
    assert result.ok is True
    assert seen["argv"][:5] == [
        "openclaw",
        "cron",
        "run",
        "felix-deployer-alert",
        "--payload-file",
    ]
    assert "--wait" in seen["argv"]
    assert "--json" in seen["argv"]
    # Payload was written and parses as v1.
    assert seen["payload_file_existed"] is True
    assert seen["payload"]["payload_version"] == "v1"
    assert seen["payload"]["manifest_name"] == "rotate-secret-example"
    assert seen["payload"]["phase"] == "entrypoint"


def test_dispatch_cleans_up_temp_file_on_success(monkeypatch):
    written_paths: list[str] = []
    original_run = subprocess.run

    def _fake_run(argv, capture_output, text, check):
        i = argv.index("--payload-file")
        path = argv[i + 1]
        written_paths.append(path)
        return _FakeProc(returncode=0)

    monkeypatch.setattr(notify.subprocess, "run", _fake_run)

    notify.dispatch_failure_dm(
        manifest=_minimal_manifest(),
        phase="entrypoint",
        error_summary="x",
        head_sha="abc",
    )
    assert written_paths, "temp file was not created"
    assert not pathlib.Path(written_paths[0]).exists()


def test_dispatch_cleans_up_temp_file_on_failure(monkeypatch):
    written_paths: list[str] = []

    def _fake_run(argv, capture_output, text, check):
        i = argv.index("--payload-file")
        path = argv[i + 1]
        written_paths.append(path)
        return _FakeProc(returncode=2, stderr="boom")

    monkeypatch.setattr(notify.subprocess, "run", _fake_run)

    result = notify.dispatch_failure_dm(
        manifest=_minimal_manifest(),
        phase="entrypoint",
        error_summary="x",
        head_sha="abc",
    )
    assert result.ok is False
    assert result.details["error_code"] == "DISPATCH_FAILED"
    assert written_paths
    assert not pathlib.Path(written_paths[0]).exists()


def test_dispatch_does_not_raise_when_subprocess_returns_nonzero(monkeypatch):
    def _fake_run(argv, capture_output, text, check):
        return _FakeProc(returncode=5, stderr="cron not registered")

    monkeypatch.setattr(notify.subprocess, "run", _fake_run)

    # The function must return a LibResult, NOT raise.
    result = notify.dispatch_failure_dm(
        manifest=_minimal_manifest(),
        phase="entrypoint",
        error_summary="x",
        head_sha="abc",
    )
    assert result.ok is False
    assert result.details["returncode"] == 5


def test_dispatch_handles_openclaw_binary_missing(monkeypatch):
    def _fake_run(argv, capture_output, text, check):
        raise FileNotFoundError("[Errno 2] openclaw")

    monkeypatch.setattr(notify.subprocess, "run", _fake_run)

    result = notify.dispatch_failure_dm(
        manifest=_minimal_manifest(),
        phase="entrypoint",
        error_summary="x",
        head_sha="abc",
    )
    assert result.ok is False
    assert result.details["error_code"] == "OPENCLAW_MISSING"


def test_dispatch_passes_redacted_summary_in_payload(monkeypatch):
    captured: dict[str, Any] = {}

    def _fake_run(argv, capture_output, text, check):
        i = argv.index("--payload-file")
        captured["payload"] = json.loads(pathlib.Path(argv[i + 1]).read_text())
        return _FakeProc(returncode=0)

    monkeypatch.setattr(notify.subprocess, "run", _fake_run)

    secret = "B" * 50  # token-shaped
    notify.dispatch_failure_dm(
        manifest=_minimal_manifest(),
        phase="entrypoint",
        error_summary=f"failed: {secret}",
        head_sha="abc",
    )
    assert secret not in captured["payload"]["error_summary"]
    assert "REDACTED" in captured["payload"]["error_summary"]
