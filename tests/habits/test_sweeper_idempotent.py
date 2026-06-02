"""Idempotency tests for the sweeper (mission #408 / WP-02 / T013 / FR-005).

Re-running the sweeper for the same ``(task_id, original_checkin_date_et)``
pair MUST be a no-op — no duplicate ``auto_skipped`` event and no double
``due_date`` advancement.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.habits import sweeper


SCHEDULE_YAML = """\
habits:
  - task_id: 14
    title: "Wake at 5:00 AM"
    repeat_after_seconds: 86400
  - task_id: 76
    title: "Strength training — Wednesday"
    designated_weekdays: ["Wed"]
    repeat_after_seconds: 604800
"""


def _write_schedule(tmp_path: Path) -> Path:
    p = tmp_path / "schedule.yaml"
    p.write_text(SCHEDULE_YAML, encoding="utf-8")
    return p


def _write_checkin(state_dir: Path, date: str, delivered: str, habits):
    state_dir.mkdir(parents=True, exist_ok=True)
    p = state_dir / f"morning-checkin-{date}.json"
    p.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "date": date,
                "generated_at": delivered,
                "delivered_at_utc": delivered,
                "habits": list(habits),
            }
        ),
        encoding="utf-8",
    )
    return p


def _ok_response():
    mock = MagicMock(name="response")
    mock.__enter__ = MagicMock(
        return_value=MagicMock(
            read=MagicMock(return_value=b"{}"),
            status=200,
        )
    )
    mock.__exit__ = MagicMock(return_value=False)
    return mock


def _read_history_events(history_path: Path) -> list[dict]:
    if not history_path.exists():
        return []
    out: list[dict] = []
    for line in history_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out


# ---------------------------------------------------------------------------


class TestSweeperIdempotency:
    def _build_args(self, tmp_path):
        token_path = tmp_path / "token"
        token_path.write_text("token-xxx\n", encoding="utf-8")
        return {
            "schedule_path": _write_schedule(tmp_path),
            "state_dir": tmp_path / "state",
            "history_path": tmp_path / "history.jsonl",
            "vikunja_token_path": token_path,
            "vikunja_base_url": "https://example.invalid/api/v1",
            "now_utc": datetime(2026, 6, 2, 11, 30, tzinfo=timezone.utc),
        }

    def test_second_run_against_same_fixture_emits_no_new_events(
        self, tmp_path
    ):
        """Run the sweeper twice with the same inputs; second run finds the
        first run's ``auto_skipped`` event and treats both habits as
        ``already_auto_skipped`` — zero new history events."""
        args = self._build_args(tmp_path)
        _write_checkin(
            args["state_dir"],
            "2026-05-27",
            "2026-05-27T11:05:00Z",
            [
                {"vikunja_task_id": 14, "title": "Wake at 5:00 AM"},
                {
                    "vikunja_task_id": 76,
                    "title": "Strength training — Wednesday",
                    "designated_weekdays": ["Wed"],
                },
            ],
        )
        with patch("urllib.request.urlopen", return_value=_ok_response()) as mock_urlopen:
            tick1 = sweeper.run_sweep(**args)
        assert tick1.exit_status == "success"
        events_after_run1 = _read_history_events(args["history_path"])
        auto_skips_run1 = [
            e for e in events_after_run1 if e.get("event_type") == "auto_skipped"
        ]
        assert len(auto_skips_run1) == 2
        run1_vikunja_calls = mock_urlopen.call_count
        # 76 is day-specific -> 1 Vikunja PUT. 14 is daily -> 0 PUTs.
        assert run1_vikunja_calls == 1

        # ---- Second run ---------------------------------------------------
        with patch("urllib.request.urlopen", return_value=_ok_response()) as mock_urlopen2:
            tick2 = sweeper.run_sweep(**args)
        events_after_run2 = _read_history_events(args["history_path"])
        auto_skips_run2 = [
            e for e in events_after_run2 if e.get("event_type") == "auto_skipped"
        ]
        # Zero new events: count unchanged.
        assert len(auto_skips_run2) == len(auto_skips_run1) == 2
        # Tick 2 reports both as already_auto_skipped.
        assert tick2.habits_auto_skipped == []
        statuses = sorted(h.status for h in tick2.habits_evaluated)
        assert statuses == ["already_auto_skipped", "already_auto_skipped"]
        # NO Vikunja PUT on the second pass (no double-advance).
        assert mock_urlopen2.call_count == 0

    def test_pre_existing_auto_skipped_event_skipped_cleanly(self, tmp_path):
        """Pre-seed history with an auto_skipped event; sweeper sees it and
        skips without writing a new event or calling Vikunja."""
        args = self._build_args(tmp_path)
        _write_checkin(
            args["state_dir"],
            "2026-05-30",
            "2026-05-30T11:05:00Z",
            [{"vikunja_task_id": 14, "title": "Wake at 5:00 AM"}],
        )
        # Pre-seed.
        args["history_path"].write_text(
            json.dumps(
                {
                    "event_type": "auto_skipped",
                    "task_id": 14,
                    "original_checkin_date_et": "2026-05-30",
                    "original_designated_weekday": None,
                    "tick_id": "01PRESEED",
                    "recorded_at_utc": "2026-06-01T11:30:00Z",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        with patch("urllib.request.urlopen") as mock_urlopen:
            tick = sweeper.run_sweep(**args)

        assert tick.exit_status == "success"
        assert tick.habits_auto_skipped == []
        assert tick.habits_evaluated[0].status == "already_auto_skipped"
        assert mock_urlopen.call_count == 0
        # History contains exactly the pre-seeded event (no append).
        events = _read_history_events(args["history_path"])
        assert len(events) == 1
        assert events[0]["tick_id"] == "01PRESEED"
