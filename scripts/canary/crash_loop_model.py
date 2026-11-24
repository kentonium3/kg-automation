"""Crash-loop value types and strict configuration (mission crash-loop-unit-alerting, #1133).

This module holds the immutable value types the crash-loop stage passes between
the readers (effects), the decision core (pure) and the canary integration, plus
the strict loader for ``crash_loop_config.json``.

- Every type is a frozen dataclass with no behaviour beyond trivial properties.
- Times are timezone-aware :class:`datetime` objects; serialisation belongs to
  :mod:`scripts.canary.crash_loop_state`.
- :func:`load_config` validates every rule and raises
  :class:`CrashLoopConfigError` on any violation. It never falls back to
  defaults (research R-10): an invalid config turns every scope ``unknown``.

Kent's 2026-11-24 ruling (research R-16): the decision counts ticks, not time.
No configuration value is a duration, and the timestamps carried by
:class:`TickInterval` are informational only.

Standard library only; no clock reads; no model calls (NFR-006).

References: data-model.md "Tick-counting model", research.md R-10, R-16,
contracts/crash-loop-config.schema.json.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final

__all__ = [
    "DEFAULT_CONFIG_PATH",
    "EVENT_KINDS",
    "SCOPES",
    "UNIT_KEY_RE",
    "CrashLoopConfig",
    "CrashLoopConfigError",
    "CrashLoopEvent",
    "RestartObservation",
    "ScopeReading",
    "TickInterval",
    "load_config",
]

# The three observation scopes, in reading order (data-model.md UnitKey).
SCOPES: Final[tuple[str, ...]] = ("system", "user", "container")

# A UnitKey is "<scope>:<name>" with a non-empty name.
UNIT_KEY_RE: Final[re.Pattern[str]] = re.compile(r"^(system|user|container):.+$")

# The decision's event kinds (data-model.md CrashLoopEvent).
EVENT_KINDS: Final[frozenset[str]] = frozenset({"alert", "reremind", "cleared"})

DEFAULT_CONFIG_PATH: Final[Path] = Path(__file__).with_name("crash_loop_config.json")


# --------------------------------------------------------------------------- #
# Observations (produced by the readers).
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RestartObservation:
    """One watched unit or container, as read on this tick."""

    scope: str
    name: str
    restart_policy: str
    restart_count: int
    state: str
    generation: str

    @property
    def key(self) -> str:
        """The UnitKey, ``"<scope>:<name>"``."""
        return f"{self.scope}:{self.name}"


@dataclass(frozen=True)
class ScopeReading:
    """The result of reading one scope.

    ``complete=False`` means could-not-check (research R-13): the reading then
    carries no observations and a non-empty ``error``. Build instances with
    :meth:`ok` or :meth:`failed`; the invariants are enforced either way.
    """

    scope: str
    complete: bool
    observations: tuple[RestartObservation, ...]
    excluded: int
    error: str | None
    elapsed_ms: int

    def __post_init__(self) -> None:
        if self.scope not in SCOPES:
            raise ValueError(f"ScopeReading: unknown scope {self.scope!r}")
        if self.complete:
            if self.error is not None:
                raise ValueError("ScopeReading: a complete reading has no error")
            for obs in self.observations:
                if obs.scope != self.scope:
                    raise ValueError(
                        f"ScopeReading: observation {obs.key!r} "
                        f"is not in scope {self.scope!r}"
                    )
        else:
            if not self.error or not self.error.strip():
                raise ValueError("ScopeReading: a failed reading needs an error")
            if self.observations:
                raise ValueError("ScopeReading: a failed reading has no observations")

    @classmethod
    def ok(
        cls,
        scope: str,
        observations: tuple[RestartObservation, ...],
        excluded: int,
        elapsed_ms: int,
    ) -> ScopeReading:
        """A complete reading of *scope*."""
        return cls(
            scope=scope,
            complete=True,
            observations=tuple(observations),
            excluded=excluded,
            error=None,
            elapsed_ms=elapsed_ms,
        )

    @classmethod
    def failed(cls, scope: str, error: str, elapsed_ms: int) -> ScopeReading:
        """An incomplete (could-not-check) reading of *scope*."""
        return cls(
            scope=scope,
            complete=False,
            observations=(),
            excluded=0,
            error=error,
            elapsed_ms=elapsed_ms,
        )


# --------------------------------------------------------------------------- #
# Decision outputs.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class TickInterval:
    """One unit's change between the previous complete tick and this one.

    ``delta = current_count − previous_count`` is the only decision input
    (research R-16). ``rose_last_tick`` is the prior tick's rise flag, as the
    rule read it. ``rises`` is the run of consecutive positive deltas ending at
    this tick, this tick's included when it rose (alert text only).
    ``previous_seen_at`` and ``observed_at`` are informational: they fill alert
    text and the ledger and never enter a decision (INV-CL-9′).
    """

    previous_count: int
    current_count: int
    delta: int
    rose_last_tick: bool
    previous_seen_at: datetime
    observed_at: datetime
    rises: tuple[int, ...] = ()


@dataclass(frozen=True)
class CrashLoopEvent:
    """An ``alert``, ``reremind`` or ``cleared`` decision for one unit."""

    kind: str
    key: str
    scope: str
    name: str
    state: str
    episode_started_utc: datetime
    interval: TickInterval

    def __post_init__(self) -> None:
        if self.kind not in EVENT_KINDS:
            raise ValueError(
                f"CrashLoopEvent: kind must be one of {sorted(EVENT_KINDS)}, "
                f"got {self.kind!r}"
            )


# --------------------------------------------------------------------------- #
# Configuration.
# --------------------------------------------------------------------------- #
class CrashLoopConfigError(ValueError):
    """The crash-loop config is unreadable or violates a validation rule."""


@dataclass(frozen=True)
class CrashLoopConfig:
    """Validated crash-loop configuration (data-model.md CrashLoopConfig).

    ``ignore`` is the exact-match set of ignored UnitKeys; ``ignore_reasons``
    maps each of them to its documented reason (read-only).
    """

    threshold: int
    consecutive_rise_ticks: int
    quiet_ticks_to_clear: int
    reremind_ticks: int
    max_alerts_per_tick: int
    read_budget_seconds: int
    ignore: frozenset[str]
    ignore_reasons: Mapping[str, str]


# (field, minimum, maximum or None) for every integer key.
_INT_RULES: Final[tuple[tuple[str, int, int | None], ...]] = (
    ("threshold", 2, 50),
    ("consecutive_rise_ticks", 2, None),
    ("quiet_ticks_to_clear", 1, None),
    ("reremind_ticks", 1, None),
    ("max_alerts_per_tick", 1, None),
    ("read_budget_seconds", 1, 10),
)
_KNOWN_KEYS: Final[frozenset[str]] = frozenset(
    {name for name, _, _ in _INT_RULES} | {"ignore"}
)
_IGNORE_ENTRY_KEYS: Final[frozenset[str]] = frozenset({"unit", "reason"})


def _validate_int(
    document: Mapping[str, Any], name: str, low: int, high: int | None
) -> int:
    value = document[name]
    # bool is an int subclass; reject it explicitly, as well as floats.
    if isinstance(value, bool) or not isinstance(value, int):
        raise CrashLoopConfigError(f"{name}: must be an integer, got {value!r}")
    if value < low or (high is not None and value > high):
        span = f"{low}..{high}" if high is not None else f">= {low}"
        raise CrashLoopConfigError(f"{name}: must be {span}, got {value}")
    return value


def _validate_ignore(value: Any) -> dict[str, str]:
    if not isinstance(value, list):
        raise CrashLoopConfigError(
            f"ignore: must be a list, got {type(value).__name__}"
        )
    reasons: dict[str, str] = {}
    for index, entry in enumerate(value):
        where = f"ignore[{index}]"
        if not isinstance(entry, dict):
            raise CrashLoopConfigError(f"{where}: must be an object")
        if set(entry) != _IGNORE_ENTRY_KEYS:
            raise CrashLoopConfigError(
                f"{where}: must have exactly the keys 'reason' and 'unit', "
                f"got {sorted(entry)}"
            )
        unit = entry["unit"]
        reason = entry["reason"]
        if not isinstance(unit, str) or not UNIT_KEY_RE.match(unit):
            raise CrashLoopConfigError(
                f"{where}.unit: must match <system|user|container>:<name>, got {unit!r}"
            )
        if not isinstance(reason, str) or not reason.strip():
            raise CrashLoopConfigError(f"{where}.reason: must be a non-empty string")
        if unit in reasons:
            raise CrashLoopConfigError(f"{where}.unit: duplicate entry {unit!r}")
        reasons[unit] = reason
    return reasons


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> CrashLoopConfig:
    """Read and strictly validate the crash-loop config at *path*.

    Raises :class:`CrashLoopConfigError`, naming the field, on an unreadable
    file, invalid JSON, a missing or unknown key (including the retired
    ``window_seconds``), any rule violation, or a ``reremind_ticks`` below
    ``consecutive_rise_ticks - 1``. It never substitutes a
    default (research R-10).
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise CrashLoopConfigError(f"config unreadable: {path}: {exc}") from exc
    try:
        document = json.loads(text)
    except (ValueError, RecursionError) as exc:
        # ValueError covers JSONDecodeError and the int digit limit;
        # RecursionError covers excessive nesting.
        raise CrashLoopConfigError(f"config is not valid JSON: {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise CrashLoopConfigError("config: top level must be a JSON object")

    unknown = sorted(set(document) - _KNOWN_KEYS)
    if unknown:
        raise CrashLoopConfigError(f"config: unknown keys {unknown}")
    missing = sorted(_KNOWN_KEYS - set(document))
    if missing:
        raise CrashLoopConfigError(f"config: missing keys {missing}")

    ints = {
        name: _validate_int(document, name, low, high) for name, low, high in _INT_RULES
    }
    # A re-remind fires when the trigger holds on a tick at least
    # ``reremind_ticks`` ticks after the last page. Its rise run spans this tick
    # and the ``consecutive_rise_ticks - 1`` before it, so a shorter interval
    # would let a re-remind rest on rises from before the last page (the WP02
    # fresh-evidence ruling, research R-16).
    if ints["reremind_ticks"] < ints["consecutive_rise_ticks"] - 1:
        raise CrashLoopConfigError(
            "reremind_ticks: must be >= consecutive_rise_ticks - 1 "
            f"({ints['consecutive_rise_ticks'] - 1}), got {ints['reremind_ticks']}; "
            "a shorter interval lets a re-remind reuse rises from before the last page"
        )
    reasons = _validate_ignore(document["ignore"])
    return CrashLoopConfig(
        threshold=ints["threshold"],
        consecutive_rise_ticks=ints["consecutive_rise_ticks"],
        quiet_ticks_to_clear=ints["quiet_ticks_to_clear"],
        reremind_ticks=ints["reremind_ticks"],
        max_alerts_per_tick=ints["max_alerts_per_tick"],
        read_budget_seconds=ints["read_budget_seconds"],
        ignore=frozenset(reasons),
        ignore_reasons=MappingProxyType(reasons),
    )
