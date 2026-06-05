"""6-phase reconciliation cycle orchestration (#520 / WP04).

Composes the WP01-WP04 modules into one tick: fetch → diff → classify → emit
→ update → 5b-deletion-cleanup → complete. State writes happen ONLY in phase 6
(complete); earlier phases work entirely in-memory.

Contract: kitty-specs/felix-vikunja-sync-project-layer-and-url-config-01KTCDZ7/
contracts/cycle-pipeline.md.
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
from scripts.sync.cleanup import append_task_deleted_event, prune_schedule_yaml
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
from scripts.sync.fetch import FetchedSnapshot, fetch_full_poll, vikunja_now_iso
from scripts.sync.guards import now_et_day, roll_g3_day_if_needed
from scripts.sync.send_whatsapp import send as default_send
from scripts.sync.state import (
    CONFLICT_EVENTS_FILENAME,
    FreshnessLayer,
    FreshnessPointer,
    LAST_TICK_FILENAME,
    LayerSummary,
    PerLayerSummary,
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

# ---------------------------------------------------------------------------
# Phase 5b path constants (repo-relative; resolved relative to this file)
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).parent.parent.parent
HABITS_HISTORY_PATH = _REPO_ROOT / "scripts" / "habits" / "state" / "habits-history.jsonl"
SCHEDULE_YAML_PATH = _REPO_ROOT / "scripts" / "habits" / "migrations" / "phase3-schedule.yaml"

# Kept for tests/callers that reference it by name; no longer drives fetch logic.
LAYER_STATUS_AND_TASK = "status_and_task"


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
    duration_ms: int = 0


# ---------------------------------------------------------------------------
# _make_empty_layer_summary — helper for failure paths
# ---------------------------------------------------------------------------


def _make_empty_layer_summary(ts: str, errors: tuple[str, ...] = ()) -> LayerSummary:
    """Return a LayerSummary with zero counts and the given errors on both layers."""
    layer = PerLayerSummary(
        polled_at_utc=ts,
        added=0,
        removed=0,
        updated=0,
        errors=errors,
    )
    return LayerSummary(task_layer=layer, project_layer=layer)


# ---------------------------------------------------------------------------
# run_cycle (the 6+1-phase pipeline)
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
        _read_or_fail_freshness(config.state_dir)   # validates bootstrap was run
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

    # --- Phase 1: fetch (full-poll) ---
    try:
        snapshot = fetch_full_poll(
            token=token,
            base_url=config.api_base_url,
            task_cache_nonempty=bool(task_cache.tasks),
            project_cache_nonempty=bool(project_cache.projects),
        )
    except OSError as e:
        error_message = str(e)
        # Determine which error token applies so we can populate layer_summary.
        if error_message.startswith("auth_failure:"):
            err_token = "auth_failure"
        elif error_message.startswith("vikunja_5xx:"):
            err_token = "vikunja_5xx"
        elif error_message.startswith("parse_error:"):
            err_token = "parse_error"
        elif error_message.startswith("empty_response_when_cache_nonzero:"):
            err_token = "empty_response_when_cache_nonzero"
        else:
            err_token = "vikunja_unreachable"
        return _record_failure(
            config=config,
            tick_id=tick_id,
            started_at_utc=started_at_utc,
            phase="fetch",
            cycle_error=f"step 1 (Vikunja fetch) failed: {error_message}",
            exit_code=1,
            duration_ms=_ms_since(start_perf),
            error_tokens=(err_token,),
        )

    # --- Phase 2: diff (3-way set-diff) ---
    (
        divergences,
        first_observation_task_ids,
        deleted_task_ids,
        project_events,
        layer_summary,
    ) = compute_divergences(
        snapshot=snapshot,
        task_cache=task_cache,
        project_cache=project_cache,
        ts_observed_utc=started_at_utc,
        private_project_ids=PRIVATE_PROJECT_IDS,
    )

    # --- Phase 3: classify ---
    task_lookup = {t["id"]: t for t in snapshot.tasks if isinstance(t.get("id"), int)}
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
        )

    # --- Phase 5: update (in-memory; persisted in phase 6) ---
    try:
        new_task_cache = _apply_cache_updates(
            task_cache=task_cache,
            snapshot=snapshot,
            first_observation_task_ids=first_observation_task_ids,
            deleted_task_ids=deleted_task_ids,
            ts_observed_utc=started_at_utc,
            private_project_ids=PRIVATE_PROJECT_IDS,
        )
        new_project_cache = _apply_project_updates(
            snapshot=snapshot,
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
        )

    # --- Phase 5b: deletion-cleanup (FR-003) ---
    if not config.dry_run:
        for task_id in sorted(deleted_task_ids):
            prior_entry = task_cache.tasks.get(str(task_id))
            prior_title = prior_entry.fields.get("title", "<unknown>") if prior_entry and prior_entry.fields else "<unknown>"
            try:
                append_task_deleted_event(
                    task_id=task_id,
                    title=prior_title,
                    detected_at_utc=started_at_utc,
                    path=HABITS_HISTORY_PATH,
                )
            except OSError as e:
                # Per FR-003: log the error, skip this task_id, continue with others.
                sys.stderr.write(
                    f"[sync cleanup] WARNING: append_task_deleted_event failed for "
                    f"task_id={task_id}: {e}\n"
                )
                try:
                    append_per_tick_error(
                        config.state_dir,
                        PerTickErrorRecord(
                            tick_id=tick_id,
                            started_at_utc=started_at_utc,
                            failed_at_utc=vikunja_now_iso(),
                            phase="cleanup_history_log",
                            cycle_error=f"append_task_deleted_event failed for task_id={task_id}: {e}",
                            layer_pointers_unchanged=False,
                        ),
                    )
                except OSError:
                    pass  # best-effort
                # Skip schedule.yaml prune for atomicity (history-log failed)
                continue

            try:
                prune_schedule_yaml(task_id, SCHEDULE_YAML_PATH)
            except (OSError, ValueError) as e:
                sys.stderr.write(
                    f"[sync cleanup] WARNING: prune_schedule_yaml failed for "
                    f"task_id={task_id}: {e}\n"
                )
                try:
                    append_per_tick_error(
                        config.state_dir,
                        PerTickErrorRecord(
                            tick_id=tick_id,
                            started_at_utc=started_at_utc,
                            failed_at_utc=vikunja_now_iso(),
                            phase="cleanup_schedule_yaml",
                            cycle_error=f"prune_schedule_yaml failed for task_id={task_id}: {e}",
                            layer_pointers_unchanged=False,
                        ),
                    )
                except OSError:
                    pass  # best-effort
                # Continue — cache removal still happens in Phase 6

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
            layer_summary=layer_summary,
            events_emitted=events_count,
            cycle_error=None,
            vikunja_version_seen=snapshot.vikunja_version,
        ),
    )

    return CycleResult(
        success=True,
        exit_code=0,
        tick_id=tick_id,
        cycle_error=None,
        events_emitted=events_count,
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
        snapshot = fetch_full_poll(
            token=token,
            base_url=config.api_base_url,
            task_cache_nonempty=False,   # bootstrap: cache is empty
            project_cache_nonempty=False,
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
    empty_task_cache = TaskCacheRecord(last_updated_utc=started_at_utc, tasks={})
    all_task_ids = {t["id"] for t in snapshot.tasks if isinstance(t.get("id"), int)}
    new_task_cache = _apply_cache_updates(
        task_cache=empty_task_cache,
        snapshot=snapshot,
        first_observation_task_ids=all_task_ids,
        deleted_task_ids=set(),
        ts_observed_utc=started_at_utc,
        private_project_ids=PRIVATE_PROJECT_IDS,
    )
    new_project_cache = _apply_project_updates(
        snapshot=snapshot,
        ts_observed_utc=started_at_utc,
    )

    et_day = now_et_day(now_utc)
    fresh_guard_state = roll_g3_day_if_needed(
        read_guard_state(config.state_dir),  # tolerates missing → default state
        et_day,
    )

    bootstrap_layer_summary = LayerSummary(
        task_layer=PerLayerSummary(
            polled_at_utc=snapshot.fetched_at_utc,
            added=len(new_task_cache.tasks),
            removed=0,
            updated=0,
            errors=(),
        ),
        project_layer=PerLayerSummary(
            polled_at_utc=snapshot.fetched_at_utc,
            added=len(new_project_cache.projects),
            removed=0,
            updated=0,
            errors=(),
        ),
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
            layer_summary=bootstrap_layer_summary,
            events_emitted={CLASS_AUTO_RESOLVED: 0, CLASS_UNSAFE: 0},
            cycle_error=None,
            vikunja_version_seen=snapshot.vikunja_version,
        ),
    )

    return CycleResult(
        success=True,
        exit_code=0,
        tick_id=tick_id,
        cycle_error=None,
        events_emitted={CLASS_AUTO_RESOLVED: 0, CLASS_UNSAFE: 0},
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


def _read_or_fail_freshness(state_dir: Path) -> None:
    from scripts.sync.state import read_freshness
    read_freshness(state_dir)


def _apply_cache_updates(
    *,
    task_cache: TaskCacheRecord,
    snapshot: FetchedSnapshot,
    first_observation_task_ids: set[int],
    deleted_task_ids: set[int],
    ts_observed_utc: str,
    private_project_ids: frozenset[int],
) -> TaskCacheRecord:
    """Apply set-diff outputs to the task cache.

    New tasks (first_observation_task_ids) get TaskCacheEntry records added.
    Deleted tasks (deleted_task_ids) get removed.
    Existing tasks (in_both) get their tracked fields updated from snapshot.
    Private tasks get tracked with empty fields (privacy boundary).
    """
    # Start from existing cache entries; deletions will be excluded at the end.
    new_tasks: dict[str, TaskCacheEntry] = {}

    # Build a quick lookup from the snapshot.
    snapshot_by_id: dict[int, dict] = {
        t["id"]: t for t in snapshot.tasks if isinstance(t.get("id"), int)
    }

    for task in snapshot.tasks:
        task_id = task.get("id")
        if not isinstance(task_id, int):
            continue
        # Skip deleted tasks (they won't be in the snapshot anyway, but guard defensively)
        if task_id in deleted_task_ids:
            continue

        is_private = task.get("project_id") in private_project_ids
        if is_private:
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

    # Preserve cache entries for tasks not in the snapshot AND not deleted.
    # (These shouldn't exist under full-poll semantics, but guard defensively.)
    for cache_key, cache_entry in task_cache.tasks.items():
        task_id = int(cache_key)
        if task_id not in deleted_task_ids and cache_key not in new_tasks:
            new_tasks[cache_key] = cache_entry

    return TaskCacheRecord(
        last_updated_utc=ts_observed_utc,
        tasks=new_tasks,
    )


def _apply_project_updates(
    *,
    snapshot: FetchedSnapshot,
    ts_observed_utc: str,
) -> ProjectCacheRecord:
    """Canonical-snapshot replacement of the project cache.

    Per data-model.md, the new project cache is the snapshot's projects
    directly — not a merge of cache and snapshot.
    """
    new_projects = {
        str(pid): ProjectCacheEntry(
            title=str(proj.get("title", "<unknown>")),
            is_archived=bool(proj.get("is_archived", False)),
        )
        for pid, proj in snapshot.projects.items()
    }
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
    error_tokens: tuple[str, ...] = (),
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
        duration_ms=duration_ms,
    )
