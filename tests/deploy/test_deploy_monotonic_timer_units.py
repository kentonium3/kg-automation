"""Tests for the #1062 timer deploy entrypoint.

No test touches systemd: the runner and sleep are injected.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[2] / "scripts" / "deploy" / "deploy-monotonic-timer-units.py"
_spec = importlib.util.spec_from_file_location("deploy_monotonic_timer_units", _PATH)
mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = mod
_spec.loader.exec_module(mod)


def _show(**overrides: str) -> str:
    props = {
        "Persistent": "no",
        "UnitFileState": "enabled",
        "ActiveState": "active",
        "SubState": "waiting",
        "FragmentPath": str(mod.UNIT_DIR / "felix-canary.timer"),
        "DropInPaths": "",
        "NextElapseUSecMonotonic": "1h 21.06s",
    }
    props.update(overrides)
    return "\n".join(f"{k}={v}" for k, v in props.items())


def _UNIT(path: Path) -> str:
    return "[Timer]\nOnBootSec=5min\nOnUnitActiveSec=15min\n"


class FakeRun:
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = outputs
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str]) -> tuple[int, str, str]:
        self.calls.append(argv)
        out = self.outputs.pop(0) if len(self.outputs) > 1 else self.outputs[0]
        return 0, out, ""


def test_the_six_repo_sources_are_valid() -> None:
    assert len(mod.TIMERS) == 6
    for src in mod.TIMERS:
        assert mod.source_problems(src.read_text(encoding="utf-8")) == [], src.name


def test_source_with_persistent_is_rejected_before_copy() -> None:
    bad = "[Timer]\nOnBootSec=5min\nOnUnitActiveSec=15min\nPersistent=true\n"
    assert any("#1062" in p for p in mod.source_problems(bad))
    assert mod.source_problems("[Unit]\nDescription=x\n")  # no [Timer]


@pytest.mark.parametrize("value, ok", [
    ("1h 21.06s", True), ("54min 36.9s", True),
    ("infinity", False), ("0", False), ("", False),
])
def test_next_elapse_is_concrete(value: str, ok: bool) -> None:
    assert mod.next_elapse_is_concrete(value) is ok


def test_loaded_config_checks() -> None:
    good = mod.parse_show(_show())
    assert mod.loaded_problems("felix-canary.timer", good, []) == []
    still = mod.parse_show(_show(Persistent="yes"))
    assert mod.loaded_problems("felix-canary.timer", still, [])
    disabled = mod.parse_show(_show(UnitFileState="disabled"))
    assert mod.loaded_problems("felix-canary.timer", disabled, [])
    elsewhere = mod.parse_show(_show(FragmentPath="/etc/systemd/user/felix-canary.timer"))
    assert mod.loaded_problems("felix-canary.timer", elsewhere, [])
    unit = "[Timer]\nOnBootSec=5min\nOnUnitActiveSec=15min\n"
    assert mod.loaded_problems("felix-canary.timer", good, [unit]) == []
    assert mod.loaded_problems("felix-canary.timer", good, [unit, "[Timer]\nPersistent=true\n"])


def test_slow_service_is_waited_for_not_failed() -> None:
    # Right after restart the service is running and next elapse is infinity
    # (timer_enter_running). That is a good deploy in progress, not a failure.
    run = FakeRun([
        _show(SubState="running", NextElapseUSecMonotonic="infinity"),
        _show(SubState="running", NextElapseUSecMonotonic="infinity"),
        _show(),
    ])
    sleeps: list[float] = []
    assert mod._verify_timer("felix-canary.timer", run, sleeps.append, read=_UNIT) == []
    assert len(sleeps) == 2


def test_never_rearming_timer_fails_after_timeout() -> None:
    # The #1062 symptom: active (elapsed), next elapse infinity, forever.
    run = FakeRun([_show(SubState="elapsed", NextElapseUSecMonotonic="infinity")])
    problems = mod._verify_timer("felix-canary.timer", run, lambda s: None, timeout_s=0, read=_UNIT)
    assert problems and "no concrete next elapse" in problems[0]


def test_loaded_persistent_fails_immediately_without_polling() -> None:
    run = FakeRun([_show(Persistent="yes")])
    sleeps: list[float] = []
    assert mod._verify_timer("felix-canary.timer", run, sleeps.append, read=_UNIT)
    assert sleeps == []


def test_installed_fragment_with_persistent_fails() -> None:
    run = FakeRun([_show()])  # loaded Persistent=no, but the file says otherwise
    bad = lambda p: "[Timer]\nOnBootSec=5min\nPersistent=true\n"
    assert mod._verify_timer("felix-canary.timer", run, lambda s: None, read=bad)
