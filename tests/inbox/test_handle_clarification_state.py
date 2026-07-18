"""Unit tests for `scripts.inbox.handle_clarification_state`.

Covers FR-006, FR-010, FR-015 from the
capture-d6-helpers-extraction-01KTMS5Q mission spec.

Subcommands under test:
  - add    — append a PendingClarification to the state file
  - sweep  — delete entries with `created_at` >= 24h old (safe on missing file)
  - match  — return the most-recent entry whose title appears (case-
             insensitive substring) in the incoming reply

State file layout: JSON array of PendingClarification objects:
  {"note_filename": str, "partial_payload": dict, "created_at": ISO 8601 UTC}

All tests use `tmp_path` for isolation; nothing touches real second-brain paths.
Invocation form in tests/docs is `python3 -m scripts.inbox.handle_clarification_state`
(per NFR-004 / [[feedback_helper_m_invocation_form]]).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# Bring scripts/ onto sys.path so we can `import scripts.inbox.handle_clarification_state`.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.inbox import handle_clarification_state as hcs  # noqa: E402


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _iso_z(dt: datetime) -> str:
    """Format `dt` as ISO 8601 with `Z` suffix (UTC)."""
    return dt.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_state(path: Path) -> list:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_state(path: Path, entries: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries), encoding="utf-8")


# --------------------------------------------------------------------------
# add
# --------------------------------------------------------------------------


def test_add_creates_state_file_when_absent(tmp_path: Path) -> None:
    state_path = tmp_path / "state-dir" / "pending.json"
    assert not state_path.exists()
    assert not state_path.parent.exists()

    rc = hcs.main(
        [
            "add",
            "--note-filename",
            "Inbox 2026-06-08 0712.md",
            "--partial-payload",
            json.dumps({"title": "Meet with Rob"}),
            "--state-file",
            str(state_path),
        ]
    )

    assert rc == 0
    assert state_path.exists()
    entries = _read_state(state_path)
    assert len(entries) == 1
    assert entries[0]["note_filename"] == "Inbox 2026-06-08 0712.md"
    assert entries[0]["partial_payload"] == {"title": "Meet with Rob"}
    assert entries[0]["created_at"].endswith("Z")


def test_add_appends_to_existing_state_file(tmp_path: Path) -> None:
    state_path = tmp_path / "pending.json"
    _write_state(
        state_path,
        [
            {
                "note_filename": "Inbox 2026-06-08 0712.md",
                "partial_payload": {"title": "Meet with Rob"},
                "created_at": _iso_z(datetime.now(timezone.utc)),
            }
        ],
    )

    rc = hcs.main(
        [
            "add",
            "--note-filename",
            "Inbox 2026-06-08 0800.md",
            "--partial-payload",
            json.dumps({"title": "Coffee with Pat"}),
            "--state-file",
            str(state_path),
        ]
    )

    assert rc == 0
    entries = _read_state(state_path)
    assert len(entries) == 2
    assert entries[1]["note_filename"] == "Inbox 2026-06-08 0800.md"
    assert entries[1]["partial_payload"] == {"title": "Coffee with Pat"}


def test_add_atomic_write_no_tempfile_on_success(tmp_path: Path) -> None:
    state_path = tmp_path / "pending.json"

    rc = hcs.main(
        [
            "add",
            "--note-filename",
            "n.md",
            "--partial-payload",
            json.dumps({"title": "T"}),
            "--state-file",
            str(state_path),
        ]
    )

    assert rc == 0
    # Atomic-write contract: no .tmp sibling left in parent.
    leftovers = [p for p in state_path.parent.iterdir() if p.suffix == ".tmp"]
    assert leftovers == []


def test_add_atomic_write_preserves_original_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_path = tmp_path / "pending.json"
    original = [
        {
            "note_filename": "n.md",
            "partial_payload": {"title": "Original"},
            "created_at": _iso_z(datetime.now(timezone.utc)),
        }
    ]
    _write_state(state_path, original)
    original_bytes = state_path.read_bytes()

    def boom(*args, **kwargs):
        raise RuntimeError("simulated replace failure")

    monkeypatch.setattr(hcs.os, "replace", boom)

    with pytest.raises(RuntimeError, match="simulated replace failure"):
        hcs.main(
            [
                "add",
                "--note-filename",
                "n2.md",
                "--partial-payload",
                json.dumps({"title": "Should not land"}),
                "--state-file",
                str(state_path),
            ]
        )

    # Original is untouched.
    assert state_path.read_bytes() == original_bytes
    # No stray .tmp sibling.
    leftovers = [p for p in state_path.parent.iterdir() if p.suffix == ".tmp"]
    assert leftovers == []


def test_add_invalid_partial_payload_json_exits_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    state_path = tmp_path / "pending.json"

    rc = hcs.main(
        [
            "add",
            "--note-filename",
            "n.md",
            "--partial-payload",
            "not json",
            "--state-file",
            str(state_path),
        ]
    )

    assert rc == 1
    err = capsys.readouterr().err
    assert "invalid_payload" in err or "error" in err
    # Did not create the state file.
    assert not state_path.exists()


# --------------------------------------------------------------------------
# sweep
# --------------------------------------------------------------------------


def test_sweep_safe_on_missing_state_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    state_path = tmp_path / "does-not-exist.json"
    assert not state_path.exists()

    rc = hcs.main(["sweep", "--state-file", str(state_path)])

    assert rc == 0
    assert "removed=0" in capsys.readouterr().out
    # Sweep does NOT create the state file when absent.
    assert not state_path.exists()


def test_sweep_safe_on_empty_array(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    state_path = tmp_path / "pending.json"
    _write_state(state_path, [])

    rc = hcs.main(["sweep", "--state-file", str(state_path)])

    assert rc == 0
    assert "removed=0" in capsys.readouterr().out
    assert _read_state(state_path) == []


def test_sweep_removes_entries_older_than_24h(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    state_path = tmp_path / "pending.json"
    now = datetime.now(timezone.utc)
    _write_state(
        state_path,
        [
            {
                "note_filename": "old.md",
                "partial_payload": {"title": "Old"},
                "created_at": _iso_z(now - timedelta(hours=25)),
            },
            {
                "note_filename": "fresh.md",
                "partial_payload": {"title": "Fresh"},
                "created_at": _iso_z(now - timedelta(hours=1)),
            },
        ],
    )

    rc = hcs.main(["sweep", "--state-file", str(state_path)])

    assert rc == 0
    assert "removed=1" in capsys.readouterr().out
    remaining = _read_state(state_path)
    assert len(remaining) == 1
    assert remaining[0]["note_filename"] == "fresh.md"


def test_sweep_24h_boundary_inclusive(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Entry exactly 24h old is REMOVED (>= 24h semantic; documented inline)."""
    state_path = tmp_path / "pending.json"
    now = datetime.now(timezone.utc)
    # Subtract a small fudge so the entry registers as slightly >= 24h once
    # the helper computes its own `now`. Even just past the boundary is fine.
    _write_state(
        state_path,
        [
            {
                "note_filename": "boundary.md",
                "partial_payload": {"title": "Boundary"},
                "created_at": _iso_z(now - timedelta(hours=24, seconds=1)),
            },
        ],
    )

    rc = hcs.main(["sweep", "--state-file", str(state_path)])

    assert rc == 0
    assert "removed=1" in capsys.readouterr().out
    assert _read_state(state_path) == []


def test_sweep_keeps_entries_just_under_24h(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Entry that is freshly added (well under 24h) is kept."""
    state_path = tmp_path / "pending.json"
    now = datetime.now(timezone.utc)
    _write_state(
        state_path,
        [
            {
                "note_filename": "almost.md",
                "partial_payload": {"title": "Almost"},
                "created_at": _iso_z(now - timedelta(hours=23, minutes=59)),
            },
        ],
    )

    rc = hcs.main(["sweep", "--state-file", str(state_path)])

    assert rc == 0
    assert "removed=0" in capsys.readouterr().out
    assert len(_read_state(state_path)) == 1


# --------------------------------------------------------------------------
# match
# --------------------------------------------------------------------------


def test_match_returns_null_when_no_match(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    state_path = tmp_path / "pending.json"
    _write_state(
        state_path,
        [
            {
                "note_filename": "n.md",
                "partial_payload": {"title": "Meet with Rob"},
                "created_at": _iso_z(datetime.now(timezone.utc)),
            }
        ],
    )

    rc = hcs.main(
        [
            "match",
            "--reply-content",
            "totally unrelated reply",
            "--state-file",
            str(state_path),
        ]
    )

    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert json.loads(out) is None


def test_match_returns_entry_when_substring_appears(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    state_path = tmp_path / "pending.json"
    _write_state(
        state_path,
        [
            {
                "note_filename": "n.md",
                "partial_payload": {"title": "Meet with Rob"},
                "created_at": _iso_z(datetime.now(timezone.utc)),
            }
        ],
    )

    rc = hcs.main(
        [
            "match",
            "--reply-content",
            "3pm works for the rob meeting",
            "--state-file",
            str(state_path),
        ]
    )

    assert rc == 0
    out = capsys.readouterr().out.strip()
    matched = json.loads(out)
    assert matched["note_filename"] == "n.md"
    assert matched["partial_payload"]["title"] == "Meet with Rob"


def test_match_returns_most_recent_when_multiple_match(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    state_path = tmp_path / "pending.json"
    now = datetime.now(timezone.utc)
    _write_state(
        state_path,
        [
            {
                "note_filename": "older.md",
                "partial_payload": {"title": "Meet"},
                "created_at": _iso_z(now - timedelta(hours=5)),
            },
            {
                "note_filename": "newer.md",
                "partial_payload": {"title": "Meet"},
                "created_at": _iso_z(now - timedelta(minutes=15)),
            },
        ],
    )

    rc = hcs.main(
        [
            "match",
            "--reply-content",
            "yes let's meet",
            "--state-file",
            str(state_path),
        ]
    )

    assert rc == 0
    matched = json.loads(capsys.readouterr().out.strip())
    assert matched["note_filename"] == "newer.md"


def test_match_does_not_delete_entry(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    state_path = tmp_path / "pending.json"
    seeded = [
        {
            "note_filename": "n.md",
            "partial_payload": {"title": "Meet with Rob"},
            "created_at": _iso_z(datetime.now(timezone.utc)),
        }
    ]
    _write_state(state_path, seeded)
    original_bytes = state_path.read_bytes()

    rc = hcs.main(
        [
            "match",
            "--reply-content",
            "yes ROB sounds good",
            "--state-file",
            str(state_path),
        ]
    )

    assert rc == 0
    assert json.loads(capsys.readouterr().out.strip()) is not None
    # State file is unchanged byte-for-byte.
    assert state_path.read_bytes() == original_bytes


def test_match_safe_on_missing_state_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    state_path = tmp_path / "does-not-exist.json"

    rc = hcs.main(
        [
            "match",
            "--reply-content",
            "anything",
            "--state-file",
            str(state_path),
        ]
    )

    assert rc == 0
    assert json.loads(capsys.readouterr().out.strip()) is None


def test_match_skips_entries_without_title(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An entry whose partial_payload has no `title` cannot match."""
    state_path = tmp_path / "pending.json"
    _write_state(
        state_path,
        [
            {
                "note_filename": "n.md",
                "partial_payload": {"start": "2026-06-08T15:00:00Z"},
                "created_at": _iso_z(datetime.now(timezone.utc)),
            }
        ],
    )

    rc = hcs.main(
        [
            "match",
            "--reply-content",
            "anything goes here",
            "--state-file",
            str(state_path),
        ]
    )

    assert rc == 0
    assert json.loads(capsys.readouterr().out.strip()) is None


def test_match_skips_entries_with_stopwords_only_title(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A title made entirely of stopwords yields no significant tokens."""
    state_path = tmp_path / "pending.json"
    _write_state(
        state_path,
        [
            {
                "note_filename": "n.md",
                "partial_payload": {"title": "the and to"},
                "created_at": _iso_z(datetime.now(timezone.utc)),
            }
        ],
    )

    rc = hcs.main(
        [
            "match",
            "--reply-content",
            "the and to anything",
            "--state-file",
            str(state_path),
        ]
    )

    assert rc == 0
    assert json.loads(capsys.readouterr().out.strip()) is None


# --------------------------------------------------------------------------
# internal helpers (branch coverage for parsing + aging)
# --------------------------------------------------------------------------


def test_parse_iso_z_accepts_offset_form() -> None:
    """`_parse_iso_z` handles both `Z` and explicit `+00:00` forms."""
    dt_z = hcs._parse_iso_z("2026-06-08T11:12:00Z")
    dt_offset = hcs._parse_iso_z("2026-06-08T11:12:00+00:00")
    assert dt_z == dt_offset


def test_is_aged_out_non_string_returns_false() -> None:
    now = datetime.now(timezone.utc)
    assert hcs._is_aged_out(None, now) is False
    assert hcs._is_aged_out(12345, now) is False


def test_is_aged_out_unparseable_string_returns_false() -> None:
    now = datetime.now(timezone.utc)
    assert hcs._is_aged_out("not a date", now) is False


def test_sweep_tolerates_entry_with_unparseable_created_at(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Sweep keeps entries whose `created_at` can't be parsed."""
    state_path = tmp_path / "pending.json"
    _write_state(
        state_path,
        [
            {
                "note_filename": "weird.md",
                "partial_payload": {"title": "X"},
                "created_at": "not a date",
            }
        ],
    )

    rc = hcs.main(["sweep", "--state-file", str(state_path)])

    assert rc == 0
    assert "removed=0" in capsys.readouterr().out
    assert len(_read_state(state_path)) == 1


def test_load_state_handles_empty_file(tmp_path: Path) -> None:
    state_path = tmp_path / "pending.json"
    state_path.write_text("", encoding="utf-8")
    assert hcs.load_state(state_path) == []


# --------------------------------------------------------------------------
# top-level / CLI
# --------------------------------------------------------------------------


def test_top_level_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        hcs.main(["--help"])
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert "add" in out and "sweep" in out and "match" in out


@pytest.mark.parametrize("sub", ["add", "sweep", "match"])
def test_subcommand_help_exits_zero(
    sub: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as excinfo:
        hcs.main([sub, "--help"])
    assert excinfo.value.code == 0


# --------------------------------------------------------------------------
# pending (#740) — deterministic "is this note awaiting Kent?" query
# --------------------------------------------------------------------------


def _entry(note_filename: str, created: datetime, title: str = "Meet Rob") -> dict:
    return {
        "note_filename": note_filename,
        "partial_payload": {"title": title},
        "created_at": _iso_z(created),
    }


def _entry_raw(note_filename: str, created_at_value: object) -> dict:
    """Entry with an arbitrary (possibly malformed) ``created_at`` value."""
    return {
        "note_filename": note_filename,
        "partial_payload": {"title": "Meet Rob"},
        "created_at": created_at_value,
    }


def test_pending_filenames_returns_live_excludes_aged(tmp_path: Path) -> None:
    now = datetime(2026, 7, 18, 12, 0, 0, tzinfo=timezone.utc)
    state = tmp_path / "pending.json"
    _write_state(
        state,
        [
            _entry("live.md", now - timedelta(hours=1)),
            _entry("aged.md", now - timedelta(hours=25)),
        ],
    )
    names = hcs.pending_filenames(state, now)
    assert names == {"live.md"}


def test_pending_filenames_dedups_duplicate_entries(tmp_path: Path) -> None:
    now = datetime(2026, 7, 18, 12, 0, 0, tzinfo=timezone.utc)
    state = tmp_path / "pending.json"
    _write_state(
        state,
        [
            _entry("dup.md", now - timedelta(hours=2)),
            _entry("dup.md", now - timedelta(hours=1)),
        ],
    )
    assert hcs.pending_filenames(state, now) == {"dup.md"}


def test_pending_filenames_empty_on_absent_file(tmp_path: Path) -> None:
    now = datetime(2026, 7, 18, 12, 0, 0, tzinfo=timezone.utc)
    assert hcs.pending_filenames(tmp_path / "nope.json", now) == set()


def test_pending_filenames_fails_open_on_bad_created_at(tmp_path: Path) -> None:
    """#740 Finding 1: a missing / malformed / future ``created_at`` must NOT
    withhold the note (fail OPEN — release), or a bad stamp strands it forever."""
    now = datetime(2026, 7, 18, 12, 0, 0, tzinfo=timezone.utc)
    state = tmp_path / "pending.json"
    _write_state(
        state,
        [
            {"note_filename": "missing.md", "partial_payload": {}},  # no created_at
            {"note_filename": "null.md", "partial_payload": {}, "created_at": None},
            _entry_raw("bad.md", "not-a-timestamp"),
            _entry_raw("nonstr.md", 12345),
            _entry("future.md", now + timedelta(hours=3)),  # future stamp
            _entry("live.md", now - timedelta(hours=1)),  # the one real live entry
        ],
    )
    # Only the genuinely-live entry is withheld; every doubtful stamp releases.
    assert hcs.pending_filenames(state, now) == {"live.md"}


def test_pending_filenames_normalizes_path_to_basename(tmp_path: Path) -> None:
    """#740 Finding 3: a path-form stored filename still matches the inbox
    basename (defensive; the contract is a basename)."""
    now = datetime(2026, 7, 18, 12, 0, 0, tzinfo=timezone.utc)
    state = tmp_path / "pending.json"
    _write_state(
        state, [_entry("01-Inbox/Deep 2026-07-18 0900.md", now - timedelta(hours=1))]
    )
    assert hcs.pending_filenames(state, now) == {"Deep 2026-07-18 0900.md"}


def test_pending_subcommand_true_for_live_entry(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    now = datetime.now(timezone.utc)
    state = tmp_path / "pending.json"
    _write_state(state, [_entry("here.md", now - timedelta(hours=1))])
    rc = hcs.main(
        ["pending", "--note-filename", "here.md", "--state-file", str(state)]
    )
    assert rc == 0
    assert capsys.readouterr().out.strip() == "pending=true"


def test_pending_subcommand_false_for_aged_and_unknown(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    now = datetime.now(timezone.utc)
    state = tmp_path / "pending.json"
    _write_state(state, [_entry("aged.md", now - timedelta(hours=30))])
    # aged-out entry → not pending
    rc = hcs.main(
        ["pending", "--note-filename", "aged.md", "--state-file", str(state)]
    )
    assert rc == 0
    assert capsys.readouterr().out.strip() == "pending=false"
    # filename with no entry at all → not pending
    rc = hcs.main(
        ["pending", "--note-filename", "other.md", "--state-file", str(state)]
    )
    assert rc == 0
    assert capsys.readouterr().out.strip() == "pending=false"


# --------------------------------------------------------------------------
# remove (#763) — deterministic resolved-record removal (Directive 6)
# --------------------------------------------------------------------------


def test_remove_deletes_matching_and_keeps_others(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    now = datetime.now(timezone.utc)
    state = tmp_path / "pending.json"
    _write_state(
        state,
        [
            _entry("resolved.md", now - timedelta(hours=1)),
            _entry("keep.md", now - timedelta(hours=1)),
        ],
    )
    rc = hcs.main(
        ["remove", "--note-filename", "resolved.md", "--state-file", str(state)]
    )
    assert rc == 0
    assert capsys.readouterr().out.strip() == "removed=1"
    remaining = [e["note_filename"] for e in _read_state(state)]
    assert remaining == ["keep.md"]


def test_remove_is_idempotent_no_match(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    now = datetime.now(timezone.utc)
    state = tmp_path / "pending.json"
    _write_state(state, [_entry("other.md", now - timedelta(hours=1))])
    rc = hcs.main(
        ["remove", "--note-filename", "nope.md", "--state-file", str(state)]
    )
    assert rc == 0
    assert capsys.readouterr().out.strip() == "removed=0"
    assert len(_read_state(state)) == 1  # untouched


def test_remove_removes_all_duplicate_entries(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    now = datetime.now(timezone.utc)
    state = tmp_path / "pending.json"
    _write_state(
        state,
        [
            _entry("dup.md", now - timedelta(hours=2)),
            _entry("dup.md", now - timedelta(hours=1)),
            _entry("other.md", now - timedelta(hours=1)),
        ],
    )
    rc = hcs.main(
        ["remove", "--note-filename", "dup.md", "--state-file", str(state)]
    )
    assert rc == 0
    assert capsys.readouterr().out.strip() == "removed=2"
    assert [e["note_filename"] for e in _read_state(state)] == ["other.md"]


def test_remove_basename_normalized(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A path-form --note-filename still matches a stored basename, and vice versa."""
    now = datetime.now(timezone.utc)
    state = tmp_path / "pending.json"
    _write_state(state, [_entry("Deep 2026-07-18 0900.md", now - timedelta(hours=1))])
    rc = hcs.main(
        [
            "remove",
            "--note-filename",
            "01-Inbox/Deep 2026-07-18 0900.md",
            "--state-file",
            str(state),
        ]
    )
    assert rc == 0
    assert capsys.readouterr().out.strip() == "removed=1"
    assert _read_state(state) == []


def test_remove_safe_on_absent_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = hcs.main(
        [
            "remove",
            "--note-filename",
            "x.md",
            "--state-file",
            str(tmp_path / "nope.json"),
        ]
    )
    assert rc == 0
    assert capsys.readouterr().out.strip() == "removed=0"


def test_module_runs_as_main(monkeypatch: pytest.MonkeyPatch) -> None:
    """`python3 -m scripts.inbox.handle_clarification_state sweep` works.

    Drives the `if __name__ == '__main__'` line via runpy to keep coverage
    at 100% without spawning a subprocess.
    """
    import runpy

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "handle_clarification_state",
            "sweep",
            "--state-file",
            str(Path(os.devnull)),  # never read; helper short-circuits on absent
        ],
    )
    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module(
            "scripts.inbox.handle_clarification_state", run_name="__main__"
        )
    assert excinfo.value.code == 0
