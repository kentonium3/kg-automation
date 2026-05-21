#!/usr/bin/env python3
"""ADR-0002 Phase 6 ``derive_state`` pure function for the escalation domain.

This module is the **sole source of truth** for the escalation policy walk
from the JSONL state log angle. It converts a list of JSONL records for ONE
task into the current :class:`EscalationState`. Every escalation policy
semantic (snooze expiry, next-eligible-level computation, terminal-state
detection) lives here -- :class:`EscalationState` is the documented contract
between this function and downstream consumers (``record_completion``,
``reconcile_completions``, and the OpenClaw ``escalation`` skill).

Policy walk order (per ``contracts/api.md`` and SKILL.md
§ "Level determination algorithm"):

    1. Empty input          -> ``current_state="new"``.
    2. Newest record is a **terminal state** (``done`` / ``dismissed``)
       -> return that terminal state, ``next_eligible_level=None``.
    3. Newest record is **snoozed**:
         a. If ``snooze_until >= today`` -> ``current_state="snoozed"``,
            ``snooze_active_until=snooze_until``, ``next_eligible_level=None``.
         b. Else -> ``current_state="snoozed_expired"``,
            ``snooze_active_until=snooze_until``, ``next_eligible_level=1``
            (re-enter the funnel at Level 1 per SKILL.md rule 4).
    4. Newest record is **rescheduled** -> ``current_state="rescheduled"``,
       ``next_eligible_level=None``. (Vikunja-state driven re-evaluation is
       the caller's responsibility.)
    5. Newest record is **level_sent**:
         a. ``level=1`` and recorded >= ``LEVEL_1_TO_2_STALENESS_DAYS`` ago
            -> ``current_state="level_1_sent"``, ``next_eligible_level=2``.
         b. ``level=1`` and recorded recently
            -> ``current_state="level_1_sent"``, ``next_eligible_level=None``.
         c. ``level=2`` (any age)
            -> ``current_state="level_2_sent"``, ``next_eligible_level=2``.
            (Per SKILL.md rule 3: daily dedup at the caller, repeat
            insistence is allowed.)

Hard-fail surface (per spec FR-008 + research D7/D8):

    Inconsistent records raise :class:`EscalationStateError` with one of the
    three reason taxonomy values from data-model Entity 5:

    - ``"missing_required_param"`` -- record carries a known ``state`` but
      a required structured parameter is missing or has the wrong shape
      (e.g., ``level_sent`` with no ``level`` field, ``level=3`` outside
      ``{1, 2}``).
    - ``"unknown_state"`` -- record carries a ``state`` not in the
      flat-enum escalation vocabulary.
    - ``"impossible_ordering"`` -- a record carries an unparseable
      ``timestamp`` so the newest-first sort cannot proceed.

    Callers are expected to catch :class:`EscalationStateError`, log
    structured stderr, and route to Q10 hard-fail per research D8.

The companion debug CLI (``python3 -m scripts.escalation.derive_state``)
loads JSONL records for one ``(task_id, project_id)`` pair, calls
``derive_state``, and dumps the result as JSON to stdout per
``contracts/cli.md``.

Design references:
    - kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/spec.md
        FR-001 (JSONL sole state source), FR-008 (Q10 hard-fail), NFR-004.
    - kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/contracts/api.md
        ``derive_state`` + ``EscalationState`` + ``EscalationStateError``.
    - kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/contracts/cli.md
        Debug CLI flag set + exit codes 0/2/3/4.
    - kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/data-model.md
        Entity 1 (JSONL record shape), Entity 5 (reason taxonomy).
    - kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/research.md
        D7 (derive_state shape), D8 (Q10 trigger conditions).
    - scripts/openclaw/skills/escalation/SKILL.md § 2
        Level determination algorithm (the policy this function encodes).
    - scripts/escalation/schema.py
        ``EVENT_TYPE_PARAMETERS`` + ``validate_event_params`` (per-record
        validation; ``derive_state`` consumes this rather than re-encoding).
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

from scripts.escalation.schema import (
    EVENT_TYPE_PARAMETERS,
    EscalationSchemaError,
    validate_event_params,
)


# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

#: Local timezone used for "today" comparisons in the policy walk. The
#: escalation skill operates in Kent's local TZ (America/New_York) so
#: snooze-expiry boundaries fall on local calendar days, not UTC days.
LOCAL_TZ = zoneinfo.ZoneInfo("America/New_York")

#: Calendar days of overdue at which Level 1 ("Nudge") becomes appropriate
#: when there is no prior escalation comment. Kept here for documentation
#: parity with SKILL.md § 1; not currently consumed by ``derive_state`` (the
#: caller computes overdue days from Vikunja state).
LEVEL_1_OVERDUE_DAYS = 1

#: Calendar days of overdue at which Level 2 ("Insistence") becomes
#: appropriate when there is no prior escalation comment. Documentation
#: parity with SKILL.md § 1.
LEVEL_2_OVERDUE_DAYS = 3

#: Calendar days a Level 1 record can sit before the next eligible level
#: bumps to 2. Per SKILL.md rule 2: "Sent 2+ days ago AND no subsequent
#: acknowledged comment -> Level 2".
LEVEL_1_TO_2_STALENESS_DAYS = 2

#: Default JSONL state directory on office2. Used by the debug CLI when
#: ``--jsonl-dir`` is not supplied.
DEFAULT_JSONL_STATE_DIR = Path("/data/services/openclaw/state/escalation")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class EscalationStateError(Exception):
    """Raised when ``derive_state`` cannot reduce records to a consistent state.

    Attributes:
        task_id: Which task's records were being processed, or ``None`` if
            no records had a usable ``task_id``.
        records: The records that triggered the inconsistency (one or more).
        reason: Short string per data-model Entity 5 reason taxonomy. One of
            ``"missing_required_param"``, ``"unknown_state"``,
            ``"impossible_ordering"``.
    """

    #: The three reason taxonomy values, exposed as a class attribute so
    #: callers (and tests) can reference them without string literals.
    REASONS = frozenset(
        {"missing_required_param", "unknown_state", "impossible_ordering"}
    )

    def __init__(
        self,
        message: str,
        *,
        task_id: Optional[int] = None,
        records: Optional[list[dict]] = None,
        reason: str = "missing_required_param",
    ) -> None:
        if reason not in self.REASONS:
            raise ValueError(
                f"reason '{reason}' not in {sorted(self.REASONS)}"
            )
        super().__init__(message)
        self.task_id = task_id
        self.records = list(records) if records else []
        self.reason = reason


# ---------------------------------------------------------------------------
# Public dataclass
# ---------------------------------------------------------------------------


#: Type alias for the discriminated union of allowed ``current_state``
#: values. Kept inline with contracts/api.md.
CurrentState = Literal[
    "new",
    "level_1_sent",
    "level_2_sent",
    "snoozed",
    "snoozed_expired",
    "dismissed",
    "done",
    "rescheduled",
]


@dataclass(frozen=True, slots=True)
class EscalationState:
    """Reduced state of an escalation-subscribed task per contracts/api.md.

    Attributes:
        current_state: Discriminated literal naming the active policy bucket
            this task sits in. ``"new"`` is reserved for the empty-records
            case (callers normally avoid passing empty input).
        last_event: The newest JSONL record from the input list, or ``None``
            when the input was empty.
        snooze_active_until: For ``snoozed`` and ``snoozed_expired`` states
            only -- the parsed ``snooze_until`` date. ``None`` for every
            other state.
        next_eligible_level: ``1`` or ``2`` if the caller may send a level
            this tick (subject to daily dedup at the caller); ``None`` when
            terminal, snoozed-active, or rescheduled.
        last_event_recorded_at: The parsed ``timestamp`` of ``last_event``,
            or ``None`` when the input was empty.
    """

    current_state: CurrentState
    last_event: Optional[dict]
    snooze_active_until: Optional[date]
    next_eligible_level: Optional[int]
    last_event_recorded_at: Optional[datetime]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _today_local() -> date:
    """Return today's date in :data:`LOCAL_TZ`.

    Wrapped as a module-level function so tests can ``monkeypatch.setattr``
    the symbol and freeze "today" without touching real wall-clock time.
    """
    return datetime.now(LOCAL_TZ).date()


def _parse_timestamp(value: Any) -> datetime:
    """Parse a record's ``timestamp`` field as a tz-aware :class:`datetime`.

    Supports the canonical ``YYYY-MM-DDTHH:MM:SS+HH:MM`` form produced by the
    Phase 2 ``state_log.append`` helper, plus the ``Z`` UTC suffix that
    appears in some legacy fixtures.

    Raises:
        ValueError: If the value cannot be parsed. Callers wrap this into
            :class:`EscalationStateError` with reason ``"impossible_ordering"``.
    """
    if not isinstance(value, str):
        raise ValueError(
            f"timestamp must be str, got {type(value).__name__}"
        )
    # ``fromisoformat`` in Python 3.10 does not accept ``Z`` directly; fold
    # to ``+00:00`` so we get a tz-aware datetime back.
    normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"timestamp '{value}' is not ISO-8601: {exc}") from None


def _parse_date(value: Any, field: str) -> date:
    """Parse an ``YYYY-MM-DD`` calendar-date field from a record.

    Used for ``snooze_until``, ``date``, and (defensively) any other
    calendar-date parameter the policy walk needs. The Phase 2 schema
    validator already enforces these patterns; this helper is the second
    line of defense inside ``derive_state``.

    Raises:
        ValueError: If the value is missing or malformed.
    """
    if not isinstance(value, str):
        raise ValueError(
            f"{field} must be str, got {type(value).__name__}"
        )
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} '{value}' is not ISO-8601: {exc}") from None


def _record_task_id(records: Iterable[dict]) -> Optional[int]:
    """Return the first record's ``task_id`` (best-effort, for error context)."""
    for r in records:
        value = r.get("task_id")
        if isinstance(value, int):
            return value
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def derive_state(records: list[dict]) -> EscalationState:
    """Reduce ``records`` (all for ONE task) to the current escalation state.

    The function is pure: zero I/O, deterministic on its inputs once
    :func:`_today_local` is treated as a side-effect-free clock. Time-
    dependent paths (snooze expiry, level-1 staleness) are mediated through
    :func:`_today_local`; tests monkeypatch that symbol.

    Args:
        records: Every JSONL record for one ``(task_id, project_id)`` pair.
            Order does not matter -- :func:`derive_state` sorts newest-first
            internally before applying the policy walk. May be empty.

    Returns:
        An :class:`EscalationState` describing the current bucket the task
        sits in plus the metadata downstream consumers need.

    Raises:
        EscalationStateError: When the records carry an inconsistent shape.
            See :class:`EscalationStateError` for the three reason values.
    """
    # ---- 1. Empty input guard --------------------------------------------
    if not records:
        return EscalationState(
            current_state="new",
            last_event=None,
            snooze_active_until=None,
            next_eligible_level=None,
            last_event_recorded_at=None,
        )

    # ---- 2. Parse + validate every record's timestamp -------------------
    # We do the timestamp parse first so an unparseable record raises
    # ``impossible_ordering`` BEFORE any state-shape check that would surface
    # a less-precise ``missing_required_param``.
    parsed: list[tuple[datetime, dict]] = []
    task_id_hint = _record_task_id(records)
    for r in records:
        try:
            ts = _parse_timestamp(r.get("timestamp"))
        except ValueError as exc:
            raise EscalationStateError(
                f"task {task_id_hint}: cannot sort records -- {exc}",
                task_id=task_id_hint,
                records=[r],
                reason="impossible_ordering",
            ) from None
        parsed.append((ts, r))

    # ---- 3. Per-record structured-parameter validation -------------------
    # Delegate to ``scripts.escalation.schema.validate_event_params`` so the
    # policy code does not re-encode the EVENT_TYPE_PARAMETERS table. We
    # rewrap ``EscalationSchemaError`` as the appropriate ``EscalationStateError``
    # reason so callers see one consistent exception surface.
    for _ts, r in parsed:
        state_value = r.get("state")
        if state_value is not None and state_value not in EVENT_TYPE_PARAMETERS:
            known = ", ".join(sorted(EVENT_TYPE_PARAMETERS.keys()))
            raise EscalationStateError(
                f"task {task_id_hint}: state '{state_value}' not in "
                f"escalation event_types {{{known}}}",
                task_id=task_id_hint,
                records=[r],
                reason="unknown_state",
            )
        try:
            validate_event_params(r)
        except EscalationSchemaError as exc:
            raise EscalationStateError(
                f"task {task_id_hint}: {exc}",
                task_id=task_id_hint,
                records=[r],
                reason="missing_required_param",
            ) from None

    # ---- 4. Sort newest-first --------------------------------------------
    parsed.sort(key=lambda pair: pair[0], reverse=True)
    newest_ts, newest = parsed[0]
    newest_state = newest["state"]

    # ---- 5. Policy walk --------------------------------------------------
    # Terminal states first.
    if newest_state == "done":
        return EscalationState(
            current_state="done",
            last_event=newest,
            snooze_active_until=None,
            next_eligible_level=None,
            last_event_recorded_at=newest_ts,
        )

    if newest_state == "dismissed":
        return EscalationState(
            current_state="dismissed",
            last_event=newest,
            snooze_active_until=None,
            next_eligible_level=None,
            last_event_recorded_at=newest_ts,
        )

    # Snooze (active or expired).
    if newest_state == "snoozed":
        try:
            snooze_until = _parse_date(newest.get("snooze_until"), "snooze_until")
        except ValueError as exc:
            # ``validate_event_params`` should already have caught this,
            # but keep the defensive raise for completeness.
            raise EscalationStateError(
                f"task {task_id_hint}: {exc}",
                task_id=task_id_hint,
                records=[newest],
                reason="missing_required_param",
            ) from None
        if _today_local() <= snooze_until:
            return EscalationState(
                current_state="snoozed",
                last_event=newest,
                snooze_active_until=snooze_until,
                next_eligible_level=None,
                last_event_recorded_at=newest_ts,
            )
        # Snooze expired -- re-enter the funnel at Level 1 per SKILL.md
        # rule 4.
        return EscalationState(
            current_state="snoozed_expired",
            last_event=newest,
            snooze_active_until=snooze_until,
            next_eligible_level=1,
            last_event_recorded_at=newest_ts,
        )

    # Rescheduled -- caller checks Vikunja state for the new due_date.
    if newest_state == "rescheduled":
        return EscalationState(
            current_state="rescheduled",
            last_event=newest,
            snooze_active_until=None,
            next_eligible_level=None,
            last_event_recorded_at=newest_ts,
        )

    # level_sent -- compute next eligible level based on staleness.
    if newest_state == "level_sent":
        level = newest.get("level")
        # ``validate_event_params`` already enforced level in {1, 2}, but be
        # explicit here so the policy walk reads end-to-end.
        if level == 1:
            try:
                record_date = _parse_date(newest.get("date"), "date")
            except ValueError as exc:
                raise EscalationStateError(
                    f"task {task_id_hint}: {exc}",
                    task_id=task_id_hint,
                    records=[newest],
                    reason="missing_required_param",
                ) from None
            days_since = (_today_local() - record_date).days
            if days_since >= LEVEL_1_TO_2_STALENESS_DAYS:
                return EscalationState(
                    current_state="level_1_sent",
                    last_event=newest,
                    snooze_active_until=None,
                    next_eligible_level=2,
                    last_event_recorded_at=newest_ts,
                )
            return EscalationState(
                current_state="level_1_sent",
                last_event=newest,
                snooze_active_until=None,
                next_eligible_level=None,
                last_event_recorded_at=newest_ts,
            )
        if level == 2:
            return EscalationState(
                current_state="level_2_sent",
                last_event=newest,
                snooze_active_until=None,
                next_eligible_level=2,
                last_event_recorded_at=newest_ts,
            )
        # Defensive: schema validation should have rejected any other
        # level value. If we got here, treat as a missing/invalid param.
        raise EscalationStateError(
            f"task {task_id_hint}: level_sent has unexpected level "
            f"value '{level!r}' (expected 1 or 2)",
            task_id=task_id_hint,
            records=[newest],
            reason="missing_required_param",
        )

    # Defensive catch-all -- ``validate_event_params`` should have already
    # raised on any state not in ``EVENT_TYPE_PARAMETERS``. Treat as
    # ``unknown_state`` so callers route to Q10 correctly.
    raise EscalationStateError(  # pragma: no cover -- truly unreachable
        f"task {task_id_hint}: state '{newest_state}' fell through policy walk",
        task_id=task_id_hint,
        records=[newest],
        reason="unknown_state",
    )


# ---------------------------------------------------------------------------
# Debug CLI
# ---------------------------------------------------------------------------


def _json_default(value: Any) -> Any:
    """JSON encoder default for :class:`date` / :class:`datetime` values.

    Used when serializing the :class:`EscalationState` dataclass for the
    debug CLI's stdout. Dates emit as ``YYYY-MM-DD``, datetimes as the
    ``datetime.isoformat()`` form.
    """
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(
        f"Object of type {type(value).__name__} is not JSON serializable"
    )


def _project_slug_glob(jsonl_dir: Path, project_slug: Optional[str]) -> list[Path]:
    """Return the list of JSONL files to scan for the debug CLI lookup.

    Args:
        jsonl_dir: Directory containing ``<slug>-escalation-history.jsonl``
            files.
        project_slug: If provided, return exactly one path. If ``None``,
            return every ``*-escalation-history.jsonl`` file in the directory.

    The caller filters by ``task_id`` / ``project_id`` inside
    :func:`_load_records_for_task`.
    """
    if project_slug:
        return [jsonl_dir / f"{project_slug}-escalation-history.jsonl"]
    return sorted(jsonl_dir.glob("*-escalation-history.jsonl"))


def _load_records_for_task(
    jsonl_dir: Path,
    task_id: int,
    project_id: int,
    project_slug: Optional[str],
) -> list[dict]:
    """Read JSONL records matching ``(task_id, project_id)`` for the debug CLI.

    Args:
        jsonl_dir: Directory of escalation JSONL files.
        task_id: Vikunja task id to filter on.
        project_id: Vikunja project id to filter on.
        project_slug: Optional slug to narrow to one file. ``None`` scans
            every ``*-escalation-history.jsonl`` file in ``jsonl_dir``.

    Returns:
        Every matching record across the candidate files. May be empty.

    Raises:
        FileNotFoundError: When ``project_slug`` is set and the specific
            file does not exist; or when ``project_slug`` is unset and
            ``jsonl_dir`` itself does not exist.
    """
    if not jsonl_dir.exists():
        raise FileNotFoundError(f"jsonl_dir does not exist: {jsonl_dir}")
    candidates = _project_slug_glob(jsonl_dir, project_slug)
    if project_slug and not candidates[0].exists():
        raise FileNotFoundError(
            f"JSONL file not found for slug '{project_slug}': {candidates[0]}"
        )

    matches: list[dict] = []
    for path in candidates:
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    # Malformed line -- skip; the CLI is a debug tool, not
                    # a hard-fail filing surface. The real reconcile path
                    # handles malformed lines per Q10.
                    continue
                if not isinstance(record, dict):
                    continue
                if (
                    record.get("task_id") == task_id
                    and record.get("project_id") == project_id
                ):
                    matches.append(record)
    return matches


def _build_arg_parser() -> argparse.ArgumentParser:
    """Construct the argparse ``ArgumentParser`` for the debug CLI."""
    parser = argparse.ArgumentParser(
        prog="python3 -m scripts.escalation.derive_state",
        description=(
            "Print the derived escalation state for one task. Reads JSONL "
            "records from the escalation state directory, filters by "
            "(task_id, project_id), and prints the EscalationState dataclass "
            "as JSON. Operator debugging tool only -- the production "
            "callers import derive_state() directly."
        ),
    )
    parser.add_argument(
        "--task-id",
        type=int,
        required=True,
        help="Vikunja task id to look up.",
    )
    parser.add_argument(
        "--project-id",
        type=int,
        required=True,
        help="Vikunja project id (also filters records).",
    )
    parser.add_argument(
        "--jsonl-dir",
        type=Path,
        default=DEFAULT_JSONL_STATE_DIR,
        help=(
            "Directory containing <slug>-escalation-history.jsonl files. "
            f"Default: {DEFAULT_JSONL_STATE_DIR}."
        ),
    )
    parser.add_argument(
        "--project-slug",
        type=str,
        default=None,
        help=(
            "Optional project slug to narrow lookup to one file. "
            "If omitted, scan every *-escalation-history.jsonl file in "
            "--jsonl-dir."
        ),
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    """Debug CLI entrypoint. See ``contracts/cli.md`` for exit codes.

    Exit codes:
        ``0`` -- Success; ``EscalationState`` printed to stdout as JSON.
        ``2`` -- JSONL read failure (missing dir / missing slug file).
        ``3`` -- ``derive_state`` raised :class:`EscalationStateError`.
                  A structured error JSON is printed to stderr.
        ``4`` -- No records found for the requested ``(task_id, project_id)``.
                  A diagnostic JSON is printed to stdout.
    """
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    try:
        records = _load_records_for_task(
            args.jsonl_dir,
            args.task_id,
            args.project_id,
            args.project_slug,
        )
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not records:
        diagnostic = {
            "task_id": args.task_id,
            "project_id": args.project_id,
            "current_state": "new",
            "records_found": 0,
        }
        print(json.dumps(diagnostic, default=_json_default))
        return 4

    try:
        state = derive_state(records)
    except EscalationStateError as exc:
        err = {
            "error": "EscalationStateError",
            "reason": exc.reason,
            "task_id": exc.task_id,
            "message": str(exc),
            "records": exc.records,
        }
        print(json.dumps(err, default=_json_default), file=sys.stderr)
        return 3

    payload: dict[str, Any] = {
        "task_id": args.task_id,
        "project_id": args.project_id,
        **asdict(state),
    }
    print(json.dumps(payload, default=_json_default))
    return 0


if __name__ == "__main__":  # pragma: no cover -- exercised via subprocess
    sys.exit(main())
