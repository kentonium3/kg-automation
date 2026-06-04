"""Tests for scripts/sync/emit.py (WP04 / T017).

Covers event_id determinism, validation, JSONL append, guard interaction
paths, delivery dispatch, G-3 increment semantics, and privacy redaction.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from scripts.sync import emit as e
from scripts.sync.classify import CLASS_AUTO_RESOLVED, CLASS_UNSAFE, ClassifiedConflict
from scripts.sync.diff import DivergenceCandidate
from scripts.sync.send_whatsapp import SendResult
from scripts.sync.state import (
    G3DailyCap,
    GuardState,
    TaskCacheEntry,
    TaskCacheRecord,
)


CYCLE_STARTED = datetime(2026, 6, 4, 19, 25, 30, tzinfo=timezone.utc)
TS_OBSERVED = "2026-06-04T19:25:30Z"
TODAY_ET = "2026-06-04"
TICK_ID = "01KTA1J3FH87XJWT7FQPT1EZE7"


def _candidate(field: str = "due_date", entity_id: int = 14, updated: str = "2026-06-04T18:32:00Z") -> DivergenceCandidate:
    return DivergenceCandidate(
        vikunja_entity_id=entity_id,
        field=field,
        vikunja_value="new-value",
        felix_cached_value="old-value",
        vikunja_updated_at=updated,
        ts_observed_utc=TS_OBSERVED,
    )


def _classified(*, class_: str = CLASS_UNSAFE, reasons=("uc1_uc2_divergence", "uc3_downstream_behavior"), candidate=None) -> ClassifiedConflict:
    return ClassifiedConflict(
        candidate=candidate or _candidate(),
        class_=class_,
        unsafe_reasons=tuple(reasons),
    )


def _guard_state(*, count: int = 0, cap: int = 5, day: str = TODAY_ET) -> GuardState:
    return GuardState(
        g3_daily_cap=G3DailyCap(
            calendar_day_et=day,
            unsafe_pings_sent_today=count,
            cap=cap,
        ),
    )


def _task_cache(*, last_observed: str | None = None, task_id: int = 14) -> TaskCacheRecord:
    if last_observed is None:
        return TaskCacheRecord(last_updated_utc="2026-06-04T19:20:30Z", tasks={})
    return TaskCacheRecord(
        last_updated_utc="2026-06-04T19:20:30Z",
        tasks={
            str(task_id): TaskCacheEntry(
                vikunja_task_id=task_id,
                fields={},
                vikunja_updated_at="2026-06-04T18:32:00Z",
                felix_last_observed_at=last_observed,
            ),
        },
    )


def _mock_send(success: bool = True, exit_code: int = 0, stderr: str | None = None):
    mock = MagicMock()
    mock.return_value = SendResult(success=success, exit_code=exit_code, stderr=stderr)
    return mock


# ===========================================================================
# Group 1 — compute_event_id
# ===========================================================================


class TestComputeEventId:
    def test_deterministic(self):
        a = e.compute_event_id("status_and_task", 14, "due_date", TS_OBSERVED, "x")
        b = e.compute_event_id("status_and_task", 14, "due_date", TS_OBSERVED, "x")
        assert a == b

    def test_format_16_char_lowercase_hex(self):
        eid = e.compute_event_id("status_and_task", 14, "title", TS_OBSERVED, "x")
        assert len(eid) == 16
        assert all(c in "0123456789abcdef" for c in eid)

    def test_value_change_yields_different_id(self):
        a = e.compute_event_id("status_and_task", 14, "title", TS_OBSERVED, "x")
        b = e.compute_event_id("status_and_task", 14, "title", TS_OBSERVED, "y")
        assert a != b


# ===========================================================================
# Group 2 — validate_event
# ===========================================================================


def _valid_event(**overrides) -> e.ConflictEvent:
    defaults = dict(
        event_id="a" * 16,
        schema_version=1,
        tick_id=TICK_ID,
        ts_observed_utc=TS_OBSERVED,
        layer="status_and_task",
        vikunja_entity_id=14,
        diff_field="title",
        vikunja_value="new",
        felix_cached_value="old",
        class_=CLASS_UNSAFE,
        unsafe_reasons=("uc1_uc2_divergence",),
        router_route_set=("whatsapp",),
        delivery_status=e.DS_DELIVERED,
        vikunja_updated_at="2026-06-04T18:32:00Z",
        delivery_error=None,
    )
    defaults.update(overrides)
    return e.ConflictEvent(**defaults)


class TestValidateEvent:
    def test_valid_event_passes(self):
        e.validate_event(_valid_event())

    def test_wrong_event_id_length_fails(self):
        with pytest.raises(OSError, match="16-char"):
            e.validate_event(_valid_event(event_id="short"))

    def test_non_hex_event_id_fails(self):
        with pytest.raises(OSError, match="lowercase hex"):
            e.validate_event(_valid_event(event_id="Z" * 16))

    def test_wrong_schema_version_fails(self):
        with pytest.raises(OSError, match="schema_version"):
            e.validate_event(_valid_event(schema_version=2))

    def test_invalid_class_fails(self):
        with pytest.raises(OSError, match="class_"):
            e.validate_event(_valid_event(class_="bogus"))

    def test_invalid_delivery_status_fails(self):
        with pytest.raises(OSError, match="delivery_status"):
            e.validate_event(_valid_event(delivery_status="weird"))

    def test_error_status_requires_error_message(self):
        with pytest.raises(OSError, match="error.*requires.*non-null"):
            e.validate_event(_valid_event(delivery_status=e.DS_ERROR, delivery_error=None))

    def test_non_error_status_must_have_null_error(self):
        with pytest.raises(OSError, match="requires delivery_error to be None"):
            e.validate_event(
                _valid_event(delivery_status=e.DS_DELIVERED, delivery_error="something")
            )


# ===========================================================================
# Group 3 — read_recent_events
# ===========================================================================


class TestReadRecentEvents:
    def test_missing_file_returns_empty(self, tmp_path):
        result = e.read_recent_events(tmp_path / "nope.jsonl", CYCLE_STARTED)
        assert result == []

    def test_filters_to_window(self, tmp_path):
        path = tmp_path / "events.jsonl"
        with open(path, "w", encoding="utf-8") as f:
            # 1h ago — in window.
            f.write(json.dumps({"event_id": "a", "ts_observed_utc": "2026-06-04T18:25:30Z"}) + "\n")
            # 25h ago — outside window.
            f.write(json.dumps({"event_id": "b", "ts_observed_utc": "2026-06-03T18:25:30Z"}) + "\n")
        result = e.read_recent_events(path, CYCLE_STARTED, lookback_hours=24)
        assert [r["event_id"] for r in result] == ["a"]

    def test_skips_malformed_lines(self, tmp_path):
        path = tmp_path / "events.jsonl"
        with open(path, "w", encoding="utf-8") as f:
            f.write("not json\n")
            f.write(json.dumps({"event_id": "ok", "ts_observed_utc": "2026-06-04T18:25:30Z"}) + "\n")
            f.write("\n")  # blank
            f.write(json.dumps({"ts_observed_utc": "bad-date"}) + "\n")
        result = e.read_recent_events(path, CYCLE_STARTED)
        assert [r["event_id"] for r in result] == ["ok"]


# ===========================================================================
# Group 4 — emit_events: auto_resolved path (no delivery)
# ===========================================================================


class TestEmitAutoResolved:
    def test_appends_without_invoking_send(self, tmp_path):
        path = tmp_path / "events.jsonl"
        send = _mock_send()
        committed, updated_gs = e.emit_events(
            classified_conflicts=[_classified(class_=CLASS_AUTO_RESOLVED, reasons=("uc1_uc2_divergence", "uc4_manual_override"))],
            tick_id=TICK_ID,
            ts_observed_utc=TS_OBSERVED,
            jsonl_path=path,
            task_cache=_task_cache(last_observed=None),
            guard_state=_guard_state(),
            recent_events=[],
            send_callable=send,
            recipient="+15551234567",
            cycle_started_at=CYCLE_STARTED,
            now_et_day_str=TODAY_ET,
        )
        assert send.call_count == 0
        assert len(committed) == 1
        assert committed[0].delivery_status == e.DS_NOT_UNSAFE
        # JSONL has one row.
        lines = path.read_text().splitlines()
        assert len(lines) == 1


# ===========================================================================
# Group 5 — emit_events: unsafe approved
# ===========================================================================


class TestEmitUnsafeDelivered:
    def test_send_invoked_and_status_delivered(self, tmp_path):
        path = tmp_path / "events.jsonl"
        send = _mock_send()
        committed, updated_gs = e.emit_events(
            classified_conflicts=[_classified()],
            tick_id=TICK_ID,
            ts_observed_utc=TS_OBSERVED,
            jsonl_path=path,
            task_cache=_task_cache(last_observed=None),
            guard_state=_guard_state(),
            recent_events=[],
            send_callable=send,
            recipient="+15551234567",
            cycle_started_at=CYCLE_STARTED,
            now_et_day_str=TODAY_ET,
            task_lookup={14: {"title": "Buy gift", "project_id": 13}},
        )
        assert send.call_count == 1
        kwargs = send.call_args.kwargs
        assert kwargs["recipient"] == "+15551234567"
        # The message contains the task title.
        assert "Buy gift" in kwargs["message"]
        assert committed[0].delivery_status == e.DS_DELIVERED
        # G-3 incremented on delivery.
        assert updated_gs.g3_daily_cap.unsafe_pings_sent_today == 1


# ===========================================================================
# Group 6 — Guard suppression
# ===========================================================================


class TestGuardSuppression:
    def test_g3_cap_suppresses(self, tmp_path):
        path = tmp_path / "events.jsonl"
        send = _mock_send()
        committed, updated_gs = e.emit_events(
            classified_conflicts=[_classified()],
            tick_id=TICK_ID,
            ts_observed_utc=TS_OBSERVED,
            jsonl_path=path,
            task_cache=_task_cache(last_observed=None),
            guard_state=_guard_state(count=5, cap=5),  # at cap
            recent_events=[],
            send_callable=send,
            recipient="+15551234567",
            cycle_started_at=CYCLE_STARTED,
            now_et_day_str=TODAY_ET,
        )
        assert send.call_count == 0
        assert committed[0].delivery_status == e.DS_SUPPRESSED_G3
        # G-3 count NOT incremented on suppression.
        assert updated_gs.g3_daily_cap.unsafe_pings_sent_today == 5

    def test_g2_window_suppresses(self, tmp_path):
        path = tmp_path / "events.jsonl"
        send = _mock_send()
        # Felix wrote 5 min ago → within G-2 window.
        cache = _task_cache(last_observed=(CYCLE_STARTED - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ"))
        committed, _ = e.emit_events(
            classified_conflicts=[_classified()],
            tick_id=TICK_ID,
            ts_observed_utc=TS_OBSERVED,
            jsonl_path=path,
            task_cache=cache,
            guard_state=_guard_state(),
            recent_events=[],
            send_callable=send,
            recipient="+15551234567",
            cycle_started_at=CYCLE_STARTED,
            now_et_day_str=TODAY_ET,
        )
        assert send.call_count == 0
        assert committed[0].delivery_status == e.DS_SUPPRESSED_G2


# ===========================================================================
# Group 7 — Delivery error
# ===========================================================================


class TestDeliveryError:
    def test_send_failure_records_error_status(self, tmp_path):
        path = tmp_path / "events.jsonl"
        send = _mock_send(success=False, exit_code=1, stderr="openclaw broke")
        committed, updated_gs = e.emit_events(
            classified_conflicts=[_classified()],
            tick_id=TICK_ID,
            ts_observed_utc=TS_OBSERVED,
            jsonl_path=path,
            task_cache=_task_cache(last_observed=None),
            guard_state=_guard_state(),
            recent_events=[],
            send_callable=send,
            recipient="+15551234567",
            cycle_started_at=CYCLE_STARTED,
            now_et_day_str=TODAY_ET,
        )
        assert send.call_count == 1
        assert committed[0].delivery_status == e.DS_ERROR
        assert committed[0].delivery_error == "openclaw broke"
        # G-3 NOT incremented on failure.
        assert updated_gs.g3_daily_cap.unsafe_pings_sent_today == 0


# ===========================================================================
# Group 8 — Privacy redaction
# ===========================================================================


class TestPrivacyRedaction:
    def test_private_task_redacted_in_event(self, tmp_path):
        path = tmp_path / "events.jsonl"
        send = _mock_send()
        committed, _ = e.emit_events(
            classified_conflicts=[_classified(candidate=_candidate(entity_id=99))],
            tick_id=TICK_ID,
            ts_observed_utc=TS_OBSERVED,
            jsonl_path=path,
            task_cache=_task_cache(last_observed=None),
            guard_state=_guard_state(),
            recent_events=[],
            send_callable=send,
            recipient="+15551234567",
            cycle_started_at=CYCLE_STARTED,
            now_et_day_str=TODAY_ET,
            task_lookup={99: {"title": "VerySecret", "project_id": 7}},
            private_project_ids=frozenset({7}),
        )
        event = committed[0]
        assert event.vikunja_value == "<redacted>"
        assert event.felix_cached_value == "<redacted>"
        assert event.diff_field == "<redacted>"
        # Task ID still exposed (no semantic content).
        assert event.vikunja_entity_id == 99
        # The send call's message must NOT include "VerySecret".
        message = send.call_args.kwargs["message"]
        assert "VerySecret" not in message
        assert "<redacted>" in message


# ===========================================================================
# Group 9 — Processing order
# ===========================================================================


class TestProcessingOrder:
    def test_sorted_by_vikunja_updated_at_ascending(self, tmp_path):
        path = tmp_path / "events.jsonl"
        send = _mock_send()
        # Three conflicts with vikunja_updated_at in reverse order.
        c1 = _classified(candidate=_candidate(field="title", entity_id=10, updated="2026-06-04T18:30:00Z"))
        c2 = _classified(candidate=_candidate(field="title", entity_id=20, updated="2026-06-04T18:20:00Z"))
        c3 = _classified(candidate=_candidate(field="title", entity_id=30, updated="2026-06-04T18:40:00Z"))
        committed, _ = e.emit_events(
            classified_conflicts=[c1, c2, c3],
            tick_id=TICK_ID,
            ts_observed_utc=TS_OBSERVED,
            jsonl_path=path,
            task_cache=_task_cache(last_observed=None),
            guard_state=_guard_state(),
            recent_events=[],
            send_callable=send,
            recipient="+15551234567",
            cycle_started_at=CYCLE_STARTED,
            now_et_day_str=TODAY_ET,
        )
        # JSONL rows appear in ascending vikunja_updated_at order: c2, c1, c3.
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        assert [r["vikunja_entity_id"] for r in rows] == [20, 10, 30]


# ===========================================================================
# Group 10 — Validation failure blocks append
# ===========================================================================


class TestValidationBlocksAppend:
    def test_invalid_event_raises_and_no_append(self, tmp_path):
        # Force validation failure by constructing an unsafe event with a
        # delivery_status that requires a delivery_error.
        # Simulate by patching build_event to return a bad row.
        path = tmp_path / "events.jsonl"
        send = _mock_send()

        # Monkeypatch build_event to inject an invalid row.
        orig_build = e.build_event

        def _bad_build(**kwargs):
            ev = orig_build(**kwargs)
            # Force invalid: error status but no delivery_error.
            return e.ConflictEvent(
                event_id=ev.event_id,
                schema_version=ev.schema_version,
                tick_id=ev.tick_id,
                ts_observed_utc=ev.ts_observed_utc,
                layer=ev.layer,
                vikunja_entity_id=ev.vikunja_entity_id,
                diff_field=ev.diff_field,
                vikunja_value=ev.vikunja_value,
                felix_cached_value=ev.felix_cached_value,
                class_=ev.class_,
                unsafe_reasons=ev.unsafe_reasons,
                router_route_set=ev.router_route_set,
                delivery_status=e.DS_ERROR,  # but delivery_error stays None
                vikunja_updated_at=ev.vikunja_updated_at,
                delivery_error=None,
            )

        import scripts.sync.emit as emit_mod
        emit_mod.build_event = _bad_build
        try:
            with pytest.raises(OSError, match="error.*requires.*non-null"):
                e.emit_events(
                    classified_conflicts=[_classified(class_=CLASS_AUTO_RESOLVED)],
                    tick_id=TICK_ID,
                    ts_observed_utc=TS_OBSERVED,
                    jsonl_path=path,
                    task_cache=_task_cache(last_observed=None),
                    guard_state=_guard_state(),
                    recent_events=[],
                    send_callable=send,
                    recipient="+15551234567",
                    cycle_started_at=CYCLE_STARTED,
                    now_et_day_str=TODAY_ET,
                )
        finally:
            emit_mod.build_event = orig_build
        # JSONL file should not exist or be empty.
        if path.exists():
            assert path.read_text() == ""
