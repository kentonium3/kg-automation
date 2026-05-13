"""Tests for scripts/inbox/file_inbox_quality_issue.py (WP04).

Covers FR-006 (batched issue), FR-007 (title-prefix dedup), and the
command-line surface. All gh subprocess calls are mocked.
"""
from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import file_inbox_quality_issue as W


# ---------- Pure helpers (no subprocess) ----------


def test_build_title_format_stable():
    assert (
        W.build_title(3, "2026-05-12")
        == "Inbox quality: 3 notes with parse errors — 2026-05-12"
    )


def test_build_title_uses_module_constant_prefix():
    """Title MUST start with the module constant — dedup depends on it."""
    title = W.build_title(7, "2026-01-01")
    assert title.startswith(W.INBOX_QUALITY_TITLE_PREFIX + " ")


def test_build_body_includes_each_parse_failure_row():
    pfs = [
        {"path": "/home/kgale/second-brain/notes/01-Inbox/a.md", "reason": "BOM"},
        {"path": "/home/kgale/second-brain/notes/01-Inbox/b.md", "reason": "missing close"},
    ]
    body = W.build_body(pfs, "2026-05-12")
    assert "| `a.md` | BOM |" in body
    assert "| `b.md` | missing close |" in body
    assert "encountered 2 notes" in body


def test_build_body_includes_activity_log_path():
    body = W.build_body([{"path": "x.md", "reason": "y"}], "2026-05-12")
    assert "inbox-processing-2026-05-12.md" in body


def test_build_body_escapes_pipe_in_reason():
    pfs = [{"path": "z.md", "reason": "got | this | mess"}]
    body = W.build_body(pfs, "2026-05-12")
    # the literal `|` characters in reason text must be escaped so the
    # table doesn't shatter
    assert "got \\| this \\| mess" in body


def test_build_body_truncates_when_table_exceeds_max(monkeypatch):
    """Codex WP04 review [P3]: a parse_failures batch large enough to
    produce a body over MAX_BODY_CHARS must be truncated with an
    `... and N more` footer rather than blowing past `gh issue create`'s
    body limit. Force a tight limit so we can exercise the path without
    constructing 1000+ failures.
    """
    monkeypatch.setattr(W, "MAX_BODY_CHARS", 2000)
    pfs = [
        {"path": f"note-{i:03d}.md", "reason": "BOM"} for i in range(120)
    ]
    body = W.build_body(pfs, "2026-05-12")
    assert len(body) <= W.MAX_BODY_CHARS
    # Total count in prose still reflects the full batch.
    assert "encountered 120 notes" in body
    # Some rows must be kept.
    assert "| `note-000.md` | BOM |" in body
    # The footer must indicate how many were dropped.
    import re as _re
    m = _re.search(r"… and (\d+) more", body)
    assert m is not None
    dropped = int(m.group(1))
    assert dropped > 0
    # Sanity: a row near the end of the original list should NOT be in
    # the truncated body (we drop from the tail).
    assert "| `note-119.md` | BOM |" not in body


def test_build_body_short_batch_no_truncation_footer():
    body = W.build_body([{"path": "a.md", "reason": "BOM"}], "2026-05-12")
    assert "and " not in body or "more" not in body.split("and ")[-1].split("more")[0] or "encountered 1 notes" in body
    # Easier assertion: the truncation footer should not appear.
    assert "… and " not in body


def test_parse_issue_number_from_url():
    assert (
        W._parse_issue_number_from_url(
            "https://github.com/kentonium3/kg-automation/issues/482"
        )
        == 482
    )


def test_parse_issue_number_from_url_raises_on_garbage():
    with pytest.raises(RuntimeError):
        W._parse_issue_number_from_url("totally bogus output")


# ---------- find_existing_open_issue (subprocess mocked) ----------


def _stub_run_factory(stdout: str, returncode: int = 0):
    """Return a stub function for subprocess.run that returns one result."""
    def _stub(*args, **kwargs):
        if returncode != 0:
            raise subprocess.CalledProcessError(
                returncode, args[0], output=stdout, stderr="boom"
            )
        return subprocess.CompletedProcess(
            args=args[0], returncode=0, stdout=stdout, stderr=""
        )
    return _stub


def test_find_existing_returns_none_when_no_matches(monkeypatch):
    monkeypatch.setattr(W.subprocess, "run", _stub_run_factory("[]"))
    assert W.find_existing_open_issue() is None


def test_find_existing_returns_number_for_prefix_match(monkeypatch):
    payload = json.dumps([
        {"number": 999, "title": "Inbox quality: 3 notes with parse errors — 2026-05-12"},
    ])
    monkeypatch.setattr(W.subprocess, "run", _stub_run_factory(payload))
    assert W.find_existing_open_issue() == 999


def test_find_existing_post_filters_fuzzy_match(monkeypatch):
    """gh's `in:title` is fuzzy — `"Some inbox quality concerns..."` may
    come back. The startswith() post-filter must reject it.
    """
    payload = json.dumps([
        {"number": 500, "title": "Some inbox quality concerns about ..."},
    ])
    monkeypatch.setattr(W.subprocess, "run", _stub_run_factory(payload))
    assert W.find_existing_open_issue() is None


def test_find_existing_picks_first_prefix_match_among_mixed(monkeypatch):
    payload = json.dumps([
        {"number": 500, "title": "Some inbox quality concerns..."},  # fuzzy
        {"number": 600, "title": "Inbox quality: 2 notes with parse errors — 2026-05-11"},  # match
        {"number": 700, "title": "Inbox quality: 5 notes with parse errors — 2026-05-12"},  # match
    ])
    monkeypatch.setattr(W.subprocess, "run", _stub_run_factory(payload))
    assert W.find_existing_open_issue() == 600  # first match wins


def test_find_existing_raises_on_gh_failure(monkeypatch):
    monkeypatch.setattr(W.subprocess, "run", _stub_run_factory("", returncode=1))
    with pytest.raises(RuntimeError, match="gh issue list failed"):
        W.find_existing_open_issue()


def test_find_existing_raises_on_non_json(monkeypatch):
    monkeypatch.setattr(W.subprocess, "run", _stub_run_factory("not json"))
    with pytest.raises(RuntimeError, match="non-JSON"):
        W.find_existing_open_issue()


# ---------- file_new_issue (subprocess mocked) ----------


def test_file_new_issue_returns_parsed_issue_number(monkeypatch):
    stub_stdout = "https://github.com/kentonium3/kg-automation/issues/482\n"
    monkeypatch.setattr(W.subprocess, "run", _stub_run_factory(stub_stdout))
    n = W.file_new_issue(
        [{"path": "a.md", "reason": "BOM"}], "2026-05-12"
    )
    assert n == 482


def test_file_new_issue_command_line_shape(monkeypatch):
    calls = []

    def _capture(*args, **kwargs):
        calls.append({"args": list(args[0]), "kwargs": kwargs})
        return subprocess.CompletedProcess(
            args=args[0], returncode=0,
            stdout="https://github.com/kentonium3/kg-automation/issues/1\n",
            stderr="",
        )

    monkeypatch.setattr(W.subprocess, "run", _capture)
    W.file_new_issue(
        [{"path": "a.md", "reason": "BOM"}, {"path": "b.md", "reason": "yaml"}],
        "2026-05-12",
    )
    argv = calls[0]["args"]
    # Core shape
    assert argv[:3] == ["gh", "issue", "create"]
    assert "--repo" in argv
    assert argv[argv.index("--repo") + 1] == W.DEFAULT_REPO
    assert "--title" in argv
    assert (
        argv[argv.index("--title") + 1]
        == "Inbox quality: 2 notes with parse errors — 2026-05-12"
    )
    assert "--body" in argv
    body = argv[argv.index("--body") + 1]
    assert "| `a.md` | BOM |" in body
    assert "| `b.md` | yaml |" in body
    assert "--label" in argv
    assert argv[argv.index("--label") + 1] == W.DEFAULT_LABEL
    assert "--assignee" in argv
    assert argv[argv.index("--assignee") + 1] == W.DEFAULT_ASSIGNEE


def test_file_new_issue_raises_on_gh_failure(monkeypatch):
    monkeypatch.setattr(W.subprocess, "run", _stub_run_factory("", returncode=1))
    with pytest.raises(RuntimeError, match="gh issue create failed"):
        W.file_new_issue([{"path": "a.md", "reason": "x"}], "2026-05-12")


# ---------- main() (CLI surface) ----------


def test_main_empty_parse_failures_is_noop(monkeypatch, capsys):
    """Empty list must NOT call gh at all and must exit 0."""
    calls = []

    def _no_calls(*args, **kwargs):
        calls.append(args)
        raise AssertionError("subprocess.run should not be invoked for empty input")

    monkeypatch.setattr(W.subprocess, "run", _no_calls)
    rc = W.main(["--parse-failures", "[]", "--date", "2026-05-12"])
    assert rc == 0
    assert calls == []


def test_main_invalid_json_returns_exit_1(monkeypatch, capsys):
    rc = W.main(["--parse-failures", "{not json}", "--date", "2026-05-12"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "could not parse --parse-failures" in err


def test_main_non_list_input_returns_exit_1(capsys):
    rc = W.main(["--parse-failures", '{"path": "x.md", "reason": "y"}'])
    assert rc == 1
    err = capsys.readouterr().err
    assert "must decode to a list" in err


def test_main_existing_issue_prints_number_no_create_call(monkeypatch, capsys):
    """Dedup hit → print existing number, do NOT call gh issue create."""
    calls = []

    def _run(*args, **kwargs):
        calls.append(list(args[0]))
        # First call: gh issue list returns one prefix match.
        if "list" in args[0]:
            return subprocess.CompletedProcess(
                args=args[0], returncode=0,
                stdout=json.dumps([{
                    "number": 314,
                    "title": "Inbox quality: 1 notes with parse errors — 2026-05-12",
                }]),
                stderr="",
            )
        # Should never reach here.
        raise AssertionError(f"unexpected gh subcommand: {args[0]}")

    monkeypatch.setattr(W.subprocess, "run", _run)
    rc = W.main([
        "--parse-failures", json.dumps([{"path": "a.md", "reason": "BOM"}]),
        "--date", "2026-05-12",
    ])
    assert rc == 0
    assert capsys.readouterr().out.strip() == "314"
    # Only ONE call was made — issue list. No create.
    assert len(calls) == 1
    assert "create" not in calls[0]


def test_main_no_existing_issue_files_new_and_prints_number(monkeypatch, capsys):
    """No existing → call gh issue list AND gh issue create."""
    seq = iter([
        # First: gh issue list → empty
        subprocess.CompletedProcess(args=[], returncode=0, stdout="[]", stderr=""),
        # Second: gh issue create → URL
        subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout="https://github.com/kentonium3/kg-automation/issues/777\n",
            stderr="",
        ),
    ])

    def _run(*args, **kwargs):
        return next(seq)

    monkeypatch.setattr(W.subprocess, "run", _run)
    rc = W.main([
        "--parse-failures",
        json.dumps([
            {"path": "/abs/a.md", "reason": "BOM"},
            {"path": "/abs/b.md", "reason": "yaml"},
        ]),
        "--date", "2026-05-12",
    ])
    assert rc == 0
    assert capsys.readouterr().out.strip() == "777"


def test_main_reads_at_file_input(monkeypatch, capsys, tmp_path):
    """`@<path>` reads JSON from a file."""
    payload_path = tmp_path / "failures.json"
    payload_path.write_text(
        json.dumps([{"path": "a.md", "reason": "BOM"}]), encoding="utf-8"
    )

    seq = iter([
        subprocess.CompletedProcess(args=[], returncode=0, stdout="[]", stderr=""),
        subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout="https://github.com/kentonium3/kg-automation/issues/55\n",
            stderr="",
        ),
    ])

    def _run(*args, **kwargs):
        return next(seq)

    monkeypatch.setattr(W.subprocess, "run", _run)
    rc = W.main(["--parse-failures", f"@{payload_path}", "--date", "2026-05-12"])
    assert rc == 0
    assert capsys.readouterr().out.strip() == "55"


def test_main_gh_failure_returns_exit_1(monkeypatch, capsys):
    monkeypatch.setattr(W.subprocess, "run", _stub_run_factory("", returncode=1))
    rc = W.main([
        "--parse-failures", json.dumps([{"path": "a.md", "reason": "x"}]),
        "--date", "2026-05-12",
    ])
    assert rc == 1
    assert "ERROR" in capsys.readouterr().err
