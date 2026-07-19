"""Tests for scripts.openclaw.enforcement.skills_drift_check (#775, WP02).

The comparator is independent of the sync (deploy_agent_skills) by design — these
tests build repo + deployed trees in tmp and drive the comparator directly.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.openclaw.enforcement import skills_drift_check as sdc


def _repo(tmp_path: Path, skills: dict[str, dict]) -> Path:
    """skills maps name -> {files: {fname: content}} under scripts/openclaw/skills/."""
    root = tmp_path / "repo"
    for name, spec in skills.items():
        d = root / "scripts" / "openclaw" / "skills" / name
        d.mkdir(parents=True)
        for fname, content in spec.get("files", {}).items():
            (d / fname).write_text(content, encoding="utf-8")
    return root


def _deployed(tmp_path: Path, skills: dict[str, dict]) -> Path:
    base = tmp_path / "deployed" / "skills"
    for name, spec in skills.items():
        d = base / name
        d.mkdir(parents=True)
        for fname, content in spec.get("files", {}).items():
            (d / fname).write_text(content, encoding="utf-8")
    return base


def _md5(s: str) -> str:
    return hashlib.md5(s.encode()).hexdigest()


# ---------------------------------------------------------------------------
# primitives
# ---------------------------------------------------------------------------


def test_md5_missing_returns_none(tmp_path):
    assert sdc._md5(tmp_path / "nope") is None


def test_md5_known(tmp_path):
    p = tmp_path / "f"; p.write_text("hello")
    assert sdc._md5(p) == _md5("hello")


@pytest.mark.parametrize("name,expected", [
    ("SKILL.md", False),
    ("SKILL.md.backup.2026-04-10", True),
])
def test_is_backup(name, expected):
    assert sdc._is_backup(name) is expected


# ---------------------------------------------------------------------------
# evaluate
# ---------------------------------------------------------------------------


def test_evaluate_all_match(tmp_path):
    repo = _repo(tmp_path, {"a": {"files": {"SKILL.md": "same"}}})
    dep = _deployed(tmp_path, {"a": {"files": {"SKILL.md": "same"}}})
    rows = sdc.evaluate(repo, dep)
    assert len(rows) == 1 and rows[0].state == sdc.STATE_MATCH
    assert rows[0].repo_md5 == rows[0].deployed_md5 == _md5("same")


def test_evaluate_content_drift(tmp_path):
    repo = _repo(tmp_path, {"a": {"files": {"SKILL.md": "new"}}})
    dep = _deployed(tmp_path, {"a": {"files": {"SKILL.md": "old"}}})
    rows = sdc.evaluate(repo, dep)
    assert rows[0].state == sdc.STATE_DRIFT
    assert rows[0].repo_md5 == _md5("new") and rows[0].deployed_md5 == _md5("old")


def test_evaluate_missing_deployed_is_drift(tmp_path):
    repo = _repo(tmp_path, {"a": {"files": {"SKILL.md": "x"}}})
    dep = _deployed(tmp_path, {})  # base exists, no skill
    rows = sdc.evaluate(repo, dep)
    assert rows[0].state == sdc.STATE_DRIFT and rows[0].deployed_md5 is None


def test_evaluate_orphan(tmp_path):
    repo = _repo(tmp_path, {"a": {"files": {"SKILL.md": "x"}}})
    dep = _deployed(tmp_path, {
        "a": {"files": {"SKILL.md": "x"}},
        "gone": {"files": {"SKILL.md": "orphaned"}},  # deployed, not in repo
    })
    rows = sdc.evaluate(repo, dep)
    states = {r.skill: r.state for r in rows}
    assert states["a"] == sdc.STATE_MATCH
    assert states["gone"] == sdc.STATE_ORPHAN


def test_evaluate_ignores_backup_sidecar(tmp_path):
    repo = _repo(tmp_path, {"a": {"files": {"SKILL.md": "x"}}})
    dep = _deployed(tmp_path, {"a": {"files": {
        "SKILL.md": "x", "SKILL.md.backup.2026-04-10": "old",
    }}})
    rows = sdc.evaluate(repo, dep)
    # backup does not create a second row, does not flip match, is not an orphan
    assert len(rows) == 1 and rows[0].state == sdc.STATE_MATCH


def test_evaluate_repo_dir_without_skillmd_is_not_a_skill(tmp_path):
    repo = _repo(tmp_path, {
        "a": {"files": {"SKILL.md": "x"}},
        "notaskill": {"files": {"README.md": "docs"}},
    })
    dep = _deployed(tmp_path, {"a": {"files": {"SKILL.md": "x"}}})
    rows = sdc.evaluate(repo, dep)
    assert [r.skill for r in rows] == ["a"]  # notaskill ignored


def test_evaluate_missing_repo_dir_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        sdc.evaluate(tmp_path / "nonexistent", tmp_path / "dep")


# ---------------------------------------------------------------------------
# main / exit contract
# ---------------------------------------------------------------------------


def _args(repo, dep, *extra):
    return [*extra, "--repo-root", str(repo), "--deployed-base", str(dep)]


def test_main_clean_exit_0(tmp_path, capsys):
    repo = _repo(tmp_path, {"a": {"files": {"SKILL.md": "x"}}})
    dep = _deployed(tmp_path, {"a": {"files": {"SKILL.md": "x"}}})
    rc = sdc.main(_args(repo, dep))
    assert rc == sdc.EXIT_CLEAN
    assert "OK 1 skills in sync" in capsys.readouterr().out


def test_main_drift_exit_1(tmp_path, capsys):
    repo = _repo(tmp_path, {"a": {"files": {"SKILL.md": "new"}}})
    dep = _deployed(tmp_path, {"a": {"files": {"SKILL.md": "old"}}})
    rc = sdc.main(_args(repo, dep))
    assert rc == sdc.EXIT_DRIFT
    assert "DRIFT a" in capsys.readouterr().out


def test_main_orphan_exit_1(tmp_path, capsys):
    repo = _repo(tmp_path, {"a": {"files": {"SKILL.md": "x"}}})
    dep = _deployed(tmp_path, {
        "a": {"files": {"SKILL.md": "x"}},
        "gone": {"files": {"SKILL.md": "o"}},
    })
    rc = sdc.main(_args(repo, dep))
    assert rc == sdc.EXIT_DRIFT
    assert "ORPHAN gone" in capsys.readouterr().out


def test_main_unreadable_exit_2(tmp_path):
    rc = sdc.main(_args(tmp_path / "nonexistent", tmp_path / "dep"))
    assert rc == sdc.EXIT_UNREADABLE


def test_main_json_shape(tmp_path, capsys):
    repo = _repo(tmp_path, {"a": {"files": {"SKILL.md": "new"}}})
    dep = _deployed(tmp_path, {"a": {"files": {"SKILL.md": "old"}}})
    rc = sdc.main(_args(repo, dep, "--json"))
    assert rc == sdc.EXIT_DRIFT
    payload = json.loads(capsys.readouterr().out)
    assert payload == [{
        "skill": "a", "state": "drift",
        "repo_md5": _md5("new"), "deployed_md5": _md5("old"),
    }]
