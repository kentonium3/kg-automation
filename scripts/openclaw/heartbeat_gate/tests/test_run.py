"""End-to-end tests for ``heartbeat_gate.run`` (#676 -- deterministic gate).

These tests exercise the orchestrator with the escalator mocked (via
the ``escalator_fn`` override). The gate decision itself is no longer
an external dependency -- ``decide_deterministic`` is pure Python, so
these tests drive it via real ``last-tick.json`` / ``HEARTBEAT.md``
fixtures rather than a fake LLM client.
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
from scripts.openclaw.heartbeat_gate.tests.conftest import write_last_tick


def _make_paths(tmp_path: Path) -> dict[str, Path]:
    """Common path bundle for run_tick calls."""
    return {
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

    escalator = _fake_escalator()
    record = _run.run_tick(
        last_tick_path=tmp_path / "last-tick.json",
        **paths,
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
    # No LLM call in the tick path -- tokens are always zero.
    assert payload["gate_input_tokens"] == 0
    assert payload["gate_cache_hit_tokens"] == 0
    assert payload["gate_output_tokens"] == 0


def test_run_log_and_skip_no_escalation(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    write_last_tick(
        tmp_path / "last-tick.json",
        issues_filed=[
            {"signal_id": "whatsapp_creds_restore", "issue_number": 491}
        ],
    )
    escalator = _fake_escalator()
    record = _run.run_tick(
        last_tick_path=tmp_path / "last-tick.json",
        **paths,
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
    escalator = _fake_escalator(event_id="evt_42")
    record = _run.run_tick(
        last_tick_path=tmp_path / "last-tick.json",
        **paths,
        escalator_fn=escalator,
    )
    assert record.outcome == "ESCALATE_TO_SONNET"
    assert record.fallback_invoked is False
    assert record.escalated_event_id == "evt_42"
    # Escalator received the gate's reason, citing the novelty marker.
    assert "whatsapp_creds_restore" in escalator.calls[0][0]  # type: ignore[attr-defined]
    # novelty_markers recorded in ledger.
    payload = json.loads(paths["last_decision_path"].read_text())
    assert payload["novelty_markers_seen"] == ["whatsapp_creds_restore"]


def test_run_escalate_on_heartbeat_has_tasks(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    write_last_tick(tmp_path / "last-tick.json")
    paths["heartbeat_md_path"].write_text("Please check the mail backlog.\n")

    escalator = _fake_escalator(event_id="evt_task")
    record = _run.run_tick(
        last_tick_path=tmp_path / "last-tick.json",
        **paths,
        escalator_fn=escalator,
    )
    assert record.outcome == "ESCALATE_TO_SONNET"
    assert "heartbeat contract has tasks" in escalator.calls[0][0]  # type: ignore[attr-defined]


def test_run_escalator_failure_recorded_in_errors(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    write_last_tick(
        tmp_path / "last-tick.json",
        errors=[{"error_type": "source_missing", "error_message": "x"}],
    )
    escalator = _fake_escalator(event_id=None, error="openclaw not on path")
    record = _run.run_tick(
        last_tick_path=tmp_path / "last-tick.json",
        **paths,
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
    escalator = _fake_escalator(event_id="evt_fallback")

    record = _run.run_tick(
        last_tick_path=tmp_path / "nope.json",
        **paths,
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
    escalator = _fake_escalator(event_id="evt_fb")

    record = _run.run_tick(
        last_tick_path=tmp_path / "last-tick.json",
        **paths,
        escalator_fn=escalator,
    )
    assert record.fallback_invoked is True
    assert any(
        err["error_type"] == "context_load_failed" for err in record.errors
    )


def test_run_fallback_on_valid_but_wrong_shaped_tick(tmp_path: Path) -> None:
    """Valid JSON but the wrong SHAPE (a top-level array instead of an
    object) makes ``context.load_context`` raise AttributeError/TypeError,
    NOT JSONDecodeError. Regression guard for post-merge Codex #1: step 1's
    broadened ``except Exception`` must route this to the fail-safe
    (fallback_invoked=True) rather than escaping to the exit-1 emergency
    path -- FR-007.
    """
    paths = _make_paths(tmp_path)
    (tmp_path / "last-tick.json").write_text("[]")  # valid JSON, wrong shape
    paths["heartbeat_md_path"].write_text("")
    escalator = _fake_escalator(event_id="evt_ws")

    record = _run.run_tick(
        last_tick_path=tmp_path / "last-tick.json",
        **paths,
        escalator_fn=escalator,
    )
    assert record.fallback_invoked is True
    assert record.outcome == "ESCALATE_TO_SONNET"
    assert record.gate_input_tokens == 0
    assert any(
        err["error_type"] == "context_load_failed" for err in record.errors
    )
    assert paths["ledger_path"].exists()


def test_run_fallback_on_malformed_context_proves_decide_fail_safe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Malformed-but-loaded tick payload: step 1 succeeds (context loads),
    but ``decide_deterministic`` is monkeypatched to raise, simulating an
    unanticipated implementation bug. Proves step 2's broadened
    ``except Exception`` routes to the FAIL-SAFE fallback path
    (``fallback_invoked=True``, exit 0 at the CLI layer) -- NOT the
    unhandled-exception emergency path (exit 1). This is the load-bearing
    test for Codex finding #2 / FR-007.
    """
    paths = _make_paths(tmp_path)
    write_last_tick(tmp_path / "last-tick.json")

    def _boom(context: Any) -> _gate.GateDecision:
        raise TypeError("simulated implementation bug in decide_deterministic")

    monkeypatch.setattr(_run._gate, "decide_deterministic", _boom)

    escalator = _fake_escalator(event_id="evt_malformed")
    record = _run.run_tick(
        last_tick_path=tmp_path / "last-tick.json",
        **paths,
        escalator_fn=escalator,
    )

    assert record.fallback_invoked is True
    assert record.outcome == "ESCALATE_TO_SONNET"
    assert record.reason == _run.FALLBACK_REASON_DEFAULT
    assert record.gate_input_tokens == 0
    assert record.escalated_event_id == "evt_malformed"
    assert any(
        err["error_type"] == "gate_decision_failed" for err in record.errors
    )
    # Ledger written -- the fail-safe path always persists.
    assert paths["last_decision_path"].exists()
    assert paths["ledger_path"].exists()

    # Now prove the SAME scenario exits 0 through main(), not 1 -- the
    # fail-safe, not the emergency exit-1 path.
    argv = [
        "--last-tick",
        str(tmp_path / "last-tick.json"),
        "--heartbeat-md",
        str(paths["heartbeat_md_path"]),
        "--last-decision",
        str(paths["last_decision_path"]),
        "--ledger",
        str(paths["ledger_path"]),
    ]
    monkeypatch.setattr(
        _run._escalator,
        "escalate",
        lambda reason, **kw: EscalationResult(
            escalated_event_id="evt_malformed_cli", error=None
        ),
    )
    rc = _run.main(argv)
    assert rc == 0


# ---------------------------------------------------------------------------
# Dry-run path
# ---------------------------------------------------------------------------


def test_run_dry_run_skips_persistence_and_escalation(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    write_last_tick(tmp_path / "last-tick.json")
    escalator = _fake_escalator()
    record = _run.run_tick(
        last_tick_path=tmp_path / "last-tick.json",
        **paths,
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
    capsys: pytest.CaptureFixture,
) -> None:
    paths = _make_paths(tmp_path)
    write_last_tick(tmp_path / "last-tick.json")

    argv = [
        "--last-tick",
        str(tmp_path / "last-tick.json"),
        "--heartbeat-md",
        str(paths["heartbeat_md_path"]),
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
    # No LLM in the tick path -- tokens print as zero.
    assert "tokens=in:0(cache:0)/out:0" in captured.out


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
        gate_input_tokens=0,
        gate_cache_hit_tokens=0,
        gate_output_tokens=0,
    )
    line = _run._summary_line(record, dry_run=False)
    assert "outcome=HEARTBEAT_OK" in line
    assert "fallback=False" in line
    assert "dur=1234ms" in line
    assert "in:0" in line
    assert "cache:0" in line
    assert "out:0" in line


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
