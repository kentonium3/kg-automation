"""Race-immune fast-forward of the shared office2 checkout (#667).

The historical failure ``fatal: Cannot fast-forward to multiple branches`` came
from two systemd-timed actors (``felix-deployer`` and ``agent-prompt-sync``)
concurrently writing the single shared ``.git/FETCH_HEAD`` and then merging from
it. This module structurally eliminates that race: it fetches, then merges the
atomic remote-tracking **ref** ``origin/main`` — never ``.git/FETCH_HEAD``.

``git fetch`` updates ``refs/remotes/origin/main`` under git's own per-ref
lockfile, so a concurrent fetch can never leave that ref in a multi-head state;
``git merge --ff-only origin/main`` then reads exactly one commit. The shared
``deploylock`` (WP02) still bounds the wider actor-level critical section, but the
FETCH_HEAD race is gone even before the lock.

See ``kitty-specs/prompt-sync-ff-race-01KX3SZC/contracts/lib-api.md`` (authoritative
contract), ``research.md`` D1 (divergence logic), and ``data-model.md``
(``AdvanceResult`` invariants).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

GitRunner = Callable[[list[str]], subprocess.CompletedProcess]

_STDERR_MAX = 200


@dataclass(frozen=True)
class AdvanceResult:
    """Immutable outcome of :func:`advance_checkout`.

    Invariants (enforced at construction):
      * ``ok`` is False iff ``reason`` is set.
      * ``advanced`` implies ``post_head != pre_head``.
      * ``diverged`` implies ``not advanced`` and ``reason == "diverged"``.
      * A clean no-op ⇒ ``ok=True, advanced=False, behind == 0`` (regardless of
        ``ahead`` — an actor's own unpushed commits are not divergence).
      * ``lock_unavailable`` is a benign defer, not a failure for health purposes.
    """

    ok: bool
    advanced: bool
    pre_head: str
    post_head: str
    origin_head: str
    behind: int
    ahead: int
    diverged: bool
    reason: str | None = None  # diverged|fetch_failed|lock_unavailable|merge_failed
    stderr: str = ""

    def __post_init__(self) -> None:
        # ok is False iff reason is set.
        if self.ok == (self.reason is not None):
            raise ValueError(
                f"AdvanceResult invariant violated: ok={self.ok!r} with "
                f"reason={self.reason!r} (ok must be False iff reason is set)"
            )
        if self.advanced and self.post_head == self.pre_head:
            raise ValueError(
                "AdvanceResult invariant violated: advanced=True but "
                "post_head == pre_head"
            )
        if self.diverged:
            if self.advanced:
                raise ValueError(
                    "AdvanceResult invariant violated: diverged=True with "
                    "advanced=True"
                )
            if self.reason != "diverged":
                raise ValueError(
                    "AdvanceResult invariant violated: diverged=True requires "
                    f'reason == "diverged" (got {self.reason!r})'
                )


def _default_git_runner(repo_root: Path) -> GitRunner:
    """Return a git runner that mirrors the actors' ``_git``/``git_pull`` seams."""

    def _runner(args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(  # noqa: S603 - argv list, no shell
            ["git", *args],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )

    return _runner


def _short_sha(runner: GitRunner, rev: str) -> str:
    """Short SHA for *rev*, or "" if it cannot be resolved."""
    proc = runner(["rev-parse", "--short", rev])
    if proc.returncode != 0:
        return ""
    return (proc.stdout or "").strip()


def _count(runner: GitRunner, range_expr: str) -> int:
    """``git rev-list --count`` for *range_expr*, or 0 if it cannot be resolved."""
    proc = runner(["rev-list", "--count", range_expr])
    if proc.returncode != 0:
        return 0
    try:
        return int((proc.stdout or "").strip() or "0")
    except ValueError:
        return 0


def _truncate(text: str | None) -> str:
    return (text or "").strip()[:_STDERR_MAX]


def advance_checkout(
    repo_root: Path,
    *,
    remote: str = "origin",
    branch: str = "main",
    assume_locked: bool = False,
    lock_path: Path | None = None,
    git_runner: GitRunner | None = None,
) -> AdvanceResult:
    """Race-immune fast-forward of *repo_root* to ``<remote>/<branch>``.

    Merge target is the remote-tracking **ref** ``<remote>/<branch>`` — never
    ``.git/FETCH_HEAD``. See the module docstring and the mission contract for
    the full rationale.

    When ``assume_locked`` is False, the shared ``deploylock`` (WP02) is acquired
    lazily around the whole operation; on timeout the result is a benign defer
    (``reason="lock_unavailable"``), not an exception. When True, the caller
    already holds the lock at the actor level and this runs inside it.

    Never raises for expected git failures — fetch/merge non-zero exit codes map
    to ``reason``.
    """
    runner = git_runner if git_runner is not None else _default_git_runner(repo_root)

    if not assume_locked:
        # Lazy import: deploylock is built by a sibling WP and may not exist yet
        # in this worktree. Importing here keeps the module importable (and tests
        # that pass assume_locked=True or inject git_runner runnable) without it.
        try:
            from scripts.deploy.lib.deploylock import (  # noqa: PLC0415
                LockUnavailable,
                deploylock,
            )
        except ImportError:
            return _lock_unavailable(runner, remote, branch)

        try:
            with deploylock(lock_path):
                return _advance_locked(runner, remote, branch)
        except LockUnavailable:
            return _lock_unavailable(runner, remote, branch)

    return _advance_locked(runner, remote, branch)


def _lock_unavailable(runner: GitRunner, remote: str, branch: str) -> AdvanceResult:
    """Benign-defer result when the shared lock could not be acquired."""
    pre = _short_sha(runner, "HEAD")
    origin = _short_sha(runner, f"{remote}/{branch}")
    return AdvanceResult(
        ok=False,
        advanced=False,
        pre_head=pre,
        post_head=pre,
        origin_head=origin,
        behind=0,
        ahead=0,
        diverged=False,
        reason="lock_unavailable",
    )


def _advance_locked(runner: GitRunner, remote: str, branch: str) -> AdvanceResult:
    """The fetch → divergence-check → ff-merge body (lock already held/skipped)."""
    pre_head = _short_sha(runner, "HEAD")

    # 1. Fetch. Updates refs/remotes/<remote>/<branch> atomically (per-ref lock).
    fetch = runner(["fetch", remote, branch])
    if fetch.returncode != 0:
        return AdvanceResult(
            ok=False,
            advanced=False,
            pre_head=pre_head,
            post_head=pre_head,
            origin_head="",
            behind=0,
            ahead=0,
            diverged=False,
            reason="fetch_failed",
            stderr=_truncate(fetch.stderr),
        )

    ref = f"{remote}/{branch}"
    origin_head = _short_sha(runner, ref)
    behind = _count(runner, f"HEAD..{ref}")
    ahead = _count(runner, f"{ref}..HEAD")

    # 2. behind == 0 → clean no-op regardless of ahead (unpushed commits are fine).
    if behind == 0:
        return AdvanceResult(
            ok=True,
            advanced=False,
            pre_head=pre_head,
            post_head=pre_head,
            origin_head=origin_head,
            behind=0,
            ahead=ahead,
            diverged=False,
        )

    # 3. behind > 0 AND ahead > 0 → true divergence: do NOT merge.
    if ahead > 0:
        return AdvanceResult(
            ok=False,
            advanced=False,
            pre_head=pre_head,
            post_head=pre_head,
            origin_head=origin_head,
            behind=behind,
            ahead=ahead,
            diverged=True,
            reason="diverged",
        )

    # 4. behind > 0, ahead == 0 → fast-forward via the ref (NEVER FETCH_HEAD).
    merge = runner(["merge", "--ff-only", ref])
    if merge.returncode != 0:
        post_head = _short_sha(runner, "HEAD")
        return AdvanceResult(
            ok=False,
            advanced=False,
            pre_head=pre_head,
            post_head=post_head,
            origin_head=origin_head,
            behind=behind,
            ahead=ahead,
            diverged=False,
            reason="merge_failed",
            stderr=_truncate(merge.stderr),
        )

    post_head = _short_sha(runner, "HEAD")
    return AdvanceResult(
        ok=True,
        advanced=True,
        pre_head=pre_head,
        post_head=post_head,
        origin_head=origin_head,
        behind=behind,
        ahead=ahead,
        diverged=False,
    )
