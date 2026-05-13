"""Tests for scripts/inbox/handle_marker_cleanup.py (WP01).

Drives the helper end-to-end via `subprocess.run`. The wrapped library
function `strip_marker` is stubbed via a shim module that is placed where
sys.path[0] (the helper's script directory) will find it first.

Covers FR-002 (single helper for Step 5a), FR-005 (per-entry failure
isolation), and the strip-success / strip-failure log emissions.
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
HELPER_SRC = SCRIPTS_INBOX / "handle_marker_cleanup.py"


def _write_log_action_stub(tmp_path: Path) -> Path:
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
    strip_fails_for: tuple[str, ...] = (),
) -> Path:
    """Write a stub strip_parse_error_marker.py into shim_dir.

    `strip_fails_for`: tuple of absolute paths for which strip_marker should
    raise. All others succeed (truncate the file to '' to simulate a strip).
    """
    shim = tmp_path / "shim"
    shim.mkdir()

    fail_paths_repr = repr(set(strip_fails_for))
    (shim / "strip_parse_error_marker.py").write_text(
        textwrap.dedent(
            f"""\
            from pathlib import Path

            FAIL_PATHS = {fail_paths_repr}
            MARKER_PREFIX = "> [!error] felix-capture:"

            def strip_marker(path):
                p = Path(path)
                if str(p) in FAIL_PATHS:
                    raise RuntimeError(f"stub-induced strip failure for {{p}}")
                # Simulate strip: remove any line starting with MARKER_PREFIX.
                if not p.exists():
                    raise RuntimeError(f"file not found: {{p}}")
                text = p.read_text(encoding="utf-8")
                kept = [
                    ln for ln in text.splitlines()
                    if not ln.startswith(MARKER_PREFIX)
                ]
                p.write_text("\\n".join(kept) + ("\\n" if text.endswith("\\n") else ""), encoding="utf-8")
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
) -> subprocess.CompletedProcess:
    helper_copy = shim_dir / "handle_marker_cleanup.py"
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


def test_empty_marker_cleanup_exits_zero(tmp_path: Path):
    prescan = tmp_path / "prescan.json"
    prescan.write_text(
        json.dumps({"marker_cleanup_needed": []}), encoding="utf-8"
    )
    log_bin = _write_log_action_stub(tmp_path)
    log_out = tmp_path / "log.jsonl"
    shim = _write_stub_modules(tmp_path)

    result = _run_helper(
        prescan, shim_dir=shim, log_action_bin=log_bin, log_action_out=log_out
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == ""
    assert _read_log_entries(log_out) == []


def test_all_strips_succeed(tmp_path: Path):
    notes = []
    for i in range(3):
        n = tmp_path / f"note{i}.md"
        n.write_text(
            "> [!error] felix-capture: stale marker.\nbody.\n", encoding="utf-8"
        )
        notes.append(n)
    prescan = tmp_path / "prescan.json"
    prescan.write_text(
        json.dumps(
            {
                "marker_cleanup_needed": [
                    {"path": str(n), "issue_number": 100 + i}
                    for i, n in enumerate(notes)
                ]
            }
        ),
        encoding="utf-8",
    )
    log_bin = _write_log_action_stub(tmp_path)
    log_out = tmp_path / "log.jsonl"
    shim = _write_stub_modules(tmp_path)

    result = _run_helper(
        prescan, shim_dir=shim, log_action_bin=log_bin, log_action_out=log_out
    )
    assert result.returncode == 0, result.stderr
    entries = _read_log_entries(log_out)
    actions = [e["action"] for e in entries]
    assert actions.count("marker_stripped") == 3
    assert "marker_cleanup_error" not in actions
    # All three notes should have the marker stripped.
    for n in notes:
        text = n.read_text(encoding="utf-8")
        assert "felix-capture:" not in text
    # Issue numbers from prescan entries flow into the log context.
    stripped_issue_numbers = sorted(
        e["context"]["issue_number"]
        for e in entries
        if e["action"] == "marker_stripped"
    )
    assert stripped_issue_numbers == [100, 101, 102]


def test_partial_strip_failure(tmp_path: Path):
    notes = []
    for i in range(3):
        n = tmp_path / f"note{i}.md"
        n.write_text(
            "> [!error] felix-capture: stale.\nbody.\n", encoding="utf-8"
        )
        notes.append(n)
    prescan = tmp_path / "prescan.json"
    prescan.write_text(
        json.dumps(
            {
                "marker_cleanup_needed": [
                    {"path": str(n), "issue_number": None} for n in notes
                ]
            }
        ),
        encoding="utf-8",
    )
    log_bin = _write_log_action_stub(tmp_path)
    log_out = tmp_path / "log.jsonl"
    # Fail the middle entry.
    shim = _write_stub_modules(tmp_path, strip_fails_for=(str(notes[1]),))

    result = _run_helper(
        prescan, shim_dir=shim, log_action_bin=log_bin, log_action_out=log_out
    )
    assert result.returncode == 1
    assert str(notes[1]) in result.stderr
    entries = _read_log_entries(log_out)
    actions = [e["action"] for e in entries]
    assert actions.count("marker_stripped") == 2
    assert actions.count("marker_cleanup_error") == 1
    err_entry = next(
        e for e in entries if e["action"] == "marker_cleanup_error"
    )
    assert err_entry["context"]["source_file"] == str(notes[1])
