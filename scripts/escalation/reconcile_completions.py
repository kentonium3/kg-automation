#!/usr/bin/env python3
"""Reads from the sync cache at /data/services/openclaw/state/sync/task-cache.json
(see scripts/common/sync_cache.py for the canonical entry point).

ADR-0002 Phase 6 ``reconcile_completions`` sweep for the escalation domain.

The reconciliation tick. For every escalation-subscribed task in a project,
read the current state from the sync cache, compare against the JSONL state
log, and:

* Emit a synthetic ``done`` record when the cache shows ``done=true`` but the
  JSONL has no terminal record (Kent ticked done in the UI between ticks —
  the 2026-05-16 habits incident vulnerability class).
* Emit a synthetic ``rescheduled`` record when the cache's ``due_date`` no
  longer matches the JSONL's last-known ``reschedule_to`` (or the initial
  due_date if no prior reschedule) — per research D3.
* Route any task whose records cannot be reduced by ``derive_state`` to the
  Q10 hard-fail surface (file_hard_fail_bug with reason
  ``derive_state_inconsistency``) — per research D8.

Synthetic records use ``source="reconcile"`` so subsequent ticks can identify
reconcile-origin records (and so the per-tick dedup window doesn't conflate
them with agent-sent events).

Hard-fail filing flows through ``scripts.escalation.hard_fail.file_hard_fail_bug``
which performs dedup against open GitHub issues per spec FR-009. Multiple
malformed records in one tick file at most one bug per unique task; multiple
ticks against the same broken task short-circuit at the dedup layer.

CLI surface — see ``contracts/cli.md``. Exit codes::

    0 — reconcile completed (drift may have been detected; synthetic records
        emitted unless ``--dry-run``).
    1 — cache or JSONL fatal error (run aborted; partial report on stderr).
    3 — validation / usage error.

Design references:
    - kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/spec.md
        FR-005 (UI-mark-done detection), FR-008 (Q10 hard-fail integration),
        SC-002 (UI-mark-done detected within one tick), NFR-001 (60-sec
        budget for 50 tasks).
    - kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/contracts/api.md
        ``reconcile_project``, ``reconcile_all``, ``ReconcileReport``,
        ``HardFailEvent``.
    - kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/contracts/cli.md
        flag set + exit codes + stdout shape.
    - kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/research.md
        D3 (rescheduled-drift detection), D6 (cache-first ordering —
        synthetic records skip the Vikunja side-effect because cache
        state already reflects reality), D8 (Q10 hard-fail trigger
        conditions).
    - scripts/escalation/derive_state.py
        ``derive_state`` + ``EscalationStateError`` (consumed for the policy
        walk and the ``derive_state_inconsistency`` hard-fail trigger).
    - scripts/escalation/record_completion.py
        ``record_event`` with ``skip_vikunja=True`` (used to write synthetic
        records — Vikunja state is already authoritative, no re-PATCH needed).
    - scripts/escalation/hard_fail.py
        ``file_hard_fail_bug`` for Q10 hard-fail routing (dedup-aware).
    - scripts/habits/reconcile_completions.py
        Phase 3 precedent — same sweep pattern, different policy.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal, Optional

from scripts.common import state_log
from scripts.common.sync_cache import (
    SLA_NORMAL,
    SLATier,
    TaskCacheView,
    read_cached_task_by_id,
)
from scripts.common.vikunja_config import get_vikunja_base_url
from scripts.escalation.derive_state import (
    EscalationStateError,
    derive_state,
)
from scripts.escalation.hard_fail import (
    HardFailReason,
    file_hard_fail_bug,
)
from scripts.escalation import record_completion as rc
from scripts.escalation.schema import (
    EscalationSchemaError,
    validate_event_params,
)


# Sentinel task_id used for file-level malformed-line hard-fails when no
# parseable task_id can be extracted from the line(s). Per D8 operator-triage
# strategy: file ONE summary hard-fail per affected file per tick listing the
# line numbers, rather than silently dropping unkeyed corruption.
_FILE_LEVEL_HARD_FAIL_SENTINEL_TASK_ID = 0


__all__ = [
    "DEFAULT_BASE_URL",
    "DEFAULT_TOKEN_PATH",
    "JSONL_STATE_DIR",
    "TOUCHPOINT_SLA",
    "TOUCHPOINT_NAME",
    "HardFailEvent",
    "ReconcileReport",
    "reconcile_project",
    "reconcile_all",
    "main",
]


# ---------------------------------------------------------------------------
# Module constants (per contracts/api.md)
# ---------------------------------------------------------------------------

TOUCHPOINT_SLA: SLATier = SLA_NORMAL
TOUCHPOINT_NAME = "escalation.reconcile_completions"

#: Default Vikunja API base URL. Retained for synthetic-record writes via
#: ``record_event`` (the write path still targets Vikunja for PATCH calls
#: when ``skip_vikunja=False``). Resolved lazily via get_vikunja_base_url()
#: at call-time in reconcile_project / reconcile_all to avoid eager config
#: reads at module import.
DEFAULT_BASE_URL: str = ""  # sentinel; resolved lazily — see reconcile_project

#: Default location of the ``felix-bot`` Vikunja API token on office2.
#: Retained for synthetic-record writes via ``record_event``.
DEFAULT_TOKEN_PATH = Path("/data/services/openclaw/secrets/vikunja-api")

#: Per-project JSONL state directory. Reconcile reads (and writes synthetic
#: records into) the per-project files matching
#: ``project-<project_id>-escalation-history.jsonl``.
JSONL_STATE_DIR = Path("/data/services/openclaw/state/escalation")

#: Vikunja's "unset" sentinel value for ``due_date``. The cache inherits
#: the same serialization format from the sync driver.
ZERO_DATE_SENTINEL = "0001-01-01T00:00:00Z"

#: Regex extracting the integer ``project_id`` from a per-project JSONL
#: filename. Used by ``reconcile_all`` to discover projects from
#: ``JSONL_STATE_DIR``.
_PROJECT_FILENAME_RE = re.compile(
    r"^project-(?P<project_id>\d+)-escalation-history\.jsonl$"
)


# ---------------------------------------------------------------------------
# Public dataclasses (per contracts/api.md)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _MalformedLine:
    """One malformed JSONL line surfaced from the read layer.

    Internal-only. Captures enough triage context for the Q10 hard-fail body:

    * ``line_number``: 1-based source-line index (matches operator-visible
      editor line numbers).
    * ``task_id``: Parseable task_id when the line JSON-decodes to a dict
      with an int ``task_id`` field. ``None`` when the line is unparseable,
      non-dict, or missing the key. The reconcile layer routes ``None`` to
      the file-level sentinel hard-fail.
    * ``snippet``: First 160 chars of the source line (already trimmed of
      surrounding whitespace) for inclusion in the bug body.
    * ``reason``: Short free-form reason ("invalid_json", "non_dict",
      "missing_task_id", "schema:<exc>") - distinct from the HardFailReason
      taxonomy; this is the per-line breakdown rendered into the bug body.
    """

    line_number: int
    task_id: Optional[int]
    snippet: str
    reason: str


@dataclass(frozen=True, slots=True)
class HardFailEvent:
    """One Q10 hard-fail event surfaced during a reconcile sweep.

    Per ``contracts/api.md``. Captures the task identity, the reason taxonomy
    value, the detection timestamp, and whether the bug-filing layer found an
    open dedup match (``deduped=True`` → no new GitHub issue was filed).

    Attributes:
        task_id: Immutable Vikunja ``id`` of the affected task.
        task_title: Snapshot of the Vikunja task title at detection time.
        project_id: Vikunja project ``id`` containing the task.
        reason: One of the HardFailReason values (``malformed_jsonl_record``,
            ``derive_state_inconsistency``).
        detail: Free-text detail string (typically the ``str()`` of the
            triggering exception or the empty-records placeholder).
        detected_at: UTC tz-aware datetime of the detection.
        deduped: True when ``file_hard_fail_bug`` found an open issue and did
            NOT file a new one.
        bug_url: URL of the existing OR newly-filed GitHub issue. ``None``
            when ``file_hard_fail_bug`` returned an error result.
    """

    task_id: int
    task_title: str
    project_id: int
    reason: HardFailReason
    detail: str
    detected_at: datetime
    deduped: bool
    bug_url: Optional[str]


@dataclass(frozen=True, slots=True)
class ReconcileReport:
    """Summary of one ``reconcile_project`` invocation.

    Per ``contracts/api.md``. Aggregates counts + duration so the CLI can
    emit a single JSON summary line per project.

    Attributes:
        project_id: Vikunja project ``id`` that was swept.
        project_slug: Best-effort slug (currently the filename stem; full
            slug resolution is deferred to a follow-on mission per research
            D2).
        tasks_scanned: Number of escalation-subscribed tasks examined.
        synthetic_done_emitted: Count of ``state="done"`` synthetic records
            emitted (or that would have been emitted under ``--dry-run``).
        synthetic_rescheduled_emitted: Count of ``state="rescheduled"``
            synthetic records emitted (or that would have been emitted under
            ``--dry-run``).
        synthetic_dismissed_emitted: Count of ``state="dismissed"`` synthetic
            records emitted for tasks the operator deleted in Vikunja (per
            kentonium3/kg-automation#527). Counted under ``--dry-run`` too.
        hard_fails: Every Q10 hard-fail detected during the sweep. Length
            equals the number of distinct tasks that hard-failed (dedup
            within one tick ensures one entry per task even on repeated
            triggers).
        duration_seconds: Wall-clock seconds the sweep took, end to end.
    """

    project_id: int
    project_slug: str
    tasks_scanned: int
    synthetic_done_emitted: int
    synthetic_rescheduled_emitted: int
    synthetic_dismissed_emitted: int = 0
    hard_fails: list[HardFailEvent] = field(default_factory=list)
    duration_seconds: float = 0.0


# ---------------------------------------------------------------------------
# JSONL helpers
# ---------------------------------------------------------------------------


def _jsonl_path_for_project(project_id: int, jsonl_dir: Path) -> Path:
    """Return the per-project JSONL path under ``jsonl_dir``."""
    return jsonl_dir / f"project-{project_id}-escalation-history.jsonl"


def _project_slug_from_filename(path: Path) -> str:
    """Best-effort slug from a per-project JSONL filename.

    Per research D2, slug-based naming is deferred — the on-disk file is
    keyed on ``project_id``. The slug returned here is the filename stem
    (e.g., ``project-4-escalation-history``) which is enough for the CLI's
    JSON summary line.
    """
    return path.stem


def _classify_line(
    line: str,
    line_number: int,
    project_id: int,
) -> tuple[Optional[dict], Optional[_MalformedLine]]:
    """Classify one JSONL source line as valid or malformed.

    Per research D8, "malformed JSONL line" includes any of:
        - JSON parse failure
        - Non-dict payload
        - Missing or non-int ``task_id`` / ``project_id`` keys
        - Mismatched ``project_id`` for the per-project file
        - ``validate_event_params`` rejection (missing/typo'd structured
          parameters per the event_type)

    A line that classifies as malformed routes through Q10 with
    ``reason="malformed_jsonl_record"`` (the caller handles the dedup +
    file-level sentinel routing).

    Returns:
        ``(record, None)`` when the line is valid.
        ``(None, _MalformedLine)`` when the line is malformed.
    """
    snippet = line[:160]
    try:
        obj = json.loads(line)
    except json.JSONDecodeError as exc:
        return None, _MalformedLine(
            line_number=line_number,
            task_id=None,
            snippet=snippet,
            reason=f"invalid_json: {exc.msg}",
        )
    if not isinstance(obj, dict):
        return None, _MalformedLine(
            line_number=line_number,
            task_id=None,
            snippet=snippet,
            reason="non_dict_payload",
        )
    tid = obj.get("task_id")
    if not isinstance(tid, int) or isinstance(tid, bool):
        return None, _MalformedLine(
            line_number=line_number,
            task_id=None,
            snippet=snippet,
            reason="missing_or_invalid_task_id",
        )
    pid = obj.get("project_id")
    if pid != project_id:
        # Per the original semantics: a record whose project_id does not
        # match the per-project file is a cross-project routing bug. The
        # original code "skipped silently" — preserve that posture (it is
        # surfaced elsewhere in the system; treating it as malformed for
        # the file would create false positives every time a record gets
        # written to the wrong file by an upstream bug).
        # Still keep the parsed object NULL-routed so the caller drops it.
        return None, None
    # Per-event_type schema validation. Failure here means missing/typo'd
    # required params (e.g., ``level_sent`` with no ``level``) — D8 reads
    # this as malformed_jsonl_record at the read layer, NOT
    # derive_state_inconsistency.
    try:
        validate_event_params(obj)
    except EscalationSchemaError as exc:
        return None, _MalformedLine(
            line_number=line_number,
            task_id=tid,
            snippet=snippet,
            reason=f"schema: {exc}",
        )
    return obj, None


def _task_deleted_event_for_task(
    task_id: int,
    history_path: Path | None = None,
) -> dict | None:
    """Return the most recent ``task_deleted`` event for ``task_id``, or None.

    Scans ``habits-history.jsonl`` for events where ``event_type == "task_deleted"``
    and ``task_id`` matches. Returns the event with the highest
    ``detected_at_utc`` (lexicographic ISO 8601 sort is correct for the
    canonical ``YYYY-MM-DDTHH:MM:SSZ`` format Phase 5b writes).

    Tolerates missing or malformed files: returns ``None`` on any read
    failure, missing file, or unparseable line. The audit log is
    append-only and may contain interleaved entries from multiple writers;
    we never raise on the audit-log read path.

    Per kentonium3/kg-automation#527: this gates the OSError handler in
    ``_reconcile_one_task`` so a cache miss caused by operator-initiated
    Vikunja task deletion does not file a spurious
    ``derive_state_inconsistency`` hard-fail. The sync driver's Phase 5b
    cleanup (mission #520, ``scripts/sync/cleanup.py``) is the writer of
    the ``task_deleted`` event.

    Args:
        task_id: Vikunja task id to look up.
        history_path: Override for the ``habits-history.jsonl`` path.
            Defaults to ``state_log.STATE_DIR / "habits-history.jsonl"``
            resolved at call time so tests can monkey-patch
            ``state_log.STATE_DIR``.

    Returns:
        The event dict, or ``None`` if no matching event was found.
    """
    if history_path is None:
        history_path = state_log.STATE_DIR / "habits-history.jsonl"
    if not history_path.exists():
        return None
    best: dict | None = None
    best_ts: str = ""
    try:
        with history_path.open("r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(event, dict):
                    continue
                if event.get("event_type") != "task_deleted":
                    continue
                if event.get("task_id") != task_id:
                    continue
                ts = event.get("detected_at_utc")
                if not isinstance(ts, str):
                    continue
                if ts > best_ts:
                    best = event
                    best_ts = ts
    except OSError:
        return None
    return best


def _load_records_for_task(
    task_id: int,
    project_id: int,
    jsonl_dir: Path,
) -> tuple[list[dict], list[_MalformedLine]]:
    """Load every JSONL record for ``(task_id, project_id)`` from the per-project file.

    Returns a tuple ``(records, malformed_lines)``. Malformed lines (JSON
    decode failures, non-dict payloads, missing/invalid ``task_id``, OR
    per-event_type schema-validation failures per D8) are NOT raised — they
    are returned so the caller can route them through the Q10 hard-fail
    surface with ``reason="malformed_jsonl_record"``.

    Args:
        task_id: Vikunja task id to filter on.
        project_id: Vikunja project id (also filters records inside the file
            in case the file accidentally holds cross-project entries).
        jsonl_dir: Directory containing per-project escalation JSONL files.

    Returns:
        Tuple ``(matching_records, malformed_lines)``. ``malformed_lines``
        includes every malformed line in the file (NOT just those for
        ``task_id``) so the caller can surface them in one place.
    """
    path = _jsonl_path_for_project(project_id, jsonl_dir)
    matches: list[dict] = []
    malformed: list[_MalformedLine] = []
    if not path.exists():
        return matches, malformed

    with path.open("r", encoding="utf-8") as fh:
        for line_number, raw in enumerate(fh, start=1):
            line = raw.strip()
            if not line:
                continue
            record, bad = _classify_line(line, line_number, project_id)
            if bad is not None:
                malformed.append(bad)
                continue
            if record is None:
                # Stray cross-project record — skip silently (see
                # ``_classify_line``).
                continue
            if record.get("task_id") == task_id:
                matches.append(record)
    return matches, malformed


def _enumerate_subscribed_tasks(
    project_id: int,
    jsonl_dir: Path,
) -> tuple[list[tuple[int, list[dict]]], list[_MalformedLine]]:
    """Enumerate escalation-subscribed tasks per the JSONL file.

    A task is "subscribed" when it has at least one ``level_sent`` record
    AND no terminal record (``done``/``dismissed``) more recent than the
    most recent ``level_sent``. Subscribed tasks are the only ones reconcile
    needs to inspect — tasks that have terminated already are out of scope.

    Per research D8, every malformed JSONL line (JSON parse failure, non-dict
    payload, missing/invalid ``task_id``, OR per-event_type schema-validation
    failure) is surfaced via the returned ``malformed`` list. The caller
    routes each into a Q10 hard-fail with ``reason="malformed_jsonl_record"``;
    within-tick dedup ensures one bug per ``(task_id, reason)`` even when
    multiple lines for the same task are malformed.

    Args:
        project_id: Vikunja project id whose JSONL file to read.
        jsonl_dir: Directory of per-project files.

    Returns:
        Tuple ``(subscribed, malformed)`` where:
          - ``subscribed`` is a list of ``(task_id, records)`` for every
            subscribed task.
          - ``malformed`` is a list of every malformed line in the file
            (with line number + parseable task_id + snippet + reason).
            Empty when the file has no defects.
        Empty / missing files return ``([], [])``.
    """
    path = _jsonl_path_for_project(project_id, jsonl_dir)
    if not path.exists():
        return [], []

    grouped: dict[int, list[dict]] = {}
    malformed: list[_MalformedLine] = []

    with path.open("r", encoding="utf-8") as fh:
        for line_number, raw in enumerate(fh, start=1):
            line = raw.strip()
            if not line:
                continue
            record, bad = _classify_line(line, line_number, project_id)
            if bad is not None:
                malformed.append(bad)
                continue
            if record is None:
                # Stray cross-project record — skip silently.
                continue
            tid = record.get("task_id")
            if isinstance(tid, int):
                grouped.setdefault(tid, []).append(record)

    subscribed: list[tuple[int, list[dict]]] = []
    for tid, records in grouped.items():
        if _is_subscribed(records):
            subscribed.append((tid, records))
    return subscribed, malformed


def _is_subscribed(records: list[dict]) -> bool:
    """Return True when ``records`` describe an escalation-subscribed task.

    Subscription requires:
      1. At least one ``level_sent`` record (the task entered the funnel),
         AND
      2. No terminal record (``done``/``dismissed``) more recent than the
         most recent ``level_sent``.

    The function sorts by ``timestamp`` (newest-first) and walks once.
    Malformed timestamps fall back to record order — reconcile callers
    file the per-task ``derive_state_inconsistency`` hard-fail downstream
    so the subscription gate doesn't need to handle that case here.
    """
    if not records:
        return False

    def _ts_key(record: dict) -> str:
        # Sort by raw timestamp string. ISO-8601 strings sort correctly as
        # plain strings. Records without a timestamp sort last (oldest)
        # so the newest-first walk still finds the most recent terminal /
        # level_sent record when timestamps are present.
        ts = record.get("timestamp")
        return ts if isinstance(ts, str) else ""

    sorted_records = sorted(records, key=_ts_key, reverse=True)
    seen_level_sent = False
    for r in sorted_records:
        state = r.get("state")
        if state in ("done", "dismissed"):
            # Newest non-stale record is terminal -> NOT subscribed.
            return False
        if state == "level_sent":
            seen_level_sent = True
            break
    return seen_level_sent


def _last_reschedule_to(records: list[dict]) -> Optional[str]:
    """Return the most recent ``reschedule_to`` value, or ``None``.

    Scans records newest-first by timestamp and returns the first
    ``rescheduled`` record's ``reschedule_to``. Returns ``None`` when no
    ``rescheduled`` record exists (the caller then falls back to the
    no-prior-reschedule rule per research D3).
    """
    def _ts_key(record: dict) -> str:
        ts = record.get("timestamp")
        return ts if isinstance(ts, str) else ""

    sorted_records = sorted(records, key=_ts_key, reverse=True)
    for r in sorted_records:
        if r.get("state") == "rescheduled":
            value = r.get("reschedule_to")
            if isinstance(value, str) and value:
                return value
    return None


def _has_terminal_record(records: list[dict]) -> bool:
    """Return True when ``records`` contains a ``done``/``dismissed`` record."""
    for r in records:
        if r.get("state") in ("done", "dismissed"):
            return True
    return False


def _has_done_record(records: list[dict]) -> bool:
    """Return True when ``records`` contains a ``done`` record."""
    for r in records:
        if r.get("state") == "done":
            return True
    return False


def _cache_due_date(fields: dict) -> Optional[str]:
    """Extract the ``YYYY-MM-DD`` form of ``fields["due_date"]``, or ``None``.

    The sync cache inherits Vikunja's serialization format for ``due_date``
    (``YYYY-MM-DDTHH:MM:SSZ``). We strip the time portion for comparison
    against JSONL ``reschedule_to`` (which is always a calendar date). The
    zero-sentinel ``0001-01-01T00:00:00Z`` is treated as ``None`` (no due date).
    """
    raw = fields.get("due_date")
    if not isinstance(raw, str) or not raw:
        return None
    if raw == ZERO_DATE_SENTINEL:
        return None
    # Take the YYYY-MM-DD prefix.
    return raw.split("T", 1)[0]


def _now_utc() -> datetime:
    """Return the current UTC instant as a tz-aware ``datetime``.

    Wrapped as a module-level helper so tests can monkeypatch deterministically.
    """
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Hard-fail filing (with within-tick dedup)
# ---------------------------------------------------------------------------


def _emit_hard_fail(
    *,
    task_id: int,
    task_title: str,
    project_id: int,
    reason: HardFailReason,
    detail: str,
    jsonl_path: Path,
    vikunja_state: dict,
    derive_state_error_message: Optional[str],
    filed_this_tick: set[tuple[int, str]],
    report_hard_fails: list[HardFailEvent],
) -> None:
    """File one Q10 hard-fail bug and append to ``report_hard_fails``.

    Within-tick dedup: if a hard-fail for ``(task_id, reason)`` has already
    been filed this tick, short-circuit silently. The GitHub-level dedup in
    ``file_hard_fail_bug`` covers cross-tick dedup; this set covers the
    "five malformed records in one tick" case from the WP05 prompt's Risks
    section so we never file more than one bug per task per tick.

    Args:
        task_id: Vikunja task id.
        task_title: Snapshot title for the bug body.
        project_id: Vikunja project id.
        reason: One of the three HardFailReason values.
        detail: Free-text detail (typically ``str(exception)`` or the
            empty-records placeholder).
        jsonl_path: Path to the per-project JSONL file (rendered in the
            bug body for operator triage context).
        vikunja_state: Dict to forward into ``file_hard_fail_bug``.
        derive_state_error_message: ``str(EscalationStateError)`` when the
            reason is ``derive_state_inconsistency``; ``None`` otherwise.
        filed_this_tick: Set of ``(task_id, reason)`` tuples already filed
            this tick. Mutated in-place to record the new entry.
        report_hard_fails: List of HardFailEvent objects to append to.
            Mutated in-place.
    """
    dedup_key = (task_id, reason)
    if dedup_key in filed_this_tick:
        return
    filed_this_tick.add(dedup_key)

    detected_at = _now_utc()
    result = file_hard_fail_bug(
        task_id=task_id,
        project_id=project_id,
        task_title=task_title,
        reason=reason,
        jsonl_path=str(jsonl_path),
        detection_snippet=detail,
        vikunja_state=vikunja_state,
        derive_state_error_message=derive_state_error_message,
        detected_at=detected_at.isoformat(),
    )
    deduped = bool(result.get("deduped"))
    bug_url: Optional[str]
    if deduped:
        bug_url = result.get("existing_url")
    elif result.get("filed"):
        bug_url = result.get("issue_url") or None
    else:
        bug_url = None

    report_hard_fails.append(
        HardFailEvent(
            task_id=task_id,
            task_title=task_title,
            project_id=project_id,
            reason=reason,
            detail=detail,
            detected_at=detected_at,
            deduped=deduped,
            bug_url=bug_url,
        )
    )


def _file_malformed_hard_fails(
    *,
    malformed_lines: list[_MalformedLine],
    project_id: int,
    jsonl_path: Path,
    filed_this_tick: set[tuple[int, str]],
    report_hard_fails: list[HardFailEvent],
) -> None:
    """Route every malformed JSONL line through Q10 hard-fail per D8.

    Grouping + dedup strategy:

    * Lines with a parseable ``task_id`` are grouped by that task_id and
      file ONE ``malformed_jsonl_record`` hard-fail per task. The
      ``_emit_hard_fail`` within-tick dedup (keyed on
      ``(task_id, reason)``) ensures we never file more than one bug per
      task per tick, even with N broken lines per task.
    * Lines with no parseable ``task_id`` (unparseable JSON, non-dict
      payload, missing/invalid task_id key) collapse to a single
      file-level sentinel hard-fail with
      ``task_id=_FILE_LEVEL_HARD_FAIL_SENTINEL_TASK_ID`` (0). The detail
      body lists the affected file + every malformed line number so an
      operator can locate the corruption deterministically.

    This routes ALL malformed lines deterministically — no silent drops.
    Reconcile continues processing the (still-valid) subscribed tasks
    after this returns; per spec FR-008, one bad line does NOT halt the
    tick.

    Args:
        malformed_lines: Every malformed line surfaced by the read layer.
        project_id: Vikunja project id for the affected file.
        jsonl_path: Path to the per-project JSONL (rendered in bug body).
        filed_this_tick: Within-tick dedup set, mutated in place.
        report_hard_fails: HardFailEvent list, mutated in place.
    """
    if not malformed_lines:
        return

    # Bucket A: lines with a parseable task_id → one hard-fail per task.
    by_task: dict[int, list[_MalformedLine]] = {}
    # Bucket B: lines with no parseable task_id → one file-level hard-fail.
    file_level: list[_MalformedLine] = []
    for line in malformed_lines:
        if isinstance(line.task_id, int) and line.task_id > 0:
            by_task.setdefault(line.task_id, []).append(line)
        else:
            file_level.append(line)

    # Bucket A: per-task malformed hard-fails. Sorted for deterministic
    # bug-body ordering across ticks; the within-tick dedup set still
    # short-circuits the 2nd+ line per task.
    for task_id in sorted(by_task.keys()):
        task_lines = by_task[task_id]
        detail = _render_malformed_detail(
            jsonl_path=jsonl_path, lines=task_lines
        )
        _emit_hard_fail(
            task_id=task_id,
            task_title=f"task #{task_id}",
            project_id=project_id,
            reason="malformed_jsonl_record",
            detail=detail,
            jsonl_path=jsonl_path,
            vikunja_state={
                "done": "unknown",
                "due_date": None,
            },
            derive_state_error_message=None,
            filed_this_tick=filed_this_tick,
            report_hard_fails=report_hard_fails,
        )

    # Bucket B: file-level sentinel hard-fail covering all unkeyed
    # corruption. Only fires when at least one such line exists.
    if file_level:
        detail = _render_malformed_detail(
            jsonl_path=jsonl_path, lines=file_level
        )
        _emit_hard_fail(
            task_id=_FILE_LEVEL_HARD_FAIL_SENTINEL_TASK_ID,
            task_title=f"file-level corruption: {jsonl_path.name}",
            project_id=project_id,
            reason="malformed_jsonl_record",
            detail=detail,
            jsonl_path=jsonl_path,
            vikunja_state={
                "done": "n/a",
                "due_date": None,
            },
            derive_state_error_message=None,
            filed_this_tick=filed_this_tick,
            report_hard_fails=report_hard_fails,
        )


def _render_malformed_detail(
    *,
    jsonl_path: Path,
    lines: list[_MalformedLine],
) -> str:
    """Render a multi-line detail string for a malformed-line hard-fail body.

    Format:
        ``<file>: <N> malformed line(s):
           line <ln> [task_id=<tid|?>] reason=<short> snippet=<first160>``

    The format is intended to be readable in the GitHub issue body without
    any HTML/markdown decoration — operators triage by line number against
    their editor.
    """
    header = f"{jsonl_path}: {len(lines)} malformed line(s)"
    rows: list[str] = [header]
    for line in lines:
        tid_repr = str(line.task_id) if line.task_id is not None else "?"
        rows.append(
            f"  line {line.line_number} [task_id={tid_repr}] "
            f"reason={line.reason} snippet={line.snippet!r}"
        )
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# Per-task reconcile logic
# ---------------------------------------------------------------------------


def _reconcile_one_task(
    *,
    task_id: int,
    project_id: int,
    records: list[dict],
    base_url: str,
    jsonl_dir: Path,
    dry_run: bool,
    filed_this_tick: set[tuple[int, str]],
    report: dict[str, int],
    report_hard_fails: list[HardFailEvent],
) -> None:
    """Reconcile one subscribed task. Mutates ``report`` + ``report_hard_fails``.

    Steps:
      1. Read current task state from the sync cache (read_cached_task_by_id).
      2. Run ``derive_state(records)``. On ``EscalationStateError`` -> file
         ``derive_state_inconsistency`` hard-fail and return.
      3. Compute cache-vs-JSONL drift:
           - Done-drift: emit synthetic ``done`` record.
           - Rescheduled-drift: emit synthetic ``rescheduled`` record.
      4. On any non-recoverable cache error, propagate ``OSError`` to the
         caller (one bad task should not abort the whole sweep, but the
         per-project sweep handles the abort).
    """
    jsonl_path = _jsonl_path_for_project(project_id, jsonl_dir)

    try:
        view: TaskCacheView = read_cached_task_by_id(
            task_id=task_id,
            sla=TOUCHPOINT_SLA,
            touchpoint_name=TOUCHPOINT_NAME,
        )
    except OSError as exc:
        # Cache miss. Two sub-cases:
        # (a) Operator deleted the task in Vikunja (mission #520 Phase 5b
        #     records a ``task_deleted`` event in habits-history.jsonl).
        #     Emit a synthetic ``dismissed`` record so the task drops out of
        #     subscription on the next tick; no hard-fail. Per #527.
        # (b) Genuine cache staleness / inconsistency. Surface as
        #     ``derive_state_inconsistency`` so the operator can triage.
        deletion_event = _task_deleted_event_for_task(task_id)
        if deletion_event is not None:
            if not dry_run:
                synthetic = {
                    "domain": "escalation",
                    "task_id": task_id,
                    "project_id": project_id,
                    "title": deletion_event.get("title") or f"task #{task_id}",
                    "date": datetime.now(rc.LOCAL_TZ).date().isoformat(),
                    "state": "dismissed",
                    "reason": (
                        f"task_deleted_in_vikunja "
                        f"(detected_at_utc={deletion_event.get('detected_at_utc')})"
                    ),
                    "source": "reconcile",
                    "timestamp": rc._now_utc_iso(),
                    "note": (
                        "Synthesized by reconcile: Vikunja task was deleted by "
                        "the operator; Phase 5b cleanup recorded the deletion "
                        "in habits-history.jsonl. Per "
                        "kentonium3/kg-automation#527."
                    ),
                }
                try:
                    rc.record_event(
                        synthetic,
                        base_url=base_url,
                        token_path=DEFAULT_TOKEN_PATH,
                        skip_vikunja=True,
                    )
                except (
                    EscalationSchemaError,
                    rc.StateLogError,
                    rc.VikunjaError,
                ) as inner_exc:
                    # If even the synthetic-dismissed write fails, surface
                    # as derive_state_inconsistency — same triage path the
                    # done/rescheduled drift handlers use on write failure.
                    _emit_hard_fail(
                        task_id=task_id,
                        task_title=(
                            deletion_event.get("title") or f"task #{task_id}"
                        ),
                        project_id=project_id,
                        reason="derive_state_inconsistency",
                        detail=(
                            f"synthetic dismissed record failed: {inner_exc}"
                        ),
                        jsonl_path=jsonl_path,
                        vikunja_state={"done": "unknown", "due_date": None},
                        derive_state_error_message=None,
                        filed_this_tick=filed_this_tick,
                        report_hard_fails=report_hard_fails,
                    )
                    return
            report["synthetic_dismissed_emitted"] += 1
            return
        # No matching task_deleted event — genuine inconsistency.
        _emit_hard_fail(
            task_id=task_id,
            task_title=f"task #{task_id}",
            project_id=project_id,
            reason="derive_state_inconsistency",
            detail=f"cache read failed: {exc}",
            jsonl_path=jsonl_path,
            vikunja_state={"done": "unknown", "due_date": None},
            derive_state_error_message=None,
            filed_this_tick=filed_this_tick,
            report_hard_fails=report_hard_fails,
        )
        return

    if view.is_private:
        # Private tasks are out-of-scope for the escalation reconciler.
        return

    task_title = (
        view.fields.get("title")
        if isinstance(view.fields.get("title"), str) and view.fields.get("title")
        else f"task #{task_id}"
    )

    vikunja_done = bool(view.fields.get("done"))
    vikunja_due = _cache_due_date(view.fields)
    vikunja_state_for_body = {
        "done": vikunja_done,
        "due_date": view.fields.get("due_date"),
    }

    # ---- Step 2: derive_state inconsistency check ------------------------
    try:
        derive_state(records)
    except EscalationStateError as exc:
        _emit_hard_fail(
            task_id=task_id,
            task_title=task_title,
            project_id=project_id,
            reason="derive_state_inconsistency",
            detail=str(exc),
            jsonl_path=jsonl_path,
            vikunja_state=vikunja_state_for_body,
            derive_state_error_message=str(exc),
            filed_this_tick=filed_this_tick,
            report_hard_fails=report_hard_fails,
        )
        return

    # ---- Step 3a: done-drift detection -----------------------------------
    # Per research D3 + spec FR-005 / SC-002: Kent ticked the task done in
    # the UI between ticks. Vikunja says done=true; JSONL has no terminal
    # ``done`` record. Emit synthetic done record with source="reconcile".
    if vikunja_done and not _has_done_record(records):
        if not dry_run:
            today_iso = datetime.now(rc.LOCAL_TZ).date().isoformat()
            synthetic = {
                "domain": "escalation",
                "task_id": task_id,
                "project_id": project_id,
                "title": task_title,
                "date": today_iso,
                "state": "done",
                "source": "reconcile",
                "timestamp": rc._now_utc_iso(),
                "note": "Synthesized by reconcile: Vikunja done=true, no JSONL done record.",
            }
            try:
                rc.record_event(
                    synthetic,
                    base_url=base_url,
                    token_path=DEFAULT_TOKEN_PATH,
                    skip_vikunja=True,
                )
            except (
                EscalationSchemaError,
                rc.StateLogError,
                rc.VikunjaError,
            ) as exc:
                # If the synthetic record itself can't be written, surface
                # as derive_state_inconsistency — operator triage.
                _emit_hard_fail(
                    task_id=task_id,
                    task_title=task_title,
                    project_id=project_id,
                    reason="derive_state_inconsistency",
                    detail=f"synthetic done record failed: {exc}",
                    jsonl_path=jsonl_path,
                    vikunja_state=vikunja_state_for_body,
                    derive_state_error_message=None,
                    filed_this_tick=filed_this_tick,
                    report_hard_fails=report_hard_fails,
                )
                return
        report["synthetic_done_emitted"] += 1
        # Done is terminal — short-circuit. No further drift detection.
        return

    # ---- Step 3b: rescheduled-drift detection (research D3) --------------
    # If Vikunja's current due_date no longer matches the JSONL's last
    # ``reschedule_to`` (or there is no prior reschedule AND Vikunja has
    # a due_date), emit a synthetic ``rescheduled`` record. Skip when the
    # task already has a terminal record (subscription check should already
    # exclude these, but defend in depth).
    if not _has_terminal_record(records) and vikunja_due is not None:
        last_reschedule = _last_reschedule_to(records)
        # If we have a prior reschedule and it matches Vikunja, no drift.
        # If we have no prior reschedule, we emit only when Vikunja's date
        # disagrees with our best inference. Per the WP05 prompt's "best-
        # effort" rule: when both unknown -> no emit (handled by the
        # vikunja_due is not None guard above); when last_reschedule is
        # None and we have a Vikunja date, emit (Kent edited the due_date
        # post-subscription).
        if last_reschedule != vikunja_due:
            if not dry_run:
                today_iso = datetime.now(rc.LOCAL_TZ).date().isoformat()
                synthetic = {
                    "domain": "escalation",
                    "task_id": task_id,
                    "project_id": project_id,
                    "title": task_title,
                    "date": today_iso,
                    "state": "rescheduled",
                    "source": "reconcile",
                    "timestamp": rc._now_utc_iso(),
                    "note": (
                        f"Synthesized by reconcile: Vikunja due_date "
                        f"{vikunja_due!r} differs from JSONL "
                        f"reschedule_to {last_reschedule!r}."
                    ),
                    "reschedule_to": vikunja_due,
                }
                try:
                    rc.record_event(
                        synthetic,
                        base_url=base_url,
                        token_path=DEFAULT_TOKEN_PATH,
                        skip_vikunja=True,
                    )
                except (
                    EscalationSchemaError,
                    rc.StateLogError,
                    rc.VikunjaError,
                ) as exc:
                    _emit_hard_fail(
                        task_id=task_id,
                        task_title=task_title,
                        project_id=project_id,
                        reason="derive_state_inconsistency",
                        detail=f"synthetic rescheduled record failed: {exc}",
                        jsonl_path=jsonl_path,
                        vikunja_state=vikunja_state_for_body,
                        derive_state_error_message=None,
                        filed_this_tick=filed_this_tick,
                        report_hard_fails=report_hard_fails,
                    )
                    return
            report["synthetic_rescheduled_emitted"] += 1


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def reconcile_project(
    project_id: int,
    *,
    base_url: Optional[str] = None,
    token_path: Optional[Path] = None,
    jsonl_dir: Optional[Path] = None,
    dry_run: bool = False,
    max_tasks: Optional[int] = None,
) -> ReconcileReport:
    """Sweep one escalation project for drift vs the sync cache.

    Per ``contracts/api.md`` and the WP05 prompt. Enumerates every
    escalation-subscribed task in the project, reads current state from
    the sync cache, runs ``derive_state``, and emits synthetic records or
    files Q10 hard-fails as appropriate.

    Args:
        project_id: Vikunja project id to reconcile.
        base_url: Vikunja API base URL (used for synthetic-record writes
            via ``record_event``).
        token_path: Path to the felix-bot bearer token file (used for
            synthetic-record writes via ``record_event``).
        jsonl_dir: Directory of per-project escalation JSONL files.
        dry_run: When True, detect drift + log hard-fails but do NOT write
            synthetic records to JSONL. The ``ReconcileReport`` counters
            still reflect the would-be writes.
        max_tasks: Optional per-project task count cap. ``None`` = no cap.

    Returns:
        Populated ``ReconcileReport``.

    Raises:
        OSError: On cache read failure during the project sweep.
            The caller decides whether to abort the multi-project sweep
            (``reconcile_all`` continues; the CLI exits 1).
    """
    # Resolve module-level defaults at call-time (not at function-definition
    # time) so monkeypatching ``JSONL_STATE_DIR`` / ``DEFAULT_TOKEN_PATH`` in
    # tests is honored by callers that omit the kwargs. base_url is resolved
    # lazily via get_vikunja_base_url() so module import does not require the
    # config file to be deployed (avoiding eager VikunjaConfigError on import).
    if base_url is None:
        base_url = get_vikunja_base_url()
    if token_path is None:
        token_path = DEFAULT_TOKEN_PATH
    if jsonl_dir is None:
        jsonl_dir = JSONL_STATE_DIR

    # Fail-fast: validate the token file exists before the sweep so any
    # synthetic-record write can succeed. Raises FileNotFoundError /
    # ValueError which the CLI maps to exit 3 (usage error per CLI contract).
    if not token_path.exists():
        raise FileNotFoundError(f"Token file not found: {token_path}")
    content = token_path.read_text(encoding="utf-8").strip()
    if not content:
        raise ValueError(f"Token file is empty: {token_path}")

    started_at = time.monotonic()

    subscribed, malformed_lines = _enumerate_subscribed_tasks(
        project_id, jsonl_dir
    )
    if max_tasks is not None and max_tasks >= 0:
        subscribed = subscribed[:max_tasks]

    report_counters: dict[str, int] = {
        "synthetic_done_emitted": 0,
        "synthetic_rescheduled_emitted": 0,
        "synthetic_dismissed_emitted": 0,
    }
    report_hard_fails: list[HardFailEvent] = []
    filed_this_tick: set[tuple[int, str]] = set()
    tasks_scanned = 0

    jsonl_path = _jsonl_path_for_project(project_id, jsonl_dir)

    # Route malformed JSONL lines through Q10 BEFORE the subscribed sweep
    # so corrupt records are surfaced even when the file has no subscribed
    # tasks left to scan. Per D8: one hard-fail per (task_id, reason) per
    # tick; lines with no parseable task_id collapse to a single sentinel
    # bug (task_id=0) listing every affected line number.
    _file_malformed_hard_fails(
        malformed_lines=malformed_lines,
        project_id=project_id,
        jsonl_path=jsonl_path,
        filed_this_tick=filed_this_tick,
        report_hard_fails=report_hard_fails,
    )

    for task_id, records in subscribed:
        tasks_scanned += 1
        _reconcile_one_task(
            task_id=task_id,
            project_id=project_id,
            records=records,
            base_url=base_url,
            jsonl_dir=jsonl_dir,
            dry_run=dry_run,
            filed_this_tick=filed_this_tick,
            report=report_counters,
            report_hard_fails=report_hard_fails,
        )

    duration = time.monotonic() - started_at
    return ReconcileReport(
        project_id=project_id,
        project_slug=_project_slug_from_filename(jsonl_path),
        tasks_scanned=tasks_scanned,
        synthetic_done_emitted=report_counters["synthetic_done_emitted"],
        synthetic_rescheduled_emitted=(
            report_counters["synthetic_rescheduled_emitted"]
        ),
        synthetic_dismissed_emitted=(
            report_counters["synthetic_dismissed_emitted"]
        ),
        hard_fails=report_hard_fails,
        duration_seconds=duration,
    )


def reconcile_all(
    *,
    base_url: Optional[str] = None,
    token_path: Optional[Path] = None,
    jsonl_dir: Optional[Path] = None,
    dry_run: bool = False,
    max_tasks: Optional[int] = None,
) -> list[ReconcileReport]:
    """Sweep every escalation-subscribed project under ``jsonl_dir``.

    Discovers projects by globbing per-project JSONL filenames. Calls
    :func:`reconcile_project` for each. One report per project, in
    project-id-ascending order.

    Args:
        base_url: Vikunja API base URL.
        token_path: Path to the felix-bot bearer token file.
        jsonl_dir: Directory of per-project escalation JSONL files.
        dry_run: When True, detect drift but emit no synthetic records.
        max_tasks: Optional cap per project. Applied uniformly.

    Returns:
        List of ``ReconcileReport`` objects, one per discovered project.

    Raises:
        FileNotFoundError: When ``token_path`` does not exist.
        OSError: Propagated from ``reconcile_project`` on Vikunja failure;
            the CLI surfaces this as exit code 1.
    """
    if base_url is None:
        base_url = get_vikunja_base_url()
    if token_path is None:
        token_path = DEFAULT_TOKEN_PATH
    if jsonl_dir is None:
        jsonl_dir = JSONL_STATE_DIR

    if not jsonl_dir.exists():
        return []
    project_ids: list[int] = []
    for path in sorted(jsonl_dir.glob("project-*-escalation-history.jsonl")):
        match = _PROJECT_FILENAME_RE.match(path.name)
        if match is None:
            continue
        project_ids.append(int(match.group("project_id")))

    reports: list[ReconcileReport] = []
    for pid in project_ids:
        reports.append(
            reconcile_project(
                pid,
                base_url=base_url,
                token_path=token_path,
                jsonl_dir=jsonl_dir,
                dry_run=dry_run,
                max_tasks=max_tasks,
            )
        )
    return reports


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class _ArgparseError(Exception):
    """Raised by ``_StructuredArgumentParser`` on argparse usage errors.

    ``main()`` catches this and converts it to exit code 3 with a structured
    stderr line per contracts/cli.md.
    """


class _StructuredArgumentParser(argparse.ArgumentParser):
    """ArgumentParser subclass that routes usage errors through exit 3."""

    def error(self, message: str) -> None:  # type: ignore[override]
        raise _ArgparseError(message)


def _build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser for the reconcile CLI."""
    parser = _StructuredArgumentParser(
        prog="python3 -m scripts.escalation.reconcile_completions",
        description=(
            "Phase 6 escalation reconcile sweep. Detects cache-vs-JSONL "
            "drift; emits synthetic records; routes inconsistent state "
            "through Q10 hard-fail. Exits 0/1/3 per contracts/cli.md."
        ),
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--project-id",
        type=int,
        default=None,
        help="Reconcile a single Vikunja project by id.",
    )
    group.add_argument(
        "--all",
        action="store_true",
        help=(
            "Reconcile every project discovered by globbing JSONL files in "
            "--jsonl-dir."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Detect drift and log; do not emit synthetic records.",
    )
    parser.add_argument(
        "--max-tasks",
        type=int,
        default=None,
        help="Cap on tasks reconciled per project (default: no cap).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-task stdout; only emit the JSON summary.",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Vikunja API base URL (default: from vikunja_config helper).",
    )
    parser.add_argument(
        "--token-path",
        type=Path,
        default=DEFAULT_TOKEN_PATH,
        help=(
            "Path to the felix-bot Vikunja API token file "
            f"(default: {DEFAULT_TOKEN_PATH})."
        ),
    )
    parser.add_argument(
        "--jsonl-dir",
        type=Path,
        default=JSONL_STATE_DIR,
        help=(
            "Directory of per-project escalation JSONL files "
            f"(default: {JSONL_STATE_DIR})."
        ),
    )
    return parser


def _emit_drift_line(
    *,
    quiet: bool,
    task_id: int,
    project_id: int,
    reason: str,
    emitted_synthetic: str,
) -> None:
    """Emit one ``DRIFT`` line per contracts/cli.md."""
    if quiet:
        return
    print(
        f"DRIFT task={task_id} project={project_id} reason={reason} "
        f"emitted_synthetic={emitted_synthetic}"
    )


def _emit_hardfail_line(
    *,
    quiet: bool,
    event: HardFailEvent,
) -> None:
    """Emit one ``HARDFAIL`` line per contracts/cli.md."""
    if quiet:
        return
    bug_repr = event.bug_url or ("DEDUPED" if event.deduped else "PENDING")
    print(
        f"HARDFAIL task={event.task_id} project={event.project_id} "
        f"reason={event.reason} bug_url={bug_repr}"
    )


def _emit_summary(report: ReconcileReport) -> None:
    """Emit the per-project JSON summary line."""
    payload = {
        "project_id": report.project_id,
        "tasks_scanned": report.tasks_scanned,
        "synthetic_done": report.synthetic_done_emitted,
        "synthetic_rescheduled": report.synthetic_rescheduled_emitted,
        "synthetic_dismissed": report.synthetic_dismissed_emitted,
        "hard_fails": len(report.hard_fails),
        "duration_s": round(report.duration_seconds, 3),
    }
    print(json.dumps(payload))


def _emit_per_task_lines(report: ReconcileReport, *, quiet: bool) -> None:
    """Emit DRIFT + HARDFAIL stdout lines for one report."""
    # Synthetic-done lines (count, not detail — task_id detail is lost
    # at the counter boundary; the JSONL file is the authoritative record
    # of which tasks got synthesized).
    for _ in range(report.synthetic_done_emitted):
        _emit_drift_line(
            quiet=quiet,
            task_id=0,
            project_id=report.project_id,
            reason="vikunja_done",
            emitted_synthetic="done",
        )
    for _ in range(report.synthetic_rescheduled_emitted):
        _emit_drift_line(
            quiet=quiet,
            task_id=0,
            project_id=report.project_id,
            reason="due_date_changed",
            emitted_synthetic="rescheduled",
        )
    for _ in range(report.synthetic_dismissed_emitted):
        _emit_drift_line(
            quiet=quiet,
            task_id=0,
            project_id=report.project_id,
            reason="vikunja_task_deleted",
            emitted_synthetic="dismissed",
        )
    for event in report.hard_fails:
        _emit_hardfail_line(quiet=quiet, event=event)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Exit codes 0/1/3 per contracts/cli.md."""
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except _ArgparseError as exc:
        print(
            json.dumps(
                {"ok": False, "step": "argparse", "error": str(exc)}
            ),
            file=sys.stderr,
        )
        return 3

    # Exactly one of --project-id / --all must be specified.
    if args.project_id is None and not args.all:
        print(
            json.dumps(
                {
                    "ok": False,
                    "step": "argparse",
                    "error": (
                        "exactly one of --project-id or --all is required"
                    ),
                }
            ),
            file=sys.stderr,
        )
        return 3

    try:
        if args.all:
            reports = reconcile_all(
                base_url=args.base_url,
                token_path=args.token_path,
                jsonl_dir=args.jsonl_dir,
                dry_run=args.dry_run,
                max_tasks=args.max_tasks,
            )
        else:
            reports = [
                reconcile_project(
                    args.project_id,
                    base_url=args.base_url,
                    token_path=args.token_path,
                    jsonl_dir=args.jsonl_dir,
                    dry_run=args.dry_run,
                    max_tasks=args.max_tasks,
                )
            ]
    except (FileNotFoundError, ValueError) as exc:
        # Token-load failures: usage error per CLI contract.
        print(
            json.dumps(
                {"ok": False, "step": "token_load", "error": str(exc)}
            ),
            file=sys.stderr,
        )
        return 3
    except OSError as exc:
        # Vikunja / JSONL fatal failure. Exit 1 per contracts/cli.md.
        print(
            json.dumps(
                {"ok": False, "step": "vikunja_or_jsonl", "error": str(exc)}
            ),
            file=sys.stderr,
        )
        return 1

    for report in reports:
        _emit_per_task_lines(report, quiet=args.quiet)
        _emit_summary(report)

    return 0


if __name__ == "__main__":  # pragma: no cover - exercised via subprocess
    sys.exit(main())
