"""Deterministic WhatsApp send wrapper (WP04 / T014).

Wraps the established ``openclaw agent --deliver --channel whatsapp`` subprocess
pattern used by ``scripts/obsidian/sync-heartbeat.py:114-138``. The subprocess
argument order is byte-for-byte identical to that precedent.

``send`` NEVER raises. All failure modes return a ``SendResult`` so the caller
in emit.py can attribute the failure to the corresponding ConflictEvent row.

Contract: kitty-specs/.../contracts/whatsapp-send.md.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


WHATSAPP_RECIPIENT_ENV_VAR: str = "FELIX_WHATSAPP_RECIPIENT"

DEFAULT_AGENT: str = "main"
DEFAULT_TIMEOUT_SECONDS: int = 60

# Class markers per contracts/whatsapp-send.md § Message shape.
MARKER_UNSAFE_DOWNSTREAM: str = "🟠 Vikunja edit (unsafe)"
MARKER_UNSAFE_CAUTION: str = "🟡 Vikunja edit (caution)"

# Truncation budgets (chars).
TITLE_TRUNCATE_LEN: int = 60
VALUE_TRUNCATE_LEN: int = 30
REDACTED_LITERAL: str = "<redacted>"


# ---------------------------------------------------------------------------
# SendResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SendResult:
    """Outcome of one WhatsApp send attempt."""

    success: bool
    exit_code: int
    stderr: str | None


# ---------------------------------------------------------------------------
# Send (subprocess wrapper)
# ---------------------------------------------------------------------------


def send(
    *,
    message: str,
    recipient: str,
    agent: str = DEFAULT_AGENT,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    dry_run: bool = False,
) -> SendResult:
    """Deliver a WhatsApp message via the ``openclaw`` CLI.

    Returns SendResult(success, exit_code, stderr). Never raises.

    On ``dry_run=True``: logs the would-send payload to stderr (prefixed
    ``[whatsapp send: dry-run]``) and returns success with exit_code 0
    without invoking the subprocess.

    Outcome mapping:
    - subprocess exit 0 → SendResult(True, 0, None)
    - subprocess exit nonzero → SendResult(False, exit_code, stderr_text)
    - TimeoutExpired → SendResult(False, -1, "timeout after Ns")
    - FileNotFoundError → SendResult(False, -2, "openclaw binary not found on PATH")
    """
    if dry_run:
        sys.stderr.write(
            f"[whatsapp send: dry-run] {message[:200]}\n"
        )
        return SendResult(success=True, exit_code=0, stderr=None)

    try:
        result = subprocess.run(
            [
                "openclaw", "agent",
                "--agent", agent,
                "--message", message,
                "--deliver",
                "--channel", "whatsapp",
                "--to", recipient,
            ],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return SendResult(
            success=False,
            exit_code=-1,
            stderr=f"timeout after {timeout_seconds}s",
        )
    except FileNotFoundError:
        return SendResult(
            success=False,
            exit_code=-2,
            stderr="openclaw binary not found on PATH",
        )

    if result.returncode == 0:
        return SendResult(success=True, exit_code=0, stderr=None)
    return SendResult(
        success=False,
        exit_code=result.returncode,
        stderr=result.stderr or None,
    )


# ---------------------------------------------------------------------------
# Recipient resolution
# ---------------------------------------------------------------------------


def resolve_recipient(cli_arg: str | None) -> str:
    """Resolve the WhatsApp recipient. CLI > env var > raise OSError.

    Per contracts/whatsapp-send.md: no hard-coded default. If neither source
    provides a value the driver exits 3 (validation_error) before any cycle
    work begins.
    """
    if cli_arg:
        return cli_arg
    env_value = os.environ.get(WHATSAPP_RECIPIENT_ENV_VAR)
    if env_value:
        return env_value
    raise OSError(
        f"WhatsApp recipient unresolved: no --whatsapp-recipient CLI argument "
        f"and {WHATSAPP_RECIPIENT_ENV_VAR} env var is unset."
    )


# ---------------------------------------------------------------------------
# Message formatter
# ---------------------------------------------------------------------------


def _truncate(value: str, max_len: int) -> str:
    if len(value) <= max_len:
        return value
    return value[: max_len - 1] + "…"


def _short_repr(value) -> str:
    """JSON-encode + truncate for display in the diff line."""
    encoded = json.dumps(value, sort_keys=True)
    return _truncate(encoded, VALUE_TRUNCATE_LEN)


def format_message(
    *,
    diff_field: str,
    vikunja_value,
    felix_cached_value,
    vikunja_entity_id: int,
    task_title: str | None,
    is_downstream: bool,
    is_private: bool,
) -> str:
    """Build the 3-line WhatsApp message per contracts/whatsapp-send.md.

    Line 1: class marker (downstream = 🟠, caution = 🟡).
    Line 2: ``Task #{id}: {title}`` (or ``<redacted>`` for private tasks).
    Line 3: ``{field}: {old} → {new}`` (JSON-encoded values, truncated).

    For privacy-redacted tasks every value-bearing slot becomes ``<redacted>``.
    """
    line1 = MARKER_UNSAFE_DOWNSTREAM if is_downstream else MARKER_UNSAFE_CAUTION

    if is_private:
        line2 = f"Task #{vikunja_entity_id}: {REDACTED_LITERAL}"
        line3 = f"{REDACTED_LITERAL}: {REDACTED_LITERAL} → {REDACTED_LITERAL}"
    else:
        title = task_title if task_title else "<unknown task>"
        line2 = f"Task #{vikunja_entity_id}: {_truncate(title, TITLE_TRUNCATE_LEN)}"
        old_short = _short_repr(felix_cached_value)
        new_short = _short_repr(vikunja_value)
        line3 = f"{diff_field}: {old_short} → {new_short}"

    return f"{line1}\n{line2}\n{line3}"
