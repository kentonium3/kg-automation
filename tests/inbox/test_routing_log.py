"""Tests for scripts/inbox/routing_log.py."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from routing_log import (
    DEFAULT_ROUTING_LOG_PATH,
    RoutingEntry,
    RoutingLogReader,
    RoutingLogWriter,
)


# ---------- Reader ----------


def test_reader_returns_empty_set_when_file_missing(tmp_path: Path):
    reader = RoutingLogReader(tmp_path / "does-not-exist.jsonl")
    assert reader.routed_filenames() == set()


def test_reader_returns_filenames_when_present(tmp_path: Path):
    log = tmp_path / "log.jsonl"
    log.write_text(
        "\n".join(
            json.dumps(d)
            for d in [
                {"filename": "a.md", "issue_number": 1, "routed_at": "2026-01-01T00:00:00Z"},
                {"filename": "b.md", "issue_number": 2, "routed_at": "2026-01-02T00:00:00Z"},
                {"filename": "c.md", "issue_number": 3, "routed_at": "2026-01-03T00:00:00Z"},
            ]
        )
        + "\n"
    )
    reader = RoutingLogReader(log)
    assert reader.routed_filenames() == {"a.md", "b.md", "c.md"}


def test_reader_skips_malformed_lines_with_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    log = tmp_path / "log.jsonl"
    log.write_text(
        json.dumps({"filename": "valid.md", "issue_number": 1, "routed_at": "2026-01-01T00:00:00Z"})
        + "\n"
        + "{this is not json\n"
        + json.dumps({"filename": "another.md", "issue_number": 2, "routed_at": "2026-01-02T00:00:00Z"})
        + "\n"
    )
    reader = RoutingLogReader(log)
    result = reader.routed_filenames()
    assert result == {"valid.md", "another.md"}
    err = capsys.readouterr().err
    assert "malformed JSON" in err


def test_reader_caches_after_first_read(tmp_path: Path):
    log = tmp_path / "log.jsonl"
    log.write_text(
        json.dumps({"filename": "a.md", "issue_number": 1, "routed_at": "2026-01-01T00:00:00Z"})
        + "\n"
    )
    reader = RoutingLogReader(log)
    assert reader.routed_filenames() == {"a.md"}

    # Mutate the file underneath; cached reader should NOT see the new content.
    log.write_text(
        json.dumps({"filename": "b.md", "issue_number": 2, "routed_at": "2026-01-02T00:00:00Z"})
        + "\n"
    )
    assert reader.routed_filenames() == {"a.md"}


def test_has_returns_true_for_present_filename(tmp_path: Path):
    log = tmp_path / "log.jsonl"
    log.write_text(
        json.dumps({"filename": "present.md", "issue_number": 1, "routed_at": "2026-01-01T00:00:00Z"})
        + "\n"
    )
    reader = RoutingLogReader(log)
    assert reader.has("present.md") is True


def test_has_returns_false_for_absent_filename(tmp_path: Path):
    log = tmp_path / "log.jsonl"
    log.write_text(
        json.dumps({"filename": "present.md", "issue_number": 1, "routed_at": "2026-01-01T00:00:00Z"})
        + "\n"
    )
    reader = RoutingLogReader(log)
    assert reader.has("absent.md") is False


def test_reader_skips_lines_with_missing_filename(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    log = tmp_path / "log.jsonl"
    log.write_text(
        json.dumps({"issue_number": 1, "routed_at": "2026-01-01T00:00:00Z"})  # no filename
        + "\n"
        + json.dumps({"filename": "good.md", "issue_number": 2, "routed_at": "2026-01-02T00:00:00Z"})
        + "\n"
    )
    reader = RoutingLogReader(log)
    assert reader.routed_filenames() == {"good.md"}
    assert "missing/invalid filename" in capsys.readouterr().err


# ---------- Writer ----------


def test_writer_appends_single_line(tmp_path: Path):
    log = tmp_path / "log.jsonl"
    writer = RoutingLogWriter(log)
    entry = writer.append(
        filename="test.md",
        issue_number=176,
        vikunja_task_id=46,
        note_excerpt="An excerpt",
    )
    assert log.exists()
    lines = log.read_text().splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["filename"] == "test.md"
    assert parsed["issue_number"] == 176
    assert parsed["vikunja_task_id"] == 46
    assert parsed["note_excerpt"] == "An excerpt"
    assert parsed["routed_at"] == entry.routed_at


def test_writer_appends_does_not_truncate(tmp_path: Path):
    log = tmp_path / "log.jsonl"
    writer = RoutingLogWriter(log)
    writer.append(filename="first.md", issue_number=1)
    writer.append(filename="second.md", issue_number=2)
    lines = log.read_text().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["filename"] == "first.md"
    assert json.loads(lines[1])["filename"] == "second.md"


def test_writer_creates_parent_directory(tmp_path: Path):
    deep = tmp_path / "nested" / "dirs" / "log.jsonl"
    assert not deep.parent.exists()
    writer = RoutingLogWriter(deep)
    writer.append(filename="x.md", issue_number=1)
    assert deep.exists()
    assert deep.parent.exists()


def test_writer_truncates_note_excerpt_at_120_chars(tmp_path: Path):
    log = tmp_path / "log.jsonl"
    long_excerpt = "x" * 200
    writer = RoutingLogWriter(log)
    entry = writer.append(filename="t.md", issue_number=1, note_excerpt=long_excerpt)
    assert len(entry.note_excerpt) == 120


def test_writer_sets_routed_at_iso_utc(tmp_path: Path):
    log = tmp_path / "log.jsonl"
    writer = RoutingLogWriter(log)
    entry = writer.append(filename="t.md", issue_number=1)
    # Should parse via fromisoformat. Replace 'Z' with '+00:00' for stdlib < 3.11 compat.
    routed_at = entry.routed_at.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(routed_at)
    assert parsed.tzinfo is not None


def test_writer_handles_none_task_id(tmp_path: Path):
    log = tmp_path / "log.jsonl"
    writer = RoutingLogWriter(log)
    writer.append(filename="t.md", issue_number=1, vikunja_task_id=None)
    parsed = json.loads(log.read_text())
    assert parsed["vikunja_task_id"] is None


# ---------- Entry dataclass ----------


def test_entry_is_frozen():
    entry = RoutingEntry(
        filename="f.md",
        issue_number=1,
        vikunja_task_id=None,
        routed_at="2026-01-01T00:00:00Z",
    )
    with pytest.raises(Exception):
        entry.filename = "other.md"  # type: ignore[misc]


def test_default_routing_log_path_under_data_services():
    # Sanity check that the default path is what the spec / contract say.
    # WP02 (cycle 2): relocated from ~/second-brain/agents/state/ to
    # /data/services/openclaw/state/ per #656 (persistent-state boundary fix).
    assert str(DEFAULT_ROUTING_LOG_PATH) == "/data/services/openclaw/state/inbox-routing.jsonl"
    assert DEFAULT_ROUTING_LOG_PATH.name == "inbox-routing.jsonl"
