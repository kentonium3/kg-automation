"""Unit tests for scripts.canary.crash_loop_state (mission #1133, WP01 T005).

Deterministic: ``now`` is always injected; every file lives under ``tmp_path``.
"""

from __future__ import annotations

import copy
import json
import os
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from scripts.canary import crash_loop_state as state_mod
from scripts.canary.crash_loop_state import (
    CrashLoopState,
    Episode,
    StateLock,
    StateLockBusy,
    UnitState,
    load_state,
    save_state,
)

NOW = datetime(2026, 11, 23, 12, 44, 46, tzinfo=UTC)
T_EARLY = NOW - timedelta(minutes=16)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _good_entry() -> dict[str, Any]:
    return {
        "generation": "boot-1",
        "boot_id": "boot-1",
        "history": [[_iso(T_EARLY), 0], [_iso(NOW), 39]],
        "episode": {
            "started_utc": _iso(NOW),
            "last_alert_utc": _iso(NOW),
            "quiet_ticks": 0,
            "peak_delta": 39,
        },
    }


def _document(units: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "updated_at_utc": _iso(NOW),
        "boot_id": "boot-1",
        "units": units,
    }


def _write(path: Path, document: Any) -> Path:
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _sample_state() -> CrashLoopState:
    return CrashLoopState(
        updated_at_utc=NOW,
        boot_id="boot-1",
        units={
            "system:obsidian-sync.service": UnitState(
                generation="boot-1",
                boot_id="boot-1",
                history=[(T_EARLY, 0), (NOW, 39)],
                episode=Episode(
                    started_utc=NOW,
                    last_alert_utc=NOW,
                    quiet_ticks=0,
                    peak_delta=39,
                ),
            ),
            "container:web": UnitState(
                generation="c0ffee",
                boot_id="boot-1",
                history=[(NOW - timedelta(seconds=1, microseconds=250), 7)],
                episode=None,
            ),
        },
    )


# --------------------------------------------------------------------------- #
# Round trip and document shape.
# --------------------------------------------------------------------------- #
def test_round_trip_is_exact(tmp_path: Path) -> None:
    path = tmp_path / "crash-loop.json"
    original = _sample_state()
    save_state(original, path, now=NOW)
    loaded, diagnostics = load_state(path, now=NOW)
    assert diagnostics == []
    assert loaded == original


def test_round_trip_of_an_empty_state(tmp_path: Path) -> None:
    path = tmp_path / "crash-loop.json"
    save_state(CrashLoopState.empty(), path, now=NOW)
    loaded, diagnostics = load_state(path, now=NOW)
    assert diagnostics == []
    assert loaded == CrashLoopState(updated_at_utc=NOW, boot_id=None, units={})


def test_saved_document_shape(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "dir" / "crash-loop.json"
    save_state(_sample_state(), path, now=NOW)
    text = path.read_text(encoding="utf-8")
    assert text.endswith("}\n")
    document = json.loads(text)
    assert text == json.dumps(document, sort_keys=True, indent=2) + "\n"
    assert document["schema_version"] == 1
    assert document["updated_at_utc"] == "2026-11-23T12:44:46+00:00"
    assert document["boot_id"] == "boot-1"
    unit = document["units"]["system:obsidian-sync.service"]
    assert unit["history"] == [
        ["2026-11-23T12:28:46+00:00", 0],
        ["2026-11-23T12:44:46+00:00", 39],
    ]
    assert document["units"]["container:web"]["episode"] is None


def test_save_normalises_offsets_to_utc(tmp_path: Path) -> None:
    path = tmp_path / "crash-loop.json"
    plus_two = timezone(timedelta(hours=2))
    state = CrashLoopState(
        updated_at_utc=None,
        boot_id=None,
        units={
            "user:a.service": UnitState("b", "b", [(NOW.astimezone(plus_two), 1)], None)
        },
    )
    save_state(state, path, now=NOW.astimezone(plus_two))
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["updated_at_utc"] == "2026-11-23T12:44:46+00:00"
    assert document["units"]["user:a.service"]["history"][0][0].endswith("+00:00")


def test_save_rejects_naive_datetimes(tmp_path: Path) -> None:
    path = tmp_path / "crash-loop.json"
    naive = NOW.replace(tzinfo=None)
    state = CrashLoopState(
        updated_at_utc=None,
        boot_id=None,
        units={"user:a.service": UnitState("b", "b", [(naive, 1)], None)},
    )
    with pytest.raises(ValueError, match="naive"):
        save_state(state, path, now=NOW)
    with pytest.raises(ValueError, match="naive"):
        save_state(CrashLoopState.empty(), path, now=naive)
    assert not path.exists()


# --------------------------------------------------------------------------- #
# Whole-document fail-safe load.
# --------------------------------------------------------------------------- #
def test_missing_file_loads_empty_without_diagnostics(tmp_path: Path) -> None:
    loaded, diagnostics = load_state(tmp_path / "absent.json", now=NOW)
    assert loaded == CrashLoopState.empty()
    assert diagnostics == []


@pytest.mark.parametrize(
    "content",
    [
        "{corrupt",
        json.dumps([1, 2]),
        json.dumps(_document({}) | {"schema_version": 2}),
        json.dumps({k: v for k, v in _document({}).items() if k != "schema_version"}),
        json.dumps(_document({}) | {"schema_version": True}),
        json.dumps(_document({}) | {"units": []}),
    ],
    ids=[
        "corrupt-json",
        "list-document",
        "schema-v2",
        "no-schema",
        "bool-schema",
        "units-list",
    ],
)
def test_bad_document_loads_empty_with_one_diagnostic(
    tmp_path: Path, content: str
) -> None:
    path = tmp_path / "crash-loop.json"
    path.write_text(content, encoding="utf-8")
    loaded, diagnostics = load_state(path, now=NOW)
    assert loaded == CrashLoopState.empty()
    assert len(diagnostics) == 1


@pytest.mark.parametrize(
    "content",
    [
        b'{"schema_version": 1, "units": {}, "boot_id": "' + b"\xff\xfe" + b'"}',
        b'{"schema_version": 1, "boot_id": null, "units": {}, "n": '
        + b"9" * 5000
        + b"}",
        b"[" * 100_000 + b"]" * 100_000,
    ],
    ids=["invalid-utf8", "huge-integer", "deep-nesting"],
)
def test_decoder_failures_load_empty_with_one_diagnostic(
    tmp_path: Path, content: bytes
) -> None:
    path = tmp_path / "crash-loop.json"
    path.write_bytes(content)
    loaded, diagnostics = load_state(path, now=NOW)
    assert loaded == CrashLoopState.empty()
    assert len(diagnostics) == 1


def test_unreadable_file_loads_empty_with_one_diagnostic(tmp_path: Path) -> None:
    path = tmp_path / "crash-loop.json"
    path.mkdir()  # reading a directory raises an OSError
    loaded, diagnostics = load_state(path, now=NOW)
    assert loaded == CrashLoopState.empty()
    assert len(diagnostics) == 1


def test_non_string_top_level_boot_id_resets_to_null(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "crash-loop.json",
        _document({"system:a.service": _good_entry()}) | {"boot_id": 7},
    )
    loaded, diagnostics = load_state(path, now=NOW)
    assert loaded.boot_id is None
    assert "system:a.service" in loaded.units
    assert len(diagnostics) == 1 and "boot_id" in diagnostics[0]


def test_null_top_level_boot_id_is_kept_without_diagnostic(tmp_path: Path) -> None:
    path = _write(tmp_path / "crash-loop.json", _document({}) | {"boot_id": None})
    loaded, diagnostics = load_state(path, now=NOW)
    assert loaded.boot_id is None
    assert diagnostics == []


# --------------------------------------------------------------------------- #
# Per-entry drop: one bad entry among two good ones.
# --------------------------------------------------------------------------- #
def _mutate(**changes: Any) -> dict[str, Any]:
    entry = _good_entry()
    entry.update(changes)
    return entry


def _episode(**changes: Any) -> dict[str, Any]:
    episode: dict[str, Any] = copy.deepcopy(_good_entry()["episode"])
    episode.update(changes)
    return episode


NAIVE = NOW.replace(tzinfo=None).isoformat()
FUTURE = _iso(NOW + timedelta(seconds=61))


def _without(key: str) -> dict[str, Any]:
    entry = _good_entry()
    del entry[key]
    return entry


BAD_ENTRIES: list[tuple[str, Any]] = [
    ("not-an-object", ["boot-1"]),
    ("generation-missing", _without("generation")),
    ("generation-empty", _mutate(generation="")),
    ("generation-int", _mutate(generation=5)),
    ("boot-id-missing", _without("boot_id")),
    ("boot-id-empty", _mutate(boot_id="")),
    ("boot-id-null", _mutate(boot_id=None)),
    ("history-missing", _without("history")),
    ("history-empty", _mutate(history=[])),
    ("history-not-list", _mutate(history={"a": 1})),
    ("history-pair-short", _mutate(history=[[_iso(NOW)]])),
    ("history-pair-long", _mutate(history=[[_iso(NOW), 1, 2]])),
    ("history-pair-object", _mutate(history=[{"at": _iso(NOW), "count": 1}])),
    ("history-negative-count", _mutate(history=[[_iso(NOW), -1]])),
    ("history-bool-count", _mutate(history=[[_iso(NOW), True]])),
    ("history-float-count", _mutate(history=[[_iso(NOW), 1.0]])),
    ("history-time-int", _mutate(history=[[1700000000, 1]])),
    ("history-time-garbage", _mutate(history=[["yesterday", 1]])),
    ("history-time-naive", _mutate(history=[[NAIVE, 1]])),
    ("history-time-equal", _mutate(history=[[_iso(T_EARLY), 0], [_iso(T_EARLY), 3]])),
    ("history-time-descending", _mutate(history=[[_iso(NOW), 0], [_iso(T_EARLY), 3]])),
    ("history-count-equal", _mutate(history=[[_iso(T_EARLY), 3], [_iso(NOW), 3]])),
    ("history-count-decreasing", _mutate(history=[[_iso(T_EARLY), 3], [_iso(NOW), 1]])),
    ("history-future", _mutate(history=[[_iso(T_EARLY), 0], [FUTURE, 3]])),
    ("episode-missing", _without("episode")),
    ("episode-not-object", _mutate(episode="open")),
    ("episode-quiet-negative", _mutate(episode=_episode(quiet_ticks=-1))),
    ("episode-quiet-bool", _mutate(episode=_episode(quiet_ticks=False))),
    ("episode-peak-negative", _mutate(episode=_episode(peak_delta=-2))),
    (
        "episode-peak-missing",
        _mutate(episode={k: v for k, v in _episode().items() if k != "peak_delta"}),
    ),
    ("episode-started-garbage", _mutate(episode=_episode(started_utc="soon"))),
    ("episode-started-naive", _mutate(episode=_episode(started_utc=NAIVE))),
    (
        "episode-alert-missing",
        _mutate(episode={k: v for k, v in _episode().items() if k != "last_alert_utc"}),
    ),
    ("episode-started-future", _mutate(episode=_episode(started_utc=FUTURE))),
    ("episode-alert-future", _mutate(episode=_episode(last_alert_utc=FUTURE))),
]


@pytest.mark.parametrize(
    ("bad_entry"), [e for _, e in BAD_ENTRIES], ids=[i for i, _ in BAD_ENTRIES]
)
def test_one_bad_entry_is_dropped_alone(tmp_path: Path, bad_entry: Any) -> None:
    path = _write(
        tmp_path / "crash-loop.json",
        _document(
            {
                "system:good-one.service": _good_entry(),
                "user:bad.service": bad_entry,
                "container:good-two": _good_entry(),
            }
        ),
    )
    loaded, diagnostics = load_state(path, now=NOW)
    assert set(loaded.units) == {"system:good-one.service", "container:good-two"}
    assert len(diagnostics) == 1
    assert "user:bad.service" in diagnostics[0]


@pytest.mark.parametrize("key", ["host:a.service", "system:", "nokey", ""])
def test_entry_with_bad_key_is_dropped(tmp_path: Path, key: str) -> None:
    path = _write(
        tmp_path / "crash-loop.json",
        _document({"system:good.service": _good_entry(), key: _good_entry()}),
    )
    loaded, diagnostics = load_state(path, now=NOW)
    assert set(loaded.units) == {"system:good.service"}
    assert len(diagnostics) == 1


def test_null_episode_is_well_formed(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "crash-loop.json",
        _document({"system:a.service": _mutate(episode=None)}),
    )
    loaded, diagnostics = load_state(path, now=NOW)
    assert diagnostics == []
    assert loaded.units["system:a.service"].episode is None


def test_history_with_one_entry_is_well_formed(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "crash-loop.json",
        _document({"system:a.service": _mutate(history=[[_iso(NOW), 0]])}),
    )
    loaded, diagnostics = load_state(path, now=NOW)
    assert diagnostics == []
    assert loaded.units["system:a.service"].history == [(NOW, 0)]


def test_history_has_no_fixed_maximum_on_load(tmp_path: Path) -> None:
    history = [[_iso(NOW - timedelta(minutes=200 - i)), i] for i in range(200)]
    path = _write(
        tmp_path / "crash-loop.json",
        _document({"system:a.service": _mutate(history=history)}),
    )
    loaded, diagnostics = load_state(path, now=NOW)
    assert diagnostics == []
    assert len(loaded.units["system:a.service"].history) == 200


def test_zulu_suffix_parses_as_utc(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "crash-loop.json",
        _document({"system:a.service": _mutate(history=[["2026-11-23T12:00:00Z", 0]])}),
    )
    loaded, diagnostics = load_state(path, now=NOW)
    assert diagnostics == []
    assert loaded.units["system:a.service"].history[0][0] == datetime(
        2026, 11, 23, 12, tzinfo=UTC
    )


# --------------------------------------------------------------------------- #
# The single clock rule.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("offset", "kept"),
    [
        (timedelta(seconds=0), True),
        (timedelta(seconds=59), True),
        (timedelta(seconds=60), True),
        (timedelta(seconds=60, microseconds=1), False),
        (timedelta(hours=3), False),
    ],
)
def test_clock_rule_boundary(tmp_path: Path, offset: timedelta, kept: bool) -> None:
    entry = _mutate(history=[[_iso(T_EARLY), 0], [_iso(NOW + offset), 3]], episode=None)
    path = _write(tmp_path / "crash-loop.json", _document({"system:a.service": entry}))
    loaded, diagnostics = load_state(path, now=NOW)
    assert ("system:a.service" in loaded.units) is kept
    assert len(diagnostics) == (0 if kept else 1)


def test_future_top_level_updated_at_resets_with_diagnostic(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "crash-loop.json",
        _document({"system:a.service": _good_entry()}) | {"updated_at_utc": FUTURE},
    )
    loaded, diagnostics = load_state(path, now=NOW)
    assert loaded.updated_at_utc is None
    assert "system:a.service" in loaded.units
    assert len(diagnostics) == 1


# --------------------------------------------------------------------------- #
# Atomic write.
# --------------------------------------------------------------------------- #
def test_fsync_precedes_replace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "crash-loop.json"
    calls: list[str] = []
    real_fsync, real_replace = os.fsync, os.replace

    def fsync(fd: int) -> None:
        calls.append("fsync")
        real_fsync(fd)

    def replace(src: Any, dst: Any) -> None:
        calls.append("replace")
        real_replace(src, dst)

    monkeypatch.setattr(os, "fsync", fsync)
    monkeypatch.setattr(os, "replace", replace)
    save_state(_sample_state(), path, now=NOW)
    assert calls == ["fsync", "replace"]


def test_failed_fsync_propagates_and_leaves_original(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "crash-loop.json"
    save_state(_sample_state(), path, now=NOW)
    before = path.read_bytes()
    replaced: list[Any] = []

    def boom(fd: int) -> None:
        raise OSError("simulated fsync failure")

    monkeypatch.setattr(os, "fsync", boom)
    monkeypatch.setattr(os, "replace", lambda src, dst: replaced.append(src))
    with pytest.raises(OSError, match="simulated fsync"):
        save_state(CrashLoopState.empty(), path, now=NOW + timedelta(minutes=15))
    assert replaced == []
    assert path.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["crash-loop.json"]


def test_failed_replace_leaves_original_and_no_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "crash-loop.json"
    save_state(_sample_state(), path, now=NOW)
    before = path.read_bytes()

    def boom(src: Any, dst: Any) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError, match="simulated"):
        save_state(CrashLoopState.empty(), path, now=NOW + timedelta(minutes=15))
    assert path.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["crash-loop.json"]


def test_save_overwrites_an_existing_document(tmp_path: Path) -> None:
    path = tmp_path / "crash-loop.json"
    save_state(_sample_state(), path, now=NOW)
    save_state(CrashLoopState.empty(), path, now=NOW)
    loaded, _ = load_state(path, now=NOW)
    assert loaded.units == {}


# --------------------------------------------------------------------------- #
# Lock.
# --------------------------------------------------------------------------- #
def test_second_lock_is_busy_and_succeeds_after_release(tmp_path: Path) -> None:
    lock_path = tmp_path / "crash-loop.lock"
    with StateLock(lock_path), pytest.raises(StateLockBusy), StateLock(lock_path):
        pass  # pragma: no cover - never reached
    with StateLock(lock_path):
        pass
    assert lock_path.exists()


def test_lock_creates_parent_directory(tmp_path: Path) -> None:
    lock_path = tmp_path / "state" / "crash-loop.lock"
    with StateLock(lock_path):
        assert lock_path.exists()


def test_lock_releases_when_the_body_raises(tmp_path: Path) -> None:
    lock_path = tmp_path / "crash-loop.lock"
    with pytest.raises(RuntimeError, match="body"), StateLock(lock_path):
        raise RuntimeError("body")
    with StateLock(lock_path):
        pass


@pytest.mark.skipif(not Path("/proc/self/fd").is_dir(), reason="needs /proc")
def test_busy_lock_does_not_leak_file_descriptors(tmp_path: Path) -> None:
    lock_path = tmp_path / "crash-loop.lock"
    with StateLock(lock_path):
        before = len(os.listdir("/proc/self/fd"))
        for _ in range(5):
            with pytest.raises(StateLockBusy), StateLock(lock_path):
                pass  # pragma: no cover
        assert len(os.listdir("/proc/self/fd")) == before


def test_default_paths() -> None:
    assert state_mod.DEFAULT_STATE_PATH == Path(
        "/data/services/felix-canary/state/crash-loop.json"
    )
    assert state_mod.DEFAULT_LOCK_PATH == Path(
        "/data/services/felix-canary/state/crash-loop.lock"
    )
