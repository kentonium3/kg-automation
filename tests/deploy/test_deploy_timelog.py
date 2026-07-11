"""Tests for scripts/deploy/deploy-timelog.py + its manifest (WP05, #703).

Covers T014/T015: the deploy entrypoint's four ordered steps (venv/deps ->
creds+workbook presence -> no-emit self-test -> prompt-sync+verify),
halt-on-error at each step, the #711 self-test gate (go-live reached only on
a clean self-test), and manifest schema validity. All subprocess / uv /
alert-bus / service-inventory primitives are mocked — NO network, NO office2
access, NO real Google API call.

The entrypoint file is hyphenated (deploy-timelog.py), which is not
importable via dotted form; it is loaded with importlib, matching the
sibling test_deploy_felix_calendar_helper.py pattern.
"""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import sys

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_ENTRYPOINT_PATH = _REPO_ROOT / "scripts" / "deploy" / "deploy-timelog.py"


def _resolve_manifest_path() -> pathlib.Path:
    """Locate the timelog manifest (queued pre-deploy, applied post-deploy)."""
    queued = _REPO_ROOT / "deploys" / "queued" / "timelog.yaml"
    if queued.exists():
        return queued
    applied = sorted((_REPO_ROOT / "deploys" / "applied").glob("*-timelog.yaml"))
    if applied:
        return applied[-1]
    return queued


_MANIFEST_PATH = _resolve_manifest_path()
_MANIFEST_IS_QUEUED = _MANIFEST_PATH.parent.name == "queued"


def _load_entrypoint():
    """Load the hyphenated-named entrypoint module via importlib."""
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    spec = importlib.util.spec_from_file_location("deploy_timelog", _ENTRYPOINT_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


_mod = _load_entrypoint()


# ---------------------------------------------------------------------------
# Helpers: a scripted _run recorder + a clean unknown_client self-test JSON.
# ---------------------------------------------------------------------------


class _RunRecorder:
    """Callable that records each _run invocation and returns scripted results.

    ``responses`` is a list of (returncode, stdout, stderr) consumed in
    order, keyed loosely by call sequence. Missing responses default to a
    generic success (0, "", "").
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


# The clean, happy-path `timelog` self-test JSON: a guaranteed-unresolvable
# client must return `unknown_client` (never reach append-row, never alert).
_CLEAN_TIMELOG_SELF_TEST_STDOUT = json.dumps(
    {"status": "unknown_client", "heard": _mod._SELF_TEST_CLIENT, "closest": None}
)


def _fake_run_clean(argv, cwd=None):
    """Default happy-path ``_run``: sheets_helper self-check ok, timelog
    self-test returns a clean unknown_client, every systemctl call ok."""
    if "scripts.google.timelog" in " ".join(argv):
        return (0, _CLEAN_TIMELOG_SELF_TEST_STDOUT, "")
    return (0, "", "")


def _write_deployed_main(tmp_path, *, has_marker=True):
    """Materialize a deployed main AGENTS.md; returns its Path."""
    p = tmp_path / "main-AGENTS.md"
    body = "# main prompt\n\n"
    if has_marker:
        body += _mod._TIMELOG_RECOGNIZER_MARKER + "\n\nsome recognizer prose\n"
    p.write_text(body, encoding="utf-8")
    return p


def _patch_all_pass(monkeypatch, tmp_path, run_recorder=None):
    """Patch every external dependency so a full --apply succeeds.

    If *run_recorder* has scripted ``responses`` queued (e.g. to force a
    step to fail), those are consumed in call order; once exhausted, calls
    fall back to the clean happy-path response for that argv shape.
    """
    run = run_recorder or _RunRecorder()

    def _fake_run(argv, cwd=None):
        run.calls.append({"argv": list(argv), "cwd": cwd})
        if run._responses:
            return run._responses.pop(0)
        return _fake_run_clean(argv, cwd)

    monkeypatch.setattr(_mod, "_run", _fake_run)
    monkeypatch.setattr(_mod, "_VENV_PYTHON", tmp_path / "venv" / "bin" / "python")
    monkeypatch.setattr(_mod, "_CREDS_DIR", tmp_path / "creds")
    creds = tuple((tmp_path / "creds" / n) for n in ("client_secret.json", "token.json"))
    monkeypatch.setattr(_mod, "_CRED_FILES", creds)
    (tmp_path / "creds").mkdir(parents=True, exist_ok=True)
    for c in creds:
        c.write_text("{}", encoding="utf-8")
    workbook_config = tmp_path / "workbook.json"
    workbook_config.write_text('{"spreadsheet_id": "abc"}', encoding="utf-8")
    monkeypatch.setattr(_mod, "_WORKBOOK_CONFIG", workbook_config)

    deployed_main = _write_deployed_main(tmp_path)
    monkeypatch.setattr(_mod, "_deployed_main_prompt", lambda: deployed_main)
    monkeypatch.setattr(_mod, "emit", lambda *a, **k: None)
    return run


# ---------------------------------------------------------------------------
# Usage / arg handling.
# ---------------------------------------------------------------------------


def test_usage_error_on_no_mode():
    assert _mod.main([]) == 2


def test_usage_error_on_bad_mode():
    assert _mod.main(["--frobnicate"]) == 2


def test_dry_run_prints_steps_and_exits_0(capsys):
    exit_code = _mod.main(["--dry-run"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "DRY-RUN" in captured.out
    assert "venv" in captured.out
    assert "self-test" in captured.out
    assert "agent-prompt-sync.service" in captured.out


def test_dry_run_never_calls_subprocess(monkeypatch):
    run = _RunRecorder()
    monkeypatch.setattr(_mod, "_run", run)
    _mod.main(["--dry-run"])
    assert run.calls == [], "dry-run must not invoke any subprocess"


# ---------------------------------------------------------------------------
# Step ORDERING: venv/deps -> creds+workbook -> self-test -> prompt-sync.
# ---------------------------------------------------------------------------


def test_apply_step_ordering(monkeypatch, tmp_path):
    """Full apply runs the steps in the required order and exits 0."""
    order: list[str] = []

    def _run(argv, cwd=None):
        joined = " ".join(argv)
        if _mod._UV in argv[0]:
            order.append("venv")
        elif "sheets_helper" in joined and "--self-check" in argv:
            order.append("sheets_self_check")
        elif "scripts.google.timelog" in joined:
            order.append("timelog_self_test")
            return (0, _CLEAN_TIMELOG_SELF_TEST_STDOUT, "")
        elif "agent-prompt-sync.service" in argv:
            order.append("prompt_sync")
        return (0, "", "")

    monkeypatch.setattr(_mod, "_run", _run)
    monkeypatch.setattr(_mod, "_VENV_PYTHON", tmp_path / "venv" / "bin" / "python")
    creds_dir = tmp_path / "creds"
    creds_dir.mkdir()
    creds = tuple((creds_dir / n) for n in ("client_secret.json", "token.json"))
    for c in creds:
        c.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(_mod, "_CREDS_DIR", creds_dir)
    monkeypatch.setattr(_mod, "_CRED_FILES", creds)
    workbook_config = tmp_path / "workbook.json"
    workbook_config.write_text('{"spreadsheet_id": "abc"}', encoding="utf-8")
    monkeypatch.setattr(_mod, "_WORKBOOK_CONFIG", workbook_config)
    monkeypatch.setattr(_mod, "_deployed_main_prompt", lambda: _write_deployed_main(tmp_path))
    monkeypatch.setattr(_mod, "emit", lambda *a, **k: None)

    assert _mod.main(["--apply"]) == 0
    assert "venv" in order
    assert order.index("venv") < order.index("sheets_self_check")
    assert order.index("sheets_self_check") < order.index("timelog_self_test")
    assert order.index("timelog_self_test") < order.index("prompt_sync")


# ---------------------------------------------------------------------------
# Halt-on-error at EACH step.
# ---------------------------------------------------------------------------


def test_halt_on_venv_create_failure(monkeypatch, tmp_path):
    run = _RunRecorder(responses=[(1, "", "uv venv boom")])
    _patch_all_pass(monkeypatch, tmp_path, run_recorder=run)

    assert _mod.main(["--apply"]) == 1
    assert len(run.calls) == 1
    assert "venv" in run.calls[0]["argv"]


def test_halt_on_pip_install_failure(monkeypatch, tmp_path):
    run = _RunRecorder(responses=[(0, "", ""), (1, "", "resolve failed")])
    _patch_all_pass(monkeypatch, tmp_path, run_recorder=run)

    assert _mod.main(["--apply"]) == 1
    assert len(run.calls) == 2
    assert "pip" in run.calls[1]["argv"]


def test_halt_on_creds_missing(monkeypatch, tmp_path):
    """Missing staged creds -> clear failure, self-test never runs."""
    run = _RunRecorder()
    _patch_all_pass(monkeypatch, tmp_path, run_recorder=run)
    # Remove one staged cred file after patching.
    _mod._CRED_FILES[0].unlink()

    assert _mod.main(["--apply"]) == 1
    assert not any(
        "self-check" in " ".join(c["argv"]) or "timelog" in " ".join(c["argv"])
        for c in run.calls
    ), "self-test must not run when creds are missing"


def test_halt_on_workbook_config_missing(monkeypatch, tmp_path):
    """Missing workbook-id config -> clear failure, self-test never runs."""
    run = _RunRecorder()
    _patch_all_pass(monkeypatch, tmp_path, run_recorder=run)
    _mod._WORKBOOK_CONFIG.unlink()

    assert _mod.main(["--apply"]) == 1
    assert not any(
        "self-check" in " ".join(c["argv"]) or "timelog" in " ".join(c["argv"])
        for c in run.calls
    ), "self-test must not run when the workbook config is missing"


def test_preconditions_message_names_both_stops(monkeypatch, tmp_path, capsys):
    """The failure recovery text names BOTH operator preconditions."""
    _patch_all_pass(monkeypatch, tmp_path)
    _mod._CRED_FILES[0].unlink()

    _mod.main(["--apply"])
    captured = capsys.readouterr()
    assert "re-consent" in captured.err.lower()
    assert "bootstrap" in captured.err.lower()


def test_halt_on_sheets_self_check_failure(monkeypatch, tmp_path):
    """A non-zero sheets_helper --self-check fails the whole deploy; timelog
    self-test never runs (nothing enabled/synced — #711)."""

    def _run(argv, cwd=None):
        joined = " ".join(argv)
        if "sheets_helper" in joined:
            return (1, "", "ERROR: auth_failed")
        return (0, "", "")

    _patch_all_pass(monkeypatch, tmp_path, run_recorder=_RunRecorder())
    monkeypatch.setattr(_mod, "_run", _run)

    assert _mod.main(["--apply"]) == 1


def test_halt_on_timelog_self_test_nonzero_exit(monkeypatch, tmp_path):
    """timelog exiting non-zero (a usage error, F9) fails the self-test gate."""

    def _run(argv, cwd=None):
        joined = " ".join(argv)
        if "scripts.google.timelog" in joined:
            return (2, "", "usage error")
        return (0, "", "")

    _patch_all_pass(monkeypatch, tmp_path, run_recorder=_RunRecorder())
    monkeypatch.setattr(_mod, "_run", _run)

    assert _mod.main(["--apply"]) == 1


def test_self_test_gate_blocks_on_unexpected_status(monkeypatch, tmp_path):
    """#711 property: if the self-test client unexpectedly resolves (or the
    normalizer returns anything other than `unknown_client`), the deploy
    FAILS here and prompt-sync is never reached — the gate does not assume
    success."""
    prompt_sync_called = {"value": False}

    def _run(argv, cwd=None):
        joined = " ".join(argv)
        if "scripts.google.timelog" in joined:
            dirty = json.dumps({"status": "logged", "receipt": "should not happen"})
            return (0, dirty, "")
        if "agent-prompt-sync.service" in argv:
            prompt_sync_called["value"] = True
        return (0, "", "")

    _patch_all_pass(monkeypatch, tmp_path, run_recorder=_RunRecorder())
    monkeypatch.setattr(_mod, "_run", _run)

    exit_code = _mod.main(["--apply"])

    assert exit_code == 1
    assert prompt_sync_called["value"] is False, (
        "prompt-sync must NEVER be reached when the self-test does not "
        "cleanly return unknown_client (#711 gate)"
    )


def test_halt_on_prompt_sync_start_failure(monkeypatch, tmp_path):
    def _run(argv, cwd=None):
        if "agent-prompt-sync.service" in argv:
            return (1, "", "start failed")
        return _fake_run_clean(argv)

    _patch_all_pass(monkeypatch, tmp_path, run_recorder=_RunRecorder())
    monkeypatch.setattr(_mod, "_run", _run)

    assert _mod.main(["--apply"]) == 1


def test_halt_on_recognizer_missing_in_deployed_main(monkeypatch, tmp_path):
    """The recognizer heading missing from deployed main's AGENTS.md fails
    the deploy even though prompt-sync itself succeeded."""
    _patch_all_pass(monkeypatch, tmp_path)
    no_marker_main = _write_deployed_main(tmp_path, has_marker=False)
    monkeypatch.setattr(_mod, "_deployed_main_prompt", lambda: no_marker_main)

    assert _mod.main(["--apply"]) == 1


def test_apply_full_success_path(monkeypatch, tmp_path):
    run = _patch_all_pass(monkeypatch, tmp_path)
    assert _mod.main(["--apply"]) == 0
    joined = [" ".join(a) for a in run.argv_list]
    assert any("sheets_helper" in c and "--self-check" in c for c in joined)
    assert any("scripts.google.timelog" in c for c in joined)
    assert any("agent-prompt-sync.service" in c for c in joined)


# ---------------------------------------------------------------------------
# Never copies secrets.
# ---------------------------------------------------------------------------


def test_script_never_copies_secrets(monkeypatch, tmp_path):
    run = _patch_all_pass(monkeypatch, tmp_path)
    assert _mod.main(["--apply"]) == 0

    flat = " ".join(tok for argv in run.argv_list for tok in argv)
    assert "scp" not in flat
    assert "client_secret.json" not in flat and "token.json" not in flat


# ---------------------------------------------------------------------------
# Reporting via the #701 bus (best-effort, never raises).
# ---------------------------------------------------------------------------


def test_report_emits_once_on_success(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(_mod, "emit", lambda alert: calls.append(alert))
    _patch_all_pass_without_emit_patch(monkeypatch, tmp_path)

    assert _mod.main(["--apply"]) == 0
    assert len(calls) == 1


def _patch_all_pass_without_emit_patch(monkeypatch, tmp_path):
    """Same as _patch_all_pass but leaves `emit` untouched for the caller."""
    run = _RunRecorder()

    def _fake_run(argv, cwd=None):
        run.calls.append({"argv": list(argv), "cwd": cwd})
        return _fake_run_clean(argv, cwd)

    monkeypatch.setattr(_mod, "_run", _fake_run)
    monkeypatch.setattr(_mod, "_VENV_PYTHON", tmp_path / "venv" / "bin" / "python")
    creds_dir = tmp_path / "creds"
    creds_dir.mkdir(exist_ok=True)
    creds = tuple((creds_dir / n) for n in ("client_secret.json", "token.json"))
    for c in creds:
        c.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(_mod, "_CREDS_DIR", creds_dir)
    monkeypatch.setattr(_mod, "_CRED_FILES", creds)
    workbook_config = tmp_path / "workbook.json"
    workbook_config.write_text('{"spreadsheet_id": "abc"}', encoding="utf-8")
    monkeypatch.setattr(_mod, "_WORKBOOK_CONFIG", workbook_config)
    monkeypatch.setattr(_mod, "_deployed_main_prompt", lambda: _write_deployed_main(tmp_path))
    return run


def test_report_never_raises_when_emit_broken(monkeypatch, tmp_path):
    def _broken_emit(*a, **k):
        raise RuntimeError("ntfy unreachable")

    monkeypatch.setattr(_mod, "emit", _broken_emit)
    _patch_all_pass_without_emit_patch(monkeypatch, tmp_path)

    # Must not raise even though `emit` blows up.
    assert _mod.main(["--apply"]) == 0


# ---------------------------------------------------------------------------
# Manifest schema validity (T015) — via the lib validator.
# ---------------------------------------------------------------------------


def test_manifest_validates_against_schema():
    from scripts.deploy.lib import manifest as manifest_mod

    result = manifest_mod.validate_manifest_file(_MANIFEST_PATH)
    assert result.ok, f"manifest invalid: {result.summary} :: {result.details}"


def test_manifest_declares_expected_fields():
    from scripts.deploy.lib import manifest as manifest_mod

    data = manifest_mod.load_manifest(_MANIFEST_PATH)
    assert data["schema_version"] == "v1"
    assert data["name"] == "timelog"
    assert data["issue"] == "kentonium3/kg-automation#703"
    assert data["tier"] == 2
    assert data["entrypoint"] == "scripts/deploy/deploy-timelog.py"
    assert data["audited_surface"] is False
    if _MANIFEST_IS_QUEUED:
        assert "applied_at" not in data
        assert "apply_mode" not in data
    else:
        assert "applied_at" in data
        assert data.get("apply_mode") == "manifest"
    post = data["verification"]["post"]
    assert any("sheets_helper" in cmd and "--self-check" in cmd for cmd in post)
    assert not any(cmd.strip().startswith("ssh office2-claude") for cmd in post)
    pre = data["verification"]["pre"]
    assert not any(cmd.strip().startswith("ssh office2-claude") for cmd in pre)


def test_manifest_not_prenumbered():
    if _MANIFEST_IS_QUEUED:
        assert _MANIFEST_PATH.name == "timelog.yaml"
        assert not _MANIFEST_PATH.name[0].isdigit()
    else:
        assert _MANIFEST_PATH.name.endswith("-timelog.yaml")
        assert _MANIFEST_PATH.name[0].isdigit()


def test_manifest_notes_name_both_preconditions():
    from scripts.deploy.lib import manifest as manifest_mod

    data = manifest_mod.load_manifest(_MANIFEST_PATH)
    notes = data.get("notes", "").lower()
    assert "re-consent" in notes
    assert "workbook" in notes and "bootstrap" in notes


# ---------------------------------------------------------------------------
# Exec bit + shebang (T014 definition-of-done).
# ---------------------------------------------------------------------------


def test_deploy_script_is_executable():
    """felix-deployer's applier invokes the entrypoint DIRECTLY, so the
    script MUST be executable with a shebang (0755, not 0644)."""
    script = _REPO_ROOT / "scripts/deploy/deploy-timelog.py"
    assert os.access(script, os.X_OK), f"{script} must be executable (chmod +x)"
    assert script.read_text(encoding="utf-8").startswith("#!/usr/bin/env python3")
