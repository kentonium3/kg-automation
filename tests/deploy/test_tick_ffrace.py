"""Tests for WP04: felix-deployer tick lock-wrap + advance_checkout + health (#667).

Covers the WP04 integration seams layered onto ``run_tick()``:

- T011: the ENTIRE checkout-mutating tick body runs inside a single
  ``deploylock``; ``LockUnavailable`` is a benign defer → ``tick_skip
  reason=lock_unavailable``, ``return 0``, and NO git mutation of the checkout.
- T012: the bare ``git pull`` is replaced by ``advance_checkout(assume_locked=
  True)``; ``diverged`` / ``fetch_failed`` / ``merge_failed`` short-circuit with
  an enriched fail-loud ``tick_skip`` (local_head/origin_head/behind/ahead/reason).
- T013: every advance outcome is recorded into the per-actor health watermark —
  a confirmed failure increments the streak; a clean advance resets it.

All git / lock / health / rebaseline side effects are injected via mocks. No
real git, no office2, no ``/data`` paths, no network.

Import approach mirrors ``test_tick_rebaseline.py``: ``_tick.py`` lives under a
hyphenated directory, so it is loaded via ``spec_from_file_location`` with the
sibling ``notify`` / ``rebaseline`` modules pre-registered in ``sys.modules``.
"""

from __future__ import annotations

import contextlib
import importlib.util
import json
import pathlib
import sys
from typing import Any

import pytest

from scripts.deploy.lib.deploylock import LockUnavailable
from scripts.deploy.lib.gitsync import AdvanceResult
from scripts.deploy.lib.health import read_watermark

# ---------------------------------------------------------------------------
# Loader (same pattern as test_tick_rebaseline.py)
# ---------------------------------------------------------------------------

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
FELIX_DEPLOYER_DIR = REPO_ROOT / "scripts" / "deploy" / "felix-deployer"


def _ensure_sys_path() -> None:
    for p in (str(REPO_ROOT), str(FELIX_DEPLOYER_DIR)):
        if p not in sys.path:
            sys.path.insert(0, p)


def _load_module(name: str, path: pathlib.Path):
    _ensure_sys_path()
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


notify = _load_module("notify", FELIX_DEPLOYER_DIR / "notify.py")
rebaseline = _load_module("rebaseline", FELIX_DEPLOYER_DIR / "rebaseline.py")
tick = _load_module("felix_deployer_tick_ffrace_under_test", FELIX_DEPLOYER_DIR / "_tick.py")


# ---------------------------------------------------------------------------
# Fakes / fixtures
# ---------------------------------------------------------------------------


class _FakeProc:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


#: Git subcommands that MUTATE the checkout / index. On the lock-unavailable
#: defer path none of these may run.
_MUTATING_GIT = frozenset({"pull", "fetch", "merge", "commit", "push", "rm", "add", "checkout", "mv", "reset"})


@pytest.fixture()
def fake_repo(tmp_path: pathlib.Path) -> pathlib.Path:
    for sub in ("queued", "applied", "failed"):
        (tmp_path / "deploys" / sub).mkdir(parents=True, exist_ok=True)
    return tmp_path


@pytest.fixture()
def log_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    d = tmp_path / "logs"
    d.mkdir()
    return d


@pytest.fixture()
def state_dir(tmp_path: pathlib.Path, monkeypatch) -> pathlib.Path:
    """Redirect the health-watermark state dir to tmp and the lock to tmp."""
    d = tmp_path / "state"
    monkeypatch.setattr(tick, "DEFAULT_STATE_DIR", d)
    monkeypatch.setenv("DEPLOY_CHECKOUT_LOCK", str(tmp_path / "checkout.lock"))
    return d


def _read_log(log_dir: pathlib.Path) -> list[dict[str, Any]]:
    files = list(log_dir.glob("*.jsonl"))
    if not files:
        return []
    return [json.loads(ln) for ln in files[0].read_text().splitlines() if ln.strip()]


def _spy_git(calls: list[list[str]]):
    """A ``tick._git`` replacement that records every git invocation."""

    def _fake_git(args: list[str], cwd: pathlib.Path) -> _FakeProc:
        calls.append(list(args))
        cmd = args[0] if args else ""
        if cmd == "rev-parse":
            return _FakeProc(returncode=0, stdout="deadbeef\n")
        return _FakeProc(returncode=0)

    return _fake_git


def _clean_advance(**overrides) -> AdvanceResult:
    base = dict(
        ok=True,
        advanced=True,
        pre_head="aaaa1111",
        post_head="bbbb2222",
        origin_head="bbbb2222",
        behind=1,
        ahead=0,
        diverged=False,
    )
    base.update(overrides)
    return AdvanceResult(**base)


def _no_rebaseline(monkeypatch) -> None:
    monkeypatch.setattr(rebaseline, "observe", lambda *a, **kw: {"outcome": "not_required"})
    monkeypatch.setattr(rebaseline, "reconcile", lambda **kw: {"outcome": "not_required"})
    monkeypatch.setattr(rebaseline, "read_observed_head", lambda *a, **kw: "")
    monkeypatch.setattr(rebaseline, "write_observed_head", lambda *a, **kw: None)
    monkeypatch.setattr(
        rebaseline,
        "classify_watermark",
        lambda *a, **kw: (rebaseline.WATERMARK_FALLBACK, ""),
    )


# ===========================================================================
# T011 — lock spans the whole tick; benign defer on LockUnavailable
# ===========================================================================


def test_advance_called_inside_lock_with_assume_locked(monkeypatch, fake_repo, log_dir, state_dir):
    """The tick acquires deploylock, then calls advance_checkout(assume_locked=
    True) from INSIDE the held lock. Ordering is asserted via an event trace."""
    events: list[str] = []

    @contextlib.contextmanager
    def _fake_lock(path=None, timeout_s: float = 5.0):
        events.append("lock_acquire")
        try:
            yield
        finally:
            events.append("lock_release")

    def _advance(repo_root, **kwargs):
        assert kwargs.get("assume_locked") is True
        events.append("advance")
        return _clean_advance()

    monkeypatch.setattr(tick, "deploylock", _fake_lock)
    monkeypatch.setattr(tick, "advance_checkout", _advance)
    monkeypatch.setattr(tick, "_git", _spy_git([]))
    _no_rebaseline(monkeypatch)

    rc = tick.run_tick(repo_root=fake_repo, log_dir=log_dir)
    assert rc == 0
    # advance runs strictly between acquire and release (lock spans the tick).
    assert events[0] == "lock_acquire"
    assert events[-1] == "lock_release"
    assert "advance" in events
    assert events.index("lock_acquire") < events.index("advance") < events.index("lock_release")


def test_lock_spans_watermark_write(monkeypatch, fake_repo, log_dir, state_dir):
    """The lock is still held when the watermark write runs — i.e. the ENTIRE
    checkout-mutating body (through the watermark) is inside the lock, not just
    the pull (Codex CRITICAL)."""
    lock_held = {"now": False}
    watermark_written_under_lock = {"ok": False}

    @contextlib.contextmanager
    def _fake_lock(path=None, timeout_s: float = 5.0):
        lock_held["now"] = True
        try:
            yield
        finally:
            lock_held["now"] = False

    monkeypatch.setattr(tick, "deploylock", _fake_lock)
    monkeypatch.setattr(tick, "advance_checkout", lambda repo_root, **kw: _clean_advance())
    monkeypatch.setattr(tick, "_git", _spy_git([]))
    monkeypatch.setattr(rebaseline, "observe", lambda *a, **kw: {"outcome": "not_required"})
    monkeypatch.setattr(rebaseline, "reconcile", lambda **kw: {"outcome": "not_required"})
    monkeypatch.setattr(rebaseline, "read_observed_head", lambda *a, **kw: "")
    monkeypatch.setattr(
        rebaseline,
        "classify_watermark",
        lambda *a, **kw: (rebaseline.WATERMARK_FALLBACK, ""),
    )

    def _write_observed_head(sha, *a, **kw):
        # The watermark write is the LAST checkout-touching step of the tick.
        watermark_written_under_lock["ok"] = lock_held["now"]

    monkeypatch.setattr(rebaseline, "write_observed_head", _write_observed_head)

    rc = tick.run_tick(repo_root=fake_repo, log_dir=log_dir)
    assert rc == 0
    assert watermark_written_under_lock["ok"], (
        "watermark write must run while the deploylock is still held"
    )


def test_lock_unavailable_defers_without_mutation(monkeypatch, fake_repo, log_dir, state_dir):
    """LockUnavailable → tick_skip reason=lock_unavailable, return 0, and NO
    git mutation of the checkout (the other actor holds the lock this tick)."""
    git_calls: list[list[str]] = []

    @contextlib.contextmanager
    def _busy_lock(path=None, timeout_s: float = 5.0):
        raise LockUnavailable("held by the other actor")
        yield  # pragma: no cover - unreachable

    advance_calls: list = []

    monkeypatch.setattr(tick, "deploylock", _busy_lock)
    monkeypatch.setattr(
        tick, "advance_checkout", lambda *a, **kw: advance_calls.append(True) or _clean_advance()
    )
    monkeypatch.setattr(tick, "_git", _spy_git(git_calls))
    _no_rebaseline(monkeypatch)

    rc = tick.run_tick(repo_root=fake_repo, log_dir=log_dir)
    assert rc == 0

    entries = _read_log(log_dir)
    skip = next(e for e in entries if e.get("event") == "tick_skip")
    assert skip["reason"] == "lock_unavailable"

    # No checkout mutation happened — advance was never called, and no mutating
    # git subcommand ran.
    assert advance_calls == [], "advance_checkout must not run when the lock is unavailable"
    mutating = [c for c in git_calls if c and c[0] in _MUTATING_GIT]
    assert mutating == [], f"no git mutation may occur on the defer path; saw {mutating}"


def test_lock_unavailable_is_not_a_health_failure(monkeypatch, fake_repo, log_dir, state_dir):
    """A defer (LockUnavailable) must NOT touch the health watermark — it is not
    a confirmed failure (health.record is never reached on this path)."""

    @contextlib.contextmanager
    def _busy_lock(path=None, timeout_s: float = 5.0):
        raise LockUnavailable("held")
        yield  # pragma: no cover

    record_calls: list = []
    monkeypatch.setattr(tick, "deploylock", _busy_lock)
    monkeypatch.setattr(tick._health, "record", lambda *a, **kw: record_calls.append(a))
    _no_rebaseline(monkeypatch)

    rc = tick.run_tick(repo_root=fake_repo, log_dir=log_dir)
    assert rc == 0
    assert record_calls == [], "health.record must not run on a lock-unavailable defer"
    # No state file was created.
    assert not (state_dir / "git-health.json").exists()


# ===========================================================================
# T012 — advance failures: enriched fail-loud tick_skip + early return
# ===========================================================================


@pytest.mark.parametrize(
    "reason,diverged,behind,ahead",
    [
        ("diverged", True, 2, 3),
        ("fetch_failed", False, 0, 0),
        ("merge_failed", False, 4, 0),
    ],
)
def test_advance_failure_logs_enriched_tick_skip(
    monkeypatch, fake_repo, log_dir, state_dir, reason, diverged, behind, ahead
):
    """diverged / fetch_failed / merge_failed short-circuit the tick with an
    enriched tick_skip carrying local_head/origin_head/behind/ahead/reason, and
    the rebaseline engine is NOT reached."""
    observe_calls: list = []

    def _advance(repo_root, **kwargs):
        return AdvanceResult(
            ok=False,
            advanced=False,
            pre_head="feed0001",
            post_head="feed0001",
            origin_head="0r1g1n00",
            behind=behind,
            ahead=ahead,
            diverged=diverged,
            reason=reason,
            stderr="boom" if reason != "diverged" else "",
        )

    monkeypatch.setattr(tick, "advance_checkout", _advance)
    monkeypatch.setattr(tick, "_git", _spy_git([]))
    monkeypatch.setattr(
        rebaseline, "observe", lambda *a, **kw: observe_calls.append(True) or {"outcome": "not_required"}
    )
    monkeypatch.setattr(rebaseline, "reconcile", lambda **kw: {"outcome": "not_required"})

    rc = tick.run_tick(repo_root=fake_repo, log_dir=log_dir)
    assert rc == 0
    assert observe_calls == [], "the rebaseline engine must not run after a failed advance"

    entries = _read_log(log_dir)
    skip = next(e for e in entries if e.get("event") == "tick_skip")
    assert skip["reason"] == reason
    assert skip["local_head"] == "feed0001"
    assert skip["origin_head"] == "0r1g1n00"
    assert skip["behind"] == behind
    assert skip["ahead"] == ahead
    assert skip["diverged"] is diverged


def test_confirmed_failure_increments_health(monkeypatch, fake_repo, log_dir, state_dir):
    """A confirmed failure (fetch_failed) increments the per-actor health streak."""

    monkeypatch.setattr(
        tick,
        "advance_checkout",
        lambda repo_root, **kw: AdvanceResult(
            ok=False,
            advanced=False,
            pre_head="feed0001",
            post_head="feed0001",
            origin_head="",
            behind=0,
            ahead=0,
            diverged=False,
            reason="fetch_failed",
        ),
    )
    monkeypatch.setattr(tick, "_git", _spy_git([]))
    monkeypatch.setattr(rebaseline, "observe", lambda *a, **kw: {"outcome": "not_required"})
    monkeypatch.setattr(rebaseline, "reconcile", lambda **kw: {"outcome": "not_required"})

    rc = tick.run_tick(repo_root=fake_repo, log_dir=log_dir)
    assert rc == 0

    wm = read_watermark(tick.HEALTH_ACTOR, state_dir / "git-health.json")
    assert wm.consecutive_failures == 1
    assert wm.failure_streak_started_ts is not None


def test_repeated_failures_alert_then_clean_advance_resets(
    monkeypatch, fake_repo, log_dir, state_dir
):
    """Three confirmed failures cross the health threshold (one ntfy alert), and
    a subsequent clean advance resets the streak to zero."""
    alerts: list[tuple[str, str]] = []
    monkeypatch.setattr(
        notify,
        "dispatch_health_notification",
        # Report delivery True so health.record stamps last_alert_ts (fires
        # exactly once per streak); a falsy return would re-attempt every tick.
        lambda actor, title, body, *, topic_env: (
            alerts.append((title, body)) or True
        ),
    )
    monkeypatch.setattr(tick, "_git", _spy_git([]))
    monkeypatch.setattr(rebaseline, "observe", lambda *a, **kw: {"outcome": "not_required"})
    monkeypatch.setattr(rebaseline, "reconcile", lambda **kw: {"outcome": "not_required"})
    monkeypatch.setattr(rebaseline, "read_observed_head", lambda *a, **kw: "")
    monkeypatch.setattr(rebaseline, "write_observed_head", lambda *a, **kw: None)
    monkeypatch.setattr(
        rebaseline,
        "classify_watermark",
        lambda *a, **kw: (rebaseline.WATERMARK_FALLBACK, ""),
    )

    def _fail(repo_root, **kw):
        return AdvanceResult(
            ok=False, advanced=False, pre_head="f0", post_head="f0",
            origin_head="o0", behind=1, ahead=1, diverged=True, reason="diverged",
        )

    state_path = state_dir / "git-health.json"

    monkeypatch.setattr(tick, "advance_checkout", _fail)
    for _ in range(3):
        assert tick.run_tick(repo_root=fake_repo, log_dir=log_dir) == 0

    # Threshold (default 3) crossed → exactly one alert fired.
    assert len(alerts) == 1
    wm = read_watermark(tick.HEALTH_ACTOR, state_path)
    assert wm.consecutive_failures == 3

    # A clean advance resets the streak.
    monkeypatch.setattr(tick, "advance_checkout", lambda repo_root, **kw: _clean_advance())
    assert tick.run_tick(repo_root=fake_repo, log_dir=log_dir) == 0
    wm = read_watermark(tick.HEALTH_ACTOR, state_path)
    assert wm.consecutive_failures == 0
    assert wm.failure_streak_started_ts is None


# ===========================================================================
# T013 — clean advance drives the normal flow + health reset
# ===========================================================================


def test_clean_advance_normal_flow_and_health_reset(monkeypatch, fake_repo, log_dir, state_dir):
    """A clean advance proceeds into the normal tick flow (queue scan +
    rebaseline) and resets/records health as a success."""
    monkeypatch.setattr(tick, "advance_checkout", lambda repo_root, **kw: _clean_advance())
    monkeypatch.setattr(tick, "_git", _spy_git([]))

    observe_calls: list = []
    monkeypatch.setattr(
        rebaseline, "observe", lambda *a, **kw: observe_calls.append(True) or {"outcome": "not_required"}
    )
    monkeypatch.setattr(rebaseline, "reconcile", lambda **kw: {"outcome": "not_required"})
    monkeypatch.setattr(rebaseline, "read_observed_head", lambda *a, **kw: "")
    monkeypatch.setattr(rebaseline, "write_observed_head", lambda *a, **kw: None)
    monkeypatch.setattr(
        rebaseline,
        "classify_watermark",
        lambda *a, **kw: (rebaseline.WATERMARK_FALLBACK, ""),
    )

    rc = tick.run_tick(repo_root=fake_repo, log_dir=log_dir)
    assert rc == 0

    # Normal flow proceeded: queue scanned + rebaseline observe ran.
    entries = _read_log(log_dir)
    assert any(e.get("event") == "queue_scanned" for e in entries)
    assert observe_calls == [True]

    # Health recorded as a success: last_success_head set, streak zero.
    wm = read_watermark(tick.HEALTH_ACTOR, state_dir / "git-health.json")
    assert wm.consecutive_failures == 0
    assert wm.last_success_head == "bbbb2222"


def test_health_record_error_never_crashes_tick(monkeypatch, fake_repo, log_dir, state_dir):
    """A health-store failure is best-effort: it is logged and the tick still
    returns 0 (health is escalation, never fatal)."""
    monkeypatch.setattr(tick, "advance_checkout", lambda repo_root, **kw: _clean_advance())
    monkeypatch.setattr(tick, "_git", _spy_git([]))
    _no_rebaseline(monkeypatch)

    def _boom(*a, **kw):
        raise RuntimeError("health store unwritable")

    monkeypatch.setattr(tick._health, "record", _boom)

    rc = tick.run_tick(repo_root=fake_repo, log_dir=log_dir)
    assert rc == 0
    entries = _read_log(log_dir)
    assert any(e.get("event") == "health_record_error" for e in entries)


def test_health_notifier_routes_to_dispatch_health_notification(monkeypatch):
    """The notifier built by _health_notifier forwards (title, body) to
    notify.dispatch_health_notification with the felix-deployer topic env."""
    captured: dict = {}

    def _fake_dispatch(actor, title, body, *, topic_env):
        captured.update(actor=actor, title=title, body=body, topic_env=topic_env)

    monkeypatch.setattr(notify, "dispatch_health_notification", _fake_dispatch)
    notifier = tick._health_notifier("felix-deployer")
    notifier("a title", "a body")

    assert captured["actor"] == "felix-deployer"
    assert captured["title"] == "a title"
    assert captured["body"] == "a body"
    assert captured["topic_env"] == tick.HEALTH_TOPIC_ENV
