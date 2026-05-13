#!/usr/bin/env python3
"""Append one entry to the inbox routing log.

Thin CLI wrapper around routing_log.RoutingLogWriter.append. Used by
felix-admin-capture's AGENTS.md after each successful route to make the
routing-log dedup substrate authoritative (FR-001/FR-002).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from routing_log import RoutingLogWriter


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Append one entry to the inbox routing log."
    )
    parser.add_argument("filename", help="Inbox note filename (basename only).")
    parser.add_argument(
        "issue_number",
        type=int,
        help="GitHub issue number filed for this note.",
    )
    parser.add_argument(
        "vikunja_task_id",
        help="Vikunja task ID, or '-' if no task was created.",
    )
    parser.add_argument(
        "excerpt",
        nargs="?",
        default="",
        help="Short note excerpt (will be truncated to 120 chars).",
    )
    args = parser.parse_args(argv)

    task_id = None if args.vikunja_task_id == "-" else int(args.vikunja_task_id)
    writer = RoutingLogWriter()
    try:
        entry = writer.append(
            filename=args.filename,
            issue_number=args.issue_number,
            vikunja_task_id=task_id,
            note_excerpt=args.excerpt,
        )
    except OSError as exc:
        print(f"ERROR: could not write routing log: {exc}", file=sys.stderr)
        return 1
    print(f"Appended routing log entry: {entry.filename} -> #{entry.issue_number}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
