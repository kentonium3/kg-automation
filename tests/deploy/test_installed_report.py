"""The installed-file report channel (#1072; contract
kitty-specs/deploy-runtime-installed-report-01M4ZP8E/contracts/installed-report.md)."""
from __future__ import annotations

import json
import os
import random
import signal

import pytest

from scripts.deploy.lib import installed_report as ir


@pytest.fixture
def report(tmp_path, monkeypatch):
    path = tmp_path / "report.jsonl"
    monkeypatch.setenv(ir.ENV_VAR, str(path))
    return path


def _lines(path):
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


# --- producer -------------------------------------------------------------------

def test_unset_variable_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.delenv(ir.ENV_VAR, raising=False)
    ir.record_installed(tmp_path / "a", tmp_path / "b")
    assert list(tmp_path.iterdir()) == []


def test_empty_variable_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv(ir.ENV_VAR, "")
    ir.record_installed(tmp_path / "a", tmp_path / "b")
    assert list(tmp_path.iterdir()) == []


def test_one_line_per_call_with_resolved_paths(report, tmp_path):
    real = tmp_path / "real.timer"
    real.write_text("x")
    link = tmp_path / "link.timer"
    link.symlink_to(real)
    ir.record_installed(link, tmp_path / "dest" / "real.timer")
    ir.record_installed(real, tmp_path / "dest" / "b.timer")
    lines = _lines(report)
    assert lines[0] == {"source": str(real.resolve()), "dest": str((tmp_path / "dest" / "real.timer").resolve())}
    assert len(lines) == 2


def test_write_failure_prints_the_marker_and_does_not_raise(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(ir.ENV_VAR, str(tmp_path / "no-such-dir" / "report.jsonl"))
    ir.record_installed(tmp_path / "a", tmp_path / "b")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith(ir.WRITE_FAILED_MARKER + ":")
    assert captured.err.count("\n") == 1


# --- reader ---------------------------------------------------------------------

def test_missing_file_is_missing_not_rejected(tmp_path):
    res = ir.read_report(tmp_path / "absent.jsonl")
    assert res == {"entries": [], "rejected": False, "missing": True, "warnings": []}


def test_valid_report_dedups_in_order(tmp_path):
    p = tmp_path / "r.jsonl"
    a = {"source": "/repo/a.timer", "dest": "/home/u/.config/systemd/user/a.timer"}
    b = {"source": "/repo/b.timer", "dest": "/home/u/.config/systemd/user/b.timer"}
    p.write_text("\n".join(json.dumps(x) for x in (a, b, a)) + "\n\n")
    res = ir.read_report(p)
    assert res == {"entries": [a, b], "rejected": False, "missing": False, "warnings": []}


@pytest.mark.parametrize("bad_line", [
    "not json",
    '["a list"]',
    '{"source": "/repo/a"}',
    '{"source": 1, "dest": "/x"}',
    '{"source": "relative/a", "dest": "/x"}',
    '{"source": "/repo/a", "dest": "relative"}',
])
def test_one_bad_line_rejects_the_whole_report(tmp_path, bad_line):
    p = tmp_path / "r.jsonl"
    good = json.dumps({"source": "/repo/a.timer", "dest": "/h/a.timer"})
    p.write_text(good + "\n" + bad_line + "\n" + good + "\n")
    res = ir.read_report(p)
    assert res["rejected"] is True and res["entries"] == [] and res["warnings"]


def test_oversized_is_rejected(tmp_path):
    p = tmp_path / "r.jsonl"
    p.write_bytes(b" " * (ir.MAX_BYTES + 10))
    assert ir.read_report(p)["rejected"] is True


def test_invalid_utf8_is_rejected(tmp_path):
    p = tmp_path / "r.jsonl"
    p.write_bytes(b'{"source": "/a\xff", "dest": "/b"}\n')
    assert ir.read_report(p)["rejected"] is True


def test_too_many_entries_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(ir, "MAX_ENTRIES", 3)
    p = tmp_path / "r.jsonl"
    p.write_text("\n".join(json.dumps({"source": f"/r/{i}", "dest": f"/h/{i}"}) for i in range(4)))
    assert ir.read_report(p)["rejected"] is True


def test_fifo_is_rejected_without_blocking(tmp_path):
    p = tmp_path / "fifo"
    os.mkfifo(p)

    def timeout(*_):
        raise AssertionError("read_report blocked on a FIFO")

    old = signal.signal(signal.SIGALRM, timeout)
    signal.alarm(2)
    try:
        assert ir.read_report(p)["rejected"] is True
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


def test_symlink_is_rejected_even_to_a_valid_report(tmp_path):
    real = tmp_path / "real.jsonl"
    real.write_text(json.dumps({"source": "/r/a", "dest": "/h/a"}) + "\n")
    link = tmp_path / "link.jsonl"
    link.symlink_to(real)
    assert ir.read_report(real)["rejected"] is False
    assert ir.read_report(link)["rejected"] is True


def test_directory_is_rejected(tmp_path):
    d = tmp_path / "dir"
    d.mkdir()
    assert ir.read_report(d)["rejected"] is True


def test_never_raises_on_random_bytes(tmp_path):
    rng = random.Random(1072)
    for i in range(20):
        p = tmp_path / f"blob{i}"
        p.write_bytes(bytes(rng.randrange(256) for _ in range(rng.randrange(1, 400))))
        res = ir.read_report(p)
        assert set(res) == {"entries", "rejected", "missing", "warnings"}


# --- round trip -----------------------------------------------------------------

def test_round_trip(report, tmp_path):
    src = tmp_path / "s.timer"
    src.write_text("x")
    dst = tmp_path / "units" / "s.timer"
    ir.record_installed(src, dst)
    res = ir.read_report(report)
    assert res["entries"] == [{"source": str(src.resolve()), "dest": str(dst.resolve())}]
    assert res["rejected"] is False


def test_producer_never_blocks_on_a_fifo_target(tmp_path, monkeypatch, capsys):
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    monkeypatch.setenv(ir.ENV_VAR, str(fifo))

    def timeout(*_):
        raise AssertionError("record_installed blocked on a FIFO")

    old = signal.signal(signal.SIGALRM, timeout)
    signal.alarm(2)
    try:
        ir.record_installed(tmp_path / "a", tmp_path / "b")
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)
    assert capsys.readouterr().err.startswith(ir.WRITE_FAILED_MARKER)


def test_producer_refuses_a_symlinked_target(tmp_path, monkeypatch, capsys):
    real = tmp_path / "real.jsonl"
    real.write_text("")
    link = tmp_path / "link.jsonl"
    link.symlink_to(real)
    monkeypatch.setenv(ir.ENV_VAR, str(link))
    ir.record_installed(tmp_path / "a", tmp_path / "b")
    assert real.read_text() == ""
    assert capsys.readouterr().err.startswith(ir.WRITE_FAILED_MARKER)


def test_deeply_nested_line_is_rejected_not_raised(tmp_path):
    """renata #1072 WP01: json.loads raises RecursionError (not ValueError)."""
    p = tmp_path / "r.jsonl"
    p.write_text("[" * 500_000 + "\n")
    assert ir.read_report(p)["rejected"] is True


def test_nul_byte_in_a_path_is_rejected(tmp_path):
    p = tmp_path / "r.jsonl"
    p.write_text(json.dumps({"source": "/a\x00b", "dest": "/h/a"}) + "\n")
    assert ir.read_report(p)["rejected"] is True


def test_only_newline_separates_records(tmp_path):
    p = tmp_path / "r.jsonl"
    a = json.dumps({"source": "/r/a", "dest": "/h/a"})
    p.write_text(a + "\x85" + a + "\n")  # NEL inside the line: not a record separator
    assert ir.read_report(p)["rejected"] is True
    p.write_text(a + "\r\n")
    assert ir.read_report(p)["entries"] == [{"source": "/r/a", "dest": "/h/a"}]


def test_duplicates_do_not_count_against_the_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(ir, "MAX_ENTRIES", 2)
    p = tmp_path / "r.jsonl"
    a = json.dumps({"source": "/r/a", "dest": "/h/a"})
    b = json.dumps({"source": "/r/b", "dest": "/h/b"})
    p.write_text("\n".join([a, a, a, b, b]) + "\n")
    assert len(ir.read_report(p)["entries"]) == 2
