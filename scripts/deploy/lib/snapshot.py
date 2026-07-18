"""Restic backup-recency verification.

The recency half of the Tier-2 destructive-deploy gate. Two signals, in
priority order:

1. **Authoritative state file** (``/data/services/backup/state/last-backup.json``,
   written by the Restic driver on every run — #511). It carries
   ``restic_exit_code`` (genuine success/failure of the backup step) and
   ``snapshot_timestamp_utc`` / ``script_finished_at_utc`` (the exact instant).
   This is preferred because it gives real success verification and an exact
   UTC instant with no wall-clock/timezone guessing (#767).
2. **Daily backup log** (``/data/services/backup/logs/backup-YYYY-MM-DD.log``) —
   kept as defence-in-depth. Used only when the state file is absent or
   malformed. A "completed" line within the window is treated as evidence of a
   recent snapshot. This path infers success from a text marker and the instant
   from a wall-clock stamp, so it is strictly weaker than the state file.

Historically only the log path existed; the ``claude`` user on office2 cannot
query the Restic repository directly (see the Felix charter "Deployment
Constraints" section), which is why the driver-written state file — readable by
``claude`` — is the right authoritative source rather than a live repo query.

Success semantics: a restic exit code of ``0`` (clean) or ``3`` (snapshot
created, some source files unreadable — still a restorable snapshot) counts as
a successful backup. This matches the system-wide convention documented in
``docs/design/architecture/data/service-inventory.json`` (#327),
``docs/runbooks/restic-backup-ops.md``, and the governance pre-flight checklist,
all of which treat ``restic_exit_code ∉ {0, 3}`` as an explicit failure.

Recency anchor: on the state path the freshness instant is
``snapshot_timestamp_utc`` **only** — the authoritative timestamp derived from
``restic snapshots --latest 1 --json`` after the run. Per the same contract,
``script_finished_at_utc`` is a *separate cron-finished witness*, not a snapshot
instant; a state file that records a good exit code but a null/absent/unparseable
``snapshot_timestamp_utc`` (the "backup ran but the snapshot query failed"
signal) cannot authoritatively confirm a snapshot, so it falls back to the log
path rather than being green-lit off the finish-witness. State timestamps must
carry an explicit UTC marker (``Z`` or an offset); a naive timestamp is treated
as malformed and falls back too (no timezone guessing on the authoritative
path). A ``snapshot_timestamp_utc`` in the future beyond a small clock-skew
tolerance is an explicit anomaly and fails the gate closed rather than reading
as "very fresh".

This module is a defence-in-depth check used by the applier for Tier 2
deploys (per ``data-model.md`` apply orchestration); Tier 1 callers may also
opt in.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
import subprocess
from collections.abc import Sequence
from pathlib import Path

from . import LibResult

DEFAULT_LOG_DIR = Path("/data/services/backup/logs")
DEFAULT_STATE_PATH = Path("/data/services/backup/state/last-backup.json")
LOG_PREFIX = "backup-"
LOG_SUFFIX = ".log"

# Sanctioned Restic backup trigger (#666 / #784). The ``claude`` user on office2
# holds a single-command NOPASSWD sudoers grant for exactly this path
# (``claude ALL=(root) NOPASSWD: /data/services/backup/scripts/backup.sh``), so
# felix-deployer — which runs as ``claude`` — can self-trigger a backup before a
# Tier-2 apply without any interactive prompt. Kept as an argv tuple (shell=False,
# no injection surface) and overridable for tests.
DEFAULT_BACKUP_TRIGGER_CMD: tuple[str, ...] = (
    "sudo",
    "/data/services/backup/scripts/backup.sh",
)
# backup.sh does a full Restic run; give it a generous ceiling but never hang the
# deployer tick forever. On timeout the apply is blocked (fail-closed).
_DEFAULT_BACKUP_TIMEOUT_SEC = 1800
_BACKUP_STDERR_EXCERPT_MAX = 2000

# Restic exit codes that mean "a snapshot was successfully created":
#   0 — clean run.
#   3 — snapshot created but some source files could not be read (still a
#       valid, restorable snapshot).
# Any other code is an explicit failure. Canonical convention: see the module
# docstring (service-inventory.json #327, restic-backup-ops.md, pre-flight
# checklist). Keeping this as a named set keeps the gate consistent with every
# other backup-health consumer in Felix.
_RESTIC_OK_EXIT_CODES = frozenset({0, 3})

# Authoritative recency anchor on the state path (#767). ``snapshot_timestamp_utc``
# is the only field the backup-health contract treats as the snapshot instant;
# ``script_finished_at_utc`` is a separate cron-finished witness (kept in details
# for diagnostics, never used as the freshness anchor).
_STATE_INSTANT_FIELD = "snapshot_timestamp_utc"

# A state-file snapshot timestamp this far (or more) in the future is an
# anomaly (corruption / clock skew), not a "very fresh" backup, and must fail
# the gate closed. The tolerance absorbs benign sub-second/second same-host UTC
# skew so a just-written snapshot is never spuriously rejected.
_FUTURE_SKEW_TOLERANCE = _dt.timedelta(minutes=5)

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
# The live Restic driver writes completion lines with a bracketed TIME-ONLY
# stamp and no date, e.g. ``[04:00:08] Backup completed successfully`` (the log's
# date lives in the ``backup-YYYY-MM-DD.log`` filename + the ``=== Backup: … ===``
# header). Before #665, ``_TS_RE`` did not match this form, so every real line
# fell through to the end-of-day fallback and the computed age was taken from
# 23:59:59 of the log date — yielding nonsensical / negative "ago" values.
_BRACKET_TIME_RE = re.compile(r"^\s*\[(?P<h>\d{2}):(?P<m>\d{2}):(?P<s>\d{2})\]")


def _utc_now() -> _dt.datetime:
    return _dt.datetime.now(tz=_dt.timezone.utc)


def _parse_iso_utc(raw: str, *, require_tz: bool = False) -> _dt.datetime | None:
    """Parse an ISO-8601 instant. Returns ``None`` when unparseable.

    When *require_tz* is False, a naive timestamp is assumed to be UTC (the
    lenient log-path policy — the driver's wall-clock is UTC on office2). When
    *require_tz* is True (the authoritative state path), a timestamp without an
    explicit ``Z`` / offset is rejected — no timezone guessing (#767).
    """
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = _dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        if require_tz:
            return None
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    return parsed


def _pick_state_instant(data: dict) -> _dt.datetime | None:
    """Return the authoritative snapshot instant from the state file.

    Uses ``snapshot_timestamp_utc`` only, and requires an explicit UTC marker.
    Returns ``None`` when the field is absent, null, non-string, naive, or
    otherwise unparseable — the caller then falls back to the log path.
    """
    value = data.get(_STATE_INSTANT_FIELD)
    if not isinstance(value, str) or not value:
        return None
    return _parse_iso_utc(value, require_tz=True)


def _age_verdict(
    instant: _dt.datetime,
    now: _dt.datetime,
    max_age_hours: int,
    *,
    source: str,
    extra: dict,
) -> LibResult:
    """Build the ok / RESTIC_TOO_OLD LibResult from an instant + window."""
    age = now - instant
    age_hours = age.total_seconds() / 3600.0
    window = _dt.timedelta(hours=max_age_hours)
    common = {
        "source": source,
        "latest_completed_at": instant.isoformat(),
        "age_hours": age_hours,
        "max_age_hours": max_age_hours,
        **extra,
    }
    if age <= window:
        return LibResult(
            ok=True,
            summary=(
                f"Restic snapshot completed {age_hours:.1f}h ago "
                f"(within {max_age_hours}h window; source={source})"
            ),
            details=common,
        )
    return LibResult(
        ok=False,
        summary=(
            f"Latest Restic snapshot is {age_hours:.1f}h old "
            f"(exceeds {max_age_hours}h window; source={source})"
        ),
        details={"error_code": "RESTIC_TOO_OLD", **common},
    )


def _read_state_verdict(
    state_path: Path,
    max_age_hours: int,
    now: _dt.datetime,
) -> LibResult | None:
    """Verdict from the authoritative state file, or ``None`` to fall back.

    Returns:
        * A ``LibResult`` (ok or explicit failure) when the state file is
          present, well-formed, and carries a usable ``restic_exit_code`` +
          instant.
        * ``None`` when the file is absent, unreadable, malformed JSON, missing
          an exit code, or missing every instant field — in which case the
          caller falls back to the log-parsing path (defence-in-depth).

    A state file that records an explicit restic *failure*
    (``restic_exit_code ∉ {0, 3}``) returns ``ok=False`` and does **not** fall
    through to the log path: an authoritative failure must never be masked by an
    older "completed" log line (that would re-open the fail-open hole #767
    closes).
    """
    try:
        raw = state_path.read_text(encoding="utf-8")
    except OSError:
        return None  # absent / unreadable → fall back to logs
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None  # malformed JSON → fall back to logs
    if not isinstance(data, dict):
        return None

    exit_code = data.get("restic_exit_code")
    if exit_code is None:
        return None  # no success signal recorded → fall back to logs
    # bool is an int subclass; reject it so True/False can't masquerade as 1/0.
    if isinstance(exit_code, bool) or not isinstance(exit_code, int):
        return None  # malformed exit code → fall back to logs
    if exit_code not in _RESTIC_OK_EXIT_CODES:
        return LibResult(
            ok=False,
            summary=(
                f"Restic backup reported failure (restic_exit_code={exit_code}); "
                "refusing to treat as a recent successful snapshot"
            ),
            details={
                "error_code": "RESTIC_FAILED",
                "source": "state",
                "state_path": str(state_path),
                "restic_exit_code": exit_code,
            },
        )

    instant = _pick_state_instant(data)
    if instant is None:
        # exit ok but no authoritative snapshot instant (null/absent/naive/
        # unparseable snapshot_timestamp_utc) → cannot confirm a snapshot from
        # state; fall back to the log path (defence in depth).
        return None

    # script_finished_at_utc is a diagnostic witness only, never the anchor.
    finished_witness = data.get("script_finished_at_utc")
    extra = {
        "state_path": str(state_path),
        "restic_exit_code": exit_code,
        "instant_field": _STATE_INSTANT_FIELD,
        "script_finished_at_utc": finished_witness,
    }

    # An authoritative snapshot timestamp in the future (beyond benign skew) is
    # an anomaly, not freshness — fail the gate closed rather than green-lighting
    # a destructive deploy off an impossible instant.
    if instant > now + _FUTURE_SKEW_TOLERANCE:
        return LibResult(
            ok=False,
            summary=(
                "Restic state snapshot_timestamp_utc is in the future "
                f"({instant.isoformat()} > now {now.isoformat()}); "
                "refusing to treat as a recent snapshot"
            ),
            details={
                "error_code": "RESTIC_TIMESTAMP_IN_FUTURE",
                "source": "state",
                "latest_completed_at": instant.isoformat(),
                **extra,
            },
        )

    return _age_verdict(instant, now, max_age_hours, source="state", extra=extra)


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
    # Bracketed time-only stamp (the live driver format, #665). Combine the
    # ``[HH:MM:SS]`` with the log's date to recover the true completion instant.
    # office2's host TZ is Etc/UTC, so the driver's wall-clock times are UTC.
    bracket = _BRACKET_TIME_RE.match(line)
    if bracket:
        try:
            t = _dt.time(
                int(bracket["h"]), int(bracket["m"]), int(bracket["s"])
            )
        except ValueError:
            pass  # e.g. "[25:00:00]" — fall through to the last-resort fallback
        else:
            return _dt.datetime.combine(fallback_date, t, tzinfo=_dt.timezone.utc)
    # Last-resort fallback: end-of-day on the log's date so a "completed" line
    # with no parseable timestamp at all still produces a comparable value.
    # Rarely hit now that the real bracketed-time format is parsed.
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


def _verify_via_logs(
    max_age_hours: int,
    log_dir: Path,
    now: _dt.datetime,
) -> LibResult:
    """Defence-in-depth fallback: infer recency from the daily backup log."""
    if not log_dir.exists():
        return LibResult(
            ok=False,
            summary=f"Restic backup log directory not found: {log_dir}",
            details={"error_code": "LOG_DIR_MISSING", "log_dir": str(log_dir)},
        )

    candidates = _candidate_logs(log_dir)
    if not candidates:
        return LibResult(
            ok=False,
            summary=f"No backup logs found in {log_dir}",
            details={"error_code": "NO_LOGS", "log_dir": str(log_dir)},
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
                "log_dir": str(log_dir),
                "logs_scanned": [p.name for p in candidates],
            },
        )

    return _age_verdict(
        latest_completed,
        now,
        max_age_hours,
        source="log",
        extra={"log_path": str(inspected_path) if inspected_path else None},
    )


def verify_restic_recent(
    max_age_hours: int = 24,
    log_dir: Path | str = DEFAULT_LOG_DIR,
    state_path: Path | str = DEFAULT_STATE_PATH,
) -> LibResult:
    """Confirm the most recent Restic snapshot finished within *max_age_hours*.

    Prefers the authoritative driver-written state file *state_path*
    (``restic_exit_code`` for genuine success, ``snapshot_timestamp_utc`` /
    ``script_finished_at_utc`` for the exact instant). Falls back to parsing the
    per-day backup log under *log_dir* only when the state file is absent or
    malformed.

    Returns ``LibResult(ok=True, ...)`` when a successful snapshot is younger
    than *max_age_hours*. ``details["source"]`` is ``"state"`` or ``"log"``.
    Otherwise returns ``ok=False`` with an ``error_code`` of:

    * ``INVALID_ARGUMENT`` — *max_age_hours* is not positive.
    * ``RESTIC_FAILED`` — the state file records a restic failure
      (``restic_exit_code ∉ {0, 3}``).
    * ``RESTIC_TIMESTAMP_IN_FUTURE`` — the state file's
      ``snapshot_timestamp_utc`` is in the future beyond clock-skew tolerance.
    * ``RESTIC_TOO_OLD`` — a success exists but is older than the window.
    * ``LOG_DIR_MISSING`` — (log fallback) *log_dir* does not exist.
    * ``NO_LOGS`` — (log fallback) no ``backup-YYYY-MM-DD.log`` files.
    * ``NO_COMPLETED_LINES`` — (log fallback) logs exist but none contain a
      completion signature.
    """
    if max_age_hours <= 0:
        return LibResult(
            ok=False,
            summary="verify_restic_recent requires max_age_hours > 0",
            details={"error_code": "INVALID_ARGUMENT"},
        )

    now = _utc_now()

    state_verdict = _read_state_verdict(Path(state_path), max_age_hours, now)
    if state_verdict is not None:
        return state_verdict

    return _verify_via_logs(max_age_hours, Path(log_dir), now)


# ---------------------------------------------------------------------------
# Backup trigger (#784) — verify → trigger-if-stale → re-verify, so the
# felix-deployer Tier-2 apply path can guarantee a recent successful snapshot
# without depending on an agent being in the loop.
# ---------------------------------------------------------------------------


def _invoke_backup(backup_cmd: Sequence[str], timeout_sec: int) -> LibResult:
    """Run the sanctioned backup trigger and return a LibResult.

    ``shell=False`` (fixed argv, no injection surface). Any spawn failure,
    non-zero exit, or timeout is a failure — the caller must then NOT apply.
    """
    argv = list(backup_cmd)
    if not argv:
        return LibResult(
            ok=False,
            summary="backup trigger command is empty",
            details={"error_code": "BACKUP_TRIGGER_SPAWN_FAILED", "backup_cmd": argv},
        )
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            argv,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired:
        return LibResult(
            ok=False,
            summary=f"backup trigger timed out after {timeout_sec}s",
            details={
                "error_code": "BACKUP_TRIGGER_TIMEOUT",
                "timeout_sec": timeout_sec,
                "backup_cmd": argv,
            },
        )
    except OSError as exc:  # FileNotFoundError, permission, etc.
        return LibResult(
            ok=False,
            summary=f"backup trigger could not spawn {argv!r}: {exc}",
            details={
                "error_code": "BACKUP_TRIGGER_SPAWN_FAILED",
                "backup_cmd": argv,
                "error": str(exc),
            },
        )
    if proc.returncode != 0:
        stderr = proc.stderr or ""
        return LibResult(
            ok=False,
            summary=f"backup trigger exited {proc.returncode}",
            details={
                "error_code": "BACKUP_TRIGGER_FAILED",
                "returncode": proc.returncode,
                "backup_cmd": argv,
                "stderr_excerpt": stderr[:_BACKUP_STDERR_EXCERPT_MAX],
            },
        )
    return LibResult(
        ok=True,
        summary="backup triggered successfully",
        details={"returncode": 0, "backup_cmd": argv},
    )


def ensure_recent_backup(
    max_age_hours: int = 24,
    *,
    log_dir: Path | str = DEFAULT_LOG_DIR,
    state_path: Path | str = DEFAULT_STATE_PATH,
    backup_cmd: Sequence[str] = DEFAULT_BACKUP_TRIGGER_CMD,
    timeout_sec: int = _DEFAULT_BACKUP_TIMEOUT_SEC,
) -> LibResult:
    """Guarantee a recent successful Restic snapshot, triggering one if stale.

    The Tier-2 change-control protocol requires a successful backup within
    *max_age_hours* before a destructive deploy. This is the automated form of
    the #666 agent flow:

    1. :func:`verify_restic_recent` — if a fresh successful snapshot already
       exists, return ``ok=True`` with ``details['triggered'] = False`` and do
       **not** trigger a backup.
    2. Otherwise (stale / failed / unconfirmed) run *backup_cmd*, wait for it to
       finish, then re-verify.
    3. Return the re-verify verdict with ``details['triggered'] = True``. If the
       trigger process fails (spawn / non-zero / timeout) or the re-verify is
       still not fresh, return ``ok=False`` — the caller MUST NOT apply (the
       felix-deployer failure path then emits one ntfy alert and leaves the
       manifest queued).

    Idempotent by construction: a fresh backup short-circuits before any side
    effect, so repeated calls within the window never re-trigger.
    """
    if max_age_hours <= 0:
        return LibResult(
            ok=False,
            summary="ensure_recent_backup requires max_age_hours > 0",
            details={"error_code": "INVALID_ARGUMENT"},
        )

    pre = verify_restic_recent(max_age_hours, log_dir=log_dir, state_path=state_path)
    if pre.ok:
        return LibResult(
            ok=True,
            summary=f"{pre.summary}; no backup trigger needed",
            details={**pre.details, "triggered": False},
        )

    pre_error = pre.details.get("error_code")
    trigger = _invoke_backup(backup_cmd, timeout_sec)
    if not trigger.ok:
        return LibResult(
            ok=False,
            summary=f"backup trigger failed; not applying ({trigger.summary})",
            details={**trigger.details, "triggered": True, "pre_trigger_error": pre_error},
        )

    post = verify_restic_recent(max_age_hours, log_dir=log_dir, state_path=state_path)
    if post.ok:
        return LibResult(
            ok=True,
            summary=f"backup triggered and re-verified fresh: {post.summary}",
            details={**post.details, "triggered": True},
        )
    return LibResult(
        ok=False,
        summary=(
            "backup triggered but re-verify is still not fresh; not applying "
            f"({post.summary})"
        ),
        details={
            **post.details,
            "triggered": True,
            "reverify_failed": True,
            "pre_trigger_error": pre_error,
        },
    )


__all__ = [
    "verify_restic_recent",
    "ensure_recent_backup",
    "DEFAULT_LOG_DIR",
    "DEFAULT_STATE_PATH",
    "DEFAULT_BACKUP_TRIGGER_CMD",
]


# ---------------------------------------------------------------------------
# Module-as-CLI surface for bash callers:
#   python3 -m scripts.deploy.lib.snapshot verify_restic_recent
# ---------------------------------------------------------------------------


def _cli_verify_restic_recent(*args: str) -> LibResult:
    """CLI wrapper: positional ``[max_age_hours] [log_dir] [state_path]`` (all optional)."""
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
    if len(args) >= 3 and args[2]:
        kwargs["state_path"] = args[2]
    return verify_restic_recent(**kwargs)


def _cli_ensure_recent_backup(*args: str) -> LibResult:
    """CLI wrapper: positional ``[max_age_hours] [log_dir] [state_path]``.

    Uses the sanctioned default backup trigger; intended for manual ops and the
    deployer's Python call path (which invokes :func:`ensure_recent_backup`
    directly). Triggering a real backup is a side effect — invoke deliberately.
    """
    kwargs: dict = {}
    if len(args) >= 1 and args[0]:
        try:
            kwargs["max_age_hours"] = int(args[0])
        except ValueError:
            return LibResult(
                ok=False,
                summary=f"ensure_recent_backup: max_age_hours must be int, got {args[0]!r}",
                details={"error_code": "INVALID_ARGUMENT"},
            )
    if len(args) >= 2 and args[1]:
        kwargs["log_dir"] = args[1]
    if len(args) >= 3 and args[2]:
        kwargs["state_path"] = args[2]
    return ensure_recent_backup(**kwargs)


_CLI_FUNCS = {
    "verify_restic_recent": _cli_verify_restic_recent,
    "ensure_recent_backup": _cli_ensure_recent_backup,
}


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    import sys as _sys

    from ._cli import run as _run

    _sys.exit(_run(_CLI_FUNCS, _sys.argv[1:], prog="scripts.deploy.lib.snapshot"))
