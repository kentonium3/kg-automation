"""Enrichment domain schema (ADR-0002 Phase 7).

This module is the canonical record shape for the enrichment JSONL substrate
(``/data/services/openclaw/state/enrichment/enrichment-history.jsonl``). It
mirrors the dataclass-based contract from data-model.md E1.

Unlike escalation (which carries per-event_type structured parameters), the
enrichment record set is intentionally narrow: a single tuple of
``(task_id, state, timestamp_utc, source[, note])`` per state transition. The
single-offer policy enforces terminal states (``skipped`` / ``declined`` never
re-propose), and the helper layer (``record_completion``) is the sole writer.

Reviewer surface (NFR-005): every constant required to read or write the
enrichment ledger is enumerated here so a reviewer reading this file alone can
answer "what does an enrichment JSONL row look like?" without running tests.

Design references:
    - kitty-specs/tasker-jsonl-migration-01KSB5XV/data-model.md E1
    - kitty-specs/tasker-jsonl-migration-01KSB5XV/spec.md FR-001..FR-005
    - scripts/escalation/schema.py (pattern source — per-event_type variant)
"""
from __future__ import annotations

from dataclasses import MISSING, asdict, dataclass, fields
from pathlib import Path
from typing import Optional


__all__ = [
    "DEFAULT_LEDGER_PATH",
    "EnrichmentCompletion",
    "EnrichmentSchemaError",
    "SCHEMA_VERSION",
    "VALID_SOURCES",
    "VALID_STATES",
    "validate_record",
]


# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

#: Schema version embedded in every JSONL row. Bump on incompatible shape
#: changes; the helper layer pins to ``SCHEMA_VERSION`` at write-time so
#: down-stream readers can dispatch on the field cleanly.
SCHEMA_VERSION: int = 1

#: Valid enrichment states. Locked to the deployed tasker AGENTS.md
#: vocabulary verified during #310 spec-readiness. ``proposed`` is the
#: opening state; ``confirmed`` / ``skipped`` / ``declined`` are terminal.
VALID_STATES: frozenset[str] = frozenset(
    {"proposed", "confirmed", "skipped", "declined"}
)

#: Valid record provenance. Mirrors the escalation source set with
#: enrichment-specific entries — ``agent`` is the live runtime writer,
#: ``reconcile`` / ``backfill`` are the JSONL-only catch-up paths, and
#: ``operator_repair`` covers manual JSONL fix-ups during triage.
VALID_SOURCES: frozenset[str] = frozenset(
    {"agent", "reconcile", "backfill", "operator_repair"}
)

#: Default location of the JSONL ledger on office2. Single file per the
#: data-model (NOT per-project — enrichment is a system-wide vertical).
DEFAULT_LEDGER_PATH: Path = Path(
    "/data/services/openclaw/state/enrichment/enrichment-history.jsonl"
)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class EnrichmentSchemaError(Exception):
    """Raised when an enrichment record fails schema validation.

    The message names the offending field and quotes the rejected value
    so an operator triaging a CLI exit code 3 can fix the input quickly.
    """


# ---------------------------------------------------------------------------
# Dataclass (data-model E1 — field ORDER is canonical)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EnrichmentCompletion:
    """One enrichment state event for a Vikunja task.

    Field order is canonical (data-model.md E1) — JSONL serialization uses
    ``json.dumps(asdict(rec), sort_keys=False)`` so the on-disk column order
    matches this dataclass definition for deterministic diffing.

    Attributes:
        task_id: Vikunja task ID (positive integer).
        state: One of :data:`VALID_STATES`.
        timestamp_utc: ISO 8601 instant with explicit UTC offset (``Z`` or
            ``+00:00`` suffix).
        source: One of :data:`VALID_SOURCES`.
        schema_version: Schema version for this row. Defaults to
            :data:`SCHEMA_VERSION`.
        note: Optional free-text note. May be ``None``.
    """

    task_id: int
    state: str
    timestamp_utc: str
    source: str
    schema_version: int = SCHEMA_VERSION
    note: Optional[str] = None

    def to_dict(self) -> dict:
        """Return the record as a plain dict in canonical field order.

        Used by the helper layer to build the JSONL line; the resulting
        ordering matches the dataclass field declaration order so the
        serialized output is deterministic across machines.
        """
        return asdict(self)


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


_REQUIRED_FIELDS: tuple[str, ...] = tuple(
    f.name
    for f in fields(EnrichmentCompletion)
    if f.default is MISSING and f.default_factory is MISSING
)
# NOTE: ``note`` has default ``None`` and ``schema_version`` has a numeric
# default; both are optional. The four positional fields without defaults
# (``task_id``, ``state``, ``timestamp_utc``, ``source``) are required.


def validate_record(record: dict) -> None:
    """Validate an enrichment record dict against the schema.

    Short-circuits on the first violation. Intended as the standalone
    validator used by the helper layer BEFORE any side-effect runs. Records
    that pass here are safe to serialize via :func:`json.dumps`.

    Validation steps (in order):

    a. All required fields present (``task_id``, ``state``, ``timestamp_utc``,
       ``source``).
    b. ``task_id``: int > 0 (no ``bool`` accepted — ``bool`` is a Python
       int subclass and would otherwise silently pass).
    c. ``state``: str in :data:`VALID_STATES`.
    d. ``source``: str in :data:`VALID_SOURCES`.
    e. ``timestamp_utc``: non-empty str (helper layer mints these via
       ``datetime.utcnow().isoformat()``; we don't re-parse here — the row
       is opaque to downstream readers besides the dispatch fields).
    f. ``note``: str or None when present.
    g. ``schema_version``: int when present (defaults to
       :data:`SCHEMA_VERSION`).

    Args:
        record: Candidate enrichment record dict.

    Raises:
        EnrichmentSchemaError: On the first violation. Message names the
            offending field and quotes the rejected value.
    """
    # (a) required fields present
    for field in _REQUIRED_FIELDS:
        if field not in record:
            raise EnrichmentSchemaError(
                f"required field '{field}' missing from record"
            )

    # (b) task_id: int > 0
    task_id = record["task_id"]
    if isinstance(task_id, bool) or not isinstance(task_id, int):
        raise EnrichmentSchemaError(
            f"task_id '{task_id!r}' must be int "
            f"(got {type(task_id).__name__})"
        )
    if task_id <= 0:
        raise EnrichmentSchemaError(
            f"task_id '{task_id}' must be a positive integer"
        )

    # (c) state: known string
    state = record["state"]
    if not isinstance(state, str):
        raise EnrichmentSchemaError(
            f"state '{state!r}' must be str (got {type(state).__name__})"
        )
    if state not in VALID_STATES:
        known = ", ".join(sorted(VALID_STATES))
        raise EnrichmentSchemaError(
            f"state '{state}' not in enrichment states {{{known}}}"
        )

    # (d) source: known string
    source = record["source"]
    if not isinstance(source, str):
        raise EnrichmentSchemaError(
            f"source '{source!r}' must be str (got {type(source).__name__})"
        )
    if source not in VALID_SOURCES:
        known = ", ".join(sorted(VALID_SOURCES))
        raise EnrichmentSchemaError(
            f"source '{source}' not in enrichment sources {{{known}}}"
        )

    # (e) timestamp_utc: non-empty string
    timestamp = record["timestamp_utc"]
    if not isinstance(timestamp, str):
        raise EnrichmentSchemaError(
            f"timestamp_utc '{timestamp!r}' must be str "
            f"(got {type(timestamp).__name__})"
        )
    if not timestamp.strip():
        raise EnrichmentSchemaError(
            "timestamp_utc must be a non-empty ISO-8601 instant"
        )

    # (f) note: str or None
    if "note" in record and record["note"] is not None:
        if not isinstance(record["note"], str):
            raise EnrichmentSchemaError(
                f"note '{record['note']!r}' must be str or None "
                f"(got {type(record['note']).__name__})"
            )

    # (g) schema_version: int
    if "schema_version" in record:
        sv = record["schema_version"]
        if isinstance(sv, bool) or not isinstance(sv, int):
            raise EnrichmentSchemaError(
                f"schema_version '{sv!r}' must be int "
                f"(got {type(sv).__name__})"
            )
