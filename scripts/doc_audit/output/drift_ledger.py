"""Drift-events append-only JSONL ledger.

Per mission ``drift-event-auto-resolution-01KS8J32`` (D4), every
processed drift event produces one row appended to
``/data/services/security-monitor/logs/drift-events-ledger.jsonl``.
The ledger powers two operator-visible metrics:

- **NFR-001 triage rate** — ``count(JUDGMENT_REQUIRED) / count(*)``
  over a trailing window. Target ≤30%.
- **NFR-005 reliability** — ``1.0 - count(RETRY_EXHAUSTED) / count(*)``.
  Target ≥98%.

Schema is defined in ``contracts/ledger-schema.md``. Each row is one
line of compact JSON with the field order in :class:`AuditLedgerEntry`
(preserved via ``json.dumps(..., sort_keys=False)`` on Python 3.7+).

Concurrency
-----------

The pipeline assumes a single-writer (one cron job at a time invokes
``append()``). Steady-state appends use ``open(path, "a")`` with an
explicit ``flush()`` + ``fsync()`` — sufficient for the single-writer
guarantee and durable across process crashes. The JSON-Lines format
is naturally append-safe: a torn write corrupts a single row but not
the file, and consumers (``read_window``) tolerate corrupt lines.

For initial creation, the parent directory is created if missing.
Tempfile + rename is NOT used for steady-state appends (appends are
O(1) and OS-atomic for small lines under the typical row size).
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

from doc_audit.judgment.drift_interpretation import RETRY_DELAYS_SECONDS


__all__ = [
    "AuditLedgerEntry",
    "DEFAULT_LEDGER_PATH",
    "RETRY_MAX_ATTEMPTS",
    "SCHEMA_VERSION",
    "VALID_VERDICTS",
    "VALID_OUTCOMES",
    "VALID_TIER_OUTCOMES",
    "FIELD_ORDER",
    "append",
    "read_window",
    "compute_triage_rate",
    "compute_reliability",
    "compute_outcome_breakdown",
    "main",
]


# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

DEFAULT_LEDGER_PATH = Path(
    "/data/services/security-monitor/logs/drift-events-ledger.jsonl"
)
"""Canonical location of the drift-events ledger on office2.

Co-located with the existing ``drift-events.jsonl`` file produced
by ``audit.sh`` (the upstream signal source). Operators can ``tail
-f`` both files side-by-side.
"""

SCHEMA_VERSION = 1
"""Current schema version. Bump on incompatible field changes."""

RETRY_MAX_ATTEMPTS = 1 + len(RETRY_DELAYS_SECONDS)
"""Upper bound on ``retry_count`` for a ledger row.

Derived from the retry policy in
:mod:`doc_audit.judgment.drift_interpretation` so the validator stays in
lockstep with the actual retry budget. The ``+1`` accounts for the
initial (zero-delay) call. With the current ``RETRY_DELAYS_SECONDS =
(30, 60, 120)`` policy this evaluates to ``4``.
"""

VALID_VERDICTS = frozenset(
    {
        "PROPOSED_EDIT",
        "JUDGMENT_REQUIRED",
        "NO_CHANGE_NEEDED",
        "RETRY_EXHAUSTED",
    }
)
"""Set of permissible ``verdict`` values for a ledger entry.

The first three mirror :class:`DriftVerdict` (E1). The fourth,
``RETRY_EXHAUSTED``, is the post-retry-policy fallback per FR-008/
FR-009 — emitted when ``DriftInterpretationError`` propagates after
all retries are exhausted.
"""

VALID_OUTCOMES = frozenset(
    {
        "auto_committed",
        "pr_filed",
        "issue_filed",
        "auto_closed",
        "retry_exhausted",
    }
)
"""Set of permissible ``outcome`` values for a ledger entry."""

VALID_TIER_OUTCOMES = frozenset({"tier_a", "tier_b", "judgment"})
"""Set of permissible ``tier_classification_outcome`` values, excluding
``None``. ``None`` is also valid when Moment 1 was not invoked
(NO_CHANGE_NEEDED / JUDGMENT_REQUIRED / RETRY_EXHAUSTED paths).
"""


# Field order is load-bearing: it determines the on-disk JSON key order
# for deterministic diffing. Mirrors the table in
# contracts/ledger-schema.md exactly. Used by ``_entry_to_json`` to
# produce a stable, hand-readable JSONL row.
FIELD_ORDER: tuple[str, ...] = (
    "schema_version",
    "event_id",
    "timestamp_utc",
    "baseline",
    "mapping_id",
    "verdict",
    "confidence",
    "outcome",
    "doc_paths",
    "retry_count",
    "latency_ms",
    "tier_classification_outcome",
    "github_issue_number",
)


# ---------------------------------------------------------------------------
# Dataclass — E3 AuditLedgerEntry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AuditLedgerEntry:
    """One JSONL row in the drift-events ledger.

    Append-only. Serialized as a single line of compact JSON with the
    field order in :data:`FIELD_ORDER` for deterministic diffing.

    Schema summary (one row per processed drift event, FR-010):

    - ``schema_version`` — current is :data:`SCHEMA_VERSION` (``1``).
    - ``event_id`` — non-empty string identifying the source event.
    - ``timestamp_utc`` — ISO 8601 ``Z``-suffixed write time.
    - ``baseline`` — non-empty baseline name from the upstream event.
    - ``mapping_id`` — non-empty id from ``signal-to-doc-map.json``.
    - ``verdict`` — one of :data:`VALID_VERDICTS`.
    - ``confidence`` — float in ``[0.0, 1.0]`` for all verdicts except
      ``RETRY_EXHAUSTED``; ``None`` for ``RETRY_EXHAUSTED``.
    - ``outcome`` — one of :data:`VALID_OUTCOMES`.
    - ``doc_paths`` — list of doc-target path strings.
    - ``retry_count`` — integer in ``[0, RETRY_MAX_ATTEMPTS]``. The
      bound is derived from the live retry policy in
      :mod:`doc_audit.judgment.drift_interpretation` (currently ``4``).
    - ``latency_ms`` — non-negative integer wall-clock latency.
    - ``tier_classification_outcome`` — ``None`` or one of
      :data:`VALID_TIER_OUTCOMES`.
    - ``github_issue_number`` — optional GitHub issue number.

    See ``docs/design/architecture/contracts/drift-ledger-schema.md``
    for the canonical schema.
    """

    event_id: str
    timestamp_utc: str
    baseline: str
    mapping_id: str
    verdict: str
    confidence: Optional[float]
    outcome: str
    doc_paths: list[str]
    retry_count: int
    latency_ms: int
    tier_classification_outcome: Optional[str]
    github_issue_number: Optional[int]
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
        if not isinstance(entry.confidence, (int, float)):
            raise ValueError(
                f"confidence must be a number; got "
                f"{type(entry.confidence).__name__}"
            )
        if not (0.0 <= float(entry.confidence) <= 1.0):
            raise ValueError(
                f"confidence must be in [0.0, 1.0]; got {entry.confidence!r}"
            )

    # tier_classification_outcome: None or one of VALID_TIER_OUTCOMES.
    if (
        entry.tier_classification_outcome is not None
        and entry.tier_classification_outcome not in VALID_TIER_OUTCOMES
    ):
        raise ValueError(
            f"invalid tier_classification_outcome: "
            f"{entry.tier_classification_outcome!r}; must be one of "
            f"{sorted(VALID_TIER_OUTCOMES)} or None"
        )

    if entry.retry_count < 0 or entry.retry_count > RETRY_MAX_ATTEMPTS:
        raise ValueError(
            f"retry_count must be in [0, {RETRY_MAX_ATTEMPTS}]; "
            f"got {entry.retry_count!r}"
        )

    if entry.latency_ms < 0:
        raise ValueError(
            f"latency_ms must be non-negative; got {entry.latency_ms!r}"
        )

    if not isinstance(entry.doc_paths, list) or not all(
        isinstance(p, str) for p in entry.doc_paths
    ):
        raise ValueError("doc_paths must be a list of strings")

    if entry.schema_version != SCHEMA_VERSION:
        # Permit older readers; writers always emit the current version.
        raise ValueError(
            f"schema_version must be {SCHEMA_VERSION}; "
            f"got {entry.schema_version!r}"
        )

    if not entry.event_id:
        raise ValueError("event_id must be a non-empty string")
    if not entry.timestamp_utc:
        raise ValueError("timestamp_utc must be a non-empty string")
    if not entry.baseline:
        raise ValueError("baseline must be a non-empty string")
    if not entry.mapping_id:
        raise ValueError("mapping_id must be a non-empty string")


def _entry_to_dict(entry: AuditLedgerEntry) -> dict[str, Any]:
    """Build an ordered dict from an entry per :data:`FIELD_ORDER`.

    Python 3.7+ preserves dict insertion order, so the resulting JSON
    serialization (with ``sort_keys=False``) emits keys in the
    contracted order.
    """
    return {field_name: getattr(entry, field_name) for field_name in FIELD_ORDER}


def _entry_to_json(entry: AuditLedgerEntry) -> str:
    """Serialize an entry to a single-line compact JSON string.

    Uses ``ensure_ascii=True`` so any non-ASCII characters in
    ``rationale``-like strings are escaped as ``\\uXXXX`` — safe for
    grep-style operator queries and platform-portable.
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
    """Append one ledger entry to the drift-events JSONL ledger.

    Validates the entry against schema invariants BEFORE writing so a
    malformed entry never reaches disk. The write is durable: the
    file handle is flushed and ``fsync``-ed before close.

    Args:
        entry: :class:`AuditLedgerEntry` to serialize (E3).
        ledger_path: target JSONL file (default
            :data:`DEFAULT_LEDGER_PATH`).

    Raises:
        ValueError: if ``entry`` violates schema invariants.
        OSError: if the write fails (caller's exit 1 path).
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

    Edge cases:
    - Empty file → no lines yielded.
    - File ending without a trailing newline → the final partial line
      is still yielded.
    - Corrupt lines (un-parseable as JSON) are still yielded; the
      caller decides whether to skip or raise.
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

            # Split the buffer on newlines. Keep the leading partial
            # segment in the buffer so the next iteration prepends
            # the preceding chunk to it before parsing.
            parts = buffer.split(b"\n")
            buffer = parts[0]  # may still be partial; carry forward
            # Walk the complete segments newest-first.
            for segment in reversed(parts[1:]):
                if not segment:
                    continue
                try:
                    text = segment.decode("utf-8")
                except UnicodeDecodeError:
                    continue
                # Early-exit check: if this is a valid entry and its
                # timestamp is older than the cutoff, stop yielding.
                try:
                    entry = _parse_json_line(text)
                    ts = _parse_timestamp(entry.timestamp_utc)
                    if ts < cutoff:
                        return
                except ValueError:
                    # Corrupt line — pass it through; caller decides.
                    pass
                yield text

        # Drain any remaining partial segment (the first line of the
        # file, never preceded by ``\n``).
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
                f"drift_ledger: skipping corrupt line: {exc}",
                file=sys.stderr,
            )
            continue
        try:
            ts = _parse_timestamp(entry.timestamp_utc)
        except ValueError:
            # Malformed timestamp — treat as corrupt.
            print(
                f"drift_ledger: skipping entry with bad timestamp: "
                f"{entry.timestamp_utc!r}",
                file=sys.stderr,
            )
            continue
        if ts < cutoff:
            continue
        collected.append(entry)

    # collected is reverse-chronological (newest first) because
    # _tail_lines walks backwards. Reverse so callers receive
    # chronological order, mirroring file-read expectations.
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


def compute_reliability(
    *,
    ledger_path: Path = DEFAULT_LEDGER_PATH,
    days: int = 7,
) -> float:
    """Compute ``1.0 - count(RETRY_EXHAUSTED) / count(*)`` over window.

    The NFR-005 success-criterion metric. Target ≥98%.

    Returns ``1.0`` for an empty window (no failures observed).
    """
    entries = read_window(ledger_path=ledger_path, days=days)
    total = len(entries)
    if total == 0:
        return 1.0
    exhausted = sum(1 for e in entries if e.verdict == "RETRY_EXHAUSTED")
    return 1.0 - (exhausted / total)


def compute_outcome_breakdown(
    *,
    ledger_path: Path = DEFAULT_LEDGER_PATH,
    days: int = 7,
) -> dict[str, int]:
    """Return ``Counter``-style mapping of outcome → count over window."""
    entries = read_window(ledger_path=ledger_path, days=days)
    return dict(Counter(e.outcome for e in entries))


# ---------------------------------------------------------------------------
# CLI surface (per contracts/cli.md)
# ---------------------------------------------------------------------------


class _ArgparseError(Exception):
    """Raised by :class:`_StructuredArgumentParser` so ``main()`` returns 3.

    argparse's default ``error()`` calls ``sys.exit(2)``, but
    ``contracts/cli.md`` defines exit 3 for bad subcommand/flag. Mirrors
    the WP01 ``drift_interpretation`` pattern.
    """


class _StructuredArgumentParser(argparse.ArgumentParser):
    """Argparse subclass that raises instead of ``sys.exit(2)`` on bad flags.

    ``--help`` still exits 0 (argparse's help path uses
    ``parser.exit``, not ``error()``).
    """

    def error(self, message: str) -> None:  # type: ignore[override]
        raise _ArgparseError(message)


def _build_parser() -> argparse.ArgumentParser:
    parser = _StructuredArgumentParser(
        prog="drift_ledger",
        description=(
            "Read-only queries against the drift-events ledger. "
            "Subcommands: summary, tail, triage-rate."
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

    # summary — verdict counts + outcome breakdown
    summary = subparsers.add_parser(
        "summary",
        parents=[],
        help="Print verdict counts + outcome breakdown for the window.",
    )
    summary.set_defaults(_handler=_handle_summary)

    # tail — last 10 entries pretty-printed
    tail = subparsers.add_parser(
        "tail",
        parents=[],
        help="Show last 10 ledger entries (pretty-printed JSON).",
    )
    tail.set_defaults(_handler=_handle_tail)

    # triage-rate — NFR-001 metric as a percentage
    triage = subparsers.add_parser(
        "triage-rate",
        parents=[],
        help=(
            "Compute count(JUDGMENT_REQUIRED) / count(*) as a percentage "
            "(NFR-001 metric)."
        ),
    )
    triage.set_defaults(_handler=_handle_triage_rate)

    return parser


def _emit_stderr_error(step: str, error: str) -> None:
    """Emit a structured JSON error line on stderr."""
    msg = json.dumps({"step": step, "error": error}, ensure_ascii=False)
    print(msg, file=sys.stderr)


def _handle_summary(args: argparse.Namespace) -> int:
    entries = read_window(ledger_path=args.ledger_path, days=args.days)
    total = len(entries)
    print(f"Ledger summary (last {args.days} day(s), {total} entries)")
    print("")
    print("Verdicts:")
    verdict_counts = Counter(e.verdict for e in entries)
    for verdict in sorted(VALID_VERDICTS):
        count = verdict_counts.get(verdict, 0)
        print(f"  {verdict:20s} {count}")
    print("")
    print("Outcomes:")
    outcome_counts = Counter(e.outcome for e in entries)
    for outcome in sorted(VALID_OUTCOMES):
        count = outcome_counts.get(outcome, 0)
        print(f"  {outcome:20s} {count}")
    return 0


def _handle_tail(args: argparse.Namespace) -> int:
    # Pull a generous window then keep the last 10 (chronological).
    entries = read_window(ledger_path=args.ledger_path, days=args.days)
    tail_entries = entries[-10:]
    for entry in tail_entries:
        print(json.dumps(_entry_to_dict(entry), indent=2, ensure_ascii=False))
    return 0


def _handle_triage_rate(args: argparse.Namespace) -> int:
    rate = compute_triage_rate(
        ledger_path=args.ledger_path,
        days=args.days,
    )
    # Match the operator-visible style used in contracts/ledger-schema.md.
    print(f"Triage rate ({args.days}d): {rate:.1%}")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry point.

    Exit codes per ``contracts/cli.md``::

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
        # Should never happen given ``required=True`` on subparsers.
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
