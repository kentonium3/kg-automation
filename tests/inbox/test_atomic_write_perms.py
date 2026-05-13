"""Unit tests for `_atomic_write` mode handling in inbox marker helpers.

Covers FR-001 through FR-006 from spec
`kitty-specs/inbox-atomic-write-perm-preservation-01KRFS03/spec.md`:

- Mode preservation when the target file already exists (0o600, 0o644, 0o664).
- Default 0o664 when the target does not yet exist.
- Atomic invariant: if the write raises mid-flight, the target is untouched
  and no stray `.tmp` file is left behind.

The two helper modules each have their own copy of `_atomic_write` (per
spec decision C-002 — duplication is intentional). We parameterize over
both modules so the same suite exercises each.

Tests use `tmp_path`; they never touch real second-brain or inbox paths
and do not depend on the test process running as a specific uid/gid.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

import inject_parse_error_marker
import strip_parse_error_marker

HELPER_MODULES = [inject_parse_error_marker, strip_parse_error_marker]
HELPER_IDS = [m.__name__ for m in HELPER_MODULES]


@pytest.fixture
def existing_note(tmp_path: Path):
    """Factory: create `tmp_path/note.md` with given mode and return its path."""

    def _make(mode: int, body: str = "original body\n") -> Path:
        path = tmp_path / "note.md"
        path.write_text(body, encoding="utf-8")
        os.chmod(path, mode)
        # Sanity-check setup so a failing fixture is obvious before assertions.
        assert stat.S_IMODE(path.stat().st_mode) == mode
        return path

    return _make


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def _stray_tmp_files(directory: Path) -> list[Path]:
    """Return any leftover `.tmp` siblings (atomic-write tempfile prefix)."""
    return [p for p in directory.iterdir() if p.suffix == ".tmp"]


@pytest.mark.parametrize("helper", HELPER_MODULES, ids=HELPER_IDS)
def test_preserves_mode_0o600(helper, existing_note):
    path = existing_note(0o600)

    helper._atomic_write(path, "new content\n")

    assert _mode(path) == 0o600
    assert path.read_text(encoding="utf-8") == "new content\n"


@pytest.mark.parametrize("helper", HELPER_MODULES, ids=HELPER_IDS)
def test_preserves_mode_0o644(helper, existing_note):
    path = existing_note(0o644)

    helper._atomic_write(path, "new content\n")

    assert _mode(path) == 0o644
    assert path.read_text(encoding="utf-8") == "new content\n"


@pytest.mark.parametrize("helper", HELPER_MODULES, ids=HELPER_IDS)
def test_preserves_mode_0o664(helper, existing_note):
    path = existing_note(0o664)

    helper._atomic_write(path, "new content\n")

    assert _mode(path) == 0o664
    assert path.read_text(encoding="utf-8") == "new content\n"


@pytest.mark.parametrize("helper", HELPER_MODULES, ids=HELPER_IDS)
def test_new_file_default_0o664(helper, tmp_path: Path):
    path = tmp_path / "fresh.md"
    assert not path.exists()

    helper._atomic_write(path, "brand new\n")

    assert path.exists()
    assert _mode(path) == 0o664
    assert path.read_text(encoding="utf-8") == "brand new\n"


@pytest.mark.parametrize("helper", HELPER_MODULES, ids=HELPER_IDS)
def test_exception_leaves_target_untouched(
    helper, existing_note, tmp_path: Path, monkeypatch
):
    """If the write raises after mkstemp, the target file is untouched and
    no stray .tmp sibling remains in the parent directory."""
    path = existing_note(0o644, body="ORIGINAL\n")
    original_mtime = path.stat().st_mtime_ns

    real_fdopen = os.fdopen

    def boom(*args, **kwargs):
        # Allow the temp fd to be closed cleanly so we don't leak a handle,
        # then raise to simulate a disk error / write failure.
        fh = real_fdopen(*args, **kwargs)
        fh.close()
        raise RuntimeError("simulated write failure")

    monkeypatch.setattr(helper.os, "fdopen", boom)

    with pytest.raises(RuntimeError, match="simulated write failure"):
        helper._atomic_write(path, "should not land\n")

    # Target file content & mode unchanged.
    assert path.read_text(encoding="utf-8") == "ORIGINAL\n"
    assert _mode(path) == 0o644
    assert path.stat().st_mtime_ns == original_mtime

    # No stray .tmp sibling left in the parent dir.
    assert _stray_tmp_files(tmp_path) == []


@pytest.mark.parametrize("helper", HELPER_MODULES, ids=HELPER_IDS)
def test_emits_stderr_log_line_on_success(
    helper, existing_note, capsys
):
    """One stderr log line per successful write, with path/mode/kind."""
    path = existing_note(0o644)

    helper._atomic_write(path, "new content\n")

    captured = capsys.readouterr()
    assert captured.err.count("INFO: atomic_write") == 1
    assert "mode=0o644" in captured.err
    assert "(preserved)" in captured.err
    assert str(path) in captured.err


@pytest.mark.parametrize("helper", HELPER_MODULES, ids=HELPER_IDS)
def test_emits_stderr_log_line_for_new_file(helper, tmp_path: Path, capsys):
    """New-file path emits the `(new)` kind in the log line."""
    path = tmp_path / "fresh.md"

    helper._atomic_write(path, "brand new\n")

    captured = capsys.readouterr()
    assert captured.err.count("INFO: atomic_write") == 1
    assert "mode=0o664" in captured.err
    assert "(new)" in captured.err
