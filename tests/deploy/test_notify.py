"""Tests for the felix-deployer notify surface (felix-alert bus backend).

Post-WP02 (#701), ``notify.py`` owns no curl/ntfy code: every dispatch path
builds an :class:`~scripts.common.alert_bus.Alert` and calls
:func:`~scripts.common.alert_bus.emit`. These tests mock ``notify.emit`` (the
symbol imported into the module) and assert on the Alert that was built and on
the ``LibResult`` / ``bool`` return contract each caller depends on.

The notify module lives under ``scripts/deploy/felix-deployer/`` — that
directory name contains a hyphen so it is not importable via
``import scripts.deploy.felix_deployer.notify``. We load it through
``importlib`` from its on-disk path; the same trick the systemd service uses.
"""

from __future__ import annotations

import importlib
import importlib.util
import pathlib
import sys
from typing import Any

import pytest

from scripts.common.alert_bus import Alert, AlertResult, Severity

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


class _EmitSpy:
    """Capture the Alert passed to emit() and return a canned AlertResult."""

    def __init__(self, result: AlertResult):
        self._result = result
        self.calls: list[Alert] = []

    def __call__(self, alert: Alert) -> AlertResult:
        self.calls.append(alert)
        return self._result

    @property
    def last(self) -> Alert:
        return self.calls[-1]


def _ok() -> AlertResult:
    return AlertResult(ok=True, reason=None, topic_configured=True)


def _fail(reason: str, topic_configured: bool = True) -> AlertResult:
    return AlertResult(ok=False, reason=reason, topic_configured=topic_configured)


# ---------------------------------------------------------------------------
# dispatch_failure_notification — Alert construction + return contract
# ---------------------------------------------------------------------------


def test_failure_builds_error_alert_and_reports_delivered(monkeypatch):
    spy = _EmitSpy(_ok())
    monkeypatch.setattr(notify, "emit", spy)

    result = notify.dispatch_failure_notification(
        manifest=_minimal_manifest(),
        phase="verification_post",
        error_summary="vikunja smoke check failed: expected 200, got 502",
        head_sha="31f63d6070bf5377fa20be921feb9f0e7f69a608",
        failed_at="2026-06-13T15:30:42Z",
    )

    assert result.ok is True
    assert result.summary == "alert delivered"
    assert result.details["title"] == "felix-deployer failed: vikunja-image-bump"
    assert result.details["format_version"] == "v1"

    alert = spy.last
    assert isinstance(alert, Alert)
    assert alert.severity is Severity.ERROR
    assert alert.source == "felix-deployer/apply"
    assert alert.title == "felix-deployer failed: vikunja-image-bump"
    assert "vikunja smoke check failed" in alert.description
    # Core context lands in details.
    assert alert.details["phase"] == "verification_post"
    assert alert.details["tier"] == "2"
    assert alert.details["head"] == "31f63d60"
    assert alert.details["failed_at"] == "2026-06-13T15:30:42Z"


def test_failure_empty_summary_degrades_gracefully(monkeypatch):
    spy = _EmitSpy(_ok())
    monkeypatch.setattr(notify, "emit", spy)

    notify.dispatch_failure_notification(
        manifest=_minimal_manifest(),
        phase="entrypoint",
        error_summary="",
        head_sha="abc",
        failed_at="2026-06-13T00:00:00Z",
    )
    assert spy.last.description == "(no error summary)"
    assert spy.last.details["head"] == "abc"


def test_failure_unknown_head(monkeypatch):
    spy = _EmitSpy(_ok())
    monkeypatch.setattr(notify, "emit", spy)

    notify.dispatch_failure_notification(
        manifest=_minimal_manifest(),
        phase="entrypoint",
        error_summary="boom",
        head_sha="",
    )
    assert spy.last.details["head"] == "(unknown)"


def test_failure_missing_topic_maps_to_error_code(monkeypatch):
    spy = _EmitSpy(_fail("NTFY_MISSING_TOPIC", topic_configured=False))
    monkeypatch.setattr(notify, "emit", spy)

    result = notify.dispatch_failure_notification(
        manifest=_minimal_manifest(),
        phase="entrypoint",
        error_summary="boom",
        head_sha="abc",
    )
    assert result.ok is False
    assert result.details["error_code"] == "NTFY_MISSING_TOPIC"
    assert result.details["topic_configured"] is False


@pytest.mark.parametrize(
    "reason",
    ["CURL_TIMEOUT", "CURL_CONNECT", "CURL_HTTP", "CURL_ERROR:42", "BUS_ERROR:ValueError"],
)
def test_failure_delivery_error_reason_passthrough(monkeypatch, reason):
    spy = _EmitSpy(_fail(reason))
    monkeypatch.setattr(notify, "emit", spy)

    result = notify.dispatch_failure_notification(
        manifest=_minimal_manifest(),
        phase="entrypoint",
        error_summary="boom",
        head_sha="abc",
    )
    assert result.ok is False
    assert result.details["error_code"] == reason


# ---------------------------------------------------------------------------
# #699 / SC-002 — real stderr threaded into the Alert details
# ---------------------------------------------------------------------------


def test_failure_threads_real_stderr_into_alert_details(monkeypatch):
    """The apply result's captured stderr/argv/returncode reach Alert.details
    so the operator sees the failing CAUSE, not just "dry-run failed".

    This is the #699 / SC-002 regression guard: before WP02 the tick passed only
    ``result.summary`` (e.g. "dry-run failed; not applying"), dropping the real
    error that named the missing exec bit.
    """
    spy = _EmitSpy(_ok())
    monkeypatch.setattr(notify, "emit", spy)

    # A realistic captured stderr for the #699 case (a non-executable deploy
    # script). The distinctive cause phrase must survive redaction+render.
    distinctive = "line 1: deploy.sh: Permission denied (exit 126)"
    notify.dispatch_failure_notification(
        manifest={"name": "felix-calendar-helper", "tier": 3},
        phase="dry_run",
        error_summary="dry-run failed; not applying",
        head_sha="0628e279aa",
        details={
            "stderr_excerpt": distinctive,
            "stdout_excerpt": "",
            "argv": "bash deploy.sh",
            "returncode": 126,
            "manifest_path": "deploys/queued/calendar.yaml",
            "failed_command": "bash deploy.sh",
        },
    )

    alert = spy.last
    assert alert.details["stderr_excerpt"] == distinctive
    assert alert.details["returncode"] == "126"
    assert alert.details["manifest_path"] == "deploys/queued/calendar.yaml"
    assert "deploy.sh" in alert.details["failed_command"]
    # Empty optional values are dropped (no key=None / key= placeholders).
    assert "stdout_excerpt" not in alert.details or alert.details["stdout_excerpt"] == ""

    # And the rendered body actually names the failing cause (the whole point of
    # #699): the operator diagnoses without SSHing into office2.
    from scripts.common.alert_bus.render import render_body

    body = render_body(alert)
    assert "Permission denied" in body
    assert distinctive in body


# ---------------------------------------------------------------------------
# dispatch_rebaseline_alert
# ---------------------------------------------------------------------------


def _make_token(**kw) -> dict:
    token = {"surface_ids": ["openclaw-agent-prompts"], "alerts_emitted": []}
    token.update(kw)
    return token


def test_rebaseline_dedupe_skips_already_emitted(monkeypatch):
    spy = _EmitSpy(_ok())
    monkeypatch.setattr(notify, "emit", spy)
    token = _make_token(alerts_emitted=["rebaseline_failed"])

    result = notify.dispatch_rebaseline_alert(
        event_key="rebaseline_failed",
        token=token,
        detail="some error",
        head_sha="aabbccdd",
    )
    assert result.ok is True
    assert result.details.get("deduplicated") is True
    assert token["alerts_emitted"].count("rebaseline_failed") == 1
    assert spy.calls == []  # emit not called on dedupe


def test_rebaseline_first_send_builds_alert_and_mutates_token(monkeypatch):
    spy = _EmitSpy(_ok())
    monkeypatch.setattr(notify, "emit", spy)
    token = _make_token(alerts_emitted=[])

    result = notify.dispatch_rebaseline_alert(
        event_key="unexpected_drift",
        token=token,
        detail="b2 outside expected set",
        head_sha="deadbeef",
        registry={"rebaseline_command": "rm baselines/* && audit.sh"},
    )
    assert result.ok is True
    assert "unexpected_drift" in token["alerts_emitted"]

    alert = spy.last
    assert alert.severity is Severity.ERROR
    assert alert.source == "felix-deployer/rebaseline"
    assert alert.title == "felix-deployer rebaseline: unexpected_drift"
    assert alert.details["event"] == "unexpected_drift"
    assert alert.details["detail"] == "b2 outside expected set"
    assert alert.details["head"] == "deadbeef"
    assert alert.details["surfaces"] == "openclaw-agent-prompts"
    assert alert.action == "rm baselines/* && audit.sh"


def test_rebaseline_not_delivered_does_not_mutate_token(monkeypatch):
    spy = _EmitSpy(_fail("NTFY_MISSING_TOPIC", topic_configured=False))
    monkeypatch.setattr(notify, "emit", spy)
    token = _make_token(alerts_emitted=[])

    result = notify.dispatch_rebaseline_alert(
        event_key="rebaseline_failed",
        token=token,
        detail="boom",
        head_sha="abc",
    )
    assert result.ok is False
    assert result.details["error_code"] == "NTFY_MISSING_TOPIC"
    # Not delivered → do NOT burn the dedupe slot.
    assert "rebaseline_failed" not in token["alerts_emitted"]


# ---------------------------------------------------------------------------
# dispatch_health_notification — bool contract
# ---------------------------------------------------------------------------


def test_health_delivered_returns_true(monkeypatch):
    spy = _EmitSpy(_ok())
    monkeypatch.setattr(notify, "emit", spy)

    delivered = notify.dispatch_health_notification(
        "felix-deployer", "git advance stalled", "behind=5", topic_env="IGNORED"
    )
    assert delivered is True
    alert = spy.last
    assert alert.severity is Severity.ERROR
    assert alert.source == "felix-deployer/health/felix-deployer"
    assert alert.title == "git advance stalled"
    assert "behind=5" in alert.description
    assert alert.details["actor"] == "felix-deployer"


def test_health_not_delivered_returns_false(monkeypatch):
    spy = _EmitSpy(_fail("NTFY_MISSING_TOPIC", topic_configured=False))
    monkeypatch.setattr(notify, "emit", spy)

    delivered = notify.dispatch_health_notification(
        "agent-prompt-sync", "t", "b", topic_env="IGNORED"
    )
    assert delivered is False


def test_health_topic_env_is_vestigial(monkeypatch):
    """topic_env is accepted but ignored; delivery is driven only by emit()."""
    spy = _EmitSpy(_ok())
    monkeypatch.setattr(notify, "emit", spy)

    # Called without topic_env at all — signature default keeps it optional.
    delivered = notify.dispatch_health_notification("felix-deployer", "t", "b")
    assert delivered is True


def test_health_empty_body_degrades(monkeypatch):
    spy = _EmitSpy(_ok())
    monkeypatch.setattr(notify, "emit", spy)

    notify.dispatch_health_notification("felix-deployer", "t", "", topic_env="x")
    assert spy.last.description == "(no detail)"


# ---------------------------------------------------------------------------
# SC-006: no curl/ntfy code remains in notify.py
# ---------------------------------------------------------------------------


def test_notify_has_no_curl_or_subprocess():
    """SC-006: no ntfy/curl CODE remains — delivery is via the bus only.

    Asserts on executable code (imports + calls), not on doc-string prose that
    merely narrates the migration.
    """
    source = (FELIX_DEPLOYER_DIR / "notify.py").read_text(encoding="utf-8")
    # No subprocess machinery.
    assert "import subprocess" not in source
    assert "subprocess.run" not in source
    # No curl argv construction.
    assert '"curl"' not in source
    assert "'curl'" not in source
    # Delivery is via the bus only.
    assert "from scripts.common.alert_bus import" in source
    assert "emit(" in source


# ---------------------------------------------------------------------------
# NFR-003: no import-time side effects (no bus call, no HTTP, no subprocess)
# ---------------------------------------------------------------------------


def test_import_no_side_effects(monkeypatch):
    """Re-importing notify.py from disk must not call emit()."""
    import scripts.common.alert_bus as bus

    call_count = {"n": 0}

    def _fake_emit(alert):
        call_count["n"] += 1
        return _ok()

    monkeypatch.setattr(bus, "emit", _fake_emit)
    spec = importlib.util.spec_from_file_location(
        "felix_deployer_notify_import_test",
        FELIX_DEPLOYER_DIR / "notify.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert call_count["n"] == 0
    assert hasattr(module, "dispatch_failure_notification")
    assert module.NOTIFICATION_FORMAT_VERSION == "v1"
