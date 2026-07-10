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
    assert "self-test" in captured.out
    assert "--dry-run" in captured.out
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


def _write_deployed_fleet(deploy_mod, tmp_path, *, main_has_infra=True, drop_block_for=None):
    """Materialize deployed AGENTS.md files for every fleet agent under tmp_path.

    Each carries the exact canonical doctrine block; ``main`` additionally
    carries the no-unrequested-infra block. Returns the slug->Path mapping that
    ``_deployed_fleet_prompts`` should be patched to return.
    """
    from scripts.openclaw.agents.truthful_doctrine import (
        FLEET_AGENTS,
        NO_UNREQUESTED_INFRA_HEADING,
        TRUTHFUL_DOCTRINE_BLOCK,
    )

    resolved = {}
    for slug in FLEET_AGENTS:
        p = tmp_path / f"{slug}-AGENTS.md"
        body = "# prompt\n\n"
        if slug != drop_block_for:
            body += TRUTHFUL_DOCTRINE_BLOCK
        if slug == "main" and main_has_infra:
            body += "\n" + NO_UNREQUESTED_INFRA_HEADING + "\n"
        p.write_text(body, encoding="utf-8")
        resolved[slug] = p
    return resolved


# Clean happy-path dry-run self-test JSON (0 findings) — the gate requires this
# before the timer is enabled (#711).
_CLEAN_SELF_TEST_STDOUT = (
    '{"ok": true, "drift_findings": 0, "assertion_findings": 0, '
    '"alerts_emitted": 0, "errors": []}'
)


def _fake_run_clean(argv, cwd=None):
    """Default happy-path ``_run``: a clean (0-findings) dry-run self-test JSON
    for the ``run_trust_scan`` call, success for every ``systemctl`` call."""
    if "run_trust_scan" in " ".join(argv):
        return (0, _CLEAN_SELF_TEST_STDOUT, "")
    return (0, "", "")


def test_apply_full_success_path(deploy_mod, tmp_path):
    unit_src = tmp_path / "office2-src"
    unit_src.mkdir()
    for name in deploy_mod._UNIT_NAMES:
        (unit_src / name).write_text("[Unit]\n", encoding="utf-8")

    systemd_dir = tmp_path / "systemd-user"
    deployed = _write_deployed_fleet(deploy_mod, tmp_path)

    calls = []

    def _fake_run(argv, cwd=None):
        calls.append(argv)
        return _fake_run_clean(argv, cwd)

    with patch.object(deploy_mod, "_UNIT_SOURCE_DIR", unit_src), patch.object(
        deploy_mod, "_SYSTEMD_USER_DIR", systemd_dir
    ), patch.object(
        deploy_mod, "_deployed_fleet_prompts", return_value=deployed
    ), patch.object(deploy_mod, "_run", side_effect=_fake_run), patch.object(
        deploy_mod, "emit"
    ) as mock_emit:
        exit_code = deploy_mod.main(["--apply"])

    assert exit_code == 0
    for name in deploy_mod._UNIT_NAMES:
        assert (systemd_dir / name).exists()
    mock_emit.assert_called_once()
    # Order gate (#711): the dry-run self-test must run BEFORE `enable --now`.
    joined = [" ".join(a) for a in calls]
    selftest_i = next(i for i, c in enumerate(joined) if "run_trust_scan" in c)
    enable_i = next(i for i, c in enumerate(joined) if "enable" in c and "--now" in c)
    assert selftest_i < enable_i
    # And the self-test uses --dry-run (never --preflight — a self-test must not emit).
    assert "--dry-run" in joined[selftest_i]
    assert "--preflight" not in joined[selftest_i]


def test_apply_daemon_reload_failure_halts(deploy_mod, tmp_path):
    unit_src = tmp_path / "office2-src"
    unit_src.mkdir()
    for name in deploy_mod._UNIT_NAMES:
        (unit_src / name).write_text("[Unit]\n", encoding="utf-8")
    systemd_dir = tmp_path / "systemd-user"

    def _fake_run(argv, cwd=None):
        if "daemon-reload" in argv:
            return (1, "", "daemon-reload failed")
        return _fake_run_clean(argv, cwd)

    with patch.object(deploy_mod, "_UNIT_SOURCE_DIR", unit_src), patch.object(
        deploy_mod, "_SYSTEMD_USER_DIR", systemd_dir
    ), patch.object(deploy_mod, "_run", side_effect=_fake_run), patch.object(
        deploy_mod, "emit"
    ) as mock_emit:
        exit_code = deploy_mod.main(["--apply"])

    assert exit_code == 1
    mock_emit.assert_called_once()


def test_apply_enable_timer_failure_halts(deploy_mod, tmp_path):
    """`enable --now` failing AFTER a clean self-test halts the deploy."""
    unit_src = tmp_path / "office2-src"
    unit_src.mkdir()
    for name in deploy_mod._UNIT_NAMES:
        (unit_src / name).write_text("[Unit]\n", encoding="utf-8")
    systemd_dir = tmp_path / "systemd-user"

    def _fake_run(argv, cwd=None):
        if "enable" in argv and "--now" in argv:
            return (1, "", "enable failed")
        return _fake_run_clean(argv, cwd)

    with patch.object(deploy_mod, "_UNIT_SOURCE_DIR", unit_src), patch.object(
        deploy_mod, "_SYSTEMD_USER_DIR", systemd_dir
    ), patch.object(deploy_mod, "_run", side_effect=_fake_run), patch.object(
        deploy_mod, "emit"
    ) as mock_emit:
        exit_code = deploy_mod.main(["--apply"])

    assert exit_code == 1
    mock_emit.assert_called_once()


def test_apply_dry_run_self_test_fault_halts(deploy_mod, tmp_path):
    """A hard scan-inability (rc=2) in the dry-run self-test halts the deploy."""
    unit_src = tmp_path / "office2-src"
    unit_src.mkdir()
    for name in deploy_mod._UNIT_NAMES:
        (unit_src / name).write_text("[Unit]\n", encoding="utf-8")
    systemd_dir = tmp_path / "systemd-user"

    def _fake_run(argv, cwd=None):
        if "run_trust_scan" in " ".join(argv):
            return (2, "", "scan-inability: unreadable baseline")
        return (0, "", "")

    with patch.object(deploy_mod, "_UNIT_SOURCE_DIR", unit_src), patch.object(
        deploy_mod, "_SYSTEMD_USER_DIR", systemd_dir
    ), patch.object(deploy_mod, "_run", side_effect=_fake_run), patch.object(
        deploy_mod, "emit"
    ) as mock_emit:
        exit_code = deploy_mod.main(["--apply"])

    assert exit_code == 1
    mock_emit.assert_called_once()


def test_apply_dry_run_findings_gate_leaves_timer_disabled(deploy_mod, tmp_path):
    """#711: a fresh deploy whose dry-run reports findings (baseline mismatch)
    FAILS before enabling the timer — so no false-positive alert ever fires."""
    unit_src = tmp_path / "office2-src"
    unit_src.mkdir()
    for name in deploy_mod._UNIT_NAMES:
        (unit_src / name).write_text("[Unit]\n", encoding="utf-8")
    systemd_dir = tmp_path / "systemd-user"

    dirty = (
        '{"ok": true, "drift_findings": 2, "assertion_findings": 0, '
        '"alerts_emitted": 0, "errors": []}'
    )
    enable_called = {"value": False}

    def _fake_run(argv, cwd=None):
        if "enable" in argv and "--now" in argv:
            enable_called["value"] = True
            return (0, "", "")
        if "run_trust_scan" in " ".join(argv):
            return (0, dirty, "")
        return (0, "", "")

    with patch.object(deploy_mod, "_UNIT_SOURCE_DIR", unit_src), patch.object(
        deploy_mod, "_SYSTEMD_USER_DIR", systemd_dir
    ), patch.object(deploy_mod, "_run", side_effect=_fake_run), patch.object(
        deploy_mod, "emit"
    ) as mock_emit:
        exit_code = deploy_mod.main(["--apply"])

    assert exit_code == 1
    assert enable_called["value"] is False  # timer NEVER enabled on a dirty baseline
    mock_emit.assert_called_once()


def test_apply_prompt_sync_block_missing_in_one_prompt_halts(deploy_mod, tmp_path):
    """F4: the canonical block missing from ANY one of the deployed fleet
    prompts fails the deploy (a loose substring check would have passed)."""
    unit_src = tmp_path / "office2-src"
    unit_src.mkdir()
    for name in deploy_mod._UNIT_NAMES:
        (unit_src / name).write_text("[Unit]\n", encoding="utf-8")
    systemd_dir = tmp_path / "systemd-user"
    # Drop the canonical block from just one non-main fleet prompt.
    deployed = _write_deployed_fleet(
        deploy_mod, tmp_path, drop_block_for="felix-admin-habits"
    )

    def _fake_run(argv, cwd=None):
        return _fake_run_clean(argv, cwd)

    with patch.object(deploy_mod, "_UNIT_SOURCE_DIR", unit_src), patch.object(
        deploy_mod, "_SYSTEMD_USER_DIR", systemd_dir
    ), patch.object(
        deploy_mod, "_deployed_fleet_prompts", return_value=deployed
    ), patch.object(deploy_mod, "_run", side_effect=_fake_run), patch.object(
        deploy_mod, "emit"
    ) as mock_emit:
        exit_code = deploy_mod.main(["--apply"])

    assert exit_code == 1
    mock_emit.assert_called_once()


def test_apply_prompt_sync_main_only_block_missing_halts(deploy_mod, tmp_path):
    """F4: the no-unrequested-infra block missing from deployed main fails the
    deploy even when the canonical doctrine block is present everywhere."""
    unit_src = tmp_path / "office2-src"
    unit_src.mkdir()
    for name in deploy_mod._UNIT_NAMES:
        (unit_src / name).write_text("[Unit]\n", encoding="utf-8")
    systemd_dir = tmp_path / "systemd-user"
    deployed = _write_deployed_fleet(deploy_mod, tmp_path, main_has_infra=False)

    def _fake_run(argv, cwd=None):
        return _fake_run_clean(argv, cwd)

    with patch.object(deploy_mod, "_UNIT_SOURCE_DIR", unit_src), patch.object(
        deploy_mod, "_SYSTEMD_USER_DIR", systemd_dir
    ), patch.object(
        deploy_mod, "_deployed_fleet_prompts", return_value=deployed
    ), patch.object(deploy_mod, "_run", side_effect=_fake_run), patch.object(
        deploy_mod, "emit"
    ) as mock_emit:
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
        return _fake_run_clean(argv, cwd)

    with patch.object(deploy_mod, "_UNIT_SOURCE_DIR", unit_src), patch.object(
        deploy_mod, "_SYSTEMD_USER_DIR", systemd_dir
    ), patch.object(deploy_mod, "_run", side_effect=_fake_run), patch.object(
        deploy_mod, "emit"
    ) as mock_emit:
        exit_code = deploy_mod.main(["--apply"])

    assert exit_code == 1
    mock_emit.assert_called_once()


# --- F4: deployed-prompt resolution + canonical-block verification ------------


def test_deployed_fleet_prompts_resolves_deployed_subset(deploy_mod):
    """The resolver maps fleet slugs to <workspace>/AGENTS.md from the real
    inventory, and excludes agents with no deployed workspace (felix-doc-auditor
    is a retired scripts-first driver absent from the inventory agents map)."""
    resolved = deploy_mod._deployed_fleet_prompts()
    assert "main" in resolved
    assert str(resolved["main"]).endswith("/data/AGENTS.md")
    for slug, path in resolved.items():
        assert path.name == "AGENTS.md"
        assert "/data/services/openclaw/" in str(path)
    # felix-doc-auditor has no deployed workspace -> not resolved.
    assert "felix-doc-auditor" not in resolved
    # At least main + the 5 deployed admin agents resolve.
    assert len(resolved) >= 6


def test_check_deployed_doctrine_all_present_ok(tmp_path):
    from scripts.openclaw.agents.truthful_doctrine import (
        NO_UNREQUESTED_INFRA_HEADING,
        TRUTHFUL_DOCTRINE_BLOCK,
        check_deployed_doctrine,
    )

    main_p = tmp_path / "main.md"
    main_p.write_text(
        "x\n" + TRUTHFUL_DOCTRINE_BLOCK + "\n" + NO_UNREQUESTED_INFRA_HEADING + "\n"
    )
    other_p = tmp_path / "other.md"
    other_p.write_text("y\n" + TRUTHFUL_DOCTRINE_BLOCK)

    check = check_deployed_doctrine({"main": main_p, "felix-admin-habits": other_p})
    assert check.ok
    assert check.missing_block == []
    assert check.missing_main_only == []


def test_check_deployed_doctrine_flags_missing_block_and_main_only(tmp_path):
    from scripts.openclaw.agents.truthful_doctrine import (
        TRUTHFUL_DOCTRINE_BLOCK,
        check_deployed_doctrine,
    )

    main_p = tmp_path / "main.md"
    main_p.write_text("x\n" + TRUTHFUL_DOCTRINE_BLOCK)  # no infra heading
    other_p = tmp_path / "other.md"
    other_p.write_text("nothing relevant\n")

    check = check_deployed_doctrine({"main": main_p, "felix-admin-tasker": other_p})
    assert not check.ok
    assert str(other_p) in check.missing_block
    assert str(main_p) in check.missing_main_only


def test_check_deployed_doctrine_unreadable_counts_as_missing(tmp_path):
    from scripts.openclaw.agents.truthful_doctrine import check_deployed_doctrine

    missing = tmp_path / "does-not-exist.md"
    check = check_deployed_doctrine({"felix-admin-capture": missing})
    assert not check.ok
    assert str(missing) in check.missing_block
