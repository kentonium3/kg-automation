"""Tests for :mod:`scripts.deploy.lib.cron`.

All ``subprocess.run`` calls are mocked. No live ``openclaw cron`` invocations.
"""

from __future__ import annotations

import json
import subprocess

import pytest

from scripts.deploy.lib import LibResult, cron


def _completed(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=[],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


class _RunStub:
    """Records consecutive ``subprocess.run`` calls and returns scripted results."""

    def __init__(self, results):
        self._results = list(results)
        self.calls: list[list[str]] = []

    def __call__(self, argv, *args, **kwargs):
        self.calls.append(list(argv))
        if not self._results:
            raise AssertionError(f"unexpected subprocess.run call: {argv}")
        return self._results.pop(0)


@pytest.fixture
def patch_run(monkeypatch):
    """Return a helper that installs scripted ``subprocess.run`` results."""

    def _install(results):
        stub = _RunStub(results)
        monkeypatch.setattr(cron.subprocess, "run", stub)
        return stub

    return _install


# ---------------------------------------------------------------------------
# openclaw_cron_list
# ---------------------------------------------------------------------------


def test_openclaw_cron_list_parses_jobs_payload(patch_run):
    payload = json.dumps({"jobs": [{"name": "a", "enabled": True}, {"name": "b", "enabled": False}]})
    stub = patch_run([_completed(0, stdout=payload)])

    result = cron.openclaw_cron_list()

    assert isinstance(result, LibResult)
    assert result.ok is True
    assert result.details["crons"] == [
        {"name": "a", "enabled": True},
        {"name": "b", "enabled": False},
    ]
    assert stub.calls == [["openclaw", "cron", "list", "--json"]]


def test_openclaw_cron_list_handles_plain_list_payload(patch_run):
    payload = json.dumps([{"name": "alpha"}, {"name": "beta"}])
    patch_run([_completed(0, stdout=payload)])

    result = cron.openclaw_cron_list()

    assert result.ok is True
    assert [c["name"] for c in result.details["crons"]] == ["alpha", "beta"]


def test_openclaw_cron_list_returns_failure_on_non_zero_exit(patch_run):
    patch_run([_completed(2, stderr="boom")])

    result = cron.openclaw_cron_list()

    assert result.ok is False
    assert result.details["returncode"] == 2
    assert "boom" in result.details["stderr_excerpt"]


# ---------------------------------------------------------------------------
# openclaw_cron_disable
# ---------------------------------------------------------------------------


def test_openclaw_cron_disable_invokes_disable_when_enabled(patch_run):
    list_payload = json.dumps(
        {"jobs": [{"id": "abc123", "name": "felix-x", "enabled": True}]}
    )
    stub = patch_run([
        _completed(0, stdout=list_payload),
        _completed(0, stdout="disabled"),
    ])

    result = cron.openclaw_cron_disable("felix-x")

    assert result.ok is True
    # openclaw expects the UUID positionally (#614).
    assert stub.calls[1] == ["openclaw", "cron", "disable", "abc123"]


def test_openclaw_cron_disable_is_idempotent_when_already_disabled(patch_run):
    list_payload = json.dumps({"jobs": [{"name": "felix-x", "enabled": False}]})
    stub = patch_run([_completed(0, stdout=list_payload)])

    result = cron.openclaw_cron_disable("felix-x")

    assert result.ok is True
    assert result.details["idempotent"] is True
    # Only the list call should have been issued.
    assert len(stub.calls) == 1


def test_openclaw_cron_disable_returns_failure_when_cron_not_found(patch_run):
    list_payload = json.dumps({"jobs": [{"name": "other", "enabled": True}]})
    patch_run([_completed(0, stdout=list_payload)])

    result = cron.openclaw_cron_disable("felix-x")

    assert result.ok is False
    assert result.details["error_code"] == "NOT_FOUND"


def test_openclaw_cron_disable_propagates_subprocess_failure(patch_run):
    list_payload = json.dumps(
        {"jobs": [{"id": "abc123", "name": "felix-x", "enabled": True}]}
    )
    patch_run([
        _completed(0, stdout=list_payload),
        _completed(1, stderr="permission denied"),
    ])

    result = cron.openclaw_cron_disable("felix-x")

    assert result.ok is False
    assert result.details["returncode"] == 1
    assert "permission denied" in result.details["stderr_excerpt"]


def test_openclaw_cron_disable_rejects_empty_name(patch_run):
    stub = patch_run([])

    result = cron.openclaw_cron_disable("")

    assert result.ok is False
    assert result.details["error_code"] == "INVALID_ARGUMENT"
    assert stub.calls == []


# ---------------------------------------------------------------------------
# openclaw_cron_enable
# ---------------------------------------------------------------------------


def test_openclaw_cron_enable_invokes_enable_when_disabled(patch_run):
    list_payload = json.dumps(
        {"jobs": [{"id": "abc123", "name": "felix-x", "enabled": False}]}
    )
    stub = patch_run([
        _completed(0, stdout=list_payload),
        _completed(0, stdout="enabled"),
    ])

    result = cron.openclaw_cron_enable("felix-x")

    assert result.ok is True
    # openclaw expects the UUID positionally (#614).
    assert stub.calls[1] == ["openclaw", "cron", "enable", "abc123"]


def test_openclaw_cron_enable_is_idempotent_when_already_enabled(patch_run):
    list_payload = json.dumps({"jobs": [{"name": "felix-x", "enabled": True}]})
    stub = patch_run([_completed(0, stdout=list_payload)])

    result = cron.openclaw_cron_enable("felix-x")

    assert result.ok is True
    assert result.details["idempotent"] is True
    assert len(stub.calls) == 1


def test_openclaw_cron_enable_handles_status_string(patch_run):
    """status='disabled' should be treated as disabled."""
    list_payload = json.dumps(
        {"jobs": [{"id": "abc123", "name": "felix-x", "status": "disabled"}]}
    )
    stub = patch_run([
        _completed(0, stdout=list_payload),
        _completed(0, stdout="enabled"),
    ])

    result = cron.openclaw_cron_enable("felix-x")

    assert result.ok is True
    assert len(stub.calls) == 2


# ---------------------------------------------------------------------------
# openclaw_cron_edit
# ---------------------------------------------------------------------------


def test_openclaw_cron_edit_with_schedule_only(patch_run):
    list_payload = json.dumps({"jobs": [{"id": "abc123", "name": "felix-x"}]})
    stub = patch_run([
        _completed(0, stdout=list_payload),
        _completed(0, stdout="edited"),
    ])

    result = cron.openclaw_cron_edit("felix-x", schedule="0 */2 * * *")

    assert result.ok is True
    # openclaw uses positional UUID + `--cron` (NOT `--name` + `--schedule`) per #614.
    assert stub.calls[1] == [
        "openclaw",
        "cron",
        "edit",
        "abc123",
        "--cron",
        "0 */2 * * *",
    ]


def test_openclaw_cron_edit_with_tz_only(patch_run):
    """Edit only the timezone; schedule expression preserved at openclaw layer."""
    list_payload = json.dumps({"jobs": [{"id": "abc123", "name": "felix-x"}]})
    stub = patch_run([
        _completed(0, stdout=list_payload),
        _completed(0, stdout="edited"),
    ])

    result = cron.openclaw_cron_edit("felix-x", tz="America/New_York")

    assert result.ok is True
    assert stub.calls[1] == [
        "openclaw",
        "cron",
        "edit",
        "abc123",
        "--tz",
        "America/New_York",
    ]


def test_openclaw_cron_edit_with_both_schedule_and_tz(patch_run):
    """Passing both fields emits both --cron AND --tz to preserve TZ across schedule changes (#614 / mission-debt)."""
    list_payload = json.dumps({"jobs": [{"id": "abc123", "name": "felix-x"}]})
    stub = patch_run([
        _completed(0, stdout=list_payload),
        _completed(0, stdout="edited"),
    ])

    result = cron.openclaw_cron_edit(
        "felix-x",
        schedule="*/15 * * * *",
        tz="America/New_York",
    )

    assert result.ok is True
    edit_call = stub.calls[1]
    assert "abc123" in edit_call
    assert "--cron" in edit_call
    assert "*/15 * * * *" in edit_call
    assert "--tz" in edit_call
    assert "America/New_York" in edit_call


def test_openclaw_cron_edit_requires_at_least_one_field(patch_run):
    stub = patch_run([])

    result = cron.openclaw_cron_edit("felix-x")

    assert result.ok is False
    assert result.details["error_code"] == "INVALID_ARGUMENT"
    assert stub.calls == []


def test_openclaw_cron_edit_refuses_unregistered_cron(patch_run):
    list_payload = json.dumps({"jobs": [{"id": "zzz999", "name": "other"}]})
    patch_run([_completed(0, stdout=list_payload)])

    result = cron.openclaw_cron_edit("felix-x", schedule="* * * * *")

    assert result.ok is False
    assert result.details["error_code"] == "NOT_FOUND"
