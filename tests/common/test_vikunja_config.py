"""Unit tests for the Vikunja token-path resolution seam
(``scripts.common.vikunja_config.get_vikunja_token_path`` — mission
``vikunja-token-seam-kent-cutover-01KY8XQ0``, phase 2 of #860).

These lock the three properties the mission depends on:

- **Env override wins** — ``VIKUNJA_TOKEN_PATH`` (set & non-empty) is the
  highest-precedence resolution source (FR-001).
- **Default is the kent path** — with the override unset/empty, resolution
  falls to the single canonical default, the kent-owned runtime credential
  (FR-003). This is the one place the runtime Vikunja identity lives.
- **Single fail-loud error** — a missing/unreadable token file raises exactly
  one :exc:`VikunjaConfigError` naming both the env var and the resolved path
  (NFR-002), never N divergent per-script messages.

The single-point-*flip* proof (that this lever moves ``VikunjaClient`` and every
routed consumer) lives in ``test_vikunja_token_seam.py`` (SC-002).
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts.common import vikunja_config as vcfg
from scripts.common.vikunja_config import (
    VikunjaConfigError,
    get_vikunja_token_path,
)

_KENT_TOKEN_PATH = Path("/data/services/openclaw/secrets/vikunja-api-kent")


# ---------------------------------------------------------------------------
# Env override wins
# ---------------------------------------------------------------------------


def test_env_override_wins(monkeypatch, tmp_path) -> None:
    token_file = tmp_path / "vikunja-api-override"
    token_file.write_text("override-token\n", encoding="utf-8")
    monkeypatch.setenv("VIKUNJA_TOKEN_PATH", str(token_file))
    assert get_vikunja_token_path() == token_file


def test_env_override_takes_precedence_over_default(monkeypatch, tmp_path) -> None:
    # Even with a (hypothetically present) default, the override is chosen; the
    # resolved path is the override, not the module default.
    token_file = tmp_path / "elsewhere"
    token_file.write_text("t\n", encoding="utf-8")
    monkeypatch.setenv("VIKUNJA_TOKEN_PATH", str(token_file))
    resolved = get_vikunja_token_path()
    assert resolved == token_file
    assert resolved != vcfg._DEFAULT_TOKEN_PATH


@pytest.mark.parametrize("blank", ["", "   ", "\t"])
def test_blank_env_override_falls_back_to_default(monkeypatch, blank) -> None:
    # An empty/whitespace override is treated as unset → the fail-loud error
    # names the module default (kent) path, proving the fallback branch.
    monkeypatch.setenv("VIKUNJA_TOKEN_PATH", blank)
    with pytest.raises(VikunjaConfigError) as info:
        get_vikunja_token_path()
    assert str(_KENT_TOKEN_PATH) in str(info.value)


# ---------------------------------------------------------------------------
# Default is the kent path
# ---------------------------------------------------------------------------


def test_default_constant_is_the_kent_path() -> None:
    # FR-003: the single default is the kent-owned runtime credential.
    assert vcfg._DEFAULT_TOKEN_PATH == _KENT_TOKEN_PATH


def test_default_is_used_when_override_unset(monkeypatch, tmp_path) -> None:
    # With the override unset and the default monkeypatched to a present file,
    # resolution returns the (patched) default — the fallback path resolves to
    # _DEFAULT_TOKEN_PATH.
    monkeypatch.delenv("VIKUNJA_TOKEN_PATH", raising=False)
    default_file = tmp_path / "vikunja-api-kent"
    default_file.write_text("kent-token\n", encoding="utf-8")
    monkeypatch.setattr(vcfg, "_DEFAULT_TOKEN_PATH", default_file)
    assert get_vikunja_token_path() == default_file


# ---------------------------------------------------------------------------
# Single fail-loud error (NFR-002)
# ---------------------------------------------------------------------------


def test_missing_file_raises_typed_error(monkeypatch, tmp_path) -> None:
    missing = tmp_path / "does-not-exist"
    monkeypatch.setenv("VIKUNJA_TOKEN_PATH", str(missing))
    with pytest.raises(VikunjaConfigError) as info:
        get_vikunja_token_path()
    message = str(info.value)
    # Names both the env var and the resolved path (NFR-002).
    assert "VIKUNJA_TOKEN_PATH" in message
    assert str(missing) in message


def test_directory_is_not_a_valid_token_file(monkeypatch, tmp_path) -> None:
    # A path that exists but is not a regular file fails loud too (is_file()).
    monkeypatch.setenv("VIKUNJA_TOKEN_PATH", str(tmp_path))
    with pytest.raises(VikunjaConfigError):
        get_vikunja_token_path()


@pytest.mark.skipif(
    not hasattr(os, "geteuid") or os.geteuid() == 0,
    reason="root bypasses filesystem read permissions; unreadable-file check is a no-op",
)
def test_unreadable_file_raises_typed_error(monkeypatch, tmp_path) -> None:
    token_file = tmp_path / "vikunja-api-unreadable"
    token_file.write_text("secret\n", encoding="utf-8")
    token_file.chmod(0o000)
    monkeypatch.setenv("VIKUNJA_TOKEN_PATH", str(token_file))
    try:
        with pytest.raises(VikunjaConfigError) as info:
            get_vikunja_token_path()
        assert str(token_file) in str(info.value)
    finally:
        # Restore perms so tmp_path teardown can remove the file.
        token_file.chmod(0o600)


def test_missing_default_error_names_kent_path(monkeypatch) -> None:
    # With no override and the real (absent-on-test-host) default, the single
    # error names the kent default — the operator's one place to look.
    monkeypatch.delenv("VIKUNJA_TOKEN_PATH", raising=False)
    # Guard: only meaningful when the real default truly is absent (it is, on
    # any non-office2 host). If it somehow exists, the assertion below is skipped.
    if vcfg._DEFAULT_TOKEN_PATH.exists():
        pytest.skip("real kent token file present on this host")
    with pytest.raises(VikunjaConfigError) as info:
        get_vikunja_token_path()
    assert str(_KENT_TOKEN_PATH) in str(info.value)
