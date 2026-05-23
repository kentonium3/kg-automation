"""Unit tests for ``scripts/openclaw/helpers/rotate_main_session.py`` (WP02).

The rotation helper is an operator-driven one-shot — these tests
verify the contract documented in
``kitty-specs/main-verbatim-passthrough-01KSATRP/contracts/rotation-helper.md``
without touching the real ``/home/claude/.openclaw/agents/main/sessions/``
directory or the operator's real ``~/.config/openclaw`` directory.

All scenarios use ``tmp_path`` fixtures + explicit ``sessions_dir`` and
``marker_dir`` overrides passed through to :func:`run`.

Tests cover the contract's nine scenarios plus marker contents +
timestamp format assertions — 12 test functions total.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

# Bootstrap sys.path so ``openclaw.helpers.rotate_main_session`` resolves
# without depending on the ``scripts.`` namespace package prefix.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from openclaw.helpers import rotate_main_session  # noqa: E402
from openclaw.helpers.rotate_main_session import (  # noqa: E402
    MISSION_SLUG,
    RotationResult,
    _list_active_sessions,
    _now_timestamp,
    _rotate_session,
    _write_marker,
    main,
    run,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_sessions(dir_: Path, active_names: list[str], reset_names: list[str]) -> None:
    """Populate ``dir_`` with mock active + already-rotated session files."""
    dir_.mkdir(parents=True, exist_ok=True)
    for name in active_names:
        (dir_ / name).write_text(f"# fake session content for {name}\n", encoding="utf-8")
    for name in reset_names:
        (dir_ / name).write_text(f"# already-rotated content for {name}\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Happy path: 3 active sessions -> 3 renames + marker
# ---------------------------------------------------------------------------


def test_run_happy_path_rotates_all_active_sessions(tmp_path: Path) -> None:
    sessions_dir = tmp_path / "sessions"
    marker_dir = tmp_path / "config" / "openclaw"
    active = [
        "29146776-d8b1-4a2c-9f01-df2981aa6ba4.jsonl",
        "5f88a221-8e8f-4f3d-b0a0-30ec76f01234.jsonl",
        "abc01234-0000-4000-8000-000000000001.jsonl",
    ]
    _seed_sessions(sessions_dir, active_names=active, reset_names=[])

    result = run(sessions_dir=sessions_dir, marker_dir=marker_dir)

    assert isinstance(result, RotationResult)
    assert result.dry_run is False
    assert sorted(result.rotated) == sorted(active)
    assert result.marker_path is not None and result.marker_path.exists()
    # Each original `.jsonl` file is gone, replaced by a `.jsonl.reset.*` file.
    remaining = sorted(p.name for p in sessions_dir.iterdir())
    assert all(".jsonl.reset." in name for name in remaining)
    assert len(remaining) == len(active)


# ---------------------------------------------------------------------------
# 2. Dry-run: no renames, no marker
# ---------------------------------------------------------------------------


def test_run_dry_run_makes_no_filesystem_changes(tmp_path: Path) -> None:
    sessions_dir = tmp_path / "sessions"
    marker_dir = tmp_path / "config" / "openclaw"
    active = [
        "11111111-1111-4111-8111-111111111111.jsonl",
        "22222222-2222-4222-8222-222222222222.jsonl",
        "33333333-3333-4333-8333-333333333333.jsonl",
    ]
    _seed_sessions(sessions_dir, active_names=active, reset_names=[])

    result = run(
        dry_run=True,
        sessions_dir=sessions_dir,
        marker_dir=marker_dir,
    )

    assert result.dry_run is True
    assert sorted(result.rotated) == sorted(active)  # describes what *would* happen
    assert result.marker_path is not None  # intended path returned
    assert not result.marker_path.exists()
    # No marker dir created; original session files untouched.
    assert not marker_dir.exists()
    actual = sorted(p.name for p in sessions_dir.iterdir())
    assert actual == sorted(active)


# ---------------------------------------------------------------------------
# 3. Empty sessions dir: returns empty rotated, no marker, exit 0
# ---------------------------------------------------------------------------


def test_run_empty_sessions_dir_returns_no_op(tmp_path: Path) -> None:
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    marker_dir = tmp_path / "config" / "openclaw"

    result = run(sessions_dir=sessions_dir, marker_dir=marker_dir)

    assert result.rotated == []
    assert result.marker_path is None
    assert result.dry_run is False
    # No marker dir created (there was nothing to record).
    assert not marker_dir.exists()


def test_run_missing_sessions_dir_returns_no_op(tmp_path: Path) -> None:
    """If the sessions directory doesn't exist, behave like 'empty'."""
    sessions_dir = tmp_path / "does-not-exist"
    marker_dir = tmp_path / "config" / "openclaw"

    result = run(sessions_dir=sessions_dir, marker_dir=marker_dir)

    assert result.rotated == []
    assert result.marker_path is None
    assert not marker_dir.exists()


# ---------------------------------------------------------------------------
# 4. Skip-reset filter: `.jsonl.reset.*` files are NOT rotated
# ---------------------------------------------------------------------------


def test_run_skips_already_rotated_files(tmp_path: Path) -> None:
    sessions_dir = tmp_path / "sessions"
    marker_dir = tmp_path / "config" / "openclaw"
    active = [
        "active-aaa.jsonl",
        "active-bbb.jsonl",
    ]
    reset = [
        "old-ccc.jsonl.reset.2026-05-22T10-00-00.000Z",
        "old-ddd.jsonl.reset.2026-05-22T11-15-30.500Z",
    ]
    _seed_sessions(sessions_dir, active_names=active, reset_names=reset)

    result = run(sessions_dir=sessions_dir, marker_dir=marker_dir)

    assert sorted(result.rotated) == sorted(active)
    # The pre-existing reset files are still on disk, untouched.
    surviving = {p.name for p in sessions_dir.iterdir()}
    for original_reset in reset:
        assert original_reset in surviving
    # And the original active files have all been rotated away.
    for original_active in active:
        assert original_active not in surviving


# ---------------------------------------------------------------------------
# 5. Filesystem rename failure -> main() returns 1
# ---------------------------------------------------------------------------


def test_main_returns_1_on_rename_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sessions_dir = tmp_path / "sessions"
    marker_dir = tmp_path / "config" / "openclaw"
    _seed_sessions(
        sessions_dir,
        active_names=["a.jsonl", "b.jsonl", "c.jsonl"],
        reset_names=[],
    )

    # Patch Path.rename to raise on the *second* rotation call so we
    # exercise the partial-state-acceptable path documented in the contract.
    real_rename = Path.rename
    calls = {"n": 0}

    def flaky_rename(self: Path, target: Path) -> Path:
        calls["n"] += 1
        if calls["n"] >= 2:
            raise OSError("disk full")
        return real_rename(self, target)

    monkeypatch.setattr(Path, "rename", flaky_rename)
    monkeypatch.setattr(rotate_main_session, "SESSIONS_DIR", sessions_dir)
    monkeypatch.setattr(rotate_main_session, "MARKER_DIR", marker_dir)

    rc = main([])
    assert rc == 1
    # No marker was written (the failure short-circuited before _write_marker).
    assert not marker_dir.exists() or not any(marker_dir.iterdir())


# ---------------------------------------------------------------------------
# 6. Marker write failure -> main() returns 1
# ---------------------------------------------------------------------------


def test_main_returns_1_on_marker_write_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sessions_dir = tmp_path / "sessions"
    _seed_sessions(sessions_dir, active_names=["x.jsonl"], reset_names=[])

    # Point MARKER_DIR at a path whose parent is a regular file — mkdir(parents=True)
    # raises NotADirectoryError (a subclass of OSError).
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    bad_marker_dir = blocker / "openclaw"

    monkeypatch.setattr(rotate_main_session, "SESSIONS_DIR", sessions_dir)
    monkeypatch.setattr(rotate_main_session, "MARKER_DIR", bad_marker_dir)

    rc = main([])
    assert rc == 1


# ---------------------------------------------------------------------------
# 7. CLI exit code 0: valid args + happy path -> returns 0
# ---------------------------------------------------------------------------


def test_main_returns_0_on_happy_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sessions_dir = tmp_path / "sessions"
    marker_dir = tmp_path / "config" / "openclaw"
    _seed_sessions(
        sessions_dir,
        active_names=["foo.jsonl", "bar.jsonl"],
        reset_names=[],
    )
    monkeypatch.setattr(rotate_main_session, "SESSIONS_DIR", sessions_dir)
    monkeypatch.setattr(rotate_main_session, "MARKER_DIR", marker_dir)

    rc = main([])

    assert rc == 0
    # Marker file present, both originals rotated.
    marker_files = list(marker_dir.iterdir())
    assert len(marker_files) == 1
    surviving = sorted(p.name for p in sessions_dir.iterdir())
    assert "foo.jsonl" not in surviving
    assert "bar.jsonl" not in surviving


def test_main_returns_0_on_dry_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    sessions_dir = tmp_path / "sessions"
    marker_dir = tmp_path / "config" / "openclaw"
    _seed_sessions(
        sessions_dir, active_names=["only.jsonl"], reset_names=[]
    )
    monkeypatch.setattr(rotate_main_session, "SESSIONS_DIR", sessions_dir)
    monkeypatch.setattr(rotate_main_session, "MARKER_DIR", marker_dir)

    rc = main(["--dry-run"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "Would rotate" in out
    # Nothing mutated.
    assert (sessions_dir / "only.jsonl").exists()
    assert not marker_dir.exists()


def test_main_returns_0_with_force_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--force` is reserved for future use; today it must not error."""
    sessions_dir = tmp_path / "sessions"
    marker_dir = tmp_path / "config" / "openclaw"
    _seed_sessions(
        sessions_dir, active_names=["forced.jsonl"], reset_names=[]
    )
    monkeypatch.setattr(rotate_main_session, "SESSIONS_DIR", sessions_dir)
    monkeypatch.setattr(rotate_main_session, "MARKER_DIR", marker_dir)

    rc = main(["--force"])
    assert rc == 0


# ---------------------------------------------------------------------------
# 8. CLI exit code 3: unknown flag -> returns 3 (via _StructuredArgumentParser)
# ---------------------------------------------------------------------------


def test_main_returns_3_on_unknown_flag(capsys) -> None:
    rc = main(["--this-is-not-a-real-flag"])
    assert rc == 3
    err = capsys.readouterr().err
    assert "error:" in err or "unrecognized" in err.lower()


def test_main_help_exits_0(capsys) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert "--dry-run" in out
    assert "--force" in out


# ---------------------------------------------------------------------------
# 9. Marker contents: mission_slug + rotated list present
# ---------------------------------------------------------------------------


def test_marker_contents_record_mission_and_rotated_list(tmp_path: Path) -> None:
    sessions_dir = tmp_path / "sessions"
    marker_dir = tmp_path / "config" / "openclaw"
    active = ["uuid-a.jsonl", "uuid-b.jsonl", "uuid-c.jsonl"]
    _seed_sessions(sessions_dir, active_names=active, reset_names=[])

    result = run(sessions_dir=sessions_dir, marker_dir=marker_dir)
    assert result.marker_path is not None

    body = result.marker_path.read_text(encoding="utf-8")
    # Parse the key:value lines so we don't depend on exact spacing.
    fields: dict[str, str] = {}
    for line in body.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fields[k.strip()] = v.strip()

    assert fields["mission"] == MISSION_SLUG
    assert "run_at_utc" in fields
    # Marker filename embeds the same timestamp as the run_at_utc value.
    assert fields["run_at_utc"] in result.marker_path.name
    # Every rotated file appears in the `rotated:` line.
    for name in active:
        assert name in fields["rotated"]


# ---------------------------------------------------------------------------
# 10. Timestamp format conforms to ^YYYY-MM-DDTHH-MM-SS.mmmZ$
# ---------------------------------------------------------------------------


def test_now_timestamp_matches_documented_format() -> None:
    pattern = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}\.\d{3}Z$")
    ts = _now_timestamp()
    assert pattern.match(ts), f"timestamp {ts!r} does not match {pattern.pattern}"


# ---------------------------------------------------------------------------
# 11. Helper-level coverage: _list_active_sessions filter behavior
# ---------------------------------------------------------------------------


def test_list_active_sessions_filters_reset_and_non_jsonl(tmp_path: Path) -> None:
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    # Active sessions:
    (sessions_dir / "a.jsonl").write_text("a", encoding="utf-8")
    (sessions_dir / "b.jsonl").write_text("b", encoding="utf-8")
    # Already-rotated:
    (sessions_dir / "old.jsonl.reset.2026-05-22T10-00-00.000Z").write_text(
        "old", encoding="utf-8"
    )
    # Not a session file at all (no `.jsonl` suffix):
    (sessions_dir / "README.txt").write_text("not a session", encoding="utf-8")
    # A subdirectory must be ignored (only files count).
    (sessions_dir / "subdir").mkdir()

    actives = _list_active_sessions(sessions_dir)
    names = sorted(p.name for p in actives)
    assert names == ["a.jsonl", "b.jsonl"]


def test_list_active_sessions_returns_empty_for_missing_dir(tmp_path: Path) -> None:
    missing = tmp_path / "not-here"
    assert _list_active_sessions(missing) == []


# ---------------------------------------------------------------------------
# 12. Helper-level coverage: _rotate_session + _write_marker direct
# ---------------------------------------------------------------------------


def test_rotate_session_returns_new_path_and_renames(tmp_path: Path) -> None:
    src = tmp_path / "session.jsonl"
    src.write_text("payload", encoding="utf-8")
    ts = "2026-05-23T16-30-45.000Z"

    new_path = _rotate_session(src, ts)

    assert new_path.name == f"session.jsonl.reset.{ts}"
    assert new_path.exists()
    assert not src.exists()
    assert new_path.read_text(encoding="utf-8") == "payload"


def test_write_marker_creates_parent_and_returns_path(tmp_path: Path) -> None:
    marker_dir = tmp_path / "nested" / "openclaw"  # parent missing on purpose
    ts = "2026-05-23T17-00-00.000Z"
    rotated = ["one.jsonl", "two.jsonl"]

    marker_path = _write_marker(rotated, ts, marker_dir)

    assert marker_path.exists()
    assert marker_path.name == f"main-rotation-{ts}.done"
    body = marker_path.read_text(encoding="utf-8")
    assert "mission: " + MISSION_SLUG in body
    assert "run_at_utc: " + ts in body
    assert "one.jsonl" in body
    assert "two.jsonl" in body


def test_write_marker_with_empty_rotated_still_writes(tmp_path: Path) -> None:
    marker_dir = tmp_path / "openclaw"
    ts = "2026-05-23T18-00-00.000Z"

    marker_path = _write_marker([], ts, marker_dir)
    assert marker_path.exists()
    body = marker_path.read_text(encoding="utf-8")
    assert "rotated: (none)" in body


# ---------------------------------------------------------------------------
# 13. End-to-end CLI smoke via subprocess: --help exits 0 with usage text
# ---------------------------------------------------------------------------


def test_script_runs_as_subprocess_help() -> None:
    """Exec the script via python3 to verify the CLI works end-to-end."""
    script = (
        REPO_ROOT / "scripts" / "openclaw" / "helpers" / "rotate_main_session.py"
    )
    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "--dry-run" in result.stdout
    assert "--force" in result.stdout
