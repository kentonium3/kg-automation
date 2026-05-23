"""Tests for ``scripts.enrichment.reconcile_completions`` (WP02 / T004, T006).

Coverage targets per WP02 § Validation:

- Happy path: 5 enrichment comments -> 5 JSONL rows via record_completion
- FR-007 disambiguation: 3 enrichment + 2 habit comments -> only 3 rows
- FR-009 idempotency: re-run on the same comment set -> 0 new rows
- FR-008 window filter: comments before --since cutoff skipped
- --dry-run: no writes, full report (parseable + malformed counts populated)
- CLI exit codes 0/1/3
- Malformed comments surfaced in report; never replayed
- Excluded projects (Goals=11, Habits=13) skipped
- Internal helpers: parse_comment, _is_habit_comment, _record_is_in_window

All Vikunja HTTP traffic is mocked via the ``mock_urlopen`` fixture. JSONL
writes land under ``tmp_path``.
"""
from __future__ import annotations

import io
import json
import sys
import urllib.error
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.enrichment import reconcile_completions as recon
from scripts.enrichment.reconcile_completions import (
    DEFAULT_BACKFILL_SINCE,
    EXCLUDED_PROJECT_IDS,
    FELIX_COMMENT_PREFIX,
    MalformedComment,
    ReconcileReport,
    _is_habit_comment,
    _parse_since,
    _record_is_in_window,
    main,
    parse_comment,
    reconcile,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_vikunja_token() -> str:
    return "test-enrichment-recon-token"


@pytest.fixture
def tmp_token_file(tmp_path: Path, fake_vikunja_token: str) -> Path:
    import os

    token_path = tmp_path / "token"
    token_path.write_text(fake_vikunja_token + "\n", encoding="utf-8")
    os.chmod(token_path, 0o600)
    return token_path


@pytest.fixture
def ledger_path(tmp_path: Path) -> Path:
    return tmp_path / "state" / "enrichment" / "enrichment-history.jsonl"


@pytest.fixture
def activity_log_sandbox(tmp_path: Path, monkeypatch) -> Path:
    """Redirect record_completion's ACTIVITY_LOG_DIR to a tmp dir.

    Otherwise the activity-log write inside record_event tries to write
    under ``~/second-brain/agents/logs/enrichment/`` on every test invocation.
    """
    from scripts.enrichment import record_completion as rc_mod

    sandbox = tmp_path / "logs" / "enrichment"
    monkeypatch.setattr(rc_mod, "ACTIVITY_LOG_DIR", sandbox)
    return sandbox


# ---------------------------------------------------------------------------
# Vikunja-mock helpers (urllib-level mock)
# ---------------------------------------------------------------------------


def _resp(payload, *, status: int = 200):
    """Build a context-manager-shaped fake urlopen response."""
    body = json.dumps(payload).encode("utf-8") if payload is not None else b""
    resp = MagicMock(name="response")
    resp.status = status
    resp.read = MagicMock(return_value=body)
    cm = MagicMock(name="cm")
    cm.__enter__ = MagicMock(return_value=resp)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


def _make_vikunja_url_router(*, projects, project_tasks, task_comments):
    """Return a side_effect callable routing on the Request URL.

    Args:
        projects: list[dict] returned by GET /projects
        project_tasks: dict[int, list[dict]] keyed on project_id
        task_comments: dict[int, list[dict]] keyed on task_id

    Returns:
        Callable suitable for ``mock_urlopen.side_effect`` that inspects the
        Request URL, decodes the path, and returns an appropriate canned
        response.
    """

    def _side_effect(request, *args, **kwargs):
        url = request.full_url if hasattr(request, "full_url") else str(request)
        # /projects (exact suffix)
        if url.endswith("/projects"):
            return _resp(projects)
        # /projects/<id>/tasks
        if "/projects/" in url and url.endswith("/tasks"):
            pid_str = url.rsplit("/projects/", 1)[1].split("/", 1)[0]
            pid = int(pid_str)
            return _resp(project_tasks.get(pid, []))
        # /tasks/<id>/comments
        if "/tasks/" in url and url.endswith("/comments"):
            tid_str = url.rsplit("/tasks/", 1)[1].split("/", 1)[0]
            tid = int(tid_str)
            return _resp(task_comments.get(tid, []))
        raise AssertionError(f"unrouted URL: {url}")

    return _side_effect


@pytest.fixture
def mock_urlopen(monkeypatch):
    """Monkey-patch ``urllib.request.urlopen`` to a MagicMock."""
    mock = MagicMock(name="urlopen")
    monkeypatch.setattr("urllib.request.urlopen", mock)
    return mock


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


def _make_felix_enrichment_comment(
    *,
    comment_id: int,
    task_id: int,
    state: str,
    timestamp_utc: str,
    note: str | None = None,
) -> dict:
    body = f"[Felix] enrichment | {state} | {timestamp_utc}"
    if note:
        body += f" | {note}"
    return {"id": comment_id, "comment": body, "created": timestamp_utc}


def _make_felix_habit_comment(
    *,
    comment_id: int,
    date_str: str,
    state: str = "done",
) -> dict:
    body = f"[Felix] {date_str} | {state}"
    return {"id": comment_id, "comment": body, "created": f"{date_str}T08:00:00Z"}


# ---------------------------------------------------------------------------
# Unit tests — internal helpers
# ---------------------------------------------------------------------------


class TestHabitDisambiguation:
    """FR-007 disambiguation: literal ``enrichment`` vs ``YYYY-MM-DD`` in field 2."""

    @pytest.mark.parametrize(
        "body, expected",
        [
            ("[Felix] 2026-05-23 | done", True),
            ("[Felix] 2026-04-11 | skipped | note", True),
            # Leading whitespace after the prefix tolerated.
            ("[Felix]  2026-05-23 | done", True),
            # Enrichment comments are NOT habit comments.
            ("[Felix] enrichment | proposed | 2026-05-23T19:00:00Z", False),
            # Plain non-Felix comments are not habit either.
            ("just a comment", False),
            # Non-strings and missing prefix.
            ("", False),
        ],
    )
    def test_is_habit_recognizes_shape(self, body, expected):
        assert _is_habit_comment(body) is expected

    def test_is_habit_rejects_non_string(self):
        assert _is_habit_comment(None) is False
        assert _is_habit_comment(123) is False

    def test_is_habit_rejects_bad_date(self):
        """Not-a-date in the second field is NOT a habit comment."""
        assert _is_habit_comment("[Felix] not-a-date | done") is False
        # Partial-date shape (missing two digits) is rejected.
        assert _is_habit_comment("[Felix] 2026-5-23 | done") is False


class TestParseComment:
    def test_parses_minimal_enrichment_comment(self):
        record, reason = parse_comment(
            "[Felix] enrichment | proposed | 2026-05-23T19:00:00Z",
            task_id=42,
        )
        assert reason is None
        assert record == {
            "task_id": 42,
            "state": "proposed",
            "timestamp_utc": "2026-05-23T19:00:00Z",
            "source": "backfill",
            "schema_version": 1,
            "note": None,
        }

    def test_parses_comment_with_note(self):
        record, reason = parse_comment(
            "[Felix] enrichment | skipped | 2026-05-23T19:00:00Z | kent skipped",
            task_id=42,
        )
        assert reason is None
        assert record is not None
        assert record["state"] == "skipped"
        assert record["note"] == "kent skipped"

    @pytest.mark.parametrize(
        "state", ["proposed", "confirmed", "skipped", "declined"]
    )
    def test_parses_all_4_states(self, state):
        record, _ = parse_comment(
            f"[Felix] enrichment | {state} | 2026-05-23T19:00:00Z",
            task_id=1,
        )
        assert record is not None
        assert record["state"] == state

    def test_rejects_unknown_state_token(self):
        record, reason = parse_comment(
            "[Felix] enrichment | weird_state | 2026-05-23T19:00:00Z",
            task_id=1,
        )
        assert record is None
        assert "unknown state token" in (reason or "")
        assert "weird_state" in (reason or "")

    def test_rejects_invalid_timestamp(self):
        record, reason = parse_comment(
            "[Felix] enrichment | proposed | not-a-timestamp",
            task_id=1,
        )
        assert record is None
        assert "invalid timestamp" in (reason or "")

    def test_rejects_regex_mismatch(self):
        record, reason = parse_comment(
            "totally malformed comment",
            task_id=1,
        )
        assert record is None
        assert "regex mismatch" in (reason or "")

    def test_rejects_non_string_body(self):
        record, reason = parse_comment(None, task_id=1)
        assert record is None
        assert "non-string" in (reason or "")


class TestSinceWindowAndParse:
    def test_parse_since_happy(self):
        assert _parse_since("2026-04-11") == date(2026, 4, 11)

    def test_parse_since_invalid_raises(self):
        with pytest.raises(recon._DateParseError):
            _parse_since("not-a-date")

    def test_record_in_window_inclusive(self):
        rec = {"timestamp_utc": "2026-04-11T00:00:00Z"}
        assert _record_is_in_window(rec, date(2026, 4, 11)) is True

    def test_record_in_window_after(self):
        rec = {"timestamp_utc": "2026-05-23T12:00:00Z"}
        assert _record_is_in_window(rec, date(2026, 4, 11)) is True

    def test_record_out_of_window(self):
        rec = {"timestamp_utc": "2026-04-10T23:59:59Z"}
        assert _record_is_in_window(rec, date(2026, 4, 11)) is False

    def test_record_missing_timestamp_out_of_window(self):
        assert _record_is_in_window({}, date(2026, 4, 11)) is False

    def test_record_bad_timestamp_format_out_of_window(self):
        rec = {"timestamp_utc": "garbage"}
        assert _record_is_in_window(rec, date(2026, 4, 11)) is False


# ---------------------------------------------------------------------------
# Integration tests — full reconcile sweep
# ---------------------------------------------------------------------------


class TestReconcileHappyPath:
    def test_5_enrichment_comments_produce_5_jsonl_rows(
        self,
        mock_urlopen,
        tmp_token_file,
        ledger_path,
        activity_log_sandbox,
    ):
        """Happy path: 5 enrichment comments across 2 tasks -> 5 JSONL rows."""
        projects = [{"id": 5}]
        project_tasks = {
            5: [{"id": 100}, {"id": 200}],
        }
        task_comments = {
            100: [
                _make_felix_enrichment_comment(
                    comment_id=1,
                    task_id=100,
                    state="proposed",
                    timestamp_utc="2026-05-20T10:00:00Z",
                ),
                _make_felix_enrichment_comment(
                    comment_id=2,
                    task_id=100,
                    state="confirmed",
                    timestamp_utc="2026-05-20T11:00:00Z",
                ),
            ],
            200: [
                _make_felix_enrichment_comment(
                    comment_id=3,
                    task_id=200,
                    state="proposed",
                    timestamp_utc="2026-05-21T10:00:00Z",
                ),
                _make_felix_enrichment_comment(
                    comment_id=4,
                    task_id=200,
                    state="skipped",
                    timestamp_utc="2026-05-21T11:00:00Z",
                ),
                _make_felix_enrichment_comment(
                    comment_id=5,
                    task_id=200,
                    state="declined",
                    timestamp_utc="2026-05-21T12:00:00Z",
                ),
            ],
        }
        mock_urlopen.side_effect = _make_vikunja_url_router(
            projects=projects,
            project_tasks=project_tasks,
            task_comments=task_comments,
        )

        report = reconcile(
            since=date(2026, 4, 11),
            token_path=tmp_token_file,
            ledger_path=ledger_path,
        )

        assert report.comments_parsed == 5
        assert report.enrichment_comments_found == 5
        assert report.habit_comments_skipped == 0
        assert report.comments_replayed == 5
        assert report.comments_deduped == 0
        assert report.comments_out_of_window == 0
        assert report.malformed_details == []

        rows = _read_jsonl(ledger_path)
        assert len(rows) == 5
        assert {(r["task_id"], r["state"]) for r in rows} == {
            (100, "proposed"),
            (100, "confirmed"),
            (200, "proposed"),
            (200, "skipped"),
            (200, "declined"),
        }
        assert all(r["source"] == "backfill" for r in rows)

    def test_excluded_projects_skipped(
        self,
        mock_urlopen,
        tmp_token_file,
        ledger_path,
        activity_log_sandbox,
    ):
        """Projects 11 (Goals) and 13 (Habits) are excluded from the sweep."""
        projects = [
            {"id": 5},   # included
            {"id": 11},  # excluded (Goals)
            {"id": 13},  # excluded (Habits)
        ]
        project_tasks = {
            5: [{"id": 100}],
            11: [{"id": 1100}],
            13: [{"id": 1300}],
        }
        task_comments = {
            100: [
                _make_felix_enrichment_comment(
                    comment_id=1,
                    task_id=100,
                    state="proposed",
                    timestamp_utc="2026-05-20T10:00:00Z",
                )
            ],
            1100: [
                _make_felix_enrichment_comment(
                    comment_id=2,
                    task_id=1100,
                    state="proposed",
                    timestamp_utc="2026-05-20T10:00:00Z",
                )
            ],
            1300: [
                _make_felix_enrichment_comment(
                    comment_id=3,
                    task_id=1300,
                    state="proposed",
                    timestamp_utc="2026-05-20T10:00:00Z",
                )
            ],
        }
        mock_urlopen.side_effect = _make_vikunja_url_router(
            projects=projects,
            project_tasks=project_tasks,
            task_comments=task_comments,
        )

        report = reconcile(
            since=date(2026, 4, 11),
            token_path=tmp_token_file,
            ledger_path=ledger_path,
        )

        # Only project 5 was swept -> 1 row.
        assert report.comments_replayed == 1
        rows = _read_jsonl(ledger_path)
        assert len(rows) == 1
        assert rows[0]["task_id"] == 100


class TestReconcileDisambiguation:
    def test_3_enrichment_plus_2_habit_yields_3_rows(
        self,
        mock_urlopen,
        tmp_token_file,
        ledger_path,
        activity_log_sandbox,
    ):
        """FR-007: habit comments share the [Felix] prefix; reconcile skips them.

        Mixed list of 3 enrichment + 2 habit comments on the same task ->
        only 3 enrichment rows in the JSONL ledger.
        """
        projects = [{"id": 5}]
        project_tasks = {5: [{"id": 100}]}
        task_comments = {
            100: [
                _make_felix_enrichment_comment(
                    comment_id=1,
                    task_id=100,
                    state="proposed",
                    timestamp_utc="2026-05-20T10:00:00Z",
                ),
                _make_felix_habit_comment(
                    comment_id=2, date_str="2026-05-20", state="done"
                ),
                _make_felix_enrichment_comment(
                    comment_id=3,
                    task_id=100,
                    state="confirmed",
                    timestamp_utc="2026-05-20T11:00:00Z",
                ),
                _make_felix_habit_comment(
                    comment_id=4, date_str="2026-05-21", state="skipped"
                ),
                _make_felix_enrichment_comment(
                    comment_id=5,
                    task_id=100,
                    state="skipped",
                    timestamp_utc="2026-05-21T10:00:00Z",
                ),
            ],
        }
        mock_urlopen.side_effect = _make_vikunja_url_router(
            projects=projects,
            project_tasks=project_tasks,
            task_comments=task_comments,
        )

        report = reconcile(
            since=date(2026, 4, 11),
            token_path=tmp_token_file,
            ledger_path=ledger_path,
        )

        assert report.comments_parsed == 5
        assert report.habit_comments_skipped == 2
        assert report.enrichment_comments_found == 3
        assert report.comments_replayed == 3
        assert report.malformed_details == []

        rows = _read_jsonl(ledger_path)
        assert len(rows) == 3
        assert {r["state"] for r in rows} == {
            "proposed",
            "confirmed",
            "skipped",
        }


class TestReconcileIdempotency:
    def test_rerun_on_same_comments_writes_zero_new_rows(
        self,
        mock_urlopen,
        tmp_token_file,
        ledger_path,
        activity_log_sandbox,
    ):
        """FR-009: re-running on the same comment set -> 0 new rows."""
        projects = [{"id": 5}]
        project_tasks = {5: [{"id": 100}]}
        task_comments = {
            100: [
                _make_felix_enrichment_comment(
                    comment_id=1,
                    task_id=100,
                    state="proposed",
                    timestamp_utc="2026-05-20T10:00:00Z",
                ),
                _make_felix_enrichment_comment(
                    comment_id=2,
                    task_id=100,
                    state="confirmed",
                    timestamp_utc="2026-05-20T11:00:00Z",
                ),
            ]
        }
        # MagicMock.side_effect must be reset between runs since
        # _make_vikunja_url_router returns a fresh closure.
        side_effect = _make_vikunja_url_router(
            projects=projects,
            project_tasks=project_tasks,
            task_comments=task_comments,
        )
        mock_urlopen.side_effect = side_effect

        # Run 1: fresh ledger.
        report1 = reconcile(
            since=date(2026, 4, 11),
            token_path=tmp_token_file,
            ledger_path=ledger_path,
        )
        assert report1.comments_replayed == 2
        rows_after_first = _read_jsonl(ledger_path)
        assert len(rows_after_first) == 2

        # Run 2: same comments.
        mock_urlopen.side_effect = _make_vikunja_url_router(
            projects=projects,
            project_tasks=project_tasks,
            task_comments=task_comments,
        )
        report2 = reconcile(
            since=date(2026, 4, 11),
            token_path=tmp_token_file,
            ledger_path=ledger_path,
        )
        assert report2.comments_replayed == 0
        assert report2.comments_deduped == 2
        rows_after_second = _read_jsonl(ledger_path)
        assert len(rows_after_second) == 2


class TestReconcileWindowFilter:
    def test_comments_before_since_skipped(
        self,
        mock_urlopen,
        tmp_token_file,
        ledger_path,
        activity_log_sandbox,
    ):
        """FR-008: comments older than --since are counted but not replayed."""
        projects = [{"id": 5}]
        project_tasks = {5: [{"id": 100}]}
        task_comments = {
            100: [
                # Way before cutoff
                _make_felix_enrichment_comment(
                    comment_id=1,
                    task_id=100,
                    state="proposed",
                    timestamp_utc="2026-01-15T10:00:00Z",
                ),
                # Exactly on cutoff
                _make_felix_enrichment_comment(
                    comment_id=2,
                    task_id=100,
                    state="confirmed",
                    timestamp_utc="2026-04-11T10:00:00Z",
                ),
                # After cutoff
                _make_felix_enrichment_comment(
                    comment_id=3,
                    task_id=100,
                    state="skipped",
                    timestamp_utc="2026-05-20T11:00:00Z",
                ),
            ]
        }
        mock_urlopen.side_effect = _make_vikunja_url_router(
            projects=projects,
            project_tasks=project_tasks,
            task_comments=task_comments,
        )

        report = reconcile(
            since=date(2026, 4, 11),  # cutoff inclusive
            token_path=tmp_token_file,
            ledger_path=ledger_path,
        )

        assert report.enrichment_comments_found == 3
        assert report.comments_out_of_window == 1
        assert report.comments_replayed == 2

        rows = _read_jsonl(ledger_path)
        assert len(rows) == 2
        states = {r["state"] for r in rows}
        assert states == {"confirmed", "skipped"}

    def test_since_as_string_parses(
        self,
        mock_urlopen,
        tmp_token_file,
        ledger_path,
        activity_log_sandbox,
    ):
        """``since`` accepted as a YYYY-MM-DD string (CLI compatibility)."""
        projects = [{"id": 5}]
        project_tasks = {5: [{"id": 100}]}
        task_comments = {
            100: [
                _make_felix_enrichment_comment(
                    comment_id=1,
                    task_id=100,
                    state="proposed",
                    timestamp_utc="2026-05-20T10:00:00Z",
                )
            ]
        }
        mock_urlopen.side_effect = _make_vikunja_url_router(
            projects=projects,
            project_tasks=project_tasks,
            task_comments=task_comments,
        )
        report = reconcile(
            since="2026-04-11",
            token_path=tmp_token_file,
            ledger_path=ledger_path,
        )
        assert report.comments_replayed == 1


class TestReconcileDryRun:
    def test_dry_run_no_writes(
        self,
        mock_urlopen,
        tmp_token_file,
        ledger_path,
        activity_log_sandbox,
    ):
        """``dry_run=True``: report populated; ledger file is NOT created."""
        projects = [{"id": 5}]
        project_tasks = {5: [{"id": 100}]}
        task_comments = {
            100: [
                _make_felix_enrichment_comment(
                    comment_id=1,
                    task_id=100,
                    state="proposed",
                    timestamp_utc="2026-05-20T10:00:00Z",
                ),
                _make_felix_enrichment_comment(
                    comment_id=2,
                    task_id=100,
                    state="confirmed",
                    timestamp_utc="2026-05-20T11:00:00Z",
                ),
            ]
        }
        mock_urlopen.side_effect = _make_vikunja_url_router(
            projects=projects,
            project_tasks=project_tasks,
            task_comments=task_comments,
        )
        report = reconcile(
            since=date(2026, 4, 11),
            token_path=tmp_token_file,
            ledger_path=ledger_path,
            dry_run=True,
        )

        assert report.dry_run is True
        assert report.comments_replayed == 2  # upper bound
        assert report.comments_deduped == 0  # no pre-check on dry-run
        assert not ledger_path.exists(), (
            "dry-run must not create the ledger file"
        )


class TestReconcileMalformed:
    def test_malformed_enrichment_comment_surfaced(
        self,
        mock_urlopen,
        tmp_token_file,
        ledger_path,
        activity_log_sandbox,
    ):
        """Malformed enrichment comments NOT replayed; surfaced in report."""
        projects = [{"id": 5}]
        project_tasks = {5: [{"id": 100}]}
        task_comments = {
            100: [
                _make_felix_enrichment_comment(
                    comment_id=1,
                    task_id=100,
                    state="proposed",
                    timestamp_utc="2026-05-20T10:00:00Z",
                ),
                # Malformed: unknown state token
                {
                    "id": 2,
                    "comment": "[Felix] enrichment | bogus | 2026-05-20T11:00:00Z",
                    "created": "2026-05-20T11:00:00Z",
                },
                # Malformed: invalid timestamp
                {
                    "id": 3,
                    "comment": "[Felix] enrichment | proposed | not-a-timestamp",
                    "created": "2026-05-20T12:00:00Z",
                },
            ],
        }
        mock_urlopen.side_effect = _make_vikunja_url_router(
            projects=projects,
            project_tasks=project_tasks,
            task_comments=task_comments,
        )

        report = reconcile(
            since=date(2026, 4, 11),
            token_path=tmp_token_file,
            ledger_path=ledger_path,
        )

        # 1 valid; 2 malformed; 0 habit.
        assert report.enrichment_comments_found == 1
        assert report.comments_replayed == 1
        assert len(report.malformed_details) == 2
        reasons = [m.reason for m in report.malformed_details]
        assert any("unknown state token" in r for r in reasons)
        assert any("invalid timestamp" in r for r in reasons)

        rows = _read_jsonl(ledger_path)
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------


class TestCLI:
    def test_cli_help_exits_zero(self, capsys):
        """``--help`` exits 0 (argparse default; not routed through error())."""
        with pytest.raises(SystemExit) as exc:
            main(["--help"])
        assert exc.value.code == 0

    def test_cli_bad_flag_returns_3(self, capsys):
        """Unknown flag -> exit 3 via _StructuredArgumentParser."""
        rc = main(["--definitely-not-a-flag"])
        captured = capsys.readouterr()
        assert rc == 3
        payload = json.loads(captured.err)
        assert payload["ok"] is False
        assert payload["step"] == "argparse"

    def test_cli_bad_since_returns_3(self, capsys):
        """Invalid --since date -> exit 3 with structured error."""
        rc = main(["--since", "not-a-date"])
        captured = capsys.readouterr()
        assert rc == 3
        payload = json.loads(captured.err)
        assert payload["ok"] is False
        assert payload["step"] == "argparse"
        assert "--since" in payload["error"]

    def test_cli_token_missing_returns_3(self, tmp_path, capsys):
        """Missing token file -> exit 3."""
        missing_token = tmp_path / "no-token-here"
        rc = main(
            [
                "--token-path",
                str(missing_token),
                "--ledger-path",
                str(tmp_path / "ledger.jsonl"),
            ]
        )
        captured = capsys.readouterr()
        assert rc == 3
        payload = json.loads(captured.err)
        assert payload["step"] == "token_load"

    def test_cli_success_emits_summary(
        self,
        mock_urlopen,
        tmp_token_file,
        ledger_path,
        activity_log_sandbox,
        capsys,
    ):
        """Successful run emits the JSON summary on stdout + exit 0."""
        projects = [{"id": 5}]
        project_tasks = {5: [{"id": 100}]}
        task_comments = {
            100: [
                _make_felix_enrichment_comment(
                    comment_id=1,
                    task_id=100,
                    state="proposed",
                    timestamp_utc="2026-05-20T10:00:00Z",
                )
            ]
        }
        mock_urlopen.side_effect = _make_vikunja_url_router(
            projects=projects,
            project_tasks=project_tasks,
            task_comments=task_comments,
        )
        rc = main(
            [
                "--token-path",
                str(tmp_token_file),
                "--ledger-path",
                str(ledger_path),
                "--quiet",
            ]
        )
        captured = capsys.readouterr()
        assert rc == 0
        payload = json.loads(captured.out.strip().splitlines()[-1])
        assert payload["enrichment_comments_found"] == 1
        assert payload["comments_replayed"] == 1
        assert payload["dry_run"] is False

    def test_cli_dry_run(
        self,
        mock_urlopen,
        tmp_token_file,
        ledger_path,
        activity_log_sandbox,
        capsys,
    ):
        """--dry-run path emits summary with dry_run=True and writes nothing."""
        projects = [{"id": 5}]
        project_tasks = {5: [{"id": 100}]}
        task_comments = {
            100: [
                _make_felix_enrichment_comment(
                    comment_id=1,
                    task_id=100,
                    state="proposed",
                    timestamp_utc="2026-05-20T10:00:00Z",
                )
            ]
        }
        mock_urlopen.side_effect = _make_vikunja_url_router(
            projects=projects,
            project_tasks=project_tasks,
            task_comments=task_comments,
        )
        rc = main(
            [
                "--token-path",
                str(tmp_token_file),
                "--ledger-path",
                str(ledger_path),
                "--dry-run",
                "--quiet",
            ]
        )
        captured = capsys.readouterr()
        assert rc == 0
        assert not ledger_path.exists()
        payload = json.loads(captured.out.strip().splitlines()[-1])
        assert payload["dry_run"] is True
        assert payload["comments_replayed"] == 1

    def test_cli_vikunja_failure_returns_1(
        self,
        mock_urlopen,
        tmp_token_file,
        ledger_path,
        activity_log_sandbox,
        capsys,
    ):
        """A Vikunja network error -> exit 1 with structured stderr."""

        def _raise(_request, *args, **kwargs):
            raise urllib.error.URLError("connection refused")

        mock_urlopen.side_effect = _raise
        rc = main(
            [
                "--token-path",
                str(tmp_token_file),
                "--ledger-path",
                str(ledger_path),
            ]
        )
        captured = capsys.readouterr()
        assert rc == 1
        payload = json.loads(captured.err)
        assert payload["ok"] is False
        assert payload["step"] == "vikunja"

    def test_cli_emits_malformed_lines(
        self,
        mock_urlopen,
        tmp_token_file,
        ledger_path,
        activity_log_sandbox,
        capsys,
    ):
        """Without --quiet, MALFORMED lines appear in stdout for malformed comments."""
        projects = [{"id": 5}]
        project_tasks = {5: [{"id": 100}]}
        task_comments = {
            100: [
                {
                    "id": 1,
                    "comment": "[Felix] enrichment | bogus | 2026-05-20T11:00:00Z",
                    "created": "2026-05-20T11:00:00Z",
                }
            ]
        }
        mock_urlopen.side_effect = _make_vikunja_url_router(
            projects=projects,
            project_tasks=project_tasks,
            task_comments=task_comments,
        )
        rc = main(
            [
                "--token-path",
                str(tmp_token_file),
                "--ledger-path",
                str(ledger_path),
            ]
        )
        captured = capsys.readouterr()
        assert rc == 0
        assert "MALFORMED task=100" in captured.out
        assert "unknown state token" in captured.out
