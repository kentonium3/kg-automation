"""On-disk state I/O for the Felix-Vikunja reconciliation driver.

Atomic JSON read/write helpers + canonical reader/writer functions for every
persistent state file under ``/data/services/openclaw/state/sync/``. See
``kitty-specs/felix-vikunja-sync-reconciliation-driver-01KTA1J3/contracts/state-directory.md``
for the layout and ``data-model.md`` for the entity schemas.

This module is pure I/O. No business logic. No HTTP. No subprocess.

Pattern conventions:
- All overwriting writes use the atomic-replace pattern (write ``.tmp`` →
  ``fsync`` → ``os.replace``) mirroring ``scripts/habits/sweeper.py``.
- Append-only writes (JSONL) are a single ``write`` + ``flush`` per row;
  POSIX guarantees per-line atomicity for short writes.
- Every state file carries a ``schema_version`` field; readers reject unknown
  versions with a clear ``OSError`` so the operator can recover.
- Missing-file semantics differ per entity (documented per function).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 1

STATE_DIR_DEFAULT = Path("/data/services/openclaw/state/sync")
SECRETS_DIR_DEFAULT = Path("/data/services/openclaw/secrets")

# State file names (the directory layout contract).
FRESHNESS_FILENAME = "freshness.json"
TASK_CACHE_FILENAME = "task-cache.json"
PROJECT_CACHE_FILENAME = "project-cache.json"
GUARD_STATE_FILENAME = "guard-state.json"
CONFLICT_EVENTS_FILENAME = "conflict-events.jsonl"
LAST_TICK_FILENAME = "last-tick.json"
LAST_TICK_ERRORS_FILENAME = "last-tick.errors.jsonl"


# ---------------------------------------------------------------------------
# Entity schemas (dataclasses)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FreshnessLayer:
    """Per-layer freshness pointer value."""

    last_polled_utc: str


@dataclass(frozen=True)
class FreshnessPointer:
    """Driver's per-layer pointer used as the ``updated_since`` parameter."""

    last_updated_utc: str
    layers: dict[str, FreshnessLayer]
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True)
class TaskCacheEntry:
    """One Vikunja task as the driver expects to see it."""

    vikunja_task_id: int
    fields: dict[str, Any]
    vikunja_updated_at: str
    felix_last_observed_at: str


@dataclass(frozen=True)
class TaskCacheRecord:
    """Felix's local view of all tracked Vikunja tasks."""

    last_updated_utc: str
    tasks: dict[str, TaskCacheEntry]
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True)
class ProjectCacheEntry:
    """Lightweight Vikunja project metadata."""

    title: str
    is_archived: bool


@dataclass(frozen=True)
class ProjectCacheRecord:
    """Felix's local view of all touched Vikunja projects."""

    last_refreshed_utc: str
    projects: dict[str, ProjectCacheEntry]
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True)
class G3DailyCap:
    """The G-3 daily-cap state for unsafe-class WhatsApp delivery."""

    calendar_day_et: str
    unsafe_pings_sent_today: int
    cap: int


@dataclass(frozen=True)
class GuardState:
    """Persistent state for the three delivery guards."""

    g3_daily_cap: G3DailyCap
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True)
class LayerPointerSnapshot:
    """Per-layer pointer values before/after a cycle."""

    before: str
    after: str


@dataclass(frozen=True)
class PerTickHealthRecord:
    """The driver's self-report of the most recent successful cycle."""

    tick_id: str
    started_at_utc: str
    completed_at_utc: str
    duration_ms: int
    cadence_seconds: int
    layer_pointers: dict[str, LayerPointerSnapshot]
    events_emitted: dict[str, int]
    cycle_error: str | None
    vikunja_version_seen: str | None
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True)
class PerTickErrorRecord:
    """One failed-cycle record appended to ``last-tick.errors.jsonl``."""

    tick_id: str
    started_at_utc: str
    failed_at_utc: str
    phase: str
    cycle_error: str
    layer_pointers_unchanged: bool
    schema_version: int = SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Atomic I/O primitives
# ---------------------------------------------------------------------------


def atomic_write_json(path: Path, data: dict) -> None:
    """Atomically write ``data`` as JSON to ``path``.

    Writes to ``<path>.tmp`` first, ``fsync``s, then ``os.replace``s onto the
    target. Mirrors ``scripts/habits/sweeper.py:_atomic_write_json``. The
    target file is either the previous version or the new version; never
    partial under POSIX semantics.
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, sort_keys=True, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def append_jsonl(path: Path, record: dict) -> None:
    """Append one JSON record + newline to ``path``.

    Per-line atomicity is guaranteed by POSIX for ``write`` calls under a few
    KB; conflict-event rows are well under that threshold.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, sort_keys=True) + "\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)
        f.flush()


# ---------------------------------------------------------------------------
# Schema-version guard
# ---------------------------------------------------------------------------


def _require_schema_version(data: dict, path: Path) -> None:
    """Raise OSError if ``data["schema_version"]`` is not SCHEMA_VERSION."""
    version = data.get("schema_version")
    if version != SCHEMA_VERSION:
        raise OSError(
            f"{path}: schema_version mismatch (got {version!r}, "
            f"expected {SCHEMA_VERSION}). Operator recovery: delete the "
            f"file and re-run `python3 -m scripts.sync.driver --bootstrap`."
        )


def _read_json(path: Path) -> dict:
    """Read JSON from ``path``. Raises FileNotFoundError if missing."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# FreshnessPointer
# ---------------------------------------------------------------------------


def read_freshness(state_dir: Path) -> FreshnessPointer:
    """Read the freshness pointer.

    Missing file is treated as an operator error (bootstrap not yet run).
    Raises OSError with explicit recovery guidance.
    """
    path = state_dir / FRESHNESS_FILENAME
    try:
        data = _read_json(path)
    except FileNotFoundError as e:
        raise OSError(
            f"{path} not found — run "
            f"`python3 -m scripts.sync.driver --bootstrap` first."
        ) from e
    _require_schema_version(data, path)
    layers = {
        name: FreshnessLayer(last_polled_utc=layer["last_polled_utc"])
        for name, layer in data.get("layers", {}).items()
    }
    return FreshnessPointer(
        last_updated_utc=data["last_updated_utc"],
        layers=layers,
    )


def write_freshness(state_dir: Path, fp: FreshnessPointer) -> None:
    """Write the freshness pointer (atomic overwrite)."""
    path = state_dir / FRESHNESS_FILENAME
    data = {
        "schema_version": fp.schema_version,
        "last_updated_utc": fp.last_updated_utc,
        "layers": {
            name: {"last_polled_utc": layer.last_polled_utc}
            for name, layer in fp.layers.items()
        },
    }
    atomic_write_json(path, data)


# ---------------------------------------------------------------------------
# TaskCacheRecord
# ---------------------------------------------------------------------------


_EMPTY_TASK_CACHE = TaskCacheRecord(
    last_updated_utc="0001-01-01T00:00:00Z",
    tasks={},
)


def read_task_cache(state_dir: Path) -> TaskCacheRecord:
    """Read the task cache.

    Missing file returns an empty-state default. Schema-version mismatch
    raises OSError.
    """
    path = state_dir / TASK_CACHE_FILENAME
    try:
        data = _read_json(path)
    except FileNotFoundError:
        return _EMPTY_TASK_CACHE
    _require_schema_version(data, path)
    tasks = {
        key: TaskCacheEntry(
            vikunja_task_id=entry["vikunja_task_id"],
            fields=entry.get("fields", {}),
            vikunja_updated_at=entry["vikunja_updated_at"],
            felix_last_observed_at=entry["felix_last_observed_at"],
        )
        for key, entry in data.get("tasks", {}).items()
    }
    return TaskCacheRecord(
        last_updated_utc=data["last_updated_utc"],
        tasks=tasks,
    )


def write_task_cache(state_dir: Path, tc: TaskCacheRecord) -> None:
    """Write the task cache (atomic overwrite)."""
    path = state_dir / TASK_CACHE_FILENAME
    data = {
        "schema_version": tc.schema_version,
        "last_updated_utc": tc.last_updated_utc,
        "tasks": {
            key: {
                "vikunja_task_id": entry.vikunja_task_id,
                "fields": entry.fields,
                "vikunja_updated_at": entry.vikunja_updated_at,
                "felix_last_observed_at": entry.felix_last_observed_at,
            }
            for key, entry in tc.tasks.items()
        },
    }
    atomic_write_json(path, data)


# ---------------------------------------------------------------------------
# ProjectCacheRecord
# ---------------------------------------------------------------------------


_EMPTY_PROJECT_CACHE = ProjectCacheRecord(
    last_refreshed_utc="0001-01-01T00:00:00Z",
    projects={},
)


def read_project_cache(state_dir: Path) -> ProjectCacheRecord:
    """Read the project cache.

    Missing file returns an empty-state default.
    """
    path = state_dir / PROJECT_CACHE_FILENAME
    try:
        data = _read_json(path)
    except FileNotFoundError:
        return _EMPTY_PROJECT_CACHE
    _require_schema_version(data, path)
    projects = {
        key: ProjectCacheEntry(
            title=entry["title"],
            is_archived=entry["is_archived"],
        )
        for key, entry in data.get("projects", {}).items()
    }
    return ProjectCacheRecord(
        last_refreshed_utc=data["last_refreshed_utc"],
        projects=projects,
    )


def write_project_cache(state_dir: Path, pc: ProjectCacheRecord) -> None:
    """Write the project cache (atomic overwrite)."""
    path = state_dir / PROJECT_CACHE_FILENAME
    data = {
        "schema_version": pc.schema_version,
        "last_refreshed_utc": pc.last_refreshed_utc,
        "projects": {
            key: {"title": entry.title, "is_archived": entry.is_archived}
            for key, entry in pc.projects.items()
        },
    }
    atomic_write_json(path, data)


# ---------------------------------------------------------------------------
# GuardState
# ---------------------------------------------------------------------------


_EMPTY_GUARD_STATE = GuardState(
    g3_daily_cap=G3DailyCap(
        calendar_day_et="0001-01-01",
        unsafe_pings_sent_today=0,
        cap=5,
    ),
)


def read_guard_state(state_dir: Path) -> GuardState:
    """Read the guard state.

    Missing file returns an empty-state default with cap=5.
    """
    path = state_dir / GUARD_STATE_FILENAME
    try:
        data = _read_json(path)
    except FileNotFoundError:
        return _EMPTY_GUARD_STATE
    _require_schema_version(data, path)
    cap_data = data["g3_daily_cap"]
    return GuardState(
        g3_daily_cap=G3DailyCap(
            calendar_day_et=cap_data["calendar_day_et"],
            unsafe_pings_sent_today=cap_data["unsafe_pings_sent_today"],
            cap=cap_data["cap"],
        ),
    )


def write_guard_state(state_dir: Path, gs: GuardState) -> None:
    """Write the guard state (atomic overwrite)."""
    path = state_dir / GUARD_STATE_FILENAME
    data = {
        "schema_version": gs.schema_version,
        "g3_daily_cap": {
            "calendar_day_et": gs.g3_daily_cap.calendar_day_et,
            "unsafe_pings_sent_today": gs.g3_daily_cap.unsafe_pings_sent_today,
            "cap": gs.g3_daily_cap.cap,
        },
    }
    atomic_write_json(path, data)


# ---------------------------------------------------------------------------
# Per-tick health record (success path) + error stream
# ---------------------------------------------------------------------------


def write_per_tick_health(state_dir: Path, record: PerTickHealthRecord) -> None:
    """Write the success-path per-tick health record (atomic overwrite)."""
    path = state_dir / LAST_TICK_FILENAME
    data = {
        "schema_version": record.schema_version,
        "tick_id": record.tick_id,
        "started_at_utc": record.started_at_utc,
        "completed_at_utc": record.completed_at_utc,
        "duration_ms": record.duration_ms,
        "cadence_seconds": record.cadence_seconds,
        "layer_pointers": {
            name: {"before": snap.before, "after": snap.after}
            for name, snap in record.layer_pointers.items()
        },
        "events_emitted": dict(record.events_emitted),
        "cycle_error": record.cycle_error,
        "vikunja_version_seen": record.vikunja_version_seen,
    }
    atomic_write_json(path, data)


def append_per_tick_error(state_dir: Path, record: PerTickErrorRecord) -> None:
    """Append a failed-cycle record to ``last-tick.errors.jsonl``."""
    path = state_dir / LAST_TICK_ERRORS_FILENAME
    data = {
        "schema_version": record.schema_version,
        "tick_id": record.tick_id,
        "started_at_utc": record.started_at_utc,
        "failed_at_utc": record.failed_at_utc,
        "phase": record.phase,
        "cycle_error": record.cycle_error,
        "layer_pointers_unchanged": record.layer_pointers_unchanged,
    }
    append_jsonl(path, data)
