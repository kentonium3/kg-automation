"""Tests for scripts/habits/exclude_completed_v2.py (WP04 / T016).

Covers the ``exclude_completed_for_today()`` Python API and the
``__main__`` CLI surface. state_log I/O is sandboxed via the
``mock_state_log_dir`` fixture from ``conftest.py``.

Test groups (per WP04 plan):

1. Filter out completed — pre-populate state_log with a ``complete``
   record; verify the matching task is excluded.
2. No completions — all returned.
3. ``today`` override governs the JSONL date check.
4. CLI stdin parsing — newline-delimited JSON tasks.
5. CLI empty stdin -> exit 0, empty stdout.
6. CLI malformed JSON line -> exit 2.
7. CLI state_log read failure -> exit 1.
8. Extra coverage (passthrough semantics, missing id, etc.)
"""
from __future__ import annotations

import io
import json

import pytest

from scripts.common import state_log
from scripts.habits import exclude_completed_v2 as ev2


# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------


def _complete_record(
    task_id: int,
    date: str,
    *,
    title: str = "Habit",
    source: str = "whatsapp",
) -> dict:
    """Return a state_log "habits" record shape with state=complete."""
    return {
        "domain": "habits",
        "task_id": task_id,
        "title": title,
        "date": date,
        "state": "complete",
        "source": source,
        "timestamp": f"{date}T11:00:00+00:00",
    }


def _task(task_id: int, title: str = "Habit") -> dict:
    """Return a minimal task dict (shape produced by query_active_today)."""
    return {
        "id": task_id,
        "title": title,
        "due_date": "2026-05-20T08:00:00Z",
        "done": False,
        "repeat_after": 86400,
        "project_id": 42,
        "labels": [],
    }


# ===========================================================================
# Group 1 — Filter out completed
# ===========================================================================


class TestFilterCompleted:
    def test_excludes_task_with_complete_record_for_today(
        self, mock_state_log_dir
    ):
        """A task with a state_log complete record for today is filtered out."""
        # Pre-populate the sandbox state_log with a complete record for task 14.
        state_log.append(
            "habits", _complete_record(task_id=14, date="2026-05-20", title="Wake")
        )

        active = [_task(14, title="Wake"), _task(15, title="Drink water")]
        result = ev2.exclude_completed_for_today(active, today="2026-05-20")
        ids = [t["id"] for t in result]
        assert ids == [15]

    def test_excludes_multiple_completed(self, mock_state_log_dir):
        state_log.append(
            "habits", _complete_record(task_id=14, date="2026-05-20")
        )
        state_log.append(
            "habits", _complete_record(task_id=16, date="2026-05-20")
        )

        active = [_task(14), _task(15), _task(16), _task(17)]
        result = ev2.exclude_completed_for_today(active, today="2026-05-20")
        ids = [t["id"] for t in result]
        assert ids == [15, 17]


# ===========================================================================
# Group 2 — No completions
# ===========================================================================


class TestNoCompletions:
    def test_empty_state_log_returns_full_input(self, mock_state_log_dir):
        """Without any state_log records, every active task is returned."""
        active = [_task(14), _task(15), _task(16)]
        result = ev2.exclude_completed_for_today(active, today="2026-05-20")
        ids = [t["id"] for t in result]
        assert ids == [14, 15, 16]

    def test_unrelated_state_log_records_dont_filter(self, mock_state_log_dir):
        """State-log records for OTHER task IDs don't affect the filter."""
        # Record for task 99 (not in active list).
        state_log.append(
            "habits", _complete_record(task_id=99, date="2026-05-20")
        )
        active = [_task(14), _task(15)]
        result = ev2.exclude_completed_for_today(active, today="2026-05-20")
        ids = [t["id"] for t in result]
        assert ids == [14, 15]

    def test_non_complete_state_doesnt_filter(self, mock_state_log_dir):
        """A 'skipped' record (not 'complete') doesn't filter the task out.

        The contract is `state="complete"` only — other states (e.g.
        ``skipped`` or ``incomplete`` per the habits domain enum) leave
        the task ready for check-in.
        """
        state_log.append(
            "habits",
            {
                "domain": "habits",
                "task_id": 14,
                "title": "Wake",
                "date": "2026-05-20",
                "state": "skipped",
                "source": "whatsapp",
                "timestamp": "2026-05-20T11:00:00+00:00",
            },
        )
        active = [_task(14)]
        result = ev2.exclude_completed_for_today(active, today="2026-05-20")
        assert [t["id"] for t in result] == [14]


# ===========================================================================
# Group 3 — `today` override
# ===========================================================================


class TestTodayOverride:
    def test_today_override_changes_filter_date(self, mock_state_log_dir):
        """State_log has a complete on 2026-05-19. Different today values give different results."""
        state_log.append(
            "habits", _complete_record(task_id=14, date="2026-05-19")
        )

        active = [_task(14)]
        # On 2026-05-19, task 14 is filtered out.
        result_yesterday = ev2.exclude_completed_for_today(
            active, today="2026-05-19"
        )
        assert result_yesterday == []
        # On 2026-05-20, task 14 is INCLUDED (no complete for that date).
        result_today = ev2.exclude_completed_for_today(
            active, today="2026-05-20"
        )
        assert [t["id"] for t in result_today] == [14]

    def test_today_default_uses_utc_today(self, mock_state_log_dir):
        """Default today is UTC today — exercises the default path."""
        # We don't pre-seed any state_log records, so every input is returned.
        active = [_task(14)]
        result = ev2.exclude_completed_for_today(active)
        assert [t["id"] for t in result] == [14]

    def test_today_bad_format_raises_value_error(self, mock_state_log_dir):
        with pytest.raises(ValueError, match="YYYY-MM-DD"):
            ev2.exclude_completed_for_today([_task(14)], today="5/15/2026")


# ===========================================================================
# Group 4 — CLI stdin parsing
# ===========================================================================


class TestCliStdin:
    def test_cli_filters_three_tasks_via_stdin(
        self, mock_state_log_dir, monkeypatch, capsys
    ):
        """Subprocess-style: stdin = 3 JSONL tasks; verify stdout filter."""
        # Pre-populate state_log so task 14 is filtered out.
        state_log.append(
            "habits", _complete_record(task_id=14, date="2026-05-20")
        )

        stdin_text = "\n".join([
            json.dumps(_task(14, title="Wake")),
            json.dumps(_task(15, title="Drink water")),
            json.dumps(_task(16, title="Meditate")),
        ]) + "\n"
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_text))
        exit_code = ev2.main(["--today", "2026-05-20"])
        assert exit_code == 0
        out = capsys.readouterr().out
        lines = [ln for ln in out.splitlines() if ln.strip()]
        ids = [json.loads(ln)["id"] for ln in lines]
        assert ids == [15, 16]

    def test_cli_blank_lines_skipped(
        self, mock_state_log_dir, monkeypatch, capsys
    ):
        """Empty/whitespace-only stdin lines are skipped silently."""
        stdin_text = (
            json.dumps(_task(14)) + "\n"
            "\n"
            "   \n"
            + json.dumps(_task(15)) + "\n"
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_text))
        exit_code = ev2.main(["--today", "2026-05-20"])
        assert exit_code == 0
        out = capsys.readouterr().out
        lines = [ln for ln in out.splitlines() if ln.strip()]
        assert len(lines) == 2


# ===========================================================================
# Group 5 — CLI empty stdin
# ===========================================================================


class TestCliEmptyStdin:
    def test_cli_empty_stdin_exits_zero_with_empty_stdout(
        self, mock_state_log_dir, monkeypatch, capsys
    ):
        """Empty stdin yields exit 0 and empty stdout, no error."""
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        exit_code = ev2.main(["--today", "2026-05-20"])
        assert exit_code == 0
        out = capsys.readouterr().out
        assert out == ""

    def test_cli_only_blank_lines_exits_zero(
        self, mock_state_log_dir, monkeypatch, capsys
    ):
        """stdin = only blank lines is treated the same as empty stdin."""
        monkeypatch.setattr("sys.stdin", io.StringIO("\n\n   \n\n"))
        exit_code = ev2.main(["--today", "2026-05-20"])
        assert exit_code == 0
        out = capsys.readouterr().out
        assert out == ""


# ===========================================================================
# Group 6 — CLI malformed JSON
# ===========================================================================


class TestCliMalformed:
    def test_cli_malformed_json_exits_two(
        self, mock_state_log_dir, monkeypatch, capsys
    ):
        """A malformed JSON line on stdin causes exit 2 with stderr explanation."""
        monkeypatch.setattr("sys.stdin", io.StringIO("not json\n"))
        exit_code = ev2.main(["--today", "2026-05-20"])
        assert exit_code == 2
        err = capsys.readouterr().err
        assert "malformed JSON" in err or "ERROR" in err

    def test_cli_non_object_line_exits_two(
        self, mock_state_log_dir, monkeypatch, capsys
    ):
        """A JSON value that's not an object (e.g., a number) is rejected."""
        monkeypatch.setattr("sys.stdin", io.StringIO("42\n"))
        exit_code = ev2.main(["--today", "2026-05-20"])
        assert exit_code == 2
        err = capsys.readouterr().err
        assert "not a JSON object" in err or "ERROR" in err

    def test_cli_bad_today_exits_two(
        self, mock_state_log_dir, monkeypatch, capsys
    ):
        """Bad --today format -> exit 2."""
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        exit_code = ev2.main(["--today", "5/20/2026"])
        assert exit_code == 2
        err = capsys.readouterr().err
        assert "YYYY-MM-DD" in err


# ===========================================================================
# Group 7 — state_log read failure -> CLI exit 1
# ===========================================================================


class TestStateLogReadFailure:
    def test_cli_state_log_oserror_exits_one(
        self, mock_state_log_dir, monkeypatch, capsys
    ):
        """If state_log.read raises OSError, CLI exits 1 with stderr."""
        def fake_read(*args, **kwargs):
            raise OSError("simulated disk failure")

        # Patch state_log.read at the module ev2 imported it through.
        monkeypatch.setattr(ev2.state_log, "read", fake_read)
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(_task(14)) + "\n"))

        exit_code = ev2.main(["--today", "2026-05-20"])
        assert exit_code == 1
        err = capsys.readouterr().err
        assert "state_log read failed" in err

    def test_api_state_log_oserror_propagates(
        self, mock_state_log_dir, monkeypatch
    ):
        """The Python API surfaces OSError directly (no wrapping)."""
        def fake_read(*args, **kwargs):
            raise OSError("boom")

        monkeypatch.setattr(ev2.state_log, "read", fake_read)
        with pytest.raises(OSError, match="boom"):
            ev2.exclude_completed_for_today([_task(14)], today="2026-05-20")


# ===========================================================================
# Group 8 — Misc / passthrough semantics
# ===========================================================================


class TestMisc:
    def test_help_exits_zero(self):
        with pytest.raises(SystemExit) as exc:
            ev2.main(["--help"])
        assert exc.value.code == 0

    def test_task_without_id_is_included(self, mock_state_log_dir):
        """A task missing an integer ``id`` is included (defensive default)."""
        active = [
            {"title": "no id field"},
            _task(15, title="ok"),
        ]
        result = ev2.exclude_completed_for_today(active, today="2026-05-20")
        # Both pass through — the malformed one because we can't query, and
        # the valid one because no complete record exists.
        assert len(result) == 2

    def test_non_dict_input_entries_skipped(self, mock_state_log_dir):
        """Stray non-dict entries are skipped silently from the API surface."""
        active = [_task(14), "garbage", 42, _task(15)]
        result = ev2.exclude_completed_for_today(active, today="2026-05-20")
        ids = [t["id"] for t in result]
        assert ids == [14, 15]

    def test_input_order_preserved(self, mock_state_log_dir):
        """The output preserves the input order."""
        active = [_task(16), _task(14), _task(15)]
        result = ev2.exclude_completed_for_today(active, today="2026-05-20")
        ids = [t["id"] for t in result]
        assert ids == [16, 14, 15]

    def test_input_dicts_returned_unmodified(self, mock_state_log_dir):
        """Each task dict in the output is the exact dict from the input."""
        t1 = _task(14)
        t2 = _task(15)
        result = ev2.exclude_completed_for_today([t1, t2], today="2026-05-20")
        # The same object identities pass through (no copy).
        assert result[0] is t1
        assert result[1] is t2
