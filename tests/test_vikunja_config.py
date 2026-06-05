"""Unit tests for scripts.common.vikunja_config (mission #520, WP01).

Covers all 7 scenarios from contracts/url-config.md § Test contract,
plus one bonus edge case (empty file), for a total of 8 tests.

All tests use ``monkeypatch`` for environment variable manipulation and
``tmp_path`` + ``monkeypatch.setattr`` for the canonical file path.
No live HTTP; no writes to /data/services/openclaw/config/.
"""
from __future__ import annotations

import pytest

import scripts.common.vikunja_config as vikunja_config_module
from scripts.common.vikunja_config import VikunjaConfigError, get_vikunja_base_url

_VALID_URL_WITH_SLASH = "https://office2.tail0f5f56.ts.net/api/v1/"
_VALID_URL_NO_SLASH = "https://office2.tail0f5f56.ts.net/api/v1"
_ALTERNATE_URL = "https://100.92.197.90:3456/api/v1/"


def _set_file_path(monkeypatch, tmp_path):
    """Redirect _CANONICAL_FILE_PATH to a temp file for tests."""
    fake_path = tmp_path / "vikunja-base-url.txt"
    monkeypatch.setattr(vikunja_config_module, "_CANONICAL_FILE_PATH", fake_path)
    return fake_path


# ---------------------------------------------------------------------------
# Test 1: Env var precedence — file is NOT consulted when env var is set
# ---------------------------------------------------------------------------


def test_env_var_takes_precedence_over_file(monkeypatch, tmp_path):
    """When VIKUNJA_BASE_URL is set, the function returns the env var value
    and does NOT read the file (even if the file contains a different URL)."""
    fake_path = _set_file_path(monkeypatch, tmp_path)
    # Write a different URL to the file to confirm it is not consulted
    fake_path.write_text(_ALTERNATE_URL, encoding="utf-8")

    monkeypatch.setenv("VIKUNJA_BASE_URL", _VALID_URL_WITH_SLASH)

    result = get_vikunja_base_url()
    assert result == _VALID_URL_WITH_SLASH
    assert result != _ALTERNATE_URL


# ---------------------------------------------------------------------------
# Test 2: File fallback — used when env var is unset
# ---------------------------------------------------------------------------


def test_file_fallback_when_env_var_unset(monkeypatch, tmp_path):
    """When VIKUNJA_BASE_URL is unset, the file's URL is read and returned."""
    fake_path = _set_file_path(monkeypatch, tmp_path)
    fake_path.write_text(_VALID_URL_WITH_SLASH, encoding="utf-8")

    monkeypatch.delenv("VIKUNJA_BASE_URL", raising=False)

    result = get_vikunja_base_url()
    assert result == _VALID_URL_WITH_SLASH


# ---------------------------------------------------------------------------
# Test 3: Trailing-slash normalization — env var without trailing slash
# ---------------------------------------------------------------------------


def test_trailing_slash_normalized_from_env_var(monkeypatch, tmp_path):
    """URL returned always has a trailing slash, even when the env var does not."""
    _set_file_path(monkeypatch, tmp_path)  # redirect path (file not needed)
    monkeypatch.setenv("VIKUNJA_BASE_URL", _VALID_URL_NO_SLASH)

    result = get_vikunja_base_url()
    assert result.endswith("/")
    assert result == _VALID_URL_WITH_SLASH


# ---------------------------------------------------------------------------
# Test 4: Whitespace stripping — file has leading/trailing whitespace
# ---------------------------------------------------------------------------


def test_whitespace_stripped_from_file(monkeypatch, tmp_path):
    """Leading and trailing whitespace in the file is stripped; trailing slash is
    still normalized."""
    fake_path = _set_file_path(monkeypatch, tmp_path)
    # File has a trailing newline and a URL without trailing slash
    fake_path.write_text(f"  {_VALID_URL_NO_SLASH}\n", encoding="utf-8")

    monkeypatch.delenv("VIKUNJA_BASE_URL", raising=False)

    result = get_vikunja_base_url()
    assert result == _VALID_URL_WITH_SLASH


# ---------------------------------------------------------------------------
# Test 5: Empty env var falls through to file
# ---------------------------------------------------------------------------


def test_empty_env_var_falls_through_to_file(monkeypatch, tmp_path):
    """An empty VIKUNJA_BASE_URL env var is treated as absent; file is read."""
    fake_path = _set_file_path(monkeypatch, tmp_path)
    fake_path.write_text(_VALID_URL_WITH_SLASH, encoding="utf-8")

    monkeypatch.setenv("VIKUNJA_BASE_URL", "")

    result = get_vikunja_base_url()
    assert result == _VALID_URL_WITH_SLASH


# ---------------------------------------------------------------------------
# Test 6: Both missing — VikunjaConfigError naming both expected locations
# ---------------------------------------------------------------------------


def test_both_missing_raises_config_error(monkeypatch, tmp_path):
    """When neither env var nor file is available, VikunjaConfigError is raised
    with a message that names both expected sources."""
    fake_path = _set_file_path(monkeypatch, tmp_path)
    # Deliberately do NOT create the file
    assert not fake_path.exists()

    monkeypatch.delenv("VIKUNJA_BASE_URL", raising=False)

    with pytest.raises(VikunjaConfigError) as exc_info:
        get_vikunja_base_url()

    msg = str(exc_info.value)
    # Error message must name both expected locations
    assert "VIKUNJA_BASE_URL" in msg
    assert str(fake_path) in msg


# ---------------------------------------------------------------------------
# Test 7: URL validation — invalid URL raises VikunjaConfigError
# ---------------------------------------------------------------------------


def test_invalid_url_raises_config_error(monkeypatch, tmp_path):
    """A URL that does not match the required pattern raises VikunjaConfigError."""
    _set_file_path(monkeypatch, tmp_path)
    monkeypatch.setenv("VIKUNJA_BASE_URL", "not-a-url")

    with pytest.raises(VikunjaConfigError) as exc_info:
        get_vikunja_base_url()

    msg = str(exc_info.value)
    assert "not-a-url" in msg


# ---------------------------------------------------------------------------
# Test 8 (bonus): Empty file — whitespace-only file raises VikunjaConfigError
# ---------------------------------------------------------------------------


def test_empty_file_raises_config_error(monkeypatch, tmp_path):
    """A file containing only whitespace is treated as empty and raises
    VikunjaConfigError (not silently defaulting or returning an empty URL)."""
    fake_path = _set_file_path(monkeypatch, tmp_path)
    fake_path.write_text("   \n\t  \n", encoding="utf-8")

    monkeypatch.delenv("VIKUNJA_BASE_URL", raising=False)

    with pytest.raises(VikunjaConfigError) as exc_info:
        get_vikunja_base_url()

    msg = str(exc_info.value)
    assert "empty" in msg.lower()
