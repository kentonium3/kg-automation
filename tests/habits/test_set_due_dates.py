"""Tests for scripts/habits/set_due_dates.py (FR-003).

Verifies the contract in
kitty-specs/habits-checkin-d6-extract-01KRNV46/contracts/set_due_dates.md.

The MOST IMPORTANT test in this module is `test_z_suffix_rejected` — that's
the #112 regression-prevention backstop. If that test ever fails, the
helper has regressed the bug that caused habits to appear overdue at
the moment the morning cron fires.
"""
from __future__ import annotations

import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

# scripts/habits/ is on sys.path via tests/habits/conftest.py
import set_due_dates as sdd  # type: ignore  # noqa: E402


VALID_ISO = "2026-05-15T23:59:59-04:00"


def _fake_token_file(tmp_path):
    p = tmp_path / "vikunja-token"
    p.write_text("fake-token-for-tests\n")
    return p


def _mock_ok_response():
    """Mock urllib.request.urlopen returning {} (Vikunja PUT 200 OK)."""
    mock = MagicMock()
    mock.__enter__ = MagicMock(return_value=MagicMock(read=MagicMock(
        return_value=b"{}"
    )))
    mock.__exit__ = MagicMock(return_value=False)
    return mock


def _mock_http_error(code: int, reason: str):
    """Raise a urllib.error.HTTPError when urlopen is called."""
    return urllib.error.HTTPError("url", code, reason, hdrs=None, fp=None)


# ---------- Validation tests (#112 regression-prevention) ----------


def test_validate_iso_eod_et_accepts_edt():
    assert sdd.validate_iso_eod_et("2026-05-15T23:59:59-04:00") is None


def test_validate_iso_eod_et_accepts_est():
    assert sdd.validate_iso_eod_et("2026-12-15T23:59:59-05:00") is None


def test_validate_iso_eod_et_rejects_z_suffix():
    """REGRESSION-PREVENTION (#112): UTC Z suffix MUST be rejected.

    If this test fails, the helper has regressed the bug fix that prevents
    habits from appearing overdue the moment the morning cron fires.
    """
    err = sdd.validate_iso_eod_et("2026-05-15T23:59:59Z")
    assert err is not None
    assert "#112" in err
    assert "UTC" in err


def test_validate_iso_eod_et_rejects_malformed():
    assert sdd.validate_iso_eod_et("garbage") is not None
    assert sdd.validate_iso_eod_et("2026-05-15") is not None
    assert sdd.validate_iso_eod_et("2026-05-15T23:59:59") is not None  # missing offset


# ---------- End-to-end tests (main()) ----------


def test_happy_path_all_succeed(tmp_path, capsys):
    token = _fake_token_file(tmp_path)
    with patch.object(sdd.urllib.request, "urlopen", return_value=_mock_ok_response()):
        rc = sdd.main([
            "--habit-ids", "100,101,102",
            "--iso-eod-et", VALID_ISO,
            "--vikunja-token-path", str(token),
            "--vikunja-base-url", "http://test",
        ])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out.splitlines()[0])
    assert payload["succeeded"] == [100, 101, 102]
    assert payload["failed"] == []
    assert "SUMMARY: total=3 succeeded=3 failed=0" in out


def test_partial_failure_exit_1_with_succeeded_subset(tmp_path, capsys):
    """Partial failure: 2 succeed, 1 fails — must exit 1 AND retain succeeded subset."""
    token = _fake_token_file(tmp_path)
    call_count = {"n": 0}

    def side_effect(req, timeout=15):  # noqa: ARG001
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise _mock_http_error(500, "Internal Server Error")
        return _mock_ok_response()

    with patch.object(sdd.urllib.request, "urlopen", side_effect=side_effect):
        rc = sdd.main([
            "--habit-ids", "100,101,102",
            "--iso-eod-et", VALID_ISO,
            "--vikunja-token-path", str(token),
            "--vikunja-base-url", "http://test",
        ])
    out = capsys.readouterr().out
    assert rc == 1, f"partial-failure must exit 1; got {rc}"
    payload = json.loads(out.splitlines()[0])
    assert 100 in payload["succeeded"]  # first call succeeded
    assert 102 in payload["succeeded"]  # third call succeeded
    assert len(payload["failed"]) == 1
    assert payload["failed"][0]["id"] == 101
    assert "500" in payload["failed"][0]["reason"]


def test_all_fail_exit_1_empty_succeeded(tmp_path, capsys):
    token = _fake_token_file(tmp_path)
    with patch.object(
        sdd.urllib.request, "urlopen",
        side_effect=_mock_http_error(500, "Server Error"),
    ):
        rc = sdd.main([
            "--habit-ids", "100,101",
            "--iso-eod-et", VALID_ISO,
            "--vikunja-token-path", str(token),
            "--vikunja-base-url", "http://test",
        ])
    out = capsys.readouterr().out
    assert rc == 1
    payload = json.loads(out.splitlines()[0])
    assert payload["succeeded"] == []
    assert len(payload["failed"]) == 2


def test_dry_run_makes_no_http_calls(tmp_path, capsys):
    """--dry-run MUST NOT call urllib.request.urlopen at all."""
    token = _fake_token_file(tmp_path)
    with patch.object(sdd.urllib.request, "urlopen") as mock_urlopen:
        rc = sdd.main([
            "--habit-ids", "100,101",
            "--iso-eod-et", VALID_ISO,
            "--vikunja-token-path", str(token),
            "--vikunja-base-url", "http://test",
            "--dry-run",
        ])
        assert mock_urlopen.call_count == 0, (
            f"dry-run made {mock_urlopen.call_count} HTTP calls; must be 0"
        )
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out.splitlines()[0])
    assert payload["succeeded"] == [100, 101]
    assert payload["failed"] == []
    assert "DRY-RUN" in out


def test_z_suffix_rejected_at_startup_no_http_calls(tmp_path, capsys):
    """Z-suffix rejection happens BEFORE any HTTP setup. Helper exits 2.

    THIS IS THE #112 REGRESSION-PREVENTION BACKSTOP. If this test fails,
    the bug fix is regressed.
    """
    token = _fake_token_file(tmp_path)
    with patch.object(sdd.urllib.request, "urlopen") as mock_urlopen:
        rc = sdd.main([
            "--habit-ids", "100",
            "--iso-eod-et", "2026-05-15T23:59:59Z",  # UTC Z suffix — must reject
            "--vikunja-token-path", str(token),
            "--vikunja-base-url", "http://test",
        ])
        assert mock_urlopen.call_count == 0, (
            "Z-suffix rejection must happen BEFORE any HTTP setup"
        )
    captured = capsys.readouterr()
    assert rc == 2, f"Z-suffix must produce exit 2; got {rc}"
    assert "#112" in captured.err
    assert "UTC" in captured.err


def test_malformed_iso_rejected(tmp_path, capsys):
    token = _fake_token_file(tmp_path)
    rc = sdd.main([
        "--habit-ids", "100",
        "--iso-eod-et", "garbage",
        "--vikunja-token-path", str(token),
        "--vikunja-base-url", "http://test",
    ])
    captured = capsys.readouterr()
    assert rc == 2
    assert "ERROR" in captured.err


def test_idempotency_same_input_same_output(tmp_path, capsys):
    """Running the helper twice with same input produces same result.

    Real Vikunja PUTs are idempotent; this test verifies the helper itself
    introduces no non-determinism (e.g., timestamps, ordering).
    """
    token = _fake_token_file(tmp_path)
    with patch.object(sdd.urllib.request, "urlopen", return_value=_mock_ok_response()):
        rc1 = sdd.main([
            "--habit-ids", "100,101",
            "--iso-eod-et", VALID_ISO,
            "--vikunja-token-path", str(token),
            "--vikunja-base-url", "http://test",
        ])
        out1 = capsys.readouterr().out
        rc2 = sdd.main([
            "--habit-ids", "100,101",
            "--iso-eod-et", VALID_ISO,
            "--vikunja-token-path", str(token),
            "--vikunja-base-url", "http://test",
        ])
        out2 = capsys.readouterr().out
    assert rc1 == rc2 == 0
    # Outputs identical except for any timestamps (the helper outputs none).
    # Compare the JSON payload (first line) for strict equality.
    assert out1.splitlines()[0] == out2.splitlines()[0]


def test_empty_habit_ids_exits_0(tmp_path, capsys):
    """Empty --habit-ids is not an error — just nothing to do, exit 0."""
    token = _fake_token_file(tmp_path)
    rc = sdd.main([
        "--habit-ids", "",
        "--iso-eod-et", VALID_ISO,
        "--vikunja-token-path", str(token),
        "--vikunja-base-url", "http://test",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out.splitlines()[0])
    assert payload["succeeded"] == []
    assert payload["failed"] == []
