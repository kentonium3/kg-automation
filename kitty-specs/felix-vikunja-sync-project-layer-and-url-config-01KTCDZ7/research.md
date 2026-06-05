# Research Log: Felix-Vikunja Sync — Project Layer and URL Config

**Phase**: 0 (planning research, implementation-level decisions)
**Spec**: [spec.md](./spec.md)
**Plan**: [plan.md](./plan.md)
**Date**: 2026-06-05

The bulk of architectural research was done during the spec phase (operator-driven discovery). This log captures the implementation-level decisions surfaced during planning interrogation.

---

## R-001: Replace `fetch_delta` with `fetch_full_poll`

**Decision**: Replace `scripts/sync/fetch.py:fetch_delta(...)` with a new `fetch_full_poll(...)` that performs two HTTP calls per cycle: `GET /tasks/all` (no `updated_since`) and `GET /projects`.

**Rationale**:
- Per spec FR-001 + FR-004, both layers use full polling.
- The current `fetch_delta` does just-in-time per-project fetches; this disappears under full-poll (the project layer is its own call).
- Single function signature: `fetch_full_poll(token, base_url) → FetchedSnapshot`. No `since_utc` or `known_project_ids` parameters (both are no-ops under full-poll).

**Alternatives considered**:
- Keep `fetch_delta` and add `fetch_projects` separately. Rejected: maintains two fetch pathways and leaves the incremental code alive.
- Lazy `GET /projects` (only if needed). Rejected: defeats FR-004's audit/discovery purpose.

---

## R-002: `FetchedSnapshot` replaces `FetchedDelta`

**Decision**: Introduce a new dataclass `FetchedSnapshot` in `scripts/sync/fetch.py`:

```python
@dataclass(frozen=True)
class FetchedSnapshot:
    tasks: tuple[dict, ...]              # full task list, all fields per Vikunja API
    projects: dict[int, dict]            # full project list keyed by project_id
    vikunja_version: str | None
    fetched_at_utc: str
```

**Rationale**:
- `FetchedSnapshot` semantically describes the full-state snapshot returned by full polling.
- Renaming makes it clear the dataclass is no longer a delta; downstream consumers (diff, classify) must update their expectations.
- `vikunja_version` and `fetched_at_utc` carry over from `FetchedDelta`.

**Alternatives considered**:
- Keep `FetchedDelta` name. Rejected: misleading semantics; the type IS the contract.

---

## R-003: `compute_divergences` operates on (snapshot, cache) using 3-way set diff

**Decision**: Replace `scripts/sync/diff.py:compute_divergences(...)` to compute three disjoint sets and emit `DivergenceCandidate` records for the `in_both` set where fields differ.

**Signature evolution**:
```python
def compute_divergences(
    snapshot: FetchedSnapshot,
    task_cache: TaskCacheRecord,
    project_cache: ProjectCacheRecord,
    ts_observed_utc: str,
    private_project_ids: frozenset[int] = PRIVATE_PROJECT_IDS,
) -> tuple[
    list[DivergenceCandidate],     # task changes
    set[int],                       # first_observation_task_ids (in_vikunja_only)
    set[int],                       # deleted_task_ids (in_cache_only)
    list[ProjectDiffEvent],         # project changes (added/removed/renamed/archived/unarchived)
    LayerSummary,                   # aggregate counts per layer
]
```

**Rationale**:
- Tasks: existing `DivergenceCandidate` interface is preserved for content changes; new outputs (`first_observation_task_ids`, `deleted_task_ids`) signal additions and deletions explicitly.
- Projects: separate event stream because the project layer doesn't go through the conflict-event pipeline (FR-005 — audit/discovery only).
- LayerSummary computed in one place (the diff function) keeps the aggregate counts honest.

**Alternatives considered**:
- Reuse `DivergenceCandidate` for project events. Rejected: it carries task-specific fields (`vikunja_entity_id` is task-keyed); reusing would muddy the type.

---

## R-004: Deletion-cleanup runs in a new Phase 5b within `cycle.py`

**Decision**: Add a Phase 5b "deletion-cleanup" step between Phase 5 (update) and Phase 6 (complete). It runs for each `task_id` in the `in_cache_only` set, in the order specified by FR-003:

1. Append `task_deleted` event to `scripts/habits/state/habits-history.jsonl` (append-only, atomic)
2. Prune the entry for that `task_id` from `scripts/habits/migrations/phase3-schedule.yaml` (if present)
3. Remove the task record from `task-cache.json` (handled by the existing Phase 6 atomic write — pass the filtered TaskCacheRecord to `write_task_cache`)

**Rationale**:
- Ordering matters for failure-recovery: history-log first means a partial cleanup leaves a benign over-counted state (history says deleted; cache and schedule.yaml still reference it; next cycle's full poll re-triggers cleanup).
- Schedule.yaml prune is YAML round-trip (read → mutate → write). The YAML library must preserve comments and ordering; use `ruamel.yaml` if available, fallback to stdlib `yaml` (recorded as a sub-decision in R-006).
- The sync cache removal is a single dict deletion before `write_task_cache`; no separate operation needed.

**Alternatives considered**:
- Run cleanup in Phase 5 (update). Rejected: Phase 5 mutates only in-memory state; the YAML and JSONL writes are side effects that must be ordered relative to the atomic cache commit in Phase 6.
- Single-transaction cleanup with rollback. Rejected: schedule.yaml and habits-history.jsonl have different write semantics; transactional rollback is over-engineering for this scale.

---

## R-005: `LayerSummary` replaces `LayerPointerSnapshot` in `last-tick.json`

**Decision**: Deprecate `scripts/sync/state.py:LayerPointerSnapshot` and `last-tick.json`'s `layer_pointers` field. Replace with `LayerSummary`:

```python
@dataclass(frozen=True)
class PerLayerSummary:
    polled_at_utc: str
    added: int
    removed: int
    updated: int            # tasks: fields changed; projects: renamed/archived/unarchived
    errors: tuple[str, ...] # structured error tokens

@dataclass(frozen=True)
class LayerSummary:
    task_layer: PerLayerSummary
    project_layer: PerLayerSummary
```

**Rationale**:
- `LayerPointerSnapshot`'s `before`/`after` timestamps are meaningful only under incremental polling.
- `LayerSummary` carries the information operators actually want: what happened this cycle, per layer.
- Errors are recorded per-layer so a partial-cycle (one layer failed, the other succeeded) is observable.

**Alternatives considered**:
- Keep `layer_pointers` as a deprecated field for one release. Rejected: per spec C-003, the schema is replaced cleanly; no hybrid.
- Use a flat dict instead of dataclasses. Rejected: existing state.py uses dataclasses uniformly; consistency wins.

---

## R-006: YAML library choice for schedule.yaml round-trip

**Decision**: Use `ruamel.yaml` for `phase3-schedule.yaml` round-trip if available; fall back to PyYAML if not.

**Rationale**:
- `phase3-schedule.yaml` contains comments and operator-readable ordering that PyYAML's dump function destroys.
- `ruamel.yaml`'s `YAML(typ="rt")` preserves comments and ordering.
- Felix's runtime already uses `ruamel.yaml` via the habits subsystem (verified by grep in pre-planning).
- Fallback to PyYAML is acceptable for testing if `ruamel` isn't installed in a test environment (the test fixture can use a comment-free YAML stub).

**Alternatives considered**:
- Hand-roll YAML editing as text manipulation. Rejected: brittle; the YAML structure can vary.
- Require `ruamel.yaml` strictly. Rejected: adds a hard dependency for a soft requirement; pyyaml is acceptable for tests.

**Verification step**: planning verified `ruamel.yaml` is in the habits codebase via `grep -rn "ruamel" scripts/` — need to confirm during WP01 design which YAML helper is canonical for this codebase.

---

## R-007: URL config helper module location and API

**Decision**: New module `scripts/common/vikunja_config.py`:

```python
def get_vikunja_base_url() -> str:
    """Return the canonical Vikunja API base URL.

    Resolution order:
    1. VIKUNJA_BASE_URL environment variable, if set and non-empty
    2. Contents of /data/services/openclaw/config/vikunja-base-url.txt, stripped of whitespace

    Raises:
        ConfigError: if neither source is available, with a structured error message
            indicating both expected locations.
    """
```

**Rationale**:
- Single function, single responsibility. Touchpoints add one line: `BASE_URL = get_vikunja_base_url()`.
- Env var first allows test fixtures to monkeypatch via env without filesystem touches.
- File fallback is the production source of truth.
- Module placement in `scripts/common/` matches `sync_cache.py`'s pattern from #519.

**Alternatives considered**:
- Place helper in `scripts/sync/` (driver-local). Rejected: touchpoints in other directories need it; `scripts/common/` is the cross-cutting home.
- File first, env var fallback. Rejected: less convenient for testing.
- Cache the URL on first read. Considered but rejected: at one read per script invocation (not per HTTP call), the optimization is invisible.

---

## R-008: Test rewrite scope — what gets rewritten vs preserved

**Decision** (per operator answer 2026-06-05):

**Rewritten in place**:
- `tests/sync/test_fetch.py` — assert `fetch_full_poll` semantics; drop all `updated_since` cases
- `tests/sync/test_diff.py` — assert 3-way set diff outputs (`in_vikunja_only`, `in_cache_only`, `in_both`); drop delta-apply assertions
- `tests/sync/test_state.py` — add `LayerSummary` tests; remove `LayerPointerSnapshot` tests

**Modified (interface stable, internals re-asserted)**:
- `tests/sync/test_cycle_*.py` — integration tests at the cycle boundary stay as regression guards. The output assertions (cache contents, JSONL events, WhatsApp dispatch) are unchanged; only the input fixtures change from `FetchedDelta` mocks to `FetchedSnapshot` mocks.

**Unchanged**:
- `tests/common/test_sync_cache.py` — NFR-004 cache-read contract test stays.
- `tests/common/conftest.py` — mock fixtures from #519 are regression guards.
- `tests/conftest.py` — urlopen guard from #519 stays.
- `tests/sync/test_classify.py`, `test_emit.py`, `test_guards.py` — these phases don't change interface.

**Net diff size estimate**: ~800 lines deleted, ~900 lines added in `tests/sync/`; ~50 lines added in `tests/test_vikunja_config.py`. Most changes are localized to fetch+diff+state.

---

## R-009: Cycle ordering when both layers fail

**Decision**: If both `GET /tasks/all` and `GET /projects` fail in the same cycle, record both errors in `LayerSummary` and abort cleanly (no cache mutation). If only one fails, also abort the entire cycle (no partial cache commit per the atomic-cycle guarantee from #518).

**Rationale**:
- Atomic-cycle guarantee from #518 must hold under the new architecture.
- Partial commits leave `task-cache.json` and `project-cache.json` in inconsistent states for downstream consumers (touchpoints that use `is_cache_healthy()` per #519).
- LayerSummary captures both errors so the operator sees the full failure state.

**Alternatives considered**:
- Commit the successful layer's update, leave the failing layer untouched. Rejected: violates atomic-cycle guarantee.
- Retry the failed layer within the same cycle. Rejected: complicates timing; next cycle (5 min) is the retry.

---

## R-010: Deployment plan after merge

**Decision**: After merge, deploy by `git pull origin main` on office2 (same pattern as #518/#519). Create the URL config file as part of the deploy step. No soak window; the 5-min cycle is the smoke test — within one cycle the new driver fully replaces the old. Rollback is `git reset --hard <previous-merge>` + `systemctl --user restart felix-vikunja-sync.timer`.

**Rationale**:
- The change is Tier 3 (logic/workflow): no service unit changes, no schema migration on backing stores, no credential changes.
- The 5-min cycle natural cadence provides immediate operator feedback (next morning check-in at 07:05 ET ratifies the cache-read contract end-to-end).
- Predecessor missions (#518, #519) used the same git-pull deploy with no incidents.

**Pre-deploy step (mandatory)**: create the URL config file BEFORE pulling, so the first post-pull cycle's driver invocation finds it. Deploy procedure documented in WP for architecture-doc updates.

---

## Decisions deferred to per-WP design

These are noted here but resolved during WP authoring (see [tasks.md](./tasks.md) once generated):

- **D-001**: exact field-by-field diff comparison for `in_both` tasks — does it follow the `TRACKED_TASK_FIELDS` set from #518's `diff.py:33`, or do we expand?
- **D-002**: project-cache `ProjectCacheEntry` dataclass needs an `owner_id` field added (currently has only `title` and `is_archived`). Decision deferred to WP01 (state.py changes).
- **D-003**: precise format of the `task_deleted` event in `habits-history.jsonl` — match the existing event format conventions; decision deferred to WP for deletion-cleanup.
- **D-004**: exact set of `LayerSummary.errors` structured error tokens — what taxonomy? (e.g., `vikunja_unreachable`, `auth_failure`, `parse_error`, `empty_response_when_cache_nonzero`). Decision deferred to WP for diff/cycle.
