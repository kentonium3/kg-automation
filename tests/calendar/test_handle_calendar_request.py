"""Tests for ``scripts.calendar_routing.handle_calendar_request``.

The orchestrator reads an ``ExtractedCalendarBlock`` from stdin, classifies it
(conversational create / conversational clarify / clarification / ambiguous),
and drives the deterministic create + cleanup. Every external side effect is a
module-level seam (``_invoke_calendar_helper``, ``_invoke_remove_record``,
``_invoke_mark_processed``, ``_invoke_log_action``); these tests monkeypatch
those so no subprocess, Google API, or filesystem note is ever touched.

Tests drive ``main()`` in-process (stdin/stdout patched) — the existing
``tests/calendar`` / ``tests/inbox`` convention — which also measures coverage
of the CLI surface honestly.

The #836 crux (test 3): a clarification reply supplies the TIME while the
pending record supplies the DATE; the merge must yield the record's date at the
reply's time. A blind field overwrite would drop the date — the exact bug.
"""
from __future__ import annotations

import io
import json
import sys
from datetime import datetime, timedelta, timezone

import pytest

from scripts.calendar_routing import handle_calendar_request as hcr


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


def _run(monkeypatch, block, argv=None) -> tuple[int, dict, str]:
    """Drive ``main`` with ``block`` on stdin; return (code, parsed_stdout, stderr)."""
    stdin_text = block if isinstance(block, str) else json.dumps(block)
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin_text))
    monkeypatch.setattr(sys, "stdout", stdout_buf)
    monkeypatch.setattr(sys, "stderr", stderr_buf)
    code = hcr.main(argv or [])
    out = stdout_buf.getvalue()
    parsed = json.loads(out) if out.strip() else {}
    return code, parsed, stderr_buf.getvalue()


class _Seams:
    """Records seam calls and returns canned successes."""

    def __init__(self):
        self.created_payloads: list = []
        self.created_keys: list = []
        self.removed: list = []
        self.marked: list = []
        self.log_calls: list = []
        self.helper_result = {"status": "created", "event_id": "E1", "html_link": "L1"}

    def install(self, monkeypatch):
        def fake_helper(payload, idempotency_key, account):
            self.created_payloads.append(payload)
            self.created_keys.append(idempotency_key)
            return self.helper_result

        def fake_remove(note_filename, state_file):
            self.removed.append(note_filename)
            return True

        def fake_mark(source_path):
            self.marked.append(source_path)
            return True

        def fake_log(agent, category, action, target, outcome, context):
            self.log_calls.append(
                {
                    "agent": agent,
                    "category": category,
                    "action": action,
                    "target": target,
                    "outcome": outcome,
                    "context": context,
                }
            )

        monkeypatch.setattr(hcr, "_invoke_calendar_helper", fake_helper)
        monkeypatch.setattr(hcr, "_invoke_remove_record", fake_remove)
        monkeypatch.setattr(hcr, "_invoke_mark_processed", fake_mark)
        monkeypatch.setattr(hcr, "_invoke_log_action", fake_log)
        return self

    @property
    def actions(self):
        return [c["action"] for c in self.log_calls]


@pytest.fixture
def seams(monkeypatch):
    return _Seams().install(monkeypatch)


def _iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _record(title, start_natural, *, note_filename="felix-smoke.md",
            source_inbox_path="/inbox/vault/felix-smoke.md", created_at=None):
    partial = {
        "title": title,
        "start_natural": start_natural,
        "source_inbox_path": source_inbox_path,
        "source_block_index": 0,
    }
    return {
        "note_filename": note_filename,
        "partial_payload": partial,
        "created_at": created_at or _iso_z(datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)),
    }


def _seed_state(tmp_path, records):
    state = tmp_path / "pending.json"
    state.write_text(json.dumps(records), encoding="utf-8")
    return state


def _empty_state(tmp_path):
    return _seed_state(tmp_path, [])


# ---------------------------------------------------------------------------
# 1. Conversational COMPLETE — summer + winter (no double offset)
# ---------------------------------------------------------------------------


def test_conversational_complete_summer(seams, monkeypatch, tmp_path):
    state = _empty_state(tmp_path)
    code, out, err = _run(
        monkeypatch,
        {"title": "meet Bob", "start_natural": "tomorrow at 2pm", "duration_natural": "1 hour"},
        ["--state-file", str(state), "--now-iso", "2026-07-15T12:00:00-04:00"],
    )
    assert code == 0, err
    assert out["status"] == "created"
    assert out["mode"] == "conversational"
    assert out["event_id"] == "E1"
    # No cleanup block for conversational creates.
    assert "cleanup" not in out
    # ET summer offset is -04:00 (EDT) — proves no double offset.
    payload = seams.created_payloads[0]
    assert payload["start_rfc3339"] == "2026-07-16T14:00:00-04:00"
    assert out["start"] == "2026-07-16T14:00:00-04:00"
    # Synthetic conversational idempotency key, not a record path.
    assert seams.created_keys[0].startswith("conversational-")
    assert "calendar_event_created" in seams.actions


def test_conversational_complete_winter(seams, monkeypatch, tmp_path):
    state = _empty_state(tmp_path)
    code, out, err = _run(
        monkeypatch,
        {"title": "meet Bob", "start_natural": "tomorrow at 2pm", "duration_natural": "1 hour"},
        ["--state-file", str(state), "--now-iso", "2026-01-15T12:00:00-05:00"],
    )
    assert code == 0, err
    payload = seams.created_payloads[0]
    # ET winter offset is -05:00 (EST) — same wall time, correct offset.
    assert payload["start_rfc3339"] == "2026-01-16T14:00:00-05:00"
    assert out["start"] == "2026-01-16T14:00:00-05:00"


# ---------------------------------------------------------------------------
# 2. Conversational INCOMPLETE — no records
# ---------------------------------------------------------------------------


def test_conversational_incomplete_no_records(seams, monkeypatch, tmp_path):
    state = _empty_state(tmp_path)
    code, out, err = _run(
        monkeypatch,
        {"title": "lunch", "start_natural": "Thursday"},
        ["--state-file", str(state), "--now-iso", "2026-07-15T12:00:00-04:00"],
    )
    assert code == 0, err
    assert out["status"] == "needs_clarification"
    assert out["mode"] == "conversational"
    assert "start_time" in out["missing"]
    # No create, no record cleanup.
    assert seams.created_payloads == []
    assert seams.removed == []
    assert seams.marked == []


# ---------------------------------------------------------------------------
# 3. Clarification SOLE-MATCH — the #836 crux (record date + reply time)
# ---------------------------------------------------------------------------


def test_clarification_sole_match_combines_date_and_time(seams, monkeypatch, tmp_path):
    state = _seed_state(
        tmp_path,
        [_record("Felix live smoke", "July 25",
                 note_filename="felix-smoke.md",
                 source_inbox_path="/inbox/vault/felix-smoke.md")],
    )
    code, out, err = _run(
        monkeypatch,
        {"title": "Felix live smoke", "start_natural": "2pm", "duration_natural": "1 hour"},
        ["--state-file", str(state), "--now-iso", "2026-07-20T12:00:00-04:00"],
    )
    assert code == 0, err
    assert out["status"] == "created"
    assert out["mode"] == "clarification"
    payload = seams.created_payloads[0]
    # Date from the RECORD (July 25), time from the REPLY (2pm). The exact fix.
    assert payload["start_rfc3339"] == "2026-07-25T14:00:00-04:00"
    # Idempotency key is the record's source path (not a synthetic conversational one).
    assert seams.created_keys[0] == "/inbox/vault/felix-smoke.md"
    # Cleanup happened: record removed + note marked.
    assert out["cleanup"] == {"record_removed": True, "note_marked": True}
    assert seams.removed == ["felix-smoke.md"]
    assert seams.marked == ["/inbox/vault/felix-smoke.md"]
    # Both log actions emitted.
    assert "calendar_event_created" in seams.actions
    assert "calendar_event_clarification_resolved" in seams.actions
    resolved = next(c for c in seams.log_calls if c["action"] == "calendar_event_clarification_resolved")
    assert resolved["context"]["clarification_id"] == "felix-smoke.md"


# ---------------------------------------------------------------------------
# 3b. #838 — idempotent hit: the re-reply requests a DIFFERENT time, but the
#     helper matched an EXISTING event. Report the calendar's ACTUAL time and
#     flag that the requested reschedule did NOT land (never confirm a time the
#     calendar does not hold).
# ---------------------------------------------------------------------------


def test_clarification_idempotent_hit_differing_time_reports_actual(seams, monkeypatch, tmp_path):
    # The existing event (matched by idempotency key) is at 2pm.
    seams.helper_result = {
        "status": "created",
        "event_id": "E1",
        "html_link": "L1",
        "idempotent": True,
        "actual_start": "2026-07-25T14:00:00-04:00",  # 2pm — what the calendar holds
    }
    state = _seed_state(
        tmp_path,
        [_record("Felix live smoke", "July 25",
                 note_filename="felix-smoke.md",
                 source_inbox_path="/inbox/vault/felix-smoke.md")],
    )
    code, out, err = _run(
        monkeypatch,
        # The re-reply asks for 3pm.
        {"title": "Felix live smoke", "start_natural": "3pm", "duration_natural": "1 hour"},
        ["--state-file", str(state), "--now-iso", "2026-07-20T12:00:00-04:00"],
    )
    assert code == 0, err
    assert out["status"] == "created"
    # The payload requested 3pm...
    assert seams.created_payloads[0]["start_rfc3339"] == "2026-07-25T15:00:00-04:00"
    # ...but the reported start is the calendar's ACTUAL 2pm, never the requested 3pm.
    assert out["start"] == "2026-07-25T14:00:00-04:00"
    assert out["idempotent"] is True
    assert out["time_change_applied"] is False
    assert out["requested_start"] == "2026-07-25T15:00:00-04:00"
    assert "2026-07-25T14:00:00-04:00" in out["note"]


def test_clarification_idempotent_hit_same_time_no_warning(seams, monkeypatch, tmp_path):
    # Idempotent hit where the requested time EQUALS the existing event: still
    # report the actual time, but no time_change_applied warning.
    seams.helper_result = {
        "status": "created",
        "event_id": "E1",
        "html_link": "L1",
        "idempotent": True,
        "actual_start": "2026-07-25T14:00:00-04:00",
    }
    state = _seed_state(
        tmp_path,
        [_record("Felix live smoke", "July 25",
                 note_filename="felix-smoke.md",
                 source_inbox_path="/inbox/vault/felix-smoke.md")],
    )
    code, out, err = _run(
        monkeypatch,
        {"title": "Felix live smoke", "start_natural": "2pm", "duration_natural": "1 hour"},
        ["--state-file", str(state), "--now-iso", "2026-07-20T12:00:00-04:00"],
    )
    assert code == 0, err
    assert out["start"] == "2026-07-25T14:00:00-04:00"
    assert out["idempotent"] is True
    assert "time_change_applied" not in out
    assert "note" not in out


def test_clarification_idempotent_hit_without_actual_start_flags_note(seams, monkeypatch, tmp_path):
    # renata #838 Finding 2: idempotent match but the helper didn't surface the
    # existing event's start → flag a verify-the-calendar note (don't silently
    # confirm the merely-requested time).
    seams.helper_result = {
        "status": "created",
        "event_id": "E1",
        "html_link": "L1",
        "idempotent": True,
        "actual_start": "",  # helper couldn't surface it
    }
    state = _seed_state(
        tmp_path,
        [_record("Felix live smoke", "July 25",
                 note_filename="felix-smoke.md",
                 source_inbox_path="/inbox/vault/felix-smoke.md")],
    )
    code, out, err = _run(
        monkeypatch,
        {"title": "Felix live smoke", "start_natural": "3pm", "duration_natural": "1 hour"},
        ["--state-file", str(state), "--now-iso", "2026-07-20T12:00:00-04:00"],
    )
    assert code == 0, err
    assert out["status"] == "created"
    assert out["idempotent"] is True
    assert "note" in out
    assert "verify" in out["note"].lower()


# ---------------------------------------------------------------------------
# 4. Clarification TERSE reply (no title) — binds via no-title -> all-candidates
# ---------------------------------------------------------------------------


def test_clarification_terse_no_title_binds_sole_record(seams, monkeypatch, tmp_path):
    state = _seed_state(
        tmp_path,
        [_record("Felix live smoke", "July 25",
                 note_filename="felix-smoke.md",
                 source_inbox_path="/inbox/vault/felix-smoke.md")],
    )
    code, out, err = _run(
        monkeypatch,
        {"start_natural": "2pm", "duration_natural": "1 hour"},
        ["--state-file", str(state), "--now-iso", "2026-07-20T12:00:00-04:00"],
    )
    assert code == 0, err
    assert out["status"] == "created"
    assert out["mode"] == "clarification"
    payload = seams.created_payloads[0]
    # Title AND date came from the record; time from the reply.
    assert payload["summary"] == "Felix live smoke"
    assert payload["start_rfc3339"] == "2026-07-25T14:00:00-04:00"


# ---------------------------------------------------------------------------
# 5. AMBIGUOUS — terse no-title reply, two live records
# ---------------------------------------------------------------------------


def test_ambiguous_two_live_records(seams, monkeypatch, tmp_path):
    state = _seed_state(
        tmp_path,
        [
            _record("Felix live smoke", "July 25", note_filename="a.md",
                    source_inbox_path="/inbox/a.md"),
            _record("Dentist appointment", "July 26", note_filename="b.md",
                    source_inbox_path="/inbox/b.md"),
        ],
    )
    code, out, err = _run(
        monkeypatch,
        {"start_natural": "2pm", "duration_natural": "1 hour"},
        ["--state-file", str(state), "--now-iso", "2026-07-20T12:00:00-04:00"],
    )
    assert code == 0, err
    assert out["status"] == "ambiguous"
    assert len(out["candidates"]) == 2
    names = {c["note_filename"] for c in out["candidates"]}
    assert names == {"a.md", "b.md"}
    # Nothing created.
    assert seams.created_payloads == []


# ---------------------------------------------------------------------------
# 6. Anti-mis-bind — complete conversational request while an UNRELATED record
#    is pending: create conversationally, leave the record untouched.
# ---------------------------------------------------------------------------


def test_anti_misbind_complete_request_ignores_pending(seams, monkeypatch, tmp_path):
    state = _seed_state(
        tmp_path,
        [_record("Dentist appointment", "July 26", note_filename="dentist.md",
                 source_inbox_path="/inbox/dentist.md")],
    )
    code, out, err = _run(
        monkeypatch,
        {"title": "meet Bob", "start_natural": "tomorrow at 2pm", "duration_natural": "1 hour"},
        ["--state-file", str(state), "--now-iso", "2026-07-15T12:00:00-04:00"],
    )
    assert code == 0, err
    assert out["status"] == "created"
    assert out["mode"] == "conversational"
    # The unrelated pending record is NOT removed or marked.
    assert seams.removed == []
    assert seams.marked == []
    assert "cleanup" not in out


# ---------------------------------------------------------------------------
# 7. ALL-DAY — whole-day duration -> start_date/end_date, no fabricated time
# ---------------------------------------------------------------------------


def test_all_day_event(seams, monkeypatch, tmp_path):
    state = _empty_state(tmp_path)
    code, out, err = _run(
        monkeypatch,
        {"title": "Kent's anniversary", "start_natural": "August 3", "duration_natural": "1 day"},
        ["--state-file", str(state), "--now-iso", "2026-07-15T12:00:00-04:00"],
    )
    assert code == 0, err
    assert out["status"] == "created"
    payload = seams.created_payloads[0]
    assert payload["start_date"] == "2026-08-03"
    assert payload["end_date"] == "2026-08-04"
    # No timed fields fabricated.
    assert "start_rfc3339" not in payload
    assert out["start"] == "2026-08-03"


# ---------------------------------------------------------------------------
# 8. Helper ERROR — surfaced verbatim, failed logged, no cleanup
# ---------------------------------------------------------------------------


def test_helper_error_surfaced_no_cleanup(seams, monkeypatch, tmp_path):
    seams.helper_result = {
        "status": "error",
        "exit_code": 3,
        "error": "ERROR: auth_failed invalid_grant",
    }
    state = _seed_state(
        tmp_path,
        [_record("Felix live smoke", "July 25", note_filename="felix-smoke.md",
                 source_inbox_path="/inbox/vault/felix-smoke.md")],
    )
    code, out, err = _run(
        monkeypatch,
        {"title": "Felix live smoke", "start_natural": "2pm", "duration_natural": "1 hour"},
        ["--state-file", str(state), "--now-iso", "2026-07-20T12:00:00-04:00"],
    )
    assert code == 0, err
    assert out["status"] == "error"
    assert out["exit_code"] == 3
    assert out["error"] == "ERROR: auth_failed invalid_grant"
    # No fabricated event id, no cleanup.
    assert "event_id" not in out
    assert seams.removed == []
    assert seams.marked == []
    assert "calendar_event_failed" in seams.actions
    assert "calendar_event_created" not in seams.actions


# ---------------------------------------------------------------------------
# 9. Liveness — an aged-out record (9h old) is ignored
# ---------------------------------------------------------------------------


def test_aged_out_record_ignored(seams, monkeypatch, tmp_path):
    now = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
    aged = _record("Felix live smoke", "July 25", note_filename="felix-smoke.md",
                   source_inbox_path="/inbox/vault/felix-smoke.md",
                   created_at=_iso_z(now - timedelta(hours=9)))
    state = _seed_state(tmp_path, [aged])
    code, out, err = _run(
        monkeypatch,
        {"start_natural": "2pm"},
        ["--state-file", str(state), "--now-iso", _iso_z(now)],
    )
    assert code == 0, err
    # Record is not live -> not matched -> falls through to conversational clarify,
    # NOT a clarification create.
    assert out["status"] == "needs_clarification"
    assert out["mode"] == "conversational"
    assert seams.created_payloads == []


# ---------------------------------------------------------------------------
# Clarification that stays incomplete after merge
# ---------------------------------------------------------------------------


def test_clarification_still_incomplete_leaves_record(seams, monkeypatch, tmp_path):
    # Record has only a title (no date); reply adds a time but still no date.
    rec = {
        "note_filename": "felix-smoke.md",
        "partial_payload": {
            "title": "Felix live smoke",
            "source_inbox_path": "/inbox/vault/felix-smoke.md",
            "source_block_index": 0,
        },
        "created_at": _iso_z(datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)),
    }
    state = _seed_state(tmp_path, [rec])
    code, out, err = _run(
        monkeypatch,
        {"title": "Felix live smoke", "start_natural": "2pm"},
        ["--state-file", str(state), "--now-iso", "2026-07-20T12:00:00-04:00"],
    )
    assert code == 0, err
    assert out["status"] == "needs_clarification"
    assert out["mode"] == "clarification"
    assert out["note_filename"] == "felix-smoke.md"
    # Record left in place (not removed), event not created.
    assert seams.removed == []
    assert seams.created_payloads == []


# ---------------------------------------------------------------------------
# CLI guards — bad stdin -> exit 2
# ---------------------------------------------------------------------------


def test_empty_stdin_exits_2(monkeypatch):
    code, out, err = _run(monkeypatch, "", [])
    assert code == 2
    assert "INVALID_INPUT_JSON" in err


def test_malformed_stdin_exits_2(monkeypatch):
    code, out, err = _run(monkeypatch, "not json", [])
    assert code == 2
    assert "INVALID_INPUT_JSON" in err


def test_non_object_stdin_exits_2(monkeypatch):
    code, out, err = _run(monkeypatch, "[1, 2, 3]", [])
    assert code == 2
    assert "top-level" in err


def test_bad_now_iso_exits_2(monkeypatch, tmp_path):
    state = _empty_state(tmp_path)
    code, out, err = _run(
        monkeypatch,
        {"title": "x", "start_natural": "tomorrow at 2pm", "duration_natural": "1 hour"},
        ["--state-file", str(state), "--now-iso", "not-a-date"],
    )
    assert code == 2
    assert "INVALID_NOW_ISO" in err


# ---------------------------------------------------------------------------
# _invoke_calendar_helper command construction (real seam, subprocess mocked)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Fix 2 — restated-complete reply that strong-matches the sole pending record
# resolves as a CLARIFICATION (with cleanup), not a fresh conversational create.
# ---------------------------------------------------------------------------


def test_restated_complete_reply_resolves_as_clarification(seams, monkeypatch, tmp_path):
    state = _seed_state(
        tmp_path,
        [_record("Dentist", "July 25", note_filename="dentist.md",
                 source_inbox_path="/inbox/dentist.md")],
    )
    # Complete on its own (date + time + duration), and its title contains the
    # pending record's title → strong match.
    code, out, err = _run(
        monkeypatch,
        {"title": "Dentist appointment", "start_natural": "July 25 at 2pm",
         "duration_natural": "1 hour"},
        ["--state-file", str(state), "--now-iso", "2026-07-20T12:00:00-04:00"],
    )
    assert code == 0, err
    assert out["status"] == "created"
    assert out["mode"] == "clarification"
    payload = seams.created_payloads[0]
    assert payload["start_rfc3339"] == "2026-07-25T14:00:00-04:00"
    # Resolved against the record: its idempotency key + cleanup, not an orphan.
    assert seams.created_keys[0] == "/inbox/dentist.md"
    assert out["cleanup"] == {"record_removed": True, "note_marked": True}
    assert out["cleanup_ok"] is True
    assert seams.removed == ["dentist.md"]
    assert seams.marked == ["/inbox/dentist.md"]


# ---------------------------------------------------------------------------
# Fix 1/2 — an incomplete reply sharing only a GENERIC token ("Lunch") with a
# pending record must NOT bind (subset rule); falls through to conversational.
# ---------------------------------------------------------------------------


def test_generic_token_does_not_misbind(seams, monkeypatch, tmp_path):
    state = _seed_state(
        tmp_path,
        [_record("Lunch with John", "Thursday", note_filename="john.md",
                 source_inbox_path="/inbox/john.md",
                 created_at=_iso_z(datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)))],
    )
    code, out, err = _run(
        monkeypatch,
        {"title": "Lunch with Sarah", "start_natural": "2pm", "duration_natural": "1 hour"},
        ["--state-file", str(state), "--now-iso", "2026-07-15T12:00:00-04:00"],
    )
    assert code == 0, err
    assert out["status"] == "needs_clarification"
    assert out["mode"] == "conversational"
    # John's record is untouched — no merge onto his Thursday, no create.
    assert seams.created_payloads == []
    assert seams.removed == []
    assert seams.marked == []


# ---------------------------------------------------------------------------
# Fix 3 — an end-only reply inherits the record's date.
# ---------------------------------------------------------------------------


def test_end_only_reply_inherits_record_date(seams, monkeypatch, tmp_path):
    state = _seed_state(
        tmp_path,
        [_record("Dentist", "Thursday", note_filename="dentist.md",
                 source_inbox_path="/inbox/dentist.md",
                 created_at=_iso_z(datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)))],
    )
    # Terse (no title) reply carrying both a start-time and an end-time.
    code, out, err = _run(
        monkeypatch,
        {"start_natural": "2pm", "end_natural": "3pm"},
        ["--state-file", str(state), "--now-iso", "2026-07-15T12:00:00-04:00"],
    )
    assert code == 0, err
    assert out["status"] == "created"
    assert out["mode"] == "clarification"
    payload = seams.created_payloads[0]
    # Thursday after Wed 2026-07-15 is 2026-07-16; both endpoints on that date.
    assert payload["start_rfc3339"] == "2026-07-16T14:00:00-04:00"
    assert payload["end_rfc3339"] == "2026-07-16T15:00:00-04:00"


# ---------------------------------------------------------------------------
# Fix 4 — conversational idempotency key: distinct per request, stable per retry.
# ---------------------------------------------------------------------------


def test_conversational_idempotency_key_distinctness(seams, monkeypatch, tmp_path):
    state = _empty_state(tmp_path)
    now = "2026-07-15T12:00:00-04:00"
    block_a = {"title": "meet Bob", "start_natural": "tomorrow at 2pm", "duration_natural": "1 hour"}
    block_b = {"title": "meet Carol", "start_natural": "tomorrow at 2pm", "duration_natural": "1 hour"}

    _run(monkeypatch, block_a, ["--state-file", str(state), "--now-iso", now])
    _run(monkeypatch, block_b, ["--state-file", str(state), "--now-iso", now])
    _run(monkeypatch, block_a, ["--state-file", str(state), "--now-iso", now])

    key_a1, key_b, key_a2 = seams.created_keys
    # Different content, same tick -> different keys (no same-second collision).
    assert key_a1 != key_b
    # Same content + same tick -> identical key (idempotent retry).
    assert key_a1 == key_a2


# ---------------------------------------------------------------------------
# Fix 6 — cleanup failure: record removal retried once, cleanup_ok False,
# status still "created".
# ---------------------------------------------------------------------------


def test_cleanup_failure_retries_and_flags(seams, monkeypatch, tmp_path):
    calls = {"remove": 0}

    def failing_remove(note_filename, state_file):
        calls["remove"] += 1
        return False

    monkeypatch.setattr(hcr, "_invoke_remove_record", failing_remove)

    state = _seed_state(
        tmp_path,
        [_record("Felix live smoke", "July 25", note_filename="felix-smoke.md",
                 source_inbox_path="/inbox/vault/felix-smoke.md")],
    )
    code, out, err = _run(
        monkeypatch,
        {"title": "Felix live smoke", "start_natural": "2pm", "duration_natural": "1 hour"},
        ["--state-file", str(state), "--now-iso", "2026-07-20T12:00:00-04:00"],
    )
    assert code == 0, err
    # Event WAS created; cleanup failed and is surfaced.
    assert out["status"] == "created"
    assert out["mode"] == "clarification"
    assert out["cleanup"]["record_removed"] is False
    assert out["cleanup"]["note_marked"] is True
    assert out["cleanup_ok"] is False
    # Removal was retried exactly once (two attempts total).
    assert calls["remove"] == 2


# ---------------------------------------------------------------------------
# Fix 5 — a launch-level OSError in the helper seam is caught, not raised.
# ---------------------------------------------------------------------------


def test_calendar_helper_oserror_is_caught(monkeypatch):
    def boom(cmd, **kwargs):
        raise OSError("No such file or directory: venv/bin/python")

    monkeypatch.setattr(hcr.subprocess, "run", boom)
    result = hcr._invoke_calendar_helper(
        {"summary": "x", "start_rfc3339": "2026-07-25T14:00:00-04:00"},
        "/inbox/vault/felix-smoke.md",
        "personal",
    )
    assert result["status"] == "error"
    assert "launch failed" in result["error"]


def test_calendar_helper_command_shape(monkeypatch):
    import subprocess

    recorded: dict = {}

    def fake_run(cmd, **kwargs):
        recorded["cmd"] = cmd
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout='{"status": "created", "event_id": "e9", "html_link": "h9"}\n'
            "SUMMARY: op=create status=created\n",
            stderr="",
        )

    monkeypatch.setattr(hcr.subprocess, "run", fake_run)
    result = hcr._invoke_calendar_helper(
        {"summary": "x", "start_rfc3339": "2026-07-25T14:00:00-04:00"},
        "/inbox/vault/felix-smoke.md",
        "personal",
    )
    assert result == {
        "status": "created",
        "event_id": "e9",
        "html_link": "h9",
        "idempotent": False,
        "actual_start": "",
    }
    cmd = recorded["cmd"]
    assert cmd[0] == hcr.DEFAULT_CALENDAR_HELPER_PYTHON
    assert cmd[0] != sys.executable
    assert "-m" in cmd and hcr.CALENDAR_HELPER_MODULE in cmd
    assert cmd[cmd.index("--idempotency-key") + 1] == "/inbox/vault/felix-smoke.md"
    assert cmd[cmd.index("--account") + 1] == "personal"


def test_calendar_helper_passes_through_idempotent_and_actual_start(monkeypatch):
    """#838: the seam carries the helper's idempotent flag + actual event start."""
    import subprocess

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout=(
                '{"status": "created", "event_id": "E", "html_link": "h", '
                '"idempotent": true, "start": "2026-07-25T14:00:00-04:00", '
                '"end": "2026-07-25T15:00:00-04:00"}\n'
                "SUMMARY: op=create status=created idempotent=true\n"
            ),
            stderr="",
        )

    monkeypatch.setattr(hcr.subprocess, "run", fake_run)
    result = hcr._invoke_calendar_helper(
        {"summary": "x", "start_rfc3339": "2026-07-25T15:00:00-04:00"},
        "/inbox/vault/note.md",
        "personal",
    )
    assert result["idempotent"] is True
    assert result["actual_start"] == "2026-07-25T14:00:00-04:00"
