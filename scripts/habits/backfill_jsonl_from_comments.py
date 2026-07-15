#!/usr/bin/env python3
"""Phase 4 (ADR-0002) one-shot historical backfill helper.

Reads existing ``[Felix]`` completion comments from Vikunja habit tasks
and replays them as JSONL entries via ``scripts.common.state_log`` so
historical completion data is preserved before Phase 5 cutover (#308).

One-shot tool: not invoked by cron. Re-runs are idempotent — Phase 2's
``(task_id, date, state)`` dedup short-circuits subsequent attempts, and
the helper additionally performs a pre-flight ``state_log.read`` check
to avoid racing on the lock.

Vikunja is treated as read-only by this helper: only GET requests are
issued (project enumeration, task listing, per-task comments). The
canonical regex ``FELIX_COMMENT_PATTERN`` is imported from
``scripts.habits.exclude_completed`` so there is exactly one source of
truth for the parser (C-004).

The historical state map ``{"complete": "complete", "will-not-do":
"skipped"}`` is locked per the 2026-05-19 production probe (C-002). The
Phase 2 ``DOMAIN_STATES["habits"]`` enum is NOT extended; unmapped
historical state values surface in the summary report's
"Unmapped state values" section for operator follow-up.

Contracts:
  - ``kitty-specs/backfill-habits-jsonl-from-comments-01KS0Y4F/contracts/api.md``
  - ``kitty-specs/backfill-habits-jsonl-from-comments-01KS0Y4F/contracts/cli.md``
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from scripts.common import state_log
from scripts.common import vikunja_refs
from scripts.common.vikunja_config import get_vikunja_base_url
from scripts.habits.exclude_completed import FELIX_COMMENT_PATTERN


# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

#: Sentinel; resolved at call-time via get_vikunja_base_url().
DEFAULT_BASE_URL: str = ""

#: Default location of the felix-bot Vikunja API token on office2 (mode 0600).
DEFAULT_TOKEN_PATH = "/data/services/openclaw/secrets/vikunja-api"

#: Suffix appended to ``habits-history.jsonl`` for the pre-backfill snapshot.
SNAPSHOT_SUFFIX = ".pre-phase4-backfill.bak"

#: HTTP socket timeout in seconds for every Vikunja API call.
HTTP_TIMEOUT_SECONDS = 30

#: Locked historical-to-Phase-2-enum mapping. The Phase 2 enum is
#: ``frozenset({"complete", "incomplete", "skipped"})``. Source values
#: come from the 2026-05-19 production probe across habit task IDs
#: 14/15/16/17/18/19/20/65 (24 ``complete`` + 2 ``will-not-do`` + 0
#: other distinct values). Any state outside these keys lands in the
#: summary's "unmapped state values" section without an append.
HISTORICAL_STATE_MAP: dict[str, str] = {
    "complete": "complete",
    "will-not-do": "skipped",
}


# ---------------------------------------------------------------------------
# Internal exception used to flag snapshot-copy failure separately from
# Vikunja network/HTTP errors. ``main()`` discriminates on this to return
# exit code 3 vs exit code 1.
# ---------------------------------------------------------------------------


class _SnapshotError(OSError):
    """Marker subclass for snapshot copy failures (exit-3 surface)."""


class _StateLogInitError(OSError):
    """Marker subclass for state_log directory init failures (exit-4 surface)."""


# ---------------------------------------------------------------------------
# HTTP helpers (urllib only, mirrors ``reconcile_completions.py``)
# ---------------------------------------------------------------------------


def _join_url(base: str, path: str) -> str:
    if not base.endswith("/"):
        base = base + "/"
    return base + path.lstrip("/")


def _http_get(url: str, token: str) -> Any:
    """Issue an authenticated GET via urllib. Returns parsed JSON (or None).

    Raises:
        OSError: On network failure, non-2xx HTTP status, or non-JSON body.
    """
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
            status = resp.status
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode("utf-8", errors="replace")
        except Exception:  # pragma: no cover -- defensive
            err_body = ""
        raise OSError(
            f"GET {url} failed with HTTP {e.code}: {err_body!r}"
        ) from e
    except urllib.error.URLError as e:
        raise OSError(f"GET {url} network failure: {e}") from e

    if status < 200 or status >= 300:
        raise OSError(f"GET {url} returned HTTP {status}: {raw!r}")

    if not raw.strip():
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise OSError(f"GET {url} returned non-JSON body: {raw!r} ({e})") from e


# ---------------------------------------------------------------------------
# Vikunja access helpers
# ---------------------------------------------------------------------------


def _enumerate_habit_tasks(
    api_base_url: str, token: str, project_id: int
) -> list[dict]:
    """Enumerate active (non-archived) tasks within the Habits project.

    Project-scoped per FR-008 (cannot use ``/tasks/all`` — would leak
    cross-project rows). Mirrors the pattern in
    ``reconcile_completions._enumerate_active_habits``.

    Per Verified API Gotcha G5 (``docs/design/research/vikunja-task-model-research.md``),
    Vikunja v0.24.6 rejects ``is_archived`` in the filter expression
    with HTTP 400. The workaround: drop the server-side filter and
    apply ``is_archived`` filtering client-side on the response.

    Raises:
        OSError: On HTTP/network failure or non-list payload.
    """
    url = _join_url(api_base_url, f"projects/{project_id}/tasks")
    payload = _http_get(url, token)
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise OSError(
            f"GET {url} returned non-list payload "
            f"(got {type(payload).__name__})"
        )
    return [
        item
        for item in payload
        if isinstance(item, dict) and not item.get("is_archived", False)
    ]


def _fetch_comments(
    api_base_url: str, token: str, task_id: int
) -> list[dict]:
    """Fetch comments for a single task.

    Raises:
        OSError: On HTTP/network failure or non-list payload.
    """
    url = _join_url(api_base_url, f"tasks/{task_id}/comments")
    payload = _http_get(url, token)
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise OSError(
            f"GET {url} returned non-list payload "
            f"(got {type(payload).__name__})"
        )
    return [item for item in payload if isinstance(item, dict)]


# ---------------------------------------------------------------------------
# Record construction
# ---------------------------------------------------------------------------


def _build_record(task: dict, comment: dict, parsed: re.Match) -> dict:
    """Build a Phase 2 habits JSONL record from a [Felix] comment match.

    Caller is responsible for verifying the parsed state value is mapped
    in ``HISTORICAL_STATE_MAP`` BEFORE invoking this builder.

    Field provenance is documented in ``data-model.md`` Entity 2:
      - ``task_id``: Vikunja task id.
      - ``title``: Vikunja task's CURRENT title at backfill time (comments
        do not carry titles).
      - ``date``: regex ``date`` group from the comment body.
      - ``state``: ``HISTORICAL_STATE_MAP[<lowercased parsed state>]``.
      - ``source``: hardcoded ``"historical-backfill"`` to distinguish from
        forward writes.
      - ``note``: optional ``note`` group (None if not present).
      - ``timestamp``: pass-through of Vikunja's ``comment.created`` ISO-8601.
    """
    parsed_state = parsed.group("state").lower()
    parsed_date = parsed.group("date")
    parsed_note = parsed.group("note")
    return {
        "domain": "habits",
        "task_id": task["id"],
        "title": task["title"],
        "date": parsed_date,
        "state": HISTORICAL_STATE_MAP[parsed_state],
        "source": "historical-backfill",
        "note": parsed_note if parsed_note else None,
        "timestamp": comment["created"],
    }


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------


def _snapshot_jsonl(state_dir: Path) -> tuple[Optional[Path], bool]:
    """Copy ``habits-history.jsonl`` to ``...pre-phase4-backfill.bak``.

    The snapshot is the operator's rollback substrate (spec FR-008 + the
    Rollback plan in quickstart.md). On re-runs the JSONL already contains
    backfilled records, so overwriting the existing ``.bak`` would destroy
    the true pre-backfill content. We therefore skip the copy when the
    snapshot already exists and surface that fact to the summary report so
    the operator knows the original ``.bak`` was preserved.

    Returns:
        Tuple ``(path, created)`` where:
          - ``path`` is the snapshot path, or ``None`` if the source did
            not exist (first-ever backfill on a host with no prior JSONL).
          - ``created`` is ``True`` if a fresh snapshot was written by this
            call, ``False`` if a pre-existing ``.bak`` was preserved as-is
            (or if the source was missing).

    Raises:
        _SnapshotError: On any failure during the copy. Marker subclass of
            ``OSError`` so the CLI can map it to exit code 3 without
            confusing it with a Vikunja network error.
    """
    source = state_dir / "habits-history.jsonl"
    if not source.exists():
        return None, False
    target = source.with_name(source.name + SNAPSHOT_SUFFIX)
    if target.exists():
        # Preserve the original pre-backfill snapshot; do NOT overwrite.
        # The summary formatter surfaces this so the operator knows the
        # existing .bak was kept (it represents the true pre-backfill
        # state from the first run).
        return target, False
    try:
        shutil.copy2(source, target)
    except OSError as e:
        raise _SnapshotError(
            f"snapshot copy failed: {source} -> {target}: {e}"
        ) from e
    return target, True


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    """Current UTC timestamp in ISO-8601 with offset."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def backfill(
    api_base_url: str,
    token: str,
    *,
    dry_run: bool = False,
    today: str | None = None,  # noqa: ARG001 -- reserved for API symmetry
) -> dict:
    """One-shot historical backfill of habits JSONL from [Felix] comments.

    See ``contracts/api.md`` for the full contract. Summary:

    - Resolves the Habits Vikunja project via the reference registry
      (logical name ``"habits"`` → ``vikunja_refs.project_id``; network-free).
    - Enumerates active (non-archived) tasks in that project.
    - For each task: GETs comments; parses ``[Felix]`` matches; maps the
      parsed state through ``HISTORICAL_STATE_MAP``; on dry_run counts
      planned records, on live appends via ``state_log.append`` with
      ``source="historical-backfill"`` and ``timestamp=comment.created``.
    - On live: creates a ``.pre-phase4-backfill.bak`` snapshot BEFORE the
      first append (skipped if no prior JSONL exists).
    - Per-task comment fetch failures are caught and reported as anomalies;
      project enumeration failures propagate as ``OSError``.

    Args:
        api_base_url: Vikunja API base URL.
        token: felix-bot bearer token.
        dry_run: If True, no writes occur. The summary reports
            ``records_planned`` instead of ``records_appended``.
        today: Reserved for clock-pinning in future fixtures; unused here.

    Returns:
        Summary dict (see ``data-model.md`` Entity 4).

    Raises:
        vikunja_refs.VikunjaRefError: If the ``"habits"`` reference is
            undeclared, unprovisioned, or label-form (fail-loud registry
            resolution; caller maps to exit 2).
        OSError: If the Vikunja API is unreachable for task enumeration, or
            if the snapshot copy fails (``_SnapshotError``). Per-comment
            fetch failures DO NOT raise.
    """
    summary: dict[str, Any] = {
        "run_mode": "dry-run" if dry_run else "live",
        "started_at": _now_iso(),
        "finished_at": None,
        "habits_project_id": None,
        "tasks_enumerated": 0,
        "comments_fetched": 0,
        "records_appended": 0,
        "records_planned": 0,
        "records_skipped_dedup": 0,
        "records_skipped_unmapped": 0,
        "records_skipped_malformed": 0,
        "records_skipped_validation": 0,
        "anomalies": [],
        "unmapped_state_values": [],
        "malformed_comments": [],  # FR-009: count + snippets for skipped malformed [Felix] comments
        "by_task": {},   # task_id -> {"title": str, "count": int}
        "by_state": {},  # mapped state -> count
        "snapshot_path": None,
        "snapshot_created": False,  # False if .bak preserved from prior run or no source
    }

    # Resolve Habits project via the reference seam (network-free, fail-loud).
    # A deleted/renamed/unprovisioned "habits" ref raises VikunjaRefError →
    # caller maps to exit 2 (config error), never a silent empty run (#748/#745).
    project_id = vikunja_refs.project_id("habits")
    summary["habits_project_id"] = project_id

    # Enumerate habit tasks. OSError → caller maps to exit 1.
    tasks = _enumerate_habit_tasks(api_base_url, token, project_id)
    summary["tasks_enumerated"] = len(tasks)

    # Snapshot before any append on a live run. _SnapshotError → exit 3.
    if not dry_run:
        snapshot, created = _snapshot_jsonl(state_log.STATE_DIR)
        summary["snapshot_path"] = str(snapshot) if snapshot else None
        summary["snapshot_created"] = created

    for task in tasks:
        task_id = task.get("id")
        title = task.get("title") or ""
        if not isinstance(task_id, int) or task_id <= 0:
            summary["anomalies"].append({
                "task_id": task_id,
                "message": "task missing or invalid 'id' field",
            })
            continue

        # Initialize the per-task bucket so 0-comment tasks appear in the
        # report (matches the data-model.md Entity 4 example).
        summary["by_task"].setdefault(task_id, {"title": title, "count": 0})

        try:
            comments = _fetch_comments(api_base_url, token, task_id)
        except OSError as e:
            summary["anomalies"].append({
                "task_id": task_id,
                "message": f"comment fetch failed: {e}",
            })
            continue

        for comment in comments:
            summary["comments_fetched"] += 1
            comment_id = comment.get("id")
            text = comment.get("comment") or ""
            created = comment.get("created")
            if not isinstance(created, str) or not created.strip():
                summary["anomalies"].append({
                    "task_id": task_id,
                    "comment_id": comment_id,
                    "message": "missing 'created' field; record skipped",
                })
                continue

            match = FELIX_COMMENT_PATTERN.search(text) if isinstance(text, str) else None
            if match is None:
                # Non-[Felix] comments are silently skipped here; only
                # strictly-malformed Felix-shaped lines are counted. We
                # approximate "malformed" as "begins with [Felix] but
                # doesn't match the regex". Anything else is genuine
                # non-Felix traffic (e.g. operator notes) and is ignored.
                if isinstance(text, str) and text.lstrip().startswith("[Felix]"):
                    summary["records_skipped_malformed"] += 1
                    # FR-009: capture snippet (first line, 80 chars) so the
                    # operator can audit what's being skipped and tell
                    # legitimate non-Felix traffic apart from parser bugs.
                    first_line = text.splitlines()[0] if text else ""
                    snippet = first_line[:80]
                    summary["malformed_comments"].append({
                        "task_id": task_id,
                        "comment_id": comment_id,
                        "snippet": snippet,
                    })
                continue

            parsed_state = match.group("state").lower()
            if parsed_state not in HISTORICAL_STATE_MAP:
                summary["records_skipped_unmapped"] += 1
                # Trim comment snippet to first line, 80 chars max, to keep
                # the operator report readable.
                first_line = text.splitlines()[0] if text else ""
                snippet = first_line[:80]
                summary["unmapped_state_values"].append({
                    "task_id": task_id,
                    "comment_id": comment_id,
                    "date": match.group("date"),
                    "state": parsed_state,
                    "comment_snippet": snippet,
                })
                continue

            try:
                record = _build_record(task, comment, match)
            except (KeyError, TypeError) as e:
                summary["anomalies"].append({
                    "task_id": task_id,
                    "comment_id": comment_id,
                    "message": f"record-build failure: {e}",
                })
                continue

            # Validate before any write. Catches malformed timestamps,
            # impossible dates, etc.
            try:
                state_log.validate_record(record, "habits")
            except ValueError as e:
                summary["records_skipped_validation"] += 1
                summary["anomalies"].append({
                    "task_id": task_id,
                    "comment_id": comment_id,
                    "message": f"record validation failed: {e}",
                })
                continue

            mapped_state = record["state"]
            record_date = record["date"]

            if dry_run:
                summary["records_planned"] += 1
                _bump_by_task(summary, task_id, title)
                _bump_by_state(summary, mapped_state)
                continue

            # Live path. Pre-flight dedup check via state_log.read avoids
            # racing on the lock (Phase 2 append also dedups, but a
            # pre-flight is cheaper and gives us an accurate
            # records_skipped_dedup count).
            try:
                existing = state_log.read(
                    "habits",
                    task_id=task_id,
                    date=record_date,
                    state=mapped_state,
                )
            except OSError as e:
                summary["anomalies"].append({
                    "task_id": task_id,
                    "comment_id": comment_id,
                    "message": f"state_log read failed: {e}",
                })
                continue

            if existing:
                summary["records_skipped_dedup"] += 1
                continue

            try:
                state_log.append("habits", record)
            except (OSError, ValueError) as e:
                summary["anomalies"].append({
                    "task_id": task_id,
                    "comment_id": comment_id,
                    "message": f"state_log append failed: {e}",
                })
                continue

            summary["records_appended"] += 1
            _bump_by_task(summary, task_id, title)
            _bump_by_state(summary, mapped_state)

    summary["finished_at"] = _now_iso()
    return summary


def _bump_by_task(summary: dict, task_id: int, title: str) -> None:
    bucket = summary["by_task"].setdefault(task_id, {"title": title, "count": 0})
    bucket["count"] += 1


def _bump_by_state(summary: dict, state: str) -> None:
    summary["by_state"][state] = summary["by_state"].get(state, 0) + 1


# ---------------------------------------------------------------------------
# Summary formatter (data-model.md Entity 4)
# ---------------------------------------------------------------------------


def _format_summary(summary: dict) -> str:
    """Render the operator-facing report (plain text, stdout)."""
    lines: list[str] = []
    lines.append("=== Backfill summary ===")
    lines.append("Mission: backfill-habits-jsonl-from-comments-01KS0Y4F")
    lines.append(f"Run mode: {summary['run_mode']}")
    lines.append(f"Run started: {summary['started_at']}")
    lines.append(f"Run finished: {summary['finished_at']}")
    lines.append("")
    lines.append("Vikunja API:")
    proj = summary["habits_project_id"]
    if proj is not None:
        lines.append(
            f"  Habits project resolved: id={proj} "
            f'title="{vikunja_refs.project_title("habits")}"'
        )
    lines.append(f"  Habit tasks enumerated: {summary['tasks_enumerated']}")
    lines.append(f"  Comments fetched: {summary['comments_fetched']}")
    lines.append("")
    lines.append("Records:")
    if summary["run_mode"] == "dry-run":
        lines.append(f"  Planned: {summary['records_planned']}")
    else:
        lines.append(f"  Appended: {summary['records_appended']}")
    lines.append(
        f"  Skipped (dedup with existing JSONL): {summary['records_skipped_dedup']}"
    )
    lines.append(
        f"  Skipped (unmapped state): {summary['records_skipped_unmapped']}"
    )
    lines.append(
        f"  Skipped (malformed comment): {summary['records_skipped_malformed']}"
    )
    lines.append(
        f"  Skipped (validation failure): {summary['records_skipped_validation']}"
    )
    lines.append("")
    lines.append("Records by task:")
    for task_id in sorted(summary["by_task"].keys()):
        bucket = summary["by_task"][task_id]
        verb = "planned" if summary["run_mode"] == "dry-run" else "appended"
        suffix = "" if bucket["count"] > 0 else " (no [Felix] comments)"
        lines.append(
            f"  task_id={task_id} ({bucket['title']}): "
            f"{bucket['count']} {verb}{suffix}"
        )
    lines.append("")
    lines.append("Records by state (post-mapping):")
    if summary["by_state"]:
        for state in sorted(summary["by_state"].keys()):
            lines.append(f"  {state}: {summary['by_state'][state]}")
    else:
        lines.append("  (none)")
    lines.append("")
    lines.append("Unmapped state values:")
    if summary["unmapped_state_values"]:
        for entry in summary["unmapped_state_values"]:
            lines.append(
                f"  task_id={entry['task_id']} date={entry['date']} "
                f"state=\"{entry['state']}\" — \"{entry['comment_snippet']}\""
            )
        lines.append("")
        lines.append(
            "  These comments were skipped (no JSONL append). To include them,"
        )
        lines.append(
            "  add an entry to HISTORICAL_STATE_MAP in"
            " scripts/habits/backfill_jsonl_from_comments.py"
        )
        lines.append("  and re-run the backfill.")
    else:
        lines.append("  (none in this run)")
    lines.append("")
    # FR-009: malformed [Felix] comments — count + snippets so the operator
    # can audit skipped lines and distinguish bugs in the regex/parser from
    # legitimate non-Felix traffic.
    lines.append(
        f"Comments skipped as malformed: {summary['records_skipped_malformed']}"
    )
    if summary.get("malformed_comments"):
        for entry in summary["malformed_comments"]:
            comment_id = entry.get("comment_id")
            cid_part = (
                f" comment_id={comment_id}" if comment_id is not None else ""
            )
            lines.append(
                f"  task_id={entry['task_id']}{cid_part}: "
                f"\"{entry['snippet']}\""
            )
    lines.append("")
    lines.append(f"Anomalies: {len(summary['anomalies'])}")
    for entry in summary["anomalies"]:
        bits = [f"task_id={entry.get('task_id')}"]
        if "comment_id" in entry and entry["comment_id"] is not None:
            bits.append(f"comment_id={entry['comment_id']}")
        bits.append(entry.get("message", ""))
        lines.append("  " + ": ".join(bits[:2]) + ": " + bits[-1])
    lines.append("")
    lines.append("Snapshot:")
    if summary["snapshot_path"]:
        lines.append(f"  Pre-backfill snapshot: {summary['snapshot_path']}")
        if not summary.get("snapshot_created", False):
            # Re-run: existing .bak was preserved, not overwritten. The
            # original (true pre-backfill) snapshot remains the rollback
            # substrate.
            lines.append(
                "  (preserved from a prior run; not overwritten)"
            )
        lines.append(
            f"  (To rollback: cp <snapshot> "
            f"{state_log.STATE_DIR}/habits-history.jsonl)"
        )
    elif summary["run_mode"] == "dry-run":
        lines.append("  (dry-run; no snapshot created)")
    else:
        lines.append(
            "  (no prior habits-history.jsonl; snapshot skipped)"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _read_token(token_file: Path) -> str:
    """Read the felix-bot bearer token from disk.

    Raises:
        FileNotFoundError: If the token file is absent.
        OSError: For any other read failure.
    """
    content = token_file.read_text(encoding="utf-8").strip()
    if not content:
        raise OSError(f"token file is empty: {token_file}")
    return content


def build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser for the ``python3 -m`` entry point."""
    parser = argparse.ArgumentParser(
        prog="backfill_jsonl_from_comments",
        description=(
            "ADR-0002 Phase 4 one-shot helper: read existing [Felix] habit "
            "completion comments from Vikunja and replay them into the "
            "habits JSONL log (state_log.append). Idempotent on re-run "
            "via the Phase 2 (task_id, date, state) dedup. See "
            "kitty-specs/backfill-habits-jsonl-from-comments-01KS0Y4F/ "
            "and docs/design/architecture/data/agent-state-log-schema.md "
            "for the contract + record schema."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Do not append to the JSONL log. Print the summary report "
            "as if a live run had executed."
        ),
    )
    parser.add_argument(
        "--token-file",
        type=Path,
        default=Path(DEFAULT_TOKEN_PATH),
        help=(
            "Path to the felix-bot Vikunja API token file "
            f"(default: {DEFAULT_TOKEN_PATH})."
        ),
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Vikunja API base URL (default: from VIKUNJA_BASE_URL env or config file).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. See contracts/cli.md for exit codes 0/1/2/3/4."""
    parser = build_parser()
    args = parser.parse_args(argv)

    args.base_url = args.base_url or get_vikunja_base_url()

    # Token read. Exit 2 on missing token (config error).
    try:
        token = _read_token(args.token_file)
    except FileNotFoundError:
        print(
            f"ERROR: token file not found: {args.token_file}",
            file=sys.stderr,
        )
        return 2
    except OSError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    print(
        f"Backfill helper starting (mode={'dry-run' if args.dry_run else 'live'})..."
    )

    try:
        summary = backfill(args.base_url, token, dry_run=args.dry_run)
    except vikunja_refs.VikunjaRefError as e:
        # Fail-loud registry resolution failure (undeclared / unprovisioned /
        # label-form "habits" ref) → config-level error.
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    except ValueError as e:
        # Other config-level error.
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    except _SnapshotError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 3
    except _StateLogInitError as e:  # pragma: no cover -- defensive
        print(f"ERROR: state_log initialization failed: {e}", file=sys.stderr)
        return 4
    except OSError as e:
        # Vikunja API failure during project enumeration or task listing.
        print(f"ERROR: backfill failed: {e}", file=sys.stderr)
        return 1

    if summary.get("habits_project_id") is not None:
        print(
            f"Resolved Habits project: id={summary['habits_project_id']} "
            f'title="{vikunja_refs.project_title("habits")}"'
        )
    if summary.get("snapshot_path"):
        print(f"Snapshot created: {summary['snapshot_path']}")
    print(
        f"Enumerated habit tasks: {summary['tasks_enumerated']}"
    )

    print(_format_summary(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
