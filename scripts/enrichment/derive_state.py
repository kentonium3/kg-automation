#!/usr/bin/env python3
"""ADR-0002 Phase 7 ``derive_state`` pure function for the enrichment domain.

This module is the **sole source of truth** for the enrichment single-offer
policy from the JSONL state log angle. It reads the enrichment JSONL ledger
and returns the current state for a given ``task_id`` — or ``None`` when the
task has no recorded enrichment events.

Policy (per spec FR-014 + data-model.md E1):

    Empty ledger / no rows for the task:
        ``derive_state(task_id) -> None``

    Any rows present:
        Return the ``state`` of the newest row by ``timestamp_utc``.

Terminal-state stickiness (per spec § "State transitions" and the
single-offer policy section of the deployed tasker AGENTS.md):

    The three terminal enrichment states — ``skipped``, ``declined``,
    ``confirmed`` — are sticky. Once a task reaches any of them, the
    enrichment cycle for that task is closed. Subsequent ``proposed``
    rows for the same task (e.g., from a misbehaving reconcile) are
    ignored: the newest terminal state wins regardless of any later
    ``proposed`` rows that follow it on the timeline.

    Practically: walk the records newest-first by ``timestamp_utc``;
    the first terminal state observed is the derived state. If no
    terminal state appears, the newest record's state is returned
    (which will be ``proposed`` in the steady-state single-offer flow).

This stickiness is what enforces "annoying-but-harmless" re-proposal
suppression at the caller. Without it, a stale ``proposed`` row appended
post-terminal would re-open the cycle.

Hard-fail surface:

    Unlike escalation (which dispatches a typed ``EscalationStateError``
    on inconsistent records), enrichment's record set is intentionally
    narrow — a single tuple of ``(task_id, state, timestamp_utc, source)``
    — and the spec's Q10 soft-fail policy (FR-013) absorbs malformed
    rows during writes. ``derive_state`` therefore tolerates malformed
    lines silently (skip + continue) rather than raising. The reconcile
    sweep is the surface that surfaces malformed records for triage.

Bulk variant:

    ``derive_states_bulk`` reads the ledger once and groups records by
    ``task_id``, returning ``{task_id: state | None}`` for every requested
    id. Used by the operator-debug helper to bulk-inspect a cohort
    without re-reading the JSONL N times.

Design references:
    - kitty-specs/tasker-jsonl-migration-01KSB5XV/spec.md FR-014
    - kitty-specs/tasker-jsonl-migration-01KSB5XV/data-model.md E1
    - kitty-specs/tasker-jsonl-migration-01KSB5XV/research.md D2
    - scripts/escalation/derive_state.py (pattern source)
    - scripts/enrichment/schema.py
        :data:`VALID_STATES`, :data:`DEFAULT_LEDGER_PATH`
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable, Optional

from scripts.enrichment.schema import (
    DEFAULT_LEDGER_PATH,
    VALID_STATES,
)


__all__ = [
    "DEFAULT_LEDGER_PATH",
    "TERMINAL_STATES",
    "derive_state",
    "derive_states_bulk",
    "main",
]


# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

#: Terminal states per the single-offer policy. Mirrors the deployed tasker
#: AGENTS.md "Single-Offer Policy" section: once a task reaches any of these,
#: the enrichment cycle for that task is closed and downstream proposals are
#: suppressed.
TERMINAL_STATES: frozenset[str] = frozenset(
    {"skipped", "declined", "confirmed"}
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _iter_records(ledger_path: Path) -> Iterable[dict]:
    """Yield every JSON-decoded record from ``ledger_path``.

    Malformed lines (empty, JSON parse failure, non-dict payload) are
    skipped silently — ``derive_state`` is a read-side helper and the
    Q10 soft-fail policy (FR-013) makes the writer responsible for
    surfacing corruption. The reconcile sweep is the surface that
    operators see for malformed-record triage; this helper just walks
    past them.

    The file is read fully into memory line-by-line. The single-file
    enrichment ledger is bounded (~10 enrichment events/month per the
    spec's "Operating shape note") so the whole-file scan is acceptable.
    """
    if not ledger_path.exists():
        return
    with ledger_path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except (ValueError, TypeError):
                continue
            if not isinstance(obj, dict):
                continue
            yield obj


def _ts_key(record: dict) -> str:
    """Return the sort key for a record (``timestamp_utc`` or empty string).

    ISO-8601 strings sort lexicographically the same as chronologically when
    the offset is consistent. Records without a timestamp sort first under
    descending order; ``derive_state`` callers filter to dict records with
    valid ``timestamp_utc`` strings before relying on the ordering.
    """
    ts = record.get("timestamp_utc")
    return ts if isinstance(ts, str) else ""


def _pick_state(records: list[dict]) -> Optional[str]:
    """Pick the derived state from a list of records for ONE task.

    Walks newest-first. Terminal stickiness: the first terminal state
    observed in the newest-first walk wins. Otherwise the newest record's
    state is returned. ``None`` if the list is empty or every record is
    malformed/state-less.
    """
    if not records:
        return None
    ordered = sorted(records, key=_ts_key, reverse=True)
    # First pass: scan newest-first for any terminal state.
    for r in ordered:
        state = r.get("state")
        if isinstance(state, str) and state in TERMINAL_STATES:
            return state
    # No terminal observed — return newest record's state (typically
    # ``proposed`` in the steady-state single-offer flow). Skip rows whose
    # ``state`` is missing / non-string.
    for r in ordered:
        state = r.get("state")
        if isinstance(state, str) and state in VALID_STATES:
            return state
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def derive_state(
    task_id: int,
    ledger_path: Path = DEFAULT_LEDGER_PATH,
) -> Optional[str]:
    """Return the current enrichment state for ``task_id`` from the JSONL ledger.

    Pure read-side function: zero writes, no Vikunja calls. Reads the
    full ledger once, filters records to those matching ``task_id``,
    and returns the derived state per the single-offer policy
    (terminal-state stickiness).

    Args:
        task_id: Vikunja task ID to look up.
        ledger_path: Path to the enrichment JSONL ledger. Defaults to
            :data:`DEFAULT_LEDGER_PATH`.

    Returns:
        The derived state string (``"proposed"``, ``"confirmed"``,
        ``"skipped"``, or ``"declined"``), or ``None`` when the task
        has no recorded events.

    Raises:
        Nothing. Malformed lines are skipped silently per the module
        docstring's "Hard-fail surface" rationale.
    """
    matches: list[dict] = []
    for r in _iter_records(ledger_path):
        if r.get("task_id") == task_id:
            matches.append(r)
    return _pick_state(matches)


def derive_states_bulk(
    task_ids: list[int],
    ledger_path: Path = DEFAULT_LEDGER_PATH,
) -> dict[int, Optional[str]]:
    """Return the derived state for every id in ``task_ids`` in one pass.

    Reads the ledger once and groups records by ``task_id``. Useful for
    cohort-level reporting (e.g., "which of these 47 tasks are still
    enrichable") without N full-file scans.

    Args:
        task_ids: List of Vikunja task IDs to look up.
        ledger_path: Path to the enrichment JSONL ledger. Defaults to
            :data:`DEFAULT_LEDGER_PATH`.

    Returns:
        Dict mapping each input ``task_id`` to its derived state (or
        ``None`` when no events exist for that id). Ids not present in
        ``task_ids`` are NOT included in the output.
    """
    wanted = set(task_ids)
    grouped: dict[int, list[dict]] = {tid: [] for tid in wanted}
    for r in _iter_records(ledger_path):
        tid = r.get("task_id")
        if isinstance(tid, int) and tid in wanted:
            grouped[tid].append(r)
    return {tid: _pick_state(grouped[tid]) for tid in wanted}


# ---------------------------------------------------------------------------
# Debug CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    """Construct the argparse ``ArgumentParser`` for the debug CLI."""
    parser = argparse.ArgumentParser(
        prog="python3 -m scripts.enrichment.derive_state",
        description=(
            "Print the derived enrichment state for one task from the JSONL "
            "ledger. Operator-debug tool only; production callers import "
            "derive_state() directly."
        ),
    )
    parser.add_argument(
        "--task-id",
        type=int,
        required=True,
        help="Vikunja task id to look up.",
    )
    parser.add_argument(
        "--ledger-path",
        type=Path,
        default=DEFAULT_LEDGER_PATH,
        help=(
            "Path to the enrichment JSONL ledger "
            f"(default: {DEFAULT_LEDGER_PATH})."
        ),
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    """Debug CLI entrypoint.

    Exit codes:
        ``0`` — success; result printed to stdout as JSON
                (``{"task_id": <id>, "state": <str|null>}``).
        ``2`` — ledger path does not exist (operator-visible misconfiguration).
        ``3`` — argparse / usage error (default argparse path).
    """
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    if not args.ledger_path.exists():
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": (
                        f"ledger path does not exist: {args.ledger_path}"
                    ),
                }
            ),
            file=sys.stderr,
        )
        return 2

    state = derive_state(args.task_id, ledger_path=args.ledger_path)
    print(json.dumps({"task_id": args.task_id, "state": state}))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised via subprocess
    sys.exit(main())
