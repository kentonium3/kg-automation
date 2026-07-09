"""Deterministic heartbeat-gate routing decision (#676 T001/T002).

Replaces the former Haiku-fronted ``decide()`` (Anthropic SDK wrapper,
retired 2026-07-08) with a pure, standard-library-only function that
reproduces the routing prompt's exact boolean escalation contract. See
``kitty-specs/deterministic-monitoring-checks-01KX1XNW/contracts/
escalation-rule.contract.md`` for the authoritative truth table.

Design notes
------------
- :func:`decide_deterministic` is **total**: it must never raise on any
  ``GateContext`` that ``context.load_context`` can produce. Every field
  access is guarded so malformed-but-loaded data (a non-list ``errors``,
  a ``signals_evaluated`` entry missing a key) degrades gracefully
  instead of escaping to the orchestrator's emergency path (FR-007).
- No I/O. No ``anthropic`` import. No network calls. The tick hot path
  imports only this module and the stdlib.
- Token fields are always zero -- there is no LLM call to measure.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


__all__ = [
    "GateDecision",
    "build_reason",
    "decide_deterministic",
]


_REASON_MAX_LEN = 500


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GateDecision:
    """Result of one heartbeat-gate routing decision.

    The orchestrator uses this struct to:
    - Decide whether to invoke the escalator (``ESCALATE_TO_SONNET``).
    - Record per-tick token cost in the gate ledger. Since the decision
      is now made deterministically (no LLM call), all three token
      fields are always ``0`` (NFR-001).
    - Surface the reason text to the operator via the ledger.
    """

    outcome: Literal["HEARTBEAT_OK", "LOG_AND_SKIP", "ESCALATE_TO_SONNET"]
    reason: str
    input_tokens: int = 0
    cache_hit_tokens: int = 0
    output_tokens: int = 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def decide_deterministic(context: Any) -> GateDecision:
    """Route one heartbeat tick using the deterministic escalation rule.

    Reproduces the routing prompt's boolean escalation contract exactly
    (see the contract doc's truth table):

    - ``ESCALATE_TO_SONNET`` iff ``novelty_markers`` is non-empty, OR
      ``heartbeat_md_state == "has_tasks"``, OR ``errors`` is non-empty.
    - Otherwise, ``LOG_AND_SKIP`` when ``issues_filed`` is non-empty OR
      any evaluated signal shows non-zero cycle activity while
      ``threshold_status == "below"``; else ``HEARTBEAT_OK``.

    This function is **total**: it never raises, regardless of how
    malformed ``context`` is (short of not being passed at all). Every
    field access is defensively guarded -- missing attributes, wrong
    types, and malformed list entries are all treated as "no signal"
    rather than propagating an exception. This is load-bearing: an
    uncaught exception here would otherwise escape to the orchestrator's
    unhandled-exception path (exit 1), contradicting the spec's
    "step 1/2 failure -> fallback, exit 0" contract (FR-007). The
    orchestrator's broadened ``except Exception`` in ``run.py`` is a
    second, independent line of defense behind this totality guarantee.

    Returns
    -------
    GateDecision
        ``input_tokens == cache_hit_tokens == output_tokens == 0``
        always -- there is no LLM call to measure (NFR-001).
    """
    novelty_markers = _safe_list(context, "novelty_markers")
    errors = _safe_list(context, "errors")
    issues_filed = _safe_list(context, "issues_filed")
    signals_evaluated = _safe_list(context, "signals_evaluated")
    heartbeat_md_state = getattr(context, "heartbeat_md_state", None)

    escalate = (
        len(novelty_markers) > 0
        or heartbeat_md_state == "has_tasks"
        or len(errors) > 0
    )

    if escalate:
        return GateDecision(
            outcome="ESCALATE_TO_SONNET",
            reason=build_reason(context),
        )

    if len(issues_filed) > 0 or _has_below_threshold_activity(
        signals_evaluated
    ):
        return GateDecision(outcome="LOG_AND_SKIP", reason="")

    return GateDecision(outcome="HEARTBEAT_OK", reason="")


def build_reason(context: Any) -> str:
    """Build a deterministic, factual reason for an ``ESCALATE_TO_SONNET``.

    Cites only the firing triggers -- novelty marker IDs, the heartbeat
    contract flag, and error types -- in one paragraph, truncated
    defensively to ``_REASON_MAX_LEN`` (500) characters. Contains no
    action/recommendation framing ("so Sonnet can...", "should...");
    the reason reports what was observed, it does not prescribe next
    steps (Codex finding #8).

    Guards every field access the same way :func:`decide_deterministic`
    does, so this function is total over any ``context`` shape.
    """
    novelty_markers = _safe_list(context, "novelty_markers")
    errors = _safe_list(context, "errors")
    heartbeat_md_state = getattr(context, "heartbeat_md_state", None)

    clauses: list[str] = []

    if novelty_markers:
        marker_ids = ", ".join(str(m) for m in novelty_markers)
        clauses.append(f"novelty markers: {marker_ids}")

    if heartbeat_md_state == "has_tasks":
        clauses.append("heartbeat contract has tasks")

    if errors:
        error_types = ", ".join(_error_type(e) for e in errors)
        clauses.append(f"tick errors: {error_types}")

    if not clauses:
        # Defensive fallback -- decide_deterministic only calls this when
        # escalate is True, but if a future caller invokes build_reason
        # directly with a context that doesn't actually trigger any of
        # the three conditions, still return a non-empty, factual string
        # rather than an empty reason.
        reason = "Escalation triggered; no specific trigger fields present."
    else:
        reason = "Escalating on: " + "; ".join(clauses) + "."

    return reason[:_REASON_MAX_LEN]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _safe_list(context: Any, field_name: str) -> list:
    """Read ``context.<field_name>``, coercing anything non-list to ``[]``.

    Totality guard: ``context`` might not be a ``GateContext`` at all
    (missing attribute), or a field might have been corrupted into a
    non-list value. Either way we treat it as "no entries" rather than
    raising ``AttributeError``/``TypeError``.
    """
    value = getattr(context, field_name, None)
    if isinstance(value, list):
        return value
    return []


def _error_type(entry: Any) -> str:
    """Extract ``error_type`` from one ``errors[]`` entry, defensively.

    Malformed entries (not a dict, missing the key, non-string value)
    render as ``"unknown"`` rather than raising.
    """
    if isinstance(entry, dict):
        value = entry.get("error_type")
        if isinstance(value, str) and value:
            return value
    return "unknown"


def _has_below_threshold_activity(signals_evaluated: list) -> bool:
    """True if any evaluated signal has non-zero cycle activity while
    still ``"below"`` threshold.

    Guards every field on each entry: non-dict entries, missing
    ``count_cycle``, and non-numeric ``count_cycle`` values are all
    treated as "no activity" rather than raising.
    """
    for sig in signals_evaluated:
        if not isinstance(sig, dict):
            continue
        if sig.get("threshold_status") != "below":
            continue
        count_cycle = sig.get("count_cycle", 0)
        try:
            if float(count_cycle) > 0:
                return True
        except (TypeError, ValueError):
            continue
    return False
