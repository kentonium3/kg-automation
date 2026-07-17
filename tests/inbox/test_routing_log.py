"""Tests for scripts/inbox/routing_log.py."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from routing_log import (
    DEFAULT_ROUTING_LOG_PATH,
    KNOWN_KINDS,
    RoutingEntry,
    RoutingLogReader,
    RoutingLogWriter,
    block_hash,
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


# ---------------------------------------------------------------------------
# #737 — calendar routes: kind / destination fields
# ---------------------------------------------------------------------------


def test_append_calendar_route_records_kind_and_destination(tmp_path: Path):
    log = tmp_path / "log.jsonl"
    writer = RoutingLogWriter(log)
    entry = writer.append(
        filename="Note 1.md", kind="calendar", destination="evt_abc", note_excerpt="Emanuel call"
    )
    assert entry.kind == "calendar"
    assert entry.destination == "evt_abc"
    assert entry.issue_number is None
    assert entry.vikunja_task_id is None
    row = json.loads(log.read_text().splitlines()[0])
    assert row["kind"] == "calendar"
    assert row["destination"] == "evt_abc"
    assert row["filename"] == "Note 1.md"


def test_append_issue_task_defaults_kind(tmp_path: Path):
    log = tmp_path / "log.jsonl"
    writer = RoutingLogWriter(log)
    entry = writer.append(filename="n.md", issue_number=42, vikunja_task_id=7)
    assert entry.kind == "issue_task"
    assert entry.destination == ""
    assert entry.issue_number == 42


def test_reader_tolerates_old_rows_without_kind(tmp_path: Path):
    # Rows written before #737 have no kind/destination — dedup still works.
    log = tmp_path / "log.jsonl"
    log.write_text(
        json.dumps({"filename": "old.md", "issue_number": 5, "vikunja_task_id": None,
                    "routed_at": "2026-01-01T00:00:00Z", "note_excerpt": ""}) + "\n"
    )
    reader = RoutingLogReader(log)
    assert reader.has("old.md")


# ---------------------------------------------------------------------------
# WP01 (#746) — D10 per-block routing-log keys
# ---------------------------------------------------------------------------


# ---------- block_hash helper ----------


def test_block_hash_is_deterministic():
    assert block_hash("- [ ] call Emanuel") == block_hash("- [ ] call Emanuel")


def test_block_hash_normalizes_surrounding_whitespace():
    # Leading/trailing whitespace is stripped before hashing so an unchanged
    # block re-hashes identically across ticks.
    assert block_hash("  hello  ") == block_hash("hello")
    assert block_hash("\nhello\n") == block_hash("hello")


def test_block_hash_differs_for_different_content():
    assert block_hash("block one") != block_hash("block two")


def test_block_hash_is_sha256_hexdigest():
    h = block_hash("anything")
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


# ---------- RoutingEntry block fields ----------


def test_entry_block_fields_default_none():
    entry = RoutingEntry(
        filename="f.md",
        issue_number=None,
        vikunja_task_id=None,
        routed_at="2026-01-01T00:00:00Z",
    )
    assert entry.block_index is None
    assert entry.block_hash is None
    d = entry.to_dict()
    assert d["block_index"] is None
    assert d["block_hash"] is None


def test_entry_block_fields_round_trip(tmp_path: Path):
    log = tmp_path / "log.jsonl"
    writer = RoutingLogWriter(log)
    bh = block_hash("- [ ] a block")
    entry = writer.append(
        filename="multi.md",
        kind="someday",
        destination="512",
        block_index=2,
        block_hash=bh,
    )
    assert entry.block_index == 2
    assert entry.block_hash == bh
    row = json.loads(log.read_text().splitlines()[0])
    assert row["block_index"] == 2
    assert row["block_hash"] == bh
    assert row["kind"] == "someday"
    assert row["destination"] == "512"


# ---------- has_block ----------


def _write_rows(log: Path, rows: list[dict]) -> None:
    log.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def test_has_block_true_when_all_three_match(tmp_path: Path):
    log = tmp_path / "log.jsonl"
    bh = block_hash("payload")
    _write_rows(
        log,
        [
            {"filename": "n.md", "issue_number": None, "vikunja_task_id": None,
             "routed_at": "2026-01-01T00:00:00Z", "kind": "someday",
             "destination": "1", "block_index": 0, "block_hash": bh},
        ],
    )
    reader = RoutingLogReader(log)
    assert reader.has_block("n.md", 0, bh) is True


def test_has_block_false_when_hash_differs(tmp_path: Path):
    log = tmp_path / "log.jsonl"
    _write_rows(
        log,
        [
            {"filename": "n.md", "issue_number": None, "vikunja_task_id": None,
             "routed_at": "2026-01-01T00:00:00Z", "kind": "someday",
             "destination": "1", "block_index": 0, "block_hash": block_hash("old")},
        ],
    )
    reader = RoutingLogReader(log)
    assert reader.has_block("n.md", 0, block_hash("new")) is False


def test_has_block_false_when_index_differs(tmp_path: Path):
    log = tmp_path / "log.jsonl"
    bh = block_hash("payload")
    _write_rows(
        log,
        [
            {"filename": "n.md", "issue_number": None, "vikunja_task_id": None,
             "routed_at": "2026-01-01T00:00:00Z", "kind": "someday",
             "destination": "1", "block_index": 0, "block_hash": bh},
        ],
    )
    reader = RoutingLogReader(log)
    assert reader.has_block("n.md", 1, bh) is False


def test_has_block_false_when_filename_absent(tmp_path: Path):
    log = tmp_path / "log.jsonl"
    bh = block_hash("payload")
    _write_rows(
        log,
        [
            {"filename": "n.md", "issue_number": None, "vikunja_task_id": None,
             "routed_at": "2026-01-01T00:00:00Z", "kind": "someday",
             "destination": "1", "block_index": 0, "block_hash": bh},
        ],
    )
    reader = RoutingLogReader(log)
    assert reader.has_block("other.md", 0, bh) is False


def test_has_block_legacy_row_satisfies_filename_fallback(tmp_path: Path):
    # A pre-WP01 row (no block_index) for a filename satisfies has_block for
    # ANY block of that filename — preserves the #737 calendar dedup.
    log = tmp_path / "log.jsonl"
    _write_rows(
        log,
        [
            {"filename": "cal.md", "issue_number": None, "vikunja_task_id": None,
             "routed_at": "2026-01-01T00:00:00Z", "kind": "calendar",
             "destination": "evt_1"},  # no block_index / block_hash
        ],
    )
    reader = RoutingLogReader(log)
    assert reader.has_block("cal.md", 0, block_hash("whatever")) is True
    assert reader.has_block("cal.md", 5, "does-not-matter") is True


def test_has_block_prefers_exact_match_over_missing(tmp_path: Path):
    # Block-keyed rows for one filename must not falsely match a different
    # block; only an exact key or a legacy (index-less) row matches.
    log = tmp_path / "log.jsonl"
    bh0 = block_hash("block 0")
    _write_rows(
        log,
        [
            {"filename": "n.md", "issue_number": None, "vikunja_task_id": None,
             "routed_at": "2026-01-01T00:00:00Z", "kind": "someday",
             "destination": "1", "block_index": 0, "block_hash": bh0},
        ],
    )
    reader = RoutingLogReader(log)
    assert reader.has_block("n.md", 0, bh0) is True
    assert reader.has_block("n.md", 1, block_hash("block 1")) is False


def test_has_block_skips_malformed_and_missing_filename(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    log = tmp_path / "log.jsonl"
    bh = block_hash("payload")
    log.write_text(
        "{not json\n"
        + json.dumps({"issue_number": 1, "routed_at": "2026-01-01T00:00:00Z"})  # no filename
        + "\n"
        + json.dumps({"filename": "n.md", "issue_number": None, "vikunja_task_id": None,
                      "routed_at": "2026-01-02T00:00:00Z", "kind": "someday",
                      "destination": "1", "block_index": 0, "block_hash": bh})
        + "\n"
    )
    reader = RoutingLogReader(log)
    assert reader.has_block("n.md", 0, bh) is True
    err = capsys.readouterr().err
    assert "malformed JSON" in err
    assert "missing/invalid filename" in err


def test_has_block_and_routed_filenames_share_single_read(tmp_path: Path):
    # has_block + routed_filenames must not double-read; mutating the file
    # after first access is invisible (read-once per reader instance).
    log = tmp_path / "log.jsonl"
    bh = block_hash("payload")
    _write_rows(
        log,
        [
            {"filename": "n.md", "issue_number": None, "vikunja_task_id": None,
             "routed_at": "2026-01-01T00:00:00Z", "kind": "someday",
             "destination": "1", "block_index": 0, "block_hash": bh},
        ],
    )
    reader = RoutingLogReader(log)
    assert reader.has_block("n.md", 0, bh) is True
    # Overwrite underneath — cached reader must not see the change.
    _write_rows(
        log,
        [
            {"filename": "m.md", "issue_number": None, "vikunja_task_id": None,
             "routed_at": "2026-01-02T00:00:00Z", "kind": "someday",
             "destination": "9", "block_index": 3, "block_hash": bh},
        ],
    )
    assert reader.routed_filenames() == {"n.md"}
    assert reader.has_block("m.md", 3, bh) is False


# ---------- grown kind vocabulary + destination ----------


@pytest.mark.parametrize(
    "kind,destination",
    [
        ("someday", "512"),
        ("journal", "/data/journal/2026-07-17.md"),
        ("vikunja_task", "777"),
        ("github_issue", "746"),
        ("empty", ""),
        ("calendar", "evt_1"),
        ("issue_task", ""),
    ],
)
def test_writer_accepts_all_known_kinds_and_populates_destination(
    tmp_path: Path, kind: str, destination: str
):
    log = tmp_path / "log.jsonl"
    writer = RoutingLogWriter(log)
    entry = writer.append(filename="n.md", kind=kind, destination=destination)
    assert entry.kind == kind
    assert entry.destination == destination
    row = json.loads(log.read_text().splitlines()[0])
    assert row["kind"] == kind
    assert row["destination"] == destination


def test_known_kinds_covers_expected_set():
    assert KNOWN_KINDS == frozenset(
        {
            "issue_task",
            "calendar",
            "someday",
            "journal",
            "vikunja_task",
            "github_issue",
            "empty",
        }
    )
