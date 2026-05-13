"""Tests for the callout-marker + routing-entry helper scripts (WP03).

Covers FR-008/FR-009 (marker shape + idempotency), FR-010 (auto-cleanup
no-op semantics), and the append_routing_entry.py CLI surface (FR-001).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from inject_parse_error_marker import MARKER_PREFIX, inject_marker
from strip_parse_error_marker import strip_marker


# ---------- inject_marker ----------


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_inject_into_well_formed_frontmatter_inserts_after_closing_fence(
    tmp_path: Path,
):
    p = tmp_path / "note.md"
    p.write_text(
        "---\nstatus: unprocessed\n---\n\nOriginal body.\n", encoding="utf-8"
    )
    changed = inject_marker(p, issue_number=42, date_str="2026-05-12")
    assert changed is True
    text = _read(p)
    lines = text.splitlines()
    assert lines[0] == "---"
    assert lines[1] == "status: unprocessed"
    assert lines[2] == "---"
    # Marker should come after the closing fence + blank line.
    marker_lines = [i for i, ln in enumerate(lines) if ln.startswith(MARKER_PREFIX)]
    assert len(marker_lines) == 1
    assert marker_lines[0] >= 3
    assert "issue #42" in lines[marker_lines[0]]
    assert "2026-05-12" in lines[marker_lines[0]]
    assert "Original body." in text  # body preserved


def test_inject_into_no_frontmatter_inserts_at_top(tmp_path: Path):
    p = tmp_path / "note.md"
    p.write_text("Just a body line.\nMore body.\n", encoding="utf-8")
    changed = inject_marker(p, issue_number=7, date_str="2026-05-12")
    assert changed is True
    lines = _read(p).splitlines()
    assert lines[0].startswith(MARKER_PREFIX)
    assert "issue #7" in lines[0]
    assert "Just a body line." in _read(p)


def test_inject_when_marker_exists_replaces_in_place_no_duplicate(tmp_path: Path):
    p = tmp_path / "note.md"
    p.write_text(
        "---\nstatus: unprocessed\n---\n\nBody.\n", encoding="utf-8"
    )
    inject_marker(p, issue_number=1, date_str="2026-05-10")
    inject_marker(p, issue_number=2, date_str="2026-05-11")
    inject_marker(p, issue_number=3, date_str="2026-05-12")
    text = _read(p)
    markers = [ln for ln in text.splitlines() if ln.startswith(MARKER_PREFIX)]
    assert len(markers) == 1
    assert "issue #3" in markers[0]
    assert "2026-05-12" in markers[0]


def test_inject_when_marker_exists_updates_date_and_issue(tmp_path: Path):
    p = tmp_path / "note.md"
    p.write_text(
        "---\nstatus: unprocessed\n---\n\n"
        "> [!error] felix-capture: could not parse frontmatter on 2026-04-01. "
        'See issue #99 ("Inbox quality" issue for this run).\n\n'
        "Body.\n",
        encoding="utf-8",
    )
    changed = inject_marker(p, issue_number=200, date_str="2026-05-12")
    assert changed is True
    text = _read(p)
    assert "2026-05-12" in text
    assert "issue #200" in text
    assert "2026-04-01" not in text
    assert "issue #99" not in text


def test_inject_idempotent_when_same_marker(tmp_path: Path):
    p = tmp_path / "note.md"
    p.write_text(
        "---\nstatus: unprocessed\n---\n\nBody.\n", encoding="utf-8"
    )
    inject_marker(p, issue_number=42, date_str="2026-05-12")
    text_first = _read(p)
    changed = inject_marker(p, issue_number=42, date_str="2026-05-12")
    assert changed is False  # same marker → no write
    assert _read(p) == text_first


def test_inject_preserves_body_content(tmp_path: Path):
    p = tmp_path / "note.md"
    body = (
        "---\nstatus: unprocessed\n---\n\n"
        "# A heading\n\n"
        "Some prose with > [!note] a callout and `code`.\n\n"
        "- bullet 1\n- bullet 2\n"
    )
    p.write_text(body, encoding="utf-8")
    inject_marker(p, issue_number=10, date_str="2026-05-12")
    text = _read(p)
    for fragment in [
        "# A heading",
        "Some prose with > [!note] a callout and `code`.",
        "- bullet 1",
        "- bullet 2",
    ]:
        assert fragment in text, f"missing: {fragment!r}"


def test_inject_does_not_leave_tmp_file(tmp_path: Path):
    p = tmp_path / "note.md"
    p.write_text(
        "---\nstatus: unprocessed\n---\n\nBody.\n", encoding="utf-8"
    )
    inject_marker(p, issue_number=42, date_str="2026-05-12")
    leftover = list(tmp_path.glob("note.md.*.tmp"))
    assert leftover == [], f"tempfile leftover: {leftover}"


def test_inject_no_closing_fence_inserts_at_top(tmp_path: Path):
    """When the fence pair is incomplete, fall back to top insertion."""
    p = tmp_path / "note.md"
    p.write_text("---\nstatus: unprocessed\n(no closing fence)\n", encoding="utf-8")
    changed = inject_marker(p, issue_number=5, date_str="2026-05-12")
    assert changed is True
    lines = _read(p).splitlines()
    # Insertion is at top because frontmatter pair is incomplete.
    assert lines[0].startswith(MARKER_PREFIX)


def test_inject_bom_prefixed_frontmatter_inserts_after_fence(tmp_path: Path):
    """Codex WP03 review [P2]: BOM-prefixed frontmatter is still legitimate
    frontmatter. Marker must go AFTER the closing fence, not at line 0
    before the BOM/fence. Otherwise fixing the BOM later still leaves
    leading content before the fence and the note stays in parse-failure.
    """
    p = tmp_path / "note.md"
    p.write_text(
        "﻿---\nstatus: unprocessed\n---\n\nBody.\n", encoding="utf-8"
    )
    changed = inject_marker(p, issue_number=42, date_str="2026-05-12")
    assert changed is True
    lines = _read(p).splitlines()
    # First line should still be BOM-fence (we don't modify the BOM here).
    assert lines[0].lstrip("﻿") == "---"
    # Marker must come AFTER the closing fence at line 2.
    marker_idx = next(
        i for i, ln in enumerate(lines) if ln.startswith(MARKER_PREFIX)
    )
    assert marker_idx > 2
    assert "issue #42" in lines[marker_idx]


def test_inject_multi_blank_after_fence_replaces_existing_no_duplicate(
    tmp_path: Path,
):
    """Codex WP03 review [P2]: when many blank lines follow the closing
    fence, an existing marker at body-start (after several blanks) must
    still be found and replaced in place — not duplicated.
    """
    p = tmp_path / "note.md"
    p.write_text(
        "---\nstatus: unprocessed\n---\n"
        "\n\n\n"  # 3 blank lines after fence
        "> [!error] felix-capture: could not parse frontmatter on 2026-05-01. "
        'See issue #1 ("Inbox quality" issue for this run).\n\n'
        "Body content.\n",
        encoding="utf-8",
    )
    changed = inject_marker(p, issue_number=99, date_str="2026-05-12")
    assert changed is True
    text = _read(p)
    markers = [ln for ln in text.splitlines() if ln.startswith(MARKER_PREFIX)]
    assert len(markers) == 1, f"expected 1 marker, got {len(markers)}: {markers}"
    assert "issue #99" in markers[0]
    assert "2026-05-12" in markers[0]


# ---------- strip_marker ----------


def test_strip_when_marker_present_removes_marker_line(tmp_path: Path):
    p = tmp_path / "note.md"
    p.write_text(
        "---\nstatus: unprocessed\n---\n\n"
        "> [!error] felix-capture: could not parse frontmatter on 2026-05-12. "
        'See issue #1 ("Inbox quality" issue for this run).\n\n'
        "Body content.\n",
        encoding="utf-8",
    )
    changed = strip_marker(p)
    assert changed is True
    text = _read(p)
    assert MARKER_PREFIX not in text
    assert "Body content." in text


def test_strip_removes_following_blank_line(tmp_path: Path):
    p = tmp_path / "note.md"
    p.write_text(
        "---\nstatus: unprocessed\n---\n\n"
        "> [!error] felix-capture: blah\n"
        "\n"
        "Body content.\n",
        encoding="utf-8",
    )
    strip_marker(p)
    text = _read(p)
    # The blank line that followed the marker should also be gone — i.e.,
    # the body should pick up directly after the frontmatter's existing blank.
    assert "\n\nBody content." in text
    assert "\n\n\nBody content." not in text


def test_strip_when_marker_absent_is_noop(tmp_path: Path):
    p = tmp_path / "note.md"
    original = "---\nstatus: unprocessed\n---\n\nBody.\n"
    p.write_text(original, encoding="utf-8")
    changed = strip_marker(p)
    assert changed is False
    assert _read(p) == original


def test_strip_preserves_other_content(tmp_path: Path):
    p = tmp_path / "note.md"
    p.write_text(
        "---\nstatus: unprocessed\n---\n\n"
        "> [!error] felix-capture: blah\n\n"
        "# Heading\n\nBody with `code`.\n- bullet\n",
        encoding="utf-8",
    )
    strip_marker(p)
    text = _read(p)
    for fragment in ["# Heading", "Body with `code`.", "- bullet"]:
        assert fragment in text


def test_strip_does_not_strip_non_felix_capture_callouts(tmp_path: Path):
    p = tmp_path / "note.md"
    p.write_text(
        "---\nstatus: unprocessed\n---\n\n"
        "> [!warning] something else entirely\n\n"
        "Body.\n",
        encoding="utf-8",
    )
    changed = strip_marker(p)
    assert changed is False
    assert "[!warning] something else entirely" in _read(p)


def test_strip_no_frontmatter_marker_at_top(tmp_path: Path):
    p = tmp_path / "note.md"
    p.write_text(
        "> [!error] felix-capture: could not parse frontmatter on 2026-05-12. "
        'See issue #1 ("Inbox quality" issue for this run).\n\n'
        "Body.\n",
        encoding="utf-8",
    )
    changed = strip_marker(p)
    assert changed is True
    text = _read(p)
    assert MARKER_PREFIX not in text
    assert "Body." in text


def test_strip_with_bom_prefixed_frontmatter(tmp_path: Path):
    """Codex WP03 review [P2]: BOM-prefixed frontmatter should still be
    recognized so the marker is found after the closing fence rather than
    the strip scan falling back to line 0.
    """
    p = tmp_path / "note.md"
    p.write_text(
        "﻿---\nstatus: unprocessed\n---\n\n"
        "> [!error] felix-capture: blah\n\n"
        "Body.\n",
        encoding="utf-8",
    )
    changed = strip_marker(p)
    assert changed is True
    assert MARKER_PREFIX not in _read(p)
    assert "Body." in _read(p)


def test_strip_ignores_deep_marker_in_no_frontmatter_note(tmp_path: Path):
    """Codex WP03 fix-review [P2]: in a no-frontmatter note, the scan
    window is bounded to ~3 lines from line 0. A marker buried deeper
    in the body (after a blank gap) must NOT be removed — that's defensive
    behavior to avoid clobbering user-authored content.
    """
    p = tmp_path / "note.md"
    p.write_text(
        "First body line.\n"
        "Second body line.\n"
        "Third body line.\n"
        "\n\n\n"
        "> [!error] felix-capture: deep marker the user typed by mistake\n",
        encoding="utf-8",
    )
    original = _read(p)
    changed = strip_marker(p)
    assert changed is False
    assert _read(p) == original


def test_inject_ignores_deep_marker_in_no_frontmatter_note(tmp_path: Path):
    """Companion to the strip test: inject must not refresh a deep
    no-frontmatter marker — it inserts a new one at line 0 instead.
    """
    p = tmp_path / "note.md"
    p.write_text(
        "First body line.\n"
        "Second body line.\n"
        "Third body line.\n"
        "\n\n\n"
        "> [!error] felix-capture: deep marker (older or user-typed)\n",
        encoding="utf-8",
    )
    inject_marker(p, issue_number=42, date_str="2026-05-12")
    text = _read(p)
    markers = [ln for ln in text.splitlines() if ln.startswith(MARKER_PREFIX)]
    # Two markers: the new one at top + the deep one untouched.
    assert len(markers) == 2
    assert "issue #42" in markers[0]
    assert "deep marker" in markers[1]
    assert text.splitlines()[0].startswith(MARKER_PREFIX)


# ---------- append_routing_entry.py (subprocess smoke tests) ----------


def _routing_script() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "inbox"
        / "append_routing_entry.py"
    )


def test_append_routing_entry_writes_jsonl_line(tmp_path: Path, monkeypatch):
    log_path = tmp_path / "routing.jsonl"
    monkeypatch.setenv("PYTHONPATH", str(_routing_script().parent))
    # Use a Python sys.path hack via subprocess by writing to the default
    # path location — easier to override the default by monkeypatching
    # routing_log.DEFAULT_ROUTING_LOG_PATH inside a one-shot Python invocation.
    code = (
        f"import sys; sys.path.insert(0, {str(_routing_script().parent)!r});"
        f"import routing_log; "
        f"routing_log.DEFAULT_ROUTING_LOG_PATH = __import__('pathlib').Path({str(log_path)!r}); "
        f"import append_routing_entry; "
        f"sys.exit(append_routing_entry.main(['note-2026-05-12.md', '101', '202', 'some excerpt']))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert log_path.exists(), result.stdout + result.stderr
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["filename"] == "note-2026-05-12.md"
    assert entry["issue_number"] == 101
    assert entry["vikunja_task_id"] == 202
    assert entry["note_excerpt"] == "some excerpt"
    assert entry["routed_at"].endswith("Z")


def test_append_routing_entry_handles_dash_task_id(tmp_path: Path):
    log_path = tmp_path / "routing.jsonl"
    code = (
        f"import sys; sys.path.insert(0, {str(_routing_script().parent)!r});"
        f"import routing_log; "
        f"routing_log.DEFAULT_ROUTING_LOG_PATH = __import__('pathlib').Path({str(log_path)!r}); "
        f"import append_routing_entry; "
        f"sys.exit(append_routing_entry.main(['note.md', '55', '-']))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    entry = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert entry["vikunja_task_id"] is None
    assert entry["issue_number"] == 55
