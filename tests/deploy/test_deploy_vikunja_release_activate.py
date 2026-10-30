"""Tests for the ACTIVATE entrypoint (#1087, WP04).

No real Docker, Compose, network or ssh. A stateful fake of the office2
Docker/Compose/curl surface is injected as the runner; ``capture_logs`` gets
a ``popen`` that starts a tiny local Python child printing fake container
logs; the clock, wall clock, sleep and disk usage are injected; every root is
under ``tmp_path``. The snapshot is the real ``dbsafety.snapshot`` on a small
SQLite DB with the v2.4.0 ``tasks`` shape.

Every refusal or absence assertion has a same-fixture positive control.
Every failure after ``down`` asserts the lock-held end state and the INV-1
call-scan (no call ever tags ``active`` to the rollback image).
"""

from __future__ import annotations

import importlib.util
import fcntl
import io
import json
import os
import sqlite3
import stat
import subprocess
import sys
from collections import namedtuple
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.deploy.vikunja_release import core

_ROOT = Path(__file__).resolve().parents[2]
_ENTRY_REL = "scripts/deploy/deploy-vikunja-release-activate.py"
_PATH = _ROOT / _ENTRY_REL
_spec = importlib.util.spec_from_file_location("deploy_vikunja_release_activate", _PATH)
mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = mod
_spec.loader.exec_module(mod)

_RELEASE = _ROOT / "services" / "vikunja" / "release.json"
_LIVE_COMPOSE = _ROOT / "services" / "vikunja" / "docker-compose.yml"
_FIX = Path(__file__).resolve().parent / "fixtures" / "vikunja_release"

RELEASE_ID = "sha256:35e1bc8790292deedf2addc3f3f196e38d84c2614219a95d6ef711c1f02afba5"
ROLLBACK_ID = "sha256:60fe1ee8f729c17b057ba00a49b968adb4ed1e774cea36b5f4cc81340991a7d2"
OTHER_ID = "sha256:" + "ab" * 32
ROLLBACK_REF = "vikunja/vikunja:2.4.0"
RELEASE_TAG = "office2.local/vikunja:v2.7.1-670-420c7bcb75"
ACTIVE_TAG = "office2.local/vikunja:active"
RELEASE_VERSION = "v2.7.1-670-420c7bcb75"
PRE_VERSION = "v2.4.0"
T0 = datetime(2026, 10, 30, 12, 0, 0, tzinfo=timezone.utc)

SECRET = "password=hunter2"
TITLE = "Buy anniversary gift for Margot"
USER_NAME = "alice.wonderland"
SEEDED = f"login failed {SECRET} task '{TITLE}' owner {USER_NAME}"
LEAKS = (SECRET, "hunter2", TITLE, USER_NAME)

#: Real-shaped ``docker logs --timestamps`` output: the build logs logfmt with
#: a quoted msg (release-build rehearsal shape, synthetic data).
MIGRATED_LOG = (
    f'2026-10-30T12:00:01.000000000Z time=2026-10-30T12:00:01.000Z level=INFO msg="user login" '
    f'user={USER_NAME} detail="{SECRET} task {TITLE}"\n'
    '2026-10-30T12:00:02.000000000Z time=2026-10-30T12:00:02.000Z level=INFO msg="RRULE migration: 7 '
    'legacy-repeat task(s) processed — 5 converted, 1 already had an RRULE, 1 unconvertible (originals '
    'backed up to task_repeat_legacy_backup); 2 row(s) used the server zone"\n'
    '2026-10-30T12:00:03.000000000Z time=2026-10-30T12:00:03.000Z level=INFO msg="Ran all migrations successfully."\n'
)
UNMIGRATED_LOG = (f'2026-10-30T12:00:01.000000000Z time=2026-10-30T12:00:01.000Z level=INFO '
                  f'msg="starting" detail="{SECRET} {TITLE}"\n')

READ_ONLY_DOCKER = {("info",), ("image", "inspect"), ("container", "inspect")}
MUTATING = {("compose", "down"), ("compose", "up"), ("image", "rm"), ("tag",), ("load",), ("run",),
            ("start",), ("stop",), ("rm",), ("rmi",), ("pull",)}

# The repo's Compose file is pre-merge until the ACTIVATE change set (WP08)
# lands, and post-merge after; derive both forms whichever state it is in.
_OLD_IMAGE = "    image: vikunja/vikunja:2.4.0\n"
_NEW_IMAGE = "    image: office2.local/vikunja:active\n    pull_policy: never\n"
_LIVE_TEXT = _LIVE_COMPOSE.read_text(encoding="utf-8")
if _NEW_IMAGE in _LIVE_TEXT:
    POST_MERGE_COMPOSE = _LIVE_TEXT
    PRE_MERGE_COMPOSE = _LIVE_TEXT.replace(_NEW_IMAGE, _OLD_IMAGE)
else:
    PRE_MERGE_COMPOSE = _LIVE_TEXT
    POST_MERGE_COMPOSE = _LIVE_TEXT.replace(_OLD_IMAGE, _NEW_IMAGE)
assert PRE_MERGE_COMPOSE.count(_OLD_IMAGE) == 1 and POST_MERGE_COMPOSE.count(_NEW_IMAGE) == 1

DiskUsage = namedtuple("DiskUsage", "total used free")


def _fixture(name: str):
    return json.loads((_FIX / name).read_text(encoding="utf-8"))


def _facts(image_id: str, **over) -> dict:
    cfg = _fixture("config.json")
    facts = {"Id": image_id, "Architecture": cfg["architecture"], "Os": cfg["os"],
             "Config": {"User": cfg["config"]["User"], "Labels": dict(cfg["config"]["Labels"])}}
    facts.update(over)
    return facts


# ---------------------------------------------------------------------------
# The fake office2 surface
# ---------------------------------------------------------------------------


class FakeClock:
    def __init__(self, t: float = 1000.0):
        self.t = t
        #: When set, each read advances the clock (used only while a real
        #: ``docker logs`` stand-in child is being waited on).
        self.auto_step = 0.0

    def __call__(self) -> float:
        now = self.t
        self.t += self.auto_step
        return now

    def sleep(self, seconds: float) -> None:
        self.t += max(0.0, seconds)


def _verb(argv: list[str]) -> tuple[str, ...]:
    if argv[0] == "curl":
        return ("curl",)
    if argv[1] == "compose":
        return ("compose", argv[4])
    if argv[1] in ("image", "container"):
        return (argv[1], argv[2])
    return (argv[1],)


class World:
    """Docker images, tags and the ``vikunja`` container, plus Compose, curl
    and ``docker logs``. Records every call with its kwargs and the umask."""

    def __init__(self, compose_file: Path, clock: FakeClock):
        self.compose_file = str(compose_file)
        self.clock = clock
        self.calls: list[tuple[list[str], dict]] = []
        self.umasks: list[int] = []
        self.info = _fixture("docker_info.json")
        self.images = {ROLLBACK_ID: _fixture("image_inspect_vikunja_2.4.0.json"), RELEASE_ID: _facts(RELEASE_ID)}
        self.tags = {ROLLBACK_REF: ROLLBACK_ID, RELEASE_TAG: RELEASE_ID, ACTIVE_TAG: ROLLBACK_ID}
        self.container: dict | None = {"image": ROLLBACK_ID, "config": ACTIVE_TAG}
        self.versions = {ROLLBACK_ID: PRE_VERSION, RELEASE_ID: RELEASE_VERSION}
        #: verb -> queue of "rc" | "timeout" | "effect_timeout" | "ok" (popped
        #: per call; default ok). "timeout" hangs with no effect; "effect_timeout"
        #: applies the effect (e.g. the container is created) and then hangs.
        self.fail: dict[tuple[str, ...], list[str]] = {}
        #: verb -> seconds the call takes. The clock advances by the elapsed
        #: time, never past the call's timeout: a call that would take longer
        #: hangs until its timeout and raises TimeoutExpired with no effect.
        self.cost: dict[tuple[str, ...], float] = {}
        self.default_cost = 0.0
        #: (verb, start time, timeout) for every call, for budget assertions.
        self.timeline: list[tuple[tuple[str, ...], float, float]] = []
        self.http_status = 200
        #: HTTP status once the release runs (readiness), separately.
        self.release_http_status = 200
        self.pre_hook = None  # called with argv before each call is answered
        self.up_image: str | None = None  # force the started container's image
        self.on_down = None  # hook run on each successful compose down
        self.logs = {RELEASE_ID: MIGRATED_LOG, ROLLBACK_ID: UNMIGRATED_LOG}
        self.popen_raises: BaseException | None = None
        self.log_hang = False  # the logs child writes its text, then never exits
        self.log_argv: list[list[str]] = []

    # -- helpers for assertions --

    def verbs(self) -> set[tuple[str, ...]]:
        return {_verb(a) for a, _ in self.calls}

    def docker_verbs(self) -> set[tuple[str, ...]]:
        return {_verb(a) for a, _ in self.calls if a[0] == "docker"}

    def mutating(self) -> list[list[str]]:
        return [a for a, _ in self.calls if a[0] == "docker" and _verb(a) in MUTATING]

    def resolve(self, ref: str) -> str | None:
        if ref in self.tags:
            return self.tags[ref]
        return ref if ref in self.images else None

    def _r(self, argv, rc, out="", err=""):
        return subprocess.CompletedProcess(argv, rc, out, err)

    # -- the runner --

    def __call__(self, argv, **kwargs):
        argv = list(argv)
        if self.pre_hook is not None:
            self.pre_hook(argv)
        self.calls.append((argv, kwargs))
        mask = os.umask(0)
        os.umask(mask)
        self.umasks.append(mask)
        assert "shell" not in kwargs and kwargs.get("timeout")
        verb = _verb(argv)
        timeout = float(kwargs["timeout"])
        self.timeline.append((verb, self.clock.t, timeout))
        queue = self.fail.get(verb)
        mode = queue.pop(0) if queue else "ok"
        cost = self.cost.get(verb, self.default_cost)
        if mode == "timeout" or cost > timeout:
            self.clock.t += timeout
            raise subprocess.TimeoutExpired(argv, timeout, stderr=SEEDED)
        self.clock.t += cost
        if mode == "rc":
            return self._r(argv, 1, "", f"Error response from daemon: {SEEDED}\n")
        result = self._answer(argv)
        if mode == "effect_timeout":
            self.clock.t += timeout - cost
            raise subprocess.TimeoutExpired(argv, timeout, stderr=SEEDED)
        return result

    def _answer(self, argv):
        if argv[0] == "curl":
            return self._curl(argv)
        cmd = argv[1:]
        if cmd == ["info", "--format", "{{json .}}"]:
            return self._r(argv, 0, json.dumps(self.info) + "\n")
        if cmd[:3] == ["image", "inspect", "--format"]:
            iid = self.resolve(cmd[4])
            if iid is None:
                return self._r(argv, 1, "", f"Error response from daemon: No such image: {cmd[4]}\n")
            if cmd[3] == "{{.Id}}":
                return self._r(argv, 0, iid + "\n")
            if cmd[3] == mod.dbsafety.UNTAG_INSPECT_FORMAT:
                names = " ".join(sorted(t for t, i in self.tags.items() if i == iid))
                return self._r(argv, 0, f"{iid} {names}\n")
            return self._r(argv, 0, json.dumps([self.images[iid]]) + "\n")
        if cmd[:3] == ["container", "inspect", "--format"]:
            if self.container is None:
                return self._r(argv, 1, "", f"Error: No such container: {cmd[4]}\n")
            return self._r(argv, 0, f"{self.container['image']} {self.container['config']}\n")
        if cmd[:3] == ["compose", "-f", self.compose_file]:
            action = cmd[3:]
            if action == ["down"]:
                self.container = None
                if self.on_down is not None:
                    self.on_down()
                return self._r(argv, 0, "", " Container vikunja Removed\n")
            if action == ["up", "-d"]:
                iid = self.tags.get(ACTIVE_TAG)
                if iid is None:  # WP05: pull_policy never + missing tag fails closed
                    return self._r(argv, 1, "", f"Error response from daemon: No such image: {ACTIVE_TAG}\n")
                self.container = {"image": self.up_image or iid, "config": ACTIVE_TAG}
                return self._r(argv, 0, "", " Container vikunja Started\n")
        if cmd[:2] == ["image", "rm"] and len(cmd) == 3:
            if cmd[2] not in self.tags:
                return self._r(argv, 1, "", f"Error response from daemon: No such image: {cmd[2]}\n")
            del self.tags[cmd[2]]
            return self._r(argv, 0, f"Untagged: {cmd[2]}\n")
        if cmd[0] == "tag" and len(cmd) == 3:
            iid = self.resolve(cmd[1])
            assert iid is not None
            self.tags[cmd[2]] = iid
            return self._r(argv, 0)
        return self._r(argv, 1, "", "unexpected call\n")

    def _curl(self, argv):
        if self.container is None:
            return self._r(argv, 7, "", "curl: (7) Failed to connect\n")
        status = self.release_http_status if self.container["image"] == RELEASE_ID else self.http_status
        if status != 200:
            return self._r(argv, 0, f"{{\"message\": \"{SEEDED}\"}}\n{status}")
        version = self.versions.get(self.container["image"], "v0.0.1")
        body = json.dumps({"version": version, "frontend_url": "https://example.invalid/", "motd": SEEDED})
        return self._r(argv, 0, f"{body}\n200")

    # -- popen for capture_logs --

    def popen(self, argv, **kwargs):
        self.log_argv.append(list(argv))
        if self.popen_raises is not None:
            raise self.popen_raises
        text = self.logs.get(self.container["image"] if self.container else "", "")
        code = f"import sys\nsys.stdout.write({text!r})\nsys.stdout.flush()\n"
        if self.log_hang:
            code += "import time\ntime.sleep(600)\n"
        return subprocess.Popen([sys.executable, "-c", code], **kwargs)


def _make_db(path: Path, rows: int = 12) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, isolation_level=None)
    try:
        conn.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY, title TEXT, "
                     "repeat_after INTEGER, repeat_mode INTEGER NOT NULL DEFAULT 0)")
        conn.executemany("INSERT INTO tasks (id, title, repeat_after, repeat_mode) VALUES (?, ?, ?, ?)",
                         [(i, f"{TITLE} {SECRET} #{i}", 86400 * (i % 3), i % 2) for i in range(1, rows + 1)])
    finally:
        conn.close()


class Env:
    def __init__(self, base: Path, *, compose: str = POST_MERGE_COMPOSE):
        base.mkdir(parents=True, exist_ok=True)
        self.base = base
        self.services = base / "services-vikunja"  # stands in for /data/services/vikunja
        self.services.mkdir()
        self.data = self.services / "data"
        _make_db(self.data / "vikunja.db")
        self.compose = base / "docker-compose.yml"
        self.compose.write_text(compose, encoding="utf-8")
        rec = json.loads(_RELEASE.read_text(encoding="utf-8"))
        rec["service"]["compose_file"] = str(self.compose)
        rec["service"]["data_dir"] = str(self.data)
        rec["roots"]["snapshots"] = str(self.services / "snapshots")
        rec["roots"]["activation"] = str(self.services / "activation")
        rec["roots"]["private_logs"] = str(self.services / "failures")
        self.rec = rec
        self.release_path = base / "release.json"
        self.release_path.write_text(json.dumps(rec), encoding="utf-8")
        self.activation = Path(rec["roots"]["activation"])
        self.snapshots = Path(rec["roots"]["snapshots"])
        self.failures = Path(rec["roots"]["private_logs"])
        self.marker = self.activation / f"{RELEASE_VERSION}.json"
        self.clock = FakeClock()
        self.world = World(self.compose, self.clock)
        self.free = 10 ** 12

    def disk_usage(self, path):
        assert Path(path).exists()
        return DiskUsage(10 ** 13, 0, self.free)

    def run(self, *argv: str):
        out, err = io.StringIO(), io.StringIO()
        rc = mod.main(list(argv), runner=self.world, popen=self.world.popen, clock=self.clock,
                      now=lambda: T0, sleep=self.clock.sleep, disk_usage=self.disk_usage,
                      release_path=self.release_path, stdout=out, stderr=err)
        return rc, out.getvalue().splitlines(), err.getvalue()

    def write_marker(self, **data) -> None:
        """A marker only ever exists after an --apply, which created the lock
        file first; so the fixture creates both."""
        self.make_lock_file()
        core.marker_create(self.marker, {"phase": "started", "outcome": None, **data})

    def make_lock_file(self) -> Path:
        self.activation.mkdir(mode=0o700, exist_ok=True)
        lock = self.activation / mod.ACTIVATION_LOCK_NAME
        os.close(os.open(lock, os.O_CREAT | os.O_RDWR, 0o600))
        return lock

    def marker_data(self) -> dict | None:
        return core.marker_read(self.marker)


@pytest.fixture
def env(tmp_path):
    return Env(tmp_path / "case")


def _code(lines: list[str]) -> str | None:
    if not lines or not lines[0].startswith("FAILED code="):
        return None
    return lines[0].split()[1].split("=", 1)[1]


def _unmet(lines: list[str]) -> dict[str, str]:
    out = {}
    for line in lines:
        if line.startswith("ACTIVATE_CHECK ") and "status_code=UNMET" in line:
            fields = dict(p.split("=", 1) for p in line.split()[1:])
            out[fields["check_code"]] = fields["code"]
    return out


def assert_inv1(world: World) -> None:
    """INV-1 call-scan: no call ever tags `active` to the rollback image."""
    for argv, _ in world.calls:
        if argv[0] == "docker" and argv[1] == "tag":
            assert argv[3] != ACTIVE_TAG or argv[2] not in (ROLLBACK_ID, ROLLBACK_REF), argv
    tag_calls = [a for a, _ in world.calls if a[0] == "docker" and a[1] == "tag"]
    assert all(a == ["docker", "tag", RELEASE_ID, ACTIVE_TAG] for a in tag_calls), tag_calls


def assert_lock_held_end_state(env: Env, code: str, failed_phase: str) -> dict:
    w = env.world
    assert w.container is None, "no container after a failed activation"
    assert ACTIVE_TAG not in w.tags, "the lock (active untagged) is held"
    assert w.tags[ROLLBACK_REF] == ROLLBACK_ID and ROLLBACK_ID in w.images
    assert w.tags[RELEASE_TAG] == RELEASE_ID and RELEASE_ID in w.images
    marker = env.marker_data()
    assert marker["outcome"] == "failed" and marker["error"] == code
    assert marker["failed_phase"] == failed_phase
    assert_inv1(w)
    return marker


def _last_index(world: World, prefix: list[str]) -> int | None:
    idx = None
    for i, (a, _) in enumerate(world.calls):
        if a[0] == "docker" and a[1:1 + len(prefix)] == prefix:
            idx = i
    return idx


def _fs(env: Env) -> dict[str, tuple]:
    """Every path under the env (roots, data, marker) with size, mtime and mode."""
    out = {}
    for path in sorted(env.base.rglob("*")):
        st = path.lstat()
        out[str(path.relative_to(env.base))] = (st.st_size, st.st_mtime_ns, st.st_mode)
    return out


def _happy(env: Env) -> list[str]:
    rc, lines, err = env.run("--apply")
    assert rc == 0, lines
    assert err == ""
    return lines


# ---------------------------------------------------------------------------
# Entrypoint shape
# ---------------------------------------------------------------------------


def test_entrypoint_is_executable_in_git():
    out = subprocess.run(["git", "ls-files", "-s", _ENTRY_REL], cwd=_ROOT,
                         capture_output=True, text=True, check=True).stdout
    assert out.startswith("100755"), out


def test_entrypoint_shebang_shim_and_no_shell():
    src = _PATH.read_text(encoding="utf-8")
    assert src.startswith("#!/usr/bin/env python3\n")
    assert "sys.path.insert(0, str(Path(__file__).resolve().parents[2]))" in src
    assert "shell=True" not in src


def test_compose_argv_is_exactly_the_units(env):
    """vikunja.service runs `docker compose -f <file> up -d`; no -p, no extras."""
    _happy(env)
    compose = [a for a, _ in env.world.calls if a[:2] == ["docker", "compose"]]
    assert compose == [["docker", "compose", "-f", str(env.compose), "down"],
                       ["docker", "compose", "-f", str(env.compose), "up", "-d"]]
    assert "services/vikunja/docker-compose.yml" in json.loads(_RELEASE.read_text())["service"]["compose_file"]


@pytest.mark.parametrize("argv", [[], ["--apply", "--dry-run"], ["--force"], ["apply"]])
def test_usage_exits_2_without_any_call(env, argv):
    rc, lines, err = env.run(*argv)
    assert rc == 2 and lines == [] and err.startswith("usage:")
    assert env.world.calls == []
    assert env.run("--dry-run")[0] == 0  # positive control


def test_umask_is_private_during_the_run_and_restored(env):
    before = os.umask(0o022)
    try:
        _happy(env)
        assert env.world.umasks and set(env.world.umasks) == {0o077}
        assert os.umask(0o022) == 0o022
    finally:
        os.umask(before)


# ---------------------------------------------------------------------------
# T017 — preconditions and dry run
# ---------------------------------------------------------------------------


def test_dry_run_reports_every_precondition_and_mutates_nothing(env):
    rc, lines, err = env.run("--dry-run")
    assert rc == 0, lines
    assert err == ""
    assert lines[0] == f"ACTIVATE_DRY_RUN_READY release_version={RELEASE_VERSION} config_digest={RELEASE_ID}"
    for name in mod.CHECKS:
        assert f"ACTIVATE_CHECK check_code={name} status_code=MET" in lines
    assert f"ACTIVATE_MARKER marker={env.marker} status_code=ABSENT" in lines
    assert f"ACTIVATE_PRE_VERSION pre_version={PRE_VERSION}" in lines
    assert env.world.docker_verbs() == READ_ONLY_DOCKER
    assert env.world.mutating() == []
    # Nothing written: no marker, no private, snapshot or activation root.
    assert sorted(p.name for p in env.services.iterdir()) == ["data"]
    assert sorted(p.name for p in env.data.iterdir()) == ["vikunja.db"]


def test_expected_unmet_set_before_the_activate_merge_is_only_compose(tmp_path):
    """R-19: with the live (pre-merge) Compose file and the container on
    `vikunja/vikunja:2.4.0`, the only unmet precondition is Compose."""
    pre = Env(tmp_path / "pre", compose=PRE_MERGE_COMPOSE)
    pre.world.container = {"image": ROLLBACK_ID, "config": ROLLBACK_REF}
    rc, lines, _ = pre.run("--dry-run")
    assert rc == 1 and _code(lines) == "ACTIVATE_PRECONDITIONS_UNMET"
    assert _unmet(lines) == {"PRE_COMPOSE": "PRE_COMPOSE_NOT_ACTIVE"}
    assert pre.world.mutating() == []
    # Same fixture after the merge (Compose on `active`): ready.
    pre.compose.write_text(POST_MERGE_COMPOSE, encoding="utf-8")
    rc, lines, _ = pre.run("--dry-run")
    assert rc == 0, lines and _unmet(lines) == {}


def _set(path: str, value):
    def apply(env: Env):
        obj, attr = path.split(".", 1)
        target = env.world if obj == "world" else env
        keys = attr.split(".")
        node = getattr(target, keys[0])
        if len(keys) == 1:
            setattr(target, keys[0], value)
        else:
            for k in keys[1:-1]:
                node = node[k]
            node[keys[-1]] = value
    return apply


def _del_tag(tag):
    return lambda env: env.world.tags.pop(tag)


def _compose_without_pull_policy(env):
    env.compose.write_text(POST_MERGE_COMPOSE.replace("    pull_policy: never\n", ""), encoding="utf-8")


def _db_unreadable(env):
    (env.data / "vikunja.db").chmod(0)


def _db_missing(env):
    (env.data / "vikunja.db").rename(env.data / "away.db")


PRECONDITIONS = [
    ("PRE_STORE", "DOCKER_STORE_UNSUPPORTED", _set("world.info.Driver", "overlayfs")),
    ("PRE_RELEASE_TAG", "PRE_RELEASE_TAG_NOT_STAGED", _del_tag(RELEASE_TAG)),
    ("PRE_RELEASE_TAG", "PRE_RELEASE_FACTS_MISMATCH",
     lambda env: env.world.images.__setitem__(RELEASE_ID, _facts(RELEASE_ID, Architecture="arm64"))),
    ("PRE_ACTIVE_TAG", "PRE_ACTIVE_ABSENT", _del_tag(ACTIVE_TAG)),
    ("PRE_ACTIVE_TAG", "PRE_ACTIVE_NOT_ROLLBACK", lambda env: env.world.tags.__setitem__(ACTIVE_TAG, RELEASE_ID)),
    ("PRE_CONTAINER", "PRE_CONTAINER_ABSENT", _set("world.container", None)),
    ("PRE_CONTAINER", "PRE_CONTAINER_NOT_ROLLBACK",
     _set("world.container", {"image": RELEASE_ID, "config": ACTIVE_TAG})),
    ("PRE_CONTAINER", "PRE_CONTAINER_REF_UNEXPECTED",
     _set("world.container", {"image": ROLLBACK_ID, "config": "vikunja/vikunja:latest"})),
    ("PRE_COMPOSE", "PRE_COMPOSE_PULL_POLICY", _compose_without_pull_policy),
    ("PRE_DATA_READABLE", "PRE_DATA_UNREADABLE", _db_unreadable),
    ("PRE_SPACE", "PRE_SPACE_LOW", _set("env.free", 100)),
    ("PRE_VERSION", "PRE_VERSION_UNREADABLE", lambda env: env.world.versions.__setitem__(ROLLBACK_ID, "v2.3.9")),
    ("PRE_VERSION", "PRE_VERSION_UNREADABLE", _set("world.http_status", 503)),
]


@pytest.mark.parametrize("mode", ["--dry-run", "--apply"])
@pytest.mark.parametrize("check, code, break_it", PRECONDITIONS,
                         ids=[f"{c}-{i}" for i, (c, _, _) in enumerate(PRECONDITIONS)])
def test_each_unmet_precondition_is_reported_alone_and_nothing_moves(tmp_path, mode, check, code, break_it):
    # Same-fixture positive control first: the unbroken env is ready.
    control = Env(tmp_path / "control")
    assert control.run("--dry-run")[0] == 0
    env = Env(tmp_path / "case")
    break_it(env)
    tags = dict(env.world.tags)
    container = env.world.container
    rc, lines, _ = env.run(mode)
    assert rc == 1 and _code(lines) == "ACTIVATE_PRECONDITIONS_UNMET", lines
    expected = {check: code}
    if code in ("PRE_CONTAINER_ABSENT", "PRE_CONTAINER_NOT_ROLLBACK"):  # 2.4.0 is not what answers
        expected["PRE_VERSION"] = "PRE_VERSION_UNREADABLE"
    assert _unmet(lines) == expected
    assert env.world.mutating() == []
    assert env.world.docker_verbs() <= READ_ONLY_DOCKER
    assert env.world.tags == tags and env.world.container == container
    assert not env.marker.exists()
    assert not env.snapshots.exists()


def test_missing_db_is_unreadable_and_its_space_need_unknown(env):
    assert env.run("--dry-run")[0] == 0  # positive control, same fixture
    _db_missing(env)
    rc, lines, _ = env.run("--dry-run")
    assert rc == 1 and _unmet(lines) == {"PRE_DATA_READABLE": "PRE_DATA_UNREADABLE",
                                         "PRE_SPACE": "PRE_SPACE_UNKNOWN"}
    assert env.world.mutating() == []


def test_space_needs_three_times_db_plus_wal(env):
    db = (env.data / "vikunja.db").stat().st_size
    (env.data / "vikunja.db-wal").write_bytes(b"\0" * 4096)
    need = 3 * (db + 4096)
    env.free = need
    assert env.run("--dry-run")[0] == 0
    env.free = need - 1
    rc, lines, _ = env.run("--dry-run")
    assert rc == 1 and _unmet(lines) == {"PRE_SPACE": "PRE_SPACE_LOW"}


def test_pre_version_failure_fails_before_the_stop(env):
    """U1: pre_version is read from the running 2.4.0 before anything stops;
    without it the run ends with no marker and the lock not taken."""
    env.world.http_status = 503
    rc, lines, _ = env.run("--apply")
    assert rc == 1 and _code(lines) == "ACTIVATE_PRECONDITIONS_UNMET"
    assert env.world.mutating() == []
    assert env.world.tags[ACTIVE_TAG] == ROLLBACK_ID
    assert env.world.container == {"image": ROLLBACK_ID, "config": ACTIVE_TAG}
    assert not env.marker.exists()
    env.world.http_status = 200  # positive control on the same fixture
    _happy(env)


def test_existing_private_root_with_loose_mode_refuses_before_the_stop(env):
    env.failures.mkdir(mode=0o755)
    env.failures.chmod(0o755)
    rc, lines, _ = env.run("--apply")
    assert rc == 1 and _code(lines) == "FAILURES_ROOT_UNSAFE"
    assert env.world.mutating() == [] and not env.marker.exists()
    env.failures.chmod(0o700)  # positive control
    _happy(env)


# ---------------------------------------------------------------------------
# T019 / T020 — the happy path
# ---------------------------------------------------------------------------


def test_apply_cuts_over_in_order_and_records_success(env, monkeypatch):
    seen = {}
    real_snapshot = mod.dbsafety.snapshot

    def spy(*args, **kwargs):  # INV-2: the copy starts only with the lock held
        seen["calls_before"] = len(env.world.calls)
        seen["container"] = env.world.container
        seen["active"] = env.world.tags.get(ACTIVE_TAG)
        seen["marker_phase"] = env.marker_data()["phase"]
        return real_snapshot(*args, **kwargs)

    monkeypatch.setattr(mod.dbsafety, "snapshot", spy)
    lines = _happy(env)
    w = env.world
    assert lines[0] == (f"ACTIVATE_VERIFIED release_version={RELEASE_VERSION} config_digest={RELEASE_ID} "
                        f"pre_version={PRE_VERSION} outage_seconds=0")
    assert [a[1:] for a in w.mutating()] == [
        ["compose", "-f", str(env.compose), "down"],
        ["image", "rm", ACTIVE_TAG],
        ["tag", RELEASE_ID, ACTIVE_TAG],
        ["compose", "-f", str(env.compose), "up", "-d"],
    ]
    assert seen == {"calls_before": seen["calls_before"], "container": None, "active": None,
                    "marker_phase": "stopped"}
    rm_at = _last_index(w, ["image", "rm"])
    assert seen["calls_before"] > rm_at
    # End state: the release runs under `active`; both images kept.
    assert w.container == {"image": RELEASE_ID, "config": ACTIVE_TAG}
    assert w.tags == {ROLLBACK_REF: ROLLBACK_ID, RELEASE_TAG: RELEASE_ID, ACTIVE_TAG: RELEASE_ID}
    assert_inv1(w)
    marker = env.marker_data()
    assert marker["phase"] == "verified" and marker["outcome"] == "success"
    assert marker["pre_version"] == PRE_VERSION and marker["tasks_before"] == 12
    assert marker["config_digest"] == RELEASE_ID and marker["rollback_image_id"] == ROLLBACK_ID
    snap = json.loads((Path(marker["snapshot_dir"]) / "snapshot.json").read_text())
    assert snap["pre_version"] == PRE_VERSION and snap["running_image_id"] == ROLLBACK_ID
    assert snap["db_sha256"] == marker["snapshot_sha"] and snap["tasks_count"] == 12
    assert f"ACTIVATE_SNAPSHOT snapshot_dir={marker['snapshot_dir']} db_sha256={snap['db_sha256']} " \
           f"tasks_before=12" in lines
    assert ("ACTIVATE_MIGRATION processed=7 converted=5 already_rrule=1 unconvertible=1 server_zone=2"
            in lines)
    for phase in ("stopped", "snapshotted", "retagged", "started_new", "verified"):
        assert f"ACTIVATE_STEP phase={phase}" in lines
    # Private folders: 0700; the verify log is kept privately.
    for root in (env.activation, env.snapshots, env.failures):
        assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert MIGRATED_LOG in Path(marker["verify_log"]).read_text()
    assert w.log_argv == [["docker", "logs", "--timestamps", "--tail", "20000", "vikunja"]]


def test_every_subprocess_call_is_time_bounded(env):
    _happy(env)
    for argv, kwargs in env.world.calls:
        t = kwargs["timeout"]
        if argv[:2] == ["docker", "compose"]:
            assert t <= 120
        elif argv[0] == "curl":
            assert t <= 7 and "--max-time" in argv
        else:
            assert t <= 30, argv


# ---------------------------------------------------------------------------
# T018 — marker and replay
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["--dry-run", "--apply"])
def test_success_replay_reconciles_read_only(env, mode):
    _happy(env)
    env.world.calls.clear()
    before = _fs(env)
    rc, lines, _ = env.run(mode)
    assert _fs(env) == before
    assert rc == 0, lines
    assert lines[0] == f"ACTIVATE_ALREADY_VERIFIED release_version={RELEASE_VERSION} config_digest={RELEASE_ID}"
    assert env.world.verbs() == {("container", "inspect"), ("curl",)}
    assert env.world.mutating() == []


@pytest.mark.parametrize("break_it", [
    _set("world.container", {"image": ROLLBACK_ID, "config": ACTIVE_TAG}),
    _set("world.container", None),
    lambda env: env.world.versions.__setitem__(RELEASE_ID, "v2.7.0"),
    lambda env: (env.world.versions.__setitem__(OTHER_ID, RELEASE_VERSION),
                 env.world.__setattr__("container", {"image": OTHER_ID, "config": ACTIVE_TAG})),
], ids=["running-rollback", "no-container", "wrong-version", "right-version-wrong-image"])
@pytest.mark.parametrize("mode", ["--dry-run", "--apply"])
def test_success_replay_that_does_not_reconcile_fails(env, mode, break_it):
    _happy(env)
    env.world.calls.clear()
    assert env.run(mode)[0] == 0  # positive control on the same fixture
    break_it(env)
    env.world.calls.clear()
    before = _fs(env)
    rc, lines, _ = env.run(mode)
    assert _fs(env) == before, "a failed replay writes nothing, not even a private log"
    assert rc == 1 and _code(lines) == "ACTIVATE_SUCCESS_NOT_RECONCILED"
    assert lines[0] == "FAILED code=ACTIVATE_SUCCESS_NOT_RECONCILED private_log=-"
    assert env.world.mutating() == []
    assert env.world.verbs() <= {("container", "inspect"), ("curl",)}


@pytest.mark.parametrize("mode", ["--dry-run", "--apply"])
@pytest.mark.parametrize("marker, code", [
    ({"phase": "verified", "outcome": "rolled_back"}, "ACTIVATE_ROLLED_BACK_REMOVE_QUEUED_MANIFEST"),
    ({"phase": "started"}, "ACTIVATE_PRIOR_ATTEMPT_STARTED"),
    ({"phase": "stopped"}, "ACTIVATE_PRIOR_ATTEMPT_STOPPED"),
    ({"phase": "retagged", "outcome": "failed", "failed_phase": "started_new", "error": "READY_TIMEOUT"},
     "ACTIVATE_PRIOR_ATTEMPT_RETAGGED"),
    ({"phase": "started_new", "outcome": "failed", "failed_phase": "verified"},
     "ACTIVATE_PRIOR_ATTEMPT_STARTED_NEW"),
])
def test_non_success_marker_refuses_with_no_docker_call(env, mode, marker, code):
    assert env.run("--dry-run")[0] == 0  # positive control: same fixture, no marker
    env.world.calls.clear()
    env.write_marker(**marker)
    before = env.marker.read_bytes()
    tree = _fs(env)
    rc, lines, _ = env.run(mode)
    assert _fs(env) == tree
    assert rc == 1 and _code(lines) == code
    assert env.world.calls == []
    assert env.marker.read_bytes() == before  # never rewritten by a replay


@pytest.mark.parametrize("mode", ["--dry-run", "--apply"])
def test_malformed_marker_refuses_with_no_docker_call(env, mode):
    env.make_lock_file()
    env.marker.write_text("{not json", encoding="utf-8")
    tree = _fs(env)
    rc, lines, _ = env.run(mode)
    assert _fs(env) == tree
    assert rc == 1 and _code(lines) == "MARKER_UNREADABLE"
    assert env.world.calls == []
    env.marker.unlink()  # positive control
    assert env.run(mode)[0] == 0


def test_marker_is_created_before_the_stop(env):
    seen = {}

    def watch(argv):
        if argv[:2] == ["docker", "compose"] and argv[-1] == "down" and "marker" not in seen:
            seen["marker"] = env.marker_data()

    env.world.pre_hook = watch
    _happy(env)
    assert seen["marker"]["phase"] == "started" and seen["marker"]["outcome"] is None
    assert seen["marker"]["pre_version"] == PRE_VERSION


# ---------------------------------------------------------------------------
# T021 — failure after `down`: lock held, no container, marker failed, INV-1
# ---------------------------------------------------------------------------


def _fail(verb, *modes):
    return lambda env: env.world.fail.__setitem__(verb, list(modes))


def _corrupt_db_on_down(env):
    def corrupt():
        (env.data / "vikunja.db").write_bytes(b"not a database" * 100)
    env.world.on_down = corrupt


FAILURES = [
    # (id, break, code, failed_phase, container-existed-at-cleanup)
    ("down-rc", _fail(("compose", "down"), "rc"), "ACTIVATE_COMPOSE_DOWN_FAILED", "stopped", True),
    ("down-timeout", _fail(("compose", "down"), "timeout"), "TIMEOUT_COMPOSE_DOWN", "stopped", True),
    ("untag-rc", _fail(("image", "rm"), "rc"), "ACTIVATE_UNTAG_FAILED", "snapshotted", False),
    ("untag-timeout", _fail(("image", "rm"), "timeout"), "TIMEOUT_DOCKER_UNTAG", "snapshotted", False),
    ("snapshot", _corrupt_db_on_down, "SNAPSHOT_INTEGRITY_FAILED", "snapshotted", False),
    ("tag-rc", _fail(("tag",), "rc"), "ACTIVATE_TAG_ACTIVE_FAILED", "retagged", False),
    ("tag-timeout", _fail(("tag",), "timeout"), "TIMEOUT_DOCKER_TAG", "retagged", False),
    ("up-rc", _fail(("compose", "up"), "rc"), "ACTIVATE_COMPOSE_UP_FAILED", "started_new", False),
    ("up-timeout", _fail(("compose", "up"), "timeout"), "TIMEOUT_COMPOSE_UP", "started_new", False),
    # A partial start: `up` created and started the container, then timed out.
    ("up-partial-start", _fail(("compose", "up"), "effect_timeout"), "TIMEOUT_COMPOSE_UP", "started_new", True),
    ("wrong-image", _set("world.up_image", OTHER_ID), "ACTIVATE_CONTAINER_IMAGE_WRONG", "verified", True),
    ("wrong-version", lambda env: env.world.versions.__setitem__(RELEASE_ID, "v2.7.0"),
     "READY_WRONG_VERSION", "verified", True),
    ("not-ready", _set("world.release_http_status", 503), "READY_TIMEOUT", "verified", True),
    ("migration-log-missing", lambda env: env.world.logs.__setitem__(RELEASE_ID, UNMIGRATED_LOG),
     "ACTIVATE_MIGRATION_LOG_MISSING", "verified", True),
    ("logs-not-captured", _set("world.popen_raises", OSError("no docker")),
     "ACTIVATE_LOGS_NOT_CAPTURED", "verified", True),
]


@pytest.mark.parametrize("name, break_it, code, failed_phase, had_container", FAILURES,
                         ids=[f[0] for f in FAILURES])
def test_failure_after_down_ends_locked_with_marker_failed(tmp_path, name, break_it, code, failed_phase,
                                                           had_container):
    control = Env(tmp_path / "control")  # the happy path is the positive control
    _happy(control)
    assert control.marker_data()["outcome"] == "success"

    env = Env(tmp_path / "case")
    break_it(env)
    rc, lines, err = env.run("--apply")
    assert rc == 1, lines
    assert _code(lines) == code
    marker = assert_lock_held_end_state(env, code, failed_phase)
    assert any(l.startswith("ACTIVATE_CLEANUP lock_code=HELD") for l in lines), lines
    # Never starts 2.4.0: the only `up` (if any) ran with `active` on the release.
    ups = [i for i, (a, _) in enumerate(env.world.calls) if a[1:2] == ["compose"] and a[-1] == "-d"]
    assert len(ups) <= 1
    # Evidence before teardown (R-14): logs captured iff a container existed.
    if had_container and name != "logs-not-captured":
        assert marker["failure_log"] and Path(marker["failure_log"]).parent == env.failures
        cleanup_down = [i for i, (a, _) in enumerate(env.world.calls) if a[-1:] == ["down"]][-1]
        assert env.world.log_argv, "logs captured before the cleanup down"
        assert cleanup_down > 0
    elif not had_container:
        assert marker.get("failure_log") is None
    out = "\n".join(lines) + err + env.marker.read_text()
    for leak in LEAKS:
        assert leak not in out


def test_cleanup_captures_logs_before_its_down(env, monkeypatch):
    order = []
    real_capture = mod.readiness.capture_logs

    def capture(*a, **k):
        order.append(("logs", env.world.container is not None))
        return real_capture(*a, **k)

    monkeypatch.setattr(mod.readiness, "capture_logs", capture)
    env.world.logs[RELEASE_ID] = UNMIGRATED_LOG
    rc, lines, _ = env.run("--apply")
    assert rc == 1 and _code(lines) == "ACTIVATE_MIGRATION_LOG_MISSING"
    # verify capture, then the cleanup capture, both while the container exists
    assert order == [("logs", True), ("logs", True)]
    assert env.world.container is None


@pytest.mark.parametrize("down_mode", ["rc", "timeout"])
def test_cleanup_down_failing_with_a_running_rejected_release_is_reported_honestly(tmp_path, down_mode):
    """The rejected release is RUNNING when the cleanup's own `down` fails.
    The end state is reported as it is (container PRESENT, CLEANUP_* codes);
    the lock is still taken and nothing ever tags `active` to 2.4.0."""
    control = Env(tmp_path / "control")
    _happy(control)
    env = Env(tmp_path / "case")
    env.world.versions[RELEASE_ID] = "v2.7.0"  # verification rejects the release
    env.world.fail[("compose", "down")] = ["ok", down_mode]  # the cleanup's down fails
    rc, lines, _ = env.run("--apply")
    assert rc == 1 and _code(lines) == "READY_WRONG_VERSION"
    w = env.world
    assert w.container == {"image": RELEASE_ID, "config": ACTIVE_TAG}  # still running, as reported
    assert ACTIVE_TAG not in w.tags  # the lock is taken: a restart after removal fails closed
    assert ROLLBACK_ID in w.images and w.tags[ROLLBACK_REF] == ROLLBACK_ID
    assert_inv1(w)
    marker = env.marker_data()
    assert marker["outcome"] == "failed" and marker["error"] == "READY_WRONG_VERSION"
    assert marker["cleanup_code"] == "CLEANUP_DOWN_FAILED"
    assert marker["failure_log"] and Path(marker["failure_log"]).exists()
    cleanup = [l for l in lines if l.startswith("ACTIVATE_CLEANUP ")]
    assert cleanup == [f"ACTIVATE_CLEANUP lock_code=HELD container_code=PRESENT "
                       f"cleanup_code=CLEANUP_DOWN_FAILED problems=2 private_log={marker['failure_log']}"]


def test_internal_error_after_down_still_cleans_up(env, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError(f"unexpected {SECRET}")

    monkeypatch.setattr(mod.dbsafety, "snapshot", boom)
    rc, lines, err = env.run("--apply")
    assert rc == 1 and _code(lines) == "ACTIVATE_INTERNAL_ERROR"
    assert_lock_held_end_state(env, "ACTIVATE_INTERNAL_ERROR", "snapshotted")
    assert SECRET not in "\n".join(lines) + err
    logs = sorted(env.failures.iterdir())
    assert any(SECRET in p.read_text() for p in logs)  # traceback kept privately


def test_replay_after_failure_never_restarts(env):
    env.world.fail[("compose", "up")] = ["rc"]
    assert env.run("--apply")[0] == 1
    env.world.calls.clear()
    rc, lines, _ = env.run("--apply")
    assert rc == 1 and _code(lines) == "ACTIVATE_PRIOR_ATTEMPT_RETAGGED"
    assert env.world.calls == []
    assert ACTIVE_TAG not in env.world.tags and env.world.container is None


# ---------------------------------------------------------------------------
# T022 — outage deadline and privacy
# ---------------------------------------------------------------------------


def test_outage_deadline_crossed_mid_readiness(tmp_path):
    control = Env(tmp_path / "control")
    control.world.cost[("compose", "up")] = 60.0
    control.world.cost[("compose", "down")] = 60.0
    lines = _happy(control)
    assert "outage_seconds=120" in lines[0]

    env = Env(tmp_path / "case")
    env.world.cost[("compose", "down")] = 60.0
    env.world.cost[("compose", "up")] = 110.0  # 170 s gone; readiness gets 130 s, not 180
    env.world.release_http_status = 503
    rc, lines, _ = env.run("--apply")
    assert rc == 1 and _code(lines) == "ACTIVATE_OUTAGE_DEADLINE"
    assert_lock_held_end_state(env, "ACTIVATE_OUTAGE_DEADLINE", "verified")


class Timing:
    """Record when the outage window and the cleanup start (fake clock)."""

    def __init__(self, env: Env, monkeypatch, *, after_down_cost: float | None = None,
                 cleanup_cost: float | None = None):
        self.env = env
        self.outage_start: float | None = None
        self.cleanup_start: float | None = None
        self.cleanup_index: int | None = None

        def hook(argv):
            if self.outage_start is None and argv[:2] == ["docker", "compose"] and argv[-1] == "down":
                self.outage_start = env.clock.t
                if after_down_cost is not None:
                    env.world.default_cost = after_down_cost
        env.world.pre_hook = hook
        real = mod.Activate._cleanup

        def cleanup(run, code):
            self.cleanup_start = env.clock.t
            self.cleanup_index = len(env.world.timeline)
            if cleanup_cost is not None:
                env.world.default_cost = cleanup_cost
                env.world.cost.clear()
            return real(run, code)
        monkeypatch.setattr(mod.Activate, "_cleanup", cleanup)

    def assert_budgets(self) -> None:
        line = self.env.world.timeline
        outage_end = self.outage_start + mod.OUTAGE_S
        for verb, start, timeout in line[:self.cleanup_index]:
            if start >= self.outage_start:
                assert start + timeout <= outage_end + 1e-6, (verb, start, timeout)
        cleanup_end = self.cleanup_start + mod.CLEANUP_BUDGET_S
        for verb, start, timeout in line[self.cleanup_index:]:
            assert start + timeout <= cleanup_end + 1e-6, (verb, start, timeout)
        assert self.cleanup_start <= outage_end + 1e-6
        assert self.env.clock.t - self.cleanup_start <= mod.CLEANUP_BUDGET_S + 1e-6


def test_realistic_cumulative_outage_exhaustion(tmp_path, monkeypatch):
    """Every call takes real time within its own timeout; the total runs out
    mid-cutover. No call's timeout reaches past the 300 s window, the failure
    is ACTIVATE_OUTAGE_DEADLINE, and the cleanup stays inside 120 s."""
    control = Env(tmp_path / "control")  # same costs, but a shorter `down`: it fits
    control.world.cost[("curl",)] = 1.0
    t_control = Timing(control, monkeypatch, after_down_cost=28.0)
    control.world.cost[("compose", "down")] = 40.0
    lines = _happy(control)
    assert t_control.cleanup_start is None and "outage_seconds=" in lines[0]
    assert int(lines[0].rsplit("outage_seconds=", 1)[1]) <= 300

    env = Env(tmp_path / "case")
    env.world.cost[("curl",)] = 1.0
    timing = Timing(env, monkeypatch, after_down_cost=28.0, cleanup_cost=28.0)
    env.world.cost[("compose", "down")] = 100.0
    rc, lines, _ = env.run("--apply")
    assert rc == 1 and _code(lines) == "ACTIVATE_OUTAGE_DEADLINE"
    timing.assert_budgets()
    assert env.clock.t - timing.outage_start <= mod.OUTAGE_S + mod.CLEANUP_BUDGET_S + 1e-6
    marker = env.marker_data()
    assert marker["outcome"] == "failed" and marker["error"] == "ACTIVATE_OUTAGE_DEADLINE"
    assert ACTIVE_TAG not in env.world.tags and env.world.container is None
    assert_inv1(env.world)


@pytest.mark.parametrize("down_s, snapshot_s", [(30.0, 10.0), (120.0, 70.0)], ids=["control-fits", "window-spent"])
def test_outage_spent_before_up_never_starts_anything(env, monkeypatch, down_s, snapshot_s):
    """A slow `down`, slow inspections and a slow snapshot: once the window
    is spent, no further call is made (the tag is never attempted)."""
    timing = Timing(env, monkeypatch)
    env.world.cost[("compose", "down")] = down_s
    for verb in (("image", "inspect"), ("container", "inspect"), ("image", "rm")):
        env.world.cost[verb] = 29.0
    real_snapshot = mod.dbsafety.snapshot

    def slow_snapshot(*a, **k):
        result = real_snapshot(*a, **k)
        env.clock.t += min(snapshot_s, k["deadline"].remaining())  # bounded by its own deadline
        return result

    monkeypatch.setattr(mod.dbsafety, "snapshot", slow_snapshot)
    rc, lines, _ = env.run("--apply")
    if snapshot_s == 10.0:
        assert rc == 0, lines  # positive control: 30 + 4*29 + 10 + 2*29 fits in 300
        return
    assert rc == 1 and _code(lines) == "ACTIVATE_OUTAGE_DEADLINE"
    timing.assert_budgets()
    assert not any(a[:2] == ["docker", "tag"] for a, _ in env.world.calls)
    assert not any(a[-1:] == ["-d"] for a, _ in env.world.calls)
    assert_lock_held_end_state(env, "ACTIVATE_OUTAGE_DEADLINE", "retagged")


@pytest.mark.parametrize("cleanup_cost", [10.0, 1e9], ids=["slow-control", "every-call-hangs"])
def test_cleanup_stays_inside_its_budget_with_the_untag_reserve(tmp_path, monkeypatch, cleanup_cost):
    """A partial start leaves the rejected release running. With slow calls
    (the positive control) cleanup removes it and takes the lock; with every
    call hanging, cleanup still ends inside 120 s and the untag reserve still
    lets the untag start. Since RISK-3 the untag first proves (one bounded
    inspection) that ``active``'s image keeps another name; when even that
    hangs, no ``image rm`` is risked and an unconfirmed lock is reported,
    never assumed."""
    env = Env(tmp_path / "case")
    timing = Timing(env, monkeypatch, cleanup_cost=cleanup_cost)
    env.world.fail[("compose", "up")] = ["effect_timeout"]
    rc, lines, _ = env.run("--apply")
    assert rc == 1 and _code(lines) == "TIMEOUT_COMPOSE_UP"
    timing.assert_budgets()
    assert env.marker_data()["outcome"] == "failed"
    assert_inv1(env.world)
    cleanup_calls = [a for a, _ in env.world.calls[timing.cleanup_index:]]
    proof = [a for a in cleanup_calls if a[:5] == ["docker", "image", "inspect", "--format",
                                                    mod.dbsafety.UNTAG_INSPECT_FORMAT]]
    assert proof  # the reserve let the untag start, with its safety proof first
    rm = [a for a in cleanup_calls if a[:3] == ["docker", "image", "rm"]]
    line = [l for l in lines if l.startswith("ACTIVATE_CLEANUP ")][0]
    if cleanup_cost < 30:
        assert rm and cleanup_calls.index(proof[0]) < cleanup_calls.index(rm[0])
        assert_lock_held_end_state(env, "TIMEOUT_COMPOSE_UP", "started_new")
        assert line.startswith("ACTIVATE_CLEANUP lock_code=HELD container_code=ABSENT cleanup_code=- ")
    else:
        assert rm == []  # the proof hung: nothing is removed on an unproven image
        assert "lock_code=NOT_CONFIRMED" in line and "container_code=UNKNOWN" in line


# ---------------------------------------------------------------------------
# Crash boundaries: the process dies right after each marker phase is durable
# ---------------------------------------------------------------------------


class Crash(BaseException):
    """A process death: not an Exception, so no cleanup runs."""


@pytest.mark.parametrize("phase", ["started", "stopped", "snapshotted", "retagged", "started_new", "verified"])
def test_crash_after_each_phase_then_replay_is_inert(env, monkeypatch, phase):
    real_create, real_update = mod.core.marker_create, mod.core.marker_update

    def create(path, data):
        real_create(path, data)
        if phase == "started":
            raise Crash()

    def update(path, data):
        real_update(path, data)
        if data["phase"] == phase:
            raise Crash()

    monkeypatch.setattr(mod.core, "marker_create", create)
    monkeypatch.setattr(mod.core, "marker_update", update)
    with pytest.raises(Crash):
        env.run("--apply")
    monkeypatch.undo()
    assert env.marker_data()["phase"] == phase
    assert_inv1(env.world)
    if phase == "stopped":  # R-21: `stopped` is durable before the untag
        assert ACTIVE_TAG in env.world.tags and env.world.container is None
    for mode in ("--dry-run", "--apply"):
        env.world.calls.clear()
        tree = _fs(env)
        tags, container = dict(env.world.tags), env.world.container
        rc, lines, _ = env.run(mode)
        assert _fs(env) == tree
        assert env.world.tags == tags and env.world.container == container
        if phase == "verified":
            assert rc == 0 and lines[0].startswith("ACTIVATE_ALREADY_VERIFIED ")
            assert env.world.verbs() == {("container", "inspect"), ("curl",)}
        else:
            assert rc == 1 and _code(lines) == f"ACTIVATE_PRIOR_ATTEMPT_{phase.upper()}"
            assert env.world.calls == []


def test_stopped_is_recorded_before_the_untag(env):
    seen = {}

    def hook(argv):
        if argv[:3] == ["docker", "image", "rm"] and "phase" not in seen:
            seen["phase"] = env.marker_data()["phase"]
            seen["container"] = env.world.container
    env.world.pre_hook = hook
    _happy(env)
    assert seen == {"phase": "stopped", "container": None}


@pytest.mark.parametrize("mode", ["--dry-run", "--apply"])
def test_seeded_text_never_reaches_stdout_stderr_or_the_marker(env, mode):
    env.world.fail[("compose", "up")] = ["rc"]
    rc, lines, err = env.run(mode)
    text = "\n".join(lines) + err + (env.marker.read_text() if env.marker.exists() else "")
    for leak in LEAKS:
        assert leak not in text
    assert "REDACTED" not in text
    for line in lines:
        assert line.split()[0] in core.registered_summaries(), line


def test_every_line_is_allowlisted_on_the_happy_path(env):
    lines = _happy(env)
    for line in lines:
        assert line.split()[0] in core.registered_summaries(), line
        assert "REDACTED" not in line
    for leak in LEAKS:
        assert leak not in "\n".join(lines)


# ---------------------------------------------------------------------------
# Activation lock (WP06 review, CRITICAL)
# ---------------------------------------------------------------------------

_HOLDER = (
    "import fcntl, os, sys\n"
    "fd = os.open(sys.argv[1], os.O_CREAT | os.O_RDWR, 0o600)\n"
    "fcntl.flock(fd, fcntl.LOCK_EX)\n"
    "print('held', flush=True)\n"
    "sys.stdin.read()\n"
)


def _hold_lock(path: Path) -> subprocess.Popen:
    """Another process (as a racing rollback helper would be) holding the lock."""
    proc = subprocess.Popen([sys.executable, "-c", _HOLDER, str(path)], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, text=True)
    assert proc.stdout.readline().strip() == "held"
    return proc


def _release(proc: subprocess.Popen) -> None:
    proc.stdin.close()
    proc.wait(timeout=10)


def _lock_is_held_elsewhere(path: Path) -> bool:
    fd = os.open(path, os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return True
    finally:
        os.close(fd)
    return False


@pytest.mark.parametrize("mode", ["--dry-run", "--apply"])
@pytest.mark.parametrize("with_marker", [False, True], ids=["fresh", "replay"])
def test_lock_held_by_another_process_refuses_with_no_call_and_no_write(env, mode, with_marker):
    lock = env.make_lock_file()
    if with_marker:
        env.write_marker(phase="stopped")
    holder = _hold_lock(lock)
    try:
        tree = _fs(env)
        rc, lines, err = env.run(mode)
        assert rc == 1 and _code(lines) == "ACTIVATE_LOCK_BUSY", lines
        assert lines[0] == "FAILED code=ACTIVATE_LOCK_BUSY private_log=-"
        assert env.world.calls == []
        assert _fs(env) == tree
        assert env.world.tags[ACTIVE_TAG] == ROLLBACK_ID
    finally:
        _release(holder)
    # Positive control: the same fixture with the lock free proceeds.
    rc, lines, _ = env.run(mode)
    if with_marker:
        assert rc == 1 and _code(lines) == "ACTIVATE_PRIOR_ATTEMPT_STOPPED"
    else:
        assert rc == 0, lines
    assert not _lock_is_held_elsewhere(lock)  # released when the run ended


def test_dry_run_probes_the_lock_without_creating_it(env):
    rc, lines, _ = env.run("--dry-run")
    assert rc == 0
    assert f"ACTIVATION_LOCK_FREE lock={env.activation / mod.ACTIVATION_LOCK_NAME}" in lines
    assert not env.activation.exists()


def test_apply_creates_the_lock_file_private_and_relative_to_the_verified_root(env):
    _happy(env)
    lock = env.activation / mod.ACTIVATION_LOCK_NAME
    st = lock.lstat()
    assert stat.S_ISREG(st.st_mode) and stat.S_IMODE(st.st_mode) == 0o600


def test_symlinked_lock_file_is_refused(env, tmp_path):
    env.activation.mkdir(mode=0o700)
    target = tmp_path / "elsewhere"
    target.write_text("")
    (env.activation / mod.ACTIVATION_LOCK_NAME).symlink_to(target)
    rc, lines, _ = env.run("--apply")
    assert rc == 1 and _code(lines) == "ACTIVATE_LOCK_UNAVAILABLE"
    assert env.world.calls == []
    (env.activation / mod.ACTIVATION_LOCK_NAME).unlink()  # positive control
    _happy(env)


@pytest.mark.parametrize("break_it", [None, _fail(("compose", "up"), "effect_timeout")],
                         ids=["happy", "failure-and-cleanup"])
def test_lock_is_held_at_every_docker_call_including_cleanup(env, break_it):
    lock = env.activation / mod.ACTIVATION_LOCK_NAME
    probes: list[tuple[list[str], bool]] = []

    def probe(argv):
        if argv[0] == "docker":
            probes.append((list(argv), _lock_is_held_elsewhere(lock)))
    env.world.pre_hook = probe
    if break_it is not None:
        break_it(env)
    rc, lines, _ = env.run("--apply")
    assert rc == (0 if break_it is None else 1), lines
    assert probes and all(held for _, held in probes), [a for a, h in probes if not h]
    if break_it is not None:
        cleanup_calls = [a for a, _ in probes if a[-1:] == ["down"]]
        assert len(cleanup_calls) == 2  # the cutover's down and the cleanup's down, both under the lock
    assert not _lock_is_held_elsewhere(lock)


@pytest.mark.parametrize("mode", ["--dry-run", "--apply"])
@pytest.mark.parametrize("kind", ["daemon-error", "unexpected-exception"])
def test_replay_errors_write_no_private_log(env, mode, kind):
    """A reconcile that errors (inspection daemon error, or an unexpected
    exception) is still read-only: no traceback or detail file is written."""
    _happy(env)
    assert env.run(mode)[0] == 0  # positive control: the same fixture reconciles
    if kind == "daemon-error":
        env.world.fail[("container", "inspect")] = ["rc"]
        code = "ACTIVATE_SUCCESS_NOT_RECONCILED"
    else:
        def boom(argv):
            if argv[0] == "docker":
                raise RuntimeError(f"unexpected {SECRET}")
        env.world.pre_hook = boom
        code = "ACTIVATE_REPLAY_INTERNAL_ERROR"
    tree = _fs(env)
    rc, lines, err = env.run(mode)
    assert rc == 1 and lines[0] == f"FAILED code={code} private_log=-"
    assert _fs(env) == tree
    assert SECRET not in "\n".join(lines) + err



# ---------------------------------------------------------------------------
# Log capture plus its reap stay inside the enclosing deadline (cycle 2)
# ---------------------------------------------------------------------------


class CaptureTiming:
    """Wrap readiness.capture_logs around a REAL child (the world's popen).
    While it is waited on, the fake clock advances with each read; the
    capture is then charged min(elapsed, its timeout) plus the worst-case
    reap allowance (readiness._stop's own 5 s wait). Records each capture's
    (start, end-including-reap, timeout)."""

    def __init__(self, env: Env, monkeypatch, step: float = 3.0):
        self.windows: list[tuple[float, float, float]] = []
        real = mod.readiness.capture_logs

        def capture(popen, container, dest, *, timeout, clock, **kw):
            start = env.clock.t
            env.clock.auto_step = step
            try:
                return real(popen, container, dest, timeout=timeout, clock=clock, **kw)
            finally:
                env.clock.auto_step = 0.0
                env.clock.t = start + min(env.clock.t - start, timeout) + mod.READINESS_REAP_ALLOWANCE_S
                self.windows.append((start, env.clock.t, timeout))
        monkeypatch.setattr(mod.readiness, "capture_logs", capture)


@pytest.mark.parametrize("down_s, up_s, inspect_s, hang, expect", [
    # control: time to spare; the log child exits; capture + reap well inside 300 s
    (60.0, 60.0, 0.0, False, "success"),
    # 119 + 119 + 2*20 + 1 = 279 s gone: 21 s left, the child hangs; capture gets 15 s
    (119.0, 119.0, 20.0, True, "ACTIVATE_LOGS_NOT_CAPTURED"),
    # 119 + 119 + 2*29 + 1 = 297 s gone: 3 s left, no room for capture + reap: skipped
    (119.0, 119.0, 29.0, True, "ACTIVATE_LOGS_NOT_CAPTURED"),
], ids=["control-time-to-spare", "hanging-child-near-end", "no-room-skips-capture"])
def test_log_capture_and_reap_fit_inside_the_outage_and_cleanup(tmp_path, monkeypatch, down_s, up_s,
                                                                inspect_s, hang, expect):
    env = Env(tmp_path / "case")
    timing = Timing(env, monkeypatch)
    captures = CaptureTiming(env, monkeypatch)
    env.world.cost[("compose", "down")] = down_s
    env.world.cost[("compose", "up")] = up_s
    env.world.cost[("container", "inspect")] = inspect_s
    env.world.cost[("curl",)] = 1.0
    env.world.log_hang = hang
    rc, lines, _ = env.run("--apply")
    outage_end = timing.outage_start + mod.OUTAGE_S
    if expect == "success":
        assert rc == 0, lines
        [(start, end, timeout)] = captures.windows
        assert timeout == mod.LOGS_TIMEOUT_S and end <= outage_end
        return
    assert rc == 1 and _code(lines) == expect, lines
    assert timing.cleanup_start is not None
    assert timing.cleanup_start <= outage_end + 1e-6, "cleanup's first call starts inside the 300 s window"
    timing.assert_budgets()
    cutover = [w for w in captures.windows if w[0] < timing.cleanup_start]
    cleanup = [w for w in captures.windows if w[0] >= timing.cleanup_start]
    if inspect_s == 29.0:
        assert cutover == []  # skipped: under 6 s left
    else:
        [(start, end, timeout)] = cutover
        assert 0 < timeout <= outage_end - start - mod.READINESS_REAP_ALLOWANCE_S - mod.LOGS_REAP_MARGIN_S + 1e-6
        assert end <= outage_end + 1e-6, "capture plus reap end inside the outage window"
    [(start, end, timeout)] = cleanup  # the rejected container's logs, still captured
    cleanup_end = timing.cleanup_start + mod.CLEANUP_BUDGET_S
    assert end <= cleanup_end - mod.CLEANUP_UNTAG_RESERVE_S + 1e-6, "the untag reserve is protected"
    assert env.clock.t - timing.cleanup_start <= mod.CLEANUP_BUDGET_S + 1e-6
    assert ("image", "rm") in [v for v, _, _ in env.world.timeline[timing.cleanup_index:]]
    assert ACTIVE_TAG not in env.world.tags
    assert env.marker_data()["outcome"] == "failed"
    assert_inv1(env.world)


@pytest.mark.parametrize("budget_s", [120.0, 70.0], ids=["control-full-budget", "tight-budget"])
def test_cleanup_log_capture_never_eats_the_untag_reserve(tmp_path, monkeypatch, budget_s):
    """With the real 120 s budget the reap allowance always fits; with a tight
    budget (patched to 70 s) only 6 s is left beyond the reserve after a slow
    inspection, which cannot hold capture + reap: the capture is skipped and
    the untag keeps its full reserve."""
    monkeypatch.setattr(mod, "CLEANUP_BUDGET_S", budget_s)
    env = Env(tmp_path / "case")
    timing = Timing(env, monkeypatch, cleanup_cost=29.0)
    captures = CaptureTiming(env, monkeypatch)
    env.world.log_hang = True
    env.world.fail[("compose", "up")] = ["effect_timeout"]  # rejected release running
    rc, lines, _ = env.run("--apply")
    assert rc == 1 and _code(lines) == "TIMEOUT_COMPOSE_UP"
    timing.assert_budgets()
    cleanup = [w for w in captures.windows if w[0] >= timing.cleanup_start]
    reserve_starts = timing.cleanup_start + budget_s - mod.CLEANUP_UNTAG_RESERVE_S
    for start, end, timeout in cleanup:
        assert end <= reserve_starts + 1e-6
    if budget_s == 120.0:
        assert len(cleanup) == 1  # positive control: there was room, so it captured
    else:
        assert cleanup == []
        assert "CLEANUP_LOGS_NOT_CAPTURED" in env.marker_data()["cleanup_code"]
    # The untag (its safety proof, then the removal) ran inside its reserve.
    timeline = env.world.timeline[timing.cleanup_index:]
    calls = [a for a, _ in env.world.calls[timing.cleanup_index:]]
    proof = [t[1] for t, a in zip(timeline, calls) if a[-2:] == [mod.dbsafety.UNTAG_INSPECT_FORMAT, ACTIVE_TAG]]
    rm = [(s_, to) for v, s_, to in timeline if v == ("image", "rm")]
    assert proof and proof[0] <= reserve_starts + 1e-6
    assert rm and rm[0][0] + rm[0][1] <= timing.cleanup_start + budget_s + 1e-6
    assert_inv1(env.world)


# ---------------------------------------------------------------------------
# RISK-3: the untag only ever removes a tag, never an image
# ---------------------------------------------------------------------------


def test_cutover_untag_refuses_when_the_rollback_image_would_lose_its_last_name(env):
    """The rollback ref disappears after the preconditions (between the
    checks and the stop): `active` is then the image's only name, and
    `docker image rm active` would delete 2.4.0 itself. ACTIVATE refuses
    before any image rm, in the cutover and again in cleanup."""

    def drop_ref():
        env.world.tags.pop(ROLLBACK_REF, None)

    env.world.on_down = drop_ref
    rc, lines, _ = env.run("--apply")
    assert rc == 1 and _code(lines) == "ACTIVATE_UNTAG_UNSAFE", lines
    assert not any(a[:3] == ["docker", "image", "rm"] for a, _ in env.world.calls)
    assert env.world.tags[ACTIVE_TAG] == ROLLBACK_ID  # the image keeps its one name
    assert ROLLBACK_ID in env.world.images
    assert env.marker_data()["outcome"] == "failed"
    assert not any(a[:2] == ["docker", "tag"] for a, _ in env.world.calls)


def test_cutover_untag_control_with_the_ref_present(tmp_path):
    env = Env(tmp_path / "ok")
    lines = _happy(env)
    assert any(a[:3] == ["docker", "image", "rm"] for a, _ in env.world.calls)
    assert env.world.tags[ROLLBACK_REF] == ROLLBACK_ID


def test_cleanup_untag_refuses_when_the_release_would_lose_its_last_name(env):
    """After the retag `active` points at the release. If the release tag is
    gone when cleanup runs, removing `active` would delete the release
    image: cleanup refuses that untag (no image rm) and reports the lock
    as not confirmed."""

    def drop_release_tag(argv):
        if argv[-2:] == ["up", "-d"]:
            env.world.tags.pop(RELEASE_TAG, None)

    env.world.pre_hook = drop_release_tag
    env.world.fail[("compose", "up")] = ["rc"]
    rc, lines, _ = env.run("--apply")
    assert rc == 1, lines
    up = next(i for i, (a, _) in enumerate(env.world.calls) if a[-2:] == ["up", "-d"])
    assert not any(a[:3] == ["docker", "image", "rm"] for a, _ in env.world.calls[up:])
    assert env.world.tags[ACTIVE_TAG] == RELEASE_ID
    line = [l for l in lines if l.startswith("ACTIVATE_CLEANUP ")][0]
    assert "lock_code=NOT_CONFIRMED" in line
    assert env.marker_data()["cleanup_code"] is not None
    roots = Path(env.rec["roots"]["private_logs"])
    untag_logs = list(roots.glob("*activate-cleanup-untag-failed*.log"))
    assert untag_logs and "ACTIVATE_UNTAG_UNSAFE" in untag_logs[0].read_text()


def test_cleanup_untag_control_with_the_release_tag_present(tmp_path):
    env = Env(tmp_path / "ok")
    env.world.fail[("compose", "up")] = ["rc"]
    rc, lines, _ = env.run("--apply")
    assert rc == 1, lines
    up = next(i for i, (a, _) in enumerate(env.world.calls) if a[-2:] == ["up", "-d"])
    assert any(a[:3] == ["docker", "image", "rm"] for a, _ in env.world.calls[up:])
    assert ACTIVE_TAG not in env.world.tags
