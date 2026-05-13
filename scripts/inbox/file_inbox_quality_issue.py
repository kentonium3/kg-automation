#!/usr/bin/env python3
"""File (or dedupe) the batched "Inbox quality" GitHub issue.

Invoked by felix-admin-capture at end-of-cron-turn when prescan reports a
non-empty `parse_failures` list. Two outcomes:

  (a) An OPEN issue whose title starts with `"Inbox quality:"` already
      exists → print that number, do nothing else.
  (b) Otherwise → file a new issue against `kentonium3/kg-automation`
      with stable title format and the table-of-failures body. Print the
      new issue number.

Title-prefix dedup is intentional. We never update an existing batched
issue's body; the existing issue stays a stable rallying point until
the human fixes notes and closes it.

See kitty-specs/inbox-capture-dedup-and-parser-hardening-01KREZJ8/contracts/
inbox-quality-issue-writer.md for the contract.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

INBOX_QUALITY_TITLE_PREFIX = "Inbox quality:"
DEFAULT_REPO = "kentonium3/kg-automation"
DEFAULT_LABEL = "area/content"
DEFAULT_ASSIGNEE = "kentonium3"
ACTIVITY_LOG_TEMPLATE = (
    "/home/kgale/second-brain/agents/logs/inbox-processing-{date}.md"
)
# GitHub issue body hard limit is ~65,536 chars; we cap conservatively below
# so `gh issue create` doesn't reject the call. See contracts/inbox-quality-
# issue-writer.md "Body too long" clause.
MAX_BODY_CHARS = 60_000


def build_title(num_failures: int, date_str: str) -> str:
    """Stable title format. Drift breaks dedup forever."""
    return f"{INBOX_QUALITY_TITLE_PREFIX} {num_failures} notes with parse errors — {date_str}"


def build_body(parse_failures: list[dict], date_str: str) -> str:
    rows = [_format_row(pf) for pf in parse_failures]
    body = _assemble_body(rows, len(parse_failures), date_str)
    if len(body) <= MAX_BODY_CHARS:
        return body
    # Truncate the table until the body fits, then add a `... and N more`
    # footer. Binary-search not needed — table grows roughly linearly so
    # decrementing from the tail terminates quickly enough at our scale.
    kept = list(rows)
    while kept:
        kept.pop()
        truncated_footer = (
            f"\n| _… and {len(parse_failures) - len(kept)} more_ | |"
        )
        body = _assemble_body(
            kept, len(parse_failures), date_str, table_suffix=truncated_footer
        )
        if len(body) <= MAX_BODY_CHARS:
            return body
    # Pathological: even zero rows + prose exceeds limit. Return prose-only
    # body anyway so the issue at least files.
    return _assemble_body([], len(parse_failures), date_str)


def _format_row(pf: dict) -> str:
    path = pf.get("path", "")
    reason = pf.get("reason", "")
    basename = Path(path).name if path else ""
    return f"| `{basename}` | {_escape_md_cell(reason)} |"


def _assemble_body(
    rows: list[str], total: int, date_str: str, table_suffix: str = ""
) -> str:
    table = "\n".join(rows) if rows else "| (none) | |"
    return (
        f"The `felix-admin-capture` agent encountered {total} "
        f"notes whose frontmatter could not be parsed on {date_str}. "
        "Routing for these notes is halted until the frontmatter is fixed; "
        "each note has been tagged with a `> [!error] felix-capture:` callout "
        "marker referencing this issue.\n\n"
        "| Filename | Reason |\n"
        "|---|---|\n"
        f"{table}{table_suffix}\n\n"
        f"Per-run activity log: `{ACTIVITY_LOG_TEMPLATE.format(date=date_str)}`\n\n"
        "### What to do\n\n"
        "Open each note in Obsidian. The agent has injected a "
        "`> [!error] felix-capture:` callout at the top indicating the "
        "malformation. Common fixes:\n\n"
        "- **Leading whitespace before `---`**: delete blank lines / spaces "
        "/ BOM before the opening `---`.\n"
        "- **UTF-8 BOM**: re-save the file in UTF-8 without BOM.\n"
        "- **Missing closing `---`**: add the closing fence.\n"
        "- **Invalid YAML inside frontmatter**: fix the YAML syntax.\n\n"
        "After fixing, the next cron tick will re-classify, auto-strip the "
        "marker, and route normally.\n\n"
        "*Filed by `felix-admin-capture` on office2 via `kg-felix-bot`.*\n"
    )


def _escape_md_cell(text: str) -> str:
    """Make a string safe to drop into a markdown table cell."""
    return text.replace("|", "\\|").replace("\n", " ").strip()


def find_existing_open_issue(repo: str = DEFAULT_REPO) -> Optional[int]:
    """Return the issue number of an existing open Inbox-quality issue,
    or None if none found. Uses gh's fuzzy search + a startswith() post-filter.
    """
    try:
        result = subprocess.run(
            [
                "gh", "issue", "list",
                "--repo", repo,
                "--search", f'in:title "{INBOX_QUALITY_TITLE_PREFIX}"',
                "--state", "open",
                "--json", "number,title",
                "--limit", "50",
            ],
            capture_output=True, text=True, check=True, timeout=15,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"gh issue list failed: rc={exc.returncode} stderr={exc.stderr!r}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"gh issue list timed out after 15s") from exc

    try:
        items = json.loads(result.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"gh issue list returned non-JSON: {result.stdout!r}"
        ) from exc

    for item in items:
        title = item.get("title", "")
        if title.startswith(INBOX_QUALITY_TITLE_PREFIX):
            return int(item["number"])
    return None


def file_new_issue(
    parse_failures: list[dict],
    date_str: str,
    repo: str = DEFAULT_REPO,
    label: str = DEFAULT_LABEL,
    assignee: str = DEFAULT_ASSIGNEE,
) -> int:
    """File a new Inbox-quality issue. Returns the new issue number."""
    title = build_title(len(parse_failures), date_str)
    body = build_body(parse_failures, date_str)
    try:
        result = subprocess.run(
            [
                "gh", "issue", "create",
                "--repo", repo,
                "--title", title,
                "--body", body,
                "--label", label,
                "--assignee", assignee,
            ],
            capture_output=True, text=True, check=True, timeout=30,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"gh issue create failed: rc={exc.returncode} stderr={exc.stderr!r}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("gh issue create timed out after 30s") from exc

    return _parse_issue_number_from_url(result.stdout.strip())


def _parse_issue_number_from_url(url: str) -> int:
    """gh issue create prints e.g. `https://github.com/owner/repo/issues/123`."""
    match = re.search(r"/issues/(\d+)\b", url)
    if not match:
        raise RuntimeError(f"could not parse issue number from gh output: {url!r}")
    return int(match.group(1))


def _load_parse_failures(arg: str) -> list[dict]:
    """`@<path>` reads the JSON from a file; otherwise arg is treated as
    a literal JSON string."""
    if arg.startswith("@"):
        return json.loads(Path(arg[1:]).read_text(encoding="utf-8"))
    return json.loads(arg)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="File or dedupe the batched 'Inbox quality' issue."
    )
    parser.add_argument(
        "--parse-failures",
        required=True,
        help=(
            "JSON list of {path, reason} objects, OR @<file> to read JSON "
            "from disk."
        ),
    )
    parser.add_argument(
        "--date",
        default=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        help="Date string YYYY-MM-DD for the title/body (UTC today default).",
    )
    parser.add_argument(
        "--repo",
        default=DEFAULT_REPO,
        help=f"Target GitHub repo (default {DEFAULT_REPO}).",
    )
    args = parser.parse_args(argv)

    try:
        parse_failures = _load_parse_failures(args.parse_failures)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"ERROR: could not parse --parse-failures: {exc}", file=sys.stderr)
        return 1

    if not isinstance(parse_failures, list):
        print(
            f"ERROR: --parse-failures must decode to a list, got {type(parse_failures).__name__}",
            file=sys.stderr,
        )
        return 1

    if not parse_failures:
        # Empty input is a no-op success. Don't file an empty issue.
        return 0

    try:
        existing = find_existing_open_issue(repo=args.repo)
        if existing is not None:
            print(existing)
            return 0
        new_number = file_new_issue(parse_failures, args.date, repo=args.repo)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(new_number)
    return 0


if __name__ == "__main__":
    sys.exit(main())
