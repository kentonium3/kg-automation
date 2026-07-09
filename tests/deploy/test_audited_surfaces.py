"""Tests for the shared audited-surface matcher (#618, WP01, NFR-001).

Loads `tooling/scripts/audited_surfaces.py` and the CI reminder
`tooling/scripts/check_audited_surface_drift.py` via importlib (the repo's
convention for tooling scripts, which are not a package) and verifies:

- `file_matches_pattern` glob semantics (`**`, single `*`, literals, non-matches)
- `match_surfaces` against fixtures mirroring the real registry shape
- NFR-001 single-source-of-truth: the CI script imports the *same* matcher
  functions (identity check — no second copy of the pattern logic exists)
- the real registry loads and matches as expected
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_TOOLING_SCRIPTS = Path(__file__).resolve().parents[2] / "tooling" / "scripts"


def _load(mod_name: str, filename: str):
    path = _TOOLING_SCRIPTS / filename
    spec = importlib.util.spec_from_file_location(mod_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


audited_surfaces = _load("audited_surfaces", "audited_surfaces.py")
check_drift = _load("check_audited_surface_drift", "check_audited_surface_drift.py")


# Fixture mirroring the real audited-surfaces.json shape (subset of surfaces).
_REGISTRY = {
    "expected_baseline_count": 14,
    "rebaseline_command": "ssh office2-claude 'rm .../baselines/* && sg docker -c .../audit.sh'",
    "audited_surfaces": [
        {
            "id": "openclaw-config",
            "description": "OpenClaw runtime config",
            "patterns": ["scripts/openclaw/openclaw.json", "scripts/openclaw/openclaw.*.json"],
            "affected_baselines": ["openclaw-config.txt", "openclaw-cron.txt"],
        },
        {
            "id": "systemd-user-units",
            "description": "systemd user units + deploy scripts",
            "patterns": ["scripts/office2/*.service", "scripts/office2/deploy/*.sh"],
            "affected_baselines": ["systemd-user-units.txt"],
        },
        {
            "id": "docker-stack",
            "description": "Docker stack files",
            "patterns": ["**/docker-compose.yml", "**/Dockerfile", "**/Dockerfile.*"],
            "affected_baselines": ["docker-images.txt", "listening-ports.txt"],
        },
    ],
}


# --- file_matches_pattern -------------------------------------------------

def test_double_star_matches_nested_and_top_level():
    assert audited_surfaces.file_matches_pattern("services/api/Dockerfile", "**/Dockerfile")
    assert audited_surfaces.file_matches_pattern("a/b/c/Dockerfile", "**/Dockerfile")
    # `**/x` is documented to also match `x` at the top level.
    assert audited_surfaces.file_matches_pattern("Dockerfile", "**/Dockerfile")


def test_double_star_does_not_match_unrelated_basename():
    assert not audited_surfaces.file_matches_pattern("services/api/Dockerfile.md", "**/Dockerfile")
    assert not audited_surfaces.file_matches_pattern("services/api/notes.txt", "**/Dockerfile")


def test_single_star_matches_segment_and_over_matches_nested():
    # `*` matches the intended file in the directory...
    assert audited_surfaces.file_matches_pattern("scripts/office2/felix.service", "scripts/office2/*.service")
    # ...and, because the matcher uses fnmatch (where `*` also crosses `/`), it
    # over-matches nested paths too. This is intentional: false positives are
    # acceptable for the CI reminder, and the deployer's audit-confirm step
    # gates any real reset. Preserved verbatim from the original CI script.
    assert audited_surfaces.file_matches_pattern("scripts/office2/sub/felix.service", "scripts/office2/*.service")
    # A non-matching extension still does not match.
    assert not audited_surfaces.file_matches_pattern("scripts/office2/felix.timer", "scripts/office2/*.service")


def test_literal_pattern_exact_match_and_nonmatch():
    assert audited_surfaces.file_matches_pattern("scripts/openclaw/openclaw.json", "scripts/openclaw/openclaw.json")
    assert not audited_surfaces.file_matches_pattern("scripts/openclaw/other.json", "scripts/openclaw/openclaw.json")


# --- match_surfaces -------------------------------------------------------

def test_openclaw_config_match_returns_affected_baselines():
    matches = audited_surfaces.match_surfaces(["scripts/openclaw/openclaw.json"], _REGISTRY)
    ids = {m["id"] for m in matches}
    assert ids == {"openclaw-config"}
    (m,) = matches
    assert m["matched_files"] == ["scripts/openclaw/openclaw.json"]
    assert m["affected_baselines"] == ["openclaw-config.txt", "openclaw-cron.txt"]


def test_docker_double_star_matches_nested_dockerfile():
    matches = audited_surfaces.match_surfaces(["services/api/Dockerfile"], _REGISTRY)
    assert {m["id"] for m in matches} == {"docker-stack"}


def test_unrelated_path_matches_nothing():
    matches = audited_surfaces.match_surfaces(["README.md", "docs/INDEX.md"], _REGISTRY)
    assert matches == []


def test_match_surfaces_dedupes_matched_files_across_patterns():
    # A path matching two patterns of one surface should appear once.
    registry = {
        "audited_surfaces": [
            {"id": "dup", "patterns": ["a/*.json", "a/b.json"], "affected_baselines": []},
        ]
    }
    matches = audited_surfaces.match_surfaces(["a/b.json"], registry)
    assert matches[0]["matched_files"] == ["a/b.json"]


# --- NFR-001 single source of truth --------------------------------------

def test_ci_script_imports_shared_matcher_not_a_copy():
    # The reminder must consume the *same* functions — proves no second
    # pattern-list/glob implementation exists (NFR-001).
    assert check_drift.match_surfaces is audited_surfaces.match_surfaces
    assert check_drift.load_audited_surfaces is audited_surfaces.load_audited_surfaces
    assert check_drift.changed_files is audited_surfaces.changed_files


# --- real registry --------------------------------------------------------

def test_real_registry_loads_and_matches():
    audited = audited_surfaces.load_audited_surfaces()
    assert audited.get("expected_baseline_count") == 14
    assert any(s["id"] == "openclaw-config" for s in audited["audited_surfaces"])
    # A real openclaw.json change matches the real openclaw-config surface.
    matches = audited_surfaces.match_surfaces(["scripts/openclaw/openclaw.json"], audited)
    assert "openclaw-config" in {m["id"] for m in matches}


def test_load_audited_surfaces_exits_2_when_missing(monkeypatch, tmp_path):
    # Preserve the exit-2 contract on a broken setup.
    monkeypatch.setattr(audited_surfaces, "AUDITED_SURFACES_PATH", tmp_path / "missing.json")
    with pytest.raises(SystemExit) as exc:
        audited_surfaces.load_audited_surfaces()
    assert exc.value.code == 2


# --- known_baselines guard (WP02 T012, Codex LOW) -------------------------

# The documented 14-baseline inventory audit.sh emits (== expected_baseline_count).
# Pinning this set catches a stale registry name that audit.sh no longer emits
# being silently accepted as a "known" declaration target.
_KNOWN_BASELINES_INVENTORY = {
    "brew-packages.txt",
    "brew-taps.txt",
    "crontabs.txt",
    "docker-images.txt",
    "enabled-services.txt",
    "hosts-hash.txt",
    "listening-ports.txt",
    "openclaw-config.txt",
    "openclaw-cron.txt",
    "pip-packages.txt",
    "pth-files.txt",
    "ssh-keys.txt",
    "systemd-user-dropins.txt",
    "systemd-user-units.txt",
}


def test_known_baselines_equals_documented_14_inventory():
    registry = audited_surfaces.load_audited_surfaces()
    names = audited_surfaces.known_baselines(registry)
    assert len(names) == 14
    assert names == _KNOWN_BASELINES_INVENTORY
    # And the registry's own count field agrees.
    assert registry.get("expected_baseline_count") == 14


def test_load_audited_surfaces_or_error_success():
    registry, reason = audited_surfaces.load_audited_surfaces_or_error()
    assert reason is None
    assert registry is not None
    assert registry.get("expected_baseline_count") == 14


def test_load_audited_surfaces_or_error_missing_does_not_exit(monkeypatch, tmp_path):
    monkeypatch.setattr(audited_surfaces, "AUDITED_SURFACES_PATH", tmp_path / "missing.json")
    registry, reason = audited_surfaces.load_audited_surfaces_or_error()
    assert registry is None
    assert reason is not None and "not found" in reason


def test_load_audited_surfaces_or_error_malformed_does_not_exit(monkeypatch, tmp_path):
    bad = tmp_path / "audited-surfaces.json"
    bad.write_text("{ not valid json", encoding="utf-8")
    monkeypatch.setattr(audited_surfaces, "AUDITED_SURFACES_PATH", bad)
    registry, reason = audited_surfaces.load_audited_surfaces_or_error()
    assert registry is None
    assert reason is not None and "malformed" in reason


def test_known_baselines_unions_surfaces_and_non_repo():
    registry = {
        "audited_surfaces": [
            {"id": "a", "affected_baselines": ["one.txt", "two.txt"]},
            {"id": "b", "affected_baselines": ["two.txt"]},
        ],
        "non_repo_baselines": [{"name": "three.txt"}, {"name": "one.txt"}],
    }
    assert audited_surfaces.known_baselines(registry) == {"one.txt", "two.txt", "three.txt"}
