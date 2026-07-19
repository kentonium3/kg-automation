"""Integration/scenario tests for the #780 all-day age-out sweep-finalize path.

These are the end-to-end acceptance evidence for the fallback invariants
(SC-001..004, INV-1..7, FR-004/005/008/009). Unlike the WP03 unit tests they
drive ``clarification_sweep_finalize.sweep_finalize`` against the **real** #746
``route_and_finalize._run_finalize`` transaction — real eligibility gate, real
all-day plan construction, real routing-log writes, and the **real**
``mark_processed`` subprocess flipping a real temp inbox note's frontmatter.

Only ONE seam is faked: ``route_calendar_event._invoke_calendar_helper`` — the
lowest deterministic boundary, the subprocess that would otherwise call the live
Google Calendar API (which needs a venv + token that never run under CI). Faking
there keeps ``_run_create`` -> ``_run_finalize`` -> log-before-mark -> mark
genuinely exercised, so atomicity and idempotency are really tested, not mocked
away (WP04 reviewer directive).

Determinism comes from an injected ``now`` (the sweep's aging clock) + a temp
state file + a temp routing log + a hermetic vault (temp inbox root wired via
``PRESCAN_REGISTRY_PATH`` so the real ``mark_processed`` subprocess resolves the
inbox root to the temp dir).

Real observables asserted throughout: the number of calendar creates, the
routing-log rows and their ``kind`` values, the note's on-disk processed state,
and the state-file survivors.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# Bring scripts/ onto sys.path so `scripts.inbox.*` imports resolve.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.inbox import clarification_sweep_finalize as csf  # noqa: E402
from scripts.inbox import handle_clarification_state as hcs  # noqa: E402
from scripts.inbox import route_calendar_event as rce  # noqa: E402
from scripts.inbox import routing_log as _routing_log  # noqa: E402


NOW = datetime(2026, 7, 18, 12, 0, 0, tzinfo=timezone.utc)
AGED = NOW - timedelta(hours=9)  # comfortably past the 8h window
FRESH = NOW - timedelta(hours=1)  # inside the window → not aged out
RESOLVED_DATE = "2026-07-20"
RESOLVED_END = "2026-07-21"  # start_date + 1 day (exclusive end)


# ---------------------------------------------------------------------------
# Calendar fake (the ONE faked seam — everything below it is real)
# ---------------------------------------------------------------------------


class _CalendarFake:
    """Stand-in for ``rce._invoke_calendar_helper``.

    Records every invocation's envelope / idempotency-key / account and returns
    a configurable ``CompletedProcess``: a helper ``status: created`` success by
    default, or an error (fail-closed) when ``mode == "error"``. Because it sits
    at the calendar-subprocess boundary, the real ``_run_create`` normalizes the
    payload, builds the delegation envelope, and parses the fake's stdout — so
    the envelope the fake captures is the genuine all-day payload.
    """

    def __init__(self, event_id: str = "evt_1") -> None:
        self.event_id = event_id
        self.mode = "created"  # or "error"
        self.calls: list[dict] = []

    def __call__(self, envelope, source_inbox_path, account):
        self.calls.append(
            {
                "envelope": envelope,
                "idempotency_key": source_inbox_path,
                "account": account,
            }
        )
        if self.mode == "error":
            return subprocess.CompletedProcess(
                args=["calendar_helper"],
                returncode=3,
                stdout="",
                stderr="ERROR: auth_failed invalid_grant\n",
            )
        stdout = (
            f'{{"status": "created", "idempotent": false, '
            f'"event_id": "{self.event_id}", '
            f'"html_link": "https://cal/{self.event_id}"}}\n'
            "SUMMARY: op=create status=created\n"
        )
        return subprocess.CompletedProcess(
            args=["calendar_helper"], returncode=0, stdout=stdout, stderr=""
        )

    @property
    def create_count(self) -> int:
        """Number of invocations that actually created an event (mode created)."""
        return sum(1 for c in self.calls if c is not None)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def hermetic_vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Temp inbox root wired so the REAL ``mark_processed`` subprocess works.

    Mirrors ``tests/inbox/test_mark_processed.py``: creates ``01-Inbox`` +
    ``02-Inbox-Processed``, writes a ``paths.json`` registry, and sets
    ``PRESCAN_REGISTRY_PATH`` (inherited by the mark_processed subprocess) so the
    inbox-root validation resolves to this temp inbox rather than the production
    vault. Returns the inbox root.
    """
    inbox = tmp_path / "01-Inbox"
    inbox.mkdir()
    inbox_processed = tmp_path / "02-Inbox-Processed"
    inbox_processed.mkdir()
    registry = tmp_path / "paths.json"
    registry.write_text(
        json.dumps(
            {"paths": {"inbox": str(inbox), "inbox_processed": str(inbox_processed)}}
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("PRESCAN_REGISTRY_PATH", str(registry))
    return inbox


@pytest.fixture
def log_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the routing log to a temp file for the test's lifetime."""
    p = tmp_path / "routing.jsonl"
    monkeypatch.setattr(_routing_log, "DEFAULT_ROUTING_LOG_PATH", p)
    return p


@pytest.fixture
def calendar(monkeypatch: pytest.MonkeyPatch) -> _CalendarFake:
    """Install the calendar fake at ``rce._invoke_calendar_helper``."""
    fake = _CalendarFake()
    monkeypatch.setattr(rce, "_invoke_calendar_helper", fake)
    return fake


@pytest.fixture
def state_path(tmp_path: Path) -> Path:
    return tmp_path / "pending.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _write_note(inbox: Path, name: str, status: str = "unprocessed") -> Path:
    """Write a real inbox note with the given frontmatter status. Returns path."""
    note = inbox / name
    note.write_text(
        f"---\nstatus: {status}\n---\n\nMeet Rob about the roadmap.\n",
        encoding="utf-8",
    )
    return note


def _note_status(note: Path) -> str:
    """Read the note's frontmatter ``status`` value (the real processed signal)."""
    for line in note.read_text(encoding="utf-8").splitlines():
        if line.startswith("status:"):
            return line.split(":", 1)[1].strip()
    return ""


def _eligible_record(
    note_name: str,
    created: datetime = AGED,
    title: str = "Meet Rob",
    start_date: str = RESOLVED_DATE,
    extra_payload: dict | None = None,
) -> dict:
    payload = {
        "title": title,
        "start_date": start_date,
        "missing_fields": ["start_time", "end_or_duration"],
    }
    if extra_payload:
        payload.update(extra_payload)
    return {
        "note_filename": note_name,
        "partial_payload": payload,
        "created_at": _iso_z(created),
    }


def _write_state(path: Path, records: list[dict]) -> None:
    path.write_text(json.dumps(records, indent=2), encoding="utf-8")


def _read_state(path: Path) -> list[dict]:
    if not path.exists():
        return []
    raw = path.read_text(encoding="utf-8").strip()
    return json.loads(raw) if raw else []


def _log_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]


def _rows_of_kind(path: Path, kind: str) -> list[dict]:
    return [r for r in _log_rows(path) if r.get("kind") == kind]


# ===========================================================================
# T010 — Eligible age-out → all-day create (happy path) [SC-001, FR-004/006]
# ===========================================================================


class TestT010EligibleAgeOut:
    def test_single_all_day_event_note_processed_marker_and_record_removed(
        self,
        hermetic_vault: Path,
        log_path: Path,
        calendar: _CalendarFake,
        state_path: Path,
    ) -> None:
        note = _write_note(hermetic_vault, "Meet Rob 2026-07-18 0900.md")
        _write_state(state_path, [_eligible_record(note.name)])

        counts = csf.sweep_finalize(state_path, NOW, hermetic_vault)

        # Exactly one calendar create, carrying the all-day timing (start_date +
        # exclusive end_date = start_date + 1), keyed on the canonical inbox path.
        assert counts == {
            "aged_out": 1,
            "finalized": 1,
            "reconciled": 0,
            "released": 0,
            "retained": 0,
        }
        assert calendar.create_count == 1
        envelope = calendar.calls[0]["envelope"]
        assert envelope["start_date"] == RESOLVED_DATE
        assert envelope["end_date"] == RESOLVED_END
        assert "start_rfc3339" not in envelope and "start" not in envelope
        assert calendar.calls[0]["idempotency_key"] == str(hermetic_vault / note.name)

        # The note is REALLY marked processed on disk (real mark subprocess).
        assert _note_status(note) == "processed"

        # Exactly one calendar row + one distinct fallback marker in the log.
        assert len(_rows_of_kind(log_path, "calendar")) == 1
        markers = _rows_of_kind(log_path, csf.FALLBACK_MARKER_KIND)
        assert len(markers) == 1
        assert markers[0]["destination"] == "evt_1"
        assert markers[0]["filename"] == note.name

        # The pending record is removed.
        assert _read_state(state_path) == []

    def test_non_aged_out_record_is_untouched(
        self,
        hermetic_vault: Path,
        log_path: Path,
        calendar: _CalendarFake,
        state_path: Path,
    ) -> None:
        # A fresh (within-window) eligible record must not be swept.
        note = _write_note(hermetic_vault, "Fresh Rob.md")
        _write_state(state_path, [_eligible_record(note.name, created=FRESH)])

        counts = csf.sweep_finalize(state_path, NOW, hermetic_vault)

        assert counts["aged_out"] == 0 and counts["finalized"] == 0
        assert calendar.create_count == 0
        assert _note_status(note) == "unprocessed"
        assert len(_read_state(state_path)) == 1  # still pending


# ===========================================================================
# T011 — Idempotency across retry + reconciliation [FR-008/009, INV-1/6]
# ===========================================================================


class TestT011IdempotencyAndReconcile:
    def test_a_mark_succeeds_then_removal_fails_reconciles_no_recreate(
        self,
        hermetic_vault: Path,
        log_path: Path,
        calendar: _CalendarFake,
        state_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """create+mark succeed on tick-1 but the record-removal (save_state)
        fails → the record survives; tick-2 reconciles it away WITHOUT
        re-creating the event (exactly one), note stays processed. [INV-6]"""
        note = _write_note(hermetic_vault, "Rob removal-fail.md")
        _write_state(state_path, [_eligible_record(note.name)])

        # tick-1: let the transaction fully succeed (note marked, event logged,
        # marker emitted) but make the terminal state rewrite blow up so the
        # record is NOT removed — the post-mark record-removal failure window.
        real_save = hcs.save_state

        def boom_save(path, entries):
            raise OSError("disk full during record removal")

        monkeypatch.setattr(hcs, "save_state", boom_save)
        with pytest.raises(OSError):
            csf.sweep_finalize(state_path, NOW, hermetic_vault)

        # The event was created + logged and the note IS processed even though
        # the record removal did not land.
        assert calendar.create_count == 1
        assert _note_status(note) == "processed"
        assert len(_rows_of_kind(log_path, "calendar")) == 1
        assert len(_rows_of_kind(log_path, csf.FALLBACK_MARKER_KIND)) == 1
        assert len(_read_state(state_path)) == 1  # stale record survived

        # tick-2: save_state works again. The block is already logged → skipped →
        # reconciled; the stale record is removed and the event is NOT re-created.
        monkeypatch.setattr(hcs, "save_state", real_save)
        counts2 = csf.sweep_finalize(state_path, NOW, hermetic_vault)

        assert counts2["reconciled"] == 1 and counts2["finalized"] == 0
        assert calendar.create_count == 1, "event must NOT be re-created"
        assert _read_state(state_path) == []  # stale record removed
        assert len(_rows_of_kind(log_path, "calendar")) == 1
        assert len(_rows_of_kind(log_path, csf.FALLBACK_MARKER_KIND)) == 1
        assert _note_status(note) == "processed"

    def test_b_mark_fail_then_reconcile_emits_marker_exactly_once(
        self,
        hermetic_vault: Path,
        log_path: Path,
        calendar: _CalendarFake,
        state_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """FR-007 (reviewer-renata HIGH-3): tick-1 creates + logs the ``calendar``
        row but ``mark_processed`` FAILS (record retained, note unprocessed, NO
        marker yet). tick-2 reconciles and MUST still emit exactly one
        ``calendar_all_day_fallback`` marker — sourced from the calendar row,
        without re-creating the event."""
        from scripts.inbox import route_and_finalize as raf

        note = _write_note(hermetic_vault, "Rob mark-fail.md")
        _write_state(state_path, [_eligible_record(note.name)])

        # tick-1: force the mark subprocess to fail (create + log still happen —
        # log-before-mark). This is a sub-seam, not the whole path: _run_finalize,
        # _run_create, and the routing-log writes all run for real. Capture the
        # real mark so tick-2 can restore ONLY this seam (not the fixture patches).
        real_mark = raf._invoke_mark_processed
        monkeypatch.setattr(
            raf,
            "_invoke_mark_processed",
            lambda p: subprocess.CompletedProcess(
                args=["mark"], returncode=1, stdout="", stderr="ERROR: mark boom"
            ),
        )
        counts1 = csf.sweep_finalize(state_path, NOW, hermetic_vault)

        assert counts1["retained"] == 1 and counts1["finalized"] == 0
        assert calendar.create_count == 1
        assert _note_status(note) == "unprocessed"  # mark never landed
        assert len(_rows_of_kind(log_path, "calendar")) == 1
        assert _rows_of_kind(log_path, csf.FALLBACK_MARKER_KIND) == []  # no marker
        assert len(_read_state(state_path)) == 1  # retained for retry

        # tick-2: restore ONLY the mark seam (the fixtures' log/env/calendar
        # patches stay in force) → the already-logged block is skipped →
        # reconciled → the missing marker is emitted exactly once.
        monkeypatch.setattr(raf, "_invoke_mark_processed", real_mark)
        counts2 = csf.sweep_finalize(state_path, NOW, hermetic_vault)

        assert counts2["reconciled"] == 1 and counts2["finalized"] == 0
        assert calendar.create_count == 1, "no double-create on reconcile"
        assert _note_status(note) == "processed"
        assert len(_rows_of_kind(log_path, "calendar")) == 1
        markers = _rows_of_kind(log_path, csf.FALLBACK_MARKER_KIND)
        assert len(markers) == 1, "exactly one fallback marker"
        assert markers[0]["destination"] == "evt_1"  # sourced from the calendar row
        assert _read_state(state_path) == []

    def test_c_fail_before_log_then_retry_creates_exactly_one(
        self,
        hermetic_vault: Path,
        log_path: Path,
        calendar: _CalendarFake,
        state_path: Path,
    ) -> None:
        """A failure BEFORE any routing-log write (the calendar create errors)
        leaves nothing logged, the record retained, the note unprocessed. On a
        later pass where the create succeeds, exactly one event is created — no
        double-create, no leaked partial state. [INV-3]"""
        note = _write_note(hermetic_vault, "Rob create-fail.md")
        _write_state(state_path, [_eligible_record(note.name)])

        # tick-1: the calendar create errors before anything is logged.
        calendar.mode = "error"
        counts1 = csf.sweep_finalize(state_path, NOW, hermetic_vault)

        assert counts1["retained"] == 1 and counts1["finalized"] == 0
        assert _note_status(note) == "unprocessed"
        assert _log_rows(log_path) == []  # nothing logged (fail-closed before log)
        assert len(_read_state(state_path)) == 1  # retained

        # tick-2: the create now succeeds → exactly one event, note processed.
        calendar.mode = "created"
        counts2 = csf.sweep_finalize(state_path, NOW, hermetic_vault)

        assert counts2["finalized"] == 1 and counts2["reconciled"] == 0
        assert len(_rows_of_kind(log_path, "calendar")) == 1
        assert len(_rows_of_kind(log_path, csf.FALLBACK_MARKER_KIND)) == 1
        assert _note_status(note) == "processed"
        assert _read_state(state_path) == []


# ===========================================================================
# T012 — Boundary + legacy: no leakage [FR-002/005, SC-002, INV-2]
# ===========================================================================


class TestT012BoundaryAndLegacy:
    def test_ineligible_aged_records_zero_events_delete_and_release(
        self,
        hermetic_vault: Path,
        log_path: Path,
        calendar: _CalendarFake,
        state_path: Path,
    ) -> None:
        # (a) missing title; (b) a NON-timing missing field alongside start_time;
        # (c) a legacy record with neither missing_fields nor start_date.
        missing_title = {
            "note_filename": "no-title.md",
            "partial_payload": {
                "start_date": RESOLVED_DATE,
                "missing_fields": ["start_time", "end_or_duration"],
            },
            "created_at": _iso_z(AGED),
        }
        non_timing_gap = _eligible_record(
            "non-timing.md",
            extra_payload={"missing_fields": ["start_time", "location"]},
        )
        legacy_no_signal = {
            "note_filename": "legacy.md",
            "partial_payload": {"title": "Old appointment"},
            "created_at": _iso_z(AGED),
        }

        notes = {
            "no-title.md": _write_note(hermetic_vault, "no-title.md"),
            "non-timing.md": _write_note(hermetic_vault, "non-timing.md"),
            "legacy.md": _write_note(hermetic_vault, "legacy.md"),
        }
        _write_state(state_path, [missing_title, non_timing_gap, legacy_no_signal])

        counts = csf.sweep_finalize(state_path, NOW, hermetic_vault)

        # Zero all-day events; every aged-out ineligible record is released.
        assert counts["aged_out"] == 3
        assert counts["finalized"] == 0 and counts["reconciled"] == 0
        assert counts["released"] == 3 and counts["retained"] == 0
        assert calendar.create_count == 0
        assert _log_rows(log_path) == []  # nothing routed, no marker

        # Delete-and-release: each record removed, each note left UNPROCESSED for
        # a later re-scan (NOT marked processed).
        assert _read_state(state_path) == []
        for note in notes.values():
            assert _note_status(note) == "unprocessed"


# ===========================================================================
# T013 — Fail-closed + week-drift [FR-008, INV-3/5]
# ===========================================================================


class TestT013FailClosedAndWeekDrift:
    def test_fail_closed_calendar_error_retains_record_note_unprocessed(
        self,
        hermetic_vault: Path,
        log_path: Path,
        calendar: _CalendarFake,
        state_path: Path,
    ) -> None:
        note = _write_note(hermetic_vault, "Rob fail-closed.md")
        _write_state(state_path, [_eligible_record(note.name)])

        calendar.mode = "error"
        counts = csf.sweep_finalize(state_path, NOW, hermetic_vault)

        # No partial event, no log row, note unprocessed, record retained.
        assert counts["retained"] == 1 and counts["finalized"] == 0
        assert _note_status(note) == "unprocessed"
        assert _log_rows(log_path) == []
        assert len(_read_state(state_path)) == 1

    def test_week_drift_uses_persisted_start_date_not_a_reparse(
        self,
        hermetic_vault: Path,
        log_path: Path,
        calendar: _CalendarFake,
        state_path: Path,
    ) -> None:
        """INV-5: the created event's date equals the date resolved at CAPTURE
        time (the persisted ``start_date``), regardless of what a natural-language
        re-parse at sweep time would yield. The record carries a misleading
        ``start_natural`` the deterministic path must ignore."""
        note = _write_note(hermetic_vault, "Rob week-drift.md")
        record = _eligible_record(
            note.name,
            extra_payload={"start_natural": "next Thursday"},  # a re-parse trap
        )
        _write_state(state_path, [record])

        counts = csf.sweep_finalize(state_path, NOW, hermetic_vault)

        assert counts["finalized"] == 1
        assert calendar.create_count == 1
        envelope = calendar.calls[0]["envelope"]
        # The event date is the PERSISTED start_date, not any NL re-parse.
        assert envelope["start_date"] == RESOLVED_DATE
        assert envelope["end_date"] == RESOLVED_END
        # The calendar row's marker records the same fallback event.
        assert len(_rows_of_kind(log_path, csf.FALLBACK_MARKER_KIND)) == 1
        assert _note_status(note) == "processed"
