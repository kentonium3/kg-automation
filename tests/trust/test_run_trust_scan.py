"""Tests for scripts.trust.run_trust_scan (WP04, #683, contract C2).

Drives drift + assertion findings through the runner, asserting the right
emits happen, `--dry-run` mutates nothing, and the two-mode exit-code
contract (timer=0 always, preflight may exit 2, drift-found never
non-zero). Fail-safe isolation: a failure in one sub-scan is caught into
`errors[]` and the other sub-scan still runs.

Mocks the bus (`scripts.trust.alert_render.emit`), the cron enumeration
subprocess boundary, and the baseline loader — no office2/ntfy/Vikunja
calls.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from scripts.trust import run_trust_scan as rts
from scripts.trust import state as state_mod
from scripts.trust.assertion_verifier import AssertionFinding
from scripts.trust.cron_baseline import ApprovedCron, BaselineError, baseline_hash
from scripts.trust.cron_drift_detector import CronDriftFinding, CronEnumerationError
from scripts.trust.unit_drift_detector import (
    UnitCoverage,
    UnitDriftFinding,
    UnitEnumerationError,
)

T0 = datetime(2026, 7, 10, 12, 0, 0, tzinfo=timezone.utc)

BASELINE = [
    ApprovedCron(
        name="inbox-5pm",
        agent_id="felix-admin-capture",
        schedule_expr="0 17 * * *",
        tz="America/New_York",
        purpose="test",
        approved_by="kent",
        approved_at="2026-07-01",
    )
]


def _live_job(**overrides) -> dict:
    job = {
        "id": "abc-123",
        "name": "inbox-5pm",
        "enabled": True,
        "createdAtMs": 1775153265189,
        "agentId": "felix-admin-capture",
        "schedule": {"kind": "cron", "expr": "0 17 * * *", "tz": "America/New_York"},
    }
    job.update(overrides)
    return job


@pytest.fixture
def isolated_paths(tmp_path: Path):
    """Provide isolated state/watermark paths + an empty assertions dir."""
    state_path = tmp_path / "state" / "seen-findings.json"
    watermark_path = tmp_path / "state" / "assertion-watermark.json"
    assertions_dir = tmp_path / "assertions"
    assertions_dir.mkdir(parents=True, exist_ok=True)
    return state_path, watermark_path, assertions_dir


# --- unit-drift sub-scan (#817) ----------------------------------------------


def _mirror_repo_units_into(deployed: Path, repo_root: Path, *, drift_unit: str | None = None) -> None:
    """Copy each repo canonical unit into a fake deployed dir byte-identical,
    optionally appending a line to one unit so it drifts."""
    from scripts.trust.unit_drift_detector import build_repo_index

    deployed.mkdir(parents=True, exist_ok=True)
    for unit, path in build_repo_index(repo_root).items():
        text = path.read_text(encoding="utf-8")
        if unit == drift_unit:
            # A FUNCTIONAL directive change (not a comment — comments are
            # normalized out) so the drift is genuinely detected.
            text += "Environment=INJECTED_DRIFT=1\n"
        (deployed / unit).write_text(text, encoding="utf-8")


def test_unit_drift_clean_when_deployed_matches_repo(isolated_paths, tmp_path):
    state_path, watermark_path, assertions_dir = isolated_paths
    deployed = tmp_path / "deployed"
    _mirror_repo_units_into(deployed, rts.REPO_ROOT)

    with patch("scripts.trust.run_trust_scan.load_baseline", return_value=BASELINE), patch(
        "scripts.trust.run_trust_scan.enumerate_live_crons", return_value=[_live_job()]
    ), patch("scripts.trust.alert_render.emit") as mock_emit:
        from scripts.common.alert_bus.model import AlertResult

        mock_emit.return_value = AlertResult(ok=True)
        summary = rts.run_scan(
            now=T0,
            state_path=state_path,
            watermark_path=watermark_path,
            assertions_base_dir=assertions_dir,
            unit_deployed_dir=deployed,
        )

    assert summary["ok"] is True
    assert summary["unit_drift_findings"] == 0
    assert summary["unit_coverage"]["compared"] > 0


def test_unit_drift_detected_and_alerted(isolated_paths, tmp_path):
    state_path, watermark_path, assertions_dir = isolated_paths
    deployed = tmp_path / "deployed"
    _mirror_repo_units_into(deployed, rts.REPO_ROOT, drift_unit="felix-trust-scan.service")

    with patch("scripts.trust.run_trust_scan.load_baseline", return_value=BASELINE), patch(
        "scripts.trust.run_trust_scan.enumerate_live_crons", return_value=[_live_job()]
    ), patch("scripts.trust.alert_render.emit") as mock_emit:
        from scripts.common.alert_bus.model import Alert, AlertResult

        mock_emit.return_value = AlertResult(ok=True)
        summary = rts.run_scan(
            now=T0,
            state_path=state_path,
            watermark_path=watermark_path,
            assertions_base_dir=assertions_dir,
            unit_deployed_dir=deployed,
        )

    assert summary["ok"] is True
    assert summary["unit_drift_findings"] == 1
    # The unit-drift finding produced an emit tagged with the unit source.
    emitted_sources = [call.args[0].source for call in mock_emit.call_args_list if isinstance(call.args[0], Alert)]
    assert any(src == "felix-trust-scan/unit-drift" for src in emitted_sources)


def test_unit_drift_failed_emit_stays_due_next_tick(isolated_paths, tmp_path):
    """#817 H1 regression: a unit-drift alert whose #701 emit fails must remain
    DUE and re-fire on the next tick, not be suppressed for 24h. This only holds
    if the emit-retry keep_due fingerprint matches the reconcile fingerprint
    (both use hash "" for unit findings)."""
    from scripts.common.alert_bus.model import Alert, AlertResult

    state_path, watermark_path, assertions_dir = isolated_paths
    deployed = tmp_path / "deployed"
    _mirror_repo_units_into(deployed, rts.REPO_ROOT, drift_unit="felix-trust-scan.service")

    def emit_fail_unit(alert):
        if isinstance(alert, Alert) and alert.source == "felix-trust-scan/unit-drift":
            return AlertResult(ok=False, reason="bus down")
        return AlertResult(ok=True)

    # Tick 1: the unit-drift emit fails.
    with patch("scripts.trust.run_trust_scan.load_baseline", return_value=BASELINE), patch(
        "scripts.trust.run_trust_scan.enumerate_live_crons", return_value=[_live_job()]
    ), patch("scripts.trust.alert_render.emit", side_effect=emit_fail_unit):
        s1 = rts.run_scan(
            now=T0,
            state_path=state_path,
            watermark_path=watermark_path,
            assertions_base_dir=assertions_dir,
            unit_deployed_dir=deployed,
        )
    assert s1["unit_drift_findings"] == 1
    assert s1["alerts_emitted"] == 0  # the only finding's emit failed

    # Tick 2, one minute later (well within the 24h cadence): emit now succeeds.
    # With the H1 bug the finding would be suppressed; with the fix it re-fires.
    with patch("scripts.trust.run_trust_scan.load_baseline", return_value=BASELINE), patch(
        "scripts.trust.run_trust_scan.enumerate_live_crons", return_value=[_live_job()]
    ), patch("scripts.trust.alert_render.emit", return_value=AlertResult(ok=True)):
        s2 = rts.run_scan(
            now=T0 + timedelta(minutes=1),
            state_path=state_path,
            watermark_path=watermark_path,
            assertions_base_dir=assertions_dir,
            unit_deployed_dir=deployed,
        )
    assert s2["alerts_emitted"] == 1  # re-fired because it stayed due (H1 fixed)


def test_unit_scan_skipped_when_deployed_dir_absent(isolated_paths, tmp_path):
    state_path, watermark_path, assertions_dir = isolated_paths
    with patch("scripts.trust.run_trust_scan.load_baseline", return_value=BASELINE), patch(
        "scripts.trust.run_trust_scan.enumerate_live_crons", return_value=[_live_job()]
    ), patch("scripts.trust.alert_render.emit") as mock_emit:
        from scripts.common.alert_bus.model import AlertResult

        mock_emit.return_value = AlertResult(ok=True)
        summary = rts.run_scan(
            now=T0,
            state_path=state_path,
            watermark_path=watermark_path,
            assertions_base_dir=assertions_dir,
            unit_deployed_dir=tmp_path / "does-not-exist",
        )

    assert summary["ok"] is True
    assert summary["unit_drift_findings"] == 0
    assert "skipped" in summary["unit_coverage"]


# --- basic drift + assertion findings drive emits ----------------------------


def test_run_scan_drift_finding_drives_emit(isolated_paths):
    state_path, watermark_path, assertions_dir = isolated_paths

    unapproved_job = _live_job(name="mystery-cron", agentId="unknown-agent")
    with patch("scripts.trust.run_trust_scan.load_baseline", return_value=BASELINE), patch(
        "scripts.trust.run_trust_scan.enumerate_live_crons",
        return_value=[_live_job(), unapproved_job],
    ), patch("scripts.trust.alert_render.emit") as mock_emit:
        from scripts.common.alert_bus.model import AlertResult

        mock_emit.return_value = AlertResult(ok=True)

        summary = rts.run_scan(
            now=T0,
            state_path=state_path,
            watermark_path=watermark_path,
            assertions_base_dir=assertions_dir,
        )

    assert summary["ok"] is True
    assert summary["drift_findings"] == 1  # only the unapproved one is drift
    assert summary["alerts_emitted"] == 1
    mock_emit.assert_called_once()


def test_run_scan_assertion_finding_drives_emit(isolated_paths):
    state_path, watermark_path, assertions_dir = isolated_paths

    assertion_file = assertions_dir / "2026-07-10.jsonl"
    record = {
        "ts": "2026-07-10T11:00:00+00:00",
        "agent": "main",
        "request_summary": None,
        "request_ref": None,
        "artifact_kind": "other",
        "artifact_ids": ["x1"],
        "claim": "did a thing",
    }
    assertion_file.write_text(json.dumps(record) + "\n", encoding="utf-8")

    with patch("scripts.trust.run_trust_scan.load_baseline", return_value=BASELINE), patch(
        "scripts.trust.run_trust_scan.enumerate_live_crons", return_value=[_live_job()]
    ), patch("scripts.trust.alert_render.emit") as mock_emit:
        from scripts.common.alert_bus.model import AlertResult

        mock_emit.return_value = AlertResult(ok=True)

        summary = rts.run_scan(
            now=T0,
            state_path=state_path,
            watermark_path=watermark_path,
            assertions_base_dir=assertions_dir,
        )

    assert summary["ok"] is True
    assert summary["assertion_findings"] == 1  # "other" kind -> unverifiable_kind
    assert summary["alerts_emitted"] == 1


def test_run_scan_second_tick_does_not_reverify_same_assertion(isolated_paths):
    """Watermark ensures each assertion line is verified exactly once."""
    state_path, watermark_path, assertions_dir = isolated_paths
    assertion_file = assertions_dir / "2026-07-10.jsonl"
    record = {
        "ts": "2026-07-10T11:00:00+00:00",
        "agent": "main",
        "request_summary": None,
        "request_ref": None,
        "artifact_kind": "other",
        "artifact_ids": ["x1"],
        "claim": "did a thing",
    }
    assertion_file.write_text(json.dumps(record) + "\n", encoding="utf-8")

    with patch("scripts.trust.run_trust_scan.load_baseline", return_value=BASELINE), patch(
        "scripts.trust.run_trust_scan.enumerate_live_crons", return_value=[_live_job()]
    ), patch("scripts.trust.alert_render.emit") as mock_emit:
        from scripts.common.alert_bus.model import AlertResult

        mock_emit.return_value = AlertResult(ok=True)

        rts.run_scan(
            now=T0,
            state_path=state_path,
            watermark_path=watermark_path,
            assertions_base_dir=assertions_dir,
        )
        summary2 = rts.run_scan(
            now=T0,
            state_path=state_path,
            watermark_path=watermark_path,
            assertions_base_dir=assertions_dir,
        )

    # Second tick: no new assertion lines -> 0 assertion findings.
    assert summary2["assertion_findings"] == 0


# --- --dry-run: no emit, no state/watermark mutation -------------------------


def test_dry_run_emits_nothing_and_mutates_no_state(isolated_paths):
    state_path, watermark_path, assertions_dir = isolated_paths

    unapproved_job = _live_job(name="mystery-cron", agentId="unknown-agent")
    with patch("scripts.trust.run_trust_scan.load_baseline", return_value=BASELINE), patch(
        "scripts.trust.run_trust_scan.enumerate_live_crons",
        return_value=[_live_job(), unapproved_job],
    ), patch("scripts.trust.alert_render.emit") as mock_emit:
        summary = rts.run_scan(
            dry_run=True,
            now=T0,
            state_path=state_path,
            watermark_path=watermark_path,
            assertions_base_dir=assertions_dir,
        )

    mock_emit.assert_not_called()
    assert summary["drift_findings"] == 1
    assert summary["alerts_emitted"] == 0
    assert not state_path.exists()
    assert not watermark_path.exists()


# --- exit codes ---------------------------------------------------------------


def test_main_timer_mode_fault_exits_0(isolated_paths, tmp_path):
    state_path, watermark_path, assertions_dir = isolated_paths
    with patch(
        "scripts.trust.run_trust_scan.load_baseline",
        side_effect=Exception("baseline unreadable"),
    ), patch(
        "scripts.trust.run_trust_scan.enumerate_live_crons", return_value=[]
    ), patch(
        "scripts.trust.run_trust_scan.assertions_dir", return_value=assertions_dir
    ), patch(
        "scripts.trust.run_trust_scan.state_mod.DEFAULT_STATE_PATH", state_path
    ), patch(
        "scripts.trust.run_trust_scan.DEFAULT_WATERMARK_PATH", watermark_path
    ):
        exit_code = rts.main(["--json"])

    assert exit_code == 0


def test_main_preflight_mode_scan_inability_exits_2(isolated_paths):
    state_path, watermark_path, assertions_dir = isolated_paths
    with patch(
        "scripts.trust.run_trust_scan.load_baseline",
        side_effect=Exception("baseline unreadable"),
    ), patch(
        "scripts.trust.run_trust_scan.enumerate_live_crons", return_value=[]
    ), patch(
        "scripts.trust.run_trust_scan.assertions_dir", return_value=assertions_dir
    ), patch(
        "scripts.trust.run_trust_scan.state_mod.DEFAULT_STATE_PATH", state_path
    ), patch(
        "scripts.trust.run_trust_scan.DEFAULT_WATERMARK_PATH", watermark_path
    ):
        exit_code = rts.main(["--preflight", "--json"])

    assert exit_code == 2


def test_main_drift_found_never_nonzero_timer_mode(isolated_paths):
    state_path, watermark_path, assertions_dir = isolated_paths
    unapproved_job = _live_job(name="mystery-cron", agentId="unknown-agent")
    with patch("scripts.trust.run_trust_scan.load_baseline", return_value=BASELINE), patch(
        "scripts.trust.run_trust_scan.enumerate_live_crons",
        return_value=[_live_job(), unapproved_job],
    ), patch("scripts.trust.alert_render.emit") as mock_emit, patch(
        "scripts.trust.run_trust_scan.assertions_dir", return_value=assertions_dir
    ), patch(
        "scripts.trust.run_trust_scan.state_mod.DEFAULT_STATE_PATH", state_path
    ), patch(
        "scripts.trust.run_trust_scan.DEFAULT_WATERMARK_PATH", watermark_path
    ):
        from scripts.common.alert_bus.model import AlertResult

        mock_emit.return_value = AlertResult(ok=True)
        exit_code = rts.main([])

    assert exit_code == 0


def test_main_drift_found_never_nonzero_preflight_mode(isolated_paths):
    state_path, watermark_path, assertions_dir = isolated_paths
    unapproved_job = _live_job(name="mystery-cron", agentId="unknown-agent")
    with patch("scripts.trust.run_trust_scan.load_baseline", return_value=BASELINE), patch(
        "scripts.trust.run_trust_scan.enumerate_live_crons",
        return_value=[_live_job(), unapproved_job],
    ), patch("scripts.trust.alert_render.emit") as mock_emit, patch(
        "scripts.trust.run_trust_scan.assertions_dir", return_value=assertions_dir
    ), patch(
        "scripts.trust.run_trust_scan.state_mod.DEFAULT_STATE_PATH", state_path
    ), patch(
        "scripts.trust.run_trust_scan.DEFAULT_WATERMARK_PATH", watermark_path
    ):
        from scripts.common.alert_bus.model import AlertResult

        mock_emit.return_value = AlertResult(ok=True)
        exit_code = rts.main(["--preflight"])

    assert exit_code == 0


# --- fail-safe isolation: one sub-scan failing does not abort the other -----


def test_cron_scan_failure_isolated_assertion_scan_still_runs(isolated_paths):
    state_path, watermark_path, assertions_dir = isolated_paths
    assertion_file = assertions_dir / "2026-07-10.jsonl"
    record = {
        "ts": "2026-07-10T11:00:00+00:00",
        "agent": "main",
        "request_summary": None,
        "request_ref": None,
        "artifact_kind": "other",
        "artifact_ids": ["x1"],
        "claim": "did a thing",
    }
    assertion_file.write_text(json.dumps(record) + "\n", encoding="utf-8")

    with patch(
        "scripts.trust.run_trust_scan.enumerate_live_crons",
        side_effect=CronEnumerationError("openclaw cron list failed"),
    ), patch("scripts.trust.run_trust_scan.load_baseline", return_value=BASELINE), patch(
        "scripts.trust.alert_render.emit"
    ) as mock_emit:
        from scripts.common.alert_bus.model import AlertResult

        mock_emit.return_value = AlertResult(ok=True)

        summary = rts.run_scan(
            now=T0,
            state_path=state_path,
            watermark_path=watermark_path,
            assertions_base_dir=assertions_dir,
        )

    assert summary["ok"] is False
    assert any("cron_scan" in e for e in summary["errors"])
    # The assertion sub-scan still ran despite the cron sub-scan failing.
    assert summary["assertion_findings"] == 1
    assert summary["alerts_emitted"] == 1


def test_assertion_scan_failure_isolated_cron_scan_still_runs(isolated_paths):
    state_path, watermark_path, assertions_dir = isolated_paths
    unapproved_job = _live_job(name="mystery-cron", agentId="unknown-agent")

    with patch("scripts.trust.run_trust_scan.load_baseline", return_value=BASELINE), patch(
        "scripts.trust.run_trust_scan.enumerate_live_crons",
        return_value=[_live_job(), unapproved_job],
    ), patch(
        "scripts.trust.run_trust_scan._iter_new_assertions_positioned",
        side_effect=RuntimeError("assertion read exploded"),
    ), patch("scripts.trust.alert_render.emit") as mock_emit:
        from scripts.common.alert_bus.model import AlertResult

        mock_emit.return_value = AlertResult(ok=True)

        summary = rts.run_scan(
            now=T0,
            state_path=state_path,
            watermark_path=watermark_path,
            assertions_base_dir=assertions_dir,
        )

    assert any("assertion_scan" in e for e in summary["errors"])
    # The cron sub-scan still ran and its finding still got alerted.
    assert summary["drift_findings"] == 1
    assert summary["alerts_emitted"] == 1


# --- JSON summary shape -------------------------------------------------------


# --- watermark helper edge cases (fail-safe load, missing base dir) ---------


def test_load_watermark_missing_file_returns_empty(tmp_path: Path):
    assert rts._load_watermark(tmp_path / "does-not-exist.json") == {}


def test_load_watermark_corrupt_json_returns_empty(tmp_path: Path):
    path = tmp_path / "corrupt.json"
    path.write_text("{not valid json", encoding="utf-8")
    assert rts._load_watermark(path) == {}


def test_load_watermark_non_object_json_returns_empty(tmp_path: Path):
    path = tmp_path / "list.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    assert rts._load_watermark(path) == {}


def test_load_watermark_unreadable_file_returns_empty(tmp_path: Path):
    path = tmp_path / "watermark.json"
    path.mkdir()  # a directory -> read_text raises IsADirectoryError (OSError)
    assert rts._load_watermark(path) == {}


def test_save_watermark_roundtrip(tmp_path: Path):
    path = tmp_path / "watermark.json"
    rts._save_watermark({"foo.jsonl": 123}, path)
    assert rts._load_watermark(path) == {"foo.jsonl": 123}


def test_iter_new_assertions_missing_base_dir_returns_empty(tmp_path: Path):
    missing_dir = tmp_path / "does-not-exist"
    records, watermark = rts._iter_new_assertions(missing_dir, {})
    assert records == []
    assert watermark == {}


def test_iter_new_assertions_skips_unstattable_file(tmp_path: Path, monkeypatch):
    assertions_dir = tmp_path / "assertions"
    assertions_dir.mkdir()
    (assertions_dir / "2026-07-10.jsonl").write_text('{"a": 1}\n', encoding="utf-8")

    original_stat = Path.stat

    def _boom_stat(self, *args, **kwargs):
        if self.name == "2026-07-10.jsonl":
            raise OSError("simulated stat failure")
        return original_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", _boom_stat)
    records, watermark = rts._iter_new_assertions(assertions_dir, {})
    assert records == []
    assert watermark == {}


# --- F1: transient Vikunja fault holds the watermark + surfaces in errors ----


class _FakeVikunja:
    """Fake VikunjaClient.get keyed by task id: present / missing / transient."""

    def __init__(self, *, present=None, error=None):
        self._present = set(present or [])
        self._error = set(error or [])
        self.calls: list[str] = []

    def get(self, path, **_kwargs):
        self.calls.append(path)
        task_id = path.rsplit("/", 1)[-1]
        if task_id in self._error:
            raise RuntimeError("transient vikunja error")
        if task_id in self._present:
            return {"id": int(task_id)}
        from scripts.common.vikunja_client import VikunjaNotFoundError

        raise VikunjaNotFoundError(path=path, status=404)


def _vikunja_assertion(assertions_dir, artifact_ids, *, name="2026-07-10.jsonl"):
    record = {
        "ts": "2026-07-10T11:00:00+00:00",
        "agent": "main",
        "request_summary": None,
        "request_ref": None,
        "artifact_kind": "vikunja_task",
        "artifact_ids": artifact_ids,
        "claim": "Created Vikunja reminder tasks",
    }
    (assertions_dir / name).write_text(json.dumps(record) + "\n", encoding="utf-8")


def _run(isolated_paths, *, client, now=T0, live_jobs=None):
    state_path, watermark_path, assertions_dir = isolated_paths
    jobs = live_jobs if live_jobs is not None else [_live_job()]
    from scripts.common.alert_bus.model import AlertResult

    with patch("scripts.trust.run_trust_scan.load_baseline", return_value=BASELINE), patch(
        "scripts.trust.run_trust_scan.enumerate_live_crons", return_value=jobs
    ), patch(
        "scripts.trust.assertion_verifier._build_client", return_value=client
    ), patch("scripts.trust.alert_render.emit") as mock_emit:
        mock_emit.return_value = AlertResult(ok=True)
        summary = rts.run_scan(
            now=now,
            state_path=state_path,
            watermark_path=watermark_path,
            assertions_base_dir=assertions_dir,
        )
        return summary, mock_emit


def test_transient_vikunja_fault_holds_watermark_and_surfaces_error(isolated_paths):
    """F1: a record whose id hit a transient fault is NOT consumed — the
    watermark does not advance past it, so it re-reads next scan; the fault is
    recorded in errors[]."""
    state_path, watermark_path, assertions_dir = isolated_paths
    _vikunja_assertion(assertions_dir, ["91"])

    # Scan 1: id 91 errors transiently -> no finding, indeterminate.
    client1 = _FakeVikunja(error={"91"})
    summary1, _ = _run(isolated_paths, client=client1)
    assert summary1["assertion_findings"] == 0  # no false artifact_missing
    assert any("assertion_scan:indeterminate" in e for e in summary1["errors"])
    # Watermark did NOT advance past the (single, held) record.
    wm = rts._load_watermark(watermark_path)
    assert all(v == 0 for v in wm.values()) or wm == {}

    # Scan 2: Vikunja recovered, id 91 now confirmed missing -> the SAME record
    # is re-read (proving it was not silently consumed) and now flags missing.
    client2 = _FakeVikunja(present=set())
    summary2, _ = _run(isolated_paths, client=client2)
    assert summary2["assertion_findings"] == 1
    # Now conclusively verified -> watermark advances.
    wm2 = rts._load_watermark(watermark_path)
    assert any(v > 0 for v in wm2.values())


def test_conclusive_record_after_indeterminate_holds_whole_file(isolated_paths):
    """F1: an indeterminate record holds the watermark for the rest of its file
    even if a later record would verify conclusively — the whole tail re-reads."""
    state_path, watermark_path, assertions_dir = isolated_paths
    # Two records in one file: first indeterminate (91 errors), second missing.
    f = assertions_dir / "2026-07-10.jsonl"
    r1 = {"agent": "main", "artifact_kind": "vikunja_task", "artifact_ids": ["91"], "claim": "c1"}
    r2 = {"agent": "main", "artifact_kind": "vikunja_task", "artifact_ids": ["92"], "claim": "c2"}
    f.write_text(json.dumps(r1) + "\n" + json.dumps(r2) + "\n", encoding="utf-8")

    client = _FakeVikunja(present=set(), error={"91"})
    summary, _ = _run(isolated_paths, client=client)
    # 92 is missing -> 1 finding; 91 indeterminate -> held, no finding.
    assert summary["assertion_findings"] == 1
    assert any("indeterminate" in e for e in summary["errors"])
    # Watermark held at 0 for the file (first record indeterminate).
    wm = rts._load_watermark(watermark_path)
    assert wm.get(str(f), 0) == 0


# --- F2: persistent artifact_missing re-alerts; no false-resolve; resolves ----


def test_persistent_artifact_missing_realerts_at_24h_no_false_resolve(isolated_paths):
    """F2: an artifact_missing persists across scans (re-verified from state,
    independent of the watermark), re-alerts at 24h, and never emits a false
    'Cron drift cleared'."""
    state_path, watermark_path, assertions_dir = isolated_paths
    _vikunja_assertion(assertions_dir, ["91"])

    # Scan 1: 91 missing -> first-observation alert.
    client = _FakeVikunja(present=set())
    summary1, emit1 = _run(isolated_paths, client=client)
    assert summary1["assertion_findings"] == 1
    assert summary1["alerts_emitted"] == 1

    # Scan 2, +1h: no NEW assertion lines (watermark advanced), but the
    # outstanding artifact_missing is re-verified from state and still missing
    # -> finding persists, NOT re-alerted yet (<24h), and NO resolution emitted.
    summary2, emit2 = _run(isolated_paths, client=_FakeVikunja(present=set()), now=T0 + timedelta(hours=1))
    assert summary2["assertion_findings"] == 1  # persisted via re-verify
    assert summary2["alerts_emitted"] == 0  # not due, not resolved
    titles2 = [c.args[0].title for c in emit2.call_args_list]
    assert not any("cleared" in t.lower() for t in titles2)
    assert not any("drift cleared" in t.lower() for t in titles2)

    # Scan 3, +24h: re-alert fires (persistent unapproved-claim reminder).
    summary3, emit3 = _run(isolated_paths, client=_FakeVikunja(present=set()), now=T0 + timedelta(hours=24))
    assert summary3["alerts_emitted"] == 1
    titles3 = [c.args[0].title for c in emit3.call_args_list]
    assert any("not grounded" in t.lower() for t in titles3)


def test_artifact_missing_resolves_as_assertion_when_it_reappears(isolated_paths):
    """F2: when the artifact reappears, the finding resolves — rendered as an
    ASSERTION resolution, not 'Cron drift cleared'."""
    state_path, watermark_path, assertions_dir = isolated_paths
    _vikunja_assertion(assertions_dir, ["91"])

    # Scan 1: missing -> alert + seeded into state.
    _run(isolated_paths, client=_FakeVikunja(present=set()))

    # Scan 2: 91 now present -> re-verify finds it -> omitted from current
    # findings -> reconcile emits a resolution rendered as an ASSERTION.
    summary2, emit2 = _run(
        isolated_paths, client=_FakeVikunja(present={"91"}), now=T0 + timedelta(hours=2)
    )
    assert summary2["assertion_findings"] == 0
    titles = [c.args[0].title for c in emit2.call_args_list]
    sources = [c.args[0].source for c in emit2.call_args_list]
    assert any("now grounded" in t.lower() for t in titles)
    assert not any("cron drift cleared" in t.lower() for t in titles)
    assert any(s == "felix-trust-scan/assertion" for s in sources)


def test_reverify_transient_fault_does_not_false_resolve(isolated_paths):
    """F2: a transient fault while re-verifying an outstanding artifact_missing
    keeps it present (no false resolve) and records the fault."""
    state_path, watermark_path, assertions_dir = isolated_paths
    _vikunja_assertion(assertions_dir, ["91"])
    _run(isolated_paths, client=_FakeVikunja(present=set()))

    summary2, emit2 = _run(
        isolated_paths, client=_FakeVikunja(error={"91"}), now=T0 + timedelta(hours=2)
    )
    # Still present in findings (not resolved), fault recorded.
    assert summary2["assertion_findings"] == 1
    assert any("assertion_reverify:indeterminate" in e for e in summary2["errors"])
    titles = [c.args[0].title for c in emit2.call_args_list]
    assert not any("grounded" in t.lower() for t in titles)


# --- F3: failed emit leaves the finding DUE next scan ------------------------


def test_failed_emit_keeps_finding_due_next_scan(isolated_paths):
    """F3: a finding whose emit returns ok=False must stay DUE on the next scan
    (last_alerted not advanced), rather than being suppressed until 24h."""
    state_path, watermark_path, assertions_dir = isolated_paths
    unapproved_job = _live_job(name="mystery-cron", agentId="unknown-agent")
    from scripts.common.alert_bus.model import AlertResult

    # Scan 1: emit FAILS (ok=False).
    with patch("scripts.trust.run_trust_scan.load_baseline", return_value=BASELINE), patch(
        "scripts.trust.run_trust_scan.enumerate_live_crons",
        return_value=[_live_job(), unapproved_job],
    ), patch("scripts.trust.alert_render.emit") as mock_emit:
        mock_emit.return_value = AlertResult(ok=False, reason="bus down")
        summary1 = rts.run_scan(
            now=T0,
            state_path=state_path,
            watermark_path=watermark_path,
            assertions_base_dir=assertions_dir,
        )
    assert summary1["drift_findings"] == 1
    assert summary1["alerts_emitted"] == 0  # nothing reached Kent

    # Scan 2, only 1 minute later (far under 24h): emit now succeeds. Because
    # scan 1's emit failed, the finding must be DUE again immediately.
    with patch("scripts.trust.run_trust_scan.load_baseline", return_value=BASELINE), patch(
        "scripts.trust.run_trust_scan.enumerate_live_crons",
        return_value=[_live_job(), unapproved_job],
    ), patch("scripts.trust.alert_render.emit") as mock_emit2:
        mock_emit2.return_value = AlertResult(ok=True)
        summary2 = rts.run_scan(
            now=T0 + timedelta(minutes=1),
            state_path=state_path,
            watermark_path=watermark_path,
            assertions_base_dir=assertions_dir,
        )
    assert summary2["alerts_emitted"] == 1  # retried immediately, not 24h later


def test_successful_emit_does_not_re_alert_before_24h(isolated_paths):
    """F3 guard: a SUCCESSFUL emit still honors the 24h cadence (no immediate
    re-alert) — the emit-gating only affects failed emits."""
    state_path, watermark_path, assertions_dir = isolated_paths
    unapproved_job = _live_job(name="mystery-cron", agentId="unknown-agent")
    from scripts.common.alert_bus.model import AlertResult

    for offset_min in (0, 1):
        with patch("scripts.trust.run_trust_scan.load_baseline", return_value=BASELINE), patch(
            "scripts.trust.run_trust_scan.enumerate_live_crons",
            return_value=[_live_job(), unapproved_job],
        ), patch("scripts.trust.alert_render.emit") as mock_emit:
            mock_emit.return_value = AlertResult(ok=True)
            summary = rts.run_scan(
                now=T0 + timedelta(minutes=offset_min),
                state_path=state_path,
                watermark_path=watermark_path,
                assertions_base_dir=assertions_dir,
            )
        if offset_min == 0:
            assert summary["alerts_emitted"] == 1  # first observation
        else:
            assert summary["alerts_emitted"] == 0  # not due yet (<24h)


def test_iter_new_assertions_backcompat_wrapper_returns_records(tmp_path: Path):
    """The thin _iter_new_assertions wrapper returns records + advanced watermark."""
    d = tmp_path / "assertions"
    d.mkdir()
    f = d / "2026-07-10.jsonl"
    f.write_text('{"artifact_ids": ["1"]}\n\nnot-json\n{"artifact_ids": ["2"]}\n', encoding="utf-8")
    records, wm = rts._iter_new_assertions(d, {})
    assert [r["artifact_ids"] for r in records] == [["1"], ["2"]]  # bad line skipped
    assert wm[str(f)] == f.stat().st_size


def test_state_load_fault_degrades_to_empty_and_records_error(isolated_paths):
    """F-safe: a state-load fault does not crash the tick; it is recorded and
    the scan proceeds with empty state."""
    state_path, watermark_path, assertions_dir = isolated_paths
    from scripts.common.alert_bus.model import AlertResult

    with patch("scripts.trust.run_trust_scan.load_baseline", return_value=BASELINE), patch(
        "scripts.trust.run_trust_scan.enumerate_live_crons", return_value=[_live_job()]
    ), patch(
        "scripts.trust.run_trust_scan.state_mod.load_state",
        side_effect=RuntimeError("state store exploded"),
    ), patch("scripts.trust.alert_render.emit") as mock_emit:
        mock_emit.return_value = AlertResult(ok=True)
        summary = rts.run_scan(
            now=T0,
            state_path=state_path,
            watermark_path=watermark_path,
            assertions_base_dir=assertions_dir,
        )
    assert any("state_load" in e for e in summary["errors"])


def test_main_json_flag_prints_summary(isolated_paths, capsys):
    state_path, watermark_path, assertions_dir = isolated_paths
    with patch("scripts.trust.run_trust_scan.load_baseline", return_value=BASELINE), patch(
        "scripts.trust.run_trust_scan.enumerate_live_crons", return_value=[_live_job()]
    ), patch(
        "scripts.trust.run_trust_scan.assertions_dir", return_value=assertions_dir
    ), patch(
        "scripts.trust.run_trust_scan.state_mod.DEFAULT_STATE_PATH", state_path
    ), patch(
        "scripts.trust.run_trust_scan.DEFAULT_WATERMARK_PATH", watermark_path
    ):
        exit_code = rts.main(["--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out.strip())
    assert set(payload.keys()) == {
        "ok",
        "drift_findings",
        "assertion_findings",
        "unit_drift_findings",
        "unit_coverage",
        "alerts_emitted",
        "carried_forward",
        "findings_held",
        "errors",
    }
    assert exit_code == 0


# --- last-tick.json freshness signal (#721) ----------------------------------


def test_run_scan_writes_last_tick_on_clean_tick(isolated_paths, tmp_path):
    """A real (non-dry-run) tick writes last-tick.json with a fresh timestamp."""
    state_path, watermark_path, assertions_dir = isolated_paths
    last_tick = tmp_path / "state" / "last-tick.json"

    with patch("scripts.trust.run_trust_scan.load_baseline", return_value=BASELINE), patch(
        "scripts.trust.run_trust_scan.enumerate_live_crons", return_value=[_live_job()]
    ), patch("scripts.trust.alert_render.emit"):
        summary = rts.run_scan(
            now=T0,
            state_path=state_path,
            watermark_path=watermark_path,
            assertions_base_dir=assertions_dir,
            last_tick_path=last_tick,
        )

    assert summary["ok"] is True
    assert last_tick.exists()
    payload = json.loads(last_tick.read_text())
    assert payload["completed_at_utc"] == "2026-07-10T12:00:00Z"
    assert payload["exit_status"] == "success"
    assert payload["scan_inability"] is False
    assert payload["error_count"] == 0


def test_dry_run_writes_no_last_tick(isolated_paths, tmp_path):
    """--dry-run must mutate nothing, including the freshness pointer."""
    state_path, watermark_path, assertions_dir = isolated_paths
    last_tick = tmp_path / "state" / "last-tick.json"

    with patch("scripts.trust.run_trust_scan.load_baseline", return_value=BASELINE), patch(
        "scripts.trust.run_trust_scan.enumerate_live_crons", return_value=[_live_job()]
    ), patch("scripts.trust.alert_render.emit"):
        rts.run_scan(
            dry_run=True,
            now=T0,
            state_path=state_path,
            watermark_path=watermark_path,
            assertions_base_dir=assertions_dir,
            last_tick_path=last_tick,
        )

    assert not last_tick.exists()


def test_scan_inability_marks_last_tick_failure(isolated_paths, tmp_path):
    """A hard scan-inability (unreadable baseline) writes exit_status=failure."""
    state_path, watermark_path, assertions_dir = isolated_paths
    last_tick = tmp_path / "state" / "last-tick.json"

    with patch(
        "scripts.trust.run_trust_scan.load_baseline",
        side_effect=Exception("baseline unreadable"),
    ), patch(
        "scripts.trust.run_trust_scan.enumerate_live_crons", return_value=[]
    ), patch("scripts.trust.alert_render.emit"):
        summary = rts.run_scan(
            now=T0,
            state_path=state_path,
            watermark_path=watermark_path,
            assertions_base_dir=assertions_dir,
            last_tick_path=last_tick,
        )

    assert summary["ok"] is False
    payload = json.loads(last_tick.read_text())
    assert payload["exit_status"] == "failure"
    assert payload["scan_inability"] is True
    assert payload["error_count"] >= 1
    # The canary probe (state-file/_explicit_error) must read this as a failure.
    from scripts.canary.probes import _explicit_error

    assert _explicit_error(payload) is not None


def test_last_tick_stays_success_on_transient_finding_fault(isolated_paths, tmp_path):
    """A transient assertion-side fault (not scan-inability) keeps exit_status=success.

    The freshness pointer must not page the canary on a recoverable Vikunja
    hiccup — only a hard scan-inability flips exit_status to failure.
    """
    state_path, watermark_path, assertions_dir = isolated_paths
    last_tick = tmp_path / "state" / "last-tick.json"

    # An assertion JSONL whose verification raises inside the assertion sub-scan
    # populates errors[] (ok=False) WITHOUT setting scan_inability.
    (assertions_dir / "a.jsonl").write_text(
        json.dumps({"artifact_kind": "vikunja_task", "artifact_ids": [1]}) + "\n"
    )
    with patch("scripts.trust.run_trust_scan.load_baseline", return_value=BASELINE), patch(
        "scripts.trust.run_trust_scan.enumerate_live_crons", return_value=[_live_job()]
    ), patch(
        "scripts.trust.run_trust_scan.verify_assertion_detailed",
        side_effect=Exception("vikunja down"),
    ), patch("scripts.trust.alert_render.emit"):
        summary = rts.run_scan(
            now=T0,
            state_path=state_path,
            watermark_path=watermark_path,
            assertions_base_dir=assertions_dir,
            last_tick_path=last_tick,
        )

    assert summary["ok"] is False  # errors[] populated
    payload = json.loads(last_tick.read_text())
    assert payload["exit_status"] == "success"  # but NOT a scan-inability
    assert payload["scan_inability"] is False
    from scripts.canary.probes import _explicit_error

    assert _explicit_error(payload) is None  # canary stays healthy


# --- #1124: null-agent plugin crons must not fail the alert path open --------


def _memory_core_job(**overrides) -> dict:
    """The OpenClaw 2026.11.7 memory-core plugin cron shape (agentId null)."""
    job = {
        "id": "7d1c2b9e-0000-4000-8000-memorycore01",
        "name": "Memory Dreaming Promotion",
        "agentId": None,
        "declarationKey": "memory-core:memory-dreaming-promotion",
        "enabled": True,
        "createdAtMs": 1795000000000,
        "schedule": {"kind": "cron", "expr": "0 3 * * *"},
    }
    job.update(overrides)
    return job


def _memory_core_job_no_agent_key() -> dict:
    job = _memory_core_job()
    del job["agentId"]
    return job


def _scan(isolated_paths, live_jobs, *, now=T0, last_tick=None, emit_side_effect=None, extra_patches=()):
    from contextlib import ExitStack

    from scripts.common.alert_bus.model import AlertResult

    state_path, watermark_path, assertions_dir = isolated_paths
    with ExitStack() as stack:
        stack.enter_context(
            patch("scripts.trust.run_trust_scan.load_baseline", return_value=BASELINE)
        )
        stack.enter_context(
            patch("scripts.trust.run_trust_scan.enumerate_live_crons", return_value=live_jobs)
        )
        mock_emit = stack.enter_context(patch("scripts.trust.alert_render.emit"))
        if emit_side_effect is not None:
            mock_emit.side_effect = emit_side_effect
        else:
            mock_emit.return_value = AlertResult(ok=True)
        for p in extra_patches:
            stack.enter_context(p)
        # Pin the unit-drift sub-scan to "skipped" so finding counts here never
        # depend on the host's real ~/.config/systemd/user contents.
        kwargs = {"unit_deployed_dir": state_path.parent / "no-deployed-units"}
        if last_tick is not None:
            kwargs["last_tick_path"] = last_tick
        summary = rts.run_scan(
            now=now,
            state_path=state_path,
            watermark_path=watermark_path,
            assertions_base_dir=assertions_dir,
            **kwargs,
        )
    return summary, mock_emit


@pytest.mark.parametrize(
    "null_agent_job",
    [_memory_core_job(), _memory_core_job_no_agent_key()],
    ids=["agentId-null", "agentId-absent"],
)
def test_null_agent_plugin_cron_alerts_and_does_not_suppress_others(
    isolated_paths, tmp_path, null_agent_job
):
    """#1124 done-condition: a null-agent unapproved cron (memory-core shape)
    plus another unapproved cron → ok True, BOTH alerted, state saved."""
    state_path, _, _ = isolated_paths
    last_tick = tmp_path / "state" / "last-tick.json"
    live = [
        _live_job(),
        null_agent_job,
        _live_job(id="rogue-1", name="mystery-cron", agentId="unknown-agent"),
    ]

    summary, mock_emit = _scan(isolated_paths, live, last_tick=last_tick)

    assert summary["errors"] == []
    assert summary["ok"] is True
    assert summary["drift_findings"] == 2
    assert summary["alerts_emitted"] == 2
    titles = sorted(call.args[0].title for call in mock_emit.call_args_list)
    assert titles == [
        "Unrequested cron detected: Memory Dreaming Promotion",
        "Unrequested cron detected: mystery-cron",
    ]
    saved = json.loads(state_path.read_text())
    assert sorted(e["name"] for e in saved.values()) == [
        "Memory Dreaming Promotion",
        "mystery-cron",
    ]
    payload = json.loads(last_tick.read_text())
    assert payload["exit_status"] == "success"
    assert payload["alert_path_fault"] is False


def test_null_agent_cron_honours_24h_cadence_across_ticks(isolated_paths):
    live = [_live_job(), _memory_core_job()]
    s1, _ = _scan(isolated_paths, live, now=T0)
    s2, _ = _scan(isolated_paths, live, now=T0 + timedelta(minutes=15))
    assert s1["alerts_emitted"] == 1
    assert s2["ok"] is True
    assert s2["alerts_emitted"] == 0  # deduped, not re-alerted every tick


def test_non_str_agent_alongside_null_agent(isolated_paths):
    """(d) agentId 42 alongside None — both alert, ok True."""
    live = [_live_job(), _memory_core_job(), _memory_core_job(id="n42", agentId=42)]
    summary, _ = _scan(isolated_paths, live)
    assert summary["ok"] is True
    assert summary["drift_findings"] == 2
    assert summary["alerts_emitted"] == 2


def test_unfingerprintable_finding_isolated_others_reconcile(isolated_paths, tmp_path):
    """(a) guard independent of the normaliser: a finding whose fingerprint
    raises is still emitted (no state), the other finding is emitted AND saved,
    ok False, error names the bad finding, last-tick flags an alert-path fault."""
    state_path, _, _ = isolated_paths
    last_tick = tmp_path / "state" / "last-tick.json"
    real_fingerprint = rts.state_mod.fingerprint_finding

    def flaky_fingerprint(finding, baseline_hash):
        if getattr(finding, "name", None) == "bad":
            raise TypeError("boom")
        return real_fingerprint(finding, baseline_hash)

    live = [
        _live_job(),
        _live_job(id="b", name="bad", agentId="agent-b"),
        _live_job(id="g", name="good", agentId="agent-g"),
    ]
    summary, mock_emit = _scan(
        isolated_paths,
        live,
        last_tick=last_tick,
        extra_patches=[
            patch(
                "scripts.trust.run_trust_scan.state_mod.fingerprint_finding",
                side_effect=flaky_fingerprint,
            )
        ],
    )

    assert summary["ok"] is False
    assert any(e.startswith("state_fingerprint:TypeError:bad") for e in summary["errors"])
    assert summary["alerts_emitted"] == 2
    titles = sorted(call.args[0].title for call in mock_emit.call_args_list)
    assert titles == [
        "Unrequested cron detected: bad",
        "Unrequested cron detected: good",
    ]
    saved = json.loads(state_path.read_text())
    assert [e["name"] for e in saved.values()] == ["good"]
    payload = json.loads(last_tick.read_text())
    assert payload["exit_status"] == "failure"
    assert payload["alert_path_fault"] is True
    assert payload["scan_inability"] is False


def test_unfingerprintable_finding_emitted_every_tick(isolated_paths):
    real_fingerprint = rts.state_mod.fingerprint_finding

    def flaky_fingerprint(finding, baseline_hash):
        if getattr(finding, "name", None) == "bad":
            raise TypeError("boom")
        return real_fingerprint(finding, baseline_hash)

    live = [_live_job(), _live_job(id="b", name="bad", agentId="agent-b")]

    def p():
        return patch(
            "scripts.trust.run_trust_scan.state_mod.fingerprint_finding",
            side_effect=flaky_fingerprint,
        )

    s1, _ = _scan(isolated_paths, live, now=T0, extra_patches=[p()])
    s2, _ = _scan(isolated_paths, live, now=T0 + timedelta(minutes=15), extra_patches=[p()])
    assert s1["alerts_emitted"] == 1
    assert s2["alerts_emitted"] == 1  # no state → loud every tick, never silent


def test_reconcile_failure_emits_every_finding_and_saves_nothing(isolated_paths, tmp_path):
    """Last-resort fallback + (b) + (e): reconcile raises → every current
    finding is still emitted, ok False, error recorded, NO state file written,
    watermark file unchanged, last-tick exit_status failure."""
    state_path, watermark_path, assertions_dir = isolated_paths
    last_tick = tmp_path / "state" / "last-tick.json"
    # An (empty) assertion file would advance the watermark if it were saved.
    (assertions_dir / "a.jsonl").write_text("")
    watermark_path.parent.mkdir(parents=True, exist_ok=True)
    watermark_path.write_text('{"sentinel": 7}\n')
    before = watermark_path.read_bytes()

    live = [
        _live_job(),
        _memory_core_job(),
        _live_job(id="r", name="mystery-cron", agentId="unknown-agent"),
    ]
    summary, mock_emit = _scan(
        isolated_paths,
        live,
        last_tick=last_tick,
        extra_patches=[
            patch(
                "scripts.trust.run_trust_scan.state_mod.reconcile",
                side_effect=RuntimeError("reconcile exploded"),
            )
        ],
    )

    assert summary["ok"] is False
    assert any(e.startswith("state_reconcile:RuntimeError") for e in summary["errors"])
    assert summary["alerts_emitted"] == 2
    assert mock_emit.call_count == 2
    assert not state_path.exists()
    assert watermark_path.read_bytes() == before
    payload = json.loads(last_tick.read_text())
    assert payload["exit_status"] == "failure"
    assert payload["alert_path_fault"] is True
    assert payload["scan_inability"] is False


def test_save_state_failure_leaves_watermark_unchanged(isolated_paths, tmp_path):
    """(c) watermark is saved ONLY after a successful state save (R1)."""
    _state_path, watermark_path, assertions_dir = isolated_paths
    last_tick = tmp_path / "state" / "last-tick.json"
    (assertions_dir / "a.jsonl").write_text("")
    watermark_path.parent.mkdir(parents=True, exist_ok=True)
    watermark_path.write_text('{"sentinel": 7}\n')
    before = watermark_path.read_bytes()

    live = [_live_job(), _memory_core_job()]
    summary, _ = _scan(
        isolated_paths,
        live,
        last_tick=last_tick,
        extra_patches=[
            patch(
                "scripts.trust.run_trust_scan.state_mod.save_state",
                side_effect=OSError("disk full"),
            )
        ],
    )

    assert summary["ok"] is False
    assert any(e.startswith("state_save:OSError") for e in summary["errors"])
    assert summary["alerts_emitted"] == 1
    assert watermark_path.read_bytes() == before
    payload = json.loads(last_tick.read_text())
    assert payload["exit_status"] == "failure"
    assert payload["alert_path_fault"] is True


def test_emit_raise_for_one_finding_does_not_suppress_others(isolated_paths, tmp_path):
    """Per-emit guard: one emit raising is recorded, the rest still go out, and
    the failed finding stays DUE for the next tick (keep_due)."""
    last_tick = tmp_path / "state" / "last-tick.json"
    from scripts.trust import alert_render

    real_emit_finding = alert_render.emit_finding

    def flaky_emit_finding(finding):
        if getattr(finding, "name", None) == "bad":
            raise RuntimeError("emit exploded")
        return real_emit_finding(finding)

    live = [
        _live_job(),
        _live_job(id="b", name="bad", agentId="agent-b"),
        _live_job(id="g", name="good", agentId="agent-g"),
    ]
    summary, mock_emit = _scan(
        isolated_paths,
        live,
        last_tick=last_tick,
        extra_patches=[
            patch(
                "scripts.trust.run_trust_scan.alert_render.emit_finding",
                side_effect=flaky_emit_finding,
            )
        ],
    )

    assert summary["ok"] is False
    assert any(e.startswith("emit:RuntimeError") for e in summary["errors"])
    assert summary["alerts_emitted"] == 1
    assert [c.args[0].title for c in mock_emit.call_args_list] == [
        "Unrequested cron detected: good"
    ]
    payload = json.loads(last_tick.read_text())
    assert payload["exit_status"] == "failure"
    assert payload["alert_path_fault"] is True

    # Next tick, 1 minute later, emits healthy: only the failed one re-fires.
    s2, mock_emit2 = _scan(isolated_paths, live, now=T0 + timedelta(minutes=1))
    assert s2["ok"] is True
    assert s2["alerts_emitted"] == 1
    assert [c.args[0].title for c in mock_emit2.call_args_list] == [
        "Unrequested cron detected: bad"
    ]


def test_clean_tick_last_tick_has_no_alert_path_fault(isolated_paths, tmp_path):
    last_tick = tmp_path / "state" / "last-tick.json"
    summary, _ = _scan(isolated_paths, [_live_job()], last_tick=last_tick)
    assert summary["ok"] is True
    payload = json.loads(last_tick.read_text())
    assert payload["alert_path_fault"] is False
    assert payload["exit_status"] == "success"


# --- #1124 pre-merge review fixes --------------------------------------------


def test_render_failure_is_an_alert_path_fault_and_stays_due(isolated_paths, tmp_path):
    """renata F1: emit_finding swallows a render exception into
    ok=False/RENDER_ERROR. That must NOT read as an ordinary failed delivery —
    it is recorded, flags alert_path_fault, and the finding stays due."""
    last_tick = tmp_path / "state" / "last-tick.json"
    live = [_live_job(), _live_job(id="r", name="mystery-cron", agentId="unknown-agent")]

    s1, mock_emit = _scan(
        isolated_paths,
        live,
        last_tick=last_tick,
        extra_patches=[
            patch(
                "scripts.trust.alert_render.render_cron_finding",
                side_effect=RuntimeError("render exploded"),
            )
        ],
    )

    assert s1["ok"] is False
    assert any(
        e.startswith("emit:RENDER_ERROR:RuntimeError:mystery-cron") for e in s1["errors"]
    ), s1["errors"]
    assert s1["alerts_emitted"] == 0
    assert mock_emit.call_count == 0  # never reached the bus
    payload = json.loads(last_tick.read_text())
    assert payload["exit_status"] == "failure"
    assert payload["alert_path_fault"] is True

    # Next tick, renderer healthy: the finding was kept due, so it fires now.
    s2, mock_emit2 = _scan(isolated_paths, live, now=T0 + timedelta(minutes=1))
    assert s2["ok"] is True
    assert s2["alerts_emitted"] == 1
    assert [c.args[0].title for c in mock_emit2.call_args_list] == [
        "Unrequested cron detected: mystery-cron"
    ]


def test_render_unknown_finding_type_is_an_alert_path_fault(isolated_paths, tmp_path):
    last_tick = tmp_path / "state" / "last-tick.json"
    from scripts.common.alert_bus.model import AlertResult

    live = [_live_job(), _live_job(id="r", name="mystery-cron", agentId="unknown-agent")]
    summary, _ = _scan(
        isolated_paths,
        live,
        last_tick=last_tick,
        extra_patches=[
            patch(
                "scripts.trust.run_trust_scan.alert_render.emit_finding",
                return_value=AlertResult(ok=False, reason="RENDER_UNKNOWN_FINDING_TYPE"),
            )
        ],
    )
    assert summary["ok"] is False
    assert any(
        e.startswith("emit:RENDER_UNKNOWN_FINDING_TYPE:mystery-cron") for e in summary["errors"]
    ), summary["errors"]
    assert json.loads(last_tick.read_text())["alert_path_fault"] is True


def test_bus_ok_false_is_still_not_an_alert_path_fault(isolated_paths, tmp_path):
    """Guard on the F1 fix: a plain bus delivery failure (non-RENDER_ reason)
    keeps its existing semantics — retried via keep_due, not an error."""
    from scripts.common.alert_bus.model import AlertResult

    last_tick = tmp_path / "state" / "last-tick.json"
    live = [_live_job(), _live_job(id="r", name="mystery-cron", agentId="unknown-agent")]
    summary, _ = _scan(
        isolated_paths,
        live,
        last_tick=last_tick,
        emit_side_effect=lambda alert: AlertResult(ok=False, reason="bus down"),
    )
    assert summary["ok"] is True
    assert summary["alerts_emitted"] == 0
    assert json.loads(last_tick.read_text())["alert_path_fault"] is False


def _surrogate_agent_assertion(assertions_dir) -> None:
    # A lone surrogate survives json.loads but cannot be UTF-8 encoded. Before
    # the pre-merge #1128 fix this made fingerprint_finding raise
    # UnicodeEncodeError (Codex's repro); _canonical now routes it to v2, so
    # the test below injects that raise to keep the guard covered. Written as
    # a JSON \\ud800 escape so the file itself is valid UTF-8.
    line = (
        '{"ts": "2026-07-10T11:00:00+00:00", "agent": "bad\\ud800agent", '
        '"request_summary": null, "request_ref": null, "artifact_kind": "other", '
        '"artifact_ids": ["x1"], "claim": "did a thing"}\n'
    )
    (assertions_dir / "2026-07-10.jsonl").write_text(line, encoding="utf-8")


def test_unfingerprintable_assertion_is_not_lost_watermark_held(isolated_paths):
    """Codex/renata F2: an unfingerprintable ASSERTION finding never enters
    state, so the watermark must not advance past its record — otherwise it is
    emitted once and permanently lost. Hold the watermark; emit every tick.

    The surrogate no longer makes fingerprinting raise (#1128 routes it to
    v2), so the pre-fix UnicodeEncodeError is injected for this one assertion
    to keep exercising the watermark-hold guard independent of the encoder."""
    from scripts.trust.assertion_verifier import AssertionFinding

    state_path, watermark_path, assertions_dir = isolated_paths
    _surrogate_agent_assertion(assertions_dir)
    watermark_path.parent.mkdir(parents=True, exist_ok=True)
    watermark_path.write_text('{"sentinel": 7}\n')
    before = watermark_path.read_bytes()
    live = [_live_job(), _live_job(id="r", name="mystery-cron", agentId="unknown-agent")]
    real_fingerprint = rts.state_mod.fingerprint_finding

    def legacy_raising_fingerprint(finding, baseline_hash):
        if isinstance(finding, AssertionFinding) and finding.artifact_id == "x1":
            raise UnicodeEncodeError("utf-8", finding.agent, 3, 4, "surrogates not allowed")
        return real_fingerprint(finding, baseline_hash)

    def fp_patch():
        return patch(
            "scripts.trust.run_trust_scan.state_mod.fingerprint_finding",
            side_effect=legacy_raising_fingerprint,
        )

    s1, emit1 = _scan(isolated_paths, live, now=T0, extra_patches=[fp_patch()])
    s2, emit2 = _scan(
        isolated_paths, live, now=T0 + timedelta(minutes=15), extra_patches=[fp_patch()]
    )

    for summary in (s1, s2):
        assert summary["assertion_findings"] == 1
        assert summary["ok"] is False
        assert any(
            e.startswith("state_fingerprint:UnicodeEncodeError:other:x1")
            for e in summary["errors"]
        ), summary["errors"]
    unverifiable = "Completion claim unverifiable: other"
    assert unverifiable in [c.args[0].title for c in emit1.call_args_list]
    assert unverifiable in [c.args[0].title for c in emit2.call_args_list]  # NOT lost
    assert watermark_path.read_bytes() == before
    # The fingerprintable cron finding still reconciles + persists normally
    # (alerted once, deduped on tick 2).
    saved = json.loads(state_path.read_text())
    assert [e["name"] for e in saved.values()] == ["mystery-cron"]
    assert s1["alerts_emitted"] == 2
    assert s2["alerts_emitted"] == 1


def test_surrogate_agent_assertion_now_fingerprints_and_reconciles(isolated_paths):
    """#1128 pre-merge fix: a lone-surrogate field routes to the v2 encoding,
    so the record fingerprints, reconciles into state and dedups on tick 2."""
    state_path, _, assertions_dir = isolated_paths
    _surrogate_agent_assertion(assertions_dir)
    live = [_live_job()]

    s1, _ = _scan(isolated_paths, live, now=T0)

    assert s1["errors"] == []
    assert s1["ok"] is True
    assert s1["assertion_findings"] == 1
    assert s1["alerts_emitted"] == 1
    assert [e["source"] for e in json.loads(state_path.read_text()).values()] == ["assertion"]


def test_keep_due_failure_is_recorded_as_alert_path_fault(isolated_paths, tmp_path):
    from scripts.common.alert_bus.model import AlertResult

    last_tick = tmp_path / "state" / "last-tick.json"
    live = [_live_job(), _live_job(id="r", name="mystery-cron", agentId="unknown-agent")]
    summary, _ = _scan(
        isolated_paths,
        live,
        last_tick=last_tick,
        emit_side_effect=lambda alert: AlertResult(ok=False, reason="bus down"),
        extra_patches=[
            patch(
                "scripts.trust.run_trust_scan.state_mod.keep_due",
                side_effect=RuntimeError("keep_due exploded"),
            )
        ],
    )
    assert summary["ok"] is False
    assert any(
        e.startswith("state_keep_due:RuntimeError:mystery-cron") for e in summary["errors"]
    ), summary["errors"]
    assert json.loads(last_tick.read_text())["alert_path_fault"] is True


def test_resolved_event_render_failure_is_guarded(isolated_paths, tmp_path):
    last_tick = tmp_path / "state" / "last-tick.json"
    rogue = _live_job(id="r", name="mystery-cron", agentId="unknown-agent")
    other = _live_job(id="o", name="other-cron", agentId="unknown-agent")

    s1, _ = _scan(isolated_paths, [_live_job(), rogue, other], now=T0)
    assert s1["alerts_emitted"] == 2

    # Tick 2: mystery-cron disappears (→ resolved event, render raises);
    # other-cron persists. The tick still completes and saves state.
    state_path, _, _ = isolated_paths
    s2, _ = _scan(
        isolated_paths,
        [_live_job(), other],
        now=T0 + timedelta(minutes=15),
        last_tick=last_tick,
        extra_patches=[
            patch(
                "scripts.trust.run_trust_scan.alert_render.render_drift_resolved",
                side_effect=RuntimeError("resolved render exploded"),
            )
        ],
    )
    assert s2["ok"] is False
    assert any(
        e.startswith("emit:RuntimeError:mystery-cron") for e in s2["errors"]
    ), s2["errors"]
    assert json.loads(last_tick.read_text())["alert_path_fault"] is True
    saved = json.loads(state_path.read_text())
    assert [e["name"] for e in saved.values()] == ["other-cron"]


# --- #1126/#1127 end to end through a fake `cron list --all --json` ----------


def test_e2e_duplicate_and_malformed_enabled_through_fake_cron_list_all(
    isolated_paths, tmp_path
):
    """Fakes the subprocess boundary (not enumerate_live_crons), so the real
    argv, payload parse, detector and render all run. A duplicate copy of an
    approved cron and an approved cron with a malformed `enabled` both alert;
    the tick is ok with no errors."""
    import subprocess

    from scripts.common.alert_bus.model import AlertResult

    state_path, watermark_path, assertions_dir = isolated_paths
    baseline = [
        *BASELINE,
        ApprovedCron(
            name="escalation-daily",
            agent_id="felix-admin-escalation",
            schedule_expr="0 12 * * *",
            tz="",
            purpose="test",
            approved_by="kent",
            approved_at="2026-07-01",
        ),
    ]
    payload = {
        "jobs": [
            _live_job(id="inbox-dup", createdAtMs=1775153265999),
            _live_job(id="inbox-orig", createdAtMs=1775153265189),
            {
                "id": "esc-1",
                "name": "escalation-daily",
                "agentId": "felix-admin-escalation",
                "enabled": {"a": 1},
                "createdAtMs": 1775153265000,
                "schedule": {"kind": "cron", "expr": "0 12 * * *"},
            },
        ],
        "total": 3,
        "hasMore": False,
    }
    seen_argv: list[list[str]] = []

    def fake_run(argv, *args, **kwargs):
        seen_argv.append(list(argv))
        return subprocess.CompletedProcess(
            args=argv, returncode=0, stdout=json.dumps(payload), stderr=""
        )

    with patch("scripts.trust.run_trust_scan.load_baseline", return_value=baseline), patch(
        "scripts.trust.cron_drift_detector.subprocess.run", side_effect=fake_run
    ), patch("scripts.trust.alert_render.emit") as mock_emit:
        mock_emit.return_value = AlertResult(ok=True)
        summary = rts.run_scan(
            now=T0,
            state_path=state_path,
            watermark_path=watermark_path,
            assertions_base_dir=assertions_dir,
            last_tick_path=tmp_path / "state" / "last-tick.json",
            unit_deployed_dir=state_path.parent / "no-deployed-units",
        )

    assert seen_argv and seen_argv[0][-4:] == ["cron", "list", "--all", "--json"]
    assert summary["errors"] == []
    assert summary["ok"] is True
    assert summary["drift_findings"] == 2
    assert summary["alerts_emitted"] == 2
    alerts = sorted((call.args[0] for call in mock_emit.call_args_list), key=lambda a: a.title)
    assert [a.title for a in alerts] == [
        "Approved cron not confirmed enabled: escalation-daily",
        "Duplicate cron detected: inbox-5pm",
    ]
    assert alerts[1].details["cron_id"] == "inbox-dup"
    assert alerts[1].details["primary_cron_id"] == "inbox-orig"
    assert alerts[0].details["enabled_raw"] == "{'a': 1}"
    saved = json.loads(state_path.read_text())
    assert sorted(e["name"] for e in saved.values()) == [
        "escalation-daily",
        "inbox-5pm (duplicate inbox-dup)",
    ]


# --- #1129: a sub-scan that did not complete never resolves its findings ------
#
# Each test pre-seeds seen-state with one outstanding entry per source, every
# one of which is GONE from the live world this tick (clean cron list, no unit
# drift, the Vikunja artifact reappeared). A source that completes therefore
# resolves its entry; a source that did not complete must carry it forward.

_SEEN_AT = (T0 - timedelta(hours=1)).isoformat()  # seen + alerted, not yet due

_CLEARED_TITLE = {
    "cron": "Cron drift cleared: rogue-cron",
    "unit-drift": "Deployed unit drift cleared: felix-canary.service",
    "assertion": "Completion claim now grounded: vikunja_task:91",
}


def _seeded_state() -> dict[str, dict[str, str]]:
    """source -> (fingerprint, entry), using each source's real fingerprint."""
    cron_hash = baseline_hash(BASELINE)
    cron_fp = state_mod.fingerprint_finding(
        CronDriftFinding(kind="unapproved_present", name="rogue-cron", agent_id="rogue-agent"),
        cron_hash,
    )
    unit_fp = state_mod.fingerprint_finding(
        UnitDriftFinding(
            kind="content_drift",
            name="felix-canary.service",
            repo_source="scripts/office2/felix-canary.service",
        ),
        "",
    )
    assertion = AssertionFinding(
        kind="artifact_missing",
        agent="main",
        artifact_kind="vikunja_task",
        artifact_id="91",
        claim="Created Vikunja task",
    )
    # Assertion fingerprints are not baseline-versioned (#1130).
    assertion_fp = state_mod.fingerprint_finding(assertion, "")
    times = {"first_seen": _SEEN_AT, "last_seen": _SEEN_AT, "last_alerted": _SEEN_AT}
    return {
        "cron": (cron_fp, {**times, "name": "rogue-cron", "source": "cron"}),
        "unit-drift": (
            unit_fp,
            {**times, "name": "felix-canary.service", "source": "unit-drift"},
        ),
        "assertion": (
            assertion_fp,
            {
                **times,
                "name": "vikunja_task:91",
                "source": "assertion",
                "assertion_kind": "artifact_missing",
                "artifact_kind": "vikunja_task",
                "artifact_id": "91",
                "agent": "main",
                "claim": "Created Vikunja task",
            },
        ),
    }


def _carry_scan(
    tmp_path: Path,
    *,
    overrides: dict[str, dict] | None = None,
    unit_dir_present: bool = True,
    dry_run: bool = False,
    extra_patches=(),
):
    """Run one tick over the seeded three-source state with fakes at every
    I/O boundary. ``overrides`` maps a ``run_trust_scan`` attribute to the
    ``patch`` kwargs that replace its default fake (e.g. a ``side_effect``)."""
    from contextlib import ExitStack

    from scripts.common.alert_bus.model import AlertResult

    seeded = _seeded_state()
    state_path = tmp_path / "state" / "seen-findings.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(dict(seeded.values())))
    assertions_dir = tmp_path / "assertions"
    assertions_dir.mkdir(exist_ok=True)
    deployed = tmp_path / "deployed-units"
    if unit_dir_present:
        deployed.mkdir(exist_ok=True)
    last_tick = tmp_path / "state" / "last-tick.json"

    fakes: dict[str, dict] = {
        "load_baseline": {"return_value": BASELINE},
        "enumerate_live_crons": {"return_value": [_live_job()]},
        "enumerate_unit_pairs": {"return_value": ([], UnitCoverage())},
        "detect_unit_drift": {"return_value": []},
        "verify_vikunja_id_present": {"return_value": True},  # artifact reappeared
    }
    fakes.update(overrides or {})

    with ExitStack() as stack:
        mocks = {
            name: stack.enter_context(patch(f"scripts.trust.run_trust_scan.{name}", **kwargs))
            for name, kwargs in fakes.items()
        }
        mock_emit = stack.enter_context(patch("scripts.trust.alert_render.emit"))
        mock_emit.return_value = AlertResult(ok=True)
        for p in extra_patches:
            stack.enter_context(p)
        summary = rts.run_scan(
            dry_run=dry_run,
            now=T0,
            state_path=state_path,
            watermark_path=tmp_path / "state" / "assertion-watermark.json",
            assertions_base_dir=assertions_dir,
            last_tick_path=last_tick,
            unit_deployed_dir=deployed,
        )

    return SimpleNamespace(
        summary=summary,
        seeded=seeded,
        saved=json.loads(state_path.read_text()),
        titles=[c.args[0].title for c in mock_emit.call_args_list],
        last_tick=json.loads(last_tick.read_text()) if last_tick.exists() else None,
        mocks=mocks,
    )


def _assert_sources_carried(run, carried_sources: tuple[str, ...]) -> None:
    carried_fps = set()
    for source in carried_sources:
        carried_fp, carried_entry = run.seeded[source]
        carried_fps.add(carried_fp)
        # Carried forward identical: no ResolvedEvent, no last_seen refresh.
        assert run.saved[carried_fp] == carried_entry
        assert _CLEARED_TITLE[source] not in run.titles
    # The sources that did complete resolve exactly as today.
    for source, (fp, _entry) in run.seeded.items():
        if source in carried_sources:
            continue
        assert fp not in run.saved
        assert _CLEARED_TITLE[source] in run.titles
    assert set(run.saved) == carried_fps
    assert run.summary["carried_forward"] == len(carried_sources)
    assert run.summary["findings_held"] is True
    # B1: held findings are visible to the canary.
    assert run.last_tick["exit_status"] == "failure"
    assert run.last_tick["findings_held"] is True
    assert run.last_tick["carried_forward"] == len(carried_sources)


def _assert_only_source_carried(run, carried_source: str) -> None:
    _assert_sources_carried(run, (carried_source,))


@pytest.mark.parametrize(
    "carried_sources, overrides, unit_dir_present, scan_inability",
    [
        (
            ("cron",),
            {"enumerate_live_crons": {"side_effect": CronEnumerationError("openclaw down")}},
            True,
            True,
        ),
        (
            ("cron",),
            {"detect_cron_drift": {"side_effect": RuntimeError("detector bug")}},
            True,
            True,
        ),
        (
            # #1130: assertion fingerprints do not depend on the baseline, so the
            # assertion source completes and its reappeared artifact resolves.
            ("cron",),
            {"load_baseline": {"side_effect": BaselineError("baseline unreadable")}},
            True,
            True,
        ),
        (
            ("unit-drift",),
            {"enumerate_unit_pairs": {"side_effect": UnitEnumerationError("unreadable")}},
            True,
            True,
        ),
        (("unit-drift",), {}, False, False),
        (
            ("assertion",),
            {"verify_vikunja_id_present": {"side_effect": RuntimeError("reverify bug")}},
            True,
            False,
        ),
    ],
    ids=[
        "cron-enumeration-raises",
        "detect-cron-drift-raises",
        "baseline-error",
        "unit-enumeration-raises",
        "unit-dir-absent",
        "assertion-reverify-raises",
    ],
)
def test_failed_subscan_carries_its_findings_forward(
    tmp_path, carried_sources, overrides, unit_dir_present, scan_inability
):
    run = _carry_scan(tmp_path, overrides=overrides, unit_dir_present=unit_dir_present)

    _assert_sources_carried(run, carried_sources)
    if "assertion" in carried_sources:
        # Neither a false "now grounded" nor a duplicate "not grounded".
        assert not any("grounded" in t.lower() for t in run.titles)
    # `ok` still means "no errors": the unit-dir skip records none, so only the
    # held finding (via last-tick exit_status) makes that tick visible.
    assert run.summary["ok"] is (not unit_dir_present)
    # scan_inability (and so the preflight exit-2 contract) is unchanged: an
    # assertion failure or an absent unit dir still does not gate preflight.
    assert run.summary["_scan_inability"] is scan_inability
    assert run.last_tick["scan_inability"] is scan_inability


def test_assertion_new_pass_raise_still_runs_reverify_loop(tmp_path):
    """B2: the outstanding re-verify loop runs even when the new-assertion pass
    raised. A still-missing artifact is present this tick, so it is updated as
    today (last_seen refreshed) rather than carried or resolved."""
    run = _carry_scan(
        tmp_path,
        overrides={
            "_iter_new_assertions_positioned": {"side_effect": RuntimeError("read exploded")},
            "verify_vikunja_id_present": {"return_value": False},  # still missing
        },
    )

    assert run.mocks["verify_vikunja_id_present"].call_args_list[0].args == ("91",)
    assert any(e.startswith("assertion_scan:RuntimeError") for e in run.summary["errors"])
    fp, entry = run.seeded["assertion"]
    assert run.saved[fp]["last_seen"] == T0.isoformat()
    assert run.saved[fp]["first_seen"] == entry["first_seen"]
    assert _CLEARED_TITLE["assertion"] not in run.titles
    assert run.summary["carried_forward"] == 0
    assert run.summary["findings_held"] is False
    assert run.last_tick["exit_status"] == "success"  # nothing held, not inability


def test_assertion_new_pass_raise_carries_a_reappeared_artifact(tmp_path):
    """The new-pass raise leaves the assertion source incomplete, so even a
    re-verify that saw the artifact reappear may not resolve it this tick."""
    run = _carry_scan(
        tmp_path,
        overrides={
            "_iter_new_assertions_positioned": {"side_effect": RuntimeError("read exploded")},
        },
    )

    assert run.mocks["verify_vikunja_id_present"].call_count == 1
    assert run.summary["ok"] is False
    _assert_only_source_carried(run, "assertion")


def test_all_sources_complete_resolve_genuinely_gone_entries(tmp_path):
    """Control: every source completes, every seeded entry is genuinely gone,
    so each resolves exactly as before #1129."""
    run = _carry_scan(tmp_path)

    assert run.saved == {}
    assert sorted(run.titles) == sorted(_CLEARED_TITLE.values())
    assert run.summary["ok"] is True
    assert run.summary["carried_forward"] == 0
    assert run.summary["findings_held"] is False
    assert run.last_tick["exit_status"] == "success"
    assert run.last_tick["findings_held"] is False
    assert run.last_tick["carried_forward"] == 0


def test_dry_run_reports_zero_carried_forward(tmp_path):
    run = _carry_scan(
        tmp_path,
        overrides={"enumerate_live_crons": {"side_effect": CronEnumerationError("down")}},
        dry_run=True,
    )

    assert run.summary["carried_forward"] == 0
    assert run.summary["findings_held"] is False
    assert run.titles == []
    assert run.last_tick is None


def test_reconcile_fallback_reports_zero_carried_forward(tmp_path):
    run = _carry_scan(
        tmp_path,
        overrides={"enumerate_live_crons": {"side_effect": CronEnumerationError("down")}},
        extra_patches=[
            patch(
                "scripts.trust.run_trust_scan.state_mod.reconcile",
                side_effect=RuntimeError("reconcile exploded"),
            )
        ],
    )

    assert run.summary["carried_forward"] == 0
    assert run.summary["findings_held"] is False
    assert run.last_tick["carried_forward"] == 0
    assert run.last_tick["exit_status"] == "failure"  # alert_path_fault, as today


def test_baseline_error_tick_updates_a_still_missing_assertion_in_place(tmp_path):
    """#1130 (reverses #1129 F1): on a BaselineError tick the assertion source
    completes, so a still-missing outstanding assertion is updated in place —
    same key, same first_seen, last_seen refreshed, no alert either way. Only
    the cron entry is carried."""
    run = _carry_scan(
        tmp_path,
        overrides={
            "load_baseline": {"side_effect": BaselineError("baseline unreadable")},
            "verify_vikunja_id_present": {"return_value": False},  # still missing
        },
    )

    fp, entry = run.seeded["assertion"]
    assert run.saved[fp] == {**entry, "last_seen": T0.isoformat()}
    assert not any("grounded" in t.lower() for t in run.titles)
    cron_fp, cron_entry = run.seeded["cron"]
    assert run.saved[cron_fp] == cron_entry  # carried: cron source did not complete
    assert _CLEARED_TITLE["cron"] not in run.titles
    assert _CLEARED_TITLE["unit-drift"] in run.titles
    assert set(run.saved) == {fp, cron_fp}
    assert run.summary["carried_forward"] == 1  # the cron entry only
    assert run.summary["findings_held"] is True
    assert run.summary["_scan_inability"] is True
    assert run.last_tick["exit_status"] == "failure"


def _baseline_tick(isolated_paths, now, *, client=None, **baseline_patch):
    """One real tick with ``load_baseline`` patched by *baseline_patch*, the
    assertion's Vikunja artifact missing by default, and no deployed units."""
    from scripts.common.alert_bus.model import AlertResult

    state_path, watermark_path, assertions_dir = isolated_paths
    with patch("scripts.trust.run_trust_scan.load_baseline", **baseline_patch), patch(
        "scripts.trust.run_trust_scan.enumerate_live_crons", return_value=[_live_job()]
    ), patch(
        "scripts.trust.assertion_verifier._build_client",
        return_value=client if client is not None else _FakeVikunja(present=set()),
    ), patch("scripts.trust.alert_render.emit") as mock_emit:
        mock_emit.return_value = AlertResult(ok=True)
        summary = rts.run_scan(
            now=now,
            state_path=state_path,
            watermark_path=watermark_path,
            assertions_base_dir=assertions_dir,
            unit_deployed_dir=state_path.parent / "no-deployed-units",
        )
    saved = json.loads(state_path.read_text()) if state_path.exists() else {}
    return summary, [c.args[0].title for c in mock_emit.call_args_list], saved


_ASSERTION_77 = AssertionFinding(
    kind="artifact_missing",
    agent="main",
    artifact_kind="vikunja_task",
    artifact_id="77",
    claim="Created Vikunja reminder tasks",
)


def test_baseline_error_tick_alerts_new_assertions_and_advances_watermark(isolated_paths):
    """#1130 (reverses #1129 F1): a new artifact_missing record read on a
    BaselineError tick alerts on that tick, is saved under its unversioned key,
    and the watermark advances. The next good tick dedups it — no re-key."""
    state_path, watermark_path, assertions_dir = isolated_paths
    _vikunja_assertion(assertions_dir, ["77"])
    unversioned_fp = state_mod.fingerprint_finding(_ASSERTION_77, "")

    summary1, titles1, saved1 = _baseline_tick(
        isolated_paths, T0, side_effect=BaselineError("baseline unreadable")
    )
    assert titles1 == ["Completion claim not grounded: vikunja_task"]
    assert set(saved1) == {unversioned_fp}
    assert summary1["carried_forward"] == 0
    assert any(v > 0 for v in rts._load_watermark(watermark_path).values())

    summary2, titles2, saved2 = _baseline_tick(
        isolated_paths, T0 + timedelta(minutes=15), return_value=BASELINE
    )
    assert summary2["ok"] is True
    assert titles2 == []
    assert set(saved2) == {unversioned_fp}
    assert saved2[unversioned_fp]["first_seen"] == saved1[unversioned_fp]["first_seen"]


# --- #1130: assertion fingerprints do not depend on the cron baseline ---------


@pytest.mark.parametrize(
    "finding, expected",
    [
        (CronDriftFinding(kind="unapproved_present", name="c", agent_id="a"), "cron-hash"),
        (_ASSERTION_77, ""),
        (UnitDriftFinding(kind="content_drift", name="u.service", repo_source="u"), ""),
        (object(), ""),  # default-deny: a new finding type is unversioned
    ],
    ids=["cron", "assertion", "unit-drift", "unknown-type"],
)
def test_only_cron_findings_are_baseline_versioned(finding, expected):
    assert rts._finding_baseline_hash(finding, "cron-hash") == expected


def test_good_tick_stores_assertion_under_unversioned_key(isolated_paths):
    _state_path, _watermark_path, assertions_dir = isolated_paths
    _vikunja_assertion(assertions_dir, ["77"])

    _summary, titles, saved = _baseline_tick(isolated_paths, T0, return_value=BASELINE)

    assert titles == ["Completion claim not grounded: vikunja_task"]
    assert set(saved) == {state_mod.fingerprint_finding(_ASSERTION_77, "")}


BASELINE_B = [
    *BASELINE,
    ApprovedCron(
        name="escalation-daily",
        agent_id="felix-admin",
        schedule_expr="0 9 * * *",
        tz="America/New_York",
        purpose="test",
        approved_by="kent",
        approved_at="2026-11-23",
    ),
]


def test_baseline_edit_does_not_rekey_an_outstanding_assertion(isolated_paths):
    """#1130 repro: two ticks through the runner. Tick 1 under baseline A
    creates the artifact_missing entry; tick 2 under an edited baseline B (one
    more approved cron), artifact still missing, must neither resolve it ("now
    grounded") nor re-alert it ("not grounded"): same key, same first_seen."""
    _state_path, _watermark_path, assertions_dir = isolated_paths
    _vikunja_assertion(assertions_dir, ["91"])
    assert baseline_hash(BASELINE_B) != baseline_hash(BASELINE)

    _s1, titles1, saved1 = _baseline_tick(isolated_paths, T0, return_value=BASELINE)
    assert titles1 == ["Completion claim not grounded: vikunja_task"]
    assertion_keys1 = {k for k, e in saved1.items() if e.get("source") == "assertion"}
    assert len(assertion_keys1) == 1

    summary2, titles2, saved2 = _baseline_tick(
        isolated_paths, T0 + timedelta(hours=1), return_value=BASELINE_B
    )
    assert summary2["errors"] == []
    assert not any("grounded" in t.lower() for t in titles2)
    assert any("escalation-daily" in t for t in titles2)  # the edit IS re-evaluated for crons
    assertion_keys2 = {k for k, e in saved2.items() if e.get("source") == "assertion"}
    assert assertion_keys2 == assertion_keys1
    (key,) = assertion_keys1
    assert saved2[key]["first_seen"] == saved1[key]["first_seen"]
