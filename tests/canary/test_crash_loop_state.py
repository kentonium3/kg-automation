"""Unit tests for scripts.canary.crash_loop_state (mission #1133, WP01 T005).

State schema v2, per Kent's 2026-11-24 tick-counting ruling (research R-16):
each unit keeps the previous tick's count and rise run instead of a history,
and no stored time is ever compared with the clock.

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
        "last_count": 39,
        "rose_last_tick": True,
        "recent_rises": [39],
        "last_seen_at": _iso(NOW),
        "episode": {
            "started_utc": _iso(NOW),
            "last_alert_utc": _iso(NOW),
            "ticks_since_alert": 0,
            "quiet_ticks": 0,
            "peak_delta": 39,
        },
    }


def _document(units: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 2,
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
                last_count=39,
                recent_rises=(39,),
                last_seen_at=NOW,
                episode=Episode(
                    started_utc=NOW,
                    last_alert_utc=NOW,
                    ticks_since_alert=3,
                    quiet_ticks=0,
                    peak_delta=39,
                ),
            ),
            "container:web": UnitState(
                generation="c0ffee",
                boot_id="boot-1",
                last_count=7,
                recent_rises=(),
                last_seen_at=NOW - timedelta(seconds=1, microseconds=250),
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
    loaded, diagnostics = load_state(path)
    assert diagnostics == []
    assert loaded == original


def test_round_trip_of_an_empty_state(tmp_path: Path) -> None:
    path = tmp_path / "crash-loop.json"
    save_state(CrashLoopState.empty(), path, now=NOW)
    loaded, diagnostics = load_state(path)
    assert diagnostics == []
    assert loaded == CrashLoopState(updated_at_utc=NOW, boot_id=None, units={})


def test_saved_document_shape(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "dir" / "crash-loop.json"
    save_state(_sample_state(), path, now=NOW)
    text = path.read_text(encoding="utf-8")
    assert text.endswith("}\n")
    document = json.loads(text)
    assert text == json.dumps(document, sort_keys=True, indent=2) + "\n"
    assert document["schema_version"] == 2
    assert document["updated_at_utc"] == "2026-11-23T12:44:46+00:00"
    assert document["boot_id"] == "boot-1"
    unit = document["units"]["system:obsidian-sync.service"]
    assert unit == {
        "generation": "boot-1",
        "boot_id": "boot-1",
        "last_count": 39,
        "rose_last_tick": True,
        "recent_rises": [39],
        "last_seen_at": "2026-11-23T12:44:46+00:00",
        "episode": {
            "started_utc": "2026-11-23T12:44:46+00:00",
            "last_alert_utc": "2026-11-23T12:44:46+00:00",
            "ticks_since_alert": 3,
            "quiet_ticks": 0,
            "peak_delta": 39,
        },
    }
    web = document["units"]["container:web"]
    assert web["episode"] is None
    assert web["rose_last_tick"] is False and web["recent_rises"] == []


def test_saved_document_validates_against_the_state_schema(tmp_path: Path) -> None:
    from jsonschema import Draft202012Validator

    schema_path = (
        Path(__file__).resolve().parents[2]
        / "kitty-specs"
        / "crash-loop-unit-alerting-01M858E8"
        / "contracts"
        / "crash-loop-state.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    path = tmp_path / "crash-loop.json"
    save_state(_sample_state(), path, now=NOW)
    Draft202012Validator(schema).validate(json.loads(path.read_text(encoding="utf-8")))


def test_save_normalises_offsets_to_utc(tmp_path: Path) -> None:
    path = tmp_path / "crash-loop.json"
    plus_two = timezone(timedelta(hours=2))
    state = CrashLoopState(
        updated_at_utc=None,
        boot_id=None,
        units={
            "user:a.service": UnitState("b", "b", 1, (), NOW.astimezone(plus_two), None)
        },
    )
    save_state(state, path, now=NOW.astimezone(plus_two))
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["updated_at_utc"] == "2026-11-23T12:44:46+00:00"
    assert document["units"]["user:a.service"]["last_seen_at"].endswith("+00:00")


def test_save_rejects_naive_datetimes(tmp_path: Path) -> None:
    path = tmp_path / "crash-loop.json"
    naive = NOW.replace(tzinfo=None)
    state = CrashLoopState(
        updated_at_utc=None,
        boot_id=None,
        units={"user:a.service": UnitState("b", "b", 1, (), naive, None)},
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
    loaded, diagnostics = load_state(tmp_path / "absent.json")
    assert loaded == CrashLoopState.empty()
    assert diagnostics == []


@pytest.mark.parametrize(
    "content",
    [
        "{corrupt",
        json.dumps([1, 2]),
        json.dumps(_document({}) | {"schema_version": 1}),
        json.dumps(_document({}) | {"schema_version": 3}),
        json.dumps({k: v for k, v in _document({}).items() if k != "schema_version"}),
        json.dumps(_document({}) | {"schema_version": True}),
        json.dumps(_document({}) | {"units": []}),
    ],
    ids=[
        "corrupt-json",
        "list-document",
        "schema-v1-never-deployed",
        "schema-v3",
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
    loaded, diagnostics = load_state(path)
    assert loaded == CrashLoopState.empty()
    assert len(diagnostics) == 1


@pytest.mark.parametrize(
    "content",
    [
        b'{"schema_version": 2, "units": {}, "boot_id": "' + b"\xff\xfe" + b'"}',
        b'{"schema_version": 2, "boot_id": null, "units": {}, "n": '
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
    loaded, diagnostics = load_state(path)
    assert loaded == CrashLoopState.empty()
    assert len(diagnostics) == 1


def test_unreadable_file_loads_empty_with_one_diagnostic(tmp_path: Path) -> None:
    path = tmp_path / "crash-loop.json"
    path.mkdir()  # reading a directory raises an OSError
    loaded, diagnostics = load_state(path)
    assert loaded == CrashLoopState.empty()
    assert len(diagnostics) == 1


def test_non_string_top_level_boot_id_resets_to_null(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "crash-loop.json",
        _document({"system:a.service": _good_entry()}) | {"boot_id": 7},
    )
    loaded, diagnostics = load_state(path)
    assert loaded.boot_id is None
    assert "system:a.service" in loaded.units
    assert len(diagnostics) == 1 and "boot_id" in diagnostics[0]


def test_null_top_level_boot_id_is_kept_without_diagnostic(tmp_path: Path) -> None:
    path = _write(tmp_path / "crash-loop.json", _document({}) | {"boot_id": None})
    loaded, diagnostics = load_state(path)
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
    ("last-count-missing", _without("last_count")),
    ("last-count-negative", _mutate(last_count=-1)),
    ("last-count-bool", _mutate(last_count=True)),
    ("last-count-float", _mutate(last_count=1.0)),
    ("last-count-string", _mutate(last_count="39")),
    ("rose-missing", _without("rose_last_tick")),
    ("rose-int", _mutate(rose_last_tick=1)),
    ("rose-null", _mutate(rose_last_tick=None)),
    ("rises-missing", _without("recent_rises")),
    ("rises-not-list", _mutate(recent_rises=39)),
    ("rises-zero", _mutate(recent_rises=[0])),
    ("rises-negative", _mutate(recent_rises=[-2])),
    ("rises-bool", _mutate(recent_rises=[True])),
    ("rises-float", _mutate(recent_rises=[2.0])),
    ("rose-without-rises", _mutate(recent_rises=[])),
    ("rises-without-rose", _mutate(rose_last_tick=False)),
    ("seen-missing", _without("last_seen_at")),
    ("seen-int", _mutate(last_seen_at=1700000000)),
    ("seen-garbage", _mutate(last_seen_at="yesterday")),
    ("seen-naive", _mutate(last_seen_at=NAIVE)),
    (
        "history-only-v1-shape",
        {
            k: v
            for k, v in _good_entry().items()
            if k not in ("last_count", "recent_rises")
        }
        | {"history": [[_iso(T_EARLY), 0], [_iso(NOW), 39]]},
    ),
    ("episode-missing", _without("episode")),
    ("episode-not-object", _mutate(episode="open")),
    ("episode-quiet-negative", _mutate(episode=_episode(quiet_ticks=-1))),
    ("episode-quiet-bool", _mutate(episode=_episode(quiet_ticks=False))),
    ("episode-peak-negative", _mutate(episode=_episode(peak_delta=-2))),
    ("episode-ticks-negative", _mutate(episode=_episode(ticks_since_alert=-1))),
    ("episode-ticks-float", _mutate(episode=_episode(ticks_since_alert=1.5))),
    (
        "episode-ticks-missing",
        _mutate(
            episode={k: v for k, v in _episode().items() if k != "ticks_since_alert"}
        ),
    ),
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
    loaded, diagnostics = load_state(path)
    assert set(loaded.units) == {"system:good-one.service", "container:good-two"}
    assert len(diagnostics) == 1
    assert "user:bad.service" in diagnostics[0]


@pytest.mark.parametrize("key", ["host:a.service", "system:", "nokey", ""])
def test_entry_with_bad_key_is_dropped(tmp_path: Path, key: str) -> None:
    path = _write(
        tmp_path / "crash-loop.json",
        _document({"system:good.service": _good_entry(), key: _good_entry()}),
    )
    loaded, diagnostics = load_state(path)
    assert set(loaded.units) == {"system:good.service"}
    assert len(diagnostics) == 1


def test_null_episode_is_well_formed(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "crash-loop.json",
        _document({"system:a.service": _mutate(episode=None)}),
    )
    loaded, diagnostics = load_state(path)
    assert diagnostics == []
    assert loaded.units["system:a.service"].episode is None


def test_entry_without_a_rise_is_well_formed(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "crash-loop.json",
        _document({"system:a.service": _mutate(rose_last_tick=False, recent_rises=[])}),
    )
    loaded, diagnostics = load_state(path)
    assert diagnostics == []
    unit = loaded.units["system:a.service"]
    assert unit.recent_rises == ()
    assert unit.rose_last_tick is False


def test_a_long_rise_run_loads(tmp_path: Path) -> None:
    # The run is capped by the writer, not by the loader.
    path = _write(
        tmp_path / "crash-loop.json",
        _document({"system:a.service": _mutate(recent_rises=[1, 2, 3, 4, 5])}),
    )
    loaded, diagnostics = load_state(path)
    assert diagnostics == []
    assert loaded.units["system:a.service"].recent_rises == (1, 2, 3, 4, 5)


def test_zulu_suffix_parses_as_utc(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "crash-loop.json",
        _document({"system:a.service": _mutate(last_seen_at="2026-11-23T12:00:00Z")}),
    )
    loaded, diagnostics = load_state(path)
    assert diagnostics == []
    assert loaded.units["system:a.service"].last_seen_at == datetime(
        2026, 11, 23, 12, tzinfo=UTC
    )


# --------------------------------------------------------------------------- #
# No clock rule (INV-CL-9′): stored times are never compared with anything.
# Replaces the v1 "single clock rule" boundary tests.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "offset",
    [
        timedelta(0),
        timedelta(seconds=60, microseconds=1),
        timedelta(hours=3),
        timedelta(days=400),
        -timedelta(days=400),
    ],
)
def test_any_well_formed_time_loads(tmp_path: Path, offset: timedelta) -> None:
    stamp = _iso(NOW + offset)
    entry = _mutate(
        last_seen_at=stamp,
        episode=_episode(started_utc=stamp, last_alert_utc=stamp),
    )
    path = _write(
        tmp_path / "crash-loop.json",
        _document({"system:a.service": entry}) | {"updated_at_utc": stamp},
    )
    loaded, diagnostics = load_state(path)
    assert diagnostics == []
    assert loaded.units["system:a.service"].last_seen_at == NOW + offset
    assert loaded.updated_at_utc == NOW + offset


def test_load_state_takes_no_clock() -> None:
    import inspect

    assert list(inspect.signature(load_state).parameters) == ["path"]
    assert not hasattr(state_mod, "CLOCK_TOLERANCE")


def test_garbage_top_level_updated_at_resets_with_diagnostic(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "crash-loop.json",
        _document({"system:a.service": _good_entry()}) | {"updated_at_utc": "soon"},
    )
    loaded, diagnostics = load_state(path)
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
    loaded, _ = load_state(path)
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
