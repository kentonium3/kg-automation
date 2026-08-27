"""Tests for audit.sh's completion pointer (#891).

The canary's freshness anchor for ``security-monitor`` is a pointer the audit
writes itself. Before #891 the probe was ``ls -t .../baselines/*.json | head -1``,
which could not fail (the baselines are ``.txt``, and the pipeline returned
``head``'s exit status regardless). Keying on baseline mtime instead would have
been wrong the other way — ``check_baseline`` only rewrites a baseline when one
is MISSING, so the baselines sat at one date while the audit completed cleanly
every day.

Same two layers as ``test_audit_emit.py``: static assertions on the script text,
plus behavioral assertions that run only the extracted ``write_tick`` snippet
under bash, so nothing here probes live office2 state.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
AUDIT_SH = REPO_ROOT / "scripts" / "office2" / "security-monitor" / "audit.sh"


def _audit_text() -> str:
    return AUDIT_SH.read_text(encoding="utf-8")


class TestCompletionPointerStatic:
    def test_dead_baseline_glob_probe_is_gone(self):
        """The un-failable probe must not be reintroduced anywhere."""
        assert "baselines/*.json" not in _audit_text()

    def test_writes_pointer_on_both_exit_branches(self):
        text = _audit_text()
        # Two explicit success writes: the drift branch and the all-clear branch.
        assert text.count('write_tick "success"') == 2, (
            "both exit branches must record completion — a pointer written only "
            "on the happy path cannot distinguish 'clean' from 'never ran'"
        )

    def test_abnormal_exit_is_covered_by_a_trap(self):
        text = _audit_text()
        assert "trap on_exit EXIT" in text
        assert 'write_tick "failure"' in text, (
            "a crash before the summary block must record failure, else the "
            "canary stays quiet until max_age expires"
        )

    def test_pointer_write_is_atomic(self):
        text = _audit_text()
        assert "mktemp" in text and 'mv -f "$tmp" "$TICK_FILE"' in text, (
            "the canary may read this file mid-write; it must be renamed into "
            "place, not written in situ"
        )


def _extract_write_tick(tmp_path: Path, trailer: str) -> Path:
    """Build a runnable script from audit.sh's own write_tick block."""
    text = _audit_text()
    match = re.search(r"^TICK_WRITTEN=0\n.*?^trap on_exit EXIT$", text, re.M | re.S)
    assert match, "write_tick/trap block not found in audit.sh"
    script = tmp_path / "snippet.sh"
    script.write_text(
        f'BASE_DIR="{tmp_path}/base"\n'
        'STATE_DIR="$BASE_DIR/state"\n'
        'TICK_FILE="$STATE_DIR/last-tick.json"\n'
        f"{match.group(0)}\n{trailer}\n",
        encoding="utf-8",
    )
    return script


def _run(script: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(script)], capture_output=True, text=True, timeout=30
    )


def _pointer(tmp_path: Path) -> dict:
    return json.loads((tmp_path / "base" / "state" / "last-tick.json").read_text())


class TestCompletionPointerBehavior:
    def test_all_clear_branch_records_success(self, tmp_path):
        _run(_extract_write_tick(tmp_path, 'write_tick "success" 0 0'))
        p = _pointer(tmp_path)
        assert p["exit_status"] == "success"
        assert p["alert_count"] == 0

    def test_drift_branch_records_success_not_failure(self, tmp_path):
        """Drift is not a runner fault.

        audit.sh already pushes its own alert-bus notification for drift. If the
        pointer said ``failure`` the canary would page for the same event, and
        would also page on a #862 expected-in-flight rebaseline (which withholds
        its own push but still exits 1).
        """
        _run(_extract_write_tick(tmp_path, 'write_tick "success" 3 2'))
        p = _pointer(tmp_path)
        assert p["exit_status"] == "success"
        assert (p["alert_count"], p["pushed_count"]) == (3, 2)

    def test_abnormal_exit_records_failure(self, tmp_path):
        result = _run(_extract_write_tick(tmp_path, 'exit 9'))
        assert result.returncode == 9
        assert _pointer(tmp_path)["exit_status"] == "failure"

    def test_normal_exit_does_not_get_overwritten_by_the_trap(self, tmp_path):
        """The trap must not clobber a completed run's verdict."""
        _run(_extract_write_tick(tmp_path, 'write_tick "success" 1 1; exit 1'))
        assert _pointer(tmp_path)["exit_status"] == "success"

    def test_non_numeric_counts_do_not_corrupt_the_json(self, tmp_path):
        """ALERT_COUNT can be the literal '?' when grep -c fails."""
        _run(_extract_write_tick(tmp_path, 'write_tick "success" "?" ""'))
        p = _pointer(tmp_path)
        assert p["alert_count"] == 0 and p["pushed_count"] == 0

    def test_no_temp_files_left_behind(self, tmp_path):
        _run(_extract_write_tick(tmp_path, 'write_tick "success" 0 0'))
        leftovers = list((tmp_path / "base" / "state").glob(".last-tick.*"))
        assert leftovers == [], f"atomic write leaked temp files: {leftovers}"


class TestPointerIsReadableByTheProbe:
    """The pointer must speak the canary's vocabulary — not just be valid JSON."""

    def test_drift_record_does_not_flip_health(self, tmp_path):
        from scripts.canary.probes import _explicit_error

        _run(_extract_write_tick(tmp_path, 'write_tick "success" 3 2'))
        assert _explicit_error(_pointer(tmp_path)) is None, (
            "alert_count/pushed_count must stay outside the explicit-error "
            "vocabulary, or drift double-pages"
        )

    def test_crash_record_does_flip_health(self, tmp_path):
        from scripts.canary.probes import _explicit_error

        _run(_extract_write_tick(tmp_path, 'exit 9'))
        assert _explicit_error(_pointer(tmp_path)) is not None

    def test_timestamp_key_is_one_the_probe_resolves(self, tmp_path):
        from scripts.canary.probes import _resolve_timestamp

        _run(_extract_write_tick(tmp_path, 'write_tick "success" 0 0'))
        resolved = _resolve_timestamp(_pointer(tmp_path))
        assert resolved is not None, "probe cannot find a timestamp in the pointer"
        key, ts = resolved
        assert key == "completed_at_utc"
        assert ts.tzinfo is not None, "naive timestamp would raise in the probe"
