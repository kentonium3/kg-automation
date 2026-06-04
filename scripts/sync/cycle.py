"""6-phase reconciliation cycle orchestration (WP05 / T018).

Composes the WP01-WP04 modules into one tick: fetch → diff → classify → emit
→ update → complete. State writes happen ONLY in phase 6 (complete); earlier
phases work entirely in-memory.

Contract: kitty-specs/.../contracts/cycle-pipeline.md.
"""
from __future__ import annotations

import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.sync.classify import CLASS_AUTO_RESOLVED, CLASS_UNSAFE, classify
from scripts.sync.diff import (
    PRIVATE_PROJECT_IDS,
    TRACKED_TASK_FIELDS,
    compute_divergences,
)
from scripts.sync.emit import (
    SendCallable,
    emit_events,
    read_recent_events,
)
from scripts.sync.fetch import fetch_delta, vikunja_now_iso
from scripts.sync.guards import now_et_day, roll_g3_day_if_needed
from scripts.sync.send_whatsapp import send as default_send
from scripts.sync.state import (
    CONFLICT_EVENTS_FILENAME,
    FreshnessLayer,
    FreshnessPointer,
    LAST_TICK_FILENAME,
    LayerPointerSnapshot,
    PerTickErrorRecord,
    PerTickHealthRecord,
    ProjectCacheEntry,
    ProjectCacheRecord,
    TaskCacheEntry,
    TaskCacheRecord,
    append_per_tick_error,
    read_guard_state,
    read_project_cache,
    read_task_cache,
    write_freshness,
    write_guard_state,
    write_per_tick_health,
    write_project_cache,
    write_task_cache,
)


LAYER_STATUS_AND_TASK = "status_and_task"
EPOCH_ZERO = "0001-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# Config / result dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CycleConfig:
    """Resolved configuration for one cycle invocation."""

    state_dir: Path
    secrets_dir: Path
    api_base_url: str
    cadence_seconds: int
    whatsapp_recipient: str
    dry_run: bool


@dataclass(frozen=True)
class CycleResult:
    """Outcome of one cycle run."""

    success: bool
    exit_code: int                             # 0, 1, or 2
    tick_id: str
    cycle_error: str | None
    events_emitted: dict[str, int] = field(default_factory=dict)
    layer_pointers_before: dict[str, str] = field(default_factory=dict)
    layer_pointers_after: dict[str, str] = field(default_factory=dict)
    duration_ms: int = 0


# ---------------------------------------------------------------------------
# run_cycle (the 6-phase pipeline)
# ---------------------------------------------------------------------------


def run_cycle(
    config: CycleConfig,
    send_callable: SendCallable | None = None,
    now_utc: datetime | None = None,
) -> CycleResult:
    """Execute one reconciliation cycle.

    Returns CycleResult with exit_code = 0 (success), 1 (pre-emit failure;
    safe state — pointer unchanged), or 2 (emit-onward failure; events may
    have partial-committed and cache may be partially advanced).
    """
    if send_callable is None:
        send_callable = default_send
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    tick_id = _new_tick_id()
    started_at_utc = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    start_perf = time.perf_counter()

    # --- Phase 0: preamble ---
    try:
        token = _read_token(config.secrets_dir / "vikunja-api")
        freshness_before = _read_or_fail_freshness(config.state_dir)
        task_cache = read_task_cache(config.state_dir)
        project_cache = read_project_cache(config.state_dir)
        guard_state = read_guard_state(config.state_dir)
    except OSError as e:
        return _record_failure(
            config=config,
            tick_id=tick_id,
            started_at_utc=started_at_utc,
            phase="preamble",
            cycle_error=str(e),
            exit_code=1,
            duration_ms=_ms_since(start_perf),
        )

    pointer_before = freshness_before.layers.get(LAYER_STATUS_AND_TASK)
    since_utc = pointer_before.last_polled_utc if pointer_before else EPOCH_ZERO
    layer_pointers_before = {LAYER_STATUS_AND_TASK: since_utc}

    # --- Phase 1: fetch ---
    try:
        delta = fetch_delta(
            token=token,
            base_url=config.api_base_url,
            since_utc=since_utc,
            known_project_ids=_project_id_set(project_cache),
        )
    except OSError as e:
        return _record_failure(
            config=config,
            tick_id=tick_id,
            started_at_utc=started_at_utc,
            phase="fetch",
            cycle_error=f"step 1 (Vikunja fetch) failed: {e}",
            exit_code=1,
            duration_ms=_ms_since(start_perf),
            layer_pointers_before=layer_pointers_before,
        )

    # --- Phase 2: diff ---
    divergences, first_observation_ids = compute_divergences(
        delta=delta,
        task_cache=task_cache,
        ts_observed_utc=started_at_utc,
        private_project_ids=PRIVATE_PROJECT_IDS,
    )

    # --- Phase 3: classify ---
    task_lookup = {t["id"]: t for t in delta.tasks if isinstance(t.get("id"), int)}
    classified = []
    for cand in divergences:
        task = task_lookup.get(cand.vikunja_entity_id, {})
        classified.append(classify(cand, task))

    # Build counts (before guards may suppress some) for the health record.
    events_count = {CLASS_AUTO_RESOLVED: 0, CLASS_UNSAFE: 0}
    for c in classified:
        events_count[c.class_] = events_count.get(c.class_, 0) + 1

    # --- Phase 4: emit ---
    et_day = now_et_day(now_utc)
    rolled_guard_state = roll_g3_day_if_needed(guard_state, et_day)
    jsonl_path = config.state_dir / CONFLICT_EVENTS_FILENAME
    recent_events = read_recent_events(jsonl_path, now_utc)
    try:
        if config.dry_run:
            # Dry-run: skip all writes including JSONL append.
            committed_events = []
            updated_guard_state = rolled_guard_state
        else:
            committed_events, updated_guard_state = emit_events(
                classified_conflicts=classified,
                tick_id=tick_id,
                ts_observed_utc=started_at_utc,
                jsonl_path=jsonl_path,
                task_cache=task_cache,
                guard_state=rolled_guard_state,
                recent_events=recent_events,
                send_callable=send_callable,
                recipient=config.whatsapp_recipient,
                cycle_started_at=now_utc,
                now_et_day_str=et_day,
                private_project_ids=PRIVATE_PROJECT_IDS,
                task_lookup=task_lookup,
            )
    except OSError as e:
        return _record_failure(
            config=config,
            tick_id=tick_id,
            started_at_utc=started_at_utc,
            phase="emit",
            cycle_error=f"step 4 (emit) failed: {e}",
            exit_code=2,
            duration_ms=_ms_since(start_perf),
            layer_pointers_before=layer_pointers_before,
        )

    # --- Phase 5: update (in-memory; persisted in phase 6) ---
    try:
        new_task_cache = _apply_cache_updates(
            task_cache=task_cache,
            delta=delta,
            first_observation_ids=first_observation_ids,
            ts_observed_utc=started_at_utc,
            private_project_ids=PRIVATE_PROJECT_IDS,
        )
        new_project_cache = _apply_project_updates(
            project_cache=project_cache,
            delta=delta,
            ts_observed_utc=started_at_utc,
        )
    except Exception as e:  # pragma: no cover -- defensive; pure transforms shouldn't raise
        return _record_failure(
            config=config,
            tick_id=tick_id,
            started_at_utc=started_at_utc,
            phase="update",
            cycle_error=f"step 5 (update) failed: {e}",
            exit_code=2,
            duration_ms=_ms_since(start_perf),
            layer_pointers_before=layer_pointers_before,
        )

    # --- Phase 6: complete (atomic writes; freshness second-to-last) ---
    if config.dry_run:
        # Dry-run: skip ALL state writes.
        sys.stderr.write(
            f"[sync DRY-RUN] tick={tick_id} would_emit={events_count} "
            f"new_pointer={started_at_utc}\n"
        )
        return CycleResult(
            success=True,
            exit_code=0,
            tick_id=tick_id,
            cycle_error=None,
            events_emitted=events_count,
            layer_pointers_before=layer_pointers_before,
            layer_pointers_after={LAYER_STATUS_AND_TASK: started_at_utc},
            duration_ms=_ms_since(start_perf),
        )

    try:
        write_task_cache(config.state_dir, new_task_cache)
        write_project_cache(config.state_dir, new_project_cache)
        write_guard_state(config.state_dir, updated_guard_state)
        write_freshness(
            config.state_dir,
            FreshnessPointer(
                last_updated_utc=started_at_utc,
                layers={
                    LAYER_STATUS_AND_TASK: FreshnessLayer(
                        last_polled_utc=started_at_utc
                    )
                },
            ),
        )
    except OSError as e:
        return _record_failure(
            config=config,
            tick_id=tick_id,
            started_at_utc=started_at_utc,
            phase="complete",
            cycle_error=f"step 6 (complete) failed: {e}",
            exit_code=2,
            duration_ms=_ms_since(start_perf),
            layer_pointers_before=layer_pointers_before,
        )

    completed_at_utc = vikunja_now_iso()
    duration_ms = _ms_since(start_perf)
    write_per_tick_health(
        config.state_dir,
        PerTickHealthRecord(
            tick_id=tick_id,
            started_at_utc=started_at_utc,
            completed_at_utc=completed_at_utc,
            duration_ms=duration_ms,
            cadence_seconds=config.cadence_seconds,
            layer_pointers={
                LAYER_STATUS_AND_TASK: LayerPointerSnapshot(
                    before=since_utc, after=started_at_utc
                ),
            },
            events_emitted=events_count,
            cycle_error=None,
            vikunja_version_seen=delta.vikunja_version,
        ),
    )

    return CycleResult(
        success=True,
        exit_code=0,
        tick_id=tick_id,
        cycle_error=None,
        events_emitted=events_count,
        layer_pointers_before=layer_pointers_before,
        layer_pointers_after={LAYER_STATUS_AND_TASK: started_at_utc},
        duration_ms=duration_ms,
    )


# ---------------------------------------------------------------------------
# run_bootstrap (first-run mode)
# ---------------------------------------------------------------------------


def run_bootstrap(
    config: CycleConfig,
    now_utc: datetime | None = None,
) -> CycleResult:
    """First-run state population. Reads ALL Vikunja state and seeds the cache.

    Does NOT classify or emit. The conflict-events.jsonl file is NOT created.
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    tick_id = _new_tick_id()
    started_at_utc = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    start_perf = time.perf_counter()

    try:
        token = _read_token(config.secrets_dir / "vikunja-api")
    except OSError as e:
        return _record_failure(
            config=config,
            tick_id=tick_id,
            started_at_utc=started_at_utc,
            phase="bootstrap-preamble",
            cycle_error=str(e),
            exit_code=1,
            duration_ms=_ms_since(start_perf),
        )

    try:
        delta = fetch_delta(
            token=token,
            base_url=config.api_base_url,
            since_utc=EPOCH_ZERO,
            known_project_ids=set(),
        )
    except OSError as e:
        return _record_failure(
            config=config,
            tick_id=tick_id,
            started_at_utc=started_at_utc,
            phase="bootstrap-fetch",
            cycle_error=f"step 1 (bootstrap fetch) failed: {e}",
            exit_code=1,
            duration_ms=_ms_since(start_perf),
        )

    # Build the cache from scratch (all tasks are first observations).
    new_task_cache = _apply_cache_updates(
        task_cache=TaskCacheRecord(last_updated_utc=started_at_utc, tasks={}),
        delta=delta,
        first_observation_ids=[t["id"] for t in delta.tasks if isinstance(t.get("id"), int)],
        ts_observed_utc=started_at_utc,
        private_project_ids=PRIVATE_PROJECT_IDS,
    )
    new_project_cache = _apply_project_updates(
        project_cache=ProjectCacheRecord(last_refreshed_utc=started_at_utc, projects={}),
        delta=delta,
        ts_observed_utc=started_at_utc,
    )

    et_day = now_et_day(now_utc)
    fresh_guard_state = roll_g3_day_if_needed(
        read_guard_state(config.state_dir),  # tolerates missing → default state
        et_day,
    )

    if config.dry_run:
        sys.stderr.write(
            f"[sync DRY-RUN bootstrap] tick={tick_id} would_seed={len(new_task_cache.tasks)} tasks\n"
        )
        return CycleResult(
            success=True,
            exit_code=0,
            tick_id=tick_id,
            cycle_error=None,
            events_emitted={CLASS_AUTO_RESOLVED: 0, CLASS_UNSAFE: 0},
            layer_pointers_before={LAYER_STATUS_AND_TASK: EPOCH_ZERO},
            layer_pointers_after={LAYER_STATUS_AND_TASK: started_at_utc},
            duration_ms=_ms_since(start_perf),
        )

    try:
        write_task_cache(config.state_dir, new_task_cache)
        write_project_cache(config.state_dir, new_project_cache)
        write_guard_state(config.state_dir, fresh_guard_state)
        write_freshness(
            config.state_dir,
            FreshnessPointer(
                last_updated_utc=started_at_utc,
                layers={
                    LAYER_STATUS_AND_TASK: FreshnessLayer(
                        last_polled_utc=started_at_utc
                    )
                },
            ),
        )
    except OSError as e:
        return _record_failure(
            config=config,
            tick_id=tick_id,
            started_at_utc=started_at_utc,
            phase="bootstrap-complete",
            cycle_error=f"bootstrap state write failed: {e}",
            exit_code=2,
            duration_ms=_ms_since(start_perf),
        )

    duration_ms = _ms_since(start_perf)
    write_per_tick_health(
        config.state_dir,
        PerTickHealthRecord(
            tick_id=tick_id,
            started_at_utc=started_at_utc,
            completed_at_utc=vikunja_now_iso(),
            duration_ms=duration_ms,
            cadence_seconds=config.cadence_seconds,
            layer_pointers={
                LAYER_STATUS_AND_TASK: LayerPointerSnapshot(
                    before=EPOCH_ZERO, after=started_at_utc
                ),
            },
            events_emitted={CLASS_AUTO_RESOLVED: 0, CLASS_UNSAFE: 0},
            cycle_error=None,
            vikunja_version_seen=delta.vikunja_version,
        ),
    )

    return CycleResult(
        success=True,
        exit_code=0,
        tick_id=tick_id,
        cycle_error=None,
        events_emitted={CLASS_AUTO_RESOLVED: 0, CLASS_UNSAFE: 0},
        layer_pointers_before={LAYER_STATUS_AND_TASK: EPOCH_ZERO},
        layer_pointers_after={LAYER_STATUS_AND_TASK: started_at_utc},
        duration_ms=duration_ms,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _new_tick_id() -> str:
    """Generate a tick identifier. Uses uuid4 hex (sufficient for our needs)."""
    return uuid.uuid4().hex[:26].upper()


def _ms_since(perf_start: float) -> int:
    return int((time.perf_counter() - perf_start) * 1000)


def _read_token(path: Path) -> str:
    """Read the Vikunja bearer token from disk."""
    try:
        content = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError as e:
        raise OSError(f"Vikunja token file not found: {path}") from e
    if not content:
        raise OSError(f"Vikunja token file is empty: {path}")
    return content


def _read_or_fail_freshness(state_dir: Path) -> FreshnessPointer:
    from scripts.sync.state import read_freshness
    return read_freshness(state_dir)


def _project_id_set(pc: ProjectCacheRecord) -> set[int]:
    out: set[int] = set()
    for key in pc.projects.keys():
        try:
            out.add(int(key))
        except (TypeError, ValueError):
            continue
    return out


def _apply_cache_updates(
    *,
    task_cache: TaskCacheRecord,
    delta,
    first_observation_ids: list[int],
    ts_observed_utc: str,
    private_project_ids: frozenset[int],
) -> TaskCacheRecord:
    """Replace cached fields with Vikunja values + update felix_last_observed_at."""
    new_tasks = dict(task_cache.tasks)
    first_obs_set = set(first_observation_ids)
    for task in delta.tasks:
        task_id = task.get("id")
        if not isinstance(task_id, int):
            continue
        is_private = task.get("project_id") in private_project_ids
        if is_private:
            # Private boundary: track only the IDs and timestamps. Empty fields.
            new_tasks[str(task_id)] = TaskCacheEntry(
                vikunja_task_id=task_id,
                fields={},
                vikunja_updated_at=str(task.get("updated") or ""),
                felix_last_observed_at=ts_observed_utc,
            )
            continue
        fields_subset: dict[str, Any] = {}
        for f_name in TRACKED_TASK_FIELDS:
            fields_subset[f_name] = task.get(f_name)
        new_tasks[str(task_id)] = TaskCacheEntry(
            vikunja_task_id=task_id,
            fields=fields_subset,
            vikunja_updated_at=str(task.get("updated") or ""),
            felix_last_observed_at=ts_observed_utc,
        )
    return TaskCacheRecord(
        last_updated_utc=ts_observed_utc,
        tasks=new_tasks,
    )


def _apply_project_updates(
    *,
    project_cache: ProjectCacheRecord,
    delta,
    ts_observed_utc: str,
) -> ProjectCacheRecord:
    """Merge fetched projects into the project cache."""
    new_projects = dict(project_cache.projects)
    for pid, proj in delta.projects.items():
        new_projects[str(pid)] = ProjectCacheEntry(
            title=str(proj.get("title", "<unknown>")),
            is_archived=bool(proj.get("is_archived", False)),
        )
    return ProjectCacheRecord(
        last_refreshed_utc=ts_observed_utc,
        projects=new_projects,
    )


def _record_failure(
    *,
    config: CycleConfig,
    tick_id: str,
    started_at_utc: str,
    phase: str,
    cycle_error: str,
    exit_code: int,
    duration_ms: int,
    layer_pointers_before: dict[str, str] | None = None,
) -> CycleResult:
    """Write the failure to last-tick.errors.jsonl and return a failure CycleResult."""
    pointers_unchanged = exit_code == 1
    failed_at_utc = vikunja_now_iso()
    if not config.dry_run:
        try:
            append_per_tick_error(
                config.state_dir,
                PerTickErrorRecord(
                    tick_id=tick_id,
                    started_at_utc=started_at_utc,
                    failed_at_utc=failed_at_utc,
                    phase=phase,
                    cycle_error=cycle_error,
                    layer_pointers_unchanged=pointers_unchanged,
                ),
            )
        except OSError:
            # If even the error record fails, fall through; the CycleResult still
            # carries the error for the CLI to surface.
            sys.stderr.write(
                f"[sync] WARNING: could not append to last-tick.errors.jsonl: {cycle_error}\n"
            )
    sys.stderr.write(f"[sync] phase={phase} status=error reason={cycle_error!r}\n")
    return CycleResult(
        success=False,
        exit_code=exit_code,
        tick_id=tick_id,
        cycle_error=cycle_error,
        events_emitted={},
        layer_pointers_before=layer_pointers_before or {},
        layer_pointers_after={},
        duration_ms=duration_ms,
    )
