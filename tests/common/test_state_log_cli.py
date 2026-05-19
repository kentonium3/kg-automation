"""Tests for the ``python3 -m scripts.common.state_log`` CLI surface.

Spawns the CLI via ``subprocess.run`` so we exercise the real argparse
parser, stdin pipe, exit codes (0/1/2/3), and stdout/stderr split
contracted in ``contracts/cli.md``.

Isolation:
- The child process can't see the parent's monkey-patched
  ``STATE_DIR``. Instead each test sets ``FELIX_STATE_LOG_DIR`` in the
  subprocess environment so the child reads the temp directory via the
  env-var override wired into the module.
- ``PYTHONPATH`` is set to the repo root so the spawned interpreter can
  ``import scripts.common.state_log`` without an installed package.

Production ``/data/services/openclaw/state`` is never touched — verified
by the env-var override and by a defensive assertion at the end.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _run_cli(
    args: list[str],
    *,
    stdin: str | None = None,
    state_dir: Path | None = None,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Spawn ``python -m scripts.common.state_log`` with the given args.

    All tests funnel through this helper so the env wiring is consistent.
    """
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    if state_dir is not None:
        env["FELIX_STATE_LOG_DIR"] = str(state_dir)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-m", "scripts.common.state_log", *args],
        input=stdin,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.fixture
def isolated_state_dir(tmp_path):
    """Return a tmp state directory for CLI subprocess isolation."""
    return tmp_path / "state"


@pytest.fixture
def good_habits_record_json(good_habits_record):
    """JSON-encoded good_habits_record for piping to the CLI."""
    return json.dumps(good_habits_record)


# ---------------------------------------------------------------------------
# append — exit code 0 (happy path)
# ---------------------------------------------------------------------------

def test_cli_append_writes_record(
    isolated_state_dir, good_habits_record, good_habits_record_json
):
    result = _run_cli(
        ["append", "--domain", "habits"],
        stdin=good_habits_record_json,
        state_dir=isolated_state_dir,
    )
    assert result.returncode == 0, (
        f"expected exit 0, got {result.returncode}; "
        f"stderr={result.stderr!r}"
    )
    assert result.stdout == "", "append produces no stdout on success"

    path = isolated_state_dir / "habits-history.jsonl"
    assert path.exists()
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed == good_habits_record


def test_cli_append_idempotent_dedup(
    isolated_state_dir, good_habits_record_json
):
    """Second append of the same record is still exit 0 and no duplicate."""
    for _ in range(2):
        result = _run_cli(
            ["append", "--domain", "habits"],
            stdin=good_habits_record_json,
            state_dir=isolated_state_dir,
        )
        assert result.returncode == 0, result.stderr

    path = isolated_state_dir / "habits-history.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1


# ---------------------------------------------------------------------------
# append — exit code 1 (validation failure)
# ---------------------------------------------------------------------------

def test_cli_append_validation_failure_exits_1(
    isolated_state_dir, good_habits_record
):
    """Missing required field → exit 1, stderr names the field."""
    bad = dict(good_habits_record)
    del bad["task_id"]
    result = _run_cli(
        ["append", "--domain", "habits"],
        stdin=json.dumps(bad),
        state_dir=isolated_state_dir,
    )
    assert result.returncode == 1, (
        f"expected exit 1, got {result.returncode}; stderr={result.stderr!r}"
    )
    assert "task_id" in result.stderr


def test_cli_append_invalid_state_exits_1(
    isolated_state_dir, good_habits_record
):
    """Domain enum violation → exit 1."""
    bad = dict(good_habits_record)
    bad["state"] = "Complete"  # capitalization mismatch
    result = _run_cli(
        ["append", "--domain", "habits"],
        stdin=json.dumps(bad),
        state_dir=isolated_state_dir,
    )
    assert result.returncode == 1
    assert "Complete" in result.stderr or "state" in result.stderr


def test_cli_append_mismatched_domain_exits_1(
    isolated_state_dir, good_habits_record
):
    """Record domain ≠ --domain arg → exit 1."""
    # good_habits_record has domain="habits"; call with --domain escalation.
    # argparse will accept "escalation" (it's a valid choice); the library
    # will reject the mismatch.
    record = dict(good_habits_record)
    result = _run_cli(
        ["append", "--domain", "escalation"],
        stdin=json.dumps(record),
        state_dir=isolated_state_dir,
    )
    assert result.returncode == 1
    assert "habits" in result.stderr and "escalation" in result.stderr


# ---------------------------------------------------------------------------
# append — exit code 3 (input handling: bad/empty stdin, bad domain)
# ---------------------------------------------------------------------------

def test_cli_append_bad_json_exits_3(isolated_state_dir):
    result = _run_cli(
        ["append", "--domain", "habits"],
        stdin="not valid json",
        state_dir=isolated_state_dir,
    )
    assert result.returncode == 3, (
        f"expected exit 3, got {result.returncode}; stderr={result.stderr!r}"
    )
    assert "JSON" in result.stderr or "json" in result.stderr.lower()


def test_cli_append_empty_stdin_exits_3(isolated_state_dir):
    result = _run_cli(
        ["append", "--domain", "habits"],
        stdin="",
        state_dir=isolated_state_dir,
    )
    assert result.returncode == 3
    assert "stdin" in result.stderr.lower() or "record" in result.stderr.lower()


def test_cli_append_whitespace_only_stdin_exits_3(isolated_state_dir):
    result = _run_cli(
        ["append", "--domain", "habits"],
        stdin="   \n\t  \n",
        state_dir=isolated_state_dir,
    )
    assert result.returncode == 3


def test_cli_append_json_array_exits_3(isolated_state_dir):
    """stdin must be a JSON object — an array (or scalar) is exit 3."""
    result = _run_cli(
        ["append", "--domain", "habits"],
        stdin="[1, 2, 3]",
        state_dir=isolated_state_dir,
    )
    assert result.returncode == 3


def test_cli_append_unknown_domain_exits_2(isolated_state_dir):
    """argparse choice violation exits 2 (argparse's own exit code)."""
    result = _run_cli(
        ["append", "--domain", "bogus"],
        stdin="{}",
        state_dir=isolated_state_dir,
    )
    # argparse exits 2 on argument errors.
    assert result.returncode == 2


# ---------------------------------------------------------------------------
# read — happy path
# ---------------------------------------------------------------------------

def _pre_populate(state_dir: Path, records: list[dict]) -> None:
    """Use the library directly (in this process) to seed records.

    Done via subprocess so the env-var STATE_DIR override applies; in the
    parent we'd otherwise touch the prod path.
    """
    for record in records:
        result = subprocess.run(
            [sys.executable, "-m", "scripts.common.state_log",
             "append", "--domain", record["domain"]],
            input=json.dumps(record),
            env={**os.environ,
                 "PYTHONPATH": str(REPO_ROOT),
                 "FELIX_STATE_LOG_DIR": str(state_dir)},
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"seed failed: {result.stderr!r}"
        )


def test_cli_read_returns_records(isolated_state_dir, good_habits_record):
    """Read returns each record as one JSON line on stdout, exit 0."""
    record2 = dict(good_habits_record)
    record2["task_id"] = 15
    record2["title"] = "Walk 30 min"
    _pre_populate(isolated_state_dir, [good_habits_record, record2])

    result = _run_cli(
        ["read", "--domain", "habits"],
        state_dir=isolated_state_dir,
    )
    assert result.returncode == 0, result.stderr
    lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
    assert len(lines) == 2
    parsed = [json.loads(ln) for ln in lines]
    assert [r["task_id"] for r in parsed] == [14, 15]


def test_cli_read_empty_when_no_records(isolated_state_dir):
    """No file yet → exit 0, empty stdout."""
    result = _run_cli(
        ["read", "--domain", "habits"],
        state_dir=isolated_state_dir,
    )
    assert result.returncode == 0
    assert result.stdout == ""


def test_cli_read_with_task_id_filter(isolated_state_dir, good_habits_record):
    """--task-id N returns only the matching record."""
    r14 = good_habits_record
    r15 = dict(good_habits_record)
    r15["task_id"] = 15
    r17 = dict(good_habits_record)
    r17["task_id"] = 17
    _pre_populate(isolated_state_dir, [r14, r15, r17])

    result = _run_cli(
        ["read", "--domain", "habits", "--task-id", "15"],
        state_dir=isolated_state_dir,
    )
    assert result.returncode == 0, result.stderr
    lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
    assert len(lines) == 1
    assert json.loads(lines[0])["task_id"] == 15


def test_cli_read_with_state_filter(isolated_state_dir, good_habits_record):
    r14_done = good_habits_record
    r15_skip = dict(good_habits_record)
    r15_skip["task_id"] = 15
    r15_skip["state"] = "skipped"
    _pre_populate(isolated_state_dir, [r14_done, r15_skip])

    result = _run_cli(
        ["read", "--domain", "habits", "--state", "skipped"],
        state_dir=isolated_state_dir,
    )
    assert result.returncode == 0
    lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
    assert len(lines) == 1
    assert json.loads(lines[0])["state"] == "skipped"


def test_cli_read_with_date_range(isolated_state_dir, good_habits_record):
    early = dict(good_habits_record)
    early["date"] = "2026-05-17"
    early["timestamp"] = "2026-05-17T11:00:00+00:00"
    mid = dict(good_habits_record)
    mid["task_id"] = 15
    mid["date"] = "2026-05-18"
    mid["timestamp"] = "2026-05-18T11:00:00+00:00"
    late = dict(good_habits_record)
    late["task_id"] = 16
    late["date"] = "2026-05-19"
    late["timestamp"] = "2026-05-19T11:00:00+00:00"
    _pre_populate(isolated_state_dir, [early, mid, late])

    result = _run_cli(
        [
            "read", "--domain", "habits",
            "--date-from", "2026-05-18",
            "--date-to", "2026-05-19",
        ],
        state_dir=isolated_state_dir,
    )
    assert result.returncode == 0
    lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
    dates = sorted(json.loads(ln)["date"] for ln in lines)
    assert dates == ["2026-05-18", "2026-05-19"]


# ---------------------------------------------------------------------------
# read — error paths
# ---------------------------------------------------------------------------

def test_cli_read_unknown_domain_exits_2(isolated_state_dir):
    """Unknown --domain → argparse choice violation → exit 2."""
    # argparse rejects this before our code runs.
    result = _run_cli(
        ["read", "--domain", "bogus"],
        state_dir=isolated_state_dir,
    )
    assert result.returncode == 2


# ---------------------------------------------------------------------------
# --help — exit 0 on all variants
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("args", [["--help"], ["append", "--help"], ["read", "--help"]])
def test_cli_help_exits_0(args):
    result = _run_cli(args)
    assert result.returncode == 0, (
        f"--help should exit 0; got {result.returncode}, "
        f"stderr={result.stderr!r}"
    )
    assert result.stdout, "--help should print to stdout"


# ---------------------------------------------------------------------------
# No subcommand → print help to stderr and exit 3.
# ---------------------------------------------------------------------------

def test_cli_no_subcommand_exits_3(isolated_state_dir):
    result = _run_cli([], state_dir=isolated_state_dir)
    assert result.returncode == 3


# ---------------------------------------------------------------------------
# Safety pin.
# ---------------------------------------------------------------------------

def test_cli_tests_isolate_via_env_var(isolated_state_dir):
    """Defensive: production state path is never the FELIX_STATE_LOG_DIR target."""
    assert "/data/services/openclaw/state" not in str(isolated_state_dir)


# ---------------------------------------------------------------------------
# In-process CLI tests (call main() directly).
#
# Subprocess tests above validate the wire protocol (exit codes, env
# isolation). These tests call ``state_log.main()`` in-process so the
# coverage tool can attribute hits to the CLI dispatch and option-parsing
# branches without needing coverage-in-subprocesses plumbing.
# ---------------------------------------------------------------------------

import io  # noqa: E402

from scripts.common import state_log  # noqa: E402


def test_main_append_in_process(monkeypatch, capsys, tmp_path, good_habits_record):
    """main(['append', ...]) reads stdin and appends to the patched STATE_DIR."""
    state_dir = tmp_path / "state"
    monkeypatch.setattr("scripts.common.state_log.STATE_DIR", state_dir)
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(good_habits_record)))
    rc = state_log.main(["append", "--domain", "habits"])
    assert rc == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    path = state_dir / "habits-history.jsonl"
    assert path.exists()


def test_main_append_validation_failure_in_process(
    monkeypatch, capsys, tmp_path, good_habits_record
):
    state_dir = tmp_path / "state"
    monkeypatch.setattr("scripts.common.state_log.STATE_DIR", state_dir)
    bad = dict(good_habits_record)
    del bad["task_id"]
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(bad)))
    rc = state_log.main(["append", "--domain", "habits"])
    assert rc == 1
    captured = capsys.readouterr()
    assert "task_id" in captured.err


def test_main_append_bad_json_in_process(monkeypatch, capsys, tmp_path):
    state_dir = tmp_path / "state"
    monkeypatch.setattr("scripts.common.state_log.STATE_DIR", state_dir)
    monkeypatch.setattr("sys.stdin", io.StringIO("not valid json"))
    rc = state_log.main(["append", "--domain", "habits"])
    assert rc == 3
    captured = capsys.readouterr()
    assert "JSON" in captured.err or "json" in captured.err.lower()


def test_main_append_empty_stdin_in_process(monkeypatch, capsys, tmp_path):
    state_dir = tmp_path / "state"
    monkeypatch.setattr("scripts.common.state_log.STATE_DIR", state_dir)
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    rc = state_log.main(["append", "--domain", "habits"])
    assert rc == 3
    captured = capsys.readouterr()
    assert "stdin" in captured.err.lower() or "record" in captured.err.lower()


def test_main_append_non_object_stdin_in_process(monkeypatch, capsys, tmp_path):
    state_dir = tmp_path / "state"
    monkeypatch.setattr("scripts.common.state_log.STATE_DIR", state_dir)
    monkeypatch.setattr("sys.stdin", io.StringIO("[1, 2, 3]"))
    rc = state_log.main(["append", "--domain", "habits"])
    assert rc == 3
    captured = capsys.readouterr()
    assert "object" in captured.err.lower()


def test_main_read_in_process(monkeypatch, capsys, tmp_path, good_habits_record):
    """main(['read', ...]) prints filtered records to stdout."""
    state_dir = tmp_path / "state"
    monkeypatch.setattr("scripts.common.state_log.STATE_DIR", state_dir)
    state_log.append("habits", good_habits_record)
    rc = state_log.main(["read", "--domain", "habits"])
    assert rc == 0
    captured = capsys.readouterr()
    lines = [ln for ln in captured.out.splitlines() if ln.strip()]
    assert len(lines) == 1
    assert json.loads(lines[0]) == good_habits_record


def test_main_read_with_all_filters_in_process(
    monkeypatch, capsys, tmp_path, good_habits_record
):
    """Exercise every CLI read filter flag together."""
    state_dir = tmp_path / "state"
    monkeypatch.setattr("scripts.common.state_log.STATE_DIR", state_dir)
    state_log.append("habits", good_habits_record)
    rc = state_log.main([
        "read", "--domain", "habits",
        "--task-id", "14",
        "--date", "2026-05-19",
        "--date-from", "2026-05-19",
        "--date-to", "2026-05-19",
        "--state", "complete",
        "--source", "whatsapp",
    ])
    assert rc == 0
    captured = capsys.readouterr()
    lines = [ln for ln in captured.out.splitlines() if ln.strip()]
    assert len(lines) == 1
    assert json.loads(lines[0])["task_id"] == 14


def test_main_no_subcommand_in_process(monkeypatch, capsys, tmp_path):
    """No subcommand prints help to stderr and returns 3."""
    state_dir = tmp_path / "state"
    monkeypatch.setattr("scripts.common.state_log.STATE_DIR", state_dir)
    rc = state_log.main([])
    assert rc == 3
    captured = capsys.readouterr()
    assert captured.err  # help text printed to stderr
