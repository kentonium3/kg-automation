"""Unit tests for ``scripts/habits/sweeper.py`` (mission #408 / WP-02 / T013).

Covers:
  * ``find_expired_checkins`` discovery filter
  * ``evaluate_habit_resolution`` resolution semantics
  * ``run_sweep`` end-to-end: empty / unresolved / completed-in-window /
    skipped-in-window / already-auto-skipped / dry-run / per-habit failure
  * Issue #112 regression-prevention: computed due_dates use explicit ET
    offset (not ``Z``) — asserted via regex.
"""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Importing via the package path exercises the same path the sweeper uses
# in production (``python3 -m scripts.habits.sweeper``).
from scripts.habits import sweeper


# ---------------------------------------------------------------------------
# Constants — keep aligned with the WP01 schedule YAML's day-specific entries
# (task_ids 75/76/77 for Mon/Wed/Fri strength training).
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SCHEDULE_YAML = """\
habits:
  - task_id: 14
    title: "Wake at 5:00 AM"
    repeat_after_seconds: 86400
  - task_id: 15
    title: "Meditate"
    repeat_after_seconds: 86400
  - task_id: 16
    title: "Morning shoulder PT"
    repeat_after_seconds: 86400
  - task_id: 18
    title: "Get steps in today"
    repeat_after_seconds: 86400
  - task_id: 19
    title: "Read 30 min minimum"
    repeat_after_seconds: 86400
  - task_id: 20
    title: "Evening shoulder PT"
    repeat_after_seconds: 86400
  - task_id: 65
    title: "Morning hip PT"
    repeat_after_seconds: 86400
  - task_id: 76
    title: "Strength training — Wednesday"
    designated_weekdays: ["Wed"]
    repeat_after_seconds: 604800
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_schedule(tmp_path: Path) -> Path:
    schedule = tmp_path / "schedule.yaml"
    schedule.write_text(SCHEDULE_YAML, encoding="utf-8")
    return schedule


def _write_checkin(
    state_dir: Path,
    date: str,
    delivered_at_utc: str,
    habits: list[dict],
) -> Path:
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / f"morning-checkin-{date}.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "date": date,
                "generated_at": delivered_at_utc,
                "delivered_at_utc": delivered_at_utc,
                "habits": habits,
            }
        ),
        encoding="utf-8",
    )
    return path


def _write_history(history_path: Path, records: list[dict]) -> None:
    history_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps(rec, ensure_ascii=False, sort_keys=False) for rec in records
    ]
    history_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _ok_response():
    """Build a MagicMock urlopen response that satisfies the context-manager API."""
    mock = MagicMock(name="response")
    mock.__enter__ = MagicMock(
        return_value=MagicMock(
            read=MagicMock(return_value=b"{}"),
            status=200,
        )
    )
    mock.__exit__ = MagicMock(return_value=False)
    return mock


# ---------------------------------------------------------------------------
# find_expired_checkins
# ---------------------------------------------------------------------------


class TestFindExpiredCheckins:
    def test_empty_state_dir_returns_empty(self, tmp_path):
        result = sweeper.find_expired_checkins(
            tmp_path / "nonexistent",
            datetime(2026, 6, 2, 11, 30, tzinfo=timezone.utc),
        )
        assert result == []

    def test_checkin_younger_than_48hr_is_excluded(self, tmp_path):
        state_dir = tmp_path / "state"
        # Now: 2026-06-02 11:30 UTC. Checkin: 2026-06-01 11:05 UTC = 24hr ago.
        _write_checkin(
            state_dir,
            "2026-06-01",
            "2026-06-01T11:05:00Z",
            [{"vikunja_task_id": 14, "title": "Wake"}],
        )
        result = sweeper.find_expired_checkins(
            state_dir, datetime(2026, 6, 2, 11, 30, tzinfo=timezone.utc)
        )
        assert result == []

    def test_checkin_older_than_48hr_is_eligible(self, tmp_path):
        state_dir = tmp_path / "state"
        _write_checkin(
            state_dir,
            "2026-05-30",
            "2026-05-30T11:05:00Z",
            [{"vikunja_task_id": 14, "title": "Wake"}],
        )
        result = sweeper.find_expired_checkins(
            state_dir, datetime(2026, 6, 2, 11, 30, tzinfo=timezone.utc)
        )
        assert len(result) == 1
        assert result[0].checkin_date_et == "2026-05-30"

    def test_checkin_older_than_7_days_is_excluded(self, tmp_path):
        state_dir = tmp_path / "state"
        _write_checkin(
            state_dir,
            "2026-05-20",
            "2026-05-20T11:05:00Z",
            [{"vikunja_task_id": 14, "title": "Wake"}],
        )
        result = sweeper.find_expired_checkins(
            state_dir, datetime(2026, 6, 2, 11, 30, tzinfo=timezone.utc)
        )
        assert result == []

    def test_malformed_artifact_skipped_silently(self, tmp_path):
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)
        (state_dir / "morning-checkin-2026-05-30.json").write_text(
            "not json", encoding="utf-8"
        )
        result = sweeper.find_expired_checkins(
            state_dir, datetime(2026, 6, 2, tzinfo=timezone.utc)
        )
        assert result == []

    def test_non_matching_filenames_ignored(self, tmp_path):
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)
        (state_dir / "sweeper-tick-2026-05-30.json").write_text(
            json.dumps({"delivered_at_utc": "2026-05-30T11:05:00Z", "habits": []}),
            encoding="utf-8",
        )
        result = sweeper.find_expired_checkins(
            state_dir, datetime(2026, 6, 2, tzinfo=timezone.utc)
        )
        assert result == []

    def test_fallback_to_generated_at_when_delivered_missing(self, tmp_path):
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)
        (state_dir / "morning-checkin-2026-05-30.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "date": "2026-05-30",
                    "generated_at": "2026-05-30T11:05:00Z",
                    "habits": [{"vikunja_task_id": 14, "title": "Wake"}],
                }
            ),
            encoding="utf-8",
        )
        result = sweeper.find_expired_checkins(
            state_dir, datetime(2026, 6, 2, tzinfo=timezone.utc)
        )
        assert len(result) == 1
        assert result[0].checkin_date_et == "2026-05-30"


# ---------------------------------------------------------------------------
# evaluate_habit_resolution
# ---------------------------------------------------------------------------


class TestEvaluateHabitResolution:
    def test_returns_unresolved_when_no_history(self):
        assert (
            sweeper.evaluate_habit_resolution([], 14, "2026-05-30")
            == "unresolved"
        )

    def test_returns_completed_in_window(self):
        history = [
            {
                "domain": "habits",
                "task_id": 14,
                "date": "2026-05-30",
                "state": "complete",
            }
        ]
        assert (
            sweeper.evaluate_habit_resolution(history, 14, "2026-05-30")
            == "completed_in_window"
        )

    def test_returns_skipped_in_window(self):
        history = [
            {
                "domain": "habits",
                "task_id": 14,
                "date": "2026-05-30",
                "state": "skipped",
            }
        ]
        assert (
            sweeper.evaluate_habit_resolution(history, 14, "2026-05-30")
            == "skipped_in_window"
        )

    def test_returns_already_auto_skipped(self):
        history = [
            {
                "event_type": "auto_skipped",
                "task_id": 14,
                "original_checkin_date_et": "2026-05-30",
            }
        ]
        assert (
            sweeper.evaluate_habit_resolution(history, 14, "2026-05-30")
            == "already_auto_skipped"
        )

    def test_auto_skip_takes_priority_over_state_records(self):
        """Defensive: if BOTH a state record AND an auto_skipped event exist,
        report ``already_auto_skipped`` so we don't accidentally re-mark."""
        history = [
            {
                "domain": "habits",
                "task_id": 14,
                "date": "2026-05-30",
                "state": "complete",
            },
            {
                "event_type": "auto_skipped",
                "task_id": 14,
                "original_checkin_date_et": "2026-05-30",
            },
        ]
        assert (
            sweeper.evaluate_habit_resolution(history, 14, "2026-05-30")
            == "already_auto_skipped"
        )

    def test_non_matching_task_id_returns_unresolved(self):
        history = [
            {
                "domain": "habits",
                "task_id": 99,
                "date": "2026-05-30",
                "state": "complete",
            }
        ]
        assert (
            sweeper.evaluate_habit_resolution(history, 14, "2026-05-30")
            == "unresolved"
        )


# ---------------------------------------------------------------------------
# run_sweep — end-to-end
# ---------------------------------------------------------------------------


class TestRunSweepHappyPath:
    def _common_args(self, tmp_path):
        return {
            "schedule_path": _write_schedule(tmp_path),
            "state_dir": tmp_path / "state",
            "history_path": tmp_path / "history.jsonl",
            "vikunja_token_path": tmp_path / "token",
            "vikunja_base_url": "https://example.invalid/api/v1",
            "now_utc": datetime(2026, 6, 2, 11, 30, tzinfo=timezone.utc),
        }

    def test_empty_state_dir_clean_tick(self, tmp_path):
        args = self._common_args(tmp_path)
        tick = sweeper.run_sweep(**args)
        assert tick.exit_status == "success"
        assert tick.habits_evaluated == []
        assert tick.habits_auto_skipped == []
        assert tick.errors == []

    def test_unresolved_daily_habit_auto_skipped_no_vikunja_call(self, tmp_path):
        """Unresolved daily habit auto-skipped; NO Vikunja PUT (daily habits
        inherit their next instance from Vikunja's native repeat cadence)."""
        args = self._common_args(tmp_path)
        # Checkin from 2026-05-30 (>48hr ago vs now=2026-06-02 11:30 UTC).
        _write_checkin(
            args["state_dir"],
            "2026-05-30",
            "2026-05-30T11:05:00Z",
            [{"vikunja_task_id": 14, "title": "Wake at 5:00 AM"}],
        )
        with patch("urllib.request.urlopen") as mock_urlopen:
            tick = sweeper.run_sweep(**args)
        assert tick.exit_status == "success"
        assert len(tick.habits_auto_skipped) == 1
        assert tick.habits_auto_skipped[0].task_id == 14
        assert tick.habits_auto_skipped[0].new_due_date_et is None
        # Daily habit — no Vikunja PUT.
        assert mock_urlopen.call_count == 0
        # History event appended.
        body = args["history_path"].read_text(encoding="utf-8").strip()
        assert body, "expected history event written"
        event = json.loads(body)
        assert event["event_type"] == "auto_skipped"
        assert event["task_id"] == 14
        assert event["original_designated_weekday"] is None

    def test_unresolved_dayspecific_habit_auto_skipped_and_vikunja_put(
        self, tmp_path
    ):
        """Day-specific habit auto-skipped triggers Vikunja PUT with explicit
        ET offset. Asserts the #112 regression-prevention guard."""
        args = self._common_args(tmp_path)
        args["vikunja_token_path"].write_text("token-xxx\n", encoding="utf-8")
        # Wednesday 2026-05-27 checkin, evaluating from 2026-06-02 (Tue).
        _write_checkin(
            args["state_dir"],
            "2026-05-27",
            "2026-05-27T11:05:00Z",
            [
                {
                    "vikunja_task_id": 76,
                    "title": "Strength training — Wednesday",
                    "designated_weekdays": ["Wed"],
                }
            ],
        )
        with patch("urllib.request.urlopen", return_value=_ok_response()) as mock_urlopen:
            tick = sweeper.run_sweep(**args)
        assert tick.exit_status == "success"
        assert len(tick.habits_auto_skipped) == 1
        rec = tick.habits_auto_skipped[0]
        assert rec.task_id == 76
        assert rec.original_designated_weekday == "Wed"
        # #112 regression-prevention guard: explicit ET offset, NOT Z.
        assert rec.new_due_date_et is not None
        assert not rec.new_due_date_et.endswith("Z")
        assert re.match(
            r"^\d{4}-\d{2}-\d{2}T23:59:59[+-]\d{2}:\d{2}$",
            rec.new_due_date_et,
        ), f"new_due_date_et {rec.new_due_date_et!r} not in expected ET format"
        # Vikunja PUT was called exactly once.
        assert mock_urlopen.call_count == 1

    def test_completed_in_window_not_auto_skipped(self, tmp_path):
        args = self._common_args(tmp_path)
        _write_checkin(
            args["state_dir"],
            "2026-05-30",
            "2026-05-30T11:05:00Z",
            [{"vikunja_task_id": 14, "title": "Wake at 5:00 AM"}],
        )
        _write_history(
            args["history_path"],
            [
                {
                    "domain": "habits",
                    "task_id": 14,
                    "title": "Wake",
                    "date": "2026-05-30",
                    "state": "complete",
                    "source": "whatsapp",
                    "timestamp": "2026-05-30T12:30:00+00:00",
                }
            ],
        )
        tick = sweeper.run_sweep(**args)
        assert tick.exit_status == "success"
        assert tick.habits_auto_skipped == []
        assert len(tick.habits_evaluated) == 1
        assert tick.habits_evaluated[0].status == "completed_in_window"

    def test_skipped_in_window_not_auto_skipped(self, tmp_path):
        args = self._common_args(tmp_path)
        _write_checkin(
            args["state_dir"],
            "2026-05-30",
            "2026-05-30T11:05:00Z",
            [{"vikunja_task_id": 14, "title": "Wake at 5:00 AM"}],
        )
        _write_history(
            args["history_path"],
            [
                {
                    "domain": "habits",
                    "task_id": 14,
                    "title": "Wake",
                    "date": "2026-05-30",
                    "state": "skipped",
                    "source": "whatsapp",
                    "timestamp": "2026-05-30T12:30:00+00:00",
                }
            ],
        )
        tick = sweeper.run_sweep(**args)
        assert tick.exit_status == "success"
        assert tick.habits_auto_skipped == []
        assert tick.habits_evaluated[0].status == "skipped_in_window"

    def test_dry_run_no_history_no_vikunja_but_tick_recorded(self, tmp_path):
        args = self._common_args(tmp_path)
        _write_checkin(
            args["state_dir"],
            "2026-05-30",
            "2026-05-30T11:05:00Z",
            [{"vikunja_task_id": 14, "title": "Wake at 5:00 AM"}],
        )
        with patch("urllib.request.urlopen") as mock_urlopen:
            tick = sweeper.run_sweep(dry_run=True, **args)
        assert tick.dry_run is True
        # Tick still records the auto-skip intent.
        assert len(tick.habits_auto_skipped) == 1
        # But no history append + no Vikunja PUT.
        assert not args["history_path"].exists()
        assert mock_urlopen.call_count == 0

    def test_per_habit_failure_yields_partial_status(self, tmp_path):
        """Mocked Vikunja PUT raises; other habits still process."""
        args = self._common_args(tmp_path)
        args["vikunja_token_path"].write_text("token-xxx\n", encoding="utf-8")
        _write_checkin(
            args["state_dir"],
            "2026-05-27",
            "2026-05-27T11:05:00Z",
            [
                {
                    "vikunja_task_id": 76,
                    "title": "Strength training — Wednesday",
                    "designated_weekdays": ["Wed"],
                },
                {"vikunja_task_id": 14, "title": "Wake at 5:00 AM"},
            ],
        )

        import urllib.error

        def side_effect(req, timeout=15):
            # Fail PUT for task 76; daily habits don't call urlopen at all.
            raise urllib.error.HTTPError(
                "url", 500, "Server Error", hdrs=None, fp=None
            )

        with patch("urllib.request.urlopen", side_effect=side_effect):
            tick = sweeper.run_sweep(**args)
        assert tick.exit_status == "partial"
        # Daily habit (14) was still auto-skipped.
        ids = [r.task_id for r in tick.habits_auto_skipped]
        assert 14 in ids
        # Day-specific (76) errored and NOT marked auto-skipped.
        assert 76 not in ids
        # Error captured.
        assert any(e.error_type == "vikunja_put" for e in tick.errors)


class TestRunSweepIso112Regression:
    def test_compute_next_designated_weekday_explicit_offset(self):
        """compute_next_eod_et_for_weekdays (re-used by the sweeper) always
        produces an explicit-offset string. Regression: #112 forbids Z."""
        now = datetime(2026, 6, 2, 11, 30, tzinfo=timezone.utc)
        result = sweeper.compute_next_eod_et_for_weekdays(("Wed",), now_utc=now)
        assert not result.endswith("Z")
        assert re.match(
            r"^\d{4}-\d{2}-\d{2}T23:59:59[+-]\d{2}:\d{2}$",
            result,
        ), f"computed {result!r} does not match expected ET format"

    def test_iso_eod_pattern_rejects_z_suffix(self):
        """The shared ISO_EOD_PATTERN regex from set_due_dates is re-used by
        the sweeper for #112 guard validation. Belt-and-suspenders check."""
        assert sweeper.ISO_EOD_PATTERN.match("2026-06-10T23:59:59-04:00")
        assert not sweeper.ISO_EOD_PATTERN.match("2026-06-10T23:59:59Z")


class TestRunSweepWriteHelpers:
    def test_write_tick_artifact_creates_dated_file(self, tmp_path):
        state_dir = tmp_path / "state"
        tick = sweeper.SweeperTickRecord(
            tick_id="01TEST",
            started_at_utc="2026-06-02T11:30:00Z",
            duration_ms=123,
        )
        path = sweeper.write_tick_artifact(state_dir, tick)
        # Filename derived from ET date of started_at_utc. 2026-06-02 11:30 UTC
        # in ET is 2026-06-02 07:30 EDT.
        assert path.name == "sweeper-tick-2026-06-02.json"
        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded["tick_id"] == "01TEST"
        assert loaded["duration_ms"] == 123

    def test_write_tick_artifact_also_writes_stable_latest_pointer(self, tmp_path):
        # The canary freshness probe reads a STATIC path (no date substitution),
        # so the sweeper writes an overwrite-each-run sweeper-tick-latest.json
        # alongside the dated artifact (#720). Same payload; started_at_utc is
        # the canary-recognized timestamp key.
        state_dir = tmp_path / "state"
        tick = sweeper.SweeperTickRecord(
            tick_id="01TEST",
            started_at_utc="2026-06-02T11:30:00Z",
            duration_ms=123,
        )
        sweeper.write_tick_artifact(state_dir, tick)
        latest = state_dir / "sweeper-tick-latest.json"
        assert latest.exists()
        loaded = json.loads(latest.read_text(encoding="utf-8"))
        assert loaded["started_at_utc"] == "2026-06-02T11:30:00Z"
        assert loaded["exit_status"] == "success"
        # Latest mirrors the dated artifact exactly.
        assert loaded == json.loads(
            (state_dir / "sweeper-tick-2026-06-02.json").read_text(encoding="utf-8")
        )

    def test_write_tick_artifact_latest_overwrites_across_runs(self, tmp_path):
        # A later tick overwrites the stable pointer (never appends/rotates it).
        state_dir = tmp_path / "state"
        sweeper.write_tick_artifact(
            state_dir,
            sweeper.SweeperTickRecord(tick_id="01OLD", started_at_utc="2026-06-02T11:30:00Z"),
        )
        sweeper.write_tick_artifact(
            state_dir,
            sweeper.SweeperTickRecord(tick_id="01NEW", started_at_utc="2026-06-03T11:30:00Z"),
        )
        latest = json.loads(
            (state_dir / "sweeper-tick-latest.json").read_text(encoding="utf-8")
        )
        assert latest["tick_id"] == "01NEW"

    def test_append_ledger_appends_one_line_per_tick(self, tmp_path):
        state_dir = tmp_path / "state"
        tick = sweeper.SweeperTickRecord(
            tick_id="01TEST",
            started_at_utc="2026-06-02T11:30:00Z",
        )
        sweeper.append_ledger(state_dir, tick)
        sweeper.append_ledger(state_dir, tick)
        ledger = state_dir / "sweeper-ledger.jsonl"
        assert ledger.exists()
        lines = ledger.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2


class TestRunSweepCli:
    """End-to-end CLI smoke against tmp dirs — no real Vikunja, no real schedule."""

    def test_help_exits_zero(self, capsys):
        with pytest.raises(SystemExit) as exc:
            sweeper.main(["--help"])
        assert exc.value.code == 0
        captured = capsys.readouterr()
        assert "Daily 48hr auto-skip sweeper" in captured.out

    def test_dry_run_writes_tick_artifact(self, tmp_path, capsys):
        schedule = _write_schedule(tmp_path)
        state_dir = tmp_path / "state"
        # Empty state dir — tick is a clean no-op success.
        argv = [
            "--dry-run",
            "--schedule-path",
            str(schedule),
            "--state-dir",
            str(state_dir),
            "--history-path",
            str(tmp_path / "history.jsonl"),
            "--vikunja-token-path",
            str(tmp_path / "token"),
            "--now-utc",
            "2026-06-02T11:30:00Z",
        ]
        rc = sweeper.main(argv)
        assert rc == 0
        captured = capsys.readouterr()
        assert "SUMMARY:" in captured.out
        # Tick artifact written: exactly one dated artifact, plus the stable
        # sweeper-tick-latest.json freshness pointer (#720).
        dated = [
            p for p in state_dir.glob("sweeper-tick-*.json")
            if p.name != "sweeper-tick-latest.json"
        ]
        assert len(dated) == 1
        assert (state_dir / "sweeper-tick-latest.json").exists()

    def test_invalid_now_utc_returns_3(self, capsys):
        rc = sweeper.main(["--now-utc", "not-a-date"])
        assert rc == 3
        err = capsys.readouterr().err
        assert "--now-utc invalid" in err


# ---------------------------------------------------------------------------
# Extra coverage — defensive branches + helpers
# ---------------------------------------------------------------------------


class TestDataClassesAndHelpers:
    def test_auto_skip_record_with_new_due_date_serialization(self):
        rec = sweeper.AutoSkipRecord(
            task_id=76,
            original_checkin_date_et="2026-05-27",
            original_designated_weekday="Wed",
            new_due_date_et="2026-06-03T23:59:59-04:00",
        )
        d = rec.to_dict()
        assert d["new_due_date_et"] == "2026-06-03T23:59:59-04:00"

    def test_auto_skip_record_omits_new_due_date_for_daily(self):
        rec = sweeper.AutoSkipRecord(
            task_id=14,
            original_checkin_date_et="2026-05-27",
            original_designated_weekday=None,
            new_due_date_et=None,
        )
        d = rec.to_dict()
        assert "new_due_date_et" not in d

    def test_new_tick_id_format(self):
        tid = sweeper.new_tick_id()
        assert isinstance(tid, str)
        assert len(tid) == 26

    def test_print_summary_line(self, capsys):
        tick = sweeper.SweeperTickRecord(
            tick_id="01TEST",
            started_at_utc="2026-06-02T11:30:00Z",
        )
        sweeper.print_summary_line(tick)
        out = capsys.readouterr().out
        assert "SUMMARY:" in out
        assert "status=success" in out
        assert "dry_run=false" in out

    def test_read_history_returns_empty_on_missing_file(self, tmp_path):
        result = sweeper._read_history(tmp_path / "nope.jsonl")
        assert result == []

    def test_read_history_skips_malformed_lines(self, tmp_path):
        p = tmp_path / "history.jsonl"
        p.write_text(
            'not json\n{"valid": true}\n[]\n{"another": "valid"}\n',
            encoding="utf-8",
        )
        result = sweeper._read_history(p)
        # Two valid dict lines kept ([] is not a dict, "not json" is malformed).
        assert len(result) == 2
        assert {"valid": True} in result
        assert {"another": "valid"} in result

    def test_parse_delivered_at_accepts_z_and_offset(self):
        z = sweeper._parse_delivered_at("2026-06-02T11:30:00Z")
        off = sweeper._parse_delivered_at("2026-06-02T07:30:00-04:00")
        # Both represent the same UTC moment.
        assert z == off

    def test_parse_delivered_at_rejects_garbage(self):
        with pytest.raises(ValueError):
            sweeper._parse_delivered_at("not-a-timestamp")


class TestRunSweepFailureModes:
    def test_invalid_schedule_yields_failure_status(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("habits:\n  - task_id: not-an-int\n    title: x\n", encoding="utf-8")
        tick = sweeper.run_sweep(
            schedule_path=bad,
            state_dir=tmp_path / "state",
            history_path=tmp_path / "history.jsonl",
            vikunja_token_path=tmp_path / "token",
            vikunja_base_url="https://example.invalid/api/v1",
            now_utc=datetime(2026, 6, 2, 11, 30, tzinfo=timezone.utc),
        )
        assert tick.exit_status == "failure"
        assert any(e.error_type == "schedule_load" for e in tick.errors)

    def test_malformed_habit_entry_logged_and_skipped(self, tmp_path):
        args = {
            "schedule_path": _write_schedule(tmp_path),
            "state_dir": tmp_path / "state",
            "history_path": tmp_path / "history.jsonl",
            "vikunja_token_path": tmp_path / "token",
            "vikunja_base_url": "https://example.invalid/api/v1",
            "now_utc": datetime(2026, 6, 2, 11, 30, tzinfo=timezone.utc),
        }
        _write_checkin(
            args["state_dir"],
            "2026-05-30",
            "2026-05-30T11:05:00Z",
            [
                {"title": "no vikunja_task_id here"},  # malformed
                {"vikunja_task_id": 14, "title": "Wake at 5:00 AM"},
            ],
        )
        tick = sweeper.run_sweep(**args)
        # Malformed habit produces an error; valid habit still auto-skipped.
        assert any(
            e.error_type == "malformed_checkin_habit" for e in tick.errors
        )
        assert any(r.task_id == 14 for r in tick.habits_auto_skipped)
        assert tick.exit_status == "partial"


class TestFindExpiredCheckinsAdditional:
    def test_artifact_with_unparseable_delivered_at_skipped(self, tmp_path):
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)
        (state_dir / "morning-checkin-2026-05-30.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "date": "2026-05-30",
                    "delivered_at_utc": "garbage",
                    "habits": [{"vikunja_task_id": 14, "title": "Wake"}],
                }
            ),
            encoding="utf-8",
        )
        result = sweeper.find_expired_checkins(
            state_dir, datetime(2026, 6, 2, tzinfo=timezone.utc)
        )
        assert result == []

    def test_artifact_with_non_dict_root_skipped(self, tmp_path):
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)
        (state_dir / "morning-checkin-2026-05-30.json").write_text(
            "[]", encoding="utf-8"
        )
        result = sweeper.find_expired_checkins(
            state_dir, datetime(2026, 6, 2, tzinfo=timezone.utc)
        )
        assert result == []
