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


# ---------------------------------------------------------------------------
# Rebaseline alert dispatch (C5 — rebaseline-lifecycle-v1.md)
# ---------------------------------------------------------------------------

# Off-happy-path event keys for rebaseline alerts.
# ``stale_ntfy`` is the WP03 dispatch-layer dedupe key for the stale token
# alert — distinct from the engine's ``stale`` classification marker which is
# pre-appended to ``alerts_emitted`` by _maybe_stale before dispatch runs.
REBASELINE_ALERT_EVENTS = ("rebaseline_failed", "unexpected_drift", "stale", "stale_ntfy")

# Priority for rebaseline alerts — high (same as failure notifications).
_REBASELINE_PRIORITY = "high"
_REBASELINE_TAGS = "warning,rotating_light"


def _render_rebaseline_title(event_key: str) -> str:
    return f"felix-deployer rebaseline: {event_key}"


def _render_rebaseline_body(
    event_key: str,
    token: dict,
    detail: str,
    head_sha: str,
    registry: dict | None = None,
) -> str:
    """Render the ntfy body for a rebaseline alert (C5).

    Includes surface_ids, drifted baselines (from *detail*), and the
    manual rebaseline_command from the registry for the operator.
    """
    surface_ids = token.get("surface_ids", [])
    surface_ids_str = ", ".join(surface_ids) if surface_ids else "(none)"
    head_prefix = head_sha[:8] if head_sha else "(unknown)"
    rebaseline_command = ""
    if registry:
        rebaseline_command = registry.get("rebaseline_command", "")
    lines = [
        f"Event: {event_key}",
        f"Surfaces: {surface_ids_str}",
        f"Head: {head_prefix}",
        f"Detail: {detail[:300] if detail else '(none)'}",
    ]
    if rebaseline_command:
        lines.append(f"\nManual rebaseline command:\n{rebaseline_command}")
    return "\n".join(lines)


def dispatch_rebaseline_alert(
    event_key: str,
    token: dict,
    detail: str,
    head_sha: str,
    *,
    registry: dict | None = None,
) -> LibResult:
    """Dispatch one ntfy alert for a rebaseline off-happy-path event (C5).

    Deduplicates via ``token["alerts_emitted"]``: fires at most once per
    ``event_key`` per token lifetime (FR-006, FR-009). If the event has
    already been emitted, returns a no-op ``LibResult(ok=True, ...)``.

    On success, mutates ``token["alerts_emitted"]`` in place so the caller
    (``_tick``) can persist the updated token via ``rebaseline.write_token``.

    Args:
        event_key: one of ``"rebaseline_failed"``, ``"unexpected_drift"``,
            ``"stale"``.
        token: the current pending-token dict (mutable — this function
            appends to ``alerts_emitted`` on success so the caller can persist).
        detail: short human-readable detail string for the body.
        head_sha: current HEAD SHA (included in body for triage).
        registry: injectable audited-surfaces registry (for
            ``rebaseline_command`` in body). Falls back to no command line.

    Returns a ``LibResult``. Dispatch errors are caught and returned as
    ``ok=False``; they are **never raised** to the caller.
    """
    # Dedupe: skip if already emitted for this token.
    alerts_emitted: list[str] = list(token.get("alerts_emitted", []))
    if event_key in alerts_emitted:
        return LibResult(
            ok=True,
            summary=f"rebaseline alert deduplicated: {event_key}",
            details={"event_key": event_key, "deduplicated": True},
        )

    topic = os.environ.get(NTFY_TOPIC_ENV, "").strip()
    if not topic:
        return LibResult(
            ok=False,
            summary=f"rebaseline alert: skipped ({NTFY_TOPIC_ENV} not configured)",
            details={"error_code": "NTFY_MISSING_TOPIC", "event_key": event_key},
        )

    title = _render_rebaseline_title(event_key)
    body = _render_rebaseline_body(
        event_key=event_key,
        token=token,
        detail=detail,
        head_sha=head_sha,
        registry=registry,
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
                "-H", f"Priority: {_REBASELINE_PRIORITY}",
                "-H", f"Tags: {_REBASELINE_TAGS}",
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
            summary=f"rebaseline alert: curl not found ({exc})",
            details={
                "error_code": "NTFY_CURL_MISSING",
                "event_key": event_key,
                "error": str(exc),
            },
        )
    except OSError as exc:
        return LibResult(
            ok=False,
            summary=f"rebaseline alert: failed to spawn curl ({exc})",
            details={
                "error_code": "NTFY_SPAWN_FAILED",
                "event_key": event_key,
                "error": str(exc),
            },
        )

    if result.returncode != 0:
        return LibResult(
            ok=False,
            summary=f"rebaseline alert: curl failed (rc={result.returncode})",
            details={
                "error_code": _classify_error_code(result.returncode),
                "event_key": event_key,
                "returncode": result.returncode,
                "stderr_excerpt": (result.stderr or "")[:200],
                "topic_redacted": topic_redacted,
            },
        )

    # Success: mark event as emitted on the mutable token dict.
    # The caller (_tick) holds the same reference and will persist it via
    # rebaseline.write_token. Mutating here is the single dedupe write.
    alerts_emitted.append(event_key)
    token["alerts_emitted"] = alerts_emitted

    return LibResult(
        ok=True,
        summary=f"rebaseline alert sent: {event_key}",
        details={
            "event_key": event_key,
            "title": title,
            "topic_redacted": topic_redacted,
        },
    )


# ---------------------------------------------------------------------------
# Generic health notifier (#667, WP03)
# ---------------------------------------------------------------------------
#
# The functions above are manifest-failure-shaped: they render a manifest title
# and read the fixed FELIX_DEPLOYER_NTFY_TOPIC. The git-advance health signal
# (scripts/deploy/lib/health.py) needs a *generic* sender: any actor supplies
# its own title/body and names the env var that holds its ntfy topic. This
# reuses the redaction (`_topic_redact` / `_redact_and_truncate`) and the curl
# POST internals so there is one wire path, but owns its own topic resolution.

# Health-alert priority/tags — same high-urgency shape as the failure path.
_HEALTH_PRIORITY = "high"
_HEALTH_TAGS = "warning,rotating_light"


def _resolve_health_topic(topic_env: str) -> str:
    """Resolve the ntfy topic for a health alert.

    Reads the env var named by *topic_env* (e.g. ``AGENT_PROMPT_SYNC_NTFY_TOPIC``);
    if unset/blank, falls back to the shared ``FELIX_DEPLOYER_NTFY_TOPIC``.
    Returns "" when neither is configured.
    """
    topic = os.environ.get(topic_env, "").strip()
    if topic:
        return topic
    return os.environ.get(NTFY_TOPIC_ENV, "").strip()


def dispatch_health_notification(
    actor: str,
    title: str,
    body: str,
    *,
    topic_env: str,
) -> bool:
    """Send a generic ntfy health alert for *actor* (best-effort).

    Resolves the topic from the env var named by *topic_env*, falling back to
    ``FELIX_DEPLOYER_NTFY_TOPIC`` if that is unset. The *body* is run through the
    shared redact-then-truncate path before POST.

    Returns ``True`` iff the alert was **actually delivered** — i.e. a topic
    resolved AND the curl POST succeeded (rc == 0). Returns ``False`` on every
    non-delivery mode (no topic configured, curl missing, spawn failure,
    network/HTTP error). This delivery bool is the contract
    :func:`scripts.deploy.lib.health.record` relies on to decide whether to stamp
    ``last_alert_ts``: a False return must NOT burn the alert. This function is
    best-effort and NEVER raises into the caller's tick.
    """
    topic = _resolve_health_topic(topic_env)
    if not topic:
        # No topic configured → nothing delivered.
        return False

    safe_body = _redact_and_truncate(body or "")
    if not safe_body:
        safe_body = "(no detail)"

    try:
        result = subprocess.run(  # noqa: S603 - argv list, no shell
            [
                "curl",
                "--silent",
                "--show-error",
                "--fail",
                "--max-time", str(CURL_MAX_TIME_SECONDS),
                "-H", f"Title: {title}",
                "-H", f"Priority: {_HEALTH_PRIORITY}",
                "-H", f"Tags: {_HEALTH_TAGS}",
                "-X", "POST",
                "--data-binary", "@-",
                f"{NTFY_BASE_URL}/{topic}",
            ],
            input=safe_body,
            capture_output=True,
            text=True,
            check=False,
        )
    except (FileNotFoundError, OSError):
        # curl missing / spawn failure → not delivered. Best-effort: swallow.
        return False

    # Delivered iff the POST succeeded.
    return result.returncode == 0


__all__ = [
    "NOTIFICATION_FORMAT_VERSION",
    "NTFY_TOPIC_ENV",
    "ERROR_SUMMARY_MAX",
    "DM_PHASES",
    "REBASELINE_ALERT_EVENTS",
    "dispatch_failure_notification",
    "dispatch_rebaseline_alert",
    "dispatch_health_notification",
]
