"""Tests for scripts/sync/cycle.py (WP04 / T017).

End-to-end cycle tests with mocked Vikunja HTTP + mocked openclaw subprocess.
Covers steady-state happy path, every failure-injection boundary, the
bootstrap path, the dry-run path, Phase 5b deletion-cleanup, project rename
detection, and FR-012 abort semantics.

Fixture migration note (WP04): FetchedDelta → FetchedSnapshot. The mock
HTTP responses now feed `fetch_full_poll`, which (post-#853) enumerates
project-scoped: GET /projects FIRST, then GET /projects/{id}/tasks per
project, then (best-effort) GET /info. The `_full_poll_responses` helper
builds the responses in that order — see its docstring.
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
    """Patch ``urllib.request.urlopen`` as seen by ``VikunjaClient``.

    WP02 migration note: sync now routes every Vikunja call through
    ``VikunjaClient`` instead of the retired ``scripts/sync/http.py`` urllib
    wrapper, so the patch target moved to
    ``scripts.common.vikunja_client.urllib...``.
    """
    mock = MagicMock()
    monkeypatch.setattr("scripts.common.vikunja_client.urllib.request.urlopen", mock)
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


@pytest.fixture(autouse=True)
def seam_token(tmp_path, monkeypatch):
    """Route sync's token resolution (WP04) through the WP01 config seam.

    ``run_cycle``/``run_bootstrap`` now resolve the Vikunja token via
    ``get_vikunja_token_path()`` (the ``VIKUNJA_TOKEN_PATH`` override → kent
    default) rather than ``config.secrets_dir / "vikunja-api"``. Point the
    override at a seeded token file so every cycle test's preamble succeeds by
    default; the failure-classification tests re-point it at a missing path.
    """
    token_file = tmp_path / "seam-vikunja-token"
    token_file.write_text("seam-test-token")
    monkeypatch.setenv("VIKUNJA_TOKEN_PATH", str(token_file))
    return token_file


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


# fetch_full_poll is project-scoped (post-#853): GET /projects FIRST, then
# GET /projects/{id}/tasks per project, then GET /info (best-effort).
_SYNTHETIC_PID = 1  # home project for fixture tasks that omit a project_id


def _full_poll_responses(tasks, *, projects=None, version="0.24.6"):
    """Build the mock HTTP responses fetch_full_poll expects, project-scoped.

    Order: GET /projects, then one GET /projects/{id}/tasks page per project
    (tasks grouped by project_id, each a single short page), then GET /info.

    A task is only enumerated if its project is returned by GET /projects
    (the #853 project-scoped model). To keep legacy fixtures working, tasks
    are normalised so each has a project_id (falling back to a synthetic
    project) and the GET /projects response is augmented with any project_id
    a task references but that ``projects`` did not list.
    """
    if projects is None:
        projects = []
    norm_tasks: list[dict] = []
    for task in tasks:
        task = dict(task)
        task.setdefault("project_id", _SYNTHETIC_PID)
        norm_tasks.append(task)

    proj_list = [dict(p) for p in projects]
    known = {p.get("id") for p in proj_list}
    for task in norm_tasks:
        pid = task["project_id"]
        if pid not in known:
            proj_list.append({"id": pid, "title": f"Project {pid}", "is_archived": False})
            known.add(pid)

    responses = [_resp(proj_list)]  # GET /projects (fetched FIRST)
    for proj in proj_list:
        pid = proj.get("id")
        page = [t for t in norm_tasks if t.get("project_id") == pid]
        responses.append(_resp(page))  # GET /projects/{pid}/tasks
    responses.append(_resp({"version": version}))  # GET /info
    return responses


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
        assert fresh.layers[cy.LAYER_STATUS_AND_TASK].last_polled_utc.startswith(
            "2026-06-04T19:25:30"
        )
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

    def test_token_resolution_failure_classified_as_preamble(
        self, env, mock_urlopen, monkeypatch
    ):
        """NFR-001: a token-path failure must land in sync's EXISTING preamble
        outcome, unchanged from HEAD.

        The WP01 seam (``get_vikunja_token_path``) fails loud with
        ``VikunjaConfigError`` — a ``RuntimeError`` subclass, NOT an
        ``OSError`` — on a missing/unreadable token. ``run_cycle`` must catch
        that typed error and map it into the same ``phase="preamble"``,
        ``exit_code=1``, populated-``cycle_error`` classification HEAD produced
        for an ``OSError`` token-read failure. A token failure must not change
        sync's error taxonomy.
        """
        state_dir, secrets_dir = env
        # Re-point the seam at a nonexistent token file → get_vikunja_token_path()
        # raises VikunjaConfigError during the preamble, BEFORE the freshness read.
        monkeypatch.setenv("VIKUNJA_TOKEN_PATH", str(state_dir / "no-such-token"))
        result = cy.run_cycle(_config(state_dir, secrets_dir), now_utc=NOW_UTC)
        assert result.success is False
        assert result.exit_code == 1
        assert result.cycle_error is not None
        # Failure stream records phase="preamble" with pointers unchanged —
        # byte-for-byte the same classification as the OSError path (see
        # test_missing_freshness_exit_1).
        errors_path = state_dir / st.LAST_TICK_ERRORS_FILENAME
        assert errors_path.exists()
        err = json.loads(errors_path.read_text().splitlines()[0])
        assert err["phase"] == "preamble"
        assert err["layer_pointers_unchanged"] is True
        # Freshness pointer NOT advanced (safe-state, exit_code==1).
        fresh = st.read_freshness(state_dir)
        assert fresh.layers[cy.LAYER_STATUS_AND_TASK].last_polled_utc == "2026-06-04T19:20:00Z"

    def test_bootstrap_token_resolution_failure_classified_as_preamble(
        self, tmp_path, mock_urlopen, monkeypatch
    ):
        """NFR-001 (bootstrap mirror): a token-path failure maps into the
        existing ``bootstrap-preamble`` outcome (exit_code=1), never leaking a
        raw ``VikunjaConfigError``."""
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        monkeypatch.setenv("VIKUNJA_TOKEN_PATH", str(tmp_path / "no-such-token"))
        result = cy.run_bootstrap(
            _config(state_dir, tmp_path / "secrets"), now_utc=NOW_UTC
        )
        assert result.success is False
        assert result.exit_code == 1
        assert result.cycle_error is not None
        errors_path = state_dir / st.LAST_TICK_ERRORS_FILENAME
        err = json.loads(errors_path.read_text().splitlines()[0])
        assert err["phase"] == "bootstrap-preamble"

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
                        fields={"title": "OldTitle", "project_id": 13},
                        vikunja_updated_at="2026-06-04T18:00:00Z",
                        felix_last_observed_at="2026-06-04T17:00:00Z",
                    ),
                },
            ),
        )
        # Cycle 1 sees divergence and updates cache.
        # Cycle 2 sees the same task returning the same value — no divergence.
        _cycle_tasks = [{
            "id": 14, "title": "NewTitle", "project_id": 13,
            "updated": "2026-06-04T19:24:00Z",
        }]
        _cycle_projects = [{"id": 13, "title": "P", "is_archived": False}]
        mock_urlopen.side_effect = [
            *_full_poll_responses(tasks=_cycle_tasks, projects=_cycle_projects),
            *_full_poll_responses(tasks=_cycle_tasks, projects=_cycle_projects),
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


# ===========================================================================
# Group 9 — The recurrence rule is tracked; seed-on-missing-key (WP06 / #1111)
# ===========================================================================


_RULE_PID = 2
_RULE_PROJECTS = [{"id": _RULE_PID, "title": "Habits", "is_archived": False}]


def _rule_task(task_id: int, **overrides):
    """A task as the v2 list endpoint serialises it (no repeats_rrule)."""
    from tests.common.vikunja_v2_factory import make_list_task

    return make_list_task(
        id=task_id,
        identifier=f"#{task_id}",
        index=task_id,
        title=f"Habit {task_id}",
        project_id=_RULE_PID,
        **overrides,
    )


def _pre_upgrade_cache(state_dir: Path, task_ids) -> None:
    """Write a cache in the pre-WP06 shape: v1 rule keys, no repeat keys."""
    tasks = {}
    for tid in task_ids:
        live = _rule_task(tid)
        tasks[str(tid)] = st.TaskCacheEntry(
            vikunja_task_id=tid,
            fields={
                "title": live["title"],
                "done": live["done"],
                "due_date": live["due_date"],
                "project_id": live["project_id"],
                "repeat_after": 86400,
                "repeat_mode": 0,
                "labels": live["labels"],
            },
            vikunja_updated_at=live["updated"],
            felix_last_observed_at="2026-11-19T11:00:00Z",
        )
    st.write_task_cache(
        state_dir,
        st.TaskCacheRecord(last_updated_utc="2026-11-19T11:00:00Z", tasks=tasks),
    )
    st.write_project_cache(
        state_dir,
        st.ProjectCacheRecord(
            last_refreshed_utc="2026-11-19T11:00:00Z",
            projects={str(_RULE_PID): st.ProjectCacheEntry(title="Habits", is_archived=False)},
        ),
    )


def _ledger_rows(state_dir: Path) -> list[dict]:
    path = state_dir / st.SEED_LEDGER_FILENAME
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


class TestRuleTrackingAndSeeding:
    def test_tracked_fields_do_not_include_repeats_rrule(self):
        # The sync reads list endpoints, whose bodies omit repeats_rrule.
        assert "repeats_rrule" not in cy.TRACKED_TASK_FIELDS
        assert "repeat_after" not in cy.TRACKED_TASK_FIELDS
        assert {"repeat", "repeats_from_current_date"} <= cy.TRACKED_TASK_FIELDS

    def test_first_cycle_over_pre_upgrade_cache_seeds_without_divergence(
        self, env, mock_urlopen, capsys
    ):
        state_dir, secrets_dir = env
        ids = list(range(100, 120))
        _pre_upgrade_cache(state_dir, ids)
        mock_urlopen.side_effect = _full_poll_responses(
            [_rule_task(i) for i in ids], projects=_RULE_PROJECTS
        )
        send = _ok_send()
        result = cy.run_cycle(
            _config(state_dir, secrets_dir), send_callable=send, now_utc=NOW_UTC
        )

        assert result.exit_code == 0
        # 0 divergences: no conflict events, no pings.
        assert result.events_emitted == {"auto_resolved": 0, "unsafe_to_auto_resolve": 0}
        assert not (state_dir / st.CONFLICT_EVENTS_FILENAME).exists()
        assert send.call_count == 0
        # N seeds = 2 per task (repeat + repeats_from_current_date).
        n = 2 * len(ids)
        assert result.baseline_seeded == n
        last = json.loads((state_dir / st.LAST_TICK_FILENAME).read_text())
        assert last["baseline_seeded"] == n
        assert last["schema_version"] == st.HEALTH_SCHEMA_VERSION
        assert f"baseline_seeded={n}" in capsys.readouterr().err
        # One ledger line per seed, carrying the documented keys.
        rows = _ledger_rows(state_dir)
        assert len(rows) == n
        assert {r["cycle_id"] for r in rows} == {result.tick_id}
        assert set(rows[0]) == {"cycle_id", "task_id", "field", "seeded_value", "at"}
        assert {(r["task_id"], r["field"]) for r in rows} == {
            (i, f) for i in ids for f in ("repeat", "repeats_from_current_date")
        }
        repeat_row = next(r for r in rows if r["task_id"] == 100 and r["field"] == "repeat")
        assert repeat_row["seeded_value"] == {"freq": "daily", "interval": 1}
        # The cache now holds the live rule (the seed persisted).
        cache = st.read_task_cache(state_dir)
        assert cache.tasks["100"].fields["repeat"] == {"freq": "daily", "interval": 1}
        assert cache.tasks["100"].fields["repeats_from_current_date"] is False
        # Schema version unchanged (no forced re-bootstrap).
        assert st.SCHEMA_VERSION == 1
        assert json.loads((state_dir / st.TASK_CACHE_FILENAME).read_text())["schema_version"] == 1

    def test_second_cycle_with_one_rule_removed_is_one_unsafe_divergence(
        self, env, mock_urlopen
    ):
        from tests.common.vikunja_v2_factory import strip_rule

        state_dir, secrets_dir = env
        ids = [100, 101, 102]
        _pre_upgrade_cache(state_dir, ids)
        cycle1 = [_rule_task(i) for i in ids]
        cycle2 = [strip_rule(t) if t["id"] == 101 else t for t in cycle1]
        mock_urlopen.side_effect = [
            *_full_poll_responses(cycle1, projects=_RULE_PROJECTS),
            *_full_poll_responses(cycle2, projects=_RULE_PROJECTS),
        ]
        send = _ok_send()
        r1 = cy.run_cycle(_config(state_dir, secrets_dir), send_callable=send, now_utc=NOW_UTC)
        assert r1.baseline_seeded == 6
        r2 = cy.run_cycle(_config(state_dir, secrets_dir), send_callable=send, now_utc=NOW_UTC)

        assert r2.exit_code == 0
        # Idempotent: the keys are present now, so no second seed.
        assert r2.baseline_seeded == 0
        assert len(_ledger_rows(state_dir)) == 6
        assert r2.events_emitted == {"auto_resolved": 0, "unsafe_to_auto_resolve": 1}
        rows = [
            json.loads(line)
            for line in (state_dir / st.CONFLICT_EVENTS_FILENAME).read_text().splitlines()
        ]
        assert len(rows) == 1
        row = rows[0]
        assert row["vikunja_entity_id"] == 101
        assert row["diff_field"] == "repeat"
        assert row["class"] == "unsafe_to_auto_resolve"
        assert "uc3_downstream_behavior" in row["unsafe_reasons"]
        assert row["vikunja_value"] is None
        assert row["felix_cached_value"] == {"freq": "daily", "interval": 1}

    def test_task_first_observed_without_rule_records_null_seed(self, env, mock_urlopen):
        """Finding 9: a pre-cycle loss seeds ``null`` -- and the ledger says so."""
        from tests.common.vikunja_v2_factory import strip_rule

        state_dir, secrets_dir = env
        _pre_upgrade_cache(state_dir, [100])
        mock_urlopen.side_effect = _full_poll_responses(
            [strip_rule(_rule_task(100))], projects=_RULE_PROJECTS
        )
        result = cy.run_cycle(_config(state_dir, secrets_dir), send_callable=_ok_send(), now_utc=NOW_UTC)

        assert result.exit_code == 0
        assert result.events_emitted == {"auto_resolved": 0, "unsafe_to_auto_resolve": 0}
        raw_lines = (state_dir / st.SEED_LEDGER_FILENAME).read_text().splitlines()
        repeat_line = next(line for line in raw_lines if '"field": "repeat"' in line)
        assert '"seeded_value": null' in repeat_line
        assert json.loads(repeat_line)["task_id"] == 100

    def test_dry_run_reports_seeds_but_writes_no_ledger(self, env, mock_urlopen, capsys):
        state_dir, secrets_dir = env
        _pre_upgrade_cache(state_dir, [100])
        mock_urlopen.side_effect = _full_poll_responses(
            [_rule_task(100)], projects=_RULE_PROJECTS
        )
        result = cy.run_cycle(
            _config(state_dir, secrets_dir, dry_run=True), send_callable=_ok_send(), now_utc=NOW_UTC
        )
        assert result.baseline_seeded == 2
        assert not (state_dir / st.SEED_LEDGER_FILENAME).exists()
        assert "would_seed=2" in capsys.readouterr().err

    def test_ledger_write_failure_fails_the_cycle_and_keeps_old_cache(
        self, env, mock_urlopen, monkeypatch
    ):
        """No unrecorded seed: if the ledger cannot be written, the cache is not advanced."""
        state_dir, secrets_dir = env
        _pre_upgrade_cache(state_dir, [100])
        mock_urlopen.side_effect = _full_poll_responses(
            [_rule_task(100)], projects=_RULE_PROJECTS
        )

        def _boom(*_a, **_k):
            raise OSError("disk full")

        monkeypatch.setattr(cy, "append_seed_ledger", _boom)
        result = cy.run_cycle(_config(state_dir, secrets_dir), send_callable=_ok_send(), now_utc=NOW_UTC)
        assert result.exit_code == 2
        cache = st.read_task_cache(state_dir)
        assert "repeat" not in cache.tasks["100"].fields

    def test_bootstrap_then_cycle_produces_no_seeds(self, tmp_path, mock_urlopen):
        state_dir = tmp_path / "state"
        secrets_dir = tmp_path / "secrets"
        state_dir.mkdir()
        secrets_dir.mkdir()
        tasks = [_rule_task(100), _rule_task(101, repeat=None)]
        mock_urlopen.side_effect = [
            *_full_poll_responses(tasks, projects=_RULE_PROJECTS),
            *_full_poll_responses(tasks, projects=_RULE_PROJECTS),
        ]
        boot = cy.run_bootstrap(_config(state_dir, secrets_dir), now_utc=NOW_UTC)
        assert boot.exit_code == 0
        assert boot.baseline_seeded == 0
        cache = st.read_task_cache(state_dir)
        assert set(cache.tasks["100"].fields) == set(cy.TRACKED_TASK_FIELDS) | cy.CACHED_ONLY_TASK_FIELDS
        last = json.loads((state_dir / st.LAST_TICK_FILENAME).read_text())
        assert last["baseline_seeded"] == 0

        result = cy.run_cycle(_config(state_dir, secrets_dir), send_callable=_ok_send(), now_utc=NOW_UTC)
        assert result.exit_code == 0
        assert result.baseline_seeded == 0
        assert result.events_emitted == {"auto_resolved": 0, "unsafe_to_auto_resolve": 0}
        assert not (state_dir / st.SEED_LEDGER_FILENAME).exists()

    def test_partial_ledger_write_then_retry_cycle_leaves_parseable_ledger(
        self, env, mock_urlopen, monkeypatch
    ):
        """Review cycle 1, finding 1: a partial ledger write followed by a retry
        cycle must leave only whole, parseable JSONL lines."""
        state_dir, secrets_dir = env
        ids = [100, 101]
        _pre_upgrade_cache(state_dir, ids)
        tasks = [_rule_task(i) for i in ids]
        mock_urlopen.side_effect = [
            *_full_poll_responses(tasks, projects=_RULE_PROJECTS),
            *_full_poll_responses(tasks, projects=_RULE_PROJECTS),
        ]

        real_replace = st.os.replace

        def _torn_replace(src, dst):
            # Simulate a crash after a partial temp-file write: truncate the
            # temp file mid-line, then fail before the rename.
            data = Path(src).read_bytes()
            Path(src).write_bytes(data[: len(data) // 2])
            raise OSError("No space left on device")

        monkeypatch.setattr(st.os, "replace", _torn_replace)
        r1 = cy.run_cycle(_config(state_dir, secrets_dir), send_callable=_ok_send(), now_utc=NOW_UTC)
        assert r1.exit_code == 2
        assert "repeat" not in st.read_task_cache(state_dir).tasks["100"].fields
        monkeypatch.setattr(st.os, "replace", real_replace)

        r2 = cy.run_cycle(_config(state_dir, secrets_dir), send_callable=_ok_send(), now_utc=NOW_UTC)
        assert r2.exit_code == 0
        assert r2.baseline_seeded == 4
        lines = (state_dir / st.SEED_LEDGER_FILENAME).read_text().splitlines()
        rows = [json.loads(line) for line in lines]  # every line parses
        assert len(rows) == 4
        assert {r["cycle_id"] for r in rows} == {r2.tick_id}
        assert not (state_dir / (st.SEED_LEDGER_FILENAME + ".tmp")).exists()
        assert "repeat" in st.read_task_cache(state_dir).tasks["100"].fields
