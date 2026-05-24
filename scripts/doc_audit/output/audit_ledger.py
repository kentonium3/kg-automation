"""Commit-audit append-only JSONL ledger.

Per mission ``audit-interpretation-moment0-01KSBGBS`` (D1, E3), every
processed in-scope doc within a commit-derived audit produces one row
appended to
``/data/services/openclaw/state/doc_audit/audit-events-ledger.jsonl``.
The ledger powers operator-visible metrics analogous to the drift
ledger:

- **NFR-001 triage rate** — ``count(JUDGMENT_REQUIRED) / count(*)``
  over a trailing window. Target ≤30%.
- Outcome breakdown for diagnostic queries.

Schema mirrors ``doc_audit.output.drift_ledger`` with two adaptations
(per data-model E3):

1. ``audit_issue: int`` replaces ``event_id`` / ``baseline`` /
   ``mapping_id``. The audit issue number is the cursor for the
   commit-audit path.
2. ``judgment_required_posted`` is added to :data:`VALID_OUTCOMES`.
   Drift uses ``issue_filed`` for JUDGMENT_REQUIRED because drift
   creates a NEW issue per event; audit appends a comment to the
   EXISTING audit issue, so a distinct outcome lets operators query
   the two pipelines independently.

Concurrency
-----------

The pipeline assumes a single-writer (one cron job at a time invokes
:func:`append`). Steady-state appends use ``open(path, "a")`` with an
explicit ``flush()`` + ``fsync()`` — sufficient for the single-writer
guarantee and durable across process crashes. The JSON-Lines format
is naturally append-safe: a torn write corrupts a single row but not
the file, and consumers (:func:`read_window`) tolerate corrupt lines.

For initial creation, the parent directory is created if missing.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from dataclasses import dataclass, fields
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional


__all__ = [
    "AuditLedgerEntry",
    "DEFAULT_LEDGER_PATH",
    "SCHEMA_VERSION",
    "VALID_VERDICTS",
    "VALID_OUTCOMES",
    "FIELD_ORDER",
    "append",
    "read_window",
    "compute_triage_rate",
    "compute_outcome_breakdown",
    "main",
]


# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

DEFAULT_LEDGER_PATH = Path(
    "/data/services/openclaw/state/doc_audit/audit-events-ledger.jsonl"
)
"""Canonical location of the audit-events ledger on office2.

Co-located with the doc_audit driver's state directory so operators
can ``tail -f`` it alongside the driver's last-tick.json and
activity logs.
"""

SCHEMA_VERSION = 1
"""Current schema version. Bump on incompatible field changes."""

VALID_VERDICTS = frozenset(
    {
        "PROPOSED_EDIT",
        "JUDGMENT_REQUIRED",
        "NO_CHANGE_NEEDED",
        "RETRY_EXHAUSTED",
    }
)
"""Set of permissible ``verdict`` values for a ledger entry.

The first three mirror :class:`doc_audit.judgment.audit_interpretation.AuditVerdict`
(E1). ``RETRY_EXHAUSTED`` is the post-retry-policy fallback emitted
when the synthetic JUDGMENT_REQUIRED-on-exhaustion path needs to be
recorded distinctly for reliability tracking.
"""

VALID_OUTCOMES = frozenset(
    {
        "auto_committed",
        "pr_filed",
        "issue_filed",
        "auto_closed",
        "judgment_required_posted",
        "retry_exhausted",
    }
)
"""Set of permissible ``outcome`` values for a ledger entry.

``judgment_required_posted`` is unique to the audit ledger (drift uses
``issue_filed`` for the same logical outcome because drift FILES a new
issue; audit POSTS a comment on the existing audit issue).
"""


# Field order is load-bearing: it determines the on-disk JSON key order
# for deterministic diffing. Used by :func:`_entry_to_json` to produce
# a stable, hand-readable JSONL row.
FIELD_ORDER: tuple[str, ...] = (
    "schema_version",
    "audit_issue",
    "doc_path",
    "timestamp_utc",
    "commit_sha",
    "verdict",
    "confidence",
    "outcome",
)


# ---------------------------------------------------------------------------
# Dataclass — E3 AuditLedgerEntry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AuditLedgerEntry:
    """One JSONL row in the audit-events ledger (E3).

    Append-only. Serialized as a single line of compact JSON with the
    field order in :data:`FIELD_ORDER` for deterministic diffing.

    Attributes:
        audit_issue: GH issue number for the originating audit.
        doc_path: in-scope doc path the verdict applies to.
        timestamp_utc: ISO 8601 ``Z``-suffixed timestamp.
        commit_sha: triggering commit SHA (short or full).
        verdict: one of :data:`VALID_VERDICTS`.
        confidence: float in [0.0, 1.0], or ``None`` for
            ``RETRY_EXHAUSTED`` verdicts.
        outcome: one of :data:`VALID_OUTCOMES`.
        schema_version: schema version (default :data:`SCHEMA_VERSION`).
    """

    audit_issue: int
    doc_path: str
    timestamp_utc: str
    commit_sha: str
    verdict: str
    confidence: Optional[float]
    outcome: str
    schema_version: int = SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate_entry(entry: AuditLedgerEntry) -> None:
    """Validate an entry against schema invariants.

    Raises:
        ValueError: on any invariant violation. Validation runs BEFORE
            the write so a malformed entry never reaches the ledger.
    """
    if entry.verdict not in VALID_VERDICTS:
        raise ValueError(
            f"invalid verdict: {entry.verdict!r}; "
            f"must be one of {sorted(VALID_VERDICTS)}"
        )

    if entry.outcome not in VALID_OUTCOMES:
        raise ValueError(
            f"invalid outcome: {entry.outcome!r}; "
            f"must be one of {sorted(VALID_OUTCOMES)}"
        )

    # confidence: None iff verdict == RETRY_EXHAUSTED.
    if entry.verdict == "RETRY_EXHAUSTED":
        if entry.confidence is not None:
            raise ValueError(
                "confidence must be None when verdict is RETRY_EXHAUSTED; "
                f"got {entry.confidence!r}"
            )
    else:
        if entry.confidence is None:
            raise ValueError(
                f"confidence must be a float in [0.0, 1.0] when "
                f"verdict is {entry.verdict!r}; got None"
            )
        if isinstance(entry.confidence, bool) or not isinstance(
            entry.confidence, (int, float)
        ):
            raise ValueError(
                f"confidence must be a number; got "
                f"{type(entry.confidence).__name__}"
            )
        if not (0.0 <= float(entry.confidence) <= 1.0):
            raise ValueError(
                f"confidence must be in [0.0, 1.0]; got {entry.confidence!r}"
            )

    if entry.schema_version != SCHEMA_VERSION:
        raise ValueError(
            f"schema_version must be {SCHEMA_VERSION}; "
            f"got {entry.schema_version!r}"
        )

    if not isinstance(entry.audit_issue, int) or isinstance(
        entry.audit_issue, bool
    ):
        raise ValueError(
            f"audit_issue must be an int; got "
            f"{type(entry.audit_issue).__name__}"
        )
    if entry.audit_issue <= 0:
        raise ValueError(
            f"audit_issue must be a positive int; got {entry.audit_issue!r}"
        )

    if not entry.doc_path:
        raise ValueError("doc_path must be a non-empty string")
    if not entry.timestamp_utc:
        raise ValueError("timestamp_utc must be a non-empty string")
    if not entry.commit_sha:
        raise ValueError("commit_sha must be a non-empty string")


def _entry_to_dict(entry: AuditLedgerEntry) -> dict[str, Any]:
    """Build an ordered dict from an entry per :data:`FIELD_ORDER`.

    Python 3.7+ preserves dict insertion order, so the resulting JSON
    serialization (with ``sort_keys=False``) emits keys in the
    contracted order.
    """
    return {field_name: getattr(entry, field_name) for field_name in FIELD_ORDER}


def _entry_to_json(entry: AuditLedgerEntry) -> str:
    """Serialize an entry to a single-line compact JSON string.

    Uses ``ensure_ascii=True`` so any non-ASCII characters are escaped
    as ``\\uXXXX`` — safe for grep-style operator queries and
    platform-portable.
    """
    payload = _entry_to_dict(entry)
    return json.dumps(
        payload,
        sort_keys=False,
        ensure_ascii=True,
        separators=(",", ":"),
    )


def _dict_to_entry(data: dict[str, Any]) -> AuditLedgerEntry:
    """Deserialize a JSON dict into an :class:`AuditLedgerEntry`.

    Unknown fields are ignored for forward-compatibility (consumers
    MUST tolerate new optional fields per JSON forward-compat).

    Raises:
        ValueError: if a required field is missing.
    """
    known = {f.name for f in fields(AuditLedgerEntry)}
    kwargs = {k: v for k, v in data.items() if k in known}
    required = set(FIELD_ORDER)
    missing = required - kwargs.keys()
    if missing:
        raise ValueError(
            f"ledger entry missing required fields: {sorted(missing)}"
        )
    return AuditLedgerEntry(**kwargs)


def _parse_json_line(line: str) -> AuditLedgerEntry:
    """Strict-parse a single JSONL line into an entry.

    Raises:
        ValueError: on JSON parse failure or schema mismatch.
    """
    try:
        data = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON parse failure: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(
            f"ledger line must be a JSON object; got {type(data).__name__}"
        )
    return _dict_to_entry(data)


def _parse_timestamp(ts: str) -> datetime:
    """Parse an ISO 8601 ``Z``-suffixed timestamp into an aware datetime.

    Accepts both ``Z`` and ``+00:00`` offset notations for resilience.
    """
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    return datetime.fromisoformat(ts)


# ---------------------------------------------------------------------------
# Public API — append
# ---------------------------------------------------------------------------


def append(
    entry: AuditLedgerEntry,
    *,
    ledger_path: Path = DEFAULT_LEDGER_PATH,
) -> None:
    """Append one ledger entry to the audit-events JSONL ledger.

    Validates the entry against schema invariants BEFORE writing so a
    malformed entry never reaches disk. The write is durable: the
    file handle is flushed and ``fsync``-ed before close.

    Args:
        entry: :class:`AuditLedgerEntry` to serialize (E3).
        ledger_path: target JSONL file (default
            :data:`DEFAULT_LEDGER_PATH`).

    Raises:
        ValueError: if ``entry`` violates schema invariants.
        OSError: if the write fails.
    """
    _validate_entry(entry)
    serialized = _entry_to_json(entry) + "\n"

    ledger_path.parent.mkdir(parents=True, exist_ok=True)

    with ledger_path.open("a", encoding="utf-8") as f:
        f.write(serialized)
        f.flush()
        os.fsync(f.fileno())


# ---------------------------------------------------------------------------
# Public API — read_window
# ---------------------------------------------------------------------------


_TAIL_CHUNK_BYTES = 64 * 1024


def _tail_lines(ledger_path: Path, cutoff: datetime) -> Iterable[str]:
    """Yield raw text lines from end-of-file, stopping at ``cutoff``.

    Reads 64KB chunks backwards. Yields complete lines in REVERSE
    order (newest first). Stops once a parseable entry's
    ``timestamp_utc`` predates ``cutoff`` (lines are roughly ordered
    by write time, so this is a safe early-exit heuristic for a
    single-writer ledger).
    """
    file_size = ledger_path.stat().st_size
    if file_size == 0:
        return

    buffer = b""
    position = file_size

    with ledger_path.open("rb") as f:
        while position > 0:
            read_size = min(_TAIL_CHUNK_BYTES, position)
            position -= read_size
            f.seek(position)
            chunk = f.read(read_size)
            buffer = chunk + buffer

            parts = buffer.split(b"\n")
            buffer = parts[0]
            for segment in reversed(parts[1:]):
                if not segment:
                    continue
                try:
                    text = segment.decode("utf-8")
                except UnicodeDecodeError:
                    continue
                try:
                    entry = _parse_json_line(text)
                    ts = _parse_timestamp(entry.timestamp_utc)
                    if ts < cutoff:
                        return
                except ValueError:
                    pass
                yield text

        if buffer:
            try:
                text = buffer.decode("utf-8")
            except UnicodeDecodeError:
                return
            yield text


def read_window(
    *,
    ledger_path: Path = DEFAULT_LEDGER_PATH,
    days: int = 7,
) -> list[AuditLedgerEntry]:
    """Read ledger entries within the trailing N-day window.

    Tails the file from end-of-file backwards, parsing JSONL rows
    until reaching an entry older than ``now - days``. Returns the
    in-window entries in CHRONOLOGICAL order (oldest first).

    Corrupt lines are silently skipped (logged via stderr) — the
    JSONL format guarantees torn writes corrupt at most one row.

    Args:
        ledger_path: ledger file location (default
            :data:`DEFAULT_LEDGER_PATH`).
        days: number of trailing days to include.

    Returns:
        list of :class:`AuditLedgerEntry`, chronological order.
        Empty list if the file does not exist or has no in-window rows.
    """
    if not ledger_path.exists():
        return []
    if ledger_path.stat().st_size == 0:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    collected: list[AuditLedgerEntry] = []
    for line in _tail_lines(ledger_path, cutoff):
        try:
            entry = _parse_json_line(line)
        except ValueError as exc:
            print(
                f"audit_ledger: skipping corrupt line: {exc}",
                file=sys.stderr,
            )
            continue
        try:
            ts = _parse_timestamp(entry.timestamp_utc)
        except ValueError:
            print(
                f"audit_ledger: skipping entry with bad timestamp: "
                f"{entry.timestamp_utc!r}",
                file=sys.stderr,
            )
            continue
        if ts < cutoff:
            continue
        collected.append(entry)

    collected.reverse()
    return collected


# ---------------------------------------------------------------------------
# Public API — metrics helpers
# ---------------------------------------------------------------------------


def compute_triage_rate(
    *,
    ledger_path: Path = DEFAULT_LEDGER_PATH,
    days: int = 7,
) -> float:
    """Compute ``count(JUDGMENT_REQUIRED) / count(*)`` over trailing window.

    The NFR-001 success-criterion metric. Target ≤30%.

    Returns ``0.0`` for an empty window.
    """
    entries = read_window(ledger_path=ledger_path, days=days)
    total = len(entries)
    if total == 0:
        return 0.0
    escalated = sum(1 for e in entries if e.verdict == "JUDGMENT_REQUIRED")
    return escalated / total


def compute_outcome_breakdown(
    *,
    ledger_path: Path = DEFAULT_LEDGER_PATH,
    days: int = 7,
) -> dict[str, int]:
    """Return ``Counter``-style mapping of outcome → count over window."""
    entries = read_window(ledger_path=ledger_path, days=days)
    return dict(Counter(e.outcome for e in entries))


# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------


class _ArgparseError(Exception):
    """Raised by :class:`_StructuredArgumentParser` so ``main()`` returns 3."""


class _StructuredArgumentParser(argparse.ArgumentParser):
    """Argparse subclass that raises instead of ``sys.exit(2)`` on bad flags."""

    def error(self, message: str) -> None:  # type: ignore[override]
        raise _ArgparseError(message)


def _build_parser() -> argparse.ArgumentParser:
    parser = _StructuredArgumentParser(
        prog="audit_ledger",
        description=(
            "Read-only queries against the audit-events ledger. "
            "Subcommands: summary, tail."
        ),
    )
    parser.add_argument(
        "--ledger-path",
        type=Path,
        default=DEFAULT_LEDGER_PATH,
        help=f"Ledger file path (default: {DEFAULT_LEDGER_PATH}).",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Trailing window size in days (default: 7).",
    )

    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    summary = subparsers.add_parser(
        "summary",
        parents=[],
        help="Print verdict counts + outcome breakdown for the window.",
    )
    summary.set_defaults(_handler=_handle_summary)

    tail = subparsers.add_parser(
        "tail",
        parents=[],
        help="Show last 10 ledger entries (pretty-printed JSON).",
    )
    tail.set_defaults(_handler=_handle_tail)

    return parser


def _emit_stderr_error(step: str, error: str) -> None:
    """Emit a structured JSON error line on stderr."""
    msg = json.dumps({"step": step, "error": error}, ensure_ascii=False)
    print(msg, file=sys.stderr)


def _handle_summary(args: argparse.Namespace) -> int:
    entries = read_window(ledger_path=args.ledger_path, days=args.days)
    total = len(entries)
    print(f"Audit ledger summary (last {args.days} day(s), {total} entries)")
    print("")
    print("Verdicts:")
    verdict_counts = Counter(e.verdict for e in entries)
    for verdict in sorted(VALID_VERDICTS):
        count = verdict_counts.get(verdict, 0)
        print(f"  {verdict:25s} {count}")
    print("")
    print("Outcomes:")
    outcome_counts = Counter(e.outcome for e in entries)
    for outcome in sorted(VALID_OUTCOMES):
        count = outcome_counts.get(outcome, 0)
        print(f"  {outcome:25s} {count}")
    return 0


def _handle_tail(args: argparse.Namespace) -> int:
    entries = read_window(ledger_path=args.ledger_path, days=args.days)
    tail_entries = entries[-10:]
    for entry in tail_entries:
        print(json.dumps(_entry_to_dict(entry), indent=2, ensure_ascii=False))
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry point.

    Exit codes::

        0 -- Success
        1 -- Ledger file unreadable
        3 -- Invalid subcommand or flag
    """
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except _ArgparseError as exc:
        _emit_stderr_error(step="argparse", error=str(exc))
        return 3

    handler = getattr(args, "_handler", None)
    if handler is None:
        _emit_stderr_error(step="argparse", error="no subcommand")
        return 3

    try:
        return handler(args)
    except FileNotFoundError as exc:
        _emit_stderr_error(step="ledger_read", error=str(exc))
        return 1
    except PermissionError as exc:
        _emit_stderr_error(step="ledger_read", error=str(exc))
        return 1
    except OSError as exc:
        _emit_stderr_error(step="ledger_read", error=str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
