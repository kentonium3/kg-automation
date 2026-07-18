#!/usr/bin/env python3
"""Deterministic sweep-finalize path for aged-out calendar clarifications (#780).

When a captured note resolves to an appointment that has a **date but no time**
("Meet Rob Thursday"), the #739 policy asks the operator for the start time and
records a *pending clarification*. Per the #780 operator decision, if that
clarification goes **unanswered** for the 8h sweep window the appointment should
still land on the calendar — as an **all-day event** — instead of being dropped
and re-asked every window forever.

This module is the deterministic (no LLM/agent — NFR-001, Directive 6) sweep
step that runs inside the existing ``felix-admin-capture`` tick. For every
**aged-out** pending clarification record it:

1. Partitions the record into **eligible** (a resolvable all-day fallback) vs
   **ineligible** (missing title / non-timing gap / legacy no-signal) using the
   deterministic timing-only-gap predicate (:func:`is_eligible`, spec FR-005).
2. For an **eligible** record: builds a single-block all-day ``calendar``
   RoutingPlan and routes it through the #746
   ``route_and_finalize._run_finalize`` transaction (create -> log -> mark note
   processed, atomically and idempotently), then removes the pending record and
   emits a distinct ``calendar_all_day_fallback`` routing-log marker (FR-007).
3. For an **ineligible** aged-out record: applies today's **delete-and-release**
   (drop the record so the note re-scans / re-asks), consistent with the prior
   timeout semantics (C-007).
4. Leaves **non-aged-out** records untouched (the read-time release contract in
   ``handle_clarification_state.pending_filenames`` still governs them).

Fail-closed + reconciliation (spec FR-008/FR-009, INV-3/6):

- If the create/mark does **not** complete, the record is **retained** and the
  note is left unprocessed for a later sweep to retry — no partial or duplicate
  state (fail-closed).
- On retry after a partial failure in which the event **was** created and logged
  but the note mark or the record removal did not complete, the transaction's
  per-block idempotency (``RoutingLogReader.has_block``) skips the already-logged
  create; this path recognizes the reconcile (the block was ``skipped``) and
  removes the stale record **without re-creating** the event. The
  ``calendar_all_day_fallback`` marker emit is idempotent + reconcile-aware
  (``RoutingLogReader.has_kind``): it fires exactly once whenever the fallback
  event exists — including the create+log-succeed / mark-fail → reconcile
  interleaving where tick-1 never got to emit it (FR-007 durability).

Concurrency is out of scope (NFR-004): the sweep runs inside the single,
serialized capture tick, so two sweep-finalize passes never race.

Invocation form (MANDATORY per NFR-001 / [[feedback_helper_m_invocation_form]])::

    python3 -m scripts.inbox.clarification_sweep_finalize \\
        [--state-file <path>] [--account personal] [--inbox-root <dir>]

Emits a one-line JSON summary on stdout::

    {"aged_out": N, "finalized": N, "reconciled": N, "released": N,
     "retained": N}

Exit codes:
    0 = sweep ran (including records retained for a later retry — that is the
        expected fail-closed outcome, not a process error)
    1 = the state store could not be read (nothing swept)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.inbox import handle_clarification_state as hcs
from scripts.inbox import route_and_finalize
from scripts.inbox.routing_log import RoutingLogReader, RoutingLogWriter, block_hash

# The persisted eligibility vocabulary emitted by
# ``validate_calendar_event.validate`` (WP01). The canonical "date but no time"
# case yields ``missing_fields == ["start_time", "end_or_duration"]`` (both are
# *timing* fields; an all-day event needs neither), so the gate keys on
# "timing-only gap + resolved date + title", not on an exact ``["start_time"]``
# match (spec FR-005).
_TIMING_FIELDS: frozenset[str] = frozenset({"start_time", "end_or_duration"})

# The distinct, durable routing-log marker for an age-out all-day create
# (spec FR-007 / SC-004). Extends the existing ``routing_log`` ``kind``
# vocabulary rather than introducing a parallel logging scheme (C-007); it sits
# alongside ``calendar`` (a normal timed/answered create) and is separable from
# both that and a plain sweep-delete.
FALLBACK_MARKER_KIND = "calendar_all_day_fallback"

# The calendar account the fallback events land on (matches the inbox
# calendar route default).
DEFAULT_ACCOUNT = "personal"


# ---------------------------------------------------------------------------
# Eligibility (deterministic timing-only-gap predicate — spec FR-005)
# ---------------------------------------------------------------------------


def _well_formed_start_date(value: object) -> bool:
    """True iff ``value`` is a ``YYYY-MM-DD`` date string (no time component).

    A datetime string (``2026-07-20T09:00``) is rejected — the all-day payload
    must carry a pure date (C-004). Mirrors the all-day date discipline in
    ``route_calendar_event.validate_payload``.
    """
    if not isinstance(value, str):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def is_eligible(record: dict) -> bool:
    """True iff an aged-out record qualifies for the all-day fallback.

    Eligible **iff** the appointment has a resolved date and a title and the only
    unresolved fields are timing fields::

        title present
        AND well-formed YYYY-MM-DD start_date present
        AND "start_time" in missing_fields
        AND missing_fields subset of {"start_time", "end_or_duration"}

    A record lacking ``missing_fields`` or a usable ``start_date`` (legacy /
    in-flight records, or a non-timing gap such as a missing title) is **not**
    eligible — fail-closed (spec FR-002, C-002). The signal is read only from the
    persisted ``partial_payload``; nothing is re-parsed from natural language
    (determinism — NFR-001).
    """
    payload = record.get("partial_payload")
    if not isinstance(payload, dict):
        return False

    title = payload.get("title")
    if not isinstance(title, str) or not title.strip():
        return False

    if not _well_formed_start_date(payload.get("start_date")):
        return False

    missing = payload.get("missing_fields")
    if not isinstance(missing, list) or not missing:
        return False
    if "start_time" not in missing:
        return False
    return set(missing) <= _TIMING_FIELDS


# ---------------------------------------------------------------------------
# All-day plan construction (spec FR-006, C-004)
# ---------------------------------------------------------------------------


def _next_day(start_date: str) -> str:
    """Return ``start_date + 1 day`` as ``YYYY-MM-DD`` (exclusive end — C-004).

    A single-day Google all-day event uses an exclusive end date, so a one-day
    event spanning ``start_date`` ends on ``start_date + 1``.
    """
    d = datetime.strptime(start_date, "%Y-%m-%d").date()
    return (d + timedelta(days=1)).isoformat()


def build_all_day_plan(title: str, start_date: str) -> dict:
    """Build the single-block all-day ``calendar`` RoutingPlan for one record.

    The block carries a stable ``content`` (the title) so the transaction's
    per-block idempotency key (``routing_log.block_hash``) re-hashes identically
    across retries. All timed fields are omitted; only ``start_date`` /
    ``end_date`` (exclusive) are set (FR-006).
    """
    return {
        "blocks": [
            {
                "block_index": 0,
                "kind": "calendar",
                "content": title,
                "payload": {
                    "title": title,
                    "start_date": start_date,
                    "end_date": _next_day(start_date),
                },
            }
        ]
    }


# ---------------------------------------------------------------------------
# Canonical inbox path (INV-7 / Codex MED-2)
# ---------------------------------------------------------------------------


def _default_registry_path() -> Path:
    """Vault registry location, resolved relative to this helper's own file.

    Mirrors ``prescan._default_registry_path`` so both the repo-root dev/test
    layout and the office2 deploy layout resolve ``scripts/vault/paths.json``.
    """
    return Path(__file__).resolve().parent.parent / "vault" / "paths.json"


def resolve_inbox_root(override: str | None = None) -> Path:
    """Return the inbox directory used to reconstruct absolute note paths.

    Precedence: explicit ``override`` (``--inbox-root``) > ``PRESCAN_REGISTRY_PATH``
    registry > the default ``scripts/vault/paths.json`` registry. Unlike
    ``prescan.resolve_registry`` this does **not** assert the directory exists —
    it only needs the string to build a deterministic canonical path.
    """
    if override:
        return Path(override)
    reg_override = os.environ.get("PRESCAN_REGISTRY_PATH")
    registry_path = Path(reg_override) if reg_override else _default_registry_path()
    data = json.loads(registry_path.read_text(encoding="utf-8"))
    return Path(data["paths"]["inbox"])


def canonical_inbox_path(note_filename: str, inbox_root: Path) -> str:
    """Reconstruct the **one** canonical absolute inbox path for a record.

    Used identically for the ``_run_finalize`` ``source_path`` **and** — since
    that path flows verbatim to the calendar helper's idempotency key inside the
    transaction — the calendar ``--idempotency-key`` (INV-7 / Codex MED-2). The
    stored ``note_filename`` is normalized to its basename first so a basename-
    vs path-form record can never mint two distinct keys.
    """
    return str(inbox_root / os.path.basename(str(note_filename)))


# ---------------------------------------------------------------------------
# Per-record finalize (create -> log -> mark, with reconciliation)
# ---------------------------------------------------------------------------


def _block_was_skipped(result: dict) -> bool:
    """True iff the transaction skipped the (already-logged) block (reconcile).

    A ``skipped`` block means a prior run already created + logged the event, so
    this run is reconciling a stale record — it must not re-create the event. The
    ``calendar_all_day_fallback`` marker, however, is emitted here too when still
    absent (idempotent via ``has_kind``), closing the mark-fail → reconcile gap.
    """
    for block in result.get("blocks", []):
        if isinstance(block, dict) and block.get("block_index") == 0:
            return bool(block.get("skipped"))
    return False


def _artifact_of(result: dict) -> str:
    """Return the created event id from the transaction result (or "")."""
    for block in result.get("blocks", []):
        if isinstance(block, dict) and block.get("block_index") == 0:
            artifact = block.get("artifact")
            if isinstance(artifact, str):
                return artifact
    return ""


def finalize_record(
    record: dict,
    inbox_root: Path,
    account: str = DEFAULT_ACCOUNT,
    writer: RoutingLogWriter | None = None,
    reader: RoutingLogReader | None = None,
) -> str:
    """Create the all-day event for one eligible record via #746 and reconcile.

    Returns one of:
        ``"finalized"``  — a fresh all-day event was created and the note marked
                           processed; the caller removes the record.
        ``"reconciled"`` — a prior run had already created + logged the event;
                           the stale record is safe to remove without
                           re-creating.
        ``"retained"``   — the create/mark did not complete (fail-closed); the
                           caller keeps the record for a later retry.

    In **both** the fresh-``finalized`` and the ``reconciled`` branch the distinct
    ``calendar_all_day_fallback`` marker (FR-007 / SC-004) is emitted **exactly
    once** whenever the fallback event exists — the emit is idempotent and
    reconcile-aware. This closes the mark-fail → reconcile marker-loss gap: if
    tick-1 creates + logs the ``calendar`` row but ``mark_processed`` fails
    (``retained``, no marker), tick-2 reconciles and still emits the missing
    marker. Sourcing the event id differs by branch: the fresh block carries the
    ``artifact``; the skipped (reconcile) block does not, so the id comes from the
    existing ``calendar`` routing-log row for the note.

    Never double-creates and never double-marks: the transaction's per-block
    idempotency key is the backstop and the ``skipped`` detection avoids the
    pointless re-drive.
    """
    payload = record["partial_payload"]
    title = payload["title"]
    start_date = payload["start_date"]
    note_basename = os.path.basename(str(record.get("note_filename", "")))
    canonical_path = canonical_inbox_path(record.get("note_filename", ""), inbox_root)
    plan = build_all_day_plan(title, start_date)

    result, _code = route_and_finalize._run_finalize(canonical_path, plan, account)

    if result.get("status") != "finalized":
        # Before create/mark completed (error or needs_clarification) → fail
        # closed: retain the record, leave the note unprocessed (FR-008).
        return "retained"

    reconciled = _block_was_skipped(result)

    # Emit the distinct fallback marker (FR-007) idempotently: exactly once
    # whenever the fallback event exists. A fresh row read (new reader per call)
    # sees the ``calendar`` row the transaction just wrote as well as any marker
    # from a prior tick.
    log_reader = reader if reader is not None else RoutingLogReader()
    if not log_reader.has_kind(note_basename, FALLBACK_MARKER_KIND):
        if reconciled:
            # Reconcile branch: the skipped block result carries no artifact, so
            # source the event id from the existing ``calendar`` row for the note
            # (the mark-fail → reconcile path, FR-007 durability under retry).
            destination = log_reader.destination_for(note_basename, "calendar") or ""
        else:
            destination = _artifact_of(result)
        log = writer if writer is not None else RoutingLogWriter()
        log.append(
            filename=note_basename,
            note_excerpt=title,
            kind=FALLBACK_MARKER_KIND,
            destination=destination,
            block_index=0,
            block_hash=block_hash(title),
        )

    return "reconciled" if reconciled else "finalized"


# ---------------------------------------------------------------------------
# Sweep orchestration
# ---------------------------------------------------------------------------


def sweep_finalize(
    state_path: Path,
    now_utc: datetime,
    inbox_root: Path,
    account: str = DEFAULT_ACCOUNT,
) -> dict:
    """Run one sweep-finalize pass over the pending-clarification store.

    Aged-out eligible records are converted to all-day events (create -> log ->
    mark) and removed; aged-out ineligible records are delete-and-released;
    non-aged-out records are untouched; records whose create did not complete are
    retained for a later retry. The store is rewritten atomically **once** (a
    crash before the write simply reconciles on the next tick — no double
    create). Returns a counts summary.
    """
    entries = hcs.load_state(state_path)
    survivors: list = []
    counts = {"aged_out": 0, "finalized": 0, "reconciled": 0, "released": 0, "retained": 0}
    writer = RoutingLogWriter()

    for entry in entries:
        if not hcs._is_aged_out(entry.get("created_at"), now_utc):
            survivors.append(entry)  # not aged out → untouched
            continue

        counts["aged_out"] += 1

        if not is_eligible(entry):
            counts["released"] += 1  # ineligible aged-out → delete-and-release
            continue

        outcome = finalize_record(entry, inbox_root, account, writer)
        if outcome == "retained":
            survivors.append(entry)  # fail-closed → keep for retry
        counts[outcome] += 1

    if len(survivors) != len(entries):
        hcs.save_state(state_path, survivors)

    return counts


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clarification_sweep_finalize",
        description=(
            "Convert aged-out, timing-only calendar clarifications into all-day "
            "events via the #746 route_and_finalize transaction."
        ),
    )
    parser.add_argument(
        "--state-file",
        default=str(hcs.STATE_PATH_DEFAULT),
        help=(
            "Path to the pending-clarification JSON state file. Defaults to "
            f"{hcs.STATE_PATH_DEFAULT}."
        ),
    )
    parser.add_argument(
        "--account",
        default=DEFAULT_ACCOUNT,
        help=f"Calendar account for created events (default: {DEFAULT_ACCOUNT}).",
    )
    parser.add_argument(
        "--inbox-root",
        default=None,
        help=(
            "Override the inbox directory used to reconstruct absolute note "
            "paths. Defaults to the vault registry's paths.inbox."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    state_path = Path(args.state_file)
    now_utc = datetime.now(timezone.utc)

    try:
        inbox_root = resolve_inbox_root(args.inbox_root)
    except (OSError, ValueError, KeyError) as exc:
        print(
            json.dumps({"error": "inbox_root_unresolved", "detail": str(exc)}),
            file=sys.stderr,
        )
        return 1

    try:
        counts = sweep_finalize(state_path, now_utc, inbox_root, args.account)
    except (OSError, ValueError) as exc:
        print(
            json.dumps({"error": "state_unreadable", "detail": str(exc)}),
            file=sys.stderr,
        )
        return 1

    print(json.dumps(counts, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
