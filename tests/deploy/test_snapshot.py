"""Tests for :mod:`scripts.deploy.lib.snapshot`."""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

import pytest

from scripts.deploy.lib import LibResult, snapshot


def _write_log(log_dir: Path, date: str, body: str) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"backup-{date}.log"
    path.write_text(body, encoding="utf-8")
    return path


@pytest.fixture
def freeze_now(monkeypatch):
    """Pin :func:`snapshot._utc_now` for deterministic age math."""

    def _install(when: _dt.datetime) -> None:
        monkeypatch.setattr(snapshot, "_utc_now", lambda: when)

    return _install


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

    result = snapshot.verify_restic_recent(max_age_hours=24, log_dir=log_dir)

    assert isinstance(result, LibResult)
    assert result.ok is True
    assert result.details["age_hours"] < 24


def test_returns_too_old_when_completed_line_outside_window(tmp_path, freeze_now):
    log_dir = tmp_path / "logs"
    now = _dt.datetime(2026, 6, 12, 12, 0, 0, tzinfo=_dt.timezone.utc)
    freeze_now(now)
    body = "2026-06-10T03:00:00Z snapshot saved\n"  # 57h ago
    _write_log(log_dir, "2026-06-10", body)

    result = snapshot.verify_restic_recent(max_age_hours=24, log_dir=log_dir)

    assert result.ok is False
    assert result.details["error_code"] == "RESTIC_TOO_OLD"


def test_returns_log_dir_missing_when_directory_absent(tmp_path):
    missing = tmp_path / "does-not-exist"

    result = snapshot.verify_restic_recent(max_age_hours=24, log_dir=missing)

    assert result.ok is False
    assert result.details["error_code"] == "LOG_DIR_MISSING"


def test_returns_no_logs_when_directory_empty(tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    result = snapshot.verify_restic_recent(max_age_hours=24, log_dir=log_dir)

    assert result.ok is False
    assert result.details["error_code"] == "NO_LOGS"


def test_returns_no_completed_lines_when_log_has_no_success_signature(tmp_path, freeze_now):
    log_dir = tmp_path / "logs"
    freeze_now(_dt.datetime(2026, 6, 12, 12, 0, 0, tzinfo=_dt.timezone.utc))
    body = "2026-06-12T03:00:00Z starting restic backup\n2026-06-12T03:05:00Z error: repo unreachable\n"
    _write_log(log_dir, "2026-06-12", body)

    result = snapshot.verify_restic_recent(max_age_hours=24, log_dir=log_dir)

    assert result.ok is False
    assert result.details["error_code"] == "NO_COMPLETED_LINES"


def test_recognises_alternative_completed_signatures(tmp_path, freeze_now):
    log_dir = tmp_path / "logs"
    freeze_now(_dt.datetime(2026, 6, 12, 12, 0, 0, tzinfo=_dt.timezone.utc))
    body = "2026-06-12T11:30:00Z backup completed\n"
    _write_log(log_dir, "2026-06-12", body)

    result = snapshot.verify_restic_recent(max_age_hours=24, log_dir=log_dir)

    assert result.ok is True


def test_rejects_zero_or_negative_max_age(tmp_path):
    result = snapshot.verify_restic_recent(max_age_hours=0, log_dir=tmp_path)
    assert result.ok is False
    assert result.details["error_code"] == "INVALID_ARGUMENT"


def test_ignores_non_log_filenames(tmp_path, freeze_now):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "README.md").write_text("not a log", encoding="utf-8")
    freeze_now(_dt.datetime(2026, 6, 12, 12, 0, 0, tzinfo=_dt.timezone.utc))

    result = snapshot.verify_restic_recent(max_age_hours=24, log_dir=log_dir)

    assert result.ok is False
    assert result.details["error_code"] == "NO_LOGS"


def test_picks_most_recent_log_when_multiple_present(tmp_path, freeze_now):
    log_dir = tmp_path / "logs"
    now = _dt.datetime(2026, 6, 12, 12, 0, 0, tzinfo=_dt.timezone.utc)
    freeze_now(now)
    _write_log(log_dir, "2026-06-10", "2026-06-10T03:00:00Z snapshot saved\n")  # stale
    _write_log(log_dir, "2026-06-12", "2026-06-12T11:00:00Z snapshot saved\n")  # recent

    result = snapshot.verify_restic_recent(max_age_hours=24, log_dir=log_dir)

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

    result = snapshot.verify_restic_recent(max_age_hours=24, log_dir=log_dir)

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

    result = snapshot.verify_restic_recent(max_age_hours=24, log_dir=log_dir)

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

    result = snapshot.verify_restic_recent(max_age_hours=24, log_dir=log_dir)

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
    result = snapshot.verify_restic_recent(max_age_hours=24, log_dir=log_dir)
    assert result.ok is True
    assert result.details["latest_completed_at"] == "2026-06-12T23:59:59+00:00"
