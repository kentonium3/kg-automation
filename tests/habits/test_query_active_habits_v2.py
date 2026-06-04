"""Tests for scripts/habits/query_active_habits_v2.py (WP02 / T005-T006).

TP-03 migration: all GET-side tests now use ``mock_sync_cache_fixture``
from ``tests/common/conftest.py``. No ``mock_urlopen`` for the read path.

Test groups:

1. Happy path — active tasks returned from the cache.
2. Cache failure modes — missing, stale (each raises OSError → CLI exit 3).
3. Private-project tasks — skipped (bulk enumeration does NOT raise per EC-7).
4. Empty cache — returns empty list.
5. today override / default UTC today.
6. CLI stdout format — JSONL, one task per line.
7. Day-of-week filter (schedule_path) — still works after cache migration.
8. Misc.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.habits import query_active_habits_v2 as qv2


# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------

#: Habits project_id used across tests.
HABITS_PROJECT_ID = 42

#: A non-habits project_id (Inbox, Goals, etc.).
OTHER_PROJECT_ID = 7


def _task_fields(
    title: str = "Habit",
    due_date: str = "2026-05-20T08:00:00Z",
    done: bool = False,
    repeat_after: int = 86400,
    repeat_mode: str = "default",
    project_id: int = HABITS_PROJECT_ID,
    labels: list | None = None,
) -> dict:
    """Return a dict of TRACKED_TASK_FIELDS for one task."""
    return {
        "title": title,
        "due_date": due_date,
        "done": done,
        "repeat_after": repeat_after,
        "repeat_mode": repeat_mode,
        "project_id": project_id,
        "labels": labels or [],
    }


def _write_schedule(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "schedule.yaml"
    p.write_text(body, encoding="utf-8")
    return p


# ===========================================================================
# Group 1 — Happy path
# ===========================================================================


class TestHappyPath:
    def test_returns_active_tasks_from_cache(self, mock_sync_cache_fixture):
        """Three active habit tasks are returned from the cache."""
        mock_sync_cache_fixture(
            tasks={
                14: _task_fields(title="Wake at 5:00 AM"),
                15: _task_fields(title="Drink water"),
                16: _task_fields(title="Meditate"),
            },
        )
        result = qv2.query_active_today(today="2026-05-20")
        assert len(result) == 3
        ids = {t["id"] for t in result}
        assert ids == {14, 15, 16}

    def test_excludes_done_tasks(self, mock_sync_cache_fixture):
        """Done tasks are excluded; active ones pass through."""
        mock_sync_cache_fixture(
            tasks={
                14: _task_fields(title="Active", done=False),
                15: _task_fields(title="Done", done=True),
            },
        )
        result = qv2.query_active_today(today="2026-05-20")
        assert len(result) == 1
        assert result[0]["id"] == 14

    def test_excludes_future_due_date(self, mock_sync_cache_fixture):
        """Tasks with due_date > today boundary are excluded."""
        mock_sync_cache_fixture(
            tasks={
                14: _task_fields(title="Today", due_date="2026-05-20T08:00:00Z"),
                15: _task_fields(title="Tomorrow", due_date="2026-05-21T00:00:00Z"),
            },
        )
        result = qv2.query_active_today(today="2026-05-20")
        ids = [t["id"] for t in result]
        assert 14 in ids
        assert 15 not in ids

    def test_return_shape_has_expected_fields(self, mock_sync_cache_fixture):
        """Each returned dict has the expected fields."""
        mock_sync_cache_fixture(
            tasks={14: _task_fields(title="Wake at 5:00 AM")},
        )
        result = qv2.query_active_today(today="2026-05-20")
        assert len(result) == 1
        task = result[0]
        assert task["id"] == 14
        assert task["title"] == "Wake at 5:00 AM"
        assert "due_date" in task
        assert "done" in task
        assert "repeat_after" in task
        assert "project_id" in task
        assert "labels" in task


# ===========================================================================
# Group 2 — Cache failure modes
# ===========================================================================


class TestCacheFailureModes:
    def test_cache_missing_raises_oserror(self, mock_sync_cache_fixture, tmp_path, monkeypatch):
        """When no cache exists, read_cached_tasks raises OSError."""
        # Point to an empty directory — no cache files.
        monkeypatch.setattr("scripts.common.sync_cache.STATE_DIR_DEFAULT", tmp_path / "empty")
        monkeypatch.setattr("scripts.sync.state.STATE_DIR_DEFAULT", tmp_path / "empty")
        with pytest.raises(OSError) as exc_info:
            qv2.query_active_today(today="2026-05-20")
        assert "freshness pointer missing" in str(exc_info.value)

    def test_cache_missing_cli_exits_3(self, tmp_path, monkeypatch, capsys):
        """CLI exits 3 with [habits.query_active_habits_v2] prefix when cache missing."""
        monkeypatch.setattr("scripts.common.sync_cache.STATE_DIR_DEFAULT", tmp_path / "empty")
        monkeypatch.setattr("scripts.sync.state.STATE_DIR_DEFAULT", tmp_path / "empty")
        exit_code = qv2.main(["--today", "2026-05-20"])
        assert exit_code == 3
        err = capsys.readouterr().err
        assert "[habits.query_active_habits_v2]" in err

    def test_stale_cache_raises_oserror(self, mock_sync_cache_fixture):
        """Cache older than SLA_NORMAL (900s) raises OSError with 'stale' message."""
        mock_sync_cache_fixture(
            tasks={14: _task_fields()},
            freshness_age_seconds=1500,  # > 900s SLA_NORMAL
        )
        with pytest.raises(OSError) as exc_info:
            qv2.query_active_today(today="2026-05-20")
        assert "stale beyond SLA_NORMAL" in str(exc_info.value)

    def test_stale_cache_cli_exits_3(self, mock_sync_cache_fixture, capsys):
        """CLI exits 3 when cache is stale."""
        mock_sync_cache_fixture(
            tasks={14: _task_fields()},
            freshness_age_seconds=1500,
        )
        exit_code = qv2.main(["--today", "2026-05-20"])
        assert exit_code == 3
        err = capsys.readouterr().err
        assert "[habits.query_active_habits_v2]" in err


# ===========================================================================
# Group 3 — Private-project tasks skipped (EC-7)
# ===========================================================================


class TestPrivateProjectSkip:
    def test_private_tasks_skipped_not_raised(self, mock_sync_cache_fixture):
        """Private-project tasks are skipped in bulk enumeration (EC-7).

        Per migration-pattern EC-7, ``read_cached_tasks`` returns private
        entries with ``is_private=True`` and the touchpoint skips them
        rather than raising. This differs from ``read_cached_task_by_id``
        which DOES raise on private.
        """
        PRIVATE_PROJECT_ID = 99
        mock_sync_cache_fixture(
            tasks={
                100: _task_fields(title="Private habit", project_id=PRIVATE_PROJECT_ID),
                14: _task_fields(title="Normal habit"),
                15: _task_fields(title="Another normal"),
            },
            private_project_ids=frozenset({PRIVATE_PROJECT_ID}),
        )
        result = qv2.query_active_today(today="2026-05-20")
        ids = {t["id"] for t in result}
        # Private task skipped, normals returned.
        assert 100 not in ids
        assert 14 in ids
        assert 15 in ids


# ===========================================================================
# Group 4 — Empty cache
# ===========================================================================


class TestEmptyCache:
    def test_empty_cache_returns_empty_list(self, mock_sync_cache_fixture):
        """An empty cache (no tasks) returns an empty list."""
        mock_sync_cache_fixture(tasks={})
        result = qv2.query_active_today(today="2026-05-20")
        assert result == []


# ===========================================================================
# Group 5 — today override / default
# ===========================================================================


class TestTodayOverride:
    def test_today_kwarg_drives_client_side_boundary(self, mock_sync_cache_fixture):
        """The explicit today override is applied as the client-side filter boundary."""
        mock_sync_cache_fixture(
            tasks={
                1: _task_fields(title="Before", due_date="2026-05-15T08:00:00Z"),
                2: _task_fields(title="After", due_date="2026-05-16T00:00:00Z"),
            },
        )
        result = qv2.query_active_today(today="2026-05-15")
        ids = [t["id"] for t in result]
        assert 1 in ids
        assert 2 not in ids

    def test_today_bad_format_raises_value_error(self, mock_sync_cache_fixture):
        """A bad --today value raises ValueError before touching the cache."""
        mock_sync_cache_fixture(tasks={})
        with pytest.raises(ValueError, match="YYYY-MM-DD"):
            qv2.query_active_today(today="5/15/2026")

    def test_today_none_uses_utc_today(self, mock_sync_cache_fixture):
        """When today is None, the helper uses the system UTC date (no crash)."""
        mock_sync_cache_fixture(tasks={})
        result = qv2.query_active_today()
        assert isinstance(result, list)


# ===========================================================================
# Group 6 — CLI stdout format
# ===========================================================================


class TestCliStdoutFormat:
    def test_three_tasks_emitted_as_jsonl(self, mock_sync_cache_fixture, capsys):
        """Three active tasks are emitted as JSONL on stdout."""
        mock_sync_cache_fixture(
            tasks={
                14: _task_fields(title="Wake at 5:00 AM"),
                15: _task_fields(title="Drink water"),
                16: _task_fields(title="Meditate"),
            },
        )
        exit_code = qv2.main(["--today", "2026-05-20"])
        assert exit_code == 0
        out = capsys.readouterr().out
        lines = [ln for ln in out.splitlines() if ln.strip()]
        assert len(lines) == 3
        for line in lines:
            obj = json.loads(line)
            assert "id" in obj
            assert "title" in obj

    def test_empty_cache_emits_no_stdout(self, mock_sync_cache_fixture, capsys):
        """Empty cache emits no stdout; exit 0."""
        mock_sync_cache_fixture(tasks={})
        exit_code = qv2.main(["--today", "2026-05-20"])
        assert exit_code == 0
        out = capsys.readouterr().out
        assert out == ""

    def test_cli_bad_today_exits_two(self, mock_sync_cache_fixture, capsys):
        """A malformed --today value exits 2."""
        mock_sync_cache_fixture(tasks={})
        exit_code = qv2.main(["--today", "5/15/2026"])
        assert exit_code == 2
        err = capsys.readouterr().err
        assert "YYYY-MM-DD" in err


# ===========================================================================
# Group 7 — Day-of-week filter (schedule_path) works after cache migration
# ===========================================================================


class TestDayOfWeekFilter:
    SCHEDULE = """
habits:
  - task_id: 14
    title: "Wake"
    repeat_after_seconds: 86400
  - task_id: 77
    title: "Friday strength"
    designated_weekdays: ["Fri"]
    repeat_after_seconds: 604800
  - task_id: 76
    title: "Wed strength"
    designated_weekdays: ["Wed"]
    repeat_after_seconds: 604800
"""

    def test_day_specific_included_on_designated_day(
        self, tmp_path, mock_sync_cache_fixture
    ):
        """Friday-only habit is included on Friday (2026-05-22)."""
        schedule = _write_schedule(tmp_path, self.SCHEDULE)
        mock_sync_cache_fixture(
            tasks={
                14: _task_fields(title="Wake"),
                77: _task_fields(title="Friday strength"),
                76: _task_fields(title="Wed strength"),
            },
        )
        result = qv2.query_active_today(
            today="2026-05-22",  # Fri
            schedule_path=schedule,
        )
        ids = sorted(t["id"] for t in result)
        # Wake (daily) + Fri strength (today is Fri) — Wed strength excluded.
        assert ids == [14, 77]

    def test_day_specific_excluded_on_other_day(
        self, tmp_path, mock_sync_cache_fixture
    ):
        """Friday-only habit excluded on Wednesday (2026-05-20)."""
        schedule = _write_schedule(tmp_path, self.SCHEDULE)
        mock_sync_cache_fixture(
            tasks={
                14: _task_fields(title="Wake"),
                77: _task_fields(title="Friday strength"),
                76: _task_fields(title="Wed strength"),
            },
        )
        result = qv2.query_active_today(
            today="2026-05-20",  # Wed
            schedule_path=schedule,
        )
        ids = sorted(t["id"] for t in result)
        assert ids == [14, 76]

    def test_no_schedule_path_returns_all_candidates(self, mock_sync_cache_fixture):
        """Without schedule_path, all candidates flow through unchanged."""
        mock_sync_cache_fixture(
            tasks={
                14: _task_fields(title="Wake"),
                77: _task_fields(title="Fri strength"),
            },
        )
        result = qv2.query_active_today(today="2026-05-20")  # Wed, no schedule
        ids = {t["id"] for t in result}
        assert ids == {14, 77}

    def test_unscheduled_habit_passes_with_warning(
        self, tmp_path, mock_sync_cache_fixture, capsys
    ):
        """A habit not in schedule.yaml is included (daily fallback) with stderr warn."""
        schedule = _write_schedule(
            tmp_path,
            """
habits:
  - task_id: 100
    title: "Known"
    repeat_after_seconds: 86400
""",
        )
        mock_sync_cache_fixture(
            tasks={
                100: _task_fields(title="Known"),
                999: _task_fields(title="Stranger"),
            },
        )
        result = qv2.query_active_today(today="2026-05-20", schedule_path=schedule)
        ids = {t["id"] for t in result}
        assert 999 in ids  # passed through
        err = capsys.readouterr().err
        assert "WARN" in err
        assert "999" in err


# ===========================================================================
# Group 8 — Misc
# ===========================================================================


class TestMisc:
    def test_help_exits_zero(self):
        with pytest.raises(SystemExit) as exc:
            qv2.main(["--help"])
        assert exc.value.code == 0

    def test_touchpoint_constants_set(self):
        """Module-level TOUCHPOINT_SLA and TOUCHPOINT_NAME are correct."""
        from scripts.common.sync_cache import SLA_NORMAL
        assert qv2.TOUCHPOINT_SLA is SLA_NORMAL
        assert qv2.TOUCHPOINT_NAME == "habits.query_active_habits_v2"

    def test_no_urlopen_calls_on_happy_path(self, mock_sync_cache_fixture):
        """The global HTTP guard from tests/conftest.py must not fire."""
        # The global _block_live_http fixture raises RuntimeError on urlopen.
        # If this test passes, no urlopen call was made during the cache read.
        mock_sync_cache_fixture(
            tasks={14: _task_fields(title="Wake")},
        )
        result = qv2.query_active_today(today="2026-05-20")
        assert len(result) == 1  # cache served correctly
