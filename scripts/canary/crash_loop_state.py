"""Crash-loop persisted state: fail-safe load, atomic save, non-blocking lock (#1133).

The document lives at ``/data/services/felix-canary/state/crash-loop.json``::

    {"schema_version": 2, "updated_at_utc": ..., "boot_id": ...,
     "units": {<UnitKey>: {"generation", "boot_id", "last_count",
                           "rose_last_tick", "recent_rises", "last_seen_at",
                           "episode"}}}

Kent's 2026-11-24 ruling (research R-16) replaced the per-unit history with the
previous tick's count and whether it rose. ``schema_version`` is therefore 2;
any other version (v1 was never deployed) loads empty, which is fail-safe:
every unit becomes first-seen.

- :func:`load_state` never raises. A missing file loads empty with no
  diagnostic; an unreadable, corrupt, non-object or unknown-version document
  loads empty with one diagnostic. Each unit entry is validated against the
  state schema and a malformed entry is dropped **alone**, with one diagnostic.
- Times are informational (INV-CL-9′). They must parse as timezone-aware
  ISO-8601, but their values are never compared with anything: there is no
  clock rule.
- ``recent_rises`` (not in the contract schema, which allows extra unit
  properties) holds the run of consecutive positive deltas ending at the last
  tick. It generalises ``rose_last_tick`` to ``consecutive_rise_ticks = N``
  and must agree with it: ``rose_last_tick`` is true exactly when it is
  non-empty.
- :func:`save_state` writes atomically (temp file in the same directory,
  ``fsync``, ``os.replace``; the temp file is removed on failure), mirroring
  :mod:`scripts.canary.dedup`, and raises on failure.
- :class:`StateLock` takes an exclusive, non-blocking ``flock`` and raises
  :class:`StateLockBusy` when another holder has it. It never blocks.

Nothing here reads the clock.

References: data-model.md "Tick-counting model", research.md R-07, R-16,
contracts/crash-loop-state.schema.json.
"""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any, Final, Self

from scripts.canary.crash_loop_model import UNIT_KEY_RE

__all__ = [
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

SCHEMA_VERSION: Final[int] = 2

_DIAG_PREFIX: Final[str] = "crash_loop_state"
_KEY_REPR_MAX: Final[int] = 80


# --------------------------------------------------------------------------- #
# In-memory types.
# --------------------------------------------------------------------------- #
@dataclass
class Episode:
    """An open crash-loop episode. There is no pending flag: no retry (R-08).

    ``ticks_since_alert`` and ``quiet_ticks`` drive the decisions; the two
    times are informational (alert text and the ledger).
    """

    started_utc: datetime
    last_alert_utc: datetime
    ticks_since_alert: int
    quiet_ticks: int
    peak_delta: int


@dataclass
class UnitState:
    """Per-unit persisted state: the previous complete tick's observation.

    ``recent_rises`` is the run of consecutive positive deltas ending at that
    tick (empty when it did not rise); ``last_seen_at`` is informational.
    """

    generation: str
    boot_id: str
    last_count: int
    recent_rises: tuple[int, ...]
    last_seen_at: datetime
    episode: Episode | None

    @property
    def rose_last_tick(self) -> bool:
        """True when the counter rose on the previous complete tick."""
        return bool(self.recent_rises)


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


def _parse_time(value: Any, where: str) -> datetime:
    if not isinstance(value, str):
        raise _Malformed(f"{where}: time must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise _Malformed(f"{where}: unparseable time {value!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _Malformed(f"{where}: naive time {value!r}")
    return parsed


def _is_count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _parse_episode(value: Any) -> Episode | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise _Malformed("episode: must be null or an object")
    for name in ("ticks_since_alert", "quiet_ticks", "peak_delta"):
        if not _is_count(value.get(name)):
            raise _Malformed(f"episode.{name}: must be an integer >= 0")
    return Episode(
        started_utc=_parse_time(value.get("started_utc"), "episode.started_utc"),
        last_alert_utc=_parse_time(
            value.get("last_alert_utc"), "episode.last_alert_utc"
        ),
        ticks_since_alert=value["ticks_since_alert"],
        quiet_ticks=value["quiet_ticks"],
        peak_delta=value["peak_delta"],
    )


def _parse_rises(entry: dict[str, Any]) -> tuple[int, ...]:
    rose = entry.get("rose_last_tick")
    if not isinstance(rose, bool):
        raise _Malformed("rose_last_tick: must be a boolean")
    raw = entry.get("recent_rises")
    if not isinstance(raw, list):
        raise _Malformed("recent_rises: must be a list")
    for index, item in enumerate(raw):
        if not _is_count(item) or item < 1:
            raise _Malformed(f"recent_rises[{index}]: must be an integer >= 1")
    if rose != bool(raw):
        raise _Malformed("rose_last_tick disagrees with recent_rises")
    return tuple(raw)


def _parse_unit(key: str, entry: Any) -> UnitState:
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
    last_count = entry.get("last_count")
    if not isinstance(last_count, int) or not _is_count(last_count):
        raise _Malformed("last_count: must be an integer >= 0")
    if "episode" not in entry:
        raise _Malformed("episode: missing")
    return UnitState(
        generation=generation,
        boot_id=boot_id,
        last_count=last_count,
        recent_rises=_parse_rises(entry),
        last_seen_at=_parse_time(entry.get("last_seen_at"), "last_seen_at"),
        episode=_parse_episode(entry["episode"]),
    )


def _diag(message: str) -> str:
    return f"{_DIAG_PREFIX}: {message}"


def load_state(
    path: Path | str = DEFAULT_STATE_PATH,
) -> tuple[CrashLoopState, list[str]]:
    """Load the crash-loop state; fail-safe, never raises.

    Returns ``(state, diagnostics)`` with one diagnostic string per dropped
    entry or reset field (the caller writes them into the scope evidence).
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
    except (ValueError, RecursionError) as exc:
        # ValueError covers JSONDecodeError and the int digit limit;
        # RecursionError covers excessive nesting. Both mean corrupt state.
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
            updated_at = _parse_time(raw_updated, "updated_at_utc")
        except _Malformed as exc:
            diagnostics.append(_diag(f"{exc}; reset"))

    units: dict[str, UnitState] = {}
    for key, entry in units_raw.items():
        try:
            units[key] = _parse_unit(key, entry)
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
        "last_count": unit.last_count,
        "rose_last_tick": unit.rose_last_tick,
        "recent_rises": list(unit.recent_rises),
        "last_seen_at": _iso(unit.last_seen_at),
        "episode": None
        if episode is None
        else {
            "started_utc": _iso(episode.started_utc),
            "last_alert_utc": _iso(episode.last_alert_utc),
            "ticks_since_alert": episode.ticks_since_alert,
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
