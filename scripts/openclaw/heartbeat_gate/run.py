"""Heartbeat gate orchestrator (WP-03 T020) -- systemd entrypoint.

Composes the four heartbeat-gate modules into one tick:

1. :mod:`context.load_context` -- read ``last-tick.json`` +
   ``HEARTBEAT.md``; derive novelty markers.
2. :mod:`gate.decide` -- run the Haiku routing prompt.
3. :mod:`escalator.escalate` -- if ``ESCALATE_TO_SONNET``, wake the
   main agent via ``openclaw system event --mode now``.
4. :mod:`ledger.write_tick_record` -- write
   ``last-gate-decision.json`` atomically and append the JSONL ledger.

Fallback behavior (FR-011)
--------------------------
ANY failure in steps 1-2 triggers the fallback path:

- Build a ``GateTickRecord`` with ``outcome = "ESCALATE_TO_SONNET"``,
  ``fallback_invoked = True``, the error captured in ``errors[]``,
  and zero token counts.
- Invoke ``escalator.escalate("Gate fallback — see ledger")`` so the
  main agent runs regardless.
- Write the ledger entry per the normal path.
- Exit 0 (observation succeeded; the fallback IS the observation).

A failure in steps 3 or 4 (escalator or ledger write) cannot be fully
recovered. We still try to write the ledger with whatever partial
information we have, and exit 0 if at least one of the persistence
calls succeeded; exit 1 only when an unhandled exception escapes.

CLI flags
---------
- ``--last-tick PATH``        signal-extraction tick file.
- ``--heartbeat-md PATH``     operator's contract file.
- ``--api-key PATH``          Anthropic API key file.
- ``--prompt PATH``           routing prompt template.
- ``--last-decision PATH``    atomic-write target for tick decision.
- ``--ledger PATH``           append-only JSONL ledger.
- ``--openclaw-binary PATH``  override hook for tests; production uses
  ``openclaw`` on PATH.
- ``--dry-run``               skip the actual Haiku call AND the
  escalator; print SUMMARY only. The ledger is NOT written when
  ``--dry-run`` is set, so dry-run never pollutes the production
  decision file.
"""

from __future__ import annotations

import argparse
import json
import logging
import secrets
import sys
import time as _time
import traceback
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


# sys.path bootstrap so the module is runnable directly via
# ``python3 scripts/openclaw/heartbeat_gate/run.py``. Mirrors the
# convention in ``observation/tick.py``.
_REPO_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT_FOR_IMPORTS))


from scripts.openclaw.heartbeat_gate import context as _context  # noqa: E402
from scripts.openclaw.heartbeat_gate import escalator as _escalator  # noqa: E402
from scripts.openclaw.heartbeat_gate import gate as _gate  # noqa: E402
from scripts.openclaw.heartbeat_gate import ledger as _ledger  # noqa: E402


__all__ = [
    "DEFAULT_HEARTBEAT_MD_PATH",
    "DEFAULT_LAST_DECISION_PATH",
    "DEFAULT_LAST_TICK_PATH",
    "DEFAULT_LEDGER_PATH",
    "DEFAULT_PROMPT_PATH",
    "FALLBACK_REASON_DEFAULT",
    "main",
    "new_tick_id",
    "run_tick",
]


logger = logging.getLogger(__name__)


DEFAULT_LAST_TICK_PATH = Path(
    "/data/services/openclaw/felix-core-digest-signals/last-tick.json"
)
DEFAULT_HEARTBEAT_MD_PATH = Path("/data/services/openclaw/data/HEARTBEAT.md")
DEFAULT_LAST_DECISION_PATH = Path(
    "/data/services/openclaw/felix-heartbeat-gate/last-gate-decision.json"
)
DEFAULT_LEDGER_PATH = Path(
    "/data/services/openclaw/felix-heartbeat-gate/gate-ledger.jsonl"
)
DEFAULT_PROMPT_PATH = (
    Path(__file__).resolve().parent / "prompts" / "routing.prompt.md"
)

FALLBACK_REASON_DEFAULT = "Gate fallback — see ledger"


# Crockford Base32 alphabet (excludes I, L, O, U). Pattern matches the
# ULID generation in ``observation/tick.py``.
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_tick_id(now_utc: datetime) -> str:
    """Generate a 26-character ULID-shaped identifier.

    Stdlib-only ULID -- mirrors ``observation/tick.py::new_cycle_id``.
    Time-sortable to ms precision so ledger entries grep-and-sort
    naturally.
    """
    ts_ms = int(now_utc.timestamp() * 1000)
    rand_bytes = secrets.token_bytes(10)
    rand_int = int.from_bytes(rand_bytes, "big")
    value = (ts_ms << 80) | rand_int
    out = []
    for _ in range(26):
        out.append(_CROCKFORD[value & 0x1F])
        value >>= 5
    return "".join(reversed(out))


def _iso_z(dt: datetime) -> str:
    """Render a tz-aware datetime as ISO-8601 with ``Z`` suffix."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def run_tick(
    *,
    last_tick_path: Path,
    heartbeat_md_path: Path,
    api_key_path: Path,
    prompt_path: Path,
    last_decision_path: Path,
    ledger_path: Path,
    openclaw_binary: str = "openclaw",
    dry_run: bool = False,
    now: Optional[datetime] = None,
    client_factory: Optional[Any] = None,
    escalator_fn: Optional[Any] = None,
) -> _ledger.GateTickRecord:
    """Run one heartbeat-gate tick.

    Returns the :class:`GateTickRecord` written to the ledger (or, in
    ``--dry-run`` mode, the record that WOULD have been written). The
    record is also returned on the fallback path -- callers can
    inspect ``record.fallback_invoked`` to distinguish.

    The function is structured so each step's failure mode rolls
    forward into the next: a failed context load goes to fallback; a
    failed gate call goes to fallback; a failed escalation populates
    the ``errors`` field but does not raise.
    """
    started_at = now or datetime.now(tz=timezone.utc)
    tick_id = new_tick_id(started_at)
    started_iso = _iso_z(started_at)

    errors: list[dict] = []
    fallback_invoked = False
    context_obj: Optional[_context.GateContext] = None
    decision: Optional[_gate.GateDecision] = None
    escalator_callable = escalator_fn or _escalator.escalate

    tick_start_perf = _time.perf_counter()

    # --- Step 1: load context ---------------------------------------------
    try:
        context_obj = _context.load_context(
            last_tick_path,
            heartbeat_md_path,
            tick_id=tick_id,
        )
    except _context.MissingTickError as exc:
        errors.append(
            {
                "error_type": "missing_last_tick",
                "error_message": f"{type(exc).__name__}: {exc}",
            }
        )
        fallback_invoked = True
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(
            {
                "error_type": "context_load_failed",
                "error_message": f"{type(exc).__name__}: {exc}",
            }
        )
        fallback_invoked = True

    # --- Step 2: gate decision --------------------------------------------
    if context_obj is not None and not fallback_invoked:
        try:
            decision = _gate.decide(
                context_obj,
                api_key_path=api_key_path,
                prompt_path=prompt_path,
                client_factory=client_factory,
            )
        except _gate.GateRoutingError as exc:
            errors.append(
                {
                    "error_type": "gate_routing_failed",
                    "error_message": f"{type(exc).__name__}: {exc}",
                }
            )
            fallback_invoked = True
        except FileNotFoundError as exc:
            # Missing API key file -- distinct from a routing error.
            errors.append(
                {
                    "error_type": "api_key_missing",
                    "error_message": f"{type(exc).__name__}: {exc}",
                }
            )
            fallback_invoked = True

    # --- Step 3: escalation (if needed) -----------------------------------
    escalated_event_id: Optional[str] = None
    if not dry_run:
        if fallback_invoked:
            # Fallback path: always escalate so observation isn't dropped.
            result = escalator_callable(
                FALLBACK_REASON_DEFAULT,
                timeout_seconds=_escalator.DEFAULT_TIMEOUT_SECONDS,
                openclaw_binary=openclaw_binary,
            )
            escalated_event_id = result.escalated_event_id
            if result.error:
                errors.append(
                    {
                        "error_type": "escalator_failed",
                        "error_message": result.error,
                    }
                )
        elif decision is not None and decision.outcome == "ESCALATE_TO_SONNET":
            result = escalator_callable(
                decision.reason,
                timeout_seconds=_escalator.DEFAULT_TIMEOUT_SECONDS,
                openclaw_binary=openclaw_binary,
            )
            escalated_event_id = result.escalated_event_id
            if result.error:
                errors.append(
                    {
                        "error_type": "escalator_failed",
                        "error_message": result.error,
                    }
                )

    # --- Build the record -------------------------------------------------
    gate_latency_ms = int((_time.perf_counter() - tick_start_perf) * 1000)

    if fallback_invoked:
        outcome = "ESCALATE_TO_SONNET"
        reason = FALLBACK_REASON_DEFAULT
        digest_snapshot = (
            context_obj.digest_snapshot_at_utc if context_obj else ""
        )
        heartbeat_md_state = (
            context_obj.heartbeat_md_state if context_obj else "empty"
        )
        novelty_markers = (
            list(context_obj.novelty_markers) if context_obj else []
        )
        in_tokens = 0
        cache_tokens = 0
        out_tokens = 0
    else:
        # On the success path we know decision is not None (loop above
        # only proceeds when context_obj is set and decide returned).
        assert decision is not None  # for type-checkers; runtime invariant
        assert context_obj is not None
        outcome = decision.outcome
        reason = decision.reason
        digest_snapshot = context_obj.digest_snapshot_at_utc
        heartbeat_md_state = context_obj.heartbeat_md_state
        novelty_markers = list(context_obj.novelty_markers)
        in_tokens = decision.input_tokens
        cache_tokens = decision.cache_hit_tokens
        out_tokens = decision.output_tokens

    record = _ledger.GateTickRecord(
        tick_id=tick_id,
        started_at_utc=started_iso,
        gate_latency_ms=gate_latency_ms,
        digest_snapshot_at_utc=digest_snapshot,
        heartbeat_md_state=heartbeat_md_state,
        novelty_markers_seen=novelty_markers,
        outcome=outcome,
        reason=reason,
        escalated_event_id=escalated_event_id,
        gate_input_tokens=in_tokens,
        gate_cache_hit_tokens=cache_tokens,
        gate_output_tokens=out_tokens,
        fallback_invoked=fallback_invoked,
        errors=errors,
    )

    # --- Step 4: persist --------------------------------------------------
    if not dry_run:
        _ledger.write_tick_record(record, last_decision_path, ledger_path)

    return record


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="heartbeat_gate.run",
        description="Felix heartbeat gate: one-shot tick orchestrator.",
    )
    parser.add_argument(
        "--last-tick",
        type=Path,
        default=DEFAULT_LAST_TICK_PATH,
        help=f"signal-extraction tick file (default: {DEFAULT_LAST_TICK_PATH})",
    )
    parser.add_argument(
        "--heartbeat-md",
        type=Path,
        default=DEFAULT_HEARTBEAT_MD_PATH,
        help=(
            "operator's heartbeat contract file "
            f"(default: {DEFAULT_HEARTBEAT_MD_PATH})"
        ),
    )
    parser.add_argument(
        "--api-key",
        type=Path,
        default=_gate.DEFAULT_API_KEY_PATH,
        help=f"Anthropic API key file (default: {_gate.DEFAULT_API_KEY_PATH})",
    )
    parser.add_argument(
        "--prompt",
        type=Path,
        default=DEFAULT_PROMPT_PATH,
        help=f"routing prompt template (default: {DEFAULT_PROMPT_PATH})",
    )
    parser.add_argument(
        "--last-decision",
        type=Path,
        default=DEFAULT_LAST_DECISION_PATH,
        help=(
            "atomic-write target for the tick decision "
            f"(default: {DEFAULT_LAST_DECISION_PATH})"
        ),
    )
    parser.add_argument(
        "--ledger",
        type=Path,
        default=DEFAULT_LEDGER_PATH,
        help=f"append-only JSONL ledger (default: {DEFAULT_LEDGER_PATH})",
    )
    parser.add_argument(
        "--openclaw-binary",
        default="openclaw",
        help="openclaw CLI binary name or path (default: openclaw on PATH)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "skip the Haiku call AND the escalator; do NOT write the ledger. "
            "Useful for smoke-testing the orchestrator wiring."
        ),
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    """systemd entrypoint. Returns exit code (0 = OK or fallback succeeded)."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        record = run_tick(
            last_tick_path=args.last_tick,
            heartbeat_md_path=args.heartbeat_md,
            api_key_path=args.api_key,
            prompt_path=args.prompt,
            last_decision_path=args.last_decision,
            ledger_path=args.ledger,
            openclaw_binary=args.openclaw_binary,
            dry_run=args.dry_run,
        )
    except Exception as exc:  # noqa: BLE001 - last-resort safety net
        # Unhandled exception path: log the traceback, attempt a minimal
        # fallback ledger entry, then exit 1.
        logger.error("heartbeat_gate unhandled exception: %s", exc)
        traceback.print_exc(file=sys.stderr)
        try:
            _emergency_fallback_write(
                last_decision_path=args.last_decision,
                ledger_path=args.ledger,
                error_text=f"{type(exc).__name__}: {exc}",
                openclaw_binary=args.openclaw_binary,
                dry_run=args.dry_run,
            )
        except Exception:  # noqa: BLE001 - best-effort
            logger.exception("emergency fallback also failed")
        return 1

    print(_summary_line(record, dry_run=args.dry_run))
    return 0


def _summary_line(record: _ledger.GateTickRecord, *, dry_run: bool) -> str:
    """Render the stdout summary line.

    Format mirrors the SUMMARY convention used by ``observation/tick.py``:
    a single grep-friendly line that captures the key per-tick facts.
    """
    prefix = "[DRY-RUN] " if dry_run else ""
    return (
        f"{prefix}SUMMARY: outcome={record.outcome} "
        f"fallback={record.fallback_invoked} "
        f"dur={record.gate_latency_ms}ms "
        f"tokens=in:{record.gate_input_tokens}"
        f"(cache:{record.gate_cache_hit_tokens})/"
        f"out:{record.gate_output_tokens}"
    )


def _emergency_fallback_write(
    *,
    last_decision_path: Path,
    ledger_path: Path,
    error_text: str,
    openclaw_binary: str,
    dry_run: bool,
) -> None:
    """Write a minimal fallback ledger entry after an unhandled exception.

    Also fires the escalator with "Gate fallback — unhandled exception"
    so the main agent runs. NEVER raises -- the caller already knows
    the gate crashed; this is a best-effort signal-preservation step.
    """
    now = datetime.now(tz=timezone.utc)
    tick_id = new_tick_id(now)
    record = _ledger.GateTickRecord(
        tick_id=tick_id,
        started_at_utc=_iso_z(now),
        gate_latency_ms=0,
        digest_snapshot_at_utc="",
        heartbeat_md_state="empty",
        novelty_markers_seen=[],
        outcome="ESCALATE_TO_SONNET",
        reason="Gate fallback — unhandled exception",
        escalated_event_id=None,
        gate_input_tokens=0,
        gate_cache_hit_tokens=0,
        gate_output_tokens=0,
        fallback_invoked=True,
        errors=[
            {
                "error_type": "unhandled_exception",
                "error_message": error_text,
            }
        ],
    )

    if not dry_run:
        # Escalate first so the main agent runs even if the ledger
        # write fails (rare, but possible on a full disk).
        result = _escalator.escalate(
            "Gate fallback — unhandled exception",
            openclaw_binary=openclaw_binary,
        )
        # Update the record with whatever the escalator returned.
        record = _ledger.GateTickRecord(
            **{**asdict(record), "escalated_event_id": result.escalated_event_id}
        )
        if result.error:
            updated_errors = list(record.errors) + [
                {
                    "error_type": "escalator_failed",
                    "error_message": result.error,
                }
            ]
            record = _ledger.GateTickRecord(
                **{**asdict(record), "errors": updated_errors}
            )

        try:
            _ledger.write_tick_record(record, last_decision_path, ledger_path)
        except Exception:  # noqa: BLE001 - best-effort
            logger.exception("emergency ledger write failed")


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())
