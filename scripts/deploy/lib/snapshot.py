"""Restic backup-recency verification.

The ``claude`` user on office2 cannot currently query the Restic repository
directly (see the Felix charter "Deployment Constraints" section). The
fallback signal is the daily backup log written by the Restic driver to
``/data/services/backup/logs/backup-YYYY-MM-DD.log``. A "completed" line
within the window is treated as evidence of a recent successful snapshot.

This module is a defence-in-depth check used by the applier for Tier 2
deploys (per ``data-model.md`` apply orchestration); Tier 1 callers may also
opt in.
"""

from __future__ import annotations

import datetime as _dt
import re
from pathlib import Path

from . import LibResult

DEFAULT_LOG_DIR = Path("/data/services/backup/logs")
LOG_PREFIX = "backup-"
LOG_SUFFIX = ".log"

# Match a wide-but-bounded set of "completed" signatures the Restic driver
# has emitted across versions. The check is greedy but case-insensitive and
# tolerates surrounding diagnostics; the goal is "did a snapshot finish
# successfully in this log".
_COMPLETED_RE = re.compile(
    r"(snapshot\s+saved|backup\s+complete[d]?|restic\s+backup\s+succeeded|status:\s*ok)",
    re.IGNORECASE,
)
# Match an ISO-style or syslog-style timestamp at the start of a log line, so
# we can compare the most recent completed line's timestamp against the
# window. We accept ISO 8601 (with or without timezone) and 'YYYY-MM-DD
# HH:MM:SS' forms — anything we cannot parse falls back to the log file's
# date stem.
_TS_RE = re.compile(
    r"^\s*(?P<ts>\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}(?:[\.\d+]*)?(?:Z|[+\-]\d{2}:?\d{2})?)"
)


def _utc_now() -> _dt.datetime:
    return _dt.datetime.now(tz=_dt.timezone.utc)


def _parse_log_date(path: Path) -> _dt.date | None:
    name = path.name
    if not name.startswith(LOG_PREFIX) or not name.endswith(LOG_SUFFIX):
        return None
    stem = name[len(LOG_PREFIX) : -len(LOG_SUFFIX)]
    try:
        return _dt.date.fromisoformat(stem)
    except ValueError:
        return None


def _parse_line_ts(line: str, fallback_date: _dt.date) -> _dt.datetime | None:
    match = _TS_RE.match(line)
    if match:
        raw = match.group("ts").replace(" ", "T")
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            parsed = _dt.datetime.fromisoformat(raw)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=_dt.timezone.utc)
            return parsed
        except ValueError:
            pass
    # Fall back to end-of-day on the log's date so a "completed" line without
    # a parseable timestamp still produces a comparable value.
    return _dt.datetime.combine(
        fallback_date,
        _dt.time(hour=23, minute=59, second=59),
        tzinfo=_dt.timezone.utc,
    )


def _most_recent_completed(path: Path) -> _dt.datetime | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    log_date = _parse_log_date(path)
    if log_date is None:
        return None
    latest: _dt.datetime | None = None
    for line in text.splitlines():
        if not _COMPLETED_RE.search(line):
            continue
        ts = _parse_line_ts(line, log_date)
        if ts is None:
            continue
        if latest is None or ts > latest:
            latest = ts
    return latest


def _candidate_logs(log_dir: Path) -> list[Path]:
    try:
        entries = sorted(log_dir.iterdir())
    except OSError:
        return []
    return [p for p in entries if _parse_log_date(p) is not None]


def verify_restic_recent(
    max_age_hours: int = 24,
    log_dir: Path | str = DEFAULT_LOG_DIR,
) -> LibResult:
    """Confirm the most recent Restic snapshot finished within *max_age_hours*.

    The Restic repository cannot be queried directly from the ``claude``
    user; this fallback reads the per-day backup log under *log_dir* and
    looks for a "snapshot saved" / "backup completed" / "status: ok"
    signature with a timestamp inside the window.

    Returns ``LibResult(ok=True, ...)`` when the most recent completed line
    is younger than *max_age_hours*. Otherwise returns ``ok=False`` with an
    ``error_code`` of:

    * ``LOG_DIR_MISSING`` — *log_dir* does not exist.
    * ``NO_LOGS`` — no ``backup-YYYY-MM-DD.log`` files in *log_dir*.
    * ``NO_COMPLETED_LINES`` — log files exist but none contain a completion
      signature.
    * ``RESTIC_TOO_OLD`` — completion exists but is older than the window.
    """
    if max_age_hours <= 0:
        return LibResult(
            ok=False,
            summary="verify_restic_recent requires max_age_hours > 0",
            details={"error_code": "INVALID_ARGUMENT"},
        )

    log_dir_path = Path(log_dir)
    if not log_dir_path.exists():
        return LibResult(
            ok=False,
            summary=f"Restic backup log directory not found: {log_dir_path}",
            details={"error_code": "LOG_DIR_MISSING", "log_dir": str(log_dir_path)},
        )

    candidates = _candidate_logs(log_dir_path)
    if not candidates:
        return LibResult(
            ok=False,
            summary=f"No backup logs found in {log_dir_path}",
            details={"error_code": "NO_LOGS", "log_dir": str(log_dir_path)},
        )

    latest_completed: _dt.datetime | None = None
    inspected_path: Path | None = None
    # Walk most-recent first so we stop early; sorted ascending, so reverse.
    for path in reversed(candidates):
        ts = _most_recent_completed(path)
        if ts is None:
            continue
        if latest_completed is None or ts > latest_completed:
            latest_completed = ts
            inspected_path = path
            break

    if latest_completed is None:
        return LibResult(
            ok=False,
            summary=f"No completed-snapshot line found in {len(candidates)} log(s)",
            details={
                "error_code": "NO_COMPLETED_LINES",
                "log_dir": str(log_dir_path),
                "logs_scanned": [p.name for p in candidates],
            },
        )

    now = _utc_now()
    age = now - latest_completed
    age_hours = age.total_seconds() / 3600.0
    window = _dt.timedelta(hours=max_age_hours)
    if age <= window:
        return LibResult(
            ok=True,
            summary=(
                f"Restic snapshot completed {age_hours:.1f}h ago "
                f"(within {max_age_hours}h window)"
            ),
            details={
                "log_path": str(inspected_path) if inspected_path else None,
                "latest_completed_at": latest_completed.isoformat(),
                "age_hours": age_hours,
                "max_age_hours": max_age_hours,
            },
        )

    return LibResult(
        ok=False,
        summary=(
            f"Latest Restic snapshot is {age_hours:.1f}h old "
            f"(exceeds {max_age_hours}h window)"
        ),
        details={
            "error_code": "RESTIC_TOO_OLD",
            "log_path": str(inspected_path) if inspected_path else None,
            "latest_completed_at": latest_completed.isoformat(),
            "age_hours": age_hours,
            "max_age_hours": max_age_hours,
        },
    )


__all__ = ["verify_restic_recent", "DEFAULT_LOG_DIR"]


# ---------------------------------------------------------------------------
# Module-as-CLI surface for bash callers:
#   python3 -m scripts.deploy.lib.snapshot verify_restic_recent
# ---------------------------------------------------------------------------


def _cli_verify_restic_recent(*args: str) -> LibResult:
    """CLI wrapper: positional ``[max_age_hours] [log_dir]`` (both optional)."""
    kwargs: dict = {}
    if len(args) >= 1 and args[0]:
        try:
            kwargs["max_age_hours"] = int(args[0])
        except ValueError:
            return LibResult(
                ok=False,
                summary=f"verify_restic_recent: max_age_hours must be int, got {args[0]!r}",
                details={"error_code": "INVALID_ARGUMENT"},
            )
    if len(args) >= 2 and args[1]:
        kwargs["log_dir"] = args[1]
    return verify_restic_recent(**kwargs)


_CLI_FUNCS = {
    "verify_restic_recent": _cli_verify_restic_recent,
}


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    import sys as _sys

    from ._cli import run as _run

    _sys.exit(_run(_CLI_FUNCS, _sys.argv[1:], prog="scripts.deploy.lib.snapshot"))
