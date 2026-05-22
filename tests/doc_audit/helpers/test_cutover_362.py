"""Unit tests for ``scripts/doc_audit/helpers/cutover_362.py`` (WP05).

The cutover script is a one-shot operator tool — these tests verify
the contract documented in ``contracts/cli.md`` and
``contracts/api.md`` without making real GitHub API calls or writing
to the operator's real ``~/.config/doc-audit`` directory.

All subprocess calls (``gh issue list``, ``gh issue comment``, ``gh
issue close``, ``python3 -m handle_drift_events --reset-cursor``) are
patched at the ``subprocess.run`` boundary. Marker writes go to
``tmp_path`` via the ``marker_path`` override parameter so we can
assert on file contents without touching ``$HOME``.

Test coverage targets the WP prompt's nine scenarios plus marker
contents verification and polite rate-limit timing — eleven test
functions total.
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
from doc_audit.helpers import cutover_362
from doc_audit.helpers.cutover_362 import (
    COMMENT_BODY,
    CutoverResult,
    GH_QUERY,
    GH_RATE_DELAY_SECONDS,
    MISSION_ID,
    MISSION_SLUG,
    REPO,
    _close_all_issues,
    _close_issue,
    _list_open_issues,
    _marker_exists,
    _reset_cursor,
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
    sub-commands (``"gh issue list"``, ``"gh issue comment"``,
    ``"gh issue close"``) or on the python module invocation
    (``"python3 -m handle_drift_events"``). Unregistered calls raise
    AssertionError so tests fail loudly if the code under test ever
    shells out to something we didn't anticipate.

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
            # "gh issue list" / "gh issue comment" / "gh issue close"
            return " ".join(cmd[:3])
        if cmd[0] == "python3" and len(cmd) >= 3 and cmd[1] == "-m":
            return "python3 -m handle_drift_events"
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


def _gh_list_response(issue_numbers: list[int]) -> subprocess.CompletedProcess:
    payload = json.dumps([{"number": n} for n in issue_numbers])
    return subprocess.CompletedProcess(
        args=["gh", "issue", "list"], returncode=0, stdout=payload, stderr=""
    )


@pytest.fixture
def fake_run(monkeypatch: pytest.MonkeyPatch) -> _FakeRun:
    """Patch ``subprocess.run`` inside ``cutover_362`` with a routable fake."""
    fake = _FakeRun()
    monkeypatch.setattr(cutover_362.subprocess, "run", fake)
    return fake


@pytest.fixture
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> mock.MagicMock:
    """Patch ``time.sleep`` so tests don't wait the polite-rate delay."""
    sleeper = mock.MagicMock()
    monkeypatch.setattr(cutover_362.time, "sleep", sleeper)
    return sleeper


@pytest.fixture
def tmp_marker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Override the module-level MARKER_PATH to live under tmp_path.

    The implementation prefers explicit ``marker_path`` overrides in
    ``run()``/``_write_marker()``/``_marker_exists()``, but ``main()``
    has no such hook — patching the module constant covers that path.
    """
    marker = tmp_path / "cutover-362.done"
    monkeypatch.setattr(cutover_362, "MARKER_PATH", marker)
    return marker


# ---------------------------------------------------------------------------
# 1. Happy path: 5 open issues → closed → cursor reset → marker written
# ---------------------------------------------------------------------------


def test_run_happy_path_closes_all_issues_and_writes_marker(
    tmp_path: Path, fake_run: _FakeRun, no_sleep, tmp_marker: Path
):
    issue_numbers = [351, 352, 353, 354, 355]
    fake_run.register("gh issue list", _gh_list_response(issue_numbers))
    fake_run.register(
        "gh issue comment",
        [_ok_completed(["gh"]) for _ in issue_numbers],
    )
    fake_run.register(
        "gh issue close",
        [_ok_completed(["gh"]) for _ in issue_numbers],
    )
    fake_run.register("python3 -m handle_drift_events", _ok_completed(["python3"]))

    result = run(marker_path=tmp_marker)

    assert isinstance(result, CutoverResult)
    assert result.issues_closed == issue_numbers
    assert result.cursor_reset is True
    assert result.marker_written is True
    assert result.dry_run is False
    assert result.already_done is False
    # Marker file exists and contains the expected fields
    assert tmp_marker.exists()
    body = tmp_marker.read_text(encoding="utf-8")
    assert MISSION_SLUG in body
    assert MISSION_ID in body
    assert "cursor_reset_to: 0" in body
    assert "351" in body and "355" in body


# ---------------------------------------------------------------------------
# 2. Dry-run: list query happens but no mutations
# ---------------------------------------------------------------------------


def test_run_dry_run_makes_no_mutations(
    tmp_path: Path, fake_run: _FakeRun, no_sleep, tmp_marker: Path
):
    issue_numbers = [351, 352, 353]
    fake_run.register("gh issue list", _gh_list_response(issue_numbers))

    result = run(dry_run=True, marker_path=tmp_marker)

    assert result.dry_run is True
    assert result.issues_closed == []  # nothing actually closed
    assert result.cursor_reset is True  # "would reset"
    assert result.marker_written is True  # "would write"
    assert result.already_done is False
    # No marker file on disk
    assert not tmp_marker.exists()
    # No gh issue comment / close / python3 -m calls were made
    cmds = [c[0:3] for c in fake_run.calls]
    assert ["gh", "issue", "list"] in cmds
    assert ["gh", "issue", "comment"] not in cmds
    assert ["gh", "issue", "close"] not in cmds
    assert not any(c[0] == "python3" for c in fake_run.calls)


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
    assert result.cursor_reset is False
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

    issue_numbers = [368, 369]
    fake_run.register("gh issue list", _gh_list_response(issue_numbers))
    fake_run.register(
        "gh issue comment", [_ok_completed(["gh"]) for _ in issue_numbers]
    )
    fake_run.register(
        "gh issue close", [_ok_completed(["gh"]) for _ in issue_numbers]
    )
    fake_run.register("python3 -m handle_drift_events", _ok_completed(["python3"]))

    result = run(force=True, marker_path=tmp_marker)

    assert result.already_done is False
    assert result.issues_closed == issue_numbers
    assert result.marker_written is True
    # Marker now contains the fresh closed-issues list
    body = tmp_marker.read_text(encoding="utf-8")
    assert "368" in body and "369" in body


# ---------------------------------------------------------------------------
# 5. gh issue list failure → main() returns exit 1
# ---------------------------------------------------------------------------


def test_main_returns_1_on_gh_list_failure(
    tmp_path: Path, fake_run: _FakeRun, no_sleep, tmp_marker: Path
):
    fake_run.register(
        "gh issue list",
        subprocess.CalledProcessError(
            returncode=1,
            cmd=["gh", "issue", "list"],
            stderr="rate-limited",
        ),
    )

    rc = main([])

    assert rc == 1
    assert not tmp_marker.exists()


# ---------------------------------------------------------------------------
# 6. Partial gh close failure: one issue fails, others succeed
# ---------------------------------------------------------------------------


def test_run_partial_close_failure_continues_and_excludes_failures(
    tmp_path: Path, fake_run: _FakeRun, no_sleep, tmp_marker: Path
):
    issue_numbers = [351, 352, 353, 354, 355]
    fake_run.register("gh issue list", _gh_list_response(issue_numbers))
    # Issue 353 (third in the list) fails on the comment step. The
    # remaining issues should still get their comment + close pair.
    comment_route: list[Any] = [
        _ok_completed(["gh"]),  # 351
        _ok_completed(["gh"]),  # 352
        subprocess.CalledProcessError(
            returncode=1, cmd=["gh", "issue", "comment"], stderr="not found"
        ),  # 353 fails
        _ok_completed(["gh"]),  # 354
        _ok_completed(["gh"]),  # 355
    ]
    close_route: list[Any] = [
        _ok_completed(["gh"]),  # 351
        _ok_completed(["gh"]),  # 352
        # 353 skipped (comment failure short-circuited it)
        _ok_completed(["gh"]),  # 354
        _ok_completed(["gh"]),  # 355
    ]
    fake_run.register("gh issue comment", comment_route)
    fake_run.register("gh issue close", close_route)
    fake_run.register("python3 -m handle_drift_events", _ok_completed(["python3"]))

    result = run(marker_path=tmp_marker)

    # 351, 352, 354, 355 succeeded; 353 was skipped
    assert result.issues_closed == [351, 352, 354, 355]
    assert result.cursor_reset is True
    assert result.marker_written is True
    # Marker should record only the issues that actually closed
    body = tmp_marker.read_text(encoding="utf-8")
    assert "351" in body and "352" in body
    assert "354" in body and "355" in body
    # 353 must NOT appear in the closed_issues line
    assert "[351, 352, 354, 355]" in body


# ---------------------------------------------------------------------------
# 7. Cursor reset failure → main() returns exit 2
# ---------------------------------------------------------------------------


def test_main_returns_2_on_cursor_reset_failure(
    tmp_path: Path, fake_run: _FakeRun, no_sleep, tmp_marker: Path
):
    issue_numbers = [351]
    fake_run.register("gh issue list", _gh_list_response(issue_numbers))
    fake_run.register("gh issue comment", _ok_completed(["gh"]))
    fake_run.register("gh issue close", _ok_completed(["gh"]))
    fake_run.register(
        "python3 -m handle_drift_events",
        subprocess.CalledProcessError(
            returncode=1,
            cmd=["python3", "-m", "scripts.doc_audit.helpers.handle_drift_events"],
            stderr="cursor write failed",
        ),
    )

    rc = main([])

    assert rc == 2
    # Marker should not be written if cursor reset failed
    assert not tmp_marker.exists()


# ---------------------------------------------------------------------------
# 8. Marker write failure → main() returns exit 2
# ---------------------------------------------------------------------------


def test_main_returns_2_on_marker_write_failure(
    tmp_path: Path, fake_run: _FakeRun, no_sleep, monkeypatch
):
    issue_numbers = [351]
    fake_run.register("gh issue list", _gh_list_response(issue_numbers))
    fake_run.register("gh issue comment", _ok_completed(["gh"]))
    fake_run.register("gh issue close", _ok_completed(["gh"]))
    fake_run.register("python3 -m handle_drift_events", _ok_completed(["python3"]))

    # Point MARKER_PATH at a location that will fail on parent.mkdir
    # (use an existing file as the parent — mkdir(parents=True) raises
    # NotADirectoryError, a subclass of OSError).
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    bad_marker = blocker / "subdir" / "cutover-362.done"
    monkeypatch.setattr(cutover_362, "MARKER_PATH", bad_marker)

    rc = main([])

    assert rc == 2


# ---------------------------------------------------------------------------
# 9. Marker contents include mission, mission_id, run_at_utc, closed_issues
# ---------------------------------------------------------------------------


def test_marker_contents_are_well_formed(
    tmp_path: Path, fake_run: _FakeRun, no_sleep, tmp_marker: Path
):
    issue_numbers = [351, 352, 358]
    fake_run.register("gh issue list", _gh_list_response(issue_numbers))
    fake_run.register(
        "gh issue comment", [_ok_completed(["gh"]) for _ in issue_numbers]
    )
    fake_run.register(
        "gh issue close", [_ok_completed(["gh"]) for _ in issue_numbers]
    )
    fake_run.register("python3 -m handle_drift_events", _ok_completed(["python3"]))

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
    assert sorted(closed) == sorted(issue_numbers)
    assert fields["cursor_reset_to"] == "0"


# ---------------------------------------------------------------------------
# 10. Polite rate-limit spacing: time.sleep called with GH_RATE_DELAY_SECONDS
# ---------------------------------------------------------------------------


def test_polite_rate_limit_spacing_between_gh_calls(
    tmp_path: Path, fake_run: _FakeRun, monkeypatch: pytest.MonkeyPatch, tmp_marker: Path
):
    sleeper = mock.MagicMock()
    monkeypatch.setattr(cutover_362.time, "sleep", sleeper)

    issue_numbers = [351, 352]
    fake_run.register("gh issue list", _gh_list_response(issue_numbers))
    fake_run.register(
        "gh issue comment", [_ok_completed(["gh"]) for _ in issue_numbers]
    )
    fake_run.register(
        "gh issue close", [_ok_completed(["gh"]) for _ in issue_numbers]
    )
    fake_run.register("python3 -m handle_drift_events", _ok_completed(["python3"]))

    run(marker_path=tmp_marker)

    # Each successful close fires 2 sleeps (after comment, after close).
    # With 2 successful issues that's 4 sleeps total.
    assert sleeper.call_count >= 2  # at least one per issue
    # All sleeps use the polite delay constant.
    for call in sleeper.call_args_list:
        args, _kwargs = call
        assert args == (GH_RATE_DELAY_SECONDS,)


# ---------------------------------------------------------------------------
# 11. CLI exit-code surface: success, no-op, bad flag
# ---------------------------------------------------------------------------


def test_main_returns_0_on_happy_path(
    tmp_path: Path, fake_run: _FakeRun, no_sleep, tmp_marker: Path
):
    fake_run.register("gh issue list", _gh_list_response([351, 352]))
    fake_run.register(
        "gh issue comment", [_ok_completed(["gh"]) for _ in range(2)]
    )
    fake_run.register("gh issue close", [_ok_completed(["gh"]) for _ in range(2)])
    fake_run.register("python3 -m handle_drift_events", _ok_completed(["python3"]))

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
# 12. Helper-level coverage: _list_open_issues argument shape + parsing
# ---------------------------------------------------------------------------


def test_list_open_issues_uses_correct_gh_query(fake_run: _FakeRun, no_sleep):
    fake_run.register("gh issue list", _gh_list_response([351]))

    numbers = _list_open_issues()

    assert numbers == [351]
    # The gh invocation passed the canonical query + JSON projection.
    assert len(fake_run.calls) == 1
    cmd = fake_run.calls[0]
    assert "--search" in cmd
    search_idx = cmd.index("--search")
    assert cmd[search_idx + 1] == GH_QUERY
    assert "--json" in cmd
    assert "--repo" in cmd
    assert cmd[cmd.index("--repo") + 1] == REPO


def test_list_open_issues_raises_on_unparseable_json(fake_run: _FakeRun, no_sleep):
    fake_run.register(
        "gh issue list",
        subprocess.CompletedProcess(
            args=["gh", "issue", "list"], returncode=0,
            stdout="not-json", stderr="",
        ),
    )

    with pytest.raises(ValueError):
        _list_open_issues()


def test_list_open_issues_raises_on_non_list_payload(fake_run: _FakeRun, no_sleep):
    fake_run.register(
        "gh issue list",
        subprocess.CompletedProcess(
            args=["gh", "issue", "list"], returncode=0,
            stdout='{"number": 1}', stderr="",
        ),
    )

    with pytest.raises(ValueError):
        _list_open_issues()


def test_list_open_issues_raises_on_missing_number_field(fake_run: _FakeRun, no_sleep):
    fake_run.register(
        "gh issue list",
        subprocess.CompletedProcess(
            args=["gh", "issue", "list"], returncode=0,
            stdout='[{"title": "no number here"}]', stderr="",
        ),
    )

    with pytest.raises(ValueError):
        _list_open_issues()


# ---------------------------------------------------------------------------
# 13. Helper-level coverage: _close_issue posts a comment then closes
# ---------------------------------------------------------------------------


def test_close_issue_posts_comment_then_closes(fake_run: _FakeRun, no_sleep):
    fake_run.register("gh issue comment", _ok_completed(["gh"]))
    fake_run.register("gh issue close", _ok_completed(["gh"]))

    _close_issue(371, "test comment body")

    assert len(fake_run.calls) == 2
    comment_cmd = fake_run.calls[0]
    close_cmd = fake_run.calls[1]
    assert comment_cmd[:3] == ["gh", "issue", "comment"]
    assert "371" in comment_cmd
    assert "test comment body" in comment_cmd
    assert close_cmd[:3] == ["gh", "issue", "close"]
    assert "371" in close_cmd
    # Two sleeps total (one after comment, one after close).
    assert no_sleep.call_count == 2


# ---------------------------------------------------------------------------
# 14. _marker_exists default + override
# ---------------------------------------------------------------------------


def test_marker_exists_default_uses_module_constant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    marker = tmp_path / "default-marker.done"
    monkeypatch.setattr(cutover_362, "MARKER_PATH", marker)
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
# 15. _reset_cursor dry-run: no subprocess called
# ---------------------------------------------------------------------------


def test_reset_cursor_dry_run_makes_no_subprocess_call(fake_run: _FakeRun):
    # No route registered — would raise AssertionError if called.
    assert _reset_cursor(dry_run=True) is True
    assert fake_run.calls == []


def test_reset_cursor_passes_cursor_path_argument(
    fake_run: _FakeRun, monkeypatch: pytest.MonkeyPatch
):
    """WP04's --reset-cursor requires --cursor; cutover must pass it."""
    fake_run.register("python3 -m handle_drift_events", _ok_completed(["python3"]))
    # Stub config loader so we don't depend on real config.toml.
    monkeypatch.setattr(
        cutover_362, "_resolve_cursor_path", lambda: "/tmp/fake-cursor"
    )

    _reset_cursor(dry_run=False)

    assert len(fake_run.calls) == 1
    cmd = fake_run.calls[0]
    assert "--reset-cursor" in cmd
    assert "--cursor" in cmd
    assert cmd[cmd.index("--cursor") + 1] == "/tmp/fake-cursor"


# ---------------------------------------------------------------------------
# 16. _write_marker is atomic (tempfile + rename); contents survive
# ---------------------------------------------------------------------------


def test_write_marker_is_atomic_no_tempfile_left_behind(tmp_path: Path):
    marker = tmp_path / "atomic-marker.done"
    _write_marker(closed_issues=[351, 352], dry_run=False, marker_path=marker)

    assert marker.exists()
    # No stray ".tmp" file left behind by tempfile + rename.
    leftover = [p for p in tmp_path.iterdir() if p.name != marker.name]
    assert leftover == []


def test_write_marker_dry_run_makes_no_filesystem_changes(tmp_path: Path):
    marker = tmp_path / "would-not-write.done"
    result = _write_marker(
        closed_issues=[351], dry_run=True, marker_path=marker
    )
    assert result is True
    assert not marker.exists()


def test_write_marker_cleanup_on_rename_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """If os.replace fails, the temporary file is unlinked."""
    marker = tmp_path / "fail-marker.done"

    real_replace = os.replace

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(cutover_362.os, "replace", boom)

    with pytest.raises(OSError):
        _write_marker(closed_issues=[1], dry_run=False, marker_path=marker)

    # No stray .tmp file
    leftovers = list(tmp_path.iterdir())
    assert leftovers == []
    # Restore so other tests aren't affected (monkeypatch undoes anyway).
    monkeypatch.setattr(cutover_362.os, "replace", real_replace)


# ---------------------------------------------------------------------------
# 17. _close_all_issues dry-run path
# ---------------------------------------------------------------------------


def test_close_all_issues_dry_run_returns_empty(fake_run: _FakeRun, no_sleep):
    # No routes — dry-run must not invoke subprocess.run.
    result = _close_all_issues([351, 352, 353], dry_run=True)
    assert result == []
    assert fake_run.calls == []


# ---------------------------------------------------------------------------
# 18. COMMENT_BODY references mission + #362 + quickstart.md (review guidance)
# ---------------------------------------------------------------------------


def test_comment_body_references_mission_362_and_quickstart():
    formatted = COMMENT_BODY.format(mission_slug=MISSION_SLUG)
    assert MISSION_SLUG in formatted
    assert "#362" in formatted
    assert "quickstart.md" in formatted
