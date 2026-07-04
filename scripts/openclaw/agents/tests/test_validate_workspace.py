"""Tests for the OpenClaw workspace shared-invariant validator (#587, FR-2).

Synthetic ``tmp_path`` workspaces exercise the invariant logic (present /
annotated-absent / missing / SOUL-only cases). A small set of live-corpus
assertions anchor the checker against the real repository state without asserting
the whole corpus is green (some agents carry pre-existing authoring debt that the
per-agent authoring children of #167 will resolve).
"""

from __future__ import annotations

from pathlib import Path

from scripts.openclaw.agents.validate_workspace import (
    SUSPENDED_WORKSPACES,
    discover_workspaces,
    validate_all,
    validate_workspace,
)


def _write(ws: Path, **files: str) -> Path:
    """Create a workspace dir with the given ``FILENAME=text`` files."""
    ws.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (ws / name.replace("_md", ".md")).write_text(text, encoding="utf-8")
    return ws


def _check(report, name: str):
    return next(c for c in report.checks if c.name == name)


# --- Invariant A: privacy boundary --------------------------------------------


def test_privacy_present_in_agents_passes(tmp_path: Path) -> None:
    ws = _write(
        tmp_path / "agent",
        AGENTS_md="never touch 04-Growth/_private/\n## Output discipline\n",
    )
    report = validate_workspace(ws)
    assert _check(report, "privacy_boundary").ok


def test_privacy_present_in_tools_passes(tmp_path: Path) -> None:
    ws = _write(
        tmp_path / "agent",
        AGENTS_md="## Output discipline\n",
        TOOLS_md="NEVER access: 04-Growth/_private/\n",
    )
    assert _check(validate_workspace(ws), "privacy_boundary").ok


def test_privacy_only_in_soul_fails_with_stance_detail(tmp_path: Path) -> None:
    ws = _write(
        tmp_path / "agent",
        AGENTS_md="## Output discipline\n",
        SOUL_md="I never touch 04-Growth/_private/\n",
    )
    result = _check(validate_workspace(ws), "privacy_boundary")
    assert not result.ok
    assert "only in SOUL.md" in result.detail


def test_privacy_missing_entirely_fails(tmp_path: Path) -> None:
    ws = _write(tmp_path / "agent", AGENTS_md="## Output discipline\n")
    result = _check(validate_workspace(ws), "privacy_boundary")
    assert not result.ok
    assert "missing" in result.detail


# --- Invariant B: output discipline (presence-or-annotation) ------------------


def test_output_discipline_block_passes(tmp_path: Path) -> None:
    ws = _write(
        tmp_path / "agent",
        AGENTS_md="04-Growth/_private/\n## Output Discipline (Hard Rules)\n",
    )
    assert _check(validate_workspace(ws), "output_discipline").ok


def test_no_whatsapp_annotation_passes(tmp_path: Path) -> None:
    ws = _write(
        tmp_path / "agent",
        AGENTS_md="04-Growth/_private/\nThis agent has no user-facing WhatsApp.\n",
    )
    result = _check(validate_workspace(ws), "output_discipline")
    assert result.ok
    assert "annotation" in result.detail


def test_output_discipline_missing_without_annotation_fails(tmp_path: Path) -> None:
    ws = _write(
        tmp_path / "agent",
        AGENTS_md="04-Growth/_private/\nSome routing rules.\n",
    )
    result = _check(validate_workspace(ws), "output_discipline")
    assert not result.ok
    assert "missing" in result.detail


def test_fully_compliant_workspace_is_ok(tmp_path: Path) -> None:
    ws = _write(
        tmp_path / "agent",
        AGENTS_md="04-Growth/_private/ never touch\n## Output discipline\nrules\n",
    )
    assert validate_workspace(ws).ok


# --- Discovery ----------------------------------------------------------------


def test_discover_excludes_suspended_and_non_workspaces(tmp_path: Path) -> None:
    _write(tmp_path / "felix-admin-x", AGENTS_md="x")
    _write(tmp_path / "felix-doc-auditor", AGENTS_md="x")  # suspended
    _write(tmp_path / "tests", AGENTS_md="x")  # non-workspace
    (tmp_path / "no-agents-file").mkdir()
    found = {d.name for d in discover_workspaces(tmp_path)}
    assert found == {"felix-admin-x"}
    assert "felix-doc-auditor" in SUSPENDED_WORKSPACES


# --- Live corpus anchors ------------------------------------------------------


def test_live_capture_workspace_passes(repo_root: Path) -> None:
    """felix-admin-capture is the canonical Output Discipline source — must pass."""
    root = repo_root / "scripts/openclaw/agents"
    report = next(r for r in validate_all(root) if r.workspace == "felix-admin-capture")
    assert report.ok, [c.detail for c in report.checks if not c.ok]


def test_live_doc_auditor_excluded(repo_root: Path) -> None:
    """Suspended felix-doc-auditor must not be validated even though its dir exists."""
    root = repo_root / "scripts/openclaw/agents"
    names = {r.workspace for r in validate_all(root)}
    assert "felix-doc-auditor" not in names
