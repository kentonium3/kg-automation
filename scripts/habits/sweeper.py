#!/usr/bin/env python3
"""48-hour auto-skip sweeper for the habit check-in flow (mission #408 / WP-02).

This module is the daily 7:30 AM ET sweep that closes Kent's response window
on yesterday's (and older, up to 48hr) morning check-ins. For each habit
instance that's been unresolved for >48hr since its check-in delivery, the
sweeper:

  1. Appends an ``auto_skipped`` event to ``habits-history.jsonl`` (per
     ``contracts/history-event-auto-skipped.contract.md``).
  2. For **day-specific** habits only: advances Vikunja ``due_date`` to the
     next occurrence of one of the habit's designated weekdays at end-of-
     day Eastern Time. Daily habits inherit their next occurrence from
     Vikunja's native ``repeat_after`` cadence — no PUT needed.
  3. Writes a structured per-tick artifact at
     ``/data/services/openclaw/state/habits/sweeper-tick-<YYYY-MM-DD>.json``
     per ``contracts/sweeper-tick.contract.md``.
  4. Appends a JSONL ledger line at
     ``/data/services/openclaw/state/habits/sweeper-ledger.jsonl``.

Architectural pattern: stateless Python oneshot fired by a systemd user
timer (``felix-habit-sweeper.timer``). Mirrors the post-#343 felix-doc-
auditor shape (tick artifact + JSONL ledger + ``SUMMARY:`` line on stdout
+ exit-status taxonomy ``success`` / ``partial`` / ``failure``).

Determinism (Directive 6): zero LLM calls. All decisions are pure data
operations against the schedule YAML, ``morning-checkin-<date>.json``
artifacts, and ``habits-history.jsonl``. Vikunja PUTs are deterministic
HTTP calls with a precomputed payload.

Idempotency (FR-005): re-running the sweeper for the same
``(task_id, original_checkin_date_et)`` MUST be a no-op. Enforced by
scanning history for an existing ``auto_skipped`` event matching the pair
before appending a new one. Tick artifacts overwrite per-date so running
the sweeper twice the same day surfaces the latest run only.

Issue #112 regression-prevention: any Vikunja due_date the sweeper PUTs
MUST end with an explicit ET offset (``-04:00`` EDT or ``-05:00`` EST),
NOT ``Z``. The sweeper reuses ``set_due_dates.compute_next_eod_et_for_weekdays``
which is unit-tested to produce explicit-offset strings, and additionally
validates the result against ``set_due_dates.ISO_EOD_PATTERN`` before any
PUT call.

CLI surface::

    python3 scripts/habits/sweeper.py [--dry-run] \\
        [--state-dir /data/services/openclaw/state/habits] \\
        [--history-path /data/services/openclaw/state/habits-history.jsonl] \\
        [--schedule-path scripts/habits/migrations/phase3-schedule.yaml] \\
        [--vikunja-token-path /data/services/openclaw/secrets/vikunja-api] \\
        [--vikunja-base-url https://office2.tail0f5f56.ts.net/api/v1] \\
        [--now-utc 2026-06-02T11:30:00Z]

Exit codes::

    0 -- success (all habits processed cleanly OR none were eligible)
    1 -- partial (some habits errored but the tick ran to completion)
    2 -- failure (cycle-aborting error before the tick could complete)
    3 -- usage / validation error

Contracts:
  * ``kitty-specs/habit-day-specific-scheduling-01KT48Y6/contracts/sweeper-tick.contract.md``
  * ``kitty-specs/habit-day-specific-scheduling-01KT48Y6/contracts/history-event-auto-skipped.contract.md``
"""
from __future__ import annotations

import argparse
import dataclasses
import fcntl
import json
import os
import re
import secrets
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from scripts.common.vikunja_config import get_vikunja_base_url

# --------------------------------------------------------------------------
# Cross-WP imports
#
# WP-01 deliverable: ``schedule_loader`` is the single parse surface for the
# runtime schedule YAML. WP-01 deliverable: ``set_due_dates`` provides the
# day-of-week math + the #112-guarded due_date string format. Both imports
# use the WP-01 try/except fallback pattern so direct-script invocation
# (``python3 scripts/habits/sweeper.py``) works alongside the module form
# (``python3 -m scripts.habits.sweeper``). Precedent: ``set_due_dates.py``
# lines 57-76 (which itself cites ``summarize.py`` lines 36-38).
# --------------------------------------------------------------------------
try:
    from scripts.habits.schedule_loader import (
        ScheduleConfigError,
        ScheduleEntry,
        WEEKDAY_NAMES,
        is_day_specific,
        load_schedule,
    )
    from scripts.habits.set_due_dates import (
        ISO_EOD_PATTERN,
        compute_next_eod_et_for_weekdays,
        validate_iso_eod_et,
    )
except ImportError:  # pragma: no cover -- exercised only on direct-script form
    # Fallback for ``python3 scripts/habits/sweeper.py``. The absolute-package
    # import above resolves under ``python3 -m scripts.habits.sweeper``; both
    # invocation forms are documented + used in production.
    from schedule_loader import (  # type: ignore[no-redef]
        ScheduleConfigError,
        ScheduleEntry,
        WEEKDAY_NAMES,
        is_day_specific,
        load_schedule,
    )
    from set_due_dates import (  # type: ignore[no-redef]
        ISO_EOD_PATTERN,
        compute_next_eod_et_for_weekdays,
        validate_iso_eod_et,
    )


# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

#: Default state directory on office2. Holds ``morning-checkin-<date>.json``
#: artifacts, ``sweeper-tick-<date>.json`` per-day, and ``sweeper-ledger.jsonl``.
DEFAULT_STATE_DIR = Path("/data/services/openclaw/state/habits")

#: Default canonical history log path (sibling of the state dir).
DEFAULT_HISTORY_PATH = Path("/data/services/openclaw/state/habits-history.jsonl")

#: Sentinel; resolved at call-time via get_vikunja_base_url().
DEFAULT_VIKUNJA_BASE_URL: str = ""

#: Default Vikunja API token file (mode 0600).
DEFAULT_VIKUNJA_TOKEN_PATH = Path("/data/services/openclaw/secrets/vikunja-api")

#: Default schedule YAML path.
DEFAULT_SCHEDULE_PATH = (
    Path(__file__).resolve().parent / "migrations" / "phase3-schedule.yaml"
)

#: Eastern time zone — Kent's local TZ (used for date math + check-in date
#: derivation from ``delivered_at_utc``).
ET_ZONE = ZoneInfo("America/New_York")

#: 48hr (in seconds) — the response window per FR-003.
WINDOW_SECONDS_48HR = 48 * 60 * 60

#: 24hr (in seconds) — conservative lower bound per OD-2. Only check-ins
#: delivered MORE than 24hr ago are candidates so today's fresh check-in is
#: never accidentally evaluated.
WINDOW_SECONDS_24HR = 24 * 60 * 60

#: Tick artifact schema version (matches E4 / sweeper-tick contract).
SCHEMA_VERSION = 1

#: Auto-skipped history event type literal — matches the
#: history-event-auto-skipped contract.
EVENT_TYPE_AUTO_SKIPPED = "auto_skipped"

#: ULID-like tick identifier alphabet (Crockford base32 minus I/L/O/U).
_ULID_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

#: Regex matching ``morning-checkin-YYYY-MM-DD.json`` artifact filenames.
_CHECKIN_FILENAME_RE = re.compile(
    r"^morning-checkin-(\d{4}-\d{2}-\d{2})\.json$"
)


# ---------------------------------------------------------------------------
# Data classes (entity E4 — Sweeper tick record)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CheckinArtifact:
    """One ``morning-checkin-<date>.json`` artifact relevant to the sweeper.

    Attributes:
        path: Absolute path on disk.
        checkin_date_et: ET date the check-in was delivered (``YYYY-MM-DD``).
        delivered_at_utc: ISO-8601 UTC delivery timestamp.
        habits: List of habit entries (raw dicts) from the artifact's
            ``habits`` field.
    """

    path: Path
    checkin_date_et: str
    delivered_at_utc: str
    habits: tuple[dict, ...]


@dataclass(slots=True)
class HabitEvaluation:
    """In-flight evaluation of one habit instance during a sweeper tick.

    Mutable so we can stamp the resolution status as we process. Serialized
    into the tick artifact as a dict.
    """

    task_id: int
    original_checkin_date_et: str
    status: str  # one of the contract status enum values

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "original_checkin_date_et": self.original_checkin_date_et,
            "status": self.status,
        }


@dataclass(slots=True)
class AutoSkipRecord:
    """One habit newly marked ``auto_skipped`` by this tick.

    ``new_due_date_et`` is populated only for day-specific habits.
    """

    task_id: int
    original_checkin_date_et: str
    original_designated_weekday: str | None
    new_due_date_et: str | None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "task_id": self.task_id,
            "original_checkin_date_et": self.original_checkin_date_et,
            "original_designated_weekday": self.original_designated_weekday,
        }
        # Only include new_due_date_et when populated — daily habits don't
        # advance via the sweeper. Contract notes the field is "Absent for
        # daily habits."
        if self.new_due_date_et is not None:
            out["new_due_date_et"] = self.new_due_date_et
        return out


@dataclass(slots=True)
class SweeperError:
    """One per-habit error captured during the tick.

    Errors do NOT abort the tick — the tick exits ``partial`` instead of
    ``failure`` when the per-habit loop accumulates one or more errors.
    """

    task_id: int
    error_type: str
    error_message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "error_type": self.error_type,
            "error_message": self.error_message,
        }


@dataclass(slots=True)
class SweeperTickRecord:
    """In-memory accumulator for one sweeper tick.

    Serialized to ``sweeper-tick-<date>.json`` per E4.
    """

    schema_version: int = SCHEMA_VERSION
    tick_id: str = ""
    started_at_utc: str = ""
    duration_ms: int = 0
    dry_run: bool = False
    expired_checkin_dates_evaluated: list[str] = field(default_factory=list)
    habits_evaluated: list[HabitEvaluation] = field(default_factory=list)
    habits_auto_skipped: list[AutoSkipRecord] = field(default_factory=list)
    errors: list[SweeperError] = field(default_factory=list)
    exit_status: str = "success"  # "success" | "partial" | "failure"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "tick_id": self.tick_id,
            "started_at_utc": self.started_at_utc,
            "duration_ms": self.duration_ms,
            "dry_run": self.dry_run,
            "expired_checkin_dates_evaluated": list(
                self.expired_checkin_dates_evaluated
            ),
            "habits_evaluated": [h.to_dict() for h in self.habits_evaluated],
            "habits_auto_skipped": [
                a.to_dict() for a in self.habits_auto_skipped
            ],
            "errors": [e.to_dict() for e in self.errors],
            "exit_status": self.exit_status,
        }


# ---------------------------------------------------------------------------
# Helpers — tick id, time
# ---------------------------------------------------------------------------


def new_tick_id() -> str:
    """Return a 26-char ULID-shaped identifier (timestamp + 16 random chars).

    Not a strict ULID (we don't claim sortability across clock changes), but
    matches the on-disk shape callers expect from ``tick_id`` fields in
    sibling contracts (``felix-doc-auditor``, ``felix-heartbeat-gate``).
    """
    ts_ms = int(time.time() * 1000)
    # 10 chars of Crockford base32 timestamp (50 bits — enough for 35 years).
    ts_part = []
    value = ts_ms & ((1 << 50) - 1)
    for _ in range(10):
        ts_part.append(_ULID_ALPHABET[value & 0x1F])
        value >>= 5
    ts_str = "".join(reversed(ts_part))
    # 16 chars of randomness for uniqueness within the same millisecond.
    rand_part = "".join(
        _ULID_ALPHABET[secrets.randbelow(32)] for _ in range(16)
    )
    return ts_str + rand_part


def _utc_now_iso(now_utc: datetime) -> str:
    """Return ``now_utc`` as ISO-8601 with explicit ``Z`` suffix."""
    return (
        now_utc.astimezone(timezone.utc)
        .replace(microsecond=0)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    )


def _parse_delivered_at(value: str) -> datetime:
    """Parse a ``delivered_at_utc`` string (accepts ``Z`` or explicit offset).

    Raises:
        ValueError: malformed timestamp.
    """
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        # Treat naive timestamps as UTC for safety. This branch is defensive;
        # production artifacts always include the timezone marker.
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# Helpers — check-in artifact discovery
# ---------------------------------------------------------------------------


def find_expired_checkins(
    state_dir: Path,
    now_utc: datetime,
) -> list[CheckinArtifact]:
    """Return morning-checkin artifacts older than 48hr but younger than ~5d.

    The conservative cutoff per OD-2: only consider artifacts whose
    ``delivered_at_utc`` is BOTH
      * older than 24hr (lower bound — never re-evaluate today's fresh
        check-in), AND
      * older than 48hr (upper bound — within the response window the
        sweeper considers "now closed"); we additionally clamp to a
        7-day max-look-back so an old un-pruned artifact pile doesn't
        explode the sweeper's work.

    Wait — re-reading the contract: the 24hr lower bound is for the
    "candidates eligible for auto-skip" set, and 48hr is the actual
    response window. A check-in delivered 36hr ago is still INSIDE the
    response window — Kent could still reply. Only check-ins older than
    48hr are eligible for auto-skip.

    So the filter is: ``delivered_at_utc`` older than 48hr AND younger
    than the 7-day cutoff (defensive — avoids re-processing very old
    artifacts on a sweeper that's been offline for weeks).

    Returns artifacts sorted by ``delivered_at_utc`` ASC so the tick
    processes the oldest first (deterministic ordering for the artifact's
    ``expired_checkin_dates_evaluated`` field).
    """
    if not state_dir.exists():
        return []

    cutoff_old = now_utc - timedelta(seconds=WINDOW_SECONDS_48HR)
    # 7-day lookback floor — anything older than this is treated as the
    # operator's problem (rare; the sweeper runs daily).
    cutoff_max = now_utc - timedelta(days=7)

    artifacts: list[CheckinArtifact] = []
    for entry in sorted(state_dir.iterdir()):
        if not entry.is_file():
            continue
        match = _CHECKIN_FILENAME_RE.match(entry.name)
        if not match:
            continue
        try:
            data = json.loads(entry.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # Malformed or unreadable artifact — skip silently; the
            # per-habit error path doesn't apply here (we have no task_id
            # yet). The artifact will surface in the operator's manual
            # inspection if it persists.
            continue
        if not isinstance(data, dict):
            continue
        delivered_at_raw = data.get("delivered_at_utc")
        # Older artifacts (mission #371 era) may not have delivered_at_utc;
        # fall back to ``generated_at`` which is the analogous field.
        if not isinstance(delivered_at_raw, str):
            delivered_at_raw = data.get("generated_at")
        if not isinstance(delivered_at_raw, str):
            continue
        try:
            delivered_at = _parse_delivered_at(delivered_at_raw)
        except ValueError:
            continue
        if delivered_at > cutoff_old:
            # Inside 48hr window — Kent can still reply.
            continue
        if delivered_at < cutoff_max:
            continue
        checkin_date = match.group(1)
        raw_habits = data.get("habits") or []
        habits_tuple = tuple(h for h in raw_habits if isinstance(h, dict))
        artifacts.append(
            CheckinArtifact(
                path=entry,
                checkin_date_et=checkin_date,
                delivered_at_utc=delivered_at_raw,
                habits=habits_tuple,
            )
        )

    artifacts.sort(key=lambda a: a.delivered_at_utc)
    return artifacts


# ---------------------------------------------------------------------------
# Helpers — history.jsonl read + atomic append
# ---------------------------------------------------------------------------


def _read_history(history_path: Path) -> list[dict]:
    """Read all records from ``habits-history.jsonl``. Malformed lines skipped.

    Returns an empty list when the file does not exist (the sweeper may
    legitimately run before any history has been written).
    """
    if not history_path.exists():
        return []
    records: list[dict] = []
    try:
        with history_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    records.append(obj)
    except OSError:
        return []
    return records


def _append_history_event(history_path: Path, event: dict) -> None:
    """Append one JSON event to ``habits-history.jsonl`` under an exclusive lock.

    Uses ``fcntl.LOCK_EX`` per the existing ``state_log.append`` precedent
    so the writer is safe under concurrent appends. ``os.fsync`` follows
    the write so a power-loss event after this call returns leaves the
    line durably on disk.
    """
    history_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(
        str(history_path),
        os.O_WRONLY | os.O_CREAT | os.O_APPEND,
        0o664,
    )
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        line = json.dumps(event, ensure_ascii=False, sort_keys=False) + "\n"
        os.write(fd, line.encode("utf-8"))
        os.fsync(fd)
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _atomic_write_json(path: Path, payload: dict) -> None:
    """Write ``payload`` to ``path`` via tmp+fsync+rename for crash safety.

    Mirrors the pattern in ``set_due_dates._atomic_write_json`` /
    ``doc_audit.output.tick_signal.write_tick_signal``.
    """
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


# ---------------------------------------------------------------------------
# Helpers — resolution status evaluation
# ---------------------------------------------------------------------------


def _has_auto_skip_event(
    history: list[dict], task_id: int, checkin_date_et: str
) -> bool:
    """Return True iff a prior ``auto_skipped`` event exists for the pair.

    Idempotency check per FR-005: matches on
    ``(event_type == "auto_skipped", task_id, original_checkin_date_et)``.
    """
    for record in history:
        if record.get("event_type") != EVENT_TYPE_AUTO_SKIPPED:
            continue
        if record.get("task_id") != task_id:
            continue
        if record.get("original_checkin_date_et") != checkin_date_et:
            continue
        return True
    return False


def _has_state_event(
    history: list[dict],
    task_id: int,
    checkin_date_et: str,
    state_value: str,
) -> bool:
    """Return True iff a state_log-style event with the matching state exists.

    The existing ``record_completion.py`` writes records of shape
    ``{"domain": "habits", "task_id": ..., "date": ..., "state": ...}``.
    Resolution checks scan for the matching ``(task_id, date, state)``
    tuple to determine if Kent already replied within the 48hr window.
    """
    for record in history:
        if record.get("domain") != "habits":
            continue
        if record.get("task_id") != task_id:
            continue
        if record.get("date") != checkin_date_et:
            continue
        if record.get("state") != state_value:
            continue
        return True
    return False


def evaluate_habit_resolution(
    history: list[dict],
    task_id: int,
    checkin_date_et: str,
) -> str:
    """Decide which contract-status applies to a habit instance.

    Returns one of:
      * ``"completed_in_window"`` — Kent replied done within 48hr.
      * ``"skipped_in_window"`` — Kent replied skip within 48hr.
      * ``"already_auto_skipped"`` — a prior tick already auto-skipped.
      * ``"unresolved"`` — none of the above; the sweeper auto-skips now.

    The order matches FR-005's idempotency contract: an existing
    auto_skipped event short-circuits the evaluation before any state
    check, so even a missing reply doesn't double-emit.
    """
    if _has_auto_skip_event(history, task_id, checkin_date_et):
        return "already_auto_skipped"
    if _has_state_event(history, task_id, checkin_date_et, "complete"):
        return "completed_in_window"
    if _has_state_event(history, task_id, checkin_date_et, "skipped"):
        return "skipped_in_window"
    return "unresolved"


# ---------------------------------------------------------------------------
# Helpers — Vikunja PUT
# ---------------------------------------------------------------------------


def _vikunja_put_due_date(
    *,
    base_url: str,
    token: str,
    task_id: int,
    new_due_date: str,
    timeout: int = 15,
) -> None:
    """Update one Vikunja task's ``due_date`` via the partial-update verb.

    Vikunja v0.24.6 uses ``POST /tasks/{id}`` for partial updates (NOT
    ``PUT``); see ``record_completion.py`` for the precedent.

    Raises:
        OSError: HTTP error, URL error, or other I/O failure.
    """
    payload = json.dumps({"due_date": new_due_date}).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}tasks/{task_id}",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            # Drain the body so the connection releases cleanly.
            resp.read()
    except urllib.error.HTTPError as exc:
        raise OSError(f"HTTP {exc.code}: {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise OSError(f"URLError: {exc.reason}") from exc


def _load_token(path: Path) -> str:
    """Read a Vikunja API bearer token from a mode-0600 file."""
    return Path(path).read_text(encoding="utf-8").strip()


# ---------------------------------------------------------------------------
# Helpers — designated weekday lookup for a check-in's ET date
# ---------------------------------------------------------------------------


_WEEKDAY_BY_INDEX: tuple[str, ...] = WEEKDAY_NAMES


def _weekday_for_date(date_str: str) -> str:
    """Return the 3-letter ISO weekday name for a ``YYYY-MM-DD`` date string.

    Raises:
        ValueError: malformed date string.
    """
    parsed = datetime.fromisoformat(date_str).date()
    return _WEEKDAY_BY_INDEX[parsed.weekday()]


# ---------------------------------------------------------------------------
# Main sweep entrypoint
# ---------------------------------------------------------------------------


def run_sweep(
    *,
    schedule_path: Path,
    state_dir: Path,
    history_path: Path,
    vikunja_token_path: Path,
    vikunja_base_url: str,
    now_utc: datetime,
    dry_run: bool = False,
) -> SweeperTickRecord:
    """Execute one sweeper tick and return the populated ``SweeperTickRecord``.

    Args:
        schedule_path: Path to the habits runtime schedule YAML.
        state_dir: Directory holding ``morning-checkin-*.json`` artifacts
            and where the per-tick artifact + ledger are written.
        history_path: Canonical ``habits-history.jsonl`` location.
        vikunja_token_path: Path to the Vikunja API bearer token file.
            Read only when at least one day-specific habit needs a PUT
            (and never in ``dry_run`` mode).
        vikunja_base_url: Vikunja API base URL.
        now_utc: Current UTC instant (injected for deterministic tests).
        dry_run: If True, no history append and no Vikunja PUTs are issued.
            The tick artifact IS still written (with ``dry_run: true``) so
            operators can preview what the sweep WOULD do.

    Returns:
        The completed ``SweeperTickRecord``. Caller is responsible for
        writing it to disk + the ledger and printing the SUMMARY line;
        ``main()`` handles those steps.
    """
    tick = SweeperTickRecord(
        tick_id=new_tick_id(),
        started_at_utc=_utc_now_iso(now_utc),
        dry_run=dry_run,
    )
    started_monotonic = time.monotonic()

    # ---- Load schedule ----------------------------------------------------
    try:
        schedule_entries = load_schedule(schedule_path)
    except ScheduleConfigError as exc:
        tick.errors.append(
            SweeperError(
                task_id=0,
                error_type="schedule_load",
                error_message=str(exc),
            )
        )
        tick.exit_status = "failure"
        tick.duration_ms = int((time.monotonic() - started_monotonic) * 1000)
        return tick

    schedule_by_task_id: dict[int, ScheduleEntry] = {
        entry.task_id: entry for entry in schedule_entries
    }

    # ---- Discover expired check-ins --------------------------------------
    expired = find_expired_checkins(state_dir, now_utc)
    tick.expired_checkin_dates_evaluated = [a.checkin_date_et for a in expired]

    if not expired:
        # Nothing to do — clean tick.
        tick.duration_ms = int((time.monotonic() - started_monotonic) * 1000)
        return tick

    # ---- Read history once for the whole tick ----------------------------
    history = _read_history(history_path)

    # ---- Optionally load the Vikunja token (deferred until needed) -------
    vikunja_token: str | None = None

    def _ensure_token() -> str:
        nonlocal vikunja_token
        if vikunja_token is None:
            vikunja_token = _load_token(vikunja_token_path)
        return vikunja_token

    # ---- Per-checkin, per-habit evaluation -------------------------------
    for artifact in expired:
        for habit_entry in artifact.habits:
            task_id_raw = habit_entry.get("vikunja_task_id")
            if not isinstance(task_id_raw, int) or isinstance(
                task_id_raw, bool
            ):
                # Skip malformed entries — record an error but keep going.
                tick.errors.append(
                    SweeperError(
                        task_id=0,
                        error_type="malformed_checkin_habit",
                        error_message=(
                            f"checkin {artifact.checkin_date_et}: habit entry "
                            f"missing/invalid vikunja_task_id "
                            f"(got {task_id_raw!r})"
                        ),
                    )
                )
                continue
            task_id = int(task_id_raw)

            try:
                resolution = evaluate_habit_resolution(
                    history,
                    task_id=task_id,
                    checkin_date_et=artifact.checkin_date_et,
                )
            except Exception as exc:  # pragma: no cover -- defensive
                tick.errors.append(
                    SweeperError(
                        task_id=task_id,
                        error_type="evaluation",
                        error_message=str(exc),
                    )
                )
                continue

            tick.habits_evaluated.append(
                HabitEvaluation(
                    task_id=task_id,
                    original_checkin_date_et=artifact.checkin_date_et,
                    status=resolution,
                )
            )

            if resolution != "unresolved":
                # Already-resolved (or already-auto-skipped) — nothing to
                # write. The status is recorded for operator visibility.
                continue

            # ---- Auto-skip path -------------------------------------------
            schedule_entry = schedule_by_task_id.get(task_id)
            is_dayspec = (
                schedule_entry is not None and is_day_specific(schedule_entry)
            )

            # Determine original_designated_weekday for the event payload.
            # For day-specific habits we record the weekday the check-in
            # WAS for (e.g., Wed for a Wednesday check-in). For daily
            # habits this is null.
            try:
                checkin_weekday = _weekday_for_date(artifact.checkin_date_et)
            except ValueError as exc:  # pragma: no cover -- caught by filename re
                tick.errors.append(
                    SweeperError(
                        task_id=task_id,
                        error_type="weekday_derivation",
                        error_message=str(exc),
                    )
                )
                continue
            original_designated_weekday: str | None = (
                checkin_weekday if is_dayspec else None
            )

            new_due_date_et: str | None = None
            if is_dayspec:
                # Compute next designated weekday's EOD-ET. Uses the
                # WP-01 helper which is unit-tested to produce an
                # explicit-offset (NOT 'Z') ISO timestamp, then we
                # belt-and-suspenders validate via ISO_EOD_PATTERN.
                try:
                    new_due_date_et = compute_next_eod_et_for_weekdays(
                        schedule_entry.designated_weekdays,
                        now_utc=now_utc,
                    )
                except ValueError as exc:  # pragma: no cover -- guarded at load
                    tick.errors.append(
                        SweeperError(
                            task_id=task_id,
                            error_type="weekday_computation",
                            error_message=str(exc),
                        )
                    )
                    continue
                guard = validate_iso_eod_et(new_due_date_et)
                if guard is not None:  # pragma: no cover -- defensive #112
                    tick.errors.append(
                        SweeperError(
                            task_id=task_id,
                            error_type="iso_eod_validation",
                            error_message=guard,
                        )
                    )
                    continue
                # Belt: also enforce the regex literally (mirrors the
                # set_due_dates guard call site).
                if not ISO_EOD_PATTERN.match(new_due_date_et):  # pragma: no cover
                    tick.errors.append(
                        SweeperError(
                            task_id=task_id,
                            error_type="iso_eod_validation",
                            error_message=(
                                f"computed due_date {new_due_date_et!r} does "
                                f"not match ISO_EOD_PATTERN"
                            ),
                        )
                    )
                    continue

                # PUT to Vikunja (skipped in dry_run).
                if not dry_run:
                    try:
                        token = _ensure_token()
                        _vikunja_put_due_date(
                            base_url=vikunja_base_url,
                            token=token,
                            task_id=task_id,
                            new_due_date=new_due_date_et,
                        )
                    except OSError as exc:
                        tick.errors.append(
                            SweeperError(
                                task_id=task_id,
                                error_type="vikunja_put",
                                error_message=str(exc),
                            )
                        )
                        # Per-habit failure resilience: continue with the
                        # remaining habits. We do NOT append the
                        # auto_skipped history event when the Vikunja PUT
                        # failed — running again next tick will retry
                        # both steps and the idempotency check still works
                        # (no prior history event yet).
                        continue

            # Append the auto_skipped history event (skipped in dry_run).
            event = {
                "event_type": EVENT_TYPE_AUTO_SKIPPED,
                "task_id": task_id,
                "original_checkin_date_et": artifact.checkin_date_et,
                "original_designated_weekday": original_designated_weekday,
                "tick_id": tick.tick_id,
                "recorded_at_utc": _utc_now_iso(now_utc),
            }
            if not dry_run:
                try:
                    _append_history_event(history_path, event)
                except OSError as exc:
                    tick.errors.append(
                        SweeperError(
                            task_id=task_id,
                            error_type="history_append",
                            error_message=str(exc),
                        )
                    )
                    continue
                # Update the in-memory history so subsequent habits in the
                # SAME tick see this event for idempotency. (Unlikely to
                # matter — the per-checkin scan visits each task_id once
                # per check-in — but harmless and defensive.)
                history.append(event)

            # Stamp the evaluation row to the contract status enum.
            tick.habits_evaluated[-1].status = "auto_skipped_this_tick"

            tick.habits_auto_skipped.append(
                AutoSkipRecord(
                    task_id=task_id,
                    original_checkin_date_et=artifact.checkin_date_et,
                    original_designated_weekday=original_designated_weekday,
                    new_due_date_et=new_due_date_et,
                )
            )

    # ---- Finalize exit status --------------------------------------------
    if tick.errors:
        tick.exit_status = "partial"

    tick.duration_ms = int((time.monotonic() - started_monotonic) * 1000)
    return tick


# ---------------------------------------------------------------------------
# Output helpers — ledger + tick artifact + SUMMARY line
# ---------------------------------------------------------------------------


def write_tick_artifact(state_dir: Path, tick: SweeperTickRecord) -> Path:
    """Atomically write the per-day ``sweeper-tick-<date>.json`` artifact.

    The date is derived from ``tick.started_at_utc`` converted to ET so the
    artifact name matches the ET date the operator thinks of as "the day
    the sweep ran" (mirrors the morning-checkin naming convention).
    """
    # Convert started_at_utc -> ET to derive the filename.
    started_dt = datetime.strptime(
        tick.started_at_utc, "%Y-%m-%dT%H:%M:%SZ"
    ).replace(tzinfo=timezone.utc)
    et_date = started_dt.astimezone(ET_ZONE).date().isoformat()
    path = state_dir / f"sweeper-tick-{et_date}.json"
    _atomic_write_json(path, tick.to_dict())
    return path


def append_ledger(state_dir: Path, tick: SweeperTickRecord) -> Path:
    """Append a single JSONL line for this tick to ``sweeper-ledger.jsonl``."""
    path = state_dir / "sweeper-ledger.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(tick.to_dict(), ensure_ascii=False, sort_keys=False) + "\n"
    fd = os.open(
        str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o664
    )
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        os.write(fd, line.encode("utf-8"))
        os.fsync(fd)
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
    return path


def print_summary_line(tick: SweeperTickRecord) -> None:
    """Emit the stdout ``SUMMARY:`` line per the doc-auditor precedent.

    Format::

        SUMMARY: status=<status> dry_run=<bool> expired=<n>
                 evaluated=<n> auto_skipped=<n> errors=<n> dur=<ms>ms
    """
    print(
        f"SUMMARY: status={tick.exit_status} "
        f"dry_run={'true' if tick.dry_run else 'false'} "
        f"expired={len(tick.expired_checkin_dates_evaluated)} "
        f"evaluated={len(tick.habits_evaluated)} "
        f"auto_skipped={len(tick.habits_auto_skipped)} "
        f"errors={len(tick.errors)} "
        f"dur={tick.duration_ms}ms"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sweeper",
        description=(
            "Daily 48hr auto-skip sweeper for the habits check-in pipeline "
            "(mission #408). Marks unresolved habits as auto_skipped and, "
            "for day-specific habits, advances their Vikunja due_date to "
            "the next designated weekday. Writes a structured tick artifact "
            "for operator inspection."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Compute what the sweep WOULD do, but issue no history appends "
            "and no Vikunja PUTs. The tick artifact is still written with "
            "dry_run=true so operators can preview."
        ),
    )
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=DEFAULT_STATE_DIR,
        help=(
            f"Directory holding morning-checkin-*.json artifacts + tick "
            f"artifacts (default: {DEFAULT_STATE_DIR})."
        ),
    )
    parser.add_argument(
        "--history-path",
        type=Path,
        default=DEFAULT_HISTORY_PATH,
        help=(
            f"Path to habits-history.jsonl (default: {DEFAULT_HISTORY_PATH})."
        ),
    )
    parser.add_argument(
        "--schedule-path",
        type=Path,
        default=DEFAULT_SCHEDULE_PATH,
        help=(
            f"Path to the habits runtime schedule YAML "
            f"(default: {DEFAULT_SCHEDULE_PATH})."
        ),
    )
    parser.add_argument(
        "--vikunja-token-path",
        type=Path,
        default=DEFAULT_VIKUNJA_TOKEN_PATH,
        help=(
            f"Path to the Vikunja API token file (default: "
            f"{DEFAULT_VIKUNJA_TOKEN_PATH}). Read only when at least one "
            f"day-specific habit needs a PUT."
        ),
    )
    parser.add_argument(
        "--vikunja-base-url",
        default=None,
        help="Vikunja API base URL (default: from VIKUNJA_BASE_URL env or config file).",
    )
    parser.add_argument(
        "--now-utc",
        default=None,
        help=(
            "Override the current UTC instant (ISO-8601, e.g. "
            "'2026-06-02T11:30:00Z'). Test/debug only."
        ),
    )
    return parser


def _parse_now_utc(value: str | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    raw = value
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. See module docstring for exit codes."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    args.vikunja_base_url = args.vikunja_base_url or get_vikunja_base_url()

    try:
        now_utc = _parse_now_utc(args.now_utc)
    except ValueError as exc:
        print(f"ERROR: --now-utc invalid: {exc}", file=sys.stderr)
        return 3

    try:
        tick = run_sweep(
            schedule_path=args.schedule_path,
            state_dir=args.state_dir,
            history_path=args.history_path,
            vikunja_token_path=args.vikunja_token_path,
            vikunja_base_url=args.vikunja_base_url,
            now_utc=now_utc,
            dry_run=args.dry_run,
        )
    except Exception as exc:  # pragma: no cover -- top-level safety net
        # An unhandled exception is a sweeper failure. Construct a minimal
        # failure tick so operators still see SOMETHING on disk.
        failure_tick = SweeperTickRecord(
            tick_id=new_tick_id(),
            started_at_utc=_utc_now_iso(now_utc),
            dry_run=args.dry_run,
            exit_status="failure",
            errors=[
                SweeperError(
                    task_id=0,
                    error_type="unhandled_exception",
                    error_message=f"{type(exc).__name__}: {exc}",
                )
            ],
        )
        try:
            write_tick_artifact(args.state_dir, failure_tick)
            append_ledger(args.state_dir, failure_tick)
        except OSError:
            pass
        print_summary_line(failure_tick)
        return 2

    # Persist the tick artifact + ledger.
    try:
        write_tick_artifact(args.state_dir, tick)
    except OSError as exc:
        tick.errors.append(
            SweeperError(
                task_id=0,
                error_type="tick_artifact_write",
                error_message=str(exc),
            )
        )
        if tick.exit_status == "success":
            tick.exit_status = "partial"
    try:
        append_ledger(args.state_dir, tick)
    except OSError as exc:
        tick.errors.append(
            SweeperError(
                task_id=0,
                error_type="ledger_append",
                error_message=str(exc),
            )
        )
        if tick.exit_status == "success":
            tick.exit_status = "partial"

    print_summary_line(tick)

    if tick.exit_status == "success":
        return 0
    if tick.exit_status == "partial":
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
