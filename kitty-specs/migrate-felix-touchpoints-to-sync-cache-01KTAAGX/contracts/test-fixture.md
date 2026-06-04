# Contract: `tests/common/conftest.py` — Shared Mock Cache Fixture

**Mission**: `migrate-felix-touchpoints-to-sync-cache-01KTAAGX`
**Phase**: Plan / Phase 1 / contracts
**Date**: 2026-06-04

The shared pytest fixture every migrated touchpoint test (and the helper's own test) uses to inject synthetic cache state. Replaces the per-touchpoint `mock_urlopen` patches used pre-migration for the read paths (write-side `mock_urlopen` patches stay where touchpoints retain writes).

---

## Fixture API

```python
# tests/common/conftest.py
"""Shared mock cache fixture for migrated touchpoint tests (mission #519)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

import pytest


@pytest.fixture
def mock_sync_cache_fixture(tmp_path: Path, monkeypatch) -> Iterator[callable]:
    """Returns a builder that synthesizes cache state for one test invocation.

    Usage:
        def test_foo(mock_sync_cache_fixture):
            mock_sync_cache_fixture(
                tasks={
                    14: {"title": "Wake at 5", "done": False, "due_date": "...", ...},
                    15: {"title": "Meditate", "done": True, ...},
                },
                freshness_age_seconds=120,
                private_project_ids={3},  # tasks whose project_id is in this set
                                          # get is_private=True + empty fields
                vikunja_updated_at_per_task={14: "2026-06-04T19:30:00Z", ...},  # optional
            )
            # After the builder runs:
            #   sync_cache.STATE_DIR_DEFAULT is monkeypatched to tmp_path / "sync"
            #   The synthetic state files exist on disk
            #   The touchpoint's read code finds them
            result = my_touchpoint.run()
            assert ...

    The builder may be called at most ONCE per test (re-call is an
    AssertionError). To compose multiple cache states sequentially, write
    separate tests or use the fixture's `update()` method (not implemented
    in v1; deferred to a future mission if needed).
    """
```

---

## Builder signature

```python
def build(
    *,
    tasks: dict[int, dict[str, Any]],
    freshness_age_seconds: float = 60.0,
    private_project_ids: frozenset[int] = frozenset(),
    vikunja_updated_at_per_task: dict[int, str] | None = None,
    felix_last_observed_at: str | None = None,
) -> Path:
    """Build the synthetic cache.

    Args:
        tasks: dict mapping integer task_id → dict of task fields.
            Each inner dict provides values for the 7 TRACKED_TASK_FIELDS
            (title, done, due_date, project_id, repeat_after, repeat_mode,
            labels) plus optional project_id for private-list testing.
        freshness_age_seconds: How old the freshness pointer is, relative
            to the test's notion of "now". Default 60s (fresh).
        private_project_ids: Set of project_ids treated as private. Tasks
            whose project_id is in this set get is_private=True semantics
            (empty fields, project_id retained).
        vikunja_updated_at_per_task: Per-task vikunja_updated_at override.
            Default: all tasks get a timestamp 1 second older than the
            freshness pointer.
        felix_last_observed_at: Cache's last_updated_utc. Default: now.

    Returns:
        The synthetic STATE_DIR_DEFAULT path (a tmp_path subdirectory).
    """
```

---

## Behavior contract

1. Compute `pointer_utc = now_utc - freshness_age_seconds`.
2. For each `(task_id, task_dict)` in `tasks`:
   - Determine `is_private = task_dict.get("project_id") in private_project_ids`
   - Build a `TaskCacheEntry`-shaped dict (using `state.TaskCacheEntry` semantics):
     - `vikunja_task_id`: `task_id`
     - `fields`: `{}` if `is_private` else a curated dict of the 7 TRACKED_TASK_FIELDS
     - `vikunja_updated_at`: per-task override OR `(pointer_utc - 1s).isoformat() + "Z"`
     - `felix_last_observed_at`: `felix_last_observed_at` OR `now_utc.isoformat() + "Z"`
3. Construct a `TaskCacheRecord` and write it to `tmp_path / "sync" / "task-cache.json"` via `state.write_task_cache(tmp_path / "sync", record)`.
4. Construct a `FreshnessPointer` and write it to `tmp_path / "sync" / "freshness.json"` via `state.write_freshness(...)`.
5. Patch `scripts.common.sync_cache.STATE_DIR_DEFAULT` (and `scripts.sync.state.STATE_DIR_DEFAULT` if different) to point at `tmp_path / "sync"`.
6. Return the path so tests can do additional assertions on cache contents if needed.

**Idempotency**: build may only be called once per test. Subsequent calls raise `AssertionError("mock_sync_cache_fixture is single-call; use separate tests for multiple cache states")`.

---

## State-log fixture (companion)

For touchpoints that use `read_completion_timestamps` (TP-02, TP-10, TP-12), the fixture exports a companion builder:

```python
@pytest.fixture
def mock_state_log_fixture(tmp_path: Path, monkeypatch) -> Iterator[callable]:
    """Inject synthetic state-log JSONL content.

    Usage:
        def test_reconciler(mock_sync_cache_fixture, mock_state_log_fixture):
            mock_sync_cache_fixture(tasks={...}, freshness_age_seconds=120)
            mock_state_log_fixture(
                domain="habits",
                entries=[
                    {"domain": "habits", "task_id": 14, "title": "Wake at 5",
                     "date": "2026-06-04", "state": "complete",
                     "source": "whatsapp",
                     "timestamp": "2026-06-04T13:24:10+00:00"},
                    ...
                ],
            )
            ...
    """
    def build(*, domain: str, entries: list[dict]) -> Path:
        log_dir = tmp_path / "state-logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"{domain}-history.jsonl"
        log_path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
        # Patch the touchpoint's state_log_dir reference if it has one.
        # Touchpoints reading state_log via sync_cache.read_completion_timestamps
        # pass state_log_dir explicitly, so no module-level patch is needed.
        return log_path
    return build
```

---

## Test invariants

Every test using `mock_sync_cache_fixture` MUST:

1. Call the builder before invoking the touchpoint under test.
2. NOT touch live `/data/services/openclaw/state/sync/` or any `~/.openclaw/` directory.
3. NOT make `urllib.request.urlopen` calls for the read path. (Write-side urlopen mocks may remain for touchpoints that retain writes.)

**Verification**: a pytest collection hook in `tests/conftest.py` (top-level) sets `monkeypatch.setattr("urllib.request.urlopen", ...)` to raise `RuntimeError("test attempted live HTTP")` so any leaked direct-read attempt during a test is caught immediately. Write-side tests that need real urlopen mocking patch over this guard.

---

## Out-of-scope for this fixture

- **conflict-events.jsonl mocking**: not needed; no touchpoint reads it. Future missions may add it.
- **guard-state.json mocking**: not needed; no touchpoint reads it.
- **Mid-test cache update**: deferred. If a touchpoint needs to test "behavior across multiple driver ticks," use separate tests with different builder calls.

---

## Verification

`tests/common/test_sync_cache.py` exercises the fixture: build a cache, call `read_cached_tasks`, assert returned tasks match the synthetic input. This doubles as a fixture sanity check and as the helper's test.
