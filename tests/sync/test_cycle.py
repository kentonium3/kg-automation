"""Tests for scripts/sync/cycle.py (WP04 / T017).

End-to-end cycle tests with mocked Vikunja HTTP + mocked openclaw subprocess.
Covers steady-state happy path, every failure-injection boundary, the
bootstrap path, the dry-run path, Phase 5b deletion-cleanup, project rename
detection, and FR-012 abort semantics.

Fixture migration note (WP04): FetchedDelta → FetchedSnapshot. The mock
HTTP responses now feed `fetch_full_poll` which makes GET /tasks/all then
GET /projects then (best-effort) GET /info. All tests include 2-3 mock
responses to match this call order.
"""
from __future__ import annotations

import io
import json
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.common import vikunja_refs
from scripts.sync import cycle as cy
from scripts.sync import state as st
from scripts.sync.send_whatsapp import SendResult


NOW_UTC = datetime(2026, 6, 4, 19, 25, 30, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _resp(payload, *, status: int = 200):
    body = json.dumps(payload).encode("utf-8") if payload is not None else b""
    resp = MagicMock(name="response")
    resp.status = status
    resp.read = MagicMock(return_value=body)
    cm = MagicMock(name="cm")
    cm.__enter__ = MagicMock(return_value=resp)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


def _http_error(code: int = 500, body: bytes = b'{"message":"boom"}'):
    return urllib.error.HTTPError(
        url="http://test/",
        code=code,
        msg="Server Error",
        hdrs=None,
        fp=io.BytesIO(body),
    )


@pytest.fixture
def mock_urlopen(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr("scripts.sync.http.urllib.request.urlopen", mock)
    return mock


@pytest.fixture
def env(tmp_path) -> tuple[Path, Path]:
    """Pre-seed state and secrets directories. Returns (state_dir, secrets_dir)."""
    state_dir = tmp_path / "state"
    secrets_dir = tmp_path / "secrets"
    state_dir.mkdir()
    secrets_dir.mkdir()
    (secrets_dir / "vikunja-api").write_text("test-token")
    # Seed an initial freshness pointer (steady-state cycles require it).
    st.write_freshness(
        state_dir,
        st.FreshnessPointer(
            last_updated_utc="2026-06-04T19:20:00Z",
            layers={
                cy.LAYER_STATUS_AND_TASK: st.FreshnessLayer(
                    last_polled_utc="2026-06-04T19:20:00Z"
                ),
            },
        ),
    )
    return state_dir, secrets_dir


def _config(state_dir: Path, secrets_dir: Path, *, dry_run: bool = False) -> cy.CycleConfig:
    return cy.CycleConfig(
        state_dir=state_dir,
        secrets_dir=secrets_dir,
        api_base_url="http://test/api/v1/",
        cadence_seconds=300,
        whatsapp_recipient="+15551234567",
        dry_run=dry_run,
    )


def _ok_send():
    mock = MagicMock()
    mock.return_value = SendResult(success=True, exit_code=0, stderr=None)
    return mock


# fetch_full_poll calls: GET /tasks/all, GET /projects, GET /info (best-effort)
# For tests that don't care about projects, we still need to provide the
# /projects response since it's always called.
def _full_poll_responses(tasks, *, projects=None, version="0.24.6"):
    """Return the 3 mock HTTP responses fetch_full_poll expects."""
    if projects is None:
        projects = []
    return [
        _resp(tasks),           # GET /tasks/all
        _resp(projects),        # GET /projects
        _resp({"version": version}),  # GET /info
    ]


# ===========================================================================
# Group 1 — Steady-state happy path
# ===========================================================================


class TestSteadyStateHappy:
    def test_zero_changes_exit_0(self, env, mock_urlopen):
        state_dir, secrets_dir = env
        # /tasks/all (empty) + /projects (empty) + /info.
        mock_urlopen.side_effect = _full_poll_responses([])
        result = cy.run_cycle(_config(state_dir, secrets_dir), now_utc=NOW_UTC)
        assert result.exit_code == 0
        assert result.success is True
        # Freshness advanced to NOW.
        fresh = st.read_freshness(state_dir)
        assert fresh.layers[cy.LAYER_STATUS_AND_TASK].last_polled_utc.startswith("2026-06-04T19:25:30")
        # last-tick.json written with success — schema_version 2 + layer_summary.
        last = json.loads((state_dir / st.LAST_TICK_FILENAME).read_text())
        assert last["cycle_error"] is None
        assert last["events_emitted"] == {"auto_resolved": 0, "unsafe_to_auto_resolve": 0}
        assert last["schema_version"] == st.HEALTH_SCHEMA_VERSION
        assert "layer_summary" in last
        assert "layer_pointers" not in last

    def test_one_unsafe_delivered(self, env, mock_urlopen):
        state_dir, secrets_dir = env
        # Seed task 14 in cache with old title.
        st.write_task_cache(
            state_dir,
            st.TaskCacheRecord(
                last_updated_utc="2026-06-04T18:00:00Z",
                tasks={
                    "14": st.TaskCacheEntry(
                        vikunja_task_id=14,
                        fields={"title": "OldTitle", "project_id": 13},
                        vikunja_updated_at="2026-06-04T18:00:00Z",
                        felix_last_observed_at="2026-06-04T17:00:00Z",
                    ),
                },
            ),
        )
        # Seed project 13 in project cache.
        st.write_project_cache(
            state_dir,
            st.ProjectCacheRecord(
                last_refreshed_utc="2026-06-04T18:00:00Z",
                projects={"13": st.ProjectCacheEntry(title="P", is_archived=False)},
            ),
        )
        mock_urlopen.side_effect = _full_poll_responses(
            tasks=[{
                "id": 14,
                "title": "NewTitle",
                "project_id": 13,
                "updated": "2026-06-04T19:24:00Z",
            }],
            projects=[{"id": 13, "title": "P", "is_archived": False}],
        )
        send = _ok_send()
        result = cy.run_cycle(
            _config(state_dir, secrets_dir), send_callable=send, now_utc=NOW_UTC
        )
        assert result.exit_code == 0
        assert send.call_count == 1
        # Conflict event written.
        events_file = state_dir / st.CONFLICT_EVENTS_FILENAME
        assert events_file.exists()
        row = json.loads(events_file.read_text().splitlines()[0])
        assert row["delivery_status"] == "delivered"
        # Cache updated with new title.
        cache = st.read_task_cache(state_dir)
        assert cache.tasks["14"].fields["title"] == "NewTitle"

    def test_auto_resolved_does_not_invoke_send(self, env, mock_urlopen):
        # WP04 seam: felix:ignore is now resolved by id through the reference
        # registry. It is unprovisioned in the shipped registry today (value:
        # null), so inject a provisioned registry (id 1, matching the fixture
        # label id below) to exercise the label-override → auto_resolved path
        # end-to-end. Cleared in the finally so no state leaks to sibling tests.
        vikunja_refs.set_registry_for_test(
            {
                "schema_version": 1,
                "source_of_truth": "test",
                "last_verified_utc": "2026-07-15T00:00:00Z",
                "projects": [],
                "labels": [
                    {
                        "name": "felix:ignore",
                        "selector": {"kind": "label", "value": 1},
                        "title": "felix:ignore",
                        "owner_token": "kent",
                    }
                ],
                "private_projects": [],
            }
        )
        try:
            self._run_auto_resolved_does_not_invoke_send(env, mock_urlopen)
        finally:
            vikunja_refs.set_registry_for_test(None)

    def _run_auto_resolved_does_not_invoke_send(self, env, mock_urlopen):
        state_dir, secrets_dir = env
        st.write_task_cache(
            state_dir,
            st.TaskCacheRecord(
                last_updated_utc="2026-06-04T18:00:00Z",
                tasks={
                    "14": st.TaskCacheEntry(
                        vikunja_task_id=14,
                        fields={"title": "OldTitle", "labels": []},
                        vikunja_updated_at="2026-06-04T18:00:00Z",
                        felix_last_observed_at="2026-06-04T17:00:00Z",
                    ),
                },
            ),
        )
        # Task labeled felix:ignore → UC-4 inverts to auto_resolved.
        mock_urlopen.side_effect = _full_poll_responses(
            tasks=[{
                "id": 14,
                "title": "NewTitle",
                "labels": [{"id": 1, "title": "felix:ignore"}],
                "updated": "2026-06-04T19:24:00Z",
            }]
        )
        send = _ok_send()
        result = cy.run_cycle(
            _config(state_dir, secrets_dir), send_callable=send, now_utc=NOW_UTC
        )
        assert result.exit_code == 0
        assert send.call_count == 0


# ===========================================================================
# Group 2 — Per-phase failure injection
# ===========================================================================


class TestFailureInjection:
    def test_missing_freshness_exit_1(self, tmp_path, mock_urlopen):
        # No state seeded → read_freshness raises OSError.
        state_dir = tmp_path / "state"
        secrets_dir = tmp_path / "secrets"
        state_dir.mkdir()
        secrets_dir.mkdir()
        (secrets_dir / "vikunja-api").write_text("tok")
        result = cy.run_cycle(_config(state_dir, secrets_dir), now_utc=NOW_UTC)
        assert result.exit_code == 1
        assert result.cycle_error is not None
        # Failure stream populated.
        errors_path = state_dir / st.LAST_TICK_ERRORS_FILENAME
        assert errors_path.exists()
        err = json.loads(errors_path.read_text().splitlines()[0])
        assert err["phase"] == "preamble"
        assert err["layer_pointers_unchanged"] is True

    def test_phase_1_fetch_failure_exit_1(self, env, mock_urlopen):
        state_dir, secrets_dir = env
        mock_urlopen.side_effect = _http_error(503, b'{"message":"down"}')
        result = cy.run_cycle(_config(state_dir, secrets_dir), now_utc=NOW_UTC)
        assert result.exit_code == 1
        assert "step 1" in result.cycle_error
        # Freshness pointer NOT advanced.
        fresh = st.read_freshness(state_dir)
        assert fresh.layers[cy.LAYER_STATUS_AND_TASK].last_polled_utc == "2026-06-04T19:20:00Z"
        # Error stream appended.
        err_file = state_dir / st.LAST_TICK_ERRORS_FILENAME
        err = json.loads(err_file.read_text().splitlines()[0])
        assert err["phase"] == "fetch"
        assert err["layer_pointers_unchanged"] is True

    def test_phase_4_emit_failure_exit_2(self, env, mock_urlopen, monkeypatch):
        state_dir, secrets_dir = env
        st.write_task_cache(
            state_dir,
            st.TaskCacheRecord(
                last_updated_utc="2026-06-04T18:00:00Z",
                tasks={
                    "14": st.TaskCacheEntry(
                        vikunja_task_id=14,
                        fields={"title": "OldTitle"},
                        vikunja_updated_at="2026-06-04T18:00:00Z",
                        felix_last_observed_at="2026-06-04T17:00:00Z",
                    ),
                },
            ),
        )
        mock_urlopen.side_effect = _full_poll_responses(
            tasks=[{"id": 14, "title": "NewTitle", "updated": "2026-06-04T19:24:00Z"}]
        )
        # Force emit failure.
        def _boom(*a, **k):
            raise OSError("simulated emit failure")
        monkeypatch.setattr("scripts.sync.cycle.emit_events", _boom)
        result = cy.run_cycle(_config(state_dir, secrets_dir), now_utc=NOW_UTC)
        assert result.exit_code == 2
        assert "step 4" in result.cycle_error
        # Freshness pointer NOT advanced.
        fresh = st.read_freshness(state_dir)
        assert fresh.layers[cy.LAYER_STATUS_AND_TASK].last_polled_utc == "2026-06-04T19:20:00Z"


# ===========================================================================
# Group 3 — Phase 6 write order
# ===========================================================================


class TestPhase6WriteOrder:
    def test_freshness_second_to_last_last_tick_last(self, env, mock_urlopen):
        """Phase 6 invariant: last-tick.json IS the success marker.

        Freshness must be written before last-tick (NFR contract).
        """
        state_dir, secrets_dir = env
        mock_urlopen.side_effect = _full_poll_responses([])
        result = cy.run_cycle(_config(state_dir, secrets_dir), now_utc=NOW_UTC)
        assert result.exit_code == 0
        # Both files exist post-cycle.
        assert (state_dir / st.FRESHNESS_FILENAME).exists()
        assert (state_dir / st.LAST_TICK_FILENAME).exists()
        # mtime: freshness should be written before last-tick.
        # On fast machines mtimes may equal; assert ≤ rather than strict <.
        fresh_mtime = (state_dir / st.FRESHNESS_FILENAME).stat().st_mtime_ns
        last_mtime = (state_dir / st.LAST_TICK_FILENAME).stat().st_mtime_ns
        assert fresh_mtime <= last_mtime


# ===========================================================================
# Group 4 — Bootstrap path
# ===========================================================================


class TestBootstrap:
    def test_empty_dir_populates_cache(self, tmp_path, mock_urlopen):
        state_dir = tmp_path / "state"
        secrets_dir = tmp_path / "secrets"
        state_dir.mkdir()
        secrets_dir.mkdir()
        (secrets_dir / "vikunja-api").write_text("tok")
        mock_urlopen.side_effect = _full_poll_responses(
            tasks=[
                {"id": 14, "title": "A", "project_id": 13, "updated": "2026-06-04T18:00:00Z"},
                {"id": 15, "title": "B", "project_id": 13, "updated": "2026-06-04T18:00:00Z"},
            ],
            projects=[{"id": 13, "title": "Habits", "is_archived": False}],
        )
        result = cy.run_bootstrap(_config(state_dir, secrets_dir), now_utc=NOW_UTC)
        assert result.exit_code == 0
        # All 4 state files exist; conflict-events.jsonl does NOT.
        assert (state_dir / st.FRESHNESS_FILENAME).exists()
        assert (state_dir / st.TASK_CACHE_FILENAME).exists()
        assert (state_dir / st.PROJECT_CACHE_FILENAME).exists()
        assert (state_dir / st.LAST_TICK_FILENAME).exists()
        assert not (state_dir / st.CONFLICT_EVENTS_FILENAME).exists()
        # Cache populated.
        cache = st.read_task_cache(state_dir)
        assert set(cache.tasks.keys()) == {"14", "15"}
        # last-tick.json uses schema_version 2 + layer_summary.
        last = json.loads((state_dir / st.LAST_TICK_FILENAME).read_text())
        assert last["schema_version"] == st.HEALTH_SCHEMA_VERSION
        assert "layer_summary" in last
        assert last["layer_summary"]["task_layer"]["added"] == 2

    def test_bootstrap_does_not_emit_events(self, tmp_path, mock_urlopen):
        state_dir = tmp_path / "state"
        secrets_dir = tmp_path / "secrets"
        state_dir.mkdir()
        secrets_dir.mkdir()
        (secrets_dir / "vikunja-api").write_text("tok")
        mock_urlopen.side_effect = _full_poll_responses(
            tasks=[{"id": 14, "title": "x", "updated": "2026-06-04T18:00:00Z"}]
        )
        result = cy.run_bootstrap(_config(state_dir, secrets_dir), now_utc=NOW_UTC)
        assert result.exit_code == 0
        # No JSONL written.
        assert not (state_dir / st.CONFLICT_EVENTS_FILENAME).exists()
        assert result.events_emitted == {"auto_resolved": 0, "unsafe_to_auto_resolve": 0}


# ===========================================================================
# Group 5 — Dry-run path
# ===========================================================================


class TestDryRun:
    def test_no_state_writes_in_dry_run(self, env, mock_urlopen, capsys):
        state_dir, secrets_dir = env
        # Capture pre-cycle freshness mtime.
        fresh_path = state_dir / st.FRESHNESS_FILENAME
        before_mtime = fresh_path.stat().st_mtime_ns
        mock_urlopen.side_effect = _full_poll_responses([])
        send = _ok_send()
        result = cy.run_cycle(
            _config(state_dir, secrets_dir, dry_run=True),
            send_callable=send,
            now_utc=NOW_UTC,
        )
        assert result.exit_code == 0
        # Freshness file untouched (mtime unchanged).
        after_mtime = fresh_path.stat().st_mtime_ns
        assert after_mtime == before_mtime
        # No conflict-events.jsonl, no last-tick.json.
        assert not (state_dir / st.CONFLICT_EVENTS_FILENAME).exists()
        assert not (state_dir / st.LAST_TICK_FILENAME).exists()
        # Send NOT invoked (no divergences anyway, but the principle holds).
        assert send.call_count == 0
        # Stderr summary printed.
        assert "[sync DRY-RUN]" in capsys.readouterr().err


# ===========================================================================
# Group 6 — Cycle 2 sees clean state after successful cycle 1
# ===========================================================================


class TestCycleReplay:
    def test_cycle_2_after_cycle_1_no_redundant_events(self, env, mock_urlopen):
        """After cycle 1 updates the cache, cycle 2 with identical Vikunja
        state sees the cache aligned and produces no new events."""
        state_dir, secrets_dir = env
        st.write_task_cache(
            state_dir,
            st.TaskCacheRecord(
                last_updated_utc="2026-06-04T18:00:00Z",
                tasks={
                    "14": st.TaskCacheEntry(
                        vikunja_task_id=14,
                        fields={"title": "OldTitle"},
                        vikunja_updated_at="2026-06-04T18:00:00Z",
                        felix_last_observed_at="2026-06-04T17:00:00Z",
                    ),
                },
            ),
        )
        # Cycle 1 sees divergence and updates cache.
        # Cycle 2 sees the same task returning the same value — no divergence.
        mock_urlopen.side_effect = [
            *_full_poll_responses(
                tasks=[{"id": 14, "title": "NewTitle", "updated": "2026-06-04T19:24:00Z"}]
            ),
            *_full_poll_responses(
                tasks=[{"id": 14, "title": "NewTitle", "updated": "2026-06-04T19:24:00Z"}]
            ),
        ]
        send = _ok_send()
        cy.run_cycle(_config(state_dir, secrets_dir), send_callable=send, now_utc=NOW_UTC)
        cy.run_cycle(_config(state_dir, secrets_dir), send_callable=send, now_utc=NOW_UTC)
        # Only one row in the JSONL — cycle 2 saw cache-aligned state.
        rows = [
            json.loads(line)
            for line in (state_dir / st.CONFLICT_EVENTS_FILENAME).read_text().splitlines()
        ]
        assert len(rows) == 1
        assert send.call_count == 1


# ===========================================================================
# Group 7 — Phase 5b: Task deletion happy path (new in WP04)
# ===========================================================================


class TestPhase5bDeletion:
    def test_deleted_task_triggers_history_log_and_cache_shrinks(
        self, env, mock_urlopen, tmp_path
    ):
        """Phase 5b happy path: a task in the cache but absent from the
        snapshot gets a task_deleted event in history.jsonl and is removed
        from the cache after Phase 6."""
        state_dir, secrets_dir = env

        # Seed two tasks in cache — task 99 will "disappear" from Vikunja.
        st.write_task_cache(
            state_dir,
            st.TaskCacheRecord(
                last_updated_utc="2026-06-04T18:00:00Z",
                tasks={
                    "14": st.TaskCacheEntry(
                        vikunja_task_id=14,
                        fields={"title": "StayTask"},
                        vikunja_updated_at="2026-06-04T18:00:00Z",
                        felix_last_observed_at="2026-06-04T17:00:00Z",
                    ),
                    "99": st.TaskCacheEntry(
                        vikunja_task_id=99,
                        fields={"title": "GoneTask"},
                        vikunja_updated_at="2026-06-04T18:00:00Z",
                        felix_last_observed_at="2026-06-04T17:00:00Z",
                    ),
                },
            ),
        )

        # Snapshot returns only task 14 — task 99 is deleted.
        mock_urlopen.side_effect = _full_poll_responses(
            tasks=[{"id": 14, "title": "StayTask", "updated": "2026-06-04T18:00:00Z"}]
        )

        # Redirect Phase 5b paths to tmp_path so we don't write to the real repo.
        history_path = tmp_path / "habits-history.jsonl"
        schedule_path = tmp_path / "phase3-schedule.yaml"

        with patch.object(cy, "HABITS_HISTORY_PATH", history_path), \
             patch.object(cy, "SCHEDULE_YAML_PATH", schedule_path):
            result = cy.run_cycle(_config(state_dir, secrets_dir), now_utc=NOW_UTC)

        assert result.exit_code == 0

        # Cache shrinks: task 99 is gone; task 14 remains.
        cache = st.read_task_cache(state_dir)
        assert "14" in cache.tasks
        assert "99" not in cache.tasks

        # history.jsonl got a task_deleted event for task 99.
        assert history_path.exists()
        lines = history_path.read_text().splitlines()
        assert len(lines) == 1
        event = json.loads(lines[0])
        assert event["event_type"] == "task_deleted"
        assert event["task_id"] == 99
        assert event["title"] == "GoneTask"

    def test_deleted_task_history_log_failure_skips_but_continues(
        self, env, mock_urlopen, tmp_path, capsys
    ):
        """If append_task_deleted_event fails, the error is logged and the
        cycle continues to completion (not a cycle-abort).

        The snapshot must be non-empty (returns task 14) so FR-012 is not
        triggered. Task 99 is in cache but absent from the snapshot → deleted.
        """
        state_dir, secrets_dir = env

        st.write_task_cache(
            state_dir,
            st.TaskCacheRecord(
                last_updated_utc="2026-06-04T18:00:00Z",
                tasks={
                    "14": st.TaskCacheEntry(
                        vikunja_task_id=14,
                        fields={"title": "StayTask"},
                        vikunja_updated_at="2026-06-04T18:00:00Z",
                        felix_last_observed_at="2026-06-04T17:00:00Z",
                    ),
                    "99": st.TaskCacheEntry(
                        vikunja_task_id=99,
                        fields={"title": "GoneTask"},
                        vikunja_updated_at="2026-06-04T18:00:00Z",
                        felix_last_observed_at="2026-06-04T17:00:00Z",
                    ),
                },
            ),
        )

        # Snapshot returns only task 14 — task 99 is deleted.
        # Cache is non-empty (2 tasks) but snapshot returns 1, so FR-012 won't fire.
        mock_urlopen.side_effect = _full_poll_responses(
            tasks=[{"id": 14, "title": "StayTask", "updated": "2026-06-04T18:00:00Z"}]
        )

        history_path = tmp_path / "habits-history.jsonl"
        schedule_path = tmp_path / "phase3-schedule.yaml"

        def _fail_append(*args, **kwargs):
            raise OSError("disk full simulation")

        with patch.object(cy, "HABITS_HISTORY_PATH", history_path), \
             patch.object(cy, "SCHEDULE_YAML_PATH", schedule_path), \
             patch("scripts.sync.cycle.append_task_deleted_event", side_effect=_fail_append):
            result = cy.run_cycle(_config(state_dir, secrets_dir), now_utc=NOW_UTC)

        # Cycle still succeeds — deletion failure is non-fatal.
        assert result.exit_code == 0
        # Warning written to stderr.
        stderr = capsys.readouterr().err
        assert "append_task_deleted_event failed" in stderr

        # Error logged to last-tick.errors.jsonl.
        err_path = state_dir / st.LAST_TICK_ERRORS_FILENAME
        assert err_path.exists()
        err_lines = err_path.read_text().splitlines()
        assert any(
            json.loads(line)["phase"] == "cleanup_history_log"
            for line in err_lines
        )


# ===========================================================================
# Group 8 — Project rename event in layer_summary (new in WP04)
# ===========================================================================


class TestProjectLayerSummary:
    def test_project_rename_reflected_in_layer_summary(self, env, mock_urlopen):
        """When a project is renamed, layer_summary.project_layer.updated >= 1
        in the written last-tick.json."""
        state_dir, secrets_dir = env

        # Seed project 13 with old title.
        st.write_project_cache(
            state_dir,
            st.ProjectCacheRecord(
                last_refreshed_utc="2026-06-04T18:00:00Z",
                projects={"13": st.ProjectCacheEntry(title="OldName", is_archived=False)},
            ),
        )

        # Snapshot returns project 13 with new title.
        mock_urlopen.side_effect = _full_poll_responses(
            tasks=[],
            projects=[{"id": 13, "title": "NewName", "is_archived": False}],
        )

        result = cy.run_cycle(_config(state_dir, secrets_dir), now_utc=NOW_UTC)
        assert result.exit_code == 0

        last = json.loads((state_dir / st.LAST_TICK_FILENAME).read_text())
        project_layer = last["layer_summary"]["project_layer"]
        assert project_layer["updated"] >= 1, (
            f"Expected project_layer.updated >= 1 (rename), got: {project_layer}"
        )

        # Project cache updated with new title (canonical replacement).
        pc = st.read_project_cache(state_dir)
        assert pc.projects["13"].title == "NewName"

    def test_task_added_in_layer_summary(self, env, mock_urlopen):
        """A new task in the snapshot appears in layer_summary.task_layer.added."""
        state_dir, secrets_dir = env
        # Empty task cache — task 42 is new.
        mock_urlopen.side_effect = _full_poll_responses(
            tasks=[{"id": 42, "title": "NewHabit", "updated": "2026-06-04T18:00:00Z"}]
        )
        result = cy.run_cycle(_config(state_dir, secrets_dir), now_utc=NOW_UTC)
        assert result.exit_code == 0

        last = json.loads((state_dir / st.LAST_TICK_FILENAME).read_text())
        task_layer = last["layer_summary"]["task_layer"]
        assert task_layer["added"] == 1


# ===========================================================================
# Group 9 — FR-012 abort (new in WP04)
# ===========================================================================


class TestFR012Abort:
    def test_empty_tasks_when_cache_nonempty_aborts_cycle(self, env, mock_urlopen):
        """FR-012: if /tasks/all returns [] but the cache is non-empty, the
        cycle aborts (exit_code=1) without writing partial state."""
        state_dir, secrets_dir = env

        # Seed a non-empty task cache.
        st.write_task_cache(
            state_dir,
            st.TaskCacheRecord(
                last_updated_utc="2026-06-04T18:00:00Z",
                tasks={
                    "14": st.TaskCacheEntry(
                        vikunja_task_id=14,
                        fields={"title": "MyHabit"},
                        vikunja_updated_at="2026-06-04T18:00:00Z",
                        felix_last_observed_at="2026-06-04T17:00:00Z",
                    ),
                },
            ),
        )

        # Vikunja returns empty task list (FR-012 scenario).
        mock_urlopen.side_effect = [_resp([])]  # GET /tasks/all → []

        result = cy.run_cycle(_config(state_dir, secrets_dir), now_utc=NOW_UTC)

        # Cycle aborts (exit_code=1 — pre-emit, pointer unchanged).
        assert result.exit_code == 1
        assert result.success is False
        assert "empty_response_when_cache_nonzero" in (result.cycle_error or "")

        # Freshness pointer NOT advanced.
        fresh = st.read_freshness(state_dir)
        assert fresh.layers[cy.LAYER_STATUS_AND_TASK].last_polled_utc == "2026-06-04T19:20:00Z"

        # Cache unchanged — still has task 14.
        cache = st.read_task_cache(state_dir)
        assert "14" in cache.tasks

        # No last-tick.json written (no successful cycle).
        assert not (state_dir / st.LAST_TICK_FILENAME).exists()

    def test_auth_failure_aborts_cycle_exit_1(self, env, mock_urlopen):
        """HTTP 401 on /tasks/all → cycle aborts with exit_code=1."""
        state_dir, secrets_dir = env
        mock_urlopen.side_effect = _http_error(401, b'{"message":"unauthorized"}')
        result = cy.run_cycle(_config(state_dir, secrets_dir), now_utc=NOW_UTC)
        assert result.exit_code == 1
        assert "step 1" in result.cycle_error

        err_file = state_dir / st.LAST_TICK_ERRORS_FILENAME
        err = json.loads(err_file.read_text().splitlines()[0])
        assert err["phase"] == "fetch"

    def test_5xx_aborts_cycle_exit_1(self, env, mock_urlopen):
        """HTTP 503 on /tasks/all → cycle aborts with exit_code=1."""
        state_dir, secrets_dir = env
        mock_urlopen.side_effect = _http_error(503)
        result = cy.run_cycle(_config(state_dir, secrets_dir), now_utc=NOW_UTC)
        assert result.exit_code == 1
        assert "step 1" in (result.cycle_error or "")
