"""Synthetic upgrade loss, receipt binding, builder and CLI controls."""

import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import stat
import subprocess
import sys
import time

import pytest

from scripts.deploy.vikunja_release import baseline, core, dbsafety
from scripts.vikunja import build_release_baseline as builder
from scripts.vikunja import verify_release_upgrade as verifier
from scripts.vikunja import preflight_release_baseline as preflight


@pytest.fixture
def zero_upgrade(synthetic):
    s = synthetic
    s["record"]["release_version"] = "v2.8.0-rrule.3"
    s["record"]["tags"]["release"] = "example.invalid/app:v2.8.0-rrule.3"
    s["record"]["rollback"]["ref"] = "example.invalid/app:v2.8.0-rrule.2"
    with sqlite3.connect(s["post"]) as conn:
        conn.execute("DELETE FROM migration WHERE id NOT IN ('10','SCHEMA_INIT')")
        conn.execute("ALTER TABLE tasks DROP COLUMN target_only")
    s["facts"]["added_migration_ids"] = []
    s["facts"]["previous_version"] = "v2.8.0-rrule.2"
    s["facts"]["schema_identity"]["target"] = s["facts"]["schema_identity"]["pre_upgrade"]
    raw = json.dumps(s["facts"]).encode()
    s["bound"].write_bytes(raw)
    s["record"]["baseline"]["sha256"] = hashlib.sha256(raw).hexdigest()
    s["release"].write_text(json.dumps(s["record"]))
    receipt_path = s["snapshot"] / "baseline.json"
    receipt = json.loads(receipt_path.read_bytes())
    receipt["baseline"] = s["facts"]
    receipt["release_version"] = s["record"]["release_version"]
    receipt["baseline_sha256"] = s["record"]["baseline"]["sha256"]
    receipt_path.write_text(json.dumps(receipt))
    snapshot_path = s["snapshot"] / "snapshot.json"
    snapshot = json.loads(snapshot_path.read_bytes())
    snapshot["pre_version"] = "v2.8.0-rrule.2"
    snapshot_path.write_text(json.dumps(snapshot))
    return s


def test_zero_migration_acceptance(zero_upgrade):
    assert all(run_verify(zero_upgrade).values())


@pytest.mark.parametrize("count", [0, 10])
def test_builder_cli_count(synthetic, count):
    s = synthetic
    output = s["root"] / "new.json"
    post = s["pre"] if count == 0 else s["post"]
    result = subprocess.run([sys.executable, "scripts/vikunja/build_release_baseline.py",
        *map(str, [s["pre"], post, s["release"], output]), "--expected-added-count", str(count)],
        capture_output=True, text=True)
    assert (result.returncode, result.stdout, result.stderr) == (0, "BUILD_BASELINE_OK\n", "")
    assert len(json.loads(output.read_text())["added_migration_ids"]) == count


@pytest.mark.parametrize("args", [[], ["-1"], ["1.5"], ["True"], ["False"], ["ten"]])
def test_builder_cli_bad_count(synthetic, args):
    s = synthetic
    output = s["root"] / "new.json"
    option = ["--expected-added-count", *args] if args else []
    result = subprocess.run([sys.executable, "scripts/vikunja/build_release_baseline.py",
        *map(str, [s["pre"], s["post"], s["release"], output]), *option],
        capture_output=True, text=True)
    assert (result.returncode, result.stdout, result.stderr) == (2, "", "BUILD_BASELINE_USAGE\n")
    assert not output.exists()


@pytest.mark.parametrize("lost", [False, True])
def test_builder_cli_mismatch_writes_nothing(synthetic, lost):
    s = synthetic
    if lost:
        with sqlite3.connect(s["post"]) as conn:
            conn.execute("DELETE FROM migration WHERE id='10'")
    output = s["root"] / "new.json"
    result = subprocess.run([sys.executable, "scripts/vikunja/build_release_baseline.py",
        *map(str, [s["pre"], s["post"], s["release"], output]), "--expected-added-count",
        "10" if lost else "0"], capture_output=True, text=True)
    assert (result.returncode, result.stdout, result.stderr) == (1, "GATE_MIGRATIONS_MISMATCH\n", "")
    assert not output.exists()


@pytest.mark.parametrize("sql", ["INSERT INTO migration VALUES ('99')",
                                 "DELETE FROM migration WHERE id='10'"])
def test_zero_migration_acceptance_mismatch(zero_upgrade, sql):
    with sqlite3.connect(zero_upgrade["post"]) as conn:
        conn.execute(sql)
    assert not run_verify(zero_upgrade)["MIGRATIONS"]


@pytest.mark.parametrize("sql", [None, "INSERT INTO migration VALUES ('99')",
                                "DELETE FROM migration WHERE id='10'"])
def test_zero_migration_compare_and_preflight(zero_upgrade, sql):
    s = zero_upgrade
    snapshot = s["snapshot"] / dbsafety.DB_NAME
    if sql:
        for database in (s["pre"], snapshot):
            with sqlite3.connect(database) as conn:
                conn.execute(sql)
    result = baseline.compare(snapshot, s["facts"])
    if sql:
        assert result.code == "GATE_MIGRATIONS_MISMATCH"
        with pytest.raises(core.Fail, match="^GATE_MIGRATIONS_MISMATCH$"):
            preflight.preflight(s["record"], repository_root=s["root"])
    else:
        assert result.code is None
        assert all(value >= 0 for value in preflight.preflight(s["record"], repository_root=s["root"]))


@pytest.fixture
def synthetic(tmp_path):
    root = tmp_path / "synthetic-repository"
    root.mkdir()
    data = root / "data"
    data.mkdir()
    pre = data / dbsafety.DB_NAME
    with sqlite3.connect(pre) as conn:
        conn.executescript("""
            CREATE TABLE migration (id TEXT PRIMARY KEY);
            INSERT INTO migration VALUES ('10'),('SCHEMA_INIT');
            CREATE TABLE tasks (id INTEGER PRIMARY KEY, created_by_id INTEGER,
                repeats TEXT, repeats_from_current_date INTEGER);
            INSERT INTO tasks VALUES (1,1,'FREQ=DAILY',NULL),(2,99,NULL,0),(3,2,'',1);
            CREATE TABLE users (id INTEGER PRIMARY KEY);
            INSERT INTO users VALUES (1),(2);
            CREATE TABLE task_assignees (task_id INTEGER,user_id INTEGER);
            INSERT INTO task_assignees VALUES (1,1),(1,2),(1,2),(2,1),(99,1),(2,99);
            CREATE TABLE subscriptions (id INTEGER PRIMARY KEY, entity_type INTEGER,
                entity_id INTEGER,user_id INTEGER,muted INTEGER);
            INSERT INTO subscriptions VALUES (1,3,1,1,1),(2,3,1,1,0),(3,2,1,1,0),(4,3,99,99,NULL);
        """)
    post = root / "post copy.sqlite"
    shutil.copyfile(pre, post)
    with sqlite3.connect(post) as conn:
        conn.executemany("INSERT INTO migration VALUES (?)", [(str(i),) for i in range(30, 40)])
        conn.execute("ALTER TABLE tasks ADD COLUMN target_only TEXT")
        conn.executemany("INSERT INTO subscriptions VALUES (?,3,?,?,0)",
                         [(5,1,2),(6,2,1),(7,3,2)])
    archive = {"path": str(root / "image.tar"), "sha256": "c" * 64, "size": 1}
    record = {
        "schema_version": 1, "release_version": "v3.1.0-rrule.1", "source_revision": "d" * 40,
        "archive": archive, "image": {"config_digest": "sha256:" + "b" * 64,
            "index_digest": "sha256:" + "c" * 64, "platform": "linux/amd64", "user": "1000"},
        "tags": {"release": "example.invalid/app:v3.1.0-rrule.1", "active": "example.invalid/app:active"},
        "rollback": {"ref": "example.invalid/app:3.0.0-rrule.1", "image_id": "sha256:" + "a" * 64,
                     "archive": archive},
        "service": {"data_dir": str(data), "compose_file": str(root / "compose.yml"),
                    "project": "synthetic", "container": "synthetic", "info_url": "http://example.test/info"},
        "roots": {"snapshots": str(root / "snapshots"), "activation": str(root / "activation"),
                  "private_logs": str(root / "failures"),
                  "office4_sources": {"archive": str(root / "image.tar"), "rollback_archive": str(root / "old.tar")}},
    }
    facts = baseline.build(pre, post, record, expected_added=10)
    bound = root / "services/vikunja/baselines/synthetic.json"
    bound.parent.mkdir(parents=True)
    raw = json.dumps(facts).encode()
    bound.write_bytes(raw)
    record["baseline"] = {"path": str(bound.relative_to(root)), "sha256": hashlib.sha256(raw).hexdigest()}
    release = root / "release record.json"
    release.write_text(json.dumps(record))
    snap = dbsafety.snapshot(data, root / "snapshots", pre_version=baseline.previous_version(record),
                             running_image_id=record["rollback"]["image_id"])
    baseline.gate(record, snap, repository_root=root)
    return {"root": root, "pre": pre, "post": post, "record": record, "release": release,
            "facts": facts, "bound": bound, "snapshot": Path(snap["snapshot_dir"])}


def run_verify(s):
    return verifier.verify(s["snapshot"], s["post"], release_path=s["release"], repository_root=s["root"])


def interrupt_command(code, args, ready, signum):
    proc = subprocess.Popen([sys.executable, "-c", code, *map(str, args)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        deadline = time.monotonic() + 10
        while not ready.exists():
            assert proc.poll() is None, proc.communicate()
            assert time.monotonic() < deadline, "child did not reach copy"
            time.sleep(0.01)
        proc.send_signal(signum)
        out, err = proc.communicate(timeout=10)
        return proc.returncode, out, err
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate()


@pytest.fixture
def wal_copy(synthetic):
    """A detached stable copy with a committed change only in its WAL."""
    s = synthetic
    conn = sqlite3.connect(s["post"])
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.execute("PRAGMA wal_autocheckpoint=0")
        conn.execute("UPDATE tasks SET repeats='FREQ=WEEKLY' WHERE id=1")
        conn.commit()
        folder = s["root"] / "stable-copy"
        folder.mkdir()
        post = folder / "arbitrary name.sqlite"
        for suffix in ("", "-wal"):
            shutil.copyfile(str(s["post"]) + suffix, str(post) + suffix)
        s["post"] = post
    finally:
        conn.close()
    return s


def test_verifier_reads_wal_without_modifying_given_copy(wal_copy, tmp_path, monkeypatch):
    s = wal_copy
    scratch = tmp_path / "private-temp"
    scratch.mkdir()
    monkeypatch.setattr(verifier.tempfile, "tempdir", str(scratch))
    before = {p.name: p.read_bytes() for p in s["post"].parent.iterdir()}
    with baseline._connect(s["post"], None) as conn:
        assert conn.execute("SELECT repeats FROM tasks WHERE id=1").fetchone() == ("FREQ=DAILY",)
    checks = run_verify(s)
    assert not checks["REPEATS"]
    assert all(value for key, value in checks.items() if key != "REPEATS")
    assert {p.name: p.read_bytes() for p in s["post"].parent.iterdir()} == before
    assert list(scratch.iterdir()) == []


@pytest.mark.parametrize("signum", [signal.SIGTERM, signal.SIGHUP])
@pytest.mark.parametrize("stage", ["copy", "snapshot", "verify"])
def test_verifier_termination_cleans_wal_copy(wal_copy, tmp_path, signum, stage):
    s = wal_copy
    ready = tmp_path / "ready"
    scratch = tmp_path / "private-temp"
    scratch.mkdir()
    before = {p.name: p.read_bytes() for p in s["post"].parent.iterdir()}
    code = """
import signal, sys, tempfile
from pathlib import Path
from scripts.vikunja import verify_release_upgrade as command
tempfile.tempdir = sys.argv[5]
stage = sys.argv[7]
owner, name = ((command.dbsafety, '_copy_hashed') if stage == 'copy' else
               (command.dbsafety, 'snapshot') if stage == 'snapshot' else
               (command.baseline, '_connect'))
original = getattr(owner, name)
def slow(*args, **kwargs):
    if stage != 'verify' or str(args[0]).startswith(sys.argv[5]):
        if stage == 'copy':
            original(*args, **kwargs)
        Path(sys.argv[6]).touch()
        signal.pause()
    return original(*args, **kwargs)
setattr(owner, name, slow)
raise SystemExit(command.main(sys.argv[3:5], release_path=Path(sys.argv[2]),
                              repository_root=Path(sys.argv[1])))
"""
    result = interrupt_command(code, [s["root"], s["release"], s["snapshot"], s["post"],
                                      scratch, ready, stage], ready, signum)
    assert result == (1, "ACCEPTANCE_FAILED\n", "")
    assert list(scratch.iterdir()) == []
    assert {p.name: p.read_bytes() for p in s["post"].parent.iterdir()} == before


@pytest.mark.parametrize("active_error", [False, True])
def test_verifier_cleanup_failure_is_reported(wal_copy, monkeypatch, capsys, active_error):
    s = wal_copy
    original = shutil.rmtree
    retained = []
    def refuse(path, *args, **kwargs):
        if Path(path).name.startswith("vikunja-acceptance-"):
            retained.append(path)
            raise OSError("private sentinel")
        return original(path, *args, **kwargs)
    if active_error:
        def fail(*args, **kwargs):
            raise KeyboardInterrupt
        monkeypatch.setattr(dbsafety, "snapshot", fail)
    monkeypatch.setattr(shutil, "rmtree", refuse)
    try:
        assert verifier.main([str(s["snapshot"]), str(s["post"])], release_path=s["release"],
                             repository_root=s["root"]) == 1
        output = capsys.readouterr()
        assert output.out == "ACCEPTANCE_CLEANUP_FAILED\n" and output.err == ""
    finally:
        for path in retained:
            original(path)


def test_correct_upgrade_preserves_duplicates_nulls_and_muted(synthetic):
    s = synthetic
    assert all(run_verify(s).values())
    evidence = s["snapshot"] / verifier.EVIDENCE_NAME
    assert stat.S_IMODE(evidence.stat().st_mode) == 0o600
    observed = json.loads(evidence.read_bytes())["aggregates"]
    assert observed["duplicate_excess"] == 1
    assert observed["missing_eligible_pairs"] == 0
    assert "existing_subscriptions" not in observed
    receipt = json.loads((s["snapshot"] / "baseline.json").read_bytes())
    assert [4,99,99,None] in receipt["aggregates"]["existing_subscriptions"]
    with pytest.raises(core.Fail, match="^ACCEPTANCE_EVIDENCE_WRITE_FAILED$"):
        run_verify(s)


@pytest.mark.parametrize("sql,check", [
    ("DELETE FROM migration WHERE id='10'", "MIGRATIONS"),
    ("DELETE FROM migration WHERE id='SCHEMA_INIT'", "MIGRATIONS"),
    ("DELETE FROM migration WHERE id='30'", "MIGRATIONS"),
    ("INSERT INTO migration VALUES ('99')", "MIGRATIONS"),
    ("DELETE FROM tasks WHERE id=2", "TASKS"),
    ("UPDATE tasks SET repeats='FREQ=WEEKLY' WHERE id=1", "REPEATS"),
    ("UPDATE tasks SET repeats=NULL WHERE id=1", "REPEATS"),
    ("UPDATE tasks SET repeats_from_current_date=0 WHERE id=1", "REPEATS"),
    ("ALTER TABLE tasks ADD COLUMN unexpected TEXT", "SCHEMA"),
    ("DELETE FROM subscriptions WHERE id=5", "SUBSCRIPTION_TOTAL"),
    ("UPDATE subscriptions SET entity_id=88 WHERE id=5", "ELIGIBLE_PAIRS"),
    ("INSERT INTO subscriptions VALUES (8,3,1,1,0)", "DUPLICATES"),
    ("UPDATE subscriptions SET muted=0 WHERE id=1", "EXISTING_SUBSCRIPTIONS"),
    ("UPDATE subscriptions SET user_id=98 WHERE id=4", "EXISTING_SUBSCRIPTIONS"),
    ("UPDATE subscriptions SET id=88 WHERE id=4", "EXISTING_SUBSCRIPTIONS"),
])
def test_seeded_losses(synthetic, sql, check):
    s = synthetic
    with sqlite3.connect(s["post"]) as conn:
        conn.execute(sql)
    checks = run_verify(s)
    assert not checks[check]
    if check == "ELIGIBLE_PAIRS":
        assert checks["SUBSCRIPTION_TOTAL"]


@pytest.mark.parametrize("kind", ["snapshot-bytes", "snapshot-hash", "receipt-hash", "baseline-hash",
    "version", "config", "rollback-version", "rollback-image", "receipt-aggregate", "bound-bytes",
    "receipt-mode", "directory-mode", "receipt-symlink", "directory-symlink"])
def test_binding_failures(synthetic, kind):
    s = synthetic
    receipt_path = s["snapshot"] / "baseline.json"
    receipt = json.loads(receipt_path.read_bytes())
    if kind == "snapshot-bytes":
        with sqlite3.connect(s["snapshot"] / dbsafety.DB_NAME) as conn:
            conn.execute("UPDATE tasks SET repeats='changed'")
    elif kind == "snapshot-hash":
        path = s["snapshot"] / "snapshot.json"
        value = json.loads(path.read_bytes())
        value["db_sha256"] = "e" * 64
        path.write_text(json.dumps(value))
    elif kind in {"rollback-version", "rollback-image"}:
        record = copy.deepcopy(s["record"])
        record["rollback"]["ref" if kind == "rollback-version" else "image_id"] = (
            "example.invalid/app:3.0.1" if kind == "rollback-version" else "sha256:" + "e" * 64)
        s["release"].write_text(json.dumps(record))
    elif kind == "receipt-aggregate":
        receipt["aggregates"]["repeat_hash"] = "e" * 64
    elif kind == "bound-bytes":
        s["bound"].write_bytes(b"{}")
    elif kind == "receipt-mode":
        receipt_path.chmod(0o644)
    elif kind == "directory-mode":
        s["snapshot"].chmod(0o755)
    elif kind == "receipt-symlink":
        target = s["root"] / "receipt.json"
        receipt_path.rename(target)
        receipt_path.symlink_to(target)
    elif kind == "directory-symlink":
        link = s["root"] / "linked"
        link.symlink_to(s["snapshot"], target_is_directory=True)
        s["snapshot"] = link
    else:
        field = {"receipt-hash": "snapshot_sha256", "baseline-hash": "baseline_sha256",
                 "version": "release_version", "config": "config_digest"}[kind]
        receipt[field] = {"version": "v3.9.0", "config": "sha256:" + "e" * 64}.get(kind, "e" * 64)
    if kind in {"receipt-aggregate", "receipt-hash", "baseline-hash", "version", "config"}:
        receipt_path.write_text(json.dumps(receipt))
    assert verifier.main([str(s["snapshot"]), str(s["post"])], release_path=s["release"],
                         repository_root=s["root"]) == 1


def test_corruption_and_noncomputable_checks(synthetic, capsys):
    s = synthetic
    s["post"].write_bytes(b"private sentinel corrupt data")
    assert verifier.main([str(s["snapshot"]), str(s["post"])], release_path=s["release"],
                         repository_root=s["root"]) == 1
    assert capsys.readouterr().out == "ACCEPTANCE_COMPUTE_FAILED\n"


def test_evidence_failure_sanitized(synthetic, monkeypatch, capsys):
    s = synthetic
    def bad(*args):
        raise OSError("private-path timestamp hash aggregate sentinel")
    monkeypatch.setattr(verifier, "_write_evidence", bad)
    assert verifier.main([str(s["snapshot"]), str(s["post"])], release_path=s["release"],
                         repository_root=s["root"]) == 1
    output = capsys.readouterr()
    assert output.out == "ACCEPTANCE_EVIDENCE_WRITE_FAILED\n" and output.err == ""


def test_evidence_short_writes_are_durable(synthetic, monkeypatch):
    events = []
    write, fsync = os.write, os.fsync
    def short(fd, payload):
        return write(fd, payload[:2])
    def sync(fd):
        events.append("directory" if stat.S_ISDIR(os.fstat(fd).st_mode) else "file")
        return fsync(fd)
    monkeypatch.setattr(os, "write", short)
    monkeypatch.setattr(os, "fsync", sync)
    assert all(run_verify(synthetic).values())
    assert events[-2:] == ["file", "directory"]


def test_builder_deterministic_create_only_and_main(synthetic, capsys):
    s = synthetic
    outputs = [s["root"] / f"new baseline {i}.json" for i in range(2)]
    for output in outputs:
        assert builder.main([*map(str, [s["pre"], s["post"], s["release"], output]),
                             "--expected-added-count", "10"]) == 0
    assert outputs[0].read_bytes() == outputs[1].read_bytes()
    assert outputs[0].read_bytes().endswith(b"\n")
    assert json.loads(outputs[0].read_bytes()) == s["facts"]
    original = outputs[0].read_bytes()
    assert builder.main([*map(str, [s["pre"], s["post"], s["release"], outputs[0]]),
                         "--expected-added-count", "10"]) == 1
    assert outputs[0].read_bytes() == original
    assert "sentinel" not in capsys.readouterr().out


@pytest.mark.parametrize("field", ["task_count", "repeat_hash", "metadata", "path", "timestamp",
                                   "previous_version", "previous_image_config", "schema_version"])
def test_builder_forbidden_fields(synthetic, monkeypatch, field):
    s = synthetic
    facts = copy.deepcopy(s["facts"])
    facts[field] = {"previous_version": "v3.9.0", "previous_image_config": "sha256:" + "e" * 64,
                   "schema_version": True}.get(field, "private sentinel")
    monkeypatch.setattr(baseline, "build", lambda *args, **kwargs: facts)
    output = s["root"] / "new.json"
    with pytest.raises(core.Fail, match="^BUILD_BASELINE_INVALID$"):
        builder.build(s["pre"], s["post"], s["record"], output, expected_added=10)
    assert not output.exists()


@pytest.mark.parametrize("sql", ["DELETE FROM migration WHERE id='10'",
    "DELETE FROM migration WHERE id='30'", "INSERT INTO migration VALUES ('99')"])
def test_builder_wrong_migration_sets(synthetic, sql):
    s = synthetic
    with sqlite3.connect(s["post"]) as conn:
        conn.execute(sql)
    with pytest.raises(core.Fail, match="^GATE_MIGRATIONS_MISMATCH$"):
        builder.build(s["pre"], s["post"], s["record"], s["root"] / "new.json", expected_added=10)
    assert not (s["root"] / "new.json").exists()


def test_builder_symlink_destination(synthetic):
    s = synthetic
    output = s["root"] / "new.json"
    output.symlink_to(s["root"] / "absent")
    with pytest.raises(core.Fail, match="^BUILD_BASELINE_FAILED$"):
        builder.build(s["pre"], s["post"], s["record"], output, expected_added=10)
    assert not (s["root"] / "absent").exists()


@pytest.mark.parametrize("script", ["preflight_release_baseline", "verify_release_upgrade", "build_release_baseline"])
def test_subprocess_help_and_usage(script):
    path = Path("scripts/vikunja") / (script + ".py")
    help_result = subprocess.run([sys.executable, str(path), "--help"], capture_output=True, text=True)
    assert help_result.returncode == 0 and "usage:" in help_result.stdout
    usage = subprocess.run([sys.executable, str(path)], capture_output=True, text=True)
    assert usage.returncode == 2 and "Traceback" not in usage.stderr
    invalid = subprocess.run([sys.executable, str(path), "--private-sentinel"],
                             capture_output=True, text=True)
    assert invalid.returncode == 2
    assert "sentinel" not in invalid.stdout + invalid.stderr


@pytest.mark.parametrize("interpreter", [sys.executable, shutil.which("python3.12")])
def test_subprocess_synthetic_interfaces(synthetic, interpreter):
    if interpreter is None:
        pytest.skip("Python 3.12 unavailable")
    s = synthetic
    builder_result = subprocess.run([interpreter, "scripts/vikunja/build_release_baseline.py",
        *map(str, [s["pre"], s["post"], s["release"], s["root"] / "new output.json"]),
        "--expected-added-count", "10"],
        capture_output=True, text=True)
    assert builder_result.returncode == 0, builder_result.stdout + builder_result.stderr
    # Inject repository/release defaults without changing either positional interface.
    commands = [
        ("preflight_release_baseline", [s["release"]], "repository_root=Path(sys.argv[1])"),
        ("verify_release_upgrade", [s["snapshot"], s["post"]],
         "repository_root=Path(sys.argv[1]), release_path=Path(sys.argv[2])"),
    ]
    for module, args, defaults in commands:
        code = ("import sys; from pathlib import Path; from scripts.vikunja import " + module +
                " as command; raise SystemExit(command.main(sys.argv[3:], " + defaults + "))")
        result = subprocess.run([interpreter, "-c", code, str(s["root"]), str(s["release"]),
                                 *map(str, args)], capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr
        assert str(s["root"]) not in result.stdout and result.stderr == ""
