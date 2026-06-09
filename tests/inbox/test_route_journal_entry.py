"""Tests for scripts/inbox/route_journal_entry.py.

Mission: capture-d6-helpers-extraction-01KTMS5Q (WP02)
FRs covered: FR-003 (append to dated journal), FR-010 (atomic write),
FR-011 (path via scripts.vault).

Invocation form under test: ``python3 -m scripts.inbox.route_journal_entry``.
The script-path form (``python3 scripts/inbox/route_journal_entry.py ...``)
is forbidden per ``[[feedback_helper_m_invocation_form]]``; tests exercise
the importable ``main(argv=...)`` entry point so coverage maps to the
``scripts.inbox.route_journal_entry`` module.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Import via the canonical package path so coverage measurement targets
# the ``scripts.inbox.route_journal_entry`` module (matches the
# `python3 -m` invocation form). We add the repo root to sys.path so this
# resolves regardless of how pytest is invoked.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.inbox import route_journal_entry as rje  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_journal_dir(monkeypatch, tmp_path: Path) -> Path:
    """Patch ``scripts.vault.resolver.get_vault_path('journal')`` -> tmp_path.

    Mirrors how production resolves the journal directory through the vault
    registry (FR-011) without writing to ``~/second-brain``.
    """
    journal_dir = tmp_path / "08-Journal"
    journal_dir.mkdir()
    monkeypatch.setattr(rje, "_get_vault_path", lambda name: str(journal_dir))
    return journal_dir


@pytest.fixture
def content_file_factory(tmp_path: Path):
    """Factory: write a content file under tmp_path and return its Path."""

    def _make(text: str, name: str = "content.txt") -> Path:
        p = tmp_path / name
        p.write_text(text, encoding="utf-8")
        return p

    return _make


# ---------------------------------------------------------------------------
# Pure-function tests
# ---------------------------------------------------------------------------


def test_target_filename_formats_correctly():
    dt = datetime(2026, 6, 8, 7, 32, tzinfo=timezone.utc)
    assert rje.target_filename(dt) == "Journal 2026-06-08 0732.md"


def test_target_filename_uses_zero_padded_components():
    dt = datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc)
    assert rje.target_filename(dt) == "Journal 2026-01-02 0304.md"


def test_make_heading_with_long_content_uses_trimmed_excerpt():
    dt = datetime(2026, 6, 8, 7, 32, tzinfo=timezone.utc)
    content = "This is a fairly long journal entry capturing today's thoughts."
    heading = rje.make_heading(dt, content)
    assert heading.startswith("## 07:32 — ")
    excerpt = heading.split("— ", 1)[1]
    assert len(excerpt) <= 60
    assert "This is a fairly long" in excerpt


def test_make_heading_with_short_content_uses_only_timestamp():
    dt = datetime(2026, 6, 8, 7, 32, tzinfo=timezone.utc)
    # Per WP DoD: content <8 chars -> heading is `## HH:mm` only.
    assert rje.make_heading(dt, "tiny") == "## 07:32"


def test_make_heading_strips_leading_whitespace_in_excerpt():
    dt = datetime(2026, 6, 8, 7, 32, tzinfo=timezone.utc)
    content = "   leading whitespace then plenty of body text follows here"
    heading = rje.make_heading(dt, content)
    excerpt = heading.split("— ", 1)[1]
    assert not excerpt.startswith(" ")


def test_make_heading_collapses_internal_newlines():
    dt = datetime(2026, 6, 8, 7, 32, tzinfo=timezone.utc)
    content = "first line\nsecond line that should still be on the heading line"
    heading = rje.make_heading(dt, content)
    # Heading must not contain an embedded newline (Markdown would break).
    assert "\n" not in heading


# ---------------------------------------------------------------------------
# File-creation / append behavior
# ---------------------------------------------------------------------------


def test_creates_journal_file_when_absent(fake_journal_dir, content_file_factory):
    cf = content_file_factory("First entry of the day — feeling productive.")
    rc = rje.main(
        [
            "--content-file",
            str(cf),
            "--datetime",
            "2026-06-08T07:32:00-04:00",
        ]
    )
    assert rc == 0
    target = fake_journal_dir / "Journal 2026-06-08 0732.md"
    assert target.exists()
    text = target.read_text(encoding="utf-8")
    # Frontmatter present and well-formed.
    assert text.startswith("---\n")
    body_start = text.index("---\n", 4) + 4
    frontmatter = text[: body_start]
    assert "doc_type: journal" in frontmatter
    assert "id:" in frontmatter
    assert "created:" in frontmatter
    assert "last_validated:" in frontmatter
    # Heading + content appear after frontmatter.
    body = text[body_start:]
    assert "## 07:32" in body
    assert "First entry of the day" in body


def test_appends_section_under_h2_timestamp_heading(
    fake_journal_dir, content_file_factory
):
    cf = content_file_factory(
        "A thoughtful reflection on today's progress, deserves its own heading."
    )
    rje.main(
        [
            "--content-file",
            str(cf),
            "--datetime",
            "2026-06-08T07:32:00-04:00",
        ]
    )
    target = fake_journal_dir / "Journal 2026-06-08 0732.md"
    text = target.read_text(encoding="utf-8")
    # The level-2 heading combines timestamp + trimmed excerpt.
    assert "## 07:32 — " in text
    assert "A thoughtful reflection" in text


def test_appends_to_existing_journal_file(
    fake_journal_dir, content_file_factory
):
    cf1 = content_file_factory("First section content for the same minute.", "a.txt")
    cf2 = content_file_factory("Second section content for the same minute.", "b.txt")
    rje.main(
        ["--content-file", str(cf1), "--datetime", "2026-06-08T07:32:00-04:00"]
    )
    rje.main(
        ["--content-file", str(cf2), "--datetime", "2026-06-08T07:32:00-04:00"]
    )
    target = fake_journal_dir / "Journal 2026-06-08 0732.md"
    text = target.read_text(encoding="utf-8")
    # Two heading occurrences, frontmatter only once.
    assert text.count("## 07:32") == 2
    assert text.count("---\ndoc_type: journal") + text.count(
        "---\nid:"
    ) <= 1 or text.count("doc_type: journal") == 1
    assert "First section content" in text
    assert "Second section content" in text


def test_datetime_drives_filename(fake_journal_dir, content_file_factory):
    cf = content_file_factory("Body.")
    rje.main(
        ["--content-file", str(cf), "--datetime", "2026-06-08T07:32:00-04:00"]
    )
    assert (fake_journal_dir / "Journal 2026-06-08 0732.md").exists()
    # Different minute -> different file.
    rje.main(
        ["--content-file", str(cf), "--datetime", "2026-06-08T07:33:00-04:00"]
    )
    assert (fake_journal_dir / "Journal 2026-06-08 0733.md").exists()


def test_short_content_uses_only_timestamp_heading(
    fake_journal_dir, content_file_factory
):
    cf = content_file_factory("hey")  # <8 chars
    rje.main(
        ["--content-file", str(cf), "--datetime", "2026-06-08T07:32:00-04:00"]
    )
    target = fake_journal_dir / "Journal 2026-06-08 0732.md"
    text = target.read_text(encoding="utf-8")
    # Heading line is bare timestamp (no em-dash + excerpt).
    assert "## 07:32\n" in text
    assert "## 07:32 — " not in text


def test_journal_path_via_vault_paths_module(
    monkeypatch, tmp_path: Path, content_file_factory
):
    """Verifies FR-011: helper resolves the journal directory via the
    vault registry, not a hard-coded fallback. We patch the resolver to
    point at tmp_path and assert the file lands there.
    """
    custom_dir = tmp_path / "custom-journal"
    custom_dir.mkdir()
    monkeypatch.setattr(rje, "_get_vault_path", lambda name: str(custom_dir))
    cf = content_file_factory("Routed via the registry.")
    rc = rje.main(
        ["--content-file", str(cf), "--datetime", "2026-06-08T07:32:00-04:00"]
    )
    assert rc == 0
    assert (custom_dir / "Journal 2026-06-08 0732.md").exists()


# ---------------------------------------------------------------------------
# Atomic-write invariants
# ---------------------------------------------------------------------------


def _stray_tmp(dir_: Path) -> list[Path]:
    return [p for p in dir_.iterdir() if p.suffix == ".tmp"]


def test_atomic_write_no_temp_leftover_on_success(
    fake_journal_dir, content_file_factory
):
    cf = content_file_factory("Some content for atomic-write test.")
    rje.main(
        ["--content-file", str(cf), "--datetime", "2026-06-08T07:32:00-04:00"]
    )
    assert _stray_tmp(fake_journal_dir) == []


def test_atomic_write_no_corruption_on_failure(
    fake_journal_dir, content_file_factory, monkeypatch
):
    """If os.replace raises mid-write, the target is untouched and no
    stray .tmp sibling remains.
    """
    cf1 = content_file_factory("Original content.", "a.txt")
    rje.main(
        ["--content-file", str(cf1), "--datetime", "2026-06-08T07:32:00-04:00"]
    )
    target = fake_journal_dir / "Journal 2026-06-08 0732.md"
    original_text = target.read_text(encoding="utf-8")

    cf2 = content_file_factory("Second content; should not land.", "b.txt")

    def boom(*args, **kwargs):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(rje.os, "replace", boom)
    rc = rje.main(
        ["--content-file", str(cf2), "--datetime", "2026-06-08T07:32:00-04:00"]
    )
    assert rc != 0
    # Target file unchanged.
    assert target.read_text(encoding="utf-8") == original_text
    # No stray tempfile.
    assert _stray_tmp(fake_journal_dir) == []


# ---------------------------------------------------------------------------
# CLI error handling
# ---------------------------------------------------------------------------


def test_invalid_datetime_exits_1(fake_journal_dir, content_file_factory, capsys):
    cf = content_file_factory("Body.")
    rc = rje.main(
        ["--content-file", str(cf), "--datetime", "not-a-datetime"]
    )
    assert rc == 1
    err = capsys.readouterr().err
    assert "invalid_datetime" in err or "invalid" in err.lower()


def test_missing_content_file_exits_1(fake_journal_dir, tmp_path: Path, capsys):
    rc = rje.main(
        [
            "--content-file",
            str(tmp_path / "does-not-exist.txt"),
            "--datetime",
            "2026-06-08T07:32:00-04:00",
        ]
    )
    assert rc == 1
    err = capsys.readouterr().err
    assert "content_file" in err or "not found" in err.lower()


def test_help_exits_0(capsys):
    with pytest.raises(SystemExit) as exc:
        rje.main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "--content-file" in out
    assert "--datetime" in out


# ---------------------------------------------------------------------------
# Module-resolution + path-resolver wiring
# ---------------------------------------------------------------------------


def test_resolve_journal_dir_returns_path_from_registry(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(rje, "_get_vault_path", lambda name: str(tmp_path / "08-Journal"))
    result = rje.resolve_journal_dir()
    assert isinstance(result, Path)
    assert result == tmp_path / "08-Journal"


def test_ensure_journal_file_creates_with_frontmatter(tmp_path: Path):
    target = tmp_path / "Journal 2026-06-08 0732.md"
    dt = datetime(2026, 6, 8, 7, 32, tzinfo=timezone.utc)
    rje.ensure_journal_file(target, dt)
    assert target.exists()
    text = target.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "doc_type: journal" in text
    assert "id:" in text
    assert "created: 2026-06-08" in text


def test_ensure_journal_file_is_idempotent(tmp_path: Path):
    """Calling ensure_journal_file twice does not overwrite or duplicate."""
    target = tmp_path / "Journal 2026-06-08 0732.md"
    dt = datetime(2026, 6, 8, 7, 32, tzinfo=timezone.utc)
    rje.ensure_journal_file(target, dt)
    first_text = target.read_text(encoding="utf-8")
    rje.ensure_journal_file(target, dt)
    second_text = target.read_text(encoding="utf-8")
    assert first_text == second_text


def test_append_section_preserves_existing_content(tmp_path: Path):
    target = tmp_path / "Journal 2026-06-08 0732.md"
    target.write_text(
        "---\nid: x\ndoc_type: journal\n---\n\n## 07:30 — earlier\nEarlier body\n",
        encoding="utf-8",
    )
    rje.append_section(target, "## 07:35 — newer", "Newer body")
    text = target.read_text(encoding="utf-8")
    assert "Earlier body" in text
    assert "## 07:30 — earlier" in text
    assert "## 07:35 — newer" in text
    assert "Newer body" in text


def test_append_section_normalizes_file_without_trailing_newline(tmp_path: Path):
    """Cover the `not existing.endswith("\\n")` branch in append_section."""
    target = tmp_path / "Journal 2026-06-08 0732.md"
    # Deliberately write without a trailing newline.
    target.write_text(
        "---\nid: x\ndoc_type: journal\n---\n\nbody-without-newline",
        encoding="utf-8",
    )
    rje.append_section(target, "## 07:35 — newer", "Newer body")
    text = target.read_text(encoding="utf-8")
    assert "body-without-newline" in text
    assert "## 07:35 — newer" in text
    assert "Newer body" in text


# ---------------------------------------------------------------------------
# Datetime + vault-resolver edge cases
# ---------------------------------------------------------------------------


def test_parse_iso_datetime_accepts_z_suffix():
    """Covers the legacy `Z` suffix branch in _parse_iso_datetime."""
    dt = rje._parse_iso_datetime("2026-06-08T07:32:00Z")
    assert dt.year == 2026
    assert dt.month == 6
    assert dt.day == 8
    assert dt.hour == 7
    assert dt.minute == 32
    assert dt.tzinfo is not None


def test_get_vault_path_delegates_to_resolver(monkeypatch):
    """Covers the `_get_vault_path` body — the resolver-bridge shim.

    Stubs ``scripts.vault.resolver.get_vault_path`` so the test does not
    depend on the real registry file on disk.
    """
    import scripts.vault.resolver as resolver_mod

    calls = []

    def fake(name):
        calls.append(name)
        return "/tmp/fake-journal"

    monkeypatch.setattr(resolver_mod, "get_vault_path", fake)
    result = rje._get_vault_path("journal")
    assert result == "/tmp/fake-journal"
    assert calls == ["journal"]


def test_main_emits_vault_resolve_failed_when_resolver_raises(
    monkeypatch, tmp_path: Path, content_file_factory, capsys
):
    """Covers the `vault_resolve_failed` error path in `main`.

    The resolver patch raises so `main` exits 1 with a structured stderr
    payload tagged ``vault_resolve_failed``.
    """

    def boom(name):
        raise RuntimeError("registry unreachable")

    monkeypatch.setattr(rje, "_get_vault_path", boom)
    cf = content_file_factory("body")
    rc = rje.main(
        ["--content-file", str(cf), "--datetime", "2026-06-08T07:32:00-04:00"]
    )
    assert rc == 1
    err = capsys.readouterr().err
    assert "vault_resolve_failed" in err
    assert "registry unreachable" in err


def test_atomic_write_swallows_unlink_failure_during_cleanup(
    tmp_path: Path, monkeypatch
):
    """Covers the defensive ``except OSError: pass`` around ``os.unlink``.

    If the primary write raises AND the cleanup ``os.unlink`` also
    raises, the original exception still propagates — the cleanup
    failure is intentionally swallowed.
    """
    target = tmp_path / "j.md"

    # Force the primary write path to raise so cleanup runs.
    def raise_during_write(*args, **kwargs):
        raise RuntimeError("primary write failure")

    monkeypatch.setattr(rje.os, "fdopen", raise_during_write)

    # Force cleanup unlink to also raise.
    def unlink_boom(_path):
        raise OSError("cleanup unlink failed")

    monkeypatch.setattr(rje.os, "unlink", unlink_boom)

    with pytest.raises(RuntimeError, match="primary write failure"):
        rje._atomic_write(target, "x")


def test_main_emits_read_failed_when_content_file_unreadable(
    fake_journal_dir, tmp_path: Path, monkeypatch, capsys
):
    """Covers the OSError-on-read_text branch in `main`.

    The content file exists (``exists()`` returns True) but reading it
    raises OSError — we patch ``Path.read_text`` to simulate that.
    """
    cf = tmp_path / "content.txt"
    cf.write_text("body", encoding="utf-8")

    original_read_text = Path.read_text

    def selective_boom(self, *args, **kwargs):
        if self == cf:
            raise OSError("simulated read failure")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", selective_boom)
    rc = rje.main(
        ["--content-file", str(cf), "--datetime", "2026-06-08T07:32:00-04:00"]
    )
    assert rc == 1
    err = capsys.readouterr().err
    assert "read_failed" in err
