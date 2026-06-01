"""End-to-end tests for ``heartbeat_gate.run`` (WP-03 T021).

These tests exercise the orchestrator with all external dependencies
mocked: Anthropic SDK (via the ``client_factory`` override) and the
escalator (via the ``escalator_fn`` override).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from scripts.openclaw.heartbeat_gate import gate as _gate
from scripts.openclaw.heartbeat_gate import run as _run
from scripts.openclaw.heartbeat_gate.escalator import EscalationResult
from scripts.openclaw.heartbeat_gate.ledger import GateTickRecord, SCHEMA_VERSION
from scripts.openclaw.heartbeat_gate.tests.conftest import (
    make_client_factory,
    write_last_tick,
)


PROMPT_PATH = (
    Path(__file__).resolve().parents[1] / "prompts" / "routing.prompt.md"
)


def _make_paths(tmp_path: Path) -> dict[str, Path]:
    """Common path bundle for run_tick calls."""
    api_key = tmp_path / "anthropic.key"
    api_key.write_text("test-key")
    return {
        "api_key_path": api_key,
        "prompt_path": PROMPT_PATH,
        "last_decision_path": tmp_path / "last-gate-decision.json",
        "ledger_path": tmp_path / "gate-ledger.jsonl",
        "heartbeat_md_path": tmp_path / "HEARTBEAT.md",
    }


def _fake_escalator(*, event_id: str | None = "evt_x", error: str | None = None):
    """Build an escalator stub recording its calls."""
    calls: list[tuple[str, dict[str, Any]]] = []

    def _stub(reason: str, **kwargs: Any) -> EscalationResult:
        calls.append((reason, kwargs))
        return EscalationResult(escalated_event_id=event_id, error=error)

    _stub.calls = calls  # type: ignore[attr-defined]
    return _stub


# ---------------------------------------------------------------------------
# Happy path: HEARTBEAT_OK
# ---------------------------------------------------------------------------


def test_run_heartbeat_ok_no_escalation(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    write_last_tick(tmp_path / "last-tick.json")
    paths["heartbeat_md_path"].write_text("")

    client_factory = make_client_factory(
        response_text='{"outcome": "HEARTBEAT_OK", "reason": "all clean"}',
    )
    escalator = _fake_escalator()
    record = _run.run_tick(
        last_tick_path=tmp_path / "last-tick.json",
        **paths,
        client_factory=client_factory,
        escalator_fn=escalator,
    )

    assert record.outcome == "HEARTBEAT_OK"
    assert record.fallback_invoked is False
    assert record.escalated_event_id is None
    # Escalator must NOT be called on HEARTBEAT_OK.
    assert escalator.calls == []  # type: ignore[attr-defined]

    # Ledger written.
    payload = json.loads(paths["last_decision_path"].read_text())
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["outcome"] == "HEARTBEAT_OK"


def test_run_log_and_skip_no_escalation(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    write_last_tick(tmp_path / "last-tick.json")
    client_factory = make_client_factory(
        response_text='{"outcome": "LOG_AND_SKIP", "reason": "noisy single event"}',
    )
    escalator = _fake_escalator()
    record = _run.run_tick(
        last_tick_path=tmp_path / "last-tick.json",
        **paths,
        client_factory=client_factory,
        escalator_fn=escalator,
    )
    assert record.outcome == "LOG_AND_SKIP"
    assert record.fallback_invoked is False
    assert escalator.calls == []  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# ESCALATE_TO_SONNET path
# ---------------------------------------------------------------------------


def test_run_escalate_invokes_escalator_with_reason(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    write_last_tick(
        tmp_path / "last-tick.json",
        signals_evaluated=[
            {
                "signal_id": "whatsapp_creds_restore",
                "count_cycle": 12,
                "count_rolling": 35,
                "threshold_status": "tripped_both",
            }
        ],
        issues_filed=[
            {
                "signal_id": "whatsapp_creds_restore",
                "issue_number": 491,
                "issue_url": "https://example.com/491",
            }
        ],
    )
    client_factory = make_client_factory(
        response_text=(
            '{"outcome": "ESCALATE_TO_SONNET", '
            '"reason": "Signal whatsapp_creds_restore tripped both."}'
        ),
    )
    escalator = _fake_escalator(event_id="evt_42")
    record = _run.run_tick(
        last_tick_path=tmp_path / "last-tick.json",
        **paths,
        client_factory=client_factory,
        escalator_fn=escalator,
    )
    assert record.outcome == "ESCALATE_TO_SONNET"
    assert record.fallback_invoked is False
    assert record.escalated_event_id == "evt_42"
    # Escalator received the gate's reason, NOT the fallback text.
    assert escalator.calls[0][0].startswith("Signal whatsapp_creds_restore")  # type: ignore[attr-defined]
    # novelty_markers recorded in ledger.
    payload = json.loads(paths["last_decision_path"].read_text())
    assert payload["novelty_markers_seen"] == ["whatsapp_creds_restore"]


def test_run_escalator_failure_recorded_in_errors(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    write_last_tick(tmp_path / "last-tick.json")
    client_factory = make_client_factory(
        response_text='{"outcome": "ESCALATE_TO_SONNET", "reason": "test"}',
    )
    escalator = _fake_escalator(event_id=None, error="openclaw not on path")
    record = _run.run_tick(
        last_tick_path=tmp_path / "last-tick.json",
        **paths,
        client_factory=client_factory,
        escalator_fn=escalator,
    )
    assert record.outcome == "ESCALATE_TO_SONNET"
    assert record.escalated_event_id is None
    assert any(
        err["error_type"] == "escalator_failed" for err in record.errors
    )


# ---------------------------------------------------------------------------
# Fallback path (FR-011)
# ---------------------------------------------------------------------------


def test_run_fallback_on_missing_tick_file(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    # No last-tick.json written -> MissingTickError -> fallback.
    paths["heartbeat_md_path"].write_text("")
    client_factory = make_client_factory()
    escalator = _fake_escalator(event_id="evt_fallback")

    record = _run.run_tick(
        last_tick_path=tmp_path / "nope.json",
        **paths,
        client_factory=client_factory,
        escalator_fn=escalator,
    )
    assert record.fallback_invoked is True
    assert record.outcome == "ESCALATE_TO_SONNET"
    assert record.reason == _run.FALLBACK_REASON_DEFAULT
    assert record.gate_input_tokens == 0
    assert record.escalated_event_id == "evt_fallback"
    assert any(
        err["error_type"] == "missing_last_tick" for err in record.errors
    )
    # Ledger written even on fallback path.
    assert paths["last_decision_path"].exists()
    assert paths["ledger_path"].exists()


def test_run_fallback_on_malformed_tick_json(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    (tmp_path / "last-tick.json").write_text("{not json")
    client_factory = make_client_factory()
    escalator = _fake_escalator(event_id="evt_fb")

    record = _run.run_tick(
        last_tick_path=tmp_path / "last-tick.json",
        **paths,
        client_factory=client_factory,
        escalator_fn=escalator,
    )
    assert record.fallback_invoked is True
    assert any(
        err["error_type"] == "context_load_failed" for err in record.errors
    )


def test_run_fallback_on_gate_routing_error(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    write_last_tick(tmp_path / "last-tick.json")

    # The Haiku returns malformed JSON on both attempts -> GateRoutingError.
    client_factory = make_client_factory(
        response_text="garbage",
        additional_responses=[
            type(
                "R",
                (),
                {"content": [type("B", (), {"text": "garbage2"})()], "usage": None},
            )()
        ],
    )

    escalator = _fake_escalator(event_id="evt_fb2")
    record = _run.run_tick(
        last_tick_path=tmp_path / "last-tick.json",
        **paths,
        client_factory=client_factory,
        escalator_fn=escalator,
    )
    assert record.fallback_invoked is True
    assert record.reason == _run.FALLBACK_REASON_DEFAULT
    assert any(
        err["error_type"] == "gate_routing_failed" for err in record.errors
    )
    # Escalator was called with the fallback reason (not the failed parse).
    assert escalator.calls[0][0] == _run.FALLBACK_REASON_DEFAULT  # type: ignore[attr-defined]


def test_run_fallback_on_missing_api_key(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    write_last_tick(tmp_path / "last-tick.json")
    paths["api_key_path"] = tmp_path / "nope.key"  # does not exist
    client_factory = make_client_factory()
    escalator = _fake_escalator()
    record = _run.run_tick(
        last_tick_path=tmp_path / "last-tick.json",
        **paths,
        client_factory=client_factory,
        escalator_fn=escalator,
    )
    assert record.fallback_invoked is True
    assert any(
        err["error_type"] == "api_key_missing" for err in record.errors
    )


# ---------------------------------------------------------------------------
# Dry-run path
# ---------------------------------------------------------------------------


def test_run_dry_run_skips_persistence_and_escalation(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    write_last_tick(tmp_path / "last-tick.json")
    client_factory = make_client_factory(
        response_text='{"outcome": "HEARTBEAT_OK", "reason": "dry"}',
    )
    escalator = _fake_escalator()
    record = _run.run_tick(
        last_tick_path=tmp_path / "last-tick.json",
        **paths,
        client_factory=client_factory,
        escalator_fn=escalator,
        dry_run=True,
    )
    assert record.outcome == "HEARTBEAT_OK"
    # Ledger NOT written under dry-run.
    assert not paths["last_decision_path"].exists()
    assert not paths["ledger_path"].exists()
    assert escalator.calls == []  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# main() CLI entrypoint
# ---------------------------------------------------------------------------


def test_main_dry_run_exits_zero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    paths = _make_paths(tmp_path)
    write_last_tick(tmp_path / "last-tick.json")

    # Patch the decide() function so main() does not need a real API call.
    def fake_decide(context, **kwargs):  # type: ignore[no-untyped-def]
        return _gate.GateDecision(
            outcome="HEARTBEAT_OK",
            reason="ok",
            input_tokens=10,
            cache_hit_tokens=5,
            output_tokens=3,
        )

    monkeypatch.setattr(_run._gate, "decide", fake_decide)

    argv = [
        "--last-tick",
        str(tmp_path / "last-tick.json"),
        "--heartbeat-md",
        str(paths["heartbeat_md_path"]),
        "--api-key",
        str(paths["api_key_path"]),
        "--prompt",
        str(paths["prompt_path"]),
        "--last-decision",
        str(paths["last_decision_path"]),
        "--ledger",
        str(paths["ledger_path"]),
        "--dry-run",
    ]
    rc = _run.main(argv)
    captured = capsys.readouterr()
    assert rc == 0
    assert "[DRY-RUN]" in captured.out
    assert "SUMMARY:" in captured.out


def test_main_unhandled_exception_writes_emergency_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    paths = _make_paths(tmp_path)
    write_last_tick(tmp_path / "last-tick.json")

    def boom(**kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("deliberate test failure")

    monkeypatch.setattr(_run, "run_tick", boom)

    # Patch the emergency-path escalator so it doesn't try to shell out.
    monkeypatch.setattr(
        _run._escalator,
        "escalate",
        lambda reason, **kw: EscalationResult(
            escalated_event_id="evt_emergency", error=None
        ),
    )

    argv = [
        "--last-tick",
        str(tmp_path / "last-tick.json"),
        "--heartbeat-md",
        str(paths["heartbeat_md_path"]),
        "--api-key",
        str(paths["api_key_path"]),
        "--prompt",
        str(paths["prompt_path"]),
        "--last-decision",
        str(paths["last_decision_path"]),
        "--ledger",
        str(paths["ledger_path"]),
    ]
    rc = _run.main(argv)
    assert rc == 1
    # Emergency ledger should still have been written.
    assert paths["last_decision_path"].exists()
    payload = json.loads(paths["last_decision_path"].read_text())
    assert payload["fallback_invoked"] is True
    assert payload["errors"][0]["error_type"] == "unhandled_exception"


def test_summary_line_includes_token_counts(tmp_path: Path) -> None:
    record = GateTickRecord(
        tick_id="01J",
        started_at_utc="2026-06-01T00:00:00Z",
        gate_latency_ms=1234,
        digest_snapshot_at_utc="2026-06-01T00:00:00Z",
        heartbeat_md_state="empty",
        outcome="HEARTBEAT_OK",
        reason="ok",
        gate_input_tokens=120,
        gate_cache_hit_tokens=100,
        gate_output_tokens=8,
    )
    line = _run._summary_line(record, dry_run=False)
    assert "outcome=HEARTBEAT_OK" in line
    assert "fallback=False" in line
    assert "dur=1234ms" in line
    assert "in:120" in line
    assert "cache:100" in line
    assert "out:8" in line


# ---------------------------------------------------------------------------
# new_tick_id
# ---------------------------------------------------------------------------


def test_new_tick_id_length_and_alphabet() -> None:
    tick_id = _run.new_tick_id(datetime(2026, 6, 1, tzinfo=timezone.utc))
    assert len(tick_id) == 26
    # Crockford Base32 alphabet (excludes I, L, O, U).
    valid_chars = set("0123456789ABCDEFGHJKMNPQRSTVWXYZ")
    assert set(tick_id).issubset(valid_chars)


def test_new_tick_id_is_unique_in_quick_succession() -> None:
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    ids = {_run.new_tick_id(now) for _ in range(20)}
    assert len(ids) == 20
