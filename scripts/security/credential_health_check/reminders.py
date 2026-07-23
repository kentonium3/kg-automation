"""Ramping ntfy reminder ladder for credential expiry (#852 Part 2).

As a credential's *effective boundary* — the earlier of its review-cadence
boundary and its hard ``expires_at`` (see
:func:`cadence.compute_effective_boundary`, #852 Part 1) — approaches, this
fires escalating ntfy pushes through the unified felix-alert bus (#701) at fixed
rungs (30 / 14 / 7 / 3 / 1 days before), then one push per calendar day once the
boundary is reached or crossed ("overdue").

Dedup / persistence (both locked design decisions on #852):

- Each rung fires **at most once per ``(credential, boundary)``**. Firing history
  is persisted to an append-only JSONL ledger so a rung crossed while the service
  was down is still fired on the next run and never re-fired. If several rungs are
  crossed in one cycle (e.g. the first run after a long outage), only the *most
  urgent* crossed rung is pushed and the superseded (less-urgent) rungs are marked
  consumed so they never back-fire.
- Once overdue, at most **one push per ``(credential, date)``** (calendar day).

A record is only persisted once the push is actually *delivered* (``result.ok``),
so a transient ntfy outage retries the same rung on the next daily cycle rather
than silently swallowing it. When the boundary itself moves (e.g. the credential
is rotated and ``expires_at`` jumps a year out), the new boundary keys a fresh
ladder — old rung records no longer match.

The push is DELIBERATELY not linked to the Vikunja task or GitHub issue (#852
design decision 4): it is a standalone urgency nudge; the durable, trackable work
item lives in Vikunja + GitHub via the existing cadence-alert path
(``orchestrator._process_cadence_alert``). This module never files issues/tasks.
"""
from __future__ import annotations

import fcntl
import json
import logging
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import NamedTuple, Optional

from scripts.common.alert_bus import Alert, Severity, emit

from .manifest import Credential


#: Days-before-boundary rungs. Selection (:func:`select`) is order-independent
#: (filter + ``min``), so this is written descending only for readability.
REMINDER_RUNGS: tuple[int, ...] = (30, 14, 7, 3, 1)

#: Sentinel rung value for the overdue (boundary reached/crossed) regime.
OVERDUE_RUNG = "overdue"

#: Where the firing ledger lives on office2. Runtime state — never in the
#: checkout (gitignored ``scripts/**/state/`` is a *different*, repo-relative
#: guard; the canonical runtime home is under /data, #855). Overridable via env
#: for tests / relocation, mirroring the alert-bus ledger (#706).
DEFAULT_STATE_DIR = "/data/services/openclaw/state/credential-health-check"
STATE_DIR_ENV = "CREDENTIAL_HEALTH_STATE_DIR"
RUNGS_FILENAME = "rungs.jsonl"

#: Alert source tag (shows up in the felix-alert ledger + ntfy body).
ALERT_SOURCE = "credential-health-check/expiry-reminder"


def state_dir() -> Path:
    """Resolve the ledger directory (``CREDENTIAL_HEALTH_STATE_DIR`` or default)."""
    override = os.environ.get(STATE_DIR_ENV, "").strip()
    return Path(override) if override else Path(DEFAULT_STATE_DIR)


def rungs_path() -> Path:
    return state_dir() / RUNGS_FILENAME


# --------------------------------------------------------------------------- #
# Persistence (append-only JSONL, torn-write-safe — mirrors alert_bus.ledger)  #
# --------------------------------------------------------------------------- #


class FiredState(NamedTuple):
    """The set of already-fired dedup keys loaded from the ledger."""

    #: {(credential, boundary_iso, rung_int)}
    rungs: frozenset[tuple[str, str, int]]
    #: {(credential, date_iso)}  — note: boundary-independent, per design decision 3
    overdue_days: frozenset[tuple[str, str]]

    def rung_fired(self, credential: str, boundary: date, rung: int) -> bool:
        return (credential, boundary.isoformat(), rung) in self.rungs

    def overdue_fired(self, credential: str, day: date) -> bool:
        return (credential, day.isoformat()) in self.overdue_days


def load_fired(path: Optional[Path] = None) -> FiredState:
    """Read the ledger and build the fired-key sets. Missing file → empty state.

    Malformed lines are skipped defensively (a truncated/partial JSONL line must
    never crash the daily cycle). A rung record's ``rungs_consumed`` list (all
    rungs superseded by that fire) is expanded so superseded rungs count as fired.
    """
    if path is None:
        path = rungs_path()
    rungs: set[tuple[str, str, int]] = set()
    overdue: set[tuple[str, str]] = set()
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return FiredState(frozenset(), frozenset())
    except OSError:
        # Unreadable ledger: treat as empty (fail toward re-notifying, not silent).
        return FiredState(frozenset(), frozenset())
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(rec, dict):
            continue
        cred = rec.get("credential")
        if not isinstance(cred, str) or not cred:
            continue
        kind = rec.get("kind")
        if kind == "rung":
            boundary = rec.get("boundary")
            if not isinstance(boundary, str):
                continue
            consumed = rec.get("rungs_consumed")
            if not isinstance(consumed, list):
                fired = rec.get("rung_fired")
                consumed = [fired] if isinstance(fired, int) else []
            for r in consumed:
                if isinstance(r, int) and not isinstance(r, bool):
                    rungs.add((cred, boundary, r))
        elif kind == "overdue":
            day = rec.get("date")
            if isinstance(day, str):
                overdue.add((cred, day))
    return FiredState(frozenset(rungs), frozenset(overdue))


def _append_record(record: dict, path: Optional[Path] = None) -> None:
    """Append one JSON record under an exclusive lock (torn-write-safe)."""
    if path is None:
        path = rungs_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, separators=(",", ":")) + "\n"
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        os.write(fd, line.encode("utf-8"))
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


# --------------------------------------------------------------------------- #
# Pure decision + rendering                                                    #
# --------------------------------------------------------------------------- #


class Reminder(NamedTuple):
    """The single reminder to fire this cycle (or None from :func:`select`)."""

    rung: object  # int rung, or OVERDUE_RUNG
    days_until: int
    boundary: date
    #: For a rung fire: every crossed-and-unfired rung this fire supersedes.
    rungs_consumed: tuple[int, ...]


def select(
    credential_name: str,
    boundary: date,
    today: date,
    fired: FiredState,
) -> Optional[Reminder]:
    """Decide which single reminder (if any) to fire for *credential_name*.

    Pure function — no I/O. Returns None when nothing is due this cycle.

    * ``days_until <= 0`` (boundary reached/crossed) → overdue regime: fire once
      per calendar day (dedup ``(credential, date)``).
    * otherwise → fire the most-urgent crossed-and-unfired rung, consuming (and
      thus silencing) every less-urgent rung also crossed this cycle.
    """
    days_until = (boundary - today).days
    if days_until <= 0:
        if fired.overdue_fired(credential_name, today):
            return None
        return Reminder(OVERDUE_RUNG, days_until, boundary, ())

    crossed = [r for r in REMINDER_RUNGS if days_until <= r]
    unfired = [r for r in crossed if not fired.rung_fired(credential_name, boundary, r)]
    if not unfired:
        return None
    # Most urgent crossed rung = smallest number of days. Consume all crossed
    # unfired rungs so the less-urgent ones never back-fire on a later cycle.
    target = min(unfired)
    return Reminder(target, days_until, boundary, tuple(sorted(unfired, reverse=True)))


def _severity_for(days_until: int) -> Severity:
    """Map real proximity to the boundary onto ntfy priority.

    Keyed off ``days_until`` (true remaining time) rather than the rung so a
    *late* first observation after an outage — e.g. fires rung 3 when actually
    2 days out — still gets the CRITICAL priority its proximity warrants, not
    the rung's nominal (ERROR) level.
    """
    if days_until <= 1:  # boundary day, overdue, or the last day before
        return Severity.CRITICAL
    if days_until <= 7:
        return Severity.ERROR
    return Severity.WARN  # 8..30 days out


def build_alert(credential: Credential, reminder: Reminder) -> Alert:
    """Render the felix-alert for *reminder*. No Vikunja/GitHub links (decision 4)."""
    boundary_iso = reminder.boundary.isoformat()
    if reminder.rung == OVERDUE_RUNG:
        overdue_by = abs(reminder.days_until)
        title = f"Credential rotation OVERDUE: {credential.name}"
        window = (
            f"Boundary {boundary_iso} reached "
            + ("today" if overdue_by == 0 else f"{overdue_by} day(s) ago")
            + "."
        )
    else:
        title = f"Credential rotation due in {reminder.days_until}d: {credential.name}"
        window = f"Boundary {boundary_iso} — {reminder.days_until} day(s) out."
    description = (
        f"Credential '{credential.name}' is due for rotation/review.\n"
        f"{window}\n"
        f"Stored at: {credential.storage}"
    )
    action = f"Rotate '{credential.name}' before {boundary_iso}."
    details = {
        "credential": credential.name,
        "boundary": boundary_iso,
        "days_until": str(reminder.days_until),
        "rung": str(reminder.rung),
        "storage": credential.storage,
    }
    return Alert(
        source=ALERT_SOURCE,
        severity=_severity_for(reminder.days_until),
        title=title,
        description=description,
        action=action,
        details=details,
    )


# --------------------------------------------------------------------------- #
# Orchestration                                                                #
# --------------------------------------------------------------------------- #


def _build_record(
    credential: Credential, reminder: Reminder, severity: Severity, today: date
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    base = {
        "credential": credential.name,
        "boundary": reminder.boundary.isoformat(),
        "days_until": reminder.days_until,
        "severity": severity.value,
        "emitted": True,
        "fired_at": now,
    }
    if reminder.rung == OVERDUE_RUNG:
        # Overdue dedup key is (credential, date) — boundary-independent.
        base.update({"kind": "overdue", "date": today.isoformat()})
    else:
        base.update(
            {
                "kind": "rung",
                "rung_fired": reminder.rung,
                "rungs_consumed": list(reminder.rungs_consumed),
            }
        )
    return base


def process_expiry_reminder(
    credential: Credential,
    boundary: date,
    today: date,
    *,
    dry_run: bool,
    logger: Optional[logging.Logger] = None,
) -> bool:
    """Evaluate + (maybe) fire the reminder ladder for one credential.

    Returns True iff a push was delivered (and recorded). Never raises — the
    alert bus is fail-safe and any ledger error is swallowed so the daily cycle
    is never crashed by a reminder.
    """
    try:
        fired = load_fired()
        reminder = select(credential.name, boundary, today, fired)
        if reminder is None:
            return False

        severity = _severity_for(reminder.days_until)
        if dry_run:
            _log(
                logger,
                logging.INFO,
                "expiry_reminder_would_fire",
                name=credential.name,
                rung=reminder.rung,
                days_until=reminder.days_until,
                boundary=boundary.isoformat(),
                severity=severity.value,
            )
            return False

        result = emit(build_alert(credential, reminder))
        if not result.ok:
            # Not delivered → do NOT persist, so the next daily cycle retries this
            # rung rather than silently swallowing it.
            _log(
                logger,
                logging.WARNING,
                "expiry_reminder_delivery_failed",
                name=credential.name,
                rung=reminder.rung,
                days_until=reminder.days_until,
                reason=result.reason,
                topic_configured=result.topic_configured,
            )
            return False

        # Persist only after a confirmed delivery. If the ledger write itself
        # fails (disk/permission) this raises, is swallowed below, and the rung
        # re-fires next cycle → at worst one duplicate ntfy. That is the
        # deliberate bias: re-notify rather than silently drop.
        _append_record(_build_record(credential, reminder, severity, today))
        _log(
            logger,
            logging.INFO,
            "expiry_reminder_fired",
            name=credential.name,
            rung=reminder.rung,
            rungs_consumed=list(reminder.rungs_consumed),
            days_until=reminder.days_until,
            boundary=boundary.isoformat(),
            severity=severity.value,
        )
        return True
    except Exception as e:  # noqa: BLE001 — a reminder must never crash the cycle
        _log(
            logger,
            logging.ERROR,
            "expiry_reminder_error",
            name=credential.name,
            error=str(e),
        )
        return False


def _log(logger: Optional[logging.Logger], level: int, msg: str, /, **kwargs) -> None:
    if logger is None:
        return
    if kwargs:
        kv = " ".join(f"{k}={v}" for k, v in kwargs.items())
        logger.log(level, "%s %s", msg, kv)
    else:
        logger.log(level, msg)
