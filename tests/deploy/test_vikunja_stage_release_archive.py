"""Tests for the Vikunja ingress helper (#1087, WP07, T030-T032).

No network and no ssh: the runner is injected and the office4 sources are
small files in ``tmp_path``. The record is the real ``release.json`` with only
the source paths, sizes and shas pointed at those files, so the destination
paths are the real office2 ones (never touched: every remote call is faked).
Every refusal has a same-fixture positive control (the passing run).
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_PATH = _ROOT / "scripts" / "vikunja" / "stage_release_archive.py"
_RELEASE = _ROOT / "services" / "vikunja" / "release.json"

_spec = importlib.util.spec_from_file_location("stage_release_archive", _PATH)
mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = mod
_spec.loader.exec_module(mod)

PREFIX = ["ssh", "-o", "BatchMode=yes", "office2-claude"]
DEST = "/data/services/vikunja/release-artifacts/48008c5067a6"
SECRET = "password=hunter2"
TITLE = "Buy anniversary gift for Margot"
SEEDED = f"Permission denied {SECRET} task '{TITLE}'\n"


PARENT = "/data/services/vikunja/release-artifacts"
NONCES = ["0" * 31 + "1", "0" * 31 + "2"]
NOCLOBBER_ERR = "bash: line 1: {}: cannot overwrite existing file\n"


def part(name, i):
    """The ``.part`` path the run with the injected NONCES uses for file *i*."""
    return f"{DEST}/.{name}.{NONCES[i]}.part"


IMG_PART, RB_PART = part("image.tar", 0), part("vikunja-2.4.0.image.tar", 1)
IMG, RB = f"{DEST}/image.tar", f"{DEST}/vikunja-2.4.0.image.tar"


class FakeOffice2:
    """A fake ssh runner holding the remote state of office2.

    ``parent`` is the artifacts parent: ``absent`` (the real office2 state
    on 2026-10-30), ``ok`` (claude-owned real folder, mode 700), ``symlink``,
    ``wrong_owner`` or ``wrong_mode``. ``parent_created`` is the state a
    parent mkdir produces. ``hooks`` maps a remote command prefix to a
    callable run just before that command is served (to stage races).
    """

    def __init__(self, *, dest_exists=False, parent="absent", parent_created="ok",
                 parent_mkdir_fails=False, avail=10 * 1024 ** 3, corrupt=None, ssh_down=False,
                 transfer_timeout=False, hooks=None):
        self.calls: list[list[str]] = []
        self.kwargs: list[dict] = []
        self.files: dict[str, bytes] = {}
        self.parent = parent
        self.parent_created = parent_created
        self.parent_mkdir_fails = parent_mkdir_fails
        self.dirs: set[str] = set()
        if dest_exists:
            self.parent = "ok" if parent == "absent" else parent
            self.dirs.add(DEST)
        self.avail = avail
        self.corrupt = corrupt or set()
        self.ssh_down = ssh_down
        self.transfer_timeout = transfer_timeout
        self.hooks = hooks or {}
        self.removed: list[str] = []
        #: symlinks at a path, mapped to the folder they point at
        self.symlinks: dict[str, str] = {}

    def _done(self, rc, out="", err=""):
        return SimpleNamespace(returncode=rc, stdout=out, stderr=err)

    def _exists(self, path):
        if path == PARENT:
            return self.parent != "absent"
        return path in self.dirs or path in self.files or path in self.symlinks

    def __call__(self, argv, **kwargs):
        assert "timeout" in kwargs and kwargs["timeout"] > 0
        assert kwargs.get("shell") is not True
        self.calls.append(list(argv))
        self.kwargs.append(kwargs)
        assert argv[:4] == PREFIX and len(argv) == 5, argv
        if self.ssh_down:
            return self._done(255, err=SEEDED)
        cmd = argv[4]
        for prefix, hook in self.hooks.items():
            if cmd.startswith(prefix):
                hook(self)
        path = cmd.split()[-1]
        if cmd == mod.parent_safety_command():
            return self._done(0 if self.parent == "ok" else 1)
        if cmd == f"test -e {PARENT} || test -L {PARENT}":
            return self._done(0 if self.parent != "absent" else 1)
        if cmd.startswith("test ! -e "):
            return self._done(1 if self._exists(path) else 0)
        if cmd.startswith("test -e "):
            return self._done(0 if self._exists(path) else 1)
        if cmd.startswith("df --output=avail -B1 "):
            return self._done(0, out=f"       Avail\n{self.avail}\n")
        if cmd == f"umask 077 && mkdir {PARENT}":
            if self.parent != "absent" or self.parent_mkdir_fails:
                return self._done(1, err=SEEDED)
            self.parent = self.parent_created
            return self._done(0)
        if cmd.startswith("umask 077 && mkdir "):
            if self.parent == "absent" or self._exists(path):
                return self._done(1, err=SEEDED)
            self.dirs.add(path)
            return self._done(0)
        if cmd.startswith("set -o noclobber; cat > "):
            if path in self.files:
                return self._done(1, out=b"", err=NOCLOBBER_ERR.format(path).encode())
            if self.transfer_timeout:
                self.files[path] = b"partial"
                raise subprocess.TimeoutExpired(argv, kwargs["timeout"],
                                                stderr=NOCLOBBER_ERR.format(path).encode())
            data = kwargs["stdin"].read()
            final_name = path.rsplit("/", 1)[1][1:].rsplit(".", 2)[0]
            self.files[path] = data + (b"x" if final_name in self.corrupt else b"")
            return self._done(0, out=b"", err=b"")
        if cmd.startswith(("ln -T -- ", "ln -- ")):
            *flags, src, dst = cmd.split()
            target_is_dir = dst in self.dirs or dst in self.symlinks
            if target_is_dir and "-T" not in flags:
                # GNU ln without -T: a folder (or a symlink to one) is a container
                inner = self.symlinks.get(dst, dst) + "/" + src.rsplit("/", 1)[1]
                self.files[inner] = self.files[src]
                return self._done(0)
            if self._exists(dst):
                return self._done(1, err=f"ln: failed to create hard link '{dst}': File exists\n")
            self.files[dst] = self.files[src]
            return self._done(0)
        if " || test -L " in cmd and cmd.startswith("test -e "):
            return self._done(0 if self._exists(path) else 1)
        if cmd.startswith("sha256sum -- "):
            digest = hashlib.sha256(self.files[path]).hexdigest()
            return self._done(0, out=f"{digest}  {path}\n")
        if cmd.startswith("rm -f -- "):
            self.removed.append(path)
            self.files.pop(path, None)
            return self._done(0)
        raise AssertionError(f"unexpected remote command: {cmd}")


@pytest.fixture
def env(tmp_path):
    src = tmp_path / "office4"
    (src / "rel").mkdir(parents=True)
    (src / "rb").mkdir()
    image = src / "rel" / "image.tar"
    rollback = src / "rb" / "vikunja-2.4.0.image.tar"
    image.write_bytes(b"release-archive-bytes" * 100)
    rollback.write_bytes(b"rollback-archive-bytes" * 150)
    record = json.loads(_RELEASE.read_text(encoding="utf-8"))
    record["roots"]["office4_sources"] = {"archive": str(image), "rollback_archive": str(rollback)}
    for key, path in (("archive", image), ("rollback", rollback)):
        target = record["archive"] if key == "archive" else record["rollback"]["archive"]
        target["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        target["size"] = path.stat().st_size
    return SimpleNamespace(tmp=tmp_path, image=image, rollback=rollback, record=record)


def _run(env, mode, runner, record=None):
    rel = env.tmp / "release.json"
    rel.write_text(json.dumps(record if record is not None else env.record), encoding="utf-8")
    out, err = io.StringIO(), io.StringIO()
    nonces = iter(NONCES)
    rc = mod.main([mode], release_path=rel, runner=runner, private_root=env.tmp / "private",
                  stdout=out, stderr=err, nonce=lambda: next(nonces))
    return rc, out.getvalue(), err.getvalue()


def _assert_ssh_only(runner):
    assert runner.calls, "expected at least one remote call"
    for argv in runner.calls:
        assert argv[:4] == PREFIX
        joined = " ".join(argv)
        assert "office2-kgale" not in joined and "office2-codex" not in joined
        assert "sudo" not in joined


def _remote_writes(runner):
    return [a for a in runner.calls if not a[4].startswith(("test ", "df ", "sha256sum "))]


# ---------------------------------------------------------------------------
# Positive controls
# ---------------------------------------------------------------------------

def test_dry_run_passes_and_makes_no_remote_change(env):
    runner = FakeOffice2()
    rc, out, err = _run(env, "--dry-run", runner)
    assert rc == 0, out
    lines = out.splitlines()
    assert lines[0].startswith(f"INGRESS_DRY_RUN_OK dest={DEST} files=2 ")
    assert f"remote={DEST}/image.tar" in out and f"remote={DEST}/vikunja-2.4.0.image.tar" in out
    assert err == ""
    _assert_ssh_only(runner)
    assert _remote_writes(runner) == []
    assert runner.files == {} and DEST not in runner.dirs
    cmds = [a[4] for a in runner.calls]
    assert f"test ! -e {DEST}" in cmds
    assert "df --output=avail -B1 /data" in cmds
    # the real office2 state: the parent is absent, so it would be created
    assert "parent_code=CREATE" in lines[0]
    assert runner.parent == "absent"
    assert mod.parent_safety_command() not in cmds


def test_dry_run_with_existing_parent_verifies_it(env):
    runner = FakeOffice2(parent="ok")
    rc, out, _ = _run(env, "--dry-run", runner)
    assert rc == 0, out
    assert "parent_code=EXISTS" in out.splitlines()[0]
    assert mod.parent_safety_command() in [a[4] for a in runner.calls]
    assert _remote_writes(runner) == []


def test_parent_safety_command_shape():
    cmd = mod.parent_safety_command()
    assert cmd == (f"test -d {PARENT} && test ! -L {PARENT} && test \"$(stat -c %U {PARENT})\" = claude "
                   f"&& test \"$(stat -c %a {PARENT})\" = 700")


def test_apply_transfers_both_and_prints_remote_shas(env):
    runner = FakeOffice2()
    rc, out, _ = _run(env, "--apply", runner)
    assert rc == 0, out
    _assert_ssh_only(runner)
    assert runner.files[f"{DEST}/image.tar"] == env.image.read_bytes()
    assert runner.files[f"{DEST}/vikunja-2.4.0.image.tar"] == env.rollback.read_bytes()
    assert out.splitlines()[0].startswith(f"INGRESS_APPLIED dest={DEST} files=2")
    assert f"sha256={env.record['archive']['sha256']}" in out
    assert f"sha256={env.record['rollback']['archive']['sha256']}" in out
    # only the two parts are removed, each after its publish; no part is left
    assert runner.removed == [IMG_PART, RB_PART]
    assert set(runner.files) == {IMG, RB}
    cmds = [a[4] for a in runner.calls]
    assert f"umask 077 && mkdir {DEST}" in cmds
    assert f"set -o noclobber; cat > {IMG_PART}" in cmds
    seq = [f"test ! -e {IMG}", f"set -o noclobber; cat > {IMG_PART}", f"sha256sum -- {IMG_PART}",
           f"ln -T -- {IMG_PART} {IMG}", f"rm -f -- {IMG_PART}"]
    assert [cmds.index(c) for c in seq] == sorted(cmds.index(c) for c in seq)
    # the absent parent is created without -p, verified, then the sha folder
    mk_parent = cmds.index(f"umask 077 && mkdir {PARENT}")
    verify = cmds.index(mod.parent_safety_command(), mk_parent)
    assert mk_parent < verify < cmds.index(f"umask 077 && mkdir {DEST}")
    assert not any("mkdir -p" in c for c in cmds)
    assert runner.parent == "ok"
    # the local file is fed on stdin; the mkdir happens before any stream
    assert cmds.index(f"umask 077 && mkdir {DEST}") < cmds.index(f"set -o noclobber; cat > {IMG_PART}")
    stream_kwargs = [k for a, k in zip(runner.calls, runner.kwargs) if a[4].startswith("set -o noclobber")]
    assert all(hasattr(k["stdin"], "read") for k in stream_kwargs)


def test_transfer_timeout_scales_with_size(env):
    small = mod.scaled_timeout(1, mod.TRANSFER_BASE, mod.TRANSFER_RATE)
    big = mod.scaled_timeout(115518464, mod.TRANSFER_BASE, mod.TRANSFER_RATE)
    assert small == mod.TRANSFER_BASE + 1
    assert big == mod.TRANSFER_BASE + 111 and big > small
    runner = FakeOffice2()
    assert _run(env, "--apply", runner)[0] == 0
    timeouts = [k["timeout"] for a, k in zip(runner.calls, runner.kwargs) if a[4].startswith("set -o")]
    assert timeouts == [mod.scaled_timeout(env.record["archive"]["size"], mod.TRANSFER_BASE, mod.TRANSFER_RATE),
                        mod.scaled_timeout(env.record["rollback"]["archive"]["size"], mod.TRANSFER_BASE,
                                           mod.TRANSFER_RATE)]


# ---------------------------------------------------------------------------
# Refusals (each against the same fixture that passes above)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mode", ["--dry-run", "--apply"])
def test_source_sha_mismatch_refused_before_any_remote_call(env, mode):
    good = FakeOffice2()
    assert _run(env, mode, good)[0] == 0
    env.rollback.write_bytes(b"x" * env.rollback.stat().st_size)  # same size, other bytes
    runner = FakeOffice2()
    rc, out, _ = _run(env, mode, runner)
    assert rc == 1
    assert out.strip() == "FAILED code=ARCHIVE_SHA_MISMATCH private_log=-"
    assert runner.calls == []


def test_source_size_mismatch_refused(env):
    assert _run(env, "--dry-run", FakeOffice2())[0] == 0
    env.image.write_bytes(env.image.read_bytes() + b"!")
    runner = FakeOffice2()
    rc, out, _ = _run(env, "--dry-run", runner)
    assert rc == 1 and "code=ARCHIVE_SIZE_MISMATCH" in out and runner.calls == []


@pytest.mark.parametrize("mode", ["--dry-run", "--apply"])
def test_existing_destination_refused(env, mode):
    assert _run(env, mode, FakeOffice2())[0] == 0
    runner = FakeOffice2(dest_exists=True)
    rc, out, _ = _run(env, mode, runner)
    assert rc == 1
    assert "code=INGRESS_DEST_EXISTS" in out
    assert _remote_writes(runner) == [] and runner.files == {}


def test_mkdir_race_existing_destination_is_dest_exists(env):
    """The create-only mkdir itself refuses a folder that appears after the check."""
    assert _run(env, "--apply", FakeOffice2())[0] == 0
    runner = FakeOffice2(hooks={f"umask 077 && mkdir {DEST}": lambda f: f.dirs.add(DEST)})
    rc, out, _ = _run(env, "--apply", runner)
    assert rc == 1 and "code=INGRESS_DEST_EXISTS" in out
    assert runner.files == {} and runner.removed == []


@pytest.mark.parametrize("mode", ["--dry-run", "--apply"])
@pytest.mark.parametrize("state", ["symlink", "wrong_owner", "wrong_mode"])
def test_unsafe_existing_parent_refused(env, mode, state):
    assert _run(env, mode, FakeOffice2(parent="ok"))[0] == 0
    runner = FakeOffice2(parent=state)
    rc, out, _ = _run(env, mode, runner)
    assert rc == 1 and "code=INGRESS_DEST_PARENT_UNSAFE" in out
    assert _remote_writes(runner) == [] and runner.files == {}


@pytest.mark.parametrize("state", ["symlink", "wrong_owner", "wrong_mode"])
def test_unsafe_created_parent_refused_before_sha_folder(env, state):
    assert _run(env, "--apply", FakeOffice2(parent_created="ok"))[0] == 0
    runner = FakeOffice2(parent_created=state)
    rc, out, _ = _run(env, "--apply", runner)
    assert rc == 1 and "code=INGRESS_DEST_PARENT_UNSAFE" in out
    assert [a[4] for a in _remote_writes(runner)] == [f"umask 077 && mkdir {PARENT}"]
    assert DEST not in runner.dirs and runner.files == {}


def test_parent_create_failure_refused(env):
    assert _run(env, "--apply", FakeOffice2())[0] == 0
    runner = FakeOffice2(parent_mkdir_fails=True)
    rc, out, _ = _run(env, "--apply", runner)
    assert rc == 1 and "code=INGRESS_DEST_PARENT_CREATE_FAILED" in out
    assert SECRET not in out
    assert DEST not in runner.dirs


def test_parent_created_concurrently_is_verified_not_refused(env):
    """A parent that appears between the probe and our mkdir is verified."""
    def appear(f):
        if f.parent == "absent":
            f.parent = "ok"
    runner = FakeOffice2(hooks={f"umask 077 && mkdir {PARENT}": appear})
    rc, out, _ = _run(env, "--apply", runner)
    assert rc == 0, out


@pytest.mark.parametrize("stage", ["precheck", "ln"])
def test_existing_final_collision_is_never_removed(env, stage):
    """A final another writer put in the folder is reported, never deleted.
    At ``ln`` the verified part is kept too, and its path reported."""
    control = FakeOffice2()
    assert _run(env, "--apply", control)[0] == 0 and control.files[RB] == env.rollback.read_bytes()

    def plant(f):
        f.files.setdefault(RB, b"someone else's file")
    hook_on = f"test ! -e {RB}" if stage == "precheck" else f"ln -T -- {RB_PART} {RB}"
    runner = FakeOffice2(hooks={hook_on: plant})
    rc, out, err = _run(env, "--apply", runner)
    assert rc == 1
    assert out.startswith("FAILED code=INGRESS_DEST_FILE_EXISTS ")
    assert runner.files[RB] == b"someone else's file"
    assert RB not in runner.removed and RB_PART not in runner.removed
    if stage == "ln":
        assert runner.files[RB_PART] == env.rollback.read_bytes()
        assert err == f"INGRESS_PART_KEPT part={RB_PART}\n"
    else:
        assert RB_PART not in runner.files and err == ""
    assert "cannot" not in out and "File exists" not in out


@pytest.mark.parametrize("kind", ["dir", "symlink_to_dir"])
def test_folder_at_final_is_a_collision_not_a_container(env, kind):
    """``ln -T`` refuses a folder, or a symlink to one, at the final path
    (plain ``ln`` would link inside it and report success)."""
    control = FakeOffice2()
    assert _run(env, "--apply", control)[0] == 0 and control.files[RB] == env.rollback.read_bytes()

    def plant(f):
        if kind == "dir":
            f.dirs.add(RB)
        else:
            f.dirs.add("/home/claude/elsewhere")
            f.symlinks[RB] = "/home/claude/elsewhere"
    runner = FakeOffice2(hooks={f"ln -T -- {RB_PART} {RB}": plant})
    rc, out, err = _run(env, "--apply", runner)
    assert rc == 1
    assert out.startswith("FAILED code=INGRESS_DEST_FILE_EXISTS ")
    assert err == f"INGRESS_PART_KEPT part={RB_PART}\n"
    assert runner.files[RB_PART] == env.rollback.read_bytes()
    assert RB_PART not in runner.removed
    assert not any(k.startswith(("/home/claude/elsewhere/", RB + "/")) for k in runner.files)
    assert (RB in runner.dirs) if kind == "dir" else (RB in runner.symlinks)


def test_plain_ln_would_have_linked_into_the_folder(env):
    """Guards the fake itself: without ``-T`` the folder case is a silent
    success, which is the defect ``-T`` closes."""
    f = FakeOffice2(parent="ok")
    f.dirs.update({DEST, RB})
    f.files[RB_PART] = b"data"
    assert f(PREFIX + [f"ln -- {RB_PART} {RB}"], timeout=1).returncode == 0
    assert f"{RB}/{RB_PART.rsplit('/', 1)[1]}" in f.files
    assert f(PREFIX + [f"ln -T -- {RB_PART} {RB}"], timeout=1).returncode == 1


def _raise(exc):
    def hook(_f):
        raise exc
    return hook


@pytest.mark.parametrize("exc", [subprocess.TimeoutExpired(["ssh"], 30), OSError("exec failed")])
def test_inconclusive_collision_probe_keeps_part(env, exc):
    """``ln`` failed and the probe of the final timed out or could not run:
    the final's state is unknown, so the part is kept and reported."""
    control = FakeOffice2()
    assert _run(env, "--apply", control)[0] == 0
    probe = f"test -e {RB} || test -L {RB}"

    class LnFails(FakeOffice2):
        def __call__(self, argv, **kw):
            if argv[4] == f"ln -T -- {RB_PART} {RB}":
                self.calls.append(list(argv))
                self.kwargs.append(kw)
                return self._done(1, err="ln: some other failure\n")
            return super().__call__(argv, **kw)

    ok = LnFails()
    rc, out, _ = _run(env, "--apply", ok)  # a conclusive "absent" probe removes the part
    assert rc == 1 and "code=INGRESS_PUBLISH_FAILED" in out and ok.removed[-1] == RB_PART
    runner = LnFails(hooks={probe: _raise(exc)})
    rc, out, err = _run(env, "--apply", runner)
    assert rc == 1 and out.startswith("FAILED code=INGRESS_PUBLISH_FAILED ")
    assert err == f"INGRESS_PART_KEPT part={RB_PART}\n"
    assert RB_PART in runner.files and RB_PART not in runner.removed


@pytest.mark.parametrize("exc", [subprocess.TimeoutExpired(["ssh"], 30), OSError("exec failed")])
def test_part_removal_failure_keeps_final_published(env, exc):
    control = FakeOffice2()
    assert _run(env, "--apply", control)[0] == 0 and RB_PART not in control.files
    runner = FakeOffice2(hooks={f"rm -f -- {RB_PART}": _raise(exc)})
    rc, out, err = _run(env, "--apply", runner)
    assert rc == 1 and out.startswith("FAILED code=INGRESS_PART_REMOVE_FAILED ")
    assert err == f"INGRESS_PART_KEPT part={RB_PART}\n"
    assert runner.files[RB] == env.rollback.read_bytes() and RB_PART in runner.files


def test_part_removal_nonzero_exit_is_part_remove_failed(env):
    assert _run(env, "--apply", FakeOffice2())[0] == 0

    class RmFails(FakeOffice2):
        def __call__(self, argv, **kw):
            if argv[4] == f"rm -f -- {IMG_PART}":
                self.calls.append(list(argv))
                self.kwargs.append(kw)
                return self._done(1, err="rm: cannot remove\n")
            return super().__call__(argv, **kw)

    runner = RmFails()
    rc, out, err = _run(env, "--apply", runner)
    assert rc == 1 and "code=INGRESS_PART_REMOVE_FAILED" in out
    assert err == f"INGRESS_PART_KEPT part={IMG_PART}\n" and IMG in runner.files


def test_unknown_stream_failure_removes_only_our_part(env):
    """A failure after the stream started removes only this run's part."""
    assert _run(env, "--apply", FakeOffice2())[0] == 0

    class Failing(FakeOffice2):
        def __call__(self, argv, **kw):
            if argv[4] == f"set -o noclobber; cat > {IMG_PART}":
                self.calls.append(list(argv))
                self.kwargs.append(kw)
                self.files[IMG_PART] = b"partial"
                self.files[IMG] = b"someone else's file"
                return self._done(1, out=b"", err=b"cat: write error: No space left on device")
            return super().__call__(argv, **kw)

    runner = Failing()
    rc, out, _ = _run(env, "--apply", runner)
    assert rc == 1 and "code=INGRESS_TRANSFER_FAILED" in out
    assert runner.removed == [IMG_PART] and IMG_PART not in runner.files
    assert runner.files[IMG] == b"someone else's file"


def test_part_and_publish_argv_shapes(env):
    assert _run(env, "--apply", FakeOffice2())[0] == 0
    runner = FakeOffice2()
    assert _run(env, "--apply", runner)[0] == 0
    q = shlex.quote
    for name, i in (("image.tar", 0), ("vikunja-2.4.0.image.tar", 1)):
        p, f = part(name, i), f"{DEST}/{name}"
        for cmd in (f"set -o noclobber; cat > {q(p)}", f"sha256sum -- {q(p)}", f"ln -T -- {q(p)} {q(f)}",
                    f"rm -f -- {q(p)}"):
            assert PREFIX + [cmd] in runner.calls, cmd
    # a real nonce is 128-bit hex; anything else is refused before use
    real = mod.new_nonce()
    assert re.fullmatch(r"[0-9a-f]{32}", real) and real != mod.new_nonce()
    assert mod.part_path(IMG, real) == f"{DEST}/.image.tar.{real}.part"
    for bad in ("x; rm -rf /", "ABCDEF" * 6, "0" * 31, ""):
        with pytest.raises(ValueError):
            mod.part_path(IMG, bad)
    # every remove ever issued names a part, never a final
    assert all(a[4].endswith(".part") for a in runner.calls if a[4].startswith("rm "))


@pytest.mark.parametrize("bad", ["/home/codex/rrule-office2-images/image.tar", "/home/codex"])
def test_codex_source_refused_without_reading_or_ssh(env, bad):
    assert _run(env, "--dry-run", FakeOffice2())[0] == 0
    record = copy.deepcopy(env.record)
    record["roots"]["office4_sources"]["archive"] = bad
    runner = FakeOffice2()
    rc, out, _ = _run(env, "--apply", runner, record)
    assert rc == 1 and "code=INGRESS_SOURCE_FORBIDDEN" in out
    assert runner.calls == []


def test_codex_lookalike_is_not_refused():
    assert mod._under("/home/codex/x", "/home/codex")
    assert not mod._under("/home/codexy/x", "/home/codex")


def test_codex_source_via_symlink_refused(env):
    """A kgale-side symlink into /home/codex is refused by its resolved path
    (the link target need not exist: it is never opened)."""
    good_link = env.tmp / "good.tar"
    good_link.symlink_to(env.image)
    record = copy.deepcopy(env.record)
    record["roots"]["office4_sources"]["archive"] = str(good_link)
    assert _run(env, "--dry-run", FakeOffice2(), record)[0] == 0
    bad_link = env.tmp / "bad.tar"
    bad_link.symlink_to("/home/codex/rrule-office2-images/image.tar")
    record["roots"]["office4_sources"]["archive"] = str(bad_link)
    runner = FakeOffice2()
    rc, out, _ = _run(env, "--dry-run", runner, record)
    assert rc == 1 and "code=INGRESS_SOURCE_FORBIDDEN" in out and runner.calls == []


@pytest.mark.parametrize("path", [
    "/data/services/vikunja/other/48008c5067a6/image.tar",
    "/data/services/vikunja/release-artifacts/image.tar",
    "/data/services/vikunja/release-artifacts/a/b/image.tar",
    "/home/claude/release-artifacts/48008c5067a6/image.tar",
])
def test_destination_outside_artifacts_refused(env, path):
    assert _run(env, "--dry-run", FakeOffice2())[0] == 0
    record = copy.deepcopy(env.record)
    record["archive"]["path"] = path
    record["rollback"]["archive"]["path"] = path.rsplit("/", 1)[0] + "/vikunja-2.4.0.image.tar"
    runner = FakeOffice2()
    rc, out, _ = _run(env, "--apply", runner, record)
    assert rc == 1 and "code=INGRESS_DEST_FORBIDDEN" in out and runner.calls == []


def test_archives_in_different_folders_refused(env):
    record = copy.deepcopy(env.record)
    assert _run(env, "--dry-run", FakeOffice2(), record)[0] == 0
    record["rollback"]["archive"]["path"] = "/data/services/vikunja/release-artifacts/other/x.tar"
    runner = FakeOffice2()
    rc, out, _ = _run(env, "--dry-run", runner, record)
    assert rc == 1 and "code=INGRESS_DEST_FORBIDDEN" in out and runner.calls == []


def test_remote_sha_mismatch_removes_only_that_part(env):
    good = FakeOffice2()
    assert _run(env, "--apply", good)[0] == 0 and good.files[RB] == env.rollback.read_bytes()
    runner = FakeOffice2(corrupt={"vikunja-2.4.0.image.tar"})
    rc, out, _ = _run(env, "--apply", runner)
    assert rc == 1
    assert out.strip() == "FAILED code=INGRESS_SHA_MISMATCH private_log=-"
    # the first archive was published (its part removed after ln); the
    # mismatched part is removed; no final is ever removed or published
    assert runner.removed == [IMG_PART, RB_PART]
    assert set(runner.files) == {IMG} and DEST in runner.dirs
    assert not any(a[4].startswith("ln ") and a[4].endswith(RB) for a in runner.calls)


def test_transfer_timeout_removes_only_part_even_with_noclobber_stderr(env):
    """The timeout's stderr looks like a noclobber refusal and a final has
    been planted meanwhile: only this run's part is removed."""
    control = FakeOffice2()
    assert _run(env, "--apply", control)[0] == 0 and control.files[IMG] == env.image.read_bytes()

    def plant(f):
        f.files[IMG] = b"someone else's file"
    runner = FakeOffice2(transfer_timeout=True, hooks={"set -o noclobber; cat > ": plant})
    rc, out, _ = _run(env, "--apply", runner)
    assert rc == 1 and "code=INGRESS_TRANSFER_TIMEOUT" in out
    assert runner.removed == [IMG_PART]
    assert runner.files == {IMG: b"someone else's file"}
    log = next((env.tmp / "private").iterdir()).read_text()
    assert "cannot overwrite existing file" in log and "cannot overwrite" not in out


def test_insufficient_space_refused(env):
    total = env.record["archive"]["size"] + env.record["rollback"]["archive"]["size"]
    assert _run(env, "--dry-run", FakeOffice2(avail=2 * total))[0] == 0
    runner = FakeOffice2(avail=2 * total - 1)
    rc, out, _ = _run(env, "--apply", runner)
    assert rc == 1 and "code=INGRESS_SPACE_INSUFFICIENT" in out
    assert _remote_writes(runner) == []


def test_ssh_failure_is_private(env):
    assert _run(env, "--dry-run", FakeOffice2())[0] == 0
    runner = FakeOffice2(ssh_down=True)
    rc, out, err = _run(env, "--dry-run", runner)
    assert rc == 1 and "code=INGRESS_SSH_FAILED" in out
    for leak in (SECRET, TITLE, "Permission denied"):
        assert leak not in out and leak not in err
    logs = list((env.tmp / "private").iterdir())
    assert len(logs) == 1 and SECRET in logs[0].read_text()
    assert f"private_log={logs[0]}" in out


def test_timeout_on_remote_check(env):
    assert _run(env, "--dry-run", FakeOffice2())[0] == 0

    def hang(argv, **kw):
        raise subprocess.TimeoutExpired(argv, kw["timeout"])
    rc, out, _ = _run(env, "--dry-run", hang)
    assert rc == 1 and "code=TIMEOUT_INGRESS_PARENT_CHECK" in out


# ---------------------------------------------------------------------------
# CLI contract
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("argv", [[], ["--force"], ["--dry-run", "--apply"], ["dry-run"]])
def test_usage_exit_2(env, argv):
    runner = FakeOffice2()
    out, err = io.StringIO(), io.StringIO()
    rc = mod.main(argv, release_path=_RELEASE, runner=runner, private_root=env.tmp / "p",
                  stdout=out, stderr=err)
    assert rc == 2 and "usage:" in err.getvalue() and runner.calls == []


def test_real_release_record_plans_expected_destination():
    from scripts.deploy.vikunja_release import core
    dest, items = mod.plan(core.load_release(_RELEASE))
    assert dest == DEST
    assert [i["remote"] for i in items] == [f"{DEST}/image.tar", f"{DEST}/vikunja-2.4.0.image.tar"]
    assert all(not i["source"].startswith("/home/codex") for i in items)


def test_remote_argv_prefix_is_exact():
    argv = mod.remote_argv("true")
    assert argv == PREFIX + ["true"]
    assert tuple(mod.SSH_PREFIX) == ("ssh", "-o", "BatchMode=yes", "office2-claude")


def test_no_other_account_in_source():
    text = _PATH.read_text(encoding="utf-8")
    assert "office2-kgale" not in text and "office2-codex" not in text and "sudo" not in text


def test_entrypoint_is_executable_in_git():
    out = subprocess.run(["git", "ls-files", "-s", str(_PATH.relative_to(_ROOT))], cwd=_ROOT,
                         capture_output=True, text=True, check=True).stdout
    assert out.startswith("100755"), out
