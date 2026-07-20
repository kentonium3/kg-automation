"""Unit tests for the deployed-unit-vs-repo drift detector (#817).

The pure diff (:func:`detect_unit_drift`) is fed in-memory tuples; the I/O
collectors (:func:`build_repo_index`, :func:`enumerate_deployed`,
:func:`enumerate_unit_pairs`) are exercised against ``tmp_path`` trees so no
test touches office2 or the real ``~/.config/systemd/user``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.trust.unit_drift_detector import (
    EXCLUDED_DEPLOYED_UNITS,
    UnitDriftFinding,
    UnitEnumerationError,
    _normalize,
    build_repo_index,
    detect_unit_drift,
    enumerate_deployed,
    enumerate_unit_pairs,
)


# --- _normalize ---------------------------------------------------------------


def test_normalize_ignores_trailing_whitespace_and_eol():
    assert _normalize("A\nB   \n") == _normalize("A   \nB\n\n") == "A\nB\n"


def test_normalize_preserves_meaningful_content():
    assert _normalize("ExecStart=/x\n") != _normalize("ExecStart=/y\n")


def test_normalize_drops_comment_and_blank_lines():
    with_comments = "# rationale block\nExecStart=/x\n\n; a note\nEnvironment=A=1\n"
    functional_only = "ExecStart=/x\nEnvironment=A=1\n"
    assert _normalize(with_comments) == _normalize(functional_only)


def test_detect_comment_only_diff_is_not_drift():
    # A comment-only edit against a not-yet-redeployed unit is not functional drift.
    pairs = [("u.service", "scripts/office2/u.service", "# new rationale\nExecStart=/x\n", "# old rationale\nExecStart=/x\n")]
    assert detect_unit_drift(pairs) == []


def test_detect_directive_change_drifts_even_amid_comments():
    # Comment stripping must never mask a real directive change (no false-clean).
    pairs = [("u.service", "scripts/office2/u.service", "# c\nExecStart=/new\n", "# c\nExecStart=/old\n")]
    assert [f.name for f in detect_unit_drift(pairs)] == ["u.service"]


# --- detect_unit_drift (pure) -------------------------------------------------


def test_detect_identical_no_finding():
    pairs = [("a.service", "scripts/office2/a.service", "X\n", "X\n")]
    assert detect_unit_drift(pairs) == []


def test_detect_content_drift_yields_finding():
    pairs = [("b.service", "scripts/office2/b.service", "ExecStart=new\n", "ExecStart=old\n")]
    findings = detect_unit_drift(pairs)
    assert len(findings) == 1
    f = findings[0]
    assert isinstance(f, UnitDriftFinding)
    assert (f.kind, f.name, f.repo_source) == ("content_drift", "b.service", "scripts/office2/b.service")


def test_detect_whitespace_only_diff_is_not_drift():
    pairs = [("c.service", "scripts/office2/c.service", "X\nY\n", "X   \nY\n\n")]
    assert detect_unit_drift(pairs) == []


def test_detect_findings_sorted_by_name():
    pairs = [
        ("z.timer", "scripts/office2/z.timer", "1\n", "2\n"),
        ("a.service", "scripts/office2/a.service", "1\n", "2\n"),
    ]
    assert [f.name for f in detect_unit_drift(pairs)] == ["a.service", "z.timer"]


# --- build_repo_index ---------------------------------------------------------


def _mk(path: Path, text: str = "unit\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_build_repo_index_spans_all_source_dirs(tmp_path):
    _mk(tmp_path / "scripts/office2/felix-a.service")
    _mk(tmp_path / "scripts/openclaw/deploy/agent-b.timer")
    _mk(tmp_path / "scripts/sync/systemd/felix-c.service")
    _mk(tmp_path / "scripts/deploy/felix-deployer/felix-deployer.service")
    index = build_repo_index(tmp_path)
    assert set(index) == {
        "felix-a.service",
        "agent-b.timer",
        "felix-c.service",
        "felix-deployer.service",
    }


def test_build_repo_index_raises_on_basename_collision(tmp_path):
    _mk(tmp_path / "scripts/office2/dupe.service", "one\n")
    _mk(tmp_path / "scripts/sync/systemd/dupe.service", "two\n")
    with pytest.raises(UnitEnumerationError, match="duplicate unit basenames"):
        build_repo_index(tmp_path)


def test_build_repo_index_ignores_non_unit_files(tmp_path):
    _mk(tmp_path / "scripts/office2/felix-a.service")
    _mk(tmp_path / "scripts/office2/deploy-helper.sh", "#!/bin/bash\n")
    _mk(tmp_path / "scripts/office2/notes.md", "hi\n")
    assert set(build_repo_index(tmp_path)) == {"felix-a.service"}


# --- enumerate_deployed -------------------------------------------------------


def test_enumerate_deployed_missing_dir_raises(tmp_path):
    with pytest.raises(UnitEnumerationError, match="deployed unit dir not found"):
        enumerate_deployed(tmp_path / "nope")


def test_enumerate_deployed_lists_units(tmp_path):
    _mk(tmp_path / "x.service")
    _mk(tmp_path / "x.timer")
    _mk(tmp_path / "ignore.conf")
    assert set(enumerate_deployed(tmp_path)) == {"x.service", "x.timer"}


# --- enumerate_unit_pairs (coverage policy) -----------------------------------


def test_enumerate_pairs_excludes_openclaw_gateway(tmp_path):
    excluded_unit = next(iter(EXCLUDED_DEPLOYED_UNITS))
    repo = tmp_path / "repo"
    deployed = tmp_path / "deployed"
    deployed.mkdir()
    (deployed / excluded_unit).write_text("managed by openclaw\n", encoding="utf-8")
    _mk(repo / "scripts/office2/felix-a.service", "A\n")
    (deployed / "felix-a.service").write_text("A\n", encoding="utf-8")

    pairs, coverage = enumerate_unit_pairs(repo, deployed)
    assert [u for u, *_ in pairs] == ["felix-a.service"]
    assert coverage.excluded == [excluded_unit]
    assert coverage.compared == ["felix-a.service"]


def test_enumerate_pairs_flags_deployed_without_repo_source(tmp_path):
    repo = tmp_path / "repo"
    deployed = tmp_path / "deployed"
    deployed.mkdir()
    (repo / "scripts/office2").mkdir(parents=True)
    (deployed / "orphan.service").write_text("no repo source\n", encoding="utf-8")

    pairs, coverage = enumerate_unit_pairs(repo, deployed)
    assert pairs == []
    assert coverage.deployed_no_repo_source == ["orphan.service"]


def test_enumerate_pairs_reports_repo_only_units(tmp_path):
    repo = tmp_path / "repo"
    deployed = tmp_path / "deployed"
    deployed.mkdir()
    _mk(repo / "scripts/office2/deployed-one.service", "X\n")
    _mk(repo / "scripts/office2/never-deployed.timer", "Y\n")
    (deployed / "deployed-one.service").write_text("X\n", encoding="utf-8")

    _, coverage = enumerate_unit_pairs(repo, deployed)
    assert coverage.repo_only == ["never-deployed.timer"]


def test_enumerate_pairs_carries_content_for_drift(tmp_path):
    repo = tmp_path / "repo"
    deployed = tmp_path / "deployed"
    deployed.mkdir()
    _mk(repo / "scripts/office2/felix-a.service", "ExecStart=/new\n")
    (deployed / "felix-a.service").write_text("ExecStart=/old\n", encoding="utf-8")

    pairs, _ = enumerate_unit_pairs(repo, deployed)
    findings = detect_unit_drift(pairs)
    assert [(f.name, f.repo_source) for f in findings] == [
        ("felix-a.service", "scripts/office2/felix-a.service")
    ]
