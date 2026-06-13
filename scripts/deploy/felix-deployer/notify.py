"""felix-deployer failure-notification surface (ntfy.sh substrate).

Renders the failure notification per
``kitty-specs/felix-deployer-ntfy-failure-notifications-01KTZ76F/contracts/ntfy-notification-v1.md``
and POSTs it to ``https://ntfy.sh/<topic>`` via a ``curl`` subprocess.

The notification is best-effort: dispatch failure is recorded but never
crashes the tick. The applier's job is to record the failure on disk
(in ``deploys/failed/``) so the operator has the durable artefact; the
push is escalation, not the source of truth.

Invariants enforced here:

* ``NOTIFICATION_FORMAT_VERSION`` is always ``"v1"``.
* ``error_summary`` is run through
  :func:`scripts.deploy.lib.verify.redact_secrets` BEFORE truncation
  to ≤500 chars. Order is fixed; tests pin it.
* The 4-value ``phase`` enum (``tier_guard``, ``verification_pre``,
  ``entrypoint``, ``verification_post``) is what the contract documents.
  Callers may pass either that or one of lib.apply's 7 phases; the
  mapping in :mod:`_tick` (``PHASE_TO_NOTIFY_PHASE``) collapses them.
* Importing this module has zero outbound side effects (no HTTP request,
  no DNS lookup, no subprocess spawn at import time).
"""

from __future__ import annotations

import datetime as _dt
import os
import subprocess
from typing import Any, Mapping

from scripts.deploy.lib import LibResult
from scripts.deploy.lib import verify as _verify

NTFY_BASE_URL = "https://ntfy.sh"
NTFY_TOPIC_ENV = "FELIX_DEPLOYER_NTFY_TOPIC"
NOTIFICATION_FORMAT_VERSION = "v1"

ERROR_SUMMARY_MAX = 500
CURL_MAX_TIME_SECONDS = 10

PRIORITY_HEADER = "high"
TAGS_HEADER = "warning,rotating_light"

# Phase strings accepted in the v1 notification body. The applier may pass
# any of lib.apply's 7 phase constants; _tick.PHASE_TO_NOTIFY_PHASE collapses
# them before reaching this function. If a caller bypasses that mapping and
# passes an unknown phase string, we pass it through verbatim so the
# operator at least sees the raw signal.
DM_PHASES = ("tier_guard", "verification_pre", "entrypoint", "verification_post")

# Closed enum of error_code values returned in LibResult.details on failure.
_ERROR_CODES = frozenset(
    {
        "NTFY_MISSING_TOPIC",
        "NTFY_CURL_MISSING",
        "NTFY_SPAWN_FAILED",
        "NTFY_TIMEOUT",
        "NTFY_NETWORK_UNREACHABLE",
        "NTFY_HTTP_ERROR",
        "NTFY_UNKNOWN",
    }
)


def _utc_now_iso() -> str:
    return _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _render_title(manifest_name: str) -> str:
    return f"felix-deployer failed: {manifest_name}"


def _redact_and_truncate(error_summary: str) -> str:
    """Redact secrets BEFORE truncating to ERROR_SUMMARY_MAX.

    Order is invariant; truncate-first would slice a secret pattern across
    the boundary and leak head bytes. Tests pin the boundary case.
    """
    redacted = _verify.redact_secrets(error_summary or "")
    if len(redacted) > ERROR_SUMMARY_MAX:
        redacted = redacted[:ERROR_SUMMARY_MAX]
    return redacted


def _render_body(
    manifest: Mapping[str, Any],
    phase: str,
    error_summary: str,
    head_sha: str,
    failed_at: str | None = None,
) -> str:
    redacted = _redact_and_truncate(error_summary or "")
    if not redacted:
        redacted = "(no error summary)"
    head_prefix = head_sha[:8] if head_sha else "(unknown)"
    failed_at_iso = failed_at or _utc_now_iso()
    return (
        f"Phase: {phase}\n"
        f"Tier: {manifest.get('tier')}\n"
        f"Head: {head_prefix}\n"
        f"Failed at: {failed_at_iso}\n"
        f"\n"
        f"Error:\n"
        f"{redacted}"
    )


def _classify_error_code(returncode: int) -> str:
    """Map curl exit code to a closed-enum LibResult error_code.

    Stable libcurl 7.x/8.x exit codes:
        6  = couldn't resolve host (DNS)
        7  = couldn't connect to host
        22 = HTTP error caught by --fail
        28 = operation timed out
    Anything else falls to NTFY_UNKNOWN.
    """
    if returncode in (6, 7):
        return "NTFY_NETWORK_UNREACHABLE"
    if returncode == 22:
        return "NTFY_HTTP_ERROR"
    if returncode == 28:
        return "NTFY_TIMEOUT"
    return "NTFY_UNKNOWN"


def _topic_redact(topic: str) -> str:
    """Produce a non-leaky log-audit form of the topic.

    The topic is private (operator's subscribed ntfy channel) but not a
    cryptographic secret; we still avoid logging it verbatim so log
    aggregators don't propagate it. Short topics are short-redacted.
    """
    if len(topic) <= 12:
        return "***"
    return f"{topic[:8]}***{topic[-4:]}"


def dispatch_failure_notification(
    manifest: Mapping[str, Any],
    phase: str,
    error_summary: str,
    head_sha: str,
    failed_at: str | None = None,
) -> LibResult:
    """Render and POST a failure notification to ntfy.sh.

    Returns ``LibResult(ok=True, ...)`` on successful POST.
    Returns ``LibResult(ok=False, details={"error_code": <code>, ...})``
    on any failure mode. NEVER raises for routine failures.

    See ``contracts/ntfy-notification-v1.md`` for the wire-shape contract.
    """
    topic = os.environ.get(NTFY_TOPIC_ENV, "").strip()
    if not topic:
        return LibResult(
            ok=False,
            summary=f"ntfy: skipped ({NTFY_TOPIC_ENV} not configured)",
            details={"error_code": "NTFY_MISSING_TOPIC"},
        )

    manifest_name = manifest.get("name", "<unknown>")
    title = _render_title(manifest_name)
    body = _render_body(
        manifest=manifest,
        phase=phase,
        error_summary=error_summary,
        head_sha=head_sha,
        failed_at=failed_at,
    )
    topic_redacted = _topic_redact(topic)

    try:
        result = subprocess.run(  # noqa: S603 - argv list, no shell
            [
                "curl",
                "--silent",
                "--show-error",
                "--fail",
                "--max-time", str(CURL_MAX_TIME_SECONDS),
                "-H", f"Title: {title}",
                "-H", f"Priority: {PRIORITY_HEADER}",
                "-H", f"Tags: {TAGS_HEADER}",
                "-X", "POST",
                "--data-binary", "@-",
                f"{NTFY_BASE_URL}/{topic}",
            ],
            input=body,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        return LibResult(
            ok=False,
            summary=f"ntfy: curl not found on PATH ({exc})",
            details={
                "error_code": "NTFY_CURL_MISSING",
                "error": str(exc),
                "title": title,
                "topic_redacted": topic_redacted,
            },
        )
    except OSError as exc:
        return LibResult(
            ok=False,
            summary=f"ntfy: failed to spawn curl ({exc})",
            details={
                "error_code": "NTFY_SPAWN_FAILED",
                "error": str(exc),
                "title": title,
                "topic_redacted": topic_redacted,
            },
        )

    if result.returncode == 0:
        return LibResult(
            ok=True,
            summary="ntfy notification sent",
            details={
                "title": title,
                "topic_redacted": topic_redacted,
                "format_version": NOTIFICATION_FORMAT_VERSION,
            },
        )

    return LibResult(
        ok=False,
        summary=f"ntfy: curl failed (rc={result.returncode})",
        details={
            "error_code": _classify_error_code(result.returncode),
            "returncode": result.returncode,
            "stderr_excerpt": (result.stderr or "")[:200],
            "title": title,
            "topic_redacted": topic_redacted,
        },
    )


__all__ = [
    "NOTIFICATION_FORMAT_VERSION",
    "NTFY_TOPIC_ENV",
    "ERROR_SUMMARY_MAX",
    "DM_PHASES",
    "dispatch_failure_notification",
]
