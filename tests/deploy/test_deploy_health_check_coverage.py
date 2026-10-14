"""Tests for the #1063 deploy entrypoint. Nothing here touches systemd or
the filesystem outside tmp: the runner, clock, reader and mover are injected."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[2]
_PATH = _ROOT / "scripts" / "deploy" / "deploy-health-check-coverage.py"
_spec = importlib.util.spec_from_file_location("deploy_health_check_coverage", _PATH)
mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = mod
_spec.loader.exec_module(mod)

T0 = datetime(2026, 10, 14, 20, 0, 0, tzinfo=timezone.utc)
_MANIFEST_QUEUED = _ROOT / "deploys" / "queued" / "health-check-coverage.yaml"


def _resolve_manifest_path() -> Path:
    """felix-deployer moves the manifest from ``deploys/queued/`` to
    ``deploys/applied/<NNNN>-health-check-coverage.yaml`` once applied, so it
    lives in exactly one of the two (same pattern as test_deploy_felix_canary)."""
    if _MANIFEST_QUEUED.exists():
        return _MANIFEST_QUEUED
    applied = sorted((_ROOT / "deploys" / "applied").glob("*-health-check-coverage.yaml"))
    return applied[-1] if applied else _MANIFEST_QUEUED


def _record(**overrides) -> dict:
    rec = {
        "status": "ALL_HEALTHY",
        "ran_at_utc": "2026-10-14T20:00:01Z",
        "exit_code": 0,
        "delivery": {"attempted": False, "sent": False, "detail": "no alert (healthy)"},
        "script_status": "ALL_HEALTHY",
        "script_path": str(mod.REPO_SCRIPT),
        "coverage_checks": [
            {"component": "felix-canary", "outcome": "healthy", "finding": "ok", "evidence": "fresh"},
            {"component": "restic-backup", "outcome": "healthy", "finding": "ok", "evidence": "fresh"},
        ],
    }
    rec.update(overrides)
    return rec


SENT = {"attempted": True, "sent": True, "detail": "delivered"}
NOT_SENT = {"attempted": True, "sent": False, "detail": "ntfy POST failed"}
BACKUP_FAILED = [
    {"component": "felix-canary", "outcome": "healthy", "finding": "ok", "evidence": "fresh"},
    {"component": "restic-backup", "outcome": "failed", "finding": "failure",
     "evidence": "last_integrity_check_utc=2026-09-27T04:00:11+00:00, age 1525364s exceeds max_age 777600s"},
]


class Harness:
    def __init__(self, record: dict | None, *, start_rc: int = 0, legacy_exists: bool = True):
        self.record = record
        self.start_rc = start_rc
        self.legacy_exists = legacy_exists
        self.runs: list[list[str]] = []
        self.moves: list[tuple[str, str]] = []
        self.mkdirs: list[Path] = []

    def run(self, argv):
        self.runs.append(argv)
        return self.start_rc, "", "boom" if self.start_rc else ""

    def read_text(self, _path):
        if self.record is None:
            raise FileNotFoundError("no record")
        return json.dumps(self.record)

    def move(self, src, dst):
        self.moves.append((src, dst))

    def apply(self, monkeypatch):
        monkeypatch.setattr(mod, "_preflight", lambda check_user: True)
        return mod._apply(run=self.run, now=lambda: T0, read_text=self.read_text, move=self.move,
                          exists=lambda p: self.legacy_exists and p == mod.LEGACY_SCRIPT, mkdir=self.mkdirs.append,
                          check_user=False)


def test_happy_path_retires_once(monkeypatch):
    h = Harness(_record())
    assert h.apply(monkeypatch) == 0
    assert h.runs == [["systemctl", "--user", "start", "felix-health-check.service"]]
    assert len(h.moves) == 1
    src, dst = h.moves[0]
    assert src == str(mod.LEGACY_SCRIPT)
    assert dst == str(mod.RETIRED_DIR / "health-check.sh.20261014T200000Z")


def test_genuine_fault_with_delivered_alert_is_a_successful_deploy(monkeypatch):
    h = Harness(_record(status="FAILURES_DETECTED", delivery=SENT, coverage_checks=BACKUP_FAILED))
    assert h.apply(monkeypatch) == 0
    assert len(h.moves) == 1


@pytest.mark.parametrize("case, overrides", [
    ("alert needed but not delivered", dict(status="FAILURES_DETECTED", delivery=NOT_SENT,
                                            coverage_checks=BACKUP_FAILED)),
    ("stale record from an earlier run", dict(ran_at_utc="2026-10-14T11:00:02Z")),
    ("still running the host copy", dict(script_path="/home/claude/helper-scripts/health-check.sh")),
    ("shell verdict unrecognised behind a coverage failure",
     dict(status="FAILURES_DETECTED", delivery=SENT, script_status="UNKNOWN", coverage_checks=BACKUP_FAILED)),
    ("shell did not run", dict(exit_code=None)),
    ("coverage entry missing", dict(coverage_checks=[_record()["coverage_checks"][0]])),
    ("coverage unknown", dict(coverage_checks=[
        _record()["coverage_checks"][0],
        {"component": "restic-backup", "outcome": "unavailable", "finding": "unknown", "evidence": "x"}])),
    ("coverage suppressed", dict(coverage_checks=[
        _record()["coverage_checks"][0],
        {"component": "restic-backup", "outcome": "suppressed", "finding": "unknown", "evidence": "x"}])),
    ("status UNKNOWN", dict(status="UNKNOWN", delivery=SENT)),
    ("record from before this mission", {"coverage_checks": None, "script_status": None, "script_path": None}),
    ("delivery missing on a healthy record", dict(delivery=None)),
])
def test_incomplete_proof_fails_and_never_retires(monkeypatch, case, overrides):
    h = Harness(_record(**overrides))
    assert h.apply(monkeypatch) == 1, case
    assert h.moves == [], case


def test_retire_oserror_is_a_structured_failure(monkeypatch, capsys):
    h = Harness(_record())

    def denied(src, dst):
        raise PermissionError("denied")

    h.move = denied
    assert h.apply(monkeypatch) == 1
    assert '"step": "retire"' in capsys.readouterr().out


def test_retire_never_overwrites_an_existing_target(monkeypatch):
    h = Harness(_record())
    monkeypatch.setattr(mod, "_preflight", lambda check_user: True)
    rc = mod._apply(run=h.run, now=lambda: T0, read_text=h.read_text, move=h.move,
                    exists=lambda _p: True, mkdir=h.mkdirs.append, check_user=False)
    assert rc == 1
    assert h.moves == []


def test_naive_timestamp_is_read_as_utc():
    assert mod.record_problems(_record(ran_at_utc="2026-10-14T20:00:01"), T0) == []


def test_start_failure_fails_and_never_retires(monkeypatch):
    h = Harness(_record(), start_rc=1)
    assert h.apply(monkeypatch) == 1
    assert h.moves == []


def test_missing_record_fails_and_never_retires(monkeypatch):
    h = Harness(None)
    assert h.apply(monkeypatch) == 1
    assert h.moves == []


def test_reapply_after_retirement_is_idempotent(monkeypatch):
    h = Harness(_record(), legacy_exists=False)
    assert h.apply(monkeypatch) == 0
    assert h.moves == []


def test_wrong_user_runs_nothing(monkeypatch):
    monkeypatch.setattr(mod.pwd, "getpwuid", lambda _uid: type("P", (), {"pw_name": "kgale"})())
    h = Harness(_record())
    rc = mod._apply(run=h.run, now=lambda: T0, read_text=h.read_text, move=h.move,
                    exists=lambda _p: True, mkdir=h.mkdirs.append, check_user=True)
    assert rc == 1
    assert h.runs == [] and h.moves == []


def test_record_problems_accepts_the_happy_record():
    assert mod.record_problems(_record(), T0) == []


def test_record_problems_reports_everything_at_once():
    problems = mod.record_problems(_record(script_path="x", exit_code=None, ran_at_utc="nope"), T0)
    assert len(problems) >= 3


# --- the manifest ------------------------------------------------------------

def test_manifest_shape():
    m = yaml.safe_load(_resolve_manifest_path().read_text(encoding="utf-8"))
    assert m["name"] == "health-check-coverage"
    assert m["issue"] == "kentonium3/kg-automation#1063"
    assert m["tier"] == 3
    assert m["audited_surface"] is True
    assert m["entrypoint"] == "scripts/deploy/deploy-health-check-coverage.py"
    assert (_ROOT / m["entrypoint"]).is_file()
    assert m["verification"]["pre"] == ["scripts/deploy/deploy-health-check-coverage.py --dry-run"]
    assert len(m["notes"]) <= 2000
    posts = " ".join(m["verification"]["post"])
    assert "helper-scripts/health-check.sh" in posts
    assert "coverage_checks" in posts


def test_entrypoint_is_executable_in_git():
    import subprocess
    out = subprocess.run(["git", "ls-files", "-s", str(_PATH.relative_to(_ROOT))], cwd=_ROOT,
                         capture_output=True, text=True, check=True).stdout
    assert out.startswith("100755"), out
