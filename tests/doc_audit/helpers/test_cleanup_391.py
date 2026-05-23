"""Unit tests for ``scripts/doc_audit/helpers/cleanup_391.py`` (WP03).

The cleanup script is a one-shot operator tool — these tests verify
the contract without making real GitHub API calls or writing to the
operator's real ``~/.config/doc-audit`` directory.

All subprocess calls (``gh issue comment``, ``gh issue close``) are
patched at the ``subprocess.run`` boundary. Marker writes go to
``tmp_path`` via the ``marker_path`` override parameter so we can
assert on file contents without touching ``$HOME``.

Mirrors the patterns established in ``test_cutover_362.py`` with two
deliberate omissions:

    1. No ``gh issue list`` tests — cleanup_391 uses a STATIC list.
    2. No cursor-reset tests — cleanup_391 does NOT reset any cursor.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

# Import the module under test. The conftest.py at tests/doc_audit/conftest.py
# already adds ``scripts/`` to sys.path so ``doc_audit.*`` resolves.
from doc_audit.helpers import cleanup_391
from doc_audit.helpers.cleanup_391 import (
    COMMENT_BODY,
    CleanupResult,
    GH_RATE_DELAY_SECONDS,
    ISSUE_NUMBERS,
    MISSION_ID,
    MISSION_SLUG,
    REPO,
    _close_all_issues,
    _close_issue,
    _marker_exists,
    _write_marker,
    main,
    run,
)


# ---------------------------------------------------------------------------
# subprocess.run fake — routes by command shape
# ---------------------------------------------------------------------------


class _FakeRun:
    """Routable replacement for ``subprocess.run``.

    Tests register per-call behavior keyed on the first two ``gh``
    sub-commands (``"gh issue comment"``, ``"gh issue close"``).
    Unregistered calls raise AssertionError so tests fail loudly if
    the code under test ever shells out to something we didn't
    anticipate.

    Each route is either:
        - a ``subprocess.CompletedProcess`` (returned as-is)
        - a callable taking ``(cmd, **kwargs)`` returning a CompletedProcess
        - an exception instance (raised when the route fires)
        - a list of any of the above (consumed in order — useful for
          "fail once, then succeed")
    """

    def __init__(self) -> None:
        self.routes: dict[str, Any] = {}
        self.calls: list[list[str]] = []

    def register(self, key: str, behavior: Any) -> None:
        self.routes[key] = behavior

    def _key_for(self, cmd: list[str]) -> str:
        if not cmd:
            return ""
        if cmd[0] == "gh":
            # "gh issue comment" / "gh issue close"
            return " ".join(cmd[:3])
        return cmd[0]

    def __call__(self, cmd, *args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
        if not isinstance(cmd, (list, tuple)):
            raise AssertionError(
                f"_FakeRun expected list/tuple cmd, got {cmd!r}"
            )
        recorded = [str(p) for p in cmd]
        self.calls.append(recorded)

        key = self._key_for(recorded)
        if key not in self.routes:
            raise AssertionError(
                f"_FakeRun has no route for key {key!r}; cmd={recorded!r}"
            )

        behavior = self.routes[key]
        if isinstance(behavior, list):
            if not behavior:
                raise AssertionError(
                    f"_FakeRun route {key!r} exhausted (list empty)"
                )
            behavior = behavior.pop(0)

        if callable(behavior):
            return behavior(recorded, **kwargs)
        if isinstance(behavior, BaseException):
            raise behavior
        if isinstance(behavior, subprocess.CompletedProcess):
            return behavior
        raise AssertionError(
            f"_FakeRun route {key!r} has unknown behavior type "
            f"{type(behavior).__name__}"
        )


def _ok_completed(cmd: list[str], stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=cmd, returncode=0, stdout=stdout, stderr=stderr
    )


@pytest.fixture
def fake_run(monkeypatch: pytest.MonkeyPatch) -> _FakeRun:
    """Patch ``subprocess.run`` inside ``cleanup_391`` with a routable fake."""
    fake = _FakeRun()
    monkeypatch.setattr(cleanup_391.subprocess, "run", fake)
    return fake


@pytest.fixture
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> mock.MagicMock:
    """Patch ``time.sleep`` so tests don't wait the polite-rate delay."""
    sleeper = mock.MagicMock()
    monkeypatch.setattr(cleanup_391.time, "sleep", sleeper)
    return sleeper


@pytest.fixture
def tmp_marker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Override the module-level MARKER_PATH to live under tmp_path.

    The implementation prefers explicit ``marker_path`` overrides in
    ``run()``/``_write_marker()``/``_marker_exists()``, but ``main()``
    has no such hook — patching the module constant covers that path.
    """
    marker = tmp_path / "cleanup-391.done"
    monkeypatch.setattr(cleanup_391, "MARKER_PATH", marker)
    return marker


# ---------------------------------------------------------------------------
# Static module-constant sanity checks
# ---------------------------------------------------------------------------


def test_issue_numbers_is_static_13_entries_378_to_390():
    """The cleanup target is a STATIC list of 13 known artifact issues."""
    assert ISSUE_NUMBERS == [378, 379, 380, 381, 382, 383, 384, 385, 386, 387, 388, 389, 390]
    assert len(ISSUE_NUMBERS) == 13


def test_comment_body_references_mission_and_drift_moment0():
    """The closing comment names the fix site so future spelunkers can trace it."""
    assert "moment0-integration-fix-01KS8XRM" in COMMENT_BODY
    assert "#391" in COMMENT_BODY
    assert "signals/drift_event.py" in COMMENT_BODY
    assert "routing/drift_moment0.py" in COMMENT_BODY


# ---------------------------------------------------------------------------
# 1. Happy path: all 13 issues closed; marker written
# ---------------------------------------------------------------------------


def test_run_happy_path_closes_all_13_issues_and_writes_marker(
    tmp_path: Path, fake_run: _FakeRun, no_sleep, tmp_marker: Path
):
    fake_run.register(
        "gh issue comment",
        [_ok_completed(["gh"]) for _ in ISSUE_NUMBERS],
    )
    fake_run.register(
        "gh issue close",
        [_ok_completed(["gh"]) for _ in ISSUE_NUMBERS],
    )

    result = run(marker_path=tmp_marker)

    assert isinstance(result, CleanupResult)
    assert result.issues_closed == ISSUE_NUMBERS
    assert len(result.issues_closed) == 13
    assert result.marker_written is True
    assert result.dry_run is False
    assert result.already_done is False
    # Marker file exists and contains the expected fields
    assert tmp_marker.exists()
    body = tmp_marker.read_text(encoding="utf-8")
    assert MISSION_SLUG in body
    assert MISSION_ID in body
    # First and last issues recorded
    assert "378" in body and "390" in body


# ---------------------------------------------------------------------------
# 2. Dry-run: no mutations at all
# ---------------------------------------------------------------------------


def test_run_dry_run_makes_no_subprocess_calls_or_marker_write(
    tmp_path: Path, fake_run: _FakeRun, no_sleep, tmp_marker: Path
):
    # No routes registered — any subprocess call would AssertionError.
    result = run(dry_run=True, marker_path=tmp_marker)

    assert result.dry_run is True
    assert result.issues_closed == []  # nothing actually closed
    assert result.marker_written is True  # "would write"
    assert result.already_done is False
    # No marker file on disk
    assert not tmp_marker.exists()
    # No subprocess.run calls at all
    assert fake_run.calls == []


# ---------------------------------------------------------------------------
# 3. Idempotent no-op: marker pre-exists → run() returns already_done
# ---------------------------------------------------------------------------


def test_run_idempotent_when_marker_exists(
    tmp_path: Path, fake_run: _FakeRun, no_sleep, tmp_marker: Path
):
    tmp_marker.parent.mkdir(parents=True, exist_ok=True)
    tmp_marker.write_text("pre-existing marker\n", encoding="utf-8")

    result = run(marker_path=tmp_marker)

    assert result.already_done is True
    assert result.issues_closed == []
    assert result.marker_written is False
    # No subprocess calls at all
    assert fake_run.calls == []


# ---------------------------------------------------------------------------
# 4. --force overrides the marker
# ---------------------------------------------------------------------------


def test_run_force_overrides_marker(
    tmp_path: Path, fake_run: _FakeRun, no_sleep, tmp_marker: Path
):
    tmp_marker.parent.mkdir(parents=True, exist_ok=True)
    tmp_marker.write_text("stale marker\n", encoding="utf-8")

    fake_run.register(
        "gh issue comment", [_ok_completed(["gh"]) for _ in ISSUE_NUMBERS]
    )
    fake_run.register(
        "gh issue close", [_ok_completed(["gh"]) for _ in ISSUE_NUMBERS]
    )

    result = run(force=True, marker_path=tmp_marker)

    assert result.already_done is False
    assert result.issues_closed == ISSUE_NUMBERS
    assert result.marker_written is True
    # Marker now contains the fresh closed-issues list
    body = tmp_marker.read_text(encoding="utf-8")
    assert "378" in body and "390" in body


# ---------------------------------------------------------------------------
# 5. Partial failure tolerance: 1 of 13 fails → other 12 closed; marker written
# ---------------------------------------------------------------------------


def test_run_partial_close_failure_continues_and_excludes_failures(
    tmp_path: Path, fake_run: _FakeRun, no_sleep, tmp_marker: Path
):
    # Issue index 5 (i.e., #383) fails on the comment step. The
    # remaining issues should still get their comment + close pair.
    comment_route: list[Any] = []
    close_route: list[Any] = []
    for idx, _n in enumerate(ISSUE_NUMBERS):
        if idx == 5:
            comment_route.append(
                subprocess.CalledProcessError(
                    returncode=1,
                    cmd=["gh", "issue", "comment"],
                    stderr="not found",
                )
            )
            # No close call for the failing issue.
        else:
            comment_route.append(_ok_completed(["gh"]))
            close_route.append(_ok_completed(["gh"]))

    fake_run.register("gh issue comment", comment_route)
    fake_run.register("gh issue close", close_route)

    result = run(marker_path=tmp_marker)

    # 12 of 13 succeeded; #383 was skipped
    expected = [n for idx, n in enumerate(ISSUE_NUMBERS) if idx != 5]
    assert result.issues_closed == expected
    assert len(result.issues_closed) == 12
    assert result.marker_written is True
    # Marker should record only the issues that actually closed
    body = tmp_marker.read_text(encoding="utf-8")
    fields = {}
    for line in body.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fields[k.strip()] = v.strip()
    closed_in_marker = json.loads(fields["closed_issues"])
    assert sorted(closed_in_marker) == sorted(expected)
    assert 383 not in closed_in_marker


# ---------------------------------------------------------------------------
# 6. Total gh failure → exit 1
# ---------------------------------------------------------------------------


def test_main_returns_1_when_all_gh_close_attempts_fail(
    tmp_path: Path, fake_run: _FakeRun, no_sleep, tmp_marker: Path
):
    # Every comment call fails — _close_all_issues skips each issue.
    fake_run.register(
        "gh issue comment",
        [
            subprocess.CalledProcessError(
                returncode=1, cmd=["gh", "issue", "comment"], stderr="rate-limited"
            )
            for _ in ISSUE_NUMBERS
        ],
    )
    # No close calls should happen since all comments fail.

    rc = main([])

    assert rc == 1
    assert not tmp_marker.exists()


# ---------------------------------------------------------------------------
# 7. Marker write failure → exit 2
# ---------------------------------------------------------------------------


def test_main_returns_2_on_marker_write_failure(
    tmp_path: Path, fake_run: _FakeRun, no_sleep, monkeypatch
):
    fake_run.register(
        "gh issue comment", [_ok_completed(["gh"]) for _ in ISSUE_NUMBERS]
    )
    fake_run.register(
        "gh issue close", [_ok_completed(["gh"]) for _ in ISSUE_NUMBERS]
    )

    # Point MARKER_PATH at a location that will fail on parent.mkdir
    # (use an existing file as the parent — mkdir(parents=True) raises
    # NotADirectoryError, a subclass of OSError).
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    bad_marker = blocker / "subdir" / "cleanup-391.done"
    monkeypatch.setattr(cleanup_391, "MARKER_PATH", bad_marker)

    rc = main([])

    assert rc == 2


# ---------------------------------------------------------------------------
# 8. Marker contents schema (all closed issue numbers present)
# ---------------------------------------------------------------------------


def test_marker_contents_are_well_formed(
    tmp_path: Path, fake_run: _FakeRun, no_sleep, tmp_marker: Path
):
    fake_run.register(
        "gh issue comment", [_ok_completed(["gh"]) for _ in ISSUE_NUMBERS]
    )
    fake_run.register(
        "gh issue close", [_ok_completed(["gh"]) for _ in ISSUE_NUMBERS]
    )

    run(marker_path=tmp_marker)

    body = tmp_marker.read_text(encoding="utf-8")
    # Parse line-by-line so we don't depend on exact whitespace.
    fields = {}
    for line in body.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fields[k.strip()] = v.strip()

    assert fields["mission"] == MISSION_SLUG
    assert fields["mission_id"] == MISSION_ID
    assert "run_at_utc" in fields
    # run_at_utc looks like an ISO 8601 Z-suffixed string
    assert fields["run_at_utc"].endswith("Z")
    assert "T" in fields["run_at_utc"]
    # closed_issues is a JSON-encoded list of the closed issue numbers
    closed = json.loads(fields["closed_issues"])
    assert sorted(closed) == sorted(ISSUE_NUMBERS)
    # All 13 artifact issues are present
    assert len(closed) == 13
    assert 378 in closed and 390 in closed


# ---------------------------------------------------------------------------
# 9. Polite rate-limit spacing: time.sleep called with GH_RATE_DELAY_SECONDS
# ---------------------------------------------------------------------------


def test_polite_rate_limit_spacing_between_gh_calls(
    tmp_path: Path, fake_run: _FakeRun, monkeypatch: pytest.MonkeyPatch, tmp_marker: Path
):
    sleeper = mock.MagicMock()
    monkeypatch.setattr(cleanup_391.time, "sleep", sleeper)

    fake_run.register(
        "gh issue comment", [_ok_completed(["gh"]) for _ in ISSUE_NUMBERS]
    )
    fake_run.register(
        "gh issue close", [_ok_completed(["gh"]) for _ in ISSUE_NUMBERS]
    )

    run(marker_path=tmp_marker)

    # Each successful close fires 2 sleeps (after comment, after close).
    # With 13 successful issues that's 26 sleeps total.
    assert sleeper.call_count == 26
    # All sleeps use the polite delay constant.
    for call in sleeper.call_args_list:
        args, _kwargs = call
        assert args == (GH_RATE_DELAY_SECONDS,)


# ---------------------------------------------------------------------------
# 10. CLI exit codes
# ---------------------------------------------------------------------------


def test_main_returns_0_on_happy_path(
    tmp_path: Path, fake_run: _FakeRun, no_sleep, tmp_marker: Path
):
    fake_run.register(
        "gh issue comment", [_ok_completed(["gh"]) for _ in ISSUE_NUMBERS]
    )
    fake_run.register(
        "gh issue close", [_ok_completed(["gh"]) for _ in ISSUE_NUMBERS]
    )

    rc = main([])

    assert rc == 0
    assert tmp_marker.exists()


def test_main_returns_0_on_idempotent_no_op(
    tmp_path: Path, fake_run: _FakeRun, tmp_marker: Path
):
    tmp_marker.parent.mkdir(parents=True, exist_ok=True)
    tmp_marker.write_text("already-done\n", encoding="utf-8")

    rc = main([])

    assert rc == 0
    # Marker untouched
    assert tmp_marker.read_text(encoding="utf-8") == "already-done\n"


def test_main_returns_3_on_bad_flag(capsys):
    rc = main(["--unknown-flag"])
    assert rc == 3
    captured = capsys.readouterr()
    # Error printed to stderr
    assert "error:" in captured.err or "unrecognized" in captured.err.lower()


def test_main_help_exits_0(capsys):
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "--dry-run" in out
    assert "--force" in out


# ---------------------------------------------------------------------------
# 11. Helper-level coverage: _close_issue posts a comment then closes
# ---------------------------------------------------------------------------


def test_close_issue_posts_comment_then_closes(fake_run: _FakeRun, no_sleep):
    fake_run.register("gh issue comment", _ok_completed(["gh"]))
    fake_run.register("gh issue close", _ok_completed(["gh"]))

    _close_issue(378, "test comment body")

    assert len(fake_run.calls) == 2
    comment_cmd = fake_run.calls[0]
    close_cmd = fake_run.calls[1]
    assert comment_cmd[:3] == ["gh", "issue", "comment"]
    assert "378" in comment_cmd
    assert "test comment body" in comment_cmd
    assert close_cmd[:3] == ["gh", "issue", "close"]
    assert "378" in close_cmd
    # Two sleeps total (one after comment, one after close).
    assert no_sleep.call_count == 2


# ---------------------------------------------------------------------------
# 12. _marker_exists default + override
# ---------------------------------------------------------------------------


def test_marker_exists_default_uses_module_constant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    marker = tmp_path / "default-marker.done"
    monkeypatch.setattr(cleanup_391, "MARKER_PATH", marker)
    assert _marker_exists() is False
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("x", encoding="utf-8")
    assert _marker_exists() is True


def test_marker_exists_with_override(tmp_path: Path):
    marker = tmp_path / "override.done"
    assert _marker_exists(marker) is False
    marker.write_text("x", encoding="utf-8")
    assert _marker_exists(marker) is True


# ---------------------------------------------------------------------------
# 13. _write_marker is atomic (tempfile + rename); contents survive
# ---------------------------------------------------------------------------


def test_write_marker_is_atomic_no_tempfile_left_behind(tmp_path: Path):
    marker = tmp_path / "atomic-marker.done"
    _write_marker(closed_issues=[378, 379], dry_run=False, marker_path=marker)

    assert marker.exists()
    # No stray ".tmp" file left behind by tempfile + rename.
    leftover = [p for p in tmp_path.iterdir() if p.name != marker.name]
    assert leftover == []


def test_write_marker_dry_run_makes_no_filesystem_changes(tmp_path: Path):
    marker = tmp_path / "would-not-write.done"
    result = _write_marker(
        closed_issues=[378], dry_run=True, marker_path=marker
    )
    assert result is True
    assert not marker.exists()


def test_write_marker_cleanup_on_rename_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """If os.replace fails, the temporary file is unlinked."""
    marker = tmp_path / "fail-marker.done"

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(cleanup_391.os, "replace", boom)

    with pytest.raises(OSError):
        _write_marker(closed_issues=[378], dry_run=False, marker_path=marker)

    # No stray .tmp file
    leftovers = list(tmp_path.iterdir())
    assert leftovers == []


# ---------------------------------------------------------------------------
# 14. _close_all_issues dry-run path
# ---------------------------------------------------------------------------


def test_close_all_issues_dry_run_returns_empty(fake_run: _FakeRun, no_sleep):
    # No routes — dry-run must not invoke subprocess.run.
    result = _close_all_issues(ISSUE_NUMBERS, dry_run=True)
    assert result == []
    assert fake_run.calls == []


# ---------------------------------------------------------------------------
# 15. Verify _close_issue invocation passes correct gh args
# ---------------------------------------------------------------------------


def test_close_issue_passes_repo_and_body(fake_run: _FakeRun, no_sleep):
    """Both gh sub-calls receive --repo and the comment passes --body."""
    fake_run.register("gh issue comment", _ok_completed(["gh"]))
    fake_run.register("gh issue close", _ok_completed(["gh"]))

    _close_issue(378, COMMENT_BODY)

    comment_cmd = fake_run.calls[0]
    close_cmd = fake_run.calls[1]
    # --repo present in both
    assert "--repo" in comment_cmd
    assert comment_cmd[comment_cmd.index("--repo") + 1] == REPO
    assert "--repo" in close_cmd
    assert close_cmd[close_cmd.index("--repo") + 1] == REPO
    # --body present on the comment call
    assert "--body" in comment_cmd
    assert comment_cmd[comment_cmd.index("--body") + 1] == COMMENT_BODY
