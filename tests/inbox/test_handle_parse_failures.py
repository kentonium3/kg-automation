"""Tests for scripts/inbox/handle_parse_failures.py (WP01).

Drives the helper end-to-end via `subprocess.run` so the CLI surface is
exercised. The wrapped library functions (`find_existing_open_issue`,
`file_new_issue`, `inject_marker`) are stubbed by injecting a sitecustomize-
style monkeypatch module at the front of `sys.path` for the subprocess.
`log_action.py` is replaced with a stub script that appends each invocation
to a JSONL file so the test can assert the action stream.

Covers FR-001 (single helper for Step 6), FR-003 (idempotent injection),
FR-004 (dedup branch), FR-005 (per-entry failure isolation), and FR-006
(stdout = issue number for downstream consumers).
"""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


SCRIPTS_INBOX = Path(__file__).resolve().parent.parent.parent / "scripts" / "inbox"
HELPER_SRC = SCRIPTS_INBOX / "handle_parse_failures.py"


def _write_log_action_stub(tmp_path: Path) -> Path:
    """Write a tiny python script that mimics log_action.py for tests.

    Appends one JSON line per invocation to LOG_ACTION_OUT (env var); exits 0
    so the helper treats logging as successful.
    """
    stub = tmp_path / "log_action_stub.py"
    stub.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            import argparse
            import json
            import os
            import sys

            p = argparse.ArgumentParser()
            p.add_argument("--agent", required=True)
            p.add_argument("--category", required=True)
            p.add_argument("--action", required=True)
            p.add_argument("--target", required=True)
            p.add_argument("--outcome", required=True)
            p.add_argument("--context", default=None)
            p.add_argument("--trace", default=None)
            args = p.parse_args()

            out_path = os.environ.get("LOG_ACTION_OUT")
            entry = {
                "agent": args.agent,
                "category": args.category,
                "action": args.action,
                "target": args.target,
                "outcome": args.outcome,
                "context": json.loads(args.context) if args.context else None,
            }
            if out_path:
                with open(out_path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(entry) + "\\n")
            sys.exit(0)
            """
        ),
        encoding="utf-8",
    )
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return stub


def _write_stub_modules(
    tmp_path: Path,
    *,
    existing_issue: int | None,
    new_issue_number: int | None,
    inject_marker_fails_for: tuple[str, ...] = (),
) -> Path:
    """Write replacement modules for file_inbox_quality_issue and
    inject_parse_error_marker into a shim dir, returning that dir so we can
    PYTHONPATH-prepend it for the subprocess.

    `existing_issue=None` causes find_existing_open_issue to return None and
    file_new_issue to return new_issue_number. `existing_issue=<int>` causes
    find_existing_open_issue to return that and file_new_issue to assert
    never-called.

    `inject_marker_fails_for` is a tuple of absolute paths for which the
    stub should raise RuntimeError; all others succeed (touch the file).
    """
    shim = tmp_path / "shim"
    shim.mkdir()

    (shim / "file_inbox_quality_issue.py").write_text(
        textwrap.dedent(
            f"""\
            EXISTING_ISSUE = {existing_issue!r}
            NEW_ISSUE_NUMBER = {new_issue_number!r}

            def find_existing_open_issue(repo=None):
                return EXISTING_ISSUE

            def file_new_issue(parse_failures, date_str, repo=None,
                               label=None, assignee=None):
                if EXISTING_ISSUE is not None:
                    raise AssertionError(
                        "file_new_issue called even though existing issue found"
                    )
                if NEW_ISSUE_NUMBER is None:
                    raise RuntimeError("stub: no NEW_ISSUE_NUMBER configured")
                return NEW_ISSUE_NUMBER
            """
        ),
        encoding="utf-8",
    )

    fail_paths_repr = repr(set(inject_marker_fails_for))
    (shim / "inject_parse_error_marker.py").write_text(
        textwrap.dedent(
            f"""\
            from pathlib import Path

            FAIL_PATHS = {fail_paths_repr}
            MARKER_PREFIX = "> [!error] felix-capture:"

            def inject_marker(path, issue_number, date_str):
                p = Path(path)
                if str(p) in FAIL_PATHS:
                    raise RuntimeError(f"stub-induced failure for {{p}}")
                # Append a tiny marker line so the test can assert "touched".
                text = p.read_text(encoding="utf-8") if p.exists() else ""
                marker = (
                    f"> [!error] felix-capture: stub marker issue=#"
                    f"{{issue_number}} date={{date_str}}"
                )
                if marker in text:
                    return False
                new_text = marker + "\\n" + text
                p.write_text(new_text, encoding="utf-8")
                return True
            """
        ),
        encoding="utf-8",
    )
    return shim


def _run_helper(
    prescan_path: Path,
    *,
    shim_dir: Path,
    log_action_bin: Path,
    log_action_out: Path,
    date: str = "2026-05-13",
) -> subprocess.CompletedProcess:
    # Copy the helper into the shim dir so its sys.path[0] (the script's
    # directory) IS the shim — guaranteeing the stub modules win over the
    # real `file_inbox_quality_issue` / `inject_parse_error_marker` in
    # scripts/inbox/. Without this, Python prepends the script's directory
    # to sys.path[0] and the real implementations would shadow the stubs.
    helper_copy = shim_dir / "handle_parse_failures.py"
    if not helper_copy.exists():
        shutil.copy2(HELPER_SRC, helper_copy)

    env = os.environ.copy()
    env["LOG_ACTION_PATH"] = str(log_action_bin)
    env["LOG_ACTION_OUT"] = str(log_action_out)
    return subprocess.run(
        [
            sys.executable,
            str(helper_copy),
            f"@{prescan_path}",
            "--date",
            date,
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _read_log_entries(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


# ---------- Tests ----------


def test_empty_parse_failures_exits_zero(tmp_path: Path):
    prescan = tmp_path / "prescan.json"
    prescan.write_text(json.dumps({"parse_failures": []}), encoding="utf-8")
    log_bin = _write_log_action_stub(tmp_path)
    log_out = tmp_path / "log.jsonl"
    shim = _write_stub_modules(
        tmp_path, existing_issue=None, new_issue_number=None
    )

    result = _run_helper(
        prescan, shim_dir=shim, log_action_bin=log_bin, log_action_out=log_out
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == ""
    assert _read_log_entries(log_out) == []


def test_single_parse_failure_full_success(tmp_path: Path):
    note = tmp_path / "note.md"
    note.write_text(
        "---\nstatus: unprocessed\n---\n\nBody.\n", encoding="utf-8"
    )
    prescan = tmp_path / "prescan.json"
    prescan.write_text(
        json.dumps(
            {
                "parse_failures": [
                    {"path": str(note), "reason": "missing close fence"}
                ]
            }
        ),
        encoding="utf-8",
    )
    log_bin = _write_log_action_stub(tmp_path)
    log_out = tmp_path / "log.jsonl"
    shim = _write_stub_modules(
        tmp_path, existing_issue=None, new_issue_number=123
    )

    result = _run_helper(
        prescan, shim_dir=shim, log_action_bin=log_bin, log_action_out=log_out
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "123"
    entries = _read_log_entries(log_out)
    actions = [e["action"] for e in entries]
    assert "inbox_quality_issue_filed" in actions
    assert "parse_error_marker_injected" in actions
    assert "inbox_quality_issue_deduped" not in actions
    # Marker stub prepended its sentinel line.
    text = note.read_text(encoding="utf-8")
    assert "stub marker issue=#123" in text
    # Action context carries the reason.
    inject_entry = next(
        e for e in entries if e["action"] == "parse_error_marker_injected"
    )
    assert inject_entry["context"]["reason"] == "missing close fence"
    assert inject_entry["context"]["issue_number"] == 123


def test_dedup_hit(tmp_path: Path):
    note = tmp_path / "note.md"
    note.write_text(
        "---\nstatus: unprocessed\n---\n\nBody.\n", encoding="utf-8"
    )
    prescan = tmp_path / "prescan.json"
    prescan.write_text(
        json.dumps(
            {"parse_failures": [{"path": str(note), "reason": "BOM"}]}
        ),
        encoding="utf-8",
    )
    log_bin = _write_log_action_stub(tmp_path)
    log_out = tmp_path / "log.jsonl"
    shim = _write_stub_modules(
        tmp_path, existing_issue=99, new_issue_number=None
    )

    result = _run_helper(
        prescan, shim_dir=shim, log_action_bin=log_bin, log_action_out=log_out
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "99"
    entries = _read_log_entries(log_out)
    actions = [e["action"] for e in entries]
    assert "inbox_quality_issue_deduped" in actions
    assert "inbox_quality_issue_filed" not in actions
    # Injection still happened, referencing the deduped issue number.
    assert "parse_error_marker_injected" in actions
    dedup_entry = next(
        e for e in entries if e["action"] == "inbox_quality_issue_deduped"
    )
    assert dedup_entry["context"]["issue_number"] == 99
    assert dedup_entry["context"]["parse_failure_count"] == 1


def test_partial_failure_exits_nonzero(tmp_path: Path):
    note_a = tmp_path / "a.md"
    note_b = tmp_path / "b.md"
    note_c = tmp_path / "c.md"
    for n in (note_a, note_b, note_c):
        n.write_text(
            "---\nstatus: unprocessed\n---\n\nBody.\n", encoding="utf-8"
        )
    prescan = tmp_path / "prescan.json"
    prescan.write_text(
        json.dumps(
            {
                "parse_failures": [
                    {"path": str(note_a), "reason": "BOM"},
                    {"path": str(note_b), "reason": "yaml"},
                    {"path": str(note_c), "reason": "missing close"},
                ]
            }
        ),
        encoding="utf-8",
    )
    log_bin = _write_log_action_stub(tmp_path)
    log_out = tmp_path / "log.jsonl"
    shim = _write_stub_modules(
        tmp_path,
        existing_issue=None,
        new_issue_number=200,
        inject_marker_fails_for=(str(note_b),),
    )

    result = _run_helper(
        prescan, shim_dir=shim, log_action_bin=log_bin, log_action_out=log_out
    )
    assert result.returncode == 1
    # stdout still contains the issue number on the first line.
    assert result.stdout.strip().splitlines()[0] == "200"
    # stderr summarizes the failed path.
    assert str(note_b) in result.stderr
    entries = _read_log_entries(log_out)
    actions = [e["action"] for e in entries]
    # Two injections succeeded; one failed.
    assert actions.count("parse_error_marker_injected") == 2
    assert actions.count("parse_failure_handling_error") == 1
    err_entry = next(
        e for e in entries if e["action"] == "parse_failure_handling_error"
    )
    assert err_entry["context"]["source_file"] == str(note_b)
    assert err_entry["context"]["issue_number"] == 200


def test_stdout_emits_issue_number(tmp_path: Path):
    note = tmp_path / "note.md"
    note.write_text(
        "---\nstatus: unprocessed\n---\n\nBody.\n", encoding="utf-8"
    )
    prescan = tmp_path / "prescan.json"
    prescan.write_text(
        json.dumps(
            {"parse_failures": [{"path": str(note), "reason": "BOM"}]}
        ),
        encoding="utf-8",
    )
    log_bin = _write_log_action_stub(tmp_path)
    log_out = tmp_path / "log.jsonl"
    shim = _write_stub_modules(
        tmp_path, existing_issue=None, new_issue_number=777
    )

    result = _run_helper(
        prescan, shim_dir=shim, log_action_bin=log_bin, log_action_out=log_out
    )
    assert result.returncode == 0, result.stderr
    # stdout is exactly the issue number followed by a newline; no other content.
    assert result.stdout == "777\n"
