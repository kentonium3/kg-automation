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
    filled in (start + 1 hour) when absent so downstream consumers (gog
    calendar create via Felix main) always have an explicit interval.
    Optional fields (``location``, ``description``) pass through verbatim.
  * On invalid: write ``{"error": "invalid_payload", "missing": [...]}``
    to stderr; exit 1.
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
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

REQUIRED_FIELDS = ("title", "start")
OPTIONAL_FIELDS = ("end", "location", "description")
DEFAULT_DURATION = timedelta(hours=1)


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
    args = parser.parse_args(argv)

    payload, err_code = _load_payload(Path(args.payload_file))
    if err_code is not None:
        return err_code

    is_valid, missing = validate_payload(payload)
    if not is_valid:
        _emit_error("invalid_payload", missing=missing)
        return 1

    assert isinstance(payload, dict)  # narrowed by validate_payload
    normalized = normalize_payload(payload)
    sys.stdout.write(json.dumps(normalized) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
