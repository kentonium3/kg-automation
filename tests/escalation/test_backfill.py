"""Tests for ``scripts.escalation.backfill_jsonl_from_comments`` (Phase 6 / WP06).

Coverage targets per WP06 § Validation:

- Every Entity 3 / D5 vocabulary row has an explicit parse test
  (``level-1``, ``level-2``, ``snoozed:Nd``, ``dismissed``, ``done``,
  ``rescheduled:YYYY-MM-DD``).
- Malformed comments are collected with snippet + reason; NEVER replayed
  and NEVER routed to the hard-fail bug filer.
- Snapshot (data-model Entity 4) is written BEFORE any JSONL line is
  appended on a live run.
- Idempotency: a second run produces 0 new records (record_event's
  append-time dedup short-circuits).
- ``--dry-run`` skips both snapshot AND JSONL writes; report still
  populated.
- ``--include-resolved`` toggles terminal-task replay (default skip).
- ``backfill_all`` excludes Goals (id 11) and Habits (id 13) per
  SKILL.md § 1.
- CLI surface: ``--project-id`` + ``--all`` mutually exclusive (exit 3);
  exit codes 0/1/2/3 per contracts/cli.md.

All HTTP traffic is mocked via the ``mock_urlopen`` fixture from
``tests/escalation/conftest.py``. JSONL writes land under
``tmp_path/escalation_state`` via a ``JSONL_STATE_DIR`` monkeypatch fixture
defined locally below — mirroring the pattern from
``test_record_completion.py``.
"""
from __future__ import annotations

import io
import json
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.escalation import backfill_jsonl_from_comments as bf
from scripts.escalation import record_completion as rc
from scripts.escalation.backfill_jsonl_from_comments import (
    BackfillReport,
    MalformedComment,
    backfill_all,
    backfill_project,
    main,
    parse_comment,
)


# ---------------------------------------------------------------------------
# Local fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def jsonl_sandbox(tmp_path: Path, monkeypatch) -> Path:
    """Redirect both ``backfill.JSONL_STATE_DIR`` and
    ``backfill.SNAPSHOT_PATH``, plus ``record_completion.JSONL_STATE_DIR``,
    to a tmp directory so JSONL writes + the snapshot land inside the
    sandbox without touching the host filesystem.
    """
    sandbox = tmp_path / "escalation_state"
    sandbox.mkdir(parents=True, exist_ok=True)
    snapshot_path = sandbox / "pre-phase6-snapshot.json"
    monkeypatch.setattr(bf, "JSONL_STATE_DIR", sandbox)
    monkeypatch.setattr(bf, "SNAPSHOT_PATH", snapshot_path)
    monkeypatch.setattr(rc, "JSONL_STATE_DIR", sandbox)
    return sandbox


def _resp(payload, *, status: int = 200):
    """Build a context-manager-shaped fake urlopen response.

    Mirrors the helper in ``test_record_completion.py``.
    """
    body = (
        json.dumps(payload).encode("utf-8") if payload is not None else b""
    )
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
        msg="boom",
        hdrs=None,
        fp=io.BytesIO(body),
    )


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out


def _vikunja_task(
    task_id: int,
    *,
    title: str = "Task",
    done: bool = False,
    project_id: int = 4,
) -> dict:
    return {
        "id": task_id,
        "title": title,
        "done": done,
        "project_id": project_id,
    }


def _vikunja_comment(
    text: str,
    *,
    comment_id: int = 1,
    created: str = "2026-05-15T08:00:00Z",
) -> dict:
    return {"id": comment_id, "comment": text, "created": created}


# ---------------------------------------------------------------------------
# Group 1 — parse_comment per locked vocabulary row (data-model Entity 3 / D5)
# ---------------------------------------------------------------------------


class TestParseCommentVocabulary:
    def test_parse_level_1_sent(self):
        record = parse_comment(
            "[Felix-Escalation] 2026-05-15 | level-1 | sent",
            task_id=1234,
            project_id=4,
            task_title="Task",
        )
        assert record is not None
        assert record["state"] == "level_sent"
        assert record["level"] == 1
        assert record["date"] == "2026-05-15"
        assert record["source"] == "backfill"
        assert record["task_id"] == 1234
        assert record["project_id"] == 4
        assert record["title"] == "Task"

    def test_parse_level_2_sent(self):
        record = parse_comment(
            "[Felix-Escalation] 2026-05-15 | level-2 | sent",
            task_id=1234,
            project_id=4,
            task_title="Task",
        )
        assert record is not None
        assert record["state"] == "level_sent"
        assert record["level"] == 2

    def test_parse_snoozed_3d(self):
        # comment-date + 3 days = 2026-05-18
        record = parse_comment(
            "[Felix-Escalation] 2026-05-15 | snoozed:3d | acknowledged",
            task_id=1234,
            project_id=4,
            task_title="Task",
        )
        assert record is not None
        assert record["state"] == "snoozed"
        assert record["snooze_days"] == 3
        assert record["snooze_until"] == "2026-05-18"

    def test_parse_snoozed_7d(self):
        record = parse_comment(
            "[Felix-Escalation] 2026-05-15 | snoozed:7d | acknowledged",
            task_id=1234,
            project_id=4,
            task_title="Task",
        )
        assert record is not None
        assert record["state"] == "snoozed"
        assert record["snooze_days"] == 7
        assert record["snooze_until"] == "2026-05-22"

    def test_parse_dismissed(self):
        record = parse_comment(
            "[Felix-Escalation] 2026-05-15 | dismissed | acknowledged",
            task_id=1234,
            project_id=4,
            task_title="Task",
        )
        assert record is not None
        assert record["state"] == "dismissed"
        # No required structured params beyond the shared 7.
        assert "snooze_days" not in record
        assert "reschedule_to" not in record

    def test_parse_done(self):
        record = parse_comment(
            "[Felix-Escalation] 2026-05-15 | done | acknowledged",
            task_id=1234,
            project_id=4,
            task_title="Task",
        )
        assert record is not None
        assert record["state"] == "done"

    def test_parse_rescheduled(self):
        record = parse_comment(
            "[Felix-Escalation] 2026-05-15 | rescheduled:2026-06-15 | "
            "acknowledged",
            task_id=1234,
            project_id=4,
            task_title="Task",
        )
        assert record is not None
        assert record["state"] == "rescheduled"
        assert record["reschedule_to"] == "2026-06-15"

    def test_parse_timestamp_uses_comment_created(self):
        """Vikunja's comment.created should win over the noon-UTC placeholder."""
        record = parse_comment(
            "[Felix-Escalation] 2026-05-15 | level-1 | sent",
            task_id=1234,
            project_id=4,
            task_title="Task",
            comment_created="2026-05-15T08:00:00Z",
        )
        assert record is not None
        # Z is normalized to +00:00 for codebase symmetry.
        assert record["timestamp"] == "2026-05-15T08:00:00+00:00"

    def test_parse_timestamp_falls_back_to_noon(self):
        record = parse_comment(
            "[Felix-Escalation] 2026-05-15 | level-1 | sent",
            task_id=1234,
            project_id=4,
            task_title="Task",
            comment_created=None,
        )
        assert record is not None
        assert record["timestamp"] == "2026-05-15T12:00:00+00:00"


# ---------------------------------------------------------------------------
# Group 2 — parse_comment malformed cases
# ---------------------------------------------------------------------------


class TestParseCommentMalformed:
    def test_parse_no_felix_prefix(self):
        record = parse_comment(
            "operator wrote a note here",
            task_id=1234,
            project_id=4,
            task_title="Task",
        )
        assert record is None

    def test_parse_wrong_separator(self):
        # Comma instead of space-pipe-space.
        record = parse_comment(
            "[Felix-Escalation] 2026-05-15, level-1, sent",
            task_id=1234,
            project_id=4,
            task_title="Task",
        )
        assert record is None

    def test_parse_unknown_state(self):
        record = parse_comment(
            "[Felix-Escalation] 2026-05-15 | acknowledged | acknowledged",
            task_id=1234,
            project_id=4,
            task_title="Task",
        )
        assert record is None

    def test_parse_invalid_date(self):
        record = parse_comment(
            "[Felix-Escalation] 2026-13-99 | level-1 | sent",
            task_id=1234,
            project_id=4,
            task_title="Task",
        )
        assert record is None

    def test_parse_snoozed_invalid_days(self):
        # ``snoozed:abcd`` should be rejected (not a positive int).
        record = parse_comment(
            "[Felix-Escalation] 2026-05-15 | snoozed:abcd | acknowledged",
            task_id=1234,
            project_id=4,
            task_title="Task",
        )
        assert record is None

    def test_parse_non_string_body(self):
        # Defensive: a non-string body (e.g., Vikunja API change shipping
        # null) should be rejected without raising.
        assert parse_comment(None, 1, 4, "T") is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Group 3 — backfill_project integration (mocked Vikunja)
# ---------------------------------------------------------------------------


class TestBackfillProject:
    def test_backfill_writes_snapshot_first(
        self, mock_urlopen, jsonl_sandbox, tmp_token_file
    ):
        """Snapshot is written BEFORE any JSONL line appears.

        Asserted by capturing on-disk state at the moment the JSONL append
        path is triggered: the snapshot path MUST already exist.
        """
        jsonl_path = jsonl_sandbox / "project-4-escalation-history.jsonl"
        snapshot_path = jsonl_sandbox / "pre-phase6-snapshot.json"

        comments = [
            _vikunja_comment(
                "[Felix-Escalation] 2026-05-15 | level-1 | sent",
                comment_id=10,
            ),
        ]
        # GET /projects/4/tasks  -> 1 task
        # GET /tasks/1234/comments -> 1 comment
        mock_urlopen.side_effect = [
            _resp([_vikunja_task(1234)]),
            _resp(comments),
        ]

        # Sanity: nothing on disk yet.
        assert not jsonl_path.exists()
        assert not snapshot_path.exists()

        # Spy on write to ensure ordering. We do this via wrapping
        # idempotent_record_event so we can capture the snapshot-existence
        # at the moment of the first append. (WP06 cycle-1 fix: backfill
        # now calls idempotent_record_event, not record_event.)
        observed_snapshot_present: list[bool] = []
        original_idempotent = rc.idempotent_record_event

        def _wrap_idempotent(record, **kwargs):
            observed_snapshot_present.append(snapshot_path.exists())
            return original_idempotent(record, **kwargs)

        # backfill_project calls bf.idempotent_record_event (imported by
        # name) — patch that reference, not rc.idempotent_record_event.
        from scripts.escalation import (
            backfill_jsonl_from_comments as _bf,
        )

        _bf.idempotent_record_event = _wrap_idempotent  # type: ignore[assignment]
        try:
            report = backfill_project(
                4, token_path=tmp_token_file, base_url="http://test/api/v1/"
            )
        finally:
            _bf.idempotent_record_event = original_idempotent  # type: ignore[assignment]

        assert report.comments_replayed == 1
        assert observed_snapshot_present == [True], (
            "JSONL append occurred BEFORE the snapshot was written"
        )
        records = _read_jsonl(jsonl_path)
        assert len(records) == 1
        assert records[0]["state"] == "level_sent"
        assert records[0]["source"] == "backfill"

    def test_backfill_replays_parseable_comments(
        self, mock_urlopen, jsonl_sandbox, tmp_token_file
    ):
        """3 tasks, 5 total Felix comments (4 parseable, 1 malformed)."""
        mock_urlopen.side_effect = [
            # GET /projects/4/tasks
            _resp(
                [
                    _vikunja_task(1234),
                    _vikunja_task(1235, title="T2"),
                    _vikunja_task(1236, title="T3"),
                ]
            ),
            # GET /tasks/1234/comments -> 2 comments (1 ok + 1 malformed)
            _resp(
                [
                    _vikunja_comment(
                        "[Felix-Escalation] 2026-05-15 | level-1 | sent",
                        comment_id=10,
                    ),
                    _vikunja_comment(
                        "[Felix-Escalation] 2026-13-99 | level-1 | sent",
                        comment_id=11,
                    ),
                ]
            ),
            # GET /tasks/1235/comments -> 2 parseable
            _resp(
                [
                    _vikunja_comment(
                        "[Felix-Escalation] 2026-05-15 | level-2 | sent",
                        comment_id=20,
                    ),
                    _vikunja_comment(
                        "[Felix-Escalation] 2026-05-16 | "
                        "snoozed:3d | acknowledged",
                        comment_id=21,
                    ),
                ]
            ),
            # GET /tasks/1236/comments -> 1 parseable
            _resp(
                [
                    _vikunja_comment(
                        "[Felix-Escalation] 2026-05-17 | dismissed | "
                        "acknowledged",
                        comment_id=30,
                    ),
                ]
            ),
        ]

        report = backfill_project(
            4, token_path=tmp_token_file, base_url="http://test/api/v1/"
        )

        assert report.project_id == 4
        assert report.tasks_scanned == 3
        assert report.comments_parsed == 5
        assert report.comments_replayed == 4
        assert report.comments_malformed == 1
        assert report.dry_run is False
        assert len(report.malformed_details) == 1
        assert isinstance(report.malformed_details[0], MalformedComment)

        jsonl_path = jsonl_sandbox / "project-4-escalation-history.jsonl"
        records = _read_jsonl(jsonl_path)
        assert len(records) == 4
        assert {r["state"] for r in records} == {
            "level_sent",
            "snoozed",
            "dismissed",
        }

    def test_backfill_dry_run_no_writes(
        self, mock_urlopen, jsonl_sandbox, tmp_token_file
    ):
        mock_urlopen.side_effect = [
            _resp([_vikunja_task(1234)]),
            _resp(
                [
                    _vikunja_comment(
                        "[Felix-Escalation] 2026-05-15 | level-1 | sent",
                        comment_id=10,
                    ),
                ]
            ),
        ]

        report = backfill_project(
            4,
            token_path=tmp_token_file,
            base_url="http://test/api/v1/",
            dry_run=True,
        )

        # Report still populated; nothing on disk.
        assert report.dry_run is True
        assert report.comments_parsed == 1
        assert report.comments_replayed == 1
        assert report.snapshot_path is None
        assert not (jsonl_sandbox / "pre-phase6-snapshot.json").exists()
        assert not (
            jsonl_sandbox / "project-4-escalation-history.jsonl"
        ).exists()

    def test_backfill_skips_terminal_unless_include_resolved(
        self, mock_urlopen, jsonl_sandbox, tmp_token_file
    ):
        """``done=true`` task: skipped by default; replayed with include_resolved."""
        # First invocation: default (skip).
        mock_urlopen.side_effect = [
            _resp([_vikunja_task(1234, done=True)]),
            _resp(
                [
                    _vikunja_comment(
                        "[Felix-Escalation] 2026-05-15 | done | acknowledged",
                        comment_id=10,
                    ),
                ]
            ),
        ]
        report = backfill_project(
            4, token_path=tmp_token_file, base_url="http://test/api/v1/"
        )
        assert report.comments_parsed == 0
        assert report.comments_replayed == 0
        assert not (
            jsonl_sandbox / "project-4-escalation-history.jsonl"
        ).exists()

        # Reset mock for the include_resolved=True invocation.
        mock_urlopen.reset_mock()
        mock_urlopen.side_effect = [
            _resp([_vikunja_task(1234, done=True)]),
            _resp(
                [
                    _vikunja_comment(
                        "[Felix-Escalation] 2026-05-15 | done | acknowledged",
                        comment_id=10,
                    ),
                ]
            ),
        ]
        report = backfill_project(
            4,
            token_path=tmp_token_file,
            base_url="http://test/api/v1/",
            include_resolved=True,
        )
        assert report.comments_parsed == 1
        assert report.comments_replayed == 1
        records = _read_jsonl(
            jsonl_sandbox / "project-4-escalation-history.jsonl"
        )
        assert len(records) == 1
        assert records[0]["state"] == "done"

    def test_backfill_no_felix_comments_no_writes(
        self, mock_urlopen, jsonl_sandbox, tmp_token_file
    ):
        """Project with tasks but no Felix-prefixed comments: no-op."""
        mock_urlopen.side_effect = [
            _resp([_vikunja_task(1234)]),
            _resp(
                [
                    _vikunja_comment(
                        "operator note, no Felix prefix", comment_id=10
                    ),
                ]
            ),
        ]
        report = backfill_project(
            4, token_path=tmp_token_file, base_url="http://test/api/v1/"
        )
        assert report.tasks_scanned == 0
        assert report.comments_parsed == 0
        assert report.comments_replayed == 0
        assert report.snapshot_path is None


# ---------------------------------------------------------------------------
# Group 4 — Idempotency on rerun
# ---------------------------------------------------------------------------


class TestIdempotency:
    def test_backfill_idempotent_on_rerun(
        self, mock_urlopen, jsonl_sandbox, tmp_token_file
    ):
        """Second run produces 0 new records (dedup short-circuits append).

        Per the WP06 idempotency contract (review-cycle-1 fix):
        ``comments_replayed`` MUST count only newly appended JSONL records.
        A rerun against an already-backfilled JSONL must report
        ``comments_replayed == 0`` and ``comments_deduped == <n>`` where n
        is the number of parseable comments that were short-circuited.
        """
        # The mock is consumed sequentially; supply enough responses for
        # BOTH runs (each run: 1 tasks list + 1 comments list = 2 calls).
        comments = [
            _vikunja_comment(
                "[Felix-Escalation] 2026-05-15 | level-1 | sent",
                comment_id=10,
            ),
            _vikunja_comment(
                "[Felix-Escalation] 2026-05-16 | "
                "snoozed:3d | acknowledged",
                comment_id=11,
            ),
        ]
        mock_urlopen.side_effect = [
            _resp([_vikunja_task(1234)]),
            _resp(comments),
            _resp([_vikunja_task(1234)]),
            _resp(comments),
        ]

        report1 = backfill_project(
            4, token_path=tmp_token_file, base_url="http://test/api/v1/"
        )
        # First run on a clean JSONL: every parseable comment is appended.
        assert report1.comments_replayed == 2
        assert report1.comments_deduped == 0

        jsonl_path = jsonl_sandbox / "project-4-escalation-history.jsonl"
        records_after_first = _read_jsonl(jsonl_path)
        assert len(records_after_first) == 2

        # Second invocation. idempotent_record_event's pre-check short-
        # circuits on (task_id, date, state); the on-disk record count must
        # NOT grow AND the counters MUST reflect the no-op outcome.
        report2 = backfill_project(
            4, token_path=tmp_token_file, base_url="http://test/api/v1/"
        )
        records_after_second = _read_jsonl(jsonl_path)
        assert len(records_after_second) == 2
        assert records_after_first == records_after_second

        # Contract assertions (review-cycle-1 fix): rerun reports 0 new
        # appends and surfaces the deduped count for operator visibility.
        assert report2.comments_replayed == 0
        assert report2.comments_deduped == 2
        # comments_parsed is unchanged across runs — the count of
        # [Felix-Escalation] comments inspected doesn't depend on JSONL state.
        assert report2.comments_parsed == report1.comments_parsed

    def test_first_run_comments_replayed_matches_appends(
        self, mock_urlopen, jsonl_sandbox, tmp_token_file
    ):
        """On a clean JSONL, comments_replayed equals the appended record count.

        Guards the contract direction opposite to ``test_backfill_idempotent_
        on_rerun``: when nothing is on disk, every parseable comment must
        result in exactly one new JSONL line AND increment comments_replayed.
        """
        comments = [
            _vikunja_comment(
                "[Felix-Escalation] 2026-05-15 | level-1 | sent",
                comment_id=10,
            ),
            _vikunja_comment(
                "[Felix-Escalation] 2026-05-16 | "
                "snoozed:3d | acknowledged",
                comment_id=11,
            ),
            _vikunja_comment(
                "[Felix-Escalation] 2026-05-17 | dismissed | acknowledged",
                comment_id=12,
            ),
        ]
        mock_urlopen.side_effect = [
            _resp([_vikunja_task(1234)]),
            _resp(comments),
        ]

        report = backfill_project(
            4, token_path=tmp_token_file, base_url="http://test/api/v1/"
        )
        jsonl_path = jsonl_sandbox / "project-4-escalation-history.jsonl"
        appended = _read_jsonl(jsonl_path)

        assert report.comments_replayed == len(appended) == 3
        assert report.comments_deduped == 0
        assert report.comments_parsed == 3


# ---------------------------------------------------------------------------
# Group 5 — Malformed report contents
# ---------------------------------------------------------------------------


class TestMalformedReport:
    def test_malformed_report_includes_snippet_and_reason(
        self, mock_urlopen, jsonl_sandbox, tmp_token_file
    ):
        long_bad = (
            "[Felix-Escalation] 2026-13-99 | level-1 | sent "
            "extra-trailing-text-to-test-the-80-char-snippet-truncation-"
            "is-applied-correctly-here"
        )
        mock_urlopen.side_effect = [
            _resp([_vikunja_task(1234)]),
            _resp(
                [
                    _vikunja_comment(long_bad, comment_id=10),
                ]
            ),
        ]
        report = backfill_project(
            4, token_path=tmp_token_file, base_url="http://test/api/v1/"
        )
        assert report.comments_malformed == 1
        m = report.malformed_details[0]
        assert isinstance(m, MalformedComment)
        # Snippet truncated to first 80 chars.
        assert len(m.snippet) <= 80
        assert m.snippet == long_bad[:80]
        assert m.task_id == 1234
        assert m.project_id == 4
        # Reason is a non-empty, descriptive string.
        assert m.reason
        assert isinstance(m.reason, str)

    def test_malformed_never_replayed(
        self, mock_urlopen, jsonl_sandbox, tmp_token_file
    ):
        """Malformed comment present ⇒ no JSONL record for it.

        Explicit guard against the "we accidentally append the malformed
        line anyway" regression mentioned in research D5.
        """
        mock_urlopen.side_effect = [
            _resp([_vikunja_task(1234)]),
            _resp(
                [
                    _vikunja_comment(
                        "[Felix-Escalation] 2026-13-99 | level-1 | sent",
                        comment_id=10,
                    ),
                ]
            ),
        ]
        report = backfill_project(
            4, token_path=tmp_token_file, base_url="http://test/api/v1/"
        )
        assert report.comments_malformed == 1
        assert report.comments_replayed == 0
        # File should not even exist — nothing to write.
        assert not (
            jsonl_sandbox / "project-4-escalation-history.jsonl"
        ).exists()


# ---------------------------------------------------------------------------
# Group 6 — Snapshot schema
# ---------------------------------------------------------------------------


class TestSnapshot:
    def test_snapshot_schema_v1(
        self, mock_urlopen, jsonl_sandbox, tmp_token_file
    ):
        mock_urlopen.side_effect = [
            _resp([_vikunja_task(1234, title="Email Q3 board summary")]),
            _resp(
                [
                    _vikunja_comment(
                        "[Felix-Escalation] 2026-05-15 | level-1 | sent",
                        comment_id=5678,
                        created="2026-05-15T08:00:00Z",
                    ),
                    _vikunja_comment(
                        "[Felix-Escalation] 2026-05-17 | level-2 | sent",
                        comment_id=5901,
                        created="2026-05-17T08:00:00Z",
                    ),
                ]
            ),
        ]
        backfill_project(
            4, token_path=tmp_token_file, base_url="http://test/api/v1/"
        )

        snapshot_path = jsonl_sandbox / "pre-phase6-snapshot.json"
        assert snapshot_path.exists()
        snap = json.loads(snapshot_path.read_text(encoding="utf-8"))

        # Entity 4 schema invariants.
        assert snap["snapshot_version"] == 1
        # created_at parses as ISO-8601.
        datetime.fromisoformat(snap["created_at"])
        assert isinstance(snap["tool_version"], str)
        assert isinstance(snap["tasks"], list)
        assert len(snap["tasks"]) == 1
        task = snap["tasks"][0]
        assert task["task_id"] == 1234
        assert task["project_id"] == 4
        assert task["title"] == "Email Q3 board summary"
        assert "vikunja_url" in task
        assert isinstance(task["felix_comments"], list)
        assert len(task["felix_comments"]) == 2
        first = task["felix_comments"][0]
        assert first["comment_id"] == 5678
        assert first["created"] == "2026-05-15T08:00:00Z"
        assert first["comment"].startswith("[Felix-Escalation]")

    def test_snapshot_not_written_when_no_felix_comments(
        self, mock_urlopen, jsonl_sandbox, tmp_token_file
    ):
        """No Felix-tagged tasks ⇒ no snapshot file."""
        mock_urlopen.side_effect = [
            _resp([_vikunja_task(1234)]),
            _resp([_vikunja_comment("operator note", comment_id=10)]),
        ]
        report = backfill_project(
            4, token_path=tmp_token_file, base_url="http://test/api/v1/"
        )
        assert report.snapshot_path is None
        assert not (jsonl_sandbox / "pre-phase6-snapshot.json").exists()


# ---------------------------------------------------------------------------
# Group 7 — backfill_all: Goals + Habits exclusion
# ---------------------------------------------------------------------------


class TestBackfillAll:
    def test_backfill_all_excludes_goals_and_habits_projects(
        self, mock_urlopen, jsonl_sandbox, tmp_token_file
    ):
        # GET /projects -> 4 projects: Habits (13), Goals (11), and two
        # ordinary projects (4 + 7). Only 4 + 7 should be visited.
        # Each visited project triggers two more calls (tasks + comments
        # for each task). To keep the mock simple, give each ordinary
        # project an empty task list — backfill_project will short-circuit
        # after the GET /tasks call.
        mock_urlopen.side_effect = [
            _resp(
                [
                    {"id": 13, "title": "Habits"},
                    {"id": 11, "title": "Goals"},
                    {"id": 4, "title": "Everyday"},
                    {"id": 7, "title": "Projects"},
                ]
            ),
            # GET /projects/4/tasks
            _resp([]),
            # GET /projects/7/tasks
            _resp([]),
        ]

        reports = backfill_all(
            token_path=tmp_token_file, base_url="http://test/api/v1/"
        )

        # Two reports — for projects 4 and 7. Habits (13) and Goals (11)
        # are excluded.
        assert len(reports) == 2
        assert {r.project_id for r in reports} == {4, 7}

    def test_backfill_all_handles_empty_project_list(
        self, mock_urlopen, jsonl_sandbox, tmp_token_file
    ):
        mock_urlopen.side_effect = [_resp([])]
        reports = backfill_all(
            token_path=tmp_token_file, base_url="http://test/api/v1/"
        )
        assert reports == []


# ---------------------------------------------------------------------------
# Group 8 — CLI surface
# ---------------------------------------------------------------------------


class TestCli:
    def test_cli_help_exits_zero(self, capsys):
        # ``main()`` catches argparse's SystemExit and returns the code
        # directly (so it can map exit-2 usage errors to exit-3 per
        # contracts/cli.md). --help still surfaces 0.
        rc_code = main(["--help"])
        assert rc_code == 0
        captured = capsys.readouterr()
        assert "Phase 6" in captured.out or "backfill" in captured.out.lower()

    def test_cli_requires_project_id_or_all(self, capsys):
        # No target flag at all: argparse error → main maps exit-2 to 3.
        rc_code = main([])
        assert rc_code == 3

    def test_cli_project_id_and_all_mutually_exclusive(self, capsys):
        rc_code = main(["--project-id", "4", "--all"])
        assert rc_code == 3

    def test_cli_token_missing_exits_3(self, tmp_path, capsys):
        rc_code = main(
            [
                "--project-id",
                "4",
                "--token-path",
                str(tmp_path / "absent-token"),
                "--base-url",
                "http://test/api/v1/",
            ]
        )
        assert rc_code == 3
        captured = capsys.readouterr()
        assert "token" in captured.err.lower()

    def test_cli_token_empty_exits_3(self, tmp_path, capsys):
        empty = tmp_path / "empty-token"
        empty.write_text("")
        rc_code = main(
            [
                "--project-id",
                "4",
                "--token-path",
                str(empty),
                "--base-url",
                "http://test/api/v1/",
            ]
        )
        assert rc_code == 3

    def test_cli_vikunja_failure_exits_1(
        self, mock_urlopen, jsonl_sandbox, tmp_token_file, capsys
    ):
        # First call (GET /projects/4/tasks) raises HTTP 500.
        mock_urlopen.side_effect = _http_error(500)
        rc_code = main(
            [
                "--project-id",
                "4",
                "--token-path",
                str(tmp_token_file),
                "--base-url",
                "http://test/api/v1/",
            ]
        )
        assert rc_code == 1
        captured = capsys.readouterr()
        assert "vikunja" in captured.err.lower()

    def test_cli_emits_summary_and_malformed_stdout(
        self, mock_urlopen, jsonl_sandbox, tmp_token_file, capsys
    ):
        mock_urlopen.side_effect = [
            _resp([_vikunja_task(1234)]),
            _resp(
                [
                    _vikunja_comment(
                        "[Felix-Escalation] 2026-05-15 | level-1 | sent",
                        comment_id=10,
                    ),
                    _vikunja_comment(
                        "[Felix-Escalation] 2026-13-99 | level-1 | sent",
                        comment_id=11,
                    ),
                ]
            ),
        ]
        rc_code = main(
            [
                "--project-id",
                "4",
                "--token-path",
                str(tmp_token_file),
                "--base-url",
                "http://test/api/v1/",
            ]
        )
        assert rc_code == 0
        captured = capsys.readouterr()
        # Per contracts/cli.md: per-malformed line + final JSON summary.
        assert "MALFORMED task=1234" in captured.out
        # Final summary parses as JSON.
        # Locate the JSON block (after the malformed lines).
        summary_start = captured.out.find("{")
        assert summary_start != -1
        summary = json.loads(captured.out[summary_start:])
        assert summary["project_id"] == 4
        assert summary["comments_replayed"] == 1
        assert summary["comments_malformed"] == 1

    def test_cli_dry_run_no_writes(
        self, mock_urlopen, jsonl_sandbox, tmp_token_file, capsys
    ):
        mock_urlopen.side_effect = [
            _resp([_vikunja_task(1234)]),
            _resp(
                [
                    _vikunja_comment(
                        "[Felix-Escalation] 2026-05-15 | level-1 | sent",
                        comment_id=10,
                    ),
                ]
            ),
        ]
        rc_code = main(
            [
                "--project-id",
                "4",
                "--dry-run",
                "--token-path",
                str(tmp_token_file),
                "--base-url",
                "http://test/api/v1/",
            ]
        )
        assert rc_code == 0
        # Nothing on disk.
        assert not (
            jsonl_sandbox / "project-4-escalation-history.jsonl"
        ).exists()
        assert not (jsonl_sandbox / "pre-phase6-snapshot.json").exists()

    def test_cli_all_emits_aggregate_summary(
        self, mock_urlopen, jsonl_sandbox, tmp_token_file, capsys
    ):
        mock_urlopen.side_effect = [
            # /projects -> [4]
            _resp([{"id": 4, "title": "Everyday"}]),
            # /projects/4/tasks
            _resp([]),
        ]
        rc_code = main(
            [
                "--all",
                "--token-path",
                str(tmp_token_file),
                "--base-url",
                "http://test/api/v1/",
            ]
        )
        assert rc_code == 0
        captured = capsys.readouterr()
        # The --all summary carries a "projects" list and "totals" block.
        summary_start = captured.out.find("{")
        summary = json.loads(captured.out[summary_start:])
        assert "projects" in summary
        assert "totals" in summary
