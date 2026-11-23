"""Crash-loop persisted state: fail-safe load, atomic save, non-blocking lock (#1133).

The document lives at ``/data/services/felix-canary/state/crash-loop.json``::

    {"schema_version": 1, "updated_at_utc": ..., "boot_id": ...,
     "units": {<UnitKey>: {"generation", "boot_id", "history", "episode"}}}

- :func:`load_state` never raises. A missing file loads empty with no
  diagnostic; an unreadable, corrupt, non-object or unknown-version document
  loads empty with one diagnostic. Each unit entry is validated semantically
  and a malformed entry is dropped **alone**, with one diagnostic (research R-07).
- **The single clock rule**: on load, any time in a unit entry later than
  ``now + 60 s`` makes the entry malformed. It is dropped, and the unit becomes
  first-seen; times are never clamped.
- Naive datetimes are rejected, never coerced to UTC.
- :func:`save_state` writes atomically (temp file in the same directory,
  ``fsync``, ``os.replace``; the temp file is removed on failure), mirroring
  :mod:`scripts.canary.dedup`, and raises on failure.
- :class:`StateLock` takes an exclusive, non-blocking ``flock`` and raises
  :class:`StateLockBusy` when another holder has it. It never blocks.

``now`` is always injected; nothing here reads the clock.

References: data-model.md (UnitState, Episode, CrashLoopState), research.md
R-07, contracts/crash-loop-state.schema.json.
"""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import TracebackType
from typing import Any, Final, Self

from scripts.canary.crash_loop_model import UNIT_KEY_RE

__all__ = [
    "CLOCK_TOLERANCE",
    "DEFAULT_LOCK_PATH",
    "DEFAULT_STATE_PATH",
    "SCHEMA_VERSION",
    "CrashLoopState",
    "Episode",
    "StateLock",
    "StateLockBusy",
    "UnitState",
    "load_state",
    "save_state",
]

DEFAULT_STATE_PATH: Final[Path] = Path(
    "/data/services/felix-canary/state/crash-loop.json"
)
DEFAULT_LOCK_PATH: Final[Path] = DEFAULT_STATE_PATH.with_name("crash-loop.lock")

SCHEMA_VERSION: Final[int] = 1

# A stored time later than now + CLOCK_TOLERANCE makes its unit entry malformed.
CLOCK_TOLERANCE: Final[timedelta] = timedelta(seconds=60)

_DIAG_PREFIX: Final[str] = "crash_loop_state"
_KEY_REPR_MAX: Final[int] = 80


# --------------------------------------------------------------------------- #
# In-memory types.
# --------------------------------------------------------------------------- #
@dataclass
class Episode:
    """An open crash-loop episode. There is no pending flag: no retry (R-08)."""

    started_utc: datetime
    last_alert_utc: datetime
    quiet_ticks: int
    peak_delta: int


@dataclass
class UnitState:
    """Per-unit persisted state. ``history[-1]`` is the latest observation."""

    generation: str
    boot_id: str
    history: list[tuple[datetime, int]]
    episode: Episode | None


@dataclass
class CrashLoopState:
    """The whole persisted document, in memory."""

    updated_at_utc: datetime | None
    boot_id: str | None
    units: dict[str, UnitState] = field(default_factory=dict)

    @classmethod
    def empty(cls) -> CrashLoopState:
        """A state with no units: every unit is first-seen."""
        return cls(updated_at_utc=None, boot_id=None, units={})


# --------------------------------------------------------------------------- #
# Load.
# --------------------------------------------------------------------------- #
class _Malformed(ValueError):
    """Internal: a unit entry failed validation; the message is the reason."""


def _parse_time(value: Any, where: str, latest: datetime) -> datetime:
    if not isinstance(value, str):
        raise _Malformed(f"{where}: time must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise _Malformed(f"{where}: unparseable time {value!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _Malformed(f"{where}: naive time {value!r}")
    if parsed > latest:
        raise _Malformed(f"{where}: time {value!r} is later than now + 60 s")
    return parsed


def _is_count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _parse_history(value: Any, latest: datetime) -> list[tuple[datetime, int]]:
    if not isinstance(value, list) or not value:
        raise _Malformed("history: must be a non-empty list")
    history: list[tuple[datetime, int]] = []
    for index, item in enumerate(value):
        where = f"history[{index}]"
        if not isinstance(item, list) or len(item) != 2:
            raise _Malformed(f"{where}: must be an [iso8601, count] pair")
        at = _parse_time(item[0], where, latest)
        count = item[1]
        if not _is_count(count):
            raise _Malformed(f"{where}: count must be an integer >= 0")
        if history:
            prev_at, prev_count = history[-1]
            if at <= prev_at:
                raise _Malformed(f"{where}: times are not strictly ascending")
            if count <= prev_count:
                raise _Malformed(f"{where}: counts are not strictly increasing")
        history.append((at, count))
    return history


def _parse_episode(value: Any, latest: datetime) -> Episode | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise _Malformed("episode: must be null or an object")
    for name in ("quiet_ticks", "peak_delta"):
        if not _is_count(value.get(name)):
            raise _Malformed(f"episode.{name}: must be an integer >= 0")
    return Episode(
        started_utc=_parse_time(
            value.get("started_utc"), "episode.started_utc", latest
        ),
        last_alert_utc=_parse_time(
            value.get("last_alert_utc"), "episode.last_alert_utc", latest
        ),
        quiet_ticks=value["quiet_ticks"],
        peak_delta=value["peak_delta"],
    )


def _parse_unit(key: str, entry: Any, latest: datetime) -> UnitState:
    if not UNIT_KEY_RE.match(key):
        raise _Malformed("key does not match <system|user|container>:<name>")
    if not isinstance(entry, dict):
        raise _Malformed("entry must be an object")
    generation = entry.get("generation")
    if not isinstance(generation, str) or not generation:
        raise _Malformed("generation: must be a non-empty string")
    boot_id = entry.get("boot_id")
    if not isinstance(boot_id, str) or not boot_id:
        raise _Malformed("boot_id: must be a non-empty string")
    if "episode" not in entry:
        raise _Malformed("episode: missing")
    return UnitState(
        generation=generation,
        boot_id=boot_id,
        history=_parse_history(entry.get("history"), latest),
        episode=_parse_episode(entry["episode"], latest),
    )


def _diag(message: str) -> str:
    return f"{_DIAG_PREFIX}: {message}"


def load_state(
    path: Path | str = DEFAULT_STATE_PATH, *, now: datetime
) -> tuple[CrashLoopState, list[str]]:
    """Load the crash-loop state; fail-safe, never raises.

    Returns ``(state, diagnostics)`` with one diagnostic string per dropped
    entry or reset field (the caller writes them into the scope evidence).
    *now* must be timezone-aware; it anchors the clock rule.
    """
    target = Path(path)
    try:
        text = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        return CrashLoopState.empty(), []
    except (OSError, UnicodeDecodeError) as exc:
        return CrashLoopState.empty(), [_diag(f"unreadable state file {target}: {exc}")]

    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        return CrashLoopState.empty(), [_diag(f"corrupt state file {target}: {exc}")]
    if not isinstance(document, dict):
        return CrashLoopState.empty(), [_diag("state document is not a JSON object")]
    version = document.get("schema_version")
    if isinstance(version, bool) or version != SCHEMA_VERSION:
        return CrashLoopState.empty(), [
            _diag(f"unsupported schema_version {version!r}")
        ]
    units_raw = document.get("units")
    if not isinstance(units_raw, dict):
        return CrashLoopState.empty(), [_diag("units is not a JSON object")]

    latest = now + CLOCK_TOLERANCE
    diagnostics: list[str] = []

    boot_id = document.get("boot_id")
    if boot_id is not None and not isinstance(boot_id, str):
        diagnostics.append(
            _diag(f"top-level boot_id {boot_id!r} is not a string; reset")
        )
        boot_id = None

    updated_at: datetime | None = None
    raw_updated = document.get("updated_at_utc")
    if raw_updated is not None:
        try:
            updated_at = _parse_time(raw_updated, "updated_at_utc", latest)
        except _Malformed as exc:
            diagnostics.append(_diag(f"{exc}; reset"))

    units: dict[str, UnitState] = {}
    for key, entry in units_raw.items():
        try:
            units[key] = _parse_unit(key, entry, latest)
        except _Malformed as exc:
            shown = repr(key)
            if len(shown) > _KEY_REPR_MAX:
                shown = shown[: _KEY_REPR_MAX - 3] + "..."
            diagnostics.append(_diag(f"dropped unit {shown}: {exc}"))

    return CrashLoopState(
        updated_at_utc=updated_at, boot_id=boot_id, units=units
    ), diagnostics


# --------------------------------------------------------------------------- #
# Save.
# --------------------------------------------------------------------------- #
def _iso(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"refusing to serialise naive datetime {value!r}")
    return value.astimezone(UTC).isoformat()


def _unit_document(unit: UnitState) -> dict[str, Any]:
    episode = unit.episode
    return {
        "generation": unit.generation,
        "boot_id": unit.boot_id,
        "history": [[_iso(at), count] for at, count in unit.history],
        "episode": None
        if episode is None
        else {
            "started_utc": _iso(episode.started_utc),
            "last_alert_utc": _iso(episode.last_alert_utc),
            "quiet_ticks": episode.quiet_ticks,
            "peak_delta": episode.peak_delta,
        },
    }


def save_state(
    state: CrashLoopState, path: Path | str = DEFAULT_STATE_PATH, *, now: datetime
) -> None:
    """Atomically write *state* to *path*, stamping ``updated_at_utc`` with *now*.

    Never partially writes. Raises on failure (including a naive datetime);
    the caller records the error.
    """
    document = {
        "schema_version": SCHEMA_VERSION,
        "updated_at_utc": _iso(now),
        "boot_id": state.boot_id,
        "units": {key: _unit_document(unit) for key, unit in state.units.items()},
    }
    payload = json.dumps(document, sort_keys=True, indent=2) + "\n"

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(target.parent), prefix=f".{target.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, target)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


# --------------------------------------------------------------------------- #
# Lock.
# --------------------------------------------------------------------------- #
class StateLockBusy(RuntimeError):
    """Another holder has the crash-loop state lock."""


class StateLock:
    """Exclusive, non-blocking ``flock`` on the lock file, as a context manager."""

    def __init__(self, lock_path: Path | str = DEFAULT_LOCK_PATH) -> None:
        self._path = Path(lock_path)
        self._fd: int | None = None

    def __enter__(self) -> Self:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self._path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            os.close(fd)
            raise StateLockBusy(f"crash-loop state lock busy: {self._path}") from exc
        except BaseException:
            os.close(fd)
            raise
        self._fd = fd
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        fd, self._fd = self._fd, None
        if fd is not None:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)
