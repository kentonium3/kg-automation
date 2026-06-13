"""Fixture-driven tests for the anthropic-verify detection core.

Verifies the spec exit-code contract from ``contracts/cli.md`` and FR-011:
  0 green, 1 error, 2 shadow, 3 drift, 4 anthropic_rejected, 5 network,
  6 substrate-gap.

Each test builds an office2-shaped layout under ``tmp_path`` via the
``tmp_office2_root`` conftest fixture and the ``build_fixtures`` helpers,
then mocks ``urllib.request.urlopen`` to control the Anthropic ping outcome
without hitting the live API.
"""

from __future__ import annotations

import io
import json
import urllib.error
from unittest.mock import patch

import pytest

from anthropic_verify import core
from tests.security.fixtures import build_fixtures as bf


# --------------------------------------------------------------------------- #
# urlopen mock helpers
# --------------------------------------------------------------------------- #


class _FakeOKResponse:
    """Mimics the ``urllib.request.urlopen`` context manager for HTTP 200."""

    status = 200

    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return self._body


def _ok_urlopen(*_args, **_kwargs):
    body = json.dumps({"model": "claude-haiku-4-5-20251001"}).encode()
    return _FakeOKResponse(body)


def _http_401_urlopen(*_args, **_kwargs):
    raise urllib.error.HTTPError(
        url="https://api.anthropic.com/v1/messages",
        code=401,
        msg="Unauthorized",
        hdrs=None,  # type: ignore[arg-type]
        fp=io.BytesIO(b"Authentication error: invalid x-api-key"),
    )


def _network_urlopen(*_args, **_kwargs):
    raise urllib.error.URLError("[Errno -2] Name or service not known")


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


def test_healthy_returns_exit_0_and_no_findings(tmp_office2_root, capsys):
    agents_dir, plaintext_path = tmp_office2_root
    bf.build_healthy(agents_dir, plaintext_path)
    with patch("anthropic_verify.core.urllib.request.urlopen", _ok_urlopen):
        rc = core.run_check()
    out = capsys.readouterr().out
    assert rc == 0
    assert "FIND" not in out
    assert "anthropic-ping" in out
    assert "HTTP 200" in out


def test_shadow_on_felix_admin_capture_returns_exit_2(tmp_office2_root, capsys):
    agents_dir, plaintext_path = tmp_office2_root
    bf.build_shadow(agents_dir, plaintext_path, agent_id="felix-admin-capture")
    with patch("anthropic_verify.core.urllib.request.urlopen", _ok_urlopen):
        rc = core.run_check()
    out = capsys.readouterr().out
    assert rc == 2
    assert "FIND  shadow felix-admin-capture" in out
    assert "auth_profile_store=1" in out
    assert "auth_profile_state=1" in out


def test_drift_returns_exit_3(tmp_office2_root, capsys):
    agents_dir, plaintext_path = tmp_office2_root
    bf.build_drift(agents_dir, plaintext_path)
    with patch("anthropic_verify.core.urllib.request.urlopen", _ok_urlopen):
        rc = core.run_check()
    out = capsys.readouterr().out
    assert rc == 3
    assert "FIND  drift" in out
    assert "plaintext_sha8=" in out
    assert "sqlite_sha8=" in out


def test_anthropic_rejected_returns_exit_4(tmp_office2_root, capsys):
    agents_dir, plaintext_path = tmp_office2_root
    bf.build_healthy(agents_dir, plaintext_path)
    with patch("anthropic_verify.core.urllib.request.urlopen", _http_401_urlopen):
        rc = core.run_check()
    out = capsys.readouterr().out
    assert rc == 4
    assert "FIND  anthropic_rejected" in out
    assert "http_status=401" in out


def test_network_failure_returns_exit_5(tmp_office2_root, capsys):
    agents_dir, plaintext_path = tmp_office2_root
    bf.build_healthy(agents_dir, plaintext_path)
    with patch("anthropic_verify.core.urllib.request.urlopen", _network_urlopen):
        rc = core.run_check()
    out = capsys.readouterr().out
    assert rc == 5
    assert "FIND  network" in out
    assert "error_class=" in out


def test_main_empty_returns_exit_6(tmp_office2_root, capsys):
    agents_dir, plaintext_path = tmp_office2_root
    bf.build_main_empty(agents_dir, plaintext_path)
    # No ping mock — substrate-gap short-circuits the ping path. Use OK
    # mock as a no-op safety net.
    with patch("anthropic_verify.core.urllib.request.urlopen", _ok_urlopen):
        rc = core.run_check()
    out = capsys.readouterr().out
    assert rc == 6
    assert "FIND  main_empty" in out


def test_plaintext_missing_returns_exit_6(tmp_office2_root, capsys):
    agents_dir, plaintext_path = tmp_office2_root
    bf.build_plaintext_missing(agents_dir, plaintext_path)
    with patch("anthropic_verify.core.urllib.request.urlopen", _ok_urlopen):
        rc = core.run_check()
    out = capsys.readouterr().out
    assert rc == 6
    assert "FIND  plaintext_missing" in out


def test_shadow_plus_drift_returns_shadow_priority(tmp_office2_root, capsys):
    """When shadow + drift both exist, exit code reflects shadow (2)."""
    agents_dir, plaintext_path = tmp_office2_root
    bf.build_drift(agents_dir, plaintext_path)
    # Add a shadow on top of drift.
    bf._build_agent_sqlite(  # noqa: SLF001 - reusing internal builder in test
        agents_dir,
        "felix-admin-capture",
        key_value=bf.SENTINEL_SHADOW,
        state_value=bf.SENTINEL_SHADOW,
    )
    with patch("anthropic_verify.core.urllib.request.urlopen", _ok_urlopen):
        rc = core.run_check()
    out = capsys.readouterr().out
    assert rc == 2  # shadow (2) wins over drift (3) per priority order
    assert "FIND  shadow" in out
    assert "FIND  drift" in out


def test_substrate_gap_wins_over_network_failure(tmp_office2_root):
    """plaintext_missing (substrate-gap=6) > network (5)."""
    agents_dir, plaintext_path = tmp_office2_root
    bf.build_plaintext_missing(agents_dir, plaintext_path)
    with patch("anthropic_verify.core.urllib.request.urlopen", _network_urlopen):
        rc = core.run_check()
    assert rc == 6


def test_discover_agents_skips_missing_sqlite_file(tmp_office2_root):
    """If a sub-agent dir has no sqlite, discover_agents skips it cleanly."""
    agents_dir, _ = tmp_office2_root
    (agents_dir / "ghost-agent" / "agent").mkdir(parents=True)
    bf.build_healthy(agents_dir, _)
    states = core.discover_agents(agents_dir)
    ids = {s.agent_id for s in states}
    assert "ghost-agent" not in ids
    assert "main" in ids


def test_discover_agents_missing_root_returns_empty(tmp_path):
    states = core.discover_agents(tmp_path / "does-not-exist")
    assert states == []


def test_read_plaintext_state_missing_file(tmp_path):
    s = core.read_plaintext_state(tmp_path / "missing")
    assert s.exists is False
    assert s.sha8 is None


def test_read_plaintext_state_present_file(tmp_path):
    p = tmp_path / "file"
    p.write_text("hello\n")
    s = core.read_plaintext_state(p)
    assert s.exists is True
    assert s.sha8 is not None
    assert len(s.sha8) == 8


def test_evaluate_topology_no_main_in_states_triggers_main_empty(tmp_path):
    """Edge case: states list has no 'main' entry at all."""
    findings = core.evaluate_topology(
        states=[],
        plaintext=core.PlaintextFileState(
            path=tmp_path / "x",
            exists=False,
            size_bytes=0,
            sha8=None,
            mode=0,
            uid=0,
            gid=0,
        ),
    )
    assert len(findings) == 1
    assert findings[0].type == "main_empty"


def test_anthropic_ping_ok_classifies_correctly():
    """Direct unit test of ping_anthropic with a mocked ok response."""
    with patch("anthropic_verify.core.urllib.request.urlopen", _ok_urlopen):
        r = core.ping_anthropic("dummy-key")
    assert r.status == "ok"
    assert r.http_status == 200


def test_anthropic_ping_rejected_classifies_correctly():
    with patch("anthropic_verify.core.urllib.request.urlopen", _http_401_urlopen):
        r = core.ping_anthropic("dummy-key")
    assert r.status == "rejected"
    assert r.http_status == 401


def test_anthropic_ping_network_classifies_correctly():
    with patch("anthropic_verify.core.urllib.request.urlopen", _network_urlopen):
        r = core.ping_anthropic("dummy-key")
    assert r.status == "network_error"
    assert r.http_status is None


def test_run_check_emits_verdict_line(tmp_office2_root, capsys):
    agents_dir, plaintext_path = tmp_office2_root
    bf.build_healthy(agents_dir, plaintext_path)
    with patch("anthropic_verify.core.urllib.request.urlopen", _ok_urlopen):
        core.run_check()
    out = capsys.readouterr().out
    assert "==> verify result: green" in out
    assert "(exit 0)" in out


def test_run_check_emits_six_agents_discovered(tmp_office2_root, capsys):
    """Healthy fixture has main + 5 sub-agents = 6 discovered."""
    agents_dir, plaintext_path = tmp_office2_root
    bf.build_healthy(agents_dir, plaintext_path)
    with patch("anthropic_verify.core.urllib.request.urlopen", _ok_urlopen):
        core.run_check()
    out = capsys.readouterr().out
    assert "==> agents: 6 discovered" in out
