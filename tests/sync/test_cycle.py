"""Tests for scripts/sync/cycle.py (WP05 / T020).

End-to-end cycle tests with mocked Vikunja HTTP + mocked openclaw subprocess.
Covers steady-state happy path, every failure-injection boundary, the
bootstrap path, and the dry-run path.
"""
from __future__ import annotations

import io
import json
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

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


# ===========================================================================
# Group 1 — Steady-state happy path
# ===========================================================================


class TestSteadyStateHappy:
    def test_zero_changes_exit_0(self, env, mock_urlopen):
        state_dir, secrets_dir = env
        # /tasks/all (empty) + /info.
        mock_urlopen.side_effect = [_resp([]), _resp({"version": "0.24.6"})]
        result = cy.run_cycle(_config(state_dir, secrets_dir), now_utc=NOW_UTC)
        assert result.exit_code == 0
        assert result.success is True
        # Freshness advanced to NOW.
        fresh = st.read_freshness(state_dir)
        assert fresh.layers[cy.LAYER_STATUS_AND_TASK].last_polled_utc.startswith("2026-06-04T19:25:30")
        # last-tick.json written with success.
        last = json.loads((state_dir / st.LAST_TICK_FILENAME).read_text())
        assert last["cycle_error"] is None
        assert last["events_emitted"] == {"auto_resolved": 0, "unsafe_to_auto_resolve": 0}

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
        # /tasks/all returns task 14 with new title; project 13 is known so no /projects fetch; /info.
        mock_urlopen.side_effect = [
            _resp([
                {
                    "id": 14,
                    "title": "NewTitle",
                    "project_id": 13,
                    "updated": "2026-06-04T19:24:00Z",
                }
            ]),
            _resp({"version": "0.24.6"}),
        ]
        # Mark project 13 known.
        st.write_project_cache(
            state_dir,
            st.ProjectCacheRecord(
                last_refreshed_utc="2026-06-04T18:00:00Z",
                projects={"13": st.ProjectCacheEntry(title="P", is_archived=False)},
            ),
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
        mock_urlopen.side_effect = [
            _resp([
                {
                    "id": 14,
                    "title": "NewTitle",
                    "labels": [{"id": 1, "title": "felix:ignore"}],
                    "updated": "2026-06-04T19:24:00Z",
                }
            ]),
            _resp({"version": "0.24.6"}),
        ]
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
        mock_urlopen.side_effect = [
            _resp([
                {"id": 14, "title": "NewTitle", "updated": "2026-06-04T19:24:00Z"}
            ]),
            _resp({"version": "0.24.6"}),
        ]
        # Force emit failure: monkeypatch emit_events to raise OSError.
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

        If freshness lands but last-tick doesn't, the next cycle starts from
        the advanced pointer; the operator notices the missing last-tick.
        Verified by checking modification-order timestamps.
        """
        state_dir, secrets_dir = env
        mock_urlopen.side_effect = [_resp([]), _resp({"version": "0.24.6"})]
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
        # Bootstrap fetches all tasks + projects + info.
        mock_urlopen.side_effect = [
            _resp([
                {"id": 14, "title": "A", "project_id": 13, "updated": "2026-06-04T18:00:00Z"},
                {"id": 15, "title": "B", "project_id": 13, "updated": "2026-06-04T18:00:00Z"},
            ]),
            _resp({"id": 13, "title": "Habits", "is_archived": False}),
            _resp({"version": "0.24.6"}),
        ]
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

    def test_bootstrap_does_not_emit_events(self, tmp_path, mock_urlopen):
        state_dir = tmp_path / "state"
        secrets_dir = tmp_path / "secrets"
        state_dir.mkdir()
        secrets_dir.mkdir()
        (secrets_dir / "vikunja-api").write_text("tok")
        mock_urlopen.side_effect = [
            _resp([
                {"id": 14, "title": "x", "updated": "2026-06-04T18:00:00Z"},
            ]),
            _resp({"version": "0.24.6"}),
        ]
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
        mock_urlopen.side_effect = [_resp([]), _resp({"version": "0.24.6"})]
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
        # Cycle 2 sees the same task returning the same value — no divergence
        # because cache was updated by cycle 1.
        mock_urlopen.side_effect = [
            _resp([{"id": 14, "title": "NewTitle", "updated": "2026-06-04T19:24:00Z"}]),
            _resp({"version": "0.24.6"}),
            _resp([{"id": 14, "title": "NewTitle", "updated": "2026-06-04T19:24:00Z"}]),
            _resp({"version": "0.24.6"}),
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
