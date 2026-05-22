"""Tests for scripts/habits/morning_checkin_list.py (mission #371 / WP01).

Covers ``build_morning_list``, ``persist_morning_list``,
``render_morning_message``, and the ``main`` CLI entry point. All Vikunja
HTTP traffic is mocked via the ``mock_urlopen`` fixture (conftest.py); no
test makes a live API call. Time-dependent helpers (``_today_local``,
``_now_utc_iso``) are monkeypatched so tests are deterministic across
CI timezones.

The most important guarantees this suite enforces (per WP01 reviewer
guidance):

  * Sort stability -- habits are always ordered by ``vikunja_task_id`` ASC
    (the immutable Vikunja per-task identifier). Any other sort key would
    reintroduce the #371 root cause.
  * Atomic write -- a fsync failure mid-write must NOT leave a partial
    file at the canonical path. The previous artifact (if any) survives.
  * TZ correctness -- "today" is always America/New_York; UTC midnight is
    not a meaningful day boundary for Kent.
  * Coverage -- the suite targets >=85% line + branch on this module.
"""
from __future__ import annotations

import io
import json
import os
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.habits import morning_checkin_list as mcl


# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------


HABITS_PROJECT_ID = 42


def _resp(payload, *, status: int = 200):
    """Build a context-manager-shaped mock urlopen response."""
    body = json.dumps(payload).encode("utf-8") if payload is not None else b""
    resp = MagicMock(name="response")
    resp.status = status
    resp.read = MagicMock(return_value=body)
    cm = MagicMock(name="cm")
    cm.__enter__ = MagicMock(return_value=resp)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


def _projects_payload(project_id: int = HABITS_PROJECT_ID):
    return [
        {"id": 1, "title": "Inbox"},
        {"id": project_id, "title": "Habits"},
        {"id": 99, "title": "Goals"},
    ]


def _task(
    task_id: int,
    title: str = "Habit",
    due_date: str = "2026-05-22T08:00:00Z",
    done: bool = False,
    repeat_after: int = 86400,
    project_id: int = HABITS_PROJECT_ID,
    labels: list | None = None,
) -> dict:
    return {
        "id": task_id,
        "title": title,
        "due_date": due_date,
        "done": done,
        "repeat_after": repeat_after,
        "project_id": project_id,
        "labels": labels or [],
    }


def _vikunja_responses(tasks):
    """A two-call sequence: GET /projects then GET /projects/<id>/tasks."""
    return [_resp(_projects_payload()), _resp(tasks)]


# ---------------------------------------------------------------------------
# Group 1 — Module shape
# ---------------------------------------------------------------------------


class TestModuleShape:
    def test_constants_have_expected_values(self):
        assert mcl.SCHEMA_VERSION == 1
        assert mcl.DEFAULT_BASE_URL == "http://100.92.197.90:3456/api/v1/"
        assert mcl.DEFAULT_TOKEN_PATH == Path(
            "/data/services/openclaw/secrets/vikunja-api"
        )
        assert mcl.DEFAULT_STATE_DIR == Path(
            "/data/services/openclaw/state/habits"
        )
        assert mcl.HTTP_TIMEOUT_SECONDS == 30
        assert str(mcl.LOCAL_TZ) == "America/New_York"

    def test_dataclasses_are_frozen(self):
        habit = mcl.MorningListHabit(position=1, vikunja_task_id=14, title="X")
        ml = mcl.MorningList(
            schema_version=1,
            date="2026-05-22",
            generated_at="2026-05-22T11:00:00Z",
            habits=[habit],
        )
        # Frozen => attribute assignment raises.
        with pytest.raises(Exception):
            habit.title = "Y"  # type: ignore[misc]
        with pytest.raises(Exception):
            ml.date = "2026-05-23"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Group 2 — Clock helpers
# ---------------------------------------------------------------------------


class TestClockHelpers:
    def test_today_local_returns_iso_date(self):
        result = mcl._today_local()
        # YYYY-MM-DD shape.
        assert len(result) == 10
        assert result[4] == "-" and result[7] == "-"
        # Parses cleanly.
        parsed = datetime.fromisoformat(result).date()
        assert parsed.isoformat() == result

    def test_today_local_uses_america_new_york(self, monkeypatch):
        """Even when system time is UTC late-day, the helper returns the
        America/New_York calendar date.

        We patch ``datetime.now`` inside the module so it behaves as if the
        process were called at 2026-05-23T03:30:00+00:00 (which is
        2026-05-22T23:30:00 in America/New_York during DST). The local
        helper must report 2026-05-22, not 2026-05-23.
        """
        utc_late = datetime(2026, 5, 23, 3, 30, 0, tzinfo=timezone.utc)

        class _FakeDatetime(datetime):
            @classmethod
            def now(cls, tz=None):  # type: ignore[override]
                if tz is None:
                    return utc_late.replace(tzinfo=None)
                return utc_late.astimezone(tz)

        monkeypatch.setattr(mcl, "datetime", _FakeDatetime)
        assert mcl._today_local() == "2026-05-22"

    def test_now_utc_iso_format(self):
        result = mcl._now_utc_iso()
        # Looks like 2026-05-22T11:05:00Z (no microseconds, explicit Z).
        assert result.endswith("Z")
        assert len(result) == 20
        # Round-trip parses.
        datetime.strptime(result, "%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Group 3 — Token reader
# ---------------------------------------------------------------------------


class TestReadToken:
    def test_reads_and_strips_token(self, tmp_path):
        token_file = tmp_path / "tok"
        token_file.write_text("abc123\n", encoding="utf-8")
        assert mcl._read_token(token_file) == "abc123"

    def test_missing_file_raises_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            mcl._read_token(tmp_path / "nope")

    def test_empty_file_raises_os_error(self, tmp_path):
        token_file = tmp_path / "tok"
        token_file.write_text("   \n", encoding="utf-8")
        with pytest.raises(OSError, match="empty"):
            mcl._read_token(token_file)


# ---------------------------------------------------------------------------
# Group 4 — build_morning_list happy path + filtering
# ---------------------------------------------------------------------------


class TestBuildMorningList:
    def test_happy_path_three_habits_sorted_by_id(
        self, monkeypatch, tmp_token_file, mock_urlopen, mock_state_log_dir
    ):
        """Habits returned with mixed IDs are sorted ASC by Vikunja id."""
        tasks = [
            _task(3, title="Meditate"),
            _task(1, title="Wake at 5:00 AM"),
            _task(2, title="Morning shoulder PT"),
        ]
        mock_urlopen.side_effect = _vikunja_responses(tasks)

        result = mcl.build_morning_list(
            date="2026-05-22",
            base_url="http://test/api/v1/",
            token_path=tmp_token_file,
        )

        assert result.schema_version == 1
        assert result.date == "2026-05-22"
        # generated_at is present and well-formed.
        assert result.generated_at.endswith("Z")
        # Three habits, sorted by id: 1, 2, 3 with positions 1, 2, 3.
        assert [(h.position, h.vikunja_task_id, h.title) for h in result.habits] == [
            (1, 1, "Wake at 5:00 AM"),
            (2, 2, "Morning shoulder PT"),
            (3, 3, "Meditate"),
        ]

    def test_sort_stability_three_two_one(
        self, tmp_token_file, mock_urlopen, mock_state_log_dir
    ):
        """Tasks arriving as [3, 1, 2] are emitted as [1, 2, 3] -- the #371 fix."""
        tasks = [
            _task(3, title="Three"),
            _task(1, title="One"),
            _task(2, title="Two"),
        ]
        mock_urlopen.side_effect = _vikunja_responses(tasks)

        result = mcl.build_morning_list(
            date="2026-05-22",
            base_url="http://test/api/v1/",
            token_path=tmp_token_file,
        )
        assert [h.vikunja_task_id for h in result.habits] == [1, 2, 3]
        assert [h.position for h in result.habits] == [1, 2, 3]
        assert [h.title for h in result.habits] == ["One", "Two", "Three"]

    def test_default_date_uses_local_today(
        self, monkeypatch, tmp_token_file, mock_urlopen, mock_state_log_dir
    ):
        """When date is None, build_morning_list calls _today_local()."""
        monkeypatch.setattr(mcl, "_today_local", lambda: "2026-05-22")
        mock_urlopen.side_effect = _vikunja_responses([_task(7, title="X")])

        result = mcl.build_morning_list(
            date=None,
            base_url="http://test/api/v1/",
            token_path=tmp_token_file,
        )
        assert result.date == "2026-05-22"
        assert [h.vikunja_task_id for h in result.habits] == [7]

    def test_empty_habits_list(
        self, tmp_token_file, mock_urlopen, mock_state_log_dir
    ):
        mock_urlopen.side_effect = _vikunja_responses([])
        result = mcl.build_morning_list(
            date="2026-05-22",
            base_url="http://test/api/v1/",
            token_path=tmp_token_file,
        )
        assert result.habits == []
        assert result.date == "2026-05-22"

    def test_invalid_date_raises_value_error(
        self, tmp_token_file, mock_urlopen
    ):
        mock_urlopen.side_effect = AssertionError("must not call HTTP")
        with pytest.raises(ValueError, match="YYYY-MM-DD"):
            mcl.build_morning_list(
                date="2026/05/22",
                base_url="http://test/api/v1/",
                token_path=tmp_token_file,
            )

    def test_vikunja_url_error_propagates(
        self, tmp_token_file, mock_urlopen, mock_state_log_dir
    ):
        mock_urlopen.side_effect = urllib.error.URLError("connection refused")
        with pytest.raises(OSError):
            mcl.build_morning_list(
                date="2026-05-22",
                base_url="http://test/api/v1/",
                token_path=tmp_token_file,
            )

    def test_excludes_habits_already_completed(
        self, tmp_token_file, mock_urlopen, mock_state_log_dir
    ):
        """Habits with a state=complete JSONL record for today are filtered."""
        # Two active habits.
        mock_urlopen.side_effect = _vikunja_responses([
            _task(1, title="One"),
            _task(2, title="Two"),
        ])
        # Pre-record task 1 as complete for today via the state_log
        # library (the same path exclude_completed_v2 reads from).
        from scripts.common import state_log
        state_log.append("habits", {
            "domain": "habits",
            "task_id": 1,
            "title": "One",
            "date": "2026-05-22",
            "state": "complete",
            "source": "test",
            "timestamp": "2026-05-22T11:00:00Z",
            "note": None,
        })

        result = mcl.build_morning_list(
            date="2026-05-22",
            base_url="http://test/api/v1/",
            token_path=tmp_token_file,
        )
        assert [h.vikunja_task_id for h in result.habits] == [2]

    def test_task_missing_integer_id_raises_value_error(
        self, tmp_token_file, mock_urlopen, mock_state_log_dir
    ):
        # An entry that somehow survives query_active_today with a non-int id
        # is rejected by the sort key. We patch the inner helper so we can
        # inject a malformed task without contradicting the upstream contract.
        from unittest.mock import patch

        bad = [{"id": "not-an-int", "title": "Bad", "due_date": "x", "done": False}]
        with patch.object(mcl, "_query_habits", return_value=bad):
            with patch.object(mcl, "_exclude_already_addressed", return_value=bad):
                with pytest.raises(ValueError, match="integer 'id'"):
                    mcl.build_morning_list(
                        date="2026-05-22",
                        base_url="http://test/api/v1/",
                        token_path=tmp_token_file,
                    )


# ---------------------------------------------------------------------------
# Group 5 — persist_morning_list (atomic write semantics)
# ---------------------------------------------------------------------------


def _sample_morning_list(date: str = "2026-05-22") -> mcl.MorningList:
    return mcl.MorningList(
        schema_version=1,
        date=date,
        generated_at="2026-05-22T11:05:00Z",
        habits=[
            mcl.MorningListHabit(position=1, vikunja_task_id=14, title="A"),
            mcl.MorningListHabit(position=2, vikunja_task_id=18, title="B"),
        ],
    )


class TestPersistMorningList:
    def test_writes_file_with_expected_path_and_shape(self, tmp_path):
        ml = _sample_morning_list()
        out = mcl.persist_morning_list(ml, state_dir=tmp_path)
        assert out == tmp_path / "morning-checkin-2026-05-22.json"
        assert out.exists()
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload == {
            "schema_version": 1,
            "date": "2026-05-22",
            "generated_at": "2026-05-22T11:05:00Z",
            "habits": [
                {"position": 1, "vikunja_task_id": 14, "title": "A"},
                {"position": 2, "vikunja_task_id": 18, "title": "B"},
            ],
        }

    def test_creates_missing_parent_directory(self, tmp_path):
        nested = tmp_path / "habits" / "morning"
        assert not nested.exists()
        ml = _sample_morning_list()
        mcl.persist_morning_list(ml, state_dir=nested)
        assert (nested / "morning-checkin-2026-05-22.json").exists()

    def test_atomic_write_no_partial_on_fsync_failure(
        self, tmp_path, monkeypatch
    ):
        """If fsync raises mid-write, the canonical file MUST NOT appear.

        This is the headline atomic-write guarantee (research D2): a crash
        during write leaves the canonical path either untouched (if no
        prior file) or with the previous good content (if one existed).
        """
        ml = _sample_morning_list()
        # Pre-existing artifact with stable content -- must survive.
        canonical = tmp_path / "morning-checkin-2026-05-22.json"
        canonical.write_text('{"schema_version": 1, "previous": true}', encoding="utf-8")
        previous_bytes = canonical.read_bytes()

        original_fsync = os.fsync

        def _exploding_fsync(fd):
            # Simulate a kernel-level write failure on fsync.
            raise OSError("simulated fsync failure")

        monkeypatch.setattr(os, "fsync", _exploding_fsync)

        with pytest.raises(OSError, match="simulated fsync failure"):
            mcl.persist_morning_list(ml, state_dir=tmp_path)

        # Canonical file still holds the prior content -- untouched.
        assert canonical.read_bytes() == previous_bytes
        # tmp file should not be left behind either.
        tmp_artifact = tmp_path / "morning-checkin-2026-05-22.json.tmp"
        assert not tmp_artifact.exists()

        # Restore for any test isolation safety net.
        monkeypatch.setattr(os, "fsync", original_fsync)

    def test_re_running_same_data_produces_same_bytes(self, tmp_path):
        """Idempotent write: same input -> same output bytes."""
        ml = _sample_morning_list()
        path1 = mcl.persist_morning_list(ml, state_dir=tmp_path)
        bytes1 = path1.read_bytes()
        path2 = mcl.persist_morning_list(ml, state_dir=tmp_path)
        bytes2 = path2.read_bytes()
        assert path1 == path2
        assert bytes1 == bytes2

    def test_replace_failure_cleans_up_tmp(self, tmp_path, monkeypatch):
        """If os.replace raises, the dangling .tmp is cleaned up best-effort."""
        ml = _sample_morning_list()
        canonical = tmp_path / "morning-checkin-2026-05-22.json"
        tmp_path_artifact = tmp_path / "morning-checkin-2026-05-22.json.tmp"

        def _exploding_replace(src, dst):
            raise OSError("simulated replace failure")

        monkeypatch.setattr(os, "replace", _exploding_replace)
        with pytest.raises(OSError, match="simulated replace failure"):
            mcl.persist_morning_list(ml, state_dir=tmp_path)
        # tmp cleanup happened.
        assert not tmp_path_artifact.exists()
        # canonical file not created.
        assert not canonical.exists()


# ---------------------------------------------------------------------------
# Group 6 — render_morning_message
# ---------------------------------------------------------------------------


class TestRenderMorningMessage:
    def test_empty_list_renders_short_string(self):
        ml = mcl.MorningList(
            schema_version=1,
            date="2026-05-22",
            generated_at="2026-05-22T11:05:00Z",
            habits=[],
        )
        assert mcl.render_morning_message(ml) == "All habits complete for today."

    def test_renders_numbered_lines_with_day_of_week(self):
        ml = _sample_morning_list("2026-05-22")  # Friday, May 22 2026
        msg = mcl.render_morning_message(ml)
        lines = msg.splitlines()
        assert lines[0] == "Morning check-in — Friday, May 22:"
        assert lines[1] == ""
        assert lines[2] == "1. A"
        assert lines[3] == "2. B"
        assert lines[4] == ""
        assert lines[5].startswith("Reply with what")

    def test_day_number_no_zero_padding(self):
        ml = mcl.MorningList(
            schema_version=1,
            date="2026-05-01",  # May 1 -- must render as "May 1" not "May 01"
            generated_at="2026-05-01T11:05:00Z",
            habits=[mcl.MorningListHabit(position=1, vikunja_task_id=1, title="X")],
        )
        msg = mcl.render_morning_message(ml)
        # Header line. Don't hard-code the weekday name in case the calendar
        # surprises us; just assert the month + day-without-padding.
        assert "May 1:" in msg.splitlines()[0]
        assert "May 01" not in msg

    def test_one_line_per_habit_in_order(self):
        ml = mcl.MorningList(
            schema_version=1,
            date="2026-05-22",
            generated_at="2026-05-22T11:05:00Z",
            habits=[
                mcl.MorningListHabit(position=i + 1, vikunja_task_id=i + 1, title=f"H{i+1}")
                for i in range(5)
            ],
        )
        msg = mcl.render_morning_message(ml)
        lines = msg.splitlines()
        # Lines 2..6 are the numbered habits.
        assert lines[2:7] == ["1. H1", "2. H2", "3. H3", "4. H4", "5. H5"]


# ---------------------------------------------------------------------------
# Group 7 — CLI
# ---------------------------------------------------------------------------


class TestCli:
    def test_help_exits_zero(self):
        with pytest.raises(SystemExit) as exc:
            mcl.main(["--help"])
        assert exc.value.code == 0

    def test_dry_run_emits_message_and_writes_no_file(
        self,
        monkeypatch,
        tmp_path,
        tmp_token_file,
        mock_urlopen,
        mock_state_log_dir,
        capsys,
    ):
        monkeypatch.setattr(mcl, "_today_local", lambda: "2026-05-22")
        mock_urlopen.side_effect = _vikunja_responses([
            _task(14, title="Wake at 5:00 AM"),
            _task(18, title="Meditate"),
        ])
        # Use a name distinct from the ``mock_state_log_dir`` fixture's
        # sandbox (which lives at ``tmp_path/state``); we want to verify
        # the artifact dir is left strictly untouched on dry-run.
        artifact_dir = tmp_path / "morning"

        exit_code = mcl.main([
            "--dry-run",
            "--state-dir", str(artifact_dir),
            "--base-url", "http://test/api/v1/",
            "--token-path", str(tmp_token_file),
        ])

        assert exit_code == 0
        # No file was written.
        assert not (artifact_dir / "morning-checkin-2026-05-22.json").exists()
        # No artifact dir created either -- dry-run is read-only with
        # respect to the persisted morning-list state.
        assert not artifact_dir.exists()
        # Stdout has the formatted message.
        out = capsys.readouterr().out
        assert "Morning check-in" in out
        assert "1. Wake at 5:00 AM" in out
        assert "2. Meditate" in out

    def test_real_run_persists_file_and_emits_message(
        self,
        monkeypatch,
        tmp_path,
        tmp_token_file,
        mock_urlopen,
        mock_state_log_dir,
        capsys,
    ):
        monkeypatch.setattr(mcl, "_today_local", lambda: "2026-05-22")
        mock_urlopen.side_effect = _vikunja_responses([
            _task(14, title="Wake at 5:00 AM"),
        ])
        state_dir = tmp_path / "state"

        exit_code = mcl.main([
            "--state-dir", str(state_dir),
            "--base-url", "http://test/api/v1/",
            "--token-path", str(tmp_token_file),
        ])

        assert exit_code == 0
        artifact = state_dir / "morning-checkin-2026-05-22.json"
        assert artifact.exists()
        payload = json.loads(artifact.read_text(encoding="utf-8"))
        assert payload["date"] == "2026-05-22"
        assert payload["habits"] == [
            {"position": 1, "vikunja_task_id": 14, "title": "Wake at 5:00 AM"}
        ]
        out = capsys.readouterr().out
        assert "1. Wake at 5:00 AM" in out

    def test_cli_url_error_exits_one(
        self,
        monkeypatch,
        tmp_path,
        tmp_token_file,
        mock_urlopen,
        mock_state_log_dir,
        capsys,
    ):
        monkeypatch.setattr(mcl, "_today_local", lambda: "2026-05-22")
        mock_urlopen.side_effect = urllib.error.URLError("connection refused")
        exit_code = mcl.main([
            "--state-dir", str(tmp_path / "state"),
            "--base-url", "http://test/api/v1/",
            "--token-path", str(tmp_token_file),
        ])
        assert exit_code == 1
        err = capsys.readouterr().err
        # Structured JSON line on stderr.
        line = err.strip().splitlines()[-1]
        parsed = json.loads(line)
        assert parsed["step"] == "vikunja_fetch"

    def test_cli_bad_date_exits_three(
        self,
        monkeypatch,
        tmp_path,
        tmp_token_file,
        mock_urlopen,
        capsys,
    ):
        mock_urlopen.side_effect = AssertionError("must not call HTTP")
        exit_code = mcl.main([
            "--state-dir", str(tmp_path / "state"),
            "--base-url", "http://test/api/v1/",
            "--token-path", str(tmp_token_file),
            "--date", "2026-13-99",
        ])
        assert exit_code == 3
        err = capsys.readouterr().err
        line = err.strip().splitlines()[-1]
        parsed = json.loads(line)
        assert parsed["step"] == "argparse"
        assert "YYYY-MM-DD" in parsed["error"]

    def test_cli_slash_separated_date_exits_three(
        self,
        monkeypatch,
        tmp_path,
        tmp_token_file,
        mock_urlopen,
        capsys,
    ):
        """A date that fails the regex (e.g., slash-separated) -> exit 3.

        Distinct path from ``2026-13-99`` which passes the regex but fails
        the fromisoformat semantic check.
        """
        mock_urlopen.side_effect = AssertionError("must not call HTTP")
        exit_code = mcl.main([
            "--state-dir", str(tmp_path / "state"),
            "--base-url", "http://test/api/v1/",
            "--token-path", str(tmp_token_file),
            "--date", "5/15/2026",
        ])
        assert exit_code == 3
        err = capsys.readouterr().err
        line = err.strip().splitlines()[-1]
        parsed = json.loads(line)
        assert parsed["step"] == "argparse"
        assert "YYYY-MM-DD" in parsed["error"]

    def test_cli_missing_token_exits_one(
        self,
        monkeypatch,
        tmp_path,
        mock_urlopen,
        mock_state_log_dir,
        capsys,
    ):
        """A missing token file is treated as a fetch-side failure (exit 1).

        Operationally the agent treats this the same as a Vikunja failure:
        the morning list cannot be built; file a P2-bug and IDLE.
        """
        monkeypatch.setattr(mcl, "_today_local", lambda: "2026-05-22")
        mock_urlopen.side_effect = AssertionError("must not call HTTP")
        exit_code = mcl.main([
            "--state-dir", str(tmp_path / "state"),
            "--base-url", "http://test/api/v1/",
            "--token-path", str(tmp_path / "no-such-token"),
        ])
        assert exit_code == 1
        err = capsys.readouterr().err
        # Structured stderr line.
        line = err.strip().splitlines()[-1]
        parsed = json.loads(line)
        assert parsed["step"] == "token_read"

    def test_cli_persist_failure_exits_two(
        self,
        monkeypatch,
        tmp_path,
        tmp_token_file,
        mock_urlopen,
        mock_state_log_dir,
        capsys,
    ):
        """A successful fetch followed by a persist OSError -> exit 2."""
        monkeypatch.setattr(mcl, "_today_local", lambda: "2026-05-22")
        mock_urlopen.side_effect = _vikunja_responses([_task(14, title="Wake")])

        def _exploding_persist(*args, **kwargs):
            raise OSError("simulated disk full")

        monkeypatch.setattr(mcl, "persist_morning_list", _exploding_persist)

        exit_code = mcl.main([
            "--state-dir", str(tmp_path / "state"),
            "--base-url", "http://test/api/v1/",
            "--token-path", str(tmp_token_file),
        ])
        assert exit_code == 2
        err = capsys.readouterr().err
        line = err.strip().splitlines()[-1]
        parsed = json.loads(line)
        assert parsed["step"] == "persist"

    def test_cli_exit_3_on_unknown_flag(
        self,
        mock_urlopen,
        capsys,
    ):
        """An unknown flag must exit 3 (argparse usage error), not 2.

        Per ``contracts/cli.md``, exit 2 is reserved for filesystem persistence
        failure. The default ``argparse.ArgumentParser.error()`` raises
        ``SystemExit(2)``, which would leak through ``main()``. The
        ``_StructuredArgumentParser`` subclass catches this and routes through
        the exit-3 path.
        """
        mock_urlopen.side_effect = AssertionError("must not call HTTP")
        exit_code = mcl.main(["--bogus-flag", "x"])
        assert exit_code == 3
        err = capsys.readouterr().err
        line = err.strip().splitlines()[-1]
        parsed = json.loads(line)
        assert parsed["step"] == "argparse"
        # The argparse-supplied error message mentions the offending flag.
        assert "bogus" in parsed["error"].lower() or "unrecognized" in parsed["error"].lower()

    def test_cli_exit_3_on_missing_required_value(
        self,
        mock_urlopen,
        capsys,
    ):
        """A flag missing its required value (e.g. ``--date`` with no arg)
        must exit 3, not 2."""
        mock_urlopen.side_effect = AssertionError("must not call HTTP")
        # --date expects an argument; supplying it as the trailing flag with
        # no value triggers argparse's "expected one argument" error.
        exit_code = mcl.main(["--date"])
        assert exit_code == 3
        err = capsys.readouterr().err
        line = err.strip().splitlines()[-1]
        parsed = json.loads(line)
        assert parsed["step"] == "argparse"

    def test_cli_help_still_exits_0(self):
        """The ``--help`` path uses ``parser.exit()`` not ``error()``; it must
        still exit 0 even with the ``_StructuredArgumentParser`` subclass."""
        with pytest.raises(SystemExit) as exc:
            mcl.main(["--help"])
        assert exc.value.code == 0
