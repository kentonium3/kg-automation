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
    cat_file_rc: int = 0,
    ancestor_rc: int = 0,
):
    """Build a _tick._git replacement that returns predictable results.

    ``cat_file_rc`` / ``ancestor_rc`` drive the watermark-classification git
    calls (``cat-file -e`` and ``merge-base --is-ancestor``) so tests can steer
    the observe-range base selection.
    """
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
        if cmd == "cat-file":
            return _FakeProc(returncode=cat_file_rc)
        if cmd == "merge-base":
            return _FakeProc(returncode=ancestor_rc)
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


# ===========================================================================
# WP01 — T008: watermark range, fold, grace, no-crash, backward compat
# ===========================================================================


PRE = "aabbccdd" * 5
POST = "11223344" * 5
WATERMARK = "0f0f0f0f" * 5  # an older observed head


# ---------------------------------------------------------------------------
# HEADLINE — out-of-band repro (SC-001)
# ---------------------------------------------------------------------------


def test_out_of_band_repro_pre_equals_post_still_observes_from_watermark(
    monkeypatch, fake_repo, log_dir
):
    """#685 out-of-band repro: an out-of-band ``git pull`` advanced HEAD before
    the tick, so ``pre_pull_head == post_pull_head`` and the tick's own pull is
    a no-op.  With a persisted watermark OLDER than post, observe MUST run over
    ``watermark..post`` (not the empty ``pre..post``), arm a token for the
    ``scripts/office2/*.service`` add in that range, and reconcile MUST reach a
    rebaseline.

    On the PRE-FIX code observe would be called with pre==post → not_required →
    NO token.  Here we assert a token IS written and reconcile completes.
    """
    # pre == post (the tick's own pull was a no-op).
    monkeypatch.setattr(
        tick,
        "_git",
        _git_mock(pre_sha=POST, post_sha=POST, cat_file_rc=0, ancestor_rc=0),
    )

    # Persist an OLDER watermark so the range base becomes watermark..post.
    wm_path = fake_repo / "rebaseline-observed-head.json"
    monkeypatch.setattr(rebaseline, "DEFAULT_OBSERVED_HEAD_PATH", wm_path)
    rebaseline.write_observed_head(WATERMARK, wm_path)

    token_path = fake_repo / "rebaseline-pending.json"
    monkeypatch.setattr(rebaseline, "DEFAULT_TOKEN_PATH", token_path)

    observe_bases: list[tuple[str, str]] = []

    def _fake_observe(base, post, **kw):
        observe_bases.append((base, post))
        # A real audited-surface add (a systemd .service) is in the range →
        # arm a token exactly as the real observe would.
        rebaseline.write_token(
            {
                "schema_version": 1,
                "pending_since_utc": rebaseline._utc_now_iso(),
                "observed_head_sha": post,
                "surface_ids": ["systemd-user-units"],
                "expected_baselines": ["enabled-services.txt", "systemd-user-units.txt"],
                "matched_files": ["scripts/office2/felix-deployer.service"],
                "last_check_utc": None,
                "alerts_emitted": [],
            },
            token_path,
        )
        return {
            "outcome": "pending_set",
            "surface_ids": ["systemd-user-units"],
            "matched_files": ["scripts/office2/felix-deployer.service"],
        }

    monkeypatch.setattr(rebaseline, "observe", _fake_observe)
    monkeypatch.setattr(
        rebaseline,
        "reconcile",
        lambda **kw: {
            "outcome": "completed",
            "rebaselined_at_utc": "2026-07-09T00:00:00Z",
            "baseline_count": 14,
        },
    )

    rc = tick.run_tick(repo_root=fake_repo, log_dir=log_dir)
    assert rc == 0

    # observe was driven from the WATERMARK base, not pre==post.
    assert observe_bases == [(WATERMARK, POST)]

    # A token WAS written (the pre-fix path would not have armed one).
    assert token_path.exists(), "out-of-band repro must arm a pending token"

    entries = _read_log(log_dir)
    obs = next(e for e in entries if e.get("event") == "rebaseline_observe")
    assert obs["range_source"] == "watermark"
    assert obs["base"] == WATERMARK
    rec = next(e for e in entries if e.get("event") == "rebaseline_reconcile")
    assert rec["outcome"] == "completed"


def test_fallback_base_when_no_watermark(monkeypatch, fake_repo, log_dir):
    """No watermark file → observe range base is pre_pull_head (legacy)."""
    monkeypatch.setattr(tick, "_git", _git_mock(pre_sha=PRE, post_sha=POST))

    wm_path = fake_repo / "rebaseline-observed-head.json"
    monkeypatch.setattr(rebaseline, "DEFAULT_OBSERVED_HEAD_PATH", wm_path)

    observe_bases: list[tuple[str, str]] = []
    monkeypatch.setattr(
        rebaseline,
        "observe",
        lambda base, post, **kw: observe_bases.append((base, post)) or {"outcome": "not_required"},
    )
    monkeypatch.setattr(rebaseline, "reconcile", lambda **kw: {"outcome": "not_required"})

    rc = tick.run_tick(repo_root=fake_repo, log_dir=log_dir)
    assert rc == 0
    assert observe_bases == [(PRE, POST)]
    entries = _read_log(log_dir)
    obs = next(e for e in entries if e.get("event") == "rebaseline_observe")
    assert obs["range_source"] == "fallback"


# ---------------------------------------------------------------------------
# Self-commit skip (SC-004)
# ---------------------------------------------------------------------------


def test_self_commit_skip_next_tick_empty_range(monkeypatch, fake_repo, log_dir):
    """After a deploy(applied) commit, the watermark advances to that commit;
    the next idle tick observes an empty range → not_required, no spurious token.

    Modeled here at the seam: a watermark equal to post yields base==post (valid
    ancestor of itself), so observe sees an empty range.
    """
    monkeypatch.setattr(
        tick, "_git", _git_mock(pre_sha=PRE, post_sha=POST, cat_file_rc=0, ancestor_rc=0)
    )

    wm_path = fake_repo / "rebaseline-observed-head.json"
    monkeypatch.setattr(rebaseline, "DEFAULT_OBSERVED_HEAD_PATH", wm_path)
    # Watermark already at post (our own commit from a prior tick).
    rebaseline.write_observed_head(POST, wm_path)

    observe_bases: list[tuple[str, str]] = []
    monkeypatch.setattr(
        rebaseline,
        "observe",
        lambda base, post, **kw: observe_bases.append((base, post)) or {"outcome": "not_required"},
    )
    monkeypatch.setattr(rebaseline, "reconcile", lambda **kw: {"outcome": "not_required"})

    rc = tick.run_tick(repo_root=fake_repo, log_dir=log_dir)
    assert rc == 0
    # base == post → empty range.
    assert observe_bases == [(POST, POST)]
    entries = _read_log(log_dir)
    obs = next(e for e in entries if e.get("event") == "rebaseline_observe")
    assert obs["outcome"] == "not_required"


def test_watermark_advances_to_post_when_no_own_commit(monkeypatch, fake_repo, log_dir):
    """An idle tick (no applied manifest) advances the watermark to post_pull_head."""
    monkeypatch.setattr(
        tick, "_git", _git_mock(pre_sha=PRE, post_sha=POST, cat_file_rc=0, ancestor_rc=0)
    )
    wm_path = fake_repo / "rebaseline-observed-head.json"
    monkeypatch.setattr(rebaseline, "DEFAULT_OBSERVED_HEAD_PATH", wm_path)
    rebaseline.write_observed_head(WATERMARK, wm_path)

    monkeypatch.setattr(rebaseline, "observe", lambda *a, **kw: {"outcome": "not_required"})
    monkeypatch.setattr(rebaseline, "reconcile", lambda **kw: {"outcome": "not_required"})

    rc = tick.run_tick(repo_root=fake_repo, log_dir=log_dir)
    assert rc == 0
    assert rebaseline.read_observed_head(wm_path) == POST
    entries = _read_log(log_dir)
    wm_entry = next(e for e in entries if e.get("event") == "rebaseline_watermark")
    assert wm_entry["observed_head_sha"] == POST


def test_transient_classification_leaves_watermark_unchanged(monkeypatch, fake_repo, log_dir):
    """A transient watermark classification (merge-base error rc) must NOT
    advance the watermark (Codex HIGH-1)."""
    # cat-file ok (rc=0) but merge-base returns rc=128 (neither 0 nor 1) →
    # classify_watermark → transient.
    monkeypatch.setattr(
        tick, "_git", _git_mock(pre_sha=PRE, post_sha=POST, cat_file_rc=0, ancestor_rc=128)
    )
    wm_path = fake_repo / "rebaseline-observed-head.json"
    monkeypatch.setattr(rebaseline, "DEFAULT_OBSERVED_HEAD_PATH", wm_path)
    rebaseline.write_observed_head(WATERMARK, wm_path)

    monkeypatch.setattr(rebaseline, "observe", lambda *a, **kw: {"outcome": "not_required"})
    monkeypatch.setattr(rebaseline, "reconcile", lambda **kw: {"outcome": "not_required"})

    rc = tick.run_tick(repo_root=fake_repo, log_dir=log_dir)
    assert rc == 0
    # Watermark UNCHANGED on transient.
    assert rebaseline.read_observed_head(wm_path) == WATERMARK
    entries = _read_log(log_dir)
    obs = next(e for e in entries if e.get("event") == "rebaseline_observe")
    assert obs["range_source"] == "transient"
    assert not any(e.get("event") == "rebaseline_watermark" for e in entries)


# ---------------------------------------------------------------------------
# Push-fail SHA capture (Codex MED-1)
# ---------------------------------------------------------------------------


def test_record_success_captures_sha_on_push_fail(monkeypatch, fake_repo_with_manifest, log_dir):
    """When git push fails, _record_success returns ok=False but still carries
    the captured commit_sha; the watermark advances to that SHA."""
    from scripts.deploy.lib import apply as _apply_lib

    OWN_COMMIT = "cafe0001" * 5

    def _fake_git(args, cwd):
        cmd = args[0] if args else ""
        if cmd == "pull":
            return _FakeProc(returncode=0)
        if cmd == "rev-parse":
            # 1st = pre, 2nd = post, 3rd (inside _record_success) = own commit,
            # later rev-parse (if any) = own commit again.
            if not getattr(_fake_git, "_pre", False):
                _fake_git._pre = True
                return _FakeProc(returncode=0, stdout=PRE + "\n")
            if not getattr(_fake_git, "_post", False):
                _fake_git._post = True
                return _FakeProc(returncode=0, stdout=POST + "\n")
            return _FakeProc(returncode=0, stdout=OWN_COMMIT + "\n")
        if cmd == "push":
            return _FakeProc(returncode=1, stderr="rejected: non-fast-forward")
        if cmd == "merge-base":
            # is-ancestor(post, own_commit) → yes (rc 0); classify → valid.
            return _FakeProc(returncode=0)
        if cmd == "cat-file":
            return _FakeProc(returncode=0)
        # rm / add / commit succeed.
        return _FakeProc(returncode=0)

    monkeypatch.setattr(tick, "_git", _fake_git)

    wm_path = fake_repo_with_manifest / "rebaseline-observed-head.json"
    monkeypatch.setattr(rebaseline, "DEFAULT_OBSERVED_HEAD_PATH", wm_path)
    rebaseline.write_observed_head(WATERMARK, wm_path)

    # Make write_applied succeed with a path inside applied/.
    from scripts.deploy.lib import applied as _applied_lib
    from scripts.deploy.lib import LibResult as _LibResult

    applied_path = fake_repo_with_manifest / "deploys" / "applied" / "0099-test-deploy.yaml"

    monkeypatch.setattr(
        _applied_lib,
        "write_applied",
        lambda *a, **kw: _LibResult(ok=True, summary="ok", details={"path": str(applied_path)}),
    )

    class _OkResult:
        ok = True
        summary = "dry-run ok"
        details: dict = {}

    monkeypatch.setattr(_apply_lib, "dry_run_then_apply_gate", lambda *a, **kw: _OkResult())
    monkeypatch.setattr(rebaseline, "observe", lambda *a, **kw: {"outcome": "not_required"})
    monkeypatch.setattr(rebaseline, "reconcile", lambda **kw: {"outcome": "not_required"})

    rc = tick.run_tick(repo_root=fake_repo_with_manifest, log_dir=log_dir)
    assert rc == 0

    # Push failed → manifest recorded as applied_record_failed, but the
    # captured own commit SHA still advanced the watermark.
    assert rebaseline.read_observed_head(wm_path) == OWN_COMMIT
    entries = _read_log(log_dir)
    wm_entry = next(e for e in entries if e.get("event") == "rebaseline_watermark")
    assert wm_entry["observed_head_sha"] == OWN_COMMIT
    assert OWN_COMMIT in wm_entry["own_commits"]


def test_record_result_dataclass_shape(monkeypatch, fake_repo_with_manifest):
    """_record_success returns a structured _RecordResult with the documented fields."""
    from scripts.deploy.lib import applied as _applied_lib
    from scripts.deploy.lib import LibResult as _LibResult

    applied_path = fake_repo_with_manifest / "deploys" / "applied" / "0099-test-deploy.yaml"
    monkeypatch.setattr(
        _applied_lib,
        "write_applied",
        lambda *a, **kw: _LibResult(ok=True, summary="ok", details={"path": str(applied_path)}),
    )

    OWN = "beef0002" * 5

    def _fake_git(args, cwd):
        cmd = args[0] if args else ""
        if cmd == "rev-parse":
            return _FakeProc(returncode=0, stdout=OWN + "\n")
        return _FakeProc(returncode=0)

    monkeypatch.setattr(tick, "_git", _fake_git)

    manifest_path = fake_repo_with_manifest / "deploys" / "queued" / "0099-test-deploy.yaml"
    res = tick._record_success(
        fake_repo_with_manifest,
        manifest_path,
        {"name": "0099-test-deploy"},
        "deadbeef",
    )
    assert isinstance(res, tick._RecordResult)
    assert res.ok is True
    assert res.pushed is True
    assert res.commit_sha == OWN
    assert res.applied_path == str(applied_path)


# ---------------------------------------------------------------------------
# Declared-baseline fold end-to-end (SC-002)
# ---------------------------------------------------------------------------


def test_declared_baseline_fold_end_to_end(monkeypatch, fake_repo_with_manifest_declared, log_dir):
    """A manifest declaring expected_baselines is applied → fold_manifest_baselines
    puts those baselines into the token so reconcile can service the drift."""
    from scripts.deploy.lib import apply as _apply_lib

    monkeypatch.setattr(tick, "_git", _git_mock(pre_sha=PRE, post_sha=POST))

    wm_path = fake_repo_with_manifest_declared / "rebaseline-observed-head.json"
    token_path = fake_repo_with_manifest_declared / "rebaseline-pending.json"
    monkeypatch.setattr(rebaseline, "DEFAULT_OBSERVED_HEAD_PATH", wm_path)
    monkeypatch.setattr(rebaseline, "DEFAULT_TOKEN_PATH", token_path)

    class _OkResult:
        ok = True
        summary = "dry-run ok"
        details: dict = {}

    monkeypatch.setattr(_apply_lib, "dry_run_then_apply_gate", lambda *a, **kw: _OkResult())
    # _record_success stubbed to succeed (no real git tree needed).
    monkeypatch.setattr(
        tick,
        "_record_success",
        lambda repo_root, manifest_path, manifest_data, head_sha: tick._RecordResult(
            ok=True, commit_sha=None, pushed=True,
            applied_path=str(repo_root / "deploys" / "applied" / "x.yaml"),
        ),
    )
    # observe finds nothing (the manifest move itself has no repo-file signal).
    monkeypatch.setattr(rebaseline, "observe", lambda *a, **kw: {"outcome": "not_required"})

    rec_seen: dict = {}

    def _real_reconcile(**kw):
        # Read the token the fold created and confirm the declared baseline is in E.
        tok = rebaseline.read_token(token_path)
        rec_seen["token"] = tok
        return {"outcome": "completed", "rebaselined_at_utc": "t", "baseline_count": 14}

    monkeypatch.setattr(rebaseline, "reconcile", _real_reconcile)

    rc = tick.run_tick(repo_root=fake_repo_with_manifest_declared, log_dir=log_dir)
    assert rc == 0

    # The fold created a token carrying the declared baseline.
    assert rec_seen["token"] is not None
    assert "openclaw-cron.txt" in rec_seen["token"]["expected_baselines"]
    assert rec_seen["token"]["surface_ids"] == ["manifest-declared"]

    entries = _read_log(log_dir)
    fold = next(e for e in entries if e.get("event") == "rebaseline_fold")
    assert fold["outcome"] == "created"
    assert "openclaw-cron.txt" in fold["expected_baselines"]


@pytest.fixture()
def fake_repo_with_manifest_declared(tmp_path: pathlib.Path) -> pathlib.Path:
    """Repo with a queued manifest that declares expected_baselines."""
    import yaml

    for sub in ("queued", "applied", "failed", "schema"):
        (tmp_path / "deploys" / sub).mkdir(parents=True, exist_ok=True)

    manifest = {
        "name": "0099-cron-deploy",
        "tier": 3,
        "entrypoint": "scripts/noop.sh",
        "audited_surface": True,
        "expected_baselines": ["openclaw-cron.txt"],
    }
    (tmp_path / "deploys" / "queued" / "0099-cron-deploy.yaml").write_text(
        yaml.safe_dump(manifest), encoding="utf-8"
    )
    return tmp_path


# ---------------------------------------------------------------------------
# No-crash regressions (NFR-001)
# ---------------------------------------------------------------------------


def test_watermark_read_exception_swallowed(monkeypatch, fake_repo, log_dir):
    """read_observed_head raising → tick returns 0 (rebaseline_error logged)."""
    monkeypatch.setattr(tick, "_git", _git_mock())

    def _boom(*a, **kw):
        raise RuntimeError("watermark read boom")

    monkeypatch.setattr(rebaseline, "read_observed_head", _boom)
    monkeypatch.setattr(rebaseline, "observe", lambda *a, **kw: {"outcome": "not_required"})
    monkeypatch.setattr(rebaseline, "reconcile", lambda **kw: {"outcome": "not_required"})

    rc = tick.run_tick(repo_root=fake_repo, log_dir=log_dir)
    assert rc == 0
    entries = _read_log(log_dir)
    assert any(e.get("event") == "rebaseline_error" for e in entries)


def test_watermark_write_exception_does_not_crash(monkeypatch, fake_repo, log_dir):
    """write_observed_head raising during advance → tick still returns 0."""
    monkeypatch.setattr(tick, "_git", _git_mock(cat_file_rc=0, ancestor_rc=0))
    wm_path = fake_repo / "rebaseline-observed-head.json"
    monkeypatch.setattr(rebaseline, "DEFAULT_OBSERVED_HEAD_PATH", wm_path)
    rebaseline.write_observed_head(WATERMARK, wm_path)

    monkeypatch.setattr(rebaseline, "observe", lambda *a, **kw: {"outcome": "not_required"})
    monkeypatch.setattr(rebaseline, "reconcile", lambda **kw: {"outcome": "not_required"})

    def _boom_write(*a, **kw):
        raise RuntimeError("watermark write boom")

    monkeypatch.setattr(rebaseline, "write_observed_head", _boom_write)

    rc = tick.run_tick(repo_root=fake_repo, log_dir=log_dir)
    assert rc == 0
    entries = _read_log(log_dir)
    # The advance failure is caught and logged as rebaseline_watermark_error.
    assert any(e.get("event") == "rebaseline_watermark_error" for e in entries)


def test_fold_exception_swallowed(monkeypatch, fake_repo_with_manifest_declared, log_dir):
    """fold_manifest_baselines raising → tick returns 0."""
    from scripts.deploy.lib import apply as _apply_lib

    monkeypatch.setattr(tick, "_git", _git_mock())
    wm_path = fake_repo_with_manifest_declared / "rebaseline-observed-head.json"
    monkeypatch.setattr(rebaseline, "DEFAULT_OBSERVED_HEAD_PATH", wm_path)

    class _OkResult:
        ok = True
        summary = "dry-run ok"
        details: dict = {}

    monkeypatch.setattr(_apply_lib, "dry_run_then_apply_gate", lambda *a, **kw: _OkResult())
    monkeypatch.setattr(
        tick,
        "_record_success",
        lambda *a, **kw: tick._RecordResult(ok=True, pushed=True, applied_path="x"),
    )
    monkeypatch.setattr(rebaseline, "observe", lambda *a, **kw: {"outcome": "not_required"})

    def _boom_fold(*a, **kw):
        raise RuntimeError("fold boom")

    monkeypatch.setattr(rebaseline, "fold_manifest_baselines", _boom_fold)
    monkeypatch.setattr(rebaseline, "reconcile", lambda **kw: {"outcome": "not_required"})

    rc = tick.run_tick(repo_root=fake_repo_with_manifest_declared, log_dir=log_dir)
    assert rc == 0
    entries = _read_log(log_dir)
    assert any(e.get("event") == "rebaseline_error" for e in entries)


# ---------------------------------------------------------------------------
# Backward compatibility (FR-009)
# ---------------------------------------------------------------------------


def test_backward_compat_manifest_without_expected_baselines(
    monkeypatch, fake_repo_with_manifest, log_dir
):
    """A manifest with NO expected_baselines behaves exactly as before: no fold
    entry is emitted and the tick completes normally."""
    from scripts.deploy.lib import apply as _apply_lib

    monkeypatch.setattr(tick, "_git", _git_mock())
    wm_path = fake_repo_with_manifest / "rebaseline-observed-head.json"
    monkeypatch.setattr(rebaseline, "DEFAULT_OBSERVED_HEAD_PATH", wm_path)

    class _OkResult:
        ok = True
        summary = "dry-run ok"
        details: dict = {}

    monkeypatch.setattr(_apply_lib, "dry_run_then_apply_gate", lambda *a, **kw: _OkResult())
    monkeypatch.setattr(
        tick,
        "_record_success",
        lambda repo_root, manifest_path, manifest_data, head_sha: tick._RecordResult(
            ok=True, pushed=True,
            applied_path=str(repo_root / "deploys" / "applied" / "0099-test-deploy.yaml"),
        ),
    )
    fold_calls: list = []
    monkeypatch.setattr(
        rebaseline,
        "fold_manifest_baselines",
        lambda *a, **kw: fold_calls.append(True) or {"outcome": "not_required"},
    )
    monkeypatch.setattr(rebaseline, "observe", lambda *a, **kw: {"outcome": "not_required"})
    monkeypatch.setattr(rebaseline, "reconcile", lambda **kw: {"outcome": "not_required"})

    rc = tick.run_tick(repo_root=fake_repo_with_manifest, log_dir=log_dir)
    assert rc == 0
    # No declared baselines → fold is never invoked.
    assert fold_calls == []
    entries = _read_log(log_dir)
    assert not any(e.get("event") == "rebaseline_fold" for e in entries)
    # Manifest still applied.
    assert any(
        e.get("event") == "manifest_processed" and e.get("outcome") == "applied"
        for e in entries
    )


def test_legacy_tuple_record_success_still_supported(monkeypatch, fake_repo_with_manifest, log_dir):
    """A monkeypatched _record_success returning a legacy (ok, summary) tuple is
    coerced and does not crash the tick (compat shim)."""
    from scripts.deploy.lib import apply as _apply_lib

    monkeypatch.setattr(tick, "_git", _git_mock())
    wm_path = fake_repo_with_manifest / "rebaseline-observed-head.json"
    monkeypatch.setattr(rebaseline, "DEFAULT_OBSERVED_HEAD_PATH", wm_path)

    class _OkResult:
        ok = True
        summary = "dry-run ok"
        details: dict = {}

    monkeypatch.setattr(_apply_lib, "dry_run_then_apply_gate", lambda *a, **kw: _OkResult())
    monkeypatch.setattr(
        tick,
        "_record_success",
        lambda repo_root, manifest_path, manifest_data, head_sha: (
            True,
            str(repo_root / "deploys" / "applied" / "0099-test-deploy.yaml"),
        ),
    )
    monkeypatch.setattr(rebaseline, "observe", lambda *a, **kw: {"outcome": "not_required"})
    monkeypatch.setattr(rebaseline, "reconcile", lambda **kw: {"outcome": "not_required"})

    rc = tick.run_tick(repo_root=fake_repo_with_manifest, log_dir=log_dir)
    assert rc == 0
    entries = _read_log(log_dir)
    assert any(
        e.get("event") == "manifest_processed" and e.get("outcome") == "applied"
        for e in entries
    )


# ---------------------------------------------------------------------------
# Codex post-merge HIGH-1 — declared-baseline fold survives a push failure
# ---------------------------------------------------------------------------


def test_declared_fold_survives_push_failure(
    monkeypatch, fake_repo_with_manifest_declared, log_dir
):
    """HIGH-1: apply succeeds but the applied-record push fails
    (``rec.ok=False`` with a ``commit_sha`` set).  The office2 mutation already
    happened, so the manifest-declared ``expected_baselines`` MUST still be
    folded into the pending token — reconcile must see the declared baseline in
    E.  Pre-fix, the fold was gated on ``rec.ok`` and this token would be empty.
    """
    from scripts.deploy.lib import apply as _apply_lib

    monkeypatch.setattr(tick, "_git", _git_mock(pre_sha=PRE, post_sha=POST))

    wm_path = fake_repo_with_manifest_declared / "rebaseline-observed-head.json"
    token_path = fake_repo_with_manifest_declared / "rebaseline-pending.json"
    monkeypatch.setattr(rebaseline, "DEFAULT_OBSERVED_HEAD_PATH", wm_path)
    monkeypatch.setattr(rebaseline, "DEFAULT_TOKEN_PATH", token_path)

    class _OkResult:
        ok = True
        summary = "dry-run ok"
        details: dict = {}

    monkeypatch.setattr(_apply_lib, "dry_run_then_apply_gate", lambda *a, **kw: _OkResult())

    OWN_COMMIT = "d00dfeed" * 5

    # Apply succeeds, but the applied-record PUSH fails: ok=False, but the
    # deployer's own commit SHA was captured before the push blew up.
    monkeypatch.setattr(
        tick,
        "_record_success",
        lambda repo_root, manifest_path, manifest_data, head_sha: tick._RecordResult(
            ok=False,
            commit_sha=OWN_COMMIT,
            pushed=False,
            applied_path=str(repo_root / "deploys" / "applied" / "x.yaml"),
            error="git push failed: rejected",
        ),
    )
    # observe finds nothing (the manifest move itself has no repo-file signal).
    monkeypatch.setattr(rebaseline, "observe", lambda *a, **kw: {"outcome": "not_required"})

    rec_seen: dict = {}

    def _real_reconcile(**kw):
        rec_seen["token"] = rebaseline.read_token(token_path)
        return {"outcome": "not_required"}

    monkeypatch.setattr(rebaseline, "reconcile", _real_reconcile)

    rc = tick.run_tick(repo_root=fake_repo_with_manifest_declared, log_dir=log_dir)
    assert rc == 0

    # The record push failed (applied_record_failed logged) …
    entries = _read_log(log_dir)
    assert any(
        e.get("event") == "manifest_processed"
        and e.get("outcome") == "applied_record_failed"
        for e in entries
    ), "push failure must be logged as applied_record_failed"

    # … but the fold still ran and armed the token with the declared baseline,
    # so reconcile would see it as EXPECTED drift.
    assert rec_seen["token"] is not None, (
        "fold must arm a token even when the applied-record push fails"
    )
    assert "openclaw-cron.txt" in rec_seen["token"]["expected_baselines"]

    fold = next(e for e in entries if e.get("event") == "rebaseline_fold")
    assert "openclaw-cron.txt" in fold["expected_baselines"]

    # The captured own commit SHA still advanced the watermark past our commit.
    assert rebaseline.read_observed_head(wm_path) == OWN_COMMIT


# ---------------------------------------------------------------------------
# Codex post-merge HIGH-2 — expected_baselines rejected PRE-apply
# ---------------------------------------------------------------------------


@pytest.fixture()
def fake_repo_with_bogus_baseline(tmp_path: pathlib.Path) -> pathlib.Path:
    """Queued manifest declaring an unknown baseline (registry-invalid)."""
    import yaml

    for sub in ("queued", "applied", "failed", "schema"):
        (tmp_path / "deploys" / sub).mkdir(parents=True, exist_ok=True)

    manifest = {
        "name": "0099-bogus-deploy",
        "tier": 3,
        "entrypoint": "scripts/noop.sh",
        "audited_surface": True,
        "expected_baselines": ["bogus.txt"],  # not in the registry
    }
    (tmp_path / "deploys" / "queued" / "0099-bogus-deploy.yaml").write_text(
        yaml.safe_dump(manifest), encoding="utf-8"
    )
    return tmp_path


def test_bogus_expected_baseline_rejected_before_apply(
    monkeypatch, fake_repo_with_bogus_baseline, log_dir
):
    """HIGH-2: a manifest whose ``expected_baselines`` names an unknown baseline
    is rejected BEFORE the entrypoint runs.  The apply gate (office2 mutation)
    must NEVER be invoked and a manifest_validation failure record is written.
    """
    from scripts.deploy.lib import apply as _apply_lib

    monkeypatch.setattr(tick, "_git", _git_mock(pre_sha=PRE, post_sha=POST))
    monkeypatch.setattr(rebaseline, "observe", lambda *a, **kw: {"outcome": "not_required"})
    monkeypatch.setattr(rebaseline, "reconcile", lambda **kw: {"outcome": "not_required"})

    # Spy on the apply gate: it must NOT be called for a pre-apply-rejected manifest.
    apply_calls: list = []

    def _spy_apply(*a, **kw):
        apply_calls.append(a)

        class _R:
            ok = True
            summary = "should-not-run"
            details: dict = {}

        return _R()

    monkeypatch.setattr(_apply_lib, "dry_run_then_apply_gate", _spy_apply)

    # _record_success must also never run.
    record_calls: list = []
    monkeypatch.setattr(
        tick,
        "_record_success",
        lambda *a, **kw: record_calls.append(a)
        or tick._RecordResult(ok=True, pushed=True, applied_path="x"),
    )

    rc = tick.run_tick(repo_root=fake_repo_with_bogus_baseline, log_dir=log_dir)
    assert rc == 0

    # The entrypoint / apply gate was NEVER invoked (office2 untouched).
    assert apply_calls == [], "apply gate must not run for a pre-apply-rejected manifest"
    assert record_calls == [], "_record_success must not run when apply was skipped"

    # A manifest_validation failure record was written.
    failed_dir = fake_repo_with_bogus_baseline / "deploys" / "failed"
    failed_files = list(failed_dir.glob("0099-bogus-deploy-*.yaml"))
    assert failed_files, "a manifest_validation failure record must be written"

    entries = _read_log(log_dir)
    assert any(
        e.get("event") == "manifest_processed"
        and e.get("outcome") == "failed_manifest_validation"
        for e in entries
    ), "the tick log must record failed_manifest_validation"


# ---------------------------------------------------------------------------
# Codex post-merge HIGH-3 — malformed registry never crashes the tick
# ---------------------------------------------------------------------------


def test_malformed_registry_degrades_and_tick_returns_zero(
    monkeypatch, fake_repo, log_dir, tmp_path
):
    """HIGH-3: with a malformed audited-surfaces registry, ``observe`` and
    ``reconcile`` must degrade gracefully (``not_required`` / ``inconclusive``)
    WITHOUT raising ``SystemExit``, and ``run_tick`` must return 0.

    Pre-fix, observe/reconcile defaulted to ``load_audited_surfaces()`` which
    calls ``sys.exit(2)`` on a malformed registry; ``run_tick``'s wrapper caught
    ``Exception`` (not ``SystemExit``) → the tick would crash.
    """
    import audited_surfaces as _as

    # Point the registry at a malformed JSON file.
    bad_registry = tmp_path / "audited-surfaces.json"
    bad_registry.write_text("{ this is not valid json ", encoding="utf-8")
    monkeypatch.setattr(_as, "AUDITED_SURFACES_PATH", bad_registry)

    # A pending token exists so reconcile actually reaches the registry read.
    token_path = fake_repo / "rebaseline-pending.json"
    monkeypatch.setattr(rebaseline, "DEFAULT_TOKEN_PATH", token_path)
    rebaseline.write_token(
        {
            "schema_version": 1,
            "pending_since_utc": "2020-01-01T00:00:00Z",
            "observed_head_sha": POST,
            "surface_ids": ["s1"],
            "expected_baselines": ["openclaw-cron.txt"],
            "matched_files": [],
            "last_check_utc": None,
            "alerts_emitted": [],
        },
        token_path,
    )

    # Direct-call assertions: neither raises SystemExit, both degrade.
    obs = rebaseline.observe(PRE, POST, token_path=token_path)
    assert obs["outcome"] == rebaseline.OUTCOME_NOT_REQUIRED

    rec = rebaseline.reconcile(token_path=token_path)
    assert rec["outcome"] == rebaseline.OUTCOME_INCONCLUSIVE

    # End-to-end: the tick uses the real (unmocked) observe/reconcile and must
    # still return 0 with the malformed registry in place.
    monkeypatch.setattr(tick, "_git", _git_mock(pre_sha=PRE, post_sha=POST))
    rc = tick.run_tick(repo_root=fake_repo, log_dir=log_dir)
    assert rc == 0


# ---------------------------------------------------------------------------
# #688 — stamp the reconcile outcome onto the applied deploy record
# ---------------------------------------------------------------------------


def test_build_rebaseline_annotation_per_outcome():
    a = tick._build_rebaseline_annotation("completed", {"baseline_count": 14})
    assert a["outcome"] == "completed" and a["baseline_count"] == 14 and a["at_utc"]

    f = tick._build_rebaseline_annotation("failed", {"error_summary": "boom"})
    assert f["outcome"] == "failed" and f["error_summary"] == "boom"

    u = tick._build_rebaseline_annotation(
        "unexpected_drift", {"unexpected": ["openclaw-cron.txt"]}
    )
    assert u["unexpected"] == ["openclaw-cron.txt"]

    n = tick._build_rebaseline_annotation("not_required", {})
    assert n["outcome"] == "not_required" and set(n) == {"outcome", "at_utc"}


def _write_valid_applied_record(path: pathlib.Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "schema_version: v1",
                "name: test-deploy",
                "mission_slug: felix-deployer-rebaseline-detection-01KX26DS",
                "tier: 3",
                "entrypoint: scripts/deploy/deploy-test.py",
                "audited_surface: false",
                "created_at: '2026-07-09T12:00:00Z'",
                "created_by: felix-deployer",
                "apply_mode: manifest",
                "applied_at: '2026-07-09T12:00:00Z'",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_reconcile_outcome_stamped_onto_applied_record(
    monkeypatch, fake_repo_with_manifest, log_dir
):
    """A deploy applied this tick has the reconcile outcome written onto its
    applied YAML in a second commit, and that commit becomes the watermark."""
    import yaml

    from scripts.deploy.lib import apply as _apply_lib

    STAMP = "5ada5ada" * 5
    applied_path = fake_repo_with_manifest / "deploys" / "applied" / "0099-test-deploy.yaml"
    _write_valid_applied_record(applied_path)

    def _fake_git(args, cwd):
        cmd = args[0] if args else ""
        if cmd == "rev-parse":
            if not getattr(_fake_git, "_pre", False):
                _fake_git._pre = True
                return _FakeProc(returncode=0, stdout=PRE + "\n")
            if not getattr(_fake_git, "_post", False):
                _fake_git._post = True
                return _FakeProc(returncode=0, stdout=POST + "\n")
            return _FakeProc(returncode=0, stdout=STAMP + "\n")  # post-stamp-commit HEAD
        return _FakeProc(returncode=0)  # pull/add/commit/push/merge-base/cat-file ok

    monkeypatch.setattr(tick, "_git", _fake_git)

    wm_path = fake_repo_with_manifest / "rebaseline-observed-head.json"
    monkeypatch.setattr(rebaseline, "DEFAULT_OBSERVED_HEAD_PATH", wm_path)
    rebaseline.write_observed_head(WATERMARK, wm_path)

    # _record_success succeeds and returns the real applied-record path.
    monkeypatch.setattr(
        tick,
        "_record_success",
        lambda repo_root, manifest_path, manifest_data, head_sha: tick._RecordResult(
            ok=True, pushed=True, commit_sha="dep10000" * 5, applied_path=str(applied_path)
        ),
    )

    class _OkResult:
        ok = True
        summary = "ok"
        details: dict = {}

    monkeypatch.setattr(_apply_lib, "dry_run_then_apply_gate", lambda *a, **kw: _OkResult())
    monkeypatch.setattr(rebaseline, "observe", lambda *a, **kw: {"outcome": "not_required"})
    monkeypatch.setattr(
        rebaseline, "reconcile", lambda **kw: {"outcome": "completed", "baseline_count": 14}
    )

    rc = tick.run_tick(repo_root=fake_repo_with_manifest, log_dir=log_dir)
    assert rc == 0

    # The applied record on disk now carries the rebaseline outcome.
    written = yaml.safe_load(applied_path.read_text(encoding="utf-8"))
    assert written["rebaseline"]["outcome"] == "completed"
    assert written["rebaseline"]["baseline_count"] == 14

    entries = _read_log(log_dir)
    stamped = next(e for e in entries if e.get("event") == "rebaseline_record_stamped")
    assert stamped["outcome"] == "completed"
    assert "deploys/applied/0099-test-deploy.yaml" in stamped["applied_records"]

    # The stamp commit is the deployer's last own commit → the new watermark.
    assert rebaseline.read_observed_head(wm_path) == STAMP


def test_record_stamp_failure_never_crashes_tick(
    monkeypatch, fake_repo_with_manifest, log_dir
):
    """If stamping raises, the tick logs the error and still returns 0 (NFR-001)."""
    from scripts.deploy.lib import apply as _apply_lib
    from scripts.deploy.lib import applied as _applied_lib

    applied_path = fake_repo_with_manifest / "deploys" / "applied" / "0099-test-deploy.yaml"
    _write_valid_applied_record(applied_path)

    monkeypatch.setattr(tick, "_git", lambda args, cwd: _FakeProc(returncode=0, stdout=POST + "\n"))
    wm_path = fake_repo_with_manifest / "rebaseline-observed-head.json"
    monkeypatch.setattr(rebaseline, "DEFAULT_OBSERVED_HEAD_PATH", wm_path)

    monkeypatch.setattr(
        tick,
        "_record_success",
        lambda *a, **kw: tick._RecordResult(ok=True, pushed=True, applied_path=str(applied_path)),
    )

    class _OkResult:
        ok = True
        summary = "ok"
        details: dict = {}

    monkeypatch.setattr(_apply_lib, "dry_run_then_apply_gate", lambda *a, **kw: _OkResult())
    monkeypatch.setattr(rebaseline, "observe", lambda *a, **kw: {"outcome": "not_required"})
    monkeypatch.setattr(rebaseline, "reconcile", lambda **kw: {"outcome": "completed"})

    def _boom(*a, **kw):
        raise RuntimeError("stamp exploded")

    monkeypatch.setattr(_applied_lib, "stamp_rebaseline", _boom)

    rc = tick.run_tick(repo_root=fake_repo_with_manifest, log_dir=log_dir)
    assert rc == 0
    entries = _read_log(log_dir)
    assert any(e.get("event") == "rebaseline_record_stamp_error" for e in entries)


def test_not_required_does_not_stamp_applied_record(
    monkeypatch, fake_repo_with_manifest, log_dir
):
    """A non-audited deploy (reconcile=not_required) leaves the applied record
    unstamped — no rebaseline field, no second commit."""
    import yaml

    from scripts.deploy.lib import apply as _apply_lib

    applied_path = fake_repo_with_manifest / "deploys" / "applied" / "0099-test-deploy.yaml"
    _write_valid_applied_record(applied_path)

    committed: list = []

    def _fake_git(args, cwd):
        if args and args[0] == "commit":
            committed.append(args)
        if args and args[0] == "rev-parse":
            return _FakeProc(returncode=0, stdout=POST + "\n")
        return _FakeProc(returncode=0)

    monkeypatch.setattr(tick, "_git", _fake_git)
    wm_path = fake_repo_with_manifest / "rebaseline-observed-head.json"
    monkeypatch.setattr(rebaseline, "DEFAULT_OBSERVED_HEAD_PATH", wm_path)
    monkeypatch.setattr(
        tick,
        "_record_success",
        lambda *a, **kw: tick._RecordResult(ok=True, pushed=True, applied_path=str(applied_path)),
    )

    class _OkResult:
        ok = True
        summary = "ok"
        details: dict = {}

    monkeypatch.setattr(_apply_lib, "dry_run_then_apply_gate", lambda *a, **kw: _OkResult())
    monkeypatch.setattr(rebaseline, "observe", lambda *a, **kw: {"outcome": "not_required"})
    monkeypatch.setattr(rebaseline, "reconcile", lambda **kw: {"outcome": "not_required"})

    rc = tick.run_tick(repo_root=fake_repo_with_manifest, log_dir=log_dir)
    assert rc == 0

    written = yaml.safe_load(applied_path.read_text(encoding="utf-8"))
    assert "rebaseline" not in written
    entries = _read_log(log_dir)
    assert not any(e.get("event") == "rebaseline_record_stamped" for e in entries)
    # No deploy(rebaseline) commit was made.
    assert not any("deploy(rebaseline)" in " ".join(a) for a in committed)


def test_stamp_commit_failure_restores_paths(
    monkeypatch, fake_repo_with_manifest, log_dir
):
    """If the stamp git commit fails, the stamped paths are restored from HEAD
    (git checkout HEAD -- <paths>) so no dirty state leaks to the next tick."""
    from scripts.deploy.lib import apply as _apply_lib

    applied_path = fake_repo_with_manifest / "deploys" / "applied" / "0099-test-deploy.yaml"
    _write_valid_applied_record(applied_path)

    calls: list = []

    def _fake_git(args, cwd):
        calls.append(list(args))
        cmd = args[0] if args else ""
        if cmd == "commit":
            return _FakeProc(returncode=1, stderr="nothing to commit / hook failed")
        if cmd == "rev-parse":
            return _FakeProc(returncode=0, stdout=POST + "\n")
        return _FakeProc(returncode=0)  # pull/add/checkout/merge-base/cat-file ok

    monkeypatch.setattr(tick, "_git", _fake_git)
    wm_path = fake_repo_with_manifest / "rebaseline-observed-head.json"
    monkeypatch.setattr(rebaseline, "DEFAULT_OBSERVED_HEAD_PATH", wm_path)
    monkeypatch.setattr(
        tick,
        "_record_success",
        lambda *a, **kw: tick._RecordResult(ok=True, pushed=True, applied_path=str(applied_path)),
    )

    class _OkResult:
        ok = True
        summary = "ok"
        details: dict = {}

    monkeypatch.setattr(_apply_lib, "dry_run_then_apply_gate", lambda *a, **kw: _OkResult())
    monkeypatch.setattr(rebaseline, "observe", lambda *a, **kw: {"outcome": "not_required"})
    monkeypatch.setattr(rebaseline, "reconcile", lambda **kw: {"outcome": "completed"})

    rc = tick.run_tick(repo_root=fake_repo_with_manifest, log_dir=log_dir)
    assert rc == 0

    # A restore (`git checkout HEAD -- <path>`) was issued after the failed commit.
    assert any(
        c[:3] == ["checkout", "HEAD", "--"] for c in calls
    ), f"expected a checkout-HEAD restore in {calls}"
    entries = _read_log(log_dir)
    assert any(
        e.get("event") == "rebaseline_record_stamp_error"
        and "git commit failed" in (e.get("reason") or "")
        for e in entries
    )
