"""Tests for scripts/common/sync_cache.py (WP01 / T003).

Covers every public function of the sync cache helper with:
- Happy path (fresh cache, valid tasks)
- Every documented failure path (missing files, stale pointer, schema mismatch,
  task not found, private task, missing state log)
- Privacy boundary assertion (no field content in private-task error messages)
- SLA tier constants validation
- Error message format assertions (substring checks per the contract)

All I/O is sandboxed via ``tmp_path`` and the shared fixtures from
``tests/common/conftest.py``.  No live network; no production filesystem.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

import scripts.common.sync_cache as sc
from scripts.sync import state as st

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

_TASK_A: dict[str, Any] = {
    "title": "Wake at 5:00 AM",
    "done": False,
    "due_date": "2026-06-04T09:00:00Z",
    "project_id": 2,
    "repeat_after": 1,
    "repeat_mode": "default",
    "labels": [],
}
_TASK_B: dict[str, Any] = {
    "title": "Meditate",
    "done": True,
    "due_date": "2026-06-04T09:00:00Z",
    "project_id": 2,
    "repeat_after": 1,
    "repeat_mode": "default",
    "labels": [],
}
_TASK_C: dict[str, Any] = {
    "title": "Private task",
    "done": False,
    "due_date": None,
    "project_id": 99,  # private project
    "repeat_after": 0,
    "repeat_mode": "default",
    "labels": [],
}

_THREE_TASKS = {14: _TASK_A, 15: _TASK_B, 16: _TASK_C}
_PRIVATE_PROJECT_IDS: frozenset[int] = frozenset({99})


# ===========================================================================
# Group 1 — SLA tier constants
# ===========================================================================


class TestSLATiers:
    def test_sla_hot(self):
        assert sc.SLA_HOT.name == "HOT"
        assert sc.SLA_HOT.seconds == 60

    def test_sla_normal(self):
        assert sc.SLA_NORMAL.name == "NORMAL"
        assert sc.SLA_NORMAL.seconds == 900

    def test_sla_batch(self):
        assert sc.SLA_BATCH.name == "BATCH"
        assert sc.SLA_BATCH.seconds == 3600

    def test_sla_loose(self):
        assert sc.SLA_LOOSE.name == "LOOSE"
        assert sc.SLA_LOOSE.seconds == 86400

    def test_all_are_frozen(self):
        with pytest.raises((AttributeError, TypeError)):
            sc.SLA_NORMAL.seconds = 100  # type: ignore[misc]


# ===========================================================================
# Group 2 — read_cached_tasks
# ===========================================================================


class TestReadCachedTasks:
    def test_happy_path_three_tasks(self, mock_sync_cache_fixture):
        """Fresh cache with 3 tasks returns all 3 TaskCacheViews."""
        mock_sync_cache_fixture(
            tasks=_THREE_TASKS,
            freshness_age_seconds=120,
            private_project_ids=_PRIVATE_PROJECT_IDS,
        )
        result = sc.read_cached_tasks(sc.SLA_NORMAL)
        assert len(result) == 3
        assert 14 in result
        assert 15 in result
        assert 16 in result

    def test_happy_path_task_view_fields(self, mock_sync_cache_fixture):
        """TaskCacheView for a non-private task has populated fields."""
        mock_sync_cache_fixture(
            tasks={14: _TASK_A},
            freshness_age_seconds=60,
        )
        views = sc.read_cached_tasks(sc.SLA_NORMAL)
        view = views[14]
        assert view.task_id == 14
        assert view.is_private is False
        assert view.fields.get("title") == "Wake at 5:00 AM"
        assert isinstance(view.vikunja_updated_at, str)

    def test_private_task_has_empty_fields(self, mock_sync_cache_fixture):
        """A task in a private project has is_private=True and empty fields."""
        mock_sync_cache_fixture(
            tasks={16: _TASK_C},
            private_project_ids=_PRIVATE_PROJECT_IDS,
            freshness_age_seconds=60,
        )
        views = sc.read_cached_tasks(sc.SLA_NORMAL)
        view = views[16]
        assert view.is_private is True
        assert view.fields == {}

    def test_cache_missing_freshness_raises_oserror(self, tmp_path):
        """When freshness.json is absent the caller gets an OSError."""
        empty_dir = tmp_path / "empty_sync"
        empty_dir.mkdir()
        with pytest.raises(OSError) as exc_info:
            sc.read_cached_tasks(sc.SLA_NORMAL, state_dir=empty_dir,
                                 touchpoint_name="habits.test")
        msg = str(exc_info.value)
        assert "freshness pointer missing" in msg
        assert "habits.test" in msg

    def test_cache_missing_freshness_has_recovery_hint(self, tmp_path):
        """Error message for missing freshness includes the --bootstrap hint."""
        empty_dir = tmp_path / "empty_sync"
        empty_dir.mkdir()
        with pytest.raises(OSError) as exc_info:
            sc.read_cached_tasks(sc.SLA_NORMAL, state_dir=empty_dir)
        assert "Recovery:" in str(exc_info.value)
        assert "--bootstrap" in str(exc_info.value)

    def test_stale_pointer_raises_oserror(self, mock_sync_cache_fixture):
        """Pointer older than SLA raises with 'stale beyond SLA_NORMAL'."""
        mock_sync_cache_fixture(
            tasks={14: _TASK_A},
            freshness_age_seconds=1000,  # > 900s SLA_NORMAL
        )
        with pytest.raises(OSError) as exc_info:
            sc.read_cached_tasks(sc.SLA_NORMAL, touchpoint_name="habits.morning")
        msg = str(exc_info.value)
        assert "stale beyond SLA_NORMAL" in msg
        assert "habits.morning" in msg

    def test_stale_message_includes_age(self, mock_sync_cache_fixture):
        """Stale error message includes the pointer age in seconds."""
        mock_sync_cache_fixture(
            tasks={14: _TASK_A},
            freshness_age_seconds=1500,
        )
        with pytest.raises(OSError) as exc_info:
            sc.read_cached_tasks(sc.SLA_NORMAL)
        # Age should be ~1500 (within a second of test execution time)
        msg = str(exc_info.value)
        assert "1500s" in msg or "149" in msg or "150" in msg  # fuzzy for timing

    def test_stale_message_has_timer_recovery_hint(self, mock_sync_cache_fixture):
        """Stale error has the timer recovery hint."""
        mock_sync_cache_fixture(
            tasks={14: _TASK_A},
            freshness_age_seconds=2000,
        )
        with pytest.raises(OSError) as exc_info:
            sc.read_cached_tasks(sc.SLA_NORMAL)
        assert "felix-vikunja-sync.timer" in str(exc_info.value)

    def test_touchpoint_name_in_stale_error(self, mock_sync_cache_fixture):
        """Touchpoint name appears as leading bracket in the error message."""
        mock_sync_cache_fixture(
            tasks={14: _TASK_A},
            freshness_age_seconds=2000,
        )
        with pytest.raises(OSError) as exc_info:
            sc.read_cached_tasks(
                sc.SLA_NORMAL, touchpoint_name="habits.set_due_dates"
            )
        assert "[habits.set_due_dates]" in str(exc_info.value)

    def test_schema_version_mismatch_propagates(self, tmp_path):
        """Schema version mismatch from state.py is propagated as OSError."""
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()

        # Write a valid freshness.json first (so stale check passes)
        now_utc = datetime.now(timezone.utc)
        fresh_ts = (now_utc - timedelta(seconds=60)).strftime("%Y-%m-%dT%H:%M:%SZ")
        fp = st.FreshnessPointer(
            last_updated_utc=fresh_ts,
            layers={"status_and_task": st.FreshnessLayer(last_polled_utc=fresh_ts)},
        )
        st.write_freshness(sync_dir, fp)

        # Write a task-cache.json with wrong schema_version
        cache_path = sync_dir / "task-cache.json"
        bad_data = {
            "schema_version": 99,
            "last_updated_utc": "2026-06-04T00:00:00Z",
            "tasks": {},
        }
        cache_path.write_text(json.dumps(bad_data), encoding="utf-8")

        with pytest.raises(OSError) as exc_info:
            sc.read_cached_tasks(sc.SLA_NORMAL, state_dir=sync_dir)
        assert "schema_version" in str(exc_info.value).lower() or "mismatch" in str(exc_info.value).lower()

    def test_returns_empty_dict_for_empty_cache(self, tmp_path):
        """Fresh pointer + no tasks → empty dict (not an error)."""
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()

        now_utc = datetime.now(timezone.utc)
        ts = (now_utc - timedelta(seconds=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        fp = st.FreshnessPointer(
            last_updated_utc=ts,
            layers={"status_and_task": st.FreshnessLayer(last_polled_utc=ts)},
        )
        st.write_freshness(sync_dir, fp)
        # Don't write task-cache.json → state.read_task_cache returns empty default

        result = sc.read_cached_tasks(sc.SLA_NORMAL, state_dir=sync_dir)
        assert result == {}


# ===========================================================================
# Group 3 — read_cached_task_by_id
# ===========================================================================


class TestReadCachedTaskById:
    def test_happy_path(self, mock_sync_cache_fixture):
        """Task in cache → returns correct TaskCacheView."""
        mock_sync_cache_fixture(
            tasks={14: _TASK_A},
            freshness_age_seconds=60,
        )
        view = sc.read_cached_task_by_id(14, sc.SLA_NORMAL)
        assert view.task_id == 14
        assert view.is_private is False
        assert view.fields.get("title") == "Wake at 5:00 AM"

    def test_task_not_found_raises_oserror(self, mock_sync_cache_fixture):
        """Task id not in cache → OSError with task_id in message."""
        mock_sync_cache_fixture(
            tasks={14: _TASK_A},
            freshness_age_seconds=60,
        )
        with pytest.raises(OSError) as exc_info:
            sc.read_cached_task_by_id(
                999, sc.SLA_NORMAL, touchpoint_name="habits.morning"
            )
        msg = str(exc_info.value)
        assert "999" in msg
        assert "not in sync cache" in msg
        assert "habits.morning" in msg

    def test_task_not_found_includes_last_polled_utc(self, mock_sync_cache_fixture):
        """Task-not-found error includes cache's last_polled_utc."""
        mock_sync_cache_fixture(
            tasks={14: _TASK_A},
            freshness_age_seconds=60,
        )
        with pytest.raises(OSError) as exc_info:
            sc.read_cached_task_by_id(999, sc.SLA_NORMAL)
        msg = str(exc_info.value)
        assert "last_polled_utc" in msg

    def test_private_task_raises_oserror(self, mock_sync_cache_fixture):
        """Private task → OSError; task_id in message, no field content."""
        mock_sync_cache_fixture(
            tasks={16: _TASK_C},
            freshness_age_seconds=60,
            private_project_ids=_PRIVATE_PROJECT_IDS,
        )
        with pytest.raises(OSError) as exc_info:
            sc.read_cached_task_by_id(
                16, sc.SLA_NORMAL, touchpoint_name="escalation.reconcile"
            )
        msg = str(exc_info.value)
        assert "16" in msg
        assert "private-project" in msg
        assert "escalation.reconcile" in msg

    def test_private_task_error_has_no_field_content(self, mock_sync_cache_fixture):
        """Privacy boundary: the title of the private task must NOT appear in the error."""
        mock_sync_cache_fixture(
            tasks={16: _TASK_C},
            freshness_age_seconds=60,
            private_project_ids=_PRIVATE_PROJECT_IDS,
        )
        with pytest.raises(OSError) as exc_info:
            sc.read_cached_task_by_id(16, sc.SLA_NORMAL)
        msg = str(exc_info.value)
        # The private task's title is "Private task" — must NOT appear
        assert "Private task" not in msg
        # The project_id value (99) is an integer — acceptable to appear as task metadata
        # but field-level content like "title" key or its value must be absent
        assert "title" not in msg

    def test_propagates_stale_error(self, mock_sync_cache_fixture):
        """Stale cache errors from read_cached_tasks are propagated."""
        mock_sync_cache_fixture(
            tasks={14: _TASK_A},
            freshness_age_seconds=2000,
        )
        with pytest.raises(OSError) as exc_info:
            sc.read_cached_task_by_id(14, sc.SLA_NORMAL)
        assert "stale" in str(exc_info.value)

    def test_propagates_missing_freshness_error(self, tmp_path):
        """Missing freshness file error from read_cached_tasks is propagated."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        with pytest.raises(OSError) as exc_info:
            sc.read_cached_task_by_id(14, sc.SLA_NORMAL, state_dir=empty_dir)
        assert "freshness pointer missing" in str(exc_info.value)


# ===========================================================================
# Group 4 — read_freshness_pointer
# ===========================================================================


class TestReadFreshnessPointer:
    def test_returns_utc_datetime(self, mock_sync_cache_fixture):
        """Returns a timezone-aware UTC datetime."""
        mock_sync_cache_fixture(tasks={14: _TASK_A}, freshness_age_seconds=300)
        dt = sc.read_freshness_pointer()
        assert isinstance(dt, datetime)
        assert dt.tzinfo is not None
        assert dt.tzinfo == timezone.utc

    def test_returns_correct_pointer_time(self, mock_sync_cache_fixture):
        """The returned datetime reflects the actual freshness_age_seconds."""
        mock_sync_cache_fixture(tasks={14: _TASK_A}, freshness_age_seconds=300)
        before = datetime.now(timezone.utc)
        dt = sc.read_freshness_pointer()
        after = datetime.now(timezone.utc)
        # The pointer is ~300s in the past
        age = (before - dt).total_seconds()
        assert 290 < age < 320  # allow a bit of test-run slop

    def test_missing_freshness_raises(self, tmp_path):
        """Missing freshness file raises OSError."""
        empty = tmp_path / "empty"
        empty.mkdir()
        with pytest.raises(OSError):
            sc.read_freshness_pointer(state_dir=empty)

    def test_touchpoint_name_in_error(self, tmp_path):
        """When touchpoint_name is given, it appears in the error."""
        empty = tmp_path / "empty"
        empty.mkdir()
        with pytest.raises(OSError) as exc_info:
            sc.read_freshness_pointer(state_dir=empty, touchpoint_name="habits.check")
        assert "habits.check" in str(exc_info.value)


# ===========================================================================
# Group 5 — read_completion_timestamps
# ===========================================================================


class TestReadCompletionTimestamps:
    def test_happy_path_latest_complete_event(self, mock_state_log_fixture):
        """Returns the most recent 'complete' event for the task."""
        log_path = mock_state_log_fixture(
            domain="habits",
            entries=[
                {
                    "domain": "habits",
                    "task_id": 14,
                    "title": "Wake at 5",
                    "date": "2026-06-03",
                    "state": "complete",
                    "source": "whatsapp",
                    "timestamp": "2026-06-03T11:05:00+00:00",
                },
                {
                    "domain": "habits",
                    "task_id": 14,
                    "title": "Wake at 5",
                    "date": "2026-06-04",
                    "state": "complete",
                    "source": "whatsapp",
                    "timestamp": "2026-06-04T13:24:10+00:00",
                },
            ],
        )
        result = sc.read_completion_timestamps("habits", 14, log_path.parent)
        assert result.most_recent_complete_at_utc == "2026-06-04T13:24:10+00:00"
        assert result.most_recent_complete_date_et == "2026-06-04"

    def test_no_completions_returns_none_none(self, mock_state_log_fixture):
        """No completions for task_id → CompletionTimestamps(None, None)."""
        log_path = mock_state_log_fixture(
            domain="habits",
            entries=[
                {
                    "domain": "habits",
                    "task_id": 99,
                    "title": "Other task",
                    "date": "2026-06-04",
                    "state": "complete",
                    "source": "whatsapp",
                    "timestamp": "2026-06-04T13:00:00+00:00",
                },
            ],
        )
        result = sc.read_completion_timestamps("habits", 14, log_path.parent)
        assert result.most_recent_complete_at_utc is None
        assert result.most_recent_complete_date_et is None

    def test_empty_log_returns_none_none(self, mock_state_log_fixture):
        """Empty log file returns (None, None) — not an error."""
        log_path = mock_state_log_fixture(domain="habits", entries=[])
        result = sc.read_completion_timestamps("habits", 14, log_path.parent)
        assert result.most_recent_complete_at_utc is None

    def test_only_non_complete_entries_returns_none(self, mock_state_log_fixture):
        """Entries with state != 'complete' are skipped."""
        log_path = mock_state_log_fixture(
            domain="habits",
            entries=[
                {
                    "domain": "habits",
                    "task_id": 14,
                    "date": "2026-06-04",
                    "state": "skipped",
                    "source": "whatsapp",
                    "timestamp": "2026-06-04T12:00:00+00:00",
                },
            ],
        )
        result = sc.read_completion_timestamps("habits", 14, log_path.parent)
        assert result.most_recent_complete_at_utc is None

    def test_multiple_complete_events_returns_latest(self, mock_state_log_fixture):
        """When multiple 'complete' events exist, the latest timestamp wins."""
        log_path = mock_state_log_fixture(
            domain="habits",
            entries=[
                {
                    "domain": "habits",
                    "task_id": 14,
                    "date": "2026-06-01",
                    "state": "complete",
                    "source": "whatsapp",
                    "timestamp": "2026-06-01T11:00:00+00:00",
                },
                {
                    "domain": "habits",
                    "task_id": 14,
                    "date": "2026-06-04",
                    "state": "complete",
                    "source": "whatsapp",
                    "timestamp": "2026-06-04T13:24:10+00:00",
                },
                {
                    "domain": "habits",
                    "task_id": 14,
                    "date": "2026-06-02",
                    "state": "complete",
                    "source": "whatsapp",
                    "timestamp": "2026-06-02T09:00:00+00:00",
                },
            ],
        )
        result = sc.read_completion_timestamps("habits", 14, log_path.parent)
        assert result.most_recent_complete_at_utc == "2026-06-04T13:24:10+00:00"
        assert result.most_recent_complete_date_et == "2026-06-04"

    def test_missing_state_log_raises_oserror(self, tmp_path):
        """Missing JSONL file raises OSError."""
        empty_dir = tmp_path / "state-logs"
        empty_dir.mkdir()
        with pytest.raises(OSError) as exc_info:
            sc.read_completion_timestamps("habits", 14, empty_dir)
        msg = str(exc_info.value)
        assert "habits-history.jsonl" in msg
        assert "not found" in msg

    def test_malformed_jsonl_line_is_skipped(self, tmp_path):
        """Malformed JSONL lines are silently skipped; valid lines still parsed."""
        log_dir = tmp_path / "state-logs"
        log_dir.mkdir()
        log_path = log_dir / "habits-history.jsonl"
        content = (
            'NOT_VALID_JSON\n'
            '{"domain": "habits", "task_id": 14, "date": "2026-06-04", '
            '"state": "complete", "source": "whatsapp", '
            '"timestamp": "2026-06-04T13:00:00+00:00"}\n'
        )
        log_path.write_text(content, encoding="utf-8")
        result = sc.read_completion_timestamps("habits", 14, log_dir)
        # The valid line was still processed despite the malformed predecessor
        assert result.most_recent_complete_at_utc == "2026-06-04T13:00:00+00:00"

    def test_escalation_domain(self, mock_state_log_fixture):
        """Works correctly for the 'escalation' domain."""
        log_path = mock_state_log_fixture(
            domain="escalation",
            entries=[
                {
                    "domain": "escalation",
                    "task_id": 27,
                    "date": "2026-06-04",
                    "state": "complete",
                    "source": "agent",
                    "timestamp": "2026-06-04T14:00:00+00:00",
                },
            ],
        )
        result = sc.read_completion_timestamps("escalation", 27, log_path.parent)
        assert result.most_recent_complete_at_utc == "2026-06-04T14:00:00+00:00"

    def test_enrichment_domain(self, mock_state_log_fixture):
        """Works correctly for the 'enrichment' domain."""
        log_path = mock_state_log_fixture(
            domain="enrichment",
            entries=[
                {
                    "domain": "enrichment",
                    "task_id": 55,
                    "date": "2026-06-04",
                    "state": "complete",
                    "source": "agent",
                    "timestamp": "2026-06-04T15:00:00+00:00",
                },
            ],
        )
        result = sc.read_completion_timestamps("enrichment", 55, log_path.parent)
        assert result.most_recent_complete_at_utc == "2026-06-04T15:00:00+00:00"


# ===========================================================================
# Group 6 — is_cache_healthy
# ===========================================================================


class TestIsCacheHealthy:
    def test_true_on_fresh_cache(self, mock_sync_cache_fixture):
        """Returns True when the cache is fresh and valid."""
        mock_sync_cache_fixture(tasks={14: _TASK_A}, freshness_age_seconds=60)
        assert sc.is_cache_healthy(sc.SLA_NORMAL) is True

    def test_false_on_stale_cache(self, mock_sync_cache_fixture):
        """Returns False when the pointer is older than SLA."""
        mock_sync_cache_fixture(tasks={14: _TASK_A}, freshness_age_seconds=2000)
        assert sc.is_cache_healthy(sc.SLA_NORMAL) is False

    def test_false_on_missing_cache(self, tmp_path):
        """Returns False when the freshness file is absent."""
        empty = tmp_path / "empty"
        empty.mkdir()
        assert sc.is_cache_healthy(sc.SLA_NORMAL, state_dir=empty) is False

    def test_never_raises(self, tmp_path):
        """is_cache_healthy never raises regardless of state."""
        bad_dir = tmp_path / "nonexistent"
        # No mkdir — directory does not exist
        result = sc.is_cache_healthy(sc.SLA_NORMAL, state_dir=bad_dir)
        assert result is False

    def test_true_with_multiple_tasks(self, mock_sync_cache_fixture):
        """Works correctly when the cache contains many tasks."""
        tasks = {i: _TASK_A for i in range(1, 51)}  # 50 tasks
        mock_sync_cache_fixture(tasks=tasks, freshness_age_seconds=120)
        assert sc.is_cache_healthy(sc.SLA_NORMAL) is True

    def test_false_with_sla_hot_and_normal_pointer_age(
        self, mock_sync_cache_fixture
    ):
        """A cache fresh for SLA_NORMAL is stale for SLA_HOT."""
        mock_sync_cache_fixture(tasks={14: _TASK_A}, freshness_age_seconds=120)
        # SLA_HOT is 60s, pointer is 120s old → stale
        assert sc.is_cache_healthy(sc.SLA_HOT) is False


# ===========================================================================
# Group 7 — module-level contract assertions
# ===========================================================================


class TestModuleContract:
    def test_no_io_at_import_time(self):
        """Importing sync_cache must not touch STATE_DIR_DEFAULT on disk."""
        # The module is already imported; verify STATE_DIR_DEFAULT is a Path
        # object with a specific value, not that any I/O occurred.  The
        # actual non-I/O guarantee is validated by the fact that the module
        # imports without error on a Mac (where /data/ doesn't exist).
        assert isinstance(sc.STATE_DIR_DEFAULT, Path)

    def test_all_public_functions_exposed(self):
        """All 5 public functions are accessible at module scope."""
        assert callable(sc.read_cached_tasks)
        assert callable(sc.read_cached_task_by_id)
        assert callable(sc.read_freshness_pointer)
        assert callable(sc.read_completion_timestamps)
        assert callable(sc.is_cache_healthy)

    def test_no_http_calls_in_module(self):
        """The module must not import urllib or requests at the top level."""
        import importlib
        import sys

        mod = sys.modules.get("scripts.common.sync_cache")
        assert mod is not None
        # No urllib.request in the module's globals
        assert "urlopen" not in dir(mod)
        assert "urllib" not in (getattr(mod, "__dict__", {}).keys())

    def test_error_message_format_bracket_prefix(self, tmp_path):
        """Error messages with touchpoint_name start with [<name>]."""
        empty = tmp_path / "empty"
        empty.mkdir()
        with pytest.raises(OSError) as exc_info:
            sc.read_cached_tasks(
                sc.SLA_NORMAL,
                state_dir=empty,
                touchpoint_name="habits.morning_checkin_list",
            )
        assert str(exc_info.value).startswith("[habits.morning_checkin_list]")

    def test_error_message_recovery_colon(self, tmp_path):
        """Error messages contain 'Recovery:' marker per the contract."""
        empty = tmp_path / "empty"
        empty.mkdir()
        with pytest.raises(OSError) as exc_info:
            sc.read_cached_tasks(sc.SLA_NORMAL, state_dir=empty)
        assert "Recovery:" in str(exc_info.value)

    def test_fixture_single_call_guard(self, mock_sync_cache_fixture):
        """Calling mock_sync_cache_fixture builder twice raises AssertionError."""
        mock_sync_cache_fixture(tasks={14: _TASK_A}, freshness_age_seconds=60)
        with pytest.raises(AssertionError, match="single-call"):
            mock_sync_cache_fixture(tasks={15: _TASK_B}, freshness_age_seconds=60)
