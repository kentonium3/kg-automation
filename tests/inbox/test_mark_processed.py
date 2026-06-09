"""Tests for `scripts/inbox/mark_processed.py` (WP01).

Covers FR-001 (atomic frontmatter mutation), FR-002 (idempotency),
FR-008 (--help), FR-009 (structured stderr on failure), FR-010 (atomic
write), and C-001 (private-path refusal).

Invocation form under test: `python3 -m scripts.inbox.mark_processed`
(NFR-004 / [[feedback_helper_m_invocation_form]]).

The conftest.py adds `scripts/inbox/` to sys.path so the helper can be
imported as `mark_processed` directly; the `-m` form is exercised via a
dedicated subprocess smoke test below.
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

# Make the repo root importable so coverage can map the helper to the
# canonical `scripts.inbox.mark_processed` dotted name. The conftest in
# tests/inbox/ already puts scripts/inbox/ on sys.path (for `import
# mark_processed`) — we add the repo root too so the `scripts.inbox.*`
# package form resolves and pytest --cov=scripts.inbox.mark_processed
# (per WP01's prescribed command) records data.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.inbox import mark_processed  # noqa: E402


# ---------- helpers ----------


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _stray_tmp_files(directory: Path) -> list[Path]:
    """Return any leftover `.tmp` siblings the atomic-write should have cleaned."""
    return [
        p
        for p in directory.iterdir()
        if ".tmp" in p.name and p.name != "note.md"
    ]


def _write_note(path: Path, frontmatter: str, body: str) -> None:
    """Write a note file with the given frontmatter and body."""
    path.write_text(f"---\n{frontmatter}\n---\n{body}", encoding="utf-8")


# ---------- behavior tests ----------


def test_mark_processed_sets_status_and_timestamp(tmp_path: Path):
    """Unprocessed note → frontmatter has status: processed + processed_at."""
    path = tmp_path / "note.md"
    body = "\nThe body text.\n"
    _write_note(path, "status: unprocessed", body)

    rc = mark_processed.mark_processed(path)
    assert rc == 0

    text = path.read_text(encoding="utf-8")
    assert "status: processed" in text
    assert re.search(r"processed_at: \S+Z", text)
    # Body preserved verbatim (including leading newline after frontmatter close).
    assert text.endswith(body)


def test_mark_processed_idempotent(tmp_path: Path):
    """Note already at status: processed → no-op, exit 0, file unchanged."""
    path = tmp_path / "note.md"
    _write_note(
        path,
        "status: processed\nprocessed_at: 2026-06-08T12:00:00Z",
        "\nbody\n",
    )
    before_md5 = _md5(path)

    rc = mark_processed.mark_processed(path)
    assert rc == 0
    assert _md5(path) == before_md5


def test_mark_processed_preserves_other_frontmatter(tmp_path: Path):
    """Extra frontmatter fields (id, created, tags) all preserved."""
    path = tmp_path / "note.md"
    _write_note(
        path,
        "id: abc123\ncreated: 2026-06-01\nstatus: unprocessed\ntags: [inbox, mobile]",
        "\nThe body.\n",
    )

    rc = mark_processed.mark_processed(path)
    assert rc == 0

    text = path.read_text(encoding="utf-8")
    assert "id: abc123" in text
    assert "created: 2026-06-01" in text
    assert "tags: [inbox, mobile]" in text
    assert "status: processed" in text
    assert "status: unprocessed" not in text


def test_mark_processed_preserves_body(tmp_path: Path):
    """Multi-paragraph body with markdown features preserved byte-for-byte."""
    body = (
        "\n# Heading One\n\n"
        "Paragraph one with **bold** and _italic_.\n\n"
        "```python\nprint('code block')\n```\n\n"
        "> [!info] An Obsidian callout\n"
        "> with two lines.\n\n"
        "- list item one\n"
        "- list item two\n"
    )
    path = tmp_path / "note.md"
    _write_note(path, "status: unprocessed", body)

    rc = mark_processed.mark_processed(path)
    assert rc == 0

    text = path.read_text(encoding="utf-8")
    # Body must appear exactly as written.
    assert text.endswith(body), f"body changed: trailing={text[-200:]!r}"


def test_mark_processed_missing_file_exits_1(tmp_path: Path, capsys):
    """--path of nonexistent file → exit 1, structured stderr."""
    missing = tmp_path / "does-not-exist.md"

    rc = mark_processed.main(["--path", str(missing)])
    assert rc == 1

    err = capsys.readouterr().err
    assert "error" in err.lower()


def test_mark_processed_no_frontmatter_exits_1(tmp_path: Path, capsys):
    """Note file without --- frontmatter block → exit 1."""
    path = tmp_path / "no_fm.md"
    path.write_text("Just a body line.\nNo frontmatter here.\n", encoding="utf-8")

    rc = mark_processed.main(["--path", str(path)])
    assert rc == 1

    err = capsys.readouterr().err
    assert "frontmatter" in err.lower() or "error" in err.lower()


def test_mark_processed_atomic_no_temp_leftover_on_success(tmp_path: Path):
    """Successful invocation → no stray .tmp file lingers."""
    path = tmp_path / "note.md"
    _write_note(path, "status: unprocessed", "\nbody\n")

    rc = mark_processed.mark_processed(path)
    assert rc == 0
    assert _stray_tmp_files(tmp_path) == []


def test_mark_processed_atomic_no_destination_corruption_on_failure(
    tmp_path: Path, monkeypatch
):
    """Mock os.replace to raise → original file unchanged + no temp leftover."""
    path = tmp_path / "note.md"
    original_text = "---\nstatus: unprocessed\n---\nbody\n"
    path.write_text(original_text, encoding="utf-8")
    original_mtime = path.stat().st_mtime_ns

    def boom(*args, **kwargs):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(mark_processed.os, "replace", boom)

    with pytest.raises(OSError, match="simulated replace failure"):
        mark_processed.mark_processed(path)

    # Target file untouched.
    assert path.read_text(encoding="utf-8") == original_text
    assert path.stat().st_mtime_ns == original_mtime
    # No stray .tmp sibling.
    assert _stray_tmp_files(tmp_path) == []


def test_mark_processed_refuses_private_path(tmp_path: Path, capsys):
    """--path under 04-Growth/_private/ → exit 3 (C-001 refusal)."""
    # We don't actually create the file — the refusal MUST happen before
    # any disk read (per WP01 spec: refusal check BEFORE any read).
    private = tmp_path / "04-Growth" / "_private" / "secret.md"

    rc = mark_processed.main(["--path", str(private)])
    assert rc == 3

    err = capsys.readouterr().err
    assert "refus" in err.lower() or "private" in err.lower()


def test_mark_processed_processed_at_iso_8601_utc(tmp_path: Path):
    """processed_at ends with `Z` and is fromisoformat-parseable."""
    from datetime import datetime

    path = tmp_path / "note.md"
    _write_note(path, "status: unprocessed", "\nbody\n")

    rc = mark_processed.mark_processed(path)
    assert rc == 0

    text = path.read_text(encoding="utf-8")
    match = re.search(r"processed_at: (\S+)", text)
    assert match is not None
    timestamp = match.group(1)
    assert timestamp.endswith("Z")
    # Python's fromisoformat accepts +00:00 form; we round-trip via replace.
    parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None


# ---------- read_frontmatter unit tests ----------


def test_read_frontmatter_parses_simple_kv(tmp_path: Path):
    text = "---\nstatus: unprocessed\nid: abc\n---\nbody\n"
    fm, body = mark_processed.read_frontmatter(text)
    assert fm["status"] == "unprocessed"
    assert fm["id"] == "abc"
    assert body == "body\n"


def test_read_frontmatter_no_opening_fence_raises():
    with pytest.raises(ValueError):
        mark_processed.read_frontmatter("no fence here\n")


def test_read_frontmatter_no_closing_fence_raises():
    with pytest.raises(ValueError):
        mark_processed.read_frontmatter("---\nstatus: unprocessed\nbody without close\n")


def test_read_frontmatter_preserves_key_order(tmp_path: Path):
    text = "---\nid: 1\nstatus: x\ncreated: 2026-01-01\ntags: a\n---\nbody"
    fm, _ = mark_processed.read_frontmatter(text)
    assert list(fm.keys()) == ["id", "status", "created", "tags"]


# ---------- write_frontmatter unit tests ----------


def test_write_frontmatter_round_trip(tmp_path: Path):
    fm = {"id": "abc", "status": "processed", "processed_at": "2026-06-08T12:00:00Z"}
    body = "Body text\n"
    text = mark_processed.write_frontmatter(fm, body)
    assert text.startswith("---\n")
    assert "id: abc" in text
    assert "status: processed" in text
    assert "processed_at: 2026-06-08T12:00:00Z" in text
    assert text.endswith(body)


# ---------- CLI surface tests ----------


def test_mark_processed_help_exits_0(capsys):
    """--help exits 0 with usage text (FR-008)."""
    with pytest.raises(SystemExit) as exc_info:
        mark_processed.main(["--help"])
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "usage" in out.lower() or "--path" in out


def test_mark_processed_dispatcher_returns_main_exit_code(tmp_path: Path):
    """main() routes to mark_processed() and returns its exit code."""
    path = tmp_path / "note.md"
    _write_note(path, "status: unprocessed", "\nbody\n")
    rc = mark_processed.main(["--path", str(path)])
    assert rc == 0
    assert "status: processed" in path.read_text(encoding="utf-8")


# ---------- subprocess smoke for -m invocation form (NFR-004) ----------


def test_mark_processed_m_invocation_form(tmp_path: Path):
    """`python3 -m scripts.inbox.mark_processed --help` succeeds from repo root.

    NFR-004: -m form is mandatory; script-path form forbidden. This smoke
    asserts the module is importable in -m form (the form that has bitten
    us twice in production).
    """
    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "-m", "scripts.inbox.mark_processed", "--help"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "--path" in result.stdout
