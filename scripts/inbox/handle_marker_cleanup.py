#!/usr/bin/env python3
"""Stale-marker cleanup orchestrator for felix-admin-capture.

Consolidates Step 5a of the felix-admin-capture AGENTS.md prompt into a
single command. Reads the prescan JSON, iterates the
`marker_cleanup_needed` list, and strips the parse-error callout marker
from each note. Per-entry actions are emitted via `log_action.py`.

Per-entry failures are logged as `marker_cleanup_error` and do not abort
the rest; the script exits 1 if any strip failed, 0 otherwise.

The underlying helper (`strip_parse_error_marker`) is imported as a
library function; we do NOT subprocess its CLI wrapper. See WP01 / issue
#253 for context.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

# `scripts/inbox/` is added to sys.path by tests/inbox/conftest.py; when this
# script runs standalone it is imported directly.
from strip_parse_error_marker import strip_marker  # noqa: E402


AGENT_NAME = "felix-admin-capture"


def _default_log_action_path() -> Path:
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
    path_str = arg[1:] if arg.startswith("@") else arg
    raw = Path(path_str).read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(
            f"prescan JSON must decode to an object, got {type(data).__name__}"
        )
    return data


def handle(prescan: dict, log_action_bin: Path) -> list[str]:
    """Strip the marker from each marker_cleanup_needed entry.

    Returns a list of paths whose strip failed (empty == all-success).
    """
    cleanup_list = prescan.get("marker_cleanup_needed") or []
    if not cleanup_list:
        return []

    failed_paths: list[str] = []
    for entry in cleanup_list:
        entry_path = entry.get("path") if isinstance(entry, dict) else None
        entry_issue = (
            entry.get("issue_number") if isinstance(entry, dict) else None
        )
        if not entry_path:
            failed_paths.append("<missing path>")
            _emit_log_action(
                log_action_bin,
                category="error",
                action="marker_cleanup_error",
                target="<missing path>",
                outcome="error",
                context={"error": "entry missing 'path' key"},
            )
            continue

        try:
            strip_marker(Path(entry_path))
        except Exception as exc:  # noqa: BLE001 — broad: per-entry continue
            failed_paths.append(entry_path)
            _emit_log_action(
                log_action_bin,
                category="error",
                action="marker_cleanup_error",
                target=entry_path,
                outcome="error",
                context={
                    "source_file": entry_path,
                    "error": str(exc),
                },
            )
            continue

        _emit_log_action(
            log_action_bin,
            category="routine",
            action="marker_stripped",
            target=entry_path,
            outcome="success",
            context={
                "source_file": entry_path,
                "issue_number": entry_issue,
            },
        )

    return failed_paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Orchestrator: strip parse-error markers from every note in "
            "prescan.marker_cleanup_needed."
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
        failed_paths = handle(prescan, log_action_bin)
    except Exception as exc:  # noqa: BLE001 — top-level guard
        print(f"ERROR: handle_marker_cleanup failed: {exc}", file=sys.stderr)
        return 1

    if failed_paths:
        print(
            "ERROR: marker cleanup failed for "
            f"{len(failed_paths)} entry/entries:",
            file=sys.stderr,
        )
        for p in failed_paths:
            print(f"  - {p}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
