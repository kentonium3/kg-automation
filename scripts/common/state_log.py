"""Felix agent state log — JSONL append/read I/O layer.

This is the canonical Python entry point for the shared JSONL state log
described in ADR-0002 Phase 2. Every Vikunja-touching Felix agent writes
through ``append()`` and reads through ``read()`` so the per-domain history
under ``/data/services/openclaw/state/`` stays consistent.

Contract: ``kitty-specs/shared-jsonl-state-log-library-01KS0E9A/contracts/api.md``
CLI surface: ``kitty-specs/shared-jsonl-state-log-library-01KS0E9A/contracts/cli.md``
On-disk format: ``kitty-specs/shared-jsonl-state-log-library-01KS0E9A/contracts/jsonl.md``

Key design points:

- ``STATE_DIR`` is a module-level constant (and may be overridden via the
  ``FELIX_STATE_LOG_DIR`` environment variable). Tests monkey-patch it to a
  temp directory; subprocess-based tests use the env var.
- ``append()`` holds an ``fcntl.LOCK_EX`` exclusive lock across the entire
  read-check-write critical section to keep idempotency dedup correct under
  concurrent writers.
- ``read()`` holds an ``fcntl.LOCK_SH`` shared lock for the duration of the
  scan; concurrent readers do not block each other but a concurrent
  ``append()`` waits for them.
- Stdlib-only. No third-party imports. No network I/O.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
from pathlib import Path
from typing import Any

from scripts.common.state_log_schema import (
    DOMAIN_STATES,
    REQUIRED_FIELDS,
    validate_record,
)

__all__ = [
    "append",
    "read",
    "validate_record",
    "DOMAIN_STATES",
    "REQUIRED_FIELDS",
    "STATE_DIR",
    "STATE_FILE_MODE",
    "STATE_DIR_MODE",
]


# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

#: Canonical state-log directory. Override via the ``FELIX_STATE_LOG_DIR``
#: environment variable; tests also monkey-patch this module-level attribute
#: directly (subprocess-based tests must use the env var because monkey-patch
#: does not cross process boundaries).
STATE_DIR: Path = Path(
    os.environ.get("FELIX_STATE_LOG_DIR", "/data/services/openclaw/state")
)

#: File mode for the per-domain JSONL files (0664 = rw-rw-r--).
STATE_FILE_MODE: int = 0o664

#: Directory mode for the parent state directory (0775 = rwxrwxr-x).
STATE_DIR_MODE: int = 0o775

#: Filter kwargs accepted by ``read()``. Anything outside this set raises
#: ``TypeError`` (defensive — caller probably typo'd).
_ALLOWED_FILTER_KEYS: frozenset[str] = frozenset(
    {"task_id", "date", "date_from", "date_to", "state", "source"}
)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _state_file(domain: str) -> Path:
    """Return the absolute path of the per-domain JSONL file.

    Raises ``ValueError`` if ``domain`` is not in ``DOMAIN_STATES``.
    """
    if domain not in DOMAIN_STATES:
        known = ", ".join(sorted(DOMAIN_STATES.keys()))
        raise ValueError(
            f"domain '{domain}' not in known domains {{{known}}}"
        )
    return STATE_DIR / f"{domain}-history.jsonl"


def _ensure_dir() -> None:
    """Create ``STATE_DIR`` if missing.

    Best-effort sets the directory group to ``secondbrain`` when present;
    silent on failure because group ownership is advisory only.
    """
    if not STATE_DIR.exists():
        STATE_DIR.mkdir(parents=True, mode=STATE_DIR_MODE, exist_ok=True)

    # Best-effort group ownership; silent on failure.
    try:
        import grp  # type: ignore[import-not-found]

        gid = grp.getgrnam("secondbrain").gr_gid
        os.chown(STATE_DIR, -1, gid)
    except Exception:
        pass


def _idempotency_match(
    file_path: Path, task_id: int, date: str, state: str
) -> bool:
    """Return True if a line with the given ``(task_id, date, state)`` exists.

    Tolerates malformed lines (skipped silently) so a partial last line from
    a crashed write does not poison the dedup check.
    """
    if not file_path.exists():
        return False

    target = (task_id, date, state)
    with open(file_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except (ValueError, TypeError):
                continue
            try:
                existing = (obj["task_id"], obj["date"], obj["state"])
            except (KeyError, TypeError):
                continue
            if existing == target:
                return True
    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def append(domain: str, record: dict) -> None:
    """Append a state-log record to the per-domain JSONL file.

    See ``contracts/api.md`` for the full contract. Validates the record,
    creates the state directory and file as needed, holds ``fcntl.LOCK_EX``
    across the read-check-write critical section, and treats a matching
    ``(task_id, date, state)`` tuple as an idempotent no-op.

    Args:
        domain: One of ``DOMAIN_STATES.keys()``.
        record: Dict containing all ``REQUIRED_FIELDS``. ``note`` is optional.

    Raises:
        ValueError: If validation fails.
        OSError: If the underlying file I/O fails.
    """
    validate_record(record, domain)
    _ensure_dir()

    path = _state_file(domain)

    fd = os.open(
        str(path),
        os.O_WRONLY | os.O_CREAT | os.O_APPEND,
        STATE_FILE_MODE,
    )
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        # We hold LOCK_EX, so opening a separate read handle on the same file
        # sees a consistent view for the dedup check.
        if _idempotency_match(
            path, record["task_id"], record["date"], record["state"]
        ):
            return
        line = json.dumps(record, ensure_ascii=False, sort_keys=False) + "\n"
        os.write(fd, line.encode("utf-8"))
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def read(domain: str, **filters: Any) -> list[dict]:
    """Read state-log records for ``domain``, optionally filtered.

    See ``contracts/api.md`` for the full contract.

    Args:
        domain: One of ``DOMAIN_STATES.keys()``.
        **filters: Optional kwargs — ``task_id``, ``date``, ``date_from``,
            ``date_to``, ``state``, ``source``. AND-combined.

    Returns:
        List of record dicts in file (append) order. Empty list if the file
        does not exist yet or no records match.

    Raises:
        ValueError: If ``domain`` is unknown.
        TypeError: If an unknown filter kwarg is passed.
        OSError: If the file exists but cannot be read.
    """
    path = _state_file(domain)

    unknown = set(filters) - _ALLOWED_FILTER_KEYS
    if unknown:
        allowed = ", ".join(sorted(_ALLOWED_FILTER_KEYS))
        bad = ", ".join(sorted(unknown))
        raise TypeError(
            f"unknown filter kwargs: {bad} (allowed: {allowed})"
        )

    if not path.exists():
        return []

    results: list[dict] = []
    fd = os.open(str(path), os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_SH)
        with os.fdopen(fd, "r", encoding="utf-8", closefd=False) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except (ValueError, TypeError):
                    continue
                if _matches(obj, filters):
                    results.append(obj)
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
    return results


def _matches(record: dict, filters: dict) -> bool:
    """Return True if ``record`` satisfies all filter predicates.

    Filters are AND-combined. Missing keys on the record fail the match.
    """
    if "task_id" in filters and record.get("task_id") != filters["task_id"]:
        return False
    if "date" in filters and record.get("date") != filters["date"]:
        return False
    if "state" in filters and record.get("state") != filters["state"]:
        return False
    if "source" in filters and record.get("source") != filters["source"]:
        return False
    rec_date = record.get("date")
    if "date_from" in filters:
        if not isinstance(rec_date, str) or rec_date < filters["date_from"]:
            return False
    if "date_to" in filters:
        if not isinstance(rec_date, str) or rec_date > filters["date_to"]:
            return False
    return True


# ---------------------------------------------------------------------------
# CLI surface (T004)
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser for the ``python3 -m`` entry point."""
    parser = argparse.ArgumentParser(
        prog="python3 -m scripts.common.state_log",
        description=(
            "Felix agent state log — append/read JSONL records per domain. "
            "See contracts/cli.md for the full contract."
        ),
    )
    subparsers = parser.add_subparsers(dest="subcommand")

    domain_choices = sorted(DOMAIN_STATES.keys())

    append_p = subparsers.add_parser(
        "append",
        help="Append a record read from stdin (one JSON object on one line).",
        description=(
            "Read a single JSON record from stdin and append it to the "
            "per-domain JSONL file. The record's 'domain' field must match "
            "--domain. Idempotent on (task_id, date, state)."
        ),
    )
    append_p.add_argument(
        "--domain",
        required=True,
        choices=domain_choices,
        help="Target domain (must match the 'domain' field on the record).",
    )

    read_p = subparsers.add_parser(
        "read",
        help="Read records for a domain, optionally filtered.",
        description=(
            "Print matching records to stdout, one JSON object per line, in "
            "append (file) order. AND-combined filters. Empty stdout for no "
            "matches."
        ),
    )
    read_p.add_argument(
        "--domain", required=True, choices=domain_choices,
        help="Target domain.",
    )
    read_p.add_argument("--task-id", type=int, help="Exact match on task_id.")
    read_p.add_argument("--date", help="Exact ISO-8601 date match.")
    read_p.add_argument(
        "--date-from", help="Inclusive lower bound (ISO-8601 date)."
    )
    read_p.add_argument(
        "--date-to", help="Inclusive upper bound (ISO-8601 date)."
    )
    read_p.add_argument("--state", help="Exact state value match.")
    read_p.add_argument("--source", help="Exact source value match.")

    return parser


def _cmd_append(args: argparse.Namespace) -> int:
    raw = sys.stdin.read().strip()
    if not raw:
        print(
            "error: no record on stdin (pipe a single JSON object)",
            file=sys.stderr,
        )
        return 3
    try:
        record = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"error: malformed JSON on stdin: {exc}", file=sys.stderr)
        return 3
    if not isinstance(record, dict):
        print(
            f"error: stdin record must be a JSON object "
            f"(got {type(record).__name__})",
            file=sys.stderr,
        )
        return 3
    try:
        append(args.domain, record)
    except ValueError as exc:
        print(f"error: validation failed: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: I/O failure: {exc}", file=sys.stderr)
        return 2
    return 0


def _cmd_read(args: argparse.Namespace) -> int:
    # Build filter dict from non-None args, dropping subcommand + domain.
    raw = vars(args)
    skip = {"subcommand", "domain", "func"}
    # Translate dashes from CLI flag names back to kwarg names.
    cli_to_kwarg = {
        "task_id": "task_id",
        "date": "date",
        "date_from": "date_from",
        "date_to": "date_to",
        "state": "state",
        "source": "source",
    }
    filters: dict[str, Any] = {}
    for key, value in raw.items():
        if key in skip or value is None:
            continue
        if key in cli_to_kwarg:
            filters[cli_to_kwarg[key]] = value
    try:
        records = read(args.domain, **filters)
    except (ValueError, TypeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    except OSError as exc:
        print(f"error: I/O failure: {exc}", file=sys.stderr)
        return 2
    out = sys.stdout
    for record in records:
        out.write(json.dumps(record, ensure_ascii=False, sort_keys=False))
        out.write("\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. See contracts/cli.md for exit codes 0/1/2/3."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.subcommand == "append":
        return _cmd_append(args)
    if args.subcommand == "read":
        return _cmd_read(args)
    parser.print_help(sys.stderr)
    return 3


if __name__ == "__main__":
    sys.exit(main())
