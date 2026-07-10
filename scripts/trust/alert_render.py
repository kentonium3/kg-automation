"""Finding -> Alert rendering + emission (WP04, felix-truthful-reporting-01KX6MN5).

Maps each :class:`~scripts.trust.cron_drift_detector.CronDriftFinding` (WP02)
and :class:`~scripts.trust.assertion_verifier.AssertionFinding` (WP03), plus
the runner's ``drift_resolved`` event (:mod:`scripts.trust.state`), into a
``#701`` :class:`~scripts.common.alert_bus.model.Alert` and emits it via the
**one shared bus** (``scripts.common.alert_bus.emit``) — no parallel channel
(C-002).

Severity + title mapping is the data-model.md "Finding -> Alert" table,
reproduced exactly here:

| Finding               | Severity | Title                                          |
|-----------------------|----------|-------------------------------------------------|
| ``unapproved_present``| error    | ``Unrequested cron detected: <name>``           |
| ``approved_missing``  | warn     | ``Approved cron missing: <name>``               |
| ``schedule_mismatch`` | warn     | ``Approved cron schedule changed: <name>``      |
| ``enabled_mismatch``  | warn     | ``Approved cron disabled: <name>``              |
| ``artifact_missing``  | error    | ``Completion claim not grounded: <artifact_kind>``|
| ``unverifiable_kind`` | warn     | ``Completion claim unverifiable: <artifact_kind>``|
| ``drift_resolved``    | info     | ``Cron drift cleared: <name>``                  |

Redaction is the bus's job (#701/#706) — this module only builds title +
description + a ``details`` dict of forensic fields, all stringified (the
bus requires ``dict[str, str]``). A malformed/unknown finding is guarded so
rendering never crashes a scan tick (NFR-001) — it logs and returns a
``AlertResult(ok=False, ...)`` without raising into the caller.
"""

from __future__ import annotations

import logging
from typing import Any

from scripts.common.alert_bus import emit
from scripts.common.alert_bus.model import Alert, AlertResult, Severity
from scripts.trust.assertion_verifier import AssertionFinding
from scripts.trust.cron_drift_detector import CronDriftFinding

__all__ = [
    "SOURCE_CRON",
    "SOURCE_ASSERTION",
    "render_cron_finding",
    "render_assertion_finding",
    "render_drift_resolved",
    "emit_finding",
]

logger = logging.getLogger(__name__)

# Stable `source` values so downstream ledger/dashboard filters can group by
# sub-scan without parsing the title.
SOURCE_CRON = "felix-trust-scan/cron"
SOURCE_ASSERTION = "felix-trust-scan/assertion"

# Cron finding kind -> (Severity, title template, extra detail keys drawn
# from the finding). Kept as a single source of truth so the severity
# mapping cannot drift between the render function and any future caller.
_CRON_SEVERITY: dict[str, Severity] = {
    "unapproved_present": Severity.ERROR,
    "approved_missing": Severity.WARN,
    "schedule_mismatch": Severity.WARN,
    "enabled_mismatch": Severity.WARN,
}

_CRON_TITLE: dict[str, str] = {
    "unapproved_present": "Unrequested cron detected: {name}",
    "approved_missing": "Approved cron missing: {name}",
    "schedule_mismatch": "Approved cron schedule changed: {name}",
    "enabled_mismatch": "Approved cron disabled: {name}",
}

_CRON_DESCRIPTION: dict[str, str] = {
    "unapproved_present": (
        "A live OpenClaw cron named {name!r} (agent {agent_id!r}) is not in "
        "the approved-cron baseline. This may be standing infrastructure "
        "nobody approved."
    ),
    "approved_missing": (
        "The approved cron {name!r} (agent {agent_id!r}) is in the "
        "baseline but was not found among live OpenClaw crons."
    ),
    "schedule_mismatch": (
        "The approved cron {name!r} (agent {agent_id!r}) is running on a "
        "different schedule than the baseline records."
    ),
    "enabled_mismatch": (
        "The approved cron {name!r} (agent {agent_id!r}) is unexpectedly "
        "disabled."
    ),
}

_ASSERTION_SEVERITY: dict[str, Severity] = {
    "artifact_missing": Severity.ERROR,
    "unverifiable_kind": Severity.WARN,
}

_ASSERTION_TITLE: dict[str, str] = {
    "artifact_missing": "Completion claim not grounded: {artifact_kind}",
    "unverifiable_kind": "Completion claim unverifiable: {artifact_kind}",
}

_ASSERTION_DESCRIPTION: dict[str, str] = {
    "artifact_missing": (
        "Agent {agent!r} claimed a completed {artifact_kind} "
        "(id={artifact_id!r}) that could not be found: {claim}"
    ),
    "unverifiable_kind": (
        "Agent {agent!r} claimed a completed {artifact_kind} "
        "(id={artifact_id!r}) with no existence check available: {claim}"
    ),
}


def _stringify_details(details: dict[str, Any]) -> dict[str, str]:
    """Coerce every value to ``str``, dropping ``None`` entries.

    ``Alert.details`` is contractually ``dict[str, str]`` (#701) — this is
    the single point where every render function funnels its forensic
    fields so the type contract can never be silently violated by a new
    field forgetting to stringify.
    """
    return {key: str(value) for key, value in details.items() if value is not None}


def render_cron_finding(finding: CronDriftFinding) -> Alert:
    """Render a :class:`CronDriftFinding` (WP02) into an :class:`Alert`.

    Raises ``ValueError`` (via ``Alert.__post_init__``) only if a required
    field would be empty — callers (i.e. :func:`emit_finding`) guard this.
    """
    kind = finding.kind
    severity = _CRON_SEVERITY.get(kind, Severity.WARN)
    title_template = _CRON_TITLE.get(kind, "Cron drift detected: {name}")
    description_template = _CRON_DESCRIPTION.get(
        kind, "Cron drift finding {kind!r} for {name!r} (agent {agent_id!r})."
    )

    format_fields = {
        "kind": kind,
        "name": finding.name,
        "agent_id": finding.agent_id,
    }
    title = title_template.format(**format_fields)
    description = description_template.format(**format_fields)

    details = _stringify_details(
        {
            "agent_id": finding.agent_id,
            "cron_id": finding.cron_id,
            "schedule": finding.schedule_expr,
            "expected_schedule": finding.expected_schedule_expr,
            "enabled": finding.enabled,
            "created_at": finding.created_at_ms,
        }
    )

    return Alert(
        source=SOURCE_CRON,
        severity=severity,
        title=title,
        description=description,
        details=details,
    )


def render_assertion_finding(finding: AssertionFinding) -> Alert:
    """Render an :class:`AssertionFinding` (WP03) into an :class:`Alert`."""
    kind = finding.kind
    severity = _ASSERTION_SEVERITY.get(kind, Severity.WARN)
    title_template = _ASSERTION_TITLE.get(
        kind, "Completion claim finding: {artifact_kind}"
    )
    description_template = _ASSERTION_DESCRIPTION.get(
        kind,
        "Assertion finding {kind!r} for agent {agent!r}, artifact_kind "
        "{artifact_kind!r} (id={artifact_id!r}): {claim}",
    )

    format_fields = {
        "kind": kind,
        "agent": finding.agent,
        "artifact_kind": finding.artifact_kind,
        "artifact_id": finding.artifact_id,
        "claim": finding.claim,
    }
    title = title_template.format(**format_fields)
    description = description_template.format(**format_fields)

    details = _stringify_details(
        {
            "agent": finding.agent,
            "artifact_id": finding.artifact_id,
            "claim": finding.claim,
        }
    )

    return Alert(
        source=SOURCE_ASSERTION,
        severity=severity,
        title=title,
        description=description,
        details=details,
    )


def render_drift_resolved(
    name: str, first_seen: str, cleared_at: str, *, source: str = "cron"
) -> Alert:
    """Render a resolution (info) event for a finding that cleared.

    ``first_seen`` / ``cleared_at`` are ISO-8601 UTC strings carried from
    the seen-findings state (:mod:`scripts.trust.state`). ``source`` selects
    the copy + bus ``source`` so an assertion that clears renders as an
    **assertion** resolution, never "Cron drift cleared" (Codex F2). A
    cleared ``artifact_missing`` means the previously-ungrounded completion
    claim is now grounded (the artifact exists).
    """
    if source == "assertion":
        title = f"Completion claim now grounded: {name}"
        description = (
            f"The previously-ungrounded completion claim for {name!r} is now "
            "grounded — the asserted artifact was found as of this scan tick."
        )
        alert_source = SOURCE_ASSERTION
    else:
        title = f"Cron drift cleared: {name}"
        description = (
            f"The previously-alerted drift finding for {name!r} is no longer "
            "present as of this scan tick."
        )
        alert_source = SOURCE_CRON
    details = _stringify_details({"first_seen": first_seen, "cleared_at": cleared_at})

    return Alert(
        source=alert_source,
        severity=Severity.INFO,
        title=title,
        description=description,
        details=details,
    )


def emit_finding(
    finding_or_event: CronDriftFinding | AssertionFinding | Alert,
) -> AlertResult:
    """Render (if needed) and ``emit()`` a finding/event via the ``#701`` bus.

    Accepts a raw finding (:class:`CronDriftFinding` / :class:`AssertionFinding`)
    or an already-built :class:`Alert` (e.g. from :func:`render_drift_resolved`,
    which the caller may build directly since it has no single finding object).
    ``emit()`` itself never raises; this wrapper additionally guards the
    *render* step so a malformed/unknown finding cannot crash the tick
    (NFR-001) — it logs and returns a failed :class:`AlertResult` instead.
    """
    try:
        if isinstance(finding_or_event, Alert):
            alert = finding_or_event
        elif isinstance(finding_or_event, CronDriftFinding):
            alert = render_cron_finding(finding_or_event)
        elif isinstance(finding_or_event, AssertionFinding):
            alert = render_assertion_finding(finding_or_event)
        else:
            logger.warning(
                "alert_render.emit_finding: unrecognized finding type %s; skipping",
                type(finding_or_event).__name__,
            )
            return AlertResult(ok=False, reason="RENDER_UNKNOWN_FINDING_TYPE")
    except Exception as exc:  # noqa: BLE001 - fail-safe: render must never crash the tick
        logger.warning(
            "alert_render.emit_finding: render failed (%s); skipping alert",
            exc,
        )
        return AlertResult(ok=False, reason=f"RENDER_ERROR:{exc.__class__.__name__}")

    return emit(alert)
