#!/usr/bin/env python3
"""Append one entry to the inbox routing log.

Thin CLI wrapper around routing_log.RoutingLogWriter.append. Used by
felix-admin-capture's AGENTS.md after each successful route to make the
routing-log dedup substrate authoritative (FR-001/FR-002).
"""
from __future__ import annotations

import argparse
import sys

# Deduplicate module loading: if routing_log is already in sys.modules
# (e.g. scripts/inbox/ on sys.path), reuse that object so any external
# monkeypatching of DEFAULT_ROUTING_LOG_PATH (e.g. in tests) applies to the
# package-absolute import form as well.
_bare_rl = sys.modules.get("routing_log")
if _bare_rl is not None:
    sys.modules.setdefault("scripts.inbox.routing_log", _bare_rl)
del _bare_rl

from scripts.inbox.routing_log import RoutingLogWriter  # noqa: E402


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
