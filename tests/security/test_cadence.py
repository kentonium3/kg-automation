"""Tests for credential_health_check.cadence."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from credential_health_check.cadence import (
    WARNING_WINDOW_DAYS,
    compute_boundary,
    is_fixed_interval_cadence,
    is_within_warning_window,
)
from credential_health_check.manifest import Credential


def _make_credential(**overrides) -> Credential:
    """Construct a minimal-but-valid Credential for tests."""
    defaults = dict(
        name="test-cred",
        review_cadence="annual",
        storage="test-storage",
        expiry_notes="test rotation procedure",
        type="api-token",
        last_reviewed=date(2025, 5, 11),
    )
    defaults.update(overrides)
    return Credential(**defaults)


# ---------- is_fixed_interval_cadence ----------


def test_annual_is_fixed_interval():
    assert is_fixed_interval_cadence("annual") is True


def test_monitor_activity_is_not_fixed_interval():
    assert is_fixed_interval_cadence("monitor-activity") is False


def test_on_revocation_is_not_fixed_interval():
    assert is_fixed_interval_cadence("on-revocation") is False


def test_session_is_not_fixed_interval():
    assert is_fixed_interval_cadence("session") is False


def test_na_is_not_fixed_interval():
    assert is_fixed_interval_cadence("n/a") is False


# ---------- compute_boundary ----------


def test_compute_boundary_annual_adds_365_days():
    cred = _make_credential(last_reviewed=date(2025, 5, 11))
    assert compute_boundary(cred) == date(2026, 5, 11)


def test_compute_boundary_uses_created_date_when_last_reviewed_missing():
    cred = _make_credential(last_reviewed=None, created_date=date(2025, 5, 11))
    assert compute_boundary(cred) == date(2026, 5, 11)


def test_compute_boundary_prefers_last_reviewed_over_created_date():
    cred = _make_credential(
        last_reviewed=date(2026, 1, 1), created_date=date(2025, 5, 11)
    )
    assert compute_boundary(cred) == date(2027, 1, 1)


def test_compute_boundary_returns_none_for_monitor_activity():
    cred = _make_credential(review_cadence="monitor-activity", last_reviewed=None)
    assert compute_boundary(cred) is None


def test_compute_boundary_returns_none_for_on_revocation():
    cred = _make_credential(review_cadence="on-revocation", last_reviewed=None)
    assert compute_boundary(cred) is None


def test_compute_boundary_returns_none_when_anchor_missing():
    cred = _make_credential(last_reviewed=None, created_date=None)
    assert compute_boundary(cred) is None


# ---------- is_within_warning_window ----------


def test_within_window_at_exact_boundary():
    today = date(2026, 5, 11)
    boundary = today + timedelta(days=WARNING_WINDOW_DAYS)
    assert is_within_warning_window(boundary, today) is True


def test_within_window_one_day_inside():
    today = date(2026, 5, 11)
    boundary = today + timedelta(days=WARNING_WINDOW_DAYS - 1)
    assert is_within_warning_window(boundary, today) is True


def test_outside_window_one_day_beyond():
    today = date(2026, 5, 11)
    boundary = today + timedelta(days=WARNING_WINDOW_DAYS + 1)
    assert is_within_warning_window(boundary, today) is False


def test_within_window_in_the_past_is_true():
    """A boundary that's already crossed is by definition inside the window."""
    today = date(2026, 5, 11)
    boundary = today - timedelta(days=5)
    assert is_within_warning_window(boundary, today) is True


def test_within_window_custom_threshold():
    today = date(2026, 5, 11)
    boundary = today + timedelta(days=20)
    assert is_within_warning_window(boundary, today, window_days=14) is False
    assert is_within_warning_window(boundary, today, window_days=21) is True


def test_within_window_boundary_far_in_future():
    today = date(2026, 5, 11)
    boundary = today + timedelta(days=1000)
    assert is_within_warning_window(boundary, today) is False
