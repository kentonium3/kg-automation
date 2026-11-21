#!/usr/bin/env python3
"""Central loader for the habit runtime schedule (mission #408 / WP-01).

Reads the ``habits:`` top-level section of
``scripts/habits/migrations/phase3-schedule.yaml`` and returns typed
``ScheduleEntry`` instances. This is the **single** parse surface for the
runtime schedule — ``morning_checkin_list.py``, ``query_active_habits_v2``,
``set_due_dates.py`` and ``sweeper.py`` all consume the loader so the YAML
is parsed in exactly one place.

Each habit declares its recurrence as RFC 5545 ``rrule`` text (mission
felix-rrule-adaptation, #1111); the old ``repeat_after_seconds`` key is
refused with a migration message. The ``set_due_dates.py
--reconcile-schedule`` mode and ``migrate_schedule.py`` are both retired.

The ``operations:`` section of the YAML is the frozen mission #282
migration record (C-005: never edited). This loader ignores
``operations:`` entirely and only reads ``habits:``.

Drift check (FR-013): ``python3 -m scripts.habits.schedule_loader
--check-live [--schedule-path P]`` reads each habit's live task with
``VikunjaClient.get_task_v2`` and prints one JSON line per habit with a
``status`` of ``match | missing | differs | inactive | unreadable``, then
a JSON summary line. It only ever issues GETs. Its ``VikunjaClient`` use
is current-state only (the live rule), never completion history.

Public API:

  ``load_schedule(path) -> list[ScheduleEntry]``
      Parse and validate the YAML; raise ``ScheduleConfigError`` on any
      load-time validation failure (unknown weekday name, malformed entry,
      duplicate task_id, etc.).

  ``is_day_specific(entry) -> bool``
      ``True`` iff the entry has at least one designated weekday.

  ``is_active_today(entry, today_weekday) -> bool``
      ``True`` if the entry is daily (no designated weekdays) OR
      ``today_weekday`` is in the entry's designated set.

  ``ScheduleConfigError``
      Raised for every load-time validation failure.

  ``check_live(entries, client) -> list[dict]``
      Read-only drift check of declared rules against live tasks.

  ``WEEKDAY_NAMES``
      Canonical 3-letter ISO weekday tuple ``("Mon", ..., "Sun")``.

Contract: ``kitty-specs/habit-day-specific-scheduling-01KT48Y6/contracts/schedule-config.contract.md``.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import yaml

from scripts.common import vikunja_rule
from scripts.common.vikunja_client import VikunjaClient, VikunjaError

#: Default schedule file (the production runtime schedule).
DEFAULT_SCHEDULE_PATH: Path = (
    Path(__file__).resolve().parent / "migrations" / "phase3-schedule.yaml"
)


#: Canonical 3-letter ISO weekday names in Mon=0..Sun=6 order.
WEEKDAY_NAMES: tuple[str, ...] = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

#: Frozen set form for O(1) membership checks.
_WEEKDAY_SET: frozenset[str] = frozenset(WEEKDAY_NAMES)

#: Loader weekday name -> RFC 5545 ``BYDAY`` token as Vikunja stores it.
_WEEKDAY_TO_BYDAY: dict[str, str] = {
    name: name[:2].lower() for name in WEEKDAY_NAMES
}

#: Frequencies at least as coarse as weekly (the #608 ratchet floor).
_WEEKLY_OR_COARSER: frozenset[str] = frozenset({"weekly", "monthly", "yearly"})

#: The only rule a daily (not day-specific) habit may declare, in normal form.
_DAILY_RULE: dict[str, Any] = {"freq": "daily", "interval": 1}


class ScheduleConfigError(Exception):
    """Raised for any load-time validation failure of the habits schedule.

    The message names the offending entry index + field + violation so the
    operator can fix the YAML without grepping.
    """


@dataclass(frozen=True, slots=True)
class ScheduleEntry:
    """One habit's runtime scheduling metadata.

    Attributes:
        task_id: Vikunja task identifier (the immutable per-task integer id —
            NOT the Vikunja UI ``identifier`` like ``"#10"``).
        title: Display title, mirroring Vikunja's title for human-readability.
        rrule: The habit's declared recurrence rule as RFC 5545 text (for
            example ``FREQ=DAILY;INTERVAL=1`` or ``FREQ=WEEKLY;BYDAY=MO``).
        designated_weekdays: Tuple of 3-letter ISO weekday abbreviations. Empty
            tuple = daily habit (appears every day). Non-empty = day-specific
            habit (appears only on listed weekdays).
    """

    task_id: int
    title: str
    rrule: str
    designated_weekdays: tuple[str, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _normalize_designated_weekdays(
    raw: Any,
    *,
    entry_index: int,
) -> tuple[str, ...]:
    """Validate + dedupe a raw ``designated_weekdays`` value into a tuple.

    Preserves the input ordering of first occurrence; downstream consumers do
    not depend on ordering, but stable ordering aids reproducible test output.
    """
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ScheduleConfigError(
            f"habits[{entry_index}].designated_weekdays must be a list "
            f"(got {type(raw).__name__})"
        )
    seen: set[str] = set()
    ordered: list[str] = []
    for j, item in enumerate(raw):
        if not isinstance(item, str):
            raise ScheduleConfigError(
                f"habits[{entry_index}].designated_weekdays[{j}] must be a "
                f"string (got {type(item).__name__})"
            )
        if item not in _WEEKDAY_SET:
            raise ScheduleConfigError(
                f"habits[{entry_index}].designated_weekdays[{j}] {item!r} is "
                f"not a valid 3-letter ISO weekday — expected one of "
                f"{list(WEEKDAY_NAMES)}"
            )
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return tuple(ordered)


def _validate_rule(
    raw_rule: Any,
    *,
    entry_index: int,
    title: str,
    weekdays: tuple[str, ...],
) -> str:
    """Parse ``rrule`` text and apply the #608 ratchet, re-expressed on the rule.

    A day-specific habit recurs on its designated weekdays, so its rule must
    be weekly (or coarser) with ``BYDAY`` equal to those weekdays. A rule
    that recurs more often, or on other days, is the #607 bug class (a
    weekday habit that never re-arms, or re-arms on the wrong day) and fails
    loudly at load time. A daily habit must declare exactly
    ``FREQ=DAILY;INTERVAL=1``.
    """
    where = f"habits[{entry_index}] ({title!r})"
    if not isinstance(raw_rule, str) or not raw_rule.strip():
        raise ScheduleConfigError(
            f"{where}.rrule must be a non-empty RFC 5545 rule string "
            f"(got {raw_rule!r})"
        )
    try:
        parts = vikunja_rule.rrule_text_to_parts(raw_rule)
    except ValueError as exc:
        raise ScheduleConfigError(f"{where}.rrule {raw_rule!r} is invalid: {exc}") from exc
    rule = vikunja_rule.normalise(parts)
    if rule is None:  # pragma: no cover -- rrule_text_to_parts requires FREQ
        raise ScheduleConfigError(f"{where}.rrule {raw_rule!r} has no FREQ")

    if weekdays:
        if rule["freq"] not in _WEEKLY_OR_COARSER:
            raise ScheduleConfigError(
                f"{where} is day-specific (designated_weekdays={list(weekdays)}) "
                f"but its rrule FREQ is {rule['freq'].upper()}; a day-specific "
                f"habit must repeat weekly or less often (#607/#608)"
            )
        expected = sorted(_WEEKDAY_TO_BYDAY[w] for w in weekdays)
        if rule.get("by_day", []) != expected:
            raise ScheduleConfigError(
                f"{where} is day-specific (designated_weekdays={list(weekdays)}) "
                f"but its rrule BYDAY is {rule.get('by_day', [])}; BYDAY must "
                f"equal the designated weekdays {expected} (#607/#608)"
            )
    elif rule != _DAILY_RULE:
        raise ScheduleConfigError(
            f"{where} is a daily habit (no designated_weekdays) so its rrule "
            f"must be exactly FREQ=DAILY;INTERVAL=1 (got {raw_rule!r})"
        )
    return raw_rule.strip()


def _validate_entry(raw: Any, *, entry_index: int) -> ScheduleEntry:
    """Validate one raw dict entry and return a ``ScheduleEntry``."""
    if not isinstance(raw, dict):
        raise ScheduleConfigError(
            f"habits[{entry_index}] must be a YAML mapping "
            f"(got {type(raw).__name__})"
        )

    task_id = raw.get("task_id")
    if not isinstance(task_id, int) or isinstance(task_id, bool) or task_id <= 0:
        raise ScheduleConfigError(
            f"habits[{entry_index}].task_id must be a positive integer "
            f"(got {task_id!r})"
        )

    title = raw.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ScheduleConfigError(
            f"habits[{entry_index}].title must be a non-empty string "
            f"(got {title!r})"
        )

    if "repeat_after_seconds" in raw:
        raise ScheduleConfigError(
            f"habits[{entry_index}] ({title!r}) still has repeat_after_seconds, "
            f"which Vikunja no longer supports; replace it with an RFC 5545 "
            f"rrule (daily: rrule: \"FREQ=DAILY;INTERVAL=1\", weekday: "
            f"rrule: \"FREQ=WEEKLY;BYDAY=MO\") (#1111)"
        )

    weekdays = _normalize_designated_weekdays(
        raw.get("designated_weekdays"), entry_index=entry_index
    )
    rrule = _validate_rule(
        raw.get("rrule"), entry_index=entry_index, title=title, weekdays=weekdays
    )

    return ScheduleEntry(
        task_id=task_id,
        title=title,
        rrule=rrule,
        designated_weekdays=weekdays,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_schedule(path: Path | str) -> list[ScheduleEntry]:
    """Load and validate the ``habits:`` section of the schedule YAML.

    Args:
        path: Filesystem path to the schedule YAML file.

    Returns:
        A list of validated ``ScheduleEntry`` instances. Empty if the YAML
        has no ``habits:`` section (a valid but degenerate configuration).

    Raises:
        ScheduleConfigError: On any validation failure (unknown weekday,
            malformed entry shape, duplicate task_id, etc.). Also wraps
            YAML parse errors and missing files so callers handle one
            exception type.
    """
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ScheduleConfigError(
            f"schedule file not found: {path}"
        ) from exc
    except OSError as exc:  # pragma: no cover -- FileNotFoundError handled above
        raise ScheduleConfigError(
            f"failed reading schedule file {path}: {exc}"
        ) from exc

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ScheduleConfigError(
            f"YAML parse error in {path}: {exc}"
        ) from exc

    if data is None:
        return []
    if not isinstance(data, dict):
        raise ScheduleConfigError(
            f"schedule file {path} top-level must be a YAML mapping "
            f"(got {type(data).__name__})"
        )

    raw_habits = data.get("habits")
    if raw_habits is None:
        return []
    if not isinstance(raw_habits, list):
        raise ScheduleConfigError(
            f"schedule file {path} 'habits' must be a list "
            f"(got {type(raw_habits).__name__})"
        )

    entries: list[ScheduleEntry] = []
    seen_task_ids: set[int] = set()
    for i, raw in enumerate(raw_habits):
        entry = _validate_entry(raw, entry_index=i)
        if entry.task_id in seen_task_ids:
            raise ScheduleConfigError(
                f"habits[{i}].task_id {entry.task_id} duplicates an earlier "
                f"entry — each habit must appear at most once"
            )
        seen_task_ids.add(entry.task_id)
        entries.append(entry)
    return entries


def is_day_specific(entry: ScheduleEntry) -> bool:
    """``True`` iff the entry has at least one designated weekday set."""
    return len(entry.designated_weekdays) > 0


def is_active_today(entry: ScheduleEntry, today_weekday: str) -> bool:
    """``True`` if the entry should appear in today's check-in.

    Daily habits (no designated weekdays) are always active. Day-specific
    habits are active only on a listed weekday.

    Args:
        entry: A ``ScheduleEntry`` from ``load_schedule``.
        today_weekday: A 3-letter ISO weekday name (``"Mon"`` .. ``"Sun"``).
            Typically produced by ``compute_today.compute_today()``'s ``day``
            field.

    Returns:
        ``True`` if the entry is active today, else ``False``.

    Raises:
        ValueError: ``today_weekday`` is not in ``WEEKDAY_NAMES``.
    """
    if today_weekday not in _WEEKDAY_SET:
        raise ValueError(
            f"today_weekday {today_weekday!r} must be one of "
            f"{list(WEEKDAY_NAMES)}"
        )
    if not entry.designated_weekdays:
        return True
    return today_weekday in entry.designated_weekdays


# ---------------------------------------------------------------------------
# Live drift check (FR-013) — read-only
# ---------------------------------------------------------------------------


#: Drift-check statuses that make the check fail. ``inactive`` (the live task
#: is done, e.g. the retired weekday habits 75–77, C-008) is not drift.
_FAILING_STATUSES: frozenset[str] = frozenset({"missing", "differs", "unreadable"})

#: Every status, in summary order.
DRIFT_STATUSES: tuple[str, ...] = ("match", "inactive", "missing", "differs", "unreadable")


class _TaskReader(Protocol):
    """The one client method the drift check uses (a GET)."""

    def get_task_v2(self, task_id: int, *, timeout: float | None = None) -> dict: ...


def _live_rule_text(task: dict) -> str | None:
    """Return the live task's rule as RFC 5545 text, or None when it has none."""
    if not vikunja_rule.has_rule(task):
        return None
    text = task.get("repeats_rrule")
    if isinstance(text, str) and text:
        return text
    return vikunja_rule.parts_to_rrule_text(task["repeat"])


def check_live(entries: Sequence[ScheduleEntry], client: _TaskReader) -> list[dict]:
    """Compare each entry's declared rule with its live task. Never writes.

    Returns one ``{task_id, title, schedule_rrule, live_rrule, status}`` dict
    per entry, in schedule order. ``status`` is:

    - ``inactive``: the live task is done (checked first; a done habit's
      rule is not drift — tasks 75–77 stay Done per C-008).
    - ``missing``: the live task has no rule.
    - ``differs``: the live rule is not :func:`vikunja_rule.same_rule` as
      the declared one.
    - ``match``: the rules are the same.
    - ``unreadable``: the GET raised a ``VikunjaError``; ``error`` names the
      exception class only (never the token or a response body).
    """
    results: list[dict] = []
    for entry in entries:
        row: dict[str, Any] = {
            "task_id": entry.task_id,
            "title": entry.title,
            "schedule_rrule": entry.rrule,
            "live_rrule": None,
        }
        try:
            task = client.get_task_v2(entry.task_id)
        except VikunjaError as exc:
            row["status"] = "unreadable"
            row["error"] = type(exc).__name__
            results.append(row)
            continue
        row["live_rrule"] = _live_rule_text(task)
        declared = vikunja_rule.rrule_text_to_parts(entry.rrule)
        if task.get("done") is True:
            row["status"] = "inactive"
        elif row["live_rrule"] is None:
            row["status"] = "missing"
        elif not vikunja_rule.same_rule(declared, task.get("repeat")):
            row["status"] = "differs"
        else:
            row["status"] = "match"
        results.append(row)
    return results


def summarise(results: Sequence[dict]) -> dict[str, Any]:
    """Return the drift-check summary: ``ok`` plus a count per status."""
    counts = {status: 0 for status in DRIFT_STATUSES}
    for row in results:
        counts[row["status"]] += 1
    ok = not any(counts[status] for status in _FAILING_STATUSES)
    return {"ok": ok, **counts}


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python3 -m scripts.habits.schedule_loader",
        description=(
            "Validate the habits schedule; with --check-live, compare each "
            "habit's declared rrule with its live Vikunja task (read-only)."
        ),
    )
    parser.add_argument(
        "--check-live",
        action="store_true",
        help="Read each habit's live task (GET only) and report rule drift.",
    )
    parser.add_argument(
        "--schedule-path",
        type=Path,
        default=DEFAULT_SCHEDULE_PATH,
        help=f"Schedule YAML (default: {DEFAULT_SCHEDULE_PATH}).",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point.

    Exit codes: 0 when the schedule loads (and, with ``--check-live``, no
    habit is ``missing``/``differs``/``unreadable``); 1 when the drift check
    finds any of those; 2 on a usage or schedule-load error.
    """
    args = _parse_args(argv)
    try:
        entries = load_schedule(args.schedule_path)
    except ScheduleConfigError as exc:
        print(f"schedule error: {exc}", file=sys.stderr)
        return 2
    if not args.check_live:
        print(json.dumps({"ok": True, "habits": len(entries)}))
        return 0
    try:
        client = VikunjaClient()
    except (OSError, ValueError) as exc:
        print(f"client setup failed: {type(exc).__name__}", file=sys.stderr)
        return 2
    results = check_live(entries, client)
    for row in results:
        print(json.dumps(row, ensure_ascii=False))
    summary = summarise(results)
    print(json.dumps(summary))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":  # pragma: no cover - module entry
    sys.exit(main())
