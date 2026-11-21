#!/usr/bin/env python3
"""Preview a recurrence rule before a task is created — read-only helper.

Mission felix-rrule-adaptation-01M7TKNX (#1111), WP09 (FR-019). The tasker
drafts an RFC 5545 rule from Kent's words, runs this helper, and shows Kent the
next dates **before** ``create_task --rrule`` writes anything. Nothing is
written: the only request is ``POST /api/v2/tasks/occurrences/preview``, which
the server treats as a read (it evaluates an unsaved rule).

Steps:

1. The rule is parsed locally (``vikunja_rule.rrule_text_to_parts``), so a
   malformed rule fails before any HTTP call.
2. ``VikunjaClient.preview_occurrences`` asks the server for the next
   ``--count`` occurrences in ``America/New_York``.
3. The server answers with the **anchor** (``due_date``: the first due date,
   sent or selected from ``--initial-due-time``) and ``occurrences``, the dates
   strictly **after** it (at most ``--count``). The helper prints the anchor
   first, labelled ``first:``, then each later date, labelled ``then:``, all in
   ET with a weekday, e.g. ``Mon 2026-11-23 07:30 ET``. When the series ends
   early (``reason``) that is printed too, counting the anchor: COUNT=1 is
   "series ends after 1 occurrence" (the anchor itself).
4. The answer is validated (field types, timestamps, the zone). A malformed
   answer is an error, never an empty success.

Invocation (on office2, where the Vikunja base URL and token live):

    python3 -m scripts.vikunja.preview_rule --rrule "FREQ=WEEKLY;BYDAY=MO" \\
        --initial-due-time 07:30

    python3 -m scripts.vikunja.preview_rule --rrule "FREQ=DAILY;INTERVAL=10" \\
        --due 2026-11-23T12:30:00Z --from-completion

Output: ``INFO:`` lines for humans, errors on stderr prefixed ``ERROR:``, and
the **last stdout line is a JSON summary**::

    {"ok": true, "rrule": "...", "due_date": "2026-11-23T12:30:00Z",
     "due_date_et": "Mon 2026-11-23 07:30 ET", "due_date_source": "generated",
     "occurrences": [...], "occurrences_et": [...],
     "dates_et": ["Mon 2026-11-23 07:30 ET", ...], "reason": null,
     "reason_text": null, ...}

``dates_et`` is what to show Kent: the anchor, then the later dates.
``create_args`` is what to pass to ``create_task`` once Kent confirms: the rule
and ``--due`` set to the previewed anchor (never ``--initial-due-time``, whose
date the server would pick again from its clock at create time).

On failure the summary has ``"ok": false`` and an ``"error"`` code:
``invalid_input`` (argument or local rule check), ``invalid_rule`` (server
2002), ``invalid_timezone`` (server 2003), ``missing_permission`` (401: the
token lacks ``tasks.occurrences_preview``), ``malformed_response`` (a 200 whose
body does not match the preview contract), or ``vikunja_error``.

Exit codes: 0 ok; 2 bad input or missing permission; 3 a malformed answer or
any other Vikunja or configuration error.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, NoReturn

from scripts.common.et_datetime import parse_vikunja_instant, to_et
from scripts.common.vikunja_rule import rrule_text_to_parts

__all__ = [
    "EXIT_BAD_INPUT",
    "EXIT_OK",
    "EXIT_VIKUNJA",
    "MAX_COUNT",
    "PERMISSION",
    "TIMEZONE",
    "MalformedPreview",
    "Preview",
    "format_et",
    "main",
    "parse_preview",
    "reason_text",
]

EXIT_OK = 0
EXIT_BAD_INPUT = 2
EXIT_VIKUNJA = 3

TIMEZONE = "America/New_York"
PERMISSION = "tasks.occurrences_preview"
#: The server's MaxOccurrencesCount (pkg/models/task_occurrences.go).
MAX_COUNT = 100

_HH_MM = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
_DUE_SOURCES = frozenset({"explicit", "generated"})


class UsageError(Exception):
    """An argument the parser rejected; reported through the exit-2 summary."""


class MalformedPreview(ValueError):
    """A 200 preview answer that does not match the server's response contract."""


@dataclass(frozen=True)
class Preview:
    """A validated preview answer (pkg/routes/api/v2/task_occurrences.go previewAnswer)."""

    due_date: str | None
    due_date_source: str | None
    occurrences: list[str]
    reason: str | None
    timezone: str

    @property
    def dates(self) -> list[str]:
        """The anchor (when present), then the dates after it."""
        return ([self.due_date] if self.due_date else []) + self.occurrences


def _instant(value: object, field: str) -> str:
    if not isinstance(value, str) or parse_vikunja_instant(value) is None:
        raise MalformedPreview(f"{field} is not an aware timestamp: {value!r}")
    return value


def parse_preview(answer: object) -> Preview:
    """Validate a preview answer; raise :class:`MalformedPreview` on any mismatch.

    Server contract (d7e202228): ``occurrences`` (list of timestamps, strictly
    after ``due_date``), ``timezone`` and ``evaluated_at`` are required;
    ``due_date`` comes with ``due_date_source``; without a ``due_date`` there is
    always a ``reason``. Later dates without an anchor, a missing anchor with no
    reason, or a zone other than the one asked for, are malformed.
    """
    if not isinstance(answer, Mapping):
        raise MalformedPreview(f"answer is not an object: {type(answer).__name__}")
    raw = answer.get("occurrences")
    if not isinstance(raw, list):
        raise MalformedPreview(f"occurrences is not a list: {raw!r}")
    occurrences = [_instant(item, "occurrences[]") for item in raw]
    zone = answer.get("timezone")
    if zone != TIMEZONE:
        raise MalformedPreview(f"timezone is {zone!r}, asked for {TIMEZONE!r}")
    _instant(answer.get("evaluated_at"), "evaluated_at")
    due = answer.get("due_date")
    if due is not None:
        _instant(due, "due_date")
    source = answer.get("due_date_source")
    if source is not None and (
        not isinstance(source, str) or due is None or source not in _DUE_SOURCES
    ):
        raise MalformedPreview(f"due_date_source {source!r} does not fit due_date {due!r}")
    if due is not None and source is None:
        raise MalformedPreview("due_date without a due_date_source")
    reason = answer.get("reason")
    if reason is not None and not isinstance(reason, str):
        raise MalformedPreview(f"reason is not a string: {reason!r}")
    if due is None and occurrences:
        raise MalformedPreview("occurrences without a due_date anchor")
    if due is None and not reason:
        # The server omits due_date only when none could be selected, and then
        # always says why (previewAnswer.reason).
        raise MalformedPreview("no due_date and no reason saying why")
    previous = parse_vikunja_instant(due) if due is not None else None
    for item in occurrences:
        instant = parse_vikunja_instant(item)
        if previous is not None and instant is not None and instant <= previous:
            raise MalformedPreview(f"occurrence {item!r} is not after the one before it")
        previous = instant
    return Preview(
        due_date=due,
        due_date_source=source,
        occurrences=occurrences,
        reason=reason or None,
        timezone=zone,
    )


def format_et(value: str) -> str:
    """Render a validated Vikunja instant as ``Mon 2026-11-23 07:30 ET``."""
    instant = parse_vikunja_instant(value)
    if instant is None:  # parse_preview guarantees this cannot happen
        raise MalformedPreview(f"not a timestamp: {value!r}")
    return to_et(instant).strftime("%a %Y-%m-%d %H:%M ET")


def reason_text(reason: str | None, total: int) -> str | None:
    """Human text for ``reason``; *total* counts every date shown, anchor included."""
    if not reason:
        return None
    if total == 0:
        return f"no due date: the rule gives no date (server reason: {reason})"
    plural = "" if total == 1 else "s"
    if reason == "count_exhausted":
        return f"series ends after {total} occurrence{plural} (COUNT)"
    if reason == "until_passed":
        return f"series ends after {total} occurrence{plural} (UNTIL)"
    return f"server reason: {reason}"


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise UsageError(message)


def _build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="scripts.vikunja.preview_rule",
        description="Show the next dates of a recurrence rule (read-only, #1111).",
    )
    parser.add_argument("--rrule", required=True, help="RFC 5545 RRULE text")
    anchor = parser.add_mutually_exclusive_group(required=True)
    anchor.add_argument("--due", default=None, help="first due date, ISO-8601 / RFC3339")
    anchor.add_argument(
        "--initial-due-time",
        default=None,
        metavar="HH:MM",
        help="no due date yet: the server picks the first date at this ET time",
    )
    parser.add_argument(
        "--from-completion",
        action="store_true",
        help="repeat from when the task is completed (repeats_from_current_date)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=3,
        help=f"how many dates to show after the first due date (1-{MAX_COUNT}, default 3)",
    )
    return parser


def _summary(**fields: Any) -> None:
    print(json.dumps(fields, ensure_ascii=False, sort_keys=True))


def _fail(rrule: str | None, error: str, message: str, code: int) -> int:
    print(f"ERROR: {message}", file=sys.stderr)
    _summary(ok=False, rrule=rrule, error=error, message=message)
    return code


def _build_client() -> Any:
    from scripts.common.vikunja_client import VikunjaClient

    return VikunjaClient()


def _validate(args: argparse.Namespace) -> None:
    rrule_text_to_parts(args.rrule)  # ValueError names the offending part
    if not 1 <= args.count <= MAX_COUNT:
        raise ValueError(f"--count must be between 1 and {MAX_COUNT}, got {args.count}")
    if args.initial_due_time is not None and not _HH_MM.match(args.initial_due_time):
        raise ValueError(
            f"--initial-due-time must be HH:MM (24h), got {args.initial_due_time!r}"
        )
    if args.due is not None and parse_vikunja_instant(args.due) is None:
        raise ValueError(f"--due must be an ISO-8601 instant with an offset, got {args.due!r}")


def _create_args(args: argparse.Namespace, preview: Preview) -> list[str] | None:
    """The ``create_task`` arguments that create exactly the previewed series.

    Always ``--due`` with the previewed anchor, never ``--initial-due-time``: the
    server picks a generated anchor from its clock at write time, so a create
    after a delayed confirmation could land on a date Kent never saw.
    ``None`` when there is no anchor (nothing to create).
    """
    if preview.due_date is None:
        return None
    out = ["--rrule", args.rrule, "--due", preview.due_date]
    if args.from_completion:
        out.append("--from-completion")
    return out


def _rrule_from_argv(argv: Sequence[str]) -> str | None:
    items = list(argv)
    for index, item in enumerate(items):
        if item == "--rrule" and index + 1 < len(items):
            return items[index + 1]
        if item.startswith("--rrule="):
            return item.split("=", 1)[1]
    return None


def main(argv: Sequence[str] | None = None, *, client: Any | None = None) -> int:
    """CLI entrypoint; see the module docstring for output and exit codes."""
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    try:
        args = _build_parser().parse_args(raw_argv)
        _validate(args)
    except (UsageError, ValueError) as exc:
        return _fail(_rrule_from_argv(raw_argv), "invalid_input", str(exc), EXIT_BAD_INPUT)

    from scripts.common.vikunja_client import (
        VikunjaAuthError,
        VikunjaBadRequestError,
        VikunjaError,
    )

    try:
        active = client if client is not None else _build_client()
        answer = active.preview_occurrences(
            rrule=args.rrule,
            due_date=args.due,
            initial_due_time=args.initial_due_time,
            timezone=TIMEZONE,
            repeats_from_current_date=args.from_completion,
            count=args.count,
        )
    except VikunjaAuthError:
        return _fail(
            args.rrule,
            "missing_permission",
            f"Vikunja refused the preview (401): the token lacks the {PERMISSION} "
            "permission. Kent must re-issue the token with it; no dates can be shown.",
            EXIT_BAD_INPUT,
        )
    except VikunjaBadRequestError as exc:
        if exc.code == 2002:
            return _fail(
                args.rrule, "invalid_rule", "Vikunja rejected the rule (2002).", EXIT_BAD_INPUT
            )
        if exc.code == 2003:
            return _fail(
                args.rrule,
                "invalid_timezone",
                f"Vikunja rejected the time zone {TIMEZONE!r} (2003).",
                EXIT_BAD_INPUT,
            )
        return _fail(args.rrule, "vikunja_error", str(exc), EXIT_VIKUNJA)
    except (VikunjaError, OSError, RuntimeError) as exc:
        return _fail(args.rrule, "vikunja_error", str(exc), EXIT_VIKUNJA)

    try:
        preview = parse_preview(answer)
    except MalformedPreview as exc:
        return _fail(
            args.rrule, "malformed_response", f"unexpected preview answer: {exc}", EXIT_VIKUNJA
        )

    due_et = format_et(preview.due_date) if preview.due_date else None
    later_et = [format_et(item) for item in preview.occurrences]
    dates_et = ([due_et] if due_et else []) + later_et
    ends = reason_text(preview.reason, len(dates_et))
    create_args = _create_args(args, preview)

    print(f"INFO: rule {args.rrule}" + (" (from completion)" if args.from_completion else ""))
    if due_et:
        print(f"INFO: first: {due_et}")
    for line in later_et:
        print(f"INFO: then: {line}")
    if not dates_et:
        print("INFO: no due date")
    if ends:
        print(f"INFO: {ends}")
    if create_args:
        print("INFO: create with: " + " ".join(create_args))
    _summary(
        ok=True,
        rrule=args.rrule,
        from_completion=args.from_completion,
        due_date=preview.due_date,
        due_date_et=due_et,
        due_date_source=preview.due_date_source,
        occurrences=preview.occurrences,
        occurrences_et=later_et,
        dates_et=dates_et,
        reason=preview.reason,
        reason_text=ends,
        create_args=create_args,
    )
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())
