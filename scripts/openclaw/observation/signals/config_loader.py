"""Signal-config TOML loader.

Loads ``scripts/openclaw/observation/signals/config.toml`` (or an
operator-supplied override) using stdlib ``tomllib`` (Python 3.11+).
Returns a typed list of :class:`SignalDefinition` records matching the
contract in
``kitty-specs/signal-driven-monitoring-haiku-gate-01KT22PC/contracts/
signal-config.contract.md`` (schema version 1).

Validation policy:
- ``meta.schema_version`` MUST equal :data:`SCHEMA_VERSION`.
- Per-signal validation (positive thresholds, rolling ≥ cycle, absolute
  source path, non-empty match pattern, enum guards) raises
  :class:`ConfigError` with the offending ``signal_id`` in the message.
- Duplicate ``signal_id`` is a load-time error (Python's TOML parser
  rejects duplicate keys at parse time, but defensive checking is kept
  for hand-built dicts in tests).

The loader NEVER reads any other on-disk state. It is safe to invoke
from cold-start contexts.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Union

__all__ = [
    "SCHEMA_VERSION",
    "VALID_SOURCE_KINDS",
    "VALID_MATCH_KINDS",
    "VALID_DEDUP_STRATEGIES",
    "VALID_PRIORITIES",
    "VALID_TIER_HYPOTHESES",
    "ConfigError",
    "SignalDefinition",
    "load_config",
]


SCHEMA_VERSION = 1

VALID_SOURCE_KINDS = frozenset(
    {"openclaw_log", "agent_jsonl", "systemd_journal"}
)
VALID_MATCH_KINDS = frozenset({"regex", "substring"})
VALID_DEDUP_STRATEGIES = frozenset(
    {"open_issue_present", "time_since_last_filed"}
)
VALID_PRIORITIES = frozenset({"P1", "P2"})
VALID_TIER_HYPOTHESES = frozenset({"0", "1", "2", "3", "4", "unknown"})


class ConfigError(Exception):
    """Raised on any load-time failure of ``config.toml``.

    The exception message identifies the offending block / field so
    operators can fix the config without re-running the loader to
    bisect.
    """


@dataclass(frozen=True)
class SignalDefinition:
    """E1 Signal definition record (data-model.md §E1).

    Mirrors the contract schema 1:1. ``frozen=True`` because the
    loader emits these once per cycle and downstream code MUST NOT
    mutate them (eliminates a class of "did we tune this thresholds
    field after extracting?" bugs).
    """

    signal_id: str
    source_kind: str
    source_path_pattern: str
    match_pattern: str
    match_kind: str
    cycle_threshold: int
    rolling_window_minutes: int
    rolling_threshold: int
    dedup_strategy: str
    dedup_window_hours: int
    priority: str
    area_label: str
    tier_hypothesis: str
    excerpt_lines: int
    enabled: bool


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ConfigError(message)


def _build_signal(signal_id: str, raw: dict) -> SignalDefinition:
    """Construct one :class:`SignalDefinition` from a raw TOML block.

    All validation lives here so the load loop stays readable. Each
    failure mode names the offending ``signal_id`` for traceability.
    """
    try:
        source_kind = str(raw["source_kind"])
        source_path_pattern = str(raw["source_path_pattern"])
        match_pattern = str(raw["match_pattern"])
        match_kind = str(raw["match_kind"])
        cycle_threshold = int(raw["cycle_threshold"])
        rolling_threshold = int(raw["rolling_threshold"])
        dedup_strategy = str(raw["dedup_strategy"])
        priority = str(raw["priority"])
        area_label = str(raw["area_label"])
        tier_hypothesis = str(raw["tier_hypothesis"])
        enabled = bool(raw["enabled"])
    except KeyError as exc:
        raise ConfigError(
            f"[signals.{signal_id}] missing required key: {exc}"
        ) from exc
    except (TypeError, ValueError) as exc:
        raise ConfigError(
            f"[signals.{signal_id}] has malformed value: {exc}"
        ) from exc

    rolling_window_minutes = int(raw.get("rolling_window_minutes", 60))
    dedup_window_hours = int(raw.get("dedup_window_hours", 24))
    excerpt_lines = int(raw.get("excerpt_lines", 5))

    _require(
        source_kind in VALID_SOURCE_KINDS,
        f"[signals.{signal_id}] source_kind={source_kind!r} not in "
        f"{sorted(VALID_SOURCE_KINDS)}",
    )
    _require(
        match_kind in VALID_MATCH_KINDS,
        f"[signals.{signal_id}] match_kind={match_kind!r} not in "
        f"{sorted(VALID_MATCH_KINDS)}",
    )
    _require(
        dedup_strategy in VALID_DEDUP_STRATEGIES,
        f"[signals.{signal_id}] dedup_strategy={dedup_strategy!r} not "
        f"in {sorted(VALID_DEDUP_STRATEGIES)}",
    )
    _require(
        priority in VALID_PRIORITIES,
        f"[signals.{signal_id}] priority={priority!r} not in "
        f"{sorted(VALID_PRIORITIES)}",
    )
    _require(
        tier_hypothesis in VALID_TIER_HYPOTHESES,
        f"[signals.{signal_id}] tier_hypothesis={tier_hypothesis!r} "
        f"not in {sorted(VALID_TIER_HYPOTHESES)}",
    )
    _require(
        bool(match_pattern),
        f"[signals.{signal_id}] match_pattern is empty",
    )
    _require(
        Path(source_path_pattern).is_absolute(),
        f"[signals.{signal_id}] source_path_pattern must be absolute, "
        f"got {source_path_pattern!r}",
    )
    _require(
        cycle_threshold >= 1,
        f"[signals.{signal_id}] cycle_threshold must be >= 1, got "
        f"{cycle_threshold}",
    )
    _require(
        rolling_threshold >= cycle_threshold,
        f"[signals.{signal_id}] rolling_threshold ({rolling_threshold}) "
        f"must be >= cycle_threshold ({cycle_threshold})",
    )
    _require(
        rolling_window_minutes >= 1,
        f"[signals.{signal_id}] rolling_window_minutes must be >= 1, "
        f"got {rolling_window_minutes}",
    )
    _require(
        excerpt_lines >= 1,
        f"[signals.{signal_id}] excerpt_lines must be >= 1, got "
        f"{excerpt_lines}",
    )

    return SignalDefinition(
        signal_id=signal_id,
        source_kind=source_kind,
        source_path_pattern=source_path_pattern,
        match_pattern=match_pattern,
        match_kind=match_kind,
        cycle_threshold=cycle_threshold,
        rolling_window_minutes=rolling_window_minutes,
        rolling_threshold=rolling_threshold,
        dedup_strategy=dedup_strategy,
        dedup_window_hours=dedup_window_hours,
        priority=priority,
        area_label=area_label,
        tier_hypothesis=tier_hypothesis,
        excerpt_lines=excerpt_lines,
        enabled=enabled,
    )


def load_config(path: Union[Path, str]) -> list[SignalDefinition]:
    """Load and validate ``signals/config.toml``.

    Args:
        path: Filesystem path to the TOML config.

    Returns:
        A list of :class:`SignalDefinition`, one per ``[signals.*]``
        block, in declared order.

    Raises:
        ConfigError: On any schema / validation failure (missing
            ``[meta]``, wrong schema version, malformed block,
            duplicate ``signal_id``, threshold ordering, etc.).
        FileNotFoundError: If ``path`` does not exist.
    """
    config_path = Path(path)
    if not config_path.is_file():
        raise FileNotFoundError(
            f"Signal config not found: {config_path}"
        )

    try:
        with config_path.open("rb") as fp:
            raw = tomllib.load(fp)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(
            f"Signal config is not valid TOML ({config_path}): {exc}"
        ) from exc

    meta = raw.get("meta")
    if meta is None:
        raise ConfigError(
            f"Signal config {config_path} is missing required [meta] block"
        )
    schema_version = meta.get("schema_version")
    if schema_version != SCHEMA_VERSION:
        raise ConfigError(
            f"Signal config {config_path} has schema_version="
            f"{schema_version!r}, loader expects {SCHEMA_VERSION}"
        )

    signals_block = raw.get("signals", {})
    if not isinstance(signals_block, dict):
        raise ConfigError(
            f"Signal config {config_path} has malformed [signals] block "
            f"(expected table, got {type(signals_block).__name__})"
        )

    seen_ids: set[str] = set()
    definitions: list[SignalDefinition] = []
    for signal_id, raw_block in signals_block.items():
        if not isinstance(raw_block, dict):
            raise ConfigError(
                f"[signals.{signal_id}] is not a table"
            )
        # Defensive duplicate check. ``tomllib`` rejects duplicate
        # keys at parse time, so this branch is unreachable from the
        # public loader. Kept as belt-and-suspenders for future
        # call paths that might construct ``signals_block`` by hand.
        if signal_id in seen_ids:  # pragma: no cover — defensive
            raise ConfigError(
                f"[signals.{signal_id}] duplicate signal_id"
            )
        seen_ids.add(signal_id)
        definitions.append(_build_signal(signal_id, raw_block))

    return definitions
