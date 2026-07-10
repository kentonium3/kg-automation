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
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.trust import run_trust_scan as rts
from scripts.trust.cron_baseline import ApprovedCron
from scripts.trust.cron_drift_detector import CronEnumerationError

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
        "scripts.trust.run_trust_scan._iter_new_assertions",
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
        "alerts_emitted",
        "errors",
    }
    assert exit_code == 0
