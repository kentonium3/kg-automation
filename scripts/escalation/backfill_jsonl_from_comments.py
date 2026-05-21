#!/usr/bin/env python3
"""ADR-0002 Phase 6 one-shot ``[Felix-Escalation]`` comment → JSONL backfill.

Reads existing ``[Felix-Escalation]`` comments from every escalation-subscribed
Vikunja task and replays them as escalation JSONL records via
:func:`scripts.escalation.record_completion.idempotent_record_event` with
``skip_vikunja=True`` (the ``--no-vikunja`` semantics from contracts/cli.md).

This is a one-shot helper: not invoked by cron. Re-runs are idempotent — the
:mod:`scripts.escalation.record_completion` ``(task_id, date, state)`` dedup
pre-check short-circuits subsequent attempts (returning ``deduped=True`` with
no JSONL append), and a snapshot of the pre-backfill Vikunja state is written
exactly once before the first JSONL write. ``comments_replayed`` in the
report counts only NEWLY APPENDED records; ``comments_deduped`` counts the
no-op short-circuits.

Vikunja is treated as read-only by this helper: only GET requests are issued
(project enumeration, task listing, per-task comments). No PATCH, no PUT.

Locked comment vocabulary mapping per research D5 and data-model Entity 3:

| Comment shape (``date | state | disposition``)             | JSONL ``state`` | Params                                                        |
|------------------------------------------------------------|-----------------|---------------------------------------------------------------|
| ``YYYY-MM-DD | level-1 | sent``                            | ``level_sent``  | ``level: 1``                                                  |
| ``YYYY-MM-DD | level-2 | sent``                            | ``level_sent``  | ``level: 2``                                                  |
| ``YYYY-MM-DD | snoozed:Nd | acknowledged``                 | ``snoozed``     | ``snooze_days: N``, ``snooze_until: date + N days``           |
| ``YYYY-MM-DD | dismissed | acknowledged``                  | ``dismissed``   | —                                                             |
| ``YYYY-MM-DD | done | acknowledged``                       | ``done``        | —                                                             |
| ``YYYY-MM-DD | rescheduled:YYYY-MM-DD | acknowledged``     | ``rescheduled`` | ``reschedule_to: <date>``                                     |

Malformed comments (parse fails, unknown vocabulary, missing fields, invalid
dates) are NEVER replayed. They are collected with a snippet (first 80 chars)
and a parse reason and surfaced in the BackfillReport / stdout. Per research
D5 + Phase 4 cycle 2 lesson: report only, never replay, never file hard-fail
bugs. Hard-fail bug filing for malformed records is owned by the live
runtime path (WP04), not by the one-shot backfill.

Projects ``id=11`` (Goals) and ``id=13`` (Habits) are excluded from
``backfill_all`` per ``scripts/openclaw/skills/escalation/SKILL.md`` § 1
("What does NOT qualify").

Contracts:
  - kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/contracts/api.md
        ``backfill_project``, ``BackfillReport``, ``MalformedComment``
  - kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/contracts/cli.md
        ``--project-id`` / ``--all`` / ``--dry-run`` / ``--include-resolved``,
        exit codes 0/1/2/3
  - kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/data-model.md
        Entity 3 (comment vocabulary), Entity 4 (snapshot schema)
  - kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/research.md
        D5 (vocabulary mapping, malformed-comment handling)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from scripts.escalation.record_completion import (
    EscalationSchemaError,
    StateLogError,
    idempotent_record_event,
)


__all__ = [
    "DEFAULT_BASE_URL",
    "DEFAULT_TOKEN_PATH",
    "FELIX_COMMENT_PREFIX",
    "JSONL_STATE_DIR",
    "SNAPSHOT_PATH",
    "SNAPSHOT_VERSION",
    "EXCLUDED_PROJECT_IDS",
    "BackfillReport",
    "MalformedComment",
    "parse_comment",
    "backfill_project",
    "backfill_all",
    "main",
]


# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

#: Default Vikunja API base URL (Tailscale IP — resolves without DNS).
DEFAULT_BASE_URL = "http://100.92.197.90:3456/api/v1/"

#: Default location of the felix-bot Vikunja API token on office2 (mode 0600).
DEFAULT_TOKEN_PATH = Path("/data/services/openclaw/secrets/vikunja-api")

#: Per-project JSONL state directory. Mirrors
#: ``scripts.escalation.record_completion.JSONL_STATE_DIR`` exactly so the
#: dedup pre-check inside ``idempotent_record_event`` finds prior
#: backfilled lines.
JSONL_STATE_DIR = Path("/data/services/openclaw/state/escalation")

#: Pre-backfill snapshot path per data-model Entity 4. Written ONCE before
#: any JSONL append. The snapshot is the operator's rollback substrate.
SNAPSHOT_PATH = JSONL_STATE_DIR / "pre-phase6-snapshot.json"

#: Mirrors SKILL.md § 3 prefix exactly.
FELIX_COMMENT_PREFIX = "[Felix-Escalation]"

#: Snapshot schema version (Entity 4).
SNAPSHOT_VERSION = 1

#: HTTP socket timeout in seconds for every Vikunja API call.
HTTP_TIMEOUT_SECONDS = 30

#: Project ids excluded from ``backfill_all`` per SKILL.md § 1.
#: 11 = Goals (anchors, not tasks); 13 = Habits (managed by felix-admin-habits).
EXCLUDED_PROJECT_IDS: frozenset[int] = frozenset({11, 13})

#: Vikunja-style "no due date" sentinel (kept for parity with reconcile).
_VIKUNJA_NULL_DATE_SENTINEL = "0001-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# Comment-parsing regex set (data-model Entity 3 + research D5)
# ---------------------------------------------------------------------------

#: Outer comment shape: ``[Felix-Escalation] YYYY-MM-DD | <state> | <disposition>``.
#: The state token may contain ``:`` (e.g., ``snoozed:3d``) and digits but not
#: the pipe separator. Disposition is a single word.
_COMMENT_RE = re.compile(
    r"^\[Felix-Escalation\] (?P<date>\d{4}-\d{2}-\d{2}) \| "
    r"(?P<state>[^|]+?) \| (?P<disposition>\w+)$"
)

#: Inner state-token shapes (data-model Entity 3 rows).
_LEVEL_RE = re.compile(r"^level-([12])$")
_SNOOZED_RE = re.compile(r"^snoozed:(\d+)d$")
_RESCHEDULED_RE = re.compile(r"^rescheduled:(\d{4}-\d{2}-\d{2})$")


# ---------------------------------------------------------------------------
# Result dataclasses (contracts/api.md)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MalformedComment:
    """One malformed comment surfaced in the backfill report.

    Per data-model Entity 3 § "Malformed comment handling" + research D5: the
    comment is NEVER replayed; the operator sees the snippet + reason in the
    summary and decides whether to repair manually.

    Attributes:
        task_id: Vikunja task id containing the malformed comment.
        project_id: Vikunja project id containing the task.
        comment_id: Vikunja comment id (or ``None`` if the comment shape
            didn't even carry an id field — defensive).
        snippet: First 80 characters of the offending comment body.
        reason: Short parse-error string ("split mismatch", "unknown state
            token 'X'", "invalid date", "invalid snooze days", ...).
    """

    task_id: int
    project_id: int
    comment_id: int | None
    snippet: str
    reason: str


@dataclass(frozen=True, slots=True)
class BackfillReport:
    """Summary of one ``backfill_project`` invocation.

    Attributes:
        project_id: Vikunja project id swept.
        project_slug: Project slug used for the JSONL filename
            (per research D2 — uses ``project-<id>`` keyed naming in this
            phase since the filename is keyed on integer id; ``project_slug``
            here mirrors that derivation for symmetry with the contract).
        tasks_scanned: Number of tasks enumerated in the project that carried
            at least one ``[Felix-Escalation]`` comment (or all tasks scanned,
            for accurate reporting on dry-run paths).
        comments_parsed: Total number of ``[Felix-Escalation]``-prefixed
            comments inspected (parseable + malformed).
        comments_replayed: Number of NEWLY APPENDED JSONL records (live
            runs) OR number that would have been written if the on-disk
            state were empty (dry-run). On a clean JSONL this equals the
            number of parseable comments; on a rerun against an already-
            backfilled JSONL it is 0 because every record short-circuits
            at ``idempotent_record_event`` with ``deduped=True``.
        comments_deduped: Number of parseable comments that were skipped
            on append because an existing JSONL record matched
            ``(task_id, date, state)``. Informational — not part of the
            contract acceptance, but useful for operator visibility on
            reruns. Always ``0`` on dry-run (no pre-check is performed).
        comments_malformed: Length of ``malformed_details``.
        malformed_details: Per-malformed-comment surface for the operator.
        snapshot_path: Absolute path of the pre-backfill snapshot
            (or ``None`` on dry-run).
        jsonl_path: Per-project JSONL file path (where records are/were
            appended).
        dry_run: ``True`` if no writes occurred this invocation.
    """

    project_id: int
    project_slug: str
    tasks_scanned: int
    comments_parsed: int
    comments_replayed: int
    comments_malformed: int
    malformed_details: list[MalformedComment] = field(default_factory=list)
    snapshot_path: Path | None = None
    jsonl_path: Path = field(
        default_factory=lambda: JSONL_STATE_DIR / "unknown.jsonl"
    )
    dry_run: bool = False
    comments_deduped: int = 0


# ---------------------------------------------------------------------------
# Internal exceptions (CLI exit-code routing)
# ---------------------------------------------------------------------------


class _SnapshotError(OSError):
    """Snapshot write failure (exit-2 surface)."""


# ---------------------------------------------------------------------------
# HTTP helpers (urllib-only, mirrors habits backfill)
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
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
            status = resp.status
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode("utf-8", errors="replace")
        except Exception:  # pragma: no cover - defensive
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
        raise OSError(
            f"GET {url} returned non-JSON body: {raw!r} ({e})"
        ) from e


# ---------------------------------------------------------------------------
# Comment parser (data-model Entity 3 vocabulary)
# ---------------------------------------------------------------------------


def _parse_state_token(state_token: str, comment_date: str) -> tuple[
    str, dict[str, Any]
]:
    """Parse a state token into ``(jsonl_state, params)``.

    Raises:
        ValueError: With a short reason string on parse failure. Caller wraps
            into a :class:`MalformedComment`.
    """
    # level-1 / level-2
    m = _LEVEL_RE.match(state_token)
    if m is not None:
        return "level_sent", {"level": int(m.group(1))}

    # snoozed:Nd
    m = _SNOOZED_RE.match(state_token)
    if m is not None:
        days = int(m.group(1))
        if days <= 0:
            raise ValueError(
                f"invalid snooze days: {days} (must be positive)"
            )
        # snooze_until = comment_date + N days (FR-004 write-time semantics
        # applied at backfill time; the comment_date is the authoritative
        # write-time for historical records).
        try:
            base = date.fromisoformat(comment_date)
        except ValueError as exc:
            raise ValueError(
                f"invalid date '{comment_date}': {exc}"
            ) from exc
        snooze_until = (base + timedelta(days=days)).isoformat()
        return "snoozed", {
            "snooze_days": days,
            "snooze_until": snooze_until,
        }

    # dismissed
    if state_token == "dismissed":
        return "dismissed", {}

    # done
    if state_token == "done":
        return "done", {}

    # rescheduled:YYYY-MM-DD
    m = _RESCHEDULED_RE.match(state_token)
    if m is not None:
        reschedule_to = m.group(1)
        # Validate parseability — surfaces 2026-13-99 etc. as malformed.
        try:
            date.fromisoformat(reschedule_to)
        except ValueError as exc:
            raise ValueError(
                f"invalid reschedule_to '{reschedule_to}': {exc}"
            ) from exc
        return "rescheduled", {"reschedule_to": reschedule_to}

    # Special-case: bare ``snoozed:abcd`` etc. — the snoozed-prefix branch
    # signals the operator-friendly reason rather than the generic
    # "unknown state" fallback. Detect the prefix without consuming the
    # full pattern.
    if state_token.startswith("snoozed:"):
        raise ValueError(
            f"invalid snooze days in state token '{state_token}'"
        )
    if state_token.startswith("rescheduled:"):
        raise ValueError(
            f"invalid reschedule_to in state token '{state_token}'"
        )

    raise ValueError(f"unknown state token '{state_token}'")


def parse_comment(
    comment_text: str,
    task_id: int,
    project_id: int,
    task_title: str,
    *,
    comment_created: str | None = None,
) -> dict | None:
    """Parse a single ``[Felix-Escalation]`` comment body into a JSONL record.

    Returns:
        A record dict ready for :func:`idempotent_record_event` on parseable input,
        or ``None`` if the comment does not match the locked Entity 3
        vocabulary. The caller appends ``None``-returning comments to the
        malformed list (with a snippet + parse reason).

    The returned record carries ``source="backfill"``. The ``timestamp`` is
    derived from ``comment_created`` when present (preferred — preserves the
    write-time wall-clock), else synthesized as ``<date>T12:00:00+00:00``
    (noon UTC per research D5).
    """
    if not isinstance(comment_text, str):
        return None
    if not comment_text.startswith(FELIX_COMMENT_PREFIX):
        return None

    match = _COMMENT_RE.match(comment_text)
    if match is None:
        return None

    date_str = match.group("date")
    state_token = match.group("state")
    # disposition is not currently semantically meaningful — every emitted
    # token has a fixed disposition in v1 (see SKILL.md § 3). We accept any
    # word here; the state-token branch is what determines validity.

    # Validate the comment date itself.
    try:
        date.fromisoformat(date_str)
    except ValueError:
        return None

    try:
        jsonl_state, params = _parse_state_token(state_token, date_str)
    except ValueError:
        return None

    # Compose timestamp.
    timestamp = _coerce_iso8601_with_offset(comment_created) or (
        f"{date_str}T12:00:00+00:00"
    )

    record: dict[str, Any] = {
        "domain": "escalation",
        "task_id": task_id,
        "project_id": project_id,
        "title": task_title,
        "date": date_str,
        "state": jsonl_state,
        "source": "backfill",
        "timestamp": timestamp,
        "note": None,
    }
    record.update(params)
    return record


def _coerce_iso8601_with_offset(value: str | None) -> str | None:
    """Return ``value`` if it parses as an ISO-8601 datetime; else ``None``.

    Vikunja serializes comment timestamps as ``2026-05-15T08:00:00Z``. The
    Phase 2 validator accepts both ``...+00:00`` and trailing ``Z``; here we
    normalize ``Z`` to ``+00:00`` so the persisted JSONL ``timestamp`` field
    matches the rest of the codebase's convention.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return normalized


def _classify_parse_failure(
    comment_text: str,
) -> str:
    """Return a short parse-failure reason for the malformed-list entry.

    Mirrors the branches in :func:`parse_comment` so the operator sees a
    targeted message ("split mismatch", "unknown state token", "invalid
    date", "invalid snooze days", ...) instead of a generic "malformed".
    """
    if not isinstance(comment_text, str):
        return "non-string comment body"
    if not comment_text.startswith(FELIX_COMMENT_PREFIX):
        return "missing [Felix-Escalation] prefix"

    match = _COMMENT_RE.match(comment_text)
    if match is None:
        return "split mismatch (expected 'date | state | disposition')"

    date_str = match.group("date")
    state_token = match.group("state")

    try:
        date.fromisoformat(date_str)
    except ValueError as exc:
        return f"invalid date '{date_str}': {exc}"

    try:
        _parse_state_token(state_token, date_str)
    except ValueError as exc:
        return str(exc)

    # Should not reach here — parse_comment would have succeeded. Defensive.
    return "unknown parse failure"  # pragma: no cover


# ---------------------------------------------------------------------------
# Snapshot writer (data-model Entity 4)
# ---------------------------------------------------------------------------


def _write_snapshot(snapshot_data: dict, snapshot_path: Path) -> None:
    """Atomically write ``snapshot_data`` to ``snapshot_path``.

    Pattern: write to ``<path>.tmp``, fsync, atomic rename. Per data-model
    Entity 4. The parent directory is created if missing.

    Raises:
        _SnapshotError: On any filesystem error (parent missing, permission,
            disk full, fsync failure, etc.). The CLI surfaces this as exit
            code 2.
    """
    try:
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = snapshot_path.with_suffix(snapshot_path.suffix + ".tmp")
        fd = os.open(
            str(tmp_path),
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            0o664,
        )
        try:
            body = json.dumps(
                snapshot_data, ensure_ascii=False, indent=2, sort_keys=False
            )
            os.write(fd, body.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp_path, snapshot_path)
    except OSError as exc:
        raise _SnapshotError(
            f"snapshot write failed: {snapshot_path}: {exc}"
        ) from exc


def _build_snapshot(
    tasks_with_comments: list[dict],
    base_url: str,
) -> dict:
    """Build the snapshot dict per data-model Entity 4."""
    tasks_block: list[dict] = []
    for task in tasks_with_comments:
        task_id = task["id"]
        project_id = task.get("project_id")
        title = task.get("title") or ""
        # Vikunja UI URL (best-effort; per data-model Entity 4 example).
        # Strip the trailing ``api/v1/`` if the caller passed a base URL with
        # that suffix.
        ui_base = base_url
        if ui_base.endswith("/"):
            ui_base = ui_base[:-1]
        ui_base = re.sub(r"/api/v\d+$", "", ui_base)
        vikunja_url = f"{ui_base}/tasks/{task_id}"
        felix_comments_block = [
            {
                "comment_id": c.get("id"),
                "created": c.get("created"),
                "comment": c.get("comment", ""),
            }
            for c in task.get("_felix_comments", [])
        ]
        tasks_block.append(
            {
                "task_id": task_id,
                "project_id": project_id,
                "title": title,
                "vikunja_url": vikunja_url,
                "felix_comments": felix_comments_block,
            }
        )
    return {
        "snapshot_version": SNAPSHOT_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        ),
        "tool_version": "scripts/escalation/backfill_jsonl_from_comments.py",
        "tasks": tasks_block,
    }


# ---------------------------------------------------------------------------
# Vikunja access helpers
# ---------------------------------------------------------------------------


def _enumerate_project_tasks(
    base_url: str, token: str, project_id: int
) -> list[dict]:
    """Enumerate tasks within ``project_id``.

    Returns a list of Vikunja-API-shaped task dicts. Empty list if the project
    is empty or absent. Per Verified API Gotcha G5 / G6 (see
    ``reference_vikunja_filter_gotchas.md``): no server-side ``filter=``
    expression; client-side filtering only.
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


def _is_terminal(task: dict) -> bool:
    """Return True if Vikunja task is terminal (``done=True``).

    "Resolved" in this helper means ``done=True``. ``--include-resolved``
    overrides the default skip.
    """
    return bool(task.get("done", False))


def _project_slug(project_id: int) -> str:
    """Return the per-project slug used for filename / report keys.

    Per research D2 this phase keys the JSONL filename on the integer id
    (slug derivation requires an extra API hop). The "slug" in the
    BackfillReport is the same string used in record_completion's
    ``_jsonl_path_for_record`` for symmetry with the live runtime.
    """
    return f"project-{project_id}"


def _jsonl_path_for_project(project_id: int) -> Path:
    """Return the per-project JSONL path used by ``record_event``.

    Mirrors :func:`scripts.escalation.record_completion._jsonl_path_for_record`
    so the snapshot/report point at the same on-disk file the live runtime
    writes.
    """
    return JSONL_STATE_DIR / f"project-{project_id}-escalation-history.jsonl"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _felix_comments(comments: list[dict]) -> list[dict]:
    """Filter ``comments`` to those carrying the ``[Felix-Escalation]`` prefix.

    Defensive: rejects non-dict / non-string comment bodies silently.
    """
    out: list[dict] = []
    for c in comments:
        if not isinstance(c, dict):
            continue
        body = c.get("comment")
        if isinstance(body, str) and body.startswith(FELIX_COMMENT_PREFIX):
            out.append(c)
    return out


def backfill_project(
    project_id: int,
    *,
    base_url: str = DEFAULT_BASE_URL,
    token_path: Path = DEFAULT_TOKEN_PATH,
    dry_run: bool = False,
    include_resolved: bool = False,
) -> BackfillReport:
    """Replay ``[Felix-Escalation]`` comments in ``project_id`` into JSONL.

    See module docstring for the locked vocabulary mapping + ordering
    invariants. Snapshot is written BEFORE any JSONL append on a live run
    (per data-model Entity 4 + spec FR-006). Dry-run skips both the snapshot
    write and the JSONL writes but still walks every comment and populates
    the full ``BackfillReport`` (parseable counts + malformed list).

    Args:
        project_id: Vikunja project id to sweep.
        base_url: Vikunja API base URL. Default is the office2 Tailscale IP.
        token_path: Path to the felix-bot bearer token file.
        dry_run: If True, no writes occur. Report still populated.
        include_resolved: If True, also replay comments on terminal
            (``done=True``) tasks. Default False — terminal tasks don't need
            replay (derive_state has no work to do on them).

    Returns:
        A :class:`BackfillReport`.

    Raises:
        OSError: On Vikunja API failure (per-project enumeration / comment
            fetch / token read).
        _SnapshotError: On snapshot write failure (live runs only).
        StateLogError: On JSONL append failure (live runs only — surfaces
            via :func:`idempotent_record_event`).
    """
    token = _read_token(token_path)

    tasks = _enumerate_project_tasks(base_url, token, project_id)

    # First pass: collect comments + apply include_resolved filter. This
    # walk also feeds the snapshot block.
    tasks_with_felix: list[dict] = []
    comments_parsed = 0
    malformed: list[MalformedComment] = []

    # Collect parseable records here so we can write the snapshot BEFORE the
    # first JSONL append (data-model Entity 4 invariant).
    parseable_records: list[dict] = []

    for task in tasks:
        task_id = task.get("id")
        if not isinstance(task_id, int) or task_id <= 0:
            # Defensive: skip tasks lacking an id. The Vikunja API should
            # never return one, but record_completion's per-project path
            # requires a positive int.
            continue
        title = task.get("title") or ""

        try:
            comments = _fetch_comments(base_url, token, task_id)
        except OSError:
            # Per-task fetch failure: re-raise to caller. We do NOT silently
            # swallow because a partial backfill that misses some tasks is
            # worse than an aborted one (the operator can retry; partial
            # passes would silently lose history).
            raise

        felix = _felix_comments(comments)
        if not felix:
            continue

        tasks_with_felix.append({**task, "_felix_comments": felix})

        # Skip terminal tasks unless --include-resolved is set.
        if _is_terminal(task) and not include_resolved:
            continue

        for c in felix:
            comments_parsed += 1
            body = c.get("comment", "")
            comment_id = c.get("id")
            comment_created = c.get("created")
            record = parse_comment(
                body,
                task_id=task_id,
                project_id=project_id,
                task_title=title,
                comment_created=comment_created,
            )
            if record is None:
                snippet = (body or "")[:80]
                reason = _classify_parse_failure(body)
                malformed.append(
                    MalformedComment(
                        task_id=task_id,
                        project_id=project_id,
                        comment_id=(
                            comment_id
                            if isinstance(comment_id, int)
                            else None
                        ),
                        snippet=snippet,
                        reason=reason,
                    )
                )
                continue
            parseable_records.append(record)

    # Snapshot BEFORE any JSONL write (live only).
    snapshot_path: Path | None = None
    if not dry_run and tasks_with_felix:
        snapshot_data = _build_snapshot(tasks_with_felix, base_url)
        _write_snapshot(snapshot_data, SNAPSHOT_PATH)
        snapshot_path = SNAPSHOT_PATH

    # JSONL replay. Idempotency uses ``idempotent_record_event``, which
    # pre-checks ``(task_id, date, state)`` against the on-disk JSONL and
    # returns ``deduped=True`` without writing when a prior record exists.
    # ``comments_replayed`` counts ONLY newly appended records so a rerun
    # against an already-backfilled JSONL reports 0 — per the WP06
    # idempotency contract (see review-cycle-1.md).
    comments_replayed = 0
    comments_deduped = 0
    if not dry_run:
        for record in parseable_records:
            try:
                result = idempotent_record_event(
                    record,
                    base_url=base_url,
                    token_path=token_path,
                    skip_vikunja=True,
                )
            except EscalationSchemaError:
                # Defensive: parse_comment built the record, but the Phase 2
                # validator (or escalation per-event_type validator) may
                # reject it (e.g., invalid timestamp normalization). Treat
                # as malformed-after-parse: surface in the report and skip.
                snippet = (record.get("note") or "")[:80]
                malformed.append(
                    MalformedComment(
                        task_id=record["task_id"],
                        project_id=project_id,
                        comment_id=None,
                        snippet=snippet,
                        reason="record validation rejected post-parse",
                    )
                )
                continue
            if result.get("deduped"):
                comments_deduped += 1
            else:
                comments_replayed += 1
    else:
        # Dry-run reports the upper-bound (parseable comment count). No
        # pre-check is performed because we are not writing anything; the
        # operator interprets this as "would write up to N records on a
        # clean JSONL". ``comments_deduped`` stays at 0.
        comments_replayed = len(parseable_records)

    return BackfillReport(
        project_id=project_id,
        project_slug=_project_slug(project_id),
        tasks_scanned=len(tasks_with_felix),
        comments_parsed=comments_parsed,
        comments_replayed=comments_replayed,
        comments_malformed=len(malformed),
        malformed_details=malformed,
        snapshot_path=snapshot_path,
        jsonl_path=_jsonl_path_for_project(project_id),
        dry_run=dry_run,
        comments_deduped=comments_deduped,
    )


def backfill_all(
    *,
    base_url: str = DEFAULT_BASE_URL,
    token_path: Path = DEFAULT_TOKEN_PATH,
    dry_run: bool = False,
    include_resolved: bool = False,
) -> list[BackfillReport]:
    """Sweep every escalation-eligible Vikunja project.

    Excludes ``project_id`` in :data:`EXCLUDED_PROJECT_IDS` (Goals + Habits)
    per ``scripts/openclaw/skills/escalation/SKILL.md`` § 1.

    Returns:
        One :class:`BackfillReport` per project visited.
    """
    token = _read_token(token_path)
    projects = _list_projects(base_url, token)

    reports: list[BackfillReport] = []
    for project in projects:
        pid = project.get("id")
        if not isinstance(pid, int) or pid <= 0:
            continue
        if pid in EXCLUDED_PROJECT_IDS:
            continue
        report = backfill_project(
            pid,
            base_url=base_url,
            token_path=token_path,
            dry_run=dry_run,
            include_resolved=include_resolved,
        )
        reports.append(report)
    return reports


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m scripts.escalation.backfill_jsonl_from_comments",
        description=(
            "ADR-0002 Phase 6 one-shot helper: replay [Felix-Escalation] "
            "Vikunja comments into per-project escalation JSONL history. "
            "Idempotent on re-run via idempotent_record_event's (task_id, date, state) "
            "dedup. See kitty-specs/migrate-escalation-to-jsonl-state-model-"
            "01KS5R4D/ for the contract + record schema."
        ),
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument(
        "--project-id",
        type=int,
        help="Single-project sweep (Vikunja project id).",
    )
    target.add_argument(
        "--all",
        action="store_true",
        help=(
            "Sweep every project (excluding Goals=11 and Habits=13 per "
            "SKILL.md § 1)."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "No snapshot, no JSONL writes; full malformed-comment report."
        ),
    )
    parser.add_argument(
        "--include-resolved",
        action="store_true",
        help=(
            "Also replay comments on tasks that are currently done. "
            "(Default: skip terminal tasks.)"
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
    return parser


def _print_malformed(reports: list[BackfillReport]) -> None:
    """Per-malformed-comment stdout line per contracts/cli.md."""
    for report in reports:
        for m in report.malformed_details:
            print(
                f"MALFORMED task={m.task_id} project={m.project_id} "
                f'snippet="{m.snippet}" reason={m.reason}'
            )


def _summary_block(
    reports: list[BackfillReport], *, aggregate: bool = False
) -> str:
    """Final summary JSON block per contracts/cli.md.

    ``--project-id`` runs emit a single flat summary; ``--all`` runs emit a
    list under ``projects`` plus a totals roll-up so the operator can eyeball
    the whole sweep even when only one project survives the
    Goals/Habits filter.
    """
    if not aggregate and len(reports) == 1:
        r = reports[0]
        return json.dumps(
            {
                "project_id": r.project_id,
                "tasks_scanned": r.tasks_scanned,
                "comments_parsed": r.comments_parsed,
                "comments_replayed": r.comments_replayed,
                "comments_deduped": r.comments_deduped,
                "comments_malformed": r.comments_malformed,
                "snapshot_path": (
                    str(r.snapshot_path) if r.snapshot_path else None
                ),
                "jsonl_path": str(r.jsonl_path),
                "dry_run": r.dry_run,
            },
            indent=2,
        )
    totals = {
        "tasks_scanned": sum(r.tasks_scanned for r in reports),
        "comments_parsed": sum(r.comments_parsed for r in reports),
        "comments_replayed": sum(r.comments_replayed for r in reports),
        "comments_deduped": sum(r.comments_deduped for r in reports),
        "comments_malformed": sum(r.comments_malformed for r in reports),
    }
    return json.dumps(
        {
            "projects": [
                {
                    "project_id": r.project_id,
                    "tasks_scanned": r.tasks_scanned,
                    "comments_parsed": r.comments_parsed,
                    "comments_replayed": r.comments_replayed,
                    "comments_deduped": r.comments_deduped,
                    "comments_malformed": r.comments_malformed,
                    "snapshot_path": (
                        str(r.snapshot_path) if r.snapshot_path else None
                    ),
                    "jsonl_path": str(r.jsonl_path),
                    "dry_run": r.dry_run,
                }
                for r in reports
            ],
            "totals": totals,
        },
        indent=2,
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Exit codes 0/1/2/3 per contracts/cli.md."""
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        # argparse's default error path exits with 2; we map to 3 per
        # contracts/cli.md (validation/usage error). ``--help`` /
        # ``--version`` exit 0 which we honor unchanged.
        code = exc.code if isinstance(exc.code, int) else 3
        if code == 2:
            return 3
        return code

    try:
        if args.all:
            reports = backfill_all(
                base_url=args.base_url,
                token_path=args.token_path,
                dry_run=args.dry_run,
                include_resolved=args.include_resolved,
            )
        else:
            reports = [
                backfill_project(
                    args.project_id,
                    base_url=args.base_url,
                    token_path=args.token_path,
                    dry_run=args.dry_run,
                    include_resolved=args.include_resolved,
                )
            ]
    except (FileNotFoundError, ValueError) as exc:
        # Token file missing / empty: usage error (exit 3).
        print(
            json.dumps(
                {"ok": False, "step": "token_load", "error": str(exc)}
            ),
            file=sys.stderr,
        )
        return 3
    except _SnapshotError as exc:
        print(
            json.dumps(
                {"ok": False, "step": "snapshot", "error": str(exc)}
            ),
            file=sys.stderr,
        )
        return 2
    except StateLogError as exc:
        print(
            json.dumps(
                {"ok": False, "step": "state_log", "error": str(exc)}
            ),
            file=sys.stderr,
        )
        return 2
    except OSError as exc:
        # Vikunja API failure during enumeration / fetch.
        print(
            json.dumps(
                {"ok": False, "step": "vikunja", "error": str(exc)}
            ),
            file=sys.stderr,
        )
        return 1

    _print_malformed(reports)
    print(_summary_block(reports, aggregate=bool(args.all)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
