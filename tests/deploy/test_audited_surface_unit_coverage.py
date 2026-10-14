"""Every tracked systemd unit is inside an audited surface, or exempt by name
(kentonium3/kg-automation#1065).

The security audit hashes the contents of every file under
``~/.config/systemd/user`` into ``systemd-user-unit-contents.txt``.
felix-deployer only expects that baseline to drift when the commit range it
pulled changes a path matched by
``docs/design/architecture/data/audited-surfaces.json``. A deployed unit that
lives outside every pattern therefore ends in ``unexpected_drift`` when a
commit edits it and deploys it. Before #1065, five did: openclaw-gateway, the
two felix-vikunja-sync units, and felix-deployer's own two units.

(Deploy 0029 also ended ``unexpected_drift``, but for a different reason: it
re-installed units changed in an earlier commit, and so needed
``expected_baselines``. A pattern would not have helped. See the last
paragraph below.)

This guard is default-deny: a new unit directory fails here until it is
covered by a pattern or listed in the registry's ``system_scope_units`` with a
reason. It uses the real matcher that felix-deployer and the CI reminder use.

It enforces the repo-path convention, not the deployed set: the deployer works
from git diffs, so the repo path is the only signal it has. And a pattern only
helps a deploy whose own commit range changes the file. A deploy that installs
files changed earlier still has to declare ``expected_baselines``; that is what
0029 actually missed (docs/runbooks/deployment.md, #1072).
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_REGISTRY = _ROOT / "docs" / "design" / "architecture" / "data" / "audited-surfaces.json"

_spec = importlib.util.spec_from_file_location(
    "audited_surfaces_unit_coverage", _ROOT / "tooling" / "scripts" / "audited_surfaces.py"
)
_matcher = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _matcher
_spec.loader.exec_module(_matcher)

_UNIT_SUFFIXES = (".service", ".timer", ".target", ".path", ".socket", ".mount",
                  ".automount", ".slice", ".swap")


def _tracked_unit_files() -> list[str]:
    """Unit files, plus every file inside a ``<unit>.<suffix>.d/`` drop-in dir."""
    out = subprocess.run(["git", "ls-files"], cwd=_ROOT, capture_output=True, text=True, check=True)
    dropin_dirs = tuple(s + ".d" for s in _UNIT_SUFFIXES)
    return sorted(
        path for path in out.stdout.splitlines()
        if Path(path).name.endswith(_UNIT_SUFFIXES) or Path(path).parent.name.endswith(dropin_dirs)
    )


def _registry() -> dict:
    return json.loads(_REGISTRY.read_text(encoding="utf-8"))


_UNIT_CONTENT_BASELINE = "systemd-user-unit-contents.txt"


def _patterns() -> list[str]:
    """Patterns of the surfaces that make the deployer EXPECT unit-content
    drift. A unit matched only by some other surface (e.g. deploy-pipeline,
    whose affected_baselines is empty) still ends unexpected_drift, so it
    does not count as covered (post-merge Codex review)."""
    return [p for s in _registry()["audited_surfaces"]
            if _UNIT_CONTENT_BASELINE in s.get("affected_baselines", [])
            for p in s["patterns"]]


def test_a_unit_matched_only_by_an_unrelated_surface_is_not_covered():
    """Non-vacuity for the baseline filter: deploy-pipeline's scripts/deploy/*.sh
    would match a unit named like a shell script, but it declares no baselines."""
    registry = _registry()
    pipeline = next(s for s in registry["audited_surfaces"] if s["id"] == "deploy-pipeline")
    assert _UNIT_CONTENT_BASELINE not in pipeline.get("affected_baselines", [])
    assert any(_matcher.file_matches_pattern("scripts/deploy/x.service.sh", p) for p in pipeline["patterns"])
    assert not _covered("scripts/deploy/x.service.sh", _patterns())


def _exempt() -> dict[str, str]:
    """``system_scope_units``: units deliberately outside every surface, each
    with a reason (audit.sh fingerprints only user-scope unit contents)."""
    return {e["path"]: e["reason"] for e in _registry().get("system_scope_units", [])}


def _covered(path: str, patterns: list[str]) -> bool:
    return any(_matcher.file_matches_pattern(path, p) for p in patterns)


def test_selection_finds_units_and_dropins():
    """Non-vacuity: the selection really sees the repo's units and drop-ins."""
    units = _tracked_unit_files()
    assert "scripts/office2/felix-canary.timer" in units
    assert "scripts/sync/systemd/felix-vikunja-sync.service" in units
    assert any("/openclaw-gateway.service.d/" in u for u in units), "drop-ins must be selected"
    assert len(units) >= 40


def test_every_tracked_unit_is_audited_or_exempt():
    patterns = _patterns()
    outside = [u for u in _tracked_unit_files() if not _covered(u, patterns) and u not in _exempt()]
    assert outside == [], (
        "these tracked unit files match no audited-surface pattern; a deploy that touches one "
        "ends in unexpected_drift (#1065). Add a pattern to audited-surfaces.json, or, for a "
        f"system-scope unit, a system_scope_units entry with a reason: {outside}"
    )


def test_exemptions_are_live_and_necessary():
    patterns = _patterns()
    tracked = set(_tracked_unit_files())
    exempt = _exempt()
    assert exempt, "system_scope_units is expected to list vikunja and transcribe"
    for path, reason in exempt.items():
        assert path in tracked, f"stale exemption, no such tracked unit: {path}"
        assert not _covered(path, patterns), f"exemption is redundant, a pattern already covers {path}"
        assert reason.strip()


def test_the_felix_vikunja_sync_units_are_covered():
    """Two of the five units this change brings under the systemd-user-units
    surface (not a fix for 0029 itself; see the module docstring)."""
    patterns = _patterns()
    for path in ("scripts/sync/systemd/felix-vikunja-sync.service",
                 "scripts/sync/systemd/felix-vikunja-sync.timer"):
        assert _covered(path, patterns), path


def test_unit_files_under_unlisted_suffixes_are_selected(tmp_path, monkeypatch):
    """Non-vacuity for the default-deny: a tracked .socket in a new directory is
    selected and reported as outside, not silently skipped."""
    real_run = subprocess.run

    def fake_run(argv, **kw):
        result = real_run(argv, **kw)
        if argv[:2] == ["git", "ls-files"]:
            result.stdout += "scripts/newdir/thing.socket\n"
        return result

    monkeypatch.setattr(subprocess, "run", fake_run)
    patterns = _patterns()
    outside = [u for u in _tracked_unit_files() if not _covered(u, patterns) and u not in _exempt()]
    assert outside == ["scripts/newdir/thing.socket"]
