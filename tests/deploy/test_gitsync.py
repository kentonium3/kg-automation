"""Tests for :mod:`scripts.deploy.lib.gitsync`.

Two flavors:
  * real temp git repos (with a real ``origin`` remote) exercise the fetch/merge
    ref plumbing and the concurrency guarantee;
  * a recording fake ``git_runner`` exercises the branch logic, argv assertions
    (merge target is ``origin/main`` — never FETCH_HEAD), and reason mapping
    without needing a real repo.
"""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path

import pytest

from scripts.deploy.lib.gitsync import AdvanceResult, advance_checkout


# --------------------------------------------------------------------------- #
# Real temp-git helpers
# --------------------------------------------------------------------------- #
def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    return proc


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test")
    _git(path, "config", "commit.gpgsign", "false")


def _commit(path: Path, filename: str, content: str, message: str) -> str:
    (path / filename).write_text(content, encoding="utf-8")
    _git(path, "add", filename)
    _git(path, "commit", "-q", "-m", message)
    return _git(path, "rev-parse", "HEAD").stdout.strip()


@pytest.fixture()
def origin_and_clone(tmp_path: Path) -> tuple[Path, Path]:
    """A bare ``origin`` seeded with one commit, plus a working clone of it."""
    upstream = tmp_path / "upstream"
    _init_repo(upstream)
    _commit(upstream, "file.txt", "v1\n", "initial")

    origin = tmp_path / "origin.git"
    _git(tmp_path, "clone", "-q", "--bare", str(upstream), str(origin))

    clone = tmp_path / "clone"
    _git(tmp_path, "clone", "-q", str(origin), str(clone))
    _git(clone, "config", "user.email", "test@example.com")
    _git(clone, "config", "user.name", "Test")
    _git(clone, "config", "commit.gpgsign", "false")
    return origin, clone


def _push_new_commit(origin: Path, tmp_path: Path, content: str) -> str:
    """Add a commit to ``origin/main`` via a throwaway working clone."""
    pusher = tmp_path / f"pusher-{content.strip()}"
    _git(tmp_path, "clone", "-q", str(origin), str(pusher))
    _git(pusher, "config", "user.email", "test@example.com")
    _git(pusher, "config", "user.name", "Test")
    _git(pusher, "config", "commit.gpgsign", "false")
    sha = _commit(pusher, "file.txt", content, f"upstream {content.strip()}")
    _git(pusher, "push", "-q", "origin", "main")
    return sha


# --------------------------------------------------------------------------- #
# Recording fake runner
# --------------------------------------------------------------------------- #
class FakeGit:
    """Records argv and returns scripted results keyed by argv prefix."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self._short = {"HEAD": "aaaaaaa", "origin/main": "bbbbbbb"}
        self._counts = {"HEAD..origin/main": 0, "origin/main..HEAD": 0}
        self._fetch_rc = 0
        self._fetch_stderr = ""
        self._merge_rc = 0
        self._merge_stderr = ""
        self._head_after_merge = "bbbbbbb"
        self._merged = False

    def set_state(self, *, behind: int, ahead: int) -> None:
        self._counts["HEAD..origin/main"] = behind
        self._counts["origin/main..HEAD"] = ahead

    def fail_fetch(self, stderr: str) -> None:
        self._fetch_rc = 1
        self._fetch_stderr = stderr

    def fail_merge(self, stderr: str) -> None:
        self._merge_rc = 1
        self._merge_stderr = stderr

    def _cp(self, rc: int, out: str = "", err: str = "") -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(args=["git"], returncode=rc, stdout=out, stderr=err)

    def __call__(self, args: list[str]) -> subprocess.CompletedProcess:
        self.calls.append(args)
        if args[:1] == ["fetch"]:
            return self._cp(self._fetch_rc, err=self._fetch_stderr)
        if args[:2] == ["rev-parse", "--short"]:
            rev = args[2]
            # Local HEAD moves to the post-merge SHA only after a successful merge.
            if rev == "HEAD" and self._merged:
                return self._cp(0, out=self._head_after_merge + "\n")
            return self._cp(0, out=self._short.get(rev, "0000000") + "\n")
        if args[:2] == ["rev-list", "--count"]:
            return self._cp(0, out=f"{self._counts.get(args[2], 0)}\n")
        if args[:1] == ["merge"]:
            if self._merge_rc == 0:
                self._merged = True
            return self._cp(self._merge_rc, err=self._merge_stderr)
        return self._cp(0)

    def merge_calls(self) -> list[list[str]]:
        return [c for c in self.calls if c[:1] == ["merge"]]


# --------------------------------------------------------------------------- #
# Real-repo behavioral tests
# --------------------------------------------------------------------------- #
def test_fetch_updates_remote_tracking_ref(origin_and_clone, tmp_path):
    origin, clone = origin_and_clone
    new_sha = _push_new_commit(origin, tmp_path, "v2\n")

    # Before the advance, the clone's origin/main is stale.
    before = _git(clone, "rev-parse", "origin/main").stdout.strip()
    assert before != new_sha

    advance_checkout(clone, assume_locked=True)

    after = _git(clone, "rev-parse", "refs/remotes/origin/main").stdout.strip()
    assert after == new_sha


def test_fast_forward_advances_head(origin_and_clone, tmp_path):
    origin, clone = origin_and_clone
    new_sha = _push_new_commit(origin, tmp_path, "v2\n")

    result = advance_checkout(clone, assume_locked=True)

    assert result.ok is True
    assert result.advanced is True
    assert result.behind == 1
    assert result.ahead == 0
    assert result.post_head != result.pre_head
    assert _git(clone, "rev-parse", "HEAD").stdout.strip() == new_sha


def test_already_current_is_clean_noop(origin_and_clone):
    _, clone = origin_and_clone

    result = advance_checkout(clone, assume_locked=True)

    assert result.ok is True
    assert result.advanced is False
    assert result.behind == 0
    assert result.diverged is False
    assert result.pre_head == result.post_head


def test_ahead_only_is_noop_not_diverged(origin_and_clone):
    """ahead>0, behind==0 (unpushed local commits) is a clean no-op."""
    _, clone = origin_and_clone
    _commit(clone, "local.txt", "local\n", "local unpushed commit")

    result = advance_checkout(clone, assume_locked=True)

    assert result.ok is True
    assert result.advanced is False
    assert result.behind == 0
    assert result.ahead == 1
    assert result.diverged is False
    assert result.reason is None


def test_diverged_does_not_merge(origin_and_clone, tmp_path):
    """behind>0 AND ahead>0 → diverged, no merge, HEAD untouched."""
    origin, clone = origin_and_clone
    _push_new_commit(origin, tmp_path, "v2-upstream\n")
    local_sha = _commit(clone, "local.txt", "local\n", "local divergent commit")

    result = advance_checkout(clone, assume_locked=True)

    assert result.ok is False
    assert result.diverged is True
    assert result.reason == "diverged"
    assert result.advanced is False
    assert result.behind == 1
    assert result.ahead == 1
    # HEAD is unchanged — no merge was attempted.
    assert _git(clone, "rev-parse", "HEAD").stdout.strip() == local_sha


# --------------------------------------------------------------------------- #
# Fake-runner argv / mapping tests
# --------------------------------------------------------------------------- #
def test_merge_target_is_ref_never_fetch_head():
    fake = FakeGit()
    fake.set_state(behind=1, ahead=0)

    advance_checkout(Path("/nonexistent"), assume_locked=True, git_runner=fake)

    merges = fake.merge_calls()
    assert merges == [["merge", "--ff-only", "origin/main"]]
    # Explicitly: FETCH_HEAD is never on the merge path.
    assert all("FETCH_HEAD" not in " ".join(c) for c in fake.calls)


def test_custom_remote_branch_in_merge_argv():
    fake = FakeGit()
    fake._short = {"HEAD": "aaaaaaa", "up/dev": "bbbbbbb"}
    fake._counts = {"HEAD..up/dev": 2, "up/dev..HEAD": 0}

    advance_checkout(
        Path("/nonexistent"),
        remote="up",
        branch="dev",
        assume_locked=True,
        git_runner=fake,
    )

    assert fake.merge_calls() == [["merge", "--ff-only", "up/dev"]]
    assert ["fetch", "up", "dev"] in fake.calls


def test_fetch_failed_maps_reason_and_no_merge():
    fake = FakeGit()
    fake.fail_fetch("fatal: could not read from remote")

    result = advance_checkout(Path("/nonexistent"), assume_locked=True, git_runner=fake)

    assert result.ok is False
    assert result.reason == "fetch_failed"
    assert result.advanced is False
    assert fake.merge_calls() == []
    assert "could not read" in result.stderr


def test_merge_failed_maps_reason():
    fake = FakeGit()
    fake.set_state(behind=1, ahead=0)
    fake.fail_merge("fatal: Not possible to fast-forward")

    result = advance_checkout(Path("/nonexistent"), assume_locked=True, git_runner=fake)

    assert result.ok is False
    assert result.reason == "merge_failed"
    assert result.advanced is False
    assert "fast-forward" in result.stderr


def test_stderr_is_truncated():
    fake = FakeGit()
    fake.fail_fetch("x" * 500)

    result = advance_checkout(Path("/nonexistent"), assume_locked=True, git_runner=fake)

    assert len(result.stderr) == 200


# --------------------------------------------------------------------------- #
# AdvanceResult invariants
# --------------------------------------------------------------------------- #
def test_advance_result_ok_iff_no_reason():
    with pytest.raises(ValueError):
        AdvanceResult(
            ok=True, advanced=False, pre_head="a", post_head="a",
            origin_head="a", behind=0, ahead=0, diverged=False, reason="fetch_failed",
        )
    with pytest.raises(ValueError):
        AdvanceResult(
            ok=False, advanced=False, pre_head="a", post_head="a",
            origin_head="a", behind=0, ahead=0, diverged=False, reason=None,
        )


def test_advance_result_diverged_requires_reason():
    with pytest.raises(ValueError):
        AdvanceResult(
            ok=False, advanced=False, pre_head="a", post_head="a",
            origin_head="b", behind=1, ahead=1, diverged=True, reason="fetch_failed",
        )


# --------------------------------------------------------------------------- #
# Primitive concurrency guarantee (#667)
# --------------------------------------------------------------------------- #
def test_concurrent_advance_no_multiple_branches(origin_and_clone, tmp_path):
    """N concurrent advance_checkout against one real checkout → 0 "multiple
    branches" errors and a single consistent final HEAD.

    A stale extra origin branch is seeded to mimic the exact bare-fetch surface
    that used to clobber ``.git/FETCH_HEAD``; the ref-merge path must be immune to
    the historical ``Cannot fast-forward to multiple branches`` failure.

    This is the PRIMITIVE-level guarantee (necessary, not sufficient — the
    load-bearing actor-level proof is WP06). ``advance_checkout`` is called here
    with ``assume_locked=True``, i.e. WITHOUT the shared ``deploylock`` that the
    actors hold around their whole critical section. So concurrent unlocked merges
    on one worktree can still contend on ``.git/index.lock`` / the ``HEAD`` ref and
    return ``merge_failed`` (or lose the per-ref fetch race → ``fetch_failed``).
    Those are the exact benign, retry-next-tick outcomes ``deploylock`` (WP02)
    exists to serialize away — they are NOT the multi-branch race and they never
    corrupt the final HEAD. What must hold unconditionally: no "multiple branches"
    error, no divergence, and a consistent converged final HEAD.
    """
    origin, clone = origin_and_clone

    # Seed a stale extra branch on origin (the historical FETCH_HEAD amplifier).
    stale = tmp_path / "stale"
    _git(tmp_path, "clone", "-q", str(origin), str(stale))
    _git(stale, "config", "user.email", "test@example.com")
    _git(stale, "config", "user.name", "Test")
    _git(stale, "config", "commit.gpgsign", "false")
    _git(stale, "checkout", "-q", "-b", "stale/lane-a")
    _commit(stale, "stale.txt", "stale\n", "stale branch commit")
    _git(stale, "push", "-q", "origin", "stale/lane-a")

    target_sha = _push_new_commit(origin, tmp_path, "v2-concurrent\n")

    n = 24
    barrier = threading.Barrier(n)
    results: list[AdvanceResult] = []
    errors: list[str] = []
    lock = threading.Lock()

    def worker() -> None:
        barrier.wait()
        try:
            res = advance_checkout(clone, assume_locked=True)
        except Exception as exc:  # pragma: no cover - defensive
            with lock:
                errors.append(repr(exc))
            return
        with lock:
            results.append(res)

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert len(results) == n

    # The load-bearing guarantee: the ref-merge path NEVER produces the historical
    # "Cannot fast-forward to multiple branches" failure, no matter how many
    # actors fetch/merge the shared checkout concurrently.
    for res in results:
        assert "multiple branches" not in (res.stderr or "").lower()

    # No result ever DIVERGED — divergence means both sides moved, which this
    # single-upstream scenario can't produce. (merge_failed / fetch_failed from
    # unlocked index/ref contention ARE expected here — see docstring; they are
    # the benign defers deploylock serializes at the actor level.)
    for res in results:
        assert res.reason in (None, "fetch_failed", "merge_failed"), (
            f"unexpected result: {res}"
        )
        assert res.diverged is False
    # At least one actor won the race and observed real work / the clean state.
    assert any(res.ok for res in results)

    # Consistent final HEAD — every actor converges the checkout to origin/main.
    final = _git(clone, "rev-parse", "HEAD").stdout.strip()
    assert final == target_sha
