"""Tests for :mod:`scripts.deploy.lib.deploylock`."""

from __future__ import annotations

import fcntl
import os
import time

import pytest

from scripts.deploy.lib import deploylock as dl
from scripts.deploy.lib.deploylock import DEFAULT_LOCK_PATH, LockUnavailable, deploylock


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


def test_default_lock_path_is_neutral_shared_location():
    assert str(DEFAULT_LOCK_PATH) == "/data/services/deploy/locks/office2-checkout.lock"


def test_lock_unavailable_is_runtime_error():
    assert issubclass(LockUnavailable, RuntimeError)


# ---------------------------------------------------------------------------
# Acquire / release / re-acquire
# ---------------------------------------------------------------------------


def test_acquire_release_reacquire(tmp_path):
    lock_path = tmp_path / "checkout.lock"

    with deploylock(path=lock_path):
        pass  # acquired then released on exit

    # Re-acquisition after a clean release must succeed.
    with deploylock(path=lock_path):
        pass


def test_lock_file_is_created_on_acquire(tmp_path):
    lock_path = tmp_path / "checkout.lock"
    assert not lock_path.exists()

    with deploylock(path=lock_path):
        assert lock_path.exists()


# ---------------------------------------------------------------------------
# Contention → LockUnavailable within ~timeout
# ---------------------------------------------------------------------------


def test_contended_acquire_raises_lock_unavailable(tmp_path):
    lock_path = tmp_path / "checkout.lock"

    # Pre-hold the flock on the same path via a separate fd (simulates the other
    # actor mid-critical-section).
    holder_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    fcntl.flock(holder_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        with pytest.raises(LockUnavailable):
            with deploylock(path=lock_path, timeout_s=0.2):
                pass  # pragma: no cover — never entered
    finally:
        fcntl.flock(holder_fd, fcntl.LOCK_UN)
        os.close(holder_fd)


def test_contended_acquire_respects_timeout_bound(tmp_path):
    lock_path = tmp_path / "checkout.lock"

    holder_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    fcntl.flock(holder_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        timeout_s = 0.3
        start = time.monotonic()
        with pytest.raises(LockUnavailable):
            with deploylock(path=lock_path, timeout_s=timeout_s):
                pass  # pragma: no cover — never entered
        elapsed = time.monotonic() - start
        # Bounded: must give up near the timeout, never block unboundedly.
        assert timeout_s <= elapsed < timeout_s + 1.0
    finally:
        fcntl.flock(holder_fd, fcntl.LOCK_UN)
        os.close(holder_fd)


def test_lock_reusable_after_contended_holder_releases(tmp_path):
    lock_path = tmp_path / "checkout.lock"

    holder_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    fcntl.flock(holder_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    with pytest.raises(LockUnavailable):
        with deploylock(path=lock_path, timeout_s=0.1):
            pass  # pragma: no cover — never entered

    # Holder releases; the lock must now be acquirable.
    fcntl.flock(holder_fd, fcntl.LOCK_UN)
    os.close(holder_fd)

    with deploylock(path=lock_path, timeout_s=1.0):
        pass


# ---------------------------------------------------------------------------
# Path-resolution precedence: arg > env > default
# ---------------------------------------------------------------------------


def test_path_arg_takes_precedence_over_env(tmp_path, monkeypatch):
    arg_path = tmp_path / "from-arg.lock"
    env_path = tmp_path / "from-env.lock"
    monkeypatch.setenv("DEPLOY_CHECKOUT_LOCK", str(env_path))

    with deploylock(path=arg_path):
        assert arg_path.exists()
        assert not env_path.exists()


def test_env_used_when_no_arg(tmp_path, monkeypatch):
    env_path = tmp_path / "from-env.lock"
    monkeypatch.setenv("DEPLOY_CHECKOUT_LOCK", str(env_path))

    with deploylock():
        assert env_path.exists()


def test_default_used_when_no_arg_and_no_env(monkeypatch):
    monkeypatch.delenv("DEPLOY_CHECKOUT_LOCK", raising=False)
    # Resolve without acquiring (never touch the real /data path).
    assert dl._resolve_path(None) == DEFAULT_LOCK_PATH


# ---------------------------------------------------------------------------
# Parent-dir creation
# ---------------------------------------------------------------------------


def test_parent_dir_created_on_demand(tmp_path):
    lock_path = tmp_path / "nested" / "dirs" / "checkout.lock"
    assert not lock_path.parent.exists()

    with deploylock(path=lock_path):
        assert lock_path.parent.is_dir()
        assert lock_path.exists()


# ---------------------------------------------------------------------------
# Release on normal exit AND on exception
# ---------------------------------------------------------------------------


def _lock_is_free(lock_path) -> bool:
    """True iff a fresh flock can be taken on *lock_path* (i.e. released)."""
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(fd, fcntl.LOCK_UN)
        return True
    except (BlockingIOError, OSError):
        return False
    finally:
        os.close(fd)


def test_released_on_normal_exit(tmp_path):
    lock_path = tmp_path / "checkout.lock"

    with deploylock(path=lock_path):
        pass

    assert _lock_is_free(lock_path)


def test_released_on_exception_inside_context(tmp_path):
    lock_path = tmp_path / "checkout.lock"

    class Boom(RuntimeError):
        pass

    with pytest.raises(Boom):
        with deploylock(path=lock_path):
            raise Boom("failure inside the critical section")

    # The flock must have been released despite the exception.
    assert _lock_is_free(lock_path)
