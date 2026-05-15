"""Tests for `scripts/openclaw/agents/main/felix-file-issue.py` (mission #291).

Tests use `--dry-run` to exercise the body-building and label/title logic
without invoking gh CLI. The identity-check path (verify_gh_identity) is
covered by a separate test that mocks subprocess.run.

Mirrors the test pattern in
`tests/openclaw/agents/felix-doc-auditor/test_handle_audit_routing.py`.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


REPO_ROOT = Path(__file__).resolve().parents[4]
HELPER_PATH = (
    REPO_ROOT
    / "scripts"
    / "openclaw"
    / "agents"
    / "main"
    / "felix-file-issue.py"
)


def run_dry(*extra_args, problem_statement: str = "Test problem statement.", observed_context: str | None = None, tmp_path: Path):
    """Invoke the helper via subprocess in --dry-run mode."""
    ps_file = tmp_path / "problem.txt"
    ps_file.write_text(problem_statement)
    cmd = [
        sys.executable,
        str(HELPER_PATH),
        "--problem-statement-file", str(ps_file),
        "--dry-run",
        *extra_args,
    ]
    if observed_context:
        oc_file = tmp_path / "context.txt"
        oc_file.write_text(observed_context)
        cmd.extend(["--observed-context-file", str(oc_file)])
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return result


# ---------- Validation tests ----------


def test_missing_required_args_exits_2(tmp_path):
    """argparse rejects missing required args with exit code 2."""
    # Missing --type, --title, --tier-hypothesis, --area, --priority
    ps_file = tmp_path / "p.txt"
    ps_file.write_text("test")
    result = subprocess.run(
        [sys.executable, str(HELPER_PATH),
         "--problem-statement-file", str(ps_file),
         "--dry-run"],
        capture_output=True, text=True,
    )
    assert result.returncode == 2


def test_invalid_type_exits_2(tmp_path):
    result = run_dry(
        "--type", "garbage",
        "--title", "Test",
        "--tier-hypothesis", "2",
        "--area", "felix-core",
        "--priority", "P2",
        tmp_path=tmp_path,
    )
    assert result.returncode == 2


def test_invalid_priority_exits_2(tmp_path):
    result = run_dry(
        "--type", "bug",
        "--title", "Test",
        "--tier-hypothesis", "2",
        "--area", "felix-core",
        "--priority", "PX",
        tmp_path=tmp_path,
    )
    assert result.returncode == 2


def test_p3_priority_rejected(tmp_path):
    """P3 is intentionally excluded; only `P3-candidate` exists as a label
    in the repo, and Felix should not auto-assign candidate status."""
    result = run_dry(
        "--type", "bug",
        "--title", "Test",
        "--tier-hypothesis", "2",
        "--area", "felix-core",
        "--priority", "P3",
        tmp_path=tmp_path,
    )
    assert result.returncode == 2


def test_invalid_tier_exits_2(tmp_path):
    result = run_dry(
        "--type", "bug",
        "--title", "Test",
        "--tier-hypothesis", "9",
        "--area", "felix-core",
        "--priority", "P2",
        tmp_path=tmp_path,
    )
    assert result.returncode == 2


def test_empty_problem_statement_exits_2(tmp_path):
    result = run_dry(
        "--type", "bug",
        "--title", "Test",
        "--tier-hypothesis", "2",
        "--area", "felix-core",
        "--priority", "P2",
        problem_statement="",
        tmp_path=tmp_path,
    )
    assert result.returncode == 2
    assert "empty" in result.stderr.lower()


def test_unknown_area_warns_but_continues(tmp_path):
    """Helper trusts caller for area label; emits WARN to stderr but proceeds."""
    result = run_dry(
        "--type", "bug",
        "--title", "Test",
        "--tier-hypothesis", "2",
        "--area", "totally-new-area",
        "--priority", "P2",
        tmp_path=tmp_path,
    )
    assert result.returncode == 0
    assert "WARN" in result.stderr
    assert "totally-new-area" in result.stderr


# ---------- Title prefix tests ----------


@pytest.mark.parametrize("type_,expected_prefix", [
    ("bug", "Bug:"),
    ("feature", "Feature:"),
    ("infra", "Infra:"),
    ("research", "Research:"),
])
def test_title_prefix_matches_type(tmp_path, type_, expected_prefix):
    """Each type produces a title with the correct prefix."""
    result = run_dry(
        "--type", type_,
        "--title", "Some test title",
        "--tier-hypothesis", "2",
        "--area", "felix-core",
        "--priority", "P2",
        tmp_path=tmp_path,
    )
    assert result.returncode == 0
    assert f"{expected_prefix} Some test title" in result.stdout


# ---------- Body construction tests ----------


def test_bug_body_includes_summary_and_actual_behavior(tmp_path):
    problem = "Cron job foo timed out 3 days."
    result = run_dry(
        "--type", "bug",
        "--title", "Foo timeout",
        "--tier-hypothesis", "2",
        "--area", "felix-core",
        "--priority", "P2",
        problem_statement=problem,
        tmp_path=tmp_path,
    )
    assert result.returncode == 0
    assert "## Summary" in result.stdout
    assert "## Actual behavior" in result.stdout
    assert problem in result.stdout


def test_feature_body_includes_executive_summary(tmp_path):
    problem = "Felix needs a way to do X."
    result = run_dry(
        "--type", "feature",
        "--title", "Add X capability",
        "--tier-hypothesis", "3",
        "--area", "felix-core",
        "--priority", "P2",
        problem_statement=problem,
        tmp_path=tmp_path,
    )
    assert result.returncode == 0
    assert "## Executive Summary" in result.stdout
    assert "## Functional Requirements" in result.stdout
    assert problem in result.stdout


def test_infra_body_marks_correct_tier(tmp_path):
    """Infra body has a tier-selection checklist with the hypothesized tier checked."""
    result = run_dry(
        "--type", "infra",
        "--title", "Some infra change",
        "--tier-hypothesis", "2",
        "--area", "felix-core",
        "--priority", "P2",
        tmp_path=tmp_path,
    )
    assert result.returncode == 0
    # Tier 2 should be checked, others unchecked
    assert "- [x] **Tier 2 — Application / State" in result.stdout
    assert "- [ ] **Tier 0 — Host / Foundational" in result.stdout


def test_research_body_includes_research_purpose(tmp_path):
    result = run_dry(
        "--type", "research",
        "--title", "Investigate Y",
        "--tier-hypothesis", "unknown",
        "--area", "felix-core",
        "--priority", "P2",
        tmp_path=tmp_path,
    )
    assert result.returncode == 0
    assert "## Research Purpose" in result.stdout
    assert "## Research Questions" in result.stdout


def test_observed_context_appears_in_body(tmp_path):
    """When --observed-context-file is provided, content shows up in Evidence."""
    context = "Error log: foo failed at 2026-05-15"
    result = run_dry(
        "--type", "bug",
        "--title", "Foo failure",
        "--tier-hypothesis", "2",
        "--area", "felix-core",
        "--priority", "P2",
        observed_context=context,
        tmp_path=tmp_path,
    )
    assert result.returncode == 0
    assert context in result.stdout


def test_related_issues_normalized_and_included(tmp_path):
    """--related-issues '#270, 285, #285' produces formatted '- #270', '- #285', '- #285'."""
    result = run_dry(
        "--type", "bug",
        "--title", "Test",
        "--tier-hypothesis", "2",
        "--area", "felix-core",
        "--priority", "P2",
        "--related-issues", "#270, 285",
        tmp_path=tmp_path,
    )
    assert result.returncode == 0
    assert "- #270" in result.stdout
    assert "- #285" in result.stdout  # bare 285 gets '#' prepended


def test_spec_ready_eval_brief_unchecks_criteria(tmp_path):
    """Default --spec-ready-eval=brief leaves spec-ready checklist items unchecked."""
    result = run_dry(
        "--type", "bug",
        "--title", "Test",
        "--tier-hypothesis", "2",
        "--area", "felix-core",
        "--priority", "P2",
        tmp_path=tmp_path,
    )
    assert result.returncode == 0
    # spec-ready section should have unchecked boxes
    assert "## Spec-ready criteria" in result.stdout
    assert "- [ ] **Summary**" in result.stdout
    # All items unchecked
    assert "- [x] **Summary**" not in result.stdout


def test_spec_ready_eval_ready_checks_criteria(tmp_path):
    """--spec-ready-eval=ready checks all spec-ready items."""
    result = run_dry(
        "--type", "bug",
        "--title", "Test",
        "--tier-hypothesis", "2",
        "--area", "felix-core",
        "--priority", "P2",
        "--spec-ready-eval", "ready",
        tmp_path=tmp_path,
    )
    assert result.returncode == 0
    assert "- [x] **Summary**" in result.stdout


# ---------- Label discipline tests ----------


def test_labels_constructed_correctly(tmp_path):
    """Labels are P<N>-<type>, area/<area>, spec: <eval>."""
    result = run_dry(
        "--type", "bug",
        "--title", "Test",
        "--tier-hypothesis", "2",
        "--area", "felix-core",
        "--priority", "P2",
        "--spec-ready-eval", "brief",
        tmp_path=tmp_path,
    )
    assert result.returncode == 0
    # Labels appear in the LABELS section of dry-run output
    assert "P2-bug" in result.stdout
    assert "area/felix-core" in result.stdout
    assert "spec: brief" in result.stdout


# ---------- Dry-run + SUMMARY line ----------


def test_dry_run_does_not_attempt_gh_invocation(tmp_path):
    """--dry-run skips gh identity check AND gh issue create entirely."""
    # If gh weren't skipped, the test environment likely wouldn't have kg-felix-bot
    # auth, and the helper would fail. Dry-run reaching exit 0 is the assertion.
    result = run_dry(
        "--type", "bug",
        "--title", "Test",
        "--tier-hypothesis", "2",
        "--area", "felix-core",
        "--priority", "P2",
        tmp_path=tmp_path,
    )
    assert result.returncode == 0
    assert "SUMMARY:" in result.stdout
    assert "dry_run=True" in result.stdout
