"""Generic, command-based liveness probe for credentials.

Implements probe_oauth_liveness() + LivenessResult. Introduced for GitHub issue
#572 (gog-specific), made generic in #845: a credential's liveness_probe block
declares an argv `command` + `dead_exit_codes`, and this runner classifies the
outcome by exit code — 0 = alive, code in `dead_exit_codes` = dead, anything
else (or a failure to execute) = probe-error. The runner is credential-agnostic:
the specificity (what to run, which codes mean dead) lives entirely in the
manifest block, so Google/Vikunja/GitHub/etc. probes need no code change here.

Every terminal path emits exactly one of the marker tokens
`credential_alive` / `credential_dead` / `credential_probe_error` at INFO, which
the credential-liveness-probe canary greps for over its 7h window.
"""
from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Optional

from .manifest import LivenessProbeConfig  # noqa: F401 — re-exported for callers


# ---------- Classification type ----------

LivenessClassification = Literal[
    "dead",
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


# ---------- Logger ----------

_logger = logging.getLogger("credential_health_check.liveness")


# ---------- Internal helper ----------

def _probe_error(
    credential_name: str, now: datetime, duration_ms: int, reason: str
) -> LivenessResult:
    """Log a credential_probe_error marker and build the result."""
    _logger.info(
        "credential_probe_error credential_name=%s probed_at=%s "
        "duration_ms=%d error_detail=%s",
        credential_name, now.isoformat(), duration_ms, reason,
    )
    return LivenessResult(
        credential_name=credential_name,
        classification="probe-error",
        reason=reason,
        recovery_command=None,
        probed_at=now,
    )


# ---------- Probe function ----------

def probe_oauth_liveness(
    credential,  # Credential (forward-ref; avoids circular import)
    *,
    now_utc: Optional[datetime] = None,
) -> Optional[LivenessResult]:
    """Probe a single credential for liveness by running its configured command.

    Returns None when alive (exit 0); returns a LivenessResult on dead (exit in
    `dead_exit_codes`) or probe-error (any other non-zero exit, timeout, or a
    failure to execute the command). Exactly one marker token is logged per call.
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
            list(cfg.command),
            capture_output=True,
            text=True,
            timeout=cfg.timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        duration_ms = int((time.monotonic() - t0) * 1000)
        return _probe_error(
            credential.name, now, duration_ms,
            f"liveness probe exceeded {cfg.timeout_seconds}s timeout",
        )
    except OSError as exc:
        # FileNotFoundError / PermissionError / NotADirectoryError / other OS
        # failures to launch the probe argv — never a credential-dead signal.
        duration_ms = int((time.monotonic() - t0) * 1000)
        return _probe_error(
            credential.name, now, duration_ms,
            f"probe command could not be executed: {type(exc).__name__}: {exc}",
        )
    except Exception as exc:  # noqa: BLE001 — defensive: any unexpected failure is a probe-error, not a death
        duration_ms = int((time.monotonic() - t0) * 1000)
        return _probe_error(
            credential.name, now, duration_ms,
            f"probe raised unexpectedly: {type(exc).__name__}: {exc}",
        )

    duration_ms = int((time.monotonic() - t0) * 1000)

    # Alive: exit 0.
    if result.returncode == 0:
        _logger.info(
            "credential_alive credential_name=%s probed_at=%s duration_ms=%d",
            credential.name,
            now.isoformat(),
            duration_ms,
        )
        return None

    # Dead: exit code the probe declares as "credential needs re-auth".
    if result.returncode in cfg.dead_exit_codes:
        reason = (
            f"probe reported credential dead (exit {result.returncode}: "
            f"{(result.stderr or '').strip()[:200]}). "
            f"Run the recovery command to re-mint."
        )
        _logger.info(
            "credential_dead credential_name=%s classification=%s "
            "probed_at=%s duration_ms=%d reason=%s recovery_command=%s",
            credential.name,
            "dead",
            now.isoformat(),
            duration_ms,
            reason,
            cfg.recovery_command,
        )
        return LivenessResult(
            credential_name=credential.name,
            classification="dead",
            reason=reason,
            recovery_command=cfg.recovery_command,
            probed_at=now,
        )

    # Any other non-zero exit is an environment/probe error, NOT a credential
    # death (e.g. a broken probe interpreter, missing deps, transient failure).
    return _probe_error(
        credential.name, now, duration_ms,
        f"probe exited {result.returncode}: {(result.stderr or '').strip()[:200]}",
    )
