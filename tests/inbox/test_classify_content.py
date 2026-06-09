"""Tests for scripts/inbox/classify_content.py (WP06).

Drives the helper end-to-end via ``python3 -m scripts.inbox.classify_content``
per [[feedback_helper_m_invocation_form]] — script-path form is forbidden
and has caused two production failures. The ``--help`` and missing-file
smoke tests use the real ``-m`` subprocess invocation; per-block
classification tests call ``main()`` in-process so coverage tooling can
instrument the branches.

Coverage targets (per NFR-003): >=90% line, >=85% branch.

Covered:
  - One test per block kind for clear high-confidence cases (7 tests)
  - Ambiguous fallback cases (3 tests)
  - Boundary heuristics (3 tests)
  - Multi-block notes (2 tests)
  - Output JSON shape (3 tests)
  - Private-path refusal per C-001 (1 test)
  - Missing-file handling (1 test)
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from scripts.inbox import classify_content


REPO_ROOT = Path(__file__).resolve().parents[2]


class HelperResult:
    """Subprocess-like return value for the in-process helper invocation."""

    def __init__(self, returncode: int, stdout: str, stderr: str) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _run_helper(content_file: Path, *extra: str) -> HelperResult:
    """Invoke ``classify_content.main`` in-process and capture stdio.

    Using in-process invocation keeps coverage instrumentation alive
    (subprocess-based runs report 0% because the tracer isn't propagated).
    The ``-m`` subprocess form is exercised separately by
    ``test_m_invocation_form_works`` to honor
    [[feedback_helper_m_invocation_form]].
    """
    argv = ["--content-file", str(content_file), *extra]
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
        rc = classify_content.main(argv)
    return HelperResult(rc, stdout_buf.getvalue(), stderr_buf.getvalue())


def _write_note(tmp_path: Path, name: str, body: str, *, frontmatter: bool = True) -> Path:
    """Write a synthetic inbox note for classification."""
    path = tmp_path / name
    if frontmatter:
        text = (
            "---\n"
            "id: test-note\n"
            "doc_type: inbox\n"
            "status: pending\n"
            "---\n"
            f"{body}"
        )
    else:
        text = body
    path.write_text(text, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------


def test_help_exits_zero() -> None:
    """FR-008: every helper supports --help."""
    cmd = [sys.executable, "-m", "scripts.inbox.classify_content", "--help"]
    result = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
    assert result.returncode == 0
    assert "classify" in result.stdout.lower() or "content-file" in result.stdout


def test_m_invocation_form_works(tmp_path: Path) -> None:
    """NFR-004: the canonical ``python3 -m scripts.inbox.classify_content``
    form must produce valid JSON output. Subprocess invocation guards against
    the ``ModuleNotFoundError`` class that bit production twice
    (see [[feedback_helper_m_invocation_form]]).
    """
    note = _write_note(tmp_path, "Inbox.md", "Today I feel productive.")
    cmd = [
        sys.executable,
        "-m",
        "scripts.inbox.classify_content",
        "--content-file",
        str(note),
    ]
    result = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert "blocks" in out


def test_missing_content_file_exits_1(tmp_path: Path) -> None:
    """Missing input file is a validation error (exit 1)."""
    missing = tmp_path / "does_not_exist.md"
    result = _run_helper(missing)
    assert result.returncode == 1
    # Stderr should be structured JSON.
    err = json.loads(result.stderr.strip().splitlines()[-1])
    assert err["error"] in {"file_not_found", "invalid_input"}


def test_non_regular_file_exits_1(tmp_path: Path) -> None:
    """A directory path (non-regular file) is a validation error."""
    dir_path = tmp_path / "a_directory"
    dir_path.mkdir()
    result = _run_helper(dir_path)
    assert result.returncode == 1
    err = json.loads(result.stderr.strip().splitlines()[-1])
    assert err["error"] == "invalid_input"


def test_private_path_input_exits_3(tmp_path: Path) -> None:
    """C-001: refuse any path under ``04-Growth/_private/``."""
    private_dir = tmp_path / "second-brain" / "notes" / "04-Growth" / "_private"
    private_dir.mkdir(parents=True)
    note = _write_note(private_dir, "secret.md", "Anything.")
    result = _run_helper(note)
    assert result.returncode == 3
    err = json.loads(result.stderr.strip().splitlines()[-1])
    assert err["error"] == "private_path_refused"


# ---------------------------------------------------------------------------
# Per-kind high-confidence classification (7 tests)
# ---------------------------------------------------------------------------


def test_journal_with_reflective_keywords_high_confidence(tmp_path: Path) -> None:
    """First-person reflective language → journal kind."""
    note = _write_note(
        tmp_path,
        "Inbox 2026-06-08 0732.md",
        "Today I noticed that I feel a lot less anxious about the deploy pipeline. "
        "Reflecting on the past few weeks, the helper extraction has paid off.",
    )
    result = _run_helper(note)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert any(b["kind"] == "journal" and b["confidence"] == "high" for b in out["blocks"])


def test_calendar_with_weekday_time_high_confidence(tmp_path: Path) -> None:
    """``<weekday> at <time>`` is a calendar signal."""
    note = _write_note(
        tmp_path,
        "Inbox 2026-06-08 0801.md",
        "Meet with Rob Thursday at 3pm to review the metalbox prototype.",
    )
    result = _run_helper(note)
    assert result.returncode == 0
    out = json.loads(result.stdout)
    assert any(b["kind"] == "calendar" and b["confidence"] == "high" for b in out["blocks"])


def test_calendar_with_explicit_date_high_confidence(tmp_path: Path) -> None:
    """Explicit MM/DD date + verb signals calendar."""
    note = _write_note(
        tmp_path,
        "Inbox 2026-06-08 0802.md",
        "Lunch with Sarah 06/15 at noon downtown.",
    )
    result = _run_helper(note)
    assert result.returncode == 0
    out = json.loads(result.stdout)
    assert any(b["kind"] == "calendar" and b["confidence"] == "high" for b in out["blocks"])


def test_someday_with_aspirational_keywords_high_confidence(tmp_path: Path) -> None:
    """Aspirational keywords (someday / would like to) → someday kind."""
    note = _write_note(
        tmp_path,
        "Inbox 2026-06-08 0803.md",
        "Someday I would like to take a sabbatical and learn woodworking properly.",
    )
    result = _run_helper(note)
    assert result.returncode == 0
    out = json.loads(result.stdout)
    assert any(b["kind"] == "someday" and b["confidence"] == "high" for b in out["blocks"])


def test_github_issue_with_explicit_marker(tmp_path: Path) -> None:
    """Markers like ``gh issue:`` / ``bug:`` → github_issue."""
    note = _write_note(
        tmp_path,
        "Inbox 2026-06-08 0804.md",
        "gh issue: classify_content should refuse private paths under 04-Growth.",
    )
    result = _run_helper(note)
    assert result.returncode == 0
    out = json.loads(result.stdout)
    assert any(b["kind"] == "github_issue" and b["confidence"] == "high" for b in out["blocks"])


def test_vikunja_task_with_todo_marker(tmp_path: Path) -> None:
    """TODO / [ ] / task: markers → vikunja_task."""
    note = _write_note(
        tmp_path,
        "Inbox 2026-06-08 0805.md",
        "TODO: rotate the office2 GitHub PAT before it expires.",
    )
    result = _run_helper(note)
    assert result.returncode == 0
    out = json.loads(result.stdout)
    assert any(b["kind"] == "vikunja_task" and b["confidence"] == "high" for b in out["blocks"])


def test_parse_failure_with_callout_marker(tmp_path: Path) -> None:
    """The felix-capture parse-error callout signals parse_failure."""
    note = _write_note(
        tmp_path,
        "Inbox 2026-06-08 0806.md",
        "> [!error] felix-capture: could not parse frontmatter on 2026-06-08.\n"
        "> See issue #999.",
    )
    result = _run_helper(note)
    assert result.returncode == 0
    out = json.loads(result.stdout)
    assert any(b["kind"] == "parse_failure" and b["confidence"] == "high" for b in out["blocks"])


# ---------------------------------------------------------------------------
# Ambiguous cases (3 tests)
# ---------------------------------------------------------------------------


def test_block_without_clear_signals_ambiguous(tmp_path: Path) -> None:
    """Generic text with no per-kind signals → ambiguous + flag."""
    note = _write_note(
        tmp_path,
        "Inbox 2026-06-08 0807.md",
        "The roof is red and quiet.",
    )
    result = _run_helper(note)
    assert result.returncode == 0
    out = json.loads(result.stdout)
    amb = [b for b in out["blocks"] if b["kind"] == "ambiguous"]
    assert len(amb) >= 1
    assert all(b["confidence"] == "low" for b in amb)
    assert all(b.get("flag") == "needs-llm-disambiguation" for b in amb)


def test_mixed_signals_ambiguous(tmp_path: Path) -> None:
    """When a block matches multiple kinds → ambiguous."""
    note = _write_note(
        tmp_path,
        "Inbox 2026-06-08 0808.md",
        # Calendar signal (meet Thursday) + someday signal (would like to)
        "Meet Thursday at 3pm — would like to maybe explore the metalbox concept someday.",
    )
    result = _run_helper(note)
    assert result.returncode == 0
    out = json.loads(result.stdout)
    # Either explicitly ambiguous OR confidence dropped to medium/low due to mixed signals.
    blocks = out["blocks"]
    assert any(
        b["kind"] == "ambiguous" or b["confidence"] in {"low", "medium"} for b in blocks
    )


def test_short_block_low_confidence(tmp_path: Path) -> None:
    """Very short blocks default to ambiguous (insufficient signal)."""
    note = _write_note(tmp_path, "Inbox 2026-06-08 0809.md", "Hmm.")
    result = _run_helper(note)
    assert result.returncode == 0
    out = json.loads(result.stdout)
    assert any(b["kind"] == "ambiguous" for b in out["blocks"])


# ---------------------------------------------------------------------------
# Boundary heuristics (3 tests)
# ---------------------------------------------------------------------------


def test_h1_heading_starts_new_block(tmp_path: Path) -> None:
    """Markdown heading begins a new block per R-003."""
    body = (
        "Today I feel calm and grounded after the long sprint.\n\n"
        "# Calendar\n"
        "Meet with Rob Thursday at 3pm.\n"
    )
    note = _write_note(tmp_path, "Inbox 2026-06-08 0810.md", body)
    result = _run_helper(note)
    assert result.returncode == 0
    out = json.loads(result.stdout)
    assert len(out["blocks"]) >= 2


def test_double_blank_line_starts_new_block(tmp_path: Path) -> None:
    """Two-or-more blank lines split blocks even without a topic-lead
    keyword on the next block — exercises the blank-run boundary
    independent of the topic-lead and heading branches."""
    body = (
        "Today I noticed that the calmness from yoga lingers.\n\n\n"
        "The deploy pipeline kept ticking quietly through the night."
    )
    note = _write_note(tmp_path, "Inbox 2026-06-08 0811.md", body)
    result = _run_helper(note)
    assert result.returncode == 0
    out = json.loads(result.stdout)
    assert len(out["blocks"]) >= 2


def test_topic_keyword_starts_new_block(tmp_path: Path) -> None:
    """A leading topic keyword (TODO:, Calendar:) starts a new block even
    without explicit boundary whitespace."""
    body = (
        "Today I feel calm and grounded.\n"
        "TODO: rotate the office2 PAT.\n"
    )
    note = _write_note(tmp_path, "Inbox 2026-06-08 0812.md", body)
    result = _run_helper(note)
    assert result.returncode == 0
    out = json.loads(result.stdout)
    assert len(out["blocks"]) >= 2


# ---------------------------------------------------------------------------
# Multi-block notes (2 tests)
# ---------------------------------------------------------------------------


def test_multi_block_note_returns_multiple_blocks(tmp_path: Path) -> None:
    """A note with journal + calendar + someday → 3+ blocks."""
    body = (
        "Today I feel optimistic about the helper extraction landing.\n\n"
        "# Calendar\n"
        "Meet Rob Thursday at 3pm.\n\n"
        "# Someday\n"
        "Someday I would like to start a small woodworking shop."
    )
    note = _write_note(tmp_path, "Inbox 2026-06-08 0813.md", body)
    result = _run_helper(note)
    assert result.returncode == 0
    out = json.loads(result.stdout)
    kinds = {b["kind"] for b in out["blocks"]}
    assert "journal" in kinds
    assert "calendar" in kinds
    assert "someday" in kinds


def test_blocks_indexed_in_order(tmp_path: Path) -> None:
    """Block ``index`` is 0-based and sequential."""
    body = (
        "Today I feel calm.\n\n"
        "Meet Thursday at 3pm with the team.\n\n"
        "Someday I would like to write a memoir."
    )
    note = _write_note(tmp_path, "Inbox 2026-06-08 0814.md", body)
    result = _run_helper(note)
    assert result.returncode == 0
    out = json.loads(result.stdout)
    indexes = [b["index"] for b in out["blocks"]]
    assert indexes == list(range(len(indexes)))


# ---------------------------------------------------------------------------
# Output format (3 tests)
# ---------------------------------------------------------------------------


def test_output_is_valid_json(tmp_path: Path) -> None:
    """Stdout is a single JSON object (no trailing junk)."""
    note = _write_note(tmp_path, "Inbox.md", "Today I feel content.")
    result = _run_helper(note)
    assert result.returncode == 0
    out = json.loads(result.stdout)
    assert isinstance(out, dict)
    assert "note_filename" in out
    assert "blocks" in out


def test_note_filename_in_output_matches_input_basename(tmp_path: Path) -> None:
    """``note_filename`` is the basename, never the full path."""
    note = _write_note(tmp_path, "Inbox 2026-06-08 0815.md", "Today I feel rested.")
    result = _run_helper(note)
    assert result.returncode == 0
    out = json.loads(result.stdout)
    assert out["note_filename"] == "Inbox 2026-06-08 0815.md"
    assert "/" not in out["note_filename"]


def test_each_block_has_all_required_fields(tmp_path: Path) -> None:
    """Every Block has index/kind/content/confidence; ambiguous blocks
    additionally carry a ``flag`` per the data model."""
    body = (
        "Today I feel like cooking.\n\n"
        "Quietly the rain continues to fall on the patio.\n"
    )
    note = _write_note(tmp_path, "Inbox.md", body)
    result = _run_helper(note)
    assert result.returncode == 0
    out = json.loads(result.stdout)
    assert out["blocks"], "expected at least one block"
    for block in out["blocks"]:
        assert "index" in block
        assert "kind" in block
        assert "content" in block
        assert "confidence" in block
        if block["kind"] == "ambiguous":
            assert block.get("flag") == "needs-llm-disambiguation"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_body_returns_empty_blocks(tmp_path: Path) -> None:
    """A note with no body (frontmatter only) → empty blocks array."""
    note = _write_note(tmp_path, "Inbox.md", "")
    result = _run_helper(note)
    assert result.returncode == 0
    out = json.loads(result.stdout)
    assert out["blocks"] == []


def test_no_frontmatter_treated_as_body(tmp_path: Path) -> None:
    """A note without ``---`` fences treats the whole file as body."""
    note = _write_note(
        tmp_path, "Inbox.md", "Today I feel grateful for the warm weather.", frontmatter=False
    )
    result = _run_helper(note)
    assert result.returncode == 0
    out = json.loads(result.stdout)
    assert any(b["kind"] == "journal" for b in out["blocks"])


def test_frontmatter_without_close_treated_as_body(tmp_path: Path) -> None:
    """A note that opens ``---`` but never closes it falls back to
    treating the whole text as body (defensive — never raise)."""
    path = tmp_path / "broken.md"
    path.write_text("---\nid: broken\nTODO: rotate the PAT.\n", encoding="utf-8")
    result = _run_helper(path)
    assert result.returncode == 0
    out = json.loads(result.stdout)
    assert out["note_filename"] == "broken.md"


def test_soft_imperative_lead_is_medium_vikunja_task() -> None:
    """A lone imperative verb (no marker, no time anchor) → vikunja_task
    at medium confidence."""
    kind, confidence, flag = classify_content.classify_block("Rotate the office2 PAT before it expires.")
    assert kind == "vikunja_task"
    assert confidence == "medium"
    assert flag is None


def test_classify_block_parse_failure_direct() -> None:
    """Direct call confirms the parse_failure pattern works on the raw
    callout marker (matches case-insensitively)."""
    kind, confidence, flag = classify_content.classify_block(
        "> [!ERROR] felix-capture: bad frontmatter."
    )
    assert kind == "parse_failure"
    assert confidence == "high"
    assert flag is None


def test_split_blocks_empty_returns_empty_list() -> None:
    """Edge case for split_blocks: whitespace-only input → empty list."""
    assert classify_content.split_blocks("") == []
    assert classify_content.split_blocks("   \n\n   \n") == []


def test_read_note_handles_colonless_frontmatter_line(tmp_path: Path) -> None:
    """A frontmatter line without ``:`` is silently skipped (defensive —
    a comment or empty line in the YAML block must not crash the parser)."""
    path = tmp_path / "frontmatter_with_comment.md"
    path.write_text(
        "---\n"
        "id: foo\n"
        "# this is a comment line with no colon-only-marker\n"
        "status: pending\n"
        "---\n"
        "Today I feel good.\n",
        encoding="utf-8",
    )
    fm, body = classify_content.read_note(path)
    assert fm["id"] == "foo"
    assert fm["status"] == "pending"
    assert "Today" in body


def test_read_note_frontmatter_dict() -> None:
    """read_note returns a dict of frontmatter keys plus the body string."""
    import tempfile
    with tempfile.NamedTemporaryFile(
        "w", suffix=".md", delete=False, encoding="utf-8"
    ) as fh:
        fh.write("---\nid: foo\nstatus: pending\n---\nHello world.\n")
        tmp = Path(fh.name)
    try:
        fm, body = classify_content.read_note(tmp)
        assert fm["id"] == "foo"
        assert fm["status"] == "pending"
        assert body.strip() == "Hello world."
    finally:
        tmp.unlink()
