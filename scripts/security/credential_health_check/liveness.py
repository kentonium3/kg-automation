"""Liveness probe for oauth2 credentials via the gog binary.

Implements probe_oauth_liveness() + LivenessResult for GitHub issue #572.
See kitty-specs/credential-liveness-probe-01KTP9M8/contracts/liveness-probe-function.md
for the authoritative contract.
"""
from __future__ import annotations

import glob as _glob
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
CYCLE_WINDOW_HOURS = 24  # ±24h around the 7d-cycle baseline for routine classification
EXPECTED_TTL_DAYS = 7


def _resolve_cycle_baseline(
    cfg: LivenessProbeConfig,
) -> tuple[Optional[datetime], str, Optional[str]]:
    """Resolve the 7d-cycle baseline for routine-vs-unexpected classification.

    Prefers ``cfg.reauth_marker_glob`` (a glob pattern whose matching files
    are touched ONLY at manual re-auth time — e.g.
    ``"~/.config/gogcli/oauth-manual-state-*.json"``) over
    ``cfg.keyring_file`` mtime. The keyring is rewritten on every successful
    6h probe tick, which advances its mtime and always blows past the
    ±24h window — so the keyring fallback misclassifies every routine 7d
    expiry as ``dead-unexpected`` (kentonium3/kg-automation#616).

    Returns (baseline_dt, source_label, error_if_no_baseline).
    ``baseline_dt`` is None iff ``error_if_no_baseline`` is set.
    """
    if cfg.reauth_marker_glob:
        matches = _glob.glob(str(Path(cfg.reauth_marker_glob).expanduser()))
        if matches:
            latest = max(Path(p).stat().st_mtime for p in matches)
            return (
                datetime.fromtimestamp(latest, tz=timezone.utc),
                "reauth",
                None,
            )
        # Configured but no match found — fall through to keyring fallback
        # rather than fail closed; the fallback's mis-classification
        # bias is still better than no liveness signal at all.
    if cfg.keyring_file:
        try:
            mtime_ts = Path(cfg.keyring_file).stat().st_mtime
        except FileNotFoundError:
            return (
                None,
                "keyring",
                f"keyring file not found at {cfg.keyring_file}",
            )
        return (
            datetime.fromtimestamp(mtime_ts, tz=timezone.utc),
            "keyring",
            None,
        )
    return (None, "—", "neither reauth_marker_glob nor keyring_file is set")

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
                "--max", "1",
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
        baseline, source_label, baseline_error = _resolve_cycle_baseline(cfg)
        if baseline is None:
            reason = baseline_error or "cycle baseline unavailable"
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

        expected_expiration = baseline + timedelta(days=EXPECTED_TTL_DAYS)
        delta = abs(now - expected_expiration)
        # Source-aware label in the message so operators can tell from the
        # alert which baseline drove the classification (#616).
        baseline_label = f"{source_label}+7d={expected_expiration.isoformat()}"

        if delta <= timedelta(hours=CYCLE_WINDOW_HOURS):
            classification: LivenessClassification = "dead-routine-7day"
            reason = (
                f"Token expired at the 7-day Testing-app cycle boundary "
                f"({baseline_label}, delta={delta}). "
                f"Run the recovery command to re-mint."
            )
        else:
            classification = "dead-unexpected"
            reason = (
                f"Token died at non-cycle time "
                f"({baseline_label}, delta={delta}). "
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
