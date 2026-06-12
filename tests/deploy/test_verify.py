"""Tests for :mod:`scripts.deploy.lib.verify`."""

from __future__ import annotations

import os
import stat

import pytest

from scripts.deploy.lib import LibResult, verify


# ---------------------------------------------------------------------------
# verify_file_present
# ---------------------------------------------------------------------------


def test_verify_file_present_returns_ok_for_existing_file(tmp_path):
    f = tmp_path / "foo.txt"
    f.write_text("hello", encoding="utf-8")

    result = verify.verify_file_present(f)

    assert isinstance(result, LibResult)
    assert result.ok is True
    assert result.details["path"] == str(f)


def test_verify_file_present_returns_failure_for_missing_file(tmp_path):
    f = tmp_path / "missing.txt"

    result = verify.verify_file_present(f)

    assert result.ok is False
    assert result.details["error_code"] == "FILE_MISSING"


def test_verify_file_present_checks_executable_bit(tmp_path):
    f = tmp_path / "tool.sh"
    f.write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
    # Not yet executable.
    result_before = verify.verify_file_present(f, executable=True)
    assert result_before.ok is False
    assert result_before.details["error_code"] == "NOT_EXECUTABLE"

    # Make executable and re-check.
    f.chmod(f.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    result_after = verify.verify_file_present(f, executable=True)
    assert result_after.ok is True
    assert result_after.details["executable"] is True


def test_verify_file_present_executable_rejects_non_regular_file(tmp_path):
    d = tmp_path / "subdir"
    d.mkdir()

    result = verify.verify_file_present(d, executable=True)

    assert result.ok is False
    assert result.details["error_code"] == "NOT_A_FILE"


# ---------------------------------------------------------------------------
# verify_no_stale_literal
# ---------------------------------------------------------------------------


def test_verify_no_stale_literal_returns_ok_when_literal_absent(tmp_path):
    f = tmp_path / "config.yaml"
    f.write_text("version: v2\nflag: true\n", encoding="utf-8")

    result = verify.verify_no_stale_literal(f, literal="v1.0.0-deprecated")

    assert result.ok is True


def test_verify_no_stale_literal_returns_failure_when_literal_present(tmp_path):
    f = tmp_path / "config.yaml"
    f.write_text("version: v1.0.0-deprecated\n", encoding="utf-8")

    result = verify.verify_no_stale_literal(f, literal="v1.0.0-deprecated")

    assert result.ok is False
    assert result.details["error_code"] == "STALE_LITERAL_PRESENT"


def test_verify_no_stale_literal_handles_missing_file(tmp_path):
    f = tmp_path / "nope.yaml"

    result = verify.verify_no_stale_literal(f, literal="anything")

    assert result.ok is False
    assert result.details["error_code"] == "FILE_MISSING"


def test_verify_no_stale_literal_rejects_empty_literal(tmp_path):
    f = tmp_path / "config.yaml"
    f.write_text("x\n", encoding="utf-8")

    result = verify.verify_no_stale_literal(f, literal="")

    assert result.ok is False
    assert result.details["error_code"] == "INVALID_ARGUMENT"


# ---------------------------------------------------------------------------
# redact_secrets — must cover at least three distinct patterns.
# ---------------------------------------------------------------------------


def test_redact_secrets_strips_long_token_shaped_substring():
    # 40 hex chars — easily over the 32-char floor.
    text = "error: token=deadbeefdeadbeefdeadbeefdeadbeefdeadbeef failed"

    redacted = verify.redact_secrets(text)

    assert "deadbeef" not in redacted
    assert "[REDACTED]" in redacted


def test_redact_secrets_strips_password_assignment():
    text = "DATABASE_URL=postgres://user:password=hunter2supersecret@db/x"

    redacted = verify.redact_secrets(text)

    assert "hunter2supersecret" not in redacted
    assert "password=" not in redacted or "[REDACTED]" in redacted


def test_redact_secrets_strips_bearer_token():
    text = "Authorization: Bearer abc.def.ghi-very-secret-jwt"

    redacted = verify.redact_secrets(text)

    assert "abc.def.ghi-very-secret-jwt" not in redacted
    assert "[REDACTED]" in redacted


def test_redact_secrets_leaves_short_strings_alone():
    text = "rc=1 reason=ok msg=fail"

    redacted = verify.redact_secrets(text)

    # Nothing in this string is 32+ chars or matches password=/Bearer.
    assert redacted == text


def test_redact_secrets_is_idempotent_on_empty_input():
    assert verify.redact_secrets("") == ""


def test_redact_secrets_conservative_floor_is_32_chars():
    """Tokens >= 32 chars are redacted; <32 are left alone."""
    short_token = "a" * 31
    long_token = "a" * 32

    short_redacted = verify.redact_secrets(short_token)
    long_redacted = verify.redact_secrets(long_token)

    assert short_redacted == short_token
    assert "a" * 32 not in long_redacted
    assert "[REDACTED]" in long_redacted


def test_redact_secrets_handles_multiple_patterns_in_one_string():
    text = (
        "GET /api Bearer abcdefghij1234567890abcdef "
        "password=correcthorsebatterystaple "
        "token=zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz"
    )

    redacted = verify.redact_secrets(text)

    assert "abcdefghij1234567890abcdef" not in redacted
    assert "correcthorsebatterystaple" not in redacted
    assert "zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz" not in redacted
    # All three should be replaced with the marker.
    assert redacted.count("[REDACTED]") >= 3
