#!/usr/bin/env python3
"""End-of-turn parse-failure orchestrator for felix-admin-capture.

Consolidates Step 6 of the felix-admin-capture AGENTS.md prompt into a
single command. Reads the prescan JSON (which lists `parse_failures`),
files (or dedups) the batched "Inbox quality" GitHub issue, then injects
the parse-error callout marker into each malformed note.

Per-entry actions are emitted to the canonical action log via
`log_action.py` (resolved relative to this script's location, overridable
with `LOG_ACTION_PATH` or `--log-action-bin`). Per-entry failures are
logged as `parse_failure_handling_error` and do not abort the rest; the
script exits 1 if any per-entry leg failed, 0 otherwise.

The underlying helpers (`file_inbox_quality_issue` and
`inject_parse_error_marker`) are imported as library functions; we do
NOT subprocess their CLI wrappers. See WP01 / issue #253 for context.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# `scripts/inbox/` is added to sys.path by tests/inbox/conftest.py; when this
# script runs standalone it is imported directly. Either way, the sibling
# modules resolve as top-level imports.
from file_inbox_quality_issue import (  # noqa: E402
    find_existing_open_issue,
    file_new_issue,
)
from inject_parse_error_marker import inject_marker  # noqa: E402


AGENT_NAME = "felix-admin-capture"


def _default_log_action_path() -> Path:
    """Resolve log_action.py relative to this script.

    `scripts/inbox/handle_parse_failures.py` →
    `scripts/openclaw/observation/log_action.py`.
    """
    return (
        Path(__file__).resolve().parent.parent
        / "openclaw"
        / "observation"
        / "log_action.py"
    )


def _resolve_log_action_path(cli_override: Optional[str]) -> Path:
    if cli_override:
        return Path(cli_override)
    env_override = os.environ.get("LOG_ACTION_PATH")
    if env_override:
        return Path(env_override)
    return _default_log_action_path()


def _emit_log_action(
    log_action_bin: Path,
    *,
    category: str,
    action: str,
    target: str,
    outcome: str,
    context: dict,
) -> None:
    """Subprocess-out to log_action.py. Logging-infra failure is logged to
    stderr but does NOT increment the work-item failure counter.
    """
    cmd = [
        "python3",
        str(log_action_bin),
        "--agent",
        AGENT_NAME,
        "--category",
        category,
        "--action",
        action,
        "--target",
        target,
        "--outcome",
        outcome,
        "--context",
        json.dumps(context),
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(
            f"WARNING: log_action.py invocation failed: {exc}",
            file=sys.stderr,
        )
        return
    if proc.returncode != 0:
        print(
            f"WARNING: log_action.py exited {proc.returncode}: "
            f"stderr={proc.stderr.strip()!r}",
            file=sys.stderr,
        )


def _load_prescan(arg: str) -> dict:
    """Accept `@<path>` or a bare path. Returns the parsed JSON dict."""
    path_str = arg[1:] if arg.startswith("@") else arg
    raw = Path(path_str).read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(
            f"prescan JSON must decode to an object, got {type(data).__name__}"
        )
    return data


def handle(
    prescan: dict,
    date_str: str,
    log_action_bin: Path,
) -> tuple[Optional[int], list[str]]:
    """Run the end-to-end parse-failure handling.

    Returns (issue_number_or_None, list_of_failed_paths).
    issue_number is None only when parse_failures is empty.
    """
    parse_failures = prescan.get("parse_failures") or []
    if not parse_failures:
        return None, []

    count = len(parse_failures)

    # Step A: file or dedup the inbox-quality issue.
    existing = find_existing_open_issue()
    if existing is not None:
        issue_number = existing
        _emit_log_action(
            log_action_bin,
            category="routine",
            action="inbox_quality_issue_deduped",
            target=f"issue#{issue_number}",
            outcome="success",
            context={
                "issue_number": issue_number,
                "parse_failure_count": count,
            },
        )
    else:
        issue_number = file_new_issue(parse_failures, date_str)
        _emit_log_action(
            log_action_bin,
            category="routine",
            action="inbox_quality_issue_filed",
            target=f"issue#{issue_number}",
            outcome="success",
            context={
                "issue_number": issue_number,
                "parse_failure_count": count,
            },
        )

    # Step B: inject marker into each entry.
    failed_paths: list[str] = []
    for entry in parse_failures:
        entry_path = entry.get("path") if isinstance(entry, dict) else None
        reason = entry.get("reason", "") if isinstance(entry, dict) else ""
        if not entry_path:
            failed_paths.append("<missing path>")
            _emit_log_action(
                log_action_bin,
                category="error",
                action="parse_failure_handling_error",
                target="<missing path>",
                outcome="error",
                context={
                    "issue_number": issue_number,
                    "error": "entry missing 'path' key",
                },
            )
            continue

        try:
            inject_marker(Path(entry_path), issue_number, date_str)
        except Exception as exc:  # noqa: BLE001 — broad: per-entry continue
            failed_paths.append(entry_path)
            _emit_log_action(
                log_action_bin,
                category="error",
                action="parse_failure_handling_error",
                target=entry_path,
                outcome="error",
                context={
                    "source_file": entry_path,
                    "issue_number": issue_number,
                    "error": str(exc),
                },
            )
            continue

        _emit_log_action(
            log_action_bin,
            category="routine",
            action="parse_error_marker_injected",
            target=entry_path,
            outcome="success",
            context={
                "source_file": entry_path,
                "issue_number": issue_number,
                "reason": reason,
            },
        )

    return issue_number, failed_paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Orchestrator: file/dedup the inbox-quality issue, then inject "
            "parse-error markers into each note in prescan.parse_failures."
        )
    )
    parser.add_argument(
        "prescan",
        help=(
            "Path to the prescan JSON, optionally prefixed with `@` "
            "(e.g. `@/tmp/inbox-prescan-latest.json`)."
        ),
    )
    parser.add_argument(
        "--date",
        default=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        help="ISO date YYYY-MM-DD for the marker line (UTC today default).",
    )
    parser.add_argument(
        "--log-action-bin",
        default=None,
        help=(
            "Path to log_action.py. Defaults to "
            "<repo>/scripts/openclaw/observation/log_action.py; can also be "
            "set via the LOG_ACTION_PATH env var."
        ),
    )
    args = parser.parse_args(argv)

    try:
        prescan = _load_prescan(args.prescan)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: could not load prescan JSON: {exc}", file=sys.stderr)
        return 1

    log_action_bin = _resolve_log_action_path(args.log_action_bin)

    try:
        issue_number, failed_paths = handle(prescan, args.date, log_action_bin)
    except Exception as exc:  # noqa: BLE001 — top-level guard
        print(f"ERROR: handle_parse_failures failed: {exc}", file=sys.stderr)
        return 1

    if issue_number is None:
        # Empty parse_failures: nothing to do, no output.
        return 0

    # Print the issue number to stdout (single line).
    print(issue_number)

    if failed_paths:
        print(
            "ERROR: parse-failure handling failed for "
            f"{len(failed_paths)} entry/entries:",
            file=sys.stderr,
        )
        for p in failed_paths:
            print(f"  - {p}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
