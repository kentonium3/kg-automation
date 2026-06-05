#!/usr/bin/env python3
"""Set Vikunja `due_date` to end-of-day Eastern Time on a list of habit IDs.

GET phase reads task state from the Felix sync cache at
/data/services/openclaw/state/sync/task-cache.json
(see scripts/common/sync_cache.py for the canonical entry point).
PUT phase writes new due_date values back to Vikunja via direct HTTP POST
(per #524's read-modify-write pattern — TP-05 write-only, out of scope for
cache migration per spec FR-010).

Mission #282 / FR-003. Part of the felix-admin-habits Steps 1-4 refactor
(per Constitution Directive 6 and `docs/design/helper-script-conventions.md`).

LOAD-BEARING for issue #112 regression-prevention. The bug fixed by #112:
habit due_dates anchored to UTC midnight caused them to appear overdue
the moment the morning cron fires at 7:05 AM ET. The fix is end-of-day-ET
(`23:59:59` with an explicit `-04:00` or `-05:00` offset), NOT UTC `Z`.

This helper rejects any `--iso-eod-et` value ending with `Z` (UTC) at
startup with exit code 2. The helper does NOT auto-convert UTC to ET —
auto-conversion was rejected during design as defeating the regression-
prevention guarantee.

Per-habit-failure resilience: if PUT fails on one habit, the helper
continues with the remaining habits, accumulates failures, and signals
partial-state via exit code 1 (non-zero) with a non-empty `succeeded`
array in the output. The calling agent's failure-handling clause uses
this signal to continue the check-in workflow with the succeeded subset.

Invocation:

    python3 scripts/habits/set_due_dates.py \\
        --habit-ids 123,124,125 \\
        --iso-eod-et 2026-05-15T23:59:59-04:00 \\
        [--vikunja-token-path /data/services/openclaw/secrets/vikunja-api] \\
        [--vikunja-base-url <url>] \\
        [--dry-run]

Output (stdout):

    {"succeeded": [123, 124], "failed": [{"id": 125, "reason": "HTTP 500: ..."}]}
    SUMMARY: total=3 succeeded=2 failed=1

Exit codes:
    0 — all habits set successfully (or --dry-run completed)
    1 — at least one habit failed (partial state). `succeeded` may still be non-empty.
    2 — usage error (--iso-eod-et ends with Z, malformed timestamp, etc.)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

try:
    from scripts.common.sync_cache import (
        SLA_NORMAL,
        SLATier,
        read_cached_task_by_id,
    )
    from scripts.common.vikunja_config import get_vikunja_base_url
except ImportError:
    # Fallback for direct-script invocation (`python3 scripts/habits/set_due_dates.py`).
    # Under that form only scripts/habits/ is on sys.path, so the absolute-package
    # import above fails. Insert the repo root (two levels up from scripts/habits/)
    # so that ``scripts.common.sync_cache`` and its own ``scripts.sync.state``
    # transitive import can both resolve.
    # Precedent: scripts/openclaw/observation/summarize.py:36-38.
    import sys as _sys
    _repo_root = str(Path(__file__).resolve().parent.parent.parent)
    if _repo_root not in _sys.path:
        _sys.path.insert(0, _repo_root)
    from scripts.common.sync_cache import (  # type: ignore[no-redef]
        SLA_NORMAL,
        SLATier,
        read_cached_task_by_id,
    )
    from scripts.common.vikunja_config import (  # type: ignore[no-redef]
        get_vikunja_base_url,
    )

try:
    from scripts.habits.schedule_loader import (
        ScheduleConfigError,
        ScheduleEntry,
        WEEKDAY_NAMES,
        is_day_specific,
        load_schedule,
    )
except ImportError:
    # Fallback for direct-script invocation (`python3 scripts/habits/set_due_dates.py`).
    # The absolute-package import above resolves only under `python3 -m scripts.habits.set_due_dates`;
    # both invocation forms are documented (see module docstring) and used in production.
    # Precedent: scripts/openclaw/observation/summarize.py:36-38.
    from schedule_loader import (  # type: ignore[no-redef]
        ScheduleConfigError,
        ScheduleEntry,
        WEEKDAY_NAMES,
        is_day_specific,
        load_schedule,
    )


TOUCHPOINT_SLA: SLATier = SLA_NORMAL
TOUCHPOINT_NAME = "habits.set_due_dates"

DEFAULT_TOKEN_PATH = Path("/data/services/openclaw/secrets/vikunja-api")

#: Default in-repo path to the runtime schedule YAML. Mirrors the default
#: used by ``morning_checkin_list`` so both helpers agree on the source.
DEFAULT_SCHEDULE_PATH = (
    Path(__file__).resolve().parent / "migrations" / "phase3-schedule.yaml"
)

#: Default directory for reconciliation record artifacts (mission #408 / E5).
DEFAULT_RECONCILE_DIR = Path("/data/services/openclaw/state/habits")

# Required shape: YYYY-MM-DDT23:59:59<+/-NN:NN> — explicit ET offset, NOT 'Z'.
# This regex is the regression-prevention backstop for #112.
ISO_EOD_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T23:59:59[+-]\d{2}:\d{2}$")

#: Reconciliation record schema version (mission #408 / E5).
RECONCILE_SCHEMA_VERSION = 1

#: Kent's local timezone — all due_date math runs in ET.
ET_ZONE = ZoneInfo("America/New_York")

#: Map Python ``datetime.weekday()`` ints (Mon=0..Sun=6) to ISO 3-letter names.
_WEEKDAY_BY_INDEX: tuple[str, ...] = WEEKDAY_NAMES

#: Reverse map: 3-letter ISO weekday name -> Python weekday() int.
_INDEX_BY_WEEKDAY: dict[str, int] = {name: i for i, name in enumerate(WEEKDAY_NAMES)}


def validate_iso_eod_et(value: str) -> str | None:
    """Return None if value is acceptable; else an error message describing why.

    The 'Z' suffix check is the critical #112 regression-prevention guard.
    """
    if value.endswith("Z"):
        return (
            "--iso-eod-et ends with 'Z' (UTC). Issue #112 forbids UTC due_date — "
            "must use explicit ET offset (-04:00 EDT or -05:00 EST). "
            "Helper does NOT auto-convert; reject and require correct input."
        )
    if not ISO_EOD_PATTERN.match(value):
        return (
            f"--iso-eod-et {value!r} does not match expected format "
            f"YYYY-MM-DDT23:59:59<+/-NN:NN>"
        )
    return None


def _load_token(path: Path) -> str:
    """Read Vikunja API token from a mode-600 file."""
    return path.read_text(encoding="utf-8").strip()


def _http_put(
    base_url: str,
    token: str,
    path: str,
    body: dict,
    timeout: int = 15,
) -> object:
    """PUT request to Vikunja with bearer auth. Returns parsed JSON response."""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}{path}",
        data=data,
        method="POST",  # Vikunja /tasks/{id} uses POST for partial updates
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _format_et_offset(offset_str: str) -> str:
    """Convert ``%z`` output (``-0400``) to ``-04:00`` per ISO-8601."""
    if len(offset_str) == 5 and offset_str[0] in ("+", "-"):
        return f"{offset_str[:3]}:{offset_str[3:]}"
    return offset_str


def compute_next_eod_et_for_weekdays(
    designated_weekdays: tuple[str, ...],
    *,
    now_utc: datetime,
) -> str:
    """Return the next end-of-day-ET ISO timestamp matching a designated set.

    For day-specific habits the next due date is the next occurrence (today
    inclusive) of any weekday in ``designated_weekdays``, anchored to
    ``23:59:59`` in Kent's local ET. Used by ``--reconcile-schedule``.

    The returned string is in the same shape as ``--iso-eod-et`` accepts:
    ``YYYY-MM-DDT23:59:59<offset>`` where the offset is ``-04:00`` (EDT) or
    ``-05:00`` (EST). The shape passes :func:`validate_iso_eod_et` and so
    preserves the #112 regression-prevention guard.

    Args:
        designated_weekdays: Non-empty tuple of 3-letter ISO weekday names.
        now_utc: Current UTC instant (injected for deterministic tests).

    Returns:
        ISO-8601 EOD-ET timestamp string.

    Raises:
        ValueError: ``designated_weekdays`` is empty or contains an invalid
            weekday name.
    """
    if not designated_weekdays:
        raise ValueError(
            "compute_next_eod_et_for_weekdays requires at least one weekday"
        )
    target_indices: set[int] = set()
    for name in designated_weekdays:
        if name not in _INDEX_BY_WEEKDAY:
            raise ValueError(
                f"unknown weekday {name!r} (expected one of {list(WEEKDAY_NAMES)})"
            )
        target_indices.add(_INDEX_BY_WEEKDAY[name])

    et_now = now_utc.astimezone(ET_ZONE)
    today_et = et_now.date()
    for delta in range(7):
        candidate = today_et + timedelta(days=delta)
        if candidate.weekday() in target_indices:
            # Anchor to 23:59:59 in ET so DST transitions land on the right
            # offset (compute_today.py uses the same pattern).
            anchor = datetime(
                candidate.year,
                candidate.month,
                candidate.day,
                23,
                59,
                59,
                tzinfo=ET_ZONE,
            )
            offset = _format_et_offset(anchor.strftime("%z"))
            return f"{candidate.isoformat()}T23:59:59{offset}"
    # Unreachable — any non-empty target_indices is hit within 7 days.
    raise AssertionError(  # pragma: no cover -- defensive
        f"no weekday match found in 7-day search for {designated_weekdays!r}"
    )


def _reconcile_record_path(
    state_dir: Path, now_utc: datetime
) -> Path:
    """Path for a reconciliation record file (one per run)."""
    stamp = now_utc.strftime("%Y-%m-%dT%H-%M-%SZ")
    return Path(state_dir) / f"reconcile-{stamp}.json"


def _atomic_write_json(path: Path, payload: dict) -> None:
    """Write ``payload`` to ``path`` via tmp+fsync+rename for crash safety."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    body = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False)
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(body)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:  # pragma: no cover -- defensive
            pass
        raise


def reconcile_schedule(
    *,
    schedule_path: Path,
    base_url: str,
    token: str,
    reconcile_dir: Path,
    now_utc: datetime,
    dry_run: bool = False,
) -> dict:
    """Reconcile Vikunja due_dates against the current schedule (mission #408).

    For each schedule entry with ``designated_weekdays`` set:
      - Fetch the current Vikunja task's ``due_date``.
      - Compute the expected next-EOD-ET for the designated weekday set.
      - If the current value differs, POST the new value (Vikunja's
        partial-update verb). Otherwise no-op.
    Daily entries (no designated_weekdays) are skipped — Vikunja's native
    repeat handles their cadence.

    Writes a reconciliation record (E5) to ``reconcile_dir`` and returns
    the structured result dict for the CLI to print on stdout.

    Per-habit-failure resilience: a single failed Vikunja call records an
    error and continues; partial state is signalled via the ``errors`` list
    (the CLI maps non-empty errors to exit 1). Validates each computed
    ``new_due_date`` against :func:`validate_iso_eod_et` so the #112
    regression-prevention guard applies to the reconciliation path too.

    Args:
        schedule_path: Path to the schedule YAML.
        base_url: Vikunja API base URL.
        token: Vikunja bearer token (unused in ``dry_run``).
        reconcile_dir: Directory the E5 record is written to.
        now_utc: Current UTC instant (injected for deterministic tests).
        dry_run: When True, no HTTP calls are made and no PUTs are issued.
            The record still records what WOULD have happened.

    Returns:
        ``{"reconciled": [...], "skipped_no_change": [...], "errors": [...],
        "schedule_sha256": str, "record_path": str}``.

    Raises:
        ScheduleConfigError: Schedule YAML invalid (load-time error).
    """
    entries = load_schedule(schedule_path)
    day_specific = [e for e in entries if is_day_specific(e)]

    schedule_sha = hashlib.sha256(
        Path(schedule_path).read_bytes()
    ).hexdigest()

    reconciled: list[dict] = []
    skipped: list[int] = []
    errors: list[dict] = []
    record_habits: list[dict] = []

    for entry in day_specific:
        try:
            new_due = compute_next_eod_et_for_weekdays(
                entry.designated_weekdays, now_utc=now_utc
            )
        except ValueError as exc:  # pragma: no cover -- guarded at load time
            # schedule_loader validates designated_weekdays at load time, so
            # compute_next_eod_et_for_weekdays should never see an unknown
            # name here. Keep the handler in case the YAML reload contract
            # changes; mark as defensive.
            errors.append(
                {
                    "task_id": entry.task_id,
                    "error_type": "weekday_computation",
                    "error_message": str(exc),
                }
            )
            continue

        # The #112 regression-prevention guard MUST hold on the computed
        # value too — defensive double-check. compute_next_eod_et_for_weekdays
        # is unit-tested to always produce a passing string; this branch is
        # safety-net for a future regression in the date math.
        guard = validate_iso_eod_et(new_due)
        if guard is not None:  # pragma: no cover -- defensive (#112 guard)
            errors.append(
                {
                    "task_id": entry.task_id,
                    "error_type": "iso_eod_validation",
                    "error_message": guard,
                }
            )
            continue

        # Fetch current due_date from the sync cache (GET phase migrated to
        # cache read per mission #519 WP02 / FR-004).
        # PUT phase (below) stays on direct Vikunja HTTP per spec FR-010.
        current_due: str | None = None
        if dry_run:
            current_due = None  # Unknown without cache read in dry_run.
        else:
            try:
                view = read_cached_task_by_id(
                    task_id=entry.task_id,
                    sla=TOUCHPOINT_SLA,
                    touchpoint_name=TOUCHPOINT_NAME,
                )
                raw_due = view.fields.get("due_date")
                current_due = raw_due if isinstance(raw_due, str) else None
            except OSError as exc:
                errors.append(
                    {
                        "task_id": entry.task_id,
                        "error_type": "cache_read",
                        "error_message": str(exc),
                    }
                )
                continue

        if current_due == new_due:
            skipped.append(entry.task_id)
            record_habits.append(
                {
                    "task_id": entry.task_id,
                    "title": entry.title,
                    "old_designated_weekdays": list(entry.designated_weekdays),
                    "new_designated_weekdays": list(entry.designated_weekdays),
                    "old_due_date": current_due,
                    "new_due_date": new_due,
                    "action": "no_change",
                }
            )
            continue

        # Issue PUT (POST in Vikunja's partial-update convention) unless dry_run.
        if dry_run:
            reconciled.append(
                {
                    "task_id": entry.task_id,
                    "old_due_date": current_due,
                    "new_due_date": new_due,
                    "dry_run": True,
                }
            )
            record_habits.append(
                {
                    "task_id": entry.task_id,
                    "title": entry.title,
                    "old_designated_weekdays": list(entry.designated_weekdays),
                    "new_designated_weekdays": list(entry.designated_weekdays),
                    "old_due_date": current_due,
                    "new_due_date": new_due,
                    "action": "would_advance",
                }
            )
            continue

        try:
            _http_put(
                base_url,
                token,
                f"tasks/{entry.task_id}",
                {"due_date": new_due},
            )
        except urllib.error.HTTPError as exc:
            errors.append(
                {
                    "task_id": entry.task_id,
                    "error_type": "vikunja_put",
                    "error_message": f"HTTP {exc.code}: {exc.reason}",
                }
            )
            continue
        except urllib.error.URLError as exc:
            errors.append(
                {
                    "task_id": entry.task_id,
                    "error_type": "vikunja_put",
                    "error_message": f"URLError: {exc.reason}",
                }
            )
            continue

        reconciled.append(
            {
                "task_id": entry.task_id,
                "old_due_date": current_due,
                "new_due_date": new_due,
            }
        )
        record_habits.append(
            {
                "task_id": entry.task_id,
                "title": entry.title,
                "old_designated_weekdays": list(entry.designated_weekdays),
                "new_designated_weekdays": list(entry.designated_weekdays),
                "old_due_date": current_due,
                "new_due_date": new_due,
                "action": "advanced",
            }
        )

    record_path = _reconcile_record_path(reconcile_dir, now_utc)
    record = {
        "schema_version": RECONCILE_SCHEMA_VERSION,
        "reconciled_at_utc": (
            now_utc.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
        ),
        "operator": os.environ.get("USER", "unknown"),
        "schedule_file_sha256": schedule_sha,
        "schedule_path": str(schedule_path),
        "dry_run": dry_run,
        "habits_reconciled": record_habits,
        "errors": errors,
    }
    _atomic_write_json(record_path, record)

    return {
        "reconciled": reconciled,
        "skipped_no_change": skipped,
        "errors": errors,
        "schedule_sha256": schedule_sha,
        "record_path": str(record_path),
    }


def parse_habit_ids(comma_separated: str) -> list[int]:
    """Parse comma-separated string of integer IDs. Returns empty list for empty input."""
    if not comma_separated.strip():
        return []
    parts = [p.strip() for p in comma_separated.split(",") if p.strip()]
    return [int(p) for p in parts]


def _run_reconcile_mode(args: argparse.Namespace) -> int:
    """Drive the --reconcile-schedule path. Returns the CLI exit code.

    Exit codes (parallel to the existing --iso-eod-et mode):
        0 -- success (zero errors)
        1 -- at least one per-habit error (partial state)
        2 -- usage / schedule validation error
    """
    # Load the token (skipped in dry-run since no HTTP).
    if args.dry_run:
        token = ""
    else:
        try:
            token = _load_token(args.vikunja_token_path)
        except FileNotFoundError:
            print(
                f"ERROR: Vikunja token file not found: "
                f"{args.vikunja_token_path}",
                file=sys.stderr,
            )
            return 1
        except PermissionError:
            print(
                f"ERROR: permission denied reading Vikunja token: "
                f"{args.vikunja_token_path}",
                file=sys.stderr,
            )
            return 1

    now_utc = datetime.now(timezone.utc)
    try:
        result = reconcile_schedule(
            schedule_path=args.schedule_path,
            base_url=args.vikunja_base_url,
            token=token,
            reconcile_dir=args.reconcile_record_dir,
            now_utc=now_utc,
            dry_run=args.dry_run,
        )
    except ScheduleConfigError as exc:
        print(f"ERROR: schedule config: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"ERROR: reconcile I/O failure: {exc}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "reconciled": result["reconciled"],
                "skipped_no_change": result["skipped_no_change"],
                "errors": result["errors"],
                "record_path": result["record_path"],
            }
        )
    )
    dry_marker = " (DRY-RUN)" if args.dry_run else ""
    print(
        f"SUMMARY: reconciled={len(result['reconciled'])} "
        f"skipped={len(result['skipped_no_change'])} "
        f"errors={len(result['errors'])}{dry_marker}"
    )
    return 1 if result["errors"] else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n\n", maxsplit=1)[0],
    )
    parser.add_argument(
        "--habit-ids",
        type=str,
        required=False,
        default=None,
        help=(
            "Comma-separated integer habit IDs (e.g., 123,124,125). Empty "
            "allowed. Required unless --reconcile-schedule is set."
        ),
    )
    parser.add_argument(
        "--iso-eod-et",
        type=str,
        required=False,
        default=None,
        help=(
            "End-of-day-ET ISO timestamp (e.g., 2026-05-15T23:59:59-04:00). "
            "MUST NOT end with 'Z' (issue #112 regression-prevention). "
            "Required unless --reconcile-schedule is set."
        ),
    )
    parser.add_argument(
        "--vikunja-token-path",
        type=Path,
        default=DEFAULT_TOKEN_PATH,
        help="Path to the Vikunja API token (mode-600 file)",
    )
    parser.add_argument(
        "--vikunja-base-url",
        type=str,
        default=None,
        help="Vikunja API base URL (default: from vikunja_config helper)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't actually PUT; print what would happen. Makes NO HTTP calls.",
    )
    parser.add_argument(
        "--reconcile-schedule",
        action="store_true",
        help=(
            "Reconcile day-specific habit due_dates against the schedule "
            "YAML (mission #408 / FR-010). Mutually exclusive with "
            "--iso-eod-et mode. Reads --schedule-path, advances each "
            "day-specific habit's due_date to the next designated weekday "
            "at end-of-ET-day, writes an E5 reconciliation record."
        ),
    )
    parser.add_argument(
        "--schedule-path",
        type=Path,
        default=DEFAULT_SCHEDULE_PATH,
        help=(
            f"Path to the habits schedule YAML for --reconcile-schedule "
            f"(default: {DEFAULT_SCHEDULE_PATH})."
        ),
    )
    parser.add_argument(
        "--reconcile-record-dir",
        type=Path,
        default=DEFAULT_RECONCILE_DIR,
        help=(
            f"Directory where reconciliation records are written "
            f"(default: {DEFAULT_RECONCILE_DIR})."
        ),
    )
    args = parser.parse_args(argv)
    # Lazy URL resolution: read from vikunja_config when not explicitly provided.
    if args.vikunja_base_url is None:
        args.vikunja_base_url = get_vikunja_base_url()

    # Mutually exclusive: --reconcile-schedule vs --iso-eod-et mode.
    if args.reconcile_schedule:
        if args.iso_eod_et is not None or args.habit_ids is not None:
            print(
                "ERROR: --reconcile-schedule is mutually exclusive with "
                "--iso-eod-et / --habit-ids",
                file=sys.stderr,
            )
            return 2
        return _run_reconcile_mode(args)

    # Existing --iso-eod-et mode: both --iso-eod-et and --habit-ids required.
    if args.iso_eod_et is None or args.habit_ids is None:
        print(
            "ERROR: --iso-eod-et and --habit-ids are required unless "
            "--reconcile-schedule is set",
            file=sys.stderr,
        )
        return 2

    # Critical: validate --iso-eod-et FIRST, before any HTTP setup.
    # This is the #112 regression-prevention guard.
    error = validate_iso_eod_et(args.iso_eod_et)
    if error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    try:
        habit_ids = parse_habit_ids(args.habit_ids)
    except ValueError as exc:
        print(f"ERROR: --habit-ids parse failure: {exc}", file=sys.stderr)
        return 2

    # Empty habit list is not an error — just nothing to do.
    if not habit_ids:
        result = {"succeeded": [], "failed": []}
        print(json.dumps(result))
        print("SUMMARY: total=0 succeeded=0 failed=0")
        return 0

    # Load token (skipped in --dry-run since we're not calling Vikunja)
    if args.dry_run:
        token = ""  # unused
    else:
        try:
            token = _load_token(args.vikunja_token_path)
        except FileNotFoundError:
            print(
                f"ERROR: Vikunja token file not found: {args.vikunja_token_path}",
                file=sys.stderr,
            )
            return 1
        except PermissionError:
            print(
                f"ERROR: permission denied reading Vikunja token: "
                f"{args.vikunja_token_path}",
                file=sys.stderr,
            )
            return 1

    succeeded: list[int] = []
    failed: list[dict] = []
    body = {"due_date": args.iso_eod_et}

    for habit_id in habit_ids:
        if args.dry_run:
            print(
                f"INFO: [dry-run] would PUT habit {habit_id} due_date={args.iso_eod_et}",
                file=sys.stderr,
            )
            succeeded.append(habit_id)
            continue
        try:
            _http_put(
                args.vikunja_base_url,
                token,
                f"tasks/{habit_id}",
                body,
            )
            succeeded.append(habit_id)
        except urllib.error.HTTPError as exc:
            reason = f"HTTP {exc.code}: {exc.reason}"
            print(f"ERROR: habit {habit_id} PUT failed: {reason}", file=sys.stderr)
            failed.append({"id": habit_id, "reason": reason})
        except urllib.error.URLError as exc:
            reason = f"URLError: {exc.reason}"
            print(f"ERROR: habit {habit_id} PUT failed: {reason}", file=sys.stderr)
            failed.append({"id": habit_id, "reason": reason})
        except Exception as exc:  # pragma: no cover — defensive
            reason = f"{type(exc).__name__}: {exc}"
            print(f"ERROR: habit {habit_id} PUT failed: {reason}", file=sys.stderr)
            failed.append({"id": habit_id, "reason": reason})

    result = {"succeeded": succeeded, "failed": failed}
    print(json.dumps(result))
    dry_marker = " (DRY-RUN)" if args.dry_run else ""
    print(
        f"SUMMARY: total={len(habit_ids)} succeeded={len(succeeded)} "
        f"failed={len(failed)}{dry_marker}"
    )

    # Partial-failure semantics: exit 1 if any habit failed (non-empty failed list).
    # This includes the case "0 succeeded, N failed" (total failure).
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
