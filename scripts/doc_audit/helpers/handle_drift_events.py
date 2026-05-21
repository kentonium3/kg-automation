#!/usr/bin/env python3
"""Consume audit.sh drift-events.jsonl and route to doc-audit issue filing.

Implements the signal-driven doc-audit pipeline (#278). Deterministic
detection of system state changes (by audit.sh) → deterministic mapping
to documentation surfaces (via signal-to-doc-map.json) → either an
auto-filed [doc-audit] issue (matched signals) or routing to
unmapped-events.jsonl for AI review (unmatched signals).

Invocation (CLI):
    python3 handle_drift_events.py \\
        --events /data/services/security-monitor/logs/drift-events.jsonl \\
        --cursor /data/services/security-monitor/.drift-events.cursor \\
        --mapping /home/claude/kg-automation/docs/design/architecture/data/signal-to-doc-map.json \\
        --unmapped /data/services/security-monitor/logs/unmapped-events.jsonl \\
        --repo kentonium3/kg-automation

Importable surface (per mission #343 WP01 lift):
    from doc_audit.helpers.handle_drift_events import (
        process_events,         # library entry point — see ProcessResult
        ProcessResult,
        Mapping,
        load_mappings,
        read_cursor,
        write_cursor_atomic,
        find_mapping,
        decode_diff,
        file_doc_audit_issue,
        append_unmapped,
    )

    Set ``PYTHONPATH=scripts/`` so the ``doc_audit`` package is on the
    import path. The CLI ``main()`` is now a thin argparse wrapper that
    delegates to ``process_events`` — both surfaces share the same code.

Exit codes:
    0 — success (events processed, cursor advanced)
    1 — operational error (file unreadable, gh failure, etc.)
    2 — invalid arguments or config

Idempotency: cursor stores the last-processed line number. Re-running
without new events is a no-op. Cursor is written atomically (tempfile +
rename) to avoid partial state on crash.

No de-duplication of repeat-drift across cron runs is performed in v1.
If a baseline keeps drifting day-over-day, multiple issues will be
filed — that's intentional (continued drift is itself a signal worth
surfacing). De-dup can be layered on later if churn becomes a problem.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class Mapping:
    id: str
    match: dict[str, Any]
    doc_targets: list[str]
    rationale: str
    issue_title_prefix: str
    issue_labels: list[str]


@dataclass
class ProcessResult:
    """Structured result from :func:`process_events`.

    Mirrors the values reported in the CLI ``SUMMARY:`` line so library
    callers receive the same outcome counts the CLI prints without
    having to re-parse stdout.
    """

    processed: int
    matched_filed: int
    unmapped: int
    errors: int
    new_cursor: int
    exit_code: int = 0


def load_mappings(path: Path) -> list[Mapping]:
    data = json.loads(path.read_text())
    mappings = []
    for m in data.get("mappings", []):
        mappings.append(
            Mapping(
                id=m["id"],
                match=m["match"],
                doc_targets=m["doc_targets"],
                rationale=m["rationale"],
                issue_title_prefix=m["issue_title_prefix"],
                issue_labels=m.get("issue_labels", ["spec: brief"]),
            )
        )
    return mappings


def read_cursor(cursor_path: Path) -> int:
    try:
        return int(cursor_path.read_text().strip())
    except (FileNotFoundError, ValueError):
        return 0


def write_cursor_atomic(cursor_path: Path, value: int) -> None:
    parent = cursor_path.parent
    parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=cursor_path.name + ".", suffix=".tmp", dir=str(parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(str(value))
        os.replace(tmp_name, cursor_path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def find_mapping(event: dict[str, Any], mappings: list[Mapping]) -> Mapping | None:
    """Return the first mapping whose `match` is a subset of the event."""
    for m in mappings:
        if all(event.get(k) == v for k, v in m.match.items()):
            return m
    return None


def decode_diff(event: dict[str, Any]) -> str:
    """Return the diff text from an event, decoding from base64 if needed."""
    if "diff_b64" in event:
        try:
            return base64.b64decode(event["diff_b64"]).decode("utf-8", errors="replace")
        except Exception:
            return "<diff decode failed>"
    return event.get("diff", "")


def file_doc_audit_issue(
    event: dict[str, Any],
    mapping: Mapping,
    repo: str,
    dry_run: bool = False,
) -> tuple[bool, str]:
    """File a [doc-audit] issue. Returns (success, output_or_url)."""
    timestamp = event.get("timestamp", "unknown")
    baseline = event.get("baseline_name", "unknown")
    diff_text = decode_diff(event)
    diff_excerpt = diff_text if len(diff_text) <= 4000 else diff_text[:4000] + "\n...(truncated)"

    title = f"{mapping.issue_title_prefix} — {timestamp}"
    doc_target_lines = "\n".join(f"- `{t}`" for t in mapping.doc_targets)
    label_arg = ",".join(mapping.issue_labels)

    body = f"""## Auto-detected drift via signal-driven doc-audit (#278)

**Signal source**: `{event.get('source', 'unknown')}`
**Baseline**: `{baseline}`
**Event timestamp**: `{timestamp}`
**Mapping id**: `{mapping.id}`

## Likely doc targets

The signal-to-doc-map.json mapping identifies these documents as candidates for review:

{doc_target_lines}

## Rationale

{mapping.rationale}

## Drift diff

```
{diff_excerpt}
```

## Next steps

1. Review the diff above against the listed doc target(s)
2. If the change is intentional and the docs need updating: open a PR with the doc updates and reference this issue
3. If the change is intentional and the docs are already correct: close this issue with a note
4. If the change is unintentional: investigate and remediate before resetting the audit baseline

## Auto-generated

This issue was filed automatically by `handle_drift_events.py` based on `signal-to-doc-map.json`. To suppress this class of auto-filed issue, edit the mapping (or remove it) in `docs/design/architecture/data/signal-to-doc-map.json`.
"""

    if dry_run:
        return True, f"[dry-run] would file: {title}"

    try:
        result = subprocess.run(
            [
                "gh",
                "issue",
                "create",
                "--repo",
                repo,
                "--title",
                title,
                "--label",
                label_arg,
                "--body",
                body,
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
        return True, result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return False, f"gh issue create failed: {e.stderr.strip()}"
    except subprocess.TimeoutExpired:
        return False, "gh issue create timed out after 60s"


def append_unmapped(unmapped_path: Path, event: dict[str, Any]) -> None:
    unmapped_path.parent.mkdir(parents=True, exist_ok=True)
    with open(unmapped_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(event) + "\n")


def process_events(
    events_path: Path,
    cursor_path: Path,
    mapping_path: Path,
    unmapped_path: Path,
    repo: str = "kentonium3/kg-automation",
    limit: int = 20,
    dry_run: bool = False,
) -> ProcessResult:
    """Library entry point for the drift-events pipeline.

    Pure-Python orchestration of the CLI behavior. Reads the cursor +
    mapping + events files, classifies each event against the mapping
    table, files a ``[doc-audit]`` issue (matched) or appends to the
    unmapped log (unmatched), and advances the cursor atomically.

    The :class:`ProcessResult` returned mirrors the values reported in
    the CLI ``SUMMARY:`` line so library callers receive the same
    outcome counts the CLI prints without having to re-parse stdout.

    Args:
        events_path: Path to ``drift-events.jsonl``.
        cursor_path: Path to the cursor file (one integer line number).
        mapping_path: Path to ``signal-to-doc-map.json``.
        unmapped_path: Path to ``unmapped-events.jsonl`` for unmatched
            events.
        repo: GitHub repo slug used by ``gh issue create``.
        limit: Maximum events to process per invocation.
        dry_run: If True, don't actually file issues and don't advance
            the on-disk cursor.

    Returns:
        :class:`ProcessResult` carrying the per-invocation counters and
        the suggested CLI ``exit_code`` (0 on success, 1 on error, 2 on
        invalid config).
    """
    if not mapping_path.exists():
        print(f"ERROR: mapping file not found: {mapping_path}", file=sys.stderr)
        return ProcessResult(
            processed=0,
            matched_filed=0,
            unmapped=0,
            errors=0,
            new_cursor=read_cursor(cursor_path),
            exit_code=2,
        )

    mappings = load_mappings(mapping_path)
    cursor = read_cursor(cursor_path)

    if not events_path.exists():
        # No events file yet — nothing to do; not an error
        print(f"INFO: no events file at {events_path}; nothing to process")
        return ProcessResult(
            processed=0,
            matched_filed=0,
            unmapped=0,
            errors=0,
            new_cursor=cursor,
            exit_code=0,
        )

    with open(events_path, encoding="utf-8") as fh:
        lines = fh.readlines()

    new_lines = lines[cursor:]
    if not new_lines:
        print(f"INFO: no new events since cursor={cursor}")
        return ProcessResult(
            processed=0,
            matched_filed=0,
            unmapped=0,
            errors=0,
            new_cursor=cursor,
            exit_code=0,
        )

    if len(new_lines) > limit:
        print(
            f"WARN: {len(new_lines)} new events exceeds --limit={limit}; "
            f"processing first {limit}, cursor will advance only that far",
            file=sys.stderr,
        )
        new_lines = new_lines[:limit]

    matched = 0
    unmapped = 0
    errors = 0
    processed = 0

    for line in new_lines:
        line = line.strip()
        if not line:
            processed += 1
            continue

        try:
            event = json.loads(line)
        except json.JSONDecodeError as e:
            print(f"WARN: skipping malformed event line: {e}", file=sys.stderr)
            processed += 1
            continue

        mapping = find_mapping(event, mappings)
        if mapping is None:
            append_unmapped(unmapped_path, event)
            unmapped += 1
            print(
                f"INFO: no mapping for event source={event.get('source')} "
                f"baseline={event.get('baseline_name')}; routed to unmapped log"
            )
        else:
            ok, output = file_doc_audit_issue(event, mapping, repo, dry_run=dry_run)
            if ok:
                matched += 1
                print(f"INFO: mapping={mapping.id} → {output}")
            else:
                errors += 1
                print(f"ERROR: mapping={mapping.id} → {output}", file=sys.stderr)
                # Don't advance cursor past failed events so they retry next run
                break

        processed += 1

    new_cursor = cursor + processed
    if dry_run:
        print(
            f"SUMMARY: processed={processed} matched_filed={matched} "
            f"unmapped={unmapped} errors={errors} "
            f"cursor={cursor}→{new_cursor} (DRY-RUN — cursor NOT written)"
        )
    else:
        write_cursor_atomic(cursor_path, new_cursor)
        print(
            f"SUMMARY: processed={processed} matched_filed={matched} "
            f"unmapped={unmapped} errors={errors} cursor={cursor}→{new_cursor}"
        )

    return ProcessResult(
        processed=processed,
        matched_filed=matched,
        unmapped=unmapped,
        errors=errors,
        new_cursor=new_cursor,
        exit_code=1 if errors > 0 else 0,
    )


def main(argv: list[str] | None = None) -> int:
    """Thin CLI wrapper around :func:`process_events`."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", required=True, type=Path, help="Path to drift-events.jsonl")
    parser.add_argument("--cursor", required=True, type=Path, help="Path to cursor file")
    parser.add_argument(
        "--mapping",
        required=True,
        type=Path,
        help="Path to signal-to-doc-map.json",
    )
    parser.add_argument(
        "--unmapped",
        required=True,
        type=Path,
        help="Path to unmapped-events.jsonl (events without a mapping)",
    )
    parser.add_argument(
        "--repo",
        default="kentonium3/kg-automation",
        help="GitHub repo for issue filing",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't actually file issues; print what would happen",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum events to process per invocation (safety against runaway)",
    )
    args = parser.parse_args(argv)

    result = process_events(
        events_path=args.events,
        cursor_path=args.cursor,
        mapping_path=args.mapping,
        unmapped_path=args.unmapped,
        repo=args.repo,
        limit=args.limit,
        dry_run=args.dry_run,
    )
    return result.exit_code


if __name__ == "__main__":
    sys.exit(main())
