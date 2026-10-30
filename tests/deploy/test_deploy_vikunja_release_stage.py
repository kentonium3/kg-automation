"""Tests for the STAGE entrypoint and manifest (#1087, WP03).

No real Docker, network or ssh: a stateful fake Docker runner is injected,
and the release record is a ``tmp_path`` copy of ``services/vikunja/release.json``
pointing at a tiny synthetic OCI archive with the real archive's structure
(``fixtures/vikunja_release/``) and at ``tmp_path`` roots. Every refusal or
absence assertion has a same-fixture positive control.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import re
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest
import yaml

from scripts.deploy.lib import LibResult
from scripts.deploy.lib import apply as apply_lib
from scripts.deploy.lib import manifest as manifest_lib
from scripts.deploy.lib import snapshot

_ROOT = Path(__file__).resolve().parents[2]
_ENTRY_REL = "scripts/deploy/deploy-vikunja-release-stage.py"
_PATH = _ROOT / _ENTRY_REL
_spec = importlib.util.spec_from_file_location("deploy_vikunja_release_stage", _PATH)
mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = mod
_spec.loader.exec_module(mod)

_RELEASE = _ROOT / "services" / "vikunja" / "release.json"
_FIX = Path(__file__).resolve().parent / "fixtures" / "vikunja_release"
_MANIFEST_QUEUED = _ROOT / "deploys" / "queued" / "vikunja-release-stage.yaml"

REAL_RELEASE_ID = "sha256:35e1bc8790292deedf2addc3f3f196e38d84c2614219a95d6ef711c1f02afba5"
ROLLBACK_ID = "sha256:60fe1ee8f729c17b057ba00a49b968adb4ed1e774cea36b5f4cc81340991a7d2"
ROLLBACK_REF = "vikunja/vikunja:2.4.0"
RELEASE_TAG = "office2.local/vikunja:v2.7.1-670-420c7bcb75"
ACTIVE_TAG = "office2.local/vikunja:active"
OTHER_ID = "sha256:" + "ab" * 32

SECRET = "password=hunter2"
TITLE = "Buy anniversary gift for Margot"
USER_NAME = "alice.wonderland"
SEEDED = f"login failed {SECRET} task '{TITLE}' owner {USER_NAME}"
LEAKS = (SECRET, "hunter2", TITLE, USER_NAME)

READ_ONLY_VERBS = {("info",), ("image", "inspect")}
MUTATING_VERBS = {"load", "tag", "rm", "rmi", "run", "compose", "pull", "create", "start", "stop"}


def _fixture(name: str):
    return json.loads((_FIX / name).read_text(encoding="utf-8"))


def _resolve_manifest_path() -> Path:
    """felix-deployer moves the manifest to ``deploys/applied/<NNNN>-...`` once
    applied, so it lives in exactly one of the two places."""
    if _MANIFEST_QUEUED.exists():
        return _MANIFEST_QUEUED
    applied = sorted((_ROOT / "deploys" / "applied").glob("*-vikunja-release-stage.yaml"))
    return applied[-1] if applied else _MANIFEST_QUEUED


# ---------------------------------------------------------------------------
# Fixtures: synthetic archive, tmp release record, stateful fake Docker
# ---------------------------------------------------------------------------


def _add(tar: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    tar.addfile(info, io.BytesIO(data))


def _build_archive(path: Path) -> str:
    """A tiny OCI layout with the real archive's structure; returns the
    config digest."""
    cfg_bytes = json.dumps(_fixture("config.json"), sort_keys=True).encode()
    cfg_hex = hashlib.sha256(cfg_bytes).hexdigest()
    layers = [b"layer-%d" % n for n in range(1, 5)]
    names = [f"blobs/sha256/{hashlib.sha256(b).hexdigest()}" for b in layers]
    manifest = _fixture("manifest.json")
    manifest[0]["Config"] = f"blobs/sha256/{cfg_hex}"
    manifest[0]["Layers"] = names
    with tarfile.open(path, "w") as tar:
        _add(tar, "oci-layout", b'{"imageLayoutVersion":"1.0.0"}')
        _add(tar, "index.json", json.dumps(_fixture("index.json")).encode())
        _add(tar, "manifest.json", json.dumps(manifest).encode())
        _add(tar, f"blobs/sha256/{cfg_hex}", cfg_bytes)
        for name, data in zip(names, layers):
            _add(tar, name, data)
    return f"sha256:{cfg_hex}"


def _image_facts(image_id: str, **over) -> dict:
    cfg = _fixture("config.json")
    facts = {"Id": image_id, "Architecture": cfg["architecture"], "Os": cfg["os"],
             "Config": {"User": cfg["config"]["User"], "Labels": dict(cfg["config"]["Labels"])}}
    for key, value in over.items():
        if key == "user":
            facts["Config"]["User"] = value
        elif key == "revision":
            facts["Config"]["Labels"]["org.opencontainers.image.revision"] = value
        else:
            facts[key] = value
    return facts


class FakeDocker:
    """A stateful stand-in for the docker CLI. Records every call."""

    def __init__(self, release_id: str):
        self.calls: list[tuple[list[str], dict]] = []
        self.info = _fixture("docker_info.json")
        self.info_rc = 0
        rollback = _fixture("image_inspect_vikunja_2.4.0.json")
        self.images: dict[str, dict] = {ROLLBACK_ID: rollback}
        self.tags: dict[str, str] = {ROLLBACK_REF: ROLLBACK_ID}
        self.load_id = release_id
        self.load_facts = _image_facts(release_id)
        self.load_rc = 0
        self.load_out: str | None = None
        self.load_raises: BaseException | None = None
        self.tag_rc = 0
        #: Make the post-load ``{{json .}}`` inspection of this ID fail:
        #: "error" (daemon error), "timeout" or "unparseable".
        self.facts_fail: tuple[str, str] | None = None

    def verbs(self) -> set[tuple[str, ...]]:
        out = set()
        for argv, _ in self.calls:
            out.add(tuple(argv[1:3]) if argv[1] in ("image", "container") else (argv[1],))
        return out

    def mutating_calls(self) -> list[list[str]]:
        return [argv for argv, _ in self.calls if (argv[1] if argv[1] != "image" else argv[2]) in MUTATING_VERBS]

    def _resolve(self, ref: str) -> str | None:
        if ref in self.tags:
            return self.tags[ref]
        return ref if ref in self.images else None

    def __call__(self, argv, **kwargs):
        self.calls.append((list(argv), kwargs))
        assert argv[0] == "docker" and "shell" not in kwargs
        cmd = argv[1:]
        if cmd == ["info", "--format", "{{json .}}"]:
            if self.info_rc:
                return subprocess.CompletedProcess(argv, 1, "", f"Cannot connect: {SEEDED}\n")
            return subprocess.CompletedProcess(argv, 0, json.dumps(self.info) + "\n", "")
        if cmd[:3] == ["image", "inspect", "--format"]:
            fmt, ref = cmd[3], cmd[4]
            iid = self._resolve(ref)
            if iid is None:
                return subprocess.CompletedProcess(argv, 1, "", f"Error response from daemon: No such image: {ref}\n")
            if fmt == "{{.Id}}":
                return subprocess.CompletedProcess(argv, 0, iid + "\n", "")
            if self.facts_fail is not None and self.facts_fail[0] == ref:
                kind = self.facts_fail[1]
                if kind == "timeout":
                    raise subprocess.TimeoutExpired(argv, 30, stderr=SEEDED)
                if kind == "unparseable":
                    return subprocess.CompletedProcess(argv, 0, "{not json " + SEEDED + "\n", "")
                return subprocess.CompletedProcess(argv, 1, "", f"Error response from daemon: {SEEDED}\n")
            return subprocess.CompletedProcess(argv, 0, json.dumps([self.images[iid]]) + "\n", "")
        if cmd[:2] == ["load", "-i"]:
            if self.load_raises is not None:
                raise self.load_raises
            if self.load_rc:
                return subprocess.CompletedProcess(argv, self.load_rc, "", f"archive/tar: {SEEDED}\n")
            self.images[self.load_id] = self.load_facts
            out = self.load_out if self.load_out is not None else f"Loaded image ID: {self.load_id}\n"
            return subprocess.CompletedProcess(argv, 0, out, "")
        if cmd[0] == "tag" and len(cmd) == 3:
            if self.tag_rc:
                return subprocess.CompletedProcess(argv, self.tag_rc, "", f"tag failed {SEEDED}\n")
            iid = self._resolve(cmd[1])
            assert iid is not None, "tag source must exist"
            self.tags[cmd[2]] = iid
            return subprocess.CompletedProcess(argv, 0, "", "")
        return subprocess.CompletedProcess(argv, 1, "", "unexpected call\n")


class Env:
    def __init__(self, tmp_path: Path):
        self.tmp = tmp_path
        self.archive = tmp_path / "release-artifacts" / "image.tar"
        self.archive.parent.mkdir()
        self.release_id = _build_archive(self.archive)
        self.activation = tmp_path / "activation"
        self.activation.mkdir(mode=0o700)
        self.activation.chmod(0o700)  # as ACTIVATE's open_private_root requires
        self.private = tmp_path / "failures"
        rec = json.loads(_RELEASE.read_text(encoding="utf-8"))
        rec["archive"]["path"] = str(self.archive)
        rec["archive"]["size"] = self.archive.stat().st_size
        rec["archive"]["sha256"] = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        rec["image"]["config_digest"] = self.release_id
        rec["roots"]["activation"] = str(self.activation)
        rec["roots"]["private_logs"] = str(self.private)
        rec["roots"]["snapshots"] = str(tmp_path / "snapshots")
        self.rec = rec
        self.release_path = tmp_path / "release.json"
        self.write_record()
        self.marker = self.activation / f"{rec['release_version']}.json"
        self.docker = FakeDocker(self.release_id)

    def write_record(self) -> None:
        self.release_path.write_text(json.dumps(self.rec), encoding="utf-8")

    def write_marker(self, **data) -> None:
        body = {"phase": "started", "outcome": None, **data}
        self.marker.write_text(json.dumps(body), encoding="utf-8")

    def run(self, *argv: str):
        out, err = io.StringIO(), io.StringIO()
        rc = mod.main(list(argv), runner=self.docker, release_path=self.release_path,
                      stdout=out, stderr=err)
        return rc, out.getvalue().splitlines(), err.getvalue()


@pytest.fixture
def env(tmp_path):
    return Env(tmp_path)


def _code(lines: list[str]) -> str | None:
    m = re.match(r"FAILED code=(\S+)", lines[0]) if lines else None
    return m.group(1) if m else None


def _assert_untouched(env: Env) -> None:
    """No load, no tag: the store holds exactly the rollback image."""
    assert env.docker.mutating_calls() == []
    assert set(env.docker.tags) == {ROLLBACK_REF}
    assert set(env.docker.images) == {ROLLBACK_ID}


def _control(env: Env) -> None:
    """Same-fixture positive control: with an unbroken fake Docker, this
    env's archive, record and roots stage cleanly. Then hand back a fresh,
    unstaged fake Docker so the test can break exactly one thing."""
    env.docker = FakeDocker(env.release_id)
    rc, lines, _ = env.run("--apply")
    assert rc == 0, lines
    assert env.docker.tags == {ROLLBACK_REF: ROLLBACK_ID, RELEASE_TAG: env.release_id,
                               ACTIVE_TAG: ROLLBACK_ID}
    assert not env.private.exists()
    env.docker = FakeDocker(env.release_id)


def _stage(env: Env) -> None:
    """Put the store in the after-STAGE state of the data model."""
    env.docker.images[env.release_id] = _image_facts(env.release_id)
    env.docker.tags[RELEASE_TAG] = env.release_id
    env.docker.tags[ACTIVE_TAG] = ROLLBACK_ID


# ---------------------------------------------------------------------------
# Entrypoint shape (discipline.md checklist)
# ---------------------------------------------------------------------------


def test_entrypoint_is_executable_in_git():
    out = subprocess.run(["git", "ls-files", "-s", _ENTRY_REL], cwd=_ROOT,
                         capture_output=True, text=True, check=True).stdout
    assert out.startswith("100755"), out


def test_entrypoint_shebang_and_sys_path_shim():
    src = _PATH.read_text(encoding="utf-8")
    assert src.startswith("#!/usr/bin/env python3\n")
    assert "sys.path.insert(0, str(Path(__file__).resolve().parents[2]))" in src
    assert "shell=True" not in src


@pytest.mark.parametrize("argv", [[], ["--apply", "--dry-run"], ["--force"], ["apply"], ["--dry-run", "x"]])
def test_usage_exits_2_without_touching_docker(env, argv):
    rc, lines, err = env.run(*argv)
    assert rc == 2 and lines == [] and err.startswith("usage:")
    assert env.docker.calls == []
    rc, _, _ = env.run("--dry-run")  # positive control
    assert rc == 0


# ---------------------------------------------------------------------------
# T012 — dry run
# ---------------------------------------------------------------------------


def test_dry_run_plans_and_makes_zero_mutating_calls(env):
    rc, lines, err = env.run("--dry-run")
    assert rc == 0, lines
    assert err == ""
    assert lines[0] == f"STAGE_DRY_RUN_OK release_version=v2.7.1-670-420c7bcb75 config_digest={env.release_id}"
    assert f"STAGE_ARCHIVE_VERIFIED path={env.archive} size={env.rec['archive']['size']} " \
           f"sha256={env.rec['archive']['sha256']}" in lines
    assert f"STAGE_PLAN_LOAD archive={env.archive}" in lines
    assert f"STAGE_PLAN_TAG_RELEASE id={env.release_id}" in lines
    assert f"STAGE_PLAN_CREATE_ACTIVE id={ROLLBACK_ID}" in lines
    assert env.docker.verbs() == READ_ONLY_VERBS
    _assert_untouched(env)
    # Nothing written anywhere: no private log, no marker, archive intact.
    assert sorted(p.name for p in env.tmp.iterdir()) == ["activation", "release-artifacts", "release.json"]
    assert list(env.activation.iterdir()) == []


@pytest.mark.parametrize("state", ["fresh", "staged", "activated", "rolled_back", "held", "refused"])
def test_dry_run_is_read_only_in_every_state(env, state):
    if state == "staged":
        _stage(env)
    elif state == "activated":
        _stage(env)
        env.docker.tags[ACTIVE_TAG] = env.release_id
        env.write_marker(phase="verified", outcome="success")
    elif state == "rolled_back":
        _stage(env)
        env.write_marker(phase="verified", outcome="rolled_back")
    elif state == "held":
        env.write_marker(phase="stopped")
    elif state == "refused":
        env.docker.tags[RELEASE_TAG] = ROLLBACK_ID
    before_tags = dict(env.docker.tags)
    rc, lines, _ = env.run("--dry-run")
    assert rc == (1 if state in ("held", "refused") else 0), lines
    assert env.docker.verbs() <= READ_ONLY_VERBS
    assert env.docker.mutating_calls() == []
    assert env.docker.tags == before_tags
    assert not env.private.exists()


def test_dry_run_reports_nothing_to_do_once_staged(env):
    _stage(env)
    rc, lines, _ = env.run("--dry-run")
    assert rc == 0
    assert lines[-1] == f"STAGE_PLAN_NOTHING id={env.release_id}"
    assert not any(l.startswith(("STAGE_PLAN_LOAD", "STAGE_PLAN_TAG", "STAGE_PLAN_CREATE")) for l in lines)


# ---------------------------------------------------------------------------
# T013 — apply order and idempotence
# ---------------------------------------------------------------------------


def _mutations(env: Env) -> list[list[str]]:
    return [argv[1:] for argv in env.docker.mutating_calls()]


def test_apply_loads_verifies_then_tags(env):
    rc, lines, err = env.run("--apply")
    assert rc == 0, lines
    assert err == ""
    assert lines[0] == f"STAGE_APPLIED release_version=v2.7.1-670-420c7bcb75 config_digest={env.release_id}"
    assert _mutations(env) == [
        ["load", "-i", str(env.archive)],
        ["tag", env.release_id, RELEASE_TAG],
        ["tag", ROLLBACK_ID, ACTIVE_TAG],
    ]
    argvs = [argv for argv, _ in env.docker.calls]
    load_at = argvs.index(["docker", "load", "-i", str(env.archive)])
    facts_at = argvs.index(["docker", "image", "inspect", "--format", "{{json .}}", env.release_id])
    tag_at = argvs.index(["docker", "tag", env.release_id, RELEASE_TAG])
    assert load_at < facts_at < tag_at
    assert env.docker.tags == {ROLLBACK_REF: ROLLBACK_ID, RELEASE_TAG: env.release_id, ACTIVE_TAG: ROLLBACK_ID}
    for marker in (f"STAGE_LOADED id={env.release_id}", f"STAGE_IMAGE_VERIFIED id={env.release_id}",
                   f"STAGE_TAGGED_RELEASE id={env.release_id}", f"STAGE_CREATED_ACTIVE id={ROLLBACK_ID}"):
        assert marker in lines


def test_every_subprocess_call_is_time_bounded(env):
    env.run("--apply")
    assert env.docker.calls
    for argv, kwargs in env.docker.calls:
        assert kwargs.get("timeout"), argv
        expected = mod.LOAD_TIMEOUT if argv[1] == "load" else 30
        assert kwargs["timeout"] == expected, argv
    assert mod.LOAD_TIMEOUT == 300


def test_apply_is_a_noop_once_staged(env):
    rc, _, _ = env.run("--apply")
    assert rc == 0
    env.docker.calls.clear()
    rc, lines, _ = env.run("--apply")
    assert rc == 0
    assert lines[0].startswith("STAGE_ALREADY_STAGED ")
    assert f"STAGE_IMAGE_VERIFIED id={env.release_id}" in lines
    assert env.docker.mutating_calls() == []


def test_apply_tags_only_active_when_release_already_staged(env):
    _stage(env)
    del env.docker.tags[ACTIVE_TAG]
    rc, lines, _ = env.run("--apply")
    assert rc == 0, lines
    assert lines[0].startswith("STAGE_APPLIED ")
    assert _mutations(env) == [["tag", ROLLBACK_ID, ACTIVE_TAG]]


def test_loaded_id_other_than_config_digest_is_refused_untagged(env):
    env.docker.load_id = OTHER_ID
    env.docker.load_facts = _image_facts(OTHER_ID)
    rc, lines, _ = env.run("--apply")
    assert rc == 1 and _code(lines) == "STAGE_LOADED_ID_UNEXPECTED"
    assert f"STAGE_LOADED_UNTAGGED loaded_id={OTHER_ID}" in lines
    assert [m[0] for m in _mutations(env)] == ["load"]
    assert RELEASE_TAG not in env.docker.tags and ACTIVE_TAG not in env.docker.tags
    # Positive control: the same fixture with the expected ID stages.
    env.docker = FakeDocker(env.release_id)
    assert env.run("--apply")[0] == 0
    assert env.docker.tags[RELEASE_TAG] == env.release_id


def test_load_output_without_an_id_is_refused(env):
    _control(env)
    env.docker.load_out = "Loaded image: something:latest\n"
    rc, lines, _ = env.run("--apply")
    assert rc == 1 and _code(lines) == "STAGE_LOAD_OUTPUT_UNPARSEABLE"
    assert [m[0] for m in _mutations(env)] == ["load"]


@pytest.mark.parametrize("override", [
    {"Architecture": "arm64"}, {"Os": "windows"}, {"user": "0"}, {"revision": "0" * 40},
])
def test_verify_failure_after_load_leaves_the_image_untagged(env, override):
    env.docker.load_facts = _image_facts(env.release_id, **override)
    rc, lines, _ = env.run("--apply")
    assert rc == 1 and _code(lines) == "STAGE_VERIFY_FAILED"
    assert lines[0].startswith("FAILED code=STAGE_VERIFY_FAILED")
    assert f"STAGE_LOADED id={env.release_id}" in lines
    assert f"STAGE_LOADED_UNTAGGED loaded_id={env.release_id}" in lines
    assert [m[0] for m in _mutations(env)] == ["load"]
    assert env.release_id in env.docker.images  # loaded ...
    assert env.docker.tags == {ROLLBACK_REF: ROLLBACK_ID}  # ... but never tagged
    # Positive control: same fixture, matching facts.
    env.docker = FakeDocker(env.release_id)
    assert env.run("--apply")[0] == 0
    assert env.docker.tags[RELEASE_TAG] == env.release_id


@pytest.mark.parametrize("kind, private_code", [
    ("error", "DOCKER_INSPECT_FAILED"), ("timeout", "TIMEOUT_DOCKER_INSPECT"),
    ("unparseable", "DOCKER_INSPECT_UNPARSEABLE"),
])
def test_post_load_inspection_failure_is_a_verify_failure(env, kind, private_code):
    """R-18: an inspection that fails outright after the load is
    STAGE_VERIFY_FAILED with the loaded ID, untagged; raw detail stays private."""
    _control(env)
    env.docker.facts_fail = (env.release_id, kind)
    rc, lines, err = env.run("--apply")
    assert rc == 1 and _code(lines) == "STAGE_VERIFY_FAILED"
    assert f"STAGE_LOADED id={env.release_id}" in lines
    assert f"STAGE_LOADED_UNTAGGED loaded_id={env.release_id}" in lines
    assert [m[0] for m in _mutations(env)] == ["load"]
    assert env.release_id in env.docker.images
    assert env.docker.tags == {ROLLBACK_REF: ROLLBACK_ID}
    out = "\n".join(lines) + err
    for leak in LEAKS:
        assert leak not in out
    logs = list(env.private.iterdir())
    assert len(logs) == 1 and f"private_log={logs[0]}" in lines[0]
    text = logs[0].read_text()
    assert text.startswith(private_code + "\n")
    if kind != "unparseable":
        assert SECRET in text
    # Recovery on the same fixture: once inspection works, a re-run verifies
    # the already-loaded image and tags it.
    env.docker.facts_fail = None
    rc, lines, _ = env.run("--apply")
    assert rc == 0, lines
    assert env.docker.tags[RELEASE_TAG] == env.release_id


def test_load_failure_is_private_and_untagged(env):
    _control(env)
    env.docker.load_rc = 1
    rc, lines, err = env.run("--apply")
    assert rc == 1 and _code(lines) == "STAGE_LOAD_FAILED"
    assert env.docker.tags == {ROLLBACK_REF: ROLLBACK_ID}
    out = "\n".join(lines) + err
    for leak in LEAKS:
        assert leak not in out
    logs = list(env.private.iterdir())
    assert len(logs) == 1 and SECRET in logs[0].read_text()
    assert f"private_log={logs[0]}" in lines[0]
    assert oct(env.private.stat().st_mode & 0o777) == "0o700"


def test_load_timeout_is_a_stable_code(env):
    _control(env)
    env.docker.load_raises = subprocess.TimeoutExpired(["docker", "load"], 300, stderr=SEEDED)
    rc, lines, _ = env.run("--apply")
    assert rc == 1 and _code(lines) == "TIMEOUT_DOCKER_LOAD"
    assert env.docker.tags == {ROLLBACK_REF: ROLLBACK_ID}


def test_tag_failure_reports_a_code_and_what_was_done(env):
    _control(env)
    env.docker.tag_rc = 1
    rc, lines, _ = env.run("--apply")
    assert rc == 1 and _code(lines) == "STAGE_TAG_RELEASE_FAILED"
    assert f"STAGE_IMAGE_VERIFIED id={env.release_id}" in lines
    assert ACTIVE_TAG not in env.docker.tags


# ---------------------------------------------------------------------------
# T014 — `active` creation and hold (R-3, R-23)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("active", ["rollback", "release"])
def test_existing_active_is_accepted_and_never_retagged(env, active):
    target = ROLLBACK_ID if active == "rollback" else env.release_id
    if active == "release":
        env.docker.images[env.release_id] = _image_facts(env.release_id)
    env.docker.tags[ACTIVE_TAG] = target
    rc, lines, _ = env.run("--apply")
    assert rc == 0, lines
    assert env.docker.tags[ACTIVE_TAG] == target
    assert not any(m[0] == "tag" and m[2] == ACTIVE_TAG for m in _mutations(env))


def test_active_pointing_elsewhere_is_refused(env):
    env.docker.images[OTHER_ID] = _image_facts(OTHER_ID)
    env.docker.tags[ACTIVE_TAG] = OTHER_ID
    for mode in ("--dry-run", "--apply"):
        rc, lines, _ = env.run(mode)
        assert rc == 1 and _code(lines) == "STAGE_ACTIVE_UNEXPECTED"
    assert env.docker.mutating_calls() == []
    assert env.docker.tags[ACTIVE_TAG] == OTHER_ID
    # Positive control: the same fixture with `active` at 2.4.0.
    env.docker.tags[ACTIVE_TAG] = ROLLBACK_ID
    assert env.run("--apply")[0] == 0


@pytest.mark.parametrize("marker", [
    {"phase": "started"},
    {"phase": "snapshotted"},
    {"phase": "retagged", "outcome": "failed", "failed_phase": "started_new"},
    {"phase": "verified", "outcome": "success"},
    {"phase": "verified", "outcome": "rolled_back"},
])
def test_marker_with_active_absent_holds_and_never_creates_active(env, marker):
    env.write_marker(**marker)
    for mode in ("--dry-run", "--apply"):
        rc, lines, _ = env.run(mode)
        assert rc == 1 and _code(lines) == "STAGE_ACTIVE_HELD_BY_ACTIVATION"
    _assert_untouched(env)
    # Positive control: the same fixture without a marker creates `active`.
    env.marker.unlink()
    assert env.run("--apply")[0] == 0
    assert env.docker.tags[ACTIVE_TAG] == ROLLBACK_ID


def test_marker_with_active_present_is_not_a_hold(env):
    _stage(env)
    env.write_marker(phase="verified", outcome="rolled_back")
    rc, lines, _ = env.run("--apply")
    assert rc == 0, lines
    assert any("marker_outcome=rolled_back" in l for l in lines)
    assert env.docker.mutating_calls() == []


def test_marker_appearing_before_the_active_tag_still_holds(env, monkeypatch):
    """R-23 re-check: the marker is read again immediately before tagging."""
    _control(env)  # same fixture, no marker: `active` is created
    real = mod.core.marker_read
    reads = {"n": 0}

    def marker_read(path):
        reads["n"] += 1
        if reads["n"] == 2:
            env.write_marker(phase="started")
        return real(path)

    monkeypatch.setattr(mod.core, "marker_read", marker_read)
    rc, lines, _ = env.run("--apply")
    assert rc == 1 and _code(lines) == "STAGE_ACTIVE_HELD_BY_ACTIVATION"
    assert ACTIVE_TAG not in env.docker.tags
    assert f"STAGE_TAGGED_RELEASE id={env.release_id}" in lines


def test_malformed_marker_refuses(env):
    env.marker.write_text("{not json", encoding="utf-8")
    rc, lines, _ = env.run("--apply")
    assert rc == 1 and _code(lines) == "MARKER_UNREADABLE"
    _assert_untouched(env)
    env.marker.unlink()  # positive control
    assert env.run("--apply")[0] == 0


# ---------------------------------------------------------------------------
# T015 — refusals: exit 1, no load, no tag; each with its positive control
# ---------------------------------------------------------------------------


def _missing_archive(env):
    env.archive.rename(env.archive.with_suffix(".away"))


def _undo_missing_archive(env):
    env.archive.with_suffix(".away").rename(env.archive)


def _size(env):
    env.rec["archive"]["size"] += 1
    env.write_record()


def _undo_size(env):
    env.rec["archive"]["size"] -= 1
    env.write_record()


def _sha(env):
    env.rec["archive"]["sha256"] = "0" * 64
    env.write_record()


def _undo_sha(env):
    env.rec["archive"]["sha256"] = hashlib.sha256(env.archive.read_bytes()).hexdigest()
    env.write_record()


def _release_elsewhere(env):
    env.docker.tags[RELEASE_TAG] = ROLLBACK_ID


def _undo_release_elsewhere(env):
    del env.docker.tags[RELEASE_TAG]


def _rollback_missing(env):
    del env.docker.tags[ROLLBACK_REF]


def _undo_rollback_missing(env):
    env.docker.tags[ROLLBACK_REF] = ROLLBACK_ID


def _rollback_other(env):
    env.docker.images[OTHER_ID] = _image_facts(OTHER_ID)
    env.docker.tags[ROLLBACK_REF] = OTHER_ID


def _undo_rollback_other(env):
    env.docker.tags[ROLLBACK_REF] = ROLLBACK_ID
    del env.docker.images[OTHER_ID]


def _store(env):
    env.docker.info["DriverStatus"].append(["driver-type", "io.containerd.snapshotter.v1"])


def _undo_store(env):
    env.docker.info["DriverStatus"].pop()


def _driver(env):
    env.docker.info["Driver"] = "overlayfs"


def _undo_driver(env):
    env.docker.info["Driver"] = "overlay2"


def _unreachable(env):
    env.docker.info_rc = 1


def _undo_unreachable(env):
    env.docker.info_rc = 0


REFUSALS = [
    (_missing_archive, _undo_missing_archive, "ARCHIVE_MISSING"),
    (_size, _undo_size, "ARCHIVE_SIZE_MISMATCH"),
    (_sha, _undo_sha, "ARCHIVE_SHA_MISMATCH"),
    (_release_elsewhere, _undo_release_elsewhere, "STAGE_RELEASE_TAG_UNEXPECTED"),
    (_rollback_missing, _undo_rollback_missing, "STAGE_ROLLBACK_IMAGE_MISSING"),
    (_rollback_other, _undo_rollback_other, "STAGE_ROLLBACK_IMAGE_UNEXPECTED"),
    (_store, _undo_store, "DOCKER_STORE_UNSUPPORTED"),
    (_driver, _undo_driver, "DOCKER_STORE_UNSUPPORTED"),
    (_unreachable, _undo_unreachable, "DOCKER_UNREACHABLE"),
]


@pytest.mark.parametrize("break_it, fix_it, code", REFUSALS, ids=[r[2] + "-" + r[0].__name__ for r in REFUSALS])
@pytest.mark.parametrize("mode", ["--dry-run", "--apply"])
def test_refusals_exit_1_with_no_load_and_no_tag(env, break_it, fix_it, code, mode):
    break_it(env)
    tags_before = dict(env.docker.tags)
    rc, lines, err = env.run(mode)
    assert rc == 1, lines
    assert _code(lines) == code
    assert len(lines) == 1 and err == ""
    assert env.docker.mutating_calls() == []
    assert env.docker.tags == tags_before
    # Positive control: the same fixture, repaired, passes in the same mode.
    fix_it(env)
    env.docker.calls.clear()
    rc, lines, _ = env.run(mode)
    assert rc == 0, lines


# ---------------------------------------------------------------------------
# Output allowlist (R-16)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("break_it", [_unreachable, _rollback_missing, None])
def test_seeded_private_text_never_reaches_stdout_or_stderr(env, break_it):
    if break_it is not None:
        break_it(env)
    env.docker.load_rc = 1  # docker stderr carries the seeded text
    for mode in ("--dry-run", "--apply"):
        rc, lines, err = env.run(mode)
        out = "\n".join(lines) + err
        for leak in LEAKS:
            assert leak not in out
        assert "REDACTED" not in out
        assert lines[0].split()[0] in mod.core.registered_summaries()


def test_every_line_starts_with_a_registered_identifier(env):
    rc, lines, _ = env.run("--apply")
    assert rc == 0
    for line in lines:
        assert line.split()[0] in mod.core.registered_summaries(), line
        assert "REDACTED" not in line


# ---------------------------------------------------------------------------
# T016 — manifest
# ---------------------------------------------------------------------------


def _manifest() -> dict:
    return yaml.safe_load(_resolve_manifest_path().read_text(encoding="utf-8"))


def test_manifest_fields():
    m = _manifest()
    assert m["schema_version"] == "v1"
    assert m["name"] == "vikunja-release-stage"
    assert m["issue"] == "kentonium3/kg-automation#1087"
    assert m["tier"] == 2
    assert m["entrypoint"] == _ENTRY_REL
    assert (_ROOT / m["entrypoint"]).is_file()
    assert m["audited_surface"] is True
    assert m["expected_baselines"] == ["docker-images.txt"]
    assert m["created_by"] == "claude-code-1087"
    assert m["verification"]["pre"] == [f"{_ENTRY_REL} --dry-run"]
    assert m["verification"]["post"] == [
        f"docker image inspect --format '{{{{.Id}}}}' {RELEASE_TAG} | grep -qx {REAL_RELEASE_ID}",
        f"docker image inspect --format '{{{{.Id}}}}' {ROLLBACK_REF} | grep -qx {ROLLBACK_ID}",
    ]
    assert 0 < len(m["notes"]) <= 2000


def test_manifest_post_checks_match_the_release_record():
    rec = json.loads(_RELEASE.read_text(encoding="utf-8"))
    posts = " ".join(_manifest()["verification"]["post"])
    assert rec["tags"]["release"] in posts and rec["image"]["config_digest"] in posts
    assert rec["rollback"]["ref"] in posts and rec["rollback"]["image_id"] in posts


def test_manifest_validates_against_the_schema():
    result = manifest_lib.validate_manifest_file(_resolve_manifest_path())
    assert result.ok, result.details
    # Positive/negative pair on the same data: an unknown key is refused.
    bad = dict(_manifest(), surprise=True)
    assert not manifest_lib.validate_manifest(bad).ok


def test_manifest_expected_baselines_are_known():
    m = _manifest()
    assert manifest_lib.validate_expected_baselines_only(m).ok
    bogus = dict(m, expected_baselines=["not-a-baseline.txt"])
    assert not manifest_lib.validate_expected_baselines_only(bogus).ok
    decoupled = dict(m, audited_surface=False)
    assert not manifest_lib.validate_expected_baselines_only(decoupled).ok


# ---------------------------------------------------------------------------
# Gate composition through dry_run_then_apply_gate (R-18)
# ---------------------------------------------------------------------------

_POST_RE = re.compile(r"^docker image inspect --format '\{\{\.Id\}\}' (\S+) \| grep -qx (sha256:[0-9a-f]{64})$")


class GateShell:
    """Fake ``apply._run_shell``: runs the entrypoint in-process against the
    fake Docker, and evaluates the post checks against its tags."""

    def __init__(self, env: Env, manifest: dict):
        self.env = env
        self.commands: list = []
        # The synthetic archive's digest stands in for the real one.
        self.digest_map = {REAL_RELEASE_ID: env.release_id}
        self.entrypoint = manifest["entrypoint"]

    def __call__(self, cmd, *, env=None):
        self.commands.append(cmd)
        if isinstance(cmd, list):
            assert cmd[0] == self.entrypoint
            rc, lines, _ = self.env.run(*cmd[1:])
        elif cmd == f"{self.entrypoint} --dry-run":
            rc, lines, _ = self.env.run("--dry-run")
        else:
            m = _POST_RE.match(cmd)
            assert m, cmd
            want = self.digest_map.get(m.group(2), m.group(2))
            rc, lines = (0 if self.env.docker.tags.get(m.group(1)) == want else 1), []
        return LibResult(ok=rc == 0, summary=lines[0] if lines else "", details={"returncode": rc})


def _gate(env: Env, monkeypatch) -> tuple[LibResult, GateShell]:
    m = _manifest()
    shell = GateShell(env, m)
    monkeypatch.chdir(_ROOT)  # tier_guard checks the relative entrypoint exists
    monkeypatch.setattr(snapshot, "ensure_recent_backup",
                        lambda *a, **k: LibResult(ok=True, summary="fresh"))
    monkeypatch.setattr(apply_lib, "_run_shell", shell)
    return apply_lib.dry_run_then_apply_gate(m, str(_resolve_manifest_path())), shell


def test_gate_composition_applies_and_post_checks_pass(env, monkeypatch):
    result, shell = _gate(env, monkeypatch)
    assert result.ok, result
    assert result.details["phase"] == apply_lib.PHASE_COMPLETE
    assert shell.commands[:3] == [f"{_ENTRY_REL} --dry-run", [_ENTRY_REL, "--dry-run"], [_ENTRY_REL, "--apply"]]
    assert len(shell.commands) == 5
    assert env.docker.tags[RELEASE_TAG] == env.release_id
    assert env.docker.tags[ACTIVE_TAG] == ROLLBACK_ID


def test_gate_composition_verify_failure_stops_at_apply_untagged(env, monkeypatch):
    env.docker.load_facts = _image_facts(env.release_id, revision="0" * 40)
    result, shell = _gate(env, monkeypatch)
    assert not result.ok
    assert result.details["phase"] == apply_lib.PHASE_ENTRYPOINT_APPLY
    assert len(shell.commands) == 3  # no post checks ran
    assert env.release_id in env.docker.images
    assert RELEASE_TAG not in env.docker.tags and ACTIVE_TAG not in env.docker.tags


def test_gate_composition_refusal_stops_before_any_mutation(env, monkeypatch):
    _release_elsewhere(env)
    result, shell = _gate(env, monkeypatch)
    assert not result.ok
    assert result.details["phase"] == apply_lib.PHASE_VERIFICATION_PRE
    assert env.docker.mutating_calls() == []
    assert len(shell.commands) == 1


# ---------------------------------------------------------------------------
# Serialisation with ACTIVATE and the rollback helper (post-merge review)
# ---------------------------------------------------------------------------

import os  # noqa: E402
import stat  # noqa: E402
import subprocess as _subprocess  # noqa: E402
import sys as _sys  # noqa: E402

from scripts.deploy.vikunja_release import dbsafety as _dbsafety  # noqa: E402

_HOLDER = (
    "import fcntl, os, sys, time\n"
    "fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o600)\n"
    "fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)\n"
    "sys.stdout.write('held\\n'); sys.stdout.flush()\n"
    "time.sleep(120)\n"
)


def _hold(lock: Path):
    proc = _subprocess.Popen([_sys.executable, "-c", _HOLDER, str(lock)], stdout=_subprocess.PIPE, text=True)
    assert proc.stdout.readline() == "held\n"
    return proc


@pytest.mark.parametrize("mode", ["--apply", "--dry-run"])
def test_stage_refuses_while_activation_lock_is_held(env, mode):
    """Another process (an ACTIVATE, a rollback or a second STAGE) holds
    activation.lock: STAGE refuses before any docker call."""
    lock = env.activation / _dbsafety.ACTIVATION_LOCK_NAME
    holder = _hold(lock)
    try:
        rc, lines, _ = env.run(mode)
        assert rc == 1 and _code(lines) == "STAGE_ACTIVATION_LOCK_BUSY", lines
        assert env.docker.calls == []
    finally:
        holder.kill()
        holder.wait(timeout=10)
    # Control: the same fixture with the lock free proceeds.
    rc, lines, _ = env.run(mode)
    assert rc == 0, lines
    assert f"STAGE_ACTIVATION_LOCK_FREE lock={lock}" in lines or mode == "--apply"


def test_every_stage_mutation_happens_under_the_activation_lock(env):
    import fcntl

    lock = env.activation / _dbsafety.ACTIVATION_LOCK_NAME
    real = env.docker
    unlocked: list[list[str]] = []

    def probing(argv, **kw):
        if os.path.exists(lock):
            fd = os.open(lock, os.O_RDONLY)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                unlocked.append(list(argv))
                fcntl.flock(fd, fcntl.LOCK_UN)
            except BlockingIOError:
                pass
            finally:
                os.close(fd)
        else:
            unlocked.append(list(argv))
        return real(argv, **kw)

    env.docker = probing
    rc, lines, _ = env.run("--apply")
    assert rc == 0, lines
    assert real.mutating_calls(), "the fixture must exercise load and tag"
    assert unlocked == []  # every call, read or write, ran with the lock held
    # Released at the end: the lock is free again.
    assert _dbsafety.activation_lock_free(env.activation)


def test_stage_dry_run_never_creates_the_lock(env):
    rc, lines, _ = env.run("--dry-run")
    assert rc == 0, lines
    assert list(env.activation.iterdir()) == []
    # Control: the apply creates and holds it, mode 0600.
    rc, lines, _ = env.run("--apply")
    assert rc == 0, lines
    lock = env.activation / _dbsafety.ACTIVATION_LOCK_NAME
    assert stat.S_IMODE(lock.stat().st_mode) == 0o600


def test_stage_refuses_a_symlinked_lock(env, tmp_path):
    target = tmp_path / "elsewhere"
    target.write_text("")
    lock = env.activation / _dbsafety.ACTIVATION_LOCK_NAME
    lock.symlink_to(target)
    rc, lines, _ = env.run("--apply")
    assert rc == 1 and _code(lines) == "STAGE_ACTIVATION_LOCK_UNAVAILABLE", lines
    assert env.docker.calls == []
    lock.unlink()
    rc, lines, _ = env.run("--apply")
    assert rc == 0, lines
