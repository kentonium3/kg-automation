"""Tests for scripts/deploy/deploy-felix-calendar-helper.py + its manifest (WP04).

Covers T016: the deploy entrypoint's four ordered gates
(Restic -> venv -> creds -> self-check), halt-on-error at each gate, idempotent
venv provisioning, the creds-absent clear failure, self-check-failure fails the
deploy, and manifest schema validity. All subprocess / uv / lib primitives are
mocked — NO network, NO office2 access.

The entrypoint file is hyphenated (deploy-felix-calendar-helper.py), which is
not importable via dotted form; it is loaded with importlib, matching the
sibling test_install_gateway_pythonpath_dropin.py pattern.
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
import sys

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_ENTRYPOINT_PATH = _REPO_ROOT / "scripts" / "deploy" / "deploy-felix-calendar-helper.py"
_MANIFEST_PATH = _REPO_ROOT / "deploys" / "queued" / "felix-calendar-helper.yaml"


def _load_entrypoint():
    """Load the hyphenated-named entrypoint module via importlib."""
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    spec = importlib.util.spec_from_file_location(
        "deploy_felix_calendar_helper",
        _ENTRYPOINT_PATH,
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_mod = _load_entrypoint()


# ---------------------------------------------------------------------------
# Helpers: a LibResult stand-in and a scripted _run recorder.
# ---------------------------------------------------------------------------


class _Result:
    """Minimal LibResult stand-in (ok + summary + details)."""

    def __init__(self, ok: bool, summary: str = "", details: dict | None = None):
        self.ok = ok
        self.summary = summary
        self.details = details or {}


class _RunRecorder:
    """Callable that records each _run invocation and returns scripted results.

    ``responses`` is a list of (returncode, stdout, stderr) consumed in order.
    Missing responses default to a success (0, "", "").
    """

    def __init__(self, responses: list[tuple[int, str, str]] | None = None):
        self.calls: list[dict] = []
        self._responses = list(responses or [])

    def __call__(self, argv, cwd=None):
        self.calls.append({"argv": list(argv), "cwd": cwd})
        if self._responses:
            return self._responses.pop(0)
        return (0, "", "")

    @property
    def argv_list(self) -> list[list[str]]:
        return [c["argv"] for c in self.calls]


def _patch_all_pass(monkeypatch, run_recorder: _RunRecorder) -> None:
    """Patch every external dependency so a full --apply succeeds."""
    monkeypatch.setattr(_mod, "_run", run_recorder)
    monkeypatch.setattr(
        _mod.snapshot_lib,
        "verify_restic_recent",
        lambda max_age_hours=24: _Result(True, "restic ok"),
    )
    monkeypatch.setattr(
        _mod.verify_lib,
        "verify_file_present",
        lambda path, executable=False: _Result(True, "present"),
    )


# ---------------------------------------------------------------------------
# Usage / arg handling.
# ---------------------------------------------------------------------------


def test_usage_error_on_no_mode():
    assert _mod.main([]) == 2


def test_usage_error_on_bad_mode():
    assert _mod.main(["--frobnicate"]) == 2


def test_dry_run_mutates_nothing(monkeypatch):
    """--dry-run must not call _run or any lib primitive; exit 0."""
    run = _RunRecorder()
    called = {"restic": False, "creds": False}

    def _no_restic(max_age_hours=24):
        called["restic"] = True
        return _Result(True)

    def _no_creds(path, executable=False):
        called["creds"] = True
        return _Result(True)

    monkeypatch.setattr(_mod, "_run", run)
    monkeypatch.setattr(_mod.snapshot_lib, "verify_restic_recent", _no_restic)
    monkeypatch.setattr(_mod.verify_lib, "verify_file_present", _no_creds)

    assert _mod.main(["--dry-run"]) == 0
    assert run.calls == [], "dry-run must not invoke any subprocess"
    assert not called["restic"], "dry-run must not check Restic"
    assert not called["creds"], "dry-run must not check creds"


# ---------------------------------------------------------------------------
# Gate ORDERING: Restic -> venv -> creds -> self-check.
# ---------------------------------------------------------------------------


def test_apply_gate_ordering(monkeypatch):
    """Full apply runs the gates in the required order and exits 0."""
    order: list[str] = []

    def _restic(max_age_hours=24):
        order.append("restic")
        return _Result(True)

    def _creds(path, executable=False):
        order.append("creds")
        return _Result(True)

    def _run(argv, cwd=None):
        if _mod._UV in argv[0]:
            order.append("venv")
        elif "--self-check" in argv:
            order.append("self_check")
        return (0, "", "")

    monkeypatch.setattr(_mod.snapshot_lib, "verify_restic_recent", _restic)
    monkeypatch.setattr(_mod.verify_lib, "verify_file_present", _creds)
    monkeypatch.setattr(_mod, "_run", _run)

    assert _mod.main(["--apply"]) == 0
    # creds is checked once per cred file (2), venv twice (uv venv + uv pip).
    assert order[0] == "restic", "Restic must be the first gate"
    assert "venv" in order and "creds" in order and "self_check" in order
    assert order.index("restic") < order.index("venv")
    assert order.index("venv") < order.index("creds")
    assert order.index("creds") < order.index("self_check")


# ---------------------------------------------------------------------------
# Halt-on-error at EACH gate.
# ---------------------------------------------------------------------------


def test_halt_on_restic_failure(monkeypatch):
    """A stale Restic snapshot halts before the venv is touched."""
    run = _RunRecorder()
    monkeypatch.setattr(_mod, "_run", run)
    monkeypatch.setattr(
        _mod.snapshot_lib,
        "verify_restic_recent",
        lambda max_age_hours=24: _Result(False, "too old", {"error_code": "RESTIC_TOO_OLD"}),
    )
    monkeypatch.setattr(
        _mod.verify_lib,
        "verify_file_present",
        lambda path, executable=False: _Result(True),
    )

    assert _mod.main(["--apply"]) == 1
    assert run.calls == [], "no subprocess (venv/self-check) after a Restic failure"


def test_backup_confirmed_skips_restic_check(monkeypatch):
    """--backup-confirmed bypasses the automated Restic log check."""
    run = _RunRecorder()
    called = {"restic": False}

    def _restic(max_age_hours=24):
        called["restic"] = True
        return _Result(False)  # would fail if called

    monkeypatch.setattr(_mod, "_run", run)
    monkeypatch.setattr(_mod.snapshot_lib, "verify_restic_recent", _restic)
    monkeypatch.setattr(
        _mod.verify_lib,
        "verify_file_present",
        lambda path, executable=False: _Result(True),
    )

    assert _mod.main(["--apply", "--backup-confirmed"]) == 0
    assert not called["restic"], "--backup-confirmed must skip the log check"


def test_halt_on_venv_create_failure(monkeypatch):
    """`uv venv` failure halts before creds/self-check; no pip install runs."""
    # First _run (uv venv) fails; nothing else should run.
    run = _RunRecorder(responses=[(1, "", "uv venv boom")])
    _patch_all_pass(monkeypatch, run)

    assert _mod.main(["--apply"]) == 1
    assert len(run.calls) == 1, "must halt after the failing `uv venv`"
    assert "venv" in run.calls[0]["argv"]


def test_halt_on_pip_install_failure(monkeypatch):
    """`uv pip install` failure halts before creds/self-check."""
    # (uv venv ok, uv pip install fails).
    run = _RunRecorder(responses=[(0, "", ""), (1, "", "resolve failed")])
    _patch_all_pass(monkeypatch, run)

    assert _mod.main(["--apply"]) == 1
    assert len(run.calls) == 2, "must halt after the failing `uv pip install`"
    assert "pip" in run.calls[1]["argv"]


def test_halt_on_creds_absent(monkeypatch):
    """Missing staged creds -> clear failure, self-check never runs."""
    # venv steps succeed; then creds check fails; self-check must not run.
    run = _RunRecorder(responses=[(0, "", ""), (0, "", "")])
    monkeypatch.setattr(_mod, "_run", run)
    monkeypatch.setattr(
        _mod.snapshot_lib,
        "verify_restic_recent",
        lambda max_age_hours=24: _Result(True),
    )
    monkeypatch.setattr(
        _mod.verify_lib,
        "verify_file_present",
        lambda path, executable=False: _Result(False, "missing", {"error_code": "FILE_MISSING"}),
    )

    assert _mod.main(["--apply"]) == 1
    # Only the two venv subprocess calls ran — no self-check.
    assert len(run.calls) == 2
    assert all("--self-check" not in c["argv"] for c in run.calls)


def test_creds_absent_message_is_clear(monkeypatch, capsys):
    """Creds-absent path prints an actionable 'stage creds first' recovery."""
    run = _RunRecorder(responses=[(0, "", ""), (0, "", "")])
    monkeypatch.setattr(_mod, "_run", run)
    monkeypatch.setattr(
        _mod.snapshot_lib,
        "verify_restic_recent",
        lambda max_age_hours=24: _Result(True),
    )
    monkeypatch.setattr(
        _mod.verify_lib,
        "verify_file_present",
        lambda path, executable=False: _Result(False),
    )

    _mod.main(["--apply"])
    captured = capsys.readouterr()
    assert "scp" in captured.err and "creds" in captured.err.lower()


def test_self_check_failure_fails_deploy(monkeypatch):
    """A non-zero helper --self-check fails the whole deploy."""
    def _run(argv, cwd=None):
        if "--self-check" in argv:
            return (3, "", "ERROR: auth_failed")
        return (0, "", "")

    monkeypatch.setattr(_mod, "_run", _run)
    monkeypatch.setattr(
        _mod.snapshot_lib,
        "verify_restic_recent",
        lambda max_age_hours=24: _Result(True),
    )
    monkeypatch.setattr(
        _mod.verify_lib,
        "verify_file_present",
        lambda path, executable=False: _Result(True),
    )

    assert _mod.main(["--apply"]) == 1


# ---------------------------------------------------------------------------
# Idempotent venv provisioning (re-run is safe) + correct uv invocation shape.
# ---------------------------------------------------------------------------


def test_venv_provision_is_idempotent_rerun(monkeypatch):
    """A second full apply issues the SAME uv commands — no cleanup/destroy.

    Idempotency here means the provisioning commands (`uv venv`, `uv pip
    install`) are re-run verbatim and each is a no-op refresh; the script never
    deletes an existing venv.
    """
    run1 = _RunRecorder()
    _patch_all_pass(monkeypatch, run1)
    assert _mod.main(["--apply"]) == 0
    first_argv = run1.argv_list

    run2 = _RunRecorder()
    _patch_all_pass(monkeypatch, run2)
    assert _mod.main(["--apply"]) == 0
    second_argv = run2.argv_list

    assert first_argv == second_argv, "re-run must issue identical commands (idempotent)"
    # No destructive command (rm / --clear / delete) anywhere.
    flat = " ".join(tok for argv in first_argv for tok in argv)
    assert "rm " not in flat and "--clear" not in flat and "delete" not in flat


def test_uv_invocation_shape(monkeypatch):
    """uv is called from ~/.local/bin/uv with the --python <venv>/bin/python form.

    NOT `-m uv` inside the venv (risk flagged in the WP prompt).
    """
    run = _RunRecorder()
    _patch_all_pass(monkeypatch, run)
    assert _mod.main(["--apply"]) == 0

    venv_cmds = [a for a in run.argv_list if a and a[0] == _mod._UV]
    assert len(venv_cmds) == 2, "expected exactly `uv venv` and `uv pip install`"

    venv_create, pip_install = venv_cmds
    assert venv_create[:2] == [_mod._UV, "venv"]
    assert "--python" in venv_create and "3.12" in venv_create

    assert pip_install[:3] == [_mod._UV, "pip", "install"]
    assert "--python" in pip_install
    py_idx = pip_install.index("--python")
    assert pip_install[py_idx + 1] == str(_mod._VENV_PYTHON)
    # deps pinned INLINE with == pins.
    assert any(dep.startswith("google-api-python-client==") for dep in pip_install)
    assert any(dep.startswith("google-auth==") for dep in pip_install)
    assert any(dep.startswith("google-auth-oauthlib==") for dep in pip_install)
    # never `-m uv`.
    assert "-m" not in pip_install and "-m" not in venv_create


def test_script_never_copies_secrets(monkeypatch):
    """The apply path issues no scp/cp of any cred file — presence-check only."""
    run = _RunRecorder()
    _patch_all_pass(monkeypatch, run)
    assert _mod.main(["--apply"]) == 0

    flat = " ".join(tok for argv in run.argv_list for tok in argv)
    assert "scp" not in flat, "script must NOT copy secrets"
    assert "client_secret.json" not in flat and "token.json" not in flat


def test_self_check_runs_from_checkout_via_venv_python(monkeypatch):
    """Self-check runs `-m scripts.google.calendar_helper` under the venv python,
    with cwd = the repo checkout."""
    run = _RunRecorder()
    _patch_all_pass(monkeypatch, run)
    assert _mod.main(["--apply"]) == 0

    self_check = next(c for c in run.calls if "--self-check" in c["argv"])
    argv = self_check["argv"]
    assert argv[0] == str(_mod._VENV_PYTHON)
    assert argv[1:3] == ["-m", "scripts.google.calendar_helper"]
    assert "--account" in argv and "personal" in argv
    assert self_check["cwd"] == _mod._REPO_ROOT


# ---------------------------------------------------------------------------
# Manifest schema validity (T014) — via the lib validator.
# ---------------------------------------------------------------------------


def test_manifest_validates_against_schema():
    from scripts.deploy.lib import manifest as manifest_mod

    result = manifest_mod.validate_manifest_file(_MANIFEST_PATH)
    assert result.ok, f"manifest invalid: {result.summary} :: {result.details}"


def test_manifest_declares_expected_fields():
    from scripts.deploy.lib import manifest as manifest_mod

    data = manifest_mod.load_manifest(_MANIFEST_PATH)
    assert data["schema_version"] == "v1"
    assert data["name"] == "felix-calendar-helper"
    assert data["mission_slug"] == "felix-calendar-helper-01KX4H3C"
    assert data["tier"] == 3
    assert data["entrypoint"] == "scripts/deploy/deploy-felix-calendar-helper.py"
    assert data["audited_surface"] is True
    # Queued manifest must NOT carry applied-only fields.
    assert "applied_at" not in data
    assert "apply_mode" not in data
    # Post-verification runs the self-check via the venv python.
    post = data["verification"]["post"]
    assert any("--self-check" in cmd and "--account personal" in cmd for cmd in post)


def test_manifest_not_prenumbered():
    """The queued manifest filename must not carry an applied NNNN- prefix."""
    assert _MANIFEST_PATH.name == "felix-calendar-helper.yaml"
    assert not _MANIFEST_PATH.name[0].isdigit()


def test_deploy_script_is_executable():
    """felix-deployer's applier invokes the entrypoint DIRECTLY
    (``[entrypoint, "--dry-run"]``, no ``python3`` prefix — see
    scripts/deploy/lib/apply.py), so the script MUST be executable with a
    shebang. Regression: it shipped 100644, which failed the deployer dry-run
    ("dry-run failed; not applying") while ``python3 <script>`` still worked."""
    script = _REPO_ROOT / "scripts/deploy/deploy-felix-calendar-helper.py"
    assert os.access(script, os.X_OK), f"{script} must be executable (chmod +x)"
    assert script.read_text(encoding="utf-8").startswith("#!/usr/bin/env python3")
