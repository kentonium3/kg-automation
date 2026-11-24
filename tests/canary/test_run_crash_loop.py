"""The crash-loop stage inside ``run_pass`` and its wiring in ``main`` (#1133, WP04).

Every test injects a fake :class:`run_mod.CrashLoopCheck`: a ``tmp_path`` state
and lock, the real repo config (or a tmp one), and ``read_scopes`` returning
scripted ``(readings, boot_id)`` per tick. Nothing reaches ``systemctl``,
``docker``, ntfy or ``/data``.

References: research.md R-07, R-08, R-09, R-15; contracts/crash-loop-alert.md
§5-§7.
"""
from __future__ import annotations

import dataclasses
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from scripts.canary import crash_loop as crash_loop_mod
from scripts.canary import crash_loop_model, crash_loop_state
from scripts.canary import run as run_mod
from scripts.canary.crash_loop_model import RestartObservation, ScopeReading
from scripts.common.alert_bus import Alert, Severity
from tests.canary.ledger_reconcile import (
    EmissionResult,
    assert_reconciles,
    load_ledgers,
)
from tests.canary.test_run import _inventory, _make_evaluate

NOW = datetime(2026, 11, 23, 12, 0, 0, tzinfo=timezone.utc)
BOOT = "boot-aaaa"
UNIT = "obsidian-sync.service"

REPO_ROOT = Path(__file__).resolve().parents[2]
INVENTORY_PATH = REPO_ROOT / "docs" / "design" / "architecture" / "data" / "service-inventory.json"

# The persisted TickSignal key set; the crash-loop stage must not change it.
TICK_SIGNAL_KEYS = {
    "status", "completed_at_utc", "components_evaluated", "emitted",
    "suppressed_dedup", "coverage_gaps", "suppressed_status", "errors",
    "duration_ms",
}
# The existing per-component ledger record shape (no `extra`).
EXISTING_LEDGER_KEYS = {
    "component_id", "outcome", "evidence", "emitted", "suppressed_dedup",
    "evaluated_at",
}
INTERVAL_KEYS = {
    "baseline_count", "baseline_at", "current_count", "observed_at", "delta",
    "period_seconds", "m", "bound",
}


# --------------------------------------------------------------------------- #
# Helpers.
# --------------------------------------------------------------------------- #
class _Result:
    def __init__(self, ok: bool):
        self.ok = ok
        self.reason = None if ok else "NTFY_MISSING_TOPIC"


def _obs(name: str, count: int, *, scope: str = "system", state: str = "activating") -> RestartObservation:
    return RestartObservation(
        scope=scope,
        name=name,
        restart_policy="on-failure",
        restart_count=count,
        state=state,
        generation=BOOT,
    )


def _readings(
    system: dict[str, int] | None = None,
    *,
    container_error: str | None = None,
) -> list[ScopeReading]:
    system_obs = tuple(_obs(name, count) for name, count in (system or {}).items())
    container = (
        ScopeReading.failed("container", container_error, 7)
        if container_error
        else ScopeReading.ok("container", (), 0, 3)
    )
    return [
        ScopeReading.ok("system", system_obs, 2, 5),
        ScopeReading.ok("user", (), 0, 4),
        container,
    ]


class _Scripted:
    """``read_scopes`` returning the next scripted readings each call."""

    def __init__(self) -> None:
        self.next: list[ScopeReading] = _readings()
        self.boot_id: str | None = BOOT
        self.calls = 0
        self.raises: Exception | None = None

    def __call__(self, config: crash_loop_model.CrashLoopConfig) -> tuple[list[ScopeReading], str | None]:
        self.calls += 1
        if self.raises is not None:
            raise self.raises
        return list(self.next), self.boot_id


def _check(tmp_path: Path, reader: _Scripted, *, config_path: Path | None = None) -> run_mod.CrashLoopCheck:
    return run_mod.CrashLoopCheck(
        config_path=config_path or crash_loop_model.DEFAULT_CONFIG_PATH,
        state_path=tmp_path / "state" / "crash-loop.json",
        lock_path=tmp_path / "state" / "crash-loop.lock",
        read_scopes=reader,
    )


def _paths(root: Path) -> dict[str, Path]:
    return {
        "dedup_path": root / "state" / "dedup.json",
        "tick_path": root / "state" / "last-tick.json",
        "ledger_dir": root / "ledger",
    }


def _recording_emit(ok: Any = True):
    """Record every alert; ``ok`` is a bool or a predicate on the alert."""
    sent: list[Alert] = []

    def emit_fn(alert: Alert):
        sent.append(alert)
        delivered = ok(alert) if callable(ok) else ok
        return _Result(delivered)

    emit_fn.sent = sent
    return emit_fn


def _read_ledger(ledger_dir: Path, now: datetime = NOW) -> list[dict]:
    path = ledger_dir / f"{now:%Y-%m-%d}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _crash_lines(ledger: list[dict]) -> list[dict]:
    return [r for r in ledger if r["component_id"].startswith("crash-loop:")]


def _event_lines(ledger: list[dict]) -> list[dict]:
    return [r for r in ledger if r["component_id"].count(":") >= 2]


def _pinned(check, now: datetime):
    """*check* with its read bracket collapsed onto *now*, unless a test injected a clock.

    Keeps the scripted-pass tests deterministic: the counters are "sampled"
    at the pass's ``now`` exactly, as before the read bracket existed.
    """
    if check is not None and check.clock is run_mod._wall_clock_utc:
        return dataclasses.replace(check, clock=lambda: now)
    return check


def _pass(tmp_path: Path, check, *, now=NOW, emit_fn=None, inventory=None, evaluate_fn=None, dry_run=False, paths=None):
    check = _pinned(check, now)
    return run_mod.run_pass(
        now=now,
        inventory=inventory if inventory is not None else _inventory("a"),
        emit_fn=emit_fn or _recording_emit(),
        evaluate_fn=evaluate_fn or _make_evaluate({}),
        crash_loop_check=check,
        dry_run=dry_run,
        **(paths or _paths(tmp_path)),
    )


def _crash_alerts(sent: list[Alert]) -> list[Alert]:
    return [a for a in sent if a.source.startswith("felix-canary:crash-loop:")
            and a.source not in {"felix-canary:crash-loop:system",
                                 "felix-canary:crash-loop:user",
                                 "felix-canary:crash-loop:container"}]


# --------------------------------------------------------------------------- #
# Disabled path.
# --------------------------------------------------------------------------- #
def test_no_check_reports_disabled_and_writes_no_crash_loop_line(tmp_path):
    p = _paths(tmp_path)
    summary = run_mod.run_pass(
        now=NOW, inventory=_inventory("a"), emit_fn=_recording_emit(),
        evaluate_fn=_make_evaluate({}), **p,
    )
    assert summary["crash_loop"] == {"enabled": False}
    assert _crash_lines(_read_ledger(p["ledger_dir"])) == []
    assert set(json.loads(p["tick_path"].read_text())) == TICK_SIGNAL_KEYS


# --------------------------------------------------------------------------- #
# SC-001 end to end.
# --------------------------------------------------------------------------- #
def test_sc001_one_alert_after_39_restarts_in_16_minutes(tmp_path):
    reader = _Scripted()
    check = _check(tmp_path, reader)
    p = _paths(tmp_path)

    reader.next = _readings({UNIT: 0})
    em1 = _recording_emit()
    s1 = _pass(tmp_path, check, emit_fn=em1)
    assert _crash_alerts(em1.sent) == []
    assert s1["crash_loop"]["events"] == 0
    assert check.state_path.exists()

    later = NOW + timedelta(minutes=16)
    reader.next = _readings({UNIT: 39})
    em2 = _recording_emit()
    s2 = _pass(tmp_path, check, now=later, emit_fn=em2)

    alerts = _crash_alerts(em2.sent)
    assert len(alerts) == 1
    assert alerts[0].source == f"felix-canary:crash-loop:system:{UNIT}"
    assert alerts[0].severity is Severity.ERROR
    assert s2["crash_loop"]["events"] == 1
    assert s2["crash_loop"]["enabled"] is True
    assert s2["crash_loop"]["scopes"] == {"system": "healthy", "user": "healthy", "container": "healthy"}
    assert s2["alerts_undelivered"] == 0
    assert s2["errors"] == []

    events = _event_lines(_read_ledger(p["ledger_dir"], later))
    assert len(events) == 1
    line = events[0]
    assert line["component_id"] == f"crash-loop:system:{UNIT}"
    assert line["outcome"] == "crash-loop"
    assert line["emitted"] is True
    assert line["delivered"] is True
    assert set(line["interval"]) == INTERVAL_KEYS
    assert line["interval"]["baseline_count"] == 0
    assert line["interval"]["current_count"] == 39
    assert line["interval"]["delta"] == 39
    assert line["interval"]["baseline_at"] == NOW.isoformat()
    assert line["interval"]["observed_at"] == later.isoformat()
    # 960 s over a 900 s window: m = 2, bound = 2·(3 − 1) + 1 = 5 (R-05).
    assert line["interval"]["period_seconds"] == 960.0
    assert line["interval"]["m"] == 2
    assert line["interval"]["bound"] == 5

    saved = json.loads(check.state_path.read_text())
    assert saved["units"][f"system:{UNIT}"]["episode"] is not None


class _ScriptedClock:
    """A wall clock returning the scripted instants in order, one per call."""

    def __init__(self, *instants: datetime) -> None:
        self.instants = list(instants)

    def __call__(self) -> datetime:
        return self.instants.pop(0)


def _bracketed_check(tmp_path: Path, reader: _Scripted, clock: _ScriptedClock) -> run_mod.CrashLoopCheck:
    return dataclasses.replace(_check(tmp_path, reader), clock=clock)


def _at(seconds: float) -> datetime:
    return NOW + timedelta(seconds=seconds)


def test_sc001_still_pages_with_a_read_bracket(tmp_path):
    # The incident replay with each read taking 2 s, 10 s into its pass.
    reader = _Scripted()
    clock = _ScriptedClock(_at(10), _at(12), _at(970), _at(972))
    check = _bracketed_check(tmp_path, reader, clock)
    p = _paths(tmp_path)

    reader.next = _readings({UNIT: 0})
    _pass(tmp_path, check)
    later = NOW + timedelta(minutes=16)
    reader.next = _readings({UNIT: 39})
    em = _recording_emit()
    _pass(tmp_path, check, now=later, emit_fn=em)

    assert len(_crash_alerts(em.sent)) == 1
    line = _event_lines(_read_ledger(p["ledger_dir"], later))[0]
    # Stored at the first read's start, proved to the second read's end.
    assert line["interval"]["baseline_at"] == _at(10).isoformat()
    assert line["interval"]["observed_at"] == _at(972).isoformat()
    assert line["interval"]["period_seconds"] == 962.0
    assert line["interval"]["m"] == 2
    assert line["interval"]["bound"] == 5
    assert line["interval"]["delta"] == 39


def test_late_reads_never_shrink_the_proven_interval(tmp_path):
    """Post-merge review counterexample (NFR-004): must NOT page.

    Passes are stamped 0 s, 900 s and 1800 s, but the counters are read at
    about 10 s and 1835 s, and the 900 s pass's system read fails. Restarts at
    11, 466, 921, 1376 and 1831 s: any three span 910 s, so no 900 s window
    holds three. Proving with the pass stamps gives delta 5, L 1800, m 2,
    bound 5 and a false page; the read bracket gives L ≥ 1825, m 3, bound 7.
    """
    reader = _Scripted()
    clock = _ScriptedClock(_at(9.5), _at(10.5), _at(905), _at(906), _at(1834.5), _at(1835.5))
    check = _bracketed_check(tmp_path, reader, clock)
    p = _paths(tmp_path)

    reader.next = _readings({UNIT: 0})  # sampled at ~10 s, before the 11 s restart
    _pass(tmp_path, check, now=_at(0))

    reader.next = [
        ScopeReading.failed("system", "systemctl timed out", 5),
        ScopeReading.ok("user", (), 0, 4),
        ScopeReading.ok("container", (), 0, 3),
    ]
    s2 = _pass(tmp_path, check, now=_at(900))
    assert s2["crash_loop"]["scopes"]["system"] == "unknown"

    reader.next = _readings({UNIT: 5})  # sampled at ~1835 s, after all five
    em = _recording_emit()
    s3 = _pass(tmp_path, check, now=_at(1800), emit_fn=em)

    assert _crash_alerts(em.sent) == []
    assert s3["crash_loop"]["events"] == 0
    assert s3["crash_loop"]["unverified"] == 1
    rise = [
        r for r in _read_ledger(p["ledger_dir"], _at(1800))
        if r["outcome"] == "crash-loop-unverified"
    ]
    assert len(rise) == 1
    interval = rise[0]["interval"]
    assert interval["baseline_at"] == _at(9.5).isoformat()
    assert interval["observed_at"] == _at(1835.5).isoformat()
    assert interval["period_seconds"] == 1826.0
    assert interval["delta"] == 5
    assert interval["m"] == 3
    assert interval["bound"] == 7
    assert clock.instants == []


def test_pass_start_stamps_would_have_paged_the_counterexample(tmp_path):
    """The same counterexample with the bracket collapsed onto the pass stamps.

    Guards the regression above: without the bracket the proof is unsound and
    the pass pages, so the previous test is only green because of the bracket.
    """
    reader = _Scripted()
    check = _check(tmp_path, reader)  # _pass pins the clock to each pass's now
    reader.next = _readings({UNIT: 0})
    _pass(tmp_path, check, now=_at(0))
    reader.next = _readings({UNIT: 5})
    em = _recording_emit()
    _pass(tmp_path, check, now=_at(1800), emit_fn=em)
    assert len(_crash_alerts(em.sent)) == 1


# --------------------------------------------------------------------------- #
# SC-005 paired runs: existing components unchanged with the stage enabled.
# --------------------------------------------------------------------------- #
def test_sc005_existing_components_identical_with_stage_enabled(tmp_path):
    inv = _inventory("a", "b", "c", "d", gaps=True)
    outcomes = {"a": "failed", "b": "healthy", "c": "unknown", "d": "suppressed"}

    def one_run(root: Path, check):
        em = _recording_emit()
        p = _paths(root)
        summary = run_mod.run_pass(
            now=NOW, inventory=inv, emit_fn=em, evaluate_fn=_make_evaluate(outcomes),
            crash_loop_check=check, **p,
        )
        ledger = _read_ledger(p["ledger_dir"])
        dedup = json.loads(p["dedup_path"].read_text())
        return summary, em.sent, ledger, dedup

    off = one_run(tmp_path / "off", None)
    reader = _Scripted()
    reader.next = _readings({UNIT: 4, "other.service": 0})
    on = one_run(tmp_path / "on", _check(tmp_path / "on", reader))

    def existing(lines):
        return [r for r in lines if not r["component_id"].startswith("crash-loop:")]

    # Ledger: identical existing lines, in order, in the existing record shape.
    assert existing(on[2]) == existing(off[2])
    assert all(set(r) == EXISTING_LEDGER_KEYS for r in existing(on[2]))
    # Only new lines: the three scope components.
    assert [r["component_id"] for r in on[2] if r not in existing(on[2])] == [
        "crash-loop:system", "crash-loop:user", "crash-loop:container",
    ]
    # Dedup: identical existing entries; the only new keys are the scopes.
    assert {k: v for k, v in on[3].items() if not k.startswith("crash-loop:")} == off[3]
    assert set(on[3]) - set(off[3]) == {"crash-loop:system", "crash-loop:user", "crash-loop:container"}

    # Emitted alerts: identical (first-seen healthy scopes do not page).
    def shape(alerts):
        return [(a.source, a.severity, a.title, a.description, a.details) for a in alerts]

    assert shape(on[1]) == shape(off[1])
    # Counters move only by the scope components.
    assert on[0]["components_evaluated"] == off[0]["components_evaluated"] + 3
    for key in ("emitted", "suppressed_dedup", "coverage_gaps", "suppressed_status", "errors", "status"):
        assert on[0][key] == off[0][key], key


# --------------------------------------------------------------------------- #
# Key ledger reconciliation with the stage enabled.
# --------------------------------------------------------------------------- #
def test_key_ledger_reconciles_with_stage_enabled(tmp_path):
    ledgers = load_ledgers(json.loads(INVENTORY_PATH.read_text(encoding="utf-8")))
    fixture = {
        "services": [{
            "id": "fixture-svc", "name": "fixture-svc", "type": "systemd-timer",
            "status": "active",
            "health_check": {"method": "http", "endpoint": "http://fixture", "timeout_seconds": 1},
        }]
    }
    reader = _Scripted()
    reader.next = _readings({UNIT: 0})
    p = _paths(tmp_path)
    summary = run_mod.run_pass(
        now=NOW, inventory=fixture, emit_fn=lambda _a: None,
        http_get=lambda *_a, **_k: 200, run_cmd=lambda *_a, **_k: (0, "", ""),
        read_state=lambda _p: {}, crash_loop_check=_check(tmp_path, reader), **p,
    )
    assert summary["status"] == "success", summary
    assert summary["crash_loop"]["enabled"] is True
    text = p["tick_path"].read_text(encoding="utf-8")
    document = json.loads(text)
    assert "crash_loop" not in document
    assert set(document) == TICK_SIGNAL_KEYS
    emission = EmissionResult(
        process_ok=True, process_detail="run_pass returned dict",
        document_text=text, document=document,
    )
    assert_reconciles(emission, ledgers["felix-canary"], "felix-canary")


# --------------------------------------------------------------------------- #
# Fault injection (FR-013, NFR-005).
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("fault", ["read_scopes", "evaluate_tick", "save_state"])
def test_stage_fault_never_aborts_the_pass(tmp_path, monkeypatch, fault):
    reader = _Scripted()
    reader.next = _readings({UNIT: 0})
    if fault == "read_scopes":
        reader.raises = RuntimeError("reader exploded")
    elif fault == "evaluate_tick":
        def boom(*_a, **_k):
            raise RuntimeError("decision exploded")
        monkeypatch.setattr(crash_loop_mod, "evaluate_tick", boom)
    else:
        def boom_save(*_a, **_k):
            raise OSError("disk full")
        monkeypatch.setattr(crash_loop_state, "save_state", boom_save)

    inv = _inventory("a", "b", "c", gaps=True)
    ev = _make_evaluate({"a": "failed", "c": "stale"})
    em = _recording_emit()
    p = _paths(tmp_path)
    summary = run_mod.run_pass(
        now=NOW, inventory=inv, emit_fn=em, evaluate_fn=ev,
        crash_loop_check=_check(tmp_path, reader), **p,
    )

    assert ev.calls == ["a", "b", "c"]
    assert any(e.startswith("crash_loop") for e in summary["errors"]), summary["errors"]
    assert summary["status"] == "error"
    # Every inventory component (and the gap) was still ledgered and routed.
    ids = {r["component_id"] for r in _read_ledger(p["ledger_dir"])}
    assert {"a", "b", "c", "gap-svc"} <= ids
    dedup = json.loads(p["dedup_path"].read_text())
    assert {"a", "b", "c", "gap-svc"} <= set(dedup)
    signal = json.loads(p["tick_path"].read_text())
    assert signal["status"] == "error"
    assert set(signal) == TICK_SIGNAL_KEYS
    if fault == "save_state":
        assert any(e.startswith("crash_loop_state_save:OSError") for e in summary["errors"])
        assert not (tmp_path / "state" / "crash-loop.json").exists()
    else:
        assert any(e.startswith("crash_loop:RuntimeError:") for e in summary["errors"])


# --------------------------------------------------------------------------- #
# Config invalid.
# --------------------------------------------------------------------------- #
def test_config_invalid_routes_scopes_unknown_and_leaves_state(tmp_path):
    bad = tmp_path / "bad-config.json"
    bad.write_text('{"threshold": 1}', encoding="utf-8")
    reader = _Scripted()
    check = _check(tmp_path, reader, config_path=bad)
    check.state_path.parent.mkdir(parents=True, exist_ok=True)
    check.state_path.write_text('{"sentinel": true}', encoding="utf-8")
    em = _recording_emit()
    p = _paths(tmp_path)

    summary = _pass(tmp_path, check, emit_fn=em)

    assert reader.calls == 0
    assert check.state_path.read_text(encoding="utf-8") == '{"sentinel": true}'
    assert not check.lock_path.exists()
    assert em.sent == []  # first-seen unknown is not paged (F5)
    scope_lines = _crash_lines(_read_ledger(p["ledger_dir"]))
    assert [r["component_id"] for r in scope_lines] == [
        "crash-loop:system", "crash-loop:user", "crash-loop:container",
    ]
    for line in scope_lines:
        assert line["outcome"] == "unknown"
        assert line["emitted"] is False
        assert line["evidence"].startswith("could not check: config invalid: ")
    assert summary["crash_loop"]["scopes"] == dict.fromkeys(("system", "user", "container"), "unknown")


# --------------------------------------------------------------------------- #
# Lock busy.
# --------------------------------------------------------------------------- #
def test_lock_busy_skips_stage_and_leaves_state(tmp_path):
    reader = _Scripted()
    check = _check(tmp_path, reader)
    p = _paths(tmp_path)
    reader.next = _readings({UNIT: 0})
    _pass(tmp_path, check)
    state_before = check.state_path.read_bytes()
    dedup_before = json.loads(p["dedup_path"].read_text())

    later = NOW + timedelta(minutes=16)
    reader.next = _readings({UNIT: 39})
    em = _recording_emit()
    with crash_loop_state.StateLock(check.lock_path):
        summary = _pass(tmp_path, check, now=later, emit_fn=em)

    assert "crash_loop:locked" in summary["errors"]
    assert reader.calls == 1  # only the first tick read
    assert _crash_alerts(em.sent) == []
    assert check.state_path.read_bytes() == state_before
    assert [r for r in _crash_lines(_read_ledger(p["ledger_dir"], later))
            if r["evaluated_at"] == later.isoformat()] == []
    dedup_after = json.loads(p["dedup_path"].read_text())
    for scope in ("system", "user", "container"):
        assert dedup_after[f"crash-loop:{scope}"] == dedup_before[f"crash-loop:{scope}"]
    assert summary["status"] == "error"


# --------------------------------------------------------------------------- #
# Undelivered: counted, not retried; the dead-man pings fail.
# --------------------------------------------------------------------------- #
def test_undelivered_alert_is_counted_and_not_resent(tmp_path):
    reader = _Scripted()
    check = _check(tmp_path, reader)
    p = _paths(tmp_path)
    reader.next = _readings({UNIT: 0})
    _pass(tmp_path, check)

    t2 = NOW + timedelta(minutes=16)
    reader.next = _readings({UNIT: 39})
    em2 = _recording_emit(lambda a: not a.source.startswith("felix-canary:crash-loop:system:"))
    s2 = _pass(tmp_path, check, now=t2, emit_fn=em2)
    assert len(_crash_alerts(em2.sent)) == 1
    assert s2["alerts_undelivered"] == 1
    line = _event_lines(_read_ledger(p["ledger_dir"], t2))[0]
    assert line["delivered"] is False
    assert line["emitted"] is True
    state = crash_loop_state.load_state(check.state_path, now=t2)[0]
    assert state.units[f"system:{UNIT}"].episode is not None

    # Next tick, still looping: no retry (re-remind waits the 6 h window).
    t3 = t2 + timedelta(minutes=5)
    reader.next = _readings({UNIT: 60})
    em3 = _recording_emit()
    s3 = _pass(tmp_path, check, now=t3, emit_fn=em3)
    assert _crash_alerts(em3.sent) == []
    assert s3["alerts_undelivered"] == 0
    assert s3["crash_loop"]["events"] == 0


def test_undelivered_cleared_is_counted(tmp_path):
    reader = _Scripted()
    check = _check(tmp_path, reader)
    reader.next = _readings({UNIT: 0})
    _pass(tmp_path, check)
    reader.next = _readings({UNIT: 39})
    _pass(tmp_path, check, now=NOW + timedelta(minutes=16))
    _pass(tmp_path, check, now=NOW + timedelta(minutes=21))  # quiet tick 1
    t = NOW + timedelta(minutes=26)  # quiet tick 2 → cleared
    em = _recording_emit(False)
    summary = _pass(tmp_path, check, now=t, emit_fn=em)
    cleared = _crash_alerts(em.sent)
    assert len(cleared) == 1 and cleared[0].severity is Severity.INFO
    assert summary["alerts_undelivered"] == 1
    line = _event_lines(_read_ledger(_paths(tmp_path)["ledger_dir"], t))[-1]
    assert line["outcome"] == "crash-loop-cleared"
    assert line["delivered"] is False


@pytest.fixture
def deadman(monkeypatch):
    pings: list[tuple[str, str]] = []
    monkeypatch.setattr(run_mod.deadman, "ping", lambda label, outcome, **kw: pings.append((label, outcome)))
    monkeypatch.setattr(
        run_mod.deadman, "channel_ok",
        lambda env, delivered_ok, **kw: (delivered_ok, "ok" if delivered_ok else "undelivered"),
    )
    monkeypatch.setattr(run_mod.deadman, "is_configured", lambda label, **kw: True)
    return pings


def _route_main(monkeypatch, tmp_path, check, *, pass_now, emit_fn, paths=None):
    """Route main() to the real run_pass with *check* in place of production's."""
    real = run_mod.run_pass

    def fake_run_pass(*, now, dry_run=False, crash_loop_check=None):
        assert isinstance(crash_loop_check, run_mod.CrashLoopCheck)
        return real(
            now=pass_now, inventory=_inventory("a"), emit_fn=emit_fn,
            evaluate_fn=_make_evaluate({}), crash_loop_check=_pinned(check, pass_now),
            dry_run=dry_run,
            **(paths or _paths(tmp_path)),
        )

    monkeypatch.setattr(run_mod, "run_pass", fake_run_pass)


def test_undelivered_crash_loop_alert_pings_fail_through_main(tmp_path, monkeypatch, deadman, capsys):
    reader = _Scripted()
    check = _check(tmp_path, reader)
    reader.next = _readings({UNIT: 0})
    _pass(tmp_path, check)

    reader.next = _readings({UNIT: 39})
    em = _recording_emit(False)
    _route_main(monkeypatch, tmp_path, check, pass_now=NOW + timedelta(minutes=16), emit_fn=em)
    assert run_mod.main(["--once"]) == 0
    assert deadman == [("canary", "fail")]
    out = capsys.readouterr().out
    assert "crash_loop_events=1" in out
    assert out.startswith("status=success ")


# --------------------------------------------------------------------------- #
# Dry run.
# --------------------------------------------------------------------------- #
def test_dry_run_through_main_writes_nothing(tmp_path, monkeypatch, deadman, capsys):
    reader = _Scripted()
    check = _check(tmp_path, reader)
    reader.next = _readings({UNIT: 0})
    em = _recording_emit()
    _route_main(monkeypatch, tmp_path, check, pass_now=NOW, emit_fn=em)

    assert run_mod.main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert em.sent == []
    assert not (tmp_path / "state").exists()  # no state, lock, dedup or tick
    assert not (tmp_path / "ledger").exists()
    assert "crash-loop:system: healthy" in out
    assert deadman == []


def test_dry_run_plans_but_does_not_emit_or_save(tmp_path, monkeypatch, deadman, capsys):
    reader = _Scripted()
    check = _check(tmp_path, reader)
    reader.next = _readings({UNIT: 0})
    _pass(tmp_path, check, paths=_paths(tmp_path / "seed"))
    state_before = check.state_path.read_bytes()

    reader.next = _readings({UNIT: 39})
    em = _recording_emit()
    dry_paths = _paths(tmp_path / "dry")
    _route_main(monkeypatch, tmp_path, check, pass_now=NOW + timedelta(minutes=16), emit_fn=em, paths=dry_paths)
    assert run_mod.main(["--dry-run"]) == 0
    out = capsys.readouterr().out

    assert em.sent == []
    assert check.state_path.read_bytes() == state_before
    assert not (tmp_path / "dry").exists()
    assert f"crash-loop:system:{UNIT}: crash-loop [emitted]" in out
    assert "crash-loop:system: healthy" in out


# --------------------------------------------------------------------------- #
# main wiring.
# --------------------------------------------------------------------------- #
def test_main_passes_the_production_check(monkeypatch, deadman):
    calls: list[dict] = []

    def recorder(**kwargs):
        calls.append(kwargs)
        return {
            "status": "success", "components_evaluated": 0, "emitted": 0,
            "suppressed_dedup": 0, "coverage_gaps": 0, "suppressed_status": 0,
            "errors": [], "duration_ms": 0, "alerts_undelivered": 0,
            "component_lines": [], "crash_loop": {"enabled": True, "events": 0},
        }

    monkeypatch.setattr(run_mod, "run_pass", recorder)
    assert run_mod.main(["--once"]) == 0
    assert run_mod.main(["--dry-run"]) == 0
    assert len(calls) == 2
    for kwargs in calls:
        check = kwargs["crash_loop_check"]
        assert isinstance(check, run_mod.CrashLoopCheck)
        assert check == run_mod._default_crash_loop_check()
        assert check.config_path == crash_loop_model.DEFAULT_CONFIG_PATH
        assert check.state_path == crash_loop_state.DEFAULT_STATE_PATH
        assert check.lock_path == crash_loop_state.DEFAULT_LOCK_PATH
        assert check.read_scopes is run_mod._default_read_scopes
    assert [c["dry_run"] for c in calls] == [False, True]


def test_default_read_scopes_uses_the_config_budget(monkeypatch):
    seen: dict[str, Any] = {}

    def fake_read_all(**kwargs):
        seen.update(kwargs)
        return [], "b"

    monkeypatch.setattr(run_mod.crash_loop_readers, "read_all_scopes", fake_read_all)
    config = crash_loop_model.load_config()
    assert run_mod._default_read_scopes(config) == ([], "b")
    assert seen == {"budget_seconds": config.read_budget_seconds}


# --------------------------------------------------------------------------- #
# Scope unknown.
# --------------------------------------------------------------------------- #
def test_container_scope_unknown_is_ledgered_not_paged(tmp_path):
    reader = _Scripted()
    reader.next = _readings({UNIT: 0}, container_error="docker unavailable")
    em = _recording_emit()
    p = _paths(tmp_path)
    summary = _pass(tmp_path, _check(tmp_path, reader), emit_fn=em)

    assert em.sent == []
    by_id = {r["component_id"]: r for r in _crash_lines(_read_ledger(p["ledger_dir"]))}
    assert by_id["crash-loop:container"]["outcome"] == "unknown"
    assert by_id["crash-loop:container"]["emitted"] is False
    assert by_id["crash-loop:container"]["evidence"] == "could not check: docker unavailable"
    assert by_id["crash-loop:system"]["outcome"] == "healthy"
    assert by_id["crash-loop:user"]["outcome"] == "healthy"
    assert summary["crash_loop"]["scopes"] == {"system": "healthy", "user": "healthy", "container": "unknown"}
    assert summary["errors"] == []


# --------------------------------------------------------------------------- #
# Cap: 3 individual + 1 aggregate; one ledger line per event.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("aggregate_ok", [True, False])
def test_cap_three_plus_aggregate(tmp_path, aggregate_ok):
    names = [f"unit{i}.service" for i in range(7)]
    reader = _Scripted()
    check = _check(tmp_path, reader)
    p = _paths(tmp_path)
    reader.next = _readings(dict.fromkeys(names, 0))
    _pass(tmp_path, check)

    later = NOW + timedelta(minutes=16)
    reader.next = _readings(dict.fromkeys(names, 39))
    em = _recording_emit(lambda a: aggregate_ok or a.source != crash_loop_mod.AGGREGATE_SOURCE)
    summary = _pass(tmp_path, check, now=later, emit_fn=em)

    crash = _crash_alerts(em.sent)
    assert len(crash) == 4
    assert crash[-1].source == crash_loop_mod.AGGREGATE_SOURCE
    assert summary["emitted"] == 4
    assert summary["crash_loop"]["events"] == 7
    events = _event_lines(_read_ledger(p["ledger_dir"], later))
    assert len(events) == 7
    folded = [r for r in events if r["evidence"].endswith("(in aggregate alert)")]
    assert len(folded) == 4
    if aggregate_ok:
        assert all(r["delivered"] is True for r in events)
        assert summary["alerts_undelivered"] == 0
    else:
        assert all(r["delivered"] is False for r in folded)
        assert all(r["delivered"] is True for r in events if r not in folded)
        assert summary["alerts_undelivered"] == 1


# --------------------------------------------------------------------------- #
# Unverified rise: ledger only.
# --------------------------------------------------------------------------- #
def test_unverified_rise_is_ledgered_not_emitted(tmp_path):
    reader = _Scripted()
    check = _check(tmp_path, reader)
    p = _paths(tmp_path)
    reader.next = _readings({UNIT: 0})
    _pass(tmp_path, check)

    # 4 restarts over 2 h 15 min: Δ ≥ N (3) but m = 9 makes the bound 19.
    later = NOW + timedelta(hours=2, minutes=15)
    reader.next = _readings({UNIT: 4})
    em = _recording_emit()
    summary = _pass(tmp_path, check, now=later, emit_fn=em)

    assert _crash_alerts(em.sent) == []
    assert summary["crash_loop"]["unverified"] == 1
    lines = _event_lines(_read_ledger(p["ledger_dir"], later))
    assert len(lines) == 1
    assert lines[0]["outcome"] == "crash-loop-unverified"
    assert lines[0]["emitted"] is False
    assert lines[0]["delivered"] is False
    assert lines[0]["interval"]["delta"] == 4
    # 8100 s over a 900 s window: m = 9, bound = 9·(3 − 1) + 1 = 19 (R-05, R-14).
    assert lines[0]["interval"]["period_seconds"] == 8100.0
    assert lines[0]["interval"]["m"] == 9
    assert lines[0]["interval"]["bound"] == 19
    assert "8100 s" in lines[0]["evidence"]
    assert "m=9" in lines[0]["evidence"]
    assert "bound 19" in lines[0]["evidence"]


# --------------------------------------------------------------------------- #
# Scope-unknown lifecycle through the enabled stage (F5, FR-011).
# --------------------------------------------------------------------------- #
def test_container_unknown_pages_once_persistent_then_recovers(tmp_path):
    reader = _Scripted()
    check = _check(tmp_path, reader)
    p = _paths(tmp_path)
    cid = "crash-loop:container"

    def tick(now, *, failing):
        reader.next = _readings({UNIT: 0}, container_error="docker unavailable" if failing else None)
        em = _recording_emit()
        summary = _pass(tmp_path, check, now=now, emit_fn=em)
        scope_alerts = [a for a in em.sent if a.source == f"felix-canary:{cid}"]
        return summary, scope_alerts, json.loads(p["dedup_path"].read_text())[cid]

    # First sight: recorded, not paged.
    _s, alerts, entry = tick(NOW, failing=True)
    assert alerts == []
    assert entry == {"last_outcome": "unknown", "last_emitted_utc": NOW.isoformat()}

    # Inside the 6 h window: still suppressed, entry carried forward.
    t2 = NOW + timedelta(hours=1)
    s2, alerts, entry = tick(t2, failing=True)
    assert alerts == []
    assert s2["suppressed_dedup"] >= 1
    assert entry == {"last_outcome": "unknown", "last_emitted_utc": NOW.isoformat()}

    # Past the window: one WARN.
    t3 = NOW + timedelta(hours=7)
    _s, alerts, entry = tick(t3, failing=True)
    assert len(alerts) == 1
    assert alerts[0].severity is Severity.WARN
    assert alerts[0].title == f"{cid} health: unknown"
    assert entry == {"last_outcome": "unknown", "last_emitted_utc": t3.isoformat()}

    # Healthy again: one INFO recovered.
    t4 = t3 + timedelta(minutes=15)
    _s, alerts, entry = tick(t4, failing=False)
    assert len(alerts) == 1
    assert alerts[0].severity is Severity.INFO
    assert alerts[0].title == f"{cid} health: recovered"
    assert entry == {"last_outcome": "healthy", "last_emitted_utc": t4.isoformat()}

    lines = [r for r in _read_ledger(p["ledger_dir"]) if r["component_id"] == cid]
    assert [(r["outcome"], r["emitted"]) for r in lines] == [
        ("unknown", False), ("unknown", False), ("unknown", True), ("healthy", True),
    ]


# --------------------------------------------------------------------------- #
# Emit, then save (R-07): a failed save after a page repeats the page.
# --------------------------------------------------------------------------- #
def test_failed_save_after_emit_repeats_the_page_next_tick(tmp_path, monkeypatch):
    reader = _Scripted()
    check = _check(tmp_path, reader)
    reader.next = _readings({UNIT: 0})
    _pass(tmp_path, check)
    state_before = check.state_path.read_bytes()

    order: list[str] = []
    real_save = crash_loop_state.save_state

    def failing_save(*_a, **_k):
        order.append("save")
        raise OSError("disk full")

    def emit_fn(alert):
        order.append(f"emit:{alert.source}")
        return _Result(True)

    monkeypatch.setattr(crash_loop_state, "save_state", failing_save)
    t2 = NOW + timedelta(minutes=16)
    reader.next = _readings({UNIT: 39})
    s2 = _pass(tmp_path, check, now=t2, emit_fn=emit_fn)

    source = f"felix-canary:crash-loop:system:{UNIT}"
    assert order == [f"emit:{source}", "save"]
    assert any(e.startswith("crash_loop_state_save:OSError:") for e in s2["errors"])
    assert s2["status"] == "error"
    assert check.state_path.read_bytes() == state_before

    # The next tick, with persistence restored, pages again (fail loud).
    monkeypatch.setattr(crash_loop_state, "save_state", real_save)
    t3 = t2 + timedelta(minutes=5)
    reader.next = _readings({UNIT: 45})
    em3 = _recording_emit()
    s3 = _pass(tmp_path, check, now=t3, emit_fn=em3)
    alerts = _crash_alerts(em3.sent)
    assert [a.source for a in alerts] == [source]
    assert s3["errors"] == []
    assert check.state_path.read_bytes() != state_before
