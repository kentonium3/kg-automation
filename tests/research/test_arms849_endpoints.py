"""WP01 (#1083): the live runtime's endpoints are a value, not a constant.

``live_runtime`` reaches FalkorDB and llama.cpp at four consumers: arm G's bridge, the serving
facade, the health check, and the secondary gate's ``/props`` probe. These tests drive the REAL
code paths (the real ``_factory_g``, the real ``ServingFacade``/``serving.complete``, the real
``container_health`` and the real default ``props_n_ctx`` resolution) and stand in only at the
network boundary (``urlopen``, ``socket.create_connection``, ``arm_g.make_bridge``).

- T-a (FR-002, ratchet): no ``endpoints`` argument -> the in-network pair everywhere.
- T-b (FR-001, build): a host pair -> the host pair everywhere. Same fixture, so T-b is the
  positive control for T-a. It also proves C-002: the host URL passes ``serving``'s allowlist.
- T-c (C-001): in a fresh process, with every endpoint override set before import, production
  code reads none of them.

``arm_g``, ``embed`` and ``arm_r`` import ``graphiti_core`` (directly or through ``embed``), which
repo CI and the FR-015 checker's fresh-worktree step do not have. They are replaced by stand-in
modules at the import boundary, so these tests RUN (not skip) there.
"""

from __future__ import annotations

import ast
import json
import os
import pathlib
import subprocess
import sys
import threading
import time
import types
import urllib.request
from dataclasses import dataclass, field
from typing import Any

import pytest

import scripts.research.arms849 as arms849_pkg
from scripts.research import run_849_harness as h
from tests.research.conftest import PASSING_GATES, PRIMARY, REPO_ROOT

#: Literals, not the module constants: the tests are an independent oracle for the defaults.
IN_NETWORK_FALKOR = ("falkordb", 6379)
IN_NETWORK_LLAMA = "http://llama:8080"
HOST_FALKOR = ("127.0.0.1", 16379)
HOST_LLAMA = "http://127.0.0.1:18080"

COMPLETION_RESPONSE = {
    "content": "ok",
    "timings": {"prompt_n": 1, "cache_n": 0, "prompt_ms": 1.0, "predicted_n": 1, "predicted_ms": 1.0},
}


class _StopAfterProps(Exception):
    """Raised by the patched ``replay`` — the first step after the probe's ``/props`` read."""


class _FakeTokenizer:
    """Only what ``serving.complete`` touches on the exercised path."""

    def count(self, text: str | bytes) -> int:
        return 1


class _QuietGtt:
    """A safe GTT window with no sampling thread."""

    breached = False
    peak_gib = 1.0

    def __enter__(self) -> _QuietGtt:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def read_once(self) -> float:
        return 1.0


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


class _FakeSocket:
    def __enter__(self) -> _FakeSocket:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def sendall(self, data: bytes) -> None:
        return None

    def recv(self, size: int) -> bytes:
        return b"+PONG\r\n"


@dataclass
class _Seen:
    """What each consumer was pointed at."""

    bridge: list[tuple[str, int]] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)
    sockets: list[tuple[str, int]] = field(default_factory=list)


def _install_boundaries(monkeypatch: pytest.MonkeyPatch, seen: _Seen) -> None:
    """Stand in at the network and graphiti import boundaries only."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(h.serving, "Tokenizer", lambda *args, **kwargs: _FakeTokenizer())
    monkeypatch.setattr(h, "_corpus_text", lambda resources: "sentinel corpus text")

    def make_bridge(embedder: Any, text: Any, *, host: str, port: int, **kwargs: Any) -> Any:
        seen.bridge.append((host, port))
        return types.SimpleNamespace(answer=lambda *a, **k: {}, build_graph=lambda *a, **k: None,
                                     drop_graph=lambda *a, **k: None, list_graphs=lambda *a, **k: [],
                                     close=lambda: None)

    stand_ins = {
        "arm_g": {"make_bridge": make_bridge},
        "embed": {"Embedder": lambda *args, **kwargs: object()},
        "arm_r": {"bind": lambda *args, **kwargs: None, "calibration_inputs": lambda *args, **kwargs: None},
    }
    for name, attrs in stand_ins.items():
        fake = types.ModuleType(f"scripts.research.arms849.{name}")
        for attr, value in attrs.items():
            setattr(fake, attr, value)
        monkeypatch.setitem(sys.modules, fake.__name__, fake)
        monkeypatch.setattr(arms849_pkg, name, fake, raising=False)

    def urlopen(req: Any, timeout: float | None = None) -> _FakeResponse:
        url = req.full_url if isinstance(req, urllib.request.Request) else str(req)
        seen.urls.append(url)
        if url.endswith("/health"):
            return _FakeResponse({"status": "ok"})
        if url.endswith("/props"):
            return _FakeResponse({"default_generation_settings": {"n_ctx": PRIMARY.n_ctx}})
        if url.endswith("/completion"):
            return _FakeResponse(COMPLETION_RESPONSE)
        raise AssertionError(f"unexpected URL {url}")

    def create_connection(address: tuple[str, int], timeout: float | None = None) -> _FakeSocket:
        seen.sockets.append(tuple(address))
        return _FakeSocket()

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(h.socket, "create_connection", create_connection)
    monkeypatch.setattr(h, "replay", lambda *args, **kwargs: (_ for _ in ()).throw(_StopAfterProps()))


@dataclass
class _Wired:
    runtime: h.Runtime
    bridge: list[tuple[str, int]]
    health: _Seen
    facade: _Seen
    props: _Seen


def _wired_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path,
                   endpoints: h.Endpoints | None) -> _Wired:
    """Build a live runtime and INVOKE every consumer; record what each one was pointed at.

    The bridge is recorded at construction (the real ``_factory_g`` runs); health, the facade's
    completion and the secondary gate's DEFAULT ``/props`` probe are each invoked and recorded
    separately, so a consumer pointed at the wrong pair cannot hide behind another's request."""
    seen = _Seen()
    _install_boundaries(monkeypatch, seen)
    kwargs = {} if endpoints is None else {"endpoints": endpoints}
    runtime = h.live_runtime(PRIMARY, tmp_path, PASSING_GATES, **kwargs)
    wired = _Wired(runtime, list(seen.bridge), _Seen(), _Seen(), _Seen())

    seen.urls, seen.sockets = wired.health.urls, wired.health.sockets
    assert runtime.health() is True

    seen.urls, seen.sockets = wired.facade.urls, wired.facade.sockets
    runtime.facade(time.monotonic() + 60, threading.Event(), lambda: None).complete({"prompt": "x"})

    seen.urls, seen.sockets = wired.props.urls, wired.props.sockets
    runtime.gtt_sampler = _QuietGtt
    with pytest.raises(_StopAfterProps):
        h.live_secondary_gate(runtime)()          # the DEFAULT props_n_ctx: never injected here
    return wired


def _assert_pair(wired: _Wired, falkor: tuple[str, int], llama: str) -> None:
    assert wired.bridge == [falkor]                                           # arm G's bridge
    assert wired.health.urls == [f"{llama}/health", f"{llama}/props"]         # health: llama half
    assert wired.health.sockets == [falkor]                                   # health: FalkorDB PING
    assert wired.facade.urls == [f"{llama}/completion"]                       # the serving facade
    assert wired.props.urls == [f"{llama}/props"]                             # the secondary gate's probe
    assert wired.facade.sockets == wired.props.sockets == []


def test_default_runtime_targets_the_in_network_pair_at_all_four_consumers(monkeypatch, tmp_path):
    """T-a (FR-002): the decisive in-container run is unchanged."""
    wired = _wired_runtime(monkeypatch, tmp_path, None)
    _assert_pair(wired, IN_NETWORK_FALKOR, IN_NETWORK_LLAMA)
    assert wired.runtime.endpoints is h.IN_NETWORK_ENDPOINTS
    assert h.IN_NETWORK_ENDPOINTS == h.Endpoints(IN_NETWORK_FALKOR, IN_NETWORK_LLAMA)


def test_host_endpoints_reach_all_four_consumers(monkeypatch, tmp_path):
    """T-b (FR-001; the positive control for T-a; C-002 with no allowlist change)."""
    endpoints = h.Endpoints(HOST_FALKOR, HOST_LLAMA)
    wired = _wired_runtime(monkeypatch, tmp_path, endpoints)
    _assert_pair(wired, HOST_FALKOR, HOST_LLAMA)
    assert wired.runtime.endpoints is endpoints


def test_the_wired_runtime_binds_the_stand_ins_and_imports_no_graphiti(monkeypatch, tmp_path):
    """The stand-ins are what the real factories and ``live_runtime`` bound, and building and
    driving the runtime imports no ``graphiti_core`` of its own. Under the CI stub (an import that
    raises) or with no graphiti installed, ``graphiti_core`` therefore stays out of
    ``sys.modules``; on office4, where other tests import the real one first, it is unchanged."""
    before = sys.modules.get("graphiti_core")
    wired = _wired_runtime(monkeypatch, tmp_path, h.Endpoints(HOST_FALKOR, HOST_LLAMA))
    assert wired.bridge == [HOST_FALKOR]                     # the fake arm_g.make_bridge ran
    assert type(wired.runtime.embedder) is object            # the fake embed.Embedder ran
    assert sys.modules.get("graphiti_core") is before


def test_runtime_and_resources_default_to_the_in_network_pair():
    """Fields go last with defaults: existing constructions keep working and get the default."""
    resources = h.Resources(corpus_dir=pathlib.Path("."), config=PRIMARY, tokenizer=None, embedder=None)
    assert resources.endpoints is h.IN_NETWORK_ENDPOINTS
    runtime = h.Runtime(config=PRIMARY, arms={}, facade=lambda *a: None, health=lambda: True,
                        gates=PASSING_GATES)
    assert runtime.endpoints is h.IN_NETWORK_ENDPOINTS


ENDPOINT_OVERRIDES = {
    "ARMS849_FALKOR_HOST": "203.0.113.7",
    "ARMS849_FALKOR_PORT": "1",
    "ARMS849_LLAMA_HOST": "203.0.113.8",
    "ARMS849_LLAMA_PORT": "2",
}

#: The fresh-process child for T-c. It installs an environment READ RECORDER before the harness
#: is imported, so import-time reads count; then builds the DEFAULT runtime and invokes all four
#: consumers through the same boundary stand-ins as the in-process fixture.
#: Recorder proof is committed: ``test_planted_environment_read_is_recorded`` passes a PLANT
#: (argv[3]) that the fake ``make_bridge`` executes mid-construction, and every planted read
#: form — including the post-merge review's ``dict(os.environ.items())`` — must be recorded.
CHILD = r'''
import json, os, sys, threading, time, types, urllib.request

WATCHED = set(json.loads(sys.argv[1]))
reads = []

from collections.abc import MutableMapping

def _name(key):
    return key.decode("utf-8", "surrogateescape") if isinstance(key, bytes) else key

class RecordingEnviron(MutableMapping):
    """A NON-dict proxy over the real os._Environ. Not subclassing dict matters: dict(env),
    {**env} and dict.update(env) take a C fast path on a dict subclass that bypasses every
    Python-level override. As a plain Mapping, every bulk access (iteration, keys/items/values
    views, dict(), copy(), ``**`` unpacking) is funnelled through __iter__/__getitem__ here,
    so a key reaching caller code by ANY route is recorded (#1083 post-merge review: a planted
    ``dict(os.environ.items())`` previously recorded nothing)."""
    def __init__(self, real):
        self._real = real
    def __getitem__(self, key):
        reads.append(_name(key))
        return self._real[key]
    def __iter__(self):
        for key in list(self._real):
            reads.append(_name(key))
            yield key
    def __len__(self):
        return len(self._real)
    def __contains__(self, key):
        reads.append(_name(key))
        return key in self._real
    def __setitem__(self, key, value):
        self._real[key] = value
    def __delitem__(self, key):
        del self._real[key]
    def copy(self):
        return dict(self)
    def __repr__(self):
        return "RecordingEnviron(" + repr(dict(self)) + ")"

os.environ = RecordingEnviron(os.environ)
os.environb = RecordingEnviron(os.environb)
os.getenv = lambda key, default=None: os.environ.get(key, default)
os.getenvb = lambda key, default=None: os.environb.get(key, default)
reads.clear()   # the recorder's own construction is not a read

import scripts.research.arms849 as pkg
from scripts.research import run_849_harness as h
from tests.research.conftest import PASSING_GATES, PRIMARY

seen = {"bridge": [], "urls": [], "sockets": []}

PLANT = sys.argv[3] if len(sys.argv) > 3 else ""

def make_bridge(embedder, text, *, host, port, **kwargs):
    seen["bridge"].append([host, port])
    if PLANT:
        exec(PLANT, {"os": os})
    noop = lambda *a, **k: None
    return types.SimpleNamespace(answer=noop, build_graph=noop, drop_graph=noop,
                                 list_graphs=noop, close=noop)

stand_ins = {
    "arm_g": {"make_bridge": make_bridge},
    "embed": {"Embedder": lambda *a, **k: object()},
    "arm_r": {"bind": lambda *a, **k: None, "calibration_inputs": lambda *a, **k: None},
}
for name, attrs in stand_ins.items():
    fake = types.ModuleType("scripts.research.arms849." + name)
    for attr, value in attrs.items():
        setattr(fake, attr, value)
    sys.modules[fake.__name__] = fake
    setattr(pkg, name, fake)

class Response:
    def __init__(self, payload):
        self.body = json.dumps(payload).encode()
    def __enter__(self):
        return self
    def __exit__(self, *exc):
        return None
    def read(self):
        return self.body

def urlopen(req, timeout=None):
    url = req.full_url if isinstance(req, urllib.request.Request) else str(req)
    seen["urls"].append(url)
    if url.endswith("/health"):
        return Response({"status": "ok"})
    if url.endswith("/props"):
        return Response({"default_generation_settings": {"n_ctx": PRIMARY.n_ctx}})
    return Response(json.loads(sys.argv[2]))

class Sock:
    def __enter__(self):
        return self
    def __exit__(self, *exc):
        return None
    def sendall(self, data):
        return None
    def recv(self, size):
        return b"+PONG\r\n"

def create_connection(address, timeout=None):
    seen["sockets"].append(list(address))
    return Sock()

class StopAfterProps(Exception):
    pass

def replay(*args, **kwargs):
    raise StopAfterProps()

class QuietGtt:
    breached = False
    peak_gib = 1.0
    def __enter__(self):
        return self
    def __exit__(self, *exc):
        return None
    def read_once(self):
        return 1.0

class Tokenizer:
    def __init__(self, *args, **kwargs):
        pass
    def count(self, text):
        return 1

urllib.request.urlopen = urlopen
h.socket.create_connection = create_connection
h.serving.Tokenizer = Tokenizer
h._corpus_text = lambda resources: "sentinel corpus text"
h.replay = replay

runtime = h.live_runtime(PRIMARY, h.CORPUS_DIR, PASSING_GATES)
healthy = runtime.health()
runtime.facade(time.monotonic() + 60, threading.Event(), lambda: None).complete({"prompt": "x"})
runtime.gtt_sampler = QuietGtt
try:
    h.live_secondary_gate(runtime)()
except StopAfterProps:
    pass
loaded = sys.modules.get("graphiti_core")
print(json.dumps({"reads": [k for k in reads if k in WATCHED], "healthy": healthy, **seen,
                  "graphiti_real": loaded is not None and hasattr(loaded, "Graphiti")}))
'''


def _run_child(plant: str = "") -> dict[str, Any]:
    env = {k: v for k, v in os.environ.items() if k != "OPENAI_API_KEY"}
    env.update(ENDPOINT_OVERRIDES)
    inherited = env.get("PYTHONPATH")
    env["PYTHONPATH"] = os.pathsep.join(p for p in (inherited, str(REPO_ROOT)) if p)
    argv = [sys.executable, "-c", CHILD, json.dumps(sorted(ENDPOINT_OVERRIDES)), json.dumps(COMPLETION_RESPONSE)]
    if plant:
        argv.append(plant)
    proc = subprocess.run(argv, env=env, cwd=REPO_ROOT, timeout=120, check=False,
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    result: dict[str, Any] = json.loads(proc.stdout.strip().splitlines()[-1])
    return result


def test_no_endpoint_override_is_read_at_import_or_construction():
    """T-c (C-001): set every override BEFORE import, in a fresh process; assert zero reads."""
    result = _run_child()
    assert result["reads"] == []                                            # (ii) zero reads
    assert result["healthy"] is True
    assert result["bridge"] == [list(IN_NETWORK_FALKOR)]                    # (i) the in-network pair
    assert result["sockets"] == [list(IN_NETWORK_FALKOR)]
    assert result["urls"] == [f"{IN_NETWORK_LLAMA}/health", f"{IN_NETWORK_LLAMA}/props",
                              f"{IN_NETWORK_LLAMA}/completion", f"{IN_NETWORK_LLAMA}/props"]
    assert result["graphiti_real"] is False


#: Every read form the recorder must see. Each is executed inside the child's fake
#: ``make_bridge``, i.e. during ``live_runtime`` construction, exactly where a regression would
#: sit. The first is the post-merge review's probe, which the old dict-subclass recorder missed.
PLANTED_READS = {
    "review-probe-dict-items": 'captured = dict(os.environ.items())\ncaptured["ARMS849_FALKOR_HOST"]',
    "get": 'os.environ.get("ARMS849_FALKOR_HOST")',
    "subscript": 'os.environ["ARMS849_LLAMA_PORT"]',
    "getenv": 'os.getenv("ARMS849_LLAMA_HOST")',
    "contains": '"ARMS849_FALKOR_PORT" in os.environ',
    "alias": 'env = os.environ\nenv.get("ARMS849_LLAMA_HOST")',
    "from-import-alias": 'from os import environ as e\ne.get("ARMS849_LLAMA_HOST")',
    "variable-key": 'k = "ARMS849_" + "FALKOR_" + "HOST"\nos.environ.get(k)',
    "dict-copy": 'dict(os.environ)',
    "copy-method": 'os.environ.copy()',
    "unpack": '{**os.environ}',
    "iterate": '[k for k in os.environ]',
    "keys": 'list(os.environ.keys())',
    "values": 'list(os.environ.values())',
    "items": 'list(os.environ.items())',
    "update-into-dict": 'd = {}\nd.update(os.environ)',
    "environb": 'os.environb.get(b"ARMS849_FALKOR_HOST")',
    "getenvb": 'os.getenvb(b"ARMS849_LLAMA_PORT")',
}


@pytest.mark.parametrize("plant", PLANTED_READS.values(), ids=PLANTED_READS.keys())
def test_planted_environment_read_is_recorded(plant):
    """Non-vacuity for T-c, committed: the same child with a planted read must NOT report zero
    reads. If this goes green-for-the-wrong-reason (empty reads), T-c's zero is meaningless."""
    result = _run_child(plant)
    assert result["reads"] != [], f"planted read was not recorded: {plant!r}"
    assert set(result["reads"]) <= set(ENDPOINT_OVERRIDES)


# --------------------------------------------------------------------------
# C-001 static guard (#1083 post-merge review: the regex line-scanner missed multiline calls,
# variable keys and aliases). It lives here, not in test_arms849_integration.py, because that
# module skips wholesale without the corpus; this one runs in repo CI.
# --------------------------------------------------------------------------

#: The rule, and why it is this rule. A read of these variables has to obtain the NAME from
#: somewhere. Rather than enumerate read shapes (get/[]/getenv/aliases/multiline/variable keys
#: — the regex lost that race), the guard bans the name itself: no string literal under scripts/
#: may contain the ARMS849_FALKOR / ARMS849_LLAMA prefix at all. That covers every read shape
#: at once, plus fragments ("ARMS849_LLAMA_" + "HOST") and the forbidden ARMS849_LLAMA_HOSTS
#: (C-002). Comments are not in the AST, so prose there is free; a docstring IS a literal and
#: is held to the rule (reword it).
#:
#: ONE allowlisted site: the four keys of the dict literal bound to HOST_LIVE_ENDPOINT_ENV in
#: scripts/research/check_849_premerge.py. The checker WRITES them into the live child's
#: environment and verifies the recorded evidence; it never reads the operator's. Each
#: allowlisted key must appear there exactly once (the allowlist cannot rot into a blanket
#: file exemption). Because that mapping is then a second way to obtain the names, any
#: reference to HOST_LIVE_ENDPOINT_ENV outside its home module is also an offence.
#:
#: Residual, deliberately left to T-c's runtime recorder: names built from fragments that do
#: not contain the prefix (chr(), "ARMS849_" + "FAL" + "KOR_HOST", decoding) and reads via
#: posix.environ. T-c covers those for the production construction path.
_C001_PREFIXES = ("ARMS849_FALKOR", "ARMS849_LLAMA")
_C001_NAMES = frozenset(ENDPOINT_OVERRIDES)
_C001_HOME = pathlib.Path("scripts/research/check_849_premerge.py")
_C001_MAPPING = "HOST_LIVE_ENDPOINT_ENV"


def _allowlisted_key_nodes(tree: ast.Module) -> list[ast.Constant]:
    """The key Constants of ``HOST_LIVE_ENDPOINT_ENV = MappingProxyType({...})`` at module level."""
    for node in tree.body:
        if isinstance(node, ast.AnnAssign):
            target, value = node.target, node.value
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        else:
            continue
        if not (isinstance(target, ast.Name) and target.id == _C001_MAPPING):
            continue
        if isinstance(value, ast.Call) and len(value.args) == 1:
            value = value.args[0]
        if isinstance(value, ast.Dict):
            return [k for k in value.keys if isinstance(k, ast.Constant)]
    return []


def _c001_offences(root: pathlib.Path) -> tuple[list[str], list[str]]:
    """(offences, allowlisted key names actually found at the home site)."""
    offences: list[str] = []
    allowlisted: list[str] = []
    for path in sorted((root / "scripts").rglob("*.py")):
        rel = path.relative_to(root)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(rel))
        exempt: set[int] = set()
        if rel == _C001_HOME:
            for key in _allowlisted_key_nodes(tree):
                if key.value in _C001_NAMES:
                    exempt.add(id(key))
                    allowlisted.append(key.value)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, (str, bytes)):
                text = node.value.decode("latin-1") if isinstance(node.value, bytes) else node.value
                if any(prefix in text for prefix in _C001_PREFIXES) and id(node) not in exempt:
                    offences.append(f"{rel}:{node.lineno}: literal {node.value!r}")
            elif rel != _C001_HOME:
                ref = (node.id if isinstance(node, ast.Name) else
                       node.attr if isinstance(node, ast.Attribute) else
                       node.name if isinstance(node, ast.alias) else None)
                if ref == _C001_MAPPING:
                    offences.append(f"{rel}:{getattr(node, 'lineno', '?')}: references {_C001_MAPPING}")
    return offences, allowlisted


def test_no_production_module_names_the_host_endpoint_variables():
    """C-001 (static): outside the checker's one write-side mapping, nothing under scripts/
    contains the endpoint variable names, so nothing there can read them by any route."""
    offences, allowlisted = _c001_offences(REPO_ROOT)
    assert offences == []
    assert sorted(allowlisted) == sorted(_C001_NAMES), "the allowlisted site moved or changed shape"
