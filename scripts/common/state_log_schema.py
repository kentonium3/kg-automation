"""Schema constants and validation for the Felix agent state log.

This module is the pure-data half of the state-log library. It exposes:

- ``DOMAIN_STATES``: the canonical per-domain state enums (frozensets).
- ``REQUIRED_FIELDS``: the tuple of fields every record must contain.
- ``StateLogRecord``: a frozen, slotted dataclass mirroring the on-disk shape.
- ``validate_record``: short-circuit validator raising ``ValueError`` with a
  field-named, value-quoted message on the first violation.

No I/O lives here. Consumers that only need to know "what states exist" can
import this module without pulling in the file-handling layer.

Contract: ``kitty-specs/shared-jsonl-state-log-library-01KS0E9A/contracts/api.md``
Data model: ``kitty-specs/shared-jsonl-state-log-library-01KS0E9A/data-model.md``
"""
from __future__ import annotations

import datetime
import re
from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

#: Per-domain state enums. ``frozenset`` (not ``set``) for immutability —
#: callers cannot accidentally mutate the canonical vocabulary.
DOMAIN_STATES: dict[str, frozenset[str]] = {
    "habits": frozenset({"complete", "incomplete", "skipped"}),
    "escalation": frozenset(
        {"triggered", "level-1", "level-2", "resolved", "dismissed"}
    ),
    "enrichment": frozenset({"pending", "enriched", "deferred", "failed"}),
}

#: Required fields on every record. ``note`` is optional and intentionally
#: excluded.
REQUIRED_FIELDS: tuple[str, ...] = (
    "domain",
    "task_id",
    "title",
    "date",
    "state",
    "source",
    "timestamp",
)


# ---------------------------------------------------------------------------
# Dataclass mirror of the on-disk record shape
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class StateLogRecord:
    """In-memory mirror of one JSONL line.

    The dataclass is ``frozen=True`` to keep records immutable post-construction
    and ``slots=True`` to keep memory low when reading large files. Mirrors
    ``data-model.md`` § In-memory record.
    """

    domain: str
    task_id: int
    title: str
    date: str
    state: str
    source: str
    timestamp: str
    note: Optional[str] = None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_record(record: dict, domain: str) -> None:
    """Validate ``record`` against the schema and the domain's state enum.

    Raises:
        ValueError: On the first violation. The exception message names the
            offending field and quotes the rejected value so consumers can
            immediately diagnose. Validation short-circuits — multiple
            failures in one record produce one error, not a list.

    Returns:
        None on success.
    """
    # (a) domain argument is a known domain
    if domain not in DOMAIN_STATES:
        known = ", ".join(sorted(DOMAIN_STATES.keys()))
        raise ValueError(
            f"domain '{domain}' not in known domains {{{known}}}"
        )

    # (b) each REQUIRED_FIELDS field is present
    for field in REQUIRED_FIELDS:
        if field not in record:
            raise ValueError(f"required field '{field}' missing from record")

    # (c) record["domain"] matches domain argument
    rec_domain = record["domain"]
    if rec_domain != domain:
        raise ValueError(
            f"domain '{rec_domain}' on record does not match argument '{domain}'"
        )

    # (d) task_id is int and > 0
    task_id = record["task_id"]
    if not isinstance(task_id, int) or isinstance(task_id, bool):
        raise ValueError(
            f"task_id '{task_id!r}' must be int (got {type(task_id).__name__})"
        )
    if task_id <= 0:
        raise ValueError(f"task_id '{task_id}' must be a positive integer")

    # (e) title is non-empty str after strip
    title = record["title"]
    if not isinstance(title, str):
        raise ValueError(
            f"title '{title!r}' must be str (got {type(title).__name__})"
        )
    if not title.strip():
        raise ValueError(f"title '{title!r}' must be non-empty after strip")

    # (f) date matches YYYY-MM-DD and parses
    date_val = record["date"]
    if not isinstance(date_val, str) or not _DATE_RE.match(date_val):
        raise ValueError(
            f"date '{date_val!r}' must match YYYY-MM-DD"
        )
    try:
        datetime.date.fromisoformat(date_val)
    except ValueError as exc:
        raise ValueError(
            f"date '{date_val}' is not a valid ISO-8601 date: {exc}"
        ) from None

    # (g) state is in DOMAIN_STATES[domain]
    state_val = record["state"]
    allowed_states = DOMAIN_STATES[domain]
    if state_val not in allowed_states:
        allowed_str = ", ".join(sorted(allowed_states))
        raise ValueError(
            f"state '{state_val}' not in {domain} enum {{{allowed_str}}}"
        )

    # (h) source is non-empty str
    source_val = record["source"]
    if not isinstance(source_val, str):
        raise ValueError(
            f"source '{source_val!r}' must be str "
            f"(got {type(source_val).__name__})"
        )
    if not source_val:
        raise ValueError(f"source '{source_val!r}' must be non-empty")

    # (i) timestamp parses via datetime.datetime.fromisoformat and has tzinfo
    ts_val = record["timestamp"]
    if not isinstance(ts_val, str):
        raise ValueError(
            f"timestamp '{ts_val!r}' must be str "
            f"(got {type(ts_val).__name__})"
        )
    try:
        parsed_ts = datetime.datetime.fromisoformat(ts_val)
    except ValueError as exc:
        raise ValueError(
            f"timestamp '{ts_val}' is not a valid ISO-8601 datetime: {exc}"
        ) from None
    if parsed_ts.tzinfo is None:
        raise ValueError(
            f"timestamp '{ts_val}' must include a timezone offset"
        )

    # (j) if note is present, must be str or explicitly None
    if "note" in record:
        note_val = record["note"]
        if note_val is not None and not isinstance(note_val, str):
            raise ValueError(
                f"note '{note_val!r}' must be str or None "
                f"(got {type(note_val).__name__})"
            )
