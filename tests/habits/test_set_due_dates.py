"""Tests for scripts/habits/set_due_dates.py (FR-003) — bulk --iso-eod-et mode.

Verifies the contract in
kitty-specs/habits-checkin-d6-extract-01KRNV46/contracts/set_due_dates.md,
as changed by #1111: each habit is read (v2), PATCHed with only
``due_date``, and read back; a changed rule is a failure. The
``--reconcile-schedule`` mode was retired by #1111 (the sweeper moves
day-specific habits by their own rule); the regression tests that guarded
the --iso-eod-et mode against it and the invocation-form tests moved here
from the deleted ``test_set_due_dates_reconcile.py``.

The MOST IMPORTANT test in this module is `test_z_suffix_rejected` — that's
the #112 regression-prevention backstop. If that test ever fails, the
helper has regressed the bug that caused habits to appear overdue at
the moment the morning cron fires.
"""
from __future__ import annotations

import json
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

# scripts/habits/ is on sys.path via tests/habits/conftest.py
import set_due_dates as sdd  # type: ignore  # noqa: E402

from tests.common.vikunja_v2_factory import make_task

VALID_ISO = "2026-05-15T23:59:59-04:00"


def _fake_token_file(tmp_path):
    p = tmp_path / "vikunja-token"
    p.write_text("fake-token-for-tests\n")
    return p


def _task_body(task_id: int) -> bytes:
    return json.dumps(
        make_task(id=task_id, repeat={"freq": "weekly", "interval": 1, "by_day": ["we"]})
    ).encode("utf-8")


def _cm(body: bytes) -> MagicMock:
    mock = MagicMock()
    mock.__enter__ = MagicMock(return_value=MagicMock(read=MagicMock(
        return_value=body
    ), status=200))
    mock.__exit__ = MagicMock(return_value=False)
    return mock


def _task_server(fail_ids: frozenset[int] = frozenset()):
    """urlopen side effect: every v2 task call answers that task (with a
    rule); any call for an id in *fail_ids* raises HTTP 500."""

    def side_effect(req, timeout=15):
        task_id = int(req.full_url.rstrip("/").split("/")[-1])
        if task_id in fail_ids:
            raise _mock_http_error(500, "Internal Server Error")
        return _cm(_task_body(task_id))

    return side_effect


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
    with patch("urllib.request.urlopen", side_effect=_task_server()) as mock_urlopen:
        rc = sdd.main([
            "--habit-ids", "100,101,102",
            "--iso-eod-et", VALID_ISO,
            "--vikunja-token-path", str(token),
            "--vikunja-base-url", "http://test/api/v1",
        ])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out.splitlines()[0])
    assert payload["succeeded"] == [100, 101, 102]
    assert payload["failed"] == []
    assert "SUMMARY: total=3 succeeded=3 failed=0" in out
    # Per habit: GET, PATCH (due_date only), GET read-back. No v1 POST.
    reqs = [c[0][0] for c in mock_urlopen.call_args_list]
    assert [r.get_method() for r in reqs] == ["GET", "PATCH", "GET"] * 3
    assert all("/api/v2/tasks/" in r.full_url for r in reqs)
    patches = [json.loads(r.data.decode("utf-8")) for r in reqs if r.get_method() == "PATCH"]
    assert patches == [{"due_date": VALID_ISO}] * 3


def test_partial_failure_exit_1_with_succeeded_subset(tmp_path, capsys):
    """Partial failure: 2 succeed, 1 fails — must exit 1 AND retain succeeded subset."""
    token = _fake_token_file(tmp_path)
    with patch("urllib.request.urlopen", side_effect=_task_server(frozenset({101}))):
        rc = sdd.main([
            "--habit-ids", "100,101,102",
            "--iso-eod-et", VALID_ISO,
            "--vikunja-token-path", str(token),
            "--vikunja-base-url", "http://test/api/v1",
        ])
    out = capsys.readouterr().out
    assert rc == 1, f"partial-failure must exit 1; got {rc}"
    payload = json.loads(out.splitlines()[0])
    assert 100 in payload["succeeded"]  # first habit succeeded
    assert 102 in payload["succeeded"]  # third habit succeeded
    assert len(payload["failed"]) == 1
    assert payload["failed"][0]["id"] == 101
    assert "500" in payload["failed"][0]["reason"]


def test_all_fail_exit_1_empty_succeeded(tmp_path, capsys):
    token = _fake_token_file(tmp_path)
    with patch(
        "urllib.request.urlopen",
        side_effect=_mock_http_error(500, "Server Error"),
    ):
        rc = sdd.main([
            "--habit-ids", "100,101",
            "--iso-eod-et", VALID_ISO,
            "--vikunja-token-path", str(token),
            "--vikunja-base-url", "http://test/api/v1",
        ])
    out = capsys.readouterr().out
    assert rc == 1
    payload = json.loads(out.splitlines()[0])
    assert payload["succeeded"] == []
    assert len(payload["failed"]) == 2


def test_dry_run_makes_no_http_calls(tmp_path, capsys):
    """--dry-run MUST NOT call urllib.request.urlopen at all."""
    token = _fake_token_file(tmp_path)
    with patch("urllib.request.urlopen") as mock_urlopen:
        rc = sdd.main([
            "--habit-ids", "100,101",
            "--iso-eod-et", VALID_ISO,
            "--vikunja-token-path", str(token),
            "--vikunja-base-url", "http://test/api/v1",
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
    with patch("urllib.request.urlopen") as mock_urlopen:
        rc = sdd.main([
            "--habit-ids", "100",
            "--iso-eod-et", "2026-05-15T23:59:59Z",  # UTC Z suffix — must reject
            "--vikunja-token-path", str(token),
            "--vikunja-base-url", "http://test/api/v1",
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
        "--vikunja-base-url", "http://test/api/v1",
    ])
    captured = capsys.readouterr()
    assert rc == 2
    assert "ERROR" in captured.err


def test_idempotency_same_input_same_output(tmp_path, capsys):
    """Running the helper twice with same input produces same result.

    Real Vikunja due_date PATCHes are idempotent; this test verifies the helper itself
    introduces no non-determinism (e.g., timestamps, ordering).
    """
    token = _fake_token_file(tmp_path)
    with patch("urllib.request.urlopen", side_effect=_task_server()):
        rc1 = sdd.main([
            "--habit-ids", "100,101",
            "--iso-eod-et", VALID_ISO,
            "--vikunja-token-path", str(token),
            "--vikunja-base-url", "http://test/api/v1",
        ])
        out1 = capsys.readouterr().out
        rc2 = sdd.main([
            "--habit-ids", "100,101",
            "--iso-eod-et", VALID_ISO,
            "--vikunja-token-path", str(token),
            "--vikunja-base-url", "http://test/api/v1",
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
        "--vikunja-base-url", "http://test/api/v1",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out.splitlines()[0])
    assert payload["succeeded"] == []
    assert payload["failed"] == []


# ---------- --reconcile-schedule retired (#1111) ----------


def test_reconcile_schedule_flag_is_gone(capsys):
    """The retired mode is not accepted (argparse usage error)."""
    import pytest

    with pytest.raises(SystemExit) as exc:
        sdd.main(["--reconcile-schedule", "--dry-run"])
    assert exc.value.code == 2
    assert "--reconcile-schedule" in capsys.readouterr().err


def test_reconcile_helpers_removed():
    """No dead reconcile code survives (no-dead-code rule)."""
    for name in (
        "reconcile_schedule",
        "compute_next_eod_et_for_weekdays",
        "_run_reconcile_mode",
    ):
        assert not hasattr(sdd, name), name
    # The #112 guards stay: the sweeper imports them.
    assert hasattr(sdd, "validate_iso_eod_et")
    assert hasattr(sdd, "ISO_EOD_PATTERN")


# ---------- --iso-eod-et mode regression (moved from the reconcile file) ----------


def test_z_suffix_still_rejected_in_dry_run(tmp_token_file, capsys):
    exit_code = sdd.main([
        "--habit-ids", "15",
        "--iso-eod-et", "2026-05-22T23:59:59Z",
        "--vikunja-token-path", str(tmp_token_file),
        "--vikunja-base-url", "http://test/api/v1",
        "--dry-run",
    ])
    assert exit_code == 2
    assert "Z" in capsys.readouterr().err


def test_iso_eod_et_required(capsys):
    exit_code = sdd.main([
        "--habit-ids", "15",
        "--vikunja-base-url", "http://test/api/v1",
        "--dry-run",
    ])
    assert exit_code == 2
    assert "required" in capsys.readouterr().err


def test_rule_changed_by_write_is_a_failure(tmp_path, capsys):
    """A habit whose rule differs after the due_date write is reported failed."""
    token = _fake_token_file(tmp_path)
    stripped = json.dumps(make_task(id=100, repeat=None)).encode("utf-8")
    responses = iter([_cm(_task_body(100)), _cm(stripped), _cm(stripped)])
    with patch("urllib.request.urlopen", side_effect=lambda req, timeout=15: next(responses)):
        rc = sdd.main([
            "--habit-ids", "100",
            "--iso-eod-et", VALID_ISO,
            "--vikunja-token-path", str(token),
            "--vikunja-base-url", "http://test/api/v1",
        ])
    assert rc == 1
    payload = json.loads(capsys.readouterr().out.splitlines()[0])
    assert payload["failed"][0]["reason"].startswith("rule_changed")


# ---------- Invocation forms (moved from the reconcile file) ----------
# Both ``python3 -m scripts.habits.set_due_dates`` and the direct-script form
# ``python3 scripts/habits/set_due_dates.py`` must start cleanly: the
# try/except ImportError fallback makes ``scripts.common.*`` resolvable when
# only ``scripts/habits/`` is on sys.path.
# Precedent: scripts/openclaw/observation/summarize.py:36-38.


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "habits" / "set_due_dates.py"


def _run(argv: list[str]):
    import os
    import subprocess
    import sys

    # Drop pytest's PYTHONPATH so the direct-script form is really tested.
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    return subprocess.run(
        [sys.executable, *argv],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )


def test_module_form_help_exits_zero():
    result = _run(["-m", "scripts.habits.set_due_dates", "--help"])
    assert result.returncode == 0, f"module form failed: stderr={result.stderr!r}"
    assert "--iso-eod-et" in result.stdout
    assert "--reconcile-schedule" not in result.stdout


def test_direct_script_form_help_exits_zero():
    assert SCRIPT_PATH.exists()
    result = _run([str(SCRIPT_PATH), "--help"])
    assert result.returncode == 0, (
        f"direct-script form failed: stderr={result.stderr!r}"
    )
    assert "--iso-eod-et" in result.stdout


# ---------- recurrence_drift (review cycle 1, finding 2) ----------


def _with_reminders(task: dict, reminders: list[dict]) -> dict:
    return {**task, "reminders": reminders}


_REL = {"reminder": "2026-05-28T02:59:59Z", "relative_to": "due_date", "relative_period": -3600}
_ABS = {"reminder": "2026-05-27T12:00:00Z", "relative_to": "", "relative_period": 0}


def test_recurrence_drift_none_when_all_survive():
    before = _with_reminders(
        make_task(repeat={"freq": "weekly", "interval": 1, "by_day": ["we"]},
                  repeats_from_current_date=True),
        [_REL, _ABS],
    )
    assert sdd.recurrence_drift(before, json.loads(json.dumps(before))) == []


def test_recurrence_drift_accepts_recomputed_relative_reminder_across_dst():
    """The server recomputes a relative reminder's instant on every save in
    the saver's zone (d7e202228 updateRelativeReminderDates). A -1 day
    reminder saved in UTC at 00:00Z legitimately reads 01:00Z after a save
    under America/New_York across the 2027-03-14 DST change: not drift."""
    day = {"relative_to": "due_date", "relative_period": -86400}
    before = _with_reminders(
        make_task(due_date="2027-03-15T00:00:00Z"),
        [{**day, "reminder": "2027-03-14T00:00:00Z"}],
    )
    after = _with_reminders(before, [{**day, "reminder": "2027-03-14T01:00:00Z"}])
    assert sdd.recurrence_drift(before, after) == []


def test_recurrence_drift_detects_each_corruption():
    base = _with_reminders(
        make_task(repeat={"freq": "weekly", "interval": 1, "by_day": ["we"]},
                  repeats_from_current_date=True),
        [_REL, _ABS],
    )
    assert sdd.recurrence_drift(base, {**base, "repeat": None}) == ["repeat"]
    assert sdd.recurrence_drift(base, {**base, "repeats_from_current_date": False}) == [
        "repeats_from_current_date"
    ]
    assert sdd.recurrence_drift(base, _with_reminders(base, [_ABS])) == ["reminders"]
    assert sdd.recurrence_drift(base, _with_reminders(base, [])) == ["reminders"]
    moved_abs = {**_ABS, "reminder": "2026-05-27T13:00:00Z"}
    assert sdd.recurrence_drift(base, _with_reminders(base, [_REL, moved_abs])) == [
        "reminders"
    ]
    other_period = {**_REL, "relative_period": -7200}
    assert sdd.recurrence_drift(base, _with_reminders(base, [other_period, _ABS])) == [
        "reminders"
    ]
