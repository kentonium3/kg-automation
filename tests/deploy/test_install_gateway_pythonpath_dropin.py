"""Tests for scripts/deploy/install-gateway-pythonpath-dropin.py.

Covers the WP01 requirement (T002 test strategy): unit-test the entrypoint's
``--dry-run`` behavior — prints planned actions, mutates nothing.

The ``--apply`` path invokes live systemctl on office2 and is a deploy-time
gate, not tested here. These tests confirm the dry-run path is safe to run
anywhere (no side effects) and surfaces the correct planned operations.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

# ---------------------------------------------------------------------------
# Load the hyphenated-named entrypoint module.
# The file is named install-gateway-pythonpath-dropin.py, which is not
# importable via dotted form — use importlib to load it directly.
# ---------------------------------------------------------------------------

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_ENTRYPOINT_PATH = (
    _REPO_ROOT / "scripts" / "deploy" / "install-gateway-pythonpath-dropin.py"
)


def _load_entrypoint():
    """Load the entrypoint module via importlib (hyphenated filename)."""
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    spec = importlib.util.spec_from_file_location(
        "install_gateway_pythonpath_dropin",
        _ENTRYPOINT_PATH,
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_mod = _load_entrypoint()


# ---------------------------------------------------------------------------
# T001 sanity: source drop-in file must exist in the repo.
# ---------------------------------------------------------------------------


def test_source_dropin_file_exists():
    """The pythonpath.conf drop-in must be present in the repo tree."""
    assert _mod._SOURCE_CONF.exists(), (
        f"Drop-in file not found: {_mod._SOURCE_CONF}. "
        "Did T001 create scripts/openclaw/openclaw-gateway.service.d/pythonpath.conf?"
    )


def test_source_dropin_file_content():
    """The drop-in must contain the exact required Environment= line."""
    content = _mod._SOURCE_CONF.read_text(encoding="utf-8")
    assert "[Service]" in content, "Drop-in must have a [Service] section"
    assert "Environment=PYTHONPATH=/home/claude/kg-automation" in content, (
        "Drop-in must set Environment=PYTHONPATH=/home/claude/kg-automation"
    )


# ---------------------------------------------------------------------------
# dry-run: exit 0, prints planned actions, mutates nothing.
# ---------------------------------------------------------------------------


def test_dry_run_exits_zero(tmp_path, monkeypatch, capsys):
    """--dry-run must return exit code 0."""
    # Redirect target dir to tmp_path so we can assert nothing is created.
    monkeypatch.setattr(_mod, "_TARGET_DIR", tmp_path / "dropin.d")
    monkeypatch.setattr(_mod, "_TARGET_CONF", tmp_path / "dropin.d" / "pythonpath.conf")

    rc = _mod.main(["--dry-run"])

    assert rc == 0


def test_dry_run_prints_source_path(tmp_path, monkeypatch, capsys):
    """--dry-run output must mention the source drop-in path."""
    monkeypatch.setattr(_mod, "_TARGET_DIR", tmp_path / "dropin.d")
    monkeypatch.setattr(_mod, "_TARGET_CONF", tmp_path / "dropin.d" / "pythonpath.conf")

    _mod.main(["--dry-run"])

    out = capsys.readouterr().out
    assert "pythonpath.conf" in out, f"Expected source path mention in output: {out!r}"


def test_dry_run_prints_target_path(tmp_path, monkeypatch, capsys):
    """--dry-run output must mention the target directory."""
    fake_target_dir = tmp_path / "dropin.d"
    monkeypatch.setattr(_mod, "_TARGET_DIR", fake_target_dir)
    monkeypatch.setattr(_mod, "_TARGET_CONF", fake_target_dir / "pythonpath.conf")

    _mod.main(["--dry-run"])

    out = capsys.readouterr().out
    assert str(fake_target_dir) in out, (
        f"Expected target dir {fake_target_dir} in dry-run output: {out!r}"
    )


def test_dry_run_prints_systemctl_reload(tmp_path, monkeypatch, capsys):
    """--dry-run output must mention daemon-reload."""
    monkeypatch.setattr(_mod, "_TARGET_DIR", tmp_path / "dropin.d")
    monkeypatch.setattr(_mod, "_TARGET_CONF", tmp_path / "dropin.d" / "pythonpath.conf")

    _mod.main(["--dry-run"])

    out = capsys.readouterr().out
    assert "daemon-reload" in out, f"Expected daemon-reload mention in dry-run output: {out!r}"


def test_dry_run_prints_restart(tmp_path, monkeypatch, capsys):
    """--dry-run output must mention the gateway restart."""
    monkeypatch.setattr(_mod, "_TARGET_DIR", tmp_path / "dropin.d")
    monkeypatch.setattr(_mod, "_TARGET_CONF", tmp_path / "dropin.d" / "pythonpath.conf")

    _mod.main(["--dry-run"])

    out = capsys.readouterr().out
    assert "restart" in out and "openclaw-gateway.service" in out, (
        f"Expected restart mention in dry-run output: {out!r}"
    )


def test_dry_run_prints_pythonpath_value(tmp_path, monkeypatch, capsys):
    """--dry-run output must state the expected PYTHONPATH value."""
    monkeypatch.setattr(_mod, "_TARGET_DIR", tmp_path / "dropin.d")
    monkeypatch.setattr(_mod, "_TARGET_CONF", tmp_path / "dropin.d" / "pythonpath.conf")

    _mod.main(["--dry-run"])

    out = capsys.readouterr().out
    assert "PYTHONPATH=/home/claude/kg-automation" in out, (
        f"Expected PYTHONPATH value in dry-run output: {out!r}"
    )


def test_dry_run_prints_proc_environ_check(tmp_path, monkeypatch, capsys):
    """--dry-run output must describe the /proc/<MainPID>/environ planned check (SC-10b).

    SC-10b verifies PYTHONPATH in the live gateway process environment — the
    deterministic proof that agent subprocesses inherit it.  Dry-run must
    describe this planned check so an operator knows what the apply step will
    assert, without actually reading /proc or running systemctl.
    """
    monkeypatch.setattr(_mod, "_TARGET_DIR", tmp_path / "dropin.d")
    monkeypatch.setattr(_mod, "_TARGET_CONF", tmp_path / "dropin.d" / "pythonpath.conf")

    _mod.main(["--dry-run"])

    out = capsys.readouterr().out
    assert "/proc/" in out, (
        f"Expected /proc/<MainPID>/environ mention in dry-run output: {out!r}"
    )
    assert "MainPID" in out, (
        f"Expected MainPID mention in dry-run output: {out!r}"
    )


def test_dry_run_prints_sc10a_systemctl_show(tmp_path, monkeypatch, capsys):
    """--dry-run output must describe the SC-10a systemctl show -p Environment check."""
    monkeypatch.setattr(_mod, "_TARGET_DIR", tmp_path / "dropin.d")
    monkeypatch.setattr(_mod, "_TARGET_CONF", tmp_path / "dropin.d" / "pythonpath.conf")

    _mod.main(["--dry-run"])

    out = capsys.readouterr().out
    assert "SC-10a" in out, (
        f"Expected SC-10a mention in dry-run output: {out!r}"
    )
    assert "Environment" in out, (
        f"Expected Environment mention (systemctl show -p Environment) in dry-run output: {out!r}"
    )


def test_dry_run_mutates_nothing(tmp_path, monkeypatch, capsys):
    """--dry-run must NOT create the target directory or copy any files."""
    fake_target_dir = tmp_path / "should-not-be-created"
    monkeypatch.setattr(_mod, "_TARGET_DIR", fake_target_dir)
    monkeypatch.setattr(_mod, "_TARGET_CONF", fake_target_dir / "pythonpath.conf")

    _mod.main(["--dry-run"])

    assert not fake_target_dir.exists(), (
        f"--dry-run must not create target dir: {fake_target_dir}"
    )


# ---------------------------------------------------------------------------
# Usage errors.
# ---------------------------------------------------------------------------


def test_usage_error_no_args(capsys):
    """Called with no arguments returns exit code 2."""
    rc = _mod.main([])
    assert rc == 2


def test_usage_error_unknown_flag(capsys):
    """Called with an unknown flag returns exit code 2."""
    rc = _mod.main(["--unknown"])
    assert rc == 2


def test_usage_error_too_many_args(capsys):
    """Called with extra positional args returns exit code 2."""
    rc = _mod.main(["--dry-run", "extra"])
    assert rc == 2


def test_usage_error_writes_to_stderr(capsys):
    """Usage errors write to stderr, not stdout."""
    _mod.main([])
    captured = capsys.readouterr()
    assert "usage:" in captured.err.lower()
    assert captured.out == ""


# ---------------------------------------------------------------------------
# Constant validation.
# ---------------------------------------------------------------------------


def test_expected_pythonpath_constant():
    """The EXPECTED_PYTHONPATH constant must be the canonical value."""
    assert _mod._EXPECTED_PYTHONPATH == "/home/claude/kg-automation"


def test_unit_name_constant():
    """The gateway unit name constant must match the base unit filename."""
    assert _mod._UNIT == "openclaw-gateway.service"
