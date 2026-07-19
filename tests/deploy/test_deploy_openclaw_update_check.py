"""Tests for scripts/deploy/deploy-openclaw-update-check.py + its units + manifest (#628).

Covers:
  * the #703 byte-identical-ExecStart guard — the deploy verifies the string it
    parses FROM the installed .service equals the canonical form the self-test
    exercises (and a static assertion that the source .service uses
    `/usr/bin/python3 -m scripts.openclaw.check_ecosystem_updates`, never bare
    `python`);
  * the OnFailure shim is declared + emits an ERROR via the bus shim;
  * the real-unit clean-pass gate FAILS the deploy (no enable) when the unit run
    exits non-zero;
  * the self-check gate FAILS the deploy (no enable) when self-check is not ok;
  * units are installed BEFORE `daemon-reload`, and `enable --now` happens ONLY
    after a clean gate;
  * manifest schema validity (tier 3, audited_surface, entrypoint, issue ref).

All subprocess / systemctl / filesystem effects are mocked — NO real systemd, NO
office2 access. The hyphenated entrypoint is loaded with importlib, matching the
sibling test_deploy_felix_canary.py pattern.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

from scripts.deploy.lib.manifest import validate_manifest_file

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_ENTRYPOINT_PATH = _REPO_ROOT / "scripts" / "deploy" / "deploy-openclaw-update-check.py"
_SERVICE_SRC = _REPO_ROOT / "scripts" / "office2" / "felix-openclaw-updates.service"
_TIMER_SRC = _REPO_ROOT / "scripts" / "office2" / "felix-openclaw-updates.timer"
_ONFAILURE_SRC = _REPO_ROOT / "scripts" / "office2" / "felix-openclaw-updates-onfailure.service"
_MANIFEST_QUEUED = _REPO_ROOT / "deploys" / "queued" / "0020-openclaw-ecosystem-update-check.yaml"


def _load_entrypoint():
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    spec = importlib.util.spec_from_file_location("deploy_openclaw_update_check", _ENTRYPOINT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_mod = _load_entrypoint()


def _resolve_manifest_path() -> pathlib.Path:
    """queued pre-deploy, applied/<NNNN>-... once felix-deployer relocates it."""
    if _MANIFEST_QUEUED.exists():
        return _MANIFEST_QUEUED
    applied = sorted(
        (_REPO_ROOT / "deploys" / "applied").glob("*-openclaw-ecosystem-update-check.yaml")
    )
    return applied[-1] if applied else _MANIFEST_QUEUED


# ---------------------------------------------------------------------------
# A scripted _run recorder.
# ---------------------------------------------------------------------------


class _RunRecorder:
    def __init__(self, responses=None, tick_path=None):
        self.calls: list[list[str]] = []
        self._responses = responses or {}
        # When set, a successful `systemctl start` writes a fresh tick here to
        # simulate the real unit's state write (the deploy asserts it advanced).
        self._tick_path = tick_path
        self._tick_seq = 0

    def __call__(self, argv, cwd=None):
        self.calls.append(list(argv))
        joined = " ".join(argv)
        resp = (0, "", "")
        for needle, r in self._responses.items():
            if needle in joined:
                resp = r
                break
        if self._tick_path is not None and "start felix-openclaw-updates.service" in joined and resp[0] == 0:
            self._tick_seq += 1
            self._tick_path.parent.mkdir(parents=True, exist_ok=True)
            self._tick_path.write_text(
                '{"status": "success", "completed_at_utc": "2026-07-19T12:00:0%d Z"}' % self._tick_seq,
                encoding="utf-8",
            )
        return resp


def _install_fake_units(monkeypatch, tmp_path, *, execstart: str | None = None) -> pathlib.Path:
    systemd_dir = tmp_path / "systemd-user"
    systemd_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(_mod, "_SYSTEMD_USER_DIR", systemd_dir)
    exec_line = execstart if execstart is not None else _mod._EXPECTED_EXECSTART
    (systemd_dir / _mod._SERVICE_UNIT).write_text(
        "[Service]\nType=oneshot\nExecStart=" + exec_line + "\n", encoding="utf-8"
    )
    return systemd_dir


def _silence_emit(monkeypatch):
    monkeypatch.setattr(_mod, "emit", lambda *a, **k: None)


# ---------------------------------------------------------------------------
# Static checks on the source systemd units.
# ---------------------------------------------------------------------------


def test_service_execstart_is_module_form_never_bare_python():
    text = _SERVICE_SRC.read_text(encoding="utf-8")
    exec_lines = [ln for ln in text.splitlines() if ln.strip().startswith("ExecStart=")]
    assert len(exec_lines) == 1
    execstart = exec_lines[0].split("=", 1)[1].strip()
    assert execstart == "/usr/bin/python3 -m scripts.openclaw.check_ecosystem_updates --once"
    assert " python " not in f" {execstart} "  # office2 is python3-only
    assert execstart.startswith("/usr/bin/python3 ")


def test_service_declares_onfailure_shim():
    text = _SERVICE_SRC.read_text(encoding="utf-8")
    assert "OnFailure=felix-openclaw-updates-onfailure.service" in text


def test_service_has_expected_environment_and_envfile():
    text = _SERVICE_SRC.read_text(encoding="utf-8")
    assert "Environment=HOME=/home/claude" in text
    assert "Environment=PYTHONPATH=/home/claude/kg-automation" in text
    assert "WorkingDirectory=/home/claude/kg-automation" in text
    assert "EnvironmentFile=-/home/claude/.config/felix/alert-bus/env" in text
    assert "Type=oneshot" in text


def test_timer_is_weekly_with_persistent_and_install():
    text = _TIMER_SRC.read_text(encoding="utf-8")
    assert "OnCalendar=Mon *-*-* 07:00:00 America/New_York" in text
    assert "Persistent=true" in text
    assert "WantedBy=timers.target" in text


def test_onfailure_unit_emits_error_via_bus_shim():
    text = _ONFAILURE_SRC.read_text(encoding="utf-8")
    assert "Type=oneshot" in text
    assert "scripts/common/alert_bus.sh emit" in text
    assert "--severity error" in text
    assert "--source felix-openclaw-updates/onfailure" in text
    assert "EnvironmentFile=-/home/claude/.config/felix/alert-bus/env" in text


def test_expected_execstart_matches_source_service():
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
    run = _RunRecorder()
    monkeypatch.setattr(_mod, "_run", run)
    emitted = {"called": False}
    monkeypatch.setattr(_mod, "emit", lambda *a, **k: emitted.__setitem__("called", True))
    assert _mod.main(["--dry-run"]) == 0
    assert run.calls == []
    assert not emitted["called"]


# ---------------------------------------------------------------------------
# #703 byte-identical ExecStart guard.
# ---------------------------------------------------------------------------


def test_execstart_guard_fails_on_drift(monkeypatch, tmp_path):
    _install_fake_units(monkeypatch, tmp_path, execstart="/usr/bin/python3 -m scripts.evil --once")
    _silence_emit(monkeypatch)
    run = _RunRecorder()
    monkeypatch.setattr(_mod, "_run", run)
    assert _mod.main(["--apply"]) == 1
    # never reached enable --now
    assert not any("enable" in " ".join(c) for c in run.calls)


# ---------------------------------------------------------------------------
# Gate: self-check must be ok, real unit must pass, before enable.
# ---------------------------------------------------------------------------


def test_self_check_failure_blocks_enable(monkeypatch, tmp_path):
    _install_fake_units(monkeypatch, tmp_path)
    _silence_emit(monkeypatch)
    run = _RunRecorder({"--self-check": (1, "status=fail npm not on PATH", "")})
    monkeypatch.setattr(_mod, "_run", run)
    assert _mod.main(["--apply"]) == 1
    assert not any("enable" in " ".join(c) for c in run.calls)


def test_real_unit_nonzero_blocks_enable(monkeypatch, tmp_path):
    _install_fake_units(monkeypatch, tmp_path)
    _silence_emit(monkeypatch)
    tick = tmp_path / "state" / "last-tick.json"
    monkeypatch.setattr(_mod, "_TICK_PATH", tick)
    run = _RunRecorder(
        {
            "--self-check": (0, "status=ok", ""),
            "start felix-openclaw-updates.service": (1, "", "unit failed"),
        },
        tick_path=tick,
    )
    monkeypatch.setattr(_mod, "_run", run)
    assert _mod.main(["--apply"]) == 1
    assert not any("enable" in " ".join(c) for c in run.calls)


def test_real_unit_no_tick_blocks_enable(monkeypatch, tmp_path):
    """rc=0 but no fresh tick (deployed command didn't write state) blocks enable."""
    _install_fake_units(monkeypatch, tmp_path)
    _silence_emit(monkeypatch)
    monkeypatch.setattr(_mod, "_TICK_PATH", tmp_path / "state" / "last-tick.json")
    # recorder with NO tick_path -> start succeeds but writes no tick
    run = _RunRecorder({"--self-check": (0, "status=ok", "")})
    monkeypatch.setattr(_mod, "_run", run)
    assert _mod.main(["--apply"]) == 1
    assert not any("enable" in " ".join(c) for c in run.calls)


def test_happy_path_enables_only_after_clean_gate(monkeypatch, tmp_path):
    _install_fake_units(monkeypatch, tmp_path)
    _silence_emit(monkeypatch)
    tick = tmp_path / "state" / "last-tick.json"
    monkeypatch.setattr(_mod, "_TICK_PATH", tick)
    run = _RunRecorder({"--self-check": (0, "status=ok", "")}, tick_path=tick)
    monkeypatch.setattr(_mod, "_run", run)
    assert _mod.main(["--apply"]) == 0

    joined = [" ".join(c) for c in run.calls]
    reload_idx = next(i for i, c in enumerate(joined) if "daemon-reload" in c)
    start_idx = next(i for i, c in enumerate(joined) if "start felix-openclaw-updates.service" in c)
    enable_idx = next(i for i, c in enumerate(joined) if "enable" in c and "--now" in c)
    # daemon-reload before running the real unit, and enable strictly last.
    assert reload_idx < start_idx < enable_idx


# ---------------------------------------------------------------------------
# Manifest schema validity.
# ---------------------------------------------------------------------------


def test_manifest_is_schema_valid():
    result = validate_manifest_file(_resolve_manifest_path())
    assert result.ok, result.summary


def test_manifest_is_tier3_audited_and_points_at_entrypoint():
    import yaml

    data = yaml.safe_load(_resolve_manifest_path().read_text(encoding="utf-8"))
    assert data["tier"] == 3
    assert data["audited_surface"] is True
    assert data["entrypoint"] == "scripts/deploy/deploy-openclaw-update-check.py"
    assert data["issue"] == "kentonium3/kg-automation#628"
