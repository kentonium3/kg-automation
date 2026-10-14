"""Characterization of the #1062 entrypoint's ``_apply`` orchestration (#1066).

Written against the pre-extraction code and kept green through the move to
``scripts.deploy.lib.userunits``. It pins behavior only through the
entrypoint's ``_apply(run=, sleep=)`` seam and process-wide facts (``pwd``,
``Path.home``, the monotonic clock), never through private helpers, so it
survives the refactor. What it pins (debugger-debbie, #1066 post-plan):

* step order: validate every source, copy all, one daemon-reload, restart all,
  verify all, re-diff;
* refuse-before-copy: one invalid source means nothing is copied or run;
* a failed restart does not stop the others, and fails the run at the end;
* ONE shared next-elapse deadline across all timers (about 300 s total, not
  300 s per timer);
* the final convergence re-diff fails a deployed copy that differs.
"""
from __future__ import annotations

import importlib.util
import pathlib
import pwd
import sys
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[2] / "scripts" / "deploy" / "deploy-monotonic-timer-units.py"
_spec = importlib.util.spec_from_file_location("deploy_monotonic_timer_units_apply", _PATH)
mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = mod
_spec.loader.exec_module(mod)

NAMES = [p.name for p in mod.TIMERS]


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0
        self.slept = 0.0

    def monotonic(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds
        self.slept += seconds


class FakeSystemd:
    """Records argv; answers ``show`` with healthy props unless told otherwise."""

    def __init__(self, unit_dir: Path, *, never_rearm: bool = False, fail_restart: str | None = None):
        self.unit_dir = unit_dir
        self.never_rearm = never_rearm
        self.fail_restart = fail_restart
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str]) -> tuple[int, str, str]:
        self.calls.append(list(argv))
        if argv[2] == "restart" and argv[3] == self.fail_restart:
            return 1, "", "boom"
        if argv[2] == "show":
            name = argv[3]
            nxt = "infinity" if self.never_rearm else "14min 3s"
            sub = "running" if self.never_rearm else "waiting"
            return 0, "\n".join([
                "Persistent=no", "UnitFileState=enabled", "ActiveState=active", f"SubState={sub}",
                f"FragmentPath={self.unit_dir / name}", "DropInPaths=", f"NextElapseUSecMonotonic={nxt}",
            ]), ""
        return 0, "", ""

    def verbs(self) -> list[tuple[str, str]]:
        return [(c[2], c[3] if len(c) > 3 else "") for c in self.calls]


@pytest.fixture
def office2(tmp_path, monkeypatch):
    unit_dir = tmp_path / "systemd-user"
    monkeypatch.setattr(mod, "UNIT_DIR", unit_dir)
    monkeypatch.setattr(pwd, "getpwuid", lambda _uid: type("P", (), {"pw_name": "claude"})())
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: Path("/home/claude")))
    clock = Clock()
    monkeypatch.setattr(mod.time, "monotonic", clock.monotonic)
    return unit_dir, clock


def test_happy_path_order_and_convergence(office2):
    unit_dir, clock = office2
    sd = FakeSystemd(unit_dir)
    assert mod._apply(run=sd, sleep=clock.sleep) == 0
    verbs = sd.verbs()
    assert verbs[0] == ("daemon-reload", "")
    assert [v for v in verbs if v[0] == "restart"] == [("restart", n) for n in NAMES]
    first_show = next(i for i, v in enumerate(verbs) if v[0] == "show")
    assert all(v[0] != "restart" for v in verbs[first_show:]), "every restart precedes every verify"
    assert {v[1] for v in verbs if v[0] == "show"} == set(NAMES)
    for src in mod.TIMERS:
        assert (unit_dir / src.name).read_bytes() == src.read_bytes()


def test_invalid_source_refuses_before_copying_anything(office2, tmp_path, monkeypatch):
    unit_dir, clock = office2
    bad = tmp_path / "bad.timer"
    bad.write_text("[Timer]\nOnBootSec=5min\nOnUnitActiveSec=15min\nPersistent=true\n")
    monkeypatch.setattr(mod, "TIMERS", (*mod.TIMERS, bad))
    sd = FakeSystemd(unit_dir)
    assert mod._apply(run=sd, sleep=clock.sleep) == 1
    assert sd.calls == []
    assert not unit_dir.exists() or not any(unit_dir.iterdir())


def test_wrong_user_runs_nothing(office2, monkeypatch):
    unit_dir, clock = office2
    monkeypatch.setattr(pwd, "getpwuid", lambda _uid: type("P", (), {"pw_name": "kgale"})())
    sd = FakeSystemd(unit_dir)
    assert mod._apply(run=sd, sleep=clock.sleep) == 1
    assert sd.calls == []


def test_failed_restart_continues_and_fails_at_end(office2):
    unit_dir, clock = office2
    sd = FakeSystemd(unit_dir, fail_restart=NAMES[1])
    assert mod._apply(run=sd, sleep=clock.sleep) == 1
    assert [v for v in sd.verbs() if v[0] == "restart"] == [("restart", n) for n in NAMES]
    shown = {v[1] for v in sd.verbs() if v[0] == "show"}
    assert NAMES[1] not in shown and shown == set(NAMES) - {NAMES[1]}


def test_one_shared_deadline_across_all_timers(office2):
    """A deploy whose timers never rearm holds the deployer ~300 s in total,
    not 300 s per timer (6 x 300 = 1800 s)."""
    unit_dir, clock = office2
    sd = FakeSystemd(unit_dir, never_rearm=True)
    assert mod._apply(run=sd, sleep=clock.sleep) == 1
    assert clock.slept <= mod.NEXT_ELAPSE_TIMEOUT_S + 60
    assert clock.slept >= mod.NEXT_ELAPSE_TIMEOUT_S


def test_deployed_copy_that_differs_fails_convergence(office2):
    """Something rewrites a deployed unit after the copy (simulated during
    daemon-reload, independent of HOW the entrypoint copies): the final
    convergence re-diff must fail the run."""
    unit_dir, clock = office2
    sd = FakeSystemd(unit_dir)
    real_call = sd.__call__

    def drifting(argv):
        if argv[2] == "daemon-reload":
            target = unit_dir / NAMES[0]
            target.write_text(target.read_text() + "\n# drift\n")
        return real_call(argv)

    assert mod._apply(run=drifting, sleep=clock.sleep) == 1


def test_dry_run_plans_and_writes_nothing(office2, capsys):
    unit_dir, _clock = office2
    assert mod._dry_run() == 0
    out = capsys.readouterr().out
    assert out.count('"event": "would_copy"') == len(NAMES)
    assert '"currently_differs": true' in out
    assert not unit_dir.exists()
