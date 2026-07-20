"""Tests for scripts/deploy/deploy-security-monitor-audit.py + its manifest (#818).

The entrypoint copies the checkout's security-monitor audit.sh to its standalone
office2 copy and verifies byte-identity + the executable bit. These tests exercise
the deterministic copy/verify + the CLI contract (dry-run / apply / usage error)
against tmp paths, so they never touch the real /data path.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import pytest
import yaml

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_ENTRYPOINT_PATH = _REPO_ROOT / "scripts" / "deploy" / "deploy-security-monitor-audit.py"
_MANIFEST_QUEUED = _REPO_ROOT / "deploys" / "queued" / "0022-systemd-unit-content-baseline.yaml"


def _resolve_manifest_path() -> pathlib.Path:
    """queued pre-deploy, applied/<NNNN>-... once felix-deployer relocates it."""
    if _MANIFEST_QUEUED.exists():
        return _MANIFEST_QUEUED
    applied = sorted(
        (_REPO_ROOT / "deploys" / "applied").glob("*-systemd-unit-content-baseline.yaml")
    )
    return applied[-1] if applied else _MANIFEST_QUEUED


def _load_entrypoint():
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    spec = importlib.util.spec_from_file_location("deploy_security_monitor_audit", _ENTRYPOINT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_mod = _load_entrypoint()


def _capsys_json(capsys) -> dict:
    out = capsys.readouterr().out.strip().splitlines()
    return json.loads(out[-1])


# --- CLI contract ----------------------------------------------------------


def test_no_mode_is_usage_error():
    assert _mod.main([]) == 2


def test_both_modes_is_usage_error():
    assert _mod.main(["--dry-run", "--apply"]) == 2


# --- dry-run ---------------------------------------------------------------


def test_dry_run_reports_copy_needed(monkeypatch, tmp_path, capsys):
    src = tmp_path / "audit.sh"
    src.write_text("echo hi\n")
    monkeypatch.setattr(_mod, "_SOURCE", src)
    monkeypatch.setattr(_mod, "_TARGET", tmp_path / "deployed" / "audit.sh")
    assert _mod.main(["--dry-run"]) == 0
    payload = _capsys_json(capsys)
    assert payload["outcome"] == "dry_run"
    assert payload["target_exists"] is False
    assert payload["would_copy"] is True


def test_dry_run_missing_source_fails(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(_mod, "_SOURCE", tmp_path / "nope.sh")
    assert _mod.main(["--dry-run"]) == 1
    assert _capsys_json(capsys)["outcome"] == "dry_run_error"


# --- apply -----------------------------------------------------------------


def test_apply_copies_and_verifies(monkeypatch, tmp_path, capsys):
    src = tmp_path / "audit.sh"
    src.write_text("#!/usr/bin/env bash\necho audit\n")
    src.chmod(0o755)
    target = tmp_path / "deployed" / "audit.sh"  # parent does not exist yet
    monkeypatch.setattr(_mod, "_SOURCE", src)
    monkeypatch.setattr(_mod, "_TARGET", target)

    assert _mod.main(["--apply"]) == 0
    assert _capsys_json(capsys)["outcome"] == "applied"
    assert target.read_text() == src.read_text()
    assert target.stat().st_mode & 0o111  # executable preserved


def test_apply_forces_executable_from_nonexec_source(monkeypatch, tmp_path, capsys):
    """audit.sh is invoked directly, so the target must be +x even if the repo
    source is not executable (copy2 preserves the source's non-exec mode)."""
    src = tmp_path / "audit.sh"
    src.write_text("echo hi\n")
    src.chmod(0o644)  # deliberately NOT executable
    target = tmp_path / "deployed" / "audit.sh"
    monkeypatch.setattr(_mod, "_SOURCE", src)
    monkeypatch.setattr(_mod, "_TARGET", target)

    assert _mod.main(["--apply"]) == 0
    assert _capsys_json(capsys)["outcome"] == "applied"
    assert target.stat().st_mode & 0o111, "target must be executable after apply"


def test_apply_is_idempotent(monkeypatch, tmp_path, capsys):
    src = tmp_path / "audit.sh"
    src.write_text("echo hi\n")
    target = tmp_path / "deployed" / "audit.sh"
    monkeypatch.setattr(_mod, "_SOURCE", src)
    monkeypatch.setattr(_mod, "_TARGET", target)
    assert _mod.main(["--apply"]) == 0
    assert _mod.main(["--apply"]) == 0  # second run: still success
    assert _capsys_json(capsys)["outcome"] == "applied"


def test_apply_missing_source_fails(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(_mod, "_SOURCE", tmp_path / "nope.sh")
    monkeypatch.setattr(_mod, "_TARGET", tmp_path / "deployed" / "audit.sh")
    assert _mod.main(["--apply"]) == 1
    assert _capsys_json(capsys)["outcome"] == "apply_error"


# --- manifest --------------------------------------------------------------


def test_manifest_shape():
    m = yaml.safe_load(_resolve_manifest_path().read_text())
    assert m["schema_version"] == "v1"
    assert m["tier"] == 3
    assert m["audited_surface"] is False
    assert m["entrypoint"] == "scripts/deploy/deploy-security-monitor-audit.py"
    assert m["issue"] == "kentonium3/kg-automation#818"
