"""Tests for credential_health_check.reminders — the #852 Part 2 ntfy ladder."""
from __future__ import annotations

import json
from datetime import date
from unittest.mock import patch

import pytest

from credential_health_check.manifest import Credential
from credential_health_check import reminders
from credential_health_check.reminders import (
    OVERDUE_RUNG,
    FiredState,
    Reminder,
    build_alert,
    load_fired,
    process_expiry_reminder,
    select,
)
from scripts.common.alert_bus import AlertResult, Severity


def _cred(name: str = "anthropic-test") -> Credential:
    return Credential(
        name=name,
        review_cadence="annual",
        storage="~/.config/anthropic/test-key",
        expiry_notes="Rotate the test key in the Anthropic console.",
        type="api-token",
        last_reviewed=date(2026, 7, 22),
        expires_at=date(2026, 8, 21),
    )


EMPTY = FiredState(frozenset(), frozenset())


# --------------------------------------------------------------------------- #
# select() — pure decision                                                     #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "days_until,expected_rung",
    [
        (31, None),   # outside first rung → nothing
        (30, 30),     # exactly first rung
        (29, 30),     # between 30 and 14 → still the 30 rung (crossed, unfired)
        (14, 14),
        (7, 7),
        (3, 3),
        (1, 1),
        (0, OVERDUE_RUNG),   # boundary day = overdue regime
        (-5, OVERDUE_RUNG),  # past boundary
    ],
)
def test_select_rung_boundaries(days_until, expected_rung):
    boundary = date(2026, 8, 21)
    today = boundary.fromordinal(boundary.toordinal() - days_until)
    r = select("anthropic-test", boundary, today, EMPTY)
    if expected_rung is None:
        assert r is None
    else:
        assert r is not None
        assert r.rung == expected_rung
        assert r.days_until == days_until


def test_select_dedups_a_fired_rung():
    boundary = date(2026, 8, 21)
    today = boundary.fromordinal(boundary.toordinal() - 30)  # days_until == 30
    fired = FiredState(frozenset({("anthropic-test", boundary.isoformat(), 30)}), frozenset())
    assert select("anthropic-test", boundary, today, fired) is None


def test_select_advances_to_next_rung_after_earlier_fired():
    boundary = date(2026, 8, 21)
    today = boundary.fromordinal(boundary.toordinal() - 14)  # days_until == 14
    fired = FiredState(frozenset({("anthropic-test", boundary.isoformat(), 30)}), frozenset())
    r = select("anthropic-test", boundary, today, fired)
    assert r is not None and r.rung == 14


def test_select_consumes_all_crossed_rungs_on_first_late_observation():
    """First run at days_until=5 (e.g. after an outage) fires the most-urgent
    crossed rung (7) and consumes the superseded 30/14 so they never back-fire."""
    boundary = date(2026, 8, 21)
    today = boundary.fromordinal(boundary.toordinal() - 5)  # days_until == 5
    r = select("anthropic-test", boundary, today, EMPTY)
    assert r is not None
    assert r.rung == 7  # most urgent crossed (days_until 5 <= 7)
    assert set(r.rungs_consumed) == {30, 14, 7}


def test_select_overdue_dedups_per_calendar_day():
    boundary = date(2026, 8, 21)
    today = date(2026, 8, 25)  # 4 days overdue
    fired = FiredState(frozenset(), frozenset({("anthropic-test", today.isoformat())}))
    assert select("anthropic-test", boundary, today, fired) is None
    # A new day is not deduped.
    r = select("anthropic-test", boundary, date(2026, 8, 26), fired)
    assert r is not None and r.rung == OVERDUE_RUNG


def test_select_boundary_change_resets_ladder():
    """After rotation, expires_at jumps out → a new boundary keys a fresh ladder."""
    old_boundary = date(2026, 8, 21)
    fired = FiredState(
        frozenset({("anthropic-test", old_boundary.isoformat(), r) for r in (30, 14, 7, 3, 1)}),
        frozenset(),
    )
    new_boundary = date(2027, 8, 21)
    today = new_boundary.fromordinal(new_boundary.toordinal() - 30)
    r = select("anthropic-test", new_boundary, today, fired)
    assert r is not None and r.rung == 30


# --------------------------------------------------------------------------- #
# Ledger round-trip                                                            #
# --------------------------------------------------------------------------- #


def test_ledger_roundtrip_rung(isolate_reminder_state):
    reminders._append_record(
        {
            "credential": "anthropic-test",
            "boundary": "2026-08-21",
            "kind": "rung",
            "rung_fired": 7,
            "rungs_consumed": [30, 14, 7],
            "days_until": 5,
            "severity": "error",
            "emitted": True,
            "fired_at": "2026-08-16T00:00:00+00:00",
        }
    )
    fired = load_fired()
    b = date(2026, 8, 21)
    assert fired.rung_fired("anthropic-test", b, 30)
    assert fired.rung_fired("anthropic-test", b, 14)
    assert fired.rung_fired("anthropic-test", b, 7)
    assert not fired.rung_fired("anthropic-test", b, 3)


def test_ledger_roundtrip_overdue(isolate_reminder_state):
    reminders._append_record(
        {
            "credential": "anthropic-test",
            "boundary": "2026-08-21",
            "kind": "overdue",
            "date": "2026-08-25",
            "days_until": -4,
            "severity": "critical",
            "emitted": True,
            "fired_at": "2026-08-25T00:00:00+00:00",
        }
    )
    fired = load_fired()
    assert fired.overdue_fired("anthropic-test", date(2026, 8, 25))
    assert not fired.overdue_fired("anthropic-test", date(2026, 8, 26))


def test_load_fired_missing_file_is_empty(isolate_reminder_state):
    assert load_fired() == EMPTY


def test_load_fired_skips_malformed_lines(isolate_reminder_state):
    path = reminders.rungs_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "not json\n"
        + json.dumps({"credential": "x", "boundary": "2026-08-21", "kind": "rung", "rungs_consumed": [7]})
        + "\n"
        + json.dumps({"no": "credential"})
        + "\n",
        encoding="utf-8",
    )
    fired = load_fired()
    assert fired.rung_fired("x", date(2026, 8, 21), 7)


# --------------------------------------------------------------------------- #
# build_alert()                                                                #
# --------------------------------------------------------------------------- #


def test_build_alert_has_no_vikunja_or_github_link():
    r = Reminder(7, 5, date(2026, 8, 21), (30, 14, 7))
    alert = build_alert(_cred(), r)
    blob = " ".join([alert.title, alert.description, alert.action or "", *alert.details.values()])
    assert "github.com" not in blob
    assert "vikunja" not in blob.lower()
    assert "/tasks/" not in blob
    assert "issues/" not in blob


def test_build_alert_severity_gradient():
    b = date(2026, 8, 21)
    assert build_alert(_cred(), Reminder(30, 30, b, (30,))).severity == Severity.WARN
    assert build_alert(_cred(), Reminder(14, 14, b, (14,))).severity == Severity.WARN
    assert build_alert(_cred(), Reminder(7, 7, b, (7,))).severity == Severity.ERROR
    assert build_alert(_cred(), Reminder(3, 3, b, (3,))).severity == Severity.ERROR
    assert build_alert(_cred(), Reminder(1, 1, b, (1,))).severity == Severity.CRITICAL
    assert build_alert(_cred(), Reminder(OVERDUE_RUNG, -2, b, ())).severity == Severity.CRITICAL


def test_build_alert_severity_tracks_true_proximity_not_rung():
    """A late first observation fires a distant rung but must carry the priority
    its real proximity warrants: rung 7 fired at 1 day out → CRITICAL (keying off
    the rung would wrongly give ERROR)."""
    b = date(2026, 8, 21)
    late = Reminder(7, 1, b, (30, 14, 7))  # fired rung 7, but only 1 day out
    assert build_alert(_cred(), late).severity == Severity.CRITICAL


def test_build_alert_overdue_wording():
    alert = build_alert(_cred(), Reminder(OVERDUE_RUNG, -4, date(2026, 8, 21), ()))
    assert "OVERDUE" in alert.title
    assert "4 day(s) ago" in alert.description


# --------------------------------------------------------------------------- #
# process_expiry_reminder() — orchestration                                    #
# --------------------------------------------------------------------------- #


def _ok():
    return AlertResult(ok=True, reason=None, topic_configured=True)


def _fail():
    return AlertResult(ok=False, reason="NTFY_MISSING_TOPIC", topic_configured=False)


def test_process_fires_and_persists_on_delivery(isolate_reminder_state):
    boundary = date(2026, 8, 21)
    today = boundary.fromordinal(boundary.toordinal() - 30)
    with patch.object(reminders, "emit", return_value=_ok()) as mock_emit:
        pushed = process_expiry_reminder(_cred(), boundary, today, dry_run=False)
    assert pushed is True
    mock_emit.assert_called_once()
    # Persisted → a second call the same cycle is deduped.
    with patch.object(reminders, "emit", return_value=_ok()) as mock_emit2:
        again = process_expiry_reminder(_cred(), boundary, today, dry_run=False)
    assert again is False
    mock_emit2.assert_not_called()


def test_process_does_not_persist_on_delivery_failure(isolate_reminder_state):
    boundary = date(2026, 8, 21)
    today = boundary.fromordinal(boundary.toordinal() - 30)
    with patch.object(reminders, "emit", return_value=_fail()):
        pushed = process_expiry_reminder(_cred(), boundary, today, dry_run=False)
    assert pushed is False
    # Nothing persisted → next cycle retries (emit called again).
    with patch.object(reminders, "emit", return_value=_ok()) as mock_emit:
        retry = process_expiry_reminder(_cred(), boundary, today, dry_run=False)
    assert retry is True
    mock_emit.assert_called_once()


def test_process_dry_run_never_emits_or_persists(isolate_reminder_state):
    boundary = date(2026, 8, 21)
    today = boundary.fromordinal(boundary.toordinal() - 30)
    with patch.object(reminders, "emit") as mock_emit:
        pushed = process_expiry_reminder(_cred(), boundary, today, dry_run=True)
    assert pushed is False
    mock_emit.assert_not_called()
    assert load_fired() == EMPTY


def test_process_nothing_due_returns_false(isolate_reminder_state):
    boundary = date(2026, 8, 21)
    today = boundary.fromordinal(boundary.toordinal() - 31)  # outside window
    with patch.object(reminders, "emit") as mock_emit:
        pushed = process_expiry_reminder(_cred(), boundary, today, dry_run=False)
    assert pushed is False
    mock_emit.assert_not_called()


def test_process_swallows_bus_exceptions(isolate_reminder_state):
    boundary = date(2026, 8, 21)
    today = boundary.fromordinal(boundary.toordinal() - 30)
    with patch.object(reminders, "emit", side_effect=RuntimeError("boom")):
        # Must not raise — a reminder can never crash the daily cycle.
        pushed = process_expiry_reminder(_cred(), boundary, today, dry_run=False)
    assert pushed is False


def test_process_overdue_fires_daily(isolate_reminder_state):
    boundary = date(2026, 8, 21)
    with patch.object(reminders, "emit", return_value=_ok()) as mock_emit:
        d1 = process_expiry_reminder(_cred(), boundary, date(2026, 8, 22), dry_run=False)
        d1_again = process_expiry_reminder(_cred(), boundary, date(2026, 8, 22), dry_run=False)
        d2 = process_expiry_reminder(_cred(), boundary, date(2026, 8, 23), dry_run=False)
    assert d1 is True
    assert d1_again is False  # same calendar day deduped
    assert d2 is True         # next day fires again
    assert mock_emit.call_count == 2
