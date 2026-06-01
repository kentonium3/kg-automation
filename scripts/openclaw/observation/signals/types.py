"""Shared runtime types for the signal-extraction package.

The extractor modules return :class:`SignalExtraction` so the
orchestrator (WP-02) consumes a uniform record regardless of which
signal produced it. Keeping the type in one module avoids a circular
import between the extractors and the state/cursor helpers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

__all__ = ["LogCursor", "SignalExtraction"]


@dataclass(frozen=True)
class LogCursor:
    """Position marker for incremental log reading.

    Re-exported from ``openclaw_log`` so callers can type-hint against
    this module without importing the heavier helper. Mirrors the
    structure in ``data-model.md`` §E2 ``last_log_position``.
    """

    path: str
    inode: int
    byte_offset: int
    mtime: float


@dataclass(frozen=True)
class SignalExtraction:
    """Per-cycle extraction result for one signal.

    Returned by every extractor in this package. Threshold evaluation,
    issue filing, and state persistence happen in callers (WP-02).

    Fields:
        signal_id: From the :class:`SignalDefinition` that drove this
            extraction.
        count_cycle: Number of matching lines seen in the just-read
            window (i.e., since the last cursor).
        count_rolling: Cycle count plus prior rolling-window counts
            held in :class:`SignalState`. The extractor fills this in
            when the caller passes existing state; otherwise equals
            ``count_cycle``.
        excerpts: First N matching lines (raw JSON text) where N comes
            from ``SignalDefinition.excerpt_lines``. Credential
            material is redacted per spec C-005 — values longer than
            64 chars in known credential fields are replaced with
            ``<redacted len=N>``.
        last_event_at_utc: Timestamp of the most recent matching event
            in the cycle window. ``None`` if no match.
        new_cursor: Updated cursor for the source log after the
            extraction. Caller persists this in :class:`SignalState`.
    """

    signal_id: str
    count_cycle: int
    count_rolling: int
    excerpts: list[str] = field(default_factory=list)
    last_event_at_utc: Optional[datetime] = None
    new_cursor: Optional[LogCursor] = None
