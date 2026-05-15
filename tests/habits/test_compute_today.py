"""Tests for scripts/habits/compute_today.py (FR-001).

Verifies the contract in
kitty-specs/habits-checkin-d6-extract-01KRNV46/contracts/compute_today.md.

Critical assertion: `iso_eod_et` MUST NOT end with `Z` (regression-prevention
for issue #112 — habit due_dates anchored to ET end-of-day, never UTC).
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER = REPO_ROOT / "scripts" / "habits" / "compute_today.py"


def run_helper(*args: str) -> subprocess.CompletedProcess[str]:
    """Invoke the helper as a subprocess and return the completed process."""
    return subprocess.run(
        ["python3", str(HELPER), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def parse_output(result: subprocess.CompletedProcess[str]) -> dict[str, str]:
    """Parse the JSON line from stdout (first non-blank line)."""
    for line in result.stdout.splitlines():
        if line.strip().startswith("{"):
            return json.loads(line)
    raise AssertionError(
        f"No JSON line in stdout. stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_typical_weekday():
    """11:00 UTC on 2026-05-15 (Fri) is 7:00 AM ET (EDT)."""
    result = run_helper("--now-utc", "2026-05-15T11:00:00Z")
    assert result.returncode == 0, result.stderr
    output = parse_output(result)
    assert output["day"] == "Fri"
    assert output["date"] == "2026-05-15"
    assert output["et_offset"] == "-04:00"
    assert output["iso_eod_et"] == "2026-05-15T23:59:59-04:00"
    # SUMMARY line present
    assert "SUMMARY: day=Fri" in result.stdout


def test_after_8pm_et_date_does_not_roll_over():
    """01:00 UTC on 2026-05-16 is 21:00 ET on 2026-05-15 — date must NOT roll forward.

    This is the issue #112 class — before this helper existed, the agent could
    misread `date +%F` without TZ as the UTC date, sending tomorrow's check-in
    21 hours early.
    """
    result = run_helper("--now-utc", "2026-05-16T01:00:00Z")
    assert result.returncode == 0, result.stderr
    output = parse_output(result)
    assert output["date"] == "2026-05-15"
    assert output["day"] == "Fri"


def test_dst_transition_uses_post_dst_offset():
    """March 8 2026 03:00 ET is the spring-forward boundary — confirm post-DST `-04:00`.

    At 07:00 UTC on 2026-03-08, ET has already moved to 03:00 EDT (post-spring-forward).
    """
    result = run_helper("--now-utc", "2026-03-08T07:00:00Z")
    assert result.returncode == 0, result.stderr
    output = parse_output(result)
    assert output["et_offset"] == "-04:00"


def test_est_transition_uses_post_est_offset():
    """November 1 2026 02:00 ET is the fall-back boundary — confirm post-EST `-05:00`.

    At 07:00 UTC on 2026-11-01, ET has moved to 02:00 EST.
    Note: the exact wall-clock moment of fallback is ambiguous; 07:00 UTC is well past it.
    """
    result = run_helper("--now-utc", "2026-11-01T08:00:00Z")
    assert result.returncode == 0, result.stderr
    output = parse_output(result)
    assert output["et_offset"] == "-05:00"


def test_iso_eod_never_has_z_suffix():
    """ANY input must produce an iso_eod_et that does NOT end with 'Z'.

    This is the #112 regression-prevention guarantee — a UTC Z suffix on the
    due_date causes habits to appear overdue immediately.
    """
    # Sample several distinct moments across DST/EST and time-of-day combos.
    samples = [
        "2026-01-15T12:00:00Z",
        "2026-05-15T11:00:00Z",
        "2026-05-15T23:30:00Z",
        "2026-07-04T16:00:00Z",
        "2026-11-15T18:00:00Z",
    ]
    for now_utc in samples:
        result = run_helper("--now-utc", now_utc)
        assert result.returncode == 0, f"helper failed for {now_utc}: {result.stderr}"
        output = parse_output(result)
        assert not output["iso_eod_et"].endswith("Z"), (
            f"REGRESSION: iso_eod_et ended with 'Z' for now_utc={now_utc!r} — "
            f"this would re-introduce issue #112. Got: {output['iso_eod_et']!r}"
        )
        # And it must contain an explicit ET offset
        assert output["iso_eod_et"].endswith(("-04:00", "-05:00")), (
            f"iso_eod_et must end with -04:00 or -05:00; got {output['iso_eod_et']!r}"
        )


def test_malformed_now_utc_exits_2():
    """Bad --now-utc value produces exit code 2 (usage error)."""
    result = run_helper("--now-utc", "not-a-date")
    assert result.returncode == 2, (
        f"expected exit 2 for malformed --now-utc; "
        f"got returncode={result.returncode} stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "ERROR" in result.stderr
