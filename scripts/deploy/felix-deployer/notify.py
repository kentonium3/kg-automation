"""felix-deployer failure-notification surface (felix-alert bus substrate).

Renders and delivers the failure/rebaseline/health alerts by building an
:class:`~scripts.common.alert_bus.Alert` and calling
:func:`~scripts.common.alert_bus.emit` — the single shared bus (WP01). This
module owns **no** ntfy/curl code of its own any more (SC-006); the bus is the
only path to ntfy.

The notification is best-effort: dispatch failure is recorded but never
crashes the tick. The applier's job is to record the failure on disk
(in ``deploys/failed/``) so the operator has the durable artefact; the
push is escalation, not the source of truth. ``emit()`` itself never raises.

Migration notes (WP02 / #701):

* The three dispatch functions keep their existing signatures and return
  contracts (``LibResult`` for the failure/rebaseline paths, ``bool`` for the
  health path) so ``_tick.py`` and ``deploy_agent_prompts.py`` are unchanged.
  Only the delivery backend moved from curl → ``emit()``.
* The bus resolves the single canonical topic from ``FELIX_ALERT_NTFY_TOPIC``.
  The old per-actor ``FELIX_DEPLOYER_NTFY_TOPIC`` / ``topic_env`` inputs are
  now **vestigial**: ``NTFY_TOPIC_ENV`` is retained only as a name constant for
  callers/tests, and ``dispatch_health_notification``'s ``topic_env`` keyword is
  accepted-but-ignored (see its docstring). Missing-topic is surfaced by the
  bus via ``AlertResult(ok=False, reason="NTFY_MISSING_TOPIC")``.
* Secret redaction + truncation now happen inside the bus renderer
  (``scripts.common.alert_bus.render``), which reuses the same
  ``scripts.deploy.lib.verify.redact_secrets`` this module used before — the
  redact-then-truncate invariant is preserved end-to-end.
* Importing this module has zero outbound side effects (no HTTP request, no DNS
  lookup, no subprocess spawn at import time).
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Mapping

from scripts.common.alert_bus import Alert, Severity, emit
from scripts.deploy.lib import LibResult

# Retained constants (public surface + tests). ``FELIX_DEPLOYER_NTFY_TOPIC`` is
# no longer read for delivery — the bus resolves ``FELIX_ALERT_NTFY_TOPIC`` — but
# the name is kept so callers/tests referencing it keep resolving.
NTFY_TOPIC_ENV = "FELIX_DEPLOYER_NTFY_TOPIC"
NOTIFICATION_FORMAT_VERSION = "v1"

# Kept for byte-comparable body length: the bus renderer truncates detail
# values at DETAIL_VALUE_MAX (500), matching this old ceiling.
ERROR_SUMMARY_MAX = 500

# Phase strings accepted in the v1 notification body. The applier may pass
# any of lib.apply's 7 phase constants; _tick.PHASE_TO_NOTIFY_PHASE collapses
# them before reaching this function. Retained for callers referencing it.
DM_PHASES = ("tier_guard", "verification_pre", "entrypoint", "verification_post")


def _utc_now_iso() -> str:
    return _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stringify_details(details: Mapping[str, Any]) -> dict[str, str]:
    """Coerce an arbitrary details mapping to the bus's ``dict[str, str]``.

    Drops keys whose value is ``None`` (absent signal) so the rendered
    ``Details:`` block never shows ``key=None`` placeholders (NFR-003).
    """
    out: dict[str, str] = {}
    for key, value in details.items():
        if value is None:
            continue
        out[str(key)] = str(value)
    return out


def dispatch_failure_notification(
    manifest: Mapping[str, Any],
    phase: str,
    error_summary: str,
    head_sha: str,
    failed_at: str | None = None,
    *,
    details: Mapping[str, Any] | None = None,
) -> LibResult:
    """Render and deliver a felix-deployer failure alert via the bus.

    Returns ``LibResult(ok=True, ...)`` when the bus delivered the alert, and
    ``LibResult(ok=False, details={"error_code": <reason>, ...})`` on any
    non-delivery. NEVER raises for routine failures — the bus is fail-safe.

    ``details`` (WP02 / #699 / SC-002): the apply result's captured error
    context — ``stderr_excerpt``, ``stdout_excerpt``, ``argv`` / ``failed_command``,
    ``returncode``, ``manifest_path`` — is threaded straight into the Alert
    ``details`` so the rendered body names the failing *cause* (e.g. a
    non-executable deploy script), not just "dry-run failed". The core
    ``phase`` / ``tier`` / ``head`` fields are always included.
    """
    manifest_name = str(manifest.get("name", "<unknown>"))
    head_prefix = head_sha[:8] if head_sha else "(unknown)"

    alert_details: dict[str, str] = {
        "phase": phase,
        "tier": str(manifest.get("tier")),
        "head": head_prefix,
        "failed_at": failed_at or _utc_now_iso(),
    }
    # Thread the real captured error context on top of the core fields (#699).
    if details:
        alert_details.update(_stringify_details(details))

    description = (error_summary or "").strip() or "(no error summary)"

    result = emit(
        Alert(
            source="felix-deployer/apply",
            severity=Severity.ERROR,
            title=f"felix-deployer failed: {manifest_name}",
            description=description,
            action=(
                "Inspect the failure record in deploys/failed/ and the stderr "
                "below; fix the cause and re-queue the manifest."
            ),
            details=alert_details,
        )
    )

    if result.ok:
        return LibResult(
            ok=True,
            summary="alert delivered",
            details={
                "title": f"felix-deployer failed: {manifest_name}",
                "format_version": NOTIFICATION_FORMAT_VERSION,
            },
        )

    return LibResult(
        ok=False,
        summary=f"alert not delivered ({result.reason})",
        details={
            "error_code": result.reason or "NTFY_UNKNOWN",
            "topic_configured": result.topic_configured,
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


def _rebaseline_details(
    event_key: str,
    token: dict,
    detail: str,
    head_sha: str,
    registry: dict | None,
) -> dict[str, str]:
    """Build the Alert ``details`` for a rebaseline alert (C5)."""
    surface_ids = token.get("surface_ids", [])
    surface_ids_str = ", ".join(surface_ids) if surface_ids else "(none)"
    head_prefix = head_sha[:8] if head_sha else "(unknown)"
    out: dict[str, str] = {
        "event": event_key,
        "surfaces": surface_ids_str,
        "head": head_prefix,
        "detail": detail if detail else "(none)",
    }
    if registry:
        rebaseline_command = registry.get("rebaseline_command", "")
        if rebaseline_command:
            out["rebaseline_command"] = rebaseline_command
    return out


def dispatch_rebaseline_alert(
    event_key: str,
    token: dict,
    detail: str,
    head_sha: str,
    *,
    registry: dict | None = None,
) -> LibResult:
    """Dispatch one alert for a rebaseline off-happy-path event (C5) via the bus.

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

    Returns a ``LibResult``. Delivery errors surface as ``ok=False``; they are
    **never raised** to the caller (the bus is fail-safe).
    """
    # Dedupe: skip if already emitted for this token.
    alerts_emitted: list[str] = list(token.get("alerts_emitted", []))
    if event_key in alerts_emitted:
        return LibResult(
            ok=True,
            summary=f"rebaseline alert deduplicated: {event_key}",
            details={"event_key": event_key, "deduplicated": True},
        )

    result = emit(
        Alert(
            source="felix-deployer/rebaseline",
            # An off-happy-path rebaseline event needs prompt operator action:
            # it means the auto-rebaseline could not confirm expected drift, so
            # an audited surface may be unbaselined. ERROR mirrors the old
            # high-priority intent.
            severity=Severity.ERROR,
            title=f"felix-deployer rebaseline: {event_key}",
            description=(
                f"Rebaseline off-happy-path event '{event_key}'. A human must "
                "investigate before clearing the pending token."
            ),
            action=(registry or {}).get("rebaseline_command") or None,
            details=_rebaseline_details(event_key, token, detail, head_sha, registry),
        )
    )

    if not result.ok:
        return LibResult(
            ok=False,
            summary=f"rebaseline alert not delivered ({result.reason})",
            details={
                "error_code": result.reason or "NTFY_UNKNOWN",
                "event_key": event_key,
                "topic_configured": result.topic_configured,
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
            "title": f"felix-deployer rebaseline: {event_key}",
        },
    )


# ---------------------------------------------------------------------------
# Generic health notifier (#667, WP03)
# ---------------------------------------------------------------------------
#
# The git-advance health signal (scripts/deploy/lib/health.py) supplies its own
# title/body and expects a delivery bool back. Post-migration this routes to the
# bus like every other emitter; the ``topic_env`` keyword is vestigial (the bus
# resolves the single FELIX_ALERT_NTFY_TOPIC) and is accepted-but-ignored so the
# existing call sites in _tick.py and deploy_agent_prompts.py need no change.


def dispatch_health_notification(
    actor: str,
    title: str,
    body: str,
    *,
    topic_env: str | None = None,
) -> bool:
    """Send a generic health alert for *actor* via the bus (best-effort).

    Returns ``True`` iff the bus **actually delivered** the alert (``emit()``
    returned ``AlertResult.ok``). Returns ``False`` on every non-delivery mode
    (no topic configured, curl failure, etc.). This delivery bool is the
    contract :func:`scripts.deploy.lib.health.record` relies on to decide
    whether to stamp ``last_alert_ts``: a False return must NOT burn the alert.
    Never raises into the caller's tick — ``emit()`` is fail-safe.

    ``topic_env`` is **vestigial** (WP02): the bus resolves the single
    ``FELIX_ALERT_NTFY_TOPIC``, so the old per-actor topic-env fallback is gone.
    The parameter is accepted-but-ignored to keep the existing call sites
    (``_tick._health_notifier`` and ``deploy_agent_prompts._health_notifier``)
    signature-compatible.
    """
    result = emit(
        Alert(
            source=f"felix-deployer/health/{actor}",
            severity=Severity.ERROR,
            title=title,
            description=(body or "").strip() or "(no detail)",
            details={"actor": actor},
        )
    )
    return result.ok


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
