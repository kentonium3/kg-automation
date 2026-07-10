"""Tests for scripts.common.alert_bus.delivery and the public emit().

All subprocess calls are mocked — no live ntfy is ever contacted.
"""

from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

from scripts.common.alert_bus import emit
from scripts.common.alert_bus.delivery import (
    base_url,
    deliver,
    resolve_topic,
)
from scripts.common.alert_bus.model import Alert, Severity


def _alert(**overrides) -> Alert:
    kwargs = {
        "source": "felix-deployer/apply",
        "severity": Severity.ERROR,
        "title": "felix-deployer failed",
        "description": "Dry-run failed before apply.",
    }
    kwargs.update(overrides)
    return Alert(**kwargs)


@pytest.fixture
def topic_env(monkeypatch):
    monkeypatch.setenv("FELIX_ALERT_NTFY_TOPIC", "secret-topic-abc")
    monkeypatch.setenv("FELIX_ALERT_NTFY_BASE_URL", "https://ntfy.example")
    return "secret-topic-abc"


def test_resolve_topic_strips(monkeypatch):
    monkeypatch.setenv("FELIX_ALERT_NTFY_TOPIC", "  padded  ")
    assert resolve_topic() == "padded"


def test_resolve_topic_blank_when_unset(monkeypatch):
    monkeypatch.delenv("FELIX_ALERT_NTFY_TOPIC", raising=False)
    assert resolve_topic() == ""


def test_base_url_default(monkeypatch):
    monkeypatch.delenv("FELIX_ALERT_NTFY_BASE_URL", raising=False)
    assert base_url() == "https://ntfy.sh"


def test_base_url_env_override(monkeypatch):
    monkeypatch.setenv("FELIX_ALERT_NTFY_BASE_URL", "https://ntfy.example")
    assert base_url() == "https://ntfy.example"


def test_missing_topic_no_post(monkeypatch):
    monkeypatch.delenv("FELIX_ALERT_NTFY_TOPIC", raising=False)
    called = {"n": 0}

    def _fail(*a, **k):
        called["n"] += 1
        raise AssertionError("subprocess.run must not be called")

    monkeypatch.setattr(subprocess, "run", _fail)
    result = deliver(_alert())
    assert result.ok is False
    assert result.reason == "NTFY_MISSING_TOPIC"
    assert result.topic_configured is False
    assert called["n"] == 0


def test_successful_delivery_builds_correct_argv(monkeypatch, topic_env):
    captured = {}

    def _run(argv, **kwargs):
        captured["argv"] = argv
        captured["input"] = kwargs.get("input")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", _run)
    result = deliver(
        _alert(severity=Severity.CRITICAL, title="urgent", description="boom")
    )
    assert result.ok is True
    assert result.reason is None
    assert result.topic_configured is True

    argv = captured["argv"]
    assert argv[0] == "curl"
    for flag in ("--silent", "--show-error", "--fail", "--max-time", "--data-binary"):
        assert flag in argv
    assert "@-" in argv
    # base url + topic
    assert argv[-1] == "https://ntfy.example/secret-topic-abc"
    # severity map: critical -> ("max", "rotating_light,sos")
    assert "Title: urgent" in argv
    assert "Priority: max" in argv
    assert "Tags: rotating_light,sos" in argv
    # body passed via stdin
    assert "boom" in captured["input"]


@pytest.mark.parametrize(
    "rc,expected",
    [
        (6, "CURL_CONNECT"),
        (7, "CURL_CONNECT"),
        (22, "CURL_HTTP"),
        (28, "CURL_TIMEOUT"),
        (99, "CURL_ERROR:99"),
    ],
)
def test_curl_failure_maps_to_reason(monkeypatch, topic_env, rc, expected):
    def _run(argv, **kwargs):
        return SimpleNamespace(returncode=rc, stdout="", stderr="err")

    monkeypatch.setattr(subprocess, "run", _run)
    result = deliver(_alert())
    assert result.ok is False
    assert result.reason == expected
    assert result.topic_configured is True


def test_timeout_returns_result_no_raise(monkeypatch, topic_env):
    def _run(argv, **kwargs):
        raise subprocess.TimeoutExpired(cmd=argv, timeout=15)

    monkeypatch.setattr(subprocess, "run", _run)
    result = deliver(_alert())
    assert result.ok is False
    assert result.reason == "CURL_TIMEOUT"


def test_oserror_returns_result_no_raise(monkeypatch, topic_env):
    def _run(argv, **kwargs):
        raise FileNotFoundError("curl not found")

    monkeypatch.setattr(subprocess, "run", _run)
    result = deliver(_alert())
    assert result.ok is False
    assert result.reason.startswith("CURL_EXEC_ERROR:")


def test_emit_is_deliver_and_never_raises(monkeypatch, topic_env):
    def _run(argv, **kwargs):
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", _run)
    assert emit(_alert()).ok is True


def test_emit_swallows_unexpected_exceptions(monkeypatch, topic_env):
    # Force an unexpected error from deep in delivery to prove emit() catches
    # anything, not just the subprocess exceptions delivery already handles.
    def _boom(*a, **k):
        raise RuntimeError("unexpected explosion")

    monkeypatch.setattr(
        "scripts.common.alert_bus.delivery.render_body", _boom
    )
    result = emit(_alert())
    assert result.ok is False
    assert result.reason.startswith("BUS_ERROR:")
