"""Tests for `scripts/inbox/mark_processed.py` (WP01).

Covers FR-001 (atomic frontmatter mutation), FR-002 (idempotency),
FR-003 (inbox-root validation), FR-004 (fs-error exit 2),
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
import json
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


# ---------- fixtures ----------


@pytest.fixture
def hermetic_vault(tmp_path: Path, monkeypatch):
    """Create a minimal hermetic vault and point PRESCAN_REGISTRY_PATH at it.

    Creates ``tmp_path/01-Inbox/`` and ``tmp_path/02-Inbox-Processed/``,
    writes a ``paths.json`` registry pointing to them, and sets
    ``PRESCAN_REGISTRY_PATH`` so ``resolve_registry()`` uses the hermetic
    dirs instead of the production vault paths (which do not exist on the
    development machine).

    Returns the inbox root (``tmp_path / "01-Inbox"``) so tests can place
    notes in a location that satisfies the inbox-root validation check.
    """
    inbox = tmp_path / "01-Inbox"
    inbox.mkdir()
    inbox_processed = tmp_path / "02-Inbox-Processed"
    inbox_processed.mkdir()
    registry = tmp_path / "paths.json"
    registry.write_text(
        json.dumps(
            {
                "paths": {
                    "inbox": str(inbox),
                    "inbox_processed": str(inbox_processed),
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("PRESCAN_REGISTRY_PATH", str(registry))
    return inbox


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


def test_mark_processed_missing_file_exits_1(
    tmp_path: Path, capsys, hermetic_vault: Path
):
    """--path of nonexistent file inside inbox root → exit 1, structured stderr."""
    missing = hermetic_vault / "does-not-exist.md"

    rc = mark_processed.main(["--path", str(missing)])
    assert rc == 1

    err = capsys.readouterr().err
    assert "error" in err.lower()


def test_mark_processed_no_frontmatter_exits_1(
    tmp_path: Path, capsys, hermetic_vault: Path
):
    """Note file without --- frontmatter block → exit 1."""
    path = hermetic_vault / "no_fm.md"
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
    tmp_path: Path, monkeypatch, capsys
):
    """Mock os.replace to raise → exit 2 + original file unchanged + no temp leftover.

    T005.b (portable exit-2 test): monkeypatching os.replace ensures this
    test exercises the OSError catch in mark_processed() regardless of
    filesystem or user privilege.  Covers CI-as-root environments where
    chmod tricks are bypassed.
    """
    path = tmp_path / "note.md"
    original_text = "---\nstatus: unprocessed\n---\nbody\n"
    path.write_text(original_text, encoding="utf-8")
    original_mtime = path.stat().st_mtime_ns

    def boom(*args, **kwargs):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(mark_processed.os, "replace", boom)

    rc = mark_processed.mark_processed(path)
    assert rc == 2

    err = capsys.readouterr().err
    assert "fs_error" in err

    # Target file content and mtime must be byte-for-byte unchanged.
    assert path.read_text(encoding="utf-8") == original_text
    assert path.stat().st_mtime_ns == original_mtime
    # No stray .tmp sibling left behind.
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


# ---------- T005.a — perm-denied exit-2 (real filesystem, root-skipped) ----------


@pytest.mark.skipif(
    os.geteuid() == 0,
    reason="root bypasses directory mode bits; use T005.b (mocked) on root CI",
)
def test_mark_processed_exit2_perm_denied_parent_dir(
    tmp_path: Path, capsys, hermetic_vault: Path
):
    """Parent dir chmod 0o555 → mkstemp fails → exit 2, note byte-for-byte unchanged.

    T005.a: exercises the real-filesystem permission-denied path without
    monkeypatching.  Placing a note in a read-only subdirectory of the inbox
    prevents ``tempfile.mkstemp`` from creating the temp file (directory
    write permission is required), which triggers the OSError catch and exit 2.

    Note: ``os.chmod(note, 0o444)`` alone does NOT prevent ``os.replace`` on
    macOS/Linux — rename is a directory operation governed by parent-dir
    permissions, not the target file's mode bits.  We therefore chmod the
    PARENT directory to 0o555.
    """
    sub = hermetic_vault / "sub"
    sub.mkdir()
    note = sub / "note.md"
    _write_note(note, "status: unprocessed", "\nbody\n")
    original_bytes = note.read_bytes()

    os.chmod(sub, 0o555)  # read+exec only: mkstemp will fail with PermissionError
    try:
        rc = mark_processed.main(["--path", str(note)])
    finally:
        os.chmod(sub, 0o755)  # restore so pytest tmp cleanup can remove the dir

    assert rc == 2
    err = capsys.readouterr().err
    assert "fs_error" in err
    # Original note must be byte-for-byte unchanged.
    assert note.read_bytes() == original_bytes


# ---------- T005.c — outside inbox root ----------


def test_mark_processed_exit1_outside_inbox_root(
    tmp_path: Path, capsys, hermetic_vault: Path
):
    """Path outside the hermetic inbox root → exit 1 + outside_inbox_root JSON.

    T005.c: validates that the inbox-root check (T001/FR-003) fires correctly.
    The note is created directly in ``tmp_path`` (parent of ``01-Inbox/``),
    which is outside the hermetic inbox root returned by ``resolve_registry()``.
    """
    outside = tmp_path / "note_outside.md"
    _write_note(outside, "status: unprocessed", "\nbody\n")

    rc = mark_processed.main(["--path", str(outside)])

    assert rc == 1
    err = capsys.readouterr().err
    assert "outside_inbox_root" in err


def test_mark_processed_symlink_note_finalizes_real_target(
    tmp_path: Path, capsys, hermetic_vault: Path
):
    """A symlinked note path finalizes the REAL target, not the symlink.

    Regression (Codex adversarial review): previously ``main()`` validated the
    resolved target but called ``mark_processed(Path(args.path))`` with the raw
    symlink path, so ``os.replace()`` replaced the symlink itself — leaving the
    real target ``status: unprocessed`` while the helper exited 0 with success
    JSON. That re-introduced the silent-failure class this WP exists to close.
    """
    inbox = hermetic_vault
    target = inbox / "real.md"
    _write_note(target, "status: unprocessed", "\nbody\n")
    link = inbox / "link.md"
    link.symlink_to(target)

    rc = mark_processed.main(["--path", str(link)])

    assert rc == 0
    # The REAL target is finalized; the symlink stays a symlink (not replaced).
    assert "status: processed" in target.read_text(encoding="utf-8")
    assert link.is_symlink()
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["finalized"] is True
    assert payload["already_processed"] is False
    assert payload["file_final_path"] == str(target.resolve())


def test_mark_processed_inbox_root_spelling_mismatch(
    tmp_path: Path, capsys, monkeypatch
):
    """A legitimate in-root note finalizes even when the registry inbox path and
    the resolved note path differ in spelling (symlinked vault dir).

    Regression (Codex adversarial review): ``inbox_root`` from
    ``resolve_registry()`` is unresolved (``Path(paths["inbox"])``); comparing it
    against a resolved candidate yielded a false ``outside_inbox_root`` (the
    macOS ``/var`` vs ``/private/var`` hazard, reproduced portably here with an
    explicit symlinked vault dir).
    """
    real = tmp_path / "real_vault"
    (real / "01-Inbox").mkdir(parents=True)
    (real / "02-Inbox-Processed").mkdir()
    link_vault = tmp_path / "link_vault"
    link_vault.symlink_to(real)  # a different spelling of the same directory
    registry = tmp_path / "paths.json"
    registry.write_text(
        json.dumps(
            {
                "paths": {
                    "inbox": str(link_vault / "01-Inbox"),
                    "inbox_processed": str(link_vault / "02-Inbox-Processed"),
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("PRESCAN_REGISTRY_PATH", str(registry))

    # The note is accessed via the REAL (resolved) spelling of the path.
    note = real / "01-Inbox" / "note.md"
    _write_note(note, "status: unprocessed", "\nbody\n")

    rc = mark_processed.main(["--path", str(note)])

    assert rc == 0  # NOT a false outside_inbox_root
    assert "status: processed" in note.read_text(encoding="utf-8")


# ---------- T005.d — stdout JSON on happy path and idempotent re-run ----------


def test_mark_processed_stdout_json_happy_and_idempotent(
    tmp_path: Path, capsys, hermetic_vault: Path
):
    """Happy path → single-line stdout JSON; idempotent re-run → already_processed=true.

    T005.d: validates the FR-002 stdout contract introduced in T003.
    Checks that stdout is exactly one parseable JSON line, that stdout
    carries no other content, and that the idempotent re-run correctly
    reflects already_processed=true.
    """
    note = hermetic_vault / "note.md"
    _write_note(note, "status: unprocessed", "\nbody\n")

    # --- First run: real write ---
    rc = mark_processed.main(["--path", str(note)])
    assert rc == 0
    captured = capsys.readouterr()
    out_lines = [line for line in captured.out.splitlines() if line.strip()]
    assert len(out_lines) == 1, f"expected exactly 1 stdout line, got: {captured.out!r}"
    data = json.loads(out_lines[0])
    assert data["finalized"] is True
    assert data["already_processed"] is False
    assert data["status"] == "processed"
    assert data["file_final_path"] == str(note.resolve())

    # --- Second run: idempotent no-op ---
    rc2 = mark_processed.main(["--path", str(note)])
    assert rc2 == 0
    captured2 = capsys.readouterr()
    out_lines2 = [line for line in captured2.out.splitlines() if line.strip()]
    assert len(out_lines2) == 1, f"expected exactly 1 stdout line, got: {captured2.out!r}"
    data2 = json.loads(out_lines2[0])
    assert data2["finalized"] is True
    assert data2["already_processed"] is True
    assert data2["status"] == "processed"
    assert data2["file_final_path"] == str(note.resolve())


# ---------- read_frontmatter unit tests ----------


def test_read_frontmatter_parses_simple_kv(tmp_path: Path):
    text = "---\nstatus: unprocessed\nid: abc\n---\nbody\n"
    fm, body, leading = mark_processed.read_frontmatter(text)
    assert fm["status"] == "unprocessed"
    assert fm["id"] == "abc"
    assert body == "body\n"
    assert leading == 0


def test_read_frontmatter_no_opening_fence_raises():
    with pytest.raises(ValueError):
        mark_processed.read_frontmatter("no fence here\n")


def test_read_frontmatter_no_closing_fence_raises():
    with pytest.raises(ValueError):
        mark_processed.read_frontmatter("---\nstatus: unprocessed\nbody without close\n")


def test_read_frontmatter_preserves_key_order(tmp_path: Path):
    text = "---\nid: 1\nstatus: x\ncreated: 2026-01-01\ntags: a\n---\nbody"
    fm, _, _ = mark_processed.read_frontmatter(text)
    assert list(fm.keys()) == ["id", "status", "created", "tags"]


def test_read_frontmatter_tolerates_leading_blank_line():
    """Production inbox files from Obsidian Templater + Wispr Flow have a
    leading blank line above the opening fence. prescan.classify_file already
    accepts this shape; mark_processed must too. Real production failure
    observed during #568 triage on `Inbox 2026-06-06 0127.md` and similar
    (silent capture-tick regression discovered in the post-#566-merge archive).
    """
    text = "\n---\ndate: 2026-06-06\ntime: 01:27\ntype: inbox\nstatus: unprocessed\n---\nbody\n"
    fm, body, leading = mark_processed.read_frontmatter(text)
    assert fm["status"] == "unprocessed"
    assert fm["date"] == "2026-06-06"
    assert body == "body\n"
    assert leading == 1


def test_read_frontmatter_tolerates_multiple_leading_blank_lines():
    """Defensive: any number of leading blank lines before the fence is OK."""
    text = "\n\n\n---\nstatus: unprocessed\n---\nbody\n"
    _, _, leading = mark_processed.read_frontmatter(text)
    assert leading == 3


def test_read_frontmatter_blank_only_file_raises():
    """A file with only whitespace and no fence still raises (no fence found)."""
    with pytest.raises(ValueError):
        mark_processed.read_frontmatter("\n\n\n")


def test_mark_processed_e2e_with_leading_blank_line_inbox_file(tmp_path: Path):
    """E2E: a templated inbox file with leading blank line is fully processable.

    Regression guard for the bug found in #568 triage. Before the fix, mark_processed
    exited 1 with no_frontmatter on real production inbox notes. After the fix,
    the helper round-trips the file (preserving the leading blank line + body)
    and sets status:processed + processed_at.
    """
    p = tmp_path / "Inbox 2026-06-06 0127.md"
    p.write_text(
        "\n---\ndate: 2026-06-06\ntime: 01:27\ntype: inbox\nstatus: unprocessed\n---\n"
        "This is a test file to see if ob is syncing on office2.\n",
        encoding="utf-8",
    )
    rc = mark_processed.mark_processed(p)
    assert rc == 0
    out = p.read_text(encoding="utf-8")
    assert out.startswith("\n---\n"), "leading blank line preserved"
    assert "status: processed" in out
    assert "status: unprocessed" not in out
    assert "processed_at:" in out
    assert "This is a test file to see if ob is syncing on office2." in out


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


def test_mark_processed_dispatcher_returns_main_exit_code(
    tmp_path: Path, hermetic_vault: Path
):
    """main() routes to mark_processed() and returns its exit code.

    Note inside the hermetic inbox root so inbox-root validation passes.
    """
    path = hermetic_vault / "note.md"
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
