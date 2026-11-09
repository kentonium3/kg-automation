"""Synthetic qualification, exact schema identity and private receipt tests."""

import copy
import hashlib
import json
import os
import shutil
import sqlite3
import stat
from datetime import datetime, timezone

import pytest

from scripts.deploy.vikunja_release import baseline as b, core, dbsafety


@pytest.fixture
def qualified(tmp_path):
    pre = tmp_path / "pre.sqlite"
    with sqlite3.connect(pre) as conn:
        conn.executescript("""
            CREATE TABLE migration (id TEXT PRIMARY KEY);
            INSERT INTO migration VALUES ('10'),('20'),('SCHEMA_INIT');
            CREATE TABLE tasks (id INTEGER PRIMARY KEY, created_by_id INTEGER,
                repeats TEXT, repeats_from_current_date INTEGER, deleted INTEGER);
            INSERT INTO tasks VALUES (1,1,'FREQ=DAILY',NULL,1),(2,99,'',0,0),(3,2,NULL,1,0);
            CREATE TABLE users (id INTEGER PRIMARY KEY, status INTEGER);
            INSERT INTO users VALUES (1,0),(2,99);
            CREATE TABLE task_assignees (task_id INTEGER,user_id INTEGER);
            INSERT INTO task_assignees VALUES (1,1),(1,2),(1,2),(2,1),(99,1),(2,99);
            CREATE TABLE subscriptions (id INTEGER PRIMARY KEY, entity_type INTEGER,
                entity_id INTEGER, user_id INTEGER, muted INTEGER);
            INSERT INTO subscriptions VALUES (1,3,1,1,1),(2,3,1,1,0),(3,2,2,1,1),(4,3,99,99,1);
        """)
    post = tmp_path / "post.sqlite"
    shutil.copyfile(pre, post)
    with sqlite3.connect(post) as conn:
        conn.executemany("INSERT INTO migration VALUES (?)", [(str(i),) for i in range(30, 40)])
        conn.execute("ALTER TABLE tasks ADD COLUMN target_only TEXT")
    record = {"rollback": {"ref": "example.invalid/app:3.0.0-rrule.1", "image_id": "sha256:" + "a" * 64},
              "release_version": "v3.1.0-rrule.1", "image": {"config_digest": "sha256:" + "b" * 64}}
    facts = b.build(pre, post, record)
    target = tmp_path / "services/vikunja/baselines/synthetic.json"
    target.parent.mkdir(parents=True)
    raw = json.dumps(facts).encode()
    target.write_bytes(raw)
    record["baseline"] = {"path": str(target.relative_to(tmp_path)),
                          "sha256": hashlib.sha256(raw).hexdigest()}
    return pre, post, record, facts, target


def test_load_build_and_compare(qualified, tmp_path):
    pre, post, record, facts, _ = qualified
    assert b.load_bound(record, tmp_path) == facts
    assert facts["previous_version"] == "v3.0.0-rrule.1"
    assert facts["pre_upgrade_migration_ids"] == ["10", "20", "SCHEMA_INIT"]
    assert facts["added_migration_ids"] == [str(i) for i in range(30, 40)]
    assert set(facts) == b._FIELDS
    result = b.compare(pre, facts)
    assert result.code is None
    evidence = result.aggregates
    assert evidence["task_count"] == 3 and evidence["repeat_count"] == 1
    expected = json.dumps([[1, "FREQ=DAILY", None]], separators=(",", ":")).encode()
    assert evidence["repeat_hash"] == hashlib.sha256(expected).hexdigest()
    assert evidence["task_subscription_rows"] == 3
    assert evidence["missing_eligible_pairs"] == 3
    assert evidence["expected_task_subscription_rows"] == 6
    assert evidence["duplicate_excess"] == 1
    assert evidence["existing_subscriptions"] == [[1, 1, 1, 1], [2, 1, 1, 0], [4, 99, 99, 1]]
    assert b.compare(post, facts).code == "GATE_MIGRATIONS_MISMATCH"


@pytest.mark.parametrize("change", [
    lambda f: f.update(schema_version=True), lambda f: f.update(private_count=123),
    lambda f: f.update(pre_upgrade_migration_ids=["20", "10"]),
    lambda f: f.update(pre_upgrade_migration_ids=["10", "10"]),
    lambda f: f.update(pre_upgrade_migration_ids=["SCHEMA_INIT", "10", "20"]),
    lambda f: f.update(pre_upgrade_migration_ids=["10", "20", "SCHEMA_INIT", "SCHEMA_INIT"]),
    lambda f: f.update(pre_upgrade_migration_ids=["10", "20", "SCHEMA_OTHER"]),
    lambda f: f.update(added_migration_ids=["10"]),
    lambda f: f.update(previous_version="v3.0.1"),
    lambda f: f.update(previous_image_config="sha256:" + "c" * 64),
    lambda f: f["schema_identity"].update(algorithm="unknown"),
    lambda f: f["schema_identity"].update(target="A" * 64),
    lambda f: f["schema_identity"].update(extra=None),
])
def test_bound_rejects_invalid_schema_and_identity(qualified, tmp_path, change):
    _, _, record, facts, target = qualified
    assert b.load_bound(record, tmp_path) == facts
    change(facts)
    raw = json.dumps(facts).encode()
    target.write_bytes(raw)
    record["baseline"]["sha256"] = hashlib.sha256(raw).hexdigest()
    with pytest.raises(core.Fail, match="^GATE_BASELINE_UNREADABLE$"):
        b.load_bound(record, tmp_path)


def test_validate_rejects_schema_init_in_added_ids(qualified):
    _, _, _, facts, _ = qualified
    facts["pre_upgrade_migration_ids"].remove("SCHEMA_INIT")
    facts["added_migration_ids"].append("SCHEMA_INIT")
    assert not b.validate(facts)


def test_compare_rejects_unlisted_schema_init(qualified):
    pre, _, _, facts, _ = qualified
    facts["pre_upgrade_migration_ids"].remove("SCHEMA_INIT")
    assert b.compare(pre, facts).code == "GATE_MIGRATIONS_MISMATCH"


@pytest.mark.parametrize("kind", ["missing", "digest", "escape", "file-link", "parent-link", "oversize", "json", "duplicate"])
def test_bound_file_refusals(qualified, tmp_path, kind):
    _, _, record, facts, target = qualified
    assert b.load_bound(record, tmp_path) == facts
    if kind == "missing":
        record.pop("baseline")
    elif kind == "digest":
        target.write_bytes(target.read_bytes() + b" ")
    elif kind == "escape":
        record["baseline"]["path"] = "services/vikunja/baselines/../synthetic.json"
    elif kind in ("file-link", "parent-link"):
        if kind == "file-link":
            dest = tmp_path / "elsewhere.json"
            target.rename(dest)
            target.symlink_to(dest)
        else:
            dest = tmp_path / "elsewhere"
            target.parent.rename(dest)
            target.parent.symlink_to(dest, target_is_directory=True)
    else:
        raw = {"oversize": b" " * (b.MAX_BASELINE_BYTES + 1), "json": b"{",
               "duplicate": b'{"schema_version":1,"schema_version":1}'}[kind]
        target.write_bytes(raw)
        record["baseline"]["sha256"] = hashlib.sha256(raw).hexdigest()
    with pytest.raises(core.Fail, match="^GATE_BASELINE_UNREADABLE$"):
        b.load_bound(record, tmp_path)


@pytest.mark.parametrize("sql,code", [
    ("DELETE FROM migration WHERE id='10'", "GATE_MIGRATIONS_MISMATCH"),
    ("DELETE FROM migration WHERE id='SCHEMA_INIT'", "GATE_MIGRATIONS_MISMATCH"),
    ("INSERT INTO migration VALUES ('99')", "GATE_MIGRATIONS_MISMATCH"),
    ("INSERT INTO migration VALUES ('SCHEMA_OTHER')", "GATE_MIGRATIONS_MISMATCH"),
    ("UPDATE migration SET id='11' WHERE id='10'", "GATE_MIGRATIONS_MISMATCH"),
    ("INSERT INTO migration VALUES (NULL)", "GATE_MIGRATIONS_MISMATCH"),
    ("DROP TABLE migration", "GATE_MIGRATIONS_MISMATCH"),
    ("ALTER TABLE tasks ADD COLUMN surprise TEXT", "GATE_SCHEMA_MISMATCH"),
])
def test_compare_mismatches(qualified, sql, code):
    pre, _, _, facts, _ = qualified
    assert b.compare(pre, facts).code is None
    with sqlite3.connect(pre) as conn:
        conn.execute(sql)
    result = b.compare(pre, facts)
    assert result.code == code and result.aggregates is None


def test_noncomputable_aggregates(qualified):
    pre, _, _, facts, _ = qualified
    with sqlite3.connect(pre) as conn:
        conn.execute("ALTER TABLE subscriptions DROP COLUMN muted")
        facts["schema_identity"]["pre_upgrade"] = b.schema_identity(conn)
    assert b.compare(pre, facts).code == "GATE_AGGREGATE_FAILED"


@pytest.mark.parametrize("sql", ["DELETE FROM migration WHERE id='10'", "DELETE FROM migration WHERE id='30'",
                                 "INSERT INTO migration VALUES ('99')"])
def test_build_requires_retention_and_ten_additions(qualified, sql):
    pre, post, record, _, _ = qualified
    with sqlite3.connect(post) as conn:
        conn.execute(sql)
    with pytest.raises(core.Fail, match="GATE_MIGRATIONS_MISMATCH"):
        b.build(pre, post, record)


def test_schema_survives_real_consolidation_route(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    with sqlite3.connect(data / dbsafety.DB_NAME) as conn:
        conn.executescript('''
            CREATE TABLE tasks (id INTEGER PRIMARY KEY, "Mixed Case" TEXT UNIQUE DEFAULT 'Do NOT Fold');
            ALTER TABLE tasks ADD COLUMN "Quoted Name" TEXT;
            CREATE INDEX "Index Name" ON tasks ("Quoted Name");
            CREATE TRIGGER "Trigger Name" AFTER INSERT ON tasks BEGIN
                UPDATE tasks SET "Quoted Name" = 'Literal  TWO spaces' WHERE id=new.id;
            END;
            CREATE VIEW "View Name" AS SELECT "Mixed Case" FROM tasks;
            INSERT INTO tasks (id) VALUES (1);
        ''')
        expected = b.schema_identity(conn)
        rows = conn.execute("SELECT type,name,tbl_name,sql FROM main.sqlite_master "
                            "ORDER BY type COLLATE BINARY,name COLLATE BINARY,tbl_name COLLATE BINARY").fetchall()
        assert any(row[3] is None for row in rows)
        assert expected == hashlib.sha256(b._json(rows)).hexdigest()
    snap = dbsafety.snapshot(data, tmp_path / "snapshots", lambda: datetime(2030, 1, 1, tzinfo=timezone.utc))
    with sqlite3.connect(snap["db_path"]) as conn:
        assert b.schema_identity(conn) == expected
        conn.execute('ALTER TABLE tasks ADD COLUMN changed TEXT')
        assert b.schema_identity(conn) != expected


@pytest.mark.parametrize("literal", ["Case Matters", "Case  Matters", "case matters"])
def test_schema_literals_are_not_normalized(tmp_path, literal):
    with sqlite3.connect(tmp_path / "schema.sqlite") as conn:
        conn.execute(f"CREATE TABLE tasks (value TEXT DEFAULT '{literal}')")
        rows = conn.execute("SELECT type,name,tbl_name,sql FROM sqlite_master").fetchall()
        assert literal in rows[0][3]
        assert b.schema_identity(conn) == hashlib.sha256(b._json(rows)).hexdigest()


def test_bound_hashes_and_parses_same_bytes(qualified, tmp_path, monkeypatch):
    _, _, record, facts, target = qualified
    loads = json.loads
    def replace_after_read(raw, **kwargs):
        target.write_text('{"replacement":"untrusted"}')
        return loads(raw, **kwargs)
    monkeypatch.setattr(b.json, "loads", replace_after_read)
    assert b.load_bound(record, tmp_path) == facts


def test_equal_subscription_totals_do_not_hide_substitution(qualified):
    pre, _, _, facts, _ = qualified
    before = b.compare(pre, facts).aggregates
    with sqlite3.connect(pre) as conn:
        conn.execute("UPDATE subscriptions SET entity_id=88 WHERE entity_id=1")
    after = b.compare(pre, facts).aggregates
    assert before["task_subscription_rows"] == after["task_subscription_rows"]
    assert after["missing_eligible_pairs"] == before["missing_eligible_pairs"] + 1
    assert after["existing_subscriptions"] != before["existing_subscriptions"]


def test_sqlite_progress_handler_interrupts_one_long_query(qualified):
    pre, _, _, _, _ = qualified
    ticks = [0]
    def clock():
        ticks[0] += 1
        return ticks[0]
    deadline = core.Deadline(10, clock)
    with pytest.raises(core.Fail, match="^GATE_DEADLINE$"):
        with b._connect(pre, deadline) as conn:
            conn.execute("WITH RECURSIVE n(x) AS (VALUES(0) UNION ALL SELECT x+1 FROM n WHERE x<100000000) "
                         "SELECT sum(x) FROM n").fetchone()
    assert ticks[0] < 20


def _receipt(qualified):
    pre, _, record, facts, _ = qualified
    return {"schema_version": 1, "snapshot_sha256": hashlib.sha256(pre.read_bytes()).hexdigest(),
            "baseline_sha256": record["baseline"]["sha256"], "release_version": record["release_version"],
            "config_digest": record["image"]["config_digest"], "baseline": facts,
            "aggregates": b.compare(pre, facts).aggregates}


def test_receipt_short_writes_and_fsync_order(qualified, tmp_path, monkeypatch):
    folder = tmp_path / "snapshot"
    folder.mkdir(mode=0o700)
    receipt = _receipt(qualified)
    write, fsync = os.write, os.fsync
    events = []
    def short(fd, payload):
        events.append("write")
        return write(fd, payload[:2])
    def synced(fd):
        events.append("dir" if stat.S_ISDIR(os.fstat(fd).st_mode) else "file")
        return fsync(fd)
    monkeypatch.setattr(b.os, "write", short)
    monkeypatch.setattr(b.os, "fsync", synced)
    b.write_receipt(folder, receipt)
    assert json.loads((folder / "baseline.json").read_bytes()) == receipt
    assert events[-2:] == ["file", "dir"]
    assert stat.S_IMODE((folder / "baseline.json").stat().st_mode) == 0o600
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700
    with pytest.raises(core.Fail, match="GATE_RECEIPT_WRITE_FAILED"):
        b.write_receipt(folder, receipt)


@pytest.mark.parametrize("kind", ["zero", "write", "file-fsync", "dir-fsync", "permissions", "unsafe-parent", "symlink", "file-symlink", "malformed"])
def test_receipt_failures(qualified, tmp_path, monkeypatch, kind):
    folder = tmp_path / "snapshot"
    folder.mkdir(mode=0o700)
    receipt = _receipt(qualified)
    real_sync = os.fsync
    def bad(*args, **kwargs):
        raise OSError("synthetic sentinel")
    if kind == "zero":
        monkeypatch.setattr(b.os, "write", lambda *a: 0)
    elif kind == "write":
        monkeypatch.setattr(b.os, "write", bad)
    elif kind.endswith("fsync"):
        def sync(fd):
            is_dir = stat.S_ISDIR(os.fstat(fd).st_mode)
            if is_dir == (kind == "dir-fsync"):
                bad()
            real_sync(fd)
        monkeypatch.setattr(b.os, "fsync", sync)
    elif kind == "permissions":
        monkeypatch.setattr(b.os, "fchmod", bad)
    elif kind == "unsafe-parent":
        folder.chmod(0o755)
    elif kind == "symlink":
        link = tmp_path / "link"
        link.symlink_to(folder, target_is_directory=True)
        folder = link
    elif kind == "file-symlink":
        (folder / "baseline.json").symlink_to(tmp_path / "absent.json")
    else:
        receipt["aggregates"]["task_count"] = -1
    with pytest.raises(core.Fail, match="GATE_RECEIPT_WRITE_FAILED"):
        b.write_receipt(folder, receipt)


@pytest.mark.parametrize("at_directory", [False, True])
def test_receipt_fsync_crash_is_create_only(qualified, tmp_path, monkeypatch, at_directory):
    folder = tmp_path / "snapshot"
    folder.mkdir(mode=0o700)
    receipt = _receipt(qualified)
    class Crash(BaseException):
        pass
    fsync = os.fsync
    def crash(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode) == at_directory:
            raise Crash()
        fsync(fd)
    monkeypatch.setattr(b.os, "fsync", crash)
    with pytest.raises(Crash):
        b.write_receipt(folder, receipt)
    assert (folder / "baseline.json").exists()
    with pytest.raises(core.Fail, match="GATE_RECEIPT_WRITE_FAILED"):
        b.write_receipt(folder, receipt)


@pytest.mark.parametrize("stage", ["read", "query", "hash", "write"])
def test_deadline_interrupts_work(qualified, tmp_path, monkeypatch, stage):
    pre, _, record, facts, _ = qualified
    now = [0.0]
    deadline = core.Deadline(1, lambda: now[0])
    def expire(*args):
        now[0] = 2
    if stage == "read":
        now[0] = 2
        call = lambda: b.load_bound(record, tmp_path, deadline=deadline)
    elif stage == "query":
        # SQLite's progress callback interrupts execution, not just a final check.
        with sqlite3.connect(pre) as conn:
            conn.executemany("INSERT INTO task_assignees VALUES (?,?)", [(i, i) for i in range(10000)])
        facts = copy.deepcopy(facts)
        def clock():
            now[0] += 0.001
            return now[0]
        deadline = core.Deadline(0.05, clock)
        call = lambda: b.compare(pre, facts, deadline=deadline)
    elif stage == "hash":
        def rows():
            for i in range(100):
                expire()
                yield [i]
        call = lambda: b._hash_rows(rows(), deadline)
    else:
        folder = tmp_path / "receipt"
        folder.mkdir(mode=0o700)
        receipt = _receipt(qualified)
        real = os.write
        def slow(fd, payload):
            expire()
            return real(fd, payload[:1])
        monkeypatch.setattr(b.os, "write", slow)
        call = lambda: b.write_receipt(folder, receipt, deadline=deadline)
    with pytest.raises(core.Fail, match="^GATE_DEADLINE$"):
        call()
