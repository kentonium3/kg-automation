"""Host-state isolation for the felix-deployer test package (#989).

Two independent mechanisms live here, and they do different jobs.

``_isolate_felix_deployer_state`` (function-scoped, autouse)
    Repoints the ``rebaseline`` module's four ``/data`` path constants at a
    per-test tmp directory, so the code under test executes truthfully
    against scratch state instead of the host's real service directory.

``_guard_host_state`` (session-scoped, autouse)
    Blocks *and* records attempted mutations under ``/data`` across the
    common write idioms — the ``pathlib`` and ``os`` mutators and both
    ``open`` bindings — then fails the session at teardown if any were
    attempted.  It is not a complete syscall interceptor: it cannot see
    writes made by a subprocess, nor through a C extension that bypasses
    these entry points.  The redirect makes a
    correctly-isolated test pass; the guard is what stops a *forgetful* one
    from touching real service state and makes the omission visible.

Why the guard both raises and records
-------------------------------------
Raising alone is not enough as a *detector* on this code path:
``rebaseline.write_observed_head`` catches ``OSError`` and logs it, and
``_tick.run_tick`` wraps the whole watermark block in ``except Exception`` by
deliberate no-crash design.  A guard that only raised would be swallowed by
the production code under test, the test would still pass, and the escape
would go unreported.

But raising *is* what prevents the harm: the real write never happens.  So
the guard does both — it appends to a session-level record and then raises,
refusing to call the underlying function.  Production may swallow the
exception; it cannot swallow the record, which is asserted at session
teardown.  Recording without raising would be an alarm that still lets the
damage through, which matters because on office2 these are the live paths
felix-deployer runs out of.

Why the redirect cannot key on a module name
--------------------------------------------
``scripts/deploy/felix-deployer/`` is hyphenated and not importable as a
package, so each test module loads its own copy via
``importlib.util.spec_from_file_location`` and registers it with
``sys.modules[name] = mod`` — unconditionally.  Each registration *rebinds*
the name, so at any moment ``sys.modules["rebaseline"]`` is only the
last-registered of several live instances, and which one that is depends on
collection order.  Measured at the end of a whole-package run: four live
``rebaseline`` objects and four live ``_tick`` objects, and the mapping is
not one-to-one — ``test_rebaseline.py`` loads a ``rebaseline`` with no
``_tick``, and two ``_tick`` copies share one name.

A ``sys.modules``-only sweep by ``__file__`` is also insufficient, at two
levels.  The rebound ``rebaseline`` instances are orphaned from the module
table and survive only as the ``_rebaseline`` attribute of the ``_tick`` copy
that imported them.  And some ``_tick`` copies are not in the table at all:
``test_deployer.py``'s loader registers only its synthetic ``notify`` module
and returns the ``_tick`` object without ever assigning it a ``sys.modules``
key, so that copy lives solely as a global of the test module that loaded it.
(It is unregistered rather than rebound — a distinction worth keeping,
because it is the rule for whether a *new* loader needs covering.)

An earlier version of this fixture walked ``sys.modules`` plus ``_tick``
attributes and still missed that second level; the guard below caught it with
28 escaping writes.  So the sweep walks three routes: modules loaded from the
two source files, module-valued globals of every ``tests/deploy`` test
module, and the ``_rebaseline`` attribute of each ``_tick`` instance found by
either.  The sweep is cached and recomputed only when ``sys.modules`` changes
size, so a module imported mid-session is still picked up.
"""

from __future__ import annotations

import builtins
import io
import os
import pathlib
import sys
import types

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_FELIX_DEPLOYER = REPO_ROOT / "scripts" / "deploy" / "felix-deployer"
_REBASELINE_SRC = (_FELIX_DEPLOYER / "rebaseline.py").resolve()
_TICK_SRC = (_FELIX_DEPLOYER / "_tick.py").resolve()
_DEPLOY_TESTS = pathlib.Path(__file__).resolve().parent

#: The four host-state constants ``rebaseline`` binds at import time.  The
#: middle two are NOT derived at use time — they are computed from
#: ``DEFAULT_STATE_DIR`` once, at import, so rebinding the parent alone is
#: inert.  All four must be patched individually.
_STATE_CONSTANTS = (
    "DEFAULT_STATE_DIR",
    "DEFAULT_TOKEN_PATH",
    "DEFAULT_OBSERVED_HEAD_PATH",
    "DEFAULT_BASELINES_DIR",
)

#: Real host prefix that no test in this package may mutate.
_FORBIDDEN_PREFIX = pathlib.Path("/data")

#: Nodeid of the ``tests/deploy`` test currently executing, or ``None``.
#:
#: The guard patches process-global functions, so once installed it sees
#: activity from every package in the session — including the ``tests/trust``
#: and ``tests/security`` escapes tracked separately as #1002.  Blaming this
#: package for those would be wrong and would couple this gate to unrelated
#: work, so the guard is gated on this flag.  It is maintained by a
#: ``pytest_runtest_protocol`` wrapper, which spans the whole protocol — so
#: a test's fixture finalizers are inside the guarded window, which the
#: ``pytest_runtest_setup``/``teardown`` pair it replaced could not manage.
#: The wrapper is NOT limited to this directory by virtue of living in this
#: conftest; it fires for every item in the session, and ``_is_deploy_item``
#: is what scopes it.  Session-scoped finalizers still fall outside the
#: window, because they run after the last item's protocol completes.
_ACTIVE: dict[str, str | None] = {"nodeid": None}

#: Attempted mutations under ``/data``, asserted at session teardown.
_ESCAPES: list[str] = []


class HostStateWriteBlocked(RuntimeError):
    """A test tried to mutate real host state under ``/data``."""


def _is_deploy_item(item) -> bool:
    """True when *item* lives under ``tests/deploy/``.

    Checked explicitly rather than relying on conftest hook scoping.
    ``pytest_runtest_protocol`` is registered on the global plugin manager and
    fires for items in OTHER packages too — measured: without this check the
    guard attributed ``tests/trust`` writes to itself and failed 22 tests that
    pass in isolation.  The ``pytest_runtest_setup``/``teardown`` pair this
    replaced did not have that reach, which is why the problem appeared only
    when the window was widened to cover fixture finalizers.
    """
    try:
        return pathlib.Path(item.path).resolve().is_relative_to(_DEPLOY_TESTS)
    except (AttributeError, OSError, ValueError):  # pragma: no cover
        return str(item.nodeid).startswith("tests/deploy/")


@pytest.hookimpl(wrapper=True)
def pytest_runtest_protocol(item, nextitem):
    """Mark the guarded window for one deploy test, setup through teardown."""
    if not _is_deploy_item(item):
        return (yield)
    _ACTIVE["nodeid"] = item.nodeid
    try:
        return (yield)
    finally:
        _ACTIVE["nodeid"] = None


# ---------------------------------------------------------------------------
# Redirect: point every live rebaseline instance at tmp
# ---------------------------------------------------------------------------


#: ``__file__`` string -> resolved path.  ``sys.modules`` is walked once per
#: test and ``Path.resolve()`` is a realpath syscall; caching on the string
#: (which never changes for a module) cuts the sweep by ~50x.
_RESOLVED: dict[str, pathlib.Path | None] = {}


def _source_of(obj) -> pathlib.Path | None:
    """Resolved ``__file__`` of *obj*, or ``None`` if it has no usable one.

    ``sys.modules`` legitimately holds lazy proxies and shims whose
    ``__file__`` may be absent, a non-string, or a raising property.  This
    runs inside an autouse fixture, so an uncaught ``TypeError`` here would
    error every test in the package rather than one.
    """
    try:
        origin = getattr(obj, "__file__", None)
    except Exception:  # noqa: BLE001 - a raising __file__ property
        return None
    if not origin or not isinstance(origin, (str, bytes, os.PathLike)):
        return None
    key = os.fsdecode(origin)
    if key in _RESOLVED:
        return _RESOLVED[key]
    try:
        resolved = pathlib.Path(key).resolve()
    except (OSError, TypeError, ValueError):  # pragma: no cover
        resolved = None
    _RESOLVED[key] = resolved
    return resolved


def _live_felix_deployer_modules():
    """Every live ``rebaseline`` and ``_tick`` instance, by identity.

    Returns ``(rebaselines, ticks)``.  Both matter: ``_tick`` carries a fifth
    host-state constant of its own (``DEFAULT_STATE_DIR``, used for
    ``git-health.json`` and the last-tick record, the latter written in a
    ``finally`` on every tick including a lock-defer).  Nothing escapes
    through it today only because all five ``run_tick`` drivers patch it by
    hand — which is exactly the per-module discipline this fixture exists to
    replace.

    An instance is reachable by one of three routes, and no single route
    finds them all:

    1. still registered in ``sys.modules`` under some name;
    2. orphaned from ``sys.modules`` by a later rebinding, but held as a
       module-valued global of the ``tests/deploy`` test module that loaded
       it (this is how the orphaned ``_tick`` copies survive);
    3. held as the ``_rebaseline`` attribute of any ``_tick`` instance found
       by route 1 or 2.

    Known limits, accepted deliberately: the walk goes one level deep into
    test-module globals, so an instance reachable only through a closure,
    a ``functools.partial``, or an attribute of a non-module object would be
    missed, as would one produced by ``importlib.reload`` mid-test.  None of
    those shapes exist in this package today, and the guard below is the
    backstop for the ones that do not.
    """
    rebaselines: dict[int, object] = {}
    ticks: dict[int, object] = {}

    def _classify(obj) -> None:
        src = _source_of(obj)
        if src == _REBASELINE_SRC:
            rebaselines[id(obj)] = obj
        elif src == _TICK_SRC:
            ticks[id(obj)] = obj

    for mod in list(sys.modules.values()):
        _classify(mod)
        src = _source_of(mod)
        if src is not None and src.parent == _DEPLOY_TESTS:
            # Route 2: a test module's globals keep orphaned copies alive.
            for value in list(vars(mod).values()):
                if isinstance(value, types.ModuleType):
                    _classify(value)

    for tick_mod in ticks.values():
        held = getattr(tick_mod, "_rebaseline", None)
        if held is not None:
            rebaselines[id(held)] = held

    return list(rebaselines.values()), list(ticks.values())


@pytest.fixture(autouse=True)
def _isolate_felix_deployer_state(monkeypatch, tmp_path):
    """Point every live ``rebaseline`` instance's host-state paths at tmp.

    A no-op for the ~30 files in this package that never load the module.
    Per-test redirects still win: module-level and in-test ``monkeypatch``
    calls run after this conftest-level fixture.

    The directory is deliberately NOT created, and deliberately not named
    ``state`` — ``test_migrate_inbox_state.py`` asserts that ``tmp_path /
    "state"`` does not exist, and separately asserts its mode once created.
    ``write_observed_head`` mkdirs its own parent lazily.
    """

    rebaselines, ticks = _live_felix_deployer_modules()
    if not rebaselines and not ticks:
        yield
        return

    state_dir = tmp_path / "felix-deployer-state"
    replacements = {
        "DEFAULT_STATE_DIR": state_dir,
        "DEFAULT_TOKEN_PATH": state_dir / "rebaseline-pending.json",
        "DEFAULT_OBSERVED_HEAD_PATH": state_dir / "rebaseline-observed-head.json",
        "DEFAULT_BASELINES_DIR": tmp_path / "security-monitor-baselines",
    }

    for mod in rebaselines:
        for name in _STATE_CONSTANTS:
            if hasattr(mod, name):
                monkeypatch.setattr(mod, name, replacements[name])

    # _tick's own state dir — git-health.json and the last-tick record.
    for mod in ticks:
        if hasattr(mod, "DEFAULT_STATE_DIR"):
            monkeypatch.setattr(mod, "DEFAULT_STATE_DIR", tmp_path / "tick-state")

    yield


# ---------------------------------------------------------------------------
# Guard: block and record any mutation under /data
# ---------------------------------------------------------------------------

#: ``os.open`` flags that can create, truncate, or write.
_WRITE_FLAGS = (
    os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC | getattr(os, "O_EXCL", 0)
)


def _under_data(path, dir_fd: int | None = None) -> bool:
    """True if *path* resolves beneath ``/data``.

    Accepts str, bytes, and ``os.PathLike``; ``os.fsdecode`` normalises the
    bytes form that ``open(b"/data/x")`` would otherwise slip through.

    ``dir_fd`` matters because the ``os`` functions resolve a RELATIVE path
    against that descriptor rather than the process CWD, so
    ``os.rename("a", "b", src_dir_fd=fd_on_data)`` would otherwise walk
    straight past a CWD-based check.  Linux exposes the descriptor's target
    at ``/proc/self/fd/<n>``, which is what this resolves through.  If that
    lookup fails we treat the path as forbidden rather than assume it is
    safe: a guard that cannot tell should refuse, not wave through.
    """
    try:
        raw = os.fsdecode(path)
    except (TypeError, ValueError):
        return False

    if dir_fd is not None and not os.path.isabs(raw):
        try:
            base = os.readlink(f"/proc/self/fd/{int(dir_fd)}")
        except (OSError, TypeError, ValueError):
            return True  # cannot resolve the anchor -> refuse
        raw = os.path.join(base, raw)

    try:
        resolved = pathlib.Path(raw).resolve()
    except (OSError, ValueError):  # pragma: no cover - pathological path
        return False
    return resolved == _FORBIDDEN_PREFIX or _FORBIDDEN_PREFIX in resolved.parents


def _block(path, how: str, dir_fd: int | None = None) -> None:
    """Record and refuse a mutation under ``/data``; no-op otherwise."""
    nodeid = _ACTIVE["nodeid"]
    if nodeid is None or not _under_data(path, dir_fd):
        return
    _ESCAPES.append(f"{nodeid}\n      {how}: {os.fsdecode(path)}")
    raise HostStateWriteBlocked(
        f"{nodeid} attempted {how} on real host state {os.fsdecode(path)!r}. "
        f"felix-deployer runs out of {_FORBIDDEN_PREFIX} on office2; tests must "
        f"redirect to tmp (see tests/deploy/conftest.py, #989)."
    )


@pytest.fixture(scope="session", autouse=True)
def _guard_host_state():
    """Block mutations under ``/data`` and fail the session if any were tried.

    Blocking is the protection; the session-teardown assertion is the
    detection, and it survives the ``except Exception`` handlers in the code
    under test that would otherwise swallow the block.  See the module
    docstring for why both halves are needed.
    """
    mp = pytest.MonkeyPatch()
    _ESCAPES.clear()

    def _wrap_path(method: str) -> None:
        """Wrap a single-target ``Path`` mutator."""
        real = getattr(pathlib.Path, method, None)
        if real is None:  # pragma: no cover - version-dependent method
            return

        def _guarded(self, *a, **kw):
            _block(self, f"Path.{method}")
            return real(self, *a, **kw)

        mp.setattr(pathlib.Path, method, _guarded)

    for method in (
        # create / write
        "mkdir", "write_text", "write_bytes", "touch",
        # remove
        "unlink", "rmdir",
        # metadata mutation — chmod is used in this package
        # (test_migrate_inbox_state.py) and mutates real state just as a
        # write does, so an unredirected call must not slip through
        "chmod", "lchmod", "chown",
        # links
        "symlink_to", "hardlink_to",
    ):
        _wrap_path(method)

    # Two-ended operations: the destination is written, the source removed.
    def _wrap_path_move(method: str) -> None:
        real = getattr(pathlib.Path, method)

        def _guarded(self, target, *a, **kw):
            _block(self, f"Path.{method} (source)")
            _block(target, f"Path.{method} (target)")
            return real(self, target, *a, **kw)

        mp.setattr(pathlib.Path, method, _guarded)

    for method in ("rename", "replace"):
        _wrap_path_move(method)

    def _wrap_os_move(name: str) -> None:
        real = getattr(os, name)

        def _guarded(src, dst, *a, src_dir_fd=None, dst_dir_fd=None, **kw):
            _block(src, f"os.{name} (source)", src_dir_fd)
            _block(dst, f"os.{name} (target)", dst_dir_fd)
            if src_dir_fd is not None:
                kw["src_dir_fd"] = src_dir_fd
            if dst_dir_fd is not None:
                kw["dst_dir_fd"] = dst_dir_fd
            return real(src, dst, *a, **kw)

        mp.setattr(os, name, _guarded)

    for name in ("replace", "rename", "link", "symlink"):
        _wrap_os_move(name)

    def _wrap_os_single(name: str) -> None:
        real = getattr(os, name, None)
        if real is None:  # pragma: no cover - platform-dependent
            return

        def _guarded(path, *a, dir_fd=None, **kw):
            _block(path, f"os.{name}", dir_fd)
            if dir_fd is not None:
                kw["dir_fd"] = dir_fd
            return real(path, *a, **kw)

        mp.setattr(os, name, _guarded)

    for name in (
        "remove", "unlink", "mkdir", "makedirs", "rmdir", "removedirs",
        "chmod", "chown", "lchown", "utime", "truncate", "mknod",
    ):
        _wrap_os_single(name)

    real_os_open = os.open

    def _guarded_os_open(path, flags, *a, dir_fd=None, **kw):
        if flags & _WRITE_FLAGS:
            _block(path, f"os.open(flags={flags:#o})", dir_fd)
        if dir_fd is not None:
            kw["dir_fd"] = dir_fd
        return real_os_open(path, flags, *a, **kw)

    mp.setattr(os, "open", _guarded_os_open)

    # ``builtins.open`` and ``io.open`` are the same function object but are
    # separate module attributes; pathlib's ``Path.open`` resolves ``io.open``
    # at call time, so patching only ``builtins`` would miss it.
    def _make_guarded_open(real):
        def _guarded(file, mode="r", *a, **kw):
            if any(flag in mode for flag in ("w", "a", "x", "+")):
                _block(file, f"open(mode={mode!r})")
            return real(file, mode, *a, **kw)

        return _guarded

    mp.setattr(builtins, "open", _make_guarded_open(builtins.open))
    mp.setattr(io, "open", _make_guarded_open(io.open))

    try:
        yield _ESCAPES
    finally:
        mp.undo()

    if _ESCAPES:
        shown = "\n    ".join(sorted(set(_ESCAPES))[:20])
        raise AssertionError(
            f"tests/deploy attempted {len(_ESCAPES)} mutation(s) of real host "
            f"state under {_FORBIDDEN_PREFIX}. They were blocked, but the "
            f"attempts are a defect: office2 runs felix-deployer out of that "
            f"directory, so an unguarded run would clobber live service state "
            f"(#989).\n    {shown}"
        )
