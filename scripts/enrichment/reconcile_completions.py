#!/usr/bin/env python3
"""ADR-0002 Phase 7 ``reconcile_completions`` backfill for the enrichment domain.

The one-shot backfill sweep. For every Vikunja task carrying historical
``[Felix] enrichment | <state> | <ISO timestamp>[| <note>]`` comments,
replay each comment as a JSONL row in the enrichment ledger.

Operation model (per spec FR-006..FR-009):

    * Enumerate Vikunja projects + tasks via ``GET`` (read-only — no
      ``POST`` / ``PUT`` / ``PATCH``).
    * For every task, fetch its comments and filter to the
      ``[Felix] enrichment`` prefix.
    * Per FR-007 disambiguation: a comment is an enrichment comment ONLY
      when the second pipe-delimited field is the literal string
      ``enrichment``. Habit comments — which carry the same ``[Felix]``
      prefix but a ``YYYY-MM-DD`` date in the second field — are skipped
      silently and never replayed into the enrichment ledger.
    * Per FR-008: comments older than the ``--since`` cutoff (default
      ``2026-04-11``) are skipped.
    * For each surviving comment, call
      :func:`scripts.enrichment.record_completion.record` with
      ``source="backfill"`` and ``skip_vikunja=True`` (the ``--no-vikunja``
      semantics). The underlying ledger append uses fcntl-locked atomic
      append + dedup, so re-runs are idempotent per FR-009.
    * Idempotency key (FR-009): the JSONL ledger's existing
      ``(task_id, state)`` dedup combined with the per-comment
      ``timestamp_utc`` derived from the comment body produces stable
      ledger rows — a re-run on the same Vikunja state yields zero new
      writes.

Q10 / soft-fail posture:

    * Malformed enrichment comments (split mismatch, unknown state token,
      invalid timestamp) are NEVER replayed. They are surfaced in the
      report's malformed list with a snippet + reason for operator triage.
    * One-shot backfill scope: no GitHub-issue hard-fail filing. Per
      research D5 precedent (escalation backfill), report-only is correct
      here — the live runtime is responsible for hard-fail surfacing on
      future bad writes.

CLI surface — see ``contracts/cli.md`` (reconcile section):

    --since YYYY-MM-DD   default 2026-04-11
    --dry-run            no JSONL writes; report only
    --ledger-path PATH   default scripts/enrichment/schema.DEFAULT_LEDGER_PATH
    --base-url URL       default Tailscale Vikunja base URL
    --token-path PATH    default /data/services/openclaw/secrets/vikunja-api

Exit codes::

    0 — success (sweep completed; report on stdout)
    1 — Vikunja or filesystem fatal error (run aborted)
    3 — validation / usage error

Design references:
    - kitty-specs/tasker-jsonl-migration-01KSB5XV/spec.md
        FR-006..FR-009, FR-014, NFR-001, NFR-003
    - kitty-specs/tasker-jsonl-migration-01KSB5XV/data-model.md
        E1 (JSONL row shape), § "Disambiguation rule (reconcile)"
    - kitty-specs/tasker-jsonl-migration-01KSB5XV/contracts/cli.md
        reconcile_completions section (flag set + exit codes)
    - scripts/escalation/reconcile_completions.py
        Pattern source — drift-detection sweep
    - scripts/escalation/backfill_jsonl_from_comments.py
        Pattern source — one-shot comment replay
    - scripts/enrichment/record_completion.py
        The atomic three-write helper invoked per parsed comment
    - scripts/enrichment/schema.py
        :data:`VALID_STATES`, :data:`DEFAULT_LEDGER_PATH`,
        :class:`EnrichmentSchemaError`
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from scripts.enrichment import record_completion as rc
from scripts.enrichment.record_completion import (
    DEFAULT_BASE_URL,
    DEFAULT_TOKEN_PATH,
    EnrichmentSchemaError,
    StateLogError,
    VikunjaError,
)
from scripts.enrichment.schema import (
    DEFAULT_LEDGER_PATH,
    VALID_STATES,
)


__all__ = [
    "DEFAULT_BACKFILL_SINCE",
    "DEFAULT_BASE_URL",
    "DEFAULT_LEDGER_PATH",
    "DEFAULT_TOKEN_PATH",
    "FELIX_COMMENT_PREFIX",
    "HTTP_TIMEOUT_SECONDS",
    "EXCLUDED_PROJECT_IDS",
    "MalformedComment",
    "ReconcileReport",
    "parse_comment",
    "reconcile",
    "main",
]


# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

#: Default backfill window per FR-008. 2026-04-11 is the post-#308 / habits
#: pattern formalization date — any enrichment comment from before this is
#: pre-vocabulary and not safely replayable.
DEFAULT_BACKFILL_SINCE: str = "2026-04-11"

#: HTTP socket timeout in seconds for every Vikunja API call.
HTTP_TIMEOUT_SECONDS: int = 30

#: Marker prefix used by Felix in enrichment comments per deployed tasker
#: AGENTS.md "Comment Format" section. Reconcile filters comments on this
#: prefix BEFORE the FR-007 disambiguation check (which then enforces that
#: the second pipe-delimited field is literally ``enrichment``).
FELIX_COMMENT_PREFIX: str = "[Felix]"

#: Project ids excluded from ``reconcile`` per the deployed tasker AGENTS.md
#: scope rules. ``11`` (Goals) and ``13`` (Habits) carry their own state
#: substrate (Habits is owned by felix-admin-habits; Goals are anchors,
#: not enrichable tasks).
EXCLUDED_PROJECT_IDS: frozenset[int] = frozenset({11, 13})


# ---------------------------------------------------------------------------
# Comment-parsing regex set (data-model E1 § "Disambiguation rule")
# ---------------------------------------------------------------------------

#: Match the enrichment-comment shape:
#:
#:     ``[Felix] enrichment | <state> | <ISO timestamp>[| <note>]``
#:
#: Per FR-007 disambiguation: the second field MUST be literally
#: ``enrichment``. Habit comments (``[Felix] YYYY-MM-DD | state``) carry a
#: date in the second field and are rejected by this regex.
#:
#: The trailing ``(?:\s*\|\s*(?P<note>.+))?$`` makes the optional fourth
#: field a permissive free-text capture group; it may contain any character
#: that isn't a newline.
_ENRICHMENT_COMMENT_RE = re.compile(
    r"^\[Felix\]\s+enrichment\s*\|\s*"
    r"(?P<state>[a-z_]+)\s*\|\s*"
    r"(?P<timestamp>[^|]+?)"
    r"(?:\s*\|\s*(?P<note>.+))?$"
)


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MalformedComment:
    """One malformed enrichment comment surfaced in the reconcile report.

    Mirrors the escalation backfill's :class:`MalformedComment`. The
    comment is NEVER replayed; the operator triages from the snippet +
    reason.

    Attributes:
        task_id: Vikunja task id containing the malformed comment.
        comment_id: Vikunja comment id (or ``None`` if the comment body
            lacked an id field — defensive).
        snippet: First 160 characters of the offending comment body.
        reason: Short parse-error string ("regex mismatch", "unknown
            state token 'X'", "invalid timestamp", ...).
    """

    task_id: int
    comment_id: int | None
    snippet: str
    reason: str


@dataclass(frozen=True, slots=True)
class ReconcileReport:
    """Summary of one ``reconcile`` invocation.

    Attributes:
        tasks_scanned: Number of tasks enumerated that carried at least
            one ``[Felix]``-prefixed comment.
        comments_parsed: Total number of ``[Felix]``-prefixed comments
            inspected (including skipped habit comments, malformed
            comments, and parseable enrichment comments).
        enrichment_comments_found: Number of comments that passed the
            FR-007 disambiguation check (second field == ``enrichment``).
        habit_comments_skipped: Number of comments whose second field was
            a date (``YYYY-MM-DD``) — skipped silently per FR-007.
        comments_replayed: Number of NEWLY appended JSONL rows. On a
            re-run against an already-backfilled ledger this is ``0``
            because every record short-circuits at the ledger's
            ``(task_id, state)`` dedup.
        comments_deduped: Number of parseable enrichment comments that
            were skipped on append because the ledger already had a row
            for ``(task_id, state)``. Informational. Always ``0`` on
            dry-run (no pre-check is performed).
        comments_out_of_window: Number of parseable enrichment comments
            whose ``timestamp_utc`` fell before the ``--since`` cutoff.
        malformed_details: Per-malformed-comment surface for the operator.
        ledger_path: Path to the enrichment JSONL ledger.
        dry_run: True if no writes occurred this invocation.
        duration_seconds: Wall-clock seconds the sweep took, end to end.
    """

    tasks_scanned: int
    comments_parsed: int
    enrichment_comments_found: int
    habit_comments_skipped: int
    comments_replayed: int
    comments_deduped: int
    comments_out_of_window: int
    malformed_details: list[MalformedComment] = field(default_factory=list)
    ledger_path: Path = field(default_factory=lambda: DEFAULT_LEDGER_PATH)
    dry_run: bool = False
    duration_seconds: float = 0.0


# ---------------------------------------------------------------------------
# Internal exceptions (CLI exit-code routing)
# ---------------------------------------------------------------------------


class _DateParseError(ValueError):
    """Raised when ``--since`` cannot be parsed as ``YYYY-MM-DD``."""


# ---------------------------------------------------------------------------
# HTTP helpers (urllib-only, mirrors escalation backfill)
# ---------------------------------------------------------------------------


def _join_url(base: str, path: str) -> str:
    """Join a base URL and a path, tolerating missing/extra slashes."""
    if not base.endswith("/"):
        base = base + "/"
    return base + path.lstrip("/")


def _read_token(token_path: Path) -> str:
    """Read and return the felix-bot bearer token from ``token_path``.

    Raises:
        FileNotFoundError: If the file is missing.
        ValueError: If the file is empty after strip.
        OSError: If the file exists but cannot be read.
    """
    if not token_path.exists():
        raise FileNotFoundError(f"Token file not found: {token_path}")
    content = token_path.read_text(encoding="utf-8").strip()
    if not content:
        raise ValueError(f"Token file is empty: {token_path}")
    return content


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
        with urllib.request.urlopen(
            req, timeout=HTTP_TIMEOUT_SECONDS
        ) as resp:
            status = resp.status
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        try:
            err_body = exc.read().decode("utf-8", errors="replace")
        except Exception:  # pragma: no cover - defensive
            err_body = ""
        raise OSError(
            f"GET {url} failed with HTTP {exc.code}: {err_body!r}"
        ) from exc
    except urllib.error.URLError as exc:
        raise OSError(f"GET {url} network failure: {exc}") from exc

    if status < 200 or status >= 300:
        raise OSError(f"GET {url} returned HTTP {status}: {raw!r}")

    if not raw.strip():
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise OSError(
            f"GET {url} returned non-JSON body: {raw!r} ({exc})"
        ) from exc


def _list_projects(base_url: str, token: str) -> list[dict]:
    """List all Vikunja projects visible to the bearer token.

    Raises:
        OSError: On HTTP/network failure or non-list payload.
    """
    url = _join_url(base_url, "projects")
    payload = _http_get(url, token)
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise OSError(
            f"GET {url} returned non-list payload "
            f"(got {type(payload).__name__})"
        )
    return [item for item in payload if isinstance(item, dict)]


def _enumerate_project_tasks(
    base_url: str, token: str, project_id: int
) -> list[dict]:
    """Enumerate tasks within ``project_id``.

    Returns a list of Vikunja-API-shaped task dicts. Empty list if the
    project is empty or absent.
    """
    url = _join_url(base_url, f"projects/{project_id}/tasks")
    payload = _http_get(url, token)
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise OSError(
            f"GET {url} returned non-list payload "
            f"(got {type(payload).__name__})"
        )
    return [item for item in payload if isinstance(item, dict)]


def _fetch_comments(
    base_url: str, token: str, task_id: int
) -> list[dict]:
    """Fetch comments for a single task.

    Raises:
        OSError: On HTTP/network failure or non-list payload.
    """
    url = _join_url(base_url, f"tasks/{task_id}/comments")
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
# Comment classification + parsing (FR-007 disambiguation)
# ---------------------------------------------------------------------------


def _is_habit_comment(comment_text: str) -> bool:
    """Return True when the comment is a habit comment (second field = date).

    Per FR-007: habit comments share the ``[Felix]`` prefix but carry a
    ``YYYY-MM-DD`` date in the second pipe-delimited field. Reconcile
    must skip these silently rather than misclassifying them as
    malformed enrichment comments.

    The check is strict: the second field (after the prefix + delimiter)
    must MATCH ``^\\d{4}-\\d{2}-\\d{2}$`` exactly. Anything else returns
    False (the caller then applies the enrichment regex).
    """
    if not isinstance(comment_text, str):
        return False
    # Split on the first pipe to extract the second field.
    # Format: "[Felix] <second_field> | rest..."
    if not comment_text.startswith(FELIX_COMMENT_PREFIX):
        return False
    # Strip the prefix and any leading whitespace.
    body = comment_text[len(FELIX_COMMENT_PREFIX):].lstrip()
    parts = body.split("|", 1)
    second_field = parts[0].strip()
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}$", second_field))


def parse_comment(
    comment_text: str,
    task_id: int,
) -> tuple[Optional[dict], Optional[str]]:
    """Parse a single ``[Felix] enrichment`` comment into a JSONL record dict.

    Returns:
        ``(record, None)`` on success.
        ``(None, reason)`` when the comment is malformed (caller appends
        to the malformed list with the reason string).

    Per FR-007 disambiguation: this function assumes the caller has
    already filtered out habit comments via :func:`_is_habit_comment`.
    Non-enrichment comments that slip through still return
    ``(None, reason)`` rather than raising.

    The returned record carries ``source="backfill"`` and a
    ``timestamp_utc`` taken verbatim from the comment body (already in
    ISO-8601 Z-suffixed form per the deployed AGENTS.md vocabulary).
    """
    if not isinstance(comment_text, str):
        return None, "non-string comment body"

    match = _ENRICHMENT_COMMENT_RE.match(comment_text)
    if match is None:
        # Could be a habit comment (caller should have filtered) or some
        # other malformed shape. The caller already invoked
        # ``_is_habit_comment`` before this; if the regex misses here it's
        # truly malformed.
        return None, "regex mismatch (expected '[Felix] enrichment | <state> | <timestamp>[| <note>]')"

    state = match.group("state").strip()
    timestamp_raw = match.group("timestamp").strip()
    note = match.group("note")
    if note is not None:
        note = note.strip()
        if not note:
            note = None

    # Validate state.
    if state not in VALID_STATES:
        known = ", ".join(sorted(VALID_STATES))
        return None, f"unknown state token '{state}' (expected one of {{{known}}})"

    # Validate the timestamp parses as ISO-8601. Accept both ``Z`` suffix
    # and ``+HH:MM`` offset (deployed vocabulary uses ``Z``).
    normalized = (
        timestamp_raw[:-1] + "+00:00"
        if timestamp_raw.endswith("Z")
        else timestamp_raw
    )
    try:
        datetime.fromisoformat(normalized)
    except ValueError as exc:
        return None, f"invalid timestamp '{timestamp_raw}': {exc}"

    record = {
        "task_id": task_id,
        "state": state,
        "timestamp_utc": timestamp_raw,
        "source": "backfill",
        "schema_version": 1,
        "note": note,
    }
    return record, None


# ---------------------------------------------------------------------------
# Filtering helpers
# ---------------------------------------------------------------------------


def _felix_comments(comments: list[dict]) -> list[dict]:
    """Filter ``comments`` to those carrying the ``[Felix]`` prefix.

    Defensive: rejects non-dict / non-string comment bodies silently.
    The FR-007 disambiguation (enrichment vs habit) is applied in the
    sweep loop, AFTER this filter.
    """
    out: list[dict] = []
    for c in comments:
        if not isinstance(c, dict):
            continue
        body = c.get("comment") or c.get("body") or ""
        if isinstance(body, str) and body.startswith(FELIX_COMMENT_PREFIX):
            out.append(c)
    return out


def _record_is_in_window(record: dict, since: date) -> bool:
    """Return True when the record's ``timestamp_utc`` is >= ``since``.

    ``since`` is a calendar date in the operator's local sense (the
    ``--since`` flag's semantics per FR-008). The record's
    ``timestamp_utc`` is compared by date-prefix lex order; ISO-8601
    timestamps sort correctly as strings within a single timezone offset.
    """
    ts = record.get("timestamp_utc")
    if not isinstance(ts, str):
        return False
    # First 10 chars: YYYY-MM-DD.
    try:
        record_date = date.fromisoformat(ts[:10])
    except ValueError:
        return False
    return record_date >= since


def _parse_since(value: str) -> date:
    """Parse the ``--since`` flag as a calendar date.

    Raises:
        _DateParseError: When ``value`` does not match ``YYYY-MM-DD``.
    """
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise _DateParseError(
            f"--since '{value}' is not a valid YYYY-MM-DD date: {exc}"
        ) from None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def reconcile(
    *,
    since: date | str = DEFAULT_BACKFILL_SINCE,
    base_url: str = DEFAULT_BASE_URL,
    token_path: Path = DEFAULT_TOKEN_PATH,
    ledger_path: Path = DEFAULT_LEDGER_PATH,
    dry_run: bool = False,
    excluded_project_ids: Iterable[int] = EXCLUDED_PROJECT_IDS,
) -> ReconcileReport:
    """Sweep every Vikunja project, replay ``[Felix] enrichment`` comments into JSONL.

    See module docstring for the FR-007 disambiguation invariant and the
    Q10 / soft-fail posture for malformed comments.

    Args:
        since: Backfill cutoff. Either a ``date`` or a ``YYYY-MM-DD`` string.
            Comments older than this are skipped (FR-008).
        base_url: Vikunja API base URL.
        token_path: Path to the felix-bot bearer token file.
        ledger_path: Path to the enrichment JSONL ledger.
        dry_run: If True, no writes occur. Report still populated with
            parseable + malformed counts.
        excluded_project_ids: Projects to skip (defaults to
            :data:`EXCLUDED_PROJECT_IDS`: Goals + Habits).

    Returns:
        A populated :class:`ReconcileReport`.

    Raises:
        OSError: On Vikunja API / network failure during the sweep.
        FileNotFoundError: When ``token_path`` does not exist.
        ValueError: When ``token_path`` is empty.
        _DateParseError: When ``since`` is a string that fails ISO parsing.
    """
    started_at = time.monotonic()

    if isinstance(since, str):
        since_date = _parse_since(since)
    else:
        since_date = since
    excluded_set = frozenset(excluded_project_ids)

    token = _read_token(token_path)
    projects = _list_projects(base_url, token)

    tasks_scanned = 0
    comments_parsed = 0
    enrichment_comments_found = 0
    habit_comments_skipped = 0
    comments_replayed = 0
    comments_deduped = 0
    comments_out_of_window = 0
    malformed: list[MalformedComment] = []

    for project in projects:
        pid = project.get("id")
        if not isinstance(pid, int) or pid <= 0:
            continue
        if pid in excluded_set:
            continue

        tasks = _enumerate_project_tasks(base_url, token, pid)

        for task in tasks:
            task_id = task.get("id")
            if not isinstance(task_id, int) or task_id <= 0:
                continue

            comments = _fetch_comments(base_url, token, task_id)
            felix = _felix_comments(comments)
            if not felix:
                continue

            tasks_scanned += 1

            for c in felix:
                comments_parsed += 1
                body = c.get("comment") or c.get("body") or ""
                comment_id = c.get("id")

                # FR-007 disambiguation: habit comments skipped silently.
                if _is_habit_comment(body):
                    habit_comments_skipped += 1
                    continue

                # Parse as enrichment.
                record, reason = parse_comment(body, task_id=task_id)
                if record is None:
                    snippet = (body or "")[:160]
                    malformed.append(
                        MalformedComment(
                            task_id=task_id,
                            comment_id=(
                                comment_id
                                if isinstance(comment_id, int)
                                else None
                            ),
                            snippet=snippet,
                            reason=reason or "unknown parse failure",
                        )
                    )
                    continue

                enrichment_comments_found += 1

                # FR-008: window filter.
                if not _record_is_in_window(record, since_date):
                    comments_out_of_window += 1
                    continue

                if dry_run:
                    # Dry-run reports the upper bound — no dedup pre-check
                    # is performed because we are not writing anything.
                    comments_replayed += 1
                    continue

                # Live: invoke record_completion.record with --no-vikunja.
                # The underlying ledger append handles fcntl-locked dedup
                # via (task_id, state) — FR-009 idempotency.
                try:
                    result = rc.record(
                        task_id=record["task_id"],
                        state=record["state"],
                        source="backfill",
                        note=record.get("note"),
                        timestamp_utc=record["timestamp_utc"],
                        skip_vikunja=True,
                        ledger_path=ledger_path,
                        idempotent=True,
                    )
                except EnrichmentSchemaError as exc:
                    # Defensive: parse_comment built the record, but the
                    # schema validator may still reject it.
                    snippet = (body or "")[:160]
                    malformed.append(
                        MalformedComment(
                            task_id=task_id,
                            comment_id=(
                                comment_id
                                if isinstance(comment_id, int)
                                else None
                            ),
                            snippet=snippet,
                            reason=f"record validation rejected: {exc}",
                        )
                    )
                    continue

                if result.get("deduped"):
                    comments_deduped += 1
                else:
                    comments_replayed += 1

    duration = time.monotonic() - started_at
    return ReconcileReport(
        tasks_scanned=tasks_scanned,
        comments_parsed=comments_parsed,
        enrichment_comments_found=enrichment_comments_found,
        habit_comments_skipped=habit_comments_skipped,
        comments_replayed=comments_replayed,
        comments_deduped=comments_deduped,
        comments_out_of_window=comments_out_of_window,
        malformed_details=malformed,
        ledger_path=ledger_path,
        dry_run=dry_run,
        duration_seconds=duration,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class _ArgparseError(Exception):
    """Raised by :class:`_StructuredArgumentParser` on argparse usage errors.

    ``main()`` catches this and converts it to exit code 3 with a
    structured stderr line per ``contracts/cli.md``.
    """


class _StructuredArgumentParser(argparse.ArgumentParser):
    """``ArgumentParser`` subclass that routes usage errors through exit 3.

    Default argparse calls ``sys.exit(2)`` from ``error()``. We raise
    :class:`_ArgparseError` instead so :func:`main` can emit a structured
    JSON line on stderr and return ``3`` per ``contracts/cli.md``.
    ``--help`` still exits ``0`` because that path goes through ``exit()``
    rather than ``error()``.
    """

    def error(self, message: str) -> None:  # type: ignore[override]
        raise _ArgparseError(message)


def _build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser for the reconcile CLI."""
    parser = _StructuredArgumentParser(
        prog="python3 -m scripts.enrichment.reconcile_completions",
        description=(
            "Phase 7 enrichment backfill sweep. Replays historical "
            "[Felix] enrichment Vikunja comments into the enrichment "
            "JSONL ledger. Idempotent on re-run. Exits 0/1/3 per "
            "contracts/cli.md."
        ),
    )
    parser.add_argument(
        "--since",
        type=str,
        default=DEFAULT_BACKFILL_SINCE,
        help=(
            "Backfill cutoff in YYYY-MM-DD form. Comments older than "
            f"this are skipped (default: {DEFAULT_BACKFILL_SINCE})."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="No JSONL writes; print intent only.",
    )
    parser.add_argument(
        "--ledger-path",
        type=Path,
        default=DEFAULT_LEDGER_PATH,
        help=(
            "Path to the enrichment JSONL ledger "
            f"(default: {DEFAULT_LEDGER_PATH})."
        ),
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Vikunja API base URL (default: {DEFAULT_BASE_URL}).",
    )
    parser.add_argument(
        "--token-path",
        type=Path,
        default=DEFAULT_TOKEN_PATH,
        help=(
            "Path to the felix-bot Vikunja API token file "
            f"(default: {DEFAULT_TOKEN_PATH})."
        ),
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-comment stdout; only emit the JSON summary.",
    )
    return parser


def _emit_malformed_lines(report: ReconcileReport, *, quiet: bool) -> None:
    """Emit one MALFORMED line per malformed comment."""
    if quiet:
        return
    for m in report.malformed_details:
        print(
            f"MALFORMED task={m.task_id} "
            f'snippet="{m.snippet}" reason={m.reason}'
        )


def _emit_summary(report: ReconcileReport) -> None:
    """Emit the JSON summary line."""
    payload = {
        "tasks_scanned": report.tasks_scanned,
        "comments_parsed": report.comments_parsed,
        "enrichment_comments_found": report.enrichment_comments_found,
        "habit_comments_skipped": report.habit_comments_skipped,
        "comments_replayed": report.comments_replayed,
        "comments_deduped": report.comments_deduped,
        "comments_out_of_window": report.comments_out_of_window,
        "comments_malformed": len(report.malformed_details),
        "ledger_path": str(report.ledger_path),
        "dry_run": report.dry_run,
        "duration_s": round(report.duration_seconds, 3),
    }
    print(json.dumps(payload))


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Exit codes 0/1/3 per contracts/cli.md."""
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except _ArgparseError as exc:
        print(
            json.dumps(
                {"ok": False, "step": "argparse", "error": str(exc)}
            ),
            file=sys.stderr,
        )
        return 3

    # Validate --since up front so a bad date returns exit 3 cleanly.
    try:
        since_date = _parse_since(args.since)
    except _DateParseError as exc:
        print(
            json.dumps(
                {"ok": False, "step": "argparse", "error": str(exc)}
            ),
            file=sys.stderr,
        )
        return 3

    try:
        report = reconcile(
            since=since_date,
            base_url=args.base_url,
            token_path=args.token_path,
            ledger_path=args.ledger_path,
            dry_run=args.dry_run,
        )
    except (FileNotFoundError, ValueError) as exc:
        # Token-load failure: usage error per CLI contract.
        print(
            json.dumps(
                {"ok": False, "step": "token_load", "error": str(exc)}
            ),
            file=sys.stderr,
        )
        return 3
    except StateLogError as exc:
        # JSONL append failure mid-sweep. Surface as exit 1 — the sweep
        # aborted with partial writes (rerun is safe due to idempotency).
        print(
            json.dumps(
                {"ok": False, "step": "state_log", "error": str(exc)}
            ),
            file=sys.stderr,
        )
        return 1
    except OSError as exc:
        # Vikunja / network failure. Exit 1 per contracts/cli.md.
        print(
            json.dumps(
                {"ok": False, "step": "vikunja", "error": str(exc)}
            ),
            file=sys.stderr,
        )
        return 1

    _emit_malformed_lines(report, quiet=args.quiet)
    _emit_summary(report)
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised via subprocess
    sys.exit(main())
