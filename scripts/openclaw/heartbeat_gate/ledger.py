"""Atomic ``last-gate-decision.json`` writer + JSONL ledger appender (WP-03 T019).

Persistence layer for the heartbeat gate. Writes two artifacts per tick:

1. ``last-gate-decision.json`` -- overwritten atomically via ``tmp+rename``.
   Operators ``cat | jq`` this to see the most recent decision. The
   atomic-write pattern mirrors ``observation/tick.py::_atomic_write_json``.
2. ``gate-ledger.jsonl`` -- append-only one-JSON-object-per-line file.
   Carries the full history for token-cost rollups and pattern analysis.

Schema is defined by ``contracts/gate-decision.contract.md`` and
``data-model.md`` §E4. The ``schema_version`` field is bumped on any
breaking change; current version is ``1``.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


__all__ = [
    "GateTickRecord",
    "SCHEMA_VERSION",
    "append_ledger",
    "atomic_write_json",
    "write_tick_record",
]


logger = logging.getLogger(__name__)


SCHEMA_VERSION = 1

_VALID_OUTCOMES: frozenset[str] = frozenset(
    {"HEARTBEAT_OK", "LOG_AND_SKIP", "ESCALATE_TO_SONNET"}
)
_VALID_HEARTBEAT_MD_STATES: frozenset[str] = frozenset({"empty", "has_tasks"})


@dataclass(frozen=True)
class GateTickRecord:
    """One heartbeat-gate tick's full record, per data-model.md §E4.

    Field order intentionally matches the contract document's worked
    example so a side-by-side diff catches schema drift early.
    """

    tick_id: str
    started_at_utc: str
    gate_latency_ms: int
    digest_snapshot_at_utc: str
    heartbeat_md_state: str
    novelty_markers_seen: list[str] = field(default_factory=list)
    outcome: str = "HEARTBEAT_OK"
    reason: str = ""
    escalated_event_id: Optional[str] = None
    gate_input_tokens: int = 0
    gate_cache_hit_tokens: int = 0
    gate_output_tokens: int = 0
    fallback_invoked: bool = False
    errors: list[dict] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        """Serialize to the ``last-gate-decision.json`` JSON shape.

        Adds the ``schema_version`` field at write time so the dataclass
        does not have to carry it as a constant field (and so a single
        constant change here propagates to all writes).
        """
        return {
            "schema_version": SCHEMA_VERSION,
            "tick_id": self.tick_id,
            "started_at_utc": self.started_at_utc,
            "gate_latency_ms": self.gate_latency_ms,
            "digest_snapshot_at_utc": self.digest_snapshot_at_utc,
            "heartbeat_md_state": self.heartbeat_md_state,
            "novelty_markers_seen": list(self.novelty_markers_seen),
            "outcome": self.outcome,
            "reason": self.reason,
            "escalated_event_id": self.escalated_event_id,
            "gate_input_tokens": self.gate_input_tokens,
            "gate_cache_hit_tokens": self.gate_cache_hit_tokens,
            "gate_output_tokens": self.gate_output_tokens,
            "fallback_invoked": self.fallback_invoked,
            "errors": list(self.errors),
        }


# ---------------------------------------------------------------------------
# Public writer API
# ---------------------------------------------------------------------------


def write_tick_record(
    record: GateTickRecord,
    last_decision_path: Path,
    ledger_path: Path,
) -> None:
    """Persist one gate tick.

    Performs two writes in this order:
    1. Atomic overwrite of ``last_decision_path``.
    2. Append one JSON line to ``ledger_path``.

    The ``last-gate-decision.json`` write happens first so a reader
    polling that path NEVER sees a stale value (the rename is atomic
    on POSIX). The ledger append happens second; a crash between the
    two writes leaves the latest-decision file consistent but the
    ledger missing one row. We accept that asymmetry as the lesser
    evil compared to a torn ``last-gate-decision.json`` write.

    Raises:
        ValueError: If ``record.outcome`` is not in the allowed enum or
            ``record.heartbeat_md_state`` is not ``"empty"``/``"has_tasks"``.
            Called only by trusted code; this is defense in depth.
    """
    _validate_record(record)
    payload = record.to_payload()
    atomic_write_json(last_decision_path, payload)
    append_ledger(ledger_path, payload)


def atomic_write_json(target: Path, payload: dict) -> None:
    """Atomically overwrite ``target`` with ``payload`` as JSON.

    Pattern mirrors ``scripts/openclaw/observation/tick.py::_atomic_write_json``:
    write a tempfile in the SAME directory (so ``os.rename`` is POSIX-atomic),
    fsync, rename, clean up on rename failure.
    """
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            dir=str(target.parent),
            prefix=target.name + ".",
            suffix=".tmp",
            delete=False,
            encoding="utf-8",
        ) as fp:
            json.dump(payload, fp, indent=2)
            fp.flush()
            os.fsync(fp.fileno())
            tmp_path = Path(fp.name)
        os.rename(tmp_path, target)
        tmp_path = None
    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink()
            except OSError:  # pragma: no cover - best-effort cleanup
                pass


def append_ledger(ledger_path: Path, payload: dict) -> None:
    """Append one JSON object as a single line to ``ledger_path``.

    Creates the file (and parent dir) if missing. Append-only -- no
    rotation here; we rely on JSONL's natural growth pattern and let
    operators rotate via systemd-tmpfiles or logrotate when needed.
    """
    ledger_path = Path(ledger_path)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(payload, ensure_ascii=False, default=str)
    with ledger_path.open("a", encoding="utf-8") as fp:
        fp.write(line)
        fp.write("\n")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_record(record: GateTickRecord) -> None:
    """Defense-in-depth schema check before any I/O.

    Catches programming errors (wrong outcome string, wrong state enum)
    BEFORE the write hits disk. The orchestrator constructs records
    with the right values; this is the belt-and-braces second check.
    """
    if record.outcome not in _VALID_OUTCOMES:
        raise ValueError(
            f"GateTickRecord.outcome must be one of {sorted(_VALID_OUTCOMES)}; "
            f"got {record.outcome!r}"
        )
    if record.heartbeat_md_state not in _VALID_HEARTBEAT_MD_STATES:
        raise ValueError(
            "GateTickRecord.heartbeat_md_state must be one of "
            f"{sorted(_VALID_HEARTBEAT_MD_STATES)}; got "
            f"{record.heartbeat_md_state!r}"
        )
