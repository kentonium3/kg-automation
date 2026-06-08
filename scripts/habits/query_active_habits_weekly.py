"""Weekly habit-completion report helper (mission vikunja-client-and-habits-weekly-report-01KTKSFT).

Queries Vikunja project 13 (habits) via the shared VikunjaClient, classifies
each habit, computes per-habit completion percentages over a current 7-day
window and a prior 7-day baseline, and emits the WeeklyHabitReport JSON
document on stdout. Consumed by ``felix-admin-habits`` on the weekly
cron tick (Sunday 22:00 America/New_York). The agent prompt rewiring
that wires this helper into the cron tick lives in WP03 of the same
mission slice — by spec-kitty convention, multi-WP mission slices land
as a unit via ``spec-kitty merge``, so this module is not "dead code"
within the mission scope: it is the deterministic substrate WP03
consumes.

Per Felix Constitution Directive 6 this is the deterministic surface of
the weekly habit-report fix (kentonium3/kg-automation#562). Same Vikunja
state + same CLI arguments → byte-identical JSON output (NFR-004).

Authoritative contract:
``kitty-specs/vikunja-client-and-habits-weekly-report-01KTKSFT/contracts/query_active_habits_weekly.md``.

Spec requirements implemented here: FR-003, FR-004, FR-005, FR-006,
FR-011, FR-012, FR-013.

Public surface
--------------
Constants: ``HABITS_PROJECT_ID``, ``DAILY_REPEAT_AFTER``
Functions: ``parse_weekday_in_title``, ``classify_habit``,
    ``scheduled_days_for_window``, ``query_completion_events``,
    ``build_report``, ``main``
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional

from scripts.common.vikunja_client import VikunjaClient, VikunjaError

__all__ = [
    "HABITS_PROJECT_ID",
    "DAILY_REPEAT_AFTER",
    "WEEKDAY_PATTERN",
    "WEEKDAY_TO_ISO",
    "ISO_TO_PYTHON_WEEKDAY",
    "AGENT_NAME",
    "parse_weekday_in_title",
    "classify_habit",
    "scheduled_days_for_window",
    "query_completion_events",
    "build_report",
    "main",
]


HABITS_PROJECT_ID = 13
DAILY_REPEAT_AFTER = 86400  # seconds — Vikunja's encoding of "every 24 hours"

#: Matches weekday names in habit titles. Both the 3-letter abbreviation
#: (``Mon``) and the full word form (``Monday``, ``Wednesday``, ``Saturday``)
#: are supported. The full-word alternatives come first so the engine
#: prefers ``Wednesday`` over the prefix ``Wed`` when the title contains
#: the full word — necessary because ``Wednesday`` is not ``Wed`` + ``day``
#: and the simpler ``(Mon|Tue|Wed|...)(day)?`` regex fails the ``\b``
#: word-boundary check after the prefix.
WEEKDAY_PATTERN = re.compile(
    r"\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|"
    r"Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b",
    re.IGNORECASE,
)

#: Lowercase 3-letter prefix → canonical ISO upper-case 3-letter name.
#: ``parse_weekday_in_title`` truncates each match's lowercase form to its
#: first three characters before looking it up here, so both ``"mon"`` and
#: ``"monday"`` resolve to ``"MON"``.
WEEKDAY_TO_ISO = {
    "mon": "MON",
    "tue": "TUE",
    "wed": "WED",
    "thu": "THU",
    "fri": "FRI",
    "sat": "SAT",
    "sun": "SUN",
}

#: Canonical ISO weekday → ``datetime.weekday()`` integer (Mon=0..Sun=6).
ISO_TO_PYTHON_WEEKDAY = {
    "MON": 0,
    "TUE": 1,
    "WED": 2,
    "THU": 3,
    "FRI": 4,
    "SAT": 5,
    "SUN": 6,
}

#: Agent identity recorded by ``log_action.py``. The weekly cron tick is
#: owned by ``felix-admin-habits``; the helper records under that agent's
#: log stream so observability rolls up correctly.
AGENT_NAME = "felix-admin-habits"

_PAGE_SIZE = 200


# ---------------------------------------------------------------------------
# HabitClassifier (FR-004)
# ---------------------------------------------------------------------------


def parse_weekday_in_title(title: str) -> frozenset[str]:
    """Return the set of ISO weekday names mentioned in ``title``.

    Returns an empty :class:`frozenset` if no weekday names are present.
    Case-insensitive; matches both the 3-letter prefix (``Mon``) and the
    full word (``Monday``). Multiple weekdays in a single title are all
    returned (e.g., ``"Yoga — Mon and Wed"`` → ``{"MON", "WED"}``).
    """
    if not title:
        return frozenset()
    matches = WEEKDAY_PATTERN.findall(title)
    return frozenset(WEEKDAY_TO_ISO[m.lower()[:3]] for m in matches)


def classify_habit(task: dict) -> str:
    """Classify a Vikunja task into ``"daily"``, ``"weekday-in-title"``, or ``"other"``.

    Rules per spec FR-004 and ``data-model.md`` HabitClassifier:

    - ``repeat_after == DAILY_REPEAT_AFTER`` AND title has no weekday → ``"daily"``.
    - ``repeat_after == 0`` AND title contains at least one weekday → ``"weekday-in-title"``.
    - Anything else → ``"other"`` (filtered before reaching the report per FR-006).
    """
    repeat_after = task.get("repeat_after")
    title = task.get("title") or ""
    weekdays = parse_weekday_in_title(title)
    if repeat_after == DAILY_REPEAT_AFTER and not weekdays:
        return "daily"
    if repeat_after == 0 and weekdays:
        return "weekday-in-title"
    return "other"


def scheduled_days_for_window(
    kind: str,
    title: str,
    window_start: datetime,
    window_end: datetime,
) -> int:
    """Return scheduled-day count for ``kind`` over ``[window_start, window_end)``.

    - ``daily`` → number of complete days in the half-open window (7 for
      a standard 7-day window).
    - ``weekday-in-title`` → number of days in the window whose weekday
      matches any weekday parsed from ``title``.
    - ``other`` → 0 (these tasks are filtered before reaching scheduling).
    """
    if window_end <= window_start:
        return 0
    if kind == "daily":
        delta = window_end.date() - window_start.date()
        return delta.days
    if kind == "weekday-in-title":
        weekdays = parse_weekday_in_title(title)
        if not weekdays:
            return 0
        target_python_weekdays = {ISO_TO_PYTHON_WEEKDAY[w] for w in weekdays}
        count = 0
        cursor = window_start
        while cursor < window_end:
            if cursor.weekday() in target_python_weekdays:
                count += 1
            cursor = cursor + timedelta(days=1)
        return count
    return 0


# ---------------------------------------------------------------------------
# Vikunja query loop + aggregation (FR-003, FR-005, FR-006)
# ---------------------------------------------------------------------------


def _parse_done_at(value: object) -> Optional[datetime]:
    """Parse a Vikunja ``done_at`` ISO 8601 timestamp.

    Returns ``None`` if the value is missing, empty, or unparseable;
    Vikunja occasionally emits the zero-value sentinel
    (``"0001-01-01T00:00:00Z"``) which we also treat as "no completion".
    """
    if not value or not isinstance(value, str):
        return None
    if value.startswith("0001-01-01"):
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _paginate(
    client: VikunjaClient,
    *,
    path: str,
    base_params: dict,
) -> Iterable[dict]:
    """Yield tasks across paginated Vikunja responses.

    Stops when a page returns fewer than :data:`_PAGE_SIZE` items (or an
    empty/non-list payload). The Vikunja list endpoints return JSON arrays
    directly.
    """
    page = 1
    while True:
        params = dict(base_params)
        params["page"] = str(page)
        params["per_page"] = str(_PAGE_SIZE)
        response = client.get(path, params=params)
        if not isinstance(response, list) or not response:
            return
        for task in response:
            yield task
        if len(response) < _PAGE_SIZE:
            return
        page += 1


def query_completion_events(
    client: VikunjaClient,
    *,
    window_start: datetime,
    window_end: datetime,
    prior_window_start: Optional[datetime],
    prior_window_end: Optional[datetime],
) -> dict[str, dict]:
    """Fetch project-13 tasks via the client, classify, and aggregate counts.

    Returns a dict keyed by habit title. Each value carries:

    - ``kind``: ``"daily"`` or ``"weekday-in-title"``.
    - ``title``: canonical habit title (same as the dict key).
    - ``current_count``: number of ``done_at`` events in the current window.
    - ``prior_count``: number of ``done_at`` events in the prior window
      (0 if ``prior_window_start`` / ``prior_window_end`` is ``None``).

    ``"other"``-classified tasks are filtered out per FR-006 before
    aggregation; the cardiac-lab one-off never appears.
    """
    events: dict[str, dict] = {}

    done_path = f"/projects/{HABITS_PROJECT_ID}/tasks"
    for task in _paginate(
        client,
        path=done_path,
        base_params={"filter": "done=true"},
    ):
        kind = classify_habit(task)
        if kind == "other":
            continue
        title = task.get("title") or ""
        done_at = _parse_done_at(task.get("done_at"))
        bucket = events.setdefault(
            title,
            {"kind": kind, "title": title, "current_count": 0, "prior_count": 0},
        )
        if done_at is None:
            # Done flag set but no parseable done_at; warn and continue.
            print(
                f"warning: skipping done task without parseable done_at: "
                f"id={task.get('id')!r} title={title!r}",
                file=sys.stderr,
            )
            continue
        if window_start <= done_at < window_end:
            bucket["current_count"] += 1
        if (
            prior_window_start is not None
            and prior_window_end is not None
            and prior_window_start <= done_at < prior_window_end
        ):
            bucket["prior_count"] += 1

    # Active (not-done) pass — guarantees every habit shows up even if
    # the operator never completed it within either window. Vikunja's
    # ``done=false`` filter returns currently-open instances of each
    # recurring habit (the next due date).
    for task in _paginate(
        client,
        path=done_path,
        base_params={"filter": "done=false"},
    ):
        kind = classify_habit(task)
        if kind == "other":
            continue
        title = task.get("title") or ""
        events.setdefault(
            title,
            {"kind": kind, "title": title, "current_count": 0, "prior_count": 0},
        )

    return events


# ---------------------------------------------------------------------------
# Report assembly (FR-005)
# ---------------------------------------------------------------------------


def _iso_utc(dt: datetime) -> str:
    """Render ``dt`` as a Vikunja-style ISO 8601 string ending in ``Z``."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _percent(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(100.0 * numerator / denominator, 1)


def _primary_weekday_for_title(title: str) -> int:
    weekdays = parse_weekday_in_title(title)
    if not weekdays:
        return 7  # sort after Sun; never reached for valid weekday-in-title rows
    return min(ISO_TO_PYTHON_WEEKDAY[w] for w in weekdays)


def _sort_key(habit: dict) -> tuple[int, int, str]:
    kind = habit["habit_kind"]
    kind_rank = 0 if kind == "daily" else 1
    if kind == "weekday-in-title":
        return (kind_rank, _primary_weekday_for_title(habit["habit_title"]), habit["habit_title"])
    return (kind_rank, 0, habit["habit_title"])


def build_report(
    events_by_title: dict[str, dict],
    *,
    window_start: datetime,
    window_end: datetime,
    prior_window_start: Optional[datetime],
    prior_window_end: Optional[datetime],
) -> dict:
    """Assemble the WeeklyHabitReport JSON-ready dict.

    Caps ``completed_events_current`` / ``completed_events_prior`` at
    their scheduled-day counts so percentages stay in ``[0, 100]`` even
    if Vikunja records duplicate completions (validation invariant 1 in
    ``contracts/weekly_report_payload.md``).
    """
    include_baseline = (
        prior_window_start is not None and prior_window_end is not None
    )

    habits: list[dict] = []
    for title, bucket in events_by_title.items():
        kind = bucket["kind"]
        scheduled_current = scheduled_days_for_window(
            kind, title, window_start, window_end
        )
        completed_current = min(bucket["current_count"], scheduled_current)
        if include_baseline:
            scheduled_prior = scheduled_days_for_window(
                kind, title, prior_window_start, prior_window_end
            )
            completed_prior = min(bucket["prior_count"], scheduled_prior)
            percent_prior: Optional[float] = _percent(
                completed_prior, scheduled_prior
            )
        else:
            scheduled_prior = None
            completed_prior = None
            percent_prior = None
        habits.append(
            {
                "habit_title": title,
                "habit_kind": kind,
                "scheduled_days_current": scheduled_current,
                "completed_events_current": completed_current,
                "percent_current": _percent(completed_current, scheduled_current),
                "scheduled_days_prior": scheduled_prior,
                "completed_events_prior": completed_prior,
                "percent_prior": percent_prior,
            }
        )

    habits.sort(key=_sort_key)

    total_scheduled_current = sum(h["scheduled_days_current"] for h in habits)
    total_completed_current = sum(h["completed_events_current"] for h in habits)
    overall_percent_current = _percent(
        total_completed_current, total_scheduled_current
    )

    if include_baseline:
        total_scheduled_prior = sum(
            (h["scheduled_days_prior"] or 0) for h in habits
        )
        total_completed_prior = sum(
            (h["completed_events_prior"] or 0) for h in habits
        )
        overall_percent_prior: Optional[float] = _percent(
            total_completed_prior, total_scheduled_prior
        )
        prior_window_start_iso: Optional[str] = _iso_utc(prior_window_start)
        prior_window_end_iso: Optional[str] = _iso_utc(prior_window_end)
    else:
        overall_percent_prior = None
        prior_window_start_iso = None
        prior_window_end_iso = None

    return {
        "window_start_iso": _iso_utc(window_start),
        "window_end_iso": _iso_utc(window_end),
        "prior_window_start_iso": prior_window_start_iso,
        "prior_window_end_iso": prior_window_end_iso,
        "habits": habits,
        "overall_percent_current": overall_percent_current,
        "overall_percent_prior": overall_percent_prior,
    }


# ---------------------------------------------------------------------------
# log_action wiring (FR-013)
# ---------------------------------------------------------------------------


def _default_log_action_path() -> Path:
    return (
        Path(__file__).resolve().parent.parent
        / "openclaw"
        / "observation"
        / "log_action.py"
    )


def _resolve_log_action_path() -> Path:
    env_override = os.environ.get("LOG_ACTION_PATH")
    if env_override:
        return Path(env_override)
    return _default_log_action_path()


def _emit_log_action(
    *,
    category: str,
    action: str,
    target: str,
    outcome: str,
    context: dict,
) -> None:
    """Subprocess-out to ``log_action.py``. Failures are swallowed.

    Following the precedent in ``scripts/inbox/handle_marker_cleanup.py``:
    log-infra failure is reported to stderr but does NOT propagate to the
    helper's exit code (FR-013 wires observability; it does not gate
    behaviour).
    """
    log_action_bin = _resolve_log_action_path()
    if not log_action_bin.exists():
        print(
            f"warning: log_action.py not found at {log_action_bin}",
            file=sys.stderr,
        )
        return
    cmd = [
        "python3",
        str(log_action_bin),
        "--agent",
        AGENT_NAME,
        "--category",
        category,
        "--action",
        action,
        "--target",
        target,
        "--outcome",
        outcome,
        "--context",
        json.dumps(context),
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(
            f"warning: log_action.py invocation failed: {exc}",
            file=sys.stderr,
        )
        return
    if proc.returncode != 0:
        print(
            f"warning: log_action.py exited {proc.returncode}: "
            f"stderr={proc.stderr.strip()!r}",
            file=sys.stderr,
        )


# ---------------------------------------------------------------------------
# CLI (FR-003)
# ---------------------------------------------------------------------------


def _parse_args(argv: Optional[list[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="query_active_habits_weekly",
        description=(
            "Emit a weekly habit-completion report for Vikunja project 13. "
            "Output is JSON on stdout; exit code 0 on success, 3 on Vikunja "
            "API failure."
        ),
    )
    parser.add_argument(
        "--window-end",
        default=None,
        metavar="YYYY-MM-DD",
        help=(
            "End of the current window (exclusive). Defaults to today (UTC). "
            "Must be an ISO 8601 date."
        ),
    )
    parser.add_argument(
        "--window-days",
        type=int,
        default=7,
        help="Length of each window in days (default: 7).",
    )
    parser.add_argument(
        "--include-baseline",
        dest="include_baseline",
        action="store_true",
        default=True,
        help="Include the prior-window baseline (default).",
    )
    parser.add_argument(
        "--no-include-baseline",
        dest="include_baseline",
        action="store_false",
        help="Omit the prior-window baseline; prior fields will be null.",
    )
    return parser.parse_args(argv)


def _resolve_windows(args: argparse.Namespace) -> tuple[
    datetime, datetime, Optional[datetime], Optional[datetime]
]:
    if args.window_days <= 0:
        raise ValueError(
            f"--window-days must be positive, got {args.window_days!r}"
        )
    if args.window_end is None:
        today = datetime.now(timezone.utc).date()
    else:
        try:
            today = datetime.strptime(args.window_end, "%Y-%m-%d").date()
        except ValueError as exc:
            raise ValueError(
                f"--window-end must be YYYY-MM-DD, got {args.window_end!r}: {exc}"
            ) from exc
    window_end = datetime(
        today.year, today.month, today.day, tzinfo=timezone.utc
    )
    window_start = window_end - timedelta(days=args.window_days)
    if args.include_baseline:
        prior_window_end = window_start
        prior_window_start = prior_window_end - timedelta(days=args.window_days)
    else:
        prior_window_end = None
        prior_window_start = None
    return window_start, window_end, prior_window_start, prior_window_end


def main(argv: Optional[list[str]] = None) -> int:
    """Run the helper. Returns the process exit code.

    Exit codes (per ``contracts/query_active_habits_weekly.md``):

    - 0: success; JSON report on stdout.
    - 2: usage error (argparse handles this directly via ``SystemExit``).
    - 3: Vikunja API failure (``VikunjaError`` raised by the client).
    - 4: internal error (unexpected exception). Should not happen.
    """
    try:
        args = _parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 0

    try:
        window_start, window_end, prior_window_start, prior_window_end = (
            _resolve_windows(args)
        )
    except ValueError as exc:
        print(f"usage error: {exc}", file=sys.stderr)
        return 2

    try:
        client = VikunjaClient()
        events = query_completion_events(
            client,
            window_start=window_start,
            window_end=window_end,
            prior_window_start=prior_window_start,
            prior_window_end=prior_window_end,
        )
        report = build_report(
            events,
            window_start=window_start,
            window_end=window_end,
            prior_window_start=prior_window_start,
            prior_window_end=prior_window_end,
        )
        sys.stdout.write(json.dumps(report))
        sys.stdout.write("\n")
        sys.stdout.flush()
        _emit_log_action(
            category="routine",
            action="weekly_report_generated",
            target=f"/projects/{HABITS_PROJECT_ID}/tasks",
            outcome="success",
            context={
                "window_start_iso": report["window_start_iso"],
                "window_end_iso": report["window_end_iso"],
                "habit_count": len(report["habits"]),
                "overall_percent_current": report["overall_percent_current"],
            },
        )
        return 0
    except VikunjaError as exc:
        print(f"{type(exc).__name__}: {exc.path}", file=sys.stderr)
        _emit_log_action(
            category="error",
            action="weekly_report_failed",
            target=getattr(exc, "path", "<unknown>"),
            outcome="error",
            context={
                "error_class": type(exc).__name__,
                "error_detail": str(exc),
                "path": getattr(exc, "path", "<unknown>"),
            },
        )
        return 3
    except Exception:  # noqa: BLE001 — broad: surface as internal-error exit
        print("internal error", file=sys.stderr)
        return 4


if __name__ == "__main__":  # pragma: no cover - module entry
    sys.exit(main())
