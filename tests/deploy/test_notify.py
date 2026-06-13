"""Tests for the felix-deployer ntfy notification surface.

Covers the wire-shape contract (``contracts/ntfy-notification-v1.md``),
secret redaction in ``error_summary``, the redact-then-truncate
invariant (including boundary-pinning), and every closed-enum
``error_code`` returned by ``dispatch_failure_notification``.

The notify module lives under ``scripts/deploy/felix-deployer/`` — that
directory name contains a hyphen so it is not importable via
``import scripts.deploy.felix_deployer.notify``. We load it through
``importlib`` from its on-disk path; the same trick the systemd service
uses (path-based ``ExecStart``).
"""

from __future__ import annotations

import importlib
import importlib.util
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


def _minimal_manifest() -> dict[str, Any]:
    return {
        "name": "vikunja-image-bump",
        "tier": 2,
        "schema_version": "v1",
        "entrypoint": "scripts/deploy/example.sh",
        "audited_surface": False,
    }


class _FakeProc:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


# ---------------------------------------------------------------------------
# Rendering: title + body
# ---------------------------------------------------------------------------


def test_render_title_basic():
    assert notify._render_title("vikunja-image-bump") == (
        "felix-deployer failed: vikunja-image-bump"
    )


def test_render_body_basic():
    body = notify._render_body(
        manifest=_minimal_manifest(),
        phase="verification_post",
        error_summary="vikunja smoke check failed: expected 200, got 502",
        head_sha="31f63d6070bf5377fa20be921feb9f0e7f69a608",
        failed_at="2026-06-13T15:30:42Z",
    )
    assert body == (
        "Phase: verification_post\n"
        "Tier: 2\n"
        "Head: 31f63d60\n"
        "Failed at: 2026-06-13T15:30:42Z\n"
        "\n"
        "Error:\n"
        "vikunja smoke check failed: expected 200, got 502"
    )


def test_render_body_empty_error_summary():
    body = notify._render_body(
        manifest=_minimal_manifest(),
        phase="entrypoint",
        error_summary="",
        head_sha="abc",
        failed_at="2026-06-13T00:00:00Z",
    )
    assert "Error:\n(no error summary)" in body


def test_render_body_unknown_head_sha():
    body = notify._render_body(
        manifest=_minimal_manifest(),
        phase="entrypoint",
        error_summary="boom",
        head_sha="",
        failed_at="2026-06-13T00:00:00Z",
    )
    assert "Head: (unknown)\n" in body


# ---------------------------------------------------------------------------
# Redact-then-truncate invariant
# ---------------------------------------------------------------------------


def test_redact_then_truncate_long_summary():
    # 40-char token-shaped secret followed by 1000 chars of padding.
    # Each 'A' run is shorter than the 32-char token threshold so
    # redact_secrets doesn't collapse the padding.
    secret = "B" * 40  # token-shaped → redacted
    padding = ("hello " * 200).rstrip()  # 1199 chars, none redactable
    summary = f"token={secret} {padding}"
    out = notify._redact_and_truncate(summary)
    assert secret not in out
    assert len(out) <= notify.ERROR_SUMMARY_MAX
    assert len(out) == notify.ERROR_SUMMARY_MAX  # filled to cap


def test_redact_then_truncate_secret_at_boundary():
    # Construct a summary where a token-shaped secret would straddle the
    # 500-char boundary. If truncation ran BEFORE redaction, the leading
    # head bytes of the secret would survive in the output.
    prefix = "x" * 480
    secret = "S" * 40  # 32+ chars triggers _TOKEN_RE → fully redacted
    summary = prefix + secret + "tail"
    out = notify._redact_and_truncate(summary)
    # The secret pattern must not appear in any form (head bytes either).
    assert secret not in out
    # And no partial run of 'S' of 8+ characters (the head bytes that
    # truncate-then-redact would leave behind).
    assert "S" * 8 not in out
    assert len(out) <= notify.ERROR_SUMMARY_MAX


def test_redact_then_truncate_empty_input():
    assert notify._redact_and_truncate("") == ""


# ---------------------------------------------------------------------------
# Error-code classification
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "returncode,expected",
    [
        (6, "NTFY_NETWORK_UNREACHABLE"),
        (7, "NTFY_NETWORK_UNREACHABLE"),
        (22, "NTFY_HTTP_ERROR"),
        (28, "NTFY_TIMEOUT"),
        (35, "NTFY_UNKNOWN"),
        (42, "NTFY_UNKNOWN"),
        (1, "NTFY_UNKNOWN"),
    ],
)
def test_classify_error_code(returncode, expected):
    assert notify._classify_error_code(returncode) == expected


# ---------------------------------------------------------------------------
# Topic redaction
# ---------------------------------------------------------------------------


def test_topic_redact_short_topic():
    assert notify._topic_redact("short") == "***"


def test_topic_redact_long_topic():
    topic = "felix-deployer-rndAlpha123XYZ"
    out = notify._topic_redact(topic)
    assert topic not in out
    assert "***" in out
    assert out.startswith(topic[:8])
    assert out.endswith(topic[-4:])


# ---------------------------------------------------------------------------
# dispatch_failure_notification — success path
# ---------------------------------------------------------------------------


def test_dispatch_success(monkeypatch):
    monkeypatch.setenv(notify.NTFY_TOPIC_ENV, "test-topic-alpha-1234")
    seen: dict[str, Any] = {}

    def _fake_run(argv, input=None, capture_output=None, text=None, check=None):
        seen["argv"] = list(argv)
        seen["input"] = input
        return _FakeProc(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(notify.subprocess, "run", _fake_run)

    result = notify.dispatch_failure_notification(
        manifest=_minimal_manifest(),
        phase="verification_post",
        error_summary="vikunja smoke check failed",
        head_sha="31f63d6070bf5377fa20be921feb9f0e7f69a608",
        failed_at="2026-06-13T15:30:42Z",
    )
    assert result.ok is True
    assert result.summary == "ntfy notification sent"
    assert result.details["title"] == "felix-deployer failed: vikunja-image-bump"
    assert "test-topic-alpha-1234" not in result.details["topic_redacted"]
    assert "***" in result.details["topic_redacted"]
    assert result.details["format_version"] == "v1"

    # Curl argv must match the contract exactly (key flags + ordering).
    argv = seen["argv"]
    assert argv[0] == "curl"
    assert "--silent" in argv
    assert "--show-error" in argv
    assert "--fail" in argv
    assert "--max-time" in argv
    assert str(notify.CURL_MAX_TIME_SECONDS) in argv
    assert "--data-binary" in argv
    assert "@-" in argv
    assert argv[-1] == "https://ntfy.sh/test-topic-alpha-1234"
    # Body piped via stdin (not as a CLI argument).
    assert seen["input"].startswith("Phase: verification_post\n")
    assert "Title: felix-deployer failed: vikunja-image-bump" in " ".join(argv)
    assert "Priority: high" in " ".join(argv)
    assert "Tags: warning,rotating_light" in " ".join(argv)


# ---------------------------------------------------------------------------
# dispatch_failure_notification — error-code paths
# ---------------------------------------------------------------------------


def test_dispatch_missing_topic(monkeypatch):
    monkeypatch.delenv(notify.NTFY_TOPIC_ENV, raising=False)
    called = []

    def _fake_run(*args, **kwargs):
        called.append(True)
        return _FakeProc(returncode=0)

    monkeypatch.setattr(notify.subprocess, "run", _fake_run)

    result = notify.dispatch_failure_notification(
        manifest=_minimal_manifest(),
        phase="entrypoint",
        error_summary="boom",
        head_sha="abc",
    )
    assert result.ok is False
    assert result.details["error_code"] == "NTFY_MISSING_TOPIC"
    assert called == []  # curl was NOT invoked


def test_dispatch_empty_topic(monkeypatch):
    monkeypatch.setenv(notify.NTFY_TOPIC_ENV, "   ")
    called = []
    monkeypatch.setattr(
        notify.subprocess,
        "run",
        lambda *a, **kw: called.append(True) or _FakeProc(returncode=0),
    )

    result = notify.dispatch_failure_notification(
        manifest=_minimal_manifest(),
        phase="entrypoint",
        error_summary="boom",
        head_sha="abc",
    )
    assert result.ok is False
    assert result.details["error_code"] == "NTFY_MISSING_TOPIC"
    assert called == []


def test_dispatch_curl_missing(monkeypatch):
    monkeypatch.setenv(notify.NTFY_TOPIC_ENV, "abc")

    def _fake_run(*args, **kwargs):
        raise FileNotFoundError("curl")

    monkeypatch.setattr(notify.subprocess, "run", _fake_run)

    result = notify.dispatch_failure_notification(
        manifest=_minimal_manifest(),
        phase="entrypoint",
        error_summary="boom",
        head_sha="abc",
    )
    assert result.ok is False
    assert result.details["error_code"] == "NTFY_CURL_MISSING"


def test_dispatch_spawn_failed(monkeypatch):
    monkeypatch.setenv(notify.NTFY_TOPIC_ENV, "abc")

    def _fake_run(*args, **kwargs):
        raise OSError("resource temporarily unavailable")

    monkeypatch.setattr(notify.subprocess, "run", _fake_run)

    result = notify.dispatch_failure_notification(
        manifest=_minimal_manifest(),
        phase="entrypoint",
        error_summary="boom",
        head_sha="abc",
    )
    assert result.ok is False
    assert result.details["error_code"] == "NTFY_SPAWN_FAILED"


def test_dispatch_timeout(monkeypatch):
    monkeypatch.setenv(notify.NTFY_TOPIC_ENV, "abc")
    monkeypatch.setattr(
        notify.subprocess,
        "run",
        lambda *a, **kw: _FakeProc(returncode=28, stderr="timeout"),
    )

    result = notify.dispatch_failure_notification(
        manifest=_minimal_manifest(),
        phase="entrypoint",
        error_summary="boom",
        head_sha="abc",
    )
    assert result.ok is False
    assert result.details["error_code"] == "NTFY_TIMEOUT"
    assert len(result.details["stderr_excerpt"]) <= 200


def test_dispatch_network_unreachable_dns(monkeypatch):
    monkeypatch.setenv(notify.NTFY_TOPIC_ENV, "abc")
    monkeypatch.setattr(
        notify.subprocess,
        "run",
        lambda *a, **kw: _FakeProc(returncode=6, stderr="could not resolve host"),
    )

    result = notify.dispatch_failure_notification(
        manifest=_minimal_manifest(),
        phase="entrypoint",
        error_summary="boom",
        head_sha="abc",
    )
    assert result.ok is False
    assert result.details["error_code"] == "NTFY_NETWORK_UNREACHABLE"


def test_dispatch_network_unreachable_connect(monkeypatch):
    monkeypatch.setenv(notify.NTFY_TOPIC_ENV, "abc")
    monkeypatch.setattr(
        notify.subprocess,
        "run",
        lambda *a, **kw: _FakeProc(returncode=7, stderr="connection refused"),
    )

    result = notify.dispatch_failure_notification(
        manifest=_minimal_manifest(),
        phase="entrypoint",
        error_summary="boom",
        head_sha="abc",
    )
    assert result.ok is False
    assert result.details["error_code"] == "NTFY_NETWORK_UNREACHABLE"


def test_dispatch_http_error(monkeypatch):
    monkeypatch.setenv(notify.NTFY_TOPIC_ENV, "abc")
    monkeypatch.setattr(
        notify.subprocess,
        "run",
        lambda *a, **kw: _FakeProc(returncode=22, stderr="HTTP 500"),
    )

    result = notify.dispatch_failure_notification(
        manifest=_minimal_manifest(),
        phase="entrypoint",
        error_summary="boom",
        head_sha="abc",
    )
    assert result.ok is False
    assert result.details["error_code"] == "NTFY_HTTP_ERROR"


def test_dispatch_unknown(monkeypatch):
    monkeypatch.setenv(notify.NTFY_TOPIC_ENV, "abc")
    monkeypatch.setattr(
        notify.subprocess,
        "run",
        lambda *a, **kw: _FakeProc(returncode=42, stderr="weird failure"),
    )

    result = notify.dispatch_failure_notification(
        manifest=_minimal_manifest(),
        phase="entrypoint",
        error_summary="boom",
        head_sha="abc",
    )
    assert result.ok is False
    assert result.details["error_code"] == "NTFY_UNKNOWN"


# ---------------------------------------------------------------------------
# NFR-003: no import-time side effects (no curl spawn, no DNS, no HTTP)
# ---------------------------------------------------------------------------


def test_import_no_side_effects(monkeypatch):
    """Re-importing notify.py from disk must not invoke subprocess.run."""
    call_count = {"n": 0}

    def _fake_run(*args, **kwargs):
        call_count["n"] += 1
        return _FakeProc(returncode=0)

    # Patch the real subprocess.run BEFORE the re-import so any
    # import-time call would land on our counter.
    monkeypatch.setattr(subprocess, "run", _fake_run)
    spec = importlib.util.spec_from_file_location(
        "felix_deployer_notify_import_test",
        FELIX_DEPLOYER_DIR / "notify.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert call_count["n"] == 0
    # And confirm the public surface loaded as expected.
    assert hasattr(module, "dispatch_failure_notification")
    assert module.NOTIFICATION_FORMAT_VERSION == "v1"
