"""Tests for :mod:`scripts.deploy.lib.apply`.

The first test (``test_round_trip_real_subprocess_entrypoint``) is the
T015 round-trip integration test — it loads a real fixture manifest,
writes a real shell-script entrypoint to ``tmp_path``, and asserts the
whole composition runs end-to-end with NO subprocess mocking.

The rest of the tests exercise every individual ``phase`` exit point
plus the module-level phase enum so drift from ``contracts/dm-payload-v1.md``
is caught at review time.
"""

from __future__ import annotations

import os
import pathlib
import sys

import pytest

from scripts.deploy.lib import LibResult, apply, manifest, snapshot, tier

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
FIXTURE_DIR = pathlib.Path(__file__).resolve().parent / "fixtures" / "manifests"


# ---------------------------------------------------------------------------
# T015: round-trip integration test — real subprocess, no mocks.
# ---------------------------------------------------------------------------


def test_round_trip_real_subprocess_entrypoint(tmp_path, monkeypatch):
    """End-to-end: real fixture manifest + real shell-script entrypoint.

    Asserts ``dry_run_then_apply_gate(manifest, manifest_path).ok is True``
    without any subprocess mocking — proves the whole composition wires
    together for a minimal Tier 3 manifest.
    """
    # 1. Load the canonical Tier 3 fixture.
    fixture_path = FIXTURE_DIR / "valid_tier3_minimal.yaml"
    mani = manifest.load_manifest(fixture_path)
    assert mani["tier"] == 3  # sanity

    # 2. Write a real entrypoint script that succeeds on --dry-run AND --apply.
    entrypoint = tmp_path / "real-entrypoint.sh"
    entrypoint.write_text(
        "#!/bin/bash\n"
        "# Real fixture entrypoint for the round-trip integration test.\n"
        "exit 0\n",
        encoding="utf-8",
    )
    entrypoint.chmod(0o755)

    # 3. Point the manifest at the real script.
    mani = dict(mani)
    mani["entrypoint"] = str(entrypoint)

    # 4. Run the orchestrator. No subprocess mocking.
    result = apply.dry_run_then_apply_gate(mani, str(fixture_path))

    assert isinstance(result, LibResult)
    assert result.ok is True, f"round-trip failed: {result.summary} / {dict(result.details)}"
    assert result.details["phase"] == "complete"
    assert result.summary == "applied"


# ---------------------------------------------------------------------------
# Phase enum: pinned to contracts/dm-payload-v1.md and data-model.md.
# ---------------------------------------------------------------------------


_EXPECTED_PHASES = (
    "tier_guard",
    "snapshot",
    "verification_pre",
    "entrypoint_dry_run",
    "entrypoint_apply",
    "verification_post",
    "complete",
)


def test_phase_enum_matches_contract():
    """Pin the phase enum to the contract. Any drift fails here."""
    assert apply.PHASES == _EXPECTED_PHASES


def test_phase_constants_are_strings():
    for name in _EXPECTED_PHASES:
        const_name = "PHASE_" + name.upper()
        assert getattr(apply, const_name) == name


# ---------------------------------------------------------------------------
# Helpers for building manifests + entrypoints in tests.
# ---------------------------------------------------------------------------


def _write_entrypoint(tmp_path: pathlib.Path, *, name: str = "ep.sh", body: str = "exit 0\n") -> pathlib.Path:
    """Write a shell-script entrypoint that responds to --dry-run / --apply.

    The default body unconditionally succeeds. Callers pass a *body* that
    branches on ``$1`` to fail one phase while succeeding the others.
    """
    p = tmp_path / name
    p.write_text(f"#!/bin/bash\n{body}", encoding="utf-8")
    p.chmod(0o755)
    return p


def _tier3_manifest(entrypoint_path: pathlib.Path, **overrides) -> dict:
    m = {
        "schema_version": "v1",
        "name": "phase-test",
        "mission_slug": "pull-based-deploy-pipeline-01KTYQQS",
        "tier": 3,
        "entrypoint": str(entrypoint_path),
        "audited_surface": False,
        "created_at": "2026-06-12T20:00:00Z",
        "created_by": "kent@intentional.biz",
    }
    m.update(overrides)
    return m


# ---------------------------------------------------------------------------
# Phase 1: tier_guard failure
# ---------------------------------------------------------------------------


def test_phase_tier_guard_failure(tmp_path):
    ep = _write_entrypoint(tmp_path)
    bad = _tier3_manifest(ep)
    bad["tier"] = 0  # Tier 0 always rejected

    result = apply.dry_run_then_apply_gate(bad, "/fake/path.yaml")

    assert result.ok is False
    assert result.details["phase"] == apply.PHASE_TIER_GUARD
    assert result.details["error_code"] == "TIER_0_REJECTED"


def test_phase_tier_guard_failure_on_missing_entrypoint(tmp_path):
    ep = tmp_path / "does-not-exist.sh"
    bad = _tier3_manifest(ep)

    result = apply.dry_run_then_apply_gate(bad, "/fake/path.yaml")

    assert result.ok is False
    assert result.details["phase"] == apply.PHASE_TIER_GUARD
    assert result.details["error_code"] == "ENTRYPOINT_NOT_FOUND"


# ---------------------------------------------------------------------------
# Phase 2: snapshot failure (Tier 2 only)
# ---------------------------------------------------------------------------


def test_phase_snapshot_failure_for_tier_2(tmp_path, monkeypatch):
    ep = _write_entrypoint(tmp_path)
    mani = _tier3_manifest(ep)
    mani["tier"] = 2
    mani["verification"] = {"pre": [], "post": []}

    def _bad_snapshot(*args, **kwargs):
        return LibResult(
            ok=False,
            summary="Restic too old",
            details={"error_code": "RESTIC_TOO_OLD"},
        )

    monkeypatch.setattr(snapshot, "verify_restic_recent", _bad_snapshot)

    result = apply.dry_run_then_apply_gate(mani, "/fake/path.yaml")

    assert result.ok is False
    assert result.details["phase"] == apply.PHASE_SNAPSHOT
    assert result.details["error_code"] == "RESTIC_TOO_OLD"


def test_snapshot_not_invoked_for_non_tier_2(tmp_path, monkeypatch):
    ep = _write_entrypoint(tmp_path)
    mani = _tier3_manifest(ep)  # tier 3

    sentinel: dict[str, bool] = {"called": False}

    def _spy(*args, **kwargs):
        sentinel["called"] = True
        return LibResult(ok=True, summary="x")

    monkeypatch.setattr(snapshot, "verify_restic_recent", _spy)

    result = apply.dry_run_then_apply_gate(mani, "/fake/path.yaml")

    assert result.ok is True
    assert sentinel["called"] is False


# ---------------------------------------------------------------------------
# Phase 3: verification_pre failure
# ---------------------------------------------------------------------------


def test_phase_verification_pre_failure(tmp_path):
    ep = _write_entrypoint(tmp_path)
    mani = _tier3_manifest(ep)
    mani["verification"] = {
        "pre": ["false"],  # exits non-zero
        "post": [],
    }

    result = apply.dry_run_then_apply_gate(mani, "/fake/path.yaml")

    assert result.ok is False
    assert result.details["phase"] == apply.PHASE_VERIFICATION_PRE
    assert "false" in result.summary


# ---------------------------------------------------------------------------
# Phase 4: entrypoint --dry-run failure (apply must NOT be invoked)
# ---------------------------------------------------------------------------


def test_phase_entrypoint_dry_run_failure_does_not_call_apply(tmp_path):
    # Script fails on --dry-run AND writes a marker on --apply. We assert the
    # marker is NOT created -> --apply was never reached.
    marker = tmp_path / "apply-was-called.marker"
    body = (
        f'if [ "$1" = "--dry-run" ]; then exit 1; fi\n'
        f'if [ "$1" = "--apply" ]; then touch {marker}; fi\n'
        "exit 0\n"
    )
    ep = _write_entrypoint(tmp_path, body=body)
    mani = _tier3_manifest(ep)

    result = apply.dry_run_then_apply_gate(mani, "/fake/path.yaml")

    assert result.ok is False
    assert result.details["phase"] == apply.PHASE_ENTRYPOINT_DRY_RUN
    assert not marker.exists(), "apply should NOT have been invoked after dry-run failure"


# ---------------------------------------------------------------------------
# Phase 5: entrypoint --apply failure
# ---------------------------------------------------------------------------


def test_phase_entrypoint_apply_failure(tmp_path):
    body = (
        'if [ "$1" = "--dry-run" ]; then exit 0; fi\n'
        'if [ "$1" = "--apply" ]; then exit 1; fi\n'
        "exit 0\n"
    )
    ep = _write_entrypoint(tmp_path, body=body)
    mani = _tier3_manifest(ep)

    result = apply.dry_run_then_apply_gate(mani, "/fake/path.yaml")

    assert result.ok is False
    assert result.details["phase"] == apply.PHASE_ENTRYPOINT_APPLY


# ---------------------------------------------------------------------------
# Phase 6: verification_post failure
# ---------------------------------------------------------------------------


def test_phase_verification_post_failure(tmp_path):
    ep = _write_entrypoint(tmp_path)
    mani = _tier3_manifest(ep)
    mani["verification"] = {
        "pre": [],
        "post": ["false"],
    }

    result = apply.dry_run_then_apply_gate(mani, "/fake/path.yaml")

    assert result.ok is False
    assert result.details["phase"] == apply.PHASE_VERIFICATION_POST


# ---------------------------------------------------------------------------
# Happy path: every phase exits ok → complete
# ---------------------------------------------------------------------------


def test_happy_path_full_sequence(tmp_path):
    ep = _write_entrypoint(tmp_path)
    mani = _tier3_manifest(ep)
    mani["verification"] = {
        "pre": ["true"],
        "post": ["true"],
    }

    result = apply.dry_run_then_apply_gate(mani, "/fake/path.yaml")

    assert result.ok is True
    assert result.details["phase"] == apply.PHASE_COMPLETE
    assert result.summary == "applied"
    assert result.details["manifest_name"] == "phase-test"
    assert result.details["manifest_path"] == "/fake/path.yaml"
    assert result.details["tier"] == 3


def test_happy_path_with_empty_verification_lists(tmp_path):
    """Empty pre/post arrays must not trip anything."""
    ep = _write_entrypoint(tmp_path)
    mani = _tier3_manifest(ep)
    mani["verification"] = {"pre": [], "post": []}

    result = apply.dry_run_then_apply_gate(mani, "/fake/path.yaml")

    assert result.ok is True
    assert result.details["phase"] == apply.PHASE_COMPLETE


def test_happy_path_with_no_verification_field(tmp_path):
    ep = _write_entrypoint(tmp_path)
    mani = _tier3_manifest(ep)  # no verification field at all

    result = apply.dry_run_then_apply_gate(mani, "/fake/path.yaml")

    assert result.ok is True
    assert result.details["phase"] == apply.PHASE_COMPLETE


# ---------------------------------------------------------------------------
# _run_shell helper
# ---------------------------------------------------------------------------


def test_run_shell_str_executes_via_shell():
    result = apply._run_shell("echo hello && exit 0")

    assert result.ok is True
    assert "hello" in result.details["stdout_excerpt"]


def test_run_shell_list_executes_without_shell():
    result = apply._run_shell(["true"])

    assert result.ok is True


def test_run_shell_captures_returncode_and_stderr_on_failure():
    result = apply._run_shell("echo err 1>&2 ; exit 7")

    assert result.ok is False
    assert result.details["returncode"] == 7
    assert "err" in result.details["stderr_excerpt"]


def test_run_shell_empty_command_rejected():
    result = apply._run_shell("")

    assert result.ok is False
    assert result.details["error_code"] == "EMPTY_COMMAND"


def test_run_shell_spawn_failure_when_executable_missing(tmp_path):
    """A list-form command whose executable does not exist returns SPAWN_FAILED."""
    missing = tmp_path / "missing-binary"
    result = apply._run_shell([str(missing)])

    assert result.ok is False
    assert result.details["error_code"] == "SPAWN_FAILED"


# ---------------------------------------------------------------------------
# CLI shim wires through correctly
# ---------------------------------------------------------------------------


def test_module_as_cli_invocation_returns_zero_on_success(tmp_path):
    """End-to-end invocation of ``python3 -m scripts.deploy.lib.apply ...``."""
    import subprocess

    fixture_path = FIXTURE_DIR / "valid_tier3_minimal.yaml"
    ep = _write_entrypoint(tmp_path)

    # Build a temp manifest pointing at the real script (the bundled fixture
    # uses a non-existent entrypoint path).
    import yaml

    fixture = manifest.load_manifest(fixture_path)
    fixture["entrypoint"] = str(ep)
    temp_manifest = tmp_path / "temp-manifest.yaml"
    temp_manifest.write_text(yaml.safe_dump(fixture, sort_keys=False), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.deploy.lib.apply",
            "dry_run_then_apply_gate",
            str(temp_manifest),
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )

    assert proc.returncode == 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    assert "applied" in proc.stdout


def test_module_as_cli_invocation_returns_nonzero_on_failure(tmp_path):
    import subprocess

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.deploy.lib.apply",
            "dry_run_then_apply_gate",
            str(tmp_path / "no-such-manifest.yaml"),
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )

    assert proc.returncode != 0
