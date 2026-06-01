"""Tests for ``heartbeat_gate.ledger`` (WP-03 T021)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.openclaw.heartbeat_gate.ledger import (
    GateTickRecord,
    SCHEMA_VERSION,
    append_ledger,
    atomic_write_json,
    write_tick_record,
)


def _base_record(**overrides) -> GateTickRecord:
    defaults = dict(
        tick_id="01JTICK",
        started_at_utc="2026-06-01T17:30:00Z",
        gate_latency_ms=1240,
        digest_snapshot_at_utc="2026-06-01T17:15:00Z",
        heartbeat_md_state="empty",
        novelty_markers_seen=[],
        outcome="HEARTBEAT_OK",
        reason="all clean",
        escalated_event_id=None,
        gate_input_tokens=120,
        gate_cache_hit_tokens=100,
        gate_output_tokens=8,
        fallback_invoked=False,
        errors=[],
    )
    defaults.update(overrides)
    return GateTickRecord(**defaults)


def test_to_payload_includes_schema_version() -> None:
    record = _base_record()
    payload = record.to_payload()
    assert payload["schema_version"] == SCHEMA_VERSION


def test_to_payload_matches_contract_keys() -> None:
    record = _base_record()
    payload = record.to_payload()
    expected_keys = {
        "schema_version",
        "tick_id",
        "started_at_utc",
        "gate_latency_ms",
        "digest_snapshot_at_utc",
        "heartbeat_md_state",
        "novelty_markers_seen",
        "outcome",
        "reason",
        "escalated_event_id",
        "gate_input_tokens",
        "gate_cache_hit_tokens",
        "gate_output_tokens",
        "fallback_invoked",
        "errors",
    }
    assert set(payload.keys()) == expected_keys


def test_atomic_write_json_creates_target(tmp_path: Path) -> None:
    target = tmp_path / "out" / "last-gate-decision.json"
    payload = {"schema_version": 1, "outcome": "HEARTBEAT_OK"}
    atomic_write_json(target, payload)
    assert target.exists()
    reread = json.loads(target.read_text(encoding="utf-8"))
    assert reread == payload


def test_atomic_write_json_overwrites_existing(tmp_path: Path) -> None:
    target = tmp_path / "last.json"
    target.write_text(json.dumps({"old": True}))
    atomic_write_json(target, {"new": True})
    assert json.loads(target.read_text()) == {"new": True}


def test_atomic_write_json_leaves_no_tempfiles(tmp_path: Path) -> None:
    target = tmp_path / "last.json"
    atomic_write_json(target, {"a": 1})
    # No leftover .tmp files (the rename atomically replaces).
    leftover = [p for p in tmp_path.iterdir() if p.suffix == ".tmp"]
    assert leftover == []


def test_append_ledger_creates_and_appends(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    append_ledger(ledger, {"tick": 1})
    append_ledger(ledger, {"tick": 2})
    lines = ledger.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"tick": 1}
    assert json.loads(lines[1]) == {"tick": 2}


def test_write_tick_record_writes_both_artifacts(tmp_path: Path) -> None:
    record = _base_record()
    last = tmp_path / "last-gate-decision.json"
    ledger = tmp_path / "gate-ledger.jsonl"
    write_tick_record(record, last, ledger)
    last_payload = json.loads(last.read_text(encoding="utf-8"))
    assert last_payload["tick_id"] == "01JTICK"
    assert last_payload["schema_version"] == SCHEMA_VERSION
    ledger_lines = ledger.read_text(encoding="utf-8").splitlines()
    assert len(ledger_lines) == 1
    assert json.loads(ledger_lines[0])["tick_id"] == "01JTICK"


def test_write_tick_record_appends_multiple_ledger_rows(
    tmp_path: Path,
) -> None:
    last = tmp_path / "last.json"
    ledger = tmp_path / "ledger.jsonl"
    write_tick_record(_base_record(tick_id="01J1"), last, ledger)
    write_tick_record(_base_record(tick_id="01J2"), last, ledger)
    lines = ledger.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["tick_id"] == "01J1"
    assert json.loads(lines[1])["tick_id"] == "01J2"
    # The last-decision file reflects only the most recent write.
    assert json.loads(last.read_text())["tick_id"] == "01J2"


def test_write_tick_record_rejects_invalid_outcome(tmp_path: Path) -> None:
    # Bypass the dataclass type hint to construct an invalid record.
    bad = _base_record(outcome="NOT_AN_OUTCOME")
    with pytest.raises(ValueError):
        write_tick_record(bad, tmp_path / "last.json", tmp_path / "l.jsonl")


def test_write_tick_record_rejects_invalid_heartbeat_state(
    tmp_path: Path,
) -> None:
    bad = _base_record(heartbeat_md_state="bogus")
    with pytest.raises(ValueError):
        write_tick_record(bad, tmp_path / "last.json", tmp_path / "l.jsonl")


def test_record_serializes_with_fallback_invoked(tmp_path: Path) -> None:
    record = _base_record(
        outcome="ESCALATE_TO_SONNET",
        reason="Gate fallback — see ledger",
        fallback_invoked=True,
        errors=[
            {
                "error_type": "gate_routing_failed",
                "error_message": "RateLimitError exhausted",
            }
        ],
        gate_input_tokens=0,
        gate_cache_hit_tokens=0,
        gate_output_tokens=0,
    )
    last = tmp_path / "last.json"
    ledger = tmp_path / "ledger.jsonl"
    write_tick_record(record, last, ledger)
    payload = json.loads(last.read_text())
    assert payload["fallback_invoked"] is True
    assert payload["errors"][0]["error_type"] == "gate_routing_failed"
    assert payload["gate_input_tokens"] == 0


def test_ledger_preserves_unicode_in_reason(tmp_path: Path) -> None:
    record = _base_record(reason="Reason with em — dash and ümlauts")
    last = tmp_path / "last.json"
    ledger = tmp_path / "ledger.jsonl"
    write_tick_record(record, last, ledger)
    line = json.loads(ledger.read_text(encoding="utf-8").splitlines()[0])
    assert "ümlauts" in line["reason"]
