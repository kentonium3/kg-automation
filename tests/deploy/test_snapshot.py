"""Tests for :mod:`scripts.deploy.lib.snapshot`."""

from __future__ import annotations

import datetime as _dt
import json
import subprocess
from pathlib import Path

import pytest

from scripts.deploy.lib import LibResult, snapshot


def _write_log(log_dir: Path, date: str, body: str) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"backup-{date}.log"
    path.write_text(body, encoding="utf-8")
    return path


def _write_state(tmp_path: Path, payload: dict | str) -> Path:
    """Write a ``last-backup.json``-shaped state file and return its path."""
    path = tmp_path / "last-backup.json"
    text = payload if isinstance(payload, str) else json.dumps(payload)
    path.write_text(text, encoding="utf-8")
    return path


def _absent_state(tmp_path: Path) -> Path:
    """A state_path guaranteed not to exist, to force the log-fallback path.

    The default state_path is the real ``/data/services/backup/state/…`` file,
    which exists on office2; log-oriented tests must pin an absent path so they
    exercise the fallback deterministically regardless of host.
    """
    return tmp_path / "no-such-state.json"


@pytest.fixture
def freeze_now(monkeypatch):
    """Pin :func:`snapshot._utc_now` for deterministic age math."""

    def _install(when: _dt.datetime) -> None:
        monkeypatch.setattr(snapshot, "_utc_now", lambda: when)

    return _install


# ---------------------------------------------------------------------------
# Log-fallback path (state file absent). All calls pin an absent state_path.
# ---------------------------------------------------------------------------


def test_returns_ok_when_recent_completed_line_within_window(tmp_path, freeze_now):
    log_dir = tmp_path / "logs"
    now = _dt.datetime(2026, 6, 12, 12, 0, 0, tzinfo=_dt.timezone.utc)
    freeze_now(now)
    body = (
        "2026-06-12T03:00:01Z starting restic backup\n"
        "2026-06-12T03:05:12Z snapshot saved at deadbeefcafe\n"
        "2026-06-12T03:05:13Z status: ok\n"
    )
    _write_log(log_dir, "2026-06-12", body)

    result = snapshot.verify_restic_recent(
        max_age_hours=24, log_dir=log_dir, state_path=_absent_state(tmp_path)
    )

    assert isinstance(result, LibResult)
    assert result.ok is True
    assert result.details["age_hours"] < 24
    assert result.details["source"] == "log"


def test_returns_too_old_when_completed_line_outside_window(tmp_path, freeze_now):
    log_dir = tmp_path / "logs"
    now = _dt.datetime(2026, 6, 12, 12, 0, 0, tzinfo=_dt.timezone.utc)
    freeze_now(now)
    body = "2026-06-10T03:00:00Z snapshot saved\n"  # 57h ago
    _write_log(log_dir, "2026-06-10", body)

    result = snapshot.verify_restic_recent(
        max_age_hours=24, log_dir=log_dir, state_path=_absent_state(tmp_path)
    )

    assert result.ok is False
    assert result.details["error_code"] == "RESTIC_TOO_OLD"


def test_returns_log_dir_missing_when_directory_absent(tmp_path):
    missing = tmp_path / "does-not-exist"

    result = snapshot.verify_restic_recent(
        max_age_hours=24, log_dir=missing, state_path=_absent_state(tmp_path)
    )

    assert result.ok is False
    assert result.details["error_code"] == "LOG_DIR_MISSING"


def test_returns_no_logs_when_directory_empty(tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    result = snapshot.verify_restic_recent(
        max_age_hours=24, log_dir=log_dir, state_path=_absent_state(tmp_path)
    )

    assert result.ok is False
    assert result.details["error_code"] == "NO_LOGS"


def test_returns_no_completed_lines_when_log_has_no_success_signature(tmp_path, freeze_now):
    log_dir = tmp_path / "logs"
    freeze_now(_dt.datetime(2026, 6, 12, 12, 0, 0, tzinfo=_dt.timezone.utc))
    body = "2026-06-12T03:00:00Z starting restic backup\n2026-06-12T03:05:00Z error: repo unreachable\n"
    _write_log(log_dir, "2026-06-12", body)

    result = snapshot.verify_restic_recent(
        max_age_hours=24, log_dir=log_dir, state_path=_absent_state(tmp_path)
    )

    assert result.ok is False
    assert result.details["error_code"] == "NO_COMPLETED_LINES"


def test_recognises_alternative_completed_signatures(tmp_path, freeze_now):
    log_dir = tmp_path / "logs"
    freeze_now(_dt.datetime(2026, 6, 12, 12, 0, 0, tzinfo=_dt.timezone.utc))
    body = "2026-06-12T11:30:00Z backup completed\n"
    _write_log(log_dir, "2026-06-12", body)

    result = snapshot.verify_restic_recent(
        max_age_hours=24, log_dir=log_dir, state_path=_absent_state(tmp_path)
    )

    assert result.ok is True


def test_rejects_zero_or_negative_max_age(tmp_path):
    result = snapshot.verify_restic_recent(
        max_age_hours=0, log_dir=tmp_path, state_path=_absent_state(tmp_path)
    )
    assert result.ok is False
    assert result.details["error_code"] == "INVALID_ARGUMENT"


def test_ignores_non_log_filenames(tmp_path, freeze_now):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "README.md").write_text("not a log", encoding="utf-8")
    freeze_now(_dt.datetime(2026, 6, 12, 12, 0, 0, tzinfo=_dt.timezone.utc))

    result = snapshot.verify_restic_recent(
        max_age_hours=24, log_dir=log_dir, state_path=_absent_state(tmp_path)
    )

    assert result.ok is False
    assert result.details["error_code"] == "NO_LOGS"


def test_picks_most_recent_log_when_multiple_present(tmp_path, freeze_now):
    log_dir = tmp_path / "logs"
    now = _dt.datetime(2026, 6, 12, 12, 0, 0, tzinfo=_dt.timezone.utc)
    freeze_now(now)
    _write_log(log_dir, "2026-06-10", "2026-06-10T03:00:00Z snapshot saved\n")  # stale
    _write_log(log_dir, "2026-06-12", "2026-06-12T11:00:00Z snapshot saved\n")  # recent

    result = snapshot.verify_restic_recent(
        max_age_hours=24, log_dir=log_dir, state_path=_absent_state(tmp_path)
    )

    assert result.ok is True
    assert "2026-06-12" in result.details["log_path"]


# ---------------------------------------------------------------------------
# #665 — the REAL Restic driver log format: bracketed time-only completion
# lines (e.g. "[04:00:08] Backup completed successfully"). The pre-#665 tests
# only fed full-ISO timestamps, so they never exercised the live format and the
# end-of-day-fallback bug shipped. These use the actual on-disk shape.
# ---------------------------------------------------------------------------


_REAL_LOG_BODY = (
    "=== Backup: 2026-06-12 ===\n"
    "[03:00:05] Starting backup of /data and /home...\n"
    "[03:00:12] Backup completed successfully\n"
    "[03:00:14] === Backup complete ===\n"
)


def test_bracketed_time_only_line_uses_real_completion_instant(tmp_path, freeze_now):
    """#665: age is computed from the bracketed [HH:MM:SS] + log date, NOT
    end-of-day. A snapshot ~9h before `now` must read ~9h, never a negative or
    end-of-day-derived value."""
    log_dir = tmp_path / "logs"
    now = _dt.datetime(2026, 6, 12, 12, 0, 0, tzinfo=_dt.timezone.utc)
    freeze_now(now)
    _write_log(log_dir, "2026-06-12", _REAL_LOG_BODY)  # last completed [03:00:14]

    result = snapshot.verify_restic_recent(
        max_age_hours=24, log_dir=log_dir, state_path=_absent_state(tmp_path)
    )

    assert result.ok is True
    # 12:00:00 - 03:00:14 == 8.996h. Pre-fix this parsed as 23:59:59 EOD →
    # a NEGATIVE age (-12h). Assert the real, positive value.
    assert result.details["age_hours"] == pytest.approx(9.0, abs=0.05)
    assert result.details["latest_completed_at"] == "2026-06-12T03:00:14+00:00"


def test_bracketed_time_only_recent_snapshot_is_not_negative(tmp_path, freeze_now):
    """The headline #665 symptom: a snapshot taken minutes ago must read a
    small POSITIVE age, not the -21.7h the end-of-day fallback produced."""
    log_dir = tmp_path / "logs"
    now = _dt.datetime(2026, 6, 12, 4, 2, 0, tzinfo=_dt.timezone.utc)  # 1.4 min later
    freeze_now(now)
    body = (
        "=== Backup: 2026-06-12 ===\n"
        "[04:00:36] Backup completed successfully\n"
    )
    _write_log(log_dir, "2026-06-12", body)

    result = snapshot.verify_restic_recent(
        max_age_hours=24, log_dir=log_dir, state_path=_absent_state(tmp_path)
    )

    assert result.ok is True
    assert result.details["age_hours"] >= 0.0
    assert result.details["age_hours"] == pytest.approx(0.024, abs=0.01)


def test_bracketed_time_only_too_old_is_detected(tmp_path, freeze_now):
    """A genuinely stale bracketed-format snapshot must trip RESTIC_TOO_OLD
    off its real instant (not a coincidentally-passing EOD value)."""
    log_dir = tmp_path / "logs"
    now = _dt.datetime(2026, 6, 14, 12, 0, 0, tzinfo=_dt.timezone.utc)
    freeze_now(now)
    body = "=== Backup: 2026-06-12 ===\n[03:00:12] Backup completed successfully\n"
    _write_log(log_dir, "2026-06-12", body)  # ~57h before now

    result = snapshot.verify_restic_recent(
        max_age_hours=24, log_dir=log_dir, state_path=_absent_state(tmp_path)
    )

    assert result.ok is False
    assert result.details["error_code"] == "RESTIC_TOO_OLD"
    assert result.details["age_hours"] == pytest.approx(57.0, abs=0.05)


def test_unparseable_completed_line_still_falls_back_to_end_of_day(tmp_path, freeze_now):
    """The last-resort EOD fallback is preserved for a completion line with no
    parseable timestamp at all (neither full-ISO nor bracketed time)."""
    log_dir = tmp_path / "logs"
    now = _dt.datetime(2026, 6, 12, 23, 0, 0, tzinfo=_dt.timezone.utc)
    freeze_now(now)
    _write_log(log_dir, "2026-06-12", "backup completed\n")  # no timestamp token
    result = snapshot.verify_restic_recent(
        max_age_hours=24, log_dir=log_dir, state_path=_absent_state(tmp_path)
    )
    assert result.ok is True
    assert result.details["latest_completed_at"] == "2026-06-12T23:59:59+00:00"


# ---------------------------------------------------------------------------
# #767 — authoritative state-file path. Preferred over the log parse; gives
# genuine success verification (restic_exit_code) and an exact UTC instant.
# ---------------------------------------------------------------------------


def _state_payload(
    *,
    exit_code: int | None = 0,
    snapshot_ts: str | None = "2026-06-12T03:00:05Z",
    finished_ts: str | None = "2026-06-12T03:00:13Z",
) -> dict:
    payload: dict = {"schema_version": 1}
    if exit_code is not None:
        payload["restic_exit_code"] = exit_code
    if snapshot_ts is not None:
        payload["snapshot_timestamp_utc"] = snapshot_ts
    if finished_ts is not None:
        payload["script_finished_at_utc"] = finished_ts
    return payload


def test_state_file_ok_within_window_uses_snapshot_timestamp(tmp_path, freeze_now):
    now = _dt.datetime(2026, 6, 12, 12, 0, 0, tzinfo=_dt.timezone.utc)
    freeze_now(now)
    state = _write_state(tmp_path, _state_payload(exit_code=0))
    # A stale LOG in the same call must be ignored — the state file wins.
    log_dir = tmp_path / "logs"
    _write_log(log_dir, "2026-06-01", "2026-06-01T03:00:00Z snapshot saved\n")

    result = snapshot.verify_restic_recent(
        max_age_hours=24, log_dir=log_dir, state_path=state
    )

    assert result.ok is True
    assert result.details["source"] == "state"
    assert result.details["restic_exit_code"] == 0
    assert result.details["instant_field"] == "snapshot_timestamp_utc"
    assert result.details["latest_completed_at"] == "2026-06-12T03:00:05+00:00"
    assert result.details["age_hours"] == pytest.approx(8.999, abs=0.01)


def test_state_file_exit_code_3_counts_as_success(tmp_path, freeze_now):
    """restic exit 3 (snapshot created, some files unreadable) is a valid,
    restorable snapshot — the system-wide {0, 3} convention."""
    freeze_now(_dt.datetime(2026, 6, 12, 12, 0, 0, tzinfo=_dt.timezone.utc))
    state = _write_state(tmp_path, _state_payload(exit_code=3))

    result = snapshot.verify_restic_recent(
        max_age_hours=24, log_dir=tmp_path / "logs", state_path=state
    )

    assert result.ok is True
    assert result.details["restic_exit_code"] == 3


def test_state_file_failure_exit_code_blocks_and_does_not_fall_through(tmp_path, freeze_now):
    """An explicit restic failure must fail the gate — never masked by an
    older 'completed' log line (the fail-open hole #767 closes)."""
    freeze_now(_dt.datetime(2026, 6, 12, 12, 0, 0, tzinfo=_dt.timezone.utc))
    state = _write_state(tmp_path, _state_payload(exit_code=1))
    # A perfectly fresh, successful-looking log must NOT rescue a failed backup.
    log_dir = tmp_path / "logs"
    _write_log(log_dir, "2026-06-12", "2026-06-12T11:59:00Z snapshot saved\n")

    result = snapshot.verify_restic_recent(
        max_age_hours=24, log_dir=log_dir, state_path=state
    )

    assert result.ok is False
    assert result.details["error_code"] == "RESTIC_FAILED"
    assert result.details["source"] == "state"
    assert result.details["restic_exit_code"] == 1


def test_state_file_too_old_trips_restic_too_old(tmp_path, freeze_now):
    now = _dt.datetime(2026, 6, 14, 12, 0, 0, tzinfo=_dt.timezone.utc)
    freeze_now(now)
    state = _write_state(
        tmp_path,
        _state_payload(
            exit_code=0,
            snapshot_ts="2026-06-12T03:00:05Z",  # ~57h old
            finished_ts="2026-06-12T03:00:13Z",
        ),
    )

    result = snapshot.verify_restic_recent(
        max_age_hours=24, log_dir=tmp_path / "logs", state_path=state
    )

    assert result.ok is False
    assert result.details["error_code"] == "RESTIC_TOO_OLD"
    assert result.details["source"] == "state"


def test_state_null_snapshot_ts_does_not_anchor_on_script_finished(tmp_path, freeze_now):
    """#767 review: a good exit code but null snapshot_timestamp_utc must NOT be
    green-lit off the script-finished witness (the backup-health contract treats
    a null snapshot instant as unconfirmed). It falls back to the log path."""
    now = _dt.datetime(2026, 6, 12, 12, 0, 0, tzinfo=_dt.timezone.utc)
    freeze_now(now)
    state = _write_state(
        tmp_path,
        _state_payload(exit_code=0, snapshot_ts=None, finished_ts="2026-06-12T03:00:13Z"),
    )
    log_dir = tmp_path / "logs"
    _write_log(log_dir, "2026-06-12", "2026-06-12T11:00:00Z snapshot saved\n")

    result = snapshot.verify_restic_recent(
        max_age_hours=24, log_dir=log_dir, state_path=state
    )

    assert result.ok is True
    assert result.details["source"] == "log"


def test_state_null_snapshot_ts_and_no_log_fails(tmp_path, freeze_now):
    """With a null snapshot instant AND no usable log, the gate fails closed —
    the script-finished witness alone never authorizes the deploy."""
    now = _dt.datetime(2026, 6, 12, 12, 0, 0, tzinfo=_dt.timezone.utc)
    freeze_now(now)
    state = _write_state(
        tmp_path,
        _state_payload(exit_code=0, snapshot_ts=None, finished_ts="2026-06-12T03:00:13Z"),
    )

    result = snapshot.verify_restic_recent(
        max_age_hours=24, log_dir=tmp_path / "logs", state_path=state
    )

    assert result.ok is False
    # Fell through to the log path, which then found no log dir → fails closed.
    assert result.details["error_code"] == "LOG_DIR_MISSING"


def test_state_future_snapshot_ts_fails_closed_no_fallthrough(tmp_path, freeze_now):
    """#767 review: a snapshot_timestamp_utc in the future beyond skew must fail
    closed (RESTIC_TIMESTAMP_IN_FUTURE), never read as 'very fresh', and must NOT
    be rescued by a fresh log line."""
    now = _dt.datetime(2026, 6, 12, 12, 0, 0, tzinfo=_dt.timezone.utc)
    freeze_now(now)
    state = _write_state(
        tmp_path,
        _state_payload(exit_code=0, snapshot_ts="2026-06-13T12:00:00Z"),  # +24h
    )
    log_dir = tmp_path / "logs"
    _write_log(log_dir, "2026-06-12", "2026-06-12T11:59:00Z snapshot saved\n")

    result = snapshot.verify_restic_recent(
        max_age_hours=24, log_dir=log_dir, state_path=state
    )

    assert result.ok is False
    assert result.details["error_code"] == "RESTIC_TIMESTAMP_IN_FUTURE"
    assert result.details["source"] == "state"


def test_state_small_future_skew_is_tolerated(tmp_path, freeze_now):
    """Benign same-host sub-minute future skew is treated as fresh, not rejected."""
    now = _dt.datetime(2026, 6, 12, 12, 0, 0, tzinfo=_dt.timezone.utc)
    freeze_now(now)
    state = _write_state(
        tmp_path,
        _state_payload(exit_code=0, snapshot_ts="2026-06-12T12:00:30Z"),  # +30s
    )

    result = snapshot.verify_restic_recent(
        max_age_hours=24, log_dir=tmp_path / "logs", state_path=state
    )

    assert result.ok is True
    assert result.details["source"] == "state"


def test_state_naive_snapshot_ts_falls_back_to_log(tmp_path, freeze_now):
    """#767 review: a naive (no Z/offset) state timestamp is malformed on the
    authoritative path — no timezone guessing — and falls back to the log."""
    now = _dt.datetime(2026, 6, 12, 12, 0, 0, tzinfo=_dt.timezone.utc)
    freeze_now(now)
    state = _write_state(
        tmp_path,
        _state_payload(exit_code=0, snapshot_ts="2026-06-12T03:00:05"),  # no Z
    )
    log_dir = tmp_path / "logs"
    _write_log(log_dir, "2026-06-12", "2026-06-12T11:00:00Z snapshot saved\n")

    result = snapshot.verify_restic_recent(
        max_age_hours=24, log_dir=log_dir, state_path=state
    )

    assert result.ok is True
    assert result.details["source"] == "log"


def test_state_file_missing_falls_back_to_log(tmp_path, freeze_now):
    now = _dt.datetime(2026, 6, 12, 12, 0, 0, tzinfo=_dt.timezone.utc)
    freeze_now(now)
    log_dir = tmp_path / "logs"
    _write_log(log_dir, "2026-06-12", "2026-06-12T11:00:00Z snapshot saved\n")

    result = snapshot.verify_restic_recent(
        max_age_hours=24, log_dir=log_dir, state_path=tmp_path / "absent.json"
    )

    assert result.ok is True
    assert result.details["source"] == "log"


def test_state_file_malformed_json_falls_back_to_log(tmp_path, freeze_now):
    now = _dt.datetime(2026, 6, 12, 12, 0, 0, tzinfo=_dt.timezone.utc)
    freeze_now(now)
    state = _write_state(tmp_path, "{ this is not json")
    log_dir = tmp_path / "logs"
    _write_log(log_dir, "2026-06-12", "2026-06-12T11:00:00Z snapshot saved\n")

    result = snapshot.verify_restic_recent(
        max_age_hours=24, log_dir=log_dir, state_path=state
    )

    assert result.ok is True
    assert result.details["source"] == "log"


def test_state_file_missing_exit_code_falls_back_to_log(tmp_path, freeze_now):
    now = _dt.datetime(2026, 6, 12, 12, 0, 0, tzinfo=_dt.timezone.utc)
    freeze_now(now)
    state = _write_state(tmp_path, _state_payload(exit_code=None))
    log_dir = tmp_path / "logs"
    _write_log(log_dir, "2026-06-12", "2026-06-12T11:00:00Z snapshot saved\n")

    result = snapshot.verify_restic_recent(
        max_age_hours=24, log_dir=log_dir, state_path=state
    )

    assert result.ok is True
    assert result.details["source"] == "log"


def test_state_file_no_instant_falls_back_to_log(tmp_path, freeze_now):
    """exit code says success but neither timestamp is parseable → fall back."""
    now = _dt.datetime(2026, 6, 12, 12, 0, 0, tzinfo=_dt.timezone.utc)
    freeze_now(now)
    state = _write_state(
        tmp_path, _state_payload(exit_code=0, snapshot_ts=None, finished_ts=None)
    )
    log_dir = tmp_path / "logs"
    _write_log(log_dir, "2026-06-12", "2026-06-12T11:00:00Z snapshot saved\n")

    result = snapshot.verify_restic_recent(
        max_age_hours=24, log_dir=log_dir, state_path=state
    )

    assert result.ok is True
    assert result.details["source"] == "log"


def test_state_file_boolean_exit_code_is_rejected(tmp_path, freeze_now):
    """A JSON ``true`` must not masquerade as exit 1 / ``false`` as exit 0."""
    now = _dt.datetime(2026, 6, 12, 12, 0, 0, tzinfo=_dt.timezone.utc)
    freeze_now(now)
    state = _write_state(
        tmp_path,
        {
            "schema_version": 1,
            "restic_exit_code": False,
            "snapshot_timestamp_utc": "2026-06-12T03:00:05Z",
        },
    )
    log_dir = tmp_path / "logs"
    _write_log(log_dir, "2026-06-12", "2026-06-12T11:00:00Z snapshot saved\n")

    result = snapshot.verify_restic_recent(
        max_age_hours=24, log_dir=log_dir, state_path=state
    )

    assert result.ok is True
    assert result.details["source"] == "log"


# ---------------------------------------------------------------------------
# #784 — ensure_recent_backup: verify → trigger-if-stale → re-verify. The real
# `sudo backup.sh` is never spawned here; the trigger is either injected via
# `backup_cmd` (a harmless local command) or stubbed at the module level.
# ---------------------------------------------------------------------------


def test_ensure_fresh_backup_does_not_trigger(tmp_path, freeze_now, monkeypatch):
    """A fresh successful state file short-circuits — no backup is triggered."""
    now = _dt.datetime(2026, 6, 12, 12, 0, 0, tzinfo=_dt.timezone.utc)
    freeze_now(now)
    state = _write_state(tmp_path, _state_payload(exit_code=0))

    def _boom(*args, **kwargs):
        raise AssertionError("_invoke_backup called despite a fresh backup")

    monkeypatch.setattr(snapshot, "_invoke_backup", _boom)

    result = snapshot.ensure_recent_backup(
        max_age_hours=24, log_dir=tmp_path / "logs", state_path=state
    )

    assert result.ok is True
    assert result.details["triggered"] is False
    assert result.details["source"] == "state"


def test_ensure_stale_backup_triggers_then_reverifies_fresh(tmp_path, freeze_now, monkeypatch):
    """Stale → trigger (injected harmless cmd) → the trigger makes the state
    fresh → re-verify passes. We simulate the state transition by rewriting the
    state file inside the injected trigger."""
    now = _dt.datetime(2026, 6, 12, 12, 0, 0, tzinfo=_dt.timezone.utc)
    freeze_now(now)
    state = _write_state(
        tmp_path, _state_payload(exit_code=0, snapshot_ts="2026-06-01T03:00:00Z")  # stale
    )
    triggered = {"count": 0}

    def _fake_trigger(backup_cmd, timeout_sec):
        triggered["count"] += 1
        # emulate backup.sh writing a fresh state file
        _write_state(tmp_path, _state_payload(exit_code=0, snapshot_ts="2026-06-12T11:59:00Z"))
        return LibResult(ok=True, summary="triggered", details={"returncode": 0})

    monkeypatch.setattr(snapshot, "_invoke_backup", _fake_trigger)

    result = snapshot.ensure_recent_backup(
        max_age_hours=24, log_dir=tmp_path / "logs", state_path=state
    )

    assert result.ok is True
    assert result.details["triggered"] is True
    assert result.details["source"] == "state"
    assert triggered["count"] == 1


def test_ensure_failed_trigger_blocks(tmp_path, freeze_now, monkeypatch):
    """A failed trigger returns ok=False (apply must be blocked)."""
    now = _dt.datetime(2026, 6, 12, 12, 0, 0, tzinfo=_dt.timezone.utc)
    freeze_now(now)
    state = _write_state(
        tmp_path, _state_payload(exit_code=0, snapshot_ts="2026-06-01T03:00:00Z")  # stale
    )

    def _fail_trigger(backup_cmd, timeout_sec):
        return LibResult(
            ok=False,
            summary="boom",
            details={"error_code": "BACKUP_TRIGGER_FAILED", "returncode": 2},
        )

    monkeypatch.setattr(snapshot, "_invoke_backup", _fail_trigger)

    result = snapshot.ensure_recent_backup(
        max_age_hours=24, log_dir=tmp_path / "logs", state_path=state
    )

    assert result.ok is False
    assert result.details["error_code"] == "BACKUP_TRIGGER_FAILED"
    assert result.details["triggered"] is True
    assert result.details["pre_trigger_error"] == "RESTIC_TOO_OLD"


def test_ensure_trigger_ok_but_reverify_still_stale_blocks(tmp_path, freeze_now, monkeypatch):
    """Trigger succeeds but re-verify is still not fresh (e.g. backup produced no
    snapshot) → ok=False, apply blocked, reverify_failed flagged."""
    now = _dt.datetime(2026, 6, 12, 12, 0, 0, tzinfo=_dt.timezone.utc)
    freeze_now(now)
    state = _write_state(
        tmp_path, _state_payload(exit_code=0, snapshot_ts="2026-06-01T03:00:00Z")  # stale
    )

    def _noop_trigger(backup_cmd, timeout_sec):
        return LibResult(ok=True, summary="triggered", details={"returncode": 0})

    monkeypatch.setattr(snapshot, "_invoke_backup", _noop_trigger)

    result = snapshot.ensure_recent_backup(
        max_age_hours=24, log_dir=tmp_path / "logs", state_path=state
    )

    assert result.ok is False
    assert result.details["error_code"] == "RESTIC_TOO_OLD"
    assert result.details["triggered"] is True
    assert result.details["reverify_failed"] is True


def test_ensure_rejects_zero_max_age(tmp_path):
    result = snapshot.ensure_recent_backup(
        max_age_hours=0, log_dir=tmp_path / "logs", state_path=tmp_path / "s.json"
    )
    assert result.ok is False
    assert result.details["error_code"] == "INVALID_ARGUMENT"


def test_ensure_stale_triggers_real_local_command(tmp_path, freeze_now):
    """End-to-end trigger path with a real (harmless) subprocess: `true` exits 0.
    Re-verify then still stale (the state file is untouched) → blocked. Proves
    _invoke_backup actually spawns and the wiring holds without stubbing it."""
    now = _dt.datetime(2026, 6, 12, 12, 0, 0, tzinfo=_dt.timezone.utc)
    freeze_now(now)
    state = _write_state(
        tmp_path, _state_payload(exit_code=0, snapshot_ts="2026-06-01T03:00:00Z")  # stale
    )

    result = snapshot.ensure_recent_backup(
        max_age_hours=24,
        log_dir=tmp_path / "logs",
        state_path=state,
        backup_cmd=["true"],
    )

    assert result.ok is False  # `true` doesn't refresh the state → still stale
    assert result.details["triggered"] is True
    assert result.details["reverify_failed"] is True


def test_invoke_backup_nonzero_exit_is_failure():
    result = snapshot._invoke_backup(["false"], timeout_sec=30)
    assert result.ok is False
    assert result.details["error_code"] == "BACKUP_TRIGGER_FAILED"
    assert result.details["returncode"] != 0


def test_invoke_backup_missing_binary_is_spawn_failure():
    result = snapshot._invoke_backup(
        ["/nonexistent/path/backup.sh"], timeout_sec=30
    )
    assert result.ok is False
    assert result.details["error_code"] == "BACKUP_TRIGGER_SPAWN_FAILED"


def test_invoke_backup_success():
    result = snapshot._invoke_backup(["true"], timeout_sec=30)
    assert result.ok is True
    assert result.details["returncode"] == 0


def test_invoke_backup_timeout_is_failure(monkeypatch):
    """#784 review: a backup.sh that overruns the timeout must fail closed with
    BACKUP_TRIGGER_TIMEOUT (this gates destructive Tier-2 deploys)."""

    def _raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0] if args else "backup", timeout=kwargs.get("timeout", 0))

    monkeypatch.setattr(snapshot.subprocess, "run", _raise_timeout)

    result = snapshot._invoke_backup(["/data/services/backup/scripts/backup.sh"], timeout_sec=1)

    assert result.ok is False
    assert result.details["error_code"] == "BACKUP_TRIGGER_TIMEOUT"
    assert result.details["timeout_sec"] == 1


def test_ensure_backup_timeout_blocks_apply(tmp_path, freeze_now, monkeypatch):
    """A trigger timeout propagates as a snapshot-blocking failure from
    ensure_recent_backup (triggered=True, ok=False)."""
    now = _dt.datetime(2026, 6, 12, 12, 0, 0, tzinfo=_dt.timezone.utc)
    freeze_now(now)
    state = _write_state(
        tmp_path, _state_payload(exit_code=0, snapshot_ts="2026-06-01T03:00:00Z")  # stale
    )

    def _raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="backup", timeout=1)

    monkeypatch.setattr(snapshot.subprocess, "run", _raise_timeout)

    result = snapshot.ensure_recent_backup(
        max_age_hours=24, log_dir=tmp_path / "logs", state_path=state, timeout_sec=1
    )

    assert result.ok is False
    assert result.details["error_code"] == "BACKUP_TRIGGER_TIMEOUT"
    assert result.details["triggered"] is True
