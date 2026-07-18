"""#740 — prescan withholds notes awaiting a calendar clarification reply.

When a calendar-classified inbox note is incomplete, the capture agent records a
``pending-calendar-clarifications`` entry and leaves the note unprocessed while
it waits on Kent. Before this fix ``prescan`` re-listed such a note every tick
(dedup only skipped terminal-``status`` notes), so the agent re-classified and
re-WhatsApp'd Kent 4×/day until the 24h sweep aged the entry out.

These tests prove prescan now filters a note with a *live* pending entry out of
``unprocessed_paths`` (surfacing it in ``pending_skipped``), that an aged-out /
absent entry does NOT withhold the note (the loop is bounded, not stranding),
and that an unreadable clarification store fails safe (note still handed over).
"""
from __future__ import annotations

import io
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Match the sibling prescan tests' module-aliasing so the routing_log object
# prescan imports package-qualified is the same one conftest put on sys.path.
import routing_log as _routing_log_mod  # noqa: E402
sys.modules.setdefault("scripts.inbox.routing_log", _routing_log_mod)

import prescan  # noqa: E402
from scripts.inbox import handle_clarification_state as hcs  # noqa: E402


NOW = datetime(2026, 7, 18, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


def _write_unprocessed(path: Path, body: str = "Body.\n") -> None:
    path.write_text(f"---\nstatus: unprocessed\n---\n\n{body}", encoding="utf-8")


def _write_pending_state(path: Path, entries: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries), encoding="utf-8")


def _entry(note_filename: str, created: datetime) -> dict:
    return {
        "note_filename": note_filename,
        "partial_payload": {"title": "Meet Rob"},
        "created_at": created.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _run_prescan(inbox: Path, processed: Path, state_file: Path, monkeypatch) -> dict:
    registry = inbox.parent / "registry.json"
    registry.write_text(
        json.dumps(
            {"paths": {"inbox": str(inbox), "inbox_processed": str(processed)}}
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("PRESCAN_REGISTRY_PATH", str(registry))
    log_dir = inbox.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PRESCAN_LOG_DIR", str(log_dir))
    # Point the clarification-state lookup at the test's file. prescan's helper
    # reads handle_clarification_state.STATE_PATH_DEFAULT at call time.
    monkeypatch.setattr(hcs, "STATE_PATH_DEFAULT", state_file)

    captured = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured)
    rc = prescan.run_prescan()
    sys.stdout = sys.__stdout__
    assert rc == 0, f"run_prescan returned {rc}"
    return json.loads(captured.getvalue().strip().splitlines()[-1])


def _setup(tmp_path: Path) -> tuple[Path, Path, Path]:
    inbox = tmp_path / "inbox"
    processed = tmp_path / "processed"
    inbox.mkdir()
    processed.mkdir()
    state_file = tmp_path / "state" / "pending-calendar-clarifications.json"
    return inbox, processed, state_file


# ---------------------------------------------------------------------------
# Integration: run_prescan skip behavior
# ---------------------------------------------------------------------------


def test_note_with_live_pending_entry_is_withheld(tmp_path, monkeypatch):
    # run_prescan reads the real wall clock, so anchor the entry to real now
    # (a fixed future constant would be treated as not-live and released).
    live = datetime.now(timezone.utc) - timedelta(hours=1)
    inbox, processed, state = _setup(tmp_path)
    _write_unprocessed(inbox / "Inbox 2026-07-18 0900.md")
    _write_pending_state(
        state, [_entry("Inbox 2026-07-18 0900.md", live)]
    )
    result = _run_prescan(inbox, processed, state, monkeypatch)

    assert result["unprocessed_count"] == 0
    assert result["unprocessed_paths"] == []
    assert [e["filename"] for e in result["pending_skipped"]] == [
        "Inbox 2026-07-18 0900.md"
    ]


def test_aged_out_pending_entry_releases_the_note(tmp_path, monkeypatch):
    inbox, processed, state = _setup(tmp_path)
    _write_unprocessed(inbox / "Inbox 2026-07-18 0900.md")
    # created 30h ago → past the 24h sweep window → not pending anymore.
    _write_pending_state(
        state, [_entry("Inbox 2026-07-18 0900.md", datetime.now(timezone.utc) - timedelta(hours=30))]
    )
    result = _run_prescan(inbox, processed, state, monkeypatch)

    assert result["unprocessed_count"] == 1
    assert result["pending_skipped"] == []
    assert result["unprocessed_paths"][0].endswith("Inbox 2026-07-18 0900.md")


def test_absent_state_file_hands_note_over(tmp_path, monkeypatch):
    inbox, processed, state = _setup(tmp_path)  # state file never created
    _write_unprocessed(inbox / "Inbox 2026-07-18 0900.md")
    result = _run_prescan(inbox, processed, state, monkeypatch)

    assert result["unprocessed_count"] == 1
    assert result["pending_skipped"] == []
    # No warning for an absent (normal, nothing-pending) state file.
    assert not any("clarification" in w.get("reason", "") for w in result["warnings"])


def test_only_the_pending_note_is_withheld(tmp_path, monkeypatch):
    live = datetime.now(timezone.utc) - timedelta(hours=2)
    inbox, processed, state = _setup(tmp_path)
    _write_unprocessed(inbox / "pending.md")
    _write_unprocessed(inbox / "ready.md")
    _write_pending_state(state, [_entry("pending.md", live)])
    result = _run_prescan(inbox, processed, state, monkeypatch)

    assert result["unprocessed_count"] == 1
    assert result["unprocessed_paths"][0].endswith("ready.md")
    assert [e["filename"] for e in result["pending_skipped"]] == ["pending.md"]


def test_malformed_created_at_does_not_strand_the_note(tmp_path, monkeypatch):
    """#740 Finding 1: a valid-JSON array with one entry whose ``created_at`` is
    malformed must NOT withhold the note indefinitely — it fails open (released),
    so a bad stamp can never silently strand a note (the #746/D9 class)."""
    inbox, processed, state = _setup(tmp_path)
    _write_unprocessed(inbox / "Inbox 2026-07-18 0900.md")
    _write_pending_state(
        state,
        [
            {
                "note_filename": "Inbox 2026-07-18 0900.md",
                "partial_payload": {"title": "Meet Rob"},
                "created_at": "totally-not-a-timestamp",
            }
        ],
    )
    result = _run_prescan(inbox, processed, state, monkeypatch)
    assert result["unprocessed_count"] == 1
    assert result["pending_skipped"] == []
    assert result["unprocessed_paths"][0].endswith("Inbox 2026-07-18 0900.md")


def test_unreadable_state_fails_safe_with_warning(tmp_path, monkeypatch):
    inbox, processed, state = _setup(tmp_path)
    _write_unprocessed(inbox / "note.md")
    # Corrupt (non-JSON) state → helper raises internally → fail-safe: note is
    # still handed over, and a warning is surfaced (not withheld on a bad read).
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text("{ this is not json", encoding="utf-8")
    result = _run_prescan(inbox, processed, state, monkeypatch)

    assert result["unprocessed_count"] == 1
    assert result["pending_skipped"] == []
    assert any("clarification" in w.get("reason", "") for w in result["warnings"])


# ---------------------------------------------------------------------------
# Unit: _pending_clarification_filenames fail-safe wrapper
# ---------------------------------------------------------------------------


def test_pending_helper_returns_names_no_warning(tmp_path, monkeypatch):
    state = tmp_path / "pending.json"
    _write_pending_state(state, [_entry("a.md", NOW - timedelta(hours=1))])
    monkeypatch.setattr(hcs, "STATE_PATH_DEFAULT", state)
    names, warning = prescan._pending_clarification_filenames(NOW)
    assert names == {"a.md"}
    assert warning is None


def test_pending_helper_corrupt_file_returns_empty_and_warning(tmp_path, monkeypatch):
    state = tmp_path / "pending.json"
    state.write_text("not json", encoding="utf-8")
    monkeypatch.setattr(hcs, "STATE_PATH_DEFAULT", state)
    names, warning = prescan._pending_clarification_filenames(NOW)
    assert names == set()
    assert warning is not None and "clarification" in warning["reason"]
