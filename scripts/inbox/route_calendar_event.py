#!/usr/bin/env python3
"""Validate and normalize a `CalendarPayload` for downstream delegation.

CLI surface (per FR-005 / contracts/helper-cli.md):

    python3 -m scripts.inbox.route_calendar_event --payload-file <abs-path>

Behavior:
  * Read JSON from ``--payload-file``.
  * Validate that ``title`` and ``start`` are present and parseable
    (ISO 8601 datetime). Optional ``end`` must also be parseable when
    supplied.
  * On valid: write the normalized payload to stdout as JSON. ``end`` is
    filled in (start + 1 hour) when absent so downstream consumers always
    have an explicit interval. Optional fields (``location``,
    ``description``) pass through verbatim.
  * With ``--as-delegation-payload --source-path <abs>``: emit the
    ``create_calendar_event`` delegation envelope (the felix-admin-calendar
    contract shape) instead of the bare normalized payload, so capture can
    forward it verbatim (capture -> main -> felix-admin-calendar). The
    deterministic field mapping lives here, not in the agent prompt.
  * With ``--create --source-path <abs>`` (D4, closes #679): validate ->
    normalize -> build the ``create_calendar_event`` envelope -> invoke the
    calendar helper (``python3 -m scripts.google.calendar_helper create
    --payload-file <tmp> --idempotency-key <source_inbox_path> --json``) IN
    PROCESS as a subprocess -> emit a single result JSON on stdout:
    ``{"status": "created", "event_id": ..., "html_link": ...}`` on success,
    ``{"status": "error", ...}`` on helper failure (surfaced verbatim, never
    faked — #683), or ``{"status": "needs_clarification", "missing": [...]}``
    when the payload is invalid (the helper is NOT called in that case). This
    is the single deterministic command capture runs — no agent-to-agent hop.
  * On invalid: write ``{"error": "invalid_payload", "missing": [...]}``
    to stderr; exit 1. (In ``--create`` mode an invalid payload is reported as
    a ``needs_clarification`` result on stdout with exit 0, so capture branches
    on ``status`` rather than exit code.)
  * On missing / malformed file: write a structured error JSON to stderr;
    exit 1.

Design-time note (per `[[feedback_design_phase_research]]`): the spec and
WP prompt referenced
``scripts.calendar_routing.validate_calendar_event.validate_payload`` as
the validation surface. The actual module exposes ``validate(block)`` over
an ``ExtractedCalendarBlock`` shape (with ``start_natural``, ``tick_iso``,
``source_inbox_path``, ``source_block_index``) — a different validator
purpose-built to lift natural-language fragments into a Google Calendar
payload. That helper is unsuitable for validating an already-structured
``CalendarPayload`` whose datetimes are ISO 8601 strings. We inline the
small `CalendarPayload` validator here. The mismatch is documented so a
later mission can decide whether to (a) collapse both validators or (b)
rename one for clarity.

Stdlib only (NFR-002). No requests/httpx/pydantic/PyYAML/frontmatter.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

REQUIRED_FIELDS = ("title", "start")
OPTIONAL_FIELDS = ("end", "location", "description")
DEFAULT_DURATION = timedelta(hours=1)

# Contract defaults for the capture -> main -> felix-admin-calendar delegation
# envelope (`create_calendar_event`). Per
# kitty-specs/.../contracts/capture_to_main_calendar_payload.md, capture resolves
# these defaults before dispatch. The field mapping lives here (deterministic
# helper) rather than in the agent prompt, per the two-layer doctrine — the LLM
# must never do this mechanical transform (#661/#662 haiku-fragility class).
DELEGATION_ACTION = "create_calendar_event"
DEFAULT_CALENDAR_ID = "primary"
# Credential-set selector for the direct-API calendar helper (D5). Flipped from
# the legacy gog ``kent@intentional.biz`` value to ``personal`` — the account
# RFC #681 proved and the new happy path targets. Adding the intentional.biz
# account later is purely additive (drop creds + pass ``--account intentional``);
# no code change here.
DEFAULT_ACCOUNT = "personal"

# The calendar helper (WP02) invoked in --create mode. Kept as a module-level
# constant so tests can monkeypatch the subprocess call site.
CALENDAR_HELPER_MODULE = "scripts.google.calendar_helper"


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------


def _parse_iso(value: object) -> Optional[datetime]:
    """Parse an ISO 8601 datetime string; return None when unparseable.

    Accepts ``2026-06-12T15:00:00-04:00`` and ``2026-06-12T15:00:00+00:00``.
    Also accepts the ``Z`` suffix form by translating it to ``+00:00`` so
    the helper handles upstream payloads that use Zulu time.
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    # `fromisoformat` in 3.10 doesn't accept the trailing "Z"; rewrite it.
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _format_iso(dt: datetime) -> str:
    """Render an aware datetime in the same `2026-06-12T15:00:00-04:00` shape
    the rest of the pipeline emits.

    Uses ``isoformat(timespec="seconds")`` so we always emit second-level
    precision (matches the input shape Kent's payloads produce).
    """
    return dt.isoformat(timespec="seconds")


def validate_payload(payload: object) -> tuple[bool, list[str]]:
    """Return ``(is_valid, missing)`` for a CalendarPayload-shaped object.

    ``missing`` enumerates every required field that is absent, blank, or
    unparseable. The optional ``end`` field is reported under ``missing``
    only when SUPPLIED-BUT-UNPARSEABLE (an absent ``end`` is not missing —
    it gets defaulted later by ``normalize_payload``).
    """
    if not isinstance(payload, dict):
        return False, ["payload_not_object"]

    missing: list[str] = []

    title = payload.get("title")
    if not isinstance(title, str) or not title.strip():
        missing.append("title")

    if _parse_iso(payload.get("start")) is None:
        missing.append("start")

    if "end" in payload and _parse_iso(payload.get("end")) is None:
        missing.append("end")

    return (not missing), missing


def normalize_payload(payload: dict) -> dict:
    """Return a copy of ``payload`` with ``end`` defaulted when absent.

    Caller must ensure the payload has already passed ``validate_payload``;
    this function trusts that ``start`` parses and that any supplied ``end``
    parses. ``location`` / ``description`` pass through untouched.
    """
    result: dict = {
        "title": payload["title"],
        "start": payload["start"],
    }

    if "end" in payload:
        result["end"] = payload["end"]
    else:
        # _parse_iso is guaranteed to succeed here per the validate gate.
        start_dt = _parse_iso(payload["start"])
        assert start_dt is not None, "validate_payload must precede normalize_payload"
        end_dt = start_dt + DEFAULT_DURATION
        result["end"] = _format_iso(end_dt)

    for field in ("location", "description"):
        if field in payload:
            result[field] = payload[field]

    return result


def build_delegation_payload(normalized: dict, source_inbox_path: str) -> dict:
    """Wrap a normalized ``CalendarPayload`` into the ``create_calendar_event``
    delegation envelope consumed by felix-admin-calendar.

    Deterministic field mapping (kept out of the agent prompt per the two-layer
    doctrine): ``title`` -> ``summary``, ``start`` -> ``start_rfc3339``,
    ``end`` -> ``end_rfc3339``; constant defaults (`action`, `calendar_id`,
    `account`) + ``source_inbox_path`` added; optional ``location`` /
    ``description`` pass through (null when absent); ``start_timezone`` /
    ``rrule`` / ``attendees`` default to null (the inbox path does not extract
    them — the RFC3339 offset in ``start_rfc3339`` carries the zone).
    ``clarification_id`` is null on first dispatch from capture.

    The envelope is forwarded verbatim capture -> main -> felix-admin-calendar;
    no agent reshapes it.
    """
    return {
        "action": DELEGATION_ACTION,
        "calendar_id": DEFAULT_CALENDAR_ID,
        "account": DEFAULT_ACCOUNT,
        "summary": normalized["title"],
        "start_rfc3339": normalized["start"],
        "end_rfc3339": normalized["end"],
        "start_timezone": None,
        "location": normalized.get("location"),
        "description": normalized.get("description"),
        "rrule": None,
        "attendees": None,
        "source_inbox_path": source_inbox_path,
        "clarification_id": None,
    }


# ---------------------------------------------------------------------------
# --create mode (D4, closes #679): validate -> envelope -> helper subprocess
# ---------------------------------------------------------------------------


def _invoke_calendar_helper(
    envelope: dict, source_inbox_path: str, account: str
) -> "subprocess.CompletedProcess[str]":
    """Invoke the WP02 calendar helper as a subprocess and return the result.

    Writes ``envelope`` to a tempfile and runs
    ``python3 -m scripts.google.calendar_helper create --payload-file <tmp>
    --idempotency-key <source_inbox_path> --account <account> --json``. The
    idempotency key is the source inbox path so re-processing the same note
    never double-creates (the helper de-dupes on it). Returns the completed
    process (stdout/stderr/returncode) for the caller to interpret.

    Kept as a small seam so the unit tests can monkeypatch this single call
    site (the real helper needs the google client libraries + a live token,
    which never run under CI).
    """
    fd, tmp_name = tempfile.mkstemp(prefix="calendar-envelope.", suffix=".json")
    try:
        with open(fd, "w", encoding="utf-8") as fh:
            json.dump(envelope, fh)
        return subprocess.run(
            [
                sys.executable,
                "-m",
                CALENDAR_HELPER_MODULE,
                "create",
                "--payload-file",
                tmp_name,
                "--idempotency-key",
                source_inbox_path,
                "--account",
                account,
                "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        try:
            Path(tmp_name).unlink()
        except OSError:  # pragma: no cover - cleanup best-effort
            pass


def _parse_helper_created(stdout: str) -> Optional[dict]:
    """Extract the helper's ``status: created`` JSON line from its stdout.

    The helper emits a JSON object line *before* its final ``SUMMARY:`` line
    (contract: JSON never follows SUMMARY). Scan the lines for the first that
    parses to a dict carrying ``status == "created"``; return it or ``None``.
    """
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and obj.get("status") == "created":
            return obj
    return None


def _run_create(
    payload: dict, source_inbox_path: str, account: str
) -> tuple[dict, int]:
    """Validate + normalize + create via the helper. Returns ``(result, code)``.

    Result shapes (all emitted on stdout as a single JSON object):

    - invalid payload -> ``{"status": "needs_clarification", "missing": [...]}``
      (the helper is NOT called); exit 0 — capture branches on ``status``.
    - helper success -> ``{"status": "created", "event_id": ..., "html_link": ...}``;
      exit 0.
    - helper failure -> ``{"status": "error", "exit_code": <n>, "error": <stderr
      verbatim>}``; exit 0 — surfaced verbatim, NEVER faked (#683).
    """
    is_valid, missing = validate_payload(payload)
    if not is_valid:
        return {"status": "needs_clarification", "missing": missing}, 0

    normalized = normalize_payload(payload)
    envelope = build_delegation_payload(normalized, source_inbox_path)
    # The envelope's account default is DEFAULT_ACCOUNT; the selected account is
    # passed to the helper explicitly so the two stay coherent.
    envelope["account"] = account

    proc = _invoke_calendar_helper(envelope, source_inbox_path, account)
    if proc.returncode == 0:
        created = _parse_helper_created(proc.stdout)
        if created is not None:
            return {
                "status": "created",
                "event_id": created.get("event_id", ""),
                "html_link": created.get("html_link", ""),
            }, 0
        # Exit 0 but no parseable created payload — treat as an error rather
        # than fabricate a success (#683). Surface what the helper printed.
        return {
            "status": "error",
            "exit_code": 0,
            "error": (proc.stdout or proc.stderr).strip(),
        }, 0

    # Non-zero exit (1 operational / 2 usage / 3 auth): surface verbatim.
    return {
        "status": "error",
        "exit_code": proc.returncode,
        "error": (proc.stderr or proc.stdout).strip(),
    }, 0


# ---------------------------------------------------------------------------
# CLI orchestrator
# ---------------------------------------------------------------------------


def _emit_error(kind: str, *, missing: Optional[list[str]] = None, detail: Optional[str] = None) -> None:
    """Write a structured error JSON to stderr."""
    report: dict = {"error": kind}
    if missing is not None:
        report["missing"] = missing
    if detail is not None:
        report["detail"] = detail
    sys.stderr.write(json.dumps(report) + "\n")


def _load_payload(path: Path) -> tuple[Optional[object], Optional[int]]:
    """Read + parse the payload JSON.

    Returns ``(payload, None)`` on success, ``(None, exit_code)`` when the
    file is missing or malformed (the caller propagates the exit code).
    """
    if not path.exists():
        _emit_error("file_not_found", detail=str(path))
        return None, 1
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover — exists() but unreadable is rare
        _emit_error("file_not_found", detail=f"{path}: {exc}")
        return None, 1
    try:
        return json.loads(raw), None
    except json.JSONDecodeError as exc:
        _emit_error("malformed_json", detail=str(exc))
        return None, 1


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="route_calendar_event",
        description=(
            "Validate a CalendarPayload JSON and emit a normalized version "
            "(with default `end = start + 1h` when absent)."
        ),
    )
    parser.add_argument(
        "--payload-file",
        required=True,
        help="Absolute path to a JSON file containing a CalendarPayload.",
    )
    parser.add_argument(
        "--as-delegation-payload",
        action="store_true",
        help=(
            "Emit the `create_calendar_event` delegation envelope "
            "(felix-admin-calendar contract) instead of the bare normalized "
            "payload. Requires --source-path. Default off (backward compatible)."
        ),
    )
    parser.add_argument(
        "--create",
        action="store_true",
        help=(
            "Validate, build the create_calendar_event envelope, and invoke the "
            "calendar helper directly (no agent hop, closes #679). Emits a single "
            "result JSON {status: created|error|needs_clarification, ...} on "
            "stdout. Requires --source-path."
        ),
    )
    parser.add_argument(
        "--account",
        default=DEFAULT_ACCOUNT,
        help=(
            "Credential-set selector passed through to the calendar helper in "
            f"--create mode (default {DEFAULT_ACCOUNT!r})."
        ),
    )
    parser.add_argument(
        "--source-path",
        help=(
            "Absolute inbox path of the source note; required with "
            "--as-delegation-payload or --create (populates source_inbox_path "
            "for audit and is the helper's idempotency key)."
        ),
    )
    args = parser.parse_args(argv)

    if args.as_delegation_payload and args.create:
        _emit_error("mutually_exclusive", detail="--create and --as-delegation-payload are mutually exclusive")
        return 1

    if (args.as_delegation_payload or args.create) and not args.source_path:
        flag = "--create" if args.create else "--as-delegation-payload"
        _emit_error("missing_source_path", detail=f"--source-path is required with {flag}")
        return 1

    payload, err_code = _load_payload(Path(args.payload_file))
    if err_code is not None:
        return err_code

    if args.create:
        # In --create mode an invalid payload is a needs_clarification RESULT
        # (on stdout, exit 0), not a stderr error — capture branches on status.
        if not isinstance(payload, dict):
            result = {"status": "needs_clarification", "missing": ["payload_not_object"]}
        else:
            result, _ = _run_create(payload, args.source_path, args.account)
        sys.stdout.write(json.dumps(result) + "\n")
        return 0

    is_valid, missing = validate_payload(payload)
    if not is_valid:
        _emit_error("invalid_payload", missing=missing)
        return 1

    assert isinstance(payload, dict)  # narrowed by validate_payload
    normalized = normalize_payload(payload)
    result = (
        build_delegation_payload(normalized, args.source_path)
        if args.as_delegation_payload
        else normalized
    )
    sys.stdout.write(json.dumps(result) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
