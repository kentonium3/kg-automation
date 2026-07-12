#!/usr/bin/env python3
"""Deterministic escalation pre-candidate enumeration (mission
``deterministic-cron-hardening-01KXA4PX``, kentonium3/kg-automation#723).

Replaces the felix-admin-escalation agent's improvised Vikunja fetch +
inline python3 (the bug: querying ``/projects/-4/tasks``, which does not
exist) with a deterministic helper the agent invokes as a subprocess.

**Critical framing (post-plan review H7, authoritative)**: this module's
output is **pre-candidates** only — the date/priority/project slice of
escalation SKILL.md §1. Snooze/dismiss/level lifecycle (§2) is NOT applied
here; the agent MUST call ``derive_state`` per pre-candidate and alert
ONLY when ``next_eligible_level != null``. Do not treat this module's
output as the final alert set.

Per Felix Constitution Directive 6, this module is split into a **pure**
filter function (:func:`filter_candidates`, no I/O, fully unit-testable)
and an I/O ``main()`` that paginates Vikunja and prints JSON — so tests
exercise the escalation-qualification logic without touching the network.

Authoritative contracts:
    - ``kitty-specs/deterministic-cron-hardening-01KXA4PX/contracts/enumerate_candidates.md``
      (IC-02) — CLI invocation, behavior, stdout shape, exit codes.
    - ``kitty-specs/deterministic-cron-hardening-01KXA4PX/contracts/post-plan-review-resolutions.md``
      H7 (pre-candidates framing), H8 (due-date normalization rules), H9
      (failure propagation — non-zero exit must surface as a real failure,
      never silently swallowed into a healthy run).
    - ``scripts/openclaw/skills/escalation/SKILL.md`` § 1 — the escalation
      qualification criteria this module implements (source of truth for
      wording; this module is the deterministic mechanism).

Vikunja access
--------------
Uses ``scripts.common.vikunja_client.VikunjaClient`` (stateless, leading-
slash paths). The all-tasks endpoint is **``/tasks/all``** — the agent's
former ``/projects/-4/tasks`` query was the root-cause bug this mission
fixes. Vikunja caps ``per_page`` at 50; this module paginates starting at
page 1 and **stops on an empty batch** (never on ``len(batch) < 100`` —
that heuristic silently truncates whenever a full-but-not-100-sized final
page arrives, per the mission's memory gotcha).

Due-date normalization (H8)
---------------------------
A task's ``due_date`` is rejected (excluded from candidacy) when it is
``None``, an empty string, the Vikunja "unset" sentinel
(``0001-01-01T00:00:00Z``), or otherwise unparseable. Valid values are
parsed as aware datetimes, converted to **America/New_York**, and compared
as **local calendar dates** against the ``--date`` argument (also an
America/New_York calendar date, defaulting to "today" in that zone) — so a
task due at 23:00 UTC and one due at 01:00 UTC on the surrounding calendar
day are classified by the same ET-local due date, not by their raw UTC
day.

Public surface
--------------
Constants: ``LOCAL_TZ``, ``SENTINEL_DUE_DATE``, ``PER_PAGE``
Dataclass: ``EscalationCandidate``
Functions: ``normalize_due_date``, ``filter_candidates``, ``fetch_all_tasks``, ``main``
"""
from __future__ import annotations

import argparse
import json
import sys
import zoneinfo
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Literal, Optional

from scripts.common.vikunja_client import VikunjaClient, VikunjaError
from scripts.common.vikunja_scope import get_escalation_excluded_project_ids

__all__ = [
    "LOCAL_TZ",
    "SENTINEL_DUE_DATE",
    "PER_PAGE",
    "EscalationCandidate",
    "normalize_due_date",
    "filter_candidates",
    "fetch_all_tasks",
    "main",
]

#: Local timezone for "today" and due-date comparisons (H8). Escalation
#: operates in Kent's local TZ so date boundaries fall on America/New_York
#: calendar days, not UTC days — mirrors ``derive_state.LOCAL_TZ``.
LOCAL_TZ = zoneinfo.ZoneInfo("America/New_York")

#: Vikunja's "no due date" sentinel value (year 1, per SKILL.md §1).
SENTINEL_DUE_DATE = "0001-01-01T00:00:00Z"

#: Vikunja's hard cap on page size for ``/tasks/all``.
PER_PAGE = 50

#: Minimum priority to qualify for escalation at all (SKILL.md §1).
_MIN_PRIORITY = 2

#: Minimum priority for a due-today task to qualify (SKILL.md §1).
_DUE_TODAY_MIN_PRIORITY = 3

Reason = Literal["overdue", "due_today_high_priority"]


@dataclass(frozen=True, slots=True)
class EscalationCandidate:
    """One pre-candidate task per ``contracts/enumerate_candidates.md``.

    Attributes:
        task_id: Vikunja task id.
        project_id: Vikunja project id.
        title: Task title (verbatim from Vikunja).
        due_date: Original ``due_date`` string as returned by Vikunja
            (preserved verbatim for downstream consumers; normalization is
            internal to the filter).
        priority: Vikunja priority int.
        reason: ``"overdue"`` or ``"due_today_high_priority"``.
    """

    task_id: int
    project_id: int
    title: str
    due_date: str
    priority: int
    reason: Reason


def normalize_due_date(value: Any, *, local_tz: zoneinfo.ZoneInfo = LOCAL_TZ) -> Optional[date]:
    """Parse a Vikunja ``due_date`` value into a local (ET) calendar date.

    Per H8: rejects (returns ``None`` for) ``None``, empty/whitespace-only
    strings, the ``0001-01-01T00:00:00Z`` sentinel, non-str values, and any
    value that fails ISO-8601 parsing. A successfully parsed value is
    converted to ``local_tz`` and the **local calendar date** is returned
    (not the raw UTC date) — this is what makes the day-boundary tests
    (23:00 UTC vs 01:00 UTC) classify consistently.

    Args:
        value: The raw ``due_date`` field from a Vikunja task dict.
        local_tz: Timezone to convert into before taking the calendar date.
            Defaults to :data:`LOCAL_TZ`; overridable for tests.

    Returns:
        The local calendar :class:`date`, or ``None`` if the value must be
        excluded per H8.
    """
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped:
        return None
    if stripped == SENTINEL_DUE_DATE:
        return None
    normalized = stripped.replace("Z", "+00:00") if stripped.endswith("Z") else stripped
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        # Malformed / naive datetime — H8 requires an aware value. Do not
        # guess a timezone; exclude rather than silently assume UTC.
        return None
    local_dt = parsed.astimezone(local_tz)
    return local_dt.date()


def _qualifies(
    task: dict,
    *,
    today: date,
    excluded_project_ids: frozenset[int],
) -> Optional[Reason]:
    """Return the qualification reason for one task, or ``None``.

    Applies SKILL.md §1's date/priority/project slice only (H7 —
    pre-candidates; snooze/dismiss/level lifecycle is NOT evaluated here).
    """
    if task.get("done"):
        return None

    priority = task.get("priority")
    if isinstance(priority, bool) or not isinstance(priority, int):
        return None
    if priority < _MIN_PRIORITY:
        return None

    project_id = task.get("project_id")
    if isinstance(project_id, int) and project_id in excluded_project_ids:
        return None

    due_local = normalize_due_date(task.get("due_date"))
    if due_local is None:
        return None

    if due_local < today:
        return "overdue"
    if due_local == today and priority >= _DUE_TODAY_MIN_PRIORITY:
        return "due_today_high_priority"
    return None


def filter_candidates(
    tasks: Iterable[dict],
    today: date,
    excluded_ids: Iterable[int],
) -> list[EscalationCandidate]:
    """Pure filter: reduce raw Vikunja task dicts to sorted pre-candidates.

    No I/O — this is the function unit tests exercise directly (per the
    mission's testing mandate that the filter be verifiable without
    network access).

    Args:
        tasks: Raw Vikunja task dicts (as returned by ``GET /tasks/all``).
        today: The America/New_York calendar date to treat as "today" for
            overdue/due-today comparisons.
        excluded_ids: Project ids to exclude (normally the return value of
            ``vikunja_scope.get_escalation_excluded_project_ids()``).

    Returns:
        Sorted list of :class:`EscalationCandidate`, ordered by
        ``(due_date, task_id)`` for deterministic output. Empty list if
        nothing qualifies.
    """
    excluded = frozenset(excluded_ids)
    candidates: list[EscalationCandidate] = []
    for task in tasks:
        reason = _qualifies(task, today=today, excluded_project_ids=excluded)
        if reason is None:
            continue
        candidates.append(
            EscalationCandidate(
                task_id=task["id"],
                project_id=task["project_id"],
                title=task.get("title", ""),
                due_date=task.get("due_date"),
                priority=task["priority"],
                reason=reason,
            )
        )
    candidates.sort(key=lambda c: (c.due_date, c.task_id))
    return candidates


# ---------------------------------------------------------------------------
# I/O: Vikunja pagination
# ---------------------------------------------------------------------------


def fetch_all_tasks(client: VikunjaClient) -> list[dict]:
    """Paginate ``GET /tasks/all`` until an empty batch, returning all tasks.

    Per the contract: starts at page 1, requests ``per_page=PER_PAGE`` (50,
    Vikunja's cap), and stops when a page returns an empty list — NEVER on
    ``len(batch) < 100`` (that heuristic is wrong once ``per_page`` is
    capped at 50 and silently truncates a full-but-partial final page).

    Raises:
        VikunjaError: Propagated from the underlying HTTP client on any
            network/HTTP failure. Callers (``main``) map this to exit 1.
    """
    tasks: list[dict] = []
    page = 1
    while True:
        batch = client.get("/tasks/all", params={"page": str(page), "per_page": str(PER_PAGE)})
        if not batch:
            break
        tasks.extend(batch)
        page += 1
    return tasks


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _json_default(value: Any) -> Any:
    """JSON encoder default for the ``date`` values that slip into output."""
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m scripts.escalation.enumerate_candidates",
        description=(
            "Enumerate escalation PRE-CANDIDATES (date/priority/project slice "
            "of SKILL.md §1 only) and print them as a sorted JSON array on "
            "stdout. This is NOT the final alert set — callers must run each "
            "pre-candidate through derive_state and alert only when "
            "next_eligible_level is not null."
        ),
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help=(
            "Calendar date (YYYY-MM-DD) to treat as 'today' for "
            "overdue/due-today comparisons, in America/New_York. "
            "Defaults to the current date in that zone."
        ),
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default=None,
        help="Vikunja API base URL override (local testing only).",
    )
    parser.add_argument(
        "--token-path",
        type=Path,
        default=None,
        help="Path to a Vikunja API token file override (local testing only).",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entrypoint. See ``contracts/enumerate_candidates.md`` for exit codes.

    Exit codes:
        ``0`` — success (including an empty ``[]`` result).
        ``1`` — Vikunja unreachable/HTTP error. Nothing is printed to
            stdout; the error is reported on stderr. Per H9, callers MUST
            propagate this as a real run failure, not swallow it.
        ``3`` — usage/validation error (e.g. malformed ``--date``).
    """
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    if args.date is not None:
        try:
            today = date.fromisoformat(args.date)
        except ValueError:
            print(f"error: --date '{args.date}' is not a valid YYYY-MM-DD date", file=sys.stderr)
            return 3
    else:
        today = datetime.now(LOCAL_TZ).date()

    token: Optional[str] = None
    if args.token_path is not None:
        try:
            token = args.token_path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            print(f"error: could not read --token-path {args.token_path}: {exc}", file=sys.stderr)
            return 3

    client_kwargs: dict[str, Any] = {}
    if args.base_url is not None:
        client_kwargs["base_url"] = args.base_url
    if token is not None:
        client_kwargs["token"] = token

    try:
        client = VikunjaClient(**client_kwargs)
        tasks = fetch_all_tasks(client)
    except (VikunjaError, ValueError) as exc:
        print(f"error: Vikunja fetch failed: {exc}", file=sys.stderr)
        return 1

    excluded_ids = get_escalation_excluded_project_ids()
    candidates = filter_candidates(tasks, today, excluded_ids)
    payload = [asdict(c) for c in candidates]
    print(json.dumps(payload, default=_json_default))
    return 0


if __name__ == "__main__":  # pragma: no cover -- exercised via subprocess
    sys.exit(main())
