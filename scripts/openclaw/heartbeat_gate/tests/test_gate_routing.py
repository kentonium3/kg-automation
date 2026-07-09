"""Tests for ``heartbeat_gate.gate`` (#676 -- deterministic escalation rule).

Covers the escalation truth table from
``kitty-specs/deterministic-monitoring-checks-01KX1XNW/contracts/
escalation-rule.contract.md``:

- ``ESCALATE_TO_SONNET`` iff novelty markers, ``has_tasks``, or errors.
- ``LOG_AND_SKIP`` vs ``HEARTBEAT_OK`` split on the non-escalate branch.
- ``build_reason`` cites triggers, stays under 500 chars, and contains
  no action/recommendation framing.
- Totality: ``decide_deterministic`` never raises on malformed input.
- Token fields are always zero.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from scripts.openclaw.heartbeat_gate.context import GateContext
from scripts.openclaw.heartbeat_gate.gate import (
    GateDecision,
    build_reason,
    decide_deterministic,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def quiet_context() -> GateContext:
    """Fully quiet tick: nothing to escalate, log, or notice."""
    return GateContext(
        tick_id="01JTEST",
        digest_snapshot_at_utc="2026-06-01T17:15:00Z",
        signals_evaluated=[
            {
                "signal_id": "whatsapp_creds_restore",
                "count_cycle": 0,
                "count_rolling": 0,
                "threshold_status": "below",
            },
        ],
        issues_filed=[],
        errors=[],
        heartbeat_md_state="empty",
        novelty_markers=[],
    )


# ---------------------------------------------------------------------------
# Escalation triggers (each condition independently)
# ---------------------------------------------------------------------------


def test_escalates_on_novelty_markers(quiet_context: GateContext) -> None:
    ctx = GateContext(
        **{
            **quiet_context.__dict__,
            "novelty_markers": ["whatsapp_creds_restore"],
        }
    )
    decision = decide_deterministic(ctx)
    assert decision.outcome == "ESCALATE_TO_SONNET"
    assert "whatsapp_creds_restore" in decision.reason


def test_escalates_on_heartbeat_has_tasks(quiet_context: GateContext) -> None:
    ctx = GateContext(
        **{**quiet_context.__dict__, "heartbeat_md_state": "has_tasks"}
    )
    decision = decide_deterministic(ctx)
    assert decision.outcome == "ESCALATE_TO_SONNET"
    assert "heartbeat contract has tasks" in decision.reason


def test_escalates_on_errors(quiet_context: GateContext) -> None:
    ctx = GateContext(
        **{
            **quiet_context.__dict__,
            "errors": [
                {
                    "error_type": "source_missing",
                    "error_message": "signal source path failed",
                }
            ],
        }
    )
    decision = decide_deterministic(ctx)
    assert decision.outcome == "ESCALATE_TO_SONNET"
    assert "source_missing" in decision.reason


def test_escalates_on_mixed_triggers_cites_all(
    quiet_context: GateContext,
) -> None:
    ctx = GateContext(
        **{
            **quiet_context.__dict__,
            "novelty_markers": ["whatsapp_creds_restore"],
            "heartbeat_md_state": "has_tasks",
            "errors": [{"error_type": "source_missing"}],
        }
    )
    decision = decide_deterministic(ctx)
    assert decision.outcome == "ESCALATE_TO_SONNET"
    assert "whatsapp_creds_restore" in decision.reason
    assert "heartbeat contract has tasks" in decision.reason
    assert "source_missing" in decision.reason


# ---------------------------------------------------------------------------
# Non-escalation sub-label split
# ---------------------------------------------------------------------------


def test_heartbeat_ok_when_fully_quiet(quiet_context: GateContext) -> None:
    decision = decide_deterministic(quiet_context)
    assert decision.outcome == "HEARTBEAT_OK"
    assert decision.reason == ""


def test_log_and_skip_on_issues_filed(quiet_context: GateContext) -> None:
    ctx = GateContext(
        **{
            **quiet_context.__dict__,
            "issues_filed": [
                {
                    "signal_id": "whatsapp_creds_restore",
                    "issue_number": 491,
                }
            ],
        }
    )
    decision = decide_deterministic(ctx)
    assert decision.outcome == "LOG_AND_SKIP"


def test_log_and_skip_on_below_threshold_activity(
    quiet_context: GateContext,
) -> None:
    ctx = GateContext(
        **{
            **quiet_context.__dict__,
            "signals_evaluated": [
                {
                    "signal_id": "web_watchdog_reconnect",
                    "count_cycle": 1,
                    "count_rolling": 3,
                    "threshold_status": "below",
                },
            ],
        }
    )
    decision = decide_deterministic(ctx)
    assert decision.outcome == "LOG_AND_SKIP"


def test_issues_filed_alone_is_not_an_escalation_trigger(
    quiet_context: GateContext,
) -> None:
    """issues_filed must NEVER escalate on its own (contract: it only
    distinguishes LOG_AND_SKIP from HEARTBEAT_OK, never wakes Sonnet).
    """
    ctx = GateContext(
        **{
            **quiet_context.__dict__,
            "issues_filed": [{"signal_id": "x", "issue_number": 1}],
        }
    )
    decision = decide_deterministic(ctx)
    assert decision.outcome != "ESCALATE_TO_SONNET"


# ---------------------------------------------------------------------------
# Token fields always zero
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "context_kwargs",
    [
        {},
        {"novelty_markers": ["x"]},
        {"heartbeat_md_state": "has_tasks"},
        {"errors": [{"error_type": "x"}]},
        {"issues_filed": [{"signal_id": "x"}]},
    ],
)
def test_tokens_always_zero(
    quiet_context: GateContext, context_kwargs: dict[str, Any]
) -> None:
    ctx = GateContext(**{**quiet_context.__dict__, **context_kwargs})
    decision = decide_deterministic(ctx)
    assert isinstance(decision, GateDecision)
    assert decision.input_tokens == 0
    assert decision.cache_hit_tokens == 0
    assert decision.output_tokens == 0


# ---------------------------------------------------------------------------
# build_reason: content and framing
# ---------------------------------------------------------------------------


def test_build_reason_cites_novelty_marker_ids(
    quiet_context: GateContext,
) -> None:
    ctx = GateContext(
        **{
            **quiet_context.__dict__,
            "novelty_markers": ["whatsapp_creds_restore", "web_watchdog"],
        }
    )
    reason = build_reason(ctx)
    assert "whatsapp_creds_restore" in reason
    assert "web_watchdog" in reason


def test_build_reason_cites_has_tasks(quiet_context: GateContext) -> None:
    ctx = GateContext(
        **{**quiet_context.__dict__, "heartbeat_md_state": "has_tasks"}
    )
    reason = build_reason(ctx)
    assert "heartbeat contract has tasks" in reason


def test_build_reason_cites_error_types(quiet_context: GateContext) -> None:
    ctx = GateContext(
        **{
            **quiet_context.__dict__,
            "errors": [
                {"error_type": "source_missing"},
                {"error_type": "parse_failed"},
            ],
        }
    )
    reason = build_reason(ctx)
    assert "source_missing" in reason
    assert "parse_failed" in reason


def test_build_reason_within_500_chars(quiet_context: GateContext) -> None:
    ctx = GateContext(
        **{
            **quiet_context.__dict__,
            "novelty_markers": [f"signal_{i}" for i in range(100)],
        }
    )
    reason = build_reason(ctx)
    assert len(reason) <= 500


def test_build_reason_no_action_recommendation_framing(
    quiet_context: GateContext,
) -> None:
    ctx = GateContext(
        **{
            **quiet_context.__dict__,
            "novelty_markers": ["whatsapp_creds_restore"],
            "heartbeat_md_state": "has_tasks",
            "errors": [{"error_type": "source_missing"}],
        }
    )
    reason = build_reason(ctx).lower()
    forbidden_phrases = [
        "so sonnet can",
        "should",
        "recommend",
        "you should",
        "needs to",
        "must ",
    ]
    for phrase in forbidden_phrases:
        assert phrase not in reason, f"reason contains action framing: {phrase!r}"


def test_build_reason_non_empty_when_no_clauses_present() -> None:
    """Defensive: build_reason called directly (not via decide_deterministic)
    on a context with no firing triggers still returns a non-empty,
    factual string rather than an empty one.
    """
    ctx = GateContext(
        tick_id="01JTEST",
        digest_snapshot_at_utc="2026-06-01T17:15:00Z",
        signals_evaluated=[],
        issues_filed=[],
        errors=[],
        heartbeat_md_state="empty",
        novelty_markers=[],
    )
    reason = build_reason(ctx)
    assert reason != ""


# ---------------------------------------------------------------------------
# Totality (Codex finding #2, load-bearing)
# ---------------------------------------------------------------------------


@dataclass
class _MalformedContext:
    """A context-shaped object with malformed/missing fields.

    Deliberately does NOT match ``GateContext``'s schema -- some fields
    are missing entirely, others hold the wrong type. Used to prove
    ``decide_deterministic`` is total: it must not raise regardless.
    """

    tick_id: str = "01JBAD"
    digest_snapshot_at_utc: str = "2026-06-01T17:15:00Z"
    # signals_evaluated omitted entirely (getattr will miss).
    issues_filed: Any = None  # wrong type: None instead of list
    errors: Any = "not-a-list"  # wrong type: str instead of list
    heartbeat_md_state: Any = 12345  # wrong type: int instead of str
    novelty_markers: Any = field(default_factory=lambda: {"not": "a-list"})


def test_decide_deterministic_never_raises_on_malformed_context() -> None:
    malformed = _MalformedContext()
    decision = decide_deterministic(malformed)  # must not raise
    assert isinstance(decision, GateDecision)
    assert decision.outcome in {
        "HEARTBEAT_OK",
        "LOG_AND_SKIP",
        "ESCALATE_TO_SONNET",
    }
    assert decision.input_tokens == 0
    assert decision.cache_hit_tokens == 0
    assert decision.output_tokens == 0


def test_decide_deterministic_handles_malformed_signal_entries(
    quiet_context: GateContext,
) -> None:
    """A signals_evaluated entry missing fields, or a non-dict entry,
    must not raise -- it should be treated as "no activity".
    """
    ctx = GateContext(
        **{
            **quiet_context.__dict__,
            "signals_evaluated": [
                {"signal_id": "incomplete"},  # missing threshold_status
                "not-a-dict",
                42,
                None,
                {
                    "signal_id": "ok_one",
                    "count_cycle": "not-a-number",
                    "threshold_status": "below",
                },
            ],
        }
    )
    decision = decide_deterministic(ctx)  # must not raise
    assert isinstance(decision, GateDecision)


def test_decide_deterministic_handles_object_with_no_relevant_attrs() -> None:
    """A bare object() has none of the expected attributes at all."""

    class _Empty:
        pass

    decision = decide_deterministic(_Empty())  # must not raise
    assert decision.outcome == "HEARTBEAT_OK"


def test_build_reason_never_raises_on_malformed_context() -> None:
    malformed = _MalformedContext()
    reason = build_reason(malformed)  # must not raise
    assert isinstance(reason, str)
    assert len(reason) <= 500
