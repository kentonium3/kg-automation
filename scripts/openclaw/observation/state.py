"""Per-signal state persistence (data-model.md §E2).

Each signal has its own JSON state file at
``<state_dir>/<signal_id>.json``. State is written atomically (tmp
file + ``os.rename`` on the same filesystem). Readers see either the
prior version or the new version — never a partial write.

Cold-start recovery: when a state file is missing the orchestrator
re-reads the most recent four 15-minute cycles (1 hour) of source
content before trusting state. The 4-cycle window is exposed via
:func:`cold_start_recovery_window_seconds` so both the orchestrator
and tests pull from one constant.

Timestamp policy (matches the felix-doc-auditor pattern):
- All datetimes are UTC. Naive datetimes are rejected on save.
- ISO-8601 strings end with the literal ``Z`` suffix.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

__all__ = [
    "COLD_START_RECOVERY_CYCLES",
    "CYCLE_DURATION_SECONDS",
    "RollingBucket",
    "SignalState",
    "cold_start_recovery_window_seconds",
    "evict_old_buckets",
    "load_state",
    "save_state",
]


# 15-min cycles × 4 = 1 hour of cold-start recovery (data-model.md §E2).
COLD_START_RECOVERY_CYCLES = 4
CYCLE_DURATION_SECONDS = 900  # 15 minutes


@dataclass(frozen=True)
class RollingBucket:
    """One cycle's bucket in the rolling-window counter.

    Mirrors the inner structure of E2 ``rolling_buckets[]``.
    ``started_at`` is an ISO-8601 UTC string with the ``Z`` suffix.
    """

    cycle_id: str
    started_at: str
    count: int


@dataclass
class SignalState:
    """E2 Signal state — persistent per-signal counter (data-model.md).

    Mutable because the orchestrator updates fields as it processes
    each cycle. Serialization is structural: :func:`save_state`
    converts to a dict that round-trips through :func:`load_state`.
    """

    signal_id: str
    cycle_id: str
    last_cycle_count: int
    rolling_buckets: list[RollingBucket] = field(default_factory=list)
    last_event_at_utc: Optional[str] = None
    last_filed_issue_ref: Optional[int] = None
    last_filed_at_utc: Optional[str] = None
    last_log_position: Optional[dict] = None


def cold_start_recovery_window_seconds() -> int:
    """Return the cold-start recovery window in seconds.

    Documented inline so tests and the orchestrator agree on the same
    constant (1 hour = 4 × 15-min cycles).
    """
    return COLD_START_RECOVERY_CYCLES * CYCLE_DURATION_SECONDS


def _state_path(state_dir: Union[Path, str], signal_id: str) -> Path:
    """Resolve the canonical state file path for a signal."""
    return Path(state_dir) / f"{signal_id}.json"


def _to_dict(state: SignalState) -> dict[str, Any]:
    """Convert a :class:`SignalState` to a JSON-serializable dict.

    ``asdict`` handles the nested :class:`RollingBucket` records
    structurally. We do not customize the encoder — keeping the
    on-disk shape an exact mirror of the dataclass keeps the loader
    branchless.
    """
    return asdict(state)


def _from_dict(raw: dict[str, Any]) -> SignalState:
    """Reconstruct :class:`SignalState` from a parsed JSON dict."""
    buckets_raw = raw.get("rolling_buckets") or []
    rolling = [
        RollingBucket(
            cycle_id=str(b["cycle_id"]),
            started_at=str(b["started_at"]),
            count=int(b["count"]),
        )
        for b in buckets_raw
    ]
    return SignalState(
        signal_id=str(raw["signal_id"]),
        cycle_id=str(raw["cycle_id"]),
        last_cycle_count=int(raw["last_cycle_count"]),
        rolling_buckets=rolling,
        last_event_at_utc=raw.get("last_event_at_utc"),
        last_filed_issue_ref=raw.get("last_filed_issue_ref"),
        last_filed_at_utc=raw.get("last_filed_at_utc"),
        last_log_position=raw.get("last_log_position"),
    )


def load_state(
    state_dir: Union[Path, str], signal_id: str
) -> Optional[SignalState]:
    """Return the persisted state for ``signal_id``, or ``None``.

    Returns:
        Parsed :class:`SignalState` on a clean read. ``None`` if the
        state file does not exist (cold-start signal).

    Raises:
        OSError: On I/O errors reading the file.
        ValueError: When the file exists but is not parseable JSON or
            is missing required fields. Callers should treat this as
            "state file corrupt — fall back to cold start" per
            spec edge case "State file missing or corrupt at cycle
            start."
    """
    path = _state_path(state_dir, signal_id)
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as fp:
            raw = json.load(fp)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"State file {path} is not valid JSON: {exc}"
        ) from exc
    try:
        return _from_dict(raw)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            f"State file {path} is missing/malformed fields: {exc}"
        ) from exc


def save_state(
    state_dir: Union[Path, str], state: SignalState
) -> Path:
    """Atomically persist ``state`` to ``<state_dir>/<signal_id>.json``.

    Atomicity contract (matches the felix-doc-auditor pattern):
    1. Open a ``NamedTemporaryFile`` in the SAME directory as the
       target (``os.rename`` is only POSIX-atomic on the same
       filesystem).
    2. Write JSON, ``flush()`` + ``fsync()``.
    3. ``os.rename`` over the target.
    4. If the rename raises, best-effort delete the temp file so we
       don't leak ``<name>.tmp`` orphans.

    Returns:
        The :class:`Path` of the written file.
    """
    target = _state_path(state_dir, state.signal_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = _to_dict(state)

    tmp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            dir=str(target.parent),
            prefix=target.name + ".",
            suffix=".tmp",
            delete=False,
            encoding="utf-8",
        ) as fp:
            json.dump(payload, fp, indent=2)
            fp.flush()
            os.fsync(fp.fileno())
            tmp_path = Path(fp.name)
        os.rename(tmp_path, target)
        tmp_path = None
    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink()
            except OSError:  # pragma: no cover — best-effort cleanup
                pass

    return target


def _parse_iso_z(value: str) -> datetime:
    """Parse an ISO-8601 ``Z``-suffixed string to a UTC datetime."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def evict_old_buckets(
    state: SignalState,
    window_minutes: int,
    now_utc: datetime,
) -> SignalState:
    """Return a new :class:`SignalState` with stale buckets dropped.

    A bucket is "stale" when ``started_at`` is older than
    ``window_minutes`` before ``now_utc``. The original state is not
    mutated — callers either replace the state object or assign the
    returned bucket list back.

    Args:
        state: Existing state record.
        window_minutes: Width of the rolling window from the signal
            definition.
        now_utc: Current UTC clock (caller passes
            ``datetime.now(tz=timezone.utc)``).

    Raises:
        ValueError: If ``now_utc`` is naive (no tzinfo). Naive
            datetimes leak local-time drift into the rolling window
            math; we reject them at the boundary instead.
    """
    if now_utc.tzinfo is None:
        raise ValueError(
            "evict_old_buckets: now_utc must be timezone-aware"
        )

    cutoff_seconds = window_minutes * 60
    retained: list[RollingBucket] = []
    for bucket in state.rolling_buckets:
        try:
            started = _parse_iso_z(bucket.started_at)
        except ValueError:
            # Malformed bucket timestamp — drop it (defensive; loader
            # only emits well-formed strings). This branch keeps a
            # half-corrupt state file from blocking eviction.
            continue
        if started.tzinfo is None:  # pragma: no branch — guarded above
            # The ISO loader always returns tz-aware datetimes when
            # the suffix is "Z". This branch is defensive.
            started = started.replace(tzinfo=timezone.utc)
        age_seconds = (now_utc - started).total_seconds()
        if age_seconds <= cutoff_seconds:
            retained.append(bucket)

    return SignalState(
        signal_id=state.signal_id,
        cycle_id=state.cycle_id,
        last_cycle_count=state.last_cycle_count,
        rolling_buckets=retained,
        last_event_at_utc=state.last_event_at_utc,
        last_filed_issue_ref=state.last_filed_issue_ref,
        last_filed_at_utc=state.last_filed_at_utc,
        last_log_position=state.last_log_position,
    )
