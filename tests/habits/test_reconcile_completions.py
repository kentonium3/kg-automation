"""Tests for scripts/habits/reconcile_completions.py (WP03 / T012).

Covers the ``reconcile()`` Python API and the ``__main__`` CLI surface.
All Vikunja HTTP traffic is mocked via ``urllib.request.urlopen``; state_log
I/O is sandboxed via the ``mock_state_log_dir`` fixture from conftest.

Cycle 2: enumeration is now project-scoped to the Habits project. Each
reconcile call makes **two** HTTP requests in order:

  1. ``GET /projects`` -- resolve the Habits project id by title.
  2. ``GET /projects/<id>/tasks?filter=is_archived=false`` -- list tasks.

Tests use ``_responses(tasks=...)`` to script both responses in order via
``mock_urlopen.side_effect``.

Test groups:

1. Backfill — Vikunja UI completion that has no JSONL entry yet.
2. No backfill needed — JSONL already records the completion.
3. Drift — JSONL says complete for today but Vikunja still done=false.
4. Zero-sentinel done_at — Vikunja returns ``0001-01-01T00:00:00Z`` for
   tasks done=true with no real timestamp; treated as "no date" + reported
   in errors, NOT backfilled.
5. today-override — ``--today`` flag (and ``today=`` kwarg) overrides UTC
   system clock for drift comparison.
6. CLI exit 0 even when drift detected.
7. CLI exit 1 on enumerate failure.
8. _done_at_date unit edge cases.
9. Project scoping — regression test that the enumerate path is
   project-scoped to Habits (Cycle 2 fix).
"""
from __future__ import annotations

import io
import json
import sys
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.common import state_log
from scripts.habits import reconcile_completions as rec


# ---------------------------------------------------------------------------
# Local mocking helpers
# ---------------------------------------------------------------------------


def _resp(payload, *, status: int = 200):
    """Return a context-manager-compatible mock urlopen response."""
    body = json.dumps(payload).encode("utf-8") if payload is not None else b""
    resp = MagicMock(name="response")
    resp.status = status
    resp.read = MagicMock(return_value=body)
    cm = MagicMock(name="cm")
    cm.__enter__ = MagicMock(return_value=resp)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


#: The Habits project id used across tests. Tests do not depend on a
#: specific value -- the project lookup mock simply returns this id and the
#: enumerate call URL is asserted to include it where relevant.
HABITS_PROJECT_ID = 42


def _projects_payload(project_id: int = HABITS_PROJECT_ID):
    """Return a Vikunja-shaped ``GET /projects`` payload with a Habits project."""
    return [
        {"id": 1, "title": "Inbox"},
        {"id": project_id, "title": "Habits"},
        {"id": 99, "title": "Goals"},
    ]


def _responses(tasks, *, projects=None):
    """Build a list of urlopen responses scripting (projects -> tasks).

    Use via ``mock_urlopen.side_effect = _responses(tasks=[...])``.
    """
    if projects is None:
        projects = _projects_payload()
    return [_resp(projects), _resp(tasks)]


def _http_error(code: int = 500, body: bytes = b'{"message":"boom"}'):
    return urllib.error.HTTPError(
        url="http://test/",
        code=code,
        msg="Server Error",
        hdrs=None,
        fp=io.BytesIO(body),
    )


def _task(
    task_id: int,
    title: str = "Habit",
    done: bool = False,
    done_at: str | None = None,
    is_archived: bool = False,
) -> dict:
    return {
        "id": task_id,
        "title": title,
        "done": done,
        "done_at": done_at,
        "is_archived": is_archived,
    }


# ===========================================================================
# Group 1 — Backfill direction
# ===========================================================================


class TestBackfill:
    def test_backfill_appends_record_with_source_vikunja_ui(
        self, mock_urlopen, mock_state_log_dir
    ):
        mock_urlopen.side_effect = _responses(tasks=[
            _task(
                14,
                title="Wake at 5:00 AM",
                done=True,
                done_at="2026-05-19T11:00:00Z",
            ),
        ])

        result = rec.reconcile(
            api_base_url="http://test/api/v1/",
            token="t",
            today="2026-05-20",
        )

        assert result["tasks_examined"] == 1
        assert len(result["backfilled"]) == 1
        backfill = result["backfilled"][0]
        assert backfill["task_id"] == 14
        assert backfill["date"] == "2026-05-19"
        assert backfill["source"] == "vikunja-ui"

        records = state_log.read("habits", task_id=14)
        assert len(records) == 1
        assert records[0]["source"] == "vikunja-ui"
        assert records[0]["state"] == "complete"
        assert records[0]["date"] == "2026-05-19"
        assert records[0]["title"] == "Wake at 5:00 AM"

    def test_done_at_timestamp_normalized_to_utc_date(
        self, mock_urlopen, mock_state_log_dir
    ):
        # An offset-suffixed timestamp at 23:30 in -07:00 = next day in UTC.
        mock_urlopen.side_effect = _responses(tasks=[
            _task(
                14,
                title="Wake",
                done=True,
                done_at="2026-05-18T23:30:00-07:00",  # = 2026-05-19T06:30Z
            ),
        ])
        result = rec.reconcile(
            api_base_url="http://test/api/v1/",
            token="t",
            today="2026-05-20",
        )
        assert result["backfilled"][0]["date"] == "2026-05-19"


# ===========================================================================
# Group 2 — No backfill needed
# ===========================================================================


class TestNoBackfill:
    def test_existing_jsonl_skips_backfill(
        self, mock_urlopen, mock_state_log_dir
    ):
        # Pre-seed JSONL with a matching complete record.
        state_log.append(
            "habits",
            {
                "domain": "habits",
                "task_id": 14,
                "title": "Wake",
                "date": "2026-05-19",
                "state": "complete",
                "source": "whatsapp",
                "timestamp": "2026-05-19T11:00:00+00:00",
            },
        )

        mock_urlopen.side_effect = _responses(tasks=[
            _task(
                14, title="Wake", done=True, done_at="2026-05-19T11:00:00Z"
            ),
        ])

        result = rec.reconcile(
            api_base_url="http://test/api/v1/",
            token="t",
            today="2026-05-20",
        )
        assert result["backfilled"] == []
        # Pre-seeded record still the only one.
        records = state_log.read("habits", task_id=14)
        assert len(records) == 1


# ===========================================================================
# Group 3 — Drift detection
# ===========================================================================


class TestDrift:
    def test_drift_reported_but_not_resolved(
        self, mock_urlopen, mock_state_log_dir
    ):
        # JSONL: complete for today.
        state_log.append(
            "habits",
            {
                "domain": "habits",
                "task_id": 14,
                "title": "Wake",
                "date": "2026-05-20",
                "state": "complete",
                "source": "whatsapp",
                "timestamp": "2026-05-20T11:00:00+00:00",
            },
        )
        # Vikunja: done=false (drift).
        mock_urlopen.side_effect = _responses(tasks=[
            _task(14, title="Wake", done=False),
        ])

        result = rec.reconcile(
            api_base_url="http://test/api/v1/",
            token="t",
            today="2026-05-20",
        )
        assert len(result["drift"]) == 1
        d = result["drift"][0]
        assert d["task_id"] == 14
        assert d["title"] == "Wake"
        assert d["date"] == "2026-05-20"
        assert d["vikunja_done"] is False
        # No mutation: drift is informational.
        records = state_log.read("habits", task_id=14)
        assert len(records) == 1

    def test_no_drift_when_jsonl_lacks_complete_for_today(
        self, mock_urlopen, mock_state_log_dir
    ):
        # JSONL has a record for a different date.
        state_log.append(
            "habits",
            {
                "domain": "habits",
                "task_id": 14,
                "title": "Wake",
                "date": "2026-05-18",
                "state": "complete",
                "source": "whatsapp",
                "timestamp": "2026-05-18T11:00:00+00:00",
            },
        )
        mock_urlopen.side_effect = _responses(tasks=[
            _task(14, title="Wake", done=False),
        ])
        result = rec.reconcile(
            api_base_url="http://test/api/v1/",
            token="t",
            today="2026-05-20",
        )
        assert result["drift"] == []


# ===========================================================================
# Group 4 — Zero-sentinel done_at
# ===========================================================================


class TestZeroSentinel:
    def test_zero_sentinel_done_at_treated_as_no_date(
        self, mock_urlopen, mock_state_log_dir
    ):
        """Vikunja returns 0001-01-01T00:00:00Z for unset done_at."""
        mock_urlopen.side_effect = _responses(tasks=[
            _task(
                14,
                title="Wake",
                done=True,
                done_at=rec.ZERO_DATE_SENTINEL,
            ),
        ])
        result = rec.reconcile(
            api_base_url="http://test/api/v1/",
            token="t",
            today="2026-05-20",
        )
        # No backfill (we don't have a valid completion date).
        assert result["backfilled"] == []
        # Error reported so the operator notices.
        assert len(result["errors"]) == 1
        assert "done=true but done_at missing" in result["errors"][0]["message"]

    def test_empty_done_at_treated_as_no_date(
        self, mock_urlopen, mock_state_log_dir
    ):
        mock_urlopen.side_effect = _responses(tasks=[
            _task(14, title="Wake", done=True, done_at=""),
        ])
        result = rec.reconcile(
            api_base_url="http://test/api/v1/",
            token="t",
            today="2026-05-20",
        )
        assert result["backfilled"] == []
        assert len(result["errors"]) == 1

    def test_null_done_at_treated_as_no_date(
        self, mock_urlopen, mock_state_log_dir
    ):
        mock_urlopen.side_effect = _responses(tasks=[
            _task(14, title="Wake", done=True, done_at=None),
        ])
        result = rec.reconcile(
            api_base_url="http://test/api/v1/",
            token="t",
            today="2026-05-20",
        )
        assert result["backfilled"] == []
        assert len(result["errors"]) == 1


# ===========================================================================
# Group 5 — today override
# ===========================================================================


class TestTodayOverride:
    def test_today_kwarg_overrides_system_date(
        self, mock_urlopen, mock_state_log_dir
    ):
        # JSONL: complete for 2026-05-15.
        state_log.append(
            "habits",
            {
                "domain": "habits",
                "task_id": 14,
                "title": "Wake",
                "date": "2026-05-15",
                "state": "complete",
                "source": "whatsapp",
                "timestamp": "2026-05-15T11:00:00+00:00",
            },
        )
        mock_urlopen.side_effect = _responses(tasks=[
            _task(14, title="Wake", done=False),
        ])
        # Drift should be detected against 2026-05-15, not system date.
        result = rec.reconcile(
            api_base_url="http://test/api/v1/",
            token="t",
            today="2026-05-15",
        )
        assert len(result["drift"]) == 1
        assert result["drift"][0]["date"] == "2026-05-15"

    def test_today_default_uses_utc_today(
        self, mock_urlopen, mock_state_log_dir
    ):
        # No drift to assert; this just exercises the default path.
        mock_urlopen.side_effect = _responses(tasks=[
            _task(14, title="Wake", done=False),
        ])
        result = rec.reconcile(
            api_base_url="http://test/api/v1/",
            token="t",
        )
        assert result["tasks_examined"] == 1

    def test_today_bad_format_raises_value_error(
        self, mock_urlopen, mock_state_log_dir
    ):
        mock_urlopen.side_effect = AssertionError("must not be called")
        with pytest.raises(ValueError, match="YYYY-MM-DD"):
            rec.reconcile(
                api_base_url="http://test/api/v1/",
                token="t",
                today="5/15/2026",
            )


# ===========================================================================
# Group 6 — _done_at_date unit
# ===========================================================================


class TestDoneAtDateUnit:
    def test_z_suffix_normalized(self):
        assert (
            rec._done_at_date({"done_at": "2026-05-19T11:00:00Z"})
            == "2026-05-19"
        )

    def test_offset_normalized_to_utc_date(self):
        # 23:30 in -07:00 is 06:30 next-day UTC.
        assert (
            rec._done_at_date({"done_at": "2026-05-18T23:30:00-07:00"})
            == "2026-05-19"
        )

    def test_zero_sentinel(self):
        assert (
            rec._done_at_date({"done_at": "0001-01-01T00:00:00Z"}) is None
        )

    def test_missing_key(self):
        assert rec._done_at_date({}) is None

    def test_none_value(self):
        assert rec._done_at_date({"done_at": None}) is None

    def test_empty_string(self):
        assert rec._done_at_date({"done_at": ""}) is None

    def test_unparseable_value(self):
        assert rec._done_at_date({"done_at": "not-a-date"}) is None

    def test_naive_timestamp_assumed_utc(self):
        # No tz offset on the input -> assume UTC.
        assert (
            rec._done_at_date({"done_at": "2026-05-19T11:00:00"})
            == "2026-05-19"
        )


# ===========================================================================
# Group 7 — CLI surface
# ===========================================================================


class TestCli:
    def test_help_exits_zero(self, capsys):
        with pytest.raises(SystemExit) as exc:
            rec.main(["--help"])
        assert exc.value.code == 0

    def test_cli_exit_zero_with_drift(
        self,
        mock_urlopen,
        mock_state_log_dir,
        tmp_token_file,
        capsys,
    ):
        # Pre-seed JSONL for drift detection.
        state_log.append(
            "habits",
            {
                "domain": "habits",
                "task_id": 14,
                "title": "Wake",
                "date": "2026-05-20",
                "state": "complete",
                "source": "whatsapp",
                "timestamp": "2026-05-20T11:00:00+00:00",
            },
        )
        mock_urlopen.side_effect = _responses(tasks=[
            _task(14, title="Wake", done=False),
        ])
        exit_code = rec.main([
            "--token-file", str(tmp_token_file),
            "--base-url", "http://test/api/v1/",
            "--today", "2026-05-20",
        ])
        # Drift is informational -- still exit 0.
        assert exit_code == 0
        out = capsys.readouterr().out
        assert "DRIFT: task_id=14" in out
        assert "JSONL says complete for 2026-05-20" in out
        assert "Vikunja shows done=false" in out

    def test_cli_exit_zero_no_drift_no_backfill(
        self,
        mock_urlopen,
        mock_state_log_dir,
        tmp_token_file,
        capsys,
    ):
        mock_urlopen.side_effect = _responses(tasks=[])  # no tasks
        exit_code = rec.main([
            "--token-file", str(tmp_token_file),
            "--base-url", "http://test/api/v1/",
            "--today", "2026-05-20",
        ])
        assert exit_code == 0
        out = capsys.readouterr().out
        assert "tasks_examined: 0" in out
        assert "backfilled: 0" in out
        assert "drift: 0" in out

    def test_cli_exit_one_on_enumerate_failure(
        self,
        mock_urlopen,
        mock_state_log_dir,
        tmp_token_file,
        capsys,
    ):
        mock_urlopen.side_effect = _http_error(503, b'{"message":"down"}')
        exit_code = rec.main([
            "--token-file", str(tmp_token_file),
            "--base-url", "http://test/api/v1/",
            "--today", "2026-05-20",
        ])
        assert exit_code == 1
        err = capsys.readouterr().err
        assert "reconcile failed" in err

    def test_cli_bad_today_exits_two(
        self,
        mock_urlopen,
        mock_state_log_dir,
        tmp_token_file,
        capsys,
    ):
        mock_urlopen.side_effect = AssertionError("must not be called")
        exit_code = rec.main([
            "--token-file", str(tmp_token_file),
            "--base-url", "http://test/api/v1/",
            "--today", "5/15/2026",
        ])
        assert exit_code == 2
        err = capsys.readouterr().err
        assert "YYYY-MM-DD" in err

    def test_cli_missing_token_file_exits_one(
        self,
        mock_urlopen,
        mock_state_log_dir,
        tmp_path,
        capsys,
    ):
        mock_urlopen.side_effect = AssertionError("must not be called")
        missing = tmp_path / "nope" / "token"
        exit_code = rec.main([
            "--token-file", str(missing),
            "--base-url", "http://test/api/v1/",
        ])
        # Token failure means we can't enumerate -> exit 1.
        assert exit_code == 1
        err = capsys.readouterr().err
        assert "Token file not found" in err

    def test_cli_backfill_summary_format(
        self,
        mock_urlopen,
        mock_state_log_dir,
        tmp_token_file,
        capsys,
    ):
        mock_urlopen.side_effect = _responses(tasks=[
            _task(
                14, title="Wake", done=True, done_at="2026-05-19T11:00:00Z"
            ),
            _task(
                18, title="Read", done=True, done_at="2026-05-19T20:00:00Z"
            ),
        ])
        exit_code = rec.main([
            "--token-file", str(tmp_token_file),
            "--base-url", "http://test/api/v1/",
            "--today", "2026-05-20",
        ])
        assert exit_code == 0
        out = capsys.readouterr().out
        assert "backfilled: 2" in out
        assert "task_id=14 date=2026-05-19 source=vikunja-ui" in out
        assert "task_id=18 date=2026-05-19 source=vikunja-ui" in out


# ===========================================================================
# Group 8 — Misc edge cases
# ===========================================================================


class TestMisc:
    def test_malformed_task_id_added_to_errors_but_does_not_abort(
        self, mock_urlopen, mock_state_log_dir
    ):
        mock_urlopen.side_effect = _responses(tasks=[
            {"title": "no id", "done": False},  # no 'id' field
            _task(14, title="ok", done=False),
        ])
        result = rec.reconcile(
            api_base_url="http://test/api/v1/",
            token="t",
            today="2026-05-20",
        )
        assert result["tasks_examined"] == 2
        assert len(result["errors"]) == 1
        assert "missing or invalid 'id'" in result["errors"][0]["message"]

    def test_non_list_payload_raises_os_error(
        self, mock_urlopen, mock_state_log_dir
    ):
        # /projects resolves fine; /tasks returns a non-list.
        mock_urlopen.side_effect = [
            _resp(_projects_payload()),
            _resp({"not": "a list"}),
        ]
        with pytest.raises(OSError, match="non-list payload"):
            rec.reconcile(
                api_base_url="http://test/api/v1/",
                token="t",
                today="2026-05-20",
            )

    def test_empty_response_treated_as_no_tasks(
        self, mock_urlopen, mock_state_log_dir
    ):
        # /projects resolves fine; /tasks returns empty body.
        mock_urlopen.side_effect = [
            _resp(_projects_payload()),
            _resp(None),  # empty body
        ]
        result = rec.reconcile(
            api_base_url="http://test/api/v1/",
            token="t",
            today="2026-05-20",
        )
        assert result["tasks_examined"] == 0
        assert result["backfilled"] == []
        assert result["drift"] == []

    def test_enumerate_uses_get_without_server_side_archived_filter(
        self, mock_urlopen, mock_state_log_dir
    ):
        """Per Verified API Gotcha G5 (#333), Vikunja v0.24.6 rejects the
        ``is_archived`` filter expression with HTTP 400. The helper must
        NOT include that filter in the URL — it filters client-side
        instead.
        """
        mock_urlopen.side_effect = _responses(tasks=[])
        rec.reconcile(
            api_base_url="http://test/api/v1/",
            token="t",
            today="2026-05-20",
        )
        # Two calls: projects lookup, then project-scoped task enumerate.
        assert len(mock_urlopen.call_args_list) == 2
        tasks_req = mock_urlopen.call_args_list[1][0][0]
        assert tasks_req.get_method() == "GET"
        # NO server-side filter — neither "filter=" nor "is_archived" appears
        # in the URL (the URL is bare /projects/<id>/tasks).
        assert "filter=" not in tasks_req.full_url
        assert "is_archived" not in tasks_req.full_url

    def test_enumerate_filters_archived_tasks_client_side(
        self, mock_urlopen, mock_state_log_dir, sample_habit_task_response
    ):
        """Archived tasks returned by Vikunja must be filtered out
        client-side so reconcile never operates on them. Regression for
        the G5 fix.
        """
        active_task = sample_habit_task_response(
            task_id=14, title="Wake at 5:00 AM", is_archived=False
        )
        archived_task = sample_habit_task_response(
            task_id=999, title="Old habit (archived)", is_archived=True
        )
        mock_urlopen.side_effect = _responses(tasks=[active_task, archived_task])
        result = rec.reconcile(
            api_base_url="http://test/api/v1/",
            token="t",
            today="2026-05-20",
        )
        # Only the active task counts toward tasks_examined; the archived
        # one is excluded before any processing.
        assert result["tasks_examined"] == 1


# ===========================================================================
# Group 9 — Project-scoping regression (Cycle 2 fix)
# ===========================================================================


class TestProjectScoping:
    """Regression tests for the Cycle 1 finding.

    Before the fix, ``_enumerate_active_habits`` called ``GET /tasks/all``
    and returned ALL unarchived tasks across every Vikunja project. A
    completed Inbox / Goals / Recurring-event task would then be
    backfilled into the habits JSONL, violating FR-008 and the Phase 2
    state_log "one domain per log" contract.

    These tests pin the new behaviour:

      - The enumerate path resolves the Habits project by title and
        targets ``GET /projects/<id>/tasks?filter=is_archived=false`` --
        Inbox / Goals / etc. are never returned by the API mock.
      - With the new scoping, a non-habit task with done=true is never
        seen by reconcile and therefore CAN'T be backfilled (the JSONL
        remains empty).
      - If the Habits project itself cannot be resolved, reconcile fails
        cleanly with an OSError rather than falling back to a broad query.
    """

    def test_enumerate_targets_habits_project_endpoint(
        self, mock_urlopen, mock_state_log_dir
    ):
        """Second HTTP call must hit /projects/<habits_id>/tasks."""
        mock_urlopen.side_effect = _responses(tasks=[])
        rec.reconcile(
            api_base_url="http://test/api/v1/",
            token="t",
            today="2026-05-20",
        )
        assert len(mock_urlopen.call_args_list) == 2

        # First call: projects lookup.
        projects_req = mock_urlopen.call_args_list[0][0][0]
        assert projects_req.get_method() == "GET"
        assert projects_req.full_url.endswith("/projects")

        # Second call: project-scoped task enumeration.
        tasks_req = mock_urlopen.call_args_list[1][0][0]
        assert tasks_req.get_method() == "GET"
        assert f"projects/{HABITS_PROJECT_ID}/tasks" in tasks_req.full_url
        # Must NOT be the legacy cross-project endpoint.
        assert "tasks/all" not in tasks_req.full_url

    def test_non_habit_completion_cannot_leak_into_habits_jsonl(
        self, mock_urlopen, mock_state_log_dir
    ):
        """End-to-end: a non-habit done task is never enumerated.

        Simulates the pre-fix bug scenario. Under the old broad query,
        a completed Inbox task (id=999) WOULD have been returned by
        ``/tasks/all`` and backfilled. Under the new project-scoped
        query, the Vikunja mock simply does not return it from the
        Habits-project endpoint -- so reconcile never sees it and the
        habits JSONL stays clean.
        """
        # /projects mock answers with Habits + Inbox.
        # /projects/<habits_id>/tasks mock returns only the habit task
        # (id=14, done=true). The "leak candidate" -- a completed Inbox
        # task -- is NOT in the project-scoped response.
        habit_task = _task(
            14,
            title="Wake at 5:00 AM",
            done=True,
            done_at="2026-05-19T11:00:00Z",
        )
        mock_urlopen.side_effect = _responses(tasks=[habit_task])

        result = rec.reconcile(
            api_base_url="http://test/api/v1/",
            token="t",
            today="2026-05-20",
        )

        # The habit task IS backfilled.
        assert len(result["backfilled"]) == 1
        assert result["backfilled"][0]["task_id"] == 14

        # No record for the non-habit task_id=999 anywhere in the log --
        # because the project-scoped enumerate never surfaced it.
        leak_records = state_log.read("habits", task_id=999)
        assert leak_records == []

        # Exactly one record overall: the legitimate habit completion.
        all_records = state_log.read("habits")
        assert len(all_records) == 1
        assert all_records[0]["task_id"] == 14
        assert all_records[0]["source"] == "vikunja-ui"

    def test_missing_habits_project_raises_oserror(
        self, mock_urlopen, mock_state_log_dir
    ):
        """If no project titled 'Habits' is returned, reconcile fails.

        The pre-fix code silently degraded to a global enumeration --
        which is exactly the bug. The new code surfaces the misconfig
        explicitly so the operator notices.
        """
        # /projects returns only non-Habits projects.
        mock_urlopen.side_effect = [
            _resp([
                {"id": 1, "title": "Inbox"},
                {"id": 99, "title": "Goals"},
            ]),
            # No second call should be made, but provide one just in
            # case (side_effect would raise StopIteration otherwise if
            # the code unexpectedly continued).
            _resp([]),
        ]
        with pytest.raises(OSError, match="No project titled 'Habits'"):
            rec.reconcile(
                api_base_url="http://test/api/v1/",
                token="t",
                today="2026-05-20",
            )

    def test_cli_exits_one_when_habits_project_missing(
        self,
        mock_urlopen,
        mock_state_log_dir,
        tmp_token_file,
        capsys,
    ):
        """A missing Habits project surfaces as exit-1 at the CLI."""
        mock_urlopen.side_effect = [
            _resp([{"id": 1, "title": "Inbox"}]),
        ]
        exit_code = rec.main([
            "--token-file", str(tmp_token_file),
            "--base-url", "http://test/api/v1/",
            "--today", "2026-05-20",
        ])
        assert exit_code == 1
        err = capsys.readouterr().err
        assert "No project titled 'Habits'" in err
