"""New unit-installing deploy code must use scripts.deploy.lib.userunits (#1066).

About twenty historical entrypoints each re-implemented copy, daemon-reload,
restart and verify, and they diverged on correctness: only #1062's verified
the loaded config and polled for a next elapse. A prose rule would not stop
the next deploy from copying the freshest one as a template, so this guard is
default-deny. Any Python file under scripts/deploy/ that runs
``systemctl --user daemon-reload`` must import ``scripts.deploy.lib.userunits``,
unless it is a frozen historical entrypoint listed below. An entry is removed
when its script migrates; nothing is ever added.
"""
from __future__ import annotations

import re
from pathlib import Path

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

_RELOAD = re.compile(r"daemon-reload")
_IMPORTS_LIB = re.compile(r"^\s*(from\s+scripts\.deploy\.lib\s+import\s+[^\n]*\buserunits\b"
                          r"|from\s+scripts\.deploy\.lib\.userunits\s+import"
                          r"|import\s+scripts\.deploy\.lib\.userunits)", re.MULTILINE)


def _python_files() -> list[Path]:
    return sorted(p for p in _DEPLOY.rglob("*.py")
                  if "lib" not in p.relative_to(_DEPLOY).parts[:1] and "__pycache__" not in p.parts)


def _offenders(paths: list[Path] | None = None, root: Path = _ROOT) -> list[str]:
    out = []
    for path in (paths if paths is not None else _python_files()):
        text = path.read_text(encoding="utf-8")
        rel = str(path.relative_to(root))
        if _RELOAD.search(text) and not _IMPORTS_LIB.search(text) and rel not in HISTORICAL_ALLOWLIST:
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
        assert not _IMPORTS_LIB.search(text), f"{rel} uses userunits now; remove it from the allowlist"


def test_the_first_adopter_passes_without_an_allowlist_entry():
    rel = "scripts/deploy/deploy-monotonic-timer-units.py"
    assert rel not in HISTORICAL_ALLOWLIST
    assert _IMPORTS_LIB.search((_ROOT / rel).read_text(encoding="utf-8"))


def test_guard_catches_a_new_copy(tmp_path, monkeypatch):
    """Non-vacuity: a new entrypoint that copies the old pattern is caught."""
    new = tmp_path / "scripts" / "deploy" / "deploy-new-thing.py"
    new.parent.mkdir(parents=True)
    new.write_text('import subprocess\nsubprocess.run(["systemctl", "--user", "daemon-reload"])\n')
    adopted = tmp_path / "scripts" / "deploy" / "deploy-adopted.py"
    adopted.write_text("from scripts.deploy.lib import userunits\n# runs daemon-reload via apply_units\n")
    assert _offenders([new, adopted], root=tmp_path) == ["scripts/deploy/deploy-new-thing.py"]
