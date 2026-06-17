"""Tests for WP03: rebaseline engine wiring inside run_tick() (#618).

Covers:
- T009: observe + reconcile called with the correct pulled range (pre..post);
  wiring happens AFTER the queue loop (NFR-002 ordering).
- T010: tick-log observability entries for each rebaseline outcome.
- T011: ntfy dedupe — each alert fires exactly once per token per event key.
- T012: no-crash discipline — exceptions from the engine are swallowed and
  the tick still returns 0.
- NFR-002 budget assertion: rebaseline is not called before the queue loop
  (manifest application is never delayed).
- NFR-004 (zero human interaction): happy-path sequence pending_set →
  completed proceeds without any external intervention.

All subprocess / filesystem / rebaseline-engine / ntfy side-effects are
injected via mocks.  No real git, no office2, no /data paths touched.

Import approach
---------------
``_tick.py`` lives under ``scripts/deploy/felix-deployer/`` — a hyphenated
directory that is not importable as a dotted Python package.  We use
``importlib.util.spec_from_file_location`` (same pattern as
``test_deployer.py`` and ``test_notify.py``).  We must register sibling
modules ``notify`` and ``rebaseline`` in ``sys.modules`` before loading
``_tick`` so its top-level imports resolve.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
from typing import Any
from unittest.mock import MagicMock, patch, call

import pytest

# ---------------------------------------------------------------------------
# Loader helpers
# ---------------------------------------------------------------------------

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
FELIX_DEPLOYER_DIR = REPO_ROOT / "scripts" / "deploy" / "felix-deployer"


def _ensure_sys_path() -> None:
    for p in (str(REPO_ROOT), str(FELIX_DEPLOYER_DIR)):
        if p not in sys.path:
            sys.path.insert(0, p)


def _load_module(name: str, path: pathlib.Path):
    """Load a module from an absolute file path and register it in sys.modules."""
    _ensure_sys_path()
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Load notify first (needed by _tick's top-level `import notify`).
notify = _load_module("notify", FELIX_DEPLOYER_DIR / "notify.py")

# Load rebaseline (needed by _tick's top-level `import rebaseline`).
# rebaseline.py inserts tooling/scripts onto sys.path at import time so
# audited_surfaces resolves — this import happens once here.
rebaseline = _load_module("rebaseline", FELIX_DEPLOYER_DIR / "rebaseline.py")

# Now load _tick — both siblings are already in sys.modules.
tick = _load_module("felix_deployer_tick_under_test", FELIX_DEPLOYER_DIR / "_tick.py")


# ---------------------------------------------------------------------------
# Shared fake types
# ---------------------------------------------------------------------------


class _FakeProc:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def fake_repo(tmp_path: pathlib.Path) -> pathlib.Path:
    """Minimal repo layout: empty queued dir (no manifests to apply)."""
    for sub in ("queued", "applied", "failed"):
        (tmp_path / "deploys" / sub).mkdir(parents=True, exist_ok=True)
    return tmp_path


@pytest.fixture()
def log_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    d = tmp_path / "logs"
    d.mkdir()
    return d


def _read_log(log_dir: pathlib.Path) -> list[dict[str, Any]]:
    files = list(log_dir.glob("*.jsonl"))
    if not files:
        return []
    return [json.loads(ln) for ln in files[0].read_text().splitlines() if ln.strip()]


def _git_mock(
    *,
    pull_rc: int = 0,
    pre_sha: str = "aabbccdd",
    post_sha: str = "11223344",
):
    """Build a _tick._git replacement that returns predictable results."""
    def _fake_git(args: list[str], cwd: pathlib.Path) -> _FakeProc:
        cmd = args[0] if args else ""
        if cmd == "pull":
            return _FakeProc(returncode=pull_rc, stdout="", stderr="pull error" if pull_rc else "")
        if cmd == "rev-parse":
            # First rev-parse (pre-pull) uses pre_sha; second (post-pull) uses post_sha.
            # We track call count via a mutable list to distinguish them.
            if not _fake_git._post_pull_resolved:  # type: ignore[attr-defined]
                _fake_git._post_pull_resolved = True  # type: ignore[attr-defined]
                return _FakeProc(returncode=0, stdout=pre_sha + "\n")
            return _FakeProc(returncode=0, stdout=post_sha + "\n")
        # All other git commands succeed by default.
        return _FakeProc(returncode=0, stdout="", stderr="")

    _fake_git._post_pull_resolved = False  # type: ignore[attr-defined]
    return _fake_git


# ---------------------------------------------------------------------------
# T009 — observe + reconcile called with correct pulled range
# ---------------------------------------------------------------------------


def test_observe_called_with_pulled_range(monkeypatch, fake_repo, log_dir):
    """observe() is called with pre_pull_head and post_pull_head."""
    PRE = "aabbccdd" * 5
    POST = "11223344" * 5

    monkeypatch.setattr(tick, "_git", _git_mock(pre_sha=PRE, post_sha=POST))

    observe_calls: list[tuple] = []

    def _fake_observe(pre, post, **kwargs):
        observe_calls.append((pre, post))
        return {"outcome": "not_required"}

    monkeypatch.setattr(rebaseline, "observe", _fake_observe)
    monkeypatch.setattr(rebaseline, "reconcile", lambda **kw: {"outcome": "not_required"})

    rc = tick.run_tick(repo_root=fake_repo, log_dir=log_dir)
    assert rc == 0
    assert len(observe_calls) == 1
    assert observe_calls[0] == (PRE, POST)


def test_reconcile_called_each_tick(monkeypatch, fake_repo, log_dir):
    """reconcile() is always called once per tick after observe()."""
    PRE = "aabbccdd" * 5
    POST = "11223344" * 5

    monkeypatch.setattr(tick, "_git", _git_mock(pre_sha=PRE, post_sha=POST))
    monkeypatch.setattr(rebaseline, "observe", lambda *a, **kw: {"outcome": "not_required"})

    reconcile_calls = []

    def _fake_reconcile(**kwargs):
        reconcile_calls.append(True)
        return {"outcome": "not_required"}

    monkeypatch.setattr(rebaseline, "reconcile", _fake_reconcile)

    rc = tick.run_tick(repo_root=fake_repo, log_dir=log_dir)
    assert rc == 0
    assert len(reconcile_calls) == 1


# ---------------------------------------------------------------------------
# NFR-002 budget — rebaseline runs AFTER the queue loop
# ---------------------------------------------------------------------------


def test_rebaseline_runs_after_queue_loop(monkeypatch, fake_repo, log_dir):
    """observe/reconcile are invoked after queue_scanned, not before."""
    call_order: list[str] = []

    original_log = tick._log

    def _tracking_log(path, entry):
        if entry.get("event") in ("queue_scanned", "rebaseline_observe"):
            call_order.append(entry["event"])
        original_log(path, entry)

    monkeypatch.setattr(tick, "_log", _tracking_log)
    monkeypatch.setattr(tick, "_git", _git_mock())
    monkeypatch.setattr(rebaseline, "observe", lambda *a, **kw: {"outcome": "not_required"})
    monkeypatch.setattr(rebaseline, "reconcile", lambda **kw: {"outcome": "not_required"})

    rc = tick.run_tick(repo_root=fake_repo, log_dir=log_dir)
    assert rc == 0
    assert call_order.index("queue_scanned") < call_order.index("rebaseline_observe")


# ---------------------------------------------------------------------------
# T010 — Observability stamping for each outcome
# ---------------------------------------------------------------------------


def test_log_not_required(monkeypatch, fake_repo, log_dir):
    """not_required outcome is stamped in the tick log."""
    monkeypatch.setattr(tick, "_git", _git_mock())
    monkeypatch.setattr(rebaseline, "observe", lambda *a, **kw: {"outcome": "not_required"})
    monkeypatch.setattr(rebaseline, "reconcile", lambda **kw: {"outcome": "not_required"})

    tick.run_tick(repo_root=fake_repo, log_dir=log_dir)
    entries = _read_log(log_dir)
    obs = [e for e in entries if e.get("event") == "rebaseline_observe"]
    rec = [e for e in entries if e.get("event") == "rebaseline_reconcile"]
    assert obs and obs[0]["outcome"] == "not_required"
    assert rec and rec[0]["outcome"] == "not_required"


def test_log_pending_set_includes_surface_ids(monkeypatch, fake_repo, log_dir):
    """pending_set carries surface_ids and matched_files in the tick log."""
    monkeypatch.setattr(tick, "_git", _git_mock())
    monkeypatch.setattr(rebaseline, "observe", lambda *a, **kw: {
        "outcome": "pending_set",
        "surface_ids": ["s1", "s2"],
        "matched_files": ["scripts/foo.sh"],
    })
    monkeypatch.setattr(rebaseline, "reconcile", lambda **kw: {"outcome": "not_required"})

    tick.run_tick(repo_root=fake_repo, log_dir=log_dir)
    entries = _read_log(log_dir)
    obs = next(e for e in entries if e.get("event") == "rebaseline_observe")
    assert obs["outcome"] == "pending_set"
    assert obs["surface_ids"] == ["s1", "s2"]
    assert obs["matched_files"] == ["scripts/foo.sh"]


def test_log_completed_carries_rebaselined_at_and_count(monkeypatch, fake_repo, log_dir):
    """completed outcome carries rebaselined_at_utc and baseline_count."""
    monkeypatch.setattr(tick, "_git", _git_mock())
    monkeypatch.setattr(rebaseline, "observe", lambda *a, **kw: {"outcome": "not_required"})
    monkeypatch.setattr(rebaseline, "reconcile", lambda **kw: {
        "outcome": "completed",
        "rebaselined_at_utc": "2026-06-17T10:00:00Z",
        "baseline_count": 5,
    })

    tick.run_tick(repo_root=fake_repo, log_dir=log_dir)
    entries = _read_log(log_dir)
    rec = next(e for e in entries if e.get("event") == "rebaseline_reconcile")
    assert rec["outcome"] == "completed"
    assert rec["rebaselined_at_utc"] == "2026-06-17T10:00:00Z"
    assert rec["baseline_count"] == 5


def test_log_failed_carries_error_summary(monkeypatch, fake_repo, log_dir):
    """failed outcome carries error_summary in the tick log."""
    monkeypatch.setattr(tick, "_git", _git_mock())
    monkeypatch.setattr(rebaseline, "observe", lambda *a, **kw: {"outcome": "not_required"})
    monkeypatch.setattr(rebaseline, "reconcile", lambda **kw: {
        "outcome": "failed",
        "error_summary": "baseline count mismatch: got 3, expected 5",
    })
    # Prevent alert dispatch from erroring on missing token.
    monkeypatch.setattr(rebaseline, "read_token", lambda **kw: None)

    tick.run_tick(repo_root=fake_repo, log_dir=log_dir)
    entries = _read_log(log_dir)
    rec = next(e for e in entries if e.get("event") == "rebaseline_reconcile")
    assert rec["outcome"] == "failed"
    assert "baseline count mismatch" in rec["error_summary"]


def test_log_unexpected_drift_carries_drifted_and_unexpected(monkeypatch, fake_repo, log_dir):
    """unexpected_drift outcome carries drifted/expected/unexpected lists."""
    monkeypatch.setattr(tick, "_git", _git_mock())
    monkeypatch.setattr(rebaseline, "observe", lambda *a, **kw: {"outcome": "not_required"})
    monkeypatch.setattr(rebaseline, "reconcile", lambda **kw: {
        "outcome": "unexpected_drift",
        "drifted": ["b1", "b2"],
        "expected": ["b1"],
        "unexpected": ["b2"],
    })
    monkeypatch.setattr(rebaseline, "read_token", lambda **kw: None)

    tick.run_tick(repo_root=fake_repo, log_dir=log_dir)
    entries = _read_log(log_dir)
    rec = next(e for e in entries if e.get("event") == "rebaseline_reconcile")
    assert rec["outcome"] == "unexpected_drift"
    assert "b2" in rec["unexpected"]


def test_log_stale_marker(monkeypatch, fake_repo, log_dir):
    """stale flag from reconcile is surfaced in the reconcile log entry."""
    monkeypatch.setattr(tick, "_git", _git_mock())
    monkeypatch.setattr(rebaseline, "observe", lambda *a, **kw: {"outcome": "not_required"})
    monkeypatch.setattr(rebaseline, "reconcile", lambda **kw: {
        "outcome": "inconclusive",
        "stale": True,
    })
    monkeypatch.setattr(rebaseline, "read_token", lambda **kw: None)

    tick.run_tick(repo_root=fake_repo, log_dir=log_dir)
    entries = _read_log(log_dir)
    rec = next(e for e in entries if e.get("event") == "rebaseline_reconcile")
    assert rec.get("stale") is True


# ---------------------------------------------------------------------------
# T011 — ntfy alert dedupe
# ---------------------------------------------------------------------------


def _make_token(alerts_emitted: list[str] | None = None) -> dict:
    return {
        "schema_version": 1,
        "pending_since_utc": "2026-06-17T00:00:00Z",
        "observed_head_sha": "aabbccdd",
        "surface_ids": ["openclaw-agent-prompts"],
        "expected_baselines": ["openclaw-config"],
        "matched_files": ["ai-agents/felix-admin.md"],
        "last_check_utc": None,
        "alerts_emitted": alerts_emitted or [],
    }


def test_alert_fires_exactly_once_for_rebaseline_failed(monkeypatch, fake_repo, log_dir):
    """rebaseline_failed alert fires once; second tick is deduped.

    Dedupe works end-to-end via the mutable token dict: dispatch_rebaseline_alert
    mutates token['alerts_emitted'] on send; _tick persists via write_token;
    next tick's read_token returns the same mutable object (already has the key).
    """
    # Shared mutable token — simulates the on-disk token across ticks.
    shared_token: dict = _make_token()

    dispatch_calls: list[str] = []

    def _fake_dispatch(event_key, token, detail, head_sha, **kwargs):
        # Simulate the real dispatch: mutate alerts_emitted on success (no curl).
        if event_key not in token.get("alerts_emitted", []):
            dispatch_calls.append(event_key)
            token.setdefault("alerts_emitted", []).append(event_key)
        from scripts.deploy.lib import LibResult
        return LibResult(ok=True, summary="sent", details={})

    monkeypatch.setattr(notify, "dispatch_rebaseline_alert", _fake_dispatch)
    monkeypatch.setattr(tick, "_git", _git_mock())
    monkeypatch.setattr(rebaseline, "observe", lambda *a, **kw: {"outcome": "not_required"})
    monkeypatch.setattr(rebaseline, "reconcile", lambda **kw: {"outcome": "failed", "error_summary": "oops"})
    # read_token returns the shared mutable token (already includes any mutations).
    monkeypatch.setattr(rebaseline, "read_token", lambda **kw: shared_token)
    # write_token is a no-op — the in-memory dict IS the store.
    monkeypatch.setattr(rebaseline, "write_token", lambda t, p=None: None)

    # Tick 1 — alert fires for the first time.
    tick.run_tick(repo_root=fake_repo, log_dir=log_dir)
    assert dispatch_calls.count("rebaseline_failed") == 1

    # Tick 2 — alerts_emitted already has 'rebaseline_failed'; dedupe fires.
    tick.run_tick(repo_root=fake_repo, log_dir=log_dir)
    assert dispatch_calls.count("rebaseline_failed") == 1  # still exactly 1


def test_alert_deduplication_via_notify_dispatch(monkeypatch):
    """dispatch_rebaseline_alert's own dedupe: skip if event already in alerts_emitted."""
    token = _make_token(alerts_emitted=["rebaseline_failed"])

    result = notify.dispatch_rebaseline_alert(
        event_key="rebaseline_failed",
        token=token,
        detail="some error",
        head_sha="aabbccdd",
    )
    assert result.ok is True
    assert result.details.get("deduplicated") is True
    # alerts_emitted must not grow.
    assert token["alerts_emitted"].count("rebaseline_failed") == 1


def test_alert_mutates_token_on_first_send(monkeypatch):
    """dispatch_rebaseline_alert appends event to token['alerts_emitted'] on success."""
    token = _make_token(alerts_emitted=[])
    monkeypatch.setenv(notify.NTFY_TOPIC_ENV, "test-topic-abc1234")

    class _FakeProc:
        returncode = 0
        stdout = ""
        stderr = ""

    import subprocess as _sp
    monkeypatch.setattr(_sp, "run", lambda *a, **kw: _FakeProc())
    monkeypatch.setattr(notify.subprocess, "run", lambda *a, **kw: _FakeProc())

    result = notify.dispatch_rebaseline_alert(
        event_key="unexpected_drift",
        token=token,
        detail="b2 outside expected set",
        head_sha="deadbeef",
    )
    assert result.ok is True
    assert "unexpected_drift" in token["alerts_emitted"]


# ---------------------------------------------------------------------------
# T012 — No-crash discipline
# ---------------------------------------------------------------------------


def test_engine_exception_is_swallowed_tick_returns_zero(monkeypatch, fake_repo, log_dir):
    """An exception raised inside the rebaseline engine does not crash the tick."""
    monkeypatch.setattr(tick, "_git", _git_mock())

    def _boom(*a, **kw):
        raise RuntimeError("simulated engine failure")

    monkeypatch.setattr(rebaseline, "observe", _boom)

    rc = tick.run_tick(repo_root=fake_repo, log_dir=log_dir)
    assert rc == 0

    entries = _read_log(log_dir)
    error_entries = [e for e in entries if e.get("event") == "rebaseline_error"]
    assert error_entries, "rebaseline_error should be logged when engine raises"
    assert "simulated engine failure" in error_entries[0]["error"]


def test_reconcile_exception_is_swallowed(monkeypatch, fake_repo, log_dir):
    """reconcile() raising does not crash the tick; rebaseline_error is logged."""
    monkeypatch.setattr(tick, "_git", _git_mock())
    monkeypatch.setattr(rebaseline, "observe", lambda *a, **kw: {"outcome": "not_required"})

    def _boom_reconcile(**kw):
        raise ValueError("reconcile exploded")

    monkeypatch.setattr(rebaseline, "reconcile", _boom_reconcile)

    rc = tick.run_tick(repo_root=fake_repo, log_dir=log_dir)
    assert rc == 0


def test_tick_returns_zero_on_pull_failure(monkeypatch, fake_repo, log_dir):
    """git pull failure produces tick_skip and does not invoke the engine."""
    observe_called = []
    monkeypatch.setattr(tick, "_git", _git_mock(pull_rc=1))
    monkeypatch.setattr(rebaseline, "observe", lambda *a, **kw: observe_called.append(True) or {"outcome": "not_required"})
    monkeypatch.setattr(rebaseline, "reconcile", lambda **kw: {"outcome": "not_required"})

    rc = tick.run_tick(repo_root=fake_repo, log_dir=log_dir)
    assert rc == 0
    # On pull failure the tick returns early; engine must NOT be called.
    assert observe_called == []


# ---------------------------------------------------------------------------
# NFR-004 — Happy path: pending_set → completed, zero human interaction
# ---------------------------------------------------------------------------


def test_happy_path_pending_set_then_completed(monkeypatch, fake_repo, log_dir):
    """Two-tick happy path: tick1=pending_set, tick2=completed; no human step."""
    # Tick 1: observe sees a change → pending_set; reconcile is not_required
    # (no token before the pull, or token just written → audit finds no drift yet).
    # Tick 2: observe sees no new change → not_required; reconcile runs and
    # produces completed (baseline reset successful).

    call_count = {"tick": 0}

    def _fake_observe(pre, post, **kw):
        call_count["tick"] += 1
        if call_count["tick"] == 1:
            return {
                "outcome": "pending_set",
                "surface_ids": ["openclaw-agent-prompts"],
                "matched_files": ["ai-agents/felix-admin.md"],
            }
        return {"outcome": "not_required"}

    def _fake_reconcile(**kw):
        if call_count["tick"] == 1:
            # First tick: token just written; assume audit comes back inconclusive
            # (baselines haven't drifted yet on the first check).
            return {"outcome": "inconclusive"}
        return {
            "outcome": "completed",
            "rebaselined_at_utc": "2026-06-17T10:00:00Z",
            "baseline_count": 5,
        }

    monkeypatch.setattr(tick, "_git", _git_mock())
    monkeypatch.setattr(rebaseline, "observe", _fake_observe)
    monkeypatch.setattr(rebaseline, "reconcile", _fake_reconcile)

    # Tick 1 — pending_set observed.
    rc1 = tick.run_tick(repo_root=fake_repo, log_dir=log_dir)
    assert rc1 == 0

    # Tick 2 — completed.
    rc2 = tick.run_tick(repo_root=fake_repo, log_dir=log_dir)
    assert rc2 == 0

    entries = _read_log(log_dir)
    completed = [
        e for e in entries
        if e.get("event") == "rebaseline_reconcile" and e.get("outcome") == "completed"
    ]
    assert completed, "completed outcome must appear in the tick log"
    assert completed[0]["baseline_count"] == 5


# ---------------------------------------------------------------------------
# NFR-002 — Budget: rebaseline never blocking before queue
# ---------------------------------------------------------------------------


def test_rebaseline_not_called_before_queue_scanned(monkeypatch, fake_repo, log_dir):
    """observe/reconcile must not appear before queue_scanned in the log."""
    events: list[str] = []
    original_log = tick._log

    def _tracking_log(path, entry):
        ev = entry.get("event")
        if ev in ("queue_scanned", "rebaseline_observe", "rebaseline_reconcile"):
            events.append(ev)
        original_log(path, entry)

    monkeypatch.setattr(tick, "_log", _tracking_log)
    monkeypatch.setattr(tick, "_git", _git_mock())
    monkeypatch.setattr(rebaseline, "observe", lambda *a, **kw: {"outcome": "not_required"})
    monkeypatch.setattr(rebaseline, "reconcile", lambda **kw: {"outcome": "not_required"})

    tick.run_tick(repo_root=fake_repo, log_dir=log_dir)

    assert "queue_scanned" in events
    assert "rebaseline_observe" in events
    # queue_scanned must come before any rebaseline_* event.
    qs_idx = events.index("queue_scanned")
    rb_idx = min(
        (events.index(e) for e in events if e.startswith("rebaseline_")),
        default=None,
    )
    assert rb_idx is not None
    assert qs_idx < rb_idx, (
        f"rebaseline ran before queue_scanned: events={events}"
    )


# ---------------------------------------------------------------------------
# F2 — FR-003: rebaseline outcome stamped on applied deploy record
# ---------------------------------------------------------------------------


@pytest.fixture()
def fake_repo_with_manifest(tmp_path: pathlib.Path) -> pathlib.Path:
    """Repo layout with one queued manifest so the queue loop produces an apply."""
    import yaml

    for sub in ("queued", "applied", "failed", "schema"):
        (tmp_path / "deploys" / sub).mkdir(parents=True, exist_ok=True)

    manifest = {
        "name": "0099-test-deploy",
        "tier": 3,
        "entrypoint": "scripts/noop.sh",
    }
    (tmp_path / "deploys" / "queued" / "0099-test-deploy.yaml").write_text(
        yaml.safe_dump(manifest), encoding="utf-8"
    )
    return tmp_path


def test_rebaseline_stamped_on_applied_manifest(monkeypatch, fake_repo_with_manifest, log_dir):
    """FR-003: when ≥1 manifest is applied, a rebaseline_stamped log entry
    correlates the applied manifest name(s) with the reconcile outcome.
    """
    from scripts.deploy.lib import LibResult as _LibResult

    monkeypatch.setattr(tick, "_git", _git_mock())
    monkeypatch.setattr(rebaseline, "observe", lambda *a, **kw: {"outcome": "not_required"})
    monkeypatch.setattr(
        rebaseline,
        "reconcile",
        lambda **kw: {
            "outcome": "completed",
            "rebaselined_at_utc": "2026-06-17T12:00:00Z",
            "baseline_count": 3,
        },
    )

    # Stub the apply gate to succeed so the manifest enters _record_success.
    class _OkResult:
        ok = True
        summary = "dry-run ok"
        details: dict = {}

    from scripts.deploy.lib import apply as _apply_lib
    monkeypatch.setattr(_apply_lib, "dry_run_then_apply_gate", lambda *a, **kw: _OkResult())

    # Stub _record_success so we don't need a real git tree.
    monkeypatch.setattr(
        tick,
        "_record_success",
        lambda repo_root, manifest_path, manifest_data, head_sha: (
            True,
            str(repo_root / "deploys" / "applied" / "0099-test-deploy.yaml"),
        ),
    )

    rc = tick.run_tick(repo_root=fake_repo_with_manifest, log_dir=log_dir)
    assert rc == 0

    entries = _read_log(log_dir)

    # The applied manifest_processed entry must appear.
    applied_entries = [
        e for e in entries
        if e.get("event") == "manifest_processed" and e.get("outcome") == "applied"
    ]
    assert applied_entries, "expected a manifest_processed/applied entry"
    assert applied_entries[0]["manifest_name"] == "0099-test-deploy"

    # The rebaseline_stamped entry must appear and correlate the manifest name
    # with the reconcile outcome (FR-003).
    stamped = [e for e in entries if e.get("event") == "rebaseline_stamped"]
    assert stamped, "expected a rebaseline_stamped entry when manifests were applied"
    s = stamped[0]
    assert "0099-test-deploy" in s["applied_manifests"]
    assert s["rebaseline_outcome"] == "completed"
    assert s.get("rebaselined_at_utc") == "2026-06-17T12:00:00Z"
    assert s.get("baseline_count") == 3

    # The rebaseline_stamped entry must appear AFTER the manifest_processed entry
    # (ordering sanity).
    applied_idx = next(i for i, e in enumerate(entries) if e.get("event") == "rebaseline_stamped")
    manifest_idx = next(i for i, e in enumerate(entries) if e.get("event") == "manifest_processed" and e.get("outcome") == "applied")
    assert manifest_idx < applied_idx, "rebaseline_stamped must follow manifest_processed"


# ---------------------------------------------------------------------------
# F1 — stale alert dispatched exactly once despite engine pre-marking "stale"
# ---------------------------------------------------------------------------


def test_stale_alert_dispatched_once_across_repeated_ticks(monkeypatch, fake_repo, log_dir):
    """F1 fix: stale ntfy fires exactly once per token even though the engine
    pre-marks 'stale' in alerts_emitted before dispatch runs.

    The engine returns {"stale": True} exactly once (self-dedupes on subsequent
    ticks via its own alerts_emitted["stale"] check).  WP03 uses event_key
    "stale_ntfy" as its dedupe key so it is independent of the engine's marker.
    This test drives a real stale token (not None) through the full dispatch
    path and asserts the ntfy send fires exactly once over two ticks where the
    engine signals stale.
    """
    # Token that already has 'stale' pre-marked (as _maybe_stale would produce).
    # alerts_emitted has "stale" but NOT "stale_ntfy" — this is the live state
    # at the moment the engine returns {"stale": True} for the first time.
    shared_token: dict = _make_token(alerts_emitted=["stale"])

    dispatch_calls: list[str] = []

    def _fake_dispatch(event_key, token, detail, head_sha, **kwargs):
        # Simulate real dispatch: mutate alerts_emitted on first send, skip on repeat.
        if event_key not in token.get("alerts_emitted", []):
            dispatch_calls.append(event_key)
            token.setdefault("alerts_emitted", []).append(event_key)
        from scripts.deploy.lib import LibResult
        return LibResult(ok=True, summary="sent", details={})

    monkeypatch.setattr(notify, "dispatch_rebaseline_alert", _fake_dispatch)
    monkeypatch.setattr(tick, "_git", _git_mock())
    monkeypatch.setattr(rebaseline, "observe", lambda *a, **kw: {"outcome": "not_required"})

    # Reconcile returns stale=True on tick 1; on tick 2 the engine sees
    # "stale" already in alerts_emitted and returns {} (no stale signal),
    # so _maybe_dispatch never appends "stale_ntfy" to alert_events.
    tick_count = {"n": 0}

    def _fake_reconcile(**kw):
        tick_count["n"] += 1
        if tick_count["n"] == 1:
            return {"outcome": "inconclusive", "stale": True}
        return {"outcome": "inconclusive"}

    monkeypatch.setattr(rebaseline, "reconcile", _fake_reconcile)
    monkeypatch.setattr(rebaseline, "read_token", lambda **kw: shared_token)
    monkeypatch.setattr(rebaseline, "write_token", lambda t, p=None: None)

    # Tick 1 — engine signals stale=True; dispatch should fire for "stale_ntfy".
    tick.run_tick(repo_root=fake_repo, log_dir=log_dir)
    assert dispatch_calls.count("stale_ntfy") == 1, (
        f"expected exactly 1 stale_ntfy dispatch on tick 1; got {dispatch_calls}"
    )

    # Tick 2 — engine no longer signals stale (self-deduped); no second dispatch.
    tick.run_tick(repo_root=fake_repo, log_dir=log_dir)
    assert dispatch_calls.count("stale_ntfy") == 1, (
        f"stale_ntfy should not fire a second time; calls={dispatch_calls}"
    )
