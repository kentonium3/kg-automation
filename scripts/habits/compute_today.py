#!/usr/bin/env python3
"""Compute today's TZ-aware day, date, ET offset, and end-of-day-ET ISO timestamp.

Mission #282 / FR-001. Part of the felix-admin-habits Steps 1-4 refactor
(per Constitution Directive 6 and `docs/design/helper-script-conventions.md`).

This helper exists because the agent's prompt previously encoded the rule
"use TZ=America/New_York, never UTC; recognize that 8 PM ET has already
rolled over in UTC" — a high-criticality block (wrong day → wrong habits
in Kent's WhatsApp) that's hallucination-prone in-prompt.

CRITICAL #112 regression-prevention:
  The `iso_eod_et` output field MUST NOT end with `Z` (UTC). Vikunja
  due_date values written with UTC midnight cause habits to appear overdue
  the moment the morning cron fires at 7:05 AM ET. The end-of-day-ET
  anchor (`23:59:59` with explicit ET offset) preserves the bug fix from
  issue #112.

Invocation:

    python3 scripts/habits/compute_today.py [--now-utc <ISO-8601>]

Output (stdout):

    {"day": "Wed", "date": "2026-05-15", "et_offset": "-04:00", "iso_eod_et": "2026-05-15T23:59:59-04:00"}
    SUMMARY: day=Wed date=2026-05-15 et_offset=-04:00

Exit codes:
    0 — success
    1 — operational error (zoneinfo unavailable, etc.)
    2 — usage error (malformed --now-utc value)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


ET_ZONE = "America/New_York"


def _format_offset(offset_str: str) -> str:
    """Convert `%z` output (`-0400`) to `-04:00` per ISO-8601 conventions."""
    if len(offset_str) == 5 and offset_str[0] in ("+", "-"):
        return f"{offset_str[:3]}:{offset_str[3:]}"
    return offset_str


def compute_today(now_utc: datetime) -> dict[str, str]:
    """Compute the four output fields from a UTC `datetime`.

    Returns a dict with keys: day, date, et_offset, iso_eod_et.
    Guarantees: `iso_eod_et` NEVER ends with `Z` (the #112 regression-prevention).
    """
    try:
        et_now = now_utc.astimezone(ZoneInfo(ET_ZONE))
    except ZoneInfoNotFoundError as exc:
        raise RuntimeError(
            f"TZ data for {ET_ZONE} not available on this host: {exc}"
        ) from exc

    day = et_now.strftime("%a")
    date = et_now.strftime("%Y-%m-%d")
    et_offset = _format_offset(et_now.strftime("%z"))
    iso_eod_et = f"{date}T23:59:59{et_offset}"

    return {
        "day": day,
        "date": date,
        "et_offset": et_offset,
        "iso_eod_et": iso_eod_et,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n\n", maxsplit=1)[0],
    )
    parser.add_argument(
        "--now-utc",
        type=str,
        default=None,
        help=(
            "ISO-8601 timestamp to override 'now' (for tests). "
            "Defaults to current UTC time. Example: 2026-05-15T11:00:00Z"
        ),
    )
    args = parser.parse_args(argv)

    if args.now_utc is None:
        now_utc = datetime.now(timezone.utc)
    else:
        try:
            # Accept the trailing Z that Python parses via fromisoformat in 3.11+
            now_utc = datetime.fromisoformat(args.now_utc.replace("Z", "+00:00"))
        except ValueError as exc:
            print(
                f"ERROR: --now-utc value is not a valid ISO-8601 timestamp: "
                f"{args.now_utc!r} ({exc})",
                file=sys.stderr,
            )
            return 2
        if now_utc.tzinfo is None:
            now_utc = now_utc.replace(tzinfo=timezone.utc)

    try:
        result = compute_today(now_utc)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result))
    print(
        f"SUMMARY: day={result['day']} date={result['date']} "
        f"et_offset={result['et_offset']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
