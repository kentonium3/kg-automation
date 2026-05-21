"""Unit tests for the importable surfaces of ``handle_drift_events.py``.

Per mission #343 WP01 (T005): lock in the new import surface so future
refactors don't regress it. The helper was lifted from
``scripts/openclaw/agents/felix-doc-auditor/`` to
``scripts/doc_audit/helpers/`` and now exposes ``process_events`` as
the library entry point alongside the existing module-level building
blocks (``find_mapping``, ``write_cursor_atomic``, etc.).

Tests are import-driven only — no CLI subprocesses, no real network or
``gh`` calls. ``file_doc_audit_issue`` is exercised via ``--dry-run``
shape (``process_events`` propagates ``dry_run=True``) so the
subprocess call is never made.
"""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from unittest import mock

import pytest

import subprocess

from doc_audit.helpers.handle_drift_events import (
    Mapping,
    ProcessResult,
    append_unmapped,
    decode_diff,
    file_doc_audit_issue,
    find_mapping,
    load_mappings,
    main,
    process_events,
    read_cursor,
    write_cursor_atomic,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _load_mappings_fixture() -> list[Mapping]:
    return load_mappings(FIXTURES_DIR / "signal_to_doc_map_sample.json")


# ---------------------------------------------------------------------------
# Mapping load + lookup
# ---------------------------------------------------------------------------


def test_load_mappings_returns_dataclasses():
    mappings = _load_mappings_fixture()
    assert len(mappings) == 2
    assert all(isinstance(m, Mapping) for m in mappings)
    assert mappings[0].id == "openclaw-cron-drift"
    assert mappings[0].match == {
        "source": "audit.sh",
        "baseline_name": "openclaw-cron.txt",
    }


def test_find_mapping_matches_by_subset_of_event_keys():
    mappings = _load_mappings_fixture()
    event = {
        "source": "audit.sh",
        "baseline_name": "openclaw-cron.txt",
        "timestamp": "2026-05-20T10:00:00Z",
        "diff": "anything",
    }
    matched = find_mapping(event, mappings)
    assert matched is not None
    assert matched.id == "openclaw-cron-drift"


def test_find_mapping_returns_none_when_no_subset_matches():
    mappings = _load_mappings_fixture()
    event = {"source": "audit.sh", "baseline_name": "nonexistent.txt"}
    assert find_mapping(event, mappings) is None


# ---------------------------------------------------------------------------
# decode_diff
# ---------------------------------------------------------------------------


def test_decode_diff_returns_plain_diff_when_present():
    event = {"diff": "diff content"}
    assert decode_diff(event) == "diff content"


def test_decode_diff_decodes_base64_when_provided():
    # base64 of "diff content"
    event = {"diff_b64": "ZGlmZiBjb250ZW50"}
    assert decode_diff(event) == "diff content"


def test_decode_diff_returns_empty_when_neither_present():
    assert decode_diff({}) == ""


# ---------------------------------------------------------------------------
# Cursor atomic write
# ---------------------------------------------------------------------------


def test_write_cursor_atomic_creates_and_reads_back(tmp_path: Path):
    cursor_path = tmp_path / "cursor"
    write_cursor_atomic(cursor_path, 42)
    assert cursor_path.read_text() == "42"
    assert read_cursor(cursor_path) == 42


def test_write_cursor_atomic_overwrites_existing(tmp_path: Path):
    cursor_path = tmp_path / "cursor"
    cursor_path.write_text("7")
    write_cursor_atomic(cursor_path, 99)
    assert cursor_path.read_text() == "99"


def test_read_cursor_returns_zero_when_missing(tmp_path: Path):
    assert read_cursor(tmp_path / "does-not-exist") == 0


def test_read_cursor_returns_zero_when_malformed(tmp_path: Path):
    p = tmp_path / "cursor"
    p.write_text("not-an-int\n")
    assert read_cursor(p) == 0


def test_write_cursor_atomic_no_stray_tmp_files(tmp_path: Path):
    cursor_path = tmp_path / "cursor"
    write_cursor_atomic(cursor_path, 5)
    leftover_tmps = [p for p in tmp_path.iterdir() if p.name.endswith(".tmp") or ".tmp." in p.name]
    assert leftover_tmps == []


# ---------------------------------------------------------------------------
# append_unmapped
# ---------------------------------------------------------------------------


def test_append_unmapped_creates_parent_dir_and_appends(tmp_path: Path):
    unmapped = tmp_path / "nested" / "unmapped.jsonl"
    event1 = {"source": "audit.sh", "baseline_name": "a.txt"}
    event2 = {"source": "audit.sh", "baseline_name": "b.txt"}
    append_unmapped(unmapped, event1)
    append_unmapped(unmapped, event2)
    lines = unmapped.read_text().strip().splitlines()
    assert json.loads(lines[0]) == event1
    assert json.loads(lines[1]) == event2


# ---------------------------------------------------------------------------
# process_events end-to-end (dry-run + mocked gh)
# ---------------------------------------------------------------------------


def _write_fixture_events(target: Path) -> None:
    source = FIXTURES_DIR / "drift_events_sample.jsonl"
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")


def test_process_events_no_events_file(tmp_path: Path):
    result = process_events(
        events_path=tmp_path / "missing.jsonl",
        cursor_path=tmp_path / "cursor",
        mapping_path=FIXTURES_DIR / "signal_to_doc_map_sample.json",
        unmapped_path=tmp_path / "unmapped.jsonl",
        dry_run=True,
    )
    assert isinstance(result, ProcessResult)
    assert result.processed == 0
    assert result.exit_code == 0


def test_process_events_missing_mapping_returns_exit_code_2(tmp_path: Path):
    events = tmp_path / "events.jsonl"
    _write_fixture_events(events)
    result = process_events(
        events_path=events,
        cursor_path=tmp_path / "cursor",
        mapping_path=tmp_path / "missing-mapping.json",
        unmapped_path=tmp_path / "unmapped.jsonl",
        dry_run=True,
    )
    assert result.exit_code == 2
    assert result.processed == 0


def test_process_events_dry_run_mixed_matched_and_unmapped(tmp_path: Path):
    events = tmp_path / "events.jsonl"
    _write_fixture_events(events)
    cursor = tmp_path / "cursor"
    unmapped = tmp_path / "unmapped.jsonl"
    result = process_events(
        events_path=events,
        cursor_path=cursor,
        mapping_path=FIXTURES_DIR / "signal_to_doc_map_sample.json",
        unmapped_path=unmapped,
        dry_run=True,
    )
    assert result.exit_code == 0
    assert result.processed == 3
    # Two events match (openclaw-cron + listening-ports); one is unmapped.
    assert result.matched_filed == 2
    assert result.unmapped == 1
    assert result.errors == 0
    # Cursor is NOT written in dry-run mode
    assert not cursor.exists()
    # Unmapped log should contain exactly one event
    unmapped_lines = unmapped.read_text().strip().splitlines()
    assert len(unmapped_lines) == 1
    assert json.loads(unmapped_lines[0])["baseline_name"] == "unknown-baseline.txt"


def test_process_events_real_run_advances_cursor_atomically(tmp_path: Path, monkeypatch):
    events = tmp_path / "events.jsonl"
    _write_fixture_events(events)
    cursor = tmp_path / "cursor"
    unmapped = tmp_path / "unmapped.jsonl"

    # Mock subprocess.run for gh issue create so no network call happens.
    fake_run = mock.MagicMock(
        return_value=mock.MagicMock(
            returncode=0,
            stdout="https://github.com/kentonium3/kg-automation/issues/12345\n",
            stderr="",
        )
    )
    monkeypatch.setattr(
        "doc_audit.helpers.handle_drift_events.subprocess.run", fake_run
    )

    result = process_events(
        events_path=events,
        cursor_path=cursor,
        mapping_path=FIXTURES_DIR / "signal_to_doc_map_sample.json",
        unmapped_path=unmapped,
        dry_run=False,
    )

    assert result.exit_code == 0
    assert result.processed == 3
    assert result.matched_filed == 2
    assert result.unmapped == 1
    # Cursor is written and reflects new position
    assert cursor.exists()
    assert int(cursor.read_text()) == 3
    assert result.new_cursor == 3
    # gh issue create was invoked for the matched events
    assert fake_run.call_count == 2


def test_process_events_idempotent_when_cursor_at_end(tmp_path: Path):
    events = tmp_path / "events.jsonl"
    _write_fixture_events(events)
    cursor = tmp_path / "cursor"
    cursor.write_text("3")  # already past the fixture's 3 events
    unmapped = tmp_path / "unmapped.jsonl"

    result = process_events(
        events_path=events,
        cursor_path=cursor,
        mapping_path=FIXTURES_DIR / "signal_to_doc_map_sample.json",
        unmapped_path=unmapped,
        dry_run=True,
    )
    assert result.exit_code == 0
    assert result.processed == 0
    assert result.new_cursor == 3


# ---------------------------------------------------------------------------
# file_doc_audit_issue (dry-run + mocked gh)
# ---------------------------------------------------------------------------


def test_file_doc_audit_issue_dry_run_does_not_invoke_subprocess(monkeypatch):
    mappings = _load_mappings_fixture()
    event = {"source": "audit.sh", "baseline_name": "openclaw-cron.txt", "timestamp": "T"}
    fake_run = mock.MagicMock()
    monkeypatch.setattr(
        "doc_audit.helpers.handle_drift_events.subprocess.run", fake_run
    )
    ok, output = file_doc_audit_issue(event, mappings[0], "x/y", dry_run=True)
    assert ok is True
    assert "[dry-run]" in output
    assert fake_run.call_count == 0


def test_file_doc_audit_issue_real_run_uses_subprocess(monkeypatch):
    mappings = _load_mappings_fixture()
    event = {"source": "audit.sh", "baseline_name": "openclaw-cron.txt", "timestamp": "T"}
    fake_run = mock.MagicMock(
        return_value=mock.MagicMock(
            returncode=0,
            stdout="https://github.com/kentonium3/kg-automation/issues/42\n",
            stderr="",
        )
    )
    monkeypatch.setattr(
        "doc_audit.helpers.handle_drift_events.subprocess.run", fake_run
    )
    ok, output = file_doc_audit_issue(event, mappings[0], "x/y", dry_run=False)
    assert ok is True
    assert "issues/42" in output
    assert fake_run.call_count == 1


# ---------------------------------------------------------------------------
# Cycle 3 additions — file_doc_audit_issue failure legs (lines 227-230)
# ---------------------------------------------------------------------------


def test_file_doc_audit_issue_returns_failure_on_called_process_error(monkeypatch):
    """gh exit non-zero → (False, "gh issue create failed: ...")."""
    mappings = _load_mappings_fixture()
    event = {"source": "audit.sh", "baseline_name": "openclaw-cron.txt", "timestamp": "T"}
    err = subprocess.CalledProcessError(1, ["gh"], stderr="boom from gh")
    fake_run = mock.MagicMock(side_effect=err)
    monkeypatch.setattr(
        "doc_audit.helpers.handle_drift_events.subprocess.run", fake_run
    )
    ok, output = file_doc_audit_issue(event, mappings[0], "x/y", dry_run=False)
    assert ok is False
    assert "gh issue create failed" in output
    assert "boom from gh" in output


def test_file_doc_audit_issue_returns_failure_on_timeout(monkeypatch):
    """gh exceeds 60s → (False, "gh issue create timed out after 60s")."""
    mappings = _load_mappings_fixture()
    event = {"source": "audit.sh", "baseline_name": "openclaw-cron.txt", "timestamp": "T"}
    err = subprocess.TimeoutExpired(cmd=["gh"], timeout=60)
    fake_run = mock.MagicMock(side_effect=err)
    monkeypatch.setattr(
        "doc_audit.helpers.handle_drift_events.subprocess.run", fake_run
    )
    ok, output = file_doc_audit_issue(event, mappings[0], "x/y", dry_run=False)
    assert ok is False
    assert "timed out" in output


# ---------------------------------------------------------------------------
# decode_diff — base64 failure branch (lines 147-148)
# ---------------------------------------------------------------------------


def test_decode_diff_returns_placeholder_on_bad_base64():
    event = {"diff_b64": "!!! not valid base64 !!!"}
    out = decode_diff(event)
    # The except branch returns a literal placeholder string.
    assert out == "<diff decode failed>"


# ---------------------------------------------------------------------------
# write_cursor_atomic — exception cleanup (lines 126-131)
# ---------------------------------------------------------------------------


def test_write_cursor_atomic_cleans_up_temp_file_on_failure(tmp_path: Path, monkeypatch):
    cursor_path = tmp_path / "cursor"

    def boom(*args, **kwargs):
        raise OSError("simulated fdopen failure")

    monkeypatch.setattr(
        "doc_audit.helpers.handle_drift_events.os.fdopen", boom
    )
    with pytest.raises(OSError):
        write_cursor_atomic(cursor_path, 1)
    # No leftover .tmp files
    leftovers = [p for p in tmp_path.iterdir() if ".tmp" in p.name]
    assert leftovers == []


# ---------------------------------------------------------------------------
# process_events — additional branches
# ---------------------------------------------------------------------------


def test_process_events_skips_empty_lines(tmp_path: Path):
    """Empty/whitespace-only lines are skipped without failing."""
    events = tmp_path / "events.jsonl"
    events.write_text("\n\n  \n", encoding="utf-8")
    cursor = tmp_path / "cursor"
    result = process_events(
        events_path=events,
        cursor_path=cursor,
        mapping_path=FIXTURES_DIR / "signal_to_doc_map_sample.json",
        unmapped_path=tmp_path / "unmapped.jsonl",
        dry_run=True,
    )
    assert result.exit_code == 0
    # Empty lines count as processed (cursor advances over them) but
    # contribute zero to matched/unmapped/errors.
    assert result.matched_filed == 0
    assert result.unmapped == 0
    assert result.errors == 0


def test_process_events_skips_malformed_json_lines(tmp_path: Path):
    """Malformed JSON lines emit WARN and are skipped without error."""
    events = tmp_path / "events.jsonl"
    events.write_text("not-json-here\n{}\n", encoding="utf-8")
    cursor = tmp_path / "cursor"
    result = process_events(
        events_path=events,
        cursor_path=cursor,
        mapping_path=FIXTURES_DIR / "signal_to_doc_map_sample.json",
        unmapped_path=tmp_path / "unmapped.jsonl",
        dry_run=True,
    )
    assert result.exit_code == 0
    # 2 lines processed; both effectively no-ops in terms of matched/unmapped.
    # The `{}` line has no matching mapping → goes to unmapped.
    assert result.processed == 2
    assert result.matched_filed == 0
    assert result.unmapped == 1


def test_process_events_warns_when_new_events_exceed_limit(tmp_path: Path, capsys):
    """More new lines than --limit → warns and processes the first `limit` only."""
    events = tmp_path / "events.jsonl"
    fixture_lines = (FIXTURES_DIR / "drift_events_sample.jsonl").read_text(
        encoding="utf-8"
    )
    # Repeat the fixture lines a few times so there are clearly more than limit.
    events.write_text(fixture_lines * 3, encoding="utf-8")
    cursor = tmp_path / "cursor"
    result = process_events(
        events_path=events,
        cursor_path=cursor,
        mapping_path=FIXTURES_DIR / "signal_to_doc_map_sample.json",
        unmapped_path=tmp_path / "unmapped.jsonl",
        dry_run=True,
        limit=2,
    )
    # Only `limit` events processed.
    assert result.processed == 2
    captured = capsys.readouterr()
    assert "exceeds --limit" in captured.err


def test_process_events_breaks_on_file_issue_failure_so_cursor_stalls(
    tmp_path: Path, monkeypatch
):
    """If gh issue create fails on a matched event, processing breaks and cursor stops."""
    events = tmp_path / "events.jsonl"
    _write_fixture_events(events)
    cursor = tmp_path / "cursor"
    unmapped = tmp_path / "unmapped.jsonl"

    # First subprocess call fails — simulates gh issue create failure.
    fake_run = mock.MagicMock(
        side_effect=subprocess.CalledProcessError(1, ["gh"], stderr="boom")
    )
    monkeypatch.setattr(
        "doc_audit.helpers.handle_drift_events.subprocess.run", fake_run
    )

    result = process_events(
        events_path=events,
        cursor_path=cursor,
        mapping_path=FIXTURES_DIR / "signal_to_doc_map_sample.json",
        unmapped_path=unmapped,
        dry_run=False,
    )

    assert result.exit_code == 1
    assert result.errors == 1
    # Loop broke after the first matched event errored — second event was not
    # processed at all (processed counter NOT incremented after `break`).
    assert result.processed == 0
    # Cursor was nonetheless written by the SUMMARY branch.
    assert cursor.exists()
    # new_cursor reflects whatever the function recorded (cursor + processed).
    assert result.new_cursor == 0


# ---------------------------------------------------------------------------
# main() CLI wrapper (lines 389-431)
# ---------------------------------------------------------------------------


def test_main_dry_run_exit_code_zero(tmp_path: Path):
    events = tmp_path / "events.jsonl"
    _write_fixture_events(events)
    cursor = tmp_path / "cursor"
    unmapped = tmp_path / "unmapped.jsonl"
    rc = main(
        [
            "--events", str(events),
            "--cursor", str(cursor),
            "--mapping", str(FIXTURES_DIR / "signal_to_doc_map_sample.json"),
            "--unmapped", str(unmapped),
            "--dry-run",
        ]
    )
    assert rc == 0


def test_main_returns_exit_code_2_when_mapping_missing(tmp_path: Path):
    events = tmp_path / "events.jsonl"
    _write_fixture_events(events)
    rc = main(
        [
            "--events", str(events),
            "--cursor", str(tmp_path / "cursor"),
            "--mapping", str(tmp_path / "missing.json"),
            "--unmapped", str(tmp_path / "unmapped.jsonl"),
            "--dry-run",
        ]
    )
    assert rc == 2
