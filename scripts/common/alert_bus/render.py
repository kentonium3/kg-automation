"""Title/body rendering for the felix-alert bus.

Renders a human-readable title + multi-line body from an :class:`Alert`.
The body shows every present schema field, degrades gracefully when optional
fields are absent (NFR-003 — omit sections rather than emit placeholders),
and redacts secrets **before** truncation (D8 — truncate-first would slice a
secret pattern across the boundary and leak head bytes).

The secret redactor is reused from the deploy library
(``scripts.deploy.lib.verify.redact_secrets``) so the bus and the existing
emitters share one behavior.
"""

from __future__ import annotations

from datetime import datetime, timezone

from scripts.deploy.lib.verify import redact_secrets

from .model import Alert

# Bounded length for redacted detail values. Matches the deployer's
# ERROR_SUMMARY_MAX so migrated failure alerts keep byte-comparable bodies.
DETAIL_VALUE_MAX = 500


def _redact_and_truncate(value: str) -> str:
    """Redact secrets, THEN truncate to :data:`DETAIL_VALUE_MAX`.

    Order is invariant: truncate-first could slice a secret pattern across the
    boundary and leak head bytes.
    """
    redacted = redact_secrets(value or "")
    if len(redacted) > DETAIL_VALUE_MAX:
        redacted = redacted[:DETAIL_VALUE_MAX]
    return redacted


def _format_timestamp(ts: datetime) -> str:
    """Render a timestamp as UTC + local.

    A naive timestamp is assumed to already be UTC (the Alert default is
    UTC-aware; this only guards hand-built naive values). ``astimezone()``
    with no argument converts to the system local zone.
    """
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    utc = ts.astimezone(timezone.utc)
    local = ts.astimezone()
    return f"{utc.isoformat()} (UTC) / {local.isoformat()} (local)"


def render_title(alert: Alert) -> str:
    """Return the ntfy ``Title`` header value for *alert*."""
    return alert.title


def render_body(alert: Alert) -> str:
    """Return the multi-line ntfy body for *alert*.

    Order: timestamp (UTC + local), ``Source:``, ``Severity:``, a blank line,
    the ``description``, then ``Action:`` only if set, then a ``Details:``
    block of ``key=value`` lines only if ``details`` is non-empty. Detail
    values are redacted then truncated.
    """
    lines: list[str] = [
        _format_timestamp(alert.timestamp),
        f"Source: {alert.source}",
        f"Severity: {alert.severity.value}",
        "",
        alert.description,
    ]

    if alert.action:
        lines.append(f"Action: {alert.action}")

    if alert.details:
        lines.append("Details:")
        for key, value in alert.details.items():
            lines.append(f"  {key}={_redact_and_truncate(str(value))}")

    return "\n".join(lines)


__all__ = ["render_title", "render_body", "DETAIL_VALUE_MAX"]
