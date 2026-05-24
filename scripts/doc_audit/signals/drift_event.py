"""``DriftEventSignalSource`` — adapter for audit.sh drift events.

Realizes the ``SignalSource`` Protocol from
``contracts/signal-source.contract.md`` for the drift-event surface
emitted by ``audit.sh`` into
``/data/services/security-monitor/logs/drift-events.jsonl``.

Approach:

    ``pending()`` reads ``drift-events.jsonl`` from the cursor position
    to EOF and constructs one :class:`Signal` per unprocessed event
    WITHOUT advancing the cursor or performing side effects. The
    helper's :func:`doc_audit.helpers.handle_drift_events.find_mapping`
    is used to classify each event so signal payloads carry the same
    mapping decision the helper would make in ``process_events``.

    ``commit()`` invokes the helper's atomic primitives
    (:func:`find_mapping`, :func:`file_doc_audit_issue`,
    :func:`append_unmapped`, :func:`write_cursor_atomic`) for the
    specific event the signal points at. This mirrors what
    ``process_events`` does per-event without re-implementing
    classification, issue filing, unmapped routing, or atomic cursor
    persistence — behavior matches the helper canonically. We use the
    primitives directly (rather than calling ``process_events`` with a
    one-event window) to avoid double-traversing the events file: the
    enumeration already happened in :meth:`pending`.

This adapter:
- DOES file ``[doc-audit]`` issues here, via
  :func:`file_doc_audit_issue`. This is the same surface the legacy
  CLI uses. The resulting GH issues flow back into next-tick signals
  via ``GHIssueSignalSource``.
- DOES route unmapped events via :func:`append_unmapped`. Same
  bookkeeping the helper performs.
- DOES advance the cursor via :func:`write_cursor_atomic` only after
  the corresponding side effect succeeds, so a failed file/append
  leaves the cursor where it was and the event retries next tick.

Cursor monotonicity (cycle 3 fix):

    The driver may commit signals from a single source in any order
    relative to drift-event file line number (it sorts pending signals
    by ``(priority, created_utc)``, and timestamps inside
    ``drift-events.jsonl`` may tie or arrive out of monotonic order).
    To preserve "no event is ever skipped", :meth:`commit` records each
    successful side effect in an in-memory buffer and then *drains
    consecutively*: starting at the current on-disk cursor, the cursor
    advances past every line that is either (a) recorded as committed
    in this adapter instance, or (b) classified as non-signal by
    :meth:`pending` (blank lines, malformed JSON). Drain stops at the
    first signal-bearing line whose commit has not yet been recorded.
    A late-arriving earlier commit therefore "fills the gap" and the
    cursor jumps forward through the now-contiguous committed range —
    never past an uncommitted signal.

Failure modes:
- Missing ``drift-events.jsonl`` is normal (drift events are
  optional) → :meth:`pending` returns ``[]`` without error.
- Missing cursor file is treated as cursor=0 (process from
  beginning).
- Malformed JSON lines are skipped with a warning in :meth:`pending`;
  the cursor advances past them on the next successful :meth:`commit`
  drain so they don't block forward progress.
- Missing or unreadable ``signal-to-doc-map.json`` raises (mapping is
  required for canonical classification; this is a configuration
  error, not a transient drift-event issue).
- ``file_doc_audit_issue`` failures (``gh`` non-zero exit, timeout)
  surface as a ``RuntimeError`` from :meth:`commit`; the cursor is
  NOT advanced and the event is NOT recorded as committed, so it
  retries next tick.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

from doc_audit.config import Config
from doc_audit.data_model import Signal
from doc_audit.helpers.handle_drift_events import (
    Mapping,
    append_unmapped,
    file_doc_audit_issue,
    find_mapping,
    load_mappings,
    read_cursor,
    write_cursor_atomic,
)
from doc_audit.judgment.client import JudgmentClient
from doc_audit.judgment.drift_interpretation import DriftInterpretationError
from doc_audit.output.drift_ledger import AuditLedgerEntry, RETRY_MAX_ATTEMPTS
from doc_audit.output.drift_ledger import append as ledger_append
from doc_audit.routing.drift_moment0 import (
    _build_judgment_client,
    _resolve_repo_root,
    route_drift_event,
)
from doc_audit.signals.base import Outcome

import logging
import time
from datetime import datetime, timezone

_logger = logging.getLogger(__name__)


def _now_utc_iso() -> str:
    """Return the current UTC time as an ISO 8601 ``Z``-suffixed string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class DriftEventSignalSource:
    """Adapter producing :class:`Signal` instances from drift events.

    Cursor semantics:
    - ``self._cursor_base`` is the cursor read at construction (or
      first :meth:`pending` call). Signal IDs encode the absolute
      line number in ``drift-events.jsonl`` so that :meth:`commit`
      can compute the post-commit cursor without relying on
      iteration order.

    Side-effect surface:
    - :meth:`pending` is read-only.
    - :meth:`commit` invokes :func:`find_mapping`,
      :func:`file_doc_audit_issue` (or :func:`append_unmapped`), and
      :func:`write_cursor_atomic` — the same primitives the helper's
      :func:`process_events` orchestrator uses per event.
    """

    name = "drift_event"

    def __init__(self, config: Config) -> None:
        self.config = config
        self._events_path = Path(config.paths.drift_events)
        self._cursor_path = Path(config.paths.drift_cursor)
        self._mapping_path = Path(config.paths.signal_to_doc_map)
        self._unmapped_path = Path(config.paths.drift_unmapped)
        self._repo = config.github.repo
        self._cached: Optional[list[Signal]] = None
        # Cursor at the moment pending() was first called this tick.
        # Used to validate that commits are within the expected
        # window and to support the missing-cursor-file case.
        self._cursor_base: Optional[int] = None
        # Mappings are loaded lazily on first need (pending() or
        # commit()) and cached for the adapter's lifetime — one load
        # per tick.
        self._mappings_cache: Optional[list[Mapping]] = None
        # Set of line indices that pending() emitted as signals this
        # tick. Drain logic uses this to distinguish "signal line not
        # yet committed (blocks drain)" from "non-signal line (blank /
        # malformed; safe to drain past)".
        self._signal_lines: set[int] = set()
        # Largest line index pending() examined this tick (file length
        # minus one, or -1 if the file was empty/missing). Drain never
        # advances cursor past ``_max_line_examined + 1`` — that is the
        # safe upper bound for "events the adapter has seen this tick."
        self._max_line_examined: int = -1
        # Lines that commit() successfully processed this tick (side
        # effect ran without raising). Drain advances cursor through
        # lines that are EITHER in this set OR not in
        # ``_signal_lines`` (non-signal lines are always safe to drain
        # past once a neighboring signal has committed).
        self._committed_lines: set[int] = set()
        # Lazily-constructed Moment 0 JudgmentClient. Stays None when
        # ``[drift_interpretation].enabled = False`` (FR-010 — no API
        # key file is read, no Anthropic SDK construction). One client
        # per adapter lifetime when enabled (D2).
        self._judgment_client: Optional[JudgmentClient] = None

    def _get_judgment_client(self) -> JudgmentClient:
        """Lazily construct and cache a JudgmentClient for this tick.

        Per D2 + FR-009: one client per adapter instance (tick lifetime).
        Per FR-010: callers MUST gate on
        ``self.config.drift_interpretation.enabled`` before invoking
        this method — when disabled, no client is ever constructed.

        Delegates to ``routing.drift_moment0._build_judgment_client``
        so the construction path is identical to the library/CLI
        surface (``handle_drift_events.process_events``) and tests can
        monkeypatch the single helper for both.
        """
        if self._judgment_client is None:
            self._judgment_client = _build_judgment_client(self.config)
        return self._judgment_client

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_mappings(self) -> list[Mapping]:
        """Load and cache mappings via the helper's :func:`load_mappings`.

        Raised errors (missing/unreadable mapping file, malformed JSON)
        propagate per the SignalSource contract — these are
        configuration failures, not "no work to do."
        """
        if self._mappings_cache is None:
            self._mappings_cache = load_mappings(self._mapping_path)
        return self._mappings_cache

    # ------------------------------------------------------------------
    # Protocol surface
    # ------------------------------------------------------------------

    def pending(self) -> list[Signal]:
        """Return one :class:`Signal` per unprocessed drift event.

        Missing ``drift-events.jsonl`` returns ``[]`` — drift events
        are optional. Missing cursor file is treated as cursor=0.

        DOES NOT advance the cursor and DOES NOT perform side effects
        (no issue filing, no unmapped logging) — those happen in
        :meth:`commit`.
        """
        if self._cached is not None:
            return self._cached

        cursor = read_cursor(self._cursor_path)
        self._cursor_base = cursor

        if not self._events_path.exists():
            self._cached = []
            return self._cached

        try:
            lines = self._events_path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            # I/O errors propagate — this is a connectivity-style
            # failure per the signal-source contract anti-patterns.
            raise OSError(
                f"Failed to read drift events at {self._events_path}: {exc}"
            ) from exc

        # Track the highest line index we examined so drain logic
        # knows the safe upper bound for cursor advance. -1 means we
        # examined nothing (file shorter than cursor).
        self._max_line_examined = len(lines) - 1

        # Load mappings via the helper so classification preview here
        # matches what commit() will route on. If the mapping file is
        # missing/unreadable this raises — configuration failure, per
        # contract.
        mappings = self._get_mappings()

        signals: list[Signal] = []
        for index, raw in enumerate(lines[cursor:], start=cursor):
            stripped = raw.strip()
            if not stripped:
                # Blank lines are valid (and drain on commit too); the
                # driver doesn't see them as signals.
                continue
            try:
                event = json.loads(stripped)
            except json.JSONDecodeError as exc:
                print(
                    f"WARN: drift-event line {index} is malformed JSON: {exc}",
                    file=sys.stderr,
                )
                continue
            timestamp = event.get("timestamp", "")
            baseline = event.get("baseline_name", "unknown")
            # Classify with the helper's find_mapping so the signal
            # payload carries the canonical mapping decision; this
            # ensures parity with what commit() will route on.
            mapping = find_mapping(event, mappings)
            mapping_id = mapping.id if mapping is not None else None
            # Record this index as a signal-bearing line so drain knows
            # it must NOT be passed over until its commit lands.
            self._signal_lines.add(index)
            signals.append(
                Signal(
                    # Line-number-anchored ID lets commit() resolve
                    # exactly which cursor position this signal sits
                    # at without re-parsing the file.
                    id=f"drift:{baseline}:{timestamp}:line{index}",
                    source=self.name,
                    kind="drift_event",
                    priority=40,
                    payload={
                        "line_number": index,
                        "timestamp": timestamp,
                        "source": event.get("source", ""),
                        "event_type": event.get(
                            "event_type", "baseline_drift"
                        ),
                        "baseline_name": baseline,
                        "diff_b64": event.get("diff_b64", ""),
                        "diff": event.get("diff", ""),
                        "raw_event": event,
                        "mapping_id": mapping_id,
                    },
                    created_utc=timestamp,
                )
            )

        self._cached = signals
        return signals

    def commit(self, signal: Signal, outcome: Outcome) -> None:
        """Process ``signal`` via the helper's atomic primitives.

        Performs the same per-event work :func:`process_events` does:

        1. :func:`find_mapping` against the loaded mapping table.
        2. If a mapping matches → :func:`file_doc_audit_issue` (real
           filing, ``dry_run=False``).
        3. If no mapping → :func:`append_unmapped` (route to AI review
           log).
        4. Record the line as committed, then drain consecutively and
           :func:`write_cursor_atomic` to advance the cursor through
           every contiguous committed-or-non-signal line starting at
           the current on-disk cursor.

        Cursor monotonicity:

        - A signal whose ``line_number < current_cursor`` is a no-op
          (idempotent re-commit on an already-passed line).
        - A re-commit of a line already in the committed buffer is a
          no-op (idempotent retry within the same tick).
        - The drain advances cursor ONLY through consecutive lines
          that are (a) recorded in the committed buffer or (b) NOT in
          ``_signal_lines`` (blank/malformed lines pending() classified
          as non-signal). It stops at the first signal-bearing line
          whose commit has not yet landed — so an out-of-order commit
          NEVER skips an earlier unprocessed event. When the earlier
          commit eventually arrives, drain jumps forward through the
          newly-contiguous committed range in one atomic cursor write.

        ``signal`` must carry a ``line_number`` and ``raw_event`` in
        its payload (set by :meth:`pending`).
        """
        line_number = signal.payload.get("line_number")
        if not isinstance(line_number, int):
            raise ValueError(
                "DriftEventSignalSource.commit: signal payload is "
                "missing the line_number set by pending() (got "
                f"{line_number!r})."
            )

        current = read_cursor(self._cursor_path)

        # Idempotent re-commit on an already-passed line. The cursor
        # has already advanced past this signal; the side effect (file
        # or append) ran on the prior commit. Nothing to do.
        if line_number < current:
            return None

        # Idempotent re-commit within the same tick — the side effect
        # already ran. Drain again in case the cursor on disk has not
        # been advanced yet (e.g., a prior drain was interrupted) but
        # do not re-run filing/appending.
        if line_number in self._committed_lines:
            self._drain(current)
            return None

        event = signal.payload.get("raw_event")
        if isinstance(event, dict):
            mappings = self._get_mappings()
            mapping = find_mapping(event, mappings)

            if mapping is None:
                # No mapping → append to unmapped log for AI review
                # (same bookkeeping as process_events does).
                append_unmapped(self._unmapped_path, event)
            elif self.config.drift_interpretation.enabled:
                # Moment 0 path (#391): route the event through the
                # shared helper which invokes drift_interpretation +
                # tier_classification + ledger append. On retry
                # exhaustion, falls back to the pre-#362 path with a
                # RETRY_EXHAUSTED ledger row.
                self._invoke_moment0(event, mapping, line_number)
            else:
                # Pre-#362 fallback path (FR-002 / FR-010 — flag
                # disabled means no JudgmentClient construction either).
                ok, output = file_doc_audit_issue(
                    event, mapping, self._repo, dry_run=False
                )
                if not ok:
                    # Filing failed — surface the error and leave both
                    # the cursor and the committed-buffer untouched so
                    # the event is retried next tick.
                    raise RuntimeError(
                        f"file_doc_audit_issue failed for mapping="
                        f"{mapping.id} line={line_number}: {output}"
                    )
        # else: blank/unparseable line carrying no event payload — no
        # side effect to perform, but we still record the line as
        # "committed" so the drain can pass over it. (In normal
        # operation pending() never emits signals for blank/malformed
        # lines; this branch is a defensive guard.)

        # Side effect succeeded (or there wasn't one) — record this
        # line as committed, then advance the cursor through every
        # contiguous committed-or-non-signal line.
        self._committed_lines.add(line_number)
        self._drain(current)
        return None

    def _invoke_moment0(
        self, event: dict, mapping: Mapping, line_number: int
    ) -> None:
        """Run the Moment 0 pipeline for one mapped drift event.

        Calls the shared helper ``route_drift_event`` which performs
        Moment 0 LLM judgment, tier-classification routing, and ledger
        append. On ``DriftInterpretationError`` (retry exhausted),
        writes a ``RETRY_EXHAUSTED`` ledger row and falls back to the
        pre-#362 ``file_doc_audit_issue`` path with the diagnostic
        block in the body (FR-006 / FR-009).

        Cursor advance happens in the caller (``commit``); this method
        does NOT touch cursor or ``_committed_lines``. It raises on
        unrecoverable filing failure so caller leaves the line
        uncommitted for retry next tick — same semantics as the
        pre-#362 path.
        """
        timestamp = str(event.get("timestamp", _now_utc_iso()))
        if not timestamp.endswith("Z") and "T" not in timestamp:
            timestamp = _now_utc_iso()
        event_id = f"{line_number}:{timestamp}"
        ledger_path = Path(self.config.drift_interpretation.ledger_path)
        repo_root = _resolve_repo_root()

        try:
            route_drift_event(
                event=event,
                mapping=mapping,
                config=self.config,
                client=self._get_judgment_client(),
                ledger_path=ledger_path,
                repo=self._repo,
                event_id=event_id,
                timestamp_utc=timestamp,
                cursor_line=line_number,
                repo_root=repo_root,
            )
        except DriftInterpretationError as exc:
            # Retry exhausted — record RETRY_EXHAUSTED in the ledger
            # and fall back to the pre-#362 issue-filing path with the
            # diagnostic block included in the issue body (FR-006).
            _logger.error(
                "Moment 0 retry exhausted for event %s (mapping=%s): %s",
                event_id,
                mapping.id,
                exc,
            )

            try:
                ledger_append(
                    AuditLedgerEntry(
                        event_id=event_id,
                        timestamp_utc=_now_utc_iso(),
                        baseline=str(
                            event.get("baseline_name", event.get("baseline", "unknown"))
                        ),
                        mapping_id=mapping.id,
                        verdict="RETRY_EXHAUSTED",
                        confidence=None,
                        outcome="retry_exhausted",
                        doc_paths=list(mapping.doc_targets),
                        retry_count=max(0, min(RETRY_MAX_ATTEMPTS, int(getattr(exc, "attempts", 0)))),
                        latency_ms=0,
                        tier_classification_outcome=None,
                        github_issue_number=None,
                        schema_version=1,
                    ),
                    ledger_path=ledger_path,
                )
            except OSError as ledger_exc:
                # Ledger append failure is not fatal — the side effect
                # (GitHub issue) still needs to happen for operator
                # visibility. Log and continue.
                _logger.warning(
                    "Ledger append failed during RETRY_EXHAUSTED fallback (event %s): %s",
                    event_id,
                    ledger_exc,
                )

            # File the pre-#362 fallback issue with the diagnostic block.
            extra_body = ""
            try:
                extra_body = exc.to_diagnostic_block()
            except (AttributeError, TypeError):
                extra_body = f"## Moment 0 diagnostic\n\n```\n{exc}\n```\n"

            ok, output = file_doc_audit_issue(
                event,
                mapping,
                self._repo,
                dry_run=False,
                extra_body=extra_body,
            )
            if not ok:
                raise RuntimeError(
                    f"file_doc_audit_issue failed during RETRY_EXHAUSTED "
                    f"fallback for mapping={mapping.id} "
                    f"line={line_number}: {output}"
                )

    def _drain(self, current_cursor: int) -> None:
        """Advance the on-disk cursor through committed/non-signal lines.

        Starting at ``current_cursor``, walks forward while the next
        line is either:

        - already recorded as committed in this tick
          (``self._committed_lines``), or
        - classified as non-signal by :meth:`pending`
          (i.e., NOT in ``self._signal_lines`` — blank line or
          malformed JSON).

        Stops at the first signal-bearing line whose commit has not
        yet landed, or once we pass ``_max_line_examined`` (the safe
        upper bound for what pending() actually inspected this tick).

        If the resulting new cursor is greater than ``current_cursor``,
        writes it atomically via :func:`write_cursor_atomic`. A no-op
        otherwise.
        """
        new_cursor = current_cursor
        # Upper bound: never advance past one beyond the last line
        # pending() examined. This guards against advancing into
        # territory we have not classified (and never advances past
        # EOF on a fresh adapter).
        upper_bound = self._max_line_examined + 1
        while new_cursor < upper_bound:
            if new_cursor in self._committed_lines:
                new_cursor += 1
                continue
            if new_cursor not in self._signal_lines:
                # Non-signal line (blank or malformed) — safe to drain
                # past since pending() emitted no signal here.
                new_cursor += 1
                continue
            # Signal-bearing line with no commit recorded yet — stop
            # so the uncommitted earlier event is preserved.
            break

        if new_cursor > current_cursor:
            write_cursor_atomic(self._cursor_path, new_cursor)


__all__ = ["DriftEventSignalSource"]
