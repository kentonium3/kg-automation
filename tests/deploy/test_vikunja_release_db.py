"""Tests for the Vikunja release-route DB-safety primitives (#1087, WP02).

T007 snapshot (R-6, R-21 INV-2), T008 migration detector, T009 rollback
guard (R-11). No docker, network or ssh: the runner, clocks and roots are
injected, and every database is a small SQLite fixture built in ``tmp_path``
with only the columns the code reads (v2.4.0 shape: ``repeat_after`` /
``repeat_mode``; migrated shape: ``tasks.repeats`` and/or
``task_repeat_legacy_backup``, per pkg/migration/20261022220000.go).
Every refusal has a same-fixture positive control.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import stat
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.deploy.lib import installed_report
from scripts.deploy.vikunja_release import core, dbsafety

ACTIVE = "office2.local/vikunja:active"
ROLLBACK_ID = "sha256:60fe1ee8f729c17b057ba00a49b968adb4ed1e774cea36b5f4cc81340991a7d2"
SECRET = "password=hunter2"
TITLE = "Buy anniversary gift for Margot"
NOW = datetime(2026, 10, 30, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class FakeClock:
    def __init__(self, t: float = 0.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


def _deadline(t: float = 0.0, seconds: float = 120.0) -> tuple[core.Deadline, FakeClock]:
    clock = FakeClock(t)
    return core.Deadline(seconds, clock=clock), clock


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _v24_schema(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY, title TEXT, "
                 "repeat_after INTEGER, repeat_mode INTEGER NOT NULL DEFAULT 0)")
    conn.execute("CREATE INDEX idx_tasks_title ON tasks (title)")


def _insert(conn: sqlite3.Connection, n: int, start: int = 1) -> None:
    conn.executemany("INSERT INTO tasks (id, title, repeat_after, repeat_mode) VALUES (?, ?, ?, ?)",
                     [(i, f"{TITLE} {SECRET} #{i}", 86400 * (i % 3), i % 2) for i in range(start, start + n)])


def make_db(path: Path, *, rows: int = 20, shape: str = "v24") -> Path:
    """A v2.4.0-shaped DB, or a migrated one (``repeats`` column, backup
    table, or both). Rollback-journal mode, closed cleanly: no sidecars."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, isolation_level=None)
    try:
        _v24_schema(conn)
        _insert(conn, rows)
        if shape in ("repeats", "both"):
            conn.execute("ALTER TABLE tasks ADD COLUMN repeats TEXT")
        if shape in ("backup", "both"):
            conn.execute("CREATE TABLE task_repeat_legacy_backup (id INTEGER PRIMARY KEY, "
                         "repeat_after INTEGER, repeat_mode INTEGER NOT NULL DEFAULT 0)")
    finally:
        conn.close()
    assert not (path.parent / (path.name + "-wal")).exists()
    return path


def make_wal_data_dir(data: Path, *, base_rows: int, wal_rows: int, wal_sql: str | None = None) -> None:
    """A data folder as a killed container leaves it: committed rows that
    live only in ``vikunja.db-wal`` (autocheckpoint off, files copied while
    the writer is still open)."""
    work = data.parent / (data.name + "-writer")
    work.mkdir(parents=True)
    db = work / dbsafety.DB_NAME
    conn = sqlite3.connect(db, isolation_level=None)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        _v24_schema(conn)
        _insert(conn, base_rows)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.execute("PRAGMA wal_autocheckpoint=0")
        if wal_rows:
            _insert(conn, wal_rows, start=base_rows + 1)
        if wal_sql:
            conn.execute(wal_sql)
        data.mkdir(parents=True, exist_ok=True)
        for name in (dbsafety.DB_NAME, dbsafety.WAL_NAME, dbsafety.SHM_NAME):
            if (work / name).exists():
                shutil.copyfile(work / name, data / name)
    finally:
        conn.close()
    shutil.rmtree(work)


def _count(path: Path) -> int:
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        return conn.execute("SELECT count(*) FROM tasks").fetchone()[0]
    finally:
        conn.close()


def _tree(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): _sha(p) for p in sorted(root.rglob("*")) if p.is_file()}


def _fail_code(excinfo) -> str:
    return excinfo.value.code


# ---------------------------------------------------------------------------
# T007 — snapshot
# ---------------------------------------------------------------------------


def test_snapshot_records_hashes_count_modes_and_pre_version(tmp_path, monkeypatch):
    report = tmp_path / "installed.jsonl"
    monkeypatch.setenv(installed_report.ENV_VAR, str(report))
    data = tmp_path / "data"
    make_db(data / dbsafety.DB_NAME, rows=25)
    before = _tree(data)
    deadline, _ = _deadline()

    rec = dbsafety.snapshot(data, tmp_path / "snapshots", lambda: NOW, pre_version="v2.4.0",
                            running_image_id=ROLLBACK_ID, deadline=deadline)

    snap = tmp_path / "snapshots" / "20261030T120000Z"
    assert Path(rec["snapshot_dir"]) == snap.resolve()
    assert stat.S_IMODE(snap.stat().st_mode) == 0o700
    assert stat.S_IMODE((snap / "raw").stat().st_mode) == 0o700
    for f in (snap / "vikunja.db", snap / "snapshot.json"):
        assert stat.S_IMODE(f.stat().st_mode) == 0o600, f
    assert stat.S_IMODE((snap / "raw" / "vikunja.db").stat().st_mode) == 0o400  # evidence: read-only
    assert sorted(os.listdir(snap)) == ["raw", "snapshot.json", "vikunja.db"]  # work/ removed
    on_disk = json.loads((snap / "snapshot.json").read_text())
    assert on_disk == {k: v for k, v in rec.items() if k != "snapshot_json"}
    assert on_disk["db_sha256"] == _sha(snap / "vikunja.db")
    assert on_disk["integrity_check"] == "ok"
    assert on_disk["tasks_count"] == 25
    assert on_disk["pre_version"] == "v2.4.0"
    assert on_disk["running_image_id"] == ROLLBACK_ID
    assert on_disk["raw"]["db"]["sha256"] == _sha(data / "vikunja.db")
    assert on_disk["raw"]["wal"] is None and on_disk["raw"]["shm"] is None
    assert dbsafety.read_snapshot(snap / "snapshot.json") == on_disk
    # The data folder is only read.
    assert _tree(data) == before
    # No task title or seeded secret is in the record.
    text = (snap / "snapshot.json").read_text()
    assert TITLE not in text and SECRET not in text
    # Every written file is reported (#1072).
    result = installed_report.read_report(report)
    assert not result["rejected"]
    dests = {e["dest"] for e in result["entries"]}
    assert dests == {str((snap / "raw" / "vikunja.db").resolve()), str((snap / "vikunja.db").resolve()),
                     str((snap / "snapshot.json").resolve())}


def test_snapshot_pre_version_is_optional(tmp_path):
    data = tmp_path / "data"
    make_db(data / dbsafety.DB_NAME)
    rec = dbsafety.snapshot(data, tmp_path / "snaps", lambda: NOW)
    assert rec["pre_version"] is None and rec["running_image_id"] is None


def test_snapshot_refuses_an_unsafe_pre_version_and_accepts_a_version(tmp_path):
    data = tmp_path / "data"
    make_db(data / dbsafety.DB_NAME)
    with pytest.raises(core.Fail) as exc:
        dbsafety.snapshot(data, tmp_path / "snaps", lambda: NOW, pre_version=f"v2.4.0 {SECRET}")
    assert _fail_code(exc) == "SNAPSHOT_RECORD_INVALID"
    assert not (tmp_path / "snaps").exists()  # refused before any write
    # Positive control: same fixture, a version string.
    rec = dbsafety.snapshot(data, tmp_path / "snaps", lambda: NOW, pre_version="v2.4.0")
    assert rec["pre_version"] == "v2.4.0"


def test_snapshot_keeps_rows_committed_only_in_the_wal(tmp_path):
    data = tmp_path / "data"
    make_wal_data_dir(data, base_rows=10, wal_rows=7)
    assert (data / dbsafety.WAL_NAME).stat().st_size > 0

    # Positive control: a main-file-only copy misses the WAL rows.
    main_only = tmp_path / "main-only" / "vikunja.db"
    main_only.parent.mkdir()
    shutil.copyfile(data / dbsafety.DB_NAME, main_only)
    assert _count(main_only) == 10

    rec = dbsafety.snapshot(data, tmp_path / "snaps", lambda: NOW)
    assert rec["tasks_count"] == 17
    assert _count(Path(rec["db_path"])) == 17
    assert rec["raw"]["wal"]["sha256"] == _sha(data / dbsafety.WAL_NAME)
    assert rec["raw"]["shm"]["sha256"] == _sha(data / dbsafety.SHM_NAME)
    # The consolidated copy is a single file: no sidecars beside it.
    snap = Path(rec["snapshot_dir"])
    assert not (snap / dbsafety.WAL_NAME).exists() and not (snap / dbsafety.SHM_NAME).exists()


def test_retained_raw_files_stay_verbatim_after_consolidation(tmp_path):
    """raw/ is evidence: the WAL checkpoint runs on a scratch copy, so the
    retained raw files still match their recorded hashes afterwards."""
    data = tmp_path / "data"
    make_wal_data_dir(data, base_rows=10, wal_rows=7)
    source_hashes = {n: _sha(data / n) for n in (dbsafety.DB_NAME, dbsafety.WAL_NAME, dbsafety.SHM_NAME)}
    rec = dbsafety.snapshot(data, tmp_path / "snaps", lambda: NOW)
    raw = Path(rec["snapshot_dir"]) / "raw"
    assert sorted(os.listdir(raw)) == sorted(source_hashes)  # sidecars kept, not truncated or removed
    for name, key in dbsafety.SOURCE_KEYS.items():
        entry = rec["raw"][key]
        assert Path(entry["path"]) == raw / name
        assert _sha(raw / name) == entry["sha256"], name  # the RETAINED file
        assert (raw / name).stat().st_size == entry["size"]
        # Control: the recorded hash is also the live source's hash.
        assert entry["sha256"] == source_hashes[name]
    assert rec["tasks_count"] == 17  # consolidation still kept the WAL rows


def test_snapshot_runs_from_a_read_only_data_folder(tmp_path):
    data = tmp_path / "data"
    make_wal_data_dir(data, base_rows=4, wal_rows=3)
    before = _tree(data)
    data.chmod(0o555)
    for f in data.iterdir():
        f.chmod(0o444)
    try:
        rec = dbsafety.snapshot(data, tmp_path / "snaps", lambda: NOW)
    finally:
        data.chmod(0o755)
    assert rec["tasks_count"] == 7
    assert _tree(data) == before


def _corrupt(path: Path) -> None:
    conn = sqlite3.connect(path)
    page = conn.execute("PRAGMA page_size").fetchone()[0]
    conn.close()
    with open(path, "r+b") as fh:
        for page_no in (2, 3):
            fh.seek(page * page_no)
            fh.write(b"\xff" * 64)


def test_snapshot_corrupt_source_fails_integrity(tmp_path):
    good = make_db(tmp_path / "good" / dbsafety.DB_NAME, rows=400)
    bad = tmp_path / "bad" / dbsafety.DB_NAME
    bad.parent.mkdir()
    shutil.copyfile(good, bad)
    _corrupt(bad)
    with pytest.raises(core.Fail) as exc:
        dbsafety.snapshot(bad.parent, tmp_path / "snaps-bad", lambda: NOW)
    assert _fail_code(exc) == "SNAPSHOT_INTEGRITY_FAILED"
    assert not (tmp_path / "snaps-bad" / "20261030T120000Z" / "snapshot.json").exists()
    assert not (tmp_path / "snaps-bad" / "20261030T120000Z" / "work").exists()  # scratch removed on failure
    # Positive control: the same DB before corruption passes.
    rec = dbsafety.snapshot(good.parent, tmp_path / "snaps-good", lambda: NOW)
    assert rec["integrity_check"] == "ok" and rec["tasks_count"] == 400


def test_snapshot_missing_source_refuses(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    with pytest.raises(core.Fail) as exc:
        dbsafety.snapshot(data, tmp_path / "snaps", lambda: NOW)
    assert _fail_code(exc) == "SNAPSHOT_SOURCE_MISSING"
    make_db(data / dbsafety.DB_NAME)
    assert dbsafety.snapshot(data, tmp_path / "snaps", lambda: NOW)["tasks_count"] == 20


def test_snapshot_never_overwrites_an_existing_snapshot(tmp_path):
    data = tmp_path / "data"
    make_db(data / dbsafety.DB_NAME)
    first = dbsafety.snapshot(data, tmp_path / "snaps", lambda: NOW)
    sha = _sha(Path(first["snapshot_json"]))
    with pytest.raises(core.Fail) as exc:
        dbsafety.snapshot(data, tmp_path / "snaps", lambda: NOW)
    assert _fail_code(exc) == "SNAPSHOT_DIR_EXISTS"
    assert _sha(Path(first["snapshot_json"])) == sha
    # Control: same data and root, a later second -> a new snapshot.
    later = dbsafety.snapshot(data, tmp_path / "snaps", lambda: NOW.replace(second=1))
    assert later["snapshot_dir"] != first["snapshot_dir"]


def test_snapshot_budget_expired_before_sqlite_work(tmp_path):
    data = tmp_path / "data"
    make_db(data / dbsafety.DB_NAME)
    deadline, clock = _deadline()
    clock.t = 121.0
    with pytest.raises(core.Fail) as exc:
        dbsafety.snapshot(data, tmp_path / "snaps-late", lambda: NOW, deadline=deadline)
    assert _fail_code(exc) == "SNAPSHOT_DEADLINE"
    # Positive control: same fixture inside the budget.
    clock.t = 119.0
    assert dbsafety.snapshot(data, tmp_path / "snaps-ok", lambda: NOW, deadline=deadline)["tasks_count"] == 20


def test_snapshot_budget_interrupts_running_sqlite_work(tmp_path, monkeypatch):
    """The progress handler aborts SQLite work once the budget passes."""
    data = tmp_path / "data"
    make_db(data / dbsafety.DB_NAME, rows=2000)
    deadline, clock = _deadline()
    real_connect = dbsafety._connect

    def connect_then_expire(*a, **kw):
        conn = real_connect(*a, **kw)
        clock.t = 500.0  # the budget passes while the connection works
        return conn

    monkeypatch.setattr(dbsafety, "_connect", connect_then_expire)
    with pytest.raises(core.Fail) as exc:
        dbsafety.snapshot(data, tmp_path / "snaps-late", lambda: NOW, deadline=deadline)
    assert _fail_code(exc) == "SNAPSHOT_DEADLINE"
    monkeypatch.setattr(dbsafety, "_connect", real_connect)
    clock.t = 0.0
    assert dbsafety.snapshot(data, tmp_path / "snaps-ok", lambda: NOW, deadline=deadline)["tasks_count"] == 2000


def test_connections_carry_a_busy_timeout_capped_by_the_budget(tmp_path):
    db = make_db(tmp_path / "db" / dbsafety.DB_NAME)
    deadline, clock = _deadline()
    conn = dbsafety._connect(db, deadline, mode="ro")
    try:
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == int(dbsafety.BUSY_TIMEOUT_S * 1000)
    finally:
        conn.close()
    clock.t = 119.75
    conn = dbsafety._connect(db, deadline, mode="ro")
    try:
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 250
    finally:
        conn.close()


def test_a_locked_db_is_bounded_by_the_busy_timeout(tmp_path):
    db = make_db(tmp_path / "db" / dbsafety.DB_NAME)
    deadline, clock = _deadline()
    clock.t = 119.8  # 0.2 s of the budget left: the busy wait is short
    holder = sqlite3.connect(db, isolation_level=None)
    holder.execute("BEGIN EXCLUSIVE")
    started = time.monotonic()
    try:
        with pytest.raises(core.Fail) as exc:
            dbsafety.is_migrated(db, deadline)
        assert time.monotonic() - started < 2.0  # not the full 5 s busy timeout
        assert _fail_code(exc) == "DB_INSPECT_FAILED"
        assert "locked" in exc.value.detail_private
    finally:
        holder.execute("ROLLBACK")
        holder.close()
    # Positive control: same DB and budget, lock released.
    assert dbsafety.is_migrated(db, deadline) is False


# ---------------------------------------------------------------------------
# Private root preparation (office2: the roots are absent until first use)
# ---------------------------------------------------------------------------


def test_root_absent_is_created_one_level_with_mode_0700(tmp_path):
    root = tmp_path / "snapshots"
    assert dbsafety.prepare_private_root(root) == root
    assert root.is_dir() and not root.is_symlink()
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    # Present and safe: accepted again, unchanged.
    assert dbsafety.prepare_private_root(root) == root


def test_root_is_created_0700_whatever_the_umask(tmp_path):
    old = os.umask(0o277)
    try:
        root = dbsafety.prepare_private_root(tmp_path / "snapshots")
    finally:
        os.umask(old)
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    # Control: the default umask gives the same mode.
    assert stat.S_IMODE(dbsafety.prepare_private_root(tmp_path / "other").stat().st_mode) == 0o700


def test_open_private_root_anchors_later_creation_to_the_verified_folder(tmp_path):
    """A root swapped for a symlink after the check cannot redirect writes
    made through the returned descriptor."""
    root = tmp_path / "snapshots"
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    fd = dbsafety.open_private_root(root)
    try:
        root.rename(tmp_path / "moved")
        root.symlink_to(elsewhere)
        os.mkdir("stamp", 0o700, dir_fd=fd)
    finally:
        os.close(fd)
    assert (tmp_path / "moved" / "stamp").is_dir()
    assert list(elsewhere.iterdir()) == []
    # And the swapped path itself is now refused (O_NOFOLLOW).
    with pytest.raises(core.Fail) as exc:
        dbsafety.open_private_root(root)
    assert _fail_code(exc) == "SNAPSHOT_ROOT_UNSAFE"
    root.unlink()
    (tmp_path / "moved").rename(root)
    os.close(dbsafety.open_private_root(root))


def test_root_with_a_missing_parent_is_not_created(tmp_path):
    root = tmp_path / "absent-parent" / "snapshots"
    with pytest.raises(core.Fail) as exc:
        dbsafety.prepare_private_root(root, code="ACTIVATION_ROOT")
    assert _fail_code(exc) == "ACTIVATION_ROOT_PARENT_MISSING"
    assert not root.parent.exists()
    # Positive control: same root once its parent exists.
    root.parent.mkdir()
    assert dbsafety.prepare_private_root(root, code="ACTIVATION_ROOT") == root


def test_root_symlink_is_refused(tmp_path):
    target = tmp_path / "elsewhere"
    target.mkdir(mode=0o700)
    target.chmod(0o700)
    root = tmp_path / "snapshots"
    root.symlink_to(target)
    with pytest.raises(core.Fail) as exc:
        dbsafety.prepare_private_root(root)
    assert _fail_code(exc) == "SNAPSHOT_ROOT_UNSAFE"
    with pytest.raises(core.Fail) as exc:
        dbsafety.snapshot(make_db(tmp_path / "data" / dbsafety.DB_NAME).parent, root, lambda: NOW)
    assert _fail_code(exc) == "SNAPSHOT_ROOT_UNSAFE"
    assert list(target.iterdir()) == []  # nothing written through the link
    # Positive control: the same path as a real folder.
    root.unlink()
    assert dbsafety.prepare_private_root(root) == root
    assert dbsafety.snapshot(tmp_path / "data", root, lambda: NOW)["tasks_count"] == 20


@pytest.mark.parametrize("mode", [0o755, 0o750, 0o777, 0o500])
def test_root_with_the_wrong_mode_is_refused_not_repaired(tmp_path, mode):
    root = tmp_path / "failures"
    root.mkdir()
    root.chmod(mode)
    try:
        with pytest.raises(core.Fail) as exc:
            dbsafety.prepare_private_root(root, code="FAILURES_ROOT")
        assert _fail_code(exc) == "FAILURES_ROOT_UNSAFE"
        assert stat.S_IMODE(root.stat().st_mode) == mode
    finally:
        root.chmod(0o700)
    assert dbsafety.prepare_private_root(root, code="FAILURES_ROOT") == root


def test_root_that_is_a_file_is_refused(tmp_path):
    root = tmp_path / "snapshots"
    root.write_text("x")
    with pytest.raises(core.Fail) as exc:
        dbsafety.prepare_private_root(root)
    assert _fail_code(exc) == "SNAPSHOT_ROOT_UNSAFE"
    root.unlink()
    assert dbsafety.prepare_private_root(root) == root


def test_root_owned_by_another_uid_is_refused(tmp_path, monkeypatch):
    root = tmp_path / "snapshots"
    dbsafety.prepare_private_root(root)
    monkeypatch.setattr(dbsafety.os, "geteuid", lambda: os.stat(root).st_uid + 1)
    with pytest.raises(core.Fail) as exc:
        dbsafety.prepare_private_root(root)
    assert _fail_code(exc) == "SNAPSHOT_ROOT_UNSAFE"
    monkeypatch.undo()
    assert dbsafety.prepare_private_root(root) == root


# ---------------------------------------------------------------------------
# T008 — migration detector
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("shape,expected", [("v24", False), ("repeats", True), ("backup", True), ("both", True)])
def test_is_migrated_detects_either_signal(tmp_path, shape, expected):
    db = make_db(tmp_path / "db" / dbsafety.DB_NAME, shape=shape)
    assert dbsafety.is_migrated(db) is expected


def test_is_migrated_opens_the_copy_read_only(tmp_path):
    db = make_db(tmp_path / "db" / dbsafety.DB_NAME, shape="repeats")
    folder = db.parent
    before = _tree(folder)
    folder.chmod(0o555)
    db.chmod(0o444)
    try:
        assert dbsafety.is_migrated(db) is True
    finally:
        folder.chmod(0o755)
    assert _tree(folder) == before


def test_is_migrated_refuses_a_db_without_tasks(tmp_path):
    db = tmp_path / "other.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE projects (id INTEGER PRIMARY KEY)")
    conn.close()
    with pytest.raises(core.Fail) as exc:
        dbsafety.is_migrated(db)
    assert _fail_code(exc) == "DB_TASKS_TABLE_MISSING"
    assert dbsafety.is_migrated(make_db(tmp_path / "v" / "vikunja.db")) is False


def test_is_migrated_refuses_a_non_database(tmp_path):
    junk = tmp_path / "junk.db"
    junk.write_bytes(b"not a database at all" * 100)
    with pytest.raises(core.Fail) as exc:
        dbsafety.is_migrated(junk)
    assert _fail_code(exc) == "DB_INSPECT_FAILED"
    # Control: a real Vikunja-shaped DB at the same folder is inspected fine.
    assert dbsafety.is_migrated(make_db(tmp_path / dbsafety.DB_NAME)) is False


# ---------------------------------------------------------------------------
# T009 — rollback guard
# ---------------------------------------------------------------------------


class FakeRunner:
    """Answers the guard's two read-only docker calls."""

    def __init__(self, *, container: str = "", active_id: str | None = None,
                 ps_rc: int = 0, raise_exc: BaseException | None = None) -> None:
        self.calls: list[tuple[list[str], dict]] = []
        self.container = container
        self.active_id = active_id
        self.ps_rc = ps_rc
        self.raise_exc = raise_exc

    def __call__(self, argv, **kwargs):
        self.calls.append((list(argv), kwargs))
        if self.raise_exc is not None:
            raise self.raise_exc
        if argv == ["docker", "ps", "-a", "--filter", "name=^vikunja$", "-q"]:
            if self.ps_rc:
                return subprocess.CompletedProcess(argv, self.ps_rc, "", f"daemon error {SECRET}\n")
            return subprocess.CompletedProcess(argv, 0, self.container, "")
        if argv == ["docker", "image", "inspect", "--format", "{{.Id}}", ACTIVE]:
            if self.active_id is None:
                return subprocess.CompletedProcess(argv, 1, "", f"Error: No such image: {ACTIVE}\n")
            return subprocess.CompletedProcess(argv, 0, self.active_id + "\n", "")
        return subprocess.CompletedProcess(argv, 1, "", "unexpected call\n")


def restored(tmp_path: Path, *, shape: str = "v24") -> tuple[Path, Path]:
    """Snapshot a data folder of the given shape, then restore the snapshot's
    consolidated DB into a fresh data folder, as Kent's ``install`` does.
    Returns ``(restored_data_dir, snapshot_json)``."""
    live = tmp_path / f"live-{shape}"
    make_db(live / dbsafety.DB_NAME, shape=shape)
    rec = dbsafety.snapshot(live, tmp_path / f"snaps-{shape}", lambda: NOW)
    data = tmp_path / f"restored-{shape}"
    data.mkdir()
    shutil.copyfile(rec["db_path"], data / dbsafety.DB_NAME)
    return data, Path(rec["snapshot_json"])


def _guard(runner, data, snap_json, tmp_path):
    return dbsafety.rollback_guard(runner, data, snap_json, work_dir=tmp_path)


def test_guard_passes_on_the_restored_unmigrated_snapshot(tmp_path):
    data, snap_json = restored(tmp_path)
    runner = FakeRunner()
    result = _guard(runner, data, snap_json, tmp_path)
    assert result == {"db_sha256": _sha(data / dbsafety.DB_NAME)}
    # Only the two read-only docker calls, each time-bounded.
    assert [c[0][:3] for c in runner.calls] == [["docker", "ps", "-a"], ["docker", "image", "inspect"]]
    assert all(c[1]["timeout"] == core.DOCKER_TIMEOUT for c in runner.calls)
    # The private copy was removed.
    assert not list(tmp_path.glob("vikunja-guard-*"))


def test_guard_refuses_when_a_container_exists(tmp_path):
    data, snap_json = restored(tmp_path)
    runner = FakeRunner(container="0123456789ab\n")
    with pytest.raises(core.Fail) as exc:
        _guard(runner, data, snap_json, tmp_path)
    assert _fail_code(exc) == "GUARD_CONTAINER_PRESENT"
    assert len(runner.calls) == 1  # refused at the first check
    assert _guard(FakeRunner(), data, snap_json, tmp_path)


def test_guard_refuses_when_active_is_tagged(tmp_path):
    data, snap_json = restored(tmp_path)
    with pytest.raises(core.Fail) as exc:
        _guard(FakeRunner(active_id=ROLLBACK_ID), data, snap_json, tmp_path)
    assert _fail_code(exc) == "GUARD_LOCK_NOT_HELD"
    assert _guard(FakeRunner(), data, snap_json, tmp_path)


@pytest.mark.parametrize("sidecar", [dbsafety.WAL_NAME, dbsafety.SHM_NAME])
def test_guard_refuses_any_sidecar(tmp_path, sidecar):
    data, snap_json = restored(tmp_path)
    (data / sidecar).write_bytes(b"")
    with pytest.raises(core.Fail) as exc:
        _guard(FakeRunner(), data, snap_json, tmp_path)
    assert _fail_code(exc) == "GUARD_SIDECAR_PRESENT"
    (data / sidecar).unlink()
    assert _guard(FakeRunner(), data, snap_json, tmp_path)


def test_guard_refuses_a_residual_migrated_wal(tmp_path):
    """The restored main file matches the snapshot, but a WAL left behind
    by the release holds the migration: SQLite would replay it on open."""
    data = tmp_path / "data"
    make_wal_data_dir(data, base_rows=5, wal_rows=0,
                      wal_sql="ALTER TABLE tasks ADD COLUMN repeats TEXT")
    # The hazard is real: main file plus WAL reads as migrated.
    probe = tmp_path / "probe"
    shutil.copytree(data, probe)
    assert dbsafety.is_migrated(probe / dbsafety.DB_NAME) is True
    # snapshot.json pins the main file's bytes (as if it were the restore).
    snap = tmp_path / "snap"
    snap.mkdir()
    snap_json = snap / "snapshot.json"
    dbsafety._write_new_json(snap_json, {"schema_version": 1, "db_sha256": _sha(data / dbsafety.DB_NAME)})

    with pytest.raises(core.Fail) as exc:
        _guard(FakeRunner(), data, snap_json, tmp_path)
    assert _fail_code(exc) == "GUARD_SIDECAR_PRESENT"
    # Positive control: same fixture with the sidecars cleared passes.
    for name in (dbsafety.WAL_NAME, dbsafety.SHM_NAME):
        (data / name).unlink()
    assert _guard(FakeRunner(), data, snap_json, tmp_path)["db_sha256"] == _sha(data / dbsafety.DB_NAME)


def test_guard_refuses_a_sha_mismatch(tmp_path):
    data, snap_json = restored(tmp_path)
    original = (data / dbsafety.DB_NAME).read_bytes()
    conn = sqlite3.connect(data / dbsafety.DB_NAME, isolation_level=None)
    conn.execute("DELETE FROM tasks WHERE id = 1")
    conn.close()
    with pytest.raises(core.Fail) as exc:
        _guard(FakeRunner(), data, snap_json, tmp_path)
    assert _fail_code(exc) == "GUARD_SHA_MISMATCH"
    (data / dbsafety.DB_NAME).write_bytes(original)
    assert _guard(FakeRunner(), data, snap_json, tmp_path)


def test_guard_refuses_a_migrated_db_even_when_the_sha_matches(tmp_path):
    for shape in ("repeats", "backup"):
        data, snap_json = restored(tmp_path, shape=shape)
        with pytest.raises(core.Fail) as exc:
            _guard(FakeRunner(), data, snap_json, tmp_path)
        assert _fail_code(exc) == "GUARD_DB_MIGRATED", shape
    data, snap_json = restored(tmp_path, shape="v24")
    assert _guard(FakeRunner(), data, snap_json, tmp_path)


def test_guard_checks_in_order(tmp_path):
    """Every check would fail; the first in R-11's order is reported, and no
    later check runs."""
    data, snap_json = restored(tmp_path, shape="repeats")
    (data / dbsafety.WAL_NAME).write_bytes(b"x")
    cases = [
        (FakeRunner(container="abc\n", active_id=ROLLBACK_ID), "GUARD_CONTAINER_PRESENT", 1),
        (FakeRunner(active_id=ROLLBACK_ID), "GUARD_LOCK_NOT_HELD", 2),
        (FakeRunner(), "GUARD_SIDECAR_PRESENT", 2),
    ]
    for runner, code, calls in cases:
        with pytest.raises(core.Fail) as exc:
            _guard(runner, data, snap_json, tmp_path)
        assert _fail_code(exc) == code
        assert len(runner.calls) == calls
    (data / dbsafety.WAL_NAME).unlink()
    with pytest.raises(core.Fail) as exc:
        _guard(FakeRunner(), data, snap_json, tmp_path)
    assert _fail_code(exc) == "GUARD_DB_MIGRATED"
    # Control: the same order of checks passes on an unmigrated restore.
    clean, clean_json = restored(tmp_path, shape="v24")
    assert _guard(FakeRunner(), clean, clean_json, tmp_path)


@pytest.mark.parametrize("runner", [
    FakeRunner(ps_rc=1),
    FakeRunner(raise_exc=subprocess.TimeoutExpired(["docker"], 30)),
    FakeRunner(raise_exc=FileNotFoundError("docker")),
], ids=["ps-error", "timeout", "no-docker"])
def test_guard_refuses_on_any_docker_inspection_error(tmp_path, runner, capsys):
    data, snap_json = restored(tmp_path)
    with pytest.raises(core.Fail) as exc:
        _guard(runner, data, snap_json, tmp_path)
    assert _fail_code(exc) == "GUARD_INSPECTION_ERROR"
    out = capsys.readouterr()
    assert SECRET not in out.out + out.err
    assert _guard(FakeRunner(), data, snap_json, tmp_path)


def test_guard_refuses_an_unreadable_snapshot_record(tmp_path):
    data, snap_json = restored(tmp_path)
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    for record in (bad, tmp_path / "absent.json"):
        with pytest.raises(core.Fail) as exc:
            _guard(FakeRunner(), data, record, tmp_path)
        assert _fail_code(exc) == "GUARD_INSPECTION_ERROR"
        assert "SNAPSHOT_RECORD_UNREADABLE" in exc.value.detail_private
    assert _guard(FakeRunner(), data, snap_json, tmp_path)


def test_guard_refuses_a_missing_db(tmp_path):
    data, snap_json = restored(tmp_path)
    saved = (data / dbsafety.DB_NAME).read_bytes()
    (data / dbsafety.DB_NAME).unlink()
    with pytest.raises(core.Fail) as exc:
        _guard(FakeRunner(), data, snap_json, tmp_path)
    assert _fail_code(exc) == "GUARD_INSPECTION_ERROR"
    (data / dbsafety.DB_NAME).write_bytes(saved)
    assert _guard(FakeRunner(), data, snap_json, tmp_path)


def test_guard_passes_on_a_non_writable_data_folder_without_writing(tmp_path):
    """R-11: a clean DB in a folder ``claude`` cannot write still passes,
    which proves the guard never writes there (SQLite would need to)."""
    data, snap_json = restored(tmp_path)
    before = _tree(data)
    data.chmod(0o555)
    (data / dbsafety.DB_NAME).chmod(0o444)
    try:
        assert _guard(FakeRunner(), data, snap_json, tmp_path)
        assert sorted(os.listdir(data)) == [dbsafety.DB_NAME]
    finally:
        data.chmod(0o755)
    assert _tree(data) == before


# ---------------------------------------------------------------------------
# Restrictive caller umasks (review cycle 2)
# ---------------------------------------------------------------------------


def _modes(snap: Path) -> dict[str, int]:
    return {str(p.relative_to(snap)): stat.S_IMODE(p.stat().st_mode) for p in [snap, *sorted(snap.rglob("*"))]}


@pytest.mark.parametrize("mask", [0o400, 0o277, 0o022], ids=["0400", "0277", "0022-control"])
def test_full_snapshot_and_guard_under_a_restrictive_umask(tmp_path, mask):
    """A whole snapshot (WAL fixture: raw sidecars, work/ scratch, VACUUM
    target, snapshot.json) and a guard pass, with the caller's umask set to
    *mask*: folders 0700, raw files 0400, the rest 0600; the caller's umask
    is restored afterwards. 0022 is the same-fixture control."""
    data = tmp_path / "data"
    make_wal_data_dir(data, base_rows=6, wal_rows=4)
    previous = os.umask(mask)
    try:
        rec = dbsafety.snapshot(data, tmp_path / "snapshots", lambda: NOW)
        assert os.umask(mask) == mask  # restored to the caller's mask
    finally:
        os.umask(previous)
    # Kent's restore installs the file with an explicit mode (install -m 644).
    restored_dir = tmp_path / "restored"
    restored_dir.mkdir()
    shutil.copyfile(rec["db_path"], restored_dir / dbsafety.DB_NAME)
    (restored_dir / dbsafety.DB_NAME).chmod(0o644)
    previous = os.umask(mask)
    try:
        guard = dbsafety.rollback_guard(FakeRunner(), restored_dir, rec["snapshot_json"], work_dir=tmp_path)
        assert os.umask(mask) == mask
    finally:
        os.umask(previous)
    assert rec["tasks_count"] == 10
    assert guard["db_sha256"] == rec["db_sha256"]
    root = tmp_path / "snapshots"
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    snap = Path(rec["snapshot_dir"])
    assert _modes(snap) == {
        ".": 0o700,
        "raw": 0o700,
        "raw/vikunja.db": 0o400,
        "raw/vikunja.db-wal": 0o400,
        "raw/vikunja.db-shm": 0o400,
        "snapshot.json": 0o600,
        "vikunja.db": 0o600,
    }
    assert dbsafety.read_snapshot(rec["snapshot_json"])["db_sha256"] == rec["db_sha256"]


def test_write_new_json_fixes_its_mode_under_umask_0277(tmp_path):
    previous = os.umask(0o277)
    try:
        dbsafety._write_new_json(tmp_path / "a.json", {"schema_version": 1, "db_sha256": "0" * 64})
    finally:
        os.umask(previous)
    assert stat.S_IMODE((tmp_path / "a.json").stat().st_mode) == 0o600
    # Control: the default umask gives the same mode.
    dbsafety._write_new_json(tmp_path / "b.json", {"schema_version": 1, "db_sha256": "0" * 64})
    assert stat.S_IMODE((tmp_path / "b.json").stat().st_mode) == 0o600


# ---------------------------------------------------------------------------
# Parent-directory durability (post-merge review, HIGH)
# ---------------------------------------------------------------------------


class _DurabilitySpy:
    """Records, in order, each directory creation (by its parent's inode)
    and each fsync (by the fsynced file's inode)."""

    def __init__(self, monkeypatch) -> None:
        self.events: list[tuple[str, int]] = []
        real_mkdir, real_fsync = os.mkdir, os.fsync

        def mkdir(path, mode=0o777, *, dir_fd=None):
            if dir_fd is not None:
                parent = os.fstat(dir_fd).st_ino
                result = real_mkdir(path, mode, dir_fd=dir_fd)
            else:
                parent = os.stat(Path(path).parent).st_ino
                result = real_mkdir(path, mode)
            self.events.append(("mkdir", parent))
            return result

        def fsync(fd):
            self.events.append(("fsync", os.fstat(fd).st_ino))
            return real_fsync(fd)

        monkeypatch.setattr(os, "mkdir", mkdir)
        monkeypatch.setattr(os, "fsync", fsync)

    def unsynced_parents(self) -> list[int]:
        """Parents of a mkdir with no fsync of that parent afterwards."""
        missing = []
        for i, (kind, ino) in enumerate(self.events):
            if kind == "mkdir" and ("fsync", ino) not in self.events[i + 1:]:
                missing.append(ino)
        return missing


def test_every_created_folder_has_its_parent_fsynced(tmp_path, monkeypatch):
    data = tmp_path / "data"
    make_db(data / dbsafety.DB_NAME)
    root = tmp_path / "snapshots"  # absent: open_private_root creates it
    spy = _DurabilitySpy(monkeypatch)
    rec = dbsafety.snapshot(data, root, lambda: NOW)
    monkeypatch.undo()
    snap = Path(rec["snapshot_dir"])
    mkdir_parents = [ino for kind, ino in spy.events if kind == "mkdir"]
    # The root (parent: tmp_path), <UTC>/ (parent: root), raw/ and work/ (parent: <UTC>/).
    assert mkdir_parents == [tmp_path.stat().st_ino, root.stat().st_ino, snap.stat().st_ino,
                             snap.stat().st_ino]
    assert spy.unsynced_parents() == []


def test_an_existing_root_still_has_its_parent_fsynced(tmp_path, monkeypatch):
    """With the root already there its parent is fsynced anyway (an earlier
    creator may have died before its own fsync), before anything is created
    inside it; the new <UTC>/ is fsynced into the root as before."""
    data = tmp_path / "data"
    make_db(data / dbsafety.DB_NAME)
    root = dbsafety.prepare_private_root(tmp_path / "snapshots")
    spy = _DurabilitySpy(monkeypatch)
    dbsafety.snapshot(data, root, lambda: NOW)
    monkeypatch.undo()
    parent_sync = spy.events.index(("fsync", tmp_path.stat().st_ino))
    first_mkdir = next(i for i, (kind, _) in enumerate(spy.events) if kind == "mkdir")
    assert parent_sync < first_mkdir  # durable before any descendant is created
    assert ("fsync", root.stat().st_ino) in spy.events
    assert spy.unsynced_parents() == []


@pytest.mark.parametrize("code", ["ACTIVATION_ROOT", "FAILURES_ROOT"])
def test_open_private_root_fsyncs_the_parent_of_a_new_root(tmp_path, monkeypatch, code):
    spy = _DurabilitySpy(monkeypatch)
    os.close(dbsafety.open_private_root(tmp_path / "root", code=code))
    monkeypatch.undo()
    assert ("fsync", tmp_path.stat().st_ino) in spy.events
    assert spy.unsynced_parents() == []
    # Opening it again creates nothing, but the parent is fsynced again.
    spy = _DurabilitySpy(monkeypatch)
    os.close(dbsafety.open_private_root(tmp_path / "root", code=code))
    monkeypatch.undo()
    assert spy.events == [("fsync", tmp_path.stat().st_ino)]


@pytest.mark.parametrize("existing", [False, True], ids=["new-root", "existing-root"])
def test_a_failed_parent_fsync_refuses(tmp_path, monkeypatch, existing):
    root = tmp_path / "root"
    if existing:
        os.close(dbsafety.open_private_root(root, code="ACTIVATION_ROOT"))
    opened: list[int] = []
    real_open = os.open

    def recording_open(path, flags, *a, **kw):
        fd = real_open(path, flags, *a, **kw)
        if Path(path) == root:
            opened.append(fd)
        return fd

    def fails(directory):
        raise OSError("injected")

    monkeypatch.setattr(os, "open", recording_open)
    monkeypatch.setattr(dbsafety, "_fsync_dir", fails)
    with pytest.raises(core.Fail) as exc:
        dbsafety.open_private_root(root, code="ACTIVATION_ROOT")
    assert exc.value.code == "ACTIVATION_ROOT_PARENT_SYNC_FAILED"
    assert len(opened) == 1
    with pytest.raises(OSError):
        os.fstat(opened[0])  # the verified root descriptor was closed, not leaked
    monkeypatch.undo()
    # Control: the same root once the parent fsync works.
    os.close(dbsafety.open_private_root(root, code="ACTIVATION_ROOT"))


def test_a_lost_mkdir_race_still_fsyncs_the_parent(tmp_path, monkeypatch):
    """Concurrent init: another process created the root between our check
    and our mkdir, so this call gets FileExistsError. It must still make
    the root's entry durable before returning."""
    root = tmp_path / "root"
    real_mkdir = os.mkdir

    def racing_mkdir(path, mode=0o777, *, dir_fd=None):
        if Path(path) == root and dir_fd is None:
            real_mkdir(path, 0o700)  # the other process wins the race
            os.chmod(path, 0o700)
            raise FileExistsError(path)
        return real_mkdir(path, mode, dir_fd=dir_fd) if dir_fd is not None else real_mkdir(path, mode)

    monkeypatch.setattr(os, "mkdir", racing_mkdir)
    synced: list[Path] = []
    real_fsync_dir = dbsafety._fsync_dir

    def spy(directory):
        synced.append(Path(directory))
        return real_fsync_dir(directory)

    monkeypatch.setattr(dbsafety, "_fsync_dir", spy)
    os.close(dbsafety.open_private_root(root, code="SNAPSHOT_ROOT"))
    assert synced == [tmp_path]


# ---------------------------------------------------------------------------
# Copy and hash loops respect the deadline (post-merge review, MEDIUM)
# ---------------------------------------------------------------------------


class _StepClock:
    """Advances by *step* seconds on every read once armed."""

    def __init__(self, step: float) -> None:
        self.t = 0.0
        self.step = step
        self.armed = False

    def __call__(self) -> float:
        if self.armed:
            self.t += self.step
        return self.t


def test_raw_copy_stops_at_the_deadline_between_chunks(tmp_path, monkeypatch):
    monkeypatch.setattr(dbsafety, "_CHUNK", 4096)
    data = tmp_path / "data"
    db = make_db(data / dbsafety.DB_NAME, rows=400)
    assert db.stat().st_size > 4 * 4096
    clock = _StepClock(50.0)
    deadline = core.Deadline(120.0, clock=clock)
    clock.armed = True  # 50 s pass per chunk: the third chunk is past 120 s
    with pytest.raises(core.Fail) as exc:
        dbsafety.snapshot(data, tmp_path / "snaps", lambda: NOW, deadline=deadline)
    assert exc.value.code == "SNAPSHOT_DEADLINE"
    partial = tmp_path / "snaps" / "20261030T120000Z" / "raw" / dbsafety.DB_NAME
    assert partial.stat().st_size < db.stat().st_size  # stopped mid-copy, not after it
    assert not (tmp_path / "snaps" / "20261030T120000Z" / "snapshot.json").exists()
    # Control: the same fixture and chunk size with a clock that never moves.
    rec = dbsafety.snapshot(data, tmp_path / "snaps-ok", lambda: NOW,
                            deadline=core.Deadline(120.0, clock=_StepClock(50.0)))
    assert rec["tasks_count"] == 400


def test_hash_loop_stops_at_the_deadline(tmp_path, monkeypatch):
    monkeypatch.setattr(dbsafety, "_CHUNK", 1024)
    path = tmp_path / "blob"
    path.write_bytes(os.urandom(10 * 1024))
    fd = os.open(path, os.O_RDONLY)
    try:
        clock = _StepClock(30.0)
        deadline = core.Deadline(100.0, clock=clock)
        clock.armed = True
        with pytest.raises(core.Fail) as exc:
            dbsafety._sha256_fd(fd, deadline)
        assert exc.value.code == "SNAPSHOT_DEADLINE"
        # Control: same file, a clock that stays inside the budget.
        assert dbsafety._sha256_fd(fd, core.Deadline(100.0, clock=_StepClock(30.0))) == _sha(path)
        assert dbsafety._sha256_fd(fd) == _sha(path)  # no deadline: unchanged behaviour
    finally:
        os.close(fd)


def test_work_copy_and_final_hash_get_the_deadline(tmp_path, monkeypatch):
    """The scratch copy and the result hash receive the snapshot's deadline."""
    seen: list[object] = []
    real_copy, real_hash = dbsafety._copy_hashed, dbsafety._sha256_fd

    def copy(*a, **kw):
        seen.append(("copy", kw.get("deadline")))
        return real_copy(*a, **kw)

    def sha(fd, deadline=None):
        seen.append(("hash", deadline))
        return real_hash(fd, deadline)

    monkeypatch.setattr(dbsafety, "_copy_hashed", copy)
    monkeypatch.setattr(dbsafety, "_sha256_fd", sha)
    data = tmp_path / "data"
    make_wal_data_dir(data, base_rows=3, wal_rows=2)
    deadline = core.Deadline(120.0)
    dbsafety.snapshot(data, tmp_path / "snaps", lambda: NOW, deadline=deadline)
    assert seen and all(d is deadline for _, d in seen)
    assert [k for k, _ in seen].count("copy") == 6 and ("hash", deadline) in seen
