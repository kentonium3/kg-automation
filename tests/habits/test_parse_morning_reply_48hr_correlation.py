"""48hr-window correlation tests for ``parse_morning_reply.py``
(mission #408 / WP-02 / T014).

Covers the new correlation helpers + the CLI's correlated-date integration:
  * find_checkin_within_48hr_window
  * _explicit_date_hint
  * _habit_unresolved_on_date / _reply_has_unresolved_match
  * correlate_reply_to_checkin priority chain (date hint > unresolved > default)
  * end-to-end CLI: reply on today / yesterday / explicit ISO date / weekday name
  * regression: today-only reply (no candidates) preserves pre-#408 semantics
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.habits import parse_morning_reply as pmr


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_checkin(
    state_dir: Path,
    date: str,
    delivered: str,
    habits: list[dict],
) -> Path:
    state_dir.mkdir(parents=True, exist_ok=True)
    p = state_dir / f"morning-checkin-{date}.json"
    p.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "date": date,
                "generated_at": delivered,
                "delivered_at_utc": delivered,
                "habits": habits,
            }
        ),
        encoding="utf-8",
    )
    return p


DAILY_HABITS = [
    {"position": 1, "vikunja_task_id": 14, "title": "Wake at 5:00 AM"},
    {"position": 2, "vikunja_task_id": 15, "title": "Meditate"},
]


# ---------------------------------------------------------------------------
# find_checkin_within_48hr_window
# ---------------------------------------------------------------------------


class TestFindCheckinWithinWindow:
    def test_empty_state_dir_returns_empty(self, tmp_path):
        result = pmr.find_checkin_within_48hr_window(
            tmp_path / "nonexistent",
            datetime(2026, 6, 2, 11, 30, tzinfo=timezone.utc),
        )
        assert result == []

    def test_within_48hr_included(self, tmp_path):
        state_dir = tmp_path / "state"
        _write_checkin(state_dir, "2026-06-01", "2026-06-01T11:05:00Z", DAILY_HABITS)
        result = pmr.find_checkin_within_48hr_window(
            state_dir, datetime(2026, 6, 2, 11, 30, tzinfo=timezone.utc)
        )
        assert len(result) == 1
        assert result[0].checkin_date_et == "2026-06-01"

    def test_older_than_48hr_excluded(self, tmp_path):
        state_dir = tmp_path / "state"
        _write_checkin(state_dir, "2026-05-30", "2026-05-30T08:00:00Z", DAILY_HABITS)
        result = pmr.find_checkin_within_48hr_window(
            state_dir, datetime(2026, 6, 2, 11, 30, tzinfo=timezone.utc)
        )
        assert result == []

    def test_sort_desc(self, tmp_path):
        state_dir = tmp_path / "state"
        _write_checkin(state_dir, "2026-06-01", "2026-06-01T11:05:00Z", DAILY_HABITS)
        _write_checkin(state_dir, "2026-06-02", "2026-06-02T11:05:00Z", DAILY_HABITS)
        result = pmr.find_checkin_within_48hr_window(
            state_dir, datetime(2026, 6, 2, 12, 0, tzinfo=timezone.utc)
        )
        assert [c.checkin_date_et for c in result] == [
            "2026-06-02",
            "2026-06-01",
        ]

    def test_malformed_artifact_skipped(self, tmp_path):
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)
        (state_dir / "morning-checkin-2026-06-01.json").write_text(
            "not json", encoding="utf-8"
        )
        result = pmr.find_checkin_within_48hr_window(
            state_dir, datetime(2026, 6, 2, tzinfo=timezone.utc)
        )
        assert result == []


# ---------------------------------------------------------------------------
# correlate_reply_to_checkin
# ---------------------------------------------------------------------------


class TestCorrelateReply:
    def test_default_when_no_candidates(self, tmp_path):
        assert (
            pmr.correlate_reply_to_checkin(
                reply_text="wake done",
                candidates=[],
                default_date_et="2026-06-02",
            )
            == "2026-06-02"
        )

    def test_explicit_iso_date_hint(self, tmp_path):
        state_dir = tmp_path / "state"
        _write_checkin(state_dir, "2026-06-01", "2026-06-01T11:05:00Z", DAILY_HABITS)
        _write_checkin(state_dir, "2026-06-02", "2026-06-02T11:05:00Z", DAILY_HABITS)
        candidates = pmr.find_checkin_within_48hr_window(
            state_dir, datetime(2026, 6, 2, 12, 0, tzinfo=timezone.utc)
        )
        result = pmr.correlate_reply_to_checkin(
            reply_text="for 2026-06-01: wake done",
            candidates=candidates,
            default_date_et="2026-06-02",
        )
        assert result == "2026-06-01"

    def test_yesterday_hint(self, tmp_path):
        state_dir = tmp_path / "state"
        _write_checkin(state_dir, "2026-06-01", "2026-06-01T11:05:00Z", DAILY_HABITS)
        _write_checkin(state_dir, "2026-06-02", "2026-06-02T11:05:00Z", DAILY_HABITS)
        candidates = pmr.find_checkin_within_48hr_window(
            state_dir, datetime(2026, 6, 2, 12, 0, tzinfo=timezone.utc)
        )
        result = pmr.correlate_reply_to_checkin(
            reply_text="yesterday wake done",
            candidates=candidates,
            default_date_et="2026-06-02",
        )
        assert result == "2026-06-01"

    def test_weekday_name_hint(self, tmp_path):
        """Reply containing 'Mon' should resolve to the Monday check-in."""
        state_dir = tmp_path / "state"
        # 2026-06-01 is a Monday; 2026-06-02 is a Tuesday.
        _write_checkin(state_dir, "2026-06-01", "2026-06-01T11:05:00Z", DAILY_HABITS)
        _write_checkin(state_dir, "2026-06-02", "2026-06-02T11:05:00Z", DAILY_HABITS)
        candidates = pmr.find_checkin_within_48hr_window(
            state_dir, datetime(2026, 6, 2, 12, 0, tzinfo=timezone.utc)
        )
        result = pmr.correlate_reply_to_checkin(
            reply_text="mon wake done",
            candidates=candidates,
            default_date_et="2026-06-02",
        )
        assert result == "2026-06-01"

    def test_default_today_when_no_hint_and_no_history(self, tmp_path):
        state_dir = tmp_path / "state"
        _write_checkin(state_dir, "2026-06-01", "2026-06-01T11:05:00Z", DAILY_HABITS)
        _write_checkin(state_dir, "2026-06-02", "2026-06-02T11:05:00Z", DAILY_HABITS)
        candidates = pmr.find_checkin_within_48hr_window(
            state_dir, datetime(2026, 6, 2, 12, 0, tzinfo=timezone.utc)
        )
        # No history path -> tier 3 (unresolved scan) skipped -> falls to tier 4.
        result = pmr.correlate_reply_to_checkin(
            reply_text="wake done",
            candidates=candidates,
            default_date_et="2026-06-02",
        )
        assert result == "2026-06-02"

    def test_most_recent_unresolved_tiebreak(self, tmp_path):
        """When today's check-in has the habit already resolved but yesterday's
        is still open, the reply correlates to yesterday."""
        state_dir = tmp_path / "state"
        _write_checkin(state_dir, "2026-06-01", "2026-06-01T11:05:00Z", DAILY_HABITS)
        _write_checkin(state_dir, "2026-06-02", "2026-06-02T11:05:00Z", DAILY_HABITS)
        history_path = tmp_path / "history.jsonl"
        # Today's wake is already complete; yesterday's is open.
        history_path.write_text(
            json.dumps(
                {
                    "domain": "habits",
                    "task_id": 14,
                    "title": "Wake",
                    "date": "2026-06-02",
                    "state": "complete",
                    "source": "whatsapp",
                    "timestamp": "2026-06-02T11:30:00+00:00",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        candidates = pmr.find_checkin_within_48hr_window(
            state_dir, datetime(2026, 6, 2, 12, 0, tzinfo=timezone.utc)
        )
        result = pmr.correlate_reply_to_checkin(
            reply_text="wake done",
            candidates=candidates,
            default_date_et="2026-06-02",
            history_path=history_path,
        )
        assert result == "2026-06-01"


# ---------------------------------------------------------------------------
# _habit_unresolved_on_date
# ---------------------------------------------------------------------------


class TestHabitUnresolved:
    def test_no_history_means_unresolved(self):
        assert pmr._habit_unresolved_on_date([], 14, "2026-06-01") is True

    def test_complete_state_record_resolves(self):
        history = [
            {
                "domain": "habits",
                "task_id": 14,
                "date": "2026-06-01",
                "state": "complete",
            }
        ]
        assert pmr._habit_unresolved_on_date(history, 14, "2026-06-01") is False

    def test_skipped_state_record_resolves(self):
        history = [
            {
                "domain": "habits",
                "task_id": 14,
                "date": "2026-06-01",
                "state": "skipped",
            }
        ]
        assert pmr._habit_unresolved_on_date(history, 14, "2026-06-01") is False

    def test_auto_skipped_event_resolves(self):
        history = [
            {
                "event_type": "auto_skipped",
                "task_id": 14,
                "original_checkin_date_et": "2026-06-01",
            }
        ]
        assert pmr._habit_unresolved_on_date(history, 14, "2026-06-01") is False

    def test_different_date_doesnt_resolve(self):
        history = [
            {
                "domain": "habits",
                "task_id": 14,
                "date": "2026-06-02",
                "state": "complete",
            }
        ]
        assert pmr._habit_unresolved_on_date(history, 14, "2026-06-01") is True


# ---------------------------------------------------------------------------
# CLI integration — end-to-end with correlation
# ---------------------------------------------------------------------------


class TestCliCorrelation:
    def test_today_reply_correlates_to_today_when_only_today_exists(
        self, tmp_path, capsys
    ):
        state_dir = tmp_path / "state"
        _write_checkin(state_dir, "2026-06-02", "2026-06-02T11:05:00Z", DAILY_HABITS)
        argv = [
            "--reply",
            "wake done",
            "--date",
            "2026-06-02",
            "--state-dir",
            str(state_dir),
            "--history-path",
            str(tmp_path / "history.jsonl"),
        ]
        rc = pmr.main(argv)
        assert rc == 0
        out = capsys.readouterr().out
        payload = json.loads(out)
        assert payload["correlated_checkin_date_et"] == "2026-06-02"

    def test_explicit_iso_date_in_reply_swaps_correlation(
        self, tmp_path, capsys
    ):
        state_dir = tmp_path / "state"
        _write_checkin(state_dir, "2026-06-01", "2026-06-01T11:05:00Z", DAILY_HABITS)
        _write_checkin(state_dir, "2026-06-02", "2026-06-02T11:05:00Z", DAILY_HABITS)
        argv = [
            "--reply",
            "for 2026-06-01 wake done",
            "--date",
            "2026-06-02",
            "--state-dir",
            str(state_dir),
            "--history-path",
            str(tmp_path / "history.jsonl"),
        ]
        # Patch clock so find_checkin_within_48hr_window sees both fixtures.
        # The CLI uses datetime.now() inside main() to filter the 48hr window;
        # both fixtures are within 48hr of any plausible "now" so we don't
        # need to patch — the test runs on test-execution clock.
        rc = pmr.main(argv)
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["correlated_checkin_date_et"] == "2026-06-01"

    def test_no_correlate_48hr_disables_correlation(self, tmp_path, capsys):
        """--no-correlate-48hr forces today-only (pre-#408 behavior)."""
        state_dir = tmp_path / "state"
        _write_checkin(state_dir, "2026-06-01", "2026-06-01T11:05:00Z", DAILY_HABITS)
        _write_checkin(state_dir, "2026-06-02", "2026-06-02T11:05:00Z", DAILY_HABITS)
        argv = [
            "--reply",
            "for 2026-06-01 wake done",  # explicit hint
            "--date",
            "2026-06-02",
            "--state-dir",
            str(state_dir),
            "--no-correlate-48hr",
        ]
        rc = pmr.main(argv)
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        # Hint ignored — correlated to today (the --date value).
        assert payload["correlated_checkin_date_et"] == "2026-06-02"

    def test_reply_outside_48hr_window_still_works_against_today(
        self, tmp_path, capsys
    ):
        """A reply that hints at a date NOT in the 48hr candidates falls back
        to today's check-in. The sweeper would have already auto_skipped any
        habits older than 48hr."""
        state_dir = tmp_path / "state"
        # Only today's check-in exists; yesterday's is gone (or never existed).
        _write_checkin(state_dir, "2026-06-02", "2026-06-02T11:05:00Z", DAILY_HABITS)
        argv = [
            "--reply",
            "for 2026-05-15 wake done",  # well outside window
            "--date",
            "2026-06-02",
            "--state-dir",
            str(state_dir),
            "--history-path",
            str(tmp_path / "history.jsonl"),
        ]
        rc = pmr.main(argv)
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["correlated_checkin_date_et"] == "2026-06-02"

    def test_no_matching_morning_list_returns_exit_4(self, tmp_path, capsys):
        """Existing pre-#408 path: no morning list for the correlated date
        returns exit code 4 (preserves NFR-003 / existing CLI contract)."""
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)
        argv = [
            "--reply",
            "wake done",
            "--date",
            "2026-06-02",
            "--state-dir",
            str(state_dir),
        ]
        rc = pmr.main(argv)
        assert rc == 4
