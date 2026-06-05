"""Tests for scripts/habits/migrate_schedule.py (WP02).

Covers the four public entry points (``load_schedule``, ``capture_snapshot``,
``apply_schedule``, ``rollback``) and the ``__main__`` CLI surface. All HTTP
calls are mocked via ``urllib.request.urlopen``; no real Vikunja traffic
during the test run.

Test groups:

1. ``load_schedule`` — happy path + every documented validation failure.
2. ``capture_snapshot`` — BEFORE-state assembly, retire pre-flight refusal,
   network-failure propagation.
3. ``apply_schedule`` — full apply, dry-run no-mutation, idempotency
   (already-matches skip), mid-batch failure with partial snapshot.
4. ``rollback`` — reverse-apply, missing snapshot error, schema-version
   mismatch error.
5. CLI — ``--help`` exits 0, Tier 2 pre-flight gate (exit 3 without env
   var), validation failure exits 2, missing ``--snapshot-file`` on rollback
   exits 2, dry-run happy path exits 0, rollback happy path exits 0.
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from scripts.habits import migrate_schedule as ms


# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------


def _resp(payload, *, status: int = 200):
    """Return a context-manager-compatible mock urlopen response."""
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


def _make_task_payload(
    task_id: int,
    title: str = "Habit",
    repeat_after: int = 0,
    repeat_mode: int = 0,
    done: bool = False,
    project_id: int = 1,
    labels: list | None = None,
) -> dict:
    return {
        "id": task_id,
        "title": title,
        "repeat_after": repeat_after,
        "repeat_mode": repeat_mode,
        "done": done,
        "due_date": "2026-05-20T08:00:00Z",
        "project_id": project_id,
        "labels": labels or [],
        "is_archived": False,
        "done_at": None,
    }


def _minimal_valid_schedule_dict() -> dict:
    return {
        "mission_id": "01KS0M59313RF0WVJZTXYDJC6C",
        "operations": [
            {
                "op": "patch",
                "task_id": 14,
                "target": {"repeat_after": 86400, "repeat_mode": 0},
            },
            {
                "op": "retire",
                "task_id": 17,
            },
            {
                "op": "create",
                "schedule": {"repeat_after": 604800, "repeat_mode": 0},
                "attributes": {"title": "Strength training — Monday"},
            },
        ],
    }


def _write_yaml(tmp_path: Path, data: dict, *, name: str = "schedule.yaml") -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Group 1: load_schedule + validation
# ---------------------------------------------------------------------------


class TestLoadScheduleHappyPath:
    def test_valid_minimal_schedule(self, tmp_path):
        path = _write_yaml(tmp_path, _minimal_valid_schedule_dict())
        result = ms.load_schedule(path)
        assert result["mission_id"] == "01KS0M59313RF0WVJZTXYDJC6C"
        assert len(result["operations"]) == 3

    def test_full_phase3_schedule_validates(self):
        # The mission's own schedule.yaml must pass validation.
        repo_root = Path(__file__).resolve().parent.parent.parent
        schedule = (
            repo_root
            / "scripts"
            / "habits"
            / "migrations"
            / "phase3-schedule.yaml"
        )
        if not schedule.exists():
            pytest.skip("phase3-schedule.yaml not present in this checkout")
        result = ms.load_schedule(schedule)
        assert result["mission_id"] == "01KS0M59313RF0WVJZTXYDJC6C"
        # 7 patches + 1 retire + 3 creates = 11 operations.
        assert len(result["operations"]) == 11


class TestLoadScheduleValidation:
    def test_yaml_parse_error(self, tmp_path):
        path = tmp_path / "bad.yaml"
        path.write_text("not: valid: yaml: [", encoding="utf-8")
        with pytest.raises(ValueError, match="YAML parse error"):
            ms.load_schedule(path)

    def test_top_level_not_mapping(self, tmp_path):
        path = tmp_path / "list.yaml"
        path.write_text("- 1\n- 2\n", encoding="utf-8")
        with pytest.raises(ValueError, match="top-level must be a YAML mapping"):
            ms.load_schedule(path)

    def test_missing_mission_id(self, tmp_path):
        data = _minimal_valid_schedule_dict()
        del data["mission_id"]
        path = _write_yaml(tmp_path, data)
        with pytest.raises(ValueError, match="missing required non-empty string 'mission_id'"):
            ms.load_schedule(path)

    def test_empty_mission_id(self, tmp_path):
        data = _minimal_valid_schedule_dict()
        data["mission_id"] = "  "
        path = _write_yaml(tmp_path, data)
        with pytest.raises(ValueError, match="missing required non-empty string 'mission_id'"):
            ms.load_schedule(path)

    def test_operations_not_list(self, tmp_path):
        data = _minimal_valid_schedule_dict()
        data["operations"] = {"not": "a list"}
        path = _write_yaml(tmp_path, data)
        with pytest.raises(ValueError, match="'operations' must be a list"):
            ms.load_schedule(path)

    def test_operation_not_mapping(self, tmp_path):
        data = _minimal_valid_schedule_dict()
        data["operations"][0] = "not-a-dict"
        path = _write_yaml(tmp_path, data)
        with pytest.raises(ValueError, match="Operation 0:.*must be a YAML mapping"):
            ms.load_schedule(path)

    def test_unknown_op(self, tmp_path):
        data = _minimal_valid_schedule_dict()
        data["operations"][0] = {"op": "frobnicate", "task_id": 14}
        path = _write_yaml(tmp_path, data)
        with pytest.raises(ValueError, match="Operation 0:.*unknown op 'frobnicate'"):
            ms.load_schedule(path)

    def test_missing_task_id_on_patch(self, tmp_path):
        data = _minimal_valid_schedule_dict()
        data["operations"][0] = {
            "op": "patch",
            "target": {"repeat_after": 86400, "repeat_mode": 0},
        }
        path = _write_yaml(tmp_path, data)
        with pytest.raises(ValueError, match="Operation 0:.*'task_id' must be a positive integer"):
            ms.load_schedule(path)

    def test_negative_task_id(self, tmp_path):
        data = _minimal_valid_schedule_dict()
        data["operations"][0]["task_id"] = -5
        path = _write_yaml(tmp_path, data)
        with pytest.raises(ValueError, match="Operation 0:.*'task_id' must be > 0"):
            ms.load_schedule(path)

    def test_duplicate_task_id(self, tmp_path):
        data = _minimal_valid_schedule_dict()
        data["operations"].append(
            {
                "op": "patch",
                "task_id": 14,  # already used in op 0
                "target": {"repeat_after": 86400, "repeat_mode": 0},
            }
        )
        path = _write_yaml(tmp_path, data)
        with pytest.raises(ValueError, match="duplicate task_id 14"):
            ms.load_schedule(path)

    def test_patch_missing_target(self, tmp_path):
        data = _minimal_valid_schedule_dict()
        del data["operations"][0]["target"]
        path = _write_yaml(tmp_path, data)
        with pytest.raises(ValueError, match="missing or non-dict 'target' block"):
            ms.load_schedule(path)

    def test_patch_negative_repeat_after(self, tmp_path):
        data = _minimal_valid_schedule_dict()
        data["operations"][0]["target"]["repeat_after"] = -1
        path = _write_yaml(tmp_path, data)
        with pytest.raises(ValueError, match="'target.repeat_after' must be > 0"):
            ms.load_schedule(path)

    def test_patch_zero_repeat_after(self, tmp_path):
        data = _minimal_valid_schedule_dict()
        data["operations"][0]["target"]["repeat_after"] = 0
        path = _write_yaml(tmp_path, data)
        with pytest.raises(ValueError, match="'target.repeat_after' must be > 0"):
            ms.load_schedule(path)

    def test_patch_invalid_repeat_mode(self, tmp_path):
        data = _minimal_valid_schedule_dict()
        data["operations"][0]["target"]["repeat_mode"] = 7
        path = _write_yaml(tmp_path, data)
        with pytest.raises(ValueError, match="'target.repeat_mode' must be one of"):
            ms.load_schedule(path)

    def test_patch_non_int_repeat_after(self, tmp_path):
        data = _minimal_valid_schedule_dict()
        data["operations"][0]["target"]["repeat_after"] = "86400"  # string not int
        path = _write_yaml(tmp_path, data)
        with pytest.raises(ValueError, match="'target.repeat_after' must be a positive integer"):
            ms.load_schedule(path)

    def test_patch_boolean_repeat_after_rejected(self, tmp_path):
        # YAML 'true' parses to bool which is also int in Python — defensive.
        data = _minimal_valid_schedule_dict()
        data["operations"][0]["target"]["repeat_after"] = True
        path = _write_yaml(tmp_path, data)
        with pytest.raises(ValueError, match="'target.repeat_after' must be a positive integer"):
            ms.load_schedule(path)

    def test_create_missing_attributes(self, tmp_path):
        data = _minimal_valid_schedule_dict()
        data["operations"][2] = {
            "op": "create",
            "schedule": {"repeat_after": 604800, "repeat_mode": 0},
        }
        path = _write_yaml(tmp_path, data)
        with pytest.raises(ValueError, match="missing or non-dict 'attributes' block"):
            ms.load_schedule(path)

    def test_create_empty_title(self, tmp_path):
        data = _minimal_valid_schedule_dict()
        data["operations"][2]["attributes"]["title"] = "   "
        path = _write_yaml(tmp_path, data)
        with pytest.raises(ValueError, match="'attributes.title' must be a non-empty string"):
            ms.load_schedule(path)

    def test_create_missing_schedule(self, tmp_path):
        data = _minimal_valid_schedule_dict()
        del data["operations"][2]["schedule"]
        path = _write_yaml(tmp_path, data)
        with pytest.raises(ValueError, match="missing or non-dict 'schedule' block"):
            ms.load_schedule(path)

    def test_create_invalid_due_date_no_tz(self, tmp_path):
        data = _minimal_valid_schedule_dict()
        data["operations"][2]["attributes"]["due_date"] = "2026-05-20T08:00:00"
        path = _write_yaml(tmp_path, data)
        with pytest.raises(ValueError, match="must include a timezone offset"):
            ms.load_schedule(path)

    def test_create_invalid_due_date_garbage(self, tmp_path):
        data = _minimal_valid_schedule_dict()
        data["operations"][2]["attributes"]["due_date"] = "not-a-date"
        path = _write_yaml(tmp_path, data)
        with pytest.raises(ValueError, match="not valid ISO-8601"):
            ms.load_schedule(path)

    def test_create_valid_due_date_with_z(self, tmp_path):
        data = _minimal_valid_schedule_dict()
        data["operations"][2]["attributes"]["due_date"] = "2026-05-20T08:00:00Z"
        path = _write_yaml(tmp_path, data)
        result = ms.load_schedule(path)
        assert result["operations"][2]["attributes"]["due_date"] == "2026-05-20T08:00:00Z"

    def test_create_invalid_project_id(self, tmp_path):
        data = _minimal_valid_schedule_dict()
        data["operations"][2]["attributes"]["project_id"] = -7
        path = _write_yaml(tmp_path, data)
        with pytest.raises(ValueError, match="'attributes.project_id' must be a positive integer"):
            ms.load_schedule(path)

    def test_create_invalid_labels_type(self, tmp_path):
        data = _minimal_valid_schedule_dict()
        data["operations"][2]["attributes"]["labels"] = "personal"  # str not list
        path = _write_yaml(tmp_path, data)
        with pytest.raises(ValueError, match="'attributes.labels' must be a list"):
            ms.load_schedule(path)

    def test_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            ms.load_schedule(tmp_path / "missing.yaml")


# ---------------------------------------------------------------------------
# Group 2: capture_snapshot
# ---------------------------------------------------------------------------


class TestCaptureSnapshot:
    def test_happy_path_assembles_before_states(self, mock_urlopen):
        schedule = _minimal_valid_schedule_dict()
        mock_urlopen.side_effect = [
            _resp(_make_task_payload(14, title="Wake at 5:00 AM")),
            _resp(_make_task_payload(17, title="Workout", project_id=1, labels=[{"id": 5, "title": "personal"}])),
        ]
        snapshot = ms.capture_snapshot(
            "http://test/api/v1/", "token", schedule
        )
        assert snapshot["schema_version"] == "1"
        assert snapshot["mission_id"] == "01KS0M59313RF0WVJZTXYDJC6C"
        assert len(snapshot["before_states"]) == 2  # patch + retire (create doesn't touch BEFORE)
        ids = sorted(e["task_id"] for e in snapshot["before_states"])
        assert ids == [14, 17]
        assert snapshot["applied_changes"] == []
        assert snapshot["created_tasks"] == []
        assert "config_file_sha256" in snapshot
        assert "captured_at" in snapshot

    def test_retire_with_nonzero_repeat_after_refused(self, mock_urlopen):
        schedule = _minimal_valid_schedule_dict()
        mock_urlopen.side_effect = [
            _resp(_make_task_payload(14)),
            # task 17 has repeat_after=604800 — should refuse to retire it.
            _resp(_make_task_payload(17, title="Workout", repeat_after=604800)),
        ]
        with pytest.raises(ValueError, match="Cannot retire task 17.*repeat_after=604800"):
            ms.capture_snapshot("http://test/api/v1/", "token", schedule)

    def test_network_error_propagates(self, mock_urlopen):
        schedule = _minimal_valid_schedule_dict()
        mock_urlopen.side_effect = urllib.error.URLError("DNS fail")
        with pytest.raises(OSError, match="network failure"):
            ms.capture_snapshot("http://test/api/v1/", "token", schedule)

    def test_http_error_propagates(self, mock_urlopen):
        schedule = _minimal_valid_schedule_dict()
        mock_urlopen.side_effect = _http_error(503, b'{"message":"down"}')
        with pytest.raises(OSError, match="HTTP 503"):
            ms.capture_snapshot("http://test/api/v1/", "token", schedule)


# ---------------------------------------------------------------------------
# Group 3: apply_schedule
# ---------------------------------------------------------------------------


class TestApplySchedule:
    def test_happy_path_full_apply(self, mock_urlopen, tmp_path):
        schedule = _minimal_valid_schedule_dict()
        snapshot_path = tmp_path / "snapshot.json"
        mock_urlopen.side_effect = [
            # capture_snapshot: GET task 14, GET task 17.
            _resp(_make_task_payload(14, title="Wake at 5:00 AM")),
            _resp(_make_task_payload(17, title="Workout", project_id=1, labels=[{"id": 5}])),
            # apply: POST patch 14, POST retire 17, PUT create new task.
            _resp(_make_task_payload(14, repeat_after=86400)),
            _resp(_make_task_payload(17, done=True)),
            _resp(_make_task_payload(100, title="Strength training — Monday")),
        ]
        snapshot = ms.apply_schedule(
            "http://test/api/v1/",
            "token",
            schedule,
            snapshot_path,
            dry_run=False,
            run_date=datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc),  # Monday
        )
        assert len(snapshot["applied_changes"]) == 3
        assert all(c["result"] == "success" for c in snapshot["applied_changes"])
        assert len(snapshot["created_tasks"]) == 1
        assert snapshot["created_tasks"][0]["task_id"] == 100
        # Snapshot file on disk should match returned dict.
        on_disk = json.loads(snapshot_path.read_text(encoding="utf-8"))
        assert len(on_disk["applied_changes"]) == 3

    def test_dry_run_issues_no_mutation_calls(self, mock_urlopen, tmp_path):
        schedule = _minimal_valid_schedule_dict()
        snapshot_path = tmp_path / "dry-snapshot.json"
        mock_urlopen.side_effect = [
            _resp(_make_task_payload(14, title="Wake at 5:00 AM")),
            _resp(_make_task_payload(17, title="Workout")),
        ]
        snapshot = ms.apply_schedule(
            "http://test/api/v1/",
            "token",
            schedule,
            snapshot_path,
            dry_run=True,
        )
        # Only the 2 BEFORE-state GETs happened — no POST/PUT.
        assert mock_urlopen.call_count == 2
        assert snapshot["applied_changes"] == []
        assert snapshot["created_tasks"] == []
        # Snapshot file written even on dry-run (per contract).
        assert snapshot_path.exists()

    def test_idempotent_patch_skipped(self, mock_urlopen, tmp_path):
        schedule = _minimal_valid_schedule_dict()
        snapshot_path = tmp_path / "idempotent.json"
        # Task 14 already has repeat_after=86400 — PATCH should be skipped.
        mock_urlopen.side_effect = [
            _resp(_make_task_payload(14, repeat_after=86400, repeat_mode=0)),
            _resp(_make_task_payload(17, title="Workout", project_id=1)),
            # No POST for task 14 — patch skipped.
            _resp(_make_task_payload(17, done=True)),
            _resp(_make_task_payload(100, title="Strength training — Monday")),
        ]
        snapshot = ms.apply_schedule(
            "http://test/api/v1/", "token", schedule, snapshot_path,
            run_date=datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc),
        )
        results = [c["result"] for c in snapshot["applied_changes"]]
        assert "skipped" in results
        assert results.count("success") == 2  # retire + create
        assert results.count("skipped") == 1  # patch was idempotent

    def test_mid_batch_failure_persists_partial_snapshot(self, mock_urlopen, tmp_path):
        schedule = _minimal_valid_schedule_dict()
        snapshot_path = tmp_path / "partial.json"
        mock_urlopen.side_effect = [
            # capture_snapshot
            _resp(_make_task_payload(14, title="Wake at 5:00 AM")),
            _resp(_make_task_payload(17, title="Workout")),
            # apply: patch 14 OK, retire 17 FAILS.
            _resp(_make_task_payload(14, repeat_after=86400)),
            _http_error(500),
        ]
        with pytest.raises(OSError):
            ms.apply_schedule(
                "http://test/api/v1/", "token", schedule, snapshot_path,
                run_date=datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc),
            )
        # Snapshot on disk should have the successful patch + the error entry.
        on_disk = json.loads(snapshot_path.read_text(encoding="utf-8"))
        results = [c["result"] for c in on_disk["applied_changes"]]
        assert "success" in results
        assert "error" in results
        # No created_tasks because create never reached.
        assert on_disk["created_tasks"] == []

    def test_create_inherits_project_id_from_retire(self, mock_urlopen, tmp_path):
        schedule = {
            "mission_id": "01KS0M59313RF0WVJZTXYDJC6C",
            "operations": [
                {"op": "retire", "task_id": 17},
                {
                    "op": "create",
                    "schedule": {"repeat_after": 604800, "repeat_mode": 0},
                    "attributes": {"title": "Strength training — Monday"},
                },
            ],
        }
        snapshot_path = tmp_path / "inherit.json"
        # Capture: GET 17 with project_id=42, labels=[{id:99}].
        mock_urlopen.side_effect = [
            _resp(_make_task_payload(17, project_id=42, labels=[{"id": 99}])),
            _resp(_make_task_payload(17, done=True)),
            _resp(_make_task_payload(100, title="Strength training — Monday", project_id=42)),
        ]
        ms.apply_schedule(
            "http://test/api/v1/", "token", schedule, snapshot_path,
            run_date=datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc),
        )
        # Inspect the third call (the create PUT) — should target project 42.
        third_call = mock_urlopen.call_args_list[2]
        request_obj = third_call[0][0]
        assert "projects/42/tasks" in request_obj.full_url

    def test_create_explicit_project_id_overrides_inheritance(self, mock_urlopen, tmp_path):
        schedule = {
            "mission_id": "01KS0M59313RF0WVJZTXYDJC6C",
            "operations": [
                {
                    "op": "create",
                    "schedule": {"repeat_after": 86400, "repeat_mode": 0},
                    "attributes": {
                        "title": "New daily habit",
                        "project_id": 7,
                    },
                },
            ],
        }
        snapshot_path = tmp_path / "explicit-proj.json"
        mock_urlopen.side_effect = [
            _resp(_make_task_payload(200, title="New daily habit")),
        ]
        ms.apply_schedule(
            "http://test/api/v1/", "token", schedule, snapshot_path,
            run_date=datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc),
        )
        # Single call was the PUT — should target project 7.
        first_call = mock_urlopen.call_args_list[0]
        assert "projects/7/tasks" in first_call[0][0].full_url

    def test_create_without_project_id_or_inheritance_raises(self, mock_urlopen, tmp_path):
        schedule = {
            "mission_id": "01KS0M59313RF0WVJZTXYDJC6C",
            "operations": [
                {
                    "op": "create",
                    "schedule": {"repeat_after": 86400, "repeat_mode": 0},
                    "attributes": {"title": "Orphan task"},
                },
            ],
        }
        snapshot_path = tmp_path / "orphan.json"
        # No GETs needed (no patch/retire); first call is the failed apply.
        with pytest.raises(ValueError, match="has no 'attributes.project_id'"):
            ms.apply_schedule(
                "http://test/api/v1/", "token", schedule, snapshot_path,
            )


# ---------------------------------------------------------------------------
# Group 4: _default_due_date
# ---------------------------------------------------------------------------


class TestDefaultDueDate:
    def test_weekly_monday_from_friday(self):
        # Run on Friday 2026-05-15 → next Monday = 2026-05-18.
        run = datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc)
        out = ms._default_due_date(
            "Strength training — Monday", ms.SECONDS_PER_WEEK, run_date=run
        )
        parsed = datetime.fromisoformat(out)
        assert parsed.weekday() == 0  # Monday
        assert parsed.date().isoformat() == "2026-05-18"
        assert parsed.hour == 8

    def test_weekly_wednesday_from_monday(self):
        run = datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc)
        out = ms._default_due_date(
            "Strength training — Wednesday", ms.SECONDS_PER_WEEK, run_date=run
        )
        parsed = datetime.fromisoformat(out)
        assert parsed.weekday() == 2  # Wednesday
        assert parsed.date().isoformat() == "2026-05-20"

    def test_weekly_friday_from_friday_is_today(self):
        # Today IS Friday → next Friday at 08:00 UTC is today.
        run = datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc)
        out = ms._default_due_date(
            "Strength training — Friday", ms.SECONDS_PER_WEEK, run_date=run
        )
        parsed = datetime.fromisoformat(out)
        assert parsed.weekday() == 4  # Friday
        assert parsed.date().isoformat() == "2026-05-15"

    def test_weekly_no_weekday_hint_defaults_to_next_week(self):
        run = datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc)
        out = ms._default_due_date("Generic weekly", ms.SECONDS_PER_WEEK, run_date=run)
        parsed = datetime.fromisoformat(out)
        # Should land 7 days later (same weekday next week).
        assert (parsed.date() - run.date()).days == 7

    def test_daily_returns_tomorrow_at_8_utc(self):
        run = datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc)
        out = ms._default_due_date("Daily habit", ms.SECONDS_PER_DAY, run_date=run)
        parsed = datetime.fromisoformat(out)
        assert parsed.date().isoformat() == "2026-05-19"
        assert parsed.hour == 8

    def test_lowercase_weekday_not_matched(self):
        # Case-sensitive regex — lowercase shouldn't extract weekday.
        run = datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc)
        out = ms._default_due_date(
            "strength training — monday", ms.SECONDS_PER_WEEK, run_date=run
        )
        parsed = datetime.fromisoformat(out)
        # No weekday extracted → fallback "next week same day".
        assert (parsed.date() - run.date()).days == 7


# ---------------------------------------------------------------------------
# Group 5: rollback
# ---------------------------------------------------------------------------


class TestRollback:
    def _seed_snapshot(self, path: Path) -> dict:
        snapshot = {
            "schema_version": "1",
            "mission_id": "01KS0M59313RF0WVJZTXYDJC6C",
            "mission_slug": "habits-native-repeat-jsonl-state-01KS0M59",
            "captured_at": "2026-05-18T12:00:00+00:00",
            "config_file_sha256": "fakehash",
            "before_states": [
                {
                    "task_id": 14,
                    "before": {
                        "repeat_after": 0,
                        "repeat_mode": 0,
                        "done": False,
                        "due_date": "2026-05-19T08:00:00Z",
                        "is_archived": False,
                        "done_at": None,
                        "title": "Wake at 5:00 AM",
                        "project_id": 1,
                        "labels": [],
                    },
                    "intended_op": "patch",
                },
                {
                    "task_id": 17,
                    "before": {
                        "repeat_after": 0,
                        "repeat_mode": 0,
                        "done": False,
                        "due_date": "2026-05-19T08:00:00Z",
                        "is_archived": False,
                        "done_at": None,
                        "title": "Workout",
                        "project_id": 1,
                        "labels": [],
                    },
                    "intended_op": "retire",
                },
            ],
            "created_tasks": [
                {
                    "task_id": 100,
                    "title": "Strength training — Monday",
                    "created_at": "2026-05-18T12:00:02+00:00",
                },
            ],
            "applied_changes": [
                {
                    "task_id": 14,
                    "op": "patch",
                    "applied_at": "2026-05-18T12:00:00+00:00",
                    "result": "success",
                },
                {
                    "task_id": 17,
                    "op": "retire",
                    "applied_at": "2026-05-18T12:00:01+00:00",
                    "result": "success",
                },
                {
                    "task_id": 100,
                    "op": "create",
                    "applied_at": "2026-05-18T12:00:02+00:00",
                    "result": "success",
                },
            ],
        }
        path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        return snapshot

    def test_happy_path_reverses_in_reverse_order(self, mock_urlopen, tmp_path):
        snap_path = tmp_path / "snapshot.json"
        self._seed_snapshot(snap_path)
        mock_urlopen.side_effect = [
            # Rollback iterates in reverse: create → retire → patch.
            _resp(_make_task_payload(100)),  # DELETE returns the deleted task (or empty)
            _resp(_make_task_payload(17, done=False)),  # POST done=false
            _resp(_make_task_payload(14, repeat_after=0)),  # POST repeat_after=0
        ]
        snapshot = ms.rollback("http://test/api/v1/", "token", snap_path)
        # Three rollback_* entries appended (after the original 3).
        new_entries = [c for c in snapshot["applied_changes"] if c["op"].startswith("rollback_")]
        assert len(new_entries) == 3
        ops = [c["op"] for c in new_entries]
        # Reverse order: create first (rollback_create), then retire, then patch.
        assert ops == ["rollback_create", "rollback_retire", "rollback_patch"]
        # Verify the methods on each call.
        methods = [c[0][0].get_method() for c in mock_urlopen.call_args_list]
        assert methods == ["DELETE", "POST", "POST"]

    def test_skipped_entries_not_reversed(self, mock_urlopen, tmp_path):
        snap_path = tmp_path / "snapshot.json"
        snapshot = self._seed_snapshot(snap_path)
        # Mark the first applied_change as "skipped" — should be a no-op on rollback.
        snapshot["applied_changes"][0]["result"] = "skipped"
        snap_path.write_text(json.dumps(snapshot), encoding="utf-8")
        mock_urlopen.side_effect = [
            _resp(_make_task_payload(100)),  # create
            _resp(_make_task_payload(17, done=False)),  # retire
        ]
        result = ms.rollback("http://test/api/v1/", "token", snap_path)
        # Only 2 reversals (skip wasn't reversed).
        new_entries = [c for c in result["applied_changes"] if c["op"].startswith("rollback_")]
        assert len(new_entries) == 2

    def test_missing_snapshot_raises(self, tmp_path):
        with pytest.raises(ValueError, match="Snapshot file not found"):
            ms.rollback("http://test/api/v1/", "token", tmp_path / "nope.json")

    def test_invalid_json_raises(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("not json", encoding="utf-8")
        with pytest.raises(ValueError, match="not valid JSON"):
            ms.rollback("http://test/api/v1/", "token", path)

    def test_unsupported_schema_version_raises(self, tmp_path):
        path = tmp_path / "wrong-schema.json"
        path.write_text(json.dumps({"schema_version": "0", "applied_changes": []}), encoding="utf-8")
        with pytest.raises(ValueError, match="unsupported schema_version"):
            ms.rollback("http://test/api/v1/", "token", path)

    def test_mid_rollback_failure_persists_partial_state(self, mock_urlopen, tmp_path):
        snap_path = tmp_path / "snapshot.json"
        self._seed_snapshot(snap_path)
        mock_urlopen.side_effect = [
            _resp(_make_task_payload(100)),  # DELETE succeeds for the create
            _http_error(500),  # POST for retire fails
        ]
        with pytest.raises(OSError):
            ms.rollback("http://test/api/v1/", "token", snap_path)
        on_disk = json.loads(snap_path.read_text(encoding="utf-8"))
        rollback_entries = [c for c in on_disk["applied_changes"] if c["op"].startswith("rollback_")]
        # One success (create reversal) + one error (retire reversal).
        results = [c["result"] for c in rollback_entries]
        assert "success" in results
        assert "error" in results


# ---------------------------------------------------------------------------
# Group 6: persistence atomicity
# ---------------------------------------------------------------------------


class TestPersistSnapshot:
    def test_writes_atomic_via_tmp_rename(self, tmp_path):
        target = tmp_path / "snapshot.json"
        snapshot = {"schema_version": "1", "data": "x"}
        ms._persist_snapshot(snapshot, target)
        assert target.exists()
        loaded = json.loads(target.read_text(encoding="utf-8"))
        assert loaded == snapshot
        # No leftover .tmp file.
        assert not (tmp_path / "snapshot.json.tmp").exists()

    def test_subsequent_writes_overwrite_cleanly(self, tmp_path):
        target = tmp_path / "snap.json"
        ms._persist_snapshot({"v": 1}, target)
        ms._persist_snapshot({"v": 2}, target)
        ms._persist_snapshot({"v": 3}, target)
        loaded = json.loads(target.read_text(encoding="utf-8"))
        assert loaded == {"v": 3}

    def test_creates_parent_directory(self, tmp_path):
        target = tmp_path / "nested" / "deep" / "snap.json"
        ms._persist_snapshot({"v": 1}, target)
        assert target.exists()


# ---------------------------------------------------------------------------
# Group 7: CLI (subprocess + in-process)
# ---------------------------------------------------------------------------


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _run_cli(*args, env_extra=None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    # Strip the preflight gate from inherited env so each test controls it explicitly.
    env.pop(ms.PREFLIGHT_ENV_VAR, None)
    if env_extra and ms.PREFLIGHT_ENV_VAR in env_extra:
        env[ms.PREFLIGHT_ENV_VAR] = env_extra[ms.PREFLIGHT_ENV_VAR]
    # Provide a dummy URL so tests that don't pass --base-url can still reach
    # argument-validation checks without get_vikunja_base_url() failing.
    env.setdefault("VIKUNJA_BASE_URL", "https://vikunja.test/api/v1/")
    return subprocess.run(
        [sys.executable, "-m", "scripts.habits.migrate_schedule", *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


class TestCLI:
    def test_help_exits_zero(self):
        result = _run_cli("--help")
        assert result.returncode == 0
        assert "migrate_schedule" in result.stdout
        assert "--schedule" in result.stdout
        assert "--rollback" in result.stdout
        assert "--dry-run" in result.stdout

    def test_missing_schedule_arg_exits_2(self, tmp_path):
        # No --schedule and no --rollback.
        result = _run_cli(
            "--snapshot-out", str(tmp_path / "snap.json"),
            env_extra={ms.PREFLIGHT_ENV_VAR: "yes"},
        )
        assert result.returncode == 2
        assert "--schedule" in result.stderr

    def test_tier2_gate_blocks_without_env_var(self, tmp_path):
        schedule = _write_yaml(tmp_path, _minimal_valid_schedule_dict())
        result = _run_cli(
            "--schedule", str(schedule),
            "--snapshot-out", str(tmp_path / "snap.json"),
        )
        assert result.returncode == 3
        assert ms.PREFLIGHT_ENV_VAR in result.stderr

    def test_tier2_gate_allows_dry_run_without_env_var(self, tmp_path):
        # Dry-run bypasses the gate but still tries to read the token file.
        # We expect exit 3 due to missing token file (default path), proving
        # the gate did NOT fire (otherwise the error would come from the gate).
        schedule = _write_yaml(tmp_path, _minimal_valid_schedule_dict())
        token_file = tmp_path / "missing-token"
        result = _run_cli(
            "--schedule", str(schedule),
            "--snapshot-out", str(tmp_path / "snap.json"),
            "--token-file", str(token_file),
            "--dry-run",
        )
        # Should fail trying to read the token, not from the gate.
        assert result.returncode == 3
        assert ms.PREFLIGHT_ENV_VAR not in result.stderr
        assert "Token file not found" in result.stderr

    def test_rollback_without_snapshot_file_exits_2(self):
        result = _run_cli("--rollback")
        assert result.returncode == 2
        assert "--snapshot-file" in result.stderr

    def test_validation_error_exits_2(self, tmp_path):
        # Bad schedule: missing mission_id.
        bad = tmp_path / "bad.yaml"
        bad.write_text("operations: []\n", encoding="utf-8")
        token = tmp_path / "token"
        token.write_text("xxx", encoding="utf-8")
        result = _run_cli(
            "--schedule", str(bad),
            "--snapshot-out", str(tmp_path / "snap.json"),
            "--token-file", str(token),
            env_extra={ms.PREFLIGHT_ENV_VAR: "yes"},
        )
        assert result.returncode == 2
        assert "mission_id" in result.stderr


class TestCLIInProcess:
    """In-process CLI tests that exercise main() with mocked HTTP."""

    def test_dry_run_full_flow(self, mock_urlopen, tmp_path, monkeypatch, capsys):
        schedule = _write_yaml(tmp_path, _minimal_valid_schedule_dict())
        token = tmp_path / "token"
        token.write_text("test-token", encoding="utf-8")
        snap = tmp_path / "snap.json"
        mock_urlopen.side_effect = [
            _resp(_make_task_payload(14, title="Wake at 5:00 AM")),
            _resp(_make_task_payload(17, title="Workout")),
        ]
        monkeypatch.delenv(ms.PREFLIGHT_ENV_VAR, raising=False)
        rc = ms.main(
            [
                "--schedule", str(schedule),
                "--snapshot-out", str(snap),
                "--token-file", str(token),
                "--dry-run",
            ]
        )
        assert rc == 0
        captured = capsys.readouterr()
        assert "SUMMARY: dry-run complete" in captured.out
        # No mutation calls.
        methods = [c[0][0].get_method() for c in mock_urlopen.call_args_list]
        assert all(m == "GET" for m in methods)

    def test_apply_happy_path_in_process(self, mock_urlopen, tmp_path, monkeypatch):
        schedule = _write_yaml(tmp_path, _minimal_valid_schedule_dict())
        token = tmp_path / "token"
        token.write_text("test-token", encoding="utf-8")
        snap = tmp_path / "snap.json"
        mock_urlopen.side_effect = [
            _resp(_make_task_payload(14, title="Wake at 5:00 AM")),
            _resp(_make_task_payload(17, title="Workout", project_id=1)),
            _resp(_make_task_payload(14, repeat_after=86400)),
            _resp(_make_task_payload(17, done=True)),
            _resp(_make_task_payload(100, title="Strength training — Monday")),
        ]
        monkeypatch.setenv(ms.PREFLIGHT_ENV_VAR, "yes")
        rc = ms.main(
            [
                "--schedule", str(schedule),
                "--snapshot-out", str(snap),
                "--token-file", str(token),
            ]
        )
        assert rc == 0
        on_disk = json.loads(snap.read_text(encoding="utf-8"))
        assert len(on_disk["applied_changes"]) == 3

    def test_rollback_in_process(self, mock_urlopen, tmp_path, monkeypatch):
        # Seed a snapshot using TestRollback's helper layout.
        snap = tmp_path / "snap.json"
        TestRollback()._seed_snapshot(snap)
        token = tmp_path / "token"
        token.write_text("test-token", encoding="utf-8")
        mock_urlopen.side_effect = [
            _resp(_make_task_payload(100)),
            _resp(_make_task_payload(17, done=False)),
            _resp(_make_task_payload(14, repeat_after=0)),
        ]
        rc = ms.main(
            [
                "--rollback",
                "--snapshot-file", str(snap),
                "--token-file", str(token),
            ]
        )
        assert rc == 0

    def test_apply_mid_batch_failure_exits_1(self, mock_urlopen, tmp_path, monkeypatch):
        schedule = _write_yaml(tmp_path, _minimal_valid_schedule_dict())
        token = tmp_path / "token"
        token.write_text("test-token", encoding="utf-8")
        snap = tmp_path / "snap.json"
        mock_urlopen.side_effect = [
            _resp(_make_task_payload(14, title="Wake")),
            _resp(_make_task_payload(17, title="Workout")),
            _resp(_make_task_payload(14, repeat_after=86400)),
            _http_error(500),
        ]
        monkeypatch.setenv(ms.PREFLIGHT_ENV_VAR, "yes")
        rc = ms.main(
            [
                "--schedule", str(schedule),
                "--snapshot-out", str(snap),
                "--token-file", str(token),
            ]
        )
        assert rc == 1

    def test_apply_missing_token_file_exits_3(self, tmp_path, monkeypatch):
        schedule = _write_yaml(tmp_path, _minimal_valid_schedule_dict())
        monkeypatch.setenv(ms.PREFLIGHT_ENV_VAR, "yes")
        rc = ms.main(
            [
                "--schedule", str(schedule),
                "--snapshot-out", str(tmp_path / "snap.json"),
                "--token-file", str(tmp_path / "missing"),
            ]
        )
        assert rc == 3


# ---------------------------------------------------------------------------
# Group 8: _http_request edge cases (defensive coverage)
# ---------------------------------------------------------------------------


class TestHTTPRequest:
    def test_get_returns_parsed_dict(self, mock_urlopen):
        mock_urlopen.return_value = _resp({"id": 1, "title": "Test"})
        status, body = ms._http_request("GET", "http://test/tasks/1", "token")
        assert status == 200
        assert body == {"id": 1, "title": "Test"}

    def test_empty_body_returns_none(self, mock_urlopen):
        # 204-style empty body — parsed should be None.
        mock_urlopen.return_value = _resp(None)
        status, body = ms._http_request("DELETE", "http://test/tasks/1", "token")
        assert body is None

    def test_non_json_body_raises(self, mock_urlopen):
        cm = MagicMock()
        resp = MagicMock()
        resp.status = 200
        resp.read = MagicMock(return_value=b"<html>not json</html>")
        cm.__enter__ = MagicMock(return_value=resp)
        cm.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = cm
        with pytest.raises(OSError, match="non-JSON body"):
            ms._http_request("GET", "http://test/x", "token")

    def test_post_sends_json_body(self, mock_urlopen):
        mock_urlopen.return_value = _resp({"ok": True})
        ms._http_request("POST", "http://test/x", "token", body={"done": True})
        called_req = mock_urlopen.call_args[0][0]
        assert called_req.get_method() == "POST"
        assert json.loads(called_req.data.decode("utf-8")) == {"done": True}
        assert called_req.headers["Content-type"] == "application/json"
        assert called_req.headers["Authorization"] == "Bearer token"

    def test_fetch_task_non_object_raises(self, mock_urlopen):
        # Vikunja returning a JSON array instead of object is a contract violation.
        mock_urlopen.return_value = _resp([1, 2, 3])
        with pytest.raises(OSError, match="non-object body"):
            ms._fetch_task("http://test/api/v1/", "token", 14)

    def test_apply_patch_non_object_raises(self, mock_urlopen):
        mock_urlopen.return_value = _resp([1, 2])
        with pytest.raises(OSError, match="non-object body"):
            ms._apply_patch(
                "http://test/api/v1/",
                "token",
                {"task_id": 14, "target": {"repeat_after": 86400, "repeat_mode": 0}},
            )

    def test_apply_retire_non_object_raises(self, mock_urlopen):
        mock_urlopen.return_value = _resp([])
        with pytest.raises(OSError, match="non-object body"):
            ms._apply_retire(
                "http://test/api/v1/", "token", {"task_id": 17}
            )

    def test_apply_create_non_object_raises(self, mock_urlopen):
        mock_urlopen.return_value = _resp([])
        with pytest.raises(OSError, match="non-object body"):
            ms._apply_create(
                "http://test/api/v1/",
                "token",
                {
                    "schedule": {"repeat_after": 86400, "repeat_mode": 0},
                    "attributes": {"title": "Test task", "project_id": 1},
                },
            )


# ---------------------------------------------------------------------------
# Group 9: Misc edge cases for coverage
# ---------------------------------------------------------------------------


class TestMiscEdges:
    def test_invalid_repeat_mode_boolean(self, tmp_path):
        data = _minimal_valid_schedule_dict()
        data["operations"][0]["target"]["repeat_mode"] = True  # bool
        path = _write_yaml(tmp_path, data)
        with pytest.raises(ValueError, match="'target.repeat_mode' must be an integer"):
            ms.load_schedule(path)

    def test_empty_due_date_string(self, tmp_path):
        data = _minimal_valid_schedule_dict()
        data["operations"][2]["attributes"]["due_date"] = ""
        path = _write_yaml(tmp_path, data)
        with pytest.raises(ValueError, match="non-empty ISO-8601 string"):
            ms.load_schedule(path)

    def test_non_string_due_date(self, tmp_path):
        data = _minimal_valid_schedule_dict()
        data["operations"][2]["attributes"]["due_date"] = 12345
        path = _write_yaml(tmp_path, data)
        with pytest.raises(ValueError, match="non-empty ISO-8601 string"):
            ms.load_schedule(path)

    def test_cli_load_schedule_oserror_exits_3(self, tmp_path, monkeypatch):
        # Schedule path exists but read raises OSError. Simulate via passing
        # a directory as the schedule path.
        token = tmp_path / "token"
        token.write_text("test-token", encoding="utf-8")
        bogus_dir = tmp_path / "schedule_dir"
        bogus_dir.mkdir()
        monkeypatch.setenv(ms.PREFLIGHT_ENV_VAR, "yes")
        rc = ms.main(
            [
                "--schedule", str(bogus_dir),
                "--snapshot-out", str(tmp_path / "snap.json"),
                "--token-file", str(token),
            ]
        )
        assert rc == 3

    def test_cli_rollback_invalid_snapshot_exits_2(self, tmp_path, monkeypatch):
        token = tmp_path / "token"
        token.write_text("test-token", encoding="utf-8")
        bad_snap = tmp_path / "bad.json"
        bad_snap.write_text("not json", encoding="utf-8")
        rc = ms.main(
            [
                "--rollback",
                "--snapshot-file", str(bad_snap),
                "--token-file", str(token),
            ]
        )
        assert rc == 2

    def test_cli_rollback_missing_token_exits_3(self, tmp_path):
        rc = ms.main(
            [
                "--rollback",
                "--snapshot-file", str(tmp_path / "snap.json"),
                "--token-file", str(tmp_path / "missing-token"),
            ]
        )
        assert rc == 3

    def test_cli_rollback_oserror_exits_1(self, mock_urlopen, tmp_path, monkeypatch):
        token = tmp_path / "token"
        token.write_text("test-token", encoding="utf-8")
        snap = tmp_path / "snap.json"
        TestRollback()._seed_snapshot(snap)
        # First reversal call (DELETE for the create) fails.
        mock_urlopen.side_effect = _http_error(500)
        rc = ms.main(
            [
                "--rollback",
                "--snapshot-file", str(snap),
                "--token-file", str(token),
            ]
        )
        assert rc == 1

    def test_cli_schedule_validation_oserror_exits_3(self, tmp_path, monkeypatch):
        # Missing schedule file → OSError → exit 3.
        token = tmp_path / "token"
        token.write_text("test-token", encoding="utf-8")
        monkeypatch.setenv(ms.PREFLIGHT_ENV_VAR, "yes")
        rc = ms.main(
            [
                "--schedule", str(tmp_path / "missing.yaml"),
                "--snapshot-out", str(tmp_path / "snap.json"),
                "--token-file", str(token),
            ]
        )
        assert rc == 3

    def test_token_file_empty_exits_3(self, tmp_path, monkeypatch):
        schedule = _write_yaml(tmp_path, _minimal_valid_schedule_dict())
        token = tmp_path / "empty-token"
        token.write_text("", encoding="utf-8")
        monkeypatch.setenv(ms.PREFLIGHT_ENV_VAR, "yes")
        rc = ms.main(
            [
                "--schedule", str(schedule),
                "--snapshot-out", str(tmp_path / "snap.json"),
                "--token-file", str(token),
            ]
        )
        assert rc == 3

    def test_apply_schedule_value_error_exits_2(self, mock_urlopen, tmp_path, monkeypatch):
        # Retire op against task with repeat_after != 0 → ValueError mid-apply.
        schedule_data = {
            "mission_id": "01KS0M59313RF0WVJZTXYDJC6C",
            "operations": [
                {"op": "retire", "task_id": 17},
            ],
        }
        schedule = _write_yaml(tmp_path, schedule_data)
        token = tmp_path / "token"
        token.write_text("test-token", encoding="utf-8")
        mock_urlopen.side_effect = [
            _resp(_make_task_payload(17, repeat_after=604800)),
        ]
        monkeypatch.setenv(ms.PREFLIGHT_ENV_VAR, "yes")
        rc = ms.main(
            [
                "--schedule", str(schedule),
                "--snapshot-out", str(tmp_path / "snap.json"),
                "--token-file", str(token),
            ]
        )
        assert rc == 2
