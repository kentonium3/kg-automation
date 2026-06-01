"""Signal extractor: web-channel watchdog reconnect events (FR-006 #2).

Matches OpenClaw log lines whose human-readable message body contains:

    "web reconnect: connection closed"

These fire whenever the OpenClaw web-channel watchdog tears a
WebSocket back up. Spec §9 explicitly notes that the *root cause*
(reconnect-without-backoff loop in OpenClaw) is upstream and out of
scope; here we only count the events so an existing issue can dedup
the noise and Kent sees the storms once.

Shape mirrors :mod:`scripts.openclaw.observation.signals.creds_restore`.
The shared engine handles the cycle walk.
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


# Watchdog reconnect lines don't carry credentials, but the same
# defensive redaction set keeps the surface uniform across extractors.
REDACT_KEYS = frozenset(
    {"creds", "credentials", "token", "secret", "password", "apiKey"}
)


def extract(
    state_dir: Union[Path, str],
    signal_def: SignalDefinition,
    now_utc: datetime,
    prior_cursor: Optional[LogCursor] = None,
    prior_rolling_count: int = 0,
) -> SignalExtraction:
    """Run one extraction pass for the watchdog_reconnect signal."""
    _ = state_dir
    return run_extraction(
        signal_def=signal_def,
        now_utc=now_utc,
        prior_cursor=prior_cursor,
        prior_rolling_count=prior_rolling_count,
        match_target="body",
        redact_keys=REDACT_KEYS,
    )
