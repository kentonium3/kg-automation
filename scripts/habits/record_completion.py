#!/usr/bin/env python3
"""ADR-0002 Phase 3 record_completion helper.

Three-write atomic completion record per ADR Q3-D (research D4):

    Step 1: idempotency check via ``state_log.read("habits", task_id, date, state)``
            -- if a matching record exists, exit 0 immediately (no writes).
    Step 2: POST /tasks/<id> with ``done=true`` -- Vikunja auto-advance trigger.
    Step 3: PUT /tasks/<id>/comments -- UI-visible mirror (G4: PUT not POST).
    Step 4: state_log.append("habits", record) -- canonical history.

If any step after the first succeeds while a later step fails, the helper
exits non-zero with a stderr message naming the failed step. It does NOT
attempt automatic compensation -- ``reconcile_completions.py`` is responsible
for surfacing the partial state next tick (research D4 rationale).

CLI:

    # Stdin = JSON record (same shape as state_log append payload)
    echo '{"task_id":14,"title":"Wake at 5:00 AM","date":"2026-05-20",
           "state":"complete","source":"whatsapp","note":null}' \
        | python3 -m scripts.habits.record_completion

    # Flag-driven equivalent
    python3 -m scripts.habits.record_completion \
        --task-id 14 \
        --title "Wake at 5:00 AM" \
        --date 2026-05-20 \
        --state complete \
        --source whatsapp

Exit codes (per contracts/cli.md):
    0 -- success (three writes done OR idempotent no-op detected)
    1 -- Vikunja write failure (step 2 or step 3)
    2 -- state_log write failure (Vikunja already committed -- operator triages)
    3 -- validation / usage error (bad state value, missing required arg, etc.)

Design references:
    - kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/spec.md
        FR-006, FR-007, NFR-002, C-005, C-006.
    - kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/contracts/{api,cli}.md
    - kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/data-model.md
        Entity 5 (Felix comment format).
    - kitty-specs/habits-native-repeat-jsonl-state-01KS0M59/research.md
        D4 (three-write ordering), D6 (idempotency), D10 (gotchas G3/G4).
    - docs/design/research/vikunja-task-model-research.md
        G3 (author.username attribution), G4 (PUT not POST for comments).
    - scripts/common/state_log.py (Phase 2 library used for append/read).
    - scripts/habits/migrate_schedule.py (urllib HTTP pattern reference).
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.common import state_log
from scripts.common.state_log_schema import DOMAIN_STATES


# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

#: Default Vikunja API base. Tailscale IP keeps the helper functional
#: without DNS resolution of the public hostname.
DEFAULT_BASE_URL = "http://100.92.197.90:3456/api/v1/"

#: Default location of the felix-bot Vikunja API token on office2 (mode 0600).
DEFAULT_TOKEN_PATH = "/data/services/openclaw/secrets/vikunja-api"

#: HTTP socket timeout in seconds for every Vikunja API call.
HTTP_TIMEOUT_SECONDS = 30

#: Felix comment body templates per data-model.md Entity 5. The two-segment
#: form is used when no operator note is supplied; the three-segment form
#: appends the free-form note as a final pipe-delimited segment.
COMMENT_TEMPLATE = "[Felix] {date} | {state}"
COMMENT_TEMPLATE_WITH_NOTE = "[Felix] {date} | {state} | {note}"


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------


def _join_url(base: str, path: str) -> str:
    if not base.endswith("/"):
        base = base + "/"
    return base + path.lstrip("/")


def _http_request(
    method: str,
    url: str,
    token: str,
    body: dict | None = None,
) -> tuple[int, Any]:
    """Issue an authenticated HTTP request via urllib.

    Args:
        method: ``GET``, ``POST``, ``PUT``, ``DELETE``.
        url: Fully qualified URL.
        token: Vikunja bearer token.
        body: Optional dict -- serialized to JSON if present.

    Returns:
        Tuple ``(status_code, parsed_json_or_none)``. ``parsed_json_or_none``
        is ``None`` when the response body is empty or non-JSON.

    Raises:
        OSError: On network error or non-2xx HTTP status. The message includes
            the method + URL + (when available) the server's error body so the
            operator can triage quickly.
    """
    data: bytes | None = None
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
            status = resp.status
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode("utf-8", errors="replace")
        except Exception:  # pragma: no cover -- purely defensive
            err_body = ""
        raise OSError(
            f"{method} {url} failed with HTTP {e.code}: {err_body!r}"
        ) from e
    except urllib.error.URLError as e:
        raise OSError(f"{method} {url} network failure: {e}") from e

    if status < 200 or status >= 300:
        raise OSError(f"{method} {url} returned HTTP {status}: {raw!r}")

    parsed: Any = None
    if raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            # Comment-create may return non-JSON; tolerate.
            parsed = None
    return status, parsed


# ---------------------------------------------------------------------------
# Comment formatting
# ---------------------------------------------------------------------------


def _format_comment(date: str, state: str, note: str | None) -> str:
    """Build the ``[Felix] ...`` comment body per data-model.md Entity 5.

    Args:
        date: ISO-8601 date (YYYY-MM-DD) -- the day the completion is for.
        state: The completion state ("complete", "incomplete", "skipped").
        note: Optional free-form note. ``None`` or empty string -> two-segment
            form; any non-empty string -> three-segment form.

    Returns:
        The formatted comment body string.
    """
    if note is None or not str(note).strip():
        return COMMENT_TEMPLATE.format(date=date, state=state)
    return COMMENT_TEMPLATE_WITH_NOTE.format(
        date=date, state=state, note=str(note).strip()
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    """Current UTC timestamp in ISO-8601 with offset (e.g. 2026-05-20T12:00:00+00:00)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def record(
    task_id: int,
    title: str,
    date: str,
    state: str,
    source: str,
    note: str | None = None,
    *,
    api_base_url: str,
    token: str,
) -> None:
    """Three-write atomic completion record per ADR Q3-D.

    See ``contracts/api.md`` for the full contract. Order of operations is
    non-negotiable per research D4:

    1. Build + validate the candidate record via
       ``state_log.validate_record`` -- raises ``ValueError`` on schema
       violation before any I/O.
    2. **Idempotency check**: ``state_log.read("habits", task_id, date, state)``.
       If a matching record exists, return immediately (no writes).
    3. **Step 2 (Vikunja done=true)**: POST ``/tasks/<id>`` with ``{"done": True}``.
    4. **Step 3 (Vikunja comment)**: PUT ``/tasks/<id>/comments`` with
       ``{"comment": "[Felix] <date> | <state>"}`` (G4: PUT not POST).
    5. **Step 4 (state_log)**: ``state_log.append("habits", record)``.

    Args:
        task_id: Vikunja task ID.
        title: Denormalized task title (recorded in the JSONL).
        date: ISO-8601 date (YYYY-MM-DD) -- the day the completion is for.
        state: Must be a member of ``DOMAIN_STATES["habits"]``
            (``"complete"``, ``"incomplete"``, ``"skipped"``).
        source: Identifier of the writer (e.g., ``"whatsapp"``).
        note: Optional free-form string. Appended to the Felix comment
            body if non-empty.
        api_base_url: Vikunja API base URL.
        token: Vikunja bearer token (felix-bot per Phase 1).

    Raises:
        ValueError: On invalid state, missing field, or other schema
            violation -- raised before any I/O.
        OSError: On Vikunja API failure (step 2 or 3) or state_log write
            failure (step 4). The exception message is prefixed with
            ``"step N (...)"`` so the caller can distinguish failure points.
    """
    timestamp = _now_iso()
    record_dict: dict[str, Any] = {
        "domain": "habits",
        "task_id": task_id,
        "title": title,
        "date": date,
        "state": state,
        "source": source,
        "timestamp": timestamp,
    }
    if note is not None:
        record_dict["note"] = note

    # Step 0: validate. Raises ValueError before any I/O.
    state_log.validate_record(record_dict, "habits")

    # Step 1: idempotency check. Pre-flight read of state_log; if a matching
    # (task_id, date, state) tuple already exists, exit immediately. This
    # avoids re-posting Vikunja done=true (idempotent at API level but
    # generates redundant Vikunja audit-log entries -- research D4).
    existing = state_log.read(
        "habits", task_id=task_id, date=date, state=state
    )
    if existing:
        return

    # Step 2: Vikunja done=true. POST per migrate_schedule pattern (Vikunja
    # v0.24.6 uses POST -- not PATCH -- for partial task updates).
    #
    # WHY the GET first (read-modify-write): Vikunja v0.24.6 treats POST
    # /tasks/<id> as a replacement -- fields not in the body are zeroed
    # server-side. Posting {"done": true} alone clears repeat_after and
    # repeat_mode, breaking the very auto-advance trigger this step exists
    # to fire. See #524 for the reproducer (2026-06-04 morning check-in
    # missed 4 of 7 daily habits because earlier completions had silently
    # stripped repeat_after=86400 -> 0). We GET the current task and echo
    # repeat_after/repeat_mode back so the recurrence config survives.
    done_url = _join_url(api_base_url, f"tasks/{task_id}")
    try:
        _, current = _http_request("GET", done_url, token)
    except OSError as e:
        raise OSError(f"step 2 (Vikunja GET pre-done) failed: {e}") from e
    if not isinstance(current, dict):
        raise OSError(
            f"step 2 (Vikunja GET pre-done) returned non-dict body: "
            f"{type(current).__name__}"
        )
    body = {
        "done": True,
        "repeat_after": current.get("repeat_after", 0),
        "repeat_mode": current.get("repeat_mode", 0),
    }
    try:
        _http_request("POST", done_url, token, body=body)
    except OSError as e:
        raise OSError(f"step 2 (Vikunja done=true) failed: {e}") from e

    # Step 3: Vikunja comment. G4: comment-create endpoint is PUT, not POST.
    comment_url = _join_url(api_base_url, f"tasks/{task_id}/comments")
    comment_body = _format_comment(date, state, note)
    try:
        _http_request(
            "PUT", comment_url, token, body={"comment": comment_body}
        )
    except OSError as e:
        raise OSError(f"step 3 (Vikunja comment) failed: {e}") from e

    # Step 4: state_log.append. Vikunja side is already committed; failure
    # here surfaces as exit code 2 so the operator knows JSONL is behind.
    try:
        state_log.append("habits", record_dict)
    except OSError as e:
        raise OSError(f"step 4 (state_log append) failed: {e}") from e


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _read_token(token_file: Path) -> str:
    try:
        content = token_file.read_text(encoding="utf-8").strip()
    except FileNotFoundError as e:
        raise OSError(f"Token file not found: {token_file}") from e
    except PermissionError as e:
        raise OSError(
            f"Token file not readable (permission denied): {token_file}"
        ) from e
    except OSError as e:
        raise OSError(f"Could not read token file {token_file}: {e}") from e
    if not content:
        raise OSError(f"Token file is empty: {token_file}")
    return content


def build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser for the ``python3 -m`` entry point."""
    parser = argparse.ArgumentParser(
        prog="record_completion",
        description=(
            "ADR-0002 Phase 3 three-write atomic completion helper. "
            "Reads a record from stdin (JSON object) OR from flags; "
            "performs idempotency check, Vikunja done=true POST, Vikunja "
            "comment PUT (G4), and state_log.append in that order. "
            "Exits 0 on success/no-op, 1 on Vikunja failure, 2 on "
            "state_log failure (Vikunja already committed), 3 on "
            "validation/usage error."
        ),
    )
    parser.add_argument(
        "--task-id", type=int, help="Vikunja task ID (required if no stdin)."
    )
    parser.add_argument(
        "--title", help="Task title (required if no stdin)."
    )
    parser.add_argument(
        "--date",
        help="ISO-8601 date YYYY-MM-DD (required if no stdin).",
    )
    parser.add_argument(
        "--state",
        choices=sorted(DOMAIN_STATES["habits"]),
        help=(
            "Completion state (required if no stdin; one of "
            f"{sorted(DOMAIN_STATES['habits'])})."
        ),
    )
    parser.add_argument(
        "--source",
        help="Writer identifier (e.g., 'whatsapp'). Required if no stdin.",
    )
    parser.add_argument(
        "--note", default=None,
        help="Optional free-form note appended to the Felix comment body.",
    )
    parser.add_argument(
        "--token-file",
        type=Path,
        default=Path(DEFAULT_TOKEN_PATH),
        help=(
            "Path to the Vikunja API token file "
            f"(default: {DEFAULT_TOKEN_PATH})."
        ),
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Vikunja API base URL (default: {DEFAULT_BASE_URL}).",
    )
    return parser


def _read_stdin_record() -> dict | None:
    """Read a JSON record from stdin if present; return None on empty stdin."""
    if sys.stdin.isatty():
        return None
    raw = sys.stdin.read().strip()
    if not raw:
        return None
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"stdin is not valid JSON: {e}") from e
    if not isinstance(obj, dict):
        raise ValueError(
            f"stdin record must be a JSON object (got {type(obj).__name__})"
        )
    return obj


def _build_args_from_flags(args: argparse.Namespace) -> dict:
    """Assemble the record kwargs from CLI flags. Raises ValueError on missing."""
    missing: list[str] = []
    for flag in ("task_id", "title", "date", "state", "source"):
        if getattr(args, flag) is None:
            missing.append(f"--{flag.replace('_', '-')}")
    if missing:
        raise ValueError(
            "missing required argument(s): " + ", ".join(missing)
            + " (or pipe a JSON record on stdin)"
        )
    return {
        "task_id": args.task_id,
        "title": args.title,
        "date": args.date,
        "state": args.state,
        "source": args.source,
        "note": args.note,
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. See contracts/cli.md for exit codes 0/1/2/3."""
    parser = build_parser()
    args = parser.parse_args(argv)

    # Resolve the record arguments: stdin JSON takes priority; otherwise flags.
    try:
        stdin_record = _read_stdin_record()
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 3

    if stdin_record is not None:
        kwargs: dict[str, Any] = {
            "task_id": stdin_record.get("task_id"),
            "title": stdin_record.get("title"),
            "date": stdin_record.get("date"),
            "state": stdin_record.get("state"),
            "source": stdin_record.get("source"),
            "note": stdin_record.get("note"),
        }
    else:
        try:
            kwargs = _build_args_from_flags(args)
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 3

    # Read the API token.
    try:
        token = _read_token(args.token_file)
    except OSError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 3

    # Invoke record(). Map exceptions to the documented exit codes.
    try:
        record(
            task_id=kwargs["task_id"],
            title=kwargs["title"],
            date=kwargs["date"],
            state=kwargs["state"],
            source=kwargs["source"],
            note=kwargs.get("note"),
            api_base_url=args.base_url,
            token=token,
        )
    except ValueError as e:
        print(f"ERROR: validation failed: {e}", file=sys.stderr)
        return 3
    except OSError as e:
        msg = str(e)
        if "step 4" in msg:
            # Vikunja already committed; JSONL append failed.
            print(f"ERROR: {msg}", file=sys.stderr)
            return 2
        # Step 2 or step 3 (Vikunja) failure.
        print(f"ERROR: {msg}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
