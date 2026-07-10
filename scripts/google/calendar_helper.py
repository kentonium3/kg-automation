"""Deterministic Google Calendar CLI for the Felix calendar helper (WP02).

This helper authenticates per-account (via WP01's
:mod:`scripts.google.calendar_auth`) and performs event
``create`` / ``list`` / ``update`` / ``delete`` plus a deploy ``--self-check``,
exactly per ``kitty-specs/felix-calendar-helper-*/contracts/calendar-helper-cli.md``
(authoritative for flags, exit codes, SUMMARY/JSON ordering) and
``data-model.md`` (event body mapping, idempotency key, attendee policy).

Conforms to ``docs/design/helper-script-conventions.md``: argparse subcommands,
long-form flags, meaningful exit codes, a final ``SUMMARY:`` line on stdout,
``INFO:``/``WARN:`` operational lines, ``ERROR:`` to stderr.

Exit-code contract (authoritative):

- ``0`` — success (mutation, if any, completed).
- ``1`` — operational / API error (4xx/5xx, timeout, ``not_found``).
- ``2`` — usage error (bad/missing args, invalid ``--account`` name,
  both/neither create input modes, ``recurrence_scope_unsupported``).
- ``3`` — **auth failure** (missing/invalid token, ``invalid_grant``, refresh
  failure). ``ERROR: auth_failed …`` on stderr, ``SUMMARY: … status=auth_failed``,
  and **never** a mutation.

CI-safe imports: ``google-api-python-client`` / ``google-auth`` are NOT in
``requirements.txt`` (they live only in a dedicated office2 venv). All google
imports are done **lazily inside functions**, so importing this module never
requires the google packages; the unit tests inject fakes via ``sys.modules``.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import TYPE_CHECKING, Any

from scripts.google.calendar_auth import (
    DEFAULT_ACCOUNT,
    SCOPES_DEFAULT,
    CalendarAuthError,
    load_credentials,
)

if TYPE_CHECKING:  # pragma: no cover - typing only, no runtime import
    from collections.abc import Sequence

__all__ = ["main"]

# Exit codes (contract).
EXIT_OK = 0
EXIT_OPERATIONAL = 1
EXIT_USAGE = 2
EXIT_AUTH = 3

# Default operating zone when a caller omits both an offset-bearing timezone and
# an explicit --start-timezone (contract "Timezone" invariant).
DEFAULT_TIMEZONE = "America/New_York"

# Private extended-property key that carries the idempotency token.
FELIX_SOURCE_KEY = "felix_source_key"

# Bounded lookback (number of events scanned) when de-duping a keyed create.
IDEMPOTENCY_LOOKBACK = 250


class HelperError(Exception):
    """Operational/usage error carrying the exit code the CLI should return.

    ``exit_code`` is ``1`` (operational) or ``2`` (usage). Auth failures are
    represented by :class:`CalendarAuthError` (exit ``3``) and handled
    separately so a bad-credentials path can never be reported as a completed
    action.
    """

    def __init__(self, message: str, exit_code: int) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def _usage_error(message: str) -> HelperError:
    return HelperError(message, EXIT_USAGE)


def _operational_error(message: str) -> HelperError:
    return HelperError(message, EXIT_OPERATIONAL)


# --------------------------------------------------------------------------- #
# stdout / stderr discipline
# --------------------------------------------------------------------------- #


def _emit_json(obj: dict[str, Any]) -> None:
    """Print a JSON result object on a stdout line *preceding* the SUMMARY.

    JSON never comes after SUMMARY (agent parse anchor).
    """
    print(json.dumps(obj, sort_keys=True))


def _emit_summary(fields: dict[str, Any]) -> None:
    """Print the final ``SUMMARY:`` stdout line (always last).

    Fields are emitted in insertion order as ``key=value`` pairs.
    """
    parts = " ".join(f"{k}={v}" for k, v in fields.items())
    print(f"SUMMARY: {parts}")


def _emit_error(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)


# --------------------------------------------------------------------------- #
# Google service construction (lazy import)
# --------------------------------------------------------------------------- #


def _build_service(account: str, dry_run: bool = False) -> Any:
    """Load credentials and build the Calendar v3 service.

    Auth is resolved here, before any mutation, so an auth failure
    short-circuits to exit ``3`` and never touches an ``insert/update/delete``.

    :raises CalendarAuthError: on any auth failure (exit 3).
    :raises HelperError: if the google client library is unavailable (exit 1).
    """
    creds = load_credentials(account, SCOPES_DEFAULT)
    try:
        from googleapiclient.discovery import build
    except ImportError as exc:  # pragma: no cover - env-specific import guard
        raise _operational_error(
            "googleapiclient is not installed in this interpreter; run the "
            "calendar helper under its dedicated venv"
        ) from exc
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def _http_status(exc: Exception) -> int | None:
    """Best-effort extraction of an HTTP status from a googleapiclient error."""
    resp = getattr(exc, "resp", None)
    status = getattr(resp, "status", None)
    if status is None:
        return None
    try:
        return int(status)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return None


def _run_execute(request: Any) -> Any:
    """Execute a googleapiclient request, mapping API errors to HelperError.

    A ``404`` maps to a ``not_found`` operational error (exit 1); all other API
    errors are operational (exit 1) as well. The message never leaks secrets.
    """
    try:
        return request.execute()
    except HelperError:  # pragma: no cover - defensive: never raised by .execute()
        raise
    except Exception as exc:  # noqa: BLE001 - map any API/transport error to exit 1
        status = _http_status(exc)
        if status == 404:
            raise _operational_error("not_found") from exc
        raise _operational_error(
            f"calendar API error ({type(exc).__name__}: {exc})"
        ) from exc


# --------------------------------------------------------------------------- #
# Event body mapping
# --------------------------------------------------------------------------- #


def _time_field(value: str, timezone: str | None) -> dict[str, str]:
    """Build a Google ``{dateTime, timeZone}`` object from an RFC3339 string."""
    field = {"dateTime": value}
    if timezone:
        field["timeZone"] = timezone
    return field


def _parse_attendees(raw: str | list[str] | None) -> list[dict[str, str]]:
    """Normalize a comma list or list of emails to ``[{"email": …}]``."""
    if not raw:
        return []
    if isinstance(raw, str):
        emails = [e.strip() for e in raw.split(",") if e.strip()]
    else:
        emails = [str(e).strip() for e in raw if str(e).strip()]
    return [{"email": e} for e in emails]


def _build_event_body(
    *,
    summary: str | None,
    start: str | None,
    end: str | None,
    start_timezone: str | None,
    location: str | None,
    description: str | None,
    rrule: str | None,
    attendees: list[dict[str, str]] | None,
    idempotency_key: str | None,
) -> dict[str, Any]:
    """Map explicit/envelope fields to a Google Calendar event request body.

    Only provided fields are included, so this is reusable for both ``create``
    (full body) and ``update`` (patch — the caller supplies only changed fields).
    """
    body: dict[str, Any] = {}
    if summary is not None:
        body["summary"] = summary
    if start is not None:
        body["start"] = _time_field(start, start_timezone)
    if end is not None:
        body["end"] = _time_field(end, start_timezone)
    if location is not None:
        body["location"] = location
    if description is not None:
        body["description"] = description
    if rrule is not None:
        body["recurrence"] = [rrule]
    if attendees:
        body["attendees"] = attendees
    if idempotency_key is not None:
        body["extendedProperties"] = {
            "private": {FELIX_SOURCE_KEY: idempotency_key}
        }
    return body


# --------------------------------------------------------------------------- #
# create
# --------------------------------------------------------------------------- #


def _load_payload_file(path: str) -> dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except OSError as exc:
        raise _usage_error(f"cannot read payload file {path!r}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise _usage_error(f"payload file {path!r} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise _usage_error(f"payload file {path!r} must contain a JSON object")
    return data


def _create_fields_from_payload(
    payload: dict[str, Any], allow_attendees: bool
) -> dict[str, Any]:
    """Extract create fields from a ``create_calendar_event`` envelope.

    Rejects attendees on this inbox path unless ``--allow-attendees`` is set —
    a note should not silently email people from Kent's personal calendar.
    """
    attendees_raw = payload.get("attendees")
    if attendees_raw and not allow_attendees:
        raise _usage_error(
            "payload declares attendees; refusing to send invitations from the "
            "inbox path without --allow-attendees"
        )
    return {
        "summary": payload.get("summary"),
        "start": payload.get("start_rfc3339"),
        "end": payload.get("end_rfc3339"),
        "start_timezone": payload.get("start_timezone"),
        "location": payload.get("location"),
        "description": payload.get("description"),
        "rrule": payload.get("rrule"),
        "attendees": _parse_attendees(attendees_raw) if allow_attendees else [],
    }


def _resolve_create_fields(args: argparse.Namespace) -> dict[str, Any]:
    """Resolve the two mutually-exclusive create input modes to a field dict."""
    payload_mode = args.payload_file is not None
    explicit_mode = any(
        v is not None
        for v in (
            args.summary,
            args.start,
            args.end,
            args.location,
            args.description,
            args.rrule,
            args.attendees,
        )
    )
    if payload_mode and explicit_mode:
        raise _usage_error(
            "create takes either --payload-file or explicit flags, not both"
        )
    if not payload_mode and not explicit_mode:
        raise _usage_error(
            "create needs either --payload-file or explicit event flags "
            "(--summary/--start/--end/…)"
        )

    if payload_mode:
        payload = _load_payload_file(args.payload_file)
        return _create_fields_from_payload(payload, args.allow_attendees)

    return {
        "summary": args.summary,
        "start": args.start,
        "end": args.end,
        "start_timezone": args.start_timezone,
        "location": args.location,
        "description": args.description,
        "rrule": args.rrule,
        "attendees": _parse_attendees(args.attendees),
    }


def _find_by_idempotency_key(
    service: Any, calendar_id: str, key: str
) -> dict[str, Any] | None:
    """Return an existing event stamped with ``key`` in a bounded lookback."""
    result = _run_execute(
        service.events().list(
            calendarId=calendar_id,
            privateExtendedProperty=f"{FELIX_SOURCE_KEY}={key}",
            maxResults=IDEMPOTENCY_LOOKBACK,
            singleEvents=False,
        )
    )
    items = result.get("items", []) if isinstance(result, dict) else []
    return items[0] if items else None


def _cmd_create(service: Any, args: argparse.Namespace) -> int:
    fields = _resolve_create_fields(args)
    if not fields.get("summary"):
        raise _usage_error("create requires a summary")
    if not fields.get("start") or not fields.get("end"):
        raise _usage_error("create requires both --start and --end (RFC3339)")

    timezone = fields.get("start_timezone") or DEFAULT_TIMEZONE
    key = args.idempotency_key

    if key and not args.dry_run:
        existing = _find_by_idempotency_key(service, args.calendar_id, key)
        if existing is not None:
            _emit_success_create(existing, args, idempotent=True)
            return EXIT_OK

    body = _build_event_body(
        summary=fields["summary"],
        start=fields["start"],
        end=fields["end"],
        start_timezone=timezone,
        location=fields.get("location"),
        description=fields.get("description"),
        rrule=fields.get("rrule"),
        attendees=fields.get("attendees"),
        idempotency_key=key,
    )

    if args.dry_run:
        print("INFO: dry-run — validated create body, no mutation performed")
        _emit_dry_run_summary("create", args)
        return EXIT_OK

    created = _run_execute(
        service.events().insert(
            calendarId=args.calendar_id,
            body=body,
            sendUpdates=args.send_updates,
        )
    )
    _emit_success_create(created, args, idempotent=False)
    return EXIT_OK


def _emit_success_create(
    event: dict[str, Any], args: argparse.Namespace, idempotent: bool
) -> None:
    event_id = event.get("id", "")
    html_link = event.get("htmlLink", "")
    if args.json:
        _emit_json(
            {
                "status": "created",
                "idempotent": idempotent,
                "event_id": event_id,
                "html_link": html_link,
            }
        )
    _emit_summary(
        {
            "op": "create",
            "status": "created",
            "idempotent": str(idempotent).lower(),
            "event_id": event_id,
            "account": args.account,
            "calendar": args.calendar_id,
        }
    )


# --------------------------------------------------------------------------- #
# list
# --------------------------------------------------------------------------- #


def _cmd_list(service: Any, args: argparse.Namespace) -> int:
    result = _run_execute(
        service.events().list(
            calendarId=args.calendar_id,
            timeMin=args.from_time,
            timeMax=args.to_time,
            maxResults=args.max,
            singleEvents=True,
            orderBy="startTime",
        )
    )
    items = result.get("items", []) if isinstance(result, dict) else []
    events = [_summarize_event(item) for item in items]
    if args.json:
        _emit_json({"status": "ok", "count": len(events), "events": events})
    _emit_summary(
        {
            "op": "list",
            "status": "ok",
            "count": len(events),
            "account": args.account,
            "calendar": args.calendar_id,
        }
    )
    return EXIT_OK


def _summarize_event(item: dict[str, Any]) -> dict[str, Any]:
    start = item.get("start", {})
    end = item.get("end", {})
    return {
        "event_id": item.get("id", ""),
        "summary": item.get("summary", ""),
        "start": start.get("dateTime") or start.get("date", ""),
        "end": end.get("dateTime") or end.get("date", ""),
        "recurring": bool(item.get("recurrence")) or "recurringEventId" in item,
    }


# --------------------------------------------------------------------------- #
# update
# --------------------------------------------------------------------------- #


def _guard_recurrence_scope(args: argparse.Namespace) -> None:
    """Reject single-occurrence edits of a recurring series (out of scope v1)."""
    if getattr(args, "recurrence_scope", None) == "single":
        raise _usage_error(
            "recurrence_scope_unsupported: single-occurrence edits of a "
            "recurring series are out of scope in v1 (operates on the series id)"
        )


def _cmd_update(service: Any, args: argparse.Namespace) -> int:
    _guard_recurrence_scope(args)

    # get-then-patch: confirm the event exists (→ not_found/exit 1 otherwise),
    # then patch only the provided fields.
    _run_execute(
        service.events().get(calendarId=args.calendar_id, eventId=args.event_id)
    )

    patch = _build_event_body(
        summary=args.summary,
        start=args.start,
        end=args.end,
        start_timezone=(args.start_timezone or DEFAULT_TIMEZONE)
        if args.start is not None or args.end is not None
        else None,
        location=args.location,
        description=args.description,
        rrule=args.rrule,
        attendees=_parse_attendees(args.attendees) if args.attendees else None,
        idempotency_key=None,
    )

    for field in _clear_fields(args.clear):
        patch[field] = None

    if not patch:
        raise _usage_error("update needs at least one field to change or --clear")

    if args.dry_run:
        print("INFO: dry-run — validated update patch, no mutation performed")
        _emit_dry_run_summary("update", args, event_id=args.event_id)
        return EXIT_OK

    updated = _run_execute(
        service.events().patch(
            calendarId=args.calendar_id,
            eventId=args.event_id,
            body=patch,
            sendUpdates=args.send_updates,
        )
    )
    event_id = updated.get("id", args.event_id) if isinstance(updated, dict) else args.event_id
    if args.json:
        _emit_json({"status": "updated", "event_id": event_id})
    _emit_summary(
        {
            "op": "update",
            "status": "updated",
            "event_id": event_id,
            "account": args.account,
            "calendar": args.calendar_id,
        }
    )
    return EXIT_OK


# Google event fields that ``--clear`` may remove (mapped from user-facing names).
_CLEARABLE = {
    "location": "location",
    "description": "description",
    "attendees": "attendees",
    "recurrence": "recurrence",
    "rrule": "recurrence",
}


def _clear_fields(raw: str | None) -> list[str]:
    """Resolve a ``--clear`` comma list to Google event field names."""
    if not raw:
        return []
    fields: list[str] = []
    for name in (n.strip() for n in raw.split(",")):
        if not name:
            continue
        if name not in _CLEARABLE:
            raise _usage_error(
                f"--clear: unknown field {name!r} "
                f"(allowed: {', '.join(sorted(set(_CLEARABLE)))})"
            )
        mapped = _CLEARABLE[name]
        if mapped not in fields:
            fields.append(mapped)
    return fields


# --------------------------------------------------------------------------- #
# delete
# --------------------------------------------------------------------------- #


def _cmd_delete(service: Any, args: argparse.Namespace) -> int:
    _guard_recurrence_scope(args)

    if args.dry_run:
        # Confirm existence without mutating.
        _run_execute(
            service.events().get(calendarId=args.calendar_id, eventId=args.event_id)
        )
        print("INFO: dry-run — event exists, no deletion performed")
        _emit_dry_run_summary("delete", args, event_id=args.event_id)
        return EXIT_OK

    _run_execute(
        service.events().delete(
            calendarId=args.calendar_id,
            eventId=args.event_id,
            sendUpdates=args.send_updates,
        )
    )
    if args.json:
        _emit_json({"status": "deleted", "event_id": args.event_id})
    _emit_summary(
        {
            "op": "delete",
            "status": "deleted",
            "event_id": args.event_id,
            "account": args.account,
            "calendar": args.calendar_id,
        }
    )
    return EXIT_OK


# --------------------------------------------------------------------------- #
# --self-check
# --------------------------------------------------------------------------- #


def _cmd_self_check(args: argparse.Namespace) -> int:
    """Deploy/preflight: refresh creds + a bounded events.list(primary, max=1).

    Any auth/scope/refresh failure raises :class:`CalendarAuthError`, which the
    caller maps to exit 3. Never interactive.
    """
    service = _build_service(args.account)
    _run_execute(
        service.events().list(calendarId="primary", maxResults=1)
    )
    _emit_summary({"op": "self-check", "status": "ok", "account": args.account})
    return EXIT_OK


# --------------------------------------------------------------------------- #
# dry-run summary helper
# --------------------------------------------------------------------------- #


def _emit_dry_run_summary(
    op: str, args: argparse.Namespace, event_id: str | None = None
) -> None:
    fields: dict[str, Any] = {"op": op, "status": "dry_run"}
    if event_id is not None:
        fields["event_id"] = event_id
    fields["account"] = args.account
    fields["calendar"] = args.calendar_id
    _emit_summary(fields)


# --------------------------------------------------------------------------- #
# argument parsing
# --------------------------------------------------------------------------- #


def _add_common_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--account", default=DEFAULT_ACCOUNT)
    parser.add_argument("--calendar-id", dest="calendar_id", default="primary")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--dry-run", dest="dry_run", action="store_true")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="calendar_helper",
        description="Deterministic Google Calendar CLI (Felix calendar helper).",
    )
    # Top-level --self-check (no subcommand). Common flags also live at the top
    # level so `--self-check --account X` parses without a subcommand.
    parser.add_argument("--self-check", dest="self_check", action="store_true")
    _add_common_flags(parser)

    sub = parser.add_subparsers(dest="command")

    p_create = sub.add_parser("create", help="Create an event")
    _add_common_flags(p_create)
    p_create.add_argument("--payload-file", dest="payload_file")
    p_create.add_argument("--summary")
    p_create.add_argument("--start")
    p_create.add_argument("--end")
    p_create.add_argument("--start-timezone", dest="start_timezone")
    p_create.add_argument("--location")
    p_create.add_argument("--description")
    p_create.add_argument("--rrule")
    p_create.add_argument("--attendees")
    p_create.add_argument(
        "--send-updates",
        dest="send_updates",
        choices=["none", "externalOnly", "all"],
        default="none",
    )
    p_create.add_argument(
        "--allow-attendees", dest="allow_attendees", action="store_true"
    )
    p_create.add_argument("--idempotency-key", dest="idempotency_key")

    p_list = sub.add_parser("list", help="List events in a window")
    _add_common_flags(p_list)
    p_list.add_argument("--from", dest="from_time", required=True)
    p_list.add_argument("--to", dest="to_time", required=True)
    p_list.add_argument("--max", type=int, default=50)

    p_update = sub.add_parser("update", help="Patch an existing event")
    _add_common_flags(p_update)
    p_update.add_argument("--event-id", dest="event_id", required=True)
    p_update.add_argument("--summary")
    p_update.add_argument("--start")
    p_update.add_argument("--end")
    p_update.add_argument("--start-timezone", dest="start_timezone")
    p_update.add_argument("--location")
    p_update.add_argument("--description")
    p_update.add_argument("--rrule")
    p_update.add_argument("--attendees")
    p_update.add_argument("--clear")
    p_update.add_argument(
        "--send-updates",
        dest="send_updates",
        choices=["none", "externalOnly", "all"],
        default="none",
    )
    p_update.add_argument(
        "--recurrence-scope", dest="recurrence_scope", choices=["single", "series"]
    )

    p_delete = sub.add_parser("delete", help="Delete/cancel an event")
    _add_common_flags(p_delete)
    p_delete.add_argument("--event-id", dest="event_id", required=True)
    p_delete.add_argument(
        "--send-updates",
        dest="send_updates",
        choices=["none", "all"],
        default="none",
    )
    p_delete.add_argument(
        "--recurrence-scope", dest="recurrence_scope", choices=["single", "series"]
    )

    return parser


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #


def _dispatch(args: argparse.Namespace) -> int:
    """Run the resolved command. Auth is built lazily inside each mutating path."""
    if args.self_check:
        return _cmd_self_check(args)

    if args.command == "create":
        service = _build_service(args.account, dry_run=args.dry_run)
        return _cmd_create(service, args)
    if args.command == "list":
        service = _build_service(args.account)
        return _cmd_list(service, args)
    if args.command == "update":
        # Guard usage errors (recurrence scope) before touching auth.
        _guard_recurrence_scope(args)
        service = _build_service(args.account, dry_run=args.dry_run)
        return _cmd_update(service, args)
    if args.command == "delete":
        _guard_recurrence_scope(args)
        service = _build_service(args.account, dry_run=args.dry_run)
        return _cmd_delete(service, args)

    # No subcommand and no --self-check → usage error.
    raise _usage_error("no subcommand given (expected create/list/update/delete or --self-check)")


def main(argv: "Sequence[str] | None" = None) -> int:
    """CLI entry point. Returns the process exit code (contract 0/1/2/3)."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        return _dispatch(args)
    except CalendarAuthError as exc:
        # Auth failure: never mutated (auth resolved before any insert/patch/
        # delete). Distinct exit 3 so callers can tell "re-stage credentials"
        # apart from a transient API error.
        _emit_error(f"auth_failed {exc}")
        account = getattr(args, "account", DEFAULT_ACCOUNT)
        op = "self-check" if getattr(args, "self_check", False) else (args.command or "unknown")
        _emit_summary({"op": op, "status": "auth_failed", "account": account})
        return EXIT_AUTH
    except ValueError as exc:
        # Raised by calendar_auth for an invalid --account name (usage → exit 2).
        _emit_error(str(exc))
        return EXIT_USAGE
    except HelperError as exc:
        _emit_error(str(exc))
        account = getattr(args, "account", DEFAULT_ACCOUNT)
        op = "self-check" if getattr(args, "self_check", False) else (args.command or "unknown")
        _emit_summary({"op": op, "status": "error", "account": account})
        return exc.exit_code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
