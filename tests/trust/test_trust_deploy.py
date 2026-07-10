"""Tests for scripts/deploy/deploy-truthful-reporting.py (WP04, #683).

Mocks `subprocess.run` (via the module's `_run` wrapper) and the filesystem
(via tmp_path monkeypatches on the module's path constants) so no real
systemctl / office2 calls happen. `--dry-run` must have zero side effects;
`--apply`'s step sequence (install / enable / preflight / prompt-sync
verify) is driven through the mocked subprocess boundary; a usage error
exits 2.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest

_MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "deploy" / "deploy-truthful-reporting.py"
)


def _load_module():
    """Load the hyphenated deploy script as an importable module for testing."""
    spec = importlib.util.spec_from_file_location("deploy_truthful_reporting", _MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def deploy_mod():
    return _load_module()


# --- --dry-run: prints steps, no side effects --------------------------------


def test_dry_run_prints_steps_and_exits_0(deploy_mod, capsys):
    exit_code = deploy_mod.main(["--dry-run"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "DRY-RUN" in captured.out
    assert "felix-trust-scan.service" in captured.out
    assert "felix-trust-scan.timer" in captured.out
    assert "daemon-reload" in captured.out
    assert "preflight" in captured.out
    assert "agent-prompt-sync.service" in captured.out


def test_dry_run_never_calls_subprocess(deploy_mod):
    with patch("subprocess.run") as mock_run:
        deploy_mod.main(["--dry-run"])
    mock_run.assert_not_called()


# --- usage errors -------------------------------------------------------------


def test_usage_error_exits_2(deploy_mod, capsys):
    exit_code = deploy_mod.main([])
    assert exit_code == 2
    captured = capsys.readouterr()
    assert "usage" in captured.err.lower()


def test_unknown_flag_exits_2(deploy_mod):
    assert deploy_mod.main(["--bogus"]) == 2


# --- --apply: step sequence via mocked subprocess/filesystem -----------------


def _mock_completed(returncode=0, stdout="", stderr=""):
    class _Completed:
        pass

    c = _Completed()
    c.returncode = returncode
    c.stdout = stdout
    c.stderr = stderr
    return c


def test_apply_install_units_failure_halts_and_reports(deploy_mod, tmp_path):
    bad_source = tmp_path / "nonexistent"
    with patch.object(deploy_mod, "_UNIT_SOURCE_DIR", bad_source), patch.object(
        deploy_mod, "_SYSTEMD_USER_DIR", tmp_path / "systemd-user"
    ), patch.object(deploy_mod, "emit") as mock_emit:
        exit_code = deploy_mod.main(["--apply"])

    assert exit_code == 1
    mock_emit.assert_called_once()


def test_apply_full_success_path(deploy_mod, tmp_path):
    unit_src = tmp_path / "office2-src"
    unit_src.mkdir()
    for name in deploy_mod._UNIT_NAMES:
        (unit_src / name).write_text("[Unit]\n", encoding="utf-8")

    systemd_dir = tmp_path / "systemd-user"
    agents_md = tmp_path / "AGENTS.md"
    agents_md.write_text("## Truthful Reporting\nBe truthful.\n", encoding="utf-8")

    def _fake_run(argv, cwd=None):
        # daemon-reload / enable --now / preflight self-test / prompt-sync start
        return (0, "", "")

    with patch.object(deploy_mod, "_UNIT_SOURCE_DIR", unit_src), patch.object(
        deploy_mod, "_SYSTEMD_USER_DIR", systemd_dir
    ), patch.object(deploy_mod, "_MAIN_DEPLOYED_AGENTS_MD", agents_md), patch.object(
        deploy_mod, "_run", side_effect=_fake_run
    ), patch.object(deploy_mod, "emit") as mock_emit:
        exit_code = deploy_mod.main(["--apply"])

    assert exit_code == 0
    for name in deploy_mod._UNIT_NAMES:
        assert (systemd_dir / name).exists()
    mock_emit.assert_called_once()


def test_apply_enable_timer_failure_halts(deploy_mod, tmp_path):
    unit_src = tmp_path / "office2-src"
    unit_src.mkdir()
    for name in deploy_mod._UNIT_NAMES:
        (unit_src / name).write_text("[Unit]\n", encoding="utf-8")
    systemd_dir = tmp_path / "systemd-user"

    def _fake_run(argv, cwd=None):
        if "daemon-reload" in argv:
            return (1, "", "daemon-reload failed")
        return (0, "", "")

    with patch.object(deploy_mod, "_UNIT_SOURCE_DIR", unit_src), patch.object(
        deploy_mod, "_SYSTEMD_USER_DIR", systemd_dir
    ), patch.object(deploy_mod, "_run", side_effect=_fake_run), patch.object(
        deploy_mod, "emit"
    ) as mock_emit:
        exit_code = deploy_mod.main(["--apply"])

    assert exit_code == 1
    mock_emit.assert_called_once()


def test_apply_preflight_self_test_failure_halts(deploy_mod, tmp_path):
    unit_src = tmp_path / "office2-src"
    unit_src.mkdir()
    for name in deploy_mod._UNIT_NAMES:
        (unit_src / name).write_text("[Unit]\n", encoding="utf-8")
    systemd_dir = tmp_path / "systemd-user"

    def _fake_run(argv, cwd=None):
        if "run_trust_scan" in " ".join(argv):
            return (2, "", "preflight scan-inability")
        return (0, "", "")

    with patch.object(deploy_mod, "_UNIT_SOURCE_DIR", unit_src), patch.object(
        deploy_mod, "_SYSTEMD_USER_DIR", systemd_dir
    ), patch.object(deploy_mod, "_run", side_effect=_fake_run), patch.object(
        deploy_mod, "emit"
    ) as mock_emit:
        exit_code = deploy_mod.main(["--apply"])

    assert exit_code == 1
    mock_emit.assert_called_once()


def test_apply_prompt_sync_marker_missing_halts(deploy_mod, tmp_path):
    unit_src = tmp_path / "office2-src"
    unit_src.mkdir()
    for name in deploy_mod._UNIT_NAMES:
        (unit_src / name).write_text("[Unit]\n", encoding="utf-8")
    systemd_dir = tmp_path / "systemd-user"
    agents_md = tmp_path / "AGENTS.md"
    agents_md.write_text("## Some Other Section\nNothing relevant.\n", encoding="utf-8")

    def _fake_run(argv, cwd=None):
        return (0, "", "")

    with patch.object(deploy_mod, "_UNIT_SOURCE_DIR", unit_src), patch.object(
        deploy_mod, "_SYSTEMD_USER_DIR", systemd_dir
    ), patch.object(deploy_mod, "_MAIN_DEPLOYED_AGENTS_MD", agents_md), patch.object(
        deploy_mod, "_run", side_effect=_fake_run
    ), patch.object(deploy_mod, "emit") as mock_emit:
        exit_code = deploy_mod.main(["--apply"])

    assert exit_code == 1
    mock_emit.assert_called_once()


def test_apply_prompt_sync_start_failure_halts(deploy_mod, tmp_path):
    unit_src = tmp_path / "office2-src"
    unit_src.mkdir()
    for name in deploy_mod._UNIT_NAMES:
        (unit_src / name).write_text("[Unit]\n", encoding="utf-8")
    systemd_dir = tmp_path / "systemd-user"

    def _fake_run(argv, cwd=None):
        if "agent-prompt-sync.service" in argv:
            return (1, "", "start failed")
        return (0, "", "")

    with patch.object(deploy_mod, "_UNIT_SOURCE_DIR", unit_src), patch.object(
        deploy_mod, "_SYSTEMD_USER_DIR", systemd_dir
    ), patch.object(deploy_mod, "_run", side_effect=_fake_run), patch.object(
        deploy_mod, "emit"
    ) as mock_emit:
        exit_code = deploy_mod.main(["--apply"])

    assert exit_code == 1
    mock_emit.assert_called_once()
