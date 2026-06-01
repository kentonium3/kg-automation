"""Signal extractor: WhatsApp credential-restore events (FR-006 #1).

Matches OpenClaw log lines whose human-readable message body contains:

    "restored corrupted WhatsApp creds.json from backup"

This is the load-bearing signal for mission #490 — the WhatsApp
creds.json corruption pattern that the original heartbeat-driven
Sonnet path mis-counted. Threshold seeds live in ``config.toml``;
calibration sits in ``research.md`` §OD-2.

The shared :func:`scripts.openclaw.observation.signals._engine.run_extraction`
does the actual cycle walk; this module owns only:

- The redaction-key set for excerpts (spec C-005).
- The match-target choice (``"body"`` — the substring matches the
  message text proper, not the surrounding JSON metadata).
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


# Credential field names whose values get scrubbed before going into
# an excerpt body. ``credsPath`` is a filesystem path (not a secret)
# but we redact it on length to keep operator excerpts free of any
# downstream PII that ever lands in this slot.
REDACT_KEYS = frozenset(
    {"creds", "credentials", "credsPath", "token", "secret",
     "password", "apiKey"}
)


def extract(
    state_dir: Union[Path, str],
    signal_def: SignalDefinition,
    now_utc: datetime,
    prior_cursor: Optional[LogCursor] = None,
    prior_rolling_count: int = 0,
) -> SignalExtraction:
    """Run one extraction pass for the creds_restore signal.

    See module docstring + the
    :func:`scripts.openclaw.observation.signals._engine.run_extraction`
    docstring for the per-cycle contract.
    """
    _ = state_dir  # API anchor — WP-02 will use this for state IO.
    return run_extraction(
        signal_def=signal_def,
        now_utc=now_utc,
        prior_cursor=prior_cursor,
        prior_rolling_count=prior_rolling_count,
        match_target="body",
        redact_keys=REDACT_KEYS,
    )
