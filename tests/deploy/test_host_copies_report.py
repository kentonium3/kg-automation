"""Deploy entrypoints that copy files onto the host must report them (#1072).

felix-deployer expects the security-monitor drift a deploy causes from two
sources: the files changed in the pulled commit range, and the installed-file
report (scripts/deploy/lib/installed_report.py) that library installers write
for every file they land. An entrypoint that copies files itself reports
nothing, so a re-install of files changed earlier ends in a false
``unexpected_drift`` alert (deploy 0029).

This guard is default-deny over deploy entrypoints: a Python file named as a
manifest ``entrypoint:`` in deploys/queued/ or deploys/applied/, or a
top-level scripts/deploy/deploy-*.py / install-*.py, may not call
``shutil.copy``/``copy2``/``copyfile``/``copytree``, ``os.replace`` or
``.write_text``/``.write_bytes`` unless it imports
``scripts.deploy.lib.userunits`` or ``scripts.deploy.lib.installed_report``.
Historical entrypoints are exempt only with evidence: each exemption is the
entrypoint of a deploy applied at or before ``_FROZEN_MAX_APPLIED``, and the
list is shrink-only.

Calls are matched through however the module was bound: ``shutil.copy2``,
``import shutil as sh; sh.copy2``, and ``from shutil import copy2; copy2``.

Stated limits (accepted; the guard is a tripwire for the common shapes, not a
proof): a copy delegated to a helper module (anything outside the entrypoint
file), ``open(..., "w")``, ``shutil.move`` / ``os.rename``, a subprocess
``cp`` / ``install``, and an entrypoint that imports a reporting module but
never calls it (the import is a presence check, not proof of reporting).
Library code under scripts/deploy/lib/ and felix-deployer/ is out of scope by
design.
"""
from __future__ import annotations

import ast
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[2]
_DEPLOY = _ROOT / "scripts" / "deploy"
_FROZEN_MAX_APPLIED = 32  # deploys/applied/0032-*: the last applied deploy when frozen

_COPY_FUNCS = {("shutil", "copy"), ("shutil", "copy2"), ("shutil", "copyfile"),
               ("shutil", "copytree"), ("os", "replace")}
_WRITE_METHODS = {"write_text", "write_bytes"}
_REPORTING_MODULES = {"scripts.deploy.lib.userunits", "scripts.deploy.lib.installed_report"}

# Entrypoints of deploys already applied (0006-0029) that copy files without
# reporting them, frozen 2026-10-15. Each re-runs only by hand and leaves this
# list when it next needs editing (install through userunits, or report).
HISTORICAL_EXEMPT = frozenset({
    "scripts/deploy/deploy-backup-script-drift.py",
    "scripts/deploy/deploy-crontab-capture.py",
    "scripts/deploy/deploy-deterministic-monitoring-checks.py",
    "scripts/deploy/deploy-felix-canary.py",
    "scripts/deploy/deploy-felix-vikunja-sync-units.py",
    "scripts/deploy/deploy-habits-weekly-driver.py",
    "scripts/deploy/deploy-openclaw-bin-seam.py",
    "scripts/deploy/deploy-openclaw-update-check.py",
    "scripts/deploy/deploy-security-monitor-audit.py",
    "scripts/deploy/deploy-truthful-reporting.py",
    "scripts/deploy/deploy-unified-alert-bus.py",
    "scripts/deploy/install-gateway-pythonpath-dropin.py",
    "scripts/deploy/migrate-inbox-state-and-logs.py",
})


def _imports_reporter(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(a.name in _REPORTING_MODULES for a in node.names):
                return True
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            if node.module in _REPORTING_MODULES:
                return True
            if node.module == "scripts.deploy.lib" and any(
                    f"scripts.deploy.lib.{a.name}" in _REPORTING_MODULES for a in node.names):
                return True
    return False


def _bindings(tree: ast.AST) -> tuple[dict[str, str], dict[str, tuple[str, str]]]:
    """Local names for the modules and functions in _COPY_FUNCS:
    ``{alias: module}`` from ``import shutil [as sh]`` and
    ``{name: (module, func)}`` from ``from shutil import copy2 [as cp]``."""
    modules = {mod for mod, _ in _COPY_FUNCS}
    mod_alias: dict[str, str] = {}
    func_alias: dict[str, tuple[str, str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name in modules:
                    mod_alias[a.asname or a.name] = a.name
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module in modules:
            for a in node.names:
                if (node.module, a.name) in _COPY_FUNCS:
                    func_alias[a.asname or a.name] = (node.module, a.name)
    return mod_alias, func_alias


def _copies(tree: ast.AST) -> list[str]:
    mod_alias, func_alias = _bindings(tree)
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id in func_alias:
            found.append("{}.{}".format(*func_alias[func.id]))
        elif isinstance(func, ast.Attribute):
            base = func.value
            if isinstance(base, ast.Name) and (mod_alias.get(base.id), func.attr) in _COPY_FUNCS:
                found.append(f"{mod_alias[base.id]}.{func.attr}")
            elif func.attr in _WRITE_METHODS:
                found.append(f".{func.attr}")
    return found


def _manifest_entrypoints(root: Path = _ROOT) -> dict[str, int | None]:
    """entrypoint -> applied sequence number (None when only queued)."""
    out: dict[str, int | None] = {}
    for sub in ("applied", "queued"):
        for rec in sorted((root / "deploys" / sub).glob("*.yaml")):
            try:
                data = yaml.safe_load(rec.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError:
                continue
            ep = data.get("entrypoint") if isinstance(data, dict) else None
            if not isinstance(ep, str) or not ep.endswith(".py"):
                continue
            seq = int(rec.name[:4]) if sub == "applied" and rec.name[:4].isdigit() else None
            if ep not in out or (seq is not None and (out[ep] is None or seq < out[ep])):
                out[ep] = seq
    return out


def _in_scope(root: Path = _ROOT) -> list[str]:
    deploy = root / "scripts" / "deploy"
    rels = set(_manifest_entrypoints(root))
    for pattern in ("deploy-*.py", "install-*.py"):
        rels.update(str(p.relative_to(root)) for p in deploy.glob(pattern))
    return sorted(r for r in rels
                  if not r.startswith(("scripts/deploy/lib/", "scripts/deploy/felix-deployer/"))
                  and (root / r).is_file())


def _offenders(root: Path = _ROOT, exempt: frozenset[str] = HISTORICAL_EXEMPT) -> list[str]:
    out = []
    for rel in _in_scope(root):
        try:
            tree = ast.parse((root / rel).read_text(encoding="utf-8"))
        except SyntaxError:
            out.append(rel)
            continue
        if _copies(tree) and not _imports_reporter(tree) and rel not in exempt:
            out.append(rel)
    return out


def test_entrypoints_that_copy_files_report_them():
    assert _offenders() == [], (
        "these deploy entrypoints write files onto the host without reporting them; "
        "install through scripts.deploy.lib.userunits, or call "
        f"installed_report.record_installed for each file (#1072): {_offenders()}"
    )


def test_exemptions_are_live_and_necessary():
    for rel in HISTORICAL_EXEMPT:
        path = _ROOT / rel
        assert path.is_file(), f"stale exemption: {rel}"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        assert _copies(tree), f"{rel} no longer copies files; remove its exemption"
        assert not _imports_reporter(tree), f"{rel} reports now; remove its exemption"


def test_exemptions_cannot_grow():
    applied = _manifest_entrypoints()
    for rel in HISTORICAL_EXEMPT:
        assert applied.get(rel) is not None, f"{rel} is not the entrypoint of an applied deploy"
        assert applied[rel] <= _FROZEN_MAX_APPLIED, f"{rel} was applied after the freeze ({applied[rel]})"


def test_guard_catches_a_new_copier_and_passes_an_adopter(tmp_path):
    deploy = tmp_path / "scripts" / "deploy"
    (deploy / "lib").mkdir(parents=True)
    (tmp_path / "deploys" / "queued").mkdir(parents=True)
    (tmp_path / "deploys" / "applied").mkdir(parents=True)
    (deploy / "deploy-new-thing.py").write_text("import shutil\nshutil.copy2('a', 'b')\n")
    (deploy / "deploy-writes.py").write_text("from pathlib import Path\nPath('x').write_text('y')\n")
    (deploy / "deploy-adopted.py").write_text(
        "import shutil\nfrom scripts.deploy.lib import userunits\nshutil.copy2('a', 'b')\n")
    (deploy / "deploy-reporter.py").write_text(
        "import os\nfrom scripts.deploy.lib.installed_report import record_installed\nos.replace('a', 'b')\n")
    (deploy / "deploy-from-import.py").write_text("from shutil import copy2\ncopy2('a', 'b')\n")
    (deploy / "deploy-alias.py").write_text("import os as o\no.replace('a', 'b')\n")
    (deploy / "lib" / "helper.py").write_text("import shutil\nshutil.copy('a', 'b')\n")
    (deploy / "helper_not_entrypoint.py").write_text("import shutil\nshutil.copy('a', 'b')\n")
    (deploy / "migrate-thing.py").write_text("import os\nos.replace('a', 'b')\n")
    (tmp_path / "deploys" / "queued" / "0099-m.yaml").write_text(
        "name: 0099-m\nentrypoint: scripts/deploy/migrate-thing.py\n")
    assert _offenders(tmp_path, frozenset()) == [
        "scripts/deploy/deploy-alias.py",
        "scripts/deploy/deploy-from-import.py",
        "scripts/deploy/deploy-new-thing.py",
        "scripts/deploy/deploy-writes.py",
        "scripts/deploy/migrate-thing.py",
    ]


def test_detection_is_parsed_not_pattern_matched():
    assert _copies(ast.parse("import shutil\nshutil.copyfile(a, b)\n")) == ["shutil.copyfile"]
    assert _copies(ast.parse("from shutil import copy2\ncopy2(a, b)\n")) == ["shutil.copy2"]
    assert _copies(ast.parse("import shutil as sh\nsh.copytree(a, b)\n")) == ["shutil.copytree"]
    assert _copies(ast.parse("from os import replace as rp\nrp(a, b)\n")) == ["os.replace"]
    # a bare name that is not bound from shutil/os is not a copy
    assert _copies(ast.parse("def copy2(a, b): pass\ncopy2(a, b)\n")) == []
    assert _copies(ast.parse("shutil.copy2(a, b)\n")) == []  # never imported
    assert _copies(ast.parse("# shutil.copy(a, b)\nx = 'os.replace(a, b)'\n")) == []
    assert _imports_reporter(ast.parse("from scripts.deploy.lib import installed_report\n"))
    assert not _imports_reporter(ast.parse("from scripts.deploy.lib import installed_report_extra\n"))
    assert not _imports_reporter(ast.parse('"""from scripts.deploy.lib import userunits"""\n'))
