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
        nargs="?",
        type=int,
        default=None,
        help=(
            "GitHub issue number filed for this note (issue_task routes). "
            "Omit for --kind calendar."
        ),
    )
    parser.add_argument(
        "vikunja_task_id",
        nargs="?",
        default=None,
        help="Vikunja task ID, or '-' if no task was created (issue_task routes).",
    )
    parser.add_argument(
        "excerpt",
        nargs="?",
        default="",
        help="Short note excerpt (will be truncated to 120 chars).",
    )
    parser.add_argument(
        "--kind",
        choices=("issue_task", "calendar"),
        default="issue_task",
        help=(
            "Route class. 'calendar' records a Google Calendar event (#737) — "
            "calendar routes have no GitHub issue or Vikunja task."
        ),
    )
    parser.add_argument(
        "--event-id",
        default=None,
        help="Calendar event id — required (and the destination) with --kind calendar.",
    )
    args = parser.parse_args(argv)

    writer = RoutingLogWriter()

    if args.kind == "calendar":
        if not args.event_id:
            print(
                "ERROR: --event-id is required with --kind calendar",
                file=sys.stderr,
            )
            return 2
        if args.issue_number is not None:
            print(
                "ERROR: positional issue_number is not allowed with --kind "
                "calendar (use --event-id)",
                file=sys.stderr,
            )
            return 2
        try:
            entry = writer.append(
                filename=args.filename,
                kind="calendar",
                destination=args.event_id,
                note_excerpt=args.excerpt,
            )
        except OSError as exc:
            print(f"ERROR: could not write routing log: {exc}", file=sys.stderr)
            return 1
        print(
            f"Appended routing log entry: {entry.filename} -> calendar "
            f"({entry.destination})"
        )
        return 0

    # issue_task route (original behavior).
    if args.issue_number is None:
        print(
            "ERROR: issue_number is required with --kind issue_task",
            file=sys.stderr,
        )
        return 2
    if args.vikunja_task_id in (None, "-"):
        task_id = None
    else:
        try:
            task_id = int(args.vikunja_task_id)
        except ValueError:
            print(
                "ERROR: vikunja_task_id must be an integer or '-' "
                f"(got {args.vikunja_task_id!r})",
                file=sys.stderr,
            )
            return 2
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
