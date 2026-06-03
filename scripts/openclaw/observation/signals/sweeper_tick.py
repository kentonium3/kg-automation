"""Signal extractor: felix-habit-sweeper tick failures (#510).

Reads the most recent **non-dry-run** record from the sweeper ledger at
``/data/services/openclaw/state/habits/sweeper-ledger.jsonl`` (or
whatever path ``signal_def.source_path_pattern`` declares) and trips
on three binary conditions:

- ``exit_status != "success"`` in the latest record
- ``errors`` array non-empty in the latest record
- ``now_utc - latest.started_at_utc >= 26 hours`` (timer didn't fire),
  OR no parseable non-dry-run record exists in the ledger at all

Binary semantic per OD-1: returns ``count_cycle = 1`` when ANY condition
holds, ``0`` otherwise. The host pipeline's quiet-cycle gate from #512
keeps the no-fail case (``count_cycle == 0``) below threshold without
filing.

See ``contracts/sweeper-tick-extractor.contract.md`` in mission
``sweeper-tick-signal-extractor-01KT6MJP`` for the authoritative
predicate, and ``contracts/tick-signal.contract.md`` in mission #490 for
the cross-extractor envelope contract.

This extractor does NOT delegate to ``_engine.run_extraction`` — that
helper is log-substring-counting; the sweeper signal is a
latest-JSONL-record check with different semantics.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Union

from scripts.openclaw.observation.signals._engine import redact_dict
from scripts.openclaw.observation.signals.config_loader import (
    SignalDefinition,
)
from scripts.openclaw.observation.signals.openclaw_log import LogCursor
from scripts.openclaw.observation.signals.types import SignalExtraction

__all__ = ["STALE_THRESHOLD_HOURS", "extract"]


#: Hours past the latest production tick's ``started_at_utc`` before
#: the extractor trips on staleness. 24 h sweeper cadence + 2 h slack.
#: Named here (not in ``config.toml``) because it's a property of the
#: sweeper's cadence, not a tunable signal threshold. If the sweeper
#: cadence changes, this constant changes in lockstep with the sweeper.
STALE_THRESHOLD_HOURS = 26


# ---------------------------------------------------------------------------
# Public extractor
# ---------------------------------------------------------------------------


def extract(
    state_dir: Union[Path, str],
    signal_def: SignalDefinition,
    now_utc: datetime,
    prior_cursor: Optional[LogCursor] = None,
    prior_rolling_count: int = 0,
) -> SignalExtraction:
    """Walk the sweeper ledger; return a :class:`SignalExtraction`.

    Args mirror the other extractors in this package so
    :func:`scripts.openclaw.observation.tick.build_extractor_dispatch` can
    hand off uniformly. ``state_dir`` and ``prior_cursor`` are accepted
    for signature compatibility but unused — this extractor is
    cursorless and stateless.

    Implements the predicate documented in the mission contract. Binary
    output: ``count_cycle`` is 0 (passing) or 1 (failing).
    """
    if now_utc.tzinfo is None:
        raise ValueError("extract: now_utc must be timezone-aware")

    ledger_path = Path(signal_def.source_path_pattern)
    count_cycle, excerpt, last_event_at = _evaluate(ledger_path, now_utc)

    excerpts = [excerpt] if excerpt is not None else []
    return SignalExtraction(
        signal_id=signal_def.signal_id,
        count_cycle=count_cycle,
        count_rolling=prior_rolling_count + count_cycle,
        excerpts=excerpts,
        last_event_at_utc=last_event_at,
        new_cursor=None,
    )


# ---------------------------------------------------------------------------
# Predicate
# ---------------------------------------------------------------------------


def _evaluate(
    ledger_path: Path,
    now_utc: datetime,
) -> tuple[int, Optional[str], Optional[datetime]]:
    """Return ``(count_cycle, excerpt_str_or_None, last_event_at)``.

    See data-model.md § "Trip truth table" for the case enumeration.
    """
    ledger_exists = ledger_path.is_file()
    if not ledger_exists:
        return (
            1,
            _synthetic_no_record_excerpt(
                ledger_path=ledger_path,
                ledger_exists=False,
                total_records=0,
                dry_run_only_count=0,
            ),
            None,
        )

    # Read the whole file. At current scale the ledger is <100 records
    # and stays comfortably under the NFR-001 500 ms budget; a tail
    # optimization can land later if the ledger grows.
    try:
        text = ledger_path.read_text(encoding="utf-8")
    except OSError:
        return (
            1,
            _synthetic_no_record_excerpt(
                ledger_path=ledger_path,
                ledger_exists=True,
                total_records=0,
                dry_run_only_count=0,
            ),
            None,
        )

    parsed_records: list[dict] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            # Trailing partial line, garbage line, etc. — skip silently.
            continue
        if isinstance(obj, dict):
            parsed_records.append(obj)

    if not parsed_records:
        return (
            1,
            _synthetic_no_record_excerpt(
                ledger_path=ledger_path,
                ledger_exists=True,
                total_records=0,
                dry_run_only_count=0,
            ),
            None,
        )

    # Walk newest-first. The ledger is append-only, so the last line is
    # the most recent record.
    dry_run_seen = 0
    for record in reversed(parsed_records):
        if record.get("dry_run") is True:
            dry_run_seen += 1
            continue
        # First non-dry-run record found. Evaluate the three conditions.
        return _evaluate_record(record, now_utc)

    # Every parsed record was a dry-run.
    return (
        1,
        _synthetic_no_record_excerpt(
            ledger_path=ledger_path,
            ledger_exists=True,
            total_records=len(parsed_records),
            dry_run_only_count=dry_run_seen,
        ),
        None,
    )


def _evaluate_record(
    record: dict,
    now_utc: datetime,
) -> tuple[int, Optional[str], Optional[datetime]]:
    """Apply the three trip conditions to ``record``."""
    started_at = _parse_iso(record.get("started_at_utc"))

    # Stale check FIRST. A stale record's exit_status / errors fields
    # are stale evidence too; stale-or-absent is the dominant failure mode.
    if started_at is None or now_utc - started_at >= timedelta(
        hours=STALE_THRESHOLD_HOURS
    ):
        return (
            1,
            _synthetic_stale_excerpt(record, now_utc, started_at),
            started_at,
        )

    if record.get("exit_status") != "success":
        return (1, _record_excerpt(record), started_at)

    errors = record.get("errors")
    if isinstance(errors, list) and len(errors) > 0:
        return (1, _record_excerpt(record), started_at)

    # All three checks passed.
    return (0, None, started_at)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_iso(value: object) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp with ``Z`` suffix, tolerantly.

    Returns ``None`` for non-string input or unparseable strings.
    Always returns a tz-aware UTC datetime when it returns a value.
    """
    if not isinstance(value, str):
        return None
    # ``datetime.fromisoformat`` in Python ≤3.10 doesn't accept ``Z``;
    # normalize before parsing.
    s = value.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _record_excerpt(record: dict) -> str:
    """Serialize a ledger record as a redacted JSON string.

    Redaction is value-length-driven per mission #490 spec C-005
    (``_engine.redact_dict``); the empty ``redact_keys`` tuple satisfies
    the helper's signature without imposing any key-based redaction.
    """
    return json.dumps(redact_dict(record, ()), sort_keys=True)


def _synthetic_stale_excerpt(
    record: dict,
    now_utc: datetime,
    started_at: Optional[datetime],
) -> str:
    """Build the synthetic excerpt for the stale-or-unparseable trip."""
    if started_at is None:
        age_hours: Optional[int] = None
        latest_ts = record.get("started_at_utc") if isinstance(
            record.get("started_at_utc"), str
        ) else None
    else:
        age_hours = int((now_utc - started_at).total_seconds() // 3600)
        latest_ts = started_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    return json.dumps(
        {
            "reason": "stale_production_record",
            "latest_tick_started_at_utc": latest_ts,
            "age_hours": age_hours,
            "threshold_hours": STALE_THRESHOLD_HOURS,
        },
        sort_keys=True,
    )


def _synthetic_no_record_excerpt(
    *,
    ledger_path: Path,
    ledger_exists: bool,
    total_records: int,
    dry_run_only_count: int,
) -> str:
    """Build the synthetic excerpt for missing / empty / dry-run-only ledger."""
    return json.dumps(
        {
            "reason": "no_production_record",
            "ledger_path": str(ledger_path),
            "ledger_exists": ledger_exists,
            "ledger_record_count": total_records,
            "dry_run_only_count": dry_run_only_count,
        },
        sort_keys=True,
    )
