"""Tests for the mission #408 --reconcile-schedule flag on set_due_dates.py.

Covers:
  * ``compute_next_eod_et_for_weekdays`` — pure date math (deterministic).
  * ``reconcile_schedule`` — idempotency, per-habit error resilience, the
    #112 regression-prevention guard on the computed ``new_due_date``, and
    the E5 reconciliation record's shape and atomic-write semantics.
  * The CLI surface — mutual exclusion with --iso-eod-et mode, exit codes,
    and pure preservation of the pre-#408 --iso-eod-et path (regression).
"""
from __future__ import annotations

import json
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# scripts/habits/ is on sys.path via tests/habits/conftest.py — both styles
# of import work, but we prefer the package-qualified one here because the
# reconcile path uses ``from scripts.habits.schedule_loader import ...``
# internally and any sys.path drift would manifest as an ImportError.
from scripts.habits import set_due_dates as sdd


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_schedule(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def _mock_ok_response(body: bytes = b"{}"):
    """Build a MagicMock urlopen response that returns the given JSON body."""
    mock = MagicMock(name="response")
    mock.__enter__ = MagicMock(return_value=MagicMock(
        read=MagicMock(return_value=body),
        status=200,
    ))
    mock.__exit__ = MagicMock(return_value=False)
    return mock


def _http_error(code: int, reason: str = "Server Error"):
    return urllib.error.HTTPError("url", code, reason, hdrs=None, fp=None)


SCHEDULE_WITH_FRIDAY = """
habits:
  - task_id: 14
    title: "Daily wake"
    repeat_after_seconds: 86400
  - task_id: 77
    title: "Friday strength"
    designated_weekdays: ["Fri"]
    repeat_after_seconds: 604800
"""


SCHEDULE_WITH_MULTI = """
habits:
  - task_id: 100
    title: "Mon+Thu"
    designated_weekdays: ["Mon", "Thu"]
    repeat_after_seconds: 302400
"""


# ---------------------------------------------------------------------------
# Group 1 — compute_next_eod_et_for_weekdays (pure math)
# ---------------------------------------------------------------------------


class TestComputeNextEodEt:
    def test_today_is_friday_returns_today(self):
        # 2026-05-22 is a Friday in ET.
        now = datetime(2026, 5, 22, 14, 0, 0, tzinfo=timezone.utc)
        result = sdd.compute_next_eod_et_for_weekdays(("Fri",), now_utc=now)
        assert result == "2026-05-22T23:59:59-04:00"

    def test_today_is_wednesday_targets_friday(self):
        # 2026-05-20 is Wed; next Fri is 2026-05-22.
        now = datetime(2026, 5, 20, 14, 0, 0, tzinfo=timezone.utc)
        result = sdd.compute_next_eod_et_for_weekdays(("Fri",), now_utc=now)
        assert result == "2026-05-22T23:59:59-04:00"

    def test_today_is_saturday_targets_next_friday(self):
        # 2026-05-23 is Sat; next Fri is 2026-05-29.
        now = datetime(2026, 5, 23, 14, 0, 0, tzinfo=timezone.utc)
        result = sdd.compute_next_eod_et_for_weekdays(("Fri",), now_utc=now)
        assert result == "2026-05-29T23:59:59-04:00"

    def test_multi_day_picks_earliest(self):
        # 2026-05-20 is Wed; "Mon,Thu" -> Thu (2026-05-21) is earlier than next Mon.
        now = datetime(2026, 5, 20, 14, 0, 0, tzinfo=timezone.utc)
        result = sdd.compute_next_eod_et_for_weekdays(
            ("Mon", "Thu"), now_utc=now
        )
        assert result == "2026-05-21T23:59:59-04:00"

    def test_est_winter_offset(self):
        # 2026-12-09 (Wed in winter — EST, -05:00). Next Fri = 2026-12-11.
        now = datetime(2026, 12, 9, 14, 0, 0, tzinfo=timezone.utc)
        result = sdd.compute_next_eod_et_for_weekdays(("Fri",), now_utc=now)
        assert result == "2026-12-11T23:59:59-05:00"

    def test_empty_designated_raises(self):
        now = datetime(2026, 5, 20, 14, 0, 0, tzinfo=timezone.utc)
        with pytest.raises(ValueError, match="at least one weekday"):
            sdd.compute_next_eod_et_for_weekdays((), now_utc=now)

    def test_unknown_weekday_raises(self):
        now = datetime(2026, 5, 20, 14, 0, 0, tzinfo=timezone.utc)
        with pytest.raises(ValueError, match="unknown weekday"):
            sdd.compute_next_eod_et_for_weekdays(("Xyz",), now_utc=now)

    def test_result_passes_iso_eod_validation(self):
        """Computed result MUST satisfy validate_iso_eod_et (the #112 guard)."""
        now = datetime(2026, 5, 20, 14, 0, 0, tzinfo=timezone.utc)
        result = sdd.compute_next_eod_et_for_weekdays(("Fri",), now_utc=now)
        assert sdd.validate_iso_eod_et(result) is None
        assert not result.endswith("Z")


# ---------------------------------------------------------------------------
# Group 2 — reconcile_schedule (API surface)
# ---------------------------------------------------------------------------


class TestReconcileSchedule:
    def test_advances_due_date_when_different(self, tmp_path):
        """Vikunja's current due_date differs from expected — issue PUT."""
        schedule = _write_schedule(
            tmp_path / "sched.yaml", SCHEDULE_WITH_FRIDAY
        )
        now = datetime(2026, 5, 20, 14, 0, 0, tzinfo=timezone.utc)  # Wed
        expected_new = "2026-05-22T23:59:59-04:00"
        old_due = "2026-05-15T23:59:59-04:00"

        get_resp = _mock_ok_response(
            json.dumps({"id": 77, "due_date": old_due}).encode("utf-8")
        )
        put_resp = _mock_ok_response(b"{}")

        with patch("urllib.request.urlopen") as mock_open:
            mock_open.side_effect = [get_resp, put_resp]
            result = sdd.reconcile_schedule(
                schedule_path=schedule,
                base_url="http://test/api/v1",
                token="t",
                reconcile_dir=tmp_path / "out",
                now_utc=now,
                dry_run=False,
            )

        assert len(result["reconciled"]) == 1
        assert result["reconciled"][0]["task_id"] == 77
        assert result["reconciled"][0]["old_due_date"] == old_due
        assert result["reconciled"][0]["new_due_date"] == expected_new
        assert result["skipped_no_change"] == []
        assert result["errors"] == []
        # Record file written.
        record_path = Path(result["record_path"])
        assert record_path.exists()
        record = json.loads(record_path.read_text(encoding="utf-8"))
        assert record["schema_version"] == 1
        assert record["dry_run"] is False
        assert len(record["habits_reconciled"]) == 1
        assert record["habits_reconciled"][0]["action"] == "advanced"

    def test_idempotent_no_op_when_already_correct(self, tmp_path):
        """Current due_date already matches expected — no PUT, no error."""
        schedule = _write_schedule(
            tmp_path / "sched.yaml", SCHEDULE_WITH_FRIDAY
        )
        now = datetime(2026, 5, 22, 14, 0, 0, tzinfo=timezone.utc)  # Fri
        expected_new = "2026-05-22T23:59:59-04:00"
        get_resp = _mock_ok_response(
            json.dumps({"id": 77, "due_date": expected_new}).encode("utf-8")
        )

        with patch("urllib.request.urlopen") as mock_open:
            mock_open.side_effect = [get_resp]  # Only GET, no PUT.
            result = sdd.reconcile_schedule(
                schedule_path=schedule,
                base_url="http://test/api/v1",
                token="t",
                reconcile_dir=tmp_path / "out",
                now_utc=now,
                dry_run=False,
            )

        assert result["reconciled"] == []
        assert result["skipped_no_change"] == [77]
        assert result["errors"] == []
        # No PUT was issued.
        assert mock_open.call_count == 1

    def test_per_habit_failure_continues_with_others(self, tmp_path):
        """A GET 500 on one habit is recorded but doesn't abort the run."""
        schedule = _write_schedule(
            tmp_path / "sched.yaml",
            """
habits:
  - task_id: 100
    title: "First"
    designated_weekdays: ["Wed"]
    repeat_after_seconds: 604800
  - task_id: 200
    title: "Second"
    designated_weekdays: ["Wed"]
    repeat_after_seconds: 604800
""",
        )
        now = datetime(2026, 5, 20, 14, 0, 0, tzinfo=timezone.utc)  # Wed

        # First: GET fails with HTTP 500. Second: GET ok, PUT ok.
        get_ok = _mock_ok_response(
            json.dumps({"id": 200, "due_date": "2026-05-13T23:59:59-04:00"})
            .encode("utf-8")
        )
        put_ok = _mock_ok_response(b"{}")

        with patch("urllib.request.urlopen") as mock_open:
            mock_open.side_effect = [_http_error(500), get_ok, put_ok]
            result = sdd.reconcile_schedule(
                schedule_path=schedule,
                base_url="http://test/api/v1",
                token="t",
                reconcile_dir=tmp_path / "out",
                now_utc=now,
                dry_run=False,
            )

        assert len(result["errors"]) == 1
        assert result["errors"][0]["task_id"] == 100
        assert result["errors"][0]["error_type"] == "vikunja_get"
        assert len(result["reconciled"]) == 1
        assert result["reconciled"][0]["task_id"] == 200

    def test_dry_run_makes_no_http_calls(self, tmp_path):
        schedule = _write_schedule(
            tmp_path / "sched.yaml", SCHEDULE_WITH_FRIDAY
        )
        now = datetime(2026, 5, 20, 14, 0, 0, tzinfo=timezone.utc)

        with patch("urllib.request.urlopen") as mock_open:
            mock_open.side_effect = AssertionError("dry-run must not call HTTP")
            result = sdd.reconcile_schedule(
                schedule_path=schedule,
                base_url="http://test/api/v1",
                token="",
                reconcile_dir=tmp_path / "out",
                now_utc=now,
                dry_run=True,
            )

        # Dry-run still produces a record entry per day-specific habit.
        assert len(result["reconciled"]) == 1
        assert result["reconciled"][0]["dry_run"] is True
        record = json.loads(Path(result["record_path"]).read_text())
        assert record["dry_run"] is True
        assert record["habits_reconciled"][0]["action"] == "would_advance"

    def test_record_includes_schedule_sha(self, tmp_path):
        schedule = _write_schedule(
            tmp_path / "sched.yaml", SCHEDULE_WITH_FRIDAY
        )
        now = datetime(2026, 5, 20, 14, 0, 0, tzinfo=timezone.utc)
        with patch("urllib.request.urlopen") as mock_open:
            mock_open.side_effect = AssertionError("no http in dry run")
            result = sdd.reconcile_schedule(
                schedule_path=schedule,
                base_url="http://test/api/v1",
                token="",
                reconcile_dir=tmp_path / "out",
                now_utc=now,
                dry_run=True,
            )
        # SHA is 64-hex-char SHA-256.
        assert len(result["schedule_sha256"]) == 64
        assert all(c in "0123456789abcdef" for c in result["schedule_sha256"])

    def test_schedule_load_error_propagates(self, tmp_path):
        schedule = _write_schedule(
            tmp_path / "sched.yaml",
            """
habits:
  - task_id: 1
    title: "Bad"
    designated_weekdays: ["Xyz"]
    repeat_after_seconds: 86400
""",
        )
        with pytest.raises(sdd.ScheduleConfigError):
            sdd.reconcile_schedule(
                schedule_path=schedule,
                base_url="http://test/",
                token="",
                reconcile_dir=tmp_path / "out",
                now_utc=datetime(2026, 5, 20, tzinfo=timezone.utc),
                dry_run=True,
            )

    def test_put_failure_recorded_as_error(self, tmp_path):
        """GET succeeds, PUT fails — error recorded, exit-1 signal preserved."""
        schedule = _write_schedule(
            tmp_path / "sched.yaml", SCHEDULE_WITH_FRIDAY
        )
        now = datetime(2026, 5, 20, 14, 0, 0, tzinfo=timezone.utc)
        get_ok = _mock_ok_response(
            json.dumps({"id": 77, "due_date": "2026-05-15T23:59:59-04:00"})
            .encode("utf-8")
        )
        with patch("urllib.request.urlopen") as mock_open:
            mock_open.side_effect = [get_ok, _http_error(500)]
            result = sdd.reconcile_schedule(
                schedule_path=schedule,
                base_url="http://test/api/v1",
                token="t",
                reconcile_dir=tmp_path / "out",
                now_utc=now,
                dry_run=False,
            )
        assert len(result["errors"]) == 1
        assert result["errors"][0]["error_type"] == "vikunja_put"

    def test_get_url_error_recorded(self, tmp_path):
        """A URLError on GET is captured as a per-habit error."""
        schedule = _write_schedule(
            tmp_path / "sched.yaml", SCHEDULE_WITH_FRIDAY
        )
        now = datetime(2026, 5, 20, 14, 0, 0, tzinfo=timezone.utc)
        with patch("urllib.request.urlopen") as mock_open:
            mock_open.side_effect = urllib.error.URLError("connection refused")
            result = sdd.reconcile_schedule(
                schedule_path=schedule,
                base_url="http://test/api/v1",
                token="t",
                reconcile_dir=tmp_path / "out",
                now_utc=now,
                dry_run=False,
            )
        assert len(result["errors"]) == 1
        assert result["errors"][0]["error_type"] == "vikunja_get"
        assert "connection refused" in result["errors"][0]["error_message"]

    def test_put_url_error_recorded(self, tmp_path):
        """A URLError on PUT is captured as a per-habit error."""
        schedule = _write_schedule(
            tmp_path / "sched.yaml", SCHEDULE_WITH_FRIDAY
        )
        now = datetime(2026, 5, 20, 14, 0, 0, tzinfo=timezone.utc)
        get_ok = _mock_ok_response(
            json.dumps({"id": 77, "due_date": "2026-05-15T23:59:59-04:00"})
            .encode("utf-8")
        )
        with patch("urllib.request.urlopen") as mock_open:
            mock_open.side_effect = [
                get_ok,
                urllib.error.URLError("network down"),
            ]
            result = sdd.reconcile_schedule(
                schedule_path=schedule,
                base_url="http://test/api/v1",
                token="t",
                reconcile_dir=tmp_path / "out",
                now_utc=now,
                dry_run=False,
            )
        assert len(result["errors"]) == 1
        assert result["errors"][0]["error_type"] == "vikunja_put"

    def test_get_returns_non_dict_treated_as_no_current(self, tmp_path):
        """If Vikunja returns a list or null, current_due stays None — still advances."""
        schedule = _write_schedule(
            tmp_path / "sched.yaml", SCHEDULE_WITH_FRIDAY
        )
        now = datetime(2026, 5, 20, 14, 0, 0, tzinfo=timezone.utc)
        # GET returns a list (unexpected shape) — _http_get returns it as-is.
        get_weird = _mock_ok_response(b"[]")
        put_ok = _mock_ok_response(b"{}")
        with patch("urllib.request.urlopen") as mock_open:
            mock_open.side_effect = [get_weird, put_ok]
            result = sdd.reconcile_schedule(
                schedule_path=schedule,
                base_url="http://test/api/v1",
                token="t",
                reconcile_dir=tmp_path / "out",
                now_utc=now,
                dry_run=False,
            )
        # current is None != expected_new -> advanced.
        assert len(result["reconciled"]) == 1
        assert result["reconciled"][0]["old_due_date"] is None

    def test_daily_entries_are_skipped(self, tmp_path):
        """Entries without designated_weekdays are not processed at all."""
        schedule = _write_schedule(
            tmp_path / "sched.yaml",
            """
habits:
  - task_id: 1
    title: "Daily wake"
    repeat_after_seconds: 86400
  - task_id: 2
    title: "Daily meditate"
    repeat_after_seconds: 86400
""",
        )
        with patch("urllib.request.urlopen") as mock_open:
            mock_open.side_effect = AssertionError("no day-specific entries — no http")
            result = sdd.reconcile_schedule(
                schedule_path=schedule,
                base_url="http://test/api/v1",
                token="t",
                reconcile_dir=tmp_path / "out",
                now_utc=datetime(2026, 5, 20, tzinfo=timezone.utc),
                dry_run=False,
            )
        assert result["reconciled"] == []
        assert result["skipped_no_change"] == []
        assert result["errors"] == []


# ---------------------------------------------------------------------------
# Group 3 — CLI surface
# ---------------------------------------------------------------------------


class TestReconcileCli:
    def test_reconcile_with_iso_eod_et_is_mutually_exclusive(
        self, tmp_path, capsys
    ):
        exit_code = sdd.main([
            "--reconcile-schedule",
            "--iso-eod-et", "2026-05-22T23:59:59-04:00",
            "--habit-ids", "15",
            "--reconcile-record-dir", str(tmp_path),
        ])
        assert exit_code == 2
        err = capsys.readouterr().err
        assert "mutually exclusive" in err

    def test_reconcile_success_returns_0(self, tmp_path, tmp_token_file):
        schedule = _write_schedule(
            tmp_path / "sched.yaml", SCHEDULE_WITH_FRIDAY
        )
        get_resp = _mock_ok_response(
            json.dumps({"id": 77, "due_date": "2026-05-15T23:59:59-04:00"})
            .encode("utf-8")
        )
        put_resp = _mock_ok_response(b"{}")
        with patch("urllib.request.urlopen") as mock_open:
            mock_open.side_effect = [get_resp, put_resp]
            # Patch datetime.now so the test is deterministic.
            with patch.object(sdd, "datetime") as mock_dt:
                mock_dt.now.return_value = datetime(
                    2026, 5, 20, 14, 0, 0, tzinfo=timezone.utc
                )
                # Pass-through the real datetime ctor for compute helpers.
                mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
                exit_code = sdd.main([
                    "--reconcile-schedule",
                    "--vikunja-token-path", str(tmp_token_file),
                    "--vikunja-base-url", "http://test/api/v1",
                    "--schedule-path", str(schedule),
                    "--reconcile-record-dir", str(tmp_path / "rec"),
                ])
        assert exit_code == 0

    def test_reconcile_per_habit_failure_returns_1(
        self, tmp_path, tmp_token_file
    ):
        schedule = _write_schedule(
            tmp_path / "sched.yaml", SCHEDULE_WITH_FRIDAY
        )
        with patch("urllib.request.urlopen") as mock_open:
            mock_open.side_effect = [_http_error(500)]
            with patch.object(sdd, "datetime") as mock_dt:
                mock_dt.now.return_value = datetime(
                    2026, 5, 20, 14, 0, 0, tzinfo=timezone.utc
                )
                mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
                exit_code = sdd.main([
                    "--reconcile-schedule",
                    "--vikunja-token-path", str(tmp_token_file),
                    "--vikunja-base-url", "http://test/api/v1",
                    "--schedule-path", str(schedule),
                    "--reconcile-record-dir", str(tmp_path / "rec"),
                ])
        assert exit_code == 1

    def test_reconcile_dry_run_no_token_required(self, tmp_path):
        """--dry-run skips token loading so the helper is usable pre-deploy."""
        schedule = _write_schedule(
            tmp_path / "sched.yaml", SCHEDULE_WITH_FRIDAY
        )
        with patch("urllib.request.urlopen") as mock_open:
            mock_open.side_effect = AssertionError("dry-run must not call HTTP")
            with patch.object(sdd, "datetime") as mock_dt:
                mock_dt.now.return_value = datetime(
                    2026, 5, 20, 14, 0, 0, tzinfo=timezone.utc
                )
                mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
                exit_code = sdd.main([
                    "--reconcile-schedule",
                    "--dry-run",
                    "--vikunja-token-path", "/does/not/exist",
                    "--schedule-path", str(schedule),
                    "--reconcile-record-dir", str(tmp_path / "rec"),
                ])
        assert exit_code == 0

    def test_reconcile_schedule_validation_returns_2(
        self, tmp_path, tmp_token_file, capsys
    ):
        bad_schedule = _write_schedule(
            tmp_path / "sched.yaml",
            """
habits:
  - task_id: 1
    title: "Bad"
    designated_weekdays: ["Xyz"]
    repeat_after_seconds: 86400
""",
        )
        with patch("urllib.request.urlopen") as mock_open:
            mock_open.side_effect = AssertionError("never reached")
            exit_code = sdd.main([
                "--reconcile-schedule",
                "--dry-run",
                "--schedule-path", str(bad_schedule),
                "--reconcile-record-dir", str(tmp_path / "rec"),
            ])
        assert exit_code == 2
        assert "schedule config" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Group 4 — Regression: --iso-eod-et mode preserved exactly
# ---------------------------------------------------------------------------


class TestIsoEodModeRegression:
    """NFR-003: pre-#408 --iso-eod-et behavior MUST be unchanged."""

    def test_z_suffix_still_rejected(self, tmp_path, tmp_token_file, capsys):
        exit_code = sdd.main([
            "--habit-ids", "15",
            "--iso-eod-et", "2026-05-22T23:59:59Z",
            "--vikunja-token-path", str(tmp_token_file),
            "--dry-run",
        ])
        assert exit_code == 2
        assert "Z" in capsys.readouterr().err

    def test_dry_run_still_works(self, tmp_path, tmp_token_file, capsys):
        exit_code = sdd.main([
            "--habit-ids", "15",
            "--iso-eod-et", "2026-05-22T23:59:59-04:00",
            "--vikunja-token-path", str(tmp_token_file),
            "--dry-run",
        ])
        assert exit_code == 0
        out = capsys.readouterr()
        assert '"succeeded": [15]' in out.out
        assert "SUMMARY: total=1 succeeded=1" in out.out

    def test_iso_eod_et_required_without_reconcile(self, tmp_path, capsys):
        exit_code = sdd.main([
            "--habit-ids", "15",
            "--dry-run",
        ])
        assert exit_code == 2
        assert "required" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Subprocess invocation regression — both module form and direct-script form
# must succeed so that production callers and the documented docstring
# invocation example continue to work after the schedule_loader import was
# added in this WP. The bug fixed by the try/except ImportError fallback in
# scripts/habits/set_due_dates.py: a top-level ``from scripts.habits.X import
# ...`` resolves only under ``python3 -m scripts.habits.set_due_dates`` (the
# package is on sys.path); under ``python3 scripts/habits/set_due_dates.py``
# only ``scripts/habits/`` itself is on sys.path, so ``scripts.habits.X``
# cannot be resolved and the script crashes BEFORE argparse runs (i.e. even
# ``--help`` exits non-zero). Precedent for the fix:
# scripts/openclaw/observation/summarize.py:36-38.
# ---------------------------------------------------------------------------


class TestInvocationFormCompatibility:
    """Verify both ``python3 -m scripts.habits.set_due_dates`` and
    ``python3 scripts/habits/set_due_dates.py`` produce a clean ``--help``
    response. These are the two documented invocation forms in production.
    """

    REPO_ROOT = Path(__file__).resolve().parents[2]
    SCRIPT_PATH = REPO_ROOT / "scripts" / "habits" / "set_due_dates.py"

    def _run(self, argv: list[str], extra_env: dict[str, str] | None = None):
        import os as _os
        import subprocess
        import sys as _sys

        # Rebuild env from scratch to avoid leaking pytest's PYTHONPATH,
        # which would mask the regression by making ``scripts.habits.*``
        # resolvable in the direct-script invocation.
        env = {k: v for k, v in _os.environ.items() if k != "PYTHONPATH"}
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [_sys.executable, *argv],
            cwd=str(self.REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
        )

    def test_module_form_help_exits_zero(self):
        """``python3 -m scripts.habits.set_due_dates --help`` succeeds."""
        # ``-m`` requires the repo root on sys.path so ``scripts.habits``
        # resolves as a package; CWD=repo-root achieves that implicitly via
        # Python's default sys.path[0] behaviour.
        result = self._run(["-m", "scripts.habits.set_due_dates", "--help"])
        assert result.returncode == 0, (
            f"module form failed: stderr={result.stderr!r}"
        )
        assert "set_due_dates" in result.stdout
        assert "--reconcile-schedule" in result.stdout

    def test_direct_script_form_help_exits_zero(self):
        """``python3 scripts/habits/set_due_dates.py --help`` succeeds.

        This is the regression guard for the codex review finding: without
        the try/except ImportError fallback in set_due_dates.py, the
        top-level ``from scripts.habits.schedule_loader import ...`` crashes
        with ``ModuleNotFoundError: No module named 'scripts'`` before
        argparse parses ``--help``.
        """
        assert self.SCRIPT_PATH.exists(), (
            f"set_due_dates.py not found at {self.SCRIPT_PATH}"
        )
        result = self._run([str(self.SCRIPT_PATH), "--help"])
        assert result.returncode == 0, (
            "direct-script form failed — the try/except ImportError fallback "
            f"is missing or broken. stderr={result.stderr!r}"
        )
        assert "set_due_dates" in result.stdout
        assert "--reconcile-schedule" in result.stdout
