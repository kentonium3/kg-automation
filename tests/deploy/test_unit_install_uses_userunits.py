"""New unit-installing deploy code must use scripts.deploy.lib.userunits (#1066).

About twenty historical entrypoints each re-implemented copy, daemon-reload,
restart and verify, and they diverged on correctness: only #1062's verified
the loaded config and polled for a next elapse. A prose rule would not stop
the next deploy from copying the freshest one as a template, so this guard is
default-deny. Any Python file under scripts/deploy/ that runs
``systemctl --user daemon-reload`` must import ``scripts.deploy.lib.userunits``,
unless it is a frozen historical entrypoint listed below. An entry is removed
when its script migrates; nothing can be added, because every entry must be
the recorded entrypoint of a deploy already applied at or before
``_FROZEN_MAX_APPLIED`` (independent evidence that it is historical).
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[2]
_DEPLOY = _ROOT / "scripts" / "deploy"

# Entrypoints of deploys already applied (0011-0029), frozen as of 2026-10-14.
# They re-run only by hand; each migrates when it next needs editing.
HISTORICAL_ALLOWLIST = frozenset({
    "scripts/deploy/deploy-backup-script-drift.py",
    "scripts/deploy/deploy-crontab-capture.py",
    "scripts/deploy/deploy-deterministic-monitoring-checks.py",
    "scripts/deploy/deploy-felix-canary.py",
    "scripts/deploy/deploy-felix-vikunja-sync-units.py",
    "scripts/deploy/deploy-habits-weekly-driver.py",
    "scripts/deploy/deploy-openclaw-update-check.py",
    "scripts/deploy/deploy-truthful-reporting.py",
    "scripts/deploy/deploy-unified-alert-bus.py",
    "scripts/deploy/install-gateway-pythonpath-dropin.py",
})

_FROZEN_MAX_APPLIED = 32  # deploys/applied/0032-*: the last applied deploy when frozen
_RELOAD = re.compile(r"daemon-reload")


def _imports_userunits(text: str) -> bool:
    """True only for a real import of scripts.deploy.lib.userunits (parsed, so
    comments, strings and look-alike module names do not count)."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(a.name == "scripts.deploy.lib.userunits" for a in node.names):
                return True
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            if node.module == "scripts.deploy.lib.userunits":
                return True
            if node.module == "scripts.deploy.lib" and any(a.name == "userunits" for a in node.names):
                return True
    return False


def _applied_entrypoints() -> dict[str, int]:
    """entrypoint path -> applied sequence number, from deploys/applied/."""
    out: dict[str, int] = {}
    for rec in sorted((_ROOT / "deploys" / "applied").glob("[0-9][0-9][0-9][0-9]-*.yaml")):
        data = yaml.safe_load(rec.read_text(encoding="utf-8")) or {}
        ep = data.get("entrypoint")
        if isinstance(ep, str):
            out.setdefault(ep, int(rec.name[:4]))
    return out


def _python_files() -> list[Path]:
    return sorted(p for p in _DEPLOY.rglob("*.py")
                  if "lib" not in p.relative_to(_DEPLOY).parts[:1] and "__pycache__" not in p.parts)


def _offenders(paths: list[Path] | None = None, root: Path = _ROOT) -> list[str]:
    out = []
    for path in (paths if paths is not None else _python_files()):
        text = path.read_text(encoding="utf-8")
        rel = str(path.relative_to(root))
        if _RELOAD.search(text) and not _imports_userunits(text) and rel not in HISTORICAL_ALLOWLIST:
            out.append(rel)
    return out


def test_new_unit_installing_code_uses_userunits():
    assert _offenders() == [], (
        "these deploy scripts run daemon-reload without scripts.deploy.lib.userunits; "
        f"use the library instead of copying an old entrypoint (#1066): {_offenders()}"
    )


def test_allowlist_is_live_and_necessary():
    """Shrink-only: every entry still exists, still reloads, and has not already
    migrated (a migrated script must leave the list)."""
    for rel in HISTORICAL_ALLOWLIST:
        path = _ROOT / rel
        assert path.is_file(), f"stale allowlist entry: {rel}"
        text = path.read_text(encoding="utf-8")
        assert _RELOAD.search(text), f"{rel} no longer reloads; remove it from the allowlist"
        assert not _imports_userunits(text), f"{rel} uses userunits now; remove it from the allowlist"


def test_allowlist_cannot_grow():
    """Every entry is the entrypoint of a deploy applied at or before the
    freeze. A new hand-rolled installer has no such record, so it cannot be
    added (Codex #1066 review)."""
    applied = _applied_entrypoints()
    for rel in HISTORICAL_ALLOWLIST:
        assert rel in applied, f"{rel} is not the entrypoint of any applied deploy"
        assert applied[rel] <= _FROZEN_MAX_APPLIED, f"{rel} was applied after the freeze ({applied[rel]})"


def test_import_detection_is_parsed_not_pattern_matched():
    yes = ["from scripts.deploy.lib import userunits\n",
           "from scripts.deploy.lib import (\n    timer_units,\n    userunits,\n)\n",
           "import scripts.deploy.lib.userunits\n",
           "from scripts.deploy.lib.userunits import apply_units\n"]
    no = ["from scripts.deploy.lib import timer_units  # userunits\n",
          '"""from scripts.deploy.lib import userunits"""\n',
          "import scripts.deploy.lib.userunits_extra\n",
          "from scripts.deploy.lib import userunits_extra\n"]
    assert all(_imports_userunits(t) for t in yes)
    assert not any(_imports_userunits(t) for t in no)


def test_the_first_adopter_passes_without_an_allowlist_entry():
    rel = "scripts/deploy/deploy-monotonic-timer-units.py"
    assert rel not in HISTORICAL_ALLOWLIST
    assert _imports_userunits((_ROOT / rel).read_text(encoding="utf-8"))


def test_guard_catches_a_new_copy(tmp_path, monkeypatch):
    """Non-vacuity: a new entrypoint that copies the old pattern is caught."""
    new = tmp_path / "scripts" / "deploy" / "deploy-new-thing.py"
    new.parent.mkdir(parents=True)
    new.write_text('import subprocess\nsubprocess.run(["systemctl", "--user", "daemon-reload"])\n')
    adopted = tmp_path / "scripts" / "deploy" / "deploy-adopted.py"
    adopted.write_text("from scripts.deploy.lib import userunits\n# runs daemon-reload via apply_units\n")
    assert _offenders([new, adopted], root=tmp_path) == ["scripts/deploy/deploy-new-thing.py"]
