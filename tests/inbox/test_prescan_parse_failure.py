"""Tests for the extended classifier in scripts/inbox/prescan.py.

Covers the FR-005 parse-failure detection paths + the mission-027 regression +
the routing-log-aware dedup integration.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from prescan import (
    _detect_malformation,
    _has_parse_error_marker,
    classify_file,
)
from routing_log import RoutingLogWriter


FIXTURES = Path(__file__).resolve().parent / "fixtures"
NOW = datetime(2026, 5, 12, 12, 0, 0, tzinfo=timezone.utc)


# ---------- _detect_malformation ----------


def test_detect_well_formed_returns_none():
    text = (FIXTURES / "inbox-well-formed.md").read_text(encoding="utf-8")
    assert _detect_malformation(text) is None


def test_detect_leading_blank_lines_returns_none_regression():
    """Mission-027 regression: a single leading blank line before `---`
    must NOT be flagged as malformed. The first non-blank line IS exactly
    `---`, so this passes through to classify as `unprocessed`.
    """
    text = (FIXTURES / "inbox-leading-blank-lines.md").read_text(encoding="utf-8")
    assert _detect_malformation(text) is None


def test_detect_multi_leading_blanks_returns_none_regression():
    """Multiple leading blanks: same behavior — first non-blank == `---`."""
    text = (FIXTURES / "inbox-leading-newline-before-fence.md").read_text(encoding="utf-8")
    assert _detect_malformation(text) is None


def test_detect_utf8_bom_returns_reason():
    text = (FIXTURES / "inbox-utf8-bom.md").read_text(encoding="utf-8")
    reason = _detect_malformation(text)
    assert reason is not None
    assert "BOM" in reason


def test_detect_missing_close_fence_returns_reason():
    text = (FIXTURES / "inbox-missing-close-fence.md").read_text(encoding="utf-8")
    reason = _detect_malformation(text)
    assert reason is not None
    assert "missing closing" in reason


def test_detect_no_frontmatter_returns_none():
    """A note with no frontmatter at all is NOT a parse failure — existing
    classification path treats it as `unprocessed`.
    """
    text = (FIXTURES / "inbox-no-frontmatter.md").read_text(encoding="utf-8")
    assert _detect_malformation(text) is None


def test_detect_leading_non_blank_content_returns_reason():
    """Specifically: leading non-blank characters BEFORE a `---` fence
    indicate the user attempted frontmatter but got the position wrong.
    """
    text = "some leading prose\n\n---\nfoo: bar\n---\n\nbody\n"
    reason = _detect_malformation(text)
    assert reason is not None
    assert "leading whitespace or content" in reason


def test_detect_inline_dashes_in_prose_returns_none():
    """Notes whose first non-blank line contains inline `---` but no
    standalone `---` line in the first 10 lines must pass through to the
    "no frontmatter" path. Routing-log dedup (FR-003) is the safety net
    for any malformations this lets through.
    """
    text = "Meeting --- followups\n\nDate: 2026-05-12\nAttendees: Kent\nMore body.\n"
    assert _detect_malformation(text) is None


# ---------- _has_parse_error_marker ----------


def test_has_marker_detects_marker_after_frontmatter():
    text = (
        "---\n"
        "date: 2026-05-12\n"
        "status: unprocessed\n"
        "---\n"
        "\n"
        "> [!error] felix-capture: could not parse frontmatter on 2026-05-12. See issue #999.\n"
        "\n"
        "Body content\n"
    )
    assert _has_parse_error_marker(text) is True


def test_has_marker_returns_false_when_absent():
    text = (
        "---\n"
        "date: 2026-05-12\n"
        "status: unprocessed\n"
        "---\n"
        "\n"
        "Just body content, no marker.\n"
    )
    assert _has_parse_error_marker(text) is False


def test_has_marker_ignores_other_callouts():
    """Only `> [!error] felix-capture:` is the felix-capture marker.
    Other callouts (like `> [!note] ...`) must not be stripped.
    """
    text = (
        "---\nstatus: unprocessed\n---\n"
        "\n"
        "> [!warning] something else\n"
        "\n"
        "body\n"
    )
    assert _has_parse_error_marker(text) is False


def test_has_marker_detects_in_no_frontmatter_file():
    """If the file has no frontmatter, the marker can be at the top."""
    text = (
        "> [!error] felix-capture: could not parse frontmatter on 2026-05-12. See issue #1.\n"
        "\n"
        "Body content for a note with no frontmatter.\n"
    )
    assert _has_parse_error_marker(text) is True


# ---------- classify_file ----------


def test_classify_well_formed_unprocessed_regression():
    result = classify_file(FIXTURES / "inbox-well-formed.md", NOW)
    assert result.classification == "unprocessed"
    assert result.parse_failure_reason is None


def test_classify_leading_blank_line_unprocessed_regression():
    """Mission-027 regression — single leading blank line classifies as
    `unprocessed`, NOT `parse-failure`. Critical regression test for #185.
    """
    result = classify_file(FIXTURES / "inbox-leading-blank-lines.md", NOW)
    assert result.classification == "unprocessed"
    assert result.parse_failure_reason is None


def test_classify_utf8_bom_parse_failure():
    result = classify_file(FIXTURES / "inbox-utf8-bom.md", NOW)
    assert result.classification == "parse-failure"
    assert "BOM" in (result.parse_failure_reason or "")


def test_classify_missing_close_fence_parse_failure():
    result = classify_file(FIXTURES / "inbox-missing-close-fence.md", NOW)
    assert result.classification == "parse-failure"
    assert "missing closing" in (result.parse_failure_reason or "")


def test_classify_invalid_yaml_parse_failure():
    result = classify_file(FIXTURES / "inbox-invalid-yaml.md", NOW)
    assert result.classification == "parse-failure"
    assert "invalid YAML" in (result.parse_failure_reason or "")


def test_classify_already_processed_regression():
    result = classify_file(FIXTURES / "inbox-already-processed.md", NOW)
    assert result.classification in {"processed-recent", "processed-stale"}
    assert result.parse_failure_reason is None


def test_classify_no_frontmatter_unprocessed_regression():
    """No frontmatter at all is unprocessed, NOT parse-failure."""
    result = classify_file(FIXTURES / "inbox-no-frontmatter.md", NOW)
    assert result.classification == "unknown-treated-as-unprocessed"
    assert result.parse_failure_reason is None


# ---------- run_prescan integration (dedup filter + JSON output shape) ----------


def _seed_routing_log(log_path: Path, filename: str, issue_number: int = 999):
    """Helper: write a single-line routing log so dedup can find filename."""
    writer = RoutingLogWriter(log_path)
    writer.append(filename=filename, issue_number=issue_number)


def _run_prescan_against(
    inbox_dir: Path, processed_dir: Path, routing_log_path: Path, monkeypatch
):
    """Run prescan's run_prescan() with paths overridden via env + monkeypatch.

    Returns the PrescanResult dict (as parsed from stdout).
    """
    import json
    import io
    import sys

    import prescan as p

    # Build a fake registry that resolve_registry() will load via PRESCAN_REGISTRY_PATH.
    registry = inbox_dir.parent / "registry.json"
    registry.write_text(
        json.dumps(
            {"paths": {"inbox": str(inbox_dir), "inbox_processed": str(processed_dir)}}
        )
    )
    monkeypatch.setenv("PRESCAN_REGISTRY_PATH", str(registry))
    log_dir = inbox_dir.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PRESCAN_LOG_DIR", str(log_dir))

    # Override the routing log location.
    monkeypatch.setattr(
        "routing_log.DEFAULT_ROUTING_LOG_PATH", routing_log_path
    )

    # Capture stdout.
    captured = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured)
    rc = p.run_prescan()
    sys.stdout = sys.__stdout__  # restore for assertion output
    assert rc == 0, f"run_prescan returned {rc}"
    output = captured.getvalue().strip().splitlines()[-1]
    return json.loads(output)


def test_unprocessed_note_with_logged_filename_still_reprocessed(
    tmp_path: Path, monkeypatch
):
    """D9 dedup shift (#746): the note-level routing-log filename dedup is REMOVED.

    Previously an ``unprocessed`` note whose filename appeared in the routing
    log was filtered OUT of ``unprocessed_paths`` and recorded in
    ``dedup_skipped``. Under the D9 state machine a note is treated as done by
    its terminal *status* (``processed``/``needs-review``), NOT by routing-log
    filename presence — per-block idempotency now lives in finalize's block
    keys. An ``unprocessed`` note whose blocks are mid-flight (e.g. one block
    logged on a prior failed tick) MUST therefore still be handed to the agent
    so finalize can reconcile the remaining blocks. This test pins the NEW
    contract: such a note STAYS in ``unprocessed_paths`` and ``dedup_skipped``
    is empty.
    """
    inbox = tmp_path / "inbox"
    processed = tmp_path / "processed"
    inbox.mkdir()
    processed.mkdir()

    # Stage a well-formed unprocessed note.
    note_name = "well-formed-test.md"
    (inbox / note_name).write_text(
        "---\nstatus: unprocessed\n---\n\nBody.\n", encoding="utf-8"
    )

    # Seed the routing log so the filename is already present (a prior partial
    # route). Under D9 this must NOT strand the note.
    log = tmp_path / "routing.jsonl"
    _seed_routing_log(log, note_name, issue_number=42)

    result = _run_prescan_against(inbox, processed, log, monkeypatch)

    # NEW: the note is still handed to the agent for reconciliation.
    assert any(note_name in p for p in result["unprocessed_paths"])
    # NEW: the note-level dedup filter is gone → nothing skipped by filename.
    assert result["dedup_skipped"] == []


def test_dedup_filter_passes_through_when_log_empty(tmp_path: Path, monkeypatch):
    inbox = tmp_path / "inbox"
    processed = tmp_path / "processed"
    inbox.mkdir()
    processed.mkdir()
    note_name = "fresh.md"
    (inbox / note_name).write_text(
        "---\nstatus: unprocessed\n---\n\nBody.\n", encoding="utf-8"
    )
    log = tmp_path / "routing.jsonl"  # never created

    result = _run_prescan_against(inbox, processed, log, monkeypatch)

    assert any(note_name in p for p in result["unprocessed_paths"])
    assert result["dedup_skipped"] == []


def test_parse_failures_field_populated(tmp_path: Path, monkeypatch):
    inbox = tmp_path / "inbox"
    processed = tmp_path / "processed"
    inbox.mkdir()
    processed.mkdir()
    # One BOM-poisoned file → parse_failure.
    (inbox / "bom.md").write_bytes(
        "﻿---\nstatus: unprocessed\n---\n\nBody.\n".encode("utf-8")
    )
    # One well-formed → unprocessed.
    (inbox / "good.md").write_text(
        "---\nstatus: unprocessed\n---\n\nBody.\n", encoding="utf-8"
    )
    log = tmp_path / "routing.jsonl"

    result = _run_prescan_against(inbox, processed, log, monkeypatch)

    assert len(result["parse_failures"]) == 1
    pf = result["parse_failures"][0]
    assert "bom.md" in pf["path"]
    assert "BOM" in pf["reason"]
    # Well-formed still routes.
    assert any("good.md" in p for p in result["unprocessed_paths"])


def test_marker_cleanup_needed_field_populated(tmp_path: Path, monkeypatch):
    inbox = tmp_path / "inbox"
    processed = tmp_path / "processed"
    inbox.mkdir()
    processed.mkdir()
    # Well-formed unprocessed note that ALSO has a stale marker in its body.
    (inbox / "fixed.md").write_text(
        "---\nstatus: unprocessed\n---\n\n"
        "> [!error] felix-capture: could not parse frontmatter on 2026-05-10. See issue #1.\n\n"
        "Body (the file is now well-formed; marker is stale).\n",
        encoding="utf-8",
    )
    log = tmp_path / "routing.jsonl"

    result = _run_prescan_against(inbox, processed, log, monkeypatch)

    assert len(result["marker_cleanup_needed"]) == 1
    assert "fixed.md" in result["marker_cleanup_needed"][0]


def test_marker_cleanup_excludes_archived_stale_files(tmp_path: Path, monkeypatch):
    """Codex WP02 review [P3]: a processed-stale file with a stale marker
    gets archived (moved to processed/), so its inbox path no longer exists.
    It must NOT appear in marker_cleanup_needed — otherwise the downstream
    strip helper would be invoked on a nonexistent path.
    """
    import os
    import time as _time

    inbox = tmp_path / "inbox"
    processed = tmp_path / "processed"
    inbox.mkdir()
    processed.mkdir()
    stale_path = inbox / "old-processed.md"
    stale_path.write_text(
        "---\nstatus: processed\n---\n\n"
        "> [!error] felix-capture: could not parse frontmatter on 2026-01-01. See issue #1.\n\n"
        "Body of a processed note that should get archived.\n",
        encoding="utf-8",
    )
    # Backdate mtime by 365 days so it crosses any STALE_AGE_DAYS threshold.
    old_ts = _time.time() - 365 * 86400
    os.utime(stale_path, (old_ts, old_ts))
    log = tmp_path / "routing.jsonl"

    result = _run_prescan_against(inbox, processed, log, monkeypatch)

    # File should have been archived (moved to processed dir).
    assert result["archived_count"] == 1
    # And it should NOT appear in marker_cleanup_needed because there is
    # no live inbox path for the strip helper to act on.
    assert result["marker_cleanup_needed"] == []
