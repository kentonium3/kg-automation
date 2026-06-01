"""Escalator: wake Sonnet via ``openclaw system event --mode now`` (WP-03 T018).

Invoked by the gate orchestrator (``run.py``) when the routing decision
is ``ESCALATE_TO_SONNET`` (FR-008) OR when the gate itself fails and a
fallback escalation must fire (FR-011).

Design notes
------------
- :func:`escalate` NEVER raises. Subprocess failures, timeouts, and
  parse errors all surface as :class:`EscalationResult` with an
  ``error`` string populated. The orchestrator records the error in
  the ledger and continues -- a failed escalation is a worse outcome
  than no escalation only if the fallback path itself depends on the
  escalation succeeding. The gate's contract treats "observation was
  attempted" as the floor.
- The reason is truncated to 500 chars (matches the contract's
  ``reason`` upper bound) before being passed to subprocess. The CLI
  argument is passed as a list element to ``subprocess.run`` (NOT as
  a shell string), so we do not shell-quote -- the kernel exec layer
  receives the raw bytes verbatim.
- ``timeout_seconds`` default 30s -- long enough for OpenClaw to
  acknowledge the event, short enough that a hung gate cannot wedge
  the systemd unit.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from typing import Optional


__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "EscalationResult",
    "REASON_MAX_LEN",
    "escalate",
]


logger = logging.getLogger(__name__)


DEFAULT_TIMEOUT_SECONDS = 30
REASON_MAX_LEN = 500


@dataclass(frozen=True)
class EscalationResult:
    """Result of one escalator invocation.

    Either ``escalated_event_id`` is set (success) or ``error`` is set
    (failure). Both being ``None`` would indicate a programming error
    in this module.
    """

    escalated_event_id: Optional[str] = None
    error: Optional[str] = None


def escalate(
    reason: str,
    *,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    openclaw_binary: str = "openclaw",
) -> EscalationResult:
    """Wake the expensive-tier path with ``reason`` as context.

    Shells out:

        ``openclaw system event --mode now --json --text "<reason>"``

    Returns a typed :class:`EscalationResult`. NEVER raises.

    Parameters
    ----------
    reason:
        Free-form text from the gate's decision. Truncated at
        ``REASON_MAX_LEN`` chars before passing to subprocess.
    timeout_seconds:
        Per-subprocess timeout. Default 30s.
    openclaw_binary:
        Override hook for tests; production uses ``openclaw`` from PATH.

    Returns
    -------
    EscalationResult
        ``escalated_event_id`` populated on success; ``error`` populated
        otherwise.
    """
    truncated = (reason or "")[:REASON_MAX_LEN]
    if not truncated:
        # An empty reason is a programming error -- the gate contract
        # requires a reason for ESCALATE and the fallback path always
        # supplies "Gate fallback — see ledger". We surface this so it
        # shows up in the ledger rather than silently passing.
        return EscalationResult(error="empty reason supplied to escalator")

    # Verify the binary exists before exec. ``shutil.which`` returns
    # None if not on PATH; surface a clear error instead of a confusing
    # FileNotFoundError later.
    if shutil.which(openclaw_binary) is None:
        return EscalationResult(
            error=f"openclaw binary not found on PATH: {openclaw_binary}"
        )

    cmd = [
        openclaw_binary,
        "system",
        "event",
        "--mode",
        "now",
        "--json",
        "--text",
        truncated,
    ]

    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return EscalationResult(
            error=f"openclaw system event timed out after {timeout_seconds}s"
        )
    except OSError as exc:
        return EscalationResult(error=f"openclaw system event OS error: {exc}")

    if completed.returncode != 0:
        # Avoid logging the reason (it may contain sensitive context);
        # the orchestrator captures the reason separately for the ledger.
        stderr_tail = (completed.stderr or "").strip()[:200]
        return EscalationResult(
            error=(
                f"openclaw system event exited {completed.returncode}: "
                f"{stderr_tail}"
            )
        )

    # Contract observed during #490 cutover (openclaw CLI 2026.3.24):
    # `openclaw system event --mode now --text "..." --json` returns
    # `{"ok": true}` on success — no event id field. Older or future
    # versions may return `{"event": {"id": "..."}}` or similar shapes.
    # Treat exit-0 as success regardless; populate event_id when present.
    event_id = _parse_event_id(completed.stdout)
    if event_id is None:
        ack = _parse_ok_ack(completed.stdout)
        if ack:
            return EscalationResult(escalated_event_id=None)
        return EscalationResult(
            error="openclaw system event returned no event id and no ok ack"
        )

    return EscalationResult(escalated_event_id=event_id)


def _parse_ok_ack(stdout: str) -> bool:
    """Detect ``{"ok": true}`` ack from openclaw system event --json.

    Used when ``_parse_event_id`` returns None — recent openclaw CLI
    versions ack-only on system events without surfacing an event id.
    """
    text = (stdout or "").strip()
    if not text:
        return False
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return False
    return isinstance(payload, dict) and payload.get("ok") is True


def _parse_event_id(stdout: str) -> Optional[str]:
    """Extract ``event.id`` (or equivalent) from JSON stdout.

    Tries several shapes the ``openclaw system event --json`` surface
    might emit -- the contract here is minimal and we are defensive
    about the actual response shape because the OpenClaw CLI has
    evolved over time:

    - ``{"event": {"id": "..."}}``
    - ``{"id": "..."}``
    - ``{"event_id": "..."}``
    """
    text = (stdout or "").strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None

    if not isinstance(payload, dict):
        return None

    event = payload.get("event")
    if isinstance(event, dict):
        candidate = event.get("id")
        if isinstance(candidate, str) and candidate:
            return candidate

    for key in ("id", "event_id", "eventId"):
        candidate = payload.get(key)
        if isinstance(candidate, str) and candidate:
            return candidate

    return None
