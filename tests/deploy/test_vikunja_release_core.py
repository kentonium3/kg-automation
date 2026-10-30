"""Tests for the Vikunja release-route core primitives (#1087, WP01).

No network, ssh or docker: the runner, clock and roots are injected, and the
release archive is a tiny synthetic OCI tar built in ``tmp_path`` with the
real archive's structure (fixtures under ``fixtures/vikunja_release/``).
Every refusal or absence assertion has a same-fixture positive control.
"""

from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import stat
import subprocess
import tarfile
from pathlib import Path

import pytest

from scripts.deploy.vikunja_release import core

_ROOT = Path(__file__).resolve().parents[2]
_RELEASE = _ROOT / "services" / "vikunja" / "release.json"
_CORE_SRC = _ROOT / "scripts" / "deploy" / "vikunja_release" / "core.py"
_FIX = Path(__file__).resolve().parent / "fixtures" / "vikunja_release"

RELEASE_ID = "sha256:35e1bc8790292deedf2addc3f3f196e38d84c2614219a95d6ef711c1f02afba5"
ROLLBACK_ID = "sha256:60fe1ee8f729c17b057ba00a49b968adb4ed1e774cea36b5f4cc81340991a7d2"
INDEX_DIGEST = "sha256:2be2b8c20475294c74447414548437eca49b1fcf972f292813737eea6578ffb6"

SECRET = "password=hunter2"
TITLE = "Buy anniversary gift for Margot"
USER_NAME = "alice.wonderland"
SEEDED_RAW = f"Error: login failed {SECRET} task '{TITLE}' owner {USER_NAME}\n"
#: Seeded private strings. Every one of these matched the cycle-0 summary
#: character regex (``[A-Za-z0-9 _:./,()@+=>-]{1,200}``), so each would have
#: printed unchanged in the summary position; the last is code-shaped.
SEEDED_SUMMARY_LEAKS = [SECRET, TITLE, USER_NAME, f"login failed {SECRET}", f"task: {TITLE}",
                        f"owner={USER_NAME}", "HUNTER2_TOKEN"]

core.register_summaries("STAGE_VERIFIED", "STAGE_REFUSED", "STAGE_LOAD_FAILED")


def _fixture(name: str):
    return json.loads((_FIX / name).read_text(encoding="utf-8"))


def _record() -> dict:
    return json.loads(_RELEASE.read_text(encoding="utf-8"))


def _write_json(path: Path, data) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Fake docker runner built around the captured office2 shapes (R-13)
# ---------------------------------------------------------------------------


class FakeRunner:
    """Records each call; answers ``docker`` argv from a table of fixtures."""

    def __init__(self, responses=None, raise_exc=None):
        self.calls: list[tuple[list[str], dict]] = []
        self.responses = responses or {}
        self.raise_exc = raise_exc

    def __call__(self, argv, **kwargs):
        self.calls.append((list(argv), kwargs))
        if self.raise_exc is not None:
            raise self.raise_exc
        key = tuple(argv)
        if key not in self.responses:
            return subprocess.CompletedProcess(argv, 1, "", "unexpected call\n")
        rc, out, err = self.responses[key]
        return subprocess.CompletedProcess(argv, rc, out, err)


def _info_argv():
    return ("docker", "info", "--format", "{{json .}}")


def _image_id_argv(ref):
    return ("docker", "image", "inspect", "--format", "{{.Id}}", ref)


def _image_json_argv(ref):
    return ("docker", "image", "inspect", "--format", "{{json .}}", ref)


def _container_argv(name):
    return ("docker", "container", "inspect", "--format", "{{.Image}} {{.Config.Image}}", name)


def _release_image_inspect() -> dict:
    """Release image as the classic store reports it: Id is the config digest."""
    cfg = _fixture("config.json")
    return {"Id": RELEASE_ID, "RepoTags": ["office2.local/vikunja:v2.7.1-670-420c7bcb75"],
            "Architecture": cfg["architecture"], "Os": cfg["os"],
            "Config": {"User": cfg["config"]["User"], "Labels": cfg["config"]["Labels"]}}


def _office2_runner() -> FakeRunner:
    rollback = _fixture("image_inspect_vikunja_2.4.0.json")
    ctr = _fixture("container_inspect_vikunja.json")
    no_image = "Error response from daemon: No such image: office2.local/vikunja:active\n"
    return FakeRunner({
        _info_argv(): (0, json.dumps(_fixture("docker_info.json")) + "\n", ""),
        _image_id_argv("vikunja/vikunja:2.4.0"): (0, rollback["Id"] + "\n", ""),
        _image_json_argv("vikunja/vikunja:2.4.0"): (0, json.dumps(rollback) + "\n", ""),
        _image_id_argv("office2.local/vikunja:active"): (1, "", no_image),
        _image_json_argv("office2.local/vikunja:active"): (1, "", no_image),
        _image_json_argv("office2.local/vikunja:v2.7.1-670-420c7bcb75"):
            (0, json.dumps(_release_image_inspect()) + "\n", ""),
        _container_argv("vikunja"): (0, f"{ctr['Image']} {ctr['Config']['Image']}\n", ""),
        _container_argv("absent"): (1, "", "Error: No such container: absent\n"),
    })


# ---------------------------------------------------------------------------
# T001 — release record
# ---------------------------------------------------------------------------


def test_release_record_loads_with_pinned_values():
    rec = core.load_release(_RELEASE)
    assert rec["release_version"] == "v2.7.1-670-420c7bcb75"
    assert rec["source_revision"] == "420c7bcb75231be9b6571fdfdf76a1a62f2aebd8"
    assert rec["archive"] == {
        "path": "/data/services/vikunja/release-artifacts/48008c5067a6/image.tar",
        "sha256": "48008c5067a6555cb880200d5416a7989df6be06246cc41bc69d1da685581f79",
        "size": 54450688,
    }
    assert rec["image"] == {"config_digest": RELEASE_ID, "index_digest": INDEX_DIGEST,
                            "platform": "linux/amd64", "user": "1000"}
    assert rec["tags"] == {"release": "office2.local/vikunja:v2.7.1-670-420c7bcb75",
                           "active": "office2.local/vikunja:active"}
    assert rec["rollback"]["image_id"] == ROLLBACK_ID
    assert rec["rollback"]["ref"] == "vikunja/vikunja:2.4.0"
    assert rec["rollback"]["archive"] == {
        "path": "/data/services/vikunja/release-artifacts/48008c5067a6/vikunja-2.4.0.image.tar",
        "sha256": "b63e5529ba35e695aec3b240f835a5ea412a2b0552f2a1b054e5d0d9a9aaa9ad",
        "size": 115518464,
    }
    assert rec["service"] == {
        "compose_file": "/home/claude/kg-automation/services/vikunja/docker-compose.yml",
        "project": "vikunja", "container": "vikunja",
        "info_url": "http://100.92.197.90:3456/api/v1/info",
        "data_dir": "/data/services/vikunja/data",
    }
    assert rec["roots"]["snapshots"] == "/data/services/vikunja/snapshots"
    assert rec["roots"]["activation"] == "/data/services/vikunja/activation"
    assert rec["roots"]["private_logs"] == "/data/services/vikunja/failures"
    assert rec["roots"]["office4_sources"] == {
        "archive": "/home/kgale/.local/share/rrule-office2-images/"
                   "420c7bcb75231be9b6571fdfdf76a1a62f2aebd8/image.tar",
        "rollback_archive": "/home/kgale/.local/share/rrule-office2-images/"
                            "rollback-v2.4.0-60fe1ee8/vikunja-2.4.0.image.tar",
    }


def _mutate(path: str, value=None, delete=False):
    def apply(rec):
        *parents, leaf = path.split(".")
        node = rec
        for p in parents:
            node = node[p]
        if delete:
            del node[leaf]
        else:
            node[leaf] = value
    return apply


@pytest.mark.parametrize("mutation, code, key", [
    (_mutate("archive.sha256", delete=True), "RELEASE_KEY_MISSING", "archive.sha256"),
    (_mutate("roots.office4_sources", delete=True), "RELEASE_KEY_MISSING", "roots.office4_sources"),
    (_mutate("schema_version", delete=True), "RELEASE_KEY_MISSING", "schema_version"),
    (_mutate("extra", "x"), "RELEASE_KEY_UNKNOWN", "extra"),
    (_mutate("archive.size", "54450688"), "RELEASE_TYPE_INVALID", "archive.size"),
    (_mutate("archive.size", True), "RELEASE_TYPE_INVALID", "archive.size"),
    (_mutate("image", "sha256:abc"), "RELEASE_TYPE_INVALID", "image"),
    (_mutate("archive.sha256", "48008C5067A6555CB880200D5416A7989DF6BE06246CC41BC69D1DA685581F79"),
     "RELEASE_VALUE_INVALID", "archive.sha256"),
    (_mutate("archive.sha256", "48008c50"), "RELEASE_VALUE_INVALID", "archive.sha256"),
    (_mutate("image.config_digest", "35e1bc8790292deedf2addc3f3f196e38d84c2614219a95d6ef711c1f02afba5"),
     "RELEASE_VALUE_INVALID", "image.config_digest"),
    (_mutate("source_revision", "420c7bcb75"), "RELEASE_VALUE_INVALID", "source_revision"),
    (_mutate("archive.size", 0), "RELEASE_VALUE_INVALID", "archive.size"),
    (_mutate("service.data_dir", "data/services/vikunja/data"), "RELEASE_VALUE_INVALID", "service.data_dir"),
    (_mutate("roots.snapshots", "/data/services/../etc"), "RELEASE_VALUE_INVALID", "roots.snapshots"),
    (_mutate("schema_version", 2), "RELEASE_VALUE_INVALID", "schema_version"),
    (_mutate("tags.release", "office2.local/vikunja:v2.4.0"), "RELEASE_VALUE_INVALID", "tags.release"),
])
def test_release_record_refuses_invalid(tmp_path, mutation, code, key):
    good = _write_json(tmp_path / "good.json", _record())
    assert core.load_release(good)["schema_version"] == 1  # positive control, same fixture
    rec = _record()
    mutation(rec)
    bad = _write_json(tmp_path / "bad.json", rec)
    with pytest.raises(core.ReleaseError) as exc:
        core.load_release(bad)
    assert exc.value.code == code
    assert exc.value.key == key


def test_release_record_refuses_malformed_json_and_absence(tmp_path):
    good = _write_json(tmp_path / "release.json", _record())
    assert core.load_release(good)  # positive control
    good.write_text(_RELEASE.read_text(encoding="utf-8")[:-20], encoding="utf-8")
    with pytest.raises(core.ReleaseError) as exc:
        core.load_release(good)
    assert exc.value.code == "RELEASE_UNREADABLE"
    with pytest.raises(core.ReleaseError) as exc:
        core.load_release(tmp_path / "absent.json")
    assert exc.value.code == "RELEASE_UNREADABLE"
    assert isinstance(exc.value, core.Fail)


# ---------------------------------------------------------------------------
# T002 — errors, output allowlist, private log, CLI exit codes
# ---------------------------------------------------------------------------


def test_fail_requires_a_stable_code():
    exc = core.Fail("ARCHIVE_SHA_MISMATCH", detail_private=SEEDED_RAW)
    assert exc.code == "ARCHIVE_SHA_MISMATCH"
    assert SECRET not in str(exc)
    with pytest.raises(ValueError):
        core.Fail("not a code")


def test_emit_passes_allowlisted_kinds():
    out = io.StringIO()
    line = core.emit("STAGE_VERIFIED", out, code="STAGE_OK", image=RELEASE_ID, short="60fe1ee8f729",
                     count=42, path="/data/services/vikunja/snapshots/20261030T120000Z",
                     ppath=Path("/tmp/x.log"), at="2026-10-30T12:00:00Z", version="v2.7.1-670-420c7bcb75",
                     phase="started_new", outcome="rolled_back", missing=None)
    assert line == ("STAGE_VERIFIED code=STAGE_OK image=" + RELEASE_ID + " short=60fe1ee8f729 count=42"
                    " path=/data/services/vikunja/snapshots/20261030T120000Z ppath=/tmp/x.log"
                    " at=2026-10-30T12:00:00Z version=v2.7.1-670-420c7bcb75 phase=started_new"
                    " outcome=rolled_back missing=-")
    assert out.getvalue() == line + "\n"


@pytest.mark.parametrize("value", [
    SEEDED_RAW, SECRET, TITLE, USER_NAME, "hunter2", f"owner={USER_NAME}", f"task: {TITLE}",
    True, 1.5, b"bytes", ["list"],
    "relative/path", "/data/../etc/shadow", "/tmp/with space", Path("relative"),
])
def test_emit_redacts_everything_else(value):
    out = io.StringIO()
    line = core.emit("STAGE_REFUSED", out, code="STAGE_OK", value=value)
    assert line == "STAGE_REFUSED code=STAGE_OK value=REDACTED"  # summary and code pass: positive control


def test_codes_print_only_under_code_keys():
    out = io.StringIO()
    line = core.emit("STAGE_REFUSED", out, code="ARCHIVE_SHA_MISMATCH", error="TIMEOUT_DOCKER_LOAD",
                     failed_code="STAGE_VERIFY_FAILED", detail="ARCHIVE_SHA_MISMATCH")
    assert line == ("STAGE_REFUSED code=ARCHIVE_SHA_MISMATCH error=TIMEOUT_DOCKER_LOAD"
                    " failed_code=STAGE_VERIFY_FAILED detail=REDACTED")


@pytest.mark.parametrize("leak", SEEDED_SUMMARY_LEAKS + [SEEDED_RAW, "two\nlines", "", None, 7])
def test_summary_is_a_registered_identifier_never_free_text(leak):
    out = io.StringIO()
    assert core.emit("STAGE_REFUSED", out) == "STAGE_REFUSED"  # positive control: registered summary
    line = core.emit(leak, out, code="STAGE_REFUSED")
    assert line == "REDACTED code=STAGE_REFUSED"
    for needle in (SECRET, "hunter2", TITLE, USER_NAME, "HUNTER2_TOKEN"):
        assert needle not in out.getvalue()


@pytest.mark.parametrize("bad", [SECRET, TITLE, USER_NAME, "stage verified", "", "X", None])
def test_register_summaries_accepts_only_identifiers(bad):
    core.register_summaries("STAGE_VERIFIED")  # positive control
    assert "STAGE_VERIFIED" in core.registered_summaries()
    with pytest.raises(ValueError):
        core.register_summaries(bad)
    assert bad not in core.registered_summaries()


def test_privacy_seeded_raw_text_reaches_only_the_private_file(tmp_path, capsys):
    root = tmp_path / "failures"
    log = core.write_private_log(root, "docker-load", SEEDED_RAW)
    line = core.emit("STAGE_LOAD_FAILED", code="STAGE_LOAD_FAILED", detail=SEEDED_RAW, private_log=log)
    assert line.startswith("STAGE_LOAD_FAILED code=STAGE_LOAD_FAILED")  # positive control
    for leak in SEEDED_SUMMARY_LEAKS:  # summary position, then field position
        core.emit(leak, code="STAGE_LOAD_FAILED")
        core.emit("STAGE_LOAD_FAILED", detail=leak, other=leak)
    captured = capsys.readouterr()
    for needle in (SECRET, "hunter2", TITLE, USER_NAME, "HUNTER2_TOKEN"):
        assert needle not in captured.out
        assert needle not in captured.err
    assert f"private_log={log}" in captured.out
    assert captured.out.count("REDACTED code=STAGE_LOAD_FAILED") == len(SEEDED_SUMMARY_LEAKS)
    # positive control: the raw text is in the private file, which is 0600 in a 0700 folder
    text = log.read_text(encoding="utf-8")
    assert SECRET in text and TITLE in text and USER_NAME in text
    assert stat.S_IMODE(os.stat(log).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(root).st_mode) == 0o700
    assert log.parent == root


def test_private_log_tightens_an_existing_root_and_never_overwrites(tmp_path):
    root = tmp_path / "failures"
    root.mkdir(mode=0o755)
    os.chmod(root, 0o755)
    from datetime import datetime, timezone
    now = datetime(2026, 10, 30, 12, 0, 0, tzinfo=timezone.utc)
    first = core.write_private_log(root, "logs", "one", now=now)
    second = core.write_private_log(root, "logs", "two", now=now)
    assert first != second
    assert first.read_text() == "one" and second.read_text() == "two"
    assert stat.S_IMODE(os.stat(root).st_mode) == 0o700
    with pytest.raises(core.Fail) as exc:
        core.write_private_log(root, "../escape", "x")
    assert exc.value.code == "PRIVATE_LOG_NAME_INVALID"


@pytest.mark.parametrize("argv", [[], ["--force"], ["--dry-run", "--apply"], ["--apply", "x"], ["dry-run"]])
def test_run_cli_usage_exits_2(argv):
    out, err = io.StringIO(), io.StringIO()
    seen = []
    assert core.run_cli(["--dry-run"], "prog", seen.append, stdout=out, stderr=err) == 0  # positive control
    assert seen == ["dry-run"]
    rc = core.run_cli(argv, "prog", seen.append, stdout=out, stderr=err)
    assert rc == core.EXIT_USAGE == 2
    assert "usage: prog --dry-run | --apply" in err.getvalue()
    assert seen == ["dry-run"]  # body never ran


def test_run_cli_modes_and_failures(tmp_path):
    out, err = io.StringIO(), io.StringIO()
    seen = []
    assert core.run_cli(["--apply"], "prog", seen.append, stdout=out, stderr=err) == core.EXIT_OK
    assert seen == ["apply"]

    def failing(mode):
        raise core.Fail("DOCKER_INSPECT_FAILED", detail_private=SEEDED_RAW)

    root = tmp_path / "failures"
    rc = core.run_cli(["--apply"], "prog", failing, private_root=root, stdout=out, stderr=err)
    assert rc == core.EXIT_FAIL == 1
    text = out.getvalue() + err.getvalue()
    assert "FAILED code=DOCKER_INSPECT_FAILED private_log=/" in text
    for needle in (SECRET, TITLE, USER_NAME):
        assert needle not in text
    logs = list(root.iterdir())
    assert len(logs) == 1 and SECRET in logs[0].read_text()  # positive control


def test_run_cli_hides_unexpected_exception_text(tmp_path):
    out, err = io.StringIO(), io.StringIO()

    def boom(mode):
        raise RuntimeError(SEEDED_RAW)

    root = tmp_path / "failures"
    assert core.run_cli(["--dry-run"], "prog", boom, private_root=root, stdout=out, stderr=err) == 1
    text = out.getvalue() + err.getvalue()
    assert "code=INTERNAL_ERROR" in text
    assert SECRET not in text and TITLE not in text
    (log,) = root.iterdir()
    assert "RuntimeError" in log.read_text() and SECRET in log.read_text()


# ---------------------------------------------------------------------------
# T003 — bounded runner and deadline
# ---------------------------------------------------------------------------


def test_run_passes_timeout_and_never_a_shell():
    fake = FakeRunner({("docker", "version"): (0, "ok\n", "")})
    assert core.run(["docker", "version"], 30, step="DOCKER_VERSION", runner=fake) == (0, "ok\n", "")
    (argv, kwargs), = fake.calls
    assert argv == ["docker", "version"]
    assert kwargs["timeout"] == 30
    assert kwargs.get("shell", False) is False
    assert kwargs["stdin"] is subprocess.DEVNULL


def test_run_timeout_becomes_a_stable_code():
    ok = FakeRunner({("docker", "load", "-i", "/x"): (0, "Loaded image ID: " + RELEASE_ID, "")})
    assert core.run(["docker", "load", "-i", "/x"], 300, step="DOCKER_LOAD", runner=ok)[0] == 0
    hang = FakeRunner(raise_exc=subprocess.TimeoutExpired(["docker", "load"], 300, stderr=SEEDED_RAW))
    with pytest.raises(core.Fail) as exc:
        core.run(["docker", "load", "-i", "/x"], 300, step="DOCKER_LOAD", runner=hang)
    assert exc.value.code == "TIMEOUT_DOCKER_LOAD"
    assert SECRET not in str(exc.value)
    assert SECRET in exc.value.detail_private


def test_run_exec_failure_and_argument_checks():
    ok = FakeRunner({("docker", "info"): (0, "{}", "")})
    assert core.run(["docker", "info"], 30, step="DOCKER_INFO", runner=ok) == (0, "{}", "")  # positive control
    with pytest.raises(core.Fail) as exc:
        core.run(["docker", "info"], 30, step="DOCKER_INFO", runner=FakeRunner(raise_exc=FileNotFoundError("docker")))
    assert exc.value.code == "EXEC_FAILED_DOCKER_INFO"
    fake = FakeRunner({("docker", "info"): (0, "{}", "")})
    assert core.run(["docker", "info"], 30, step="DOCKER_INFO", runner=fake)[0] == 0  # positive control
    fake.calls.clear()
    for bad in (0, -1, None, True):
        with pytest.raises(ValueError):
            core.run(["docker", "info"], bad, step="DOCKER_INFO", runner=fake)
    with pytest.raises(ValueError):
        core.run("docker info", 30, step="DOCKER_INFO", runner=fake)
    with pytest.raises(ValueError):
        core.run(["docker", "info"], 30, step="lower", runner=fake)
    assert fake.calls == []


def test_core_source_never_uses_a_shell():
    src = _CORE_SRC.read_text(encoding="utf-8")
    assert "shell=True" not in src
    assert "os.system" not in src and "Popen" not in src
    assert "__main__" not in src  # no entrypoint logic


class FakeClock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


def test_deadline_with_a_fake_clock():
    clock = FakeClock()
    d = core.Deadline(300, clock=clock)
    assert d.remaining() == 300
    clock.t += 120
    d.check("ACTIVATE_OUTAGE")  # positive control: time remains
    assert d.remaining() == 180
    assert d.cap(120, "ACTIVATE_OUTAGE") == 120
    clock.t += 100
    assert d.cap(120, "ACTIVATE_OUTAGE") == 80
    clock.t += 80
    with pytest.raises(core.Fail) as exc:
        d.check("ACTIVATE_OUTAGE")
    assert exc.value.code == "ACTIVATE_OUTAGE_DEADLINE"
    with pytest.raises(core.Fail):
        d.cap(30, "ACTIVATE_OUTAGE")
    assert d.remaining() == 0


# ---------------------------------------------------------------------------
# T004 — docker store preflight and identity
# ---------------------------------------------------------------------------


def test_store_preflight_accepts_office2_classic_store():
    fake = _office2_runner()
    assert core.docker_store_ok(fake) is True
    (argv, kwargs), = fake.calls
    assert kwargs["timeout"] == 30


@pytest.mark.parametrize("info", [
    {"Driver": "overlay2", "DriverStatus": [["driver-type", "io.containerd.snapshotter.v1"]]},
    {"Driver": "overlayfs", "DriverStatus": [["driver-type", "io.containerd.snapshotter.v1"]]},
    {"Driver": "vfs", "DriverStatus": []},
    {"DriverStatus": []},
    {"Driver": "overlay2", "DriverStatus": "oops"},
    ["not", "a", "dict"],
])
def test_store_preflight_refuses_anything_else(info):
    assert core.docker_store_ok(_office2_runner()) is True  # positive control
    fake = FakeRunner({_info_argv(): (0, json.dumps(info), "")})
    with pytest.raises(core.Fail) as exc:
        core.docker_store_ok(fake)
    assert exc.value.code == "DOCKER_STORE_UNSUPPORTED"


def test_store_preflight_unreachable_and_unparseable():
    good = json.dumps(_fixture("docker_info.json"))
    assert core.docker_store_ok(FakeRunner({_info_argv(): (0, good, "")})) is True  # positive control
    with pytest.raises(core.Fail) as exc:
        core.docker_store_ok(FakeRunner({_info_argv(): (1, "", f"Cannot connect {SECRET}\n")}))
    assert exc.value.code == "DOCKER_UNREACHABLE"
    assert SECRET not in exc.value.code
    with pytest.raises(core.Fail) as exc:
        core.docker_store_ok(FakeRunner({_info_argv(): (0, "not json", "")}))
    assert exc.value.code == "DOCKER_STORE_UNSUPPORTED"


def test_image_id_present_and_absent():
    fake = _office2_runner()
    assert core.image_id("vikunja/vikunja:2.4.0", runner=fake) == ROLLBACK_ID  # positive control
    assert core.image_id("office2.local/vikunja:active", runner=fake) is None
    assert all(kw["timeout"] == 30 for _, kw in fake.calls)


def test_image_id_errors_are_not_absence():
    ok = FakeRunner({_image_id_argv("vikunja/vikunja:2.4.0"): (0, ROLLBACK_ID + "\n", "")})
    assert core.image_id("vikunja/vikunja:2.4.0", runner=ok) == ROLLBACK_ID  # positive control
    fake = FakeRunner({_image_id_argv("vikunja/vikunja:2.4.0"): (1, "", f"permission denied {SECRET}\n")})
    with pytest.raises(core.Fail) as exc:
        core.image_id("vikunja/vikunja:2.4.0", runner=fake)
    assert exc.value.code == "DOCKER_INSPECT_FAILED"
    fake = FakeRunner({_image_id_argv("vikunja/vikunja:2.4.0"): (0, "garbage\n", "")})
    with pytest.raises(core.Fail) as exc:
        core.image_id("vikunja/vikunja:2.4.0", runner=fake)
    assert exc.value.code == "DOCKER_INSPECT_UNPARSEABLE"
    with pytest.raises(ValueError):
        core.image_id("--format=x", runner=fake)


def test_image_facts_for_captured_and_release_shapes():
    fake = _office2_runner()
    assert core.image_facts("vikunja/vikunja:2.4.0", runner=fake) == {
        "id": ROLLBACK_ID, "architecture": "amd64", "os": "linux", "user": "1000", "revision": None}
    assert core.image_facts("office2.local/vikunja:v2.7.1-670-420c7bcb75", runner=fake) == {
        "id": RELEASE_ID, "architecture": "amd64", "os": "linux", "user": "1000",
        "revision": "420c7bcb75231be9b6571fdfdf76a1a62f2aebd8"}
    assert core.image_facts("office2.local/vikunja:active", runner=fake) is None


def test_container_image_present_and_absent():
    fake = _office2_runner()
    assert core.container_image("vikunja", runner=fake) == (ROLLBACK_ID, "vikunja/vikunja:2.4.0")
    assert core.container_image("absent", runner=fake) is None
    argv, _ = fake.calls[0]
    assert "{{json .}}" not in argv  # never reads the container environment


def test_identity_calls_are_read_only_verbs():
    fake = _office2_runner()
    core.docker_store_ok(fake)
    core.image_id("vikunja/vikunja:2.4.0", runner=fake)
    core.image_facts("vikunja/vikunja:2.4.0", runner=fake)
    core.container_image("vikunja", runner=fake)
    verbs = {tuple(argv[1:3]) if argv[1] in ("image", "container") else (argv[1],) for argv, _ in fake.calls}
    assert verbs == {("info",), ("image", "inspect"), ("container", "inspect")}


# ---------------------------------------------------------------------------
# T005 — offline archive chain
# ---------------------------------------------------------------------------


def _add(tar: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    tar.addfile(info, io.BytesIO(data))


def _build_archive(tmp_path: Path, *, config=None, blob_override=None, index=None,
                   manifest_config=None, name="image.tar"):
    """A tiny OCI layout with the real archive's structure.

    Returns ``(path, record)``, the record carrying the computed size, sha
    and config digest, so an intact build verifies.
    """
    cfg = config if config is not None else _fixture("config.json")
    cfg_bytes = json.dumps(cfg, sort_keys=True).encode()
    cfg_hex = hashlib.sha256(cfg_bytes).hexdigest()
    layers = [b"layer-%d" % n for n in range(1, 5)]
    layer_names = [f"blobs/sha256/{hashlib.sha256(b).hexdigest()}" for b in layers]
    manifest = _fixture("manifest.json")
    manifest[0]["Config"] = manifest_config or f"blobs/sha256/{cfg_hex}"
    manifest[0]["Layers"] = layer_names
    path = tmp_path / name
    with tarfile.open(path, "w") as tar:
        _add(tar, "oci-layout", b'{"imageLayoutVersion":"1.0.0"}')
        _add(tar, "index.json", json.dumps(index if index is not None else _fixture("index.json")).encode())
        _add(tar, "manifest.json", json.dumps(manifest).encode())
        _add(tar, f"blobs/sha256/{cfg_hex}", blob_override if blob_override is not None else cfg_bytes)
        for lname, data in zip(layer_names, layers):
            _add(tar, lname, data)
    rec = _record()
    rec["archive"]["path"] = str(path)
    rec["archive"]["size"] = path.stat().st_size
    rec["archive"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    rec["image"]["config_digest"] = f"sha256:{cfg_hex}"
    return path, rec


def test_fixtures_mirror_the_real_archive_shapes():
    index = _fixture("index.json")
    assert index["schemaVersion"] == 2
    assert index["manifests"][0]["digest"] == INDEX_DIGEST == _record()["image"]["index_digest"]
    manifest = _fixture("manifest.json")
    assert manifest[0]["Config"] == "blobs/sha256/" + RELEASE_ID.split(":")[1]
    assert manifest[0]["RepoTags"] is None and len(manifest[0]["Layers"]) == 4


def test_intact_archive_verifies_without_extracting(tmp_path):
    path, rec = _build_archive(tmp_path)
    before = sorted(p.name for p in tmp_path.iterdir())
    facts = core.verify_archive(path, rec)
    assert facts == {"sha256": rec["archive"]["sha256"], "size": rec["archive"]["size"],
                     "index_digest": INDEX_DIGEST, "config_digest": rec["image"]["config_digest"]}
    assert sorted(p.name for p in tmp_path.iterdir()) == before == ["image.tar"]


def _cfg(**changes):
    cfg = _fixture("config.json")
    for dotted, value in changes.items():
        node = cfg
        *parents, leaf = dotted.split("__")
        for p in parents:
            node = node[p]
        node[leaf] = value
    return cfg


@pytest.mark.parametrize("kwargs, code", [
    (dict(blob_override=b'{"architecture":"amd64","os":"linux","tampered":true}'), "ARCHIVE_CONFIG_HASH_MISMATCH"),
    (dict(config=_cfg(config__Labels={"org.opencontainers.image.revision": "0" * 40})), "ARCHIVE_REVISION_MISMATCH"),
    (dict(config=_cfg(config__Labels=None)), "ARCHIVE_REVISION_MISMATCH"),
    (dict(config=_cfg(architecture="arm64")), "ARCHIVE_ARCH_MISMATCH"),
    (dict(config=_cfg(os="windows")), "ARCHIVE_OS_MISMATCH"),
    (dict(config=_cfg(config__User="0")), "ARCHIVE_USER_MISMATCH"),
    (dict(index={"schemaVersion": 2, "manifests": [{"digest": "sha256:" + "1" * 64}]}), "ARCHIVE_INDEX_MISMATCH"),
    (dict(index={"schemaVersion": 2, "manifests": [{"digest": INDEX_DIGEST}, {"digest": INDEX_DIGEST}]}),
     "ARCHIVE_INDEX_MISMATCH"),
    (dict(manifest_config="blobs/sha256/" + "2" * 64), "ARCHIVE_MANIFEST_MISMATCH"),
])
def test_archive_mutations_fail(tmp_path, kwargs, code):
    good_path, good_rec = _build_archive(tmp_path, name="intact.tar")
    assert core.verify_archive(good_path, good_rec)  # positive control
    path, rec = _build_archive(tmp_path, name="mutated.tar", **kwargs)
    with pytest.raises(core.Fail) as exc:
        core.verify_archive(path, rec)
    assert exc.value.code == code


def test_archive_record_digest_mismatch_fails(tmp_path):
    path, rec = _build_archive(tmp_path)
    assert core.verify_archive(path, rec)  # positive control
    wrong = copy.deepcopy(rec)
    wrong["image"]["config_digest"] = RELEASE_ID  # a tar whose config is not the pinned one
    with pytest.raises(core.Fail) as exc:
        core.verify_archive(path, wrong)
    assert exc.value.code == "ARCHIVE_MANIFEST_MISMATCH"


def test_archive_size_sha_and_presence(tmp_path):
    path, rec = _build_archive(tmp_path)
    assert core.verify_archive(path, rec)  # positive control
    for key, value, code in (("size", rec["archive"]["size"] + 1, "ARCHIVE_SIZE_MISMATCH"),
                             ("sha256", "0" * 64, "ARCHIVE_SHA_MISMATCH")):
        bad = copy.deepcopy(rec)
        bad["archive"][key] = value
        with pytest.raises(core.Fail) as exc:
            core.verify_archive(path, bad)
        assert exc.value.code == code
    with pytest.raises(core.Fail) as exc:
        core.verify_archive(tmp_path / "absent.tar", rec)
    assert exc.value.code == "ARCHIVE_MISSING"


def test_archive_that_is_not_a_tar_is_unreadable(tmp_path):
    path, rec = _build_archive(tmp_path)
    assert core.verify_archive(path, rec)  # positive control
    junk = tmp_path / "junk.tar"
    junk.write_bytes(b"\x00not a tar" * 100)
    bad = copy.deepcopy(rec)
    bad["archive"]["size"] = junk.stat().st_size
    bad["archive"]["sha256"] = hashlib.sha256(junk.read_bytes()).hexdigest()
    with pytest.raises(core.Fail) as exc:
        core.verify_archive(junk, bad)
    assert exc.value.code == "ARCHIVE_UNREADABLE"


def _raw_header(name: bytes, size: int, typeflag: bytes) -> bytes:
    """One ustar header block with a valid checksum."""
    b = bytearray(512)
    b[0:len(name)] = name
    b[100:108] = b"0000644\0"
    b[108:116] = b"0000000\0"
    b[116:124] = b"0000000\0"
    b[124:136] = b"%011o\0" % size
    b[136:148] = b"00000000000\0"
    b[148:156] = b" " * 8
    b[156:157] = typeflag
    b[257:263] = b"ustar\0"
    b[263:265] = b"00"
    b[148:156] = b"%06o\0 " % sum(b)
    return bytes(b)


def _pax_header(key: str, value: str) -> bytes:
    body = f" {key}={value}\n".encode()
    n = len(body)
    while len(str(n).encode()) + len(body) != n:
        n = len(str(n).encode()) + len(body)
    record = str(n).encode() + body
    pad = -len(record) % 512
    return _raw_header(b"././@PaxHeader", len(record), b"x") + record + b"\0" * pad


class _Spy:
    """Counts calls and delegates to the real function."""

    def __init__(self, real):
        self.real = real
        self.calls = 0

    def __call__(self, *a, **kw):
        self.calls += 1
        return self.real(*a, **kw)


def test_unpinned_hostile_archive_is_refused_before_tar_parsing(tmp_path, monkeypatch):
    tar_open = _Spy(tarfile.open)
    monkeypatch.setattr(tarfile, "open", tar_open)
    path, rec = _build_archive(tmp_path)  # builds before counting starts
    tar_open.calls = 0
    assert core.verify_archive(path, rec)  # positive control: the pinned bytes are parsed
    assert tar_open.calls == 1
    # Same length as the pinned archive, so the size check passes and only the
    # sha stands between the hostile bytes and the parser.
    size = path.stat().st_size
    nested = _pax_header("comment", "x") * (size // 1024 + 1)
    hostile = tmp_path / "hostile.tar"
    hostile.write_bytes(nested[:size])
    assert hostile.stat().st_size == rec["archive"]["size"]
    with pytest.raises(core.Fail) as exc:
        core.verify_archive(hostile, rec)
    assert exc.value.code == "ARCHIVE_SHA_MISMATCH"
    assert tar_open.calls == 1  # tarfile never opened the hostile bytes


def test_size_mismatch_is_refused_before_hashing_or_parsing(tmp_path, monkeypatch):
    path, rec = _build_archive(tmp_path)
    hasher = _Spy(core._sha256_handle)
    tar_open = _Spy(tarfile.open)
    monkeypatch.setattr(core, "_sha256_handle", hasher)
    monkeypatch.setattr(tarfile, "open", tar_open)
    assert core.verify_archive(path, rec)  # positive control: hashed once, parsed once
    assert (hasher.calls, tar_open.calls) == (1, 1)
    # 3000 nested PAX headers: plain tarfile raises RecursionError on these.
    hostile = tmp_path / "nested-pax.tar"
    hostile.write_bytes(_pax_header("comment", "x") * 3000 + path.read_bytes())
    with pytest.raises(core.Fail) as exc:
        core.verify_archive(hostile, rec)
    assert exc.value.code == "ARCHIVE_SIZE_MISMATCH"
    assert (hasher.calls, tar_open.calls) == (1, 1)


def test_tarfile_parses_the_hashed_handle_never_a_path(tmp_path, monkeypatch):
    path, rec = _build_archive(tmp_path)
    hashed = []
    opened = []
    real_hash, real_open = core._sha256_handle, tarfile.open

    def hash_spy(fh):
        hashed.append(fh)
        return real_hash(fh)

    def open_spy(*args, **kwargs):
        opened.append((args, kwargs))
        return real_open(*args, **kwargs)

    monkeypatch.setattr(core, "_sha256_handle", hash_spy)
    monkeypatch.setattr(tarfile, "open", open_spy)
    facts = core.verify_archive(path, rec)
    assert facts["config_digest"] == rec["image"]["config_digest"]
    assert len(hashed) == 1 and len(opened) == 1
    args, kwargs = opened[0]
    assert args == ()  # no positional name
    assert "name" not in kwargs
    assert kwargs["fileobj"] is hashed[0]  # the very handle that was hashed
    assert kwargs["mode"] == "r:"


def test_path_swap_after_hash_does_not_reach_the_parser(tmp_path, monkeypatch):
    path, rec = _build_archive(tmp_path)
    expected = core.verify_archive(path, rec)  # positive control: the normal intact run
    hostile_dir = tmp_path / "hostile"
    hostile_dir.mkdir()
    hostile, hostile_rec = _build_archive(hostile_dir, config=_cfg(architecture="arm64"))
    with pytest.raises(core.Fail) as exc:  # the hostile archive really would fail if parsed
        core.verify_archive(hostile, hostile_rec)
    assert exc.value.code == "ARCHIVE_ARCH_MISMATCH"
    hostile_bytes = hostile.read_bytes()
    real_hash = core._sha256_handle
    swaps = []

    def hash_then_swap(fh):
        digest = real_hash(fh)
        os.replace(hostile, path)  # swap the path right after the hash
        swaps.append(True)
        return digest

    monkeypatch.setattr(core, "_sha256_handle", hash_then_swap)
    assert core.verify_archive(path, rec) == expected  # the intact, hashed bytes were parsed
    assert swaps == [True]
    assert path.read_bytes() == hostile_bytes  # the swap did happen on the path


def test_parser_failures_on_pinned_bytes_map_to_a_stable_code(tmp_path, monkeypatch):
    path, rec = _build_archive(tmp_path)
    assert core.verify_archive(path, rec)  # positive control
    for error in (RecursionError(), MemoryError(), OverflowError(), tarfile.ReadError(), ValueError()):
        def broken(*a, _e=error, **kw):
            raise _e
        monkeypatch.setattr(tarfile, "open", broken)
        with pytest.raises(core.Fail) as exc:
            core.verify_archive(path, rec)
        assert exc.value.code == "ARCHIVE_UNREADABLE"


def test_core_has_no_tar_prescan():
    src = _CORE_SRC.read_text(encoding="utf-8")
    for gone in ("_prescan_tar", "MAX_TAR_", "_tar_size", "ARCHIVE_METADATA_LIMIT"):
        assert gone not in src


def test_verify_size_and_sha_for_hash_only_archives(tmp_path):
    blob = tmp_path / "vikunja-2.4.0.image.tar"
    blob.write_bytes(b"rollback-archive-bytes" * 100)
    size, sha = blob.stat().st_size, hashlib.sha256(blob.read_bytes()).hexdigest()
    assert core.verify_size_and_sha(blob, size, sha) is None  # positive control
    assert core.sha256_file(blob) == sha
    for args, code in (((size + 1, sha), "ARCHIVE_SIZE_MISMATCH"), ((size, "0" * 64), "ARCHIVE_SHA_MISMATCH")):
        with pytest.raises(core.Fail) as exc:
            core.verify_size_and_sha(blob, *args)
        assert exc.value.code == code
    with pytest.raises(core.Fail) as exc:
        core.verify_size_and_sha(tmp_path / "absent.tar", size, sha)
    assert exc.value.code == "ARCHIVE_MISSING"
    with pytest.raises(core.Fail) as exc:
        core.verify_size_and_sha(tmp_path, size, sha)
    assert exc.value.code == "ARCHIVE_UNREADABLE"
    fifo = tmp_path / "fifo.tar"
    os.mkfifo(fifo)
    with pytest.raises(core.Fail) as exc:  # O_NONBLOCK: refused, never hangs
        core.verify_size_and_sha(fifo, size, sha)
    assert exc.value.code == "ARCHIVE_UNREADABLE"


def test_sha256_streams_in_1mib_chunks(tmp_path, monkeypatch):
    big = tmp_path / "big.bin"
    data = os.urandom(core.CHUNK * 2 + 17)
    big.write_bytes(data)
    assert core.CHUNK == 1024 * 1024
    reads = []
    real_open = open

    class Spy:
        def __init__(self, fh):
            self.fh = fh

        def read(self, n):
            reads.append(n)
            return self.fh.read(n)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            self.fh.close()

    monkeypatch.setattr(core, "open", lambda p, m="r": Spy(real_open(p, m)), raising=False)
    assert core.sha256_file(big) == hashlib.sha256(data).hexdigest()
    assert set(reads) == {core.CHUNK}


# ---------------------------------------------------------------------------
# T006 — durable marker I/O
# ---------------------------------------------------------------------------


def _marker(**overrides):
    data = {"phase": "started", "started_at": "2026-10-30T12:00:00Z", "outcome": None,
            "snapshot_dir": None, "snapshot_sha": None}
    data.update(overrides)
    return data


def test_marker_create_is_exclusive_and_durable(tmp_path, monkeypatch):
    synced = []
    real = core._fsync_dir
    monkeypatch.setattr(core, "_fsync_dir", lambda d: (synced.append(Path(d)), real(d)))
    path = tmp_path / "v2.7.1-670-420c7bcb75.json"
    core.marker_create(path, _marker())
    assert core.marker_read(path) == _marker()  # positive control
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert synced == [tmp_path]
    with pytest.raises(core.Fail) as exc:
        core.marker_create(path, _marker(phase="verified", outcome="success"))
    assert exc.value.code == "MARKER_EXISTS"
    assert core.marker_read(path) == _marker()  # the first marker is untouched


def test_marker_create_refuses_unsafe_data(tmp_path):
    ok = tmp_path / "ok.json"
    core.marker_create(ok, _marker(error="ACTIVATE_OUTAGE_DEADLINE"))  # positive control
    path = tmp_path / "bad.json"
    for data in (_marker(phase="booting"), _marker(outcome="maybe"), _marker(error=SEEDED_RAW)):
        with pytest.raises(core.Fail) as exc:
            core.marker_create(path, data)
        assert exc.value.code == "MARKER_INVALID"
        assert not path.exists()


def test_marker_update_replaces_atomically(tmp_path, monkeypatch):
    path = tmp_path / "m.json"
    core.marker_create(path, _marker())
    synced = []
    real = core._fsync_dir
    monkeypatch.setattr(core, "_fsync_dir", lambda d: (synced.append(Path(d)), real(d)))
    new = _marker(phase="snapshotted", snapshot_dir="/data/services/vikunja/snapshots/20261030T120000Z",
                  snapshot_sha="ab" * 32)
    core.marker_update(path, new)
    assert core.marker_read(path) == new
    assert synced == [tmp_path]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["m.json"]


class SimulatedCrash(BaseException):
    """Stands in for the process dying between the temp write and the replace."""


def test_interrupted_update_leaves_the_old_marker_readable(tmp_path, monkeypatch):
    path = tmp_path / "m.json"
    core.marker_create(path, _marker())

    def crash(src, dst, *a, **kw):
        raise SimulatedCrash()

    monkeypatch.setattr(os, "replace", crash)
    with pytest.raises(SimulatedCrash):
        core.marker_update(path, _marker(phase="stopped"))
    monkeypatch.undo()
    assert core.marker_read(path) == _marker()
    core.marker_update(path, _marker(phase="stopped"))  # positive control: same file updates fine
    assert core.marker_read(path)["phase"] == "stopped"


def test_marker_update_requires_an_existing_marker(tmp_path):
    path = tmp_path / "m.json"
    with pytest.raises(core.Fail) as exc:
        core.marker_update(path, _marker(phase="stopped"))
    assert exc.value.code == "MARKER_MISSING"
    assert not path.exists()
    core.marker_create(path, _marker())
    core.marker_update(path, _marker(phase="stopped"))  # positive control
    assert core.marker_read(path)["phase"] == "stopped"


@pytest.mark.parametrize("phase, outcome", [
    ("verified", "success"), ("retagged", "failed"), ("verified", "rolled_back"), ("started_new", None),
])
def test_marker_read_accepts_known_phases_and_outcomes(tmp_path, phase, outcome):
    path = _write_json(tmp_path / "m.json", _marker(phase=phase, outcome=outcome,
                                                     failed_phase="retagged" if outcome == "failed" else None))
    assert core.marker_read(path)["outcome"] == outcome


@pytest.mark.parametrize("content", [
    "{not json", "[]", json.dumps({"outcome": "success"}), json.dumps(_marker(phase="unknown")),
    json.dumps(_marker(outcome="aborted")), json.dumps(_marker(failed_phase="nope", outcome="failed")),
    json.dumps(_marker(error=SEEDED_RAW)), "\xff\xfe",
    json.dumps({"phase": []}), json.dumps({"phase": {}}), json.dumps({"phase": 1}),
    json.dumps({"phase": "started", "outcome": {}}), json.dumps({"phase": "started", "outcome": []}),
    json.dumps({"phase": "started", "failed_phase": []}), json.dumps(_marker(error={"x": 1})),
    "[" * 30000 + "]" * 30000,
    '{"phase": "started", "error": ' + "[" * 30000 + "]" * 30000 + "}",
])
def test_malformed_marker_refuses(tmp_path, content):
    good = _write_json(tmp_path / "good.json", _marker())
    assert core.marker_read(good) == _marker()  # positive control
    path = tmp_path / "m.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(core.Fail) as exc:
        core.marker_read(path)
    assert exc.value.code == "MARKER_UNREADABLE"


def test_deeply_nested_marker_is_unreadable_not_recursion_error(tmp_path):
    good = _write_json(tmp_path / "good.json", _marker())
    assert core.marker_read(good) == _marker()  # positive control
    nested = "[" * 30000 + "]" * 30000
    assert len(nested.encode()) < 64 * 1024  # under the reader's size limit
    with pytest.raises(RecursionError):
        json.loads(nested)  # the decoder itself exhausts the stack on this input
    path = tmp_path / "m.json"
    path.write_text(nested, encoding="utf-8")
    with pytest.raises(core.Fail) as exc:
        core.marker_read(path)
    assert exc.value.code == "MARKER_UNREADABLE"


def test_marker_absent_symlink_and_directory(tmp_path):
    good = _write_json(tmp_path / "good.json", _marker())
    assert core.marker_read(good) == _marker()  # positive control
    assert core.marker_read(tmp_path / "absent.json") is None
    link = tmp_path / "link.json"
    link.symlink_to(good)
    with pytest.raises(core.Fail) as exc:
        core.marker_read(link)
    assert exc.value.code == "MARKER_UNREADABLE"
    (tmp_path / "dir.json").mkdir()
    with pytest.raises(core.Fail) as exc:
        core.marker_read(tmp_path / "dir.json")
    assert exc.value.code == "MARKER_UNREADABLE"


@pytest.mark.parametrize("data", [
    {"phase": []}, {"phase": {}}, {"phase": "started", "outcome": {}}, {"phase": "started", "failed_phase": []},
])
def test_marker_create_refuses_malformed_types(tmp_path, data):
    core.marker_create(tmp_path / "ok.json", _marker())  # positive control
    path = tmp_path / "bad.json"
    with pytest.raises(core.Fail) as exc:
        core.marker_create(path, data)
    assert exc.value.code == "MARKER_INVALID"
    assert not path.exists()


def _one_byte_writes(fd, data):
    return os.write(fd, bytes(data[:1]))


def test_marker_writes_complete_across_short_writes(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "_os_write", _one_byte_writes)
    path = tmp_path / "m.json"
    core.marker_create(path, _marker())
    assert core.marker_read(path) == _marker()
    core.marker_update(path, _marker(phase="stopped"))
    assert core.marker_read(path) == _marker(phase="stopped")


def test_stalled_write_fails_and_keeps_the_old_marker(tmp_path, monkeypatch):
    path = tmp_path / "m.json"
    core.marker_create(path, _marker())
    core.marker_update(path, _marker(phase="stopped"))  # positive control
    monkeypatch.setattr(core, "_os_write", lambda fd, data: 0)
    with pytest.raises(core.Fail) as exc:
        core.marker_update(path, _marker(phase="snapshotted"))
    assert exc.value.code == "MARKER_WRITE_FAILED"
    assert core.marker_read(path) == _marker(phase="stopped")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["m.json"]
    with pytest.raises(core.Fail) as exc:
        core.marker_create(tmp_path / "new.json", _marker())
    assert exc.value.code == "MARKER_WRITE_FAILED"


def test_oversize_marker_is_refused_before_any_mutation(tmp_path):
    path = tmp_path / "m.json"
    core.marker_create(path, _marker())
    near = "/" + "a" * 60000
    core.marker_update(path, _marker(snapshot_dir=near))  # positive control: under 64 KiB
    assert core.marker_read(path)["snapshot_dir"] == near
    huge = "/" + "a" * (64 * 1024)
    with pytest.raises(core.Fail) as exc:
        core.marker_update(path, _marker(snapshot_dir=huge))
    assert exc.value.code == "MARKER_TOO_LARGE"
    assert core.marker_read(path)["snapshot_dir"] == near
    assert sorted(p.name for p in tmp_path.iterdir()) == ["m.json"]
    with pytest.raises(core.Fail) as exc:
        core.marker_create(tmp_path / "new.json", _marker(snapshot_dir=huge))
    assert exc.value.code == "MARKER_TOO_LARGE"
    assert not (tmp_path / "new.json").exists()


def test_phase_and_outcome_sets_match_the_data_model():
    assert core.PHASES == {"started", "stopped", "snapshotted", "retagged", "started_new", "verified"}
    assert core.OUTCOMES == {"success", "failed", "rolled_back"}


def test_module_docstring_lists_later_callers():
    doc = core.__doc__
    for wp in ("WP02", "WP03", "WP04", "WP06", "WP07"):
        assert wp in doc
