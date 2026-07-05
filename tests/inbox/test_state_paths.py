"""Tests for WP02 — relocated inbox state file path constants.

Verifies:
  - Both defaults equal the canonical /data/services/openclaw/state/... paths.
  - Paths are independent of HOME and cwd (absolute anchors, not ~ derived).
  - Round-trip write+read via the routing-log reader/writer.
  - Missing file → fail-safe empty result (no exception).
  - Parent-dir creation uses mode not more restrictive than 0o750.
"""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

import routing_log
import handle_clarification_state
from routing_log import DEFAULT_ROUTING_LOG_PATH, RoutingLogReader, RoutingLogWriter
from handle_clarification_state import STATE_PATH_DEFAULT, load_state, save_state


# ---------------------------------------------------------------------------
# T006a — absolute path values
# ---------------------------------------------------------------------------

STATE_DIR = Path("/data/services/openclaw/state")


def test_routing_log_default_path():
    assert DEFAULT_ROUTING_LOG_PATH == STATE_DIR / "inbox-routing.jsonl"


def test_clarification_state_default_path():
    assert STATE_PATH_DEFAULT == STATE_DIR / "pending-calendar-clarifications.json"


# ---------------------------------------------------------------------------
# T006b — path independence from HOME and cwd
# ---------------------------------------------------------------------------


def test_routing_log_path_independent_of_home(tmp_path, monkeypatch):
    """Changing HOME must not affect the resolved default."""
    monkeypatch.setenv("HOME", str(tmp_path))
    # Re-read the attribute through the module so monkeypatch on the *module*
    # attribute (if ever needed) would also be reflected.
    path = routing_log.DEFAULT_ROUTING_LOG_PATH
    assert path == STATE_DIR / "inbox-routing.jsonl"
    # Path must be absolute — no HOME-relative components.
    assert path.is_absolute()


def test_clarification_state_path_independent_of_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    path = handle_clarification_state.STATE_PATH_DEFAULT
    assert path == STATE_DIR / "pending-calendar-clarifications.json"
    assert path.is_absolute()


def test_routing_log_path_independent_of_cwd(tmp_path, monkeypatch):
    """Changing cwd must not affect the resolved default."""
    monkeypatch.chdir(tmp_path)
    path = routing_log.DEFAULT_ROUTING_LOG_PATH
    assert path == STATE_DIR / "inbox-routing.jsonl"


def test_clarification_state_path_independent_of_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = handle_clarification_state.STATE_PATH_DEFAULT
    assert path == STATE_DIR / "pending-calendar-clarifications.json"


# ---------------------------------------------------------------------------
# T006c — call-time monkeypatch support (preserve sys.modules resolution)
# ---------------------------------------------------------------------------


def test_routing_log_reader_honors_monkeypatched_default(tmp_path, monkeypatch):
    """RoutingLogReader(path=None) must pick up a monkeypatched DEFAULT_ROUTING_LOG_PATH."""
    custom = tmp_path / "custom.jsonl"
    monkeypatch.setattr(routing_log, "DEFAULT_ROUTING_LOG_PATH", custom)
    reader = RoutingLogReader()  # path=None → resolves via sys.modules[__name__]
    assert reader._path == custom


# ---------------------------------------------------------------------------
# T006d — round-trip: writer then reader
# ---------------------------------------------------------------------------


def test_routing_log_round_trip(tmp_path):
    log_path = tmp_path / "inbox-routing.jsonl"
    writer = RoutingLogWriter(path=log_path)
    entry = writer.append(
        filename="note-abc.md",
        issue_number=42,
        vikunja_task_id=7,
        note_excerpt="hello world",
    )
    reader = RoutingLogReader(path=log_path)
    names = reader.routed_filenames()
    assert "note-abc.md" in names
    assert entry.issue_number == 42


# ---------------------------------------------------------------------------
# T006e — missing file → fail-safe empty result (no exception)
# ---------------------------------------------------------------------------


def test_routing_log_missing_file_returns_empty_set(tmp_path):
    reader = RoutingLogReader(path=tmp_path / "does-not-exist.jsonl")
    assert reader.routed_filenames() == set()


def test_clarification_state_missing_file_returns_empty_list(tmp_path):
    result = load_state(tmp_path / "does-not-exist.json")
    assert result == []


def test_clarification_state_round_trip(tmp_path):
    path = tmp_path / "pending.json"
    entries = [{"note_filename": "x.md", "partial_payload": {"title": "Lunch"}, "created_at": "2026-01-01T00:00:00Z"}]
    save_state(path, entries)
    loaded = load_state(path)
    assert loaded == entries


# ---------------------------------------------------------------------------
# T006f — parent-dir mode not more restrictive than 0750
# ---------------------------------------------------------------------------


def test_routing_log_parent_dir_mode(tmp_path):
    """mkdir in RoutingLogWriter must not create a dir more restrictive than 0750."""
    log_path = tmp_path / "sub" / "inbox-routing.jsonl"
    writer = RoutingLogWriter(path=log_path)
    writer.append(filename="a.md", issue_number=1)
    parent_mode = stat.S_IMODE(os.stat(log_path.parent).st_mode)
    # 0o750 allows group read+execute; 0o700 would be more restrictive.
    # Check that group-read bit (0o040) is set.
    assert parent_mode & 0o040, (
        f"parent dir mode {oct(parent_mode)} is more restrictive than 0o750 "
        "(group-read bit not set)"
    )


def test_clarification_state_parent_dir_mode(tmp_path):
    """save_state mkdir must not create a dir more restrictive than 0750."""
    path = tmp_path / "sub" / "pending.json"
    save_state(path, [])
    parent_mode = stat.S_IMODE(os.stat(path.parent).st_mode)
    assert parent_mode & 0o040, (
        f"parent dir mode {oct(parent_mode)} is more restrictive than 0o750 "
        "(group-read bit not set)"
    )


# --- FR-012/SC-9: newly-created state files must be 0640 (Codex #2 H1) ---

def test_routing_log_new_file_is_0640(tmp_path):
    import os as _os
    import scripts.inbox.routing_log as rl
    p = tmp_path / "state" / "inbox-routing.jsonl"
    old = _os.umask(0o077)  # hostile umask: proves we chmod explicitly
    try:
        rl.RoutingLogWriter(path=p).append(filename="n.md", issue_number=1, vikunja_task_id=None)
    finally:
        _os.umask(old)
    assert (p.stat().st_mode & 0o777) == 0o640


def test_clarification_state_file_is_0640(tmp_path):
    import os as _os
    import scripts.inbox.handle_clarification_state as hcs
    p = tmp_path / "state" / "pending-calendar-clarifications.json"
    old = _os.umask(0o077)
    try:
        hcs.save_state(p, [])  # save_state(path, entries)
    finally:
        _os.umask(old)
    assert (p.stat().st_mode & 0o777) == 0o640
