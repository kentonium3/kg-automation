#!/usr/bin/env python3
"""Morning check-in list emitter (mission #371 / WP01).

Reads active habits via scripts/habits/query_active_habits_v2, which now
reads from the sync cache at
/data/services/openclaw/state/sync/task-cache.json
(see scripts/common/sync_cache.py for the canonical entry point).

Produces today's ordered habit list as both:

  (a) a persisted JSON artifact at
      ``/data/services/openclaw/state/habits/morning-checkin-<YYYY-MM-DD>.json``
      (single source of truth for the morning send + reply parse paths), and

  (b) the formatted WhatsApp check-in message text on stdout.

This module is the root-cause fix for issue #371: the morning send and reply
parse used to be two independent OpenClaw sessions, each regenerating the
habit list from live Vikunja state. Async state changes (and unstable
ordering) caused the orderings to diverge -- Kent's "skipped 3" got applied
to the wrong habit. The persisted artifact, ordered by the immutable
``vikunja_task_id`` ASC, removes both failure modes.

The helper composes two existing Phase 5 helpers without modifying them
(C-001):

  * ``scripts.habits.query_active_habits_v2.query_active_today`` -- fetch
    the project-scoped active habit task set (from the sync cache).
  * ``scripts.habits.exclude_completed_v2.exclude_completed_for_today`` --
    filter out habits already addressed today via the JSONL state log.

The atomic-write pattern (tmp + fsync + rename per research D2) prevents a
mid-write crash from leaving a corrupt artifact the next morning. Dates are
in America/New_York throughout per research D1 ("today" means Kent's day,
not UTC's).

See the spec / plan / data-model / contracts under
``kitty-specs/habits-checkin-reply-scripts-first-01KS86ZQ/`` for the full
contract. Public API surface per ``contracts/api.md``; CLI surface per
``contracts/cli.md``.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import sys
import zoneinfo
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.common.sync_cache import (
    SLA_NORMAL,
    SLATier,
)
from scripts.habits.exclude_completed_v2 import exclude_completed_for_today
from scripts.habits.query_active_habits_v2 import query_active_today

# NOTE: ``morning_checkin_list.py`` is invoked exclusively via the module form
# (``python3 -m scripts.habits.morning_checkin_list``) — the helper composes
# downstream modules under ``scripts.common`` and ``scripts.habits`` whose own
# imports use the absolute-package form. Direct-script invocation
# (``python3 scripts/habits/morning_checkin_list.py``) was never supported on
# main and is out of scope for this WP. Only the WP-introduced
# ``schedule_loader`` import gets the try/except fallback so unit tests that
# import ``scripts.habits.schedule_loader`` symbols from this module continue
# to behave identically under either resolution path.
try:
    from scripts.habits.schedule_loader import (
        ScheduleConfigError,
        ScheduleEntry,
        is_active_today,
        load_schedule,
    )
except ImportError:
    # Precedent: scripts/openclaw/observation/summarize.py:36-38.
    from schedule_loader import (  # type: ignore[no-redef]
        ScheduleConfigError,
        ScheduleEntry,
        is_active_today,
        load_schedule,
    )


# ---------------------------------------------------------------------------
# Touchpoint SLA constants (mission #519 WP02)
# ---------------------------------------------------------------------------

#: Touchpoint SLA tier — inherits SLA_NORMAL from the underlying TP-03 call.
TOUCHPOINT_SLA: SLATier = SLA_NORMAL

#: Touchpoint name used in structured error messages.
TOUCHPOINT_NAME = "habits.morning_checkin_list"


# ---------------------------------------------------------------------------
# Module constants (per contracts/api.md)
# ---------------------------------------------------------------------------

#: Default per-date morning-list artifact directory on office2.
DEFAULT_STATE_DIR = Path("/data/services/openclaw/state/habits")

#: Default path to the habits runtime schedule YAML (mission #408 / WP-01).
DEFAULT_SCHEDULE_PATH = (
    Path(__file__).resolve().parent / "migrations" / "phase3-schedule.yaml"
)

#: Map Python ``datetime.weekday()`` ints (Mon=0..Sun=6) to 3-letter names.
_WEEKDAY_BY_INDEX: tuple[str, ...] = (
    "Mon",
    "Tue",
    "Wed",
    "Thu",
    "Fri",
    "Sat",
    "Sun",
)

#: Kent's local timezone. "Today" in this module is Kent's local day, not UTC.
LOCAL_TZ = zoneinfo.ZoneInfo("America/New_York")

#: Schema version embedded in every persisted artifact.
SCHEMA_VERSION = 1

#: Regex for the --date flag (ISO-8601 date).
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ---------------------------------------------------------------------------
# Dataclasses (per contracts/api.md Entity 1)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MorningListHabit:
    """A single habit row in the morning list. Position is 1-indexed.

    ``designated_weekdays`` (mission #408 / E2 extension): tuple of 3-letter
    ISO weekday names (``"Mon"`` .. ``"Sun"``) for day-specific habits, or
    an empty tuple for daily habits. Persisted in the per-date artifact so
    the WP-02 sweeper can recall what was day-specific when it auto-skips.
    """

    position: int
    vikunja_task_id: int
    title: str
    designated_weekdays: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MorningList:
    """The persisted artifact: ordered list of habits Kent should address today."""

    schema_version: int
    date: str  # YYYY-MM-DD, America/New_York
    generated_at: str  # ISO-8601 UTC
    habits: list[MorningListHabit]


# ---------------------------------------------------------------------------
# Internal helpers (clock + I/O wrappers; small, monkeypatch-friendly)
# ---------------------------------------------------------------------------


def _today_local() -> str:
    """Return today's date in America/New_York as ``YYYY-MM-DD``.

    Wrapped so tests can monkeypatch the clock without patching ``datetime``
    globally. Kent's local TZ matches his lived experience of "today's
    check-in" -- UTC midnight is not a meaningful day boundary for him.
    """
    return datetime.now(LOCAL_TZ).date().isoformat()


def _weekday_name_for_date(date_str: str) -> str:
    """Return the 3-letter ISO weekday name for a ``YYYY-MM-DD`` string.

    Mirrors the ``day`` field emitted by ``scripts.habits.compute_today`` so
    morning_checkin_list and the schedule loader agree on weekday naming.
    """
    parsed = datetime.fromisoformat(date_str).date()
    return _WEEKDAY_BY_INDEX[parsed.weekday()]


def _now_utc_iso() -> str:
    """Return current UTC instant as ISO-8601 with explicit ``Z`` suffix.

    The ``Z`` form is chosen over ``+00:00`` for compactness in the
    persisted JSON (NFR-005 keeps files ~1KB).
    """
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    )


def _query_habits(
    date: str,
    schedule_path: Path | None = None,
) -> list[dict]:
    """Fetch active habits for the given date via the Phase 5 helper.

    Thin wrapper -- exists so tests can monkeypatch this single name to
    bypass the cache read path without re-wiring the underlying helper
    (though the end-to-end cache path is also exercised in
    integration-style test cases).

    When ``schedule_path`` is supplied (mission #408 / WP-01), the
    day-of-week filter is applied at the query layer so day-specific
    habits not designated for today are excluded before
    ``exclude_completed_for_today`` runs.
    """
    return query_active_today(
        today=date,
        schedule_path=schedule_path,
    )


def _exclude_already_addressed(
    habits: list[dict],
    date: str,
) -> list[dict]:
    """Filter out habits with a ``state=complete`` JSONL record for ``date``.

    Thin wrapper around ``exclude_completed_for_today`` so callers (and
    tests) can intercept the dependency at this seam without monkeypatching
    a module name with a hyphen-free dotted path.
    """
    return exclude_completed_for_today(habits, today=date)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class ScheduleInvariantError(Exception):
    """Raised when a day-specific habit not designated for today somehow
    survives the day-of-week filter.

    Production safety net: if this fires, the day-of-week filter wiring is
    broken (e.g., a habit's schedule entry was mutated between the query
    layer and the morning-list build) and Kent's check-in would otherwise
    contain a habit he cannot do today. The CLI maps this to ``exit 4`` with
    structured stderr (``error_type: schedule_invariant_violation``).
    """


def build_morning_list(
    *,
    date: str | None = None,
    schedule_path: Path | None = None,
) -> MorningList:
    """Build the ordered ``MorningList`` for a Kent-day.

    Behavior:
      1. Resolve ``date`` (default: today in America/New_York).
      2. Query active habits for ``date`` via the Phase 5 helper (reads from
         the sync cache — no direct Vikunja HTTP call). The day-of-week
         filter from mission #408 is applied here when ``schedule_path`` is
         set (default is the in-repo phase3 schedule).
      3. Exclude habits already addressed today via the JSONL state log.
      4. Sort surviving habits by ``vikunja_task_id`` ASC (immutable
         per ``reference_vikunja_id_vs_identifier.md`` -- the only sort key
         that does not reintroduce the #371 instability).
      5. Resolve each habit's ``designated_weekdays`` from the schedule (for
         persistence in the artifact — needed by the WP-02 sweeper).
      6. Verify the day-of-week invariant: every entry in the produced list
         must satisfy ``is_active_today`` OR be a daily habit. Violations
         raise ``ScheduleInvariantError`` (mapped to CLI exit 4).
      7. Assign 1-indexed positions and return a frozen ``MorningList``.

    Args:
        date: ISO-8601 ``YYYY-MM-DD``. ``None`` => today local.
        schedule_path: Path to the habits schedule YAML. Pass an explicit
            path to enable the mission-#408 day-of-week filter; pass
            ``None`` (the default) to disable it. The CLI entry point
            defaults to ``DEFAULT_SCHEDULE_PATH`` so production runs always
            apply the filter — keeping the function default at ``None``
            preserves existing test fixtures that do not configure a
            schedule.

    Returns:
        A frozen ``MorningList`` with ``habits`` ordered by task_id ASC. The
        ``designated_weekdays`` field on each ``MorningListHabit`` reflects
        the schedule entry's value, or an empty tuple if the habit is daily
        or not in the schedule.

    Raises:
        ValueError: ``date`` does not match ``YYYY-MM-DD``.
        OSError: cache read failure (cache missing, stale, or corrupt).
        ScheduleConfigError: ``schedule_path`` is supplied but YAML invalid.
        ScheduleInvariantError: A day-specific habit not designated for
            today survived the filter (production safety net).
    """
    resolved_date = date if date is not None else _today_local()
    if not _DATE_RE.match(resolved_date):
        raise ValueError(
            f"date {resolved_date!r} must match YYYY-MM-DD"
        )

    raw_habits = _query_habits(resolved_date, schedule_path)
    surviving = _exclude_already_addressed(raw_habits, resolved_date)

    # Resolve the schedule once so we can both stamp designated_weekdays on
    # each emitted habit AND verify the day-of-week invariant.
    schedule_by_task_id: dict[int, ScheduleEntry] = {}
    today_weekday: str | None = None
    if schedule_path is not None:
        for entry in load_schedule(schedule_path):
            schedule_by_task_id[entry.task_id] = entry
        today_weekday = _weekday_name_for_date(resolved_date)

    # Sort by Vikunja task_id ASC -- the immutable per-task identifier.
    # Any other key (title, due_date, project order) would reintroduce
    # the #371 instability the moment Vikunja's underlying state shifts.
    def _id_key(task: dict) -> int:
        tid = task.get("id")
        if not isinstance(tid, int):
            raise ValueError(
                f"Vikunja habit task missing integer 'id': {task!r}"
            )
        return tid

    ordered = sorted(surviving, key=_id_key)

    habits: list[MorningListHabit] = []
    for index, task in enumerate(ordered):
        tid = _id_key(task)
        entry = schedule_by_task_id.get(tid)
        designated: tuple[str, ...] = entry.designated_weekdays if entry else ()

        # Day-of-week invariant safety net. The query layer should have
        # already excluded mis-scheduled habits; if one slipped through, fail
        # loudly rather than ship a wrong check-in to Kent.
        if (
            entry is not None
            and today_weekday is not None
            and not is_active_today(entry, today_weekday)
        ):
            raise ScheduleInvariantError(
                f"task_id={tid} title={task.get('title')!r} is day-specific "
                f"({list(entry.designated_weekdays)}) but today is "
                f"{today_weekday!r} — day-of-week filter is broken"
            )

        habits.append(
            MorningListHabit(
                position=index + 1,
                vikunja_task_id=tid,
                title=str(task.get("title", "")).strip(),
                designated_weekdays=designated,
            )
        )

    return MorningList(
        schema_version=SCHEMA_VERSION,
        date=resolved_date,
        generated_at=_now_utc_iso(),
        habits=habits,
    )


def persist_morning_list(
    morning_list: MorningList,
    *,
    state_dir: Path = DEFAULT_STATE_DIR,
) -> Path:
    """Atomically write ``morning_list`` to ``state_dir`` and return the path.

    Per research D2: write to ``<path>.tmp``, fsync, then ``os.replace`` to
    the final path. A crash before ``os.replace`` leaves only the ``.tmp``
    file -- the previous day's artifact (if any) is untouched, and the
    canonical ``morning-checkin-<date>.json`` either reflects the prior
    successful write or does not exist at all. No partial files are ever
    visible at the canonical path.

    Args:
        morning_list: The list to persist (typically from
            ``build_morning_list``).
        state_dir: Directory to write to. Created if missing.

    Returns:
        The final ``Path`` of the persisted file (after ``os.replace``).

    Raises:
        OSError: filesystem failure during mkdir, write, fsync, or replace.
    """
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)

    final_path = state_dir / f"morning-checkin-{morning_list.date}.json"
    tmp_path = state_dir / f"morning-checkin-{morning_list.date}.json.tmp"

    payload = _morning_list_to_dict(morning_list)
    body = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False)

    # Open with explicit flush + fsync so a power loss between the write
    # and the os.replace cannot leave a torn final file. The .tmp may be
    # left dangling on crash -- harmless; it's not at the canonical path.
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(body)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, final_path)
    except OSError:
        # Best-effort cleanup of the dangling tmp file so we don't pollute
        # the state dir on retry. Swallow secondary errors; the primary
        # one is what the caller needs to see.
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:  # pragma: no cover -- defensive
            pass
        raise

    return final_path


def render_morning_message(morning_list: MorningList) -> str:
    """Render the WhatsApp check-in message text for Kent.

    Empty list -> single line ``"All habits complete for today."`` per the
    existing SKILL.md / data-model convention.

    Otherwise the format (per contracts/cli.md) is::

        Morning check-in - <Day>, <Month> <DD>:

        1. <title>
        2. <title>
        ...

        Reply with what you've done (e.g., "1 and 2 done, skipping 4")

    where ``<Day>`` is the day-of-week (``%A``) derived from
    ``morning_list.date`` interpreted in America/New_York, and
    ``<Month> <DD>`` is ``"<full month> <day>"`` without zero-padding on
    the day. The day-stripping is portable across macOS (which does not
    accept ``%-d``) and Linux.
    """
    if not morning_list.habits:
        return "All habits complete for today."

    parsed = datetime.fromisoformat(morning_list.date).date()
    day_name = parsed.strftime("%A")
    month_name = parsed.strftime("%B")
    day_num = str(parsed.day)  # portable, no zero padding (cross-platform).

    header = f"Morning check-in — {day_name}, {month_name} {day_num}:"

    lines: list[str] = [header, ""]
    for h in morning_list.habits:
        lines.append(f"{h.position}. {h.title}")
    lines.append("")
    lines.append(
        "Reply with what you've done (e.g., \"1 and 2 done, skipping 4\")"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Private helpers (serialization)
# ---------------------------------------------------------------------------


def _morning_list_to_dict(morning_list: MorningList) -> dict[str, Any]:
    """Convert a ``MorningList`` to a JSON-serializable dict.

    Mission #408 / E2 extension: ``designated_weekdays`` is included on each
    habit row ONLY when the habit is day-specific (non-empty tuple). Daily
    habits omit the field entirely — preserving the pre-#408 persisted
    artifact shape so the existing reader contract (and existing tests)
    continue to hold without modification. The WP-02 sweeper interprets
    absence-of-field as "daily habit" per the contract.
    """
    return {
        "schema_version": morning_list.schema_version,
        "date": morning_list.date,
        "generated_at": morning_list.generated_at,
        "habits": [_habit_to_dict(h) for h in morning_list.habits],
    }


def _habit_to_dict(habit: MorningListHabit) -> dict[str, Any]:
    """Serialize one habit row, omitting empty ``designated_weekdays``."""
    out: dict[str, Any] = {
        "position": habit.position,
        "vikunja_task_id": habit.vikunja_task_id,
        "title": habit.title,
    }
    if habit.designated_weekdays:
        out["designated_weekdays"] = list(habit.designated_weekdays)
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class _ArgparseError(Exception):
    """Raised by ``_StructuredArgumentParser.error()`` to let ``main()`` return exit 3.

    The default ``argparse.ArgumentParser.error()`` calls ``sys.exit(2)``, which
    leaks through ``main()`` and violates ``contracts/cli.md`` (exit 2 is reserved
    for filesystem persistence failure; exit 3 is the canonical "validation /
    usage error" code). We catch this exception in ``main()`` and translate it
    to a structured stderr line + ``return 3``.
    """


class _StructuredArgumentParser(argparse.ArgumentParser):
    """ArgumentParser subclass that raises ``_ArgparseError`` instead of ``sys.exit(2)`` on bad flags.

    ``--help`` is unaffected: argparse's help path uses ``parser.exit()`` /
    ``parser._print_message``, not ``error()``, so it still exits 0 as expected.
    """

    def error(self, message: str) -> None:  # type: ignore[override]
        raise _ArgparseError(message)


def _build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser for the ``python3 -m`` entry point."""
    parser = _StructuredArgumentParser(
        prog="morning_checkin_list",
        description=(
            "Emit today's ordered habit list as both (a) a persisted JSON "
            "artifact at <state-dir>/morning-checkin-<date>.json and (b) "
            "the formatted WhatsApp check-in message on stdout. Reads "
            "active habits from the Felix sync cache (no direct Vikunja "
            "HTTP calls). The artifact is the single source of truth for "
            "the reply-parse path; the message is what Felix relays to "
            "Kent. Use --dry-run to emit the message without writing the "
            "artifact."
        ),
    )
    parser.add_argument(
        "--date",
        default=None,
        help=(
            "Date in YYYY-MM-DD (default: today in America/New_York)."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip artifact persistence; emit only the formatted message.",
    )
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=DEFAULT_STATE_DIR,
        help=(
            f"Directory for the persisted artifact "
            f"(default: {DEFAULT_STATE_DIR})."
        ),
    )
    parser.add_argument(
        "--schedule-path",
        type=Path,
        default=DEFAULT_SCHEDULE_PATH,
        help=(
            "Path to the habits runtime schedule YAML (mission #408 / "
            "WP-01). Drives the day-of-week filter. Default: in-repo "
            f"{DEFAULT_SCHEDULE_PATH}."
        ),
    )
    parser.add_argument(
        "--no-schedule",
        action="store_true",
        help=(
            "Disable the day-of-week filter (preserves pre-#408 behavior). "
            "Use for diagnostics; production runs always apply the filter."
        ),
    )
    return parser


def _emit_stderr_error(step: str, error: str) -> None:
    """Emit a single JSON line on stderr to keep error output structured."""
    msg = json.dumps({"step": step, "error": error}, ensure_ascii=False)
    print(msg, file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Exit codes per contracts/cli.md (extended by mission #408)::

        0 -- success (message emitted; artifact written unless --dry-run)
        1 -- cache read failure (missing, stale, or corrupt sync cache)
        2 -- Filesystem write failure (cache succeeded; persist failed)
        3 -- Validation / usage error (bad date format, bad flags, or
             schedule.yaml validation failure — ScheduleConfigError)
        4 -- Schedule invariant violation (day-specific habit not designated
             for today survived the filter). Production safety net.
    """
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except _ArgparseError as exc:
        _emit_stderr_error(step="argparse", error=str(exc))
        return 3

    if args.date is not None:
        if not _DATE_RE.match(args.date):
            _emit_stderr_error(
                step="argparse",
                error=f"--date must match YYYY-MM-DD (got {args.date!r})",
            )
            return 3
        # Reject syntactically-valid-but-semantically-impossible dates
        # like 2026-13-99 (month/day out of range). fromisoformat is
        # strict on both range and length.
        try:
            datetime.fromisoformat(args.date).date()
        except ValueError as exc:
            _emit_stderr_error(
                step="argparse",
                error=(
                    f"--date must be a real YYYY-MM-DD date "
                    f"(got {args.date!r}): {exc}"
                ),
            )
            return 3

    schedule_path: Path | None = None if args.no_schedule else args.schedule_path

    try:
        morning_list = build_morning_list(
            date=args.date,
            schedule_path=schedule_path,
        )
    except ValueError as exc:
        _emit_stderr_error(step="argparse", error=str(exc))
        return 3
    except ScheduleConfigError as exc:
        _emit_stderr_error(step="schedule_load", error=str(exc))
        return 3
    except ScheduleInvariantError as exc:
        _emit_stderr_error(
            step="schedule_invariant_violation",
            error=str(exc),
        )
        return 4
    except OSError as exc:
        _emit_stderr_error(step="cache_read", error=str(exc))
        return 1

    if not args.dry_run:
        try:
            persist_morning_list(morning_list, state_dir=args.state_dir)
        except OSError as exc:
            _emit_stderr_error(step="persist", error=str(exc))
            return 2

    sys.stdout.write(render_morning_message(morning_list))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
