"""Tests for the #1133 deploy entrypoint and its manifest.

Offline: the runner, clock, file reader, scope reader, config loader and the
user/home lookups are all injected. Nothing here touches systemd, office2, or
any path outside tmp.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from scripts.canary.crash_loop_model import (
    CrashLoopConfig,
    CrashLoopConfigError,
    RestartObservation,
    ScopeReading,
)

_ROOT = Path(__file__).resolve().parents[2]
_PATH = _ROOT / "scripts" / "deploy" / "deploy-crash-loop-unit-alerting.py"
_spec = importlib.util.spec_from_file_location("deploy_crash_loop_unit_alerting", _PATH)
assert _spec is not None and _spec.loader is not None
mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = mod
_spec.loader.exec_module(mod)

SCHEMA_PATH = _ROOT / "deploys" / "schema" / "manifest-v1.schema.json"
NAME = "crash-loop-unit-alerting"

T0 = datetime(2026, 11, 24, 15, 0, 0, tzinfo=UTC)
FRESH = T0 + timedelta(seconds=1)
STALE = T0 - timedelta(seconds=40)
SCOPES = ("system", "user", "container")

CONFIG = CrashLoopConfig(
    threshold=3,
    window_seconds=900,
    quiet_ticks_to_clear=2,
    max_alerts_per_tick=3,
    read_budget_seconds=6,
    ignore=frozenset({"user:noisy.service"}),
    ignore_reasons={"user:noisy.service": "test"},
)


# --------------------------------------------------------------------------- #
# Artifact builders.
# --------------------------------------------------------------------------- #
def _state(at: datetime = FRESH) -> str:
    return json.dumps({"schema_version": 1, "updated_at_utc": at.isoformat(),
                       "boot_id": "b", "units": {}})


def _tick(at: datetime = FRESH, errors: list[str] | None = None) -> str:
    return json.dumps({"status": "success" if not errors else "error",
                       "completed_at_utc": at.isoformat(), "errors": errors or []})


def _line(component_id: str, outcome: str, at: datetime = FRESH, **extra: object) -> dict:
    rec = {"component_id": component_id, "outcome": outcome, "evidence": "e",
           "emitted": False, "suppressed_dedup": False, "evaluated_at": at.isoformat()}
    rec.update(extra)
    return rec


def _scope_lines(at: datetime = FRESH, **outcomes: str) -> list[dict]:
    return [_line(f"crash-loop:{s}", outcomes.get(s, "healthy"), at) for s in SCOPES]


def _ledger(lines: list[dict]) -> str:
    return "".join(json.dumps(r) + "\n" for r in lines)


class Pass:
    """The artifacts one canary pass leaves behind."""

    def __init__(self, *, state: str | None = None, tick: str | None = None,
                 lines: list[dict] | None = None):
        self.state = _state() if state is None else state
        self.tick = _tick() if tick is None else tick
        self.lines = _scope_lines() if lines is None else lines


def _stale_pass() -> Pass:
    return Pass(state=_state(STALE), tick=_tick(STALE), lines=_scope_lines(STALE))


class Harness:
    """Each systemctl start advances to the next scripted Pass."""

    def __init__(self, *passes: Pass, start_rc: int = 0):
        self.passes = list(passes)
        self.start_rc = start_rc
        self.runs: list[list[str]] = []
        self.timeouts: list[float] = []
        self.current: Pass | None = None

    def run(self, argv: list[str], timeout: float) -> tuple[int, str, str]:
        self.runs.append(argv)
        self.timeouts.append(timeout)
        if self.start_rc == 0 and self.passes:
            self.current = self.passes.pop(0)
        return self.start_rc, "", "boom" if self.start_rc else ""

    def read_text(self, path: Path) -> str:
        assert self.current is not None, "artifact read before any start"
        if path == mod.STATE_PATH:
            return self.current.state
        if path == mod.TICK_PATH:
            return self.current.tick
        if path.parent == mod.LEDGER_DIR:
            if path.name == f"{T0:%Y-%m-%d}.jsonl":
                return _ledger(self.current.lines)
            raise FileNotFoundError(path)
        raise AssertionError(f"unexpected read {path}")

    def apply(self) -> int:
        return mod.apply(run=self.run, now=lambda: T0, read_text=self.read_text,
                         preflight=lambda: True)


# --------------------------------------------------------------------------- #
# Preflight.
# --------------------------------------------------------------------------- #
def test_preflight_accepts_claude_at_home():
    assert mod.preflight(user_name=lambda: "claude", home=lambda: Path("/home/claude"),
                         load_config=lambda: CONFIG) is True


def test_preflight_refuses_wrong_user(capsys):
    assert mod.preflight(user_name=lambda: "kgale", home=lambda: Path("/home/claude"),
                         load_config=lambda: CONFIG) is False
    assert "FAIL preflight-user" in capsys.readouterr().out


def test_preflight_refuses_wrong_home(capsys):
    assert mod.preflight(user_name=lambda: "claude", home=lambda: Path("/home/kgale"),
                         load_config=lambda: CONFIG) is False
    assert "FAIL preflight-user" in capsys.readouterr().out


def test_preflight_refuses_invalid_config(capsys):
    def bad() -> CrashLoopConfig:
        raise CrashLoopConfigError("threshold: must be 2..50, got 1")

    assert mod.preflight(user_name=lambda: "claude", home=lambda: Path("/home/claude"),
                         load_config=bad) is False
    assert "threshold" in capsys.readouterr().out


def test_wrong_user_starts_nothing():
    h = Harness(Pass())
    rc = mod.apply(run=h.run, now=lambda: T0, read_text=h.read_text, preflight=lambda: False)
    assert rc == 1
    assert h.runs == []


def test_the_shipped_config_loads():
    assert mod.crash_loop_model.load_config(mod.crash_loop_model.DEFAULT_CONFIG_PATH)


# --------------------------------------------------------------------------- #
# --dry-run.
# --------------------------------------------------------------------------- #
def _obs(scope: str, name: str) -> RestartObservation:
    return RestartObservation(scope=scope, name=name, restart_policy="always",
                              restart_count=0, state="active", generation="b")


def _readings(incomplete: str | None = None) -> list[ScopeReading]:
    out = []
    for s in SCOPES:
        if s == incomplete:
            out.append(ScopeReading.failed(s, "deadline exceeded", 6000))
        else:
            out.append(ScopeReading.ok(s, (_obs(s, "a.service"), _obs(s, "noisy.service")), 1, 12))
    return out


def test_dry_run_all_complete_exits_zero_and_reads_once(capsys):
    calls: list[float] = []

    def read_scopes(*, budget_seconds: float):
        calls.append(budget_seconds)
        return _readings(), "boot"

    rc = mod.dry_run(read_scopes=read_scopes, preflight=lambda: True,
                     load_config=lambda: CONFIG)
    assert rc == 0
    assert calls == [6]
    out = capsys.readouterr().out
    for s in SCOPES:
        assert f"PASS scope-{s}: complete=True watched=2" in out
    assert "ignored=1" in out  # user:noisy.service is in the ignore list
    assert "total_elapsed_ms=36" in out


@pytest.mark.parametrize("scope", SCOPES)
def test_dry_run_incomplete_scope_exits_one_naming_it(capsys, scope):
    rc = mod.dry_run(read_scopes=lambda *, budget_seconds: (_readings(scope), "boot"),
                     preflight=lambda: True, load_config=lambda: CONFIG)
    assert rc == 1
    out = capsys.readouterr().out
    assert f"FAIL scope-{scope}: complete=False" in out
    assert "deadline exceeded" in out


def test_dry_run_preflight_failure_reads_nothing():
    calls: list[float] = []

    def read_scopes(*, budget_seconds: float):
        calls.append(budget_seconds)
        return _readings(), "boot"

    assert mod.dry_run(read_scopes=read_scopes, preflight=lambda: False,
                       load_config=lambda: CONFIG) == 1
    assert calls == []


def test_dry_run_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    before = sorted(tmp_path.rglob("*"))
    mod.dry_run(read_scopes=lambda *, budget_seconds: (_readings(), "boot"),
                preflight=lambda: True, load_config=lambda: CONFIG)
    assert sorted(tmp_path.rglob("*")) == before
    # The dry run takes no file-writing hooks at all.
    assert "write" not in mod.dry_run.__code__.co_varnames


# --------------------------------------------------------------------------- #
# --apply.
# --------------------------------------------------------------------------- #
def test_apply_happy_path(capsys):
    h = Harness(Pass())
    assert h.apply() == 0
    assert h.runs == [["systemctl", "--user", "start", "felix-canary.service"]]
    assert h.timeouts == [120]
    out = capsys.readouterr().out
    for check in ("state-fresh", "scope-system", "scope-user", "scope-container",
                  "tick-fresh", "tick-errors", "events-delivered"):
        assert f"PASS {check}" in out
    assert "FAIL" not in out


def test_apply_delivered_alert_is_success():
    lines = _scope_lines() + [_line("crash-loop:system:obsidian-sync.service", "crash-loop",
                                    emitted=True, delivered=True, interval={})]
    assert Harness(Pass(lines=lines)).apply() == 0


def test_apply_unverified_rise_never_needs_delivery():
    lines = _scope_lines() + [_line("crash-loop:user:x.service", "crash-loop-unverified",
                                    delivered=False, interval={})]
    assert Harness(Pass(lines=lines)).apply() == 0


@pytest.mark.parametrize("scope", SCOPES)
def test_apply_fails_when_one_scope_is_unknown(capsys, scope):
    h = Harness(Pass(lines=_scope_lines(**{scope: "unknown"})))
    assert h.apply() == 1
    assert len(h.runs) == 1  # a non-freshness failure is never retried
    out = capsys.readouterr().out
    assert f"FAIL scope-{scope}" in out
    for other in set(SCOPES) - {scope}:
        assert f"PASS scope-{other}" in out


@pytest.mark.parametrize("scope", SCOPES)
def test_apply_fails_when_one_scope_line_is_missing(scope):
    lines = [r for r in _scope_lines() if r["component_id"] != f"crash-loop:{scope}"]
    h = Harness(Pass(lines=lines), Pass(lines=lines))
    assert h.apply() == 1


def test_apply_fails_on_stale_state_with_fresh_tick():
    h = Harness(Pass(state=_state(STALE)), Pass(state=_state(STALE)))
    assert h.apply() == 1
    assert len(h.runs) == 2


def test_apply_fails_on_crash_loop_tick_error(capsys):
    h = Harness(Pass(tick=_tick(errors=["crash_loop:locked"])))
    assert h.apply() == 1
    assert len(h.runs) == 1
    assert "FAIL tick-errors" in capsys.readouterr().out


def test_apply_fails_on_state_save_error():
    tick = _tick(errors=["crash_loop_state_save:OSError:disk full"])
    assert Harness(Pass(tick=tick)).apply() == 1


def test_apply_ignores_unrelated_tick_errors():
    assert Harness(Pass(tick=_tick(errors=["ledger:x:OSError:boom"]))).apply() == 0


def test_apply_fails_on_undelivered_event(capsys):
    lines = _scope_lines() + [_line("crash-loop:system:a.service", "crash-loop",
                                    emitted=True, delivered=False, interval={})]
    h = Harness(Pass(lines=lines))
    assert h.apply() == 1
    assert len(h.runs) == 1
    assert "FAIL events-delivered" in capsys.readouterr().out


def test_apply_ignores_an_undelivered_event_from_before_t0():
    lines = _scope_lines() + [_line("crash-loop:system:a.service", "crash-loop-reremind",
                                    STALE, delivered=False, interval={})]
    assert Harness(Pass(lines=lines)).apply() == 0


def test_apply_fails_on_nonzero_systemctl(capsys):
    h = Harness(Pass(), start_rc=1)
    assert h.apply() == 1
    assert len(h.runs) == 1
    assert "FAIL start" in capsys.readouterr().out


def test_apply_fails_on_unreadable_state():
    assert Harness(Pass(state="{not json")).apply() == 1


def test_apply_fails_when_a_fresh_line_is_healthy_but_another_fresh_line_is_unknown():
    lines = _scope_lines() + [_line("crash-loop:user", "unknown", FRESH + timedelta(seconds=60))]
    assert Harness(Pass(lines=lines)).apply() == 1


def test_naive_timestamps_read_as_utc():
    naive = FRESH.replace(tzinfo=None)
    p = Pass(state=_state(naive), tick=_tick(naive),
             lines=[_line(f"crash-loop:{s}", "healthy", naive) for s in SCOPES])
    assert Harness(p).apply() == 0


# --------------------------------------------------------------------------- #
# Joined-pass rule.
# --------------------------------------------------------------------------- #
def test_joined_pass_then_fresh_pass_succeeds_with_two_starts(capsys):
    h = Harness(_stale_pass(), Pass())
    assert h.apply() == 0
    assert len(h.runs) == 2
    assert "joined" in capsys.readouterr().out


def test_stale_twice_fails_with_two_starts():
    h = Harness(_stale_pass(), _stale_pass(), Pass())
    assert h.apply() == 1
    assert len(h.runs) == 2


def test_stale_plus_hard_failure_is_not_retried():
    stale_bad = Pass(state=_state(STALE), tick=_tick(STALE),
                     lines=_scope_lines(STALE) + _scope_lines(FRESH, user="unknown"))
    h = Harness(stale_bad, Pass())
    assert h.apply() == 1
    assert len(h.runs) == 1


def test_retry_start_failure_fails():
    h = Harness(_stale_pass(), Pass())

    def run(argv: list[str], timeout: float) -> tuple[int, str, str]:
        rc = h.run(argv, timeout)
        return (1, "", "boom") if len(h.runs) == 2 else rc

    assert mod.apply(run=run, now=lambda: T0, read_text=h.read_text,
                     preflight=lambda: True) == 1
    assert len(h.runs) == 2


def test_default_runner_maps_timeout_to_failure(monkeypatch):
    def boom(*_a, **_k):
        raise subprocess.TimeoutExpired(cmd="systemctl", timeout=120)

    monkeypatch.setattr(mod.subprocess, "run", boom)
    rc, _out, err = mod._run(["systemctl"], 120)
    assert rc != 0 and "timed out" in err


def test_ledger_days_cover_midnight():
    late = datetime(2026, 11, 24, 23, 59, 59, tzinfo=UTC)
    days = mod.ledger_paths(late, late + timedelta(seconds=5))
    assert [p.name for p in days] == ["2026-11-24.jsonl", "2026-11-25.jsonl"]
    assert mod.ledger_paths(T0, T0) == [mod.LEDGER_DIR / f"{date(2026, 11, 24)}.jsonl"]


def test_paths_match_the_canary_modules():
    from scripts.canary import crash_loop_state, run

    assert mod.STATE_PATH == crash_loop_state.DEFAULT_STATE_PATH
    assert mod.TICK_PATH == run.DEFAULT_TICK_PATH
    assert mod.LEDGER_DIR == run.DEFAULT_LEDGER_DIR


# --------------------------------------------------------------------------- #
# The entrypoint and the manifest.
# --------------------------------------------------------------------------- #
def _manifest_path() -> Path:
    """felix-deployer moves the queued manifest to ``deploys/applied/`` on apply."""
    for sub in ("queued", "applied"):
        found = sorted((_ROOT / "deploys" / sub).glob(f"*{NAME}.yaml"))
        if found:
            return found[-1]
    raise AssertionError(f"no {NAME} manifest found")


def _manifest() -> dict:
    return yaml.safe_load(_manifest_path().read_text(encoding="utf-8"))


def test_manifest_validates_against_schema():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(_manifest())


def test_manifest_shape():
    m = _manifest()
    assert m["name"] == NAME
    assert re.sub(r"^\d{4}-", "", _manifest_path().stem) == m["name"]
    assert m["issue"] == "kentonium3/kg-automation#1133"
    assert m["tier"] == 3
    assert m["audited_surface"] is True
    assert "expected_baselines" not in m
    assert m["entrypoint"] == "scripts/deploy/deploy-crash-loop-unit-alerting.py"
    assert m["verification"]["pre"] == ["scripts/deploy/deploy-crash-loop-unit-alerting.py --dry-run"]
    assert "crash-loop.json" in " ".join(m["verification"]["post"])
    assert len(m["notes"]) <= 2000


def test_entrypoint_is_executable():
    rel = str(_PATH.relative_to(_ROOT))
    out = subprocess.run(["git", "ls-files", "-s", rel], cwd=_ROOT,
                         capture_output=True, text=True, check=True).stdout
    if out:
        assert out.startswith("100755"), out
    else:  # not yet committed
        assert os.access(_PATH, os.X_OK)


def test_entrypoint_never_uses_ssh_or_sudo():
    src = _PATH.read_text(encoding="utf-8")
    assert "ssh " not in src
    assert '"ssh"' not in src and "'ssh'" not in src
    assert "sudo" not in src.lower()


def test_main_requires_a_mode():
    with pytest.raises(SystemExit):
        mod.main([])
