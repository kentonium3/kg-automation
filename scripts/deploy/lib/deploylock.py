"""Actor-level advisory checkout lock for the deploy pipeline.

Both deploy actors (``felix-deployer`` and ``agent-prompt-sync``) share a single
git checkout on office2. Even with the FETCH_HEAD race eliminated by ref-based
merges (see :mod:`scripts.deploy.lib.gitsync`), two concurrent working-tree/index
mutations on one checkout still race — felix-deployer's post-pull
commit/push/stamp/watermark phase is the widest window. This module provides the
mutual-exclusion primitive both actors wrap around their **entire** critical
section (research D2, contract ``contracts/lib-api.md``).

Design:
    * ``deploylock`` is a **standalone** context manager (NOT embedded inside
      ``advance_checkout``); each actor holds it at the actor level.
    * ``fcntl.flock(LOCK_EX | LOCK_NB)`` — **non-blocking** — with a bounded
      retry loop (short sleeps) up to ``timeout_s``. On continued failure it
      raises :class:`LockUnavailable` so the caller can defer to the next tick
      instead of hanging a tick indefinitely.
    * The OS auto-releases the flock if the holding process dies, so a crashed
      actor never leaves a stale lock wedging the other.

Dependency-free: stdlib only (``fcntl``, ``os``, ``time``, ``contextlib``,
``pathlib``).
"""

from __future__ import annotations

import fcntl
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

#: Environment variable that overrides the lock path (used by tests and, if
#: ever needed, by an operator). Takes precedence over :data:`DEFAULT_LOCK_PATH`
#: but not over an explicit ``path`` argument.
ENV_LOCK_PATH = "DEPLOY_CHECKOUT_LOCK"

#: Well-known shared lock path on office2. A neutral location owned by neither
#: actor's service directory. Created on demand.
DEFAULT_LOCK_PATH = Path("/data/services/deploy/locks/office2-checkout.lock")

#: Sleep between non-blocking acquisition attempts (seconds).
_RETRY_INTERVAL_S = 0.05


class LockUnavailable(RuntimeError):
    """Raised when the advisory lock could not be acquired within ``timeout_s``.

    The caller treats this as a **benign defer** (the other actor simply held the
    lock): record ``reason="lock_unavailable"`` and retry on the next tick. It is
    NOT a health failure.
    """


def _resolve_path(path: Path | None) -> Path:
    """Resolve the lock path: explicit arg > env override > default."""
    if path is not None:
        return Path(path)
    env_value = os.environ.get(ENV_LOCK_PATH)
    if env_value:
        return Path(env_value)
    return DEFAULT_LOCK_PATH


@contextmanager
def deploylock(path: Path | None = None, timeout_s: float = 5.0) -> Iterator[None]:
    """Hold an advisory ``fcntl.flock`` on a shared checkout-lock file.

    Args:
        path: Explicit lock path. When ``None``, resolves from the
            ``DEPLOY_CHECKOUT_LOCK`` env var, then :data:`DEFAULT_LOCK_PATH`.
        timeout_s: Upper bound (seconds) on the non-blocking retry loop before
            giving up and raising :class:`LockUnavailable`.

    Yields:
        ``None`` while the lock is held.

    Raises:
        LockUnavailable: If ``LOCK_EX`` could not be acquired within
            ``timeout_s``.

    The lock is acquired with ``LOCK_EX | LOCK_NB`` (non-blocking) so a busy
    holder never blocks this caller past ``timeout_s`` (NFR-002). The flock and
    the file descriptor are released on context exit — guaranteed even if the
    body raises — and the OS auto-releases if the process dies.
    """
    lock_path = _resolve_path(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    # O_CREAT so the lock file materialises on first use; content is irrelevant.
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        deadline = time.monotonic() + max(timeout_s, 0.0)
        acquired = False
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except (BlockingIOError, OSError):
                # Contended. Retry until the deadline, then defer.
                if time.monotonic() >= deadline:
                    break
                time.sleep(_RETRY_INTERVAL_S)

        if not acquired:
            raise LockUnavailable(
                f"could not acquire deploylock at {lock_path} within {timeout_s}s"
            )

        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
