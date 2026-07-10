"""felix-alert bus — the single shared library for sending an ntfy alert.

Public API::

    from scripts.common.alert_bus import emit, Alert, Severity, AlertResult

    result = emit(Alert(
        source="felix-deployer/apply",
        severity=Severity.ERROR,
        title="felix-deployer failed: felix-calendar-helper",
        description="Dry-run failed before apply; the deploy script was not executable.",
        action="chmod +x the deploy script and re-queue the manifest.",
        details={"phase": "dry_run", "exit_code": "126"},
    ))
    # result.ok -> bool ; never raises

Guarantees:

- :func:`emit` is the ONLY entry point callers use and **never raises** — all
  failures surface as ``AlertResult(ok=False, reason=…)`` (D7/NFR-001).
- Only :func:`emit` (via ``delivery``) performs ntfy I/O; no other module or
  caller talks to ntfy (FR-005).
- Constructing an :class:`Alert` with a missing required field raises
  ``ValueError`` at the call site (a programming error), not at delivery time.
"""

from __future__ import annotations

from .delivery import deliver
from .ledger import record_alert
from .model import Alert, AlertResult, Severity


def emit(alert: Alert) -> AlertResult:
    """Render *alert*, deliver it to ntfy, and record it to the local ledger; never raises.

    This is the sole public entry point. Rendering happens inside
    :func:`~scripts.common.alert_bus.delivery.deliver`, which catches all
    delivery failures and returns a structured :class:`AlertResult`. Any other
    unexpected error is also swallowed into a result so callers on cron/audit
    paths are never crashed by the bus.

    After delivery, the alert + its delivery outcome are appended to the durable
    local ledger (#706) as a best-effort side effect: this records the fault even
    when ntfy delivery failed, and a ledger problem never changes the returned
    :class:`AlertResult` or raises.
    """
    try:
        result = deliver(alert)
    except Exception as exc:  # noqa: BLE001 — fail-safe: the bus must never raise
        result = AlertResult(
            ok=False,
            reason=f"BUS_ERROR:{exc.__class__.__name__}",
            topic_configured=True,
        )
    # Best-effort durable record. record_alert() never raises; the extra guard is
    # belt-and-suspenders so the ledger can never affect delivery semantics.
    try:
        record_alert(alert, result)
    except Exception:  # noqa: BLE001 — fail-safe
        pass
    return result


__all__ = ["emit", "Alert", "Severity", "AlertResult"]
