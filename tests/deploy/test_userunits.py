"""Tests for scripts.deploy.lib.userunits (#1066): systemd user-unit install
mechanism, lifted from the #1062 entrypoint. No test touches systemd or a real
unit directory; the runner, clock, sleep and reader are injected."""
from __future__ import annotations

import pwd
from pathlib import Path

import pytest

from scripts.deploy.lib import LibResult, userunits as uu


# --- pure helpers -------------------------------------------------------------

@pytest.mark.parametrize("value, ok", [
    ("1h 21.06s", True), ("54min 36.9s", True),
    ("infinity", False), ("0", False), ("", False), ("  ", False),
])
def test_next_elapse_is_concrete(value, ok):
    assert uu.next_elapse_is_concrete(value) is ok


def test_parse_show_keeps_values_with_equals_signs():
    assert uu.parse_show("A=1\nB=x=y\nnoise\n") == {"A": "1", "B": "x=y"}


# --- preflight ------------------------------------------------------------------

def test_preflight_user(monkeypatch):
    monkeypatch.setattr(pwd, "getpwuid", lambda _u: type("P", (), {"pw_name": "claude"})())
    monkeypatch.setattr(Path, "home", classmethod(lambda c: Path("/home/claude")))
    assert uu.preflight_user(expected_user="claude", expected_home=Path("/home/claude")).ok
    bad = uu.preflight_user(expected_user="claude", expected_home=Path("/home/other"))
    assert not bad.ok and bad.details["error_code"] == "WRONG_USER"


def test_preflight_has_no_office2_defaults():
    with pytest.raises(TypeError):
        uu.preflight_user()  # type: ignore[call-arg]


# --- install / plan / converged ------------------------------------------------

def _src(tmp_path, name, text):
    p = tmp_path / "repo" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


def test_plan_install_is_tristate_and_writes_nothing(tmp_path):
    a = _src(tmp_path, "a.timer", "[Timer]\nOnCalendar=daily\n")
    b = _src(tmp_path, "b.timer", "[Timer]\nOnCalendar=weekly\n")
    unit_dir = tmp_path / "units"
    unit_dir.mkdir()
    (unit_dir / "b.timer").write_text(b.read_text())
    res = uu.plan_install([a, b], unit_dir)
    assert res.ok
    assert {u["name"]: u["differs"] for u in res.details["units"]} == {"a.timer": True, "b.timer": False}
    assert not (unit_dir / "a.timer").exists()


def test_install_units_refuses_before_copying_when_a_source_is_missing(tmp_path):
    a = _src(tmp_path, "a.timer", "x")
    unit_dir = tmp_path / "units"
    res = uu.install_units([a, tmp_path / "repo" / "missing.timer"], unit_dir)
    assert not res.ok and res.details["error_code"] == "SOURCE_MISSING"
    assert not (unit_dir / "a.timer").exists()


def test_install_units_reports_changed_and_is_idempotent(tmp_path):
    a = _src(tmp_path, "a.timer", "x")
    unit_dir = tmp_path / "units"
    first = uu.install_units([a], unit_dir)
    second = uu.install_units([a], unit_dir)
    assert first.ok and first.details["units"] == [{"name": "a.timer", "changed": True}]
    assert second.ok and second.details["units"] == [{"name": "a.timer", "changed": False}]
    assert (unit_dir / "a.timer").read_text() == "x"
    assert not list(unit_dir.glob("*.tmp")), "no temp files left behind"


def test_converged_treats_unreadable_as_failure(tmp_path):
    a = _src(tmp_path, "a.timer", "x")
    unit_dir = tmp_path / "units"
    unit_dir.mkdir()
    (unit_dir / "a.timer").mkdir()  # unreadable as a file
    res = uu.converged([a], unit_dir)
    assert not res.ok and res.details["units"] == [{"name": "a.timer", "differs": None}]


def test_converged(tmp_path):
    a = _src(tmp_path, "a.timer", "x")
    unit_dir = tmp_path / "units"
    uu.install_units([a], unit_dir)
    assert uu.converged([a], unit_dir).ok
    (unit_dir / "a.timer").write_text("y")
    assert not uu.converged([a], unit_dir).ok


# --- actions --------------------------------------------------------------------

class Run:
    def __init__(self, fail: set[tuple[str, str]] = frozenset(), show: dict | None = None):
        self.fail, self.show_out, self.calls = set(fail), show or {}, []

    def __call__(self, argv):
        self.calls.append(argv)
        key = (argv[2], argv[3] if len(argv) > 3 else "")
        if key in self.fail:
            return 1, "", "boom"
        if argv[2] == "show":
            out = self.show_out[argv[3]]
            return 0, out.pop(0) if isinstance(out, list) and len(out) > 1 else (out[0] if isinstance(out, list) else out), ""
        return 0, "", ""


@pytest.mark.parametrize("action, argv", [
    ("restart", ["systemctl", "--user", "restart", "a.timer"]),
    ("enable-now", ["systemctl", "--user", "enable", "--now", "a.timer"]),
    ("start", ["systemctl", "--user", "start", "a.timer"]),
])
def test_unit_action(action, argv):
    run = Run()
    assert uu.unit_action("a.timer", action, run).ok
    assert run.calls == [argv]


def test_unit_action_none_runs_nothing_and_unknown_is_refused():
    run = Run()
    assert uu.unit_action("a.timer", "none", run).ok and run.calls == []
    assert not uu.unit_action("a.timer", "bounce", run).ok


def test_apply_units_installs_reloads_then_acts_and_continues_past_failures(tmp_path):
    a, b = _src(tmp_path, "a.timer", "x"), _src(tmp_path, "b.timer", "y")
    unit_dir = tmp_path / "units"
    run = Run(fail={("restart", "a.timer")})
    res = uu.apply_units([a, b], unit_dir, action="restart", run=run)
    assert not res.ok
    assert [c[2:] for c in run.calls] == [["daemon-reload"], ["restart", "a.timer"], ["restart", "b.timer"]]
    assert set(res.details["failed"]) == {"a.timer"}
    assert (unit_dir / "a.timer").exists() and (unit_dir / "b.timer").exists()


def test_apply_units_reload_failure_stops_before_actions(tmp_path):
    a = _src(tmp_path, "a.timer", "x")
    run = Run(fail={("daemon-reload", "")})
    res = uu.apply_units([a], tmp_path / "units", action="restart", run=run)
    assert not res.ok and res.details["error_code"] == "DAEMON_RELOAD_FAILED"
    assert [c[2] for c in run.calls] == ["daemon-reload"]


# --- verify ---------------------------------------------------------------------

def _show(unit_dir, name, **over):
    props = {"UnitFileState": "enabled", "ActiveState": "active", "SubState": "waiting",
             "FragmentPath": str(unit_dir / name), "DropInPaths": "",
             "NextElapseUSecMonotonic": "14min", "Persistent": "no"}
    props.update(over)
    return "\n".join(f"{k}={v}" for k, v in props.items())


def _read(_p):
    return "[Timer]\nOnBootSec=5min\nOnUnitActiveSec=15min\n"


def test_verify_unit_checks_expected_props_and_fragment_path(tmp_path):
    good = Run(show={"a.timer": _show(tmp_path, "a.timer")})
    assert uu.verify_unit("a.timer", good, unit_dir=tmp_path, expect={"Persistent": "no"}, read=_read).ok
    wrong = Run(show={"a.timer": _show(tmp_path, "a.timer", Persistent="yes")})
    res = uu.verify_unit("a.timer", wrong, unit_dir=tmp_path, expect={"Persistent": "no"}, read=_read)
    assert not res.ok and any("Persistent" in p for p in res.details["problems"])
    elsewhere = Run(show={"a.timer": _show(tmp_path, "a.timer", FragmentPath="/etc/systemd/user/a.timer")})
    assert not uu.verify_unit("a.timer", elsewhere, unit_dir=tmp_path, read=_read).ok


def test_verify_unit_runs_the_callers_extra_check_over_fragment_and_dropins(tmp_path):
    run = Run(show={"a.timer": _show(tmp_path, "a.timer", DropInPaths="/d/10.conf")})
    seen = {}

    def extra(props, texts):
        seen["texts"] = texts
        return ["policy says no"]

    res = uu.verify_unit("a.timer", run, unit_dir=tmp_path, extra_check=extra,
                         read=lambda p: f"text of {p}")
    assert not res.ok and "policy says no" in res.details["problems"]
    assert seen["texts"] == [f"text of {tmp_path / 'a.timer'}", "text of /d/10.conf"]


def test_verify_unit_fails_on_unreadable_unit_file(tmp_path):
    run = Run(show={"a.timer": _show(tmp_path, "a.timer")})

    def boom(p):
        raise OSError("gone")

    res = uu.verify_unit("a.timer", run, unit_dir=tmp_path, read=boom)
    assert not res.ok and "cannot read" in res.details["problems"][0]


def test_next_elapse_wait_is_opt_in(tmp_path):
    run = Run(show={"a.service": _show(tmp_path, "a.service", NextElapseUSecMonotonic="infinity")})
    assert uu.verify_unit("a.service", run, unit_dir=tmp_path, read=_read).ok


def test_waits_through_running_then_succeeds(tmp_path):
    run = Run(show={"a.timer": [_show(tmp_path, "a.timer", SubState="running", NextElapseUSecMonotonic="infinity"),
                                _show(tmp_path, "a.timer")]})
    slept, events = [], []
    res = uu.verify_unit("a.timer", run, unit_dir=tmp_path, read=_read, wait_next_elapse=True,
                         sleep=slept.append, deadline=10_000.0, monotonic=lambda: 0.0,
                         emit=lambda event, **f: events.append(event))
    assert res.ok and slept == [uu.POLL_INTERVAL_S] and events == ["waiting_for_next_elapse"]


def test_never_rearming_fails_at_the_deadline(tmp_path):
    run = Run(show={"a.timer": _show(tmp_path, "a.timer", SubState="elapsed", NextElapseUSecMonotonic="infinity")})
    res = uu.verify_unit("a.timer", run, unit_dir=tmp_path, read=_read, wait_next_elapse=True,
                         sleep=lambda s: None, deadline=0.0, monotonic=lambda: 1.0)
    assert not res.ok and "no concrete next elapse" in res.details["problems"][0]


def test_library_never_prints(tmp_path, capsys):
    a = _src(tmp_path, "a.timer", "x")
    uu.apply_units([a], tmp_path / "units", action="restart", run=Run(fail={("restart", "a.timer")}))
    uu.verify_unit("a.timer", Run(show={"a.timer": _show(tmp_path, "a.timer")}), unit_dir=tmp_path, read=_read)
    assert capsys.readouterr() == ("", "")


def test_every_public_function_returns_libresult(tmp_path):
    a = _src(tmp_path, "a.timer", "x")
    for res in (uu.plan_install([a], tmp_path / "u"), uu.install_units([a], tmp_path / "u"),
                uu.daemon_reload(Run()), uu.unit_action("a.timer", "none", Run()), uu.converged([a], tmp_path / "u")):
        assert isinstance(res, LibResult)


def test_install_mode_matches_the_copyfile_it_replaced(tmp_path):
    """New file: 0666 & ~umask. Existing file: its mode is kept (shutil.copyfile
    semantics), never mkstemp's 0600."""
    import os
    a = _src(tmp_path, "a.timer", "x")
    unit_dir = tmp_path / "units"
    old = os.umask(0o022)
    try:
        uu.install_units([a], unit_dir)
        assert (unit_dir / "a.timer").stat().st_mode & 0o777 == 0o644
        (unit_dir / "a.timer").chmod(0o640)
        a.write_text("y")
        uu.install_units([a], unit_dir)
        assert (unit_dir / "a.timer").stat().st_mode & 0o777 == 0o640
    finally:
        os.umask(old)


def test_temp_file_creation_failure_is_a_copy_failure_not_a_crash(tmp_path, monkeypatch):
    import tempfile
    a = _src(tmp_path, "a.timer", "x")

    def no_temp(*_a, **_k):
        raise PermissionError("no space for temp files")

    monkeypatch.setattr(tempfile, "mkstemp", no_temp)
    res = uu.install_units([a], tmp_path / "units")
    assert not res.ok and res.details["error_code"] == "COPY_FAILED" and res.details["units"] == []


def test_read_only_destination_is_refused_not_replaced(tmp_path):
    a = _src(tmp_path, "a.timer", "new")
    unit_dir = tmp_path / "units"
    unit_dir.mkdir()
    dst = unit_dir / "a.timer"
    dst.write_text("old")
    dst.chmod(0o444)
    try:
        res = uu.install_units([a], unit_dir)
        assert not res.ok and res.details["error_code"] == "COPY_FAILED"
        assert dst.read_text() == "old"
    finally:
        dst.chmod(0o644)


def test_progress_fires_as_each_step_happens(tmp_path):
    a, b = _src(tmp_path, "a.timer", "x"), _src(tmp_path, "b.timer", "y")
    log: list[tuple] = []
    run = Run(fail={("restart", "b.timer")})
    orig = run.__call__

    def logging_run(argv):
        log.append(("run", argv[2]))
        return orig(argv)

    uu.apply_units([a, b], tmp_path / "units", action="restart", run=logging_run,
                   progress=lambda ev, **f: log.append((ev, f.get("unit"), f.get("ok"))))
    assert log == [("installed", "a.timer", None), ("installed", "b.timer", None),
                   ("run", "daemon-reload"), ("reloaded", None, None),
                   ("run", "restart"), ("acted", "a.timer", True),
                   ("run", "restart"), ("acted", "b.timer", False)]


def test_installed_is_reported_on_reload_failure(tmp_path):
    a = _src(tmp_path, "a.timer", "x")
    res = uu.apply_units([a], tmp_path / "units", action="restart", run=Run(fail={("daemon-reload", "")}))
    assert not res.ok and res.details["installed"] == [{"name": "a.timer", "changed": True}]


def test_verify_unit_honours_a_passed_deadline_without_hanging(tmp_path):
    """renata #1066: a regression that ignores the caller's deadline must FAIL
    here, not hang the suite. The clock raises after a bounded number of reads."""
    run = Run(show={"a.timer": _show(tmp_path, "a.timer", SubState="running", NextElapseUSecMonotonic="infinity")})
    ticks = iter(range(1000, 1100))

    def bounded_clock():
        try:
            return float(next(ticks))
        except StopIteration:
            raise AssertionError("verify_unit kept polling past the deadline it was given")

    res = uu.verify_unit("a.timer", run, unit_dir=tmp_path, read=_read, wait_next_elapse=True,
                         sleep=lambda s: None, deadline=1005.0, monotonic=bounded_clock)
    assert not res.ok and res.details["error_code"] == "NO_NEXT_ELAPSE"


def test_extra_check_runs_even_when_expect_fails_and_unreadable_reports_alone(tmp_path):
    run = Run(show={"a.timer": _show(tmp_path, "a.timer", Persistent="yes")})
    res = uu.verify_unit("a.timer", run, unit_dir=tmp_path, expect={"Persistent": "no"}, read=_read,
                         extra_check=lambda props, texts: ["extra"])
    assert "extra" in res.details["problems"] and any("Persistent" in p for p in res.details["problems"])

    def boom(_p):
        raise OSError("gone")

    res2 = uu.verify_unit("a.timer", Run(show={"a.timer": _show(tmp_path, "a.timer", Persistent="yes")}),
                          unit_dir=tmp_path, expect={"Persistent": "no"}, read=boom)
    assert res2.details["problems"] == [f"cannot read unit file {tmp_path / 'a.timer'}: gone"]


# --- installed-file report (#1072) -------------------------------------------------

from scripts.deploy.lib import installed_report as ir  # noqa: E402


@pytest.fixture
def report(tmp_path, monkeypatch):
    path = tmp_path / "report.jsonl"
    monkeypatch.setenv(ir.ENV_VAR, str(path))
    return path


def _reported(path):
    return ir.read_report(path)


def test_install_reports_exactly_the_changed_files(tmp_path, report):
    a = _src(tmp_path, "a.timer", "a")
    b = _src(tmp_path, "b.timer", "b")
    c = _src(tmp_path, "c.timer", "c")
    unit_dir = tmp_path / "units"
    unit_dir.mkdir()
    (unit_dir / "c.timer").write_text("c")  # unchanged
    assert uu.install_units([a, b, c], unit_dir).ok
    res = _reported(report)
    assert res["rejected"] is False
    assert res["entries"] == [
        {"source": str(a.resolve()), "dest": str((unit_dir / "a.timer").resolve())},
        {"source": str(b.resolve()), "dest": str((unit_dir / "b.timer").resolve())},
    ]


def test_reinstalling_identical_files_reports_nothing(tmp_path, report):
    a = _src(tmp_path, "a.timer", "a")
    unit_dir = tmp_path / "units"
    assert uu.install_units([a], unit_dir).ok
    report.unlink()
    assert uu.install_units([a], unit_dir).ok
    assert _reported(report)["missing"] is True


def test_a_mid_install_failure_reports_only_what_landed(tmp_path, report, monkeypatch):
    a = _src(tmp_path, "a.timer", "a")
    b = _src(tmp_path, "b.timer", "b")
    unit_dir = tmp_path / "units"
    real_replace = uu.os.replace
    calls = []

    def flaky_replace(src, dst):
        calls.append(dst)
        if len(calls) == 2:
            raise OSError("disk full")
        return real_replace(src, dst)

    monkeypatch.setattr(uu.os, "replace", flaky_replace)
    res = uu.install_units([a, b], unit_dir)
    assert not res.ok
    assert [e["dest"] for e in _reported(report)["entries"]] == [str((unit_dir / "a.timer").resolve())]


def test_without_the_variable_no_report_is_written(tmp_path, monkeypatch):
    monkeypatch.delenv(ir.ENV_VAR, raising=False)
    a = _src(tmp_path, "a.timer", "a")
    assert uu.install_units([a], tmp_path / "units").ok
    assert not list(tmp_path.rglob("*.jsonl"))
