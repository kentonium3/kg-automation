"""Tests for scripts/deploy/deploy-felix-canary.py + its units + manifest (WP06).

Covers T029:
  * the #703 byte-identical-ExecStart guard — the deploy verifies the string it
    parses FROM the installed .service equals the canonical form the self-test
    exercises (and a static assertion that the source .service uses
    `/usr/bin/python3 -m scripts.canary.run`, never bare `python`);
  * SC-006 — the source .service declares
    `OnFailure=felix-canary-onfailure.service`;
  * the F9 gate FAILS the deploy (no enable) when the real-unit tick-signal /
    ledger assertion fails;
  * units are installed BEFORE `daemon-reload`;
  * `enable --now` happens ONLY after a clean gate;
  * manifest schema validity (tier 3, audited_surface, entrypoint, numbering).

All subprocess / systemctl / filesystem effects are mocked — NO real systemd,
NO office2 access. The entrypoint file is hyphenated
(deploy-felix-canary.py), which is not importable via dotted form; it is loaded
with importlib, matching the sibling test_deploy_felix_calendar_helper.py /
test_install_gateway_pythonpath_dropin.py pattern.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_ENTRYPOINT_PATH = _REPO_ROOT / "scripts" / "deploy" / "deploy-felix-canary.py"
_SERVICE_SRC = _REPO_ROOT / "scripts" / "office2" / "felix-canary.service"
_TIMER_SRC = _REPO_ROOT / "scripts" / "office2" / "felix-canary.timer"
_ONFAILURE_SRC = _REPO_ROOT / "scripts" / "office2" / "felix-canary-onfailure.service"
_MANIFEST_QUEUED = _REPO_ROOT / "deploys" / "queued" / "0017-felix-canary-registry.yaml"


def _load_entrypoint():
    """Load the hyphenated-named entrypoint module via importlib."""
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    spec = importlib.util.spec_from_file_location(
        "deploy_felix_canary",
        _ENTRYPOINT_PATH,
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_mod = _load_entrypoint()


def _resolve_manifest_path() -> pathlib.Path:
    """Locate the 0017 manifest.

    felix-deployer relocates the manifest from ``deploys/queued/`` to
    ``deploys/applied/<NNNN>-felix-canary-registry.yaml`` once applied, so the
    manifest lives in exactly one of the two directories depending on state.
    Resolve queued first (pre-deploy), then the applied copy (post-deploy).
    """
    if _MANIFEST_QUEUED.exists():
        return _MANIFEST_QUEUED
    applied = sorted(
        (_REPO_ROOT / "deploys" / "applied").glob("*-felix-canary-registry.yaml")
    )
    if applied:
        return applied[-1]
    return _MANIFEST_QUEUED


# ---------------------------------------------------------------------------
# Helpers: a scripted _run recorder that records order + argv.
# ---------------------------------------------------------------------------


class _RunRecorder:
    """Callable that records each _run invocation and returns scripted results.

    ``responses`` maps a match-substring (found in the argv) to a
    ``(returncode, stdout, stderr)`` tuple. The first matching key wins; an
    unmatched call defaults to success ``(0, "", "")``. ``calls`` preserves the
    invocation order for ordering assertions.
    """

    def __init__(self, responses: dict[str, tuple[int, str, str]] | None = None):
        self.calls: list[list[str]] = []
        self._responses = responses or {}

    def __call__(self, argv, cwd=None):
        self.calls.append(list(argv))
        joined = " ".join(argv)
        for needle, resp in self._responses.items():
            if needle in joined:
                return resp
        return (0, "", "")


def _install_fake_units(monkeypatch, tmp_path, *, execstart: str | None = None) -> pathlib.Path:
    """Point the module's install dir at tmp_path and write a fake installed
    .service whose ExecStart is *execstart* (defaults to the expected string)."""
    systemd_dir = tmp_path / "systemd-user"
    systemd_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(_mod, "_SYSTEMD_USER_DIR", systemd_dir)
    exec_line = execstart if execstart is not None else _mod._EXPECTED_EXECSTART
    (systemd_dir / _mod._SERVICE_UNIT).write_text(
        "[Service]\nType=oneshot\nExecStart=" + exec_line + "\n",
        encoding="utf-8",
    )
    return systemd_dir


def _patch_state(monkeypatch, tmp_path):
    """Redirect the tick + ledger paths under tmp_path and return the paths."""
    state_dir = tmp_path / "state"
    ledger_dir = tmp_path / "ledger"
    tick_path = state_dir / "last-tick.json"
    monkeypatch.setattr(_mod, "_STATE_DIR", state_dir)
    monkeypatch.setattr(_mod, "_TICK_PATH", tick_path)
    monkeypatch.setattr(_mod, "_LEDGER_DIR", ledger_dir)
    return state_dir, ledger_dir, tick_path


# ---------------------------------------------------------------------------
# Static checks on the source systemd units (T025 / #703 / SC-006).
# ---------------------------------------------------------------------------


def test_service_execstart_is_module_form_never_bare_python():
    """The .service must run `/usr/bin/python3 -m scripts.canary.run --once`
    — module form, absolute interpreter, never a bare `python` (the -m trap)."""
    text = _SERVICE_SRC.read_text(encoding="utf-8")
    exec_lines = [ln for ln in text.splitlines() if ln.strip().startswith("ExecStart=")]
    assert len(exec_lines) == 1, "exactly one ExecStart line expected"
    execstart = exec_lines[0].split("=", 1)[1].strip()
    assert execstart == "/usr/bin/python3 -m scripts.canary.run --once"
    # Never a bare `python ` (a space-delimited token) — office2 is python3-only.
    assert " python " not in f" {execstart} "
    assert execstart.startswith("/usr/bin/python3 ")
    assert "-m scripts.canary.run" in execstart


def test_service_declares_onfailure_shim():
    """SC-006: the .service must wire OnFailure to the shim unit (trust-scan
    omitted this — a copy-paste would miss crash detection)."""
    text = _SERVICE_SRC.read_text(encoding="utf-8")
    assert "OnFailure=felix-canary-onfailure.service" in text


def test_service_has_expected_environment_and_envfile():
    text = _SERVICE_SRC.read_text(encoding="utf-8")
    assert "Environment=HOME=/home/claude" in text
    assert "Environment=PYTHONPATH=/home/claude/kg-automation" in text
    assert "WorkingDirectory=/home/claude/kg-automation" in text
    assert "EnvironmentFile=-/home/claude/.config/felix/alert-bus/env" in text
    assert "Type=oneshot" in text


def test_timer_has_15min_cadence_and_install():
    text = _TIMER_SRC.read_text(encoding="utf-8")
    assert "OnBootSec=5min" in text
    assert "OnUnitActiveSec=15min" in text
    assert "Persistent=true" in text
    assert "WantedBy=timers.target" in text


def test_onfailure_unit_emits_error_via_bus_shim():
    text = _ONFAILURE_SRC.read_text(encoding="utf-8")
    assert "Type=oneshot" in text
    assert "scripts/common/alert_bus.sh emit" in text
    assert "--severity error" in text
    assert "--source felix-canary/onfailure" in text
    assert "EnvironmentFile=-/home/claude/.config/felix/alert-bus/env" in text


def test_expected_execstart_matches_source_service():
    """The deploy's canonical _EXPECTED_EXECSTART must equal the source unit's
    ExecStart — the #703 guard has no meaning if the constant drifts from the
    unit the deploy actually installs."""
    text = _SERVICE_SRC.read_text(encoding="utf-8")
    execstart = next(
        ln.split("=", 1)[1].strip()
        for ln in text.splitlines()
        if ln.strip().startswith("ExecStart=")
    )
    assert _mod._EXPECTED_EXECSTART == execstart


# ---------------------------------------------------------------------------
# Usage / dry-run.
# ---------------------------------------------------------------------------


def test_usage_error_on_no_mode():
    assert _mod.main([]) == 2


def test_usage_error_on_bad_mode():
    assert _mod.main(["--frobnicate"]) == 2


def test_dry_run_mutates_nothing(monkeypatch):
    """--dry-run must not call _run or emit; exit 0."""
    run = _RunRecorder()
    monkeypatch.setattr(_mod, "_run", run)
    emitted = {"called": False}

    def _no_emit(*a, **k):
        emitted["called"] = True

    monkeypatch.setattr(_mod, "emit", _no_emit)
    assert _mod.main(["--dry-run"]) == 0
    assert run.calls == [], "dry-run must not invoke any subprocess"
    assert not emitted["called"], "dry-run must not emit"


# ---------------------------------------------------------------------------
# #703 byte-identical ExecStart guard.
# ---------------------------------------------------------------------------


def test_execstart_guard_parses_installed_service_and_matches(monkeypatch, tmp_path):
    """The guard parses the ExecStart FROM the installed .service and asserts
    it equals the canonical form — a byte-identical match passes."""
    _install_fake_units(monkeypatch, tmp_path)
    ok, details = _mod._step_verify_execstart()
    assert ok is True
    assert details["parsed_execstart"] == _mod._EXPECTED_EXECSTART
    assert details["expected_execstart"] == _mod._EXPECTED_EXECSTART


def test_execstart_guard_fails_on_drift(monkeypatch, tmp_path):
    """A hand-typed / drifted ExecStart in the installed unit fails the guard."""
    _install_fake_units(
        monkeypatch,
        tmp_path,
        execstart="/usr/bin/python -m scripts.canary.run --once",  # bare python
    )
    ok, details = _mod._step_verify_execstart()
    assert ok is False
    assert "drift" in details["error"].lower()


def test_apply_fails_when_execstart_drifts_and_never_enables(monkeypatch, tmp_path):
    """A drifted installed ExecStart fails the deploy before enable is reached."""
    # Install units into tmp then overwrite the .service ExecStart with a drift.
    systemd_dir = tmp_path / "systemd-user"
    monkeypatch.setattr(_mod, "_SYSTEMD_USER_DIR", systemd_dir)

    def _drift_install():
        systemd_dir.mkdir(parents=True, exist_ok=True)
        (systemd_dir / _mod._SERVICE_UNIT).write_text(
            "[Service]\nExecStart=/usr/bin/python3 -m scripts.canary.run\n",  # missing --once
            encoding="utf-8",
        )
        return True, {"installed": [str(systemd_dir / _mod._SERVICE_UNIT)]}

    run = _RunRecorder()
    monkeypatch.setattr(_mod, "_step_install_units", _drift_install)
    monkeypatch.setattr(_mod, "_run", run)
    monkeypatch.setattr(_mod, "emit", lambda *a, **k: None)

    assert _mod.main(["--apply"]) == 1
    joined = [" ".join(c) for c in run.calls]
    # daemon-reload happens; enable must NOT.
    assert not any("enable" in c for c in joined), "enable must not run on ExecStart drift"


# ---------------------------------------------------------------------------
# Install BEFORE daemon-reload.
# ---------------------------------------------------------------------------


def test_units_installed_before_daemon_reload(monkeypatch, tmp_path):
    """The three units are copied into the systemd dir BEFORE `daemon-reload`
    (a unit file does nothing until installed + reloaded)."""
    _patch_state(monkeypatch, tmp_path)
    systemd_dir = tmp_path / "systemd-user"
    monkeypatch.setattr(_mod, "_SYSTEMD_USER_DIR", systemd_dir)

    order: list[str] = []

    real_install = _mod._step_install_units

    def _tracked_install():
        order.append("install")
        return real_install()

    def _run(argv, cwd=None):
        joined = " ".join(argv)
        if "daemon-reload" in joined:
            order.append("daemon-reload")
            # At daemon-reload time, all three units must already be on disk.
            for name in _mod._UNIT_NAMES:
                assert (systemd_dir / name).exists(), f"{name} not installed before reload"
        elif "--self-check" in joined:
            return (0, "status=ok\n", "")
        elif "start felix-canary.service" in joined:
            _write_fresh_tick_and_ledger(monkeypatch, tmp_path)
        return (0, "", "")

    monkeypatch.setattr(_mod, "_step_install_units", _tracked_install)
    monkeypatch.setattr(_mod, "_run", _run)
    monkeypatch.setattr(_mod, "emit", lambda *a, **k: None)

    assert _mod.main(["--apply"]) == 0
    assert order[0] == "install"
    assert order.index("install") < order.index("daemon-reload")


# ---------------------------------------------------------------------------
# F9 real-unit verify gate: fails the deploy → no enable.
# ---------------------------------------------------------------------------


def _write_fresh_tick_and_ledger(monkeypatch, tmp_path, *, ledger: bool = True):
    """Simulate what the real unit does: write a fresh tick + a ledger line."""
    state_dir = _mod._TICK_PATH.parent
    state_dir.mkdir(parents=True, exist_ok=True)
    # A monotonically-later timestamp than any prior tick.
    ts = "2026-07-11T12:00:00+00:00"
    _mod._TICK_PATH.write_text(json.dumps({"completed_at_utc": ts}), encoding="utf-8")
    if ledger:
        _mod._LEDGER_DIR.mkdir(parents=True, exist_ok=True)
        (_mod._LEDGER_DIR / "2026-07-11.jsonl").write_text(
            json.dumps({"component_id": "x", "status": "healthy"}) + "\n",
            encoding="utf-8",
        )


def test_real_unit_verify_passes_when_tick_and_ledger_land(monkeypatch, tmp_path):
    _patch_state(monkeypatch, tmp_path)

    def _run(argv, cwd=None):
        if "start felix-canary.service" in " ".join(argv):
            _write_fresh_tick_and_ledger(monkeypatch, tmp_path)
        return (0, "", "")

    monkeypatch.setattr(_mod, "_run", _run)
    ok, details = _mod._step_real_unit_verify()
    assert ok is True
    assert details["tick_after"] == "2026-07-11T12:00:00+00:00"


def test_real_unit_verify_fails_when_no_tick(monkeypatch, tmp_path):
    """If the real unit writes NO tick-signal, the gate fails."""
    _patch_state(monkeypatch, tmp_path)

    def _run(argv, cwd=None):
        return (0, "", "")  # unit "ran" but wrote nothing

    monkeypatch.setattr(_mod, "_run", _run)
    ok, details = _mod._step_real_unit_verify()
    assert ok is False
    assert "last-tick.json absent" in details["error"] or "did not advance" in details["error"]


def test_real_unit_verify_fails_when_tick_but_no_ledger(monkeypatch, tmp_path):
    """A fresh tick but NO ledger line still fails the gate (both required)."""
    _patch_state(monkeypatch, tmp_path)

    def _run(argv, cwd=None):
        if "start felix-canary.service" in " ".join(argv):
            _write_fresh_tick_and_ledger(monkeypatch, tmp_path, ledger=False)
        return (0, "", "")

    monkeypatch.setattr(_mod, "_run", _run)
    ok, details = _mod._step_real_unit_verify()
    assert ok is False
    assert "ledger" in details["error"].lower()


def test_real_unit_verify_fails_on_stale_tick(monkeypatch, tmp_path):
    """A pre-existing tick that the real unit does NOT advance fails the gate."""
    _patch_state(monkeypatch, tmp_path)
    # Seed a stale tick that the "run" never updates.
    state_dir = _mod._TICK_PATH.parent
    state_dir.mkdir(parents=True, exist_ok=True)
    _mod._TICK_PATH.write_text(
        json.dumps({"completed_at_utc": "2026-07-11T00:00:00+00:00"}), encoding="utf-8"
    )

    def _run(argv, cwd=None):
        return (0, "", "")  # unit "ran" but did not rewrite the tick

    monkeypatch.setattr(_mod, "_run", _run)
    ok, details = _mod._step_real_unit_verify()
    assert ok is False
    assert "did not advance" in details["error"]


def test_apply_fails_at_gate_and_never_enables(monkeypatch, tmp_path):
    """When the F9 real-unit assertion fails, the deploy exits 1 and NEVER
    reaches `enable --now` (the #711 lesson — no unverified go-live)."""
    _install_fake_units(monkeypatch, tmp_path)
    _patch_state(monkeypatch, tmp_path)

    def _run(argv, cwd=None):
        joined = " ".join(argv)
        if "--self-check" in joined:
            return (0, "status=ok\n", "")
        # start the unit but write NOTHING → the tick/ledger assertion fails.
        return (0, "", "")

    run = _RunRecorder()

    def _tracked_run(argv, cwd=None):
        run.calls.append(list(argv))
        return _run(argv, cwd)

    monkeypatch.setattr(_mod, "_run", _tracked_run)
    monkeypatch.setattr(_mod, "emit", lambda *a, **k: None)

    assert _mod.main(["--apply"]) == 1
    joined = [" ".join(c) for c in run.calls]
    assert any("start felix-canary.service" in c for c in joined), "real unit must be started"
    assert not any("enable" in c for c in joined), "enable must NOT run after a failed gate"


# ---------------------------------------------------------------------------
# enable happens ONLY after a fully clean gate.
# ---------------------------------------------------------------------------


def test_apply_enables_only_after_clean_gate(monkeypatch, tmp_path):
    """The happy path installs → reload → verify → enable, in that order, and
    `enable --now felix-canary.timer` is the LAST systemctl call."""
    _install_fake_units(monkeypatch, tmp_path)
    _patch_state(monkeypatch, tmp_path)

    run = _RunRecorder()

    def _tracked_run(argv, cwd=None):
        run.calls.append(list(argv))
        joined = " ".join(argv)
        if "--self-check" in joined:
            return (0, "status=ok\n", "")
        if "start felix-canary.service" in joined:
            _write_fresh_tick_and_ledger(monkeypatch, tmp_path)
        return (0, "", "")

    monkeypatch.setattr(_mod, "_run", _tracked_run)
    monkeypatch.setattr(_mod, "emit", lambda *a, **k: None)

    assert _mod.main(["--apply"]) == 0
    joined = [" ".join(c) for c in run.calls]
    reload_idx = next(i for i, c in enumerate(joined) if "daemon-reload" in c)
    selfcheck_idx = next(i for i, c in enumerate(joined) if "--self-check" in c)
    start_idx = next(i for i, c in enumerate(joined) if "start felix-canary.service" in c)
    enable_idx = next(i for i, c in enumerate(joined) if "enable --now felix-canary.timer" in c or ("enable" in c and "felix-canary.timer" in c))
    assert reload_idx < selfcheck_idx < start_idx < enable_idx
    assert enable_idx == len(joined) - 1, "enable must be the final systemctl call"


def test_apply_halts_when_self_check_not_ok(monkeypatch, tmp_path):
    """A self-check that does not print status=ok halts before the real-unit
    run and before enable."""
    _install_fake_units(monkeypatch, tmp_path)
    _patch_state(monkeypatch, tmp_path)

    run = _RunRecorder()

    def _tracked_run(argv, cwd=None):
        run.calls.append(list(argv))
        if "--self-check" in " ".join(argv):
            return (1, "status=error state_dir_unwritable\n", "")
        return (0, "", "")

    monkeypatch.setattr(_mod, "_run", _tracked_run)
    monkeypatch.setattr(_mod, "emit", lambda *a, **k: None)

    assert _mod.main(["--apply"]) == 1
    joined = [" ".join(c) for c in run.calls]
    assert not any("start felix-canary.service" in c for c in joined)
    assert not any("enable" in c for c in joined)


# ---------------------------------------------------------------------------
# Manifest schema validity + numbering.
# ---------------------------------------------------------------------------


def test_manifest_is_schema_valid_tier3_audited():
    import yaml
    from jsonschema import Draft202012Validator

    schema_path = _REPO_ROOT / "deploys" / "schema" / "manifest-v1.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    data = yaml.safe_load(_resolve_manifest_path().read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(data)  # raises on any violation

    assert data["tier"] == 3
    assert data["audited_surface"] is True
    assert data["entrypoint"] == "scripts/deploy/deploy-felix-canary.py"
    assert data["name"] == "felix-canary-registry"
    assert data["mission_slug"] == "felix-canary-registry-01KX8T7B"


def test_manifest_numbering_is_0017():
    path = _resolve_manifest_path()
    assert path.name.startswith("0017-felix-canary-registry")


# ---------------------------------------------------------------------------
# The deploy entrypoint is executable (felix-deployer runs it directly).
# ---------------------------------------------------------------------------


def test_entrypoint_is_executable():
    import os

    assert os.access(_ENTRYPOINT_PATH, os.X_OK), "deploy script must be chmod +x"
