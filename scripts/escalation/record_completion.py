#!/usr/bin/env python3
"""ADR-0002 Phase 6 ``record_completion`` for the escalation domain.

Per-event side-effect dispatcher. Every live escalation event flows
through the two-step path below (post-parity-cleanup; see
``kitty-specs/remove-escalation-v1-parity-01KT4VTD``):

    Step 0: Validate the candidate record (Phase 2 shared validator + the
            escalation per-event_type validator from ``scripts.escalation.schema``).
            Raises :class:`scripts.escalation.schema.EscalationSchemaError` on
            failure, BEFORE any side-effects.

    Step 1 (Vikunja side-effect, FIRST — only for two states):
        All writes go through :meth:`VikunjaClient.patch_task`, i.e.
        ``PATCH /api/v2/tasks/{task_id}`` as an RFC 7396 merge patch carrying
        only the changed key (mission felix-rrule-adaptation, WP04, #1111).
        The old v1 ``PATCH /api/v1/tasks/{id}`` answered **405** on the RRULE
        server, and a v1 narrow write strips the recurrence rule (R-005).

        - For ``state="done"``: read the task (v2), decide whether this
          completion should end the series (``exhaustion_expected``), send
          ``{"done": true}``, re-read on a 304, then classify the result:
          ``advanced`` / ``series_ended`` (``completion_outcome``) for a
          repeating task, ``done_one_off`` for a task without a rule, else
          ``unexpected``. ``vikunja_actions`` gets ``task_PATCH_done`` and
          ``outcome:<x>``.
          **Unexpected ordering:** Kent did say done, so the JSONL done record
          is STILL written, with ``note="vikunja outcome unexpected: ..."``;
          only *after* that write does the CLI exit non-zero
          (:data:`EXIT_OUTCOME_UNEXPECTED`) so the agent reports the anomaly.
        - For ``state="rescheduled"``: read the task, send ``{"due_date":
          <end-of-day ET>}``, read back (the PATCH response, or a GET after a
          304). If the rule changed (``not same_rule``), raise
          :class:`VikunjaError` ("rule changed by reschedule") **before** the
          JSONL write: the task is in a wrong state, so no record may claim
          success.
        - For ``state="level_sent" | "snoozed" | "dismissed"``: NO Vikunja
          side-effect. JSONL append (Step 2) is the sole record.
        - All requests authenticate as ``felix-bot`` (FR-010) using the token
          loaded from ``token_path``.
        - On any HTTP/network failure: raise :class:`VikunjaError`. No JSONL
          write happens.

    Step 2 (JSONL append, SECOND):
        Write the JSONL record to
        ``/data/services/openclaw/state/escalation/project-<project_id>-escalation-history.jsonl``
        using the same fcntl-locked append-then-flush-then-fsync pattern as
        ``scripts.common.state_log.append``. The Phase 2 library writes per
        ``<domain>-history.jsonl`` only, so the per-project escalation files
        are written directly here. On I/O failure raise :class:`StateLogError`
        — Vikunja already committed; the CLI surfaces this as exit code 2 for
        operator triage.

Ordering is non-negotiable per research D6. Vikunja is the unreliable remote;
failing there first surfaces the network problem before any state_log line is
written. Vikunja state is authoritative for "did Kent get the message"; the
JSONL is canonical for our derived state walk.

CLI surface — see ``contracts/cli.md``. Exit codes:

    0 — success (writes done OR idempotent no-op)
    1 — Vikunja step failure (no JSONL write)
    2 — JSONL step failure (Vikunja already committed)
    3 — validation / usage error
    4 — ``done`` written to Vikunja and JSONL, but the Vikunja outcome was
        ``unexpected`` (the JSONL note says why); report it to Kent verbatim

Design references:
    - kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/spec.md
        FR-002, FR-004, FR-010, NFR-004
    - kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/contracts/api.md
        ``record_event``, ``idempotent_record_event``, exception types,
        module constants.
    - kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/contracts/cli.md
        flag set + exit codes.
    - kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/data-model.md
        Entity 1 (JSONL record shape).
    - kitty-specs/migrate-escalation-to-jsonl-state-model-01KS5R4D/research.md
        D2 (filename), D4 (snooze_until TZ), D6 (two-write ordering).
    - kitty-specs/remove-escalation-v1-parity-01KT4VTD/contracts/escalation-side-effects.contract.md
        Post-parity-cleanup side-effect contract.
    - scripts/habits/record_completion.py
        Phase 3 precedent (HTTP wrapper + per-state side-effect pattern).
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from scripts.common import et_datetime
from scripts.common.state_log_schema import (
    validate_record as _validate_shared_record,
)
from scripts.common.vikunja_client import VikunjaClient
from scripts.common.vikunja_client import VikunjaError as _ClientVikunjaError
from scripts.common.vikunja_config import (
    get_vikunja_base_url,
    get_vikunja_token_path,
)
from scripts.common.vikunja_rule import (
    completion_outcome,
    exhaustion_expected,
    has_rule,
    normalise,
    recurrence_drift,
)
from scripts.escalation.schema import (
    EVENT_TYPE_PARAMETERS,
    EscalationSchemaError,
    validate_event_params,
)


__all__ = [
    "DEFAULT_BASE_URL",
    "DEFAULT_TOKEN_PATH",
    "EXIT_OUTCOME_UNEXPECTED",
    "HTTP_TIMEOUT_SECONDS",
    "JSONL_STATE_DIR",
    "LOCAL_TZ",
    "VikunjaError",
    "StateLogError",
    "EscalationSchemaError",
    "record_event",
    "idempotent_record_event",
    "main",
]


# ---------------------------------------------------------------------------
# Module constants (per contracts/api.md)
# ---------------------------------------------------------------------------

#: Sentinel; resolved at call-time via get_vikunja_base_url().
DEFAULT_BASE_URL: str = ""

#: Override hook for the default token path. ``None`` means "resolve the token
#: path at call-time via :func:`scripts.common.vikunja_config.get_vikunja_token_path`"
#: — the WP01 seam that returns the kent-owned runtime credential (FR-001). No
#: felix-bot literal lives here anymore; the path is decided at exactly one point.
#: Kept as a module attribute so callers/tests may monkeypatch a fixed path.
DEFAULT_TOKEN_PATH: Optional[Path] = None

#: HTTP socket timeout in seconds for every Vikunja API call.
HTTP_TIMEOUT_SECONDS = 30

#: Per-project JSONL state directory. Distinct from the Phase 2 ``STATE_DIR``
#: which is one file per domain. Escalation uses one file per project_id.
JSONL_STATE_DIR = Path("/data/services/openclaw/state/escalation")

#: Kent's local timezone (FR-004). All ``snooze_until`` arithmetic and the
#: write-time ``date`` resolution happen in this TZ. Sourced from the canonical
#: ET utility (#761) so there is one ``America/New_York`` definition repo-wide.
LOCAL_TZ = et_datetime.ET_ZONE

#: CLI exit code for a ``done`` whose Vikunja outcome was ``unexpected``.
#: The JSONL record HAS been written (with the anomaly in ``note``).
EXIT_OUTCOME_UNEXPECTED = 4

#: File mode for per-project JSONL files (rw-rw-r--).
_STATE_FILE_MODE: int = 0o664


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class VikunjaError(Exception):
    """Raised when the Vikunja side-effect step (HTTP) fails.

    The message names the failed sub-step (``PATCH done`` / ``PATCH due_date``)
    and includes the HTTP status code / network error so the operator can
    triage quickly. No JSONL line is written when this is raised; callers
    should surface exit code 1.
    """


class StateLogError(Exception):
    """Raised when the JSONL append step fails after Vikunja has succeeded.

    Vikunja already committed the side-effect (done PATCH or due_date PATCH)
    — operator triage required to either append the missing JSONL record by
    hand OR reverse the Vikunja state. Callers surface exit code 2.
    """


# ---------------------------------------------------------------------------
# Token loader
# ---------------------------------------------------------------------------


def _read_token(token_path: Path) -> str:
    """Read and return the felix-bot bearer token from ``token_path``.

    Args:
        token_path: Filesystem path to the token file.

    Returns:
        The stripped token string.

    Raises:
        FileNotFoundError: If the file is missing.
        OSError: If the file exists but cannot be read.
        ValueError: If the file is empty after strip.
    """
    if not token_path.exists():
        raise FileNotFoundError(f"Token file not found: {token_path}")
    content = token_path.read_text(encoding="utf-8").strip()
    if not content:
        raise ValueError(f"Token file is empty: {token_path}")
    return content


# ---------------------------------------------------------------------------
# HTTP helper (WP03, mission #860: migrated onto the shared VikunjaClient)
# ---------------------------------------------------------------------------


def _translate(verb: str, url: str, exc: _ClientVikunjaError) -> VikunjaError:
    """Map a client exception to this module's :class:`VikunjaError`.

    Keeps the pre-migration message substrings (``HTTP <status>`` /
    ``network failure``) that callers and tests rely on.
    """
    if exc.status is not None:
        return VikunjaError(f"{verb} {url} failed with HTTP {exc.status}: {exc.body!r}")
    return VikunjaError(f"{verb} {url} network failure: {exc.verbose_message()}")


def _client(base_url: str, token: str) -> VikunjaClient:
    return VikunjaClient(base_url=base_url, token=token, timeout=HTTP_TIMEOUT_SECONDS)


def _get_task(client: VikunjaClient, task_id: int) -> dict:
    """GET ``/api/v2/tasks/{task_id}``, errors mapped to :class:`VikunjaError`."""
    url = f"{client.v2_base_url}/tasks/{task_id}"
    try:
        return client.get_task_v2(task_id)
    except _ClientVikunjaError as exc:
        raise _translate("GET", url, exc) from exc


def _patch_task(
    task_id: int,
    body: dict,
    *,
    base_url: str,
    token: str,
    client: VikunjaClient | None = None,
) -> dict | None:
    """PATCH ``/api/v2/tasks/{task_id}`` via :meth:`VikunjaClient.patch_task`.

    Sends exactly ``body`` as a merge patch (WP02 seam). Returns the task the
    server answered with, or ``None`` on 304 (no change; the caller re-reads).

    Raises:
        VikunjaError: On HTTP-status-error, network failure, or timeout.
            Message is ``PATCH <v2 url> failed with HTTP <status>: <body>`` or
            ``PATCH <v2 url> network failure: ...`` (substrings preserved for
            existing callers/tests).
    """
    if client is None:
        client = _client(base_url, token)
    url = f"{client.v2_base_url}/tasks/{task_id}"
    try:
        return client.patch_task(task_id, body)
    except _ClientVikunjaError as exc:
        raise _translate("PATCH", url, exc) from exc


def _rule_summary(task: dict) -> str:
    rule = normalise(task.get("repeat"))
    return "none" if rule is None else json.dumps(rule, sort_keys=True)


def _task_summary(task: dict) -> str:
    return (
        f"done={task.get('done')!r} due_date={task.get('due_date')!r} "
        f"rule={_rule_summary(task)} "
        f"repeats_from_current_date={task.get('repeats_from_current_date')!r} "
        f"reminders={len(task.get('reminders') or [])}"
    )


# ---------------------------------------------------------------------------
# Filename routing + clock helpers
# ---------------------------------------------------------------------------


def _jsonl_path_for_record(record: dict) -> Path:
    """Return the per-project JSONL path for ``record``.

    Per research D2: filename is keyed on ``project_id``. (Slug-based naming
    is deferred — it requires a Vikunja API lookup of the project title; the
    helpers test-cleanly with the immutable integer id.) The on-disk record
    carries both ``task_id`` and ``project_id`` for unambiguous routing.

    Args:
        record: Escalation JSONL record dict (must contain ``project_id``).

    Returns:
        Path to the per-project history file under
        :data:`JSONL_STATE_DIR`.
    """
    project_id = record["project_id"]
    return JSONL_STATE_DIR / f"project-{project_id}-escalation-history.jsonl"


def _today_local() -> date:
    """Return today's date in :data:`LOCAL_TZ` (FR-004 clock).

    Exposed as a module function so tests can monkeypatch without overriding
    ``datetime.now``. All snooze-arithmetic and the write-time ``date`` field
    flow through here.
    """
    return et_datetime.today_et()


def _now_utc_iso() -> str:
    """Current UTC instant as ISO-8601 with offset.

    Exposed as a module function so tests can monkeypatch deterministically.
    """
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _compute_snooze_until(snooze_days: int) -> str:
    """Compute ``snooze_until = today + snooze_days`` in local TZ (FR-004).

    Args:
        snooze_days: Positive integer count of days.

    Returns:
        ISO-8601 ``YYYY-MM-DD`` string.

    Raises:
        ValueError: If ``snooze_days`` is not a positive integer.
    """
    if (
        isinstance(snooze_days, bool)
        or not isinstance(snooze_days, int)
        or snooze_days <= 0
    ):
        raise ValueError(
            f"snooze_days '{snooze_days!r}' must be a positive integer"
        )
    return (_today_local() + timedelta(days=snooze_days)).isoformat()


# ---------------------------------------------------------------------------
# JSONL append (per-project, fcntl-locked)
# ---------------------------------------------------------------------------


def _idempotency_match(
    file_path: Path, task_id: int, date_str: str, state: str
) -> bool:
    """Return True if a record matching ``(task_id, date, state)`` already exists.

    Tolerates malformed lines (skipped silently) so a partial last line from a
    crashed write does not poison the dedup check. Mirrors
    :func:`scripts.common.state_log._idempotency_match`.
    """
    if not file_path.exists():
        return False
    target = (task_id, date_str, state)
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


def _append_jsonl(record: dict) -> Path:
    """Atomically append ``record`` to its per-project JSONL file.

    Uses ``fcntl.LOCK_EX`` across the read-check-write critical section. The
    file is created with mode 0o664 on first write; the parent directory is
    created if missing.

    On any I/O error, raises :class:`StateLogError`. Caller MUST treat this
    as a post-Vikunja-commit failure (operator triage required).

    Args:
        record: Escalation JSONL record dict (already validated).

    Returns:
        The absolute path of the file written to.

    Raises:
        StateLogError: On any filesystem error (parent missing, permission,
            disk full, fsync failure, etc.).
    """
    try:
        path = _jsonl_path_for_record(record)
        path.parent.mkdir(parents=True, exist_ok=True)

        fd = os.open(
            str(path),
            os.O_WRONLY | os.O_CREAT | os.O_APPEND,
            _STATE_FILE_MODE,
        )
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            # Idempotent dedup inside the lock — append-time check beats the
            # CLI/library boundary and protects against duplicate ticks.
            if _idempotency_match(
                path,
                record["task_id"],
                record["date"],
                record["state"],
            ):
                return path
            line = (
                json.dumps(record, ensure_ascii=False, sort_keys=False)
                + "\n"
            )
            os.write(fd, line.encode("utf-8"))
            os.fsync(fd)
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)
        return path
    except StateLogError:  # pragma: no cover - defensive
        raise
    except Exception as exc:  # noqa: BLE001 — re-raise as StateLogError
        raise StateLogError(f"JSONL append failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Per-state Vikunja side-effects
# ---------------------------------------------------------------------------


def _done_side_effect(
    client: VikunjaClient, task_id: int
) -> tuple[str, str | None]:
    """Mark ``task_id`` done on v2 and classify the outcome.

    Returns ``(outcome, anomaly)``. ``outcome`` is ``advanced`` /
    ``series_ended`` (repeating task, :func:`completion_outcome`),
    ``done_one_off`` (no rule, now done) or ``unexpected``; ``anomaly`` is a
    before/after summary when the outcome is ``unexpected``, else ``None``.
    """
    before = _get_task(client, task_id)
    recurring = has_rule(before)
    exhaustion = (
        exhaustion_expected(before, preview=client.preview_occurrences)
        if recurring
        else "no"
    )
    after = _patch_task(
        task_id, {"done": True}, base_url=client.base_url, token=client.token, client=client
    )
    if after is None:
        try:
            after = _get_task(client, task_id)
        except VikunjaError as exc:
            # The write went out; only the classification failed. Kent did
            # say done, so keep the record and report the anomaly.
            return "unexpected", (
                f"vikunja outcome unexpected: readback after 304 failed ({exc}); "
                f"before {_task_summary(before)}"
            )
    outcome: str
    if recurring:
        outcome = completion_outcome(before, after, exhaustion=exhaustion)
    else:
        # A one-off task has no series to advance or end. completion_outcome
        # would call its done=true "unexpected" (exhaustion "no"), so it is
        # special-cased here (WP04 T017 step 3).
        outcome = "done_one_off" if after.get("done") is True else "unexpected"
    # The rule itself was judged by completion_outcome; this checks the flag
    # and the reminders, letting absolute reminders move only as the server
    # moves them on an advance (shared helper, vikunja_rule.recurrence_drift).
    losses = recurrence_drift(
        before, after, compare_rule=False, advanced=outcome == "advanced"
    )
    if losses:
        # The rule may have advanced correctly, but a lost reminder or a reset
        # repeat-from-completion flag is damage, never a normal completion.
        outcome = "unexpected"
    anomaly = None
    if outcome == "unexpected":
        anomaly = (
            "vikunja outcome unexpected: "
            f"before {_task_summary(before)}; after {_task_summary(after)}; "
            f"exhaustion_expected={exhaustion}"
        )
        if losses:
            anomaly += f"; companion fields changed: {', '.join(losses)}"
    return outcome, anomaly


def _reschedule_side_effect(
    client: VikunjaClient, task_id: int, reschedule_to: str
) -> None:
    """PATCH the due date on v2; assert the rule and companion fields survived."""
    before = _get_task(client, task_id)
    after = _patch_task(
        task_id,
        {"due_date": et_datetime.et_end_of_day(reschedule_to)},
        base_url=client.base_url,
        token=client.token,
        client=client,
    )
    if after is None:
        after = _get_task(client, task_id)
    drift = recurrence_drift(before, after)
    if "repeat" in drift:
        raise VikunjaError(
            f"rule changed by reschedule of task {task_id}: "
            f"before rule={_rule_summary(before)}, after rule={_rule_summary(after)}"
        )
    losses = drift
    if losses:
        raise VikunjaError(
            f"companion fields changed by reschedule of task {task_id}: "
            f"{', '.join(losses)}; before {_task_summary(before)}; "
            f"after {_task_summary(after)}"
        )


def _vikunja_side_effects(
    record: dict, *, base_url: str, token: str
) -> tuple[list[str], str | None, str | None]:
    """Perform the Vikunja side-effects required by ``record["state"]``.

    Only ``done`` and ``rescheduled`` events produce a Vikunja side-effect
    (a v2 task PATCH, see the module docstring). The other states
    (``level_sent``, ``snoozed``, ``dismissed``) have JSONL append as their
    sole side-effect — see ``contracts/escalation-side-effects.contract.md``
    in mission ``remove-escalation-v1-parity-01KT4VTD``.

    Args:
        record: Validated escalation JSONL record dict.
        base_url: Vikunja API base URL (the configured ``/api/v1`` URL; the
            client derives the v2 root from it).
        token: Vikunja bearer token.

    Returns:
        ``(actions, outcome, anomaly)``. ``actions`` lists what was done, in
        order, e.g. ``["task_PATCH_done", "outcome:advanced"]`` for ``done``,
        ``["task_PATCH_due_date"]`` for ``rescheduled``, ``[]`` otherwise.
        ``outcome`` is the done outcome (else ``None``); ``anomaly`` is the
        ``unexpected`` summary (else ``None``).

    Raises:
        VikunjaError: On HTTP / network failure, or a reschedule that changed
            the rule. The JSONL write does NOT happen if this step raises.
    """
    state = record["state"]
    task_id = record["task_id"]
    actions: list[str] = []
    outcome: str | None = None
    anomaly: str | None = None

    if state == "done":
        outcome, anomaly = _done_side_effect(_client(base_url, token), task_id)
        actions.extend(["task_PATCH_done", f"outcome:{outcome}"])
    elif state == "rescheduled":
        _reschedule_side_effect(_client(base_url, token), task_id, record["reschedule_to"])
        actions.append("task_PATCH_due_date")

    return actions, outcome, anomaly


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def record_event(
    record: dict,
    *,
    base_url: Optional[str] = None,
    token_path: Optional[Path] = None,
    skip_vikunja: bool = False,
) -> dict:
    """Validate, run any Vikunja side-effect FIRST, then JSONL append SECOND.

    See module docstring for the full ordering contract and the per-state
    Vikunja side-effect table. For ``done``/``rescheduled`` events the Vikunja
    PATCH precedes the JSONL append; for ``level_sent``/``snoozed``/
    ``dismissed`` the JSONL append is the only side-effect.

    Args:
        record: Escalation JSONL record dict. Must satisfy both the Phase 2
            shared validator (``state_log_schema.validate_record``) and the
            escalation per-event_type validator
            (``escalation.schema.validate_event_params``).
        base_url: Vikunja API base URL. Default is the office2 Tailscale IP.
        token_path: Path to the felix-bot bearer token file (FR-010).
        skip_vikunja: When True, skip Step 1 (Vikunja side-effects). Used by
            reconcile to write synthetic records without re-sending alerts.
            Step 0 (validation) and Step 2 (JSONL append) still run.

    Returns:
        Dict ``{"ok": True, "jsonl_path": "<path>",
        "vikunja_actions": [...], "deduped": False}``, plus ``"outcome"``
        for a Vikunja ``done`` and ``"anomaly"`` when that outcome was
        ``unexpected`` (the JSONL record was still written, see the module
        docstring; the CLI then exits :data:`EXIT_OUTCOME_UNEXPECTED`).

    Raises:
        EscalationSchemaError: On validation failure (no writes attempted).
        VikunjaError: On Vikunja step failure (no JSONL write).
        StateLogError: On JSONL append failure (Vikunja already committed —
            operator triage).
    """
    base_url = base_url or get_vikunja_base_url()

    # Step 0: validation (Phase 2 shared + escalation per-event_type).
    # ``validate_record`` raises ``ValueError``; we re-route to the domain
    # exception for cleaner upstream try/except.
    try:
        _validate_shared_record(record, "escalation")
    except ValueError as exc:
        raise EscalationSchemaError(str(exc)) from exc
    validate_event_params(record)

    # Step 1: Vikunja side-effect (FIRST per research D6).
    vikunja_actions: list[str] = []
    outcome: str | None = None
    anomaly: str | None = None
    if not skip_vikunja:
        if token_path is None:
            token_path = get_vikunja_token_path()
        token = _read_token(token_path)
        vikunja_actions, outcome, anomaly = _vikunja_side_effects(
            record, base_url=base_url, token=token
        )

    if anomaly is not None:
        # Kent did say done: keep the record, and carry the anomaly in it.
        record = dict(record)
        existing = record.get("note")
        record["note"] = f"{anomaly}; {existing}" if existing else anomaly

    # Step 2: JSONL append (SECOND). On failure, raise StateLogError —
    # Vikunja already committed.
    path = _append_jsonl(record)

    result: dict[str, Any] = {
        "ok": True,
        "jsonl_path": str(path),
        "vikunja_actions": vikunja_actions,
        "deduped": False,
    }
    if outcome is not None:
        result["outcome"] = outcome
    if anomaly is not None:
        result["anomaly"] = anomaly
    return result


def idempotent_record_event(
    record: dict,
    *,
    base_url: Optional[str] = None,
    token_path: Optional[Path] = None,
    skip_vikunja: bool = False,
) -> dict:
    """Pre-check then ``record_event``. No-op on duplicate ``(task_id, date, state)``.

    The pre-check scans the per-project JSONL file for an existing record
    matching the tuple ``(task_id, date, state)``. If one is found, returns
    immediately with ``deduped=True`` and no Vikunja calls / no JSONL write.

    Args:
        record: Same as :func:`record_event`.
        base_url: Same as :func:`record_event`.
        token_path: Same as :func:`record_event`.
        skip_vikunja: Same as :func:`record_event`.

    Returns:
        Either the normal :func:`record_event` return dict OR
        ``{"ok": True, "jsonl_path": "<path>", "vikunja_actions": [],
        "deduped": True}`` on dedup hit.

    Raises:
        EscalationSchemaError: On validation failure (no writes attempted).
        VikunjaError: On Vikunja step failure (no JSONL write).
        StateLogError: On JSONL append failure (Vikunja already committed).
    """
    # Validation first — must run before any path inspection so a malformed
    # record never short-circuits to "deduped=True" silently.
    try:
        _validate_shared_record(record, "escalation")
    except ValueError as exc:
        raise EscalationSchemaError(str(exc)) from exc
    validate_event_params(record)

    path = _jsonl_path_for_record(record)
    if _idempotency_match(
        path, record["task_id"], record["date"], record["state"]
    ):
        return {
            "ok": True,
            "jsonl_path": str(path),
            "vikunja_actions": [],
            "deduped": True,
        }
    return record_event(
        record,
        base_url=base_url,
        token_path=token_path,
        skip_vikunja=skip_vikunja,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


_STATE_CHOICES = sorted(EVENT_TYPE_PARAMETERS.keys())
_SOURCE_CHOICES = (
    "agent",
    "reconcile",
    "backfill",
    "kent_reply",
    "operator_repair",
)


class _ArgparseError(Exception):
    """Raised by ``_StructuredArgumentParser`` when argparse hits a usage error.

    ``main()`` catches this and converts it to exit code 3 with a structured
    stderr line per ``contracts/cli.md`` (usage / validation errors). This
    keeps argparse's default ``SystemExit(2)`` path from leaking through.
    """


class _StructuredArgumentParser(argparse.ArgumentParser):
    """``ArgumentParser`` subclass that routes usage errors through exit 3.

    Default argparse calls ``sys.exit(2)`` from ``error()``. We instead raise
    ``_ArgparseError`` so ``main()`` can emit a structured JSON line on
    stderr and return ``3`` to conform to ``contracts/cli.md``. ``--help``
    still exits ``0`` because that path goes through ``exit()`` /
    ``_print_message`` rather than ``error()``.
    """

    def error(self, message: str) -> None:  # type: ignore[override]
        raise _ArgparseError(message)


def _build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser for ``python3 -m`` entry point."""
    parser = _StructuredArgumentParser(
        prog="python3 -m scripts.escalation.record_completion",
        description=(
            "Phase 6 escalation per-event side-effect dispatcher. "
            "Validate -> Vikunja v2 PATCH (only for done/rescheduled) -> "
            "JSONL append. Exits 0/1/2/3 per contracts/cli.md, 4 when a done "
            "had an unexpected Vikunja outcome (JSONL still written)."
        ),
    )
    parser.add_argument(
        "--task-id", type=int, help="Vikunja task id (required if no stdin)."
    )
    parser.add_argument(
        "--project-id",
        type=int,
        help="Vikunja project id (required if no stdin).",
    )
    parser.add_argument(
        "--title", help="Task title snapshot (required if no stdin)."
    )
    parser.add_argument(
        "--date",
        help="Local-TZ date of the event in YYYY-MM-DD (required if no stdin).",
    )
    parser.add_argument(
        "--state",
        choices=_STATE_CHOICES,
        help=(
            "Event state (required if no stdin). One of "
            f"{_STATE_CHOICES}."
        ),
    )
    parser.add_argument(
        "--source",
        choices=_SOURCE_CHOICES,
        help=(
            "Origin of the record (required if no stdin). One of "
            f"{list(_SOURCE_CHOICES)}."
        ),
    )
    parser.add_argument(
        "--level",
        type=int,
        help="Level (1 or 2) when --state level_sent.",
    )
    parser.add_argument(
        "--snooze-days",
        type=int,
        help="Snooze duration in days when --state snoozed.",
    )
    parser.add_argument(
        "--due-date",
        default=None,
        help=(
            "With --state level_sent: the task's current due_date as "
            "enumerate_candidates printed it. Stored as due_date_at_alert, the "
            "baseline reconcile uses to tell a recurring completion from a "
            "reschedule (FR-015). Optional; ignored for other states."
        ),
    )
    parser.add_argument(
        "--reschedule-to",
        help="New due date YYYY-MM-DD when --state rescheduled.",
    )
    parser.add_argument(
        "--reason",
        default=None,
        help="Optional free-text reason (dismissed / done).",
    )
    parser.add_argument(
        "--note",
        default=None,
        help="Optional free-text note (Phase 2 shared field).",
    )
    parser.add_argument(
        "--idempotent",
        action="store_true",
        help="Pre-check for duplicate (task_id, date, state); no-op on hit.",
    )
    parser.add_argument(
        "--no-vikunja",
        action="store_true",
        help=(
            "Skip the Vikunja side-effect step. Used by reconcile to write "
            "synthetic records without re-sending alerts."
        ),
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Vikunja API base URL (default: from VIKUNJA_BASE_URL env or config file).",
    )
    parser.add_argument(
        "--token-path",
        type=Path,
        default=None,
        help=(
            "Path to the Vikunja API token file (default: resolved via "
            "get_vikunja_token_path() — the kent-owned runtime credential)."
        ),
    )
    return parser


def _read_stdin_record() -> dict | None:
    """Read a JSON record from stdin if present; return None on empty stdin."""
    if sys.stdin.isatty():
        return None
    raw = sys.stdin.read().strip()
    if not raw:
        return None
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"stdin is not valid JSON: {exc}") from exc
    if not isinstance(obj, dict):
        raise ValueError(
            f"stdin record must be a JSON object (got {type(obj).__name__})"
        )
    return obj


def _build_record_from_flags(args: argparse.Namespace) -> dict:
    """Assemble a full record dict from CLI flags.

    Raises:
        ValueError: On missing required flags or per-state required-param
            omissions. The CLI surfaces these as exit code 3.
    """
    required = ("task_id", "project_id", "title", "date", "state", "source")
    missing = [
        f"--{name.replace('_', '-')}"
        for name in required
        if getattr(args, name) is None
    ]
    if missing:
        raise ValueError(
            "missing required argument(s): "
            + ", ".join(missing)
            + " (or pipe a JSON record on stdin)"
        )

    record: dict[str, Any] = {
        "domain": "escalation",
        "task_id": args.task_id,
        "project_id": args.project_id,
        "title": args.title,
        "date": args.date,
        "state": args.state,
        "source": args.source,
        "timestamp": _now_utc_iso(),
        "note": args.note,
    }

    # Per-state required parameters. argparse can't conditionally require
    # flags; we surface missing ones here as exit-code-3 errors.
    state = args.state
    if state == "level_sent":
        if args.level is None:
            raise ValueError(
                "--level is required when --state level_sent"
            )
        record["level"] = args.level
        due_at_alert = _due_date_at_alert(args.due_date)
        if due_at_alert is not None:
            record["due_date_at_alert"] = due_at_alert
    elif state == "snoozed":
        if args.snooze_days is None:
            raise ValueError(
                "--snooze-days is required when --state snoozed"
            )
        record["snooze_days"] = args.snooze_days
        # Per FR-004: compute snooze_until at write-time in local TZ.
        record["snooze_until"] = _compute_snooze_until(args.snooze_days)
    elif state == "rescheduled":
        if args.reschedule_to is None:
            raise ValueError(
                "--reschedule-to is required when --state rescheduled"
            )
        record["reschedule_to"] = args.reschedule_to
    # dismissed / done: no required params.

    if args.reason is not None:
        record["reason"] = args.reason

    return record


def _due_date_at_alert(value: str | None) -> str | None:
    """Return *value* when it is a usable Vikunja instant, else ``None``.

    The baseline is optional: an absent or unusable value (``None``, the
    year-1 "unset" sentinel, a naive or unparseable string) is dropped rather
    than failing the ``level_sent`` record, which matters more than the
    baseline. Reconcile then falls back to its pre-baseline behaviour.
    """
    if value is None or et_datetime.parse_vikunja_instant(value) is None:
        return None
    return value


def _augment_stdin_record(record: dict) -> dict:
    """Fill in defaults a CLI-side stdin record may omit (timestamp, snooze_until).

    Stdin records typically arrive missing the ``timestamp`` field; we mint
    one at the CLI boundary so the caller doesn't have to. For snoozed
    records missing ``snooze_until`` but carrying ``snooze_days``, we compute
    the local-TZ value here (FR-004 write-time).
    """
    out = dict(record)
    out.setdefault("domain", "escalation")
    out.setdefault("timestamp", _now_utc_iso())
    out.setdefault("note", None)
    if (
        out.get("state") == "snoozed"
        and "snooze_until" not in out
        and isinstance(out.get("snooze_days"), int)
    ):
        try:
            out["snooze_until"] = _compute_snooze_until(out["snooze_days"])
        except ValueError:
            # Leave it for the validator to reject with a clear message.
            pass
    return out


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Exit codes 0/1/2/3 per contracts/cli.md."""
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except _ArgparseError as exc:
        # argparse usage errors (unknown flags, bad enum values via choices,
        # invalid int types, etc.) must map to exit 3 per contracts/cli.md.
        print(
            json.dumps(
                {"ok": False, "step": "argparse", "error": str(exc)}
            ),
            file=sys.stderr,
        )
        return 3
    args.base_url = args.base_url or get_vikunja_base_url()

    # Resolve the record from stdin OR flags.
    try:
        stdin_record = _read_stdin_record()
    except ValueError as exc:
        print(
            json.dumps({"ok": False, "step": "stdin", "error": str(exc)}),
            file=sys.stderr,
        )
        return 3

    if stdin_record is not None:
        record = _augment_stdin_record(stdin_record)
    else:
        try:
            record = _build_record_from_flags(args)
        except ValueError as exc:
            print(
                json.dumps(
                    {"ok": False, "step": "argparse", "error": str(exc)}
                ),
                file=sys.stderr,
            )
            return 3

    func = idempotent_record_event if args.idempotent else record_event
    try:
        result = func(
            record,
            base_url=args.base_url,
            token_path=args.token_path,
            skip_vikunja=args.no_vikunja,
        )
    except EscalationSchemaError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "step": "validation",
                    "error": str(exc),
                }
            ),
            file=sys.stderr,
        )
        return 3
    except (FileNotFoundError, ValueError) as exc:
        # Token file missing (FileNotFoundError) or empty/whitespace-only
        # after strip (ValueError from ``_read_token``). Both are usage
        # failures per contracts/cli.md and must exit 3 with a structured
        # stderr line rather than bubbling up as an uncaught exception.
        print(
            json.dumps(
                {"ok": False, "step": "token_load", "error": str(exc)}
            ),
            file=sys.stderr,
        )
        return 3
    except VikunjaError as exc:
        print(
            json.dumps(
                {"ok": False, "step": "vikunja", "error": str(exc)}
            ),
            file=sys.stderr,
        )
        return 1
    except StateLogError as exc:
        print(
            json.dumps(
                {"ok": False, "step": "state_log", "error": str(exc)}
            ),
            file=sys.stderr,
        )
        return 2

    print(json.dumps(result))
    if result.get("anomaly"):
        # Written AFTER the JSONL append on purpose: the record is kept and
        # the agent still has to report the anomaly to Kent.
        print(
            json.dumps(
                {"ok": False, "step": "vikunja_outcome", "error": result["anomaly"]}
            ),
            file=sys.stderr,
        )
        return EXIT_OUTCOME_UNEXPECTED
    return 0


if __name__ == "__main__":
    sys.exit(main())
