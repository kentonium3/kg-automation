"""felix-health-check's restic-backup coverage line names the failure cause (#1067).

The health check judges restic-backup through the canary's own evaluator
(#1063), so the cause the canary probe appends must reach the coverage
finding and its rendered alert detail with no health-check code of its own.
Exercised against the REAL inventory declaration via ``evaluate_coverage``;
only the pointer read is injected.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from scripts.office2.felix_health_check.coverage import evaluate_coverage
from scripts.office2.felix_health_check.run import alert_details

NOW = datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc)
RESTIC_STATE = "/data/services/backup/state/last-backup.json"
CAUSE = "; cause: backup drive /mnt/backups is not mounted"


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _not_mounted(with_cause: bool) -> dict:
    p = {
        "schema_version": 2,
        "snapshot_timestamp_utc": None,
        "snapshot_id": None,
        "restic_exit_code": 127,
        "prune_exit_code": 127,
        "script_finished_at_utc": _iso(NOW - timedelta(hours=8)),
        "repo_size_bytes": 1024,
        "snapshot_count": None,
        "integrity_check_run": False,
        "integrity_check_passed": None,
        "last_integrity_check_utc": _iso(NOW - timedelta(days=3)),
        "files_processed": None,
        "source_roots_present": None,
        "repo_fs_free_bytes": None,
    }
    if with_cause:
        p["failure_reason"] = "backup_mount_missing"
    return p


def _restic_finding(pointer: dict):
    def read_state(path: str):
        if path == RESTIC_STATE:
            return json.loads(json.dumps(pointer))
        raise FileNotFoundError(path)

    findings = evaluate_coverage(NOW, read_state=read_state, uptime_seconds=lambda: None)
    (finding,) = [f for f in findings if f.component == "restic-backup"]
    return finding


def test_coverage_finding_and_rendered_detail_carry_the_cause():
    finding = _restic_finding(_not_mounted(with_cause=True))
    assert finding.finding == "failure"
    assert finding.evidence.endswith(CAUSE)
    detail = alert_details("FAILURES_DETECTED", "", [finding])["coverage:restic-backup"]
    assert CAUSE in detail
    assert len(detail) <= 500, "must survive the bus's 500-character detail truncation"


def test_same_pointer_without_cause_renders_exactly_as_before():
    with_cause = _restic_finding(_not_mounted(with_cause=True))
    without = _restic_finding(_not_mounted(with_cause=False))
    assert (with_cause.finding, with_cause.outcome) == (without.finding, without.outcome)
    assert CAUSE not in without.evidence
    assert with_cause.evidence == without.evidence + CAUSE
