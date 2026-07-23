#!/usr/bin/env python3
"""Deterministic orchestrator for felix-admin-calendar conversational requests.

Single deterministic entry point the ``felix-admin-calendar`` agent calls to
turn a natural-language calendar request (or a clarification reply) into a
Google Calendar event. The agent extracts natural-language fields and phrases
the reply; THIS module owns every date/time decision, the
create-vs-clarify-vs-ambiguous classification, and the side-effect
orchestration (create, record cleanup, note-flip, action logging).

Motivation (#836): the agent previously hand-built calendar payloads and got
dates/times wrong (e.g. dropping the clarification's original date, resolving
relative phrases against the wrong "now"). Moving the whole deterministic
transform here removes that fragility — the LLM never assembles a payload.

Invocation (MANDATORY ``-m`` form per [[feedback_helper_m_invocation_form]]):

    python3 -m scripts.calendar_routing.handle_calendar_request \
        --account <acct> [--state-file <path>] [--now-iso <iso8601>]

Reads an ``ExtractedCalendarBlock`` JSON object from **stdin**. Fields the
agent provides: ``title``, ``start_natural``, ``end_natural``,
``duration_natural``, ``location``, ``recurrence_natural``, ``attendees``,
``tick_iso`` (optional). There is NO ``source_inbox_path`` for conversational
requests (this module synthesizes one).

Emits a SINGLE JSON object on stdout and exits 0 for all non-crash outcomes
(the caller branches on ``status``). Exit 2 only on unreadable/empty/invalid
stdin JSON (or an unparseable ``--now-iso``).

Result-JSON contract (the agent prompt is written against these shapes):

  * created (conversational)::

        {"status": "created", "mode": "conversational",
         "event_id": ..., "html_link": ..., "summary": ...,
         "start": <rfc3339 or YYYY-MM-DD>}

    (The idempotent-hit keys described under the clarification shape below —
    ``idempotent`` / ``time_change_applied`` / ``requested_start`` / ``note`` —
    can also appear here: a same-key conversational retry idempotent-hits too,
    though for a retry the requested time equals the existing one, so no
    ``time_change_applied`` warning is added.)

  * created (clarification) — adds a best-effort ``cleanup`` block plus a
    top-level ``cleanup_ok`` (false => event created but the pending record /
    source note were not reconciled; the agent surfaces that to Kent)::

        {"status": "created", "mode": "clarification",
         "event_id": ..., "html_link": ..., "summary": ...,
         "start": <rfc3339 or YYYY-MM-DD>,
         "cleanup": {"record_removed": bool, "note_marked": bool},
         "cleanup_ok": bool}

    ``start`` is the calendar's ACTUAL event start. On an idempotent hit (#838)
    — the helper matched an EXISTING event for this clarification instead of
    creating a new one — the result also carries ``"idempotent": true``, and if
    the newly-requested start differed from the existing event's start it adds
    ``"time_change_applied": false``, ``"requested_start": <rfc3339>``, and a
    human ``"note"``. The event is NOT moved; the agent must report the actual
    ``start`` and, when ``time_change_applied`` is false, tell Kent the requested
    reschedule did not land (never confirm a time the calendar does not hold).

  * needs_clarification (conversational)::

        {"status": "needs_clarification", "mode": "conversational",
         "missing": [...]}

  * needs_clarification (clarification) — a matched record that still lacks
    fields after merging the reply::

        {"status": "needs_clarification", "mode": "clarification",
         "missing": [...], "note_filename": <record note_filename>}

  * ambiguous — the reply matched more than one live pending record::

        {"status": "ambiguous",
         "candidates": [{"title", "note_filename", "created_at"}, ...]}

  * error — the calendar helper failed (surfaced verbatim, NEVER faked #683;
    never falls back to gog)::

        {"status": "error", "exit_code": <n>, "error": <stderr verbatim>}

Classification algorithm (see ``_classify_and_run``):

  1. Parse the block; compute ``now_utc`` and the ET ``tick_iso``.
  2. ``live`` = pending records whose ``created_at`` is live (< 8h old).
  3. ``conv_block`` = the block + a synthetic ``source_inbox_path`` /
     ``source_block_index`` / ``tick_iso``; ``alone = validate(conv_block)``.
  4. ``matched`` live records: a block with NO title matches every live record
     (a terse reply carries nothing to disambiguate on); a block with a title
     matches a record iff one title's significant tokens are a subset of the
     other's (``_strong_match`` — not a single shared token).
  5. Branch — matching decides FIRST (a reply that strong-matches a pending
     record is a clarification even if it is self-sufficient, so a restated-
     complete reply resolves + cleans up instead of spawning a fresh orphan):
       - >1 match  -> AMBIGUOUS.
       - 1 match   -> CLARIFICATION: merge the reply over the record (reply wins
         per-component; the record supplies the missing date for start AND end),
         re-validate, create (+ best-effort cleanup) or re-ask.
       - 0 matches -> validate the block alone: complete -> CONVERSATIONAL
         create; incomplete -> CONVERSATIONAL needs_clarification.

Stdlib only (no requests/httpx/pydantic/PyYAML/frontmatter). Matches the style
of ``scripts/inbox/route_calendar_event.py``: external side effects go through
small module-level seam functions so unit tests can monkeypatch them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from scripts.calendar_routing.validate_calendar_event import (
    _parse_date_component,
    validate,
)
from scripts.inbox.handle_clarification_state import (
    STATE_PATH_DEFAULT,
    _is_live,
    _significant_tokens,
    load_state,
)

# The Eastern zone the validator anchors against (import the same string so a
# relative phrase resolves identically here and inside validate_calendar_event).
ET_ZONE = ZoneInfo("America/New_York")

# The agent whose actions this orchestrator logs.
AGENT = "felix-admin-calendar"

# Credential-set selector default for the direct-API calendar helper (D5,
# matches validate_calendar_event / route_calendar_event).
DEFAULT_ACCOUNT = "personal"

# The deterministic calendar helper (WP02) invoked to create the event. Kept as
# module-level constants so tests can monkeypatch the subprocess call site.
CALENDAR_HELPER_MODULE = "scripts.google.calendar_helper"

# Subprocess timeouts (seconds). A blocked Google API call or a stuck
# mark_processed must fail cleanly rather than hang until openclaw's 600s cron
# limit kills the turn.
CALENDAR_HELPER_TIMEOUT_SECONDS = 90
STATE_HELPER_TIMEOUT_SECONDS = 30
MARK_PROCESSED_TIMEOUT_SECONDS = 30
LOG_ACTION_TIMEOUT_SECONDS = 15
_TIMEOUT_RETURNCODE = 124  # conventional timeout exit code

# The calendar helper's Google client libraries live ONLY in a dedicated venv on
# office2 (system python3 has neither pip nor the google libs). The helper MUST
# be invoked with that venv's interpreter — NOT ``sys.executable`` (this module
# runs under the system python3, which would crash on ``import googleapiclient``).
# Overridable for local/dev via FELIX_CALENDAR_HELPER_PYTHON.
DEFAULT_CALENDAR_HELPER_PYTHON = "/data/services/openclaw/felix-calendar/venv/bin/python"

# log_action.py uses the script-path import convention (a bare ``from config
# import ObservationConfig``), so it MUST be invoked by absolute script path —
# NOT ``-m scripts.openclaw.observation.log_action`` (which raises
# ``ModuleNotFoundError: No module named 'config'`` because the observation dir
# is not on sys.path under ``-m``). Every other Felix agent invokes it this way.
# Resolved from this module's location so it is cwd-independent.
_REPO_ROOT = Path(__file__).resolve().parents[2]
LOG_ACTION_SCRIPT = str(_REPO_ROOT / "scripts/openclaw/observation/log_action.py")


def _calendar_helper_python() -> str:
    """Return the interpreter used to run the calendar helper subprocess."""
    import os

    return os.environ.get("FELIX_CALENDAR_HELPER_PYTHON", DEFAULT_CALENDAR_HELPER_PYTHON)


# ---------------------------------------------------------------------------
# Seams — every external side effect goes through one of these so the unit
# tests can monkeypatch a single call site (mirrors route_calendar_event).
# ---------------------------------------------------------------------------


def _parse_helper_created(stdout: str) -> Optional[dict]:
    """Extract the helper's ``status: created`` JSON line from its stdout.

    The helper emits a JSON object line *before* its final ``SUMMARY:`` line
    (contract: JSON never follows SUMMARY). Return the first line that parses to
    a dict carrying ``status == "created"``, or ``None``.
    """
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and obj.get("status") == "created":
            return obj
    return None


def _invoke_calendar_helper(
    payload: dict, idempotency_key: str, account: str
) -> dict:
    """Create the event via the calendar helper; return a normalized result dict.

    ``payload`` is the already-built ``calendar_event_payload`` from ``validate``
    (the exact shape ``calendar_helper create --payload-file`` consumes) — it is
    written verbatim to a tempfile; NO envelope is rebuilt around it. Runs::

        python3 -m scripts.google.calendar_helper create --payload-file <tmp>
            --idempotency-key <idempotency_key> --account <account> --json

    Returns ``{"status": "created", "event_id", "html_link"}`` on success or
    ``{"status": "error", "exit_code", "error"}`` on any failure (non-zero exit,
    timeout, or exit-0-without-a-parseable-created-line). The error is surfaced
    verbatim and NEVER faked (#683).

    This is the single seam the unit tests monkeypatch (the real helper needs the
    google client libraries + a live token, which never run under CI).
    """
    fd, tmp_name = tempfile.mkstemp(prefix="calendar-payload.", suffix=".json")
    try:
        with open(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        try:
            proc = subprocess.run(
                [
                    _calendar_helper_python(),
                    "-m",
                    CALENDAR_HELPER_MODULE,
                    "create",
                    "--payload-file",
                    tmp_name,
                    "--idempotency-key",
                    idempotency_key,
                    "--account",
                    account,
                    "--json",
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=CALENDAR_HELPER_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return {
                "status": "error",
                "exit_code": _TIMEOUT_RETURNCODE,
                "error": (
                    "ERROR: calendar helper timed out after "
                    f"{CALENDAR_HELPER_TIMEOUT_SECONDS}s"
                ),
            }
        except OSError as exc:
            # Missing / non-executable venv python (or any launch-level failure):
            # must never traceback — that would violate the single-JSON contract.
            return {
                "status": "error",
                "exit_code": _TIMEOUT_RETURNCODE,
                "error": f"ERROR: calendar helper launch failed: {exc}",
            }
    finally:
        try:
            Path(tmp_name).unlink()
        except OSError:  # pragma: no cover - cleanup best-effort
            pass

    if proc.returncode == 0:
        created = _parse_helper_created(proc.stdout)
        if created is not None:
            return {
                "status": "created",
                "event_id": created.get("event_id", ""),
                "html_link": created.get("html_link", ""),
                # #838: carry the helper's idempotent flag and the event's ACTUAL
                # start through the seam so the orchestrator can report the
                # calendar's real time on an idempotent hit (never the merely
                # -requested one). Absent on an old helper → benign defaults.
                "idempotent": bool(created.get("idempotent", False)),
                "actual_start": created.get("start", ""),
            }
        # Exit 0 but no parseable created line — treat as an error rather than
        # fabricate a success (#683).
        return {
            "status": "error",
            "exit_code": 0,
            "error": (proc.stdout or proc.stderr).strip(),
        }
    return {
        "status": "error",
        "exit_code": proc.returncode,
        "error": (proc.stderr or proc.stdout).strip(),
    }


def _invoke_remove_record(note_filename: str, state_file: Optional[str]) -> bool:
    """Remove a resolved clarification record via handle_clarification_state.

    Deliberately a subprocess (``python3 -m
    scripts.inbox.handle_clarification_state remove --note-filename <n>
    --state-file <p>``) rather than an in-process call, so its stdout
    (``removed=N``) stays isolated from this module's single-result-JSON
    contract — the same isolation philosophy route_calendar_event uses for
    mark_processed. stdlib-only, so ``sys.executable`` is correct. Returns True
    on a clean exit; best-effort (the event already exists), never raises.
    """
    args = [
        sys.executable,
        "-m",
        "scripts.inbox.handle_clarification_state",
        "remove",
        "--note-filename",
        note_filename,
    ]
    if state_file:
        args += ["--state-file", state_file]
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            check=False,
            timeout=STATE_HELPER_TIMEOUT_SECONDS,
        )
        return proc.returncode == 0
    except (subprocess.TimeoutExpired, OSError):  # pragma: no cover - best-effort
        return False


def _invoke_mark_processed(source_path: str) -> bool:
    """Flip the source note to processed via mark_processed (subprocess seam).

    Subprocess (``python3 -m scripts.inbox.mark_processed --path <source_path>``)
    not an in-process import: the inbox-root validation and
    symlink ``.resolve()`` guard all live in ``mark_processed.main()``. stdlib-only,
    so ``sys.executable`` is correct. Returns True on a clean exit; best-effort,
    never raises (the event already exists).
    """
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "scripts.inbox.mark_processed", "--path", source_path],
            capture_output=True,
            text=True,
            check=False,
            timeout=MARK_PROCESSED_TIMEOUT_SECONDS,
        )
        return proc.returncode == 0
    except (subprocess.TimeoutExpired, OSError):  # pragma: no cover - best-effort
        return False


def _invoke_log_action(
    agent: str,
    category: str,
    action: str,
    target: str,
    outcome: str,
    context: dict,
) -> None:
    """Emit one observation log entry (best-effort; never blocks the result).

    Shells out ``log_action.py`` (by absolute script path — see
    ``LOG_ACTION_SCRIPT``) with the given fields. Any failure (non-zero exit,
    timeout, unimportable config) is swallowed — logging is observability, not
    part of the create contract.
    """
    try:
        subprocess.run(
            [
                sys.executable,
                LOG_ACTION_SCRIPT,
                "--agent",
                agent,
                "--category",
                category,
                "--action",
                action,
                "--target",
                target,
                "--outcome",
                outcome,
                "--context",
                json.dumps(context),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=LOG_ACTION_TIMEOUT_SECONDS,
        )
    except Exception:  # noqa: BLE001 - best-effort; logging must never block
        pass


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _parse_now(now_iso: Optional[str]) -> datetime:
    """Return an aware UTC datetime for "now".

    ``--now-iso`` overrides the wall clock for deterministic tests. A naive
    value is assumed UTC. Raises ``ValueError`` on an unparseable string.
    """
    if not now_iso or not now_iso.strip():
        return datetime.now(timezone.utc)
    text = now_iso.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _et_iso(now_utc: datetime) -> str:
    """Render ``now_utc`` as an ET-localized ISO 8601 string (validator anchor)."""
    return now_utc.astimezone(ET_ZONE).isoformat()


def _nonempty(value: object) -> bool:
    """True when ``value`` is a meaningful (non-null / non-blank) field."""
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def _block_title(block: dict) -> Optional[str]:
    """Return the block's stripped title, or None when absent/blank."""
    title = block.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip()
    return None


def _strong_match(record_title: object, block_title: object) -> bool:
    """True when one title's significant tokens are a subset of the other's.

    Replaces loose single-shared-token binding (which mis-bound "Lunch with
    Sarah" onto a pending "Lunch with John" via the shared "lunch"). A subset
    relation requires the whole of the shorter title to appear in the longer —
    "Dentist" ⊆ "Dentist appointment" binds; "…John" vs "…Sarah" does not.
    """
    rt = set(_significant_tokens(record_title if isinstance(record_title, str) else ""))
    bt = set(_significant_tokens(block_title if isinstance(block_title, str) else ""))
    if not rt or not bt:
        return False
    return rt <= bt or bt <= rt


def _matched_records(block: dict, live: list) -> list:
    """Return the live records the block could be a clarification reply to.

    - Block with NO non-empty title -> every live record is a candidate (a terse
      reply like "2pm" carries no title to disambiguate on).
    - Block with a title -> a record matches iff ``_strong_match`` holds (one
      title's significant tokens are contained in the other's).
    """
    title = _block_title(block)
    if title is None:
        return list(live)
    out: list = []
    for rec in live:
        rec_title = (rec.get("partial_payload") or {}).get("title")
        if _strong_match(rec_title, title):
            out.append(rec)
    return out


def _merge_temporal(
    reply_value: object, record_value: object, date_source: object, anchor: datetime
) -> Optional[str]:
    """Component-merge a reply's temporal field over a record's, keeping the date.

    A blind field overwrite would drop the record's date when the reply supplies
    only a time — exactly the #836 bug (and its end-only sibling, MED-1). So:

    - reply blank            -> keep the record's value.
    - reply carries a date   -> reply wins outright (it is self-sufficient).
    - reply has NO date but ``date_source`` does -> combine "``<reply>
      <date_source>``" so the date is inherited while the reply supplies (and,
      being first, wins) the time-of-day.

    For ``start_natural`` the ``date_source`` is the record's own start; for
    ``end_natural`` it is the record's start too (an end-only reply inherits the
    event's date). Example: record start "July 25", reply "2pm" -> "2pm July 25"
    -> July 25 14:00; record start "Thursday", reply end "3pm" -> "3pm Thursday".
    """
    rep = reply_value if isinstance(reply_value, str) and reply_value.strip() else None
    rec = record_value if isinstance(record_value, str) and record_value.strip() else None
    if rep is None:
        return rec
    if _parse_date_component(rep, anchor) is not None:
        return rep
    ds = date_source if isinstance(date_source, str) and date_source.strip() else None
    if ds is not None and _parse_date_component(ds, anchor) is not None:
        return f"{rep} {ds}"
    return rep


def _build_merged(rec: dict, block: dict, et_now_iso: str) -> tuple[dict, str]:
    """Build the merged ExtractedCalendarBlock for a clarification reply.

    Base = the record's ``partial_payload``; every non-empty field of the reply
    overlays it (reply wins). ``start_natural`` and ``end_natural`` are merged at
    component granularity (see :func:`_merge_temporal`). ``source_inbox_path`` /
    ``source_block_index`` are forced from the record; ``tick_iso`` is set to now
    (inbound receipt — relative phrases resolve against now). Returns
    ``(merged_block, source_path)``.
    """
    base = dict(rec.get("partial_payload") or {})
    merged = dict(base)
    for key, value in block.items():
        if key in (
            "source_inbox_path",
            "source_block_index",
            "tick_iso",
            "start_natural",
            "end_natural",
        ):
            continue
        if _nonempty(value):
            merged[key] = value

    try:
        anchor = datetime.fromisoformat(et_now_iso)
    except ValueError:  # pragma: no cover - _et_iso always emits a parseable value
        anchor = datetime.now(ET_ZONE)
    # The record's start is the date-bearing field; both start and end inherit
    # its date when the reply gives only a time.
    date_source = base.get("start_natural")
    merged_start = _merge_temporal(
        block.get("start_natural"), base.get("start_natural"), date_source, anchor
    )
    if merged_start is not None:
        merged["start_natural"] = merged_start
    merged_end = _merge_temporal(
        block.get("end_natural"), base.get("end_natural"), date_source, anchor
    )
    if merged_end is not None:
        merged["end_natural"] = merged_end

    source_path = base.get("source_inbox_path") or rec.get("note_filename") or ""
    merged["source_inbox_path"] = source_path
    merged["source_block_index"] = base.get("source_block_index", 0)
    merged["tick_iso"] = et_now_iso
    return merged, str(source_path)


def _candidate(rec: dict) -> dict:
    """Project a live record into the ambiguous-result candidate shape."""
    return {
        "title": (rec.get("partial_payload") or {}).get("title"),
        "note_filename": rec.get("note_filename"),
        "created_at": rec.get("created_at"),
    }


def _payload_start(payload: dict) -> str:
    """Return the timed RFC3339 start, or the all-day date, for the result."""
    return payload.get("start_rfc3339") or payload.get("start_date") or ""


def _conversational_key(block: dict, tick_iso: str) -> str:
    """Idempotency key for a conversational create: stable per request, distinct
    across distinct requests.

    ``conversational-{tick_iso}-{h}`` where ``h`` is the first 8 hex of the SHA-1
    of the content-normalized block. Same content + same tick -> same key (a
    retry never double-creates); different content in the same second -> a
    different key (no collision between two distinct requests, MED-2).
    """
    digest = hashlib.sha1(
        json.dumps(block, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:8]
    return f"conversational-{tick_iso}-{digest}"


# ---------------------------------------------------------------------------
# Create + orchestration
# ---------------------------------------------------------------------------


def _create_from_payload(
    payload: dict,
    idempotency_key: str,
    account: str,
    mode: str,
    *,
    record: Optional[dict] = None,
    source_path: Optional[str] = None,
    state_file: Optional[str] = None,
) -> dict:
    """Create the event and (for clarifications) run best-effort cleanup.

    On helper failure: log ``calendar_event_failed`` and return the error dict
    verbatim (never faked #683; no record removed, no note marked). On success:
    log ``calendar_event_created`` and, for a clarification, remove the record +
    mark the source note + log ``calendar_event_clarification_resolved`` (all
    best-effort — the event already exists — with their outcome reported in the
    ``cleanup`` block).
    """
    summary = payload.get("summary", "")
    requested_start = _payload_start(payload)

    create_result = _invoke_calendar_helper(payload, idempotency_key, account)
    if create_result.get("status") != "created":
        _invoke_log_action(
            AGENT,
            "error",
            "calendar_event_failed",
            summary or idempotency_key,
            "error",
            {"mode": mode, "error": create_result.get("error", "")},
        )
        return {
            "status": "error",
            "exit_code": create_result.get("exit_code"),
            "error": create_result.get("error", ""),
        }

    event_id = create_result.get("event_id", "")
    html_link = create_result.get("html_link", "")
    idempotent = bool(create_result.get("idempotent", False))
    actual_start = create_result.get("actual_start", "")
    # #838: on an idempotent hit the helper returned an EXISTING event whose time
    # may differ from what this reply just requested (the calendar was NOT moved).
    # Report the calendar's ACTUAL start in that case — never the merely-requested
    # time. A fresh (non-idempotent) create holds exactly the requested time, so
    # keep reporting the requested value there (no behavior change — criterion #3).
    reported_start = actual_start if (idempotent and actual_start) else requested_start
    result: dict = {
        "status": "created",
        "mode": mode,
        "event_id": event_id,
        "html_link": html_link,
        "summary": summary,
        "start": reported_start,
    }
    if idempotent:
        result["idempotent"] = True
        if not actual_start:
            # Defensive (renata #838 Finding 2): an idempotent match whose actual
            # start the helper did not surface (should not happen with the
            # lockstep helper, and a Google event without a start is effectively
            # impossible). Rather than silently confirm the merely-requested time,
            # flag it so the agent tells Kent to verify the calendar.
            result["note"] = (
                "This clarification matched an existing calendar event, but its "
                "actual start could not be confirmed from the helper response — "
                "verify the event time on the calendar before treating it as set."
            )
        elif requested_start and requested_start != actual_start:
            # The newly-requested time differs from the existing event's time, so
            # this idempotent match did NOT change the calendar. Surface it
            # explicitly so the agent never confirms a reschedule that didn't land
            # (#838 — never silently confirm a time the calendar does not hold). We
            # deliberately do NOT auto-move the event (the success criteria
            # sanction "clearly states it did not"): the re-reply is reported
            # honestly and the operator can issue an explicit reschedule.
            # NOTE: this is a raw string compare of the payload's RFC3339 against
            # Google's stored dateTime; the helper always emits offset-form
            # dateTime that Google preserves identically, so a false "not applied"
            # would require differently-spelled equal instants — and even then the
            # direction is safe (we still report the true `start`), just an
            # over-warn (renata #838 Finding 3).
            result["time_change_applied"] = False
            result["requested_start"] = requested_start
            result["note"] = (
                f"An event for this clarification already exists at {actual_start}; "
                f"the newly-requested start {requested_start} was NOT applied "
                f"(idempotent match). The calendar still holds {actual_start} — "
                f"issue an explicit reschedule to move it."
            )
    _invoke_log_action(
        AGENT,
        "routine",
        "calendar_event_created",
        summary or event_id,
        "created",
        {"mode": mode, "event_id": event_id, "idempotent": idempotent},
    )

    if mode == "clarification":
        note_filename = (record or {}).get("note_filename", "")
        record_removed = _invoke_remove_record(note_filename, state_file)
        if not record_removed:
            # Retry the removal once — a transient state-file contention should
            # not strand the record (and leave a resolved clarification re-asking).
            record_removed = _invoke_remove_record(note_filename, state_file)
        note_marked = _invoke_mark_processed(source_path) if source_path else False
        cleanup_ok = record_removed and note_marked
        _invoke_log_action(
            AGENT,
            "routine",
            "calendar_event_clarification_resolved",
            note_filename or event_id,
            "resolved",
            {"event_id": event_id, "clarification_id": note_filename},
        )
        result["cleanup"] = {
            "record_removed": record_removed,
            "note_marked": note_marked,
        }
        # Surfaced so the agent can tell Kent when cleanup silently failed (the
        # event exists but the record/note weren't reconciled). Status stays
        # "created" — the event DID get created.
        result["cleanup_ok"] = cleanup_ok

    return result


def _classify_and_run(
    block: dict, now_utc: datetime, state_path: Path, account: str
) -> dict:
    """Classify the request and run the matching branch. Returns the result dict."""
    et_now_iso = _et_iso(now_utc)
    block_tick = block.get("tick_iso")
    tick_iso = (
        block_tick
        if isinstance(block_tick, str) and block_tick.strip()
        else et_now_iso
    )

    live = [r for r in load_state(state_path) if _is_live(r.get("created_at"), now_utc)]

    # Matching decides FIRST — a reply that strong-matches a pending record is a
    # clarification even when it happens to be self-sufficient (a restated-complete
    # reply must resolve + clean up the record, not spawn a fresh orphan). Only
    # when NO record matches does alone-completeness pick conversational
    # create-vs-clarify.
    matched = _matched_records(block, live)

    if len(matched) > 1:
        return {
            "status": "ambiguous",
            "candidates": [_candidate(r) for r in matched],
        }

    if len(matched) == 1:
        rec = matched[0]
        merged, source_path = _build_merged(rec, block, et_now_iso)
        mval = validate(merged)
        if mval.get("complete"):
            return _create_from_payload(
                mval["calendar_event_payload"],
                source_path,
                account,
                "clarification",
                record=rec,
                source_path=source_path,
                state_file=str(state_path),
            )
        return {
            "status": "needs_clarification",
            "mode": "clarification",
            "missing": mval.get("missing_fields", []),
            "note_filename": rec.get("note_filename"),
        }

    # No pending record matched — a purely conversational request.
    conv_block = dict(block)
    conv_block["source_inbox_path"] = f"conversational-{tick_iso}"
    conv_block["source_block_index"] = 0
    conv_block["tick_iso"] = tick_iso
    alone = validate(conv_block)

    if alone.get("complete"):
        return _create_from_payload(
            alone["calendar_event_payload"],
            _conversational_key(block, tick_iso),
            account,
            "conversational",
        )

    return {
        "status": "needs_clarification",
        "mode": "conversational",
        "missing": alone.get("missing_fields", []),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="handle_calendar_request",
        description=(
            "Deterministic orchestrator: classify a conversational calendar "
            "request (or clarification reply) read from stdin and create the "
            "event / ask for clarification / report ambiguity."
        ),
    )
    parser.add_argument(
        "--account",
        default=DEFAULT_ACCOUNT,
        help=(
            "Credential-set selector passed through to the calendar helper "
            f"(default {DEFAULT_ACCOUNT!r})."
        ),
    )
    parser.add_argument(
        "--state-file",
        default=str(STATE_PATH_DEFAULT),
        help=(
            "Path to the pending-clarification JSON state file. Defaults to "
            f"{STATE_PATH_DEFAULT}."
        ),
    )
    parser.add_argument(
        "--now-iso",
        default=None,
        help=(
            "Override 'now' (ISO 8601, aware or naive-UTC) for deterministic "
            "tests. Defaults to the current UTC time."
        ),
    )
    args = parser.parse_args(argv)

    raw = sys.stdin.read()
    if not raw.strip():
        sys.stderr.write("INVALID_INPUT_JSON: empty stdin\n")
        return 2
    try:
        block = json.loads(raw)
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"INVALID_INPUT_JSON: {exc}\n")
        return 2
    if not isinstance(block, dict):
        sys.stderr.write("INVALID_INPUT_JSON: top-level value is not a JSON object\n")
        return 2

    try:
        now_utc = _parse_now(args.now_iso)
    except ValueError as exc:
        sys.stderr.write(f"INVALID_NOW_ISO: {exc}\n")
        return 2

    result = _classify_and_run(block, now_utc, Path(args.state_file), args.account)
    sys.stdout.write(json.dumps(result) + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
