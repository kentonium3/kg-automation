#!/usr/bin/env python3
"""Morning check-in list emitter (mission #371 / WP01).

Produces today's ordered habit list as both:

  (a) a persisted JSON artifact at
      ``/data/services/openclaw/state/habits/morning-checkin-<YYYY-MM-DD>.json``
      (single source of truth for the morning send + reply parse paths), and

  (b) the formatted WhatsApp check-in message text on stdout.

This module is the root-cause fix for issue #371: the morning send and reply
parse used to be two independent OpenClaw sessions, each regenerating the
habit list from live Vikunja state. Async state changes (and unstable
ordering) caused the orderings to diverge -- Kent's "skipped 3" got applied
to the wrong habit. The persisted artifact, ordered by the immutable
``vikunja_task_id`` ASC, removes both failure modes.

The helper composes two existing Phase 5 helpers without modifying them
(C-001):

  * ``scripts.habits.query_active_habits_v2.query_active_today`` -- fetch
    the project-scoped active habit task set.
  * ``scripts.habits.exclude_completed_v2.exclude_completed_for_today`` --
    filter out habits already addressed today via the JSONL state log.

The atomic-write pattern (tmp + fsync + rename per research D2) prevents a
mid-write crash from leaving a corrupt artifact the next morning. Dates are
in America/New_York throughout per research D1 ("today" means Kent's day,
not UTC's).

See the spec / plan / data-model / contracts under
``kitty-specs/habits-checkin-reply-scripts-first-01KS86ZQ/`` for the full
contract. Public API surface per ``contracts/api.md``; CLI surface per
``contracts/cli.md``.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import sys
import urllib.error
import zoneinfo
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.habits.exclude_completed_v2 import exclude_completed_for_today
from scripts.habits.query_active_habits_v2 import query_active_today


# ---------------------------------------------------------------------------
# Module constants (per contracts/api.md)
# ---------------------------------------------------------------------------

#: Default Vikunja API base. Tailscale IP keeps the helper functional
#: without DNS resolution of the public hostname.
DEFAULT_BASE_URL = "http://100.92.197.90:3456/api/v1/"

#: Default location of the felix-bot Vikunja API token on office2 (mode 0600).
DEFAULT_TOKEN_PATH = Path("/data/services/openclaw/secrets/vikunja-api")

#: Default per-date morning-list artifact directory on office2.
DEFAULT_STATE_DIR = Path("/data/services/openclaw/state/habits")

#: HTTP socket timeout for any direct Vikunja calls (the downstream helpers
#: use their own constants; this is kept for symmetry with the contract).
HTTP_TIMEOUT_SECONDS = 30

#: Kent's local timezone. "Today" in this module is Kent's local day, not UTC.
LOCAL_TZ = zoneinfo.ZoneInfo("America/New_York")

#: Schema version embedded in every persisted artifact.
SCHEMA_VERSION = 1

#: Regex for the --date flag (ISO-8601 date).
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ---------------------------------------------------------------------------
# Dataclasses (per contracts/api.md Entity 1)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MorningListHabit:
    """A single habit row in the morning list. Position is 1-indexed."""

    position: int
    vikunja_task_id: int
    title: str


@dataclass(frozen=True, slots=True)
class MorningList:
    """The persisted artifact: ordered list of habits Kent should address today."""

    schema_version: int
    date: str  # YYYY-MM-DD, America/New_York
    generated_at: str  # ISO-8601 UTC
    habits: list[MorningListHabit]


# ---------------------------------------------------------------------------
# Internal helpers (clock + I/O wrappers; small, monkeypatch-friendly)
# ---------------------------------------------------------------------------


def _today_local() -> str:
    """Return today's date in America/New_York as ``YYYY-MM-DD``.

    Wrapped so tests can monkeypatch the clock without patching ``datetime``
    globally. Kent's local TZ matches his lived experience of "today's
    check-in" -- UTC midnight is not a meaningful day boundary for him.
    """
    return datetime.now(LOCAL_TZ).date().isoformat()


def _now_utc_iso() -> str:
    """Return current UTC instant as ISO-8601 with explicit ``Z`` suffix.

    The ``Z`` form is chosen over ``+00:00`` for compactness in the
    persisted JSON (NFR-005 keeps files ~1KB).
    """
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    )


def _read_token(token_path: Path) -> str:
    """Read a Vikunja API token from a mode-0600 file.

    Raises:
        FileNotFoundError: token file missing.
        OSError: token file unreadable or empty.
    """
    try:
        content = Path(token_path).read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        raise
    except PermissionError as exc:
        raise OSError(
            f"Token file not readable (permission denied): {token_path}"
        ) from exc
    except OSError as exc:
        raise OSError(
            f"Could not read token file {token_path}: {exc}"
        ) from exc
    if not content:
        raise OSError(f"Token file is empty: {token_path}")
    return content


def _query_habits(base_url: str, token: str, date: str) -> list[dict]:
    """Fetch active habits for the given date via the Phase 5 helper.

    Thin wrapper -- exists so tests can monkeypatch this single name to
    bypass the live HTTP path without re-wiring ``urllib.request.urlopen``
    (though that path is also exercised in the integration-style cases).
    """
    return query_active_today(api_base_url=base_url, token=token, today=date)


def _exclude_already_addressed(
    habits: list[dict],
    date: str,
) -> list[dict]:
    """Filter out habits with a ``state=complete`` JSONL record for ``date``.

    Thin wrapper around ``exclude_completed_for_today`` so callers (and
    tests) can intercept the dependency at this seam without monkeypatching
    a module name with a hyphen-free dotted path.
    """
    return exclude_completed_for_today(habits, today=date)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_morning_list(
    *,
    date: str | None = None,
    base_url: str = DEFAULT_BASE_URL,
    token_path: Path = DEFAULT_TOKEN_PATH,
) -> MorningList:
    """Build the ordered ``MorningList`` for a Kent-day.

    Behavior:
      1. Resolve ``date`` (default: today in America/New_York).
      2. Read the Vikunja API token from ``token_path``.
      3. Query active habits for ``date`` via the Phase 5 helper.
      4. Exclude habits already addressed today via the JSONL state log.
      5. Sort surviving habits by ``vikunja_task_id`` ASC (immutable
         per ``reference_vikunja_id_vs_identifier.md`` -- the only sort key
         that does not reintroduce the #371 instability).
      6. Assign 1-indexed positions and return a frozen ``MorningList``.

    Args:
        date: ISO-8601 ``YYYY-MM-DD``. ``None`` => today local.
        base_url: Vikunja API base URL.
        token_path: Path to the Vikunja API token file.

    Returns:
        A frozen ``MorningList`` with ``habits`` ordered by task_id ASC.

    Raises:
        ValueError: ``date`` does not match ``YYYY-MM-DD``.
        FileNotFoundError: ``token_path`` does not exist.
        OSError: token unreadable, or Vikunja API failure.
        urllib.error.URLError: Vikunja unreachable (subclass of OSError).
    """
    resolved_date = date if date is not None else _today_local()
    if not _DATE_RE.match(resolved_date):
        raise ValueError(
            f"date {resolved_date!r} must match YYYY-MM-DD"
        )

    token = _read_token(token_path)
    raw_habits = _query_habits(base_url, token, resolved_date)
    surviving = _exclude_already_addressed(raw_habits, resolved_date)

    # Sort by Vikunja task_id ASC -- the immutable per-task identifier.
    # Any other key (title, due_date, project order) would reintroduce
    # the #371 instability the moment Vikunja's underlying state shifts.
    def _id_key(task: dict) -> int:
        tid = task.get("id")
        if not isinstance(tid, int):
            raise ValueError(
                f"Vikunja habit task missing integer 'id': {task!r}"
            )
        return tid

    ordered = sorted(surviving, key=_id_key)

    habits = [
        MorningListHabit(
            position=index + 1,
            vikunja_task_id=_id_key(task),
            title=str(task.get("title", "")).strip(),
        )
        for index, task in enumerate(ordered)
    ]

    return MorningList(
        schema_version=SCHEMA_VERSION,
        date=resolved_date,
        generated_at=_now_utc_iso(),
        habits=habits,
    )


def persist_morning_list(
    morning_list: MorningList,
    *,
    state_dir: Path = DEFAULT_STATE_DIR,
) -> Path:
    """Atomically write ``morning_list`` to ``state_dir`` and return the path.

    Per research D2: write to ``<path>.tmp``, fsync, then ``os.replace`` to
    the final path. A crash before ``os.replace`` leaves only the ``.tmp``
    file -- the previous day's artifact (if any) is untouched, and the
    canonical ``morning-checkin-<date>.json`` either reflects the prior
    successful write or does not exist at all. No partial files are ever
    visible at the canonical path.

    Args:
        morning_list: The list to persist (typically from
            ``build_morning_list``).
        state_dir: Directory to write to. Created if missing.

    Returns:
        The final ``Path`` of the persisted file (after ``os.replace``).

    Raises:
        OSError: filesystem failure during mkdir, write, fsync, or replace.
    """
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)

    final_path = state_dir / f"morning-checkin-{morning_list.date}.json"
    tmp_path = state_dir / f"morning-checkin-{morning_list.date}.json.tmp"

    payload = _morning_list_to_dict(morning_list)
    body = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False)

    # Open with explicit flush + fsync so a power loss between the write
    # and the os.replace cannot leave a torn final file. The .tmp may be
    # left dangling on crash -- harmless; it's not at the canonical path.
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(body)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, final_path)
    except OSError:
        # Best-effort cleanup of the dangling tmp file so we don't pollute
        # the state dir on retry. Swallow secondary errors; the primary
        # one is what the caller needs to see.
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:  # pragma: no cover -- defensive
            pass
        raise

    return final_path


def render_morning_message(morning_list: MorningList) -> str:
    """Render the WhatsApp check-in message text for Kent.

    Empty list -> single line ``"All habits complete for today."`` per the
    existing SKILL.md / data-model convention.

    Otherwise the format (per contracts/cli.md) is::

        Morning check-in - <Day>, <Month> <DD>:

        1. <title>
        2. <title>
        ...

        Reply with what you've done (e.g., "1 and 2 done, skipping 4")

    where ``<Day>`` is the day-of-week (``%A``) derived from
    ``morning_list.date`` interpreted in America/New_York, and
    ``<Month> <DD>`` is ``"<full month> <day>"`` without zero-padding on
    the day. The day-stripping is portable across macOS (which does not
    accept ``%-d``) and Linux.
    """
    if not morning_list.habits:
        return "All habits complete for today."

    parsed = datetime.fromisoformat(morning_list.date).date()
    day_name = parsed.strftime("%A")
    month_name = parsed.strftime("%B")
    day_num = str(parsed.day)  # portable, no zero padding (cross-platform).

    header = f"Morning check-in — {day_name}, {month_name} {day_num}:"

    lines: list[str] = [header, ""]
    for h in morning_list.habits:
        lines.append(f"{h.position}. {h.title}")
    lines.append("")
    lines.append(
        "Reply with what you've done (e.g., \"1 and 2 done, skipping 4\")"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Private helpers (serialization)
# ---------------------------------------------------------------------------


def _morning_list_to_dict(morning_list: MorningList) -> dict[str, Any]:
    """Convert a ``MorningList`` to a JSON-serializable dict.

    ``dataclasses.asdict`` recurses into nested dataclasses (it doesn't
    require a custom encoder), but we route through it explicitly so the
    final shape is auditable in one place.
    """
    return dataclasses.asdict(morning_list)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class _ArgparseError(Exception):
    """Raised by ``_StructuredArgumentParser.error()`` to let ``main()`` return exit 3.

    The default ``argparse.ArgumentParser.error()`` calls ``sys.exit(2)``, which
    leaks through ``main()`` and violates ``contracts/cli.md`` (exit 2 is reserved
    for filesystem persistence failure; exit 3 is the canonical "validation /
    usage error" code). We catch this exception in ``main()`` and translate it
    to a structured stderr line + ``return 3``.
    """


class _StructuredArgumentParser(argparse.ArgumentParser):
    """ArgumentParser subclass that raises ``_ArgparseError`` instead of ``sys.exit(2)`` on bad flags.

    ``--help`` is unaffected: argparse's help path uses ``parser.exit()`` /
    ``parser._print_message``, not ``error()``, so it still exits 0 as expected.
    """

    def error(self, message: str) -> None:  # type: ignore[override]
        raise _ArgparseError(message)


def _build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser for the ``python3 -m`` entry point."""
    parser = _StructuredArgumentParser(
        prog="morning_checkin_list",
        description=(
            "Emit today's ordered habit list as both (a) a persisted JSON "
            "artifact at <state-dir>/morning-checkin-<date>.json and (b) "
            "the formatted WhatsApp check-in message on stdout. The "
            "artifact is the single source of truth for the reply-parse "
            "path; the message is what Felix relays to Kent. Use --dry-run "
            "to emit the message without writing the artifact."
        ),
    )
    parser.add_argument(
        "--date",
        default=None,
        help=(
            "Date in YYYY-MM-DD (default: today in America/New_York)."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip artifact persistence; emit only the formatted message.",
    )
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=DEFAULT_STATE_DIR,
        help=(
            f"Directory for the persisted artifact "
            f"(default: {DEFAULT_STATE_DIR})."
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
            f"Path to the Vikunja API token file "
            f"(default: {DEFAULT_TOKEN_PATH})."
        ),
    )
    return parser


def _emit_stderr_error(step: str, error: str) -> None:
    """Emit a single JSON line on stderr to keep error output structured."""
    msg = json.dumps({"step": step, "error": error}, ensure_ascii=False)
    print(msg, file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Exit codes per contracts/cli.md::

        0 -- success (message emitted; artifact written unless --dry-run)
        1 -- Vikunja unreachable / API failure
        2 -- Filesystem write failure (Vikunja succeeded; persist failed)
        3 -- Validation / usage error (bad date format, bad flags)
    """
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except _ArgparseError as exc:
        _emit_stderr_error(step="argparse", error=str(exc))
        return 3

    if args.date is not None:
        if not _DATE_RE.match(args.date):
            _emit_stderr_error(
                step="argparse",
                error=f"--date must match YYYY-MM-DD (got {args.date!r})",
            )
            return 3
        # Reject syntactically-valid-but-semantically-impossible dates
        # like 2026-13-99 (month/day out of range). fromisoformat is
        # strict on both range and length.
        try:
            datetime.fromisoformat(args.date).date()
        except ValueError as exc:
            _emit_stderr_error(
                step="argparse",
                error=(
                    f"--date must be a real YYYY-MM-DD date "
                    f"(got {args.date!r}): {exc}"
                ),
            )
            return 3

    try:
        morning_list = build_morning_list(
            date=args.date,
            base_url=args.base_url,
            token_path=args.token_path,
        )
    except ValueError as exc:
        _emit_stderr_error(step="argparse", error=str(exc))
        return 3
    except FileNotFoundError as exc:
        _emit_stderr_error(step="token_read", error=str(exc))
        return 1
    except urllib.error.URLError as exc:
        _emit_stderr_error(step="vikunja_fetch", error=str(exc))
        return 1
    except OSError as exc:
        _emit_stderr_error(step="vikunja_fetch", error=str(exc))
        return 1

    if not args.dry_run:
        try:
            persist_morning_list(morning_list, state_dir=args.state_dir)
        except OSError as exc:
            _emit_stderr_error(step="persist", error=str(exc))
            return 2

    sys.stdout.write(render_morning_message(morning_list))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
