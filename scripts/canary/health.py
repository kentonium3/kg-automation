"""Canary health computation — gate-before-probe + ProbeResult → HealthResult.

:func:`evaluate` is the single evaluation entry point (contracts §3). It is
**pure with respect to injected effects** — network / subprocess / filesystem
are passed through to the probe as callables — and contains **no LLM call**
(INV-E).

Gate-before-probe (F6 / INV-A)
------------------------------
The very first thing :func:`evaluate` does is check ``target.alert_eligible``.
If the component's declared status is not alert-eligible (ADR-0006 §4), it
returns a ``suppressed`` :class:`HealthResult` **without calling any probe** —
the injected effects are never touched. This is the single suppression rule:
gate first, probe only for alert-eligible components. Consequently
``should_emit`` can only ever be ``True`` for an alert-eligible component.

Outcome mapping (ADR-0006, research R4/R6)
------------------------------------------
For an alert-eligible component, the :class:`~scripts.canary.probes.ProbeResult`
maps to a health outcome + severity:

======================  ==========  ==========  =============================
ProbeResult             outcome     severity    should_emit (here)
======================  ==========  ==========  =============================
not evaluable           unknown     WARN        False  (WP04 persistence flips)
ok & not stale          healthy     None        False
ok & stale              stale       ERROR       True
not ok                  failed      ERROR       True
degraded (self-report)  degraded    WARN        True
======================  ==========  ==========  =============================

``degraded`` is not reachable from a probe this mission (no probe self-reports
partial health); its enum value + WARN mapping are retained for WP04.

The ``unknown`` / ``should_emit=False`` split is deliberate: an ``unknown``
should alert only once it has *persisted* past the dedup window (F5). That
persistence decision belongs to WP04's dedup layer, which flips ``should_emit``
to ``True`` when appropriate. Here we emit the honest current-tick verdict.

Fail-safe (INV-D)
-----------------
The probe call is wrapped: a probe that raises is turned into an ``unknown``
outcome with evidence naming the error. :func:`evaluate` **never raises** for a
component-level fault — WP04 collects these into its ``errors[]`` and keeps
ticking.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from scripts.canary.probes import ProbeResult, run_probe
from scripts.canary.registry import CanaryTarget
from scripts.common.alert_bus import Severity


@dataclass(frozen=True)
class HealthResult:
    """Computed health verdict for one component (data-model.md).

    ``should_emit`` is the *current-tick* emission decision. For ``unknown`` it
    is left ``False`` here; WP04's dedup/persistence layer flips it once the
    ``unknown`` persists past the window. ``evaluated_at`` is the ISO-8601 UTC
    render of the injected ``now`` (no ``datetime.now()`` in this module).
    """

    component_id: str
    outcome: str
    alert_eligible: bool
    should_emit: bool
    severity: Severity | None
    evidence: str
    evaluated_at: str


# Injected-effect callable signatures (documentation only; not enforced).
HttpGet = Callable[..., int]
RunCmd = Callable[..., tuple[int, str, str]]
ReadState = Callable[[str], dict[str, Any]]


def _map_outcome(probe: ProbeResult) -> tuple[str, Severity | None, bool]:
    """Map a :class:`ProbeResult` to ``(outcome, severity, should_emit)``.

    Emission here is the deterministic current-tick decision:
    ``stale`` / ``failed`` / ``degraded`` → emit; ``healthy`` → no; ``unknown``
    → no (WP04 persistence flips it once it survives the dedup window).
    """
    if not probe.evaluable:
        return "unknown", Severity.WARN, False
    if probe.ok and not probe.stale:
        return "healthy", None, False
    if probe.ok and probe.stale:
        return "stale", Severity.ERROR, True
    # evaluable and not ok
    return "failed", Severity.ERROR, True


def evaluate(
    target: CanaryTarget,
    now: datetime,
    *,
    http_get: HttpGet,
    run_cmd: RunCmd,
    read_state: ReadState,
) -> HealthResult:
    """Evaluate one :class:`CanaryTarget` into a :class:`HealthResult`.

    Gate-before-probe (F6 / INV-A): when ``target.alert_eligible`` is false the
    component is **not probed** — the injected effects are never called — and a
    ``suppressed`` result is returned. Otherwise the target is probed and the
    :class:`ProbeResult` mapped per ADR-0006 (see module docstring). Never
    raises for a component-level fault (INV-D): a raising probe becomes an
    ``unknown`` outcome.
    """
    evaluated_at = now.isoformat()

    # --- Gate first: suppressed-status components are never probed. --------- #
    if not target.alert_eligible:
        return HealthResult(
            component_id=target.component_id,
            outcome="suppressed",
            alert_eligible=False,
            should_emit=False,
            severity=None,
            evidence=f"status {target.status!r} not alert-eligible; not probed",
            evaluated_at=evaluated_at,
        )

    # --- Probe (fail-safe: a raising probe → unknown, never escapes). ------- #
    try:
        probe = run_probe(
            target.health_check or {},
            now,
            http_get=http_get,
            run_cmd=run_cmd,
            read_state=read_state,
        )
    except Exception as exc:  # noqa: BLE001 — belt-and-suspenders (INV-D)
        probe = ProbeResult(
            ok=False, stale=False, evaluable=False,
            evidence=f"{type(exc).__name__}: {exc}",
        )

    outcome, severity, should_emit = _map_outcome(probe)
    return HealthResult(
        component_id=target.component_id,
        outcome=outcome,
        alert_eligible=True,
        should_emit=should_emit,
        severity=severity,
        evidence=probe.evidence,
        evaluated_at=evaluated_at,
    )
