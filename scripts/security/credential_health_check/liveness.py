"""Liveness probe for oauth2 credentials via the gog binary.

Implements probe_oauth_liveness() + LivenessResult for GitHub issue #572.
See kitty-specs/credential-liveness-probe-01KTP9M8/contracts/liveness-probe-function.md
for the authoritative contract.
"""
from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal, Optional

from .manifest import LivenessProbeConfig  # noqa: F401 — re-exported for callers


# ---------- Classification type ----------

LivenessClassification = Literal[
    "dead-routine-7day",
    "dead-unexpected",
    "probe-error",
]


# ---------- Result dataclass ----------

@dataclass(frozen=True)
class LivenessResult:
    """Per-credential probe outcome. Returned only on failure or error.

    Alive credentials return None from probe_oauth_liveness().
    """

    credential_name: str
    classification: LivenessClassification
    reason: str
    recovery_command: Optional[str]
    probed_at: datetime  # MUST be timezone-aware UTC


# ---------- Module constants ----------

GOG_BINARY = "/home/linuxbrew/.linuxbrew/bin/gog"
PROBE_TIMEOUT_SECONDS = 15
CYCLE_WINDOW_HOURS = 24  # ±24h around mtime + 7d for routine classification
EXPECTED_TTL_DAYS = 7

# ---------- Logger ----------

_logger = logging.getLogger("credential_health_check.liveness")


# ---------- Probe function ----------

def probe_oauth_liveness(
    credential,  # Credential (forward-ref; avoids circular import)
    *,
    now_utc: Optional[datetime] = None,
) -> Optional[LivenessResult]:
    """Probe a single oauth2 credential for liveness.

    See kitty-specs/credential-liveness-probe-01KTP9M8/contracts/liveness-probe-function.md
    for the full contract.

    Returns None when alive; returns LivenessResult on any failure or error.
    """
    if credential.liveness_probe is None or not credential.liveness_probe.enabled:
        raise ValueError(
            f"probe_oauth_liveness called on credential {credential.name!r} "
            f"with no enabled liveness_probe block"
        )

    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")  # pragma: no branch

    cfg = credential.liveness_probe
    t0 = time.monotonic()

    try:
        result = subprocess.run(
            [
                GOG_BINARY,
                "--account", cfg.gog_account,
                "calendar", "list",
                "-j",
                "--max-results", "1",
            ],
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        duration_ms = int((time.monotonic() - t0) * 1000)
        reason = f"liveness probe exceeded {PROBE_TIMEOUT_SECONDS}s timeout"
        _logger.info(
            "credential_probe_error credential_name=%s probed_at=%s "
            "duration_ms=%d error_detail=%s",
            credential.name, now.isoformat(), duration_ms, reason,
        )
        return LivenessResult(
            credential_name=credential.name,
            classification="probe-error",
            reason=reason,
            recovery_command=None,
            probed_at=now,
        )
    except FileNotFoundError:
        duration_ms = int((time.monotonic() - t0) * 1000)
        reason = f"gog binary not found at {GOG_BINARY}"
        _logger.info(
            "credential_probe_error credential_name=%s probed_at=%s "
            "duration_ms=%d error_detail=%s",
            credential.name, now.isoformat(), duration_ms, reason,
        )
        return LivenessResult(
            credential_name=credential.name,
            classification="probe-error",
            reason=reason,
            recovery_command=None,
            probed_at=now,
        )

    duration_ms = int((time.monotonic() - t0) * 1000)

    # Happy path: probe succeeded.
    if result.returncode == 0:
        _logger.info(
            "credential_alive credential_name=%s probed_at=%s duration_ms=%d",
            credential.name,
            now.isoformat(),
            duration_ms,
        )
        return None

    # Dead path: token has expired (invalid_grant reported by gog).
    if "invalid_grant" in (result.stderr or ""):
        keyring_path = Path(cfg.keyring_file)
        try:
            mtime_ts = keyring_path.stat().st_mtime
        except FileNotFoundError:
            reason = f"keyring file not found at {cfg.keyring_file}"
            _logger.info(
                "credential_probe_error credential_name=%s probed_at=%s "
                "duration_ms=%d error_detail=%s",
                credential.name, now.isoformat(), duration_ms, reason,
            )
            return LivenessResult(
                credential_name=credential.name,
                classification="probe-error",
                reason=reason,
                recovery_command=None,
                probed_at=now,
            )

        mtime = datetime.fromtimestamp(mtime_ts, tz=timezone.utc)
        expected_expiration = mtime + timedelta(days=EXPECTED_TTL_DAYS)
        delta = abs(now - expected_expiration)

        if delta <= timedelta(hours=CYCLE_WINDOW_HOURS):
            classification: LivenessClassification = "dead-routine-7day"
            reason = (
                f"Token expired at the 7-day Testing-app cycle boundary "
                f"(mtime+7d={expected_expiration.isoformat()}, "
                f"delta={delta}). Run the recovery command to re-mint."
            )
        else:
            classification = "dead-unexpected"
            reason = (
                f"Token died at non-cycle time "
                f"(mtime+7d={expected_expiration.isoformat()}, "
                f"delta={delta}). "
                f"If you didn't recently change passwords or revoke access, "
                f"investigate at https://myaccount.google.com/permissions "
                f"before re-auth."
            )

        _logger.info(
            "credential_dead credential_name=%s classification=%s "
            "probed_at=%s duration_ms=%d reason=%s recovery_command=%s",
            credential.name,
            classification,
            now.isoformat(),
            duration_ms,
            reason,
            cfg.recovery_command,
        )
        return LivenessResult(
            credential_name=credential.name,
            classification=classification,
            reason=reason,
            recovery_command=cfg.recovery_command,
            probed_at=now,
        )

    # Fallthrough: non-zero exit, not invalid_grant — probe environment error.
    reason = (
        f"gog exited {result.returncode}: "
        f"{(result.stderr or '').strip()[:200]}"
    )
    _logger.info(
        "credential_probe_error credential_name=%s probed_at=%s "
        "duration_ms=%d error_detail=%s",
        credential.name, now.isoformat(), duration_ms, reason,
    )
    return LivenessResult(
        credential_name=credential.name,
        classification="probe-error",
        reason=reason,
        recovery_command=None,
        probed_at=now,
    )
