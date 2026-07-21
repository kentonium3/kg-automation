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


# --- Invariant B: output discipline (presence-or-annotation) ------------------


def test_output_discipline_block_passes(tmp_path: Path) -> None:
    ws = _write(
        tmp_path / "agent",
        AGENTS_md="## Output Discipline (Hard Rules)\n",
    )
    assert _check(validate_workspace(ws), "output_discipline").ok


def test_output_discipline_block_in_soul_passes(tmp_path: Path) -> None:
    """#805: the block is accepted in SOUL.md (OpenClaw loads all prompt files),
    but the detail flags AGENTS.md as the preferred home for discoverability."""
    ws = _write(
        tmp_path / "agent",
        AGENTS_md="Some routing rules.\n",
        SOUL_md="## Output discipline\nHard rule #1 ...\n",
    )
    result = _check(validate_workspace(ws), "output_discipline")
    assert result.ok
    assert "SOUL.md" in result.detail
    assert "preferred home is AGENTS.md" in result.detail


def test_output_discipline_block_in_tools_not_accepted(tmp_path: Path) -> None:
    """TOOLS.md is a tool-reference file, not a home for a behavioral output
    rule — a block there does NOT satisfy Invariant B (#805 scoped to AGENTS/SOUL)."""
    ws = _write(
        tmp_path / "agent",
        AGENTS_md="Some routing rules.\n",
        TOOLS_md="## Output discipline\nHard rule #1 ...\n",
    )
    result = _check(validate_workspace(ws), "output_discipline")
    assert not result.ok
    assert "missing" in result.detail


def test_output_discipline_prose_mention_does_not_false_pass(tmp_path: Path) -> None:
    """Anchored to the ## heading: a bare phrase in prose must not satisfy it."""
    ws = _write(
        tmp_path / "agent",
        AGENTS_md="This agent controls its output discipline tightly.\n",
    )
    assert not _check(validate_workspace(ws), "output_discipline").ok


def test_output_discipline_agents_md_preferred_when_in_both(tmp_path: Path) -> None:
    """AGENTS.md wins the report even if the block also appears in SOUL.md —
    no 'preferred home' note when it is already in AGENTS.md."""
    ws = _write(
        tmp_path / "agent",
        AGENTS_md="## Output discipline\nrules\n",
        SOUL_md="## Output discipline\ncopy\n",
    )
    result = _check(validate_workspace(ws), "output_discipline")
    assert result.ok
    assert "AGENTS.md" in result.detail
    assert "preferred home" not in result.detail


def test_no_whatsapp_annotation_passes(tmp_path: Path) -> None:
    ws = _write(
        tmp_path / "agent",
        AGENTS_md="This agent has no user-facing WhatsApp.\n",
    )
    result = _check(validate_workspace(ws), "output_discipline")
    assert result.ok
    assert "annotation" in result.detail


def test_output_discipline_missing_without_annotation_fails(tmp_path: Path) -> None:
    ws = _write(
        tmp_path / "agent",
        AGENTS_md="Some routing rules.\n",
    )
    result = _check(validate_workspace(ws), "output_discipline")
    assert not result.ok
    assert "missing" in result.detail


def test_fully_compliant_workspace_is_ok(tmp_path: Path) -> None:
    ws = _write(
        tmp_path / "agent",
        AGENTS_md="## Output discipline\nrules\n",
    )
    assert validate_workspace(ws).ok


# --- Invariant C: runtime-env assumptions (#662, corrects #658) ---------------


def test_runtime_env_assumptions_clean_passes(tmp_path: Path) -> None:
    ws = _write(
        tmp_path / "agent",
        AGENTS_md=(
            "## Output discipline\n"
            "Invoke `cd /home/claude/kg-automation && python3 -m scripts.inbox.prescan`.\n"
        ),
    )
    result = _check(validate_workspace(ws), "runtime_env_assumptions")
    assert result.ok
    assert result.detail == "ok"


def test_runtime_env_assumptions_bare_invocation_fails(tmp_path: Path) -> None:
    ws = _write(
        tmp_path / "agent",
        AGENTS_md=(
            "## Output discipline\n"
            "Invoke `python3 -m scripts.inbox.prescan`.\n"  # bare — unanchored
        ),
    )
    result = _check(validate_workspace(ws), "runtime_env_assumptions")
    assert not result.ok
    assert "bare_m_scripts" in result.detail


def test_runtime_env_assumptions_pythonpath_anchor_fails(tmp_path: Path) -> None:
    # The old #658 canonical form is now a violation (fails under OpenClaw exec).
    ws = _write(
        tmp_path / "agent",
        AGENTS_md=(
            "## Output discipline\n"
            '```bash\ncd "${PYTHONPATH:?msg}" && python3 -m scripts.habits.x\n```\n'
        ),
    )
    result = _check(validate_workspace(ws), "runtime_env_assumptions")
    assert not result.ok
    assert "pythonpath_anchor" in result.detail


def test_runtime_env_assumptions_failure_bubbles_to_workspace_ok(tmp_path: Path) -> None:
    ws = _write(
        tmp_path / "agent",
        AGENTS_md="## Output discipline\npython3 -m scripts.inbox.prescan\n",
    )
    assert not validate_workspace(ws).ok  # a runtime-env violation fails the whole workspace


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
    """felix-admin-capture is the canonical Output Discipline source, and
    (post-fleet-migration, #662) also a clean ``runtime_env_assumptions`` corpus.

    The remaining per-workspace invariants are asserted now that WP02/WP03 have
    swapped the fleet to the self-contained checkout-``cd`` form. The whole-fleet
    migration gate additionally lives in ``test_env_assumptions_guard.py``.
    """
    root = repo_root / "scripts/openclaw/agents"
    report = next(r for r in validate_all(root) if r.workspace == "felix-admin-capture")
    assert _check(report, "output_discipline").ok, _check(report, "output_discipline").detail
    assert _check(report, "runtime_env_assumptions").ok, _check(report, "runtime_env_assumptions").detail


def test_live_doc_auditor_excluded(repo_root: Path) -> None:
    """Suspended felix-doc-auditor must not be validated even though its dir exists."""
    root = repo_root / "scripts/openclaw/agents"
    names = {r.workspace for r in validate_all(root)}
    assert "felix-doc-auditor" not in names
