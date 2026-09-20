"""Host-state isolation for the felix-deployer test package (#989).

Two independent mechanisms live here, and they do different jobs.

``_isolate_felix_deployer_state`` (function-scoped, autouse)
    Repoints the ``rebaseline`` module's four ``/data`` path constants at a
    per-test tmp directory, so the code under test executes truthfully
    against scratch state instead of the host's real service directory.

``_forbid_data_writes`` (session-scoped, autouse)
    Records every filesystem write under ``/data`` and fails the session at
    teardown if any occurred.  This is the part that actually closes the
    defect class: the redirect makes a *forgetful* test pass quietly, while
    the observer makes the omission visible.

Why the observer records instead of raising
-------------------------------------------
A raise-based guard — the shape ``tests/conftest.py`` uses for live HTTP —
does not work on this code path.  ``rebaseline.write_observed_head`` catches
``OSError`` and logs it (``rebaseline.py``), and ``_tick.run_tick`` wraps the
whole watermark block in ``except Exception`` by deliberate no-crash design
(``_tick.py``).  A guard that raised would be swallowed by the production
code under test and downgraded to a log line: the write would not happen,
the test would still pass, and the guard would appear to work while
protecting nothing.  Recording and asserting at teardown is immune to
``except Exception``.

Why the redirect cannot key on a module name
--------------------------------------------
``scripts/deploy/felix-deployer/`` is hyphenated and not importable as a
package, so each test module loads its own copy via
``importlib.util.spec_from_file_location`` and registers it with
``sys.modules[name] = mod`` — unconditionally.  Each registration *rebinds*
the name, so at any moment ``sys.modules["rebaseline"]`` is only the
last-registered of several live instances, and which one that is depends on
collection order.  Measured during a whole-directory run, three distinct
``rebaseline`` objects are live, one per ``_tick`` copy, and only one is the
one ``sys.modules`` names.

A ``sys.modules``-only sweep by ``__file__`` is also insufficient, at two
levels.  The rebound ``rebaseline`` instances are orphaned from the module
table and survive only as the ``_rebaseline`` attribute of the ``_tick`` copy
that imported them — and ``_tick`` is orphaned the same way, because
``test_deployer.py`` and ``test_tick_rebaseline.py`` both register their copy
under the name ``felix_deployer_tick_under_test``.  The first copy then lives
on only as a global inside the *test module* that loaded it.

An earlier version of this fixture walked ``sys.modules`` plus ``_tick``
attributes and still missed that second level; the ``_forbid_data_writes``
observer below caught it with 28 escaping writes.  So the sweep walks three
routes: modules loaded from the two source files, module-valued globals of
every ``tests/deploy`` test module, and the ``_rebaseline`` attribute of each
``_tick`` instance found by either.
"""

from __future__ import annotations

import builtins
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
#: latter three are NOT derived at use time — ``DEFAULT_TOKEN_PATH`` and
#: ``DEFAULT_OBSERVED_HEAD_PATH`` are computed from ``DEFAULT_STATE_DIR``
#: once, at import, so rebinding the parent alone is inert.  All four must
#: be patched individually.
_STATE_CONSTANTS = (
    "DEFAULT_STATE_DIR",
    "DEFAULT_TOKEN_PATH",
    "DEFAULT_OBSERVED_HEAD_PATH",
    "DEFAULT_BASELINES_DIR",
)

#: Real host prefix that no test in this package may write beneath.
_FORBIDDEN_PREFIX = pathlib.Path("/data")

#: Nodeid of the ``tests/deploy`` test currently executing, or ``None``.
#:
#: The observer patches process-global functions, so once installed it sees
#: writes from every package in the session — including the ``tests/trust``
#: and ``tests/security`` escapes tracked separately as #1002.  Blaming this
#: package for those would be wrong and would couple this gate to unrelated
#: work, so recording is gated on this flag.  The two hooks that maintain it
#: are declared in THIS conftest, so pytest fires them only for items
#: collected under ``tests/deploy/``.
_ACTIVE: dict[str, str | None] = {"nodeid": None}


def pytest_runtest_setup(item):
    _ACTIVE["nodeid"] = item.nodeid


def pytest_runtest_teardown(item):
    _ACTIVE["nodeid"] = None


def _source_of(obj) -> pathlib.Path | None:
    """Resolved ``__file__`` of *obj*, or ``None`` if it has no usable one."""
    origin = getattr(obj, "__file__", None)
    if not origin:
        return None
    try:
        return pathlib.Path(origin).resolve()
    except OSError:  # pragma: no cover - unresolvable __file__
        return None


def _live_rebaseline_modules():
    """Every live ``rebaseline`` instance, de-duplicated by identity.

    An instance is reachable by one of three routes, and no single route
    finds them all:

    1. still registered in ``sys.modules`` under some name;
    2. orphaned from ``sys.modules`` by a later rebinding, but held as a
       module-valued global of the ``tests/deploy`` test module that loaded
       it (this is how the orphaned ``_tick`` copies survive);
    3. held as the ``_rebaseline`` attribute of any ``_tick`` instance found
       by route 1 or 2.

    The scan is bounded to modules sourced from ``tests/deploy/`` and from
    the two felix-deployer files, so it stays cheap enough to run per test.
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

    return list(rebaselines.values())


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
    targets = _live_rebaseline_modules()
    if not targets:
        yield
        return

    state_dir = tmp_path / "felix-deployer-state"
    replacements = {
        "DEFAULT_STATE_DIR": state_dir,
        "DEFAULT_TOKEN_PATH": state_dir / "rebaseline-pending.json",
        "DEFAULT_OBSERVED_HEAD_PATH": state_dir / "rebaseline-observed-head.json",
        "DEFAULT_BASELINES_DIR": tmp_path / "security-monitor-baselines",
    }

    for mod in targets:
        for name in _STATE_CONSTANTS:
            if hasattr(mod, name):
                monkeypatch.setattr(mod, name, replacements[name])

    yield


@pytest.fixture(scope="session", autouse=True)
def _forbid_data_writes():
    """Record writes under ``/data`` and fail the session at teardown.

    Observes behaviour rather than asserting on the redirect fixture's own
    output, so it cannot pass vacuously: it catches escapes from instances no
    name-based patch reached, and escapes nobody anticipated.

    Recorded, never raised — see the module docstring for why raising is
    defeated here.
    """
    escapes: list[str] = []
    mp = pytest.MonkeyPatch()

    def _under_data(path) -> bool:
        try:
            return _FORBIDDEN_PREFIX in pathlib.Path(path).resolve().parents
        except (OSError, TypeError, ValueError):
            return False

    def _record(path, how: str) -> None:
        nodeid = _ACTIVE["nodeid"]
        if nodeid is not None and _under_data(path):
            escapes.append(f"{nodeid}\n      {how}: {path}")

    real_mkdir = pathlib.Path.mkdir
    real_write_text = pathlib.Path.write_text
    real_write_bytes = pathlib.Path.write_bytes
    real_replace = os.replace
    real_open = builtins.open

    def _mkdir(self, *a, **kw):
        _record(self, "mkdir")
        return real_mkdir(self, *a, **kw)

    def _write_text(self, *a, **kw):
        _record(self, "write_text")
        return real_write_text(self, *a, **kw)

    def _write_bytes(self, *a, **kw):
        _record(self, "write_bytes")
        return real_write_bytes(self, *a, **kw)

    def _replace(src, dst, *a, **kw):
        _record(dst, "os.replace")
        return real_replace(src, dst, *a, **kw)

    def _open(file, mode="r", *a, **kw):
        if any(flag in mode for flag in ("w", "a", "x", "+")):
            _record(file, f"open(mode={mode!r})")
        return real_open(file, mode, *a, **kw)

    mp.setattr(pathlib.Path, "mkdir", _mkdir)
    mp.setattr(pathlib.Path, "write_text", _write_text)
    mp.setattr(pathlib.Path, "write_bytes", _write_bytes)
    mp.setattr(os, "replace", _replace)
    mp.setattr(builtins, "open", _open)

    try:
        yield escapes
    finally:
        mp.undo()

    if escapes:
        shown = "\n    ".join(sorted(set(escapes))[:20])
        raise AssertionError(
            f"tests/deploy wrote to real host state under {_FORBIDDEN_PREFIX} "
            f"({len(escapes)} write(s)). These are production service paths — "
            f"on office2, which runs felix-deployer out of that directory, "
            f"this would clobber live service state (#989).\n"
            f"    {shown}"
        )
