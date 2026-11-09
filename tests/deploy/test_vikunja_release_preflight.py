"""Stable-copy preflight races, time budgets, privacy and cleanup."""

from pathlib import Path
import os
import signal
import sqlite3

import pytest

from scripts.deploy.vikunja_release import baseline, core, dbsafety
from scripts.vikunja import preflight_release_baseline as preflight
from tests.deploy.test_vikunja_release_acceptance import synthetic, interrupt_command


def assert_clean(s):
    assert list(Path(s["record"]["roots"]["private_logs"]).iterdir()) == []


def test_preflight_main_and_no_activation_receipt(synthetic, capsys):
    s = synthetic
    assert preflight.main([str(s["release"])], repository_root=s["root"]) == 0
    output = capsys.readouterr()
    assert output.out.startswith("PREFLIGHT_OK consolidation_seconds=")
    assert " gate_seconds=" in output.out and output.err == ""
    assert str(s["root"]) not in output.out
    assert_clean(s)


@pytest.mark.parametrize("mode", ["hash", "membership", "appearance", "disappearance"])
def test_five_unstable_rounds(synthetic, monkeypatch, mode):
    s = synthetic
    calls = []
    original = preflight._copy_round
    def changing(source, target, deadline):
        result = original(source, target, deadline)
        calls.append(target)
        if mode == "hash":
            result[dbsafety.DB_NAME] = str(len(calls))
        elif mode == "membership":
            if len(calls) % 2:
                result[dbsafety.DB_NAME + "-wal"] = "synthetic"
        else:
            raise FileNotFoundError("private copy race sentinel")
        return result
    monkeypatch.setattr(preflight, "_copy_round", changing)
    with pytest.raises(core.Fail, match="^PREFLIGHT_COPY_UNSTABLE$"):
        preflight.preflight(s["record"], repository_root=s["root"])
    assert len(calls) == 5
    assert_clean(s)


def test_eventual_stability(synthetic, monkeypatch):
    s = synthetic
    original = preflight._copy_round
    calls = []
    def settling(*args):
        result = original(*args)
        calls.append(1)
        if len(calls) < 3:
            result[dbsafety.DB_NAME] = str(len(calls))
        return result
    monkeypatch.setattr(preflight, "_copy_round", settling)
    preflight.preflight(s["record"], repository_root=s["root"])
    assert len(calls) == 4
    assert_clean(s)


def test_real_wal_copy_keeps_committed_rows(synthetic):
    s = synthetic
    conn = sqlite3.connect(s["pre"])
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA wal_autocheckpoint=0")
        conn.execute("INSERT INTO tasks VALUES (4,1,'FREQ=WEEKLY',1)")
        conn.commit()
        assert Path(str(s["pre"]) + "-wal").exists()
        # The qualification schema stays unchanged; aggregates are computed on the private copy.
        preflight.preflight(s["record"], repository_root=s["root"])
        assert_clean(s)
    finally:
        conn.close()


@pytest.mark.parametrize("kind", ["disappears", "appears"])
def test_round_checks_membership_after_copy(synthetic, tmp_path, monkeypatch, kind):
    s = synthetic
    wal = Path(str(s["pre"]) + "-wal")
    if kind == "disappears":
        wal.write_bytes(b"synthetic wal")
    original = os.read
    changed = []
    def mutate(fd, size):
        result = original(fd, size)
        if not changed:
            changed.append(True)
            if kind == "appears":
                wal.write_bytes(b"synthetic wal")
            else:
                wal.unlink()
        return result
    monkeypatch.setattr(preflight.os, "read", mutate)
    target = tmp_path / "round"
    target.mkdir(mode=0o700)
    with pytest.raises(FileNotFoundError):
        preflight._copy_round(s["pre"].parent, target, core.Deadline(90))


@pytest.mark.parametrize("stage", ["snapshot", "compare", "copy", "interrupt"])
def test_failure_cleanup_and_public_privacy(synthetic, monkeypatch, capsys, stage):
    s = synthetic
    def fail(*args, **kwargs):
        if stage == "interrupt":
            raise KeyboardInterrupt("private path timestamp hash aggregate sentinel")
        raise RuntimeError("private path timestamp hash aggregate sentinel")
    if stage in {"snapshot", "interrupt"}:
        monkeypatch.setattr(dbsafety, "snapshot", fail)
    elif stage == "compare":
        monkeypatch.setattr(baseline, "compare", fail)
    else:
        monkeypatch.setattr(preflight, "_copy_round", fail)
    assert preflight.main([str(s["release"])], repository_root=s["root"]) == 1
    output = capsys.readouterr()
    assert output.out == "PREFLIGHT_FAILED\n" and output.err == ""
    assert_clean(s)


@pytest.mark.parametrize("sql,code", [
    ("INSERT INTO migration VALUES ('99')", "GATE_MIGRATIONS_MISMATCH"),
    ("ALTER TABLE tasks ADD COLUMN unexpected TEXT", "GATE_SCHEMA_MISMATCH"),
])
def test_comparison_failure_cleanup(synthetic, sql, code):
    s = synthetic
    with sqlite3.connect(s["pre"]) as conn:
        conn.execute(sql)
    with pytest.raises(core.Fail, match="^" + code + "$"):
        preflight.preflight(s["record"], repository_root=s["root"])
    assert_clean(s)


@pytest.mark.parametrize("stage,elapsed", [("compare", 26), ("snapshot", 91), ("compare", 91)])
def test_simulated_budgets(synthetic, monkeypatch, stage, elapsed):
    s = synthetic
    now = [0.0]
    owner, name = (baseline, "compare") if stage == "compare" else (dbsafety, "snapshot")
    original = getattr(owner, name)
    def slow(*args, **kwargs):
        result = original(*args, **kwargs)
        now[0] += elapsed
        return result
    monkeypatch.setattr(owner, name, slow)
    with pytest.raises(core.Fail, match="^PREFLIGHT_OVER_BUDGET$"):
        preflight.preflight(s["record"], repository_root=s["root"], clock=lambda: now[0])
    assert_clean(s)


def test_total_budget_includes_consolidation_and_comparison(synthetic, monkeypatch):
    s = synthetic
    now = [0.0]
    snapshot, compare = dbsafety.snapshot, baseline.compare
    def slow_snapshot(*args, **kwargs):
        result = snapshot(*args, **kwargs)
        now[0] += 70
        return result
    def slow_compare(*args, **kwargs):
        result = compare(*args, **kwargs)
        now[0] += 22
        return result
    monkeypatch.setattr(dbsafety, "snapshot", slow_snapshot)
    monkeypatch.setattr(baseline, "compare", slow_compare)
    with pytest.raises(core.Fail, match="^PREFLIGHT_OVER_BUDGET$"):
        preflight.preflight(s["record"], repository_root=s["root"], clock=lambda: now[0])
    assert_clean(s)


def test_corrupt_private_copy_refuses_and_cleans(synthetic):
    s = synthetic
    s["pre"].write_bytes(b"synthetic corrupt database sentinel")
    with pytest.raises(core.Fail, match="^PREFLIGHT_FAILED$"):
        preflight.preflight(s["record"], repository_root=s["root"])
    assert_clean(s)


@pytest.mark.parametrize("signum", [signal.SIGTERM, signal.SIGHUP])
def test_termination_during_copy_cleans_private_bytes(synthetic, tmp_path, signum):
    s = synthetic
    ready = tmp_path / "ready"
    code = """
import signal, sys
from pathlib import Path
from scripts.vikunja import preflight_release_baseline as command
original = command.os.read
def slow_read(fd, size):
    chunk = original(fd, size)
    Path(sys.argv[3]).touch()
    signal.pause()
    return chunk
command.os.read = slow_read
raise SystemExit(command.main([sys.argv[2]], repository_root=Path(sys.argv[1])))
"""
    result = interrupt_command(code, [s["root"], s["release"], ready], ready, signum)
    assert result == (1, "PREFLIGHT_FAILED\n", "")
    assert_clean(s)


@pytest.mark.parametrize("active_error", [False, True])
def test_cleanup_failure_is_reported(synthetic, monkeypatch, capsys, active_error):
    s = synthetic
    original = preflight.shutil.rmtree
    def refuse(path, *args, **kwargs):
        if Path(path).name.startswith("preflight-"):
            raise OSError("private sentinel")
        return original(path, *args, **kwargs)
    if active_error:
        def fail(*args):
            raise KeyboardInterrupt
        monkeypatch.setattr(preflight, "_copy_round", fail)
    monkeypatch.setattr(preflight.shutil, "rmtree", refuse)
    try:
        assert preflight.main([str(s["release"])], repository_root=s["root"]) == 1
        output = capsys.readouterr()
        assert output.out == "PREFLIGHT_CLEANUP_FAILED\n" and output.err == ""
    finally:
        for path in Path(s["record"]["roots"]["private_logs"]).iterdir():
            original(path)
