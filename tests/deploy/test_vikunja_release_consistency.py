"""Cross-module consistency for the Vikunja release route (#1087).

STAGE, ACTIVATE and the rollback helper were written as separate work
packages; these tests pin the values they must agree on, so a later edit to
one cannot drift from the others or from the systemd unit:

* the rollback version both ACTIVATE and rollback derive from release.json;
* the Compose argv ACTIVATE and rollback run, against vikunja.service's
  ExecStart / ExecStop (STAGE runs no Compose at all);
* the one shared ``activation.lock`` name and helper.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import shlex
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.deploy.vikunja_release import dbsafety

_ROOT = Path(__file__).resolve().parents[2]
_RELEASE = json.loads((_ROOT / "services" / "vikunja" / "release.json").read_text(encoding="utf-8"))
_UNIT = _ROOT / "scripts" / "vikunja" / "vikunja.service"
_STAGE = _ROOT / "scripts" / "deploy" / "deploy-vikunja-release-stage.py"
_ACTIVATE = _ROOT / "scripts" / "deploy" / "deploy-vikunja-release-activate.py"
_ROLLBACK = _ROOT / "scripts" / "vikunja" / "rollback_release.py"
_DBSAFETY = _ROOT / "scripts" / "deploy" / "vikunja_release" / "dbsafety.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


stage = _load(_STAGE, "consistency_stage")
activate = _load(_ACTIVATE, "consistency_activate")
rollback = _load(_ROLLBACK, "consistency_rollback")


def _unit_argv(key: str) -> list[str]:
    for line in _UNIT.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{key}="):
            argv = shlex.split(line.split("=", 1)[1])
            return [Path(argv[0]).name, *argv[1:]]  # /usr/bin/docker -> docker (PATH lookup)
    raise AssertionError(f"{key} missing from {_UNIT}")


def _rollback_compose_argv(*action: str) -> list[str]:
    seen: list[list[str]] = []

    def runner(argv, **kw):
        seen.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, "", "")

    ctx = SimpleNamespace(compose_file=_RELEASE["service"]["compose_file"], runner=runner)
    rollback._compose(ctx, *action)
    assert len(seen) == 1
    return seen[0]


def _activate_compose_argv(*action: str) -> list[str]:
    return activate.Activate._compose_argv(SimpleNamespace(compose_file=_RELEASE["service"]["compose_file"]),
                                           *action)


def test_rollback_version_is_derived_the_same_way():
    tag = _RELEASE["rollback"]["ref"].rsplit(":", 1)[1]
    expected = tag if tag.startswith("v") else "v" + tag
    assert activate.rollback_version(_RELEASE) == expected
    assert rollback.rollback_version(_RELEASE) == expected


@pytest.mark.parametrize("tag,expected", [
    ("2.4.0", "v2.4.0"),
    ("v3.0.0-rrule.2", "v3.0.0-rrule.2"),
    ("3.0.0-rrule.2", "v3.0.0-rrule.2"),
    ("v3.0.0-671-0123456789", "v3.0.0-671-0123456789"),
    ("3.0.0-671-0123456789", "v3.0.0-671-0123456789"),
])
def test_rollback_version_normalization(tag, expected):
    other = json.loads(json.dumps(_RELEASE))
    other["rollback"]["ref"] = "example.invalid/app:" + tag
    assert activate.rollback_version(other) == expected
    assert rollback.rollback_version(other) == expected


def test_frozen_first_cutover_rollback_version():
    historical = json.loads((_ROOT / "tests/deploy/fixtures/vikunja_first_cutover_release.json").read_text())
    assert activate.rollback_version(historical) == "v2.4.0"
    assert rollback.rollback_version(historical) == "v2.4.0"


@pytest.mark.parametrize("key,action", [("ExecStart", ("up", "-d")), ("ExecStop", ("down",))])
def test_compose_argv_matches_the_unit(key, action):
    unit = _unit_argv(key)
    assert unit[:4] == ["docker", "compose", "-f", _RELEASE["service"]["compose_file"]]
    assert _activate_compose_argv(*action) == unit
    assert _rollback_compose_argv(*action) == unit


def _string_constants(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def test_stage_runs_no_compose():
    assert "compose" not in _string_constants(_STAGE)
    # Control: the scan does find it where it is used.
    assert "compose" in _string_constants(_ACTIVATE) and "compose" in _string_constants(_ROLLBACK)


def test_one_shared_activation_lock():
    assert stage.dbsafety.ACTIVATION_LOCK_NAME == "activation.lock"
    assert activate.ACTIVATION_LOCK_NAME is dbsafety.ACTIVATION_LOCK_NAME
    assert rollback.ACTIVATION_LOCK_NAME is dbsafety.ACTIVATION_LOCK_NAME
    for path in (_STAGE, _ACTIVATE, _ROLLBACK):
        text = path.read_text(encoding="utf-8")
        assert "take_activation_lock(" in text, path
        assert "activation.lock" not in _string_constants(path), path  # no private copy of the name
    assert "activation.lock" in _string_constants(_DBSAFETY)  # control: the one definition
