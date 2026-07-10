"""Value objects for the felix-alert bus.

The bus is stateless; these are in-memory value objects plus the fixed
severity → ntfy header mapping. See ``../data-model.md`` for the canonical
schema.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class Severity(str, Enum):
    """Ordered alert severity: ``info`` < ``warn`` < ``error`` < ``critical``.

    Subclasses :class:`str` so the enum members compare/serialise as their
    string values (``info|warn|error|critical``) while still being ordered
    for criticality comparisons.
    """

    INFO = "info"
    WARN = "warn"
    ERROR = "error"
    CRITICAL = "critical"

    @property
    def _rank(self) -> int:
        return _SEVERITY_ORDER[self]

    def __lt__(self, other: object) -> bool:  # type: ignore[override]
        if isinstance(other, Severity):
            return self._rank < other._rank
        return NotImplemented

    def __le__(self, other: object) -> bool:  # type: ignore[override]
        if isinstance(other, Severity):
            return self._rank <= other._rank
        return NotImplemented

    def __gt__(self, other: object) -> bool:  # type: ignore[override]
        if isinstance(other, Severity):
            return self._rank > other._rank
        return NotImplemented

    def __ge__(self, other: object) -> bool:  # type: ignore[override]
        if isinstance(other, Severity):
            return self._rank >= other._rank
        return NotImplemented


_SEVERITY_ORDER: dict[Severity, int] = {
    Severity.INFO: 0,
    Severity.WARN: 1,
    Severity.ERROR: 2,
    Severity.CRITICAL: 3,
}


# Single source of truth: severity → (ntfy Priority header, ntfy Tags header).
# Monotonic priority gradient so criticality is visually distinct on one
# thread (FR-004). Tags are comma-separated shortcodes, exactly as today's
# emitters render them.
SEVERITY_MAP: dict[Severity, tuple[str, str]] = {
    Severity.INFO: ("low", "information_source"),
    Severity.WARN: ("default", "warning"),
    Severity.ERROR: ("high", "rotating_light"),
    Severity.CRITICAL: ("max", "rotating_light,sos"),
}


def _utc_now() -> datetime:
    """Return a UTC-aware ``datetime`` for the default alert timestamp."""
    return datetime.now(timezone.utc)


@dataclass
class Alert:
    """Uniform alert value object every emitter constructs.

    ``source``, ``severity``, ``title`` and ``description`` are required and
    must be non-empty — a malformed Alert is a programming error, caught in
    :meth:`__post_init__`. Optional fields absent still render to a readable
    message (NFR-003); the renderer omits absent sections rather than emitting
    placeholders.
    """

    source: str
    severity: Severity
    title: str
    description: str
    action: str | None = None
    details: dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        if not isinstance(self.severity, Severity):
            raise ValueError(
                f"severity must be a Severity, got {type(self.severity).__name__}"
            )
        for name in ("source", "title", "description"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Alert.{name} is required and must be non-empty")


@dataclass
class AlertResult:
    """The fail-safe contract returned by ``emit()`` (D7).

    ``ok`` is True iff the ntfy POST succeeded. ``reason`` names the failure
    when ``ok`` is False (e.g. ``NTFY_MISSING_TOPIC``, ``CURL_TIMEOUT``,
    ``CURL_CONNECT``, ``CURL_HTTP``). ``topic_configured`` is False when
    ``FELIX_ALERT_NTFY_TOPIC`` is unset/blank.
    """

    ok: bool
    reason: str | None = None
    topic_configured: bool = True


__all__ = ["Severity", "SEVERITY_MAP", "Alert", "AlertResult"]
