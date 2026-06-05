"""Tests for scripts/sync/cleanup.py — Deletion-Cleanup Helpers (WP02).

Covers:
  - append_task_deleted_event: happy path, multiple events, parent-dir
    creation, invalid task_id validation.
  - prune_schedule_yaml: happy path, idempotency, missing entry, missing
    file, malformed YAML, and (if ruamel available) comment preservation.

All file I/O uses pytest's ``tmp_path`` fixture. No live network calls,
no production filesystem paths.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.sync.cleanup import (
    _USING_RUAMEL,
    append_task_deleted_event,
    prune_schedule_yaml,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_schedule_yaml(habits: list[dict]) -> str:
    """Return a minimal schedule YAML string with the given habits list."""
    lines = ["habits:"]
    if habits:
        for h in habits:
            # Emit a simple block-sequence entry for each habit dict.
            first = True
            for k, v in h.items():
                prefix = "  - " if first else "    "
                if isinstance(v, str):
                    lines.append(f"{prefix}{k}: {json.dumps(v)}")
                else:
                    lines.append(f"{prefix}{k}: {v}")
                first = False
    else:
        lines.append("  []")
    return "\n".join(lines) + "\n"


def _make_schedule_yaml_with_comment(habits: list[dict], comment: str) -> str:
    """Return a schedule YAML with a leading comment above the habits list."""
    body = _make_schedule_yaml(habits)
    return f"# {comment}\n{body}"


def _read_lines(path: Path) -> list[str]:
    """Read non-empty lines from a file."""
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line]


# ---------------------------------------------------------------------------
# append_task_deleted_event — scenario 1: happy path
# ---------------------------------------------------------------------------


def test_append_task_deleted_event_happy_path(tmp_path: Path) -> None:
    """Appending one event writes a valid JSON line with the expected schema."""
    target = tmp_path / "test.jsonl"
    append_task_deleted_event(
        task_id=42,
        title="Wake at 5:00 AM",
        detected_at_utc="2026-06-05T20:00:00Z",
        path=target,
    )

    assert target.exists()
    lines = _read_lines(target)
    assert len(lines) == 1

    event = json.loads(lines[0])
    assert event["event_type"] == "task_deleted"
    assert event["task_id"] == 42
    assert event["title"] == "Wake at 5:00 AM"
    assert event["detected_at_utc"] == "2026-06-05T20:00:00Z"
    assert event["schema_version"] == 1


# ---------------------------------------------------------------------------
# append_task_deleted_event — scenario 2: multiple events
# ---------------------------------------------------------------------------


def test_append_task_deleted_event_multiple(tmp_path: Path) -> None:
    """Three consecutive appends produce three parseable JSON lines in order."""
    target = tmp_path / "history.jsonl"
    events_in = [
        (14, "Wake at 5:00 AM", "2026-06-05T20:00:00Z"),
        (15, "Meditate", "2026-06-05T20:00:01Z"),
        (16, "Morning shoulder PT", "2026-06-05T20:00:02Z"),
    ]
    for task_id, title, ts in events_in:
        append_task_deleted_event(
            task_id=task_id,
            title=title,
            detected_at_utc=ts,
            path=target,
        )

    lines = _read_lines(target)
    assert len(lines) == 3

    for i, (task_id, title, ts) in enumerate(events_in):
        event = json.loads(lines[i])
        assert event["task_id"] == task_id
        assert event["title"] == title
        assert event["detected_at_utc"] == ts


# ---------------------------------------------------------------------------
# append_task_deleted_event — scenario 3: creates parent directories
# ---------------------------------------------------------------------------


def test_append_task_deleted_event_creates_parent_dirs(tmp_path: Path) -> None:
    """Parent directories are created automatically when they don't exist."""
    target = tmp_path / "nested" / "dir" / "test.jsonl"
    assert not target.parent.exists()

    append_task_deleted_event(
        task_id=99,
        title="Some habit",
        detected_at_utc="2026-06-05T20:00:00Z",
        path=target,
    )

    assert target.exists()
    event = json.loads(target.read_text(encoding="utf-8").strip())
    assert event["task_id"] == 99


# ---------------------------------------------------------------------------
# append_task_deleted_event — scenario 4: invalid task_id raises ValueError
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_task_id",
    [
        -1,
        0,
        "not-an-int",
        3.14,
        None,
        True,   # bool is a subclass of int in Python, but not a valid task_id
    ],
    ids=["negative", "zero", "string", "float", "none", "bool"],
)
def test_append_task_deleted_event_invalid_task_id(
    tmp_path: Path, bad_task_id: object
) -> None:
    """Non-positive or non-integer task_id raises ValueError before any write."""
    target = tmp_path / "test.jsonl"
    with pytest.raises(ValueError, match="task_id must be a positive integer"):
        append_task_deleted_event(
            task_id=bad_task_id,  # type: ignore[arg-type]
            title="Irrelevant",
            detected_at_utc="2026-06-05T20:00:00Z",
            path=target,
        )
    # File must NOT have been created.
    assert not target.exists()


# ---------------------------------------------------------------------------
# prune_schedule_yaml — scenario 5: happy path
# ---------------------------------------------------------------------------


def test_prune_schedule_yaml_happy_path(tmp_path: Path) -> None:
    """Pruning task_id=2 from a 3-entry schedule removes it and returns True."""
    habits = [
        {"task_id": 1, "title": "Habit one", "repeat_after_seconds": 86400},
        {"task_id": 2, "title": "Habit two", "repeat_after_seconds": 86400},
        {"task_id": 3, "title": "Habit three", "repeat_after_seconds": 86400},
    ]
    path = tmp_path / "schedule.yaml"
    path.write_text(_make_schedule_yaml(habits), encoding="utf-8")

    result = prune_schedule_yaml(2, path)
    assert result is True

    # Re-read and verify.
    import yaml  # stdlib fallback always available
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    remaining_ids = [entry["task_id"] for entry in data["habits"]]
    assert remaining_ids == [1, 3]


# ---------------------------------------------------------------------------
# prune_schedule_yaml — scenario 6: idempotent (second call returns False)
# ---------------------------------------------------------------------------


def test_prune_schedule_yaml_idempotent(tmp_path: Path) -> None:
    """Second call for the same task_id returns False and leaves file unchanged."""
    habits = [
        {"task_id": 1, "title": "Habit one", "repeat_after_seconds": 86400},
        {"task_id": 2, "title": "Habit two", "repeat_after_seconds": 86400},
        {"task_id": 3, "title": "Habit three", "repeat_after_seconds": 86400},
    ]
    path = tmp_path / "schedule.yaml"
    path.write_text(_make_schedule_yaml(habits), encoding="utf-8")

    first = prune_schedule_yaml(2, path)
    assert first is True

    second = prune_schedule_yaml(2, path)
    assert second is False

    # File should now have 2 entries (1 and 3).
    import yaml
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    remaining_ids = [entry["task_id"] for entry in data["habits"]]
    assert remaining_ids == [1, 3]


# ---------------------------------------------------------------------------
# prune_schedule_yaml — scenario 7: missing entry returns False
# ---------------------------------------------------------------------------


def test_prune_schedule_yaml_missing_entry(tmp_path: Path) -> None:
    """Pruning a task_id not in the schedule returns False; file unchanged."""
    habits = [
        {"task_id": 1, "title": "Habit one", "repeat_after_seconds": 86400},
        {"task_id": 3, "title": "Habit three", "repeat_after_seconds": 86400},
    ]
    path = tmp_path / "schedule.yaml"
    original_text = _make_schedule_yaml(habits)
    path.write_text(original_text, encoding="utf-8")

    result = prune_schedule_yaml(2, path)
    assert result is False

    # File must be unchanged (same task_ids).
    import yaml
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    remaining_ids = [entry["task_id"] for entry in data["habits"]]
    assert remaining_ids == [1, 3]


# ---------------------------------------------------------------------------
# prune_schedule_yaml — scenario 8: missing file returns False (no exception)
# ---------------------------------------------------------------------------


def test_prune_schedule_yaml_missing_file(tmp_path: Path) -> None:
    """A non-existent file returns False without raising an exception."""
    path = tmp_path / "nonexistent.yaml"
    assert not path.exists()

    result = prune_schedule_yaml(1, path)
    assert result is False


# ---------------------------------------------------------------------------
# prune_schedule_yaml — scenario 9: malformed YAML raises ValueError
# ---------------------------------------------------------------------------


def test_prune_schedule_yaml_malformed_yaml(tmp_path: Path) -> None:
    """A YAML file whose top-level value is not a dict raises ValueError."""
    # Write a YAML that is a list at the top level (missing the habits: key).
    path = tmp_path / "bad_schedule.yaml"
    path.write_text(
        "- task_id: 1\n  title: Oops\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="top-level mapping"):
        prune_schedule_yaml(1, path)


# ---------------------------------------------------------------------------
# prune_schedule_yaml — scenario 10: preserves comments (ruamel only)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _USING_RUAMEL,
    reason="ruamel.yaml not installed; comment-preservation test skipped",
)
def test_prune_schedule_yaml_preserves_comments(tmp_path: Path) -> None:
    """After pruning, the leading comment block is still present in the file."""
    comment_line = "# THIS COMMENT MUST SURVIVE THE ROUND-TRIP"
    yaml_content = (
        f"{comment_line}\n"
        "habits:\n"
        "  - task_id: 1\n"
        "    title: \"Habit one\"\n"
        "    repeat_after_seconds: 86400\n"
        "  - task_id: 2\n"
        "    title: \"Habit two\"\n"
        "    repeat_after_seconds: 86400\n"
        "  - task_id: 3\n"
        "    title: \"Habit three\"\n"
        "    repeat_after_seconds: 86400\n"
    )
    path = tmp_path / "schedule_with_comment.yaml"
    path.write_text(yaml_content, encoding="utf-8")

    result = prune_schedule_yaml(2, path)
    assert result is True

    written = path.read_text(encoding="utf-8")
    assert comment_line in written, (
        f"Comment was lost after round-trip.\nFile contents:\n{written}"
    )

    # Also verify task_id=2 is gone from the output.
    assert "task_id: 2" not in written
    assert "task_id: 1" in written
    assert "task_id: 3" in written
