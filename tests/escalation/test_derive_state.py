"""Tests for ``scripts.escalation.derive_state`` (Phase 6 / WP02).

Coverage targets per WP02 § Validation:

- Every ``EscalationState.current_state`` Literal value reachable.
- Every ``EscalationStateError.reason`` value covered.
- Snooze expiry boundary (``today == snooze_until`` -> still ``"snoozed"``).
- ``last_event`` and ``last_event_recorded_at`` populated whenever input is
  non-empty.

All time-dependent paths monkeypatch ``scripts.escalation.derive_state._today_local``
rather than calling real ``date.today()``. The ``make_jsonl_record`` factory
fixture from ``tests/escalation/conftest.py`` is used to build records that
satisfy the Phase 2 state_log schema plus the WP01
``validate_event_params`` validator that ``derive_state`` consumes.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from scripts.escalation import derive_state as derive_state_mod
from scripts.escalation.derive_state import (
    EscalationState,
    EscalationStateError,
    derive_state,
    main,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def freeze_today(monkeypatch):
    """Return a callable that freezes ``_today_local`` to the supplied date.

    Tests call ``freeze_today(date(2026, 5, 21))`` to pin the policy walk
    clock without depending on the real wall clock.
    """

    def _freeze(today: date) -> None:
        monkeypatch.setattr(derive_state_mod, "_today_local", lambda: today)

    return _freeze


# ---------------------------------------------------------------------------
# Empty input
# ---------------------------------------------------------------------------


def test_empty_records_returns_new():
    """``derive_state([])`` returns the canonical ``"new"`` empty state."""
    state = derive_state([])
    assert isinstance(state, EscalationState)
    assert state.current_state == "new"
    assert state.last_event is None
    assert state.snooze_active_until is None
    assert state.next_eligible_level is None
    assert state.last_event_recorded_at is None


# ---------------------------------------------------------------------------
# Terminal states
# ---------------------------------------------------------------------------


def test_done_terminal(make_jsonl_record, freeze_today):
    """Single ``state="done"`` record yields the terminal ``done`` bucket."""
    freeze_today(date(2026, 5, 21))
    record = make_jsonl_record(state="done", date="2026-05-20")
    state = derive_state([record])
    assert state.current_state == "done"
    assert state.next_eligible_level is None
    assert state.snooze_active_until is None
    assert state.last_event == record


def test_dismissed_terminal(make_jsonl_record, freeze_today):
    """Single ``state="dismissed"`` record yields the terminal ``dismissed`` bucket."""
    freeze_today(date(2026, 5, 21))
    record = make_jsonl_record(state="dismissed", date="2026-05-20")
    state = derive_state([record])
    assert state.current_state == "dismissed"
    assert state.next_eligible_level is None
    assert state.snooze_active_until is None


def test_done_overrides_earlier_level_sent(make_jsonl_record, freeze_today):
    """A later ``done`` record wins over an earlier ``level_sent``."""
    freeze_today(date(2026, 5, 21))
    earlier = make_jsonl_record(
        state="level_sent",
        level=1,
        date="2026-05-18",
    )
    later = make_jsonl_record(state="done", date="2026-05-20")
    state = derive_state([earlier, later])
    assert state.current_state == "done"
    assert state.last_event == later


# ---------------------------------------------------------------------------
# Snooze states
# ---------------------------------------------------------------------------


def test_snoozed_active_future(make_jsonl_record, freeze_today):
    """``snooze_until`` strictly in the future -> ``"snoozed"`` active."""
    freeze_today(date(2026, 5, 21))
    record = make_jsonl_record(
        state="snoozed",
        date="2026-05-21",
        snooze_days=3,
        snooze_until="2026-05-24",
    )
    state = derive_state([record])
    assert state.current_state == "snoozed"
    assert state.snooze_active_until == date(2026, 5, 24)
    assert state.next_eligible_level is None


def test_snoozed_active_today_boundary(make_jsonl_record, freeze_today):
    """``snooze_until == today`` -> still ``"snoozed"`` (``<=`` boundary)."""
    freeze_today(date(2026, 5, 24))
    record = make_jsonl_record(
        state="snoozed",
        date="2026-05-21",
        snooze_days=3,
        snooze_until="2026-05-24",
    )
    state = derive_state([record])
    assert state.current_state == "snoozed"
    assert state.snooze_active_until == date(2026, 5, 24)
    assert state.next_eligible_level is None


def test_snoozed_expired(make_jsonl_record, freeze_today):
    """``snooze_until`` in the past -> ``"snoozed_expired"`` re-entering at Level 1."""
    freeze_today(date(2026, 5, 25))
    record = make_jsonl_record(
        state="snoozed",
        date="2026-05-21",
        snooze_days=3,
        snooze_until="2026-05-24",
    )
    state = derive_state([record])
    assert state.current_state == "snoozed_expired"
    assert state.snooze_active_until == date(2026, 5, 24)
    assert state.next_eligible_level == 1


# ---------------------------------------------------------------------------
# Rescheduled
# ---------------------------------------------------------------------------


def test_rescheduled(make_jsonl_record, freeze_today):
    """Single ``state="rescheduled"`` -> ``"rescheduled"`` bucket, no next level."""
    freeze_today(date(2026, 5, 21))
    record = make_jsonl_record(
        state="rescheduled",
        date="2026-05-20",
        reschedule_to="2026-05-30",
    )
    state = derive_state([record])
    assert state.current_state == "rescheduled"
    assert state.next_eligible_level is None
    assert state.snooze_active_until is None


# ---------------------------------------------------------------------------
# level_sent walks
# ---------------------------------------------------------------------------


def test_level_1_fresh(make_jsonl_record, freeze_today):
    """``level=1`` recorded today -> already alerted, no next eligible level."""
    freeze_today(date(2026, 5, 21))
    record = make_jsonl_record(
        state="level_sent",
        level=1,
        date="2026-05-21",
    )
    state = derive_state([record])
    assert state.current_state == "level_1_sent"
    assert state.next_eligible_level is None


def test_level_1_stale_2_days(make_jsonl_record, freeze_today):
    """``level=1`` recorded 2 days ago -> ``next_eligible_level=2``."""
    freeze_today(date(2026, 5, 21))
    record = make_jsonl_record(
        state="level_sent",
        level=1,
        date="2026-05-19",
    )
    state = derive_state([record])
    assert state.current_state == "level_1_sent"
    assert state.next_eligible_level == 2


def test_level_1_stale_5_days(make_jsonl_record, freeze_today):
    """``level=1`` recorded 5 days ago -> still ``next_eligible_level=2``."""
    freeze_today(date(2026, 5, 21))
    record = make_jsonl_record(
        state="level_sent",
        level=1,
        date="2026-05-16",
    )
    state = derive_state([record])
    assert state.current_state == "level_1_sent"
    assert state.next_eligible_level == 2


def test_level_2_sent(make_jsonl_record, freeze_today):
    """``level=2`` recorded today -> ``level_2_sent``, ``next=2`` (repeat allowed)."""
    freeze_today(date(2026, 5, 21))
    record = make_jsonl_record(
        state="level_sent",
        level=2,
        date="2026-05-21",
    )
    state = derive_state([record])
    assert state.current_state == "level_2_sent"
    assert state.next_eligible_level == 2


def test_level_2_stale_3_days(make_jsonl_record, freeze_today):
    """``level=2`` recorded 3 days ago -> still ``level_2_sent`` with ``next=2``."""
    freeze_today(date(2026, 5, 21))
    record = make_jsonl_record(
        state="level_sent",
        level=2,
        date="2026-05-18",
    )
    state = derive_state([record])
    assert state.current_state == "level_2_sent"
    assert state.next_eligible_level == 2


# ---------------------------------------------------------------------------
# Ordering
# ---------------------------------------------------------------------------


def test_newest_record_wins(make_jsonl_record, freeze_today):
    """Older ``level_1_sent`` followed by newer ``done`` -> terminal ``done``."""
    freeze_today(date(2026, 5, 21))
    older = make_jsonl_record(
        state="level_sent",
        level=1,
        date="2026-05-18",
    )
    newer = make_jsonl_record(state="done", date="2026-05-20")
    # Hand the records in reverse-of-expected order to exercise the sort.
    state = derive_state([older, newer])
    assert state.current_state == "done"
    assert state.last_event == newer


def test_snoozed_after_level_1(make_jsonl_record, freeze_today):
    """Older ``level_1_sent`` then newer ``snoozed`` -> active ``snoozed``."""
    freeze_today(date(2026, 5, 21))
    older = make_jsonl_record(
        state="level_sent",
        level=1,
        date="2026-05-19",
    )
    newer = make_jsonl_record(
        state="snoozed",
        date="2026-05-20",
        snooze_days=3,
        snooze_until="2026-05-23",
    )
    state = derive_state([older, newer])
    assert state.current_state == "snoozed"
    assert state.snooze_active_until == date(2026, 5, 23)


# ---------------------------------------------------------------------------
# Error surface
# ---------------------------------------------------------------------------


def test_level_sent_missing_level_raises(make_jsonl_record):
    """``state="level_sent"`` without a ``level`` field -> ``missing_required_param``."""
    # Build a level_sent record but drop the ``level`` parameter the
    # schema validator demands.
    record = make_jsonl_record(state="level_sent", date="2026-05-21")
    record.pop("level", None)  # defensive -- factory does not add it by default
    with pytest.raises(EscalationStateError) as excinfo:
        derive_state([record])
    assert excinfo.value.reason == "missing_required_param"
    assert excinfo.value.task_id == 1234


def test_unknown_state_raises(make_jsonl_record):
    """A ``state`` not in the escalation vocabulary -> ``unknown_state``."""
    record = make_jsonl_record(state="acknowledged", date="2026-05-21")
    with pytest.raises(EscalationStateError) as excinfo:
        derive_state([record])
    assert excinfo.value.reason == "unknown_state"
    assert excinfo.value.task_id == 1234


def test_unparseable_timestamp_raises(make_jsonl_record):
    """A record with a non-ISO timestamp -> ``impossible_ordering``."""
    record = make_jsonl_record(state="done", date="2026-05-21")
    record["timestamp"] = "not a real ts"
    with pytest.raises(EscalationStateError) as excinfo:
        derive_state([record])
    assert excinfo.value.reason == "impossible_ordering"


def test_non_string_timestamp_raises(make_jsonl_record):
    """A record with a non-string timestamp -> ``impossible_ordering``."""
    record = make_jsonl_record(state="done", date="2026-05-21")
    record["timestamp"] = 12345
    with pytest.raises(EscalationStateError) as excinfo:
        derive_state([record])
    assert excinfo.value.reason == "impossible_ordering"


# ---------------------------------------------------------------------------
# last_event / last_event_recorded_at always populated
# ---------------------------------------------------------------------------


def test_last_event_recorded_at(make_jsonl_record, freeze_today):
    """``last_event_recorded_at`` is the newest record's parsed timestamp."""
    freeze_today(date(2026, 5, 21))
    record = make_jsonl_record(
        state="level_sent",
        level=2,
        date="2026-05-21",
    )
    state = derive_state([record])
    assert state.last_event == record
    assert isinstance(state.last_event_recorded_at, datetime)
    # The factory's default timestamp is ``<date>T12:00:00+00:00``.
    assert state.last_event_recorded_at == datetime(
        2026, 5, 21, 12, 0, 0, tzinfo=timezone.utc
    )


def test_last_event_is_newest_after_sort(make_jsonl_record, freeze_today):
    """When records are out-of-order, ``last_event`` is still the newest."""
    freeze_today(date(2026, 5, 21))
    earlier = make_jsonl_record(
        state="level_sent",
        level=1,
        date="2026-05-15",
    )
    later = make_jsonl_record(
        state="level_sent",
        level=2,
        date="2026-05-20",
    )
    state = derive_state([later, earlier])  # supplied newest-first already
    assert state.last_event == later
    state = derive_state([earlier, later])  # supplied oldest-first
    assert state.last_event == later


# ---------------------------------------------------------------------------
# Module-level helper coverage
# ---------------------------------------------------------------------------


def test_today_local_returns_date():
    """``_today_local`` returns a :class:`date` instance (smoke-only)."""
    today = derive_state_mod._today_local()
    assert isinstance(today, date)


def test_error_rejects_unknown_reason():
    """``EscalationStateError`` refuses reasons outside the taxonomy."""
    with pytest.raises(ValueError):
        EscalationStateError("oops", reason="not-a-real-reason")


# ---------------------------------------------------------------------------
# Debug CLI
# ---------------------------------------------------------------------------


def _write_jsonl(path: Path, records: list[dict]) -> None:
    """Write ``records`` as newline-delimited JSON to ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")


def test_cli_happy_path(tmp_path, make_jsonl_record, freeze_today, capsys):
    """CLI prints ``EscalationState`` JSON and exits 0 when records match."""
    freeze_today(date(2026, 5, 21))
    record = make_jsonl_record(
        state="level_sent",
        level=1,
        date="2026-05-21",
    )
    jsonl_dir = tmp_path / "state" / "escalation"
    _write_jsonl(jsonl_dir / "everyday-escalation-history.jsonl", [record])

    rc = main(
        [
            "--task-id",
            "1234",
            "--project-id",
            "4",
            "--jsonl-dir",
            str(jsonl_dir),
            "--project-slug",
            "everyday",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["task_id"] == 1234
    assert payload["project_id"] == 4
    assert payload["current_state"] == "level_1_sent"
    assert payload["next_eligible_level"] is None


def test_cli_no_records_exits_4(tmp_path, capsys):
    """CLI exits 4 with diagnostic JSON when no records match."""
    jsonl_dir = tmp_path / "state" / "escalation"
    jsonl_dir.mkdir(parents=True)

    rc = main(
        [
            "--task-id",
            "9999",
            "--project-id",
            "4",
            "--jsonl-dir",
            str(jsonl_dir),
        ]
    )
    assert rc == 4
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["records_found"] == 0
    assert payload["current_state"] == "new"


def test_cli_missing_dir_exits_2(tmp_path, capsys):
    """CLI exits 2 when ``--jsonl-dir`` does not exist."""
    rc = main(
        [
            "--task-id",
            "1234",
            "--project-id",
            "4",
            "--jsonl-dir",
            str(tmp_path / "does-not-exist"),
        ]
    )
    assert rc == 2
    err = capsys.readouterr().err
    assert "does not exist" in err


def test_cli_missing_slug_file_exits_2(tmp_path, capsys):
    """CLI exits 2 when ``--project-slug`` is set but the file is missing."""
    jsonl_dir = tmp_path / "state" / "escalation"
    jsonl_dir.mkdir(parents=True)

    rc = main(
        [
            "--task-id",
            "1234",
            "--project-id",
            "4",
            "--jsonl-dir",
            str(jsonl_dir),
            "--project-slug",
            "ghost-project",
        ]
    )
    assert rc == 2
    err = capsys.readouterr().err
    assert "ghost-project" in err


def test_cli_escalation_state_error_exits_3(
    tmp_path, make_jsonl_record, capsys
):
    """CLI exits 3 and prints structured error JSON on EscalationStateError."""
    bad_record = make_jsonl_record(state="acknowledged", date="2026-05-21")
    jsonl_dir = tmp_path / "state" / "escalation"
    _write_jsonl(jsonl_dir / "everyday-escalation-history.jsonl", [bad_record])

    rc = main(
        [
            "--task-id",
            "1234",
            "--project-id",
            "4",
            "--jsonl-dir",
            str(jsonl_dir),
            "--project-slug",
            "everyday",
        ]
    )
    assert rc == 3
    err = capsys.readouterr().err
    payload = json.loads(err)
    assert payload["error"] == "EscalationStateError"
    assert payload["reason"] == "unknown_state"


def test_cli_skips_malformed_lines(tmp_path, make_jsonl_record, freeze_today, capsys):
    """Malformed JSONL lines are skipped silently in the debug CLI."""
    freeze_today(date(2026, 5, 21))
    record = make_jsonl_record(
        state="level_sent",
        level=2,
        date="2026-05-21",
    )
    jsonl_dir = tmp_path / "state" / "escalation"
    jsonl_dir.mkdir(parents=True)
    path = jsonl_dir / "everyday-escalation-history.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        fh.write("\n")  # blank line
        fh.write("not-json\n")  # malformed
        fh.write("[1, 2, 3]\n")  # JSON but not a dict
        fh.write(json.dumps(record) + "\n")

    rc = main(
        [
            "--task-id",
            "1234",
            "--project-id",
            "4",
            "--jsonl-dir",
            str(jsonl_dir),
            "--project-slug",
            "everyday",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["current_state"] == "level_2_sent"


def test_cli_filters_by_task_and_project(
    tmp_path, make_jsonl_record, freeze_today, capsys
):
    """CLI returns only records matching the requested (task_id, project_id)."""
    freeze_today(date(2026, 5, 21))
    target = make_jsonl_record(
        state="level_sent",
        level=1,
        date="2026-05-21",
        task_id=1234,
        project_id=4,
    )
    other_task = make_jsonl_record(
        state="done",
        date="2026-05-21",
        task_id=5678,
        project_id=4,
    )
    other_project = make_jsonl_record(
        state="done",
        date="2026-05-21",
        task_id=1234,
        project_id=99,
    )

    jsonl_dir = tmp_path / "state" / "escalation"
    _write_jsonl(
        jsonl_dir / "everyday-escalation-history.jsonl",
        [other_task, other_project, target],
    )

    rc = main(
        [
            "--task-id",
            "1234",
            "--project-id",
            "4",
            "--jsonl-dir",
            str(jsonl_dir),
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    # Only ``target`` should have driven the policy walk.
    assert payload["current_state"] == "level_1_sent"


def test_cli_module_help_returns_zero():
    """``python3 -m scripts.escalation.derive_state --help`` exits 0."""
    result = subprocess.run(
        [sys.executable, "-m", "scripts.escalation.derive_state", "--help"],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "Vikunja task id" in result.stdout
