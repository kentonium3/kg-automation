"""Durable local ledger for the felix-alert bus (#706).

Every :func:`~scripts.common.alert_bus.emit` call appends one record — the
:class:`~scripts.common.alert_bus.model.Alert` (redacted to match what is sent)
plus the :class:`~scripts.common.alert_bus.model.AlertResult` delivery outcome —
to an append-only, date-partitioned JSONL ledger on office2. This gives a
queryable fault history that survives ntfy being down and captures delivery
failures too (a failed POST is still a recorded fault).

Contract:

- **Best-effort + fail-safe.** :func:`record_alert` catches every error and
  returns ``False`` on failure — a ledger problem must NEVER break ``emit()``
  (same best-effort discipline as the ntfy POST, NFR-001/FR-2).
- **Redaction-consistent.** The description and detail values are redacted with
  the exact same helper the renderer uses, so the ledger never holds secrets the
  alert itself would not (NFR-2). ``action`` is authored operator guidance and,
  like the rendered body, is stored as-is.
- **Atomic append.** Writes hold ``fcntl.LOCK_EX`` (mirrors
  ``scripts/common/state_log.py``) so concurrent emitters cannot tear a record.
- **Bounded.** Files are named ``<YYYY-MM-DD>.jsonl``; each append opportunistically
  prunes files older than :data:`RETENTION_DAYS`.
"""

from __future__ import annotations

import fcntl
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .model import Alert, AlertResult
from .render import DESCRIPTION_MAX, DETAIL_VALUE_MAX, _redact_and_truncate

# Default ledger location on office2. Overridable via env (tests point it at a
# tmpdir; a different host can relocate it).
DEFAULT_LEDGER_DIR = "/data/services/alert-bus/ledger"
LEDGER_DIR_ENV = "FELIX_ALERT_LEDGER_DIR"

# Keep this many days of ledger files; older date-partitions are pruned.
RETENTION_DAYS = 30


def ledger_dir() -> Path:
    """Resolve the ledger directory (``FELIX_ALERT_LEDGER_DIR`` or the default)."""
    override = os.environ.get(LEDGER_DIR_ENV, "").strip()
    return Path(override) if override else Path(DEFAULT_LEDGER_DIR)


def _ledger_path(base: Path, day_utc: str) -> Path:
    return base / f"{day_utc}.jsonl"


def build_record(alert: Alert, result: AlertResult) -> dict:
    """Build the redacted, JSON-serializable ledger record for *alert*/*result*."""
    ts = alert.timestamp.astimezone(timezone.utc)
    return {
        "ts": ts.isoformat(),
        "source": alert.source,
        "severity": alert.severity.value,
        "title": alert.title,
        # Redacted to match what the renderer sends (NFR-2). description can carry
        # a migrated error_summary; details can carry stderr. ``str()`` mirrors
        # the renderer (render.py), so the ledger accepts exactly what the
        # renderer accepts — a non-str detail (e.g. an int returncode) is
        # stringified, not dropped by a TypeError in the redactor.
        "description": _redact_and_truncate(str(alert.description), DESCRIPTION_MAX),
        "action": alert.action,
        "details": {
            key: _redact_and_truncate(str(value), DETAIL_VALUE_MAX)
            for key, value in alert.details.items()
        },
        "delivery": {
            "ok": result.ok,
            "reason": result.reason,
            "topic_configured": result.topic_configured,
        },
    }


def _append_line(path: Path, line: str) -> None:
    """Append *line* to *path* under an exclusive lock (torn-write-safe)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        os.write(fd, line.encode("utf-8"))
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _prune(base: Path, retention_days: int) -> None:
    """Delete date-partition files older than *retention_days* (best-effort).

    Only triggers a deletion for **old-timestamped** alerts (an alert dated >30d
    ago writes an old-dated file that is then pruned). In the rare case two
    emitters concurrently write such an old alert, one may unlink the file the
    other just wrote; the `unlink` is `OSError`-guarded so it never raises. Real
    alerts carry a current timestamp and are never pruned on write.
    """
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=retention_days)
    for path in base.glob("*.jsonl"):
        try:
            day = datetime.strptime(path.stem, "%Y-%m-%d").date()
        except ValueError:
            continue  # not a date-partition file; leave it alone
        if day < cutoff:
            try:
                path.unlink()
            except OSError:
                pass  # best-effort


def record_alert(alert: Alert, result: AlertResult) -> bool:
    """Append one ledger record for *alert*/*result*; never raises.

    Returns ``True`` iff the record was written. On any failure (unwritable
    ledger dir, serialization error, …) returns ``False`` without raising, so the
    bus stays fail-safe.
    """
    try:
        base = ledger_dir()
        day_utc = alert.timestamp.astimezone(timezone.utc).strftime("%Y-%m-%d")
        line = json.dumps(build_record(alert, result), separators=(",", ":")) + "\n"
        _append_line(_ledger_path(base, day_utc), line)
    except Exception:  # noqa: BLE001 — fail-safe: the ledger must never break emit()
        return False
    # Pruning is a separate best-effort step; its failure never fails the write.
    try:
        _prune(base, RETENTION_DAYS)
    except Exception:  # noqa: BLE001
        pass
    return True


__all__ = [
    "record_alert",
    "build_record",
    "ledger_dir",
    "DEFAULT_LEDGER_DIR",
    "LEDGER_DIR_ENV",
    "RETENTION_DAYS",
]
