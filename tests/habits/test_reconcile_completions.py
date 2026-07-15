"""Tests for scripts/habits/reconcile_completions.py (WP03 / T012).

Covers the ``reconcile()`` Python API and the ``__main__`` CLI surface.
Task enumeration is mocked via ``mock_sync_cache_fixture`` (WP01 fixture).
Completion timestamps are mocked via ``mock_state_log_fixture`` (WP01 fixture).
State-log I/O for backfill writes is sandboxed via the ``mock_state_log_dir``
fixture.

Test groups:

1. Backfill — cache says done=true + state log has completion event → backfill JSONL.
2. Cache done + state log EMPTY — operator-side completion detected (no date → error).
3. Cache NOT done + state log empty — no action.
4. Cache NOT done + state log has stale complete — drift detected.
5. Agreement matrix — all four cache/state-log combinations.
6. CLI exit codes and output format.
7. Private task skipped in bulk enumeration.
8. Cache staleness / missing → OSError → exit 3.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.common import state_log
from scripts.habits import reconcile_completions as rec

# Re-export fixtures from common conftest so pytest can discover them.
from tests.common.conftest import mock_state_log_fixture  # noqa: F401
from tests.common.conftest import mock_sync_cache_fixture  # noqa: F401


# ---------------------------------------------------------------------------
# Test constants
# ---------------------------------------------------------------------------

HABITS_PROJECT_ID = rec.HABITS_PROJECT_ID  # registry-sourced (13 today)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _task_fields(
    *,
    task_id: int,
    title: str = "Habit task",
    done: bool = False,
    project_id: int = HABITS_PROJECT_ID,
    due_date: str | None = None,
) -> dict:
    """Return a field dict suitable for mock_sync_cache_fixture ``tasks``."""
    return {
        "title": title,
        "done": done,
        "project_id": project_id,
        "due_date": due_date,
        "repeat_after": 0,
        "repeat_mode": "default",
        "labels": [],
    }


# ===========================================================================
# Group 1 — Backfill direction (cache done + state log has completion)
# ===========================================================================


class TestBackfill:
    def test_cache_done_with_state_log_entry_backfills_jsonl(
        self,
        mock_sync_cache_fixture,
        mock_state_log_fixture,
        mock_state_log_dir,
    ):
        """Cache done=true; read_completion_timestamps finds date; JSONL sandbox
        is empty → backfill fires and writes the record.

        ``mock_state_log_fixture`` provides the completion event so that
        ``read_completion_timestamps`` can derive the date. The sandboxed
        ``STATE_DIR`` (via ``mock_state_log_dir``) starts empty, so
        ``state_log.read()`` finds no existing entry and backfill fires.
        """
        task_id = 14
        mock_sync_cache_fixture(
            tasks={task_id: _task_fields(task_id=task_id, done=True, title="Wake")},
        )
        log_path = mock_state_log_fixture(
            domain="habits",
            entries=[{
                "domain": "habits",
                "task_id": task_id,
                "title": "Wake",
                "date": "2026-05-19",
                "state": "complete",
                "source": "whatsapp",
                "timestamp": "2026-05-19T11:00:00+00:00",
            }],
        )

        result = rec.reconcile(
            today="2026-05-20",
            state_log_dir=log_path.parent,
        )

        assert result["tasks_examined"] == 1
        # Backfill fires: read_completion_timestamps derived the date from the
        # fixture, but STATE_DIR sandbox is empty so state_log.read() finds no
        # existing entry → one backfill record written.
        assert len(result["backfilled"]) == 1
        assert result["backfilled"][0]["task_id"] == task_id
        assert result["backfilled"][0]["date"] == "2026-05-19"
        assert len(result["errors"]) == 0

    def test_cache_done_with_state_log_entry_no_duplicate_backfill(
        self,
        mock_sync_cache_fixture,
        mock_state_log_fixture,
        mock_state_log_dir,
    ):
        """If JSONL already has the complete entry, no backfill is appended."""
        task_id = 14
        mock_sync_cache_fixture(
            tasks={task_id: _task_fields(task_id=task_id, done=True, title="Wake")},
        )
        log_path = mock_state_log_fixture(
            domain="habits",
            entries=[{
                "domain": "habits",
                "task_id": task_id,
                "title": "Wake",
                "date": "2026-05-19",
                "state": "complete",
                "source": "whatsapp",
                "timestamp": "2026-05-19T11:00:00+00:00",
            }],
        )
        # Pre-seed the state_log sandbox with the same record.
        state_log.append(
            "habits",
            {
                "domain": "habits",
                "task_id": task_id,
                "title": "Wake",
                "date": "2026-05-19",
                "state": "complete",
                "source": "whatsapp",
                "timestamp": "2026-05-19T11:00:00+00:00",
            },
        )

        result = rec.reconcile(
            today="2026-05-20",
            state_log_dir=log_path.parent,
        )

        assert result["backfilled"] == []
        records = state_log.read("habits", task_id=task_id)
        # Only the pre-seeded record; reconcile did not add a duplicate.
        assert len(records) == 1


# ===========================================================================
# Group 2 — Cache done + state log EMPTY (operator-side completion, no date)
# ===========================================================================


class TestCacheDoneStateLogEmpty:
    def test_cache_done_no_state_log_entry_reports_error(
        self,
        mock_sync_cache_fixture,
        mock_state_log_fixture,
        mock_state_log_dir,
    ):
        """Cache done=true, state log has NO completion event → error (can't derive date)."""
        task_id = 14
        mock_sync_cache_fixture(
            tasks={task_id: _task_fields(task_id=task_id, done=True, title="Wake")},
        )
        # State log is empty for this task.
        log_path = mock_state_log_fixture(domain="habits", entries=[])

        result = rec.reconcile(
            today="2026-05-20",
            state_log_dir=log_path.parent,
        )

        assert result["tasks_examined"] == 1
        assert result["backfilled"] == []
        assert len(result["errors"]) == 1
        assert "done=true in cache but no completion event" in result["errors"][0]["message"]
        assert result["errors"][0]["task_id"] == task_id


# ===========================================================================
# Group 3 — Cache NOT done + state log empty → no action
# ===========================================================================


class TestCacheNotDoneStateLogEmpty:
    def test_cache_not_done_empty_state_log_no_action(
        self,
        mock_sync_cache_fixture,
        mock_state_log_fixture,
        mock_state_log_dir,
    ):
        """Cache done=false, state log empty → no backfill, no drift, no error."""
        task_id = 14
        mock_sync_cache_fixture(
            tasks={task_id: _task_fields(task_id=task_id, done=False, title="Wake")},
        )
        log_path = mock_state_log_fixture(domain="habits", entries=[])

        result = rec.reconcile(
            today="2026-05-20",
            state_log_dir=log_path.parent,
        )

        assert result["tasks_examined"] == 1
        assert result["backfilled"] == []
        assert result["drift"] == []
        assert result["errors"] == []


# ===========================================================================
# Group 4 — Drift direction (JSONL says complete for today, cache says done=false)
# ===========================================================================


class TestDrift:
    def test_drift_reported_when_jsonl_complete_but_cache_not_done(
        self,
        mock_sync_cache_fixture,
        mock_state_log_fixture,
        mock_state_log_dir,
    ):
        """JSONL has complete for today; cache shows done=false → drift reported."""
        task_id = 14
        mock_sync_cache_fixture(
            tasks={task_id: _task_fields(task_id=task_id, done=False, title="Wake")},
        )
        # Seed the state_log sandbox.
        state_log.append(
            "habits",
            {
                "domain": "habits",
                "task_id": task_id,
                "title": "Wake",
                "date": "2026-05-20",
                "state": "complete",
                "source": "whatsapp",
                "timestamp": "2026-05-20T11:00:00+00:00",
            },
        )
        log_path = mock_state_log_fixture(domain="habits", entries=[])  # not used for drift check

        result = rec.reconcile(
            today="2026-05-20",
            state_log_dir=log_path.parent,
        )

        assert len(result["drift"]) == 1
        d = result["drift"][0]
        assert d["task_id"] == task_id
        assert d["title"] == "Wake"
        assert d["date"] == "2026-05-20"
        assert d["vikunja_done"] is False
        # Drift is informational — no mutation.
        records = state_log.read("habits", task_id=task_id)
        assert len(records) == 1

    def test_no_drift_when_jsonl_lacks_complete_for_today(
        self,
        mock_sync_cache_fixture,
        mock_state_log_fixture,
        mock_state_log_dir,
    ):
        """JSONL has complete for a DIFFERENT date → no drift."""
        task_id = 14
        mock_sync_cache_fixture(
            tasks={task_id: _task_fields(task_id=task_id, done=False, title="Wake")},
        )
        # Complete record for a different date.
        state_log.append(
            "habits",
            {
                "domain": "habits",
                "task_id": task_id,
                "title": "Wake",
                "date": "2026-05-18",
                "state": "complete",
                "source": "whatsapp",
                "timestamp": "2026-05-18T11:00:00+00:00",
            },
        )
        log_path = mock_state_log_fixture(domain="habits", entries=[])

        result = rec.reconcile(
            today="2026-05-20",
            state_log_dir=log_path.parent,
        )

        assert result["drift"] == []


# ===========================================================================
# Group 5 — Agreement matrix (end-to-end)
# ===========================================================================


class TestAgreementMatrix:
    """Four (cache_done, state_log_complete) combinations."""

    def test_both_agree_done(
        self,
        mock_sync_cache_fixture,
        mock_state_log_fixture,
        mock_state_log_dir,
    ):
        """Cache done + state log has complete → no action (already in sync)."""
        task_id = 14
        mock_sync_cache_fixture(
            tasks={task_id: _task_fields(task_id=task_id, done=True)},
        )
        state_log.append(
            "habits",
            {
                "domain": "habits",
                "task_id": task_id,
                "title": "Wake",
                "date": "2026-05-19",
                "state": "complete",
                "source": "whatsapp",
                "timestamp": "2026-05-19T11:00:00+00:00",
            },
        )
        log_path = mock_state_log_fixture(
            domain="habits",
            entries=[{
                "domain": "habits",
                "task_id": task_id,
                "title": "Wake",
                "date": "2026-05-19",
                "state": "complete",
                "source": "whatsapp",
                "timestamp": "2026-05-19T11:00:00+00:00",
            }],
        )

        result = rec.reconcile(today="2026-05-20", state_log_dir=log_path.parent)

        assert result["backfilled"] == []
        assert result["drift"] == []
        assert result["errors"] == []

    def test_cache_done_state_log_empty_reports_error(
        self,
        mock_sync_cache_fixture,
        mock_state_log_fixture,
        mock_state_log_dir,
    ):
        """Cache done + state log empty → error (cannot derive completion date)."""
        task_id = 14
        mock_sync_cache_fixture(
            tasks={task_id: _task_fields(task_id=task_id, done=True)},
        )
        log_path = mock_state_log_fixture(domain="habits", entries=[])

        result = rec.reconcile(today="2026-05-20", state_log_dir=log_path.parent)

        assert len(result["errors"]) == 1
        assert "done=true in cache but no completion event" in result["errors"][0]["message"]

    def test_cache_not_done_state_log_empty_no_action(
        self,
        mock_sync_cache_fixture,
        mock_state_log_fixture,
        mock_state_log_dir,
    ):
        """Cache not done + state log empty → no action (both agree: not done)."""
        task_id = 14
        mock_sync_cache_fixture(
            tasks={task_id: _task_fields(task_id=task_id, done=False)},
        )
        log_path = mock_state_log_fixture(domain="habits", entries=[])

        result = rec.reconcile(today="2026-05-20", state_log_dir=log_path.parent)

        assert result["backfilled"] == []
        assert result["drift"] == []
        assert result["errors"] == []

    def test_cache_not_done_state_log_complete_today_drift(
        self,
        mock_sync_cache_fixture,
        mock_state_log_fixture,
        mock_state_log_dir,
    ):
        """Cache not done + state log has complete for today → drift detected."""
        task_id = 14
        mock_sync_cache_fixture(
            tasks={task_id: _task_fields(task_id=task_id, done=False, title="Wake")},
        )
        state_log.append(
            "habits",
            {
                "domain": "habits",
                "task_id": task_id,
                "title": "Wake",
                "date": "2026-05-20",
                "state": "complete",
                "source": "whatsapp",
                "timestamp": "2026-05-20T11:00:00+00:00",
            },
        )
        log_path = mock_state_log_fixture(domain="habits", entries=[])

        result = rec.reconcile(today="2026-05-20", state_log_dir=log_path.parent)

        assert len(result["drift"]) == 1
        assert result["drift"][0]["task_id"] == task_id


# ===========================================================================
# Group 6 — Non-habits tasks skipped
# ===========================================================================


class TestProjectScoping:
    def test_non_habits_project_task_skipped(
        self,
        mock_sync_cache_fixture,
        mock_state_log_fixture,
        mock_state_log_dir,
    ):
        """Tasks from other projects are excluded from reconcile."""
        task_id = 99
        mock_sync_cache_fixture(
            tasks={task_id: _task_fields(
                task_id=task_id, done=True, project_id=99  # not HABITS_PROJECT_ID
            )},
        )
        log_path = mock_state_log_fixture(domain="habits", entries=[])

        result = rec.reconcile(today="2026-05-20", state_log_dir=log_path.parent)

        assert result["tasks_examined"] == 0
        assert result["backfilled"] == []
        assert result["errors"] == []


# ===========================================================================
# Group 7 — Private task skipped
# ===========================================================================


class TestPrivateTask:
    def test_private_task_skipped_in_bulk_enumeration(
        self,
        mock_sync_cache_fixture,
        mock_state_log_fixture,
        mock_state_log_dir,
    ):
        """Private tasks are skipped; is_private check is applied early."""
        task_id = 14
        private_project_id = 42
        mock_sync_cache_fixture(
            tasks={task_id: {
                "title": "Private habit",
                "done": True,
                "project_id": private_project_id,
                "repeat_after": 0,
                "repeat_mode": "default",
                "labels": [],
            }},
            private_project_ids=frozenset({private_project_id}),
        )
        log_path = mock_state_log_fixture(domain="habits", entries=[])

        result = rec.reconcile(today="2026-05-20", state_log_dir=log_path.parent)

        # Private task is skipped entirely.
        assert result["tasks_examined"] == 0
        assert result["backfilled"] == []
        assert result["errors"] == []


# ===========================================================================
# Group 8 — Cache staleness → OSError
# ===========================================================================


class TestCacheStale:
    def test_stale_cache_raises_oserror(
        self,
        mock_sync_cache_fixture,
        mock_state_log_fixture,
        mock_state_log_dir,
    ):
        """Cache freshness pointer older than SLA_NORMAL → OSError from helper."""
        task_id = 14
        mock_sync_cache_fixture(
            tasks={task_id: _task_fields(task_id=task_id, done=False)},
            freshness_age_seconds=9999,  # far beyond SLA_NORMAL (900s)
        )
        log_path = mock_state_log_fixture(domain="habits", entries=[])

        with pytest.raises(OSError, match="stale"):
            rec.reconcile(today="2026-05-20", state_log_dir=log_path.parent)

    def test_missing_cache_raises_oserror(self, tmp_path, mock_state_log_dir):
        """No cache at all → OSError with 'freshness pointer missing'."""
        with pytest.raises(OSError, match="freshness pointer missing"):
            rec.reconcile(today="2026-05-20", state_log_dir=tmp_path)


# ===========================================================================
# Group 9 — CLI surface
# ===========================================================================


class TestCli:
    def test_help_exits_zero(self, capsys):
        with pytest.raises(SystemExit) as exc:
            rec.main(["--help"])
        assert exc.value.code == 0

    def test_cli_exit_zero_with_drift(
        self,
        mock_sync_cache_fixture,
        mock_state_log_fixture,
        mock_state_log_dir,
        capsys,
    ):
        """Drift is informational — CLI exits 0 even when drift count > 0."""
        task_id = 14
        mock_sync_cache_fixture(
            tasks={task_id: _task_fields(task_id=task_id, done=False, title="Wake")},
        )
        state_log.append(
            "habits",
            {
                "domain": "habits",
                "task_id": task_id,
                "title": "Wake",
                "date": "2026-05-20",
                "state": "complete",
                "source": "whatsapp",
                "timestamp": "2026-05-20T11:00:00+00:00",
            },
        )
        log_path = mock_state_log_fixture(domain="habits", entries=[])

        exit_code = rec.main([
            "--today", "2026-05-20",
            "--state-log-dir", str(log_path.parent),
        ])

        assert exit_code == 0
        out = capsys.readouterr().out
        assert "DRIFT" in out
        assert "drift: 1" in out

    def test_cli_exit_zero_no_drift_no_backfill(
        self,
        mock_sync_cache_fixture,
        mock_state_log_fixture,
        mock_state_log_dir,
        capsys,
    ):
        """No tasks → exit 0 with tasks_examined: 0."""
        mock_sync_cache_fixture(tasks={})
        log_path = mock_state_log_fixture(domain="habits", entries=[])

        exit_code = rec.main([
            "--today", "2026-05-20",
            "--state-log-dir", str(log_path.parent),
        ])

        assert exit_code == 0
        out = capsys.readouterr().out
        assert "tasks_examined: 0" in out
        assert "backfilled: 0" in out
        assert "drift: 0" in out

    def test_cli_bad_today_exits_two(
        self,
        mock_sync_cache_fixture,
        mock_state_log_fixture,
        mock_state_log_dir,
        capsys,
    ):
        """Invalid --today format → exit 2."""
        mock_sync_cache_fixture(tasks={})
        log_path = mock_state_log_fixture(domain="habits", entries=[])

        exit_code = rec.main([
            "--today", "5/15/2026",
            "--state-log-dir", str(log_path.parent),
        ])

        assert exit_code == 2
        err = capsys.readouterr().err
        assert "YYYY-MM-DD" in err

    def test_cli_stale_cache_exits_one(
        self,
        mock_sync_cache_fixture,
        mock_state_log_fixture,
        mock_state_log_dir,
        capsys,
    ):
        """Stale cache → OSError → exit 1."""
        task_id = 14
        mock_sync_cache_fixture(
            tasks={task_id: _task_fields(task_id=task_id, done=False)},
            freshness_age_seconds=9999,
        )
        log_path = mock_state_log_fixture(domain="habits", entries=[])

        exit_code = rec.main([
            "--today", "2026-05-20",
            "--state-log-dir", str(log_path.parent),
        ])

        assert exit_code == 1
        err = capsys.readouterr().err
        assert "reconcile failed" in err
