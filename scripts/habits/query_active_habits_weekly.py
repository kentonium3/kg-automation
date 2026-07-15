"""Weekly habit-completion report helper.

Originally introduced under mission
``vikunja-client-and-habits-weekly-report-01KTKSFT``; rewritten in
mission ``trustworthy-weekly-habit-report-01KV4GZ7`` (issue
kentonium3/kg-automation#605) to read completion history from the
canonical ``habits-history.jsonl`` (via :mod:`scripts.habits.history`)
instead of Vikunja's volatile ``done_at`` field.

Per Felix Constitution Directive 6 this is the deterministic surface of
the weekly habit-report fix. Same canonical state + same Vikunja
current-state response + same CLI arguments → byte-identical JSON
output AND byte-identical ``rendered_text`` (NFR-001, NFR-004).

The Vikunja side is retained only for **current-state** habit-list
metadata (titles + ``repeat_after`` for classification). Completion
history is read exclusively from the canonical JSONL store via the
IC-01 wrapper. The IC-03 architectural test in WP03 ratchets this
boundary — this file is on the current-state allowlist but is NOT
allowed to read ``done_at`` for historical purposes.

Authoritative contracts:

- ``kitty-specs/trustworthy-weekly-habit-report-01KV4GZ7/contracts/weekly_helper_cli.md`` (CLI surface)
- ``kitty-specs/vikunja-client-and-habits-weekly-report-01KTKSFT/contracts/weekly_report_payload.md`` (JSON shape — preserved per FR-007 / NFR-005; ``rendered_text`` added additively per FR-005)

Public surface
--------------
Constants: ``DAILY_REPEAT_AFTER``
Functions: ``parse_weekday_in_title``, ``classify_habit``,
    ``scheduled_days_for_window``, ``query_completion_events``,
    ``build_report``, ``main``

Habit project id (mission deterministic-cron-hardening-01KXA4PX, #723;
mission vikunja-reference-seam-01KXK68Z, #748/#745)
------------------------------------------------------------------------
The habit project id is resolved on demand via
:func:`_resolve_habits_project_id`, which reads
:func:`scripts.common.vikunja_scope.habit_project_id` (in turn sourced
from the reference registry ``vikunja_refs.json``) — never hardcoded and
never mirrored into a module-level constant, so the one source is the
registry (FR-002/FR-005/FR-008). The label selector fetch strategy is out
of scope here (deferred to #716) — if the scope module ever reports a
label selector (``habit_project_id()`` returns ``None``), the resolver
raises :class:`NotImplementedError` rather than silently misbehaving.
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
from zoneinfo import ZoneInfo

from scripts.common import vikunja_scope
from scripts.common.vikunja_client import VikunjaClient, VikunjaError
from scripts.habits import history

__all__ = [
    "DAILY_REPEAT_AFTER",
    "WEEKDAY_PATTERN",
    "WEEKDAY_TO_ISO",
    "ISO_TO_PYTHON_WEEKDAY",
    "AGENT_NAME",
    "REPORT_TZ",
    "parse_weekday_in_title",
    "classify_habit",
    "scheduled_days_for_window",
    "query_completion_events",
    "build_report",
    "main",
]


#: Canonical reporting timezone for habit windowing and rendered labels.
REPORT_TZ: ZoneInfo = ZoneInfo("America/New_York")


def _resolve_habits_project_id() -> int:
    """Resolve the habit project id from the shared scope config (#723).

    Raises :class:`NotImplementedError` if the configured habit selector is
    a label form — the label fetch strategy is out of scope for this
    mission (see #716). This makes the boundary explicit rather than
    silently misbehaving (e.g. fetching ``/projects/None/tasks``).
    """
    project_id = vikunja_scope.habit_project_id()
    if project_id is None:
        raise NotImplementedError(
            "label habit selector not supported yet — see #716"
        )
    return project_id


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


def _completed_in_window_for_habit(
    *,
    kind: str,
    title: str,
    habit_id: int,
    window_start: datetime,
    window_end: datetime,
) -> int:
    """Return dedup-by-date completion count for ``habit_id`` in the window.

    Routes through :func:`scripts.habits.history.scheduled_vs_completed_for_habit`
    so the canonical-read invariant (FR-002) is honored even by the helper's
    internal aggregation path. The wrapper handles dedup-by-date and clamping;
    we discard the scheduled half and return only the completed count because
    we already compute scheduled here via :func:`scheduled_days_for_window`.

    Falls back to 0 when scheduled is 0 (e.g. weekday-in-title habit whose
    target weekday isn't in the window): the wrapper requires
    ``scheduled_days_count > 0`` so we can't call it; a habit with no
    scheduled occurrences in the window contributes 0 to the report
    regardless.
    """
    scheduled = scheduled_days_for_window(kind, title, window_start, window_end)
    if scheduled <= 0:
        return 0
    _, completed = history.scheduled_vs_completed_for_habit(
        habit_id=habit_id,
        window_start=window_start,
        window_end=window_end,
        scheduled_days_count=scheduled,
    )
    return completed


def query_completion_events(
    client: VikunjaClient,
    *,
    window_start: datetime,
    window_end: datetime,
    prior_window_start: Optional[datetime],
    prior_window_end: Optional[datetime],
) -> dict[str, dict]:
    """Fetch the project-13 habit list and aggregate canonical-store counts.

    Returns a dict keyed by habit title. Each value carries:

    - ``kind``: ``"daily"`` or ``"weekday-in-title"``.
    - ``title``: canonical habit title (same as the dict key).
    - ``current_count``: dedup-by-date completion count from
      ``habits-history.jsonl`` in the current window.
    - ``prior_count``: same for the prior window (0 if
      ``prior_window_start`` / ``prior_window_end`` is ``None``).

    The Vikunja query is intentionally **current-state only**: titles +
    ``repeat_after`` for classification. Completion counts come from the
    canonical store via :mod:`scripts.habits.history` (FR-002). The
    WP03 architectural test allowlists this file for the current-state
    Vikunja call; it does NOT allow ``task.get("done_at")`` reads —
    those have been removed from this module.

    ``"other"``-classified tasks are filtered out before aggregation
    (the cardiac-lab one-off and any non-recurring/non-weekday tasks
    never appear in the report).
    """
    events: dict[str, dict] = {}

    tasks_path = f"/projects/{_resolve_habits_project_id()}/tasks"
    # No ``filter`` param — we want every habit in project 13 regardless
    # of current-tick done flag; the report enumerates each habit and
    # consults the canonical store for completion counts.
    for task in _paginate(client, path=tasks_path, base_params={}):
        kind = classify_habit(task)
        if kind == "other":
            continue
        title = task.get("title") or ""
        habit_id = task.get("id")
        if not isinstance(habit_id, int):
            continue
        if title in events:
            # Vikunja may return the same habit twice across page boundaries
            # in edge cases; keep the first-seen bucket.
            continue

        current_count = _completed_in_window_for_habit(
            kind=kind,
            title=title,
            habit_id=habit_id,
            window_start=window_start,
            window_end=window_end,
        )
        if prior_window_start is not None and prior_window_end is not None:
            prior_count = _completed_in_window_for_habit(
                kind=kind,
                title=title,
                habit_id=habit_id,
                window_start=prior_window_start,
                window_end=prior_window_end,
            )
        else:
            prior_count = 0

        events[title] = {
            "kind": kind,
            "title": title,
            "current_count": current_count,
            "prior_count": prior_count,
        }

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


def _emit_anomaly_log_action(
    *,
    habit_title: str,
    habit_kind: str,
    window: str,
    scheduled_days: int,
    raw_count: int,
    capped_count: int,
    window_start: datetime,
    window_end: datetime,
) -> None:
    """Emit a ``weekly_report_anomaly`` log_action for one capped cell.

    Called by :func:`build_report` whenever Vikunja returns more completion
    events than the scheduled-day count for a habit (validation invariant
    1 in ``contracts/weekly_report_payload.md``). One emission per
    (habit, window) cell — no batching. Context payload is redaction-safe:
    no Vikunja body content, only the habit title, classification, window
    boundaries, and the raw/capped integers.
    """
    _emit_log_action(
        category="flagged",
        action="weekly_report_anomaly",
        target=f"/projects/{_resolve_habits_project_id()}/tasks",
        outcome="capped",
        context={
            "habit_title": habit_title,
            "habit_kind": habit_kind,
            "window": window,
            "scheduled_days": scheduled_days,
            "raw_count": raw_count,
            "capped_count": capped_count,
            "window_start_iso": _iso_utc(window_start),
            "window_end_iso": _iso_utc(window_end),
        },
    )


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
    ``contracts/weekly_report_payload.md``). Each capped cell emits a
    ``weekly_report_anomaly`` log_action (one per (habit, window) cell —
    no batching) so operators retain the required audit signal.
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
        raw_current = bucket["current_count"]
        completed_current = min(raw_current, scheduled_current)
        if raw_current > scheduled_current:
            _emit_anomaly_log_action(
                habit_title=title,
                habit_kind=kind,
                window="current",
                scheduled_days=scheduled_current,
                raw_count=raw_current,
                capped_count=completed_current,
                window_start=window_start,
                window_end=window_end,
            )
        if include_baseline:
            scheduled_prior = scheduled_days_for_window(
                kind, title, prior_window_start, prior_window_end
            )
            raw_prior = bucket["prior_count"]
            completed_prior = min(raw_prior, scheduled_prior)
            if raw_prior > scheduled_prior:
                _emit_anomaly_log_action(
                    habit_title=title,
                    habit_kind=kind,
                    window="prior",
                    scheduled_days=scheduled_prior,
                    raw_count=raw_prior,
                    capped_count=completed_prior,
                    window_start=prior_window_start,
                    window_end=prior_window_end,
                )
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

    report = {
        "window_start_iso": _iso_utc(window_start),
        "window_end_iso": _iso_utc(window_end),
        "prior_window_start_iso": prior_window_start_iso,
        "prior_window_end_iso": prior_window_end_iso,
        "habits": habits,
        "overall_percent_current": overall_percent_current,
        "overall_percent_prior": overall_percent_prior,
    }
    # ``rendered_text`` is a pure function of all other fields; same JSON
    # → byte-identical text (NFR-004). Computed last so it observes the
    # final sorted/clamped values rather than intermediate state.
    report["rendered_text"] = _render_whatsapp_text(
        report,
        window_start=window_start,
        window_end=window_end,
    )
    return report


# ---------------------------------------------------------------------------
# Rendered text (FR-005 / NFR-004) + window label (FR-006)
# ---------------------------------------------------------------------------


def _format_window_label(window_start: datetime, window_end: datetime) -> str:
    """Format a 7-day inclusive window label for the rendered message.

    ``window_end`` here is the **exclusive** upper bound used internally
    (e.g. next Monday 00:00 ET); the label converts it to the inclusive
    last-day form humans expect (the prior Sunday).

    Examples:

    - Mon Jun 8 → Mon Jun 15 (exclusive)  → ``"Jun 8–14"`` (same month)
    - Mon Jul 28 → Mon Aug 4 (exclusive)  → ``"Jul 28 – Aug 3"`` (cross-month)

    Uses ``window_start`` in :data:`REPORT_TZ` for month-equality so DST
    or UTC-supplied bounds don't accidentally cross-month the label.
    """
    start_local = window_start.astimezone(REPORT_TZ)
    last_day_local = (window_end - timedelta(days=1)).astimezone(REPORT_TZ)
    month_abbr = start_local.strftime("%b")
    if start_local.month == last_day_local.month:
        return f"{month_abbr} {start_local.day}–{last_day_local.day}"
    end_month_abbr = last_day_local.strftime("%b")
    return (
        f"{month_abbr} {start_local.day} – "
        f"{end_month_abbr} {last_day_local.day}"
    )


def _arrow_for_delta(current_pct: float, prior_pct: Optional[float]) -> str:
    """Return the WhatsApp arrow glyph for a current-vs-prior comparison.

    Uses the same percent units the report exposes (0–100 floats from
    :func:`_percent`). The 0.5-percentage-point epsilon prevents arrow
    flicker on essentially-equal rates.
    """
    if prior_pct is None:
        return ""
    delta = current_pct - prior_pct
    if delta > 0.5:
        return "↑"  # ↑
    if delta < -0.5:
        return "↓"  # ↓
    return ""


def _render_pct(value: float) -> str:
    """Round to integer percent without trailing decimal."""
    return f"{int(round(value))}"


def _render_whatsapp_text(
    report: dict,
    *,
    window_start: datetime,
    window_end: datetime,
) -> str:
    """Render the WeeklyHabitReport JSON dict to the canonical WhatsApp text.

    Pure function: same ``report`` dict + same window bounds → byte-identical
    output (NFR-004). The identity-attribution line is the agent's
    responsibility (FR-010) and is NOT rendered here.
    """
    short_window = _format_window_label(window_start, window_end)
    lines: list[str] = []
    lines.append(f"*This week* ({short_window}):")
    lines.append("")
    for habit in report["habits"]:
        current_pct = habit["percent_current"]
        prior_pct = habit.get("percent_prior")
        arrow = _arrow_for_delta(current_pct, prior_pct)
        if prior_pct is None:
            row = f"{habit['habit_title']} — {_render_pct(current_pct)}%"
        else:
            row = (
                f"{habit['habit_title']} — {_render_pct(current_pct)}% "
                f"(was {_render_pct(prior_pct)}%)"
            )
        if arrow:
            row = f"{row} {arrow}"
        lines.append(row)
    lines.append("")
    overall_current = report["overall_percent_current"]
    overall_prior = report.get("overall_percent_prior")
    overall_arrow = _arrow_for_delta(overall_current, overall_prior)
    if overall_prior is None:
        overall_line = f"*Overall: {_render_pct(overall_current)}%*"
    else:
        overall_line = (
            f"*Overall: {_render_pct(overall_current)}%* "
            f"(was {_render_pct(overall_prior)}%)"
        )
    if overall_arrow:
        overall_line = f"{overall_line} {overall_arrow}"
    lines.append(overall_line)
    return "\n".join(lines)


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


def _parse_as_of(value: str) -> datetime:
    """Argparse type converter: parse a tz-aware ISO 8601 datetime string.

    Accepts the same shapes :func:`datetime.fromisoformat` does, plus the
    trailing ``Z`` UTC marker. Rejects naive datetimes with
    :class:`argparse.ArgumentTypeError` so the helper never silently
    windows against an ambiguous wall clock (DST-safe testing).
    """
    if not isinstance(value, str) or not value:
        raise argparse.ArgumentTypeError(
            "--as-of must be a non-empty ISO 8601 datetime string"
        )
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"--as-of must be ISO 8601, got {value!r}: {exc}"
        ) from exc
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError(
            "--as-of must be tz-aware (include an offset, e.g. -04:00)"
        )
    return parsed


def _now_in_et() -> datetime:
    """Return the current wall-clock time in :data:`REPORT_TZ`.

    Thin wrapper so tests can monkeypatch a fixed instant without
    touching the whole module's time source.
    """
    return datetime.now(REPORT_TZ)


def _parse_args(argv: Optional[list[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="query_active_habits_weekly",
        description=(
            "Emit a weekly habit-completion report for Vikunja project 13. "
            "Reads canonical habits-history.jsonl for completion counts; "
            "does NOT query Vikunja done_at for history (kg-automation#605). "
            "Output is JSON on stdout; exit code 0 on success, 3 on Vikunja "
            "API failure."
        ),
    )
    parser.add_argument(
        "--as-of",
        dest="as_of",
        type=_parse_as_of,
        default=None,
        metavar="ISO_DATETIME",
        help=(
            "Reference datetime (ISO 8601, tz-aware) for the report window. "
            "When supplied, the current window is "
            "[as_of - 7 days @ 00:00 ET, as_of @ 00:00 ET) regardless of "
            "--window-end / --window-days. Used by tests for "
            "deterministic golden-week fixtures."
        ),
    )
    parser.add_argument(
        "--output",
        choices=("json", "text"),
        default="json",
        help=(
            "Output format. 'json' (default) emits the full "
            "WeeklyHabitReport JSON. 'text' emits only the rendered_text "
            "field on stdout — for the WhatsApp message body."
        ),
    )
    parser.add_argument(
        "--window-end",
        default=None,
        metavar="YYYY-MM-DD",
        help=(
            "[Legacy] End of the current window (exclusive). Defaults to "
            "today (UTC). Ignored when --as-of is supplied."
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

    # FR-006 / R-04: the canonical window is 7 days in ET, anchored to ET
    # midnight (not the wall time) so the same window is computed regardless
    # of what hour the cron fires. ``--as-of`` lets tests inject a
    # deterministic instant; production resolves through :func:`_now_in_et`.
    # The legacy ``--window-end`` branch (UTC-anchored) is retained for
    # compatibility with existing call sites that still pass the prior
    # mission's flag shape; explicit ``--window-end`` wins over the
    # ET-anchored default but ``--as-of`` wins over both.
    if args.as_of is not None:
        anchor_dt = args.as_of
        use_et = True
    elif args.window_end is None:
        anchor_dt = _now_in_et()
        use_et = True
    else:
        use_et = False
        try:
            today = datetime.strptime(args.window_end, "%Y-%m-%d").date()
        except ValueError as exc:
            raise ValueError(
                f"--window-end must be YYYY-MM-DD, got {args.window_end!r}: {exc}"
            ) from exc
        window_end = datetime(
            today.year, today.month, today.day, tzinfo=timezone.utc
        )

    if use_et:
        anchor_et = anchor_dt.astimezone(REPORT_TZ).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        window_end = anchor_et
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
        if args.output == "text":
            sys.stdout.write(report["rendered_text"])
            sys.stdout.write("\n")
        else:
            sys.stdout.write(json.dumps(report))
            sys.stdout.write("\n")
        sys.stdout.flush()
        _emit_log_action(
            category="routine",
            action="weekly_report_generated",
            target=f"/projects/{_resolve_habits_project_id()}/tasks",
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
