"""Coverage checks: the canary dead-man's switch and the backup check (#1063).

Every case goes through the real service inventory and the canary's real
evaluator, and the pointer documents are real captures or are derived from
them (see ``fixtures/README.md``).
"""
from __future__ import annotations

import copy
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.office2.felix_health_check import coverage

FIXTURES = Path(__file__).resolve().parent / "fixtures"
REAL_TICK = json.loads((FIXTURES / "last-tick.2026-10-14.json").read_text(encoding="utf-8"))
REAL_BACKUP = json.loads((FIXTURES / "last-backup.2026-10-14.json").read_text(encoding="utf-8"))

TICK_PATH = "/data/services/felix-canary/state/last-tick.json"
BACKUP_PATH = "/data/services/backup/state/last-backup.json"

# Five minutes after the real tick: the canary is fresh.
NOW = datetime(2026, 10, 14, 18, 49, 16, tzinfo=timezone.utc)


def healthy_backup() -> dict:
    """The real pointer as it would read had the 2026-10-11 Sunday integrity
    check run (the outage skipped it; see fixtures/README.md)."""
    doc = copy.deepcopy(REAL_BACKUP)
    doc["last_integrity_check_utc"] = "2026-10-11T04:00:11Z"
    return doc


def incident_backup() -> dict:
    """The pointer backup.sh's EXIT trap writes when /mnt/backups is not
    mounted (scripts/office2/restic-backup.sh): both exit codes keep their
    127 "never attempted" sentinel, and every repo-derived value is null."""
    return {
        "schema_version": 2,
        "snapshot_timestamp_utc": None,
        "snapshot_id": None,
        "restic_exit_code": 127,
        "prune_exit_code": 127,
        "script_finished_at_utc": "2026-09-28T04:00:02Z",
        "repo_size_bytes": None,
        "snapshot_count": None,
        "integrity_check_run": False,
        "integrity_check_passed": None,
        "last_integrity_check_utc": "2026-09-20T04:00:11Z",
        "files_processed": None,
        "source_roots_present": None,
        "repo_fs_free_bytes": None,
    }


def dead_tick() -> dict:
    doc = copy.deepcopy(REAL_TICK)
    doc["completed_at_utc"] = "2026-09-27T15:52:00+00:00"
    return doc


INCIDENT_NOW = datetime(2026, 9, 28, 11, 0, 3, tzinfo=timezone.utc)


def reader(tick=None, backup=None):
    docs = {TICK_PATH: REAL_TICK if tick is None else tick,
            BACKUP_PATH: healthy_backup() if backup is None else backup}

    def read(path: str):
        if path not in docs:
            raise FileNotFoundError(path)
        value = docs[path]
        if isinstance(value, Exception):
            raise value
        return value

    return read


def by_component(findings):
    assert [f.component for f in findings] == list(coverage.COVERAGE_COMPONENTS)
    return {f.component: f for f in findings}


def no_uptime():
    return None


# --- T006: findings and mapping ---------------------------------------------

def test_healthy_system_yields_two_ok_findings():
    found = by_component(coverage.evaluate_coverage(NOW, read_state=reader(), uptime_seconds=no_uptime))
    assert found["felix-canary"].finding == "ok", found["felix-canary"].evidence
    assert found["restic-backup"].finding == "ok", found["restic-backup"].evidence


def test_incident_replay_reports_both_failures():
    """SC-001's coverage half: 2026-09-28 11:00, canary dead since 09-27,
    backup drive not mounted. Pre-mission, this run said ALL_HEALTHY."""
    found = by_component(coverage.evaluate_coverage(
        INCIDENT_NOW, read_state=reader(tick=dead_tick(), backup=incident_backup()),
        uptime_seconds=no_uptime))
    assert (found["felix-canary"].outcome, found["felix-canary"].finding) == ("stale", "failure")
    assert (found["restic-backup"].outcome, found["restic-backup"].finding) == ("failed", "failure")
    assert "restic_exit_code=127" in found["restic-backup"].evidence


def test_real_2026_10_14_backup_pointer_is_a_failure():
    """The verbatim pointer is unhealthy today: integrity check skipped twice."""
    found = by_component(coverage.evaluate_coverage(
        NOW, read_state=reader(backup=REAL_BACKUP), uptime_seconds=no_uptime))
    assert found["restic-backup"].finding == "failure"
    assert "last_integrity_check_utc" in found["restic-backup"].evidence


@pytest.mark.parametrize("outcome, expected", [
    ("healthy", "ok"), ("stale", "failure"), ("failed", "failure"), ("degraded", "failure"),
    ("unknown", "unknown"), ("brand-new-outcome", "unknown"),
])
def test_outcome_mapping_is_an_allow_list(monkeypatch, outcome, expected):
    from scripts.canary import health

    real = health.evaluate

    def fake(target, now, **kw):
        return real(target, now, **kw).__class__(
            component_id=target.component_id, outcome=outcome, alert_eligible=True,
            should_emit=False, severity=None, evidence="stubbed", evaluated_at=now.isoformat())

    monkeypatch.setattr(health, "evaluate", fake)
    findings = coverage.evaluate_coverage(NOW, read_state=reader(), uptime_seconds=no_uptime)
    assert {f.finding for f in findings} == {expected}


def test_suppressed_declaration_withholds_coverage(tmp_path):
    inv = json.loads(coverage.INVENTORY_PATH.read_text(encoding="utf-8"))
    for svc in inv["services"]:
        if svc.get("name") == "restic-backup":
            svc["status"] = "suspended"
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps(inv), encoding="utf-8")
    found = by_component(coverage.evaluate_coverage(
        NOW, inventory_path=path, read_state=reader(), uptime_seconds=no_uptime))
    assert found["restic-backup"].finding == "unknown"
    assert found["restic-backup"].outcome == "suppressed"
    assert "coverage withheld" in found["restic-backup"].evidence
    assert found["felix-canary"].finding == "ok"


def test_to_record_shape():
    finding = coverage.evaluate_coverage(NOW, read_state=reader(), uptime_seconds=no_uptime)[0]
    assert set(finding.to_record()) == {"component", "outcome", "finding", "evidence"}


# --- T007: declaration preconditions ---------------------------------------

def _real_health_check(name: str) -> dict:
    inv = json.loads(coverage.INVENTORY_PATH.read_text(encoding="utf-8"))
    return copy.deepcopy(next(s for s in inv["services"] if s.get("name") == name)["health_check"])


def test_real_inventory_satisfies_preconditions():
    """CI pin (FR-012, paula-4): an inventory edit that drops a coverage
    target, suspends it, or strips its freshness bound fails here."""
    inv = json.loads(coverage.INVENTORY_PATH.read_text(encoding="utf-8"))
    services = {s.get("name"): s for s in inv["services"]}
    for name in coverage.COVERAGE_COMPONENTS:
        assert name in services, f"{name} missing from the inventory"
        assert services[name].get("status") in {"active", "running"}, f"{name} is not alert-eligible"
        assert coverage.declaration_problems(services[name]["health_check"]) == [], name


def test_inventory_prose_names_both_coverage_targets():
    """FR-010 docs cross-check (analysis C1)."""
    purpose = next(s for s in json.loads(coverage.INVENTORY_PATH.read_text(encoding="utf-8"))["services"]
                   if s.get("name") == "felix-health-check")["purpose"]
    for name in coverage.COVERAGE_COMPONENTS:
        assert name in purpose


@pytest.mark.parametrize("mutate, fragment", [
    (lambda hc: hc.pop("max_age_seconds"), "max_age_seconds"),
    (lambda hc: hc.update(max_age_seconds=True), "max_age_seconds"),
    (lambda hc: hc.update(max_age_seconds=0), "max_age_seconds"),
    (lambda hc: hc.update(max_age_seconds=float("inf")), "max_age_seconds"),
    (lambda hc: hc.update(max_age_seconds="2100"), "max_age_seconds"),
    (lambda hc: hc.pop("key_ledger"), "key_ledger"),
    (lambda hc: hc["key_ledger"]["adjudicated"]["completed_at_utc"].pop("anchor"), "anchor"),
    (lambda hc: hc["key_ledger"]["adjudicated"]["completed_at_utc"].update(max_age_seconds=-1),
     "completed_at_utc.max_age_seconds"),
])
def test_declaration_problems_detects_each_shape_fault(mutate, fragment):
    hc = _real_health_check("felix-canary")
    assert coverage.declaration_problems(hc) == []  # same-fixture positive control
    mutate(hc)
    problems = coverage.declaration_problems(hc)
    assert problems and any(fragment in p for p in problems), problems


def test_missing_bound_at_runtime_is_unknown_not_liveness_only(tmp_path):
    """Codex post-plan finding 4: without a bound the canary's freshness path
    degrades to liveness-only, which would read a 17-day-old tick healthy."""
    inv = json.loads(coverage.INVENTORY_PATH.read_text(encoding="utf-8"))
    for svc in inv["services"]:
        if svc.get("name") == "felix-canary":
            svc["health_check"].pop("max_age_seconds")
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps(inv), encoding="utf-8")
    found = by_component(coverage.evaluate_coverage(
        INCIDENT_NOW, inventory_path=path, read_state=reader(tick=dead_tick()), uptime_seconds=no_uptime))
    assert found["felix-canary"].finding == "unknown"
    assert "declaration invalid" in found["felix-canary"].evidence


# --- T008: fail closed --------------------------------------------------------

def _assert_all_unknown(findings, fragment):
    assert [f.component for f in findings] == list(coverage.COVERAGE_COMPONENTS)
    for f in findings:
        assert f.finding == "unknown", f
        assert fragment in f.evidence, f.evidence


def test_inventory_missing(tmp_path):
    _assert_all_unknown(coverage.evaluate_coverage(
        NOW, inventory_path=tmp_path / "nope.json", read_state=reader()), "FileNotFoundError")


def test_inventory_not_json(tmp_path):
    path = tmp_path / "inv.json"
    path.write_text("{not json", encoding="utf-8")
    _assert_all_unknown(coverage.evaluate_coverage(NOW, inventory_path=path, read_state=reader()),
                        "JSONDecodeError")


def test_inventory_without_services(tmp_path):
    path = tmp_path / "inv.json"
    path.write_text("{}", encoding="utf-8")
    _assert_all_unknown(coverage.evaluate_coverage(NOW, inventory_path=path, read_state=reader()),
                        "not declared")


def test_one_target_absent(tmp_path):
    inv = json.loads(coverage.INVENTORY_PATH.read_text(encoding="utf-8"))
    inv["services"] = [s for s in inv["services"] if s.get("name") != "felix-canary"]
    path = tmp_path / "inv.json"
    path.write_text(json.dumps(inv), encoding="utf-8")
    found = by_component(coverage.evaluate_coverage(NOW, inventory_path=path, read_state=reader()))
    assert found["felix-canary"].finding == "unknown"
    assert found["restic-backup"].finding == "ok"


def test_pointer_file_missing_is_unknown():
    def read(path):
        raise FileNotFoundError(path)
    findings = coverage.evaluate_coverage(NOW, read_state=read, uptime_seconds=no_uptime)
    assert {f.finding for f in findings} == {"unknown"}


def test_repointed_to_a_network_probe_fails_closed(tmp_path):
    inv = json.loads(coverage.INVENTORY_PATH.read_text(encoding="utf-8"))
    for svc in inv["services"]:
        if svc.get("name") == "restic-backup":
            hc = svc["health_check"]
            hc["method"] = "http"
            hc["endpoint"] = "http://example.invalid"
    path = tmp_path / "inv.json"
    path.write_text(json.dumps(inv), encoding="utf-8")
    found = by_component(coverage.evaluate_coverage(NOW, inventory_path=path, read_state=reader()))
    assert found["restic-backup"].finding == "unknown"
    assert "file-read only" in found["restic-backup"].evidence


def test_canary_code_unimportable(monkeypatch):
    monkeypatch.setitem(sys.modules, "scripts.canary.health", None)
    _assert_all_unknown(coverage.evaluate_coverage(NOW, read_state=reader()), "scripts.canary.health")


# --- T010: post-boot note; working directory; duration ----------------------

def test_post_boot_note_when_host_just_started():
    found = by_component(coverage.evaluate_coverage(
        INCIDENT_NOW, read_state=reader(tick=dead_tick()), uptime_seconds=lambda: 600.0))
    assert found["felix-canary"].finding == "failure"
    assert "may be a post-boot catch-up" in found["felix-canary"].evidence


def test_no_post_boot_note_on_a_long_running_host():
    found = by_component(coverage.evaluate_coverage(
        INCIDENT_NOW, read_state=reader(tick=dead_tick()), uptime_seconds=lambda: 86400.0))
    assert found["felix-canary"].finding == "failure"
    assert "post-boot" not in found["felix-canary"].evidence


def test_independent_of_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    found = by_component(coverage.evaluate_coverage(NOW, read_state=reader(), uptime_seconds=no_uptime))
    assert {f.finding for f in found.values()} == {"ok"}


def test_well_inside_the_run_time_budget():
    """NFR-002 (<= 5 s added per run); local file reads only."""
    start = time.monotonic()
    coverage.evaluate_coverage(NOW, read_state=reader(), uptime_seconds=no_uptime)
    assert time.monotonic() - start < 5.0


def test_evaluate_coverage_never_raises_on_a_hostile_reader():
    def read(path):
        raise MemoryError("hostile")
    findings = coverage.evaluate_coverage(NOW, read_state=read, uptime_seconds=no_uptime)
    assert len(findings) == 2


def test_dead_tick_fixture_is_stale_at_the_replay_instant():
    """Guard the replay's premise (debbie's 2026-09-28 11:00 replay)."""
    age = INCIDENT_NOW - datetime.fromisoformat(dead_tick()["completed_at_utc"])
    assert age > timedelta(hours=19)


# --- review-cycle 1 additions (mutation survivors M2, M4, M5, M10) ----------

def test_uptime_probe_raising_keeps_the_failure_and_adds_no_note():
    def boom():
        raise OSError("no /proc")
    found = by_component(coverage.evaluate_coverage(
        INCIDENT_NOW, read_state=reader(tick=dead_tick()), uptime_seconds=boom))
    assert found["felix-canary"].finding == "failure"
    assert "post-boot" not in found["felix-canary"].evidence


def test_post_boot_note_is_only_for_the_canary():
    stale_backup = healthy_backup()
    found = by_component(coverage.evaluate_coverage(
        NOW + timedelta(hours=40), read_state=reader(tick=REAL_TICK, backup=stale_backup),
        uptime_seconds=lambda: 60.0))
    assert found["restic-backup"].outcome == "stale"
    assert "post-boot" not in found["restic-backup"].evidence


@pytest.mark.parametrize("mutate, fragment", [
    (lambda hc: hc["key_ledger"]["adjudicated"].update(completed_at_utc="freshness"), "anchor"),
    (lambda hc: hc["key_ledger"]["adjudicated"]["status"].update(freshness=True, anchor=True),
     "exactly one freshness anchor"),
])
def test_declaration_problems_on_malformed_predicates(mutate, fragment):
    hc = _real_health_check("felix-canary")
    mutate(hc)
    problems = coverage.declaration_problems(hc)
    assert problems and any(fragment in p for p in problems), problems


def test_evaluator_raising_is_unknown_per_component(monkeypatch):
    from scripts.canary import health

    def boom(*_a, **_k):
        raise RuntimeError("evaluator bug")

    monkeypatch.setattr(health, "evaluate", boom)
    findings = coverage.evaluate_coverage(NOW, read_state=reader(), uptime_seconds=no_uptime)
    assert [f.finding for f in findings] == ["unknown", "unknown"]
    assert all("evaluator bug" in f.evidence for f in findings)
