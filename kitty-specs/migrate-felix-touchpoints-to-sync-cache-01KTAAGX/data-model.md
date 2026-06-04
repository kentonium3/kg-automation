# Data Model: Migrate Felix Touchpoints to Sync Cache — Phase 1

**Mission**: `migrate-felix-touchpoints-to-sync-cache-01KTAAGX`
**Date**: 2026-06-04

The mission introduces one new module (`scripts/common/sync_cache.py`), one shared test fixture (`tests/common/conftest.py`), and modifies six touchpoint files in place. This document enumerates the runtime entities each new artifact owns, plus the migration-manifest data structure used at planning time.

---

## Entity 1 — `SyncCacheHelper` (the public API of `scripts/common/sync_cache.py`)

**Role**: The canonical cache-read entry point for every migrated touchpoint. Wraps `scripts/sync/state.py` reads with per-touchpoint SLA enforcement, error normalization, and (for two touchpoints) `state_log.jsonl`-derived completion-timestamp lookup.

**Persistence**: Module-level (no state). All state is read from `/data/services/openclaw/state/sync/` (driver cache) and `/data/services/openclaw/state/{habits-history,escalation,enrichment}/` (state logs).

**Public surface** (full contract in `contracts/helper-api.md`):

| Function | Signature | Purpose |
|---|---|---|
| `read_cached_tasks` | `(sla: SLATier, state_dir: Path = STATE_DIR_DEFAULT) -> dict[int, TaskCacheView]` | Read every cached task. Raises `OSError` on cache-missing, stale-beyond-SLA, malformed JSON, or schema-version mismatch. |
| `read_cached_task_by_id` | `(task_id: int, sla: SLATier, state_dir: Path = STATE_DIR_DEFAULT) -> TaskCacheView` | Read a single task. Raises `OSError` (with task_id in message) on cache-missing, stale, task-not-found, or empty-fields (private). |
| `read_freshness_pointer` | `(state_dir: Path = STATE_DIR_DEFAULT) -> datetime` | Return the cache's `last_polled_utc` as a UTC `datetime`. Raises `OSError` on missing/malformed. Used by tests + ad-hoc operator queries. |
| `read_completion_timestamps` | `(domain: str, task_id: int, state_log_dir: Path) -> CompletionTimestamps` | Return the most recent `complete`-state timestamp for `task_id` from `{domain}-history.jsonl`. `domain` is one of `"habits"`, `"escalation"`, `"enrichment"`. Raises `OSError` on missing state log; returns `CompletionTimestamps(None, None)` if task_id has no completion event. |

**Constants** (module-level):

| Constant | Type | Value | Purpose |
|---|---|---|---|
| `SLA_HOT` | `SLATier` | 60s | Touchpoints requiring near-real-time freshness (≤ 1 cycle stale). Unused in this mission; reserved for future. |
| `SLA_NORMAL` | `SLATier` | 900s (15 min) | All 6 in-scope touchpoints. Allows up to 3 missed cycles. |
| `SLA_BATCH` | `SLATier` | 3600s (1 h) | Daily sweepers / periodic enrichers. Unused in this mission. |
| `SLA_LOOSE` | `SLATier` | 86400s (24 h) | Analysis / reporting touchpoints. Unused in this mission. |
| `STATE_DIR_DEFAULT` | `Path` | `/data/services/openclaw/state/sync` | Inherited from `scripts.sync.state.STATE_DIR_DEFAULT`. |

**Internal helpers** (not exported):

- `_freshness_age_seconds(state_dir) -> float` — computes the wall-clock age of the freshness pointer
- `_format_error(touchpoint_name, failure_class, recovery_hint) -> str` — builds the structured stderr message body

---

## Entity 2 — `SLATier`

**Role**: A typed wrapper around the freshness-window seconds for one touchpoint.

**Persistence**: Module-level (immutable constants). Touchpoints reference by name (e.g., `SLA_NORMAL`).

**Schema**:

```python
@dataclass(frozen=True)
class SLATier:
    name: str           # "HOT", "NORMAL", "BATCH", "LOOSE"
    seconds: int        # the actual freshness window
```

**Relationships**:
- Passed to `read_cached_tasks` and `read_cached_task_by_id` as the `sla` parameter
- Compared against `freshness_age_seconds` in the helper's check
- Surfaces in stderr error messages: `"...stale beyond SLA_NORMAL (15 min); pointer age 23 min"`

---

## Entity 3 — `TaskCacheView`

**Role**: The shape returned to touchpoints from `read_cached_tasks` and `read_cached_task_by_id`. Strict subset of `scripts.sync.state.TaskCacheEntry` exposing only what touchpoints need.

**Persistence**: Constructed on read; not persisted. Touchpoints consume and discard.

**Schema**:

```python
@dataclass(frozen=True)
class TaskCacheView:
    task_id: int
    fields: dict[str, Any]              # the 7 TRACKED_TASK_FIELDS values (verbatim copy)
    vikunja_updated_at: str             # ISO-8601 UTC; the per-task last-update timestamp
    is_private: bool                    # True if fields is empty (private-project redaction applied)
```

**Field set in `fields`** (per `scripts/sync/diff.py:TRACKED_TASK_FIELDS`): `title`, `done`, `due_date`, `project_id`, `repeat_after`, `repeat_mode`, `labels`.

**Privacy semantics**:
- For a private-project task, `is_private` is `True` and `fields` is `{}`. Touchpoints MUST check `is_private` and treat the entry as "task data unavailable" (raise OSError per FR-006).
- The `read_cached_task_by_id` helper raises OSError when `is_private` is True (so touchpoints don't have to check). The bulk `read_cached_tasks` returns the entry with `is_private=True` so touchpoints can filter at their discretion (e.g., enumerate non-private tasks).

**Relationships**:
- Constructed by `read_cached_tasks` (one per cached task)
- Constructed by `read_cached_task_by_id` (one per ID)
- Consumed by every migrated touchpoint

---

## Entity 4 — `CompletionTimestamps`

**Role**: The shape returned by `read_completion_timestamps` for TPs that derive `done_at` from `state_log.jsonl` (TP-02, TP-10, TP-12).

**Persistence**: Constructed on read; not persisted.

**Schema**:

```python
@dataclass(frozen=True)
class CompletionTimestamps:
    most_recent_complete_at_utc: str | None    # ISO-8601 UTC of latest "complete" event; None if no completion in log
    most_recent_complete_date_et: str | None   # YYYY-MM-DD ET of latest "complete" event; None if no completion in log
```

**Why two fields**: The `at_utc` field is the wall-clock timestamp suitable for ordering. The `date_et` field is the day in Eastern Time the operator did the completion, which matches the habits-history.jsonl `date` field's semantics and avoids touchpoints re-doing the UTC→ET conversion.

**Relationships**:
- Returned by `read_completion_timestamps`
- Consumed by reconcilers (TP-02, TP-10, TP-12) to verify that JSONL state-log entries match cache `done` flags

---

## Entity 5 — `MockSyncCacheFixture` (the public API of `tests/common/conftest.py`)

**Role**: A pytest fixture that synthesizes cache state and lets each test parameterize cache contents, freshness pointer, and private-project list without touching live `/data/services/openclaw/state/sync/`.

**Persistence**: Per-test (pytest fixture lifecycle). The fixture writes a synthetic cache file tree to `tmp_path` and the touchpoint test's `read_cached_*` calls (or the helper's internal `read_task_cache`) consume from there.

**Schema** (the fixture's API, not the data shape):

```python
@pytest.fixture
def mock_sync_cache_fixture(tmp_path, monkeypatch):
    """
    Provides a builder for synthesizing cache state for a test.

    Example usage:
        def test_my_touchpoint(mock_sync_cache_fixture):
            cache = mock_sync_cache_fixture(
                tasks={
                    14: {"title": "Wake at 5", "done": False, ...},
                    15: {"title": "Meditate", "done": True, ...},
                },
                freshness_age_seconds=120,
                private_project_ids={3},
            )
            # The fixture has patched STATE_DIR_DEFAULT to tmp_path/sync;
            # touchpoint reads now hit the synthetic cache.
            result = my_touchpoint.run()
            assert ...
    """
    def build(*, tasks: dict[int, dict], freshness_age_seconds: float, private_project_ids: set[int] = frozenset()):
        # Constructs a synthetic TaskCacheRecord + FreshnessPointer
        # Writes them to tmp_path / "sync"
        # Patches STATE_DIR_DEFAULT to tmp_path / "sync"
        ...
    return build
```

**Relationships**:
- Used by every migrated touchpoint's test file
- Used by `tests/common/test_sync_cache.py` for testing the helper itself
- Does NOT replace existing `mock_urlopen` fixtures (those remain for write-side tests)

---

## Entity 6 — `MigrationManifest` (planning-time, not runtime)

**Role**: The reference table mapping each in-scope touchpoint to its SLA tier, field-set requirements, and migration WP. Lives in `plan.md` § Project Structure and `research.md` § Unknown 1; this entry exists for completeness.

**Persistence**: Planning artifacts only. Not loaded at runtime.

**Schema** (informal):

| TP | File | SLA | Reads `done_at`? | Reads `updated`? | WP |
|---|---|---|---|---|---|
| TP-02 | `scripts/habits/reconcile_completions.py` | `SLA_NORMAL` | Yes (via state_log) | Yes (via cache view) | WP02 |
| TP-03 | `scripts/habits/query_active_habits_v2.py` | `SLA_NORMAL` | No | No | WP02 |
| TP-04 | `scripts/habits/set_due_dates.py` (GET phase) | `SLA_NORMAL` | No | No | WP02 |
| TP-07 | `scripts/habits/morning_checkin_list.py` | `SLA_NORMAL` | No | No | WP02 |
| TP-10 | `scripts/escalation/reconcile_completions.py` | `SLA_NORMAL` | Yes (via state_log) | Yes (via cache view) | WP03 |
| TP-12 | `scripts/enrichment/reconcile_completions.py` | `SLA_NORMAL` | No | Yes (via cache view) | WP04 |

WP01 is the foundation (`sync_cache.py` + `tests/common/conftest.py` + helper tests). WP02-WP04 are the per-domain migrations. Total: 4 WPs (revised from the spec's "6 WPs likely" estimate).

---

## Entity-relationship summary

```
┌─────────────────────────────┐    ┌─────────────────────────────┐
│ #518 driver state files     │    │ state_log files             │
│ (on /data/...sync/)         │    │ (on /data/...state/)        │
│  ├── freshness.json          │    │  ├── habits-history.jsonl  │
│  ├── task-cache.json         │    │  ├── escalation-history... │
│  └── ...                     │    │  └── enrichment-history... │
└────────────┬─────────────────┘    └─────────────┬───────────────┘
             │                                    │
             ▼                                    ▼
       ┌─────────────────────────────────────────────┐
       │  scripts/common/sync_cache.py (this mission) │
       │  • read_cached_tasks (sla) → dict[id, View]  │
       │  • read_cached_task_by_id (id, sla) → View   │
       │  • read_freshness_pointer () → datetime      │
       │  • read_completion_timestamps (dom, id) → CT │
       │  • SLA_HOT / NORMAL / BATCH / LOOSE constants │
       └────────────────────┬────────────────────────┘
                            │
              ┌─────────────┼─────────────────────┐
              ▼             ▼                     ▼
    ┌───────────────┐ ┌─────────────────┐ ┌──────────────────┐
    │ habits TPs    │ │ escalation TP   │ │ enrichment TP    │
    │ (4 callsites) │ │ (1 callsite)    │ │ (1 callsite)     │
    └───────────────┘ └─────────────────┘ └──────────────────┘

   ┌─────────────────────────────────┐
   │ tests/common/conftest.py        │ ← Used by ALL above test suites
   │ mock_sync_cache_fixture(...)    │
   └─────────────────────────────────┘
```

---

## Field-set evolution policy

`TRACKED_TASK_FIELDS` is NOT modified by this mission (per Phase 0 research). The 6 in-scope touchpoints read only fields already in the set. Future missions that introduce touchpoints reading fields outside the set will face the same plan-phase decision matrix this mission encoded in spec C-007 and FR-008.
