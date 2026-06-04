"""Shared fixtures for tests/common/.

Provides:

- ``REPO_ROOT`` constant — used by the CLI subprocess tests to set
  ``PYTHONPATH`` for the spawned child.
- ``state_dir`` fixture — creates an isolated temp directory and
  monkey-patches ``scripts.common.state_log.STATE_DIR`` so in-process
  tests never touch the production state path
  (``/data/services/openclaw/state``).
- ``good_habits_record`` fixture — a known-good habits record reused
  across append and read tests.
- ``mock_sync_cache_fixture`` — builder that synthesizes sync cache state
  for one test invocation (mission #519).
- ``mock_state_log_fixture`` — builder that writes synthetic per-domain
  JSONL state log content (mission #519).

The conftest also inserts the repo root onto ``sys.path`` so test files
can ``from scripts.common import state_log`` without an installed
package (mirrors the pattern in ``tests/inbox/conftest.py`` and
``tests/habits/conftest.py``).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

import pytest

# Repo root is two levels above this conftest (tests/common/conftest.py).
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def state_dir(tmp_path, monkeypatch):
    """Return an isolated temp state-log directory.

    Monkey-patches ``scripts.common.state_log.STATE_DIR`` to the temp
    dir, so any in-process call to ``append()`` / ``read()`` lands in
    the temp tree, never under ``/data/services/openclaw/state``.
    """
    d = tmp_path / "state"
    monkeypatch.setattr("scripts.common.state_log.STATE_DIR", d)
    return d


@pytest.fixture
def good_habits_record():
    """A known-good habits record matching the data-model contract."""
    return {
        "domain": "habits",
        "task_id": 14,
        "title": "Wake at 5:00 AM",
        "date": "2026-05-19",
        "state": "complete",
        "source": "whatsapp",
        "note": None,
        "timestamp": "2026-05-19T11:05:11+00:00",
    }


# ---------------------------------------------------------------------------
# Sync cache fixtures (mission #519)
# ---------------------------------------------------------------------------

#: The 7 curated task fields the driver tracks.
_TRACKED_TASK_FIELDS = frozenset(
    {"title", "done", "due_date", "project_id", "repeat_after", "repeat_mode", "labels"}
)


@pytest.fixture
def mock_sync_cache_fixture(
    tmp_path: Path, monkeypatch
) -> Iterator[Any]:
    """Return a builder that synthesizes sync cache state for one test.

    After calling the builder:
    - ``scripts.common.sync_cache.STATE_DIR_DEFAULT`` is monkeypatched to
      ``tmp_path / "sync"``.
    - ``scripts.sync.state.STATE_DIR_DEFAULT`` is monkeypatched to the same
      path.
    - The synthetic ``task-cache.json`` and ``freshness.json`` files exist
      under that directory.

    The builder may be called at most ONCE per test.  A second call raises
    ``AssertionError``.

    Usage::

        def test_something(mock_sync_cache_fixture):
            sync_dir = mock_sync_cache_fixture(
                tasks={14: {"title": "Wake at 5", "done": False, "due_date": None,
                            "project_id": 2, "repeat_after": 0,
                            "repeat_mode": "default", "labels": []}},
                freshness_age_seconds=120,
            )
            # sync_dir == tmp_path / "sync"
    """
    from scripts.sync import state as st

    _called = [False]

    def build(
        *,
        tasks: dict[int, dict[str, Any]],
        freshness_age_seconds: float = 60.0,
        private_project_ids: frozenset[int] = frozenset(),
        vikunja_updated_at_per_task: dict[int, str] | None = None,
        felix_last_observed_at: str | None = None,
    ) -> Path:
        """Build synthetic cache state.

        Args:
            tasks: Mapping of integer task_id → dict of task fields.
            freshness_age_seconds: Age of the freshness pointer in seconds.
                Default 60 (fresh under SLA_NORMAL).
            private_project_ids: Set of project_ids whose tasks are treated as
                private (empty ``fields``, ``is_private=True``).
            vikunja_updated_at_per_task: Per-task ``vikunja_updated_at``
                override.  Default: pointer_utc minus 1 second.
            felix_last_observed_at: Cache ``last_updated_utc``.  Default: now.

        Returns:
            The synthetic ``STATE_DIR_DEFAULT`` path.
        """
        if _called[0]:
            raise AssertionError(
                "mock_sync_cache_fixture is single-call; "
                "use separate tests for multiple cache states"
            )
        _called[0] = True

        sync_dir = tmp_path / "sync"
        sync_dir.mkdir(parents=True, exist_ok=True)

        now_utc = datetime.now(timezone.utc)
        pointer_utc = now_utc - timedelta(seconds=freshness_age_seconds)
        pointer_utc_str = pointer_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        now_utc_str = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

        felix_last_obs = felix_last_observed_at or now_utc_str
        default_task_ts = (pointer_utc - timedelta(seconds=1)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )

        # Build the TaskCacheRecord
        task_entries: dict[str, st.TaskCacheEntry] = {}
        for task_id, task_dict in tasks.items():
            project_id = task_dict.get("project_id")
            is_private = project_id in private_project_ids

            if is_private:
                fields: dict[str, Any] = {}
            else:
                fields = {
                    k: task_dict.get(k)
                    for k in _TRACKED_TASK_FIELDS
                    if k in task_dict
                }

            per_task_ts = (
                vikunja_updated_at_per_task.get(task_id, default_task_ts)
                if vikunja_updated_at_per_task
                else default_task_ts
            )

            task_entries[str(task_id)] = st.TaskCacheEntry(
                vikunja_task_id=task_id,
                fields=fields,
                vikunja_updated_at=per_task_ts,
                felix_last_observed_at=felix_last_obs,
            )

        task_record = st.TaskCacheRecord(
            last_updated_utc=now_utc_str,
            tasks=task_entries,
        )
        st.write_task_cache(sync_dir, task_record)

        # Build the FreshnessPointer
        freshness = st.FreshnessPointer(
            last_updated_utc=pointer_utc_str,
            layers={
                "status_and_task": st.FreshnessLayer(
                    last_polled_utc=pointer_utc_str,
                ),
            },
        )
        st.write_freshness(sync_dir, freshness)

        # Monkeypatch both module-level STATE_DIR_DEFAULT references
        monkeypatch.setattr("scripts.common.sync_cache.STATE_DIR_DEFAULT", sync_dir)
        monkeypatch.setattr("scripts.sync.state.STATE_DIR_DEFAULT", sync_dir)

        return sync_dir

    yield build


@pytest.fixture
def mock_state_log_fixture(tmp_path: Path) -> Iterator[Any]:
    """Return a builder that writes synthetic state-log JSONL content.

    Usage::

        def test_reconciler(mock_sync_cache_fixture, mock_state_log_fixture):
            mock_sync_cache_fixture(tasks={...})
            log_path = mock_state_log_fixture(
                domain="habits",
                entries=[
                    {"domain": "habits", "task_id": 14, "title": "Wake at 5",
                     "date": "2026-06-04", "state": "complete",
                     "source": "whatsapp",
                     "timestamp": "2026-06-04T13:24:10+00:00"},
                ],
            )
            # Reads via read_completion_timestamps(domain, task_id, log_path.parent)

    No monkeypatching needed — ``read_completion_timestamps`` takes
    ``state_log_dir`` as an explicit argument; callers pass
    ``log_path.parent``.
    """

    def build(*, domain: str, entries: list[dict]) -> Path:
        """Write synthetic JSONL state log and return its path.

        Args:
            domain: Domain name (e.g. ``"habits"``).
            entries: List of record dicts; each is written as one JSON line.

        Returns:
            Path to the written JSONL file.
        """
        log_dir = tmp_path / "state-logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"{domain}-history.jsonl"
        log_path.write_text(
            "\n".join(json.dumps(e) for e in entries) + "\n",
            encoding="utf-8",
        )
        return log_path

    yield build
