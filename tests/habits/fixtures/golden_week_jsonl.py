"""Golden-week JSONL fixture for the trustworthy-weekly-habit-report mission.

Mission: ``trustworthy-weekly-habit-report-01KV4GZ7`` (FR-008 / SC-004).

This fixture writes a deterministic ``habits-history.jsonl`` payload that
covers all three scheduling patterns the weekly report must handle without
zero-percenting any of them:

- ``habit_id=100`` "Daily walk" — daily habit. Scheduled 7/7 of the week.
  Completed on Mon, Tue, Thu, Sat (4 days). Expected weekly rate: 4/7.
- ``habit_id=200`` "Strength Mon" — day-specific. Scheduled Monday only
  (1 day in the window). Completed on Monday. Expected weekly rate: 1/1.
- ``habit_id=300`` "Weekly review" — week-bounded. Scheduled once across
  the week (1 day). Completed on Sunday. Expected weekly rate: 1/1.

The week anchor defaults to ``"2026-06-08"`` (Monday, America/New_York).
Tests pin to that anchor so the fixture is independent of the wall clock
and so the golden-week assertions stay byte-stable.

The records use the exact schema enforced by
``scripts.common.state_log.validate_record("habits", ...)`` — no invented
fields. Timestamps are UTC (the canonical writers all emit UTC), and the
``date`` field is the wall-clock America/New_York date the completion is
attributed to (per the data-model invariants).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

__all__ = [
    "GOLDEN_WEEK_ANCHOR",
    "GOLDEN_WEEK_ANCHOR_ISO",
    "GOLDEN_WEEK_TZ",
    "DAILY_HABIT_ID",
    "DAYSPEC_HABIT_ID",
    "WEEKLY_HABIT_ID",
    "DAILY_COMPLETED_OFFSETS",
    "DAYSPEC_COMPLETED_OFFSETS",
    "WEEKLY_COMPLETED_OFFSETS",
    "write_golden_week_jsonl",
]


#: America/New_York is the canonical reporting timezone for habits. The
#: data-model says the on-disk ``date`` field is wall-clock ET; the
#: ``timestamp`` is UTC. We honor both here.
GOLDEN_WEEK_TZ: ZoneInfo = ZoneInfo("America/New_York")

#: Default Monday-anchor as ISO date string.
GOLDEN_WEEK_ANCHOR_ISO: str = "2026-06-08"

#: Default Monday-anchor as a tz-aware ET datetime at 00:00. Tests use
#: this as the canonical ``window_start`` argument; the matching
#: ``window_end`` is ``GOLDEN_WEEK_ANCHOR + timedelta(days=7)``.
GOLDEN_WEEK_ANCHOR: datetime = datetime(2026, 6, 8, 0, 0, tzinfo=GOLDEN_WEEK_TZ)

# ---------------------------------------------------------------------------
# Habit IDs and their completion-day offsets (Monday=0 through Sunday=6).
# These are exported as module-level constants so tests can assert against
# the same numbers the fixture writes — single source of truth.
# ---------------------------------------------------------------------------

#: Daily walk — daily, completed Mon, Tue, Thu, Sat → 4/7.
DAILY_HABIT_ID: int = 100
DAILY_COMPLETED_OFFSETS: tuple[int, ...] = (0, 1, 3, 5)

#: Strength Mon — day-specific (Mondays), completed Monday → 1/1 for the
#: caller (caller passes ``scheduled_days_count=1``).
DAYSPEC_HABIT_ID: int = 200
DAYSPEC_COMPLETED_OFFSETS: tuple[int, ...] = (0,)

#: Weekly review — week-bounded, completed Sunday → 1/1 for the caller
#: (caller passes ``scheduled_days_count=1``).
WEEKLY_HABIT_ID: int = 300
WEEKLY_COMPLETED_OFFSETS: tuple[int, ...] = (6,)


# ---------------------------------------------------------------------------
# Per-habit metadata used to assemble each record.
# ---------------------------------------------------------------------------

_HABITS: tuple[tuple[int, str, tuple[int, ...]], ...] = (
    (DAILY_HABIT_ID, "Daily walk", DAILY_COMPLETED_OFFSETS),
    (DAYSPEC_HABIT_ID, "Strength Mon", DAYSPEC_COMPLETED_OFFSETS),
    (WEEKLY_HABIT_ID, "Weekly review", WEEKLY_COMPLETED_OFFSETS),
)


def _build_record(
    *,
    task_id: int,
    title: str,
    record_date_iso: str,
    timestamp_iso: str,
) -> dict:
    """Return a single ``habits`` state-log record dict.

    Schema mirrors ``scripts.common.state_log_schema.REQUIRED_FIELDS``
    exactly — no extra fields beyond the required set plus the optional
    ``note`` (omitted here since fixtures do not need it).
    """
    return {
        "domain": "habits",
        "task_id": task_id,
        "title": title,
        "date": record_date_iso,
        "state": "complete",
        "source": "whatsapp",
        "timestamp": timestamp_iso,
    }


def write_golden_week_jsonl(
    path: Path,
    *,
    week_anchor_iso: str = GOLDEN_WEEK_ANCHOR_ISO,
) -> None:
    """Write the golden-week ``habits-history.jsonl`` fixture to ``path``.

    The output is deterministic: same ``week_anchor_iso`` + same code
    version → byte-identical JSONL file. The function creates parent
    directories as needed.

    Args:
        path: Destination JSONL file. Parent directory is created if
            missing.
        week_anchor_iso: Monday-anchor date as YYYY-MM-DD. Defaults to
            :data:`GOLDEN_WEEK_ANCHOR_ISO` (2026-06-08).

    Returns:
        None. The JSONL is written to disk.
    """
    anchor_date = datetime.strptime(week_anchor_iso, "%Y-%m-%d").date()

    path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    for task_id, title, offsets in _HABITS:
        for offset in offsets:
            day_date = anchor_date + timedelta(days=offset)
            # Anchor the wall-clock day at 12:30 ET so the record
            # timestamp lands unambiguously inside the day in both ET and
            # UTC. The morning checkin and sweeper canonically emit
            # midday-ish timestamps, so this matches the production
            # shape.
            ts_local = datetime(
                day_date.year,
                day_date.month,
                day_date.day,
                12,
                30,
                tzinfo=GOLDEN_WEEK_TZ,
            )
            ts_utc = ts_local.astimezone(ZoneInfo("UTC"))
            record = _build_record(
                task_id=task_id,
                title=title,
                record_date_iso=day_date.isoformat(),
                # Use ``isoformat()`` with explicit UTC offset so the
                # string is the same shape state_log emits on writes
                # (e.g. "2026-06-08T16:30:00+00:00").
                timestamp_iso=ts_utc.isoformat(),
            )
            lines.append(json.dumps(record, ensure_ascii=False, sort_keys=False))

    # Trailing newline keeps the file POSIX-conformant and matches the
    # append-mode shape state_log writes in production.
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
