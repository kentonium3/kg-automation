"""Signal extractor: OpenClaw unhandled-error events (FR-006 #3).

Matches OpenClaw log lines whose **raw JSON serialization** contains
the literal substring:

    "logLevelName":"ERROR"

The substring lives in the nested ``_meta`` block, not in the
human-readable message body — so this extractor matches against the
raw line text via ``match_target="raw"`` rather than the assembled
message body.

Per research.md §OD-2, the 2026-06-01 calibration showed 6 ERROR-level
events in the 18-hour window; thresholds at ``cycle=3 / rolling=5``
fire on real bursts without tripping on the routine 1/hour baseline.

Excerpts use ``signal_def.excerpt_lines = 8`` (configured in the seed
``config.toml``) so the issue body can carry enough context for an
operator to triage the error class without an extra log dive.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional, Union

from scripts.openclaw.observation.signals._engine import run_extraction
from scripts.openclaw.observation.signals.config_loader import (
    SignalDefinition,
)
from scripts.openclaw.observation.signals.openclaw_log import LogCursor
from scripts.openclaw.observation.signals.types import SignalExtraction

__all__ = ["REDACT_KEYS", "extract"]


# Errors can dump arbitrary context. Redact aggressively at length on
# any field whose name suggests credential material. ``stack`` and
# ``error`` are left readable — operators need them to triage the
# unhandled-error class.
REDACT_KEYS = frozenset(
    {"creds", "credentials", "token", "secret", "password", "apiKey",
     "authorization", "cookie", "sessionToken"}
)


def extract(
    state_dir: Union[Path, str],
    signal_def: SignalDefinition,
    now_utc: datetime,
    prior_cursor: Optional[LogCursor] = None,
    prior_rolling_count: int = 0,
) -> SignalExtraction:
    """Run one extraction pass for the unhandled_error signal."""
    _ = state_dir
    return run_extraction(
        signal_def=signal_def,
        now_utc=now_utc,
        prior_cursor=prior_cursor,
        prior_rolling_count=prior_rolling_count,
        match_target="raw",
        redact_keys=REDACT_KEYS,
    )
