"""Tests for the operator rollback helper (#1087, WP06: T026-T029).

No docker, network or ssh: a stateful fake docker (containers, tags, compose,
curl) is injected as the runner, ``docker logs`` is a tiny local Python child
behind an injected ``Popen``, and every root comes from a ``release.json``
copy pointing into ``tmp_path``. The databases are SQLite fixtures in the
v2.4.0 shape and a migrated shape (``tasks.repeats``,
``task_repeat_legacy_backup``), with post-cutover writes held in the WAL.
Every refusal has a same-fixture positive control, and no argv ever
contains ``sudo``.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import shutil
import sqlite3
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.deploy.vikunja_release import core, dbsafety

_ROOT = Path(__file__).resolve().parents[2]
_SRC = _ROOT / "scripts" / "vikunja" / "rollback_release.py"
_spec = importlib.util.spec_from_file_location("rollback_release", _SRC)
rb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rb)

RELEASE = json.loads((_ROOT / "services" / "vikunja" / "release.json").read_text())
RELEASE_ID = RELEASE["image"]["config_digest"]
ROLLBACK_ID = RELEASE["rollback"]["image_id"]
RELEASE_TAG = RELEASE["tags"]["release"]
ROLLBACK_REF = RELEASE["rollback"]["ref"]
ACTIVE = RELEASE["tags"]["active"]
COMPOSE = RELEASE["service"]["compose_file"]
VERSION = RELEASE["release_version"]
PRE = "v2.4.0"
NOW = datetime(2026, 10, 30, 12, 0, 0, tzinfo=timezone.utc)
LATER = datetime(2026, 10, 30, 13, 0, 0, tzinfo=timezone.utc)
SECRET = "password=hunter2"
TITLE = "Buy anniversary gift for Margot"
USER_NAME = "alice.wonderland"

READ_ONLY_PREFIXES = (
    ("docker", "ps"), ("docker", "image", "inspect"), ("docker", "container", "inspect"), ("curl",),
)


@pytest.fixture(autouse=True)
def _restore_umask():
    previous = os.umask(0o022)
    os.umask(previous)
    yield
    os.umask(previous)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeDocker:
    """A stateful fake of the docker CLI and the curl probe."""

    def __init__(self) -> None:
        self.tags = {RELEASE_TAG: RELEASE_ID, ROLLBACK_REF: ROLLBACK_ID, ACTIVE: RELEASE_ID}
        self.images = {RELEASE_ID, ROLLBACK_ID}
        self.container: str | None = RELEASE_ID
        self.versions = {RELEASE_ID: VERSION, ROLLBACK_ID: PRE}
        self.calls: list[list[str]] = []

    def resolve(self, ref: str) -> str | None:
        return self.tags.get(ref) or (ref if ref in self.images else None)

    def _cp(self, argv, rc=0, out="", err=""):
        return subprocess.CompletedProcess(argv, rc, out, err)

    def __call__(self, argv, **kwargs):
        argv = list(argv)
        assert "timeout" in kwargs and kwargs["timeout"] > 0
        self.calls.append(argv)
        if argv[0] == "curl":
            if self.container is None:
                return self._cp(argv, 7, "", f"curl: (7) refused {SECRET}\n")
            body = json.dumps({"version": self.versions[self.container], "motd": TITLE})
            return self._cp(argv, 0, f"{body}\n200")
        if argv == ["docker", "ps", "-a", "--filter", "name=^vikunja$", "-q"]:
            return self._cp(argv, 0, "0123456789ab\n" if self.container else "")
        if argv[:5] == ["docker", "image", "inspect", "--format", dbsafety.UNTAG_INSPECT_FORMAT]:
            found = self.resolve(argv[5])
            if found is None:
                return self._cp(argv, 1, "", f"Error: No such image: {argv[5]}\n")
            names = " ".join(sorted(t for t, i in self.tags.items() if i == found))
            return self._cp(argv, 0, f"{found} {names}\n")
        if argv[:5] == ["docker", "image", "inspect", "--format", "{{.Id}}"]:
            found = self.resolve(argv[5])
            if found is None:
                return self._cp(argv, 1, "", f"Error: No such image: {argv[5]}\n")
            return self._cp(argv, 0, found + "\n")
        if argv == ["docker", "container", "inspect", "--format", "{{.Image}} {{.Config.Image}}", "vikunja"]:
            if self.container is None:
                return self._cp(argv, 1, "", "Error: No such container: vikunja\n")
            return self._cp(argv, 0, f"{self.container} {ACTIVE}\n")
        if argv == ["docker", "compose", "-f", COMPOSE, "down"]:
            self.container = None
            return self._cp(argv, 0, "", f"Container vikunja Removed {SECRET}\n")
        if argv == ["docker", "compose", "-f", COMPOSE, "up", "-d"]:
            if ACTIVE not in self.tags:
                return self._cp(argv, 1, "", "Error: No such image: office2.local/vikunja:active\n")
            self.container = self.tags[ACTIVE]
            return self._cp(argv, 0)
        if argv == ["docker", "image", "rm", ACTIVE]:
            self.tags.pop(ACTIVE, None)
            return self._cp(argv, 0, f"Untagged: {ACTIVE}\n")
        if argv[:2] == ["docker", "tag"] and len(argv) == 4:
            src = self.resolve(argv[2])
            if src is None:
                return self._cp(argv, 1, "", "Error: No such image\n")
            self.tags[argv[3]] = src
            return self._cp(argv, 0)
        return self._cp(argv, 1, "", "unexpected call\n")

    def mutating(self) -> list[list[str]]:
        return [c for c in self.calls if not any(tuple(c[:len(p)]) == p for p in READ_ONLY_PREFIXES)]

    def index(self, prefix: list[str]) -> int:
        for i, call in enumerate(self.calls):
            if call[:len(prefix)] == prefix:
                return i
        return -1


SEEDED_LOG = (f"2026-10-30T12:00:01Z ERROR task '{TITLE}' owner {USER_NAME} {SECRET}\n"
              "2026-10-30T12:00:02Z INFO Ran all migrations successfully.\n")


class Spawn:
    """``Popen`` stand-in: records the docker argv, runs a local child."""

    def __init__(self) -> None:
        self.argvs: list[list[str]] = []

    def __call__(self, argv, **kwargs):
        self.argvs.append(list(argv))
        code = f"import sys\nsys.stdout.write({SEEDED_LOG!r})\n"
        return subprocess.Popen([sys.executable, "-c", code], **kwargs)


# ---------------------------------------------------------------------------
# Fixture: a failed activation on office2, in tmp_path
# ---------------------------------------------------------------------------


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _v24(conn: sqlite3.Connection, rows: int = 10) -> None:
    conn.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY, title TEXT, updated DATETIME, "
                 "repeat_after INTEGER, repeat_mode INTEGER NOT NULL DEFAULT 0)")
    conn.executemany("INSERT INTO tasks VALUES (?, ?, ?, ?, ?)",
                     [(i, f"{TITLE} #{i}", "2026-10-29 10:00:00", 0, 0) for i in range(1, rows + 1)])
    conn.execute("CREATE TABLE task_comments (id INTEGER PRIMARY KEY, task_id INTEGER, comment TEXT)")
    conn.executemany("INSERT INTO task_comments VALUES (?, ?, ?)", [(1, 1, f"{SECRET}"), (2, 2, TITLE)])
    conn.execute("CREATE TABLE labels (id INTEGER PRIMARY KEY, title TEXT)")
    conn.executemany("INSERT INTO labels VALUES (?, ?)", [(1, "home"), (2, "work")])
    conn.execute("CREATE TABLE label_tasks (task_id INTEGER, label_id INTEGER)")  # no id column
    conn.executemany("INSERT INTO label_tasks VALUES (?, ?)", [(1, 1), (2, 2)])
    conn.execute("CREATE TABLE migration (id TEXT, description TEXT)")
    conn.execute("INSERT INTO migration VALUES ('20190324205606', 'old')")


def _migrate(conn: sqlite3.Connection) -> None:
    """The release's migrations alone: tasks rebuilt with ``repeats`` (the
    legacy columns rewritten), the backup table, and bookkeeping rows.
    None of this is a post-cutover write."""
    conn.execute("ALTER TABLE tasks ADD COLUMN repeats TEXT")
    conn.execute("CREATE TABLE task_repeat_legacy_backup (id INTEGER PRIMARY KEY, repeat_after INTEGER, "
                 "repeat_mode INTEGER NOT NULL DEFAULT 0)")
    conn.execute("INSERT INTO task_repeat_legacy_backup SELECT id, repeat_after, repeat_mode FROM tasks")
    conn.execute("UPDATE tasks SET repeats = '', repeat_after = NULL, repeat_mode = 0")
    conn.execute("INSERT INTO migration VALUES ('20261022220000', 'rrule')")


def _migrate_and_write(conn: sqlite3.Connection) -> None:
    """The migrations plus post-cutover writes to tasks: 2 new, 3 modified,
    1 deleted (6 in all)."""
    _migrate(conn)
    conn.executemany("INSERT INTO tasks (id, title, updated, repeat_after, repeat_mode) VALUES (?, ?, ?, 0, 0)",
                     [(11, TITLE, "2026-10-30 12:30:00"), (12, TITLE, "2026-10-30 12:31:00")])
    conn.execute("UPDATE tasks SET updated = '2026-10-30 12:40:00' WHERE id IN (2, 3, 4)")
    conn.execute("DELETE FROM tasks WHERE id = 5")


class Scenario:
    def __init__(self, tmp: Path, *, marker_outcome: str | None = "failed", pre_version: str | None = PRE,
                 writes=_migrate_and_write):
        self.tmp = tmp
        tmp.mkdir(parents=True, exist_ok=True)
        self.data = tmp / "data"
        self.data.mkdir()
        db = self.data / dbsafety.DB_NAME
        conn = sqlite3.connect(db, isolation_level=None)
        _v24(conn)
        conn.close()
        rec = dbsafety.snapshot(self.data, tmp / "snapshots", lambda: NOW, pre_version=pre_version,
                                running_image_id=ROLLBACK_ID)
        self.snapshot = Path(rec["snapshot_dir"])
        self.snapshot_sha = rec["db_sha256"]
        # The release runs: it migrates and takes writes that sit in the WAL.
        writer = tmp / "writer"
        writer.mkdir()
        shutil.copyfile(db, writer / dbsafety.DB_NAME)
        conn = sqlite3.connect(writer / dbsafety.DB_NAME, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA wal_autocheckpoint=0")
        writes(conn)
        for name in (dbsafety.DB_NAME, dbsafety.WAL_NAME, dbsafety.SHM_NAME):
            shutil.copyfile(writer / name, self.data / name)
        conn.close()
        shutil.rmtree(writer)
        # Roots as on office2: activation exists (ACTIVATE made it), failures does not.
        self.release_path = tmp / "release.json"
        release = json.loads(json.dumps(RELEASE))
        release["service"]["data_dir"] = str(self.data)
        release["roots"]["snapshots"] = str(tmp / "snapshots")
        release["roots"]["activation"] = str(tmp / "activation")
        release["roots"]["private_logs"] = str(tmp / "failures")
        self.release_path.write_text(json.dumps(release))
        (tmp / "activation").mkdir(mode=0o700)
        self.marker = tmp / "activation" / f"{VERSION}.json"
        if marker_outcome is not None:
            marker = {"phase": "started_new", "outcome": marker_outcome, "started_at": "2026-10-30T12:00:00Z",
                      "snapshot_dir": str(self.snapshot), "snapshot_sha": self.snapshot_sha}
            if marker_outcome == "failed":
                marker["failed_phase"] = "verified"
            if marker_outcome == "success":
                marker["phase"] = "verified"
            core.marker_create(self.marker, marker)
        self.lock = tmp / "locks" / "checkout.lock"
        self.repo_root = _ROOT
        self.stream = None
        self.docker = FakeDocker()
        self.spawn = Spawn()
        self.out = io.StringIO()
        self.err = io.StringIO()

    def run(self, *args: str, when: datetime = LATER) -> int:
        self.out, self.err = (self.stream or io.StringIO()), io.StringIO()
        clock = [0.0]

        def sleep(s: float) -> None:
            clock[0] += s

        rc = rb.main(["--snapshot", str(self.snapshot), *args], runner=self.docker, popen=self.spawn,
                     monotonic=lambda: clock[0], utcnow=lambda: when, sleep=sleep,
                     release_path=self.release_path, repo_root=self.repo_root, stdout=self.out, stderr=self.err,
                     lock_path=self.lock, lock_timeout_s=0.2)
        return rc

    def restore(self) -> None:
        """Kent's restore command, simulated: install the snapshot DB, drop sidecars."""
        target = self.data / dbsafety.DB_NAME
        shutil.copyfile(self.snapshot / dbsafety.DB_NAME, target)
        target.chmod(0o644)
        for name in (dbsafety.WAL_NAME, dbsafety.SHM_NAME):
            (self.data / name).unlink(missing_ok=True)

    @property
    def text(self) -> str:
        return self.out.getvalue() + self.err.getvalue()

    def code(self) -> str | None:
        for line in self.out.getvalue().splitlines():
            if line.startswith("FAILED "):
                return dict(p.split("=", 1) for p in line.split()[1:])["code"]
        return None

    def assert_no_sudo(self) -> None:
        for argv in self.docker.calls + self.spawn.argvs:
            assert "sudo" not in argv and not any("sudo" in a for a in argv), argv

    def assert_private(self) -> None:
        for leak in (SECRET, TITLE, USER_NAME):
            assert leak not in self.text


def _tree(root: Path) -> dict[str, object]:
    out: dict[str, object] = {}
    for p in sorted(root.rglob("*")):
        rel = str(p.relative_to(root))
        out[rel] = (stat.S_IMODE(p.lstat().st_mode), _sha(p) if p.is_file() and not p.is_symlink() else None)
    return out


def _prepared(tmp_path: Path, **kw) -> Scenario:
    sc = Scenario(tmp_path, **kw)
    assert sc.run("--prepare") == 0, sc.text
    return sc


# ---------------------------------------------------------------------------
# Entrypoint shape
# ---------------------------------------------------------------------------


def test_helper_is_executable():
    out = subprocess.run(["git", "ls-files", "-s", str(_SRC.relative_to(_ROOT))], cwd=_ROOT,
                         capture_output=True, text=True, check=True).stdout
    if out:
        assert out.startswith("100755"), out
    assert os.stat(_SRC).st_mode & 0o111 == 0o111


@pytest.mark.parametrize("args", [
    [], ["--prepare"], ["--snapshot", "/x"], ["--snapshot", "rel", "--dry-run"],
    ["--recover-pre-snapshot", "--snapshot", "/x"], ["--dry-run", "--recover-pre-snapshot"],
    ["--recover-pre-snapshot", "--ack-post-cutover-writes", "1"],
    ["--snapshot", "/x", "--finish"], ["--snapshot", "/x", "--prepare", "--ack-post-cutover-writes", "1"],
    ["--snapshot", "/x", "--finish", "--ack-post-cutover-writes", "-1"],
    ["--snapshot", "/x", "--dry-run", "--prepare"], ["--snapshot", "/x", "--apply"],
], ids=lambda a: " ".join(a) or "empty")
def test_usage_errors_exit_2_with_no_calls(tmp_path, args):
    sc = Scenario(tmp_path)
    rc = rb.main(args, runner=sc.docker, popen=sc.spawn, release_path=sc.release_path, repo_root=_ROOT,
                 stdout=sc.out, stderr=sc.err)
    assert rc == 2
    assert sc.err.getvalue() == rb.USAGE and sc.out.getvalue() == ""
    assert sc.docker.calls == [] and sc.spawn.argvs == []
    # Control: a well-formed call on the same fixture.
    assert sc.run("--dry-run") == 0


def test_main_sets_a_private_umask(tmp_path):
    sc = Scenario(tmp_path)
    os.umask(0o022)
    assert sc.run("--dry-run") == 0
    assert os.umask(0o022) == 0o077


# ---------------------------------------------------------------------------
# --dry-run: state only
# ---------------------------------------------------------------------------


def test_dry_run_reports_state_with_no_mutation(tmp_path):
    sc = Scenario(tmp_path)
    before = _tree(tmp_path)
    assert sc.run("--dry-run") == 0, sc.text
    assert sc.docker.mutating() == [] and sc.spawn.argvs == []
    assert _tree(tmp_path) == before
    line = sc.out.getvalue().splitlines()[0]
    assert line.startswith("ROLLBACK_STATE ")
    fields = dict(p.split("=", 1) for p in line.split()[1:])
    assert fields["marker_outcome"] == "failed" and fields["prepared"] == "0"
    assert fields["container_image"] == RELEASE_ID and fields["active"] == RELEASE_ID
    assert fields["sidecars"] == "2" and fields["data_matches_snapshot"] == "0"
    assert fields["deployer_lock_free"] == "1"
    assert not sc.lock.exists()  # probed, never created
    assert fields["snapshot_sha"] == sc.snapshot_sha and fields["pre_version"] == PRE
    sc.assert_no_sudo()
    sc.assert_private()
    # Control: after prepare and restore, the same dry run reports the change.
    assert sc.run("--prepare") == 0
    sc.restore()
    before = _tree(tmp_path)
    sc.docker.calls.clear()
    assert sc.run("--dry-run") == 0
    assert sc.docker.mutating() == [] and _tree(tmp_path) == before
    fields = dict(p.split("=", 1) for p in sc.out.getvalue().splitlines()[0].split()[1:])
    assert fields["prepared"] == "1" and fields["post_cutover_writes"] == "6"
    assert fields["container_image"] == "-" and fields["active"] == "-"
    assert fields["sidecars"] == "0" and fields["data_matches_snapshot"] == "1"


# ---------------------------------------------------------------------------
# --prepare (T026, T028)
# ---------------------------------------------------------------------------


def test_prepare_captures_stops_untags_copies_counts_and_prints_the_restore(tmp_path):
    sc = Scenario(tmp_path)
    data_hashes = {n: _sha(sc.data / n) for n in (dbsafety.DB_NAME, dbsafety.WAL_NAME, dbsafety.SHM_NAME)}
    assert sc.run("--prepare") == 0, sc.text
    # Order: logs before the stop, the stop before the untag.
    assert sc.spawn.argvs == [["docker", "logs", "--timestamps", "--tail", "20000", "vikunja"]]
    down = sc.docker.index(["docker", "compose", "-f", COMPOSE, "down"])
    untag = sc.docker.index(["docker", "image", "rm", ACTIVE])
    assert 0 <= down < untag
    assert sc.docker.container is None
    assert ACTIVE not in sc.docker.tags
    assert sc.docker.tags[RELEASE_TAG] == RELEASE_ID and sc.docker.tags[ROLLBACK_REF] == ROLLBACK_ID
    assert not any(c[:2] == ["docker", "tag"] for c in sc.docker.calls)
    # The failed DB files, verbatim and read-only, in a private failures folder.
    failures = tmp_path / "failures"
    assert stat.S_IMODE(failures.stat().st_mode) == 0o700
    (run_dir,) = list(failures.iterdir())
    assert run_dir.name == "20261030T130000Z-rollback"
    assert stat.S_IMODE(run_dir.stat().st_mode) == 0o700
    for name, sha in data_hashes.items():
        assert _sha(run_dir / name) == sha
        assert stat.S_IMODE((run_dir / name).stat().st_mode) == 0o400
    (log,) = list(run_dir.glob("*.log"))
    assert SECRET in log.read_text()  # kept privately
    # The live data folder is untouched by the helper.
    assert {n: _sha(sc.data / n) for n in data_hashes} == data_hashes
    # Aggregate post-cutover writes, recorded for --finish.
    record = json.loads((sc.snapshot / rb.PREPARE_RECORD).read_text())
    assert record["post_cutover_writes"] == 6
    assert record["tables"] == {"tasks": {"added": 2, "removed": 1, "changed": 3}}
    out = sc.out.getvalue().splitlines()
    assert any(l.startswith("ROLLBACK_POST_CUTOVER_WRITES count=6 tables=1") for l in out)
    assert "post-cutover writes: table=tasks added=2 removed=1 changed=3" in out
    # Kent's exact restore command, verbatim from the WP06 prompt.
    restore = (f"sudo install -o kgale -g root -m 644 {sc.snapshot}/vikunja.db {sc.data}/vikunja.db "
               f"&& sudo rm -f {sc.data}/vikunja.db-wal {sc.data}/vikunja.db-shm")
    assert restore in out
    assert rb._TEMPLATES["restore_via"] in out
    sc.assert_no_sudo()
    sc.assert_private()


def test_prepare_counts_none_when_nothing_was_written(tmp_path):
    """Control for the count: a failed activation that wrote nothing."""
    sc = Scenario(tmp_path)
    for name in (dbsafety.WAL_NAME, dbsafety.SHM_NAME):
        (sc.data / name).unlink()
    shutil.copyfile(sc.snapshot / dbsafety.DB_NAME, sc.data / dbsafety.DB_NAME)
    assert sc.run("--prepare") == 0, sc.text
    assert json.loads((sc.snapshot / rb.PREPARE_RECORD).read_text())["post_cutover_writes"] == 0


def _no_marker(sc):
    sc.marker.unlink()


def _rolled_back(sc):
    data = core.marker_read(sc.marker)
    core.marker_update(sc.marker, {**data, "outcome": "rolled_back"})


def _other_snapshot(sc):
    data = core.marker_read(sc.marker)
    core.marker_update(sc.marker, {**data, "snapshot_dir": str(sc.tmp / "snapshots" / "20200101T000000Z")})


def _bad_snapshot_db(sc):
    db = sc.snapshot / dbsafety.DB_NAME
    db.chmod(0o600)
    with open(db, "ab") as fh:
        fh.write(b"x")


def _unknown_active(sc):
    sc.docker.images.add("sha256:" + "ab" * 32)
    sc.docker.tags[ACTIVE] = "sha256:" + "ab" * 32


def _broken_marker(sc):
    sc.marker.write_text("{not json")


@pytest.mark.parametrize("break_it,code,docker_calls", [
    (_no_marker, "ROLLBACK_MARKER_MISSING", False),
    (_rolled_back, "ROLLBACK_ALREADY_ROLLED_BACK", False),
    (_other_snapshot, "ROLLBACK_SNAPSHOT_NOT_MARKER", False),
    (_broken_marker, "MARKER_UNREADABLE", False),
    (_bad_snapshot_db, "ROLLBACK_SNAPSHOT_SHA_MISMATCH", False),
    (_unknown_active, "ACTIVE_TAG_UNEXPECTED", True),
], ids=["no-marker", "rolled-back", "other-snapshot", "bad-marker", "snapshot-sha", "unknown-active"])
def test_prepare_refusals(tmp_path, break_it, code, docker_calls):
    broken = Scenario(tmp_path / "broken")
    break_it(broken)
    assert broken.run("--prepare") == 1
    assert broken.code() == code
    assert not any(c[:3] == ["docker", "image", "rm"] for c in broken.docker.calls)
    if not docker_calls:
        assert broken.docker.calls == [] and broken.spawn.argvs == []
    assert not (broken.snapshot / rb.PREPARE_RECORD).exists()
    broken.assert_private()
    # Positive control: the same fixture, unbroken.
    clean = Scenario(tmp_path / "clean")
    assert clean.run("--prepare") == 0, clean.text


def test_prepare_twice_is_refused(tmp_path):
    sc = _prepared(tmp_path)
    sc.docker.calls.clear()
    assert sc.run("--prepare") == 1
    assert sc.code() == "ROLLBACK_ALREADY_PREPARED"
    assert sc.docker.calls == []


def test_prepare_states_a_rollback_of_a_verified_activation(tmp_path):
    sc = _prepared(tmp_path / "success", marker_outcome="success")
    assert any(l.startswith("ROLLBACK_OF_VERIFIED_ACTIVATION ") for l in sc.out.getvalue().splitlines())
    # Control: a failed activation is not announced as verified.
    failed = _prepared(tmp_path / "failed", marker_outcome="failed")
    assert "ROLLBACK_OF_VERIFIED_ACTIVATION" not in failed.out.getvalue()


def test_prepare_with_a_failed_log_capture_still_stops(tmp_path):
    sc = Scenario(tmp_path)

    def broken_popen(argv, **kw):
        sc.spawn.argvs.append(list(argv))
        raise FileNotFoundError("docker")

    sc.spawn = broken_popen  # type: ignore[assignment]
    sc.spawn.argvs = []  # type: ignore[attr-defined]
    assert sc.run("--prepare") == 0, sc.text
    assert "ROLLBACK_LOGS_CAPTURED captured=0" in sc.out.getvalue()
    assert sc.docker.container is None and ACTIVE not in sc.docker.tags


# ---------------------------------------------------------------------------
# --finish (T026, T027, T028)
# ---------------------------------------------------------------------------


def test_finish_after_restore_rolls_back(tmp_path):
    sc = _prepared(tmp_path)
    sc.restore()
    sc.docker.calls.clear()
    assert sc.run("--finish", "--ack-post-cutover-writes", "6") == 0, sc.text
    tag = sc.docker.index(["docker", "tag", ROLLBACK_ID, ACTIVE])
    up = sc.docker.index(["docker", "compose", "-f", COMPOSE, "up", "-d"])
    curl = sc.docker.index(["curl"])
    assert 0 <= tag < up < curl
    assert sc.docker.container == ROLLBACK_ID and sc.docker.tags[ACTIVE] == ROLLBACK_ID
    marker = core.marker_read(sc.marker)
    assert marker["outcome"] == "rolled_back" and marker["rollback_snapshot"] == str(sc.snapshot)
    assert marker["failed_phase"] == "verified"  # history kept
    out = sc.out.getvalue().splitlines()
    assert f"ROLLBACK_READY version={PRE}" in out
    assert any(l.startswith("ROLLBACK_FINISHED ") and "outcome=rolled_back" in l for l in out)
    # T029: the runbook's manual reset commands, read from the repo, in order.
    assert any(l.startswith("ROLLBACK_FOLLOWUP_REBASELINE ") and "commands=2" in l for l in out)
    assert ("ssh office2-claude 'cp -a /data/services/security-monitor/baselines "
            "/tmp/baselines-$(date +%s)'") in out
    assert ("ssh office2-claude 'rm /data/services/security-monitor/baselines/* && sg docker -c "
            "/data/services/security-monitor/scripts/audit.sh'") in out
    assert "ROLLBACK_FOLLOWUP_QUEUE manifest_code=ACTIVATE_ROLLED_BACK_REMOVE_QUEUED_MANIFEST" in out
    assert any(str(_ROOT / rb.QUEUED_MANIFEST) in l and l.startswith("queue cancel (R-17)") for l in out)
    sc.assert_no_sudo()
    sc.assert_private()


def test_finish_refuses_a_wrong_ack_and_accepts_the_right_one(tmp_path):
    sc = _prepared(tmp_path)
    sc.restore()
    for wrong in ("0", "5", "7"):
        sc.docker.calls.clear()
        assert sc.run("--finish", "--ack-post-cutover-writes", wrong) == 1
        assert sc.code() == "ROLLBACK_ACK_MISMATCH"
        assert sc.docker.calls == []
    assert sc.run("--finish", "--ack-post-cutover-writes", "6") == 0, sc.text


def test_finish_without_prepare_is_refused(tmp_path):
    sc = Scenario(tmp_path)
    assert sc.run("--finish", "--ack-post-cutover-writes", "6") == 1
    assert sc.code() == "ROLLBACK_NOT_PREPARED"
    assert sc.docker.calls == []
    assert sc.run("--prepare") == 0
    sc.restore()
    assert sc.run("--finish", "--ack-post-cutover-writes", "6") == 0, sc.text


def _container_back(sc):
    sc.docker.container = RELEASE_ID


def _lock_released(sc):
    sc.docker.tags[ACTIVE] = RELEASE_ID


def _sidecar(sc):
    (sc.data / dbsafety.WAL_NAME).write_bytes(b"")


def _not_restored(sc):
    shutil.copyfile(sc.tmp / "failures" / "20261030T130000Z-rollback" / dbsafety.DB_NAME,
                    sc.data / dbsafety.DB_NAME)


def _tampered(sc):
    conn = sqlite3.connect(sc.data / dbsafety.DB_NAME, isolation_level=None)
    conn.execute("UPDATE tasks SET title = 'x' WHERE id = 1")
    conn.close()


@pytest.mark.parametrize("break_it,code", [
    (_container_back, "GUARD_CONTAINER_PRESENT"),
    (_lock_released, "GUARD_LOCK_NOT_HELD"),
    (_sidecar, "GUARD_SIDECAR_PRESENT"),
    (_not_restored, "GUARD_SHA_MISMATCH"),
    (_tampered, "GUARD_SHA_MISMATCH"),
], ids=["container", "lock", "sidecar", "not-restored", "tampered"])
def test_finish_guard_refusal_means_no_tag_and_no_up(tmp_path, break_it, code):
    """T027 / FR-014: on any guard code the rollback image is never tagged
    to active and nothing is started."""
    sc = _prepared(tmp_path)
    sc.restore()
    break_it(sc)
    tags_before = dict(sc.docker.tags)
    container_before = sc.docker.container
    sc.docker.calls.clear()
    assert sc.run("--finish", "--ack-post-cutover-writes", "6") == 1
    assert sc.code() == code
    assert not any(c[:2] == ["docker", "tag"] for c in sc.docker.calls)
    assert not any(c[-2:] == ["up", "-d"] for c in sc.docker.calls)
    assert sc.docker.tags == tags_before and sc.docker.container == container_before
    assert sc.docker.tags.get(ACTIVE) != ROLLBACK_ID
    assert core.marker_read(sc.marker)["outcome"] == "failed"
    sc.assert_no_sudo()
    sc.assert_private()
    # Positive control: the same prepared fixture, cleanly restored.
    if code == "GUARD_CONTAINER_PRESENT":
        sc.docker.container = None
    if code == "GUARD_LOCK_NOT_HELD":
        sc.docker.tags.pop(ACTIVE)
    sc.restore()
    assert sc.run("--finish", "--ack-post-cutover-writes", "6") == 0, sc.text
    assert sc.docker.tags[ACTIVE] == ROLLBACK_ID


def test_finish_guard_inspection_error_refuses(tmp_path):
    sc = _prepared(tmp_path)
    sc.restore()
    real = sc.docker

    def failing(argv, **kw):
        if argv[:2] == ["docker", "ps"]:
            real.calls.append(list(argv))
            return subprocess.CompletedProcess(argv, 1, "", f"daemon {SECRET}\n")
        return real(argv, **kw)

    sc.docker = failing  # type: ignore[assignment]
    assert sc.run("--finish", "--ack-post-cutover-writes", "6") == 1
    assert sc.code() == "GUARD_INSPECTION_ERROR"
    assert not any(c[:2] == ["docker", "tag"] or c[-2:] == ["up", "-d"] for c in real.calls)
    assert SECRET not in sc.text
    sc.docker = real
    assert sc.run("--finish", "--ack-post-cutover-writes", "6") == 0, sc.text


def _touch_db_like_a_running_service(sc: Scenario) -> None:
    conn = sqlite3.connect(sc.data / dbsafety.DB_NAME, isolation_level=None)
    conn.execute("UPDATE tasks SET updated = '2026-10-30 14:00:00' WHERE id = 1")
    conn.close()


@pytest.mark.parametrize("touched", [True, False], ids=["db-touched", "db-untouched"])
def test_readiness_failure_after_up_cleans_up_and_retry_follows_the_guard(tmp_path, touched):
    """R-14: a failure after the tag captures logs, stops the service and
    takes the lock again, leaving the marker unchanged. Nothing is cleared
    by hand here: the retry runs on the state the helper left."""
    sc = _prepared(tmp_path)
    sc.restore()
    sc.docker.versions[ROLLBACK_ID] = "v2.5.0"
    assert sc.run("--finish", "--ack-post-cutover-writes", "6") == 1
    assert sc.code() == "READY_WRONG_VERSION"
    # End state: no container, the lock tag gone, images kept, marker unchanged.
    assert sc.docker.container is None
    assert ACTIVE not in sc.docker.tags
    assert sc.docker.tags[ROLLBACK_REF] == ROLLBACK_ID and sc.docker.tags[RELEASE_TAG] == RELEASE_ID
    assert core.marker_read(sc.marker)["outcome"] == "failed"
    assert "ROLLBACK_CLEANUP container=0 active=- down_code=- untag_code=-" in sc.out.getvalue()
    logs = sorted((tmp_path / "failures" / "20261030T130000Z-rollback").glob("*.log"))
    assert len(logs) == 2  # prepare's capture plus the failed start's
    sc.assert_private()
    # The 2.4.0 container ran on the restored DB; it may have written it.
    if touched:
        _touch_db_like_a_running_service(sc)
    sc.docker.versions[ROLLBACK_ID] = PRE
    sc.docker.calls.clear()
    rc = sc.run("--finish", "--ack-post-cutover-writes", "6")
    if touched:
        assert rc == 1 and sc.code() == "GUARD_SHA_MISMATCH"
        assert not any(c[:2] == ["docker", "tag"] or c[-2:] == ["up", "-d"] for c in sc.docker.calls)
        # Kent re-runs his restore; then the same retry passes.
        sc.restore()
        assert sc.run("--finish", "--ack-post-cutover-writes", "6") == 0, sc.text
    else:
        assert rc == 0, sc.text
    assert core.marker_read(sc.marker)["outcome"] == "rolled_back"
    assert sc.docker.tags[ACTIVE] == ROLLBACK_ID


def test_a_failed_up_also_cleans_up(tmp_path):
    sc = _prepared(tmp_path)
    sc.restore()
    real = sc.docker

    def up_fails(argv, **kw):
        if argv[-2:] == ["up", "-d"]:
            real.calls.append(list(argv))
            return subprocess.CompletedProcess(argv, 1, "", f"boom {SECRET}\n")
        return real(argv, **kw)

    sc.docker = up_fails  # type: ignore[assignment]
    assert sc.run("--finish", "--ack-post-cutover-writes", "6") == 1
    assert sc.code() == "COMPOSE_UP_D_FAILED"
    assert ACTIVE not in real.tags and real.container is None
    assert SECRET not in sc.text
    sc.docker = real
    assert sc.run("--finish", "--ack-post-cutover-writes", "6") == 0, sc.text


def test_finish_without_pre_version_requires_2_4(tmp_path):
    """U1 fallback: no recorded pre_version -> any 2.4.x passes; 2.5 does not."""
    sc = _prepared(tmp_path, pre_version=None)
    sc.restore()
    sc.docker.versions[ROLLBACK_ID] = "v2.5.0"
    assert sc.run("--finish", "--ack-post-cutover-writes", "6") == 1
    assert sc.code() == "READY_WRONG_VERSION"
    assert sc.docker.container is None and ACTIVE not in sc.docker.tags  # cleaned up by the helper
    sc.docker.versions[ROLLBACK_ID] = "v2.4.3"
    assert sc.run("--finish", "--ack-post-cutover-writes", "6") == 0, sc.text
    assert "ROLLBACK_READY version=v2.4.3" in sc.out.getvalue()


def test_finish_of_a_verified_activation_is_stated(tmp_path):
    sc = _prepared(tmp_path, marker_outcome="success")
    sc.restore()
    assert sc.run("--finish", "--ack-post-cutover-writes", "6") == 0, sc.text
    assert sc.out.getvalue().startswith("ROLLBACK_OF_VERIFIED_ACTIVATION ")
    assert core.marker_read(sc.marker)["outcome"] == "rolled_back"


def test_finish_replay_after_rollback_is_refused(tmp_path):
    sc = _prepared(tmp_path)
    sc.restore()
    assert sc.run("--finish", "--ack-post-cutover-writes", "6") == 0
    sc.docker.calls.clear()
    assert sc.run("--finish", "--ack-post-cutover-writes", "6") == 1
    assert sc.code() == "ROLLBACK_ALREADY_ROLLED_BACK"
    assert sc.docker.calls == []


def test_missing_rollback_image_refuses_before_tagging(tmp_path):
    sc = _prepared(tmp_path)
    sc.restore()
    sc.docker.tags.pop(ROLLBACK_REF)
    assert sc.run("--finish", "--ack-post-cutover-writes", "6") == 1
    assert sc.code() == "ROLLBACK_IMAGE_MISSING"
    assert not any(c[:2] == ["docker", "tag"] for c in sc.docker.calls)
    sc.docker.tags[ROLLBACK_REF] = ROLLBACK_ID
    assert sc.run("--finish", "--ack-post-cutover-writes", "6") == 0, sc.text


# ---------------------------------------------------------------------------
# T029 follow-ups and output allowlist
# ---------------------------------------------------------------------------


def test_rebaseline_commands_print_only_while_the_runbook_confirms_them(tmp_path):
    sc = _prepared(tmp_path / "real")
    sc.restore()
    assert sc.run("--finish", "--ack-post-cutover-writes", "6") == 0
    out = sc.out.getvalue().splitlines()
    assert all(cmd in out for cmd in rb.REBASELINE_COMMANDS)  # the real runbook confirms them
    assert any(l.startswith("ROLLBACK_FOLLOWUP_REBASELINE ") and "commands=2" in l for l in out)


@pytest.mark.parametrize("keep_real", [True, False], ids=["real-plus-secret", "secret-only"])
def test_a_secret_bearing_runbook_line_is_never_printed(tmp_path, keep_real):
    fake_repo = tmp_path / "repo"
    runbook = fake_repo / rb.RUNBOOK
    runbook.parent.mkdir(parents=True)
    body = "## Manual reset procedure\n\n```bash\nssh office2-claude 'echo password=hunter2'\n```\n"
    if keep_real:
        body += "".join(f"\n{cmd}\n" for cmd in rb.REBASELINE_COMMANDS)
    runbook.write_text(body)
    sc = _prepared(tmp_path / "sc")
    sc.restore()
    sc.repo_root = fake_repo
    assert sc.run("--finish", "--ack-post-cutover-writes", "6") == 0, sc.text
    out = sc.out.getvalue().splitlines()
    assert SECRET not in sc.text and "echo" not in sc.text
    if keep_real:
        assert all(cmd in out for cmd in rb.REBASELINE_COMMANDS)
    else:
        assert not any(cmd in out for cmd in rb.REBASELINE_COMMANDS)
        assert f"manual rebaseline: see the Manual reset procedure in {runbook}" in out


def test_every_output_line_is_allowlisted(tmp_path):
    sc = _prepared(tmp_path)
    lines = sc.out.getvalue().splitlines()
    sc.restore()
    assert sc.run("--finish", "--ack-post-cutover-writes", "6") == 0
    lines += sc.out.getvalue().splitlines()
    summaries = core.registered_summaries()
    restore = (f"sudo install -o kgale -g root -m 644 {sc.snapshot}/vikunja.db {sc.data}/vikunja.db "
               f"&& sudo rm -f {sc.data}/vikunja.db-wal {sc.data}/vikunja.db-shm")
    fixed = {restore, rb._TEMPLATES["restore_via"], *rb.REBASELINE_COMMANDS,
             rb._TEMPLATES["queue_cancel"].format(manifest=_ROOT / rb.QUEUED_MANIFEST),
             "post-cutover writes: table=tasks added=2 removed=1 changed=3"}
    for line in lines:
        assert line.split(" ", 1)[0] in summaries or line in fixed, line
        assert "REDACTED" not in line, line
    sc.assert_private()


# ---------------------------------------------------------------------------
# Serialisation with the deployer (INV-1)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("phase", ["prepare", "finish"])
def test_a_held_deployer_lock_refuses_before_any_docker_call(tmp_path, phase):
    from scripts.deploy.lib.deploylock import deploylock

    sc = Scenario(tmp_path)
    if phase == "finish":
        assert sc.run("--prepare") == 0
        sc.restore()
    args = ["--prepare"] if phase == "prepare" else ["--finish", "--ack-post-cutover-writes", "6"]
    sc.docker.calls.clear()
    sc.spawn.argvs.clear()
    marker_before = core.marker_read(sc.marker)
    with deploylock(path=sc.lock, timeout_s=1.0):  # the deployer tick, mid-ACTIVATE
        assert sc.run(*args) == 1
        assert sc.code() == "ROLLBACK_DEPLOYER_BUSY"
        assert sc.docker.calls == [] and sc.spawn.argvs == []
        assert core.marker_read(sc.marker) == marker_before
        assert sc.run("--dry-run") == 0  # the dry run does not take the lock
        assert "deployer_lock_free=0" in sc.out.getvalue()
    # Control: the same fixture once the lock is free.
    assert sc.run("--dry-run") == 0 and "deployer_lock_free=1" in sc.out.getvalue()
    assert sc.run(*args) == 0, sc.text


def test_the_lock_is_held_for_the_whole_phase(tmp_path):
    """Every docker call of --prepare and --finish happens with the lock held."""
    import fcntl

    sc = Scenario(tmp_path)
    real = sc.docker
    unlocked: list[list[str]] = []

    def probing(argv, **kw):
        for path in (sc.lock, sc.marker.parent / rb.ACTIVATION_LOCK_NAME):
            fd = os.open(path, os.O_RDONLY)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                unlocked.append([str(path), *argv])
                fcntl.flock(fd, fcntl.LOCK_UN)
            except BlockingIOError:
                pass
            finally:
                os.close(fd)
        return real(argv, **kw)

    sc.docker = probing  # type: ignore[assignment]
    assert sc.run("--prepare") == 0, sc.text
    sc.restore()
    assert sc.run("--finish", "--ack-post-cutover-writes", "6") == 0, sc.text
    assert real.calls and unlocked == []


# ---------------------------------------------------------------------------
# Post-cutover write count: conservative, every table (T028)
# ---------------------------------------------------------------------------


def _with(*sql: str):
    def writes(conn: sqlite3.Connection) -> None:
        _migrate(conn)
        for stmt in sql:
            conn.execute(stmt)
    return writes


@pytest.mark.parametrize("sql,expected", [
    (("UPDATE tasks SET title = 'renamed' WHERE id = 3",), {"tasks": {"added": 0, "removed": 0, "changed": 1}}),
    (("INSERT INTO task_comments VALUES (3, 1, 'new')",), {"task_comments": {"added": 1, "removed": 0, "changed": 0}}),
    (("DELETE FROM labels WHERE id = 2",), {"labels": {"added": 0, "removed": 1, "changed": 0}}),
    (("INSERT INTO label_tasks VALUES (3, 1)",), {"label_tasks": {"added": 1, "removed": 0, "changed": 0}}),
    (("CREATE TABLE new_table (id INTEGER PRIMARY KEY)", "INSERT INTO new_table VALUES (1)"),
     {"new_table": {"added": 1, "removed": 0, "changed": 0}}),
], ids=["title-same-updated", "new-comment", "deleted-label", "no-id-table", "new-table"])
def test_each_post_cutover_write_is_counted(tmp_path, sql, expected):
    sc = Scenario(tmp_path / "w", writes=_with(*sql))
    assert sc.run("--prepare") == 0, sc.text
    record = json.loads((sc.snapshot / rb.PREPARE_RECORD).read_text())
    assert record["tables"] == expected
    assert record["post_cutover_writes"] == 1
    sc.assert_private()
    # Control: the migration alone (backup table, bookkeeping row, repeat
    # columns rewritten) counts 0 on the same fixture shape.
    clean = Scenario(tmp_path / "c", writes=_migrate)
    assert clean.run("--prepare") == 0, clean.text
    record = json.loads((clean.snapshot / rb.PREPARE_RECORD).read_text())
    assert record["post_cutover_writes"] == 0 and record["tables"] == {}
    assert "ROLLBACK_POST_CUTOVER_WRITES count=0 tables=0" in clean.out.getvalue()


# ---------------------------------------------------------------------------
# ACTIVATE's lifetime lock (parent-crash case)
# ---------------------------------------------------------------------------

_HOLDER = (
    "import fcntl, os, sys, time\n"
    "fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o600)\n"
    "fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)\n"
    "sys.stdout.write('held\\n'); sys.stdout.flush()\n"
    "time.sleep(120)\n"
)


def _hold_activation_lock(sc: Scenario) -> subprocess.Popen:
    """A separate process holding activation.lock: an ACTIVATE whose
    deployer tick died (deploylock free) but which itself lives on."""
    proc = subprocess.Popen([sys.executable, "-c", _HOLDER, str(sc.marker.parent / rb.ACTIVATION_LOCK_NAME)],
                            stdout=subprocess.PIPE, text=True)
    assert proc.stdout.readline() == "held\n"
    return proc


@pytest.mark.parametrize("phase", ["prepare", "finish"])
def test_an_orphaned_activation_holding_its_lock_refuses_rollback(tmp_path, phase):
    from scripts.deploy.lib.deploylock import deploylock

    sc = Scenario(tmp_path)
    if phase == "finish":
        assert sc.run("--prepare") == 0
        sc.restore()
    args = ["--prepare"] if phase == "prepare" else ["--finish", "--ack-post-cutover-writes", "6"]
    holder = _hold_activation_lock(sc)
    try:
        with deploylock(path=sc.lock, timeout_s=0.5):
            pass  # deploylock is free: the tick that ran ACTIVATE is gone
        sc.docker.calls.clear()
        sc.spawn.argvs.clear()
        marker_before = sc.marker.read_bytes()
        assert sc.run(*args) == 1
        assert sc.code() == "ROLLBACK_ACTIVATION_RUNNING"
        assert sc.docker.calls == [] and sc.spawn.argvs == []
        assert sc.marker.read_bytes() == marker_before
        assert sc.run("--dry-run") == 0
        state = sc.out.getvalue()
        assert "activation_lock_free=0" in state and "deployer_lock_free=1" in state
    finally:
        holder.kill()
        holder.wait(timeout=10)
    # Control: the holder died (the OS released its flock); same fixture passes.
    assert sc.run("--dry-run") == 0 and "activation_lock_free=1" in sc.out.getvalue()
    assert sc.run(*args) == 0, sc.text


def test_a_busy_deploylock_refuses_even_with_the_activation_lock_free(tmp_path):
    from scripts.deploy.lib.deploylock import deploylock

    sc = Scenario(tmp_path)
    with deploylock(path=sc.lock, timeout_s=1.0):
        assert rb._probe_lock(sc.marker.parent / rb.ACTIVATION_LOCK_NAME) == 1
        assert sc.run("--prepare") == 1
        assert sc.code() == "ROLLBACK_DEPLOYER_BUSY"
        assert sc.docker.calls == []
    assert sc.run("--prepare") == 0, sc.text


def test_activation_lock_file_is_private_and_not_followed(tmp_path):
    sc = Scenario(tmp_path)
    lock = sc.marker.parent / rb.ACTIVATION_LOCK_NAME
    assert not lock.exists()
    assert sc.run("--dry-run") == 0 and not lock.exists()  # the probe never creates it
    assert sc.run("--prepare") == 0, sc.text
    assert stat.S_IMODE(lock.stat().st_mode) == 0o600
    # A symlink planted in its place is refused, before any docker call.
    sc2 = Scenario(tmp_path / "planted")
    target = tmp_path / "planted-target"
    target.write_text("")
    (sc2.marker.parent / rb.ACTIVATION_LOCK_NAME).symlink_to(target)
    assert sc2.run("--prepare") == 1
    assert sc2.code() == "ACTIVATION_LOCK_UNSAFE"
    assert sc2.docker.calls == []
    (sc2.marker.parent / rb.ACTIVATION_LOCK_NAME).unlink()
    assert sc2.run("--prepare") == 0, sc2.text


def test_activation_lock_name_constant():
    assert rb.ACTIVATION_LOCK_NAME == "activation.lock"



# ---------------------------------------------------------------------------
# --recover-pre-snapshot: ACTIVATE failed before any retag
# ---------------------------------------------------------------------------


class Recover:
    """office2 after an ACTIVATE that failed before the retag: WP04's cleanup
    ran, so the service is down, ``active`` untagged, the marker ``failed``,
    no snapshot, and the live DB unmigrated (unless *wal_migrated*: the
    migration markers sit only in the WAL)."""

    def __init__(self, tmp: Path, *, phase: str = "stopped", failed_phase: str = "snapshotted",
                 outcome: str | None = "failed", wal_migrated: bool = False) -> None:
        self.tmp = tmp
        tmp.mkdir(parents=True, exist_ok=True)
        self.data = tmp / "data"
        self.data.mkdir()
        writer = tmp / "writer"
        writer.mkdir()
        conn = sqlite3.connect(writer / dbsafety.DB_NAME, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        _v24(conn)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.execute("PRAGMA wal_autocheckpoint=0")
        conn.execute("UPDATE tasks SET title = title")  # a live WAL either way
        if wal_migrated:
            _migrate(conn)
        for name in (dbsafety.DB_NAME, dbsafety.WAL_NAME, dbsafety.SHM_NAME):
            shutil.copyfile(writer / name, self.data / name)
        conn.close()
        shutil.rmtree(writer)
        self.release_path = tmp / "release.json"
        release = json.loads(json.dumps(RELEASE))
        release["service"]["data_dir"] = str(self.data)
        release["roots"]["snapshots"] = str(tmp / "snapshots")
        release["roots"]["activation"] = str(tmp / "activation")
        release["roots"]["private_logs"] = str(tmp / "failures")
        self.release_path.write_text(json.dumps(release))
        (tmp / "activation").mkdir(mode=0o700)
        self.marker = tmp / "activation" / f"{VERSION}.json"
        self.write_marker(phase=phase, failed_phase=failed_phase, outcome=outcome)
        self.lock = tmp / "locks" / "checkout.lock"
        self.stream = None
        self.docker = FakeDocker()
        self.docker.container = None
        self.docker.tags.pop(ACTIVE)
        self.spawn = Spawn()
        self.out = io.StringIO()
        self.err = io.StringIO()

    def write_marker(self, *, phase: str, failed_phase: str | None, outcome: str | None) -> None:
        data = {"phase": phase, "outcome": outcome, "started_at": "2026-10-30T12:00:00Z",
                "release_version": VERSION, "config_digest": RELEASE_ID, "rollback_image_id": ROLLBACK_ID,
                "pre_version": PRE, "error": "ACTIVATE_SNAPSHOT_FAILED" if outcome == "failed" else None}
        if failed_phase is not None:
            data["failed_phase"] = failed_phase
        if self.marker.exists():
            core.marker_update(self.marker, data)
        else:
            core.marker_create(self.marker, data)

    def run(self, *args: str) -> int:
        self.out, self.err = (self.stream or io.StringIO()), io.StringIO()
        clock = [0.0]

        def sleep(sec: float) -> None:
            clock[0] += sec

        return rb.main(list(args), runner=self.docker, popen=self.spawn, monotonic=lambda: clock[0],
                       utcnow=lambda: LATER, sleep=sleep, release_path=self.release_path, repo_root=_ROOT,
                       stdout=self.out, stderr=self.err, lock_path=self.lock, lock_timeout_s=0.2)

    code = Scenario.code
    text = Scenario.text
    assert_no_sudo = Scenario.assert_no_sudo
    assert_private = Scenario.assert_private

    def no_tag_no_up(self) -> None:
        assert not any(c[:2] == ["docker", "tag"] for c in self.docker.calls)
        assert not any(c[-2:] == ["up", "-d"] for c in self.docker.calls)


RECOVER = "--recover-pre-snapshot"


def test_rollback_version_is_derived_like_wp04():
    assert rb.rollback_version(RELEASE) == "v2.4.0"
    assert rb.PRE_RETAG_FAILED_PHASES == {"started", "stopped", "snapshotted"}


@pytest.mark.parametrize("phase,failed_phase", [("started", "stopped"), ("stopped", "snapshotted")],
                         ids=["failed-stopping", "failed-snapshotting"])
def test_recover_brings_2_4_back(tmp_path, phase, failed_phase):
    rc = Recover(tmp_path, phase=phase, failed_phase=failed_phase)
    assert rc.run(RECOVER) == 0, rc.text
    calls = rc.docker.calls
    tag = calls.index(["docker", "tag", ROLLBACK_ID, ACTIVE])
    up = calls.index(["docker", "compose", "-f", COMPOSE, "up", "-d"])
    curl = next(i for i, c in enumerate(calls) if c[0] == "curl")
    assert tag < up < curl
    assert rc.docker.container == ROLLBACK_ID and rc.docker.tags[ACTIVE] == ROLLBACK_ID
    marker = core.marker_read(rc.marker)
    assert marker["outcome"] == "rolled_back" and marker["recovered_pre_snapshot"] == 1
    assert marker["failed_phase"] == failed_phase and marker["rolled_back_at"] == "2026-10-30T13:00:00Z"
    out = rc.out.getvalue().splitlines()
    assert "ROLLBACK_READY version=v2.4.0" in out
    assert all(cmd in out for cmd in rb.REBASELINE_COMMANDS)
    assert any(l.startswith("ROLLBACK_FOLLOWUP_QUEUE ") for l in out)
    # The live DB was only copied, privately.
    copy_dir = tmp_path / "failures" / "20261030T130000Z-recover"
    assert stat.S_IMODE(copy_dir.stat().st_mode) == 0o700
    assert _sha(copy_dir / dbsafety.DB_NAME) == _sha(rc.data / dbsafety.DB_NAME)
    rc.assert_no_sudo()
    rc.assert_private()


@pytest.mark.parametrize("marker,code", [
    ({"phase": "snapshotted", "failed_phase": "retagged", "outcome": "failed"}, "RECOVER_MARKER_PAST_RETAG"),
    ({"phase": "retagged", "failed_phase": "started_new", "outcome": "failed"}, "RECOVER_MARKER_PAST_RETAG"),
    ({"phase": "started_new", "failed_phase": "verified", "outcome": "failed"}, "RECOVER_MARKER_PAST_RETAG"),
    ({"phase": "verified", "failed_phase": None, "outcome": "success"}, "RECOVER_MARKER_NOT_FAILED"),
    ({"phase": "stopped", "failed_phase": None, "outcome": None}, "RECOVER_MARKER_NOT_FAILED"),
    ({"phase": "stopped", "failed_phase": "snapshotted", "outcome": "rolled_back"}, "RECOVER_MARKER_NOT_FAILED"),
    ({"phase": "snapshotted", "failed_phase": "snapshotted", "outcome": "failed"}, "RECOVER_MARKER_PAST_RETAG"),
], ids=["retagged", "started-new", "verified", "success", "in-progress", "rolled-back", "phase-snapshotted"])
def test_recover_refuses_a_marker_past_the_retag(tmp_path, marker, code):
    rc = Recover(tmp_path)
    rc.write_marker(**marker)
    before = rc.marker.read_bytes()
    assert rc.run(RECOVER) == 1
    assert rc.code() == code
    assert rc.docker.calls == [] and rc.spawn.argvs == []  # refused before any docker call
    assert rc.marker.read_bytes() == before
    rc.no_tag_no_up()
    # Positive control: the same fixture with a pre-retag failure recovers.
    rc.write_marker(phase="stopped", failed_phase="snapshotted", outcome="failed")
    assert rc.run(RECOVER) == 0, rc.text


def test_recover_refuses_without_a_marker(tmp_path):
    rc = Recover(tmp_path)
    rc.marker.unlink()
    assert rc.run(RECOVER) == 1 and rc.code() == "RECOVER_MARKER_MISSING"
    assert rc.docker.calls == []
    rc.write_marker(phase="stopped", failed_phase="snapshotted", outcome="failed")
    assert rc.run(RECOVER) == 0, rc.text


def _container(rc):
    rc.docker.container = ROLLBACK_ID


def _active_tagged(rc):
    rc.docker.tags[ACTIVE] = RELEASE_ID


def _no_rollback_image(rc):
    rc.docker.tags.pop(ROLLBACK_REF)


@pytest.mark.parametrize("break_it,fix,code", [
    (_container, lambda rc: setattr(rc.docker, "container", None), "RECOVER_CONTAINER_PRESENT"),
    (_active_tagged, lambda rc: rc.docker.tags.pop(ACTIVE), "RECOVER_LOCK_NOT_HELD"),
    (_no_rollback_image, lambda rc: rc.docker.tags.__setitem__(ROLLBACK_REF, ROLLBACK_ID),
     "RECOVER_ROLLBACK_IMAGE_MISSING"),
], ids=["container", "active-tagged", "no-rollback-image"])
def test_recover_refuses_on_docker_state(tmp_path, break_it, fix, code):
    rc = Recover(tmp_path)
    break_it(rc)
    tags, container = dict(rc.docker.tags), rc.docker.container
    assert rc.run(RECOVER) == 1
    assert rc.code() == code
    rc.no_tag_no_up()
    assert rc.docker.tags == tags and rc.docker.container == container
    assert not (tmp_path / "failures").exists()  # refused before the DB copy
    assert core.marker_read(rc.marker)["outcome"] == "failed"
    fix(rc)
    assert rc.run(RECOVER) == 0, rc.text


def test_recover_refuses_a_db_migrated_only_in_the_wal(tmp_path):
    rc = Recover(tmp_path, wal_migrated=True)
    # The main file alone looks unmigrated: the markers live only in the WAL.
    main_only = tmp_path / "main-only"
    main_only.mkdir()
    shutil.copyfile(rc.data / dbsafety.DB_NAME, main_only / dbsafety.DB_NAME)
    assert dbsafety.is_migrated(main_only / dbsafety.DB_NAME) is False
    assert rc.run(RECOVER) == 1
    assert rc.code() == "RECOVER_DB_MIGRATED"
    rc.no_tag_no_up()
    # The private copy took the WAL along, so it shows the migration.
    copy_dir = tmp_path / "failures" / "20261030T130000Z-recover"
    assert sorted(p.name for p in copy_dir.iterdir()) == sorted(
        [dbsafety.DB_NAME, dbsafety.WAL_NAME, dbsafety.SHM_NAME])
    assert dbsafety.is_migrated(copy_dir / dbsafety.DB_NAME) is True
    assert core.marker_read(rc.marker)["outcome"] == "failed"
    # Control: the same fixture without the migrated WAL recovers.
    for name in (dbsafety.WAL_NAME, dbsafety.SHM_NAME):
        (rc.data / name).unlink()
    shutil.rmtree(copy_dir)
    assert rc.run(RECOVER) == 0, rc.text


def test_recover_refuses_an_uninspectable_db(tmp_path):
    rc = Recover(tmp_path)
    saved = {n: (rc.data / n).read_bytes() for n in (dbsafety.DB_NAME, dbsafety.WAL_NAME, dbsafety.SHM_NAME)}
    for n in saved:
        (rc.data / n).unlink()
    (rc.data / dbsafety.DB_NAME).write_bytes(b"not a database" * 200)
    assert rc.run(RECOVER) == 1
    assert rc.code() == "DB_INSPECT_FAILED"
    rc.no_tag_no_up()
    for n, b in saved.items():
        (rc.data / n).write_bytes(b)
    shutil.rmtree(tmp_path / "failures" / "20261030T130000Z-recover")
    assert rc.run(RECOVER) == 0, rc.text


def test_recover_refuses_while_either_lock_is_held(tmp_path):
    from scripts.deploy.lib.deploylock import deploylock

    rc = Recover(tmp_path)
    with deploylock(path=rc.lock, timeout_s=1.0):
        assert rc.run(RECOVER) == 1 and rc.code() == "ROLLBACK_DEPLOYER_BUSY"
        assert rc.docker.calls == [] and rc.spawn.argvs == []
    holder = _hold_activation_lock(rc)
    try:
        assert rc.run(RECOVER) == 1 and rc.code() == "ROLLBACK_ACTIVATION_RUNNING"
        assert rc.docker.calls == [] and rc.spawn.argvs == []
    finally:
        holder.kill()
        holder.wait(timeout=10)
    assert core.marker_read(rc.marker)["outcome"] == "failed"
    assert rc.run(RECOVER) == 0, rc.text


def test_recover_up_failure_cleans_up(tmp_path):
    rc = Recover(tmp_path)
    rc.docker.versions[ROLLBACK_ID] = "v2.5.0"
    assert rc.run(RECOVER) == 1
    assert rc.code() == "READY_WRONG_VERSION"
    assert rc.docker.container is None and ACTIVE not in rc.docker.tags
    assert rc.docker.tags[ROLLBACK_REF] == ROLLBACK_ID
    assert core.marker_read(rc.marker)["outcome"] == "failed"
    assert "ROLLBACK_CLEANUP container=0 active=- down_code=- untag_code=-" in rc.out.getvalue()
    assert list((tmp_path / "failures" / "20261030T130000Z-recover").glob("*.log"))
    rc.assert_private()
    # Retry once the right version serves (the helper left a clean state).
    rc.docker.versions[ROLLBACK_ID] = PRE
    assert rc.run(RECOVER) == 1 and rc.code() == "FAILURES_DIR_EXISTS"  # same second, same folder
    shutil.rmtree(tmp_path / "failures" / "20261030T130000Z-recover")
    assert rc.run(RECOVER) == 0, rc.text


def test_recover_docker_calls_all_happen_under_both_locks(tmp_path):
    import fcntl

    rc = Recover(tmp_path)
    real = rc.docker
    unlocked: list[list[str]] = []

    def probing(argv, **kw):
        for path in (rc.lock, rc.marker.parent / rb.ACTIVATION_LOCK_NAME):
            fd = os.open(path, os.O_RDONLY)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                unlocked.append([str(path), *argv])
                fcntl.flock(fd, fcntl.LOCK_UN)
            except BlockingIOError:
                pass
            finally:
                os.close(fd)
        return real(argv, **kw)

    rc.docker = probing  # type: ignore[assignment]
    assert rc.run(RECOVER) == 0, rc.text
    assert real.calls and unlocked == []


def test_dry_run_reports_recover_eligibility_without_writing(tmp_path):
    rc = Recover(tmp_path)
    before = _tree(tmp_path)
    assert rc.run("--dry-run") == 0, rc.text
    lines = rc.out.getvalue().splitlines()
    assert ("ROLLBACK_RECOVER_ELIGIBILITY prelim_eligible=1 checks_run=6 recover_code=- db_present=1 "
            "db_migration_checked=0 deployer_lock_free=1 activation_lock_free=1") in lines
    state = dict(p.split("=", 1) for p in lines[0].split()[1:])
    assert state["snapshot_sha"] == "-" and state["marker_outcome"] == "failed"
    assert rc.docker.mutating() == [] and rc.spawn.argvs == []
    assert _tree(tmp_path) == before
    # Refusal reported the same way, still read-only.
    rc.write_marker(phase="snapshotted", failed_phase="retagged", outcome="failed")
    before = _tree(tmp_path)
    rc.docker.calls.clear()
    assert rc.run("--dry-run") == 0
    assert ("ROLLBACK_RECOVER_ELIGIBILITY prelim_eligible=0 checks_run=6 recover_code=RECOVER_MARKER_PAST_RETAG"
            in rc.out.getvalue())
    assert rc.docker.mutating() == [] and _tree(tmp_path) == before
    rc.docker.container = ROLLBACK_ID
    rc.write_marker(phase="stopped", failed_phase="snapshotted", outcome="failed")
    assert rc.run("--dry-run") == 0
    assert "prelim_eligible=0 checks_run=6 recover_code=RECOVER_CONTAINER_PRESENT" in rc.out.getvalue()
    # DB absence and a held lock are reported beside the preliminary answer.
    rc.docker.container = None
    saved = rc.data / "moved"
    saved.mkdir()
    for name in (dbsafety.DB_NAME, dbsafety.WAL_NAME, dbsafety.SHM_NAME):
        (rc.data / name).rename(saved / name)
    holder = _hold_activation_lock(rc)
    try:
        assert rc.run("--dry-run") == 0
        out = rc.out.getvalue()
        assert "prelim_eligible=1" in out and "db_present=0" in out
        assert "ROLLBACK_RECOVER_ELIGIBILITY" in out and out.count("activation_lock_free=0") == 2
    finally:
        holder.kill()
        holder.wait(timeout=10)



# ---------------------------------------------------------------------------
# A failed marker write after a successful start (both modes)
# ---------------------------------------------------------------------------


def _failing_marker_update(monkeypatch, *, when_outcome: str = "rolled_back"):
    real = core.marker_update

    def fails(path, data):
        if data.get("outcome") == when_outcome:
            raise core.Fail("MARKER_WRITE_FAILED")
        return real(path, data)

    monkeypatch.setattr(core, "marker_update", fails)


def _assert_cleaned_up(docker: FakeDocker, out: str, marker: Path, logs_dir: Path) -> None:
    assert docker.container is None and ACTIVE not in docker.tags
    assert docker.tags[ROLLBACK_REF] == ROLLBACK_ID
    assert any(c[-1] == "down" for c in docker.calls[-12:])
    assert "ROLLBACK_CLEANUP container=0 active=- down_code=- untag_code=-" in out
    assert "ROLLBACK_FINISHED" not in out
    assert core.marker_read(marker)["outcome"] == "failed"
    assert list(logs_dir.glob("*.log"))


def test_finish_marker_write_failure_after_ready_cleans_up(tmp_path, monkeypatch):
    sc = _prepared(tmp_path)
    sc.restore()
    logs_dir = tmp_path / "failures" / "20261030T130000Z-rollback"
    logs_before = len(list(logs_dir.glob("*.log")))
    _failing_marker_update(monkeypatch)
    assert sc.run("--finish", "--ack-post-cutover-writes", "6") == 1
    assert sc.code() == "MARKER_WRITE_FAILED"
    assert "ROLLBACK_READY version=v2.4.0" in sc.out.getvalue()  # it had started fine
    _assert_cleaned_up(sc.docker, sc.out.getvalue(), sc.marker, logs_dir)
    assert len(list(logs_dir.glob("*.log"))) == logs_before + 1
    sc.assert_private()
    # Control: the same fixture with a working marker write.
    monkeypatch.undo()
    assert sc.run("--finish", "--ack-post-cutover-writes", "6") == 0, sc.text
    assert core.marker_read(sc.marker)["outcome"] == "rolled_back"


def test_recover_marker_write_failure_after_ready_cleans_up(tmp_path, monkeypatch):
    rc = Recover(tmp_path)
    logs_dir = tmp_path / "failures" / "20261030T130000Z-recover"
    _failing_marker_update(monkeypatch)
    assert rc.run(RECOVER) == 1
    assert rc.code() == "MARKER_WRITE_FAILED"
    assert "ROLLBACK_READY version=v2.4.0" in rc.out.getvalue()
    _assert_cleaned_up(rc.docker, rc.out.getvalue(), rc.marker, logs_dir)
    rc.assert_private()
    # Control: the same fixture with a working marker write.
    monkeypatch.undo()
    shutil.rmtree(logs_dir)  # same-second folder name in tests
    assert rc.run(RECOVER) == 0, rc.text
    assert core.marker_read(rc.marker)["outcome"] == "rolled_back"



# ---------------------------------------------------------------------------
# Reopen cycle 3: marker durability, broken output, real compose-up failures
# ---------------------------------------------------------------------------


def _finish_ready(tmp: Path) -> Scenario:
    sc = _prepared(tmp)
    sc.restore()
    return sc


def _modes():
    return [
        pytest.param(lambda tmp: (_finish_ready(tmp), ["--finish", "--ack-post-cutover-writes", "6"]), id="finish"),
        pytest.param(lambda tmp: (Recover(tmp), [RECOVER]), id="recover"),
    ]


@pytest.mark.parametrize("make", _modes())
def test_marker_replaced_but_not_durable_keeps_the_service(tmp_path, monkeypatch, make):
    """The replace landed and only the directory fsync failed: the marker
    reads rolled_back and the service is verified up, so nothing is torn
    down; the run says so and exits 1."""
    sc, args = make(tmp_path / "fault")
    real_fsync_dir = core._fsync_dir

    def fsync_fails(directory):
        if Path(directory) == sc.marker.parent:
            raise OSError("injected fsync failure")
        return real_fsync_dir(directory)

    monkeypatch.setattr(core, "_fsync_dir", fsync_fails)
    sc.docker.calls.clear()
    assert sc.run(*args) == 1
    assert sc.code() == "MARKER_DURABILITY_UNCERTAIN"
    assert core.marker_read(sc.marker)["outcome"] == "rolled_back"
    assert sc.docker.container == ROLLBACK_ID and sc.docker.tags[ACTIVE] == ROLLBACK_ID
    up = sc.docker.calls.index(["docker", "compose", "-f", COMPOSE, "up", "-d"])
    assert not any(c[-1] == "down" for c in sc.docker.calls[up:])
    assert not any(c[:3] == ["docker", "image", "rm"] for c in sc.docker.calls[up:])
    out = sc.out.getvalue()
    assert ("ROLLBACK_MARKER_DURABILITY_UNCERTAIN service_up=1 version=v2.4.0 "
            f"container_image={ROLLBACK_ID} marker={sc.marker} marker_outcome=rolled_back") in out
    assert "ROLLBACK_CLEANUP" not in out and "ROLLBACK_FINISHED" not in out
    sc.assert_private()
    # Control: the same fixture shape without the fault succeeds.
    monkeypatch.undo()
    ok, args = make(tmp_path / "ok")
    assert ok.run(*args) == 0, ok.text


@pytest.mark.parametrize("make", _modes())
@pytest.mark.parametrize("damage", ["before-replace", "unreadable"])
def test_marker_write_failure_without_a_rolled_back_marker_cleans_up(tmp_path, monkeypatch, make, damage):
    sc, args = make(tmp_path / "fault")
    real = core.marker_update

    def failing(path, data):
        if data.get("outcome") != "rolled_back":
            return real(path, data)
        if damage == "unreadable":
            Path(path).write_text("{torn")
        raise core.Fail("MARKER_WRITE_FAILED")

    monkeypatch.setattr(core, "marker_update", failing)
    assert sc.run(*args) == 1
    assert sc.code() == "MARKER_WRITE_FAILED"
    assert sc.docker.container is None and ACTIVE not in sc.docker.tags
    assert "ROLLBACK_CLEANUP container=0 active=- down_code=- untag_code=-" in sc.out.getvalue()
    if damage == "before-replace":
        assert core.marker_read(sc.marker)["outcome"] == "failed"
    monkeypatch.undo()
    ok, args = make(tmp_path / "ok")
    assert ok.run(*args) == 0, ok.text


class BreaksAfterTag(io.StringIO):
    """The operator's stream: fine until ``active`` is tagged, then every
    write raises BrokenPipeError (the ssh session went away)."""

    def __init__(self) -> None:
        super().__init__()
        self.broken = False

    def write(self, text):
        if self.broken:
            raise BrokenPipeError("pipe closed")
        return super().write(text)


def _break_on_tag(sc) -> BreaksAfterTag:
    stream = BreaksAfterTag()
    real = sc.docker

    def runner(argv, **kw):
        if argv[:2] == ["docker", "tag"]:
            stream.broken = True
        return real(argv, **kw)

    sc.docker = runner
    sc.real_docker = real
    sc.stream = stream
    return stream


@pytest.mark.parametrize("make", _modes())
def test_a_broken_pipe_never_stops_the_teardown(tmp_path, make):
    sc, args = make(tmp_path / "broken")
    _break_on_tag(sc)
    sc.real_docker.versions[ROLLBACK_ID] = "v2.5.0"  # readiness fails after the start
    assert sc.run(*args) == 1
    real = sc.real_docker
    up = real.calls.index(["docker", "compose", "-f", COMPOSE, "up", "-d"])
    assert ["docker", "compose", "-f", COMPOSE, "down"] in real.calls[up:]
    assert ["docker", "image", "rm", ACTIVE] in real.calls[up:]
    assert real.container is None and ACTIVE not in real.tags
    assert core.marker_read(sc.marker)["outcome"] == "failed"
    # Control: the same failure with a working stream reports the cleanup.
    ok, args = make(tmp_path / "ok")
    ok.docker.versions[ROLLBACK_ID] = "v2.5.0"
    assert ok.run(*args) == 1
    assert "ROLLBACK_CLEANUP container=0" in ok.out.getvalue()
    assert ok.docker.container is None and ACTIVE not in ok.docker.tags


@pytest.mark.parametrize("make", _modes())
def test_a_broken_pipe_does_not_undo_a_durable_success(tmp_path, make):
    sc, args = make(tmp_path / "broken")
    _break_on_tag(sc)
    assert sc.run(*args) == 0
    assert core.marker_read(sc.marker)["outcome"] == "rolled_back"
    assert sc.real_docker.container == ROLLBACK_ID and sc.real_docker.tags[ACTIVE] == ROLLBACK_ID


def _up_fails(rc, *, partial: bool):
    real = rc.docker

    def runner(argv, **kw):
        if argv[-2:] == ["up", "-d"]:
            real.calls.append(list(argv))
            if partial:
                real.container = real.tags[ACTIVE]  # the container came up, compose hung
                raise subprocess.TimeoutExpired(argv, kw["timeout"], stderr=f"stuck {SECRET}")
            return subprocess.CompletedProcess(argv, 1, "", f"Error response from daemon {SECRET}\n")
        return real(argv, **kw)

    rc.docker = runner
    return real


@pytest.mark.parametrize("partial,code", [(False, "COMPOSE_UP_D_FAILED"), (True, "TIMEOUT_COMPOSE_UP_D")],
                         ids=["non-zero-exit", "timeout-after-partial-start"])
def test_recover_compose_up_failure_cleans_up(tmp_path, partial, code):
    rc = Recover(tmp_path / "fault")
    real = _up_fails(rc, partial=partial)
    assert rc.run(RECOVER) == 1
    assert rc.code() == code
    up = real.calls.index(["docker", "compose", "-f", COMPOSE, "up", "-d"])
    assert ["docker", "compose", "-f", COMPOSE, "down"] in real.calls[up:]
    assert real.container is None and ACTIVE not in real.tags
    assert real.tags[ROLLBACK_REF] == ROLLBACK_ID
    assert core.marker_read(rc.marker)["outcome"] == "failed"
    assert "ROLLBACK_CLEANUP container=0 active=- down_code=- untag_code=-" in rc.out.getvalue()
    assert SECRET not in rc.text
    # Control: the same fixture shape with a working compose up.
    ok = Recover(tmp_path / "ok")
    assert ok.run(RECOVER) == 0, ok.text


# ---------------------------------------------------------------------------
# RISK-3: the shared untag never removes an image's last name
# ---------------------------------------------------------------------------


def test_prepare_refuses_to_untag_an_image_with_no_other_name(tmp_path):
    sc = Scenario(tmp_path / "broken")
    sc.docker.tags.pop(RELEASE_TAG)  # active -> the release, which now has no other name
    assert sc.run("--prepare") == 1
    assert sc.code() == "ACTIVE_TAG_UNEXPECTED"
    assert not any(c[:3] == ["docker", "image", "rm"] for c in sc.docker.calls)
    assert sc.docker.tags[ACTIVE] == RELEASE_ID
    # Control: the same fixture with the release tag in place untags.
    ok = Scenario(tmp_path / "ok")
    assert ok.run("--prepare") == 0, ok.text
    assert ACTIVE not in ok.docker.tags and ok.docker.tags[RELEASE_TAG] == RELEASE_ID


def test_shared_untag_helper(tmp_path):
    docker = FakeDocker()
    keepers = [(RELEASE_TAG, RELEASE_ID), (ROLLBACK_REF, ROLLBACK_ID)]
    kw = {"unsafe_code": "X_UNSAFE", "failed_code": "X_FAILED"}
    # A keeper that names a different image does not count.
    docker.tags[RELEASE_TAG] = ROLLBACK_ID
    with pytest.raises(core.Fail) as exc:
        dbsafety.untag_active(docker, ACTIVE, keepers, **kw)
    assert exc.value.code == "X_UNSAFE"
    assert not any(c[:3] == ["docker", "image", "rm"] for c in docker.calls)
    # Control: the release keeps its tag -> untagged, ID returned, image kept.
    docker.tags[RELEASE_TAG] = RELEASE_ID
    assert dbsafety.untag_active(docker, ACTIVE, keepers, **kw) == RELEASE_ID
    assert ACTIVE not in docker.tags and docker.tags[RELEASE_TAG] == RELEASE_ID
    # Already absent: nothing to do, no rm.
    docker.calls.clear()
    assert dbsafety.untag_active(docker, ACTIVE, keepers, **kw) is None
    assert not any(c[:3] == ["docker", "image", "rm"] for c in docker.calls)
