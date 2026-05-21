"""Tick-signal artifact writer.

Per ``kitty-specs/refactor-doc-auditor-to-scripts-first-driver-01KS2XNX/
contracts/tick-signal.contract.md`` (schema v1.0). Writes a structured
JSON artifact at ``config.paths.tick_signal_path`` summarizing the
just-completed tick. The artifact is the load-bearing observation
surface for operators (`cat`/`jq`) and future #327 ``felix-alert``.

Semantics (from the contract):

- **Atomic**: temp-file in the same directory as the target, then
  ``os.rename`` (NOT ``shutil.move`` — across filesystems is not a
  concern here and only ``os.rename`` is POSIX-atomic on the same
  filesystem). No reader ever sees a partial write.
- **Current-state, not append-only**: each tick overwrites. History
  lives in the systemd journal + activity log.
- **Always written**: driver invokes :func:`write_tick_signal` from a
  ``try/finally`` block at the end of ``main()``; on crash, the
  ``finally`` block writes a best-effort ``status="failure"``
  artifact with whatever fields could be populated.

Status / exit-code alignment (contract §"Field constraints"):

- ``status="success"`` ↔ ``exit_code=0``
- ``status="partial"`` ↔ ``exit_code=2``
- ``status="failure"`` ↔ ``exit_code=1``
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from doc_audit.config import Config
from doc_audit.data_model import TickResult

__all__ = ["SCHEMA_VERSION", "DRIVER_VERSION", "print_summary_line", "write_tick_signal"]


SCHEMA_VERSION = "1.0"
DRIVER_VERSION = "0.1.0"

# Status → exit-code map. Mirrors the contract §"Field constraints".
_STATUS_EXIT_CODE = {
    "success": 0,
    "partial": 2,
    "failure": 1,
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _compute_duration(result: TickResult) -> float:
    """Compute wall-clock duration from ``started_utc`` / ``ended_utc``.

    Both fields are ISO-8601 strings (the data-model constraint;
    typically with a trailing ``Z`` produced via
    ``datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")``).
    Returns the elapsed seconds as a float.

    Returns ``0.0`` if either timestamp is missing or unparseable.
    The artifact is always written, so we never let a parse failure
    here abort the write.
    """
    if not result.started_utc or not result.ended_utc:
        return 0.0
    try:
        start = datetime.fromisoformat(result.started_utc.replace("Z", "+00:00"))
        end = datetime.fromisoformat(result.ended_utc.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    delta = end - start
    return delta.total_seconds()


def _exit_code_for(status: str) -> int:
    """Map a status string to its CLI exit code.

    Defaults to ``1`` (failure) on an unknown status so the artifact
    truthfully reflects an unrecoverable state rather than silently
    claiming success.
    """
    return _STATUS_EXIT_CODE.get(status, 1)


def _host() -> str:
    """Return the host the driver ran on (contract field ``host``).

    Wrapped so tests can monkeypatch ``os.uname`` cleanly.
    """
    try:
        return os.uname().nodename
    except AttributeError:  # pragma: no cover — non-POSIX
        # Windows is not a supported platform per CLAUDE.md, but keep
        # a sane fallback so the artifact always has a string value.
        return "unknown"


def _token_field(token_usage: dict[str, Any], field: str) -> int:
    """Safe-default access to a token-usage field."""
    return int(token_usage.get(field, 0) or 0)


def _judgment_call_count(judgment_calls: dict[str, Any], field: str) -> int:
    """Safe-default access to a judgment-call counter."""
    return int(judgment_calls.get(field, 0) or 0)


def _build_signal_dict(
    result: TickResult,
    next_scheduled_tick_utc: str,
) -> dict[str, Any]:
    """Build the dict serialized as ``last-tick.json``.

    Mirrors the contract schema v1.0 exactly. Field ordering matches
    the contract's example for readability; ``json.dump`` preserves
    dict ordering in Python 3.7+.
    """
    duration = _compute_duration(result)
    status = result.status or "failure"
    exit_code = _exit_code_for(status)

    return {
        "schema_version": SCHEMA_VERSION,
        "timestamp_utc": result.ended_utc,
        "status": status,
        "exit_code": exit_code,
        "driver_version": DRIVER_VERSION,
        "duration_seconds": duration,
        "host": _host(),
        "tick": {
            "signals_seen": result.signals_seen,
            "signals_processed": result.signals_processed,
            "audits_processed": list(getattr(result, "audits_processed", []) or []),
            "pending_approvals_applied": list(result.pending_approvals_applied),
            "pending_approvals_filed": list(result.pending_approvals_filed),
            "tier_a_commits": list(result.tier_a_commits),
            "debt_filed": list(result.debt_filed),
            "drift_events_consumed": int(result.drift_events_consumed),
        },
        "judgment": {
            "tier_classification_calls": _judgment_call_count(
                result.judgment_calls, "tier_classification"
            ),
            "debt_body_generation_calls": _judgment_call_count(
                result.judgment_calls, "debt_body_generation"
            ),
            "cross_file_implication_calls": _judgment_call_count(
                result.judgment_calls, "cross_file_implication"
            ),
            "input_tokens": _token_field(result.token_usage, "input_tokens"),
            "cache_hit_input_tokens": _token_field(
                result.token_usage, "cache_hit_input_tokens"
            ),
            "output_tokens": _token_field(result.token_usage, "output_tokens"),
        },
        "errors": list(result.errors),
        "next_scheduled_tick_utc": next_scheduled_tick_utc,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def write_tick_signal(
    config: Config,
    result: TickResult,
    next_scheduled_tick_utc: str,
) -> Path:
    """Atomically write ``last-tick.json``.

    Always succeeds (when the parent directory is writable). The
    contract guarantees this writer never raises on partial / failure
    ``TickResult`` instances — those produce a JSON artifact with
    ``status="failure"`` rather than an exception.

    Args:
        config: Driver :class:`Config`. The target path is
            ``config.paths.tick_signal_path``.
        result: The accumulated :class:`TickResult`. Mutated counters
            and lists are snapshotted into the JSON payload by value.
        next_scheduled_tick_utc: ISO-8601 timestamp of the next
            systemd-timer tick. The driver computes this from the
            timer schedule and passes it in (this module has no
            knowledge of systemd).

    Returns:
        The :class:`Path` of the written artifact.
    """
    signal_dict = _build_signal_dict(result, next_scheduled_tick_utc)

    target = Path(config.paths.tick_signal_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    # Atomic write: tempfile in the SAME directory as the target so
    # ``os.rename`` is a POSIX-atomic same-filesystem operation.
    # ``shutil.move`` is NOT atomic across filesystems — explicitly
    # use ``os.rename`` per the contract.
    fd_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            dir=str(target.parent),
            prefix=target.name + ".",
            suffix=".tmp",
            delete=False,
            encoding="utf-8",
        ) as f:
            json.dump(signal_dict, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
            fd_path = Path(f.name)
        os.rename(fd_path, target)
        fd_path = None  # ownership transferred; nothing to clean up
    finally:
        if fd_path is not None:
            # Rename failed; best-effort cleanup of the temp file.
            try:
                fd_path.unlink()
            except OSError:
                pass

    return target


def print_summary_line(result: TickResult) -> None:
    """Print the stdout SUMMARY: line per the contract.

    Format (from contract §"Stdout-summary line (companion)"):

        SUMMARY: status=<status> audits=<n> debt=<n> tier_a=<n>
                 drift=<n> dur=<s>s tokens=in:<n>(cache:<n>)/out:<n>

    Deterministic, single-line; consumers MAY parse it for at-a-glance
    health. The JSON artifact remains the canonical machine-readable
    surface.
    """
    duration = _compute_duration(result)
    audits = list(getattr(result, "audits_processed", []) or [])
    tu = result.token_usage or {}
    input_tokens = _token_field(tu, "input_tokens")
    cache_tokens = _token_field(tu, "cache_hit_input_tokens")
    output_tokens = _token_field(tu, "output_tokens")
    print(
        f"SUMMARY: status={result.status} "
        f"audits={len(audits)} "
        f"debt={len(result.debt_filed)} "
        f"tier_a={len(result.tier_a_commits)} "
        f"drift={result.drift_events_consumed} "
        f"dur={duration:.1f}s "
        f"tokens=in:{input_tokens}(cache:{cache_tokens})/"
        f"out:{output_tokens}"
    )
