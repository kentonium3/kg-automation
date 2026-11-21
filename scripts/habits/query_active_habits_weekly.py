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
metadata (titles + the ``repeat`` rule for classification, mission
felix-rrule-adaptation #1111 FR-012). Completion
history is read exclusively from the canonical JSONL store via the
IC-01 wrapper. The IC-03 architectural test in WP03 ratchets this
boundary — this file is on the current-state allowlist but is NOT
allowed to read ``done_at`` for historical purposes.

Authoritative contracts:

- ``kitty-specs/trustworthy-weekly-habit-report-01KV4GZ7/contracts/weekly_helper_cli.md`` (CLI surface)
- ``kitty-specs/vikunja-client-and-habits-weekly-report-01KTKSFT/contracts/weekly_report_payload.md`` (JSON shape — preserved per FR-007 / NFR-005; ``rendered_text`` added additively per FR-005)

Public surface
--------------
Constants: ``HABIT_KINDS``, ``UNKNOWN_SCHEDULE_TEXT``
Functions: ``classify_habit``, ``scheduled_days_for_window``,
    ``query_completion_events``, ``build_report``, ``main``

Classification and scheduled days (FR-012, #1111)
-------------------------------------------------
Habits are classified from their Vikunja ``repeat`` rule (list bodies carry
``repeat`` but not ``repeats_rrule``), never from ``repeat_after`` (dead on
the RRULE server) or weekday words in the title. Plain daily
(``FREQ=DAILY;INTERVAL=1``) and plain weekly-by-day
(``FREQ=WEEKLY;INTERVAL=1;BYDAY=...``, nothing else) rules are counted
locally. Any other rule's scheduled days are ``None`` and render as
:data:`UNKNOWN_SCHEDULE_TEXT` — never a guessed 0.

The server's occurrence preview is deliberately not used. In vikunja-harness
d7e202228 it steps from ``max(now, due_date)``
(``pkg/models/task_next_occurrence_engine.go:205-212, 429-440``;
``pkg/models/task_occurrences.go:176, 189-202``), so it cannot evaluate the
report's windows, which are always in the past. Re-anchoring it would also
shift an interval rule's phase (review cycle 2, #1111).

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
import subprocess
import sys
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

from scripts.common import vikunja_rule, vikunja_scope
from scripts.common.vikunja_client import VikunjaClient, VikunjaError
from scripts.habits import history

__all__ = [
    "AGENT_NAME",
    "HABIT_KINDS",
    "REPORT_TZ",
    "RULE_WEEKDAY_TO_PYTHON",
    "UNKNOWN_SCHEDULE_TEXT",
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


#: Report kinds, in report sort order. ``other`` (no rule) is filtered out.
HABIT_KINDS: tuple[str, ...] = ("daily", "weekly-by-day", "rule")

#: Vikunja ``by_day`` token -> ``datetime.weekday()`` (Mon=0..Sun=6).
RULE_WEEKDAY_TO_PYTHON: dict[str, int] = {
    "mo": 0,
    "tu": 1,
    "we": 2,
    "th": 3,
    "fr": 4,
    "sa": 5,
    "su": 6,
}

#: Rendered in place of a percentage when a habit's scheduled days are unknown.
UNKNOWN_SCHEDULE_TEXT = "scheduled: unknown (rule preview unavailable)"

#: Agent identity recorded by ``log_action.py``. The weekly cron tick is
#: owned by ``felix-admin-habits``; the helper records under that agent's
#: log stream so observability rolls up correctly.
AGENT_NAME = "felix-admin-habits"

_PAGE_SIZE = 200


# ---------------------------------------------------------------------------
# HabitClassifier (FR-004)
# ---------------------------------------------------------------------------


def classify_habit(task: Mapping[str, Any]) -> str:
    """Classify a Vikunja task from its ``repeat`` rule (FR-012).

    - ``FREQ=DAILY;INTERVAL=1`` and nothing else -> ``"daily"``.
    - ``FREQ=WEEKLY`` with a ``BYDAY`` list -> ``"weekly-by-day"``.
    - any other rule -> ``"rule"`` (scheduled days unknown).
    - no rule -> ``"other"`` (filtered before the report, as before; this
      includes Done habits whose rule is gone, e.g. tasks 75–77, C-008).
    """
    rule = vikunja_rule.normalise(task.get("repeat"))
    if rule is None:
        return "other"
    if rule == {"freq": "daily", "interval": 1}:
        return "daily"
    if rule["freq"] == "weekly" and rule.get("by_day"):
        return "weekly-by-day"
    return "rule"


def _local_weekdays(rule: Mapping[str, Any]) -> set[int] | None:
    """Python weekdays of a plain ``FREQ=WEEKLY;INTERVAL=1;BYDAY=..`` rule.

    ``None`` when the rule has anything else (COUNT, UNTIL, another BY*
    part, a non-default WKST, an interval > 1, or an ordinal BYDAY such as
    ``1mo``): those cannot be counted locally, so they are unknown.
    """
    if set(rule) - {"freq", "interval", "by_day"} or rule.get("interval") != 1:
        return None
    days = rule.get("by_day") or []
    if not days or any(d not in RULE_WEEKDAY_TO_PYTHON for d in days):
        return None
    return {RULE_WEEKDAY_TO_PYTHON[d] for d in days}


def scheduled_days_for_window(
    kind: str,
    task: Mapping[str, Any],
    window_start: datetime,
    window_end: datetime,
) -> int | None:
    """Return the scheduled-day count for ``task`` over ``[window_start, window_end)``.

    - ``daily`` -> number of days in the half-open window (7 for a week).
    - ``weekly-by-day`` -> number of window days whose weekday is in
      ``BYDAY``, computed locally when the rule is plain
      ``FREQ=WEEKLY;INTERVAL=1;BYDAY=...``; otherwise ``None``.
    - ``rule`` -> ``None`` (unknown; see the module docstring for why the
      server preview is not used).
    - ``other`` -> 0 (filtered before scheduling).
    """
    if window_end <= window_start:
        return 0
    if kind == "daily":
        return (window_end.date() - window_start.date()).days
    if kind not in ("weekly-by-day", "rule"):
        return 0
    rule = vikunja_rule.normalise(task.get("repeat"))
    if rule is None:
        return 0
    weekdays = _local_weekdays(rule) if kind == "weekly-by-day" else None
    if weekdays is None:
        return None
    count = 0
    cursor = window_start
    while cursor < window_end:
        if cursor.weekday() in weekdays:
            count += 1
        cursor = cursor + timedelta(days=1)
    return count


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
    scheduled: int | None,
    habit_id: int,
    window_start: datetime,
    window_end: datetime,
) -> int | None:
    """Return dedup-by-date completion count for ``habit_id`` in the window.

    Routes through :func:`scripts.habits.history.scheduled_vs_completed_for_habit`
    so the canonical-read invariant (FR-002) is honored even by the helper's
    internal aggregation path. The wrapper handles dedup-by-date and clamping;
    we discard the scheduled half and return only the completed count because
    the scheduled count was computed by :func:`scheduled_days_for_window`.

    Returns 0 when nothing is scheduled (the wrapper requires
    ``scheduled_days_count > 0``), and ``None`` when the scheduled count is
    unknown: without it the completed count cannot be clamped, so it is not
    reported either.
    """
    if scheduled is None:
        return None
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

    - ``kind``: ``"daily"``, ``"weekly-by-day"`` or ``"rule"``.
    - ``title``: canonical habit title (same as the dict key).
    - ``repeat``: the habit's rule in normal form (for sorting).
    - ``scheduled_current`` / ``scheduled_prior``: scheduled days per window
      (``None`` when unknown; ``scheduled_prior`` is ``None`` without a prior
      window).
    - ``current_count``: dedup-by-date completion count from
      ``habits-history.jsonl`` in the current window (``None`` when the
      scheduled count is unknown).
    - ``prior_count``: same for the prior window (0 if
      ``prior_window_start`` / ``prior_window_end`` is ``None``).

    The Vikunja query is intentionally **current-state only**: titles +
    the ``repeat`` rule for classification. Completion counts come from the
    canonical store via :mod:`scripts.habits.history` (FR-002). The
    WP03 architectural test allowlists this file for the current-state
    Vikunja call; it does NOT allow ``task.get("done_at")`` reads —
    those have been removed from this module.

    ``"other"``-classified tasks (no rule) are filtered out before
    aggregation: the cardiac-lab one-off and any non-recurring task never
    appear in the report.
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

        scheduled_current = scheduled_days_for_window(
            kind, task, window_start, window_end
        )
        current_count = _completed_in_window_for_habit(
            scheduled=scheduled_current,
            habit_id=habit_id,
            window_start=window_start,
            window_end=window_end,
        )
        scheduled_prior: int | None = None
        prior_count: int | None = 0
        if prior_window_start is not None and prior_window_end is not None:
            scheduled_prior = scheduled_days_for_window(
                kind, task, prior_window_start, prior_window_end
            )
            prior_count = _completed_in_window_for_habit(
                scheduled=scheduled_prior,
                habit_id=habit_id,
                window_start=prior_window_start,
                window_end=prior_window_end,
            )

        events[title] = {
            "kind": kind,
            "title": title,
            "repeat": vikunja_rule.normalise(task.get("repeat")),
            "scheduled_current": scheduled_current,
            "scheduled_prior": scheduled_prior,
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


def _sort_key(bucket: Mapping[str, Any]) -> tuple[int, int, str]:
    """Daily first, then weekly-by-day by first weekday, then other rules; title last."""
    kind = bucket["kind"]
    kind_rank = HABIT_KINDS.index(kind) if kind in HABIT_KINDS else len(HABIT_KINDS)
    weekday_rank = 0
    if kind == "weekly-by-day":
        days = [
            RULE_WEEKDAY_TO_PYTHON[d[-2:]]
            for d in (bucket.get("repeat") or {}).get("by_day", [])
            if d[-2:] in RULE_WEEKDAY_TO_PYTHON
        ]
        weekday_rank = min(days) if days else 7
    return (kind_rank, weekday_rank, bucket["title"])


def _cap(
    *,
    raw: int | None,
    scheduled: int | None,
    title: str,
    kind: str,
    window: str,
    window_start: datetime,
    window_end: datetime,
) -> int | None:
    """Clamp ``raw`` at ``scheduled``, emitting an anomaly when it was over."""
    if raw is None or scheduled is None:
        return None
    capped = min(raw, scheduled)
    if raw > scheduled:
        _emit_anomaly_log_action(
            habit_title=title,
            habit_kind=kind,
            window=window,
            scheduled_days=scheduled,
            raw_count=raw,
            capped_count=capped,
            window_start=window_start,
            window_end=window_end,
        )
    return capped


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


def _overall_percent(
    habits: list[dict], scheduled_key: str, completed_key: str
) -> Optional[float]:
    """Aggregate one window's overall percent over habits with a known schedule.

    Returns ``None`` (unknown) when habits exist but none has a known
    scheduled count for the window. An empty habit list keeps ``0.0``.
    """
    known = [h for h in habits if h[scheduled_key] is not None]
    if habits and not known:
        return None
    total_scheduled = sum(h[scheduled_key] for h in known)
    total_completed = sum(h[completed_key] or 0 for h in known)
    return _percent(total_completed, total_scheduled)


def build_report(
    events_by_title: dict[str, dict],
    *,
    window_start: datetime,
    window_end: datetime,
    prior_window_start: Optional[datetime],
    prior_window_end: Optional[datetime],
) -> dict:
    """Assemble the WeeklyHabitReport JSON-ready dict.

    Takes each bucket's scheduled-day counts from
    :func:`query_completion_events`. A ``None`` (unknown) scheduled count
    gives ``None`` completed/percent fields for that cell, and the habit is
    left out of the overall totals.

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
    for bucket in sorted(events_by_title.values(), key=_sort_key):
        title = bucket["title"]
        kind = bucket["kind"]
        scheduled_current = bucket["scheduled_current"]
        completed_current = _cap(
            raw=bucket["current_count"],
            scheduled=scheduled_current,
            title=title,
            kind=kind,
            window="current",
            window_start=window_start,
            window_end=window_end,
        )
        if include_baseline:
            scheduled_prior = bucket["scheduled_prior"]
            completed_prior = _cap(
                raw=bucket["prior_count"],
                scheduled=scheduled_prior,
                title=title,
                kind=kind,
                window="prior",
                window_start=prior_window_start,  # type: ignore[arg-type]
                window_end=prior_window_end,  # type: ignore[arg-type]
            )
            percent_prior: Optional[float] = (
                None
                if scheduled_prior is None or completed_prior is None
                else _percent(completed_prior, scheduled_prior)
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
                "percent_current": (
                    None
                    if scheduled_current is None or completed_current is None
                    else _percent(completed_current, scheduled_current)
                ),
                "scheduled_days_prior": scheduled_prior,
                "completed_events_prior": completed_prior,
                "percent_prior": percent_prior,
            }
        )

    # Habits with an unknown schedule are left out of the overall totals:
    # counting them as 0 scheduled would be a guess. When habits exist but
    # none has a known schedule in a window, that window's overall is
    # unknown (``None``), never a false 0%.
    overall_percent_current = _overall_percent(
        habits, "scheduled_days_current", "completed_events_current"
    )

    if include_baseline:
        overall_percent_prior: Optional[float] = _overall_percent(
            habits, "scheduled_days_prior", "completed_events_prior"
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
        if current_pct is None:
            lines.append(f"{habit['habit_title']} — {UNKNOWN_SCHEDULE_TEXT}")
            continue
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
    if overall_current is None:
        # No habit has a known schedule: same marker as an unknown habit row.
        lines.append(f"*Overall* — {UNKNOWN_SCHEDULE_TEXT}")
        return "\n".join(lines)
    overall_arrow = _arrow_for_delta(overall_current, overall_prior)
    if overall_prior is None and report.get("prior_window_start_iso"):
        # A baseline window exists but no habit has a known schedule in it.
        overall_line = (
            f"*Overall: {_render_pct(overall_current)}%* "
            f"(was {UNKNOWN_SCHEDULE_TEXT})"
        )
    elif overall_prior is None:
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
