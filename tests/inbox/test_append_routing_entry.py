"""Tests for the append_routing_entry CLI — issue_task + calendar routes (#737)."""
from __future__ import annotations

import json
from pathlib import Path

from scripts.inbox import append_routing_entry as cli
from scripts.inbox import routing_log as _routing_log


def _run(argv, capsys):
    code = cli.main(argv)
    cap = capsys.readouterr()
    return code, cap.out, cap.err


def _redirect(tmp_path, monkeypatch):
    log = tmp_path / "routing.jsonl"
    monkeypatch.setattr(_routing_log, "DEFAULT_ROUTING_LOG_PATH", log)
    return log


def test_issue_task_positional_form_unchanged(tmp_path, capsys, monkeypatch):
    log = _redirect(tmp_path, monkeypatch)
    code, out, err = _run(["n.md", "42", "7", "an excerpt"], capsys)
    assert code == 0, err
    row = json.loads(log.read_text().splitlines()[0])
    assert row["filename"] == "n.md"
    assert row["issue_number"] == 42
    assert row["vikunja_task_id"] == 7
    assert row["kind"] == "issue_task"


def test_issue_task_dash_task_id(tmp_path, capsys, monkeypatch):
    log = _redirect(tmp_path, monkeypatch)
    code, out, err = _run(["n.md", "0", "-"], capsys)
    assert code == 0, err
    row = json.loads(log.read_text().splitlines()[0])
    assert row["issue_number"] == 0
    assert row["vikunja_task_id"] is None


def test_calendar_route_records_event_id(tmp_path, capsys, monkeypatch):
    log = _redirect(tmp_path, monkeypatch)
    code, out, err = _run(["Note 1.md", "--kind", "calendar", "--event-id", "evt_xyz"], capsys)
    assert code == 0, err
    row = json.loads(log.read_text().splitlines()[0])
    assert row["kind"] == "calendar"
    assert row["destination"] == "evt_xyz"
    assert row["filename"] == "Note 1.md"
    assert row["issue_number"] is None


def test_calendar_requires_event_id(tmp_path, capsys, monkeypatch):
    _redirect(tmp_path, monkeypatch)
    code, out, err = _run(["n.md", "--kind", "calendar"], capsys)
    assert code == 2
    assert "event-id" in err


def test_calendar_rejects_positional_issue_number(tmp_path, capsys, monkeypatch):
    _redirect(tmp_path, monkeypatch)
    code, out, err = _run(["n.md", "42", "--kind", "calendar", "--event-id", "e"], capsys)
    assert code == 2
    assert "issue_number is not allowed" in err


def test_issue_task_requires_issue_number(tmp_path, capsys, monkeypatch):
    _redirect(tmp_path, monkeypatch)
    code, out, err = _run(["n.md"], capsys)
    assert code == 2
    assert "issue_number is required" in err


def test_issue_task_bad_vikunja_id_is_clean_error(tmp_path, capsys, monkeypatch):
    _redirect(tmp_path, monkeypatch)
    # A non-int, non-'-' task id must exit 2 cleanly (not raise ValueError).
    code, out, err = _run(["n.md", "42", "not-an-int"], capsys)
    assert code == 2
    assert "must be an integer" in err
