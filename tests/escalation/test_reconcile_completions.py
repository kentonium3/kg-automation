"""Tests for ``scripts.escalation.reconcile_completions`` (WP03 / T014).

Coverage matrix per WP03 T014 (cache-based migration):

- **Done-drift detection** — cache done=true + no JSONL ``done`` record →
  synthetic ``done`` emitted with ``source="reconcile"``.
- **Done-drift dedup** — pre-existing ``done`` record → not subscribed; no emit.
- **Rescheduled-drift detection** — cache due_date != last ``reschedule_to``
  → synthetic ``rescheduled`` emitted with ``source="reconcile"``.
- **Rescheduled-drift dedup** — cache due_date matches last reschedule
  → no emit.
- **Terminal short-circuit** — JSONL has ``dismissed`` → not subscribed (no emit).
- **Hard-fail (derive_state)** — malformed JSONL → ``derive_state``
  raises → ``file_hard_fail_bug`` called with
  ``reason="derive_state_inconsistency"``.
- **No v1-substrate reader path** — reconcile MUST NOT enumerate Vikunja
  project tasks; surviving hard-fails come exclusively from JSONL-native paths.
- **Hard-fail dedup within tick** — once filed for a (task_id, reason),
  subsequent triggers in the same tick short-circuit.
- **Multi-project sweep** — ``reconcile_all`` iterates every per-project
  JSONL file and returns one report per project.
- **dry_run mode** — counters reflect would-be writes; JSONL is untouched.
- **Private task in cache** — skipped; no hard-fail filed.
- **Cache read failure** — OSError from read_cached_task_by_id surfaces as
  ``derive_state_inconsistency`` hard-fail; CLI exits 1.
- **NFR-001 performance smoke** — 50-task sweep completes under 60s with
  cache mocked.

All HTTP traffic from record_event is mocked via the ``mock_urlopen`` fixture.
``hard_fail.file_hard_fail_bug`` is monkey-patched to a recording stub so we
never spawn ``gh`` or ``felix-file-issue.py`` subprocesses from tests.
Cache reads are mocked via the ``mock_sync_cache_fixture`` from
``tests/common/conftest.py``.
"""
from __future__ import annotations

import io
import json
import time
import urllib.error
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from scripts.escalation import reconcile_completions as rcn
from scripts.escalation import record_completion as rc
from scripts.escalation.reconcile_completions import (
    HardFailEvent,
    ReconcileReport,
    main,
    reconcile_all,
    reconcile_project,
)

# Re-export fixture from common conftest so pytest can discover it.
from tests.common.conftest import mock_sync_cache_fixture  # noqa: F401


# ---------------------------------------------------------------------------
# Local fixtures + helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def jsonl_sandbox(tmp_path: Path, monkeypatch) -> Path:
    """Redirect every JSONL_STATE_DIR reference to a tmp directory.

    Both ``reconcile_completions`` and ``record_completion`` consume the
    constant — the synthetic-record path goes through ``record_event``
    which uses ``record_completion.JSONL_STATE_DIR``. We monkeypatch both
    so the synthetic-record append lands in the same sandbox the test
    seeded the initial JSONL into.
    """
    sandbox = tmp_path / "escalation_state"
    sandbox.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(rcn, "JSONL_STATE_DIR", sandbox)
    monkeypatch.setattr(rc, "JSONL_STATE_DIR", sandbox)
    return sandbox


@pytest.fixture
def tmp_token_file(tmp_path: Path, monkeypatch) -> Path:
    """Write a placeholder token file and redirect DEFAULT_TOKEN_PATH.

    Reconcile validates the token file exists at start (fail-fast). We point
    DEFAULT_TOKEN_PATH at the tmp file so the synthetic-record path (which
    calls ``record_event`` with ``token_path=DEFAULT_TOKEN_PATH``) does not
    hit the real production secret path.
    """
    token_path = tmp_path / "vikunja-api"
    token_path.write_text("test-token-xxx\n", encoding="utf-8")
    monkeypatch.setattr(rcn, "DEFAULT_TOKEN_PATH", token_path)
    monkeypatch.setattr(rc, "DEFAULT_TOKEN_PATH", token_path)
    return token_path


class _HardFailRecorder(list):
    """List subclass with a ``queue`` attribute for pre-staged stub results."""

    queue: list[dict]


@pytest.fixture
def recorded_hard_fails(monkeypatch) -> _HardFailRecorder:
    """Stub ``hard_fail.file_hard_fail_bug`` and capture call kwargs.

    Each entry is a dict ``{"kwargs": <kwargs>, "result": <result>}`` where
    ``result`` is the dict the stub returned. Tests can pre-queue stub
    return values via ``recorded_hard_fails.queue.append(...)`` to simulate
    deduped responses or filing failures.
    """
    captured = _HardFailRecorder()
    captured.queue = []

    def _stub(**kwargs: Any) -> dict:
        if captured.queue:
            result = captured.queue.pop(0)
        else:
            result = {
                "filed": True,
                "deduped": False,
                "issue_url": "https://example/1",
            }
        captured.append({"kwargs": kwargs, "result": result})
        return result

    monkeypatch.setattr(rcn, "file_hard_fail_bug", _stub)
    return captured


@pytest.fixture
def mock_urlopen(monkeypatch):
    """Monkey-patch ``urllib.request.urlopen`` to a ``MagicMock``.

    Still needed for synthetic-record writes via record_event (which PATCHes
    Vikunja). In tests that don't actually write synthetic records, the mock
    ensures no real HTTP calls slip through.
    """
    mock = MagicMock(name="urlopen")
    monkeypatch.setattr("urllib.request.urlopen", mock)
    return mock


def _resp(payload: Any, *, status: int = 200) -> MagicMock:
    """Build a context-manager-shaped fake urlopen response."""
    body = json.dumps(payload).encode("utf-8") if payload is not None else b""
    resp = MagicMock(name="response")
    resp.status = status
    resp.read = MagicMock(return_value=body)
    cm = MagicMock(name="cm")
    cm.__enter__ = MagicMock(return_value=resp)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


def _write_jsonl(path: Path, records: list[dict]) -> None:
    """Write ``records`` to ``path`` (one JSON object per line)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _make_record(
    task_id: int = 1234,
    project_id: int = 4,
    state: str = "level_sent",
    date_str: str = "2026-05-19",
    timestamp: str | None = None,
    title: str = "Task",
    source: str = "agent",
    **params: Any,
) -> dict:
    """Build a minimal valid escalation JSONL record."""
    record = {
        "domain": "escalation",
        "task_id": task_id,
        "project_id": project_id,
        "title": title,
        "date": date_str,
        "state": state,
        "source": source,
        "timestamp": timestamp or f"{date_str}T12:00:00+00:00",
        "note": None,
    }
    record.update(params)
    return record


def _cache_task_fields(
    task_id: int,
    *,
    done: bool = False,
    due_date: str | None = "2026-05-15T00:00:00Z",
    project_id: int = 4,
    title: str = "Task",
) -> dict:
    """Return a fields dict suitable for mock_sync_cache_fixture ``tasks``."""
    return {
        "title": title,
        "done": done,
        "due_date": due_date,
        "project_id": project_id,
        "repeat_after": 0,
        "repeat_mode": "default",
        "labels": [],
    }


# ---------------------------------------------------------------------------
# Done-drift detection
# ---------------------------------------------------------------------------


def test_vikunja_done_emits_synthetic_done(
    jsonl_sandbox: Path,
    tmp_token_file: Path,
    mock_sync_cache_fixture,
    mock_urlopen,
    recorded_hard_fails: _HardFailRecorder,
) -> None:
    """JSONL has only ``level_sent``; cache returns done=true → emit done."""
    project_id = 4
    task_id = 1234
    jsonl_path = jsonl_sandbox / f"project-{project_id}-escalation-history.jsonl"
    _write_jsonl(
        jsonl_path,
        [
            _make_record(
                task_id=task_id,
                project_id=project_id,
                state="level_sent",
                date_str="2026-05-19",
                level=1,
            )
        ],
    )

    mock_sync_cache_fixture(
        tasks={task_id: _cache_task_fields(task_id, done=True, title="Email Q3 board summary")},
    )
    # record_event writes via HTTP; stub it to avoid real Vikunja calls.
    mock_urlopen.return_value = _resp({"id": task_id, "done": True})

    report = reconcile_project(project_id, jsonl_dir=jsonl_sandbox)

    assert report.synthetic_done_emitted == 1
    assert report.synthetic_rescheduled_emitted == 0
    assert report.tasks_scanned == 1
    assert report.hard_fails == []

    # Verify synthetic record was appended with source="reconcile".
    records = _read_jsonl(jsonl_path)
    new_records = [r for r in records if r.get("state") == "done"]
    assert len(new_records) == 1
    assert new_records[0]["source"] == "reconcile"
    assert new_records[0]["task_id"] == task_id


def test_vikunja_done_with_existing_done_record_no_emit(
    jsonl_sandbox: Path,
    tmp_token_file: Path,
    mock_urlopen,
    recorded_hard_fails: _HardFailRecorder,
) -> None:
    """JSONL already has a ``done`` record → not subscribed → no emit."""
    project_id = 4
    task_id = 1234
    jsonl_path = jsonl_sandbox / f"project-{project_id}-escalation-history.jsonl"
    _write_jsonl(
        jsonl_path,
        [
            _make_record(
                task_id=task_id,
                project_id=project_id,
                state="level_sent",
                date_str="2026-05-19",
                level=1,
            ),
            _make_record(
                task_id=task_id,
                project_id=project_id,
                state="done",
                date_str="2026-05-20",
                timestamp="2026-05-20T12:00:00+00:00",
                source="agent",
            ),
        ],
    )

    # Task with done record is not subscribed → no cache read attempt.
    mock_urlopen.side_effect = AssertionError("no cache or Vikunja call expected")

    report = reconcile_project(project_id, jsonl_dir=jsonl_sandbox)

    assert report.tasks_scanned == 0
    assert report.synthetic_done_emitted == 0
    # No second ``done`` record appended.
    final_records = _read_jsonl(jsonl_path)
    assert sum(1 for r in final_records if r.get("state") == "done") == 1


# ---------------------------------------------------------------------------
# Rescheduled-drift detection
# ---------------------------------------------------------------------------


def test_due_date_change_emits_synthetic_rescheduled(
    jsonl_sandbox: Path,
    tmp_token_file: Path,
    mock_sync_cache_fixture,
    mock_urlopen,
    recorded_hard_fails: _HardFailRecorder,
) -> None:
    """JSONL has ``rescheduled`` for one date; cache shows different → emit."""
    project_id = 4
    task_id = 1234
    jsonl_path = jsonl_sandbox / f"project-{project_id}-escalation-history.jsonl"
    _write_jsonl(
        jsonl_path,
        [
            _make_record(
                task_id=task_id,
                project_id=project_id,
                state="level_sent",
                date_str="2026-05-18",
                level=1,
            ),
            _make_record(
                task_id=task_id,
                project_id=project_id,
                state="rescheduled",
                date_str="2026-05-19",
                timestamp="2026-05-19T12:00:00+00:00",
                reschedule_to="2026-05-22",
            ),
        ],
    )

    # Cache shows due_date = 2026-05-25 (differs from JSONL reschedule_to=2026-05-22)
    mock_sync_cache_fixture(
        tasks={task_id: _cache_task_fields(task_id, done=False, due_date="2026-05-25T00:00:00Z")},
    )
    mock_urlopen.return_value = _resp({"ok": True})  # stub record_event HTTP

    report = reconcile_project(project_id, jsonl_dir=jsonl_sandbox)

    assert report.synthetic_rescheduled_emitted == 1
    assert report.synthetic_done_emitted == 0

    records = _read_jsonl(jsonl_path)
    new = [
        r for r in records
        if r.get("state") == "rescheduled" and r.get("source") == "reconcile"
    ]
    assert len(new) == 1
    assert new[0]["reschedule_to"] == "2026-05-25"
    assert new[0]["task_id"] == task_id


def test_due_date_unchanged_no_emit(
    jsonl_sandbox: Path,
    tmp_token_file: Path,
    mock_sync_cache_fixture,
    mock_urlopen,
    recorded_hard_fails: _HardFailRecorder,
) -> None:
    """Cache due_date matches last ``reschedule_to`` → no emit."""
    project_id = 4
    task_id = 1234
    jsonl_path = jsonl_sandbox / f"project-{project_id}-escalation-history.jsonl"
    _write_jsonl(
        jsonl_path,
        [
            _make_record(
                task_id=task_id,
                project_id=project_id,
                state="level_sent",
                date_str="2026-05-18",
                level=1,
            ),
            _make_record(
                task_id=task_id,
                project_id=project_id,
                state="rescheduled",
                date_str="2026-05-19",
                timestamp="2026-05-19T12:00:00+00:00",
                reschedule_to="2026-05-25",
            ),
        ],
    )
    mock_sync_cache_fixture(
        tasks={task_id: _cache_task_fields(task_id, done=False, due_date="2026-05-25T00:00:00Z")},
    )

    report = reconcile_project(project_id, jsonl_dir=jsonl_sandbox)

    assert report.synthetic_rescheduled_emitted == 0
    assert report.synthetic_done_emitted == 0


def test_due_date_change_with_terminal_record_no_emit(
    jsonl_sandbox: Path,
    tmp_token_file: Path,
    mock_urlopen,
    recorded_hard_fails: _HardFailRecorder,
) -> None:
    """JSONL has ``dismissed`` → subscription gate excludes task; no emit."""
    project_id = 4
    task_id = 1234
    jsonl_path = jsonl_sandbox / f"project-{project_id}-escalation-history.jsonl"
    _write_jsonl(
        jsonl_path,
        [
            _make_record(
                task_id=task_id,
                project_id=project_id,
                state="level_sent",
                date_str="2026-05-18",
                level=1,
            ),
            _make_record(
                task_id=task_id,
                project_id=project_id,
                state="dismissed",
                date_str="2026-05-19",
                timestamp="2026-05-19T12:00:00+00:00",
                source="kent_reply",
            ),
        ],
    )

    # Not subscribed → no cache read.
    mock_urlopen.side_effect = AssertionError("no call expected — dismissed task not subscribed")

    report = reconcile_project(project_id, jsonl_dir=jsonl_sandbox)

    assert report.tasks_scanned == 0
    assert report.synthetic_rescheduled_emitted == 0


def test_no_prior_reschedule_emits_when_vikunja_due_diverges(
    jsonl_sandbox: Path,
    tmp_token_file: Path,
    mock_sync_cache_fixture,
    mock_urlopen,
    recorded_hard_fails: _HardFailRecorder,
) -> None:
    """No prior reschedule + cache due_date present → emit (per D3)."""
    project_id = 4
    task_id = 1234
    jsonl_path = jsonl_sandbox / f"project-{project_id}-escalation-history.jsonl"
    _write_jsonl(
        jsonl_path,
        [
            _make_record(
                task_id=task_id,
                project_id=project_id,
                state="level_sent",
                date_str="2026-05-18",
                level=1,
            ),
        ],
    )
    mock_sync_cache_fixture(
        tasks={task_id: _cache_task_fields(task_id, done=False, due_date="2026-05-25T00:00:00Z")},
    )
    mock_urlopen.return_value = _resp({"ok": True})

    report = reconcile_project(project_id, jsonl_dir=jsonl_sandbox)
    assert report.synthetic_rescheduled_emitted == 1


# ---------------------------------------------------------------------------
# Hard-fail integration (Q10)
# ---------------------------------------------------------------------------


def test_invalid_event_params_files_hard_fail(
    jsonl_sandbox: Path,
    tmp_token_file: Path,
    mock_urlopen,
    recorded_hard_fails: _HardFailRecorder,
) -> None:
    """Schema-invalid JSONL record (no ``level``) → malformed_jsonl_record per D8.

    Per research D8, "malformed JSONL line" includes any line that
    JSON-parses but has missing/typo'd parameter fields per the event_type.
    The read layer catches this and routes through Q10 with
    ``reason="malformed_jsonl_record"`` (NOT derive_state_inconsistency —
    the schema-validation failure is detected before derive_state runs).
    """
    project_id = 4
    task_id = 1234
    jsonl_path = jsonl_sandbox / f"project-{project_id}-escalation-history.jsonl"
    bad = _make_record(
        task_id=task_id,
        project_id=project_id,
        state="level_sent",
        date_str="2026-05-18",
    )
    # Strip the required `level` param.
    bad.pop("level", None)
    _write_jsonl(jsonl_path, [bad])

    # No task is subscribed (malformed_record → not subscribed) → no cache read.
    mock_urlopen.side_effect = AssertionError("no call expected post-parity-cleanup")

    report = reconcile_project(project_id, jsonl_dir=jsonl_sandbox)

    assert len(report.hard_fails) == 1
    event = report.hard_fails[0]
    assert event.reason == "malformed_jsonl_record"
    assert event.task_id == task_id
    # Verify the stub was called with the correct reason kwarg.
    assert len(recorded_hard_fails) == 1
    assert recorded_hard_fails[0]["kwargs"]["reason"] == "malformed_jsonl_record"
    # And that no synthetic record was appended after the hard-fail.
    records = _read_jsonl(jsonl_path)
    assert all(r.get("source") != "reconcile" for r in records)


def test_no_v1_substrate_reader_path(
    jsonl_sandbox: Path,
    tmp_token_file: Path,
    mock_sync_cache_fixture,
    mock_urlopen,
    recorded_hard_fails: _HardFailRecorder,
) -> None:
    """Post-parity-cleanup regression guard.

    Reconcile MUST NOT enumerate Vikunja project tasks for the removed
    v1-comment-substrate drift check, and MUST NOT call any Vikunja
    endpoint that existed only to support that check (notably
    ``GET /projects/{id}/tasks``). Now that the per-task GET is replaced
    with a cache read, no Vikunja URL calls should appear during the
    subscribed-sweep phase.
    """
    project_id = 4
    subscribed_task_id = 1234
    jsonl_path = (
        jsonl_sandbox / f"project-{project_id}-escalation-history.jsonl"
    )
    _write_jsonl(
        jsonl_path,
        [
            _make_record(
                task_id=subscribed_task_id,
                project_id=project_id,
                state="level_sent",
                date_str="2026-05-18",
                level=1,
            ),
        ],
    )

    # Cache returns no drift (done=False, due_date matches no reschedule).
    mock_sync_cache_fixture(
        tasks={subscribed_task_id: _cache_task_fields(
            subscribed_task_id, done=False, due_date="2026-05-18T00:00:00Z",
        )},
    )
    # urlopen should NOT be called for the subscribed-sweep phase (no Vikunja reads).
    mock_urlopen.side_effect = AssertionError("no Vikunja read expected in subscribed sweep")

    report = reconcile_project(project_id, jsonl_dir=jsonl_sandbox)

    # All surviving hard-fails come from JSONL-native code paths.
    surviving_reasons = {
        "malformed_jsonl_record",
        "derive_state_inconsistency",
    }
    assert all(ev.reason in surviving_reasons for ev in report.hard_fails)
    # No /projects/<id>/tasks calls.
    assert mock_urlopen.call_count == 0


def test_hard_fail_dedup_hit_does_not_double_file(
    jsonl_sandbox: Path,
    tmp_token_file: Path,
    mock_urlopen,
    recorded_hard_fails: _HardFailRecorder,
) -> None:
    """Mock file_hard_fail_bug to return deduped=True → bug_url reflects dedup."""
    project_id = 4
    task_id = 1234
    jsonl_path = jsonl_sandbox / f"project-{project_id}-escalation-history.jsonl"
    bad = _make_record(
        task_id=task_id,
        project_id=project_id,
        state="level_sent",
        date_str="2026-05-18",
    )
    bad.pop("level", None)
    _write_jsonl(jsonl_path, [bad])

    # Pre-queue a deduped result so the stub returns deduped=True.
    recorded_hard_fails.queue.append(  # type: ignore[attr-defined]
        {"filed": False, "deduped": True, "existing_url": "https://example/dup"}
    )

    mock_urlopen.side_effect = AssertionError("no Vikunja read expected")

    report = reconcile_project(project_id, jsonl_dir=jsonl_sandbox)

    assert len(report.hard_fails) == 1
    assert report.hard_fails[0].deduped is True
    assert report.hard_fails[0].bug_url == "https://example/dup"
    # Only one invocation despite the dedup hit (within-tick dedup also
    # prevents a second call).
    assert len(recorded_hard_fails) == 1


def test_within_tick_dedup_prevents_second_file(
    jsonl_sandbox: Path,
    tmp_token_file: Path,
    mock_urlopen,
    recorded_hard_fails: _HardFailRecorder,
) -> None:
    """Two malformed-record tasks → exactly two file_hard_fail_bug calls."""
    project_id = 4
    task_a, task_b = 1234, 5678
    jsonl_path = jsonl_sandbox / f"project-{project_id}-escalation-history.jsonl"

    def _bad(task_id: int) -> dict:
        r = _make_record(
            task_id=task_id,
            project_id=project_id,
            state="level_sent",
            date_str="2026-05-18",
        )
        r.pop("level", None)
        return r

    # Two records per task, both broken — without dedup we'd file 4 bugs.
    _write_jsonl(jsonl_path, [_bad(task_a), _bad(task_a), _bad(task_b)])

    mock_urlopen.side_effect = AssertionError("no Vikunja read expected")

    report = reconcile_project(project_id, jsonl_dir=jsonl_sandbox)
    assert len(report.hard_fails) == 2
    assert len(recorded_hard_fails) == 2
    reasons = {evt.reason for evt in report.hard_fails}
    assert reasons == {"malformed_jsonl_record"}
    task_ids = {evt.task_id for evt in report.hard_fails}
    assert task_ids == {task_a, task_b}


# ---------------------------------------------------------------------------
# Multi-project sweep
# ---------------------------------------------------------------------------


def test_reconcile_all_iterates_projects(
    jsonl_sandbox: Path,
    tmp_token_file: Path,
    mock_sync_cache_fixture,
    mock_urlopen,
    recorded_hard_fails: _HardFailRecorder,
) -> None:
    """reconcile_all returns one report per discovered per-project JSONL file."""
    p4 = 4
    p7 = 7
    j4 = jsonl_sandbox / f"project-{p4}-escalation-history.jsonl"
    j7 = jsonl_sandbox / f"project-{p7}-escalation-history.jsonl"
    _write_jsonl(j4, [_make_record(task_id=1, project_id=p4, level=1)])
    _write_jsonl(j7, [_make_record(task_id=10, project_id=p7, level=1)])

    # Cache returns no drift for either project's tasks.
    mock_sync_cache_fixture(
        tasks={
            1: _cache_task_fields(1, done=False, due_date="2026-05-15T00:00:00Z", project_id=p4),
            10: _cache_task_fields(10, done=False, due_date="2026-05-15T00:00:00Z", project_id=p7),
        },
    )

    reports = reconcile_all(jsonl_dir=jsonl_sandbox)
    assert len(reports) == 2
    pids = sorted(r.project_id for r in reports)
    assert pids == [p4, p7]
    for r in reports:
        assert r.tasks_scanned == 1


def test_reconcile_all_empty_dir_returns_empty_list(
    tmp_path: Path,
    tmp_token_file: Path,
    recorded_hard_fails: _HardFailRecorder,
) -> None:
    """Empty / missing jsonl_dir → no reports."""
    sandbox = tmp_path / "empty"
    sandbox.mkdir()
    assert reconcile_all(jsonl_dir=sandbox) == []
    # Also tolerate a missing directory.
    assert reconcile_all(jsonl_dir=tmp_path / "does-not-exist") == []


# ---------------------------------------------------------------------------
# dry_run
# ---------------------------------------------------------------------------


def test_dry_run_reports_no_writes(
    jsonl_sandbox: Path,
    tmp_token_file: Path,
    mock_sync_cache_fixture,
    mock_urlopen,
    recorded_hard_fails: _HardFailRecorder,
) -> None:
    """dry_run=True → counters reflect would-be writes; JSONL untouched."""
    project_id = 4
    task_id = 1234
    jsonl_path = jsonl_sandbox / f"project-{project_id}-escalation-history.jsonl"
    _write_jsonl(
        jsonl_path,
        [
            _make_record(
                task_id=task_id,
                project_id=project_id,
                state="level_sent",
                date_str="2026-05-19",
                level=1,
            )
        ],
    )

    mock_sync_cache_fixture(
        tasks={task_id: _cache_task_fields(task_id, done=True)},
    )

    before = _read_jsonl(jsonl_path)
    report = reconcile_project(
        project_id, jsonl_dir=jsonl_sandbox, dry_run=True
    )
    after = _read_jsonl(jsonl_path)

    assert report.synthetic_done_emitted == 1
    # File unchanged.
    assert before == after


# ---------------------------------------------------------------------------
# Performance smoke (NFR-001)
# ---------------------------------------------------------------------------


def test_reconcile_50_tasks_under_60s(
    jsonl_sandbox: Path,
    tmp_token_file: Path,
    mock_sync_cache_fixture,
    mock_urlopen,
    recorded_hard_fails: _HardFailRecorder,
) -> None:
    """50-task sweep with mocked cache completes well under 60s.

    Not a strict NFR gate (real network adds variable latency), but a smoke
    test ensures we don't introduce an O(n^2) hot path. We expect this to
    finish in well under a second with mocks; the 60s ceiling is the spec
    NFR-001 budget.
    """
    project_id = 4
    jsonl_path = jsonl_sandbox / f"project-{project_id}-escalation-history.jsonl"
    records = []
    for i in range(50):
        records.append(
            _make_record(
                task_id=2000 + i,
                project_id=project_id,
                state="level_sent",
                date_str="2026-05-19",
                level=1,
            )
        )
    _write_jsonl(jsonl_path, records)

    # 50 tasks, all done=False with matching due_date (no drift).
    cache_tasks = {
        2000 + i: _cache_task_fields(2000 + i, done=False, due_date="2026-05-15T00:00:00Z")
        for i in range(50)
    }
    mock_sync_cache_fixture(tasks=cache_tasks)

    started = time.monotonic()
    report = reconcile_project(project_id, jsonl_dir=jsonl_sandbox)
    elapsed = time.monotonic() - started

    assert report.tasks_scanned == 50
    assert report.synthetic_done_emitted == 0
    assert report.duration_seconds < 60
    assert elapsed < 60


# ---------------------------------------------------------------------------
# Additional coverage: helper boundary cases
# ---------------------------------------------------------------------------


def test_max_tasks_caps_scan(
    jsonl_sandbox: Path,
    tmp_token_file: Path,
    mock_sync_cache_fixture,
    mock_urlopen,
    recorded_hard_fails: _HardFailRecorder,
) -> None:
    """max_tasks caps the subscribed sweep."""
    project_id = 4
    jsonl_path = jsonl_sandbox / f"project-{project_id}-escalation-history.jsonl"
    records = []
    for i in range(5):
        records.append(
            _make_record(
                task_id=3000 + i,
                project_id=project_id,
                state="level_sent",
                date_str="2026-05-19",
                level=1,
            )
        )
    _write_jsonl(jsonl_path, records)

    cache_tasks = {
        3000 + i: _cache_task_fields(3000 + i, done=False, due_date="2026-05-15T00:00:00Z")
        for i in range(5)
    }
    mock_sync_cache_fixture(tasks=cache_tasks)

    report = reconcile_project(
        project_id, jsonl_dir=jsonl_sandbox, max_tasks=2
    )
    assert report.tasks_scanned == 2


def test_missing_jsonl_file_yields_empty_report(
    jsonl_sandbox: Path,
    tmp_token_file: Path,
    mock_urlopen,
    recorded_hard_fails: _HardFailRecorder,
) -> None:
    """No JSONL file for the project → tasks_scanned=0; no cache read at all."""
    report = reconcile_project(7, jsonl_dir=jsonl_sandbox)
    assert report.tasks_scanned == 0
    assert report.hard_fails == []
    assert mock_urlopen.call_count == 0


def test_cache_read_failure_routes_to_hard_fail(
    jsonl_sandbox: Path,
    tmp_token_file: Path,
    mock_sync_cache_fixture,
    mock_urlopen,
    recorded_hard_fails: _HardFailRecorder,
) -> None:
    """Cache read failure for a subscribed task → derive_state_inconsistency hard-fail."""
    project_id = 4
    task_id = 1234
    jsonl_path = jsonl_sandbox / f"project-{project_id}-escalation-history.jsonl"
    _write_jsonl(
        jsonl_path,
        [_make_record(task_id=task_id, project_id=project_id, level=1)],
    )

    # Cache has a different task, so read_cached_task_by_id for task_id=1234 raises.
    mock_sync_cache_fixture(
        tasks={9999: _cache_task_fields(9999, done=False)},
    )

    report = reconcile_project(project_id, jsonl_dir=jsonl_sandbox)
    assert len(report.hard_fails) == 1
    assert report.hard_fails[0].reason == "derive_state_inconsistency"
    assert "cache read failed" in report.hard_fails[0].detail


def test_zero_sentinel_due_date_treated_as_none(
    jsonl_sandbox: Path,
    tmp_token_file: Path,
    mock_sync_cache_fixture,
    mock_urlopen,
    recorded_hard_fails: _HardFailRecorder,
) -> None:
    """Cache due_date '0001-01-01T00:00:00Z' → treated as None; no emit."""
    project_id = 4
    task_id = 1234
    jsonl_path = jsonl_sandbox / f"project-{project_id}-escalation-history.jsonl"
    _write_jsonl(
        jsonl_path,
        [
            _make_record(
                task_id=task_id,
                project_id=project_id,
                state="level_sent",
                date_str="2026-05-19",
                level=1,
            )
        ],
    )
    mock_sync_cache_fixture(
        tasks={task_id: _cache_task_fields(
            task_id, done=False, due_date="0001-01-01T00:00:00Z"
        )},
    )
    report = reconcile_project(project_id, jsonl_dir=jsonl_sandbox)
    # Sentinel due is "none" → no rescheduled-drift.
    assert report.synthetic_rescheduled_emitted == 0


def test_malformed_jsonl_line_does_not_crash_enumeration(
    jsonl_sandbox: Path,
    tmp_token_file: Path,
    mock_sync_cache_fixture,
    mock_urlopen,
    recorded_hard_fails: _HardFailRecorder,
) -> None:
    """A broken JSONL line is tolerated by enumeration; subscribed tasks still scanned.

    Also verifies that the broken lines route through Q10 (one file-level
    sentinel hard-fail for the unparseable / non-dict lines) without
    halting the tick for the valid subscribed task.
    """
    project_id = 4
    task_id = 1234
    jsonl_path = jsonl_sandbox / f"project-{project_id}-escalation-history.jsonl"
    # Mix a broken line in front of a valid level_sent record.
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    with jsonl_path.open("w", encoding="utf-8") as fh:
        fh.write("not-json\n")
        fh.write(json.dumps(
            _make_record(task_id=task_id, project_id=project_id, level=1)
        ) + "\n")
        fh.write("\n")  # empty line should be ignored
        fh.write("\"a string not a dict\"\n")  # non-dict JSON

    mock_sync_cache_fixture(
        tasks={task_id: _cache_task_fields(task_id, done=False, due_date="2026-05-15T00:00:00Z")},
    )

    report = reconcile_project(project_id, jsonl_dir=jsonl_sandbox)
    # Valid subscribed task still gets scanned.
    assert report.tasks_scanned == 1
    # The two unkeyed malformed lines (not-json + non-dict string) collapse
    # to one file-level sentinel hard-fail (task_id=0).
    malformed_events = [
        e for e in report.hard_fails
        if e.reason == "malformed_jsonl_record"
    ]
    assert len(malformed_events) == 1
    assert malformed_events[0].task_id == 0


def test_synthetic_done_failure_routes_to_hard_fail(
    jsonl_sandbox: Path,
    tmp_token_file: Path,
    mock_sync_cache_fixture,
    mock_urlopen,
    recorded_hard_fails: _HardFailRecorder,
    monkeypatch,
) -> None:
    """If record_event raises while writing synthetic done → hard-fail filed."""
    project_id = 4
    task_id = 1234
    jsonl_path = jsonl_sandbox / f"project-{project_id}-escalation-history.jsonl"
    _write_jsonl(
        jsonl_path,
        [_make_record(task_id=task_id, project_id=project_id, level=1)],
    )

    def _bad_record_event(*args, **kwargs):
        raise rc.StateLogError("disk full")

    monkeypatch.setattr(rc, "record_event", _bad_record_event)

    mock_sync_cache_fixture(
        tasks={task_id: _cache_task_fields(task_id, done=True)},
    )

    report = reconcile_project(project_id, jsonl_dir=jsonl_sandbox)
    assert len(report.hard_fails) == 1
    assert "synthetic done record failed" in report.hard_fails[0].detail


# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------


def test_cli_requires_project_id_or_all(capsys) -> None:
    """No mode flag → exit 3 with structured stderr."""
    exit_code = main([])
    captured = capsys.readouterr()
    assert exit_code == 3
    payload = json.loads(captured.err.strip())
    assert payload["ok"] is False
    assert payload["step"] == "argparse"


def test_cli_token_missing_yields_exit_3(
    jsonl_sandbox: Path,
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    """Token file missing → exit 3 (usage error per CLI contract)."""
    missing = tmp_path / "no-such-token"
    monkeypatch.setattr(rcn, "DEFAULT_TOKEN_PATH", missing)
    exit_code = main(
        [
            "--project-id", "4",
            "--jsonl-dir", str(jsonl_sandbox),
            "--token-path", str(missing),
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 3
    payload = json.loads(captured.err.strip())
    assert payload["step"] == "token_load"


def test_cli_emits_summary_line_for_project(
    jsonl_sandbox: Path,
    tmp_token_file: Path,
    mock_sync_cache_fixture,
    mock_urlopen,
    recorded_hard_fails: _HardFailRecorder,
    capsys,
) -> None:
    """CLI summary line is valid JSON with the expected keys."""
    project_id = 4
    jsonl_path = jsonl_sandbox / f"project-{project_id}-escalation-history.jsonl"
    _write_jsonl(
        jsonl_path,
        [
            _make_record(
                task_id=1234,
                project_id=project_id,
                state="level_sent",
                date_str="2026-05-19",
                level=1,
            )
        ],
    )
    mock_sync_cache_fixture(
        tasks={1234: _cache_task_fields(1234, done=False, due_date="2026-05-15T00:00:00Z")},
    )

    exit_code = main(
        [
            "--project-id", str(project_id),
            "--jsonl-dir", str(jsonl_sandbox),
            "--token-path", str(tmp_token_file),
            "--quiet",
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 0
    # Last line is the JSON summary.
    lines = [ln for ln in captured.out.splitlines() if ln.strip()]
    payload = json.loads(lines[-1])
    assert payload["project_id"] == project_id
    assert payload["tasks_scanned"] == 1
    assert "hard_fails" in payload
    assert "duration_s" in payload


def test_cli_non_quiet_emits_drift_and_hardfail_lines(
    jsonl_sandbox: Path,
    tmp_token_file: Path,
    mock_sync_cache_fixture,
    mock_urlopen,
    recorded_hard_fails: _HardFailRecorder,
    capsys,
) -> None:
    """Without --quiet, CLI emits DRIFT and HARDFAIL prefixed lines."""
    project_id = 4
    task_id = 1234
    jsonl_path = jsonl_sandbox / f"project-{project_id}-escalation-history.jsonl"
    _write_jsonl(
        jsonl_path,
        [
            _make_record(
                task_id=task_id,
                project_id=project_id,
                state="level_sent",
                date_str="2026-05-19",
                level=1,
            )
        ],
    )
    mock_sync_cache_fixture(
        tasks={task_id: _cache_task_fields(task_id, done=True)},
    )
    mock_urlopen.return_value = _resp({"ok": True})  # stub record_event HTTP

    exit_code = main(
        [
            "--project-id", str(project_id),
            "--jsonl-dir", str(jsonl_sandbox),
            "--token-path", str(tmp_token_file),
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "DRIFT" in captured.out
    assert "emitted_synthetic=done" in captured.out


def test_cli_all_flag_calls_reconcile_all(
    jsonl_sandbox: Path,
    tmp_token_file: Path,
    mock_sync_cache_fixture,
    mock_urlopen,
    recorded_hard_fails: _HardFailRecorder,
    capsys,
) -> None:
    """--all sweeps every project file under --jsonl-dir."""
    p4, p7 = 4, 7
    _write_jsonl(
        jsonl_sandbox / f"project-{p4}-escalation-history.jsonl",
        [_make_record(task_id=1, project_id=p4, level=1)],
    )
    _write_jsonl(
        jsonl_sandbox / f"project-{p7}-escalation-history.jsonl",
        [_make_record(task_id=10, project_id=p7, level=1)],
    )
    mock_sync_cache_fixture(
        tasks={
            1: _cache_task_fields(1, done=False, due_date="2026-05-15T00:00:00Z", project_id=p4),
            10: _cache_task_fields(10, done=False, due_date="2026-05-15T00:00:00Z", project_id=p7),
        },
    )

    exit_code = main(
        [
            "--all",
            "--jsonl-dir", str(jsonl_sandbox),
            "--token-path", str(tmp_token_file),
            "--quiet",
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 0
    # Two JSON summary lines (one per project).
    json_lines = [
        ln for ln in captured.out.splitlines()
        if ln.strip().startswith("{")
    ]
    assert len(json_lines) == 2


def test_cache_oserror_raises(
    jsonl_sandbox: Path,
    tmp_token_file: Path,
    mock_sync_cache_fixture,
    mock_urlopen,
    recorded_hard_fails: _HardFailRecorder,
) -> None:
    """Stale cache → OSError → hard-fail filed, not propagated to caller."""
    project_id = 4
    task_id = 1234
    jsonl_path = jsonl_sandbox / f"project-{project_id}-escalation-history.jsonl"
    _write_jsonl(
        jsonl_path,
        [_make_record(task_id=task_id, project_id=project_id, level=1)],
    )
    # Stale cache: freshness_age_seconds >> SLA_NORMAL (900s).
    mock_sync_cache_fixture(
        tasks={task_id: _cache_task_fields(task_id, done=False)},
        freshness_age_seconds=9999,
    )

    # A stale cache causes read_cached_task_by_id to raise OSError with "stale".
    # The reconciler routes this to a hard-fail, not a crash.
    report = reconcile_project(project_id, jsonl_dir=jsonl_sandbox)
    assert len(report.hard_fails) == 1
    assert report.hard_fails[0].reason == "derive_state_inconsistency"
    assert "stale" in report.hard_fails[0].detail.lower()


def test_cli_record_event_failure_routes_to_hard_fail(
    jsonl_sandbox: Path,
    tmp_token_file: Path,
    mock_sync_cache_fixture,
    mock_urlopen,
    recorded_hard_fails: _HardFailRecorder,
    monkeypatch,
    capsys,
) -> None:
    """record_event StateLogError during synthetic-record write → hard-fail.

    WP03 note: synthetic records use skip_vikunja=True (cache-first, no HTTP
    side-effect needed). So URLError on urlopen can no longer simulate
    record_event failure. We monkeypatch rc.record_event directly to raise
    StateLogError, which the reconciler catches and routes to a hard-fail.
    """
    project_id = 4
    task_id = 1234
    jsonl_path = jsonl_sandbox / f"project-{project_id}-escalation-history.jsonl"
    _write_jsonl(
        jsonl_path,
        [
            _make_record(
                task_id=task_id,
                project_id=project_id,
                state="level_sent",
                date_str="2026-05-19",
                level=1,
            )
        ],
    )
    # Cache says done=True → will try to write synthetic done record.
    mock_sync_cache_fixture(
        tasks={task_id: _cache_task_fields(task_id, done=True)},
    )
    # Simulate JSONL write failure (skip_vikunja=True so URLError is irrelevant).
    from scripts.escalation import record_completion as rc_mod
    monkeypatch.setattr(
        rcn.rc,
        "record_event",
        lambda *a, **kw: (_ for _ in ()).throw(rc_mod.StateLogError("disk full")),
    )

    exit_code = main(
        [
            "--project-id", str(project_id),
            "--jsonl-dir", str(jsonl_sandbox),
            "--token-path", str(tmp_token_file),
            "--quiet",
        ]
    )
    # StateLogError → _emit_hard_fail → routes to hard-fail in report.
    # reconcile_project does not propagate the error → exit 0.
    captured = capsys.readouterr()
    assert exit_code == 0
    lines = [ln for ln in captured.out.splitlines() if ln.strip()]
    payload = json.loads(lines[-1])
    assert payload["hard_fails"] == 1
