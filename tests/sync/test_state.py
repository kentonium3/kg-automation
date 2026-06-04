"""Tests for scripts/sync/state.py (WP01 / T004).

Covers atomic-write semantics, schema validation, missing-file handling, and
roundtrip correctness for every entity reader/writer. All I/O is sandboxed
via the pytest ``tmp_path`` fixture; no live state directory is touched.
"""
from __future__ import annotations

import json

import pytest

from scripts.sync import state as st


# ===========================================================================
# Group 1 — atomic_write_json
# ===========================================================================


class TestAtomicWriteJson:
    def test_roundtrip(self, tmp_path):
        path = tmp_path / "out.json"
        payload = {"hello": "world", "n": 42}
        st.atomic_write_json(path, payload)
        assert json.loads(path.read_text()) == payload

    def test_no_tmp_file_left_behind_on_success(self, tmp_path):
        path = tmp_path / "out.json"
        st.atomic_write_json(path, {"a": 1})
        tmp = path.with_suffix(path.suffix + ".tmp")
        assert not tmp.exists()

    def test_overwrite_replaces_previous_content(self, tmp_path):
        path = tmp_path / "out.json"
        st.atomic_write_json(path, {"v": 1})
        st.atomic_write_json(path, {"v": 2})
        assert json.loads(path.read_text()) == {"v": 2}

    def test_creates_parent_directory_if_missing(self, tmp_path):
        path = tmp_path / "nested" / "out.json"
        st.atomic_write_json(path, {"ok": True})
        assert path.exists()
        assert json.loads(path.read_text()) == {"ok": True}

    def test_output_is_sorted_keys_indented(self, tmp_path):
        path = tmp_path / "out.json"
        st.atomic_write_json(path, {"b": 1, "a": 2})
        text = path.read_text()
        # sort_keys=True puts "a" before "b"
        assert text.index('"a"') < text.index('"b"')
        # indent=2 — second key starts on its own line
        assert "\n" in text


# ===========================================================================
# Group 2 — append_jsonl
# ===========================================================================


class TestAppendJsonl:
    def test_writes_one_line_per_record(self, tmp_path):
        path = tmp_path / "log.jsonl"
        st.append_jsonl(path, {"event": "a"})
        st.append_jsonl(path, {"event": "b"})
        lines = path.read_text().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0]) == {"event": "a"}
        assert json.loads(lines[1]) == {"event": "b"}

    def test_creates_parent_directory_if_missing(self, tmp_path):
        path = tmp_path / "nested" / "log.jsonl"
        st.append_jsonl(path, {"first": True})
        assert path.exists()


# ===========================================================================
# Group 3 — FreshnessPointer reader/writer
# ===========================================================================


class TestFreshnessPointer:
    def test_roundtrip(self, tmp_path):
        fp = st.FreshnessPointer(
            last_updated_utc="2026-06-04T19:25:32Z",
            layers={
                "status_and_task": st.FreshnessLayer(
                    last_polled_utc="2026-06-04T19:25:30Z"
                ),
            },
        )
        st.write_freshness(tmp_path, fp)
        roundtripped = st.read_freshness(tmp_path)
        assert roundtripped == fp

    def test_missing_file_raises_with_bootstrap_hint(self, tmp_path):
        with pytest.raises(OSError, match="--bootstrap"):
            st.read_freshness(tmp_path)

    def test_schema_version_mismatch_raises(self, tmp_path):
        path = tmp_path / st.FRESHNESS_FILENAME
        bad = {
            "schema_version": 999,
            "last_updated_utc": "x",
            "layers": {},
        }
        path.write_text(json.dumps(bad))
        with pytest.raises(OSError, match="schema_version mismatch"):
            st.read_freshness(tmp_path)


# ===========================================================================
# Group 4 — TaskCacheRecord reader/writer
# ===========================================================================


class TestTaskCacheRecord:
    def test_roundtrip(self, tmp_path):
        tc = st.TaskCacheRecord(
            last_updated_utc="2026-06-04T19:25:30Z",
            tasks={
                "14": st.TaskCacheEntry(
                    vikunja_task_id=14,
                    fields={"title": "Wake at 5", "done": False},
                    vikunja_updated_at="2026-06-04T18:32:18Z",
                    felix_last_observed_at="2026-06-04T18:35:01Z",
                ),
            },
        )
        st.write_task_cache(tmp_path, tc)
        roundtripped = st.read_task_cache(tmp_path)
        assert roundtripped == tc

    def test_missing_file_returns_empty_default(self, tmp_path):
        rc = st.read_task_cache(tmp_path)
        assert rc.tasks == {}
        assert rc.schema_version == st.SCHEMA_VERSION

    def test_schema_version_mismatch_raises(self, tmp_path):
        path = tmp_path / st.TASK_CACHE_FILENAME
        path.write_text(json.dumps({"schema_version": 2, "last_updated_utc": "x", "tasks": {}}))
        with pytest.raises(OSError, match="schema_version mismatch"):
            st.read_task_cache(tmp_path)


# ===========================================================================
# Group 5 — ProjectCacheRecord reader/writer
# ===========================================================================


class TestProjectCacheRecord:
    def test_roundtrip(self, tmp_path):
        pc = st.ProjectCacheRecord(
            last_refreshed_utc="2026-06-04T19:25:30Z",
            projects={
                "13": st.ProjectCacheEntry(title="Habits", is_archived=False),
            },
        )
        st.write_project_cache(tmp_path, pc)
        roundtripped = st.read_project_cache(tmp_path)
        assert roundtripped == pc

    def test_missing_file_returns_empty_default(self, tmp_path):
        rc = st.read_project_cache(tmp_path)
        assert rc.projects == {}

    def test_schema_version_mismatch_raises(self, tmp_path):
        path = tmp_path / st.PROJECT_CACHE_FILENAME
        path.write_text(
            json.dumps({"schema_version": 99, "last_refreshed_utc": "x", "projects": {}})
        )
        with pytest.raises(OSError, match="schema_version mismatch"):
            st.read_project_cache(tmp_path)


# ===========================================================================
# Group 6 — GuardState reader/writer
# ===========================================================================


class TestGuardState:
    def test_roundtrip(self, tmp_path):
        gs = st.GuardState(
            g3_daily_cap=st.G3DailyCap(
                calendar_day_et="2026-06-04",
                unsafe_pings_sent_today=3,
                cap=5,
            ),
        )
        st.write_guard_state(tmp_path, gs)
        roundtripped = st.read_guard_state(tmp_path)
        assert roundtripped == gs

    def test_missing_file_returns_empty_default_cap_5(self, tmp_path):
        rc = st.read_guard_state(tmp_path)
        assert rc.g3_daily_cap.unsafe_pings_sent_today == 0
        assert rc.g3_daily_cap.cap == 5

    def test_schema_version_mismatch_raises(self, tmp_path):
        path = tmp_path / st.GUARD_STATE_FILENAME
        path.write_text(
            json.dumps(
                {
                    "schema_version": 5,
                    "g3_daily_cap": {
                        "calendar_day_et": "x",
                        "unsafe_pings_sent_today": 0,
                        "cap": 5,
                    },
                }
            )
        )
        with pytest.raises(OSError, match="schema_version mismatch"):
            st.read_guard_state(tmp_path)


# ===========================================================================
# Group 7 — Per-tick health record (success + error stream)
# ===========================================================================


class TestPerTickHealthRecord:
    def test_success_path_overwrites(self, tmp_path):
        record = st.PerTickHealthRecord(
            tick_id="01KTA1J3FH87XJWT7FQPT1EZE7",
            started_at_utc="2026-06-04T19:25:30Z",
            completed_at_utc="2026-06-04T19:25:30.347Z",
            duration_ms=347,
            cadence_seconds=300,
            layer_pointers={
                "status_and_task": st.LayerPointerSnapshot(
                    before="2026-06-04T19:20:30Z",
                    after="2026-06-04T19:25:30Z",
                ),
            },
            events_emitted={"auto_resolved": 0, "unsafe_to_auto_resolve": 0},
            cycle_error=None,
            vikunja_version_seen="0.24.6",
        )
        st.write_per_tick_health(tmp_path, record)
        # Second write overwrites; tmp file is gone.
        st.write_per_tick_health(tmp_path, record)
        path = tmp_path / st.LAST_TICK_FILENAME
        assert path.exists()
        assert not path.with_suffix(".json.tmp").exists()
        data = json.loads(path.read_text())
        assert data["cycle_error"] is None

    def test_error_path_appends(self, tmp_path):
        e1 = st.PerTickErrorRecord(
            tick_id="t1",
            started_at_utc="2026-06-04T19:25:30Z",
            failed_at_utc="2026-06-04T19:25:33Z",
            phase="fetch",
            cycle_error="boom",
            layer_pointers_unchanged=True,
        )
        e2 = st.PerTickErrorRecord(
            tick_id="t2",
            started_at_utc="2026-06-04T19:30:30Z",
            failed_at_utc="2026-06-04T19:30:35Z",
            phase="emit",
            cycle_error="JSONL append failed",
            layer_pointers_unchanged=False,
        )
        st.append_per_tick_error(tmp_path, e1)
        st.append_per_tick_error(tmp_path, e2)
        path = tmp_path / st.LAST_TICK_ERRORS_FILENAME
        lines = path.read_text().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["phase"] == "fetch"
        assert json.loads(lines[1])["phase"] == "emit"


# ===========================================================================
# Group 8 — Module-import sanity
# ===========================================================================


class TestModuleImport:
    def test_constants_present(self):
        assert st.SCHEMA_VERSION == 1
        assert st.STATE_DIR_DEFAULT.as_posix() == "/data/services/openclaw/state/sync"
        assert st.SECRETS_DIR_DEFAULT.as_posix() == "/data/services/openclaw/secrets"

    def test_filenames_present(self):
        # The downstream WPs reference these by name; treat as a contract.
        assert st.FRESHNESS_FILENAME == "freshness.json"
        assert st.TASK_CACHE_FILENAME == "task-cache.json"
        assert st.PROJECT_CACHE_FILENAME == "project-cache.json"
        assert st.GUARD_STATE_FILENAME == "guard-state.json"
        assert st.CONFLICT_EVENTS_FILENAME == "conflict-events.jsonl"
        assert st.LAST_TICK_FILENAME == "last-tick.json"
        assert st.LAST_TICK_ERRORS_FILENAME == "last-tick.errors.jsonl"
