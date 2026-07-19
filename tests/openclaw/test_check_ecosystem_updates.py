"""Tests for the OpenClaw ecosystem update-availability check (#628).

No test touches npm or the network — every npm call goes through an injected
fake runner, and the alert bus is exercised via an injected emitter that just
captures the ``Alert`` objects.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.openclaw import check_ecosystem_updates as ceu

_FIXED_NOW = lambda: datetime(2026, 7, 19, 12, 0, 0, tzinfo=timezone.utc)  # noqa: E731


def _tick(tmp_path: Path) -> Path:
    return tmp_path / "state" / "last-tick.json"


# --------------------------------------------------------------------------- #
# Fake runner helpers.
# --------------------------------------------------------------------------- #


def _completed(argv, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(argv, returncode, stdout=stdout, stderr=stderr)


def make_runner(handlers):
    """Build a Runner that dispatches on a key derived from argv.

    ``handlers`` maps a key -> CompletedProcess (or a callable argv->CP). Keys:
    ``"outdated"`` for ``npm outdated``; ``"view:<pkg>"`` for ``npm view <pkg>``.
    """

    def runner(argv):
        if argv[:2] == ["npm", "outdated"]:
            h = handlers["outdated"]
        elif argv[:2] == ["npm", "view"]:
            h = handlers[f"view:{argv[2]}"]
        else:  # pragma: no cover - defensive
            raise AssertionError(f"unexpected argv: {argv}")
        return h(argv) if callable(h) else h

    return runner


class CapturingEmitter:
    def __init__(self):
        self.alerts = []

    def __call__(self, alert):
        self.alerts.append(alert)
        return object()


def _write_plugin(projects_dir: Path, project_slug: str, name: str, version: str):
    pkg_dir = projects_dir / project_slug / "node_modules" / name
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "package.json").write_text(json.dumps({"name": name, "version": version}), encoding="utf-8")


# --------------------------------------------------------------------------- #
# check_core
# --------------------------------------------------------------------------- #


def test_check_core_current_empty_output():
    runner = make_runner({"outdated": _completed([], 0, stdout="")})
    update, error = ceu.check_core(runner)
    assert update is None and error is None


def test_check_core_current_not_in_map():
    runner = make_runner({"outdated": _completed([], 0, stdout="{}")})
    update, error = ceu.check_core(runner)
    assert update is None and error is None


def test_check_core_update_available():
    payload = json.dumps({"openclaw": {"current": "2026.6.11", "latest": "2026.7.1-2"}})
    # npm outdated exits 1 when something IS outdated — must NOT be treated as error.
    runner = make_runner({"outdated": _completed([], 1, stdout=payload)})
    update, error = ceu.check_core(runner)
    assert error is None
    assert update == ceu.ComponentUpdate("openclaw", "core", "2026.6.11", "2026.7.1-2")


def test_check_core_subprocess_failure_is_error():
    def boom(argv):
        raise OSError("npm exploded")

    runner = make_runner({"outdated": boom})
    update, error = ceu.check_core(runner)
    assert update is None
    assert error is not None and error.kind == "core"


def test_check_core_unparseable_output_is_error():
    runner = make_runner({"outdated": _completed([], 0, stdout="not json <<")})
    update, error = ceu.check_core(runner)
    assert update is None
    assert error is not None and "unparseable" in error.error


# --------------------------------------------------------------------------- #
# discover_plugins
# --------------------------------------------------------------------------- #


def _installs_as_set(installs):
    return {(i.name, i.version, i.project) for i in installs}


def test_discover_plugins_reads_versions(tmp_path):
    _write_plugin(tmp_path, "wa-proj", "@openclaw/whatsapp", "2026.6.11")
    _write_plugin(tmp_path, "sig-proj", "@openclaw/signal", "2026.5.1")
    assert _installs_as_set(ceu.discover_plugins(tmp_path)) == {
        ("@openclaw/whatsapp", "2026.6.11", "wa-proj"),
        ("@openclaw/signal", "2026.5.1", "sig-proj"),
    }


def test_discover_plugins_lists_every_install_site_no_dedup(tmp_path):
    # Same plugin in two project trees at DIFFERENT versions -> both surface
    # (no dedup that could mask per-tree drift).
    _write_plugin(tmp_path, "a", "@openclaw/whatsapp", "2026.6.11")
    _write_plugin(tmp_path, "b", "@openclaw/whatsapp", "2026.7.1")
    assert _installs_as_set(ceu.discover_plugins(tmp_path)) == {
        ("@openclaw/whatsapp", "2026.6.11", "a"),
        ("@openclaw/whatsapp", "2026.7.1", "b"),
    }


def test_discover_plugins_skips_malformed_and_non_openclaw(tmp_path):
    _write_plugin(tmp_path, "ok", "@openclaw/whatsapp", "1.0.0")
    # non-@openclaw scope is ignored
    _write_plugin(tmp_path, "other", "@vendor/thing", "9.9.9")
    # malformed package.json is skipped
    bad = tmp_path / "bad" / "node_modules" / "@openclaw" / "broken"
    bad.mkdir(parents=True)
    (bad / "package.json").write_text("{ not json", encoding="utf-8")
    assert _installs_as_set(ceu.discover_plugins(tmp_path)) == {
        ("@openclaw/whatsapp", "1.0.0", "ok"),
    }


def test_discover_plugins_empty_dir(tmp_path):
    assert ceu.discover_plugins(tmp_path) == []


# --------------------------------------------------------------------------- #
# npm_latest / check_plugins
# --------------------------------------------------------------------------- #


def test_npm_latest_success():
    runner = make_runner({"view:@openclaw/whatsapp": _completed([], 0, stdout="2026.7.1\n")})
    assert ceu.npm_latest(runner, "@openclaw/whatsapp") == "2026.7.1"


def test_npm_latest_nonzero_raises():
    runner = make_runner({"view:@openclaw/x": _completed([], 1, stderr="E404")})
    with pytest.raises(RuntimeError):
        ceu.npm_latest(runner, "@openclaw/x")


def test_npm_latest_empty_raises():
    runner = make_runner({"view:@openclaw/x": _completed([], 0, stdout="  \n")})
    with pytest.raises(RuntimeError):
        ceu.npm_latest(runner, "@openclaw/x")


def test_check_plugins_flags_only_outdated(tmp_path):
    _write_plugin(tmp_path, "wa", "@openclaw/whatsapp", "2026.6.11")
    _write_plugin(tmp_path, "sig", "@openclaw/signal", "2026.7.1")
    runner = make_runner(
        {
            "view:@openclaw/whatsapp": _completed([], 0, stdout="2026.7.1"),
            "view:@openclaw/signal": _completed([], 0, stdout="2026.7.1"),
        }
    )
    updates, errors, checked = ceu.check_plugins(runner, tmp_path)
    assert errors == []
    assert updates == [ceu.ComponentUpdate("@openclaw/whatsapp", "plugin", "2026.6.11", "2026.7.1")]
    assert checked == 2


def test_check_plugins_records_error_and_continues(tmp_path):
    _write_plugin(tmp_path, "wa", "@openclaw/whatsapp", "2026.6.11")
    _write_plugin(tmp_path, "sig", "@openclaw/signal", "2026.5.0")
    runner = make_runner(
        {
            "view:@openclaw/whatsapp": _completed([], 1, stderr="registry down"),
            "view:@openclaw/signal": _completed([], 0, stdout="2026.7.1"),
        }
    )
    updates, errors, checked = ceu.check_plugins(runner, tmp_path)
    assert [u.name for u in updates] == ["@openclaw/signal"]
    assert [e.name for e in errors] == ["@openclaw/whatsapp"]
    assert checked == 2


def test_check_plugins_stale_copy_in_one_tree_not_masked(tmp_path):
    # reviewer Finding 1: whatsapp current in projA (== latest) but STALE in
    # projB must still be flagged — the stale copy must not be masked.
    _write_plugin(tmp_path, "projA", "@openclaw/whatsapp", "2.0.0")
    _write_plugin(tmp_path, "projB", "@openclaw/whatsapp", "1.5.0")
    runner = make_runner({"view:@openclaw/whatsapp": _completed([], 0, stdout="2.0.0")})
    updates, errors, checked = ceu.check_plugins(runner, tmp_path)
    assert errors == []
    assert checked == 2
    assert updates == [ceu.ComponentUpdate("@openclaw/whatsapp", "plugin", "1.5.0", "2.0.0")]


def test_check_plugins_same_stale_version_in_two_trees_collapses(tmp_path):
    _write_plugin(tmp_path, "projA", "@openclaw/whatsapp", "1.5.0")
    _write_plugin(tmp_path, "projB", "@openclaw/whatsapp", "1.5.0")
    runner = make_runner({"view:@openclaw/whatsapp": _completed([], 0, stdout="2.0.0")})
    updates, errors, checked = ceu.check_plugins(runner, tmp_path)
    assert checked == 2  # both sites enumerated
    # same stale version in two trees collapses to one digest line
    assert updates == [ceu.ComponentUpdate("@openclaw/whatsapp", "plugin", "1.5.0", "2.0.0")]


# --------------------------------------------------------------------------- #
# run_pass
# --------------------------------------------------------------------------- #


def _all_current_runner(tmp_path):
    return make_runner(
        {
            "outdated": _completed([], 0, stdout=""),
            "view:@openclaw/whatsapp": _completed([], 0, stdout="2026.6.11"),
        }
    )


def test_run_pass_silent_no_op_when_current(tmp_path, capsys):
    _write_plugin(tmp_path, "wa", "@openclaw/whatsapp", "2026.6.11")
    emitter = CapturingEmitter()
    result = ceu.run_pass(
        runner=_all_current_runner(tmp_path), projects_dir=tmp_path, emitter=emitter,
        tick_path=_tick(tmp_path), now=_FIXED_NOW,
    )
    assert not result.has_findings
    assert emitter.alerts == []  # silent no-op — nothing paged
    assert "silent no-op" in capsys.readouterr().out


def test_run_pass_writes_tick_on_completed_pass(tmp_path):
    _write_plugin(tmp_path, "wa", "@openclaw/whatsapp", "2026.6.11")
    tick = _tick(tmp_path)
    ceu.run_pass(
        runner=_all_current_runner(tmp_path), projects_dir=tmp_path, emitter=CapturingEmitter(),
        tick_path=tick, now=_FIXED_NOW,
    )
    data = json.loads(tick.read_text())
    assert data["status"] == "success"
    assert data["completed_at_utc"] == "2026-07-19T12:00:00Z"
    assert data["updates_available"] == 0


def test_run_pass_emits_digest_on_updates(tmp_path):
    _write_plugin(tmp_path, "wa", "@openclaw/whatsapp", "2026.6.11")
    runner = make_runner(
        {
            "outdated": _completed([], 1, stdout=json.dumps({"openclaw": {"current": "2026.6.11", "latest": "2026.7.1-2"}})),
            "view:@openclaw/whatsapp": _completed([], 0, stdout="2026.7.1"),
        }
    )
    emitter = CapturingEmitter()
    result = ceu.run_pass(
        runner=runner, projects_dir=tmp_path, emitter=emitter,
        tick_path=_tick(tmp_path), now=_FIXED_NOW,
    )
    assert len(result.updates) == 2  # core + whatsapp
    assert len(emitter.alerts) == 1
    alert = emitter.alerts[0]
    assert "update" in alert.title.lower()
    assert "@openclaw/whatsapp" in alert.description
    assert "openclaw" in alert.description
    assert ".md" in alert.action
    assert "tier-0" not in alert.action.lower()  # OpenClaw apply is Tier-2, not Tier-0
    # a tick with the finding counts is still recorded
    assert json.loads(_tick(tmp_path).read_text())["updates_available"] == 2


def test_run_pass_emits_on_errors_only(tmp_path):
    _write_plugin(tmp_path, "wa", "@openclaw/whatsapp", "2026.6.11")
    runner = make_runner(
        {
            "outdated": _completed([], 0, stdout=""),  # core current
            "view:@openclaw/whatsapp": _completed([], 1, stderr="registry down"),
        }
    )
    emitter = CapturingEmitter()
    result = ceu.run_pass(
        runner=runner, projects_dir=tmp_path, emitter=emitter,
        tick_path=_tick(tmp_path), now=_FIXED_NOW,
    )
    assert result.updates == []
    assert len(result.errors) == 1
    assert len(emitter.alerts) == 1  # errors still page — a check we couldn't complete


def test_run_pass_dry_run_does_not_emit_or_tick(tmp_path, capsys):
    _write_plugin(tmp_path, "wa", "@openclaw/whatsapp", "2026.6.11")
    runner = make_runner(
        {
            "outdated": _completed([], 1, stdout=json.dumps({"openclaw": {"current": "2026.6.11", "latest": "2026.7.1-2"}})),
            "view:@openclaw/whatsapp": _completed([], 0, stdout="2026.6.11"),
        }
    )
    emitter = CapturingEmitter()
    tick = _tick(tmp_path)
    result = ceu.run_pass(
        runner=runner, projects_dir=tmp_path, emitter=emitter, tick_path=tick, now=_FIXED_NOW, dry_run=True,
    )
    assert result.has_findings
    assert emitter.alerts == []  # dry-run never emits
    assert not tick.exists()  # dry-run has no side effects
    assert "[dry-run]" in capsys.readouterr().out


def test_run_pass_runner_fault_no_projects_dir(tmp_path):
    missing = tmp_path / "nope"
    with pytest.raises(RuntimeError):
        ceu.run_pass(runner=make_runner({}), projects_dir=missing, emitter=CapturingEmitter(), tick_path=_tick(tmp_path))


def test_run_pass_runner_fault_no_npm(tmp_path, monkeypatch):
    _write_plugin(tmp_path, "wa", "@openclaw/whatsapp", "1.0.0")
    monkeypatch.setattr(ceu.shutil, "which", lambda _: None)
    with pytest.raises(RuntimeError, match="npm not found"):
        ceu.run_pass(runner=make_runner({}), projects_dir=tmp_path, emitter=CapturingEmitter(), tick_path=_tick(tmp_path))


def test_run_pass_runner_fault_unwritable_tick(tmp_path):
    _write_plugin(tmp_path, "wa", "@openclaw/whatsapp", "2026.6.11")
    # point the tick at a path whose parent is a FILE -> mkdir fails -> runner fault
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    bad_tick = blocker / "state" / "last-tick.json"
    with pytest.raises(RuntimeError, match="tick-signal"):
        ceu.run_pass(
            runner=_all_current_runner(tmp_path), projects_dir=tmp_path,
            emitter=CapturingEmitter(), tick_path=bad_tick, now=_FIXED_NOW,
        )


# --------------------------------------------------------------------------- #
# CLI / main
# --------------------------------------------------------------------------- #


def test_main_self_check_ok(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(ceu, "_DEFAULT_PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(ceu, "_TICK_PATH", _tick(tmp_path))
    monkeypatch.setattr(ceu.shutil, "which", lambda _: "/usr/bin/npm")
    assert ceu.main(["--self-check"]) == 0
    assert "status=ok" in capsys.readouterr().out


def test_main_self_check_fail_no_npm(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(ceu, "_DEFAULT_PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(ceu, "_TICK_PATH", _tick(tmp_path))
    monkeypatch.setattr(ceu.shutil, "which", lambda _: None)
    assert ceu.main(["--self-check"]) == 1
    assert "status=fail" in capsys.readouterr().out


def test_main_runner_fault_returns_1(monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("npm not found on PATH")

    monkeypatch.setattr(ceu, "run_pass", boom)
    assert ceu.main(["--once"]) == 1


def test_main_ok_returns_0(monkeypatch):
    monkeypatch.setattr(ceu, "run_pass", lambda **kwargs: ceu.CheckResult())
    assert ceu.main(["--once"]) == 0
