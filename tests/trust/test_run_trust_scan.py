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
        "alerts_emitted",
        "errors",
    }
    assert exit_code == 0
