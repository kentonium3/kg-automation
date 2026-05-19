"""Tests for scripts/habits/backfill_jsonl_from_comments.py (WP01 / T002).

Covers the ``backfill()`` Python API and the ``__main__`` CLI surface.
All Vikunja HTTP traffic is mocked via ``urllib.request.urlopen``; state_log
I/O is sandboxed via the ``mock_state_log_dir`` fixture from conftest.

Test layout mirrors the WP01 spec's Steps 2-8:

  - TestProjectResolution     (zero / one / many "Habits" projects)
  - TestSnapshot              (created / skipped / failure)
  - TestBackfillDryRun        (happy path / unmapped / malformed)
  - TestBackfillLive          (happy path / source / timestamp / state map)
  - TestIdempotency           (re-run → dedup-skip)
  - TestErrorHandling         (project enum / comment fetch / validation)
  - TestCLI                   (--help / --dry-run / live / token / project)

Each test scripts a sequence of Vikunja responses via
``mock_urlopen.side_effect`` — the helper makes 1 GET /projects + 1 GET
/projects/<id>/tasks + N GETs /tasks/<id>/comments per task.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.common import state_log
from scripts.habits import backfill_jsonl_from_comments as bf


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


def _http_error(code: int = 500, body: bytes = b'{"message":"boom"}'):
    return urllib.error.HTTPError(
        url="http://test/",
        code=code,
        msg="Server Error",
        hdrs=None,
        fp=io.BytesIO(body),
    )


HABITS_PROJECT_ID = 42


def _projects_payload(*, with_habits: bool = True, duplicates: int = 0):
    """Return a Vikunja-shaped ``GET /projects`` payload."""
    out: list[dict] = [{"id": 1, "title": "Inbox"}, {"id": 99, "title": "Goals"}]
    if with_habits:
        out.append({"id": HABITS_PROJECT_ID, "title": "Habits"})
    for i in range(duplicates):
        # Add additional Habits-titled projects to drive the "0 or >1 match"
        # path. Use distinct ids.
        out.append({"id": 200 + i, "title": "Habits"})
    return out


def _task(task_id: int, title: str = "Habit") -> dict:
    return {"id": task_id, "title": title}


def _felix_comment(
    comment_id: int,
    date: str,
    state: str,
    note: str | None = None,
    created: str = "2026-05-19T11:00:00+00:00",
) -> dict:
    body = f"[Felix] {date} | {state}"
    if note:
        body = body + f" | {note}"
    return {"id": comment_id, "comment": body, "created": created}


def _responses(*, projects=None, tasks=None, comments_by_task=None):
    """Build the urlopen side_effect sequence.

    Order:
      1. GET /projects
      2. GET /projects/<id>/tasks?filter=is_archived=false
      3. GET /tasks/<task_id>/comments  (one per task, in the order tasks
         appear in ``tasks``)

    ``comments_by_task`` is a dict {task_id: [comment_dict, ...]} OR a dict
    {task_id: Exception_instance | callable} for failure injection.
    """
    if projects is None:
        projects = _projects_payload()
    if tasks is None:
        tasks = []
    if comments_by_task is None:
        comments_by_task = {}
    seq = [_resp(projects), _resp(tasks)]
    for task in tasks:
        tid = task["id"]
        value = comments_by_task.get(tid, [])
        if isinstance(value, Exception):
            seq.append(value)
        else:
            seq.append(_resp(value))
    return seq


# ===========================================================================
# Group 1 — Project resolution
# ===========================================================================


class TestProjectResolution:
    def test_resolves_unique_habits_project(self, mock_urlopen):
        mock_urlopen.return_value = _resp(_projects_payload())
        pid = bf._resolve_habits_project_id("http://test/api/v1/", "t")
        assert pid == HABITS_PROJECT_ID

    def test_zero_matches_raises_value_error(self, mock_urlopen):
        mock_urlopen.return_value = _resp(_projects_payload(with_habits=False))
        with pytest.raises(ValueError, match="not uniquely resolvable"):
            bf._resolve_habits_project_id("http://test/api/v1/", "t")

    def test_multiple_matches_raises_value_error(self, mock_urlopen):
        mock_urlopen.return_value = _resp(_projects_payload(duplicates=2))
        with pytest.raises(ValueError, match="found 3 matches"):
            bf._resolve_habits_project_id("http://test/api/v1/", "t")

    def test_non_list_payload_raises_oserror(self, mock_urlopen):
        mock_urlopen.return_value = _resp({"not": "a list"})
        with pytest.raises(OSError, match="non-list payload"):
            bf._resolve_habits_project_id("http://test/api/v1/", "t")

    def test_http_error_propagates_as_oserror(self, mock_urlopen):
        mock_urlopen.side_effect = _http_error(500)
        with pytest.raises(OSError):
            bf._resolve_habits_project_id("http://test/api/v1/", "t")


# ===========================================================================
# Group 2 — Snapshot
# ===========================================================================


class TestSnapshot:
    def test_snapshot_created_when_source_exists(
        self, mock_state_log_dir, tmp_path
    ):
        # Pre-seed source.
        src = mock_state_log_dir / "habits-history.jsonl"
        src.write_text('{"foo": "bar"}\n', encoding="utf-8")
        original_mtime = src.stat().st_mtime

        target, created = bf._snapshot_jsonl(mock_state_log_dir)
        assert target is not None
        assert created is True
        assert target.name == "habits-history.jsonl" + bf.SNAPSHOT_SUFFIX
        assert target.read_text(encoding="utf-8") == '{"foo": "bar"}\n'
        # copy2 preserves mtime.
        assert target.stat().st_mtime == pytest.approx(original_mtime, abs=1.0)

    def test_snapshot_skipped_when_source_missing(self, mock_state_log_dir):
        # No JSONL exists yet.
        target, created = bf._snapshot_jsonl(mock_state_log_dir)
        assert target is None
        assert created is False
        # No .bak file was created.
        bak = mock_state_log_dir / ("habits-history.jsonl" + bf.SNAPSHOT_SUFFIX)
        assert not bak.exists()

    def test_snapshot_failure_raises_snapshot_error(
        self, mock_state_log_dir, monkeypatch
    ):
        src = mock_state_log_dir / "habits-history.jsonl"
        src.write_text("x\n", encoding="utf-8")

        def boom(*args, **kwargs):
            raise PermissionError("no write")

        monkeypatch.setattr(shutil, "copy2", boom)
        with pytest.raises(bf._SnapshotError, match="snapshot copy failed"):
            bf._snapshot_jsonl(mock_state_log_dir)

    def test_bak_preserved_on_second_call(self, mock_state_log_dir):
        """Regression for WP01 cycle-1 finding 1.

        After the first call writes the .bak, a second call must NOT
        overwrite it. The .bak content (representing the true pre-backfill
        state) must survive verbatim and ``created`` must report ``False``.
        """
        src = mock_state_log_dir / "habits-history.jsonl"
        src.write_text("original-pre-backfill-content\n", encoding="utf-8")

        # First call: snapshot created.
        target1, created1 = bf._snapshot_jsonl(mock_state_log_dir)
        assert target1 is not None
        assert created1 is True

        # Simulate the JSONL evolving (backfill records appended).
        src.write_text(
            "original-pre-backfill-content\nappended-by-backfill\n",
            encoding="utf-8",
        )

        # Second call: snapshot preserved, not overwritten.
        target2, created2 = bf._snapshot_jsonl(mock_state_log_dir)
        assert target2 == target1
        assert created2 is False
        # .bak still contains only the pre-backfill content.
        assert (
            target2.read_text(encoding="utf-8")
            == "original-pre-backfill-content\n"
        )

    def test_bak_not_overwritten_on_second_live_run(
        self, mock_urlopen, mock_state_log_dir
    ):
        """Regression for WP01 cycle-1 finding 1 — end-to-end through backfill().

        First live run creates a .bak. We then append a marker line to the
        .bak. After a second live run, the marker line MUST still be present
        (the .bak was NOT overwritten).
        """
        # Seed a prior JSONL line so the snapshot path triggers.
        state_log.append(
            "habits",
            {
                "domain": "habits",
                "task_id": 99,
                "title": "Prior unrelated habit",
                "date": "2026-05-01",
                "state": "complete",
                "source": "vikunja-ui",
                "timestamp": "2026-05-01T11:00:00+00:00",
            },
        )

        tasks = [_task(14, "Wake")]
        comments = {14: [_felix_comment(101, "2026-05-15", "complete")]}
        mock_urlopen.side_effect = _responses(
            tasks=tasks, comments_by_task=comments
        )

        # First live run: creates the .bak.
        first = bf.backfill("http://test/api/v1/", "t", dry_run=False)
        bak = mock_state_log_dir / (
            "habits-history.jsonl" + bf.SNAPSHOT_SUFFIX
        )
        assert bak.exists()
        assert first["snapshot_created"] is True

        # Add a marker line so we can prove the .bak was NOT overwritten.
        bak_pre = bak.read_text(encoding="utf-8")
        bak.write_text(bak_pre + "BACKFILL_MARKER\n", encoding="utf-8")
        assert "BACKFILL_MARKER" in bak.read_text(encoding="utf-8")

        # Re-script the mock for run #2 (full sequence again).
        mock_urlopen.side_effect = _responses(
            tasks=tasks, comments_by_task=comments
        )
        second = bf.backfill("http://test/api/v1/", "t", dry_run=False)

        # The .bak still contains the marker — was preserved, not overwritten.
        assert "BACKFILL_MARKER" in bak.read_text(encoding="utf-8")
        # Summary records the preservation.
        assert second["snapshot_path"] == str(bak)
        assert second["snapshot_created"] is False
        # Formatter surfaces the preservation note.
        out = bf._format_summary(second)
        assert "preserved from a prior run" in out


# ===========================================================================
# Group 3 — backfill() dry-run
# ===========================================================================


class TestBackfillDryRun:
    def test_dry_run_counts_planned_no_appends(
        self, mock_urlopen, mock_state_log_dir
    ):
        tasks = [_task(14, "Wake at 5:00 AM"), _task(15, "Meditate")]
        comments = {
            14: [
                _felix_comment(101, "2026-05-15", "complete"),
                _felix_comment(102, "2026-05-16", "complete"),
            ],
            15: [
                _felix_comment(201, "2026-05-15", "complete"),
                _felix_comment(202, "2026-05-16", "will-not-do"),
            ],
        }
        mock_urlopen.side_effect = _responses(
            tasks=tasks, comments_by_task=comments
        )

        result = bf.backfill(
            "http://test/api/v1/", "t", dry_run=True
        )

        assert result["run_mode"] == "dry-run"
        assert result["habits_project_id"] == HABITS_PROJECT_ID
        assert result["tasks_enumerated"] == 2
        assert result["comments_fetched"] == 4
        assert result["records_planned"] == 4
        assert result["records_appended"] == 0
        assert result["records_skipped_dedup"] == 0
        assert result["records_skipped_unmapped"] == 0
        assert result["records_skipped_malformed"] == 0
        assert result["by_state"] == {"complete": 3, "skipped": 1}
        assert result["snapshot_path"] is None
        # No JSONL was written.
        jsonl = mock_state_log_dir / "habits-history.jsonl"
        assert not jsonl.exists()
        # No .bak file either.
        bak = mock_state_log_dir / ("habits-history.jsonl" + bf.SNAPSHOT_SUFFIX)
        assert not bak.exists()

    def test_dry_run_records_unmapped_state(
        self, mock_urlopen, mock_state_log_dir
    ):
        tasks = [_task(14, "Wake")]
        comments = {
            14: [
                _felix_comment(101, "2026-05-15", "complete"),
                _felix_comment(102, "2026-05-16", "partial", note="tweaked back"),
            ],
        }
        mock_urlopen.side_effect = _responses(
            tasks=tasks, comments_by_task=comments
        )

        result = bf.backfill("http://test/api/v1/", "t", dry_run=True)
        assert result["records_planned"] == 1
        assert result["records_skipped_unmapped"] == 1
        assert len(result["unmapped_state_values"]) == 1
        entry = result["unmapped_state_values"][0]
        assert entry["task_id"] == 14
        assert entry["state"] == "partial"
        assert entry["date"] == "2026-05-16"
        assert "partial" in entry["comment_snippet"]

    def test_dry_run_records_malformed_felix_comment(
        self, mock_urlopen, mock_state_log_dir
    ):
        tasks = [_task(14, "Wake")]
        # Starts with [Felix] but fails the regex (missing pipe).
        bad = {
            "id": 999,
            "comment": "[Felix] not a real format here",
            "created": "2026-05-19T11:00:00+00:00",
        }
        comments = {
            14: [
                _felix_comment(101, "2026-05-15", "complete"),
                bad,
                {
                    "id": 102,
                    "comment": "Just a regular comment from Kent",
                    "created": "2026-05-19T11:01:00+00:00",
                },
            ],
        }
        mock_urlopen.side_effect = _responses(
            tasks=tasks, comments_by_task=comments
        )

        result = bf.backfill("http://test/api/v1/", "t", dry_run=True)
        assert result["records_planned"] == 1
        assert result["records_skipped_malformed"] == 1
        # Non-[Felix] comment must NOT count as malformed.
        assert result["comments_fetched"] == 3

    def test_malformed_comment_snippets_in_report(
        self, mock_urlopen, mock_state_log_dir
    ):
        """Regression for WP01 cycle-1 finding 2.

        FR-009 requires the summary report to include COUNT + SNIPPETS for
        malformed [Felix] comments. The cycle-1 implementation only counted.
        This test mocks two malformed comments and asserts both the count
        and the snippets (with task_id) appear in the formatted report.
        """
        tasks = [_task(14, "Wake"), _task(18, "PT")]
        malformed_1 = {
            "id": 501,
            "comment": (
                "[Felix] Took my Wake-at-5am note out of the inbox folder today"
            ),
            "created": "2026-05-19T11:00:00+00:00",
        }
        malformed_2 = {
            "id": 519,
            "comment": "[Felix] (intentionally blank)",
            "created": "2026-05-19T11:01:00+00:00",
        }
        comments = {
            14: [
                _felix_comment(101, "2026-05-15", "complete"),
                malformed_1,
            ],
            18: [malformed_2],
        }
        mock_urlopen.side_effect = _responses(
            tasks=tasks, comments_by_task=comments
        )

        result = bf.backfill("http://test/api/v1/", "t", dry_run=True)

        # Both malformed comments counted.
        assert result["records_skipped_malformed"] == 2
        # Both snippets captured with task_id + comment_id.
        assert len(result["malformed_comments"]) == 2
        by_task = {e["task_id"]: e for e in result["malformed_comments"]}
        assert 14 in by_task
        assert 18 in by_task
        assert by_task[14]["comment_id"] == 501
        assert by_task[18]["comment_id"] == 519
        assert "Wake-at-5am" in by_task[14]["snippet"]
        assert "intentionally blank" in by_task[18]["snippet"]

        # Formatted report contains both snippets, prefixed with task_id.
        out = bf._format_summary(result)
        assert "Comments skipped as malformed: 2" in out
        assert "task_id=14" in out
        assert "Wake-at-5am" in out
        assert "task_id=18" in out
        assert "intentionally blank" in out

    def test_malformed_snippet_trimmed_to_80_chars(
        self, mock_urlopen, mock_state_log_dir
    ):
        """Long malformed comments are trimmed to the first 80 chars (per
        the existing unmapped-snippet convention)."""
        tasks = [_task(14, "Wake")]
        long_text = "[Felix] " + ("X" * 200)
        bad = {
            "id": 999,
            "comment": long_text,
            "created": "2026-05-19T11:00:00+00:00",
        }
        mock_urlopen.side_effect = _responses(
            tasks=tasks, comments_by_task={14: [bad]}
        )
        result = bf.backfill("http://test/api/v1/", "t", dry_run=True)
        assert result["records_skipped_malformed"] == 1
        assert len(result["malformed_comments"]) == 1
        assert len(result["malformed_comments"][0]["snippet"]) == 80


# ===========================================================================
# Group 4 — backfill() live
# ===========================================================================


class TestBackfillLive:
    def test_live_appends_records_with_correct_provenance(
        self, mock_urlopen, mock_state_log_dir
    ):
        tasks = [_task(14, "Wake at 5:00 AM"), _task(15, "Meditate")]
        comments = {
            14: [
                _felix_comment(
                    101, "2026-05-15", "complete",
                    created="2026-05-15T11:00:00+00:00",
                ),
                _felix_comment(
                    102, "2026-05-16", "complete",
                    created="2026-05-16T11:00:00+00:00",
                ),
                _felix_comment(
                    103, "2026-05-17", "will-not-do",
                    note="travel day",
                    created="2026-05-17T11:00:00+00:00",
                ),
            ],
            15: [
                _felix_comment(
                    201, "2026-05-15", "complete",
                    created="2026-05-15T11:30:00+00:00",
                ),
                _felix_comment(
                    202, "2026-05-16", "complete",
                    created="2026-05-16T11:30:00+00:00",
                ),
            ],
        }
        mock_urlopen.side_effect = _responses(
            tasks=tasks, comments_by_task=comments
        )

        result = bf.backfill("http://test/api/v1/", "t", dry_run=False)
        assert result["run_mode"] == "live"
        assert result["records_appended"] == 5
        assert result["records_planned"] == 0
        assert result["by_state"] == {"complete": 4, "skipped": 1}

        # Snapshot SKIPPED because no prior JSONL existed.
        assert result["snapshot_path"] is None
        bak = mock_state_log_dir / ("habits-history.jsonl" + bf.SNAPSHOT_SUFFIX)
        assert not bak.exists()

        # Read back: source attribution + timestamp pass-through.
        records = state_log.read("habits")
        assert len(records) == 5
        for r in records:
            assert r["source"] == "historical-backfill"
        # Spot-check one record.
        wake_records = state_log.read("habits", task_id=14)
        assert len(wake_records) == 3
        ts_for_complete = [
            r["timestamp"] for r in wake_records if r["state"] == "complete"
        ]
        assert "2026-05-15T11:00:00+00:00" in ts_for_complete
        assert "2026-05-16T11:00:00+00:00" in ts_for_complete

    def test_live_state_map_correctness(
        self, mock_urlopen, mock_state_log_dir
    ):
        tasks = [_task(14, "Wake")]
        comments = {
            14: [
                _felix_comment(101, "2026-05-15", "complete"),
                _felix_comment(
                    102, "2026-05-16", "will-not-do",
                    note="sick",
                ),
            ],
        }
        mock_urlopen.side_effect = _responses(
            tasks=tasks, comments_by_task=comments
        )

        bf.backfill("http://test/api/v1/", "t", dry_run=False)

        complete_records = state_log.read("habits", state="complete")
        skipped_records = state_log.read("habits", state="skipped")
        assert len(complete_records) == 1
        assert len(skipped_records) == 1
        assert skipped_records[0]["note"] == "sick"

    def test_live_snapshot_created_when_prior_jsonl_exists(
        self, mock_urlopen, mock_state_log_dir
    ):
        # Seed an existing JSONL line (from some other source).
        state_log.append(
            "habits",
            {
                "domain": "habits",
                "task_id": 99,
                "title": "Prior unrelated habit",
                "date": "2026-05-01",
                "state": "complete",
                "source": "vikunja-ui",
                "timestamp": "2026-05-01T11:00:00+00:00",
            },
        )

        tasks = [_task(14, "Wake")]
        comments = {
            14: [_felix_comment(101, "2026-05-15", "complete")],
        }
        mock_urlopen.side_effect = _responses(
            tasks=tasks, comments_by_task=comments
        )

        result = bf.backfill("http://test/api/v1/", "t", dry_run=False)
        assert result["records_appended"] == 1
        # Snapshot was created.
        bak = mock_state_log_dir / ("habits-history.jsonl" + bf.SNAPSHOT_SUFFIX)
        assert bak.exists()
        assert result["snapshot_path"] == str(bak)
        # Snapshot content reflects the pre-backfill JSONL — one prior line.
        bak_lines = [
            json.loads(ln) for ln in bak.read_text(encoding="utf-8").splitlines() if ln
        ]
        assert len(bak_lines) == 1
        assert bak_lines[0]["task_id"] == 99

    def test_live_zero_comment_task_appears_in_report(
        self, mock_urlopen, mock_state_log_dir
    ):
        tasks = [_task(14, "Wake"), _task(75, "Strength training — Monday")]
        comments = {
            14: [_felix_comment(101, "2026-05-15", "complete")],
            75: [],  # new MWF task — no prior comments
        }
        mock_urlopen.side_effect = _responses(
            tasks=tasks, comments_by_task=comments
        )

        result = bf.backfill("http://test/api/v1/", "t", dry_run=False)
        assert result["records_appended"] == 1
        # Zero-comment task still present in by_task with count=0.
        assert 75 in result["by_task"]
        assert result["by_task"][75]["count"] == 0
        # Formatted summary should mention the empty task.
        out = bf._format_summary(result)
        assert "task_id=75" in out


# ===========================================================================
# Group 5 — Idempotency
# ===========================================================================


class TestIdempotency:
    def test_second_run_is_dedup_noop(
        self, mock_urlopen, mock_state_log_dir
    ):
        tasks = [_task(14, "Wake")]
        comments = {
            14: [
                _felix_comment(101, "2026-05-15", "complete"),
                _felix_comment(102, "2026-05-16", "complete"),
            ],
        }
        mock_urlopen.side_effect = _responses(
            tasks=tasks, comments_by_task=comments
        )

        first = bf.backfill("http://test/api/v1/", "t", dry_run=False)
        assert first["records_appended"] == 2
        assert first["records_skipped_dedup"] == 0

        # Re-script the mock for run #2 (full sequence again).
        mock_urlopen.side_effect = _responses(
            tasks=tasks, comments_by_task=comments
        )
        second = bf.backfill("http://test/api/v1/", "t", dry_run=False)
        assert second["records_appended"] == 0
        assert second["records_skipped_dedup"] == 2

        # JSONL line count unchanged.
        jsonl = mock_state_log_dir / "habits-history.jsonl"
        lines = jsonl.read_text(encoding="utf-8").splitlines()
        assert len([ln for ln in lines if ln.strip()]) == 2


# ===========================================================================
# Group 6 — Error handling
# ===========================================================================


class TestErrorHandling:
    def test_project_enumeration_failure_propagates_as_oserror(
        self, mock_urlopen, mock_state_log_dir
    ):
        # /projects ok, /tasks fails.
        mock_urlopen.side_effect = [
            _resp(_projects_payload()),
            _http_error(500),
        ]
        with pytest.raises(OSError):
            bf.backfill("http://test/api/v1/", "t", dry_run=True)

    def test_per_task_comment_fetch_failure_logged_as_anomaly(
        self, mock_urlopen, mock_state_log_dir
    ):
        tasks = [_task(14, "Wake"), _task(15, "Meditate")]
        # Comments for 14 succeed; comments for 15 raise. The backfill
        # must continue to subsequent tasks (but in this case 15 is last).
        mock_urlopen.side_effect = [
            _resp(_projects_payload()),
            _resp(tasks),
            _resp([_felix_comment(101, "2026-05-15", "complete")]),
            _http_error(404),
        ]

        result = bf.backfill("http://test/api/v1/", "t", dry_run=False)
        # Task 14's comment was appended.
        assert result["records_appended"] == 1
        # Task 15 contributed an anomaly.
        assert any(
            a.get("task_id") == 15 and "comment fetch failed" in a["message"]
            for a in result["anomalies"]
        )

    def test_other_tasks_processed_after_one_task_fetch_fails(
        self, mock_urlopen, mock_state_log_dir
    ):
        tasks = [_task(14, "Wake"), _task(15, "Meditate"), _task(16, "PT")]
        mock_urlopen.side_effect = [
            _resp(_projects_payload()),
            _resp(tasks),
            # Task 14: error.
            _http_error(500),
            # Task 15: success.
            _resp([_felix_comment(201, "2026-05-15", "complete")]),
            # Task 16: success.
            _resp([_felix_comment(301, "2026-05-15", "complete")]),
        ]
        result = bf.backfill("http://test/api/v1/", "t", dry_run=False)
        # Task 14 anomaly, tasks 15 + 16 appended.
        assert result["records_appended"] == 2
        assert len(result["anomalies"]) == 1
        assert result["anomalies"][0]["task_id"] == 14

    def test_comment_missing_created_logged_as_anomaly(
        self, mock_urlopen, mock_state_log_dir
    ):
        tasks = [_task(14, "Wake")]
        bad = {
            "id": 999,
            "comment": "[Felix] 2026-05-15 | complete",
            # no 'created' field
        }
        comments = {14: [bad, _felix_comment(101, "2026-05-16", "complete")]}
        mock_urlopen.side_effect = _responses(
            tasks=tasks, comments_by_task=comments
        )

        result = bf.backfill("http://test/api/v1/", "t", dry_run=False)
        assert result["records_appended"] == 1
        assert any(
            "missing 'created' field" in a["message"]
            for a in result["anomalies"]
        )

    def test_invalid_task_id_logged_as_anomaly(
        self, mock_urlopen, mock_state_log_dir
    ):
        tasks = [
            {"id": None, "title": "Bad task"},
            _task(14, "Wake"),
        ]
        # Bad task has no id — its comments are NOT fetched, so the side
        # effect sequence only needs the projects + tasks + comments-for-14
        # responses.
        mock_urlopen.side_effect = [
            _resp(_projects_payload()),
            _resp(tasks),
            _resp([_felix_comment(101, "2026-05-15", "complete")]),
        ]
        result = bf.backfill("http://test/api/v1/", "t", dry_run=False)
        assert result["records_appended"] == 1
        assert any(
            "missing or invalid 'id'" in a["message"]
            for a in result["anomalies"]
        )

    def test_validation_failure_logged_and_skipped(
        self, mock_urlopen, mock_state_log_dir
    ):
        # Comment with an invalid timestamp (no timezone) — validate_record
        # rejects it.
        tasks = [_task(14, "Wake")]
        bad = {
            "id": 999,
            "comment": "[Felix] 2026-05-15 | complete",
            "created": "2026-05-15T11:00:00",  # no offset
        }
        comments = {14: [bad, _felix_comment(101, "2026-05-16", "complete")]}
        mock_urlopen.side_effect = _responses(
            tasks=tasks, comments_by_task=comments
        )

        result = bf.backfill("http://test/api/v1/", "t", dry_run=False)
        assert result["records_appended"] == 1
        assert result["records_skipped_validation"] == 1
        assert any(
            "record validation failed" in a["message"]
            for a in result["anomalies"]
        )

    def test_snapshot_failure_raises_snapshot_error_from_backfill(
        self, mock_urlopen, mock_state_log_dir, monkeypatch
    ):
        # Seed a prior JSONL so snapshot is attempted.
        state_log.append(
            "habits",
            {
                "domain": "habits",
                "task_id": 99,
                "title": "x",
                "date": "2026-05-01",
                "state": "complete",
                "source": "vikunja-ui",
                "timestamp": "2026-05-01T11:00:00+00:00",
            },
        )
        # Make shutil.copy2 fail.
        monkeypatch.setattr(
            shutil, "copy2",
            lambda *a, **k: (_ for _ in ()).throw(PermissionError("denied")),
        )
        mock_urlopen.side_effect = _responses(
            tasks=[_task(14, "Wake")],
            comments_by_task={14: [_felix_comment(101, "2026-05-15", "complete")]},
        )
        with pytest.raises(bf._SnapshotError):
            bf.backfill("http://test/api/v1/", "t", dry_run=False)


# ===========================================================================
# Group 7 — CLI
# ===========================================================================


class TestCLI:
    def test_help_exits_zero(self, capsys):
        with pytest.raises(SystemExit) as exc:
            bf.main(["--help"])
        assert exc.value.code == 0

    def test_dry_run_cli_prints_report_and_exits_zero(
        self, mock_urlopen, mock_state_log_dir, tmp_token_file, capsys
    ):
        tasks = [_task(14, "Wake")]
        comments = {14: [_felix_comment(101, "2026-05-15", "complete")]}
        mock_urlopen.side_effect = _responses(
            tasks=tasks, comments_by_task=comments
        )
        exit_code = bf.main([
            "--dry-run",
            "--token-file", str(tmp_token_file),
            "--base-url", "http://test/api/v1/",
        ])
        assert exit_code == 0
        out = capsys.readouterr().out
        assert "Run mode: dry-run" in out
        assert "Planned: 1" in out
        # No JSONL written in dry-run.
        jsonl = mock_state_log_dir / "habits-history.jsonl"
        assert not jsonl.exists()

    def test_live_cli_appends_and_exits_zero(
        self, mock_urlopen, mock_state_log_dir, tmp_token_file, capsys
    ):
        tasks = [_task(14, "Wake")]
        comments = {14: [_felix_comment(101, "2026-05-15", "complete")]}
        mock_urlopen.side_effect = _responses(
            tasks=tasks, comments_by_task=comments
        )
        exit_code = bf.main([
            "--token-file", str(tmp_token_file),
            "--base-url", "http://test/api/v1/",
        ])
        assert exit_code == 0
        out = capsys.readouterr().out
        assert "Run mode: live" in out
        assert "Appended: 1" in out
        # JSONL was written.
        records = state_log.read("habits")
        assert len(records) == 1

    def test_missing_token_file_exits_two(
        self, mock_urlopen, mock_state_log_dir, tmp_path, capsys
    ):
        exit_code = bf.main([
            "--token-file", str(tmp_path / "nonexistent"),
            "--base-url", "http://test/api/v1/",
        ])
        assert exit_code == 2
        err = capsys.readouterr().err
        assert "token file not found" in err

    def test_empty_token_file_exits_two(
        self, mock_urlopen, mock_state_log_dir, tmp_path, capsys
    ):
        empty = tmp_path / "empty-token"
        empty.write_text("", encoding="utf-8")
        exit_code = bf.main([
            "--token-file", str(empty),
            "--base-url", "http://test/api/v1/",
        ])
        assert exit_code == 2

    def test_project_resolution_failure_exits_two(
        self, mock_urlopen, mock_state_log_dir, tmp_token_file, capsys
    ):
        # /projects returns no Habits project.
        mock_urlopen.return_value = _resp(
            _projects_payload(with_habits=False)
        )
        exit_code = bf.main([
            "--token-file", str(tmp_token_file),
            "--base-url", "http://test/api/v1/",
        ])
        assert exit_code == 2
        err = capsys.readouterr().err
        assert "not uniquely resolvable" in err

    def test_enumerate_http_failure_exits_one(
        self, mock_urlopen, mock_state_log_dir, tmp_token_file, capsys
    ):
        mock_urlopen.side_effect = [
            _resp(_projects_payload()),
            _http_error(500),
        ]
        exit_code = bf.main([
            "--token-file", str(tmp_token_file),
            "--base-url", "http://test/api/v1/",
        ])
        assert exit_code == 1
        err = capsys.readouterr().err
        assert "backfill failed" in err

    def test_snapshot_failure_exits_three(
        self, mock_urlopen, mock_state_log_dir, tmp_token_file,
        monkeypatch, capsys,
    ):
        # Seed a prior JSONL so snapshot is attempted.
        state_log.append(
            "habits",
            {
                "domain": "habits",
                "task_id": 99,
                "title": "x",
                "date": "2026-05-01",
                "state": "complete",
                "source": "vikunja-ui",
                "timestamp": "2026-05-01T11:00:00+00:00",
            },
        )
        monkeypatch.setattr(
            shutil, "copy2",
            lambda *a, **k: (_ for _ in ()).throw(PermissionError("denied")),
        )
        mock_urlopen.side_effect = _responses(
            tasks=[_task(14, "Wake")],
            comments_by_task={
                14: [_felix_comment(101, "2026-05-15", "complete")]
            },
        )
        exit_code = bf.main([
            "--token-file", str(tmp_token_file),
            "--base-url", "http://test/api/v1/",
        ])
        assert exit_code == 3

    def test_enumerate_uses_project_scoped_endpoint(
        self, mock_urlopen, mock_state_log_dir, tmp_token_file
    ):
        """Regression: backfill MUST enumerate /projects/<id>/tasks, not /tasks/all."""
        mock_urlopen.side_effect = _responses(tasks=[])
        bf.main([
            "--dry-run",
            "--token-file", str(tmp_token_file),
            "--base-url", "http://test/api/v1/",
        ])
        # First call: /projects. Second call: /projects/<id>/tasks?...
        assert len(mock_urlopen.call_args_list) >= 2
        projects_req = mock_urlopen.call_args_list[0][0][0]
        assert projects_req.full_url.endswith("/projects")
        tasks_req = mock_urlopen.call_args_list[1][0][0]
        assert f"projects/{HABITS_PROJECT_ID}/tasks" in tasks_req.full_url
        assert "tasks/all" not in tasks_req.full_url


# ===========================================================================
# Group 8 — Misc unit tests for helpers
# ===========================================================================


class TestHelpers:
    def test_state_map_locked_content(self):
        assert bf.HISTORICAL_STATE_MAP == {
            "complete": "complete",
            "will-not-do": "skipped",
        }

    def test_join_url_normalizes_trailing_slash(self):
        assert bf._join_url("http://a/api/v1", "/projects") == "http://a/api/v1/projects"
        assert bf._join_url("http://a/api/v1/", "projects") == "http://a/api/v1/projects"

    def test_build_record_shape(self):
        import re as _re
        task = {"id": 14, "title": "Wake"}
        comment = {"id": 101, "comment": "[Felix] 2026-05-15 | complete | note",
                   "created": "2026-05-15T11:00:00+00:00"}
        m = bf.FELIX_COMMENT_PATTERN.search(comment["comment"])
        rec = bf._build_record(task, comment, m)
        assert rec["domain"] == "habits"
        assert rec["task_id"] == 14
        assert rec["title"] == "Wake"
        assert rec["date"] == "2026-05-15"
        assert rec["state"] == "complete"
        assert rec["source"] == "historical-backfill"
        assert rec["note"] == "note"
        assert rec["timestamp"] == "2026-05-15T11:00:00+00:00"

    def test_build_record_will_not_do_maps_to_skipped(self):
        task = {"id": 14, "title": "Wake"}
        comment = {"id": 101, "comment": "[Felix] 2026-05-15 | will-not-do",
                   "created": "2026-05-15T11:00:00+00:00"}
        m = bf.FELIX_COMMENT_PATTERN.search(comment["comment"])
        rec = bf._build_record(task, comment, m)
        assert rec["state"] == "skipped"
        assert rec["note"] is None

    def test_format_summary_dry_run_has_planned_section(self):
        summary = bf.backfill.__wrapped__ if hasattr(bf.backfill, "__wrapped__") else None
        # Build a fake summary by hand so we don't have to drive the HTTP path.
        s = {
            "run_mode": "dry-run",
            "started_at": "2026-05-19T20:30:00+00:00",
            "finished_at": "2026-05-19T20:30:15+00:00",
            "habits_project_id": 42,
            "tasks_enumerated": 0,
            "comments_fetched": 0,
            "records_appended": 0,
            "records_planned": 3,
            "records_skipped_dedup": 0,
            "records_skipped_unmapped": 0,
            "records_skipped_malformed": 0,
            "records_skipped_validation": 0,
            "anomalies": [],
            "unmapped_state_values": [],
            "by_task": {},
            "by_state": {"complete": 3},
            "snapshot_path": None,
        }
        out = bf._format_summary(s)
        assert "Run mode: dry-run" in out
        assert "Planned: 3" in out
        assert "complete: 3" in out
        assert "Unmapped state values:" in out
        assert "(none in this run)" in out

    def test_format_summary_live_with_unmapped_states(self):
        s = {
            "run_mode": "live",
            "started_at": "2026-05-19T20:30:00+00:00",
            "finished_at": "2026-05-19T20:30:15+00:00",
            "habits_project_id": 42,
            "tasks_enumerated": 1,
            "comments_fetched": 2,
            "records_appended": 1,
            "records_planned": 0,
            "records_skipped_dedup": 0,
            "records_skipped_unmapped": 1,
            "records_skipped_malformed": 0,
            "records_skipped_validation": 0,
            "anomalies": [
                {
                    "task_id": 65,
                    "message": "HTTP 404 fetching comments",
                },
            ],
            "unmapped_state_values": [
                {
                    "task_id": 17,
                    "comment_id": 503,
                    "date": "2026-05-12",
                    "state": "partial",
                    "comment_snippet": "[Felix] 2026-05-12 | partial",
                },
            ],
            "by_task": {17: {"title": "PT", "count": 1}},
            "by_state": {"complete": 1},
            "snapshot_path": "/tmp/snap.bak",
        }
        out = bf._format_summary(s)
        assert "Run mode: live" in out
        assert "Appended: 1" in out
        assert "Skipped (unmapped state): 1" in out
        assert "task_id=17" in out
        assert "partial" in out
        assert "/tmp/snap.bak" in out
        # Anomaly entry rendered.
        assert "task_id=65" in out
        assert "HTTP 404" in out
