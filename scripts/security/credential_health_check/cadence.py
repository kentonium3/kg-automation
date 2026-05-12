"""Cadence boundary math.

Pure date arithmetic. No I/O. No external dependencies beyond stdlib + the
Credential dataclass.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from .manifest import Credential, FIXED_INTERVAL_CADENCES


WARNING_WINDOW_DAYS = 30
ANNUAL_DAYS = 365


CADENCE_INTERVALS: dict[str, timedelta] = {
    "annual": timedelta(days=ANNUAL_DAYS),
    # Extensible: add other fixed-interval cadences here as the manifest schema
    # grows. Any entry added here must also appear in
    # manifest.FIXED_INTERVAL_CADENCES.
}


def is_fixed_interval_cadence(review_cadence: str) -> bool:
    """True if review_cadence drives boundary math (vs. monitor-activity etc.)."""
    return review_cadence in CADENCE_INTERVALS


def compute_boundary(credential: Credential) -> Optional[date]:
    """Return the cadence boundary date for a fixed-interval credential.

    Returns None for non-fixed-interval cadences (monitor-activity,
    on-revocation, n/a, session). Returns None defensively if the credential
    is fixed-interval but has no anchor date — well-formed credentials always
    have one per manifest validation.
    """
    if not is_fixed_interval_cadence(credential.review_cadence):
        return None
    anchor = credential.last_reviewed or credential.created_date
    if anchor is None:
        return None
    return anchor + CADENCE_INTERVALS[credential.review_cadence]


def is_within_warning_window(
    boundary: date,
    today: date,
    window_days: int = WARNING_WINDOW_DAYS,
) -> bool:
    """True iff boundary is within `window_days` of today, OR already crossed.

    Equivalent: boundary - today <= timedelta(days=window_days).
    At the edge (boundary exactly window_days out) returns True.
    """
    return (boundary - today) <= timedelta(days=window_days)
