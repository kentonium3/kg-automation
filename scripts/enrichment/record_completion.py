#!/usr/bin/env python3
"""ADR-0002 Phase 7 ``record_completion`` for the enrichment domain.

The atomic three-write helper every live enrichment event flows through:

    Step 0: Validate the candidate record via
            :func:`scripts.enrichment.schema.validate_record`. Raises
            :class:`EnrichmentSchemaError` on failure BEFORE any side-effects.

    Step 1 (Vikunja side-effect, FIRST):
        PUT ``/tasks/{task_id}/comments`` with the v1 ``[Felix] enrichment``
        comment body — the visible-in-Vikunja signal that's already wired
        through the deployed AGENTS.md. Authenticated as ``felix-bot`` (FR-010
        analog) via the bearer token loaded from ``token_path``. On any
        HTTP/network failure raise :class:`VikunjaError`. No JSONL write
        happens; the CLI surfaces this as exit code 1.

    Step 2 (JSONL append, SECOND):
        Append the record to the single-file ledger at
        ``/data/services/openclaw/state/enrichment/enrichment-history.jsonl``
        using an fcntl-locked append-then-flush-then-fsync pattern. On I/O
        failure raise :class:`StateLogError`. Per FR-013 (Q10 soft-fail
        policy): the CLI logs a warning and returns exit code 0 — the
        Vikunja state is consistent, JSONL is recoverable via reconcile.

    Step 3 (ack log, THIRD, best-effort):
        Append a one-line activity log entry to the operator-readable
        per-day file under ``~/second-brain/agents/logs/``. Failures here
        are silently swallowed; the JSONL row is the authoritative record.

Ordering is non-negotiable. Vikunja is the unreliable remote; failing there
first surfaces the network problem before any state_log line is written.
Vikunja state is what Kent sees in the UI; the JSONL is canonical for our
derived state walk.

C-002 parity (soak): every enrichment state transition continues writing
the ``[Felix] enrichment | <state> | <ISO timestamp>`` comment as Step 1.
``derive_state`` (WP02) reads ONLY the JSONL — the comment is a write-only
mirror during the 3-day soak. A v2 follow-on removes the comment write.

CLI surface — see ``contracts/cli.md``. Exit codes:

    0 — success (three writes done OR idempotent no-op OR soft-fail
        per FR-013 with JSONL warning logged)
    1 — Vikunja step failure (no JSONL write)
    3 — validation / usage error

Note on exit code 2: ``contracts/cli.md`` reserves exit 2 for "JSONL
append error". FR-013 (the Q10 soft-fail policy) supersedes that for the
post-Vikunja JSONL failure case — we exit 0 with a logged warning rather
than failing hard, because the Vikunja state is consistent and re-proposing
on the next cycle is annoying but harmless. Pre-Vikunja JSONL failures
(idempotent pre-check I/O errors) still surface as exit 2 because no
side-effect has landed and the operator can re-run cleanly.

Design references:
    - kitty-specs/tasker-jsonl-migration-01KSB5XV/spec.md
        FR-001..FR-005, FR-013, FR-015, NFR-006
    - kitty-specs/tasker-jsonl-migration-01KSB5XV/contracts/cli.md
        flag set + exit code semantics
    - kitty-specs/tasker-jsonl-migration-01KSB5XV/data-model.md
        E1 (JSONL record shape), comment vocabulary
    - scripts/escalation/record_completion.py
        Pattern source (three-write contract, HTTP wrapper, atomic JSONL)
"""
from __future__ import annotations

import argparse
import fcntl
import json
import logging
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from scripts.enrichment.schema import (
    DEFAULT_LEDGER_PATH,
    SCHEMA_VERSION,
    VALID_SOURCES,
    VALID_STATES,
    EnrichmentCompletion,
    EnrichmentSchemaError,
    validate_record,
)


__all__ = [
    "ACTIVITY_LOG_DIR",
    "DEFAULT_BASE_URL",
    "DEFAULT_LEDGER_PATH",
    "DEFAULT_TOKEN_PATH",
    "HTTP_TIMEOUT_SECONDS",
    "EnrichmentSchemaError",
    "StateLogError",
    "VikunjaError",
    "main",
    "record",
    "record_event",
]


# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

#: Default Vikunja API base URL. Tailscale IP keeps this resolvable without
#: DNS even when the office2 hostname is unavailable.
DEFAULT_BASE_URL: str = "http://100.92.197.90:3456/api/v1/"

#: Default location of the ``felix-bot`` Vikunja API token on office2.
DEFAULT_TOKEN_PATH: Path = Path("/data/services/openclaw/secrets/vikunja-api")

#: HTTP socket timeout in seconds for every Vikunja API call.
HTTP_TIMEOUT_SECONDS: int = 30

#: Operator-readable activity log directory. Mirrors the pattern habits +
#: escalation use; one file per day keeps grep-by-date trivial.
ACTIVITY_LOG_DIR: Path = (
    Path.home() / "second-brain" / "agents" / "logs" / "enrichment"
)

#: File mode for the JSONL ledger (rw-rw-r--).
_STATE_FILE_MODE: int = 0o664

#: Logger used for soft-fail warnings (FR-013). Library code emits the
#: warning; the CLI surface mirrors it to stderr so an operator running
#: the helper interactively sees the message immediately.
_LOG = logging.getLogger("enrichment.record_completion")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class VikunjaError(Exception):
    """Raised when the Vikunja side-effect step (HTTP) fails.

    The message names the failed sub-step (``PUT comment``) and includes
    the HTTP status code / network error so the operator can triage
    quickly. No JSONL line is written when this is raised; callers
    surface exit code 1.
    """


class StateLogError(Exception):
    """Raised when the JSONL append step fails.

    Two surfaces:

    1. Post-Vikunja: caller catches this and applies the FR-013 soft-fail
       policy (log warning, exit 0).
    2. Pre-Vikunja (idempotent pre-check I/O error): caller surfaces as
       exit code 2 — nothing has been committed downstream and the operator
       can re-run cleanly.
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
# HTTP helper
# ---------------------------------------------------------------------------


def _join_url(base: str, path: str) -> str:
    """Join a base URL and a path, tolerating missing/extra slashes."""
    if not base.endswith("/"):
        base = base + "/"
    return base + path.lstrip("/")


def _http_request(
    method: str,
    url: str,
    token: str,
    body: dict | None = None,
) -> tuple[int, Any]:
    """Issue an authenticated HTTP request via urllib.

    Args:
        method: ``GET`` / ``POST`` / ``PUT`` / ``PATCH`` / ``DELETE``.
        url: Fully qualified URL.
        token: Vikunja bearer token (felix-bot).
        body: Optional dict — serialized to JSON if present.

    Returns:
        Tuple ``(status_code, parsed_json_or_none)``.

    Raises:
        VikunjaError: On HTTP-status-error or network failure. Message
            includes ``method url`` + status + server error body when
            available.
    """
    data: bytes | None = None
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(
        url, data=data, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(
            req, timeout=HTTP_TIMEOUT_SECONDS
        ) as resp:
            status = resp.status
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        try:
            err_body = exc.read().decode("utf-8", errors="replace")
        except Exception:  # pragma: no cover — purely defensive
            err_body = ""
        raise VikunjaError(
            f"{method} {url} failed with HTTP {exc.code}: {err_body!r}"
        ) from exc
    except urllib.error.URLError as exc:
        raise VikunjaError(
            f"{method} {url} network failure: {exc}"
        ) from exc

    if status < 200 or status >= 300:
        raise VikunjaError(
            f"{method} {url} returned HTTP {status}: {raw!r}"
        )

    parsed: Any = None
    if raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            # Comment-create may return non-JSON; tolerate.
            parsed = None
    return status, parsed


# ---------------------------------------------------------------------------
# Clock helpers
# ---------------------------------------------------------------------------


def _now_utc_iso() -> str:
    """Current UTC instant as ISO-8601 with ``Z`` suffix.

    Exposed as a module function so tests can monkeypatch deterministically.
    The ``Z`` suffix matches the deployed AGENTS.md comment vocabulary
    (``[Felix] enrichment | <state> | 2026-05-23T19:00:00Z``).
    """
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    )


# ---------------------------------------------------------------------------
# v1 [Felix] enrichment comment formatter
# ---------------------------------------------------------------------------

#: Prefix + delimiter mirror the deployed tasker AGENTS.md vocabulary
#: verbatim (verified during #310 spec-readiness). Round-trip-able by the
#: reconcile parser (WP02).
_COMMENT_PREFIX = "[Felix] enrichment"
_COMMENT_DELIMITER = " | "


def _format_v1_comment(record_dict: dict) -> str:
    """Build the v1 ``[Felix] enrichment`` comment body for ``record_dict``.

    Per data-model.md and deployed tasker AGENTS.md vocabulary:

    | record state    | comment body                                     |
    |-----------------|--------------------------------------------------|
    | ``proposed``    | ``[Felix] enrichment | proposed | <ISO Z>``      |
    | ``confirmed``   | ``[Felix] enrichment | confirmed | <ISO Z>``     |
    | ``skipped``     | ``[Felix] enrichment | skipped | <ISO Z>``       |
    | ``declined``    | ``[Felix] enrichment | declined | <ISO Z>``      |

    If a ``note`` is present, it's appended as the fourth ``|``-delimited
    field (preserving the deployed AGENTS.md "optional notes" pattern).

    Args:
        record_dict: Validated enrichment record dict.

    Returns:
        Comment body string, ready to PUT to ``/tasks/{id}/comments``.
    """
    state = record_dict["state"]
    timestamp = record_dict["timestamp_utc"]
    body = (
        f"{_COMMENT_PREFIX}"
        f"{_COMMENT_DELIMITER}{state}"
        f"{_COMMENT_DELIMITER}{timestamp}"
    )
    note = record_dict.get("note")
    if note:
        body += f"{_COMMENT_DELIMITER}{note}"
    return body


# ---------------------------------------------------------------------------
# JSONL append (single-file, fcntl-locked)
# ---------------------------------------------------------------------------


def _idempotency_match(
    file_path: Path, task_id: int, state: str
) -> bool:
    """Return True if a record matching ``(task_id, state)`` already exists.

    Per spec FR-004: idempotency key is ``(task_id, state)``. Once a task
    has been recorded in a given state, further attempts to record the
    same state are a no-op (single-offer policy: terminal states never
    re-propose; same-state-rewrite is a duplicate).

    Tolerates malformed lines (skipped silently) so a partial last line
    from a crashed write does not poison the dedup check.
    """
    if not file_path.exists():
        return False
    target = (task_id, state)
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
                existing = (obj["task_id"], obj["state"])
            except (KeyError, TypeError):
                continue
            if existing == target:
                return True
    return False


def _append_jsonl(record_dict: dict, ledger_path: Path) -> Path:
    """Atomically append ``record_dict`` to the JSONL ledger.

    Uses ``fcntl.LOCK_EX`` across the read-check-write critical section.
    The file is created with mode 0o664 on first write; the parent
    directory is created if missing.

    On any I/O error raises :class:`StateLogError`. Caller decides whether
    to apply the FR-013 soft-fail policy (post-Vikunja) or hard-fail
    (pre-Vikunja idempotent pre-check).

    Args:
        record_dict: Enrichment record dict (already validated).
        ledger_path: Path to the JSONL ledger.

    Returns:
        The absolute path of the file written to.

    Raises:
        StateLogError: On any filesystem error (parent missing, permission,
            disk full, fsync failure, etc.).
    """
    try:
        ledger_path.parent.mkdir(parents=True, exist_ok=True)

        fd = os.open(
            str(ledger_path),
            os.O_WRONLY | os.O_CREAT | os.O_APPEND,
            _STATE_FILE_MODE,
        )
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            # Idempotent dedup inside the lock — append-time check beats
            # the CLI/library boundary and protects against duplicate ticks.
            if _idempotency_match(
                ledger_path,
                record_dict["task_id"],
                record_dict["state"],
            ):
                return ledger_path
            line = (
                json.dumps(record_dict, ensure_ascii=False, sort_keys=False)
                + "\n"
            )
            os.write(fd, line.encode("utf-8"))
            os.fsync(fd)
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)
        return ledger_path
    except StateLogError:  # pragma: no cover — defensive
        raise
    except Exception as exc:  # noqa: BLE001 — re-raise as StateLogError
        raise StateLogError(f"JSONL append failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Activity log (best-effort, FR-013 swallows failures)
# ---------------------------------------------------------------------------


def _write_activity_log(record_dict: dict) -> Optional[Path]:
    """Append a one-line activity entry to the per-day operator log.

    Best-effort: any filesystem error is logged at debug level and
    swallowed. The JSONL row is the authoritative record; this log is a
    secondary operator-readable trail.

    Format (per day file):
        ``<ISO timestamp_utc> | <task_id> | <state> | <source> [| <note>]``

    Returns:
        The path written to, or ``None`` on failure.
    """
    try:
        ACTIVITY_LOG_DIR.mkdir(parents=True, exist_ok=True)
        # Date stamp from the record's timestamp (first 10 chars of ISO).
        date_str = str(record_dict["timestamp_utc"])[:10]
        log_path = ACTIVITY_LOG_DIR / f"{date_str}.log"
        parts = [
            str(record_dict["timestamp_utc"]),
            str(record_dict["task_id"]),
            str(record_dict["state"]),
            str(record_dict["source"]),
        ]
        if record_dict.get("note"):
            parts.append(str(record_dict["note"]))
        line = " | ".join(parts) + "\n"
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(line)
        return log_path
    except Exception as exc:  # noqa: BLE001 — best-effort
        _LOG.debug("activity log append failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Vikunja side-effect
# ---------------------------------------------------------------------------


def _vikunja_side_effect(
    record_dict: dict, *, base_url: str, token: str
) -> list[str]:
    """Perform the single Vikunja side-effect required by every record.

    PUT ``/tasks/{task_id}/comments`` with the v1 ``[Felix] enrichment``
    comment body. Unlike escalation, enrichment never PATCHes the task
    itself — Kent (or the agent) closes / edits the task separately;
    this helper records the enrichment state cycle only.

    Args:
        record_dict: Validated enrichment record dict.
        base_url: Vikunja API base URL.
        token: felix-bot bearer token.

    Returns:
        List of action names performed, in order. Always
        ``["comment_PUT"]`` on success.

    Raises:
        VikunjaError: On HTTP/network failure. The JSONL write does NOT
            happen when this is raised.
    """
    task_id = record_dict["task_id"]
    comment_url = _join_url(base_url, f"tasks/{task_id}/comments")
    comment_body = _format_v1_comment(record_dict)
    _http_request(
        "PUT", comment_url, token, body={"comment": comment_body}
    )
    return ["comment_PUT"]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def record(
    task_id: int,
    state: str,
    source: str,
    *,
    note: Optional[str] = None,
    timestamp_utc: Optional[str] = None,
    idempotent: bool = False,
    skip_vikunja: bool = False,
    base_url: str = DEFAULT_BASE_URL,
    token_path: Path = DEFAULT_TOKEN_PATH,
    ledger_path: Path = DEFAULT_LEDGER_PATH,
) -> dict:
    """Public convenience wrapper. Builds the record and delegates to ``record_event``.

    This is the import-facing entry point named in WP01 § Validation. It
    constructs an :class:`EnrichmentCompletion` from the keyword arguments
    and routes through the underlying three-write helper.

    Args:
        task_id: Vikunja task ID (positive integer).
        state: One of :data:`VALID_STATES`.
        source: One of :data:`VALID_SOURCES`.
        note: Optional free-text note.
        timestamp_utc: Override timestamp. Default: ``_now_utc_iso()``.
        idempotent: If True, skip the Vikunja call AND the JSONL append
            when a record matching ``(task_id, state)`` already exists.
        skip_vikunja: If True (reconcile/backfill paths), skip the
            Vikunja side-effect; write JSONL only.
        base_url: Vikunja API base URL.
        token_path: Path to the felix-bot bearer token file.
        ledger_path: Path to the JSONL ledger.

    Returns:
        Same dict as :func:`record_event`.

    Raises:
        EnrichmentSchemaError: On validation failure (no writes attempted).
        VikunjaError: On Vikunja step failure (no JSONL write).
        StateLogError: On JSONL append failure (Vikunja already committed
            unless ``skip_vikunja=True``).
    """
    completion = EnrichmentCompletion(
        task_id=task_id,
        state=state,
        timestamp_utc=timestamp_utc or _now_utc_iso(),
        source=source,
        schema_version=SCHEMA_VERSION,
        note=note,
    )
    func = (
        idempotent_record_event if idempotent else record_event
    )
    return func(
        completion.to_dict(),
        base_url=base_url,
        token_path=token_path,
        ledger_path=ledger_path,
        skip_vikunja=skip_vikunja,
    )


def record_event(
    record_dict: dict,
    *,
    base_url: str = DEFAULT_BASE_URL,
    token_path: Path = DEFAULT_TOKEN_PATH,
    ledger_path: Path = DEFAULT_LEDGER_PATH,
    skip_vikunja: bool = False,
) -> dict:
    """Atomic three-write helper. Vikunja FIRST, JSONL SECOND, ack log THIRD.

    See module docstring for the full ordering contract and the FR-013
    soft-fail semantics.

    Args:
        record_dict: Enrichment JSONL record dict. Must satisfy
            :func:`scripts.enrichment.schema.validate_record`.
        base_url: Vikunja API base URL.
        token_path: Path to the felix-bot bearer token file.
        ledger_path: Path to the JSONL ledger.
        skip_vikunja: When True, skip Step 1 (Vikunja side-effect). Used
            by reconcile/backfill to write synthetic records without
            re-emitting comments. Steps 0, 2, and 3 still run.

    Returns:
        Dict ``{"ok": True, "jsonl_path": "<path>",
        "vikunja_actions": [...], "deduped": False}``.

    Raises:
        EnrichmentSchemaError: On validation failure (no writes attempted).
        VikunjaError: On Vikunja step failure (no JSONL write).
        StateLogError: On JSONL append failure (Vikunja already committed
            unless ``skip_vikunja=True``).
    """
    # Step 0: validation.
    validate_record(record_dict)

    # Step 1: Vikunja side-effect (FIRST).
    vikunja_actions: list[str] = []
    if not skip_vikunja:
        token = _read_token(token_path)
        vikunja_actions = _vikunja_side_effect(
            record_dict, base_url=base_url, token=token
        )

    # Step 2: JSONL append (SECOND).
    path = _append_jsonl(record_dict, ledger_path)

    # Step 3: activity log (THIRD, best-effort).
    _write_activity_log(record_dict)

    return {
        "ok": True,
        "jsonl_path": str(path),
        "vikunja_actions": vikunja_actions,
        "deduped": False,
    }


def idempotent_record_event(
    record_dict: dict,
    *,
    base_url: str = DEFAULT_BASE_URL,
    token_path: Path = DEFAULT_TOKEN_PATH,
    ledger_path: Path = DEFAULT_LEDGER_PATH,
    skip_vikunja: bool = False,
) -> dict:
    """Pre-check then ``record_event``. No-op on duplicate ``(task_id, state)``.

    Per spec FR-004: the pre-check scans the JSONL ledger for an existing
    record matching ``(task_id, state)``. If found, returns immediately
    with ``deduped=True`` — no Vikunja calls, no JSONL write, no activity
    log entry.

    Validation runs BEFORE the dedup check so a malformed record can't
    short-circuit silently as "deduped=True".

    Args:
        record_dict: Same as :func:`record_event`.
        base_url: Same as :func:`record_event`.
        token_path: Same as :func:`record_event`.
        ledger_path: Same as :func:`record_event`.
        skip_vikunja: Same as :func:`record_event`.

    Returns:
        Either the normal :func:`record_event` return dict OR
        ``{"ok": True, "jsonl_path": "<path>", "vikunja_actions": [],
        "deduped": True}`` on dedup hit.

    Raises:
        EnrichmentSchemaError: On validation failure (no writes attempted).
        VikunjaError: On Vikunja step failure (no JSONL write).
        StateLogError: On JSONL append failure post-Vikunja, OR on the
            pre-check I/O error (caller distinguishes via context).
    """
    # Validation first — must run before any path inspection so a malformed
    # record never short-circuits silently as "deduped=True".
    validate_record(record_dict)

    if _idempotency_match(
        ledger_path, record_dict["task_id"], record_dict["state"]
    ):
        return {
            "ok": True,
            "jsonl_path": str(ledger_path),
            "vikunja_actions": [],
            "deduped": True,
        }
    return record_event(
        record_dict,
        base_url=base_url,
        token_path=token_path,
        ledger_path=ledger_path,
        skip_vikunja=skip_vikunja,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


_STATE_CHOICES = sorted(VALID_STATES)
_SOURCE_CHOICES = sorted(VALID_SOURCES)


class _ArgparseError(Exception):
    """Raised by :class:`_StructuredArgumentParser` on argparse usage errors.

    ``main()`` catches this and converts it to exit code 3 with a structured
    stderr line. Keeps argparse's default ``SystemExit(2)`` path from
    leaking through.
    """


class _StructuredArgumentParser(argparse.ArgumentParser):
    """``ArgumentParser`` subclass that routes usage errors through exit 3.

    Default argparse calls ``sys.exit(2)`` from ``error()``. We instead
    raise :class:`_ArgparseError` so :func:`main` can emit a structured
    JSON line on stderr and return ``3`` to conform to ``contracts/cli.md``.
    ``--help`` still exits ``0`` because that path goes through ``exit()``
    rather than ``error()``.
    """

    def error(self, message: str) -> None:  # type: ignore[override]
        raise _ArgparseError(message)


def _build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser for ``python3 -m`` entry point."""
    parser = _StructuredArgumentParser(
        prog="python3 -m scripts.enrichment.record_completion",
        description=(
            "Phase 7 enrichment three-write helper. Validate -> Vikunja "
            "comment (FIRST) -> JSONL append (SECOND) -> activity log "
            "(THIRD). Exits 0/1/2/3 per contracts/cli.md (with FR-013 "
            "soft-fail mapping JSONL-after-Vikunja failures to exit 0)."
        ),
    )
    parser.add_argument(
        "--task-id",
        type=int,
        required=True,
        help="Vikunja task id (required).",
    )
    parser.add_argument(
        "--state",
        choices=_STATE_CHOICES,
        required=True,
        help=f"Enrichment state (required). One of {_STATE_CHOICES}.",
    )
    parser.add_argument(
        "--source",
        choices=_SOURCE_CHOICES,
        required=True,
        help=f"Origin of the record (required). One of {_SOURCE_CHOICES}.",
    )
    parser.add_argument(
        "--note",
        default=None,
        help="Optional free-text note.",
    )
    parser.add_argument(
        "--idempotent",
        action="store_true",
        help="Pre-check for duplicate (task_id, state); no-op on hit.",
    )
    parser.add_argument(
        "--no-vikunja",
        action="store_true",
        help=(
            "Skip the Vikunja side-effect step. Used by reconcile/backfill "
            "to write synthetic JSONL rows without re-emitting comments."
        ),
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Vikunja API base URL (default: {DEFAULT_BASE_URL}).",
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
        "--ledger-path",
        type=Path,
        default=DEFAULT_LEDGER_PATH,
        help=(
            "Path to the JSONL ledger "
            f"(default: {DEFAULT_LEDGER_PATH})."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Exit codes 0/1/2/3 per contracts/cli.md.

    Exit code mapping (with FR-013 soft-fail policy):
        0 — success OR idempotent no-op OR post-Vikunja JSONL failure
            (warning logged, Vikunja state consistent)
        1 — Vikunja step failure (no JSONL write)
        2 — pre-Vikunja JSONL failure (idempotent pre-check I/O error;
            nothing committed downstream)
        3 — validation / usage / token-load error
    """
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

    # Build the record from flags.
    completion = EnrichmentCompletion(
        task_id=args.task_id,
        state=args.state,
        timestamp_utc=_now_utc_iso(),
        source=args.source,
        schema_version=SCHEMA_VERSION,
        note=args.note,
    )
    record_dict = completion.to_dict()

    # Pre-flight: idempotent dedup check (done in main BEFORE token load
    # so a duplicate -idempotent run doesn't fail on missing token files).
    if args.idempotent:
        try:
            if _idempotency_match(
                args.ledger_path, record_dict["task_id"], record_dict["state"]
            ):
                result = {
                    "ok": True,
                    "jsonl_path": str(args.ledger_path),
                    "vikunja_actions": [],
                    "deduped": True,
                }
                print(json.dumps(result))
                return 0
        except OSError as exc:
            # Pre-Vikunja I/O failure on the idempotent pre-check — surface
            # as exit 2 so the operator can re-run cleanly. Nothing has
            # been committed downstream.
            print(
                json.dumps(
                    {
                        "ok": False,
                        "step": "state_log_precheck",
                        "error": str(exc),
                    }
                ),
                file=sys.stderr,
            )
            return 2

    # Run the three-write contract. We split into "Vikunja" and "JSONL"
    # phases manually so the FR-013 soft-fail policy can apply only to
    # the post-Vikunja JSONL failure case.
    try:
        validate_record(record_dict)
    except EnrichmentSchemaError as exc:
        print(
            json.dumps(
                {"ok": False, "step": "validation", "error": str(exc)}
            ),
            file=sys.stderr,
        )
        return 3

    vikunja_actions: list[str] = []
    if not args.no_vikunja:
        try:
            token = _read_token(args.token_path)
        except (FileNotFoundError, ValueError) as exc:
            print(
                json.dumps(
                    {"ok": False, "step": "token_load", "error": str(exc)}
                ),
                file=sys.stderr,
            )
            return 3
        try:
            vikunja_actions = _vikunja_side_effect(
                record_dict, base_url=args.base_url, token=token
            )
        except VikunjaError as exc:
            print(
                json.dumps(
                    {"ok": False, "step": "vikunja", "error": str(exc)}
                ),
                file=sys.stderr,
            )
            return 1

    # JSONL append. Failure here is the FR-013 soft-fail boundary when
    # Vikunja has already committed (or when --no-vikunja was set the
    # caller is reconcile, which itself runs idempotent and cares about
    # the I/O error — surface as exit 2 in that case).
    try:
        path = _append_jsonl(record_dict, args.ledger_path)
    except StateLogError as exc:
        if args.no_vikunja:
            # Reconcile / backfill path: nothing committed downstream;
            # exit 2 so the operator can re-run.
            print(
                json.dumps(
                    {"ok": False, "step": "state_log", "error": str(exc)}
                ),
                file=sys.stderr,
            )
            return 2
        # FR-013 soft-fail: Vikunja already committed; log warning + exit 0.
        warning = (
            f"JSONL append failed AFTER Vikunja side-effect landed; "
            f"the Vikunja state is consistent and the JSONL row is "
            f"recoverable via reconcile. Original error: {exc}"
        )
        _LOG.warning(warning)
        print(
            json.dumps(
                {
                    "ok": True,
                    "step": "state_log_soft_fail",
                    "warning": warning,
                    "vikunja_actions": vikunja_actions,
                }
            ),
            file=sys.stderr,
        )
        return 0

    # Step 3: activity log (best-effort).
    _write_activity_log(record_dict)

    result = {
        "ok": True,
        "jsonl_path": str(path),
        "vikunja_actions": vikunja_actions,
        "deduped": False,
    }
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
