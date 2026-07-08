"""INV-006 historical-fidelity replay harness (#676 T007).

Replays the deterministic escalation rule (``gate.decide_deterministic``)
over a gate-ledger JSONL file and asserts the **historical-fidelity
invariant** from ``kitty-specs/deterministic-monitoring-checks-01KX1XNW/
contracts/escalation-rule.contract.md``:

    escalate(r.novelty_markers_seen, r.heartbeat_md_state, r.errors)
        == (r.outcome == "ESCALATE_TO_SONNET")

for every record ``r`` in the ledger.

Scope (contract, "Historical-fidelity invariant" scope note): the ledger
persists only the escalation-relevant fields (``novelty_markers_seen``,
``heartbeat_md_state``, ``errors``) -- NOT ``issues_filed`` or per-signal
counts. This harness therefore validates the **escalate vs. not-escalate
boolean ONLY** (the sole cost-bearing decision). It does NOT validate the
``LOG_AND_SKIP`` vs. ``HEARTBEAT_OK`` sub-label split -- that split is
covered separately by synthetic ``GateContext`` fixtures in
``tests/test_validate_ledger.py``.

The escalation boolean is **imported, not reimplemented**: this module
calls ``gate.decide_deterministic`` (the same function ``run.py`` calls in
production) via a minimal shim object exposing the three fields the
predicate reads (``novelty_markers``, ``heartbeat_md_state``, ``errors``).
This keeps the replay and the production decision as a single source of
truth that can never drift apart.

CLI usage (module form -- office2 is python3-only, C-006)::

    python3 -m scripts.openclaw.heartbeat_gate.validate_ledger \\
        --ledger /data/services/openclaw/felix-heartbeat-gate/gate-ledger.jsonl

Exit codes:
    0 -- missed == 0 AND over-escalation rate <= the NFR-006 threshold (5%).
    1 -- missed > 0 (the historical-fidelity invariant is violated), or the
         over-escalation rate exceeds the threshold, or the ledger could
         not be read/parsed.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Optional

from scripts.openclaw.heartbeat_gate.gate import decide_deterministic


__all__ = [
    "OVER_ESCALATION_THRESHOLD_PCT",
    "ReplayResult",
    "iter_ledger_records",
    "main",
    "replay_ledger",
]


# NFR-006: over-escalation is reported unconditionally, but only fails the
# gate above this threshold.
OVER_ESCALATION_THRESHOLD_PCT = 5.0


@dataclass(frozen=True)
class _ReplayContext:
    """Minimal shim exposing exactly the attributes
    ``gate.decide_deterministic`` reads to compute the escalate boolean.

    Deliberately NOT a full ``GateContext`` -- the ledger does not carry
    ``issues_filed`` or ``signals_evaluated``, so this shim's
    ``issues_filed`` and ``signals_evaluated`` are always empty. That is
    fine for this module's purpose: only the escalate/not-escalate
    boolean is asserted (see module docstring "Scope").
    """

    novelty_markers: list[str] = field(default_factory=list)
    heartbeat_md_state: str = "empty"
    errors: list[Any] = field(default_factory=list)
    issues_filed: list[Any] = field(default_factory=list)
    signals_evaluated: list[Any] = field(default_factory=list)


@dataclass(frozen=True)
class ReplayResult:
    """Outcome of replaying one gate-ledger over the shared escalate rule."""

    total: int
    actual_escalate: int
    actual_non_escalate: int
    missed: int
    """Records where ``outcome == ESCALATE_TO_SONNET`` but the recomputed
    boolean says "no escalate". This is the INV-006 gate: must be 0."""
    over: int
    """Records where ``outcome != ESCALATE_TO_SONNET`` but the recomputed
    boolean says "escalate". Reported; fails only above threshold."""
    missed_tick_ids: list[str] = field(default_factory=list)
    over_tick_ids: list[str] = field(default_factory=list)

    @property
    def over_escalation_pct(self) -> float:
        """Over-escalations as a percentage of all records.

        Percentage of total (not of non-escalating records) so the
        reported rate is stable even when the ledger is all-escalate or
        all-quiet; ``0.0`` when the ledger is empty.
        """
        if self.total == 0:
            return 0.0
        return (self.over / self.total) * 100.0

    @property
    def passed(self) -> bool:
        """True iff 0 missed AND over-escalation is within threshold."""
        return (
            self.missed == 0
            and self.over_escalation_pct <= OVER_ESCALATION_THRESHOLD_PCT
        )


# ---------------------------------------------------------------------------
# Ledger reading
# ---------------------------------------------------------------------------


def iter_ledger_records(ledger_path: Path) -> Iterator[dict]:
    """Yield one parsed JSON object per non-blank line of ``ledger_path``.

    Raises
    ------
    FileNotFoundError
        If ``ledger_path`` does not exist.
    json.JSONDecodeError
        If any non-blank line is not valid JSON. The line number is
        included via the exception's own ``lineno`` reporting relative to
        that line's content; callers that want the ledger's line number
        should catch and re-wrap if needed.
    """
    with ledger_path.open("r", encoding="utf-8") as fp:
        for raw_line in fp:
            line = raw_line.strip()
            if not line:
                continue
            yield json.loads(line)


# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------


def _recompute_escalate(record: dict) -> bool:
    """Recompute the escalate boolean for one ledger record via the SHARED
    predicate (``gate.decide_deterministic``) -- never reimplemented here.
    """
    shim = _ReplayContext(
        novelty_markers=list(record.get("novelty_markers_seen") or []),
        heartbeat_md_state=record.get("heartbeat_md_state") or "empty",
        errors=list(record.get("errors") or []),
    )
    decision = decide_deterministic(shim)
    return decision.outcome == "ESCALATE_TO_SONNET"


def replay_ledger(records: Iterator[dict]) -> ReplayResult:
    """Replay ``records`` (an iterable of ledger-record dicts) over the
    shared escalate predicate and tally missed / over-escalations.

    A "missed" escalation is a false negative relative to history: the
    ledger says ``ESCALATE_TO_SONNET`` actually fired, but recomputing the
    boolean from the same record's fields says it should not have. This
    is the INV-006 gate -- it must be 0.

    An "over"-escalation is the opposite false-positive case: the ledger
    recorded a non-escalating outcome, but recomputing says it should
    have escalated. This is reported (NFR-006) but only fails the gate
    above ``OVER_ESCALATION_THRESHOLD_PCT``.
    """
    total = 0
    actual_escalate = 0
    missed = 0
    over = 0
    missed_tick_ids: list[str] = []
    over_tick_ids: list[str] = []

    for record in records:
        total += 1
        actual_is_escalate = record.get("outcome") == "ESCALATE_TO_SONNET"
        if actual_is_escalate:
            actual_escalate += 1
        recomputed_is_escalate = _recompute_escalate(record)

        if actual_is_escalate and not recomputed_is_escalate:
            missed += 1
            missed_tick_ids.append(str(record.get("tick_id", "")))
        elif not actual_is_escalate and recomputed_is_escalate:
            over += 1
            over_tick_ids.append(str(record.get("tick_id", "")))

    return ReplayResult(
        total=total,
        actual_escalate=actual_escalate,
        actual_non_escalate=total - actual_escalate,
        missed=missed,
        over=over,
        missed_tick_ids=missed_tick_ids,
        over_tick_ids=over_tick_ids,
    )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _summary_lines(result: ReplayResult) -> list[str]:
    return [
        f"total={result.total} "
        f"actual_escalate={result.actual_escalate} "
        f"actual_non_escalate={result.actual_non_escalate}",
        f"missed={result.missed} "
        f"over={result.over} "
        f"over_pct={result.over_escalation_pct:.2f}% "
        f"threshold={OVER_ESCALATION_THRESHOLD_PCT:.2f}%",
    ]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="heartbeat_gate.validate_ledger",
        description=(
            "Replay the deterministic escalation rule over a gate-ledger "
            "and assert 0 missed escalations (INV-006)."
        ),
    )
    parser.add_argument(
        "--ledger",
        type=Path,
        required=True,
        help="path to a gate-ledger.jsonl file to replay",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    ledger_path: Path = args.ledger
    try:
        result = replay_ledger(iter_ledger_records(ledger_path))
    except FileNotFoundError:
        print(f"ERROR: ledger not found at {ledger_path}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"ERROR: malformed JSONL in {ledger_path}: {exc}", file=sys.stderr)
        return 1

    for line in _summary_lines(result):
        print(line)

    if result.missed > 0:
        print(
            f"FAIL: {result.missed} missed escalation(s): "
            f"{', '.join(result.missed_tick_ids)}",
            file=sys.stderr,
        )
        return 1

    if result.over_escalation_pct > OVER_ESCALATION_THRESHOLD_PCT:
        print(
            "FAIL: over-escalation rate "
            f"{result.over_escalation_pct:.2f}% exceeds threshold "
            f"{OVER_ESCALATION_THRESHOLD_PCT:.2f}%",
            file=sys.stderr,
        )
        return 1

    print("PASS: 0 missed escalations; over-escalation within threshold.")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())
