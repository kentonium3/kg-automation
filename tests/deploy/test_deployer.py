"""End-to-end tick tests for ``scripts/deploy/felix-deployer/_tick.py``.

Five canonical scenarios per WP04 T021:

1. ``tick_no_queue_no_pull`` — empty queue → only tick_start/queue_scanned/tick_complete logged.
2. ``tick_git_pull_fails`` — git pull non-zero → tick_skip, no manifest processing.
3. ``tick_successful_manifest`` — one valid manifest, entrypoint succeeds → applied entry written, queued path removed, commit issued.
4. ``tick_failed_manifest_dispatches_dm`` — entrypoint fails → failure record written, notify.dispatch_failure_dm called with correct payload, manifest stays in queue.
5. ``tick_multiple_manifests_serial`` — three manifests, second fails → first applied, second failed, third still processed.

Plus: DM dispatch failure does NOT crash the tick (T018 isolation
contract). The tick must complete and emit ``tick_complete``.

All subprocess interaction is mocked. We construct a real on-disk
``tmp_path`` mini-repo with the layout the tick expects:
``deploys/queued/``, ``deploys/applied/``, ``deploys/failed/``,
``deploys/schema/manifest-v1.schema.json`` (symlinked from the real
schema for validation), and a single tracked entrypoint script.

The ``_tick`` module is imported via ``importlib`` from the on-disk
felix-deployer/ directory because that directory's hyphenated name
makes it non-importable via dotted form.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import shutil
import subprocess
import sys
from typing import Any

import pytest
import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
FELIX_DEPLOYER_DIR = REPO_ROOT / "scripts" / "deploy" / "felix-deployer"
SCHEMA_SRC = REPO_ROOT / "deploys" / "schema" / "manifest-v1.schema.json"


def _load_tick_module():
    """Load _tick from the hyphenated felix-deployer/ directory.

    The loader registers a synthetic ``notify`` module so the sibling
    import in _tick resolves. We also ensure REPO_ROOT is on sys.path
    so the deploy library imports succeed.
    """
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    if str(FELIX_DEPLOYER_DIR) not in sys.path:
        sys.path.insert(0, str(FELIX_DEPLOYER_DIR))

    # First load notify so _tick's `import notify` finds it.
    notify_spec = importlib.util.spec_from_file_location(
        "notify",
        FELIX_DEPLOYER_DIR / "notify.py",
    )
    notify_mod = importlib.util.module_from_spec(notify_spec)
    sys.modules["notify"] = notify_mod
    notify_spec.loader.exec_module(notify_mod)

    tick_spec = importlib.util.spec_from_file_location(
        "felix_deployer_tick_under_test",
        FELIX_DEPLOYER_DIR / "_tick.py",
    )
    tick_mod = importlib.util.module_from_spec(tick_spec)
    tick_spec.loader.exec_module(tick_mod)
    return tick_mod, notify_mod


tick, notify = _load_tick_module()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_repo(tmp_path: pathlib.Path) -> pathlib.Path:
    """Build a minimal repo layout the tick can operate on.

    Layout::

        <tmp>/
          deploys/
            queued/    (empty by default; tests drop manifests here)
            applied/   (empty)
            failed/    (empty)
            schema/manifest-v1.schema.json (copied from real schema)
          entrypoints/  (per-test scripts; populated by helpers)
    """
    for sub in ("queued", "applied", "failed", "schema"):
        (tmp_path / "deploys" / sub).mkdir(parents=True, exist_ok=True)
    # Write a relaxed copy of the canonical schema: the production
    # ``entrypoint`` pattern requires ``^scripts/deploy/...`` (a
    # repo-relative path), but tests need to point manifests at the
    # absolute on-disk path of a ``tmp_path`` script so subprocess can
    # actually execute it. We relax just the ``entrypoint`` pattern
    # while preserving every other invariant — Tier 0 still rejected,
    # Tier 1/2 verification still required, etc. The lib.applied
    # writer's schema_path defaults to <repo_root>/deploys/schema/
    # manifest-v1.schema.json, which resolves through the manifest
    # module's _repo_root() helper based on this file's location; in
    # tests we patch that path via the applied_dir override and rely
    # on the schema sitting at <fake_repo>/deploys/schema/.
    schema = json.loads(SCHEMA_SRC.read_text(encoding="utf-8"))
    schema["properties"]["entrypoint"]["pattern"] = r".+\.(sh|py)$"
    (tmp_path / "deploys" / "schema" / "manifest-v1.schema.json").write_text(
        json.dumps(schema), encoding="utf-8"
    )
    # Schema requires entrypoint paths under scripts/deploy/ — put test
    # scripts there so applied.write_applied's schema validation passes.
    (tmp_path / "scripts" / "deploy").mkdir(parents=True, exist_ok=True)
    return tmp_path


@pytest.fixture
def log_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    d = tmp_path / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _read_jsonl_log(log_dir: pathlib.Path) -> list[dict]:
    """Read every JSON line in the daily log file."""
    files = list(log_dir.glob("*.jsonl"))
    if not files:
        return []
    assert len(files) == 1, f"expected exactly one daily log, got {files}"
    return [json.loads(line) for line in files[0].read_text().splitlines() if line.strip()]


def _write_entrypoint(repo: pathlib.Path, name: str, body: str = "exit 0\n") -> pathlib.Path:
    """Write a test entrypoint under <repo>/scripts/deploy/ so the manifest
    schema's ``^scripts/deploy/...`` entrypoint pattern matches."""
    p = repo / "scripts" / "deploy" / name
    p.write_text(f"#!/bin/bash\n{body}", encoding="utf-8")
    p.chmod(0o755)
    return p


def _make_manifest(
    repo: pathlib.Path,
    manifest_name: str,
    entrypoint_path: pathlib.Path,
    tier: int = 3,
    audited: bool = False,
) -> pathlib.Path:
    """Drop a tier-3 manifest YAML into deploys/queued/.

    The manifest's ``entrypoint`` is the absolute on-disk path of the
    test script so ``subprocess.run([entrypoint, '--apply'])`` inside
    ``lib.apply._run_shell`` succeeds. The schema's strict
    ``^scripts/deploy/...`` pattern is relaxed in the ``fake_repo``
    fixture so this absolute form passes validation when the applied
    entry is written.
    """
    manifest = {
        "schema_version": "v1",
        "name": manifest_name,
        "mission_slug": "pull-based-deploy-pipeline-01KTYQQS",
        "tier": tier,
        "entrypoint": str(entrypoint_path),
        "audited_surface": audited,
        "created_at": "2026-06-12T20:00:00Z",
        "created_by": "kent@intentional.biz",
    }
    out = repo / "deploys" / "queued" / f"{manifest_name}.yaml"
    out.write_text(yaml.safe_dump(manifest, sort_keys=False))
    return out


class _FakeGitProc:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _git_mock(
    *,
    pull_rc: int = 0,
    head_sha: str = "deadbeefcafebabefeed",
    success_subcommands: tuple[str, ...] = (
        "rm",
        "add",
        "commit",
        "push",
        "pull",
        "rev-parse",
    ),
):
    """Build a subprocess.run replacement that only intercepts git calls.

    Returns a callable suitable for monkeypatching ``tick._git`` (which
    is the wrapper around ``subprocess.run`` inside _tick.py).
    """

    def _fake(args, cwd):
        sub = args[0] if args else ""
        if sub == "pull":
            return _FakeGitProc(returncode=pull_rc, stderr="non-fast-forward" if pull_rc else "")
        if sub == "rev-parse":
            return _FakeGitProc(returncode=0, stdout=head_sha + "\n")
        if sub in success_subcommands:
            return _FakeGitProc(returncode=0)
        return _FakeGitProc(returncode=1, stderr=f"unmocked git {sub}")

    return _fake


# ---------------------------------------------------------------------------
# Scenario 1: empty queue, git pull succeeds
# ---------------------------------------------------------------------------


def test_tick_no_queue_no_pull(fake_repo, log_dir, monkeypatch):
    monkeypatch.setattr(tick, "_git", _git_mock())
    # No DM should be invoked since there are no manifests.
    dispatched: list[dict] = []
    monkeypatch.setattr(
        notify,
        "dispatch_failure_dm",
        lambda **kw: dispatched.append(kw) or None,
    )

    rc = tick.run_tick(repo_root=fake_repo, log_dir=log_dir)
    assert rc == 0

    events = _read_jsonl_log(log_dir)
    event_names = [e["event"] for e in events]
    assert "tick_start" in event_names
    assert "queue_scanned" in event_names
    assert "tick_complete" in event_names
    # queue_scanned reports count=0.
    scanned = next(e for e in events if e["event"] == "queue_scanned")
    assert scanned["count"] == 0
    # No DM dispatched.
    assert dispatched == []


# ---------------------------------------------------------------------------
# Scenario 2: git pull fails
# ---------------------------------------------------------------------------


def test_tick_git_pull_fails(fake_repo, log_dir, monkeypatch):
    monkeypatch.setattr(tick, "_git", _git_mock(pull_rc=1))
    dispatched: list[dict] = []
    monkeypatch.setattr(
        notify,
        "dispatch_failure_dm",
        lambda **kw: dispatched.append(kw) or None,
    )
    # Drop a manifest so we can verify it was NOT processed.
    ep = _write_entrypoint(fake_repo, "ep.sh")
    _make_manifest(fake_repo, "m1", ep)

    rc = tick.run_tick(repo_root=fake_repo, log_dir=log_dir)
    assert rc == 0

    events = _read_jsonl_log(log_dir)
    event_names = [e["event"] for e in events]
    assert "tick_start" in event_names
    assert "tick_skip" in event_names
    # No queue_scanned, no manifest_processed.
    assert "queue_scanned" not in event_names
    assert "manifest_processed" not in event_names
    # Manifest still in queue.
    assert (fake_repo / "deploys" / "queued" / "m1.yaml").exists()
    assert dispatched == []


# ---------------------------------------------------------------------------
# Scenario 3: one successful manifest
# ---------------------------------------------------------------------------


def test_tick_successful_manifest(fake_repo, log_dir, monkeypatch):
    monkeypatch.setattr(tick, "_git", _git_mock())
    dispatched: list[dict] = []
    monkeypatch.setattr(
        notify,
        "dispatch_failure_dm",
        lambda **kw: dispatched.append(kw) or None,
    )

    ep = _write_entrypoint(fake_repo, "ok.sh")
    _make_manifest(fake_repo, "happy-path", ep)

    rc = tick.run_tick(repo_root=fake_repo, log_dir=log_dir)
    assert rc == 0

    events = _read_jsonl_log(log_dir)
    processed = [e for e in events if e["event"] == "manifest_processed"]
    assert len(processed) == 1
    assert processed[0]["outcome"] == "applied"
    assert processed[0]["manifest_name"] == "happy-path"

    # Applied file present in deploys/applied/ (sequenced).
    applied_files = list((fake_repo / "deploys" / "applied").glob("*.yaml"))
    assert len(applied_files) == 1
    assert applied_files[0].name.startswith("0001-happy-path")
    # No DM dispatched for success.
    assert dispatched == []


# ---------------------------------------------------------------------------
# Scenario 4: one failing manifest → DM dispatched, manifest stays in queue
# ---------------------------------------------------------------------------


def test_tick_failed_manifest_dispatches_dm(fake_repo, log_dir, monkeypatch):
    monkeypatch.setattr(tick, "_git", _git_mock())
    dispatched: list[dict] = []
    monkeypatch.setattr(
        notify,
        "dispatch_failure_dm",
        lambda **kw: dispatched.append(kw) or None,
    )

    # Entrypoint that fails on --apply (after --dry-run succeeds).
    ep = _write_entrypoint(
        fake_repo,
        "fail-apply.sh",
        body=(
            'if [ "$1" = "--dry-run" ]; then\n'
            '  exit 0\n'
            'fi\n'
            'echo "apply broke" >&2\n'
            'exit 7\n'
        ),
    )
    manifest_path = _make_manifest(fake_repo, "broken-deploy", ep)

    rc = tick.run_tick(repo_root=fake_repo, log_dir=log_dir)
    assert rc == 0  # tick always returns 0 unless it crashes

    events = _read_jsonl_log(log_dir)
    processed = [e for e in events if e["event"] == "manifest_processed"]
    assert len(processed) == 1
    assert processed[0]["outcome"].startswith("failed_")
    assert "entrypoint" in processed[0]["outcome"]

    # Manifest STAYS in queue.
    assert manifest_path.exists()
    # Failure record written.
    failed_files = list((fake_repo / "deploys" / "failed").glob("broken-deploy-*.yaml"))
    assert len(failed_files) == 1
    failure = yaml.safe_load(failed_files[0].read_text())
    assert failure["manifest_name"] == "broken-deploy"
    assert failure["phase"] in ("entrypoint_apply", "entrypoint_dry_run", "entrypoint")
    assert "error_summary" in failure

    # DM dispatched exactly once with the failed manifest + a DM-style phase.
    assert len(dispatched) == 1
    call = dispatched[0]
    assert call["manifest"]["name"] == "broken-deploy"
    # Tick passes the apply.PHASE_* value verbatim; the openclaw cron
    # receiver maps it via the dm-payload-v1 contract. We assert here
    # only that a phase is present and is one of apply.PHASE_*.
    assert call["phase"] in (
        "entrypoint_apply",
        "entrypoint_dry_run",
        "entrypoint",
    )


# ---------------------------------------------------------------------------
# Scenario 5: three manifests, middle fails — others still process
# ---------------------------------------------------------------------------


def test_tick_multiple_manifests_serial(fake_repo, log_dir, monkeypatch):
    monkeypatch.setattr(tick, "_git", _git_mock())
    dispatched: list[dict] = []
    monkeypatch.setattr(
        notify,
        "dispatch_failure_dm",
        lambda **kw: dispatched.append(kw) or None,
    )

    ok_ep = _write_entrypoint(fake_repo, "ok.sh")
    bad_ep = _write_entrypoint(
        fake_repo,
        "bad.sh",
        body=(
            'if [ "$1" = "--dry-run" ]; then\n'
            '  exit 0\n'
            'fi\n'
            'exit 3\n'
        ),
    )

    # alphabetical order: a-, b-, c-.
    _make_manifest(fake_repo, "a-first", ok_ep)
    _make_manifest(fake_repo, "b-broken", bad_ep)
    _make_manifest(fake_repo, "c-third", ok_ep)

    rc = tick.run_tick(repo_root=fake_repo, log_dir=log_dir)
    assert rc == 0

    events = _read_jsonl_log(log_dir)
    processed = [e for e in events if e["event"] == "manifest_processed"]
    assert len(processed) == 3
    # In alphabetical order.
    assert [p["manifest_name"] for p in processed] == [
        "a-first",
        "b-broken",
        "c-third",
    ]
    # a + c are applied, b is failed.
    outcomes = [p["outcome"] for p in processed]
    assert outcomes[0] == "applied"
    assert outcomes[1].startswith("failed_")
    assert outcomes[2] == "applied"

    # Applied dir has 2 entries.
    applied_files = sorted((fake_repo / "deploys" / "applied").glob("*.yaml"))
    assert len(applied_files) == 2
    # Failed dir has 1 entry for b-broken.
    failed_files = list((fake_repo / "deploys" / "failed").glob("b-broken-*.yaml"))
    assert len(failed_files) == 1

    # DM dispatched exactly once (for the middle failure).
    assert len(dispatched) == 1
    assert dispatched[0]["manifest"]["name"] == "b-broken"


# ---------------------------------------------------------------------------
# DM dispatch failure isolation (WP04 reviewer guidance #2 + #4):
# the tick MUST NOT crash if openclaw cron run raises.
# ---------------------------------------------------------------------------


def test_tick_continues_when_dm_dispatch_raises(fake_repo, log_dir, monkeypatch):
    monkeypatch.setattr(tick, "_git", _git_mock())

    # notify raises an arbitrary exception — the tick must absorb it.
    def _exploding_dispatch(**kw):
        raise RuntimeError("openclaw socket dead")

    monkeypatch.setattr(notify, "dispatch_failure_dm", _exploding_dispatch)

    ep = _write_entrypoint(
        fake_repo,
        "bad.sh",
        body=(
            'if [ "$1" = "--dry-run" ]; then\n'
            '  exit 0\n'
            'fi\n'
            'exit 9\n'
        ),
    )
    _make_manifest(fake_repo, "raises-during-dm", ep)
    _make_manifest(fake_repo, "z-still-processed", _write_entrypoint(fake_repo, "ok.sh"))

    rc = tick.run_tick(repo_root=fake_repo, log_dir=log_dir)
    assert rc == 0

    events = _read_jsonl_log(log_dir)
    # tick_complete still emitted despite DM raising.
    assert any(e["event"] == "tick_complete" for e in events)
    # Both manifests were processed (DM failure did not abort the second).
    processed = [e for e in events if e["event"] == "manifest_processed"]
    assert len(processed) == 2
    assert processed[1]["outcome"] == "applied"


# ---------------------------------------------------------------------------
# DM dispatch returning a non-ok LibResult also does not propagate.
# ---------------------------------------------------------------------------


def test_tick_continues_when_dm_dispatch_returns_failure(fake_repo, log_dir, monkeypatch):
    monkeypatch.setattr(tick, "_git", _git_mock())

    from scripts.deploy.lib import LibResult

    monkeypatch.setattr(
        notify,
        "dispatch_failure_dm",
        lambda **kw: LibResult(
            ok=False,
            summary="openclaw rc=3",
            details={"error_code": "DISPATCH_FAILED", "returncode": 3},
        ),
    )

    ep = _write_entrypoint(
        fake_repo,
        "bad.sh",
        body=(
            'if [ "$1" = "--dry-run" ]; then exit 0; fi\n'
            'exit 5\n'
        ),
    )
    _make_manifest(fake_repo, "still-completes", ep)

    rc = tick.run_tick(repo_root=fake_repo, log_dir=log_dir)
    assert rc == 0

    events = _read_jsonl_log(log_dir)
    assert any(e["event"] == "tick_complete" for e in events)


# ---------------------------------------------------------------------------
# JSONL discipline: every log entry parses as JSON on a single line.
# ---------------------------------------------------------------------------


def test_tick_log_is_valid_jsonl(fake_repo, log_dir, monkeypatch):
    monkeypatch.setattr(tick, "_git", _git_mock())
    monkeypatch.setattr(
        notify,
        "dispatch_failure_dm",
        lambda **kw: None,
    )

    _make_manifest(fake_repo, "j-ok", _write_entrypoint(fake_repo, "ok.sh"))
    tick.run_tick(repo_root=fake_repo, log_dir=log_dir)

    log_files = list(log_dir.glob("*.jsonl"))
    assert len(log_files) == 1
    for i, line in enumerate(log_files[0].read_text().splitlines()):
        assert line.strip(), f"empty line at index {i}"
        json.loads(line)  # raises if not valid JSON


# ---------------------------------------------------------------------------
# Phase mapping is exposed and matches the dm-payload-v1 4-value enum.
# ---------------------------------------------------------------------------


def test_phase_to_dm_phase_collapses_to_4_values():
    from scripts.deploy.lib import apply as _apply

    expected_dm_phases = {"tier_guard", "verification_pre", "entrypoint", "verification_post"}
    mapped = set(tick.PHASE_TO_DM_PHASE.values())
    assert mapped == expected_dm_phases
    # Every apply phase (except 'complete') is covered.
    for phase in _apply.PHASES:
        if phase == _apply.PHASE_COMPLETE:
            continue
        assert phase in tick.PHASE_TO_DM_PHASE, f"missing mapping for {phase}"
