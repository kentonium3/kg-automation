"""Tests for scripts.trust.completion_assertion (#683, WP03).

All tests point FELIX_TRUST_ASSERTIONS_DIR at a tmpdir — no office2 calls.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.trust import completion_assertion as ca


@pytest.fixture(autouse=True)
def _isolated_assertions_dir(tmp_path, monkeypatch):
    monkeypatch.setenv(ca.ASSERTIONS_DIR_ENV, str(tmp_path))
    return tmp_path


def _read_lines(tmp_path: Path) -> list[dict]:
    files = sorted(tmp_path.glob("*.jsonl"))
    assert len(files) == 1, f"expected exactly one ledger file, found {files}"
    lines = [json.loads(line) for line in files[0].read_text().splitlines() if line.strip()]
    return lines


# --- assertions_dir ----------------------------------------------------------


def test_assertions_dir_uses_env_override(tmp_path):
    assert ca.assertions_dir() == tmp_path


def test_assertions_dir_default_when_unset(monkeypatch):
    monkeypatch.delenv(ca.ASSERTIONS_DIR_ENV, raising=False)
    assert ca.assertions_dir() == Path(ca.DEFAULT_ASSERTIONS_DIR)


# --- record_assertion: roundtrip --------------------------------------------


def test_record_assertion_roundtrip(tmp_path):
    ok = ca.record_assertion(
        agent="main",
        artifact_kind="vikunja_task",
        artifact_ids=["91"],
        claim="Created Vikunja task #38",
        request_ref=None,
    )
    assert ok is True

    records = _read_lines(tmp_path)
    assert len(records) == 1
    record = records[0]
    assert record["agent"] == "main"
    assert record["artifact_kind"] == "vikunja_task"
    assert record["artifact_ids"] == ["91"]
    assert isinstance(record["artifact_ids"], list)
    assert record["claim"] == "Created Vikunja task #38"
    assert record["request_ref"] is None
    assert "ts" in record and record["ts"]


def test_record_assertion_multi_artifact_seven_ids(tmp_path):
    # The motivating case: one request creates 7 Vikunja reminder tasks.
    seven_ids = [str(91 + i) for i in range(7)]
    ok = ca.record_assertion(
        agent="main",
        artifact_kind="vikunja_task",
        artifact_ids=seven_ids,
        claim="Created 7 Vikunja reminder tasks",
    )
    assert ok is True

    records = _read_lines(tmp_path)
    assert records[0]["artifact_ids"] == seven_ids
    assert len(records[0]["artifact_ids"]) == 7


def test_record_assertion_appends_multiple_records(tmp_path):
    ca.record_assertion(agent="main", artifact_kind="vikunja_task", artifact_ids=["1"], claim="a")
    ca.record_assertion(agent="main", artifact_kind="vikunja_task", artifact_ids=["2"], claim="b")
    records = _read_lines(tmp_path)
    assert len(records) == 2
    assert records[0]["artifact_ids"] == ["1"]
    assert records[1]["artifact_ids"] == ["2"]


def test_record_assertion_preserves_optional_fields(tmp_path):
    ca.record_assertion(
        agent="calendar-agent",
        artifact_kind="calendar_event",
        artifact_ids=["evt-1"],
        claim="Created event",
        request_ref="req-123",
        request_summary="schedule a meeting",
    )
    record = _read_lines(tmp_path)[0]
    assert record["request_ref"] == "req-123"
    assert record["request_summary"] == "schedule a meeting"


# --- record_assertion: fail-safe --------------------------------------------


def test_record_assertion_write_failure_returns_false_and_does_not_raise(monkeypatch):
    def _boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(ca, "_append_line", _boom)
    # Must not raise.
    result = ca.record_assertion(
        agent="main", artifact_kind="vikunja_task", artifact_ids=["1"], claim="x"
    )
    assert result is False


def test_record_assertion_unwritable_dir_returns_false(tmp_path, monkeypatch):
    # Point the ledger dir at a path that can't be created (a file, not a dir).
    blocked = tmp_path / "not_a_dir"
    blocked.write_text("i am a file")
    monkeypatch.setenv(ca.ASSERTIONS_DIR_ENV, str(blocked / "sub"))
    result = ca.record_assertion(
        agent="main", artifact_kind="vikunja_task", artifact_ids=["1"], claim="x"
    )
    assert result is False


def test_record_assertion_swallows_arbitrary_exception(monkeypatch):
    def _boom():
        raise RuntimeError("boom")

    monkeypatch.setattr(ca, "assertions_dir", _boom)
    assert ca.record_assertion(agent="a", artifact_kind="other", artifact_ids=["1"], claim="c") is False


# --- CLI ---------------------------------------------------------------------


def test_cli_repeated_artifact_id_collected(tmp_path, capsys):
    rc = ca.main(
        [
            "--agent", "main",
            "--artifact-kind", "vikunja_task",
            "--artifact-id", "91",
            "--artifact-id", "92",
            "--claim", "Created two tasks",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "91" in out and "92" in out

    records = _read_lines(tmp_path)
    assert records[0]["artifact_ids"] == ["91", "92"]


def test_cli_forced_failure_returns_nonzero_without_raising(monkeypatch, capsys):
    monkeypatch.setattr(ca, "record_assertion", lambda **_kwargs: False)
    rc = ca.main(
        [
            "--agent", "main",
            "--artifact-kind", "vikunja_task",
            "--artifact-id", "1",
            "--claim", "x",
        ]
    )
    assert rc == 1
    assert "ERROR" in capsys.readouterr().err


def test_cli_never_raises_on_unexpected_exception(monkeypatch, capsys):
    def _boom(**_kwargs):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(ca, "record_assertion", _boom)
    rc = ca.main(
        [
            "--agent", "main",
            "--artifact-kind", "vikunja_task",
            "--artifact-id", "1",
            "--claim", "x",
        ]
    )
    assert rc == 1
    assert "ERROR" in capsys.readouterr().err


def test_cli_missing_required_arg_exits_nonzero_via_argparse():
    with pytest.raises(SystemExit):
        ca.main(["--agent", "main"])
